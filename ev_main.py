import argparse
import os
import json
import matplotlib.pyplot as plt
import logging

# 导入自定义模块
# from ev_charging_scheduler import ChargingEnvironment, ChargingScheduler, ChargingVisualizationDashboard
from ev_model_training import DataGenerator, train_model, evaluate_model
from ev_integration_scheduler import IntegratedChargingSystem
from ev_system_test import run_system_tests, run_comprehensive_evaluation
def setup_logging(log_level=logging.INFO, log_file="ev_charging_system.log"):
    """设置日志配置"""
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger("EVChargingSystem")


def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="电动汽车有序充电调度策略系统")
    
    parser.add_argument("--mode", type=str, default="simulate", 
                        choices=["simulate", "train", "evaluate", "visualize", "test", "all"],
                        help="运行模式: simulate(模拟), train(训练), evaluate(评估), visualize(可视化), test(测试), all(全部)")
    
    parser.add_argument("--config", type=str, default="config.json",
                        help="配置文件路径")
    
    parser.add_argument("--days", type=int, default=7,
                        help="模拟天数")
    
    parser.add_argument("--strategy", type=str, default="balanced",
                        choices=["user", "profit", "grid", "balanced"],
                        help="使用的策略: user(用户优先), profit(利润优先), grid(电网友好优先), balanced(平衡)")
    
    parser.add_argument("--output_dir", type=str, default="output",
                        help="输出目录")
    
    parser.add_argument("--log_level", type=str, default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
                        help="日志级别")
    
    return parser.parse_args()


def load_config(config_path):
    """加载配置文件"""
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    else:
        # 创建默认配置
        default_config = {
            "environment": {
                "grid_id": "DEFAULT001",
                "charger_count": 20,
                "user_count": 50,
                "simulation_days": 7,
                "time_step_minutes": 15
            },
            "model": {
                "input_dim": 19,
                "hidden_dim": 128,
                "task_hidden_dim": 64,
                "model_path": "models/ev_charging_model.pth"
            },
            "scheduler": {
                "use_trained_model": True,
                "optimization_weights": {
                    "user_satisfaction": 0.4,
                    "operator_profit": 0.3,
                    "grid_friendliness": 0.3
                }
            },
            "visualization": {
                "dashboard_port": 8050,
                "update_interval": 15,
                "output_dir": "output"
            },
            "strategies": {
                "user": {
                    "user_satisfaction": 0.6,
                    "operator_profit": 0.2,
                    "grid_friendliness": 0.2
                },
                "profit": {
                    "user_satisfaction": 0.2,
                    "operator_profit": 0.6,
                    "grid_friendliness": 0.2
                },
                "grid": {
                    "user_satisfaction": 0.2,
                    "operator_profit": 0.2,
                    "grid_friendliness": 0.6
                },
                "balanced": {
                    "user_satisfaction": 0.33,
                    "operator_profit": 0.33,
                    "grid_friendliness": 0.34
                }
            }
        }
        
        # 保存默认配置
        # 只有当路径不为空时才创建目录
        dir_path = os.path.dirname(config_path)
        if dir_path:  # 如果目录路径不为空
            os.makedirs(dir_path, exist_ok=True)
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(default_config, f, indent=4)
        
        return default_config


def run_simulation(config, args, logger):
    """运行充电调度模拟"""
    logger.info(f"开始运行充电调度模拟，策略: {args.strategy}, 天数: {args.days}")
    
    # 创建输出目录
    os.makedirs(args.output_dir, exist_ok=True)
    
    # 更新配置
    if args.strategy in config["strategies"]:
        config["scheduler"]["optimization_weights"] = config["strategies"][args.strategy]
    
    # 创建集成系统
    system = IntegratedChargingSystem()
    system.config = config
    system.config["visualization"]["output_dir"] = args.output_dir
    
    # 运行模拟
    metrics, avg_metrics = system.run_simulation(days=args.days)
    
    # 分析用户行为
    user_behavior = system.analyze_user_behavior(num_days=args.days)
    
    # 分析电网影响
    grid_impact = system.analyze_grid_impact(num_days=args.days)
    
    # 生成可视化仪表盘
    dashboards = system.generate_dashboards()
    
    logger.info(f"模拟完成，结果保存在: {args.output_dir}")
    logger.info(f"用户仪表盘: {dashboards['user_dashboard']}")
    logger.info(f"运营商仪表盘: {dashboards['operator_dashboard']}")
    
    return metrics, avg_metrics, user_behavior, grid_impact


