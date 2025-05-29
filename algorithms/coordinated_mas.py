# ev_charging_project/algorithms/coordinated_mas.py
# (内容来自原 ev_multi_agent_system.py)

from datetime import datetime
import math
import logging
from collections import defaultdict
# 导入重构后的工具函数
from simulation.utils import calculate_distance

# Initialize logger for this module
logger = logging.getLogger("MAS") # 可以保留原名或改为 "CoordMAS"


class MultiAgentSystem:
    def __init__(self):
        self.config = {} # 稍后由 app.py 或 scheduler.py 填充
        self.user_agent = CoordinatedUserSatisfactionAgent()
        self.profit_agent = CoordinatedOperatorProfitAgent()
        self.grid_agent = CoordinatedGridFriendlinessAgent()
        self.coordinator = CoordinatedCoordinator()

    def make_decisions(self, state):
        """
        Coordinate decisions between different agents

        Args:
            state: Current state of the environment

        Returns:
            decisions: Dict mapping user_ids to charger_ids
        """
        # Get decisions from each agent
        user_decisions = self.user_agent.make_decision(state)
        profit_decisions = self.profit_agent.make_decisions(state)
        grid_decisions = self.grid_agent.make_decisions(state)

        # Store decisions for analysis and visualization
        self.user_agent.last_decision = user_decisions
        self.profit_agent.last_decision = profit_decisions
        self.grid_agent.last_decision = grid_decisions

        # Resolve conflicts and make final decisions
        # 将 config 中的权重传递给协调器
        coordinator_weights = self.config.get('scheduler', {}).get('optimization_weights', {})
        if coordinator_weights:
             self.coordinator.set_weights(coordinator_weights)

        final_decisions = self.coordinator.resolve_conflicts(
            user_decisions, profit_decisions, grid_decisions, state
        )

        return final_decisions


