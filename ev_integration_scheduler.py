import torch
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime
import json
import os
import logging
from tqdm import tqdm
import random
import time
import shutil

from ev_charging_scheduler import ChargingEnvironment, ChargingScheduler
from ev_model_training import MultiTaskModel
from ev_multi_agent_system import MultiAgentSystem

class IntegratedChargingSystem:
    def __init__(self):
        self.config = None
        self.env = None
        self.scheduler = None
        self.multi_agent_system = None
        self.metrics_history = []
        
    def initialize(self, config):
        """Initialize the integrated system with configuration"""
        logger = logging.getLogger("EVApp")
        logger.info("Initializing IntegratedChargingSystem with config")
        
        try:
            self.config = config
            
            # Initialize environment
            logger.info("Initializing ChargingEnvironment")
            self.env = ChargingEnvironment(config["environment"])
            
            # Initialize scheduler
            logger.info("Initializing ChargingScheduler")
            scheduler_config = {
                "grid_id": config["environment"]["grid_id"],
                "charger_count": config["environment"]["charger_count"],
                "user_count": config["environment"]["user_count"],
                "use_multi_agent": config["scheduler"].get("use_multi_agent", False),
            }
            
            # Add optimization weights if available
            if "optimization_weights" in config["scheduler"]:
                scheduler_config["user_satisfaction_weight"] = config["scheduler"]["optimization_weights"]["user_satisfaction"]
                scheduler_config["operator_profit_weight"] = config["scheduler"]["optimization_weights"]["operator_profit"]
                scheduler_config["grid_friendliness_weight"] = config["scheduler"]["optimization_weights"]["grid_friendliness"]
            
            self.scheduler = ChargingScheduler(scheduler_config)
            
            # Initialize multi-agent system if enabled
            if config["scheduler"].get("use_multi_agent", False):
                logger.info("Initializing MultiAgentSystem")
                self.multi_agent_system = MultiAgentSystem()
                self.multi_agent_system.config = config
                
                # Configure agent weights
                agent_weights = {
                    "user": config["scheduler"]["optimization_weights"]["user_satisfaction"],
                    "profit": config["scheduler"]["optimization_weights"]["operator_profit"],
                    "grid": config["scheduler"]["optimization_weights"]["grid_friendliness"]
                }
                
                logger.info(f"Setting agent weights: {agent_weights}")
                if hasattr(self.multi_agent_system, 'coordinator'):
                    self.multi_agent_system.coordinator.set_weights(agent_weights)
                else:
                    logger.warning("MultiAgentSystem has no coordinator attribute")
                
                # Connect to scheduler
                self.scheduler.multi_agent_system = self.multi_agent_system
            
            logger.info("IntegratedChargingSystem initialization completed successfully")
            return self
        except Exception as e:
            logger.error(f"Error initializing IntegratedChargingSystem: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            raise
    
    def run_simulation(self, days):
        """
        Run a full simulation for the specified number of days
        
        Args:
            days: Number of days to simulate
            
        Returns:
            metrics_history: List of metrics at each time step
        """
        # Reset environment
        state = self.env.reset()
        
        # Calculate total steps
        time_step_minutes = self.config["environment"]["time_step_minutes"]
        total_steps = days * 24 * 60 // time_step_minutes
        
        # Run simulation
        self.metrics_history = []
        
        for step in range(total_steps):
            # Get current state
            state = self.env.get_current_state()
            
            # Make decisions
            decisions = self.scheduler.make_scheduling_decision(state)
            
            # Execute step
            rewards, next_state, done = self.env.step(decisions)
            
            # Record metrics
            self.metrics_history.append({
                "timestamp": next_state["timestamp"],
                "rewards": rewards,
                "grid_load": self.env.grid_status["grid_load"],
                "ev_load": self.env.grid_status["ev_load"],
                "renewable_ratio": self.env.grid_status["renewable_ratio"]
            })
            
            if done:
                break
        
        return self.metrics_history
    
    def get_user_metrics(self):
        """Get user-related metrics for the entire simulation"""
        if not self.env:
            return {}
        
        # Aggregate user metrics
        waiting_times = []
        charging_times = []
        traveling_times = []
        satisfaction_scores = []
        
        for user in self.env.users.values():
            # Calculate metrics from charging history
            for session in user["charging_history"]:
                waiting_times.append(session.get("waiting_time", 0))
                charging_times.append(session.get("charging_time", 0))
                traveling_times.append(session.get("traveling_time", 0))
                satisfaction_scores.append(session.get("satisfaction", 0))
        
        # Create waiting time distribution
        waiting_time_dist = {
            "0-5min": len([t for t in waiting_times if t <= 5]),
            "5-10min": len([t for t in waiting_times if 5 < t <= 10]),
            "10-15min": len([t for t in waiting_times if 10 < t <= 15]),
            "15-20min": len([t for t in waiting_times if 15 < t <= 20]),
            "20-30min": len([t for t in waiting_times if 20 < t <= 30]),
            ">30min": len([t for t in waiting_times if t > 30])
        }
        
        return {
            "waiting_time_distribution": waiting_time_dist,
            "avg_waiting_time": sum(waiting_times) / len(waiting_times) if waiting_times else 0,
            "avg_charging_time": sum(charging_times) / len(charging_times) if charging_times else 0,
            "avg_traveling_time": sum(traveling_times) / len(traveling_times) if traveling_times else 0,
            "avg_satisfaction": sum(satisfaction_scores) / len(satisfaction_scores) if satisfaction_scores else 0
        }
    
    def get_operator_metrics(self):
        """Get operator-related metrics for the entire simulation"""
        if not self.env:
            return {}
        
        # Aggregate operator metrics
        daily_revenue = {}
        daily_energy = {}
        charger_utilization = {}
        
        for charger in self.env.chargers.values():
            charger_id = charger["charger_id"]
            location = charger["location"]
            
            # Aggregate by location
            if location not in daily_revenue:
                daily_revenue[location] = 0
                daily_energy[location] = 0
                charger_utilization[location] = 0
            
            daily_revenue[location] += charger["daily_revenue"]
            daily_energy[location] += charger["daily_energy"]
            
            # Estimate utilization from history
            if hasattr(self.env, "history") and self.env.history:
                occupied_steps = sum(1 for step in self.env.history if any(
                    c["charger_id"] == charger_id and c["status"] == "occupied" 
                    for c in step.get("chargers", [])
                ))
                charger_utilization[location] += occupied_steps / len(self.env.history)
        
        # Normalize utilization
        for location in charger_utilization:
            # Count chargers in this location
            location_chargers = sum(1 for c in self.env.chargers.values() if c["location"] == location)
            if location_chargers > 0:
                charger_utilization[location] = (charger_utilization[location] / location_chargers) * 100
        
        return {
            "daily_revenue": daily_revenue,
            "daily_energy": daily_energy,
            "charger_utilization": charger_utilization,
            "total_revenue": sum(daily_revenue.values()),
            "total_energy": sum(daily_energy.values()),
            "avg_utilization": sum(charger_utilization.values()) / len(charger_utilization) if charger_utilization else 0
        }
    
    def get_grid_metrics(self):
        """Get grid-related metrics for the entire simulation"""
        if not self.env or not hasattr(self.env, "history") or not self.env.history:
            return {}
        
        # Extract hourly metrics from history
        hourly_grid_load = [0] * 24
        hourly_ev_load = [0] * 24
        hourly_counts = [0] * 24
        
        for step in self.env.history:
            timestamp = datetime.fromisoformat(step["timestamp"])
            hour = timestamp.hour
            
            hourly_grid_load[hour] += step.get("grid_load", 0)
            hourly_ev_load[hour] += step.get("ev_load", 0)
            hourly_counts[hour] += 1
        
        # Compute averages
        for hour in range(24):
            if hourly_counts[hour] > 0:
                hourly_grid_load[hour] /= hourly_counts[hour]
                hourly_ev_load[hour] /= hourly_counts[hour]
        
        # Calculate peak and valley metrics
        peak_hours = self.env.grid_status.get("peak_hours", [7, 8, 9, 10, 18, 19, 20, 21])
        valley_hours = self.env.grid_status.get("valley_hours", [0, 1, 2, 3, 4, 5])
        
        peak_load = sum(hourly_grid_load[h] for h in peak_hours) / len(peak_hours) if peak_hours else 0
        valley_load = sum(hourly_grid_load[h] for h in valley_hours) / len(valley_hours) if valley_hours else 0
        peak_ev_load = sum(hourly_ev_load[h] for h in peak_hours) / len(peak_hours) if peak_hours else 0
        valley_ev_load = sum(hourly_ev_load[h] for h in valley_hours) / len(valley_hours) if valley_hours else 0
        
        # Calculate peak-to-valley ratio
        peak_valley_ratio = peak_load / valley_load if valley_load > 0 else float('inf')
        
        # Calculate load balance index
        load_variance = np.var(hourly_grid_load)
        max_load = max(hourly_grid_load)
        load_balance_index = 1 - (load_variance / (max_load * max_load))
        
        return {
            "hourly_grid_load": hourly_grid_load,
            "hourly_ev_load": hourly_ev_load,
            "peak_load": peak_load,
            "valley_load": valley_load,
            "peak_ev_load": peak_ev_load,
            "valley_ev_load": valley_ev_load,
            "peak_valley_ratio": peak_valley_ratio,
            "load_balance_index": load_balance_index,
            "avg_renewable_ratio": sum(step.get("renewable_ratio", 0) for step in self.env.history) / len(self.env.history)
        }