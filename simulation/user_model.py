# ev_charging_project/simulation/user_model.py
import random
import math
from datetime import datetime, timedelta
import logging
from .utils import calculate_distance, get_random_location # 使用相对导入
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

def simulate_step(users, chargers, current_time, time_step_minutes, config):
    """
    模拟所有用户的行为，特别处理手动决策用户
    """
    time_step_hours = time_step_minutes / 60.0
    env_config = config.get('environment', {}) # Top-level 'environment' key
    user_model_params = env_config.get('user_model_params', {}) # Specific user model params
    
    map_bounds = env_config.get("map_bounds", { # map_bounds is still under top-level 'environment'
        "lat_min": 30.5, "lat_max": 31.0, "lng_min": 114.0, "lng_max": 114.5
    })

    for user_id, user in list(users.items()):
        if not isinstance(user, dict):
            logger.warning(f"Invalid user data found for ID {user_id}. Skipping.")
            continue

        current_soc = user.get("soc", 0)
        user_status = user.get("status", "idle")
        battery_capacity = user.get("battery_capacity", 60)
        is_manual_decision = user.get("manual_decision", False)

        # 手动决策用户的特殊处理
        if is_manual_decision:
            # 手动决策用户减少随机行为，更确定地执行决策
            if user_status == "traveling" and user.get("target_charger"):
                manual_speed_mult = user_model_params.get('manual_decision_travel_speed_multiplier', 2.0)
                travel_speed = user.get("travel_speed", 45) * manual_speed_mult
                user["travel_speed"] = travel_speed
                
                current_time_to_dest = user.get("time_to_destination", 0)
                reduction_thresh = user_model_params.get('manual_decision_time_to_dest_reduction_threshold_minutes', 5.0)
                reduction_factor = user_model_params.get('manual_decision_time_to_dest_reduction_factor', 0.3)
                if current_time_to_dest > reduction_thresh:
                    user["time_to_destination"] = max(1, current_time_to_dest * reduction_factor)
                    logger.debug(f"Manual decision user {user_id} accelerated travel: time reduced to {user['time_to_destination']:.1f} minutes")
                
                logger.debug(f"Manual decision user {user_id} traveling at enhanced speed: {travel_speed:.1f} km/h")
            
            # 手动决策用户不会改变充电需求
            user["needs_charge_decision"] = False

        # 原有的用户行为模拟逻辑...
        # 后充电状态处理
        if user_status == "post_charge":
            if user.get("post_charge_timer") is None:
                # 根据用户类型设置不同的停留时间
                if user.get("user_type") == "taxi" or user.get("user_type") == "ride_hailing":
                    user["post_charge_timer"] = random.randint(1, 2)  # 出租车和网约车停留时间短
                elif user.get("user_type") == "logistics" or user.get("user_type") == "delivery":
                    user["post_charge_timer"] = random.randint(1, 3)  # 物流车和配送车停留时间中等
                else:
                    user["post_charge_timer"] = random.randint(2, 5)  # 私家车停留时间较长
            if user["post_charge_timer"] > 0:
                user["post_charge_timer"] -= 1
            else:
                # 清除所有手动决策相关标记
                if user.get("manual_decision"):
                    logger.info(f"=== MANUAL DECISION CLEARED (Post-charge timer expired) ===")
                    logger.info(f"User {user_id} manual decision cleared after charging completion")
                    logger.info(f"Final SOC: {user.get('soc', 0):.1f}%")
                    logger.info(f"User {user_id} now eligible for normal scheduling")
                user["manual_decision"] = False
                user["manual_decision_locked"] = False
                user["manual_decision_override"] = False
                user["manual_charging_params"] = None
                
                logger.debug(f"User {user_id} post-charge timer expired.")
                
                # 根据用户类型和时间选择目的地
                new_destination = get_destination_by_user_type_and_time(user, current_time, map_bounds)
                while calculate_distance(user.get("current_position", {}), new_destination) < 0.1:
                    new_destination = get_destination_by_user_type_and_time(user, current_time, map_bounds)

                user["status"] = "traveling"
                user["target_charger"] = None
                user["post_charge_timer"] = None
                user["needs_charge_decision"] = False
                user["last_destination_type"] = "random"
                
                if plan_route_to_destination(user, new_destination, map_bounds, user_model_params):
                    logger.debug(f"User {user_id} planned route to new destination after charging.")
                else:
                    logger.warning(f"User {user_id} failed to plan route. Setting idle.")
                    user["status"] = "idle"
                    user["destination"] = None

        # 电量消耗（对手动决策用户同样适用）
        if user_status not in ["charging", "waiting"]:
            # Configurable Idle Energy Consumption Logic
            idle_cfg = user_model_params.get("idle_consumption_params", {})
            
            idle_consumption_rate_kw = idle_cfg.get("base_kw", 0.4)
            vehicle_type = user.get("vehicle_type", "sedan")
            
            type_multipliers = idle_cfg.get("vehicle_type_multipliers", {})
            idle_consumption_rate_kw *= type_multipliers.get(vehicle_type, type_multipliers.get("default", 1.0))

            current_month = current_time.month
            season_cfg = idle_cfg.get("season_factors", {})
            if current_month in season_cfg.get("summer_months", [6,7,8]):
                idle_consumption_rate_kw *= season_cfg.get("summer_factor", 1.0)
            elif current_month in season_cfg.get("winter_months", [12,1,2]):
                idle_consumption_rate_kw *= season_cfg.get("winter_factor", 1.0)
            else:
                idle_consumption_rate_kw *= season_cfg.get("default_factor", 1.0)

            hour = current_time.hour
            time_cfg = idle_cfg.get("time_factors", {})
            if hour in time_cfg.get("peak_hours", []):
                idle_consumption_rate_kw *= time_cfg.get("peak_factor", 1.0)
            elif time_cfg.get("night_hours_start", 22) <= hour or hour < time_cfg.get("night_hours_end", 4): # Handles wrap-around midnight
                idle_consumption_rate_kw *= time_cfg.get("night_factor", 1.0)
            else:
                idle_consumption_rate_kw *= time_cfg.get("default_factor", 1.0)

            behavior_min = idle_cfg.get("behavior_factor_min", 0.9)
            behavior_max = idle_cfg.get("behavior_factor_max", 1.8)
            idle_consumption_rate_kw *= random.uniform(behavior_min, behavior_max)

            idle_energy_used_kwh = idle_consumption_rate_kw * time_step_hours
            idle_soc_decrease = (idle_energy_used_kwh / battery_capacity) * 100 if battery_capacity > 0 else 0
            user["soc"] = max(0, user.get("soc", 0) - idle_soc_decrease)
            current_soc = user["soc"] # Ensure current_soc is updated after consumption

        # 检查充电需求（手动决策用户跳过）
        if not is_manual_decision:
            user["needs_charge_decision"] = False
            if user_status in ["idle", "traveling", "post_charge"] and not user.get("target_charger"):
                estimated_charge_amount = 100 - current_soc
                MIN_CHARGE_AMOUNT_THRESHOLD = config.get('environment',{}).get('min_charge_threshold_percent', 25.0)
                
                if estimated_charge_amount < MIN_CHARGE_AMOUNT_THRESHOLD:
                    pass
                elif current_soc <= config.get('environment',{}).get('force_charge_soc_threshold', 20.0): # This threshold is from general env_config
                    user["needs_charge_decision"] = True
                    logger.debug(f"User {user_id} SOC critical, forcing charge need.")
                else:
                    charging_prob = calculate_charging_probability(user, current_time.hour, config, user_model_params)
                    # The detailed factor adjustments are now inside calculate_charging_probability
                    if random.random() < charging_prob:
                        user["needs_charge_decision"] = True

        # 基于充电需求的状态转换
        if (user["needs_charge_decision"] and user_status in ["idle", "traveling"] and 
            (user.get("last_destination_type") == "random" or user_status == "idle")):
            logger.info(f"User {user_id} (SOC: {current_soc:.1f}%) flagged as needing charging decision.")
            if user_status == "traveling":
                user["status"] = "idle"
                user["destination"] = None
                user["route"] = None
                logger.debug(f"User {user_id} stopped random travel to wait for charge decision.")

        # 移动模拟
        if user_status == "traveling" and user.get("destination"):
            travel_speed = user.get("travel_speed", 45)
            if travel_speed <= 0: travel_speed = 45

            distance_this_step = travel_speed * time_step_hours
            actual_distance_moved = update_user_position_along_route(user, distance_this_step, map_bounds, user_model_params)

            #行驶能耗计算 (Configurable Travel Energy Consumption Logic)
            travel_energy_cfg = user_model_params.get("travel_energy_params", {})
            
            base_kwh_per_km = travel_energy_cfg.get("base_kwh_per_km", 0.25)
            speed_factor_denom = travel_energy_cfg.get("speed_factor_for_base_kwh", 80.0)
            if speed_factor_denom == 0: speed_factor_denom = 80.0 # Avoid division by zero

            energy_per_km = base_kwh_per_km * (1 + (travel_speed / speed_factor_denom))
            
            vehicle_type = user.get("vehicle_type", "sedan")
            vehicle_multipliers = travel_energy_cfg.get("vehicle_type_multipliers", {})
            energy_per_km *= vehicle_multipliers.get(vehicle_type, vehicle_multipliers.get("default", 1.0))
            
            driving_style = user.get("driving_style", "normal")
            style_multipliers = travel_energy_cfg.get("driving_style_multipliers", {})
            energy_per_km *= style_multipliers.get(driving_style, style_multipliers.get("normal", 1.0))
            
            road_min = travel_energy_cfg.get("road_condition_factor_min", 1.0)
            road_max = travel_energy_cfg.get("road_condition_factor_max", 1.0) # Default to 1.0 if max is less than min
            if road_max < road_min: road_max = road_min 
            energy_per_km *= random.uniform(road_min, road_max)
            
            weather_min = travel_energy_cfg.get("weather_impact_factor_min", 1.0)
            weather_max = travel_energy_cfg.get("weather_impact_factor_max", 1.0)
            if weather_max < weather_min: weather_max = weather_min
            energy_per_km *= random.uniform(weather_min, weather_max)
            
            traffic_factor = travel_energy_cfg.get("traffic_factor_default", 1.0)
            hour = current_time.hour
            peak_hours_key = travel_energy_cfg.get("traffic_factor_peak_hours_config_key", "peak_hours")
            # Access peak_hours from the main config's grid section
            peak_hours = config.get('grid', {}).get(peak_hours_key, [])
            if hour in peak_hours:
                traffic_peak_min = travel_energy_cfg.get("traffic_factor_peak_min", 1.0)
                traffic_peak_max = travel_energy_cfg.get("traffic_factor_peak_max", 1.0)
                if traffic_peak_max < traffic_peak_min: traffic_peak_max = traffic_peak_min
                traffic_factor = random.uniform(traffic_peak_min, traffic_peak_max)
            energy_per_km *= traffic_factor

            energy_consumed_kwh = actual_distance_moved * energy_per_km
            soc_decrease_travel = (energy_consumed_kwh / battery_capacity) * 100 if battery_capacity > 0 else 0
            user["soc"] = max(0, user["soc"] - soc_decrease_travel)
            # current_soc should be updated if it's used later in the same step after this block

            time_taken_minutes = (actual_distance_moved / travel_speed) * 60 if travel_speed > 0 else 0
            user["time_to_destination"] = max(0, user.get("time_to_destination", 0) - time_taken_minutes)

            # 检查是否到达
            if has_reached_destination(user, user_model_params):
                logger.debug(f"User {user_id} arrived at destination.")
                user["current_position"] = user["destination"].copy()
                user["time_to_destination"] = 0
                user["route"] = None

                target_charger_id = user.get("target_charger")
                last_dest_type = user.get("last_destination_type")

                if target_charger_id:
                    logger.info(f"User {user_id} arrived at target charger {target_charger_id}. Setting status to WAITING.")
                    user["status"] = "waiting"
                    user["destination"] = None
                    user["arrival_time_at_charger"] = current_time
                    
                    # 如果是手动决策用户，记录到达时间并强制锁定到目标充电桩
                    if is_manual_decision:
                        user["manual_decision_arrival_time"] = current_time.isoformat()
                        user["force_target_charger"] = True  # 强制锁定到目标充电桩
                        user["manual_decision_locked"] = True  # 防止被重新分配
                        logger.info(f"=== MANUAL DECISION USER LOCKED TO TARGET CHARGER ===")
                        logger.info(f"Manual decision user {user_id} arrived and LOCKED to charger {target_charger_id}")
                        logger.info(f"User will ONLY charge at this specific charger, ignoring system allocation")
                        
                elif last_dest_type == "charger":
                    logger.warning(f"User {user_id} arrived at charger destination, but target_charger ID is None. Setting WAITING.")
                    user["status"] = "waiting"
                    user["destination"] = None
                    user["arrival_time_at_charger"] = current_time
                else:
                    logger.info(f"User {user_id} reached random destination. Setting IDLE.")
                    user["status"] = "idle"
                    user["destination"] = None
                    user["target_charger"] = None
                    # 清除手动决策标记
                    if user.get("manual_decision"):
                        logger.info(f"=== MANUAL DECISION CLEARED (Destination reached) ===")
                        logger.info(f"User {user_id} manual decision cleared upon reaching destination")
                        logger.info(f"Current SOC: {user.get('soc', 0):.1f}%")
                    user["manual_decision"] = False
                    if user["soc"] < 70: user["needs_charge_decision"] = True

        # 更新最终用户续航里程
        user["current_range"] = user.get("max_range", 300) * (user["soc"] / 100)
