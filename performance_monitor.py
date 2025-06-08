#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
性能监控工具
用于监控EV充电仿真系统的性能指标
"""

import psutil
import time
import logging
from PyQt6.QtCore import QTimer, QObject, pyqtSignal
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar, QGroupBox

logger = logging.getLogger(__name__)

class PerformanceMonitor(QObject):
    """性能监控器"""
    
    performance_updated = pyqtSignal(dict)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.process = psutil.Process()
        self.start_time = time.time()
        self.last_cpu_times = self.process.cpu_times()
        
        # 创建监控定时器
        self.monitor_timer = QTimer()
        self.monitor_timer.timeout.connect(self._collectMetrics)
        self.monitor_timer.start(5000)  # 每5秒收集一次性能数据
        
        # 性能历史数据
        self.performance_history = {
            'cpu_percent': [],
            'memory_mb': [],
            'memory_percent': [],
            'timestamps': []
        }
        
    def _collectMetrics(self):
        """收集性能指标"""
        try:
            # CPU使用率
            cpu_percent = self.process.cpu_percent()
            
            # 内存使用情况
            memory_info = self.process.memory_info()
            memory_mb = memory_info.rss / 1024 / 1024  # 转换为MB
            memory_percent = self.process.memory_percent()
            
            # 系统总体情况
            system_cpu = psutil.cpu_percent()
            system_memory = psutil.virtual_memory().percent
            
            # 线程数
            thread_count = self.process.num_threads()
            
            # 运行时间
            runtime = time.time() - self.start_time
            
            # 构建性能数据
            performance_data = {
                'process_cpu_percent': cpu_percent,
                'process_memory_mb': memory_mb,
                'process_memory_percent': memory_percent,
                'system_cpu_percent': system_cpu,
                'system_memory_percent': system_memory,
                'thread_count': thread_count,
                'runtime_seconds': runtime,
                'timestamp': time.time()
            }
            
            # 保存历史数据
            self.performance_history['cpu_percent'].append(cpu_percent)
            self.performance_history['memory_mb'].append(memory_mb)
            self.performance_history['memory_percent'].append(memory_percent)
            self.performance_history['timestamps'].append(time.time())
            
            # 限制历史数据长度
            max_history = 100
            for key in self.performance_history:
                if len(self.performance_history[key]) > max_history:
                    self.performance_history[key] = self.performance_history[key][-max_history:]
            
            # 发送性能数据
            self.performance_updated.emit(performance_data)
            
            # 记录性能警告
            if cpu_percent > 80:
                logger.warning(f"CPU使用率过高: {cpu_percent:.1f}%")
            if memory_mb > 1000:  # 超过1GB
                logger.warning(f"内存使用过高: {memory_mb:.1f}MB")
                
        except Exception as e:
            logger.error(f"性能监控错误: {e}")
    
    def getPerformanceHistory(self):
        """获取性能历史数据"""
        return self.performance_history.copy()
    
    def getPerformanceSummary(self):
        """获取性能摘要"""
        if not self.performance_history['cpu_percent']:
            return None
            
        cpu_data = self.performance_history['cpu_percent']
        memory_data = self.performance_history['memory_mb']
        
        return {
            'avg_cpu_percent': sum(cpu_data) / len(cpu_data),
            'max_cpu_percent': max(cpu_data),
            'avg_memory_mb': sum(memory_data) / len(memory_data),
            'max_memory_mb': max(memory_data),
            'sample_count': len(cpu_data)
        }

class PerformanceWidget(QWidget):
    """性能显示组件"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUI()
        
        # 创建性能监控器
        self.monitor = PerformanceMonitor()
        self.monitor.performance_updated.connect(self.updateDisplay)
        
    def setupUI(self):
        """设置UI"""
        layout = QVBoxLayout(self)
        
        # CPU使用率组
        cpu_group = QGroupBox("CPU使用率")
        cpu_layout = QVBoxLayout(cpu_group)
        
        self.cpu_label = QLabel("CPU: 0%")
        self.cpu_progress = QProgressBar()
        self.cpu_progress.setRange(0, 100)
        
        cpu_layout.addWidget(self.cpu_label)
        cpu_layout.addWidget(self.cpu_progress)
        
        # 内存使用组
        memory_group = QGroupBox("内存使用")
        memory_layout = QVBoxLayout(memory_group)
        
        self.memory_label = QLabel("内存: 0 MB")
        self.memory_progress = QProgressBar()
        self.memory_progress.setRange(0, 100)
        
        memory_layout.addWidget(self.memory_label)
        memory_layout.addWidget(self.memory_progress)
        
        # 系统信息组
        system_group = QGroupBox("系统信息")
        system_layout = QVBoxLayout(system_group)
        
        self.system_cpu_label = QLabel("系统CPU: 0%")
        self.system_memory_label = QLabel("系统内存: 0%")
        self.thread_label = QLabel("线程数: 0")
        self.runtime_label = QLabel("运行时间: 0s")
        
        system_layout.addWidget(self.system_cpu_label)
        system_layout.addWidget(self.system_memory_label)
        system_layout.addWidget(self.thread_label)
        system_layout.addWidget(self.runtime_label)
        
        # 添加到主布局
        layout.addWidget(cpu_group)
        layout.addWidget(memory_group)
        layout.addWidget(system_group)
        
    def updateDisplay(self, performance_data):
        """更新显示"""
        try:
            # 更新CPU显示
            cpu_percent = performance_data['process_cpu_percent']
            self.cpu_label.setText(f"CPU: {cpu_percent:.1f}%")
            self.cpu_progress.setValue(int(cpu_percent))
            
            # 更新内存显示
            memory_mb = performance_data['process_memory_mb']
            memory_percent = performance_data['process_memory_percent']
            self.memory_label.setText(f"内存: {memory_mb:.1f} MB ({memory_percent:.1f}%)")
            self.memory_progress.setValue(int(memory_percent))
            
            # 更新系统信息
            self.system_cpu_label.setText(f"系统CPU: {performance_data['system_cpu_percent']:.1f}%")
            self.system_memory_label.setText(f"系统内存: {performance_data['system_memory_percent']:.1f}%")
            self.thread_label.setText(f"线程数: {performance_data['thread_count']}")
            
            runtime = performance_data['runtime_seconds']
            if runtime < 60:
                runtime_str = f"{runtime:.0f}s"
            elif runtime < 3600:
                runtime_str = f"{runtime/60:.1f}m"
            else:
                runtime_str = f"{runtime/3600:.1f}h"
            self.runtime_label.setText(f"运行时间: {runtime_str}")
            
            # 设置进度条颜色
            if cpu_percent > 80:
                self.cpu_progress.setStyleSheet("QProgressBar::chunk { background-color: red; }")
            elif cpu_percent > 60:
                self.cpu_progress.setStyleSheet("QProgressBar::chunk { background-color: orange; }")
            else:
                self.cpu_progress.setStyleSheet("QProgressBar::chunk { background-color: green; }")
                
            if memory_percent > 80:
                self.memory_progress.setStyleSheet("QProgressBar::chunk { background-color: red; }")
            elif memory_percent > 60:
                self.memory_progress.setStyleSheet("QProgressBar::chunk { background-color: orange; }")
            else:
                self.memory_progress.setStyleSheet("QProgressBar::chunk { background-color: green; }")
                
        except Exception as e:
            logger.error(f"性能显示更新错误: {e}")