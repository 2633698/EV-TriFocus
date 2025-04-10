import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import random
import math
from typing import Dict, List, Tuple, Any
import logging
# Import necessary systems
from ev_multi_agent_system import MultiAgentSystem
# Assuming MARLSystem is in marl_components, adjust if necessary
from marl_components import MARLSystem

logger = logging.getLogger(__name__)

class ChargingEnvironment:
    def __init__(self, config):
        """
        Initialize the charging environment with the given configuration
        
        Args:
            config: Dictionary containing configuration parameters
        """
        # 存储配置以便其他方法访问
        self.config = config
        
        # 基本环境参数
        self.grid_id = config.get("grid_id", "DEFAULT001")
        
        # 站点和充电桩配置
        self.station_count = config.get("station_count", 20)
        self.chargers_per_station = config.get("chargers_per_station", 20)
        self.charger_count = self.station_count * self.chargers_per_station
        
        # 用户和模拟配置
        self.user_count = config.get("user_count", 1000)
        self.simulation_days = config.get("simulation_days", 7)
        self.time_step_minutes = config.get("time_step_minutes", 15)
        
        # 地区数量
        self.region_count = config.get("region_count", 5)
        
        # 地图边界
        map_bounds_config = config.get("map_bounds", {
            "min_lat": 30.5, # Default if not provided
            "max_lat": 31.0,
            "min_lng": 114.0,
            "max_lng": 114.5
        })
        # Convert to internal naming convention
        self.map_bounds = {
            "lat_min": map_bounds_config.get("min_lat", 30.5),
            "lat_max": map_bounds_config.get("max_lat", 31.0),
            "lng_min": map_bounds_config.get("min_lng", 114.0),
            "lng_max": map_bounds_config.get("max_lng", 114.5)
        }
        
        # 当前模拟时间
        self.current_time = datetime.now().replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        
        # 初始化用户、充电桩和电网状态
        logger.info(f"Initializing environment with {self.user_count} users and {self.charger_count} chargers across {self.station_count} stations")
        self.users = self._initialize_users()
        self.chargers = self._initialize_chargers()
        self.grid_status = self._initialize_grid()
        self.history = []
        
        # 启用无序充电基准对比分析
        self.uncoordinated_baseline = config.get("enable_uncoordinated_baseline", True)
        logger.info(f"Uncoordinated charging baseline: {'Enabled' if self.uncoordinated_baseline else 'Disabled'}")
        
        # 统计信息
        self.metrics = {
            "user_satisfaction": [],
            "operator_profit": [],
            "grid_friendliness": [],
            "total_reward": [],
            "charging_sessions": 0,
            "average_waiting_time": 0,
            "average_charging_time": 0
        }
        
        logger.info("Environment initialization completed successfully")
        
    def _initialize_users(self):
        """
        初始化模拟用户
        """
        user_count = self.config.get("user_count", 1000)
        map_bounds = self.config.get("map_bounds", {
            "min_lat": 30.5,
            "max_lat": 31.0,
            "min_lng": 114.0,
            "max_lng": 114.5
        })
        
        logging.info(f"初始化 {user_count} 个用户")
        
        if user_count <= 0:
            logging.warning("用户数量无效，设置为默认值 1000")
            user_count = 1000
        
        # 定义SOC分布
        soc_ranges = [
            (0.15, (10, 30)),   # 15%的用户SOC在10-30%之间
            (0.35, (30, 60)),   # 35%的用户SOC在30-60%之间
            (0.35, (60, 80)),   # 35%的用户SOC在60-80%之间
            (0.15, (80, 95))    # 15%的用户SOC在80-95%之间
        ]
        
        # 预定义一些热点区域（商业区、居民区等）
        # 根据地图边界和区域数量自动生成热点
        hotspots = []
        
        # 确保有一个中心商业区
        center_lat = (map_bounds["min_lat"] + map_bounds["max_lat"]) / 2
        center_lng = (map_bounds["min_lng"] + map_bounds["max_lng"]) / 2
        hotspots.append({
            "lat": center_lat, 
            "lng": center_lng, 
            "desc": "CBD", 
            "weight": 0.2
        })
        
        # 根据区域动态创建热点位置
        region_count = self.region_count
        remaining_weight = 0.8  # 中心占0.2，其余区域分配0.8
        
        # 创建更多细分区域，提高分散度
        actual_regions = region_count * 2  # 增加区域数量
        
        # 计算网格布局以均匀分布热点
        grid_rows = int(math.sqrt(actual_regions))
        grid_cols = (actual_regions + grid_rows - 1) // grid_rows  # 向上取整
        
        lat_step = (map_bounds["max_lat"] - map_bounds["min_lat"]) / grid_rows
        lng_step = (map_bounds["max_lng"] - map_bounds["min_lng"]) / grid_cols
        
        for i in range(actual_regions - 1):  # 除去中心区域
            # 计算网格位置
            row = i // grid_cols
            col = i % grid_cols
            
            # 在网格单元内随机分布，但避免与边界和中心过近
            base_lat = map_bounds["min_lat"] + lat_step * row
            base_lng = map_bounds["min_lng"] + lng_step * col
            
            # 在网格单元内随机分布，但避免靠得太近
            # 随机位置范围是网格单元的60%-90%，避免过度集中
            lat_offset = random.uniform(0.6, 0.9) * lat_step
            lng_offset = random.uniform(0.6, 0.9) * lng_step
            
            lat = base_lat + lat_offset
            lng = base_lng + lng_offset
            
            # 确保不会与已有热点太近（最小距离）
            min_distance = 0.01  # 约1km
            too_close = False
            for spot in hotspots:
                dist = math.sqrt((lat - spot["lat"])**2 + (lng - spot["lng"])**2)
                if dist < min_distance:
                    too_close = True
                    break
            
            # 如果太近，尝试新位置
            if too_close:
                lat = base_lat + random.uniform(0.1, 0.9) * lat_step
                lng = base_lng + random.uniform(0.1, 0.9) * lng_step
            
            # 区域描述和权重
            descriptions = ["科技园区", "购物中心", "居民区", "工业园区", "休闲区", "大学城", "商圈", 
                           "医院", "学校", "办公区", "体育场", "公园", "火车站", "汽车站"]
            desc = descriptions[i % len(descriptions)]
            if i < len(descriptions):
                desc += str(i + 1)
                
            # 分配较小权重以避免用户高度集中
            weight = remaining_weight / (actual_regions * 1.5)
            
            hotspots.append({
                "lat": lat,
                "lng": lng,
                "desc": desc,
                "weight": weight
            })
        
        # 计算热点总权重
        total_weight = sum(spot["weight"] for spot in hotspots)
        # 归一化权重
        for i in range(len(hotspots)):
            hotspots[i]["weight"] = hotspots[i]["weight"] / total_weight
        
        # 车型及其参数
        vehicle_types = {
            "sedan": {"battery_capacity": 60, "max_range": 400},
            "suv": {"battery_capacity": 85, "max_range": 480},
            "compact": {"battery_capacity": 40, "max_range": 350},
            "luxury": {"battery_capacity": 100, "max_range": 550},
            "truck": {"battery_capacity": 120, "max_range": 500}
        }
        
        users = {}
        
        for i in range(user_count):
            user_id = f"user_{i+1}"
            
            # 随机车型
            vehicle_type = random.choice(list(vehicle_types.keys()))
            
            # 随机用户类型
            user_types = ["private", "taxi", "ride_hailing", "logistics"]
            user_type = random.choice(user_types)
            
            # 随机SOC分布
            rand_val = random.random()
            cumulative_prob = 0
            soc_range = (10, 90)
            for prob, range_val in soc_ranges:
                cumulative_prob += prob
                if rand_val <= cumulative_prob:
                    soc_range = range_val
                    break
            
            soc = random.uniform(soc_range[0], soc_range[1])
            
            # 根据用户类型和SOC决定用户偏好
            # 紧急用户：时间敏感度高，价格敏感度低
            # 经济用户：价格敏感度高，时间敏感度低
            # 灵活用户：两者平衡
            # 焦虑用户：里程焦虑高，寻找方便的充电点
            user_profiles = ["urgent", "economic", "flexible", "anxious"]
            
            # 给不同用户类型分配合理的概率分布
            profile_probs = []
            if user_type == "taxi":
                profile_probs = [0.5, 0.1, 0.3, 0.1]  # 出租车更可能是紧急用户
            elif user_type == "ride_hailing":
                profile_probs = [0.4, 0.2, 0.3, 0.1]  # 网约车类似出租车
            elif user_type == "logistics":
                profile_probs = [0.3, 0.4, 0.2, 0.1]  # 物流车辆更注重经济性
            else:  # private
                profile_probs = [0.2, 0.3, 0.3, 0.2]  # 私家车分布更均匀
            
            # SOC低的用户更可能是紧急用户
            if soc < 30:
                profile_probs[0] += 0.2  # 增加紧急概率
                profile_probs = [p / sum(profile_probs) for p in profile_probs]  # 重新归一化
            
            user_profile = random.choices(user_profiles, weights=profile_probs)[0]
            
            # 电池容量和最大行驶里程
            battery_capacity = vehicle_types[vehicle_type]["battery_capacity"]
            max_range = vehicle_types[vehicle_type]["max_range"]
            current_range = max_range * (soc / 100)
            
            # 决定用户位置 - 基于热点区域
            if random.random() < 0.7:  # 降低热点区域概率从0.8到0.7
                # 基于权重选择热点
                hotspot = random.choices(hotspots, weights=[spot["weight"] for spot in hotspots])[0]
                
                # 在热点周围随机分布（更大范围高斯分布）
                radius = random.gauss(0, 0.03)  # 增加标准差到0.03°，约3公里
                angle = random.uniform(0, 2 * math.pi)
                lat = hotspot["lat"] + radius * math.cos(angle)
                lng = hotspot["lng"] + radius * math.sin(angle)
                
                # 增加一些额外随机性，防止重叠
                lat += random.uniform(-0.005, 0.005)
                lng += random.uniform(-0.005, 0.005)
                
                # 确保在地图边界内
                lat = min(max(lat, map_bounds["min_lat"]), map_bounds["max_lat"])
                lng = min(max(lng, map_bounds["min_lng"]), map_bounds["max_lng"])
            else:
                # 完全随机分布在地图范围内，增加分散度
                lat = random.uniform(map_bounds["min_lat"], map_bounds["max_lat"])
                lng = random.uniform(map_bounds["min_lng"], map_bounds["max_lng"])
                
                # 防止随机位置与热点完全重叠
                for spot in hotspots:
                    dist = math.sqrt((lat - spot["lat"])**2 + (lng - spot["lng"])**2)
                    if dist < 0.005:  # 约500m
                        # 如果太近，稍微偏移
                        lat += random.uniform(-0.01, 0.01)
                        lng += random.uniform(-0.01, 0.01)
                        break
                
                # 再次确保在地图边界内
                lat = min(max(lat, map_bounds["min_lat"]), map_bounds["max_lat"])
                lng = min(max(lng, map_bounds["min_lng"]), map_bounds["max_lng"])
            
            # 决定用户状态 - SOC低的用户更可能处于traveling状态
            status_probs = {}
            if soc < 30:
                status_probs = {"idle": 0.3, "traveling": 0.7}
            elif soc < 60:
                status_probs = {"idle": 0.6, "traveling": 0.4}
            else:
                status_probs = {"idle": 0.8, "traveling": 0.2}
                
            status = random.choices(list(status_probs.keys()), weights=list(status_probs.values()))[0]
            
            # 根据车辆类型和用户类型分配合理的行驶速度
            speed_range = (30, 60)  # 默认速度范围 km/h
            
            if user_type == "taxi":
                speed_range = (35, 70)  # 出租车速度范围
            elif user_type == "ride_hailing":
                speed_range = (35, 65)  # 网约车速度范围
            elif user_type == "logistics":
                speed_range = (30, 55)  # 物流车速度范围
            elif vehicle_type == "luxury":
                speed_range = (40, 75)  # 豪华车速度范围
            elif vehicle_type == "compact":
                speed_range = (35, 65)  # 紧凑型车速度范围
                
            travel_speed = random.uniform(speed_range[0], speed_range[1])
            
            # 创建用户
            users[user_id] = {
                "user_id": user_id,  # 确保包含用户ID
                "vehicle_type": vehicle_type,
                "user_type": user_type,
                "user_profile": user_profile,
                "battery_capacity": battery_capacity,
                "soc": soc,  # 电池电量百分比
                "max_range": max_range,  # 满电最大行驶里程
                "current_range": current_range,  # 当前剩余续航里程
                "current_position": {"lat": lat, "lng": lng},
                "status": status,
                "target_charger": None,
                "charging_history": [],
                "travel_speed": travel_speed,  # 行驶速度 km/h
                "route": [],  # 当前路线
                "waypoints": [],  # 路径点
                "destination": None,  # 目的地
                "time_to_destination": None,  # 到达目的地的预计时间（分钟）
                "traveled_distance": 0,  # 已行驶距离
                # 添加驾驶风格以支持更精确的能耗计算
                "driving_style": random.choices(
                    ["normal", "aggressive", "eco"],
                    weights=[0.6, 0.25, 0.15]  # 大多数人使用普通驾驶方式，少数人激进或经济模式
                )[0],
            }
            
            # 根据用户类型和偏好设置时间和价格敏感度
            if user_profile == "urgent":
                users[user_id]["time_sensitivity"] = random.uniform(0.7, 0.9)
                users[user_id]["price_sensitivity"] = random.uniform(0.1, 0.3)
            elif user_profile == "economic":
                users[user_id]["time_sensitivity"] = random.uniform(0.2, 0.4)
                users[user_id]["price_sensitivity"] = random.uniform(0.7, 0.9)
            elif user_profile == "flexible":
                users[user_id]["time_sensitivity"] = random.uniform(0.4, 0.6)
                users[user_id]["price_sensitivity"] = random.uniform(0.4, 0.6)
            elif user_profile == "anxious":
                users[user_id]["time_sensitivity"] = random.uniform(0.5, 0.7)
                users[user_id]["price_sensitivity"] = random.uniform(0.3, 0.5)
                users[user_id]["range_anxiety"] = random.uniform(0.6, 0.9)
            
        logging.info(f"用户初始化完成，包含 {len(users)} 个用户")
        return users
    
    def _initialize_chargers(self):
        """Initialize charging stations with different types and locations"""
        chargers = {}
        charger_count = self.config.get("charger_count", 10)
        chargers_per_station = self.config.get("chargers_per_station", 4)
        station_count = self.config.get("station_count", 5)
        failure_rate = self.config.get("charger_failure_rate", 0.0)

        # Get map bounds for random positioning
        map_bounds = self.config.get("map_bounds", {
            "min_lat": 30.0,
            "max_lat": 30.3,
            "min_lng": 116.0,
            "max_lng": 116.3
        })
        
        # Define locations and their coordinates
        # Either use pre-defined locations or generate random ones based on map_bounds
        locations = []
        for i in range(station_count):
            locations.append({
                "name": f"充电站{i+1}",
                "lat": random.uniform(map_bounds.get("min_lat", 30.0), map_bounds.get("max_lat", 30.3)),
                "lng": random.uniform(map_bounds.get("min_lng", 116.0), map_bounds.get("max_lng", 116.3))
            })

        # 生成充电桩，分配类型和功率
        current_id = 1
        
        # 超级快充的比例
        superfast_ratio = 0.1  # 10%的充电桩是超级快充
        fast_ratio = 0.4  # 40%的充电桩是快充
        # 剩余50%是普通充电桩
        
        for location in locations:
            # 为每个位置生成多个充电桩
            for i in range(chargers_per_station):
                charger_id = f"charger_{current_id}"
                
                # 决定充电桩类型
                rand_val = random.random()
                
                if rand_val < superfast_ratio:
                    charger_type = "superfast"
                    charger_power = random.uniform(250, 400)  # 超级快充 250-400kW
                    price_multiplier = 1.5  # 超级快充费用更高
                elif rand_val < superfast_ratio + fast_ratio:
                    charger_type = "fast"
                    charger_power = random.uniform(60, 120)  # 快充 60-120kW
                    price_multiplier = 1.2  # 快充费用较高
                else:
                    charger_type = "normal"
                    charger_power = random.uniform(7, 20)  # 慢充 7-20kW
                    price_multiplier = 1.0  # 标准费用
                
                # 判断充电桩是否故障
                is_failure = random.random() < failure_rate
                    
                chargers[charger_id] = {
                        "charger_id": charger_id,
                    "location": location["name"],
                        "type": charger_type,
                    "max_power": charger_power,
                    "position": {
                        "lat": location["lat"] + random.uniform(-0.005, 0.005),  # 略微偏移于位置中心
                        "lng": location["lng"] + random.uniform(-0.005, 0.005)
                    },
                    "status": "failure" if is_failure else "available",
                        "current_user": None,
                        "queue": [],
                    "queue_capacity": 10,
                    "daily_revenue": 0.0,
                    "daily_energy": 0.0,
                    "utilization_rate": 0.0,
                    "price_multiplier": price_multiplier,
                    "region": f"Region_{random.randint(1, self.config.get('region_count', 4))}"  # 分配一个区域ID
                }
                current_id += 1
        
        # 确保总数正确（可能因为locations*chargers_per_station大于charger_count）
        if current_id - 1 > charger_count:
            # 删除多余的充电桩
            excess = current_id - 1 - charger_count
            keys_to_remove = list(chargers.keys())[-excess:]
            for key in keys_to_remove:
                del chargers[key]
        
        # 日志摘要
        superfast_count = sum(1 for c in chargers.values() if c["type"] == "superfast") 
        fast_count = sum(1 for c in chargers.values() if c["type"] == "fast")
        normal_count = sum(1 for c in chargers.values() if c["type"] == "normal")
        failure_count = sum(1 for c in chargers.values() if c["status"] == "failure")
        
        logger.info(f"已初始化 {len(chargers)} 个充电桩: {superfast_count} 超级快充, "
                   f"{fast_count} 快充, {normal_count} 慢充, {failure_count} 故障")
        
        return chargers
    
    def _initialize_grid(self):
        """Initialize grid status"""
        # 从配置文件中读取基础负载
        grid_config = self.config.get("grid", {})
        # 大幅提高基础负载值 (kW)
        base_load = grid_config.get("base_load", [
            16000, 14000, 12000, 11000, 10000, 11000, 18000, 24000, 30000, 32000, 32800, 33600,
            32000, 30000, 28000, 26000, 28000, 30000, 34000, 36000, 32000, 28000, 24000, 20000
        ])  # 峰值约36000kW

        # 从配置文件中读取峰谷时段 (保持不变)
        peak_hours = grid_config.get("peak_hours", [7, 8, 9, 10, 18, 19, 20, 21])
        valley_hours = grid_config.get("valley_hours", [0, 1, 2, 3, 4, 5])
        
        # 可再生能源生成 - 保持现有调整值 (kW)
        solar_generation = grid_config.get("solar_generation", [
            0, 0, 0, 0, 0, 0, 1000, 2000, 3600, 5000, 6000, 6400,
            6000, 5600, 5000, 4000, 2000, 600, 0, 0, 0, 0, 0, 0
        ])
        wind_generation = grid_config.get("wind_generation", [
            2400, 2800, 3000, 2600, 2000, 2400, 3000, 3400, 2600, 2000, 2400, 2600,
            3000, 3400, 3200, 2800, 3200, 3600, 4000, 3600, 3200, 3000, 2600, 2800
        ])
        
        # 电价设置
        normal_price = grid_config.get("normal_price", 0.85)  # yuan/kWh
        peak_price = grid_config.get("peak_price", 1.2)  # yuan/kWh
        valley_price = grid_config.get("valley_price", 0.4)  # yuan/kWh
        
        # 根据当前小时计算电价
        current_hour = self.current_time.hour
        if current_hour in peak_hours:
            current_price = peak_price
        elif current_hour in valley_hours:
            current_price = valley_price
        else:
            current_price = normal_price
        
        # 确保base_load是一个包含24个值的列表
        if not isinstance(base_load, list) or len(base_load) != 24:
            logger.warning(f"Invalid base_load in config: {base_load}. Using default values.")
            # 更新默认值以匹配提高后的负载
            base_load = [
                16000, 14000, 12000, 11000, 10000, 11000, 18000, 24000, 30000, 32000, 32800, 33600,
                32000, 30000, 28000, 26000, 28000, 30000, 34000, 36000, 32000, 28000, 24000, 20000
            ]
        
        # 初始化电网状态
        grid_status = {
            "base_load": base_load,  # 当前基础负载（kW）
            "current_load": base_load[self.current_time.hour],  # 总负载（kW）
            "peak_hours": peak_hours,
            "valley_hours": valley_hours,
            "solar_generation": solar_generation,
            "wind_generation": wind_generation,
            "normal_price": normal_price,
            "peak_price": peak_price,
            "valley_price": valley_price,
            "current_price": current_price,
            "load_balance_index": 0.85,
            "renewable_ratio": (solar_generation[self.current_time.hour] + 
                               wind_generation[self.current_time.hour]) / base_load[self.current_time.hour] * 100,
            "ev_load": 0,
            "grid_load": base_load[self.current_time.hour]
        }
        
        logger.info(f"Grid initialized with base_load: {base_load}")
        return grid_status
    
    def get_current_state(self):
        """Return the current state of the environment"""
        # Convert users and chargers dicts to lists for output
        users_list = list(self.users.values())
        chargers_list = list(self.chargers.values())
        
        # Get current hour and load
        hour = self.current_time.hour
        
        # 构建基本状态
        state = {
            "timestamp": self.current_time.isoformat(),
            "users": users_list,
            "chargers": chargers_list,
            "grid_status": self.grid_status.copy()  # 复制当前电网状态
        }
        
        # 添加历史数据
        if hasattr(self, 'history') and self.history:
            # 创建历史记录的副本，避免修改原始数据
            history_data = []
            for h in self.history:
                history_entry = {
                    "timestamp": h["timestamp"],
                    "grid_status": {
                        "current_load": h["grid_status"].get("current_load", 0),
                        "grid_load": h["grid_status"].get("grid_load", 0),
                        "ev_load": h["grid_status"].get("ev_load", 0),
                        "renewable_ratio": h["grid_status"].get("renewable_ratio", 0)
                    }
                }
                history_data.append(history_entry)
            state["history"] = history_data
        else:
            state["history"] = []
        
        return state
    
    def _get_current_price(self, hour):
        """Get electricity price based on the hour"""
        if self.grid_status and "peak_hours" in self.grid_status:
            if hour in self.grid_status["peak_hours"]:
                return self.grid_status["peak_price"]
            elif hour in self.grid_status["valley_hours"]:
                return self.grid_status["valley_price"]
            else:
                return self.grid_status["normal_price"]
        else:
            # 如果grid_status尚未初始化，使用默认值
            peak_hours = [7, 8, 9, 10, 18, 19, 20, 21]
            valley_hours = [0, 1, 2, 3, 4, 5]
            if hour in peak_hours:
                return 1.2  # peak_price
            elif hour in valley_hours:
                return 0.4  # valley_price
            else:
                return 0.85  # normal_price
    
    def step(self, decisions):
        """
        Execute one time step with the given charging decisions
        
        Args:
            decisions: Dictionary mapping user_id to charger_id for charging decisions
            
        Returns:
            rewards: Dictionary of various reward metrics
            next_state: The next state after executing the decisions
            done: Boolean indicating if the simulation is complete
        """
        # 记录需要充电但未分配充电桩的用户，用于诊断
        users_needing_charge = [user_id for user_id, user in self.users.items() 
                               if user.get("needs_charge_decision", False) and 
                               user_id not in decisions and
                               user.get("status") not in ["charging", "waiting"]]
        
        if users_needing_charge:
            logger.debug(f"{len(users_needing_charge)} users need charging but weren't assigned: {users_needing_charge[:5]}...")
        
        # 计算本次分配了多少用户
        assigned_count = len(decisions)
        logger.info(f"Processing {assigned_count} charging assignments in this step")
        
        # 先处理调度器决策（分配用户到充电桩）
        for user_id, charger_id in decisions.items():
            if user_id in self.users and charger_id in self.chargers:
                user = self.users[user_id]
                charger = self.chargers[charger_id]
                
                # 如果用户尚未分配充电桩，则分配
                if user["status"] != "charging" and user["status"] != "waiting":
                    # 为此用户规划路线到充电桩
                    success = self._plan_route_to_charger(user_id, charger_id)
                    
                    if success:
                        # 更新用户状态为traveling（还没到充电桩）
                        user["status"] = "traveling"
                        user["target_charger"] = charger_id
                        user["last_destination_type"] = "charger"  # 明确标记目的地类型
                        logger.debug(f"User {user_id} was assigned to charger {charger_id} and is now traveling there.")
                    else:
                        logger.warning(f"Failed to plan route for user {user_id} to charger {charger_id}")
                
                # 如果用户已经到达充电桩，加入队列
                elif user["status"] == "traveling" and user["target_charger"] == charger_id and self._has_reached_charger(user_id, charger_id):
                    # 添加用户到充电桩队列
                    charger["queue"].append(user_id)
                    
                    # 更新用户状态
                    user["status"] = "waiting"
                    # 记录初始SOC
                    user["initial_soc"] = user.get("soc", 0)
                    logger.debug(f"User {user_id} reached charger {charger_id} and joined queue. Initial SOC: {user['initial_soc']:.1f}%")
        
        # 模拟用户行为（包括移动、SOC变化等）
        self._simulate_user_behavior()
        
        # 处理充电站充电过程
        self._process_charging()
        
        # 更新电网状态
        self._update_grid_state()
        
        # 前进时间
        self.current_time += timedelta(minutes=self.time_step_minutes)
        
        # 检查模拟是否结束
        done = (self.current_time.date() - datetime.now().date()).days >= self.simulation_days
        
        # 计算此步骤的奖励
        rewards = self._calculate_rewards()
        
        # 保存状态到历史记录
        self._save_current_state()
        
        # 获取下一状态
        next_state = self.get_current_state()
        
        return rewards, next_state, done
    
    def _plan_route_to_charger(self, user_id, charger_id):
        """规划用户到充电桩的路线"""
        if user_id not in self.users or charger_id not in self.chargers:
            return False
            
        user = self.users[user_id]
        charger = self.chargers[charger_id]
        
        # 获取起点和终点
        start_pos = user["current_position"]
        end_pos = charger["position"]
        
        # 清空之前的路径
        user["route"] = []
        user["waypoints"] = []
        
        # 设置目的地
        user["destination"] = end_pos.copy()
        
        # 简单路径规划：直线+随机偏移
        # 在实际应用中，这里应该使用真实的路网数据和路径规划算法
        
        # 计算起点到终点的向量
        dx = end_pos["lng"] - start_pos["lng"]
        dy = end_pos["lat"] - start_pos["lat"]
        
        # 路径长度（直线距离）
        distance = math.sqrt(dx*dx + dy*dy) * 111  # 乘以111转换为公里
        
        # 生成2-4个路径点
        num_points = random.randint(2, 4)
        waypoints = []
        
        # 沿路径添加一些随机偏移的路径点
        for i in range(1, num_points):
            # 在直线路径上的位置（0-1之间）
            t = i / num_points
            
            # 基础位置（沿直线）
            point_lng = start_pos["lng"] + t * dx
            point_lat = start_pos["lat"] + t * dy
            
            # 添加一些随机偏移（垂直于直线方向）
            # 这会使路径看起来更自然，不是完全直线
            perpendicular_dx = -dy
            perpendicular_dy = dx
            
            # 标准化垂直向量
            perp_len = math.sqrt(perpendicular_dx*perpendicular_dx + perpendicular_dy*perpendicular_dy)
            if perp_len > 0:
                perpendicular_dx /= perp_len
                perpendicular_dy /= perp_len
            
            # 随机偏移（最大距离为直线距离的10%）
            offset_magnitude = random.uniform(-0.1, 0.1) * distance / 111  # 转回坐标单位
            
            # 应用偏移
            point_lng += perpendicular_dx * offset_magnitude
            point_lat += perpendicular_dy * offset_magnitude
            
            waypoints.append({
                "lat": point_lat,
                "lng": point_lng
            })
        
        # 设置路径点
        user["waypoints"] = waypoints
        
        # 创建完整路径（起点 + 路径点 + 终点）
        full_route = [start_pos.copy()]
        full_route.extend(waypoints)
        full_route.append(end_pos.copy())
        user["route"] = full_route
        
        # 计算总行程距离
        total_distance = 0
        for i in range(1, len(full_route)):
            p1 = full_route[i-1]
            p2 = full_route[i]
            segment_dx = p2["lng"] - p1["lng"]
            segment_dy = p2["lat"] - p1["lat"]
            segment_dist = math.sqrt(segment_dx*segment_dx + segment_dy*segment_dy) * 111  # 转为公里
            total_distance += segment_dist
        
        # 计算预计到达时间（假设平均速度为用户travel_speed，单位km/h）
        travel_time_hours = total_distance / user["travel_speed"]
        travel_time_minutes = travel_time_hours * 60
        
        # 设置到达时间
        user["time_to_destination"] = travel_time_minutes
        user["traveled_distance"] = 0
        
        return True
    
    def _plan_route_to_destination(self, user_id, destination):
        """规划用户到任意目的地的路线（非充电桩）"""
        if user_id not in self.users:
            logger.error(f"_plan_route_to_destination: User {user_id} not found.")
            return False

        user = self.users[user_id]
        start_pos = user["current_position"]
        end_pos = destination # Destination is already a coordinate dict

        # Check if destination is valid
        if not isinstance(end_pos, dict) or 'lat' not in end_pos or 'lng' not in end_pos:
            logger.error(f"_plan_route_to_destination: Invalid destination format for user {user_id}: {end_pos}")
            return False

        # Clear previous route info
        user["route"] = []
        user["waypoints"] = []
        user["destination"] = end_pos.copy()
        user["target_charger"] = None # Ensure it's not targeting a charger
        user["last_destination_type"] = "random" # Or determine based on context if possible

        # Simple path planning: Straight line with random waypoints
        dx = end_pos["lng"] - start_pos["lng"]
        dy = end_pos["lat"] - start_pos["lat"]
        distance = math.sqrt(dx*dx + dy*dy) * 111 # Approx km

        # Generate waypoints
        num_points = random.randint(2, 4)
        waypoints = []
        for i in range(1, num_points):
            t = i / num_points
            point_lng = start_pos["lng"] + t * dx
            point_lat = start_pos["lat"] + t * dy
            # Add random offset
            perpendicular_dx = -dy
            perpendicular_dy = dx
            perp_len = math.sqrt(perpendicular_dx**2 + perpendicular_dy**2)
            if perp_len > 0:
                perpendicular_dx /= perp_len
                perpendicular_dy /= perp_len
            offset_magnitude = random.uniform(-0.1, 0.1) * distance / 111
            point_lng += perpendicular_dx * offset_magnitude
            point_lat += perpendicular_dy * offset_magnitude
            waypoints.append({"lat": point_lat, "lng": point_lng})

        user["waypoints"] = waypoints
        full_route = [start_pos.copy()] + waypoints + [end_pos.copy()]
        user["route"] = full_route

        # Calculate total distance and time
        total_distance = 0
        for i in range(1, len(full_route)):
            p1 = full_route[i-1]
            p2 = full_route[i]
            segment_dist = math.sqrt((p2["lng"] - p1["lng"])**2 + (p2["lat"] - p1["lat"])**2) * 111
            total_distance += segment_dist

        # Ensure travel_speed exists and is not zero before division
        travel_speed = user.get("travel_speed", 45) # Default to 45 if not set
        if travel_speed <= 0:
             logger.warning(f"User {user_id} has invalid travel speed ({travel_speed}). Using default 45 km/h.")
             travel_speed = 45

        travel_time_minutes = (total_distance / travel_speed) * 60

        user["time_to_destination"] = travel_time_minutes
        user["traveled_distance"] = 0

        logger.debug(f"Planned route for user {user_id} to random destination {destination}, distance: {total_distance:.2f} km, time: {travel_time_minutes:.1f} min.")
        return True


    def _has_reached_charger(self, user_id, charger_id):
        """检查用户是否已到达目标充电桩"""
        if user_id not in self.users or charger_id not in self.chargers:
            return False
            
        user = self.users[user_id]
        charger = self.chargers[charger_id]
        
        # 如果用户没有route或者没有time_to_destination，则认为没有到达
        if not user["route"] or user["time_to_destination"] is None:
            return False
            
        # 检查用户当前位置与充电站位置的距离
        user_pos = user["current_position"]
        charger_pos = charger["position"]
        distance = self._calculate_distance(user_pos, charger_pos)
        
        # 如果距离小于0.1km且时间已到，则认为到达
        return distance <= 0.1 and user["time_to_destination"] <= 0
    
    def _calculate_distance(self, pos1, pos2):
        """Calculate distance between two positions"""
        # Simple Euclidean distance
        return math.sqrt((pos1["lat"] - pos2["lat"])**2 + 
                         (pos1["lng"] - pos2["lng"])**2) * 111  # Convert to km (rough approximation)
    
    def _simulate_user_behavior(self):
        """Simulate user behavior - battery drain, movement, charging needs, post-charge actions."""
        time_step_hours = self.time_step_minutes / 60
        
        for user_id, user in self.users.items():
            current_soc = user.get("soc", 0)
            user_status = user.get("status", "idle")

            # --- Post-Charge State Handling ---
            if user_status == "post_charge":
                # Ensure timer exists and is initialized if None
                if user.get("post_charge_timer") is None:
                    user["post_charge_timer"] = random.randint(1, 4) # Initialize if missing
                    logger.debug(f"User {user_id} in post_charge state had None timer, initialized to: {user['post_charge_timer']} steps.")

                # Now we can safely assume post_charge_timer exists as an int
                # Make sure to access the key directly now, not via user.get() again
                if user["post_charge_timer"] > 0: # Use direct access after ensuring initialization
                    user["post_charge_timer"] -= 1
                else: # Timer expired
                    logger.debug(f"User {user_id} post-charge timer expired. Assigning new random destination.")
                    # Assign a new random destination (not a charger initially)
                    new_destination = self._get_random_location()
                    # Ensure it's not the same as current location (rare case)
                    while self._calculate_distance(user["current_position"], new_destination) < 0.1:
                         new_destination = self._get_random_location()

                    user["destination"] = new_destination
                    user["status"] = "traveling" # Start traveling to the new destination
                    user["target_charger"] = None # Not heading to a charger yet
                    user["route"] = None # Will be planned if needed
                    user["time_to_destination"] = None # Will be calculated
                    user["post_charge_timer"] = None # Reset timer
                    user["needs_charge_decision"] = False # Reset flag
                    user["last_destination_type"] = "random"

            # --- Battery Drain (Idle & Traveling & PostCharge) ---
            # Apply base consumption unless charging/waiting
            if user_status not in ["charging", "waiting"]:
                # 基础空闲能耗率 (kWh/h)
                idle_consumption_rate = 0.4
                vehicle_type = user.get("vehicle_type", "sedan")
                
                # 根据车型调整基础能耗
                if vehicle_type == "sedan": 
                    idle_consumption_rate = 0.8
                elif vehicle_type == "suv": 
                    idle_consumption_rate = 1.2
                elif vehicle_type == "truck": 
                    idle_consumption_rate = 2.0
                elif vehicle_type == "luxury":
                    idle_consumption_rate = 1.0
                elif vehicle_type == "compact":
                    idle_consumption_rate = 0.6

                # 季节性能耗差异
                current_month = self.current_time.month
                season_factor = 1.0
                if 6 <= current_month <= 8:  # 夏季
                    season_factor = 2.2  # 空调能耗
                elif current_month <= 2 or current_month == 12:  # 冬季
                    season_factor = 2.5  # 暖气能耗
                else:  # 春秋季节
                    season_factor = 1.3
                
                idle_consumption_rate *= season_factor

                # 时间因素 - 早晚高峰期准备出行时的能耗增加
                hour = self.current_time.hour
                time_factor = 1.0
                if hour in [6, 7, 8, 17, 18, 19]:  # 早晚高峰期
                    time_factor = 1.6  # 高峰期准备时的能耗增加
                elif 22 <= hour or hour <= 4:  # 夜间
                    time_factor = 0.8  # 夜间能耗略低
                
                idle_consumption_rate *= time_factor
                
                # 用户行为和环境条件影响
                behavior_factor = random.uniform(0.9, 1.8)
                idle_consumption_rate *= behavior_factor
                
                # 最终能耗计算
                idle_energy_used = idle_consumption_rate * time_step_hours
                
                # 计算SOC减少
                battery_capacity = user.get("battery_capacity", 60)
                idle_soc_decrease = (idle_energy_used / battery_capacity) * 100 if battery_capacity > 0 else 0

                # 应用电量消耗
                current_soc = max(0, user.get("soc", 0) - idle_soc_decrease)
                user["soc"] = current_soc

            # --- Check Charging Need (Generalized) ---
            user["needs_charge_decision"] = False # Reset flag each step
            # Check if user is active and NOT already heading to a charger
            # Also include 'post_charge' users who might decide to charge again if needed
            if user_status in ["idle", "traveling", "post_charge"] and not user.get("target_charger"):
                # 首先检查是否充电量太小
                estimated_charge_amount = 100 - current_soc  # 假设充满电的情况
                if estimated_charge_amount < 25:  # 如果充电量小于25%，不充电
                    user["needs_charge_decision"] = False
                    logger.debug(f"User {user_id} needs only {estimated_charge_amount:.1f}% charge, skipping charging.")
                # 当SOC较低时强制充电
                elif current_soc <= 20:  # 保持强制充电阈值在20%
                    user["needs_charge_decision"] = True
                    logger.debug(f"User {user_id} SOC critical ({current_soc:.1f}%), forcing charge need.")
                else:
                    # 计算充电概率
                    charging_prob = self._calculate_charging_probability(user, self.current_time.hour)
                    
                    # 添加额外因素影响充电概率
                    # 1. 如果用户刚完成充电不久，大幅降低充电概率
                    timer_value = user.get("post_charge_timer") # Get value which might be None
                    if user_status == "post_charge" and isinstance(timer_value, int) and timer_value > 0:
                        charging_prob *= 0.1  # 进一步降低post-charge状态的充电概率
                    
                    # 2. 如果用户正在随机旅行，基于SOC调整充电概率
                    if user_status == "traveling" and user.get("last_destination_type") == "random":
                        if current_soc > 60:
                            charging_prob *= 0.1  # SOC高时大幅降低充电概率
                        else:
                            charging_prob *= 1.2  # SOC低时适度增加充电概率
                    
                    # 3. 对于SOC高的用户，大幅降低充电概率
                    if current_soc > 75:
                        charging_prob *= 0.01  # 非常低的概率
                    elif current_soc > 60:
                        charging_prob *= 0.1  # 显著降低概率
                    
                    # 4. 如果用户是出租车或网约车，适度调整充电概率
                    if user.get("user_type") in ["taxi", "ride_hailing"]:
                        if current_soc > 50:  # 即使是商业用户，如果电量高也要降低概率
                            charging_prob *= 0.5
                        else:
                            charging_prob *= 1.2  # 电量低时增加商业用户的充电概率
                    
                    # 5. 如果当前是高峰时段，根据SOC调整充电概率
                    hour = self.current_time.hour
                    if hour in [7, 8, 9, 17, 18, 19]:
                        if current_soc > 60:
                            charging_prob *= 0.5  # 高峰期+高SOC，降低概率
                        else:
                            charging_prob *= 1.2  # 高峰期+低SOC，增加概率
                    
                    # 6. 如果SOC在20-35%之间，增加充电概率
                    if 20 < current_soc <= 35:
                        charging_prob *= 1.5  # 增加低电量时的充电概率
                        
                    # 7. 如果随机值小于充电概率，设置充电需求
                    if random.random() < charging_prob:
                        user["needs_charge_decision"] = True
                        logger.debug(f"User {user_id} decided to charge based on probability {charging_prob:.2f}")

            # --- State transition based on charging need ---
            if user["needs_charge_decision"]:
                # If user is idle or traveling randomly and decides to charge
                if user_status in ["idle", "traveling"] and (user.get("last_destination_type") == "random" or user_status == "idle"):
                    logger.info(f"User {user_id} (SOC: {current_soc:.1f}%) needs charging - finding nearest available charger directly")
                    
                    # Stop current random travel
                    if user_status == "traveling":
                        logger.debug(f"User {user_id} was traveling randomly, stopping to go charge.")
                    
                    # Find nearest available charger directly
                    nearest_charger_id = None
                    nearest_distance = float('inf')
                    user_pos = user.get("current_position", {"lat": 0, "lng": 0})
                    
                    # First, look for all chargers that are not full
                    available_chargers = []
                    for c_id, charger in self.chargers.items():
                        # Skip failed chargers
                        if charger.get("status") == "failure":
                            continue
                            
                        # Check if queue is not too long (allow joining if less than 5 in queue)
                        queue_length = len(charger.get("queue", []))
                        if charger.get("status") == "occupied":
                            queue_length += 1
                            
                        if queue_length < 5:  # 增加最大队列长度阈值到5
                            charger_pos = charger.get("position", {"lat": 0, "lng": 0})
                            distance = self._calculate_distance(user_pos, charger_pos)
                            
                            # 根据距离和队列长度计算综合得分
                            # 距离权重降低，队列长度权重提高
                            score = distance * 0.6 + queue_length * 0.4
                            available_chargers.append((c_id, charger, distance, score))
                    
                    # Sort by score instead of just distance
                    available_chargers.sort(key=lambda x: x[3])
                    
                    # Take one of the top 5 chargers with balanced weights
                    if available_chargers:
                        # Favor better scores but allow more variety
                        if len(available_chargers) >= 5:
                            weights = [5, 4, 3, 2, 1]  # More balanced weights
                            nearest_charger_id = random.choices([c[0] for c in available_chargers[:5]], weights=weights, k=1)[0]
                        else:
                            nearest_charger_id = available_chargers[0][0]
                        
                        nearest_distance = next(c[2] for c in available_chargers if c[0] == nearest_charger_id)
                        
                        # Plan route directly to the selected charger
                        if self._plan_route_to_charger(user_id, nearest_charger_id):
                            user["status"] = "traveling"
                            user["target_charger"] = nearest_charger_id
                            user["last_destination_type"] = "charger"
                            logger.info(f"User {user_id} is going DIRECTLY to charger {nearest_charger_id} ({nearest_distance:.2f} km away)")
                            
                            # Reset needs_charge_decision since we've handled it
                            user["needs_charge_decision"] = False
                        else:
                            logger.error(f"Failed to plan route for user {user_id} to charger {nearest_charger_id}")
                    else:
                        logger.warning(f"User {user_id} needs charging but no available chargers found. Staying idle.")
                        # Keep the flag for next time step
                        user["status"] = "idle"
                        user["destination"] = None
                        user["route"] = None

            # --- Movement Simulation ---
            if user_status == "traveling":
                # Ensure the user has a destination to travel to
                if not user.get("destination"):
                    # If user needs charge, they should wait for scheduler (status might already be idle from above logic)
                    if user.get("needs_charge_decision"):
                        logger.debug(f"User {user_id} is traveling, needs charge, but has no destination. Status: {user['status']}. Waiting for scheduler.")
                        # We don't assign random destination here if they need charge
                        continue # Skip movement this step

                    # If somehow traveling with no destination AND doesn't need charge, assign random (fallback case)
                    else:
                        logger.warning(f"User {user_id} is traveling with no destination and doesn't need charge? Assigning random destination.")
                        user["destination"] = self._get_random_location()
                        user["last_destination_type"] = "random"
                        # Plan route to this new random destination
                        self._plan_route_to_destination(user_id, user["destination"])

                    # Skip movement this step if no route exists after potentially planning above
                    if not user.get("route"):
                        continue

                # --- Simulate movement along route ---
                if user.get("time_to_destination") is not None:
                    travel_speed = user.get("travel_speed", 45)
                    battery_capacity = user.get("battery_capacity", 60)

                    # Distance covered in this time step
                    distance_this_step = travel_speed * time_step_hours

                    # Update position and get actual distance moved
                    actual_distance_moved = self._update_user_position_along_route(user, distance_this_step)

                    # Energy consumed during travel (based on actual distance)
                    # 调整基础能耗
                    base_energy_per_km = 0.25 * (1 + (travel_speed / 80))  # 移除了10倍放大
                    
                    # 根据车型调整能耗
                    vehicle_type = user.get("vehicle_type", "sedan")
                    energy_per_km = base_energy_per_km
                    if vehicle_type == "sedan": energy_per_km *= 1.2
                    elif vehicle_type == "suv": energy_per_km *= 1.5
                    elif vehicle_type == "truck": energy_per_km *= 1.8
                    
                    # 驾驶风格影响
                    driving_style = user.get("driving_style", "normal")
                    if driving_style == "aggressive": energy_per_km *= 1.3
                    elif driving_style == "eco": energy_per_km *= 0.9
                    
                    # 路况、堵车和天气影响
                    road_condition = random.uniform(1.0, 1.3)  # 路况影响最多30%
                    weather_impact = random.uniform(1.0, 1.2)  # 天气影响最多20%
                    traffic_factor = 1.0
                    
                    # 模拟高峰时段的交通状况
                    hour = self.current_time.hour
                    if (7 <= hour <= 9) or (17 <= hour <= 19):  # 早晚高峰
                        traffic_factor = random.uniform(1.1, 1.4)  # 高峰期能耗增加10-40%
                    
                    # 组合所有影响因素
                    energy_per_km *= road_condition * weather_impact * traffic_factor
                    
                    energy_consumed = actual_distance_moved * energy_per_km
                    soc_decrease_travel = (energy_consumed / battery_capacity) * 100 if battery_capacity > 0 else 0

                     # Update SOC (already includes base drain from above, add travel drain)
                     # Note: Base drain was already applied earlier, so just subtract travel drain here
                    current_soc = max(0, user["soc"] - soc_decrease_travel) # Subtract from already drained SOC
                    user["soc"] = current_soc
                     

                     # Update remaining time based on actual distance moved
                    time_taken_minutes = (actual_distance_moved / travel_speed) * 60 if travel_speed > 0 else 0
                    user["time_to_destination"] = max(0, user["time_to_destination"] - time_taken_minutes)


                     # Check for arrival
                    if user["time_to_destination"] <= 0.1: # 到达目的地
                        logger.debug(f"User {user_id} arrived at destination {user['destination']}.")
                        # 已到达目的地
                        user["current_position"] = user["destination"].copy()
                        user["time_to_destination"] = 0
                        user["route"] = None # Clear route upon arrival

                        target_charger_id = user.get("target_charger")
                        last_dest_type = user.get("last_destination_type") # Get last destination type

                        # 检查是否到达了目标充电桩
                        if target_charger_id:
                            # 主要情况：到达目标充电桩，target_charger_id 仍然有效
                            logger.info(f"User {user_id} has arrived at target charger {target_charger_id} (target_charger valid). Setting status to WAITING.")
                            user["status"] = "waiting"
                            user["destination"] = None # Clear destination
                            user["arrival_time_at_charger"] = self.current_time # Record arrival time
                            # Keep target_charger_id for queue logic if needed immediately

                            # 尝试将用户加入充电桩队列 (可能由 _simulate_charging_stations 处理更好，但保留以防万一)
                            if target_charger_id in self.chargers:
                                charger = self.chargers[target_charger_id]
                                if "queue" not in charger:
                                    charger["queue"] = []
                                if user_id not in charger["queue"]:
                                     charger["queue"].append(user_id)
                                     logger.info(f"User {user_id} added to queue for charger {target_charger_id}.")
                            else:
                                logger.error(f"User {user_id} arrived at target charger {target_charger_id}, but charger not found! Setting idle.")
                                user["status"] = "idle"

                        # 后备检查：如果 target_charger_id 为 None，但记录的最后目的地类型是 'charger'
                        elif last_dest_type == "charger":
                            logger.warning(f"User {user_id} arrived where charger was targeted (last_dest_type='charger'), but target_charger ID is now None. Setting status to WAITING anyway.")
                            user["status"] = "waiting"
                            user["destination"] = None
                            user["arrival_time_at_charger"] = self.current_time
                            # Cannot add to specific queue without ID here.
                            # _simulate_charging_stations logic will need to handle users in 'waiting' state without a specific target ID if this happens.
                            # OR maybe we should try to find the nearest charger again?
                            # For now, just set to waiting.

                        # 到达的是随机目的地
                        elif last_dest_type == "random":
                            logger.info(f"User {user_id} reached random destination. Setting status to IDLE.")
                            user["status"] = "idle"
                            user["destination"] = None
                            user["target_charger"] = None # Ensure cleared

                            # ... (强制评估充电需求等逻辑保持不变)
                            current_soc = user.get("soc", 100)
                            if current_soc <= 70:
                                user["needs_charge_decision"] = True
                                logger.debug(f"User {user_id} arrived at random destination, forcing charge evaluation with SOC {current_soc:.1f}%")
                            user["post_travel_timer"] = random.randint(1, 3)

                        # 其他情况（真正未预期的目的地）
                        else:
                            logger.error(f"User {user_id} arrived at truly unexpected destination (last_dest_type: {last_dest_type}). Setting to idle.")
                            user["status"] = "idle"
                            user["destination"] = None
                            user["target_charger"] = None
                            user["last_destination_type"] = None

            # Update final user range based on potentially updated SOC
            user["current_range"] = user.get("max_range", 300) * (user["soc"] / 100)
    
    def _process_charging(self):
        """Process charging operations for all chargers and users"""
        # 模拟用户行为（电量消耗等）
        self._simulate_user_behavior()
        
        # 模拟充电站操作并获取总EV负载
        ev_load = self._simulate_charging_stations()
        
        # Update grid EV load
        if isinstance(self.grid_status, dict):
            # Use update for safer modification
            self.grid_status.update({"ev_load": ev_load})
        else:
            logger.error("_process_charging: grid_status is not a dict, cannot update ev_load.")
    
    def _simulate_charging_stations(self):
        """模拟充电站操作，处理充电过程并计算总EV负载"""
        time_step_hours = round(self.time_step_minutes / 60, 4)  # 使用round避免精度问题
        total_ev_load = 0
        
        # 统计信息 - 运行时诊断
        active_chargers = 0
        charging_users = 0
        waiting_users = 0
        total_chargers = len(self.chargers)
        chargers_with_queue = 0
        
        # 遍历所有充电桩
        for charger_id, charger in self.chargers.items():
            # 初始化充电量变量
            actual_charging_amount = 0
            
            # 跳过故障状态的充电桩
            if charger.get("status") == "failure":
                continue
                
            queue = charger.get("queue", [])
            if queue:
                chargers_with_queue += 1
                waiting_users += len(queue)
            
            # 处理当前正在充电的用户
            if charger.get("status") == "occupied" and charger.get("current_user"):
                active_chargers += 1
                charging_users += 1
                user_id = charger.get("current_user")
                
                if user_id in self.users:
                    user = self.users[user_id]
                    
                    # 当前SOC和电池容量
                    current_soc = user.get("soc", 0)
                    battery_capacity = user.get("battery_capacity", 60)
                    target_soc = user.get("target_soc", 85)
                    
                    # 1. 计算达到目标所需的SOC和能量
                    soc_needed = max(0, target_soc - current_soc)
                    energy_needed = (soc_needed / 100.0) * battery_capacity

                    # 2. 计算充电功率和充电时间
                    # 充电桩类型判断和功率设置
                    charger_type = charger.get("type", "normal")
                    if charger_type == "superfast":
                        charger_power = 180  # 超级快充 180kW
                    elif charger_type == "fast":
                        charger_power = 120  # 快充 120kW
                    else:
                        charger_power = 60   # 慢充 60kW
                    
                    # 基础充电效率
                    base_efficiency = 0.92
                
                    charge_efficiency = base_efficiency
                    soc_factor = 1.0    
                    # 根据SOC调整充电功率
                    if current_soc < 20:
                        # 低SOC时保持较高功率
                        actual_power = charger_power * charge_efficiency
                    elif current_soc < 50:
                        # 20-50% SOC时线性降低
                        soc_factor = 1.0 - ((current_soc - 20) / 30) * 0.1
                        actual_power = charger_power * soc_factor * charge_efficiency
                    elif current_soc < 80:
                        # 50-80% SOC时加速降低
                        soc_factor = 0.9 - ((current_soc - 50) / 30) * 0.2
                        actual_power = charger_power * soc_factor * charge_efficiency
                    else:
                        # 80%以上SOC时显著降低
                        soc_factor = 0.7 - ((current_soc - 80) / 20) * 0.5
                        actual_power = charger_power * max(0.1, soc_factor) * charge_efficiency

                    # 记录充电效率信息
                    logger.debug(f"Charging efficiency factors - Base: {base_efficiency:.2f}, " 
                                f"SOC({current_soc}%): {soc_factor:.2f}, Final Power: {actual_power:.2f}kW")
                    
                    # 获取充电开始时间
                    charging_start_time = charger.get("charging_start_time", self.current_time)
                    charging_duration_minutes = (self.current_time - charging_start_time).total_seconds() / 60
                    
                    # 最大充电时间限制
                    max_charging_time = 0
                    if charger_type == "superfast":
                        max_charging_time = 30  # 超级快充最多30分钟
                    elif charger_type == "fast":
                        max_charging_time = 60  # 快充最多60分钟
                    else:
                        max_charging_time = 180  # 慢充最多3小时
                    
                    # 使用round避免浮点数精度问题
                    charging_duration_minutes = round(charging_duration_minutes, 2)
                    
                    # 如果超过最大充电时间，强制结束充电
                    if charging_duration_minutes + 0.01 >= max_charging_time:  # 添加小的容差
                        logger.warning(f"User {user_id} charging time exceeded limit ({max_charging_time} min, actual: {charging_duration_minutes:.2f} min). Force ending charging session.")
                        
                        # 正确计算本次充电的总电量和最终SOC
                        # 按时间比例计算实际充到了多少SOC
                        initial_soc = user.get("initial_soc", current_soc)
                        soc_to_charge = target_soc - initial_soc
                        time_ratio = min(1.0, charging_duration_minutes / max_charging_time)
                        actual_soc_increase = soc_to_charge * time_ratio
                        new_soc = initial_soc + actual_soc_increase
                        
                        # 计算实际充电量(kWh)
                        actual_charging_amount = (actual_soc_increase / 100) * battery_capacity
                        if actual_charging_amount < 0:
                            actual_charging_amount = 0
                            new_soc = initial_soc
                        
                        # 强制结束充电会话
                        charger["status"] = "available"
                        charger["current_user"] = None
                        user["status"] = "post_charge"
                        user["target_charger"] = None
                        user["destination"] = None
                        user["route"] = None
                        user["post_charge_timer"] = random.randint(1, 3)
                        
                        # 更新用户SOC和续航里程
                        user["soc"] = new_soc
                        user["current_range"] = user.get("max_range", 400) * (new_soc / 100)
                        
                        # 记录充电会话信息
                        charging_session = {
                            "user_id": user_id,
                            "charger_id": charger_id,
                            "start_time": charger.get("charging_start_time"),
                            "end_time": self.current_time,
                            "duration_minutes": charging_duration_minutes,
                            "initial_soc": initial_soc,
                            "final_soc": new_soc,
                            "energy_charged": actual_charging_amount,
                            "termination_reason": "time_limit_exceeded"
                        }
                        
                        # 添加到充电历史
                        if not hasattr(self, "charging_history"):
                            self.charging_history = []
                        self.charging_history.append(charging_session)
                        
                        # 添加到总负载
                        actual_power_used = actual_charging_amount / time_step_hours if time_step_hours > 0 else 0
                        total_ev_load += actual_power_used
                        
                        logger.info(f"Charging session ended: Total energy charged: {actual_charging_amount:.2f} kWh, Final SOC: {new_soc:.1f}%")
                        
                        # 处理队列中的下一个用户
                        while charger["queue"]:
                            next_user_id = charger["queue"].pop(0)
                            if next_user_id in self.users:
                                next_user = self.users[next_user_id]
                                if next_user.get("status") == "waiting":
                                    charger["current_user"] = next_user_id
                                    charger["status"] = "occupied"
                                    charger["charging_start_time"] = self.current_time
                                    next_user["status"] = "charging"
                                    next_user["target_soc"] = min(85, next_user.get("soc", 0) + 50)
                                    next_user["initial_soc"] = next_user.get("soc", 0)  # 记录初始SOC
                                    logger.info(f"Next user {next_user_id} started charging at {charger_id}")
                                    break
                        
                        if not charger.get("current_user"):
                            charger["status"] = "available"
                            logger.info(f"No valid waiting users in queue for {charger_id}")
                        
                        # 不要在这里return，继续处理下一个充电桩
                        continue
                    else:
                        # 计算此时间步内最大可提供的能量
                        max_energy_this_step = actual_power * time_step_hours
                        actual_charging_amount = min(energy_needed, max_energy_this_step)
                        
                        if actual_charging_amount <= 0.01:
                            if current_soc >= target_soc - 1:
                                new_soc = current_soc
                                actual_charging_amount = 0
                            else:
                                # 如果充电量太小但还没达到目标，继续处理下一个充电桩
                                continue
                        else:
                            actual_soc_increase = (actual_charging_amount / battery_capacity) * 100 if battery_capacity > 0 else 0
                            new_soc = min(100, current_soc + actual_soc_increase)
                            logger.info(f"User {user_id} charging: SOC {current_soc:.1f}% -> {new_soc:.1f}% (+{actual_soc_increase:.1f}%), Energy: {actual_charging_amount:.2f} kWh")
                        
                        # 更新用户SOC和续航里程
                        user["soc"] = new_soc
                        user["current_range"] = user.get("max_range", 400) * (new_soc / 100)
                        
                        # 添加到总负载
                        actual_power_used = actual_charging_amount / time_step_hours if time_step_hours > 0 else 0
                        total_ev_load += actual_power_used
                        
                        # 计算收入
                        current_price = self.grid_status.get("current_price", 0.85)
                        price_multiplier = charger.get("price_multiplier", 1.0)
                        revenue = actual_charging_amount * current_price * price_multiplier
                        
                        # 更新充电桩收入和能源统计
                        charger["daily_revenue"] = charger.get("daily_revenue", 0) + revenue
                        charger["daily_energy"] = charger.get("daily_energy", 0) + actual_charging_amount
                        
                        # 检查充电是否完成
                        if new_soc >= target_soc - 0.5 or charging_duration_minutes + 0.01 >= max_charging_time:  # 添加小的容差
                            # 充电完成
                            charging_end_time = self.current_time
                            charging_start_time = charger.get("charging_start_time", charging_end_time - timedelta(minutes=30))
                            charging_time = round((charging_end_time - charging_start_time).total_seconds() / 60, 2)  # 使用round避免精度问题
                            
                            # 记录充电历史
                            if "charging_history" not in user:
                                user["charging_history"] = []
                            
                            # 计算满意度
                            expected_time = 0
                            if charger_type == "superfast":
                                expected_time = 20
                            elif charger_type == "fast":
                                expected_time = 45
                            else:
                                expected_time = 120
                            
                            time_satisfaction = min(1.0, expected_time / max(charging_time, 1.0))
                            price_sensitivity = user.get("price_sensitivity", 0.5)
                            price_satisfaction = max(0.0, 1.0 - (price_sensitivity * (revenue / 50.0)))
                            final_satisfaction = 0.7 * time_satisfaction + 0.3 * price_satisfaction
                            
                            user["charging_history"].append({
                                "charger_id": charger_id,
                                "start_time": charging_start_time,
                                "end_time": charging_end_time,
                                "charging_amount": actual_charging_amount,
                                "cost": revenue,
                                "charging_time": charging_time,
                                "satisfaction": final_satisfaction
                            })
                            
                            logger.info(f"User {user_id} finished charging at {charger_id}. Final SOC: {new_soc:.1f}%, Time: {charging_time:.1f} min, Satisfaction: {final_satisfaction:.2f}")
                            
                            # 更新用户和充电站状态
                            user["status"] = "post_charge"
                            user["target_charger"] = None
                            user["destination"] = None
                            user["route"] = None
                            user["post_charge_timer"] = random.randint(1, 3)
                            
                            # 处理队列中的下一个用户
                            while charger["queue"]:
                                next_user_id = charger["queue"].pop(0)
                                if next_user_id in self.users:
                                    next_user = self.users[next_user_id]
                                    if next_user.get("status") == "waiting":
                                        charger["current_user"] = next_user_id
                                        charger["status"] = "occupied"
                                        charger["charging_start_time"] = self.current_time
                                        next_user["status"] = "charging"
                                        next_user["target_soc"] = min(95, next_user.get("soc", 0) + 50)
                                        next_user["initial_soc"] = next_user.get("soc", 0)  # 记录初始SOC
                                        logger.info(f"Next user {next_user_id} started charging at {charger_id}")
                                        break
                            
                            if not charger.get("current_user"):
                                charger["status"] = "available"
                                logger.info(f"No valid waiting users in queue for {charger_id}")
                else:
                    # User ID不在用户列表中，修复状态
                    logger.warning(f"Charger {charger_id} has invalid current_user {user_id}. Fixing state.")
                    charger["status"] = "available"
                    charger["current_user"] = None
            
            # 如果充电桩空闲但有等待用户，开始为第一个用户充电
            elif charger.get("status") == "available" and charger.get("queue"):
                next_user_id = charger["queue"].pop(0)
                if next_user_id in self.users:
                    next_user = self.users[next_user_id]
                    # *** ADD Check for user status ***
                    logger.debug(f"Charger {charger_id} is available. Trying to start user {next_user_id} from queue. User's current status: {next_user.get('status')}")
                    if next_user.get("status") == "waiting":
                        charger["status"] = "occupied"
                        charger["current_user"] = next_user_id
                        charger["charging_start_time"] = self.current_time
                        next_user["status"] = "charging"
                        logger.info(f"User {next_user_id} (status was waiting) successfully started charging at available charger {charger_id}")
                        active_chargers += 1
                        charging_users += 1
                    else:
                        # User was in queue but not in 'waiting' state, log and skip
                        logger.warning(f"User {next_user_id} pulled from queue for {charger_id} but status was '{next_user.get('status')}' (expected 'waiting'). Skipping charging start this step.")
                        # Consider putting user back: charger["queue"].insert(0, next_user_id)
                        # Or maybe remove them if state is consistently wrong?
                else:
                    logger.warning(f"User {next_user_id} was in queue for {charger_id} but not found in self.users! Removing from queue.")
        
            # Log if charger is available but queue is empty
            elif charger.get("status") == "available" and not charger.get("queue"):
                logger.debug(f"Charger {charger_id} is available, queue is empty.")
            
            # Log if charger is occupied
            elif charger.get("status") == "occupied":
                logger.debug(f"Charger {charger_id} is occupied by user {charger.get('current_user')}. Queue length: {len(charger.get('queue', []))}")

        # 添加诊断信息日志
        total_users = len(self.users)
        idle_users = sum(1 for u in self.users.values() if u.get("status") == "idle")
        traveling_users = sum(1 for u in self.users.values() if u.get("status") == "traveling")
        # Recalculate waiting users based on actual status, not just queue length
        actual_waiting_users = sum(1 for u in self.users.values() if u.get("status") == "waiting")
        
        logger.info(f"Charging stations summary @ {self.current_time}: {active_chargers}/{total_chargers} active, "
                f"{chargers_with_queue} have queues.")
        logger.info(f"User status @ {self.current_time}: {charging_users} charging, {actual_waiting_users} waiting, "
                f"{traveling_users} traveling, {idle_users} idle, {total_users} total")
        
        return total_ev_load
    def _update_grid_state(self):
        """Update grid state based on current time and EV load with robustness"""
        hour = self.current_time.hour

        # 确保grid_status是一个字典
        if not isinstance(self.grid_status, dict):
            logger.error("Critical error: self.grid_status is not a dictionary! Reinitializing.")
            self.grid_status = self._initialize_grid()

        # 从配置文件获取基础负载配置 - 使用更新后的更高默认值
        base_load_profile = self.config.get("grid", {}).get("base_load", [
            16000, 14000, 12000, 11000, 10000, 11000, 18000, 24000, 30000, 32000, 32800, 33600,
            32000, 30000, 28000, 26000, 28000, 30000, 34000, 36000, 32000, 28000, 24000, 20000
        ])

        if not isinstance(base_load_profile, list) or len(base_load_profile) != 24:
            logger.warning(f"Invalid base_load_profile in config: {base_load_profile}. Using default.")
            # 更新默认配置文件
            base_load_profile = [
                16000, 14000, 12000, 11000, 10000, 11000, 18000, 24000, 30000, 32000, 32800, 33600,
                32000, 30000, 28000, 26000, 28000, 30000, 34000, 36000, 32000, 28000, 24000, 20000
            ]

        # 获取当前小时的基础负载
        try:
            base_load = base_load_profile[hour]
        except IndexError:
            logger.warning(f"Hour {hour} out of range for base_load_profile. Using default value.")
            base_load = 20000 # 更高的默认值

        # 更新电网状态
        ev_load = self.grid_status.get("ev_load", 0)

        # 计算总负载百分比 - 提高系统最大容量
        system_capacity = 60000  # 系统最大容量提高到 60000kW
        total_load = base_load + ev_load
        grid_load_percentage = (total_load / system_capacity) * 100

        # 添加调试日志
        logger.debug(f"_update_grid_state: Hour={hour}, BaseLoad={base_load:.1f}kW, EVLoad={ev_load:.1f}kW, TotalLoad={total_load:.1f}kW ({grid_load_percentage:.1f}% of {system_capacity}kW)")

        # 更新可再生能源比例 - 基于实际发电量
        # (保持之前的逻辑，但注意这里的分母是 total_load)
        solar_gen_profile = self.config.get("grid", {}).get("solar_generation", [0]*24)
        wind_gen_profile = self.config.get("grid", {}).get("wind_generation", [0]*24)
        solar_gen = solar_gen_profile[hour] if 0 <= hour < 24 else 0
        wind_gen = wind_gen_profile[hour] if 0 <= hour < 24 else 0

        total_renewable = solar_gen + wind_gen
        renewable_ratio = (total_renewable / total_load * 100) if total_load > 0 else 0

        # 更新电价
        current_price = self._get_current_price(hour)

        # 创建新的电网状态
        new_grid_status = {
            "base_load": base_load,  # 当前基础负载（kW）
            "current_load": total_load,  # 总负载（kW）
            "grid_load": grid_load_percentage,  # 负载百分比 (0-100+)
            "ev_load": ev_load,  # 电动车负载（kW）
            "renewable_ratio": renewable_ratio,  # 可再生能源比例（%）
            "current_price": current_price,
            "solar_generation": solar_gen_profile, # Pass full profile
            "wind_generation": wind_gen_profile, # Pass full profile
            "peak_hours": self.grid_status.get("peak_hours", [7, 8, 9, 10, 18, 19, 20, 21]),
            "valley_hours": self.grid_status.get("valley_hours", [0, 1, 2, 3, 4, 5]),
            "normal_price": self.grid_status.get("normal_price", 0.85),
            "peak_price": self.grid_status.get("peak_price", 1.2),
            "valley_price": self.grid_status.get("valley_price", 0.4)
        }

        self.grid_status = new_grid_status
    
    def _save_current_state(self):
        """保存当前状态到历史记录"""
        # 获取当前状态
        state = self.get_current_state()
        
        # 添加完整的负载数据
        state["grid_status"] = {
            "current_load": self.grid_status.get("current_load", 0),
            "grid_load": self.grid_status.get("grid_load", 0),
            "ev_load": self.grid_status.get("ev_load", 0),
            "renewable_ratio": self.grid_status.get("renewable_ratio", 0),
            "current_price": self.grid_status.get("current_price", 0.85),
            "base_load": self.grid_status.get("base_load", []),
            "peak_hours": self.grid_status.get("peak_hours", []),
            "valley_hours": self.grid_status.get("valley_hours", [])
        }
        
        # 如果历史记录不存在，创建一个新的
        if not hasattr(self, 'history'):
            self.history = []
        
        # 添加到历史记录
        self.history.append(state)
        
        # 限制历史记录长度，只保留最近24小时的数据
        if len(self.history) > 24 * (60 // self.time_step_minutes):  # 24小时的数据点数
            self.history = self.history[-(24 * (60 // self.time_step_minutes)):]
    
    def reset(self):
        """重置环境到初始状态，返回初始状态"""
        # 重置当前时间
        self.current_time = datetime.now().replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        
        # 重新初始化用户、充电桩和电网状态
        logger.info("重置充电环境状态")
        self.users = self._initialize_users()
        self.chargers = self._initialize_chargers()
        self.grid_status = self._initialize_grid()
        self.history = []
        
        # 重置统计信息
        self.metrics = {
            "user_satisfaction": [],
            "operator_profit": [],
            "grid_friendliness": [],
            "total_reward": [],
            "charging_sessions": 0,
            "average_waiting_time": 0,
            "average_charging_time": 0
        }
        
        # 返回初始状态
        return self.get_current_state()

    def _calculate_rewards(self):
        """计算当前状态下的奖励值"""
        # 用户满意度指标
        user_satisfaction = 0
        total_users = len(self.users) if self.users else 1  # 避免除以零
        
        # 统计不同状态的用户数量
        charging_count = 0
        waiting_count = 0
        traveling_count = 0
        low_soc_count = 0  # SOC低于30%的用户
        
        for user in self.users.values():
            # SOC因子 - 电量越高满意度越高
            soc_factor = min(1.0, user.get("soc", 0) / 100)  # 使用.get()，限制最大值为1
            
            # 状态因子 - 不同状态有不同的满意度
            status_factor = 1.0
            user_status = user.get("status", "idle")  # 使用.get()
            
            if user_status == "charging":
                status_factor = 1.2  # 正在充电的用户满意度更高
                charging_count += 1
            elif user_status == "waiting":
                status_factor = 0.6  # 等待充电的用户满意度较低
                waiting_count += 1
            elif user_status == "traveling":
                status_factor = 0.8  # 正在前往充电站的用户满意度处于中间
                traveling_count += 1
                
            if user.get("soc", 0) < 30:
                low_soc_count += 1
                
            # 单个用户的满意度贡献，考虑电量和状态
            user_satisfaction += soc_factor * status_factor
        
        # 归一化用户满意度，考虑正在充电和等待用户的比例
        active_users_ratio = (charging_count + waiting_count) / total_users if total_users > 0 else 0
        user_satisfaction = user_satisfaction / total_users  # 基本归一化
        
        # 对用户满意度进行调整，考虑到低电量用户和服务中用户比例
        # 如果低SOC用户很多但充电/等待用户比例低，降低满意度
        if low_soc_count > 0 and active_users_ratio < 0.2:
            user_satisfaction *= 0.8
        
        # 缩放到[-1, 1]范围 - 使用更平滑的曲线
        user_satisfaction = 2 * (1 / (1 + math.exp(-5 * (user_satisfaction - 0.5)))) - 1
        
        # 运营商利润 - 改进计算方法
        total_revenue = 0
        total_energy = 0
        total_chargers = len(self.chargers) if self.chargers else 1  # 避免除以零
        occupied_chargers = 0
        
        for charger in self.chargers.values():
            daily_revenue = charger.get("daily_revenue", 0)  # 使用.get()
            daily_energy = charger.get("daily_energy", 0)  # 使用.get()获取充电量
            total_revenue += daily_revenue
            total_energy += daily_energy
            
            if charger.get("status") == "occupied":
                occupied_chargers += 1
        
        # 充电桩利用率 - 重要的运营指标
        charger_utilization = occupied_chargers / total_chargers
        
        # 收入系数 - 随时间缓慢增长，避免过快饱和
        # 考虑当前小时，白天时段按小时比例计算，晚上则保持低值
        hour = self.current_time.hour
        day_progress = 0
        
        if 6 <= hour <= 23:  # 工作时段 6:00-23:00
            day_progress = (hour - 6) / 17  # 归一化到0-1
        else:  # 夜间时段
            day_progress = 0.1  # 夜间较低固定值
        
        # 跟踪历史累计收入，用于平滑和正确评估运营商利润
        if not hasattr(self, '_cumulative_revenue'):
            self._cumulative_revenue = 0
            self._revenue_history = []
            self._revenue_day_counter = 0
            self._days_revenue = []  # 每日收入列表
            self._last_day = self.current_time.day
        
        # 检测新的一天，重置日收入
        if self.current_time.day != getattr(self, '_last_day', -1):
            self._last_day = self.current_time.day
            if hasattr(self, '_daily_revenue'):
                self._days_revenue.append(self._daily_revenue)
                # 保留最近7天的数据
                if len(self._days_revenue) > 7:
                    self._days_revenue.pop(0)
            self._daily_revenue = 0
            self._revenue_day_counter += 1
        
        # 更新当前步骤的收入
        step_revenue = sum(c.get("daily_revenue", 0) - c.get("previous_revenue", 0) for c in self.chargers.values())
        
        # 更新每个充电桩的历史收入
        for charger_id, charger in self.chargers.items():
            charger["previous_revenue"] = charger.get("daily_revenue", 0)
        
        # 累计当天收入
        if not hasattr(self, '_daily_revenue'):
            self._daily_revenue = 0
        self._daily_revenue += step_revenue
        
        # 累计总收入（需要给予一个逐渐减弱的权重）
        decay_factor = 0.98  # 较慢的衰减率
        self._cumulative_revenue = self._cumulative_revenue * decay_factor + step_revenue
        
        # 收入因子 - 根据充电桩数量和利用率动态计算期望值
        # 每个充电桩每天的基准收入（元）
        base_daily_revenue_per_charger = 200  
        
        # 理论最大日收入（考虑充电桩数量的平方根缩放）
        theoretical_max_daily_revenue = base_daily_revenue_per_charger * math.sqrt(total_chargers) * 1.2
        
        # 基于历史数据的预期收入，考虑时间进度
        expected_daily_revenue = theoretical_max_daily_revenue * (0.3 + 0.7 * day_progress)
        
        # 计算收入比率 - 使用更平滑的比较方式
        revenue_ratio = 0
        
        # 如果有足够的历史数据，使用移动平均
        if hasattr(self, '_days_revenue') and len(self._days_revenue) > 0:
            avg_daily_revenue = sum(self._days_revenue) / len(self._days_revenue)
            # 当天进度比例
            day_fraction = min(1.0, (hour + 1) / 24)
            # 当天预期收入
            today_expected = expected_daily_revenue * day_fraction
            # 实际累计与预期的比例
            revenue_ratio = min(0.9, self._daily_revenue / (today_expected + 1))  # 防止除以0，限制最大值
        else:
            # 没有足够历史数据时，使用理论值和当前利用率
            revenue_ratio = min(0.85, total_revenue / (expected_daily_revenue + 1) * charger_utilization)
        
        # 充电能量因子 - 充电量与充电用户数量的关系
        energy_factor = 0
        active_users = charging_count + waiting_count
        
        if total_energy > 0 and active_users > 0:
            # 每个活跃用户的预期充电量范围
            expected_energy_per_user = 10  # kWh
            
            # 实际每用户充电量
            actual_energy_per_user = total_energy / active_users
            
            # 能量因子，使用对数函数使增长更平滑
            energy_ratio = actual_energy_per_user / expected_energy_per_user
            energy_factor = min(0.85, math.log(1 + energy_ratio) / math.log(2))
        
        # 组合利润得分 - 平衡各因素的影响
        operator_profit_combined = (
            revenue_ratio * 0.5 +                 # 收入贡献
            energy_factor * 0.3 +                 # 能量输出贡献
            (charger_utilization * 0.8) * 0.2     # 资源利用率贡献（缩小范围）
        )
        
        # 应用超级平滑的S型函数，确保饱和度非常缓慢
        # 使用自定义映射函数，控制增长率
        def smooth_profit_curve(x):
            # 将[0,1]范围的输入映射到[-1,1]范围的输出
            # 使用更扁平的S曲线，中点在0.5
            if x < 0.2:
                # 起始段缓慢增长
                return -0.8 + x * 2
            elif x < 0.8:
                # 中间段线性增长但较缓
                return -0.4 + (x - 0.2) * 1.0
            else:
                # 高端缓慢接近1
                remaining = x - 0.8
                return 0.4 + remaining * 1.5
        
        operator_profit = smooth_profit_curve(operator_profit_combined)
        
        # 确保在[-1,1]范围内
        operator_profit = max(-1.0, min(1.0, operator_profit))
        
        # 电网友好度指标 - 改进计算
        current_load = self.grid_status.get("grid_load", 50)  # 使用.get()并设置默认值50
        ev_load = self.grid_status.get("ev_load", 0)  # 电动车充电负载
        max_load = 100  # 最大负载基准
        
        # 计算负载比例，但考虑电动车负载的贡献
        base_load = current_load - (ev_load)  # 去除EV负载影响后的基础负载
        base_load_ratio = base_load / max_load
        
        # EV负载占总负载的比例
        ev_load_ratio = 0
        if current_load > 0:
            ev_load_ratio = (ev_load) / current_load
        
        # 可再生能源比例
        renewable_ratio = self.grid_status.get("renewable_ratio", 0) / 100  # 使用.get()，转换为0-1
        
        # 考虑峰谷状态和再生能源情况
        hour = self.current_time.hour
        
        # 使用与单次决策相同的峰谷时段定义
        peak_hours = [9, 10, 11, 12, 13, 14, 15, 16, 19, 20, 21]  # 工作和晚间高峰
        valley_hours = [0, 1, 2, 3, 4, 5, 23]  # 深夜/凌晨低谷
        shoulder_hours = [6, 7, 8, 17, 18, 22]  # 过渡时段
        
        # 时间因子 - 考虑峰谷
        time_factor = 0
        if hour in peak_hours:
            time_factor = -0.3  # 高峰期，不友好（降低惩罚力度）
        elif hour in valley_hours:
            time_factor = 0.6   # 低谷期，很友好（增加奖励力度）
        else:  # shoulder_hours
            time_factor = 0.2   # 过渡期，适中友好
        
        # 增加降低EV影响的因子，与单次决策计算保持一致
        base_load_factor = 20  # 与单次决策保持一致
        adjusted_grid_load = (current_load * base_load_factor + ev_load) / (base_load_factor + 1)
        
        # 基于调整后负载的评分，与单次决策保持一致
        if adjusted_grid_load < 30:  # 低负载，非常友好
            load_factor = 0.8
        elif adjusted_grid_load < 50:  # 中等负载，适度友好
            load_factor = 0.5 - (adjusted_grid_load - 30) * 0.015  # 0.5到0.2线性下降
        elif adjusted_grid_load < 70:  # 较高负载，不太友好
            load_factor = 0.2 - (adjusted_grid_load - 50) * 0.015  # 0.2到-0.1线性下降
        elif adjusted_grid_load < 85:  # 高负载，不友好
            load_factor = -0.1 - (adjusted_grid_load - 70) * 0.025  # -0.1到-0.475线性下降
        else:  # 极高负载，非常不友好
            load_factor = -0.475 - (adjusted_grid_load - 85) * 0.01  # -0.475到-0.625线性下降
            load_factor = max(-0.7, load_factor)  # 限制最低值
        
        # 可再生能源因子 - 再生能源比例高时鼓励充电
        renewable_factor = 0.8 * renewable_ratio  # 与单次决策保持一致
        
        # EV负载占比因子 - EV负载占比过高时轻微惩罚
        ev_concentration_factor = 0
        if ev_load_ratio > 0.2:  # EV负载超过总负载20%时开始惩罚
            ev_concentration_factor = -0.1 * (ev_load_ratio - 0.2) / 0.7  # 降低惩罚
        
        # 计算总电网友好度
        grid_friendliness = load_factor + renewable_factor + time_factor + ev_concentration_factor
        
        # 确保评分在[-1,1]范围内，并提高总体评分水平
        grid_friendliness = max(-0.9, min(1.0, grid_friendliness))
        
        # 对所有评分进行小幅度提升，避免过度负面
        if grid_friendliness < 0:
            grid_friendliness *= 0.8  # 负面评分减弱20%
        else:
            grid_friendliness *= 1.1  # 正面评分增强10%
            grid_friendliness = min(1.0, grid_friendliness)  # 确保不超过1.0
            
        # 增加详细日志，帮助诊断
        logger.info(f"Grid friendliness calculation - overall metrics:")
        logger.info(f"  - Current load: {current_load:.1f}%, EV load: {ev_load:.1f}%")
        logger.info(f"  - Adjusted grid load: {adjusted_grid_load:.1f}%")
        logger.info(f"  - Hour: {hour} ({'peak' if hour in peak_hours else 'valley' if hour in valley_hours else 'shoulder'})")
        logger.info(f"  - Load factor: {load_factor:.2f}")
        logger.info(f"  - Time factor: {time_factor:.2f}")
        logger.info(f"  - Renewable factor (ratio={renewable_ratio:.2f}): {renewable_factor:.2f}")
        logger.info(f"  - EV concentration factor: {ev_concentration_factor:.2f}")
        logger.info(f"  - Final grid friendliness (before adjustment): {load_factor + renewable_factor + time_factor + ev_concentration_factor:.2f}")
        logger.info(f"  - Final grid friendliness (after adjustment): {grid_friendliness:.2f}")
        
        # 计算总奖励（加权和）
        weights = {
            "user_satisfaction": 0.4,
            "operator_profit": 0.3,
            "grid_friendliness": 0.3
        }
        
        total_reward = (user_satisfaction * weights["user_satisfaction"] +
                        operator_profit * weights["operator_profit"] +
                        grid_friendliness * weights["grid_friendliness"])
        
        # 存储本次计算的指标，用于历史记录
        self.metrics["user_satisfaction"].append(user_satisfaction)
        self.metrics["operator_profit"].append(operator_profit)
        self.metrics["grid_friendliness"].append(grid_friendliness)
        self.metrics["total_reward"].append(total_reward)
                        
        # 计算无序充电的基准指标（用于对比）
        if hasattr(self, 'uncoordinated_baseline') and self.uncoordinated_baseline:
            # 现在我们有了更精确的用户行为模式，可以做更精确的对比
            uncoordinated_user_satisfaction = 0
            uncoordinated_operator_profit = 0
            uncoordinated_grid_friendliness = 0
            
            # 无序充电的特点：
            # 1. 用户满意度往往较高，因为用户更可能找最近的充电站
            # 2. 运营商利润不均衡，热门站点过载而偏远站点闲置
            # 3. 电网友好度差，因为充电高度集中在工作日下班后
            
            # 无序充电下的用户满意度 - 实际可能更高
            # 用户可自由选择，但总体等待时间更长
            uncoordinated_wait_factor = 0.7  # 等待时间估计
            uncoordinated_soc_factor = 1.1 * (sum([min(1.0, u.get("soc", 0) / 100) for u in self.users.values()]) / total_users)
            uncoordinated_user_satisfaction = min(0.8, uncoordinated_wait_factor * uncoordinated_soc_factor)
            
            # 无序充电下的运营商利润 - 更真实建模
            # 收入可能相似，但利用率不均衡
            unc_utilization_factor = 0.7 if charger_utilization > 0.3 else 0.9  # 高利用率时效率更低
            
            # 收入分布不均
            revenue_distribution_penalty = -0.2 if charger_utilization > 0.4 else -0.1
            
            # 计算无序充电利润 - 与当前利润相关但更不平衡
            uncoordinated_operator_profit = max(-0.8, min(0.8, 
                 operator_profit * unc_utilization_factor + revenue_distribution_penalty))
            
            # 无序充电下的电网友好度 - 更精确建模不同时段的行为
            # 晚间充电高度集中，早晨相对较少
            if 17 <= hour <= 22:  # 晚高峰充电集中
                uncoordinated_grid_friendliness = -0.7 - 0.1 * renewable_ratio  # 几乎不考虑可再生能源
            elif 7 <= hour <= 9:  # 早高峰适度集中
                uncoordinated_grid_friendliness = -0.4 - 0.1 * renewable_ratio
            elif 0 <= hour <= 5:  # 深夜较少充电
                uncoordinated_grid_friendliness = 0.2 + 0.2 * renewable_ratio  # 深夜利用率低但友好
            else:
                uncoordinated_grid_friendliness = -0.2  # 其他时段一般水平
            
            # 计算总体奖励
            uncoordinated_total_reward = (
                uncoordinated_user_satisfaction * weights["user_satisfaction"] +
                uncoordinated_operator_profit * weights["operator_profit"] +
                uncoordinated_grid_friendliness * weights["grid_friendliness"]
            )
            
            # 存储无序充电基准指标
            self.metrics["uncoordinated_user_satisfaction"] = uncoordinated_user_satisfaction
            self.metrics["uncoordinated_operator_profit"] = uncoordinated_operator_profit
            self.metrics["uncoordinated_grid_friendliness"] = uncoordinated_grid_friendliness
            self.metrics["uncoordinated_total_reward"] = uncoordinated_total_reward
            
            # 计算改进百分比（针对总奖励）
            if uncoordinated_total_reward != 0:
                improvement_percentage = ((total_reward - uncoordinated_total_reward) / 
                                         abs(uncoordinated_total_reward)) * 100
                self.metrics["improvement_percentage"] = improvement_percentage
            
            # 返回包含对比的结果
        return {
                "user_satisfaction": user_satisfaction,
                "operator_profit": operator_profit,
                "grid_friendliness": grid_friendliness,
                "total_reward": total_reward,
                "uncoordinated_user_satisfaction": uncoordinated_user_satisfaction,
                "uncoordinated_operator_profit": uncoordinated_operator_profit,
                "uncoordinated_grid_friendliness": uncoordinated_grid_friendliness,
                "uncoordinated_total_reward": uncoordinated_total_reward
            }
                        
        return {
            "user_satisfaction": user_satisfaction,
            "operator_profit": operator_profit,
            "grid_friendliness": grid_friendliness,
            "total_reward": total_reward
        }

    # <<< ADD NEW HELPER FUNCTION HERE >>>
    def _calculate_charging_probability(self, user, current_hour):
        """Calculates the probability that a user decides to seek charging."""
        current_soc = user.get("soc", 100)
        user_type = user.get("user_type", "commuter")
        charging_preference = user.get("charging_preference", "flexible")
        profile = user.get("profile", "balanced")

        # 检查充电量是否太小，如果太小直接返回非常低的概率
        estimated_charge_amount = 100 - current_soc
        if estimated_charge_amount < 25:
            logger.debug(f"User {user.get('id')} charge amount too small ({estimated_charge_amount:.1f}%), returning minimal probability.")
            return 0.01  # 极低概率

        # 1. Base probability using sigmoid curve
        soc_midpoint = 40  # 降低中点SOC到40%
        soc_steepness = 0.1  # 增加曲线斜率使变化更明显
        
        base_prob = 1 / (1 + math.exp(soc_steepness * (current_soc - soc_midpoint)))
        base_prob = min(0.95, max(0.05, base_prob))  # 限制基础概率范围

        # 对SOC过高的用户，进一步降低概率
        if current_soc > 75: 
            base_prob *= 0.1  # 大幅降低高SOC用户的基础概率
        elif current_soc > 60:
            base_prob *= 0.3  # 降低较高SOC用户的基础概率

        # 2. 根据用户类型调整概率
        type_factor = 0
        if user_type == "taxi":
            type_factor = 0.2  # 降低出租车额外概率
        elif user_type == "delivery":
            type_factor = 0.15  # 降低配送车辆额外概率
        elif user_type == "business":
            type_factor = 0.1  # 降低商务用户额外概率

        # 3. 根据充电偏好调整概率
        preference_factor = 0
        hour = current_hour
        if charging_preference == "evening" and 17 <= hour <= 22:
            preference_factor = 0.2  # 降低时段偏好影响
        elif charging_preference == "night" and (hour <= 5 or hour >= 22):
            preference_factor = 0.2
        elif charging_preference == "day" and 9 <= hour <= 16:
            preference_factor = 0.2
        elif charging_preference == "flexible":
            preference_factor = 0.1  # 降低灵活充电的额外概率

        # 4. 根据用户特征调整概率
        profile_factor = 0
        if profile == "anxious":
            profile_factor = 0.2  # 降低焦虑型用户额外概率
        elif profile == "planner":
            if 25 <= current_soc <= 40:  # 降低规划型用户的充电SOC区间
                profile_factor = 0.15
        elif profile == "economic":
            profile_factor = -0.1  # 保持经济型用户的降低概率

        # 5. SOC紧急充电提升
        emergency_boost = 0
        if current_soc <= 25:  # 降低紧急充电的SOC阈值
            emergency_boost = 0.4 * (1 - current_soc/25)  # 降低紧急提升系数

        # 组合所有因素
        charging_prob = base_prob + type_factor + preference_factor + profile_factor + emergency_boost

        # 最终限制在[0,1]范围内
        charging_prob = min(1.0, max(0.0, charging_prob))

        # 记录调试信息
        logger.debug(f"User {user.get('id')} charging probability calculation:")
        logger.debug(f"  - SOC: {current_soc:.1f}%, Charge amount: {estimated_charge_amount:.1f}%")
        logger.debug(f"  - Base prob: {base_prob:.2f}")
        logger.debug(f"  - Type factor: {type_factor:.2f}")
        logger.debug(f"  - Preference factor: {preference_factor:.2f}")
        logger.debug(f"  - Profile factor: {profile_factor:.2f}")
        logger.debug(f"  - Emergency boost: {emergency_boost:.2f}")
        logger.debug(f"  - Final prob: {charging_prob:.2f}")

        return charging_prob
    # <<< END OF NEW HELPER FUNCTION >>>

    def _update_user_position_along_route(self, user, distance_km):
        """Moves the user along the route by a certain distance. Returns actual distance moved."""
        route = user["route"]
        if not route or len(route) < 2:
            return 0
            
        # 将距离转换为坐标单位
        distance_coord = distance_km / 111  # 粗略转换
        
        # 当前位置
        current_pos = user["current_position"]
        
        # 找到当前位置在路径中的位置
        current_segment = 0
        for i in range(1, len(route)):
            segment_start = route[i-1]
            segment_end = route[i]
            
            # 检查当前位置是否在这个线段上
            # 简单版：如果当前位置接近线段的起点或终点
            if (abs(current_pos["lat"] - segment_start["lat"]) < 0.001 and 
                abs(current_pos["lng"] - segment_start["lng"]) < 0.001):
                current_segment = i-1
                break
            elif (abs(current_pos["lat"] - segment_end["lat"]) < 0.001 and 
                  abs(current_pos["lng"] - segment_end["lng"]) < 0.001):
                current_segment = i
                break
        
        # 从当前段开始移动用户
        remaining_distance = distance_coord
        while remaining_distance > 0 and current_segment < len(route) - 1:
            segment_start = route[current_segment]
            segment_end = route[current_segment + 1]
            
            # 如果用户刚好在段起点
            if (abs(current_pos["lat"] - segment_start["lat"]) < 0.001 and 
                abs(current_pos["lng"] - segment_start["lng"]) < 0.001):
                # 计算段长度
                segment_dx = segment_end["lng"] - segment_start["lng"]
                segment_dy = segment_end["lat"] - segment_start["lat"]
                segment_length = math.sqrt(segment_dx*segment_dx + segment_dy*segment_dy)
                
                # 如果剩余距离足够走完整个段
                if remaining_distance >= segment_length:
                    # 直接移动到段终点
                    current_pos["lat"] = segment_end["lat"]
                    current_pos["lng"] = segment_end["lng"]
                    remaining_distance -= segment_length
                    current_segment += 1
                else:
                    # 移动一部分距离
                    fraction = remaining_distance / segment_length
                    current_pos["lat"] = segment_start["lat"] + segment_dy * fraction
                    current_pos["lng"] = segment_start["lng"] + segment_dx * fraction
                    remaining_distance = 0
            else:
                # 用户在段中间某处，计算到段终点的距离
                dx = segment_end["lng"] - current_pos["lng"]
                dy = segment_end["lat"] - current_pos["lat"]
                distance_to_end = math.sqrt(dx*dx + dy*dy)
                
                # 如果剩余距离足够到达段终点
                if remaining_distance >= distance_to_end:
                    # 直接移动到段终点
                    current_pos["lat"] = segment_end["lat"]
                    current_pos["lng"] = segment_end["lng"]
                    remaining_distance -= distance_to_end
                    current_segment += 1
                else:
                    # 移动一部分距离
                    fraction = remaining_distance / distance_to_end
                    current_pos["lat"] += dy * fraction
                    current_pos["lng"] += dx * fraction
                    remaining_distance = 0
        
        # 如果用户已经到达最后一个点，直接设置位置为终点
        if current_segment >= len(route) - 1:
            current_pos["lat"] = route[-1]["lat"]
            current_pos["lng"] = route[-1]["lng"]
            
        # 根据实际行驶距离消耗电量
        # 不同车型每公里耗电量不同 (kWh/km)
        consumption_rate = 0.0
        if user.get("vehicle_type") == "sedan":
            consumption_rate = 0.15  # 较小型轿车
        elif user.get("vehicle_type") == "suv":
            consumption_rate = 0.22  # SUV
        elif user.get("vehicle_type") == "truck":
            consumption_rate = 0.35  # 卡车
        else:
            consumption_rate = 0.18  # 默认值
            
        # 考虑驾驶风格对能耗的影响
        if user.get("driving_style") == "aggressive":
            consumption_rate *= 1.2  # 激进驾驶增加20%能耗
        elif user.get("driving_style") == "eco":
            consumption_rate *= 0.9  # 经济驾驶减少10%能耗
            
        # 计算能耗 (kWh)
        energy_used = distance_km * consumption_rate
        
        # 计算SOC减少百分比
        battery_capacity = user.get("battery_capacity", 60)  # 默认60kWh
        soc_decrease = (energy_used / battery_capacity) * 100
        
        # 更新SOC和续航里程
        user["soc"] = max(0, user["soc"] - soc_decrease)
        user["current_range"] = user["max_range"] * (user["soc"] / 100)
        
        return distance_km

    # <<< ADD THE MISSING HELPER FUNCTION >>>
    def _get_random_location(self):
        """Generates a random location within the defined map boundaries."""
        # Ensure map_bounds exists and has the expected keys
        if not hasattr(self, 'map_bounds') or not all(k in self.map_bounds for k in ['lat_min', 'lat_max', 'lng_min', 'lng_max']):
            logger.error("Map bounds not properly initialized. Using default fallback region.")
            # Fallback to a default region if bounds are missing
            return {"lat": 30.75, "lng": 114.25} 
            
        try:
            lat = random.uniform(self.map_bounds['lat_min'], self.map_bounds['lat_max'])
            lng = random.uniform(self.map_bounds['lng_min'], self.map_bounds['lng_max'])
            return {"lat": lat, "lng": lng}
        except Exception as e:
            logger.error(f"Error generating random location: {e}. Using default fallback.", exc_info=True)
            return {"lat": 30.75, "lng": 114.25} # Fallback on other errors
    # <<< END OF ADDED HELPER FUNCTION >>>

    # <<< ADD NEW FUNCTION >>>
    def _plan_route_to_destination(self, user_id, destination):
        """规划用户到任意目的地的路线（非充电桩）"""
        if user_id not in self.users:
            logger.error(f"_plan_route_to_destination: User {user_id} not found.")
            return False

        user = self.users[user_id]
        start_pos = user["current_position"]
        end_pos = destination # Destination is already a coordinate dict

        # Check if destination is valid
        if not isinstance(end_pos, dict) or 'lat' not in end_pos or 'lng' not in end_pos:
            logger.error(f"_plan_route_to_destination: Invalid destination format for user {user_id}: {end_pos}")
            return False

        # Clear previous route info
        user["route"] = []
        user["waypoints"] = []
        user["destination"] = end_pos.copy()
        user["target_charger"] = None # Ensure it's not targeting a charger
        user["last_destination_type"] = "random" # Or determine based on context if possible

        # Simple path planning: Straight line with random waypoints
        dx = end_pos["lng"] - start_pos["lng"]
        dy = end_pos["lat"] - start_pos["lat"]
        distance = math.sqrt(dx*dx + dy*dy) * 111 # Approx km

        # Generate waypoints
        num_points = random.randint(2, 4)
        waypoints = []
        for i in range(1, num_points):
            t = i / num_points
            point_lng = start_pos["lng"] + t * dx
            point_lat = start_pos["lat"] + t * dy
            # Add random offset
            perpendicular_dx = -dy
            perpendicular_dy = dx
            perp_len = math.sqrt(perpendicular_dx**2 + perpendicular_dy**2)
            if perp_len > 0:
                perpendicular_dx /= perp_len
                perpendicular_dy /= perp_len
            offset_magnitude = random.uniform(-0.1, 0.1) * distance / 111
            point_lng += perpendicular_dx * offset_magnitude
            point_lat += perpendicular_dy * offset_magnitude
            waypoints.append({"lat": point_lat, "lng": point_lng})

        user["waypoints"] = waypoints
        full_route = [start_pos.copy()] + waypoints + [end_pos.copy()]
        user["route"] = full_route

        # Calculate total distance and time
        total_distance = 0
        for i in range(1, len(full_route)):
            p1 = full_route[i-1]
            p2 = full_route[i]
            segment_dist = math.sqrt((p2["lng"] - p1["lng"])**2 + (p2["lat"] - p1["lat"])**2) * 111
            total_distance += segment_dist

        travel_time_minutes = (total_distance / user.get("travel_speed", 45)) * 60 if user.get("travel_speed", 45) > 0 else float('inf')

        user["time_to_destination"] = travel_time_minutes
        user["traveled_distance"] = 0

        logger.debug(f"Planned route for user {user_id} to random destination {destination}, distance: {total_distance:.2f} km, time: {travel_time_minutes:.1f} min.")
        return True
    # <<< END ADD NEW FUNCTION >>>

class ChargingScheduler:
    def __init__(self, config: Dict[str, Any]):
        # Store relevant parts of the config
        self.config = config
        env_config = config.get("environment", {})
        scheduler_config = config.get("scheduler", {})
        marl_specific_config = scheduler_config.get("marl_config", {})

        # --- Assign algorithm FIRST ---
        self.algorithm = scheduler_config.get("scheduling_algorithm", "rule_based")
        logger.info(f"ChargingScheduler initialized with algorithm: {self.algorithm}")
        # --- End Assign algorithm FIRST ---

        self.grid_id = env_config.get("grid_id", "DEFAULT001")
        self.charger_count = env_config.get("charger_count", 20)
        self.user_count = env_config.get("user_count", 50)

        # Store optimization weights (used by rule_based and coordinated_mas)
        self.optimization_weights = scheduler_config.get("optimization_weights", {
            "user_satisfaction": 0.33,
            "operator_profit": 0.33,
            "grid_friendliness": 0.34
        })

        # Initialize specific systems based on the algorithm
        self.coordinated_mas_system = None
        self.marl_system = None

        if self.algorithm == "coordinated_mas":
            logger.info("Initializing Coordinated MAS subsystem...")
            try:
                self.coordinated_mas_system = MultiAgentSystem()
                # Pass necessary config/weights to the MAS coordinator
                # The MultiAgentSystem itself might need the config too
                self.coordinated_mas_system.config = config
                if hasattr(self.coordinated_mas_system, 'coordinator'):
                    self.coordinated_mas_system.coordinator.set_weights(self.optimization_weights)
                logger.info("Coordinated MAS subsystem initialized.")
            except Exception as e:
                logger.error(f"Failed to initialize Coordinated MAS: {e}", exc_info=True)
                self.algorithm = "rule_based" # Fallback to rule-based
                logger.warning("Falling back to rule_based scheduling due to MAS initialization error.")

        elif self.algorithm == "marl":
            logger.info("Initializing MARL subsystem...")
            try:
                # Initialize MARL system (assuming MARLSystem class exists)
                # It likely needs the MARL-specific config and possibly env details
                self.marl_system = MARLSystem(
                     num_chargers=self.charger_count,
                     action_space_size=marl_specific_config.get("action_space_size", 5), # Example
                     learning_rate=marl_specific_config.get("learning_rate", 0.01),
                     discount_factor=marl_specific_config.get("discount_factor", 0.95),
                     exploration_rate=marl_specific_config.get("exploration_rate", 0.1),
                     q_table_path=marl_specific_config.get("q_table_path", None)
                 )
                logger.info("MARL subsystem initialized.")
            except NameError:
                 logger.error("MARLSystem class not found. MARL scheduling disabled.", exc_info=True)
                 self.algorithm = "rule_based" # Fallback
                 logger.warning("Falling back to rule_based scheduling because MARLSystem class is missing.")
            except Exception as e:
                logger.error(f"Failed to initialize MARL system: {e}", exc_info=True)
                self.algorithm = "rule_based" # Fallback
                logger.warning("Falling back to rule_based scheduling due to MARL initialization error.")

        # No specific initialization needed for rule_based beyond weights

    # Add learn method stub for MARL
    def learn(self, state, actions, rewards, next_state):
         if self.algorithm == "marl" and self.marl_system:
              try:
                   self.marl_system.update_q_tables(state, actions, rewards, next_state)
              except Exception as e:
                   logger.error(f"Error during MARL learning step: {e}", exc_info=True)
         # else: pass # No learning for other algorithms

    # Add load/save Q-table methods for MARL
    def load_q_tables(self):
        if self.algorithm == "marl" and self.marl_system:
            try:
                self.marl_system.load_q_tables()
                logger.info("MARL Q-tables loaded successfully")
            except Exception as e:
                logger.error(f"Error loading MARL Q-tables: {e}", exc_info=True)

    def save_q_tables(self):
        if self.algorithm == "marl" and self.marl_system:
            try:
                self.marl_system.save_q_tables()
                logger.info("MARL Q-tables saved successfully.")
            except Exception as e:
                logger.error(f"Failed to save MARL Q-tables: {e}", exc_info=True)

    def make_scheduling_decision(self, state: Dict[str, Any]) -> Dict[str, str]:
        """
        Make scheduling decisions for charging assignments

        Args:
            state: Current state of the environment

        Returns:
            decisions: Dict mapping user_ids to charger_ids
        """
        decisions = {}
        
        # Validate state
        if not state or not isinstance(state, dict):
            logger.error("make_scheduling_decision received invalid state")
            return decisions
            
        # Choose algorithm based on configuration
        if self.algorithm == "coordinated_mas" and self.coordinated_mas_system:
            # Use coordinated multi-agent system
            try:
                decisions = self.coordinated_mas_system.make_decisions(state)
                logger.info(f"Coordinated MAS made {len(decisions)} assignments")
            except Exception as e:
                logger.error(f"Error in coordinated MAS: {e}", exc_info=True)
                # Fallback to rule-based if MAS fails
                decisions = self._rule_based_scheduling(state)
                
        elif self.algorithm == "marl" and self.marl_system:
            # Use MARL system
            try:
                # 1. Generate action maps for all active chargers *before* agents choose actions
                charger_action_maps = {}
                if state.get("chargers"):
                    for charger in state["chargers"]:
                        charger_id = charger.get("charger_id")
                        if charger_id and charger.get("status") != "failure":
                            action_map, action_size = self._create_dynamic_action_map(charger_id, state)
                            charger_action_maps[charger_id] = {"map": action_map, "size": action_size}

                # 2. Let MARL agents choose numerical actions based on the state
                marl_actions = self.marl_system.choose_actions(state)

                # 3. Convert chosen actions to decisions using the pre-generated maps
                decisions = self._convert_marl_actions_to_decisions(marl_actions, state, charger_action_maps)
                logger.info(f"MARL made {len(decisions)} assignments")
            except Exception as e:
                logger.error(f"Error in MARL decision: {e}", exc_info=True)
                # Fallback to rule-based if MARL fails
                decisions = self._rule_based_scheduling(state)
        
        elif self.algorithm == "uncoordinated":  # 新增无序充电模式
            # 使用无序充电（先到先得，不考虑优化）
            try:
                decisions = self._uncoordinated_charging(state)
                logger.info(f"Uncoordinated charging made {len(decisions)} assignments")
            except Exception as e:
                logger.error(f"Error in uncoordinated charging: {e}", exc_info=True)
                decisions = self._rule_based_scheduling(state)  # 出错时回退到规则算法
                
        else:
            # Default to rule-based
            decisions = self._rule_based_scheduling(state)
            
        logger.info(f"调度决策 ({self.algorithm}): {len(decisions)} 个分配")
        return decisions
        
    def _uncoordinated_charging(self, state):
        """
        无序充电模式：基于先到先得原则，不考虑全局优化
        这种模式模拟现实中无协调的充电行为，作为优化策略的对比基准
        
        Args:
            state: 当前环境状态
            
        Returns:
            decisions: 用户ID到充电桩ID的映射
        """
        decisions = {}
        
        # 安全提取用户和充电桩信息
        users_list = state.get("users", [])
        chargers_list = state.get("chargers", [])
        
        if not isinstance(users_list, list) or not isinstance(chargers_list, list):
            logger.warning("_uncoordinated_charging: Invalid format for users or chargers")
            return decisions
            
        # 将列表转为字典便于处理
        users = {}
        for user_data in users_list:
            if isinstance(user_data, dict) and "user_id" in user_data:
                users[user_data["user_id"]] = user_data
                
        chargers = {}
        for charger_data in chargers_list:
            if isinstance(charger_data, dict) and "charger_id" in charger_data:
                chargers[charger_data["charger_id"]] = charger_data
                
        if not users or not chargers:
            logger.warning("_uncoordinated_charging: No valid users or chargers found")
            return decisions
            
        # 找出需要充电的用户(traveling状态且没有目标充电桩)
        charging_candidates = []
        for user_id, user in users.items():
            if user.get("status") == "traveling" and user.get("target_charger") is None:
                # 用户的SOC越低，焦虑越高，越可能随机选择一个最近的充电桩
                soc = user.get("soc", 100)
                if not isinstance(soc, (int, float)):
                    soc = 100
                
                user_pos = user.get("current_position", {"lat": 0, "lng": 0})
                charging_candidates.append((user_id, user, soc, user_pos))
                
        if not charging_candidates:
            return decisions
            
        # 给充电桩建立队列状态
        # 无序充电模式下，用户倾向于选择最近或者排队最短的充电桩
        charger_queue_info = {}
        for charger_id, charger in chargers.items():
            if charger.get("status") != "failure":
                queue_length = len(charger.get("queue", []))
                position = charger.get("position", {"lat": 0, "lng": 0})
                is_occupied = charger.get("status") == "occupied"
                
                # 快充桩更受欢迎
                is_fast = charger.get("type") == "fast"
                
                charger_queue_info[charger_id] = {
                    "queue_length": queue_length,
                    "position": position,
                    "is_occupied": is_occupied,
                    "is_fast": is_fast
                }
                
        # 模拟非协调的选择行为：用户会随机选择相对近的或排队相对短的充电桩
        for user_id, user, soc, user_pos in charging_candidates:
            # 充电桩已满，无法分配更多
            if not charger_queue_info:
                break
                
            # 计算用户到所有可用充电桩的距离
            charger_distances = []
            for charger_id, info in charger_queue_info.items():
                charger_pos = info["position"]
                queue_length = info["queue_length"]
                is_occupied = info["is_occupied"]
                is_fast = info["is_fast"]
                
                # 计算距离
                distance = self._calculate_distance(user_pos, charger_pos)
                
                # 将距离与排队情况结合成一个吸引力分数
                # SOC越低，用户越倾向于选择近的充电桩，而不考虑排队长度
                if soc < 20:  # 电量极低时，距离是最主要因素
                    attraction_score = -distance  # 负距离，越近越好
                else:
                    # 平衡距离和排队长度
                    # 快充桩有加成
                    fast_bonus = 1.3 if is_fast else 1.0
                    # 距离和排队长度的加权和
                    attraction_score = -(distance * 0.7 + queue_length * 5 * 0.3) * fast_bonus
                
                # 如果已满(队列长度>=3)，则跳过
                if is_occupied and queue_length >= 3:
                    continue
                    
                charger_distances.append((charger_id, attraction_score))
                
            if not charger_distances:
                continue  # 没有合适的充电桩
                
            # 排序获取前三个最有吸引力的充电桩
            charger_distances.sort(key=lambda x: x[1], reverse=True)  # 降序排序，吸引力最高的在前
            
            # 从前三个中随机选择一个，模拟现实中的随机性和不完全信息
            top_choices = charger_distances[:min(3, len(charger_distances))]
            
            # 根据SOC确定随机性：SOC越低，越可能选择最近的(第一个)
            if soc < 15 and len(top_choices) > 0:
                # 电量极低时几乎总是选择最近的
                selected_charger_id = top_choices[0][0]
            elif soc < 30 and len(top_choices) > 0:
                # 电量较低时有80%的概率选择最近的，20%随机
                if random.random() < 0.8:
                    selected_charger_id = top_choices[0][0]
                else:
                        weights = [0.8, 0.15, 0.05][:len(top_choices)]
                        selected_charger_id = random.choices(
                            [c[0] for c in top_choices], 
                            weights=weights, 
                            k=1
                        )[0]
            else:
                    # 电量正常时，在前三个中有更多随机性
                    weights = [0.5, 0.3, 0.2][:len(top_choices)]
                    selected_charger_id = random.choices(
                        [c[0] for c in top_choices], 
                        weights=weights, 
                        k=1
                    )[0]
            
            # 分配充电桩
            decisions[user_id] = selected_charger_id
            
            # 更新该充电桩的队列信息
            info = charger_queue_info[selected_charger_id]
            info["queue_length"] += 1
            
            # 如果队列已满，从可选列表中移除
            if info["is_occupied"] and info["queue_length"] >= 3:
                del charger_queue_info[selected_charger_id]
                
        return decisions

    # --- Helper to create dynamic action map (needed for MARL conversion) ---
    def _create_dynamic_action_map(self, charger_id, state):
        """
        Creates a mapping from action index (0 to N-1) to the actual action ('idle' or user_id)
        that is valid for the agent in the current step. Revised for better candidate selection.
        Index 0 is always 'idle'. Subsequent indices map to potential user IDs.
        Uses action_space_size from the MARL config.
        """
        # Get action space size from the MARL config
        marl_config = self.config.get("scheduler", {}).get("marl_config", {})
        action_space_size = marl_config.get("action_space_size", 6) # Default to 6 if not found
        max_potential_users = action_space_size - 1 # Number of users to map (action 0 is idle)

        # --- CONFIGURABLE PARAMETERS for candidate selection ---
        # Reasonable distance threshold (degrees squared), e.g., 0.15^2 ≈ 20km radius
        MAX_DISTANCE_SQ = marl_config.get("marl_candidate_max_dist_sq", 0.15**2)
        # Weights for priority scoring
        W_SOC = marl_config.get("marl_priority_w_soc", 0.5)       # Weight for low SOC
        W_DIST = marl_config.get("marl_priority_w_dist", 0.4)    # Weight for proximity
        W_URGENCY = marl_config.get("marl_priority_w_urgency", 0.1) # Weight for urgency (how far below threshold)
        # --- END CONFIGURABLE PARAMETERS ---

        logger.debug(f"Creating action map for charger {charger_id}: max_dist_sq={MAX_DISTANCE_SQ}, action_size={action_space_size}")

        action_map = {0: 'idle'} # Action 0 is always idle
        chargers = state.get('chargers', [])
        users = state.get('users', [])
        # Get the full grid status for context (e.g., price)
        grid_status = state.get('grid_status', {})
        
        charger = next((c for c in chargers if c.get('charger_id') == charger_id), None)

        if not charger or charger.get('status') == 'failure':
            logger.debug(f"Charger {charger_id} not found or in failure, returning only idle action")
            return action_map, action_space_size # Only 'idle' is possible

        potential_users = []
        charger_pos = charger.get('position', {'lat': 0, 'lng': 0})
        
        for user in users:
            user_id = user.get('user_id')
            soc = user.get('soc', 100)
            status = user.get('status', 'unknown')
            user_profile = user.get('user_profile', 'flexible')
            # Check if user explicitly needs a charging decision (assuming this flag exists/is set)
            # needs_charge_decision = user.get('needs_charge_decision', False)

            # --- Revised Filtering Logic ---
            is_actively_seeking = False
            charge_threshold = 30 # Base threshold
            # Adjust threshold based on profile (example)
            if user_profile == 'anxious': charge_threshold = 45
            elif user_profile == 'economic': charge_threshold = 20

            is_low_soc = soc < charge_threshold

            # Condition 1: Traveling without a target charger (actively looking)
            if status == 'traveling' and user.get('target_charger') is None:
                 is_actively_seeking = True
            # Condition 2: Idle, low SOC, and flagged as needing charge (more explicit)
            # elif status == 'idle' and is_low_soc and needs_charge_decision:
            #    is_actively_seeking = True
            # Condition 3: Simpler alternative - Idle and low SOC (less explicit but broader)
            elif status == 'idle' and is_low_soc:
                 is_actively_seeking = True # Assume idle + low SOC implies seeking

            if not is_actively_seeking:
                continue # Skip users not actively looking for charge
            # --- End Revised Filtering Logic ---

                # Check distance
                user_pos = user.get('current_position', {'lat': -999, 'lng': -999})
                if isinstance(user_pos.get('lat'), (int, float)) and isinstance(user_pos.get('lng'), (int, float)):
                    dist_sq = (user_pos['lat'] - charger_pos['lat'])**2 + (user_pos['lng'] - charger_pos['lng'])**2
                    
                    if dist_sq < MAX_DISTANCE_SQ:
                        distance = math.sqrt(dist_sq) * 111 # Approx km
                        # Calculate urgency (0 to 1, higher is more urgent)
                        urgency = max(0, (charge_threshold - soc)) / charge_threshold if charge_threshold > 0 else 0

                    # --- Revised Priority Score ---
                    # Normalize distance (0=close, 1=far) using MAX_DISTANCE_SQ
                    normalized_distance = min(1.0, math.sqrt(dist_sq) / math.sqrt(MAX_DISTANCE_SQ)) if MAX_DISTANCE_SQ > 0 else 0
                    normalized_soc = soc / 100.0

                    priority_score = (
                        W_SOC * (1.0 - normalized_soc) +    # Low SOC contributes positively
                        W_DIST * (1.0 - normalized_distance) + # Low distance contributes positively
                        W_URGENCY * urgency
                    )
                    # --- End Revised Priority Score ---

                    potential_users.append({
                            'id': user_id, 
                            'soc': soc, 
                        'dist_km': distance,
                            'status': status,
                        'priority': priority_score
                    })
                    logger.debug(f"User {user_id} (status={status}, SOC:{soc:.1f}) potential candidate for {charger_id}. Dist: {distance:.1f}km, Priority: {priority_score:.3f}")
                # else: logger.debug(f"User {user_id} too far ({math.sqrt(dist_sq)*111:.1f}km)")
            # else: logger.debug(f"Skipping user {user_id} due to invalid coords")

        # Sort potential users by the new PRIORITY score (higher is better)
        potential_users.sort(key=lambda u: -u['priority'])
        logger.debug(f"Found and sorted {len(potential_users)} potential users for charger {charger_id}. Top 5: {potential_users[:5]}")

        # Map the top N-1 *highest priority* potential users to action indices 1 to N-1
        assigned_users_count = 0
        for i, user_info in enumerate(potential_users):
             if assigned_users_count < max_potential_users:
                  action_map[i + 1] = user_info['id']
                  assigned_users_count += 1
                  # logger.debug(f"Mapped user {user_info['id']} to action {i+1} (Priority: {user_info['priority']:.3f})")
             else:
                  break # Stop once we've filled the action space slots

        logger.debug(f"Final action map for charger {charger_id}: {action_map}")
        return action_map, action_space_size

    def _convert_marl_actions_to_decisions(self, agent_actions, state, charger_action_maps):
        """
        将MARL智能体选择的动作转换为充电分配决策
        
        Args:
            agent_actions: 充电站智能体的动作字典 {charger_id: action_index}
            state: 当前环境状态
            charger_action_maps: 预生成的动作映射字典 {charger_id: {"map": action_map}}
            
        Returns:
            decisions: 字典，将用户ID映射到充电站ID
        """
        decisions = {}
        assigned_users = set()  # 跟踪已分配的用户以防止重复
        
        # 确保agent_actions是字典类型
        if not isinstance(agent_actions, dict):
            logger.error(f"_convert_marl_actions_to_decisions接收到无效的agent_actions类型: {type(agent_actions)}")
            return {}
            
        logger.debug(f"转换MARL智能体动作为决策: {agent_actions}")
        idle_count = sum(1 for action in agent_actions.values() if action == 0)
        active_count = len(agent_actions) - idle_count
        logger.debug(f"动作统计: 总计{len(agent_actions)}个, 空闲{idle_count}个, 活跃{active_count}个")
        
        # ==== 新增调试代码 ====
        potential_users = []
        for user in state.get('users', []):
            if user.get('status') == 'traveling' and user.get('soc', 100) < 50:
                potential_users.append((user.get('user_id'), user.get('soc')))
        logger.info(f"状态中的潜在用户: {len(potential_users)}个, 样本: {potential_users[:5]}")
        # ==== 结束调试代码 ====
        
        # 遍历每个充电站智能体选择的动作
        for charger_id, action_index in agent_actions.items():
            # Action 0 总是表示'idle'(不分配)
            if action_index == 0:
                # logger.debug(f"充电站 {charger_id} 选择了'idle'动作 (0)")
                continue
                
            # --- 使用预生成的动作映射 --- 
            map_data = charger_action_maps.get(charger_id)
            if not map_data:
                logger.warning(f"未找到充电站 {charger_id} 的预生成动作映射。无法转换动作 {action_index}。跳过。")
                continue
            action_map = map_data.get("map")
            if not action_map:
                logger.warning(f"充电站 {charger_id} 的映射数据无效。跳过。")
                continue
                
            # 在提供的映射中查找对应于所选action_index的user_id
            user_id_to_assign = action_map.get(action_index)
            
            if user_id_to_assign and user_id_to_assign != 'idle':
                # 查找用户对象以获取更多信息
                users = state.get("users", [])
                user = next((u for u in users if u.get("user_id") == user_id_to_assign), None)
                
                # 检查这个用户是否已经被另一个充电站分配
                if user_id_to_assign not in assigned_users:
                    # 如果用户处于traveling状态并且SOC较低，强制分配
                    force_assignment = False
                    if user:
                        user_soc = user.get("soc", 100)
                        user_status = user.get("status", "")
                        if user_status == "traveling" and user_soc < 50:
                            force_assignment = True
                            logger.info(f"强制分配traveling用户 {user_id_to_assign} (SOC: {user_soc}%) 到充电站 {charger_id}")
                            
                    decisions[user_id_to_assign] = charger_id
                    assigned_users.add(user_id_to_assign)
                    logger.debug(f"MARL决策: 分配用户 {user_id_to_assign} 到充电站 {charger_id} (动作索引 {action_index})")
                else:
                    # 冲突: 用户已分配。记录日志。
                    logger.warning(f"MARL冲突: 用户 {user_id_to_assign} 已被分配。充电站 {charger_id} 也选择了该用户 (动作索引 {action_index})。忽略第二次分配。")
            else:
                # 所选动作索引可能不对应任何用户，如果映射生成和动作选择之间候选者略有变化，或者动作空间大小不匹配
                logger.debug(f"充电站 {charger_id} 选择了动作索引 {action_index}，但在预生成的action_map中未找到有效用户: {action_map}")
                
        # 如果assignments为空，且有大量非idle动作，强制分配一些用户
        if not decisions and active_count > 20:
            logger.warning("MARL转换未产生分配，但有大量活跃动作。尝试应急分配...")
            # 寻找所有低SOC的traveling用户
            emergency_users = []
            for user in state.get("users", []):
                if user.get("status") == "traveling" and user.get("soc", 100) < 40:
                    emergency_users.append(user)
                    
            # 对用户按SOC排序
            emergency_users.sort(key=lambda u: u.get("soc", 100))
            
            # 寻找可用的充电站
            available_chargers = []
            for charger in state.get("chargers", []):
                if charger.get("status") == "available":
                    available_chargers.append(charger)
                    
            # 尝试匹配前5个紧急用户和任意充电站
            emergency_count = 0
            for user in emergency_users[:5]:
                if not available_chargers:
                    break
                    
                user_id = user.get("user_id")
                if user_id not in assigned_users:
                    # 随机选择一个充电站
                    charger = random.choice(available_chargers)
                    charger_id = charger.get("charger_id")
                    
                    decisions[user_id] = charger_id
                    assigned_users.add(user_id)
                    
                    # 强制设置用户需求充电
                    user["needs_charge_decision"] = True
                    if user.get("time_to_destination", 0) > 5:
                        user["time_to_destination"] = 5  # 加速到达
                        
                    logger.info(f"紧急分配: 用户 {user_id} (SOC: {user.get('soc')}%) 到充电站 {charger_id}")
                    emergency_count += 1
                    
            if emergency_count > 0:
                logger.info(f"应急分配成功: {emergency_count}个用户被分配")
        
        if not decisions:
            logger.warning("MARL转换未产生任何分配。")
        else:
            logger.info(f"MARL决策: {decisions}")
        return decisions

    def _rule_based_scheduling(self, state):
        """
        Implement a rule-based scheduling strategy that balances:
        - User satisfaction (minimizing wait times and travel distance)
        - Operator profit (maximizing utilization and revenue)
        - Grid friendliness (avoiding peak hours, utilizing renewables)
        
        Args:
            state: Current environment state
            
        Returns:
            decisions: Dict mapping user_ids to charger_ids
        """
        decisions = {}

        # 获取当前时间、负载等信息
        timestamp = state.get("timestamp")
        grid_load = state.get("grid_load", 50)
        renewable_ratio = state.get("renewable_ratio", 0)
        
        if not timestamp:
            return decisions

        try:
            current_dt = datetime.fromisoformat(timestamp)
            current_hour = current_dt.hour
        except:
            current_hour = 12  # 默认中午
        
        # 获取用户和充电桩信息
        users = state.get("users", [])
        chargers = state.get("chargers", [])

        if not users or not chargers:
             return decisions
        
        # 为提高效率，将充电桩转换为字典
        charger_dict = {c["charger_id"]: c for c in chargers if "charger_id" in c}
        
        # 确定充电桩可接受的最大队列长度 - 动态调整
        # 高峰时段允许更少排队，低谷时段更多排队（促进填谷削峰）
        peak_hours = [9, 10, 11, 12, 13, 14, 15, 16, 19, 20, 21]  # 与电网友好度保持一致
        valley_hours = [0, 1, 2, 3, 4, 5, 23]  # 与电网友好度保持一致
        
        if current_hour in peak_hours:
            max_queue_len = 3  # 高峰期减少队列长度，抑制用电高峰
        elif current_hour in valley_hours:
            max_queue_len = 12  # 低谷期大幅增加队列长度，鼓励低谷充电
        else:
            max_queue_len = 6  # 平常时段适中队列
        
        # 获取基础权重配置
        base_weights = {
            "user_satisfaction": self.config.get("user_satisfaction_weight", 0.25),
            "operator_profit": self.config.get("operator_profit_weight", 0.25),
            "grid_friendliness": self.config.get("grid_friendliness_weight", 0.5)  # 增加电网友好度权重
        }
        
        # 根据时间段动态调整权重
        weights = base_weights.copy()
        
        # 高峰期增加电网友好度权重，降低用户满意度权重
        if current_hour in peak_hours:
            grid_boost = min(0.3, grid_load / 200)  # 根据负载调整增量，最大0.3
            weights["grid_friendliness"] += grid_boost
            weights["user_satisfaction"] = max(0.15, weights["user_satisfaction"] - grid_boost/2)
            weights["operator_profit"] = max(0.15, weights["operator_profit"] - grid_boost/2)
        
        # 低谷期适当降低电网友好度权重，增加运营商利润权重（鼓励多充电）
        elif current_hour in valley_hours:
            weights["grid_friendliness"] = max(0.3, weights["grid_friendliness"] - 0.15)
            weights["operator_profit"] += 0.1
            weights["user_satisfaction"] += 0.05
        
        # 归一化权重
        total = sum(weights.values())
        for key in weights:
            weights[key] /= total
        
        logger.info(f"Adjusted weights: User={weights['user_satisfaction']:.2f}, "
                   f"Profit={weights['operator_profit']:.2f}, Grid={weights['grid_friendliness']:.2f}")
        
        # 创建候选用户列表 - 需要充电且未在充电或等待的用户
        candidate_users = []
        for user in users:
            user_id = user.get("user_id")
            status = user.get("status", "")
            soc = user.get("soc", 100)
            
            if not user_id:
                continue
                
            # 首先排除充电量太小的用户
            estimated_charge_amount = 100 - soc  # 假设充满电的情况
            if estimated_charge_amount < 25:  # 如果充电量小于25%，直接跳过
                logger.debug(f"Scheduler skipping user {user_id} with only {estimated_charge_amount:.1f}% potential charge.")
                continue
                
            # 优先考虑已经明确表示需要充电的用户
            needs_charge = user.get("needs_charge_decision", False)
            
            # 针对不同用户设置不同的SOC阈值 - 更智能地判断充电需求
            if status not in ["charging", "waiting"]:
                # SOC过高的用户不参与调度
                if soc > 75 and not needs_charge:  # 除非明确需要充电，SOC>75的用户不参与调度
                    continue
                
                # 根据用户类型和时间判断SOC阈值
                user_type = user.get("user_type", "private")
                user_profile = user.get("user_profile", "normal")
                
                # 基础阈值
                threshold = 25  # 默认私家车25%以下充电
                
                # 根据用户类型调整
                if user_type == "taxi" or user_type == "ride_hailing":
                    threshold = 35  # 出租车/网约车需要更高SOC
                elif user_type == "logistics":
                    threshold = 30  # 物流车辆适中
                
                # 根据用户特性调整
                if user_profile == "anxious":
                    threshold += 10  # 焦虑用户更早充电
                elif user_profile == "economic":
                    threshold -= 5   # 经济型用户更晚充电
                
                # 时间因素 - 峰谷充电调整
                if current_hour in peak_hours:
                    threshold -= 5   # 高峰期提高充电门槛
                elif current_hour in valley_hours:
                    threshold += 10  # 低谷期降低充电门槛，鼓励低谷充电
                
                # 最终阈值限制在10-50之间
                threshold = max(10, min(50, threshold))
                
                # 两种情况下将用户加入候选列表:
                # 1. 用户明确表示需要充电 (needs_charge_decision=True)
                # 2. 用户SOC低于阈值，但不要太高的SOC
                if needs_charge or (soc <= threshold and soc <= 75):
                    # 排除充电量过少的用户
                    estimated_charge_amount = 95 - soc  # 充电至95%的充电量
                    if estimated_charge_amount < 25:  # 充电量小于25%不参与调度
                        logger.debug(f"Scheduler skipping user {user_id} with small charge amount {estimated_charge_amount:.1f}%")
                        continue
                    
                    # 计算充电紧迫性评分 - 明确需要充电的用户紧迫性更高
                    base_urgency = (threshold - soc) / threshold if threshold > 0 else 0
                    # 明确需要充电的用户额外加分
                    urgency_bonus = 0.3 if needs_charge else 0
                    urgency = min(1.0, base_urgency + urgency_bonus)
                    
                    # 将用户添加到候选列表，包含需要充电的标志
                    candidate_users.append((user_id, user, urgency, needs_charge))
        
        # 排序逻辑:
        # 1. 首先按照明确需要充电的标志降序排序
        # 2. 其次按照紧迫度降序排序
        candidate_users.sort(key=lambda x: (-int(x[3]), -x[2]))
        
        logger.info(f"Found {len(candidate_users)} candidate users for charging, "
                   f"{sum(1 for u in candidate_users if u[3])} explicitly need charging.")
        
        # 计算每个充电桩的当前负载/队列情况
        charger_loads = {}
        for charger_id, charger in charger_dict.items():
            # 跳过故障充电桩
            if charger.get("status") == "failure":
                continue
                
            # 当前队列长度
            queue_len = len(charger.get("queue", []))
            
            # 已经在充电的话，算作队列+1
            if charger.get("status") == "occupied":
                queue_len += 1
                
            charger_loads[charger_id] = queue_len
        
        # 为每个候选用户找最佳充电桩
        for user_id, user, urgency, needs_charge in candidate_users:
            best_charger_id = None
            best_score = float('-inf')

            # 获取用户位置
            user_pos = user.get("current_position", {"lat": 0, "lng": 0})
            
            # 创建可用充电桩列表
            available_chargers = []
            for charger_id, charger in charger_dict.items():
                # 跳过故障充电桩
                if charger.get("status") == "failure":
                    continue
                    
                # 跳过队列已满的充电桩
                if charger_loads.get(charger_id, 0) >= max_queue_len:
                    continue
                
                # 计算用户到充电桩的距离
                charger_pos = charger.get("position", {"lat": 0, "lng": 0})
                distance = self._calculate_distance(user_pos, charger_pos)
                
                # 将可用充电桩添加到列表
                available_chargers.append((charger_id, charger, distance))
            
            # 对可用充电桩进行排序（按距离）
            available_chargers.sort(key=lambda x: x[2])
            
            # 为了提高效率，只考虑最近的10个充电桩
            for charger_id, charger, distance in available_chargers[:10]:
                # 计算用户满意度分数（距离+等待时间）
                user_score = self._calculate_user_satisfaction(user, charger, distance)
                
                # 计算运营商利润分数
                profit_score = self._calculate_operator_profit(user, charger, state)
                
                # 计算电网友好度分数
                grid_score = self._calculate_grid_friendliness(charger, state)
                
                # 加权组合分数
                # 额外：根据紧急程度和峰谷时段调整权重
                adjusted_weights = weights.copy()
                
                # 电网友好度必须影响所有决策
                if grid_score < -0.5:  # 如果电网友好度非常差
                    adjusted_weights["grid_friendliness"] = min(0.8, adjusted_weights["grid_friendliness"] * 1.5)  # 进一步增强电网影响
                
                # 只有在真正紧急的情况下才提高用户满意度权重
                if urgency > 0.9 and user.get("soc", 100) < 15:  # 非常紧急且SOC很低
                    adjusted_weights["user_satisfaction"] = min(0.6, adjusted_weights["user_satisfaction"] * 1.5)
                
                # 归一化调整后的权重
                total = sum(adjusted_weights.values())
                for key in adjusted_weights:
                    adjusted_weights[key] /= total

                # 智能调整权重
                combined_score = (
                    user_score * adjusted_weights["user_satisfaction"] +
                    profit_score * adjusted_weights["operator_profit"] +
                    grid_score * adjusted_weights["grid_friendliness"]
                )

                # 应用队列长度惩罚
                current_queue_len = charger_loads.get(charger_id, 0)
                # 惩罚系数可以根据需要调整，队列越长惩罚越大
                # 例如，每辆排队的车减少0.05分，可以加入非线性惩罚
                queue_penalty_factor = 0.05
                queue_penalty = current_queue_len * queue_penalty_factor
                penalized_score = combined_score - queue_penalty
                logger.debug(f"Charger {charger_id} for user {user_id}: User={user_score:.2f}, Profit={profit_score:.2f}, Grid={grid_score:.2f} -> Combined={combined_score:.2f}, Queue={current_queue_len}, Penalty={queue_penalty:.2f} -> Final={penalized_score:.2f}")

                # 比较分数并更新最佳充电桩
                if penalized_score > best_score:
                    best_score = penalized_score
                    best_charger_id = charger_id
            
            # 分配最佳充电桩
            if best_charger_id:
                decisions[user_id] = best_charger_id
                # 更新充电桩负载计数
                charger_loads[best_charger_id] = charger_loads.get(best_charger_id, 0) + 1
                logger.debug(f"Assigned user {user_id} to charger {best_charger_id} with score {best_score:.2f}")
            else:
                logger.warning(f"Could not find suitable charger for user {user_id}")
        
        logger.info(f"Made {len(decisions)} charging assignments out of {len(candidate_users)} candidates")
        return decisions
    
    def _calculate_distance(self, pos1, pos2):
        """Calculate distance between two positions"""
        # Simple Euclidean distance
        return math.sqrt((pos1["lat"] - pos2["lat"])**2 + 
                         (pos1["lng"] - pos2["lng"])**2) * 111  # Convert to km (rough approximation)
    
    def _calculate_user_satisfaction(self, user, charger, distance):
        """
        计算用户满意度指标
        考虑因素：等待时间，距离，充电速度匹配等
        
        Args:
            user: 用户数据
            charger: 充电桩数据
            distance: 用户到充电桩的距离(km)
            
        Returns:
            用户满意度评分 [-1,1]
        """
        # 1. 距离因素 - 距离越远，满意度越低
        # 使用非线性函数将距离映射到[-0.5, 0.5]范围
        if distance < 2:  # 2km以内，高满意度
            distance_score = 0.5 - distance * 0.1  # 0.5到0.3线性降低
        elif distance < 5:  # 2-5km，中等满意度
            distance_score = 0.3 - (distance - 2) * 0.1  # 0.3到0线性降低
        elif distance < 10:  # 5-10km，较低满意度
            distance_score = 0 - (distance - 5) * 0.05  # 0到-0.25线性降低
        else:  # 10km以上，低满意度
            distance_score = -0.25 - (distance - 10) * 0.025  # -0.25到-0.5线性降低
            distance_score = max(-0.5, distance_score)  # 最低限制在-0.5
        
        # 2. 等待时间因素 - 队列越长，满意度越低
        queue_length = len(charger.get("queue", []))
        
        # 已经在充电的话，算作队列+1
        if charger.get("status") == "occupied":
            queue_length += 1
            
        # 根据队列长度计算等待时间评分
        if queue_length == 0:  # 无需等待
            wait_score = 0.5
        elif queue_length <= 2:  # 短队列
            wait_score = 0.3
        elif queue_length <= 5:  # 中等队列
            wait_score = 0.1
        elif queue_length <= 8:  # 较长队列
            wait_score = -0.1
        else:  # 非常长的队列
            wait_score = -0.3
            
        # 3. 充电速度匹配因素 - 充电速度满足用户需求
        charger_power = charger.get("max_power", 50)  # kW
        
        # 基于用户类型和SOC计算需要的充电速度
        user_type = user.get("user_type", "private")
        user_soc = user.get("soc", 50)
        urgency = max(0, (40 - user_soc) / 40) if user_soc < 40 else 0  # 低SOC意味着高紧急度
        
        # 计算用户期望的最小充电功率
        expected_power = 0
        if user_type in ["taxi", "ride_hailing"]:  # 商业用户希望快速充电
            expected_power = 50 + urgency * 50  # 50-100kW
        elif user_type == "logistics":  # 物流车辆
            expected_power = 30 + urgency * 50  # 30-80kW
        else:  # 普通用户
            expected_power = 20 + urgency * 30  # 20-50kW
            
        # 计算充电功率满意度
        power_ratio = charger_power / expected_power if expected_power > 0 else 1
        
        if power_ratio >= 1.5:  # 远超预期
            power_score = 0.4
        elif power_ratio >= 1:  # 满足或超过预期
            power_score = 0.3
        elif power_ratio >= 0.7:  # 略低于预期
            power_score = 0.1
        elif power_ratio >= 0.5:  # 明显低于预期
            power_score = -0.1
        else:  # 远低于预期
            power_score = -0.2
            
        # 4. 充电费率因素 - 费率越高，满意度越低
        charging_rate = charger.get("charging_rate", 1.0)  # 默认1.0元/kWh
        
        # 获取用户价格敏感度
        user_profile = user.get("user_profile", "normal")
        price_sensitivity = 1.0  # 默认敏感度
        
        if user_profile == "economic":
            price_sensitivity = 1.5  # 经济型用户更敏感
        elif user_profile == "premium":
            price_sensitivity = 0.6  # 高端用户不太敏感
        elif user_profile == "anxious":
            price_sensitivity = 0.8  # 焦虑型用户更关注充电本身
            
        # 根据充电费率计算价格评分
        reference_rate = 1.0  # 参考费率
        price_factor = (reference_rate - charging_rate) / reference_rate * price_sensitivity
        price_score = max(-0.3, min(0.3, price_factor * 0.5))  # 限制在[-0.3, 0.3]
        
        # 5. 综合服务设施 - 充电站配套设施越好，满意度越高
        amenities_score = 0
        if charger.get("has_restroom", False):
            amenities_score += 0.05
        if charger.get("has_shop", False):
            amenities_score += 0.05
        if charger.get("has_wifi", False):
            amenities_score += 0.03
        if charger.get("has_restaurant", False):
            amenities_score += 0.07
            
        # 6. 紧急情况的特殊处理 - SOC非常低时，距离和等待时间权重增加
        # 计算紧急系数
        emergency_factor = 1.0
        if user_soc < 15:  # SOC非常低
            emergency_factor = 1.5
        elif user_soc < 25:  # SOC较低
            emergency_factor = 1.2
            
        # 计算最终满意度评分
        # 距离和等待时间是最重要的因素，特别是在紧急情况下
        satisfaction = (
            distance_score * 0.35 * emergency_factor +  # 距离因素
            wait_score * 0.25 * emergency_factor +      # 等待时间因素
            power_score * 0.15 +                        # 充电功率因素
            price_score * 0.15 +                        # 价格因素
            amenities_score * 0.1                       # 设施因素
        )
        
        # 确保满意度在[-1,1]范围内，且紧急情况下不会太低
        if emergency_factor > 1.2 and satisfaction < -0.5:
            satisfaction = max(-0.5, satisfaction * 0.8)  # 紧急情况下降低负面影响
            
        satisfaction = max(-1.0, min(1.0, satisfaction))
        
        # 记录调试信息
        logger.debug(f"User satisfaction calculation for user {user.get('user_id')} and charger {charger.get('charger_id')}:")
        logger.debug(f"  - Distance: {distance:.1f}km, Score: {distance_score:.2f}")
        logger.debug(f"  - Queue length: {queue_length}, Wait score: {wait_score:.2f}")
        logger.debug(f"  - Power ratio: {power_ratio:.1f}, Power score: {power_score:.2f}")
        logger.debug(f"  - Price sensitivity: {price_sensitivity:.1f}, Price score: {price_score:.2f}")
        logger.debug(f"  - Amenities score: {amenities_score:.2f}")
        logger.debug(f"  - Emergency factor: {emergency_factor:.1f}")
        logger.debug(f"  - Final satisfaction: {satisfaction:.2f}")
        
        return satisfaction
    
    def _calculate_operator_profit(self, user, charger, state):
        """
        计算运营商利润评分，考虑多种收益和成本因素
        返回值范围：-1到1，值越高代表利润越高
        
        考虑因素:
        1. 电价和充电费率（峰谷时段不同）
        2. 充电桩利用率和吞吐量
        3. 不同充电类型的成本差异
        4. 充电量与收入的关系
        5. 潜在长期收益（客户忠诚度）
        """
        # 安全获取数据
        timestamp_str = state.get("timestamp", datetime.now().isoformat())
        try:
            timestamp = datetime.fromisoformat(timestamp_str)
            hour = timestamp.hour
        except (ValueError, TypeError):
            hour = datetime.now().hour
            
        grid_status = state.get("grid_status", {})
        current_grid_load = grid_status.get("grid_load", 50)  # 当前电网负载百分比
        peak_hours = grid_status.get("peak_hours", [7, 8, 9, 10, 18, 19, 20, 21])
        valley_hours = grid_status.get("valley_hours", [0, 1, 2, 3, 4, 5])

        # 用户充电需求
        user_battery_capacity = user.get("battery_capacity", 60)  # kWh
        user_soc = user.get("soc", 50)  # 当前电量百分比
        charging_need = user_battery_capacity * (1 - user_soc / 100)  # 需要充电的度数
        user_profile = user.get("user_profile", "normal")
        
        # 充电桩特性
        charger_type = charger.get("type", "normal")
        queue_length = len(charger.get("queue", []))
        is_occupied = charger.get("status") == "occupied"
        
        # 1. 基础价格与成本
        base_price = grid_status.get("current_price", 0.85)  # 元/kWh
        base_cost = base_price * 0.7  # 简化：成本是电价的70%
        
        # 根据时段调整价格和成本
        time_multiplier = 1.0
        if hour in peak_hours:
            time_multiplier = 1.2  # 高峰时段高价格，但成本也高
        elif hour in valley_hours:
            time_multiplier = 0.8  # 低谷时段低价格，成本也低

        # 根据电网负载调整成本
        # 电网负载高时，获取电力成本更高，用电成本上升
        grid_load_cost_factor = 1.0 + max(0, (current_grid_load - 70) / 100)  # 负载超过70%时成本开始上升
        
        # 充电桩类型调整
        charger_price_multiplier = 1.0
        charger_cost_multiplier = 1.0
        if charger_type == "fast":
            charger_price_multiplier = 1.15  # 快充更贵
            charger_cost_multiplier = 1.2  # 快充建设和维护成本更高
        
        # 2. 计算收入和成本
        charge_price = base_price * time_multiplier * charger_price_multiplier
        charge_cost = base_cost * time_multiplier * charger_cost_multiplier * grid_load_cost_factor
        
        expected_revenue = charging_need * charge_price
        expected_cost = charging_need * charge_cost
        expected_profit = expected_revenue - expected_cost
        
        # 3. 考虑充电桩利用率
        utilization_bonus = 0
        
        # 已有队列的充电桩更有价值（体现持续使用价值）
        if is_occupied:
            if queue_length == 0:  # 有人充电但没有等待队列
                utilization_bonus = 0.1
            elif queue_length == 1:  # 有1人等待
                utilization_bonus = 0.05  # 适当的等待队列是好的
            else:  # 等待人数>=2
                utilization_bonus = -0.05  # 太多人等待可能降低长期满意度
        
        # 4. 用户类型和忠诚度考虑
        loyalty_potential = 0
        if user_profile == "anxious":
            loyalty_potential = 0.05  # 焦虑用户如果得到好服务，更可能成为回头客
        elif user_profile == "economic":
            loyalty_potential = 0.15 if hour in valley_hours else -0.05  # 经济型用户在低谷时段充电更可能成为忠诚客户
        
        # 5. 综合利润评分计算
        # 基础利润分数
        profit_score = 0
        
        # 避免除以零或负数
        max_theoretical_profit = user_battery_capacity * base_price * 0.3  # 理论最大利润
        
        if max_theoretical_profit > 0:
            # 使用对数函数平滑增长
            raw_profit_ratio = expected_profit / max_theoretical_profit
            if raw_profit_ratio <= 0:
                profit_score = raw_profit_ratio  # 负利润维持原值
            else:
                # 对数函数: log(x+1)在x=0时为0，随x增加而缓慢增加
                profit_score = min(1.0, math.log(raw_profit_ratio * 5 + 1) / 2)
        
        # 添加利用率和忠诚度修正
        profit_score += utilization_bonus + loyalty_potential
        
        # 归一化到[-1, 1]区间
        return max(-1, min(1, profit_score * 2 - 1 if profit_score > 0.5 else profit_score))
    
    def _calculate_grid_friendliness(self, charger, state):
        """
        计算充电决策对电网的友好度
        考虑因素：当前电网负载，可再生能源比例，峰谷时段等
        
        Args:
            charger: 充电桩数据
            state: 当前环境状态
            
        Returns:
            网格友好度评分 [-1,1]
        """
        # 获取电网状态数据
        grid_load = state.get("grid_load", 50)  # 默认50%负载
        renewable_ratio = state.get("renewable_ratio", 0.2)  # 默认20%可再生能源
        timestamp = state.get("timestamp")
        
        # 获取当前小时
        try:
            current_dt = datetime.fromisoformat(timestamp)
            hour = current_dt.hour
        except:
            hour = 12  # 默认中午
        
        # 新增：获取充电桩功率和当前使用情况
        charger_max_power = charger.get("max_power", 50)  # 单位：kW
        current_power = 0
        
        # 如果充电桩正在使用，考虑实际功率
        if charger.get("status") == "occupied":
            current_power = charger.get("current_power", charger_max_power * 0.8)  # 默认使用80%额定功率
        
        # 降低EV充电对总负载的影响因子
        # 通过增加基础负载来减小单个充电桩的相对影响
        base_load_factor = 20  # 增加这个值，进一步降低EV充电的相对影响
        adjusted_grid_load = (grid_load * base_load_factor + current_power) / (base_load_factor + 1)
        
        # 1. 基于负载的基础评分 - 负载越高，越不友好
        # 使用非线性函数，使高负载时惩罚更严重，但避免始终为负值
        if adjusted_grid_load < 30:  # 低负载，非常友好
            load_score = 0.8
        elif adjusted_grid_load < 50:  # 中等负载，适度友好
            load_score = 0.5 - (adjusted_grid_load - 30) * 0.015  # 0.5到0.2线性下降
        elif adjusted_grid_load < 70:  # 较高负载，不太友好
            load_score = 0.2 - (adjusted_grid_load - 50) * 0.015  # 0.2到-0.1线性下降
        elif adjusted_grid_load < 85:  # 高负载，不友好
            load_score = -0.1 - (adjusted_grid_load - 70) * 0.025  # -0.1到-0.475线性下降
        else:  # 极高负载，非常不友好
            load_score = -0.475 - (adjusted_grid_load - 85) * 0.01  # -0.475到-0.625线性下降
            load_score = max(-0.7, load_score)  # 限制最低值为-0.7，避免过度惩罚
        
        # 2. 可再生能源奖励 - 可再生能源比例越高，越友好
        renewable_score = renewable_ratio * 0.8  # 增加可再生能源影响，最高可增加0.8的评分
        
        # 3. 时间影响 - 基于峰谷时段
        # 定义峰谷时段
        peak_hours = [9, 10, 11, 12, 13, 14, 15, 16, 19, 20, 21]  # 工作和晚间高峰
        valley_hours = [0, 1, 2, 3, 4, 5, 23]  # 深夜/凌晨低谷
        shoulder_hours = [6, 7, 8, 17, 18, 22]  # 过渡时段
        
        time_score = 0
        if hour in peak_hours:
            time_score = -0.3  # 高峰期，不友好（降低惩罚力度）
        elif hour in valley_hours:
            time_score = 0.6   # 低谷期，很友好（增加奖励力度）
        else:  # shoulder_hours
            time_score = 0.2   # 过渡期，适中友好（增加奖励力度）
        
        # 4. 充电功率影响 - 功率越大，对电网冲击越大
        # 根据充电桩功率，计算功率惩罚
        power_penalty = 0
        if charger_max_power > 150:  # 超快充
            power_penalty = 0.1  # 降低惩罚
        elif charger_max_power > 50:  # 快充
            power_penalty = 0.05  # 降低惩罚
        else:  # 慢充
            power_penalty = 0
        
        # 5. 季节性因素 - 根据月份调整
        month = current_dt.month if hasattr(current_dt, 'month') else 6  # 默认6月
        season_factor = 0
        
        # 夏季和冬季用电高峰期调整
        if month in [6, 7, 8]:  # 夏季
            if 13 <= hour <= 16:  # 夏季午后高峰
                season_factor = -0.1  # 降低惩罚
        elif month in [12, 1, 2]:  # 冬季
            if 18 <= hour <= 21:  # 冬季晚间高峰
                season_factor = -0.1  # 降低惩罚
                
        # 计算最终电网友好度评分
        grid_friendliness = load_score + renewable_score + time_score - power_penalty + season_factor
        
        # 确保评分在[-1,1]范围内，并提高总体评分水平
        grid_friendliness = max(-0.9, min(1.0, grid_friendliness))
        
        # 对所有评分进行小幅度提升，避免过度负面
        if grid_friendliness < 0:
            grid_friendliness *= 0.8  # 负面评分减弱20%
        else:
            grid_friendliness *= 1.1  # 正面评分增强10%
            grid_friendliness = min(1.0, grid_friendliness)  # 确保不超过1.0
        
        # 记录调试信息
        logger.debug(f"Grid friendliness calculation for charger {charger.get('charger_id')}:")
        logger.debug(f"  - Grid load: {grid_load:.1f}%")
        logger.debug(f"  - Adjusted grid load: {adjusted_grid_load:.1f}%")
        logger.debug(f"  - Load score: {load_score:.2f}")
        logger.debug(f"  - Renewable score: {renewable_score:.2f}")
        logger.debug(f"  - Time score: {time_score:.2f}")
        logger.debug(f"  - Power penalty: {power_penalty:.2f}")
        logger.debug(f"  - Season factor: {season_factor:.2f}")
        logger.debug(f"  - Final score: {grid_friendliness:.2f}")
        
        return grid_friendliness