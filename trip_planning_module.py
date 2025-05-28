# -*- coding: utf-8 -*-
"""
行程规划模块
提供全面的出行规划功能，包括导航路线显示、预计到达时间计算、
沿途充电站推荐和路线优化建议
"""

import math
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class RoutePoint:
    """路线点数据类"""
    lat: float
    lng: float
    name: str = ""
    type: str = "waypoint"  # waypoint, charger, destination
    eta: Optional[datetime] = None
    distance_from_start: float = 0.0

@dataclass
class ChargingStopRecommendation:
    """充电站推荐数据类"""
    station_id: str
    name: str
    lat: float
    lng: float
    distance_from_route: float
    detour_distance: float
    available_chargers: int
    max_power: float
    current_price: float
    estimated_charging_time: int  # 分钟
    estimated_cost: float
    rating: float
    recommended_soc: float  # 推荐充电到的电量
    urgency_level: str  # low, medium, high, critical

@dataclass
class RouteOptimization:
    """路线优化建议数据类"""
    optimization_type: str  # time, cost, energy, comfort
    description: str
    potential_savings: Dict[str, float]  # time_minutes, cost_yuan, energy_kwh
    alternative_route: List[RoutePoint]
    confidence: float  # 0-1

class TripPlanningEngine:
    """行程规划引擎"""
    
    def __init__(self):
        self.charging_stations = []
        self.traffic_data = {}
        self.weather_data = {}
        self.energy_consumption_model = {
            'base_consumption': 0.18,  # kWh/km
            'speed_factor': 0.002,     # 速度影响因子
            'weather_factor': 0.1,     # 天气影响因子
            'terrain_factor': 0.05     # 地形影响因子
        }
    
    def calculate_distance(self, point1: Dict, point2: Dict) -> float:
        """计算两点间距离（公里）"""
        lat1, lng1 = point1['lat'], point1['lng']
        lat2, lng2 = point2['lat'], point2['lng']
        
        # 使用Haversine公式
        R = 6371  # 地球半径（公里）
        dlat = math.radians(lat2 - lat1)
        dlng = math.radians(lng2 - lng1)
        a = (math.sin(dlat/2) * math.sin(dlat/2) + 
             math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * 
             math.sin(dlng/2) * math.sin(dlng/2))
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        return R * c
    
    def estimate_energy_consumption(self, distance_km: float, avg_speed: float, 
                                  weather_condition: str = "clear") -> float:
        """估算能耗（kWh）"""
        base = self.energy_consumption_model['base_consumption'] * distance_km
        
        # 速度影响
        speed_impact = self.energy_consumption_model['speed_factor'] * (avg_speed - 60) ** 2
        
        # 天气影响
        weather_multiplier = {
            'clear': 1.0,
            'rain': 1.1,
            'snow': 1.2,
            'wind': 1.05,
            'hot': 1.15,  # 空调使用
            'cold': 1.25  # 暖气使用
        }.get(weather_condition, 1.0)
        
        return base * (1 + speed_impact) * weather_multiplier
    
    def calculate_eta(self, route: List[RoutePoint], start_time: datetime, 
                     avg_speed: float = 60) -> List[RoutePoint]:
        """计算路线各点的预计到达时间"""
        updated_route = []
        current_time = start_time
        total_distance = 0
        
        for i, point in enumerate(route):
            if i == 0:
                point.eta = current_time
                point.distance_from_start = 0
            else:
                # 计算到前一个点的距离
                prev_point = route[i-1]
                segment_distance = self.calculate_distance(
                    {'lat': prev_point.lat, 'lng': prev_point.lng},
                    {'lat': point.lat, 'lng': point.lng}
                )
                total_distance += segment_distance
                point.distance_from_start = total_distance
                
                # 计算行驶时间
                travel_time_hours = segment_distance / avg_speed
                current_time += timedelta(hours=travel_time_hours)
                point.eta = current_time
            
            updated_route.append(point)
        
        return updated_route
    
    def find_charging_stations_along_route(self, route: List[RoutePoint], 
                                         chargers_data: List[dict] = None,
                                         max_detour_km: float = 5.0) -> List[ChargingStopRecommendation]:
        """查找沿途充电站"""
        recommendations = []
        
        # 如果没有提供真实充电桩数据，使用空列表
        if chargers_data is None:
            chargers_data = []
            
        # 使用真实的充电桩数据
        available_stations = []
        for charger in chargers_data:
            if isinstance(charger, dict) and charger.get('status') == 'available':
                # 从position字段获取坐标信息
                position = charger.get('position', {})
                station_data = {
                    'station_id': charger.get('station_id', charger.get('charger_id', 'Unknown')),
                    'name': f"充电站 {charger.get('station_id', charger.get('charger_id', 'Unknown'))}",
                    'lat': position.get('lat', 0),
                    'lng': position.get('lng', 0),
                    'available_chargers': 1 if charger.get('status') == 'available' else 0,
                    'total_chargers': 1,
                    'max_power': charger.get('max_power', 50),
                    'current_price': charger.get('price_per_kwh', 1.2),
                    'rating': 4.0  # 默认评分
                }
                available_stations.append(station_data)
        
        for station in available_stations:
            # 找到距离充电站最近的路线点
            min_distance = float('inf')
            closest_route_point = None
            
            for point in route:
                distance = self.calculate_distance(
                    {'lat': point.lat, 'lng': point.lng},
                    {'lat': station['lat'], 'lng': station['lng']}
                )
                if distance < min_distance:
                    min_distance = distance
                    closest_route_point = point
            
            # 如果充电站在可接受的绕行距离内
            if min_distance <= max_detour_km:
                # 估算充电时间和费用
                estimated_charging_time = self._estimate_charging_time(
                    station['max_power'], 30, 80  # 从30%充到80%
                )
                estimated_cost = self._estimate_charging_cost(
                    station['current_price'], 50  # 充电50kWh
                )
                
                # 确定紧急程度
                urgency = self._determine_urgency(closest_route_point.distance_from_start)
                
                recommendation = ChargingStopRecommendation(
                    station_id=station['station_id'],
                    name=station['name'],
                    lat=station['lat'],
                    lng=station['lng'],
                    distance_from_route=min_distance,
                    detour_distance=min_distance * 2,  # 往返绕行距离
                    available_chargers=station['available_chargers'],
                    max_power=station['max_power'],
                    current_price=station['current_price'],
                    estimated_charging_time=estimated_charging_time,
                    estimated_cost=estimated_cost,
                    rating=station['rating'],
                    recommended_soc=80.0,
                    urgency_level=urgency
                )
                recommendations.append(recommendation)
        
        # 按距离排序
        recommendations.sort(key=lambda x: x.distance_from_route)
        return recommendations
    
    def _estimate_charging_time(self, max_power: float, start_soc: float, target_soc: float) -> int:
        """估算充电时间（分钟）"""
        # 简化的充电时间计算
        battery_capacity = 60  # kWh，假设电池容量
        energy_needed = battery_capacity * (target_soc - start_soc) / 100
        
        # 考虑充电功率衰减
        avg_power = max_power * 0.8  # 平均功率约为最大功率的80%
        charging_time_hours = energy_needed / avg_power
        
        return int(charging_time_hours * 60)
    
    def _estimate_charging_cost(self, price_per_kwh: float, energy_kwh: float) -> float:
        """估算充电费用"""
        return price_per_kwh * energy_kwh
    
    def _determine_urgency(self, distance_from_start: float) -> str:
        """根据行程进度确定充电紧急程度"""
        if distance_from_start < 50:
            return "low"
        elif distance_from_start < 150:
            return "medium"
        elif distance_from_start < 250:
            return "high"
        else:
            return "critical"
    
    def generate_route_optimizations(self, route: List[RoutePoint], 
                                   user_preferences: Dict) -> List[RouteOptimization]:
        """生成路线优化建议"""
        optimizations = []
        
        # 时间优化建议
        if user_preferences.get('priority') != 'time':
            time_opt = RouteOptimization(
                optimization_type="time",
                description="选择高速路线可节省约15分钟行程时间",
                potential_savings={
                    'time_minutes': 15,
                    'cost_yuan': -8,  # 可能增加过路费
                    'energy_kwh': 2   # 可能增加能耗
                },
                alternative_route=self._generate_alternative_route(route, "time"),
                confidence=0.85
            )
            optimizations.append(time_opt)
        
        # 经济性优化建议
        if user_preferences.get('priority') != 'cost':
            cost_opt = RouteOptimization(
                optimization_type="cost",
                description="避开收费路段可节省12元过路费",
                potential_savings={
                    'time_minutes': -10,  # 可能增加时间
                    'cost_yuan': 12,
                    'energy_kwh': -1      # 可能节省能耗
                },
                alternative_route=self._generate_alternative_route(route, "cost"),
                confidence=0.92
            )
            optimizations.append(cost_opt)
        
        # 能耗优化建议
        if user_preferences.get('priority') != 'energy':
            energy_opt = RouteOptimization(
                optimization_type="energy",
                description="选择平缓路线可节省约3kWh电量",
                potential_savings={
                    'time_minutes': -5,
                    'cost_yuan': 0,
                    'energy_kwh': 3
                },
                alternative_route=self._generate_alternative_route(route, "energy"),
                confidence=0.78
            )
            optimizations.append(energy_opt)
        
        return optimizations
    
    def _generate_alternative_route(self, original_route: List[RoutePoint], 
                                  optimization_type: str) -> List[RoutePoint]:
        """生成替代路线（简化实现）"""
        # 这里是简化实现，实际应该调用路线规划API
        alternative = []
        for i, point in enumerate(original_route):
            new_point = RoutePoint(
                lat=point.lat + (0.001 if optimization_type == "time" else -0.001),
                lng=point.lng + (0.001 if optimization_type == "cost" else -0.001),
                name=point.name,
                type=point.type
            )
            alternative.append(new_point)
        return alternative
    
    def plan_comprehensive_trip(self, start_pos: Dict, end_pos: Dict, 
                              user_preferences: Dict, current_soc: float, 
                              chargers_data: List[dict] = None) -> Dict:
        """综合行程规划"""
        # 生成基础路线
        route = self._generate_base_route(start_pos, end_pos)
        
        # 计算ETA
        start_time = datetime.now()
        route_with_eta = self.calculate_eta(route, start_time)
        
        # 查找沿途充电站
        charging_recommendations = self.find_charging_stations_along_route(route_with_eta, chargers_data)
        
        # 生成优化建议
        optimizations = self.generate_route_optimizations(route_with_eta, user_preferences)
        
        # 计算总体统计
        total_distance = route_with_eta[-1].distance_from_start if route_with_eta else 0
        total_time = (route_with_eta[-1].eta - start_time).total_seconds() / 60 if route_with_eta else 0
        estimated_energy = self.estimate_energy_consumption(total_distance, 60)
        
        return {
            'route': route_with_eta,
            'charging_recommendations': charging_recommendations,
            'optimizations': optimizations,
            'statistics': {
                'total_distance_km': total_distance,
                'estimated_time_minutes': total_time,
                'estimated_energy_kwh': estimated_energy,
                'estimated_arrival': route_with_eta[-1].eta if route_with_eta else None,
                'charging_stops_needed': self._estimate_charging_stops_needed(total_distance, current_soc)
            }
        }
    
    def _generate_base_route(self, start_pos: Dict, end_pos: Dict) -> List[RoutePoint]:
        """生成基础路线"""
        route = []
        
        # 起点
        start_point = RoutePoint(
            lat=start_pos['lat'],
            lng=start_pos['lng'],
            name="出发地",
            type="start"
        )
        route.append(start_point)
        
        # 生成中间路径点（简化实现）
        num_waypoints = 3
        for i in range(1, num_waypoints + 1):
            t = i / (num_waypoints + 1)
            waypoint = RoutePoint(
                lat=start_pos['lat'] + t * (end_pos['lat'] - start_pos['lat']),
                lng=start_pos['lng'] + t * (end_pos['lng'] - start_pos['lng']),
                name=f"途经点{i}",
                type="waypoint"
            )
            route.append(waypoint)
        
        # 终点
        end_point = RoutePoint(
            lat=end_pos['lat'],
            lng=end_pos['lng'],
            name="目的地",
            type="destination"
        )
        route.append(end_point)
        
        return route
    
    def _estimate_charging_stops_needed(self, total_distance: float, current_soc: float) -> int:
        """估算需要的充电次数"""
        vehicle_range = 400  # km，假设车辆续航
        current_range = vehicle_range * current_soc / 100
        
        if total_distance <= current_range:
            return 0
        
        remaining_distance = total_distance - current_range
        charging_range = vehicle_range * 0.6  # 每次充电增加60%续航
        
        return math.ceil(remaining_distance / charging_range)

# 全局实例
trip_planning_engine = TripPlanningEngine()