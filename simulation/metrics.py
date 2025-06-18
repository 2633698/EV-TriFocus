# ev_charging_project/simulation/metrics.py

import logging
import math
import random
from datetime import datetime
import numpy # Added for numpy.std

logger = logging.getLogger(__name__)

# --- New Metric Calculation Functions ---

def calculate_peak_reduction(coordinated_load_profile: list[float], uncoordinated_load_profile: list[float]) -> float:
    """Calculates the percentage reduction in peak load."""
    if not coordinated_load_profile or not uncoordinated_load_profile:
        logger.warning("Empty load profile(s) provided to calculate_peak_reduction.")
        return 0.0

    max_coord_load = max(coordinated_load_profile)
    max_uncoord_load = max(uncoordinated_load_profile)

    if max_uncoord_load == 0:
        if max_coord_load == 0:
            return 100.0 # No load in either case, effectively 100% reduction of zero peak
        else:
            # Uncoordinated had no load, but coordinated has load - this is unusual, implies negative reduction (increase)
            # Or could be seen as undefined or infinitely bad. For percentage, let's return a large negative.
            logger.warning(f"Uncoordinated peak load is 0, but coordinated is {max_coord_load}. Peak reduction is ill-defined.")
            return -float('inf') # Or handle as per specific requirements, e.g., -100 * (max_coord_load / some_reference_load_if_available)

    reduction = max_uncoord_load - max_coord_load
    reduction_percentage = (reduction / max_uncoord_load) * 100
    return reduction_percentage

def calculate_load_balance_improvement(coordinated_load_profile: list[float], uncoordinated_load_profile: list[float]) -> float:
    """Calculates the improvement in load balance (reduction in standard deviation)."""
    if not coordinated_load_profile or not uncoordinated_load_profile:
        logger.warning("Empty load profile(s) provided to calculate_load_balance_improvement.")
        return 0.0

    std_dev_coord = numpy.std(coordinated_load_profile)
    std_dev_uncoord = numpy.std(uncoordinated_load_profile)

    if std_dev_uncoord == 0:
        if std_dev_coord == 0:
            return 0.0 # Both are perfectly flat, no improvement needed or made if interpreted as absolute reduction.
        else:
            # Uncoordinated was flat, coordinated is not - implies worsening.
            logger.warning(f"Uncoordinated load profile StdDev is 0, but coordinated is {std_dev_coord}. Load balance worsened.")
            return -std_dev_coord # Negative improvement (increase in std dev)

    improvement_metric = std_dev_uncoord - std_dev_coord
    # This returns the absolute reduction in StdDev.
    # If percentage improvement was desired: (improvement_metric / std_dev_uncoord) * 100
    return improvement_metric


def calculate_renewable_energy_percentage(total_load_profile: list[float], renewable_generation_profile: list[float]) -> float:
    """Calculates the percentage of total load met by renewable energy."""
    if not total_load_profile or not renewable_generation_profile:
        return 0.0
    
    min_len = min(len(total_load_profile), len(renewable_generation_profile))
    if min_len == 0:
        return 0.0

    total_load_profile = total_load_profile[:min_len]
    renewable_generation_profile = renewable_generation_profile[:min_len]
    
    total_energy_consumed = sum(total_load_profile)
    if total_energy_consumed == 0:
        return 0.0 # 不能说100%，因为没有消耗也就没有使用

    # --- START OF FIX ---
    # 核心修复：计算实际使用的可再生能源
    # 在每个时间步，实际使用的可再生能源 = min(当前负荷, 当前可再生能源发电量)
    renewable_energy_used = sum(
        min(load, gen) for load, gen in zip(total_load_profile, renewable_generation_profile)
    )
    
    # 百分比 = (实际使用的可再生能源 / 总消耗的能源) * 100
    renewable_percentage = (renewable_energy_used / total_energy_consumed) * 100 if total_energy_consumed > 0 else 0
    # --- END OF FIX ---
    return renewable_percentage


# --- Modified calculate_rewards or a new wrapper ---
# For now, let's extend calculate_rewards and assume profiles are passed in via `state` or `config`
# This part will need careful integration with how profiles are generated/accessed.


