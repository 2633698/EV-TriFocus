# ev_charging_project/simulation/user_model.py
import random
import math
from datetime import datetime, timedelta
import logging
from .utils import calculate_distance, get_random_location # 使用相对导入

logger = logging.getLogger(__name__)

def simulate_step(users, chargers, current_time, time_step_minutes, config):
    """
    模拟所有用户的行为在一个时间步内。
    直接修改传入的 users 字典。

    Args:
        users (dict): 用户状态字典 {user_id: user_data}
        chargers (dict): 充电桩状态字典 {charger_id: charger_data} (用于查找目标)
        current_time (datetime): 当前模拟时间
        time_step_minutes (int): 模拟时间步长（分钟）
        config (dict): 全局配置字典

    Returns:
        None: 直接修改 users 字典
    """
    time_step_hours = time_step_minutes / 60.0
    env_config = config.get('environment', {})
    map_bounds = env_config.get("map_bounds", {
        "lat_min": 30.5, "lat_max": 31.0, "lng_min": 114.0, "lng_max": 114.5
    })

    for user_id, user in list(users.items()): # 使用 list(users.items()) 允许在循环中删除用户（如果需要）
        if not isinstance(user, dict):
            logger.warning(f"Invalid user data found for ID {user_id}. Skipping.")
            continue

        current_soc = user.get("soc", 0)
        user_status = user.get("status", "idle")
        battery_capacity = user.get("battery_capacity", 60)

        # --- 后充电状态处理 ---
        # (与之前提供的 user_model.py 相同)
        if user_status == "post_charge":
            if user.get("post_charge_timer") is None:
                user["post_charge_timer"] = random.randint(1, 4)
            if user["post_charge_timer"] > 0:
                user["post_charge_timer"] -= 1
            else:
                logger.debug(f"User {user_id} post-charge timer expired. Assigning new random destination.")
                new_destination = get_random_location(map_bounds)
                while calculate_distance(user.get("current_position", {}), new_destination) < 0.1:
                     new_destination = get_random_location(map_bounds)

                user["status"] = "traveling"
                user["target_charger"] = None
                user["post_charge_timer"] = None
                user["needs_charge_decision"] = False
                user["last_destination_type"] = "random"
                if plan_route_to_destination(user, new_destination, map_bounds):
                    logger.debug(f"User {user_id} planned route to new random destination after charging.")
                else:
                    logger.warning(f"User {user_id} failed to plan route to new random destination. Setting idle.")
                    user["status"] = "idle"
                    user["destination"] = None


        # --- 电量消耗 (非充电/等待状态) ---
        # (使用原 ChargingEnvironment._simulate_user_behavior 中的详细逻辑)
        if user_status not in ["charging", "waiting"]:
            idle_consumption_rate = 0.4 # 基础 kWh/h
            vehicle_type = user.get("vehicle_type", "sedan")

            # 根据车型调整
            if vehicle_type == "sedan": idle_consumption_rate = 0.8
            elif vehicle_type == "suv": idle_consumption_rate = 1.2
            elif vehicle_type == "truck": idle_consumption_rate = 2.0
            elif vehicle_type == "luxury": idle_consumption_rate = 1.0
            elif vehicle_type == "compact": idle_consumption_rate = 0.6

            # 季节因素
            current_month = current_time.month
            season_factor = 1.0
            if 6 <= current_month <= 8: season_factor = 2.2 # Summer AC
            elif current_month <= 2 or current_month == 12: season_factor = 2.5 # Winter Heat
            else: season_factor = 1.3 # Spring/Autumn
            idle_consumption_rate *= season_factor

            # 时间因素
            hour = current_time.hour
            time_factor = 1.0
            if hour in [6, 7, 8, 17, 18, 19]: time_factor = 1.6 # Peak prep
            elif 22 <= hour or hour <= 4: time_factor = 0.8 # Night low
            idle_consumption_rate *= time_factor

            # 随机行为因素
            behavior_factor = random.uniform(0.9, 1.8)
            idle_consumption_rate *= behavior_factor

            # 计算并应用SOC减少
            idle_energy_used = idle_consumption_rate * time_step_hours
            idle_soc_decrease = (idle_energy_used / battery_capacity) * 100 if battery_capacity > 0 else 0
            user["soc"] = max(0, user.get("soc", 0) - idle_soc_decrease)
            current_soc = user["soc"] # 更新当前SOC


        # --- 检查充电需求 ---
        # (使用原 ChargingEnvironment._simulate_user_behavior 中的详细逻辑)
        user["needs_charge_decision"] = False # Reset flag each step
        if user_status in ["idle", "traveling", "post_charge"] and not user.get("target_charger"):
            # 检查是否充电量太小
            estimated_charge_amount = 100 - current_soc
            MIN_CHARGE_AMOUNT_THRESHOLD = config.get('environment',{}).get('min_charge_threshold_percent', 25.0)
            if estimated_charge_amount < MIN_CHARGE_AMOUNT_THRESHOLD:
                # logger.debug(f"User {user_id} needs only {estimated_charge_amount:.1f}% charge, skipping.")
                pass # 不标记需要充电
            # 强制充电检查
            elif current_soc <= config.get('environment',{}).get('force_charge_soc_threshold', 20.0):
                user["needs_charge_decision"] = True
                logger.debug(f"User {user_id} SOC critical ({current_soc:.1f}%), forcing charge need.")
            else:
                # 计算概率
                charging_prob = calculate_charging_probability(user, current_time.hour, config)
                # (应用各种调整因子 - 从原逻辑复制)
                timer_value = user.get("post_charge_timer")
                if user_status == "post_charge" and isinstance(timer_value, int) and timer_value > 0:
                    charging_prob *= 0.1
                if user_status == "traveling" and user.get("last_destination_type") == "random":
                    charging_prob *= (0.1 if current_soc > 60 else 1.2)
                if current_soc > 75: charging_prob *= 0.01
                elif current_soc > 60: charging_prob *= 0.1
                if user.get("user_type") in ["taxi", "ride_hailing"]:
                    charging_prob *= (0.5 if current_soc > 50 else 1.2)
                hour = current_time.hour # 确保使用当前小时
                grid_status = config.get('grid', {}) # 获取电网配置
                peak_hours = grid_status.get('peak_hours', [])
                if hour in peak_hours:
                     charging_prob *= (0.5 if current_soc > 60 else 1.2)
                if 20 < current_soc <= 35: charging_prob *= 1.5

                # 最终决定
                if random.random() < charging_prob:
                    user["needs_charge_decision"] = True
                    # logger.debug(f"User {user_id} decided to charge based on probability {charging_prob:.2f}")


        # --- 基于充电需求的状态转换 ---
        # 这个逻辑块在协调模式下是多余的，因为调度器会处理 `needs_charge_decision`.
        # 如果要模拟完全无序的行为，可以在 uncoordinated.py 中实现类似逻辑。
        # 这里我们只设置标志，让调度器决定。
        if user["needs_charge_decision"] and user_status in ["idle", "traveling"] and (user.get("last_destination_type") == "random" or user_status == "idle"):
             logger.info(f"User {user_id} (SOC: {current_soc:.1f}%) flagged as needing charging decision.")
             # 停止当前随机行程 (如果适用)
             if user_status == "traveling":
                  user["status"] = "idle" # 停止旅行，等待调度
                  user["destination"] = None
                  user["route"] = None
                  logger.debug(f"User {user_id} stopped random travel to wait for charge decision.")


        # --- 移动模拟 ---
        # (使用原 ChargingEnvironment._simulate_user_behavior 中的详细逻辑)
        if user_status == "traveling" and user.get("destination"):
            travel_speed = user.get("travel_speed", 45)
            if travel_speed <= 0: travel_speed = 45 # 防御性编程

            distance_this_step = travel_speed * time_step_hours
            actual_distance_moved = update_user_position_along_route(user, distance_this_step, map_bounds)

            # --- 行驶能耗计算 (使用原详细逻辑) ---
            base_energy_per_km = 0.25 * (1 + (travel_speed / 80)) # 基础能耗率
            vehicle_type = user.get("vehicle_type", "sedan")
            energy_per_km = base_energy_per_km
            # 车型调整
            if vehicle_type == "sedan": energy_per_km *= 1.2
            elif vehicle_type == "suv": energy_per_km *= 1.5
            elif vehicle_type == "truck": energy_per_km *= 1.8
            # 驾驶风格
            driving_style = user.get("driving_style", "normal")
            if driving_style == "aggressive": energy_per_km *= 1.3
            elif driving_style == "eco": energy_per_km *= 0.9
            # 路况、天气、交通 (简化)
            road_condition = random.uniform(1.0, 1.3)
            weather_impact = random.uniform(1.0, 1.2)
            traffic_factor = 1.0
            hour = current_time.hour # 使用当前小时
            grid_status = config.get('grid', {}) # 获取电网配置
            peak_hours = grid_status.get('peak_hours', [])
            if hour in peak_hours: traffic_factor = random.uniform(1.1, 1.4)
            energy_per_km *= road_condition * weather_impact * traffic_factor
            # --- 结束能耗计算 ---

            energy_consumed = actual_distance_moved * energy_per_km
            soc_decrease_travel = (energy_consumed / battery_capacity) * 100 if battery_capacity > 0 else 0
            # 从已经计算过 idle 消耗的 SOC 上减去行驶消耗
            user["soc"] = max(0, user["soc"] - soc_decrease_travel)

            # 更新剩余时间
            time_taken_minutes = (actual_distance_moved / travel_speed) * 60 if travel_speed > 0 else 0
            user["time_to_destination"] = max(0, user.get("time_to_destination", 0) - time_taken_minutes)

            # 检查是否到达
            if has_reached_destination(user):
                 logger.debug(f"User {user_id} arrived at destination {user['destination']}.")
                 user["current_position"] = user["destination"].copy()
                 user["time_to_destination"] = 0
                 user["route"] = None

                 target_charger_id = user.get("target_charger")
                 last_dest_type = user.get("last_destination_type")

                 if target_charger_id:
                      logger.info(f"User {user_id} arrived at target charger {target_charger_id}. Setting status to WAITING.")
                      user["status"] = "waiting"
                      user["destination"] = None
                      user["arrival_time_at_charger"] = current_time # 记录到达时间
                      # 注意：加入队列的逻辑由 charger_model 或 environment 处理
                 # (处理其他到达情况 - Fallback 和随机目的地)
                 elif last_dest_type == "charger":
                     logger.warning(f"User {user_id} arrived at target charger destination, but target_charger ID is None. Setting WAITING.")
                     user["status"] = "waiting"
                     user["destination"] = None
                     user["arrival_time_at_charger"] = current_time
                 else: # Arrived at random destination
                     logger.info(f"User {user_id} reached random destination. Setting IDLE.")
                     user["status"] = "idle"
                     user["destination"] = None
                     user["target_charger"] = None
                     # 到达后强制检查充电需求
                     if user["soc"] < 70: user["needs_charge_decision"] = True


        # 更新最终用户续航里程
        user["current_range"] = user.get("max_range", 300) * (user["soc"] / 100)


