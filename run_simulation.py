#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
命令行仿真运行工具
用于在终端中直接运行EV充电仿真，便于调试和错误输出
"""

import sys
import os
import json
import logging
import traceback
from datetime import datetime
import time

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 导入仿真相关模块
try:
    from simulation.environment import ChargingEnvironment
    from simulation.scheduler import ChargingScheduler
except ImportError as e:
    print(f"导入错误: {e}")
    print("请确保在项目根目录下运行此脚本")
    sys.exit(1)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('simulation_cli.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

def load_config(config_path='config.json'):
    """加载配置文件"""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        logger.info(f"成功加载配置文件: {config_path}")
        return config
    except FileNotFoundError:
        logger.error(f"配置文件未找到: {config_path}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"配置文件JSON格式错误: {e}")
        return None
    except Exception as e:
        logger.error(f"加载配置文件时发生错误: {e}")
        return None

def run_simulation(config, max_steps=100):
    """运行仿真"""
    try:
        logger.info("开始初始化仿真环境...")
        
        # 初始化仿真环境
        environment = ChargingEnvironment(config)
        logger.info("仿真环境初始化成功")
        
        # 初始化调度器
        scheduler = ChargingScheduler(config)
        logger.info("调度器初始化成功")
        
        logger.info("开始运行仿真...")
        step_count = 0
        
        while step_count < max_steps:
            try:
                # 获取当前状态
                current_state = environment.get_current_state()
                logger.info(f"步骤 {step_count + 1}: 获取当前状态成功")
                
                # 调度决策
                decisions = scheduler.make_scheduling_decision(current_state)
                logger.info(f"步骤 {step_count + 1}: 生成调度决策成功")
                
                # 执行一步仿真
                rewards, next_state, done = environment.step(decisions)
                logger.info(f"步骤 {step_count + 1}: 仿真步骤执行成功")
                
                # 输出关键信息
                current_time = next_state.get('current_time', 'unknown')
                user_count = len(next_state.get('users', []))
                charger_count = len(next_state.get('chargers', []))
                
                print(f"\n=== 仿真步骤 {step_count + 1} ===")
                print(f"当前时间: {current_time}")
                print(f"用户数量: {user_count}")
                print(f"充电桩数量: {charger_count}")
                print(f"奖励值: {rewards.get('total_reward', 0):.2f}")
                
                step_count += 1
                
                if done:
                    logger.info("仿真完成")
                    break
                    
                # 短暂延迟
                time.sleep(0.1)
                
            except Exception as e:
                logger.error(f"仿真步骤 {step_count + 1} 执行失败: {e}")
                logger.error(f"错误详情: {traceback.format_exc()}")
                print(f"\n❌ 仿真步骤 {step_count + 1} 失败: {e}")
                break
        
        logger.info(f"仿真结束，共执行 {step_count} 步")
        print(f"\n✅ 仿真完成，共执行 {step_count} 步")
        
    except Exception as e:
        logger.error(f"仿真运行失败: {e}")
        logger.error(f"错误详情: {traceback.format_exc()}")
        print(f"\n❌ 仿真运行失败: {e}")
        print(f"错误详情: {traceback.format_exc()}")
        return False
    
    return True

def main():
    """主函数"""
    print("=== EV充电仿真命令行工具 ===")
    print(f"启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 加载配置
    config = load_config()
    if config is None:
        print("❌ 配置加载失败，程序退出")
        return 1
    
    print("✅ 配置加载成功")
    
    # 运行仿真
    success = run_simulation(config)
    
    if success:
        print("\n🎉 仿真运行成功完成")
        return 0
    else:
        print("\n💥 仿真运行失败")
        return 1

if __name__ == '__main__':
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断仿真")
        sys.exit(130)
    except Exception as e:
        print(f"\n💥 程序异常退出: {e}")
        print(f"错误详情: {traceback.format_exc()}")
        sys.exit(1)