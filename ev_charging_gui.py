import sys
import json
import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import traceback
import random
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QGridLayout, QTabWidget, QLabel, QPushButton, QProgressBar,
    QSlider, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit,
    QGroupBox, QFrame, QSplitter, QScrollArea, QDialog, QDialogButtonBox,
    QFormLayout, QCheckBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QStatusBar, QMenuBar, QMenu, QMessageBox, QFileDialog, QToolBar,
    QSizePolicy, QStyle, QStyleOption
)
from PyQt6.QtCore import (
    Qt, QTimer, QThread, pyqtSignal, QObject, QSize, QRect, QPointF,
    QPropertyAnimation, QEasingCurve, pyqtProperty, QMutex, QMutexLocker
)
from PyQt6.QtGui import (
    QFont, QPixmap, QPainter, QPen, QBrush, QColor, QLinearGradient,
    QRadialGradient, QIcon, QAction, QPalette, QGradient, QPolygonF,
    QFontMetrics, QMovie
)

# 图表库
try:
    import pyqtgraph as pg
    from pyqtgraph import PlotWidget, plot
    HAS_PYQTGRAPH = True
except ImportError:
    HAS_PYQTGRAPH = False
    print("警告：未安装pyqtgraph，图表功能将受限")

# 数据处理
import numpy as np
import pandas as pd

# 导入仿真模块（需要调整import路径）
try:
    from simulation.environment import ChargingEnvironment
    from simulation.scheduler import ChargingScheduler
    from simulation.grid_model_enhanced import EnhancedGridModel
    from simulation.metrics import calculate_rewards
except ImportError as e:
    print(f"警告：无法导入仿真模块: {e}")
    print("请确保simulation包在Python路径中")

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class AnimatedProgressBar(QProgressBar):
    """带动画效果的进度条"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            QProgressBar {
                border: 2px solid #3498db;
                border-radius: 8px;
                text-align: center;
                font-weight: bold;
                background-color: #ecf0f1;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #3498db, stop:0.5 #5dade2, stop:1 #85c1e9);
                border-radius: 6px;
            }
        """)
        self._animation = QPropertyAnimation(self, b"value")
        self._animation.setDuration(500)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
    
    def setValueAnimated(self, value):
        """带动画的数值设置"""
        self._animation.setStartValue(self.value())
        self._animation.setEndValue(value)
        self._animation.start()


class GlowLabel(QLabel):
    """带发光效果的标签"""
    
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._glow_color = QColor(52, 152, 219)
        self._glow_radius = 10
        
    def setGlowColor(self, color):
        self._glow_color = QColor(color)
        self.update()
    
    def setGlowRadius(self, radius):
        self._glow_radius = radius
        self.update()


class MetricCard(QFrame):
    """指标卡片组件"""
    
    def __init__(self, title, value=0.0, trend=0.0, parent=None):
        super().__init__(parent)
        self.title = title
        self.current_value = value
        self.trend = trend
        
        self.setFrameStyle(QFrame.Shape.Box)
        self.setStyleSheet("""
            MetricCard {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #ffffff, stop:1 #f8f9fa);
                border: 1px solid #dee2e6;
                border-radius: 12px;
                padding: 15px;
            }
            MetricCard:hover {
                border: 2px solid #3498db;
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #f8f9fa, stop:1 #e9ecef);
            }
        """)
        
        self.setupUI()
        
    def setupUI(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        
        # 标题
        title_label = QLabel(self.title)
        title_label.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        title_label.setStyleSheet("color: #6c757d;")
        layout.addWidget(title_label)
        
        # 数值
        self.value_label = QLabel(f"{self.current_value:.2f}")
        self.value_label.setFont(QFont("Arial", 24, QFont.Weight.Bold))
        self.value_label.setStyleSheet("color: #2c3e50;")
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.value_label)
        
        # 趋势
        self.trend_label = QLabel(self._getTrendText())
        self.trend_label.setFont(QFont("Arial", 10))
        self.trend_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.trend_label)
        
    def updateValue(self, value, trend=None):
        """更新指标值"""
        self.current_value = value
        if trend is not None:
            self.trend = trend
            
        self.value_label.setText(f"{value:.2f}")
        self.trend_label.setText(self._getTrendText())
        self.trend_label.setStyleSheet(self._getTrendStyle())
        
    def _getTrendText(self):
        if abs(self.trend) < 0.01:
            return "━ 0.00%"
        elif self.trend > 0:
            return f"↗ +{self.trend:.2f}%"
        else:
            return f"↘ {self.trend:.2f}%"
    
    def _getTrendStyle(self):
        if abs(self.trend) < 0.01:
            return "color: #6c757d;"
        elif self.trend > 0:
            return "color: #27ae60; font-weight: bold;"
        else:
            return "color: #e74c3c; font-weight: bold;"


