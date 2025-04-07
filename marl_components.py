import numpy as np
import random
import pickle
import os
from collections import defaultdict
import logging
from datetime import datetime
import math

logger = logging.getLogger("MARL")

class MARLAgent:
    """Represents a single agent (e.g., a charging station) using Q-learning."""
    def __init__(self, agent_id, action_space_size, learning_rate=0.1, discount_factor=0.9, exploration_rate=0.1):
        self.agent_id = agent_id
        # Action space size is now fixed, actions are indices 0 to N-1
        self.action_space_size = action_space_size
        self.lr = learning_rate
        self.gamma = discount_factor
        self.epsilon = exploration_rate
        # Q-table keys are state strings, values are numpy arrays of Q-values for each action index
        self.q_table = defaultdict(lambda: np.zeros(self.action_space_size))

    def choose_action(self, state, current_action_map):
        """Choose action using epsilon-greedy strategy based on the current valid actions.

        Args:
            state: The current state representation for the agent.
            current_action_map: Dict mapping action index to actual action (e.g., 'idle', user_id).
                                This defines the valid actions in this specific step.

        Returns:
            action: The chosen action ('idle' or user_id).
            action_index: The index corresponding to the chosen action in the Q-table.
        """
        state_str = self._state_to_string(state)

        # Ensure Q-table entry exists and has the correct size
        if len(self.q_table[state_str]) != self.action_space_size:
            logger.warning(f"Q-table size mismatch for agent {self.agent_id} state {state_str}. Expected {self.action_space_size}, got {len(self.q_table[state_str])}. Resetting.")
            self.q_table[state_str] = np.zeros(self.action_space_size)

        valid_action_indices = list(current_action_map.keys())
        if not valid_action_indices:
            logger.warning(f"Agent {self.agent_id} has no valid actions in state {state_str}.")
            # Default to action index 0 ('idle') if no actions possible
            return current_action_map.get(0, 'idle'), 0

        if random.uniform(0, 1) < self.epsilon:
            # Explore: choose a random valid action index
            action_index = random.choice(valid_action_indices)
        else:
            # Exploit: choose the best action among *valid* actions
            q_values = self.q_table[state_str]
            valid_q_values = {idx: q_values[idx] for idx in valid_action_indices}

            if not valid_q_values:
                 # Should not happen if valid_action_indices is not empty
                 action_index = random.choice(valid_action_indices)
            else:
                max_q = max(valid_q_values.values())
                # Get all valid action indices that have the max Q-value
                best_action_indices = [idx for idx, q in valid_q_values.items() if q == max_q]
                action_index = random.choice(best_action_indices)

        chosen_action = current_action_map[action_index]
        return chosen_action, action_index

    def update_q_table(self, state, action_index, reward, next_state):
        """Update Q-value for the state-action pair.

           Note: Assumes the action space size is constant for Q-table structure.
                 The selection of the best next action considers only the maximum Q value
                 across all possible actions (indices 0 to N-1), assuming the environment
                 implicitly handles invalid actions in the next state.
        """
        if action_index < 0 or action_index >= self.action_space_size:
            logger.error(f"Invalid action_index {action_index} for agent {self.agent_id} (size {self.action_space_size}). State: {state}")
            return

        state_str = self._state_to_string(state)
        next_state_str = self._state_to_string(next_state)

        # Ensure Q-table entry for next state exists and has the correct size
        if len(self.q_table[next_state_str]) != self.action_space_size:
             self.q_table[next_state_str] = np.zeros(self.action_space_size)

        old_value = self.q_table[state_str][action_index]
        # Q-learning uses the max Q-value of the *next* state, irrespective of which actions
        # will be *actually* valid then. This is a simplification of IQL.
        next_max = np.max(self.q_table[next_state_str])

        # Q-learning formula
        new_value = old_value + self.lr * (reward + self.gamma * next_max - old_value)
        self.q_table[state_str][action_index] = new_value

    def _state_to_string(self, state):
        """Convert state dictionary to a hashable string for Q-table keys."""
        if not isinstance(state, dict):
            return str(state)
        # Sort items by key to ensure consistency
        items = sorted(state.items())
        return str(items)

    def load_q_table(self, file_path):
        """Load Q-table from a file."""
        if os.path.exists(file_path):
            try:
                with open(file_path, 'rb') as f:
                    loaded_q_dict = pickle.load(f)
                    # Convert back to defaultdict, ensuring values are numpy arrays of correct size
                    self.q_table = defaultdict(lambda: np.zeros(self.action_space_size))
                    for state_key, q_values in loaded_q_dict.items():
                        if len(q_values) == self.action_space_size:
                            self.q_table[state_key] = np.array(q_values)
                        else:
                            logger.warning(f"Size mismatch loading Q-table for agent {self.agent_id}, state {state_key}. Expected {self.action_space_size}, got {len(q_values)}. Skipping state.")

                logger.info(f"Q-table loaded for agent {self.agent_id} from {file_path}")
            except Exception as e:
                logger.error(f"Error loading Q-table for agent {self.agent_id} from {file_path}: {e}")
        else:
            logger.warning(f"Q-table file not found for agent {self.agent_id} at {file_path}. Starting with empty table.")

    def save_q_table(self, file_path):
        """Save Q-table to a file."""
        try:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, 'wb') as f:
                # Convert numpy arrays to lists for pickle compatibility if needed, though numpy arrays should work
                q_dict_to_save = {k: v.tolist() for k, v in self.q_table.items()}
                pickle.dump(q_dict_to_save, f)
            logger.info(f"Q-table saved for agent {self.agent_id} to {file_path}")
        except Exception as e:
             logger.error(f"Error saving Q-table for agent {self.agent_id} to {file_path}: {e}")