def train_decision_model(config, args, logger):
    """训练决策模型"""
    logger.info("开始训练决策模型")
    
    # 创建输出目录
    model_dir = os.path.dirname(config["model"]["model_path"])
    os.makedirs(model_dir, exist_ok=True)
    
    # 生成训练数据
    logger.info("生成训练数据...")
    data_gen = DataGenerator(num_samples=50000)
    X, y_satisfaction, y_profit, y_grid = data_gen.generate_samples()
    
    # 划分数据集
    from sklearn.model_selection import train_test_split
    
    X_train, X_temp, y_train_satisfaction, y_temp_satisfaction = train_test_split(
        X, y_satisfaction, test_size=0.3, random_state=42
    )
    
    X_val, X_test, y_val_satisfaction, y_test_satisfaction = train_test_split(
        X_temp, y_temp_satisfaction, test_size=0.5, random_state=42
    )
    
    _, _, y_train_profit, y_temp_profit = train_test_split(
        X, y_profit, test_size=0.3, random_state=42
    )
    
    _, _, y_val_profit, y_test_profit = train_test_split(
        X_temp, y_temp_profit, test_size=0.5, random_state=42
    )
    
    _, _, y_train_grid, y_temp_grid = train_test_split(
        X, y_grid, test_size=0.3, random_state=42
    )
    
    _, _, y_val_grid, y_test_grid = train_test_split(
        X_temp, y_temp_grid, test_size=0.5, random_state=42
    )
    
    # 训练模型
    logger.info("开始训练模型...")
    input_dim = X.shape[1]
    model, history = train_model(
        X_train, y_train_satisfaction, y_train_profit, y_train_grid,
        X_val, y_val_satisfaction, y_val_profit, y_val_grid,
        input_dim, batch_size=64, epochs=50
    )
    
    # 评估模型
    logger.info("评估模型性能...")
    metrics = evaluate_model(
        model, X_test, y_test_satisfaction, y_test_profit, y_test_grid
    )
    
    # 保存模型
    import torch
    torch.save(model.state_dict(), config["model"]["model_path"])
    logger.info(f"模型已保存到: {config['model']['model_path']}")
    
    # 输出评估指标
    logger.info("模型评估指标:")
    logger.info(f"用户满意度 - MSE: {metrics['mse']['satisfaction']:.4f}, MAE: {metrics['mae']['satisfaction']:.4f}, R²: {metrics['r2']['satisfaction']:.4f}")
    logger.info(f"运营商利润 - MSE: {metrics['mse']['profit']:.4f}, MAE: {metrics['mae']['profit']:.4f}, R²: {metrics['r2']['profit']:.4f}")
    logger.info(f"电网友好度 - MSE: {metrics['mse']['grid']:.4f}, MAE: {metrics['mae']['grid']:.4f}, R²: {metrics['r2']['grid']:.4f}")
    
    # 绘制学习曲线
    plt.figure(figsize=(15, 10))
    
    plt.subplot(2, 2, 1)
    plt.plot(history['train_loss'], label='训练损失')
    plt.plot(history['val_loss'], label='验证损失')
    plt.title('训练和验证损失')
    plt.xlabel('轮次')
    plt.ylabel('损失')
    plt.legend()
    
    plt.subplot(2, 2, 2)
    plt.plot(history['satisfaction_loss'], label='满意度损失')
    plt.title('用户满意度损失')
    plt.xlabel('轮次')
    plt.ylabel('损失')
    plt.legend()
    
    plt.subplot(2, 2, 3)
    plt.plot(history['profit_loss'], label='利润损失')
    plt.title('运营商利润损失')
    plt.xlabel('轮次')
    plt.ylabel('损失')
    plt.legend()
    
    plt.subplot(2, 2, 4)
    plt.plot(history['grid_loss'], label='电网友好度损失')
    plt.title('电网友好度损失')
    plt.xlabel('轮次')
    plt.ylabel('损失')
    plt.legend()
    
    plt.tight_layout()
    plt.savefig(f"{args.output_dir}/learning_curves.png")
    
    logger.info(f"学习曲线已保存到: {args.output_dir}/learning_curves.png")
    
    return model, metrics


