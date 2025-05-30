# operator_panel.py
import sys
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
import numpy as np
import pandas as pd
from collections import defaultdict

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QTabWidget,
    QLabel, QPushButton, QComboBox, QSpinBox, QDoubleSpinBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox,
    QTextEdit, QLineEdit, QCheckBox, QSlider, QProgressBar,
    QSplitter, QFrame, QScrollArea, QListWidget, QListWidgetItem,
    QMessageBox, QDialog, QDialogButtonBox, QFormLayout,
    QTreeWidget, QTreeWidgetItem, QMenu, QToolBar, QDateEdit
)
from PyQt6.QtCore import (
    Qt, QTimer, pyqtSignal, QThread, QDateTime, QDate, QTime,
    QPropertyAnimation, QEasingCurve, pyqtProperty, QPointF
)
from PyQt6.QtGui import (
    QFont, QPainter, QPen, QBrush, QColor, QLinearGradient,
    QIcon, QPixmap, QAction, QPalette, QPolygonF
)

try:
    import pyqtgraph as pg
    from pyqtgraph import PlotWidget
    HAS_PYQTGRAPH = True
except ImportError:
    HAS_PYQTGRAPH = False

from data_storage import operator_storage

logger = logging.getLogger(__name__)


class StationStatusCard(QFrame):
    """站点状态卡片 - 简化版"""
    
    clicked = pyqtSignal(str)  # 站点ID
    
    def __init__(self, station_id: str, station_name: str, parent=None):
        super().__init__(parent)
        self.station_id = station_id
        self.station_name = station_name
        self.setupUI()
        
    def setupUI(self):
        self.setFrameStyle(QFrame.Shape.Box)
        self.setFixedSize(200, 120)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # 站点名称
        self.name_label = QLabel(self.station_name)
        self.name_label.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        layout.addWidget(self.name_label)
        
        # 状态信息网格
        info_layout = QGridLayout()
        
        # 创建信息标签
        self.total_label = QLabel("总数: 0")
        self.available_label = QLabel("可用: 0")
        self.occupied_label = QLabel("使用: 0")
        self.queue_label = QLabel("排队: 0")
        
        info_layout.addWidget(self.total_label, 0, 0)
        info_layout.addWidget(self.available_label, 0, 1)
        info_layout.addWidget(self.occupied_label, 1, 0)
        info_layout.addWidget(self.queue_label, 1, 1)
        
        layout.addLayout(info_layout)
        
        # 利用率进度条
        self.utilization_bar = QProgressBar()
        self.utilization_bar.setMaximum(100)
        self.utilization_bar.setTextVisible(True)
        self.utilization_bar.setFormat("%p%")
        layout.addWidget(self.utilization_bar)
        
        self.updateStyle()
    
    def updateStatus(self, status_data: Dict):
        """更新站点状态"""
        total = status_data.get('total_chargers', 0)
        available = status_data.get('available', 0)
        occupied = status_data.get('occupied', 0)
        queue = status_data.get('total_queue', 0)
        utilization = status_data.get('avg_utilization', 0) * 100
        
        self.total_label.setText(f"总数: {total}")
        self.available_label.setText(f"可用: {available}")
        self.occupied_label.setText(f"使用: {occupied}")
        self.queue_label.setText(f"排队: {queue}")
        
        self.utilization_bar.setValue(int(utilization))
        self.updateStyle(utilization)
    
    def updateStyle(self, utilization: float = 0):
        """根据利用率更新样式"""
        if utilization > 80:
            color = "#ff4444"
            border_color = "#cc0000"
        elif utilization > 60:
            color = "#ff9944"
            border_color = "#cc6600"
        else:
            color = "#44ff44"
            border_color = "#00cc00"
        
        self.setStyleSheet(f"""
            StationStatusCard {{
                background: white;
                border: 2px solid {border_color};
                border-radius: 8px;
            }}
            StationStatusCard:hover {{
                background: #f0f0f0;
                border: 3px solid {border_color};
            }}
            QProgressBar::chunk {{
                background: {color};
            }}
        """)
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.station_id)
        super().mousePressEvent(event)


