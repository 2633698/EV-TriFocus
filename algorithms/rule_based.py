# ev_charging_project/algorithms/rule_based.py
import logging
import math
import random
from datetime import datetime
from collections import defaultdict
try:
    from simulation.utils import calculate_distance # 注意这里的导入路径
except ImportError:
    logging.error("Could not import calculate_distance from simulation.utils in rule_based.py")
    def calculate_distance(p1, p2): return 10.0 # Fallback

logger = logging.getLogger(__name__)

def schedule(state, config, manual_decisions=None, grid_preferences=None): # Added manual_decisions
    """
    基于规则的调度算法实现。

    Args:
        state (dict): 当前环境状态
        config (dict): 全局配置

    Returns:
        dict: 调度决策 {user_id: charger_id}
    """
    if grid_preferences:
        logger.debug(f"Rule-based algorithm received grid_preferences: {grid_preferences}")
    else:
        logger.debug("Rule-based algorithm received no grid_preferences.")

    decisions = {}
    scheduler_config = config.get('scheduler', {}) # For base weights
    env_config = config.get('environment', {})     # For some general params not in rule_based algo config yet

    algo_config = config.get('algorithms', {})
    rule_based_config = algo_config.get('rule_based', {})
    score_params_config = rule_based_config.get('score_params', {})
    user_score_params = score_params_config.get('user_satisfaction', {})
    profit_score_params = score_params_config.get('operator_profit', {})
    grid_score_params = score_params_config.get('grid_friendliness', {})
    dyn_weight_params = rule_based_config.get('dynamic_weight_adjustment', {})
    user_charge_trigger_config = rule_based_config.get('user_charge_trigger', {})


    # 获取当前时间、负载等信息
    timestamp = state.get("timestamp")
    grid_status = state.get("grid_status", {})
    # 使用 grid_load_percentage
    grid_load_percentage = grid_status.get("grid_load_percentage", grid_status.get("grid_load", 50)) # 兼容旧 key
    renewable_ratio = grid_status.get("renewable_ratio", 0)

    if not timestamp:
        logger.error("RuleBased: Timestamp missing in state.")
        return decisions
    try:
        # 处理可能的时区和微秒
        time_part = timestamp.split('+')[0].split('Z')[0].split('.')[0]
        current_dt = datetime.fromisoformat(time_part)
        current_hour = current_dt.hour
    except ValueError:
        logger.warning(f"RuleBased: Invalid timestamp format '{timestamp}'. Using current hour.")
        current_hour = datetime.now().hour

    users = state.get("users", [])
    chargers = state.get("chargers", [])
    if not users or not chargers:
        logger.warning("RuleBased: No users or chargers in state.")
        return decisions

    # 使用字典提高查找效率
    charger_dict = {c["charger_id"]: c for c in chargers if isinstance(c, dict) and "charger_id" in c}

    # 动态最大队列长度
    peak_hours = grid_status.get("peak_hours", [7, 8, 9, 10, 18, 19, 20, 21]) # Keep sourcing from grid_status or central config
    valley_hours = grid_status.get("valley_hours", [0, 1, 2, 3, 4, 5]) # Keep sourcing from grid_status or central config

    max_queue_conf = rule_based_config.get("max_queue", {"peak": 3, "valley": 12, "shoulder": 6})
    if current_hour in peak_hours: max_queue_len = max_queue_conf.get("peak", 3)
    elif current_hour in valley_hours: max_queue_len = max_queue_conf.get("valley", 12)
    else: max_queue_len = max_queue_conf.get("shoulder", 6)

    # 动态权重
    base_weights = scheduler_config.get("optimization_weights", { # These are the overall strategy weights
        "user_satisfaction": 0.33, "operator_profit": 0.33, "grid_friendliness": 0.34
    })
    weights = base_weights.copy()

    # Weight adjustment logic using dyn_weight_params
    if current_hour in peak_hours:
        peak_grid_boost_max = dyn_weight_params.get('peak_grid_boost_max', 0.3)
        peak_grid_boost_load_divisor = dyn_weight_params.get('peak_grid_boost_load_divisor', 200)
        grid_boost = min(peak_grid_boost_max, grid_load_percentage / peak_grid_boost_load_divisor if peak_grid_boost_load_divisor > 0 else 0)

        weights["grid_friendliness"] = min(0.7, weights["grid_friendliness"] + grid_boost) # Max cap

        user_reduction_factor = dyn_weight_params.get('peak_user_reduction_factor', 0.5)
        profit_reduction_factor = dyn_weight_params.get('peak_profit_reduction_factor', 0.5)
        weights["user_satisfaction"] = max(0.1, weights["user_satisfaction"] - grid_boost * user_reduction_factor) # Min cap
        weights["operator_profit"] = max(0.1, weights["operator_profit"] - grid_boost * profit_reduction_factor) # Min cap
    elif current_hour in valley_hours:
         weights["grid_friendliness"] = max(0.2, weights["grid_friendliness"] + dyn_weight_params.get('valley_grid_reduction', -0.15)) # Min cap
         weights["operator_profit"] = min(0.6, weights["operator_profit"] + dyn_weight_params.get('valley_profit_increase', 0.1)) # Max cap
         weights["user_satisfaction"] = min(0.6, weights["user_satisfaction"] + dyn_weight_params.get('valley_user_increase', 0.05)) # Max cap

    # Normalize weights
    total_w = sum(weights.values())
    if total_w > 0:
        for key in weights: weights[key] /= total_w
    # logger.info(f"RuleBased weights: User={weights['user_satisfaction']:.2f}, Profit={weights['operator_profit']:.2f}, Grid={weights['grid_friendliness']:.2f}")

    # 创建候选用户列表
    candidate_users = []
    # Sourcing from env_config as these are not in the prompt's rule_based algo config section
    min_charge_needed_for_scheduling = env_config.get("min_charge_threshold_percent", 20.0)
    default_base_soc_threshold = env_config.get("default_charge_soc_threshold", 40.0)

    profile_adjustments = user_charge_trigger_config.get('profile_threshold_adjustments', {})
    hour_adjustments = user_charge_trigger_config.get('hour_threshold_adjustments', {})
    min_clamp = user_charge_trigger_config.get('min_threshold_clamp', 15)
    max_clamp = user_charge_trigger_config.get('max_threshold_clamp', 60)
    target_soc_charge_to = user_charge_trigger_config.get('target_soc_charge_to', 95)

    for user in users:
        user_id = user.get("user_id")
        status = user.get("status", "")
        soc = user.get("soc", 100)
        if not user_id or status in ["charging", "waiting"] or not isinstance(soc, (int, float)):
            continue

        # Calculate dynamic SOC threshold for charging trigger
        threshold = default_base_soc_threshold # Start with a base default
        user_profile = user.get("user_profile", "normal") # Assuming 'normal' if not specified
        threshold += profile_adjustments.get(user_profile, 0)

        if current_hour in peak_hours:
            threshold += hour_adjustments.get('peak', 0)
        elif current_hour in valley_hours:
            threshold += hour_adjustments.get('valley', 0)

        threshold = max(min_clamp, min(max_clamp, threshold))

        needs_charge_flag = user.get("needs_charge_decision", False) # User explicitly requested
        charge_needed_percent = target_soc_charge_to - soc

        if (needs_charge_flag or (soc <= threshold and soc < 80)) and charge_needed_percent >= min_charge_needed_for_scheduling:
            urgency = (threshold - soc) / threshold if soc < threshold and threshold > 0 else 0
            urgency = min(1.0, max(0.0, urgency + (0.3 if needs_charge_flag else 0))) # Boost urgency if explicit request
            candidate_users.append((user_id, user, urgency, needs_charge_flag))

    candidate_users.sort(key=lambda x: (-int(x[3]), -x[2])) # 按需充电优先，然后按紧迫度
    # logger.info(f"RuleBased found {len(candidate_users)} candidates.")

    # 计算当前充电桩负载
    charger_loads = defaultdict(int)
    for cid, charger in charger_dict.items():
        if charger.get("status") == "failure": continue
        if charger.get("status") == "occupied": charger_loads[cid] += 1
        charger_loads[cid] += len(charger.get("queue", []))

    # 为候选用户分配充电桩
    assigned_users = set()
    num_assigned = 0
    for user_id, user, urgency, needs_charge in candidate_users:
        if user_id in assigned_users: continue

        best_charger_id = None
        best_score = float('-inf')
        user_pos = user.get("current_position", {})

        # 获取可用充电桩列表 (性能优化：只计算一次)
        available_chargers_with_dist = []
        for cid, charger in charger_dict.items():
            if charger.get("status") == "failure": continue
            if charger_loads.get(cid, 0) >= max_queue_len: continue # 提前过滤满队列
            dist = calculate_distance(user_pos, charger.get("position", {}))
            if dist == float('inf'): continue # 跳过无效距离
            available_chargers_with_dist.append((cid, charger, dist))

        # 按距离排序，并只考虑最近的 N 个
        available_chargers_with_dist.sort(key=lambda x: x[2])
    candidate_limit = rule_based_config.get("candidate_limit", 15)
    nearby_chargers_to_consider = available_chargers_with_dist[:candidate_limit]

        for charger_id, charger, distance in nearby_chargers_to_consider:
            # 调用评分函数
            current_queue_len = charger_loads.get(charger_id, 0) # 当前实际负载
        user_score = _calculate_user_satisfaction_score(user, charger, distance, current_queue_len, user_score_params)
        profit_score = _calculate_operator_profit_score(user, charger, state, profit_score_params)
        grid_score = _calculate_grid_friendliness_score(charger, state, grid_score_params)

        # 动态权重调整 based on critical urgency/SOC
            adjusted_weights = weights.copy()
        # Example: if grid_score < -0.5: adjusted_weights["grid_friendliness"] = min(0.8, adjusted_weights["grid_friendliness"] * 1.5)
        # This specific logic is not in dyn_weight_params, so I'll keep it simpler or it needs more config keys

        crit_urgency_thresh = dyn_weight_params.get('critical_urgency_threshold', 0.9)
        crit_soc_thresh = dyn_weight_params.get('critical_soc_threshold', 15)
        if urgency > crit_urgency_thresh and user.get("soc", 100) < crit_soc_thresh:
            crit_boost_factor = dyn_weight_params.get('critical_user_satisfaction_boost_factor', 1.5)
            crit_max_val = dyn_weight_params.get('critical_user_satisfaction_max', 0.6)
            adjusted_weights["user_satisfaction"] = min(crit_max_val, adjusted_weights["user_satisfaction"] * crit_boost_factor)

        # Normalize adjusted_weights
            total_adj_w = sum(adjusted_weights.values())
            if total_adj_w > 0:
                 for key in adjusted_weights: adjusted_weights[key] /= total_adj_w

            # 组合分数
            combined_score = (user_score * adjusted_weights["user_satisfaction"] +
                              profit_score * adjusted_weights["operator_profit"] +
                              grid_score * adjusted_weights["grid_friendliness"])

            # 队列惩罚
        queue_penalty = rule_based_config.get("queue_penalty", 0.05)
        penalized_score = combined_score - (current_queue_len * queue_penalty)

            if penalized_score > best_score:
                best_score = penalized_score
                best_charger_id = charger_id

        if best_charger_id:
            if user_id not in assigned_users:
                decisions[user_id] = best_charger_id
                charger_loads[best_charger_id] += 1 # 更新负载计数
                assigned_users.add(user_id)
                num_assigned += 1
                # logger.debug(f"RuleBased assigned user {user_id} to charger {best_charger_id} (Score: {best_score:.2f})")
        # else:
             # logger.warning(f"RuleBased could not find suitable charger for user {user_id}")

    logger.info(f"RuleBased made {num_assigned} assignments for {len(candidate_users)} candidates.")
    return decisions


