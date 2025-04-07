from datetime import datetime
import math
import logging
from collections import defaultdict

# Initialize logger for this module
logger = logging.getLogger("MAS")


class MultiAgentSystem:
    def __init__(self):
        self.config = {}
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
            if not user_id:
                continue
            
            # Only recommend charging if SOC is below threshold
            if soc < self._get_charging_threshold(timestamp.hour):
                best_charger_info = self._find_best_charger_for_user(user, chargers, state)
                if best_charger_info:
                    recommendations[user_id] = best_charger_info["charger_id"]
        
        self.last_decision = recommendations
        return recommendations
    
    def _get_charging_threshold(self, hour):
        # Example: Lower threshold during the day, higher at night
        if 6 <= hour < 22:
            return 30 # More likely to charge if below 30% during the day
        else:
            return 40 # Higher threshold at night

    def _find_best_charger_for_user(self, user, chargers, state):
        best_charger = None
        min_weighted_cost = float('inf')
        user_pos = user.get("current_position", {"lat": 0, "lng": 0})
        time_sensitivity = user.get("time_sensitivity", 0.5)
        price_sensitivity = user.get("price_sensitivity", 0.5)
        current_price = state.get("current_price", 0.85) # Use safe access

        for charger in chargers:
            # Skip failed chargers
            if charger.get("status") == "failure":
                continue

            charger_pos = charger.get("position", {"lat": 0, "lng": 0})
            distance = self._calculate_distance(user_pos, charger_pos)
            travel_time = distance * 2 # Simple estimate: 2 min/km

            queue_length = len(charger.get("queue", []))
            # Estimate wait time based on type and queue
            base_wait_per_user = 10 if charger.get("type") == "fast" else 20
            wait_time = queue_length * base_wait_per_user
            if charger.get("status") == "occupied":
                wait_time += base_wait_per_user / 2 # Add partial wait for current user

            # Estimate charging cost (simplified, doesn't account for charger price variations yet)
            charge_needed = user.get("battery_capacity", 60) * (1 - user.get("soc", 50)/100)
            est_cost = charge_needed * current_price

            # Weighted cost: lower is better
            time_cost = travel_time + wait_time
            # Scale cost relative to typical max cost (e.g., 50 yuan)
            price_cost = est_cost / 50.0

            weighted_cost = (time_cost * time_sensitivity) + (price_cost * price_sensitivity)

            if weighted_cost < min_weighted_cost:
                min_weighted_cost = weighted_cost
                best_charger = charger

        return best_charger

    def _calculate_distance(self, pos1, pos2):
        # Ensure coords are valid numbers
        lat1, lng1 = pos1.get('lat', 0), pos1.get('lng', 0)
        lat2, lng2 = pos2.get('lat', 0), pos2.get('lng', 0)
        if not all(isinstance(c, (int, float)) for c in [lat1, lng1, lat2, lng2]):
            return float('inf') # Invalid position yields max distance
        return math.sqrt((lat1 - lat2)**2 + (lng1 - lng2)**2) * 111