# --- 辅助函数 ---

def get_destination_by_user_type_and_time(user, current_time, map_bounds):
    """根据用户类型和当前时间生成合适的目的地"""
    user_type = user.get("user_type", "private")
    hour = current_time.hour
    day_of_week = current_time.weekday()  # 0-6，0是周一
    is_weekend = day_of_week >= 5  # 周六和周日
    
    # 定义不同区域的权重
    weights = {
        "residential": 0.3,  # 住宅区
        "business": 0.2,    # 商业区
        "industrial": 0.1,  # 工业区
        "entertainment": 0.1,  # 娱乐区
        "suburban": 0.1,    # 郊区
        "random": 0.2       # 完全随机
    }
    
    # 根据用户类型调整权重
    if user_type == "private":
        if 7 <= hour <= 9 and not is_weekend:  # 工作日早高峰
            weights["business"] = 0.6
            weights["residential"] = 0.1
            weights["random"] = 0.1
        elif 17 <= hour <= 19 and not is_weekend:  # 工作日晚高峰
            weights["residential"] = 0.6
            weights["business"] = 0.1
            weights["random"] = 0.1
        elif 22 <= hour or hour <= 5:  # 夜间
            weights["residential"] = 0.7
            weights["random"] = 0.1
    elif user_type == "commuter":
        if 7 <= hour <= 9 and not is_weekend:  # 工作日早高峰
            weights["business"] = 0.8
            weights["residential"] = 0.1
            weights["random"] = 0.1
        elif 17 <= hour <= 19 and not is_weekend:  # 工作日晚高峰
            weights["residential"] = 0.8
            weights["business"] = 0.1
            weights["random"] = 0.1
        elif 22 <= hour or hour <= 5:  # 夜间
            weights["residential"] = 0.9
            weights["random"] = 0.1
    elif user_type in ["taxi", "ride_hailing"]:
        if 7 <= hour <= 9 or 17 <= hour <= 19:  # 高峰期
            weights["business"] = 0.4
            weights["residential"] = 0.3
            weights["entertainment"] = 0.2
            weights["random"] = 0.1
        elif 9 < hour < 17:  # 工作时间
            weights["business"] = 0.3
            weights["residential"] = 0.2
            weights["random"] = 0.3
        elif 19 < hour < 22:  # 晚间
            weights["entertainment"] = 0.4
            weights["residential"] = 0.3
            weights["random"] = 0.2
        else:  # 深夜
            weights["residential"] = 0.4
            weights["entertainment"] = 0.2
            weights["random"] = 0.3
    elif user_type in ["logistics", "delivery"]:
        if 8 <= hour <= 18:  # 工作时间
            weights["business"] = 0.3
            weights["residential"] = 0.3
            weights["industrial"] = 0.3
            weights["random"] = 0.1
        else:  # 非工作时间
            weights["industrial"] = 0.5
            weights["business"] = 0.2
            weights["random"] = 0.3
    elif user_type == "business":
        if 8 <= hour <= 18 and not is_weekend:  # 工作日工作时间
            weights["business"] = 0.7
            weights["random"] = 0.3
        elif is_weekend:  # 周末
            weights["entertainment"] = 0.4
            weights["residential"] = 0.3
            weights["random"] = 0.3
        else:  # 工作日非工作时间
            weights["residential"] = 0.6
            weights["random"] = 0.4
    
    # 根据权重选择区域类型
    area_types = list(weights.keys())
    area_weights = list(weights.values())
    selected_area = random.choices(area_types, weights=area_weights, k=1)[0]
    
    # 根据区域类型生成具体坐标
    if selected_area == "random":
        return get_random_location(map_bounds)
    
    # 为不同区域定义中心点和半径
    area_centers = {
        "residential": {"lat": map_bounds["lat_min"] + (map_bounds["lat_max"] - map_bounds["lat_min"]) * 0.3, 
                       "lng": map_bounds["lng_min"] + (map_bounds["lng_max"] - map_bounds["lng_min"]) * 0.3},
        "business": {"lat": map_bounds["lat_min"] + (map_bounds["lat_max"] - map_bounds["lat_min"]) * 0.7, 
                     "lng": map_bounds["lng_min"] + (map_bounds["lng_max"] - map_bounds["lng_min"]) * 0.7},
        "industrial": {"lat": map_bounds["lat_min"] + (map_bounds["lat_max"] - map_bounds["lat_min"]) * 0.5, 
                       "lng": map_bounds["lng_min"] + (map_bounds["lng_max"] - map_bounds["lng_min"]) * 0.2},
        "entertainment": {"lat": map_bounds["lat_min"] + (map_bounds["lat_max"] - map_bounds["lat_min"]) * 0.6, 
                          "lng": map_bounds["lng_min"] + (map_bounds["lng_max"] - map_bounds["lng_min"]) * 0.5},
        "suburban": {"lat": map_bounds["lat_min"] + (map_bounds["lat_max"] - map_bounds["lat_min"]) * 0.2, 
                     "lng": map_bounds["lng_min"] + (map_bounds["lng_max"] - map_bounds["lng_min"]) * 0.8}
    }
    
    # 在选定区域周围生成随机位置
    center = area_centers[selected_area]
    radius = 0.05  # 约5公里半径
    
    # 生成区域内随机点
    r = radius * math.sqrt(random.random())
    theta = random.uniform(0, 2 * math.pi)
    
    lat = center["lat"] + r * math.cos(theta)
    lng = center["lng"] + r * math.sin(theta)
    
    # 确保坐标在地图范围内
    lat = min(max(lat, map_bounds["lat_min"]), map_bounds["lat_max"])
    lng = min(max(lng, map_bounds["lng_min"]), map_bounds["lng_max"])
    
    return {"lat": lat, "lng": lng}

