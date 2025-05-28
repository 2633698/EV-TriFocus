# -*- coding: utf-8 -*-
"""
充电预约系统
为电动汽车用户提供充电站预约功能
"""

import sys
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum

# 设置预约系统专用日志记录器
reservation_logger = logging.getLogger('reservation_system')
reservation_handler = logging.FileHandler('reservation_system.log', encoding='utf-8')
reservation_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
reservation_handler.setFormatter(reservation_formatter)
reservation_logger.addHandler(reservation_handler)
reservation_logger.setLevel(logging.DEBUG)
reservation_logger.propagate = False  # 防止重复输出到根日志记录器

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, 
    QPushButton, QGroupBox, QScrollArea, QFrame, QListWidget,
    QListWidgetItem, QComboBox, QSpinBox, QDoubleSpinBox,
    QTextEdit, QProgressBar, QTabWidget, QTableWidget,
    QTableWidgetItem, QHeaderView, QSlider, QCheckBox,
    QSplitter, QDialog, QDialogButtonBox, QFormLayout,
    QMessageBox, QLineEdit, QDateTimeEdit, QCalendarWidget,
    QTimeEdit, QRadioButton, QButtonGroup
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread, QSize, QRect, QDateTime
from PyQt6.QtGui import (
    QFont, QPainter, QPen, QBrush, QColor, QPixmap, QIcon,
    QLinearGradient, QPalette
)

logger = logging.getLogger(__name__)

# 使用专用的预约日志记录器
def log_reservation(level, message, *args, **kwargs):
    """预约系统专用日志记录函数"""
    reservation_logger.log(level, message, *args, **kwargs)

class ReservationStatus(Enum):
    """预约状态枚举"""
    PENDING = "pending"          # 待确认
    CONFIRMED = "confirmed"      # 已确认
    ACTIVE = "active"            # 进行中
    COMPLETED = "completed"      # 已完成
    CANCELLED = "cancelled"      # 已取消
    EXPIRED = "expired"          # 已过期

@dataclass
class ChargingReservation:
    """充电预约数据类"""
    reservation_id: str
    user_id: str
    station_id: str
    charger_id: str
    start_time: datetime
    end_time: datetime
    target_soc: int
    charging_type: str
    estimated_cost: float
    estimated_duration: int  # 分钟
    status: ReservationStatus
    created_at: datetime
    updated_at: datetime
    notes: str = ""
    