# --- 辅助函数 ---

def calculate_charging_probability(user, current_hour, config):
    """计算用户决定寻求充电的概率 (使用原详细逻辑)"""
    # (从原 ChargingEnvironment._calculate_charging_probability 复制逻辑)
    current_soc = user.get("soc", 100)
    user_type = user.get("user_type", "commuter")
    charging_preference = user.get("charging_preference", "flexible") # 可能没有这个字段
    profile = user.get("user_profile", "balanced") # 使用 user_profile

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
    elif user_type == "delivery": type_factor = 0.15 # Hypothetical type
    elif user_type == "business": type_factor = 0.1 # Hypothetical type

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
    elif profile == "planner": # Hypothetical profile
        if 25 <= current_soc <= 40: profile_factor = 0.15
    elif profile == "economic": profile_factor = -0.1 # Discourage charging unless needed

    # 5. Emergency boost
    emergency_boost = 0
    force_charge_soc = config.get('environment',{}).get('force_charge_soc_threshold', 20.0)
    if current_soc <= force_charge_soc + 5: # Slightly above force threshold
        emergency_boost = 0.4 * (1 - (current_soc - force_charge_soc) / 5.0) if current_soc > force_charge_soc else 0.4

    # Combine factors
    charging_prob = base_prob + type_factor + preference_factor + profile_factor + emergency_boost
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
    """检查用户是否已到达目的地（基于剩余时间）"""
    if not user or user.get("time_to_destination") is None:
        return False
    # 检查剩余时间是否为0或非常小
    return user["time_to_destination"] <= 0.1