class CoordinatedUserSatisfactionAgent:
    def __init__(self):
        self.last_decision = {}
        self.last_reward = 0

    def make_decision(self, state):
        """Make charging recommendations based on user satisfaction"""
        recommendations = {}

        # Use .get() for safe access
        users = state.get("users", [])
        chargers = state.get("chargers", [])
        timestamp_str = state.get("timestamp")

        if not users or not chargers or not timestamp_str:
            logger.warning("UserAgent: Missing users, chargers, or timestamp in state.")
            return recommendations

        try:
            timestamp = datetime.fromisoformat(timestamp_str)
        except (ValueError, TypeError):
            logger.warning(f"UserAgent: Invalid timestamp format: {timestamp_str}")
            return recommendations

        # Make recommendations for each user who needs charging
        for user in users:
            user_id = user.get("user_id")
            soc = user.get("soc", 100)
            # 检查用户是否明确需要充电或SOC低于阈值
            needs_charge = user.get("needs_charge_decision", False)
            threshold = self._get_charging_threshold(timestamp.hour)

            if not user_id: continue
            # 只考虑状态不是充电/等待，且 (明确需要 或 SOC低于阈值) 的用户
            if user.get("status") not in ["charging", "waiting"] and (needs_charge or soc < threshold):
                 # 并且电量不是太满 (例如，避免只差一点点就推荐)
                 if soc < 90: # 增加一个上限，避免为接近满电的用户推荐
                    best_charger_info = self._find_best_charger_for_user(user, chargers, state)
                    if best_charger_info:
                        recommendations[user_id] = best_charger_info["charger_id"]

        self.last_decision = recommendations
        return recommendations

    def _get_charging_threshold(self, hour):
        # Example: Lower threshold during the day, higher at night
        if 6 <= hour < 22:
            return 35 # 白天充电阈值稍高，鼓励主动充电
        else:
            return 45 # 夜间阈值更高，抓住夜间充电机会

    def _find_best_charger_for_user(self, user, chargers, state):
        best_charger = None
        min_weighted_cost = float('inf')
        user_pos = user.get("current_position", {"lat": 0, "lng": 0})
        # 使用 .get 获取敏感度，并提供默认值
        time_sensitivity = user.get("time_sensitivity", 0.5)
        price_sensitivity = user.get("price_sensitivity", 0.5)
        grid_status = state.get("grid_status", {}) # 获取电网状态以获取价格
        current_price = grid_status.get("current_price", 0.85) # Use safe access

        for charger in chargers:
            # Skip failed chargers
            if charger.get("status") == "failure": continue

            charger_pos = charger.get("position", {"lat": 0, "lng": 0})
            # 使用导入的 calculate_distance
            distance = calculate_distance(user_pos, charger_pos)
            travel_time = distance * 2 # Simple estimate: 2 min/km

            queue_length = len(charger.get("queue", []))
            # 简化等待时间计算：队列长度乘以平均充电时间
            if charger.get("type") == "superfast":
                avg_charge_time = 30  # 超快充30分钟
            elif charger.get("type") == "fast":
                avg_charge_time = 45  # 快充45分钟
            else:
                avg_charge_time = 60  # 普通充电60分钟
            
            wait_time = queue_length * avg_charge_time

            # Estimate charging cost (simplified)
            charge_needed = user.get("battery_capacity", 60) * (1 - user.get("soc", 50)/100)
            # 使用充电桩特定的价格乘数
            price_multiplier = charger.get("price_multiplier", 1.0)
            est_cost = charge_needed * current_price * price_multiplier

            # Weighted cost: lower is better
            time_cost = travel_time + wait_time
            # Scale cost relative to typical max cost (e.g., 50 yuan)
            price_cost = est_cost / 50.0

            # 确保敏感度是有效数字
            if not isinstance(time_sensitivity, (int, float)): time_sensitivity = 0.5
            if not isinstance(price_sensitivity, (int, float)): price_sensitivity = 0.5

            weighted_cost = (time_cost * time_sensitivity) + (price_cost * price_sensitivity)

            if weighted_cost < min_weighted_cost:
                min_weighted_cost = weighted_cost
                best_charger = charger

        return best_charger

