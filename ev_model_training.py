import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from tqdm import tqdm

class MultiTaskModel(nn.Module):
    """
    多任务学习模型，同时优化用户满意度、运营商利润和电网友好度
    """
    def __init__(self, input_dim, hidden_dim=128, task_hidden_dim=64):
        """
        初始化多任务学习模型
        
        参数:
            input_dim: 输入特征维度
            hidden_dim: 共享层隐藏单元数
            task_hidden_dim: 任务特定层隐藏单元数
        """
        super(MultiTaskModel, self).__init__()
        
        # 共享特征提取层
        self.shared_layers = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.BatchNorm1d(hidden_dim),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(hidden_dim, hidden_dim),
            nn.BatchNorm1d(hidden_dim),
            nn.ReLU(),
            nn.Dropout(0.3)
        )
        
        # 用户满意度预测任务
        self.user_satisfaction_head = nn.Sequential(
            nn.Linear(hidden_dim, task_hidden_dim),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(task_hidden_dim, 1),
            nn.Sigmoid()  # 用户满意度在0-1之间
        )
        
        # 运营商利润预测任务
        self.operator_profit_head = nn.Sequential(
            nn.Linear(hidden_dim, task_hidden_dim),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(task_hidden_dim, 1)
        )
        
        # 电网友好度预测任务
        self.grid_friendliness_head = nn.Sequential(
            nn.Linear(hidden_dim, task_hidden_dim),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(task_hidden_dim, 1),
            nn.Tanh()  # 电网友好度在-1到1之间
        )
        
    def forward(self, x):
        """前向传播"""
        shared_features = self.shared_layers(x)
        
        user_satisfaction = self.user_satisfaction_head(shared_features)
        operator_profit = self.operator_profit_head(shared_features)
        grid_friendliness = self.grid_friendliness_head(shared_features)
        
        return user_satisfaction, operator_profit, grid_friendliness


class PolicyGradientAgent(nn.Module):
    """基于策略梯度的强化学习智能体"""
    
    def __init__(self, state_dim, action_dim, hidden_dim=128):
        """
        初始化策略梯度智能体
        
        参数:
            state_dim: 状态空间维度
            action_dim: 动作空间维度
            hidden_dim: 隐藏层维度
        """
        super(PolicyGradientAgent, self).__init__()
        
        self.policy_network = nn.Sequential(
            nn.Linear(state_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, action_dim),
            nn.Softmax(dim=-1)
        )
        
        self.value_network = nn.Sequential(
            nn.Linear(state_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, 1)
        )
        
        self.optimizer = optim.Adam(self.parameters(), lr=0.001)
        self.saved_log_probs = []
        self.saved_values = []
        self.rewards = []
        
    def forward(self, state):
        """前向传播"""
        action_probs = self.policy_network(state)
        state_value = self.value_network(state)
        
        return action_probs, state_value
        
    def select_action(self, state):
        """
        根据状态选择动作
        
        参数:
            state: 当前状态
            
        返回:
            action: 选择的动作
            log_prob: 动作的对数概率
            value: 状态值估计
        """
        state = torch.FloatTensor(state)
        action_probs, state_value = self(state)
        
        # 从动作概率分布中采样
        m = torch.distributions.Categorical(action_probs)
        action = m.sample()
        
        # 保存动作的对数概率和状态值，用于后续更新
        self.saved_log_probs.append(m.log_prob(action))
        self.saved_values.append(state_value)
        
        return action.item(), m.log_prob(action), state_value
        
    def update_policy(self, gamma=0.99):
        """
        使用累积奖励更新策略网络
        
        参数:
            gamma: 折扣因子
        """
        # 计算折扣累积奖励
        R = 0
        returns = []
        
        for r in self.rewards[::-1]:
            R = r + gamma * R
            returns.insert(0, R)
            
        returns = torch.tensor(returns)
        
        # 标准化返回值以减少方差
        if len(returns) > 1:
            returns = (returns - returns.mean()) / (returns.std() + 1e-8)
        
        # 计算策略损失和值函数损失
        policy_loss = []
        value_loss = []
        
        for log_prob, value, R in zip(self.saved_log_probs, self.saved_values, returns):
            advantage = R - value.item()
            policy_loss.append(-log_prob * advantage)  # 策略梯度
            value_loss.append(F.smooth_l1_loss(value, torch.tensor([R])))  # 值函数损失
            
        # 总损失
        loss = torch.stack(policy_loss).sum() + torch.stack(value_loss).sum()
        
        # 更新网络参数
        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()
        
        # 清空缓存的奖励和动作概率
        self.saved_log_probs = []
        self.saved_values = []
        self.rewards = []
        
        return loss.item()


