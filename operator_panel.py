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

# Default config, will be overwritten by __init__
config = {}


class StationStatusCard(QFrame):
    """站点状态卡片 - 简化版"""
    clicked = pyqtSignal(str)  # 站点ID

    def __init__(self, station_id: str, station_name: str, config: Dict, parent=None):
        super().__init__(parent)
        self.station_id = station_id
        self.station_name = station_name
        self.card_config = config  # Specific config for this card
        self.setupUI()
        
    def setupUI(self):
        self.setFrameStyle(QFrame.Shape.Box)
        width = self.card_config.get('width', 200)
        height = self.card_config.get('height', 120)
        self.setFixedSize(width, height)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # 站点名称
        self.name_label = QLabel(self.station_name)
        font_family = self.card_config.get('font_family', 'Arial')
        font_size = self.card_config.get('font_size', 11)
        # QFont.Weight.Bold is typically 75. Some systems might use other values.
        # Ensuring it's an int.
        font_weight_val = int(self.card_config.get('font_weight_bold_value', 75)) 
        self.name_label.setFont(QFont(font_family, font_size, font_weight_val))
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
        
        self.updateStyle() # Initial style setup

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
        util_high = self.card_config.get('utilization_threshold_high', 80)
        util_medium = self.card_config.get('utilization_threshold_medium', 60)

        if utilization > util_high:
            color = self.card_config.get('utilization_color_high', "#ff4444")
            border_color = self.card_config.get('utilization_border_high', "#cc0000")
        elif utilization > util_medium:
            color = self.card_config.get('utilization_color_medium', "#ff9944")
            border_color = self.card_config.get('utilization_border_medium', "#cc6600")
        else:
            color = self.card_config.get('utilization_color_low', "#44ff44")
            border_color = self.card_config.get('utilization_border_low', "#00cc00")
            
        border_radius = self.card_config.get('border_radius', 8)
        hover_bg_color = self.card_config.get('hover_background_color', "#f0f0f0")

        self.setStyleSheet(f"""
            StationStatusCard {{
                background: white;
                border: 2px solid {border_color};
                border-radius: {border_radius}px;
            }}
            StationStatusCard:hover {{
                background: {hover_bg_color};
                border: 3px solid {border_color};
            }}
            QProgressBar::chunk {{
                background: {color};
                border-radius: {max(0, border_radius - 2)}px; /* Ensure progress bar chunk radius is smaller */
            }}
        """)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.station_id)
        super().mousePressEvent(event)