def calculate_charging_probability(user, current_hour, config, user_model_params): # Added user_model_params
    """计算用户决定寻求充电的概率 (使用原详细逻辑)"""
    # (从原 ChargingEnvironment._calculate_charging_probability 复制逻辑)
    current_soc = user.get("soc", 100)
    user_type = user.get("user_type", "commuter")
    profile = user.get("user_profile", "balanced") 
    fast_charging_preference = user.get("fast_charging_preference", 0.5)

    # Check min charge amount - this is from top-level environment config, not user_model_params directly
    min_charge_amount_env = config.get('environment',{}).get('min_charge_threshold_percent', 25.0)
    if (100 - current_soc) < min_charge_amount_env:
        return 0.0

    # 1. Base probability using sigmoid
    # Make the sigmoid curve more aggressive. Lower the midpoint and increase steepness.
    mid = user_model_params.get('charging_prob_sigmoid_midpoint', 35) # Lowered from 40 to 35
    steep = user_model_params.get('charging_prob_sigmoid_steepness', 0.15) # Increased from 0.1 to 0.15
    base_prob = 1 / (1 + math.exp(steep * (current_soc - mid)))
    
    min_clamp = user_model_params.get('charging_prob_min_clamp', 0.05)
    max_clamp = user_model_params.get('charging_prob_max_clamp', 0.95)
    base_prob = min(max_clamp, max(min_clamp, base_prob))

    # SOC reduction factors (This part remains, it prevents users with very high SOC from charging)
    soc_reduct_thresh = user_model_params.get('charging_probability_soc_thresholds_for_reduction', [75, 60])
    soc_reduct_factors = user_model_params.get('charging_probability_soc_reduction_factors', [0.1, 0.3])
    if current_soc > soc_reduct_thresh[0]: base_prob *= soc_reduct_factors[0]
    elif current_soc > soc_reduct_thresh[1]: base_prob *= soc_reduct_factors[1]

    # User type factor
    type_factors = user_model_params.get('charging_prob_user_type_factors', {})
    type_factor_adj = type_factors.get(user_type, 0.0)

    # Time preference factor (valley/shoulder)
    time_pref_factors = user_model_params.get('charging_prob_time_preference_factors', {})
    grid_config = config.get('grid', {}) # Need peak_hours, valley_hours from grid_config
    peak_hours_list = grid_config.get('peak_hours', [])
    valley_hours_list = grid_config.get('valley_hours', [])
    
    time_factor_adj = 0.0
    if current_hour in valley_hours_list: time_factor_adj = time_pref_factors.get('valley', 0.0)
    elif current_hour not in peak_hours_list: time_factor_adj = time_pref_factors.get('shoulder', 0.0)
        
    # Profile factor
    profile_adj_factors = user_model_params.get('charging_prob_profile_factors', {})
    profile_factor_adj = profile_adj_factors.get(profile, 0.0)
    
    # NEW: Range anxiety factor
    anxiety_factor_adj = 0.0
    range_anxiety = user.get('range_anxiety', 0.3) # Default to 0.3 if not present
    # Anxiety has a larger effect when SOC is moderately high, encouraging early charging
    if 35 < current_soc < 75:
        # Scale the effect: more anxiety and lower SOC (within this range) = higher probability
        # Strengthen the anxiety boost
        anxiety_boost = range_anxiety * ((75 - current_soc) / 40.0) * 0.25 # Increased from 0.15 to 0.25
        anxiety_factor_adj = anxiety_boost
    
    # Fast charging preference factor
    fast_charge_pref_factor_adj = 0.0
    fc_pref_high_soc_min = user_model_params.get('charging_prob_fast_charging_pref_factor_high_soc_min', 40)
    fc_pref_high_soc_max = user_model_params.get('charging_prob_fast_charging_pref_factor_high_soc_max', 60)
    fc_pref_high_boost = user_model_params.get('charging_prob_fast_charging_pref_factor_high_pref_boost', 0.1)
    
    fc_pref_low_soc_min = user_model_params.get('charging_prob_fast_charging_pref_factor_low_soc_min', 30)
    fc_pref_low_penalty = user_model_params.get('charging_prob_fast_charging_pref_factor_low_pref_penalty', -0.1)

    if fast_charging_preference > 0.7: # High preference
        if fc_pref_high_soc_min <= current_soc <= fc_pref_high_soc_max:
            fast_charge_pref_factor_adj = fc_pref_high_boost * (fast_charging_preference - 0.7) / 0.3
    elif fast_charging_preference < 0.3: # Low preference
        if current_soc > fc_pref_low_soc_min: # Penalty if SOC is not that low
            fast_charge_pref_factor_adj = fc_pref_low_penalty * (0.3 - fast_charging_preference) / 0.3
            
    # Emergency boost (uses force_charge_soc_threshold from top-level environment config)
    emergency_boost_adj = 0.0
    force_charge_soc_env = config.get('environment',{}).get('force_charge_soc_threshold', 20.0)
    emergency_soc_offset = user_model_params.get('charging_prob_emergency_boost_soc_offset', 5)
    emergency_max_factor = user_model_params.get('charging_prob_emergency_boost_max_factor', 0.4)

    if current_soc <= force_charge_soc_env + emergency_soc_offset:
        boost_range = force_charge_soc_env + emergency_soc_offset - force_charge_soc_env
        emergency_boost_adj = emergency_max_factor * (1 - (current_soc - force_charge_soc_env) / boost_range) if current_soc > force_charge_soc_env and boost_range > 0 else emergency_max_factor
        emergency_boost_adj = max(0, emergency_boost_adj) # Ensure non-negative boost

    charging_prob = base_prob + type_factor_adj + time_factor_adj + profile_factor_adj + fast_charge_pref_factor_adj + emergency_boost_adj + anxiety_factor_adj # Added anxiety_factor_adj
    return min(1.0, max(0.0, charging_prob))