class RealtimeMonitorWidget(QWidget):
    """实时监控组件"""
    
    stationSelected = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.station_cards = {}
        self.setupUI()
        
    def setupUI(self):
        layout = QVBoxLayout(self)
        
        # 标题栏
        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel("实时监控"))
        
        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.clicked.connect(self.refreshData)
        header_layout.addWidget(self.refresh_btn)
        
        header_layout.addStretch()
        layout.addLayout(header_layout)
        
        # 站点卡片容器
        scroll_area = QScrollArea()
        scroll_widget = QWidget()
        self.cards_layout = QGridLayout(scroll_widget)
        scroll_area.setWidget(scroll_widget)
        scroll_area.setWidgetResizable(True)
        
        layout.addWidget(scroll_area)

    def updateStations(self, stations_data: Dict[str, Dict]):
        """更新站点显示"""
        # 清除现有卡片
        for card in self.station_cards.values():
            card.deleteLater()
        self.station_cards.clear()
        
        # 创建新卡片
        row, col = 0, 0
        for station_id, status in stations_data.items():
            card = StationStatusCard(station_id, station_id)
            card.clicked.connect(self.stationSelected)
            card.updateStatus(status)
            
            self.cards_layout.addWidget(card, row, col)
            self.station_cards[station_id] = card
            
            col += 1
            if col >= 3:  # 每行3个
                col = 0
                row += 1
    
    def refreshData(self):
        """刷新数据"""
        # 从数据库获取最新状态
        stations_status = operator_storage.get_latest_station_status()
        self.updateStations(stations_status)


class PricingControlWidget(QWidget):
    """定价控制组件 - 简化版"""
    
    pricingUpdated = pyqtSignal(dict)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUI()
        
    def setupUI(self):
        layout = QVBoxLayout(self)
        
        # 基础定价
        base_group = QGroupBox("基础定价")
        base_layout = QFormLayout(base_group)
        
        self.base_price_spin = QDoubleSpinBox()
        self.base_price_spin.setRange(0.1, 5.0)
        self.base_price_spin.setSingleStep(0.01)
        self.base_price_spin.setValue(0.85)
        self.base_price_spin.setSuffix(" 元/kWh")
        base_layout.addRow("基础电价:", self.base_price_spin)
        
        self.service_fee_spin = QSpinBox()
        self.service_fee_spin.setRange(0, 100)
        self.service_fee_spin.setValue(20)
        self.service_fee_spin.setSuffix(" %")
        base_layout.addRow("服务费率:", self.service_fee_spin)
        
        layout.addWidget(base_group)
        
        # 时段系数
        time_group = QGroupBox("时段系数")
        time_layout = QFormLayout(time_group)
        
        self.peak_factor = QDoubleSpinBox()
        self.peak_factor.setRange(0.5, 3.0)
        self.peak_factor.setValue(1.5)
        time_layout.addRow("峰时系数:", self.peak_factor)
        
        self.valley_factor = QDoubleSpinBox()
        self.valley_factor.setRange(0.3, 1.5)
        self.valley_factor.setValue(0.6)
        time_layout.addRow("谷时系数:", self.valley_factor)
        
        layout.addWidget(time_group)
        
        # 应用按钮
        self.apply_btn = QPushButton("应用定价策略")
        self.apply_btn.clicked.connect(self.applyPricing)
        layout.addWidget(self.apply_btn)
        
        layout.addStretch()
    
    def applyPricing(self):
        """应用定价策略"""
        pricing = {
            'base_price': self.base_price_spin.value(),
            'service_fee_rate': self.service_fee_spin.value() / 100,
            'peak_factor': self.peak_factor.value(),
            'valley_factor': self.valley_factor.value(),
            'normal_factor': 1.0
        }
        
        self.pricingUpdated.emit(pricing)
        QMessageBox.information(self, "成功", "定价策略已更新")