class RealtimeMonitorWidget(QWidget):
    """实时监控组件"""
    
    stationSelected = pyqtSignal(str)

    def __init__(self, config: Dict, parent=None):
        super().__init__(parent)
        self.op_config = config # This is the operator_panel config section
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
        station_card_config = self.op_config.get('station_status_card', {})
        card_columns = self.op_config.get('realtime_monitor_widget', {}).get('card_columns', 3)
        
        row, col = 0, 0
        for station_id, status in stations_data.items():
            card = StationStatusCard(station_id, station_id, station_card_config)
            card.clicked.connect(self.stationSelected)
            card.updateStatus(status)
            
            self.cards_layout.addWidget(card, row, col)
            self.station_cards[station_id] = card
            
            col += 1
            if col >= card_columns:
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

    def __init__(self, app_config: Dict, parent=None): # Expects the full application config
        super().__init__(parent)
        self.app_config = app_config
        self.pricing_config = self.app_config.get('operator_panel', {}).get('pricing_control_widget', {})
        self.grid_config_main_app = self.app_config.get('grid', {})

        self.setupUI()
        
    def setupUI(self):
        layout = QVBoxLayout(self)
        
        # 基础定价
        base_group = QGroupBox("基础定价")
        base_layout = QFormLayout(base_group)
        
        self.base_price_spin = QDoubleSpinBox()
        self.base_price_spin.setRange(
            self.pricing_config.get('base_price_min', 0.1),
            self.pricing_config.get('base_price_max', 5.0)
        )
        self.base_price_spin.setSingleStep(0.01)
        # Try to use grid_config if available, else pricing_config default
        base_price_default = self.grid_config_main_app.get('normal_price', self.pricing_config.get('base_price_default', 0.85))
        self.base_price_spin.setValue(base_price_default)
        self.base_price_spin.setSuffix(" 元/kWh")
        base_layout.addRow("基础电价:", self.base_price_spin)
        
        self.service_fee_spin = QSpinBox()
        self.service_fee_spin.setRange(
            self.pricing_config.get('service_fee_min', 0),
            self.pricing_config.get('service_fee_max', 100)
        )
        self.service_fee_spin.setValue(self.pricing_config.get('service_fee_default', 20))
        self.service_fee_spin.setSuffix(" %")
        base_layout.addRow("服务费率:", self.service_fee_spin)
        
        layout.addWidget(base_group)
        
        # 时段系数
        time_group = QGroupBox("时段系数")
        time_layout = QFormLayout(time_group)
        
        self.peak_factor = QDoubleSpinBox()
        self.peak_factor.setRange(
            self.pricing_config.get('peak_factor_min', 0.5),
            self.pricing_config.get('peak_factor_max', 3.0)
        )
        # Default for peak_factor
        normal_price = self.grid_config_main_app.get('normal_price')
        peak_price = self.grid_config_main_app.get('peak_price')
        peak_factor_default = self.pricing_config.get('peak_factor_default', 1.5)
        if normal_price and peak_price and normal_price > 0:
            peak_factor_default = peak_price / normal_price
        self.peak_factor.setValue(peak_factor_default)
        time_layout.addRow("峰时系数:", self.peak_factor)
        
        self.valley_factor = QDoubleSpinBox()
        self.valley_factor.setRange(
            self.pricing_config.get('valley_factor_min', 0.3),
            self.pricing_config.get('valley_factor_max', 1.5)
        )
        # Default for valley_factor
        valley_price = self.grid_config_main_app.get('valley_price')
        valley_factor_default = self.pricing_config.get('valley_factor_default', 0.6)
        if normal_price and valley_price and normal_price > 0:
            valley_factor_default = valley_price / normal_price
        self.valley_factor.setValue(valley_factor_default)
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
    def __init__(self, op_panel_config: Dict, parent=None):
        super().__init__(parent)
        self.op_panel_config = op_panel_config
        self.financial_config = self.op_panel_config.get('financial_analysis', {})
        self.setupUI()
        
    def setupUI(self):
        layout = QVBoxLayout(self)
        
        # 时间范围选择 (保持不变)
        time_layout = QHBoxLayout()
        # ... (code for time range selection remains the same)
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
        
        # 汇总卡片 (保持不变)
        cards_layout = QHBoxLayout()
        # ... (code for summary cards remains the same)
        self.revenue_card = self._createSummaryCard("总收入", "¥0.00")
        self.cost_card = self._createSummaryCard("总成本", "¥0.00")
        self.profit_card = self._createSummaryCard("净利润", "¥0.00")
        self.margin_card = self._createSummaryCard("利润率", "0.0%")
        cards_layout.addWidget(self.revenue_card)
        cards_layout.addWidget(self.cost_card)
        cards_layout.addWidget(self.profit_card)
        cards_layout.addWidget(self.margin_card)
        layout.addLayout(cards_layout)
        
        # 图表 (保持不变)
        if HAS_PYQTGRAPH:
            # ... (code for chart setup remains the same) ...
            self.chart_widget = pg.GraphicsLayoutWidget()
            self.chart = self.chart_widget.addPlot(row=0, col=0, axisItems={'bottom': pg.DateAxisItem()})
            chart_bg = self.financial_config.get('chart_background', 'w')
            grid_alpha = self.financial_config.get('grid_alpha', 0.3)
            view_box = self.chart.getViewBox()
            view_box.setBackgroundColor(QColor(chart_bg))
            self.chart.setLabel('left', '金额 (千元)')
            self.chart.setLabel('bottom', '日期')
            self.chart.showGrid(x=True, y=True, alpha=grid_alpha)
            self.chart.addLegend()
            layout.addWidget(self.chart_widget)
        
        # --- START OF MODIFICATION ---
        # 替换详细表格为站点盈利能力排行榜
        leaderboard_group = QGroupBox("站点盈利能力排行榜")
        leaderboard_layout = QVBoxLayout(leaderboard_group)
        
        self.leaderboard_table = QTableWidget()
        self.leaderboard_table.setColumnCount(6)
        self.leaderboard_table.setHorizontalHeaderLabels([
            "排名", "站点", "总利润 (¥)", "利润率 (%)", "总会话数", "平均客单价 (¥)"
        ])
        # 让表格可排序
        self.leaderboard_table.setSortingEnabled(True)
        # 优化列宽
        self.leaderboard_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.leaderboard_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents) # 排名列
        self.leaderboard_table.verticalHeader().setVisible(False)
        
        leaderboard_layout.addWidget(self.leaderboard_table)
        layout.addWidget(leaderboard_group)
        # --- END OF MODIFICATION ---

    # _createSummaryCard 方法保持不变
    def _createSummaryCard(self, title: str, value: str) -> QFrame:
        # ... (existing code is correct) ...
        card = QFrame(); card.setFrameStyle(QFrame.Shape.Box); card.setStyleSheet("QFrame { background: white; border: 1px solid #ddd; border-radius: 8px; padding: 15px; }"); layout = QVBoxLayout(card); title_label = QLabel(title); title_label.setStyleSheet("color: #666; font-size: 12px;"); layout.addWidget(title_label); value_label = QLabel(value); font_family = "Arial"; font_size = self.financial_config.get('summary_card_font_size', 16); font_weight_val = int(self.financial_config.get('summary_card_font_weight_bold_value', 75)); value_label.setFont(QFont(font_family, font_size, font_weight_val)); value_label.setObjectName(f"{title}_value"); layout.addWidget(value_label); return card
        
    def queryFinancialData(self):
        """查询财务数据"""
        start = self.start_date.date().toString("yyyy-MM-dd")
        end = self.end_date.date().toString("yyyy-MM-dd")
        
        df = operator_storage.get_financial_summary(start, end)
        
        if df.empty:
            QMessageBox.information(self, "提示", "该时间段没有数据")
            # 清空旧数据
            if HAS_PYQTGRAPH: self.chart.clear()
            self.leaderboard_table.setRowCount(0)
            return
        
        # 更新汇总卡片 (保持不变)
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
        
        # --- START OF MODIFICATION ---
        # 更新排行榜，而不是旧的详细表格
        self._updateLeaderboard(df)
        # --- END OF MODIFICATION ---

    # _updateChart 方法保持不变
    def _updateChart(self, df: pd.DataFrame):
        # ... (existing code is correct) ...
        if not HAS_PYQTGRAPH: return
        self.chart.clear()
        try: df['datetime_dt'] = pd.to_datetime(df['datetime_hour'])
        except Exception as e: logger.error(f"Failed to convert 'datetime_hour' to datetime: {e}"); return
        hourly_df = df.groupby('datetime_dt').agg({'total_revenue': 'sum', 'total_cost': 'sum', 'total_profit': 'sum'}).reset_index()
        if hourly_df.empty: return
        x_timestamps = hourly_df['datetime_dt'].apply(lambda x: x.timestamp()).values
        y_revenue_k = hourly_df['total_revenue'].values / 1000; y_cost_k = hourly_df['total_cost'].values / 1000; y_profit_k = hourly_df['total_profit'].values / 1000
        self.chart.setLabel('left', '金额 (千元)')
        self.chart.setAxisItems({'bottom': pg.DateAxisItem()})
        self.chart.plot(x_timestamps, y_revenue_k, pen='b', name='收入(k¥)', symbol='o', connect='finite')
        self.chart.plot(x_timestamps, y_cost_k, pen='r', name='成本(k¥)', symbol='s', connect='finite')
        self.chart.plot(x_timestamps, y_profit_k, pen='g', name='利润(k¥)', symbol='t', connect='finite')


    # --- START OF MODIFICATION ---

    def _updateLeaderboard(self, df: pd.DataFrame):
        """更新站点盈利能力排行榜"""
        
        # --- START OF FIX & DEBUGGING ---

        logger.debug(f"Updating leaderboard with {len(df)} hourly records.")
        if df.empty:
            self.leaderboard_table.setRowCount(0)
            logger.warning("Leaderboard update skipped: input DataFrame is empty.")
            return

        # 1. 按站点聚合数据
        try:
            station_summary = df.groupby('station_id').agg(
                total_profit=('total_profit', 'sum'),
                total_revenue=('total_revenue', 'sum'),
                total_cost=('total_cost', 'sum'),
                sessions_count=('sessions_count', 'sum')
            ).reset_index()
            logger.debug(f"Aggregated station summary:\n{station_summary}")
        except Exception as e:
            logger.error(f"Error during station summary aggregation: {e}")
            self.leaderboard_table.setRowCount(0)
            return

        # 2. 计算衍生指标
        if station_summary.empty:
            self.leaderboard_table.setRowCount(0)
            logger.warning("Leaderboard update skipped: station summary is empty after aggregation.")
            return
            
        station_summary['profit_margin'] = station_summary.apply(
            lambda row: (row['total_profit'] / row['total_revenue'] * 100) if row['total_revenue'] > 0 else 0,
            axis=1
        )
        station_summary['avg_revenue_per_session'] = station_summary.apply(
            lambda row: (row['total_revenue'] / row['sessions_count']) if row['sessions_count'] > 0 else 0,
            axis=1
        )

        # 3. 按总利润降序排序
        leaderboard_df = station_summary.sort_values(by='total_profit', ascending=False)
        # 使用 reset_index(drop=True) 来确保索引是连续的，便于后面循环
        leaderboard_df = leaderboard_df.reset_index(drop=True)
        leaderboard_df['rank'] = leaderboard_df.index + 1

        # 4. 填充表格
        # 在填充前先禁用排序，填充完再启用，这是标准做法，可以提高性能
        self.leaderboard_table.setSortingEnabled(False)
        self.leaderboard_table.setRowCount(len(leaderboard_df))
        
        logger.debug(f"Populating leaderboard table with {len(leaderboard_df)} rows.")
        
        for index, data in leaderboard_df.iterrows():
            row = index # 现在 index 就是行号
            
            # 强制将 numpy 类型转换为 python 内置类型，增加兼容性
            rank_val = int(data['rank'])
            profit_val = float(data['total_profit'])
            margin_val = float(data['profit_margin'])
            sessions_val = int(data['sessions_count'])
            arpu_val = float(data['avg_revenue_per_session'])
            station_id_val = str(data['station_id'])

            # 创建 TableWidgetItem
            rank_item = QTableWidgetItem()
            station_item = QTableWidgetItem(station_id_val)
            profit_item = QTableWidgetItem()
            margin_item = QTableWidgetItem()
            sessions_item = QTableWidgetItem()
            arpu_item = QTableWidgetItem()

            # 设置显示内容 (DisplayRole)
            rank_item.setData(Qt.ItemDataRole.DisplayRole, f"#{rank_val}")
            profit_item.setData(Qt.ItemDataRole.DisplayRole, f"{profit_val:,.2f}")
            margin_item.setData(Qt.ItemDataRole.DisplayRole, f"{margin_val:.1f}%")
            sessions_item.setData(Qt.ItemDataRole.DisplayRole, f"{sessions_val}")
            arpu_item.setData(Qt.ItemDataRole.DisplayRole, f"{arpu_val:.2f}")

            # 设置排序用的原始数值 (UserRole)
            rank_item.setData(Qt.ItemDataRole.UserRole, rank_val)
            profit_item.setData(Qt.ItemDataRole.UserRole, profit_val)
            margin_item.setData(Qt.ItemDataRole.UserRole, margin_val)
            sessions_item.setData(Qt.ItemDataRole.UserRole, sessions_val)
            arpu_item.setData(Qt.ItemDataRole.UserRole, arpu_val)

            # 根据利润正负设置颜色
            if profit_val < 0:
                profit_item.setForeground(QColor('red'))
            
            self.leaderboard_table.setItem(row, 0, rank_item)
            self.leaderboard_table.setItem(row, 1, station_item)
            self.leaderboard_table.setItem(row, 2, profit_item)
            self.leaderboard_table.setItem(row, 3, margin_item)
            self.leaderboard_table.setItem(row, 4, sessions_item)
            self.leaderboard_table.setItem(row, 5, arpu_item)
        
        # 填充完毕后，重新启用排序并应用默认排序
        self.leaderboard_table.setSortingEnabled(True)
        self.leaderboard_table.sortItems(2, Qt.SortOrder.DescendingOrder)