def plan_route(user, start_pos, end_pos, map_bounds, user_model_params): # Added user_model_params
    """规划通用路线（使用原详细逻辑，如果需要）"""
    # (从原 ChargingEnvironment._plan_route_to_charger/destination 复制完整逻辑)
    user["route"] = []
    user["waypoints"] = []
    user["destination"] = end_pos.copy()

    # 安全地获取坐标，提供默认值
    start_lng = start_pos.get("lng", map_bounds['lng_min'])
    start_lat = start_pos.get("lat", map_bounds['lat_min'])
    end_lng = end_pos.get("lng", map_bounds['lng_min'])
    end_lat = end_pos.get("lat", map_bounds['lat_min'])

    dx = end_lng - start_lng
    dy = end_lat - start_lat
    distance = calculate_distance(start_pos, end_pos)

    # 生成路径点 (原逻辑)
    num_points = random.randint(2, 4)
    waypoints = []
    for i in range(1, num_points):
        t = i / num_points
        point_lng = start_lng + t * dx
        point_lat = start_lat + t * dy
        # 添加随机偏移
        perp_dx = -dy
        perp_dy = dx
        perp_len = math.sqrt(perp_dx**2 + perp_dy**2)
        if perp_len > 0:
            perp_dx /= perp_len
            perp_dy /= perp_len
        offset_magnitude = random.uniform(-0.1, 0.1) * distance / 111 # Convert dist back to coord scale
        point_lng += perp_dx * offset_magnitude
        point_lat += perp_dy * offset_magnitude
        waypoints.append({"lat": point_lat, "lng": point_lng})

    user["waypoints"] = waypoints
    full_route = [start_pos.copy()] + waypoints + [end_pos.copy()]
    user["route"] = full_route

    # 计算总距离
    total_distance = 0
    for i in range(1, len(full_route)):
        p1 = full_route[i-1]
        p2 = full_route[i]
        total_distance += calculate_distance(p1, p2)

    # 计算时间
    travel_speed = user.get("travel_speed", 45)
    if travel_speed <= 0: travel_speed = 45
    travel_time_minutes = (total_distance / travel_speed) * 60 if travel_speed > 0 else float('inf')

    user["time_to_destination"] = travel_time_minutes
    user["traveled_distance"] = 0
    return True