class RegionalLoadChart(QWidget):
    """区域负载图表组件"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.regions = []
        self.time_data = []
        self.load_data = {}
        
        self.setupUI()
        
    def setupUI(self):
        layout = QVBoxLayout(self)
        
        # 标题
        title = QLabel("区域电网负载实时监控")
        title.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        
        if HAS_PYQTGRAPH:
            # 使用pyqtgraph创建图表
            self.plot_widget = PlotWidget()
            self.plot_widget.setBackground('w')
            self.plot_widget.setLabel('left', '负载 (MW)')
            self.plot_widget.setLabel('bottom', '时间')
            self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
            
            # 设置图例
            self.plot_widget.addLegend()
            
            layout.addWidget(self.plot_widget)
            
            # 颜色方案
            self.colors = [
                (255, 99, 132), (54, 162, 235), (255, 205, 86),
                (75, 192, 192), (153, 102, 255), (255, 159, 64)
            ]
        else:
            # 简单的文本显示
            self.text_display = QTextEdit()
            self.text_display.setReadOnly(True)
            layout.addWidget(self.text_display)
    
    def updateData(self, time_series_data):
        """更新图表数据"""
        if not time_series_data or 'timestamps' not in time_series_data:
            return
            
        timestamps = time_series_data['timestamps']
        regional_data = time_series_data.get('regional_data', {})
        
        if HAS_PYQTGRAPH and hasattr(self, 'plot_widget'):
            self.plot_widget.clear()
            
            for i, (region_id, data) in enumerate(regional_data.items()):
                if 'total_load' in data and data['total_load']:
                    color = self.colors[i % len(self.colors)]
                    pen = pg.mkPen(color=color, width=2)
                    
                    # 转换时间戳为x轴数据
                    x_data = list(range(len(data['total_load'])))
                    y_data = data['total_load']
                    
                    self.plot_widget.plot(
                        x_data, y_data, 
                        pen=pen, 
                        name=region_id,
                        symbolBrush=color,
                        symbolSize=6
                    )
        else:
            # 文本显示模式
            text = "区域负载数据:\n\n"
            for region_id, data in regional_data.items():
                if 'total_load' in data and data['total_load']:
                    current_load = data['total_load'][-1] if data['total_load'] else 0
                    text += f"{region_id}: {current_load:.2f} MW\n"
            
            if hasattr(self, 'text_display'):
                self.text_display.setText(text)

# 在ev_charging_gui.py中，替换MapWidget类
# 在MapWidget类中添加updateData方法

class MapWidget(QWidget):
    """增强版地图组件"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.users = []
        self.chargers = []
        self.selected_user = None
        self.selected_charger = None
        self.zoom_level = 1.0
        self.offset_x = 0
        self.offset_y = 0
        self.mouse_press_pos = None
        self.show_user_paths = True
        self.show_charger_queues = True
        self.show_grid_overlay = False
        
        self.setMinimumSize(800, 600)
        self.setMouseTracking(True)
        
        # 地图边界
        self.map_bounds = {
            'lat_min': 30.5, 'lat_max': 31.0,
            'lng_min': 114.0, 'lng_max': 114.5
        }
        
        # 创建右键菜单
        self.createContextMenu()
    
    def updateData(self, users, chargers):
        """更新地图数据"""
        self.users = users or []
        self.chargers = chargers or []
        self.update()  # 触发重绘
    
    def createContextMenu(self):
        """创建右键菜单"""
        self.context_menu = QMenu(self)
        
        self.show_paths_action = QAction("显示用户路径", self)
        self.show_paths_action.setCheckable(True)
        self.show_paths_action.setChecked(True)
        self.show_paths_action.triggered.connect(self.toggleUserPaths)
        
        self.show_queues_action = QAction("显示队列详情", self)
        self.show_queues_action.setCheckable(True)
        self.show_queues_action.setChecked(True)
        self.show_queues_action.triggered.connect(self.toggleQueueDisplay)
        
        self.show_grid_action = QAction("显示电网分区", self)
        self.show_grid_action.setCheckable(True)
        self.show_grid_action.setChecked(False)
        self.show_grid_action.triggered.connect(self.toggleGridOverlay)
        
        self.context_menu.addAction(self.show_paths_action)
        self.context_menu.addAction(self.show_queues_action)
        self.context_menu.addAction(self.show_grid_action)
    
    def toggleUserPaths(self):
        self.show_user_paths = self.show_paths_action.isChecked()
        self.update()
    
    def toggleQueueDisplay(self):
        self.show_charger_queues = self.show_queues_action.isChecked()
        self.update()
    
    def toggleGridOverlay(self):
        self.show_grid_overlay = self.show_grid_action.isChecked()
        self.update()
    
    def contextMenuEvent(self, event):
        """显示右键菜单"""
        self.context_menu.exec(event.globalPos())
    
    def paintEvent(self, event):
        """增强的绘制方法"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # 应用缩放和偏移
        painter.translate(self.offset_x, self.offset_y)
        painter.scale(self.zoom_level, self.zoom_level)
        
        # 绘制背景
        self._drawBackground(painter)
        
        # 绘制电网分区（如果启用）
        if self.show_grid_overlay:
            self._drawGridRegions(painter)
        
        # 绘制用户路径（如果启用）
        if self.show_user_paths:
            self._drawUserPaths(painter)
        
        # 绘制充电桩
        self._drawChargers(painter)
        
        # 绘制用户
        self._drawUsers(painter)
        
        # 绘制选中对象的详细信息
        if self.selected_user:
            self._drawUserDetails(painter, self.selected_user)
        if self.selected_charger:
            self._drawChargerDetails(painter, self.selected_charger)
        
        # 重置变换
        painter.resetTransform()
        
        # 绘制图例和统计信息
        self._drawLegend(painter)
        self._drawStatistics(painter)
    
    def _drawBackground(self, painter):
        """绘制地图背景"""
        rect = self.rect()
        
        # 背景渐变
        gradient = QLinearGradient(0, 0, 0, rect.height())
        gradient.setColorAt(0, QColor(240, 248, 255))
        gradient.setColorAt(1, QColor(220, 235, 250))
        
        painter.fillRect(rect, QBrush(gradient))
        
        # 网格线
        painter.setPen(QPen(QColor(200, 200, 200), 1, Qt.PenStyle.DotLine))
        
        grid_size = 50
        for x in range(0, rect.width(), grid_size):
            painter.drawLine(x, 0, x, rect.height())
        for y in range(0, rect.height(), grid_size):
            painter.drawLine(0, y, rect.width(), y)
    
    def _drawChargers(self, painter):
        """绘制充电桩"""
        for charger in self.chargers:
            if not charger.get('position'):
                continue
            
            x, y = self._geoToPixel(charger['position'])
            
            # 根据状态选择颜色
            status = charger.get('status', 'unknown')
            if status == 'available':
                color = QColor(46, 204, 113)  # 绿色
            elif status == 'occupied':
                color = QColor(231, 76, 60)   # 红色
            elif status == 'failure':
                color = QColor(149, 165, 166) # 灰色
            else:
                color = QColor(52, 152, 219)  # 蓝色
            
            # 绘制充电桩图标
            painter.setBrush(QBrush(color))
            painter.setPen(QPen(Qt.GlobalColor.black, 2))
            painter.drawRect(int(x-10), int(y-10), 20, 20)
            
            # 绘制充电桩ID
            painter.setPen(QPen(Qt.GlobalColor.white, 1))
            painter.setFont(QFont("Arial", 8, QFont.Weight.Bold))
            charger_id = charger.get('charger_id', '')
            if len(charger_id) > 10:
                charger_id = charger_id[-4:]  # 只显示最后4位
            painter.drawText(int(x-8), int(y+3), charger_id)
            
            # 绘制队列指示器
            queue_length = len(charger.get('queue', []))
            if queue_length > 0 and self.show_charger_queues:
                painter.setPen(QPen(Qt.GlobalColor.red, 2))
                painter.setBrush(QBrush(QColor(255, 255, 255)))
                painter.drawEllipse(int(x+8), int(y-12), 16, 16)
                painter.setPen(QPen(Qt.GlobalColor.red, 1))
                painter.drawText(int(x+12), int(y-1), str(queue_length))
    
    def _drawUsers(self, painter):
        """绘制用户"""
        for user in self.users:
            if not user.get('current_position'):
                continue
            
            x, y = self._geoToPixel(user['current_position'])
            
            # 根据状态选择颜色
            status = user.get('status', 'unknown')
            if status == 'charging':
                color = QColor(46, 204, 113)  # 绿色
            elif status == 'waiting':
                color = QColor(241, 196, 15)  # 黄色
            elif status == 'traveling':
                color = QColor(52, 152, 219)  # 蓝色
            else:
                color = QColor(149, 165, 166) # 灰色
            
            # 绘制用户图标
            painter.setBrush(QBrush(color))
            painter.setPen(QPen(Qt.GlobalColor.black, 1))
            painter.drawEllipse(int(x-6), int(y-6), 12, 12)
            
            # 显示SOC
            soc = user.get('soc', 0)
            if soc < 20:
                painter.setPen(QPen(Qt.GlobalColor.red, 1, Qt.PenStyle.SolidLine))
            elif soc < 50:
                painter.setPen(QPen(QColor(255, 165, 0), 1))
            else:
                painter.setPen(QPen(Qt.GlobalColor.green, 1))
            
            painter.setFont(QFont("Arial", 8))
            painter.drawText(int(x+8), int(y+8), f"{soc:.0f}%")
    
    def _drawUserPaths(self, painter):
        """绘制用户路径"""
        for user in self.users:
            if user.get('status') == 'traveling' and user.get('target_charger'):
                # 找到目标充电桩
                target_charger = next(
                    (c for c in self.chargers if c.get('charger_id') == user['target_charger']), 
                    None
                )
                if target_charger:
                    start = self._geoToPixel(user['current_position'])
                    end = self._geoToPixel(target_charger['position'])
                    
                    # 绘制路径
                    painter.setPen(QPen(QColor(52, 152, 219, 100), 2, Qt.PenStyle.DashLine))
                    painter.drawLine(QPointF(*start), QPointF(*end))
                    
                    # 绘制箭头
                    self._drawArrow(painter, start, end, QColor(52, 152, 219))
    
    def _drawArrow(self, painter, start, end, color):
        """绘制箭头"""
        import math
        
        # 计算箭头方向
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        length = math.sqrt(dx**2 + dy**2)
        
        if length > 0:
            # 标准化方向向量
            dx /= length
            dy /= length
            
            # 箭头参数
            arrow_length = 10
            arrow_angle = 0.5
            
            # 计算箭头点
            arrow_x = end[0] - arrow_length * dx
            arrow_y = end[1] - arrow_length * dy
            
            # 计算箭头两侧的点
            perp_dx = -dy
            perp_dy = dx
            
            arrow_points = [
                QPointF(end[0], end[1]),
                QPointF(arrow_x + arrow_length * arrow_angle * perp_dx, 
                       arrow_y + arrow_length * arrow_angle * perp_dy),
                QPointF(arrow_x - arrow_length * arrow_angle * perp_dx, 
                       arrow_y - arrow_length * arrow_angle * perp_dy)
            ]
            
            painter.setBrush(QBrush(color))
            painter.setPen(QPen(color, 2))
            painter.drawPolygon(QPolygonF(arrow_points))
    
    def _drawGridRegions(self, painter):
        """绘制电网分区"""
        # 假设有3个区域
        regions = [
            {'name': 'Region_1', 'color': QColor(255, 0, 0, 50), 'bounds': (0, 0, 0.33, 1)},
            {'name': 'Region_2', 'color': QColor(0, 255, 0, 50), 'bounds': (0.33, 0, 0.67, 1)},
            {'name': 'Region_3', 'color': QColor(0, 0, 255, 50), 'bounds': (0.67, 0, 1, 1)}
        ]
        
        for region in regions:
            x1, y1, x2, y2 = region['bounds']
            x1 = x1 * self.width() / self.zoom_level
            y1 = y1 * self.height() / self.zoom_level
            x2 = x2 * self.width() / self.zoom_level
            y2 = y2 * self.height() / self.zoom_level
            
            painter.fillRect(int(x1), int(y1), int(x2-x1), int(y2-y1), region['color'])
            painter.setPen(QPen(Qt.GlobalColor.black, 1))
            painter.drawText(int(x1+10), int(y1+20), region['name'])
    
    def _drawUserDetails(self, painter, user):
        """绘制用户详细信息"""
        x, y = self._geoToPixel(user['current_position'])
        
        # 信息框背景
        info_width = 180
        info_height = 120
        info_x = x + 15
        info_y = y - info_height // 2
        
        # 确保信息框在视图内
        if info_x + info_width > self.width() / self.zoom_level:
            info_x = x - info_width - 15
        
        # 绘制信息框
        painter.fillRect(int(info_x), int(info_y), info_width, info_height, 
                        QColor(255, 255, 255, 240))
        painter.setPen(QPen(Qt.GlobalColor.black, 1))
        painter.drawRect(int(info_x), int(info_y), info_width, info_height)
        
        # 绘制信息
        painter.setFont(QFont("Arial", 9))
        y_offset = info_y + 20
        
        info_lines = [
            f"ID: {user.get('user_id', 'N/A')}",
            f"状态: {self._getUserStatusText(user.get('status', 'unknown'))}",
            f"电量: {user.get('soc', 0):.1f}%",
            f"车型: {user.get('vehicle_type', 'sedan')}",
            f"目标: {user.get('target_charger', '无')}"
        ]
        
        for line in info_lines:
            painter.drawText(int(info_x + 10), int(y_offset), line)
            y_offset += 20
    
    def _drawChargerDetails(self, painter, charger):
        """绘制充电桩详细信息"""
        x, y = self._geoToPixel(charger['position'])
        
        # 信息框背景
        info_width = 200
        info_height = 150
        info_x = x + 20
        info_y = y - info_height // 2
        
        # 确保信息框在视图内
        if info_x + info_width > self.width() / self.zoom_level:
            info_x = x - info_width - 20
        
        # 绘制信息框
        painter.fillRect(int(info_x), int(info_y), info_width, info_height, 
                        QColor(255, 255, 255, 240))
        painter.setPen(QPen(Qt.GlobalColor.black, 1))
        painter.drawRect(int(info_x), int(info_y), info_width, info_height)
        
        # 绘制信息
        painter.setFont(QFont("Arial", 9))
        y_offset = info_y + 20
        
        info_lines = [
            f"ID: {charger.get('charger_id', 'N/A')}",
            f"状态: {self._getChargerStatusText(charger.get('status', 'unknown'))}",
            f"类型: {charger.get('type', 'normal')}",
            f"功率: {charger.get('max_power', 0):.1f} kW",
            f"队列: {len(charger.get('queue', []))} 人",
            f"今日收入: ¥{charger.get('daily_revenue', 0):.2f}",
            f"使用率: {charger.get('utilization_rate', 0):.1f}%"
        ]
        
        for line in info_lines:
            painter.drawText(int(info_x + 10), int(y_offset), line)
            y_offset += 18
    
    def _drawLegend(self, painter):
        """绘制图例"""
        legend_x = 10
        legend_y = 10
        
        painter.fillRect(legend_x, legend_y, 200, 120, QColor(255, 255, 255, 220))
        painter.setPen(QPen(Qt.GlobalColor.black, 1))
        painter.drawRect(legend_x, legend_y, 200, 120)
        
        painter.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        painter.drawText(legend_x + 10, legend_y + 20, "图例")
        
        # 用户图例
        painter.setFont(QFont("Arial", 9))
        y_offset = 40
        
        user_statuses = [
            ("充电中", QColor(46, 204, 113)),
            ("等待中", QColor(241, 196, 15)),
            ("行驶中", QColor(52, 152, 219)),
            ("空闲", QColor(149, 165, 166))
        ]
        
        for status, color in user_statuses:
            painter.setBrush(QBrush(color))
            painter.drawEllipse(legend_x + 15, legend_y + y_offset - 5, 10, 10)
            painter.drawText(legend_x + 35, legend_y + y_offset + 3, f"用户-{status}")
            y_offset += 18
    
    def _drawStatistics(self, painter):
        """绘制统计信息"""
        # 统计数据
        total_users = len(self.users)
        charging_users = sum(1 for u in self.users if u.get('status') == 'charging')
        waiting_users = sum(1 for u in self.users if u.get('status') == 'waiting')
        traveling_users = sum(1 for u in self.users if u.get('status') == 'traveling')
        
        total_chargers = len(self.chargers)
        available_chargers = sum(1 for c in self.chargers if c.get('status') == 'available')
        occupied_chargers = sum(1 for c in self.chargers if c.get('status') == 'occupied')
        
        # 绘制统计框
        stat_x = self.width() - 220
        stat_y = 10
        stat_width = 200
        stat_height = 180
        
        painter.fillRect(stat_x, stat_y, stat_width, stat_height, QColor(255, 255, 255, 240))
        painter.setPen(QPen(Qt.GlobalColor.black, 2))
        painter.drawRect(stat_x, stat_y, stat_width, stat_height)
        
        painter.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        painter.drawText(stat_x + 10, stat_y + 20, "实时统计")
        
        painter.setFont(QFont("Arial", 9))
        y_offset = stat_y + 40
        
        stats = [
            f"总用户数: {total_users}",
            f"充电中: {charging_users}",
            f"等待中: {waiting_users}",
            f"行驶中: {traveling_users}",
            "",
            f"总充电桩: {total_chargers}",
            f"可用: {available_chargers}",
            f"占用: {occupied_chargers}"
        ]
        
        for stat in stats:
            if stat:  # 跳过空行
                painter.drawText(stat_x + 10, y_offset, stat)
            y_offset += 18
    
    def _geoToPixel(self, geo_pos):
        """地理坐标转换为像素坐标"""
        lat = geo_pos.get('lat', 0)
        lng = geo_pos.get('lng', 0)
        
        # 标准化到[0,1]
        x_norm = (lng - self.map_bounds['lng_min']) / (self.map_bounds['lng_max'] - self.map_bounds['lng_min'])
        y_norm = (lat - self.map_bounds['lat_min']) / (self.map_bounds['lat_max'] - self.map_bounds['lat_min'])
        
        # 转换为像素坐标
        x = x_norm * self.width() / self.zoom_level
        y = (1 - y_norm) * self.height() / self.zoom_level  # Y轴翻转
        
        return x, y
    
    def _screenToGeo(self, screen_pos):
        """屏幕坐标转地理坐标"""
        # 考虑缩放和偏移
        x = (screen_pos.x() - self.offset_x) / self.zoom_level
        y = (screen_pos.y() - self.offset_y) / self.zoom_level
        
        # 转换为地理坐标
        lng = self.map_bounds['lng_min'] + (x / self.width()) * (self.map_bounds['lng_max'] - self.map_bounds['lng_min'])
        lat = self.map_bounds['lat_max'] - (y / self.height()) * (self.map_bounds['lat_max'] - self.map_bounds['lat_min'])
        
        return {'lat': lat, 'lng': lng}
    
    def _isNearPosition(self, pos1, pos2, threshold):
        """检查两个位置是否接近"""
        if not pos1 or not pos2:
            return False
        
        dlat = abs(pos1.get('lat', 0) - pos2.get('lat', 0))
        dlng = abs(pos1.get('lng', 0) - pos2.get('lng', 0))
        
        return dlat < threshold and dlng < threshold
    
    def _getUserStatusText(self, status):
        """获取用户状态文本"""
        status_map = {
            'idle': '空闲',
            'traveling': '行驶中',
            'waiting': '等待中',
            'charging': '充电中',
            'post_charge': '充电后'
        }
        return status_map.get(status, status)
    
    def _getChargerStatusText(self, status):
        """获取充电桩状态文本"""
        status_map = {
            'available': '可用',
            'occupied': '占用中',
            'failure': '故障',
            'maintenance': '维护中'
        }
        return status_map.get(status, status)
    
    def mousePressEvent(self, event):
        """鼠标按下事件"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.mouse_press_pos = event.pos()
            
            # 检查是否点击了对象
            click_pos = self._screenToGeo(event.pos())
            
            # 检查用户
            self.selected_user = None
            for user in self.users:
                user_pos = user.get('current_position', {})
                if self._isNearPosition(click_pos, user_pos, 0.002):
                    self.selected_user = user
                    break
            
            # 检查充电桩
            self.selected_charger = None
            if not self.selected_user:
                for charger in self.chargers:
                    charger_pos = charger.get('position', {})
                    if self._isNearPosition(click_pos, charger_pos, 0.002):
                        self.selected_charger = charger
                        break
            
            self.update()
    
    def mouseMoveEvent(self, event):
        """鼠标移动事件"""
        if event.buttons() == Qt.MouseButton.LeftButton and self.mouse_press_pos:
            # 拖动地图
            delta = event.pos() - self.mouse_press_pos
            self.offset_x += delta.x()
            self.offset_y += delta.y()
            self.mouse_press_pos = event.pos()
            self.update()
        
        # 更新悬停信息
        self.setCursor(Qt.CursorShape.ArrowCursor)
        hover_pos = self._screenToGeo(event.pos())
        
        # 检查是否悬停在对象上
        for user in self.users:
            if self._isNearPosition(hover_pos, user.get('current_position', {}), 0.002):
                self.setCursor(Qt.CursorShape.PointingHandCursor)
                break
        
        for charger in self.chargers:
            if self._isNearPosition(hover_pos, charger.get('position', {}), 0.002):
                self.setCursor(Qt.CursorShape.PointingHandCursor)
                break
    
    def wheelEvent(self, event):
        """鼠标滚轮事件 - 真正的缩放功能"""
        # 获取鼠标位置
        mouse_pos = event.position()
        
        # 缩放前的地理坐标
        geo_before = self._screenToGeo(mouse_pos.toPoint())
        
        # 计算缩放
        delta = event.angleDelta().y()
        zoom_factor = 1.1 if delta > 0 else 0.9
        
        self.zoom_level *= zoom_factor
        self.zoom_level = max(0.5, min(5.0, self.zoom_level))
        
        # 缩放后的地理坐标
        geo_after = self._screenToGeo(mouse_pos.toPoint())
        
        # 调整偏移以保持鼠标位置不变
        if geo_before and geo_after:
            pixel_before = self._geoToPixel(geo_before)
            pixel_after = self._geoToPixel(geo_after)
            
            self.offset_x += (pixel_after[0] - pixel_before[0]) * self.zoom_level
            self.offset_y += (pixel_after[1] - pixel_before[1]) * self.zoom_level
        
        self.update()

