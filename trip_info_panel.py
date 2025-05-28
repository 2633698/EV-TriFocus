# -*- coding: utf-8 -*-
"""
行程信息面板组件
提供全面的出行规划界面，包括当前导航路线显示、预计到达时间计算、
沿途充电站推荐和路线优化建议
"""

import sys
import json
import logging
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

# 创建专门的调试日志记录器
debug_logger = logging.getLogger('trip_info_debug')
debug_handler = logging.FileHandler('trip_info_debug.log', encoding='utf-8')
debug_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
debug_handler.setFormatter(debug_formatter)
debug_logger.addHandler(debug_handler)
debug_logger.setLevel(logging.DEBUG)

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, 
    QPushButton, QGroupBox, QScrollArea, QFrame, QListWidget,
    QListWidgetItem, QComboBox, QSpinBox, QDoubleSpinBox,
    QTextEdit, QProgressBar, QTabWidget, QTableWidget,
    QTableWidgetItem, QHeaderView, QSlider, QCheckBox,
    QSplitter, QDialog, QDialogButtonBox, QFormLayout,
    QMessageBox, QLineEdit, QTreeWidget, QTreeWidgetItem
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread, QSize, QRect
from PyQt6.QtGui import (
    QFont, QPainter, QPen, QBrush, QColor, QPixmap, QIcon,
    QLinearGradient, QPalette, QPolygonF
)

from trip_planning_module import (
    trip_planning_engine, RoutePoint, ChargingStopRecommendation, 
    RouteOptimization
)

logger = logging.getLogger(__name__)

class RouteVisualizationWidget(QWidget):
    """路线可视化组件"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.route_points = []
        self.current_position_index = 0
        self.setMinimumSize(400, 300)
        self.setStyleSheet("""
            QWidget {
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 8px;
            }
        """)
    
    def updateRoute(self, route_points: List[RoutePoint]):
        """更新路线数据"""
        self.route_points = route_points
        self.update()
    
    def setCurrentPosition(self, index: int):
        """设置当前位置"""
        self.current_position_index = index
        self.update()
    
    def paintEvent(self, event):
        """绘制路线图"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        if not self.route_points:
            painter.setPen(QPen(QColor(108, 117, 125)))
            painter.setFont(QFont("Arial", 12))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "暂无路线数据")
            return
        
        # 绘制路线
        self._drawRoute(painter)
        
        # 绘制路线点
        self._drawRoutePoints(painter)
        
        # 绘制当前位置
        self._drawCurrentPosition(painter)
    
    def _drawRoute(self, painter):
        """绘制路线"""
        if len(self.route_points) < 2:
            return
        
        painter.setPen(QPen(QColor(0, 123, 255), 3))
        
        # 简化的路线绘制（直线连接）
        for i in range(len(self.route_points) - 1):
            start_point = self._mapToWidget(self.route_points[i])
            end_point = self._mapToWidget(self.route_points[i + 1])
            painter.drawLine(start_point, end_point)
    
    def _drawRoutePoints(self, painter):
        """绘制路线点"""
        for i, point in enumerate(self.route_points):
            widget_pos = self._mapToWidget(point)
            
            # 根据点类型选择颜色
            if point.type == "start":
                color = QColor(40, 167, 69)  # 绿色
            elif point.type == "destination":
                color = QColor(220, 53, 69)  # 红色
            elif point.type == "charger":
                color = QColor(255, 193, 7)  # 黄色
            else:
                color = QColor(108, 117, 125)  # 灰色
            
            painter.setBrush(QBrush(color))
            painter.setPen(QPen(color.darker(), 2))
            painter.drawEllipse(widget_pos.x() - 6, widget_pos.y() - 6, 12, 12)
            
            # 绘制点名称
            if point.name:
                painter.setPen(QPen(QColor(50, 50, 50)))
                painter.setFont(QFont("Arial", 8))
                painter.drawText(widget_pos.x() + 10, widget_pos.y() + 5, point.name)
    
    def _drawCurrentPosition(self, painter):
        """绘制当前位置"""
        if 0 <= self.current_position_index < len(self.route_points):
            current_point = self.route_points[self.current_position_index]
            widget_pos = self._mapToWidget(current_point)
            
            # 绘制当前位置标记（闪烁的圆圈）
            painter.setBrush(QBrush(QColor(255, 0, 0, 100)))
            painter.setPen(QPen(QColor(255, 0, 0), 3))
            painter.drawEllipse(widget_pos.x() - 10, widget_pos.y() - 10, 20, 20)
    
    def _mapToWidget(self, point: RoutePoint):
        """将地理坐标映射到组件坐标"""
        # 简化的坐标映射
        if not self.route_points:
            return self.rect().center()
        
        # 计算边界
        min_lat = min(p.lat for p in self.route_points)
        max_lat = max(p.lat for p in self.route_points)
        min_lng = min(p.lng for p in self.route_points)
        max_lng = max(p.lng for p in self.route_points)
        
        # 映射到组件坐标
        margin = 20
        width = self.width() - 2 * margin
        height = self.height() - 2 * margin
        
        if max_lat == min_lat:
            y = height // 2
        else:
            y = margin + height * (1 - (point.lat - min_lat) / (max_lat - min_lat))
        
        if max_lng == min_lng:
            x = width // 2
        else:
            x = margin + width * (point.lng - min_lng) / (max_lng - min_lng)
        
        return self.rect().topLeft() + QRect(int(x), int(y), 0, 0).topLeft()

