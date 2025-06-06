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
    scheduler_config = config.get('scheduler', {})
    env_config = config.get('environment', {})

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
    peak_hours = grid_status.get("peak_hours", [7, 8, 9, 10, 18, 19, 20, 21])
    valley_hours = grid_status.get("valley_hours", [0, 1, 2, 3, 4, 5])
    max_queue_config = env_config.get("rule_based_max_queue", {}) # 可配置队列长度
    if current_hour in peak_hours: max_queue_len = max_queue_config.get("peak", 3)
    elif current_hour in valley_hours: max_queue_len = max_queue_config.get("valley", 12)
    else: max_queue_len = max_queue_config.get("shoulder", 6)

    # 动态权重
    base_weights = scheduler_config.get("optimization_weights", {
        "user_satisfaction": 0.33, "operator_profit": 0.33, "grid_friendliness": 0.34
    })
    weights = base_weights.copy()
    # 权重调整逻辑
    if current_hour in peak_hours:
        grid_boost = min(0.3, grid_load_percentage / 200)
        weights["grid_friendliness"] = min(0.7, weights["grid_friendliness"] + grid_boost)
        weights["user_satisfaction"] = max(0.1, weights["user_satisfaction"] - grid_boost / 2)
        weights["operator_profit"] = max(0.1, weights["operator_profit"] - grid_boost / 2)
    elif current_hour in valley_hours:
         weights["grid_friendliness"] = max(0.2, weights["grid_friendliness"] - 0.15)
         weights["operator_profit"] = min(0.6, weights["operator_profit"] + 0.1)
         weights["user_satisfaction"] = min(0.6, weights["user_satisfaction"] + 0.05)
    # 归一化
    total_w = sum(weights.values())
    if total_w > 0:
        for key in weights: weights[key] /= total_w
    # logger.info(f"RuleBased weights: User={weights['user_satisfaction']:.2f}, Profit={weights['operator_profit']:.2f}, Grid={weights['grid_friendliness']:.2f}")

    # 创建候选用户列表
    candidate_users = []
    min_charge_needed = env_config.get("min_charge_threshold_percent", 20.0) # 至少需要充这么多电才调度
    default_threshold = env_config.get("default_charge_soc_threshold", 40.0) # 默认触发调度的SOC阈值

    for user in users:
        user_id = user.get("user_id")
        status = user.get("status", "")
        soc = user.get("soc", 100)
        if not user_id or status in ["charging", "waiting"] or not isinstance(soc, (int, float)):
            continue

        # 计算阈值 (更细化的逻辑)
        threshold = default_threshold
        user_profile = user.get("user_profile", "normal")
        if user_profile == "anxious": threshold += 10
        elif user_profile == "economic": threshold -= 10
        if current_hour in peak_hours: threshold -= 5
        elif current_hour in valley_hours: threshold += 10
        threshold = max(15, min(60, threshold)) # 限制阈值范围

        needs_charge_flag = user.get("needs_charge_decision", False)
        charge_needed_percent = 95 - soc # 目标充到95%

        # 条件：明确需要 或 (SOC低于阈值且低于某个上限) 并且 需要充电量足够
        if (needs_charge_flag or (soc <= threshold and soc < 80)) and charge_needed_percent >= min_charge_needed:
            urgency = (threshold - soc) / threshold if soc < threshold else 0
            urgency = min(1.0, max(0.0, urgency + (0.3 if needs_charge_flag else 0)))
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
        nearby_chargers_to_consider = available_chargers_with_dist[:env_config.get("rule_based_candidate_limit", 15)]

        for charger_id, charger, distance in nearby_chargers_to_consider:
            # 调用评分函数
            current_queue_len = charger_loads.get(charger_id, 0) # 当前实际负载
            user_score = _calculate_user_satisfaction_score(user, charger, distance, current_queue_len)
            profit_score = _calculate_operator_profit_score(user, charger, state)
            grid_score = _calculate_grid_friendliness_score(charger, state)

            # 动态权重调整
            adjusted_weights = weights.copy()
            if grid_score < -0.5: adjusted_weights["grid_friendliness"] = min(0.8, adjusted_weights["grid_friendliness"] * 1.5)
            if urgency > 0.9 and soc < 15: adjusted_weights["user_satisfaction"] = min(0.6, adjusted_weights["user_satisfaction"] * 1.5)
            # 归一化 adjusted_weights
            total_adj_w = sum(adjusted_weights.values())
            if total_adj_w > 0:
                 for key in adjusted_weights: adjusted_weights[key] /= total_adj_w

            # 组合分数
            combined_score = (user_score * adjusted_weights["user_satisfaction"] +
                              profit_score * adjusted_weights["operator_profit"] +
                              grid_score * adjusted_weights["grid_friendliness"])

            # 队列惩罚
            queue_penalty_factor = env_config.get("rule_based_queue_penalty", 0.05)
            penalized_score = combined_score - (current_queue_len * queue_penalty_factor)

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