class ReservationTimeSlotWidget(QWidget):
    """时间段选择组件"""
    
    timeSlotSelected = pyqtSignal(str, str)  # start_time, end_time
    
    def __init__(self, parent=None, simulation_time=None):
        super().__init__(parent)
        # 使用仿真时间或当前时间作为基准
        self.simulation_time = simulation_time or datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        self.selected_date = self.simulation_time.date()
        self.available_slots = []
        self.setupUI()
        
    def setupUI(self):
        layout = QVBoxLayout(self)
        
        # 日期选择
        date_group = QGroupBox("选择日期")
        date_layout = QVBoxLayout(date_group)
        
        self.calendar = QCalendarWidget()
        # 使用仿真时间设置日期范围
        sim_qdate = QDateTime(self.simulation_time).date()
        self.calendar.setMinimumDate(sim_qdate)
        self.calendar.setMaximumDate(sim_qdate.addDays(7))
        # 设置默认选中日期为仿真时间日期
        self.calendar.setSelectedDate(sim_qdate)
        self.calendar.clicked.connect(self.onDateChanged)
        date_layout.addWidget(self.calendar)
        
        layout.addWidget(date_group)
        
        # 时间段选择
        time_group = QGroupBox("可用时间段")
        time_layout = QVBoxLayout(time_group)
        
        self.time_slots_list = QListWidget()
        self.time_slots_list.itemClicked.connect(self.onTimeSlotSelected)
        time_layout.addWidget(self.time_slots_list)
        
        layout.addWidget(time_group)
        
        # 在所有UI组件创建完成后，手动触发一次日期改变事件
        self.onDateChanged(sim_qdate)
        
    def onDateChanged(self, date):
        """日期改变处理"""
        # PyQt6中使用toPyDate()方法
        if hasattr(date, 'toPyDate'):
            self.selected_date = date.toPyDate()
        elif hasattr(date, 'toPython'):
            self.selected_date = date.toPython()
        else:
            # 如果是Python的date对象，直接使用
            self.selected_date = date
        self.updateTimeSlots()
        
    def updateTimeSlots(self):
        """更新可用时间段"""
        self.time_slots_list.clear()
        
        # 生成时间段（每2小时一个时间段）
        # 使用仿真时间基准，确保与仿真时间一致
        current_time = datetime.combine(self.selected_date, datetime.min.time())
        
        # 如果选择的是仿真当天，则从当前仿真时间开始
        if self.selected_date == self.simulation_time.date():
            current_time = max(current_time, self.simulation_time.replace(minute=0, second=0, microsecond=0))
            
        end_of_day = datetime.combine(self.selected_date, datetime.max.time().replace(hour=22, minute=0))
        
        while current_time < end_of_day:
            slot_end = current_time + timedelta(hours=2)
            if slot_end > end_of_day:
                break
                
            # 检查时间段可用性（简化逻辑）
            is_available = self.checkSlotAvailability(current_time, slot_end)
            
            item_text = f"{current_time.strftime('%H:%M')} - {slot_end.strftime('%H:%M')}"
            if not is_available:
                item_text += " (已预约)"
                
            item = QListWidgetItem(item_text)
            item.setData(Qt.ItemDataRole.UserRole, (current_time, slot_end))
            
            if is_available:
                item.setBackground(QColor(240, 248, 255))  # 浅蓝色
            else:
                item.setBackground(QColor(245, 245, 245))  # 灰色
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
                
            self.time_slots_list.addItem(item)
            current_time += timedelta(hours=2)
            
    def checkSlotAvailability(self, start_time, end_time):
        """检查时间段可用性（简化实现）"""
        # 这里应该查询实际的预约数据
        # 简化实现：随机生成一些不可用时间段
        import random
        return random.random() > 0.3
        
    def onTimeSlotSelected(self, item):
        """时间段选择处理"""
        if item.flags() & Qt.ItemFlag.ItemIsSelectable:
            start_time, end_time = item.data(Qt.ItemDataRole.UserRole)
            self.timeSlotSelected.emit(
                start_time.isoformat(),
                end_time.isoformat()
            )

