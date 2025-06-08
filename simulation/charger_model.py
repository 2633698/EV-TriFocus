# ev_charging_project/simulation/charger_model.py
import logging
from datetime import datetime, timedelta
import random
import math # 需要 math

logger = logging.getLogger(__name__)

def simulate_step(chargers, users, current_time, time_step_minutes, grid_status, config):
    """
    模拟所有充电桩的操作，特别关注手动决策用户
    """
    time_step_hours = round(time_step_minutes / 60, 4)
    total_ev_load = 0
    completed_sessions_this_step = []

    # 从电网状态获取当前电价
    current_price_from_grid = grid_status.get("current_price", 0.85)
    # 获取运营商的电力成本率
    op_elec_cost_rate = config.get("metrics_params", {}).get("operator_profit", {}).get("operator_electricity_cost_rate_from_retail", 0.85)

    for charger_id, charger in chargers.items():
        if not isinstance(charger, dict): continue
        if charger.get("status") == "failure": continue

        current_user_id = charger.get("current_user")

        # --- 1. 处理正在充电的用户 ---
        if charger.get("status") == "occupied" and current_user_id:
            if current_user_id in users:
                user = users[current_user_id]
                current_soc = user.get("soc", 0)
                battery_capacity = user.get("battery_capacity", 60)
                target_soc = user.get("target_soc", 95)
                initial_soc = user.get("initial_soc", current_soc)
                is_manual_decision = user.get("manual_decision", False)

                # 充电功率和效率计算 (这部分逻辑保持不变)
                charger_type = charger.get("type", "normal")
                charger_max_power = charger.get("max_power", 60)
                vehicle_max_power = user.get("max_charging_power", 60)
                power_limit = min(charger_max_power, vehicle_max_power)
                base_efficiency = user.get("charging_efficiency", 0.92)
                
                fast_charging_preference = user.get("fast_charging_preference", 0.5)
                efficiency_boost = 0.0
                if is_manual_decision:
                    preferred_type = user.get("preferred_charging_type", "快充")
                    if preferred_type == "快充" and charger_type in ["fast", "superfast"]:
                        efficiency_boost += 0.03
                if charger_type in ["fast", "superfast"]:
                    if fast_charging_preference > 0.7:
                        efficiency_boost += 0.02 * (fast_charging_preference - 0.7) / 0.3
                elif charger_type == "normal" and fast_charging_preference < 0.3:
                    efficiency_boost += 0.01 * (0.3 - fast_charging_preference) / 0.3
                base_efficiency = min(0.95, base_efficiency * (1 + efficiency_boost))

                soc_factor = 1.0
                if current_soc < 20: soc_factor = 1.0
                elif current_soc < 50: soc_factor = 1.0 - ((current_soc - 20) / 30) * 0.1
                elif current_soc < 80: soc_factor = 0.9 - ((current_soc - 50) / 30) * 0.2
                else: soc_factor = 0.7 - ((current_soc - 80) / 20) * 0.5
                
                actual_power = power_limit * max(0.1, soc_factor)
                power_to_battery = actual_power * base_efficiency
                soc_needed = max(0, target_soc - current_soc)
                energy_needed = (soc_needed / 100.0) * battery_capacity
                max_energy_this_step = power_to_battery * time_step_hours
                actual_energy_charged_to_battery = min(energy_needed, max_energy_this_step)
                actual_energy_from_grid = actual_energy_charged_to_battery / base_efficiency if base_efficiency > 0 else actual_energy_charged_to_battery

                new_soc = current_soc # 初始化 new_soc
                if actual_energy_charged_to_battery > 0.01:
                    actual_soc_increase = (actual_energy_charged_to_battery / battery_capacity) * 100 if battery_capacity > 0 else 0
                    new_soc = min(100, current_soc + actual_soc_increase)
                    user["soc"] = new_soc
                    user["current_range"] = user.get("max_range", 400) * (new_soc / 100)

                    actual_power_drawn_from_grid = actual_energy_from_grid / time_step_hours if time_step_hours > 0 else 0
                    total_ev_load += actual_power_drawn_from_grid

                    price_multiplier = charger.get("price_multiplier", 1.0)
                    if is_manual_decision:
                        price_multiplier *= 0.98
                    
                    revenue_this_step = actual_energy_from_grid * current_price_from_grid * price_multiplier
                    cost_base_price_this_step = actual_energy_from_grid * current_price_from_grid

                    # 安全地累加会话数据
                    charger["session_energy"] += actual_energy_from_grid
                    charger["session_revenue"] += revenue_this_step
                    charger["session_cost_base_price"] += cost_base_price_this_step

                # 检查充电是否完成
                charging_start_time = charger.get("charging_start_time", current_time - timedelta(minutes=time_step_minutes))
                charging_duration_minutes = (current_time - charging_start_time).total_seconds() / 60
                max_charging_time = 180
                if charger_type == "superfast": max_charging_time = 30
                elif charger_type == "fast": max_charging_time = 60

                if new_soc >= target_soc - 0.5 or charging_duration_minutes >= max_charging_time - 0.1:
                    reason = "target_reached" if new_soc >= target_soc - 0.5 else "time_limit_exceeded"
                    
                    # 在充电会话结束时，进行最终的成本和收入计算
                    final_session_energy = charger.get("session_energy", 0)
                    final_session_revenue = charger.get("session_revenue", 0)
                    final_session_cost_base_price = charger.get("session_cost_base_price", 0)
                    
                    avg_price_this_session = (final_session_cost_base_price / final_session_energy) if final_session_energy > 0 else current_price_from_grid
                    final_session_cost = final_session_energy * avg_price_this_session * op_elec_cost_rate
                    
                    logger.info(f"Session End: User {current_user_id} at {charger_id}. Energy: {final_session_energy:.2f}kWh, Revenue: ¥{final_session_revenue:.2f}, Cost: ¥{final_session_cost:.2f}")

                    charging_session = {
                        "user_id": current_user_id, 
                        "charger_id": charger_id,
                        "station_id": charger.get("location", "unknown"),
                        "start_time": charging_start_time.isoformat(), 
                        "end_time": current_time.isoformat(),
                        "duration_minutes": round(charging_duration_minutes, 2),
                        "initial_soc": initial_soc, 
                        "end_soc": new_soc,
                        "energy_kwh": round(final_session_energy, 3),
                        "cost": round(final_session_cost, 2),
                        "revenue": round(final_session_revenue, 2),
                        "price_per_kwh": round(avg_price_this_session, 3),
                        "termination_reason": reason,
                        "manual_decision": is_manual_decision
                    }
                    completed_sessions_this_step.append(charging_session)
                    
                    if "charging_history" not in user: user["charging_history"] = []
                    user["charging_history"].append(charging_session)
                    
                    # 累加到每日统计
                    charger["daily_revenue"] = charger.get("daily_revenue", 0) + final_session_revenue
                    charger["daily_energy"] = charger.get("daily_energy", 0) + final_session_energy

                    # 重置状态和会话临时变量
                    charger["status"] = "available"
                    charger["current_user"] = None
                    charger["charging_start_time"] = None
                    charger.pop("session_energy", None)
                    charger.pop("session_revenue", None)
                    charger.pop("session_cost_base_price", None)
                    charger["_prev_energy"] = charger.get("daily_energy", 0) # 更新快照值
                    charger["_prev_revenue"] = charger.get("daily_revenue", 0)

                    user["status"] = "post_charge"
                    user["target_charger"] = None
                    user["post_charge_timer"] = random.randint(1, 3)
                    user["initial_soc"] = None
                    user["target_soc"] = None
                    
                    # 处理预约完成
                    if user.get('reservation_id'):
                        from reservation_system import reservation_manager
                        reservation_id = user.get('reservation_id')
                        if reservation_manager.completeReservation(reservation_id):
                            logger.info(f"预约 {reservation_id} 已完成 - 用户 {current_user_id} 充电结束")
                        user['reservation_id'] = None
                        user['is_reservation_user'] = False

        # --- 2. 处理等待队列 ---
        if charger.get("status") == "available" and charger.get("queue"):
            # ... (queue sorting logic remains the same) ...
            queue = charger["queue"]; manual_users = []; regular_users = []
            for queued_user_id in queue:
                if queued_user_id in users and users[queued_user_id].get("status") == "waiting":
                    if users[queued_user_id].get("manual_decision"): manual_users.append(queued_user_id)
                    else: regular_users.append(queued_user_id)
            charger["queue"] = manual_users + regular_users
            
            if charger["queue"]:
                next_user_id = charger["queue"][0]
                if next_user_id in users:
                    next_user = users[next_user_id]
                    if next_user.get("status") == "waiting":
                        # ... (manual decision lock check remains the same) ...

                        # 更新充电桩状态
                        charger["status"] = "occupied"
                        charger["current_user"] = next_user_id
                        charger["charging_start_time"] = current_time
                        
                        # --- START OF FIX ---
                        # 初始化会话临时变量
                        charger["session_energy"] = 0
                        charger["session_revenue"] = 0
                        charger["session_cost_base_price"] = 0
                        # --- END OF FIX ---
                        
                        # 更新用户状态
                        next_user["status"] = "charging"
                        if next_user.get("manual_decision"):
                            logger.info(f"Starting charging for manual decision user {next_user_id} at {charger_id}")
                        else:
                            logger.info(f"Starting charging for user {next_user_id} at {charger_id}")
                        
                        # ... (target SOC setting logic remains the same) ...
                        is_manual = next_user.get("manual_decision", False)
                        if is_manual and 'manual_charging_params' in next_user:
                            target_soc = next_user['manual_charging_params'].get('target_soc', 80)
                        else:
                            target_soc = min(95, next_user.get("soc", 0) + 60)
                        next_user["target_soc"] = target_soc
                        next_user["initial_soc"] = next_user.get("soc", 0)

                        charger["queue"].pop(0)
                        logger.debug(f"User {next_user_id} removed from queue {charger_id}.")

    # --- 3. 自适应EV负载 (保持不变) ---
    env_config = config.get("environment", {})
    current_user_count = env_config.get("user_count", 1000)
    baseline_user_count = 1000
    if current_user_count > 0:
        user_scaling_factor = baseline_user_count / current_user_count
        user_scaling_factor = min(user_scaling_factor, 10.0)
        if user_scaling_factor != 1.0:
            total_ev_load *= user_scaling_factor
    
    return total_ev_load, completed_sessions_this_step