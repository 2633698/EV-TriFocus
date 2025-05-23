#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EV充电调度仿真系统启动脚本
功能：检查依赖、配置环境、启动GUI
"""

import sys
import os
import subprocess
import importlib
import json
from pathlib import Path

def check_python_version():
    """检查Python版本"""
    if sys.version_info < (3, 8):
        print("❌ 错误：需要Python 3.8或更高版本")
        print(f"当前版本：{sys.version}")
        return False
    print(f"✅ Python版本检查通过：{sys.version}")
    return True

def check_dependencies():
    """检查必要的依赖库"""
    required_packages = [
        ('PyQt6', 'PyQt6'),
        ('numpy', 'numpy'),
        ('pandas', 'pandas'),
        ('pyqtgraph', 'pyqtgraph')
    ]
    
    missing_packages = []
    
    for package_name, import_name in required_packages:
        try:
            importlib.import_module(import_name)
            print(f"✅ {package_name} - 已安装")
        except ImportError:
            print(f"❌ {package_name} - 未安装")
            missing_packages.append(package_name)
    
    if missing_packages:
        print(f"\n缺少以下依赖包：{', '.join(missing_packages)}")
        print("请运行以下命令安装：")
        print(f"pip install {' '.join(missing_packages)}")
        return False
    
    return True

def setup_environment():
    """设置环境变量和路径"""
    # 添加当前目录到Python路径
    current_dir = Path(__file__).parent.absolute()
    if str(current_dir) not in sys.path:
        sys.path.insert(0, str(current_dir))
    
    # 设置Qt相关环境变量
    os.environ['QT_AUTO_SCREEN_SCALE_FACTOR'] = '1'
    os.environ['QT_ENABLE_HIGHDPI_SCALING'] = '1'
    
    print("✅ 环境配置完成")

def create_default_config():
    """创建默认配置文件"""
    config_path = Path("config.json")
    
    if config_path.exists():
        print("✅ 配置文件已存在")
        return True
    
    default_config = {
        "environment": {
            "simulation_days": 7,
            "user_count": 1000,
            "station_count": 20,
            "chargers_per_station": 10,
            "region_count": 3,
            "time_step_minutes": 15,
            "map_bounds": {
                "lat_min": 30.5,
                "lat_max": 31.0,
                "lng_min": 114.0,
                "lng_max": 114.5
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
                           1050, 1000, 950, 900, 1000, 1100, 1050, 950, 850, 750, 700, 650],
                "region_2": [400, 380, 360, 340, 320, 340, 380, 450, 520, 580, 620, 650,
                           680, 650, 620, 580, 650, 720, 680, 620, 560, 500, 460, 420]
            },
            "solar_generation": {
                "region_0": [0, 0, 0, 0, 0, 0, 50, 150, 300, 450, 550, 600,
                           650, 600, 550, 450, 300, 150, 50, 0, 0, 0, 0, 0],
                "region_1": [0, 0, 0, 0, 0, 0, 40, 120, 250, 380, 480, 520,
                           560, 520, 480, 380, 250, 120, 40, 0, 0, 0, 0, 0],
                "region_2": [0, 0, 0, 0, 0, 0, 30, 90, 180, 270, 340, 370,
                           400, 370, 340, 270, 180, 90, 30, 0, 0, 0, 0, 0]
            },
            "wind_generation": {
                "region_0": [200, 180, 160, 140, 120, 130, 150, 170, 160, 140, 120, 110,
                           100, 110, 120, 140, 160, 180, 200, 220, 240, 230, 220, 210],
                "region_1": [150, 140, 130, 120, 110, 120, 130, 140, 130, 120, 110, 100,
                           90, 100, 110, 120, 130, 140, 150, 160, 170, 165, 160, 155],
                "region_2": [100, 95, 90, 85, 80, 85, 90, 100, 95, 85, 80, 75,
                           70, 75, 80, 85, 95, 100, 110, 120, 125, 120, 115, 105]
            },
            "system_capacity_kw": {
                "region_0": 2000,
                "region_1": 1500,
                "region_2": 1000
            }
        },
        "ui": {
            "theme": "light",
            "update_interval_ms": 1000,
            "chart_max_points": 288,
            "map_refresh_rate": 2000
        }
    }
    
    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(default_config, f, indent=2, ensure_ascii=False)
        print("✅ 默认配置文件已创建")
        return True
    except Exception as e:
        print(f"❌ 创建配置文件失败：{e}")
        return False

def check_simulation_modules():
    """检查仿真模块"""
    simulation_dir = Path("simulation")
    
    if not simulation_dir.exists():
        print("❌ simulation目录不存在")
        print("请确保以下文件存在：")
        print("  - simulation/environment.py")
        print("  - simulation/scheduler.py")
        print("  - simulation/grid_model_enhanced.py")
        print("  - simulation/metrics.py")
        return False
    
    required_modules = [
        "environment.py",
        "scheduler.py", 
        "grid_model_enhanced.py",
        "metrics.py",
        "utils.py"
    ]
    
    missing_modules = []
    for module in required_modules:
        if not (simulation_dir / module).exists():
            missing_modules.append(module)
    
    if missing_modules:
        print(f"❌ 缺少仿真模块：{', '.join(missing_modules)}")
        return False
    
    print("✅ 仿真模块检查通过")
    return True

def launch_gui():
    """启动GUI应用"""
    try:
        from ev_charging_gui import main
        print("🚀 启动GUI应用...")
        main()
    except ImportError as e:
        print(f"❌ 导入GUI模块失败：{e}")
        return False
    except Exception as e:
        print(f"❌ 启动GUI失败：{e}")
        return False

def install_dependencies():
    """安装依赖"""
    print("正在安装依赖包...")
    try:
        result = subprocess.run([
            sys.executable, "-m", "pip", "install", "-r", "requirements.txt"
        ], check=True, capture_output=True, text=True)
        print("✅ 依赖安装完成")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ 依赖安装失败：{e}")
        print(f"错误输出：{e.stderr}")
        return False
    except FileNotFoundError:
        print("❌ requirements.txt文件不存在")
        return False

def main():
    """主函数"""
    print("=" * 60)
    print("🔋 EV充电调度仿真系统启动检查")
    print("=" * 60)
    
    # 检查Python版本
    if not check_python_version():
        sys.exit(1)
    
    # 检查依赖
    if not check_dependencies():
        choice = input("\n是否自动安装缺失的依赖？(y/n): ").lower()
        if choice == 'y':
            if not install_dependencies():
                sys.exit(1)
        else:
            sys.exit(1)
    
    # 设置环境
    setup_environment()
    
    # 创建默认配置
    if not create_default_config():
        sys.exit(1)
    
    # 检查仿真模块
    if not check_simulation_modules():
        print("\n请确保simulation模块正确配置后重新运行")
        sys.exit(1)
    
    print("\n" + "=" * 60)
    print("✅ 所有检查完成，准备启动系统...")
    print("=" * 60)
    
    # 启动GUI
    launch_gui()

if __name__ == "__main__":
    main()
