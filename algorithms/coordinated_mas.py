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
        self.operational_mode = 'v1g' # Default operational mode

    def set_operational_mode(self, mode):
        if mode in ['v1g', 'v2g']:
            self.operational_mode = mode
            logger.info(f"MAS operational mode set to: {self.operational_mode}")
            if hasattr(self.grid_agent, 'set_operational_mode'):
                self.grid_agent.set_operational_mode(mode)
            # Potentially inform other agents if their behavior should change
            # if hasattr(self.profit_agent, 'set_operational_mode'):
            #     self.profit_agent.set_operational_mode(mode)
        else:
            logger.warning(f"MAS: Unknown operational mode: {mode}")

    def make_decisions(self, state, manual_decisions=None, grid_preferences=None):
        """
        Coordinate decisions between different agents

        Args:
            state: Current state of the environment

        Returns:
            decisions: Dict mapping user_ids to charger_ids
        """
        # Get decisions from each agent
        # Pass grid_preferences to agents that might use it (e.g., for requested_v2g_discharge_mw)
        user_decisions = self.user_agent.make_decision(state) # User agent might not need grid_preferences directly
        profit_decisions = self.profit_agent.make_decisions(state, grid_preferences)
        grid_decisions = self.grid_agent.make_decisions(state, grid_preferences)

        # Store decisions for analysis and visualization
        self.user_agent.last_decision = user_decisions
        self.profit_agent.last_decision = profit_decisions
        self.grid_agent.last_decision = grid_decisions

        # Resolve conflicts and make final decisions
        # Extract charging_priority from grid_preferences (passed from scheduler)
        charging_priority = "balanced" # Default
        if grid_preferences and isinstance(grid_preferences, dict):
            charging_priority = grid_preferences.get("charging_priority", "balanced")

        # Pass charging_priority to the coordinator
        # The coordinator will use its base weights (from config) and adjust them based on priority.
        # No need to call self.coordinator.set_weights here anymore if resolve_conflicts handles dynamic weights.

        final_decisions = self.coordinator.resolve_conflicts(
            user_decisions, profit_decisions, grid_decisions, state, charging_priority
        )

        return final_decisions


class CoordinatedUserSatisfactionAgent:
    def __init__(self):
        self.last_decision = {}
        self.last_reward = 0

    def make_decision(self, state, grid_preferences=None): # Added grid_preferences
        """Make charging recommendations based on user satisfaction"""
        if grid_preferences is None: grid_preferences = {}
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
        time_sensitivity_base = user.get("time_sensitivity", 0.5)
        price_sensitivity_base = user.get("price_sensitivity", 0.5)
        charging_priority = grid_preferences.get("charging_priority", "balanced")

        effective_price_sensitivity = price_sensitivity_base
        if charging_priority == "minimize_cost":
            effective_price_sensitivity *= 1.5 # Users become more price sensitive under this priority
            logger.debug(f"UserAgent: User {user.get('user_id')} applying 'Minimize Cost' logic, effective price sensitivity: {effective_price_sensitivity:.2f}")

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
            if not isinstance(time_sensitivity_base, (int, float)): time_sensitivity_base = 0.5
            if not isinstance(effective_price_sensitivity, (int, float)): effective_price_sensitivity = 0.5 # Corrected variable name

            weighted_cost = (time_cost * time_sensitivity_base) + (price_cost * effective_price_sensitivity) # Use effective_price_sensitivity

            if weighted_cost < min_weighted_cost:
                min_weighted_cost = weighted_cost
                best_charger = charger

        return best_charger