class CoordinatedOperatorProfitAgent:
    def __init__(self):
        self.last_decision = {}
        self.last_reward = 0
        
    def make_decisions(self, state):
        """
        Make decisions prioritizing operator profit
        
        Args:
            state: Current state of the environment
            
        Returns:
            decisions: Dict mapping user_ids to charger_ids
        """
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
        
        peak_hours = grid_status.get("peak_hours", [7, 8, 9, 10, 18, 19, 20, 21])
        valley_hours = grid_status.get("valley_hours", [0, 1, 2, 3, 4, 5])
        base_price = grid_status.get("current_price", 0.85) # Use safe access
        
        # Make profit-oriented recommendations
        for user in users:
            user_id = user.get("user_id")
            soc = user.get("soc", 100)
            if not user_id or user.get("status") in ["charging", "waiting"]:
                continue # Skip users already charging/waiting or without ID
            
            if soc < 80: # Consider users below 80% SOC
                best_charger_info = self._find_most_profitable_charger(user, chargers, base_price, peak_hours, valley_hours, hour)
                if best_charger_info:
                    recommendations[user_id] = best_charger_info["charger_id"]
        
        self.last_decision = recommendations
        return recommendations
    
    def _find_most_profitable_charger(self, user, chargers, base_price, peak_hours, valley_hours, hour):
        best_charger = None
        max_profit_score = float('-inf')

        for charger in chargers:
            if charger.get("status") == "failure":
                continue

            price_multiplier = 1.0
            if hour in peak_hours:
                price_multiplier = 1.2
            elif hour in valley_hours:
                price_multiplier = 0.8

            if charger.get("type") == "fast":
                price_multiplier *= 1.15

            # Estimated profit potential (simplified score)
            profit_potential = price_multiplier # Higher price = higher potential
            # Bonus for fast chargers
            if charger.get("type") == "fast":
                profit_potential *= 1.2
            # Penalty for long queue
            queue_length = len(charger.get("queue", []))
            profit_potential /= (1 + queue_length * 0.2)

            if profit_potential > max_profit_score:
                max_profit_score = profit_potential
                best_charger = charger

        return best_charger


class CoordinatedGridFriendlinessAgent:
    def __init__(self):
        self.last_decision = {}
        self.last_reward = 0
        
    def make_decisions(self, state):
        """
        Make decisions prioritizing grid friendliness
        
        Args:
            state: Current state of the environment
            
        Returns:
            decisions: Dict mapping user_ids to charger_ids
        """
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
        
        users = {user["user_id"]: user for user in users_list if "user_id" in user}
        chargers = {charger["charger_id"]: charger for charger in chargers_list if "charger_id" in charger}

        grid_load = grid_status.get("grid_load", 50) # Use safe access
        renewable_ratio = grid_status.get("renewable_ratio", 0) # Use safe access
        peak_hours = grid_status.get("peak_hours", [7, 8, 9, 10, 18, 19, 20, 21])
        valley_hours = grid_status.get("valley_hours", [0, 1, 2, 3, 4, 5])
        
        # Identify users who need charging
        charging_candidates = []
        for user_id, user in users.items():
            # Consider users traveling or idle with low SOC
            if user.get("status") not in ["charging", "waiting"] and user.get("soc", 100) < 50:
                urgency = (100 - user.get("soc", 100)) # Simple urgency based on SOC deficit
                charging_candidates.append((user_id, user, urgency))
        
        charging_candidates.sort(key=lambda x: -x[2]) # Most urgent first
        
        # Score each charger based on grid friendliness
        charger_scores = {}
        max_queue_len = 3 # Configurable?
        for charger_id, charger in chargers.items():
            if charger.get("status") != "failure" and len(charger.get("queue", [])) < max_queue_len:
                time_score = 0
                if hour in valley_hours:
                    time_score = 1.0
                elif hour not in peak_hours:
                    time_score = 0.5

                renewable_score = renewable_ratio / 100.0
                load_score = max(0, 1 - (grid_load / 100.0))

                # Combined score: prioritize valley hours, then renewables, then low load
                grid_score = time_score * 0.5 + renewable_score * 0.3 + load_score * 0.2
                charger_scores[charger_id] = grid_score
        
        # Sort available chargers by grid friendliness score
        available_chargers = sorted(charger_scores.items(), key=lambda item: -item[1])
        # Keep track of simulated assignments to avoid overbooking
        assigned_chargers = defaultdict(int) # charger_id -> count assigned this step
        
        for user_id, user, urgency in charging_candidates:
            if not available_chargers:
                break
            
            # Find the best grid-friendly charger for this user
            best_choice = None
            best_charger_id = None
            for i, (charger_id, score) in enumerate(available_chargers):
                 current_assignments = assigned_chargers[charger_id]
                 charger_capacity = 1 # Assumes 1 car per charger + queue
                 charger_queue_len = len(chargers.get(charger_id, {}).get("queue", []))
                 if current_assignments + charger_queue_len < max_queue_len:
                      best_choice = i
                      best_charger_id = charger_id
                      break # Found a suitable charger
            
            if best_choice is not None and best_charger_id is not None:
                decisions[user_id] = best_charger_id
                assigned_chargers[best_charger_id] += 1
                # If charger is now considered full for this planning step, remove it from pool
                if assigned_chargers[best_charger_id] + len(chargers.get(best_charger_id, {}).get("queue", [])) >= max_queue_len:
                     available_chargers.pop(best_choice)
        
        self.last_decision = decisions
        return decisions