class SimulationWorker(QThread):
    """仿真工作线程"""
    
    # 信号定义
    statusUpdated = pyqtSignal(dict)
    metricsUpdated = pyqtSignal(dict)
    errorOccurred = pyqtSignal(str)
    simulationFinished = pyqtSignal()
    
    def __init__(self, config):
        super().__init__()
        self.config = config
        self.running = False
        self.paused = False
        self.environment = None
        self.scheduler = None
        self.mutex = QMutex()
        
    def run(self):
        """运行仿真"""
        try:
            self.running = True
            
            # 初始化仿真环境
            self.environment = ChargingEnvironment(self.config)
            self.scheduler = ChargingScheduler(self.config)
            
            logger.info("仿真开始")
            
            while self.running:
                if self.paused:
                    time.sleep(0.1)
                    continue
                
                # 获取当前状态
                current_state = self.environment.get_current_state()
                
                # 调度决策
                decisions = self.scheduler.make_scheduling_decision(current_state)
                
                # 执行一步仿真
                rewards, next_state, done = self.environment.step(decisions)
                
                # 发送状态更新信号
                self.statusUpdated.emit({
                    'state': next_state,
                    'rewards': rewards,
                    'decisions': decisions,
                    'timestamp': datetime.now().isoformat()
                })
                
                # 发送指标更新信号
                self.metricsUpdated.emit(rewards)
                
                if done:
                    break
                
                # 控制更新频率
                time.sleep(0.1)
                
        except Exception as e:
            logger.error(f"仿真错误: {e}")
            self.errorOccurred.emit(str(e))
        finally:
            self.running = False
            self.simulationFinished.emit()
    
    def pause(self):
        """暂停仿真"""
        with QMutexLocker(self.mutex):
            self.paused = True
    
    def resume(self):
        """恢复仿真"""
        with QMutexLocker(self.mutex):
            self.paused = False
    
    def stop(self):
        """停止仿真"""
        with QMutexLocker(self.mutex):
            self.running = False


