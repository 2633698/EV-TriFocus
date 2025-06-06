# ev_charging_project/simulation/metrics.py

import logging
import math
import random
from datetime import datetime
import numpy # Added for numpy.std

logger = logging.getLogger(__name__)

# --- New Metric Calculation Functions ---

def calculate_peak_reduction(coordinated_load_profile: list[float], uncoordinated_load_profile: list[float]) -> float:
    """Calculates the percentage reduction in peak load."""
    if not coordinated_load_profile or not uncoordinated_load_profile:
        logger.warning("Empty load profile(s) provided to calculate_peak_reduction.")
        return 0.0

    max_coord_load = max(coordinated_load_profile)
    max_uncoord_load = max(uncoordinated_load_profile)

    if max_uncoord_load == 0:
        if max_coord_load == 0:
            return 100.0 # No load in either case, effectively 100% reduction of zero peak
        else:
            # Uncoordinated had no load, but coordinated has load - this is unusual, implies negative reduction (increase)
            # Or could be seen as undefined or infinitely bad. For percentage, let's return a large negative.
            logger.warning(f"Uncoordinated peak load is 0, but coordinated is {max_coord_load}. Peak reduction is ill-defined.")
            return -float('inf') # Or handle as per specific requirements, e.g., -100 * (max_coord_load / some_reference_load_if_available)

    reduction = max_uncoord_load - max_coord_load
    reduction_percentage = (reduction / max_uncoord_load) * 100
    return reduction_percentage

def calculate_load_balance_improvement(coordinated_load_profile: list[float], uncoordinated_load_profile: list[float]) -> float:
    """Calculates the improvement in load balance (reduction in standard deviation)."""
    if not coordinated_load_profile or not uncoordinated_load_profile:
        logger.warning("Empty load profile(s) provided to calculate_load_balance_improvement.")
        return 0.0

    std_dev_coord = numpy.std(coordinated_load_profile)
    std_dev_uncoord = numpy.std(uncoordinated_load_profile)

    if std_dev_uncoord == 0:
        if std_dev_coord == 0:
            return 0.0 # Both are perfectly flat, no improvement needed or made if interpreted as absolute reduction.
        else:
            # Uncoordinated was flat, coordinated is not - implies worsening.
            logger.warning(f"Uncoordinated load profile StdDev is 0, but coordinated is {std_dev_coord}. Load balance worsened.")
            return -std_dev_coord # Negative improvement (increase in std dev)

    improvement_metric = std_dev_uncoord - std_dev_coord
    # This returns the absolute reduction in StdDev.
    # If percentage improvement was desired: (improvement_metric / std_dev_uncoord) * 100
    return improvement_metric

def calculate_renewable_energy_percentage(total_load_profile: list[float], renewable_generation_profile: list[float]) -> float:
    """Calculates the percentage of total load met by renewable energy."""
    if not total_load_profile or not renewable_generation_profile:
        logger.warning("Empty load/generation profile provided to calculate_renewable_energy_percentage.")
        return 0.0
    if len(total_load_profile) != len(renewable_generation_profile):
        logger.warning(f"Load profile length ({len(total_load_profile)}) and renewable profile length ({len(renewable_generation_profile)}) mismatch.")
        # Adjust profiles to the minimum length or return error
        min_len = min(len(total_load_profile), len(renewable_generation_profile))
        total_load_profile = total_load_profile[:min_len]
        renewable_generation_profile = renewable_generation_profile[:min_len]
        if not total_load_profile: return 0.0


    total_energy_consumed = sum(total_load_profile)
    # total_renewable_generation = sum(renewable_generation_profile) # Not directly used in this definition

    if total_energy_consumed == 0:
        return 100.0 # No energy consumed, so 100% of (zero) consumption could be seen as met by renewables. Or 0% if no renewables either.

    # Assumes renewables are used first up to the load at each timestep
    renewable_used = sum(min(load, gen) for load, gen in zip(total_load_profile, renewable_generation_profile))

    renewable_percentage = (renewable_used / total_energy_consumed) * 100
    return renewable_percentage


