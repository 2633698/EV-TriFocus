import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
import numpy as np
import pandas as pd
import json
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
from pylab import mpl
mpl.rcParams["font.sans-serif"] = ["SimHei"] # 设置显示中文字体 宋体
mpl.rcParams["axes.unicode_minus"] = False #字体更改后，会导致坐标轴中的部分字符无法正常显示，此时需要设置正常显示负号

# 设置随机种子以确保结果可复现
torch.manual_seed(42)
np.random.seed(42)

class ChargingEnvironment:
    """充电环境模拟类，包含电网状态、充电桩、用户行为等"""
    
    def __init__(self, config):
        """初始化充电环境"""
        self.config = config
        self.grid_id = config.get("grid_id", "DEFAULT001")
        self.time = datetime.now().replace(minute=0, second=0, microsecond=0)  # 整点开始
        self.chargers = {}
        self.users = {}
        self.grid_status = {}
        
        # 重置电网状态
        self.reset_grid()
        
        # 初始化充电桩
        self.init_chargers(config.get("charger_count", 20))
        
        # 初始化用户
        self.init_users(config.get("user_count", 20))
    
    def reset_grid(self):
        """重置电网状态"""
        # 初始化电网负载曲线 (24小时)
        # 尝试从配置中获取，若不存在则使用默认值
        base_load = np.array(self.config.get("grid", {}).get("base_load", [
            40, 35, 30, 28, 27, 30,  # 0-6点 (凌晨低谷)
            45, 60, 75, 80, 82, 84,  # 6-12点 (早高峰)
            80, 75, 70, 65, 70, 75,  # 12-18点 (工作时段)
            85, 90, 80, 70, 60, 50   # 18-24点 (晚高峰到夜间)
        ]))
        
        # 添加一些随机波动
        noise = np.random.normal(0, 3, 24)
        load_curve = np.clip(base_load + noise, 25, 95)
        
        current_hour = self.time.hour
        
        # 从配置中获取其他电网参数
        grid_config = self.config.get("grid", {})
        peak_hours = grid_config.get("peak_hours", [7, 8, 9, 10, 18, 19, 20, 21])
        valley_hours = grid_config.get("valley_hours", [0, 1, 2, 3, 4, 5])
        normal_price = grid_config.get("normal_price", 0.85)
        peak_price = grid_config.get("peak_price", 1.2)
        valley_price = grid_config.get("valley_price", 0.4)
        renewable_ratio_range = grid_config.get("renewable_ratio_range", [30, 60])
        
        self.grid_status = {
            "current_load": load_curve[current_hour],
            "pred_1h_load": load_curve[(current_hour + 1) % 24],
            "pred_load_curve": load_curve.tolist(),
            "renewable_ratio": np.random.uniform(renewable_ratio_range[0], renewable_ratio_range[1]),
            "peak_hours": peak_hours,
            "valley_hours": valley_hours,
            "normal_price": normal_price,
            "peak_price": peak_price,
            "valley_price": valley_price
        }
    
    def init_chargers(self, count):
        """初始化充电桩"""
        # 获取充电桩配置
        charger_config = self.config.get("chargers", {})
        charger_types_config = charger_config.get("types", {
            "fast": {"probability": 0.7, "max_power": 120},
            "slow": {"probability": 0.3, "max_power": 60}
        })
        
        # 计算充电桩类型的概率分布
        charger_types = list(charger_types_config.keys())
        type_probs = [charger_types_config[t].get("probability", 0.5) for t in charger_types]
        # 归一化概率
        type_probs = np.array(type_probs) / sum(type_probs)
        
        # 获取其他参数
        health_score_range = charger_config.get("health_score_range", [60, 99])
        solar_probability = charger_config.get("solar_probability", 0.3)
        storage_probability = charger_config.get("storage_probability", 0.2)
        
        locations = ["商业区", "住宅区", "工业园", "交通枢纽", "办公区"]
        
        for i in range(count):
            charger_id = f"CQ_{1000+i}"
            charger_type = np.random.choice(charger_types, p=type_probs)
            max_power = charger_types_config[charger_type].get("max_power", 60)
            
            # 健康状态评分 (范围从配置获取)
            health_score = np.random.normal(85, 10)
            health_score = np.clip(health_score, health_score_range[0], health_score_range[1])
            
            # 基础故障率
            failure_rate = (100 - health_score) / 500  # 健康分数越低，故障率越高
            
            self.chargers[charger_id] = {
                "charger_id": charger_id,
                "type": charger_type,
                "max_power": max_power,
                "available_power": max_power * (health_score / 100),  # 可用功率受健康状态影响
                "health_score": health_score,
                "location": np.random.choice(locations),
                "queue_length": np.random.randint(0, 5),  # 当前排队长度
                "position": {
                    "lat": np.random.uniform(30.5, 30.7),  # 模拟某城市经纬度范围
                    "lng": np.random.uniform(104.0, 104.2)
                },
                "failure_rate": failure_rate,
                "has_solar": np.random.random() < solar_probability,
                "has_storage": np.random.random() < storage_probability,
                "utilization_rate": np.random.uniform(0.5, 0.9),  # 历史利用率
                "avg_waiting_time": np.random.randint(5, 30)  # 平均等待时间(分钟)
            }
    
    def init_users(self, count):
        """初始化用户"""
        # 获取用户配置
        user_config = self.config.get("users", {})
        user_types = user_config.get("types", ["出租车", "私家车", "网约车", "物流车"])
        preference_profiles = user_config.get("profiles", {
            "紧急补电型": {"time_sensitivity": 0.9, "price_sensitivity": 0.2, "range_anxiety": 0.8},
            "经济优先型": {"time_sensitivity": 0.3, "price_sensitivity": 0.9, "range_anxiety": 0.4},
            "平衡考量型": {"time_sensitivity": 0.5, "price_sensitivity": 0.5, "range_anxiety": 0.5},
            "计划充电型": {"time_sensitivity": 0.4, "price_sensitivity": 0.7, "range_anxiety": 0.3}
        })
        
        # 获取SOC范围和最大续航里程范围
        soc_range = user_config.get("soc_range", [10, 90])
        max_range = user_config.get("max_range", [300, 500])
        
        for i in range(count):
            user_id = f"EV2024_{3000+i}"
            user_type = np.random.choice(user_types)
            profile_type = np.random.choice(list(preference_profiles.keys()))
            profile = preference_profiles[profile_type]
            
            soc = np.random.randint(soc_range[0], soc_range[1])  # 当前电量百分比
            
            # 为不同类型用户设置不同的参数
            if user_type == "出租车":
                max_wait_time = np.random.randint(5, 15)  # 出租车等待时间短
                preferred_power = np.random.randint(90, 120)  # 偏好快充
            elif user_type == "物流车":
                max_wait_time = np.random.randint(15, 30)
                preferred_power = np.random.randint(80, 120)
            else:  # 私家车和网约车
                max_wait_time = np.random.randint(20, 60)
                preferred_power = np.random.randint(60, 100)
            
            self.users[user_id] = {
                "user_id": user_id,
                "type": user_type,
                "profile": profile_type,
                "soc": soc,
                "max_wait_time": max_wait_time,
                "preferred_power": preferred_power,
                "time_sensitivity": profile["time_sensitivity"],
                "price_sensitivity": profile["price_sensitivity"],
                "range_anxiety": profile["range_anxiety"],
                "max_range": np.random.randint(max_range[0], max_range[1]),
                "current_position": {
                    "lat": np.random.uniform(30.5, 30.7),
                    "lng": np.random.uniform(104.0, 104.2)
                },
                "destination": {
                    "lat": np.random.uniform(30.5, 30.7),
                    "lng": np.random.uniform(104.0, 104.2)
                },
                "historical_sessions": np.random.randint(1, 50)  # 历史充电次数
            }
    
    def get_current_state(self):
        """获取当前环境状态"""
        current_hour = self.time.hour

        # 确定当前电价
        if current_hour in self.grid_status["peak_hours"]:
            current_price = self.grid_status["peak_price"]
        elif current_hour in self.grid_status["valley_hours"]:
            current_price = self.grid_status["valley_price"]
        else:
            current_price = self.grid_status["normal_price"]

        # 构建标准化输出
        state = {
            "timestamp": self.time.isoformat(),
            "grid_id": self.grid_id,
            "users": [],
            "chargers": [],
            "grid_status": {
                "current_load": self.grid_status["current_load"],
                "pred_1h_load": self.grid_status["pred_1h_load"],
                "renewable_ratio": self.grid_status["renewable_ratio"],
                "current_price": current_price,
                "is_peak_hour": current_hour in self.grid_status["peak_hours"],
                "is_valley_hour": current_hour in self.grid_status["valley_hours"]
            }
        }

        # 添加用户数据
        for user_id, user in self.users.items():
            state["users"].append({
                "user_id": user_id,
                "soc": user["soc"],
                "max_wait_time": user["max_wait_time"],
                "preferred_power": user["preferred_power"],
                "position": user["current_position"],
                "user_type": user["type"],
                "profile": user["profile"]
            })

        # 添加充电桩数据
        for charger_id, charger in self.chargers.items():
            state["chargers"].append({
                "charger_id": charger_id,
                "health_score": charger["health_score"],
                "available_power": charger["available_power"],
                "queue_length": charger["queue_length"],
                "position": charger["position"],
                "charger_type": charger["type"],
                "avg_waiting_time": charger["avg_waiting_time"]
            })

        return state

    
    def step(self, actions):
        """
        根据调度动作执行一个时间步长的模拟

        参数:
            actions: 调度动作，将用户分配到特定充电桩的决策

        返回:
            rewards: 根据目标函数计算的奖励值
            next_state: 执行动作后的新状态
            done: 模拟是否结束
        """
        # 更新环境状态
        self.time += timedelta(minutes=15)  # 每步模拟15分钟

        # 模拟用户能量消耗
        for user_id, user in self.users.items():
            # 假设用户消耗电量与行驶距离成正比，我们可以通过历史数据或者随机数来模拟消耗
            energy_consumed = np.random.uniform(3, 7)  # 用户每 15 分钟消耗电量范围 1%-3%
            user["soc"] = max(0, user["soc"] - energy_consumed)  # 确保电量不为负

        # 根据调度动作更新充电桩队列
        for user_id, charger_id in actions.items():
            if user_id in self.users and charger_id in self.chargers:
                # 增加充电桩排队长度
                self.chargers[charger_id]["queue_length"] += 1

                # 模拟充电过程 (简化处理)
                user = self.users[user_id]
                charger = self.chargers[charger_id]

                # 充电时间取决于SOC和充电功率
                charge_amount = min(100 - user["soc"], 30)  # 最多充30%
                user["soc"] += charge_amount

                # 更新充电桩状态
                # 简化模拟：每个用户完成充电后队列减1
                self.chargers[charger_id]["queue_length"] = max(0, charger["queue_length"] - 1)

                # 小概率发生故障
                if np.random.random() < charger["failure_rate"]:
                    self.chargers[charger_id]["health_score"] = max(60, charger["health_score"] - np.random.randint(1, 5))
                    self.chargers[charger_id]["available_power"] = charger["max_power"] * (charger["health_score"] / 100)

        # 计算奖励
        rewards = self.calculate_rewards(actions)

        # 获取新状态
        next_state = self.get_current_state()

        # 检查是否结束模拟
        done = self.time.hour == 23 and self.time.minute >= 45

        return rewards, next_state, done

    
    def calculate_rewards(self, actions):

        user_satisfaction = 0
        operator_profit = 0
        grid_friendliness = 0
        
        # 如果没有动作，返回零奖励
        if not actions:
            return {
                "user_satisfaction": 0.0,
                "operator_profit": 0.0,
                "grid_friendliness": 0.0,
                "total_reward": 0.0
            }
        current_hour = self.time.hour
        
        # 确定当前电价
        if current_hour in self.grid_status["peak_hours"]:
            current_price = self.grid_status["peak_price"]
            grid_stress_factor = 1.2  # 高峰期电网压力因子
        elif current_hour in self.grid_status["valley_hours"]:
            current_price = self.grid_status["valley_price"]
            grid_stress_factor = 0.4  # 低谷期电网压力因子
        else:
            current_price = self.grid_status["normal_price"]
            grid_stress_factor = 0.8  # 平常时段电网压力因子
        base_grid_score = 0
        renewable_factor = self.grid_status["renewable_ratio"] / 100
        for user_id, charger_id in actions.items():
            if user_id in self.users and charger_id in self.chargers:
                user = self.users[user_id]
                charger = self.chargers[charger_id]
                
                # 1. 用户满意度计算
                # 等待时间因子 (等待时间越短越满意)
                wait_time = charger["queue_length"] * 10  # 简化：每辆车等待约10分钟
                wait_time_factor = max(0, 1 - (wait_time / user["max_wait_time"]))
                
                # 充电功率匹配因子 (功率越接近用户偏好越满意)
                power_match = min(charger["available_power"], user["preferred_power"]) / user["preferred_power"]
                
                # 价格满意度 (对价格敏感的用户在低谷期更满意)
                price_satisfaction = 1 - user["price_sensitivity"] * (current_price / self.grid_status["peak_price"])
                
                # 用户综合满意度
                user_weight = 0.4 * wait_time_factor + 0.3 * power_match + 0.3 * price_satisfaction
                user_satisfaction += user_weight
                
                # 2. 运营商利润计算
                # 充电量 (kWh)
                charge_amount = min(100 - user["soc"], 30) / 100 * 60  # 假设电池容量60kWh
                
                # 充电收入
                charging_fee = charge_amount * current_price * 1.1  # 运营商加价10%
                
                # 电网采购成本
                grid_cost = charge_amount * current_price
                
                # 设备折旧成本
                depreciation_cost = charge_amount * 0.05  # 假设每kWh折旧0.05元
                
                charger_profit = charging_fee - grid_cost - depreciation_cost
                operator_profit += charger_profit
                
                # 3. 电网友好度计算
                charge_amount = min(100 - user["soc"], 30) / 100 * 60
                # 当前负载贡献
                load_contribution = charge_amount / 15  # 15分钟内的功率贡献
                
                if current_hour in self.grid_status["valley_hours"]:
                    # 低谷时段充电奖励
                    grid_score = load_contribution * 0.5  # 正向奖励
                elif current_hour in self.grid_status["peak_hours"]:
                    # 高峰时段充电惩罚，但惩罚程度降低
                    grid_score = -load_contribution * 0.5 * (self.grid_status["current_load"] / 100)
                else:
                    # 平时段适度惩罚
                    grid_score = -load_contribution * 0.1 * (self.grid_status["current_load"] / 100)



                # 新能源利用奖励 (有光伏的充电桩在白天充电更友好)
                if charger["has_solar"] and 8 <= current_hour <= 16:
                    grid_score += load_contribution * 0.5
                if self.grid_status["renewable_ratio"] > 40:  # If renewable energy is above 40%
                    renewable_bonus = load_contribution * (self.grid_status["renewable_ratio"] - 40) / 100
                    grid_score += renewable_bonus
                grid_friendliness += grid_score
                
        # 归一化处理
        if actions:
            user_satisfaction /= len(actions)
            operator_profit = min(1.0, operator_profit / (len(actions) * 10))
            grid_friendliness = max(-1.0, min(1.0, grid_friendliness / len(actions)))
        
        # 从配置中获取奖励权重
        weights = self.config.get("scheduler", {}).get("optimization_weights", {
            "user_satisfaction": 0.4, 
            "operator_profit": 0.3, 
            "grid_friendliness": 0.3
        })
        
        # 计算总奖励
        total_reward = (
            weights.get("user_satisfaction", 0.4) * user_satisfaction + 
            weights.get("operator_profit", 0.3) * operator_profit + 
            weights.get("grid_friendliness", 0.3) * (1 + grid_friendliness) / 2
        )
        
        return {
            "user_satisfaction": user_satisfaction,
            "operator_profit": operator_profit,
            "grid_friendliness": grid_friendliness,
            "total_reward": total_reward
        }


