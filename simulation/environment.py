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
        # Store relevant sub-configs from environment config
        self.init_params = self.env_config.get('initialization_params', {})
        self.user_model_params = self.env_config.get('user_model_params', {})
        self.charger_model_params = self.env_config.get('charger_model_params', {})

        logger.info("Initializing ChargingEnvironment...")

        # 基本参数 - 从 env_config 获取，带默认值
        self.station_count = self.env_config.get("station_count", 20)
        self.chargers_per_station = self.env_config.get("chargers_per_station", 10)
        self.charger_count = self.station_count * self.chargers_per_station # Initial estimate

        raw_user_count = self.env_config.get("user_count", 0) # Get user_count from top-level env_config
        if not isinstance(raw_user_count, int) or raw_user_count <= 0:
            logger.warning(f"Invalid user_count value: {raw_user_count} in env_config. Using fallback from initialization_params.")
            raw_user_count = self.init_params.get('user_count_invalid_fallback', 1000)
        self.user_count = raw_user_count
        
        self.simulation_days = self.env_config.get("simulation_days", 7)
        self.time_step_minutes = self.env_config.get("time_step_minutes", 15)
        
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
        # user_count is self.user_count, already validated in __init__
        logger.info(f"Initializing {self.user_count} users...")
        
        map_bounds = self.map_bounds # Already set in __init__
        # soc_ranges from top-level env_config, as it's a general distribution not specific to init_params
        soc_ranges = self.env_config.get("user_soc_distribution", [
            (0.15, (10, 30)), (0.35, (30, 60)), (0.35, (60, 80)), (0.15, (80, 95))
        ])

        # Hotspot Generation Parameters
        hotspot_gen_params = self.init_params.get('hotspot_generation', {})
        cbd_weight = hotspot_gen_params.get('cbd_weight', 0.2)
        region_multiplier = hotspot_gen_params.get('region_multiplier', 2)
        remaining_weight_factor = hotspot_gen_params.get('remaining_weight_factor_for_other_hotspots', 0.8)
        other_hs_weight_divisor = hotspot_gen_params.get('other_hotspot_weight_divisor_factor', 1.5)
        min_hotspot_distance = hotspot_gen_params.get('min_hotspot_distance_degrees', 0.01)
        hotspot_descriptions_list = hotspot_gen_params.get('hotspot_descriptions', ["Tech Park", "Mall", "Residential Area", "Industrial Zone", "Leisure Area", "University", "Business District", "Hospital", "School", "Office Area"])
        hs_rand_min = hotspot_gen_params.get('hotspot_placement_randomness_factor_min', 0.1)
        hs_rand_max = hotspot_gen_params.get('hotspot_placement_randomness_factor_max', 0.9)

        hotspots = []
        center_lat = (map_bounds["lat_min"] + map_bounds["lat_max"]) / 2
        center_lng = (map_bounds["lng_min"] + map_bounds["lng_max"]) / 2
        hotspots.append({"lat": center_lat, "lng": center_lng, "desc": "CBD", "weight": cbd_weight})

        actual_regions = self.region_count * region_multiplier
        
        grid_rows = int(math.sqrt(actual_regions)) if actual_regions > 0 else 0
        grid_cols = (actual_regions + grid_rows - 1) // grid_rows if grid_rows > 0 else 0
        
        lat_step = (map_bounds["lat_max"] - map_bounds["lat_min"]) / (grid_rows + 1e-6) if grid_rows > 0 else 0
        lng_step = (map_bounds["lng_max"] - map_bounds["lng_min"]) / (grid_cols + 1e-6) if grid_cols > 0 else 0

        for i in range(max(0, actual_regions - 1)):
            row = i // grid_cols if grid_cols > 0 else 0
            col = i % grid_cols if grid_cols > 0 else 0
            base_lat = map_bounds["lat_min"] + lat_step * row
            base_lng = map_bounds["lng_min"] + lng_step * col
            lat = base_lat + random.uniform(hs_rand_min, hs_rand_max) * lat_step
            lng = base_lng + random.uniform(hs_rand_min, hs_rand_max) * lng_step
            
            too_close = any(calculate_distance({"lat": lat, "lng": lng}, spot) < min_hotspot_distance for spot in hotspots)
            if too_close: # Retry once
                lat = base_lat + random.uniform(hs_rand_min, hs_rand_max) * lat_step
                lng = base_lng + random.uniform(hs_rand_min, hs_rand_max) * lng_step
            
            desc = hotspot_descriptions_list[i % len(hotspot_descriptions_list)] + str(i // len(hotspot_descriptions_list) + 1) if hotspot_descriptions_list else f"Hotspot_{i+1}"
            weight = remaining_weight_factor / (actual_regions * other_hs_weight_divisor) if actual_regions > 0 and other_hs_weight_divisor > 0 else 0.01
            hotspots.append({"lat": lat, "lng": lng, "desc": desc, "weight": weight})

        total_hotspot_weight = sum(spot["weight"] for spot in hotspots)
        if total_hotspot_weight > 0:
            for spot in hotspots: spot["weight"] /= total_hotspot_weight
        
        vehicle_types = self.env_config.get("vehicle_types", {}) # Already available
        user_types_config = self.env_config.get("user_types", {}) # Already available
        user_type_options = list(user_types_config.keys()) if user_types_config else ["private"]

        # User Profile and Type Parameters from init_params
        user_type_base_weights = self.init_params.get('user_type_base_weights', {"private": 1.0})
        user_profile_options = self.init_params.get('user_profile_options', ["flexible"])
        user_profile_base_probs = self.init_params.get('user_profile_base_probs', [1.0])
        user_profile_probs_by_type = self.init_params.get('user_profile_probs_by_type', {})
        user_profile_low_soc_boost = self.init_params.get('user_profile_low_soc_urgent_boost', 0.2)
        
        # Other user initialization parameters
        travel_speed_min_kmh = self.init_params.get('user_travel_speed_min_kmh', 30)
        travel_speed_max_kmh = self.init_params.get('user_travel_speed_max_kmh', 65)
        default_charging_efficiency = self.init_params.get('user_default_charging_efficiency', 0.92)
        driving_style_options_list = self.init_params.get('user_driving_style_options', ["normal"])
        driving_style_weights_list = self.init_params.get('user_driving_style_weights', [1.0])
        sensitivity_profile_adjustments = self.init_params.get('user_sensitivity_profile_adjustments', {})


        for i in range(self.user_count): # Use self.user_count
            user_id = f"user_{i+1}"
            vehicle_type = random.choice(list(vehicle_types.keys())) if vehicle_types else "sedan"
            
            # User Type Selection
            valid_types_for_choice = [utype for utype in user_type_options if utype in user_type_base_weights]
            if not valid_types_for_choice: valid_types_for_choice = user_type_options if user_type_options else ["private"]
            
            current_type_weights = [user_type_base_weights.get(utype, 1.0/len(valid_types_for_choice) if len(valid_types_for_choice)>0 else 1.0) for utype in valid_types_for_choice]
            sum_type_weights = sum(current_type_weights)
            if sum_type_weights > 0: current_type_weights = [w/sum_type_weights for w in current_type_weights]
            else: current_type_weights = [1.0/len(valid_types_for_choice)] * len(valid_types_for_choice) if valid_types_for_choice else []
            user_type = random.choices(valid_types_for_choice, weights=current_type_weights, k=1)[0] if valid_types_for_choice and current_type_weights else "private"

            # SOC Initialization
            rand_soc_val = random.random(); cumulative_prob = 0; soc_range_sel = (10, 90) # Default soc_range_sel
            for prob, range_val_soc in soc_ranges:
                cumulative_prob += prob
                if rand_soc_val <= cumulative_prob: soc_range_sel = range_val_soc; break
            soc = random.uniform(soc_range_sel[0], soc_range_sel[1])

            # User Profile Selection
            profile_probs_specific = user_profile_probs_by_type.get(user_type, user_profile_base_probs)
            profile_probs_current = list(profile_probs_specific) # Make a mutable copy

            if soc < 30: # Example: if low SOC, slightly boost 'urgent'
                try:
                    urgent_idx = user_profile_options.index('urgent')
                    if len(profile_probs_current) > urgent_idx:
                         profile_probs_current[urgent_idx] = min(1.0, profile_probs_current[urgent_idx] + user_profile_low_soc_boost)
                except ValueError: pass # 'urgent' not in options

            sum_profile_probs = sum(profile_probs_current) 
            if sum_profile_probs > 0: profile_probs_current = [p / sum_profile_probs for p in profile_probs_current]
            else: profile_probs_current = [1.0/len(user_profile_options)] * len(user_profile_options) if user_profile_options else []
            user_profile = random.choices(user_profile_options, weights=profile_probs_current, k=1)[0] if user_profile_options and profile_probs_current else "flexible"
            
            vehicle_info = vehicle_types.get(vehicle_type, list(vehicle_types.values())[0] if vehicle_types else {})
            battery_capacity = vehicle_info.get("battery_capacity", 60)
            max_range = vehicle_info.get("max_range", 400)
            current_range = max_range * (soc / 100)
            max_charging_power = vehicle_info.get("max_charging_power", 60)

            if hotspots and random.random() < 0.7: 
                 chosen_hotspot = random.choices(hotspots, weights=[spot.get("weight",0.1) for spot in hotspots], k=1)[0]
                 radius = random.gauss(0, 0.03); angle = random.uniform(0, 2 * math.pi)
                 lat = chosen_hotspot["lat"] + radius * math.cos(angle)
                 lng = chosen_hotspot["lng"] + radius * math.sin(angle)
            else:
                 lat = random.uniform(map_bounds["lat_min"], map_bounds["lat_max"])
                 lng = random.uniform(map_bounds["lng_min"], map_bounds["lng_max"])
            lat = min(max(lat, map_bounds["lat_min"]), map_bounds["lat_max"])
            lng = min(max(lng, map_bounds["lng_min"]), map_bounds["lng_max"])
            
            status_probs = {"idle": 0.7, "traveling": 0.3}; 
            if soc < 30: status_probs = {"idle": 0.3, "traveling": 0.7} 
            elif soc < 60: status_probs = {"idle": 0.6, "traveling": 0.4}
            status = random.choices(list(status_probs.keys()), weights=list(status_probs.values()))[0]
            
            travel_speed = random.uniform(travel_speed_min_kmh, travel_speed_max_kmh)

            users[user_id] = {
                "user_id": user_id, "vehicle_type": vehicle_type, "user_type": user_type,
                "user_profile": user_profile, "battery_capacity": battery_capacity, "soc": soc,
                "max_range": max_range, "current_range": current_range,
                "current_position": {"lat": lat, "lng": lng}, "status": status,
                "target_charger": None, "charging_history": [], "travel_speed": travel_speed,
                "route": [], "waypoints": [], "destination": None, "time_to_destination": None,
                "traveled_distance": 0, "charging_efficiency": default_charging_efficiency,
                "max_charging_power": max_charging_power,
                "driving_style": random.choices(driving_style_options_list, weights=driving_style_weights_list, k=1)[0] if driving_style_options_list and driving_style_weights_list else "normal",
                "needs_charge_decision": False, "time_sensitivity": 0.5, "price_sensitivity": 0.5, 
                "range_anxiety": 0.0, "last_destination_type": None, "_current_segment_index": 0 
            }
            
            user_type_detail_config = user_types_config.get(user_type, {}) # from top-level env_config.user_types
            base_time_sensitivity = user_type_detail_config.get("time_sensitivity", 0.5)
            base_price_sensitivity = user_type_detail_config.get("price_sensitivity", 0.5)
            base_range_anxiety = user_type_detail_config.get("range_anxiety", 0.3)
            base_fast_charging_preference = user_type_detail_config.get("fast_charging_preference", 0.5)
            
            # Corrected variable name here:
            profile_sensitivity_config = sensitivity_profile_adjustments.get(user_profile, {}) # from init_params
            
            ts_range = profile_sensitivity_config.get("time_sensitivity", [0.9, 1.1])
            ps_range = profile_sensitivity_config.get("price_sensitivity", [0.9, 1.1])
            ra_range = profile_sensitivity_config.get("range_anxiety", [0.9, 1.1])
            fc_range = profile_sensitivity_config.get("fast_charging_preference", [0.9, 1.1])

            users[user_id]["time_sensitivity"] = min(1.0, max(0.0, base_time_sensitivity * random.uniform(ts_range[0], ts_range[1])))
            users[user_id]["price_sensitivity"] = min(1.0, max(0.0, base_price_sensitivity * random.uniform(ps_range[0], ps_range[1])))
            users[user_id]["range_anxiety"] = min(1.0, max(0.0, base_range_anxiety * random.uniform(ra_range[0], ra_range[1])))
            users[user_id]["fast_charging_preference"] = min(1.0, max(0.0, base_fast_charging_preference * random.uniform(fc_range[0], fc_range[1])))

        logger.info(f"Initialized {len(users)} users.")
        return users

    def _initialize_chargers(self):
        """初始化充电站和充电桩 (使用完整的详细逻辑)"""
        chargers = {}
        logger.info(f"Initializing {self.station_count} stations, aiming for approx {self.chargers_per_station} chargers/station...")

        failure_rate = self.env_config.get("charger_failure_rate", 0.0) # General env param
        charger_defaults_env = self.env_config.get("charger_defaults", {}) # General env param for charger types, power, price mult
        
        superfast_ratio = charger_defaults_env.get("superfast_ratio", 0.1) 
        fast_ratio = charger_defaults_env.get("fast_ratio", 0.4)
        power_ranges = charger_defaults_env.get("power_ranges", {"superfast": [250, 400], "fast": [60, 120], "normal": [7, 20]})
        price_multipliers = charger_defaults_env.get("price_multipliers", {"superfast": 1.5, "fast": 1.2, "normal": 1.0})
        
        queue_capacity = self.env_config.get("charger_queue_capacity", 5) # General env param
        
        charger_location_spread = self.init_params.get('charger_location_spread_degrees', 0.002)
        charger_fallback_power = self.init_params.get('charger_fallback_power_kw', 50)


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

                if pr and isinstance(pr, list) and len(pr) == 2 and all(isinstance(p, (int, float)) for p in pr):
                     charger_power = random.uniform(pr[0], pr[1])
                else:
                     charger_power = charger_fallback_power 
                     logger.warning(f"Invalid power range defined for type '{charger_type}': {pr}. Using fallback {charger_fallback_power}kW.")

                is_failure = random.random() < failure_rate

                chargers[charger_id] = {
                    "charger_id": charger_id, "location": location["name"], "type": charger_type,
                    "max_power": round(charger_power, 1),
                    "position": {"lat": location["lat"] + random.uniform(-charger_location_spread, charger_location_spread), 
                                 "lng": location["lng"] + random.uniform(-charger_location_spread, charger_location_spread)},
                    "status": "failure" if is_failure else "available", "current_user": None, "queue": [],
                    "queue_capacity": queue_capacity, "daily_revenue": 0.0, "daily_energy": 0.0,
                    "price_multiplier": p_mult if isinstance(p_mult, (int, float)) else 1.0, 
                    "region": f"Region_{random.randint(1, self.region_count)}"
                }
                current_id += 1

        self.charger_count = len(chargers) 
        logger.info(f"Initialized {self.charger_count} chargers across {self.station_count} stations.")
        return chargers

    def step(self, decisions, manual_decisions=None, v2g_request_mw=None, scheduler_metadata=None):
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
        # The 'decisions' argument now comes directly from the scheduler in the main loop
        final_decisions = {}
        if decisions and isinstance(decisions, dict):
            final_decisions.update(decisions)
        if manual_decisions and isinstance(manual_decisions, dict):
            final_decisions.update(manual_decisions)
            logger.info(f"Applied {len(manual_decisions)} manual decisions")
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
                        
                        if plan_route_to_charger(user, charger_pos, self.map_bounds, self.user_model_params):
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
            self.chargers, self.users, self.current_time, self.time_step_minutes, current_grid_status, self.config
        )
        

        # `completed_sessions_this_step`现在已经包含了成本和收入，直接保存即可
        if completed_sessions_this_step:
            from data_storage import operator_storage
            for session in completed_sessions_this_step:
                # 确保会话ID是唯一的
                session_id = f"{session['user_id']}_{session['charger_id']}_{session['end_time']}"
                session['session_id'] = session_id
                
                # 直接保存，因为所有财务数据已在charger_model中计算好
                operator_storage.save_charging_session(session)
            logger.info(f"Saved {len(completed_sessions_this_step)} completed charging sessions to the database.")

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

        # 保存历史状态，并传入 scheduler_metadata
        self._save_current_state(rewards, scheduler_metadata)

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
            "grid_status": self.grid_simulator.get_status(), 
            "history": self.history[-self.user_model_params.get('history_max_steps_snapshot', 96):]
        }
        return state


    def _save_current_state(self, rewards, scheduler_metadata=None): # Added scheduler_metadata
        """保存当前的关键状态和奖励到历史记录"""
        latest_grid_status = self.grid_simulator.get_status()
        state_snapshot = {
            "timestamp": self.current_time.isoformat(),
            "grid_status": { 
                "aggregated_metrics": latest_grid_status.get("aggregated_metrics", {}),
                "regional_current_state": latest_grid_status.get("regional_current_state", {}),
            },
            "rewards": rewards,
            "scheduler_metadata": scheduler_metadata if scheduler_metadata else {}
        }
        self.history.append(state_snapshot)
        
        max_hist_steps = self.user_model_params.get('simulation_history_max_steps', 1000)
        if len(self.history) > max_hist_steps:
            self.history = self.history[-max_hist_steps:]