class CoordinatedOperatorProfitAgent:
    def __init__(self):
        self.last_decision = {}
        self.last_reward = 0

    def make_decisions(self, state, grid_preferences=None): # Added grid_preferences
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
        peak_hours = grid_status.get("peak_hours", [])
        valley_hours = grid_status.get("valley_hours", [])
        current_grid_price = grid_status.get("current_price", 0.85) # This is the current TOU price from grid_status

        charging_priority = grid_preferences.get("charging_priority", "balanced")
        operator_cost_of_energy_multiplier = 1.0 # Represents how operator's cost relates to TOU price

        if charging_priority == "minimize_cost":
            # If operator wants to minimize cost, their perceived cost of energy is higher at peak, lower at valley
            if hour in peak_hours:
                operator_cost_of_energy_multiplier = 1.2 # Higher cost burden for operator during peak
            elif hour in valley_hours:
                operator_cost_of_energy_multiplier = 0.7 # Lower cost burden for operator during valley
            logger.debug(f"ProfitAgent: Applying 'Minimize Cost' logic, operator energy cost multiplier: {operator_cost_of_energy_multiplier}")

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

            # 最终充电价格 (price user pays) is current_grid_price * charger_price_multiplier
            # This part was trying to re-evaluate TOU price which is already in current_grid_price.
            effective_charge_price_to_user = current_grid_price * charger_price_multiplier

            # 利润潜力评分：
            # Simplified profit: (revenue_from_user - cost_of_energy_for_operator)
            # Revenue part:
            revenue_potential = effective_charge_price_to_user
            if charger.get("type") == "fast": revenue_potential *= 1.1 # Adjusted bonus
            elif charger.get("type") == "superfast": revenue_potential *= 1.2 # Adjusted bonus

            # Cost part for operator (simplified)
            # Operator's cost of energy is related to the current_grid_price but affected by their own strategy/costs
            # and the charging_priority ("minimize_cost" makes operator more sensitive to TOU via operator_cost_of_energy_multiplier)
            # Assume operator's base cost is a fraction of the current TOU price, then modified by multiplier.
            operator_base_energy_cost = current_grid_price * 0.6 # e.g., operator's cost is 60% of sale price
            estimated_energy_cost_for_operator = operator_base_energy_cost * operator_cost_of_energy_multiplier

            # Profit score considers revenue minus cost, then other factors
            profit_margin_score = revenue_potential - estimated_energy_cost_for_operator

            # Adjust score based on queue and demand
            queue_length = len(charger.get("queue", []))
            profit_score = profit_margin_score / (1 + queue_length * 0.3) # Queue penalty

            charge_needed_factor = (100 - user.get("soc", 50)) / 50.0
            profit_score *= (1 + charge_needed_factor * 0.1)

            if profit_score > max_profit_score:
                max_profit_score = profit_score
                best_charger = charger

        return best_charger


