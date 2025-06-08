# ev_charging_project/algorithms/uncoordinated.py
import logging
import math
import random
from collections import defaultdict
try:
    from simulation.utils import calculate_distance # 注意导入路径
except ImportError:
    logging.error("Could not import calculate_distance from simulation.utils in uncoordinated.py")
    def calculate_distance(p1, p2): return 10.0 # Fallback

logger = logging.getLogger(__name__)

def schedule(state, config, manual_decisions=None, grid_preferences=None): # Added config
    """
    无序充电算法实现 (先到先得，或基于简单距离/队列)。

    Args:
        state (dict): 当前环境状态

    Returns:
        dict: 调度决策 {user_id: charger_id}
    """
    decisions = {}
    
    algo_config = config.get('algorithms', {})
    uncoordinated_config = algo_config.get('uncoordinated', {})
    score_weights = uncoordinated_config.get('score_weights', {"distance": 0.7, "queue_penalty_km": 5.0})
    low_soc_threshold_for_distance_only = uncoordinated_config.get('low_soc_behavior_threshold', 20)
    soc_trigger_threshold = uncoordinated_config.get('soc_threshold', 50)
    max_queue_allowed = uncoordinated_config.get('max_queue', 4)

    users = state.get("users", [])
    chargers = state.get("chargers", [])
    if not users or not chargers:
        logger.warning("Uncoordinated: No users or chargers in state.")
        return decisions

    # 筛选需要充电决策的用户
    candidate_users = []
    for u in users:
        needs_charge_flag = u.get("needs_charge_decision", False)
        soc = u.get("soc", 100)
        status = u.get("status", "idle")
        if status not in ["charging", "waiting"] and (needs_charge_flag or soc < soc_trigger_threshold):
             if u.get("current_position"): # Ensure position data exists
                 candidate_users.append(u)

    if not candidate_users:
        # logger.debug("Uncoordinated: No users actively seeking charge.")
        return decisions

    random.shuffle(candidate_users) # 模拟随机决策顺序

    # 获取充电桩状态和队列信息
    charger_dict = {c["charger_id"]: c for c in chargers if isinstance(c,dict) and c.get("charger_id") and c.get("status") != "failure"}
    if not charger_dict:
        logger.warning("Uncoordinated: No operational chargers found.")
        return decisions

    # 记录本轮已分配给充电桩的用户数，模拟用户看到的情况
    current_assignments = defaultdict(int)

    assigned_users_this_step = set() # 防止重复分配

    for user in candidate_users:
        user_id = user.get("user_id")
        if not user_id or user_id in assigned_users_this_step: continue

        user_pos = user.get("current_position", {})
        soc = user.get("soc", 100)
        
        # The user's own model has determined they need a charge.
        needs_charge_flag = user.get("needs_charge_decision", False) 

        possible_targets = []
        for cid, charger in charger_dict.items():
            # 计算当前总排队人数（真实队列+本轮已分配）
            current_queue_len = len(charger.get("queue", []))
            if charger.get("status") == "occupied": current_queue_len += 1
            total_waiting = current_queue_len + current_assignments.get(cid, 0)

            if total_waiting < max_queue_allowed:
                dist = calculate_distance(user_pos, charger.get("position", {}))
                if dist == float('inf'): continue # 跳过无效距离

                # Uncoordinated user choice strategy:
                # If SOC is very low OR the user has proactively decided they need a charge, prioritize distance.
                # Otherwise, consider both distance and queue.
                eval_score = 0
                # A user who has decided they need a charge should act like they have low SOC: prioritize proximity.
                if soc < low_soc_threshold_for_distance_only or needs_charge_flag:
                    eval_score = dist # Primarily distance
                else:
                    dist_weight = score_weights.get('distance', 0.7)
                    queue_penalty_km_equivalent = score_weights.get('queue_penalty_km', 5.0)
                    eval_score = dist * dist_weight + total_waiting * queue_penalty_km_equivalent

                possible_targets.append((cid, eval_score))

        if not possible_targets:
            # logger.warning(f"Uncoordinated: No suitable chargers found for user {user_id}")
            continue

        # 选择评估分数最低（最优）的充电桩
        possible_targets.sort(key=lambda x: x[1])
        best_charger_id = possible_targets[0][0]

        if best_charger_id:
            decisions[user_id] = best_charger_id
            current_assignments[best_charger_id] += 1 # 更新本轮分配计数
            assigned_users_this_step.add(user_id)
            # logger.debug(f"Uncoordinated assigned user {user_id} to charger {best_charger_id}")

    logger.info(f"Uncoordinated made {len(decisions)} assignments for {len(candidate_users)} candidates.")
    # --- ADD THIS PART ---
    metadata = {
        "candidate_user_count": len(candidate_users)
    }
    return decisions