class CoordinatedOperatorProfitAgent:
    def __init__(self):
        self.last_decision = {}
        self.last_reward = 0

    def make_decisions(self, state):
        """Make decisions prioritizing operator profit"""
        recommendations = {}

        # Use .get() for safe access
        users = state.get("users", [])
        chargers = state.get("chargers", [])
        timestamp_str = state.get("timestamp")
        grid_status = state.get("grid_status", {}) # Use safe access

        if not users or not chargers or not timestamp_str:
            logger.warning("ProfitAgent: Missing users, chargers, or timestamp in state.")
            return recommendations

        try:
            timestamp = datetime.fromisoformat(timestamp_str)
            hour = timestamp.hour
        except (ValueError, TypeError):
            logger.warning(f"ProfitAgent: Invalid timestamp format: {timestamp_str}")
            return recommendations

        # 从 grid_status 获取峰谷信息和基础价格
        peak_hours = grid_status.get("peak_hours", [7, 8, 9, 10, 18, 19, 20, 21])
        valley_hours = grid_status.get("valley_hours", [0, 1, 2, 3, 4, 5])
        base_price = grid_status.get("current_price", 0.85) # Use current grid price

        # Make profit-oriented recommendations
        for user in users:
            user_id = user.get("user_id")
            soc = user.get("soc", 100)
            if not user_id or user.get("status") in ["charging", "waiting"]:
                continue # Skip users already charging/waiting or without ID

            # 考虑所有未充电/等待的用户，利润优先不只看低电量
            # 但可以稍微优先电量低一点的用户 (需要充电量大)
            if soc < 95: # 只要不是满电都考虑
                best_charger_info = self._find_most_profitable_charger(user, chargers, base_price, peak_hours, valley_hours, hour)
                if best_charger_info:
                    recommendations[user_id] = best_charger_info["charger_id"]

        self.last_decision = recommendations
        return recommendations

    def _find_most_profitable_charger(self, user, chargers, base_price, peak_hours, valley_hours, hour):
        best_charger = None
        max_profit_score = float('-inf')

        for charger in chargers:
            if charger.get("status") == "failure": continue

            # 使用充电桩自身的价格乘数
            charger_price_multiplier = charger.get("price_multiplier", 1.0)

            # 根据时间调整基础价格
            price_at_charger_time = base_price # 默认使用当前电价
            if hour in peak_hours:
                 # 如果已经是峰时电价，不再乘，否则用峰时电价
                 price_at_charger_time = max(base_price, self.config.get('grid',{}).get('peak_price', 1.2))
            elif hour in valley_hours:
                 # 如果已经是谷时电价，不再乘，否则用谷时电价
                 price_at_charger_time = min(base_price, self.config.get('grid',{}).get('valley_price', 0.4))

            # 最终充电价格 = 时段价格 * 充电桩乘数
            effective_charge_price = price_at_charger_time * charger_price_multiplier

            # 利润潜力评分：价格越高越好，快充更好，队列越短越好
            profit_potential = effective_charge_price # Base score is the price
            if charger.get("type") == "fast": # Bonus for fast chargers
                profit_potential *= 1.15
            elif charger.get("type") == "superfast": # Even bigger bonus
                 profit_potential *= 1.3

            # Penalty for queue length
            queue_length = len(charger.get("queue", []))
            profit_potential /= (1 + queue_length * 0.25) # Stronger penalty for queue

            # Bonus for users needing more charge
            charge_needed_factor = (100 - user.get("soc", 50)) / 50.0 # Normalize needed charge (0-2 approx)
            profit_potential *= (1 + charge_needed_factor * 0.1) # Small bonus for higher need

            if profit_potential > max_profit_score:
                max_profit_score = profit_potential
                best_charger = charger

        return best_charger