class DataGenerator:
    """模拟数据生成器，用于生成训练数据"""
    
    def __init__(self, num_users=500, num_chargers=50, num_samples=10000):
        """
        初始化数据生成器
        
        参数:
            num_users: 模拟用户数量
            num_chargers: 模拟充电桩数量
            num_samples: 生成的样本数量
        """
        self.num_users = num_users
        self.num_chargers = num_chargers
        self.num_samples = num_samples
        
        # 生成用户行为模型参数
        self.user_types = ["出租车", "私家车", "网约车", "物流车"]
        self.user_profiles = {
            "紧急补电型": {"time_sensitivity": 0.9, "price_sensitivity": 0.2, "range_anxiety": 0.8},
            "经济优先型": {"time_sensitivity": 0.3, "price_sensitivity": 0.9, "range_anxiety": 0.4},
            "平衡考量型": {"time_sensitivity": 0.5, "price_sensitivity": 0.5, "range_anxiety": 0.5},
            "计划充电型": {"time_sensitivity": 0.4, "price_sensitivity": 0.7, "range_anxiety": 0.3}
        }
        
        # 生成充电桩属性
        self.charger_types = ["fast", "slow"]
        self.locations = ["商业区", "住宅区", "工业园", "交通枢纽", "办公区"]
        
        # 初始化用户和充电桩数据
        self.users = self._generate_users()
        self.chargers = self._generate_chargers()
        
    def _generate_users(self):
        """生成用户数据"""
        users = []
        
        for i in range(self.num_users):
            user_type = np.random.choice(self.user_types)
            profile_type = np.random.choice(list(self.user_profiles.keys()))
            profile = self.user_profiles[profile_type]
            
            user = {
                "user_id": f"EV2024_{3000+i}",
                "type": user_type,
                "profile": profile_type,
                "time_sensitivity": profile["time_sensitivity"],
                "price_sensitivity": profile["price_sensitivity"],
                "range_anxiety": profile["range_anxiety"],
                "max_range": np.random.randint(300, 500)  # 车辆最大续航里程
            }
            
            users.append(user)
            
        return users
    
    def _generate_chargers(self):
        """生成充电桩数据"""
        chargers = []
        
        for i in range(self.num_chargers):
            charger_type = np.random.choice(self.charger_types, p=[0.7, 0.3])  # 70%为快充
            max_power = 120 if charger_type == "fast" else 60  # 快充120kW，慢充60kW
            
            # 健康状态评分 (0-100)
            health_score = np.random.normal(85, 10)
            health_score = np.clip(health_score, 60, 99)
            
            charger = {
                "charger_id": f"CQ_{1000+i}",
                "type": charger_type,
                "max_power": max_power,
                "health_score": health_score,
                "location": np.random.choice(self.locations),
                "has_solar": np.random.random() < 0.3,  # 30%的充电桩接入光伏
                "has_storage": np.random.random() < 0.2  # 20%的充电桩接入储能
            }
            
            chargers.append(charger)
            
        return chargers
    
    def generate_samples(self):
        """生成训练样本"""
        X = []  # 特征
        y_satisfaction = []  # 用户满意度标签
        y_profit = []  # 运营商利润标签
        y_grid = []  # 电网友好度标签
        
        for _ in range(self.num_samples):
            # 随机选择用户和充电桩
            user = np.random.choice(self.users)
            charger = np.random.choice(self.chargers)
            
            # 随机生成状态特征
            soc = np.random.randint(10, 90)  # 当前电量百分比
            hour = np.random.randint(0, 24)  # 当前小时
            grid_load = np.random.uniform(0.3, 0.9)  # 电网负载率
            queue_length = np.random.randint(0, 5)  # 排队长度
            distance = np.random.uniform(0.5, 15)  # 距离(km)
            
            # 确定当前是否高峰/低谷时段
            is_peak = 1.0 if hour in [7, 8, 9, 10, 18, 19, 20, 21] else 0.0
            is_valley = 1.0 if hour in [0, 1, 2, 3, 4, 5] else 0.0
            
            # 确定当前电价
            if is_peak:
                current_price = 1.2  # 高峰电价
            elif is_valley:
                current_price = 0.4  # 低谷电价
            else:
                current_price = 0.85  # 平段电价
            
            # 计算等待时间 (分钟)
            avg_wait_time = np.random.randint(5, 15)
            wait_time = queue_length * avg_wait_time
            
            # 构建特征向量
            features = [
                # 用户特征
                soc / 100,  # 电池电量百分比 (归一化到0-1)
                user["time_sensitivity"],  # 时间敏感度
                user["price_sensitivity"],  # 价格敏感度
                user["range_anxiety"],  # 里程焦虑度
                1.0 if user["type"] == "出租车" else 0.0,  # 是否为出租车
                1.0 if user["type"] == "物流车" else 0.0,  # 是否为物流车
                
                # 充电桩特征
                charger["health_score"] / 100,  # 健康分数
                charger["max_power"] / 120,  # 最大功率 (归一化)
                1.0 if charger["type"] == "fast" else 0.0,  # 是否为快充
                1.0 if charger["has_solar"] else 0.0,  # 是否有光伏
                1.0 if charger["has_storage"] else 0.0,  # 是否有储能
                
                # 环境特征
                hour / 24,  # 一天中的小时 (归一化)
                grid_load,  # 电网负载
                is_peak,  # 是否高峰时段
                is_valley,  # 是否低谷时段
                current_price / 1.2,  # 当前电价 (归一化到峰值电价)
                
                # 交互特征
                queue_length / 10,  # 队列长度 (归一化)
                min(wait_time, 60) / 60,  # 等待时间 (归一化到1小时)
                min(distance, 20) / 20,  # 距离 (归一化到20km)
            ]
            
            X.append(features)
            
            # 生成标签
            # 1. 用户满意度计算
            wait_time_factor = max(0, 1 - (wait_time / 60))  # 等待时间越短越满意
            power_match = 1.0 if (charger["type"] == "fast" and user["time_sensitivity"] > 0.7) else 0.8
            price_satisfaction = 1 - user["price_sensitivity"] * (current_price / 1.2)
            
            user_satisfaction = 0.4 * wait_time_factor + 0.3 * power_match + 0.3 * price_satisfaction
            user_satisfaction += np.random.normal(0, 0.05)  # 添加一些随机噪声
            user_satisfaction = np.clip(user_satisfaction, 0, 1)
            
            # 2. 运营商利润计算
            charge_amount = min(100 - soc, 30) / 100 * 60  # 假设电池容量60kWh
            charging_fee = charge_amount * current_price * 1.1  # 运营商加价10%
            grid_cost = charge_amount * current_price
            depreciation_cost = charge_amount * 0.05 * (1 - charger["health_score"]/100)  # 设备折旧
            
            operator_profit = charging_fee - grid_cost - depreciation_cost
            operator_profit += np.random.normal(0, 0.5)  # 添加随机波动
            
            # 3. 电网友好度计算
            grid_penalty = grid_load ** 2  # 高负载惩罚
            
            renewable_bonus = 0
            if charger["has_solar"] and 8 <= hour <= 16:  # 白天光伏发电
                renewable_bonus = 0.3
            
            grid_friendliness = 1 - grid_penalty + renewable_bonus
            
            # 高峰时段充电不友好，低谷时段充电友好
            if is_peak:
                grid_friendliness -= 0.3
            elif is_valley:
                grid_friendliness += 0.3
            
            grid_friendliness = np.clip(grid_friendliness, -1, 1)
            
            y_satisfaction.append(user_satisfaction)
            y_profit.append(operator_profit)
            y_grid.append(grid_friendliness)
            
        return np.array(X), np.array(y_satisfaction), np.array(y_profit), np.array(y_grid)


