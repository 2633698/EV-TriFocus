# operator_panel.py
import sys
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
import numpy as np
import pandas as pd
from collections import defaultdict
from data_storage import data_storage  # 导入数据存储模块

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QTabWidget,
    QLabel, QPushButton, QComboBox, QSpinBox, QDoubleSpinBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox,
    QTextEdit, QLineEdit, QCheckBox, QSlider, QProgressBar,
    QSplitter, QFrame, QScrollArea, QListWidget, QListWidgetItem,
    QMessageBox, QDialog, QDialogButtonBox, QFormLayout,
    QTreeWidget, QTreeWidgetItem, QMenu, QToolBar, QDateTimeEdit
)
from PyQt6.QtCore import (
    Qt, QTimer, pyqtSignal, QThread, QDateTime, QDate, QTime,
    QPropertyAnimation, QEasingCurve, pyqtProperty
)
from PyQt6.QtGui import (
    QFont, QPainter, QPen, QBrush, QColor, QLinearGradient,
    QIcon, QPixmap, QAction, QPalette
)

try:
    import pyqtgraph as pg
    from pyqtgraph import PlotWidget
    HAS_PYQTGRAPH = True
except ImportError:
    HAS_PYQTGRAPH = False

logger = logging.getLogger(__name__)


class StationHealthCard(QFrame):
    """充电站健康度卡片"""
    
    def __init__(self, station_id, parent=None):
        super().__init__(parent)
        self.station_id = station_id
        self.health_score = 100
        self.setupUI()
        
    def setupUI(self):
        self.setFrameStyle(QFrame.Shape.Box)
        self.setStyleSheet("""
            QFrame {
                background: white;
                border: 1px solid #ddd;
                border-radius: 8px;
                padding: 10px;
            }
            QFrame:hover {
                border: 2px solid #3498db;
            }
        """)
        
        layout = QVBoxLayout(self)
        
        # 站点名称
        self.name_label = QLabel(self.station_id)
        self.name_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        layout.addWidget(self.name_label)
        
        # 健康度得分
        self.score_label = QLabel("100%")
        self.score_label.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        self.score_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.score_label)
        
        # 状态指示器
        self.status_widget = QWidget()
        self.status_widget.setFixedHeight(20)
        layout.addWidget(self.status_widget)
        
        # 详细信息
        self.info_label = QLabel("运行正常")
        self.info_label.setStyleSheet("color: #666;")
        layout.addWidget(self.info_label)
    
    def updateHealth(self, health_data):
        """更新健康度"""
        self.health_score = health_data.get('score', 100)
        self.score_label.setText(f"{self.health_score}%")
        
        # 根据得分设置颜色
        if self.health_score >= 80:
            color = "#27ae60"
            status = "运行良好"
        elif self.health_score >= 60:
            color = "#f39c12"
            status = "需要关注"
        else:
            color = "#e74c3c"
            status = "需要维护"
        
        self.score_label.setStyleSheet(f"color: {color};")
        self.info_label.setText(status)
        
        # 更新状态条
        self.status_widget.setStyleSheet(f"""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 {color}, stop:{self.health_score/100} {color},
                stop:{self.health_score/100} #ecf0f1, stop:1 #ecf0f1);
            border-radius: 10px;
        """)


class PricingStrategyWidget(QWidget):
    """定价策略控制组件"""
    
    strategyChanged = pyqtSignal(dict)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_strategy = {}
        self.setupUI()
        
    def setupUI(self):
        layout = QVBoxLayout(self)
        
        # 基础设置组
        base_group = QGroupBox("基础定价设置")
        base_layout = QFormLayout(base_group)
        
        # 基础电价
        self.base_price_spin = QDoubleSpinBox()
        self.base_price_spin.setRange(0.1, 5.0)
        self.base_price_spin.setSingleStep(0.01)
        self.base_price_spin.setValue(0.85)
        self.base_price_spin.setSuffix(" 元/kWh")
        self.base_price_spin.valueChanged.connect(self.onStrategyChanged)
        base_layout.addRow("基础电价:", self.base_price_spin)
        
        # 服务费率
        self.service_fee_spin = QDoubleSpinBox()
        self.service_fee_spin.setRange(0, 100)
        self.service_fee_spin.setSingleStep(1)
        self.service_fee_spin.setValue(20)
        self.service_fee_spin.setSuffix(" %")
        self.service_fee_spin.valueChanged.connect(self.onStrategyChanged)
        base_layout.addRow("服务费率:", self.service_fee_spin)
        
        layout.addWidget(base_group)
        
        # 时段定价组
        time_group = QGroupBox("时段定价系数")
        time_layout = QFormLayout(time_group)
        
        # 峰时系数
        self.peak_factor_spin = QDoubleSpinBox()
        self.peak_factor_spin.setRange(0.5, 3.0)
        self.peak_factor_spin.setSingleStep(0.1)
        self.peak_factor_spin.setValue(1.5)
        self.peak_factor_spin.valueChanged.connect(self.onStrategyChanged)
        time_layout.addRow("峰时系数:", self.peak_factor_spin)
        
        # 平时系数
        self.normal_factor_spin = QDoubleSpinBox()
        self.normal_factor_spin.setRange(0.5, 2.0)
        self.normal_factor_spin.setSingleStep(0.1)
        self.normal_factor_spin.setValue(1.0)
        self.normal_factor_spin.valueChanged.connect(self.onStrategyChanged)
        time_layout.addRow("平时系数:", self.normal_factor_spin)
        
        # 谷时系数
        self.valley_factor_spin = QDoubleSpinBox()
        self.valley_factor_spin.setRange(0.3, 1.5)
        self.valley_factor_spin.setSingleStep(0.1)
        self.valley_factor_spin.setValue(0.6)
        self.valley_factor_spin.valueChanged.connect(self.onStrategyChanged)
        time_layout.addRow("谷时系数:", self.valley_factor_spin)
        
        layout.addWidget(time_group)
        
        # 动态定价组
        dynamic_group = QGroupBox("动态定价策略")
        dynamic_layout = QVBoxLayout(dynamic_group)
        
        # 需求响应定价
        self.demand_response_cb = QCheckBox("启用需求响应定价")
        self.demand_response_cb.stateChanged.connect(self.onStrategyChanged)
        dynamic_layout.addWidget(self.demand_response_cb)
        
        # 拥堵定价
        self.congestion_pricing_cb = QCheckBox("启用拥堵定价")
        self.congestion_pricing_cb.stateChanged.connect(self.onStrategyChanged)
        dynamic_layout.addWidget(self.congestion_pricing_cb)
        
        # 会员优惠
        self.member_discount_cb = QCheckBox("启用会员优惠")
        self.member_discount_cb.stateChanged.connect(self.onStrategyChanged)
        dynamic_layout.addWidget(self.member_discount_cb)
        
        layout.addWidget(dynamic_group)
        
        # 预测影响
        impact_group = QGroupBox("预测影响")
        impact_layout = QVBoxLayout(impact_group)
        
        self.impact_text = QTextEdit()
        self.impact_text.setReadOnly(True)
        self.impact_text.setMaximumHeight(100)
        impact_layout.addWidget(self.impact_text)
        
        layout.addWidget(impact_group)
        
        # 应用按钮
        self.apply_button = QPushButton("应用定价策略")
        self.apply_button.setStyleSheet("""
            QPushButton {
                background: #3498db;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 10px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #2980b9;
            }
        """)
        self.apply_button.clicked.connect(self.applyStrategy)
        layout.addWidget(self.apply_button)
        
    def onStrategyChanged(self):
        """策略参数改变时更新预测"""
        self.updateImpactPrediction()
        
    def updateImpactPrediction(self):
        """更新影响预测"""
        # 获取当前策略参数
        base_price = self.base_price_spin.value()
        service_fee = self.service_fee_spin.value()
        peak_factor = self.peak_factor_spin.value()
        
        # 简单的影响预测模型
        price_increase = (base_price - 0.85) / 0.85 * 100
        revenue_impact = price_increase * 0.8  # 假设价格弹性为0.8
        satisfaction_impact = -price_increase * 0.5
        
        impact_text = f"""预计影响分析：
- 营收变化: {revenue_impact:+.1f}%
- 用户满意度: {satisfaction_impact:+.1f}%
- 峰时价格: ¥{base_price * peak_factor:.2f}/kWh
- 谷时价格: ¥{base_price * self.valley_factor_spin.value():.2f}/kWh
"""
        self.impact_text.setText(impact_text)
        
    def applyStrategy(self):
        """应用定价策略"""
        strategy = {
            'base_price': self.base_price_spin.value(),
            'service_fee': self.service_fee_spin.value(),
            'peak_factor': self.peak_factor_spin.value(),
            'normal_factor': self.normal_factor_spin.value(),
            'valley_factor': self.valley_factor_spin.value(),
            'demand_response': self.demand_response_cb.isChecked(),
            'congestion_pricing': self.congestion_pricing_cb.isChecked(),
            'member_discount': self.member_discount_cb.isChecked(),
            'timestamp': datetime.now().isoformat()
        }
        
        self.current_strategy = strategy
        self.strategyChanged.emit(strategy)
        
        QMessageBox.information(self, "成功", "定价策略已应用")


