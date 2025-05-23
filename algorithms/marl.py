# ev_charging_project/algorithms/marl.py
# (内容来自原 marl_components.py, 并移除末尾重复类)

import numpy as np
import random
import pickle
import os
from collections import defaultdict
import logging
from datetime import datetime
import math
# 导入重构后的工具函数
from simulation.utils import calculate_distance # 确保导入路径正确

logger = logging.getLogger("MARL")

class MARLAgent:
    """Represents a single agent (e.g., a charging station) using Q-learning."""
    def __init__(self, agent_id, action_space_size, learning_rate=0.1, discount_factor=0.9, exploration_rate=0.1):
        self.agent_id = agent_id
        self.action_space_size = action_space_size
        self.lr = learning_rate
        self.gamma = discount_factor
        self.epsilon = exploration_rate
        self.q_table = defaultdict(lambda: np.zeros(self.action_space_size))

    def choose_action(self, state, current_action_map):
        """Choose action using epsilon-greedy strategy based on the current valid actions."""
        state_str = self._state_to_string(state)

        # Ensure Q-table entry exists and has the correct size
        if len(self.q_table[state_str]) != self.action_space_size:
            logger.warning(f"Q-table size mismatch for agent {self.agent_id} state {state_str}. Expected {self.action_space_size}, got {len(self.q_table[state_str])}. Resetting.")
            self.q_table[state_str] = np.zeros(self.action_space_size)

        valid_action_indices = list(current_action_map.keys())
        if not valid_action_indices:
            logger.warning(f"Agent {self.agent_id} has no valid actions in state {state_str}.")
            return current_action_map.get(0, 'idle'), 0 # Default to idle

        if random.uniform(0, 1) < self.epsilon:
            # Explore
            action_index = random.choice(valid_action_indices)
        else:
            # Exploit
            q_values = self.q_table[state_str]
            valid_q_values = {idx: q_values[idx] for idx in valid_action_indices}
            if not valid_q_values:
                 action_index = random.choice(valid_action_indices)
            else:
                max_q = max(valid_q_values.values())
                best_action_indices = [idx for idx, q in valid_q_values.items() if q == max_q]
                action_index = random.choice(best_action_indices)

        chosen_action = current_action_map.get(action_index, 'idle') # Safely get action
        return chosen_action, action_index

    def update_q_table(self, state, action_index, reward, next_state):
        """Update Q-value for the state-action pair."""
        if not (0 <= action_index < self.action_space_size):
            logger.error(f"Invalid action_index {action_index} for agent {self.agent_id} (size {self.action_space_size}). State: {state}")
            return

        state_str = self._state_to_string(state)
        next_state_str = self._state_to_string(next_state)

        # Ensure next state entry exists
        if len(self.q_table[next_state_str]) != self.action_space_size:
             self.q_table[next_state_str] = np.zeros(self.action_space_size)

        old_value = self.q_table[state_str][action_index]
        next_max = np.max(self.q_table[next_state_str])

        # Q-learning formula
        new_value = old_value + self.lr * (reward + self.gamma * next_max - old_value)
        self.q_table[state_str][action_index] = new_value

    def _state_to_string(self, state):
        """Convert state dictionary to a hashable string."""
        if not isinstance(state, dict): return str(state)
        items = sorted(state.items())
        return str(items)

    def load_q_table(self, file_path):
        """Load Q-table from a file."""
        if os.path.exists(file_path):
            try:
                with open(file_path, 'rb') as f:
                    loaded_q_dict = pickle.load(f)
                    self.q_table = defaultdict(lambda: np.zeros(self.action_space_size))
                    for state_key, q_values in loaded_q_dict.items():
                        if len(q_values) == self.action_space_size:
                            self.q_table[state_key] = np.array(q_values)
                        else:
                            logger.warning(f"Size mismatch loading Q-table for agent {self.agent_id}, state {state_key}. Skipping state.")
                logger.info(f"Q-table loaded for agent {self.agent_id} from {file_path}")
            except Exception as e:
                logger.error(f"Error loading Q-table for agent {self.agent_id} from {file_path}: {e}", exc_info=True)
        else:
            logger.warning(f"Q-table file not found for agent {self.agent_id} at {file_path}.")

    def save_q_table(self, file_path):
        """Save Q-table to a file."""
        try:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, 'wb') as f:
                # Convert defaultdict to regular dict for saving
                q_dict_to_save = dict(self.q_table)
                pickle.dump(q_dict_to_save, f)
            logger.info(f"Q-table saved for agent {self.agent_id} to {file_path}")
        except Exception as e:
             logger.error(f"Error saving Q-table for agent {self.agent_id} to {file_path}: {e}", exc_info=True)


