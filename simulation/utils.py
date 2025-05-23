import math
import random
import logging

logger = logging.getLogger(__name__)

def calculate_distance(pos1, pos2):
    """计算两个地理位置点之间的大致距离 (km)"""
    if not isinstance(pos1, dict) or not isinstance(pos2, dict) or \
       'lat' not in pos1 or 'lng' not in pos1 or \
       'lat' not in pos2 or 'lng' not in pos2:
        logger.warning(f"Invalid position format for distance calculation: {pos1}, {pos2}")
        return float('inf') # 返回无穷大表示无效距离

    lat1 = pos1.get('lat', 0)
    lng1 = pos1.get('lng', 0)
    lat2 = pos2.get('lat', 0)
    lng2 = pos2.get('lng', 0)

    # 确保坐标是有效的数字
    if not all(isinstance(c, (int, float)) for c in [lat1, lng1, lat2, lng2]):
        logger.warning(f"Non-numeric coordinates found: lat1={lat1}, lng1={lng1}, lat2={lat2}, lng2={lng2}")
        return float('inf')

    # 简单的欧几里得距离乘以转换系数 (这是一个粗略的近似值)
    # 对于小范围，这个近似还可以接受
    distance_degrees = math.sqrt((lat1 - lat2)**2 + (lng1 - lng2)**2)
    distance_km = distance_degrees * 111  # 粗略转换: 1度约等于111公里
    return distance_km

def get_random_location(map_bounds):
    """在定义的地图边界内生成一个随机位置"""
    if not map_bounds or not all(k in map_bounds for k in ['lat_min', 'lat_max', 'lng_min', 'lng_max']):
        logger.error("Map bounds not properly initialized. Using default fallback region.")
        # 如果边界无效，返回一个默认区域的中心点
        return {"lat": 30.75, "lng": 114.25}

    try:
        lat = random.uniform(map_bounds['lat_min'], map_bounds['lat_max'])
        lng = random.uniform(map_bounds['lng_min'], map_bounds['lng_max'])
        return {"lat": lat, "lng": lng}
    except Exception as e:
        logger.error(f"Error generating random location: {e}. Using default fallback.", exc_info=True)
        return {"lat": 30.75, "lng": 114.25}