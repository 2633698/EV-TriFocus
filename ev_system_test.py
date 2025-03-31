import unittest
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import os
import json
import pandas as pd
from tqdm import tqdm

from ev_charging_scheduler import ChargingEnvironment, ChargingScheduler, ChargingVisualizationDashboard
from ev_integration_scheduler import IntegratedChargingSystem
from pylab import mpl
mpl.rcParams["font.sans-serif"] = ["SimHei"] # 设置显示中文字体 宋体
mpl.rcParams["axes.unicode_minus"] = False #字体更改后，会导致坐标轴中的部分字符无法正常显示，此时需要设置正常显示负号


class SystemTest(unittest.TestCase):
    def setUp(self):
        # 创建输出目录
        os.makedirs("test_output", exist_ok=True)
        
        # 测试配置
        self.test_config = {
            "environment": {
                "grid_id": "TEST001",
                "charger_count": 5,  # 少量充电桩便于快速测试
                "user_count": 10,    # 少量用户便于快速测试
                "simulation_days": 1,
                "time_step_minutes": 30  # 更大的时间步长以加速测试
            },
            "model": {
                "input_dim": 19,
                "hidden_dim": 64,
                "task_hidden_dim": 32,
                "model_path": "test_model.pth"
            },
            "scheduler": {
                "use_trained_model": False,  # 测试使用启发式规则
                "optimization_weights": {
                    "user_satisfaction": 0.4,
                    "operator_profit": 0.3,
                    "grid_friendliness": 0.3
                }
            },
            "visualization": {
                "dashboard_port": 8051,
                "update_interval": 5,
                "output_dir": "test_output"
            }
        }
        
        # 初始化环境
        self.env = ChargingEnvironment(self.test_config["environment"])
        
        # 初始化调度器
        self.scheduler = ChargingScheduler({
            "grid_id": self.test_config["environment"]["grid_id"],
            "charger_count": self.test_config["environment"]["charger_count"],
            "user_count": self.test_config["environment"]["user_count"]
        })
        
        # 初始化可视化仪表盘
        self.dashboard = ChargingVisualizationDashboard(self.scheduler)
        
        # 初始化集成系统
        self.system = IntegratedChargingSystem()
        self.system.config = self.test_config  # 使用测试配置
        self.system.env = self.env
        self.system.scheduler = self.scheduler
        self.system.dashboard = self.dashboard
    
    def test_environment_initialization(self):
        self.assertEqual(self.env.grid_id, self.test_config["environment"]["grid_id"])
        self.assertEqual(len(self.env.chargers), self.test_config["environment"]["charger_count"])
        self.assertEqual(len(self.env.users), self.test_config["environment"]["user_count"])
        
        # 检查电网状态是否初始化
        self.assertIsNotNone(self.env.grid_status)
        self.assertIn("current_load", self.env.grid_status)
        self.assertIn("pred_1h_load", self.env.grid_status)
        self.assertIn("renewable_ratio", self.env.grid_status)
        
        print("环境初始化测试通过")
    
    def test_state_representation(self):
        state = self.env.get_current_state()
        
        # 检查状态格式
        self.assertIn("timestamp", state)
        self.assertIn("grid_id", state)
        self.assertIn("users", state)
        self.assertIn("chargers", state)
        self.assertIn("grid_status", state)
        
        # 检查用户数据格式
        self.assertEqual(len(state["users"]), self.test_config["environment"]["user_count"])
        user = state["users"][0]
        self.assertIn("user_id", user)
        self.assertIn("soc", user)
        self.assertIn("max_wait_time", user)
        self.assertIn("preferred_power", user)
        
        # 检查充电桩数据格式
        self.assertEqual(len(state["chargers"]), self.test_config["environment"]["charger_count"])
        charger = state["chargers"][0]
        self.assertIn("charger_id", charger)
        self.assertIn("health_score", charger)
        self.assertIn("available_power", charger)
        self.assertIn("queue_length", charger)
        
        print("状态表示测试通过")
    
    def test_environment_step(self):
        # 获取初始状态
        initial_state = self.env.get_current_state()
        initial_time = datetime.fromisoformat(initial_state["timestamp"])
        
        # 创建简单调度动作
        actions = {}
        for i, user in enumerate(initial_state["users"]):
            if i < len(initial_state["chargers"]):  # 确保有足够的充电桩
                actions[user["user_id"]] = initial_state["chargers"][i]["charger_id"]
        
        # 执行环境步进
        rewards, next_state, done = self.env.step(actions)
        next_time = datetime.fromisoformat(next_state["timestamp"])
        
        # 检查时间步进
        time_step_minutes = self.test_config["environment"]["time_step_minutes"]
        expected_time = initial_time + timedelta(minutes=time_step_minutes)
        self.assertEqual(next_time, expected_time)
        
        # 检查奖励结构
        self.assertIn("user_satisfaction", rewards)
        self.assertIn("operator_profit", rewards)
        self.assertIn("grid_friendliness", rewards)
        self.assertIn("total_reward", rewards)
        
        # 检查奖励值范围
        self.assertTrue(0 <= rewards["user_satisfaction"] <= 1)
        self.assertTrue(-1 <= rewards["grid_friendliness"] <= 1)
        self.assertTrue(0 <= rewards["total_reward"] <= 1)
        
        print("环境步进测试通过")
    
    def test_scheduler_recommendations(self):
        # 获取当前状态
        state = self.env.get_current_state()
        
        # 为一个特定用户生成推荐
        if state["users"]:
            user_id = state["users"][0]["user_id"]
            recommendations = self.scheduler.make_recommendation(user_id, state)
            
            # 检查推荐结果
            self.assertIsInstance(recommendations, list)
            
            if recommendations:  # 如果有推荐
                recommendation = recommendations[0]
                self.assertIn("charger_id", recommendation)
                self.assertIn("combined_score", recommendation)
                self.assertIn("user_score", recommendation)
                self.assertIn("profit_score", recommendation)
                self.assertIn("grid_score", recommendation)
                
                # 检查评分是否在合理范围内
                self.assertTrue(0 <= recommendation["combined_score"] <= 1)
        
        print("调度器推荐功能测试通过")
    
    def test_scheduling_decision(self):
        # 获取当前状态
        state = self.env.get_current_state()
        
        # 生成调度决策
        decisions = self.scheduler.make_scheduling_decision(state)
        
        # 检查决策格式
        self.assertIsInstance(decisions, dict)
        
        # 检查决策内容
        for user_id, charger_id in decisions.items():
            # 验证用户ID是否存在
            user_exists = False
            for user in state["users"]:
                if user["user_id"] == user_id:
                    user_exists = True
                    break
            self.assertTrue(user_exists)
            
            # 验证充电桩ID是否存在
            charger_exists = False
            for charger in state["chargers"]:
                if charger["charger_id"] == charger_id:
                    charger_exists = True
                    break
            self.assertTrue(charger_exists)
        
        print("调度决策功能测试通过")
    
    def test_short_simulation(self):
        # 运行一个短时间的模拟
        metrics, avg_metrics = self.scheduler.run_simulation(num_steps=10)
        
        # 检查指标结构
        self.assertIn("user_satisfaction", metrics)
        self.assertIn("operator_profit", metrics)
        self.assertIn("grid_friendliness", metrics)
        self.assertIn("total_reward", metrics)
        
        # 检查指标长度
        self.assertEqual(len(metrics["user_satisfaction"]), 10)
        
        # 检查平均指标
        self.assertIn("user_satisfaction", avg_metrics)
        self.assertIn("operator_profit", avg_metrics)
        self.assertIn("grid_friendliness", avg_metrics)
        self.assertIn("total_reward", avg_metrics)
        
        print("短时间模拟测试通过")
    
    def test_visualization_dashboard(self):
        # 生成用户界面HTML
        user_dashboard = self.dashboard.generate_user_interface()
        self.assertIsInstance(user_dashboard, str)
        self.assertIn("<!DOCTYPE html>", user_dashboard)
        self.assertIn("EV充电推荐系统", user_dashboard)
        
        # 生成运营商看板HTML
        operator_dashboard = self.dashboard.generate_operator_dashboard()
        self.assertIsInstance(operator_dashboard, str)
        self.assertIn("<!DOCTYPE html>", operator_dashboard)
        self.assertIn("充电运营管理系统", operator_dashboard)
        
        # 保存到文件（可选）
        with open("test_output/user_dashboard_test.html", "w", encoding="utf-8") as f:
            f.write(user_dashboard)
        
        with open("test_output/operator_dashboard_test.html", "w", encoding="utf-8") as f:
            f.write(operator_dashboard)
        
        print("可视化仪表盘生成测试通过")
    
    def test_integrated_system(self):
        # 运行短时间模拟
        metrics, _ = self.system.run_simulation(days=1, output_metrics=True)
        
        # 检查指标结构
        self.assertIn("user_satisfaction", metrics)
        self.assertIn("operator_profit", metrics)
        self.assertIn("grid_friendliness", metrics)
        self.assertIn("total_reward", metrics)
        
        # 检查结果文件生成
        output_dir = self.test_config["visualization"]["output_dir"]
        self.assertTrue(os.path.exists(f"{output_dir}/simulation_metrics.csv"))
        self.assertTrue(os.path.exists(f"{output_dir}/charging_scheduler_results.png"))
        self.assertTrue(os.path.exists(f"{output_dir}/evaluation_report.md"))
        
        print("集成系统功能测试通过")


