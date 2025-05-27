# ev_charging_project/simulation/charger_model.py
import logging
from datetime import datetime, timedelta
import random
import math # 需要 math

logger = logging.getLogger(__name__)

def simulate_step(chargers, users, current_time, time_step_minutes, grid_status):
    """
    模拟所有充电桩的操作，特别关注手动决策用户
    """
    time_step_hours = round(time_step_minutes / 60, 4)
    total_ev_load = 0
    completed_sessions_this_step = []

    for charger_id, charger in chargers.items():
        if not isinstance(charger, dict): continue
        if charger.get("status") == "failure": continue

        current_user_id = charger.get("current_user")

        # 处理正在充电的用户（保持原有逻辑）
        if charger.get("status") == "occupied" and current_user_id:
            if current_user_id in users:
                user = users[current_user_id]
                current_soc = user.get("soc", 0)
                battery_capacity = user.get("battery_capacity", 60)
                target_soc = user.get("target_soc", 95)
                initial_soc = user.get("initial_soc", current_soc)
                is_manual_decision = user.get("manual_decision", False)

                # 充电功率和效率计算
                charger_type = charger.get("type", "normal")
                charger_max_power = charger.get("max_power", 60)
                vehicle_max_power = user.get("max_charging_power", 60)
                power_limit = min(charger_max_power, vehicle_max_power)
                base_efficiency = user.get("charging_efficiency", 0.92)
                
                # 手动决策用户的充电功率优化
                if is_manual_decision:
                    preferred_type = user.get("preferred_charging_type", "快充")
                    if preferred_type == "快充" and charger_type in ["fast", "superfast"]:
                        # 提高充电效率
                        base_efficiency = min(0.95, base_efficiency * 1.03)
                        logger.debug(f"Manual decision user {current_user_id} getting optimized charging")

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

                if actual_energy_charged_to_battery > 0.01:
                    actual_soc_increase = (actual_energy_charged_to_battery / battery_capacity) * 100 if battery_capacity > 0 else 0
                    new_soc = min(100, current_soc + actual_soc_increase)

                    user["soc"] = new_soc
                    user["current_range"] = user.get("max_range", 400) * (new_soc / 100)

                    actual_power_drawn_from_grid = actual_energy_from_grid / time_step_hours if time_step_hours > 0 else 0
                    total_ev_load += actual_power_drawn_from_grid

                    current_price = grid_status.get("current_price", 0.85)
                    price_multiplier = charger.get("price_multiplier", 1.0)
                    
                    # 手动决策用户可能享受小幅折扣
                    if is_manual_decision:
                        price_multiplier *= 0.98  # 2%折扣
                    
                    revenue = actual_energy_from_grid * current_price * price_multiplier
                    charger["daily_revenue"] = charger.get("daily_revenue", 0) + revenue
                    charger["daily_energy"] = charger.get("daily_energy", 0) + actual_energy_from_grid

                    # 检查充电是否完成
                    charging_start_time = charger.get("charging_start_time", current_time - timedelta(minutes=time_step_minutes))
                    charging_duration_minutes = (current_time - charging_start_time).total_seconds() / 60
                    max_charging_time = 180
                    if charger_type == "superfast": max_charging_time = 30
                    elif charger_type == "fast": max_charging_time = 60

                    # 结束充电逻辑
                    if new_soc >= target_soc - 0.5 or charging_duration_minutes >= max_charging_time - 0.1:
                        reason = "target_reached" if new_soc >= target_soc - 0.5 else "time_limit_exceeded"
                        
                        if is_manual_decision:
                            logger.info(f"Manual decision user {current_user_id} finished charging at {charger_id} ({reason}). Final SOC: {new_soc:.1f}%")
                        else:
                            logger.info(f"User {current_user_id} finished charging at {charger_id} ({reason}). Final SOC: {new_soc:.1f}%")

                        session_energy = charger.get("daily_energy", 0) - charger.get("_prev_energy", 0)
                        session_revenue = charger.get("daily_revenue", 0) - charger.get("_prev_revenue", 0)
                        charging_session = {
                            "user_id": current_user_id, "charger_id": charger_id,
                            "start_time": charging_start_time.isoformat(), "end_time": current_time.isoformat(),
                            "duration_minutes": round(charging_duration_minutes, 2),
                            "initial_soc": initial_soc, "final_soc": new_soc,
                            "energy_charged_grid": round(session_energy, 3),
                            "cost": round(session_revenue, 2), "termination_reason": reason,
                            "manual_decision": is_manual_decision
                        }
                        completed_sessions_this_step.append(charging_session)
                        
                        if "charging_history" not in user: user["charging_history"] = []
                        user["charging_history"].append(charging_session)

                        # 重置状态
                        charger["status"] = "available"
                        charger["current_user"] = None
                        charger["charging_start_time"] = None
                        charger["_prev_energy"] = charger.get("daily_energy", 0)
                        charger["_prev_revenue"] = charger.get("daily_revenue", 0)

                        user["status"] = "post_charge"
                        user["target_charger"] = None
                        user["post_charge_timer"] = random.randint(1, 3)
                        user["initial_soc"] = None
                        user["target_soc"] = None
                        # 保留手动决策标记直到post_charge结束

        # 处理等待队列 - 优先处理手动决策用户
        if charger.get("status") == "available" and charger.get("queue"):
            queue = charger["queue"]
            
            # 重新排序队列，手动决策用户优先
            manual_users = []
            regular_users = []
            
            for queued_user_id in queue:
                if queued_user_id in users:
                    user = users[queued_user_id]
                    if user.get("status") == "waiting":
                        if user.get("manual_decision"):
                            manual_users.append(queued_user_id)
                        else:
                            regular_users.append(queued_user_id)
            
            # 重新排列队列：手动决策用户优先
            charger["queue"] = manual_users + regular_users
            
            if charger["queue"]:
                next_user_id = charger["queue"][0]
                
                if next_user_id in users:
                    next_user = users[next_user_id]
                    if next_user.get("status") == "waiting":
                        is_manual = next_user.get("manual_decision", False)
                        if is_manual:
                            logger.info(f"Starting charging for manual decision user {next_user_id} at {charger_id}")
                        else:
                            logger.info(f"Starting charging for user {next_user_id} at {charger_id}")

                        # 更新充电桩状态
                        charger["status"] = "occupied"
                        charger["current_user"] = next_user_id
                        charger["charging_start_time"] = current_time
                        charger["_prev_energy"] = charger.get("daily_energy", 0)
                        charger["_prev_revenue"] = charger.get("daily_revenue", 0)

                        # 更新用户状态
                        next_user["status"] = "charging"
                        
                        # 使用手动设置的目标SOC或默认值
                        if is_manual and 'manual_charging_params' in next_user:
                            target_soc = next_user['manual_charging_params'].get('target_soc', 80)
                        else:
                            target_soc = min(95, next_user.get("soc", 0) + 60)
                        
                        next_user["target_soc"] = target_soc
                        next_user["initial_soc"] = next_user.get("soc", 0)

                        # 从队列中移除
                        charger["queue"].pop(0)
                        logger.debug(f"User {next_user_id} removed from queue {charger_id}.")

    return total_ev_load, completed_sessions_this_step