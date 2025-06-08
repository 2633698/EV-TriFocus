# ev_charging_project/algorithms/coordinated_mas.py

from datetime import datetime
import math
import logging
from collections import defaultdict
from simulation.utils import calculate_distance

logger = logging.getLogger("MAS")

class MultiAgentSystem:
    def __init__(self, main_config=None): # Expects the full application config
        self.config = main_config if main_config is not None else {}
        
        coordinated_mas_config = self.config.get('algorithms', {}).get('coordinated_mas', {})
        
        user_params = coordinated_mas_config.get('user_satisfaction_agent_params', {})
        profit_params = coordinated_mas_config.get('operator_profit_agent_params', {})
        grid_params = coordinated_mas_config.get('grid_friendliness_agent_params', {})
        coordinator_params = coordinated_mas_config.get('coordinator_params', {})

        self.user_agent = CoordinatedUserSatisfactionAgent(user_params)
        self.profit_agent = CoordinatedOperatorProfitAgent(profit_params)
        self.grid_agent = CoordinatedGridFriendlinessAgent(grid_params)
        self.coordinator = CoordinatedCoordinator(coordinator_params) # Pass specific params
        self.operational_mode = 'v1g'

    def set_operational_mode(self, mode):
        if mode in ['v1g', 'v2g']:
            self.operational_mode = mode
            logger.info(f"MAS operational mode set to: {self.operational_mode}")
            if hasattr(self.grid_agent, 'set_operational_mode'):
                self.grid_agent.set_operational_mode(mode)
        else:
            logger.warning(f"MAS: Unknown operational mode: {mode}")

    def make_decisions(self, state, manual_decisions=None, grid_preferences=None):
        if grid_preferences is None: grid_preferences = {}

        # Ensure agents and coordinator have the latest config if it can change dynamically
        # (or ensure config is passed during their __init__ if it's static post-MAS-init)
        # For now, assuming self.config is set once for MAS and passed to coordinator.
        # Agents might need config if their parameters are in the main config file.
        # Example: if UserSatisfactionAgent needed config:
        # self.user_agent.config = self.config
        # Or pass it in make_decision if params can change per step based on global config changes

        user_decisions = self.user_agent.make_decision(state, grid_preferences)
        profit_decisions = self.profit_agent.make_decisions(state, grid_preferences)
        grid_decisions = self.grid_agent.make_decisions(state, grid_preferences)

        self.user_agent.last_decision = user_decisions
        self.profit_agent.last_decision = profit_decisions
        self.grid_agent.last_decision = grid_decisions

        charging_priority = grid_preferences.get("charging_priority", "balanced")

        # Pass MAS operational_mode to coordinator if it needs to adjust weights based on it
        # (Currently, coordinator's V2G boost logic is commented out)
        # grid_preferences_for_coord = grid_preferences.copy()
        # grid_preferences_for_coord['mas_operational_mode'] = self.operational_mode

        final_decisions = self.coordinator.resolve_conflicts(
            user_decisions, profit_decisions, grid_decisions, state,
            charging_priority, grid_preferences # Pass full grid_preferences
        )
        return final_decisions

