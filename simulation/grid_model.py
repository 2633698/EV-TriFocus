# ev_charging_project/simulation/grid_model.py
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class GridModel:
    def __init__(self, config):
        """初始化电网模型, 支持区域化配置"""
        # Store grid-specific and environment-specific configurations
        self.grid_config = config.get('grid', {})
        self.environment_config = config.get('environment', {})
        self.grid_status = {}
        self.region_ids = [] # Will be populated in reset
        self.reset() # 初始化状态

    def _get_regional_profile_or_default(self, profile_key_name, region_id, default_hourly_value=0):
        """
        Helper to safely get a specific regional profile (list of 24 values).
        If the profile_key_name (e.g., "base_load") or the specific region_id is missing,
        or if the data is malformed, it returns a default 24-hour profile.
        """
        profiles_dict = self.grid_config.get(profile_key_name, {})
        if not isinstance(profiles_dict, dict):
            logger.warning(
                f"Regional profile set '{profile_key_name}' is not a dictionary in config. "
                f"Using default list for region '{region_id}'."
            )
            return [default_hourly_value] * 24
        
        region_profile = profiles_dict.get(region_id)
        if not isinstance(region_profile, list) or len(region_profile) != 24:
            logger.warning(
                f"Profile for '{profile_key_name}' in region '{region_id}' is missing, not a list, or not 24 hours. "
                f"Using default list."
            )
            return [default_hourly_value] * 24
        return region_profile

    def _get_regional_value_or_default(self, value_key_name, region_id, default_value=0):
        """
        Helper to safely get a specific regional scalar value (e.g., system_capacity_kw for a region).
        If the value_key_name (e.g., "system_capacity_kw") or the specific region_id is missing,
        or if the data is malformed, it returns a default value.
        """
        values_dict = self.grid_config.get(value_key_name, {})
        if not isinstance(values_dict, dict):
            logger.warning(
                f"Regional value set '{value_key_name}' is not a dictionary in config. "
                f"Using default value for region '{region_id}'."
            )
            return default_value
        
        regional_scalar_value = values_dict.get(region_id)
        if not isinstance(regional_scalar_value, (int, float)):
            logger.warning(
                f"Value for '{value_key_name}' in region '{region_id}' is missing or not a number. "
                f"Using default value."
            )
            return default_value
        return regional_scalar_value

    def reset(self):
        """重置电网状态到初始值, 支持区域化配置"""
        logger.info("Resetting GridModel status for regional setup...")

        # Determine region_ids:
        # 1. Try from 'base_load' keys in grid_config (preferred)
        # 2. Fallback to 'region_count' in environment_config
        # 3. Absolute fallback to a single default region "region_0"
        
        base_load_regional_data = self.grid_config.get("base_load", {})
        if isinstance(base_load_regional_data, dict) and base_load_regional_data.keys():
            self.region_ids = list(base_load_regional_data.keys())
            logger.info(f"Region IDs derived from 'grid.base_load' keys: {self.region_ids}")
        else:
            num_regions_env = self.environment_config.get("region_count", 0)
            if isinstance(num_regions_env, int) and num_regions_env > 0:
                self.region_ids = [f"region_{i}" for i in range(num_regions_env)]
                logger.warning(
                    f"'grid.base_load' is not a valid regional dictionary or is empty. "
                    f"Falling back to region_ids based on environment_config.region_count: {self.region_ids}"
                )
            else:
                self.region_ids = ["region_0"] # Default to a single region if no other info
                logger.error(
                    f"'grid.base_load' is not valid, and 'environment_config.region_count' is not a positive integer. "
                    f"Critical fallback to a single default region_id: {self.region_ids}. Configuration should be checked."
                )
        
        # Global settings (prices, peak/valley hours) - these remain global in grid_status
        peak_hours = self.grid_config.get("peak_hours", [7, 8, 9, 10, 18, 19, 20, 21])
        valley_hours = self.grid_config.get("valley_hours", [0, 1, 2, 3, 4, 5])
        normal_price = self.grid_config.get("normal_price", 0.85)
        peak_price = self.grid_config.get("peak_price", 1.2)
        valley_price = self.grid_config.get("valley_price", 0.4)

        # Initialize dictionaries for regional profiles and current states
        base_load_profiles_regional = {}
        solar_generation_profiles_regional = {}
        wind_generation_profiles_regional = {}
        system_capacity_regional = {} 

        current_base_load_regional = {}
        current_solar_gen_regional = {}
        current_wind_gen_regional = {}
        current_ev_load_regional = {} 
        current_total_load_regional = {}
        grid_load_percentage_regional = {}
        renewable_ratio_regional = {}

        initial_hour = 0 # For setting initial state based on the first hour of profiles

        for region_id in self.region_ids:
            # Populate profiles for each region using helper for defaults
            # Default values are placeholders; ideally, config should be complete.
            base_load_profiles_regional[region_id] = self._get_regional_profile_or_default("base_load", region_id, 1000) # Default 1000kW hourly base load
            solar_generation_profiles_regional[region_id] = self._get_regional_profile_or_default("solar_generation", region_id, 0) # Default 0kW solar
            wind_generation_profiles_regional[region_id] = self._get_regional_profile_or_default("wind_generation", region_id, 100) # Default 100kW wind
            system_capacity_regional[region_id] = self._get_regional_value_or_default("system_capacity_kw", region_id, 10000) # Default 10MW capacity

            # Set initial current values for hour 0
            current_base_load_regional[region_id] = base_load_profiles_regional[region_id][initial_hour]
            current_solar_gen_regional[region_id] = solar_generation_profiles_regional[region_id][initial_hour]
            current_wind_gen_regional[region_id] = wind_generation_profiles_regional[region_id][initial_hour]
            current_ev_load_regional[region_id] = 0.0  # Initial EV load is zero for all regions

            initial_total_load_region = current_base_load_regional[region_id] + current_ev_load_regional[region_id]
            current_total_load_regional[region_id] = initial_total_load_region
            
            capacity_region = system_capacity_regional[region_id]
            grid_load_percentage_regional[region_id] = (initial_total_load_region / capacity_region) * 100 if capacity_region > 0 else 0.0
            
            initial_renew_gen_region = current_solar_gen_regional[region_id] + current_wind_gen_regional[region_id]
            renewable_ratio_regional[region_id] = (initial_renew_gen_region / initial_total_load_region * 100) if initial_total_load_region > 0 else 0.0

        self.grid_status = {
            # Regional Profiles (dictionaries of lists, keyed by region_id)
            "base_load_profiles_regional": base_load_profiles_regional,
            "solar_generation_profiles_regional": solar_generation_profiles_regional,
            "wind_generation_profiles_regional": wind_generation_profiles_regional,
            "system_capacity_regional": system_capacity_regional, # Dict of numbers, keyed by region_id
            
            # Global Settings (these are not regional)
            "peak_hours": peak_hours,
            "valley_hours": valley_hours,
            "normal_price": normal_price,
            "peak_price": peak_price,
            "valley_price": valley_price,
            
            # Current Regional State Values (dictionaries keyed by region_id)
            "current_base_load_regional": current_base_load_regional,
            "current_solar_gen_regional": current_solar_gen_regional,
            "current_wind_gen_regional": current_wind_gen_regional,
            "current_ev_load_regional": current_ev_load_regional, # Distributed EV load
            "current_total_load_regional": current_total_load_regional,
            "grid_load_percentage_regional": grid_load_percentage_regional,
            "renewable_ratio_regional": renewable_ratio_regional,
            
            # Global Current Values (price is global)
            "current_price": self._get_current_price(initial_hour),
        }
        logger.info(f"GridModel reset complete. Status initialized for regions: {self.region_ids}")

    def update_step(self, current_time, global_ev_load): # Input ev_load is global
        """更新电网在一个时间步的状态, 支持区域化负载和计算"""
        hour = current_time.hour
        if not (0 <= hour < 24):
             logger.error(f"Invalid hour ({hour}) for grid update. Using hour 0 as fallback.")
             hour = 0

        # --- EV Load Distribution ---
        # Distribute global_ev_load to regions proportionally to each region's system_capacity
        current_ev_load_regional_updated = {} 
        total_system_capacity_all_regions = sum(self.grid_status["system_capacity_regional"].values())
        
        if total_system_capacity_all_regions == 0:
            logger.warning(
                "Total system capacity across all regions is 0. "
                "Cannot distribute EV load proportionally. Setting EV load to 0 for all regions."
            )
            for region_id in self.region_ids:
                current_ev_load_regional_updated[region_id] = 0.0
        else:
            for region_id in self.region_ids:
                # Use .get for safety, though reset should ensure keys exist
                region_capacity = self.grid_status["system_capacity_regional"].get(region_id, 0)
                proportion = region_capacity / total_system_capacity_all_regions
                current_ev_load_regional_updated[region_id] = global_ev_load * proportion
        
        self.grid_status["current_ev_load_regional"] = current_ev_load_regional_updated

        # --- Regional Calculations ---
        for region_id in self.region_ids:
            # Get current hour's profile data for the region
            # Using .get on the profile dicts for safety, with fallbacks to default lists if a region was somehow missed post-reset
            base_load_profile_region = self.grid_status["base_load_profiles_regional"].get(region_id, [1000]*24)
            solar_gen_profile_region = self.grid_status["solar_generation_profiles_regional"].get(region_id, [0]*24)
            wind_gen_profile_region = self.grid_status["wind_generation_profiles_regional"].get(region_id, [100]*24)
            
            base_load_region = base_load_profile_region[hour]
            solar_gen_region = solar_gen_profile_region[hour]
            wind_gen_region = wind_gen_profile_region[hour]
            
            ev_load_region = self.grid_status["current_ev_load_regional"][region_id] # Already updated for current step

            # Calculate regional total load
            total_load_region = base_load_region + ev_load_region
            
            # Calculate regional grid load percentage
            system_capacity_region = self.grid_status["system_capacity_regional"].get(region_id, 0) # Default to 0 if missing
            grid_load_percentage_region = (total_load_region / system_capacity_region) * 100 if system_capacity_region > 0 else 0.0
            
            # Calculate regional renewable energy ratio
            total_renewable_region = solar_gen_region + wind_gen_region
            renewable_ratio_region = (total_renewable_region / total_load_region * 100) if total_load_region > 0 else 0.0

            # Update regional values in grid_status (directly updating the nested dictionaries)
            self.grid_status["current_base_load_regional"][region_id] = base_load_region
            self.grid_status["current_solar_gen_regional"][region_id] = solar_gen_region
            self.grid_status["current_wind_gen_regional"][region_id] = wind_gen_region
            self.grid_status["current_total_load_regional"][region_id] = total_load_region
            self.grid_status["grid_load_percentage_regional"][region_id] = grid_load_percentage_region
            self.grid_status["renewable_ratio_regional"][region_id] = renewable_ratio_region
            
            # logger.debug(
            #     f"Region {region_id} @ Hour {hour}: Base={base_load_region:.1f}, Solar={solar_gen_region:.1f}, "
            #     f"Wind={wind_gen_region:.1f}, EV={ev_load_region:.1f}, Total={total_load_region:.1f} "
            #     f"({grid_load_percentage_region:.1f}% of {system_capacity_region}kW), Renew%={renewable_ratio_region:.1f}%"
            # )

        # Update global current price (remains global)
        current_price = self._get_current_price(hour)
        self.grid_status["current_price"] = current_price
        
        # logger.debug(f"Grid Aggregated @ Hour {hour}: GlobalEVLoad={global_ev_load:.1f}kW, CurrentPrice={current_price}")


    def _get_current_price(self, hour):
        """根据小时获取电价 (remains global)"""
        if hour in self.grid_status.get("peak_hours", []): # peak_hours is global
            return self.grid_status.get("peak_price", 1.2)
        elif hour in self.grid_status.get("valley_hours", []): # valley_hours is global
            return self.grid_status.get("valley_price", 0.4)
        else:
            return self.grid_status.get("normal_price", 0.85)

    def get_status(self):
        """返回当前的电网状态字典 (now includes regional data)"""
        return self.grid_status.copy()