# --- Helper Functions for MARL ---

def get_agent_state(charger_id, global_state):
    """
    Extracts the relevant state information for a specific charger agent.
    """
    if not global_state or 'chargers' not in global_state:
        logger.warning(f"Cannot get agent state for {charger_id}. Invalid global_state.")
        return {}

    charger = next((c for c in global_state.get('chargers', []) if c['charger_id'] == charger_id), None)

    if not charger:
        logger.warning(f"Charger {charger_id} not found in global_state.")
        return {}

    # --- State Features ---
    status_map = {'available': 0, 'occupied': 1, 'failure': 2}
    charger_status = status_map.get(charger.get('status', 'available'), 0)
    queue_length = len(charger.get('queue', []))

    try:
        # Use .get() for timestamp
        timestamp_str = global_state.get('timestamp')
        if timestamp_str:
            timestamp = datetime.fromisoformat(timestamp_str)
            hour_of_day = timestamp.hour
        else:
             raise ValueError("Timestamp missing")
    except (ValueError, TypeError):
        logger.warning(f"Invalid or missing timestamp in global_state: {global_state.get('timestamp')}")
        hour_of_day = 0

    grid_load_category = 0
    # Use .get() for grid_load
    grid_load = global_state.get('grid_load', 50)
    if isinstance(grid_load, (int, float)):
        if grid_load > 80:
            grid_load_category = 2
        elif grid_load > 60:
            grid_load_category = 1
    else:
         logger.warning(f"Invalid grid_load type: {type(grid_load)}")

    renewable_ratio_category = 0
    # Use .get() for renewable_ratio
    renewable_ratio = global_state.get('renewable_ratio', 0)
    if isinstance(renewable_ratio, (int, float)):
        if renewable_ratio > 50:
             renewable_ratio_category = 2
        elif renewable_ratio > 20:
            renewable_ratio_category = 1
    else:
         logger.warning(f"Invalid renewable_ratio type: {type(renewable_ratio)}")

    # --- Nearby Demand (Simplified: count users needing charge within radius) ---
    users_needing_charge = 0
    charger_pos = charger.get('position', {'lat': 0, 'lng': 0})
    nearby_radius_sq = 0.05**2 # Approx 5km radius squared

    for user in global_state.get('users', []):
        # Consider users potentially needing charge soon
        needs_charge_threshold = 40 # SOC % threshold
        if user.get('soc', 100) < needs_charge_threshold and user.get('status') not in ['charging', 'waiting']:
             user_pos = user.get('current_position', {'lat': -999, 'lng': -999}) # Use default invalid coords
             if all(isinstance(coord, (int, float)) for coord in [user_pos.get('lat'), user_pos.get('lng'), charger_pos.get('lat'), charger_pos.get('lng')]):
                 dist_sq = (user_pos['lat'] - charger_pos['lat'])**2 + (user_pos['lng'] - charger_pos['lng'])**2
                 if dist_sq < nearby_radius_sq:
                     users_needing_charge += 1

    # --- Assemble State Dictionary ---
    state = {
        "status": charger_status,
        "queue": min(queue_length, 3),
        "hour_discrete": hour_of_day // 4,
        "grid_load_cat": grid_load_category,
        "renew_cat": renewable_ratio_category,
        "nearby_demand_cat": min(users_needing_charge, 2)
    }
    return state