class ReservationDialog(QDialog):
    """预约对话框"""
    
    def __init__(self, station_data, user_data, parent=None, simulation_time=None):
        super().__init__(parent)
        self.station_data = station_data
        self.user_data = user_data
        self.simulation_time = simulation_time
        self.selected_start_time = None
        self.selected_end_time = None
        self.setWindowTitle("充电预约")
        self.setModal(True)
        self.resize(600, 700)
        self.setupUI()
        
    def setupUI(self):
        layout = QVBoxLayout(self)
        
        # 标题
        title = QLabel("充电站预约")
        title.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        
        # 充电站信息
        station_group = QGroupBox("充电站信息")
        station_layout = QFormLayout(station_group)
        
        station_layout.addRow("充电站:", QLabel(self.station_data.get('name', '--')))
        station_layout.addRow("地址:", QLabel(self.station_data.get('address', '--')))
        station_layout.addRow("最大功率:", QLabel(f"{self.station_data.get('max_power', 60)}kW"))
        station_layout.addRow("当前价格:", QLabel(f"¥{self.station_data.get('current_price', 1.0):.2f}/度"))
        
        layout.addWidget(station_group)
        
        # 时间选择
        self.time_slot_widget = ReservationTimeSlotWidget(simulation_time=self.simulation_time)
        self.time_slot_widget.timeSlotSelected.connect(self.onTimeSlotSelected)
        layout.addWidget(self.time_slot_widget)
        
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
        
        # 备注
        self.notes_edit = QTextEdit()
        self.notes_edit.setMaximumHeight(60)
        self.notes_edit.setPlaceholderText("可选：添加预约备注...")
        params_layout.addRow("备注:", self.notes_edit)
        
        layout.addWidget(params_group)
        
        # 预估信息
        self.estimate_group = QGroupBox("预估信息")
        estimate_layout = QFormLayout(self.estimate_group)
        
        self.estimate_duration_label = QLabel("--")
        self.estimate_cost_label = QLabel("--")
        self.estimate_energy_label = QLabel("--")
        
        estimate_layout.addRow("预估时长:", self.estimate_duration_label)
        estimate_layout.addRow("预估费用:", self.estimate_cost_label)
        estimate_layout.addRow("预估充电量:", self.estimate_energy_label)
        
        layout.addWidget(self.estimate_group)
        
        # 按钮
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | 
            QDialogButtonBox.StandardButton.Cancel
        )
        button_box.button(QDialogButtonBox.StandardButton.Ok).setText("确认预约")
        button_box.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
        # 连接信号
        self.target_soc_spin.valueChanged.connect(self.updateEstimates)
        self.charging_type_combo.currentTextChanged.connect(self.updateEstimates)
        
        # 初始状态
        button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        
    def onTimeSlotSelected(self, start_time_str, end_time_str):
        """时间段选择处理"""
        self.selected_start_time = datetime.fromisoformat(start_time_str)
        self.selected_end_time = datetime.fromisoformat(end_time_str)
        self.updateEstimates()
        
        # 启用确认按钮
        button_box = self.findChild(QDialogButtonBox)
        if button_box:
            button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(True)
            
    def updateEstimates(self):
        """更新预估信息"""
        if not self.selected_start_time:
            return
            
        target_soc = self.target_soc_spin.value()
        charging_type = self.charging_type_combo.currentText()
        
        # 简化的预估计算
        current_soc = self.user_data.get('soc', 30)
        soc_needed = target_soc - current_soc
        battery_capacity = 60  # 假设60kWh电池
        
        energy_needed = (soc_needed / 100) * battery_capacity
        
        if charging_type == "快充":
            power = self.station_data.get('max_power', 60)
            time_hours = energy_needed / power
            price_per_kwh = self.station_data.get('current_price', 1.5)
        else:
            power = 7  # 7kW功率
            time_hours = energy_needed / power
            price_per_kwh = self.station_data.get('current_price', 1.0) * 0.8
            
        duration_minutes = int(time_hours * 60)
        cost = energy_needed * price_per_kwh
        
        self.estimate_duration_label.setText(f"{duration_minutes}分钟")
        self.estimate_cost_label.setText(f"¥{cost:.2f}")
        self.estimate_energy_label.setText(f"{energy_needed:.1f} kWh")
        
    def getReservationData(self):
        """获取预约数据"""
        if not self.selected_start_time:
            return None
            
        return {
            'start_time': self.selected_start_time,
            'end_time': self.selected_end_time,
            'target_soc': self.target_soc_spin.value(),
            'charging_type': self.charging_type_combo.currentText(),
            'notes': self.notes_edit.toPlainText(),
            'estimated_duration': int((self.selected_end_time - self.selected_start_time).total_seconds() / 60),
            'estimated_cost': float(self.estimate_cost_label.text().replace('¥', '').replace('--', '0'))
        }