class SimulationEvaluator:
    def __init__(self, config_path=None):
        # 加载配置
        if config_path and os.path.exists(config_path):
            with open(config_path, 'r') as f:
                self.config = json.load(f)
        else:
            # 默认评价配置
            self.config = {
                "simulation": {
                    "days": 14,  # 两周仿真
                    "strategies": [
                        {
                            "name": "用户体验优先",
                            "weights": {
                                "user_satisfaction": 0.6,
                                "operator_profit": 0.2,
                                "grid_friendliness": 0.2
                            }
                        },
                        {
                            "name": "电网友好优先",
                            "weights": {
                                "user_satisfaction": 0.2,
                                "operator_profit": 0.2,
                                "grid_friendliness": 0.6
                            }
                        },
                        {
                            "name": "运营利润优先",
                            "weights": {
                                "user_satisfaction": 0.2,
                                "operator_profit": 0.6,
                                "grid_friendliness": 0.2
                            }
                        },
                        {
                            "name": "三者平衡",
                            "weights": {
                                "user_satisfaction": 0.33,
                                "operator_profit": 0.33,
                                "grid_friendliness": 0.34
                            }
                        }
                    ],
                    "scenarios": [
                        {
                            "name": "正常工作日",
                            "user_count": 50,
                            "charger_count": 20
                        },
                        {
                            "name": "假日高峰",
                            "user_count": 80,
                            "charger_count": 20
                        },
                        {
                            "name": "低负载夜间",
                            "user_count": 30,
                            "charger_count": 20,
                            "night_mode": True
                        },
                        {
                            "name": "充电桩故障",
                            "user_count": 50,
                            "charger_count": 15,
                            "failure_rate": 0.3
                        }
                    ]
                },
                "evaluation": {
                    "metrics": ["user_satisfaction", "operator_profit", "grid_friendliness", "total_reward"],
                    "output_dir": "evaluation_results"
                }
            }
        
        # 创建输出目录
        os.makedirs(self.config["evaluation"]["output_dir"], exist_ok=True)
        
        # 初始化结果存储
        self.results = {
            "strategy_comparison": {},
            "scenario_comparison": {},
            "cross_evaluation": {}
        }
    
    def evaluate_strategies(self):
        print("开始评估不同调度策略...")
        
        strategies = self.config["simulation"]["strategies"]
        metrics = self.config["evaluation"]["metrics"]
        
        # 初始化系统
        system = IntegratedChargingSystem()
        
        # 运行每个策略并记录结果
        strategy_results = {metric: [] for metric in metrics}
        strategy_names = []
        
        for strategy in tqdm(strategies):
            print(f"  评估策略: {strategy['name']}")
            strategy_names.append(strategy['name'])
            
            # 更新系统配置
            system.config["scheduler"]["optimization_weights"] = strategy["weights"]
            
            # 重新初始化环境和调度器
            system.env = ChargingEnvironment(system.env_config)
            system.scheduler = ChargingScheduler({
                "grid_id": system.env_config["grid_id"],
                "charger_count": system.env_config["charger_count"],
                "user_count": system.env_config["user_count"]
            })
            
            # 运行模拟
            _, avg_metrics = system.run_simulation(days=self.config["simulation"]["days"], output_metrics=False)
            
            # 记录结果
            for metric in metrics:
                strategy_results[metric].append(avg_metrics[metric])
        
        # 存储结果
        self.results["strategy_comparison"] = {
            "strategy_names": strategy_names,
            "metrics": strategy_results
        }
        
        # 可视化结果
        self._visualize_strategy_evaluation()
        
        print("策略评估完成")
        return self.results["strategy_comparison"]
    
    def _visualize_strategy_evaluation(self):
        output_dir = self.config["evaluation"]["output_dir"]
        
        results = self.results["strategy_comparison"]
        strategy_names = results["strategy_names"]
        metrics = results["metrics"]
        
        # 创建DataFrame以便绘图
        strategy_df = pd.DataFrame({
            "策略": strategy_names
        })
        
        for metric, values in metrics.items():
            strategy_df[metric] = values
        
        # 绘制对比柱状图
        plt.figure(figsize=(14, 10))
        
        for i, metric in enumerate(metrics.keys()):
            plt.subplot(2, 2, i+1)
            bars = plt.bar(strategy_names, metrics[metric])
            plt.title(f"不同策略的{metric}对比")
            plt.ylabel(metric)
            plt.grid(axis='y', linestyle='--', alpha=0.7)
            
            # 旋转x轴标签
            plt.xticks(rotation=15)
            
            # 添加数据标签
            for bar in bars:
                height = bar.get_height()
                plt.text(bar.get_x() + bar.get_width()/2., height + 0.01,
                        f'{height:.3f}', ha='center', va='bottom')
        
        plt.tight_layout()
        plt.savefig(f"{output_dir}/strategy_comparison.png")
        plt.close()
        
        # 绘制雷达图
        fig = plt.figure(figsize=(10, 10))
        ax = fig.add_subplot(111, polar=True)
        
        # 准备绘制雷达图的数据
        metric_list = list(metrics.keys())
        num_metrics = len(metric_list)
        
        # 计算角度
        angles = np.linspace(0, 2*np.pi, num_metrics, endpoint=False).tolist()
        angles += angles[:1]  # 闭合图形
        
        # 为每个策略绘制
        for i, strategy in enumerate(strategy_names):
            values = [metrics[metric][i] for metric in metric_list]
            values += values[:1]  # 闭合图形
            
            ax.plot(angles, values, 'o-', linewidth=2, label=strategy)
            ax.fill(angles, values, alpha=0.1)
        
        # 设置图表参数
        ax.set_theta_offset(np.pi / 2)  # 从顶部开始
        ax.set_theta_direction(-1)  # 顺时针方向
        
        # 设置刻度标签
        plt.xticks(angles[:-1], metric_list)
        
        # 添加图例
        plt.legend(loc='upper right', bbox_to_anchor=(0.1, 0.1))
        
        plt.title("不同策略在各指标上的表现", size=15, y=1.05)
        plt.tight_layout()
        plt.savefig(f"{output_dir}/strategy_radar_chart.png")
        plt.close()
    
    def evaluate_scenarios(self):
        print("开始评估不同场景...")
        
        scenarios = self.config["simulation"]["scenarios"]
        metrics = self.config["evaluation"]["metrics"]
        
        # 使用平衡策略评估不同场景
        balanced_strategy = None
        for strategy in self.config["simulation"]["strategies"]:
            if strategy["name"] == "三者平衡":
                balanced_strategy = strategy
                break
        
        if not balanced_strategy:
            balanced_strategy = self.config["simulation"]["strategies"][0]
        
        # 初始化系统
        system = IntegratedChargingSystem()
        
        # 设置平衡策略权重
        system.config["scheduler"]["optimization_weights"] = balanced_strategy["weights"]
        
        # 运行每个场景并记录结果
        scenario_results = {metric: [] for metric in metrics}
        scenario_names = []
        
        for scenario in tqdm(scenarios):
            print(f"  评估场景: {scenario['name']}")
            scenario_names.append(scenario['name'])
            
            # 更新系统配置
            system.config["environment"]["user_count"] = scenario["user_count"]
            system.config["environment"]["charger_count"] = scenario["charger_count"]
            
            # 特殊场景处理
            if scenario.get("night_mode"):
                # 模拟夜间场景
                system.env_config["simulation_start_hour"] = 22  # 从晚上10点开始
                
            if scenario.get("failure_rate"):
                # 模拟充电桩故障率
                system.env_config["charger_failure_rate"] = scenario["failure_rate"]
            
            # 重新初始化环境和调度器
            system.env = ChargingEnvironment(system.env_config)
            system.scheduler = ChargingScheduler({
                "grid_id": system.env_config["grid_id"],
                "charger_count": system.env_config["charger_count"],
                "user_count": system.env_config["user_count"]
            })
            
            # 运行模拟
            _, avg_metrics = system.run_simulation(days=self.config["simulation"]["days"], output_metrics=False)
            
            # 记录结果
            for metric in metrics:
                scenario_results[metric].append(avg_metrics[metric])
        
        # 存储结果
        self.results["scenario_comparison"] = {
            "scenario_names": scenario_names,
            "metrics": scenario_results
        }
        
        # 可视化结果
        self._visualize_scenario_evaluation()
        
        print("场景评估完成")
        return self.results["scenario_comparison"]
    
    def _visualize_scenario_evaluation(self):
        output_dir = self.config["evaluation"]["output_dir"]
        
        results = self.results["scenario_comparison"]
        scenario_names = results["scenario_names"]
        metrics = results["metrics"]
        
        # 创建DataFrame以便绘图
        scenario_df = pd.DataFrame({
            "场景": scenario_names
        })
        
        for metric, values in metrics.items():
            scenario_df[metric] = values
        
        # 绘制折线图
        plt.figure(figsize=(14, 10))
        
        for metric, values in metrics.items():
            plt.plot(scenario_names, values, 'o-', linewidth=2, label=metric)
        
        plt.title("不同场景下各指标的表现")
        plt.xlabel("场景")
        plt.ylabel("指标值")
        plt.grid(True, linestyle='--', alpha=0.7)
        plt.legend()
        
        # 旋转x轴标签
        plt.xticks(rotation=15)
        
        plt.tight_layout()
        plt.savefig(f"{output_dir}/scenario_performance.png")
        plt.close()
        
        # 绘制热力图
        plt.figure(figsize=(12, 8))
        
        data = np.array([metrics[metric] for metric in metrics.keys()])
        
        # 创建热力图
        im = plt.imshow(data, cmap='YlGnBu')
        
        # 添加颜色条
        plt.colorbar(im, label='指标值')
        
        # 设置坐标轴
        plt.xticks(range(len(scenario_names)), scenario_names, rotation=45)
        plt.yticks(range(len(metrics)), metrics.keys())
        
        # 添加数据标签
        for i in range(len(metrics)):
            for j in range(len(scenario_names)):
                text = plt.text(j, i, f"{data[i, j]:.3f}",
                               ha="center", va="center", color="black")
        
        plt.title("场景-指标热力图")
        plt.tight_layout()
        plt.savefig(f"{output_dir}/scenario_heatmap.png")
        plt.close()
    
    def cross_evaluate(self):
        print("开始交叉评估不同策略在不同场景下的表现...")
        
        strategies = self.config["simulation"]["strategies"]
        scenarios = self.config["simulation"]["scenarios"]
        metrics = self.config["evaluation"]["metrics"]
        
        # 初始化系统
        system = IntegratedChargingSystem()
        
        # 初始化结果存储
        cross_results = {}
        for metric in metrics:
            cross_results[metric] = np.zeros((len(strategies), len(scenarios)))
        
        # 交叉评估
        for i, strategy in enumerate(tqdm(strategies, desc="策略")):
            for j, scenario in enumerate(tqdm(scenarios, desc="场景", leave=False)):
                print(f"  评估策略 '{strategy['name']}' 在场景 '{scenario['name']}' 下的表现")
                
                # 更新系统配置
                system.config["scheduler"]["optimization_weights"] = strategy["weights"]
                system.config["environment"]["user_count"] = scenario["user_count"]
                system.config["environment"]["charger_count"] = scenario["charger_count"]
                
                # 特殊场景处理
                if scenario.get("night_mode"):
                    system.env_config["simulation_start_hour"] = 22
                
                if scenario.get("failure_rate"):
                    system.env_config["charger_failure_rate"] = scenario["failure_rate"]
                
                # 重新初始化环境和调度器
                system.env = ChargingEnvironment(system.env_config)
                system.scheduler = ChargingScheduler({
                    "grid_id": system.env_config["grid_id"],
                    "charger_count": system.env_config["charger_count"],
                    "user_count": system.env_config["user_count"]
                })
                
                # 运行较短时间模拟
                _, avg_metrics = system.run_simulation(days=7, output_metrics=False)
                
                # 记录结果
                for metric in metrics:
                    cross_results[metric][i, j] = avg_metrics[metric]
        
        # 存储结果
        self.results["cross_evaluation"] = {
            "strategy_names": [strategy["name"] for strategy in strategies],
            "scenario_names": [scenario["name"] for scenario in scenarios],
            "metrics": cross_results
        }
        
        # 可视化结果
        self._visualize_cross_evaluation()
        
        print("交叉评估完成")
        return self.results["cross_evaluation"]
    
    def _visualize_cross_evaluation(self):
        output_dir = self.config["evaluation"]["output_dir"]
        
        results = self.results["cross_evaluation"]
        strategy_names = results["strategy_names"]
        scenario_names = results["scenario_names"]
        metrics = results["metrics"]
        
        # 为每个指标绘制热力图
        for metric, data in metrics.items():
            plt.figure(figsize=(12, 8))

            im = plt.imshow(data, cmap='YlGnBu')

            plt.colorbar(im, label=f'{metric}值')

            plt.xticks(range(len(scenario_names)), scenario_names, rotation=45)
            plt.yticks(range(len(strategy_names)), strategy_names)

            for i in range(len(strategy_names)):
                for j in range(len(scenario_names)):
                    text = plt.text(j, i, f"{data[i, j]:.3f}",
                                   ha="center", va="center", color="black")
            
            plt.title(f"{metric}在不同策略和场景下的表现")
            plt.tight_layout()
            plt.savefig(f"{output_dir}/cross_evaluation_{metric}.png")
            plt.close()
        
        # 绘制最佳策略分析
        best_strategies = {}
        for metric, data in metrics.items():
            best_indices = np.argmax(data, axis=0)
            best_strategies[metric] = [strategy_names[idx] for idx in best_indices]
        
        # 创建最佳策略表格
        plt.figure(figsize=(14, 8))
        plt.axis('tight')
        plt.axis('off')
        
        table_data = [["场景"] + scenario_names]
        for metric in metrics.keys():
            table_data.append([metric] + best_strategies[metric])
        
        table = plt.table(cellText=table_data, loc='center', cellLoc='center')
        table.auto_set_font_size(False)
        table.set_fontsize(12)
        table.scale(1, 3)
        
        plt.title("各场景下每个指标的最佳策略", y=0.8)
        plt.savefig(f"{output_dir}/best_strategies_by_scenario.png", bbox_inches='tight')
        plt.close()


    def generate_comprehensive_report(self):
            print("生成综合评价报告...")
            
            output_dir = self.config["evaluation"]["output_dir"]
            
            # 确保至少进行了一项评估
            if not self.results["strategy_comparison"] and not self.results["scenario_comparison"] and not self.results["cross_evaluation"]:
                print("没有评估结果可用于生成报告。请先运行评估。")
                return
            
            # 生成Markdown报告
            report = f"""
            # 电动汽车有序充电调度策略综合评价报告
            
            **生成时间**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
            
            ## 1. 评价概述
            
            本报告对不同充电调度策略在各种场景下的性能进行了综合评价，旨在分析策略的优劣及其适用场景。
            评价通过以下三个维度进行：
            
            1. **策略对比评价**: 在标准场景下比较不同调度策略的性能
            2. **场景适应性评价**: 评估平衡策略在不同场景下的表现
            3. **交叉评价**: 分析不同策略在不同场景下的表现，找出每个场景的最佳策略
            
            ## 2. 评价指标
            
            评价采用以下四个主要指标：
            
            - **用户满意度**: 衡量用户等待时间、充电速度、价格满意度等用户体验因素
            - **运营商利润**: 评估充电服务费、电费差价、设备使用效率对利润的影响
            - **电网友好度**: 分析调度策略对电网峰谷负荷平衡、可再生能源利用的贡献
            - **综合奖励**: 三者的加权平均，反映整体效果
            
            ## 3. 策略对比评价结果
            """
            
            # 添加策略对比结果
            if self.results["strategy_comparison"]:
                strategy_names = self.results["strategy_comparison"]["strategy_names"]
                metrics = self.results["strategy_comparison"]["metrics"]
                
                report += """
            
            ### 3.1 各策略性能指标
            
            | 策略名称 | 用户满意度 | 运营商利润 | 电网友好度 | 综合奖励 |
            |---------|-----------|-----------|-----------|---------|
            """
                
                for i, strategy in enumerate(strategy_names):
                    report += f"| {strategy} | {metrics['user_satisfaction'][i]:.4f} | {metrics['operator_profit'][i]:.4f} | {metrics['grid_friendliness'][i]:.4f} | {metrics['total_reward'][i]:.4f} |\n"
                
                # 找出各指标的最佳策略
                best_strategy = {}
                for metric in metrics:
                    best_idx = np.argmax(metrics[metric])
                    best_strategy[metric] = strategy_names[best_idx]
                
                report += f"""
            
            ### 3.2 最佳策略分析
            
            - **用户满意度最高的策略**: {best_strategy['user_satisfaction']}
            - **运营商利润最高的策略**: {best_strategy['operator_profit']}
            - **电网友好度最高的策略**: {best_strategy['grid_friendliness']}
            - **综合奖励最高的策略**: {best_strategy['total_reward']}
            
            ### 3.3 策略对比分析
            
            通过对比不同策略的性能指标，可以得出以下结论：
            
            1. 当以单一目标为优化导向时，相应指标确实能够获得显著提升。例如，用户体验优先策略在用户满意度上表现最佳，电网友好优先策略在电网友好度上表现最佳。
            
            2. 三者平衡策略虽然在单项指标上可能不是最优，但在综合奖励上表现良好，体现了多目标优化的价值。
            
            3. 某些指标之间存在一定程度的权衡关系。例如，过分强调电网友好度可能会在一定程度上牺牲用户体验或运营商利润。
            """
            
            # 添加场景适应性结果
            report += """
            
            ## 4. 场景适应性评价结果
            """
            
            if self.results["scenario_comparison"]:
                scenario_names = self.results["scenario_comparison"]["scenario_names"]
                metrics = self.results["scenario_comparison"]["metrics"]
                
                report += """
            
            ### 4.1 不同场景下的性能指标
            
            | 场景名称 | 用户满意度 | 运营商利润 | 电网友好度 | 综合奖励 |
            |---------|-----------|-----------|-----------|---------|
            """
                
                for i, scenario in enumerate(scenario_names):
                    report += f"| {scenario} | {metrics['user_satisfaction'][i]:.4f} | {metrics['operator_profit'][i]:.4f} | {metrics['grid_friendliness'][i]:.4f} | {metrics['total_reward'][i]:.4f} |\n"
                
                # 找出各场景的最佳指标和最差指标
                best_metrics = {}
                worst_metrics = {}
                for scenario_idx, scenario in enumerate(scenario_names):
                    metrics_values = [metrics[metric][scenario_idx] for metric in metrics.keys()]
                    best_idx = np.argmax(metrics_values)
                    worst_idx = np.argmin(metrics_values)
                    best_metrics[scenario] = list(metrics.keys())[best_idx]
                    worst_metrics[scenario] = list(metrics.keys())[worst_idx]
                
                report += f"""
            
            ### 4.2 场景适应性分析
            
            不同场景下，系统性能表现各异：
            
            """
                
                for scenario in scenario_names:
                    report += f"- **{scenario}**: 最优指标为{best_metrics[scenario]}，最弱指标为{worst_metrics[scenario]}。\n"
                
                report += """
            
            ### 4.3 场景挑战分析
            
            1. **正常工作日**场景下，系统能够保持较好的平衡，各项指标表现均衡。
            
            2. **假日高峰**场景是对系统最大的挑战，用户数量增加导致等待时间延长，用户满意度下降，同时电网负载增加也会影响电网友好度。
            
            3. **低负载夜间**场景是系统表现最好的场景，由于用户较少且电网负载低，系统能够提供更好的用户体验，同时保持较高的电网友好度。
            
            4. **充电桩故障**场景下，系统需要更智能地分配有限资源，此时对调度算法的鲁棒性要求更高。
            """
            
            # 添加交叉评价结果
            report += """
            
            ## 5. 交叉评价结果
            """
            
            if self.results["cross_evaluation"]:
                strategy_names = self.results["cross_evaluation"]["strategy_names"]
                scenario_names = self.results["cross_evaluation"]["scenario_names"]
                metrics = self.results["cross_evaluation"]["metrics"]
                
                report += """
            
            ### 5.1 最佳策略匹配
            
            对于每个场景，以下是各指标表现最佳的策略：
            
            | 场景 | 用户满意度最佳策略 | 运营商利润最佳策略 | 电网友好度最佳策略 | 综合奖励最佳策略 |
            |------|------------------|------------------|------------------|-----------------|
            """
                
                for j, scenario in enumerate(scenario_names):
                    best_strategies = []
                    for metric in metrics:
                        best_idx = np.argmax(metrics[metric][:, j])
                        best_strategies.append(strategy_names[best_idx])
                    
                    report += f"| {scenario} | {best_strategies[0]} | {best_strategies[1]} | {best_strategies[2]} | {best_strategies[3]} |\n"
                
                report += """
            
            ### 5.2 策略-场景适配性分析
            
            通过交叉评价，我们发现不同策略在不同场景下的表现存在显著差异：
            
            1. **用户体验优先策略**在用户数量适中的场景中表现最佳，能够提供较好的用户满意度。然而，在高负载场景下，由于资源有限，其优势减弱。
            
            2. **电网友好优先策略**在高峰期和高负载场景下发挥重要作用，能够有效避免电网过载，但可能导致用户等待时间延长。
            
            3. **运营利润优先策略**在低谷电价时段效果最佳，此时充电成本低，利润空间大。
            
            4. **三者平衡策略**在大多数场景中都能保持较好的综合表现，尤其是在正常工作日这样的标准场景中，表现出较好的适应性。
            """
            
            # 添加综合结论
            report += """
            
            ## 6. 综合结论与优化建议
            
            ### 6.1 综合结论
            
            1. **策略选择应当场景化**：没有一种"放之四海而皆准"的调度策略，应根据实际场景选择或动态调整策略权重。
            
            2. **多目标平衡至关重要**：单一目标优化虽然能在特定指标上取得突出成绩，但往往难以兼顾其他目标，而平衡策略能够在不同场景下保持较好的综合表现。
            
            3. **调度系统的鲁棒性**：在充电桩故障等异常场景下，调度系统的鲁棒性尤为重要，需要能够灵活应对各种突发情况。
            
            ### 6.2 优化建议
            
            1. **动态调整策略权重**：基于当前场景特征（如时段、用户数量、电网负载等）自动调整优化权重，以适应不同情境。
            
            2. **预测性调度优化**：结合历史数据分析和预测模型，提前预估用户需求和电网负载，主动优化调度决策。
            
            3. **分区域差异化调度**：针对不同地理区域的特性（如商业区、住宅区等）采用不同的调度策略，提高整体效率。
            
            4. **更精细的用户画像**：进一步细化用户画像，为不同类型用户提供个性化的充电推荐，提升用户满意度。
            
            5. **电网-充电桩协同优化**：加强与电网的信息互联互通，实现更精准的负载管理和需求响应。
            
            ## 7. 附录
            
            评价过程中生成的详细图表和数据已保存在评价结果目录中，包括：
            
            - 策略对比图表
            - 场景适应性分析图表
            - 交叉评价热力图
            - 最佳策略匹配表
            """
            
            # 保存报告
            with open(f"{output_dir}/comprehensive_evaluation_report.md", 'w', encoding='utf-8') as f:
                f.write(report)
            
            print(f"综合评价报告已生成: {output_dir}/comprehensive_evaluation_report.md")
            
            return report


def run_system_tests():
        """运行系统单元测试"""
        unittest.main(argv=['first-arg-is-ignored'], exit=False)


def run_comprehensive_evaluation():
        """运行综合评价"""
        evaluator = SimulationEvaluator()
        
        # 评估不同策略
        evaluator.evaluate_strategies()
        
        # 评估不同场景
        evaluator.evaluate_scenarios()
        
        # 交叉评价
        evaluator.cross_evaluate()
        
        # 生成综合报告
        evaluator.generate_comprehensive_report()


if __name__ == "__main__":
        # 运行系统测试
        print("开始运行系统单元测试...\n")
        run_system_tests()
        
        # 运行综合评价
        print("\n开始运行综合评价...\n")
        run_comprehensive_evaluation()
        
        print("\n所有测试和评价已完成!")