import torch
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime
import json
import os
import logging
from tqdm import tqdm

from ev_charging_scheduler import ChargingEnvironment, ChargingScheduler
from ev_model_training import MultiTaskModel


class IntegratedChargingSystem:
    """
    集成充电系统管理类，整合环境、模型和调度策略
    """
    
    def __init__(self, config_path=None):

        # 配置日志
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler("charging_system.log"),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger("ChargingSystem")
        
        # 加载配置
        if config_path and os.path.exists(config_path):
            with open(config_path, 'r') as f:
                self.config = json.load(f)
        else:
            # 默认配置
            self.config = {
                "environment": {
                    "grid_id": "0258",
                    "charger_count": 20,
                    "user_count": 50,
                    "simulation_days": 7,
                    "time_step_minutes": 15
                },
                "model": {
                    "input_dim": 19,
                    "hidden_dim": 128,
                    "task_hidden_dim": 64,
                    "model_path": "ev_charging_model.pth"
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
                    
                    "update_interval": 15,  # 秒
                    "output_dir": "output"
                }
            }
            
        # 创建输出目录
        os.makedirs(self.config["visualization"]["output_dir"], exist_ok=True)
        
        # 初始化环境
        self.env_config = self.config["environment"]
        self.env = ChargingEnvironment(self.env_config)
        
        # 初始化调度器
        self.scheduler = ChargingScheduler({
            "grid_id": self.env_config["grid_id"],
            "charger_count": self.env_config["charger_count"],
            "user_count": self.env_config["user_count"]
        })
        
        # 加载预训练模型（如果存在）
        model_path = self.config["model"]["model_path"]
        if os.path.exists(model_path) and self.config["scheduler"]["use_trained_model"]:
            self.logger.info(f"加载预训练模型: {model_path}")
            self.load_pretrained_model(model_path)
        else:
            self.logger.info("未找到预训练模型或配置为不使用模型，将使用启发式规则进行调度")
        
        
        
        # 初始化性能指标记录
        self.metrics_history = {
            "timestamp": [],
            "user_satisfaction": [],
            "operator_profit": [],
            "grid_friendliness": [],
            "total_reward": [],
            "charging_sessions": [],
            "average_wait_time": [],
            "energy_delivered": [],
            "revenue": [],
            "peak_load": [],
            "load_balancing_index": []
        }
        
        self.logger.info("系统初始化完成")
    
    def load_pretrained_model(self, model_path):

        model_path = self.config["model"]["model_path"]
        self.logger.info(f"检查模型文件: {model_path}, 存在: {os.path.exists(model_path)}")
        try:
            # 创建模型实例
            model_config = self.config["model"]
            self.model = MultiTaskModel(
                input_dim=model_config["input_dim"],
                hidden_dim=model_config["hidden_dim"],
                task_hidden_dim=model_config["task_hidden_dim"]
            )
            
            # 加载模型权重
            self.model.load_state_dict(torch.load(model_path))
            self.model.eval()  # 设置为评估模式
            
            # 将模型关联到调度器
            self.scheduler.user_model = self.model
            self.scheduler.is_trained = True
            
            self.logger.info("成功加载预训练模型")
            return True
        except Exception as e:
            self.logger.error(f"加载模型失败: {str(e)}")
            import traceback
            self.logger.error(traceback.format_exc())  # 打印完整堆栈
            return False

    
    def run_simulation(self, days=None, output_metrics=True):
        """运行充电调度模拟"""
        if days is None:
            days = self.env_config.get("simulation_days", 7)
        
        # 计算模拟步数 (每15分钟一步)
        steps_per_day = 24 * 60 // self.env_config.get("time_step_minutes", 15)
        num_steps = days * steps_per_day
        
        self.logger.info(f"开始运行充电调度模拟，模拟天数: {days}天，总步数: {num_steps}步")
        
        # 确保环境和调度器正确初始化
        if not hasattr(self, 'env') or self.env is None:
            self.env = ChargingEnvironment(self.env_config)
        
        if not hasattr(self, 'scheduler') or self.scheduler is None:
            self.scheduler = ChargingScheduler({
                "grid_id": self.env_config["grid_id"],
                "charger_count": self.env_config["charger_count"],
                "user_count": self.env_config["user_count"]
            })
            # 如有必要，重新加载预训练模型
            if hasattr(self, 'model') and self.model is not None:
                self.scheduler.user_model = self.model
                self.scheduler.is_trained = True
        
        # 运行模拟
        metrics, avg_metrics = self.scheduler.run_simulation(num_steps=num_steps)
        
        # 记录和输出指标
        if output_metrics:
            self._output_simulation_results(metrics, avg_metrics, days)
        
        return metrics, avg_metrics
    
    def _output_simulation_results(self, metrics, avg_metrics, days):
        """
        输出模拟结果
        
        参数:
            metrics: 模拟指标
            avg_metrics: 平均指标
            days: 模拟天数
        """
        output_dir = self.config["visualization"]["output_dir"]
        
        # 保存指标数据
        metrics_df = pd.DataFrame({
            "time_step": range(len(metrics["user_satisfaction"])),
            "user_satisfaction": metrics["user_satisfaction"],
            "operator_profit": metrics["operator_profit"],
            "grid_friendliness": metrics["grid_friendliness"],
            "total_reward": metrics["total_reward"]
        })
        
        metrics_df.to_csv(f"{output_dir}/simulation_metrics.csv", index=False)
        
        # 绘制指标变化图
        self.scheduler.visualize_results(metrics)
        plt.figure(figsize=(12, 6))
        
        # 打印平均指标
        self.logger.info(f"模拟完成，{days}天平均指标:")
        self.logger.info(f"  用户满意度: {avg_metrics['user_satisfaction']:.4f}")
        self.logger.info(f"  运营商利润: {avg_metrics['operator_profit']:.4f}")
        self.logger.info(f"  电网友好度: {avg_metrics['grid_friendliness']:.4f}")
        self.logger.info(f"  综合奖励: {avg_metrics['total_reward']:.4f}")
    
    def run_sensitivity_analysis(self, parameter_ranges, target_metric="total_reward"):
        """
        运行敏感性分析，分析参数变化对系统性能的影响
        
        参数:
            parameter_ranges: 参数范围字典，格式为 {"参数名": [值列表]}
            target_metric: 目标指标名称
        
        返回:
            results: 敏感性分析结果
        """
        self.logger.info(f"开始敏感性分析，目标指标: {target_metric}")
        
        results = {}
        base_config = self.config.copy()
        
        for param_name, param_values in parameter_ranges.items():
            self.logger.info(f"分析参数 '{param_name}' 的影响...")
            param_results = []
            
            for value in tqdm(param_values):
                # 更新特定参数
                if "." in param_name:
                    # 处理嵌套参数
                    parts = param_name.split(".")
                    target_dict = self.config
                    for part in parts[:-1]:
                        target_dict = target_dict[part]
                    target_dict[parts[-1]] = value
                else:
                    # 顶层参数
                    self.config[param_name] = value
                
                # 重新初始化环境和调度器（如果需要）
                if param_name.startswith("environment") or param_name == "charger_count" or param_name == "user_count":
                    self.env = ChargingEnvironment(self.env_config)
                    self.scheduler = ChargingScheduler({
                        "grid_id": self.env_config["grid_id"],
                        "charger_count": self.env_config["charger_count"],
                        "user_count": self.env_config["user_count"]
                    })
                    
                    if os.path.exists(self.config["model"]["model_path"]) and self.config["scheduler"]["use_trained_model"]:
                        self.load_pretrained_model(self.config["model"]["model_path"])
                
                # 运行短期模拟
                _, avg_metrics = self.run_simulation(days=2, output_metrics=False)
                
                # 记录结果
                param_results.append({
                    "param_value": value,
                    "metric_value": avg_metrics[target_metric]
                })
            
            # 存储参数分析结果
            results[param_name] = param_results
            
            # 恢复基础配置
            self.config = base_config.copy()
        
        # 绘制敏感性分析图表
        self._plot_sensitivity_analysis(results, target_metric)
        
        return results
    
    def _plot_sensitivity_analysis(self, results, target_metric):
        """
        绘制敏感性分析图表
        
        参数:
            results: 敏感性分析结果
            target_metric: 目标指标名称
        """
        output_dir = self.config["visualization"]["output_dir"]
        
        plt.figure(figsize=(15, 10))
        
        for i, (param_name, param_results) in enumerate(results.items()):
            plt.subplot(2, 2, i+1)
            
            x = [r["param_value"] for r in param_results]
            y = [r["metric_value"] for r in param_results]
            
            plt.plot(x, y, 'o-', linewidth=2)
            plt.title(f"参数 '{param_name}' 对 {target_metric} 的影响")
            plt.xlabel(param_name)
            plt.ylabel(target_metric)
            plt.grid(True)
            
            # 标记最优参数值
            best_idx = np.argmax(y)
            plt.scatter([x[best_idx]], [y[best_idx]], color='red', s=100, zorder=5)
            plt.annotate(f"最优值: {x[best_idx]}", 
                         (x[best_idx], y[best_idx]), 
                         xytext=(10, -20), 
                         textcoords='offset points',
                         bbox=dict(boxstyle="round,pad=0.3", fc="yellow", alpha=0.8))
        
        plt.tight_layout()
        plt.savefig(f"{output_dir}/sensitivity_analysis.png")
        plt.close()
    
    def compare_scheduling_strategies(self, strategies):
        """
        比较不同调度策略的性能
        
        参数:
            strategies: 策略列表，每个策略是一个字典，包含策略名和参数
        
        返回:
            comparison: 比较结果
        """
        self.logger.info(f"开始比较 {len(strategies)} 种不同的调度策略")
        
        comparison = {
            "strategy_names": [],
            "user_satisfaction": [],
            "operator_profit": [],
            "grid_friendliness": [],
            "total_reward": []
        }
        
        original_config = self.config.copy()
        
        for strategy in strategies:
            self.logger.info(f"评估策略: {strategy['name']}")
            comparison["strategy_names"].append(strategy["name"])
            
            # 更新配置
            for key, value in strategy.get("params", {}).items():
                if "." in key:
                    # 处理嵌套参数
                    parts = key.split(".")
                    target_dict = self.config
                    for part in parts[:-1]:
                        target_dict = target_dict[part]
                    target_dict[parts[-1]] = value
                else:
                    # 顶层参数
                    self.config[key] = value
            
            # 重新初始化环境和调度器
            self.env = ChargingEnvironment(self.env_config)
            self.scheduler = ChargingScheduler({
                "grid_id": self.env_config["grid_id"],
                "charger_count": self.env_config["charger_count"],
                "user_count": self.env_config["user_count"]
            })
            
            if strategy.get("use_model", False) and os.path.exists(self.config["model"]["model_path"]):
                self.load_pretrained_model(self.config["model"]["model_path"])
            
            # 运行模拟
            _, avg_metrics = self.run_simulation(days=3, output_metrics=False)
            
            # 记录结果
            for metric in ["user_satisfaction", "operator_profit", "grid_friendliness", "total_reward"]:
                comparison[metric].append(avg_metrics[metric])
            
            # 恢复原始配置
            self.config = original_config.copy()
        
        # 绘制策略比较图表
        self._plot_strategy_comparison(comparison)
        
        return comparison
    
    def _plot_strategy_comparison(self, comparison):
        """
        绘制策略比较图表
        
        参数:
            comparison: 比较结果
        """
        output_dir = self.config["visualization"]["output_dir"]
        
        # 转换为DataFrame以便绘图
        df = pd.DataFrame({
            "策略": comparison["strategy_names"],
            "用户满意度": comparison["user_satisfaction"],
            "运营商利润": comparison["operator_profit"],
            "电网友好度": comparison["grid_friendliness"],
            "综合奖励": comparison["total_reward"]
        })
        
        # 绘制雷达图比较不同策略
        plt.figure(figsize=(12, 10))
        
        # 准备雷达图数据
        metrics = ["用户满意度", "运营商利润", "电网友好度", "综合奖励"]
        num_metrics = len(metrics)
        
        # 计算每个指标的角度
        angles = np.linspace(0, 2*np.pi, num_metrics, endpoint=False).tolist()
        angles += angles[:1]  # 闭合雷达图
        
        # 创建子图
        ax = plt.subplot(111, polar=True)
        
        # 为每个策略绘制雷达图
        for i, strategy in enumerate(comparison["strategy_names"]):
            values = [comparison["user_satisfaction"][i], 
                     comparison["operator_profit"][i], 
                     comparison["grid_friendliness"][i], 
                     comparison["total_reward"][i]]
            values += values[:1]  # 闭合雷达图
            
            ax.plot(angles, values, linewidth=2, label=strategy)
            ax.fill(angles, values, alpha=0.1)
        
        # 设置雷达图参数
        ax.set_theta_offset(np.pi / 2)  # 从顶部开始
        ax.set_theta_direction(-1)  # 顺时针方向
        
        # 设置刻度标签
        plt.xticks(angles[:-1], metrics)
        
        # 添加图例
        plt.legend(loc='upper right', bbox_to_anchor=(0.1, 0.1))
        
        plt.title("不同调度策略性能比较", size=15, y=1.05)
        plt.tight_layout()
        plt.savefig(f"{output_dir}/strategy_comparison_radar.png")
        plt.close()
        
        # 绘制分组柱状图
        plt.figure(figsize=(14, 8))
        
        # 设置分组柱状图参数
        x = np.arange(len(metrics))
        width = 0.15  # 柱子宽度
        
        # 绘制每个策略的柱状图
        for i, strategy in enumerate(comparison["strategy_names"]):
            values = [comparison["user_satisfaction"][i], 
                     comparison["operator_profit"][i], 
                     comparison["grid_friendliness"][i], 
                     comparison["total_reward"][i]]
            
            plt.bar(x + i*width, values, width, label=strategy)
        
        # 设置图表参数
        plt.xlabel('评估指标')
        plt.ylabel('指标得分')
        plt.title('不同调度策略性能对比')
        plt.xticks(x + width * (len(comparison["strategy_names"])-1)/2, metrics)
        plt.legend()
        plt.grid(True, linestyle='--', alpha=0.7)
        
        plt.tight_layout()
        plt.savefig(f"{output_dir}/strategy_comparison_bar.png")
        plt.close()
    
    def analyze_user_behavior(self, num_days=7):
        """
        分析用户充电行为模式
        
        参数:
            num_days: 分析的天数
        
        返回:
            analysis: 用户行为分析结果
        """
        self.logger.info(f"开始分析用户充电行为模式 ({num_days}天)")
        
        # 运行模拟收集数据
        steps_per_day = 24 * 60 // self.env_config.get("time_step_minutes", 15)
        num_steps = num_days * steps_per_day
        
        # 追踪用户充电行为
        user_charges = {}  # 用户充电记录
        hourly_demand = np.zeros(24)  # 每小时充电需求
        
        # 重置环境
        self.env = ChargingEnvironment(self.env_config)
        state = self.env.get_current_state()
        
        for step in tqdm(range(num_steps)):
            # 获取当前状态
            current_time = datetime.fromisoformat(state["timestamp"])
            current_hour = current_time.hour
            
            # 做出调度决策
            decisions = self.scheduler.make_scheduling_decision(state)
            
            # 记录用户充电行为
            for user_id, charger_id in decisions.items():
                # 查找用户和充电桩信息
                user_info = None
                for user in state["users"]:
                    if user["user_id"] == user_id:
                        user_info = user
                        break
                
                if user_info:
                    # 记录用户充电会话
                    if user_id not in user_charges:
                        user_charges[user_id] = []
                    
                    user_charges[user_id].append({
                        "timestamp": state["timestamp"],
                        "hour": current_hour,
                        "soc": user_info["soc"],
                        "charger_id": charger_id,
                        "user_type": user_info.get("user_type", "未知"),
                        "profile": user_info.get("profile", "未知")
                    })
                    
                    # 更新每小时充电需求
                    hourly_demand[current_hour] += 1
            
            # 执行决策并获取下一个状态
            _, state, _ = self.env.step(decisions)
        
        # 分析用户行为
        analysis = {
            "hourly_demand": hourly_demand.tolist(),
            "user_type_distribution": {},
            "profile_distribution": {},
            "avg_soc_at_charge": {},
            "charging_frequency": {}
        }
        
        # 统计不同用户类型和画像的分布
        for user_id, charges in user_charges.items():
            if not charges:
                continue
                
            user_type = charges[0]["user_type"]
            profile = charges[0]["profile"]
            
            # 用户类型分布
            if user_type not in analysis["user_type_distribution"]:
                analysis["user_type_distribution"][user_type] = 0
            analysis["user_type_distribution"][user_type] += 1
            
            # 用户画像分布
            if profile not in analysis["profile_distribution"]:
                analysis["profile_distribution"][profile] = 0
            analysis["profile_distribution"][profile] += 1
            
            # 计算平均充电时SOC
            avg_soc = sum(charge["soc"] for charge in charges) / len(charges)
            
            if user_type not in analysis["avg_soc_at_charge"]:
                analysis["avg_soc_at_charge"][user_type] = []
            analysis["avg_soc_at_charge"][user_type].append(avg_soc)
            
            # 统计充电频率
            if user_type not in analysis["charging_frequency"]:
                analysis["charging_frequency"][user_type] = []
            analysis["charging_frequency"][user_type].append(len(charges))
        
        # 计算每种用户类型的平均充电SOC和频率
        for user_type in analysis["avg_soc_at_charge"]:
            analysis["avg_soc_at_charge"][user_type] = np.mean(analysis["avg_soc_at_charge"][user_type])
            analysis["charging_frequency"][user_type] = np.mean(analysis["charging_frequency"][user_type])
        
        # 可视化分析结果
        self._visualize_user_behavior(analysis)
        
        return analysis
    
    def _visualize_user_behavior(self, analysis):

        output_dir = self.config["visualization"]["output_dir"]
        
        # 绘制每小时充电需求
        plt.figure(figsize=(12, 6))
        plt.bar(range(24), analysis["hourly_demand"])
        plt.xlabel("小时")
        plt.ylabel("充电需求")
        plt.title("24小时充电需求分布")
        plt.xticks(range(24))
        plt.grid(axis='y', linestyle='--', alpha=0.7)
        plt.savefig(f"{output_dir}/hourly_charging_demand.png")
        plt.close()
        
        # 绘制用户类型分布
        plt.figure(figsize=(10, 6))
        user_types = list(analysis["user_type_distribution"].keys())
        user_type_counts = list(analysis["user_type_distribution"].values())
        
        plt.pie(user_type_counts, labels=user_types, autopct='%1.1f%%', startangle=90)
        plt.axis('equal')
        plt.title("用户类型分布")
        plt.savefig(f"{output_dir}/user_type_distribution.png")
        plt.close()
        
        # 绘制用户画像分布
        plt.figure(figsize=(10, 6))
        profiles = list(analysis["profile_distribution"].keys())
        profile_counts = list(analysis["profile_distribution"].values())
        
        plt.pie(profile_counts, labels=profiles, autopct='%1.1f%%', startangle=90)
        plt.axis('equal')
        plt.title("用户画像分布")
        plt.savefig(f"{output_dir}/profile_distribution.png")
        plt.close()
        
        # 绘制平均充电SOC
        plt.figure(figsize=(10, 6))
        user_types = list(analysis["avg_soc_at_charge"].keys())
        avg_socs = list(analysis["avg_soc_at_charge"].values())
        
        plt.bar(user_types, avg_socs)
        plt.xlabel("用户类型")
        plt.ylabel("平均充电SOC (%)")
        plt.title("不同用户类型的平均充电电量")
        plt.grid(axis='y', linestyle='--', alpha=0.7)
        plt.savefig(f"{output_dir}/avg_soc_at_charge.png")
        plt.close()
        
        # 绘制充电频率
        plt.figure(figsize=(10, 6))
        user_types = list(analysis["charging_frequency"].keys())
        frequencies = list(analysis["charging_frequency"].values())
        
        plt.bar(user_types, frequencies)
        plt.xlabel("用户类型")
        plt.ylabel("平均充电频率 (次/周)")
        plt.title("不同用户类型的充电频率")
        plt.grid(axis='y', linestyle='--', alpha=0.7)
        plt.savefig(f"{output_dir}/charging_frequency.png")
        plt.close()
    
    def analyze_grid_impact(self, num_days=7):

        self.logger.info(f"开始分析充电调度策略对电网的影响 ({num_days}天)")
        
        # 运行带调度的模拟
        steps_per_day = 24 * 60 // self.env_config.get("time_step_minutes", 15)
        num_steps = num_days * steps_per_day
        
        # 准备数据结构
        hourly_load_with_scheduling = np.zeros(24)
        peak_loads_with_scheduling = []
        load_variance_with_scheduling = []
        renewable_utilization_with_scheduling = []
        
        # 重置环境
        self.env = ChargingEnvironment(self.env_config)
        state = self.env.get_current_state()
        
        for step in tqdm(range(num_steps)):
            # 获取当前状态
            current_time = datetime.fromisoformat(state["timestamp"])
            current_hour = current_time.hour
            
            # 记录当前电网负载
            grid_load = state["grid_status"]["current_load"]
            hourly_load_with_scheduling[current_hour] += grid_load
            
            # 记录峰值负载
            if current_hour in [7, 8, 9, 10, 18, 19, 20, 21]:  # 高峰时段
                peak_loads_with_scheduling.append(grid_load)
            
            # 记录负载方差（用于评估负载均衡性）
            all_loads = [hourly_load_with_scheduling[h] for h in range(24) if hourly_load_with_scheduling[h] > 0]
            if all_loads:
                load_variance_with_scheduling.append(np.var(all_loads))
            
            # 记录可再生能源利用率
            renewable_ratio = state["grid_status"]["renewable_ratio"]
            if 8 <= current_hour <= 16:  # 光伏发电高峰期
                renewable_utilization_with_scheduling.append(renewable_ratio)
            
            # 做出调度决策
            decisions = self.scheduler.make_scheduling_decision(state)
            
            # 执行决策并获取下一个状态
            _, state, _ = self.env.step(decisions)
        
        # 运行不带调度的基准模拟（随机分配充电桩）
        hourly_load_without_scheduling = np.zeros(24)
        peak_loads_without_scheduling = []
        load_variance_without_scheduling = []
        renewable_utilization_without_scheduling = []
        
        # 定义随机调度函数
        def random_scheduling(state):
            decisions = {}
            for user in state["users"]:
                if user["soc"] < 80:  # 只为SOC较低的用户做调度
                    if state["chargers"]:
                        charger = np.random.choice(state["chargers"])
                        decisions[user["user_id"]] = charger["charger_id"]
            return decisions
        
        # 重置环境
        self.env = ChargingEnvironment(self.env_config)
        state = self.env.get_current_state()
        
        for step in tqdm(range(num_steps)):
            # 获取当前状态
            current_time = datetime.fromisoformat(state["timestamp"])
            current_hour = current_time.hour
            
            # 记录当前电网负载
            grid_load = state["grid_status"]["current_load"]
            hourly_load_without_scheduling[current_hour] += grid_load
            
            # 记录峰值负载
            if current_hour in [7, 8, 9, 10, 18, 19, 20, 21]:  # 高峰时段
                peak_loads_without_scheduling.append(grid_load)
            
            # 记录负载方差
            all_loads = [hourly_load_without_scheduling[h] for h in range(24) if hourly_load_without_scheduling[h] > 0]
            if all_loads:
                load_variance_without_scheduling.append(np.var(all_loads))
            
            # 记录可再生能源利用率
            renewable_ratio = state["grid_status"]["renewable_ratio"]
            if 8 <= current_hour <= 16:  # 光伏发电高峰期
                renewable_utilization_without_scheduling.append(renewable_ratio)
            
            # 随机调度
            decisions = random_scheduling(state)
            
            # 执行决策并获取下一个状态
            _, state, _ = self.env.step(decisions)
        
        # 分析结果
        analysis = {
            "hourly_load": {
                "with_scheduling": (hourly_load_with_scheduling / num_days).tolist(),
                "without_scheduling": (hourly_load_without_scheduling / num_days).tolist()
            },
            "peak_load": {
                "with_scheduling": np.mean(peak_loads_with_scheduling) if peak_loads_with_scheduling else 0,
                "without_scheduling": np.mean(peak_loads_without_scheduling) if peak_loads_without_scheduling else 0,
                "reduction_percentage": 0  # 计算下面填充
            },
            "load_variance": {
                "with_scheduling": np.mean(load_variance_with_scheduling) if load_variance_with_scheduling else 0,
                "without_scheduling": np.mean(load_variance_without_scheduling) if load_variance_without_scheduling else 0,
                "improvement_percentage": 0  # 计算下面填充
            },
            "renewable_utilization": {
                "with_scheduling": np.mean(renewable_utilization_with_scheduling) if renewable_utilization_with_scheduling else 0,
                "without_scheduling": np.mean(renewable_utilization_without_scheduling) if renewable_utilization_without_scheduling else 0,
                "improvement_percentage": 0  # 计算下面填充
            }
        }
        
        # 计算改进百分比
        if analysis["peak_load"]["without_scheduling"] > 0:
            analysis["peak_load"]["reduction_percentage"] = (
                (analysis["peak_load"]["without_scheduling"] - analysis["peak_load"]["with_scheduling"]) /
                analysis["peak_load"]["without_scheduling"] * 100
            )
        
        if analysis["load_variance"]["without_scheduling"] > 0:
            analysis["load_variance"]["improvement_percentage"] = (
                (analysis["load_variance"]["without_scheduling"] - analysis["load_variance"]["with_scheduling"]) /
                analysis["load_variance"]["without_scheduling"] * 100
            )
        
        if analysis["renewable_utilization"]["without_scheduling"] > 0:
            analysis["renewable_utilization"]["improvement_percentage"] = (
                (analysis["renewable_utilization"]["with_scheduling"] - analysis["renewable_utilization"]["without_scheduling"]) /
                analysis["renewable_utilization"]["without_scheduling"] * 100
            )
        
        # 可视化分析结果
        self._visualize_grid_impact(analysis)
        
        return analysis
    
    def _visualize_grid_impact(self, analysis):
        """
        可视化电网影响分析结果
        
        参数:
            analysis: 电网影响分析结果
        """
        output_dir = self.config["visualization"]["output_dir"]
        
        # 绘制每小时负载对比图
        plt.figure(figsize=(12, 6))
        hours = range(24)
        
        plt.plot(hours, analysis["hourly_load"]["with_scheduling"], 'b-', linewidth=2, label="有序调度")
        plt.plot(hours, analysis["hourly_load"]["without_scheduling"], 'r--', linewidth=2, label="无序充电")
        
        plt.xlabel("小时")
        plt.ylabel("平均电网负载 (%)")
        plt.title("有序调度vs无序充电的24小时电网负载对比")
        plt.xticks(hours)
        plt.grid(True, linestyle='--', alpha=0.7)
        plt.legend()
        
        # 标记峰谷时段
        plt.fill_between([7, 11], 0, 100, alpha=0.2, color='orange', label="早高峰")
        plt.fill_between([18, 22], 0, 100, alpha=0.2, color='orange', label="晚高峰")
        plt.fill_between([0, 6], 0, 100, alpha=0.2, color='blue', label="低谷时段")
        
        plt.ylim(0, 100)
        plt.savefig(f"{output_dir}/hourly_load_comparison.png")
        plt.close()
        
        # 绘制峰值负载和负载方差对比图
        plt.figure(figsize=(14, 6))
        
        plt.subplot(1, 2, 1)
        labels = ["有序调度", "无序充电"]
        peak_loads = [analysis["peak_load"]["with_scheduling"], analysis["peak_load"]["without_scheduling"]]
        
        bars = plt.bar(labels, peak_loads, color=['green', 'red'])
        plt.xlabel("调度策略")
        plt.ylabel("峰值负载 (%)")
        plt.title(f"峰值负载对比\n减少了 {analysis['peak_load']['reduction_percentage']:.2f}%")
        plt.grid(axis='y', linestyle='--', alpha=0.7)
        
        # 添加数据标签
        for bar in bars:
            height = bar.get_height()
            plt.text(bar.get_x() + bar.get_width()/2., height + 1,
                    f'{height:.1f}%', ha='center', va='bottom')
        
        plt.subplot(1, 2, 2)
        variances = [analysis["load_variance"]["with_scheduling"], analysis["load_variance"]["without_scheduling"]]
        
        bars = plt.bar(labels, variances, color=['green', 'red'])
        plt.xlabel("调度策略")
        plt.ylabel("负载方差")
        plt.title(f"负载均衡性对比\n改善了 {analysis['load_variance']['improvement_percentage']:.2f}%")
        plt.grid(axis='y', linestyle='--', alpha=0.7)
        
        # 添加数据标签
        for bar in bars:
            height = bar.get_height()
            plt.text(bar.get_x() + bar.get_width()/2., height + 1,
                    f'{height:.1f}', ha='center', va='bottom')
        
        plt.tight_layout()
        plt.savefig(f"{output_dir}/peak_load_variance_comparison.png")
        plt.close()
        
        # 绘制可再生能源利用率对比图
        plt.figure(figsize=(10, 6))
        
        labels = ["有序调度", "无序充电"]
        utilization = [analysis["renewable_utilization"]["with_scheduling"], 
                      analysis["renewable_utilization"]["without_scheduling"]]
        
        bars = plt.bar(labels, utilization, color=['green', 'red'])
        plt.xlabel("调度策略")
        plt.ylabel("可再生能源利用率 (%)")
        plt.title(f"可再生能源利用率对比\n提高了 {analysis['renewable_utilization']['improvement_percentage']:.2f}%")
        plt.grid(axis='y', linestyle='--', alpha=0.7)
        
        # 添加数据标签
        for bar in bars:
            height = bar.get_height()
            plt.text(bar.get_x() + bar.get_width()/2., height + 1,
                    f'{height:.1f}%', ha='center', va='bottom')
        
        plt.savefig(f"{output_dir}/renewable_utilization_comparison.png")
        plt.close()



