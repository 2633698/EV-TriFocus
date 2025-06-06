#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
高级图表组件
提供各种专业的数据可视化组件
"""

import sys
from typing import Dict, List, Optional, Any, Tuple
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, 
    QComboBox, QPushButton, QGroupBox, QScrollArea, QFrame,
    QSlider, QCheckBox, QSpinBox, QTabWidget, QSplitter,
    QTableWidget, QTableWidgetItem, QHeaderView, QProgressBar
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread, QPointF
from PyQt6.QtGui import (
    QFont, QPainter, QPen, QBrush, QColor, QLinearGradient,
    QRadialGradient, QPalette, QPolygonF
)

try:
    import pyqtgraph as pg
    from pyqtgraph import PlotWidget, GraphicsLayoutWidget
    HAS_PYQTGRAPH = True
except ImportError:
    HAS_PYQTGRAPH = False


class RegionalLoadHeatmap(QWidget):
    """区域负载显示"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_loads = {}  # 当前各区域负载
        self.region_widgets = {}  # 区域显示组件
        
        self.setupUI()
        
    def setupUI(self):
        layout = QVBoxLayout(self)
        
        # 标题
        title = QLabel("区域负载状态")
        title.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        
        # 区域显示容器
        self.regions_container = QHBoxLayout()
        self.regions_container.setSpacing(20)
        layout.addLayout(self.regions_container)
        
        # 添加说明
        legend_layout = QHBoxLayout()
        legend_layout.addStretch()
        
        legend_label = QLabel("负载水平: ")
        legend_layout.addWidget(legend_label)
        
        # 颜色图例
        colors = [("低", "#90EE90"), ("中", "#FFD700"), ("高", "#FF6B6B")]
        for level, color in colors:
            color_box = QLabel()
            color_box.setFixedSize(20, 20)
            color_box.setStyleSheet(f"background-color: {color}; border: 1px solid #ccc;")
            legend_layout.addWidget(color_box)
            legend_layout.addWidget(QLabel(level))
            legend_layout.addSpacing(10)
        
        legend_layout.addStretch()
        layout.addLayout(legend_layout)
        
        layout.addStretch()
    
    def updateData(self, grid_status):
        """更新区域负载显示"""
        if not grid_status or 'regional_current_state' not in grid_status:
            return
        
        regional_data = grid_status['regional_current_state']
        
        # 更新当前负载数据
        for region_id, data in regional_data.items():
            current_load = data.get('current_total_load', 0)
            # 使用系统容量而不是基础负载来计算负载率，与数据详情页保持一致
            system_capacity = data.get('system_capacity', 80000)  # 默认系统容量
            
            # 计算负载率 - 与grid_model_enhanced.py中的计算方式一致
            load_rate = data.get('grid_load_percentage', 0)
            self.current_loads[region_id] = {
                'load': current_load,
                'rate': load_rate,
                'base': system_capacity
            }
        
        self._updateDisplay()
    
    def _updateDisplay(self):
        """更新显示"""
        # 清除现有区域显示
        for i in reversed(range(self.regions_container.count())):
            child = self.regions_container.takeAt(i)
            if child.widget():
                child.widget().deleteLater()
        
        # 创建新的区域显示
        for region_id, load_data in self.current_loads.items():
            region_widget = self._createRegionWidget(region_id, load_data)
            self.regions_container.addWidget(region_widget)
    
    def _createRegionWidget(self, region_id, load_data):
        """创建区域显示组件"""
        widget = QFrame()
        widget.setFrameStyle(QFrame.Shape.Box)
        widget.setFixedSize(120, 100)
        
        layout = QVBoxLayout(widget)
        
        # 区域名称
        name_label = QLabel(region_id)
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        layout.addWidget(name_label)
        
        # 负载值
        load_value = load_data['load'] / 1000  # 转换为MW
        load_label = QLabel(f"{load_value:.1f} MW")
        load_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(load_label)
        
        # 负载率
        rate = load_data['rate']
        rate_label = QLabel(f"{rate:.1f}%")
        rate_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(rate_label)
        
        # 根据负载率设置背景颜色
        if rate > 80:
            color = "#FF6B6B"  # 红色
        elif rate > 60:
            color = "#FFD700"  # 黄色
        else:
            color = "#90EE90"  # 绿色
        
        widget.setStyleSheet(f"QFrame {{ background-color: {color}; border-radius: 5px; }}")
        
        return widget
    