class ChargingStationRecommendationWidget(QWidget):
    """充电站推荐组件"""
    
    station_selected = pyqtSignal(str)  # 充电站被选中信号
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.recommendations = []
        self.setupUI()
    
    def setupUI(self):
        layout = QVBoxLayout(self)
        
        # 标题
        title_label = QLabel("沿途充电站推荐")
        title_label.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        layout.addWidget(title_label)
        
        # 充电站列表
        self.station_list = QListWidget()
        self.station_list.itemClicked.connect(self._onStationClicked)
        layout.addWidget(self.station_list)
    
    def updateRecommendations(self, recommendations: List[ChargingStopRecommendation]):
        """更新充电站推荐"""
        self.recommendations = recommendations
        self.station_list.clear()
        
        for rec in recommendations:
            item_widget = self._createStationItem(rec)
            item = QListWidgetItem()
            item.setSizeHint(item_widget.sizeHint())
            item.setData(Qt.ItemDataRole.UserRole, rec.station_id)
            self.station_list.addItem(item)
            self.station_list.setItemWidget(item, item_widget)
    
    def _createStationItem(self, rec: ChargingStopRecommendation) -> QWidget:
        """创建充电站项目组件"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 8, 10, 8)
        
        # 第一行：名称和紧急程度
        header_layout = QHBoxLayout()
        
        name_label = QLabel(rec.name)
        name_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        header_layout.addWidget(name_label)
        
        urgency_label = QLabel(self._getUrgencyText(rec.urgency_level))
        urgency_label.setStyleSheet(self._getUrgencyStyle(rec.urgency_level))
        urgency_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        header_layout.addWidget(urgency_label)
        
        layout.addLayout(header_layout)
        
        # 第二行：距离和绕行信息
        distance_label = QLabel(f"距离路线: {rec.distance_from_route:.1f}km | 绕行: {rec.detour_distance:.1f}km")
        distance_label.setStyleSheet("color: #6c757d; font-size: 9px;")
        layout.addWidget(distance_label)
        
        # 第三行：充电信息
        charging_info = QHBoxLayout()
        
        power_label = QLabel(f"⚡ {rec.max_power}kW")
        charging_info.addWidget(power_label)
        
        time_label = QLabel(f"⏱ {rec.estimated_charging_time}分钟")
        charging_info.addWidget(time_label)
        
        cost_label = QLabel(f"💰 ¥{rec.estimated_cost:.1f}")
        charging_info.addWidget(cost_label)
        
        rating_label = QLabel(f"⭐ {rec.rating:.1f}")
        charging_info.addWidget(rating_label)
        
        charging_info.addStretch()
        layout.addLayout(charging_info)
        
        # 可用充电桩
        availability_label = QLabel(f"可用充电桩: {rec.available_chargers}个")
        availability_label.setStyleSheet("color: #28a745; font-size: 9px;")
        layout.addWidget(availability_label)
        
        # 设置样式
        widget.setStyleSheet("""
            QWidget {
                background-color: white;
                border: 1px solid #dee2e6;
                border-radius: 6px;
                margin: 2px;
            }
            QWidget:hover {
                background-color: #f8f9fa;
                border-color: #007bff;
            }
        """)
        
        return widget
    
    def _getUrgencyText(self, urgency: str) -> str:
        """获取紧急程度文本"""
        urgency_map = {
            'low': '建议',
            'medium': '推荐', 
            'high': '重要',
            'critical': '紧急'
        }
        return urgency_map.get(urgency, '未知')
    
    def _getUrgencyStyle(self, urgency: str) -> str:
        """获取紧急程度样式"""
        style_map = {
            'low': 'background-color: #d4edda; color: #155724; padding: 2px 6px; border-radius: 3px; font-size: 9px;',
            'medium': 'background-color: #fff3cd; color: #856404; padding: 2px 6px; border-radius: 3px; font-size: 9px;',
            'high': 'background-color: #f8d7da; color: #721c24; padding: 2px 6px; border-radius: 3px; font-size: 9px;',
            'critical': 'background-color: #f5c6cb; color: #721c24; padding: 2px 6px; border-radius: 3px; font-size: 9px; font-weight: bold;'
        }
        return style_map.get(urgency, '')
    
    def _onStationClicked(self, item):
        """充电站被点击"""
        station_id = item.data(Qt.ItemDataRole.UserRole)
        self.station_selected.emit(station_id)

class RouteOptimizationWidget(QWidget):
    """路线优化建议组件"""
    
    optimization_selected = pyqtSignal(str)  # 优化方案被选中信号
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.optimizations = []
        self.setupUI()
    
    def setupUI(self):
        layout = QVBoxLayout(self)
        
        # 标题
        title_label = QLabel("路线优化建议")
        title_label.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        layout.addWidget(title_label)
        
        # 优化建议列表
        self.optimization_list = QListWidget()
        self.optimization_list.itemClicked.connect(self._onOptimizationClicked)
        layout.addWidget(self.optimization_list)
    
    def updateOptimizations(self, optimizations: List[RouteOptimization]):
        """更新优化建议"""
        self.optimizations = optimizations
        self.optimization_list.clear()
        
        for opt in optimizations:
            item_widget = self._createOptimizationItem(opt)
            item = QListWidgetItem()
            item.setSizeHint(item_widget.sizeHint())
            item.setData(Qt.ItemDataRole.UserRole, opt.optimization_type)
            self.optimization_list.addItem(item)
            self.optimization_list.setItemWidget(item, item_widget)
    
    def _createOptimizationItem(self, opt: RouteOptimization) -> QWidget:
        """创建优化建议项目组件"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 8, 10, 8)
        
        # 优化类型标题
        type_label = QLabel(self._getOptimizationTypeText(opt.optimization_type))
        type_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        layout.addWidget(type_label)
        
        # 描述
        desc_label = QLabel(opt.description)
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("color: #495057; font-size: 9px;")
        layout.addWidget(desc_label)
        
        # 潜在节省
        savings_layout = QHBoxLayout()
        
        if opt.potential_savings.get('time_minutes', 0) != 0:
            time_saving = opt.potential_savings['time_minutes']
            time_label = QLabel(f"⏱ {'+' if time_saving > 0 else ''}{time_saving:.0f}分钟")
            time_label.setStyleSheet("color: #007bff; font-size: 9px;")
            savings_layout.addWidget(time_label)
        
        if opt.potential_savings.get('cost_yuan', 0) != 0:
            cost_saving = opt.potential_savings['cost_yuan']
            cost_label = QLabel(f"💰 {'+' if cost_saving > 0 else ''}¥{cost_saving:.1f}")
            cost_label.setStyleSheet("color: #28a745; font-size: 9px;")
            savings_layout.addWidget(cost_label)
        
        if opt.potential_savings.get('energy_kwh', 0) != 0:
            energy_saving = opt.potential_savings['energy_kwh']
            energy_label = QLabel(f"🔋 {'+' if energy_saving > 0 else ''}{energy_saving:.1f}kWh")
            energy_label.setStyleSheet("color: #ffc107; font-size: 9px;")
            savings_layout.addWidget(energy_label)
        
        savings_layout.addStretch()
        
        # 置信度
        confidence_label = QLabel(f"置信度: {opt.confidence*100:.0f}%")
        confidence_label.setStyleSheet("color: #6c757d; font-size: 8px;")
        savings_layout.addWidget(confidence_label)
        
        layout.addLayout(savings_layout)
        
        # 设置样式
        widget.setStyleSheet("""
            QWidget {
                background-color: white;
                border: 1px solid #dee2e6;
                border-radius: 6px;
                margin: 2px;
            }
            QWidget:hover {
                background-color: #f8f9fa;
                border-color: #007bff;
            }
        """)
        
        return widget
    
    def _getOptimizationTypeText(self, opt_type: str) -> str:
        """获取优化类型文本"""
        type_map = {
            'time': '⚡ 时间优化',
            'cost': '💰 经济优化',
            'energy': '🔋 能耗优化',
            'comfort': '😌 舒适优化'
        }
        return type_map.get(opt_type, '未知优化')
    
    def _onOptimizationClicked(self, item):
        """优化方案被点击"""
        opt_type = item.data(Qt.ItemDataRole.UserRole)
        self.optimization_selected.emit(opt_type)

