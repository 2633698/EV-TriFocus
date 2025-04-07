# Sample code for ev_model_training.py

from datetime import datetime
import os
import torch
import torch.nn as nn
import torch.optim as optim
import numpy as np
import pandas as pd
from torch.utils.data import DataLoader, Dataset

class EVChargingDataset(Dataset):
    def __init__(self, features, targets):
        self.features = features
        self.targets = targets
    
    def __len__(self):
        return len(self.features)
    
    def __getitem__(self, idx):
        return self.features[idx], self.targets[idx]

class MultiTaskModel(nn.Module):
    def __init__(self, input_dim, hidden_dim, task_hidden_dim):
        super(MultiTaskModel, self).__init__()
        self.base = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU()
        )
        
        # Task-specific heads
        self.user_head = nn.Sequential(
            nn.Linear(hidden_dim, task_hidden_dim),
            nn.ReLU(),
            nn.Linear(task_hidden_dim, 1),
            nn.Tanh()  # Output in [-1, 1]
        )
        
        self.profit_head = nn.Sequential(
            nn.Linear(hidden_dim, task_hidden_dim),
            nn.ReLU(),
            nn.Linear(task_hidden_dim, 1),
            nn.Tanh()  # Output in [-1, 1]
        )
        
        self.grid_head = nn.Sequential(
            nn.Linear(hidden_dim, task_hidden_dim),
            nn.ReLU(),
            nn.Linear(task_hidden_dim, 1),
            nn.Tanh()  # Output in [-1, 1]
        )
    
    def forward(self, x):
        base_features = self.base(x)
        user_satisfaction = self.user_head(base_features)
        operator_profit = self.profit_head(base_features)
        grid_friendliness = self.grid_head(base_features)
        
        return user_satisfaction, operator_profit, grid_friendliness

def train_model(model, train_loader, val_loader, optimizer, criterion, num_epochs=50):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)
    
    best_val_loss = float('inf')
    best_model_state = None
    
    for epoch in range(num_epochs):
        # Training
        model.train()
        train_loss = 0.0
        
        for features, targets in train_loader:
            features = features.to(device)
            user_target = targets[:, 0].unsqueeze(1).to(device)
            profit_target = targets[:, 1].unsqueeze(1).to(device)
            grid_target = targets[:, 2].unsqueeze(1).to(device)
            
            optimizer.zero_grad()
            
            user_pred, profit_pred, grid_pred = model(features)
            
            loss_user = criterion(user_pred, user_target)
            loss_profit = criterion(profit_pred, profit_target)
            loss_grid = criterion(grid_pred, grid_target)
            
            loss = loss_user + loss_profit + loss_grid
            loss.backward()
            optimizer.step()
            
            train_loss += loss.item()
        
        train_loss /= len(train_loader)
        
        # Validation
        model.eval()
        val_loss = 0.0
        
        with torch.no_grad():
            for features, targets in val_loader:
                features = features.to(device)
                user_target = targets[:, 0].unsqueeze(1).to(device)
                profit_target = targets[:, 1].unsqueeze(1).to(device)
                grid_target = targets[:, 2].unsqueeze(1).to(device)
                
                user_pred, profit_pred, grid_pred = model(features)
                
                loss_user = criterion(user_pred, user_target)
                loss_profit = criterion(profit_pred, profit_target)
                loss_grid = criterion(grid_pred, grid_target)
                
                loss = loss_user + loss_profit + loss_grid
                val_loss += loss.item()
        
        val_loss /= len(val_loader)
        
        print(f"Epoch {epoch+1}/{num_epochs}, Train Loss: {train_loss:.4f}, Val Loss: {val_loss:.4f}")
        
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_model_state = model.state_dict()
    
    # Load best model
    model.load_state_dict(best_model_state)
    return model

def prepare_data_from_simulation(history):
    """Convert simulation history to training data"""
    features = []
    targets = []
    
    for item in history:
        # Extract timestamp
        timestamp = datetime.fromisoformat(item["timestamp"])
        
        # Create feature vector
        feature = [
            timestamp.hour / 24,  # Hour (normalized)
            timestamp.weekday() / 6,  # Day of week (normalized)
            item.get("grid_load", 50) / 100,  # Grid load (normalized)
            item.get("ev_load", 0) / 100,  # EV load (normalized)
            item.get("renewable_ratio", 0) / 100  # Renewable ratio (normalized)
        ]
        
        # Add one-hot encoding for peak/valley hours
        for h in range(24):
            feature.append(1 if timestamp.hour == h else 0)
        
        # Add targets
        rewards = item.get("rewards", {})
        target = [
            rewards.get("user_satisfaction", 0),
            rewards.get("operator_profit", 0),
            rewards.get("grid_friendliness", 0)
        ]
        
        features.append(feature)
        targets.append(target)
    
    return np.array(features, dtype=np.float32), np.array(targets, dtype=np.float32)

def train_and_save_model(history, config):
    """Train model from simulation history and save it"""
    # Prepare data
    features, targets = prepare_data_from_simulation(history)
    
    # Split into train/val
    indices = np.random.permutation(len(features))
    train_size = int(len(features) * 0.8)
    train_indices = indices[:train_size]
    val_indices = indices[train_size:]
    
    train_features = features[train_indices]
    train_targets = targets[train_indices]
    val_features = features[val_indices]
    val_targets = targets[val_indices]
    
    # Create datasets and dataloaders
    train_dataset = EVChargingDataset(
        torch.FloatTensor(train_features),
        torch.FloatTensor(train_targets)
    )
    val_dataset = EVChargingDataset(
        torch.FloatTensor(val_features),
        torch.FloatTensor(val_targets)
    )
    
    train_loader = DataLoader(train_dataset, batch_size=32, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=32)
    
    # Create model
    input_dim = train_features.shape[1]
    hidden_dim = config.get("model", {}).get("hidden_dim", 128)
    task_hidden_dim = config.get("model", {}).get("task_hidden_dim", 64)
    
    model = MultiTaskModel(input_dim, hidden_dim, task_hidden_dim)
    
    # Train model
    optimizer = optim.Adam(model.parameters(), lr=0.001)
    criterion = nn.MSELoss()
    
    model = train_model(model, train_loader, val_loader, optimizer, criterion)
    
    # Save model
    model_path = config.get("model", {}).get("model_path", "models/ev_charging_model.pth")
    os.makedirs(os.path.dirname(model_path), exist_ok=True)
    torch.save(model.state_dict(), model_path)
    
    return model