class ReservationListWidget(QWidget):
    """预约列表组件"""
    
    reservationSelected = pyqtSignal(str)  # reservation_id
    reservationCancelled = pyqtSignal(str)  # reservation_id
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.reservations = []
        self.setupUI()
        
    def setupUI(self):
        layout = QVBoxLayout(self)
        
        # 筛选器
        filter_layout = QHBoxLayout()
        
        filter_layout.addWidget(QLabel("状态筛选:"))
        self.status_filter = QComboBox()
        self.status_filter.addItems(["全部", "待确认", "已确认", "进行中", "已完成", "已取消"])
        self.status_filter.currentTextChanged.connect(self.updateReservationList)
        filter_layout.addWidget(self.status_filter)
        
        filter_layout.addStretch()
        
        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self.refreshReservations)
        filter_layout.addWidget(refresh_btn)
        
        layout.addLayout(filter_layout)
        
        # 预约列表
        self.reservation_list = QListWidget()
        self.reservation_list.itemClicked.connect(self.onReservationSelected)
        layout.addWidget(self.reservation_list)
        
    def updateReservations(self, reservations):
        """更新预约列表"""
        self.reservations = reservations
        self.updateReservationList()
        
    def updateReservationList(self):
        """更新显示的预约列表"""
        self.reservation_list.clear()
        
        filter_status = self.status_filter.currentText()
        
        for reservation in self.reservations:
            # 应用筛选
            if filter_status != "全部":
                status_map = {
                    "待确认": ReservationStatus.PENDING,
                    "已确认": ReservationStatus.CONFIRMED,
                    "进行中": ReservationStatus.ACTIVE,
                    "已完成": ReservationStatus.COMPLETED,
                    "已取消": ReservationStatus.CANCELLED
                }
                if reservation.status != status_map.get(filter_status):
                    continue
                    
            # 创建列表项
            item_widget = self.createReservationItem(reservation)
            item = QListWidgetItem()
            item.setSizeHint(item_widget.sizeHint())
            item.setData(Qt.ItemDataRole.UserRole, reservation.reservation_id)
            
            self.reservation_list.addItem(item)
            self.reservation_list.setItemWidget(item, item_widget)
            
    def createReservationItem(self, reservation):
        """创建预约项组件"""
        widget = QFrame()
        widget.setFrameStyle(QFrame.Shape.Box)
        widget.setStyleSheet("""
            QFrame {
                border: 1px solid #ddd;
                border-radius: 8px;
                background: white;
                margin: 2px;
            }
        """)
        
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 8, 12, 8)
        
        # 第一行：充电站和状态
        header_layout = QHBoxLayout()
        
        station_label = QLabel(f"充电站: {reservation.station_id}")
        station_label.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        header_layout.addWidget(station_label)
        
        header_layout.addStretch()
        
        status_label = QLabel(self.getStatusText(reservation.status))
        status_label.setStyleSheet(f"color: {self.getStatusColor(reservation.status)}; font-weight: bold;")
        header_layout.addWidget(status_label)
        
        layout.addLayout(header_layout)
        
        # 第二行：时间信息
        time_layout = QHBoxLayout()
        
        time_label = QLabel(f"时间: {reservation.start_time.strftime('%m-%d %H:%M')} - {reservation.end_time.strftime('%H:%M')}")
        time_layout.addWidget(time_label)
        
        time_layout.addStretch()
        
        duration_label = QLabel(f"时长: {reservation.estimated_duration}分钟")
        time_layout.addWidget(duration_label)
        
        layout.addLayout(time_layout)
        
        # 第三行：充电参数
        params_layout = QHBoxLayout()
        
        soc_label = QLabel(f"目标SOC: {reservation.target_soc}%")
        params_layout.addWidget(soc_label)
        
        type_label = QLabel(f"类型: {reservation.charging_type}")
        params_layout.addWidget(type_label)
        
        params_layout.addStretch()
        
        cost_label = QLabel(f"预估费用: ¥{reservation.estimated_cost:.2f}")
        cost_label.setStyleSheet("color: #dc3545; font-weight: bold;")
        params_layout.addWidget(cost_label)
        
        layout.addLayout(params_layout)
        
        # 操作按钮（根据状态显示）
        if reservation.status in [ReservationStatus.PENDING, ReservationStatus.CONFIRMED]:
            button_layout = QHBoxLayout()
            button_layout.addStretch()
            
            cancel_btn = QPushButton("取消预约")
            cancel_btn.setStyleSheet("""
                QPushButton {
                    background: #dc3545;
                    color: white;
                    border: none;
                    padding: 4px 12px;
                    border-radius: 4px;
                }
                QPushButton:hover {
                    background: #c82333;
                }
            """)
            cancel_btn.clicked.connect(lambda: self.reservationCancelled.emit(reservation.reservation_id))
            button_layout.addWidget(cancel_btn)
            
            layout.addLayout(button_layout)
            
        return widget
        
    def getStatusText(self, status):
        """获取状态文本"""
        status_map = {
            ReservationStatus.PENDING: "待确认",
            ReservationStatus.CONFIRMED: "已确认",
            ReservationStatus.ACTIVE: "进行中",
            ReservationStatus.COMPLETED: "已完成",
            ReservationStatus.CANCELLED: "已取消",
            ReservationStatus.EXPIRED: "已过期"
        }
        return status_map.get(status, "未知")
        
    def getStatusColor(self, status):
        """获取状态颜色"""
        color_map = {
            ReservationStatus.PENDING: "#ffc107",
            ReservationStatus.CONFIRMED: "#28a745",
            ReservationStatus.ACTIVE: "#007bff",
            ReservationStatus.COMPLETED: "#6f42c1",
            ReservationStatus.CANCELLED: "#dc3545",
            ReservationStatus.EXPIRED: "#6c757d"
        }
        return color_map.get(status, "#6c757d")
        
    def onReservationSelected(self, item):
        """预约选择处理"""
        reservation_id = item.data(Qt.ItemDataRole.UserRole)
        self.reservationSelected.emit(reservation_id)
        
    def refreshReservations(self):
        """刷新预约列表"""
        # 这里应该从数据源重新加载预约数据
        self.updateReservationList()

