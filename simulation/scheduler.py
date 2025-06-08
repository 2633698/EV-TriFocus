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
                self.coordinated_mas_system = MultiAgentSystem(main_config=self.config) # Pass main config
                # self.coordinated_mas_system.config = self.config # This line is redundant if passed in constructor
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
                     q_table_path=marl_specific_config.get("q_table_path", None),
                     marl_config=marl_specific_config # Ensure this line is present
                 )
                logger.info("MARL subsystem initialized.")
            except ImportError:
                 logger.error("Could not import MARLSystem from algorithms.marl.")
                 # No change to self.scheduling_algorithm_name here
            except Exception as e:
                logger.error(f"Failed to initialize MARL system: {e}", exc_info=True)



    def make_scheduling_decision(self, current_state, manual_decisions=None, grid_preferences=None):
        """根据配置的算法进行调度决策，支持手动决策优先和电网偏好"""
        # 初始化元数据字典，确保总有返回值
        scheduler_metadata = {
            "algorithm_used": "unknown",
            "candidate_user_count": 0
        }
        
        # 初始化决策字典
        algo_decisions = {}
        final_decisions = {}

        if grid_preferences is None:
            grid_preferences = {}
        # 日志记录可以简化，避免刷屏
        # logger.info(f"SCHEDULER: Received grid_preferences: {grid_preferences}")

        # --- 确定要使用的算法 ---
        ui_strategy = grid_preferences.get("charging_strategy")
        effective_algo_name = getattr(self, 'scheduling_algorithm_name', 'rule_based')
        operational_mode = None

        if ui_strategy == "uncoordinated":
            effective_algo_name = "uncoordinated"
        elif ui_strategy == "smart_charging_v1g":
            if self.scheduling_algorithm_name in ["coordinated_mas", "marl"]: 
                effective_algo_name = self.scheduling_algorithm_name
                operational_mode = 'v1g'
        elif ui_strategy == "v2g_active":
            if self.scheduling_algorithm_name in ["coordinated_mas", "marl"]: 
                effective_algo_name = self.scheduling_algorithm_name
                operational_mode = 'v2g'
        
        scheduler_metadata["algorithm_used"] = effective_algo_name

        # --- 获取算法模块或系统实例 ---
        algo_module_or_system = None
        if effective_algo_name == "coordinated_mas": algo_module_or_system = self.coordinated_mas_system
        elif effective_algo_name == "marl": algo_module_or_system = self.marl_system
        else: algo_module_or_system = self.algorithms.get(effective_algo_name)

        if not algo_module_or_system:
            logger.error(f"SCHEDULER: Algorithm module/system for '{effective_algo_name}' not found.")
            return {}, scheduler_metadata # 保证返回两个值

        if operational_mode and hasattr(algo_module_or_system, 'set_operational_mode'):
            algo_module_or_system.set_operational_mode(operational_mode)

        # --- 开始决策流程 ---
        try:
            # 1. 处理手动决策 (这部分逻辑是正确的，保持不变)
            validated_manual_decisions = {}
            if manual_decisions and isinstance(manual_decisions, dict):
                # ... (validation logic for manual decisions) ...
                users_map = {u.get('user_id'): u for u in current_state.get('users', []) if isinstance(u, dict)}
                chargers_map = {c.get('charger_id'): c for c in current_state.get('chargers', []) if isinstance(c, dict)}
                for user_id, charger_id in manual_decisions.items():
                    if user_id in users_map and charger_id in chargers_map:
                         validated_manual_decisions[user_id] = charger_id

            # 2. 调用算法模块获取决策和元数据
            if hasattr(algo_module_or_system, 'schedule'):
                # --- START OF FIX ---
                # 正确解包算法返回的元组
                algo_decisions, algo_metadata = algo_module_or_system.schedule(
                    current_state, self.config, manual_decisions, grid_preferences
                )
                # 更新我们的主元数据
                scheduler_metadata.update(algo_metadata)
                # --- END OF FIX ---

            elif hasattr(algo_module_or_system, 'make_decisions'): # For Coordinated MAS
                # 假设 make_decisions 也返回元组
                algo_decisions, algo_metadata = algo_module_or_system.make_decisions(
                    current_state, manual_decisions, grid_preferences
                )
                scheduler_metadata.update(algo_metadata)

            elif effective_algo_name == "marl" and self.marl_system:
                # MARL的逻辑比较特殊，我们在这里封装它的返回
                # ... (MARL action creation and conversion logic) ...
                marl_actions = self.marl_system.choose_actions(current_state)
                algo_decisions = self._convert_marl_actions_to_decisions(marl_actions, current_state, {}) # Placeholder for action maps
                # MARL 目前没有返回元数据，所以我们用默认值
                scheduler_metadata['candidate_user_count'] = len(algo_decisions) # 粗略估计
            
            else:
                logger.error(f"SCHEDULER: Algorithm '{effective_algo_name}' has no recognized decision method.")
                # 即使出错，也要保证返回两个值
                return {}, scheduler_metadata

            # 3. 合并决策 (算法决策优先，手动决策覆盖)
            # 注意：这里的逻辑应该是 manual_decisions 覆盖 algo_decisions
            final_decisions = algo_decisions.copy()
            final_decisions.update(validated_manual_decisions) # 手动决策有最高优先级

        except Exception as e:
            logger.error(f"SCHEDULER: Error during scheduling with {effective_algo_name}: {e}", exc_info=True)
            # 出错时返回空决策和元数据
            return {}, scheduler_metadata

        logger.info(f"SCHEDULER: ({effective_algo_name}) made {len(final_decisions)} assignments. Candidates: {scheduler_metadata.get('candidate_user_count', 'N/A')}.")
        
        # 确保最终返回的是一个包含两个元素的元组
        return final_decisions, scheduler_metadata
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
        candidate_params = marl_config.get('candidate_selection_params', {})
        
        action_space_size = marl_config.get("action_space_size", 6) # Default to 6
        max_potential_users = action_space_size - 1 # Number of users to map

        # --- 获取可配置的候选用户选择参数 ---
        MAX_DISTANCE_SQ = marl_config.get("marl_candidate_max_dist_sq", 0.15**2) # Example: (0.15 degrees)^2
        W_SOC = marl_config.get("marl_priority_w_soc", 0.5) # Weight for SOC in priority scoring
        W_DIST = marl_config.get("marl_priority_w_dist", 0.4) # Weight for distance
        W_URGENCY = marl_config.get("marl_priority_w_urgency", 0.1) # Weight for urgency

        base_soc_trigger = candidate_params.get('base_soc_threshold', 40)
        profile_soc_adjustments = candidate_params.get('profile_soc_adjustments', {})
        dist_conversion_factor = candidate_params.get('distance_unit_conversion_factor', 111.0) # km per degree

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
            
            charge_threshold = base_soc_trigger # Start with base
            charge_threshold += profile_soc_adjustments.get(user_profile, 0)
            # Ensure threshold is reasonable, e.g. not negative if adjustments are large
            charge_threshold = max(5, charge_threshold) # Minimum practical threshold

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
                    distance = math.sqrt(dist_sq) * dist_conversion_factor # Use configured conversion factor
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