def main():
    """主函数，运行完整系统分析"""
    # 创建集成系统
    system = IntegratedChargingSystem()
    
    # 1. 运行调度模拟
    print("1. 运行充电调度模拟...")
    system.run_simulation(days=7)
    
    # 2. 进行敏感性分析
    print("\n2. 进行敏感性分析...")
    parameter_ranges = {
        "scheduler.optimization_weights.user_satisfaction": [0.2, 0.3, 0.4, 0.5, 0.6],
        "scheduler.optimization_weights.operator_profit": [0.2, 0.3, 0.4],
        "scheduler.optimization_weights.grid_friendliness": [0.2, 0.3, 0.4]
    }
    system.run_sensitivity_analysis(parameter_ranges)
    
    # 3. 比较不同调度策略
    print("\n3. 比较不同调度策略...")
    strategies = [
        {
            "name": "用户优先策略",
            "params": {
                "scheduler.optimization_weights.user_satisfaction": 0.6,
                "scheduler.optimization_weights.operator_profit": 0.2,
                "scheduler.optimization_weights.grid_friendliness": 0.2
            },
            "use_model": True
        },
        {
            "name": "利润优先策略",
            "params": {
                "scheduler.optimization_weights.user_satisfaction": 0.2,
                "scheduler.optimization_weights.operator_profit": 0.6,
                "scheduler.optimization_weights.grid_friendliness": 0.2
            },
            "use_model": True
        },
        {
            "name": "电网友好策略",
            "params": {
                "scheduler.optimization_weights.user_satisfaction": 0.2,
                "scheduler.optimization_weights.operator_profit": 0.2,
                "scheduler.optimization_weights.grid_friendliness": 0.6
            },
            "use_model": True
        },
        {
            "name": "平衡策略",
            "params": {
                "scheduler.optimization_weights.user_satisfaction": 0.33,
                "scheduler.optimization_weights.operator_profit": 0.33,
                "scheduler.optimization_weights.grid_friendliness": 0.34
            },
            "use_model": True
        },
        {
            "name": "启发式调度",
            "params": {},
            "use_model": False
        }
    ]
    system.compare_scheduling_strategies(strategies)
    
    # 4. 分析用户行为
    print("\n4. 分析用户充电行为...")
    system.analyze_user_behavior()
    
    # 5. 分析电网影响
    print("\n5. 分析充电调度对电网的影响...")
    system.analyze_grid_impact()

    return system


if __name__ == "__main__":
    main()