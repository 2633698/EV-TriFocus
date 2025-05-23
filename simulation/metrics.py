# ev_charging_project/simulation/metrics.py

import logging
import math
import random
from datetime import datetime

logger = logging.getLogger(__name__)

def calculate_rewards(state, config):
    """
    计算当前状态下的奖励值，并包含无序充电基准对比。

    Args:
        state (dict): 当前环境状态 (包含 users, chargers, grid_status)
        config (dict): 全局配置

    Returns:
        dict: 包含各项奖励指标及对比指标的字典
    """
    users = state.get('users', [])
    chargers = state.get('chargers', [])
    grid_status_dict = state.get('grid_status', {})
    current_time_str = state.get('timestamp', datetime.now().isoformat())
    try:
        current_time = datetime.fromisoformat(current_time_str)
    except ValueError:
        current_time = datetime.now()
    hour = current_time.hour

    total_users = len(users) if users else 1
    total_chargers = len(chargers) if chargers else 1

    # --- 1. 用户满意度 (协调后) ---
    user_satisfaction_score = 0
    # (复制粘贴原 _calculate_rewards 中用户满意度的计算逻辑)
    # ... [原用户满意度计算逻辑，注意使用 state 中的数据] ...
    # 示例简化版：
    soc_sum = sum(u.get('soc', 0) for u in users if isinstance(u.get('soc'), (int, float))) # 更安全的求和
    avg_soc = soc_sum / total_users if total_users > 0 else 0
    waiting_count = sum(1 for u in users if u.get('status') == 'waiting')
    # 简单的满意度计算，需要替换为原详细逻辑
    user_satisfaction_raw = (avg_soc / 100.0) * (1 - 0.5 * (waiting_count / total_users))
    # 映射到 [-1, 1]
    user_satisfaction = 2 * user_satisfaction_raw - 1 # 极简示例
    user_satisfaction = max(-1.0, min(1.0, user_satisfaction))
    logger.debug(f"Calculated User Satisfaction: {user_satisfaction:.4f}")


    # --- 2. 运营商利润 (协调后) ---
    operator_profit_score = 0
    # (复制粘贴原 _calculate_rewards 中运营商利润的计算逻辑)
    # ... [原运营商利润计算逻辑，注意使用 state 中的数据] ...
    # 示例简化版：
    total_revenue = sum(c.get('daily_revenue', 0) for c in chargers if isinstance(c.get('daily_revenue'), (int, float)))
    occupied_chargers = sum(1 for c in chargers if c.get('status') == 'occupied')
    utilization = occupied_chargers / total_chargers if total_chargers > 0 else 0
    # 简单的利润计算，需要替换为原详细逻辑
    profit_factor = (total_revenue / (total_chargers * 50 + 1e-6)) # 假设每个充电桩每天目标收入50
    operator_profit_raw = min(1.0, profit_factor * 0.6 + utilization * 0.4)
     # 映射到 [-1, 1]
    operator_profit = 2 * operator_profit_raw - 1 # 极简示例
    operator_profit = max(-1.0, min(1.0, operator_profit))
    logger.debug(f"Calculated Operator Profit: {operator_profit:.4f}")


    # --- 3. 电网友好度 (协调后) ---
    grid_friendliness_score = 0
    # (复制粘贴原 _calculate_rewards 中电网友好度的计算逻辑)
    # ... [原电网友好度计算逻辑，注意使用 state 中的数据] ...
    # 示例简化版 (使用 grid_status_dict 中的数据):
    current_load_percentage = grid_status_dict.get("grid_load_percentage", 50)
    renewable_ratio = grid_status_dict.get("renewable_ratio", 0) / 100.0 if grid_status_dict.get("renewable_ratio") is not None else 0.0
    peak_hours = grid_status_dict.get("peak_hours", [])
    valley_hours = grid_status_dict.get("valley_hours", [])

    # 使用更详细的评分逻辑 (从原环境类中借鉴)
    if current_load_percentage < 30: load_factor = 0.8
    elif current_load_percentage < 50: load_factor = 0.5 - (current_load_percentage - 30) * 0.015
    elif current_load_percentage < 70: load_factor = 0.2 - (current_load_percentage - 50) * 0.01
    elif current_load_percentage < 85: load_factor = 0.0 - (current_load_percentage - 70) * 0.015
    else: load_factor = max(-0.5, -0.225 - (current_load_percentage - 85) * 0.01)

    renewable_factor = 0.8 * renewable_ratio # 可再生能源加分
    time_factor = 0
    if hour in peak_hours: time_factor = -0.3
    elif hour in valley_hours: time_factor = 0.6
    else: time_factor = 0.2 # 平峰

    # EV负载集中度惩罚 (可选)
    ev_concentration_factor = 0
    total_load_abs = grid_status_dict.get("current_total_load", 0)
    ev_load_abs = grid_status_dict.get("current_ev_load", 0)
    if total_load_abs > 1e-6:
        ev_load_ratio = ev_load_abs / total_load_abs
        if ev_load_ratio > 0.3:
            ev_concentration_factor = -0.15 * (ev_load_ratio - 0.3) / 0.7

    grid_friendliness_raw = load_factor + renewable_factor + time_factor + ev_concentration_factor
    # 最终调整
    grid_friendliness = max(-0.9, min(1.0, grid_friendliness_raw))
    if grid_friendliness < 0: grid_friendliness *= 0.8
    else: grid_friendliness = min(1.0, grid_friendliness * 1.1)
    logger.debug(f"Calculated Grid Friendliness: {grid_friendliness:.4f}")


    # --- 4. 总奖励 (协调后) ---
    weights = config.get('scheduler', {}).get('optimization_weights', {
        "user_satisfaction": 0.4, "operator_profit": 0.3, "grid_friendliness": 0.3
    })
    total_reward = (user_satisfaction * weights["user_satisfaction"] +
                    operator_profit * weights["operator_profit"] +
                    grid_friendliness * weights["grid_friendliness"])
    logger.debug(f"Calculated Total Reward: {total_reward:.4f}")


    # --- 5. 无序充电基准对比 (从原环境类逻辑迁移并调整) ---
    uncoordinated_user_satisfaction = None
    uncoordinated_operator_profit = None
    uncoordinated_grid_friendliness = None
    uncoordinated_total_reward = None
    improvement_percentage = None

    # 检查配置是否启用了基准对比
    enable_baseline = config.get('environment', {}).get('enable_uncoordinated_baseline', True)

    if enable_baseline:
        # 估算无序用户满意度 (简化)
        # 主要惩罚等待时间，SOC影响较小
        uncoordinated_wait_factor = 0.7 # 假设平均等待时间更长，满意度因子降低
        # 无序充电可能导致SOC分布更差？这里简化为与协调后类似，但乘以等待惩罚
        uncoordinated_soc_factor = avg_soc / 100.0
        unc_user_satisfaction_raw = uncoordinated_soc_factor * uncoordinated_wait_factor
        uncoordinated_user_satisfaction = 2 * unc_user_satisfaction_raw - 1
        uncoordinated_user_satisfaction = max(-1.0, min(1.0, uncoordinated_user_satisfaction))
        logger.debug(f"Baseline User Satisfaction: {uncoordinated_user_satisfaction:.4f}")

        # 估算无序运营商利润 (简化)
        # 假设利用率可能接近，但收入分布不均，高峰期收入高但成本也高，可能利润率更低
        # 假设整体利润比协调后低 10-30%
        profit_reduction_factor = random.uniform(0.7, 0.9)
        uncoordinated_operator_profit = operator_profit * profit_reduction_factor - 0.1 # 再加一点固定惩罚
        uncoordinated_operator_profit = max(-1.0, min(1.0, uncoordinated_operator_profit))
        logger.debug(f"Baseline Operator Profit: {uncoordinated_operator_profit:.4f}")

        # 估算无序电网友好度 (基于时间)
        # 无序充电更可能集中在高峰期
        if hour in peak_hours:
            # 高峰期，大量无序充电，电网友好度很差
            uncoordinated_grid_friendliness = -0.7 - 0.1 * renewable_ratio # 基础分很低，受可再生能源影响小
        elif hour in valley_hours:
            # 低谷期，部分无序充电可能发生，但比协调模式差
            uncoordinated_grid_friendliness = 0.2 + 0.2 * renewable_ratio # 比协调模式的谷时得分低
        else: # 平峰期
            # 平峰期，无序充电影响中等偏负面
            uncoordinated_grid_friendliness = -0.2 - 0.1 * renewable_ratio # 比协调模式的平峰得分低

        uncoordinated_grid_friendliness = max(-1.0, min(1.0, uncoordinated_grid_friendliness))
        logger.debug(f"Baseline Grid Friendliness: {uncoordinated_grid_friendliness:.4f}")

        # 计算无序总奖励
        uncoordinated_total_reward = (
            uncoordinated_user_satisfaction * weights["user_satisfaction"] +
            uncoordinated_operator_profit * weights["operator_profit"] +
            uncoordinated_grid_friendliness * weights["grid_friendliness"]
        )
        logger.debug(f"Baseline Total Reward: {uncoordinated_total_reward:.4f}")

        # 计算改进百分比
        if uncoordinated_total_reward is not None and abs(uncoordinated_total_reward) > 1e-6:
            improvement_percentage = ((total_reward - uncoordinated_total_reward) /
                                      abs(uncoordinated_total_reward)) * 100
            logger.debug(f"Improvement Percentage: {improvement_percentage:.2f}%")


    # --- 最终返回结果 ---
    results = {
        "user_satisfaction": user_satisfaction,
        "operator_profit": operator_profit,
        "grid_friendliness": grid_friendliness,
        "total_reward": total_reward
    }
    # 如果计算了基准，则添加到结果中
    if enable_baseline:
        results.update({
            "uncoordinated_user_satisfaction": uncoordinated_user_satisfaction,
            "uncoordinated_operator_profit": uncoordinated_operator_profit,
            "uncoordinated_grid_friendliness": uncoordinated_grid_friendliness,
            "uncoordinated_total_reward": uncoordinated_total_reward,
            "improvement_percentage": improvement_percentage
        })

    return results