class UserModel(nn.Module):
    """用户行为模型，用于预测用户对不同充电方案的偏好"""
    
    def __init__(self, input_dim, hidden_dim=64):
        """
        初始化用户行为模型
        参数:
            input_dim: 输入特征维度
            hidden_dim: 隐藏层维度
        """
        super(UserModel, self).__init__()
        self.fc1 = nn.Linear(input_dim, hidden_dim)
        self.fc2 = nn.Linear(hidden_dim, hidden_dim)
        self.fc3 = nn.Linear(hidden_dim, 1)  # 输出用户对方案的偏好得分
    
    def forward(self, x):
        """前向传播"""
        x = F.relu(self.fc1(x))
        x = F.relu(self.fc2(x))
        x = torch.sigmoid(self.fc3(x))  # 将偏好得分压缩到0-1之间
        return x


class ChargingScheduler:
    """充电调度策略模型"""
    
    def __init__(self, config):
        """
        初始化充电调度策略
        """
        self.config = config
        self.env = ChargingEnvironment(config)
        
        # 特征维度计算
        # 用户特征: SOC + 最大等待时间 + 首选功率 + 时间敏感度 + 价格敏感度 + 里程焦虑度
        # 充电桩特征: 健康分 + 可用功率 + 队列长度 + 平均等待时间 + 位置(2维)
        # 电网特征: 当前负载 + 预测负载 + 新能源占比 + 电价 + 是否高峰/低谷
        # 交互特征: 距离 + 等待时间预估
        # 总维度: 6 + 6 + 5 + 2 = 19
        input_dim = config.get("model", {}).get("input_dim", 19)
        hidden_dim = config.get("model", {}).get("hidden_dim", 64)
        
        # 初始化用户行为模型
        self.user_model = UserModel(input_dim, hidden_dim)
        self.optimizer = optim.Adam(self.user_model.parameters(), lr=0.001)
        
        # 历史数据存储
        self.experience_buffer = []
        
        # 模型训练标志
        self.is_trained = False
    def dynamic_scheduling(self, current_hour, actions):
        """根据当前电网负荷调整调度策略"""
        grid_load = self.env.grid_status["current_load"]
        
        if current_hour in self.env.grid_status["peak_hours"]:
            # 高峰时段
            if grid_load > 80:  # 电网负荷过高，优先调度低功率充电桩
                for user_id, charger_id in actions.items():
                    charger = self.env.chargers[charger_id]
                    if charger["max_power"] > 60:
                        # 将大功率充电桩分配给低负载用户
                        actions[user_id] = self.find_low_power_charger()
        elif current_hour in self.env.grid_status["valley_hours"]:
            # 低谷时段，电网负荷低，鼓励更多充电
            self.encourage_more_charging(actions)
        return actions

    def find_low_power_charger(self):
        """查找低功率充电桩"""
        for charger_id, charger in self.env.chargers.items():
            if charger["max_power"] <= 60:
                return charger_id

    def encourage_more_charging(self, actions):
        """在低谷时段鼓励更多充电"""
        for user_id, charger_id in actions.items():
            charger = self.env.chargers[charger_id]
            if charger["queue_length"] == 0:
                # 如果充电桩没有排队，鼓励更多充电
                actions[user_id] = charger_id
        return actions
    def preprocess_features(self, user, charger, grid_status, current_time):

        # 计算用户到充电桩的距离
        user_lat, user_lng = user["position"]["lat"], user["position"]["lng"]
        charger_lat, charger_lng = charger["position"]["lat"], charger["position"]["lng"]
        
        # 简化的距离计算 (球面坐标系下的欧氏距离近似)
        distance = np.sqrt((user_lat - charger_lat)**2 + (user_lng - charger_lng)**2) * 111  # 1经纬度约111km

        wait_time = charger["queue_length"] * charger["avg_waiting_time"]
        
        # 当前是否为高峰或低谷时段
        current_hour = current_time.hour
        is_peak = 1.0 if current_hour in [7, 8, 9, 10, 18, 19, 20, 21] else 0.0
        is_valley = 1.0 if current_hour in [0, 1, 2, 3, 4, 5] else 0.0
        
        # 构建特征向量
        features = [
            # 用户特征
            user["soc"] / 100,  # 电池电量百分比 (归一化到0-1)
            user["max_wait_time"] / 60,  # 最大等待时间 (归一化到小时)
            user["preferred_power"] / 120,  # 首选功率 (归一化到最大功率)
            user.get("time_sensitivity", 0.5),
            user.get("price_sensitivity", 0.5),
            user.get("range_anxiety", 0.5),
            
            # 充电桩特征
            charger["health_score"] / 100,
            charger["available_power"] / 120,
            charger["queue_length"] / 10,  # 队列长度 (归一化到最大队列10)
            charger["avg_waiting_time"] / 30,
            1.0 if charger["charger_type"] == "fast" else 0.0,
            1.0 if charger.get("has_solar", False) else 0.0,
            
            # 电网特征
            grid_status["current_load"] / 100,
            grid_status["pred_1h_load"] / 100,
            grid_status["renewable_ratio"] / 100,
            grid_status["current_price"] / 1.2,  # 当前电价 (归一化到峰值电价)
            is_peak,
            
            # 交互特征
            min(distance, 20) / 20,  # 距离 (归一化到20km)
            min(wait_time, 120) / 120  # 等待时间预估 (归一化到2小时)
        ]
        
        return torch.tensor(features, dtype=torch.float32)
    
    def filter_feasible_chargers(self, user, all_chargers, grid_status, current_time):

        feasible_chargers = []

        current_hour = current_time.hour
    
        # 判断是否为高峰时段
        is_peak_hour = current_hour in [7, 8, 9, 10, 18, 19, 20, 21]
        is_valley_hour = current_hour in [0, 1, 2, 3, 4, 5]
        current_hour = current_time.hour
        is_solar_hour = 1 if 8 <= current_hour <= 16 else 0
        high_renewable = grid_status["renewable_ratio"] > 40
        for charger_id, charger in all_chargers.items():
            if is_valley_hour or (high_renewable and is_solar_hour):
                pass
            if is_peak_hour and grid_status["current_load"] > 80:
                # 紧急情况下才允许在高峰期高负载情况下充电
                if user["soc"] > 20 and not charger.get("has_storage", False):
                    continue
            # 在高负载但非高峰期，放宽限制
            elif grid_status["current_load"] > 90 and not charger.get("has_storage", False):
                if user["soc"] > 15:  # 真正紧急情况才允许
                    continue
            if is_solar_hour and charger.get("has_solar", False):

                pass

            # 计算距离
            user_lat, user_lng = user["position"]["lat"], user["position"]["lng"]
            charger_lat, charger_lng = charger["position"]["lat"], charger["position"]["lng"]
            distance = np.sqrt((user_lat - charger_lat)**2 + (user_lng - charger_lng)**2) * 111
            
            # 续航可达性检查
            remaining_range = user["soc"] / 100 * user.get("max_range", 400)
            if remaining_range < 1.2 * distance:  # 需要留20%的余量
                # 但如果SOC低于10%，则放宽此约束作为应急措施
                if user["soc"] >= 10:
                    continue

            # 跳过健康状态差的充电桩
            if charger["health_score"] < 70:
                continue
            # 跳过功率不匹配的充电桩
            if charger["available_power"] < user["preferred_power"] * 0.8:
                continue
            # 如果用户时间敏感且等待时间长，跳过
            expected_wait = charger["queue_length"] * charger["avg_waiting_time"]
            if user.get("time_sensitivity", 0.5) > 0.7 and expected_wait > user["max_wait_time"]:
                continue
                
            # 通过所有约束，加入可行充电桩列表
            feasible_chargers.append(charger)
        if is_solar_hour:

            feasible_chargers.sort(key=lambda c: 1 if c.get("has_solar", False) else 0, reverse=True)
        
        return feasible_chargers
    
    def score_chargers(self, user, chargers, grid_status, current_time):

        charger_scores = []
        current_hour = current_time.hour
        if grid_status["current_load"] > 85:
            if current_hour in [7, 8, 9, 10, 18, 19, 20, 21]:
                weights = {"user": 0.2, "profit": 0.2, "grid": 0.6}
            else:
                weights = {"user": 0.3, "profit": 0.2, "grid": 0.5}
        elif current_hour in [0, 1, 2, 3, 4, 5]:
            weights = {"user": 0.3, "profit": 0.3, "grid": 0.4}
        elif grid_status["renewable_ratio"] > 50:
            weights = {"user": 0.3, "profit": 0.2, "grid": 0.5}
        elif user["soc"] < 20:
            weights = {"user": 0.5, "profit": 0.3, "grid": 0.2}
        else:
            weights = {"user": 0.3, "profit": 0.3, "grid": 0.4}
        
        for charger in chargers:

            features = self.preprocess_features(user, charger, grid_status, current_time)
            
            if self.is_trained:

                with torch.no_grad():
                    features = features.unsqueeze(0)
                    # 解包返回的元组，只取第一个值（用户满意度）
                    user_satisfaction, _, _ = self.user_model(features)
                    user_preference = user_satisfaction.item()

            else:
                # 未训练时使用启发式规则

                # 计算用户到充电桩的距离
                user_lat, user_lng = user["position"]["lat"], user["position"]["lng"]
                charger_lat, charger_lng = charger["position"]["lat"], charger["position"]["lng"]
                distance = np.sqrt((user_lat - charger_lat)**2 + (user_lng - charger_lng)**2) * 111
                
                wait_time = charger["queue_length"] * charger["avg_waiting_time"]

                power_match = min(charger["available_power"], user["preferred_power"]) / user["preferred_power"]
                
                time_factor = 1 - min(wait_time / user["max_wait_time"], 1) if user["max_wait_time"] > 0 else 0
                distance_factor = 1 - min(distance / 20, 1)  # 最远考虑20km

                user_type = user.get("type", "私家车")  # 如果没有type键，默认为"私家车"
                if user_type == "出租车":
                    weights = {"time": 0.5, "distance": 0.3, "power": 0.2}
                elif user_type == "物流车":
                    weights = {"time": 0.4, "distance": 0.4, "power": 0.2}
                else:  # 私家车和网约车
                    weights = {"time": 0.3, "distance": 0.4, "power": 0.3}
                
                user_preference = (
                    weights["time"] * time_factor + 
                    weights["distance"] * distance_factor + 
                    weights["power"] * power_match
                )
            
            # 计算运营商利润因子
            current_hour = current_time.hour
            
            # 确定当前电价
            if current_hour in [7, 8, 9, 10, 18, 19, 20, 21]:
                current_price = grid_status.get("peak_price", 1.2)
            elif current_hour in [0, 1, 2, 3, 4, 5]:
                current_price = grid_status.get("valley_price", 0.4)
            else:
                current_price = grid_status.get("normal_price", 0.85)
            
            # 简化的利润计算
            # 2. 运营商利润计算
            # 充电量 (kWh)
            charge_amount = min(100 - user["soc"], 30) / 100 * 60  # 假设电池容量60kWh
            # 差异化定价策略，基于时段动态调整加价比例
            if current_hour in [7, 8, 9, 10, 18, 19, 20, 21]:
                # 低谷时段提高加价，因为电费成本低
                markup_rate = 1.25  # 低谷时段加价25%
            elif current_hour in [0, 1, 2, 3, 4, 5]:
                # 高峰时段降低加价，提高吸引力
                markup_rate = 1.05  # 高峰时段仅加价5%
            else:
                markup_rate = 1.15  # 平常时段加价15%

            # 充电收入
            charging_fee = charge_amount * current_price * markup_rate

            # 电网采购成本
            grid_cost = charge_amount * current_price

            # 设备折旧成本 - 考虑不同桩类型的折旧差异
            depreciation_rate = 0.04  # 慢充桩折旧率低

            depreciation_cost = charge_amount * depreciation_rate

            # 光伏自发电收益
            solar_benefit = 0
            if charger.get("has_solar", False) and 8 <= current_hour <= 16:
                solar_benefit = charge_amount * 0.2  # 20%的电量来自自发电，降低采购成本
            operator_profit = charging_fee - grid_cost - depreciation_cost
            
            # 设备健康影响因子 (健康状态越好，长期利润越高)
            health_factor = charger["health_score"] / 100
            
            # 运营商利润评分
            profit_score = operator_profit * health_factor / (charge_amount * 0.3)  # 归一化
            
            # 计算电网友好度因子
            grid_load = grid_status["current_load"] / 100
            
            # 高负载区域充电不友好
            grid_penalty = grid_load ** 2  # 二次惩罚项，负载越高惩罚越重
            
            # 新能源利用奖励
            renewable_bonus = 0
            if charger.get("has_solar", False) and 8 <= current_hour <= 16:
                renewable_bonus = 0.2 * grid_status["renewable_ratio"] / 100
            
            grid_score = 1 - grid_penalty + renewable_bonus
            grid_score = max(0, min(1, grid_score))  # 限制在0-1范围内

            # 计算综合评分
            if grid_load > 0.8:  # 电网高负载情况下，电网友好度权重提高
                if current_hour in [7, 8, 9, 10, 18, 19, 20, 21]:
                    weights = {"user": 0.25, "profit": 0.25, "grid": 0.5}
                else:
                    weights = {"user": 0.3, "profit": 0.3, "grid": 0.4}
            elif current_hour in [0, 1, 2, 3, 4, 5]:
                weights = {"user": 0.35, "profit": 0.4, "grid": 0.25}  # 增加利润权重，鼓励运营商引导用户低谷充电
            elif user["soc"] < 20:
                weights = {"user": 0.5, "profit": 0.3, "grid": 0.2}
            else:
                weights = {"user": 0.35, "profit": 0.35, "grid": 0.3}
            
            combined_score = (
                weights["user"] * user_preference + 
                weights["profit"] * profit_score + 
                weights["grid"] * grid_score
            )
            
            charger_scores.append({
                "charger_id": charger["charger_id"],
                "combined_score": combined_score,
                "user_score": user_preference,
                "profit_score": profit_score,
                "grid_score": grid_score,
                "distance": distance if 'distance' in locals() else None,
                "wait_time": wait_time if 'wait_time' in locals() else charger["queue_length"] * charger["avg_waiting_time"],
                "available_power": charger["available_power"]
            })
        
        # 按综合评分排序
        charger_scores.sort(key=lambda x: x["combined_score"], reverse=True)
        
        return charger_scores
    
    def make_recommendation(self, user_id, state):
        """
        为指定用户生成充电桩推荐列表
        """
        # 从状态中获取用户信息
        user_info = None
        for user in state["users"]:
            if user["user_id"] == user_id:
                user_info = user
                break
        
        if not user_info:
            return []

        chargers_dict = {charger["charger_id"]: charger for charger in state["chargers"]}
        
        # 预筛选可行充电桩
        current_time = datetime.fromisoformat(state["timestamp"])
        feasible_chargers = self.filter_feasible_chargers(
            user_info, chargers_dict, state["grid_status"], current_time
        )
        
        # 如果用户SOC低于10%，增加应急模式处理
        if user_info["soc"] < 10:

            for charger in feasible_chargers:
                user_lat, user_lng = user_info["position"]["lat"], user_info["position"]["lng"]
                charger_lat, charger_lng = charger["position"]["lat"], charger["position"]["lng"]
                distance = np.sqrt((user_lat - charger_lat)**2 + (user_lng - charger_lng)**2) * 111
                charger["distance"] = distance
            
            # 紧急情况下，先按距离排序，取最近的3个充电桩
            feasible_chargers.sort(key=lambda x: x["distance"])
            emergency_chargers = feasible_chargers[:3]
            
            # 仅为这些最近的充电桩计算详细得分
            recommendations = self.score_chargers(
                user_info, emergency_chargers, state["grid_status"], current_time
            )
        else:
            # 正常模式：为所有可行充电桩评分
            recommendations = self.score_chargers(
                user_info, feasible_chargers, state["grid_status"], current_time
            )
        
        return recommendations
    
    def collect_experience(self, user_id, recommended_chargers, selected_charger_id, satisfaction_score):
        """
        收集用户选择行为数据，用于模型训练
        """
        # 找到用户选择的充电桩在推荐列表中的排名
        selected_rank = None
        for i, rec in enumerate(recommended_chargers):
            if rec["charger_id"] == selected_charger_id:
                selected_rank = i
                break
        
        if selected_rank is not None:
            # 记录为正样本
            positive_sample = {
                "user_id": user_id,
                "charger_id": selected_charger_id,
                "rank": selected_rank,
                "satisfaction": satisfaction_score,
                "features": None  # 稍后填充特征
            }
            
            # 随机选择一个未被选中的充电桩作为负样本
            negative_samples = []
            for i, rec in enumerate(recommended_chargers):
                if i != selected_rank:
                    negative_samples.append({
                        "user_id": user_id,
                        "charger_id": rec["charger_id"],
                        "rank": i,
                        "satisfaction": 0,  # 假设未选择的满意度为0
                        "features": None  # 稍后填充特征
                    })
            
            # 如果有负样本，随机选择一个
            if negative_samples:
                negative_sample = np.random.choice(negative_samples)
                self.experience_buffer.append((positive_sample, negative_sample))
    
    def train_model(self, batch_size=32, epochs=10):
        """训练用户行为模型"""
        if len(self.experience_buffer) < batch_size:
            return  # 数据不足，暂不训练
        
        # 准备训练数据
        dataset = []
        for positive, negative in self.experience_buffer:
            if positive["features"] is not None and negative["features"] is not None:
                dataset.append((positive["features"], torch.tensor([1.0], dtype=torch.float32)))
                dataset.append((negative["features"], torch.tensor([0.0], dtype=torch.float32)))
        
        # 打乱数据
        np.random.shuffle(dataset)
        
        # 训练模型
        self.user_model.train()
        criterion = nn.BCELoss()
        
        for epoch in range(epochs):
            epoch_loss = 0
            
            for features, label in dataset:
                self.optimizer.zero_grad()
                output = self.user_model(features)
                loss = criterion(output, label)
                loss.backward()
                self.optimizer.step()
                
                epoch_loss += loss.item()
            
            print(f"Epoch {epoch+1}/{epochs}, Loss: {epoch_loss / len(dataset)}")
        
        self.is_trained = True
    
    def make_scheduling_decision(self, state):
        """
        为所有待充电用户做出调度决策
        返回:
            decisions: 调度决策，包含用户ID到充电桩ID的映射
        """
        decisions = {}
        
        # 为每个用户生成推荐
        for user in state["users"]:
            # 只为SOC较低的用户做调度
            if user["soc"] < 80:
                recommendations = self.make_recommendation(user["user_id"], state)
                
                if recommendations:
                    # 选择评分最高的充电桩
                    best_charger = recommendations[0]["charger_id"]
                    decisions[user["user_id"]] = best_charger
        
        return decisions
    
    def run_simulation(self, num_steps=96, progress_callback=None):  # 默认模拟24小时 (15分钟/步)
        """
        运行充电调度模拟
        返回:
            metrics: 模拟结果指标
        """
        metrics = {
            "user_satisfaction": [],
            "operator_profit": [],
            "grid_friendliness": [],
            "total_reward": []
        }
        
        for step in range(num_steps):
            state = self.env.get_current_state()

            decisions = self.make_scheduling_decision(state)

            rewards, next_state, done = self.env.step(decisions)

            for key in metrics:
                metrics[key].append(rewards[key])
            
            # 如果提供了进度回调，则调用
            if progress_callback:
                progress_callback(step + 1, num_steps)
            
            if done:
                break

        avg_metrics = {}
        for key in metrics:
            avg_metrics[key] = np.mean(metrics[key])
        
        return metrics, avg_metrics
    def update_load_forecast(self, current_load, hour):

        if not hasattr(self, 'historical_loads'):
            self.historical_loads = {hour: [] for hour in range(24)}
            self.load_forecast = np.zeros(24)

        self.historical_loads[hour].append(current_load)
        
        # 保留最近7天的数据
        if len(self.historical_loads[hour]) > 7:
            self.historical_loads[hour].pop(0)
        
        # 更新每小时预测
        for h in range(24):
            if self.historical_loads[h]:
                # 简单移动平均预测
                self.load_forecast[h] = np.mean(self.historical_loads[h])
    def visualize_results(self, metrics):
        """
        可视化模拟结果
        """
        # 创建时间轴 (假设每步15分钟)
        time_steps = len(metrics["user_satisfaction"])
        hours = np.arange(0, time_steps * 0.25, 0.25)
        
        plt.figure(figsize=(15, 10))
        
        # 绘制用户满意度
        plt.subplot(2, 2, 1)
        plt.plot(hours, metrics["user_satisfaction"])
        plt.title("User Satisfaction")
        plt.xlabel("Time (hours)")
        plt.ylabel("Satisfaction Score")
        plt.grid(True)
        
        # 绘制运营商利润
        plt.subplot(2, 2, 2)
        plt.plot(hours, metrics["operator_profit"])
        plt.title("Operator Profit")
        plt.xlabel("Time (hours)")
        plt.ylabel("Profit Score")
        plt.grid(True)
        
        # 绘制电网友好度
        plt.subplot(2, 2, 3)
        plt.plot(hours, metrics["grid_friendliness"])
        plt.title("Grid Friendliness")
        plt.xlabel("Time (hours)")
        plt.ylabel("Friendliness Score")
        plt.grid(True)
        
        # 绘制综合奖励
        plt.subplot(2, 2, 4)
        plt.plot(hours, metrics["total_reward"])
        plt.title("Total Reward")
        plt.xlabel("Time (hours)")
        plt.ylabel("Reward Score")
        plt.grid(True)
        
        plt.tight_layout()
        plt.savefig("charging_scheduler_results.png")
        plt.close()
        