class FinancialAnalysisWidget(QWidget):
    """财务分析组件"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUI()
        
    def setupUI(self):
        layout = QVBoxLayout(self)
        
        # 时间范围选择
        time_layout = QHBoxLayout()
        time_layout.addWidget(QLabel("时间范围:"))
        
        self.start_date = QDateEdit()
        self.start_date.setCalendarPopup(True)
        self.start_date.setDate(QDate.currentDate().addDays(-7))
        time_layout.addWidget(self.start_date)
        
        time_layout.addWidget(QLabel("至"))
        
        self.end_date = QDateEdit()
        self.end_date.setCalendarPopup(True)
        self.end_date.setDate(QDate.currentDate())
        time_layout.addWidget(self.end_date)
        
        self.query_btn = QPushButton("查询")
        self.query_btn.clicked.connect(self.queryFinancialData)
        time_layout.addWidget(self.query_btn)
        
        time_layout.addStretch()
        layout.addLayout(time_layout)
        
        # 汇总卡片
        cards_layout = QHBoxLayout()
        
        self.revenue_card = self._createSummaryCard("总收入", "¥0.00")
        self.cost_card = self._createSummaryCard("总成本", "¥0.00")
        self.profit_card = self._createSummaryCard("净利润", "¥0.00")
        self.margin_card = self._createSummaryCard("利润率", "0.0%")
        
        cards_layout.addWidget(self.revenue_card)
        cards_layout.addWidget(self.cost_card)
        cards_layout.addWidget(self.profit_card)
        cards_layout.addWidget(self.margin_card)
        
        layout.addLayout(cards_layout)
        
        # 图表
        if HAS_PYQTGRAPH:
            self.chart = PlotWidget()
            self.chart.setBackground('w')
            self.chart.setLabel('left', '金额 (元)')
            self.chart.setLabel('bottom', '日期')
            self.chart.showGrid(x=True, y=True, alpha=0.3)
            self.chart.addLegend()
            layout.addWidget(self.chart)
        
        # 详细表格
        self.detail_table = QTableWidget()
        self.detail_table.setColumnCount(6)
        self.detail_table.setHorizontalHeaderLabels([
            "日期", "站点", "收入", "成本", "利润", "利润率"
        ])
        layout.addWidget(self.detail_table)
    
    def _createSummaryCard(self, title: str, value: str) -> QFrame:
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
        value_label.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        value_label.setObjectName(f"{title}_value")
        layout.addWidget(value_label)
        
        return card
    
    def queryFinancialData(self):
        """查询财务数据"""
        start = self.start_date.date().toString("yyyy-MM-dd")
        end = self.end_date.date().toString("yyyy-MM-dd")
        
        # 获取财务汇总
        df = operator_storage.get_financial_summary(start, end)
        
        if df.empty:
            QMessageBox.information(self, "提示", "该时间段没有数据")
            return
        
        # 更新汇总卡片
        total_revenue = df['total_revenue'].sum()
        total_cost = df['total_cost'].sum()
        total_profit = df['total_profit'].sum()
        profit_margin = (total_profit / total_revenue * 100) if total_revenue > 0 else 0
        
        self.revenue_card.findChild(QLabel, "总收入_value").setText(f"¥{total_revenue:,.2f}")
        self.cost_card.findChild(QLabel, "总成本_value").setText(f"¥{total_cost:,.2f}")
        self.profit_card.findChild(QLabel, "净利润_value").setText(f"¥{total_profit:,.2f}")
        self.margin_card.findChild(QLabel, "利润率_value").setText(f"{profit_margin:.1f}%")
        
        # 更新图表
        if HAS_PYQTGRAPH:
            self._updateChart(df)
        
        # 更新表格
        self._updateTable(df)
    
    def _updateChart(self, df: pd.DataFrame):
        """更新图表"""
        self.chart.clear()
        
        # 按日期分组
        daily_df = df.groupby('date').agg({
            'total_revenue': 'sum',
            'total_cost': 'sum',
            'total_profit': 'sum'
        }).reset_index()
        
        # 绘制曲线
        x = np.arange(len(daily_df))
        self.chart.plot(x, daily_df['total_revenue'], pen='b', name='收入', symbol='o')
        self.chart.plot(x, daily_df['total_cost'], pen='r', name='成本', symbol='s')
        self.chart.plot(x, daily_df['total_profit'], pen='g', name='利润', symbol='^')
        
        # 设置X轴标签
        labels = [(i, str(d)) for i, d in enumerate(daily_df['date'])]
        self.chart.getAxis('bottom').setTicks([labels])
    
    def _updateTable(self, df: pd.DataFrame):
        """更新表格"""
        self.detail_table.setRowCount(len(df))
        
        for row, record in df.iterrows():
            self.detail_table.setItem(row, 0, QTableWidgetItem(str(record['date'])))
            self.detail_table.setItem(row, 1, QTableWidgetItem(record['station_id']))
            self.detail_table.setItem(row, 2, QTableWidgetItem(f"{record['total_revenue']:.2f}"))
            self.detail_table.setItem(row, 3, QTableWidgetItem(f"{record['total_cost']:.2f}"))
            self.detail_table.setItem(row, 4, QTableWidgetItem(f"{record['total_profit']:.2f}"))
            
            margin = (record['total_profit'] / record['total_revenue'] * 100) if record['total_revenue'] > 0 else 0
            self.detail_table.setItem(row, 5, QTableWidgetItem(f"{margin:.1f}%"))


class DemandForecastWidget(QWidget):
    """需求预测组件"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_forecast = None
        self.setupUI()
        
    def setupUI(self):
        layout = QVBoxLayout(self)
        
        # 控制面板
        control_layout = QHBoxLayout()
        
        control_layout.addWidget(QLabel("站点:"))
        self.station_combo = QComboBox()
        control_layout.addWidget(self.station_combo)
        
        control_layout.addWidget(QLabel("预测天数:"))
        self.days_spin = QSpinBox()
        self.days_spin.setRange(1, 30)
        self.days_spin.setValue(7)
        control_layout.addWidget(self.days_spin)
        
        self.forecast_btn = QPushButton("生成预测")
        self.forecast_btn.clicked.connect(self.generateForecast)
        control_layout.addWidget(self.forecast_btn)
        
        control_layout.addStretch()
        layout.addLayout(control_layout)
        
        # 预测图表
        if HAS_PYQTGRAPH:
            self.chart = PlotWidget()
            self.chart.setBackground('w')
            self.chart.setLabel('left', '预测值')
            self.chart.setLabel('bottom', '时间')
            self.chart.showGrid(x=True, y=True, alpha=0.3)
            self.chart.addLegend()
            layout.addWidget(self.chart)
        
        # 建议面板
        self.suggestions_text = QTextEdit()
        self.suggestions_text.setReadOnly(True)
        self.suggestions_text.setMaximumHeight(150)
        layout.addWidget(self.suggestions_text)
    
    def updateStationList(self, stations: List[str]):
        """更新站点列表"""
        self.station_combo.clear()
        self.station_combo.addItems(stations)
    
    def generateForecast(self):
        """生成需求预测"""
        station_id = self.station_combo.currentText()
        days = self.days_spin.value()
        
        if not station_id:
            return
        
        # 生成预测数据
        forecast_data = self._performForecast(station_id, days)
        
        # 保存预测结果
        operator_storage.save_demand_forecast(forecast_data)
        
        # 更新显示
        self._updateDisplay(forecast_data)
        
        # 生成建议
        suggestions = self._generateSuggestions(forecast_data)
        self.suggestions_text.setText(suggestions)
    
    def _performForecast(self, station_id: str, days: int) -> List[Dict]:
        """执行预测算法"""
        # 获取历史数据
        performance = operator_storage.analyze_station_performance(station_id, 30)
        hourly_dist = performance.get('hourly_distribution', [])
        
        # 简单的预测模型
        forecast_data = []
        base_date = datetime.now().date()
        
        for day in range(days):
            forecast_date = base_date + timedelta(days=day + 1)
            
            for hour in range(24):
                # 基于历史平均值
                hour_data = next((h for h in hourly_dist if int(h['hour']) == hour), {})
                base_sessions = hour_data.get('sessions', 5)
                base_energy = hour_data.get('energy', 100)
                
                # 添加周期性和趋势
                weekday_factor = 0.8 if forecast_date.weekday() in [5, 6] else 1.0
                trend_factor = 1.02 ** day  # 2%日增长
                
                # 添加随机性
                random_factor = np.random.uniform(0.9, 1.1)
                
                predicted_sessions = int(base_sessions * weekday_factor * trend_factor * random_factor)
                predicted_energy = base_energy * weekday_factor * trend_factor * random_factor
                predicted_queue = max(0, predicted_sessions - 10) * 0.3  # 简单队列模型
                
                forecast_data.append({
                    'forecast_date': forecast_date.isoformat(),
                    'station_id': station_id,
                    'hour': hour,
                    'predicted_sessions': predicted_sessions,
                    'predicted_energy': predicted_energy,
                    'predicted_queue_length': predicted_queue,
                    'confidence_level': 0.75,
                    'model_version': 'simple_v1'
                })
        
        return forecast_data
    
    def _updateDisplay(self, forecast_data: List[Dict]):
        """更新预测显示"""
        if not HAS_PYQTGRAPH or not forecast_data:
            return
        
        self.chart.clear()
        
        # 准备数据
        hours = list(range(len(forecast_data)))
        sessions = [d['predicted_sessions'] for d in forecast_data]
        energy = [d['predicted_energy'] for d in forecast_data]
        queue = [d['predicted_queue_length'] for d in forecast_data]
        
        # 绘制曲线
        self.chart.plot(hours, sessions, pen='b', name='充电会话')
        
        # 创建第二个Y轴
        self.chart.plot(hours, energy, pen='g', name='充电量(kWh)')
        self.chart.plot(hours, queue, pen='r', name='排队长度')
    
    def _generateSuggestions(self, forecast_data: List[Dict]) -> str:
        """生成运营建议"""
        if not forecast_data:
            return "无预测数据"
        
        # 分析预测结果
        df = pd.DataFrame(forecast_data)
        
        # 计算峰值
        peak_hour = df.loc[df['predicted_sessions'].idxmax()]
        peak_queue = df['predicted_queue_length'].max()
        avg_sessions = df['predicted_sessions'].mean()
        
        suggestions = f"""预测分析结果：

    1. 需求峰值：
    - 时间：{peak_hour['forecast_date']} {peak_hour['hour']}:00
    - 预计充电会话：{peak_hour['predicted_sessions']}次
    - 最大排队长度：{peak_queue:.1f}人

    2. 平均需求：
    - 日均充电会话：{avg_sessions * 24:.0f}次
    - 预计总能耗：{df['predicted_energy'].sum():.0f} kWh

    3. 运营建议："""
        
        if peak_queue > 5:
            suggestions += "\n   - 建议增加充电桩数量或引导用户错峰充电"
        
        if avg_sessions > 20:
            suggestions += "\n   - 站点负载较高，考虑扩容或建设新站点"
        
        return suggestions


