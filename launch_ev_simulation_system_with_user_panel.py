#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EV充电调度仿真系统启动脚本（带用户面板）
Enhanced EV Charging Simulation System with User Panel
"""

import sys
import os
import json
import logging
import traceback
from pathlib import Path

def setup_logging():
    """设置日志系统"""
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('ev_simulation.log', encoding='utf-8')
        ]
    )
    
    # 设置特定模块的日志级别
    logging.getLogger('user_panel').setLevel(logging.DEBUG)
    logging.getLogger('ev_charging_gui').setLevel(logging.INFO)
    
    return logging.getLogger(__name__)

def check_dependencies():
    """检查依赖包"""
    logger = logging.getLogger(__name__)
    required_packages = [
        ('PyQt6', 'PyQt6'),
        ('numpy', 'numpy'),
        ('pandas', 'pandas'),
        ('pyqtgraph', 'pyqtgraph')
    ]
    
    missing_packages = []
    
    for display_name, import_name in required_packages:
        try:
            __import__(import_name)
            logger.info(f"✓ {display_name} 已安装")
        except ImportError:
            missing_packages.append(display_name)
            logger.error(f"✗ {display_name} 未安装")
    
    if missing_packages:
        logger.error(f"缺少以下依赖包: {', '.join(missing_packages)}")
        logger.info("请运行以下命令安装:")
        logger.info(f"pip install {' '.join(missing_packages)}")
        return False
    
    return True

def check_project_structure():
    """检查项目结构"""
    logger = logging.getLogger(__name__)
    required_files = [
        'simulation/environment.py',
        'simulation/scheduler.py',
        'simulation/user_model.py',
        'simulation/charger_model.py',
        'simulation/grid_model_enhanced.py',
        'simulation/metrics.py',
        'simulation/utils.py',
        'algorithms/rule_based.py',
        'algorithms/uncoordinated.py',
        'ev_charging_gui.py',
        'user_panel.py',
        'advanced_charts.py',
        'config.json'
    ]
    
    missing_files = []
    
    for file_path in required_files:
        if not Path(file_path).exists():
            missing_files.append(file_path)
            logger.error(f"✗ 缺少文件: {file_path}")
        else:
            logger.info(f"✓ 找到文件: {file_path}")
    
    if missing_files:
        logger.error(f"缺少 {len(missing_files)} 个必需文件")
        return False
    
    return True

def load_config():
    """加载配置文件"""
    logger = logging.getLogger(__name__)
    config_path = Path('config.json')
    
    if not config_path.exists():
        logger.warning("配置文件不存在，创建默认配置...")
        default_config = create_default_config()
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(default_config, f, indent=2, ensure_ascii=False)
        logger.info("默认配置文件已创建")
        return default_config
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        logger.info("配置文件加载成功")
        return config
    except Exception as e:
        logger.error(f"配置文件加载失败: {e}")
        logger.info("使用默认配置...")
        return create_default_config()

def create_default_config():
    """创建默认配置"""
    return {
        "environment": {
            "simulation_days": 1,
            "user_count": 50,
            "station_count": 10,
            "chargers_per_station": 5,
            "time_step_minutes": 15,
            "region_count": 3,
            "enable_uncoordinated_baseline": True,
            "min_charge_threshold_percent": 20.0,
            "force_charge_soc_threshold": 15.0,
            "default_charge_soc_threshold": 40.0,
            "charger_queue_capacity": 5,
            "charger_failure_rate": 0.05,
            "map_bounds": {
                "lat_min": 30.0,
                "lat_max": 30.1,
                "lng_min": 116.0,
                "lng_max": 116.1
            },
            "user_defaults": {
                "soc_distribution": [
                    [0.2, [10, 30]],
                    [0.4, [30, 60]],
                    [0.3, [60, 80]],
                    [0.1, [80, 95]]
                ]
            },
            "charger_defaults": {
                "superfast_ratio": 0.1,
                "fast_ratio": 0.3,
                "power_ranges": {
                    "superfast": [150, 350],
                    "fast": [50, 120],
                    "normal": [7, 22]
                },
                "price_multipliers": {
                    "superfast": 1.8,
                    "fast": 1.3,
                    "normal": 1.0
                }
            }
        },
        "grid": {
            "base_load": {
                "region_0": [800, 750, 700, 650, 600, 650, 800, 1000, 1200, 1300, 1350, 1400, 1450, 1400, 1350, 1300, 1400, 1500, 1450, 1300, 1100, 950, 900, 850],
                "region_1": [600, 550, 500, 450, 400, 450, 600, 800, 1000, 1100, 1150, 1200, 1250, 1200, 1150, 1100, 1200, 1300, 1250, 1100, 900, 750, 700, 650],
                "region_2": [400, 350, 300, 250, 200, 250, 400, 600, 800, 900, 950, 1000, 1050, 1000, 950, 900, 1000, 1100, 1050, 900, 700, 550, 500, 450]
            },
            "solar_generation": {
                "region_0": [0, 0, 0, 0, 0, 0, 20, 80, 200, 350, 450, 500, 520, 500, 450, 350, 200, 80, 20, 0, 0, 0, 0, 0],
                "region_1": [0, 0, 0, 0, 0, 0, 15, 60, 150, 280, 360, 400, 420, 400, 360, 280, 150, 60, 15, 0, 0, 0, 0, 0],
                "region_2": [0, 0, 0, 0, 0, 0, 10, 40, 100, 200, 260, 300, 320, 300, 260, 200, 100, 40, 10, 0, 0, 0, 0, 0]
            },
            "wind_generation": {
                "region_0": [150, 140, 120, 100, 80, 90, 110, 130, 120, 100, 90, 85, 80, 85, 90, 100, 120, 140, 160, 170, 165, 160, 155, 150],
                "region_1": [120, 110, 100, 80, 60, 70, 90, 110, 100, 80, 70, 65, 60, 65, 70, 80, 100, 120, 130, 140, 135, 130, 125, 120],
                "region_2": [80, 70, 60, 50, 40, 45, 60, 80, 70, 50, 45, 40, 35, 40, 45, 50, 70, 80, 90, 95, 90, 85, 80, 75]
            },
            "system_capacity_kw": {
                "region_0": 2000,
                "region_1": 1500,
                "region_2": 1000
            },
            "peak_hours": [7, 8, 9, 10, 18, 19, 20, 21],
            "valley_hours": [0, 1, 2, 3, 4, 5],
            "normal_price": 0.85,
            "peak_price": 1.2,
            "valley_price": 0.4
        },
        "scheduler": {
            "scheduling_algorithm": "rule_based",
            "optimization_weights": {
                "user_satisfaction": 0.4,
                "operator_profit": 0.3,
                "grid_friendliness": 0.3
            },
            "marl_config": {
                "action_space_size": 6,
                "discount_factor": 0.95,
                "exploration_rate": 0.1,
                "learning_rate": 0.01,
                "q_table_path": "models/marl_q_tables.pkl"
            }
        },
        "algorithms": {
            "rule_based": {
                "max_queue": {"peak": 3, "valley": 8, "shoulder": 5},
                "candidate_limit": 12,
                "queue_penalty": 0.08
            }
        },
        "user_panel": {
            "enabled": True,
            "max_recommendations": 10,
            "update_interval_ms": 1000,
            "decision_timeout_minutes": 30,
            "priority_boost_for_manual": True
        },
        "ui": {
            "theme": "light",
            "update_interval_ms": 1000,
            "chart_max_points": 200,
            "map_refresh_rate": 2000
        }
    }

def setup_python_path():
    """设置Python路径"""
    current_dir = Path.cwd()
    simulation_dir = current_dir / 'simulation'
    algorithms_dir = current_dir / 'algorithms'
    
    # 添加到sys.path
    for path in [current_dir, simulation_dir, algorithms_dir]:
        path_str = str(path)
        if path_str not in sys.path:
            sys.path.insert(0, path_str)

def validate_config(config):
    """验证配置文件"""
    logger = logging.getLogger(__name__)
    
    # 检查必需的配置节
    required_sections = ['environment', 'grid', 'scheduler']
    for section in required_sections:
        if section not in config:
            logger.error(f"配置文件缺少 '{section}' 节")
            return False
    
    # 检查用户面板配置
    if 'user_panel' not in config:
        logger.warning("配置文件缺少用户面板配置，使用默认设置")
        config['user_panel'] = {
            "enabled": True,
            "max_recommendations": 10,
            "update_interval_ms": 1000,
            "decision_timeout_minutes": 30
        }
    
    # 验证数值范围
    env_config = config['environment']
    if env_config.get('user_count', 0) < 1:
        logger.error("用户数量必须大于0")
        return False
    
    if env_config.get('station_count', 0) < 1:
        logger.error("充电站数量必须大于0")
        return False
    
    logger.info("配置文件验证通过")
    return True

def create_backup_config(config):
    """创建配置备份"""
    logger = logging.getLogger(__name__)
    try:
        backup_path = Path('config_backup.json')
        with open(backup_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        logger.info(f"配置备份已创建: {backup_path}")
    except Exception as e:
        logger.warning(f"创建配置备份失败: {e}")

def main():
    """主函数"""
    print("=" * 60)
    print("🚗 EV充电调度仿真系统（用户面板版本）")
    print("   Electric Vehicle Charging Simulation with User Panel")
    print("=" * 60)
    
    # 设置日志
    logger = setup_logging()
    logger.info("系统启动中...")
    
    try:
        # 1. 检查依赖
        logger.info("步骤 1/7: 检查依赖包...")
        if not check_dependencies():
            logger.error("依赖检查失败，程序退出")
            return 1
        
        # 2. 检查项目结构
        logger.info("步骤 2/7: 检查项目结构...")
        if not check_project_structure():
            logger.error("项目结构检查失败，程序退出")
            return 1
        
        # 3. 设置Python路径
        logger.info("步骤 3/7: 设置Python路径...")
        setup_python_path()
        
        # 4. 加载配置
        logger.info("步骤 4/7: 加载配置文件...")
        config = load_config()
        
        # 5. 验证配置
        logger.info("步骤 5/7: 验证配置...")
        if not validate_config(config):
            logger.error("配置验证失败，程序退出")
            return 1
        
        # 6. 创建配置备份
        logger.info("步骤 6/7: 创建配置备份...")
        create_backup_config(config)
        
        # 7. 启动GUI应用
        logger.info("步骤 7/7: 启动图形界面...")
        
        # 动态导入GUI模块
        try:
            from PyQt6.QtWidgets import QApplication
            from PyQt6.QtCore import Qt
            
            # 导入主GUI模块
            from ev_charging_gui import MainWindow
            
            # 设置高DPI支持
            QApplication.setHighDpiScaleFactorRoundingPolicy(
                Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
            )
            QApplication.setAttribute(Qt.ApplicationAttribute.AA_Use96Dpi)
            
            # 创建应用
            app = QApplication(sys.argv)
            app.setApplicationName("EV充电调度仿真系统")
            app.setApplicationVersion("2.0 (用户面板版)")
            app.setOrganizationName("EV Research Lab")
            
            # 设置样式
            app.setStyle('Fusion')
            
            # 创建主窗口
            window = MainWindow()
            
            # 应用配置
            window.config = config
            window.updateConfigUI()
            
            # 显示启动信息
            logger.info("🎉 系统启动成功！")
            logger.info(f"用户数量: {config['environment']['user_count']}")
            logger.info(f"充电站数量: {config['environment']['station_count']}")
            logger.info(f"仿真天数: {config['environment']['simulation_days']}")
            logger.info(f"用户面板: {'启用' if config.get('user_panel', {}).get('enabled', True) else '禁用'}")
            logger.info("请在图形界面中开始仿真...")
            
            # 显示窗口
            window.show()
            
            # 运行应用
            return app.exec()
            
        except ImportError as e:
            logger.error(f"GUI模块导入失败: {e}")
            logger.info("请检查PyQt6是否正确安装")
            return 1
        except Exception as e:
            logger.error(f"GUI启动失败: {e}")
            logger.error(traceback.format_exc())
            return 1
    
    except KeyboardInterrupt:
        logger.info("用户中断程序")
        return 0
    except Exception as e:
        logger.error(f"程序运行出错: {e}")
        logger.error(traceback.format_exc())
        return 1

def show_help():
    """显示帮助信息"""
    help_text = """