class ReservationManager:
    """预约管理器"""
    
    def __init__(self):
        self.reservations = {}
        self.next_id = 1
        
    def createReservation(self, user_id, station_id, charger_id, reservation_data):
        """创建预约"""
        reservation_id = f"RES_{self.next_id:06d}"
        self.next_id += 1
        
        log_reservation(logging.INFO, f"=== 创建预约开始 ===")
        log_reservation(logging.INFO, f"预约ID: {reservation_id}")
        log_reservation(logging.INFO, f"用户ID: {user_id}")
        log_reservation(logging.INFO, f"充电站ID: {station_id}")
        log_reservation(logging.INFO, f"充电桩ID: {charger_id}")
        log_reservation(logging.INFO, f"开始时间: {reservation_data['start_time']}")
        log_reservation(logging.INFO, f"结束时间: {reservation_data['end_time']}")
        log_reservation(logging.INFO, f"目标SOC: {reservation_data['target_soc']}%")
        log_reservation(logging.INFO, f"充电类型: {reservation_data['charging_type']}")
        log_reservation(logging.INFO, f"预估费用: ¥{reservation_data['estimated_cost']:.2f}")
        log_reservation(logging.INFO, f"预估时长: {reservation_data['estimated_duration']}分钟")
        
        reservation = ChargingReservation(
            reservation_id=reservation_id,
            user_id=user_id,
            station_id=station_id,
            charger_id=charger_id,
            start_time=reservation_data['start_time'],
            end_time=reservation_data['end_time'],
            target_soc=reservation_data['target_soc'],
            charging_type=reservation_data['charging_type'],
            estimated_cost=reservation_data['estimated_cost'],
            estimated_duration=reservation_data['estimated_duration'],
            status=ReservationStatus.CONFIRMED,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            notes=reservation_data.get('notes', '')
        )
        
        self.reservations[reservation_id] = reservation
        log_reservation(logging.INFO, f"✓ 预约创建成功: {reservation_id}")
        logger.info(f"创建预约: {reservation_id} for user {user_id} at station {station_id}")
        
        return reservation
        
    def cancelReservation(self, reservation_id):
        """取消预约"""
        log_reservation(logging.INFO, f"尝试取消预约: {reservation_id}")
        if reservation_id in self.reservations:
            reservation = self.reservations[reservation_id]
            old_status = reservation.status
            reservation.status = ReservationStatus.CANCELLED
            reservation.updated_at = datetime.now()
            log_reservation(logging.INFO, f"✓ 预约取消成功: {reservation_id} (原状态: {old_status.value})")
            logger.info(f"取消预约: {reservation_id}")
            return True
        else:
            log_reservation(logging.WARNING, f"✗ 预约取消失败: {reservation_id} 不存在")
            return False
        
    def getUserReservations(self, user_id):
        """获取用户预约列表"""
        return [r for r in self.reservations.values() if r.user_id == user_id]
        
    def getStationReservations(self, station_id, date=None):
        """获取充电站预约列表"""
        reservations = [r for r in self.reservations.values() if r.station_id == station_id]
        
        if date:
            reservations = [r for r in reservations if r.start_time.date() == date]
            
        return reservations
        
    def updateReservationStatus(self, reservation_id, status):
        """更新预约状态"""
        if reservation_id in self.reservations:
            reservation = self.reservations[reservation_id]
            old_status = reservation.status
            reservation.status = status
            reservation.updated_at = datetime.now()
            log_reservation(logging.INFO, f"预约状态更新: {reservation_id} {old_status.value} -> {status.value}")
            logger.info(f"更新预约状态: {reservation_id} -> {status.value}")
            return True
        else:
            log_reservation(logging.WARNING, f"预约状态更新失败: {reservation_id} 不存在")
            return False
    
    def checkAndProcessReservations(self, current_time, users, chargers):
        """检查并处理到期的预约"""
        processed_reservations = []
        
        # 添加调试日志
        confirmed_reservations = [r for r in self.reservations.values() if r.status == ReservationStatus.CONFIRMED]
        log_reservation(logging.INFO, f"=== 预约检查开始 ===")
        log_reservation(logging.INFO, f"当前时间: {current_time}")
        log_reservation(logging.INFO, f"已确认预约数量: {len(confirmed_reservations)}")
        
        if confirmed_reservations:
            logger.info(f"检查预约执行: 当前时间 {current_time}, 共有 {len(confirmed_reservations)} 个已确认预约")
        
        for reservation_id, reservation in self.reservations.items():
            # 只处理已确认的预约
            if reservation.status != ReservationStatus.CONFIRMED:
                continue
                
            # 检查预约时间是否到了（允许10分钟的提前量和30分钟的延后量）
            time_diff = (reservation.start_time - current_time).total_seconds() / 60
            log_reservation(logging.DEBUG, f"预约 {reservation_id}: 开始时间 {reservation.start_time}, 当前时间 {current_time}, 时间差 {time_diff:.1f} 分钟")
            logger.debug(f"预约 {reservation_id}: 开始时间 {reservation.start_time}, 当前时间 {current_time}, 时间差 {time_diff:.1f} 分钟")
            
            if -10 <= time_diff <= 30:  # 预约时间前10分钟到后30分钟内
                user_id = reservation.user_id
                charger_id = reservation.charger_id
                
                log_reservation(logging.INFO, f"预约 {reservation_id} 进入执行窗口: 用户 {user_id}, 充电桩 {charger_id}")
                
                # 检查用户和充电桩是否存在
                if user_id in users and charger_id in chargers:
                    user = users[user_id]
                    charger = chargers[charger_id]
                    
                    current_status = user.get('status')
                    log_reservation(logging.INFO, f"预约 {reservation_id} 用户状态检查: 用户 {user_id} 当前状态 {current_status}")
                    logger.info(f"预约 {reservation_id} 检查用户状态: 用户 {user_id} 当前状态 {user.get('status')}")
                    
                    # 检查用户是否空闲或正在旅行（不是正在充电）
                    # 对于预约用户，即使在充电也要检查是否需要切换到预约的充电桩
                    if current_status not in ['charging', 'waiting'] or user.get('target_charger') != charger_id:
                        log_reservation(logging.INFO, f"预约 {reservation_id} 开始执行: 更新状态为ACTIVE")
                        # 更新预约状态为进行中
                        self.updateReservationStatus(reservation_id, ReservationStatus.ACTIVE)
                        
                        # 设置用户的预约充电参数
                        user['target_soc'] = reservation.target_soc
                        user['preferred_charging_type'] = reservation.charging_type
                        user['reservation_id'] = reservation_id
                        user['is_reservation_user'] = True
                        
                        log_reservation(logging.INFO, f"预约 {reservation_id} 设置用户参数: SOC目标 {reservation.target_soc}%, 充电类型 {reservation.charging_type}")
                        
                        # 强制清除之前的决策状态，确保预约优先
                        user['needs_charge_decision'] = False
                        user['manual_decision'] = False
                        
                        # 添加到处理列表，返回给调用者进行路径规划
                        processed_reservations.append({
                            'user_id': user_id,
                            'charger_id': charger_id,
                            'reservation_id': reservation_id,
                            'reservation': reservation
                        })
                        
                        log_reservation(logging.INFO, f"✓ 预约执行成功: {reservation_id} - 用户 {user_id} 前往充电桩 {charger_id} (时间差: {time_diff:.1f}分钟)")
                        logger.info(f"✓ 执行预约: {reservation_id} - 用户 {user_id} 前往充电桩 {charger_id} (时间差: {time_diff:.1f}分钟)")
                    else:
                        log_reservation(logging.WARNING, f"预约 {reservation_id} 暂时无法执行: 用户 {user_id} 状态为 {current_status}, 目标充电桩 {user.get('target_charger')}")
                        logger.warning(f"预约 {reservation_id} 暂时无法执行: 用户 {user_id} 状态为 {current_status}, 目标充电桩 {user.get('target_charger')}")
                else:
                    log_reservation(logging.ERROR, f"预约 {reservation_id} 无法执行: 用户存在 {user_id in users}, 充电桩存在 {charger_id in chargers}")
                    logger.error(f"预约 {reservation_id} 无法执行: 用户 {user_id in users} 或充电桩 {charger_id in chargers} 不存在")
            
            # 检查预约是否已过期（超过结束时间30分钟）
            elif (current_time - reservation.end_time).total_seconds() / 60 > 30:
                if reservation.status in [ReservationStatus.CONFIRMED, ReservationStatus.ACTIVE]:
                    log_reservation(logging.INFO, f"预约过期处理: {reservation_id} 超过结束时间30分钟")
                    self.updateReservationStatus(reservation_id, ReservationStatus.EXPIRED)
                    logger.info(f"预约已过期: {reservation_id}")
        
        log_reservation(logging.INFO, f"=== 预约检查结束 ===")
        log_reservation(logging.INFO, f"本次处理的预约数量: {len(processed_reservations)}")
        if processed_reservations:
            for proc_res in processed_reservations:
                log_reservation(logging.INFO, f"处理的预约: {proc_res['reservation_id']} - 用户 {proc_res['user_id']} -> 充电桩 {proc_res['charger_id']}")
        
        return processed_reservations
    
    def completeReservation(self, reservation_id):
        """完成预约（当用户充电完成时调用）"""
        log_reservation(logging.INFO, f"尝试完成预约: {reservation_id}")
        if reservation_id in self.reservations:
            reservation = self.reservations[reservation_id]
            if reservation.status == ReservationStatus.ACTIVE:
                self.updateReservationStatus(reservation_id, ReservationStatus.COMPLETED)
                log_reservation(logging.INFO, f"✓ 预约完成: {reservation_id}")
                logger.info(f"预约完成: {reservation_id}")
                return True
            else:
                log_reservation(logging.WARNING, f"✗ 预约完成失败: {reservation_id} 状态不是ACTIVE (当前: {reservation.status.value})")
        else:
            log_reservation(logging.WARNING, f"✗ 预约完成失败: {reservation_id} 不存在")
        return False

# 全局预约管理器实例
reservation_manager = ReservationManager()