def plan_route_to_charger(user, charger_pos, map_bounds, user_model_params): # Added user_model_params
    """规划用户到充电桩的路线"""
    if not user or not isinstance(user, dict) or \
       not charger_pos or not isinstance(charger_pos, dict):
        logger.warning("Invalid input for plan_route_to_charger")
        return False
    start_pos = user.get("current_position")
    if not start_pos:
         logger.warning(f"User {user.get('user_id')} missing current_position.")
         return False

    # ===> 移除或注释掉下面这行 <===
    # user["target_charger"] = charger_pos.get("charger_id") if isinstance(charger_pos.get("charger_id"), str) else None
    # ^^^ 移除这行，target_charger 由 environment.py 设置 ^^^

    user["last_destination_type"] = "charger"
    return plan_route(user, start_pos, charger_pos, map_bounds, user_model_params) # Pass params

def plan_route_to_destination(user, destination, map_bounds, user_model_params): # Added user_model_params
    """规划用户到任意目的地的路线"""
    if not user or not isinstance(user, dict) or \
       not destination or not isinstance(destination, dict):
        logger.warning("Invalid input for plan_route_to_destination")
        return False
    start_pos = user.get("current_position")
    if not start_pos:
         logger.warning(f"User {user.get('user_id')} missing current_position.")
         return False
    user["target_charger"] = None 
    user["last_destination_type"] = "random"
    return plan_route(user, start_pos, destination, map_bounds, user_model_params) # Pass params


