import os
import sys
import logging

# 设置日志记录
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("TestImport")

try:
    logger.info("正在导入模块...")
    from ev_charging_scheduler import ChargingEnvironment, ChargingScheduler
    logger.info("导入 ev_charging_scheduler 成功")
    
    from ev_integration_scheduler import IntegratedChargingSystem
    logger.info("导入 ev_integration_scheduler 成功")
    
    from ev_multi_agent_system import MultiAgentSystem
    logger.info("导入 ev_multi_agent_system 成功")
    
    logger.info("正在加载配置...")
    config_path = 'config.json'
    if os.path.exists(config_path):
        logger.info(f"配置文件存在: {config_path}")
    else:
        logger.error(f"配置文件不存在: {config_path}")
    
    logger.info("尝试创建和初始化系统...")
    try:
        system = IntegratedChargingSystem()
        logger.info("已创建 IntegratedChargingSystem 实例")
    except Exception as e:
        logger.error(f"创建系统时出错: {str(e)}", exc_info=True)
    
    # 测试系统初始化
    try:
        if os.path.exists('config.json'):
            import json
            with open('config.json', 'r', encoding='utf-8') as f:
                config = json.load(f)
                logger.info("成功读取配置文件")
                
                # 初始化系统
                system.initialize(config)
                logger.info("系统初始化成功")
        else:
            logger.error("找不到配置文件，无法初始化系统")
    except Exception as e:
        logger.error(f"初始化系统时出错: {str(e)}", exc_info=True)

except Exception as e:
    logger.error(f"运行测试时出错: {str(e)}", exc_info=True)

print("测试完成，请检查日志输出") 