def create_dynamic_action_map(charger_id, global_state, max_potential_users=5):
    """
    Creates a mapping from action index (0 to N-1) to the actual action ('idle' or user_id)
    that is valid for the agent in the current step.
    Index 0 is always 'idle'. Subsequent indices map to potential user IDs.

    Args:
        charger_id: The ID of the charger agent.
        global_state: The current global state of the environment.
        max_potential_users: Max number of users to consider in the action space (N-1).

    Returns:
        dict: Mapping action_index -> action ('idle' or user_id).
        int: The total size of the action space (N = max_potential_users + 1).
    """
    action_map = {0: 'idle'} # Action 0 is always idle
    action_space_size = max_potential_users + 1
    charger = next((c for c in global_state.get('chargers', []) if c['charger_id'] == charger_id), None)

    if not charger or charger.get('status') == 'failure':
        return action_map, action_space_size # Only 'idle' is possible if charger failed

    # Find users who are requesting charging and are reasonably close
    potential_users = []
    charger_pos = charger.get('position', {'lat': 0, 'lng': 0})
    # 增加检测范围 - 从原来的10km提高到15km
    max_dist_sq = 0.15**2 # 扩大范围到约15km

    for user in global_state.get('users', []):
        # 条件：降低SOC阈值 - 从50%调整至65%，确保更多用户被考虑
        # 更灵敏地捕捉需要充电的车辆
        if user.get('soc', 100) < 65 and user.get('status') not in ['charging', 'waiting']:
            # 检查用户是否明确需要充电决策，如果有这个标志
            needs_charge = user.get('needs_charge_decision', False)
            # 额外考虑：低电量用户总是需要充电
            soc_critical = user.get('soc', 100) < 30
            # 检查距离
            user_pos = user.get('current_position', {'lat': -999, 'lng': -999})
            
            if all(isinstance(coord, (int, float)) for coord in [user_pos.get('lat'), user_pos.get('lng'), 
                                                                 charger_pos.get('lat'), charger_pos.get('lng')]):
                dist_sq = (user_pos['lat'] - charger_pos['lat'])**2 + (user_pos['lng'] - charger_pos['lng'])**2
                
                # 更复杂的选择逻辑：根据SOC和距离的不同组合来决定是否考虑该用户
                if dist_sq < max_dist_sq:
                    distance_km = math.sqrt(dist_sq) * 111 # 转换为公里
                    
                    # 计算距离惩罚 - 距离越远，接受充电请求的可能性越低
                    # 但我们不完全排除远距离的关键低电量车辆
                    consider_user = False
                    
                    if soc_critical or needs_charge:
                        # 紧急情况 - 无论距离都考虑
                        consider_user = True
                        priority_score = (30 - user.get('soc', 30)) * (1 - (distance_km / 15))
                    elif user.get('soc', 100) < 50:
                        # 中度电量 - 如果在10km以内就考虑
                        if distance_km < 10:
                            consider_user = True
                            priority_score = (50 - user.get('soc', 50)) * (1 - (distance_km / 10))
                    else:
                        # 高电量但仍低于65% - 只考虑非常近的
                        if distance_km < 5:
                            consider_user = True
                            priority_score = (65 - user.get('soc', 65)) * (1 - (distance_km / 5))
                    
                    if consider_user:
                        # 用优先级分数来决定充电次序
                        potential_users.append({
                            'id': user['user_id'], 
                            'soc': user['soc'],
                            'distance': distance_km,
                            'priority': priority_score
                        })

    # 根据优先级排序 - 高优先级（低SOC和近距离）用户优先
    potential_users.sort(key=lambda u: -u.get('priority', 0))

    # 映射前N-1个最高优先级的潜在用户到行动索引1到N-1
    for i, user_info in enumerate(potential_users[:max_potential_users]):
        action_map[i + 1] = user_info['id']

    return action_map, action_space_size