def update_user_position_along_route(user, distance_km, map_bounds, user_model_params): # Added user_model_params
    route = user.get("route")
    if not route or len(route) < 2 or distance_km <= 0:
        return 0

    current_pos = user["current_position"]
    if not current_pos: return 0 # Cannot move without current position

    # --- 沿路径点移动的逻辑 ---
    # (复制原 ChargingEnvironment._update_user_position_along_route 中 while 循环及相关逻辑)
    distance_coord = distance_km / 111.0 # Approx conversion
    moved_coord = 0.0 # Track distance moved in coord units

    current_segment_index = user.get("_current_segment_index", 0) # Track progress

    while distance_coord > 1e-9 and current_segment_index < len(route) - 1:
        segment_start = route[current_segment_index]
        segment_end = route[current_segment_index + 1]

        # Vector from current pos to segment end
        dx_to_end = segment_end.get('lng', map_bounds['lng_min']) - current_pos.get('lng', map_bounds['lng_min'])
        dy_to_end = segment_end.get('lat', map_bounds['lat_min']) - current_pos.get('lat', map_bounds['lat_min'])
        dist_to_end_coord = math.sqrt(dx_to_end**2 + dy_to_end**2)

        if dist_to_end_coord < 1e-9: # Already at or past the end of this segment
            current_segment_index += 1
            continue

        # Distance to move in this step, limited by segment end or remaining distance
        move_on_segment_coord = min(distance_coord, dist_to_end_coord)
        fraction = move_on_segment_coord / dist_to_end_coord

        # Update position
        current_pos['lng'] += dx_to_end * fraction
        current_pos['lat'] += dy_to_end * fraction

        distance_coord -= move_on_segment_coord # Reduce remaining distance
        moved_coord += move_on_segment_coord

        # If we reached the end of the segment, move to the next
        if distance_coord < 1e-9 or abs(move_on_segment_coord - dist_to_end_coord) < 1e-9:
             # Snap to segment end to avoid floating point errors
             current_pos['lng'] = segment_end.get('lng', map_bounds['lng_min'])
             current_pos['lat'] = segment_end.get('lat', map_bounds['lat_min'])
             current_segment_index += 1

    user["_current_segment_index"] = current_segment_index # Store progress for next step
    user["traveled_distance"] = user.get("traveled_distance", 0) + (moved_coord * 111.0) # Update total traveled

    # Return actual distance moved in km
    degrees_to_km = user_model_params.get('degrees_to_km_conversion_factor', 111.0)
    return moved_coord * degrees_to_km if degrees_to_km > 0 else moved_coord * 111.0