class CoordinatedGridFriendlinessAgent:
    def __init__(self):
        self.last_decision = {}
        self.last_reward = 0

    def make_decisions(self, state):
        """Make decisions prioritizing grid friendliness"""
        decisions = {}
        users_list = state.get("users", [])
        chargers_list = state.get("chargers", [])
        timestamp_str = state.get("timestamp")
        grid_status = state.get("grid_status", {}) # Use safe access

        if not users_list or not chargers_list or not timestamp_str:
            logger.warning("GridAgent: Missing users, chargers, or timestamp in state.")
            return decisions

        try:
            timestamp = datetime.fromisoformat(timestamp_str)
            hour = timestamp.hour
        except (ValueError, TypeError):
            logger.warning(f"GridAgent: Invalid timestamp format: {timestamp_str}")
            return decisions

        # 使用列表推导式，更安全
        users = {user["user_id"]: user for user in users_list if isinstance(user, dict) and "user_id" in user}
        chargers = {charger["charger_id"]: charger for charger in chargers_list if isinstance(charger, dict) and "charger_id" in charger}


        # 从 grid_status 获取电网信息
        grid_load_percentage = grid_status.get("grid_load_percentage", 50) # 使用百分比
        renewable_ratio = grid_status.get("renewable_ratio", 0) # 已经是百分比
        peak_hours = grid_status.get("peak_hours", [7, 8, 9, 10, 18, 19, 20, 21])
        valley_hours = grid_status.get("valley_hours", [0, 1, 2, 3, 4, 5])

        # 识别需要充电的用户
        charging_candidates = []
        for user_id, user in users.items():
            soc = user.get("soc", 100)
            # 考虑状态不是充电/等待，且需要充电标志为True或SOC低于50%的用户
            needs_charge = user.get("needs_charge_decision", False)
            if user.get("status") not in ["charging", "waiting"] and (needs_charge or soc < 50):
                 # 确保需要充电量足够大
                 if 95 - soc >= 20: # 至少需要充20%
                    urgency = (100 - soc) # 简单紧迫度：需要充的电量越多越紧急
                    charging_candidates.append((user_id, user, urgency))

        # 按紧迫度排序，最紧急的优先
        charging_candidates.sort(key=lambda x: -x[2])

        # 对每个充电桩进行评分
        charger_scores = {}
        max_queue_len = 4 # 电网优先时允许的稍长队列
        for charger_id, charger in chargers.items():
            if charger.get("status") != "failure":
                current_queue_len = len(charger.get("queue", []))
                if charger.get("status") == "occupied": current_queue_len += 1

                if current_queue_len < max_queue_len:
                    # 时间分数：低谷>平峰>高峰
                    time_score = 0
                    if hour in valley_hours: time_score = 1.0
                    elif hour not in peak_hours: time_score = 0.5

                    # 可再生能源分数
                    renewable_score = renewable_ratio / 100.0 # 0-1

                    # 负载分数：负载越低越好
                    load_score = max(0, 1 - (grid_load_percentage / 100.0)) # 0-1

                    # 组合评分 (调整权重，优先时间，其次负载，再可再生)
                    grid_score = time_score * 0.5 + load_score * 0.3 + renewable_score * 0.2
                    charger_scores[charger_id] = grid_score

        # 按电网友好度分数排序可用充电桩
        available_chargers = sorted(charger_scores.items(), key=lambda item: -item[1])
        assigned_chargers = defaultdict(int) # 跟踪本轮已分配计数

        # 为候选用户分配最友好的充电桩
        for user_id, user, urgency in charging_candidates:
            if not available_chargers: break # 没有可用充电桩了

            best_choice_idx = -1
            best_charger_id = None
            for i, (charger_id, score) in enumerate(available_chargers):
                # 检查加上本轮分配后是否超载
                charger_info = chargers.get(charger_id, {})
                current_actual_queue = len(charger_info.get("queue", []))
                if charger_info.get("status") == "occupied": current_actual_queue += 1

                if current_actual_queue + assigned_chargers[charger_id] < max_queue_len:
                    best_choice_idx = i
                    best_charger_id = charger_id
                    break # 找到了

            if best_choice_idx != -1 and best_charger_id is not None:
                decisions[user_id] = best_charger_id
                assigned_chargers[best_charger_id] += 1
                # 如果这个充电桩在本轮分配后达到最大容量，则从可用列表中移除
                charger_info = chargers.get(best_charger_id, {})
                current_actual_queue = len(charger_info.get("queue", []))
                if charger_info.get("status") == "occupied": current_actual_queue += 1
                if current_actual_queue + assigned_chargers[best_charger_id] >= max_queue_len:
                     available_chargers.pop(best_choice_idx)
            # else:
                # logger.debug(f"GridAgent: No suitable grid-friendly charger found for user {user_id}")


        self.last_decision = decisions
        return decisions