class CoordinatedCoordinator:
    def __init__(self):
        self.weights = {
            "user": 0.4,
            "profit": 0.3,
            "grid": 0.3
        }
        self.conflict_history = []
        self.last_agent_rewards = {} # Store rewards used in decision
        
    def set_weights(self, weights):
        """Set agent weights"""
        self.weights = {
            "user": weights.get("user_satisfaction", 0.4), # Map from config names
            "profit": weights.get("operator_profit", 0.3),
            "grid": weights.get("grid_friendliness", 0.3)
        }
        logger.info(f"Coordinator weights updated: {self.weights}")
        
    def resolve_conflicts(self, user_decisions, profit_decisions, grid_decisions, state):
        """
        Resolve conflicts between agent decisions
        
        Args:
            user_decisions: Decisions from UserSatisfactionAgent
            profit_decisions: Decisions from OperatorProfitAgent
            grid_decisions: Decisions from GridFriendlinessAgent
            state: Current state of the environment
            
        Returns:
            final_decisions: Dict mapping user_ids to charger_ids
        """
        final_decisions = {}
        conflict_count = 0
        all_users = set(user_decisions.keys()) | set(profit_decisions.keys()) | set(grid_decisions.keys())
        
        chargers_state = {c['charger_id']: c for c in state.get('chargers', []) if 'charger_id' in c}
        assigned_count = defaultdict(int)
        max_queue_len = 3
        
        # Add users currently in queue or charging to assigned_count
        for cid, charger in chargers_state.items():
             assigned_count[cid] += len(charger.get('queue', []))
             if charger.get('status') == 'occupied':
                  assigned_count[cid] += 1
        
        # Process users (e.g., maybe prioritize by some criteria?)
        user_list = list(all_users)
        # random.shuffle(user_list) # Optional: Shuffle to avoid bias
        
        for user_id in user_list:
            choices = []
            if user_id in user_decisions:
                choices.append((user_decisions[user_id], self.weights.get("user", 0.4)))
            if user_id in profit_decisions:
                choices.append((profit_decisions[user_id], self.weights.get("profit", 0.3)))
            if user_id in grid_decisions:
                choices.append((grid_decisions[user_id], self.weights.get("grid", 0.3)))
            
            if not choices:
                continue
            
            # Simple conflict check
            unique_choices = {cid for cid, w in choices}
            if len(unique_choices) > 1:
                conflict_count += 1
            
            # Weighted voting for the best charger for THIS user
            charger_votes = defaultdict(float)
            for charger_id, weight in choices:
                charger_votes[charger_id] += weight
            
            # Sort potential chargers by votes (descending)
            sorted_chargers = sorted(charger_votes.items(), key=lambda item: -item[1])
            
            # Assign user to the best charger that still has capacity
            assigned = False
            for best_charger_id, vote_score in sorted_chargers:
                if assigned_count[best_charger_id] < max_queue_len:
                    final_decisions[user_id] = best_charger_id
                    assigned_count[best_charger_id] += 1
                    assigned = True
                    break # User assigned
            
            # if not assigned: logger.warning(f"Could not assign user {user_id}, all preferred chargers full.")
        
        self.conflict_history.append(conflict_count)
        # Store agent rewards/decisions for analysis?
        
        return final_decisions