🚗 EV充电调度仿真系统（用户面板版本）使用说明

基本功能：
  • 实时仿真电动汽车充电调度过程
  • 支持多种智能调度算法
  • 提供用户交互面板，支持手动决策
  • 可视化分析仿真结果

用户面板功能：
  • 用户信息管理 - 查看用户状态和车辆信息
  • 充电历史记录 - 查看过往充电记录和统计
  • 充电站推荐 - 智能推荐合适的充电站
  • 充电站详情 - 查看充电站实时状态和价格
  • 手动决策 - 为选定用户人工选择充电站

操作流程：
  1. 启动系统后，在左侧选择调度算法和策略
  2. 点击"启动"开始仿真
  3. 切换到"用户面板"选项卡
  4. 在仿真过程中暂停并选择用户
  5. 为选定用户查看推荐并做出充电决策
  6. 应用决策后继续仿真观察结果

配置文件：
  • config.json - 主配置文件
  • config_backup.json - 自动备份
  
日志文件：
  • ev_simulation.log - 运行日志

依赖要求：
  • Python 3.8+
  • PyQt6
  • numpy, pandas
  • pyqtgraph (可选，用于高级图表)

获取帮助：
  • 查看README.md文件
  • 检查日志文件排查问题
"""
    print(help_text)

if __name__ == '__main__':
    # 检查命令行参数
    if len(sys.argv) > 1:
        if sys.argv[1] in ['-h', '--help', 'help']:
            show_help()
            sys.exit(0)
        elif sys.argv[1] in ['-v', '--version', 'version']:
            print("EV充电调度仿真系统 v2.0 (用户面板版)")
            sys.exit(0)
    
    # 运行主程序
    exit_code = main()
    
    if exit_code == 0:
        print("\n✅ 程序正常退出")
    else:
        print(f"\n❌ 程序异常退出 (代码: {exit_code})")
    
    sys.exit(exit_code)