class ChargingVisualizationDashboard:
    """
    充电调度可视化交互系统
    暂时只是静态页面，不可用
    """
    
    def __init__(self, scheduler):
        """
        初始化可视化交互系统
        
        参数:
            scheduler: 充电调度器实例
        """
        self.scheduler = scheduler
        self.env = scheduler.env
    
    def generate_user_interface(self):
        """生成用户界面HTML"""
        html = """
        <!DOCTYPE html>
        <html lang="zh-CN">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>EV充电推荐系统</title>
            <style>
                body {
                    font-family: 'Arial', sans-serif;
                    margin: 0;
                    padding: 0;
                    background-color: #f5f5f5;
                }
                .container {
                    max-width: 1200px;
                    margin: 0 auto;
                    padding: 20px;
                }
                .header {
                    background-color: #2c3e50;
                    color: white;
                    padding: 15px;
                    border-radius: 5px;
                    margin-bottom: 20px;
                }
                .card {
                    background-color: white;
                    border-radius: 5px;
                    box-shadow: 0 2px 5px rgba(0,0,0,0.1);
                    padding: 20px;
                    margin-bottom: 20px;
                }
                .recommendation {
                    display: flex;
                    margin-bottom: 15px;
                    padding: 15px;
                    border: 1px solid #e0e0e0;
                    border-radius: 5px;
                    transition: all 0.3s;
                }
                .recommendation:hover {
                    box-shadow: 0 5px 15px rgba(0,0,0,0.1);
                    transform: translateY(-2px);
                }
                .score-indicator {
                    width: 60px;
                    height: 60px;
                    border-radius: 50%;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    font-weight: bold;
                    margin-right: 20px;
                }
                .details {
                    flex-grow: 1;
                }
                .stat-group {
                    display: flex;
                    margin-top: 10px;
                }
                .stat {
                    margin-right: 20px;
                    font-size: 14px;
                }
                .emergency-switch {
                    background-color: #e74c3c;
                    color: white;
                    border: none;
                    padding: 10px 15px;
                    border-radius: 5px;
                    cursor: pointer;
                    font-weight: bold;
                    margin-bottom: 20px;
                }
                .label {
                    display: inline-block;
                    padding: 3px 8px;
                    border-radius: 3px;
                    font-size: 12px;
                    color: white;
                    margin-right: 5px;
                }
                .label-green {
                    background-color: #2ecc71;
                }
                .label-blue {
                    background-color: #3498db;
                }
                .label-orange {
                    background-color: #e67e22;
                }
                .charts {
                    display: flex;
                    flex-wrap: wrap;
                    gap: 20px;
                }
                .chart {
                    flex-basis: calc(50% - 20px);
                    min-width: 300px;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>电动汽车充电推荐系统</h1>
                    <p>基于用户偏好、运营商利润和电网友好度的智能调度</p>
                </div>
                
                <div class="card">
                    <h2>当前状态</h2>
                    <div class="stat-group">
                        <div class="stat">
                            <strong>当前时间:</strong> <span id="current-time">2024-07-20 08:15</span>
                        </div>
                        <div class="stat">
                            <strong>电池电量:</strong> <span id="battery-level">35%</span>
                        </div>
                        <div class="stat">
                            <strong>电网负载:</strong> <span id="grid-load">65%</span>
                        </div>
                        <div class="stat">
                            <strong>当前电价:</strong> <span id="current-price">0.85元/度</span>
                        </div>
                    </div>
                    
                    <button class="emergency-switch" id="emergency-mode">
                        启用紧急模式 (SOC < 20%)
                    </button>
                </div>
                
                <div class="card">
                    <h2>推荐充电站</h2>
                    <div id="recommendations">
                        <!-- 推荐列表将动态生成 -->
                        <div class="recommendation">
                            <div class="score-indicator" style="background-color: #2ecc71; color: white;">
                                98
                            </div>
                            <div class="details">
                                <h3>城东快充站 <span class="label label-green">快充</span> <span class="label label-blue">低谷电价</span></h3>
                                <div class="stat-group">
                                    <div class="stat">
                                        <strong>距离:</strong> 2.5公里
                                    </div>
                                    <div class="stat">
                                        <strong>等待时间:</strong> 约5分钟
                                    </div>
                                    <div class="stat">
                                        <strong>充电费用:</strong> 约35元
                                    </div>
                                    <div class="stat">
                                        <strong>可用功率:</strong> 120kW
                                    </div>
                                </div>
                            </div>
                        </div>
                        
                        <div class="recommendation">
                            <div class="score-indicator" style="background-color: #3498db; color: white;">
                                85
                            </div>
                            <div class="details">
                                <h3>科技园区充电站 <span class="label label-blue">低谷电价</span></h3>
                                <div class="stat-group">
                                    <div class="stat">
                                        <strong>距离:</strong> 1.2公里
                                    </div>
                                    <div class="stat">
                                        <strong>等待时间:</strong> 约15分钟
                                    </div>
                                    <div class="stat">
                                        <strong>充电费用:</strong> 约32元
                                    </div>
                                    <div class="stat">
                                        <strong>可用功率:</strong> 90kW
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
                
                <div class="card">
                    <h2>系统评估指标</h2>
                    <div class="charts">
                        <div class="chart">
                            <h3>用户满意度</h3>
                            <div id="user-satisfaction-chart"></div>
                        </div>
                        <div class="chart">
                            <h3>运营商利润</h3>
                            <div id="operator-profit-chart"></div>
                        </div>
                        <div class="chart">
                            <h3>电网友好度</h3>
                            <div id="grid-friendliness-chart"></div>
                        </div>
                        <div class="chart">
                            <h3>充电站负载热力图</h3>
                            <div id="charger-load-heatmap"></div>
                        </div>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """
        return html
    
    def generate_operator_dashboard(self):
        """生成运营商看板HTML"""
        html = """
        <!DOCTYPE html>
        <html lang="zh-CN">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>EV充电运营商管理系统</title>
            <style>
                body {
                    font-family: 'Arial', sans-serif;
                    margin: 0;
                    padding: 0;
                    background-color: #f0f2f5;
                }
                .container {
                    max-width: 1400px;
                    margin: 0 auto;
                    padding: 20px;
                }
                .header {
                    background-color: #001529;
                    color: white;
                    padding: 15px;
                    border-radius: 5px;
                    margin-bottom: 20px;
                }
                .dashboard {
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
                    gap: 20px;
                    margin-bottom: 20px;
                }
                .card {
                    background-color: white;
                    border-radius: 5px;
                    box-shadow: 0 2px 5px rgba(0,0,0,0.1);
                    padding: 20px;
                }
                .card h2 {
                    margin-top: 0;
                    border-bottom: 1px solid #eee;
                    padding-bottom: 10px;
                }
                .stat-value {
                    font-size: 36px;
                    font-weight: bold;
                    margin: 10px 0;
                }
                .stat-label {
                    color: #666;
                }
                .chart {
                    height: 300px;
                }
                .profit-settings {
                    display: flex;
                    flex-direction: column;
                    gap: 15px;
                }
                .slider-group {
                    margin-bottom: 10px;
                }
                .slider-label {
                    display: block;
                    margin-bottom: 5px;
                }
                .slider {
                    width: 100%;
                }
                .slider-value {
                    display: inline-block;
                    width: 50px;
                    text-align: right;
                }
                .apply-button {
                    background-color: #1890ff;
                    color: white;
                    border: none;
                    padding: 10px 15px;
                    border-radius: 5px;
                    cursor: pointer;
                    font-weight: bold;
                    align-self: flex-start;
                }
                table {
                    width: 100%;
                    border-collapse: collapse;
                }
                th, td {
                    padding: 12px 15px;
                    text-align: left;
                }
                th {
                    background-color: #f5f5f5;
                    font-weight: bold;
                }
                tr {
                    border-bottom: 1px solid #ddd;
                }
                tr:hover {
                    background-color: #f9f9f9;
                }
                .status-indicator {
                    display: inline-block;
                    width: 10px;
                    height: 10px;
                    border-radius: 50%;
                    margin-right: 5px;
                }
                .status-healthy {
                    background-color: #52c41a;
                }
                .status-warning {
                    background-color: #faad14;
                }
                .status-critical {
                    background-color: #f5222d;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>充电运营管理系统</h1>
                    <p>实时监控与调度控制平台</p>
                </div>
                
                <div class="dashboard">
                    <div class="card">
                        <h2>运营概览</h2>
                        <div>
                            <div class="stat-label">今日总充电次数</div>
                            <div class="stat-value">347</div>
                        </div>
                        <div>
                            <div class="stat-label">总充电时长</div>
                            <div class="stat-value">728<span style="font-size: 20px;">小时</span></div>
                        </div>
                    </div>
                    
                    <div class="card">
                        <h2>收益统计</h2>
                        <div>
                            <div class="stat-label">今日收入</div>
                            <div class="stat-value">¥12,845</div>
                        </div>
                        <div>
                            <div class="stat-label">利润率</div>
                            <div class="stat-value">27.8%</div>
                        </div>
                    </div>
                    
                    <div class="card">
                        <h2>充电桩状态</h2>
                        <div>
                            <div class="stat-label">在线充电桩</div>
                            <div class="stat-value">42<span style="font-size: 20px;">/45</span></div>
                        </div>
                        <div>
                            <div class="stat-label">平均利用率</div>
                            <div class="stat-value">68.4%</div>
                        </div>
                    </div>
                    
                    <div class="card">
                        <h2>用户体验</h2>
                        <div>
                            <div class="stat-label">平均等待时间</div>
                            <div class="stat-value">12<span style="font-size: 20px;">分钟</span></div>
                        </div>
                        <div>
                            <div class="stat-label">用户满意度</div>
                            <div class="stat-value">4.7<span style="font-size: 20px;">/5.0</span></div>
                        </div>
                    </div>
                </div>
                
                <div class="card">
                    <h2>利润与电网负载平衡</h2>
                    <div class="chart" id="profit-load-chart"></div>
                </div>
                
                <div style="display: grid; grid-template-columns: 2fr 1fr; gap: 20px; margin-top: 20px;">
                    <div class="card">
                        <h2>充电桩状态监控</h2>
                        <table>
                            <thead>
                                <tr>
                                    <th>充电桩ID</th>
                                    <th>位置</th>
                                    <th>类型</th>
                                    <th>当前负载</th>
                                    <th>健康状态</th>
                                    <th>队列长度</th>
                                </tr>
                            </thead>
                            <tbody>
                                <tr>
                                    <td>CQ_1001</td>
                                    <td>城东商圈</td>
                                    <td>快充</td>
                                    <td>78%</td>
                                    <td><span class="status-indicator status-healthy"></span>良好 (92%)</td>
                                    <td>2</td>
                                </tr>
                                <tr>
                                    <td>CQ_1002</td>
                                    <td>西区工业园</td>
                                    <td>快充</td>
                                    <td>45%</td>
                                    <td><span class="status-indicator status-healthy"></span>良好 (89%)</td>
                                    <td>0</td>
                                </tr>
                                <tr>
                                    <td>CQ_1003</td>
                                    <td>南湖科技园</td>
                                    <td>慢充</td>
                                    <td>95%</td>
                                    <td><span class="status-indicator status-warning"></span>注意 (74%)</td>
                                    <td>3</td>
                                </tr>
                                <tr>
                                    <td>CQ_1004</td>
                                    <td>北城商务区</td>
                                    <td>快充</td>
                                    <td>62%</td>
                                    <td><span class="status-indicator status-healthy"></span>良好 (86%)</td>
                                    <td>1</td>
                                </tr>
                                <tr>
                                    <td>CQ_1005</td>
                                    <td>中央车站</td>
                                    <td>快充</td>
                                    <td>90%</td>
                                    <td><span class="status-indicator status-critical"></span>异常 (65%)</td>
                                    <td>4</td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                    
                    <div class="card">
                        <h2>价格策略模拟</h2>
                        <div class="profit-settings">
                            <div class="slider-group">
                                <label class="slider-label">峰时电价加价率 (%)</label>
                                <input type="range" min="5" max="30" value="12" class="slider" id="peak-price-markup">
                                <span class="slider-value">12%</span>
                            </div>
                            
                            <div class="slider-group">
                                <label class="slider-label">谷时电价折扣率 (%)</label>
                                <input type="range" min="0" max="40" value="20" class="slider" id="valley-price-discount">
                                <span class="slider-value">20%</span>
                            </div>
                            
                            <div class="slider-group">
                                <label class="slider-label">充电服务费 (元/度)</label>
                                <input type="range" min="0" max="1" step="0.1" value="0.3" class="slider" id="service-fee">
                                <span class="slider-value">0.3</span>
                            </div>
                            
                            <button class="apply-button">应用并模拟结果</button>
                            
                            <div style="margin-top: 20px;">
                                <div class="stat-label">预计日利润变化</div>
                                <div class="stat-value" style="color: #52c41a;">+8.5%</div>
                                
                                <div class="stat-label">预计用户满意度变化</div>
                                <div class="stat-value" style="color: #f5222d;">-2.1%</div>
                            </div>
                        </div>
                    </div>
                </div>
                
                <div class="card" style="margin-top: 20px;">
                    <h2>电网协同监控</h2>
                    <div class="chart" id="grid-load-chart"></div>
                </div>
            </div>
        </body>
        </html>
        """
        return html
    
    def create_evaluation_report(self, simulation_results):
        """
        创建评价指标体系报告
        
        参数:
            simulation_results: 模拟结果
        
        返回:
            report: 评价报告
        """
        # 解包模拟结果
        metrics, avg_metrics = simulation_results
        
        # 构建报告Markdown
        report = f"""
        # 电动汽车有序充电调度策略评价报告
        
        ## 综合评价指标
        
        | 指标名称 | 平均值 | 最高值 | 最低值 | 标准差 |
        |---------|-------|-------|-------|-------|
        | 用户满意度 | {np.mean(metrics['user_satisfaction']):.4f} | {np.max(metrics['user_satisfaction']):.4f} | {np.min(metrics['user_satisfaction']):.4f} | {np.std(metrics['user_satisfaction']):.4f} |
        | 运营商利润 | {np.mean(metrics['operator_profit']):.4f} | {np.max(metrics['operator_profit']):.4f} | {np.min(metrics['operator_profit']):.4f} | {np.std(metrics['operator_profit']):.4f} |
        | 电网友好度 | {np.mean(metrics['grid_friendliness']):.4f} | {np.max(metrics['grid_friendliness']):.4f} | {np.min(metrics['grid_friendliness']):.4f} | {np.std(metrics['grid_friendliness']):.4f} |
        | 综合奖励 | {np.mean(metrics['total_reward']):.4f} | {np.max(metrics['total_reward']):.4f} | {np.min(metrics['total_reward']):.4f} | {np.std(metrics['total_reward']):.4f} |
        
        ## 详细评价分析
        
        ### 1. 用户体验分析
        
        - **平均用户满意度**: {np.mean(metrics['user_satisfaction']):.4f}
        - **用户满意度波动性**: {np.std(metrics['user_satisfaction']):.4f}
        - **用户体验最佳时段**: {np.argmax(metrics['user_satisfaction']) * 0.25:.2f}小时
        - **用户体验最差时段**: {np.argmin(metrics['user_satisfaction']) * 0.25:.2f}小时
        
        ### 2. 运营商效益分析
        
        - **平均运营利润**: {np.mean(metrics['operator_profit']):.4f}
        - **利润波动性**: {np.std(metrics['operator_profit']):.4f}
        - **利润最高时段**: {np.argmax(metrics['operator_profit']) * 0.25:.2f}小时
        - **利润最低时段**: {np.argmin(metrics['operator_profit']) * 0.25:.2f}小时
        
        ### 3. 电网友好度分析
        
        - **平均电网友好度**: {np.mean(metrics['grid_friendliness']):.4f}
        - **电网友好度波动性**: {np.std(metrics['grid_friendliness']):.4f}
        - **电网最友好时段**: {np.argmax(metrics['grid_friendliness']) * 0.25:.2f}小时
        - **电网最不友好时段**: {np.argmin(metrics['grid_friendliness']) * 0.25:.2f}小时
        
        ## 各指标时序变化图
        
        *用户满意度、运营商利润、电网友好度和综合奖励的时间变化图见附件。*
        
        ## 优化建议
        
        1. **提高用户满意度的策略**:
           - 针对{np.argmin(metrics['user_satisfaction']) * 0.25:.2f}小时左右的满意度低谷，可增加充电桩动态调度频率
           - 高峰期可实施更激进的预约充电激励机制
        
        2. **提高运营商利润的策略**:
           - 优化{np.argmin(metrics['operator_profit']) * 0.25:.2f}小时的充电桩使用率
           - 调整峰谷电价差，引导用户向利润更高的时段转移
        
        3. **提高电网友好度的策略**:
           - 在{np.argmin(metrics['grid_friendliness']) * 0.25:.2f}小时实施更严格的有序充电控制
           - 增加光伏+储能一体化充电站比例，缓解电网压力
        
        ## 综合结论
        
        本充电调度策略在用户满意度、运营商利润和电网友好度三方面取得了良好的平衡，综合奖励平均值为{np.mean(metrics['total_reward']):.4f}。策略在不同时段的表现存在一定波动，特别是在高峰时段的电网友好度方面有提升空间。建议进一步优化高峰时段的调度算法，并探索更多元化的用户激励机制。
        """
        
        return report


def main():
    config = {
        "grid_id": "0258",
        "charger_count": 15,
        "user_count": 30,
    }

    scheduler = ChargingScheduler(config)

    simulation_results = scheduler.run_simulation(num_steps=96)  # 模拟24小时

    scheduler.visualize_results(simulation_results[0])

    dashboard = ChargingVisualizationDashboard(scheduler)
    evaluation_report = dashboard.create_evaluation_report(simulation_results)
    
    print("模拟完成，评价报告已生成。")
    
    return evaluation_report


if __name__ == "__main__":
    main()