class AlertManagementWidget(QWidget):
    """告警管理组件"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUI()
        
    def setupUI(self):
        layout = QVBoxLayout(self)
        
        # 告警统计
        stats_layout = QHBoxLayout()
        
        self.critical_count = self._createAlertCounter("严重", "#ff4444")
        self.warning_count = self._createAlertCounter("警告", "#ff9944")
        self.info_count = self._createAlertCounter("信息", "#4444ff")
        
        stats_layout.addWidget(self.critical_count)
        stats_layout.addWidget(self.warning_count)
        stats_layout.addWidget(self.info_count)
        stats_layout.addStretch()
        
        layout.addLayout(stats_layout)
        
        # 告警列表
        self.alert_table = QTableWidget()
        self.alert_table.setColumnCount(6)
        self.alert_table.setHorizontalHeaderLabels([
            "时间", "严重程度", "站点", "充电桩", "描述", "操作"
        ])
        layout.addWidget(self.alert_table)
        
        # 定时刷新
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.refreshAlerts)
        self.refresh_timer.start(30000)  # 30秒刷新一次
    
    def _createAlertCounter(self, level: str, color: str) -> QFrame:
        """创建告警计数器"""
        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{
                background: white;
                border: 2px solid {color};
                border-radius: 8px;
                padding: 10px;
            }}
        """)
        
        layout = QVBoxLayout(frame)
        
        count_label = QLabel("0")
        count_label.setFont(QFont("Arial", 24, QFont.Weight.Bold))
        count_label.setStyleSheet(f"color: {color};")
        count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        count_label.setObjectName(f"{level}_count")
        layout.addWidget(count_label)
        
        level_label = QLabel(level)
        level_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(level_label)
        
        return frame
    
    def refreshAlerts(self):
        """刷新告警列表"""
        alerts = operator_storage.get_active_alerts()
        
        # 更新计数
        critical = sum(1 for a in alerts if a.get('severity') == 'critical')
        warning = sum(1 for a in alerts if a.get('severity') == 'warning')
        info = sum(1 for a in alerts if a.get('severity') == 'info')
        
        self.critical_count.findChild(QLabel, "严重_count").setText(str(critical))
        self.warning_count.findChild(QLabel, "警告_count").setText(str(warning))
        self.info_count.findChild(QLabel, "信息_count").setText(str(info))
        
        # 更新表格
        self.alert_table.setRowCount(len(alerts))
        
        for row, alert in enumerate(alerts):
            # 时间
            self.alert_table.setItem(row, 0, QTableWidgetItem(alert.get('timestamp', '')))
            
            # 严重程度
            severity = alert.get('severity', 'info')
            severity_item = QTableWidgetItem(severity)
            if severity == 'critical':
                severity_item.setBackground(QColor("#ff4444"))
                severity_item.setForeground(QColor("white"))
            elif severity == 'warning':
                severity_item.setBackground(QColor("#ff9944"))
            self.alert_table.setItem(row, 1, severity_item)
            
            # 站点和充电桩
            self.alert_table.setItem(row, 2, QTableWidgetItem(alert.get('station_id', '')))
            self.alert_table.setItem(row, 3, QTableWidgetItem(alert.get('charger_id', '')))
            self.alert_table.setItem(row, 4, QTableWidgetItem(alert.get('message', '')))
            
            # 操作按钮
            resolve_btn = QPushButton("处理")
            resolve_btn.clicked.connect(lambda checked, aid=alert['alert_id']: self.resolveAlert(aid))
            self.alert_table.setCellWidget(row, 5, resolve_btn)
    
    def resolveAlert(self, alert_id: str):
        """处理告警"""
        operator_storage.resolve_alert(alert_id, "operator", "已处理")
        self.refreshAlerts()
        QMessageBox.information(self, "成功", "告警已处理")
    
    def createChargerAlert(self, charger_id: str, station_id: str, alert_type: str, message: str):
        """创建充电桩告警"""
        alert_data = {
            'charger_id': charger_id,
            'station_id': station_id,
            'alert_type': alert_type,
            'severity': 'critical' if 'failure' in alert_type else 'warning',
            'message': message
        }
        
        operator_storage.create_alert(alert_data)
        self.refreshAlerts()