# --- Helper Functions for MARL (Remain associated with MARL logic) ---

def get_agent_state(charger_id, global_state):
    """Extracts the relevant state information for a specific charger agent."""
    # (基本逻辑不变，确保从 global_state 安全取值)
    if not global_state or 'chargers' not in global_state:
        logger.warning(f"Cannot get agent state for {charger_id}. Invalid global_state.")
        return {}

    charger = next((c for c in global_state.get('chargers', []) if c['charger_id'] == charger_id), None)
    if not charger: return {}

    # --- State Features ---
    status_map = {'available': 0, 'occupied': 1, 'failure': 2}
    charger_status = status_map.get(charger.get('status', 'available'), 0)
    queue_length = len(charger.get('queue', []))
    hour_of_day = 0
    try:
        timestamp_str = global_state.get('timestamp')
        if timestamp_str: hour_of_day = datetime.fromisoformat(timestamp_str).hour
    except: pass # Ignore parsing errors

    grid_status = global_state.get('grid_status', {})
    grid_load_percentage = grid_status.get('grid_load_percentage', 50)
    renewable_ratio = grid_status.get('renewable_ratio', 0)

    grid_load_cat = 0
    if grid_load_percentage > 80: grid_load_cat = 2
    elif grid_load_percentage > 60: grid_load_cat = 1

    renew_cat = 0
    if renewable_ratio > 50: renew_cat = 2
    elif renewable_ratio > 20: renew_cat = 1

    # --- Nearby Demand (Simplified) ---
    users_needing_charge = 0
    charger_pos = charger.get('position', {'lat': 0, 'lng': 0})
    nearby_radius_sq = 0.05**2 # Approx 5km radius squared
    for user in global_state.get('users', []):
        if user.get('soc', 100) < 40 and user.get('status') not in ['charging', 'waiting']:
             user_pos = user.get('current_position', {'lat': -999, 'lng': -999})
             # Use imported calculate_distance helper if needed, or keep inline calculation
             # dist_sq = (user_pos['lat'] - charger_pos['lat'])**2 + (user_pos['lng'] - charger_pos['lng'])**2
             # Simplified check:
             if abs(user_pos.get('lat', -999) - charger_pos.get('lat', 0)) < 0.05 and \
                abs(user_pos.get('lng', -999) - charger_pos.get('lng', 0)) < 0.05:
                 users_needing_charge += 1

    # --- Assemble State Dictionary ---
    state = {
        "status": charger_status,
        "queue": min(queue_length, 3),
        "hour_discrete": hour_of_day // 4, # Discretize hour
        "grid_load_cat": grid_load_cat,
        "renew_cat": renew_cat,
        "nearby_demand_cat": min(users_needing_charge, 2) # Discretize demand
    }
    return state

# Note: The `create_dynamic_action_map` function used by MARL is now defined
# within the `ChargingScheduler` class in `simulation/scheduler.py` because
# it might need access to the scheduler's config or state more easily.
# If you prefer it here, you'll need to pass `config` to it.