class CoordinatedGridFriendlinessAgent:
    def __init__(self):
        self.last_decision = {}
        self.last_reward = 0
        self.operational_mode = 'v1g' # Default for the agent

    def set_operational_mode(self, mode):
        if mode in ['v1g', 'v2g']:
            self.operational_mode = mode
            logger.info(f"CoordinatedGridFriendlinessAgent operational mode set to: {self.operational_mode}")
        else:
            logger.warning(f"CoordinatedGridFriendlinessAgent: Unknown operational mode: {mode}")

    def make_decisions(self, state, grid_preferences=None): # Added grid_preferences
        """Make decisions prioritizing grid friendliness, considering operational_mode and V2G requests."""
        if grid_preferences is None: grid_preferences = {}
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

        # --- V2G Awareness ---
        requested_v2g_mw = grid_preferences.get("v2g_discharge_active_request_mw", 0.0)
        actual_v2g_mw_this_step = state.get('grid_status', {}).get('aggregated_metrics', {}).get('current_actual_v2g_dispatch_mw', 0.0)
        is_v2g_active_or_requested = self.operational_mode == 'v2g' and (requested_v2g_mw > 0 or actual_v2g_mw_this_step > 0)
        if is_v2g_active_or_requested:
            logger.info(f"GridAgent: V2G is active or requested (request: {requested_v2g_mw} MW, actual: {actual_v2g_mw_this_step} MW). Adjusting charging decisions.")
        # --- End V2G Awareness ---

        charging_priority = grid_preferences.get("charging_priority", "balanced")

        # 对每个充电桩进行评分
        charger_scores = {}
        # Adjust queue length tolerance based on operational mode
        if self.operational_mode == 'v2g':
            max_queue_len = 5
            if is_v2g_active_or_requested:
                max_queue_len = 2
            logger.debug(f"GridAgent (V2G mode, V2G active/req: {is_v2g_active_or_requested}): Max queue length set to {max_queue_len}")
        else: # V1G mode
            max_queue_len = 3
            logger.debug(f"GridAgent (V1G mode): Max queue length set to {max_queue_len}")


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

                    # Default/Balanced weights for components of grid_score
                    time_w, load_w, renewable_w = 0.5, 0.3, 0.2
                    base_peak_penalty_score = -1.0
                    base_valley_bonus_score = 0.8
                    base_normal_time_score = 0.2 # Score for shoulder periods

                    if self.operational_mode == 'v2g':
                        time_w, load_w, renewable_w = 0.4, 0.2, 0.4 # V2G mode base weights

                    # Adjust weights/scores based on charging_priority
                    if charging_priority == "prioritize_renewables":
                        time_w, load_w, renewable_w = 0.15, 0.15, 0.7 # Heavily favor renewables
                        logger.debug(f"GridAgent: Charger {charger_id} applying 'Prioritize Renewables' weights.")
                    elif charging_priority == "minimize_cost": # Grid agent helps by pushing to cheap (off-peak) times
                        time_w, load_w, renewable_w = 0.6, 0.2, 0.2
                        base_valley_bonus_score = 1.0 # Make valley even more attractive
                        logger.debug(f"GridAgent: Charger {charger_id} applying 'Minimize Cost' (favor off-peak) weights.")
                    elif charging_priority == "peak_shaving":
                        if hour in peak_hours:
                            charger_scores[charger_id] = -100 # Assign a very low score and continue
                            logger.debug(f"GridAgent (Peak Shaving): Charger {charger_id} heavily penalized during peak hour {hour}.")
                            continue
                        else: # Off-peak for peak_shaving strategy, strongly prefer off-peak
                            time_w, load_w, renewable_w = 0.7, 0.15, 0.15 # Emphasize time for off-peak, less focus on renewables here
                            logger.debug(f"GridAgent: Charger {charger_id} applying 'Peak Shaving' (off-peak) weights.")

                    # Calculate individual score components using current values from grid_status
                    current_time_score = 0
                    if hour in valley_hours: current_time_score = base_valley_bonus_score
                    elif hour not in peak_hours: current_time_score = base_normal_time_score
                    else: current_time_score = base_peak_penalty_score

                    current_renewable_score = (renewable_ratio / 100.0) if renewable_ratio is not None else 0.0
                    current_load_score = max(0, 1.0 - (grid_load_percentage / 100.0)) if grid_load_percentage is not None else 0.5


                    grid_score = (current_time_score * time_w +
                                  current_renewable_score * renewable_w +
                                  current_load_score * load_w)

                    if is_v2g_active_or_requested and self.operational_mode == 'v2g':
                        grid_score -= 0.5
                        logger.debug(f"GridAgent: Charger {charger_id} penalized due to active V2G request/dispatch.")

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
        # Base weights, can be loaded from config if MultiAgentSystem passes its config here
        # For now, using the defaults that were previously set by set_weights.
        # self.config should ideally be passed to Coordinator or weights directly.
        # Let's assume self.weights are the "balanced" weights, potentially set by MAS if config is passed to Coordinator.
        self.base_weights = {"user": 0.4, "profit": 0.3, "grid": 0.3} # Default balanced weights

    def set_weights(self, weights): # This method can still be used for initial config loading
        """Set agent base weights from config"""
        self.base_weights = { # Store as base_weights
            "user": weights.get("user_satisfaction", 0.4),
            "profit": weights.get("operator_profit", 0.3),
            "grid": weights.get("grid_friendliness", 0.3)
        }
        # 确保权重和为1
        total_w = sum(self.base_weights.values())
        if total_w > 0 and abs(total_w - 1.0) > 1e-6:
             logger.warning(f"Coordinator base weights do not sum to 1 ({total_w}). Normalizing.")
             for k in self.base_weights: self.base_weights[k] /= total_w
        logger.info(f"Coordinator base weights updated: User={self.base_weights['user']:.2f}, Profit={self.base_weights['profit']:.2f}, Grid={self.base_weights['grid']:.2f}")

    def _estimate_assignment_power_kw(self, user_dict, charger_dict, state): # Added state for future use e.g. vehicle_models
        """Estimates power for a user-charger assignment in kW."""
        # More sophisticated: consider user.vehicle_model.max_charging_rate_kw, current SOC.
        # For now, use charger's max power or a default.
        # Ensure 'max_power' is the correct key and in kW. If it's 'max_power_kw', use that.
        charger_max_power_kw = charger_dict.get('max_power_kw', charger_dict.get('max_power', 30.0)) # Assuming 30kW default

        # Placeholder for EV's max acceptance rate if available
        # vehicle_type = user_dict.get('vehicle_type')
        # vehicle_models = state.get('vehicle_models', {}) # Assuming vehicle_models are part of state
        # ev_max_power_kw = charger_max_power_kw # Default to charger max
        # if vehicle_type and vehicle_models and vehicle_type in vehicle_models:
        #     ev_max_power_kw = vehicle_models[vehicle_type].get('max_charging_rate_kw', charger_max_power_kw)
        # return min(charger_max_power_kw, ev_max_power_kw)
        return charger_max_power_kw


    def resolve_conflicts(self, user_decisions, profit_decisions, grid_decisions, state, charging_priority="balanced", grid_preferences=None): # Added grid_preferences
        """Resolve conflicts using dynamically adjusted weights, capacity checks, and EV fleet load limit."""
        if grid_preferences is None: # Ensure grid_preferences is a dict
            grid_preferences = {}

        final_decisions_dict = {} # Changed name to avoid confusion with outer scope final_decisions
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

            # --- Dynamic Weight Adjustment based on charging_priority ---
            current_weights = self.base_weights.copy() # Start with base/balanced weights
            requested_v2g_mw = grid_preferences.get("v2g_discharge_active_request_mw", 0.0)

            if charging_priority == "prioritize_renewables":
                current_weights = {"user": 0.2, "profit": 0.2, "grid": 0.6}
                logger.debug("Coordinator: Applying 'Prioritize Renewables' dynamic weights.")
            elif charging_priority == "minimize_cost":
                current_weights = {"user": 0.3, "profit": 0.5, "grid": 0.2}
                logger.debug("Coordinator: Applying 'Minimize Cost' dynamic weights.")
            elif charging_priority == "peak_shaving":
                current_weights = {"user": 0.15, "profit": 0.15, "grid": 0.7}
                logger.debug("Coordinator: Applying 'Peak Shaving' dynamic weights.")
            # else: "balanced" uses self.base_weights as is.

            # If V2G is actively requested, slightly boost grid agent's influence further
            # This is a simple way; more complex logic could involve specific V2G scores from agents
            if requested_v2g_mw > 0 and self.operational_mode == 'v2g': # operational_mode is on MAS, not coordinator directly
                # Need to get operational_mode from MAS or pass it in. For now, assume coordinator is aware or MAS passes it.
                # Let's assume MultiAgentSystem passes its self.operational_mode to resolve_conflicts
                # For now, this direct check is not possible without changing resolve_conflicts signature again or MAS structure.
                # So, this specific boost might be better handled inside GridFriendlinessAgent's scoring.
                # logger.info(f"Coordinator: V2G request active, slightly boosting grid agent weight if possible.")
                # current_weights["grid"] = min(0.8, current_weights["grid"] + 0.1) # Example boost
                pass


            # Normalize if necessary (e.g., if custom priority weights don't sum to 1)
            total_w_dynamic = sum(current_weights.values())
            if total_w_dynamic > 0 and abs(total_w_dynamic - 1.0) > 1e-6:
                 for k_w_dyn in current_weights: current_weights[k_w_dyn] /= total_w_dynamic
            # --- End Dynamic Weight Adjustment ---

            # 获取各 agent 的推荐和对应的权重
            if user_id in user_decisions:
                choices.append((user_decisions[user_id], current_weights.get("user", 0)))
            if user_id in profit_decisions:
                choices.append((profit_decisions[user_id], current_weights.get("profit", 0)))
            if user_id in grid_decisions:
                choices.append((grid_decisions[user_id], current_weights.get("grid", 0)))

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
            assigned_this_user = False
            for best_charger_id, vote_score in sorted_chargers:
                if assigned_count.get(best_charger_id, 0) < max_queue_len_config:
                    if chargers_state.get(best_charger_id, {}).get('status') != 'failure':
                        final_decisions_dict[user_id] = best_charger_id
                        assigned_count[best_charger_id] += 1
                        assigned_this_user = True
                        logger.debug(f"Coordinator initial assignment: User {user_id} to Charger {best_charger_id} (Score: {vote_score:.2f})")
                        break
                    else:
                        logger.debug(f"Charger {best_charger_id} (top vote for {user_id}) is in failure. Trying next.")
            # if not assigned_this_user:
            #     logger.debug(f"Could not assign user {user_id}; all preferred chargers full or invalid.")

        self.conflict_history.append(conflict_count)
        logger.info(f"Coordinator initial resolution: {len(final_decisions_dict)} assignments, {conflict_count} conflicts.")

        # --- Apply Max EV Fleet Load Limit ---
        max_ev_fleet_load_mw = grid_preferences.get("max_ev_fleet_load_mw")

        if max_ev_fleet_load_mw is not None and max_ev_fleet_load_mw < float('inf'): # Check if a limit is actually set
            current_assigned_ev_load_kw = 0
            assignments_with_power = []

            users_map = {u['user_id']: u for u in state.get('users', []) if 'user_id' in u}

            for user_id, charger_id in final_decisions_dict.items():
                user = users_map.get(user_id)
                charger = chargers_state.get(charger_id)
                if user and charger:
                    power_kw = self._estimate_assignment_power_kw(user, charger, state)
                    assignments_with_power.append({"user_id": user_id, "charger_id": charger_id, "power_kw": power_kw})
                    current_assigned_ev_load_kw += power_kw

            current_assigned_ev_load_mw = current_assigned_ev_load_kw / 1000.0

            if current_assigned_ev_load_mw > max_ev_fleet_load_mw:
                logger.info(f"MAS: Initial EV load {current_assigned_ev_load_mw:.2f} MW exceeds limit {max_ev_fleet_load_mw:.2f} MW. Applying curtailment.")

                # Sort by power (highest first) to remove largest consumers first
                assignments_with_power.sort(key=lambda x: x['power_kw'], reverse=True)

                curtailed_final_decisions = final_decisions_dict.copy()

                for assignment_to_remove in assignments_with_power:
                    if current_assigned_ev_load_mw <= max_ev_fleet_load_mw:
                        break

                    user_to_remove_id = assignment_to_remove['user_id']
                    power_removed_kw = assignment_to_remove['power_kw']

                    if user_to_remove_id in curtailed_final_decisions:
                        del curtailed_final_decisions[user_to_remove_id]
                        current_assigned_ev_load_kw -= power_removed_kw
                        current_assigned_ev_load_mw = current_assigned_ev_load_kw / 1000.0
                        logger.info(f"MAS: Curtailed user {user_to_remove_id} (removed {power_removed_kw:.2f} kW). New total EV load: {current_assigned_ev_load_mw:.2f} MW")

                final_decisions_dict = curtailed_final_decisions
                logger.info(f"MAS: EV load after curtailment: {current_assigned_ev_load_mw:.2f} MW. Total assignments: {len(final_decisions_dict)}")
        else:
            logger.debug(f"No Max EV Fleet Load limit applied or limit is infinite ({max_ev_fleet_load_mw} MW).")

        return final_decisions_dict