class MultiMetricsChart(QWidget):
    """多指标对比图表"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.metrics_data = {}
        self.plot_items = {}
        
        self.setupUI()
    
    def setupUI(self):
        layout = QVBoxLayout(self)
        
        # 控制面板
        control_panel = QGroupBox("图表控制")
        control_layout = QHBoxLayout(control_panel)
        
        # 指标选择
        self.metrics_checkboxes = {}
        metrics = ["用户满意度", "运营商利润", "电网友好度", "综合评分"]
        
        for metric in metrics:
            checkbox = QCheckBox(metric)
            checkbox.setChecked(True)
            checkbox.stateChanged.connect(self.updateChart)
            self.metrics_checkboxes[metric] = checkbox
            control_layout.addWidget(checkbox)
        
        control_layout.addStretch()
        
        # Y轴范围控制
        control_layout.addWidget(QLabel("Y轴范围:"))
        self.y_min_spin = QSpinBox()
        self.y_min_spin.setRange(-100, 100)
        self.y_min_spin.setValue(-1)
        self.y_min_spin.valueChanged.connect(self.updateChart)
        control_layout.addWidget(self.y_min_spin)
        
        control_layout.addWidget(QLabel("到"))
        self.y_max_spin = QSpinBox()
        self.y_max_spin.setRange(-100, 100)
        self.y_max_spin.setValue(1)
        self.y_max_spin.valueChanged.connect(self.updateChart)
        control_layout.addWidget(self.y_max_spin)
        
        layout.addWidget(control_panel)
        
        if HAS_PYQTGRAPH:
            # 创建图表
            self.plot_widget = PlotWidget()
            self.plot_widget.setBackground('w')
            self.plot_widget.setLabel('left', '指标值')
            self.plot_widget.setLabel('bottom', '时间')
            self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
            self.plot_widget.addLegend()
            
            layout.addWidget(self.plot_widget)
        else:
            # 简单显示
            self.text_display = QLabel("需要pyqtgraph库支持图表显示")
            layout.addWidget(self.text_display)
    
    def updateData(self, metrics_history):
        """更新指标数据"""
        if not metrics_history:
            return
        
        self.metrics_data = metrics_history
        self.updateChart()
    
    def updateChart(self):
        """更新图表显示"""
        if not HAS_PYQTGRAPH or not hasattr(self, 'plot_widget'):
            return
        
        self.plot_widget.clear()
        
        if not self.metrics_data or 'timestamps' not in self.metrics_data:
            return
        
        timestamps = self.metrics_data['timestamps']
        if not timestamps:
            return
        
        x_data = list(range(len(timestamps)))
        
        # 颜色方案
        colors = [
            (52, 152, 219),   # 蓝色 - 用户满意度
            (46, 204, 113),   # 绿色 - 运营商利润
            (241, 196, 15),   # 黄色 - 电网友好度
            (155, 89, 182)    # 紫色 - 综合评分
        ]
        
        metric_keys = {
            "用户满意度": "userSatisfaction",
            "运营商利润": "operatorProfit", 
            "电网友好度": "gridFriendliness",
            "综合评分": "totalReward"
        }
        
        for i, (metric_name, data_key) in enumerate(metric_keys.items()):
            checkbox = self.metrics_checkboxes.get(metric_name)
            if checkbox and checkbox.isChecked():
                y_data = self.metrics_data.get(data_key, [])
                if y_data and len(y_data) == len(x_data):
                    color = colors[i % len(colors)]
                    pen = pg.mkPen(color=color, width=2)
                    
                    self.plot_widget.plot(
                        x_data, y_data,
                        pen=pen,
                        name=metric_name,
                        symbolBrush=color,
                        symbolSize=6,
                        symbol='o'
                    )
        
        # 设置Y轴范围
        y_min = self.y_min_spin.value()
        y_max = self.y_max_spin.value()
        self.plot_widget.setYRange(y_min, y_max)


class RealTimeDataTable(QWidget):
    """实时数据表格"""
    # 添加更新信号
    updateRequested = pyqtSignal(dict)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_data = {}
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._processUpdate)
        self.update_timer.setInterval(500)  # 500ms更新一次
        self.pending_update = None
        self.max_display_rows = 100  # 限制显示行数
        
        self.setupUI()
    
    def setupUI(self):
        layout = QVBoxLayout(self)
        
        # 添加控制面板
        control_panel = self._createControlPanel()
        layout.addWidget(control_panel)
        
        # 创建选项卡
        self.tab_widget = QTabWidget()
        
        # 用户数据表
        self.users_table = self._createUsersTable()
        self.tab_widget.addTab(self.users_table, "用户数据")
        
        # 充电桩数据表
        self.chargers_table = self._createChargersTable()
        self.tab_widget.addTab(self.chargers_table, "充电桩数据")
        
        # 区域数据表
        self.regions_table = self._createRegionsTable()
        self.tab_widget.addTab(self.regions_table, "区域数据")
        
        layout.addWidget(self.tab_widget)
    
    def _createUsersTable(self):
        """创建用户数据表"""
        table = QTableWidget()
        
        headers = [
            "用户ID", "状态", "电量(%)", "位置", "目标充电桩", 
            "等待时间", "充电时间", "费用"
        ]
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        
        # 设置表格属性
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setSortingEnabled(True)
        
        # 自适应列宽
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        
        return table
    
    def _createChargersTable(self):
        """创建充电桩数据表"""
        table = QTableWidget()
        
        headers = [
            "充电桩ID", "状态", "位置", "类型", "功率(kW)", 
            "当前用户", "队列长度", "利用率(%)", "今日收入"
        ]
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setSortingEnabled(True)
        
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        
        return table
    
    def _createRegionsTable(self):
        """创建区域数据表"""
        table = QTableWidget()
        
        headers = [
            "区域ID", "总负载(MW)", "基础负载(MW)", "充电负载(MW)", 
            "太阳能(MW)", "风能(MW)", "可再生比例(%)", "负载率(%)", "碳强度"
        ]
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setSortingEnabled(True)
        
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        
        return table

    def _createControlPanel(self):
        """创建控制面板"""
        panel = QGroupBox("显示控制")
        layout = QHBoxLayout(panel)
        
        # 自动更新开关
        self.auto_update_cb = QCheckBox("自动更新")
        self.auto_update_cb.setChecked(True)
        self.auto_update_cb.stateChanged.connect(self._toggleAutoUpdate)
        layout.addWidget(self.auto_update_cb)
        
        # 显示行数限制
        layout.addWidget(QLabel("最大行数:"))
        self.row_limit_spin = QSpinBox()
        self.row_limit_spin.setRange(10, 1000)
        self.row_limit_spin.setValue(100)
        self.row_limit_spin.valueChanged.connect(self._updateRowLimit)
        layout.addWidget(self.row_limit_spin)
        
        # 筛选条件
        layout.addWidget(QLabel("筛选:"))
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["全部", "充电中", "等待中", "行驶中", "空闲"])
        self.filter_combo.currentTextChanged.connect(self._applyFilter)
        layout.addWidget(self.filter_combo)
        
        layout.addStretch()
        
        # 手动刷新按钮
        self.refresh_button = QPushButton("刷新")
        self.refresh_button.clicked.connect(self._manualRefresh)
        layout.addWidget(self.refresh_button)
        
        return panel

    def _toggleAutoUpdate(self, checked):
        """切换自动更新"""
        if checked:
            self.update_timer.start()
        else:
            self.update_timer.stop()
    
    def _updateRowLimit(self, value):
        """更新行数限制"""
        self.max_display_rows = value
        if self.pending_update:
            self._processUpdate()
    
    def _applyFilter(self, filter_text):
        """应用筛选"""
        if self.pending_update:
            self._processUpdate()
    
    def _manualRefresh(self):
        """手动刷新"""
        if self.pending_update:
            self._processUpdate()
    def updateData(self, state_data):
        """更新数据 - 不直接更新表格，而是存储待更新数据"""
        if not state_data:
            return
        
        # 存储待更新数据
        self.pending_update = state_data
        
        # 如果定时器没有运行且启用了自动更新，立即处理一次
        if not self.update_timer.isActive() and self.auto_update_cb.isChecked():
            self.update_timer.start()
    
    def _processUpdate(self):
        """处理更新 - 在定时器触发时执行"""
        if not self.pending_update:
            return
        
        # 获取当前选中的标签页
        current_tab = self.tab_widget.currentIndex()
        
        # 只更新当前可见的表格
        if current_tab == 0:  # 用户数据
            self._updateUsersTableOptimized(self.pending_update.get('users', []))
        elif current_tab == 1:  # 充电桩数据
            self._updateChargersTableOptimized(self.pending_update.get('chargers', []))
        elif current_tab == 2:  # 区域数据
            self._updateRegionsTableOptimized(self.pending_update.get('grid_status', {}))
        
        # 清除待更新数据
        self.pending_update = None
    def _updateUsersTableOptimized(self, users_data):
        """优化的用户表更新"""
        table = self.users_table
        
        # 应用筛选
        filter_text = self.filter_combo.currentText()
        if filter_text != "全部":
            status_map = {
                "充电中": "charging",
                "等待中": "waiting",
                "行驶中": "traveling",
                "空闲": "idle"
            }
            filter_status = status_map.get(filter_text, "")
            users_data = [u for u in users_data if u.get('status') == filter_status]
        
        # 限制显示行数
        display_data = users_data[:self.max_display_rows]
        
        # 暂时禁用排序和更新
        table.setSortingEnabled(False)
        table.setUpdatesEnabled(False)
        
        try:
            # 设置行数
            table.setRowCount(len(display_data))
            
            # 批量更新数据
            for row, user in enumerate(display_data):
                # 用户ID
                if not table.item(row, 0):
                    table.setItem(row, 0, QTableWidgetItem())
                table.item(row, 0).setText(user.get('user_id', ''))
                
                # 状态
                status = user.get('status', 'unknown')
                if not table.item(row, 1):
                    table.setItem(row, 1, QTableWidgetItem())
                status_item = table.item(row, 1)
                status_item.setText(self._getStatusText(status))
                status_item.setBackground(self._getStatusColor(status))
                
                # 电量
                soc = user.get('soc', 0)
                if not table.item(row, 2):
                    table.setItem(row, 2, QTableWidgetItem())
                soc_item = table.item(row, 2)
                soc_item.setText(f"{soc:.1f}")
                if soc < 20:
                    soc_item.setBackground(QColor(255, 220, 220))
                elif soc < 50:
                    soc_item.setBackground(QColor(255, 255, 220))
                else:
                    soc_item.setBackground(QColor(240, 255, 240))
                
                # 位置（简化显示）
                if not table.item(row, 3):
                    table.setItem(row, 3, QTableWidgetItem())
                pos = user.get('current_position', {})
                table.item(row, 3).setText(f"({pos.get('lat', 0):.2f}, {pos.get('lng', 0):.2f})")
                
                # 目标充电桩
                if not table.item(row, 4):
                    table.setItem(row, 4, QTableWidgetItem())
                target = user.get('target_charger', '')
                table.item(row, 4).setText(target if target else '-')
                
                # 等待时间
                if not table.item(row, 5):
                    table.setItem(row, 5, QTableWidgetItem())
                # 计算等待时间
                wait_time = 0
                if status == 'waiting' and 'arrival_time_at_charger' in user:
                    # 简化计算：根据队列长度估算等待时间
                    queue_length = user.get('queue_position', 0)
                    wait_time = queue_length * 15  # 每个用户平均15分钟
                elif 'wait_time' in user:
                    wait_time = user['wait_time']
                table.item(row, 5).setText(f"{wait_time:.1f}分钟" if wait_time > 0 else '-')
                
                # 充电时间
                if not table.item(row, 6):
                    table.setItem(row, 6, QTableWidgetItem())
                # 计算充电时间
                charge_time = 0
                if status == 'charging':
                    # 根据SOC和目标SOC计算充电时间
                    current_soc = user.get('soc', 0)
                    target_soc = user.get('target_soc', 80)
                    battery_capacity = user.get('battery_capacity', 60)  # 默认60kWh
                    charging_power = user.get('charging_power', 30)  # 默认30kW
                    if charging_power > 0:
                        energy_needed = (target_soc - current_soc) / 100 * battery_capacity
                        charge_time = energy_needed / charging_power * 60  # 转换为分钟
                elif 'charge_time' in user:
                    charge_time = user['charge_time']
                table.item(row, 6).setText(f"{charge_time:.1f}分钟" if charge_time > 0 else '-')
                
                # 费用
                if not table.item(row, 7):
                    table.setItem(row, 7, QTableWidgetItem())
                # 计算费用
                current_soc = user.get('soc', 0)
                initial_soc = user.get('initial_soc')
                if initial_soc is None:
                    initial_soc = max(0, current_soc - 20)  # 估算初始SOC，确保不为负
                battery_capacity = user.get('battery_capacity', 60)
                energy_charged = (current_soc - initial_soc) / 100 * battery_capacity
                price_per_kwh = user.get('price_per_kwh', 1.2)  # 默认1.2元/kWh
                cost = energy_charged * price_per_kwh
                table.item(row, 7).setText(f"¥{cost:.2f}" if cost > 0 else '-')
            
            # 显示总数信息
                if len(users_data) > len(display_data):
                    # 记录显示的数据统计信息
                    pass
                
        finally:
            # 重新启用排序和更新
            table.setUpdatesEnabled(True)
            table.setSortingEnabled(True)
    def _updateChargersTableOptimized(self, chargers_data):
            """优化的充电桩表更新"""
            table = self.chargers_table
            
            # 限制显示行数
            display_data = chargers_data[:self.max_display_rows]
            
            # 暂时禁用更新
            table.setSortingEnabled(False)
            table.setUpdatesEnabled(False)
            
            try:
                table.setRowCount(len(display_data))
                
                for row, charger in enumerate(display_data):
                    # 充电桩ID
                    if not table.item(row, 0):
                        table.setItem(row, 0, QTableWidgetItem())
                    table.item(row, 0).setText(charger.get('charger_id', ''))
                    
                    # 状态
                    status = charger.get('status', 'unknown')
                    if not table.item(row, 1):
                        table.setItem(row, 1, QTableWidgetItem())
                    status_item = table.item(row, 1)
                    status_item.setText(self._getChargerStatusText(status))
                    status_item.setBackground(self._getChargerStatusColor(status))
                    
                    # 其他列快速更新
                    for col, key in enumerate(['position', 'type', 'max_power', 'current_user', 
                                            'queue', 'utilization_rate', 'daily_revenue'], start=2):
                        if not table.item(row, col):
                            table.setItem(row, col, QTableWidgetItem())
                        
                        if key == 'position':
                            pos = charger.get(key, {})
                            text = f"({pos.get('lat', 0):.2f}, {pos.get('lng', 0):.2f})"
                        elif key == 'queue':
                            text = str(len(charger.get(key, [])))
                        elif key == 'max_power':
                            text = f"{charger.get(key, 0):.1f}"
                        elif key == 'utilization_rate':
                            util_rate = charger.get(key, 0)
                            if util_rate == 0:
                                # 计算利用率：当前用户存在时为100%，否则为0%
                                util_rate = 100.0 if charger.get('current_user') else 0.0
                            text = f"{util_rate:.1f}%"
                        elif key == 'daily_revenue':
                            text = f"¥{charger.get(key, 0):.2f}"
                        else:
                            text = str(charger.get(key, ''))
                        
                        table.item(row, col).setText(text)
                        
            finally:
                table.setUpdatesEnabled(True)
                table.setSortingEnabled(True)
    def _updateRegionsTableOptimized(self, grid_status):
            """优化的区域表更新"""
            regional_data = grid_status.get('regional_current_state', {})
            table = self.regions_table
            
            table.setSortingEnabled(False)
            table.setUpdatesEnabled(False)
            
            try:
                table.setRowCount(len(regional_data))
                
                for row, (region_id, data) in enumerate(regional_data.items()):
                    # 创建或更新单元格
                    for col in range(9):
                        if not table.item(row, col):
                            table.setItem(row, col, QTableWidgetItem())
                    
                    # 批量设置数据
                    table.item(row, 0).setText(region_id)
                    table.item(row, 1).setText(f"{data.get('current_total_load', 0) / 1000:.2f}")
                    table.item(row, 2).setText(f"{data.get('current_base_load', 0) / 1000:.2f}")
                    table.item(row, 3).setText(f"{data.get('current_ev_load', 0) / 1000:.2f}")
                    table.item(row, 4).setText(f"{data.get('current_solar_gen', 0) / 1000:.2f}")
                    table.item(row, 5).setText(f"{data.get('current_wind_gen', 0) / 1000:.2f}")
                    table.item(row, 6).setText(f"{data.get('renewable_ratio', 0):.1f}")
                    
                    # 负载率着色
                    load_percentage = data.get('grid_load_percentage', 0)
                    load_item = table.item(row, 7)
                    load_item.setText(f"{load_percentage:.1f}")
                    if load_percentage > 90:
                        load_item.setBackground(QColor(255, 220, 220))
                    elif load_percentage > 70:
                        load_item.setBackground(QColor(255, 255, 220))
                    else:
                        load_item.setBackground(QColor(240, 255, 240))
                    
                    table.item(row, 8).setText(f"{data.get('carbon_intensity', 0):.1f}")
                    
            finally:
                table.setUpdatesEnabled(True)
                table.setSortingEnabled(True)
    def _getStatusText(self, status):
        """获取用户状态文本"""
        status_map = {
            'idle': '空闲',
            'traveling': '行驶中',
            'waiting': '等待中',
            'charging': '充电中',
            'post_charge': '充电后'
        }
        return status_map.get(status, status)
    
    def _getStatusColor(self, status):
        """获取状态颜色"""
        color_map = {
            'idle': QColor(240, 240, 240),
            'traveling': QColor(220, 240, 255),
            'waiting': QColor(255, 245, 220),
            'charging': QColor(220, 255, 220),
            'post_charge': QColor(245, 245, 255)
        }
        return color_map.get(status, QColor(255, 255, 255))
    
    def _getChargerStatusText(self, status):
        """获取充电桩状态文本"""
        status_map = {
            'available': '可用',
            'occupied': '占用中',
            'failure': '故障',
            'maintenance': '维护中'
        }
        return status_map.get(status, status)
    
    def _getChargerStatusColor(self, status):
        """获取充电桩状态颜色"""
        color_map = {
            'available': QColor(220, 255, 220),
            'occupied': QColor(255, 245, 220),
            'failure': QColor(255, 220, 220),
            'maintenance': QColor(240, 240, 240)
        }
        return color_map.get(status, QColor(255, 255, 255))


class StatisticsPanel(QWidget):
    """统计面板"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUI()
    
    def setupUI(self):
        layout = QVBoxLayout(self)
        
        # 创建统计卡片网格
        grid_layout = QGridLayout()
        
        # 用户统计
        self.user_stats = self._createStatsGroup("用户统计", [
            "总用户数", "活跃用户", "充电用户", "等待用户", "平均SOC"
        ])
        grid_layout.addWidget(self.user_stats, 0, 0)
        
        # 充电桩统计
        self.charger_stats = self._createStatsGroup("充电桩统计", [
            "总充电桩", "可用充电桩", "占用充电桩", "故障充电桩", "平均利用率"
        ])
        grid_layout.addWidget(self.charger_stats, 0, 1)
        
        # 电网统计
        self.grid_stats = self._createStatsGroup("电网统计", [
            "总负载", "充电负载", "负载率", "可再生比例", "碳强度"
        ])
        grid_layout.addWidget(self.grid_stats, 1, 0)
        
        # 经济统计
        self.economic_stats = self._createStatsGroup("经济统计", [
            "总收入", "平均电价", "用户成本", "运营利润", "效率指标"
        ])
        grid_layout.addWidget(self.economic_stats, 1, 1)
        
        layout.addLayout(grid_layout)
        layout.addStretch()
    
    def _createStatsGroup(self, title, metrics):
        """创建统计组"""
        group = QGroupBox(title)
        layout = QVBoxLayout(group)
        
        stats_dict = {}
        for metric in metrics:
            metric_layout = QHBoxLayout()
            
            label = QLabel(f"{metric}:")
            label.setMinimumWidth(80)
            metric_layout.addWidget(label)
            
            value_label = QLabel("0")
            value_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
            value_label.setStyleSheet("color: #2c3e50;")
            metric_layout.addWidget(value_label)
            
            metric_layout.addStretch()
            
            layout.addLayout(metric_layout)
            stats_dict[metric] = value_label
        
        # 存储标签引用
        setattr(self, f"{title.replace('统计', '_labels')}", stats_dict)
        
        return group
    
    def updateStatistics(self, state_data):
        """更新统计数据"""
        if not state_data:
            return
        
        # 更新用户统计
        self._updateUserStats(state_data.get('users', []))
        
        # 更新充电桩统计
        self._updateChargerStats(state_data.get('chargers', []))
        
        # 更新电网统计
        self._updateGridStats(state_data.get('grid_status', {}))
        
        # 更新经济统计
        self._updateEconomicStats(state_data)
    
    def _updateUserStats(self, users_data):
        """更新用户统计"""
        if not hasattr(self, '用户_labels'):
            return
        
        labels = self.用户_labels
        
        total_users = len(users_data)
        charging_users = sum(1 for u in users_data if u.get('status') == 'charging')
        waiting_users = sum(1 for u in users_data if u.get('status') == 'waiting')
        active_users = sum(1 for u in users_data if u.get('status') in ['charging', 'waiting', 'traveling'])
        
        avg_soc = np.mean([u.get('soc', 0) for u in users_data]) if users_data else 0
        
        labels["总用户数"].setText(str(total_users))
        labels["活跃用户"].setText(str(active_users))
        labels["充电用户"].setText(str(charging_users))
        labels["等待用户"].setText(str(waiting_users))
        labels["平均SOC"].setText(f"{avg_soc:.1f}%")
    
    def _updateChargerStats(self, chargers_data):
        """更新充电桩统计"""
        if not hasattr(self, '充电桩_labels'):
            return
        
        labels = self.充电桩_labels
        
        total_chargers = len(chargers_data)
        available_chargers = sum(1 for c in chargers_data if c.get('status') == 'available')
        occupied_chargers = sum(1 for c in chargers_data if c.get('status') == 'occupied')
        failed_chargers = sum(1 for c in chargers_data if c.get('status') == 'failure')
        
        utilization_rates = [c.get('utilization_rate', 0) for c in chargers_data]
        avg_utilization = np.mean(utilization_rates) if utilization_rates else 0
        
        labels["总充电桩"].setText(str(total_chargers))
        labels["可用充电桩"].setText(str(available_chargers))
        labels["占用充电桩"].setText(str(occupied_chargers))
        labels["故障充电桩"].setText(str(failed_chargers))
        labels["平均利用率"].setText(f"{avg_utilization:.1f}%")
    
    def _updateGridStats(self, grid_status):
        """更新电网统计"""
        if not hasattr(self, '电网_labels'):
            return
        
        labels = self.电网_labels
        aggregated = grid_status.get('aggregated_metrics', {})
        
        total_load = aggregated.get('total_load', 0) / 1000  # 转换为MW
        ev_load = aggregated.get('total_ev_load', 0) / 1000
        load_percentage = aggregated.get('overall_load_percentage', 0)
        renewable_ratio = aggregated.get('weighted_renewable_ratio', 0)
        carbon_intensity = aggregated.get('weighted_carbon_intensity', 0)
        
        labels["总负载"].setText(f"{total_load:.1f} MW")
        labels["充电负载"].setText(f"{ev_load:.1f} MW")
        labels["负载率"].setText(f"{load_percentage:.1f}%")
        labels["可再生比例"].setText(f"{renewable_ratio:.1f}%")
        labels["碳强度"].setText(f"{carbon_intensity:.1f}")
    
    def _updateEconomicStats(self, state_data):
        """更新经济统计"""
        if not hasattr(self, '经济_labels'):
            return
        
        labels = self.经济_labels
        chargers_data = state_data.get('chargers', [])
        grid_status = state_data.get('grid_status', {})
        
        total_revenue = sum(c.get('daily_revenue', 0) for c in chargers_data)
        current_price = grid_status.get('current_price', 0)
        
        # 计算用户平均成本（简化）
        users_data = state_data.get('users', [])
        user_costs = [u.get('total_cost', 0) for u in users_data if u.get('total_cost', 0) > 0]
        avg_user_cost = np.mean(user_costs) if user_costs else 0
        
        # 运营利润（简化计算）
        total_energy = sum(c.get('daily_energy', 0) for c in chargers_data)
        operation_profit = total_revenue - (total_energy * current_price * 0.8)  # 假设80%的电价成本
        
        # 效率指标（简化）
        efficiency = (total_revenue / max(1, total_energy)) if total_energy > 0 else 0
        
        labels["总收入"].setText(f"¥{total_revenue:.2f}")
        labels["平均电价"].setText(f"¥{current_price:.2f}/kWh")
        labels["用户成本"].setText(f"¥{avg_user_cost:.2f}")
        labels["运营利润"].setText(f"¥{operation_profit:.2f}")
        labels["效率指标"].setText(f"{efficiency:.2f}")


# 导出所有组件
__all__ = [
    'RegionalLoadHeatmap',
    'MultiMetricsChart', 
    'RealTimeDataTable',
    'StatisticsPanel'
]