# --- 评分辅助函数 ---
def _calculate_user_satisfaction_score(user, charger, distance, current_queue_len):
    """计算用户满意度评分 [-1, 1] (使用原 Environment 的详细逻辑)"""
    # (复制粘贴原 _calculate_user_satisfaction 的完整逻辑)
    # 1. 距离因素
    if distance < 2: distance_score = 0.5 - distance * 0.1
    elif distance < 5: distance_score = 0.3 - (distance - 2) * 0.1
    elif distance < 10: distance_score = 0 - (distance - 5) * 0.05
    else: distance_score = max(-0.5, -0.25 - (distance - 10) * 0.025)

    # 2. 等待时间因素 (基于当前队列长度)
    if current_queue_len == 0: wait_score = 0.5
    elif current_queue_len <= 2: wait_score = 0.3
    elif current_queue_len <= 5: wait_score = 0.1
    elif current_queue_len <= 8: wait_score = -0.1
    else: wait_score = -0.3

    # 3. 充电速度匹配因素
    charger_power = charger.get("max_power", 50)
    user_type = user.get("user_type", "private")
    user_soc = user.get("soc", 50)
    urgency = max(0, (40 - user_soc) / 40) if user_soc < 40 else 0
    expected_power = 20 + urgency * 30 # Default for private
    if user_type in ["taxi", "ride_hailing"]: expected_power = 50 + urgency * 50
    elif user_type == "logistics": expected_power = 30 + urgency * 50
    power_ratio = charger_power / expected_power if expected_power > 0 else 1
    if power_ratio >= 1.5: power_score = 0.4
    elif power_ratio >= 1: power_score = 0.3
    elif power_ratio >= 0.7: power_score = 0.1
    elif power_ratio >= 0.5: power_score = -0.1
    else: power_score = -0.2

    # 4. 价格因素 (简化，可从 state 获取更准确价格)
    price_multiplier = charger.get("price_multiplier", 1.0)
    price_score = max(-0.3, min(0.3, (1.0 - price_multiplier) * 0.5)) # 假设乘数越低越好

    # 5. 紧急情况调整
    emergency_factor = 1.0
    if user_soc < 15: emergency_factor = 1.5
    elif user_soc < 25: emergency_factor = 1.2

    # 综合评分
    satisfaction = (
        distance_score * 0.4 * emergency_factor +
        wait_score * 0.3 * emergency_factor +
        power_score * 0.15 +
        price_score * 0.15
    )
    # 限制和调整
    if emergency_factor > 1.2 and satisfaction < -0.5:
        satisfaction = max(-0.5, satisfaction * 0.8)
    score = max(-1.0, min(1.0, satisfaction))
    # logger.debug(f"User Sat Score for {user.get('user_id')} @ {charger.get('charger_id')}: Dist={distance_score:.2f}, Wait={wait_score:.2f}, Power={power_score:.2f}, Price={price_score:.2f} -> Final={score:.2f}")
    return score