def train_model(X_train, y_train_satisfaction, y_train_profit, y_train_grid, 
                X_val, y_val_satisfaction, y_val_profit, y_val_grid, 
                input_dim, batch_size=32, epochs=50):
    """
    训练多任务模型
    
    参数:
        X_train: 训练特征
        y_train_*: 训练标签
        X_val: 验证特征
        y_val_*: 验证标签
        input_dim: 输入特征维度
        batch_size: 批次大小
        epochs: 训练轮数
    
    返回:
        model: 训练好的模型
        history: 训练历史记录
    """
    # 创建模型
    model = MultiTaskModel(input_dim=input_dim)
    optimizer = optim.Adam(model.parameters(), lr=0.001)
    
    # 损失函数
    satisfaction_criterion = nn.MSELoss()
    profit_criterion = nn.MSELoss()
    grid_criterion = nn.MSELoss()
    
    # 训练历史记录
    history = {
        'train_loss': [],
        'val_loss': [],
        'satisfaction_loss': [],
        'profit_loss': [],
        'grid_loss': []
    }
    
    # 转换为PyTorch张量
    X_train = torch.FloatTensor(X_train)
    y_train_satisfaction = torch.FloatTensor(y_train_satisfaction).view(-1, 1)
    y_train_profit = torch.FloatTensor(y_train_profit).view(-1, 1)
    y_train_grid = torch.FloatTensor(y_train_grid).view(-1, 1)
    
    X_val = torch.FloatTensor(X_val)
    y_val_satisfaction = torch.FloatTensor(y_val_satisfaction).view(-1, 1)
    y_val_profit = torch.FloatTensor(y_val_profit).view(-1, 1)
    y_val_grid = torch.FloatTensor(y_val_grid).view(-1, 1)
    
    # 训练循环
    n_samples = X_train.shape[0]
    n_batches = (n_samples + batch_size - 1) // batch_size
    
    for epoch in range(epochs):
        model.train()
        epoch_loss = 0
        epoch_satisfaction_loss = 0
        epoch_profit_loss = 0
        epoch_grid_loss = 0
        
        # 随机打乱训练数据
        indices = torch.randperm(n_samples)
        X_train = X_train[indices]
        y_train_satisfaction = y_train_satisfaction[indices]
        y_train_profit = y_train_profit[indices]
        y_train_grid = y_train_grid[indices]
        
        # 批次训练
        for i in range(n_batches):
            start_idx = i * batch_size
            end_idx = min((i + 1) * batch_size, n_samples)
            
            X_batch = X_train[start_idx:end_idx]
            y_batch_satisfaction = y_train_satisfaction[start_idx:end_idx]
            y_batch_profit = y_train_profit[start_idx:end_idx]
            y_batch_grid = y_train_grid[start_idx:end_idx]
            
            # 前向传播
            pred_satisfaction, pred_profit, pred_grid = model(X_batch)
            
            # 计算各任务损失
            loss_satisfaction = satisfaction_criterion(pred_satisfaction, y_batch_satisfaction)
            loss_profit = profit_criterion(pred_profit, y_batch_profit)
            loss_grid = grid_criterion(pred_grid, y_batch_grid)
            
            # 多任务加权损失 (可以根据任务重要性调整权重)
            loss = 0.4 * loss_satisfaction + 0.3 * loss_profit + 0.3 * loss_grid
            
            # 反向传播和优化
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            
            # 记录损失
            epoch_loss += loss.item() * (end_idx - start_idx)
            epoch_satisfaction_loss += loss_satisfaction.item() * (end_idx - start_idx)
            epoch_profit_loss += loss_profit.item() * (end_idx - start_idx)
            epoch_grid_loss += loss_grid.item() * (end_idx - start_idx)
        
        # 计算平均损失
        epoch_loss /= n_samples
        epoch_satisfaction_loss /= n_samples
        epoch_profit_loss /= n_samples
        epoch_grid_loss /= n_samples
        
        # 验证
        model.eval()
        with torch.no_grad():
            pred_val_satisfaction, pred_val_profit, pred_val_grid = model(X_val)
            
            val_loss_satisfaction = satisfaction_criterion(pred_val_satisfaction, y_val_satisfaction)
            val_loss_profit = profit_criterion(pred_val_profit, y_val_profit)
            val_loss_grid = grid_criterion(pred_val_grid, y_val_grid)
            
            val_loss = 0.4 * val_loss_satisfaction + 0.3 * val_loss_profit + 0.3 * val_loss_grid
        
        # 记录训练历史
        history['train_loss'].append(epoch_loss)
        history['val_loss'].append(val_loss.item())
        history['satisfaction_loss'].append(epoch_satisfaction_loss)
        history['profit_loss'].append(epoch_profit_loss)
        history['grid_loss'].append(epoch_grid_loss)
        
        # 打印训练进度
        if (epoch + 1) % 5 == 0:
            print(f"Epoch {epoch+1}/{epochs}, Train Loss: {epoch_loss:.4f}, Val Loss: {val_loss.item():.4f}")
            print(f"  Satisfaction Loss: {epoch_satisfaction_loss:.4f}, Profit Loss: {epoch_profit_loss:.4f}, Grid Loss: {epoch_grid_loss:.4f}")
    
    return model, history


