#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据存储模块 - 管理运营商数据存储和分析
"""

import sqlite3
import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from collections import defaultdict
import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)

class OperatorDataStorage:
    """运营商数据存储管理类"""
    
    def __init__(self, db_path: str = "operator_data.db"):
        self.db_path = db_path
        self._init_database()
    
    def _init_database(self):
        """初始化数据库表结构"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 实时运行数据表
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS realtime_data (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        charger_id TEXT NOT NULL,
                        station_id TEXT NOT NULL,
                        status TEXT NOT NULL,
                        power_output REAL DEFAULT 0,
                        queue_length INTEGER DEFAULT 0,
                        current_user TEXT,
                        soc_start REAL,
                        soc_current REAL,
                        session_start TIMESTAMP,
                        utilization_rate REAL DEFAULT 0
                    )
                """)
                
                # 充电会话记录表
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS charging_sessions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id TEXT UNIQUE NOT NULL,
                        charger_id TEXT NOT NULL,
                        station_id TEXT NOT NULL,
                        user_id TEXT NOT NULL,
                        start_time TIMESTAMP NOT NULL,
                        end_time TIMESTAMP,
                        duration_minutes REAL,
                        energy_kwh REAL DEFAULT 0,
                        cost REAL DEFAULT 0,
                        revenue REAL DEFAULT 0,
                        start_soc REAL,
                        end_soc REAL,
                        price_per_kwh REAL,
                        service_fee REAL DEFAULT 0
                    )
                """)
                
                # 财务记录表
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS financial_records (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        date DATE NOT NULL,
                        hour INTEGER,
                        station_id TEXT NOT NULL,
                        revenue REAL DEFAULT 0,
                        electricity_cost REAL DEFAULT 0,
                        service_cost REAL DEFAULT 0,
                        profit REAL DEFAULT 0,
                        sessions_count INTEGER DEFAULT 0,
                        energy_delivered REAL DEFAULT 0,
                        avg_price_per_kwh REAL
                    )
                """)
                
                # 站点配置表
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS station_config (
                        station_id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        location_lat REAL,
                        location_lng REAL,
                        total_chargers INTEGER DEFAULT 0,
                        fast_chargers INTEGER DEFAULT 0,
                        normal_chargers INTEGER DEFAULT 0,
                        base_price REAL DEFAULT 0.85,
                        peak_multiplier REAL DEFAULT 1.5,
                        valley_multiplier REAL DEFAULT 0.6,
                        service_fee_rate REAL DEFAULT 0.2,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # 告警记录表
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS alerts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        alert_id TEXT UNIQUE NOT NULL,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        charger_id TEXT,
                        station_id TEXT,
                        alert_type TEXT NOT NULL,
                        severity TEXT NOT NULL,
                        message TEXT NOT NULL,
                        status TEXT DEFAULT 'active',
                        resolved_at TIMESTAMP,
                        resolved_by TEXT,
                        resolution_notes TEXT
                    )
                """)
                
                # 维护工单表
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS maintenance_orders (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        order_id TEXT UNIQUE NOT NULL,
                        charger_id TEXT NOT NULL,
                        station_id TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        scheduled_at TIMESTAMP,
                        completed_at TIMESTAMP,
                        issue_type TEXT NOT NULL,
                        description TEXT,
                        priority TEXT DEFAULT 'normal',
                        status TEXT DEFAULT 'pending',
                        technician TEXT,
                        cost REAL DEFAULT 0,
                        parts_replaced TEXT
                    )
                """)
                
                # 需求预测表
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS demand_forecast (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        forecast_date DATE NOT NULL,
                        station_id TEXT NOT NULL,
                        hour INTEGER NOT NULL,
                        predicted_sessions INTEGER,
                        predicted_energy REAL,
                        predicted_queue_length REAL,
                        confidence_level REAL,
                        model_version TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(forecast_date, station_id, hour)
                    )
                """)
                
                conn.commit()
                logger.info("运营商数据库初始化完成")
                
        except Exception as e:
            logger.error(f"数据库初始化失败: {e}")
    
    # === 实时数据管理 ===
    
    def save_realtime_snapshot(self, chargers_data: List[Dict], timestamp: datetime):
        """保存实时数据快照"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                for charger in chargers_data:
                    cursor.execute("""
                        INSERT INTO realtime_data 
                        (timestamp, charger_id, station_id, status, power_output, 
                         queue_length, current_user, utilization_rate)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        timestamp,
                        charger.get('charger_id'),
                        charger.get('location', 'unknown'),
                        charger.get('status', 'unknown'),
                        charger.get('current_power', 0),
                        len(charger.get('queue', [])),
                        charger.get('current_user'),
                        charger.get('utilization_rate', 0)
                    ))
                
                conn.commit()
                
        except Exception as e:
            logger.error(f"保存实时数据失败: {e}")
    
    def get_latest_station_status(self) -> Dict[str, Dict]:
        """获取各站点最新状态"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                # 使用SQLite兼容的子查询方式获取每个充电桩的最新记录
                query = """
                    SELECT 
                        station_id,
                        COUNT(DISTINCT charger_id) as total_chargers,
                        SUM(CASE WHEN status = 'available' THEN 1 ELSE 0 END) as available,
                        SUM(CASE WHEN status = 'occupied' THEN 1 ELSE 0 END) as occupied,
                        SUM(CASE WHEN status = 'failure' THEN 1 ELSE 0 END) as failed,
                        AVG(utilization_rate) as avg_utilization,
                        SUM(queue_length) as total_queue
                    FROM (
                        SELECT r.*
                        FROM realtime_data r
                        INNER JOIN (
                            SELECT charger_id, MAX(timestamp) as max_time
                            FROM realtime_data
                            GROUP BY charger_id
                        ) m ON r.charger_id = m.charger_id AND r.timestamp = m.max_time
                    ) latest
                    GROUP BY station_id
                """
                
                df = pd.read_sql_query(query, conn)
                # 将DataFrame转换为字典，使用station_id作为键
                result = {}
                for _, row in df.iterrows():
                    result[row['station_id']] = row.to_dict()
                return result
                
        except Exception as e:
            logger.error(f"获取站点状态失败: {e}")
            return {}
    
    # === 充电会话管理 ===
    
    def save_charging_session(self, session_data: Dict):
        """保存充电会话记录"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    INSERT OR REPLACE INTO charging_sessions 
                    (session_id, charger_id, station_id, user_id, start_time, 
                     end_time, duration_minutes, energy_kwh, cost, revenue,
                     start_soc, end_soc, price_per_kwh, service_fee)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    session_data.get('session_id'),
                    session_data.get('charger_id'),
                    session_data.get('station_id'),
                    session_data.get('user_id'),
                    session_data.get('start_time'),
                    session_data.get('end_time'),
                    session_data.get('duration_minutes', 0),
                    session_data.get('energy_kwh', 0),
                    session_data.get('cost', 0),
                    session_data.get('revenue', 0),
                    session_data.get('start_soc', 0),
                    session_data.get('end_soc', 0),
                    session_data.get('price_per_kwh', 0),
                    session_data.get('service_fee', 0)
                ))
                
                conn.commit()
                
        except Exception as e:
            logger.error(f"保存充电会话失败: {e}")
    
    # === 财务分析 ===


    def get_financial_summary(self, start_date: str, end_date: str, 
                            station_id: Optional[str] = None) -> pd.DataFrame:
        """获取财务汇总数据，支持按小时聚合"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                # --- START OF MODIFICATION ---
                # 查询语句改为按小时聚合 (strftime('%Y-%m-%d %H:00:00'))
                query = """
                    SELECT 
                        strftime('%Y-%m-%d %H:00:00', start_time) as datetime_hour,
                        station_id,
                        COUNT(*) as sessions_count,
                        SUM(energy_kwh) as total_energy,
                        SUM(revenue) as total_revenue,
                        SUM(cost) as total_cost,
                        SUM(revenue) - SUM(cost) as total_profit,
                        AVG(price_per_kwh) as avg_price,
                        AVG(duration_minutes) as avg_duration
                    FROM charging_sessions
                    WHERE start_time BETWEEN ? AND ?
                """
                # --- END OF MODIFICATION ---
                
                # 调整日期范围以确保包含 end_date 的所有小时
                start_dt_str = f"{start_date} 00:00:00"
                end_dt_str = f"{end_date} 23:59:59"
                
                params = [start_dt_str, end_dt_str]
                if station_id:
                    query += " AND station_id = ?"
                    params.append(station_id)
                
                # 按小时和站点分组
                query += " GROUP BY datetime_hour, station_id ORDER BY datetime_hour, station_id"
                
                df = pd.read_sql_query(query, conn, params=params)
                logger.info(f"Financial summary query returned {len(df)} hourly records for period {start_date} to {end_date}.")
                return df
                
        except Exception as e:
            logger.error(f"获取财务汇总失败: {e}")
            return pd.DataFrame()
    
    def save_hourly_financial_record(self, record: Dict):
        """保存小时级财务记录"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    INSERT OR REPLACE INTO financial_records
                    (date, hour, station_id, revenue, electricity_cost, 
                     service_cost, profit, sessions_count, energy_delivered, avg_price_per_kwh)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    record.get('date'),
                    record.get('hour'),
                    record.get('station_id'),
                    record.get('revenue', 0),
                    record.get('electricity_cost', 0),
                    record.get('service_cost', 0),
                    record.get('profit', 0),
                    record.get('sessions_count', 0),
                    record.get('energy_delivered', 0),
                    record.get('avg_price_per_kwh', 0)
                ))
                
                conn.commit()
                
        except Exception as e:
            logger.error(f"保存财务记录失败: {e}")
    
    # === 告警管理 ===

    def create_alert(self, alert_data: Dict) -> str:
        """创建告警，增加重复告警检查"""
        try:
            # --- START OF FIX: 防止重复告警 ---
            # 对于特定类型的告警，如果已存在一个活跃的同类告警，则不重复创建。
            # 例如，一个充电桩的故障告警，只要还是 active，就不再创建新的。
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 检查是否存在相同的、仍在活跃的告警
                query = "SELECT alert_id FROM alerts WHERE status = 'active' AND alert_type = ?"
                params = [alert_data.get('alert_type')]
                
                if alert_data.get('charger_id'):
                    query += " AND charger_id = ?"
                    params.append(alert_data.get('charger_id'))
                elif alert_data.get('station_id'):
                    query += " AND station_id = ?"
                    params.append(alert_data.get('station_id'))

                cursor.execute(query, tuple(params))
                existing_alert = cursor.fetchone()

                if existing_alert:
                    logger.debug(f"Skipping duplicate active alert for type: {alert_data.get('alert_type')}, target: {alert_data.get('charger_id') or alert_data.get('station_id')}")
                    return existing_alert[0] # 返回已存在的告警ID
            # --- END OF FIX ---

            alert_id = f"ALERT_{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{alert_data.get('charger_id', 'SYS')}"
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO alerts 
                    (alert_id, charger_id, station_id, alert_type, 
                     severity, message, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    alert_id,
                    alert_data.get('charger_id'),
                    alert_data.get('station_id'),
                    alert_data.get('alert_type'),
                    alert_data.get('severity', 'info'),
                    alert_data.get('message'),
                    'active'
                ))
                conn.commit()
                logger.info(f"Created new alert: {alert_id} - {alert_data.get('message')}")
                return alert_id
                
        except Exception as e:
            logger.error(f"创建告警失败: {e}")
            return ""
    def get_active_alerts(self) -> List[Dict]:
        """获取活跃告警"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                query = """
                    SELECT * FROM alerts 
                    WHERE status = 'active' 
                    ORDER BY severity DESC, timestamp DESC
                """
                
                df = pd.read_sql_query(query, conn)
                return df.to_dict('records')
                
        except Exception as e:
            logger.error(f"获取活跃告警失败: {e}")
            return []
    
    def resolve_alert(self, alert_id: str, resolved_by: str, notes: str = ""):
        """解决告警"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    UPDATE alerts 
                    SET status = 'resolved', 
                        resolved_at = CURRENT_TIMESTAMP,
                        resolved_by = ?,
                        resolution_notes = ?
                    WHERE alert_id = ?
                """, (resolved_by, notes, alert_id))
                
                conn.commit()
                
        except Exception as e:
            logger.error(f"解决告警失败: {e}")
    
    # === 维护管理 ===
    
    def create_maintenance_order(self, order_data: Dict) -> str:
        """创建维护工单"""
        try:
            order_id = f"MO_{datetime.now().strftime('%Y%m%d%H%M%S')}_{order_data.get('charger_id')}"
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    INSERT INTO maintenance_orders
                    (order_id, charger_id, station_id, issue_type, 
                     description, priority, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    order_id,
                    order_data.get('charger_id'),
                    order_data.get('station_id'),
                    order_data.get('issue_type'),
                    order_data.get('description'),
                    order_data.get('priority', 'normal'),
                    'pending'
                ))
                
                conn.commit()
                return order_id
                
        except Exception as e:
            logger.error(f"创建维护工单失败: {e}")
            return ""
    
    def get_maintenance_history(self, days: int = 30, 
                              station_id: Optional[str] = None) -> pd.DataFrame:
        """获取维护历史"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                query = """
                    SELECT * FROM maintenance_orders
                    WHERE created_at >= date('now', ? || ' days')
                """
                
                params = [f'-{days}']
                if station_id:
                    query += " AND station_id = ?"
                    params.append(station_id)
                
                query += " ORDER BY created_at DESC"
                
                return pd.read_sql_query(query, conn, params=params)
                
        except Exception as e:
            logger.error(f"获取维护历史失败: {e}")
            return pd.DataFrame()
    def get_historical_demand_patterns(self, station_id: str, days: int = 28) -> Dict:
        """
        获取站点的历史需求模式，用于预测。
        返回按 (星期几, 小时) 聚合的平均会话数和每日趋势。
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                # 查询过去N天的每小时会话数
                query = """
                    SELECT 
                        strftime('%Y-%m-%d', start_time) as date,
                        strftime('%w', start_time) as weekday, -- 0=Sunday, 1=Monday, ..., 6=Saturday
                        strftime('%H', start_time) as hour,
                        COUNT(*) as sessions
                    FROM charging_sessions
                    WHERE station_id = ? AND start_time >= date('now', ? || ' days')
                    GROUP BY date, hour
                """
                df = pd.read_sql_query(query, conn, params=[station_id, f'-{days}'])

                if df.empty:
                    logger.warning(f"No historical data found for station {station_id} in the last {days} days.")
                    return {"hourly_avg": pd.DataFrame(), "daily_trend": 0.0}

                # 计算每日总会话数以分析趋势
                daily_totals = df.groupby('date')['sessions'].sum()
                # 简单的线性回归来找趋势
                if len(daily_totals) > 1:
                    x = np.arange(len(daily_totals))
                    y = daily_totals.values
                    # 使用 numpy.polyfit 进行线性回归
                    coeffs = np.polyfit(x, y, 1)
                    daily_trend = coeffs[0] # 斜率，即每日会话数的平均增长量
                else:
                    daily_trend = 0.0

                # 计算按 (星期几, 小时) 聚合的平均会话数
                df['weekday'] = df['weekday'].astype(int)
                df['hour'] = df['hour'].astype(int)
                hourly_avg = df.groupby(['weekday', 'hour'])['sessions'].mean().reset_index()
                
                logger.info(f"Generated historical demand patterns for station {station_id}. Daily trend: {daily_trend:.2f} sessions/day.")
                return {"hourly_avg": hourly_avg, "daily_trend": daily_trend}

        except Exception as e:
            logger.error(f"获取历史需求模式失败: {e}")
            return {"hourly_avg": pd.DataFrame(), "daily_trend": 0.0}
    # === 需求预测 ===
    
    def save_demand_forecast(self, forecast_data: List[Dict]):
        """保存需求预测数据"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                for forecast in forecast_data:
                    cursor.execute("""
                        INSERT OR REPLACE INTO demand_forecast
                        (forecast_date, station_id, hour, predicted_sessions,
                         predicted_energy, predicted_queue_length, 
                         confidence_level, model_version)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        forecast.get('forecast_date'),
                        forecast.get('station_id'),
                        forecast.get('hour'),
                        forecast.get('predicted_sessions', 0),
                        forecast.get('predicted_energy', 0),
                        forecast.get('predicted_queue_length', 0),
                        forecast.get('confidence_level', 0.8),
                        forecast.get('model_version', 'v1.0')
                    ))
                
                conn.commit()
                
        except Exception as e:
            logger.error(f"保存需求预测失败: {e}")
    
    def get_demand_forecast(self, station_id: str, days: int = 7) -> pd.DataFrame:
        """获取需求预测"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                query = """
                    SELECT * FROM demand_forecast
                    WHERE station_id = ?
                    AND forecast_date BETWEEN date('now') AND date('now', ? || ' days')
                    ORDER BY forecast_date, hour
                """
                
                return pd.read_sql_query(query, conn, params=[station_id, f'+{days}'])
                
        except Exception as e:
            logger.error(f"获取需求预测失败: {e}")
            return pd.DataFrame()
    
    # === 分析方法 ===
    
    def analyze_station_performance(self, station_id: str, days: int = 30) -> Dict:
        """分析站点性能"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                # 获取基础统计
                stats_query = """
                    SELECT 
                        COUNT(DISTINCT DATE(start_time)) as operating_days,
                        COUNT(*) as total_sessions,
                        SUM(energy_kwh) as total_energy,
                        SUM(revenue) as total_revenue,
                        AVG(duration_minutes) as avg_session_duration,
                        AVG(energy_kwh) as avg_energy_per_session,
                        AVG(price_per_kwh) as avg_price
                    FROM charging_sessions
                    WHERE station_id = ?
                    AND start_time >= date('now', ? || ' days')
                """
                
                stats_df = pd.read_sql_query(stats_query, conn, 
                                            params=[station_id, f'-{days}'])
                
                # 获取时段分布
                hourly_query = """
                    SELECT 
                        strftime('%H', start_time) as hour,
                        COUNT(*) as sessions,
                        SUM(energy_kwh) as energy
                    FROM charging_sessions
                    WHERE station_id = ?
                    AND start_time >= date('now', ? || ' days')
                    GROUP BY hour
                """
                
                hourly_df = pd.read_sql_query(hourly_query, conn,
                                             params=[station_id, f'-{days}'])
                
                # 获取故障统计
                failure_query = """
                    SELECT 
                        COUNT(*) as failure_count,
                        AVG(julianday(completed_at) - julianday(created_at)) * 24 as avg_repair_hours
                    FROM maintenance_orders
                    WHERE station_id = ?
                    AND created_at >= date('now', ? || ' days')
                """
                
                failure_df = pd.read_sql_query(failure_query, conn,
                                             params=[station_id, f'-{days}'])
                
                return {
                    'basic_stats': stats_df.to_dict('records')[0] if not stats_df.empty else {},
                    'hourly_distribution': hourly_df.to_dict('records'),
                    'failure_stats': failure_df.to_dict('records')[0] if not failure_df.empty else {}
                }
                
        except Exception as e:
            logger.error(f"分析站点性能失败: {e}")
            return {}
    
    def get_expansion_recommendations(self) -> List[Dict]:
        """获取扩容建议"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                # 分析高负载站点
                query = """
                    SELECT 
                        s.station_id,
                        s.name,
                        AVG(r.utilization_rate) as avg_utilization,
                        AVG(r.queue_length) as avg_queue,
                        COUNT(DISTINCT r.charger_id) as charger_count,
                        SUM(CASE WHEN r.status = 'failure' THEN 1 ELSE 0 END) / 
                            COUNT(*) * 100 as failure_rate
                    FROM station_config s
                    LEFT JOIN (
                        SELECT * FROM realtime_data 
                        WHERE timestamp >= datetime('now', '-7 days')
                    ) r ON s.station_id = r.station_id
                    GROUP BY s.station_id, s.name
                    HAVING avg_utilization > 0.7 OR avg_queue > 3
                """
                
                high_load_df = pd.read_sql_query(query, conn)
                
                recommendations = []
                for _, station in high_load_df.iterrows():
                    if station['avg_utilization'] > 0.8:
                        rec_type = 'urgent_expansion'
                        additional_chargers = max(2, int(station['charger_count'] * 0.5))
                    elif station['avg_utilization'] > 0.7:
                        rec_type = 'expansion'
                        additional_chargers = max(1, int(station['charger_count'] * 0.3))
                    else:
                        rec_type = 'optimization'
                        additional_chargers = 0
                    
                    recommendations.append({
                        'station_id': station['station_id'],
                        'station_name': station['name'],
                        'recommendation_type': rec_type,
                        'current_utilization': station['avg_utilization'],
                        'avg_queue_length': station['avg_queue'],
                        'suggested_additional_chargers': additional_chargers,
                        'priority': 'high' if rec_type == 'urgent_expansion' else 'medium'
                    })
                
                return recommendations
                
        except Exception as e:
            logger.error(f"获取扩容建议失败: {e}")
            return []

# 全局数据存储实例
operator_storage = OperatorDataStorage()