# In operator_panel.py

# ... (imports and other classes remain the same) ...

class DemandForecastWidget(QWidget):
    """需求预测组件 (真实数据驱动版)"""
    def __init__(self, op_panel_config: Dict, parent=None):
        super().__init__(parent)
        self.demand_forecast_config = op_panel_config.get('demand_forecast', {})
        self.current_forecast_df = None
        self.setupUI()
        
    def setupUI(self):
        # UI 布局基本保持不变
        layout = QVBoxLayout(self)
        control_layout = QHBoxLayout()
        control_layout.addWidget(QLabel("站点:"))
        self.station_combo = QComboBox()
        control_layout.addWidget(self.station_combo)
        control_layout.addWidget(QLabel("预测未来天数:"))
        self.days_spin = QSpinBox()
        self.days_spin.setRange(1, 30)
        self.days_spin.setValue(self.demand_forecast_config.get('default_forecast_days', 7))
        control_layout.addWidget(self.days_spin)
        self.forecast_btn = QPushButton("生成预测")
        self.forecast_btn.clicked.connect(self.generateForecast)
        control_layout.addWidget(self.forecast_btn)
        control_layout.addStretch()
        layout.addLayout(control_layout)
        
        if HAS_PYQTGRAPH:
            self.chart = PlotWidget()
            self.chart.setBackground('w')
            self.chart.setLabel('left', '预测充电会话数')
            self.chart.setLabel('bottom', '日期和时间')
            self.chart.showGrid(x=True, y=True, alpha=0.3)
            self.chart.addLegend()
            layout.addWidget(self.chart)
        
        self.suggestions_text = QTextEdit()
        self.suggestions_text.setReadOnly(True)
        self.suggestions_text.setMaximumHeight(150)
        layout.addWidget(self.suggestions_text)

    def updateStationList(self, stations: List[str]):
        current_selection = self.station_combo.currentText()
        self.station_combo.clear()
        self.station_combo.addItems(stations)
        if current_selection in stations:
            self.station_combo.setCurrentText(current_selection)

    def generateForecast(self):
        station_id = self.station_combo.currentText()
        days_to_forecast = self.days_spin.value()
        
        if not station_id:
            QMessageBox.warning(self, "提示", "请先选择一个站点。")
            return
        
        # 1. 获取历史数据模式
        historical_patterns = operator_storage.get_historical_demand_patterns(station_id)
        
        if historical_patterns["hourly_avg"].empty:
            QMessageBox.information(self, "提示", f"站点 {station_id} 没有足够的历史数据来进行预测。")
            self.chart.clear()
            self.suggestions_text.setText("无可用数据。")
            return

        # 2. 执行预测
        forecast_data = self._performForecast(historical_patterns, days_to_forecast)
        self.current_forecast_df = pd.DataFrame(forecast_data)
        
        # 3. 更新显示
        self._updateDisplay()
        self._updateSuggestions()
        
        # 4. (可选) 保存预测结果
        # operator_storage.save_demand_forecast(forecast_data)

    def _performForecast(self, patterns: Dict, days: int) -> List[Dict]:
        """基于历史模式执行预测 (增强版)"""
        hourly_avg_df = patterns["hourly_avg"]
        daily_trend = patterns["daily_trend"] # 每日会话数的平均增长量

        if hourly_avg_df.empty:
            logger.warning("无法进行预测，因为历史小时模式数据为空。")
            return []

        # --- START OF FIX: 使用更稳健的预测模型 ---

        # 1. 计算稳健的基准和小时模式系数
        # 计算历史总的小时平均会话数
        total_avg_sessions_per_hour = hourly_avg_df['sessions'].mean()
        if total_avg_sessions_per_hour == 0:
            logger.warning("历史平均会话数为0，无法计算模式系数。")
            return []
            
        # 计算每个(星期几, 小时)的模式系数
        # 系数 = (该时段的平均会话数 / 总的平均会话数)
        hourly_avg_df['pattern_coeff'] = hourly_avg_df['sessions'] / total_avg_sessions_per_hour
        
        # 将模式系数存入字典以便快速查找
        patterns_dict = {(row.weekday, row.hour): row.pattern_coeff for _, row in hourly_avg_df.iterrows()}

        # 2. 计算用于外推的基准日均会话数
        # 使用最近7天的日均会话数作为更贴近当前的基准
        recent_history = operator_storage.get_financial_summary(
            (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d'),
            datetime.now().strftime('%Y-%m-%d')
        )
        if not recent_history.empty:
            # 计算每日总会话数
            daily_sessions = recent_history.groupby('datetime_hour')['sessions_count'].sum()
            # 使用最近的日均值作为预测的起点
            base_daily_sessions = daily_sessions.mean() * 24 # 乘以24小时
        else:
            # 如果最近7天没数据，就用所有历史数据的平均值
            base_daily_sessions = total_avg_sessions_per_hour * 24

        logger.info(f"预测模型基准: 日均会话数={base_daily_sessions:.2f}, 日增长趋势={daily_trend:.2f}")

        # 3. 生成预测
        forecast_results = []
        start_date = datetime.now().date()

        for i in range(days):
            current_date = start_date + timedelta(days=i + 1)
            
            # 预测当天的日均会话数 = 基准 + 趋势累加
            predicted_daily_avg = base_daily_sessions + (i + 1) * daily_trend
            
            # 星期几 (SQLite: 0=周日, Python: 0=周一)
            weekday_sqlite = (current_date.weekday() + 1) % 7 

            for hour in range(24):
                # 获取该小时的模式系数，如果历史上没有，则使用1.0（即平均水平）
                pattern_coeff = patterns_dict.get((weekday_sqlite, hour), 1.0)
                
                # 预测该小时的会话数 = (预测日均/24) * 模式系数
                predicted_sessions = (predicted_daily_avg / 24) * pattern_coeff
                
                # 添加一些随机性
                predicted_sessions *= np.random.uniform(0.9, 1.1)

                forecast_results.append({
                    "datetime": datetime.combine(current_date, datetime.min.time()) + timedelta(hours=hour),
                    "predicted_sessions": max(0, predicted_sessions)
                })
        
        return forecast_results
    def _updateDisplay(self):
        """更新预测图表显示"""
        if not HAS_PYQTGRAPH or self.current_forecast_df is None or self.current_forecast_df.empty:
            self.chart.clear()
            return
        
        self.chart.clear()
        
        # 使用时间戳作为X轴
        x_timestamps = self.current_forecast_df['datetime'].apply(lambda x: x.timestamp()).values
        y_sessions = self.current_forecast_df['predicted_sessions'].values
        
        # 设置X轴为日期模式
        self.chart.setAxisItems({'bottom': pg.DateAxisItem()})
        
        self.chart.plot(x_timestamps, y_sessions, pen='b', name='预测充电会话数')
        self.chart.getAxis('bottom').setLabel("日期和时间")

    def _updateSuggestions(self):
        """基于预测结果生成运营建议"""
        if self.current_forecast_df is None or self.current_forecast_df.empty:
            self.suggestions_text.setText("无预测数据。")
            return
            
        df = self.current_forecast_df
        
        peak_session = df.loc[df['predicted_sessions'].idxmax()]
        peak_time = peak_session['datetime']
        peak_value = peak_session['predicted_sessions']
        
        avg_sessions_per_hour = df['predicted_sessions'].mean()
        
        suggestions = f"#### 预测分析与运营建议 ####\n\n"
        suggestions += f"**1. 需求高峰预测:**\n"
        suggestions += f"   - **高峰时段:** 预计在 **{peak_time.strftime('%Y-%m-%d %A, %H:%M')}** 左右出现。\n"
        suggestions += f"   - **峰值需求:** 预计达到约 **{peak_value:.1f}** 次充电会话/小时。\n\n"
        
        suggestions += f"**2. 整体需求水平:**\n"
        suggestions += f"   - **平均需求:** 每小时约 **{avg_sessions_per_hour:.1f}** 次充电会话。\n\n"
        
        suggestions += f"**3. 运营建议:**\n"
        
        # 建议逻辑
        if peak_value > avg_sessions_per_hour * 2 and peak_value > 10:
            suggestions += f"   - **[高优先级]** 针对 **{peak_time.strftime('%A')}** 的高峰时段，考虑增加员工排班或准备应急预案。\n"
        
        # 假设一个站点的服务能力上限是每小时15个会话
        if peak_value > 15:
            suggestions += f"   - **[资源警告]** 高峰需求（{peak_value:.1f}次/小时）可能超出服务能力，有排队风险。建议在高峰期前通过App推送优惠，引导用户错峰充电。\n"
        
        if avg_sessions_per_hour < 2:
            suggestions += f"   - **[营销机会]** 站点整体需求较低。可以考虑在该站点推出限时折扣、会员活动等营销策略以提升利用率。\n"
        else:
            suggestions += f"   - **[常规运营]** 站点需求平稳，请保持常规运营和服务水平。\n"

        self.suggestions_text.setMarkdown(suggestions)

class FailureSimulationWidget(QWidget):
    """故障注入与压力测试面板，带影响分析"""
    injectFailure = pyqtSignal(str, str)
    injectDemandSpike = pyqtSignal(int, int)
    # 新增信号，请求主窗口在下一步更新后回调
    requestImpactAnalysis = pyqtSignal()

    def __init__(self, op_panel_config: Dict, simulation_environment=None, parent=None):
        super().__init__(parent)
        self.op_panel_config = op_panel_config
        self.charger_list = []
        self.station_list = []
        self.pre_injection_snapshot = None # 存储注入前快照
        self.simulation_environment = simulation_environment
        self.setupUI()

    def setupUI(self):
        main_layout = QHBoxLayout(self)
        main_layout.setSpacing(20)

        # 左侧：操作区
        action_widget = QWidget()
        action_layout = QVBoxLayout(action_widget)

        failure_group = QGroupBox("故障注入模拟")
        failure_layout = QFormLayout(failure_group)
        self.charger_combo = QComboBox()
        failure_layout.addRow("选择充电桩:", self.charger_combo)
        inject_charger_btn = QPushButton("模拟单桩故障")
        inject_charger_btn.clicked.connect(self.simulate_charger_failure)
        failure_layout.addRow(inject_charger_btn)
        self.station_combo = QComboBox()
        failure_layout.addRow("选择充电站:", self.station_combo)
        inject_station_btn = QPushButton("模拟区域停电")
        inject_station_btn.clicked.connect(self.simulate_station_outage)
        failure_layout.addRow(inject_station_btn)
        action_layout.addWidget(failure_group)

        demand_group = QGroupBox("需求冲击模拟")
        demand_layout = QFormLayout(demand_group)
        self.spike_users_spin = QSpinBox()
        self.spike_users_spin.setRange(1, 100)
        self.spike_users_spin.setValue(10)
        demand_layout.addRow("额外需求用户数:", self.spike_users_spin)
        self.spike_soc_spin = QSpinBox()
        self.spike_soc_spin.setRange(10, 80)
        self.spike_soc_spin.setValue(40)
        self.spike_soc_spin.setSuffix("%")
        demand_layout.addRow("将他们的SOC设置为低于:", self.spike_soc_spin)
        inject_demand_btn = QPushButton("注入瞬时充电需求")
        inject_demand_btn.clicked.connect(self.simulate_demand_spike)
        demand_layout.addRow(inject_demand_btn)
        action_layout.addWidget(demand_group)
        action_layout.addStretch()

        main_layout.addWidget(action_widget, 1)

        # --- START OF MODIFICATION ---
        # 右侧：影响分析区
        impact_group = QGroupBox("影响分析")
        self.impact_layout = QVBoxLayout(impact_group)
        
        self.impact_title = QLabel("请先执行一次模拟操作")
        self.impact_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.impact_title.setStyleSheet("font-style: italic; color: #888;")
        
        self.impact_table = QTableWidget()
        self.impact_table.setColumnCount(3)
        self.impact_table.setHorizontalHeaderLabels(["指标", "操作前", "操作后"])
        self.impact_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.impact_table.verticalHeader().setVisible(False)
        self.impact_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        
        self.impact_layout.addWidget(self.impact_title)
        self.impact_layout.addWidget(self.impact_table)
        self.impact_table.hide() # 默认隐藏

        main_layout.addWidget(impact_group, 2)
        # --- END OF MODIFICATION ---

    def _capture_snapshot(self, state):
        """从当前状态中捕获关键指标"""
        if not state: return None
        users = state.get('users', [])
        chargers = state.get('chargers', [])
        total_users = len(users) if users else 1
        return {
            "等待用户数": sum(1 for u in users if u.get('status') == 'waiting'),
            "平均SOC (%)": np.mean([u.get('soc', 0) for u in users]) if users else 0,
            "可用充电桩数": sum(1 for c in chargers if c.get('status') == 'available'),
            "总排队长度": sum(len(c.get('queue', [])) for c in chargers)
        }

    def _trigger_injection(self):
        """执行注入前的通用逻辑"""
        if not self.simulation_environment:
            QMessageBox.critical(self, "错误", "仿真环境未连接，无法执行操作。")
            return False
            
        current_state = self.simulation_environment.get_current_state()
        self.pre_injection_snapshot = self._capture_snapshot(current_state)
        self.requestImpactAnalysis.emit()
        return True

    def simulate_charger_failure(self):
        charger_id = self.charger_combo.currentText()
        if not charger_id: return
        if self._trigger_injection():
            self.injectFailure.emit("charger", charger_id)
            self.impact_title.setText(f"分析中：模拟充电桩 {charger_id} 故障...")
            self.impact_table.hide()

    def simulate_station_outage(self):
        station_id = self.station_combo.currentText()
        if not station_id: return
        if self._trigger_injection():
            self.injectFailure.emit("station", station_id)
            self.impact_title.setText(f"分析中：模拟站点 {station_id} 停电...")
            self.impact_table.hide()
        
    def simulate_demand_spike(self):
        if self._trigger_injection():
            num_users = self.spike_users_spin.value()
            soc_threshold = self.spike_soc_spin.value()
            self.injectDemandSpike.emit(num_users, soc_threshold)
            self.impact_title.setText(f"分析中：注入 {num_users} 个紧急充电需求...")
            self.impact_table.hide()
            
    def analyze_impact(self, post_state):
        """在注入操作后的一步，对比快照并显示结果"""
        if not self.pre_injection_snapshot:
            logger.warning("无法分析影响：缺少操作前快照。")
            return
            
        post_snapshot = self._capture_snapshot(post_state)
        if not post_snapshot:
            logger.warning("无法分析影响：操作后状态无效。")
            return

        self.impact_title.setText("操作影响分析结果:")
        self.impact_table.setRowCount(0) # 清空旧数据
        self.impact_table.show()

        for i, key in enumerate(self.pre_injection_snapshot.keys()):
            self.impact_table.insertRow(i)
            pre_val = self.pre_injection_snapshot[key]
            post_val = post_snapshot[key]
            
            # 指标名称
            self.impact_table.setItem(i, 0, QTableWidgetItem(key))
            
            # 操作前的值
            pre_item = QTableWidgetItem(f"{pre_val:.1f}")
            self.impact_table.setItem(i, 1, pre_item)

            # 操作后的值和变化
            post_item = QTableWidgetItem(f"{post_val:.1f}")
            delta = post_val - pre_val
            
            if abs(delta) > 0.01:
                # 根据变化好坏设置颜色
                # 假设等待/排队是坏事，SOC/可用桩是好事
                is_bad_change = (delta > 0 and ("等待" in key or "排队" in key)) or \
                                (delta < 0 and ("SOC" in key or "可用" in key))
                
                if is_bad_change:
                    post_item.setForeground(QColor('red'))
                    post_item.setText(f"{post_val:.1f} (▼ {abs(delta):.1f})")
                else:
                    post_item.setForeground(QColor('green'))
                    post_item.setText(f"{post_val:.1f} (▲ {abs(delta):.1f})")
            
            self.impact_table.setItem(i, 2, post_item)

        self.pre_injection_snapshot = None # 重置快照，准备下一次分析

    # update_lists 方法保持不变
    def update_lists(self, chargers, stations):
        self.charger_list = sorted(chargers)
        self.station_list = sorted(stations)
        current_charger = self.charger_combo.currentText()
        self.charger_combo.clear()
        self.charger_combo.addItems(self.charger_list)
        if current_charger in self.charger_list: self.charger_combo.setCurrentText(current_charger)
        current_station = self.station_combo.currentText()
        self.station_combo.clear()
        self.station_combo.addItems(self.station_list)
        if current_station in self.station_list: self.station_combo.setCurrentText(current_station)
class OperatorControlPanel(QWidget):
    # 信号定义
    pricingStrategyChanged = pyqtSignal(dict)


    def __init__(self, config_param, parent=None):
        super().__init__(parent)
        self.config = config_param
        self.op_panel_specific_config = self.config.get('operator_panel', {})
        self.panel_settings = self.op_panel_specific_config.get('main_panel_settings', {})
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
        op_panel_config = self.config.get('operator_panel', {})
        self.monitor_widget = RealtimeMonitorWidget(op_panel_config)
        self.monitor_widget.stationSelected.connect(self.onStationSelected)
        self.tab_widget.addTab(self.monitor_widget, "📊 实时监控")
        
        # 定价管理
        # Pass the full application config to PricingControlWidget
        self.pricing_widget = PricingControlWidget(self.config) 
        self.pricing_widget.pricingUpdated.connect(self.onPricingUpdated)
        self.tab_widget.addTab(self.pricing_widget, "💰 定价管理")
        
        # 财务分析
        # Ensure FinancialAnalysisWidget receives op_panel_config
        self.financial_widget = FinancialAnalysisWidget(op_panel_config) 
        self.tab_widget.addTab(self.financial_widget, "📈 财务分析")
        
        # 需求预测
        self.forecast_widget = DemandForecastWidget(op_panel_config) 
        self.tab_widget.addTab(self.forecast_widget, "🔮 需求预测")

        # --- START OF MODIFICATION ---
        # 替换告警管理为故障模拟
        self.failure_sim_widget = FailureSimulationWidget(op_panel_config, self.simulation_environment, self)
        # 连接新面板的信号到处理方法
        self.failure_sim_widget.injectFailure.connect(self.handle_failure_injection)
        self.failure_sim_widget.injectDemandSpike.connect(self.handle_demand_spike_injection)
        self.tab_widget.addTab(self.failure_sim_widget, "⚡ 故障与压力测试")
        # --- END OF MODIFICATION ---
        layout.addWidget(self.tab_widget)
        
    def _createToolbar(self):
        toolbar = QToolBar()
        refresh_action = QAction("🔄 刷新", self)
        refresh_action.triggered.connect(self.refreshAll)
        toolbar.addAction(refresh_action)
        toolbar.addSeparator()
        export_action = QAction("📊 导出报表", self)
        export_action.triggered.connect(self.exportReport)
        toolbar.addAction(export_action)
        expansion_action = QAction("📈 扩容建议", self)
        expansion_action.triggered.connect(self.showExpansionRecommendations)
        toolbar.addAction(expansion_action)
        return toolbar
        
    def setupTimers(self):
        """设置定时器"""
        op_config = self.config.get('operator_panel', {})
        
        # 数据更新定时器 - 性能优化：降低更新频率
        update_interval = op_config.get('update_interval_ms', 8000)
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.updateRealtimeData)
        self.update_timer.start(update_interval)
        
    def setSimulationEnvironment(self, environment):
        """设置仿真环境"""
        self.simulation_environment = environment
        logger.info("运营商面板已连接到仿真环境")
        if hasattr(self, 'failure_sim_widget'):
            self.failure_sim_widget.simulation_environment = environment # <-- 关键的传递
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

        # 更新下拉框列表
        station_list = list(stations_status.keys())
        charger_ids = [c.get('charger_id') for c in chargers]
        self.forecast_widget.updateStationList(station_list)
        # --- START OF MODIFICATION ---
        # 为故障模拟面板更新列表
        self.failure_sim_widget.update_lists(charger_ids, station_list)
        # --- END OF MODIFICATION ---
        
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

    def handle_failure_injection(self, failure_type: str, target_id: str):
        """处理从UI发来的故障注入信号，直接修改仿真环境的状态"""
        if not self.simulation_environment:
            logger.warning("无法注入故障：仿真环境未连接。")
            return
            
        if failure_type == "charger":
            if target_id in self.simulation_environment.chargers:
                self.simulation_environment.chargers[target_id]['status'] = 'failure'
                logger.info(f"成功注入故障：充电桩 {target_id} 状态已设置为 'failure'。")
            else:
                logger.error(f"注入故障失败：找不到充电桩 {target_id}。")
                
        elif failure_type == "station":
            found_chargers = 0
            for charger_id, charger_data in self.simulation_environment.chargers.items():
                if charger_data.get('location') == target_id:
                    charger_data['status'] = 'failure'
                    found_chargers += 1
            logger.info(f"成功注入区域停电：站点 {target_id} 的 {found_chargers} 个充电桩状态已设置为 'failure'。")

    def handle_demand_spike_injection(self, num_users: int, soc_threshold: int):
        """处理从UI发来的需求冲击信号"""
        if not self.simulation_environment:
            logger.warning("无法注入需求冲击：仿真环境未连接。")
            return
            
        all_users = list(self.simulation_environment.users.values())
        # 选择当前不在充电或等待中的空闲用户
        eligible_users = [u for u in all_users if u.get('status') in ['idle', 'traveling'] and u.get('target_charger') is None]
        
        if len(eligible_users) < num_users:
            logger.warning(f"需求冲击：符合条件的用户数 ({len(eligible_users)}) 少于请求数 ({num_users})。将对所有符合条件的用户操作。")
            num_users = len(eligible_users)
            
        # 随机选择用户并修改他们的状态
        selected_users = random.sample(eligible_users, num_users)
        count = 0
        for user in selected_users:
            # 随机设置一个低于阈值的SOC
            user['soc'] = random.uniform(soc_threshold - 10, soc_threshold)
            # 强制他们需要充电
            user['needs_charge_decision'] = True
            count += 1
        
        logger.info(f"成功注入需求冲击：{count} 个用户的SOC已被降低，并标记为需要充电。")
    # --- END OF MODIFICATION ---

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
        dialog_width = self.panel_settings.get('station_details_dialog_width', 600)
        dialog_height = self.panel_settings.get('station_details_dialog_height', 400)
        dialog.resize(dialog_width, dialog_height)
        
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
        default_export_days = self.panel_settings.get('report_export_default_days', 30)
        start_date.setDate(QDate.currentDate().addDays(-default_export_days))
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
            filename_prefix = self.panel_settings.get('report_filename_prefix', 'operator_report_')
            filename = f"{filename_prefix}{start}_{end}.json"
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
        dialog_width = self.panel_settings.get('expansion_recs_dialog_width', 800)
        dialog_height = self.panel_settings.get('expansion_recs_dialog_height', 600)
        dialog.resize(dialog_width, dialog_height)
        
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
                bg_color_hex = self.panel_settings.get('expansion_recs_high_priority_color_hex', "#ff4444")
                text_color_hex = self.panel_settings.get('expansion_recs_high_priority_text_color_hex', "#ffffff")
                priority_item.setBackground(QColor(bg_color_hex))
                priority_item.setForeground(QColor(text_color_hex))
            table.setItem(row, 5, priority_item)
        
        layout.addWidget(table)
        
        # 关闭按钮
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(dialog.close)
        layout.addWidget(close_btn)
        
        dialog.exec()


    # 导出组件
    __all__ = ['OperatorControlPanel']