def calculate_agent_reward(charger_id, action_taken, global_state, previous_state):
    """
    Calculates the reward for a charger agent based on the transition and action taken.

    Args:
        charger_id: ID of the agent.
        action_taken: The action the agent decided ('idle' or user_id).
        global_state: The state *after* the environment step.
        previous_state: The state *before* the environment step.

    Returns:
        float: The calculated reward.
    """
    reward = 0.0

    if not global_state or not previous_state or \
       'chargers' not in global_state or 'chargers' not in previous_state:
        logger.warning(f"Cannot calculate reward for {charger_id}. Invalid states provided.")
        return 0.0

    charger = next((c for c in global_state.get('chargers', []) if c['charger_id'] == charger_id), None)
    prev_charger = next((c for c in previous_state.get('chargers', []) if c['charger_id'] == charger_id), None)

    if not charger or not prev_charger:
        return 0.0 # Cannot calculate reward if charger info is missing

    # --- Reward Components ----

    # 1. Successful Assignment Reward:
    if action_taken != 'idle' and charger.get('current_user') == action_taken and prev_charger.get('status') == 'available':
        # Use .get() for current_price
        current_price = global_state.get('current_price', 0.8)
        reward += current_price * 0.6

    # 2. Grid Friendliness Reward/Penalty:
    if charger.get('status') == 'occupied':
        try:
            # Use .get() for timestamp
            timestamp_str = global_state.get('timestamp')
            if timestamp_str:
                hour = datetime.fromisoformat(timestamp_str).hour
                # Use .get() for grid_status and its sub-keys
                grid_status = global_state.get('grid_status', {})
                peak_hours = grid_status.get('peak_hours', [7, 8, 9, 10, 18, 19, 20, 21])
                valley_hours = grid_status.get('valley_hours', [0, 1, 2, 3, 4, 5])
                renewable_ratio = grid_status.get('renewable_ratio', 0)

                if hour in peak_hours:
                    reward -= 0.5
                elif hour in valley_hours:
                    reward += 0.3
                elif renewable_ratio > 50:
                    reward += 0.2
            else:
                 logger.warning("Timestamp missing for grid reward calculation")
        except (ValueError, TypeError):
            logger.warning(f"Invalid timestamp for grid reward calculation: {timestamp_str}")

    # 3. Idle Penalty:
    if action_taken == 'idle' and prev_charger.get('status') == 'available':
        # Pass previous_state to create_dynamic_action_map
        prev_action_map, _ = create_dynamic_action_map(charger_id, previous_state)
        if len(prev_action_map) > 1:
            reward -= 0.1

    # 4. Failure Penalty:
    if charger.get('status') == 'failure' and prev_charger.get('status') != 'failure':
        reward -= 2.0

    return float(reward)

