#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
用户面板组件
为电动汽车车主设计的核心交互界面
"""

import sys
import json
import random
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, 
    QPushButton, QGroupBox, QScrollArea, QFrame, QListWidget,
    QListWidgetItem, QComboBox, QSpinBox, QDoubleSpinBox,
    QTextEdit, QProgressBar, QTabWidget, QTableWidget,
    QTableWidgetItem, QHeaderView, QSlider, QCheckBox,
    QSplitter, QDialog, QDialogButtonBox, QFormLayout,
    QMessageBox, QLineEdit
)

# 导入预约系统组件
from reservation_system import (
    ReservationDialog, ReservationListWidget, ReservationManager,
    reservation_manager, ReservationStatus
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread, QSize, QRect
from PyQt6.QtGui import (
    QFont, QPainter, QPen, QBrush, QColor, QPixmap, QIcon,
    QLinearGradient, QPalette, QPolygonF
)
from PyQt6.QtCore import QPointF
import math

logger = logging.getLogger(__name__)

@dataclass
class ChargingStation:
    """充电站数据类"""
    station_id: str
    name: str
    address: str
    lat: float
    lng: float
    distance: float
    eta_minutes: int
    available_chargers: int
    total_chargers: int
    queue_length: int
    wait_time_minutes: int
    max_power: float
    current_price: float
    rating: float
    tags: List[str]
    estimated_cost: float


class UserProfileWidget(QWidget):
    """用户画像可视化组件"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.user_data = {}
        self.profile_scores = {
            '时间敏感度': 0.5,
            '价格敏感度': 0.5,
            '续航焦虑': 0.3,
            '充电频率': 0.4,
            '快充偏好': 0.6
        }
        self.setMinimumSize(300, 250)
        
    def updateProfile(self, user_data, charging_history=None):
        """更新用户画像数据"""
        self.user_data = user_data
        
        # 根据用户类型和画像计算特征分数
        user_profile = user_data.get('user_profile', 'flexible')
        user_type = user_data.get('user_type', 'private')
        
        # 基于用户画像设置基础分数
        if user_profile == 'urgent':
            self.profile_scores = {
                '时间敏感度': 0.9,
                '价格敏感度': 0.2,
                '续航焦虑': 0.4,
                '充电频率': 0.7,
                '快充偏好': 0.9
            }
        elif user_profile == 'economic':
            self.profile_scores = {
                '时间敏感度': 0.3,
                '价格敏感度': 0.9,
                '续航焦虑': 0.3,
                '充电频率': 0.4,
                '快充偏好': 0.2
            }
        elif user_profile == 'anxious':
            self.profile_scores = {
                '时间敏感度': 0.6,
                '价格敏感度': 0.4,
                '续航焦虑': 0.9,
                '充电频率': 0.8,
                '快充偏好': 0.7
            }
        else:  # flexible
            self.profile_scores = {
                '时间敏感度': 0.5,
                '价格敏感度': 0.5,
                '续航焦虑': 0.4,
                '充电频率': 0.5,
                '快充偏好': 0.5
            }
        
        # 根据用户类型调整
        if user_type == 'taxi':
            self.profile_scores['时间敏感度'] = min(1.0, self.profile_scores['时间敏感度'] + 0.2)
            self.profile_scores['充电频率'] = min(1.0, self.profile_scores['充电频率'] + 0.3)
        elif user_type == 'logistics':
            self.profile_scores['价格敏感度'] = min(1.0, self.profile_scores['价格敏感度'] + 0.2)
            self.profile_scores['续航焦虑'] = min(1.0, self.profile_scores['续航焦虑'] + 0.1)
        
        # 根据充电历史调整（如果有的话）
        if charging_history and len(charging_history) > 0:
            self._adjustScoresFromHistory(charging_history)
        
        self.update()  # 触发重绘
    
    def _adjustScoresFromHistory(self, charging_history):
        """根据充电历史调整画像分数"""
        if len(charging_history) < 3:
            return
        
        recent_sessions = charging_history[-10:]  # 最近10次充电
        
        # 分析快充使用频率
        fast_charge_count = sum(1 for session in recent_sessions 
                               if session.get('power_kw', 0) > 50)
        fast_charge_ratio = fast_charge_count / len(recent_sessions)
        self.profile_scores['快充偏好'] = fast_charge_ratio
        
        # 分析充电频率
        if len(charging_history) > 1:
            # 计算平均充电间隔
            intervals = []
            for i in range(1, len(recent_sessions)):
                prev_time = datetime.fromisoformat(recent_sessions[i-1].get('start_time', '2024-01-01T00:00:00'))
                curr_time = datetime.fromisoformat(recent_sessions[i].get('start_time', '2024-01-01T00:00:00'))
                interval_hours = (curr_time - prev_time).total_seconds() / 3600
                intervals.append(interval_hours)
            
            if intervals:
                avg_interval = sum(intervals) / len(intervals)
                # 间隔越短，充电频率越高
                frequency_score = max(0, min(1, 1 - (avg_interval - 12) / 48))  # 12-60小时映射到1-0
                self.profile_scores['充电频率'] = frequency_score
        
        # 分析SOC偏好（续航焦虑）
        final_socs = [session.get('final_soc', 80) for session in recent_sessions]
        avg_final_soc = sum(final_socs) / len(final_socs)
        # 充电到越高SOC，续航焦虑越高
        anxiety_score = max(0, min(1, (avg_final_soc - 60) / 40))  # 60-100%映射到0-1
        self.profile_scores['续航焦虑'] = anxiety_score
    
    def paintEvent(self, event):
        """绘制用户画像雷达图"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # 获取绘制区域
        rect = self.rect()
        center_x = rect.width() // 2
        center_y = rect.height() // 2
        radius = min(center_x, center_y) - 40
        
        # 绘制背景网格
        self._drawGrid(painter, center_x, center_y, radius)
        
        # 绘制雷达图
        self._drawRadarChart(painter, center_x, center_y, radius)
        
        # 绘制标签
        self._drawLabels(painter, center_x, center_y, radius)
        
        # 绘制用户画像标签
        self._drawProfileInfo(painter, rect)
    
    def _drawGrid(self, painter, center_x, center_y, radius):
        """绘制网格背景"""
        painter.setPen(QPen(QColor(200, 200, 200), 1))
        
        # 绘制同心圆
        for i in range(1, 6):
            r = radius * i / 5
            painter.drawEllipse(int(center_x - r), int(center_y - r), int(2 * r), int(2 * r))
        
        # 绘制射线
        angles = [i * 2 * math.pi / 5 for i in range(5)]
        for angle in angles:
            x = center_x + radius * math.cos(angle - math.pi/2)
            y = center_y + radius * math.sin(angle - math.pi/2)
            painter.drawLine(int(center_x), int(center_y), int(x), int(y))
    
    def _drawRadarChart(self, painter, center_x, center_y, radius):
        """绘制雷达图数据"""
        # 计算各个点的坐标
        points = []
        angles = [i * 2 * math.pi / 5 for i in range(5)]
        scores = list(self.profile_scores.values())
        
        for i, (angle, score) in enumerate(zip(angles, scores)):
            r = radius * score
            x = center_x + r * math.cos(angle - math.pi/2)
            y = center_y + r * math.sin(angle - math.pi/2)
            points.append(QPointF(x, y))
        
        # 绘制填充区域
        polygon = QPolygonF(points)
        
        # 设置填充颜色（半透明蓝色）
        painter.setBrush(QBrush(QColor(0, 123, 255, 100)))
        painter.setPen(QPen(QColor(0, 123, 255), 2))
        painter.drawPolygon(polygon)
        
        # 绘制数据点
        painter.setBrush(QBrush(QColor(0, 123, 255)))
        for point in points:
            painter.drawEllipse(int(point.x() - 4), int(point.y() - 4), 8, 8)
    
    def _drawLabels(self, painter, center_x, center_y, radius):
        """绘制标签"""
        painter.setPen(QPen(QColor(50, 50, 50)))
        painter.setFont(QFont("Arial", 9))
        
        labels = list(self.profile_scores.keys())
        angles = [i * 2 * math.pi / 5 for i in range(5)]
        
        for i, (angle, label) in enumerate(zip(angles, labels)):
            # 标签位置稍微外移
            label_radius = radius + 25
            x = center_x + label_radius * math.cos(angle - math.pi/2)
            y = center_y + label_radius * math.sin(angle - math.pi/2)
            
            # 调整文本位置以居中
            metrics = painter.fontMetrics()
            text_width = metrics.horizontalAdvance(label)
            text_height = metrics.height()
            
            painter.drawText(int(x - text_width//2), int(y + text_height//4), label)
            
            # 显示数值
            score = list(self.profile_scores.values())[i]
            score_text = f"{score:.1f}"
            score_width = metrics.horizontalAdvance(score_text)
            painter.drawText(int(x - score_width//2), int(y + text_height//4 + 15), score_text)
    
    def _drawProfileInfo(self, painter, rect):
        """绘制用户画像信息"""
        painter.setPen(QPen(QColor(50, 50, 50)))
        painter.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        
        # 获取用户画像类型
        user_profile = self.user_data.get('user_profile', 'flexible')
        profile_names = {
            'urgent': '快充优先型',
            'economic': '价格敏感型', 
            'anxious': '续航焦虑型',
            'flexible': '均衡偏好型'
        }
        
        profile_name = profile_names.get(user_profile, '未知类型')
        
        # 在顶部绘制画像类型
        painter.drawText(10, 20, f"用户画像: {profile_name}")
        
        # 绘制特征标签
        painter.setFont(QFont("Arial", 8))
        y_offset = 40
        
        # 根据分数生成特征标签
        tags = self._generateProfileTags()
        for i, tag in enumerate(tags[:3]):  # 最多显示3个标签
            painter.setPen(QPen(QColor(255, 255, 255)))
            painter.setBrush(QBrush(QColor(0, 123, 255)))
            
            # 绘制标签背景
            tag_rect = QRect(10, y_offset + i * 20, 80, 16)
            painter.drawRoundedRect(tag_rect, 8, 8)
            
            # 绘制标签文字
            painter.drawText(tag_rect, Qt.AlignmentFlag.AlignCenter, tag)
    
    def _generateProfileTags(self):
        """根据画像分数生成特征标签"""
        tags = []
        
        if self.profile_scores['时间敏感度'] > 0.7:
            tags.append('时间优先')
        if self.profile_scores['价格敏感度'] > 0.7:
            tags.append('价格敏感')
        if self.profile_scores['续航焦虑'] > 0.7:
            tags.append('续航焦虑')
        if self.profile_scores['充电频率'] > 0.7:
            tags.append('频繁充电')
        if self.profile_scores['快充偏好'] > 0.7:
            tags.append('快充偏好')
        
        # 如果没有突出特征，添加均衡标签
        if not tags:
            tags.append('均衡用户')
        
        return tags


class UserInfoPanel(QGroupBox):
    """用户信息管理面板"""
    
    def __init__(self, parent=None):
        super().__init__("用户信息", parent)
        self.user_data = {}
        self.setupUI()
    
    def setupUI(self):
        layout = QVBoxLayout(self)
        
        # 创建水平布局，左侧基本信息，右侧用户画像
        main_layout = QHBoxLayout()
        
        # 左侧：基本信息
        info_widget = QWidget()
        info_layout = QVBoxLayout(info_widget)
        
        # 静态信息
        static_group = QGroupBox("基本信息")
        static_layout = QGridLayout(static_group)
        
        self.user_id_label = QLabel("--")
        self.user_type_label = QLabel("--")
        self.vehicle_model_label = QLabel("--")
        self.charging_preference_label = QLabel("--")
        
        static_layout.addWidget(QLabel("用户ID:"), 0, 0)
        static_layout.addWidget(self.user_id_label, 0, 1)
        static_layout.addWidget(QLabel("用户类型:"), 1, 0)
        static_layout.addWidget(self.user_type_label, 1, 1)
        static_layout.addWidget(QLabel("车辆型号:"), 2, 0)
        static_layout.addWidget(self.vehicle_model_label, 2, 1)
        static_layout.addWidget(QLabel("充电偏好:"), 3, 0)
        static_layout.addWidget(self.charging_preference_label, 3, 1)
        
        info_layout.addWidget(static_group)
        
        # 动态信息
        dynamic_group = QGroupBox("实时状态")
        dynamic_layout = QGridLayout(dynamic_group)
        
        self.status_label = QLabel("--")
        self.location_label = QLabel("--")
        self.soc_progress = QProgressBar()
        self.soc_progress.setRange(0, 100)
        self.target_soc_spin = QSpinBox()
        self.target_soc_spin.setRange(20, 100)
        self.target_soc_spin.setValue(80)
        self.target_soc_spin.setSuffix("%")
        
        dynamic_layout.addWidget(QLabel("当前状态:"), 0, 0)
        dynamic_layout.addWidget(self.status_label, 0, 1)
        dynamic_layout.addWidget(QLabel("当前位置:"), 1, 0)
        dynamic_layout.addWidget(self.location_label, 1, 1)
        dynamic_layout.addWidget(QLabel("当前电量:"), 2, 0)
        dynamic_layout.addWidget(self.soc_progress, 2, 1)
        dynamic_layout.addWidget(QLabel("目标电量:"), 3, 0)
        dynamic_layout.addWidget(self.target_soc_spin, 3, 1)
        
        info_layout.addWidget(dynamic_group)
        
        # 右侧：用户画像可视化
        self.profile_widget = UserProfileWidget()
        
        # 添加到主布局
        main_layout.addWidget(info_widget, 1)  # 基本信息占1份
        main_layout.addWidget(self.profile_widget, 1)  # 用户画像占1份
        
        layout.addLayout(main_layout)
    
    def updateUserInfo(self, user_data, charging_history=None):
        """更新用户信息"""
        self.user_data = user_data
        
        # 更新静态信息
        self.user_id_label.setText(user_data.get('user_id', '--'))
        self.user_type_label.setText(self._translateUserType(user_data.get('user_type', 'private')))
        self.vehicle_model_label.setText(user_data.get('vehicle_type', 'sedan'))
        self.charging_preference_label.setText(self._translateProfile(user_data.get('user_profile', 'flexible')))
        
        # 更新动态信息
        status = user_data.get('status', 'idle')
        self.status_label.setText(self._translateStatus(status))
        self.status_label.setStyleSheet(f"color: {self._getStatusColor(status)};")
        
        position = user_data.get('current_position', {})
        self.location_label.setText(f"({position.get('lat', 0):.3f}, {position.get('lng', 0):.3f})")
        
        soc = user_data.get('soc', 0)
        self.soc_progress.setValue(int(soc))
        self.soc_progress.setFormat(f"{soc:.1f}%")
        
        # 设置进度条颜色
        if soc < 20:
            color = "red"
        elif soc < 50:
            color = "orange"
        else:
            color = "green"
        
        self.soc_progress.setStyleSheet(f"""
            QProgressBar::chunk {{
                background-color: {color};
            }}
        """)
        
        # 更新用户画像
        self.profile_widget.updateProfile(user_data, charging_history)
    
    def _translateUserType(self, user_type):
        """翻译用户类型"""
        type_map = {
            'private': '个人用户',
            'taxi': '出租车',
            'ride_hailing': '网约车',
            'logistics': '物流车队'
        }
        return type_map.get(user_type, user_type)
    
    def _translateProfile(self, profile):
        """翻译用户偏好"""
        profile_map = {
            'urgent': '快充优先',
            'economic': '价格优先',
            'flexible': '均衡偏好',
            'anxious': '续航焦虑'
        }
        return profile_map.get(profile, profile)
    
    def _translateStatus(self, status):
        """翻译状态"""
        status_map = {
            'idle': '空闲',
            'traveling': '行驶中',
            'waiting': '等待充电',
            'charging': '充电中',
            'post_charge': '充电完成'
        }
        return status_map.get(status, status)
    
    def _getStatusColor(self, status):
        """获取状态颜色"""
        color_map = {
            'idle': '#6c757d',
            'traveling': '#007bff',
            'waiting': '#ffc107',
            'charging': '#28a745',
            'post_charge': '#6f42c1'
        }
        return color_map.get(status, '#6c757d')


class ChargingHistoryPanel(QGroupBox):
    """充电历史面板"""
    
    def __init__(self, parent=None):
        super().__init__("充电历史", parent)
        self.setupUI()
    
    def setupUI(self):
        layout = QVBoxLayout(self)
        
        # 统计信息
        stats_group = QGroupBox("本月统计")
        stats_layout = QGridLayout(stats_group)
        
        self.total_sessions_label = QLabel("0")
        self.total_cost_label = QLabel("¥0.00")
        self.avg_soc_label = QLabel("0%")
        self.total_energy_label = QLabel("0 kWh")
        
        stats_layout.addWidget(QLabel("充电次数:"), 0, 0)
        stats_layout.addWidget(self.total_sessions_label, 0, 1)
        stats_layout.addWidget(QLabel("总费用:"), 0, 2)
        stats_layout.addWidget(self.total_cost_label, 0, 3)
        stats_layout.addWidget(QLabel("平均充至:"), 1, 0)
        stats_layout.addWidget(self.avg_soc_label, 1, 1)
        stats_layout.addWidget(QLabel("总充电量:"), 1, 2)
        stats_layout.addWidget(self.total_energy_label, 1, 3)
        
        layout.addWidget(stats_group)
        
        # 历史记录表格
        self.history_table = QTableWidget()
        self.history_table.setColumnCount(5)
        self.history_table.setHorizontalHeaderLabels([
            "充电站", "日期时间", "充电量(kWh)", "费用(元)", "最终SOC"
        ])
        
        # 设置表格属性
        header = self.history_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.history_table.setAlternatingRowColors(True)
        self.history_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        
        layout.addWidget(self.history_table)
    
    def updateHistory(self, charging_history):
        """更新充电历史"""
        if not charging_history:
            return
        
        # 更新统计信息
        total_sessions = len(charging_history)
        total_cost = sum(session.get('cost', 0) for session in charging_history)
        total_energy = sum(session.get('energy_charged_grid', 0) for session in charging_history)
        avg_soc = sum(session.get('final_soc', 0) for session in charging_history) / max(1, total_sessions)
        
        self.total_sessions_label.setText(str(total_sessions))
        self.total_cost_label.setText(f"¥{total_cost:.2f}")
        self.total_energy_label.setText(f"{total_energy:.1f} kWh")
        self.avg_soc_label.setText(f"{avg_soc:.1f}%")
        
        # 更新历史表格 - 只显示最近的记录
        recent_history = charging_history[-20:] if len(charging_history) > 20 else charging_history
        self.history_table.setRowCount(len(recent_history))
        
        for row, session in enumerate(recent_history):
            # 充电站名称
            charger_id = session.get('charger_id', '')
            station_name = f"充电站_{charger_id.split('_')[-1] if '_' in charger_id else charger_id}"
            self.history_table.setItem(row, 0, QTableWidgetItem(station_name))
            
            # 日期时间
            start_time = session.get('start_time', '')
            if start_time:
                try:
                    dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                    time_str = dt.strftime('%m-%d %H:%M')
                except:
                    time_str = start_time[:16]
            else:
                time_str = '--'
            self.history_table.setItem(row, 1, QTableWidgetItem(time_str))
            
            # 充电量
            energy = session.get('energy_charged_grid', 0)
            self.history_table.setItem(row, 2, QTableWidgetItem(f"{energy:.1f}"))
            
            # 费用
            cost = session.get('cost', 0)
            self.history_table.setItem(row, 3, QTableWidgetItem(f"{cost:.2f}"))
            
            # 最终SOC
            final_soc = session.get('final_soc', 0)
            self.history_table.setItem(row, 4, QTableWidgetItem(f"{final_soc:.1f}%"))


class StationRecommendationPanel(QGroupBox):
    """充电站推荐面板"""
    
    stationSelected = pyqtSignal(str)  # 充电站选择信号
    
    def __init__(self, parent=None):
        super().__init__("充电站推荐", parent)
        self.stations_data = []
        self.user_position = {}
        self.setupUI()
    
    def setupUI(self):
        layout = QVBoxLayout(self)
        
        # 控制面板
        control_panel = QHBoxLayout()
        
        # 排序选择
        control_panel.addWidget(QLabel("排序:"))
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["综合评分", "距离最近", "价格最低", "等待最短"])
        self.sort_combo.currentTextChanged.connect(self.updateRecommendations)
        control_panel.addWidget(self.sort_combo)
        
        # 筛选选择
        control_panel.addWidget(QLabel("筛选:"))
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["全部", "快充", "慢充", "有车位", "低价格"])
        self.filter_combo.currentTextChanged.connect(self.updateRecommendations)
        control_panel.addWidget(self.filter_combo)
        
        control_panel.addStretch()
        
        # 刷新按钮
        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self.refreshRecommendations)
        control_panel.addWidget(refresh_btn)
        
        layout.addLayout(control_panel)
        
        # 推荐列表
        self.station_list = QListWidget()
        self.station_list.itemClicked.connect(self.onStationClicked)
        layout.addWidget(self.station_list)
    
    def updateRecommendations(self):
        """更新推荐列表"""
        # 应用排序和筛选
        filtered_stations = self._applyFilters(self.stations_data)
        sorted_stations = self._applySorting(filtered_stations)
        
        # 更新UI
        self.station_list.clear()
        
        for station in sorted_stations[:10]:  # 只显示前10个推荐
            item_widget = self._createStationItem(station)
            list_item = QListWidgetItem()
            list_item.setSizeHint(item_widget.sizeHint())
            list_item.setData(Qt.ItemDataRole.UserRole, station.station_id)
            
            self.station_list.addItem(list_item)
            self.station_list.setItemWidget(list_item, item_widget)
    
    def _createStationItem(self, station: ChargingStation):
        """创建充电站项目widget"""
        widget = QFrame()
        widget.setFrameStyle(QFrame.Shape.Box)
        widget.setStyleSheet("""
            QFrame {
                border: 1px solid #ddd;
                border-radius: 8px;
                padding: 10px;
                margin: 2px;
                background: white;
            }
            QFrame:hover {
                border: 2px solid #007bff;
                background: #f8f9fa;
            }
        """)
        
        layout = QVBoxLayout(widget)
        
        # 第一行：评分和名称
        header_layout = QHBoxLayout()
        
        # 评分
        rating_label = QLabel(f"★ {station.rating:.1f}")
        rating_label.setStyleSheet("color: #ffc107; font-weight: bold;")
        header_layout.addWidget(rating_label)
        
        # 名称
        name_label = QLabel(station.name)
        name_label.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        header_layout.addWidget(name_label)
        
        header_layout.addStretch()
        
        # 特色标签
        for tag in station.tags:
            tag_label = QLabel(tag)
            tag_label.setStyleSheet("""
                background: #007bff;
                color: white;
                padding: 2px 6px;
                border-radius: 10px;
                font-size: 10px;
            """)
            header_layout.addWidget(tag_label)
        
        layout.addLayout(header_layout)
        
        # 第二行：位置和距离
        location_layout = QHBoxLayout()
        location_label = QLabel(station.address)
        location_label.setStyleSheet("color: #6c757d;")
        location_layout.addWidget(location_label)
        
        location_layout.addStretch()
        
        distance_label = QLabel(f"{station.distance:.1f}km · {station.eta_minutes}分钟")
        distance_label.setStyleSheet("color: #007bff; font-weight: bold;")
        location_layout.addWidget(distance_label)
        
        layout.addLayout(location_layout)
        
        # 第三行：充电信息
        charging_layout = QHBoxLayout()
        
        # 可用性
        if station.available_chargers > 0:
            availability_text = f"可用 {station.available_chargers}/{station.total_chargers}"
            availability_color = "#28a745"
        else:
            availability_text = f"排队 {station.queue_length}人"
            availability_color = "#ffc107"
        
        availability_label = QLabel(availability_text)
        availability_label.setStyleSheet(f"color: {availability_color}; font-weight: bold;")
        charging_layout.addWidget(availability_label)
        
        charging_layout.addStretch()
        
        # 功率和价格
        power_price_label = QLabel(f"{station.max_power:.0f}kW · ¥{station.current_price:.2f}/度")
        charging_layout.addWidget(power_price_label)
        
        layout.addLayout(charging_layout)
        
        # 第四行：等待时间和预估费用
        bottom_layout = QHBoxLayout()
        
        wait_label = QLabel(f"预计等待: {station.wait_time_minutes}分钟")
        wait_label.setStyleSheet("color: #6c757d;")
        bottom_layout.addWidget(wait_label)
        
        bottom_layout.addStretch()
        
        cost_label = QLabel(f"预估费用: ¥{station.estimated_cost:.1f}")
        cost_label.setStyleSheet("color: #dc3545; font-weight: bold;")
        bottom_layout.addWidget(cost_label)
        
        layout.addLayout(bottom_layout)
        
        # 按钮行 
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        nav_btn = QPushButton("导航")
        nav_btn.setStyleSheet("""
            QPushButton {
                background: #6c757d;
                color: white;
                border: none;
                padding: 5px 15px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background: #5a6268;
            }
        """)
        button_layout.addWidget(nav_btn)
        
        select_btn = QPushButton("选择此站")
        select_btn.setStyleSheet("""
            QPushButton {
                background: #007bff;
                color: white;
                border: none;
                padding: 5px 15px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background: #0056b3;
            }
        """)
        select_btn.clicked.connect(lambda: self.stationSelected.emit(station.station_id))
        button_layout.addWidget(select_btn)
        
        layout.addLayout(button_layout)
        
        return widget
    
    def _applyFilters(self, stations):
        """应用筛选条件"""
        filter_type = self.filter_combo.currentText()
        
        if filter_type == "全部":
            return stations
        elif filter_type == "快充":
            return [s for s in stations if "快充" in s.tags]
        elif filter_type == "慢充":
            return [s for s in stations if "慢充" in s.tags]
        elif filter_type == "有车位":
            return [s for s in stations if s.available_chargers > 0]
        elif filter_type == "低价格":
            return [s for s in stations if s.current_price < 1.0]
        
        return stations
    
    def _applySorting(self, stations):
        """应用排序条件"""
        sort_type = self.sort_combo.currentText()
        
        if sort_type == "综合评分":
            return sorted(stations, key=lambda s: s.rating, reverse=True)
        elif sort_type == "距离最近":
            return sorted(stations, key=lambda s: s.distance)
        elif sort_type == "价格最低":
            return sorted(stations, key=lambda s: s.current_price)
        elif sort_type == "等待最短":
            return sorted(stations, key=lambda s: s.wait_time_minutes)
        
        return stations
    
    def onStationClicked(self, item):
        """处理充电站点击"""
        station_id = item.data(Qt.ItemDataRole.UserRole)
        if station_id:
            self.stationSelected.emit(station_id)
    
    def refreshRecommendations(self):
        """刷新推荐"""
        # 这里会触发后端重新计算推荐
        pass
    
    def updateStations(self, stations_data, user_position):
        """更新充电站数据"""
        self.stations_data = stations_data
        self.user_position = user_position
        self.updateRecommendations()


class StationDetailsPanel(QGroupBox):
    """充电站详情面板"""
    
    chargingRequested = pyqtSignal(str, dict)  # 充电请求信号
    
    def __init__(self, parent=None):
        super().__init__("充电站详情", parent)
        self.current_station = None
        self.setupUI()
    
    def setupUI(self):
        layout = QVBoxLayout(self)
        
        # 默认提示
        self.no_selection_label = QLabel("请从推荐列表中选择一个充电站")
        self.no_selection_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.no_selection_label.setStyleSheet("color: #6c757d; font-size: 14px;")
        layout.addWidget(self.no_selection_label)
        
        # 详情内容（初始隐藏）
        self.details_widget = QWidget()
        self.details_widget.setVisible(False)
        self.setupDetailsWidget()
        layout.addWidget(self.details_widget)
    
    def setupDetailsWidget(self):
        """设置详情widget"""
        layout = QVBoxLayout(self.details_widget)
        
        # 基本信息
        basic_group = QGroupBox("基本信息")
        basic_layout = QGridLayout(basic_group)
        
        self.station_name_label = QLabel("--")
        self.station_address_label = QLabel("--")
        self.operator_label = QLabel("--")
        self.open_hours_label = QLabel("--")
        
        basic_layout.addWidget(QLabel("站点名称:"), 0, 0)
        basic_layout.addWidget(self.station_name_label, 0, 1)
        basic_layout.addWidget(QLabel("详细地址:"), 1, 0)
        basic_layout.addWidget(self.station_address_label, 1, 1)
        basic_layout.addWidget(QLabel("运营商:"), 2, 0)
        basic_layout.addWidget(self.operator_label, 2, 1)
        basic_layout.addWidget(QLabel("营业时间:"), 3, 0)
        basic_layout.addWidget(self.open_hours_label, 3, 1)
        
        layout.addWidget(basic_group)
        
        # 实时状态
        status_group = QGroupBox("实时状态")
        status_layout = QGridLayout(status_group)
        
        self.available_label = QLabel("--")
        self.queue_label = QLabel("--")
        self.wait_time_label = QLabel("--")
        self.current_price_label = QLabel("--")
        
        status_layout.addWidget(QLabel("可用充电枪:"), 0, 0)
        status_layout.addWidget(self.available_label, 0, 1)
        status_layout.addWidget(QLabel("排队人数:"), 1, 0)
        status_layout.addWidget(self.queue_label, 1, 1)
        status_layout.addWidget(QLabel("预计等待:"), 2, 0)
        status_layout.addWidget(self.wait_time_label, 2, 1)
        status_layout.addWidget(QLabel("当前电价:"), 3, 0)
        status_layout.addWidget(self.current_price_label, 3, 1)
        
        layout.addWidget(status_group)
        
        # 设备信息
        equipment_group = QGroupBox("设备信息")
        equipment_layout = QGridLayout(equipment_group)
        
        self.charger_types_label = QLabel("--")
        self.interfaces_label = QLabel("--")
        self.max_power_label = QLabel("--")
        
        equipment_layout.addWidget(QLabel("充电类型:"), 0, 0)
        equipment_layout.addWidget(self.charger_types_label, 0, 1)
        equipment_layout.addWidget(QLabel("接口标准:"), 1, 0)
        equipment_layout.addWidget(self.interfaces_label, 1, 1)
        equipment_layout.addWidget(QLabel("最大功率:"), 2, 0)
        equipment_layout.addWidget(self.max_power_label, 2, 1)
        
        layout.addWidget(equipment_group)
        
        # 价格详情
        price_group = QGroupBox("价格详情")
        price_layout = QVBoxLayout(price_group)
        
        self.price_table = QTableWidget()
        self.price_table.setColumnCount(3)
        self.price_table.setHorizontalHeaderLabels(["时段", "电费(元/度)", "服务费(元/度)"])
        self.price_table.setRowCount(3)
        
        # 设置价格表格
        periods = ["峰时(7-10,18-21)", "平时(10-18)", "谷时(21-7)"]
        for i, period in enumerate(periods):
            self.price_table.setItem(i, 0, QTableWidgetItem(period))
        
        header = self.price_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.price_table.setMaximumHeight(150)
        
        price_layout.addWidget(self.price_table)
        layout.addWidget(price_group)
        
        # 用户评价
        rating_group = QGroupBox("用户评价")
        rating_layout = QVBoxLayout(rating_group)
        
        rating_header = QHBoxLayout()
        self.overall_rating_label = QLabel("★★★★☆ 4.2")
        self.overall_rating_label.setStyleSheet("color: #ffc107; font-size: 16px; font-weight: bold;")
        rating_header.addWidget(self.overall_rating_label)
        rating_header.addStretch()
        self.rating_count_label = QLabel("(128条评价)")
        self.rating_count_label.setStyleSheet("color: #6c757d;")
        rating_header.addWidget(self.rating_count_label)
        
        rating_layout.addLayout(rating_header)
        
        # 评价详情
        self.rating_details = QLabel("设备可用性: ★★★★☆\n位置便利性: ★★★★★\n充电速度: ★★★☆☆")
        rating_layout.addWidget(self.rating_details)
        
        layout.addWidget(rating_group)
        
        # 操作按钮
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        # 立即充电按钮
        self.charge_now_btn = QPushButton("立即充电")
        self.charge_now_btn.setStyleSheet("""
            QPushButton {
                background: #28a745;
                color: white;
                border: none;
                padding: 12px 24px;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #218838;
            }
        """)
        self.charge_now_btn.clicked.connect(self.onChargingRequested)
        button_layout.addWidget(self.charge_now_btn)
        
        # 预约充电按钮
        self.reserve_btn = QPushButton("预约充电")
        self.reserve_btn.setStyleSheet("""
            QPushButton {
                background: #007bff;
                color: white;
                border: none;
                padding: 12px 24px;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #0056b3;
            }
        """)
        self.reserve_btn.clicked.connect(self.onReservationRequested)
        button_layout.addWidget(self.reserve_btn)
        
        layout.addLayout(button_layout)
    
    def showStationDetails(self, station_data):
        """显示充电站详情"""
        self.current_station = station_data
        
        if not station_data:
            self.no_selection_label.setVisible(True)
            self.details_widget.setVisible(False)
            return
        
        # 隐藏提示，显示详情
        self.no_selection_label.setVisible(False)
        self.details_widget.setVisible(True)
        
        # 更新基本信息
        self.station_name_label.setText(station_data.get('name', '--'))
        self.station_address_label.setText(station_data.get('address', '--'))
        self.operator_label.setText(station_data.get('operator', '默认运营商'))
        self.open_hours_label.setText(station_data.get('open_hours', '24小时'))
        
        # 更新实时状态
        available = station_data.get('available_chargers', 0)
        total = station_data.get('total_chargers', 0)
        self.available_label.setText(f"{available}/{total}")
        self.available_label.setStyleSheet(f"color: {'#28a745' if available > 0 else '#dc3545'}; font-weight: bold;")
        
        queue_length = station_data.get('queue_length', 0)
        self.queue_label.setText(str(queue_length))
        self.queue_label.setStyleSheet(f"color: {'#28a745' if queue_length == 0 else '#ffc107'};")
        
        wait_time = station_data.get('wait_time_minutes', 0)
        self.wait_time_label.setText(f"{wait_time}分钟")
        
        current_price = station_data.get('current_price', 0)
        self.current_price_label.setText(f"¥{current_price:.2f}/度")
        
        # 更新设备信息
        charger_types = station_data.get('charger_types', ['快充', '慢充'])
        self.charger_types_label.setText(', '.join(charger_types))
        
        interfaces = station_data.get('interfaces', ['国标'])
        self.interfaces_label.setText(', '.join(interfaces))
        
        max_power = station_data.get('max_power', 60)
        self.max_power_label.setText(f"{max_power:.0f}kW")
        
        # 更新价格表格
        price_data = station_data.get('price_details', {
            'peak': {'electricity': 1.2, 'service': 0.5},
            'normal': {'electricity': 0.85, 'service': 0.4},
            'valley': {'electricity': 0.4, 'service': 0.3}
        })
        
        price_items = [
            ('peak', 0), ('normal', 1), ('valley', 2)
        ]
        
        for period, row in price_items:
            period_data = price_data.get(period, {'electricity': 0, 'service': 0})
            self.price_table.setItem(row, 1, QTableWidgetItem(f"{period_data['electricity']:.2f}"))
            self.price_table.setItem(row, 2, QTableWidgetItem(f"{period_data['service']:.2f}"))
        
        # 更新评价信息
        rating = station_data.get('rating', 4.2)
        rating_stars = '★' * int(rating) + '☆' * (5 - int(rating))
        self.overall_rating_label.setText(f"{rating_stars} {rating:.1f}")
        
        review_count = station_data.get('review_count', random.randint(50, 200))
        self.rating_count_label.setText(f"({review_count}条评价)")
    
    def onChargingRequested(self):
        """处理立即充电请求"""
        if not self.current_station:
            return
        
        # 弹出确认对话框
        dialog = ChargingConfirmDialog(self.current_station, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            charging_params = dialog.getChargingParams()
            station_id = self.current_station.get('station_id')
            self.chargingRequested.emit(station_id, charging_params)
            
    def onReservationRequested(self):
        """处理预约充电请求"""
        if not self.current_station:
            return
            
        # 获取当前用户数据（需要从父组件传递）
        user_data = getattr(self, 'current_user_data', {})
        
        # 弹出预约对话框，传递仿真时间
        simulation_time = getattr(self.parent(), 'current_simulation_time', None)
        dialog = ReservationDialog(self.current_station, user_data, self, simulation_time=simulation_time)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            reservation_data = dialog.getReservationData()
            if reservation_data:
                # 创建预约
                user_id = user_data.get('user_id', 'unknown')
                station_id = self.current_station.get('station_id')
                charger_id = station_id  # 直接使用station_id作为charger_id
                
                reservation = reservation_manager.createReservation(
                    user_id, station_id, charger_id, reservation_data
                )
                
                QMessageBox.information(
                    self, "预约成功", 
                    f"预约已创建！\n"
                    f"预约编号: {reservation.reservation_id}\n"
                    f"预约时间: {reservation.start_time.strftime('%m-%d %H:%M')}\n"
                    f"预估费用: ¥{reservation.estimated_cost:.2f}"
                )
                
                # 发送预约信号（如果需要）
                if hasattr(self, 'reservationCreated'):
                    self.reservationCreated.emit(reservation.reservation_id)
    
    def setCurrentUserData(self, user_data):
        """设置当前用户数据"""
        self.current_user_data = user_data


class ChargingConfirmDialog(QDialog):
    """充电确认对话框"""
    
    def __init__(self, station_data, parent=None):
        super().__init__(parent)
        self.station_data = station_data
        self.setWindowTitle("确认充电")
        self.setModal(True)
        self.setupUI()
    
    def setupUI(self):
        layout = QVBoxLayout(self)
        
        # 标题
        title = QLabel("确认充电参数")
        title.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        
        # 充电参数
        params_group = QGroupBox("充电参数")
        params_layout = QFormLayout(params_group)
        
        # 目标SOC
        self.target_soc_spin = QSpinBox()
        self.target_soc_spin.setRange(20, 100)
        self.target_soc_spin.setValue(80)
        self.target_soc_spin.setSuffix("%")
        params_layout.addRow("目标电量:", self.target_soc_spin)
        
        # 充电类型
        self.charging_type_combo = QComboBox()
        self.charging_type_combo.addItems(["快充", "慢充"])
        params_layout.addRow("充电类型:", self.charging_type_combo)
        
        # 支付方式
        self.payment_combo = QComboBox()
        self.payment_combo.addItems(["自动支付", "现金支付", "积分支付"])
        params_layout.addRow("支付方式:", self.payment_combo)
        
        layout.addWidget(params_group)
        
        # 预估信息
        estimate_group = QGroupBox("预估信息")
        estimate_layout = QFormLayout(estimate_group)
        
        self.estimate_time_label = QLabel("45分钟")
        self.estimate_cost_label = QLabel("¥38.50")
        self.estimate_energy_label = QLabel("25.6 kWh")
        
        estimate_layout.addRow("预估时间:", self.estimate_time_label)
        estimate_layout.addRow("预估费用:", self.estimate_cost_label)
        estimate_layout.addRow("预估充电量:", self.estimate_energy_label)
        
        layout.addWidget(estimate_group)
        
        # 按钮
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | 
            QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
        # 更新预估信息
        self.target_soc_spin.valueChanged.connect(self.updateEstimates)
        self.charging_type_combo.currentTextChanged.connect(self.updateEstimates)
        self.updateEstimates()
    
    def updateEstimates(self):
        """更新预估信息"""
        target_soc = self.target_soc_spin.value()
        charging_type = self.charging_type_combo.currentText()
        
        # 简化的预估计算
        current_soc = 30  # 假设当前SOC
        soc_needed = target_soc - current_soc
        battery_capacity = 60  # 假设60kWh电池
        
        energy_needed = (soc_needed / 100) * battery_capacity
        
        if charging_type == "快充":
            power = 60  # 60kW功率
            time_hours = energy_needed / power
            price_per_kwh = 1.5
        else:
            power = 7  # 7kW功率
            time_hours = energy_needed / power
            price_per_kwh = 1.0
        
        time_minutes = int(time_hours * 60)
        cost = energy_needed * price_per_kwh
        
        self.estimate_time_label.setText(f"{time_minutes}分钟")
        self.estimate_cost_label.setText(f"¥{cost:.2f}")
        self.estimate_energy_label.setText(f"{energy_needed:.1f} kWh")
    
    def getChargingParams(self):
        """获取充电参数"""
        return {
            'target_soc': self.target_soc_spin.value(),
            'charging_type': self.charging_type_combo.currentText(),
            'payment_method': self.payment_combo.currentText()
        }


class UserControlPanel(QWidget):
    """用户控制面板 - 主面板"""
    
    # 信号定义
    userSelected = pyqtSignal(str)  # 用户选择信号
    simulationStepChanged = pyqtSignal(int)  # 仿真步骤改变信号
    chargingDecisionMade = pyqtSignal(str, str, dict)  # 充电决策信号 (user_id, station_id, params)
    decisionAppliedAndContinue = pyqtSignal()  # 应用决策并继续仿真信号
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_user_id = None
        self.current_step = 0
        self.max_step = 0
        self.simulation_data = {}
        self.is_paused = False
        # 初始化仿真时间为当日零点
        from datetime import datetime
        self.current_simulation_time = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        self.setupUI()
    
    def setupUI(self):
        layout = QVBoxLayout(self)
        
        # 创建垂直分割器
        vertical_splitter = QSplitter(Qt.Orientation.Vertical)
        
        # 控制头部 - 设置为较小的固定高度
        control_header = self._createControlHeader()
        control_header.setMaximumHeight(120)  # 限制控制头部高度
        vertical_splitter.addWidget(control_header)
        
        # 主要内容区域
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # 左侧用户选择和控制
        left_panel = self._createLeftPanel()
        main_splitter.addWidget(left_panel)
        
        # 右侧用户面板内容
        right_panel = self._createRightPanel()
        main_splitter.addWidget(right_panel)
        
        # 设置水平分割比例 - 调整为更平衡的比例
        main_splitter.setStretchFactor(0, 1)
        main_splitter.setStretchFactor(1, 1)
        
        vertical_splitter.addWidget(main_splitter)
        
        # 设置垂直分割比例 - 控制头部小，主内容区域大
        vertical_splitter.setStretchFactor(0, 0)  # 控制头部不拉伸
        vertical_splitter.setStretchFactor(1, 1)  # 主内容区域可拉伸
        vertical_splitter.setSizes([120, 600])  # 设置初始大小
        
        layout.addWidget(vertical_splitter)
    
    def _createControlHeader(self):
        """创建控制头部"""
        group = QGroupBox("仿真控制")
        layout = QHBoxLayout(group)
        
        # 仿真步骤控制
        layout.addWidget(QLabel("仿真步骤:"))
        
        self.step_slider = QSlider(Qt.Orientation.Horizontal)
        self.step_slider.setMinimum(0)
        self.step_slider.setMaximum(100)
        self.step_slider.valueChanged.connect(self.onStepChanged)
        layout.addWidget(self.step_slider)
        
        self.step_label = QLabel("0/0")
        layout.addWidget(self.step_label)
        
        # 播放控制
        self.pause_btn = QPushButton("⏸️ 暂停")
        self.pause_btn.clicked.connect(self.togglePause)
        layout.addWidget(self.pause_btn)
        
        self.prev_btn = QPushButton("⏮️ 上一步")
        self.prev_btn.clicked.connect(self.prevStep)
        layout.addWidget(self.prev_btn)
        
        self.next_btn = QPushButton("⏭️ 下一步")
        self.next_btn.clicked.connect(self.nextStep)
        layout.addWidget(self.next_btn)
        
        layout.addStretch()
        
        # 应用决策按钮
        self.apply_btn = QPushButton("应用决策并继续")
        self.apply_btn.setStyleSheet("""
            QPushButton {
                background: #28a745;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #218838;
            }
        """)
        self.apply_btn.clicked.connect(self.applyDecisionAndContinue)
        self.apply_btn.setEnabled(False)
        layout.addWidget(self.apply_btn)
        
        return group
    
    def _createLeftPanel(self):
        """创建左侧面板"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # 用户选择
        user_select_group = QGroupBox("选择用户")
        user_select_layout = QVBoxLayout(user_select_group)
        
        # 用户筛选
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("筛选:"))
        
        self.user_filter_combo = QComboBox()
        self.user_filter_combo.addItems(["全部用户", "需要充电", "行驶中", "等待中", "充电中"])
        self.user_filter_combo.currentTextChanged.connect(self.updateUserList)
        filter_layout.addWidget(self.user_filter_combo)
        
        user_select_layout.addLayout(filter_layout)
        
        # 用户列表
        self.user_list = QListWidget()
        self.user_list.itemClicked.connect(self.onUserSelected)
        user_select_layout.addWidget(self.user_list)
        
        layout.addWidget(user_select_group)
        
        # 当前选中用户信息简要显示
        current_user_group = QGroupBox("当前用户")
        current_user_layout = QVBoxLayout(current_user_group)
        
        self.current_user_label = QLabel("未选择用户")
        self.current_user_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.current_user_label.setStyleSheet("font-size: 12px; color: #6c757d;")
        current_user_layout.addWidget(self.current_user_label)
        
        layout.addWidget(current_user_group)
        
        return widget
    
    def _createRightPanel(self):
        """创建右侧面板"""
        # 使用选项卡组织内容
        tab_widget = QTabWidget()
        
        # 用户信息选项卡
        self.user_info_panel = UserInfoPanel()
        tab_widget.addTab(self.user_info_panel, "用户信息")
        
        # 行程信息选项卡
        from trip_info_panel import TripInfoPanel
        self.trip_info_panel = TripInfoPanel()
        tab_widget.addTab(self.trip_info_panel, "行程信息")
        
        # 充电历史选项卡
        self.history_panel = ChargingHistoryPanel()
        tab_widget.addTab(self.history_panel, "充电历史")
        
        # 充电站推荐选项卡
        self.recommendation_panel = StationRecommendationPanel()
        self.recommendation_panel.stationSelected.connect(self.onStationSelected)
        
        # 连接trip_info_panel的充电决策信号
        self.trip_info_panel.chargingDecisionMade.connect(self.onTripInfoChargingDecision)
        tab_widget.addTab(self.recommendation_panel, "充电站推荐")
        
        # 充电站详情选项卡
        self.details_panel = StationDetailsPanel()
        self.details_panel.chargingRequested.connect(self.onChargingRequested)
        tab_widget.addTab(self.details_panel, "充电站详情")
        
        # 预约管理选项卡
        self.reservation_panel = ReservationListWidget()
        self.reservation_panel.reservationCancelled.connect(self.onReservationCancelled)
        tab_widget.addTab(self.reservation_panel, "我的预约")
        
        return tab_widget
    
    def updateSimulationData(self, step, max_step, simulation_data):
        """更新仿真数据"""
        self.current_step = step
        self.max_step = max_step
        self.simulation_data = simulation_data
        
        # 提取仿真时间信息
        timestamp_str = simulation_data.get('timestamp')
        if timestamp_str:
            try:
                from datetime import datetime
                self.current_simulation_time = datetime.fromisoformat(timestamp_str)
            except (ValueError, TypeError):
                self.current_simulation_time = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            self.current_simulation_time = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        # 更新步骤显示
        self.step_slider.setMaximum(max_step)
        self.step_slider.setValue(step)
        self.step_label.setText(f"{step}/{max_step}")
        
        # 更新用户列表
        self.updateUserList()
        
        # 如果有选中的用户，更新其信息
        if self.current_user_id:
            self.updateCurrentUserInfo()
    
    def updateUserList(self):
        """更新用户列表"""
        self.user_list.clear()
        
        users_data = self.simulation_data.get('users', [])
        filter_type = self.user_filter_combo.currentText()
        
        # 应用筛选
        filtered_users = []
        for user in users_data:
            if filter_type == "全部用户":
                filtered_users.append(user)
            elif filter_type == "需要充电" and user.get('needs_charge_decision'):
                filtered_users.append(user)
            elif filter_type == "行驶中" and user.get('status') == 'traveling':
                filtered_users.append(user)
            elif filter_type == "等待中" and user.get('status') == 'waiting':
                filtered_users.append(user)
            elif filter_type == "充电中" and user.get('status') == 'charging':
                filtered_users.append(user)
        
        # 添加到列表
        for user in filtered_users[:50]:  # 限制显示数量
            item_text = f"{user.get('user_id', '')} | {user.get('status', '')} | SOC: {user.get('soc', 0):.1f}%"
            item = QListWidgetItem(item_text)
            item.setData(Qt.ItemDataRole.UserRole, user.get('user_id'))
            
            # 设置颜色
            status = user.get('status', '')
            if status == 'charging':
                item.setBackground(QColor(200, 255, 200))
            elif status == 'waiting':
                item.setBackground(QColor(255, 255, 200))
            elif user.get('needs_charge_decision'):
                item.setBackground(QColor(255, 200, 200))
            
            self.user_list.addItem(item)
    
    def onUserSelected(self, item):
        """处理用户选择"""
        user_id = item.data(Qt.ItemDataRole.UserRole)
        if user_id:
            self.current_user_id = user_id
            self.userSelected.emit(user_id)
            self.updateCurrentUserInfo()
            self.updateRecommendations()
            
            # 更新行程信息面板
            if hasattr(self, 'trip_info_panel'):
                self.trip_info_panel.setSelectedUser(user_id)
            
            # 启用应用决策按钮
            self.apply_btn.setEnabled(True)
    
    def updateCurrentUserInfo(self):
        """更新当前用户信息"""
        if not self.current_user_id:
            return
        
        # 找到当前用户数据
        users_data = self.simulation_data.get('users', [])
        current_user = None
        for user in users_data:
            if user.get('user_id') == self.current_user_id:
                current_user = user
                break
        
        if not current_user:
            return
        
        # 更新显示
        self.current_user_label.setText(f"用户: {self.current_user_id}\n状态: {current_user.get('status', '')}\nSOC: {current_user.get('soc', 0):.1f}%")
        
        # 更新各个面板
        charging_history = current_user.get('charging_history', [])
        self.user_info_panel.updateUserInfo(current_user, charging_history)
        self.history_panel.updateHistory(charging_history)
        
        # 更新充电站详情面板的用户数据
        self.details_panel.setCurrentUserData(current_user)
        
        # 更新预约面板
        user_reservations = reservation_manager.getUserReservations(self.current_user_id)
        self.reservation_panel.updateReservations(user_reservations)
    
    def updateRecommendations(self):
        """更新充电站推荐"""
        if not self.current_user_id:
            return
        
        # 获取当前用户
        users_data = self.simulation_data.get('users', [])
        current_user = None
        for user in users_data:
            if user.get('user_id') == self.current_user_id:
                current_user = user
                break
        
        if not current_user:
            return
        
        user_position = current_user.get('current_position', {})
        chargers_data = self.simulation_data.get('chargers', [])
        
        # 生成推荐数据
        recommendations = self._generateRecommendations(current_user, chargers_data)
        
        # 更新推荐面板
        self.recommendation_panel.updateStations(recommendations, user_position)
    
    def _generateRecommendations(self, user, chargers_data):
        """生成个性化充电站推荐"""
        recommendations = []
        user_pos = user.get('current_position', {})
        
        # 获取用户充电历史和偏好分析
        charging_history = user.get('charging_history', [])
        user_preferences = self._analyzeUserPreferences(charging_history, user)
        
        for charger in chargers_data[:20]:  # 限制数量
            if charger.get('status') == 'failure':
                continue
            
            charger_pos = charger.get('position', {})
            
            # 计算真实距离
            user_pos = user.get('current_position', {})
            if user_pos.get('lat') and user_pos.get('lng') and charger_pos.get('lat') and charger_pos.get('lng'):
                # 使用简化的距离计算公式（度数转换为公里）
                lat_diff = user_pos['lat'] - charger_pos['lat']
                lng_diff = user_pos['lng'] - charger_pos['lng']
                distance = ((lat_diff ** 2 + lng_diff ** 2) ** 0.5) * 111  # 大约1度=111公里
            else:
                distance = random.uniform(0.5, 10.0)  # 备用距离
            
            eta_minutes = max(5, int(distance * 3 + random.uniform(-2, 5)))  # 基于真实距离的预估时间
            
            # 生成真实地址（基于坐标）
            lat = charger_pos.get('lat', 0)
            lng = charger_pos.get('lng', 0)
            real_address = f"经度{lng:.4f}°, 纬度{lat:.4f}°"
            
            # 生成更有区分性的充电站名称
            charger_id = charger.get('charger_id', '')
            charger_number = charger_id.split('_')[-1] if '_' in charger_id else charger_id
            station_name = charger.get('location', f"充电站{charger_number}")
            charger_type_cn = {'superfast': '超快充', 'fast': '快充', 'normal': '慢充'}.get(charger.get('type', 'normal'), '普通')
            full_name = f"{station_name}-{charger_type_cn}桩({charger_id})"
            
            # 实时价格预测
            base_price = charger.get('price_multiplier', 1.0) * 0.85
            predicted_price_factor = self._predictPriceFactor(charger, eta_minutes)
            predicted_price = base_price * predicted_price_factor
            
            # 个性化评分计算
            base_rating = round(4.0 + (charger.get('max_power', 60) - 50) / 100, 1)
            preference_score = self._calculatePreferenceScore(charger, user_preferences, distance, predicted_price)
            personalized_rating = min(5.0, base_rating + preference_score)
            
            # 个性化标签生成
            tags = self._generatePersonalizedTags(charger, user_preferences, charging_history, predicted_price, base_price)
            
            # 个性化成本估算
            base_cost = distance * 0.5 + charger.get('max_power', 60) * 0.3
            preference_cost_adjustment = self._calculatePreferenceCostAdjustment(charger, user_preferences)
            estimated_cost = round(base_cost + preference_cost_adjustment, 1)
            
            # 生成推荐数据
            station = ChargingStation(
                station_id=charger_id,
                name=full_name,
                address=real_address,
                lat=lat,
                lng=lng,
                distance=round(distance, 2),
                eta_minutes=eta_minutes,
                available_chargers=1 if charger.get('status') == 'available' else 0,
                total_chargers=1,
                queue_length=len(charger.get('queue', [])),
                wait_time_minutes=len(charger.get('queue', [])) * 15,
                max_power=charger.get('max_power', 60),
                current_price=round(predicted_price, 2),
                rating=round(personalized_rating, 1),
                tags=tags,
                estimated_cost=estimated_cost
            )
            
            # 添加个性化属性
            station.preference_score = round(preference_score, 2)
            station.price_trend = self._getPriceTrend(predicted_price_factor)
            
            recommendations.append(station)
        
        # 个性化排序：综合偏好分数、距离和价格
        recommendations.sort(key=lambda x: (
            -getattr(x, 'preference_score', 0) * 2,  # 偏好分数权重最高
            x.distance * 0.5,                        # 距离权重中等
            x.current_price * 0.3                    # 价格权重较低
        ))
        
        return recommendations
    
    def _analyzeUserPreferences(self, charging_history, user):
        """分析用户充电偏好"""
        preferences = {
            'preferred_charger_types': {},
            'preferred_power_range': [50, 120],
            'price_sensitivity': 0.5,
            'distance_tolerance': 5.0,
            'time_preferences': {},
            'location_preferences': {},
            'avg_charging_duration': 30,
            'preferred_soc_range': [20, 80]
        }
        
        if not charging_history:
            return preferences
        
        # 分析充电桩类型偏好
        type_counts = {}
        power_values = []
        durations = []
        soc_values = []
        
        for session in charging_history[-20:]:  # 分析最近20次充电记录
            charger_type = session.get('charger_type', 'normal')
            type_counts[charger_type] = type_counts.get(charger_type, 0) + 1
            
            power = session.get('power_kw', 60)
            power_values.append(power)
            
            duration = session.get('duration_minutes', 30)
            durations.append(duration)
            
            final_soc = session.get('final_soc', 80)
            soc_values.append(final_soc)
        
        # 计算偏好
        if type_counts:
            preferences['preferred_charger_types'] = type_counts
        
        if power_values:
            avg_power = sum(power_values) / len(power_values)
            preferences['preferred_power_range'] = [max(30, avg_power - 20), min(150, avg_power + 20)]
        
        if durations:
            preferences['avg_charging_duration'] = sum(durations) / len(durations)
        
        if soc_values:
            avg_soc = sum(soc_values) / len(soc_values)
            preferences['preferred_soc_range'] = [max(10, avg_soc - 20), min(100, avg_soc + 10)]
        
        # 分析价格敏感度
        user_type = user.get('user_type', 'normal')
        if user_type == 'economic':
            preferences['price_sensitivity'] = 0.8
        elif user_type == 'business':
            preferences['price_sensitivity'] = 0.3
        else:
            preferences['price_sensitivity'] = 0.5
        
        return preferences
    
    def _calculatePreferenceScore(self, charger, user_preferences, distance, price):
        """计算个性化偏好分数"""
        score = 0.0
        
        # 充电桩类型偏好
        charger_type = charger.get('type', 'normal')
        type_prefs = user_preferences.get('preferred_charger_types', {})
        if charger_type in type_prefs:
            total_sessions = sum(type_prefs.values())
            type_ratio = type_prefs[charger_type] / total_sessions
            score += type_ratio * 0.3
        
        # 功率偏好
        power = charger.get('max_power', 60)
        power_range = user_preferences.get('preferred_power_range', [50, 120])
        if power_range[0] <= power <= power_range[1]:
            score += 0.2
        
        # 距离偏好
        distance_tolerance = user_preferences.get('distance_tolerance', 5.0)
        if distance <= distance_tolerance:
            score += 0.2 * (1 - distance / distance_tolerance)
        
        # 价格偏好
        price_sensitivity = user_preferences.get('price_sensitivity', 0.5)
        base_price = 0.85
        if price <= base_price:
            score += 0.3 * (1 - price_sensitivity)
        else:
            score -= 0.2 * price_sensitivity * (price - base_price) / base_price
        
        return max(0, min(1, score))
    
    def _predictPriceFactor(self, charger, eta_minutes):
        """预测价格变化因子"""
        from datetime import datetime, timedelta
        
        # 获取预计到达时间
        arrival_time = datetime.now() + timedelta(minutes=eta_minutes)
        hour = arrival_time.hour
        
        # 基于时间的价格预测
        if 7 <= hour <= 9 or 17 <= hour <= 21:  # 高峰期
            price_factor = 1.1
        elif 22 <= hour or hour <= 6:  # 谷期
            price_factor = 0.9
        else:  # 平期
            price_factor = 1.0
        
        # 基于充电桩类型的价格调整
        charger_type = charger.get('type', 'normal')
        if charger_type == 'superfast':
            price_factor *= 1.05
        elif charger_type == 'normal':
            price_factor *= 0.95
        
        # 基于队列长度的价格调整
        queue_length = len(charger.get('queue', []))
        if queue_length > 2:
            price_factor *= 1.02
        elif queue_length == 0:
            price_factor *= 0.98
        
        return price_factor
    
    def _calculatePreferenceCostAdjustment(self, charger, user_preferences):
        """计算基于偏好的成本调整"""
        adjustment = 0.0
        
        # 如果不是偏好的充电桩类型，增加成本
        charger_type = charger.get('type', 'normal')
        type_prefs = user_preferences.get('preferred_charger_types', {})
        if type_prefs and charger_type not in type_prefs:
            adjustment += 2.0
        
        # 功率不在偏好范围内，增加成本
        power = charger.get('max_power', 60)
        power_range = user_preferences.get('preferred_power_range', [50, 120])
        if not (power_range[0] <= power <= power_range[1]):
            adjustment += 1.5
        
        return adjustment
    
    def _generatePersonalizedTags(self, charger, user_preferences, charging_history, predicted_price, base_price):
        """生成个性化标签"""
        tags = []
        
        # 基础标签
        charger_type = charger.get('type', 'normal')
        if charger_type == 'superfast':
            tags.append('超快充')
        elif charger_type == 'fast':
            tags.append('快充')
        else:
            tags.append('慢充')
        
        if charger.get('status') == 'available':
            tags.append('有车位')
        
        # 个性化标签
        type_prefs = user_preferences.get('preferred_charger_types', {})
        if charger_type in type_prefs:
            tags.append('偏好类型')
        
        # 价格标签
        if predicted_price < base_price * 0.9:
            tags.append('优惠价格')
        elif predicted_price > base_price * 1.1:
            tags.append('高峰价格')
        
        # 功率标签
        power = charger.get('max_power', 60)
        power_range = user_preferences.get('preferred_power_range', [50, 120])
        if power_range[0] <= power <= power_range[1]:
            tags.append('适合功率')
        
        # 历史使用标签
        charger_id = charger.get('charger_id', '')
        if self._isFrequentlyUsed(charger_id, charging_history):
            tags.append('常用站点')
        
        return tags
    
    def _isFrequentlyUsed(self, charger_id, charging_history):
        """检查是否为常用充电站"""
        if not charging_history:
            return False
        
        usage_count = sum(1 for session in charging_history 
                         if session.get('charger_id') == charger_id)
        return usage_count >= 2
    
    def _getPriceTrend(self, price_factor):
        """获取价格趋势"""
        if price_factor > 1.05:
            return '上涨'
        elif price_factor < 0.95:
            return '下降'
        else:
            return '稳定'
    
    def _generateTags(self, charger):
        """生成充电站标签（保留原方法以兼容）"""
        tags = []
        
        charger_type = charger.get('type', 'normal')
        if charger_type == 'superfast':
            tags.append('超快充')
        elif charger_type == 'fast':
            tags.append('快充')
        else:
            tags.append('慢充')
        
        if charger.get('status') == 'available':
            tags.append('有车位')
        
        price_multiplier = charger.get('price_multiplier', 1.0)
        if price_multiplier < 1.0:
            tags.append('低价格')
        
        return tags
    
    def onStationSelected(self, station_id):
        """处理充电站选择"""
        # 查找充电站详细信息
        chargers_data = self.simulation_data.get('chargers', [])
        selected_charger = None
        
        for charger in chargers_data:
            if charger.get('charger_id') == station_id:
                selected_charger = charger
                break
        
        if selected_charger:
            # 生成详细信息
            station_details = self._generateStationDetails(selected_charger)
            self.details_panel.showStationDetails(station_details)
    
    def _generateStationDetails(self, charger):
        """生成充电站详细信息（使用真实数据，包含价格预测）"""
        # 获取当前用户信息
        current_user = self.simulation_data.get('users', [{}])[0] if self.simulation_data.get('users') else {}
        charging_history = current_user.get('charging_history', [])
        user_preferences = self._analyzeUserPreferences(charging_history, current_user)
        
        # 计算真实距离
        user_pos = self.getCurrentUserPosition()
        charger_pos = charger.get('position', {})
        if user_pos.get('lat') and user_pos.get('lng') and charger_pos.get('lat') and charger_pos.get('lng'):
            lat_diff = user_pos['lat'] - charger_pos['lat']
            lng_diff = user_pos['lng'] - charger_pos['lng']
            distance = ((lat_diff ** 2 + lng_diff ** 2) ** 0.5) * 111
        else:
            distance = 5.0  # 备用距离
        
        # 生成真实地址
        lat = charger_pos.get('lat', 0)
        lng = charger_pos.get('lng', 0)
        real_address = f"经度{lng:.4f}°, 纬度{lat:.4f}°"
        
        # 生成更有区分性的充电站名称
        charger_id = charger.get('charger_id', '')
        charger_number = charger_id.split('_')[-1] if '_' in charger_id else charger_id
        station_name = charger.get('location', f"充电站{charger_number}")
        charger_type_cn = {'superfast': '超快充', 'fast': '快充', 'normal': '慢充'}.get(charger.get('type', 'normal'), '普通')
        full_name = f"{station_name}-{charger_type_cn}桩({charger_id})"
        
        return {
            'station_id': charger_id,
            'name': full_name,
            'address': real_address,
            'operator': f"{charger.get('region', 'Region_1')}运营商",
            'open_hours': '24小时',
            'available_chargers': 1 if charger.get('status') == 'available' else 0,
            'total_chargers': 1,
            'queue_length': len(charger.get('queue', [])),
            'wait_time_minutes': len(charger.get('queue', [])) * 15,
            'current_price': charger.get('price_multiplier', 1.0) * 0.85,
            'charger_types': [charger.get('type', 'normal')],
            'interfaces': ['国标'],
            'max_power': charger.get('max_power', 60),
            'rating': round(4.0 + (charger.get('max_power', 60) - 50) / 100, 1),  # 基于功率的真实评分
            'review_count': max(10, int(charger.get('max_power', 60) * 2)),  # 基于功率的评论数量
            'price_details': {
                'peak': {'electricity': 1.2, 'service': 0.5},
                'normal': {'electricity': 0.85, 'service': 0.4},
                'valley': {'electricity': 0.4, 'service': 0.3}
            }
        }
    
    def getCurrentUserPosition(self):
        """获取当前用户位置"""
        if not self.current_user_id:
            return {}
        
        users_data = self.simulation_data.get('users', [])
        for user in users_data:
            if user.get('user_id') == self.current_user_id:
                return user.get('current_position', {})
        return {}
    
    def onChargingRequested(self, station_id, charging_params):
        """处理充电请求"""
        if self.current_user_id:
            self.chargingDecisionMade.emit(self.current_user_id, station_id, charging_params)
            QMessageBox.information(self, "充电请求", f"已为用户 {self.current_user_id} 请求在 {station_id} 充电")
            
    def onReservationCancelled(self, reservation_id):
        """处理预约取消"""
        reply = QMessageBox.question(
            self, "确认取消", 
            f"确定要取消预约 {reservation_id} 吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            if reservation_manager.cancelReservation(reservation_id):
                QMessageBox.information(self, "取消成功", "预约已成功取消")
                # 刷新预约列表
                if self.current_user_id:
                    user_reservations = reservation_manager.getUserReservations(self.current_user_id)
                    self.reservation_panel.updateReservations(user_reservations)
            else:
                QMessageBox.warning(self, "取消失败", "预约取消失败，请稍后重试")
    
    def onStepChanged(self, step):
        """处理步骤改变"""
        self.current_step = step
        self.step_label.setText(f"{step}/{self.max_step}")
        self.simulationStepChanged.emit(step)
    
    def togglePause(self):
        """切换暂停状态"""
        self.is_paused = not self.is_paused
        if self.is_paused:
            self.pause_btn.setText("▶️ 继续")
        else:
            self.pause_btn.setText("⏸️ 暂停")
    
    def prevStep(self):
        """上一步"""
        if self.current_step > 0:
            self.step_slider.setValue(self.current_step - 1)
    
    def nextStep(self):
        """下一步"""
        if self.current_step < self.max_step:
            self.step_slider.setValue(self.current_step + 1)
    
    def setSimulationEnvironment(self, environment):
        """设置仿真环境"""
        self.simulation_environment = environment
        
        # 将仿真环境传递给行程信息面板
        if hasattr(self, 'trip_info_panel'):
            self.trip_info_panel.setSimulationEnvironment(environment)
    
    def applyDecisionAndContinue(self):
        """应用决策并继续仿真"""
        if self.current_user_id:
            # 发射信号通知主GUI继续仿真
            self.decisionAppliedAndContinue.emit()
            QMessageBox.information(self, "决策应用", "用户决策已应用，仿真将继续")
            self.apply_btn.setEnabled(False)
    
    def onTripInfoChargingDecision(self, user_id: str, station_id: str, charging_params: dict):
        """处理来自行程信息面板的充电决策"""
        logger.info(f"用户面板接收到来自行程信息面板的充电决策: 用户{user_id} -> 充电站{station_id}")
        
        # 转发充电决策信号到主窗口
        self.chargingDecisionMade.emit(user_id, station_id, charging_params)
        logger.info(f"已转发充电决策信号到主窗口")