class CoordinatedUserSatisfactionAgent:
    def __init__(self, params=None):
        self.params = params if params is not None else {}
        self.last_decision = {}
        self.last_reward = 0

    def make_decision(self, state, grid_preferences=None):
        if grid_preferences is None: grid_preferences = {}
        recommendations = {}
        users = state.get("users", [])
        chargers = state.get("chargers", [])
        timestamp_str = state.get("timestamp")

        if not users or not chargers or not timestamp_str:
            logger.warning("UserAgent: Missing users, chargers, or timestamp in state.")
            return recommendations
        try:
            timestamp = datetime.fromisoformat(timestamp_str)
        except (ValueError, TypeError):
            logger.warning(f"UserAgent: Invalid timestamp format: {timestamp_str}. Defaulting to current time.")
            timestamp = datetime.now()

        current_hour = timestamp.hour

        for user in users:
            user_id = user.get("user_id", "UNKNOWN_USER")
            soc = user.get("soc", 100.0)
            status = user.get("status", "unknown")
            needs_charge_flag = user.get("needs_charge_decision", False)
            threshold = self._get_charging_threshold(current_hour)

            logger.debug(f"UserAgent: Checking User ID: {user_id}, SOC: {soc:.1f}%, Status: '{status}', NeedsChargeFlag: {needs_charge_flag}, DecisionThreshold: {threshold:.1f}% (soc < threshold OR needs_charge_flag), UpperSOCLimit: 90%")

            if status in ["charging", "waiting"]:
                logger.debug(f"UserAgent: User {user_id} skipped (already '{status}').")
                continue
            if soc >= 90:
                logger.debug(f"UserAgent: User {user_id} skipped (SOC {soc:.1f}% >= 90%).")
                continue
            if not (needs_charge_flag or soc < threshold):
                logger.debug(f"UserAgent: User {user_id} skipped (Not meeting charging criteria: needs_charge_flag={needs_charge_flag}, soc={soc:.1f}% vs threshold={threshold:.1f}%).")
                continue

            logger.info(f"UserAgent: User {user_id} (SOC {soc:.1f}%) IS being considered for charging recommendation.")
            best_charger_info = self._find_best_charger_for_user(user, chargers, state, grid_preferences)
            if best_charger_info and 'charger_id' in best_charger_info:
                recommendations[user_id] = best_charger_info['charger_id']
                logger.info(f"UserAgent: Recommended Charger ID: {best_charger_info['charger_id']} for User ID: {user_id}.")
            else:
                logger.warning(f"UserAgent: No suitable charger found by UserSatisfactionAgent for User ID: {user_id} (SOC {soc:.1f}%).")

        self.last_decision = recommendations
        return recommendations

    def _get_charging_threshold(self, hour):
        thresholds_by_hour = self.params.get('soc_thresholds_by_hour', {})
        default_thresh = thresholds_by_hour.get("default", 50)
        night_start = thresholds_by_hour.get("night_start_hour", 22)
        night_end = thresholds_by_hour.get("night_end_hour", 6)
        night_thresh = thresholds_by_hour.get("night_soc_threshold", 60)

        threshold = default_thresh
        if hour >= night_start or hour < night_end:
            threshold = night_thresh
        logger.debug(f"UserAgent: Charging threshold for hour {hour} set to {threshold}%.")
        return threshold

    def _find_best_charger_for_user(self, user, chargers, state, grid_preferences=None):
        if grid_preferences is None: grid_preferences = {}
        best_charger = None
        min_weighted_cost = float('inf')
        user_pos = user.get("current_position", {"lat": 0, "lng": 0})
        
        time_sensitivity_base = user.get("time_sensitivity", self.params.get('default_time_sensitivity', 0.5))
        price_sensitivity_base = user.get("price_sensitivity", self.params.get('default_price_sensitivity', 0.5))
        charging_priority = grid_preferences.get("charging_priority", "balanced")
        
        effective_price_sensitivity = price_sensitivity_base
        if charging_priority == "minimize_cost":
            effective_price_sensitivity = price_sensitivity_base * self.params.get('minimize_cost_priority_price_sensitivity_factor', 1.5)

        grid_status = state.get("grid_status", {})
        current_price = grid_status.get("current_price", 0.85)
        
        travel_time_dist_mult = self.params.get('travel_time_distance_multiplier', 2.0)
        avg_charge_time_defaults = self.params.get('avg_charge_time_by_type', {"superfast": 30, "fast": 45, "normal": 60})
        price_scaling = self.params.get('price_cost_scaling_factor', 50.0)

        for charger in chargers:
            if charger.get("status") == "failure": continue
            charger_pos = charger.get("position", {"lat": 0, "lng": 0})
            distance = calculate_distance(user_pos, charger_pos)
            travel_time = distance * travel_time_dist_mult
            
            queue_length = len(charger.get("queue", []))
            charger_type = charger.get("type", "normal")
            avg_charge_time = avg_charge_time_defaults.get(charger_type, 60) # Default to 'normal' time
            
            wait_time = queue_length * avg_charge_time
            charge_needed = user.get("battery_capacity", 60) * (1 - user.get("soc", 50)/100)
            price_multiplier = charger.get("price_multiplier", 1.0)
            est_cost = charge_needed * current_price * price_multiplier
            
            time_cost = travel_time + wait_time
            price_cost = est_cost / price_scaling if price_scaling > 0 else est_cost
            
            if not isinstance(time_sensitivity_base, (int, float)): time_sensitivity_base = self.params.get('default_time_sensitivity', 0.5)
            if not isinstance(effective_price_sensitivity, (int, float)): effective_price_sensitivity = price_sensitivity_base
            
            weighted_cost = (time_cost * time_sensitivity_base) + (price_cost * effective_price_sensitivity)
            if weighted_cost < min_weighted_cost:
                min_weighted_cost = weighted_cost
                best_charger = charger
        return best_charger