def evaluate_model(model, X_test, y_test_satisfaction, y_test_profit, y_test_grid):
    """
    评估模型性能
    
    参数:
        model: 训练好的模型
        X_test: 测试特征
        y_test_*: 测试标签
    
    返回:
        metrics: 评估指标
    """
    model.eval()
    
    # 转换为PyTorch张量
    X_test = torch.FloatTensor(X_test)
    y_test_satisfaction = torch.FloatTensor(y_test_satisfaction).view(-1, 1)
    y_test_profit = torch.FloatTensor(y_test_profit).view(-1, 1)
    y_test_grid = torch.FloatTensor(y_test_grid).view(-1, 1)
    
    # 预测
    with torch.no_grad():
        pred_satisfaction, pred_profit, pred_grid = model(X_test)
        
        # 计算均方误差
        mse_satisfaction = F.mse_loss(pred_satisfaction, y_test_satisfaction).item()
        mse_profit = F.mse_loss(pred_profit, y_test_profit).item()
        mse_grid = F.mse_loss(pred_grid, y_test_grid).item()
        
        # 计算平均绝对误差
        mae_satisfaction = F.l1_loss(pred_satisfaction, y_test_satisfaction).item()
        mae_profit = F.l1_loss(pred_profit, y_test_profit).item()
        mae_grid = F.l1_loss(pred_grid, y_test_grid).item()
        
        # 转换为NumPy数组用于计算R2分数
        pred_satisfaction_np = pred_satisfaction.numpy().flatten()
        y_test_satisfaction_np = y_test_satisfaction.numpy().flatten()
        
        pred_profit_np = pred_profit.numpy().flatten()
        y_test_profit_np = y_test_profit.numpy().flatten()
        
        pred_grid_np = pred_grid.numpy().flatten()
        y_test_grid_np = y_test_grid.numpy().flatten()
        
        # 计算R2分数
        from sklearn.metrics import r2_score
        r2_satisfaction = r2_score(y_test_satisfaction_np, pred_satisfaction_np)
        r2_profit = r2_score(y_test_profit_np, pred_profit_np)
        r2_grid = r2_score(y_test_grid_np, pred_grid_np)
    
    # 返回评估指标
    metrics = {
        'mse': {
            'satisfaction': mse_satisfaction,
            'profit': mse_profit,
            'grid': mse_grid
        },
        'mae': {
            'satisfaction': mae_satisfaction,
            'profit': mae_profit,
            'grid': mae_grid
        },
        'r2': {
            'satisfaction': r2_satisfaction,
            'profit': r2_profit,
            'grid': r2_grid
        }
    }
    
    return metrics


