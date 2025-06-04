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
    env_config = config.get('environment', {})
    map_bounds = env_config.get("map_bounds", {
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
                # 大幅加速到达目标（模拟用户更积极的驾驶）
                travel_speed = user.get("travel_speed", 45) * 2.0  # 提高100%速度
                user["travel_speed"] = travel_speed
                
                # 强制减少剩余时间，确保快速到达
                current_time_to_dest = user.get("time_to_destination", 0)
                if current_time_to_dest > 5:  # 如果剩余时间超过5分钟
                    user["time_to_destination"] = max(1, current_time_to_dest * 0.3)  # 大幅减少剩余时间
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
                
                if plan_route_to_destination(user, new_destination, map_bounds):
                    logger.debug(f"User {user_id} planned route to new destination after charging.")
                else:
                    logger.warning(f"User {user_id} failed to plan route. Setting idle.")
                    user["status"] = "idle"
                    user["destination"] = None

        # 电量消耗（对手动决策用户同样适用）
        if user_status not in ["charging", "waiting"]:
            # 原有电量消耗逻辑...
            idle_consumption_rate = 0.4
            vehicle_type = user.get("vehicle_type", "sedan")

            if vehicle_type == "sedan": idle_consumption_rate = 0.8
            elif vehicle_type == "suv": idle_consumption_rate = 1.2
            elif vehicle_type == "truck": idle_consumption_rate = 2.0
            elif vehicle_type == "luxury": idle_consumption_rate = 1.0
            elif vehicle_type == "compact": idle_consumption_rate = 0.6

            current_month = current_time.month
            season_factor = 1.0
            if 6 <= current_month <= 8: season_factor = 2.2
            elif current_month <= 2 or current_month == 12: season_factor = 2.5
            else: season_factor = 1.3
            idle_consumption_rate *= season_factor

            hour = current_time.hour
            time_factor = 1.0
            if hour in [6, 7, 8, 17, 18, 19]: time_factor = 1.6
            elif 22 <= hour or hour <= 4: time_factor = 0.8
            idle_consumption_rate *= time_factor

            behavior_factor = random.uniform(0.9, 1.8)
            idle_consumption_rate *= behavior_factor

            idle_energy_used = idle_consumption_rate * time_step_hours
            idle_soc_decrease = (idle_energy_used / battery_capacity) * 100 if battery_capacity > 0 else 0
            user["soc"] = max(0, user.get("soc", 0) - idle_soc_decrease)
            current_soc = user["soc"]

        # 检查充电需求（手动决策用户跳过）
        if not is_manual_decision:
            user["needs_charge_decision"] = False
            if user_status in ["idle", "traveling", "post_charge"] and not user.get("target_charger"):
                estimated_charge_amount = 100 - current_soc
                MIN_CHARGE_AMOUNT_THRESHOLD = config.get('environment',{}).get('min_charge_threshold_percent', 25.0)
                
                if estimated_charge_amount < MIN_CHARGE_AMOUNT_THRESHOLD:
                    pass
                elif current_soc <= config.get('environment',{}).get('force_charge_soc_threshold', 20.0):
                    user["needs_charge_decision"] = True
                    logger.debug(f"User {user_id} SOC critical, forcing charge need.")
                else:
                    charging_prob = calculate_charging_probability(user, current_time.hour, config)
                    # 应用各种调整因子
                    timer_value = user.get("post_charge_timer")
                    if user_status == "post_charge" and isinstance(timer_value, int) and timer_value > 0:
                        charging_prob *= 0.1
                    if user_status == "traveling" and user.get("last_destination_type") == "random":
                        charging_prob *= (0.1 if current_soc > 60 else 1.2)
                    if current_soc > 75: charging_prob *= 0.01
                    elif current_soc > 60: charging_prob *= 0.1
                    if user.get("user_type") in ["taxi", "ride_hailing"]:
                        charging_prob *= (0.5 if current_soc > 50 else 1.2)
                    
                    hour = current_time.hour
                    grid_status = config.get('grid', {})
                    peak_hours = grid_status.get('peak_hours', [])
                    if hour in peak_hours:
                        charging_prob *= (0.5 if current_soc > 60 else 1.2)
                    if 20 < current_soc <= 35: charging_prob *= 1.5

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
            actual_distance_moved = update_user_position_along_route(user, distance_this_step, map_bounds)

            # 行驶能耗计算
            base_energy_per_km = 0.25 * (1 + (travel_speed / 80))
            vehicle_type = user.get("vehicle_type", "sedan")
            energy_per_km = base_energy_per_km
            
            if vehicle_type == "sedan": energy_per_km *= 1.2
            elif vehicle_type == "suv": energy_per_km *= 1.5
            elif vehicle_type == "truck": energy_per_km *= 1.8
            
            driving_style = user.get("driving_style", "normal")
            if driving_style == "aggressive": energy_per_km *= 1.3
            elif driving_style == "eco": energy_per_km *= 0.9
            
            road_condition = random.uniform(1.0, 1.3)
            weather_impact = random.uniform(1.0, 1.2)
            traffic_factor = 1.0
            hour = current_time.hour
            grid_status = config.get('grid', {})
            peak_hours = grid_status.get('peak_hours', [])
            if hour in peak_hours: traffic_factor = random.uniform(1.1, 1.4)
            energy_per_km *= road_condition * weather_impact * traffic_factor

            energy_consumed = actual_distance_moved * energy_per_km
            soc_decrease_travel = (energy_consumed / battery_capacity) * 100 if battery_capacity > 0 else 0
            user["soc"] = max(0, user["soc"] - soc_decrease_travel)

            time_taken_minutes = (actual_distance_moved / travel_speed) * 60 if travel_speed > 0 else 0
            user["time_to_destination"] = max(0, user.get("time_to_destination", 0) - time_taken_minutes)

            # 检查是否到达
            if has_reached_destination(user):
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

def calculate_charging_probability(user, current_hour, config):
    """计算用户决定寻求充电的概率 (使用原详细逻辑)"""
    # (从原 ChargingEnvironment._calculate_charging_probability 复制逻辑)
    current_soc = user.get("soc", 100)
    user_type = user.get("user_type", "commuter")
    charging_preference = user.get("charging_preference", "flexible") # 可能没有这个字段
    profile = user.get("user_profile", "balanced") # 使用 user_profile
    fast_charging_preference = user.get("fast_charging_preference", 0.5) # 快充偏好

    # 检查充电量是否太小
    estimated_charge_amount = 100 - current_soc
    MIN_CHARGE_AMOUNT_THRESHOLD = config.get('environment',{}).get('min_charge_threshold_percent', 25.0)
    if estimated_charge_amount < MIN_CHARGE_AMOUNT_THRESHOLD:
        return 0.0 # 概率为0

    # 1. Base probability using sigmoid
    soc_midpoint = 40
    soc_steepness = 0.1
    base_prob = 1 / (1 + math.exp(soc_steepness * (current_soc - soc_midpoint)))
    base_prob = min(0.95, max(0.05, base_prob))
    if current_soc > 75: base_prob *= 0.1
    elif current_soc > 60: base_prob *= 0.3

    # 2. User type factor
    type_factor = 0
    if user_type == "taxi": type_factor = 0.2
    elif user_type == "delivery": type_factor = 0.15
    elif user_type == "business": type_factor = 0.1
    elif user_type == "ride_hailing": type_factor = 0.15
    elif user_type == "logistics": type_factor = 0.1

    # 3. Preference factor (simplified - time based)
    preference_factor = 0
    grid_status = config.get('grid', {})
    peak_hours = grid_status.get('peak_hours', [])
    valley_hours = grid_status.get('valley_hours', [])
    hour = current_hour
    if hour in valley_hours: preference_factor = 0.2 # Prefer valley
    elif hour not in peak_hours: preference_factor = 0.1 # Prefer shoulder over peak

    # 4. Profile factor
    profile_factor = 0
    if profile == "anxious": profile_factor = 0.2
    elif profile == "urgent": profile_factor = 0.15
    elif profile == "economic": profile_factor = -0.1 # Discourage charging unless needed

    # 5. Fast charging preference factor
    # 快充偏好高的用户更倾向于在SOC较高时就开始寻找充电站
    fast_charging_factor = 0
    if fast_charging_preference > 0.7:
        # 高快充偏好的用户在SOC较高时就会考虑充电
        if 40 <= current_soc <= 60:
            fast_charging_factor = 0.1 * (fast_charging_preference - 0.7) / 0.3
    elif fast_charging_preference < 0.3:
        # 低快充偏好的用户会等到SOC较低时才充电
        if current_soc > 30:
            fast_charging_factor = -0.1 * (0.3 - fast_charging_preference) / 0.3

    # 6. Emergency boost
    emergency_boost = 0
    force_charge_soc = config.get('environment',{}).get('force_charge_soc_threshold', 20.0)
    if current_soc <= force_charge_soc + 5: # Slightly above force threshold
        emergency_boost = 0.4 * (1 - (current_soc - force_charge_soc) / 5.0) if current_soc > force_charge_soc else 0.4

    # Combine factors
    charging_prob = base_prob + type_factor + preference_factor + profile_factor + fast_charging_factor + emergency_boost
    charging_prob = min(1.0, max(0.0, charging_prob)) # Clamp to [0, 1]

    # logger.debug(f"User {user.get('user_id')} charging prob: {charging_prob:.3f} (SOC:{current_soc:.1f})")
    return charging_prob


def plan_route(user, start_pos, end_pos, map_bounds):
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

def plan_route_to_charger(user, charger_pos, map_bounds):
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
    # 现在只调用通用的 plan_route
    return plan_route(user, start_pos, charger_pos, map_bounds)

def plan_route_to_destination(user, destination, map_bounds):
    """规划用户到任意目的地的路线"""
    if not user or not isinstance(user, dict) or \
       not destination or not isinstance(destination, dict):
        logger.warning("Invalid input for plan_route_to_destination")
        return False
    start_pos = user.get("current_position")
    if not start_pos:
         logger.warning(f"User {user.get('user_id')} missing current_position.")
         return False
    user["target_charger"] = None # Not going to a charger
    user["last_destination_type"] = "random"
    return plan_route(user, start_pos, destination, map_bounds)


def update_user_position_along_route(user, distance_km, map_bounds):
    """沿路线移动用户位置（使用原详细逻辑），返回实际移动距离"""
    # (从原 ChargingEnvironment._update_user_position_along_route 复制逻辑)
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
    return moved_coord * 111.0


def has_reached_destination(user):
    """检查用户是否已到达目的地（基于剩余时间和距离）"""
    if not user or user.get("time_to_destination") is None:
        return False
    
    # 检查剩余时间是否为0或非常小
    if user["time_to_destination"] <= 0.1:
        return True
    
    # 额外检查：如果用户位置非常接近目的地，也认为已到达
    current_pos = user.get("current_position")
    destination = user.get("destination")
    if current_pos and destination:
        from .utils import calculate_distance
        distance_to_dest = calculate_distance(current_pos, destination)
        # 如果距离小于100米，认为已到达
        if distance_to_dest < 0.1:  # 0.1km = 100m
            logger.debug(f"User {user.get('user_id')} reached destination by distance check: {distance_to_dest:.3f}km")
            return True
    
    return False
class UserDecisionManager:
    """用户决策管理器 - 处理用户手动决策的验证和应用"""
    
    def __init__(self):
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
    
    def clear_expired_decisions(self, expiry_minutes=30):
        """清理过期的待处理决策"""
        current_time = datetime.now()
        expired_users = []
        
        for user_id, decision in self.pending_decisions.items():
            decision_time = datetime.fromisoformat(decision['timestamp'])
            if (current_time - decision_time).total_seconds() > expiry_minutes * 60:
                expired_users.append(user_id)
        
        for user_id in expired_users:
            expired_decision = self.pending_decisions[user_id]
            expired_decision['status'] = 'expired'
            self.decision_history.append(expired_decision)
            del self.pending_decisions[user_id]
            logger.info(f"Expired user decision for {user_id}")
        
        return len(expired_users)
