# ev_charging_project/simulation/environment.py

import logging
from datetime import datetime, timedelta
import random
import math
import time  # <--- 确认导入 time 模块

# 使用相对导入，确保这些文件在同一目录下或正确配置了PYTHONPATH
try:
    from .grid_model import GridModel
    from .user_model import simulate_step as simulate_users_step
    from .charger_model import simulate_step as simulate_chargers_step
    from .metrics import calculate_rewards
    from .utils import get_random_location, calculate_distance
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
        self.grid_simulator = GridModel(config)

        logger.info(f"Config loaded: Users={self.user_count}, Stations={self.station_count}, Chargers/Station={self.chargers_per_station}")
        self.reset() # 调用 reset 来完成初始化

    def reset(self):
        """重置环境到初始状态"""
        logger.info("Resetting ChargingEnvironment...")
        # ---> 设置 current_time 和 start_time <---
        # 使用固定或可配置的起始时间点，而不是 datetime.now()，保证可重复性
        # 可以从 config 读取，或使用一个固定的日期
        start_dt_str = self.env_config.get("simulation_start_datetime", "2025-01-01T00:00:00")
        try:
            base_start_time = datetime.fromisoformat(start_dt_str)
        except ValueError:
            logger.warning(f"Invalid simulation_start_datetime format '{start_dt_str}'. Using default.")
            base_start_time = datetime(2025, 1, 1, 0, 0, 0)
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

        vehicle_types = user_config_defaults.get("vehicle_types", {
            "sedan": {"battery_capacity": 60, "max_range": 400, "max_charging_power": 60},
            "suv": {"battery_capacity": 85, "max_range": 480, "max_charging_power": 90},
        })

        user_type_options = ["private", "taxi", "ride_hailing", "logistics"]
        user_profile_options = ["urgent", "economic", "flexible", "anxious"]

        for i in range(user_count):
            user_id = f"user_{i+1}"
            vehicle_type = random.choice(list(vehicle_types.keys()))
            user_type = random.choice(user_type_options)

            # 随机SOC
            rand_soc_val = random.random(); cumulative_prob = 0; soc_range = (10, 90)
            for prob, range_val in soc_ranges:
                cumulative_prob += prob
                if rand_soc_val <= cumulative_prob: soc_range = range_val; break
            soc = random.uniform(soc_range[0], soc_range[1])

            # 用户偏好 profile
            profile_probs = [0.25] * 4 # Equal default
            if user_type == "taxi": profile_probs = [0.5, 0.1, 0.3, 0.1]
            elif user_type == "ride_hailing": profile_probs = [0.4, 0.2, 0.3, 0.1]
            elif user_type == "logistics": profile_probs = [0.3, 0.4, 0.2, 0.1]
            else: profile_probs = [0.2, 0.3, 0.3, 0.2]
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
            # 设置敏感度
            if user_profile == "urgent": users[user_id]["time_sensitivity"] = random.uniform(0.7, 0.9); users[user_id]["price_sensitivity"] = random.uniform(0.1, 0.3)
            elif user_profile == "economic": users[user_id]["time_sensitivity"] = random.uniform(0.2, 0.4); users[user_id]["price_sensitivity"] = random.uniform(0.7, 0.9)
            elif user_profile == "anxious": users[user_id]["time_sensitivity"] = random.uniform(0.5, 0.7); users[user_id]["price_sensitivity"] = random.uniform(0.3, 0.5); users[user_id]["range_anxiety"] = random.uniform(0.6, 0.9)
            # else: flexible/default uses 0.5

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
                    "position": {"lat": location["lat"] + random.uniform(-0.0005, 0.0005), "lng": location["lng"] + random.uniform(-0.0005, 0.0005)},
                    "status": "failure" if is_failure else "available", "current_user": None, "queue": [],
                    "queue_capacity": queue_capacity, "daily_revenue": 0.0, "daily_energy": 0.0,
                    "price_multiplier": p_mult if isinstance(p_mult, (int, float)) else 1.0, # Ensure multiplier is number
                    "region": f"Region_{random.randint(1, self.region_count)}"
                }
                current_id += 1

        self.charger_count = len(chargers) # 更新实际数量
        logger.info(f"Initialized {self.charger_count} chargers across {self.station_count} stations.")
        return chargers

    def step(self, decisions):
        """执行一个仿真时间步"""
        if self.start_time is None:
             logger.error("Simulation start time not set! Resetting environment.")
             self.reset()

        logger.debug(f"--- Step Start: {self.current_time} ---")
        step_start_time = time.time() # 使用导入的 time 模块

        # 1. 应用决策: 设置用户目标充电桩并规划初始路线
        users_routed = 0
        for user_id, charger_id in decisions.items():
            if user_id in self.users and charger_id in self.chargers:
                user = self.users[user_id]
                charger = self.chargers[charger_id]
                # 只有当用户当前需要去这个充电桩时才规划路线
                if user.get('status') not in ['charging', 'waiting'] and user.get('target_charger') != charger_id:
                    # 导入 user_model 中的路线规划函数
                    from .user_model import plan_route_to_charger
                    charger_pos = charger.get('position')
                    if charger_pos:
                        # ===> 修正: 直接设置 target_charger <===
                        user['target_charger'] = charger_id
                        user['_current_segment_index'] = 0 # 重置路径跟踪
                        if plan_route_to_charger(user, charger_pos, self.map_bounds):
                            user['status'] = 'traveling' # 设置为旅行状态
                            users_routed += 1
                        else:
                             logger.warning(f"Failed to plan route for user {user_id} to charger {charger_id}")
                             user['target_charger'] = None # 规划失败，清除目标
                    else:
                         logger.warning(f"Charger {charger_id} has no position data.")
            # else: logger.warning(f"Invalid decision: User {user_id} or Charger {charger_id} not found.")

        logger.debug(f"Processed {len(decisions)} decisions, routed {users_routed} users.")

        # 2. 模拟用户行为 (调用 user_model)
        simulate_users_step(self.users, self.chargers, self.current_time, self.time_step_minutes, self.config)
        logger.debug("User simulation step completed.")
        # ===> 新增逻辑：处理到达的用户，将其加入队列 <===
        users_added_to_queue = 0
        for user_id, user in self.users.items():
            if user.get("status") == "waiting":
                target_charger_id = user.get("target_charger")
                if target_charger_id and target_charger_id in self.chargers:
                    charger = self.chargers[target_charger_id]
                    # 确保 charger['queue'] 是一个列表
                    if not isinstance(charger.get('queue'), list):
                        charger['queue'] = []
                    # 如果用户不在队列中，则添加
                    if user_id not in charger['queue']:
                        # 检查队列容量
                        queue_capacity = charger.get("queue_capacity", 5) # 获取容量
                        current_queue_len = len(charger['queue'])
                        if current_queue_len < queue_capacity:
                             charger['queue'].append(user_id)
                             users_added_to_queue += 1
                             logger.info(f"User {user_id} arrived and added to queue for charger {target_charger_id}. Queue size: {len(charger['queue'])}")
                             # 清除 target_charger，表示已到达并入队，防止重复添加
                             # user["target_charger"] = None # <--- 考虑是否需要清除，可能影响重试逻辑
                        else:
                             logger.warning(f"User {user_id} arrived at charger {target_charger_id}, but queue is full ({current_queue_len}/{queue_capacity}). User remains WAITING.")
                             # 用户仍然是 waiting 状态，但未入队，下一轮调度可能会重新分配或用户放弃？
                             # 或者让用户状态变回 idle?
                             # user['status'] = 'idle' # 方案1：让用户变回空闲
                             # user['target_charger'] = None
                             pass # 方案2：保持 waiting，依赖后续逻辑处理

                # else: # 用户状态是 waiting 但没有有效的 target_charger，这不应该发生
                    # logger.warning(f"User {user_id} is WAITING but has no valid target_charger ID ({target_charger_id}).")
        if users_added_to_queue > 0:
            logger.debug(f"{users_added_to_queue} users added to charger queues this step.")
        # 3. 模拟充电过程 (调用 charger_model)
        current_grid_status = self.grid_simulator.get_status()
        total_ev_load, completed_sessions_this_step = simulate_chargers_step(
            self.chargers, self.users, self.current_time, self.time_step_minutes, current_grid_status
        )
        self.completed_charging_sessions.extend(completed_sessions_this_step) # 添加到总列表
        logger.debug(f"Charger simulation step completed. EV Load: {total_ev_load:.2f} kW. Sessions completed: {len(completed_sessions_this_step)}")

        # 4. 更新电网状态 (调用 grid_model)
        self.grid_simulator.update_step(self.current_time, total_ev_load)
        logger.debug("Grid simulation step completed.")

        # 5. 前进模拟时间
        self.current_time += timedelta(minutes=self.time_step_minutes)

        # 6. 计算奖励 (调用 metrics 模块)
        current_state = self.get_current_state() # 获取更新后的状态
        rewards = calculate_rewards(current_state, self.config)
        logger.debug(f"Rewards calculated: {rewards}")

        # 7. 保存历史状态
        self._save_current_state(rewards)

        # 8. 检查结束条件 (使用正确的开始时间)
        # ===> 修正 done 计算 <===
        if self.start_time:
             # 确保比较时去除时区信息（如果存在）以避免错误
             current_sim_time_naive = self.current_time.replace(tzinfo=None)
             start_sim_time_naive = self.start_time.replace(tzinfo=None)
             # 计算总的模拟分钟数
             total_minutes_elapsed = (current_sim_time_naive - start_sim_time_naive).total_seconds() / 60
             # 计算总的目标分钟数
             total_simulation_minutes = self.simulation_days * 24 * 60
             # 判断是否完成（留一点点余量防止浮点数问题）
             done = total_minutes_elapsed >= (total_simulation_minutes - self.time_step_minutes / 2)
             logger.debug(f"Checking completion: Elapsed Min={total_minutes_elapsed:.1f}, Target Min={total_simulation_minutes}, Done={done}")
        else:
             logger.error("Simulation start time is missing! Cannot determine completion.")
             done = True # 无法判断，强制结束

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
        max_history_points = 48 * (60 // self.time_step_minutes)
        if len(self.history) > max_history_points:
            self.history = self.history[-max_history_points:]