def plot_learning_curves(history):
    """
    绘制学习曲线
    
    参数:
        history: 训练历史记录
    """
    epochs = range(1, len(history['train_loss']) + 1)
    
    plt.figure(figsize=(15, 10))
    
    # 绘制总体损失
    plt.subplot(2, 2, 1)
    plt.plot(epochs, history['train_loss'], 'b-', label='Training Loss')
    plt.plot(epochs, history['val_loss'], 'r-', label='Validation Loss')
    plt.title('Training and Validation Loss')
    plt.xlabel('Epochs')
    plt.ylabel('Loss')
    plt.legend()
    plt.grid(True)
    
    # 绘制用户满意度损失
    plt.subplot(2, 2, 2)
    plt.plot(epochs, history['satisfaction_loss'], 'g-', label='Satisfaction Loss')
    plt.title('User Satisfaction Loss')
    plt.xlabel('Epochs')
    plt.ylabel('Loss')
    plt.legend()
    plt.grid(True)
    
    # 绘制运营商利润损失
    plt.subplot(2, 2, 3)
    plt.plot(epochs, history['profit_loss'], 'm-', label='Profit Loss')
    plt.title('Operator Profit Loss')
    plt.xlabel('Epochs')
    plt.ylabel('Loss')
    plt.legend()
    plt.grid(True)
    
    # 绘制电网友好度损失
    plt.subplot(2, 2, 4)
    plt.plot(epochs, history['grid_loss'], 'c-', label='Grid Friendliness Loss')
    plt.title('Grid Friendliness Loss')
    plt.xlabel('Epochs')
    plt.ylabel('Loss')
    plt.legend()
    plt.grid(True)
    
    plt.tight_layout()
    plt.savefig("learning_curves.png")
    plt.close()