def compare_strategies(config, args, logger):
    """比较不同调度策略"""
    logger.info("开始比较不同调度策略")
    
    # 创建集成系统
    system = IntegratedChargingSystem()
    system.config = config
    system.config["visualization"]["output_dir"] = args.output_dir
    
    # 构建策略列表
    strategies = []
    for name, weights in config["strategies"].items():
        strategies.append({
            "name": name,
            "params": {
                "scheduler.optimization_weights.user_satisfaction": weights["user_satisfaction"],
                "scheduler.optimization_weights.operator_profit": weights["operator_profit"],
                "scheduler.optimization_weights.grid_friendliness": weights["grid_friendliness"]
            },
            "use_model": config["scheduler"]["use_trained_model"]
        })
    
    # 比较策略
    comparison = system.compare_scheduling_strategies(strategies)
    
    # 输出比较结果
    logger.info("策略比较结果:")
    for i, strategy in enumerate(comparison["strategy_names"]):
        logger.info(f"策略: {strategy}")
        logger.info(f"  用户满意度: {comparison['user_satisfaction'][i]:.4f}")
        logger.info(f"  运营商利润: {comparison['operator_profit'][i]:.4f}")
        logger.info(f"  电网友好度: {comparison['grid_friendliness'][i]:.4f}")
        logger.info(f"  综合奖励: {comparison['total_reward'][i]:.4f}")
    
    logger.info(f"策略比较结果已保存到: {args.output_dir}")
    
    return comparison


def run_visualization(config, args, logger):
    """生成可视化结果"""
    logger.info("生成可视化结果")
    
    # 创建集成系统
    system = IntegratedChargingSystem()
    system.config = config
    system.config["visualization"]["output_dir"] = args.output_dir
    
    # 生成仪表盘
    dashboards = system.generate_dashboards()
    
    logger.info(f"可视化结果已生成:")
    logger.info(f"用户仪表盘: {dashboards['user_dashboard']}")
    logger.info(f"运营商仪表盘: {dashboards['operator_dashboard']}")
    
    return dashboards


def main():
    """主函数：运行指定模式的任务"""
    # 解析命令行参数
    args = parse_arguments()
    
    # 设置日志
    log_level = getattr(logging, args.log_level)
    logger = setup_logging(log_level=log_level)
    
    # 加载配置
    config = load_config(args.config)
    
    # 更新输出目录
    config["visualization"]["output_dir"] = args.output_dir
    os.makedirs(args.output_dir, exist_ok=True)
    
    logger.info(f"运行模式: {args.mode}")
    
    # 根据不同模式执行相应任务
    if args.mode == "simulate" or args.mode == "all":
        run_simulation(config, args, logger)
    
    if args.mode == "train" or args.mode == "all":
        train_decision_model(config, args, logger)
    
    if args.mode == "evaluate" or args.mode == "all":
        compare_strategies(config, args, logger)
    
    if args.mode == "visualize" or args.mode == "all":
        run_visualization(config, args, logger)
    
    if args.mode == "test" or args.mode == "all":
        logger.info("运行系统测试...")
        run_system_tests()
        
        logger.info("运行综合评价...")
        run_comprehensive_evaluation()
    
    logger.info("所有任务已完成")


if __name__ == "__main__":
    main()
