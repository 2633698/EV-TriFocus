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
    from user_panel import UserControlPanel
except ImportError as e:
    print(f"警告：无法导入仿真模块: {e}")
    print("请确保simulation包在Python路径中")

# 配置日志
# 配置基础日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# 配置手动决策专用日志文件
manual_decision_logger = logging.getLogger('manual_decisions')
manual_decision_logger.setLevel(logging.INFO)

# 创建文件处理器，专门记录手动决策日志
manual_log_handler = logging.FileHandler('manual_decisions.log', encoding='utf-8')
manual_log_handler.setLevel(logging.INFO)
manual_log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
manual_log_handler.setFormatter(manual_log_formatter)
manual_decision_logger.addHandler(manual_log_handler)

# 防止日志重复输出到根logger
manual_decision_logger.propagate = False

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
        self.display_mode = "total"  # 默认显示总负载
        self.selected_region = None  # 当前选中的区域
        self.cached_data = None  # 缓存数据
        
        self.setupUI()
        
    def setupUI(self):
        layout = QVBoxLayout(self)
        
        # 标题和控制区域
        header_layout = QHBoxLayout()
        
        # 标题
        title = QLabel("区域电网负载实时监控")
        title.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        header_layout.addWidget(title)
        
        header_layout.addStretch()
        
        # 显示模式选择
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("总负载", "total")
        self.mode_combo.addItem("单区域", "single")
        self.mode_combo.addItem("所有区域", "all")
        self.mode_combo.currentIndexChanged.connect(self.onDisplayModeChanged)
        header_layout.addWidget(QLabel("显示模式:"))
        header_layout.addWidget(self.mode_combo)
        
        # 区域选择
        self.region_combo = QComboBox()
        self.region_combo.setEnabled(False)  # 默认禁用，只有单区域模式才启用
        self.region_combo.currentIndexChanged.connect(self.onRegionChanged)
        header_layout.addWidget(QLabel("选择区域:"))
        header_layout.addWidget(self.region_combo)
        
        layout.addLayout(header_layout)
        
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
    
    def onDisplayModeChanged(self, index):
        """当显示模式改变时触发"""
        self.display_mode = self.mode_combo.currentData()
        
        # 如果是单区域模式，启用区域选择
        self.region_combo.setEnabled(self.display_mode == "single")
        
        # 如果有缓存数据，重新渲染
        if self.cached_data:
            self.renderChart(self.cached_data)
    
    def onRegionChanged(self, index):
        """当选择的区域改变时触发"""
        if index >= 0 and self.region_combo.count() > 0:
            self.selected_region = self.region_combo.currentText()
            
            # 如果有缓存数据，重新渲染
            if self.cached_data:
                self.renderChart(self.cached_data)
    
    def updateData(self, time_series_data):
        """更新图表数据"""
        if not time_series_data or 'timestamps' not in time_series_data:
            return
        
        # 缓存数据
        self.cached_data = time_series_data
        
        # 更新区域选择下拉框
        regional_data = time_series_data.get('regional_data', {})
        regions = list(regional_data.keys())
        
        # 保存当前选中的区域
        current_region = self.region_combo.currentText() if self.region_combo.count() > 0 else None
        
        # 清空并重新填充区域下拉框
        self.region_combo.clear()
        for region in regions:
            self.region_combo.addItem(region)
        
        # 如果之前有选择的区域，尝试恢复选择
        if current_region and current_region in regions:
            self.region_combo.setCurrentText(current_region)
        elif regions:
            self.selected_region = regions[0]
        
        # 渲染图表
        self.renderChart(time_series_data)
    
    def renderChart(self, time_series_data):
        """根据显示模式渲染图表"""
        if not time_series_data or 'timestamps' not in time_series_data:
            return
            
        timestamps = time_series_data['timestamps']
        regional_data = time_series_data.get('regional_data', {})
        
        if not HAS_PYQTGRAPH or not hasattr(self, 'plot_widget'):
            # 文本显示模式
            self._renderTextMode(regional_data)
            return
        
        # 清除当前图表
        self.plot_widget.clear()
        
        # 数据采样优化 - 限制显示的数据点数量
        max_points = 100  # 最多显示100个数据点
        if len(timestamps) > max_points:
            # 计算采样步长
            step = len(timestamps) // max_points
            sampled_timestamps = timestamps[::step]
            sampled_indices = list(range(0, len(timestamps), step))
        else:
            sampled_timestamps = timestamps
            sampled_indices = list(range(len(timestamps)))
        
        # 准备X轴数据
        x_data = list(range(len(sampled_timestamps)))
        
        if self.display_mode == "total":
            # 总负载模式 - 将所有区域的负载相加
            total_load = np.zeros(len(sampled_timestamps)) if sampled_timestamps else []
            
            for region_id, data in regional_data.items():
                if 'total_load' in data and data['total_load']:
                    # 对数据进行采样
                    region_load = data['total_load']
                    if len(region_load) > max_points:
                        sampled_load = [region_load[i] for i in sampled_indices if i < len(region_load)]
                    else:
                        sampled_load = region_load
                    
                    # 确保长度一致
                    if len(sampled_load) <= len(total_load):
                        total_load[:len(sampled_load)] += np.array(sampled_load)
            
            # 绘制总负载曲线
            if len(total_load) > 0:
                pen = pg.mkPen(color=(31, 119, 180), width=3)
                self.plot_widget.plot(
                    x_data[:len(total_load)], total_load, 
                    pen=pen, 
                    name="总负载",
                    symbolBrush=(31, 119, 180),
                    symbolSize=6,  # 减小符号大小
                    symbolPen=None,  # 移除符号边框
                    skipFiniteCheck=True  # 提高性能
                )
        
        elif self.display_mode == "single" and self.selected_region:
            # 单区域模式 - 只显示选中的区域
            if self.selected_region in regional_data:
                data = regional_data[self.selected_region]
                if 'total_load' in data and data['total_load']:
                    # 对数据进行采样
                    region_load = data['total_load']
                    if len(region_load) > max_points:
                        sampled_load = [region_load[i] for i in sampled_indices if i < len(region_load)]
                    else:
                        sampled_load = region_load
                    
                    pen = pg.mkPen(color=(31, 119, 180), width=3)
                    self.plot_widget.plot(
                        x_data[:len(sampled_load)], sampled_load, 
                        pen=pen, 
                        name=self.selected_region,
                        symbolBrush=(31, 119, 180),
                        symbolSize=6,  # 减小符号大小
                        symbolPen=None  # 移除符号边框
                    )
        
        else:  # "all" 模式 - 显示所有区域，但使用更细的线条
            for i, (region_id, data) in enumerate(regional_data.items()):
                if 'total_load' in data and data['total_load']:
                    # 对数据进行采样
                    region_load = data['total_load']
                    if len(region_load) > max_points:
                        sampled_load = [region_load[i] for i in sampled_indices if i < len(region_load)]
                    else:
                        sampled_load = region_load
                    
                    color = self.colors[i % len(self.colors)]
                    pen = pg.mkPen(color=color, width=2)  # 稍微加粗线条
                    
                    self.plot_widget.plot(
                        x_data[:len(sampled_load)], sampled_load, 
                        pen=pen, 
                        name=region_id,
                        symbolBrush=color,
                        symbolSize=3,  # 进一步减小符号
                        symbol='o',  # 使用圆形符号
                        symbolPen=None,  # 无边框
                        skipFiniteCheck=True  # 跳过有限检查以提高性能
                    )
        
        # 设置X轴标签为时间
        if sampled_timestamps:
            # 生成时间标签，最多显示10个
            label_step = max(1, len(sampled_timestamps) // 10)
            x_ticks = []
            for i in range(0, len(sampled_timestamps), label_step):
                if i < len(sampled_timestamps):
                    try:
                        # 从时间戳中提取时间
                        ts = sampled_timestamps[i]
                        if isinstance(ts, str):
                            dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                            time_str = dt.strftime('%H:%M')
                        else:
                            time_str = str(i)
                        x_ticks.append((i, time_str))
                    except:
                        x_ticks.append((i, str(i)))
            
            if x_ticks:
                self.plot_widget.getAxis('bottom').setTicks([x_ticks])
    
    def _renderTextMode(self, regional_data):
        """文本显示模式下的渲染"""
        if not hasattr(self, 'text_display'):
            return
            
        if self.display_mode == "total":
            # 总负载模式
            total_current_load = 0
            for region_id, data in regional_data.items():
                if 'total_load' in data and data['total_load']:
                    total_current_load += data['total_load'][-1] if data['total_load'] else 0
            
            text = "区域总负载: {:.2f} MW\n数据点已优化显示，避免过度密集".format(total_current_load)
            
        elif self.display_mode == "single" and self.selected_region:
            # 单区域模式
            if self.selected_region in regional_data:
                data = regional_data[self.selected_region]
                current_load = data['total_load'][-1] if 'total_load' in data and data['total_load'] else 0
                text = "区域 '{0}' 负载: {1:.2f} MW\n数据点已优化显示".format(self.selected_region, current_load)
            else:
                text = "没有选中区域的数据"
        
        else:  # "all" 模式
            text = "区域负载数据（已优化显示）:\n\n"
            for region_id, data in regional_data.items():
                if 'total_load' in data and data['total_load']:
                    current_load = data['total_load'][-1] if data['total_load'] else 0
                    text += f"{region_id}: {current_load:.2f} MW\n"
        
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
        
        # 根据缩放级别调整地图边界
        center_lat = (self.map_bounds['lat_max'] + self.map_bounds['lat_min']) / 2
        center_lng = (self.map_bounds['lng_max'] + self.map_bounds['lng_min']) / 2
        
        lat_range = (self.map_bounds['lat_max'] - self.map_bounds['lat_min']) / self.zoom_level
        lng_range = (self.map_bounds['lng_max'] - self.map_bounds['lng_min']) / self.zoom_level
        
        # 计算当前显示的地图边界
        current_lat_min = center_lat - lat_range / 2
        current_lat_max = center_lat + lat_range / 2
        current_lng_min = center_lng - lng_range / 2
        current_lng_max = center_lng + lng_range / 2
        
        # 标准化到[0,1]
        x_norm = (lng - current_lng_min) / lng_range
        y_norm = (lat - current_lat_min) / lat_range
        
        # 转换为像素坐标
        x = x_norm * self.width()
        y = (1 - y_norm) * self.height()  # Y轴翻转
        
        return x, y
    
    def _screenToGeo(self, screen_pos):
        """屏幕坐标转地理坐标"""
        # 考虑偏移但不考虑缩放（因为缩放已经在_geoToPixel中处理）
        x = screen_pos.x() - self.offset_x
        y = screen_pos.y() - self.offset_y
        
        # 根据缩放级别调整地图边界
        center_lat = (self.map_bounds['lat_max'] + self.map_bounds['lat_min']) / 2
        center_lng = (self.map_bounds['lng_max'] + self.map_bounds['lng_min']) / 2
        
        lat_range = (self.map_bounds['lat_max'] - self.map_bounds['lat_min']) / self.zoom_level
        lng_range = (self.map_bounds['lng_max'] - self.map_bounds['lng_min']) / self.zoom_level
        
        # 计算当前显示的地图边界
        current_lat_min = center_lat - lat_range / 2
        current_lng_min = center_lng - lng_range / 2
        
        # 转换为地理坐标
        lng = current_lng_min + (x / self.width()) * lng_range
        lat = current_lat_min + ((self.height() - y) / self.height()) * lat_range
        
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
        old_zoom = self.zoom_level
        
        self.zoom_level *= zoom_factor
        self.zoom_level = max(0.5, min(5.0, self.zoom_level))
        
        # 缩放后的像素坐标
        pixel_after = self._geoToPixel(geo_before)
        pixel_before = [mouse_pos.x() - self.offset_x, mouse_pos.y() - self.offset_y]
        
        # 调整偏移以保持鼠标位置不变
        self.offset_x += pixel_before[0] - pixel_after[0]
        self.offset_y += pixel_before[1] - pixel_after[1]
        
        self.update()

class SimulationWorker(QThread):
    """仿真工作线程"""
    
    # 信号定义
    statusUpdated = pyqtSignal(dict)
    metricsUpdated = pyqtSignal(dict)
    errorOccurred = pyqtSignal(str)
    simulationFinished = pyqtSignal()
    environmentReady = pyqtSignal(object)  # 新增：环境准备就绪信号
    
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
            # 添加手动决策支持
            self.manual_decisions = {}
            
            # 发出环境准备就绪信号
            self.environmentReady.emit(self.environment)

            logger.info("仿真开始")
            
            while self.running:
                if self.paused:
                    time.sleep(0.1)
                    continue
                
                # 获取当前状态
                current_state = self.environment.get_current_state()
                
                # 调度决策 - 分离手动决策和算法决策
                manual_decisions = None
                if hasattr(self, 'manual_decisions') and self.manual_decisions:
                    manual_decisions = self.manual_decisions.copy()
                    self.manual_decisions.clear()  # 清除已使用的手动决策
                    logger.info(f"应用手动决策: {manual_decisions}")
                    # 记录到专用日志文件
                    manual_decision_logger.info(f"=== 仿真步骤中应用手动决策 ===")
                    manual_decision_logger.info(f"当前仿真时间: {current_state.get('current_time', 'unknown')}")
                    manual_decision_logger.info(f"手动决策内容: {manual_decisions}")
                    for user_id, charger_id in manual_decisions.items():
                        manual_decision_logger.info(f"  用户 {user_id} -> 充电桩 {charger_id}")
                
                # 获取算法决策
                decisions = self.scheduler.make_scheduling_decision(current_state, manual_decisions)
                
                # 执行一步仿真，传递手动决策
                rewards, next_state, done = self.environment.step(decisions, manual_decisions)
                
                # 记录手动决策执行结果
                if manual_decisions:
                    manual_decision_logger.info(f"=== 手动决策执行结果 ===")
                    # 获取用户列表并转换为字典格式以便查找
                    users_list = next_state.get('users', [])
                    users_dict = {user.get('user_id'): user for user in users_list if isinstance(user, dict) and 'user_id' in user}
                    
                    manual_decision_logger.info(f"状态中包含 {len(users_list)} 个用户，转换为字典后有 {len(users_dict)} 个用户")
                    
                    # 调试信息：显示用户对象的实际结构
                    if users_list and len(users_dict) == 0:
                        sample_user = users_list[0] if users_list else {}
                        manual_decision_logger.info(f"用户对象示例结构: {list(sample_user.keys()) if isinstance(sample_user, dict) else type(sample_user)}")
                    
                    for user_id, charger_id in manual_decisions.items():
                        if user_id in users_dict:
                            user_state = users_dict[user_id]
                            manual_decision_logger.info(f"用户 {user_id}:")
                            manual_decision_logger.info(f"  目标充电桩: {charger_id}")
                            manual_decision_logger.info(f"  当前状态: {user_state.get('status', 'unknown')}")
                            manual_decision_logger.info(f"  当前SOC: {user_state.get('soc', 0):.1f}%")
                            manual_decision_logger.info(f"  分配的充电桩: {user_state.get('target_charger', 'none')}")
                            if user_state.get('target_charger') == charger_id:
                                manual_decision_logger.info(f"  ✓ 手动决策成功执行")
                            else:
                                manual_decision_logger.warning(f"  ✗ 手动决策执行失败，实际分配: {user_state.get('target_charger', 'none')}")
                        else:
                            manual_decision_logger.error(f"用户 {user_id} 在执行结果中不存在")
                            # 调试信息：显示前几个用户的ID
                            if users_list:
                                sample_user_ids = [user.get('user_id', 'no_user_id') for user in users_list[:5] if isinstance(user, dict)]
                                manual_decision_logger.error(f"  可用用户ID示例: {sample_user_ids}")
                            else:
                                manual_decision_logger.error(f"  用户列表为空")
                    manual_decision_logger.info(f"=== 手动决策执行结果结束 ===")
                
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
        # 添加用户面板相关状态
        self.user_panel_active = False
        self.selected_user_id = None
        self.simulation_history = []  # 存储仿真历史状态
        self.current_simulation_step = 0
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
    
        # 新增：用户面板选项卡
        user_panel_tab = self._createUserPanelTab()
        tab_widget.addTab(user_panel_tab, "👤 用户面板")

        layout = QVBoxLayout(panel)
        layout.addWidget(tab_widget)
        
        return panel
    def _createUserPanelTab(self):
        """创建用户面板选项卡"""
        self.user_control_panel = UserControlPanel()
        
        # 连接信号
        self.user_control_panel.userSelected.connect(self.onUserSelected)
        self.user_control_panel.simulationStepChanged.connect(self.onSimulationStepChanged)
        self.user_control_panel.chargingDecisionMade.connect(self.onChargingDecisionMade)
        self.user_control_panel.decisionAppliedAndContinue.connect(self.onDecisionAppliedAndContinue)
        
        return self.user_control_panel

    # 5. 添加用户面板相关的事件处理方法
    def onUserSelected(self, user_id):
        """处理用户选择事件"""
        self.selected_user_id = user_id
        logger.info(f"用户已选择: {user_id}")
        
        # 暂停仿真以允许用户交互
        if self.simulation_running and not self.simulation_paused:
            self.pauseSimulation()
            self.user_panel_active = True
            
            # 更新状态显示
            self.status_label.setText("用户交互模式")
            self.status_label.setStyleSheet("""
                QLabel {
                    background: #e3f2fd;
                    border: 1px solid #2196f3;
                    border-radius: 6px;
                    padding: 8px;
                    font-weight: bold;
                    color: #1976d2;
                }
            """)
    def onSimulationStepChanged(self, step):
        """处理仿真步骤改变事件"""
        self.current_simulation_step = step
        logger.info(f"仿真步骤改变到: {step}")
        
        # 如果有历史数据，加载对应步骤的状态
        if step < len(self.simulation_history):
            historical_state = self.simulation_history[step]
            self.user_control_panel.updateSimulationData(
                step, len(self.simulation_history) - 1, historical_state
            )

    def onChargingDecisionMade(self, user_id, station_id, charging_params):
        """处理充电决策事件"""
        logger.info(f"用户 {user_id} 选择在 {station_id} 充电，参数: {charging_params}")
        
        # 记录详细的手动决策信息到专用日志文件
        manual_decision_logger.info(f"=== 手动决策开始 ===")
        manual_decision_logger.info(f"用户ID: {user_id}")
        manual_decision_logger.info(f"目标充电站: {station_id}")
        manual_decision_logger.info(f"目标SOC: {charging_params.get('target_soc', 80)}%")
        manual_decision_logger.info(f"充电类型: {charging_params.get('charging_type', '快充')}")
        manual_decision_logger.info(f"决策时间: {datetime.now().isoformat()}")
        
        # 应用用户决策到仿真环境
        if self.simulation_worker and hasattr(self.simulation_worker, 'environment'):
            # 创建人工决策
            manual_decision = {user_id: station_id}
            
            # 更新用户目标SOC
            target_soc = charging_params.get('target_soc', 80)
            users = self.simulation_worker.environment.users
            if user_id in users:
                user_data = users[user_id]
                # 记录用户当前状态
                manual_decision_logger.info(f"用户当前状态: {user_data.get('status', 'unknown')}")
                manual_decision_logger.info(f"用户当前SOC: {user_data.get('soc', 0):.1f}%")
                manual_decision_logger.info(f"用户当前位置: {user_data.get('position', {})}")
                
                user_data['target_soc'] = target_soc
                user_data['manual_decision'] = True
                user_data['manual_charging_params'] = charging_params
                
                manual_decision_logger.info(f"用户数据已更新: target_soc={target_soc}, manual_decision=True")
            else:
                manual_decision_logger.error(f"用户 {user_id} 在仿真环境中不存在")
            
            # 存储人工决策供调度器使用
            self.simulation_worker.manual_decisions = manual_decision
            manual_decision_logger.info(f"手动决策已存储到仿真工作线程: {manual_decision}")
            
            # 显示确认消息
            QMessageBox.information(self, "决策应用", 
                f"已为用户 {user_id} 安排在充电站 {station_id} 充电\n"
                f"目标电量: {target_soc}%\n"
                f"充电类型: {charging_params.get('charging_type', '快充')}")
            
            manual_decision_logger.info(f"手动决策处理完成")
            manual_decision_logger.info(f"=== 手动决策结束 ===")
            
            # 继续仿真
            self.user_panel_active = False
            if self.simulation_paused:
                self.pauseSimulation()  # 取消暂停
    
    def onDecisionAppliedAndContinue(self):
        """处理应用决策并继续仿真事件"""
        logger.info("收到应用决策并继续仿真信号")
        manual_decision_logger.info("用户面板请求继续仿真")
        
        # 退出用户交互模式
        self.user_panel_active = False
        
        # 如果仿真被暂停，则恢复仿真
        if self.simulation_paused:
            self.pauseSimulation()  # 取消暂停
            manual_decision_logger.info("仿真已恢复运行")
        
        # 更新状态显示
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

    def _createChartsTab(self):
        """创建图表选项卡"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # 导入高级图表组件
        from advanced_charts import RegionalLoadHeatmap, MultiMetricsChart
        # RegionalLoadChart已在当前文件中定义
        
        # 创建分割器
        splitter = QSplitter(Qt.Orientation.Vertical)
        
        # 创建区域负载图表容器
        load_charts_container = QWidget()
        load_charts_layout = QHBoxLayout(load_charts_container)
        
        # 区域负载曲线图
        self.regional_load_chart = RegionalLoadChart()
        load_charts_layout.addWidget(self.regional_load_chart)
        
        # 区域负载热力图
        self.regional_heatmap = RegionalLoadHeatmap()
        load_charts_layout.addWidget(self.regional_heatmap)
        
        # 添加负载图表容器到分割器
        splitter.addWidget(load_charts_container)
        
        # 多指标趋势图
        self.multi_metrics_chart = MultiMetricsChart()
        splitter.addWidget(self.multi_metrics_chart)
        
        # 如果有pyqtgraph，添加等待时间分布图
        if HAS_PYQTGRAPH:
            self.wait_time_chart = self._createWaitTimeChart()
            splitter.addWidget(self.wait_time_chart)
        
        # 设置分割器比例
        splitter.setStretchFactor(0, 2)  # 给负载图表容器更多空间
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
        
        # 新增：用户菜单
        user_menu = menubar.addMenu("用户")
        
        enable_user_panel_action = QAction("启用用户面板", self)
        enable_user_panel_action.setCheckable(True)
        enable_user_panel_action.triggered.connect(self.toggleUserPanel)
        user_menu.addAction(enable_user_panel_action)
        
        user_menu.addSeparator()
        
        export_user_data_action = QAction("导出用户数据", self)
        export_user_data_action.triggered.connect(self.exportUserData)
        user_menu.addAction(export_user_data_action)
        # 帮助菜单
        help_menu = menubar.addMenu("帮助")
        
        about_action = QAction("关于", self)
        about_action.triggered.connect(self.showAbout)
        help_menu.addAction(about_action)
    def toggleUserPanel(self, enabled):
        """切换用户面板"""
        # 这里可以控制用户面板的启用/禁用
        if hasattr(self, 'user_control_panel'):
            self.user_control_panel.setEnabled(enabled)

    def exportUserData(self):
        """导出用户数据"""
        if not self.simulation_history:
            QMessageBox.warning(self, "警告", "没有可导出的用户数据")
            return
        
        filename, _ = QFileDialog.getSaveFileName(
            self, "导出用户数据", "user_data.json", "JSON files (*.json)"
        )
        if filename:
            try:
                # 提取用户相关数据
                user_data = {
                    'selected_user': self.selected_user_id,
                    'simulation_steps': len(self.simulation_history),
                    'user_sessions': [],
                    'charging_decisions': []
                }
                
                # 收集用户会话数据
                for step, state in enumerate(self.simulation_history):
                    users = state.get('users', [])
                    for user in users:
                        if user.get('user_id') == self.selected_user_id:
                            user_data['user_sessions'].append({
                                'step': step,
                                'timestamp': state.get('timestamp'),
                                'user_state': user
                            })
                            break
                
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(user_data, f, indent=2, ensure_ascii=False)
                QMessageBox.information(self, "成功", f"用户数据已导出到 {filename}")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"导出失败:\n{str(e)}")

    # 9. 添加用户面板相关的工具栏按钮
    def _createToolBar(self):
        """创建工具栏"""
        toolbar = self.addToolBar("主工具栏")
        
        # 现有工具栏项目...
        toolbar.addAction("▶️", self.startSimulation)
        toolbar.addAction("⏸️", self.pauseSimulation)
        toolbar.addAction("⏹️", self.stopSimulation)
        toolbar.addSeparator()
        
        # 配置工具
        toolbar.addAction("⚙️", self.showConfig)
        toolbar.addSeparator()
        
        # 新增：用户面板工具
        toolbar.addAction("👤", self.showUserPanel)
        toolbar.addSeparator()
        
        # 导出工具
        toolbar.addAction("💾", self.exportData)

    def showUserPanel(self):
        """显示用户面板"""
        # 切换到用户面板选项卡
        if hasattr(self, 'tab_widget'):  # 假设主选项卡widget有这个名字
            for i in range(self.tab_widget.count()):
                if "用户面板" in self.tab_widget.tabText(i):
                    self.tab_widget.setCurrentIndex(i)
                    break
    
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
            self.simulation_worker.environmentReady.connect(self.onEnvironmentReady)
            
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

    def onStatusUpdated(self, status_data):
        """处理状态更新"""
        import random  # 确保random模块可用
        try:
            state = status_data.get('state', {})
            rewards = status_data.get('rewards', {})
            timestamp = status_data.get('timestamp', '')
            # 保存到历史记录
            self.simulation_history.append(state.copy())
            
            # 限制历史记录长度
            max_history = 1000
            if len(self.simulation_history) > max_history:
                self.simulation_history = self.simulation_history[-max_history:]
            
            # 更新用户面板
            if hasattr(self, 'user_control_panel'):
                current_step = len(self.simulation_history) - 1
                self.user_control_panel.updateSimulationData(
                    current_step, len(self.simulation_history) - 1, state
                )
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
            
            # 处理电网数据
            grid_status = state.get('grid_status', {})
            
            # 调试输出，查看grid_status内容
            logger.info(f"Grid status data received: {grid_status.keys() if isinstance(grid_status, dict) else 'Not a dict'}")
            
            # 创建测试数据（无论是否有真实数据）
            # 构建时间序列数据
            if not hasattr(self, 'time_series_collector'):
                self.time_series_collector = {
                    'timestamps': [],
                    'regional_data': {}
                }
            
            # 添加新的时间戳
            self.time_series_collector['timestamps'].append(timestamp if timestamp else datetime.now().isoformat())
            
            # 限制历史数据长度
            max_points = 288  # 72小时，15分钟间隔
            if len(self.time_series_collector['timestamps']) > max_points:
                self.time_series_collector['timestamps'] = self.time_series_collector['timestamps'][-max_points:]
            
            # 创建测试区域数据
            test_regions = ['region_1', 'region_2', 'region_3']
            for region_id in test_regions:
                if region_id not in self.time_series_collector['regional_data']:
                    self.time_series_collector['regional_data'][region_id] = {
                        'total_load': [],
                        'base_load': [],
                        'ev_load': [],
                        'renewable_ratio': [],
                        'grid_load_percentage': []
                    }
                
                # 生成随机测试数据
                region_collector = self.time_series_collector['regional_data'][region_id]
                region_collector['total_load'].append(random.uniform(800, 1200))
                region_collector['base_load'].append(random.uniform(700, 900))
                region_collector['ev_load'].append(random.uniform(50, 300))
                region_collector['renewable_ratio'].append(random.uniform(10, 40))
                region_collector['grid_load_percentage'].append(random.uniform(60, 90))
                
                # 限制长度
                for key in region_collector:
                    if len(region_collector[key]) > max_points:
                        region_collector[key] = region_collector[key][-max_points:]
            
            # 创建区域当前状态数据用于数据表
            regional_current_state = {}
            for region_id, region_data in self.time_series_collector['regional_data'].items():
                if region_data['total_load']:
                    # 取最新的数据点
                    regional_current_state[region_id] = {
                        'current_total_load': region_data['total_load'][-1] * 1000,  # 转换为kW
                        'current_base_load': region_data['base_load'][-1] * 1000 if region_data['base_load'] else 0,
                        'current_ev_load': region_data['ev_load'][-1] * 1000 if region_data['ev_load'] else 0,
                        'current_solar_gen': random.uniform(50, 200) * 1000,  # 模拟太阳能数据
                        'current_wind_gen': random.uniform(20, 150) * 1000,  # 模拟风能数据
                        'renewable_ratio': region_data['renewable_ratio'][-1] if region_data['renewable_ratio'] else 0,
                        'grid_load_percentage': region_data['grid_load_percentage'][-1] if region_data['grid_load_percentage'] else 0,
                        'carbon_intensity': random.uniform(200, 500)  # 模拟碳强度数据
                    }
            
            # 将区域数据添加到state中
            if regional_current_state:
                # 创建电网状态对象
                grid_status = {
                    'regional_current_state': regional_current_state,
                    'aggregated_metrics': {
                        'total_load': sum(data['current_total_load'] for data in regional_current_state.values()),
                        'total_base_load': sum(data['current_base_load'] for data in regional_current_state.values()),
                        'total_ev_load': sum(data['current_ev_load'] for data in regional_current_state.values()),
                        'weighted_renewable_ratio': sum(data['renewable_ratio'] * data['current_total_load'] 
                                                    for data in regional_current_state.values()) / 
                                                sum(data['current_total_load'] for data in regional_current_state.values()) 
                                                if sum(data['current_total_load'] for data in regional_current_state.values()) > 0 else 0,
                        'overall_load_percentage': sum(data['grid_load_percentage'] * data['current_total_load'] 
                                                    for data in regional_current_state.values()) / 
                                                sum(data['current_total_load'] for data in regional_current_state.values())
                                                if sum(data['current_total_load'] for data in regional_current_state.values()) > 0 else 0
                    }
                }
                
                # 更新state中的grid_status
                state['grid_status'] = grid_status
                
                # 更新数据表
                if hasattr(self, 'data_table_widget'):
                    logger.info("Updating data table with grid status")
                    self.data_table_widget.updateData(state)
            
            # 更新区域负载图表
            if hasattr(self, 'regional_load_chart'):
                logger.info("Updating regional load chart with test data")
                self.regional_load_chart.updateData(self.time_series_collector)
            
            # 更新区域热力图
            if hasattr(self, 'regional_heatmap'):
                logger.info("Updating regional heatmap with test data")
                # 为充电桩分配区域并计算负载
                region_loads = {'Region_1': 0, 'Region_2': 0, 'Region_3': 0}
                
                for i, charger in enumerate(chargers):
                    # 根据充电桩索引分配区域
                    region_id = f"Region_{(i % 3) + 1}"
                    charger['region_id'] = region_id
                    
                    # 计算充电桩当前负载
                    if charger.get('status') == 'occupied':
                        # 充电中的负载 = 充电功率
                        current_load = charger.get('max_power', 60) * 0.8  # 80%功率
                    elif charger.get('status') == 'available':
                        # 空闲时的基础负载
                        current_load = charger.get('max_power', 60) * 0.1  # 10%待机功率
                    else:
                        current_load = 0
                    
                    region_loads[region_id] += current_load
                
                # 添加基础电网负载
                import random
                base_loads = {'Region_1': 800, 'Region_2': 1000, 'Region_3': 600}
                for region in region_loads:
                    # 添加随机的基础负载变化
                    base_variation = random.uniform(0.8, 1.2)
                    region_loads[region] += base_loads[region] * base_variation
                
                # 构造热力图需要的grid_status格式
                grid_status = {
                    'regional_current_state': {
                        'Region_1': {
                            'current_total_load': region_loads['Region_1'],
                            'base_load': 1000
                        },
                        'Region_2': {
                            'current_total_load': region_loads['Region_2'],
                            'base_load': 1200
                        },
                        'Region_3': {
                            'current_total_load': region_loads['Region_3'],
                            'base_load': 800
                        }
                    }
                }
                self.regional_heatmap.updateData(grid_status)
            
            # 更新等待时间分布
            if hasattr(self, 'wait_time_plot'):
                self._updateWaitTimeChart(users)
                
        except Exception as e:
            logger.error(f"状态更新错误: {e}")
            logger.error(traceback.format_exc())


    def _updateWaitTimeChart(self, users):
        """更新等待时间分布图"""
        if not hasattr(self, 'wait_time_plot') or not HAS_PYQTGRAPH:
            return
        
        # 统计等待时间分布
        wait_times = []
        for user in users:
            if isinstance(user, dict) and user.get('status') == 'waiting' and 'arrival_time_at_charger' in user:
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
    
    def onEnvironmentReady(self, environment):
        """处理仿真环境准备就绪"""
        # 设置用户面板的仿真环境
        if hasattr(self, 'user_control_panel') and self.user_control_panel:
            self.user_control_panel.setSimulationEnvironment(environment)
    
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
            # 根据当前步数和总步数计算进度
            current_step = getattr(self.simulation_worker, 'current_step', 0)
            total_steps = getattr(self.simulation_worker, 'total_steps', 100)
            
            if total_steps > 0:
                progress = int((current_step / total_steps) * 100)
                # 确保进度在0-100之间
                progress = max(0, min(100, progress))
                self.progress_bar.setValueAnimated(progress)
    
    def updateCurrentTime(self):
        """更新当前时间显示"""
        # 优先显示模拟时间，如果没有则显示系统时间
        if hasattr(self, 'user_control_panel') and hasattr(self.user_control_panel, 'current_simulation_time'):
            sim_time = self.user_control_panel.current_simulation_time
            if sim_time:
                time_text = f"模拟时间: {sim_time.strftime('%Y-%m-%d %H:%M:%S')}"
            else:
                time_text = f"系统时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        else:
            time_text = f"系统时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        self.current_time_label.setText(time_text)
    
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
    
    # 加载QSS样式表
    try:
        with open("styles.qss", "r", encoding="utf-8") as style_file:
            style_sheet = style_file.read()
            app.setStyleSheet(style_sheet)
            logger.info("成功加载QSS样式表")
    except Exception as e:
        logger.error(f"加载QSS样式表失败: {str(e)}")
        # 如果样式表加载失败，使用默认样式
    
    # 应用深色主题（可选 - 现在由QSS控制）
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
    
    # 可选择应用深色主题（现在由QSS控制，保留注释以便需要时启用）
    # app.setPalette(dark_palette)
    
    # 创建并显示主窗口
    window = MainWindow()
    window.show()
    
    # 运行应用程序
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