def calculate_rewards(state, config):
    """
    计算当前状态下的奖励值，并包含无序充电基准对比。

    Args:
        state (dict): 当前环境状态 (包含 users, chargers, grid_status)
        config (dict): 全局配置

    Returns:
        dict: 包含各项奖励指标及对比指标的字典
    """
    
    # --- START OF NESTED HELPER FUNCTION ---
    # 将 _estimate_uncoordinated_charging_metrics 移动到这里并缩进
    def _estimate_uncoordinated_charging_metrics(state, config, baseline_cfg, avg_soc, operator_profit, renewable_ratio, hour, peak_hours, valley_hours, weights):
        """
        估算无序充电情况下的基准指标。
        
        Args:
            state (dict): 当前环境状态
            config (dict): 全局配置
            baseline_cfg (dict): 基准估算配置
            avg_soc (float): 平均SOC
            operator_profit (float): 运营商利润
            renewable_ratio (float): 可再生能源比例
            hour (int): 当前小时
            peak_hours (list): 峰值小时列表
            valley_hours (list): 谷值小时列表
            weights (dict): 权重配置
        
        Returns:
            dict: 包含基准指标的字典
        """
        logger.debug("Estimating uncoordinated charging baseline metrics")
        
        # 基准用户满意度估算 (通常比协调充电更低)
        baseline_satisfaction_factor = baseline_cfg.get('satisfaction_degradation_factor', 0.7)
        baseline_user_satisfaction = avg_soc * baseline_satisfaction_factor
        
        # 基准运营商利润估算 (可能略有不同，但通常相近)
        baseline_profit_factor = baseline_cfg.get('profit_factor', 0.95)
        baseline_operator_profit = operator_profit * baseline_profit_factor
        
        # 基准电网友好性估算 (通常更差)
        baseline_grid_factor = baseline_cfg.get('grid_friendliness_factor', 0.6)
        # 在峰值时段，无序充电会显著降低电网友好性
        if hour in peak_hours:
            baseline_grid_factor *= baseline_cfg.get('peak_hour_penalty', 0.5)
        elif hour in valley_hours:
            baseline_grid_factor *= baseline_cfg.get('valley_hour_bonus', 1.1)
        
        baseline_grid_friendliness = renewable_ratio * baseline_grid_factor
        
        # 计算基准总奖励
        baseline_total_reward = (
            baseline_user_satisfaction * weights.get("user_satisfaction", 0.4) +
            baseline_operator_profit * weights.get("operator_profit", 0.3) +
            baseline_grid_friendliness * weights.get("grid_friendliness", 0.3)
        )
        
        logger.debug(f"Baseline User Satisfaction: {baseline_user_satisfaction:.4f}")
        logger.debug(f"Baseline Operator Profit: {baseline_operator_profit:.4f}")
        logger.debug(f"Baseline Grid Friendliness: {baseline_grid_friendliness:.4f}")
        logger.debug(f"Baseline Total Reward: {baseline_total_reward:.4f}")
        
        return {
            "baseline_user_satisfaction": baseline_user_satisfaction,
            "baseline_operator_profit": baseline_operator_profit,
            "baseline_grid_friendliness": baseline_grid_friendliness,
            "baseline_total_reward": baseline_total_reward
        }
    # --- END OF NESTED HELPER FUNCTION ---

    users = state.get('users', [])
    chargers = state.get('chargers', [])
    grid_status_dict = state.get('grid_status', {})
    current_time_str = state.get('timestamp', datetime.now().isoformat())
    try:
        current_time = datetime.fromisoformat(current_time_str)
    except ValueError:
        current_time = datetime.now()
    hour = current_time.hour

    total_users = len(users) if users else 1
    total_chargers = len(chargers) if chargers else 1

    # --- 1. 用户满意度 (协调后) ---
    soc_sum = sum(u.get('soc', 0) for u in users if isinstance(u.get('soc'), (int, float)))
    avg_soc = soc_sum / total_users if total_users > 0 else 0
    waiting_count = sum(1 for u in users if u.get('status') == 'waiting')
    metrics_cfg = config.get("metrics_params", {})
    user_sat_cfg = metrics_cfg.get("user_satisfaction", {})
    op_profit_cfg = metrics_cfg.get("operator_profit", {})
    grid_friend_cfg = metrics_cfg.get("grid_friendliness", {})
    comparison_cfg = metrics_cfg.get("algorithm_comparison_dummy_uncoordinated_profile", {})
    power_quality_cfg = metrics_cfg.get("power_quality_metrics", {})
    carbon_savings_cfg = metrics_cfg.get("carbon_savings_calculation", {})
    user_satisfaction_raw = (avg_soc / 100.0) * \
                            (1 - user_sat_cfg.get("waiting_penalty_factor", 0.5) * (waiting_count / total_users if total_users > 0 else 0))
    
    user_satisfaction = user_satisfaction_raw * user_sat_cfg.get("final_scale_factor", 2.0) + user_sat_cfg.get("final_offset_factor", -1.0)
    user_satisfaction = max(-1.0, min(1.0, user_satisfaction))
    logger.debug(f"Calculated User Satisfaction: {user_satisfaction:.4f}")


    # --- 2. 运营商利润 (协调后) ---
    peak_hours = grid_status_dict.get("peak_hours", [])
    valley_hours = grid_status_dict.get("valley_hours", [])
    history = state.get('history', [])
    
    current_revenue = {}
    current_energy = {}
    for c in chargers:
        if isinstance(c, dict):
            charger_id = c.get('id', c.get('charger_id'))
            if charger_id:
                current_revenue[charger_id] = c.get('daily_revenue', 0)
                current_energy[charger_id] = c.get('daily_energy', 0)
    
    time_window_steps = op_profit_cfg.get("time_window_steps_for_history", 4)
    previous_revenue = {}
    previous_energy = {}
    if len(history) >= time_window_steps:
        previous_state = history[-time_window_steps]
        previous_chargers = previous_state.get('chargers', [])
        for c in previous_chargers:
            if isinstance(c, dict):
                charger_id = c.get('id', c.get('charger_id'))
                if charger_id:
                    previous_revenue[charger_id] = c.get('daily_revenue', 0)
                    previous_energy[charger_id] = c.get('daily_energy', 0)
    
    period_revenue = 0
    period_energy = 0
    for charger_id, current_rev in current_revenue.items():
        prev_rev = previous_revenue.get(charger_id, current_rev) 
        period_revenue += max(0, current_rev - prev_rev)
    for charger_id, current_eng in current_energy.items():
        prev_eng = previous_energy.get(charger_id, current_eng)
        period_energy += max(0, current_eng - prev_eng)
    
    if len(history) < time_window_steps:
        fall_rev_div = op_profit_cfg.get("fallback_revenue_divisor_for_hourly_est", 24)
        fall_en_div = op_profit_cfg.get("fallback_energy_divisor_for_hourly_est", 24)
        period_revenue = sum(c.get('daily_revenue', 0) / fall_rev_div for c in chargers if isinstance(c.get('daily_revenue'), (int, float)))
        period_energy = sum(c.get('daily_energy', 0) / fall_en_div for c in chargers if isinstance(c.get('daily_energy'), (int, float)))
    
    occupied_chargers = sum(1 for c in chargers if c.get('status') == 'occupied')
    waiting_users = sum(1 for c in chargers if len(c.get('queue', [])) > 0)
    utilization = occupied_chargers / total_chargers if total_chargers > 0 else 0
    queue_utilization = waiting_users / total_chargers if total_chargers > 0 else 0
    
    util_w = op_profit_cfg.get("utilization_weight_in_combined", 0.7)
    queue_util_w = op_profit_cfg.get("queue_utilization_weight_in_combined", 0.3)
    combined_utilization = (utilization * util_w) + (queue_utilization * queue_util_w)
    
    current_price = grid_status_dict.get("current_price", 0.85)
    op_elec_cost_rate = op_profit_cfg.get("operator_electricity_cost_rate_from_retail", 0.85)
    electricity_cost = period_energy * current_price * op_elec_cost_rate
    
    maint_costs_hourly = op_profit_cfg.get("maintenance_cost_per_charger_hourly", {"normal": 0.2083})
    maintenance_cost = sum(maint_costs_hourly.get(c.get('type', 'normal'), maint_costs_hourly.get("default",0.2083)) for c in chargers if isinstance(c, dict))
    
    fixed_cost_base_hr = op_profit_cfg.get("fixed_cost_base_hourly", 4.1667)
    fixed_cost_per_charger_hr = op_profit_cfg.get("fixed_cost_per_charger_hourly", 0.0833)
    fixed_cost_scale_factor = op_profit_cfg.get("fixed_cost_scale_effect_factor", 50)
    fixed_cost = fixed_cost_base_hr + (fixed_cost_per_charger_hr * total_chargers * (0.7 + 0.3 * math.exp(-total_chargers/ (fixed_cost_scale_factor + 1e-6) )))
    
    total_cost = electricity_cost + maintenance_cost + fixed_cost
    net_profit = period_revenue - total_cost
    
    invest_per_type = op_profit_cfg.get("investment_per_charger_type", {"normal": 5000})
    total_investment = sum(invest_per_type.get(c.get('type', 'normal'), invest_per_type.get("default", 5000)) for c in chargers if isinstance(c, dict))
    
    lifespan_years = op_profit_cfg.get("charger_lifespan_years_for_roi", 10)
    hourly_investment_cost = total_investment / (lifespan_years * 365 * 24) if lifespan_years > 0 else float('inf')
    hourly_roi = net_profit / hourly_investment_cost if hourly_investment_cost > 0 and hourly_investment_cost != float('inf') else (net_profit if hourly_investment_cost == 0 else 0)

    time_factors_profit = op_profit_cfg.get("time_factors_hourly_profit", {"default":0.0})
    time_factor = time_factors_profit.get("default",0.0)
    if hour in peak_hours: time_factor = time_factors_profit.get("peak", -0.1)
    elif hour in valley_hours: time_factor = time_factors_profit.get("valley", 0.2)
    
    util_score_base_mult = op_profit_cfg.get("utilization_score_base_multiplier", 0.8)
    util_score_high_bonus_thresh = op_profit_cfg.get("utilization_score_high_bonus_threshold", 0.8)
    util_score_high_bonus_factor = op_profit_cfg.get("utilization_score_high_bonus_factor", 0.5)
    util_score_low_penalty_thresh = op_profit_cfg.get("utilization_score_low_penalty_threshold", 0.2)
    util_score_low_penalty_factor = op_profit_cfg.get("utilization_score_low_penalty_factor", 0.8)

    utilization_score = combined_utilization * util_score_base_mult
    if combined_utilization > util_score_high_bonus_thresh:
        utilization_score += (combined_utilization - util_score_high_bonus_thresh) * util_score_high_bonus_factor
    elif combined_utilization < util_score_low_penalty_thresh:
        utilization_score *= util_score_low_penalty_factor
    
    target_hr_rev_base = op_profit_cfg.get("target_hourly_revenue_per_charger_base", 4.1667)
    target_hourly_revenue = target_hr_rev_base * total_chargers
    revenue_ratio = period_revenue / target_hourly_revenue if target_hourly_revenue > 0 else 0
    
    rev_log_mult = op_profit_cfg.get("revenue_score_log_base_multiplier", 0.3)
    rev_log_input_mult = op_profit_cfg.get("revenue_score_log_input_multiplier", 3.0)
    rev_log_base = op_profit_cfg.get("revenue_score_log_base", 4.0)
    rev_max_score = op_profit_cfg.get("revenue_score_max", 0.6)
    revenue_score = min(rev_max_score, rev_log_mult * math.log(1 + revenue_ratio * rev_log_input_mult) / math.log(rev_log_base if rev_log_base > 1 else 4.0))
    
    roi_target_hr = op_profit_cfg.get("roi_target_hourly", 0.002083)
    roi_log_mult = op_profit_cfg.get("roi_score_log_base_multiplier", 0.2)
    roi_log_input_mult = op_profit_cfg.get("roi_score_log_input_multiplier", 5.0)
    roi_log_base = op_profit_cfg.get("roi_score_log_base", 6.0)
    roi_max_score = op_profit_cfg.get("roi_score_max", 0.4)
    roi_score = min(roi_max_score, roi_log_mult * math.log(1 + hourly_roi / (roi_target_hr  + 1e-9) * roi_log_input_mult) / math.log(roi_log_base if roi_log_base > 1 else 6.0)) if hourly_roi > 0 else 0
    
    operator_profit_raw = utilization_score + revenue_score + roi_score + time_factor
    
    op_raw_min = op_profit_cfg.get("profit_raw_min_clamp", 0.0)
    op_raw_max = op_profit_cfg.get("profit_raw_max_clamp", 1.0)
    operator_profit_raw = max(op_raw_min, min(op_raw_max, operator_profit_raw))
    
    op_final_scale = op_profit_cfg.get("profit_final_scale_factor", 2.0)
    op_final_offset = op_profit_cfg.get("profit_final_offset_factor", -1.0)
    operator_profit = op_final_scale * operator_profit_raw + op_final_offset
    operator_profit = max(-1.0, min(1.0, operator_profit))
    
    logger.debug(f"Calculated Operator Profit: {operator_profit:.4f} (Raw: {operator_profit_raw:.2f}, Util: {combined_utilization:.2f}, Revenue: {period_revenue:.2f}, ROI_hr: {hourly_roi:.4f})")

    # --- 3. 电网友好度 (增强版) ---
    current_load_percentage = grid_status_dict.get("grid_load_percentage", 50)
    renewable_ratio = grid_status_dict.get("renewable_ratio", 0) / 100.0 if grid_status_dict.get("renewable_ratio") is not None else 0.0
    total_load_abs = grid_status_dict.get("current_total_load", 0)
    ev_load_abs = grid_status_dict.get("current_ev_load", 0)
    regional_current_state = grid_status_dict.get("regional_current_state", {})
    regional_connections = grid_status_dict.get("regional_connections", {})

    load_tiers = grid_friend_cfg.get('load_factor_tiers', [[30,0.8,0.0],[50,0.5,-0.015],[70,0.2,-0.01],[85,0.0,-0.015]])
    default_slope = grid_friend_cfg.get('load_factor_default_slope', -0.01)
    default_base_penalty = grid_friend_cfg.get('load_factor_default_base_penalty', -0.225)
    max_penalty = grid_friend_cfg.get('load_factor_max_penalty', -0.5)
    load_factor = default_base_penalty 
    for i, (threshold, base_score, factor) in enumerate(load_tiers):
        if current_load_percentage < threshold:
            prev_threshold = load_tiers[i-1][0] if i > 0 else 0
            load_factor = base_score - (current_load_percentage - prev_threshold) * factor
            break
    else:
        last_threshold = load_tiers[-1][0] if load_tiers else 85
        load_factor = max(max_penalty, default_base_penalty - (current_load_percentage - last_threshold) * default_slope)

    renewable_factor = grid_friend_cfg.get('renewable_factor_multiplier', 0.8) * renewable_ratio
    
    time_scores = grid_friend_cfg.get('time_factor_scores', {"peak": -0.3, "valley": 0.6, "shoulder": 0.2})
    if hour in peak_hours: time_factor = time_scores.get('peak', -0.3)
    elif hour in valley_hours: time_factor = time_scores.get('valley', 0.6)
    else: time_factor = time_scores.get('shoulder', 0.2)
        
    ev_conc_thresh = grid_friend_cfg.get('ev_concentration_penalty_threshold', 0.3)
    ev_conc_factor_val = grid_friend_cfg.get('ev_concentration_penalty_factor', -0.15)
    ev_concentration_factor = 0.0
    if total_load_abs > 1e-6:
        ev_load_ratio = ev_load_abs / total_load_abs
        if ev_load_ratio > ev_conc_thresh:
            ev_concentration_factor = ev_conc_factor_val * (ev_load_ratio - ev_conc_thresh) / (1.0 - ev_conc_thresh + 1e-6)
            
    region_imbalance_std_thresh = grid_friend_cfg.get('region_imbalance_std_dev_threshold', 10.0)
    region_imbalance_penalty = grid_friend_cfg.get('region_imbalance_penalty_factor', -0.2)
    region_imbalance_scale = grid_friend_cfg.get('region_imbalance_penalty_scale_range', 30.0)
    region_imbalance_factor = 0.0
    if regional_current_state:
        load_percentages = [region.get('grid_load_percentage', 0) for region in regional_current_state.values() if region]
        if load_percentages:
            std_dev = numpy.std(load_percentages)
            if std_dev > region_imbalance_std_thresh:
                region_imbalance_factor = region_imbalance_penalty * min(1.0, (std_dev - region_imbalance_std_thresh) / (region_imbalance_scale + 1e-6) )
    
    carbon_intensity_factor = 0.0
    ci_thresholds = grid_friend_cfg.get('carbon_intensity_thresholds', [400,600,800])
    ci_scores = grid_friend_cfg.get('carbon_intensity_scores', [0.2, 0.1, 0.0, -0.1])
    if regional_current_state and len(ci_thresholds) == 3 and len(ci_scores) == 4:
        carbon_intensities = [region.get('carbon_intensity', ci_thresholds[1]) for region in regional_current_state.values() if region]
        if carbon_intensities:
            avg_carbon = sum(carbon_intensities) / len(carbon_intensities)
            if avg_carbon < ci_thresholds[0]: carbon_intensity_factor = ci_scores[0]
            elif avg_carbon < ci_thresholds[1]: carbon_intensity_factor = ci_scores[1]
            elif avg_carbon < ci_thresholds[2]: carbon_intensity_factor = ci_scores[2]
            else: carbon_intensity_factor = ci_scores[3]

    load_change_factor = 0.0
    lc_thresh = grid_friend_cfg.get('load_change_rate_threshold', 0.2)
    lc_penalty = grid_friend_cfg.get('load_change_penalty_factor', -0.15)
    lc_scale = grid_friend_cfg.get('load_change_penalty_scale_range', 0.3)
    history = state.get('history', [])
    if len(history) >= time_window_steps:
        prev_state_for_load_change = history[-time_window_steps]
        if prev_state_for_load_change and 'grid_status' in prev_state_for_load_change:
            prev_load = prev_state_for_load_change['grid_status'].get('current_total_load')
            if prev_load is not None and total_load_abs is not None and prev_load > 1e-6:
                load_change_rate = abs(total_load_abs - prev_load) / prev_load
                if load_change_rate > lc_thresh:
                    load_change_factor = lc_penalty * min(1.0, (load_change_rate - lc_thresh) / (lc_scale + 1e-6))
    
    transfer_factor = 0.0
    tr_thresh = grid_friend_cfg.get('transfer_ratio_threshold', 0.7)
    tr_penalty = grid_friend_cfg.get('transfer_penalty_factor', -0.1)
    tr_scale = grid_friend_cfg.get('transfer_penalty_scale_range', 0.3)
    if regional_connections:
        total_transfer = sum(conn.get('current_transfer', 0) for conn in regional_connections.values())
        total_capacity = sum(conn.get('transfer_capacity', 1000) for conn in regional_connections.values())
        if total_capacity > 1e-6:
            transfer_ratio = abs(total_transfer) / total_capacity
            if transfer_ratio > tr_thresh:
                transfer_factor = tr_penalty * min(1.0, (transfer_ratio - tr_thresh) / (tr_scale + 1e-6))

    grid_friendliness_raw = sum([
        load_factor, renewable_factor, time_factor, ev_concentration_factor,
        region_imbalance_factor, carbon_intensity_factor, load_change_factor, transfer_factor
    ])
    
    gf_raw_min = grid_friend_cfg.get('grid_raw_min_clamp', -0.9)
    gf_raw_max = grid_friend_cfg.get('grid_raw_max_clamp', 1.0)
    grid_friendliness_raw = max(gf_raw_min, min(gf_raw_max, grid_friendliness_raw))

    neg_adjust = grid_friend_cfg.get('grid_negative_score_adjustment_factor', 0.8)
    pos_adjust = grid_friend_cfg.get('grid_positive_score_adjustment_factor', 1.1)
    if grid_friendliness_raw < 0: grid_friendliness = grid_friendliness_raw * neg_adjust
    else: grid_friendliness = min(1.0, grid_friendliness_raw * pos_adjust)
    
    logger.debug(f"Grid Friendliness Components: Load={load_factor:.2f}, Renewable={renewable_factor:.2f}, "  
                f"Time={time_factor:.2f}, EV Concentration={ev_concentration_factor:.2f}, "  
                f"Region Imbalance={region_imbalance_factor:.2f}, Carbon={carbon_intensity_factor:.2f}, "  
                f"Load Change={load_change_factor:.2f}, Transfer={transfer_factor:.2f}")
    logger.debug(f"Calculated Grid Friendliness: {grid_friendliness:.4f} (Raw: {grid_friendliness_raw:.4f})")


    # --- 4. 总奖励 (协调后) ---
    weights = config.get('scheduler', {}).get('optimization_weights', {
        "user_satisfaction": 0.4, "operator_profit": 0.3, "grid_friendliness": 0.3
    })
    total_reward = (user_satisfaction * weights["user_satisfaction"] +
                    operator_profit * weights["operator_profit"] +
                    grid_friendliness * weights["grid_friendliness"])
    logger.debug(f"Calculated Total Reward: {total_reward:.4f}")


    # --- 5. 无序充电基准对比 ---
    baseline_cfg = metrics_cfg.get("uncoordinated_baseline_estimation", {})
    # This is the line that caused the error. Now the function is nested, so it's in scope.
    results = _estimate_uncoordinated_charging_metrics(state, config, baseline_cfg, avg_soc, operator_profit, renewable_ratio, hour, peak_hours, valley_hours, weights)
    results["user_satisfaction"] = user_satisfaction
    results["operator_profit"] = operator_profit
    results["grid_friendliness"] = grid_friendliness
    results["total_reward"] = total_reward

    # --- Algorithm Comparison Metrics (Data for GUI) ---
    comparison_cfg = metrics_cfg.get("algorithm_comparison_dummy_uncoordinated_profile", {})
    
    grid_time_series = state.get('grid_status', {}).get('time_series_data_snapshot', {})
    coordinated_load_profile_regional = grid_time_series.get('regional_data', {})
    timestamps = grid_time_series.get('timestamps', [])
    num_steps = len(timestamps)

    # --- START OF FIX: 使用真实的协调和非协调数据 ---
    
    # 从 state 中直接获取由 SimulationWorker 准备好的曲线
    coordinated_total_load_profile = state.get('coordinated_load_profile', [])
    uncoordinated_load_profile = state.get('uncoordinated_load_profile', [])
    coordinated_total_renewable_gen_profile = state.get('renewable_generation_profile', [])
    
    # 确保曲线长度一致，以当前协调调度的步数为准
    current_steps = len(coordinated_total_load_profile)
    if len(uncoordinated_load_profile) >= current_steps:
        uncoordinated_load_profile = uncoordinated_load_profile[:current_steps]
    
    if coordinated_total_load_profile and uncoordinated_load_profile and len(uncoordinated_load_profile) == current_steps:
        peak_reduction_perc = calculate_peak_reduction(coordinated_total_load_profile, uncoordinated_load_profile)
        std_dev_uncoordinated = numpy.std(uncoordinated_load_profile)
        std_dev_coordinated = numpy.std(coordinated_total_load_profile)
        renewable_share_coord_perc = calculate_renewable_energy_percentage(coordinated_total_load_profile, coordinated_total_renewable_gen_profile)
        renewable_share_uncoord_perc = calculate_renewable_energy_percentage(uncoordinated_load_profile, coordinated_total_renewable_gen_profile)
        
        results['comparison_metrics_display'] = {
            'peak_reduction': {'uncoordinated': 0, 'coordinated': peak_reduction_perc},
            'load_balance': {'uncoordinated': std_dev_uncoordinated, 'coordinated': std_dev_coordinated},
            'renewable_share': {'uncoordinated': renewable_share_uncoord_perc, 'coordinated': renewable_share_coord_perc}
        }
    else:
        results['comparison_metrics_display'] = {'peak_reduction': {'uncoordinated': 0, 'coordinated': 0}, 'load_balance': {'uncoordinated': 0, 'coordinated': 0}, 'renewable_share': {'uncoordinated': 0, 'coordinated': 0}}
    
    logger.debug(f"Calculated Algorithm Comparison Metrics: {results['comparison_metrics_display']}")
    # --- Power Quality Metrics ---
    history = state.get('history', [])
    previous_total_load_profile = []
    if history:
        prev_grid_time_series = history[-1].get('grid_status', {}).get('time_series_data_snapshot', {})
        prev_regional_data = prev_grid_time_series.get('regional_data', {})
        prev_timestamps = prev_grid_time_series.get('timestamps', [])
        if prev_timestamps and prev_regional_data:
            previous_total_load_profile = [0.0] * len(prev_timestamps)
            for region_id, r_data in prev_regional_data.items():
                for i in range(len(prev_timestamps)):
                    previous_total_load_profile[i] += r_data.get('total_load', [0]*len(prev_timestamps))[i]
    
    current_ev_load_total = grid_status_dict.get('aggregated_metrics', {}).get('total_ev_load', 0)
    current_scheduling_algorithm = config.get('scheduler', {}).get('scheduling_algorithm', 'uncoordinated')
    v2g_active_kw_total = state.get('v2g_active_total_kw', 0)

    results['power_quality'] = {
        'voltage_stability': _calculate_voltage_stability_metric(grid_status_dict, coordinated_total_load_profile, power_quality_cfg),
        'frequency_stability': _calculate_frequency_stability_metric(grid_status_dict, coordinated_total_load_profile, previous_total_load_profile, power_quality_cfg),
        'grid_strain': _calculate_grid_strain_metric(grid_status_dict, current_ev_load_total, current_scheduling_algorithm, v2g_active_kw_total, power_quality_cfg)
    }
    logger.debug(f"Calculated Power Quality Metrics: {results['power_quality']}")

    # --- Carbon Savings Calculation ---
    time_step_minutes = config.get('environment', {}).get('time_step_minutes', 15)
    step_duration_hours = time_step_minutes / 60.0
    current_carbon_intensity_profile_aggregated = []
    if num_steps > 0 and coordinated_load_profile_regional:
        for i in range(num_steps):
            step_intensities = [region_data.get('carbon_intensity', [carbon_savings_cfg.get("default_carbon_intensity_g_kwh",300)]*num_steps)[i] 
                                for region_data in coordinated_load_profile_regional.values() if region_data]
            current_carbon_intensity_profile_aggregated.append(sum(step_intensities) / len(step_intensities) if step_intensities else carbon_savings_cfg.get("default_carbon_intensity_g_kwh",300))
    else:
        current_carbon_intensity_profile_aggregated = [carbon_savings_cfg.get("default_carbon_intensity_g_kwh",300)] * num_steps

    uncoordinated_carbon_intensity_profile_mock = [
        intensity * carbon_savings_cfg.get("mock_uncoordinated_intensity_multiplier", 1.2) 
        for intensity in current_carbon_intensity_profile_aggregated
    ]
    load_profile_kwh = [load_kw * step_duration_hours for load_kw in coordinated_total_load_profile]

    if coordinated_total_load_profile and current_carbon_intensity_profile_aggregated and uncoordinated_carbon_intensity_profile_mock:
        results['calculated_carbon_savings_kg'] = _calculate_carbon_savings(
            current_carbon_intensity_profile_aggregated,
            uncoordinated_carbon_intensity_profile_mock,
            load_profile_kwh
        )
        logger.debug(f"Calculated Carbon Savings: {results['calculated_carbon_savings_kg']:.2f} kg CO₂")
    else:
        results['calculated_carbon_savings_kg'] = 0.0
        logger.warning("Insufficient data for carbon savings calculation.")
        
    return results