class OperatorControlPanel(QWidget):
    """运营商控制面板主组件 - 重构版"""
    
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
        
        # 创建选项卡
        self.tab_widget = QTabWidget()
        
        # 实时监控
        self.monitor_widget = RealtimeMonitorWidget()
        self.monitor_widget.stationSelected.connect(self.onStationSelected)
        self.tab_widget.addTab(self.monitor_widget, "📊 实时监控")
        
        # 定价管理
        self.pricing_widget = PricingControlWidget()
        self.pricing_widget.pricingUpdated.connect(self.onPricingUpdated)
        self.tab_widget.addTab(self.pricing_widget, "💰 定价管理")
        
        # 财务分析
        self.financial_widget = FinancialAnalysisWidget()
        self.tab_widget.addTab(self.financial_widget, "📈 财务分析")
        
        # 需求预测
        self.forecast_widget = DemandForecastWidget()
        self.tab_widget.addTab(self.forecast_widget, "🔮 需求预测")
        
        # 告警管理
        self.alert_widget = AlertManagementWidget()
        self.tab_widget.addTab(self.alert_widget, "🚨 告警管理")
        
        layout.addWidget(self.tab_widget)
        
    def _createToolbar(self):
        """创建工具栏"""
        toolbar = QToolBar()
        
        # 刷新
        refresh_action = QAction("🔄 刷新", self)
        refresh_action.triggered.connect(self.refreshAll)
        toolbar.addAction(refresh_action)
        
        toolbar.addSeparator()
        
        # 导出
        export_action = QAction("📊 导出报表", self)
        export_action.triggered.connect(self.exportReport)
        toolbar.addAction(export_action)
        
        # 扩容建议
        expansion_action = QAction("📈 扩容建议", self)
        expansion_action.triggered.connect(self.showExpansionRecommendations)
        toolbar.addAction(expansion_action)
        
        return toolbar
        
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
        
        # 保存实时快照
        chargers = state_data.get('chargers', [])
        timestamp = datetime.fromisoformat(state_data.get('timestamp', datetime.now().isoformat()))
        operator_storage.save_realtime_snapshot(chargers, timestamp)
        
        # 保存充电会话
        for charger in chargers:
            if charger.get('current_user') and 'charging_session' in charger:
                session = charger['charging_session']
                session['station_id'] = charger.get('location', 'unknown')
                operator_storage.save_charging_session(session)
        
        # 更新实时监控
        stations_status = self._aggregateStationStatus(chargers)
        self.monitor_widget.updateStations(stations_status)
        
        # 更新站点列表
        station_list = list(stations_status.keys())
        self.forecast_widget.updateStationList(station_list)
        
    def _aggregateStationStatus(self, chargers: List[Dict]) -> Dict[str, Dict]:
        """聚合站点状态"""
        stations = defaultdict(lambda: {
            'total_chargers': 0,
            'available': 0,
            'occupied': 0,
            'failed': 0,
            'total_queue': 0,
            'total_power': 0,
            'used_power': 0
        })
        
        for charger in chargers:
            station = charger.get('location', 'unknown')
            status = charger.get('status', 'unknown')
            
            stations[station]['total_chargers'] += 1
            
            if status == 'available':
                stations[station]['available'] += 1
            elif status == 'occupied':
                stations[station]['occupied'] += 1
                stations[station]['used_power'] += charger.get('max_power', 0)
            elif status == 'failure':
                stations[station]['failed'] += 1
            
            stations[station]['total_queue'] += len(charger.get('queue', []))
            stations[station]['total_power'] += charger.get('max_power', 0)
        
        # 计算利用率
        for station_data in stations.values():
            total = station_data['total_chargers']
            if total > 0:
                station_data['avg_utilization'] = station_data['occupied'] / total
            else:
                station_data['avg_utilization'] = 0
        
        return dict(stations)
        
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
        
        for charger in chargers:
            charger_id = charger.get('charger_id', '')
            station_id = charger.get('location', 'unknown')
            
            # 检查故障
            if charger.get('status') == 'failure':
                # 检查是否已有活跃告警
                active_alerts = operator_storage.get_active_alerts()
                existing = any(a.get('charger_id') == charger_id and 
                                a.get('alert_type') == 'charger_failure' 
                                for a in active_alerts)
                
                if not existing:
                    self.alert_widget.createChargerAlert(
                        charger_id, station_id, 'charger_failure',
                        f'充电桩 {charger_id} 发生故障'
                    )
                    
                    # 自动创建维护工单
                    order_data = {
                        'charger_id': charger_id,
                        'station_id': station_id,
                        'issue_type': 'failure',
                        'description': '充电桩故障，需要维修',
                        'priority': 'high'
                    }
                    operator_storage.create_maintenance_order(order_data)
            
            # 检查队列过长
            queue_length = len(charger.get('queue', []))
            if queue_length > 5:
                self.alert_widget.createChargerAlert(
                    charger_id, station_id, 'long_queue',
                    f'充电桩 {charger_id} 排队人数过多: {queue_length}人'
                )
    
    def onStationSelected(self, station_id: str):
        """处理站点选择"""
        logger.info(f"选中站点: {station_id}")
        # 可以显示站点详情对话框
        self.showStationDetails(station_id)
    
    def showStationDetails(self, station_id: str):
        """显示站点详情"""
        # 获取站点性能数据
        performance = operator_storage.analyze_station_performance(station_id, 30)
        
        dialog = QDialog(self)
        dialog.setWindowTitle(f"站点详情 - {station_id}")
        dialog.resize(600, 400)
        
        layout = QVBoxLayout(dialog)
        
        # 基础统计
        stats = performance.get('basic_stats', {})
        stats_text = f"""
        运营天数: {stats.get('operating_days', 0)}
        总充电会话: {stats.get('total_sessions', 0)}
        总充电量: {stats.get('total_energy', 0):.1f} kWh
        总收入: ¥{stats.get('total_revenue', 0):.2f}
        平均充电时长: {stats.get('avg_session_duration', 0):.1f} 分钟
        平均单价: ¥{stats.get('avg_price', 0):.2f}/kWh
        """
        
        stats_label = QLabel(stats_text)
        layout.addWidget(stats_label)
        
        # 关闭按钮
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(dialog.close)
        layout.addWidget(close_btn)
        
        dialog.exec()
    
    def onPricingUpdated(self, pricing: Dict):
        """处理定价更新"""
        logger.info(f"定价策略已更新: {pricing}")
        self.pricingStrategyChanged.emit(pricing)
        
        # 应用到仿真环境
        if self.simulation_environment:
            config = self.simulation_environment.config
            config['grid']['normal_price'] = pricing['base_price']
            config['grid']['peak_price'] = pricing['base_price'] * pricing['peak_factor']
            config['grid']['valley_price'] = pricing['base_price'] * pricing['valley_factor']
    
    def refreshAll(self):
        """刷新所有数据"""
        self.updateRealtimeData()
        self.alert_widget.refreshAlerts()
        QMessageBox.information(self, "刷新", "数据已更新")
    
    def exportReport(self):
        """导出运营报表"""
        # 选择时间范围
        dialog = QDialog(self)
        dialog.setWindowTitle("选择导出时间范围")
        
        layout = QFormLayout(dialog)
        
        start_date = QDateEdit()
        start_date.setCalendarPopup(True)
        start_date.setDate(QDate.currentDate().addDays(-30))
        layout.addRow("开始日期:", start_date)
        
        end_date = QDateEdit()
        end_date.setCalendarPopup(True)
        end_date.setDate(QDate.currentDate())
        layout.addRow("结束日期:", end_date)
        
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | 
                                    QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            start = start_date.date().toString("yyyy-MM-dd")
            end = end_date.date().toString("yyyy-MM-dd")
            
            # 生成报表
            report_data = self._generateReport(start, end)
            
            # 保存到文件
            filename = f"operator_report_{start}_{end}.json"
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(report_data, f, indent=2, ensure_ascii=False)
                
                QMessageBox.information(self, "导出成功", f"报表已导出到: {filename}")
            except Exception as e:
                QMessageBox.critical(self, "导出失败", f"导出报表时发生错误: {str(e)}")
    
    def _generateReport(self, start_date: str, end_date: str) -> Dict:
        """生成运营报表"""
        report = {
            'report_period': {
                'start': start_date,
                'end': end_date
            },
            'generated_at': datetime.now().isoformat(),
            'financial_summary': {},
            'operational_metrics': {},
            'station_performance': {},
            'maintenance_summary': {},
            'alerts_summary': {}
        }
        
        # 财务汇总
        financial_df = operator_storage.get_financial_summary(start_date, end_date)
        if not financial_df.empty:
            report['financial_summary'] = {
                'total_revenue': float(financial_df['total_revenue'].sum()),
                'total_cost': float(financial_df['total_cost'].sum()),
                'total_profit': float(financial_df['total_profit'].sum()),
                'total_sessions': int(financial_df['sessions_count'].sum()),
                'total_energy': float(financial_df['total_energy'].sum()),
                'avg_price_per_kwh': float(financial_df['avg_price'].mean())
            }
        
        # 站点性能
        stations_status = operator_storage.get_latest_station_status()
        for station_id in stations_status:
            performance = operator_storage.analyze_station_performance(station_id, 30)
            report['station_performance'][station_id] = performance
        
        # 维护汇总
        maintenance_df = operator_storage.get_maintenance_history(30)
        if not maintenance_df.empty:
            report['maintenance_summary'] = {
                'total_orders': len(maintenance_df),
                'completed_orders': len(maintenance_df[maintenance_df['status'] == 'completed']),
                'pending_orders': len(maintenance_df[maintenance_df['status'] == 'pending']),
                'total_cost': float(maintenance_df['cost'].sum()),
                'avg_repair_time': float(maintenance_df['duration_hours'].mean())
            }
        
        return report
    
    def showExpansionRecommendations(self):
        """显示扩容建议"""
        recommendations = operator_storage.get_expansion_recommendations()
        
        dialog = QDialog(self)
        dialog.setWindowTitle("扩容建议")
        dialog.resize(800, 600)
        
        layout = QVBoxLayout(dialog)
        
        # 建议表格
        table = QTableWidget()
        table.setColumnCount(6)
        table.setHorizontalHeaderLabels([
            "站点", "当前利用率", "平均排队", "建议类型", "建议增加", "优先级"
        ])
        
        table.setRowCount(len(recommendations))
        
        for row, rec in enumerate(recommendations):
            table.setItem(row, 0, QTableWidgetItem(rec['station_name']))
            table.setItem(row, 1, QTableWidgetItem(f"{rec['current_utilization']*100:.1f}%"))
            table.setItem(row, 2, QTableWidgetItem(f"{rec['avg_queue_length']:.1f}"))
            table.setItem(row, 3, QTableWidgetItem(rec['recommendation_type']))
            table.setItem(row, 4, QTableWidgetItem(f"+{rec['suggested_additional_chargers']}"))
            
            priority_item = QTableWidgetItem(rec['priority'])
            if rec['priority'] == 'high':
                priority_item.setBackground(QColor("#ff4444"))
                priority_item.setForeground(QColor("white"))
            table.setItem(row, 5, priority_item)
        
        layout.addWidget(table)
        
        # 关闭按钮
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(dialog.close)
        layout.addWidget(close_btn)
        
        dialog.exec()


    # 导出组件
    __all__ = ['OperatorControlPanel']