class ConfigDialog(QDialog):
    """配置对话框"""
    
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config.copy()
        self.setupUI()
        self.loadConfig()
        
    def setupUI(self):
        self.setWindowTitle("仿真配置")
        self.setModal(True)
        self.resize(600, 500)
        
        layout = QVBoxLayout(self)
        
        # 创建选项卡
        tab_widget = QTabWidget()
        
        # 环境配置选项卡
        env_tab = self._createEnvironmentTab()
        tab_widget.addTab(env_tab, "环境配置")
        
        # 调度器配置选项卡
        scheduler_tab = self._createSchedulerTab()
        tab_widget.addTab(scheduler_tab, "调度配置")
        
        # 电网配置选项卡
        grid_tab = self._createGridTab()
        tab_widget.addTab(grid_tab, "电网配置")
        
        layout.addWidget(tab_widget)
        
        # 按钮
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | 
            QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def _createEnvironmentTab(self):
        """创建环境配置选项卡"""
        widget = QWidget()
        layout = QFormLayout(widget)
        
        # 仿真天数
        self.simulation_days = QSpinBox()
        self.simulation_days.setRange(1, 30)
        layout.addRow("仿真天数:", self.simulation_days)
        
        # 用户数量
        self.user_count = QSpinBox()
        self.user_count.setRange(10, 10000)
        layout.addRow("用户数量:", self.user_count)
        
        # 充电站数量
        self.station_count = QSpinBox()
        self.station_count.setRange(1, 100)
        layout.addRow("充电站数量:", self.station_count)
        
        # 每站充电桩数量
        self.chargers_per_station = QSpinBox()
        self.chargers_per_station.setRange(1, 50)
        layout.addRow("每站充电桩数:", self.chargers_per_station)
        
        # 时间步长
        self.time_step = QSpinBox()
        self.time_step.setRange(1, 60)
        self.time_step.setSuffix(" 分钟")
        layout.addRow("时间步长:", self.time_step)
        
        return widget
    
    def _createSchedulerTab(self):
        """创建调度器配置选项卡"""
        widget = QWidget()
        layout = QFormLayout(widget)
        
        # 调度算法
        self.algorithm = QComboBox()
        self.algorithm.addItems([
            "rule_based", "uncoordinated", 
            "coordinated_mas", "marl"
        ])
        layout.addRow("调度算法:", self.algorithm)
        
        # 优化权重
        weight_group = QGroupBox("优化权重")
        weight_layout = QFormLayout(weight_group)
        
        self.user_weight = QDoubleSpinBox()
        self.user_weight.setRange(0.0, 1.0)
        self.user_weight.setSingleStep(0.1)
        weight_layout.addRow("用户满意度:", self.user_weight)
        
        self.profit_weight = QDoubleSpinBox()
        self.profit_weight.setRange(0.0, 1.0)
        self.profit_weight.setSingleStep(0.1)
        weight_layout.addRow("运营商利润:", self.profit_weight)
        
        self.grid_weight = QDoubleSpinBox()
        self.grid_weight.setRange(0.0, 1.0)
        self.grid_weight.setSingleStep(0.1)
        weight_layout.addRow("电网友好度:", self.grid_weight)
        
        layout.addRow(weight_group)
        
        return widget
    
    def _createGridTab(self):
        """创建电网配置选项卡"""
        widget = QWidget()
        layout = QFormLayout(widget)
        
        # 电价设置
        price_group = QGroupBox("电价设置")
        price_layout = QFormLayout(price_group)
        
        self.normal_price = QDoubleSpinBox()
        self.normal_price.setRange(0.1, 2.0)
        self.normal_price.setSingleStep(0.01)
        self.normal_price.setSuffix(" 元/kWh")
        price_layout.addRow("平时电价:", self.normal_price)
        
        self.peak_price = QDoubleSpinBox()
        self.peak_price.setRange(0.1, 3.0)
        self.peak_price.setSingleStep(0.01)
        self.peak_price.setSuffix(" 元/kWh")
        price_layout.addRow("峰时电价:", self.peak_price)
        
        self.valley_price = QDoubleSpinBox()
        self.valley_price.setRange(0.1, 1.0)
        self.valley_price.setSingleStep(0.01)
        self.valley_price.setSuffix(" 元/kWh")
        price_layout.addRow("谷时电价:", self.valley_price)
        
        layout.addRow(price_group)
        
        return widget
    
    def loadConfig(self):
        """加载配置到界面"""
        # 环境配置
        env_config = self.config.get('environment', {})
        self.simulation_days.setValue(env_config.get('simulation_days', 7))
        self.user_count.setValue(env_config.get('user_count', 1000))
        self.station_count.setValue(env_config.get('station_count', 20))
        self.chargers_per_station.setValue(env_config.get('chargers_per_station', 10))
        self.time_step.setValue(env_config.get('time_step_minutes', 15))
        
        # 调度器配置
        scheduler_config = self.config.get('scheduler', {})
        algorithm = scheduler_config.get('scheduling_algorithm', 'rule_based')
        index = self.algorithm.findText(algorithm)
        if index >= 0:
            self.algorithm.setCurrentIndex(index)
        
        # 权重配置
        weights = scheduler_config.get('optimization_weights', {})
        self.user_weight.setValue(weights.get('user_satisfaction', 0.33))
        self.profit_weight.setValue(weights.get('operator_profit', 0.33))
        self.grid_weight.setValue(weights.get('grid_friendliness', 0.34))
        
        # 电网配置
        grid_config = self.config.get('grid', {})
        self.normal_price.setValue(grid_config.get('normal_price', 0.85))
        self.peak_price.setValue(grid_config.get('peak_price', 1.2))
        self.valley_price.setValue(grid_config.get('valley_price', 0.4))
    
    def getConfig(self):
        """获取界面配置"""
        config = self.config.copy()
        
        # 更新环境配置
        config['environment'].update({
            'simulation_days': self.simulation_days.value(),
            'user_count': self.user_count.value(),
            'station_count': self.station_count.value(),
            'chargers_per_station': self.chargers_per_station.value(),
            'time_step_minutes': self.time_step.value()
        })
        
        # 更新调度器配置
        config['scheduler'].update({
            'scheduling_algorithm': self.algorithm.currentText(),
            'optimization_weights': {
                'user_satisfaction': self.user_weight.value(),
                'operator_profit': self.profit_weight.value(),
                'grid_friendliness': self.grid_weight.value()
            }
        })
        
        # 更新电网配置
        config['grid'].update({
            'normal_price': self.normal_price.value(),
            'peak_price': self.peak_price.value(),
            'valley_price': self.valley_price.value()
        })
        
        return config


