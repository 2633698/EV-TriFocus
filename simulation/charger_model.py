# ev_charging_project/simulation/charger_model.py
import logging
from datetime import datetime, timedelta
import random
import math # 需要 math

logger = logging.getLogger(__name__)

def simulate_step(chargers, users, current_time, time_step_minutes, grid_status):
    """
    模拟所有充电桩在一个时间步内的操作。
    直接修改传入的 chargers 和 users 字典。

    Args:
        chargers (dict): 充电桩状态字典
        users (dict): 用户状态字典
        current_time (datetime): 当前模拟时间
        time_step_minutes (int): 模拟时间步长（分钟）
        grid_status (dict): 当前电网状态 (用于获取价格)

    Returns:
        tuple: (total_ev_load, completed_sessions)
               - float: 该时间步的总 EV 充电负载 (kW)
               - list: 本次时间步完成的充电会话信息列表
    """
    time_step_hours = round(time_step_minutes / 60, 4)
    total_ev_load = 0
    completed_sessions_this_step = [] # 存储本次完成的会话

    for charger_id, charger in chargers.items():
        if not isinstance(charger, dict): continue # 基本检查
        if charger.get("status") == "failure": continue

        current_user_id = charger.get("current_user")

        # --- 处理正在充电的用户 ---
        # (这部分逻辑与上次提供的版本一致)
        if charger.get("status") == "occupied" and current_user_id:
            if current_user_id in users:
                user = users[current_user_id]
                current_soc = user.get("soc", 0)
                battery_capacity = user.get("battery_capacity", 60)
                target_soc = user.get("target_soc", 95)
                initial_soc = user.get("initial_soc", current_soc)

                # --- 充电功率和效率计算 (使用原详细逻辑) ---
                charger_type = charger.get("type", "normal")
                charger_max_power = charger.get("max_power", 60)
                vehicle_max_power = user.get("max_charging_power", 60)
                power_limit = min(charger_max_power, vehicle_max_power)
                base_efficiency = user.get("charging_efficiency", 0.92)
                soc_factor = 1.0
                if current_soc < 20: soc_factor = 1.0
                elif current_soc < 50: soc_factor = 1.0 - ((current_soc - 20) / 30) * 0.1
                elif current_soc < 80: soc_factor = 0.9 - ((current_soc - 50) / 30) * 0.2
                else: soc_factor = 0.7 - ((current_soc - 80) / 20) * 0.5
                actual_power = power_limit * max(0.1, soc_factor)
                power_to_battery = actual_power * base_efficiency
                # --- 结束功率计算 ---

                soc_needed = max(0, target_soc - current_soc)
                energy_needed = (soc_needed / 100.0) * battery_capacity
                max_energy_this_step = power_to_battery * time_step_hours
                actual_energy_charged_to_battery = min(energy_needed, max_energy_this_step)
                actual_energy_from_grid = actual_energy_charged_to_battery / base_efficiency if base_efficiency > 0 else actual_energy_charged_to_battery

                if actual_energy_charged_to_battery > 0.01:
                    actual_soc_increase = (actual_energy_charged_to_battery / battery_capacity) * 100 if battery_capacity > 0 else 0
                    new_soc = min(100, current_soc + actual_soc_increase)

                    user["soc"] = new_soc
                    user["current_range"] = user.get("max_range", 400) * (new_soc / 100)

                    actual_power_drawn_from_grid = actual_energy_from_grid / time_step_hours if time_step_hours > 0 else 0
                    total_ev_load += actual_power_drawn_from_grid

                    current_price = grid_status.get("current_price", 0.85)
                    price_multiplier = charger.get("price_multiplier", 1.0)
                    revenue = actual_energy_from_grid * current_price * price_multiplier
                    charger["daily_revenue"] = charger.get("daily_revenue", 0) + revenue
                    charger["daily_energy"] = charger.get("daily_energy", 0) + actual_energy_from_grid

                    # 检查充电是否完成
                    charging_start_time = charger.get("charging_start_time", current_time - timedelta(minutes=time_step_minutes))
                    charging_duration_minutes = (current_time - charging_start_time).total_seconds() / 60
                    max_charging_time = 180 # Default
                    if charger_type == "superfast": max_charging_time = 30
                    elif charger_type == "fast": max_charging_time = 60

                    # --- 结束充电逻辑 ---
                    if new_soc >= target_soc - 0.5 or charging_duration_minutes >= max_charging_time - 0.1:
                        reason = "target_reached" if new_soc >= target_soc - 0.5 else "time_limit_exceeded"
                        logger.info(f"User {current_user_id} finished charging at {charger_id} ({reason}). Final SOC: {new_soc:.1f}%")

                        session_energy = charger.get("daily_energy", 0) - charger.get("_prev_energy", 0)
                        session_revenue = charger.get("daily_revenue", 0) - charger.get("_prev_revenue", 0)
                        charging_session = {
                            "user_id": current_user_id, "charger_id": charger_id,
                            "start_time": charging_start_time.isoformat(), "end_time": current_time.isoformat(),
                            "duration_minutes": round(charging_duration_minutes, 2),
                            "initial_soc": initial_soc, "final_soc": new_soc,
                            "energy_charged_grid": round(session_energy, 3),
                            "cost": round(session_revenue, 2), "termination_reason": reason
                        }
                        completed_sessions_this_step.append(charging_session)
                        if "charging_history" not in user: user["charging_history"] = []
                        user["charging_history"].append(charging_session)

                        # 重置状态
                        charger["status"] = "available"
                        charger["current_user"] = None
                        charger["charging_start_time"] = None
                        # 更新 _prev 以便下次计算差值
                        charger["_prev_energy"] = charger.get("daily_energy", 0)
                        charger["_prev_revenue"] = charger.get("daily_revenue", 0)

                        user["status"] = "post_charge"
                        user["target_charger"] = None
                        user["post_charge_timer"] = random.randint(1, 3)
                        user["initial_soc"] = None; user["target_soc"] = None

                        # 注意：这里不再立即处理队列，交给下面的逻辑块统一处理

                else: # 充电量过小，也算完成
                     if current_soc >= target_soc - 1.0:
                         logger.debug(f"User {current_user_id} charging considered complete at {charger_id}. SOC: {current_soc:.1f}%")
                         charging_start_time = charger.get("charging_start_time", current_time - timedelta(minutes=time_step_minutes))
                         charging_duration_minutes = (current_time - charging_start_time).total_seconds() / 60
                         session_energy = charger.get("daily_energy", 0) - charger.get("_prev_energy", 0)
                         session_revenue = charger.get("daily_revenue", 0) - charger.get("_prev_revenue", 0)
                         charging_session = { "user_id": current_user_id, "charger_id": charger_id,"start_time": charging_start_time.isoformat(),"end_time": current_time.isoformat(),"duration_minutes": round(charging_duration_minutes, 2),"initial_soc": initial_soc,"final_soc": current_soc,"energy_charged_grid": round(session_energy, 3),"cost": round(session_revenue, 2),"termination_reason": "target_reached"}
                         completed_sessions_this_step.append(charging_session)
                         if "charging_history" not in user: user["charging_history"] = []
                         user["charging_history"].append(charging_session)

                         charger["status"] = "available"; charger["current_user"] = None
                         charger["charging_start_time"] = None
                         charger["_prev_energy"] = charger.get("daily_energy", 0)
                         charger["_prev_revenue"] = charger.get("daily_revenue", 0)

                         user["status"] = "post_charge"; user["target_charger"] = None
                         user["post_charge_timer"] = random.randint(1, 3)
                         user["initial_soc"] = None; user["target_soc"] = None

            else: # 用户不存在
                logger.warning(f"Charger {charger_id} occupied by non-existent user {current_user_id}. Setting available.")
                charger["status"] = "available"; charger["current_user"] = None
                charger["charging_start_time"] = None

        # ===> 修正后的等待队列处理逻辑 <===
        # 检查条件：充电桩现在是 'available' 状态，并且它的 'queue' 不为空
        if charger.get("status") == "available" and charger.get("queue"):
            queue = charger["queue"] # 获取队列列表的引用
            next_user_id = queue[0] # 查看队首用户 ID

            if next_user_id in users:
                next_user = users[next_user_id]
                # 关键检查：确认用户的状态是 'waiting'
                if next_user.get("status") == "waiting":
                    logger.info(f"Starting charging for user {next_user_id} from queue at {charger_id}")

                    # 更新充电桩状态
                    charger["status"] = "occupied"
                    charger["current_user"] = next_user_id
                    charger["charging_start_time"] = current_time
                    # 记录开始充电时的能量和收入基准
                    charger["_prev_energy"] = charger.get("daily_energy", 0)
                    charger["_prev_revenue"] = charger.get("daily_revenue", 0)

                    # 更新用户状态
                    next_user["status"] = "charging"
                    next_user["target_soc"] = min(95, next_user.get("soc", 0) + 60) # 设置充电目标
                    next_user["initial_soc"] = next_user.get("soc", 0) # 记录开始充电时的SOC

                    # 从队列中移除已开始充电的用户
                    queue.pop(0)
                    logger.debug(f"User {next_user_id} removed from queue {charger_id}.")

                else:
                    # 用户状态不是 'waiting'，暂时不处理，让他留在队首，下一轮再检查
                    logger.warning(f"User {next_user_id} at head of queue for {charger_id} has status '{next_user.get('status')}' (expected 'waiting'). Skipping charging start this step.")
            else:
                # 队列中的用户 ID 在 users 字典中找不到，说明用户可能已离开或数据错误
                logger.warning(f"User {next_user_id} in queue for {charger_id} not found in users dict. Removing from queue.")
                queue.pop(0) # 从队列移除无效用户

            # 注意：因为我们直接修改了 charger['queue'] 列表，所以不需要 charger['queue'] = queue 这行了。

    # 返回总负载和本次完成的充电记录
    return total_ev_load, completed_sessions_this_step