# --------- 后端API服务 ---------
import flask
from flask import Flask, request, jsonify, send_file
import threading
import os
# import json
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime
import time
import logging

# 导入现有的EV充电系统模块
from ev_charging_scheduler import ChargingEnvironment, ChargingScheduler, ChargingVisualizationDashboard
from ev_model_training import MultiTaskModel
from ev_integration_scheduler import IntegratedChargingSystem
from ev_system_test import run_system_tests, run_comprehensive_evaluation

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("ev_api_server.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("EVAPIServer")

# 初始化Flask应用
app = Flask(__name__, static_folder='static')

# 全局系统实例
system = None
# 当前任务状态
current_task = {
    "id": None,
    "status": "idle",  # idle, running, completed, failed
    "progress": 0,
    "message": "",
    "result": None
}

# 初始化系统
def initialize_system(config_path=None):
    global system
    system = IntegratedChargingSystem(config_path)
    return system

# 运行后台任务的线程函数
def run_background_task(task_type, params):
    global current_task, system
    
    try:
        current_task["status"] = "running"
        current_task["message"] = f"正在执行{task_type}任务..."
        
        # 确保系统已初始化
        if system is None:
            initialize_system()
        
        # 根据任务类型执行不同操作
        if task_type == "simulate":
            days = params.get("days", 7)
            
            # 更新系统配置
            update_system_config(params)
            
            # 每10%进度更新一次状态
            steps = 10
            for i in range(steps):
                time.sleep(0.5)  # 模拟计算时间
                current_task["progress"] = (i+1) * (100/steps)
                current_task["message"] = f"模拟进行中...{int(current_task['progress'])}%"
            
            # 实际运行模拟
            metrics, avg_metrics = system.run_simulation(days=days)
            
            current_task["result"] = {
                "metrics": {k: v[-20:] for k, v in metrics.items()},  # 只返回最后20个数据点
                "avg_metrics": avg_metrics
            }
            
        elif task_type == "train":
            epochs = params.get("epochs", 50)
            
            # 更新模型配置
            update_system_config(params)
            
            # 模拟训练进度
            steps = epochs
            for i in range(steps):
                time.sleep(0.2)  # 模拟计算时间
                current_task["progress"] = (i+1) * (100/steps)
                current_task["message"] = f"训练进行中...第{i+1}/{epochs}轮"
            
            # 在实际应用中，这里会调用model_training.py中的训练函数
            # 简化起见，我们直接返回示例结果
            current_task["result"] = {
                "loss": 0.0325,
                "val_loss": 0.0412,
                "model_path": "models/ev_charging_model.pth"
            }
            
        elif task_type == "evaluate":
            # 更新系统配置
            update_system_config(params)
            
            # 模拟评估进度
            strategies = system.config["strategies"].keys()
            total_steps = len(strategies)
            
            for i, strategy in enumerate(strategies):
                time.sleep(0.3)  # 模拟计算时间
                current_task["progress"] = (i+1) * (100/total_steps)
                current_task["message"] = f"评估策略: {strategy}...{int(current_task['progress'])}%"
            
            # 运行策略比较
            comparison = system.compare_scheduling_strategies([
                {"name": s, "params": system.config["strategies"][s]} 
                for s in strategies
            ])
            
            current_task["result"] = comparison
            
        elif task_type == "analyze_users":
            num_days = params.get("days", 7)
            
            # 更新系统配置
            update_system_config(params)
            
            # 模拟分析进度
            for i in range(10):
                time.sleep(0.2)
                current_task["progress"] = (i+1) * 10
                current_task["message"] = f"分析用户行为...{current_task['progress']}%"
            
            # 执行用户行为分析
            analysis = system.analyze_user_behavior(num_days=num_days)
            
            current_task["result"] = analysis
            
        elif task_type == "analyze_grid":
            num_days = params.get("days", 7)
            
            # 更新系统配置
            update_system_config(params)
            
            # 模拟分析进度
            for i in range(10):
                time.sleep(0.2)
                current_task["progress"] = (i+1) * 10
                current_task["message"] = f"分析电网影响...{current_task['progress']}%"
            
            # 执行电网影响分析
            analysis = system.analyze_grid_impact(num_days=num_days)
            
            current_task["result"] = analysis
        
        current_task["status"] = "completed"
        current_task["message"] = f"{task_type}任务完成"
        logger.info(f"任务 {task_type} 成功完成")
        
    except Exception as e:
        current_task["status"] = "failed"
        current_task["message"] = f"执行失败: {str(e)}"
        logger.error(f"任务 {task_type} 失败: {str(e)}")
        
# 更新系统配置
def update_system_config(params):
    global system
    
    if system is None:
        initialize_system()
    
    # 更新环境配置
    if "gridId" in params:
        system.config["environment"]["grid_id"] = params["gridId"]
    if "chargerCount" in params:
        system.config["environment"]["charger_count"] = int(params["chargerCount"])
    if "userCount" in params:
        system.config["environment"]["user_count"] = int(params["userCount"])
    if "timeStep" in params:
        system.config["environment"]["time_step_minutes"] = int(params["timeStep"])
    
    # 更新模型配置
    if "hiddenDim" in params:
        system.config["model"]["hidden_dim"] = int(params["hiddenDim"])
    if "taskHiddenDim" in params:
        system.config["model"]["task_hidden_dim"] = int(params["taskHiddenDim"])
    if "useTrainedModel" in params:
        system.config["scheduler"]["use_trained_model"] = params["useTrainedModel"] == "true"
    if "modelPath" in params:
        system.config["model"]["model_path"] = params["modelPath"]
    
    # 更新权重配置
    if "userSatisfactionWeight" in params and "operatorProfitWeight" in params and "gridFriendlinessWeight" in params:
        weights = {
            "user_satisfaction": float(params["userSatisfactionWeight"]),
            "operator_profit": float(params["operatorProfitWeight"]),
            "grid_friendliness": float(params["gridFriendlinessWeight"])
        }
        
        # 更新所选策略的权重
        if "strategy" in params:
            system.config["strategies"][params["strategy"]] = weights
        
        # 更新调度器当前权重
        system.config["scheduler"]["optimization_weights"] = weights

# API路由
@app.route('/api/status', methods=['GET'])
def get_status():
    """获取当前系统状态"""
    return jsonify(current_task)

@app.route('/api/config', methods=['GET'])
def get_config():
    """获取系统配置"""
    global system
    
    if system is None:
        initialize_system()
        
    return jsonify(system.config)

@app.route('/api/run', methods=['POST'])
def run_task():
    """运行指定任务"""
    global current_task
    
    # 如果有任务正在运行，返回错误
    if current_task["status"] == "running":
        return jsonify({"error": "有任务正在运行中，请等待完成"}), 400
    
    # 获取任务参数
    data = request.json
    task_type = data.get("mode", "simulate")
    params = data.get("params", {})
    
    # 生成任务ID
    current_task["id"] = f"{task_type}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    current_task["status"] = "initialized"
    current_task["progress"] = 0
    current_task["message"] = "任务初始化中..."
    current_task["result"] = None
    
    # 启动后台线程
    thread = threading.Thread(target=run_background_task, args=(task_type, params))
    thread.daemon = True
    thread.start()
    
    return jsonify({"taskId": current_task["id"], "status": "initialized"})

@app.route('/api/results/<path:filename>', methods=['GET'])
def get_result_file(filename):
    """获取结果文件"""
    output_dir = system.config["visualization"]["output_dir"] if system else "output"
    file_path = os.path.join(output_dir, filename)
    
    if os.path.exists(file_path):
        return send_file(file_path)
    else:
        return jsonify({"error": f"文件 {filename} 不存在"}), 404

@app.route('/api/chargers', methods=['GET'])
def get_chargers():
    """获取充电桩状态"""
    global system
    
    if system is None or system.env is None:
        return jsonify({"error": "系统未初始化"}), 500
    
    # 获取当前充电桩状态
    state = system.env.get_current_state()
    return jsonify({"chargers": state["chargers"]})

@app.route('/api/users', methods=['GET'])
def get_users():
    """获取用户状态"""
    global system
    
    if system is None or system.env is None:
        return jsonify({"error": "系统未初始化"}), 500
    
    # 获取当前用户状态
    state = system.env.get_current_state()
    return jsonify({"users": state["users"]})

@app.route('/api/grid', methods=['GET'])
def get_grid():
    """获取电网状态"""
    global system
    
    if system is None or system.env is None:
        return jsonify({"error": "系统未初始化"}), 500
    
    # 获取当前电网状态
    state = system.env.get_current_state()
    return jsonify({"grid": state["grid_status"]})

@app.route('/api/decisions', methods=['GET'])
def get_decisions():
    """获取当前调度决策"""
    global system
    
    if system is None or system.scheduler is None:
        return jsonify({"error": "系统未初始化"}), 500
    
    # 获取当前状态
    state = system.env.get_current_state()
    
    # 生成调度决策
    decisions = system.scheduler.make_scheduling_decision(state)
    
    # 增强决策数据
    enhanced_decisions = []
    for user_id, charger_id in decisions.items():
        # 找出用户和充电桩详情
        user_info = next((u for u in state["users"] if u["user_id"] == user_id), None)
        charger_info = next((c for c in state["chargers"] if c["charger_id"] == charger_id), None)
        
        if user_info and charger_info:
            # 计算等待时间
            wait_time = charger_info["queue_length"] * charger_info.get("avg_waiting_time", 10)
            
            # 估算费用
            current_hour = datetime.fromisoformat(state["timestamp"]).hour
            if current_hour in [7, 8, 9, 10, 18, 19, 20, 21]:  # 高峰时段
                price = state["grid_status"].get("peak_price", 1.2)
            elif current_hour in [0, 1, 2, 3, 4, 5]:  # 低谷时段
                price = state["grid_status"].get("valley_price", 0.4)
            else:
                price = state["grid_status"].get("normal_price", 0.85)
            
            # 假设充电30%，电池容量60kWh
            charge_amount = min(100 - user_info["soc"], 30) / 100 * 60
            cost = charge_amount * price * 1.1  # 运营商加价10%
            
            enhanced_decisions.append({
                "user_id": user_id,
                "user_type": user_info.get("user_type", "未知"),
                "soc": user_info["soc"],
                "charger_id": charger_id,
                "wait_time": wait_time,
                "estimated_cost": round(cost, 1)
            })
    
    return jsonify({"decisions": enhanced_decisions})

@app.route('/', methods=['GET'])
def index():
    """返回主页"""
    return send_file('static/index.html')

# 启动服务器
def start_server(host='0.0.0.0', port=5000, debug=False):
    app.run(host=host, port=port, debug=debug)

if __name__ == "__main__":
    # 初始化系统
    initialize_system()
    # 启动服务器
    start_server()