# --- Carbon Savings Helper Function ---
def _calculate_carbon_savings(current_carbon_intensity_profile_g_kwh: list[float],
                             uncoordinated_carbon_intensity_profile_g_kwh: list[float],
                             load_profile_kwh: list[float]) -> float:
    """Calculates carbon savings in kg CO2."""
    if not (len(current_carbon_intensity_profile_g_kwh) == len(uncoordinated_carbon_intensity_profile_g_kwh) == len(load_profile_kwh)):
        logger.warning("Carbon intensity and load profiles have mismatched lengths. Cannot calculate savings.")
        return 0.0

    total_current_emissions_g = sum(
        intensity * energy
        for intensity, energy in zip(current_carbon_intensity_profile_g_kwh, load_profile_kwh)
    )
    total_baseline_emissions_g = sum(
        intensity * energy
        for intensity, energy in zip(uncoordinated_carbon_intensity_profile_g_kwh, load_profile_kwh)
    )

    savings_gCO2 = total_baseline_emissions_g - total_current_emissions_g
    savings_kgCO2 = savings_gCO2 / 1000.0

    return savings_kgCO2

# --- Power Quality Helper Functions ---

def _calculate_voltage_stability_metric(grid_status_dict, load_profile, pq_cfg):
    """Calculates a voltage stability indicator."""
    aggregated_metrics = grid_status_dict.get('aggregated_metrics', {})
    load_percentage = aggregated_metrics.get('overall_load_percentage', 50)
    thresholds = pq_cfg.get("voltage_stability_load_thresholds", [60, 80, 95])

    if load_percentage < thresholds[0]: 
        return {'text': '稳定', 'color': 'green'}
    elif load_percentage < thresholds[1]: 
        return {'text': '良好', 'color': 'lightgreen'}
    elif load_percentage < thresholds[2]: 
        return {'text': '波动风险', 'color': 'orange'}
    else:
        return {'text': '不稳定', 'color': 'red'}