def train_policy_gradient_agent(env, agent, num_episodes=1000, gamma=0.99):
    """
    训练策略梯度智能体
    
    参数:
        env: 充电环境
        agent: 策略梯度智能体
        num_episodes: 训练轮数
        gamma: 折扣因子
    
    返回:
        episode_rewards: 每个回合的累积奖励
    """
    episode_rewards = []
    
    for episode in tqdm(range(num_episodes)):
        # 重置环境
        state = env.reset()
        state = np.array(state, dtype=np.float32)
        
        episode_reward = 0
        done = False
        
        while not done:
            # 选择动作
            action, log_prob, value = agent.select_action(state)
            
            # 执行动作并获取奖励
            next_state, reward, done, _ = env.step(action)
            next_state = np.array(next_state, dtype=np.float32)
            
            # 记录奖励
            agent.rewards.append(reward)
            episode_reward += reward
            
            # 更新状态
            state = next_state
            
            # 如果回合结束，更新策略
            if done:
                agent.update_policy(gamma)
        
        # 记录回合奖励
        episode_rewards.append(episode_reward)
        
        # 打印训练进度
        if (episode + 1) % 50 == 0:
            avg_reward = np.mean(episode_rewards[-50:])
            print(f"Episode {episode+1}, Avg Reward: {avg_reward:.2f}")
    
    return episode_rewards


def main():
    """训练与评估流程"""
    # 生成模拟数据
    print("生成训练数据...")
    data_gen = DataGenerator(num_samples=50000)
    X, y_satisfaction, y_profit, y_grid = data_gen.generate_samples()
    
    # 划分训练集、验证集和测试集
    X_train, X_temp, y_train_satisfaction, y_temp_satisfaction = train_test_split(
        X, y_satisfaction, test_size=0.3, random_state=42
    )
    
    X_val, X_test, y_val_satisfaction, y_test_satisfaction = train_test_split(
        X_temp, y_temp_satisfaction, test_size=0.5, random_state=42
    )
    
    _, _, y_train_profit, y_temp_profit = train_test_split(
        X, y_profit, test_size=0.3, random_state=42
    )
    
    _, _, y_val_profit, y_test_profit = train_test_split(
        X_temp, y_temp_profit, test_size=0.5, random_state=42
    )
    
    _, _, y_train_grid, y_temp_grid = train_test_split(
        X, y_grid, test_size=0.3, random_state=42
    )
    
    _, _, y_val_grid, y_test_grid = train_test_split(
        X_temp, y_temp_grid, test_size=0.5, random_state=42
    )
    
    # 训练多任务模型
    print("训练多任务模型...")
    input_dim = X.shape[1]
    model, history = train_model(
        X_train, y_train_satisfaction, y_train_profit, y_train_grid,
        X_val, y_val_satisfaction, y_val_profit, y_val_grid,
        input_dim, batch_size=64, epochs=50
    )
    
    # 绘制学习曲线
    print("绘制学习曲线...")
    plot_learning_curves(history)
    
    # 评估模型
    print("评估模型性能...")
    metrics = evaluate_model(
        model, X_test, y_test_satisfaction, y_test_profit, y_test_grid
    )
    
    print("模型评估指标:")
    print(f"用户满意度 - MSE: {metrics['mse']['satisfaction']:.4f}, MAE: {metrics['mae']['satisfaction']:.4f}, R²: {metrics['r2']['satisfaction']:.4f}")
    print(f"运营商利润 - MSE: {metrics['mse']['profit']:.4f}, MAE: {metrics['mae']['profit']:.4f}, R²: {metrics['r2']['profit']:.4f}")
    print(f"电网友好度 - MSE: {metrics['mse']['grid']:.4f}, MAE: {metrics['mae']['grid']:.4f}, R²: {metrics['r2']['grid']:.4f}")
    
    # 保存模型
    torch.save(model.state_dict(), "ev_charging_model.pth")
    print("模型已保存为 'ev_charging_model.pth'")
    
    return model, history, metrics


if __name__ == "__main__":
    main()