class TripInfoPanel(QWidget):
    """行程信息主面板"""
    
    # 添加充电决策信号
    chargingDecisionMade = pyqtSignal(str, str, dict)  # 充电决策信号 (user_id, station_id, params)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_trip_data = None
        self.simulation_environment = None  # 仿真环境引用
        self.selected_user_id = None  # 当前选中的用户ID
        self.setupUI()
        self.setupConnections()
        
        # 真实数据更新定时器
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.updateTripInfo)
        self.update_timer.start(2000)  # 每2秒更新一次
    
    def setupUI(self):
        layout = QVBoxLayout(self)
        
        # 创建分割器
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # 左侧：路线可视化和基本信息
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        
        # 当前行程状态
        self.status_group = QGroupBox("当前行程状态")
        status_layout = QGridLayout(self.status_group)
        
        self.destination_label = QLabel("目的地: --")
        self.eta_label = QLabel("预计到达: --")
        self.remaining_distance_label = QLabel("剩余距离: --")
        self.remaining_time_label = QLabel("剩余时间: --")
        self.current_speed_label = QLabel("当前速度: --")
        self.battery_status_label = QLabel("电池状态: --")
        
        status_layout.addWidget(self.destination_label, 0, 0)
        status_layout.addWidget(self.eta_label, 0, 1)
        status_layout.addWidget(self.remaining_distance_label, 1, 0)
        status_layout.addWidget(self.remaining_time_label, 1, 1)
        status_layout.addWidget(self.current_speed_label, 2, 0)
        status_layout.addWidget(self.battery_status_label, 2, 1)
        
        left_layout.addWidget(self.status_group)
        
        # 路线可视化
        self.route_viz = RouteVisualizationWidget()
        route_group = QGroupBox("当前导航路线")
        route_layout = QVBoxLayout(route_group)
        route_layout.addWidget(self.route_viz)
        left_layout.addWidget(route_group)
        
        # 右侧：推荐和优化
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        
        # 充电站推荐
        self.charging_recommendations = ChargingStationRecommendationWidget()
        right_layout.addWidget(self.charging_recommendations)
        
        # 路线优化建议
        self.route_optimizations = RouteOptimizationWidget()
        right_layout.addWidget(self.route_optimizations)
        
        # 添加到分割器
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setSizes([600, 400])  # 设置初始比例
        
        layout.addWidget(splitter)
        
        # 底部控制按钮
        button_layout = QHBoxLayout()
        
        self.start_navigation_btn = QPushButton("开始导航")
        self.start_navigation_btn.setStyleSheet("""
            QPushButton {
                background-color: #007bff;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #0056b3;
            }
        """)
        
        self.stop_navigation_btn = QPushButton("停止导航")
        self.stop_navigation_btn.setStyleSheet("""
            QPushButton {
                background-color: #dc3545;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #c82333;
            }
        """)
        
        self.refresh_btn = QPushButton("刷新数据")
        self.refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #218838;
            }
        """)
        
        button_layout.addWidget(self.start_navigation_btn)
        button_layout.addWidget(self.stop_navigation_btn)
        button_layout.addWidget(self.refresh_btn)
        button_layout.addStretch()
        
        layout.addLayout(button_layout)
    
    def setupConnections(self):
        """设置信号连接"""
        self.charging_recommendations.station_selected.connect(self.onChargingStationSelected)
        self.route_optimizations.optimization_selected.connect(self.onOptimizationSelected)
        self.start_navigation_btn.clicked.connect(self.startNavigation)
        self.stop_navigation_btn.clicked.connect(self.stopNavigation)
        self.refresh_btn.clicked.connect(self.refreshTripData)
    
    def setSimulationEnvironment(self, environment):
        """设置仿真环境引用"""
        debug_logger.info(f"=== setSimulationEnvironment被调用 ===")
        debug_logger.info(f"传入的环境对象类型: {type(environment)}")
        debug_logger.info(f"环境对象是否为None: {environment is None}")
        if environment:
            debug_logger.info(f"环境对象属性: {dir(environment)}")
            debug_logger.info(f"是否有get_current_state方法: {hasattr(environment, 'get_current_state')}")
        
        self.simulation_environment = environment
        logger.info("行程信息面板已连接到仿真环境")
        debug_logger.info(f"设置后的simulation_environment: {self.simulation_environment}")
    
    def setSelectedUser(self, user_id):
        """设置当前选中的用户"""
        debug_logger.info(f"=== setSelectedUser被调用 ===")
        debug_logger.info(f"传入的user_id: {user_id}")
        debug_logger.info(f"之前的selected_user_id: {self.selected_user_id}")
        
        self.selected_user_id = user_id
        logger.info(f"行程信息面板选中用户: {user_id}")
        debug_logger.info(f"设置后的selected_user_id: {self.selected_user_id}")
        
        # 立即更新数据
        debug_logger.info("调用updateTripInfo()...")
        self.updateTripInfo()
    
    def updateTripInfo(self, user_id: str = None):
        """更新行程信息（使用真实仿真数据）"""
        debug_logger.info("=== 开始更新行程信息 ===")
        debug_logger.info(f"传入的user_id: {user_id}")
        debug_logger.info(f"当前选中的用户ID: {self.selected_user_id}")
        debug_logger.info(f"仿真环境是否存在: {self.simulation_environment is not None}")
        
        # 如果传入了user_id参数，更新选中的用户
        if user_id is not None:
            self.selected_user_id = user_id
            debug_logger.info(f"更新选中用户ID为: {self.selected_user_id}")
            
        if not self.simulation_environment or not self.selected_user_id:
            # 如果没有仿真环境或选中用户，显示默认信息
            debug_logger.warning(f"显示默认信息 - 仿真环境: {self.simulation_environment is not None}, 选中用户: {self.selected_user_id}")
            self._showDefaultInfo()
            return
        
        try:
            # 获取当前仿真状态
            debug_logger.info("正在获取仿真状态...")
            current_state = self.simulation_environment.get_current_state()
            debug_logger.info(f"获取到的状态类型: {type(current_state)}")
            debug_logger.info(f"状态键: {list(current_state.keys()) if isinstance(current_state, dict) else 'Not a dict'}")
            
            users_data = current_state.get('users', [])
            chargers_data = current_state.get('chargers', [])
            current_time = current_state.get('current_time')
            
            debug_logger.info(f"用户数据数量: {len(users_data)}")
            debug_logger.info(f"充电桩数据数量: {len(chargers_data)}")
            debug_logger.info(f"当前时间: {current_time}")
            
            # 记录前几个用户的信息
            if users_data:
                for i, user in enumerate(users_data[:3]):
                    if isinstance(user, dict):
                        debug_logger.info(f"用户{i}: ID={user.get('user_id')}, 状态={user.get('status')}, SOC={user.get('soc')}")
                    else:
                        debug_logger.info(f"用户{i}: 类型={type(user)}")
            
            # 找到选中的用户
            selected_user = None
            debug_logger.info(f"正在查找用户ID: {self.selected_user_id}")
            for user in users_data:
                if isinstance(user, dict) and user.get('user_id') == self.selected_user_id:
                    selected_user = user
                    debug_logger.info(f"找到匹配用户: {user}")
                    break
            
            if not selected_user:
                debug_logger.warning(f"未找到用户ID为 {self.selected_user_id} 的用户")
                debug_logger.info(f"可用用户ID列表: {[user.get('user_id') for user in users_data if isinstance(user, dict)]}")
                self._showUserNotFound()
                return
            
            debug_logger.info("开始生成行程数据...")
            # 生成基于真实数据的行程信息
            trip_data = self._generateTripDataFromSimulation(
                selected_user, chargers_data, current_time
            )
            
            debug_logger.info(f"生成的行程数据键: {list(trip_data.keys())}")
            self.current_trip_data = trip_data
            
            debug_logger.info("开始更新UI...")
            # 更新UI
            self._updateStatusLabels(trip_data)
            self.route_viz.updateRoute(trip_data['route'])
            self.charging_recommendations.updateRecommendations(trip_data['charging_recommendations'])
            self.route_optimizations.updateOptimizations(trip_data['optimizations'])
            
            debug_logger.info("=== 行程信息更新完成 ===")
            
        except Exception as e:
            debug_logger.error(f"更新行程信息时出错: {e}")
            debug_logger.error(f"错误类型: {type(e)}")
            import traceback
            debug_logger.error(f"错误堆栈: {traceback.format_exc()}")
            logger.error(f"更新行程信息时出错: {e}")
            self._showErrorInfo(str(e))
    
    def _generateTripDataFromSimulation(self, user_data, chargers_data, current_time):
        """从仿真数据生成行程信息"""
        debug_logger.info("=== 开始生成行程数据 ===")
        debug_logger.info(f"用户数据: {user_data}")
        debug_logger.info(f"充电桩数据数量: {len(chargers_data)}")
        debug_logger.info(f"当前时间: {current_time}")
        
        # 获取用户基本信息
        user_position = user_data.get('current_position', {})
        destination = user_data.get('destination', {})
        soc = user_data.get('soc', 0)
        battery_capacity = user_data.get('battery_capacity', 60)
        status = user_data.get('status', 'idle')
        target_charger = user_data.get('target_charger')
        
        debug_logger.info(f"用户位置: {user_position}")
        debug_logger.info(f"目的地: {destination}")
        debug_logger.info(f"SOC: {soc}%")
        debug_logger.info(f"电池容量: {battery_capacity}kWh")
        debug_logger.info(f"状态: {status}")
        debug_logger.info(f"目标充电桩: {target_charger}")
        
        # 生成路线点
        route_points = self._generateRoutePoints(user_position, destination, target_charger, chargers_data)
        
        # 生成充电站推荐
        charging_recommendations = self._generateChargingRecommendations(
            user_position, chargers_data, soc, battery_capacity
        )
        
        # 生成路线优化建议
        optimizations = self._generateOptimizations(user_data, chargers_data)
        
        # 计算统计信息
        statistics = self._calculateTripStatistics(
            user_position, destination, soc, battery_capacity, current_time
        )
        
        return {
            'route': route_points,
            'charging_recommendations': charging_recommendations,
            'optimizations': optimizations,
            'statistics': statistics,
            'user_data': user_data,
            'current_time': current_time
        }
    
    def _generateRoutePoints(self, start_pos, destination, target_charger, chargers_data):
        """生成路线点"""
        from trip_planning_module import RoutePoint
        
        route_points = []
        
        # 起点
        if start_pos:
            route_points.append(RoutePoint(
                lat=start_pos.get('lat', 0),
                lng=start_pos.get('lng', 0),
                type='start',
                name='当前位置'
            ))
        
        # 目标充电站（如果有）
        if target_charger:
            for charger in chargers_data:
                if isinstance(charger, dict) and charger.get('charger_id') == target_charger:
                    route_points.append(RoutePoint(
                        lat=charger.get('lat', 0),
                        lng=charger.get('lng', 0),
                        type='charging_station',
                        name=f"充电站 {charger.get('station_id', 'Unknown')}"
                    ))
                    break
        
        # 目的地
        if destination:
            route_points.append(RoutePoint(
                lat=destination.get('lat', 0),
                lng=destination.get('lng', 0),
                type='destination',
                name='目的地'
            ))
        
        return route_points
    
    def _generateChargingRecommendations(self, user_position, chargers_data, soc, battery_capacity):
        """生成充电站推荐"""
        from trip_planning_module import ChargingStopRecommendation
        from simulation.utils import calculate_distance
        
        recommendations = []
        
        # 按距离排序充电站
        charger_distances = []
        for charger in chargers_data:
            if isinstance(charger, dict) and charger.get('status') == 'available':
                # 从position字段获取坐标信息
                position = charger.get('position', {})
                charger_pos = {'lat': position.get('lat', 0), 'lng': position.get('lng', 0)}
                distance = calculate_distance(user_position, charger_pos)
                charger_distances.append((distance, charger))
        
        charger_distances.sort(key=lambda x: x[0])
        
        # 生成推荐（最多10个）
        for i, (distance, charger) in enumerate(charger_distances[:10]):
            # 根据电量和距离确定紧急程度
            urgency = 'low'
            if soc < 20:
                urgency = 'critical'
            elif soc < 40:
                urgency = 'high'
            elif soc < 60:
                urgency = 'medium'
            
            # 估算充电时间（简化计算）
            needed_charge = max(0, 80 - soc)  # 充到80%
            charging_time = (needed_charge * battery_capacity / 100) / (charger.get('max_power', 50) / 60)
            
            recommendations.append(ChargingStopRecommendation(
                station_id=charger.get('station_id', f'station_{i}'),
                name=f"充电站 {charger.get('station_id', i+1)}",
                lat=charger.get('position', {}).get('lat', 0),
                lng=charger.get('position', {}).get('lng', 0),
                distance_from_route=distance,
                detour_distance=distance * 0.1,  # 简化计算
                estimated_charging_time=int(charging_time),
                estimated_cost=charging_time * 1.5,  # 简化计算
                urgency_level=urgency,
                max_power=charger.get('max_power', 50),
                available_chargers=1 if charger.get('status') == 'available' else 0,
                rating=4.0 + random.random(),  # 模拟评分
                current_price=1.5,  # 添加当前价格
                recommended_soc=80.0  # 添加推荐SOC
            ))
        
        return recommendations
    
    def _generateOptimizations(self, user_data, chargers_data):
        """生成路线优化建议"""
        from trip_planning_module import RouteOptimization
        
        optimizations = []
        soc = user_data.get('soc', 0)
        status = user_data.get('status', 'idle')
        
        # 根据用户状态生成不同的优化建议
        if soc < 30:
            optimizations.append(RouteOptimization(
                optimization_type='immediate_charging',
                description='电量较低，建议立即充电',
                potential_savings={'time_minutes': -10, 'cost_yuan': 0},
                alternative_route=[],
                confidence=0.9
            ))
        
        if status == 'traveling' and user_data.get('target_charger'):
            optimizations.append(RouteOptimization(
                optimization_type='route_efficiency',
                description='当前路线较优，建议继续前往目标充电站',
                potential_savings={'time_minutes': 0, 'cost_yuan': 0},
                alternative_route=[],
                confidence=0.8
            ))
        
        if soc > 70:
            optimizations.append(RouteOptimization(
                optimization_type='delay_charging',
                description='电量充足，可以延后充电以获得更好的价格',
                potential_savings={'time_minutes': 15, 'cost_yuan': 5.0},
                alternative_route=[],
                confidence=0.7
            ))
        
        return optimizations
    
    def _calculateTripStatistics(self, start_pos, destination, soc, battery_capacity, current_time):
        """计算行程统计信息"""
        from simulation.utils import calculate_distance
        
        # 计算距离
        if start_pos and destination:
            total_distance = calculate_distance(start_pos, destination)
        else:
            total_distance = 0
        
        # 估算时间（假设平均速度50km/h）
        estimated_time = total_distance / 50 * 60  # 分钟
        
        # 估算到达时间
        estimated_arrival = None
        if current_time and estimated_time > 0:
            estimated_arrival = current_time + timedelta(minutes=estimated_time)
        
        return {
            'total_distance_km': total_distance,
            'estimated_time_minutes': estimated_time,
            'estimated_arrival': estimated_arrival,
            'current_soc': soc,
            'battery_capacity': battery_capacity,
            'remaining_range_km': (soc / 100) * battery_capacity * 5  # 简化计算，假设1kWh=5km
        }
    
    def _updateStatusLabels(self, trip_data: Dict):
        """更新状态标签"""
        stats = trip_data['statistics']
        user_data = trip_data['user_data']
        current_time = trip_data['current_time']
        
        # 目的地信息
        destination = user_data.get('destination', {})
        if destination:
            dest_name = f"({destination.get('lat', 0):.3f}, {destination.get('lng', 0):.3f})"
        else:
            dest_name = "未设置"
        self.destination_label.setText(f"目的地: {dest_name}")
        
        # 预计到达时间
        if stats.get('estimated_arrival'):
            eta_str = stats['estimated_arrival'].strftime("%H:%M")
            self.eta_label.setText(f"预计到达: {eta_str}")
        else:
            self.eta_label.setText("预计到达: --")
        
        # 距离和时间
        self.remaining_distance_label.setText(f"剩余距离: {stats['total_distance_km']:.1f}km")
        self.remaining_time_label.setText(f"剩余时间: {stats['estimated_time_minutes']:.0f}分钟")
        
        # 当前速度（从用户数据获取）
        travel_speed = user_data.get('travel_speed', 0)
        self.current_speed_label.setText(f"当前速度: {travel_speed:.0f}km/h")
        
        # 电池状态
        soc = stats['current_soc']
        remaining_range = stats['remaining_range_km']
        self.battery_status_label.setText(f"电池状态: {soc:.1f}% ({remaining_range:.0f}km)")
    
    def _showDefaultInfo(self):
        """显示默认信息"""
        self.destination_label.setText("目的地: 请选择用户")
        self.eta_label.setText("预计到达: --")
        self.remaining_distance_label.setText("剩余距离: --")
        self.remaining_time_label.setText("剩余时间: --")
        self.current_speed_label.setText("当前速度: --")
        self.battery_status_label.setText("电池状态: --")
        
        # 清空其他组件
        self.route_viz.updateRoute([])
        self.charging_recommendations.updateRecommendations([])
        self.route_optimizations.updateOptimizations([])
    
    def _showUserNotFound(self):
        """显示用户未找到信息"""
        self.destination_label.setText("目的地: 用户未找到")
        self.eta_label.setText("预计到达: --")
        self.remaining_distance_label.setText("剩余距离: --")
        self.remaining_time_label.setText("剩余时间: --")
        self.current_speed_label.setText("当前速度: --")
        self.battery_status_label.setText("电池状态: --")
    
    def _showErrorInfo(self, error_msg):
        """显示错误信息"""
        self.destination_label.setText(f"错误: {error_msg}")
        self.eta_label.setText("预计到达: --")
        self.remaining_distance_label.setText("剩余距离: --")
        self.remaining_time_label.setText("剩余时间: --")
        self.current_speed_label.setText("当前速度: --")
        self.battery_status_label.setText("电池状态: --")
    
    def onChargingStationSelected(self, station_id: str):
        """充电站被选中"""
        logger.info(f"选中充电站: {station_id}")
        
        # 使用信号机制触发充电决策
        if self.selected_user_id:
            # 创建充电参数
            charging_params = {
                'target_soc': 80,
                'charging_type': '快充'
            }
            
            # 发射充电决策信号
            self.chargingDecisionMade.emit(self.selected_user_id, station_id, charging_params)
            logger.info(f"已为用户 {self.selected_user_id} 发射充电决策信号，目标充电站: {station_id}")
            
            QMessageBox.information(self, "路线规划", 
                f"已为用户规划到充电站 {station_id} 的路线\n"
                f"用户将在下一个仿真步骤开始前往该充电站")
        else:
            QMessageBox.warning(self, "路线规划失败", "请先选择一个用户")
            logger.warning("尝试选择充电站但未选中用户")
    
    def onOptimizationSelected(self, optimization_type: str):
        """优化方案被选中"""
        logger.info(f"选中优化方案: {optimization_type}")
        QMessageBox.information(self, "路线优化", f"已选择{optimization_type}优化方案\n正在重新规划路线...")
    
    def startNavigation(self):
        """开始导航"""
        logger.info("开始导航")
        self.start_navigation_btn.setEnabled(False)
        self.stop_navigation_btn.setEnabled(True)
        QMessageBox.information(self, "导航", "导航已开始！")
    
    def stopNavigation(self):
        """停止导航"""
        logger.info("停止导航")
        self.start_navigation_btn.setEnabled(True)
        self.stop_navigation_btn.setEnabled(False)
        QMessageBox.information(self, "导航", "导航已停止！")
    
    def refreshTripData(self):
        """刷新行程数据"""
        logger.info("刷新行程数据")
        self.updateTripInfo()
        QMessageBox.information(self, "刷新", "行程数据已刷新！")