class CoordinatedCoordinator:
    def __init__(self):
        # 默认权重，会被 set_weights 覆盖
        self.weights = {"user": 0.4, "profit": 0.3, "grid": 0.3}
        self.conflict_history = []
        self.last_agent_rewards = {}

    def set_weights(self, weights):
        """Set agent weights from config"""
        self.weights = {
            "user": weights.get("user_satisfaction", 0.4),
            "profit": weights.get("operator_profit", 0.3),
            "grid": weights.get("grid_friendliness", 0.3)
        }
        # 确保权重和为1
        total_w = sum(self.weights.values())
        if total_w > 0 and abs(total_w - 1.0) > 1e-6:
             logger.warning(f"Coordinator weights do not sum to 1 ({total_w}). Normalizing.")
             for k in self.weights: self.weights[k] /= total_w
        logger.info(f"Coordinator weights updated: User={self.weights['user']:.2f}, Profit={self.weights['profit']:.2f}, Grid={self.weights['grid']:.2f}")

    def resolve_conflicts(self, user_decisions, profit_decisions, grid_decisions, state):
        """Resolve conflicts between agent decisions using weighted voting and capacity checks."""
        final_decisions = {}
        conflict_count = 0
        all_users = set(user_decisions.keys()) | set(profit_decisions.keys()) | set(grid_decisions.keys())

        chargers_list = state.get('chargers', [])
        if not chargers_list:
             logger.error("Coordinator: No chargers found in state.")
             return {}

        chargers_state = {c['charger_id']: c for c in chargers_list if 'charger_id' in c}
        # 初始化分配计数，考虑当前实际排队和占用情况
        assigned_count = defaultdict(int)
        max_queue_len_config = 4 # 协调器使用的队列长度限制，可以配置
        for cid, charger in chargers_state.items():
            if charger.get('status') == 'occupied':
                assigned_count[cid] += 1
            assigned_count[cid] += len(charger.get('queue', []))

        # 按某种顺序处理用户（例如，可以基于用户紧迫度或随机）
        # 这里简化为按 ID 排序
        user_list = sorted(list(all_users))

        for user_id in user_list:
            choices = []
            # 获取各 agent 的推荐和对应的权重
            if user_id in user_decisions:
                choices.append((user_decisions[user_id], self.weights.get("user", 0)))
            if user_id in profit_decisions:
                choices.append((profit_decisions[user_id], self.weights.get("profit", 0)))
            if user_id in grid_decisions:
                choices.append((grid_decisions[user_id], self.weights.get("grid", 0)))

            if not choices: continue # 该用户没有收到任何推荐

            # 检查冲突
            unique_choices = {cid for cid, w in choices}
            if len(unique_choices) > 1: conflict_count += 1

            # 加权投票
            charger_votes = defaultdict(float)
            for charger_id, weight in choices:
                # 确保 charger_id 存在于 chargers_state 中
                if charger_id in chargers_state:
                    charger_votes[charger_id] += weight
                else:
                     logger.warning(f"Coordinator: Recommended charger {charger_id} for user {user_id} not found in current state. Ignoring vote.")


            if not charger_votes: # 如果所有推荐的充电桩都不存在
                 logger.warning(f"Coordinator: No valid recommended chargers found for user {user_id}.")
                 continue

            # 按票数排序
            sorted_chargers = sorted(charger_votes.items(), key=lambda item: -item[1])

            # 分配给票数最高且未满的充电桩
            assigned = False
            for best_charger_id, vote_score in sorted_chargers:
                # 检查容量，使用配置的 max_queue_len_config
                if assigned_count.get(best_charger_id, 0) < max_queue_len_config:
                    # 确保充电桩不是故障状态
                    if chargers_state.get(best_charger_id, {}).get('status') != 'failure':
                        final_decisions[user_id] = best_charger_id
                        assigned_count[best_charger_id] += 1 # 更新本轮分配计数
                        assigned = True
                        logger.debug(f"Coordinator assigned user {user_id} to charger {best_charger_id} (Votes: {vote_score:.2f}, Queue now: {assigned_count[best_charger_id]})")
                        break # 用户已分配
                    else:
                         logger.debug(f"Coordinator: Charger {best_charger_id} (top vote for user {user_id}) is in failure state. Trying next.")
                # else:
                    # logger.debug(f"Coordinator: Charger {best_charger_id} (top vote for user {user_id}) is full (Current count: {assigned_count.get(best_charger_id, 0)}). Trying next.")


            # if not assigned:
                # logger.warning(f"Coordinator: Could not assign user {user_id}, all preferred chargers were full or invalid.")

        self.conflict_history.append(conflict_count)
        logger.info(f"Coordinator resolved decisions: {len(final_decisions)} assignments made, {conflict_count} conflicts encountered.")
        return final_decisions