def has_reached_destination(user, user_model_params): # Added user_model_params
    """检查用户是否已到达目的地（基于剩余时间和距离）"""
    if not user or user.get("time_to_destination") is None:
        return False
    
    if user["time_to_destination"] <= 0.1: # Time-based check
        return True
    
    current_pos = user.get("current_position")
    destination = user.get("destination")
    if current_pos and destination:
        # from .utils import calculate_distance # Already imported at top
        distance_to_dest = calculate_distance(current_pos, destination)
        dist_thresh_km = user_model_params.get('reached_destination_distance_threshold_km', 0.1)
        if distance_to_dest < dist_thresh_km:
            logger.debug(f"User {user.get('user_id')} reached destination by distance check: {distance_to_dest:.3f}km (threshold: {dist_thresh_km}km)")
            return True
    
    return False
class UserDecisionManager:
    """用户决策管理器 - 处理用户手动决策的验证和应用"""
    
    def __init__(self, config=None): # Allow passing config for parameters
        self.config = config if config is not None else {}
        self.user_model_params = self.config.get('environment', {}).get('user_model_params', {})
        self.pending_decisions = {}
        self.decision_history = []
    
    def add_user_decision(self, user_id, charger_id, charging_params, timestamp):
        """添加用户决策"""
        decision = {
            'user_id': user_id,
            'charger_id': charger_id,
            'charging_params': charging_params,
            'timestamp': timestamp,
            'status': 'pending'
        }
        
        self.pending_decisions[user_id] = decision
        logger.info(f"Added user decision: {user_id} -> {charger_id}")
        
        return decision
    
    def validate_decision(self, user_id, users_data, chargers_data):
        """验证用户决策的有效性"""
        if user_id not in self.pending_decisions:
            return False, "没有找到待处理的决策"
        
        decision = self.pending_decisions[user_id]
        charger_id = decision['charger_id']
        
        # 检查用户状态
        user = users_data.get(user_id)
        if not user:
            return False, f"用户 {user_id} 不存在"
        
        if user.get('status') in ['charging', 'waiting']:
            return False, f"用户 {user_id} 正在充电或等待中"
        
        # 检查充电桩状态
        charger = chargers_data.get(charger_id)
        if not charger:
            return False, f"充电桩 {charger_id} 不存在"
        
        if charger.get('status') == 'failure':
            return False, f"充电桩 {charger_id} 故障中"
        
        queue_length = len(charger.get('queue', []))
        queue_capacity = charger.get('queue_capacity', 5)
        
        if queue_length >= queue_capacity:
            return False, f"充电桩 {charger_id} 队列已满"
        
        return True, "决策有效"
    
    def apply_decision(self, user_id):
        """应用用户决策"""
        if user_id not in self.pending_decisions:
            return None
        
        decision = self.pending_decisions[user_id]
        decision['status'] = 'applied'
        decision['applied_timestamp'] = datetime.now().isoformat()
        
        # 移动到历史记录
        self.decision_history.append(decision)
        del self.pending_decisions[user_id]
        
        logger.info(f"Applied user decision for {user_id}")
        return decision
    
    def get_pending_decisions(self):
        """获取所有待处理决策"""
        return self.pending_decisions.copy()
    
    def get_decision_history(self, user_id=None):
        """获取决策历史"""
        if user_id:
            return [d for d in self.decision_history if d['user_id'] == user_id]
        return self.decision_history.copy()
    
    def clear_expired_decisions(self): # Removed expiry_minutes, will use from config
        """清理过期的待处理决策"""
        expiry_minutes_cfg = self.user_model_params.get('user_decision_manager_expiry_minutes', 30)
        current_time = datetime.now()
        expired_users = []
        
        for user_id, decision in self.pending_decisions.items():
            decision_time = datetime.fromisoformat(decision['timestamp'])
            if (current_time - decision_time).total_seconds() > expiry_minutes_cfg * 60:
                expired_users.append(user_id)
        
        for user_id in expired_users:
            expired_decision = self.pending_decisions[user_id]
            expired_decision['status'] = 'expired'
            self.decision_history.append(expired_decision)
            del self.pending_decisions[user_id]
            logger.info(f"Expired user decision for {user_id}")
        
        return len(expired_users)
