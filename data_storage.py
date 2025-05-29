#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据存储模块 - 管理历史收益、需求预测和运营数据
"""

import sqlite3
import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)

class DataStorage:
    """数据存储管理类"""
    
    def __init__(self, db_path: str = "ev_charging_data.db"):
        self.db_path = db_path
        self._init_database()
    
    def _init_database(self):
        """初始化数据库表结构"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 历史收益表
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS revenue_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        date TEXT NOT NULL,
                        station_id TEXT,
                        charger_id TEXT,
                        daily_revenue REAL DEFAULT 0,
                        daily_energy REAL DEFAULT 0,
                        daily_sessions INTEGER DEFAULT 0,
                        avg_session_duration REAL DEFAULT 0,
                        peak_hour_revenue REAL DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # 需求历史表
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS demand_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        date TEXT NOT NULL,
                        hour INTEGER NOT NULL,
                        station_id TEXT,
                        demand_level REAL DEFAULT 0,
                        queue_length INTEGER DEFAULT 0,
                        utilization_rate REAL DEFAULT 0,
                        weather_condition TEXT,
                        day_type TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # 维护记录表
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS maintenance_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        charger_id TEXT NOT NULL,
                        maintenance_type TEXT NOT NULL,
                        description TEXT,
                        cost REAL DEFAULT 0,
                        duration_hours REAL DEFAULT 0,
                        technician TEXT,
                        status TEXT DEFAULT 'completed',
                        scheduled_date TEXT,
                        completed_date TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # 价格历史表
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS pricing_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        date TEXT NOT NULL,
                        hour INTEGER NOT NULL,
                        station_id TEXT,
                        base_price REAL NOT NULL,
                        dynamic_multiplier REAL DEFAULT 1.0,
                        final_price REAL NOT NULL,
                        demand_factor REAL DEFAULT 0,
                        grid_factor REAL DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                conn.commit()
                logger.info("数据库初始化完成")
                
        except Exception as e:
            logger.error(f"数据库初始化失败: {e}")
    
    def save_daily_revenue(self, date: str, chargers_data: List[Dict]):
        """保存每日收益数据"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                for charger in chargers_data:
                    if not isinstance(charger, dict):
                        continue
                        
                    charger_id = charger.get('charger_id', '')
                    station_id = charger.get('location', 'unknown')
                    daily_revenue = charger.get('daily_revenue', 0)
                    daily_energy = charger.get('daily_energy', 0)
                    
                    # 计算会话统计
                    sessions_count = len(charger.get('completed_sessions', []))
                    avg_duration = 0
                    if sessions_count > 0:
                        total_duration = sum(s.get('duration', 0) for s in charger.get('completed_sessions', []))
                        avg_duration = total_duration / sessions_count
                    
                    cursor.execute("""
                        INSERT OR REPLACE INTO revenue_history 
                        (date, station_id, charger_id, daily_revenue, daily_energy, 
                         daily_sessions, avg_session_duration, peak_hour_revenue)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (date, station_id, charger_id, daily_revenue, daily_energy,
                          sessions_count, avg_duration, daily_revenue * 0.3))
                
                conn.commit()
                logger.info(f"保存了 {len(chargers_data)} 个充电桩的收益数据")
                
        except Exception as e:
            logger.error(f"保存收益数据失败: {e}")
    
    def save_demand_data(self, date: str, hour: int, stations_data: List[Dict]):
        """保存需求数据"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                for station in stations_data:
                    station_id = station.get('station_id', '')
                    demand_level = station.get('demand_level', 0)
                    queue_length = station.get('total_queue_length', 0)
                    utilization_rate = station.get('utilization_rate', 0)
                    
                    # 简单的天气和日期类型模拟
                    weather = ['晴天', '阴天', '雨天'][hash(date + str(hour)) % 3]
                    day_type = '工作日' if datetime.strptime(date, '%Y-%m-%d').weekday() < 5 else '周末'
                    
                    cursor.execute("""
                        INSERT INTO demand_history 
                        (date, hour, station_id, demand_level, queue_length, 
                         utilization_rate, weather_condition, day_type)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (date, hour, station_id, demand_level, queue_length,
                          utilization_rate, weather, day_type))
                
                conn.commit()
                
        except Exception as e:
            logger.error(f"保存需求数据失败: {e}")
    
    def get_revenue_history(self, days: int = 30, station_id: str = None) -> List[Dict]:
        """获取历史收益数据"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                query = """
                    SELECT date, station_id, SUM(daily_revenue) as total_revenue,
                           SUM(daily_energy) as total_energy, SUM(daily_sessions) as total_sessions,
                           AVG(avg_session_duration) as avg_duration
                    FROM revenue_history 
                    WHERE date >= date('now', '-{} days')
                """.format(days)
                
                params = []
                if station_id:
                    query += " AND station_id = ?"
                    params.append(station_id)
                
                query += " GROUP BY date, station_id ORDER BY date DESC"
                
                cursor.execute(query, params)
                rows = cursor.fetchall()
                
                return [{
                    'date': row[0],
                    'station_id': row[1],
                    'total_revenue': row[2] or 0,
                    'total_energy': row[3] or 0,
                    'total_sessions': row[4] or 0,
                    'avg_duration': row[5] or 0
                } for row in rows]
                
        except Exception as e:
            logger.error(f"获取收益历史失败: {e}")
            return []
    
    def get_demand_prediction(self, days: int = 7, station_id: str = None) -> Dict:
        """基于历史数据生成需求预测"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 获取历史需求数据
                query = """
                    SELECT hour, AVG(demand_level) as avg_demand, 
                           AVG(utilization_rate) as avg_utilization,
                           day_type, weather_condition
                    FROM demand_history 
                    WHERE date >= date('now', '-30 days')
                """
                
                params = []
                if station_id:
                    query += " AND station_id = ?"
                    params.append(station_id)
                
                query += " GROUP BY hour, day_type ORDER BY hour"
                
                cursor.execute(query, params)
                rows = cursor.fetchall()
                
                if not rows:
                    # 如果没有历史数据，生成模拟预测
                    return self._generate_simulated_prediction(days)
                
                # 基于历史数据生成预测
                predictions = []
                base_date = datetime.now().date()
                
                for day in range(days):
                    pred_date = base_date + timedelta(days=day)
                    day_type = '工作日' if pred_date.weekday() < 5 else '周末'
                    
                    daily_pred = {
                        'date': pred_date.strftime('%Y-%m-%d'),
                        'day_type': day_type,
                        'hourly_demand': [],
                        'peak_demand': 0,
                        'avg_demand': 0
                    }
                    
                    total_demand = 0
                    for hour in range(24):
                        # 查找相似时间段的历史数据
                        similar_data = [r for r in rows if r[0] == hour and r[3] == day_type]
                        
                        if similar_data:
                            base_demand = similar_data[0][1] or 0
                            base_util = similar_data[0][2] or 0
                        else:
                            # 使用典型模式
                            base_demand = self._get_typical_demand(hour, day_type)
                            base_util = base_demand * 0.8
                        
                        # 添加一些随机变化
                        import random
                        variation = random.uniform(0.85, 1.15)
                        predicted_demand = base_demand * variation
                        
                        daily_pred['hourly_demand'].append({
                            'hour': hour,
                            'demand': round(predicted_demand, 2),
                            'utilization': round(base_util * variation, 2)
                        })
                        
                        total_demand += predicted_demand
                    
                    daily_pred['avg_demand'] = round(total_demand / 24, 2)
                    daily_pred['peak_demand'] = round(max(h['demand'] for h in daily_pred['hourly_demand']), 2)
                    
                    predictions.append(daily_pred)
                
                return {
                    'predictions': predictions,
                    'confidence': 0.75,
                    'model_type': 'historical_analysis',
                    'data_points': len(rows)
                }
                
        except Exception as e:
            logger.error(f"生成需求预测失败: {e}")
            return self._generate_simulated_prediction(days)
    
    def _get_typical_demand(self, hour: int, day_type: str) -> float:
        """获取典型时段的需求模式"""
        if day_type == '工作日':
            # 工作日模式：早晚高峰
            if 7 <= hour <= 9 or 17 <= hour <= 19:
                return 0.8
            elif 10 <= hour <= 16:
                return 0.4
            elif 20 <= hour <= 22:
                return 0.6
            else:
                return 0.2
        else:
            # 周末模式：相对平缓
            if 10 <= hour <= 14 or 19 <= hour <= 21:
                return 0.6
            elif 15 <= hour <= 18:
                return 0.5
            else:
                return 0.3
    
    def _generate_simulated_prediction(self, days: int) -> Dict:
        """生成模拟预测数据（当没有历史数据时使用）"""
        import random
        
        predictions = []
        base_date = datetime.now().date()
        
        for day in range(days):
            pred_date = base_date + timedelta(days=day)
            day_type = '工作日' if pred_date.weekday() < 5 else '周末'
            
            daily_pred = {
                'date': pred_date.strftime('%Y-%m-%d'),
                'day_type': day_type,
                'hourly_demand': [],
                'peak_demand': 0,
                'avg_demand': 0
            }
            
            total_demand = 0
            for hour in range(24):
                base_demand = self._get_typical_demand(hour, day_type)
                variation = random.uniform(0.8, 1.2)
                predicted_demand = base_demand * variation
                
                daily_pred['hourly_demand'].append({
                    'hour': hour,
                    'demand': round(predicted_demand, 2),
                    'utilization': round(predicted_demand * 0.8, 2)
                })
                
                total_demand += predicted_demand
            
            daily_pred['avg_demand'] = round(total_demand / 24, 2)
            daily_pred['peak_demand'] = round(max(h['demand'] for h in daily_pred['hourly_demand']), 2)
            
            predictions.append(daily_pred)
        
        return {
            'predictions': predictions,
            'confidence': 0.6,
            'model_type': 'simulated',
            'data_points': 0
        }
    
    def save_maintenance_record(self, charger_id: str, maintenance_type: str, 
                              description: str, cost: float = 0, 
                              duration_hours: float = 0, technician: str = ""):
        """保存维护记录"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    INSERT INTO maintenance_history 
                    (charger_id, maintenance_type, description, cost, 
                     duration_hours, technician, completed_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (charger_id, maintenance_type, description, cost,
                      duration_hours, technician, datetime.now().strftime('%Y-%m-%d')))
                
                conn.commit()
                logger.info(f"保存维护记录: {charger_id} - {maintenance_type}")
                
        except Exception as e:
            logger.error(f"保存维护记录失败: {e}")
    
    def get_maintenance_history(self, days: int = 30, charger_id: str = None) -> List[Dict]:
        """获取维护历史"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                query = """
                    SELECT charger_id, maintenance_type, description, cost,
                           duration_hours, technician, completed_date
                    FROM maintenance_history 
                    WHERE completed_date >= date('now', '-{} days')
                """.format(days)
                
                params = []
                if charger_id:
                    query += " AND charger_id = ?"
                    params.append(charger_id)
                
                query += " ORDER BY completed_date DESC"
                
                cursor.execute(query, params)
                rows = cursor.fetchall()
                
                return [{
                    'charger_id': row[0],
                    'maintenance_type': row[1],
                    'description': row[2],
                    'cost': row[3] or 0,
                    'duration_hours': row[4] or 0,
                    'technician': row[5] or '',
                    'completed_date': row[6]
                } for row in rows]
                
        except Exception as e:
            logger.error(f"获取维护历史失败: {e}")
            return []
    
    def get_usage_history(self, days: int = 30, station_id: str = None) -> List[Dict]:
        """获取使用历史数据"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 从需求历史表获取使用数据
                query = """
                    SELECT date, hour, station_id, demand_level as total_energy,
                           utilization_rate, day_type
                    FROM demand_history 
                    WHERE date >= date('now', '-{} days')
                """.format(days)
                
                params = []
                if station_id:
                    query += " AND station_id = ?"
                    params.append(station_id)
                
                query += " ORDER BY date DESC, hour DESC"
                
                cursor.execute(query, params)
                rows = cursor.fetchall()
                
                return [{
                    'date': row[0],
                    'hour': row[1],
                    'station_id': row[2],
                    'total_energy': row[3] or 0,
                    'utilization_rate': row[4] or 0,
                    'day_type': row[5] or '工作日'
                } for row in rows]
                
        except Exception as e:
            logger.error(f"获取使用历史失败: {e}")
            return []
    
    def cleanup_old_data(self, days_to_keep: int = 90):
        """清理旧数据"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                tables = ['revenue_history', 'demand_history', 'maintenance_history', 'pricing_history']
                
                for table in tables:
                    cursor.execute(f"""
                        DELETE FROM {table} 
                        WHERE created_at < date('now', '-{days_to_keep} days')
                    """)
                
                conn.commit()
                logger.info(f"清理了超过 {days_to_keep} 天的旧数据")
                
        except Exception as e:
            logger.error(f"清理旧数据失败: {e}")

# 全局数据存储实例
data_storage = DataStorage()