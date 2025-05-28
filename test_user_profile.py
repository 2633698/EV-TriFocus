#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
用户画像功能测试脚本
"""

import sys
import json
from datetime import datetime, timedelta
from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget
from user_panel import UserInfoPanel

class TestWindow(QMainWindow):
    """测试窗口"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("用户画像可视化测试")
        self.setGeometry(100, 100, 800, 600)
        
        # 创建中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 创建布局
        layout = QVBoxLayout(central_widget)
        
        # 创建用户信息面板
        self.user_info_panel = UserInfoPanel()
        layout.addWidget(self.user_info_panel)
        
        # 加载测试数据
        self.loadTestData()
    
    def loadTestData(self):
        """加载测试数据"""
        # 模拟用户数据
        test_user_data = {
            'user_id': 'test_user_001',
            'user_type': 'taxi',
            'user_profile': 'urgent',
            'vehicle_type': 'Model 3',
            'status': 'traveling',
            'soc': 35.5,
            'current_position': {
                'lat': 39.9042,
                'lng': 116.4074
            }
        }
        
        # 模拟充电历史数据
        test_charging_history = []
        base_time = datetime.now() - timedelta(days=30)
        
        for i in range(15):
            session = {
                'session_id': f'session_{i:03d}',
                'start_time': (base_time + timedelta(days=i*2, hours=i%24)).isoformat(),
                'end_time': (base_time + timedelta(days=i*2, hours=i%24, minutes=45)).isoformat(),
                'charger_type': 'superfast' if i % 3 == 0 else ('fast' if i % 2 == 0 else 'normal'),
                'power_kw': 120 if i % 3 == 0 else (60 if i % 2 == 0 else 30),
                'initial_soc': 20 + (i % 40),
                'final_soc': 80 + (i % 20),
                'duration_minutes': 30 + (i % 60),
                'cost': 25.5 + (i % 50),
                'energy_kwh': 35.2 + (i % 30)
            }
            test_charging_history.append(session)
        
        # 更新用户信息面板
        self.user_info_panel.updateUserInfo(test_user_data, test_charging_history)

def main():
    """主函数"""
    app = QApplication(sys.argv)
    
    # 创建测试窗口
    window = TestWindow()
    window.show()
    
    # 运行应用
    sys.exit(app.exec())

if __name__ == '__main__':
    main()