def _calculate_frequency_stability_metric(grid_status_dict, current_load_profile, previous_load_profile, pq_cfg):
    """Calculates a frequency stability indicator based on load changes."""
    fallback_thresh = pq_cfg.get("frequency_stability_fallback_load_threshold", 75)
    ramp_thresholds = pq_cfg.get("frequency_stability_ramp_rate_thresholds_percent", [2.0, 5.0])

    if not current_load_profile or not previous_load_profile or not current_load_profile or not previous_load_profile:
        logger.debug("Frequency stability: Insufficient profile data. Using load percentage fallback.")
        aggregated_metrics = grid_status_dict.get('aggregated_metrics', {})
        load_percentage = aggregated_metrics.get('overall_load_percentage', 50)
        if load_percentage < fallback_thresh: return {'text': '稳定', 'color': 'green'}
        else: return {'text': '轻微波动', 'color': 'orange'}

    current_final_load = current_load_profile[-1]
    previous_final_load = previous_load_profile[-1]
    load_diff = abs(current_final_load - previous_final_load)
    total_capacity = grid_status_dict.get('aggregated_metrics', {}).get('total_capacity', 0)

    if total_capacity == 0 and current_final_load > 0:
        load_perc = grid_status_dict.get('aggregated_metrics', {}).get('overall_load_percentage', 50)
        total_capacity = current_final_load / (load_perc / 100.0 if load_perc > 0 else 0.5) # Estimate capacity
    if total_capacity == 0:
         logger.warning("Frequency stability: Total capacity is zero. Fallback.")
         return {'text': '稳定 (低负荷)', 'color': 'green'}

    ramp_rate_percentage = (load_diff / total_capacity) * 100 if total_capacity > 0 else 0

    if ramp_rate_percentage < ramp_thresholds[0]: return {'text': '稳定', 'color': 'green'}
    elif ramp_rate_percentage < ramp_thresholds[1]: return {'text': '轻微波动', 'color': 'orange'}
    else: return {'text': '较大波动', 'color': 'red'}

def _calculate_grid_strain_metric(grid_status_dict, current_total_ev_load, current_strategy, v2g_active_total_kw, pq_cfg):
    """Calculates a grid strain indicator."""
    aggregated_metrics = grid_status_dict.get('aggregated_metrics', {})
    total_load = aggregated_metrics.get('total_load', 0)
    strain_thresholds = pq_cfg.get("grid_strain_ev_load_ratio_thresholds_percent", [30, 15]) # [High, Medium]

    ev_load_ratio = (current_total_ev_load / total_load) * 100 if total_load > 0 else 0

    if current_strategy == "v2g_active" or v2g_active_total_kw > 0 :
        return {'text': '可变(双向)', 'color': '#F39C12'} 
    elif ev_load_ratio > strain_thresholds[0]: 
        return {'text': '升高', 'color': 'red'}
    elif ev_load_ratio > strain_thresholds[1]: 
        return {'text': '中等', 'color': 'orange'}
    else: 
        return {'text': '正常', 'color': 'green'}