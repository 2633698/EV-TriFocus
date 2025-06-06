# ev_charging_project/simulation/environment.py

import logging
from datetime import datetime, timedelta
import random
import math
import time  # <--- 确认导入 time 模块

# 使用相对导入，确保这些文件在同一目录下或正确配置了PYTHONPATH
try:
    from simulation.grid_model_enhanced import EnhancedGridModel
    from simulation.user_model import simulate_step as simulate_users_step
    from simulation.charger_model import simulate_step as simulate_chargers_step
    from simulation.metrics import calculate_rewards
    from simulation.utils import get_random_location, calculate_distance
except ImportError as e:
    logging.error(f"Error importing simulation submodules in environment.py: {e}", exc_info=True)
    # 在启动时如果无法导入核心模块，抛出错误可能更好
    raise ImportError(f"Could not import required simulation submodules: {e}")

logger = logging.getLogger(__name__)

class ChargingEnvironment:
    def __init__(self, config):
        """
        初始化充电环境。

        Args:
            config (dict): 包含所有配置项的字典。
        """
        self.config = config
        # 分别获取环境和电网的配置部分，提供默认空字典防止 KeyErrors
        self.env_config = config.get('environment', {})
        self.grid_config = config.get('grid', {}) # GridModel 会用到

        logger.info("Initializing ChargingEnvironment...")

        # 基本参数 - 从 env_config 获取，带默认值
        self.station_count = self.env_config.get("station_count", 20)
        self.chargers_per_station = self.env_config.get("chargers_per_station", 10)
        # charger_count 会在 _initialize_chargers 后根据实际创建数量更新
        self.charger_count = self.station_count * self.chargers_per_station
        self.user_count = self.env_config.get("user_count", 1000)
        self.simulation_days = self.env_config.get("simulation_days", 7)
        self.time_step_minutes = self.env_config.get("time_step_minutes", 15)
        # 地图边界，提供健壮的默认值
        self.map_bounds = self.env_config.get("map_bounds", {})
        self.map_bounds.setdefault("lat_min", 30.5)
        self.map_bounds.setdefault("lat_max", 31.0)
        self.map_bounds.setdefault("lng_min", 114.0)
        self.map_bounds.setdefault("lng_max", 114.5)
        self.region_count = self.env_config.get("region_count", 5)
        self.enable_uncoordinated_baseline = self.env_config.get("enable_uncoordinated_baseline", True)


        # 状态变量
        self.start_time = None # <--- 添加: 记录模拟开始时间
        self.current_time = None # 将在 reset 中设置
        self.users = {}
        self.chargers = {}
        self.history = []
        self.completed_charging_sessions = [] # 存储完成的充电会话日志

        # 初始化子模型 - GridModel 需要完整的 config
        self.grid_simulator = EnhancedGridModel(config)

        logger.info(f"Config loaded: Users={self.user_count}, Stations={self.station_count}, Chargers/Station={self.chargers_per_station}")
        self.reset() # 调用 reset 来完成初始化

    def reset(self):
        """重置环境到初始状态"""
        logger.info("Resetting ChargingEnvironment...")
        # ---> 设置 current_time 和 start_time <---
        # 使用当日零点作为起始时间，保证与预约系统时间一致
        start_dt_str = self.env_config.get("simulation_start_datetime", None)
        if start_dt_str:
            try:
                base_start_time = datetime.fromisoformat(start_dt_str)
                logger.info(f"Using configured simulation start time: {base_start_time}")
            except ValueError:
                logger.warning(f"Invalid simulation_start_datetime format '{start_dt_str}'. Using today's midnight.")
                base_start_time = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            # 默认使用当日零点作为起始时间
            base_start_time = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            logger.info(f"Using today's midnight as simulation start time: {base_start_time}")
        
        self.current_time = base_start_time
        self.start_time = base_start_time # <--- 记录仿真的实际开始时间

        self.users = self._initialize_users()
        self.chargers = self._initialize_chargers()
        self.grid_simulator.reset() # 重置电网状态
        self.history = []
        self.completed_charging_sessions = []
        logger.info(f"Environment reset complete. Simulation starts at: {self.start_time}")
        # 返回初始状态
        return self.get_current_state()

    def _initialize_users(self):
        """初始化模拟用户 (使用完整的详细逻辑)"""
        users = {}
        logger.info(f"Initializing {self.user_count} users...")

        user_count = self.user_count
        map_bounds = self.map_bounds
        user_config_defaults = self.env_config.get("user_defaults", {}) # 获取用户默认配置

        if user_count <= 0:
            logger.warning("User count is invalid, setting to default 1000")
            user_count = 1000

        soc_ranges = user_config_defaults.get("soc_distribution", [
            (0.15, (10, 30)), (0.35, (30, 60)), (0.35, (60, 80)), (0.15, (80, 95))
        ])

        # --- 热点区域生成逻辑 (使用更完整的版本) ---
        hotspots = []
        center_lat = (map_bounds["lat_min"] + map_bounds["lat_max"]) / 2
        center_lng = (map_bounds["lng_min"] + map_bounds["lng_max"]) / 2
        hotspots.append({"lat": center_lat, "lng": center_lng, "desc": "CBD", "weight": 0.2})

        actual_regions = self.region_count * 2 # 增加区域数量以分散
        remaining_weight = 0.8
        grid_rows = int(math.sqrt(actual_regions))
        grid_cols = (actual_regions + grid_rows - 1) // grid_rows
        lat_step = (map_bounds["lat_max"] - map_bounds["lat_min"]) / (grid_rows + 1e-6) # Avoid division by zero
        lng_step = (map_bounds["lng_max"] - map_bounds["lng_min"]) / (grid_cols + 1e-6) # Avoid division by zero

        for i in range(max(0, actual_regions - 1)): # 确保 non-negative
            row = i // grid_cols; col = i % grid_cols
            base_lat = map_bounds["lat_min"] + lat_step * row
            base_lng = map_bounds["lng_min"] + lng_step * col
            lat = base_lat + random.uniform(0.1, 0.9) * lat_step # 在格子内随机
            lng = base_lng + random.uniform(0.1, 0.9) * lng_step
            # 避免太近
            min_distance = 0.01
            too_close = any(calculate_distance({"lat": lat, "lng": lng}, spot) < min_distance for spot in hotspots)
            if too_close: # 尝试重新随机
                lat = base_lat + random.uniform(0.1, 0.9) * lat_step
                lng = base_lng + random.uniform(0.1, 0.9) * lng_step

            descriptions = ["科技园", "购物中心", "居民区", "工业区", "休闲区", "大学城", "商圈", "医院", "学校", "办公区"]
            desc = descriptions[i % len(descriptions)] + str(i // len(descriptions) + 1)
            weight = remaining_weight / (actual_regions * 1.5) # 分散权重
            hotspots.append({"lat": lat, "lng": lng, "desc": desc, "weight": weight})

        total_weight = sum(spot["weight"] for spot in hotspots)
        if total_weight > 0:
            for spot in hotspots: spot["weight"] /= total_weight
        # --- 结束热点生成 ---

        # 从环境配置中获取车辆类型，如果没有则使用默认值
        vehicle_types = self.env_config.get("vehicle_types", user_config_defaults.get("vehicle_types", {
            "sedan": {"battery_capacity": 60, "max_range": 400, "max_charging_power": 60},
            "suv": {"battery_capacity": 85, "max_range": 480, "max_charging_power": 90},
            "compact": {"battery_capacity": 45, "max_range": 350, "max_charging_power": 50},
            "luxury": {"battery_capacity": 100, "max_range": 550, "max_charging_power": 120},
            "truck": {"battery_capacity": 120, "max_range": 400, "max_charging_power": 150},
        }))
        
        # 从环境配置中获取用户类型，如果没有则使用默认值
        user_types = self.env_config.get("user_types", {})
        user_type_options = list(user_types.keys()) if user_types else ["private", "taxi", "ride_hailing", "logistics", "commuter", "business", "delivery"]
        user_profile_options = ["urgent", "economic", "flexible", "anxious"]

        for i in range(user_count):
            user_id = f"user_{i+1}"
            vehicle_type = random.choice(list(vehicle_types.keys()))
            # 根据不同用户类型设置概率分布
            user_type_weights = {
                "private": 0.4,
                "taxi": 0.1,
                "ride_hailing": 0.1,
                "logistics": 0.1,
                "commuter": 0.15,
                "business": 0.05,
                "delivery": 0.1
            }
            
            # 确保只使用配置中存在的用户类型
            available_types = []
            available_weights = []
            for ut, weight in user_type_weights.items():
                if ut in user_type_options:
                    available_types.append(ut)
                    available_weights.append(weight)
            
            # 如果没有可用类型，则使用所有类型并平均分配权重
            if not available_types:
                available_types = user_type_options
                available_weights = [1.0/len(user_type_options)] * len(user_type_options)
            else:
                # 归一化权重
                total_weight = sum(available_weights)
                if total_weight > 0:
                    available_weights = [w/total_weight for w in available_weights]
            
            user_type = random.choices(available_types, weights=available_weights, k=1)[0]

            # 随机SOC
            rand_soc_val = random.random(); cumulative_prob = 0; soc_range = (10, 90)
            for prob, range_val in soc_ranges:
                cumulative_prob += prob
                if rand_soc_val <= cumulative_prob: soc_range = range_val; break
            soc = random.uniform(soc_range[0], soc_range[1])

            # 用户偏好 profile - 根据用户类型设置不同的画像概率分布
            # 画像顺序: [urgent, economic, flexible, anxious]
            profile_probs = [0.25] * 4 # 默认平均分布
            
            # 根据用户类型设置不同的画像概率分布
            profile_probs_by_type = {
                "private": [0.2, 0.3, 0.3, 0.2],
                "taxi": [0.5, 0.1, 0.3, 0.1],
                "ride_hailing": [0.4, 0.2, 0.3, 0.1],
                "logistics": [0.3, 0.4, 0.2, 0.1],
                "commuter": [0.3, 0.2, 0.3, 0.2],
                "business": [0.6, 0.1, 0.2, 0.1],
                "delivery": [0.5, 0.3, 0.1, 0.1]
            }
            
            # 使用用户类型对应的概率分布，如果没有则使用默认值
            profile_probs = profile_probs_by_type.get(user_type, [0.25, 0.25, 0.25, 0.25])
            if soc < 30: profile_probs[0] += 0.2 # Increase urgent if low SOC
            total_prob = sum(profile_probs)
            if total_prob > 0: profile_probs = [p / total_prob for p in profile_probs]
            else: profile_probs = [0.25]*4 # Fallback if somehow total is zero
            user_profile = random.choices(user_profile_options, weights=profile_probs, k=1)[0]

            # 电池和续航
            vehicle_info = vehicle_types.get(vehicle_type, list(vehicle_types.values())[0])
            battery_capacity = vehicle_info.get("battery_capacity", 60)
            max_range = vehicle_info.get("max_range", 400)
            current_range = max_range * (soc / 100)
            max_charging_power = vehicle_info.get("max_charging_power", 60)

            # 用户位置
            if hotspots and random.random() < 0.7:
                 chosen_hotspot = random.choices(hotspots, weights=[spot["weight"] for spot in hotspots], k=1)[0]
                 radius = random.gauss(0, 0.03); angle = random.uniform(0, 2 * math.pi)
                 lat = chosen_hotspot["lat"] + radius * math.cos(angle)
                 lng = chosen_hotspot["lng"] + radius * math.sin(angle)
            else:
                 lat = random.uniform(map_bounds["lat_min"], map_bounds["lat_max"])
                 lng = random.uniform(map_bounds["lng_min"], map_bounds["lng_max"])
            lat = min(max(lat, map_bounds["lat_min"]), map_bounds["lat_max"])
            lng = min(max(lng, map_bounds["lng_min"]), map_bounds["lng_max"])

            # 用户状态
            status_probs = {"idle": 0.7, "traveling": 0.3};
            if soc < 30: status_probs = {"idle": 0.3, "traveling": 0.7}
            elif soc < 60: status_probs = {"idle": 0.6, "traveling": 0.4}
            status = random.choices(list(status_probs.keys()), weights=list(status_probs.values()))[0]

            # 行驶速度
            travel_speed = random.uniform(30, 65)

            # 创建用户字典
            users[user_id] = {
                "user_id": user_id, "vehicle_type": vehicle_type, "user_type": user_type,
                "user_profile": user_profile, "battery_capacity": battery_capacity, "soc": soc,
                "max_range": max_range, "current_range": current_range,
                "current_position": {"lat": lat, "lng": lng}, "status": status,
                "target_charger": None, "charging_history": [], "travel_speed": travel_speed,
                "route": [], "waypoints": [], "destination": None, "time_to_destination": None,
                "traveled_distance": 0, "charging_efficiency": 0.92,
                "max_charging_power": max_charging_power,
                "driving_style": random.choices(["normal", "aggressive", "eco"], weights=[0.6, 0.25, 0.15])[0],
                "needs_charge_decision": False, "time_sensitivity": 0.5, "price_sensitivity": 0.5,
                "range_anxiety": 0.0, "last_destination_type": None, "_current_segment_index": 0 # Add helper for path tracking
            }
            # 设置敏感度 - 首先根据用户类型设置基础敏感度
            user_type_config = self.env_config.get("user_types", {}).get(user_type, {})
            base_time_sensitivity = user_type_config.get("time_sensitivity", 0.5)
            base_price_sensitivity = user_type_config.get("price_sensitivity", 0.5)
            base_range_anxiety = user_type_config.get("range_anxiety", 0.3)
            base_fast_charging_preference = user_type_config.get("fast_charging_preference", 0.5)
            
            # 然后根据用户画像调整敏感度
            if user_profile == "urgent": 
                users[user_id]["time_sensitivity"] = min(1.0, base_time_sensitivity * random.uniform(1.2, 1.4))
                users[user_id]["price_sensitivity"] = max(0.1, base_price_sensitivity * random.uniform(0.3, 0.5))
                users[user_id]["range_anxiety"] = max(0.1, base_range_anxiety * random.uniform(0.5, 0.7))
                users[user_id]["fast_charging_preference"] = min(1.0, base_fast_charging_preference * random.uniform(1.3, 1.5))
            elif user_profile == "economic": 
                users[user_id]["time_sensitivity"] = max(0.1, base_time_sensitivity * random.uniform(0.5, 0.7))
                users[user_id]["price_sensitivity"] = min(1.0, base_price_sensitivity * random.uniform(1.2, 1.4))
                users[user_id]["range_anxiety"] = base_range_anxiety * random.uniform(0.8, 1.2)
                users[user_id]["fast_charging_preference"] = max(0.1, base_fast_charging_preference * random.uniform(0.4, 0.6))
            elif user_profile == "anxious": 
                users[user_id]["time_sensitivity"] = base_time_sensitivity * random.uniform(0.8, 1.2)
                users[user_id]["price_sensitivity"] = max(0.1, base_price_sensitivity * random.uniform(0.6, 0.8))
                users[user_id]["range_anxiety"] = min(1.0, base_range_anxiety * random.uniform(1.5, 2.0))
                users[user_id]["fast_charging_preference"] = min(1.0, base_fast_charging_preference * random.uniform(1.1, 1.3))
            else: # flexible
                users[user_id]["time_sensitivity"] = base_time_sensitivity * random.uniform(0.9, 1.1)
                users[user_id]["price_sensitivity"] = base_price_sensitivity * random.uniform(0.9, 1.1)
                users[user_id]["range_anxiety"] = base_range_anxiety * random.uniform(0.9, 1.1)
                users[user_id]["fast_charging_preference"] = base_fast_charging_preference * random.uniform(0.9, 1.1)

        logger.info(f"Initialized {len(users)} users.")
        return users

    def _initialize_chargers(self):
        """初始化充电站和充电桩 (使用完整的详细逻辑)"""
        chargers = {}
        logger.info(f"Initializing {self.station_count} stations, aiming for approx {self.chargers_per_station} chargers/station...")

        failure_rate = self.env_config.get("charger_failure_rate", 0.0)
        charger_defaults = self.env_config.get("charger_defaults", {})
        superfast_ratio = charger_defaults.get("superfast_ratio", 0.1)
        fast_ratio = charger_defaults.get("fast_ratio", 0.4)
        power_ranges = charger_defaults.get("power_ranges", {"superfast": [250, 400], "fast": [60, 120], "normal": [7, 20]})
        price_multipliers = charger_defaults.get("price_multipliers", {"superfast": 1.5, "fast": 1.2, "normal": 1.0})
        queue_capacity = self.env_config.get("charger_queue_capacity", 5)

        locations = []
        for i in range(self.station_count):
            random_pos = get_random_location(self.map_bounds)
            locations.append({"name": f"充电站{i+1}", "lat": random_pos["lat"], "lng": random_pos["lng"]})

        current_id = 1
        for location in locations:
            num_chargers_at_loc = self.chargers_per_station
            for i in range(num_chargers_at_loc):
                charger_id = f"charger_{current_id}"
                rand_val = random.random()
                charger_type = "normal"; pr = power_ranges.get("normal"); p_mult = price_multipliers.get("normal")
                if rand_val < superfast_ratio: charger_type = "superfast"; pr = power_ranges.get("superfast"); p_mult = price_multipliers.get("superfast")
                elif rand_val < superfast_ratio + fast_ratio: charger_type = "fast"; pr = power_ranges.get("fast"); p_mult = price_multipliers.get("fast")

                # 安全地处理功率范围
                if pr and isinstance(pr, list) and len(pr) == 2 and all(isinstance(p, (int, float)) for p in pr):
                     charger_power = random.uniform(pr[0], pr[1])
                else:
                     charger_power = 50 # Fallback power
                     logger.warning(f"Invalid power range defined for type '{charger_type}': {pr}. Using default 50kW.")

                is_failure = random.random() < failure_rate

                chargers[charger_id] = {
                    "charger_id": charger_id, "location": location["name"], "type": charger_type,
                    "max_power": round(charger_power, 1),
                    "position": {"lat": location["lat"] + random.uniform(-0.002, 0.002), "lng": location["lng"] + random.uniform(-0.002, 0.002)},
                    "status": "failure" if is_failure else "available", "current_user": None, "queue": [],
                    "queue_capacity": queue_capacity, "daily_revenue": 0.0, "daily_energy": 0.0,
                    "price_multiplier": p_mult if isinstance(p_mult, (int, float)) else 1.0, # Ensure multiplier is number
                    "region": f"Region_{random.randint(1, self.region_count)}"
                }
                current_id += 1

        self.charger_count = len(chargers) # 更新实际数量
        logger.info(f"Initialized {self.charger_count} chargers across {self.station_count} stations.")
        return chargers

    def step(self, decisions, manual_decisions=None, v2g_request_mw=None):
        """执行一个仿真时间步，支持手动决策和V2G请求"""
        if self.start_time is None:
            logger.error("Simulation start time not set! Resetting environment.")
            self.reset()

        logger.debug(f"--- Step Start: {self.current_time} ---")
        step_start_time = time.time()

        # 0. 检查并处理预约
        from reservation_system import reservation_manager
        processed_reservations = reservation_manager.checkAndProcessReservations(
            self.current_time, self.users, self.chargers
        )
        
        # 将预约决策添加到最终决策中（预约优先级最高）
        reservation_decisions = {}
        for res_data in processed_reservations:
            user_id = res_data['user_id']
            charger_id = res_data['charger_id']
            reservation_decisions[user_id] = charger_id
            logger.info(f"预约决策: 用户 {user_id} -> 充电桩 {charger_id} (预约ID: {res_data['reservation_id']})")
        
        # 1. 合并预约决策、手动决策和算法决策（按优先级）
        final_decisions = {}
        
        # 首先添加算法决策（最低优先级）
        if decisions and isinstance(decisions, dict):
            final_decisions.update(decisions)
        
        # 然后添加手动决策（覆盖算法决策）
        if manual_decisions and isinstance(manual_decisions, dict):
            final_decisions.update(manual_decisions)
            logger.info(f"Applied {len(manual_decisions)} manual decisions")
        
        # 最后添加预约决策（最高优先级，覆盖所有其他决策）
        if reservation_decisions:
            final_decisions.update(reservation_decisions)
            logger.info(f"Applied {len(reservation_decisions)} reservation decisions")
        
        # 2. 应用决策: 设置用户目标充电桩并规划初始路线
        users_routed = 0
        for user_id, charger_id in final_decisions.items():
            if user_id in self.users and charger_id in self.chargers:
                user = self.users[user_id]
                charger = self.chargers[charger_id]
                
                # 检查用户是否已经在处理中
                if user.get('status') not in ['charging', 'waiting'] and user.get('target_charger') != charger_id:
                    from .user_model import plan_route_to_charger
                    charger_pos = charger.get('position')
                    if charger_pos:
                        # 设置目标充电桩
                        user['target_charger'] = charger_id
                        user['_current_segment_index'] = 0
                        
                        # 如果是手动决策，设置特殊标记和参数
                        if manual_decisions and user_id in manual_decisions:
                            user['manual_decision'] = True
                            user['manual_decision_time'] = self.current_time.isoformat()
                            
                            # 专门为手动决策用户启用详细日志
                            logger.info(f"=== MANUAL DECISION TRIGGERED for User {user_id} ===")
                            logger.info(f"Decision time: {self.current_time.isoformat()}")
                            logger.info(f"Target charger: {charger_id}")
                            logger.info(f"User current status: {user.get('status')}")
                            logger.info(f"User current SOC: {user.get('soc', 0):.1f}%")
                            logger.info(f"User current position: {user.get('current_position')}")
                            
                            # 应用手动设置的目标SOC
                            if 'manual_charging_params' in user:
                                params = user.get('manual_charging_params', {})
                                old_target_soc = user.get('target_soc', 80)
                                old_charging_type = user.get('preferred_charging_type', '快充')
                                user['target_soc'] = params.get('target_soc', 80)
                                user['preferred_charging_type'] = params.get('charging_type', '快充')
                                logger.info(f"Manual charging params applied:")
                                logger.info(f"  - Target SOC: {old_target_soc}% -> {user['target_soc']}%")
                                logger.info(f"  - Charging type: {old_charging_type} -> {user.get('preferred_charging_type')}")
                            else:
                                logger.warning(f"No manual_charging_params found for user {user_id}, using defaults")
                            
                            # 立即强制用户开始前往充电桩（覆盖当前状态）
                            if user.get('status') in ['idle', 'traveling']:
                                old_status = user.get('status')
                                user['status'] = 'traveling'
                                user['needs_charge_decision'] = False
                                # 清除之前的路径，强制重新规划
                                user['waypoints'] = []
                                user['_current_segment_index'] = 0
                                logger.info(f"Manual decision status change: {old_status} -> traveling")
                                logger.info(f"Cleared previous waypoints, forcing route replanning")
                                logger.info(f"User {user_id} immediately starts traveling to charger {charger_id}")
                            else:
                                logger.warning(f"User {user_id} status '{user.get('status')}' not suitable for immediate travel")
                        
                        # 如果是预约决策，设置特殊标记和参数（类似手动决策的强制执行）
                        elif reservation_decisions and user_id in reservation_decisions:
                            user['reservation_decision'] = True
                            user['reservation_decision_time'] = self.current_time.isoformat()
                            
                            # 专门为预约决策用户启用详细日志
                            logger.info(f"=== RESERVATION DECISION TRIGGERED for User {user_id} ===")
                            logger.info(f"Decision time: {self.current_time.isoformat()}")
                            logger.info(f"Target charger: {charger_id}")
                            logger.info(f"User current status: {user.get('status')}")
                            logger.info(f"User current SOC: {user.get('soc', 0):.1f}%")
                            logger.info(f"User current position: {user.get('current_position')}")
                            
                            # 应用预约设置的目标SOC（已在checkAndProcessReservations中设置）
                            logger.info(f"Reservation charging params:")
                            logger.info(f"  - Target SOC: {user.get('target_soc', 80)}%")
                            logger.info(f"  - Charging type: {user.get('preferred_charging_type', '快充')}")
                            logger.info(f"  - Reservation ID: {user.get('reservation_id', 'unknown')}")
                            
                            # 立即强制用户开始前往充电桩（覆盖当前状态）
                            if user.get('status') in ['idle', 'traveling']:
                                old_status = user.get('status')
                                user['status'] = 'traveling'
                                user['needs_charge_decision'] = False
                                # 清除之前的路径，强制重新规划
                                user['waypoints'] = []
                                user['_current_segment_index'] = 0
                                logger.info(f"Reservation decision status change: {old_status} -> traveling")
                                logger.info(f"Cleared previous waypoints, forcing route replanning")
                                logger.info(f"User {user_id} immediately starts traveling to charger {charger_id} for reservation")
                            else:
                                logger.warning(f"User {user_id} status '{user.get('status')}' not suitable for immediate travel")
                        
                        if plan_route_to_charger(user, charger_pos, self.map_bounds):
                            user['status'] = 'traveling'
                            # 确保手动决策用户正确设置目的地
                            user['destination'] = charger_pos.copy()
                            users_routed += 1
                            # 为手动决策用户添加专门的路径规划成功日志
                            if user.get('manual_decision'):
                                logger.info(f"=== MANUAL DECISION ROUTE PLANNING SUCCESS ===")
                                logger.info(f"User {user_id} successfully routed to charger {charger_id}")
                                logger.info(f"Route waypoints count: {len(user.get('waypoints', []))}")
                                logger.info(f"User status confirmed: {user.get('status')}")
                                logger.info(f"Destination set to: {user.get('destination')}")
                                logger.info(f"Time to destination: {user.get('time_to_destination', 0):.1f} minutes")
                            # 为预约决策用户添加专门的路径规划成功日志
                            elif user.get('reservation_decision'):
                                logger.info(f"=== RESERVATION DECISION ROUTE PLANNING SUCCESS ===")
                                logger.info(f"User {user_id} successfully routed to charger {charger_id}")
                                logger.info(f"Route waypoints count: {len(user.get('waypoints', []))}")
                                logger.info(f"User status confirmed: {user.get('status')}")
                                logger.info(f"Destination set to: {user.get('destination')}")
                                logger.info(f"Time to destination: {user.get('time_to_destination', 0):.1f} minutes")
                                logger.info(f"Reservation ID: {user.get('reservation_id', 'unknown')}")
                            else:
                                logger.info(f"Routed user {user_id} to charger {charger_id}")
                        else:
                            # 为手动决策用户添加专门的路径规划失败日志
                            if user.get('manual_decision'):
                                logger.error(f"=== MANUAL DECISION ROUTE PLANNING FAILED ===")
                                logger.error(f"Failed to plan route for MANUAL user {user_id} to charger {charger_id}")
                                logger.error(f"User position: {user.get('current_position')}")
                                logger.error(f"Charger position: {charger_pos}")
                                logger.error(f"Clearing manual decision due to routing failure")
                                user['manual_decision'] = False
                            # 为预约决策用户添加专门的路径规划失败日志
                            elif user.get('reservation_decision'):
                                logger.error(f"=== RESERVATION DECISION ROUTE PLANNING FAILED ===")
                                logger.error(f"Failed to plan route for RESERVATION user {user_id} to charger {charger_id}")
                                logger.error(f"User position: {user.get('current_position')}")
                                logger.error(f"Charger position: {charger_pos}")
                                logger.error(f"Reservation ID: {user.get('reservation_id', 'unknown')}")
                                logger.error(f"Clearing reservation decision due to routing failure")
                                user['reservation_decision'] = False
                                user['is_reservation_user'] = False
                            else:
                                logger.warning(f"Failed to plan route for user {user_id} to charger {charger_id}")
                            user['target_charger'] = None
                    else:
                        logger.warning(f"Charger {charger_id} has no position data.")

        logger.debug(f"Processed {len(final_decisions)} decisions, routed {users_routed} users.")

        # 2. 模拟用户行为 (调用 user_model)
        simulate_users_step(self.users, self.chargers, self.current_time, self.time_step_minutes, self.config)
            
        # 处理到达用户加入队列
        users_added_to_queue = 0
        for user_id, user in self.users.items():
            if user.get("status") == "waiting":
                target_charger_id = user.get("target_charger")
                if target_charger_id and target_charger_id in self.chargers:
                    charger = self.chargers[target_charger_id]
                    if not isinstance(charger.get('queue'), list):
                        charger['queue'] = []
                    
                    if user_id not in charger['queue']:
                        queue_capacity = charger.get("queue_capacity", 5)
                        current_queue_len = len(charger['queue'])
                        
                        # 检查是否为锁定的手动决策用户
                        is_locked_manual = user.get('manual_decision') and user.get('manual_decision_locked')
                        
                        if is_locked_manual:
                            # 强制锁定的手动决策用户只能在目标充电桩排队
                            locked_target = user.get('target_charger')
                            if locked_target != target_charger_id:
                                logger.warning(f"=== MANUAL DECISION LOCK VIOLATION PREVENTED ===")
                                logger.warning(f"Locked manual user {user_id} can ONLY queue at {locked_target}, not {target_charger_id}")
                                logger.warning(f"Ignoring queue addition to wrong charger")
                                continue
                            
                            # 强制添加到锁定的目标充电桩，无视队列容量
                            charger['queue'].append(user_id)
                            users_added_to_queue += 1
                            
                            logger.info(f"=== FORCED MANUAL DECISION QUEUE ADDITION ===")
                            logger.info(f"Locked manual user {user_id} FORCED into queue for target charger {target_charger_id}")
                            logger.info(f"Queue size: {len(charger['queue'])}/{queue_capacity} (capacity ignored for locked manual users)")
                            
                            # 将锁定的手动决策用户移到队列最前面
                            if len(charger['queue']) > 1:
                                charger['queue'].remove(user_id)
                                charger['queue'].insert(0, user_id)
                                logger.info(f"Locked manual user {user_id} moved to FRONT of queue")
                            
                        elif current_queue_len < queue_capacity:
                            charger['queue'].append(user_id)
                            users_added_to_queue += 1
                            
                            # 为普通手动决策用户提供优先级
                            if user.get('manual_decision'):
                                logger.info(f"=== MANUAL DECISION QUEUE PROCESSING ===")
                                logger.info(f"User {user_id} targeting charger {target_charger_id}")
                                logger.info(f"Current queue size: {len(charger['queue'])}/{queue_capacity}")
                                
                                # 将手动决策用户移到队列前面
                                if len(charger['queue']) > 1:
                                    charger['queue'].remove(user_id)
                                    charger['queue'].insert(0, user_id)
                                
                                logger.info(f"Manual decision user {user_id} given priority in queue for {target_charger_id}")
                            
                            logger.info(f"User {user_id} added to queue for charger {target_charger_id}")
                        else:
                            logger.warning(f"User {user_id} arrived but queue full for charger {target_charger_id}")

        # 模拟充电过程
        current_grid_status = self.grid_simulator.get_status()
        total_ev_load, completed_sessions_this_step = simulate_chargers_step(
            self.chargers, self.users, self.current_time, self.time_step_minutes, current_grid_status
        )
        self.completed_charging_sessions.extend(completed_sessions_this_step)

        # Apply V2G discharge request to the grid model before updating the step
        if v2g_request_mw is not None and self.grid_simulator:
            logger.info(f"Environment: Applying V2G discharge of {v2g_request_mw} MW to grid model.")
            if hasattr(self.grid_simulator, 'apply_v2g_discharge'): # Check if method exists
                self.grid_simulator.apply_v2g_discharge(v2g_request_mw)
            else:
                logger.warning("Grid simulator does not have method 'apply_v2g_discharge'.")


        # 更新电网状态
        self.grid_simulator.update_step(self.current_time, total_ev_load)

        # 前进模拟时间
        self.current_time += timedelta(minutes=self.time_step_minutes)

        # 计算奖励
        current_state = self.get_current_state()
        rewards = calculate_rewards(current_state, self.config)

        # 保存历史状态
        self._save_current_state(rewards)

        # 检查结束条件
        if self.start_time:
            current_sim_time_naive = self.current_time.replace(tzinfo=None)
            start_sim_time_naive = self.start_time.replace(tzinfo=None)
            total_minutes_elapsed = (current_sim_time_naive - start_sim_time_naive).total_seconds() / 60
            total_simulation_minutes = self.simulation_days * 24 * 60
            done = total_minutes_elapsed >= (total_simulation_minutes - self.time_step_minutes / 2)
        else:
            logger.error("Simulation start time is missing!")
            done = True

        step_duration = time.time() - step_start_time
        logger.debug(f"--- Step End: {self.current_time} (Duration: {step_duration:.3f}s) ---")

        return rewards, current_state, done


    def get_current_state(self):
        """获取当前环境状态"""
        users_list = list(self.users.values()) if self.users else []
        chargers_list = list(self.chargers.values()) if self.chargers else []

        state = {
            "timestamp": self.current_time.isoformat(),
            "users": users_list,
            "chargers": chargers_list,
            "grid_status": self.grid_simulator.get_status(), # 从 grid_simulator 获取
            # 优化历史记录大小: 只包含关键信息，并且限制长度
            "history": self.history[-96:] # 最近24小时 (假设15分钟步长)
        }
        return state

    def _save_current_state(self, rewards):
        """保存当前的关键状态和奖励到历史记录"""
        latest_grid_status = self.grid_simulator.get_status()
        state_snapshot = {
            "timestamp": self.current_time.isoformat(),
            "grid_status": { # 只保存关键指标
                "grid_load_percentage": latest_grid_status.get("grid_load_percentage"),
                "current_ev_load": latest_grid_status.get("current_ev_load"),
                "current_total_load": latest_grid_status.get("current_total_load"),
                "renewable_ratio": latest_grid_status.get("renewable_ratio"),
                "current_price": latest_grid_status.get("current_price"),
            },
            "rewards": rewards,
        }
        self.history.append(state_snapshot)
        # 限制历史记录长度 (例如，保留最近48小时的数据点)