class CoordinatedOperatorProfitAgent:
    def __init__(self, params=None):
        self.params = params if params is not None else {}
        self.last_decision = {}
        self.last_reward = 0

    def make_decisions(self, state, grid_preferences=None):
        if grid_preferences is None: grid_preferences = {}
        recommendations = {}
        users = state.get("users", [])
        chargers = state.get("chargers", [])
        timestamp_str = state.get("timestamp")
        grid_status = state.get("grid_status", {})

        if not users or not chargers or not timestamp_str:
            logger.warning("ProfitAgent: Missing users, chargers, or timestamp in state.")
            return recommendations
        try:
            timestamp = datetime.fromisoformat(timestamp_str)
            hour = timestamp.hour
        except (ValueError, TypeError):
            logger.warning(f"ProfitAgent: Invalid timestamp format: {timestamp_str}. Defaulting hour to 0.")
            hour = 0

        peak_hours = grid_status.get("peak_hours", [])
        valley_hours = grid_status.get("valley_hours", [])
        current_grid_price = grid_status.get("current_price", 0.85)
        charging_priority = grid_preferences.get("charging_priority", "balanced")

        for user in users:
            user_id = user.get("user_id")
            soc = user.get("soc", 100)
            if not user_id or user.get("status") in ["charging", "waiting"]: continue
            if soc < 95: # Assuming 95 is a general threshold to consider charging
                best_charger_info = self._find_most_profitable_charger(user, chargers, current_grid_price, peak_hours, valley_hours, hour, charging_priority)
                if best_charger_info:
                    recommendations[user_id] = best_charger_info["charger_id"]
        self.last_decision = recommendations
        return recommendations

    def _find_most_profitable_charger(self, user, chargers, current_grid_price, peak_hours, valley_hours, hour, charging_priority):
        best_charger = None
        max_profit_score = float('-inf')
        
        op_cost_multipliers = self.params.get('minimize_cost_priority_op_cost_multipliers', {"peak": 1.25, "valley": 0.75, "default": 1.0})
        operator_cost_of_energy_multiplier = op_cost_multipliers.get('default', 1.0)
        if charging_priority == "minimize_cost":
            if hour in peak_hours: operator_cost_of_energy_multiplier = op_cost_multipliers.get('peak', 1.25)
            elif hour in valley_hours: operator_cost_of_energy_multiplier = op_cost_multipliers.get('valley', 0.75)
            logger.debug(f"ProfitAgent: User {user.get('user_id')} (Minimize Cost) - OpCostMultiplier: {operator_cost_of_energy_multiplier}")

        revenue_multipliers = self.params.get('revenue_multipliers_by_type', {"fast": 1.1, "superfast": 1.2, "normal": 1.0})
        base_energy_cost_rate = self.params.get('operator_base_energy_cost_rate', 0.6)
        queue_penalty_factor = self.params.get('queue_score_penalty_factor', 0.3)
        charge_needed_factor_config = self.params.get('charge_needed_score_factor', 0.05)

        for charger in chargers:
            if charger.get("status") == "failure": continue
            
            charger_price_multiplier = charger.get("price_multiplier", 1.0) # Charger's own markup
            effective_charge_price_to_user = current_grid_price * charger_price_multiplier
            
            revenue_potential = effective_charge_price_to_user
            charger_type = charger.get("type", "normal")
            revenue_potential *= revenue_multipliers.get(charger_type, 1.0)
            
            estimated_energy_cost_for_operator = current_grid_price * base_energy_cost_rate * operator_cost_of_energy_multiplier
            profit_margin_score = revenue_potential - estimated_energy_cost_for_operator
            
            queue_length = len(charger.get("queue", []))
            profit_score = profit_margin_score / (1 + queue_length * queue_penalty_factor) # Apply queue penalty
            
            charge_needed_user = (100 - user.get("soc", 50)) / 50.0 # Scale: 0-2
            profit_score *= (1 + charge_needed_user * charge_needed_factor_config) # Boost by how much user needs charge
            
            if profit_score > max_profit_score:
                max_profit_score = profit_score
                best_charger = charger
        return best_charger