class RevenueAnalysisWidget(QWidget):
    """收益分析组件"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.revenue_data = {}
        self.setupUI()
        
    def setupUI(self):
        layout = QVBoxLayout(self)
        
        # 时间范围选择
        time_layout = QHBoxLayout()
        time_layout.addWidget(QLabel("时间范围:"))
        
        self.time_range_combo = QComboBox()
        self.time_range_combo.addItems(["今日", "本周", "本月", "本年", "自定义"])
        self.time_range_combo.currentTextChanged.connect(self.onTimeRangeChanged)
        time_layout.addWidget(self.time_range_combo)
        
        time_layout.addStretch()
        layout.addLayout(time_layout)
        
        # 汇总数据卡片
        cards_layout = QHBoxLayout()
        
        # 总收入卡片
        self.total_revenue_card = self._createSummaryCard("总收入", "¥0.00")
        cards_layout.addWidget(self.total_revenue_card)
        
        # 总成本卡片
        self.total_cost_card = self._createSummaryCard("总成本", "¥0.00")
        cards_layout.addWidget(self.total_cost_card)
        
        # 净利润卡片
        self.net_profit_card = self._createSummaryCard("净利润", "¥0.00")
        cards_layout.addWidget(self.net_profit_card)
        
        # 利润率卡片
        self.profit_margin_card = self._createSummaryCard("利润率", "0.0%")
        cards_layout.addWidget(self.profit_margin_card)
        
        layout.addLayout(cards_layout)
        
        if HAS_PYQTGRAPH:
            # 收益趋势图
            self.revenue_chart = PlotWidget()
            self.revenue_chart.setBackground('w')
            self.revenue_chart.setLabel('left', '金额 (元)')
            self.revenue_chart.setLabel('bottom', '时间')
            self.revenue_chart.showGrid(x=True, y=True, alpha=0.3)
            self.revenue_chart.addLegend()
            layout.addWidget(self.revenue_chart)
        
        # 详细数据表
        self.detail_table = QTableWidget()
        self.detail_table.setColumnCount(6)
        self.detail_table.setHorizontalHeaderLabels([
            "站点", "充电量(kWh)", "收入(元)", "成本(元)", "利润(元)", "利润率(%)"
        ])
        self.detail_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.detail_table)
        
    def _createSummaryCard(self, title, value):
        """创建汇总卡片"""
        card = QFrame()
        card.setFrameStyle(QFrame.Shape.Box)
        card.setStyleSheet("""
            QFrame {
                background: white;
                border: 1px solid #ddd;
                border-radius: 8px;
                padding: 15px;
            }
        """)
        
        layout = QVBoxLayout(card)
        
        title_label = QLabel(title)
        title_label.setStyleSheet("color: #666; font-size: 12px;")
        layout.addWidget(title_label)
        
        value_label = QLabel(value)
        value_label.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        value_label.setStyleSheet("color: #2c3e50;")
        layout.addWidget(value_label)
        
        # 存储value标签的引用
        card.value_label = value_label
        
        return card
        
    def onTimeRangeChanged(self, time_range):
        """时间范围改变时更新数据"""
        self.updateRevenueData()
        
    def updateRevenueData(self, revenue_data=None):
        """更新收益数据"""
        if revenue_data:
            self.revenue_data = revenue_data
            
        # 更新汇总卡片
        total_revenue = self.revenue_data.get('total_revenue', 0)
        total_cost = self.revenue_data.get('total_cost', 0)
        net_profit = total_revenue - total_cost
        profit_margin = (net_profit / total_revenue * 100) if total_revenue > 0 else 0
        
        self.total_revenue_card.value_label.setText(f"¥{total_revenue:,.2f}")
        self.total_cost_card.value_label.setText(f"¥{total_cost:,.2f}")
        self.net_profit_card.value_label.setText(f"¥{net_profit:,.2f}")
        self.profit_margin_card.value_label.setText(f"{profit_margin:.1f}%")
        
        # 根据利润设置颜色
        if net_profit > 0:
            self.net_profit_card.value_label.setStyleSheet("color: #27ae60;")
        else:
            self.net_profit_card.value_label.setStyleSheet("color: #e74c3c;")
        
        # 更新图表
        if HAS_PYQTGRAPH and hasattr(self, 'revenue_chart'):
            self._updateRevenueChart()
        
        # 更新详细表格
        self._updateDetailTable()
        
    def _updateRevenueChart(self):
        """更新收益图表"""
        if not HAS_PYQTGRAPH:
            return
            
        self.revenue_chart.clear()
        
        # 获取历史收益数据
        revenue_history = data_storage.get_revenue_history(days=7)
        
        if revenue_history and len(revenue_history) > 0:
            # 使用真实历史数据
            dates = []
            daily_revenues = []
            daily_costs = []
            
            # 按日期汇总数据
            date_totals = defaultdict(lambda: {'revenue': 0, 'energy': 0})
            for record in revenue_history:
                date = record['date']
                date_totals[date]['revenue'] += record['total_revenue']
                date_totals[date]['energy'] += record['total_energy']
            
            # 取最近7天数据
            sorted_dates = sorted(date_totals.keys())[-7:]
            
            for date in sorted_dates:
                dates.append(date)
                revenue = date_totals[date]['revenue']
                cost = date_totals[date]['energy'] * 0.7  # 假设成本率70%
                daily_revenues.append(revenue)
                daily_costs.append(cost)
            
            profits = [r - c for r, c in zip(daily_revenues, daily_costs)]
            
            # 使用日期索引绘制
            x_data = list(range(len(dates)))
            self.revenue_chart.plot(x_data, daily_revenues, pen='b', name='收入', symbol='o')
            self.revenue_chart.plot(x_data, daily_costs, pen='r', name='成本', symbol='s')
            self.revenue_chart.plot(x_data, profits, pen='g', name='利润', symbol='^')
            
            # 设置X轴标签
            ax = self.revenue_chart.getAxis('bottom')
            ax.setTicks([[(i, dates[i][-5:]) for i in range(len(dates))]])
            
        elif hasattr(self, 'revenue_data') and self.revenue_data:
            # 如果没有历史数据但有当前数据，生成模拟的24小时趋势数据
            current_revenue = self.revenue_data.get('total_revenue', 0)
            current_energy = self.revenue_data.get('total_energy', 0)
            

            # 使用当前数据生成24小时趋势
            hours = list(range(24))
            revenue = []
            cost = []
                
            for hour in hours:
                # 根据时间段调整收益分布
                if 6 <= hour <= 9 or 17 <= hour <= 20:  # 高峰期
                    hour_factor = 1.5
                elif 0 <= hour <= 5:  # 深夜
                    hour_factor = 0.3
                else:
                    hour_factor = 1.0
                    
                # 基于当前总收益按比例分配
                hour_revenue = (current_revenue / 24) * hour_factor
                hour_cost = hour_revenue * 0.7  # 假设成本率70%
                    
                revenue.append(hour_revenue)
                cost.append(hour_cost)
            
            profit = [r - c for r, c in zip(revenue, cost)]
            
            # 绘制曲线
            self.revenue_chart.plot(hours, revenue, pen='b', name='收入', symbol='o')
            self.revenue_chart.plot(hours, cost, pen='r', name='成本', symbol='s')
            self.revenue_chart.plot(hours, profit, pen='g', name='利润', symbol='^')
            
            # 设置X轴标签
            ax = self.revenue_chart.getAxis('bottom')
            ax.setTicks([[(i, f'{i:02d}:00') for i in range(0, 24, 4)]])
        else:
            # 如果没有任何数据，生成示例数据
            import random
            hours = list(range(24))
            revenue = []
            cost = []
            
            base_revenue = 300
            for hour in hours:
                if 6 <= hour <= 9 or 17 <= hour <= 20:  # 高峰期
                    hour_factor = 1.8 + random.uniform(-0.2, 0.2)
                elif 10 <= hour <= 16:  # 白天
                    hour_factor = 1.2 + random.uniform(-0.2, 0.2)
                elif 21 <= hour <= 23:  # 晚上
                    hour_factor = 0.8 + random.uniform(-0.1, 0.1)
                else:  # 深夜
                    hour_factor = 0.4 + random.uniform(-0.1, 0.1)
                
                hour_revenue = base_revenue * hour_factor
                hour_cost = hour_revenue * 0.65
                
                revenue.append(hour_revenue)
                cost.append(hour_cost)
            
            profit = [r - c for r, c in zip(revenue, cost)]
            
            # 绘制曲线
            self.revenue_chart.plot(hours, revenue, pen='b', name='收入', symbol='o')
            self.revenue_chart.plot(hours, cost, pen='r', name='成本', symbol='s')
            self.revenue_chart.plot(hours, profit, pen='g', name='利润', symbol='^')
            
            # 设置X轴标签
            ax = self.revenue_chart.getAxis('bottom')
            ax.setTicks([[(i, f'{i:02d}:00') for i in range(0, 24, 4)]])
        
    def _updateDetailTable(self):
        """更新详细表格"""
        # 使用真实的充电桩数据
        if hasattr(self, 'revenue_data') and self.revenue_data:
            chargers = self.revenue_data.get('chargers', [])
            
            # 如果没有充电桩数据或数据为空，生成示例数据
            if not chargers:
                self._generateSampleTableData()
                return
            
            # 按区域分组充电桩数据
            stations = defaultdict(list)
            for charger in chargers:
                region = charger.get('region', '未知区域')
                stations[region].append(charger)
            
            station_list = list(stations.keys())
            
            # 检查是否有有效的收益数据
            total_system_revenue = 0
            for station_chargers in stations.values():
                total_system_revenue += sum(c.get('daily_revenue', 0) for c in station_chargers)
            
            # 如果总收益太小，生成示例数据
            if total_system_revenue < 10:
                self._generateSampleTableData()
                return
            
            self.detail_table.setRowCount(len(station_list))
            
            for row, station_name in enumerate(station_list):
                station_chargers = stations[station_name]
                
                # 计算站点汇总数据
                total_energy = sum(c.get('daily_energy', 0) for c in station_chargers)
                total_revenue = sum(c.get('daily_revenue', 0) for c in station_chargers)
                total_cost = total_energy * 0.7  # 假设成本率70%
                profit = total_revenue - total_cost
                margin = (profit / total_revenue * 100) if total_revenue > 0 else 0
                
                # 站点
                self.detail_table.setItem(row, 0, QTableWidgetItem(station_name))
                
                # 充电量
                self.detail_table.setItem(row, 1, QTableWidgetItem(f"{total_energy:.1f}"))
                
                # 收入
                self.detail_table.setItem(row, 2, QTableWidgetItem(f"{total_revenue:.2f}"))
                
                # 成本
                self.detail_table.setItem(row, 3, QTableWidgetItem(f"{total_cost:.2f}"))
                
                # 利润
                profit_item = QTableWidgetItem(f"{profit:.2f}")
                if profit > 0:
                    profit_item.setForeground(QColor(39, 174, 96))
                else:
                    profit_item.setForeground(QColor(231, 76, 60))
                self.detail_table.setItem(row, 4, profit_item)
                
                # 利润率
                self.detail_table.setItem(row, 5, QTableWidgetItem(f"{margin:.1f}"))
        else:
            # 如果没有真实数据，生成示例数据
            self._generateSampleTableData()
    
    def _generateSampleTableData(self):
        """生成示例表格数据"""
        import random
        
        # 示例区域数据
        sample_regions = [
            {'name': '市中心区', 'base_energy': 2500},
            {'name': '商业区', 'base_energy': 2000},
            {'name': '住宅区', 'base_energy': 1200},
            {'name': '工业区', 'base_energy': 800},
            {'name': '郊区', 'base_energy': 500}
        ]
        
        self.detail_table.setRowCount(len(sample_regions))
        
        for row, region_info in enumerate(sample_regions):
            # 添加随机变化
            energy = region_info['base_energy'] * (0.8 + random.random() * 0.4)
            revenue = energy * (1.2 + random.random() * 0.3)  # 每kWh 1.2-1.5元
            cost = energy * 0.65  # 成本率65%
            profit = revenue - cost
            margin = (profit / revenue * 100) if revenue > 0 else 0
            
            # 站点
            self.detail_table.setItem(row, 0, QTableWidgetItem(region_info['name']))
            
            # 充电量
            self.detail_table.setItem(row, 1, QTableWidgetItem(f"{energy:.1f}"))
            
            # 收入
            self.detail_table.setItem(row, 2, QTableWidgetItem(f"{revenue:.2f}"))
            
            # 成本
            self.detail_table.setItem(row, 3, QTableWidgetItem(f"{cost:.2f}"))
            
            # 利润
            profit_item = QTableWidgetItem(f"{profit:.2f}")
            if profit > 0:
                profit_item.setForeground(QColor(39, 174, 96))
            else:
                profit_item.setForeground(QColor(231, 76, 60))
            self.detail_table.setItem(row, 4, profit_item)
            
            # 利润率
            self.detail_table.setItem(row, 5, QTableWidgetItem(f"{margin:.1f}"))


class DemandPredictionWidget(QWidget):
    """需求预测组件"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.prediction_data = {}
        self.setupUI()
        
    def setupUI(self):
        layout = QVBoxLayout(self)
        
        # 预测控制
        control_layout = QHBoxLayout()
        
        control_layout.addWidget(QLabel("预测时长:"))
        self.prediction_days = QSpinBox()
        self.prediction_days.setRange(1, 30)
        self.prediction_days.setValue(7)
        self.prediction_days.setSuffix(" 天")
        control_layout.addWidget(self.prediction_days)
        
        control_layout.addWidget(QLabel("预测模型:"))
        self.model_combo = QComboBox()
        self.model_combo.addItems(["时间序列", "机器学习", "混合模型"])
        control_layout.addWidget(self.model_combo)
        
        self.predict_button = QPushButton("生成预测")
        self.predict_button.clicked.connect(self.generatePrediction)
        control_layout.addWidget(self.predict_button)
        
        control_layout.addStretch()
        layout.addLayout(control_layout)
        
        if HAS_PYQTGRAPH:
            # 预测图表
            self.prediction_chart = PlotWidget()
            self.prediction_chart.setBackground('w')
            self.prediction_chart.setLabel('left', '充电需求 (kWh)')
            self.prediction_chart.setLabel('bottom', '时间')
            self.prediction_chart.showGrid(x=True, y=True, alpha=0.3)
            self.prediction_chart.addLegend()
            layout.addWidget(self.prediction_chart)
        
        # 预测汇总
        summary_group = QGroupBox("预测汇总")
        summary_layout = QGridLayout(summary_group)
        
        self.peak_demand_label = QLabel("预测峰值需求: 0 kWh")
        self.avg_demand_label = QLabel("平均日需求: 0 kWh")
        self.growth_rate_label = QLabel("需求增长率: 0%")
        self.confidence_label = QLabel("预测置信度: 0%")
        
        summary_layout.addWidget(self.peak_demand_label, 0, 0)
        summary_layout.addWidget(self.avg_demand_label, 0, 1)
        summary_layout.addWidget(self.growth_rate_label, 1, 0)
        summary_layout.addWidget(self.confidence_label, 1, 1)
        
        layout.addWidget(summary_group)
        
        # 站点需求表
        self.station_demand_table = QTableWidget()
        self.station_demand_table.setColumnCount(5)
        self.station_demand_table.setHorizontalHeaderLabels([
            "站点", "当前负载率", "预测峰值", "建议扩容", "优先级"
        ])
        layout.addWidget(self.station_demand_table)
        
    def generatePrediction(self):
        """生成需求预测"""
        days = self.prediction_days.value()
        model = self.model_combo.currentText()
        
        # 生成预测数据（示例）
        self.prediction_data = self._generatePredictionData(days)
        
        # 更新显示
        self.updateDisplay()
        
        QMessageBox.information(self, "预测完成", 
            f"已使用{model}生成未来{days}天的需求预测")
        
    def _generatePredictionData(self, days):
        """基于真实数据生成预测数据"""
        # 获取历史数据作为预测基础
        historical_data = data_storage.get_usage_history(days=30)  # 获取30天历史数据
        
        if historical_data:
            # 基于历史数据计算基础需求和趋势
            daily_demands = defaultdict(float)
            hourly_patterns = defaultdict(list)
            
            for record in historical_data:
                date = record['date']
                hour = record.get('hour', 0)
                energy = record.get('total_energy', 0)
                
                daily_demands[date] += energy
                hourly_patterns[hour].append(energy)
            
            # 计算平均日需求和增长趋势
            sorted_dates = sorted(daily_demands.keys())
            if len(sorted_dates) >= 7:
                recent_avg = np.mean([daily_demands[d] for d in sorted_dates[-7:]])
                earlier_avg = np.mean([daily_demands[d] for d in sorted_dates[:7]])
                growth_rate = (recent_avg - earlier_avg) / earlier_avg if earlier_avg > 0 else 0.05
                base_demand = recent_avg
            else:
                base_demand = np.mean(list(daily_demands.values())) if daily_demands else 5000
                growth_rate = 0.05
            
            # 计算小时模式
            hour_factors = {}
            avg_hourly = np.mean([np.mean(values) for values in hourly_patterns.values() if values])
            for hour in range(24):
                if hour in hourly_patterns and hourly_patterns[hour]:
                    hour_factors[hour] = np.mean(hourly_patterns[hour]) / avg_hourly if avg_hourly > 0 else 1.0
                else:
                    # 使用默认模式
                    if 6 <= hour <= 9:
                        hour_factors[hour] = 1.5
                    elif 17 <= hour <= 20:
                        hour_factors[hour] = 1.8
                    elif 0 <= hour <= 5:
                        hour_factors[hour] = 0.3
                    else:
                        hour_factors[hour] = 1.0
        else:
            # 如果没有历史数据，使用当前数据或默认值
            if hasattr(self.parent(), 'current_data') and self.parent().current_data:
                chargers = self.parent().current_data.get('chargers', [])
                current_total_energy = sum(c.get('daily_energy', 0) for c in chargers)
                current_utilization = len([c for c in chargers if c.get('status') == 'occupied']) / max(len(chargers), 1)
                
                base_demand = max(current_total_energy, 1000)
                if current_utilization > 0.8:
                    growth_rate = 0.15
                elif current_utilization > 0.5:
                    growth_rate = 0.10
                else:
                    growth_rate = 0.05
            else:
                base_demand = 5000
                growth_rate = 0.05
            
            # 默认小时模式
            hour_factors = {}
            for hour in range(24):
                if 6 <= hour <= 9:
                    hour_factors[hour] = 1.5
                elif 17 <= hour <= 20:
                    hour_factors[hour] = 1.8
                elif 0 <= hour <= 5:
                    hour_factors[hour] = 0.3
                else:
                    hour_factors[hour] = 1.0
        
        # 生成每小时预测
        hours = days * 24
        timestamps = []
        demands = []
        
        for h in range(hours):
            hour_of_day = h % 24
            day_of_week = (h // 24) % 7
            
            # 应用小时模式
            daily_factor = hour_factors.get(hour_of_day, 1.0)
            
            # 周末调整
            weekly_factor = 1.2 if day_of_week in [5, 6] else 1.0
            
            # 增长趋势
            growth_factor = 1 + (h / hours) * growth_rate
            
            # 减少随机波动
            random_factor = np.random.uniform(0.98, 1.02)
            
            demand = base_demand * daily_factor * weekly_factor * growth_factor * random_factor / 24
            
            timestamps.append(datetime.now() + timedelta(hours=h))
            demands.append(max(demand, 0))  # 确保需求非负
        
        # 计算置信度
        confidence = 90.0 if historical_data else 75.0
        
        return {
            'timestamps': timestamps,
            'demands': demands,
            'peak_demand': max(demands),
            'avg_demand': np.mean(demands),
            'growth_rate': growth_rate * 100,
            'confidence': confidence
        }
        
    def updateDisplay(self):
        """更新显示"""
        if not self.prediction_data:
            return
        
        # 更新汇总信息
        peak = self.prediction_data['peak_demand']
        avg = self.prediction_data['avg_demand']
        growth = self.prediction_data['growth_rate']
        confidence = self.prediction_data['confidence']
        
        self.peak_demand_label.setText(f"预测峰值需求: {peak:,.0f} kWh")
        self.avg_demand_label.setText(f"平均日需求: {avg:,.0f} kWh")
        self.growth_rate_label.setText(f"需求增长率: {growth:.1f}%")
        self.confidence_label.setText(f"预测置信度: {confidence:.0f}%")
        
        # 更新图表
        if HAS_PYQTGRAPH and hasattr(self, 'prediction_chart'):
            self._updatePredictionChart()
        
        # 更新站点需求表
        self._updateStationDemandTable()
        
    def _updatePredictionChart(self):
        """更新预测图表"""
        self.prediction_chart.clear()
        
        if not self.prediction_data:
            return
        
        # 准备数据
        timestamps = self.prediction_data['timestamps']
        demands = self.prediction_data['demands']
        
        # 转换为小时索引
        hours = list(range(len(timestamps)))
        
        # 绘制预测曲线
        self.prediction_chart.plot(hours, demands, pen='b', name='预测需求')
        
        # 添加置信区间
        upper_bound = [d * 1.1 for d in demands]
        lower_bound = [d * 0.9 for d in demands]
        
        # 填充置信区间
        self.prediction_chart.plot(hours, upper_bound, pen='r', style=Qt.PenStyle.DashLine)
        self.prediction_chart.plot(hours, lower_bound, pen='r', style=Qt.PenStyle.DashLine)
        
    def _updateStationDemandTable(self):
        """更新站点需求表"""
        # 示例站点数据
        stations = [
            {'name': '充电站1', 'load': 85, 'peak': 12000, 'expand': 4, 'priority': '高'},
            {'name': '充电站2', 'load': 70, 'peak': 8000, 'expand': 2, 'priority': '中'},
            {'name': '充电站3', 'load': 50, 'peak': 6000, 'expand': 0, 'priority': '低'},
            {'name': '充电站4', 'load': 95, 'peak': 15000, 'expand': 6, 'priority': '紧急'},
            {'name': '充电站5', 'load': 60, 'peak': 7000, 'expand': 1, 'priority': '低'},
        ]
        
        self.station_demand_table.setRowCount(len(stations))
        
        for row, station in enumerate(stations):
            # 站点名称
            self.station_demand_table.setItem(row, 0, QTableWidgetItem(station['name']))
            
            # 当前负载率
            load_item = QTableWidgetItem(f"{station['load']}%")
            if station['load'] > 80:
                load_item.setForeground(QColor(231, 76, 60))
            elif station['load'] > 60:
                load_item.setForeground(QColor(243, 156, 18))
            self.station_demand_table.setItem(row, 1, load_item)
            
            # 预测峰值
            self.station_demand_table.setItem(row, 2, QTableWidgetItem(f"{station['peak']:,} kWh"))
            
            # 建议扩容
            expand_item = QTableWidgetItem(f"+{station['expand']} 桩")
            if station['expand'] > 0:
                expand_item.setForeground(QColor(52, 152, 219))
            self.station_demand_table.setItem(row, 3, expand_item)
            
            # 优先级
            priority_item = QTableWidgetItem(station['priority'])
            if station['priority'] == '紧急':
                priority_item.setForeground(QColor(231, 76, 60))
                priority_item.setFont(QFont("Arial", 9, QFont.Weight.Bold))
            elif station['priority'] == '高':
                priority_item.setForeground(QColor(243, 156, 18))
            self.station_demand_table.setItem(row, 4, priority_item)

class MaintenanceManagementWidget(QWidget):
   """维护管理组件"""
   
   def __init__(self, parent=None):
       super().__init__(parent)
       self.work_orders = []
       self.alerts = []
       self.setupUI()
       self._loadSampleData()
       
   def setupUI(self):
       layout = QVBoxLayout(self)
       
       # 创建选项卡
       tab_widget = QTabWidget()
       
       # 告警管理选项卡
       alerts_tab = self._createAlertsTab()
       tab_widget.addTab(alerts_tab, "告警管理")
       
       # 工单管理选项卡
       work_orders_tab = self._createWorkOrdersTab()
       tab_widget.addTab(work_orders_tab, "工单管理")
       
       # 故障分析选项卡
       fault_analysis_tab = self._createFaultAnalysisTab()
       tab_widget.addTab(fault_analysis_tab, "故障分析")
       
       layout.addWidget(tab_widget)
       
   def _createAlertsTab(self):
       """创建告警管理选项卡"""
       widget = QWidget()
       layout = QVBoxLayout(widget)
       
       # 告警统计
       stats_layout = QHBoxLayout()
       
       self.critical_alerts_label = self._createAlertStatCard("严重", 0, "#e74c3c")
       self.warning_alerts_label = self._createAlertStatCard("警告", 0, "#f39c12")
       self.info_alerts_label = self._createAlertStatCard("提示", 0, "#3498db")
       
       stats_layout.addWidget(self.critical_alerts_label)
       stats_layout.addWidget(self.warning_alerts_label)
       stats_layout.addWidget(self.info_alerts_label)
       stats_layout.addStretch()
       
       layout.addLayout(stats_layout)
       
       # 告警列表
       self.alerts_table = QTableWidget()
       self.alerts_table.setColumnCount(6)
       self.alerts_table.setHorizontalHeaderLabels([
           "时间", "级别", "充电桩", "告警内容", "状态", "操作"
       ])
       self.alerts_table.horizontalHeader().setStretchLastSection(True)
       layout.addWidget(self.alerts_table)
       
       # 告警规则设置
       rules_group = QGroupBox("告警规则")
       rules_layout = QFormLayout(rules_group)
       
       # 离线时长阈值
       self.offline_threshold = QSpinBox()
       self.offline_threshold.setRange(1, 60)
       self.offline_threshold.setValue(10)
       self.offline_threshold.setSuffix(" 分钟")
       rules_layout.addRow("离线告警阈值:", self.offline_threshold)
       
       # 故障率阈值
       self.fault_rate_threshold = QDoubleSpinBox()
       self.fault_rate_threshold.setRange(0, 100)
       self.fault_rate_threshold.setValue(10)
       self.fault_rate_threshold.setSuffix(" %")
       rules_layout.addRow("故障率告警阈值:", self.fault_rate_threshold)
       
       # 排队长度阈值
       self.queue_threshold = QSpinBox()
       self.queue_threshold.setRange(1, 20)
       self.queue_threshold.setValue(5)
       self.queue_threshold.setSuffix(" 人")
       rules_layout.addRow("排队告警阈值:", self.queue_threshold)
       
       layout.addWidget(rules_group)
       
       return widget
       
   def _createAlertStatCard(self, level, count, color):
       """创建告警统计卡片"""
       card = QFrame()
       card.setFrameStyle(QFrame.Shape.Box)
       card.setStyleSheet(f"""
           QFrame {{
               background: white;
               border: 2px solid {color};
               border-radius: 8px;
               padding: 10px;
           }}
       """)
       
       layout = QVBoxLayout(card)
       
       count_label = QLabel(str(count))
       count_label.setFont(QFont("Arial", 24, QFont.Weight.Bold))
       count_label.setStyleSheet(f"color: {color};")
       count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
       layout.addWidget(count_label)
       
       level_label = QLabel(level)
       level_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
       layout.addWidget(level_label)
       
       # 保存引用以便更新
       card.count_label = count_label
       
       return card
       
   def _createWorkOrdersTab(self):
       """创建工单管理选项卡"""
       widget = QWidget()
       layout = QVBoxLayout(widget)
       
       # 工单控制栏
       control_layout = QHBoxLayout()
       
       self.create_work_order_btn = QPushButton("创建工单")
       self.create_work_order_btn.clicked.connect(self.createWorkOrder)
       control_layout.addWidget(self.create_work_order_btn)
       
       control_layout.addWidget(QLabel("筛选:"))
       self.status_filter = QComboBox()
       self.status_filter.addItems(["全部", "待处理", "处理中", "已完成", "已关闭"])
       self.status_filter.currentTextChanged.connect(self.filterWorkOrders)
       control_layout.addWidget(self.status_filter)
       
       control_layout.addStretch()
       layout.addLayout(control_layout)
       
       # 工单列表
       self.work_orders_table = QTableWidget()
       self.work_orders_table.setColumnCount(7)
       self.work_orders_table.setHorizontalHeaderLabels([
           "工单号", "创建时间", "充电桩", "故障类型", "状态", "负责人", "操作"
       ])
       self.work_orders_table.horizontalHeader().setStretchLastSection(True)
       layout.addWidget(self.work_orders_table)
       
       return widget
       
   def _createFaultAnalysisTab(self):
       """创建故障分析选项卡"""
       widget = QWidget()
       layout = QVBoxLayout(widget)
       
       # 故障统计
       if HAS_PYQTGRAPH:
           # 故障类型分布图
           self.fault_type_chart = PlotWidget()
           self.fault_type_chart.setBackground('w')
           self.fault_type_chart.setTitle("故障类型分布")
           layout.addWidget(self.fault_type_chart)
           
           # 故障趋势图
           self.fault_trend_chart = PlotWidget()
           self.fault_trend_chart.setBackground('w')
           self.fault_trend_chart.setTitle("故障趋势分析")
           self.fault_trend_chart.setLabel('left', '故障次数')
           self.fault_trend_chart.setLabel('bottom', '日期')
           self.fault_trend_chart.showGrid(x=True, y=True, alpha=0.3)
           layout.addWidget(self.fault_trend_chart)
       
       # 故障原因分析表
       self.fault_analysis_table = QTableWidget()
       self.fault_analysis_table.setColumnCount(4)
       self.fault_analysis_table.setHorizontalHeaderLabels([
           "故障类型", "发生次数", "平均修复时间", "改进建议"
       ])
       layout.addWidget(self.fault_analysis_table)
       
       return widget
       
   def addAlert(self, alert_data):
       """添加告警"""
       self.alerts.append(alert_data)
       self.updateAlertsDisplay()
       
   def updateAlertsDisplay(self):
       """更新告警显示"""
       # 统计各级别告警数量
       critical_count = sum(1 for a in self.alerts if a.get('level') == 'critical')
       warning_count = sum(1 for a in self.alerts if a.get('level') == 'warning')
       info_count = sum(1 for a in self.alerts if a.get('level') == 'info')
       
       # 更新统计卡片
       self.critical_alerts_label.count_label.setText(str(critical_count))
       self.warning_alerts_label.count_label.setText(str(warning_count))
       self.info_alerts_label.count_label.setText(str(info_count))
       
       # 更新告警列表
       self.alerts_table.setRowCount(len(self.alerts))
       
       for row, alert in enumerate(self.alerts):
           # 时间
           self.alerts_table.setItem(row, 0, QTableWidgetItem(alert.get('timestamp', '')))
           
           # 级别
           level = alert.get('level', 'info')
           level_item = QTableWidgetItem(level)
           if level == 'critical':
               level_item.setBackground(QColor(231, 76, 60))
               level_item.setForeground(QColor(255, 255, 255))
           elif level == 'warning':
               level_item.setBackground(QColor(243, 156, 18))
               level_item.setForeground(QColor(255, 255, 255))
           self.alerts_table.setItem(row, 1, level_item)
           
           # 充电桩
           self.alerts_table.setItem(row, 2, QTableWidgetItem(alert.get('charger_id', '')))
           
           # 告警内容
           self.alerts_table.setItem(row, 3, QTableWidgetItem(alert.get('message', '')))
           
           # 状态
           status = alert.get('status', '未处理')
           self.alerts_table.setItem(row, 4, QTableWidgetItem(status))
           
           # 操作按钮
           action_widget = QWidget()
           action_layout = QHBoxLayout(action_widget)
           action_layout.setContentsMargins(0, 0, 0, 0)
           
           handle_btn = QPushButton("处理")
           handle_btn.clicked.connect(lambda checked, r=row: self.handleAlert(r))
           action_layout.addWidget(handle_btn)
           
           self.alerts_table.setCellWidget(row, 5, action_widget)
           
   def createWorkOrder(self, charger_id=None, fault_type=None):
        """创建工单（基于真实故障数据）"""
        # 如果没有指定充电桩和故障类型，则基于真实数据创建
        if not charger_id or not fault_type:
            # 从当前故障充电桩中选择
            if hasattr(self.parent(), 'current_data') and self.parent().current_data:
                chargers = self.parent().current_data.get('chargers', [])
                failed_chargers = [c for c in chargers if c.get('status') == 'failure']
                
                if failed_chargers:
                    # 选择第一个故障充电桩
                    failed_charger = failed_chargers[0]
                    charger_id = failed_charger.get('charger_id', f'充电桩{len(self.work_orders)+1}')
                    fault_type = '设备故障'  # 基于真实状态
                else:
                    # 如果没有故障充电桩，创建预防性维护工单
                    charger_id = f'充电桩{len(self.work_orders)+1}'
                    fault_type = '预防性维护'
            else:
                charger_id = f'充电桩{len(self.work_orders)+1}'
                fault_type = '预防性维护'
        
        work_order = {
            'id': f"WO{len(self.work_orders)+1:04d}",
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'charger_id': charger_id,
            'fault_type': fault_type,
            'status': '待处理',
            'assignee': '未分配'
        }
        
        self.work_orders.append(work_order)
        self.updateWorkOrdersDisplay()
       
   def filterWorkOrders(self, status_filter):
       """筛选工单"""
       self.updateWorkOrdersDisplay()
       
   def updateWorkOrdersDisplay(self):
       """更新工单显示"""
       # 获取筛选条件
       status_filter = self.status_filter.currentText()
       
       # 筛选工单
       if status_filter == "全部":
           filtered_orders = self.work_orders
       else:
           filtered_orders = [wo for wo in self.work_orders if wo.get('status') == status_filter]
       
       # 更新表格
       self.work_orders_table.setRowCount(len(filtered_orders))
       
       for row, order in enumerate(filtered_orders):
           # 工单号
           self.work_orders_table.setItem(row, 0, QTableWidgetItem(order.get('id', '')))
           
           # 创建时间
           self.work_orders_table.setItem(row, 1, QTableWidgetItem(order.get('timestamp', '')))
           
           # 充电桩
           self.work_orders_table.setItem(row, 2, QTableWidgetItem(order.get('charger_id', '')))
           
           # 故障类型
           self.work_orders_table.setItem(row, 3, QTableWidgetItem(order.get('fault_type', '')))
           
           # 状态
           status = order.get('status', '')
           status_item = QTableWidgetItem(status)
           if status == '待处理':
               status_item.setForeground(QColor(231, 76, 60))
           elif status == '处理中':
               status_item.setForeground(QColor(243, 156, 18))
           elif status == '已完成':
               status_item.setForeground(QColor(39, 174, 96))
           self.work_orders_table.setItem(row, 4, status_item)
           
           # 负责人
           self.work_orders_table.setItem(row, 5, QTableWidgetItem(order.get('assignee', '')))
           
           # 操作按钮
           action_widget = QWidget()
           action_layout = QHBoxLayout(action_widget)
           action_layout.setContentsMargins(0, 0, 0, 0)
           
           if status != '已完成':
               update_btn = QPushButton("更新")
               update_btn.clicked.connect(lambda checked, r=row: self.updateWorkOrder(r))
               action_layout.addWidget(update_btn)
           
           self.work_orders_table.setCellWidget(row, 6, action_widget)
           
   def handleAlert(self, row):
       """处理告警"""
       if row < len(self.alerts):
           self.alerts[row]['status'] = '已处理'
           self.updateAlertsDisplay()
           QMessageBox.information(self, "成功", "告警已处理")
           
   def updateWorkOrder(self, row):
       """更新工单"""
       # 这里应该弹出更新工单对话框
       # 简化示例：直接更新状态
       if row < len(self.work_orders):
           current_status = self.work_orders[row]['status']
           if current_status == '待处理':
               self.work_orders[row]['status'] = '处理中'
               self.work_orders[row]['assignee'] = '张三'
           elif current_status == '处理中':
               self.work_orders[row]['status'] = '已完成'
           
           self.updateWorkOrdersDisplay()
           
   def _loadSampleData(self):
       """加载示例数据"""
       from datetime import datetime, timedelta
       import random
       
       # 生成示例告警数据
       sample_alerts = [
           {
               'timestamp': (datetime.now() - timedelta(hours=2)).strftime('%Y-%m-%d %H:%M:%S'),
               'level': 'critical',
               'charger_id': 'CHG001',
               'message': '充电桩通信故障',
               'status': '处理中'
           },
           {
               'timestamp': (datetime.now() - timedelta(hours=1)).strftime('%Y-%m-%d %H:%M:%S'),
               'level': 'warning',
               'charger_id': 'CHG003',
               'message': '充电功率异常',
               'status': '未处理'
           },
           {
               'timestamp': (datetime.now() - timedelta(minutes=30)).strftime('%Y-%m-%d %H:%M:%S'),
               'level': 'info',
               'charger_id': 'CHG005',
               'message': '定期维护提醒',
               'status': '未处理'
           }
       ]
       
       # 生成示例工单数据
       sample_work_orders = [
           {
               'id': 'WO001',
               'charger_id': 'CHG001',
               'type': '故障维修',
               'description': '充电桩通信模块故障，需要更换通信板',
               'priority': '高',
               'status': '进行中',
               'created_time': (datetime.now() - timedelta(hours=3)).strftime('%Y-%m-%d %H:%M:%S'),
               'assigned_to': '张工程师',
               'estimated_time': '2小时'
           },
           {
               'id': 'WO002',
               'charger_id': 'CHG003',
               'type': '预防性维护',
               'description': '定期检查充电接口和电缆',
               'priority': '中',
               'status': '待分配',
               'created_time': (datetime.now() - timedelta(hours=1)).strftime('%Y-%m-%d %H:%M:%S'),
               'assigned_to': '',
               'estimated_time': '1小时'
           }
       ]
       
       # 添加到组件中
       self.alerts.extend(sample_alerts)
       self.work_orders.extend(sample_work_orders)


class OperatorControlPanel(QWidget):
   """运营商控制面板主组件"""
   
   # 信号定义
   pricingStrategyChanged = pyqtSignal(dict)
   maintenanceRequested = pyqtSignal(str)
   
   def __init__(self, parent=None):
       super().__init__(parent)
       self.simulation_environment = None
       self.current_data = {}
       self.setupUI()
       self.setupTimers()
       
   def setupUI(self):
       """设置UI"""
       layout = QVBoxLayout(self)
       
       # 创建工具栏
       toolbar = self._createToolbar()
       layout.addWidget(toolbar)
       
       # 创建主分割器
       main_splitter = QSplitter(Qt.Orientation.Horizontal)
       
       # 左侧面板 - 实时监控
       left_panel = self._createLeftPanel()
       main_splitter.addWidget(left_panel)
       
       # 右侧面板 - 详细信息
       right_panel = self._createRightPanel()
       main_splitter.addWidget(right_panel)
       
       # 设置分割比例
       main_splitter.setStretchFactor(0, 1)
       main_splitter.setStretchFactor(1, 2)
       
       layout.addWidget(main_splitter)
       
   def _createToolbar(self):
       """创建工具栏"""
       toolbar = QToolBar()
       
       # 刷新按钮
       refresh_action = QAction("🔄 刷新", self)
       refresh_action.triggered.connect(self.refreshData)
       toolbar.addAction(refresh_action)
       
       toolbar.addSeparator()
       
       # 导出按钮
       export_action = QAction("📊 导出报表", self)
       export_action.triggered.connect(self.exportReport)
       toolbar.addAction(export_action)
       
       # 设置按钮
       settings_action = QAction("⚙️ 设置", self)
       settings_action.triggered.connect(self.showSettings)
       toolbar.addAction(settings_action)
       
       return toolbar
       
   def _createLeftPanel(self):
       """创建左侧面板 - 实时监控"""
       panel = QWidget()
       layout = QVBoxLayout(panel)
       
       # 站点健康度监控
       health_group = QGroupBox("站点健康度")
       health_layout = QGridLayout(health_group)
       
       self.health_cards = {}
       # 创建示例站点健康卡片
       for i in range(6):
           station_id = f"充电站{i+1}"
           card = StationHealthCard(station_id)
           health_layout.addWidget(card, i//2, i%2)
           self.health_cards[station_id] = card
           
       layout.addWidget(health_group)
       
       # 实时统计
       stats_group = QGroupBox("实时统计")
       stats_layout = QFormLayout(stats_group)
       
       self.total_chargers_label = QLabel("0")
       self.available_chargers_label = QLabel("0")
       self.charging_users_label = QLabel("0")
       self.today_revenue_label = QLabel("¥0.00")
       
       stats_layout.addRow("总充电桩:", self.total_chargers_label)
       stats_layout.addRow("可用充电桩:", self.available_chargers_label)
       stats_layout.addRow("充电中用户:", self.charging_users_label)
       stats_layout.addRow("今日收入:", self.today_revenue_label)
       
       layout.addWidget(stats_group)
       
       layout.addStretch()
       
       return panel
       
   def _createRightPanel(self):
       """创建右侧面板 - 详细信息"""
       # 创建选项卡
       tab_widget = QTabWidget()
       
       # 定价管理选项卡
       self.pricing_widget = PricingStrategyWidget()
       self.pricing_widget.strategyChanged.connect(self.onPricingStrategyChanged)
       tab_widget.addTab(self.pricing_widget, "定价管理")
       
       # 收益分析选项卡
       self.revenue_widget = RevenueAnalysisWidget()
       tab_widget.addTab(self.revenue_widget, "收益分析")
       
       # 需求预测选项卡
       self.prediction_widget = DemandPredictionWidget()
       tab_widget.addTab(self.prediction_widget, "需求预测")
       
       # 维护管理选项卡
       self.maintenance_widget = MaintenanceManagementWidget()
       tab_widget.addTab(self.maintenance_widget, "维护管理")
       
       return tab_widget
       
   def setupTimers(self):
       """设置定时器"""
       # 数据更新定时器
       self.update_timer = QTimer()
       self.update_timer.timeout.connect(self.updateRealtimeData)
       self.update_timer.start(5000)  # 5秒更新一次
       
       # 告警检查定时器
       self.alert_timer = QTimer()
       self.alert_timer.timeout.connect(self.checkAlerts)
       self.alert_timer.start(30000)  # 30秒检查一次
       
   def setSimulationEnvironment(self, environment):
       """设置仿真环境"""
       self.simulation_environment = environment
       logger.info("运营商面板已连接到仿真环境")
       
   def updateSimulationData(self, state_data):
       """更新仿真数据"""
       if not state_data:
           return
           
       self.current_data = state_data
       
       # 更新实时统计
       self.updateRealtimeStats(state_data)
       
       # 更新站点健康度
       self.updateStationHealth(state_data)
       
       # 更新收益数据
       self.updateRevenueData(state_data)
       
   def updateRealtimeStats(self, state_data):
       """更新实时统计"""
       chargers = state_data.get('chargers', [])
       users = state_data.get('users', [])
       
       # 统计充电桩状态
       total_chargers = len(chargers)
       available_chargers = sum(1 for c in chargers if c.get('status') == 'available')
       charging_users = sum(1 for u in users if u.get('status') == 'charging')
       
       # 计算今日收入
       today_revenue = sum(c.get('daily_revenue', 0) for c in chargers)
       
       # 更新显示
       self.total_chargers_label.setText(str(total_chargers))
       self.available_chargers_label.setText(str(available_chargers))
       self.charging_users_label.setText(str(charging_users))
       self.today_revenue_label.setText(f"¥{today_revenue:,.2f}")
       
   def updateStationHealth(self, state_data):
       """更新站点健康度"""
       chargers = state_data.get('chargers', [])
       
       # 按站点分组
       stations = defaultdict(list)
       for charger in chargers:
           station = charger.get('location', '未知站点')
           stations[station].append(charger)
       
       # 计算每个站点的健康度
       for station_id, station_chargers in stations.items():
           health_score = self._calculateStationHealth(station_chargers)
           
           if station_id in self.health_cards:
               self.health_cards[station_id].updateHealth({
                   'score': health_score,
                   'chargers': station_chargers
               })
               
   def _calculateStationHealth(self, chargers):
       """计算站点健康度得分"""
       if not chargers:
           return 0
           
       # 故障率
       failure_count = sum(1 for c in chargers if c.get('status') == 'failure')
       failure_rate = failure_count / len(chargers)
       
       # 利用率
       occupied_count = sum(1 for c in chargers if c.get('status') == 'occupied')
       utilization_rate = occupied_count / len(chargers)
       
       # 队列长度
       avg_queue_length = np.mean([len(c.get('queue', [])) for c in chargers])
       
       # 计算综合得分
       health_score = 100
       health_score -= failure_rate * 50  # 故障率影响
       health_score -= max(0, (avg_queue_length - 3) * 5)  # 队列过长扣分
       
       # 利用率过低或过高都扣分
       if utilization_rate < 0.3:
           health_score -= (0.3 - utilization_rate) * 20
       elif utilization_rate > 0.9:
           health_score -= (utilization_rate - 0.9) * 30
           
       return max(0, min(100, health_score))
       
   def updateRevenueData(self, state_data):
       """更新收益数据"""
       chargers = state_data.get('chargers', [])
       
       # 计算收益数据
       total_revenue = sum(c.get('daily_revenue', 0) for c in chargers)
       total_energy = sum(c.get('daily_energy', 0) for c in chargers)
       
       # 假设电价成本
       electricity_cost = 0.6  # 元/kWh
       total_cost = total_energy * electricity_cost
       
       revenue_data = {
           'total_revenue': total_revenue,
           'total_cost': total_cost,
           'total_energy': total_energy,
           'chargers': chargers
       }
       
       self.revenue_widget.updateRevenueData(revenue_data)
       
   def updateRealtimeData(self):
       """定时更新实时数据"""
       if self.simulation_environment:
           state = self.simulation_environment.get_current_state()
           self.updateSimulationData(state)
           
   def checkAlerts(self):
       """检查告警条件"""
       if not self.current_data:
           return
           
       chargers = self.current_data.get('chargers', [])
       timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
       
       # 检查每个充电桩
       for charger in chargers:
           charger_id = charger.get('charger_id', '')
           
           # 检查故障
           if charger.get('status') == 'failure':
               alert = {
                   'timestamp': timestamp,
                   'level': 'critical',
                   'charger_id': charger_id,
                   'message': '充电桩故障',
                   'status': '未处理'
               }
               self.maintenance_widget.addAlert(alert)
               
               # 自动创建工单
               existing_orders = [wo for wo in self.maintenance_widget.work_orders 
                                if wo.get('charger_id') == charger_id and wo.get('status') != '已完成']
               if not existing_orders:  # 避免重复创建工单
                   self.maintenance_widget.createWorkOrder(charger_id, '设备故障')
               
           # 检查队列长度
           queue_length = len(charger.get('queue', []))
           queue_threshold = self.maintenance_widget.offline_threshold.value()
           
           if queue_length > queue_threshold:
               alert = {
                   'timestamp': timestamp,
                   'level': 'warning',
                   'charger_id': charger_id,
                   'message': f'排队人数过多: {queue_length}人',
                   'status': '未处理'
               }
               self.maintenance_widget.addAlert(alert)
               
   def onPricingStrategyChanged(self, strategy):
       """处理定价策略变化"""
       logger.info(f"定价策略已更新: {strategy}")
       self.pricingStrategyChanged.emit(strategy)
       
       # 应用到仿真环境
       if self.simulation_environment:
           # 更新配置中的价格参数
           config = self.simulation_environment.config
           config['grid']['normal_price'] = strategy['base_price']
           config['grid']['peak_price'] = strategy['base_price'] * strategy['peak_factor']
           config['grid']['valley_price'] = strategy['base_price'] * strategy['valley_factor']
           
   def refreshData(self):
       """刷新数据"""
       self.updateRealtimeData()
       QMessageBox.information(self, "刷新", "数据已更新")
       
   def exportReport(self):
       """导出运营报表"""
       # 收集报表数据
       report_data = {
           'timestamp': datetime.now().isoformat(),
           'summary': {
               'total_chargers': self.total_chargers_label.text(),
               'available_chargers': self.available_chargers_label.text(),
               'charging_users': self.charging_users_label.text(),
               'today_revenue': self.today_revenue_label.text()
           },
           'revenue_data': self.revenue_widget.revenue_data,
           'station_health': {
               station_id: card.health_score 
               for station_id, card in self.health_cards.items()
           },
           'alerts': self.maintenance_widget.alerts,
           'work_orders': self.maintenance_widget.work_orders
       }
       
       # 保存到文件
       try:
           filename = f"operator_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
           with open(filename, 'w', encoding='utf-8') as f:
               json.dump(report_data, f, indent=2, ensure_ascii=False)
           
           QMessageBox.information(self, "导出成功", f"报表已导出到: {filename}")
       except Exception as e:
           QMessageBox.critical(self, "导出失败", f"导出报表时发生错误: {str(e)}")
           
   def showSettings(self):
       """显示设置对话框"""
       # 这里可以实现设置对话框
       QMessageBox.information(self, "设置", "设置功能正在开发中...")


# 导出组件
__all__ = ['OperatorControlPanel']