def calculate_agent_reward(charger_id, action_taken, global_state, previous_state):
    """Calculates the reward for a charger agent."""
    # (基本逻辑不变，确保从 global_state 和 previous_state 安全取值)
    reward = 0.0
    if not global_state or not previous_state or \
       'chargers' not in global_state or 'chargers' not in previous_state:
        return 0.0

    charger = next((c for c in global_state.get('chargers', []) if c.get('charger_id') == charger_id), None)
    prev_charger = next((c for c in previous_state.get('chargers', []) if c.get('charger_id') == charger_id), None)
    if not charger or not prev_charger: return 0.0

    grid_status = global_state.get('grid_status', {})
    current_price = grid_status.get('current_price', 0.8)
    hour = 0
    try:
        if global_state.get('timestamp'): hour = datetime.fromisoformat(global_state['timestamp']).hour
    except: pass

    # 1. Successful Assignment Reward:
    # Check if the charger is now occupied by the user it decided to take
    if action_taken != 'idle' and charger.get('status') == 'occupied' and charger.get('current_user') == action_taken and prev_charger.get('status') == 'available':
        reward += current_price * 0.7 # Slightly higher reward for successful assignment

    # 2. Grid Friendliness Reward/Penalty:
    if charger.get('status') == 'occupied':
        peak_hours = grid_status.get('peak_hours', [])
        valley_hours = grid_status.get('valley_hours', [])
        renewable_ratio = grid_status.get('renewable_ratio', 0)
        if hour in peak_hours: reward -= 0.6 # Stronger penalty for peak
        elif hour in valley_hours: reward += 0.4 # Higher reward for valley
        elif renewable_ratio > 60: reward += 0.25 # Higher threshold for renewable bonus

    # 3. Idle Penalty:
    if action_taken == 'idle' and prev_charger.get('status') == 'available':
        # Check if there *were* potential users it could have taken (requires action map from previous state)
        # Simplified: Apply small penalty if idle when grid is not stressed
         grid_load_percentage = grid_status.get('grid_load_percentage', 50)
         if grid_load_percentage < 70:
            reward -= 0.15

    # 4. Failure Penalty:
    if charger.get('status') == 'failure' and prev_charger.get('status') != 'failure':
        reward -= 3.0 # Stronger penalty for failure

    # 5. Queue Management Reward (Optional)
    # Small reward for keeping queue short?
    # queue_length = len(charger.get("queue", []))
    # if queue_length < 2: reward += 0.05

    return float(reward)


