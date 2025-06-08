# synergy_dashboard.py

import sys
import logging
import numpy as np
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox, QLabel, QFrame, QTextEdit
)
from PyQt6.QtGui import (
    QFont, QPainter, QPen, QBrush, QColor, QPolygonF, QFontMetrics, QLinearGradient
)
from PyQt6.QtCore import Qt, QPointF

try:
    import pyqtgraph as pg
    from pyqtgraph import PlotWidget, ViewBox, mkPen, BarGraphItem, FillBetweenItem
    HAS_PYQTGRAPH = True
except ImportError:
    HAS_PYQTGRAPH = False

logger = logging.getLogger(__name__)

# --- PerformanceRadarChart and KPIPanel classes remain the same as the last correct version ---
# (No changes needed for these two classes, you can keep them as they are)
class PerformanceRadarChart(QWidget):
    """性能雷达图，直观展示多维目标的平衡状态"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(300, 300)
        self.labels = [
            "用户满意度", "运营商利润", "电网友好度", 
            "充电效率", "系统利用率"
        ]
        self.values = [0.0] * len(self.labels)
        self.baseline_values = [0.0] * len(self.labels) # For comparison
        self.max_value = 1.0

    def update_data(self, values, baseline_values=None):
        if len(values) == len(self.labels):
            self.values = [min(max(v, -1), 1) for v in values] # Clamp values between -1 and 1
        if baseline_values and len(baseline_values) == len(self.labels):
            self.baseline_values = [min(max(v, -1), 1) for v in baseline_values]
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        center_x, center_y = self.width() / 2, self.height() / 2
        radius = min(center_x, center_y) * 0.75
        num_levels = 4
        
        painter.setPen(QPen(QColor(200, 200, 220), 1, Qt.PenStyle.DotLine))
        for i in range(1, num_levels + 1):
            r = radius * i / num_levels
            painter.drawEllipse(QPointF(center_x, center_y), r, r)

        angles = np.linspace(0, 2 * np.pi, len(self.labels), endpoint=False) - np.pi / 2 # Rotate to start at top
        for i, angle in enumerate(angles):
            x = center_x + radius * np.cos(angle)
            y = center_y + radius * np.sin(angle)
            painter.drawLine(QPointF(center_x, center_y), QPointF(x, y))

        painter.setPen(QColor(50, 50, 50))
        painter.setFont(QFont("Arial", 9))
        for i, label in enumerate(self.labels):
            angle = angles[i]
            x = center_x + (radius + 15) * np.cos(angle)
            y = center_y + (radius + 15) * np.sin(angle)
            fm = QFontMetrics(painter.font())
            text_width = fm.horizontalAdvance(label)
            # Adjust text position for better alignment
            if np.isclose(angle, -np.pi / 2): # Top
                y -= fm.height() / 2
            elif np.isclose(angle, np.pi / 2): # Bottom
                y += fm.height()
            x -= text_width / 2
            painter.drawText(QPointF(x, y), label)
            
        if any(self.baseline_values):
            polygon = QPolygonF()
            for i, value in enumerate(self.baseline_values):
                r = radius * (value + 1) / 2
                angle = angles[i]
                polygon.append(QPointF(center_x + r * np.cos(angle), center_y + r * np.sin(angle)))
            painter.setBrush(QBrush(QColor(255, 100, 100, 80)))
            painter.setPen(QPen(QColor(255, 100, 100), 2, Qt.PenStyle.DashLine))
            painter.drawPolygon(polygon)
            
        if any(self.values):
            polygon = QPolygonF()
            for i, value in enumerate(self.values):
                r = radius * (value + 1) / 2
                angle = angles[i]
                polygon.append(QPointF(center_x + r * np.cos(angle), center_y + r * np.sin(angle)))
            painter.setBrush(QBrush(QColor(100, 150, 255, 120)))
            painter.setPen(QPen(QColor(50, 80, 220), 2))
            painter.drawPolygon(polygon)


class KPIPanel(QFrame):
    """显示关键性能指标的面板"""
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFrameShadow(QFrame.Shadow.Sunken)
        self.setObjectName("KPIPanel")
        
        main_layout = QVBoxLayout(self)
        
        title_label = QLabel(title)
        title_label.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(title_label)
        
        self.value_label = QLabel("N/A")
        self.value_label.setFont(QFont("Arial", 28, QFont.Weight.Bold))
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.value_label)
        
        self.setStyleSheet("""
            #KPIPanel {
                background-color: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:1, 
                                                stop:0 rgba(245, 245, 245, 255), 
                                                stop:1 rgba(220, 220, 220, 255));
                border-radius: 10px;
                border: 1px solid #ccc;
            }
        """)

    def update_value(self, value, unit=""):
        if isinstance(value, (int, float)):
            if abs(value) < 100:
                self.value_label.setText(f"{value:.2f}{unit}")
            else:
                self.value_label.setText(f"{int(value)}{unit}")
        else:
            self.value_label.setText(str(value))
        
        try:
            is_negative_kpi = "耗尽" in self.windowTitle() or "等待" in self.windowTitle()
            numeric_value = float(value)
            if numeric_value > 0 and is_negative_kpi:
                self.value_label.setStyleSheet("color: #e74c3c;")
            elif numeric_value < 0:
                 self.value_label.setStyleSheet("color: #e74c3c;")
            elif numeric_value > 0:
                self.value_label.setStyleSheet("color: #27ae60;")
            else:
                self.value_label.setStyleSheet("color: #34495e;")
        except (ValueError, TypeError):
            self.value_label.setStyleSheet("color: #34495e;")


class SynergyDashboard(QWidget):
    """系统协同仪表盘 (修改版)"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUI()

    def setupUI(self):
        main_layout = QGridLayout(self)
        main_layout.setSpacing(20)

        # 主题一：总体性能与目标权衡 (保持不变)
        performance_group = QGroupBox("总体性能与目标权衡")
        performance_layout = QHBoxLayout(performance_group)
        self.radar_chart = PerformanceRadarChart()
        kpi_layout = QGridLayout()
        self.kpi_total_reward = KPIPanel("综合奖励")
        self.kpi_waiting_users = KPIPanel("等待用户比例")
        self.kpi_soc_depletion = KPIPanel("电量耗尽事件")
        self.kpi_v2g_contrib = KPIPanel("V2G贡献")
        kpi_layout.addWidget(self.kpi_total_reward, 0, 0)
        kpi_layout.addWidget(self.kpi_waiting_users, 0, 1)
        kpi_layout.addWidget(self.kpi_soc_depletion, 1, 0)
        kpi_layout.addWidget(self.kpi_v2g_contrib, 1, 1)
        performance_layout.addWidget(self.radar_chart, 1)
        performance_layout.addLayout(kpi_layout, 1)
        main_layout.addWidget(performance_group, 0, 0, 1, 2)
        
        # --- START OF MODIFICATION ---
        
        # 主题二：车-桩互动分析 (已删除)

        # 主题三：桩-网互动分析 (现在占据整个第二行)
        grid_interaction_group = QGroupBox("桩-网互动分析")
        grid_interaction_layout = QHBoxLayout(grid_interaction_group)
        if HAS_PYQTGRAPH:
            self.load_composition_chart = PlotWidget()
            self.load_composition_chart.setBackground('w')
            self.load_composition_chart.addLegend()
            self.base_load_curve = self.load_composition_chart.plot(pen=mkPen(color=(200, 200, 200), width=2), name="基础负荷 (MW)")
            self.total_load_curve = self.load_composition_chart.plot(pen=mkPen(color=(255, 0, 0), width=2), name="总负荷 (MW)")
            
            # 移除了 self.renewable_gen_curve 的创建
            
            fill_brush = QBrush(QColor(255, 0, 0, 80))
            self.ev_fill = FillBetweenItem(self.base_load_curve, self.total_load_curve, brush=fill_brush)
            self.load_composition_chart.addItem(self.ev_fill)
            
            grid_interaction_layout.addWidget(self.load_composition_chart)
        else:
            grid_interaction_layout.addWidget(QLabel("PyQtGraph not found."))
            
        # 让桩-网互动分析图占据整个第二行
        main_layout.addWidget(grid_interaction_group, 1, 0, 1, 2)
        
        # --- END OF MODIFICATION ---
        
    def update_data(self, history, rewards):
        """用新的仿真历史数据更新整个仪表盘"""
        if not history:
            return

        latest_state = history[-1]
        
        self._update_performance_kpis(latest_state, rewards)
        
        # --- START OF MODIFICATION ---
        # 删除了对 _update_demand_supply 的调用
        # --- END OF MODIFICATION ---
        
        self._update_load_composition(history)

    def _update_performance_kpis(self, state, rewards):
        # 此函数保持不变
        user_satisfaction = rewards.get('user_satisfaction', 0)
        operator_profit = rewards.get('operator_profit', 0)
        grid_friendliness = rewards.get('grid_friendliness', 0)
        
        total_chargers = len(state.get('chargers', []))
        occupied_chargers = sum(1 for c in state.get('chargers', []) if c.get('status') == 'occupied')
        failed_chargers = sum(1 for c in state.get('chargers', []) if c.get('status') == 'failure')
        operational_chargers = total_chargers - failed_chargers
        system_utilization = (occupied_chargers / operational_chargers) * 1.0 if operational_chargers > 0 else 0.0

        charging_users = [u for u in state.get('users', []) if u.get('status') == 'charging']
        avg_efficiency = np.mean([u.get('charging_efficiency', 0.9) for u in charging_users]) * 1.0 if charging_users else 0.0

        self.radar_chart.update_data(
            [user_satisfaction, operator_profit, grid_friendliness, avg_efficiency, system_utilization]
        )

        self.kpi_total_reward.update_value(rewards.get('total_reward', 0))
        
        total_users = len(state.get('users', []))
        waiting_users = sum(1 for u in state.get('users', []) if u.get('status') == 'waiting')
        waiting_percentage = (waiting_users / total_users) * 100 if total_users > 0 else 0
        self.kpi_waiting_users.update_value(waiting_percentage, "%")
        
        depleted_users = sum(1 for u in state.get('users', []) if u.get('soc', 100) <= 0.1)
        self.kpi_soc_depletion.update_value(depleted_users)
        
        v2g_mw = state.get('grid_status', {}).get('aggregated_metrics', {}).get('current_actual_v2g_dispatch_mw', 0)
        self.kpi_v2g_contrib.update_value(v2g_mw, " MW")

    # --- START OF MODIFICATION ---
    # 删除了整个 _update_demand_supply 方法
    # --- END OF MODIFICATION ---

    def _update_load_composition(self, history):
        if not HAS_PYQTGRAPH or not history:
            return

        timestamps = list(range(len(history)))
        base_loads_mw = []
        total_loads_mw = []
        
        # --- START OF MODIFICATION ---
        # 移除了 renewable_gens_mw 的相关计算
        # --- END OF MODIFICATION ---

        for step_data in history:
            grid_status = step_data.get('grid_status', {})
            agg_metrics = grid_status.get('aggregated_metrics', {})
            
            base_load_kw = agg_metrics.get('total_base_load', 0)
            ev_load_kw = agg_metrics.get('total_ev_load', 0)
            
            base_loads_mw.append(base_load_kw / 1000)
            total_loads_mw.append((base_load_kw + ev_load_kw) / 1000)

        self.base_load_curve.setData(x=timestamps, y=base_loads_mw)
        self.total_load_curve.setData(x=timestamps, y=total_loads_mw)
        
        # --- START OF MODIFICATION ---
        # 移除了对 self.renewable_gen_curve.setData 的调用
        # --- END OF MODIFICATION ---