class CoordinatedGridFriendlinessAgent:
    def __init__(self, params=None):
        self.params = params if params is not None else {}
        self.last_decision = {}
        self.last_reward = 0
        self.operational_mode = 'v1g' # Default, can be changed by set_operational_mode

    def set_operational_mode(self, mode):
        if mode in ['v1g', 'v2g']:
            self.operational_mode = mode
            logger.info(f"CoordinatedGridFriendlinessAgent operational mode set to: {self.operational_mode}")
        else:
            logger.warning(f"CoordinatedGridFriendlinessAgent: Unknown operational mode: {mode}")

    def make_decisions(self, state, grid_preferences=None):
        if grid_preferences is None: grid_preferences = {}
        decisions = {}
        users_list = state.get("users", [])
        chargers_list = state.get("chargers", [])
        timestamp_str = state.get("timestamp")
        grid_status = state.get("grid_status", {})

        if not users_list or not chargers_list or not timestamp_str:
            logger.warning("GridAgent: Missing users, chargers, or timestamp in state.")
            return decisions
        try:
            timestamp = datetime.fromisoformat(timestamp_str)
            hour = timestamp.hour
        except (ValueError, TypeError):
            logger.warning(f"GridAgent: Invalid timestamp format: {timestamp_str}. Defaulting hour to 0.")
            hour = 0

        users = {user_data["user_id"]: user_data for user_data in users_list if isinstance(user_data, dict) and "user_id" in user_data}
        chargers = {charger_data["charger_id"]: charger_data for charger_data in chargers_list if isinstance(charger_data, dict) and "charger_id" in charger_data}

        grid_load_percentage = grid_status.get("grid_load_percentage", 50.0)
        renewable_ratio = grid_status.get("renewable_ratio", 0.0) # Assuming this is 0-100
        peak_hours = grid_status.get("peak_hours", [])
        valley_hours = grid_status.get("valley_hours", [])

        charging_candidates = []
        min_charge_needed = self.params.get('min_charge_needed_threshold', 10.0)
        soc_threshold = self.params.get('soc_threshold', 60.0)
        target_soc_deficit_calc = self.params.get('target_soc_for_deficit', 95.0)


        for user_id, user_data in users.items():
            soc = user_data.get("soc", 100.0)
            status = user_data.get("status", "unknown")
            needs_charge_flag = user_data.get("needs_charge_decision", False)

            logger.debug(f"GridAgent: Checking User ID: {user_id}, SOC: {soc:.1f}%, Status: '{status}', NeedsChargeFlag: {needs_charge_flag}, SOCThreshold: {soc_threshold}%, MinChargeNeeded: {min_charge_needed}%")

            if status in ["charging", "waiting"]:
                logger.debug(f"GridAgent: User {user_id} skipped (already '{status}').")
                continue

            charge_deficit = target_soc_deficit_calc - soc
            passes_soc_threshold = soc < soc_threshold
            passes_charge_amount_threshold = charge_deficit >= min_charge_needed

            is_candidate = False
            if needs_charge_flag and passes_charge_amount_threshold:
                logger.debug(f"GridAgent: User {user_id} is candidate via NeedsChargeFlag (charge needed: {charge_deficit:.1f}%).")
                is_candidate = True
            elif passes_soc_threshold and passes_charge_amount_threshold:
                logger.debug(f"GridAgent: User {user_id} is candidate via SOC < {soc_threshold}% (charge needed: {charge_deficit:.1f}%).")
                is_candidate = True

            if is_candidate:
                urgency = (100.0 - soc) # Higher urgency for lower SOC
                charging_candidates.append((user_id, user_data, urgency))
                logger.info(f"GridAgent: User {user_id} (SOC {soc:.1f}%) added to charging_candidates with urgency {urgency:.1f}.")
            else:
                if not (needs_charge_flag or passes_soc_threshold):
                     logger.debug(f"GridAgent: User {user_id} not candidate (failed primary need: needs_charge_flag={needs_charge_flag}, soc_under_{soc_threshold}={passes_soc_threshold}).")
                elif not passes_charge_amount_threshold:
                     logger.debug(f"GridAgent: User {user_id} not candidate (charge needed {charge_deficit:.1f}% < {min_charge_needed}%).")
        
        charging_candidates.sort(key=lambda x: -x[2]) # Higher urgency first

        requested_v2g_mw = grid_preferences.get("v2g_discharge_active_request_mw", 0.0)
        actual_v2g_mw_this_step = state.get('grid_status', {}).get('aggregated_metrics', {}).get('current_actual_v2g_dispatch_mw', 0.0)
        is_v2g_active_or_requested = self.operational_mode == 'v2g' and (requested_v2g_mw > 0 or actual_v2g_mw_this_step > 0)
        if is_v2g_active_or_requested:
            logger.info(f"GridAgent: V2G is active/requested (Request: {requested_v2g_mw} MW, Actual: {actual_v2g_mw_this_step} MW). Adjusting charging decisions.")

        charging_priority = grid_preferences.get("charging_priority", "balanced")
        charger_scores = {}
        
        max_q_defaults = self.params.get('max_queue_len_defaults', {"default": 3, "v2g_mode": 5, "v2g_active_request": 2, "peak_shaving_priority": 1})
        max_queue_len = max_q_defaults.get("default",3)
        if self.operational_mode == 'v2g':
            max_queue_len = max_q_defaults.get("v2g_mode",5)
            if is_v2g_active_or_requested: max_queue_len = max_q_defaults.get("v2g_active_request",2)
        if charging_priority == "peak_shaving" and hour in peak_hours and not is_v2g_active_or_requested :
            max_queue_len = max_q_defaults.get("peak_shaving_priority",1)
        logger.debug(f"GridAgent: OpMode='{self.operational_mode}', V2GActiveOrReq={is_v2g_active_or_requested}, Prio='{charging_priority}', Hour={hour}. MaxQueueLen={max_queue_len}")

        score_weights_map = {
            "balanced": self.params.get('score_weights_balanced', {"time": 0.5, "load": 0.3, "renewable": 0.2}),
            "v2g_mode": self.params.get('score_weights_v2g_mode', {"time": 0.4, "load": 0.25, "renewable": 0.35}),
            "prioritize_renewables": self.params.get('score_weights_prioritize_renewables', {"time": 0.15, "load": 0.15, "renewable": 0.7}),
            "minimize_cost": self.params.get('score_weights_minimize_cost', {"time": 0.6, "load": 0.2, "renewable": 0.2}),
            "peak_shaving": self.params.get('score_weights_peak_shaving', {"time": 0.7, "load": 0.15, "renewable": 0.15})
        }
        
        time_scores_map = {
            "default": self.params.get('time_scores_default', {"valley": 0.8, "shoulder": 0.2, "peak": -1.0}),
            "minimize_cost": self.params.get('time_scores_minimize_cost', {"valley": 1.0, "shoulder": 0.3, "peak": -0.5}),
            "peak_shaving": self.params.get('time_scores_peak_shaving', {"valley": 1.0, "shoulder": 0.4, "peak": -200})
        }

        current_score_weights = score_weights_map.get(charging_priority, score_weights_map["balanced"])
        if self.operational_mode == 'v2g': # V2G mode might override charging_priority weights for grid agent
            current_score_weights = score_weights_map.get("v2g_mode", current_score_weights)

        time_w = current_score_weights.get("time",0.5)
        load_w = current_score_weights.get("load",0.3)
        renewable_w = current_score_weights.get("renewable",0.2)

        current_time_scores = time_scores_map.get(charging_priority if charging_priority in time_scores_map else "default", time_scores_map["default"])


        for charger_id, charger_data in chargers.items():
            if charger_data.get("status") == "failure": continue
            current_queue_len = len(charger_data.get("queue", []))
            if charger_data.get("status") == "occupied": current_queue_len += 1

            if current_queue_len < max_queue_len:
                raw_load_score = max(0, 1.0 - (grid_load_percentage / 100.0)) if grid_load_percentage is not None else 0.5
                raw_renewable_score = (renewable_ratio / 100.0) if renewable_ratio is not None else 0.0 # renewable_ratio is 0-100

                if hour in valley_hours: raw_time_score = current_time_scores.get('valley', 0.8)
                elif hour not in peak_hours: raw_time_score = current_time_scores.get('shoulder', 0.2)
                else: raw_time_score = current_time_scores.get('peak', -1.0)

                # Special handling for peak_shaving priority during peak hours
                if charging_priority == "peak_shaving" and hour in peak_hours:
                    charger_scores[charger_id] = current_time_scores.get('peak',-200) # Use the very high penalty
                    logger.debug(f"GridAgent: Charger {charger_id} during peak_shaving gets score: {charger_scores[charger_id]:.2f}")
                    continue


                grid_score = (raw_time_score * time_w +
                              raw_renewable_score * renewable_w +
                              raw_load_score * load_w)

                if is_v2g_active_or_requested: # Apply penalty if V2G is active and we are still considering charging
                    grid_score += self.params.get('v2g_active_score_penalty', -0.75)
                
                charger_scores[charger_id] = grid_score
                logger.debug(f"GridAgent: Charger {charger_id} score: {grid_score:.2f} (T:{raw_time_score:.2f}*w{time_w:.2f}, R:{raw_renewable_score:.2f}*w{renewable_w:.2f}, L:{raw_load_score:.2f}*w{load_w:.2f}) Prio: {charging_priority}")

        available_chargers = sorted(charger_scores.items(), key=lambda item: -item[1])
        assigned_chargers = defaultdict(int)
        for user_id, user_data, urgency in charging_candidates:
            if not available_chargers: break
            best_choice_idx = -1
            best_charger_id = None
            for i, (charger_id, score) in enumerate(available_chargers):
                charger_info = chargers.get(charger_id, {})
                current_actual_queue = len(charger_info.get("queue", []))
                if charger_info.get("status") == "occupied": current_actual_queue += 1
                if current_actual_queue + assigned_chargers[charger_id] < max_queue_len:
                    best_choice_idx = i
                    best_charger_id = charger_id
                    break
            if best_choice_idx != -1 and best_charger_id is not None:
                decisions[user_id] = best_charger_id
                assigned_chargers[best_charger_id] += 1
                charger_info = chargers.get(best_charger_id, {}) # Re-fetch for safety, though not strictly needed here
                current_actual_queue = len(charger_info.get("queue", []))
                if charger_info.get("status") == "occupied": current_actual_queue += 1
                # If this charger is now full (considering assignments in this step), remove it from further consideration in this step
                if current_actual_queue + assigned_chargers[best_charger_id] >= max_queue_len:
                     available_chargers.pop(best_choice_idx)
        self.last_decision = decisions
        return decisions