class MainWindow(QMainWindow):
    """主窗口"""
    
    def __init__(self):
        super().__init__()
        
        # 初始化配置和状态
        self.config = self._loadDefaultConfig()
        self.simulation_worker = None
        self.current_metrics = {}
        self.time_series_data = {'timestamps': [], 'regional_data': {}}
        
        # 初始化其他属性
        self.simulation_running = False
        self.simulation_paused = False
        self.metrics_history = {
            'timestamps': [],
            'userSatisfaction': [],
            'operatorProfit': [],
            'gridFriendliness': [],
            'totalReward': []
        }
        self.time_series_collector = {
            'timestamps': [],
            'regional_data': {}
        }
        
        # 先设置UI，这会创建所有的UI组件
        self.setupUI()
        
        # 然后设置连接，这需要UI组件已经存在
        self.setupConnections()
        
        # 最后创建定时器，这可能需要连接到已定义的方法
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.updateDisplays)

    def updateDisplays(self):
        """更新显示 - 定时器调用"""
        # 更新进度条
        if self.simulation_running and hasattr(self, 'simulation_worker') and self.simulation_worker:
            # 这里可以根据实际仿真进度更新进度条
            # 暂时使用模拟进度
            current_value = self.progress_bar.value()
            if current_value < 100:
                self.progress_bar.setValueAnimated(current_value + 1)
            else:
                self.progress_bar.setValueAnimated(0)
        
        # 更新其他需要定期刷新的显示
        # 例如，更新状态标签、检查仿真状态等

    def updateConfig(self):
        """更新配置 - 当UI控件改变时调用"""
        # 从UI控件更新配置
        algorithm = self.algorithm_combo.currentText()
        self.config['scheduler']['scheduling_algorithm'] = algorithm
        
        # 根据策略更新权重
        strategy = self.strategy_combo.currentText()
        if strategy == "user_first":
            weights = {"user_satisfaction": 0.6, "operator_profit": 0.2, "grid_friendliness": 0.2}
        elif strategy == "profit_first":
            weights = {"user_satisfaction": 0.2, "operator_profit": 0.6, "grid_friendliness": 0.2}
        elif strategy == "grid_first":
            weights = {"user_satisfaction": 0.2, "operator_profit": 0.2, "grid_friendliness": 0.6}
        else:  # balanced
            weights = {"user_satisfaction": 0.33, "operator_profit": 0.33, "grid_friendliness": 0.34}
        
        self.config['scheduler']['optimization_weights'] = weights
        
        logger.info(f"配置已更新: 算法={algorithm}, 策略={strategy}")
    def openConfig(self):
        """打开配置文件"""
        filename, _ = QFileDialog.getOpenFileName(
            self, "打开配置", "", "JSON files (*.json)"
        )
        if filename:
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    self.config = json.load(f)
                self.updateConfigUI()
                QMessageBox.information(self, "成功", "配置文件已加载")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"加载配置失败:\n{str(e)}")

    def saveConfig(self):
        """保存配置文件"""
        filename, _ = QFileDialog.getSaveFileName(
            self, "保存配置", "config.json", "JSON files (*.json)"
        )
        if filename:
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(self.config, f, indent=2, ensure_ascii=False)
                QMessageBox.information(self, "成功", "配置文件已保存")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"保存配置失败:\n{str(e)}")

    def showAbout(self):
        """显示关于对话框"""
        QMessageBox.about(self, "关于", 
            "EV充电调度仿真系统\n\n"
            "版本: 1.0\n"
            "基于PyQt6开发\n"
            "支持多种调度算法和策略\n\n"
            "功能特点:\n"
            "• 实时仿真监控\n"
            "• 多区域电网模型\n"
            "• 动态地图显示\n"
            "• 智能调度算法\n"
            "• 数据分析与导出"
        )

    def showConfig(self):
        """显示配置对话框"""
        dialog = ConfigDialog(self.config, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.config = dialog.getConfig()
            self.updateConfigUI()

    def updateConfigUI(self):
        """更新配置UI"""
        algorithm = self.config['scheduler']['scheduling_algorithm']
        index = self.algorithm_combo.findText(algorithm)
        if index >= 0:
            self.algorithm_combo.setCurrentIndex(index)
    # 在MainWindow类中添加updateConfig方法

    def updateConfig(self):
        """更新配置 - 当UI控件改变时调用"""
        # 从UI控件更新配置
        algorithm = self.algorithm_combo.currentText()
        self.config['scheduler']['scheduling_algorithm'] = algorithm
        
        # 根据策略更新权重
        strategy = self.strategy_combo.currentText()
        if strategy == "user_first":
            weights = {"user_satisfaction": 0.6, "operator_profit": 0.2, "grid_friendliness": 0.2}
        elif strategy == "profit_first":
            weights = {"user_satisfaction": 0.2, "operator_profit": 0.6, "grid_friendliness": 0.2}
        elif strategy == "grid_first":
            weights = {"user_satisfaction": 0.2, "operator_profit": 0.2, "grid_friendliness": 0.6}
        else:  # balanced
            weights = {"user_satisfaction": 0.33, "operator_profit": 0.33, "grid_friendliness": 0.34}
        
        self.config['scheduler']['optimization_weights'] = weights
        
        logger.info(f"配置已更新: 算法={algorithm}, 策略={strategy}")
    # 在 ev_charging_gui.py 的 MainWindow 类中添加

    def _createDataTab(self):
        """创建数据详情选项卡"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # 添加提示信息
        info_label = QLabel("💡 提示：数据表格会定期更新，您可以调整显示行数和筛选条件来优化性能")
        info_label.setStyleSheet("""
            QLabel {
                background: #e3f2fd;
                border: 1px solid #1976d2;
                border-radius: 4px;
                padding: 8px;
                color: #1976d2;
            }
        """)
        layout.addWidget(info_label)
        
        # 使用优化后的数据表格
        from advanced_charts import RealTimeDataTable
        self.data_table_widget = RealTimeDataTable()
        
        # 添加状态栏引用
        self.data_table_widget.statusBar = self.statusBar
        
        layout.addWidget(self.data_table_widget)
        
        return widget
    def exportData(self):
        """导出数据"""
        filename, _ = QFileDialog.getSaveFileName(
            self, "导出数据", "simulation_data.json", "JSON files (*.json)"
        )
        if filename:
            try:
                data = {
                    'config': self.config,
                    'metrics': self.current_metrics,
                    'timestamp': datetime.now().isoformat()
                }
                
                # 添加时间序列数据
                if hasattr(self, 'time_series_collector'):
                    data['time_series'] = self.time_series_collector
                
                # 添加指标历史
                if hasattr(self, 'metrics_history'):
                    data['metrics_history'] = self.metrics_history
                
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                QMessageBox.information(self, "成功", "数据已导出")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"导出数据失败:\n{str(e)}")

    def updateCurrentTime(self):
        """更新当前时间显示"""
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        if hasattr(self, 'current_time_label'):
            self.current_time_label.setText(current_time)

    def closeEvent(self, event):
        """窗口关闭事件"""
        if self.simulation_running:
            reply = QMessageBox.question(
                self, "确认", "仿真正在运行，确定要退出吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.stopSimulation()
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()
    def setupUI(self):
        """设置用户界面"""
        self.setWindowTitle("EV充电调度仿真系统")
        self.setWindowIcon(QIcon("icon.png"))  # 需要准备图标文件
        self.resize(1400, 900)
        
        # 创建中央widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 主布局
        main_layout = QHBoxLayout(central_widget)
        
        # 创建分割器
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(main_splitter)
        
        # 左侧控制面板
        left_panel = self._createLeftPanel()
        main_splitter.addWidget(left_panel)
        
        # 右侧内容区域
        right_panel = self._createRightPanel()
        main_splitter.addWidget(right_panel)
        
        # 设置分割器比例
        main_splitter.setStretchFactor(0, 0)  # 左侧固定宽度
        main_splitter.setStretchFactor(1, 1)  # 右侧可伸缩
        main_splitter.setSizes([350, 1050])
        
        # 创建菜单栏
        self._createMenuBar()
        
        # 创建工具栏
        self._createToolBar()
        
        # 创建状态栏
        self._createStatusBar()
        
    def _createLeftPanel(self):
        """创建左侧控制面板"""
        panel = QWidget()
        panel.setFixedWidth(350)
        panel.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #f8f9fa, stop:1 #e9ecef);
            }
        """)
        
        layout = QVBoxLayout(panel)
        layout.setSpacing(15)
        
        # 控制区域
        control_group = self._createControlGroup()
        layout.addWidget(control_group)
        
        # 指标区域
        metrics_group = self._createMetricsGroup()
        layout.addWidget(metrics_group)
        
        # 配置区域
        config_group = self._createConfigGroup()
        layout.addWidget(config_group)
        
        layout.addStretch()
        
        return panel
    
    def _createControlGroup(self):
        """创建控制组"""
        group = QGroupBox("仿真控制")
        group.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        layout = QVBoxLayout(group)
        
        # 控制按钮
        button_layout = QHBoxLayout()
        
        self.start_button = QPushButton("启动")
        self.start_button.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #27ae60, stop:1 #2ecc71);
                color: white;
                border: none;
                border-radius: 8px;
                padding: 12px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #229954, stop:1 #27ae60);
            }
            QPushButton:pressed {
                background: #1e8449;
            }
            QPushButton:disabled {
                background: #bdc3c7;
            }
        """)
        
        self.pause_button = QPushButton("暂停")
        self.pause_button.setEnabled(False)
        self.pause_button.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #f39c12, stop:1 #e67e22);
                color: white;
                border: none;
                border-radius: 8px;
                padding: 12px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #e67e22, stop:1 #d35400);
            }
            QPushButton:disabled {
                background: #bdc3c7;
            }
        """)
        
        self.stop_button = QPushButton("停止")
        self.stop_button.setEnabled(False)
        self.stop_button.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #e74c3c, stop:1 #c0392b);
                color: white;
                border: none;
                border-radius: 8px;
                padding: 12px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #c0392b, stop:1 #a93226);
            }
            QPushButton:disabled {
                background: #bdc3c7;
            }
        """)
        
        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.pause_button)
        button_layout.addWidget(self.stop_button)
        layout.addLayout(button_layout)
        
        # 进度条
        self.progress_bar = AnimatedProgressBar()
        self.progress_bar.setRange(0, 100)
        layout.addWidget(self.progress_bar)
        
        # 状态信息
        self.status_label = QLabel("就绪")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("""
            QLabel {
                background: #ecf0f1;
                border: 1px solid #bdc3c7;
                border-radius: 6px;
                padding: 8px;
                font-weight: bold;
            }
        """)
        layout.addWidget(self.status_label)
        
        # 时间显示
        time_layout = QHBoxLayout()
        time_layout.addWidget(QLabel("仿真时间:"))
        self.time_label = QLabel("00:00:00")
        self.time_label.setFont(QFont("Courier", 12, QFont.Weight.Bold))
        time_layout.addWidget(self.time_label)
        layout.addLayout(time_layout)
        
        return group
    
    def _createMetricsGroup(self):
        """创建指标组"""
        group = QGroupBox("实时指标")
        group.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        layout = QVBoxLayout(group)
        
        # 指标卡片
        self.user_satisfaction_card = MetricCard("用户满意度", 0.0)
        self.operator_profit_card = MetricCard("运营商利润", 0.0)
        self.grid_friendliness_card = MetricCard("电网友好度", 0.0)
        self.total_score_card = MetricCard("综合评分", 0.0)
        
        layout.addWidget(self.user_satisfaction_card)
        layout.addWidget(self.operator_profit_card)
        layout.addWidget(self.grid_friendliness_card)
        layout.addWidget(self.total_score_card)
        
        return group
    
    def _createConfigGroup(self):
        """创建配置组"""
        group = QGroupBox("快速配置")
        group.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        layout = QVBoxLayout(group)
        
        # 算法选择
        algo_layout = QHBoxLayout()
        algo_layout.addWidget(QLabel("算法:"))
        self.algorithm_combo = QComboBox()
        self.algorithm_combo.addItems([
            "rule_based", "uncoordinated",
            "coordinated_mas", "marl"
        ])
        algo_layout.addWidget(self.algorithm_combo)
        layout.addLayout(algo_layout)
        
        # 策略选择
        strategy_layout = QHBoxLayout()
        strategy_layout.addWidget(QLabel("策略:"))
        self.strategy_combo = QComboBox()
        self.strategy_combo.addItems([
            "balanced", "user_first",
            "profit_first", "grid_first"
        ])
        strategy_layout.addWidget(self.strategy_combo)
        layout.addLayout(strategy_layout)
        
        # 高级配置按钮
        self.config_button = QPushButton("高级配置")
        self.config_button.setStyleSheet("""
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
        layout.addWidget(self.config_button)
        
        return group
    
    def _createRightPanel(self):
        """创建右侧面板"""
        panel = QWidget()
        
        # 创建选项卡widget
        tab_widget = QTabWidget()
        tab_widget.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #c0c4c8;
                background: white;
            }
            QTabBar::tab {
                background: #f1f3f4;
                padding: 12px 20px;
                margin-right: 2px;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
            }
            QTabBar::tab:selected {
                background: #3498db;
                color: white;
            }
            QTabBar::tab:hover {
                background: #5dade2;
                color: white;
            }
        """)
        
        # 图表选项卡
        charts_tab = self._createChartsTab()
        tab_widget.addTab(charts_tab, "📊 图表分析")
        
        # 地图选项卡
        map_tab = self._createMapTab()
        tab_widget.addTab(map_tab, "🗺️ 实时地图")
        
        # 数据选项卡
        data_tab = self._createDataTab()
        tab_widget.addTab(data_tab, "📋 数据详情")
        
        layout = QVBoxLayout(panel)
        layout.addWidget(tab_widget)
        
        return panel
    
    def _createChartsTab(self):
        """创建图表选项卡"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # 导入高级图表组件
        from advanced_charts import RegionalLoadHeatmap, MultiMetricsChart
        
        # 创建分割器
        splitter = QSplitter(Qt.Orientation.Vertical)
        
        # 区域负载热力图
        self.regional_heatmap = RegionalLoadHeatmap()
        splitter.addWidget(self.regional_heatmap)
        
        # 多指标趋势图
        self.multi_metrics_chart = MultiMetricsChart()
        splitter.addWidget(self.multi_metrics_chart)
        
        # 如果有pyqtgraph，添加等待时间分布图
        if HAS_PYQTGRAPH:
            self.wait_time_chart = self._createWaitTimeChart()
            splitter.addWidget(self.wait_time_chart)
        
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        if HAS_PYQTGRAPH:
            splitter.setStretchFactor(2, 1)
        
        layout.addWidget(splitter)
        return widget

    def _createWaitTimeChart(self):
        """创建等待时间分布图"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # 标题
        title = QLabel("用户等待时间分布")
        title.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        layout.addWidget(title)
        
        # 图表
        plot_widget = PlotWidget()
        plot_widget.setBackground('w')
        plot_widget.setLabel('left', '用户数量')
        plot_widget.setLabel('bottom', '等待时间(分钟)')
        plot_widget.showGrid(x=True, y=True, alpha=0.3)
        
        # 存储引用以便后续更新
        self.wait_time_plot = plot_widget
        
        layout.addWidget(plot_widget)
        return widget

    # 在_createMapTab方法中，添加按钮功能

    def _createMapTab(self):
        """创建地图选项卡"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # 地图控制栏
        control_bar = QHBoxLayout()
        
        # 缩放控制
        control_bar.addWidget(QLabel("缩放:"))
        zoom_in_btn = QPushButton("🔍+")
        zoom_out_btn = QPushButton("🔍-")
        reset_btn = QPushButton("重置")
        
        # 连接按钮功能
        zoom_in_btn.clicked.connect(lambda: self._zoomMap(1.2))
        zoom_out_btn.clicked.connect(lambda: self._zoomMap(0.8))
        reset_btn.clicked.connect(self._resetMap)
        
        control_bar.addWidget(zoom_in_btn)
        control_bar.addWidget(zoom_out_btn)
        control_bar.addWidget(reset_btn)
        control_bar.addStretch()
        
        # 图层控制
        self.show_users_cb = QCheckBox("显示用户")
        self.show_users_cb.setChecked(True)
        self.show_users_cb.stateChanged.connect(self._updateMapLayers)
        
        self.show_chargers_cb = QCheckBox("显示充电桩")
        self.show_chargers_cb.setChecked(True)
        self.show_chargers_cb.stateChanged.connect(self._updateMapLayers)
        
        control_bar.addWidget(self.show_users_cb)
        control_bar.addWidget(self.show_chargers_cb)
        
        layout.addLayout(control_bar)
        
        # 地图widget
        self.map_widget = MapWidget()
        layout.addWidget(self.map_widget)
        
        return widget

    def _zoomMap(self, factor):
        """缩放地图"""
        if hasattr(self, 'map_widget'):
            self.map_widget.zoom_level *= factor
            self.map_widget.zoom_level = max(0.5, min(5.0, self.map_widget.zoom_level))
            self.map_widget.update()

    def _resetMap(self):
        """重置地图视图"""
        if hasattr(self, 'map_widget'):
            self.map_widget.zoom_level = 1.0
            self.map_widget.offset_x = 0
            self.map_widget.offset_y = 0
            self.map_widget.update()

    def _updateMapLayers(self):
        """更新地图图层显示"""
        # 这里可以实现显示/隐藏用户和充电桩的功能
        pass

    def _createDataTab(self):
        """创建数据详情选项卡"""
        # 使用advanced_charts.py中的RealTimeDataTable
        from advanced_charts import RealTimeDataTable
        
        self.data_table_widget = RealTimeDataTable()
        return self.data_table_widget
    
    def _createMenuBar(self):
        """创建菜单栏"""
        menubar = self.menuBar()
        
        # 文件菜单
        file_menu = menubar.addMenu("文件")
        
        new_action = QAction("新建", self)
        new_action.setShortcut("Ctrl+N")
        file_menu.addAction(new_action)
        
        open_action = QAction("打开", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self.openConfig)
        file_menu.addAction(open_action)
        
        save_action = QAction("保存", self)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self.saveConfig)
        file_menu.addAction(save_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("退出", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # 仿真菜单
        sim_menu = menubar.addMenu("仿真")
        
        start_action = QAction("启动仿真", self)
        start_action.setShortcut("F5")
        start_action.triggered.connect(self.startSimulation)
        sim_menu.addAction(start_action)
        
        pause_action = QAction("暂停仿真", self)
        pause_action.setShortcut("F6")
        pause_action.triggered.connect(self.pauseSimulation)
        sim_menu.addAction(pause_action)
        
        stop_action = QAction("停止仿真", self)
        stop_action.setShortcut("F7")
        stop_action.triggered.connect(self.stopSimulation)
        sim_menu.addAction(stop_action)
        
        # 帮助菜单
        help_menu = menubar.addMenu("帮助")
        
        about_action = QAction("关于", self)
        about_action.triggered.connect(self.showAbout)
        help_menu.addAction(about_action)
    
    def _createToolBar(self):
        """创建工具栏"""
        toolbar = self.addToolBar("主工具栏")
        
        # 仿真控制工具
        toolbar.addAction("▶️", self.startSimulation)
        toolbar.addAction("⏸️", self.pauseSimulation)
        toolbar.addAction("⏹️", self.stopSimulation)
        toolbar.addSeparator()
        
        # 配置工具
        toolbar.addAction("⚙️", self.showConfig)
        toolbar.addSeparator()
        
        # 导出工具
        toolbar.addAction("💾", self.exportData)
    
    def _createStatusBar(self):
        """创建状态栏"""
        statusbar = self.statusBar()
        
        # 仿真状态
        self.sim_status_label = QLabel("就绪")
        statusbar.addWidget(self.sim_status_label)
        
        statusbar.addPermanentWidget(QLabel("|"))
        
        # 连接状态
        self.connection_label = QLabel("未连接")
        statusbar.addPermanentWidget(self.connection_label)
        
        statusbar.addPermanentWidget(QLabel("|"))
        
        # 时间显示
        self.current_time_label = QLabel()
        self.updateCurrentTime()
        statusbar.addPermanentWidget(self.current_time_label)
        
        # 定时更新当前时间 - 保存定时器引用
        self.time_timer = QTimer()
        self.time_timer.timeout.connect(self.updateCurrentTime)
        self.time_timer.start(1000)
    
    def setupConnections(self):
        """设置信号连接"""
        # 按钮连接
        self.start_button.clicked.connect(self.startSimulation)
        self.pause_button.clicked.connect(self.pauseSimulation)
        self.stop_button.clicked.connect(self.stopSimulation)
        self.config_button.clicked.connect(self.showConfig)
        
        # 组合框连接
        self.algorithm_combo.currentTextChanged.connect(self.updateConfig)
        self.strategy_combo.currentTextChanged.connect(self.updateConfig)
    
    def _loadDefaultConfig(self):
        """加载默认配置"""
        default_config = {
            "environment": {
                "simulation_days": 7,
                "user_count": 1000,
                "station_count": 20,
                "chargers_per_station": 10,
                "time_step_minutes": 15,
                "map_bounds": {
                    "lat_min": 30.5, "lat_max": 31.0,
                    "lng_min": 114.0, "lng_max": 114.5
                }
            },
            "scheduler": {
                "scheduling_algorithm": "rule_based",
                "optimization_weights": {
                    "user_satisfaction": 0.33,
                    "operator_profit": 0.33,
                    "grid_friendliness": 0.34
                }
            },
            "grid": {
                "normal_price": 0.85,
                "peak_price": 1.2,
                "valley_price": 0.4,
                "peak_hours": [7, 8, 9, 10, 18, 19, 20, 21],
                "valley_hours": [0, 1, 2, 3, 4, 5],
                "base_load": {
                    "region_0": [800, 750, 700, 650, 600, 650, 750, 900, 1000, 1100, 1150, 1200,
                               1250, 1200, 1150, 1100, 1200, 1300, 1250, 1150, 1050, 950, 900, 850],
                    "region_1": [600, 550, 500, 450, 400, 450, 550, 700, 800, 900, 950, 1000,
                               1050, 1000, 950, 900, 1000, 1100, 1050, 950, 850, 750, 700, 650]
                },
                "solar_generation": {
                    "region_0": [0, 0, 0, 0, 0, 0, 50, 150, 300, 450, 550, 600,
                               650, 600, 550, 450, 300, 150, 50, 0, 0, 0, 0, 0],
                    "region_1": [0, 0, 0, 0, 0, 0, 40, 120, 250, 380, 480, 520,
                               560, 520, 480, 380, 250, 120, 40, 0, 0, 0, 0, 0]
                },
                "wind_generation": {
                    "region_0": [200, 180, 160, 140, 120, 130, 150, 170, 160, 140, 120, 110,
                               100, 110, 120, 140, 160, 180, 200, 220, 240, 230, 220, 210],
                    "region_1": [150, 140, 130, 120, 110, 120, 130, 140, 130, 120, 110, 100,
                               90, 100, 110, 120, 130, 140, 150, 160, 170, 165, 160, 155]
                },
                "system_capacity_kw": {
                    "region_0": 2000,
                    "region_1": 1500
                }
            }
        }
        return default_config
    
    def startSimulation(self):
        """启动仿真"""
        if self.simulation_running:
            return
        
        try:
            # 创建仿真工作线程
            self.simulation_worker = SimulationWorker(self.config)
            
            # 连接信号
            self.simulation_worker.statusUpdated.connect(self.onStatusUpdated)
            self.simulation_worker.metricsUpdated.connect(self.onMetricsUpdated)
            self.simulation_worker.errorOccurred.connect(self.onErrorOccurred)
            self.simulation_worker.simulationFinished.connect(self.onSimulationFinished)
            
            # 启动线程
            self.simulation_worker.start()
            
            # 更新UI状态
            self.simulation_running = True
            self.simulation_paused = False
            
            self.start_button.setEnabled(False)
            self.pause_button.setEnabled(True)
            self.stop_button.setEnabled(True)
            
            self.status_label.setText("运行中")
            self.status_label.setStyleSheet("""
                QLabel {
                    background: #d5f4e6;
                    border: 1px solid #27ae60;
                    border-radius: 6px;
                    padding: 8px;
                    font-weight: bold;
                    color: #27ae60;
                }
            """)
            
            self.sim_status_label.setText("仿真运行中")
            
            # 启动显示更新定时器
            self.update_timer.start(1000)
            
            logger.info("仿真已启动")
            
        except Exception as e:
            logger.error(f"启动仿真失败: {e}")
            QMessageBox.critical(self, "错误", f"启动仿真失败:\n{str(e)}")
    
    def pauseSimulation(self):
        """暂停/恢复仿真"""
        if not self.simulation_worker:
            return
        
        if self.simulation_paused:
            # 恢复
            self.simulation_worker.resume()
            self.simulation_paused = False
            self.pause_button.setText("暂停")
            self.status_label.setText("运行中")
            self.status_label.setStyleSheet("""
                QLabel {
                    background: #d5f4e6;
                    border: 1px solid #27ae60;
                    border-radius: 6px;
                    padding: 8px;
                    font-weight: bold;
                    color: #27ae60;
                }
            """)
        else:
            # 暂停
            self.simulation_worker.pause()
            self.simulation_paused = True
            self.pause_button.setText("恢复")
            self.status_label.setText("已暂停")
            self.status_label.setStyleSheet("""
                QLabel {
                    background: #fdeaa7;
                    border: 1px solid #f39c12;
                    border-radius: 6px;
                    padding: 8px;
                    font-weight: bold;
                    color: #f39c12;
                }
            """)
    
    def stopSimulation(self):
        """停止仿真"""
        if not self.simulation_running:
            return
        
        if self.simulation_worker:
            self.simulation_worker.stop()
            self.simulation_worker.wait()  # 等待线程结束
            self.simulation_worker = None
        
        # 更新UI状态
        self.simulation_running = False
        self.simulation_paused = False
        
        self.start_button.setEnabled(True)
        self.pause_button.setEnabled(False)
        self.pause_button.setText("暂停")
        self.stop_button.setEnabled(False)
        
        self.status_label.setText("已停止")
        self.status_label.setStyleSheet("""
            QLabel {
                background: #fadbd8;
                border: 1px solid #e74c3c;
                border-radius: 6px;
                padding: 8px;
                font-weight: bold;
                color: #e74c3c;
            }
        """)
        
        self.sim_status_label.setText("仿真已停止")
        
        # 停止更新定时器
        self.update_timer.stop()
        
        logger.info("仿真已停止")
    
    # 在MainWindow类中，更新onStatusUpdated方法

    def onStatusUpdated(self, status_data):
        """处理状态更新"""
        try:
            state = status_data.get('state', {})
            rewards = status_data.get('rewards', {})
            timestamp = status_data.get('timestamp', '')
            
            # 更新时间显示
            if timestamp:
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                self.time_label.setText(dt.strftime('%H:%M:%S'))
            
            # 更新地图
            users = state.get('users', [])
            chargers = state.get('chargers', [])
            self.map_widget.updateData(users, chargers)
            
            # 更新数据表
            if hasattr(self, 'data_table_widget'):
                self.data_table_widget.updateData(state)
            
            # 处理电网数据用于热力图
            grid_status = state.get('grid_status', {})
            
            # 更新区域负载热力图
            if hasattr(self, 'regional_heatmap'):
                # 构建时间序列数据
                if not hasattr(self, 'time_series_collector'):
                    self.time_series_collector = {
                        'timestamps': [],
                        'regional_data': {}
                    }
                
                # 添加新的时间戳
                self.time_series_collector['timestamps'].append(timestamp)
                
                # 限制历史数据长度
                max_points = 288  # 72小时，15分钟间隔
                if len(self.time_series_collector['timestamps']) > max_points:
                    self.time_series_collector['timestamps'] = self.time_series_collector['timestamps'][-max_points:]
                
                # 收集区域数据
                regional_state = grid_status.get('regional_current_state', {})
                for region_id, region_data in regional_state.items():
                    if region_id not in self.time_series_collector['regional_data']:
                        self.time_series_collector['regional_data'][region_id] = {
                            'total_load': [],
                            'base_load': [],
                            'ev_load': [],
                            'renewable_ratio': [],
                            'grid_load_percentage': []
                        }
                    
                    region_collector = self.time_series_collector['regional_data'][region_id]
                    region_collector['total_load'].append(region_data.get('current_total_load', 0))
                    region_collector['base_load'].append(region_data.get('current_base_load', 0))
                    region_collector['ev_load'].append(region_data.get('current_ev_load', 0))
                    region_collector['renewable_ratio'].append(region_data.get('renewable_ratio', 0))
                    region_collector['grid_load_percentage'].append(region_data.get('grid_load_percentage', 0))
                    
                    # 限制长度
                    for key in region_collector:
                        if len(region_collector[key]) > max_points:
                            region_collector[key] = region_collector[key][-max_points:]
                
                # 更新热力图
                self.regional_heatmap.updateData(self.time_series_collector)
            
            # 更新等待时间分布
            if hasattr(self, 'wait_time_plot'):
                self._updateWaitTimeChart(users)
            
        except Exception as e:
            logger.error(f"状态更新错误: {e}")
            logger.error(traceback.format_exc())

    def _updateWaitTimeChart(self, users):
        """更新等待时间分布图"""
        if not hasattr(self, 'wait_time_plot'):
            return
        
        # 统计等待时间分布
        wait_times = []
        for user in users:
            if user.get('status') == 'waiting' and 'arrival_time_at_charger' in user:
                # 计算等待时间（这里简化处理）
                wait_time = random.uniform(0, 60)  # 实际应该根据arrival_time计算
                wait_times.append(wait_time)
        
        if wait_times:
            # 创建直方图数据
            hist, bins = np.histogram(wait_times, bins=10)
            
            # 清除旧数据
            self.wait_time_plot.clear()
            
            # 绘制柱状图
            bar_width = (bins[1] - bins[0]) * 0.8
            bar_graph = pg.BarGraphItem(
                x=bins[:-1], 
                height=hist, 
                width=bar_width, 
                brush=(52, 152, 219)
            )
            
            self.wait_time_plot.addItem(bar_graph)


    def onMetricsUpdated(self, metrics):
        """处理指标更新"""
        try:
            self.current_metrics = metrics
            
            # 更新指标卡片
            user_satisfaction = metrics.get('user_satisfaction', 0)
            operator_profit = metrics.get('operator_profit', 0)
            grid_friendliness = metrics.get('grid_friendliness', 0)
            total_reward = metrics.get('total_reward', 0)
            
            # 计算趋势
            if not hasattr(self, 'metrics_history'):
                self.metrics_history = {
                    'timestamps': [],
                    'userSatisfaction': [],
                    'operatorProfit': [],
                    'gridFriendliness': [],
                    'totalReward': []
                }
            
            # 添加到历史记录
            self.metrics_history['timestamps'].append(datetime.now().isoformat())
            self.metrics_history['userSatisfaction'].append(user_satisfaction)
            self.metrics_history['operatorProfit'].append(operator_profit)
            self.metrics_history['gridFriendliness'].append(grid_friendliness)
            self.metrics_history['totalReward'].append(total_reward)
            
            # 限制历史长度
            max_history = 100
            for key in self.metrics_history:
                if len(self.metrics_history[key]) > max_history:
                    self.metrics_history[key] = self.metrics_history[key][-max_history:]
            
            # 计算趋势（与前一个值比较）
            def calculate_trend(values):
                if len(values) < 2:
                    return 0
                return ((values[-1] - values[-2]) / abs(values[-2]) * 100) if values[-2] != 0 else 0
            
            user_trend = calculate_trend(self.metrics_history['userSatisfaction'])
            profit_trend = calculate_trend(self.metrics_history['operatorProfit'])
            grid_trend = calculate_trend(self.metrics_history['gridFriendliness'])
            total_trend = calculate_trend(self.metrics_history['totalReward'])
            
            # 更新卡片显示
            self.user_satisfaction_card.updateValue(user_satisfaction, user_trend)
            self.operator_profit_card.updateValue(operator_profit, profit_trend)
            self.grid_friendliness_card.updateValue(grid_friendliness, grid_trend)
            self.total_score_card.updateValue(total_reward, total_trend)
            
            # 更新多指标图表
            if hasattr(self, 'multi_metrics_chart'):
                self.multi_metrics_chart.updateData(self.metrics_history)
                
        except Exception as e:
            logger.error(f"指标更新错误: {e}")
            logger.error(traceback.format_exc())
    def onErrorOccurred(self, error_msg):
        """处理错误"""
        logger.error(f"仿真错误: {error_msg}")
        QMessageBox.critical(self, "仿真错误", error_msg)
        self.stopSimulation()
    
    def onSimulationFinished(self):
        """处理仿真完成"""
        self.stopSimulation()
        QMessageBox.information(self, "完成", "仿真已完成!")
    
    def showConfig(self):
        """显示配置对话框"""
        dialog = ConfigDialog(self.config, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.config = dialog.getConfig()
            self.updateConfigUI()
    
    def updateConfig(self):
        """更新配置"""
        # 从UI控件更新配置
        algorithm = self.algorithm_combo.currentText()
        self.config['scheduler']['scheduling_algorithm'] = algorithm
        
        # 根据策略更新权重
        strategy = self.strategy_combo.currentText()
        if strategy == "user_first":
            weights = {"user_satisfaction": 0.6, "operator_profit": 0.2, "grid_friendliness": 0.2}
        elif strategy == "profit_first":
            weights = {"user_satisfaction": 0.2, "operator_profit": 0.6, "grid_friendliness": 0.2}
        elif strategy == "grid_first":
            weights = {"user_satisfaction": 0.2, "operator_profit": 0.2, "grid_friendliness": 0.6}
        else:  # balanced
            weights = {"user_satisfaction": 0.33, "operator_profit": 0.33, "grid_friendliness": 0.34}
        
        self.config['scheduler']['optimization_weights'] = weights
    
    def updateConfigUI(self):
        """更新配置UI"""
        algorithm = self.config['scheduler']['scheduling_algorithm']
        index = self.algorithm_combo.findText(algorithm)
        if index >= 0:
            self.algorithm_combo.setCurrentIndex(index)
    
    def updateDisplays(self):
        """更新显示 - 定时器调用"""
        # 更新进度条
        if self.simulation_running and hasattr(self, 'simulation_worker') and self.simulation_worker:
            # 这里可以根据实际仿真进度更新进度条
            # 暂时使用模拟进度
            current_value = self.progress_bar.value()
            if current_value < 100:
                self.progress_bar.setValueAnimated(current_value + 1)
            else:
                self.progress_bar.setValueAnimated(0)
    
    def updateCurrentTime(self):
        """更新当前时间显示"""
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.current_time_label.setText(current_time)
    
    def openConfig(self):
        """打开配置文件"""
        filename, _ = QFileDialog.getOpenFileName(
            self, "打开配置", "", "JSON files (*.json)"
        )
        if filename:
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    self.config = json.load(f)
                self.updateConfigUI()
                QMessageBox.information(self, "成功", "配置文件已加载")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"加载配置失败:\n{str(e)}")
    
    def saveConfig(self):
        """保存配置文件"""
        filename, _ = QFileDialog.getSaveFileName(
            self, "保存配置", "config.json", "JSON files (*.json)"
        )
        if filename:
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(self.config, f, indent=2, ensure_ascii=False)
                QMessageBox.information(self, "成功", "配置文件已保存")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"保存配置失败:\n{str(e)}")
    
    def exportData(self):
        """导出数据"""
        filename, _ = QFileDialog.getSaveFileName(
            self, "导出数据", "simulation_data.json", "JSON files (*.json)"
        )
        if filename:
            try:
                data = {
                    'config': self.config,
                    'metrics': self.current_metrics,
                    'time_series': self.time_series_data,
                    'timestamp': datetime.now().isoformat()
                }
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                QMessageBox.information(self, "成功", "数据已导出")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"导出数据失败:\n{str(e)}")
    
    def showAbout(self):
        """显示关于对话框"""
        QMessageBox.about(self, "关于", 
            "EV充电调度仿真系统\n\n"
            "版本: 1.0\n"
            "基于PyQt6开发\n"
            "支持多种调度算法和策略\n\n"
            "功能特点:\n"
            "• 实时仿真监控\n"
            "• 多区域电网模型\n"
            "• 动态地图显示\n"
            "• 智能调度算法\n"
            "• 数据分析与导出"
        )
    
    def closeEvent(self, event):
        """窗口关闭事件"""
        if self.simulation_running:
            reply = QMessageBox.question(
                self, "确认", "仿真正在运行，确定要退出吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.stopSimulation()
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()


def main():
    """主函数"""
    # 设置高DPI支持
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_Use96Dpi)
    
    app = QApplication(sys.argv)
    
    # 设置应用程序信息
    app.setApplicationName("EV充电调度仿真系统")
    app.setApplicationVersion("1.0")
    app.setOrganizationName("EV Simulation Lab")
    
    # 设置样式
    app.setStyle('Fusion')
    
    # 应用深色主题（可选）
    dark_palette = QPalette()
    dark_palette.setColor(QPalette.ColorRole.Window, QColor(53, 53, 53))
    dark_palette.setColor(QPalette.ColorRole.WindowText, QColor(255, 255, 255))
    dark_palette.setColor(QPalette.ColorRole.Base, QColor(25, 25, 25))
    dark_palette.setColor(QPalette.ColorRole.AlternateBase, QColor(53, 53, 53))
    dark_palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(0, 0, 0))
    dark_palette.setColor(QPalette.ColorRole.ToolTipText, QColor(255, 255, 255))
    dark_palette.setColor(QPalette.ColorRole.Text, QColor(255, 255, 255))
    dark_palette.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
    dark_palette.setColor(QPalette.ColorRole.ButtonText, QColor(255, 255, 255))
    dark_palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 0, 0))
    dark_palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
    dark_palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
    dark_palette.setColor(QPalette.ColorRole.HighlightedText, QColor(0, 0, 0))
    
    # 可选择应用深色主题
    # app.setPalette(dark_palette)
    
    # 创建并显示主窗口
    window = MainWindow()
    window.show()
    
    # 运行应用程序
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