# --- Scoring helper functions ---
def _calculate_user_satisfaction_score(user, charger, distance, current_queue_len, params):
    """Calculates user satisfaction score [-1, 1] using parameters from config."""

    # 1. Distance factor
    dist_tiers = params.get('distance_tiers', [[2, 0.5, -0.1], [5, 0.3, -0.1], [10, 0.0, -0.05]])
    default_dist_factor = params.get('default_dist_factor', -0.025)
    dist_base_penalty = params.get('dist_base_penalty', -0.25)
    distance_score = dist_base_penalty # Start with base penalty for long distances
    for tier_max_dist, base_score, per_km_penalty in dist_tiers:
        if distance < tier_max_dist:
            distance_score = base_score - (distance - (dist_tiers[[i[0] for i in dist_tiers].index(tier_max_dist)-1][0] if [i[0] for i in dist_tiers].index(tier_max_dist) > 0 else 0) ) * per_km_penalty
            break
    else: # Executed if loop doesn't break (distance > last tier_max_dist)
        last_tier_dist = dist_tiers[-1][0] if dist_tiers else 10
        distance_score = max(-0.5, dist_base_penalty - (distance - last_tier_dist) * default_dist_factor)

    # 2. Wait time factor
    wait_time_tiers = params.get('wait_time_tiers', [[0, 0.5], [2, 0.3], [5, 0.1], [8, -0.1]])
    default_wait_score = params.get('default_wait_score', -0.3)
    wait_score = default_wait_score
    for max_queue, score_val in wait_time_tiers:
        if current_queue_len <= max_queue:
            wait_score = score_val
            break

    # 3. Power matching factor
    charger_power = charger.get("max_power", 50)
    user_type = user.get("user_type", "private")
    user_soc = user.get("soc", 50)
    urgency = max(0, (params.get('power_expected_base_soc_threshold', 40) - user_soc) / params.get('power_expected_base_soc_threshold', 40)) if user_soc < params.get('power_expected_base_soc_threshold', 40) else 0

    power_expected_base = params.get('power_expected_base', 20)
    power_expected_urgency_factor = params.get('power_expected_urgency_factor', 30)
    expected_power = power_expected_base + urgency * power_expected_urgency_factor

    profile_factors = params.get('power_expected_profile_factors', {})
    expected_power *= profile_factors.get(user_type, 1.0)

    power_ratio = charger_power / expected_power if expected_power > 0 else 1.0
    power_score_tiers = params.get('power_score_tiers', [[1.5, 0.4], [1.0, 0.3], [0.7, 0.1], [0.5, -0.1]])
    default_power_score = params.get('default_power_score', -0.2)
    power_score = default_power_score
    for min_ratio, score_val in power_score_tiers:
        if power_ratio >= min_ratio:
            power_score = score_val
            break

    # 4. Price factor
    price_multiplier = charger.get("price_multiplier", 1.0) # Lower is better for user
    price_score_mult = params.get('price_score_multiplier', 0.5)
    price_score_max_abs = params.get('price_score_max_abs', 0.3)
    price_score = max(-price_score_max_abs, min(price_score_max_abs, (1.0 - price_multiplier) * price_score_mult))

    # 5. Emergency SOC adjustment
    emergency_factor = 1.0
    emergency_soc_thresholds = params.get('emergency_soc_thresholds', [15, 25])
    emergency_factors = params.get('emergency_factors', [1.5, 1.2])
    if user_soc < emergency_soc_thresholds[0]: emergency_factor = emergency_factors[0]
    elif user_soc < emergency_soc_thresholds[1]: emergency_factor = emergency_factors[1]

    # Combine components
    component_weights = params.get('component_weights', {"distance": 0.4, "wait_time": 0.3, "power": 0.15, "price": 0.15})
    satisfaction = (
        distance_score * component_weights.get('distance', 0.4) * emergency_factor +
        wait_score * component_weights.get('wait_time', 0.3) * emergency_factor +
        power_score * component_weights.get('power', 0.15) +
        price_score * component_weights.get('price', 0.15)
    )

    # Final adjustments
    if emergency_factor > 1.0 and satisfaction < params.get('emergency_satisfaction_min_score_adjustment', -0.5):
        satisfaction = max(params.get('emergency_satisfaction_min_score_adjustment', -0.5), satisfaction * params.get('emergency_satisfaction_adjustment_factor', 0.8))

    return max(-1.0, min(1.0, satisfaction))


