# ev_charging_project/simulation/grid_model_enhanced.py
import logging
from datetime import datetime
from collections import defaultdict, deque
import json

logger = logging.getLogger(__name__)

class EnhancedGridModel:
    def __init__(self, config):
        """初始化增强的电网模型，支持时间-区域数据结构"""
        self.grid_config = config.get('grid', {})
        self.environment_config = config.get('environment', {})
        self.grid_status = {}
        self.region_ids = []
        self.region_geometries = {} # To store loaded geometries
        
        # 新增：时间-区域历史数据存储
        self.time_series_data = {
            'timestamps': deque(maxlen=288),  # 保存最近72小时的数据（15分钟间隔）
            'regional_data': defaultdict(lambda: {
                'base_load': deque(maxlen=288),
                'ev_load': deque(maxlen=288),
                'total_load': deque(maxlen=288),
                'solar_generation': deque(maxlen=288),
                'wind_generation': deque(maxlen=288),
                'renewable_ratio': deque(maxlen=288),
                'grid_load_percentage': deque(maxlen=288),
                'current_price': deque(maxlen=288),
                'carbon_intensity': deque(maxlen=288)
            })
        }
        
        # 新增：区域间连接关系
        self.regional_connections = {}
        
        self._load_region_geometries() # Load geometries during initialization
        self.reset()

    def _load_region_geometries(self):
        """Loads region geometry data from the grid configuration."""
        self.region_geometries = self.grid_config.get("region_geometries", {})
        if not self.region_geometries:
            logger.warning("No region geometries found in grid configuration.")
        else:
            logger.info(f"Loaded geometries for regions: {list(self.region_geometries.keys())}")

    def reset(self):
        """重置电网状态到初始值，支持区域化配置"""
        logger.info("Resetting Enhanced GridModel for regional setup...")

        # 确定区域ID
        # If region_ids are defined by geometries, prioritize those.
        if self.region_geometries and isinstance(self.region_geometries, dict) and self.region_geometries.keys():
             # Ensure consistency if both base_load and geometries define regions
            geom_region_ids = list(self.region_geometries.keys())
            base_load_regional_data = self.grid_config.get("base_load", {})
            if isinstance(base_load_regional_data, dict) and base_load_regional_data.keys():
                base_load_region_ids = list(base_load_regional_data.keys())
                if set(geom_region_ids) != set(base_load_region_ids):
                    logger.warning(f"Region IDs from geometries {geom_region_ids} and base_load {base_load_region_ids} differ. Using geometry IDs.")
                self.region_ids = geom_region_ids
            else:
                self.region_ids = geom_region_ids
            logger.info(f"Region IDs derived from 'grid.region_geometries' keys: {self.region_ids}")
        else:
            base_load_regional_data = self.grid_config.get("base_load", {})
        if isinstance(base_load_regional_data, dict) and base_load_regional_data.keys():
            self.region_ids = list(base_load_regional_data.keys())
            logger.info(f"Region IDs derived from 'grid.base_load' keys: {self.region_ids}")
        else:
            num_regions_env = self.environment_config.get("region_count", 5)
            if isinstance(num_regions_env, int) and num_regions_env > 0:
                self.region_ids = [f"region_{i}" for i in range(num_regions_env)]
                logger.warning(f"Using default region IDs: {self.region_ids}")
            else:
                self.region_ids = ["region_0"]
                logger.error("Critical fallback to single default region")

        # 全局设置
        peak_hours = self.grid_config.get("peak_hours", [7, 8, 9, 10, 18, 19, 20, 21])
        valley_hours = self.grid_config.get("valley_hours", [0, 1, 2, 3, 4, 5])
        normal_price = self.grid_config.get("normal_price", 0.85)
        peak_price = self.grid_config.get("peak_price", 1.2)
        valley_price = self.grid_config.get("valley_price", 0.4)

        # 初始化区域数据结构
        regional_profiles = {}
        regional_current_state = {}
        
        initial_hour = 0

        for region_id in self.region_ids:
            # 获取区域配置
            base_load_profile = self._get_regional_profile_or_default("base_load", region_id, 1000)
            solar_profile = self._get_regional_profile_or_default("solar_generation", region_id, 0)
            wind_profile = self._get_regional_profile_or_default("wind_generation", region_id, 100)
            system_capacity = self._get_regional_value_or_default("system_capacity_kw", region_id, 10000)
            
            regional_profiles[region_id] = {
                'base_load_profile': base_load_profile,
                'solar_generation_profile': solar_profile,
                'wind_generation_profile': wind_profile,
                'system_capacity': system_capacity
            }

            # 初始化当前状态
            initial_base_load = base_load_profile[initial_hour]
            initial_solar = solar_profile[initial_hour]
            initial_wind = wind_profile[initial_hour]
            initial_ev_load = 0.0
            initial_total_load = initial_base_load + initial_ev_load
            
            grid_load_percentage = (initial_total_load / system_capacity) * 100 if system_capacity > 0 else 0.0
            renewable_generation = initial_solar + initial_wind
            renewable_ratio = (renewable_generation / initial_total_load * 100) if initial_total_load > 0 else 0.0
            
            # 计算碳强度（简化模型）
            carbon_intensity = self._calculate_carbon_intensity(renewable_ratio, initial_hour)
            
            regional_current_state[region_id] = {
                'current_base_load': initial_base_load,
                'current_solar_gen': initial_solar,
                'current_wind_gen': initial_wind,
                'current_ev_load': initial_ev_load,
                'current_total_load': initial_total_load,
                'grid_load_percentage': grid_load_percentage,
                'renewable_ratio': renewable_ratio,
                'carbon_intensity': carbon_intensity
            }

        # 初始化区域间连接关系
        self._initialize_regional_connections()

        self.grid_status = {
            # 区域配置文件
            "regional_profiles": regional_profiles,
            
            # 全局设置
            "peak_hours": peak_hours,
            "valley_hours": valley_hours,
            "normal_price": normal_price,
            "peak_price": peak_price,
            "valley_price": valley_price,
            
            # 当前区域状态
            "regional_current_state": regional_current_state,
            
            # 全局当前值
            "current_price": self._get_current_price(initial_hour),
            
            # 区域间连接
            "regional_connections": self.regional_connections
        }
        
        # 清空时间序列数据
        self.time_series_data['timestamps'].clear()
        for region_data in self.time_series_data['regional_data'].values():
            for metric_data in region_data.values():
                metric_data.clear()
        
        logger.info(f"Enhanced GridModel reset complete for regions: {self.region_ids}")

    def update_step(self, current_time, global_ev_load):
        """更新电网状态，记录时间-区域数据"""
        hour = current_time.hour
        if not (0 <= hour < 24):
            logger.error(f"Invalid hour ({hour}). Using hour 0.")
            hour = 0

        # 记录时间戳
        timestamp = current_time.isoformat()
        self.time_series_data['timestamps'].append(timestamp)

        # 分配EV负载到各区域
        regional_ev_loads = self._distribute_ev_load(global_ev_load)

        # 更新每个区域的状态
        for region_id in self.region_ids:
            self._update_regional_state(region_id, hour, regional_ev_loads.get(region_id, 0), current_time)

        # 更新全局价格
        current_price = self._get_current_price(hour)
        self.grid_status["current_price"] = current_price

    def _update_regional_state(self, region_id, hour, ev_load, current_time):
        """更新单个区域的状态并记录时间序列数据"""
        profiles = self.grid_status["regional_profiles"][region_id]
        current_state = self.grid_status["regional_current_state"][region_id]
        
        # 获取当前小时的基础数据
        base_load = profiles['base_load_profile'][hour]
        solar_gen = profiles['solar_generation_profile'][hour]
        wind_gen = profiles['wind_generation_profile'][hour]
        system_capacity = profiles['system_capacity']
        
        # 计算负载和比例
        total_load = base_load + ev_load
        grid_load_percentage = (total_load / system_capacity) * 100 if system_capacity > 0 else 0.0
        
        # 计算可再生能源比例
        renewable_generation = solar_gen + wind_gen
        renewable_ratio = (renewable_generation / total_load * 100) if total_load > 0 else 0.0
        
        # 计算碳强度
        carbon_intensity = self._calculate_carbon_intensity(renewable_ratio, hour)
        
        # 更新当前状态
        current_state.update({
            'current_base_load': base_load,
            'current_solar_gen': solar_gen,
            'current_wind_gen': wind_gen,
            'current_ev_load': ev_load,
            'current_total_load': total_load,
            'grid_load_percentage': grid_load_percentage,
            'renewable_ratio': renewable_ratio,
            'carbon_intensity': carbon_intensity
        })
        
        # 记录时间序列数据
        region_data = self.time_series_data['regional_data'][region_id]
        region_data['base_load'].append(base_load)
        region_data['ev_load'].append(ev_load)
        region_data['total_load'].append(total_load)
        region_data['solar_generation'].append(solar_gen)
        region_data['wind_generation'].append(wind_gen)
        region_data['renewable_ratio'].append(renewable_ratio)
        region_data['grid_load_percentage'].append(grid_load_percentage)
        region_data['current_price'].append(self.grid_status["current_price"])
        region_data['carbon_intensity'].append(carbon_intensity)

    def _distribute_ev_load(self, global_ev_load):
        """将全局EV负载分配到各区域"""
        total_capacity = sum(
            self.grid_status["regional_profiles"][region_id]['system_capacity']
            for region_id in self.region_ids
        )
        
        if total_capacity == 0:
            return {region_id: 0.0 for region_id in self.region_ids}
        
        regional_loads = {}
        for region_id in self.region_ids:
            capacity = self.grid_status["regional_profiles"][region_id]['system_capacity']
            proportion = capacity / total_capacity
            regional_loads[region_id] = global_ev_load * proportion
            
        return regional_loads

    def _calculate_carbon_intensity(self, renewable_ratio, hour):
        """计算碳强度 (kg CO2/MWh)"""
        # 基础碳强度（煤电为主）
        base_carbon_intensity = 800  # kg CO2/MWh
        
        # 可再生能源降低碳强度
        renewable_factor = (100 - renewable_ratio) / 100
        
        # 夜间碳强度通常更高（更多煤电）
        time_factor = 1.1 if 22 <= hour or hour <= 6 else 1.0
        
        return base_carbon_intensity * renewable_factor * time_factor

    def _initialize_regional_connections(self):
        """初始化区域间连接关系"""
        self.regional_connections = {}
        
        # 简化的连接模型：相邻区域相互连接
        for i, region_id in enumerate(self.region_ids):
            connections = []
            # 连接到前一个和后一个区域（环形连接）
            if len(self.region_ids) > 1:
                prev_idx = (i - 1) % len(self.region_ids)
                next_idx = (i + 1) % len(self.region_ids)
                connections.extend([self.region_ids[prev_idx], self.region_ids[next_idx]])
            
            self.regional_connections[region_id] = {
                'connected_regions': connections,
                'transfer_capacity': 1000,  # MW
                'current_transfer': 0  # MW
            }

    def get_time_series_data(self, start_time=None, end_time=None):
        """获取时间-区域序列数据"""
        timestamps = list(self.time_series_data['timestamps'])
        
        if not timestamps:
            return {'timestamps': [], 'regional_data': {}}
        
        # 如果指定了时间范围，进行过滤
        if start_time or end_time:
            filtered_data = self._filter_time_series(start_time, end_time)
            return filtered_data
        
        # 返回所有数据
        result = {
            'timestamps': timestamps,
            'regional_data': {}
        }
        
        for region_id in self.region_ids:
            region_data = self.time_series_data['regional_data'][region_id]
            result['regional_data'][region_id] = {
                key: list(values) for key, values in region_data.items()
            }
        
        return result

    def get_regional_comparison(self):
        """获取区域间对比数据"""
        comparison_data = {
            'regions': self.region_ids,
            'metrics': {}
        }
        
        metrics = ['current_total_load', 'grid_load_percentage', 'renewable_ratio', 'carbon_intensity']
        
        for metric in metrics:
            comparison_data['metrics'][metric] = []
            for region_id in self.region_ids:
                current_state = self.grid_status["regional_current_state"][region_id]
                comparison_data['metrics'][metric].append(current_state.get(metric, 0))
        
        return comparison_data

    def get_aggregated_metrics(self):
        """获取聚合指标"""
        total_base_load = 0
        total_ev_load = 0
        total_capacity = 0
        weighted_renewable_ratio = 0
        weighted_carbon_intensity = 0
        
        for region_id in self.region_ids:
            state = self.grid_status["regional_current_state"][region_id]
            capacity = self.grid_status["regional_profiles"][region_id]['system_capacity']
            
            total_base_load += state['current_base_load']
            total_ev_load += state['current_ev_load']
            total_capacity += capacity
            
            # 按负载权重计算加权平均
            load = state['current_total_load']
            if load > 0:
                weighted_renewable_ratio += state['renewable_ratio'] * load
                weighted_carbon_intensity += state['carbon_intensity'] * load
        
        total_load = total_base_load + total_ev_load
        
        return {
            'total_base_load': total_base_load,
            'total_ev_load': total_ev_load,
            'total_load': total_load,
            'total_capacity': total_capacity,
            'overall_load_percentage': (total_load / total_capacity * 100) if total_capacity > 0 else 0,
            'weighted_renewable_ratio': (weighted_renewable_ratio / total_load) if total_load > 0 else 0,
            'weighted_carbon_intensity': (weighted_carbon_intensity / total_load) if total_load > 0 else 0,
            'current_price': self.grid_status["current_price"]
        }

    def _get_regional_profile_or_default(self, profile_key, region_id, default_value):
        """安全获取区域配置文件"""
        profiles_dict = self.grid_config.get(profile_key, {})
        if not isinstance(profiles_dict, dict):
            logger.warning(f"Profile '{profile_key}' not found or invalid. Using default.")
            return [default_value] * 24
        
        region_profile = profiles_dict.get(region_id)
        if not isinstance(region_profile, list) or len(region_profile) != 24:
            logger.warning(f"Profile '{profile_key}' for region '{region_id}' invalid. Using default.")
            return [default_value] * 24
        
        return region_profile

    def _get_regional_value_or_default(self, value_key, region_id, default_value):
        """安全获取区域数值配置"""
        values_dict = self.grid_config.get(value_key, {})
        if not isinstance(values_dict, dict):
            logger.warning(f"Value '{value_key}' not found. Using default.")
            return default_value
        
        value = values_dict.get(region_id)
        if not isinstance(value, (int, float)):
            logger.warning(f"Value '{value_key}' for region '{region_id}' invalid. Using default.")
            return default_value
        
        return value

    def _get_current_price(self, hour):
        """根据小时获取电价"""
        if hour in self.grid_status.get("peak_hours", []):
            return self.grid_status.get("peak_price", 1.2)
        elif hour in self.grid_status.get("valley_hours", []):
            return self.grid_status.get("valley_price", 0.4)
        else:
            return self.grid_status.get("normal_price", 0.85)

    def get_status(self):
        """返回当前电网状态"""
        status = self.grid_status.copy()
        
        # 添加聚合指标
        status['aggregated_metrics'] = self.get_aggregated_metrics()
        
        # 添加区域对比
        status['regional_comparison'] = self.get_regional_comparison()
        
        # 添加时间序列数据快照，供 metrics 使用
        status['time_series_data_snapshot'] = self.get_time_series_data() # Calling with no args gets all data

        # 添加区域地理信息
        status['region_geometries'] = self.get_region_geometries()

        return status

    def get_region_geometries(self):
        """Returns the loaded region geometry data."""
        return self.region_geometries

    def export_time_series_data(self, filepath):
        """导出时间序列数据到文件"""
        data = self.get_time_series_data()
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.info(f"Time series data exported to {filepath}")
        except Exception as e:
            logger.error(f"Failed to export time series data: {e}")

    def apply_v2g_discharge(self, amount_mw):
        """
        Applies V2G discharge to the grid.
        This will reduce the 'current_ev_load' in regional and aggregated metrics.
        """
        if amount_mw is None or amount_mw <= 0:
            return

        logger.info(f"GridModel: Applying V2G discharge of {amount_mw:.2f} MW.")
        ev_load_reduction_kw = amount_mw * 1000

        # Reduce aggregated EV load
        if 'aggregated_metrics' in self.grid_status and \
           'total_ev_load' in self.grid_status['aggregated_metrics']:
            current_total_ev_load_kw = self.grid_status['aggregated_metrics']['total_ev_load']
            self.grid_status['aggregated_metrics']['total_ev_load'] = max(0, current_total_ev_load_kw - ev_load_reduction_kw)
            logger.debug(f"Aggregated EV load reduced from {current_total_ev_load_kw:.2f} kW to {self.grid_status['aggregated_metrics']['total_ev_load']:.2f} kW.")
        else:
            logger.warning("Could not apply V2G to aggregated_metrics: 'total_ev_load' not found.")

        # Distribute reduction proportionally to regional EV loads
        # This requires knowing the EV load distribution *before* this V2G discharge for the current step.
        # For simplicity, if we don't have pre-V2G regional EV loads, we might distribute based on capacity or equally.
        # However, EV load is updated in `update_step` based on `simulate_chargers_step`.
        # `apply_v2g_discharge` should ideally be called *before* `update_step` calculates the new `total_ev_load`
        # or `update_step` needs to be aware of V2G discharge.
        # For now, let's assume it directly reduces the most recent 'current_ev_load' for each region.

        # Calculate total current EV load across regions to find proportions
        # This sum might be different from aggregated_metrics.total_ev_load if it was already reduced.
        # To avoid double counting reduction if this method is called multiple times in a step,
        # this needs careful state management or should only reduce a "demand" value that then feeds into total_load.

        # Simplification for now: Reduce the current_ev_load in each region.
        # This will be reflected when get_status() is called next or if update_step re-reads these.
        # A more robust solution would be to have a separate 'v2g_discharge_kw' field per region
        # that `update_step` then subtracts from the calculated EV charging load.

        num_regions = len(self.region_ids)
        if num_regions == 0:
            logger.warning("No regions to apply V2G discharge to.")
            return

        # Attempt to distribute reduction proportionally to current EV load in regions
        # This is tricky because current_ev_load might already reflect previous V2G or charging.
        # A simpler, though less accurate, initial approach is to distribute equally or based on capacity.
        # Let's distribute equally for now as a placeholder.
        reduction_per_region_kw = ev_load_reduction_kw / num_regions

        for region_id in self.region_ids:
            if region_id in self.grid_status['regional_current_state']:
                regional_state = self.grid_status['regional_current_state'][region_id]
                current_regional_ev_load_kw = regional_state.get('current_ev_load', 0)

                new_regional_ev_load_kw = max(0, current_regional_ev_load_kw - reduction_per_region_kw)
                actual_reduction_this_region = current_regional_ev_load_kw - new_regional_ev_load_kw

                regional_state['current_ev_load'] = new_regional_ev_load_kw
                # Total load will also need to be re-calculated or adjusted based on this.
                # For now, assume update_step will pick up the new current_ev_load.
                # To be more accurate, total load should be adjusted here.
                regional_state['current_total_load'] = max(0, regional_state.get('current_total_load',0) - actual_reduction_this_region)


                logger.debug(f"Region {region_id}: EV load reduced by {actual_reduction_this_region:.2f} kW to {new_regional_ev_load_kw:.2f} kW due to V2G.")
            else:
                logger.warning(f"Region {region_id} not found in regional_current_state for V2G discharge.")

        # Note: This simplified V2G application directly modifies current loads.
        # A full simulation would integrate this into the energy balance calculation within update_step.
        # The impact on grid_load_percentage, renewable_ratio etc. will be reflected
        # when these are recalculated based on the new total_load in the next call to _update_regional_state or get_status.

        # Store the actual total amount of V2G power dispatched in this step's status
        if 'aggregated_metrics' not in self.grid_status: # Should always exist after reset
            self.grid_status['aggregated_metrics'] = {}
        self.grid_status['aggregated_metrics']['current_actual_v2g_dispatch_mw'] = amount_mw
        logger.info(f"GridModel: Recorded {amount_mw:.2f} MW of V2G dispatch in grid status's aggregated_metrics.")
