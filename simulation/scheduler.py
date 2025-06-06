# ev_charging_project/simulation/scheduler.py

import logging
import random
from collections import defaultdict
import math
from datetime import datetime # 需要导入 datetime 用于 MARL 辅助函数

# 导入算法模块 (使用 try-except 增加健壮性)
try:
    from algorithms import rule_based, uncoordinated
except ImportError as e:
    logging.error(f"Failed to import base algorithms: {e}", exc_info=True)
    # 定义空的 schedule 函数作为 fallback
    rule_based = type('obj', (object,), {'schedule': lambda s, c: {}})()
    uncoordinated = type('obj', (object,), {'schedule': lambda s: {}})()

# 导入 utils (如果需要)
try:
    from .utils import calculate_distance
except ImportError:
    # 如果 utils 导入失败，提供一个 fallback 或记录错误
    logging.warning("Could not import calculate_distance from simulation.utils")
    def calculate_distance(p1, p2): return 10.0 # Fallback distance

logger = logging.getLogger(__name__)

class ChargingScheduler:
    def __init__(self, config):
        """
        初始化充电调度器。

        Args:
            config (dict): 包含所有配置项的字典。
        """
        self.config = config
        # 安全地获取配置，提供默认空字典
        env_config = config.get("environment", {})
        scheduler_config = self.config.get('scheduler', {}) # Use self.config here
        if not isinstance(scheduler_config, dict):
            logger.warning("Scheduler config section not found or not a dictionary. Using default algorithm.")
            scheduler_config = {} # Default to empty dict to prevent errors

        self.scheduling_algorithm_name = scheduler_config.get('scheduling_algorithm', 'coordinated_mas') # Changed self.algorithm to self.scheduling_algorithm_name
        logger.info(f"ChargingScheduler initialized. Default algorithm from config: '{self.scheduling_algorithm_name}'")

        marl_specific_config = scheduler_config.get("marl_config", {})


        # 根据算法初始化特定系统
        self.coordinated_mas_system = None
        self.marl_system = None

        # Populate self.algorithms for simple modules
        self.algorithms = {
            "rule_based": rule_based,
            "uncoordinated": uncoordinated
            # Note: MARL and MAS are handled via their specific system instances (self.marl_system, self.coordinated_mas_system)
        }

        # Initialize systems based on the configured self.scheduling_algorithm_name
        if self.scheduling_algorithm_name == "coordinated_mas":
            logger.info("Initializing Coordinated MAS subsystem as it's the configured default...")
            try:
                from algorithms.coordinated_mas import MultiAgentSystem
                self.coordinated_mas_system = MultiAgentSystem()
                self.coordinated_mas_system.config = self.config # Pass the main config to MAS
                if hasattr(self.coordinated_mas_system, 'coordinator') and hasattr(self.coordinated_mas_system.coordinator, 'set_weights'):
                    coordinator_weights = scheduler_config.get('optimization_weights', {})
                    if coordinator_weights:
                        self.coordinated_mas_system.coordinator.set_weights(coordinator_weights)
                logger.info("Coordinated MAS subsystem initialized.")
            except ImportError:
                 logger.error("Could not import MultiAgentSystem from algorithms.coordinated_mas.")
                 # No change to self.scheduling_algorithm_name here, error will be caught when trying to use it
            except Exception as e:
                logger.error(f"Failed to initialize Coordinated MAS: {e}", exc_info=True)

        elif self.scheduling_algorithm_name == "marl":
            logger.info("Initializing MARL subsystem as it's the configured default...")
            try:
                from algorithms.marl import MARLSystem
                # 获取充电桩数量，处理可能的缺失
                num_chargers = env_config.get("charger_count")
                if num_chargers is None:
                    stations = env_config.get("station_count", 20)
                    per_station = env_config.get("chargers_per_station", 10)
                    num_chargers = stations * per_station
                    logger.warning(f"env_config['charger_count'] not found, calculated as {num_chargers}")

                self.marl_system = MARLSystem(
                     num_chargers=num_chargers,
                     action_space_size=marl_specific_config.get("action_space_size", 6),
                     learning_rate=marl_specific_config.get("learning_rate", 0.01),
                     discount_factor=marl_specific_config.get("discount_factor", 0.95),
                     exploration_rate=marl_specific_config.get("exploration_rate", 0.1),
                     q_table_path=marl_specific_config.get("q_table_path", None)
                 )
                logger.info("MARL subsystem initialized.")
            except ImportError:
                 logger.error("Could not import MARLSystem from algorithms.marl.")
                 # No change to self.scheduling_algorithm_name here
            except Exception as e:
                logger.error(f"Failed to initialize MARL system: {e}", exc_info=True)


    def make_scheduling_decision(self, current_state, manual_decisions=None, grid_preferences=None): # Renamed state to current_state for clarity
        """根据配置的算法进行调度决策，支持手动决策优先和电网偏好"""
        decisions = {}
        # logger.debug(f"Making decision using algorithm: {self.scheduling_algorithm_name}") # Now uses self.scheduling_algorithm_name

        if grid_preferences is None:
            grid_preferences = {}
        logger.info(f"Scheduler received grid_preferences: {grid_preferences}")

        # current_strategy_key is derived from grid_preferences
        current_strategy_key = grid_preferences.get("charging_strategy")

        # effective_algo_name is determined based on current_strategy_key and self.scheduling_algorithm_name (base from config)
        effective_algo_name = self.scheduling_algorithm_name
        operational_mode = None

        if current_strategy_key == "uncoordinated":
            effective_algo_name = "uncoordinated"
            # operational_mode remains None
            logger.info(f"UI Strategy: '{current_strategy_key}'. Effective Algo: Uncoordinated.")
        elif current_strategy_key == "smart_charging_v1g":
            if self.scheduling_algorithm_name == "coordinated_mas": # Only apply V1G mode if base is MAS
                effective_algo_name = "coordinated_mas"
                operational_mode = 'v1g'
                logger.info(f"UI Strategy: '{current_strategy_key}'. Effective Algo: CoordinatedMAS in 'v1g' mode.")
            elif self.scheduling_algorithm_name == "marl": # MARL might also support modes
                effective_algo_name = "marl"
                operational_mode = 'v1g' # Assuming MARL agent can interpret this
                logger.info(f"UI Strategy: '{current_strategy_key}'. Effective Algo: MARL in 'v1g' mode.")
            else: # Base algo is rule_based or uncoordinated itself
                logger.warning(f"UI Strategy '{current_strategy_key}' selected, but base algorithm '{self.scheduling_algorithm_name}' doesn't support distinct V1G mode. Using base algorithm '{effective_algo_name}' behavior.")
        elif current_strategy_key == "v2g_active":
            if self.scheduling_algorithm_name == "coordinated_mas":
                effective_algo_name = "coordinated_mas"
                operational_mode = 'v2g'
                logger.info(f"UI Strategy: '{current_strategy_key}'. Effective Algo: CoordinatedMAS in 'v2g' mode.")
            elif self.scheduling_algorithm_name == "marl":
                effective_algo_name = "marl"
                operational_mode = 'v2g'
                logger.info(f"UI Strategy: '{current_strategy_key}'. Effective Algo: MARL in 'v2g' mode.")
            else:
                logger.warning(f"UI Strategy '{current_strategy_key}' selected, but base algorithm '{self.scheduling_algorithm_name}' doesn't support distinct V2G mode. Using base algorithm '{effective_algo_name}' behavior.")
        else: # No specific UI strategy, or unknown key
            logger.info(f"No specific UI strategy ('{current_strategy_key}') or unknown. Effective Algo: {effective_algo_name} (from config).")
            # If default is MAS, ensure its operational mode is its configured/current default
            if effective_algo_name == "coordinated_mas" and self.coordinated_mas_system and hasattr(self.coordinated_mas_system, 'operational_mode'):
                operational_mode = self.coordinated_mas_system.operational_mode # Use MAS's current/default
                logger.info(f"CoordinatedMAS will operate in its current/default mode: '{operational_mode}'.")
            # Similar logic could be applied if MARL had a default settable mode.


        # Get the algorithm module or system instance
        algo_module_or_system = None
        if effective_algo_name == "coordinated_mas":
            algo_module_or_system = self.coordinated_mas_system
        elif effective_algo_name == "marl":
             algo_module_or_system = self.marl_system # Assuming marl_system instance exists
        else: # rule_based, uncoordinated, or other simple modules
            algo_module_or_system = self.algorithms.get(effective_algo_name)


        if not algo_module_or_system:
            logger.error(f"Algorithm module/system for '{effective_algo_name}' not found. Defaulting to empty decisions.")
            return {}

        # Set operational mode if applicable (primarily for MAS)
        if operational_mode and hasattr(algo_module_or_system, 'set_operational_mode'):
            algo_module_or_system.set_operational_mode(operational_mode)
        elif operational_mode: # Mode specified but algo doesn't support setting it
            logger.warning(f"Algorithm '{effective_algo_name}' selected for mode '{operational_mode}' but has no 'set_operational_mode' method.")


        # Log other preferences being passed down (already present in previous version)
        priority = grid_preferences.get("charging_priority", "Balanced")
        max_ev_load = grid_preferences.get("max_ev_fleet_load_mw", float('inf')) # Already correctly logged
        logger.info(f"Scheduler passing down: charging_priority='{priority}', max_ev_fleet_load_mw={max_ev_load} to '{effective_algo_name}'")

        if not current_state or not isinstance(current_state, dict): # Use current_state
            logger.error("Scheduler received invalid current_state")
            return decisions

        try:
            # 优先应用手动决策
            if manual_decisions and isinstance(manual_decisions, dict):
                logger.info(f"Applying manual decisions: {manual_decisions}") # This part seems fine
                # The decisions.update(manual_decisions) was removed in a previous diff, ensure it's handled or re-added if needed
                # The logic for validating and applying manual_decisions should be here, before algo_decisions.
                # Based on previous diff, it seems manual_decisions are handled to create 'decisions',
                # and algo_decisions are only sought if 'decisions' is empty. This is correct.
                # The provided search block for this change started *after* manual_decision handling.
                # The key is that manual_decisions processing should correctly populate 'decisions'.
                # Re-inserting the manual decision processing from the original file snippet if it was lost.

                # --- Copied from existing logic for manual decision handling ---
                users = {u.get('user_id'): u for u in current_state.get('users', []) if isinstance(u, dict)}
                chargers = {c.get('charger_id'): c for c in current_state.get('chargers', []) if isinstance(c, dict)}
                valid_manual_decisions = {}
                for user_id, charger_id in manual_decisions.items():
                    if user_id in users and charger_id in chargers:
                        user = users[user_id]
                        charger = chargers[charger_id]
                        if True:
                            if charger.get('status') != 'failure':
                                valid_manual_decisions[user_id] = charger_id
                                current_status = user.get('status')
                                if current_status == 'charging':
                                    user['status'] = 'idle'; user['target_charger'] = None; user['needs_charge_decision'] = True
                                    for cid, c_obj in chargers.items():
                                        if c_obj.get('current_user') == user_id: c_obj['current_user'] = None; c_obj['status'] = 'available'; break
                                elif current_status == 'waiting':
                                    for cid, c_obj in chargers.items():
                                        if user_id in c_obj.get('queue', []): c_obj['queue'].remove(user_id); break
                                    user['status'] = 'idle'; user['target_charger'] = None; user['needs_charge_decision'] = True
                                user['manual_decision'] = True; user['manual_decision_locked'] = True;
                                user['force_target_charger'] = True; user['manual_decision_override'] = True;
                decisions.update(valid_manual_decisions) # Apply valid manual decisions
                # --- End copied manual decision handling ---
                
                # 验证手动决策的有效性
                users = {u.get('user_id'): u for u in state.get('users', []) if isinstance(u, dict)}
                chargers = {c.get('charger_id'): c for c in state.get('chargers', []) if isinstance(c, dict)}
                
                valid_manual_decisions = {}
                for user_id, charger_id in manual_decisions.items():
                    if user_id in users and charger_id in chargers:
                        user = users[user_id]
                        charger = chargers[charger_id]
                        
                        # 手动决策强制执行：无论用户当前状态如何都接受
                        if True:  # 移除状态限制，允许所有状态的用户接受手动决策
                            if charger.get('status') != 'failure':
                                valid_manual_decisions[user_id] = charger_id
                                
                                # 处理正在充电的用户：强制中断当前充电
                                current_status = user.get('status')
                                if current_status == 'charging':
                                    logger.info(f"=== FORCING CHARGING USER TO SWITCH CHARGERS ===")
                                    logger.info(f"User {user_id} currently charging, will be forced to switch to {charger_id}")
                                    
                                    # 强制中断当前充电，设置为需要重新路由
                                    user['status'] = 'idle'
                                    user['target_charger'] = None
                                    user['needs_charge_decision'] = True
                                    
                                    # 清除当前充电桩的用户分配
                                    current_charger_id = None
                                    for cid, c in chargers.items():
                                        if c.get('current_user') == user_id:
                                            current_charger_id = cid
                                            c['current_user'] = None
                                            c['status'] = 'available'
                                            logger.info(f"Released user {user_id} from charger {cid}")
                                            break
                                
                                elif current_status == 'waiting':
                                    logger.info(f"=== FORCING WAITING USER TO SWITCH CHARGERS ===")
                                    logger.info(f"User {user_id} currently waiting, will be forced to switch to {charger_id}")
                                    
                                    # 从当前等待队列中移除
                                    for cid, c in chargers.items():
                                        if user_id in c.get('queue', []):
                                            c['queue'].remove(user_id)
                                            logger.info(f"Removed user {user_id} from queue of charger {cid}")
                                            break
                                    
                                    # 设置为需要重新路由
                                    user['status'] = 'idle'
                                    user['target_charger'] = None
                                    user['needs_charge_decision'] = True
                                
                                # 标记为手动决策并强制锁定到目标充电桩
                                user['manual_decision'] = True
                                user['manual_decision_locked'] = True  # 锁定到特定充电桩
                                user['force_target_charger'] = True   # 强制使用目标充电桩
                                user['manual_decision_override'] = True  # 标记为强制覆盖决策
                                
                                # 详细记录手动决策信息
                                queue_size = len(charger.get('queue', []))
                                queue_capacity = charger.get('queue_capacity', 5)
                                logger.info(f"=== MANUAL DECISION FORCE ACCEPTED ===")
                                logger.info(f"User {user_id} -> Charger {charger_id} (FORCE LOCKED)")
                                logger.info(f"Previous status: {current_status} -> Now: {user.get('status')}")
                                logger.info(f"Target charger status: {charger.get('status')}")
                                logger.info(f"Target queue: {queue_size}/{queue_capacity}")
                                logger.info(f"User FORCE LOCKED - will override any system allocation")
                                
                                if queue_size >= queue_capacity:
                                    logger.info(f"Manual decision accepted despite full queue - user will wait")
                            else:
                                logger.warning(f"Manual decision rejected: Charger {charger_id} is in failure status")
                    else:
                        logger.warning(f"Manual decision rejected: User {user_id} or Charger {charger_id} not found in current state")
                
                decisions = valid_manual_decisions

            # 获取已锁定的手动决策用户列表
            locked_manual_users = set()
            if state and state.get('users'):
                for user in state['users']:
                    if isinstance(user, dict) and user.get('manual_decision_locked'):
                        locked_manual_users.add(user.get('user_id'))
            
            # 如果没有手动决策或手动决策不足，使用算法补充
            if len(decisions) == 0: # Only apply algo if no manual decisions overrode everything
                if algo_module_or_system:
                    try:
                        if hasattr(algo_module_or_system, 'make_decisions'): # For MAS-like objects
                            algo_decisions = algo_module_or_system.make_decisions(state, manual_decisions, grid_preferences)
                        elif hasattr(algo_module_or_system, 'schedule'): # For simple algorithm modules
                            # Standardized call: state, config, manual_decisions, grid_preferences
                            algo_decisions = algo_module_or_system.schedule(current_state, self.config, manual_decisions, grid_preferences)
                        # MARL specific handling
                        elif effective_algo_name == "marl" and self.marl_system:
                             charger_action_maps = {}
                             if current_state.get("chargers"):
                                 for charger in current_state["chargers"]:
                                     charger_id = charger.get("charger_id")
                                     if charger_id and charger.get("status") != "failure":
                                         action_map, action_size = self._create_dynamic_action_map(charger_id, current_state)
                                         charger_action_maps[charger_id] = {"map": action_map, "size": action_size}
                             marl_actions = self.marl_system.choose_actions(current_state)
                             algo_decisions = self._convert_marl_actions_to_decisions(marl_actions, current_state, charger_action_maps)
                        else:
                            logger.error(f"Algorithm module/system '{effective_algo_name}' has no recognized decision-making method.")
                            algo_decisions = {}
                    except Exception as e_algo:
                        logger.error(f"Error executing algorithm {effective_algo_name}: {e_algo}", exc_info=True)
                        algo_decisions = {}
                else:
                    logger.error(f"Algorithm module/system for {effective_algo_name} was None before attempting to make decisions (this should have been caught earlier).")
                    algo_decisions = {}
                    if state.get("chargers"):
                        for charger in state["chargers"]:
                            charger_id = charger.get("charger_id")
                            if charger_id and charger.get("status") != "failure":
                                action_map, action_size = self._create_dynamic_action_map(charger_id, state)
                                charger_action_maps[charger_id] = {"map": action_map, "size": action_size}
                    
                    marl_actions = self.marl_system.choose_actions(state)
                    algo_decisions = self._convert_marl_actions_to_decisions(marl_actions, state, charger_action_maps)
                # else: # OLD LOGIC BLOCK
                #     logger.warning(f"Algorithm '{self.algorithm}' not recognized. Using rule-based fallback.")
                #     algo_decisions = rule_based.schedule(state, self.config)
                
                # 过滤掉已锁定的手动决策用户，防止算法重新分配
                filtered_decisions = {}
                for user_id, charger_id in algo_decisions.items():
                    if user_id not in locked_manual_users:
                        filtered_decisions[user_id] = charger_id
                    else:
                        logger.info(f"Algorithm decision for locked manual user {user_id} ignored - user locked to specific charger")
                
                decisions = filtered_decisions

        except Exception as e:
            logger.error(f"Error during scheduling with {effective_algorithm_name}: {e}", exc_info=True) # Use effective_algorithm_name
            logger.warning("Falling back to rule-based scheduling due to error.")
            try:
                # Ensure rule_based is imported or available as a fallback module
                from algorithms import rule_based as fallback_rule_based_module # Ensure this import is valid
                decisions = fallback_rule_based_module.schedule(current_state, self.config, grid_preferences) # Pass current_state
            except Exception as fallback_e:
                logger.error(f"Error during fallback rule-based scheduling: {fallback_e}", exc_info=True)
                decisions = {}

        logger.info(f"Scheduler ({effective_algo_name}) made {len(decisions)} assignments.")
        return decisions

    def _get_configured_algorithm_module(self):
        """Helper to get the module instance based on self.scheduling_algorithm_name from config."""
        # This method is primarily for simple modules listed in self.algorithms
        # MAS and MARL are typically handled via their dedicated system instances.
        if self.scheduling_algorithm_name in self.algorithms:
            return self.algorithms[self.scheduling_algorithm_name]
        elif self.scheduling_algorithm_name == "coordinated_mas" and self.coordinated_mas_system:
             return self.coordinated_mas_system # Should be handled before calling this ideally
        elif self.scheduling_algorithm_name == "marl" and self.marl_system:
             return self.marl_system # Should be handled before calling this ideally
        logger.error(f"Configured algorithm {self.scheduling_algorithm_name} module not found in self.algorithms or as a system.")
        return None
        
    # --- learn, load_q_tables, save_q_tables ---
    def learn(self, state, actions, rewards, next_state): # Use 'state' consistent with other methods if it's current_state
        """如果使用 MARL，则调用其学习方法"""
        if self.algorithm == "marl" and self.marl_system:
            try:
                # TODO: 确认 MARLSystem.update_q_tables 需要的 actions 格式。
                # 假设它需要原始的 {charger_id: action_index} 映射。
                # 目前传入的是 decisions {user_id: charger_id}，这可能不正确。
                # 需要在 run_simulation 循环中存储 marl_actions 并传递到这里，
                # 或者让 MARLSystem.update_q_tables 能处理 decisions。
                logger.debug("Calling MARL learn...")
                self.marl_system.update_q_tables(state, actions, rewards, next_state)
            except Exception as e:
                logger.error(f"Error during MARL learning step: {e}", exc_info=True)

    def load_q_tables(self):
        """如果使用 MARL，加载 Q 表"""
        if self.algorithm == "marl" and self.marl_system:
            logger.info("Scheduler attempting to load MARL Q-tables...")
            self.marl_system.load_q_tables()

    def save_q_tables(self):
        """如果使用 MARL，保存 Q 表"""
        if self.algorithm == "marl" and self.marl_system:
            logger.info("Scheduler attempting to save MARL Q-tables...")
            self.marl_system.save_q_tables()

    # --- MARL 辅助方法 ---
    def _create_dynamic_action_map(self, charger_id, state):
        """
        为 MARL 创建动态动作映射。
        Index 0 is 'idle', subsequent indices map to potential user IDs.
        """
        # 从配置中获取 MARL 参数
        marl_config = self.config.get("scheduler", {}).get("marl_config", {})
        action_space_size = marl_config.get("action_space_size", 6) # Default to 6
        max_potential_users = action_space_size - 1 # Number of users to map

        # --- 获取可配置的候选用户选择参数 ---
        MAX_DISTANCE_SQ = marl_config.get("marl_candidate_max_dist_sq", 0.15**2) # ~20km radius
        W_SOC = marl_config.get("marl_priority_w_soc", 0.5)
        W_DIST = marl_config.get("marl_priority_w_dist", 0.4)
        W_URGENCY = marl_config.get("marl_priority_w_urgency", 0.1)

        action_map = {0: 'idle'} # Action 0 is always idle
        chargers = state.get('chargers', [])
        users = state.get('users', [])
        charger = next((c for c in chargers if c.get('charger_id') == charger_id), None)

        if not charger or charger.get('status') == 'failure':
            # logger.debug(f"Charger {charger_id} not found or failed, only idle action.")
            return action_map, action_space_size # Only 'idle' is possible

        potential_users = []
        charger_pos = charger.get('position', {}) # Default to empty dict if missing

        for user in users:
            user_id = user.get('user_id')
            soc = user.get('soc', 100)
            status = user.get('status', 'unknown')
            user_profile = user.get('user_profile', 'flexible')
            needs_charge_flag = user.get('needs_charge_decision', False)

            if not user_id: continue

            # --- 筛选逻辑: 寻找主动寻求充电的用户 ---
            is_actively_seeking = False
            charge_threshold = 40 # 基础阈值，可配置
            if user_profile == 'anxious': charge_threshold = 50
            elif user_profile == 'economic': charge_threshold = 30

            is_low_soc = soc < charge_threshold

            # 满足以下条件之一视为寻求充电:
            # 1. 用户明确标记需要决策
            if needs_charge_flag and status not in ['charging', 'waiting']:
                 is_actively_seeking = True
            # 2. 用户空闲或随机旅行，且电量低于阈值
            elif status in ['idle', 'traveling'] and user.get('target_charger') is None and is_low_soc:
                 is_actively_seeking = True

            if not is_actively_seeking:
                continue # 跳过不寻求充电的用户
            # --- 结束筛选 ---

            user_pos = user.get('current_position',{})
            # 检查坐标有效性
            if isinstance(user_pos.get('lat'), (int, float)) and isinstance(user_pos.get('lng'), (int, float)) and \
               isinstance(charger_pos.get('lat'), (int, float)) and isinstance(charger_pos.get('lng'), (int, float)):

                dist_sq = (user_pos['lat'] - charger_pos['lat'])**2 + (user_pos['lng'] - charger_pos['lng'])**2

                if dist_sq < MAX_DISTANCE_SQ:
                    distance = math.sqrt(dist_sq) * 111 # Approx km
                    # 计算紧迫度 (0 to 1, higher is more urgent)
                    urgency = max(0, (charge_threshold - soc)) / charge_threshold if charge_threshold > 0 else 0

                    # --- 计算优先级分数 ---
                    normalized_distance = min(1.0, math.sqrt(dist_sq) / math.sqrt(MAX_DISTANCE_SQ)) if MAX_DISTANCE_SQ > 0 else 0
                    priority_score = (
                        W_SOC * (1.0 - soc / 100.0) +      # 低 SOC 贡献正分
                        W_DIST * (1.0 - normalized_distance) + # 近距离贡献正分
                        W_URGENCY * urgency                 # 紧迫度贡献正分
                    )
                    # --- 结束评分 ---

                    potential_users.append({
                            'id': user_id,
                            'priority': priority_score
                    })
                    # logger.debug(f"User {user_id} potential for {charger_id}. Priority: {priority_score:.3f}")
            # else: logger.warning(f"Invalid coordinates for distance calc: User {user_id} or Charger {charger_id}")

        # 按优先级排序 (高优先级在前)
        potential_users.sort(key=lambda u: -u['priority'])
        # logger.debug(f"Found {len(potential_users)} potential users for {charger_id}.")

        # 映射优先级最高的用户到动作索引
        assigned_users_count = 0
        for i, user_info in enumerate(potential_users):
             if assigned_users_count < max_potential_users:
                  action_map[i + 1] = user_info['id']
                  assigned_users_count += 1
             else:
                  break # Stop once we've filled the action space slots

        # logger.debug(f"Final action map for {charger_id}: {action_map}")
        return action_map, action_space_size


    def _convert_marl_actions_to_decisions(self, agent_actions, state, charger_action_maps):
        """
        将 MARL 智能体选择的动作 {charger_id: action_index}
        转换为充电分配决策 {user_id: charger_id}。
        """
        decisions = {}
        assigned_users = set() # 跟踪已分配用户，防止重复

        if not isinstance(agent_actions, dict):
             logger.error(f"_convert_marl_actions_to_decisions received invalid agent_actions type: {type(agent_actions)}")
             return {}

        logger.debug(f"Converting MARL actions: {agent_actions}")

        # 遍历每个充电站智能体选择的动作
        for charger_id, action_index in agent_actions.items():
            # Action 0 总是表示'idle'(不分配)
            if action_index == 0:
                # logger.debug(f"Charger {charger_id} chose 'idle' (action 0)")
                continue

            # --- 使用预生成的动作映射 ---
            map_data = charger_action_maps.get(charger_id)
            if not map_data:
                logger.warning(f"No pre-generated action map found for charger {charger_id}. Cannot convert action {action_index}. Skipping.")
                continue
            action_map = map_data.get("map")
            if not action_map:
                logger.warning(f"Invalid action map data for charger {charger_id}. Skipping.")
                continue

            # 在提供的映射中查找对应于所选 action_index 的 user_id
            user_id_to_assign = action_map.get(action_index)

            if user_id_to_assign and user_id_to_assign != 'idle':
                # 检查这个用户是否已经被另一个充电站分配
                if user_id_to_assign not in assigned_users:
                    # 验证用户是否仍然存在于状态中 (可选但更健壮)
                    user_exists = any(u.get('user_id') == user_id_to_assign for u in state.get('users', []))
                    if user_exists:
                        decisions[user_id_to_assign] = charger_id
                        assigned_users.add(user_id_to_assign)
                        logger.debug(f"MARL decision: Assign user {user_id_to_assign} to charger {charger_id} (from action index {action_index})")
                    else:
                         logger.warning(f"MARL action {action_index} mapped to user {user_id_to_assign} but user not found in current state. Skipping.")
                else:
                    # 冲突: 用户已被分配。记录日志。
                    logger.warning(f"MARL conflict: User {user_id_to_assign} was already assigned. Charger {charger_id} also selected this user (action index {action_index}). Ignoring second assignment.")
            else:
                # 所选动作索引可能不对应任何用户
                logger.debug(f"Charger {charger_id} chose action index {action_index}, but no valid user found in its action map: {action_map}")

        # --- 可选的应急分配逻辑 ---
        # (如果需要，可以从原 app.py 复制粘贴应急分配逻辑到这里)
        # if not decisions and active_count > 20: ...

        if not decisions:
            logger.warning("MARL action conversion resulted in zero assignments.")
        else:
            logger.info(f"Converted MARL actions to {len(decisions)} assignments.")
        return decisions