def _calculate_operator_profit_score(user, charger, state):
    """计算运营商利润评分 [-1, 1] (使用原 Environment 的详细逻辑)"""
    # (复制粘贴原 _calculate_operator_profit 的完整逻辑)
    grid_status = state.get("grid_status", {})
    hour = datetime.fromisoformat(state.get('timestamp', '')).hour if state.get('timestamp') else datetime.now().hour
    peak_hours = grid_status.get("peak_hours", [])
    valley_hours = grid_status.get("valley_hours", [])
    current_price = grid_status.get("current_price", 0.85) # 使用当前电价作为基础

    user_soc = user.get("soc", 50)
    charge_needed_factor = (100 - user_soc) / 50.0 # 0-2 scale approx

    charger_type = charger.get("type", "normal")
    charger_price_multiplier = charger.get("price_multiplier", 1.0)
    is_occupied = charger.get("status") == "occupied"
    queue_length = len(charger.get("queue", []))

    # 评分基于有效价格、快充、队列和需求量
    effective_price = current_price * charger_price_multiplier
    score = effective_price # Base score on price

    # 快充加分
    if charger_type == "fast": score *= 1.15
    elif charger_type == "superfast": score *= 1.30

    # 队列惩罚
    penalty_per_queue = 0.15 # 调整惩罚力度
    score -= queue_length * penalty_per_queue

    # 需求量加分
    score *= (1 + charge_needed_factor * 0.05) # 较小影响

    # 映射到 [-1, 1] - 可以使用简单的线性映射或 Sigmoid
    # 简单线性映射示例: 假设分数范围在 0.5 到 2.0 之间比较常见
    normalized_score = (score - 0.5) / (2.0 - 0.5) # Map to ~[0, 1]
    final_score = 2 * normalized_score - 1 # Map to [-1, 1]
    final_score = max(-1.0, min(1.0, final_score)) # Clamp

    # logger.debug(f"Operator Profit Score for {user.get('user_id')} @ {charger.get('charger_id')}: EffectivePrice={effective_price:.2f}, Type={charger_type}, Queue={queue_length} -> Raw={score:.2f} -> Final={final_score:.2f}")
    return final_score


def _calculate_grid_friendliness_score(charger, state):
    """计算电网友好度评分 [-1, 1] (使用原 Environment 的详细逻辑)"""
    # (复制粘贴原 _calculate_grid_friendliness 的完整逻辑)
    grid_status = state.get("grid_status", {})
    hour = datetime.fromisoformat(state.get('timestamp', '')).hour if state.get('timestamp') else datetime.now().hour
    grid_load_percentage = grid_status.get("grid_load_percentage", 50)
    renewable_ratio = grid_status.get("renewable_ratio", 0) / 100.0 if grid_status.get("renewable_ratio") is not None else 0.0
    peak_hours = grid_status.get("peak_hours", [])
    valley_hours = grid_status.get("valley_hours", [])
    charger_max_power = charger.get("max_power", 50)

    # 1. 负载评分
    if grid_load_percentage < 30: load_score = 0.8
    elif grid_load_percentage < 50: load_score = 0.5 - (grid_load_percentage - 30) * 0.015
    elif grid_load_percentage < 70: load_score = 0.2 - (grid_load_percentage - 50) * 0.01
    elif grid_load_percentage < 85: load_score = 0.0 - (grid_load_percentage - 70) * 0.015
    else: load_score = max(-0.5, -0.225 - (grid_load_percentage - 85) * 0.01)

    # 2. 可再生能源
    renewable_score = 0.8 * renewable_ratio

    # 3. 时间
    time_score = 0
    if hour in peak_hours: time_score = -0.3
    elif hour in valley_hours: time_score = 0.6
    else: time_score = 0.2

    # 4. 功率惩罚 (可选)
    power_penalty = 0
    if charger_max_power > 150: power_penalty = 0.1
    elif charger_max_power > 50: power_penalty = 0.05

    # 组合
    grid_friendliness_raw = load_score + renewable_score + time_score - power_penalty
    # 调整
    grid_friendliness = max(-0.9, min(1.0, grid_friendliness_raw))
    if grid_friendliness < 0: grid_friendliness *= 0.8
    else: grid_friendliness = min(1.0, grid_friendliness * 1.1)

    # logger.debug(f"Grid Friendliness Score for {charger.get('charger_id')}: Load%={grid_load_percentage:.1f}({load_score:.2f}), Renew%={renewable_ratio*100:.1f}({renewable_score:.2f}), Time={hour}({time_score:.2f}) -> Final={grid_friendliness:.2f}")
    return grid_friendliness