def _calculate_operator_profit_score(user, charger, state, params):
    grid_status = state.get("grid_status", {})
    current_price = grid_status.get("current_price", 0.85) # Base electricity price
    user_soc = user.get("soc", 50)

    charge_needed_factor = (100 - user_soc) / 50.0 # Scale: more need = higher factor
    charger_type = charger.get("type", "normal")
    charger_price_multiplier = charger.get("price_multiplier", 1.0) # From charger's own settings
    queue_length = len(charger.get("queue", []))

    effective_price = current_price * charger_price_multiplier
    score = effective_price # Base score

    if charger_type == "fast": score *= params.get('fast_charger_multiplier', 1.15)
    elif charger_type == "superfast": score *= params.get('superfast_charger_multiplier', 1.30)

    score -= queue_length * params.get('queue_penalty_per_person', 0.15)
    score *= (1 + charge_needed_factor * params.get('charge_needed_score_factor', 0.05))

    norm_min = params.get('normalization_min_assumed_score', 0.5)
    norm_max = params.get('normalization_max_assumed_score', 2.0)
    normalized_score = (score - norm_min) / (norm_max - norm_min) if (norm_max - norm_min) != 0 else 0.5
    final_score = 2 * normalized_score - 1

    return max(-1.0, min(1.0, final_score))


