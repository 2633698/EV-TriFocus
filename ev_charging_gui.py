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
    from operator_panel import OperatorControlPanel


    from data_storage import operator_storage
    from power_grid_panel import PowerGridPanel
    from synergy_dashboard import SynergyDashboard
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
        try:
            if not time_series_data:
                logger.debug("RegionalLoadChart: No time_series_data provided")
                return
                
            if 'timestamps' not in time_series_data:
                logger.debug(f"RegionalLoadChart: No timestamps in data. Available keys: {list(time_series_data.keys()) if isinstance(time_series_data, dict) else 'Not a dict'}")
                return
                
            logger.debug(f"RegionalLoadChart: Rendering chart with {len(time_series_data['timestamps'])} timestamps")
            
            timestamps = time_series_data['timestamps']
            regional_data = time_series_data.get('regional_data', {})
            
            logger.debug(f"RegionalLoadChart: Regional data has {len(regional_data)} regions")
            
            if not HAS_PYQTGRAPH or not hasattr(self, 'plot_widget'):
                # 文本显示模式
                self._renderTextMode(regional_data)
                return
            
            # 清除当前图表
            self.plot_widget.clear()
            
            # 数据采样优化 - 限制显示的数据点数量
            max_points = 15  # 最多显示15个数据点
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
                        
                        # 确保长度一致并转换为MW单位
                        if len(sampled_load) <= len(total_load):
                            # 转换为MW单位显示
                            sampled_load_mw = [load / 1000 for load in sampled_load]
                            total_load[:len(sampled_load)] += np.array(sampled_load_mw)
                
                # 绘制总负载曲线
                if len(total_load) > 0 and np.any(total_load > 0):
                    pen = pg.mkPen(color=(31, 119, 180), width=3)
                    self.plot_widget.plot(
                                x_data[:len(total_load)], total_load, 
                                pen=pen, 
                                name="总负载",
                                symbolBrush=(31, 119, 180),
                                symbolSize=4,  # 减小符号大小
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
                        
                        # 转换为MW单位显示
                        sampled_load_mw = [load / 1000 for load in sampled_load]
                        
                        # 检查是否有有效数据
                        if any(load > 0 for load in sampled_load_mw):
                            pen = pg.mkPen(color=(31, 119, 180), width=3)
                            self.plot_widget.plot(
                                 x_data[:len(sampled_load_mw)], sampled_load_mw, 
                                 pen=pen, 
                                 name=self.selected_region,
                                 symbolBrush=(31, 119, 180),
                                 symbolSize=4,  # 减小符号大小
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
                        
                        # 转换为MW单位显示
                        sampled_load_mw = [load / 1000 for load in sampled_load]
                        
                        # 检查是否有有效数据
                        if any(load > 0 for load in sampled_load_mw):
                            color = self.colors[i % len(self.colors)]
                            pen = pg.mkPen(color=color, width=2)  # 稍微加粗线条
                            
                            self.plot_widget.plot(
                                 x_data[:len(sampled_load_mw)], sampled_load_mw, 
                                 pen=pen, 
                                 name=region_id,
                                 symbolBrush=color,
                                 symbolSize=3,  # 进一步减小符号
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
        
        except Exception as e:
            logger.error(f"RegionalLoadChart renderChart error: {e}")
            import traceback
            traceback.print_exc()
            # 在出错时显示错误信息
            if hasattr(self, 'text_display'):
                self.text_display.setText(f"图表渲染错误: {str(e)}")
            elif hasattr(self, 'plot_widget'):
                self.plot_widget.clear()
    
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
    
    def __init__(self, parent=None, config=None):
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
        self.grid_regions = None # To store region geometry data
        
        self.setMinimumSize(800, 600)
        self.setMouseTracking(True)
        
        # 从传入的 config 加载地图边界，如果失败则使用默认值
        if config and 'environment' in config and 'map_bounds' in config['environment']:
            self.map_bounds = config['environment']['map_bounds']
            logger.info(f"MapWidget: Successfully loaded map_bounds from config: {self.map_bounds}")
        else:
            # 保留一个硬编码的默认值作为后备，以防万一
            self.map_bounds = {
                'lat_min': 30.5, 'lat_max': 31.0,
                'lng_min': 114.0, 'lng_max': 114.5
            }
            logger.warning(f"MapWidget: Could not load map_bounds from config, using default values: {self.map_bounds}")
        
        # 创建右键菜单
        self.createContextMenu()
    
    def updateData(self, users, chargers, grid_regions=None):
        """更新地图数据"""
        self.users = users or []
        self.chargers = chargers or []
        self.grid_regions = grid_regions # Store region data
        
        # 添加调试信息
        logger.debug(f"Map updating with {len(self.users)} users, {len(self.chargers)} chargers")
        if self.users:
            logger.debug(f"First user current_position: {self.users[0].get('current_position', 'No current_position')}")
            logger.debug(f"First user position: {self.users[0].get('position', 'No position')}")
        if self.chargers:
            logger.debug(f"First charger position: {self.chargers[0].get('position', 'No position')}")
        
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
        self.update() # Ensure map repaints when toggling overlay
    
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
        
        # 绘制电网分区（如果启用）- 临时禁用用于测试
        if self.show_grid_overlay and self.grid_regions:
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
            # 1. 直接获取 'position'
            position = charger.get('position')
            
            # 2. 严格的有效性检查
            if not isinstance(position, dict) or 'lat' not in position or 'lng' not in position:
                # 这条日志非常重要，如果数据有问题，它会告诉你
                logger.warning(f"Invalid or missing position data for charger: {charger.get('charger_id', 'Unknown ID')}, data: {charger}")
                continue
            
            # 3. 坐标转换
            try:
                x, y = self._geoToPixel(position)
            except Exception as e:
                logger.error(f"Error converting charger coordinates for {charger.get('charger_id')}: {e}, position: {position}")
                continue

            # ... 后续的绘图代码保持不变 ...
            # (根据状态选择颜色, 绘制图标, ID, 队列等)
            status = charger.get('status', 'unknown')
            if status == 'available':
                color = QColor(46, 204, 113)
            elif status == 'occupied':
                color = QColor(231, 76, 60)
            elif status == 'failure':
                color = QColor(149, 165, 166)
            else:
                color = QColor(52, 152, 219)
            
            painter.setBrush(QBrush(color))
            painter.setPen(QPen(Qt.GlobalColor.black, 2))
            painter.drawRect(int(x-10), int(y-10), 20, 20)
            
            painter.setPen(QPen(Qt.GlobalColor.white, 1))
            painter.setFont(QFont("Arial", 8, QFont.Weight.Bold))
            charger_id = charger.get('charger_id', '')
            if len(charger_id) > 10:
                charger_id = charger_id[-4:]
            painter.drawText(int(x-8), int(y+3), charger_id)
            
            queue_length = len(charger.get('queue', []))
            if queue_length > 0 and self.show_charger_queues:
                painter.setPen(QPen(Qt.GlobalColor.red, 2))
                painter.setBrush(QBrush(QColor(255, 255, 255)))
                painter.drawEllipse(int(x+8), int(y-12), 16, 16)
                painter.setPen(QPen(Qt.GlobalColor.red, 1))
                painter.drawText(int(x+12), int(y-1), str(queue_length))
    
    def _drawUsers(self, painter):
        """绘制用户"""
        if not self.users: return
        
        # 打印第一个用户的计算过程
        first_user = self.users[0]
        position = first_user.get('current_position')
        if position:
            x, y = self._geoToPixel(position)
            print(f"DEBUG: First user geo {position} -> pixel ({x:.2f}, {y:.2f}). Widget size: ({self.width()}, {self.height()})")
        for user in self.users:
            # 1. 直接获取 'current_position'
            position = user.get('current_position')
            
            # 2. 严格的有效性检查
            if not isinstance(position, dict) or 'lat' not in position or 'lng' not in position:
                # 这条日志将揭示问题所在
                logger.warning(f"Invalid or missing current_position for user: {user.get('user_id', 'Unknown ID')}, data: {user}")
                continue

            # 3. 坐标转换
            try:
                x, y = self._geoToPixel(position)
            except Exception as e:
                logger.error(f"Error converting user coordinates for {user.get('user_id')}: {e}, position: {position}")
                continue
                
            # ... 后续的绘图代码保持不变 ...
            status = user.get('status', 'unknown')
            if status == 'charging':
                color = QColor(46, 204, 113)
            elif status == 'waiting':
                color = QColor(241, 196, 15)
            elif status == 'traveling':
                color = QColor(52, 152, 219)
            else:
                color = QColor(149, 165, 166)
            
            painter.setBrush(QBrush(color))
            painter.setPen(QPen(Qt.GlobalColor.black, 1))
            painter.drawEllipse(int(x-6), int(y-6), 12, 12)
            
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
                # 获取用户当前位置
                user_position = user.get('current_position') or user.get('position')
                if not user_position:
                    continue
                    
                # 找到目标充电桩
                target_charger = next(
                    (c for c in self.chargers if c.get('charger_id') == user['target_charger']), 
                    None
                )
                if target_charger:
                    start = self._geoToPixel(user_position)
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
        if not self.grid_regions:
            return

        for region_id, region_info in self.grid_regions.items():
            polygon_geo = region_info.get("polygon")
            color_rgba = region_info.get("color", [128, 128, 128, 30]) # Default gray, semi-transparent
            region_name = region_info.get("name", region_id)

            if not polygon_geo or not isinstance(polygon_geo, list) or len(polygon_geo) < 3:
                logger.warning(f"Region {region_id} has invalid polygon data: {polygon_geo}")
                continue

            pixel_points = []
            for geo_point in polygon_geo:
                if isinstance(geo_point, list) and len(geo_point) == 2:
                    # Assuming geo_point is [lng, lat]
                    px, py = self._geoToPixel({'lng': geo_point[0], 'lat': geo_point[1]})
                    pixel_points.append(QPointF(px, py))
                else:
                    logger.warning(f"Invalid point in polygon for region {region_id}: {geo_point}")
                    pixel_points.clear() # Invalidate polygon if a point is bad
                    break
            
            if not pixel_points:
                continue

            q_polygon_f = QPolygonF(pixel_points)

            try:
                brush_color = QColor(color_rgba[0], color_rgba[1], color_rgba[2], color_rgba[3])
            except (IndexError, TypeError):
                logger.warning(f"Invalid color format for region {region_id}: {color_rgba}. Using default.")
                brush_color = QColor(128, 128, 128, 30)

            painter.setBrush(QBrush(brush_color))
            painter.setPen(QPen(QColor(color_rgba[0],color_rgba[1],color_rgba[2],150), 1)) # Darker border for the region color
            painter.drawPolygon(q_polygon_f)

            # Draw region name (optional, simple centroid calculation)
            if region_name:
                centroid_x = sum(p.x() for p in pixel_points) / len(pixel_points)
                centroid_y = sum(p.y() for p in pixel_points) / len(pixel_points)
                painter.setPen(QColor(0,0,0, 180)) # Semi-transparent black for text
                painter.setFont(QFont("Arial", 10, QFont.Weight.Bold))
                # Adjust text position slightly if needed
                metrics = QFontMetrics(painter.font())
                text_width = metrics.horizontalAdvance(region_name)
                painter.drawText(int(centroid_x - text_width / 2), int(centroid_y), region_name)
    
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
    
    # 在 MapWidget 类中
    def _geoToPixel(self, geo_pos):
        """
        将地理坐标转换为【未缩放、未平移】的画布像素坐标。
        缩放和平移将由 QPainter 在 paintEvent 中统一处理。
        """
        lat = geo_pos.get('lat', 0)
        lng = geo_pos.get('lng', 0)
        
        # 使用基础的、未缩放的地图边界
        lat_range = self.map_bounds['lat_max'] - self.map_bounds['lat_min']
        lng_range = self.map_bounds['lng_max'] - self.map_bounds['lng_min']
        
        # 防止除以零
        if lat_range == 0 or lng_range == 0:
            return -1, -1

        # 标准化到 [0, 1]
        x_norm = (lng - self.map_bounds['lng_min']) / lng_range
        y_norm = (lat - self.map_bounds['lat_min']) / lat_range
        
        # 转换为原始画布尺寸的像素坐标
        x = x_norm * self.width()
        y = (1 - y_norm) * self.height()  # Y轴翻转，因为屏幕坐标y向下增长
        
        return x, y 
    
    # 在 MapWidget 类中
    def _screenToGeo(self, screen_pos):
        """将屏幕坐标转换为地理坐标"""
        # 1. 将屏幕坐标转换回场景坐标 (撤销平移和缩放)
        scene_x = (screen_pos.x() - self.offset_x) / self.zoom_level
        scene_y = (screen_pos.y() - self.offset_y) / self.zoom_level
        
        # 2. 将场景坐标标准化回 [0, 1]
        x_norm = scene_x / self.width()
        y_norm = 1 - (scene_y / self.height()) # 撤销Y轴翻转

        # 3. 将标准化坐标转换回地理坐标
        lat_range = self.map_bounds['lat_max'] - self.map_bounds['lat_min']
        lng_range = self.map_bounds['lng_max'] - self.map_bounds['lng_min']
        
        lng = self.map_bounds['lng_min'] + x_norm * lng_range
        lat = self.map_bounds['lat_min'] + y_norm * lat_range

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
                user_pos = user.get('current_position', {}) or user.get('position', {})
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
    
    # 在 MapWidget 类中
    def wheelEvent(self, event):
        """鼠标滚轮事件 - 实现以鼠标为中心的缩放"""
        mouse_pos = event.position()
        
        # 缩放前的鼠标点在场景坐标系中的位置
        # (scene_x, scene_y) = (screen_x - offset_x) / zoom
        scene_x_before = (mouse_pos.x() - self.offset_x) / self.zoom_level
        scene_y_before = (mouse_pos.y() - self.offset_y) / self.zoom_level

        # 计算新的缩放级别
        delta = event.angleDelta().y()
        zoom_factor = 1.1 if delta > 0 else (1 / 1.1)
        new_zoom_level = self.zoom_level * zoom_factor
        new_zoom_level = max(0.2, min(10.0, new_zoom_level)) # 限制缩放范围

        self.zoom_level = new_zoom_level
        
        # 缩放后，我们希望场景中的同一点仍然在鼠标下方。
        # new_offset_x = screen_x - scene_x * new_zoom
        self.offset_x = mouse_pos.x() - scene_x_before * self.zoom_level
        self.offset_y = mouse_pos.y() - scene_y_before * self.zoom_level
        
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
        self.grid_preferences = {}
        self.pending_v2g_request = None
        
        # 新增属性来存储负荷曲线
        self.uncoordinated_load_profile = []
        self.coordinated_load_profile = []
        self.renewable_generation_profile = []
        self.total_steps = 0
        self.current_step = 0
        # 计算总的仿真步数




# In class SimulationWorker:

# In ev_charging_gui.py

class SimulationWorker(QThread):
    """仿真工作线程（修复版，用于维护和传递负荷曲线）"""
    
    statusUpdated = pyqtSignal(dict)
    metricsUpdated = pyqtSignal(dict)
    errorOccurred = pyqtSignal(str)
    simulationFinished = pyqtSignal()
    environmentReady = pyqtSignal(object)

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.running = False
        self.paused = False
        self.environment = None
        self.scheduler = None
        self.mutex = QMutex()
        self.grid_preferences = {}
        self.pending_v2g_request = None
        
        # --- START OF MODIFICATION ---
        # 新增属性来存储负荷曲线
        self.uncoordinated_load_profile = []
        self.coordinated_load_profile = []
        self.renewable_generation_profile = []
        self.total_steps = 0
        self.current_step = 0
        # --- END OF MODIFICATION ---
        
    def run(self):
        """运行仿真，先跑基线，再跑主循环，并记录两条曲线"""
        logger.info("SimulationWorker.run() started!")
        try:
            self.running = True
            
            # 1. 初始化
            self.environment = ChargingEnvironment(self.config)
            self.scheduler = ChargingScheduler(self.config)
            self.manual_decisions = {}
            self.environmentReady.emit(self.environment)
            
            self.total_steps = (self.environment.simulation_days * 24 * 60) // self.environment.time_step_minutes
            
            # --- 2. 运行无序充电基线 ---
            logger.info("--- Starting Uncoordinated Baseline Simulation ---")
            self.uncoordinated_load_profile = [] # 清空旧数据
            baseline_env = ChargingEnvironment(self.config)
            uncoordinated_scheduler_config = self.config.copy()
            uncoordinated_scheduler_config['scheduler']['scheduling_algorithm'] = 'uncoordinated'
            baseline_scheduler = ChargingScheduler(uncoordinated_scheduler_config)
            
            for _ in range(self.total_steps):
                if not self.running: break
                state = baseline_env.get_current_state()
                decisions, _ = baseline_scheduler.make_scheduling_decision(state)
                _, next_state, _ = baseline_env.step(decisions)
                
                agg_metrics = next_state.get('grid_status', {}).get('aggregated_metrics', {})
                self.uncoordinated_load_profile.append(agg_metrics.get('total_load', 0))
            
            logger.info(f"--- Uncoordinated Baseline Simulation Finished. ---")
            
            if not self.running:
                self.simulationFinished.emit()
                return

            # --- 3. 运行主仿真（协调调度） ---
            self.environment.reset()
            self.current_step = 0
            self.coordinated_load_profile = [] # 清空
            self.renewable_generation_profile = [] # 清空

            while self.running and self.current_step < self.total_steps:
                if self.paused:
                    time.sleep(0.1)
                    continue

                current_state = self.environment.get_current_state()
                
                # 在这里，我们不再需要向 state 注入 uncoordinated_load_profile
                # 因为我们将直接把它传递给 calculate_rewards

                # ... (获取决策和V2G请求的逻辑保持不变) ...
                manual_decisions_this_step = self.manual_decisions.copy(); self.manual_decisions.clear()
                decisions, scheduler_metadata = self.scheduler.make_scheduling_decision(current_state, manual_decisions_this_step, self.grid_preferences)
                v2g_request_to_pass = self.pending_v2g_request; self.pending_v2g_request = None
                
                # --- 4. 修改 step 调用和 rewards 计算 ---
                # 我们需要在调用 step 之后，但在计算 rewards 之前，记录下当前的负荷
                
                # 先执行一步仿真
                _, next_state, _ = self.environment.step(
                    decisions, manual_decisions_this_step, v2g_request_to_pass, scheduler_metadata
                )
                
                # 从新状态中记录当前步的负荷和新能源发电量
                agg_metrics = next_state.get('grid_status', {}).get('aggregated_metrics', {})
                self.coordinated_load_profile.append(agg_metrics.get('total_load', 0))
                
                regional_states = next_state.get('grid_status', {}).get('regional_current_state', {})
                renewable_gen = sum(r.get('current_solar_gen', 0) + r.get('current_wind_gen', 0) for r in regional_states.values() if r)
                self.renewable_generation_profile.append(renewable_gen)

                # 将最新的曲线数据添加到要传递给 calculate_rewards 的 state 字典中
                # 这是一个临时的、用于计算的数据包，不影响 environment 的主状态
                state_for_rewards = next_state.copy()
                state_for_rewards['uncoordinated_load_profile'] = self.uncoordinated_load_profile
                state_for_rewards['coordinated_load_profile'] = self.coordinated_load_profile
                state_for_rewards['renewable_generation_profile'] = self.renewable_generation_profile
                
                # 使用这个增强的 state 来计算 rewards
                rewards = calculate_rewards(state_for_rewards, self.config)

                # 更新步数
                self.current_step += 1
                
                # 发送信号
                self.statusUpdated.emit({
                    'state': next_state, 'rewards': rewards,
                    'decisions': decisions, 'timestamp': next_state.get('timestamp')
                })
                self.metricsUpdated.emit(rewards)
                
                time.sleep(0.1)
            
        except Exception as e:
            logger.error(f"仿真错误: {e}", exc_info=True)
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

    def set_grid_preference(self, preference_name, value):
        with QMutexLocker(self.mutex):
            self.grid_preferences[preference_name] = value
        logger.info(f"SimulationWorker: Grid preference '{preference_name}' set to '{value}'.")

    def request_v2g_discharge(self, amount_mw):
        with QMutexLocker(self.mutex):
            self.pending_v2g_request = amount_mw
            # Also store it in grid_preferences for agents to see in the next decision cycle
            if self.grid_preferences is None: # Should have been initialized
                self.grid_preferences = {}
            self.grid_preferences["v2g_discharge_active_request_mw"] = amount_mw
            # This preference will be cleared/reset by the scheduler or environment after being consumed or if request changes.
            # For now, it will persist until the next request.
        logger.info(f"SimulationWorker: V2G discharge of {amount_mw} MW requested and preference set.")


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
        # Load configuration
        try:
            with open("config.json", 'r', encoding='utf-8') as f:
                self.config = json.load(f)
            logger.info("Successfully loaded config.json")
        except FileNotFoundError:
            logger.warning("config.json not found, using default configuration.")
            self.config = self._loadDefaultConfig()
            try:
                with open("config.json", 'w', encoding='utf-8') as f:
                    json.dump(self.config, f, indent=4, ensure_ascii=False)
                logger.info("Default configuration saved to config.json")
            except IOError as e:
                logger.error(f"Could not save default config.json: {e}")
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding config.json: {e}. Using default configuration.")
            self.config = self._loadDefaultConfig()
        except Exception as e:
            logger.error(f"Error loading config.json: {e}. Using default configuration.")
            self.config = self._loadDefaultConfig()
        self.impact_analysis_pending = False # <-- 新增标志位
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
        
        # 初始化标签页切换相关属性
        self.pending_tab_index = -1
        self.tab_switch_timer = None
        self._switching_tab = False  # 防止递归调用标志
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
        
        # 性能优化：添加更新频率控制
        self.last_status_update = 0
        self.last_metrics_update = 0
        self.update_throttle_ms = 200  # 最小更新间隔200ms
        self.ui_update_counter = 0
        self.ui_update_skip_interval = 3  # 每3次更新跳过2次UI更新
        
        # 内存优化：定期垃圾回收
        self.gc_timer = QTimer()
        self.gc_timer.timeout.connect(self._performGarbageCollection)
        self.gc_timer.start(30000)  # 每30秒进行一次垃圾回收

    def _performGarbageCollection(self):
        """执行垃圾回收以优化内存使用"""
        import gc
        try:
            # 执行垃圾回收
            collected = gc.collect()
            if collected > 0:
                logger.debug(f"垃圾回收完成，清理了 {collected} 个对象")
        except Exception as e:
            logger.error(f"垃圾回收失败: {e}")
    
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
                # 添加运营商数据（新增）
                if hasattr(self, 'operator_control_panel'):
                    # 获取最近30天的财务汇总
                    end_date = datetime.now().strftime('%Y-%m-%d')
                    start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
                    financial_summary = operator_storage.get_financial_summary(start_date, end_date)
                    if not financial_summary.empty:
                        data['operator_financial'] = financial_summary.to_dict('records')
                    
                    # 获取活跃告警
                    data['active_alerts'] = operator_storage.get_active_alerts()



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
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #27ae60, stop:1 #2ecc71);
                color: white; border: none; border-radius: 8px; padding: 12px; font-weight: bold; font-size: 14px;
            }
            QPushButton:hover { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #229954, stop:1 #27ae60); }
            QPushButton:pressed { background: #1e8449; }
            QPushButton:disabled { background: #bdc3c7; }
        """)
        
        self.pause_button = QPushButton("暂停")
        self.pause_button.setEnabled(False)
        self.pause_button.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #f39c12, stop:1 #e67e22);
                color: white; border: none; border-radius: 8px; padding: 12px; font-weight: bold; font-size: 14px;
            }
            QPushButton:hover { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #e67e22, stop:1 #d35400); }
            QPushButton:disabled { background: #bdc3c7; }
        """)
        
        self.stop_button = QPushButton("停止")
        self.stop_button.setEnabled(False)
        self.stop_button.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #e74c3c, stop:1 #c0392b);
                color: white; border: none; border-radius: 8px; padding: 12px; font-weight: bold; font-size: 14px;
            }
            QPushButton:hover { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #c0392b, stop:1 #a93226); }
            QPushButton:disabled { background: #bdc3c7; }
        """)
        
        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.pause_button)
        button_layout.addWidget(self.stop_button)
        layout.addLayout(button_layout)
        
        # --- START OF MODIFICATION ---
        # 删除了进度条的相关代码
        # --- END OF MODIFICATION ---
        
        # 状态信息
        self.status_label = QLabel("就绪")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("""
            QLabel {
                background: #ecf0f1; border: 1px solid #bdc3c7; border-radius: 6px;
                padding: 8px; font-weight: bold;
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
        self.tab_widget = QTabWidget()  # 保存为实例属性
        tab_widget = self.tab_widget
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
        # 新的协同仪表盘选项卡
        self.synergy_dashboard = SynergyDashboard(self) # 创建实例
        tab_widget.addTab(self.synergy_dashboard, "📈 系统协同仪表盘")
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
        # 新增：运营商面板选项卡
        operator_panel_tab = self._createOperatorPanelTab()
        tab_widget.addTab(operator_panel_tab, "💼 运营商面板")

        # 新增：电网面板选项卡
        self.power_grid_panel = PowerGridPanel(self) # Store as attribute
        tab_widget.addTab(self.power_grid_panel, "⚡️ 电网面板")

        # Connect signals from PowerGridPanel
        if hasattr(self.power_grid_panel, 'gridPreferenceChanged'):
            self.power_grid_panel.gridPreferenceChanged.connect(self.handle_grid_preference_changed)
        if hasattr(self.power_grid_panel, 'v2gDischargeRequested'):
            self.power_grid_panel.v2gDischargeRequested.connect(self.handle_v2g_discharge_requested)

        # 连接标签页切换信号，添加错误处理
        try:
            self.tab_widget.currentChanged.connect(self.onTabChanged)
            # 设置标签页切换的延迟处理，避免快速切换导致的问题
            self.tab_switch_timer = QTimer()
            self.tab_switch_timer.setSingleShot(True)
            self.tab_switch_timer.timeout.connect(self.processTabSwitch)
            self.pending_tab_index = -1
        except Exception as e:
            logger.error(f"设置标签页信号连接时发生错误: {e}")
        
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
    # 添加创建方法：
    def _createOperatorPanelTab(self):
        """创建运营商面板选项卡"""
        from operator_panel import OperatorControlPanel
        self.operator_control_panel = OperatorControlPanel(self.config)
        
        # 连接信号
        self.operator_control_panel.pricingStrategyChanged.connect(self.onPricingStrategyChanged)
                # 连接故障注入面板的信号
        if hasattr(self.operator_control_panel, 'failure_sim_widget'):
            self.operator_control_panel.failure_sim_widget.requestImpactAnalysis.connect(
                self.schedule_impact_analysis
            )
        return self.operator_control_panel

        # 添加事件处理方法：
    def onPricingStrategyChanged(self, strategy):
        """处理定价策略变化"""
        logger.info(f"收到定价策略更新: {strategy}")
        
        # 应用到仿真环境
        if self.simulation_worker and hasattr(self.simulation_worker, 'environment'):
            environment = self.simulation_worker.environment
            config = environment.config
            
            # 更新配置
            config['grid']['normal_price'] = strategy['base_price']
            config['grid']['peak_price'] = strategy['base_price'] * strategy['peak_factor']
            config['grid']['valley_price'] = strategy['base_price'] * strategy['valley_factor']
            
            # 更新充电桩定价
            for charger_id, charger in environment.chargers.items():
                charger['price_multiplier'] = 1.0
                
                # 应用会员优惠
                if strategy.get('member_discount'):
                    charger['member_discount'] = 0.9  # 9折优惠
                    
            logger.info("定价策略已应用到仿真环境")

    def onMaintenanceRequested(self, charger_id):
        """处理维护请求"""
        logger.info(f"收到充电桩 {charger_id} 的维护请求")
        
        # 在仿真中标记充电桩为维护状态
        if self.simulation_worker and hasattr(self.simulation_worker, 'environment'):
            environment = self.simulation_worker.environment
            if charger_id in environment.chargers:
                environment.chargers[charger_id]['status'] = 'maintenance'
                logger.info(f"充电桩 {charger_id} 已设置为维护状态")

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
        
        # 设置分割器比例
        splitter.setStretchFactor(0, 2)  # 给负载图表容器更多空间
        splitter.setStretchFactor(1, 1)
        
        layout.addWidget(splitter)
        return widget



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
        self.map_widget = MapWidget(config=self.config)
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

    # 重复的_createDataTab方法已删除，使用上面的完整实现
    
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

    def onTabChanged(self, index):
        """处理标签页切换事件（延迟处理）"""
        try:
            # 使用延迟处理机制，避免快速切换导致的问题
            self.pending_tab_index = index
            if hasattr(self, 'tab_switch_timer'):
                self.tab_switch_timer.stop()
                self.tab_switch_timer.start(100)  # 100ms延迟
            else:
                # 如果定时器未初始化，直接处理
                self.processTabSwitch()
        except Exception as e:
            logger.error(f"标签页切换信号处理时发生错误: {e}")
    
    def processTabSwitch(self):
        """实际处理标签页切换的逻辑"""
        try:
            # 防止递归调用
            if hasattr(self, '_switching_tab') and self._switching_tab:
                return
                
            index = self.pending_tab_index
            if index < 0 or not hasattr(self, 'tab_widget') or not self.tab_widget:
                return
                
            # 检查索引有效性
            if index >= self.tab_widget.count():
                logger.warning(f"标签页索引 {index} 超出范围 (总数: {self.tab_widget.count()})")
                return
                
            tab_text = self.tab_widget.tabText(index)
            logger.info(f"标签页切换到: {tab_text} (索引: {index})")
            
            # 如果切换到用户面板，暂停仿真
            if "用户面板" in tab_text and self.simulation_running and not self.simulation_paused:
                self.pauseSimulation()
                self.user_panel_active = True
                logger.info("切换到用户面板，仿真已暂停")
            
            # 更新状态栏
            if hasattr(self, 'sim_status_label'):
                self.sim_status_label.setText(f"当前面板: {tab_text}")
                
        except Exception as e:
            logger.error(f"处理标签页切换时发生错误: {e}")
            # 不重新抛出异常，避免GUI卡死
    
    def showUserPanel(self):
        """显示用户面板"""
        try:
            # 防止递归调用
            if hasattr(self, '_switching_tab') and self._switching_tab:
                return
                
            # 切换到用户面板选项卡
            if hasattr(self, 'tab_widget') and self.tab_widget:
                self._switching_tab = True
                try:
                    for i in range(self.tab_widget.count()):
                        if "用户面板" in self.tab_widget.tabText(i):
                            self.tab_widget.setCurrentIndex(i)
                            break
                finally:
                    self._switching_tab = False
            else:
                logger.warning("tab_widget 未找到，无法切换到用户面板")
        except Exception as e:
            logger.error(f"切换到用户面板时发生错误: {e}")
            if hasattr(self, '_switching_tab'):
                self._switching_tab = False
    
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
                "simulation_days": 3,
                "user_count": 100,
                "station_count": 5,
                "chargers_per_station": 3,
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

            # Connect PowerGridPanel to status updates
            if hasattr(self, 'power_grid_panel') and self.power_grid_panel:
                self.simulation_worker.statusUpdated.connect(self.power_grid_panel.handle_status_update)
            
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
            # 使用异步方式等待线程结束，避免阻塞主线程
            QTimer.singleShot(100, self._finishStopSimulation)
        else:
            self._finishStopSimulation()
    
    def _finishStopSimulation(self):
        """完成停止仿真的后续操作"""
        if self.simulation_worker and self.simulation_worker.isFinished():
            self.simulation_worker = None
        elif self.simulation_worker and not self.simulation_worker.isFinished():
            # 如果线程还没结束，再等待一下
            QTimer.singleShot(100, self._finishStopSimulation)
            return
        
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
        

    def schedule_impact_analysis(self):
        """设置标志，表示下一步需要进行影响分析"""
        self.impact_analysis_pending = True
        logger.info("Impact analysis scheduled for the next step.")

    def onStatusUpdated(self, status_data):
        """处理状态更新 - 结合了数据流修复和完整更新逻辑的最终版本"""
        print("DEBUG: onStatusUpdated called!")
        import time
        
        try:
            # 性能优化：限制UI更新频率
            current_time_ms = time.time() * 1000
            if hasattr(self, 'last_status_update') and current_time_ms - self.last_status_update < self.update_throttle_ms:
                return
            self.last_status_update = current_time_ms
            
            # 从信号中解包数据
            state = status_data.get('state', {})
            rewards = status_data.get('rewards', {})
            timestamp_str = status_data.get('timestamp', '')

            if not state or not timestamp_str:
                logger.warning("onStatusUpdated received empty state or timestamp.")
                return

            # --- 1. 获取最新、最权威的电网状态 ---
            # 直接从仿真环境的 grid_simulator 获取，确保数据是最新的
            if hasattr(self, 'simulation_worker') and hasattr(self.simulation_worker, 'environment'):
                grid_status = self.simulation_worker.environment.grid_simulator.get_status()
                # 将最新的电网状态更新回 state 字典，以便所有下游函数都能使用
                state['grid_status'] = grid_status

            else:
                grid_status = state.get('grid_status', {}) # Fallback
            
            # --- 2. 存储历史数据快照 ---
            # 创建一个更轻量的快照以节省内存
            history_snapshot = {
                "timestamp": state.get("timestamp"),
                "users": state.get("users", []), # 注意：这里仍然是完整列表，未来可优化为只存摘要
                "chargers": state.get("chargers", []),
                "grid_status": grid_status, # 使用上面获取的最新电网状态
                "rewards": rewards # 存储奖励，可用于历史分析
            }
            self.simulation_history.append(history_snapshot)
            
            # 限制历史记录长度
            max_history = 200
            if len(self.simulation_history) > max_history:
                self.simulation_history = self.simulation_history[-max_history:]
            
            # --- START OF MODIFICATION ---
            # 检查是否需要执行影响分析回调
            if self.impact_analysis_pending:
                if hasattr(self, 'operator_control_panel') and hasattr(self.operator_control_panel, 'failure_sim_widget'):
                    logger.info("Executing impact analysis callback.")
                    # 将操作后的状态传递给分析面板
                    self.operator_control_panel.failure_sim_widget.analyze_impact(state)
                # 重置标志位
                self.impact_analysis_pending = False
            # --- 3. 更新所有UI面板 ---
            
            dt_object = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            if hasattr(self, 'time_label'):
                self.time_label.setText(dt_object.strftime('%Y-%m-%d %H:%M:%S'))

            # 更新协同仪表盘
            if hasattr(self, 'synergy_dashboard'):
                # 传递完整的历史记录和当前奖励
                self.synergy_dashboard.update_data(self.simulation_history, rewards)
                logger.debug("Synergy Dashboard updated.")

            # 更新地图
            if hasattr(self, 'map_widget'):
                users = state.get('users', [])
                chargers = state.get('chargers', [])
                region_geometries = grid_status.get('region_geometries', {})
                self.map_widget.updateData(users, chargers, grid_regions=region_geometries)
                logger.debug("MapWidget updated.")
            
            # 更新数据详情表格
            if hasattr(self, 'data_table_widget'):
                self.data_table_widget.updateData(state)
                logger.debug("DataTable updated.")

            # 更新用户面板
            if hasattr(self, 'user_control_panel'):
                current_step = len(self.simulation_history) - 1
                self.user_control_panel.updateSimulationData(current_step, current_step, state)
                logger.debug("UserControlPanel updated.")

            # 更新运营商面板
            if hasattr(self, 'operator_control_panel'):
                self.operator_control_panel.updateSimulationData(state)
                logger.debug("OperatorControlPanel updated.")
                
            # 更新电网面板
            if hasattr(self, 'power_grid_panel'):
                self.power_grid_panel.handle_status_update(status_data)
                comparison_data = rewards.get('comparison_metrics_display')
                if comparison_data:
                    self.power_grid_panel.update_algorithm_comparison_chart(comparison_data)
                    logger.debug("Explicitly updated algorithm comparison chart.")
                else:
                    logger.warning("Comparison metrics not found in rewards for GUI update.")
                logger.debug("PowerGridPanel updated.")

            # 更新旧的图表分析页（如果还存在的话，现在被协同仪表盘取代）
            # 这部分逻辑可以保留，以防需要单独的区域图表
            time_series_data = grid_status.get('time_series_data_snapshot', {})
            if hasattr(self, 'regional_load_chart'):
                self.regional_load_chart.updateData(time_series_data)
                logger.debug("RegionalLoadChart updated.")
            
            if hasattr(self, 'regional_heatmap'):
                self.regional_heatmap.updateData(grid_status)
                logger.debug("RegionalHeatmap updated.")

        except Exception as e:
            logger.error(f"状态更新错误: {e}")
            import traceback
            logger.error(traceback.format_exc())

    def onMetricsUpdated(self, metrics):
        """处理指标更新"""
        try:
            # 性能优化：限制更新频率，避免GUI卡死
            import time
            current_time = time.time() * 1000  # 转换为毫秒
            if current_time - self.last_metrics_update < self.update_throttle_ms:
                return  # 跳过过于频繁的更新
            self.last_metrics_update = current_time
            
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
        self.environment = environment
        # 设置用户面板的仿真环境
        if hasattr(self, 'user_control_panel') and self.user_control_panel:
            self.user_control_panel.setSimulationEnvironment(environment)
        # 设置运营商面板的仿真环境
        if hasattr(self, 'operator_control_panel') and self.operator_control_panel:
            self.operator_control_panel.setSimulationEnvironment(environment)
    
    def showConfig(self):
        """显示配置对话框"""
        dialog = ConfigDialog(self.config, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.config = dialog.getConfig()
            self.updateConfigUI()

    def handle_grid_preference_changed(self, preference_name, value):
        """Handles grid preference changes from the PowerGridPanel."""
        logger.info(f"MainWindow: Grid preference changed - {preference_name}: {value}")
        if self.simulation_worker and self.simulation_running: # Check if sim is running
            self.simulation_worker.set_grid_preference(preference_name, value)
        else:
            # Optionally, store it and apply when simulation starts, or just log
            logger.warning("Simulation not running or worker not available. Grid preference change not passed to worker yet.")
            # Example: self.config.setdefault('initial_grid_preferences', {})[preference_name] = value

    def handle_v2g_discharge_requested(self, amount_mw):
        """Handles V2G discharge requests from the PowerGridPanel."""
        logger.info(f"MainWindow: V2G discharge requested: {amount_mw} MW")
        if self.simulation_worker and self.simulation_running: # Check if sim is running
            self.simulation_worker.request_v2g_discharge(amount_mw)
        else:
            logger.warning("Simulation not running or worker not available. V2G request not passed to worker.")
    
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
        # --- START OF MODIFICATION ---
        # 删除了更新进度条的逻辑
        # 这个定时器现在可以用于其他周期性UI更新，或者如果不再需要，可以完全禁用
        # --- END OF MODIFICATION ---
        
        # 更新其他需要定期刷新的显示
        # 例如，更新状态标签、检查仿真状态等
        pass
    
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