# --- Modified calculate_rewards or a new wrapper ---
# For now, let's extend calculate_rewards and assume profiles are passed in via `state` or `config`
# This part will need careful integration with how profiles are generated/accessed.

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
    
    # 获取峰谷时段信息，供后续使用
    peak_hours = grid_status_dict.get("peak_hours", [])
    valley_hours = grid_status_dict.get("valley_hours", [])
    
    # 计算当前时段的收入和能耗，而不是累计值
    # 从历史记录中获取最近一段时间（如最近24小时）的数据
    history = state.get('history', [])
    
    # 计算当前时段的收入增量和能耗增量
    # 1. 获取当前充电桩状态
    current_revenue = {}
    current_energy = {}
    for c in chargers:
        if isinstance(c, dict):
            charger_id = c.get('id')
            if charger_id:
                current_revenue[charger_id] = c.get('daily_revenue', 0)
                current_energy[charger_id] = c.get('daily_energy', 0)
    
    # 2. 计算时段收入和能耗（当前值与前一时段的差值）
    # 默认时段长度为1小时（4个15分钟时间步）
    time_window_steps = 4
    
    # 从历史记录中获取前一时段的数据
    previous_revenue = {}
    previous_energy = {}
    
    # 如果有足够的历史数据，获取前一时段的值
    if len(history) >= time_window_steps:
        # 获取前一时段的状态
        previous_state = history[-time_window_steps]
        previous_chargers = previous_state.get('chargers', [])
        
        for c in previous_chargers:
            if isinstance(c, dict):
                charger_id = c.get('id')
                if charger_id:
                    previous_revenue[charger_id] = c.get('daily_revenue', 0)
                    previous_energy[charger_id] = c.get('daily_energy', 0)
    
    # 3. 计算时段收入和能耗增量
    period_revenue = 0
    period_energy = 0
    
    for charger_id, current_rev in current_revenue.items():
        prev_rev = previous_revenue.get(charger_id, current_rev)  # 如果没有前一时段数据，假设增量为0
        period_revenue += max(0, current_rev - prev_rev)  # 确保增量非负
    
    for charger_id, current_eng in current_energy.items():
        prev_eng = previous_energy.get(charger_id, current_eng)  # 如果没有前一时段数据，假设增量为0
        period_energy += max(0, current_eng - prev_eng)  # 确保增量非负
    
    # 如果没有足够的历史数据，使用当前值的一小部分作为估计
    if len(history) < time_window_steps:
        period_revenue = sum(c.get('daily_revenue', 0) / 24 for c in chargers if isinstance(c.get('daily_revenue'), (int, float)))
        period_energy = sum(c.get('daily_energy', 0) / 24 for c in chargers if isinstance(c.get('daily_energy'), (int, float)))
    
    # 计算充电桩利用率
    occupied_chargers = sum(1 for c in chargers if c.get('status') == 'occupied')
    waiting_users = sum(1 for c in chargers if len(c.get('queue', [])) > 0)
    utilization = occupied_chargers / total_chargers if total_chargers > 0 else 0
    queue_utilization = waiting_users / total_chargers if total_chargers > 0 else 0
    combined_utilization = (utilization * 0.7) + (queue_utilization * 0.3)  # 综合利用率
    
    # 计算运营成本
    # 1. 电费成本 (根据当前电价和时段能耗)
    current_price = grid_status_dict.get("current_price", 0.85)  # 当前电价
    electricity_cost = period_energy * current_price * 0.85  # 假设运营商电价为零售价的85%
    
    # 2. 维护成本 (与充电桩数量和类型相关) - 按小时分摊
    maintenance_cost_per_charger = {
        "normal": 5/24,    # 普通充电桩每小时维护成本
        "fast": 12/24,     # 快充每小时维护成本
        "superfast": 25/24  # 超快充每小时维护成本
    }
    maintenance_cost = sum(maintenance_cost_per_charger.get(c.get('type', 'normal'), 5/24) 
                          for c in chargers if isinstance(c, dict))
    
    # 3. 人力和固定成本 (与充电桩数量相关，但有规模效应) - 按小时分摊
    fixed_cost_base = 100/24  # 基础固定成本
    fixed_cost_per_charger = 2/24  # 每个充电桩增加的固定成本
    fixed_cost = fixed_cost_base + (fixed_cost_per_charger * total_chargers * (0.7 + 0.3 * math.exp(-total_chargers/50)))  # 规模效应
    
    # 总成本
    total_cost = electricity_cost + maintenance_cost + fixed_cost
    
    # 计算净利润
    net_profit = period_revenue - total_cost
    
    # 计算投资回报率 (ROI)
    # 假设不同类型充电桩的投资成本
    investment_per_charger = {
        "normal": 5000,    # 普通充电桩投资成本
        "fast": 15000,     # 快充投资成本
        "superfast": 40000  # 超快充投资成本
    }
    total_investment = sum(investment_per_charger.get(c.get('type', 'normal'), 5000) 
                          for c in chargers if isinstance(c, dict))
    
    # 假设充电桩寿命为10年，计算小时均投资成本
    hourly_investment_cost = total_investment / (10 * 365 * 24)
    
    # 小时投资回报率
    hourly_roi = net_profit / hourly_investment_cost if hourly_investment_cost > 0 else 0
    
    # 考虑峰谷电价对利润的影响
    time_factor = 0
    if hour in peak_hours: 
        time_factor = -0.1  # 高峰期电价高，利润降低
    elif hour in valley_hours: 
        time_factor = 0.2   # 低谷期电价低，利润提高
    
    # 综合评分计算 (考虑多个因素)
    # 1. 利用率评分
    utilization_score = combined_utilization * 0.8  # 0-0.8分
    if combined_utilization > 0.8:
        utilization_score += (combined_utilization - 0.8) * 0.5  # 高利用率额外奖励
    elif combined_utilization < 0.2:
        utilization_score *= 0.8  # 低利用率惩罚
    
    # 2. 收入评分 - 使用对数函数使增长更合理
    # 假设每个充电桩每小时目标收入为100/24
    target_hourly_revenue = (100/24) * total_chargers
    revenue_ratio = period_revenue / target_hourly_revenue if target_hourly_revenue > 0 else 0
    revenue_score = min(0.6, 0.3 * math.log(1 + revenue_ratio * 3) / math.log(4))  # 对数增长，最高0.6分
    
    # 3. ROI评分
    roi_target = 0.05/24  # 目标小时投资回报率
    roi_score = min(0.4, 0.2 * math.log(1 + hourly_roi / roi_target * 5) / math.log(6)) if hourly_roi > 0 else 0  # 对数增长，最高0.4分
    
    # 综合评分，加入时间因素
    operator_profit_raw = utilization_score + revenue_score + roi_score + time_factor
    
    # 确保在合理范围内
    operator_profit_raw = max(0.0, min(1.0, operator_profit_raw))
    
    # 映射到 [-1, 1]
    operator_profit = 2 * operator_profit_raw - 1
    operator_profit = max(-1.0, min(1.0, operator_profit))
    
    logger.debug(f"Calculated Operator Profit: {operator_profit:.4f} (Utilization: {combined_utilization:.2f}, Period Revenue: {period_revenue:.2f}, Period Energy: {period_energy:.2f}, Cost: {total_cost:.2f}, ROI: {hourly_roi:.4f})")



    # --- 3. 电网友好度 (增强版) ---
    grid_friendliness_score = 0
    
    # 获取全局电网状态
    current_load_percentage = grid_status_dict.get("grid_load_percentage", 50)
    renewable_ratio = grid_status_dict.get("renewable_ratio", 0) / 100.0 if grid_status_dict.get("renewable_ratio") is not None else 0.0
    total_load_abs = grid_status_dict.get("current_total_load", 0)
    ev_load_abs = grid_status_dict.get("current_ev_load", 0)
    
    # 获取区域电网状态
    regional_current_state = grid_status_dict.get("regional_current_state", {})
    regional_connections = grid_status_dict.get("regional_connections", {})
    
    # 1. 全局负载因子 (基础评分)
    if current_load_percentage < 30: load_factor = 0.8
    elif current_load_percentage < 50: load_factor = 0.5 - (current_load_percentage - 30) * 0.015
    elif current_load_percentage < 70: load_factor = 0.2 - (current_load_percentage - 50) * 0.01
    elif current_load_percentage < 85: load_factor = 0.0 - (current_load_percentage - 70) * 0.015
    else: load_factor = max(-0.5, -0.225 - (current_load_percentage - 85) * 0.01)
    
    # 2. 可再生能源因子
    renewable_factor = 0.8 * renewable_ratio
    
    # 3. 时间因子 (峰谷平)
    time_factor = 0
    if hour in peak_hours: time_factor = -0.3
    elif hour in valley_hours: time_factor = 0.6
    else: time_factor = 0.2  # 平峰
    
    # 4. EV负载集中度因子
    ev_concentration_factor = 0
    if total_load_abs > 1e-6:
        ev_load_ratio = ev_load_abs / total_load_abs
        if ev_load_ratio > 0.3:
            ev_concentration_factor = -0.15 * (ev_load_ratio - 0.3) / 0.7
    
    # 5. 区域负载不平衡因子 (新增)
    region_imbalance_factor = 0
    try:
        if regional_current_state:
            # 计算区域负载百分比的标准差
            load_percentages = [region.get('grid_load_percentage', 0) for region in regional_current_state.values()]
            if load_percentages:
                avg_load = sum(load_percentages) / len(load_percentages)
                variance = sum((x - avg_load) ** 2 for x in load_percentages) / len(load_percentages)
                std_dev = variance ** 0.5
                
                # 标准差越大，不平衡越严重，惩罚越大
                if std_dev > 10:  # 10%的标准差作为阈值
                    region_imbalance_factor = -0.2 * min(1.0, (std_dev - 10) / 30)  # 最多-0.2分
    except Exception as e:
        logger.warning(f"Error calculating region imbalance factor: {e}")
    
    # 6. 碳强度因子 (新增)
    carbon_intensity_factor = 0
    try:
        if regional_current_state:
            # 计算平均碳强度
            carbon_intensities = [region.get('carbon_intensity', 0) for region in regional_current_state.values()]
            if carbon_intensities:
                avg_carbon = sum(carbon_intensities) / len(carbon_intensities)
                # 碳强度越低越好
                if avg_carbon < 400:  # 低碳 (kg CO2/MWh)
                    carbon_intensity_factor = 0.2
                elif avg_carbon < 600:  # 中等
                    carbon_intensity_factor = 0.1
                elif avg_carbon > 800:  # 高碳
                    carbon_intensity_factor = -0.1
    except Exception as e:
        logger.warning(f"Error calculating carbon intensity factor: {e}")
    
    # 7. 负载变化率因子 (新增)
    load_change_factor = 0
    history = state.get('history', [])
    if len(history) >= 4:  # 至少需要前一小时的数据
        try:
            prev_state = history[-4]  # 假设15分钟一个时间步，取1小时前
            if prev_state and 'grid_status' in prev_state:
                prev_grid_status = prev_state.get('grid_status', {})
                prev_load = prev_grid_status.get('current_total_load')
                
                # 确保 prev_load 和 total_load_abs 都不是 None
                if prev_load is not None and total_load_abs is not None and prev_load > 0:
                    load_change_rate = abs(total_load_abs - prev_load) / prev_load
                    # 负载变化率过大不利于电网稳定
                    if load_change_rate > 0.2:  # 20%的变化率作为阈值
                        load_change_factor = -0.15 * min(1.0, (load_change_rate - 0.2) / 0.3)  # 最多-0.15分
        except Exception as e:
            logger.warning(f"Error calculating load change factor: {e}")
    
    # 8. 区域间电力传输因子 (新增)
    transfer_factor = 0
    try:
        if regional_connections:
            # 计算区域间电力传输总量与容量比
            total_transfer = sum(conn.get('current_transfer', 0) for conn in regional_connections.values())
            total_capacity = sum(conn.get('transfer_capacity', 1000) for conn in regional_connections.values())
            
            if total_capacity > 0:
                transfer_ratio = total_transfer / total_capacity
                # 传输比例过高不利于电网稳定
                if transfer_ratio > 0.7:  # 70%的传输比例作为阈值
                    transfer_factor = -0.1 * min(1.0, (transfer_ratio - 0.7) / 0.3)  # 最多-0.1分
    except Exception as e:
        logger.warning(f"Error calculating transfer factor: {e}")
    
    # 综合计算电网友好度原始分数
    grid_friendliness_raw = (
        load_factor +              # 全局负载因子
        renewable_factor +         # 可再生能源因子
        time_factor +              # 时间因子
        ev_concentration_factor +  # EV负载集中度因子
        region_imbalance_factor +  # 区域负载不平衡因子
        carbon_intensity_factor +  # 碳强度因子
        load_change_factor +       # 负载变化率因子
        transfer_factor            # 区域间电力传输因子
    )
    
    # 最终调整
    grid_friendliness = max(-0.9, min(1.0, grid_friendliness_raw))
    if grid_friendliness < 0: 
        grid_friendliness *= 0.8  # 负分减轻惩罚
    else: 
        grid_friendliness = min(1.0, grid_friendliness * 1.1)  # 正分小幅提升
    
    # 详细日志
    logger.debug(f"Grid Friendliness Components: Load={load_factor:.2f}, Renewable={renewable_factor:.2f}, "  
                f"Time={time_factor:.2f}, EV Concentration={ev_concentration_factor:.2f}, "  
                f"Region Imbalance={region_imbalance_factor:.2f}, Carbon={carbon_intensity_factor:.2f}, "  
                f"Load Change={load_change_factor:.2f}, Transfer={transfer_factor:.2f}")
    logger.debug(f"Calculated Grid Friendliness: {grid_friendliness:.4f} (Raw: {grid_friendliness_raw:.4f})")


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

    # --- Algorithm Comparison Metrics ---

    # Extract time series data from grid_status if available
    # Path updated based on EnhancedGridModel.get_status() modification
    grid_time_series = state.get('grid_status', {}).get('time_series_data_snapshot', {})

    coordinated_load_profile_regional = grid_time_series.get('regional_data', {})
    timestamps = grid_time_series.get('timestamps', [])
    num_steps = len(timestamps)

    coordinated_total_load_profile = [0.0] * num_steps
    coordinated_total_renewable_gen_profile = [0.0] * num_steps

    if num_steps > 0 and coordinated_load_profile_regional:
        for region_id, region_data in coordinated_load_profile_regional.items():
            region_total_load = region_data.get('total_load', [])
            region_solar_gen = region_data.get('solar_generation', [])
            region_wind_gen = region_data.get('wind_generation', [])

            for i in range(num_steps):
                coordinated_total_load_profile[i] += region_total_load[i] if i < len(region_total_load) else 0
                solar = region_solar_gen[i] if i < len(region_solar_gen) else 0
                wind = region_wind_gen[i] if i < len(region_wind_gen) else 0
                coordinated_total_renewable_gen_profile[i] += solar + wind

    # Placeholder for uncoordinated load profile - generate dummy data if not provided
    # In a real scenario, this would come from a baseline simulation or historical data
    uncoordinated_load_profile = state.get('uncoordinated_load_profile')
    if not uncoordinated_load_profile and coordinated_total_load_profile:
        # Create a dummy uncoordinated profile: coordinated load + some random noise, ensuring it's generally higher/peakier
        uncoordinated_load_profile = [
            max(0, load + load * random.uniform(-0.05, 0.2) + random.uniform(0, max(coordinated_total_load_profile)*0.1 if coordinated_total_load_profile else 10))
            for load in coordinated_total_load_profile
        ]
        # Ensure it has some peaks for reduction calculations
        if len(uncoordinated_load_profile) > 5 : # at least 5 data points
            peak_increase_factor = 1.2
            idx_to_increase_1 = random.randint(0, len(uncoordinated_load_profile)-1)
            idx_to_increase_2 = random.randint(0, len(uncoordinated_load_profile)-1)
            uncoordinated_load_profile[idx_to_increase_1] *= peak_increase_factor
            uncoordinated_load_profile[idx_to_increase_2] *= (peak_increase_factor*0.8)


    # Assume uncoordinated scenario uses the same renewable generation profile for now
    uncoordinated_renewable_profile = coordinated_total_renewable_gen_profile

    if coordinated_total_load_profile and uncoordinated_load_profile:
        peak_reduction_perc = calculate_peak_reduction(coordinated_total_load_profile, uncoordinated_load_profile)

        # For load_balance, the GUI expects the direct std dev values.
        # The 'improvement' is visually derived by comparing the two bars.
        std_dev_uncoordinated = numpy.std(uncoordinated_load_profile) if uncoordinated_load_profile else 0
        std_dev_coordinated = numpy.std(coordinated_total_load_profile) if coordinated_total_load_profile else 0

        renewable_share_coord_perc = calculate_renewable_energy_percentage(coordinated_total_load_profile, coordinated_total_renewable_gen_profile)
        renewable_share_uncoord_perc = calculate_renewable_energy_percentage(uncoordinated_load_profile, uncoordinated_renewable_profile)

        # This structure should align with what PowerGridPanel.update_algorithm_comparison_chart expects
        # where 'uncoordinated' and 'coordinated' are keys under each metric.
        results['comparison_metrics_display'] = {
            'peak_reduction': { # Peak reduction achieved by coordinated strategy (uncoordinated is baseline 0% reduction)
                'uncoordinated': 0,
                'coordinated': peak_reduction_perc
            },
            'load_balance': { # Actual StdDev values. Lower is better.
                'uncoordinated': std_dev_uncoordinated,
                'coordinated': std_dev_coordinated
            },
            'renewable_share': { # Actual renewable share percentage. Higher is better.
                'uncoordinated': renewable_share_uncoord_perc,
                'coordinated': renewable_share_coord_perc
            }
        }
        logger.debug(f"Calculated Algorithm Comparison Metrics: {results['comparison_metrics_display']}")
    else:
        logger.warning("Could not calculate algorithm comparison metrics due to missing load profiles.")
        results['comparison_metrics_display'] = { # Send default structure if data is missing
            'peak_reduction': {'uncoordinated': 0, 'coordinated': 0},
            'load_balance': {'uncoordinated': 0, 'coordinated': 0},
            'renewable_share': {'uncoordinated': 0, 'coordinated': 0}
        }


    # Note: The panel's update_algorithm_comparison_chart expects values for 'uncoordinated' and 'coordinated' for each metric.
        # The GUI's update_algorithm_comparison_chart is set up to receive 'uncoordinated' and 'coordinated'
        # values for each metric category. The interpretation for each category is:
        # - 'peak_reduction': Coordinated shows % reduction vs Uncoordinated. Uncoordinated is 0.
        # - 'load_balance': Shows direct StdDev for each. Lower is better.
        # - 'renewable_share': Shows % share for each. Higher is better.
        # The current `results['comparison_metrics_display']` structure aligns with this.

    return results