class CoordinatedCoordinator:
    def __init__(self, params=None):
        self.params = params if params is not None else {}
        self.max_queue_len_config = self.params.get('max_queue_length', 4)
        logger.info(f"Coordinator initialized with max_queue_length: {self.max_queue_len_config}")

        # Base weights are part of params, but also allow direct setting via set_weights
        self.base_weights = self.params.get('base_agent_weights', {"user": 0.4, "profit": 0.3, "grid": 0.3}).copy()
        self.priority_weights_override = self.params.get('priority_weights_override', {})
        self.critical_soc_threshold = self.params.get('critical_soc_threshold', 20.0)
        self.critical_soc_max_queue_increment = self.params.get('critical_soc_max_queue_increment', 1)
        
        self.conflict_history = []
        self.last_agent_rewards = {}
        self._normalize_base_weights() # Normalize once at init

    def _normalize_base_weights(self):
        total_w = sum(self.base_weights.values())
        if total_w > 0 and abs(total_w - 1.0) > 1e-6:
            logger.warning(f"Coordinator base weights ({self.base_weights}) do not sum to 1 ({total_w}). Normalizing.")
            for k in self.base_weights: self.base_weights[k] /= total_w
        logger.info(f"Coordinator base weights (normalized): User={self.base_weights.get('user',0):.2f}, Profit={self.base_weights.get('profit',0):.2f}, Grid={self.base_weights.get('grid',0):.2f}")

    def set_weights(self, weights_input): # weights_input is expected to be like {"user_satisfaction":0.x, ...} or {"user":0.x, ...}
        # This method allows external override of base_weights, using the structure from scheduler.optimization_weights
        user_w = weights_input.get("user_satisfaction", weights_input.get("user", self.base_weights.get("user", 0.4)))
        profit_w = weights_input.get("operator_profit", weights_input.get("profit", self.base_weights.get("profit", 0.3)))
        grid_w = weights_input.get("grid_friendliness", weights_input.get("grid", self.base_weights.get("grid", 0.3)))
        
        self.base_weights = {"user": user_w, "profit": profit_w, "grid": grid_w}
        self._normalize_base_weights()


    def _estimate_assignment_power_kw(self, user_dict, charger_dict, state):
        charger_max_power_kw = charger_dict.get('max_power_kw', charger_dict.get('max_power', 30.0))
        return charger_max_power_kw

    def resolve_conflicts(self, user_decisions, profit_decisions, grid_decisions, state, charging_priority="balanced", grid_preferences=None):
        if grid_preferences is None: grid_preferences = {}

        final_decisions_dict = {}
        conflict_count = 0
        all_users = set(user_decisions.keys()) | set(profit_decisions.keys()) | set(grid_decisions.keys())

        logger.info(f"Coordinator: Starting conflict resolution for {len(all_users)} users. Priority: '{charging_priority}'.")
        logger.debug(f"Coordinator: UserDecisions: {user_decisions}")
        logger.debug(f"Coordinator: ProfitDecisions: {profit_decisions}")
        logger.debug(f"Coordinator: GridDecisions: {grid_decisions}")

        chargers_list = state.get('chargers', [])
        if not chargers_list:
             logger.error("Coordinator: No chargers found in state.")
             return {}

        users_dict = {u['user_id']: u for u in state.get('users', []) if 'user_id' in u}
        chargers_state = {c['charger_id']: c for c in chargers_list if 'charger_id' in c}

        assigned_count = defaultdict(int)
        for cid, charger in chargers_state.items():
            if charger.get('status') == 'occupied':
                assigned_count[cid] += 1
            assigned_count[cid] += len(charger.get('queue', []))

        user_list = sorted(list(all_users))

        for user_id in user_list:
            user_soc = users_dict.get(user_id, {}).get('soc', -1)
            logger.debug(f"Coordinator: Processing user {user_id} (SOC {user_soc:.1f}%).")
            choices = []

            # Determine current weights based on priority
            current_weights = self.priority_weights_override.get(charging_priority, self.base_weights).copy()
            if charging_priority in self.priority_weights_override:
                logger.debug(f"Coordinator: Using override weights for priority '{charging_priority}': {current_weights}")
            else:
                logger.debug(f"Coordinator: Using base_weights for priority '{charging_priority}': {current_weights}")
            
            # Normalization of current_weights (important if overrides or base_weights don't sum to 1)
            total_w_dynamic = sum(current_weights.values())
            if total_w_dynamic > 0 and abs(total_w_dynamic - 1.0) > 1e-6:
                 logger.warning(f"Coordinator dynamic weights for priority '{charging_priority}' (Source: {'override' if charging_priority in self.priority_weights_override else 'base'}, Original: {self.priority_weights_override.get(charging_priority, self.base_weights)}) do not sum to 1 ({total_w_dynamic}). Normalizing to: { {k: v/total_w_dynamic for k,v in current_weights.items()} }")
                 for k_w_dyn in current_weights: current_weights[k_w_dyn] /= total_w_dynamic
            
            log_choices_for_user = []
            if user_id in user_decisions:
                choices.append((user_decisions[user_id], current_weights.get("user", 0)))
                log_choices_for_user.append(f"UserAgent: {user_decisions[user_id]} (w:{current_weights.get('user',0):.2f})")
            if user_id in profit_decisions:
                choices.append((profit_decisions[user_id], current_weights.get("profit", 0)))
                log_choices_for_user.append(f"ProfitAgent: {profit_decisions[user_id]} (w:{current_weights.get('profit',0):.2f})")
            if user_id in grid_decisions:
                choices.append((grid_decisions[user_id], current_weights.get("grid", 0)))
                log_choices_for_user.append(f"GridAgent: {grid_decisions[user_id]} (w:{current_weights.get('grid',0):.2f})")
            logger.debug(f"Coordinator: User {user_id} choices: [{', '.join(log_choices_for_user)}]")

            if not choices:
                logger.warning(f"Coordinator: No recommendations for User {user_id} (SOC {user_soc:.1f}%).")
                continue

            unique_choices = {cid for cid, w in choices}
            if len(unique_choices) > 1: conflict_count += 1

            charger_votes = defaultdict(float)
            for charger_id, weight in choices:
                if charger_id in chargers_state:
                    charger_votes[charger_id] += weight
                else:
                     logger.warning(f"Coordinator: Recommended charger {charger_id} for user {user_id} (vote weight {weight:.2f}) not found in current state. Ignoring vote.")

            if not charger_votes:
                 logger.warning(f"Coordinator: No VALID charger votes for User {user_id} (SOC {user_soc:.1f}%). Original choices: {log_choices_for_user}")
                 continue
            logger.debug(f"Coordinator: Charger votes for user {user_id}: {dict(charger_votes)}")

            sorted_chargers = sorted(charger_votes.items(), key=lambda item: -item[1])
            assigned_this_user = False
            for best_charger_id, vote_score in sorted_chargers:
                effective_max_queue_for_user = self.max_queue_len_config # Base max queue from config
                if user_soc < self.critical_soc_threshold: # Use critical_soc_threshold from self.params
                    effective_max_queue_for_user += self.critical_soc_max_queue_increment # Use increment from self.params
                    logger.debug(f"Coordinator: User {user_id} has critical SOC {user_soc:.1f}% (Threshold: {self.critical_soc_threshold}%) applying increment {self.critical_soc_max_queue_increment}. Effective max queue: {effective_max_queue_for_user}.")
                
                current_q_count_at_charger = assigned_count.get(best_charger_id, 0)
                if current_q_count_at_charger < effective_max_queue_for_user:
                    if chargers_state.get(best_charger_id, {}).get('status') != 'failure':
                        final_decisions_dict[user_id] = best_charger_id
                        assigned_count[best_charger_id] += 1
                        assigned_this_user = True
                        logger.info(f"Coordinator: Assigned User {user_id} (SOC {user_soc:.1f}%) to Charger {best_charger_id} (Score: {vote_score:.2f}). Queue at {best_charger_id} now: {assigned_count[best_charger_id]}/{self.max_queue_len_config} (EffectiveMax: {effective_max_queue_for_user}).")
                        break
                    else:
                        logger.debug(f"Coordinator: Charger {best_charger_id} (top vote for User {user_id}) is in failure state. Trying next.")
                else:
                    logger.debug(f"Coordinator: Charger {best_charger_id} (top vote for User {user_id}) is full (Queue: {current_q_count_at_charger}/{effective_max_queue_for_user}). Trying next.")

            if not assigned_this_user:
                logger.warning(f"Coordinator: Could NOT assign User {user_id} (SOC {user_soc:.1f}%). All preferred chargers were full or invalid. Top choices considered: {[(cid, round(s,2)) for cid, s in sorted_chargers[:3]]}")

        self.conflict_history.append(conflict_count)
        logger.info(f"Coordinator initial resolution: {len(final_decisions_dict)} assignments made, {conflict_count} conflicts encountered during voting.")

        max_ev_fleet_load_mw = grid_preferences.get("max_ev_fleet_load_mw")
        initial_assigned_count = len(final_decisions_dict)

        if max_ev_fleet_load_mw is not None and max_ev_fleet_load_mw < float('inf'):
            current_assigned_ev_load_kw = 0
            assignments_with_power = []

            for user_id, charger_id in final_decisions_dict.items():
                user = users_dict.get(user_id)
                charger = chargers_state.get(charger_id)
                if user and charger:
                    power_kw = self._estimate_assignment_power_kw(user, charger, state)
                    assignments_with_power.append({"user_id": user_id, "charger_id": charger_id, "power_kw": power_kw, "soc": user.get("soc", -1)})
                    current_assigned_ev_load_kw += power_kw

            current_assigned_ev_load_mw = current_assigned_ev_load_kw / 1000.0
            logger.info(f"Coordinator (MaxEVLoad): Checking limit. Limit: {max_ev_fleet_load_mw} MW. Initial assigned load: {current_assigned_ev_load_mw:.2f} MW from {initial_assigned_count} assignments.")

            if current_assigned_ev_load_mw > max_ev_fleet_load_mw:
                logger.warning(f"MAS: Initial EV load {current_assigned_ev_load_mw:.2f} MW exceeds limit {max_ev_fleet_load_mw:.2f} MW. Applying curtailment.")
                assignments_with_power.sort(key=lambda x: x['power_kw'], reverse=True)
                curtailed_final_decisions = final_decisions_dict.copy()
                for assignment_to_remove in assignments_with_power:
                    if current_assigned_ev_load_mw <= max_ev_fleet_load_mw: break
                    user_to_remove_id = assignment_to_remove['user_id']
                    power_removed_kw = assignment_to_remove['power_kw']
                    user_soc_removed = assignment_to_remove['soc']
                    if user_to_remove_id in curtailed_final_decisions:
                        del curtailed_final_decisions[user_to_remove_id]
                        current_assigned_ev_load_kw -= power_removed_kw
                        current_assigned_ev_load_mw = current_assigned_ev_load_kw / 1000.0
                        logger.warning(f"Coordinator (MaxEVLoad): Curtailed User {user_to_remove_id} (SOC {user_soc_removed:.1f}%, removing {power_removed_kw:.2f} kW). New total EV load: {current_assigned_ev_load_mw:.2f} MW")
                final_decisions_dict = curtailed_final_decisions

            if initial_assigned_count > len(final_decisions_dict):
                 logger.warning(f"Coordinator (MaxEVLoad): Curtailed {initial_assigned_count - len(final_decisions_dict)} assignments. Final assignments: {len(final_decisions_dict)}. Final EV load {current_assigned_ev_load_mw:.2f} MW.")
            else:
                 logger.info(f"Coordinator (MaxEVLoad): No curtailment needed. Final EV load {current_assigned_ev_load_mw:.2f} MW within limit {max_ev_fleet_load_mw} MW (or no limit set).")
        else:
            logger.info(f"Coordinator (MaxEVLoad): No Max EV Fleet Load limit applied (limit is None or infinite: {max_ev_fleet_load_mw}).")

        return final_decisions_dict