# Placeholder for MARL Q-learning logic
class MARLSystem:
    def __init__(self, num_chargers, action_space_size, learning_rate, discount_factor, exploration_rate, q_table_path):
        self.num_chargers = num_chargers
        self.action_space_size = action_space_size
        self.lr = learning_rate
        self.gamma = discount_factor
        self.epsilon = exploration_rate
        self.q_table_path = q_table_path
        self.q_tables = {} # charger_id -> state_representation -> action -> Q-value
        logger.info(f"MARLSystem initialized for {num_chargers} chargers with action_space_size={action_space_size}")

        # Attempt to load existing Q-tables
        self.load_q_tables()

        # Check if Q-tables is empty, and if so, initialize with optimistic values to encourage exploration
        if not self.q_tables:
            logger.info("Initializing new Q-tables with optimistic initial values to encourage exploration")
            self._initialize_q_tables_with_bias()

    def _initialize_q_tables_with_bias(self):
        """Initialize Q-tables with a bias toward taking non-idle actions."""
        for charger_id in range(1, self.num_chargers+1):
            charger_key = f"CHARGER_{charger_id:04d}"
            self.q_tables[charger_key] = {}
            
            # Create some default state representations that will encourage exploration
            # For example, combinations of hour, load, renewables, and queue length
            default_states = [
                (hour, load, ren, queue) 
                for hour in [0, 6, 12, 18]  # Sample hours
                for load in [0, 2, 4]      # Load categories
                for ren in [0, 2, 4]       # Renewable categories  
                for queue in [0, 1, 2]     # Queue lengths
            ]
            
            for state_repr in default_states:
                self.q_tables[charger_key][state_repr] = {}
                for action in range(self.action_space_size):
                    if action == 0:  # idle action
                        self.q_tables[charger_key][state_repr][action] = 0.1  # Lower initial value
                    else:  # charging actions
                        self.q_tables[charger_key][state_repr][action] = 0.5  # Higher initial value to encourage exploration
        
        logger.info(f"Successfully initialized Q-tables with bias for {len(self.q_tables)} chargers")

    def _get_state_representation(self, state, charger_id):
        # Placeholder: Convert global state + charger_id to a hashable representation for Q-table lookup
        # This MUST be consistent!
        # Example: (hour, grid_load_category, renewable_category, charger_queue_length)
        try:
            timestamp = datetime.fromisoformat(state.get("timestamp", ""))
            hour = timestamp.hour
        except ValueError:
            hour = 0 # Default hour if timestamp is invalid

        grid_load = state.get('grid_status', {}).get('grid_load', 50)
        grid_load_cat = int(grid_load // 20) # Categorize load (0-19, 20-39, ...)

        renew_ratio = state.get('grid_status', {}).get('renewable_ratio', 0)
        renew_cat = int(renew_ratio // 20) # Categorize renewables

        charger = next((c for c in state.get('chargers', []) if c.get('charger_id') == charger_id), None)
        queue_len = len(charger.get('queue', [])) if charger else 0

        return (hour, grid_load_cat, renew_cat, queue_len)

    def choose_actions(self, state):
        actions = {}
        chargers = state.get('chargers', [])
        logger.info(f"MARL choose_actions called with {len(chargers)} chargers")
        
        # 更低的探索率，使系统更倾向于利用已学习的知识
        actual_epsilon = self.epsilon * 0.8  # 降低探索率，更依赖已学习的经验
        
        # Count how many actions of each type we're selecting
        action_counts = {i: 0 for i in range(self.action_space_size)}
        
        for charger in chargers:
            charger_id = charger.get('charger_id')
            if not charger_id:
                continue

            # 如果充电站被占用或者失败，跳过
            if charger.get('status') in ['occupied', 'failure']:
                if charger.get('status') == 'occupied':
                    # 已经在充电的保持原状
                    actions[charger_id] = 0  # 使用idle表示保持当前充电
                    action_counts[0] = action_counts.get(0, 0) + 1
                continue

            state_repr = self._get_state_representation(state, charger_id)
            
            # Check if we have Q-values for this state
            q_values = {}
            if charger_id in self.q_tables and state_repr in self.q_tables[charger_id]:
                q_values = self.q_tables[charger_id][state_repr]
                logger.debug(f"Found Q-values for charger {charger_id}, state {state_repr}: {q_values}")
            else:
                # If no exact match, find nearest state in our Q-table
                if charger_id in self.q_tables:
                    # Simple nearest state: just pick the first one (could be improved)
                    if self.q_tables[charger_id]:
                        nearest_state = next(iter(self.q_tables[charger_id].keys()))
                        q_values = self.q_tables[charger_id][nearest_state]
                        logger.debug(f"No exact state match for {state_repr}, using nearest state {nearest_state}")
                
                if not q_values:
                    logger.debug(f"No Q-values for charger {charger_id}, state {state_repr}. Using defaults.")
                    # Initialize with stronger bias toward non-idle actions for this new state
                    q_values = {0: 0.05}  # Idle action (更低的初始值)
                    for a in range(1, self.action_space_size):
                        q_values[a] = 0.7  # Non-idle actions strongly preferred (更高的初始值)
            
            # Exploration vs Exploitation with modified bias
            if random.random() < actual_epsilon:
                # Exploration: explicitly prefer non-idle actions during exploration to kickstart learning
                if random.random() < 0.9 and self.action_space_size > 1:  # 90% chance to explore non-idle actions (提高非空闲动作的概率)
                    action = random.randint(1, self.action_space_size - 1)  # Only non-idle actions
                    logger.debug(f"Charger {charger_id}: Exploring NON-IDLE actions, chose {action}")
                else:
                    action = random.randint(0, self.action_space_size - 1)  # Any action including idle
                    logger.debug(f"Charger {charger_id}: Exploring ALL actions, chose {action}")
            else:
                # Exploitation: Choose best action from Q-table with tie-breaking in favor of charging
                if q_values:
                    # 找出最大Q值
                    max_q = max(q_values.values())
                    # 所有具有最大Q值的动作
                    best_actions = [a for a, q in q_values.items() if q == max_q]
                    
                    if len(best_actions) > 1:
                        # 如果有多个最佳动作，优先选择非空闲的动作
                        non_idle_best = [a for a in best_actions if a != 0]
                        if non_idle_best:
                            action = random.choice(non_idle_best)
                            logger.debug(f"Charger {charger_id}: Multiple best actions, prioritizing non-idle {action}")
                        else:
                            action = random.choice(best_actions)
                    else:
                        action = best_actions[0]
                    
                    logger.debug(f"Charger {charger_id}: Exploiting, chose action {action} (Q={q_values[action]:.2f})")
                else:
                    # 如果没有Q值，也偏好非空闲动作
                    if self.action_space_size > 1 and random.random() < 0.8:
                        action = random.randint(1, self.action_space_size - 1)
                        logger.debug(f"Charger {charger_id}: No Q-values, preferring non-idle action {action}")
                    else:
                        action = random.randint(0, self.action_space_size - 1)
                        logger.debug(f"Charger {charger_id}: No Q-values, random action {action}")
            
            # 检查行动是否有效 - 添加动态行动映射验证
            action_map, _ = create_dynamic_action_map(charger_id, state)
            if action not in action_map:
                # 如果选择的动作无效，则选择空闲或可用的有效动作
                valid_actions = list(action_map.keys())
                if len(valid_actions) > 1 and 0 in valid_actions:
                    # 优先选择非空闲动作
                    valid_non_idle = [a for a in valid_actions if a != 0]
                    if valid_non_idle:
                        action = random.choice(valid_non_idle)
                    else:
                        action = 0  # 如果没有有效的非空闲动作，选择空闲
                elif valid_actions:
                    action = random.choice(valid_actions)
                else:
                    action = 0  # 默认空闲
                logger.debug(f"Charger {charger_id}: Invalid action replaced with {action}")
            
            actions[charger_id] = action
            action_counts[action] = action_counts.get(action, 0) + 1
        
        # Log summary of actions chosen
        idle_count = action_counts.get(0, 0)
        non_idle_count = sum(action_counts.get(i, 0) for i in range(1, self.action_space_size))
        logger.info(f"MARL actions chosen: {len(actions)} total, {idle_count} idle, {non_idle_count} non-idle")
        return actions

    def update_q_tables(self, state, actions, rewards, next_state):
        """
        Update Q-tables based on experience tuple (state, actions, rewards, next_state)
        
        Args:
            state: Previous state where actions were taken
            actions: Dictionary of {charger_id: action_index} that was chosen
            rewards: Dictionary of rewards received after taking actions
            next_state: Resulting state after actions were taken
        """
        if not state or not actions or not next_state:
            logger.warning("update_q_tables called with empty state or actions, skipping update")
            return

        logger.debug(f"Updating Q-tables with {len(actions)} actions")
        
        # Process each charger that took an action
        update_count = 0
        for charger_id, action_index in actions.items():
            # Get state representations for each state
            prev_state_repr = self._get_state_representation(state, charger_id)
            next_state_repr = self._get_state_representation(next_state, charger_id)
            
            # Initialize Q-table entries if they don't exist
            if charger_id not in self.q_tables:
                self.q_tables[charger_id] = {}
                
            if prev_state_repr not in self.q_tables[charger_id]:
                self.q_tables[charger_id][prev_state_repr] = {a: 0.0 for a in range(self.action_space_size)}
                
            if next_state_repr not in self.q_tables[charger_id]:
                self.q_tables[charger_id][next_state_repr] = {a: 0.0 for a in range(self.action_space_size)}
            
            # Determine reward for this action
            # First try to get specific reward components
            user_satisfaction = rewards.get("user_satisfaction", 0)
            operator_profit = rewards.get("operator_profit", 0) 
            grid_friendliness = rewards.get("grid_friendliness", 0)
            
            # Use weighted reward, prioritizing profit for MARL (can be adjusted)
            reward = 0.2 * user_satisfaction + 0.5 * operator_profit + 0.3 * grid_friendliness
            
            # Alternatively, can use total reward if available
            if "total_reward" in rewards:
                reward = rewards["total_reward"]
                
            # Apply an immediate penalty for idle actions (to discourage constant idling)
            if action_index == 0:  # Idle action
                reward -= 0.1  # Small penalty for idle action
            
            # Q-learning update
            old_q_value = self.q_tables[charger_id][prev_state_repr].get(action_index, 0.0)
            
            # Get maximum Q-value in next state
            next_q_values = self.q_tables[charger_id][next_state_repr]
            max_next_q = max(next_q_values.values()) if next_q_values else 0.0
            
            # Q-learning formula: Q(s,a) = Q(s,a) + α * (r + γ * max_a' Q(s',a') - Q(s,a))
            new_q_value = old_q_value + self.lr * (reward + self.gamma * max_next_q - old_q_value)
            
            # Update Q-value
            self.q_tables[charger_id][prev_state_repr][action_index] = new_q_value
            update_count += 1
            
            # Log only significant updates to avoid excessive logging
            if abs(new_q_value - old_q_value) > 0.1:
                logger.debug(f"Q-value update - charger {charger_id}, state {prev_state_repr}, action {action_index}: {old_q_value:.3f} -> {new_q_value:.3f}, reward: {reward:.3f}")
        
        if update_count > 0:
            logger.debug(f"Updated {update_count} Q-values")
        else:
            logger.warning("No Q-values were updated - check for issues in the learning process")
            
        # Occasionally (every ~50 updates) log the size of the Q-tables
        if random.random() < 0.02:
            state_count = sum(len(states) for states in self.q_tables.values())
            logger.info(f"Q-tables size: {len(self.q_tables)} chargers, {state_count} states")
            
    def load_q_tables(self):
        if self.q_table_path and os.path.exists(self.q_table_path):
            try:
                with open(self.q_table_path, 'rb') as f:
                    loaded_tables = pickle.load(f)
                    # Basic validation: Check if it's a dict
                    if isinstance(loaded_tables, dict):
                         self.q_tables = loaded_tables
                         logger.info(f"Loaded Q-tables from {self.q_table_path}. Found {len(self.q_tables)} charger entries.")
                    else:
                         logger.error(f"Invalid format for Q-tables file {self.q_table_path}. Expected dict, got {type(loaded_tables)}. Initializing empty tables.")
                         self.q_tables = {}
            except (pickle.UnpicklingError, EOFError, ImportError, IndexError) as e:
                logger.error(f"Error unpickling Q-tables from {self.q_table_path}: {e}. Initializing empty tables.", exc_info=True)
                self.q_tables = {}
            except Exception as e:
                logger.error(f"Error loading Q-tables from {self.q_table_path}: {e}. Initializing empty tables.", exc_info=True)
                self.q_tables = {}
        else:
            logger.warning(f"Q-table file not found at {self.q_table_path}. Initializing empty Q-tables.")
            self.q_tables = {}

    def save_q_tables(self):
        if self.q_table_path:
            try:
                q_table_dir = os.path.dirname(self.q_table_path)
                if q_table_dir:
                    os.makedirs(q_table_dir, exist_ok=True)
                with open(self.q_table_path, 'wb') as f:
                    pickle.dump(self.q_tables, f)
                logger.info(f"Saved Q-tables ({len(self.q_tables)} entries) to {self.q_table_path}")
            except Exception as e:
                logger.error(f"Error saving Q-tables to {self.q_table_path}: {e}", exc_info=True)
        else:
             logger.warning("Cannot save Q-tables: q_table_path not set in config.")


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
        # Implementation of the method
        pass


class CoordinatedOperatorProfitAgent:
    def __init__(self):
        self.last_decision = {}
        self.last_reward = 0

    def make_decisions(self, state):
        # Implementation of the method
        pass


class CoordinatedGridFriendlinessAgent:
    def __init__(self):
        self.last_decision = {}
        self.last_reward = 0

    def make_decisions(self, state):
        # Implementation of the method
        pass


class CoordinatedCoordinator:
    def __init__(self):
        self.last_decision = {}
        self.last_reward = 0

    def resolve_conflicts(self, user_decisions, profit_decisions, grid_decisions, state):
        # Implementation of the method
        pass 