def _calculate_grid_friendliness_score(charger, state, params):
    grid_status = state.get("grid_status", {})
    hour = datetime.fromisoformat(state.get('timestamp', '')).hour if state.get('timestamp') else datetime.now().hour
    grid_load_percentage = grid_status.get("grid_load_percentage", 50)
    renewable_ratio = grid_status.get("renewable_ratio", 0) / 100.0 if grid_status.get("renewable_ratio") is not None else 0.0
    peak_hours = grid_status.get("peak_hours", []) # Consider sourcing from main config or grid_status
    valley_hours = grid_status.get("valley_hours", [])
    charger_max_power = charger.get("max_power", 50)

    # 1. Load score
    load_tiers = params.get('load_score_tiers', [[30, 0.8, 0.0], [50, 0.5, -0.015], [70, 0.2, -0.01], [85, 0.0, -0.015]])
    default_load_factor = params.get('default_load_factor', -0.01)
    default_load_base_penalty = params.get('default_load_base_penalty', -0.225)
    max_load_penalty = params.get('max_load_score_penalty', -0.5)

    load_score = default_load_base_penalty
    for i, (threshold, base_score, factor) in enumerate(load_tiers):
        if grid_load_percentage < threshold:
            prev_threshold = load_tiers[i-1][0] if i > 0 else 0
            load_score = base_score - (grid_load_percentage - prev_threshold) * factor
            break
    else: # Executed if grid_load_percentage >= last threshold
        last_threshold = load_tiers[-1][0] if load_tiers else 85
        load_score = max(max_load_penalty, default_load_base_penalty - (grid_load_percentage - last_threshold) * default_load_factor)

    # 2. Renewable score
    renewable_score = params.get('renewable_score_multiplier', 0.8) * renewable_ratio

    # 3. Time score
    time_scores = params.get('time_scores', {"peak": -0.3, "valley": 0.6, "shoulder": 0.2})
    if hour in peak_hours: time_score = time_scores.get('peak', -0.3)
    elif hour in valley_hours: time_score = time_scores.get('valley', 0.6)
    else: time_score = time_scores.get('shoulder', 0.2)

    # 4. Power penalty
    power_penalty = 0
    power_penalty_thresholds = params.get('power_penalty_thresholds', [150, 50])
    power_penalties = params.get('power_penalties', [0.1, 0.05])
    if charger_max_power > power_penalty_thresholds[0]: power_penalty = power_penalties[0]
    elif charger_max_power > power_penalty_thresholds[1]: power_penalty = power_penalties[1]

    raw_score = load_score + renewable_score + time_score - power_penalty

    # Adjustments and clamping
    if raw_score < 0: raw_score *= params.get('negative_score_adjustment_factor', 0.8)
    else: raw_score = min(1.0, raw_score * params.get('positive_score_adjustment_factor', 1.1))

    final_score = max(params.get('final_score_min_clamp', -0.9), min(params.get('final_score_max_clamp', 1.0), raw_score))
    return final_score