# --- MARLSystem Class ---
class MARLSystem:
    def __init__(self, num_chargers, action_space_size, learning_rate, discount_factor, exploration_rate, q_table_path):
        self.num_chargers = num_chargers
        self.action_space_size = action_space_size
        self.lr = learning_rate
        self.gamma = discount_factor
        self.epsilon = exploration_rate
        self.q_table_path = q_table_path
        # Use MARLAgent instances
        self.agents = {f"CHARGER_{i+1:04d}": MARLAgent(f"CHARGER_{i+1:04d}", action_space_size, learning_rate, discount_factor, exploration_rate)
                       for i in range(num_chargers)}
        logger.info(f"MARLSystem initialized with {len(self.agents)} agents.")
        self.load_q_tables() # Load Q-tables for all agents

    def choose_actions(self, state):
        """Get actions from all agents."""
        all_actions = {}
        chargers = state.get('chargers', [])
        logger.info(f"MARL choose_actions called for {len(chargers)} chargers")

        active_agents = 0
        idle_agents = 0

        # Need to pre-calculate action maps if agents need them (depends on MARLAgent.choose_action signature)
        # Assuming MARLAgent needs the action map passed to it.
        # We need the SCHEDULER's config here to get the action map generation parameters.
        # This is a bit awkward. A better design might pass the config into choose_actions.
        # WORKAROUND: Assume scheduler config is accessible somehow or use defaults.
        # OR: The action map logic should be internal to MARLAgent or MARLSystem.
        # Let's assume the action map is generated *outside* and passed if needed.
        # For now, let's assume MARLAgent can get its valid actions internally based on state.
        # If not, the `ChargingScheduler._create_dynamic_action_map` needs to be called here.

        for charger in chargers:
             charger_id = charger.get('charger_id')
             agent = self.agents.get(charger_id)
             if not agent:
                  logger.warning(f"No MARL agent found for charger {charger_id}. Skipping.")
                  continue

             if charger.get('status') in ['occupied', 'failure']:
                 # Agent is busy or failed, default action might be 'idle' (index 0)
                 all_actions[charger_id] = 0 # Let's represent 'no action needed' as 0
                 idle_agents += 1
                 continue

             agent_state = get_agent_state(charger_id, state) # Get state specific to this agent

             # --- How to get valid actions? ---
             # OPTION 1: Assume MARLAgent.choose_action handles it (needs state only)
             # action, action_index = agent.choose_action(agent_state, ?) # Problem: Needs action map

             # OPTION 2: Generate action map here (Requires config/scheduler logic)
             # This implies MARLSystem needs access to the scheduler's config or the function itself.
             # Let's simulate calling the function (assuming it exists globally or is passed)
             try:
                 # We need the config here! Assuming it's accessible globally or passed.
                 # If this MARLSystem instance doesn't have config, this will fail.
                 # It's better if ChargingScheduler calls this map creation.
                 # See updated logic in simulation/scheduler.py where map creation happens *before* choose_actions.
                 # Here, we'll just pass an empty map for structure.
                 _temp_map = {0:'idle'} # Placeholder - Actual map generated in scheduler
                 _chosen_action_name, action_index = agent.choose_action(agent_state, _temp_map)
                 all_actions[charger_id] = action_index
                 active_agents += 1
             except Exception as e:
                 logger.error(f"Error choosing action for agent {charger_id}: {e}", exc_info=True)
                 all_actions[charger_id] = 0 # Default to idle on error
                 idle_agents += 1


        logger.info(f"MARL actions chosen: {active_agents} active agents, {idle_agents} idle/failed.")
        # Returns a dict of {charger_id: action_index}
        return all_actions


    def update_q_tables(self, state, actions, rewards, next_state):
        """Update Q-tables for all agents based on experience."""
        # This 'rewards' might be the global reward dict. We need agent-specific rewards.
        if not state or not actions or not next_state:
            logger.warning("MARL update_q_tables received empty data. Skipping.")
            return

        logger.debug(f"Updating MARL Q-tables for {len(actions)} actions.")
        update_count = 0

        # Calculate agent-specific rewards *before* updating
        agent_rewards = {}
        previous_state_for_reward = state # Assuming 'state' is the state *before* actions were taken
        current_state_for_reward = next_state # Assuming 'next_state' is the state *after* actions were taken

        for charger_id, action_index in actions.items():
             # Find the action name (e.g., 'idle' or user_id) if needed by reward function
             # This requires the action_map from the time the action was chosen.
             # This highlights the complexity - state/action/reward alignment is crucial.
             # Let's assume `calculate_agent_reward` works with action_index or the decision.
             # The `actions` dict here likely contains the *decision* (user_id or None/idle)
             # rather than the raw action_index chosen by the agent.
             # We need clarity on what `actions` represents here.
             # Assuming `actions` is the *decision* dict {user_id: charger_id} returned by scheduler

             # Let's REVERSE the mapping to get {charger_id: user_id_or_idle}
             charger_actions_taken = defaultdict(lambda: 'idle') # Default to idle
             for user_id, assigned_charger_id in actions.items():
                  charger_actions_taken[assigned_charger_id] = user_id

             # Now calculate reward for each charger based on what it *did*
             for charger_id_reward_calc, action_name in charger_actions_taken.items():
                  agent_rewards[charger_id_reward_calc] = calculate_agent_reward(
                       charger_id_reward_calc,
                       action_name, # Pass 'idle' or the user_id assigned
                       current_state_for_reward, # State AFTER action
                       previous_state_for_reward # State BEFORE action
                  )

        # Now update agents using the calculated specific rewards
        # We need the original {charger_id: action_index} mapping here!
        # This structure is problematic. `actions` should ideally be the raw {charger_id: action_index}.
        # Let's assume `actions` IS {charger_id: action_index} for the update logic.

        if isinstance(actions, dict): # Check if actions is the expected format
            for charger_id, action_index in actions.items():
                agent = self.agents.get(charger_id)
                if not agent: continue

                agent_state = get_agent_state(charger_id, state) # State when action was chosen
                next_agent_state = get_agent_state(charger_id, next_state) # Resulting state
                reward = agent_rewards.get(charger_id, 0) # Get specific reward

                agent.update_q_table(agent_state, action_index, reward, next_agent_state)
                update_count += 1
                # Optional: Log significant updates
                # ...

        if update_count > 0: logger.debug(f"Updated Q-values for {update_count} agents.")


    def load_q_tables(self):
        """Load Q-tables for all agents."""
        logger.info(f"Loading Q-tables for {len(self.agents)} agents from path: {self.q_table_path}")
        num_loaded = 0
        # If path points to a single file containing all tables:
        if self.q_table_path and os.path.exists(self.q_table_path) and os.path.isfile(self.q_table_path):
             try:
                 with open(self.q_table_path, 'rb') as f:
                     all_q_tables = pickle.load(f)
                     if isinstance(all_q_tables, dict):
                          for agent_id, agent in self.agents.items():
                              if agent_id in all_q_tables:
                                   # Convert loaded dict back to defaultdict
                                   loaded_agent_q = all_q_tables[agent_id]
                                   agent.q_table = defaultdict(lambda: np.zeros(agent.action_space_size))
                                   for state_key, q_values in loaded_agent_q.items():
                                        if len(q_values) == agent.action_space_size:
                                             agent.q_table[state_key] = np.array(q_values)
                                        else:
                                            logger.warning(f"Size mismatch loading Q-table for agent {agent_id}, state {state_key}. Skipping.")
                                   num_loaded += 1
                          logger.info(f"Loaded Q-tables for {num_loaded} agents from single file {self.q_table_path}")
                     else:
                          logger.error(f"Invalid format in Q-table file {self.q_table_path}. Expected dict.")
             except Exception as e:
                 logger.error(f"Error loading Q-tables from {self.q_table_path}: {e}", exc_info=True)
        # If path points to a directory (load individual files)
        elif self.q_table_path and os.path.isdir(self.q_table_path):
             for agent_id, agent in self.agents.items():
                  agent_file = os.path.join(self.q_table_path, f"{agent_id}_q_table.pkl")
                  agent.load_q_table(agent_file) # Use agent's own load method
                  if os.path.exists(agent_file): num_loaded +=1
             logger.info(f"Attempted to load Q-tables for {len(self.agents)} agents from directory {self.q_table_path}. Found {num_loaded} files.")
        else:
             logger.warning(f"Q-table path '{self.q_table_path}' not found or invalid. Agents starting with empty Q-tables.")


    def save_q_tables(self):
        """Save Q-tables for all agents."""
        logger.info(f"Saving Q-tables for {len(self.agents)} agents to path: {self.q_table_path}")
        if not self.q_table_path:
            logger.error("Cannot save Q-tables: q_table_path is not set.")
            return

        # Option 1: Save all tables to a single file
        if not os.path.splitext(self.q_table_path)[1]: # Check if it looks like a directory path
             # Assume directory saving
             os.makedirs(self.q_table_path, exist_ok=True)
             num_saved = 0
             for agent_id, agent in self.agents.items():
                  agent_file = os.path.join(self.q_table_path, f"{agent_id}_q_table.pkl")
                  agent.save_q_table(agent_file)
                  num_saved +=1
             logger.info(f"Saved Q-tables for {num_saved} agents to directory {self.q_table_path}")
        else:
             # Assume single file saving
             all_q_tables_to_save = {}
             for agent_id, agent in self.agents.items():
                  # Convert defaultdict to regular dict for saving
                  all_q_tables_to_save[agent_id] = dict(agent.q_table)

             try:
                  q_table_dir = os.path.dirname(self.q_table_path)
                  if q_table_dir: os.makedirs(q_table_dir, exist_ok=True)
                  with open(self.q_table_path, 'wb') as f:
                      pickle.dump(all_q_tables_to_save, f)
                  logger.info(f"Saved all Q-tables ({len(all_q_tables_to_save)} agents) to single file {self.q_table_path}")
             except Exception as e:
                  logger.error(f"Error saving Q-tables to {self.q_table_path}: {e}", exc_info=True)

# !! IMPORTANT: Removed the duplicated MultiAgentSystem and related classes below !!
# class MultiAgentSystem: ... (REMOVED)
# class CoordinatedUserSatisfactionAgent: ... (REMOVED)
# ... etc ... (REMOVED)