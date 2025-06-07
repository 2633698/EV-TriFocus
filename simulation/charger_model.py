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
    env_conf = config.get('environment', {})
    charger_params = env_conf.get('charger_model_params', {})
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
                base_efficiency = user.get("charging_efficiency", 0.92) # This is user's base vehicle efficiency
                
                # Efficiency boost calculation from charger_params
                manual_boost_val = charger_params.get('manual_decision_efficiency_boost', 0.03)
                fast_pref_boost_factor_val = charger_params.get('fast_pref_efficiency_boost_factor', 0.02)
                fast_pref_thresh_val = charger_params.get('fast_pref_threshold_for_boost', 0.7)
                low_fast_pref_boost_factor_val = charger_params.get('low_fast_pref_efficiency_boost_factor', 0.01)
                low_fast_pref_thresh_val = charger_params.get('low_fast_pref_threshold', 0.3)
                max_efficiency_val = charger_params.get('max_total_efficiency_clamp', 0.95)

                fast_charging_preference = user.get("fast_charging_preference", 0.5)
                efficiency_boost = 0.0
                
                if is_manual_decision:
                    preferred_type = user.get("preferred_charging_type", "快充")
                    if preferred_type == "快充" and charger_type in ["fast", "superfast"]:
                        efficiency_boost += manual_boost_val
                        logger.info(f"=== MANUAL DECISION CHARGING OPTIMIZATION ===")
                        logger.info(f"User {current_user_id} getting optimized charging at charger {charger_id}")
                        logger.info(f"Preferred type: {preferred_type}, Charger type: {charger_type}")
                        logger.info(f"Current SOC: {current_soc:.1f}%, Target SOC: {target_soc}%")
                    else:
                        logger.info(f"=== MANUAL DECISION CHARGING STARTED ===")
                        logger.info(f"User {current_user_id} charging at charger {charger_id}")
                        logger.info(f"Preferred type: {preferred_type}, Charger type: {charger_type}")
                        logger.info(f"Current SOC: {current_soc:.1f}%, Target SOC: {target_soc}%")
                
                # According to fast charging preference
                if charger_type in ["fast", "superfast"]:
                    if fast_charging_preference > fast_pref_thresh_val:
                        # Normalize preference effect: (preference - threshold) / (1.0 - threshold)
                        norm_pref = (fast_charging_preference - fast_pref_thresh_val) / (1.0 - fast_pref_thresh_val + 1e-5)
                        preference_boost = fast_pref_boost_factor_val * norm_pref
                        efficiency_boost += preference_boost
                        logger.debug(f"User {current_user_id} high fast pref ({fast_charging_preference:.2f}) on {charger_type} gets +{preference_boost:.3f} efficiency.")
                elif charger_type == "normal" and fast_charging_preference < low_fast_pref_thresh_val:
                    # Normalize preference effect: (threshold - preference) / threshold
                    norm_pref = (low_fast_pref_thresh_val - fast_charging_preference) / (low_fast_pref_thresh_val + 1e-5)
                    preference_boost = low_fast_pref_boost_factor_val * norm_pref
                    efficiency_boost += preference_boost
                    logger.debug(f"User {current_user_id} low fast pref ({fast_charging_preference:.2f}) on normal gets +{preference_boost:.3f} efficiency.")
                
                old_efficiency = base_efficiency
                final_efficiency = min(max_efficiency_val, base_efficiency * (1 + efficiency_boost))
                
                if efficiency_boost > 0:
                    logger.debug(f"Charging efficiency for {current_user_id}: Base={base_efficiency:.3f}, Boost={efficiency_boost:.3f}, Final={final_efficiency:.3f}")

                # SOC Tapering
                soc_tapering_curve = charger_params.get('soc_tapering_curve', [
                    [20, 1.0, 0.0], [50, 1.0, -0.003333], [80, 0.9, -0.006667], [100, 0.7, -0.025]
                ])
                min_taper_factor = charger_params.get('min_soc_taper_factor', 0.1)

                soc_factor = 1.0 # Default if no matching tier
                for i in range(len(soc_tapering_curve)):
                    tier_soc_thresh, tier_start_factor, tier_slope = soc_tapering_curve[i]
                    if current_soc < tier_soc_thresh:
                        if i == 0: # Below first threshold
                            soc_factor = tier_start_factor
                        else: # In between thresholds or within a sloped segment
                            prev_tier_soc, prev_tier_factor, _ = soc_tapering_curve[i-1]
                            # The slope in config is per unit of SOC over the range of that tier
                            # Example: -0.1/30 means a 0.1 drop over 30 SOC points
                            # So, (current_soc - prev_tier_soc) * slope_from_config
                            # The config has slope_factor_over_range, so it's already per unit of SOC in that range
                            # Let's assume the slope is just the factor to multiply (current_soc - prev_tier_soc)
                            soc_factor = prev_tier_factor + (current_soc - prev_tier_soc) * soc_tapering_curve[i-1][2] # Use previous tier's slope
                        break
                else: # If current_soc is >= last threshold
                    last_tier_soc, last_tier_factor, last_tier_slope = soc_tapering_curve[-1]
                    soc_factor = last_tier_factor + (current_soc - last_tier_soc) * last_tier_slope

                soc_factor = max(min_taper_factor, soc_factor) # Clamp to min factor
                
                actual_power = power_limit * soc_factor
                power_to_battery = actual_power * final_efficiency

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
                    
                    if is_manual_decision:
                        price_multiplier *= charger_params.get('manual_decision_price_discount_factor', 0.98)
                    
                    revenue = actual_energy_from_grid * current_price * price_multiplier
                    charger["daily_revenue"] = charger.get("daily_revenue", 0) + revenue
                    charger["daily_energy"] = charger.get("daily_energy", 0) + actual_energy_from_grid

                    # 检查充电是否完成
                    charging_start_time = charger.get("charging_start_time", current_time - timedelta(minutes=time_step_minutes))
                    charging_duration_minutes = (current_time - charging_start_time).total_seconds() / 60

                    max_times_by_type = charger_params.get('max_charging_time_minutes_by_type', {"default": 180, "superfast": 30, "fast": 60})
                    max_charging_time = max_times_by_type.get(charger_type, max_times_by_type.get("default", 180))

                    # 结束充电逻辑
                    # Allow a small tolerance for target_soc, e.g. 0.5%
                    target_soc_reached = new_soc >= (target_soc - 0.5)
                    time_limit_exceeded = charging_duration_minutes >= (max_charging_time - 0.1) # Small tolerance for time limit

                    if target_soc_reached or time_limit_exceeded:
                        reason = "target_reached" if target_soc_reached else "time_limit_exceeded"
                        if is_manual_decision:
                            logger.info(f"=== MANUAL DECISION CHARGING COMPLETED ===")
                            logger.info(f"User {current_user_id} finished charging at charger {charger_id}")
                            logger.info(f"Completion reason: {reason}")
                            logger.info(f"SOC progress: {initial_soc:.1f}% -> {new_soc:.1f}% (target: {target_soc}%)")
                            logger.info(f"Charging duration: {charging_duration_minutes:.1f} minutes")
                            logger.info(f"Preferred charging type: {user.get('preferred_charging_type', 'N/A')}")
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

                        # 处理预约完成
                        if user.get('reservation_id'):
                            from reservation_system import reservation_manager
                            reservation_id = user.get('reservation_id')
                            if reservation_manager.completeReservation(reservation_id):
                                logger.info(f"预约 {reservation_id} 已完成 - 用户 {current_user_id} 充电结束")
                            user['reservation_id'] = None
                            user['is_reservation_user'] = False

                        # 重置状态
                        charger["status"] = "available"
                        charger["current_user"] = None
                        charger["charging_start_time"] = None
                        charger["_prev_energy"] = charger.get("daily_energy", 0)
                        charger["_prev_revenue"] = charger.get("daily_revenue", 0)

                        user["status"] = "post_charge"
                        user["target_charger"] = None

                        min_post_steps = charger_params.get('user_post_charge_min_timer_steps', 1)
                        max_post_steps_normal = charger_params.get('user_post_charge_max_timer_steps_normal', 3)
                        max_post_steps_profiled = charger_params.get('user_post_charge_max_timer_steps_profiled', {})
                        user_type_for_timer = user.get('user_type', 'private_default') # Use a default key if user_type not in map
                        max_steps = max_post_steps_profiled.get(user_type_for_timer, max_post_steps_normal)
                        user["post_charge_timer"] = random.randint(min_post_steps, max_steps)

                        user["initial_soc"] = None
                        user["target_soc"] = None # Clear target SOC after charging
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

                        # 检查手动决策用户是否被锁定到特定充电桩
                        if is_manual and next_user.get("manual_decision_locked"):
                            target_charger = next_user.get("target_charger")
                            if target_charger != charger_id:
                                logger.warning(f"=== MANUAL DECISION VIOLATION PREVENTED ===")
                                logger.warning(f"Manual user {next_user_id} locked to {target_charger}, cannot charge at {charger_id}")
                                logger.warning(f"Removing user from wrong charger queue")
                                # 从错误的充电桩队列中移除
                                charger["queue"].pop(0)
                                continue
                        
                        # 更新充电桩状态
                        charger["status"] = "occupied"
                        charger["current_user"] = next_user_id
                        charger["charging_start_time"] = current_time
                        charger["_prev_energy"] = charger.get("daily_energy", 0)
                        charger["_prev_revenue"] = charger.get("daily_revenue", 0)

                        # 更新用户状态
                        next_user["status"] = "charging"
                        
                        # 为手动决策用户记录成功分配
                        if is_manual:
                            logger.info(f"=== MANUAL DECISION SUCCESSFULLY EXECUTED ===")
                            logger.info(f"Manual user {next_user_id} successfully assigned to target charger {charger_id}")
                            logger.info(f"Manual decision fulfilled as requested")
                        
                        # Set target SOC for the new session
                        default_target_soc_val = charger_params.get('default_target_soc_if_not_set', 95)
                        default_charge_needed_val = charger_params.get('default_charge_needed_for_target_soc', 60)

                        if is_manual and 'manual_charging_params' in next_user and next_user['manual_charging_params'].get('target_soc') is not None:
                            target_soc = next_user['manual_charging_params']['target_soc']
                        elif next_user.get('is_reservation_user') and next_user.get('target_soc') is not None: # Reservation might set target_soc
                            target_soc = next_user['target_soc']
                        else: # Default logic if not manual or reservation with specific target
                            current_soc_val = next_user.get("soc", 0)
                            if current_soc_val + default_charge_needed_val < default_target_soc_val:
                                target_soc = default_target_soc_val
                            else:
                                target_soc = min(100, current_soc_val + default_charge_needed_val)
                        
                        next_user["target_soc"] = target_soc
                        next_user["initial_soc"] = next_user.get("soc", 0) # Record SOC at start of charge

                        # 从队列中移除
                        charger["queue"].pop(0)
                        logger.debug(f"User {next_user_id} removed from queue {charger_id}.")

    return total_ev_load, completed_sessions_this_step