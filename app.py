from flask import Flask, request, jsonify, send_from_directory
import json
import os
import matplotlib.pyplot as plt
from datetime import datetime
import shutil
from ev_charging_scheduler import ChargingScheduler, ChargingEnvironment
from ev_integration_scheduler import IntegratedChargingSystem
import random
import math
import matplotlib
import time
import pickle  # 用于保存模拟结果
import traceback  # 添加traceback模块导入
matplotlib.use('Agg')  # 使用非GUI后端避免线程问题

app = Flask(__name__, static_folder='static')

# 系统配置路径
CONFIG_PATH = 'config.json'
OUTPUT_DIR = "output"
RESULTS_DIR = "simulation_results"  # 添加结果保存目录

# 模拟进度全局变量
simulation_progress = {
    "percent": 0,
    "message": "准备中...",
    "start_time": None
}

# 加载配置函数
def load_config(config_path):
    """加载配置文件，如果不存在则创建默认配置"""
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        return config
    else:
        # 使用init_config中的逻辑生成默认配置
        return init_config(return_config=True)

# 初始化配置
def init_config(return_config=False):
    """初始化配置文件"""
    default_config = None
    if not os.path.exists(CONFIG_PATH):
        print(f"配置文件 {CONFIG_PATH} 不存在，创建默认配置")
        default_config = {
            "environment": {
                "charger_count": 20,
                "user_count": 50,
                "simulation_days": 7,
                "time_step_minutes": 15,
                "grid_id": "DEFAULT001"
            },
            "grid": {
                "base_load": [40, 35, 30, 28, 27, 30, 45, 60, 75, 80, 82, 84, 80, 75, 70, 65, 70, 75, 85, 90, 80, 70, 60, 50],
                "peak_hours": [7, 8, 9, 10, 18, 19, 20, 21],
                "valley_hours": [0, 1, 2, 3, 4, 5],
                "normal_price": 0.85,
                "peak_price": 1.2,
                "valley_price": 0.4
            },
            "model": {
                "input_dim": 19,
                "hidden_dim": 128,
                "task_hidden_dim": 64,
                "model_path": "models/ev_charging_model.pth"
            },
            "scheduler": {
                "optimization_weights": {
                    "grid_friendliness": 0.3,
                    "operator_profit": 0.3,
                    "user_satisfaction": 0.4
                },
                "use_trained_model": True
            },
            "strategies": {
                "balanced": {"grid_friendliness": 0.34, "operator_profit": 0.33, "user_satisfaction": 0.33},
                "grid": {"grid_friendliness": 0.6, "operator_profit": 0.2, "user_satisfaction": 0.2},
                "profit": {"grid_friendliness": 0.2, "operator_profit": 0.6, "user_satisfaction": 0.2},
                "user": {"grid_friendliness": 0.2, "operator_profit": 0.2, "user_satisfaction": 0.6}
            },
            "visualization": {
                "output_dir": OUTPUT_DIR,
                "minimal_output": True
            }
        }
        
        # 确保输出目录存在
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        os.makedirs("static/results", exist_ok=True)
        os.makedirs(RESULTS_DIR, exist_ok=True)  # 创建结果保存目录
        
        # 保存默认配置
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(default_config, f, indent=4)
        
        print("默认配置已创建")
    else:
        print(f"配置文件 {CONFIG_PATH} 已存在")
        if return_config:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                default_config = json.load(f)
    
    # 确保结果目录存在
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs("static/results", exist_ok=True)
    os.makedirs(RESULTS_DIR, exist_ok=True)
    
    if return_config:
        return default_config

# 确保应用启动时初始化配置
with app.app_context():
    init_config()

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/api/config', methods=['GET', 'POST'])
def handle_config():
    if request.method == 'GET':
        with open(CONFIG_PATH) as f:
            config = json.load(f)
        return jsonify(config)
    else:
        # 创建配置文件备份
        backup_path = f"config_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        shutil.copy(CONFIG_PATH, backup_path)
        
        # 获取当前配置
        with open(CONFIG_PATH) as f:
            current_config = json.load(f)
        
        # 获取新配置并合并
        new_config = request.json
        
        # 使用递归函数合并配置
        def merge_configs(current, new):
            for key, value in new.items():
                if key in current and isinstance(current[key], dict) and isinstance(value, dict):
                    merge_configs(current[key], value)
                else:
                    current[key] = value
            return current
        
        # 合并配置
        updated_config = merge_configs(current_config, new_config)
        
        # 保存更新后的配置
        with open(CONFIG_PATH, 'w') as f:
            json.dump(updated_config, f, indent=4)
        
        return jsonify({"status": "success"})

@app.route('/api/progress', methods=['GET'])
def get_progress():
    """获取模拟进度"""
    global simulation_progress
    
    # 计算已用时间
    elapsed = 0
    if simulation_progress.get("start_time"):
        elapsed = time.time() - simulation_progress["start_time"]
    
    # 估计剩余时间
    remaining = 0
    if simulation_progress["percent"] > 0:
        remaining = (elapsed / simulation_progress["percent"]) * (100 - simulation_progress["percent"])
    
    return jsonify({
        "percent": simulation_progress["percent"],
        "message": simulation_progress["message"],
        "elapsed_seconds": int(elapsed),
        "remaining_seconds": int(remaining)
    })

@app.route('/api/simulate', methods=['POST'])
def run_simulation():
    """运行充电调度模拟"""
    global simulation_progress
    
    # 重置模拟进度
    simulation_progress = {"percent": 0, "message": "准备模拟环境..."}
    
    try:
        data = request.json
        strategy = data.get('strategy', 'balanced')
        days = int(data.get('days', 7))
        full_analysis = data.get('fullAnalysis', False)
        save_result = data.get('saveResult', False)
        
        print(f"使用策略: {strategy}, 天数: {days}, 完整分析: {full_analysis}")
    
        # 加载配置
        config = load_config(CONFIG_PATH)
    
        # 更新策略权重
        if strategy in config['strategies']:
            config['scheduler']['optimization_weights'] = config['strategies'][strategy]
    
            # 确保model配置存在
            if 'model' not in config:
                config['model'] = {
                    "input_dim": 19,
                    "hidden_dim": 128,
                    "task_hidden_dim": 64,
                    "model_path": "models/ev_charging_model.pth"
                }
                
                # 将更新后的配置写回文件
                with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
                    json.dump(config, f, indent=4)
            
            # 确保output目录存在
            output_dir = config['visualization']['output_dir']
            os.makedirs(output_dir, exist_ok=True)
            
            # 生成时间戳，用于结果文件命名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # 使用真实计算
            metrics, avg_metrics, charts, analysis_data = run_real_simulation(config, strategy, days, full_analysis, timestamp)
            
            # 记录模拟开始时间
            simulation_progress["start_time"] = time.time()
            
            # 如果需要保存结果
            result_id = None
            if save_result:
                # 确保结果保存目录存在
                result_dir = "simulation_results"
                os.makedirs(result_dir, exist_ok=True)
                
                # 构造结果ID和文件名
                result_id = f"{timestamp}_{strategy}_{days}days"
                result_file = os.path.join(result_dir, f"{result_id}.pkl")
                
                # 保存结果
                result_data = {
                    "timestamp": timestamp,
                    "strategy": strategy,
                    "days": days,
                    "metrics": metrics,
                    "avg_metrics": avg_metrics,
                    "charts": charts,
                    "analysis": analysis_data,
                    "full_analysis": full_analysis
                }
                
                with open(result_file, 'wb') as f:
                    pickle.dump(result_data, f)
                
                print(f"模拟结果已保存至: {result_file}")
            
            # 更新进度为100%
            simulation_progress = {"percent": 100, "message": "模拟完成"}
            
            # 返回结果
            return jsonify({
                "success": True,
                "metrics": metrics,
                "avg_metrics": avg_metrics,
                "charts": charts,
                "analysis": analysis_data,
                "result_id": result_id,
                "timestamp": timestamp
            })
    
    except Exception as e:
        print(f"模拟过程中发生错误: {str(e)}")
        traceback.print_exc()
        
        # 更新进度显示错误
        simulation_progress = {"percent": 100, "message": f"模拟失败: {str(e)}"}
        
        return jsonify({
            "success": False,
            "error": str(e),
            "details": traceback.format_exc()
        }), 500

def run_real_simulation(config, strategy, days, full_analysis, timestamp):
    """运行真实的充电模拟计算"""
    global simulation_progress
    
    simulation_progress = {"percent": 10, "message": "初始化集成充电系统..."}
    
    try:
        # 打印配置信息，帮助调试
        print(f"运行真实计算，使用配置: {config}")
        if 'model' in config:
            print(f"模型配置存在: {config['model']}")
        else:
            print("警告: 配置中没有model键")
            
        # 创建并初始化集成系统
        print("开始创建IntegratedChargingSystem...")
        system = IntegratedChargingSystem(config_path=CONFIG_PATH)
        print("IntegratedChargingSystem创建成功")
        
        # 设置输出目录
        output_dir = config['visualization']['output_dir']
        os.makedirs(output_dir, exist_ok=True)
        system.config["visualization"]["output_dir"] = output_dir
        
        # 设置策略权重
        system.config["scheduler"]["optimization_weights"] = config["strategies"][strategy]
        
    # 运行模拟
        simulation_progress = {"percent": 20, "message": f"执行{days}天的模拟计算..."}
        print(f"开始运行{days}天的模拟计算...")
        metrics, avg_metrics = system.run_simulation(days=days)
        print("模拟计算完成，生成结果...")
        
        # 生成图表路径和文件
        chart_filename = f"simulation_result_{timestamp}.png"
        main_chart_path = f"results/{chart_filename}"  # 移除前导斜杠
        
        # 创建并保存主图表
        plt.figure(figsize=(10, 6))
        
        # 提取均值数据用于图表
        metrics_data = [
            avg_metrics.get("user_satisfaction", 0.0),
            avg_metrics.get("operator_profit", 0.0),
            avg_metrics.get("grid_friendliness", 0.0),
            avg_metrics.get("total_reward", 0.0)
        ]
        
        # 绘制柱状图
        labels = ['用户满意度', '运营商利润', '电网友好度', '综合奖励']
        colors = ['#4e73df', '#1cc88a', '#36b9cc', '#f6c23e']
        
        plt.bar(labels, metrics_data, color=colors)
        plt.title(f"充电调度模拟结果 (策略: {strategy})")
        plt.ylim(0, 1.0)
        plt.grid(True, axis='y', linestyle='--', alpha=0.7)
        
        # 保存图表到static/results目录
        plt.savefig(f"static/{main_chart_path}")
        plt.close()
        
        # 为API返回加上前导斜杠
        charts = [f"/{main_chart_path}"]
        
        # 如果需要完整分析
        analysis_data = {}
        if full_analysis:
            simulation_progress = {"percent": 90, "message": "生成用户行为分析..."}
            print("开始生成用户行为分析...")
            user_behavior = system.analyze_user_behavior(num_days=days)
            
            simulation_progress = {"percent": 95, "message": "生成电网影响分析..."}
            print("开始生成电网影响分析...")
            grid_impact = system.analyze_grid_impact(num_days=days)
            
            analysis_data = {
                "user_behavior": user_behavior,
                "grid_impact": grid_impact
            }
            
            # 添加额外图表路径，使用绝对路径
            extra_charts = [
                "hourly_charging_demand.png",
                "user_type_distribution.png",
                "grid_load_comparison.png",
                "charging_patterns.png",
                "user_satisfaction_matrix.png"
            ]
            
            for chart in extra_charts:
                charts.append(f"/output/{chart}")
            
        print("真实计算结果生成完成")
        return metrics, avg_metrics, charts, analysis_data
    
    except Exception as e:
        print(f"真实计算过程中发生错误: {str(e)}")
        traceback.print_exc()  # 打印完整的堆栈跟踪
        simulation_progress = {"percent": 100, "message": f"模拟失败: {str(e)}"}
        raise e

def create_metrics_chart(metrics, strategy, output_path):
    """创建指标图表"""
    plt.figure(figsize=(10, 6))
    
    x = range(len(metrics["user_satisfaction"]))
    
    plt.plot(x, metrics["user_satisfaction"], "b-", label="用户满意度")
    plt.plot(x, metrics["operator_profit"], "g-", label="运营商利润")
    plt.plot(x, metrics["grid_friendliness"], "r-", label="电网友好度")
    plt.plot(x, metrics["total_reward"], "k-", label="总奖励")
    
    plt.title(f"充电调度模拟结果 (策略: {strategy})")
    plt.xlabel("时间")
    plt.ylabel("指标值")
    plt.legend()
    plt.grid(True)
    
    # 保存图表
    plt.savefig(f"static/{output_path.lstrip('/')}")
    plt.close()

def create_hourly_demand_chart(output_path):
    """创建小时充电需求图表"""
    plt.figure(figsize=(10, 6))
    
    hours = range(24)
    demand = [random.uniform(10, 50) for _ in range(24)]
    
    # 生成柱状图
    bars = plt.bar(hours, demand, color='skyblue')
    
    # 在高峰时段使用不同颜色
    peak_hours = [8, 9, 17, 18, 19]
    for i in peak_hours:
        bars[i].set_color('coral')
    
    plt.title("24小时充电需求分布")
    plt.xlabel("小时")
    plt.ylabel("充电需求 (kW)")
    plt.xticks(hours)
    plt.grid(True, axis='y', linestyle='--', alpha=0.7)
    
    # 添加图例
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor='skyblue', label='普通时段'),
        Patch(facecolor='coral', label='高峰时段')
    ]
    plt.legend(handles=legend_elements)
    
    # 保存图表
    plt.savefig(f"static/{output_path.lstrip('/')}")
    plt.close()

def create_user_types_chart(output_path):
    """创建用户类型分布图表"""
    plt.figure(figsize=(8, 8))
    
    # 用户类型及其比例
    types = ['通勤者', '购物者', '旅行者', '居民']
    values = [
        random.uniform(0.4, 0.6),
        random.uniform(0.2, 0.3),
        random.uniform(0.1, 0.2),
        random.uniform(0.1, 0.2)
    ]
    
    # 标准化比例，确保总和为1
    total = sum(values)
    values = [v/total for v in values]
    
    # 定义饼图颜色
    colors = ['#ff9999', '#66b3ff', '#99ff99', '#ffcc99']
    
    # 生成饼图
    plt.pie(values, labels=types, colors=colors, autopct='%1.1f%%', startangle=90, shadow=True)
    plt.axis('equal')  # 保持饼图为圆形
    plt.title("用户类型分布")
    
    # 保存图表
    plt.savefig(f"static/{output_path.lstrip('/')}")
    plt.close()

def create_grid_load_chart(output_path):
    """创建电网负荷对比图表"""
    plt.figure(figsize=(12, 6))
    
    hours = range(24)
    
    # 模拟电网基准负荷
    base_load = [40, 35, 30, 28, 27, 30, 45, 60, 75, 80, 82, 84, 80, 75, 70, 65, 70, 75, 85, 90, 80, 70, 60, 50]
    
    # 模拟无调度充电负荷
    no_scheduling_load = [load + random.uniform(5, 15) for load in base_load]
    
    # 模拟有调度充电负荷
    scheduling_load = []
    for i, load in enumerate(base_load):
        if i in [0, 1, 2, 3, 4, 5, 13, 14, 15, 22, 23]:  # 低谷时段增加负荷
            scheduling_load.append(load + random.uniform(10, 20))
        elif i in [7, 8, 9, 10, 18, 19, 20]:  # 高峰时段减少负荷
            scheduling_load.append(load + random.uniform(0, 5))
        else:  # 其他时段适中增加
            scheduling_load.append(load + random.uniform(5, 10))
    
    plt.plot(hours, base_load, 'k--', label='基准负荷')
    plt.plot(hours, no_scheduling_load, 'r-', label='无调度充电')
    plt.plot(hours, scheduling_load, 'g-', label='有调度充电')
    
    plt.title("电网负荷对比")
    plt.xlabel("小时")
    plt.ylabel("负荷 (MW)")
    plt.xticks(hours)
    plt.grid(True)
    plt.legend()
    
    # 保存图表
    plt.savefig(f"static/{output_path.lstrip('/')}")
    plt.close()

@app.route('/api/strategies', methods=['GET'])
def get_strategies():
    with open(CONFIG_PATH) as f:
        config = json.load(f)
    return jsonify(config['strategies'])

@app.route('/api/update_strategy', methods=['POST'])
def update_strategy():
    data = request.json
    strategy_name = data['name']
    weights = data['weights']
    
    # 创建配置文件备份
    backup_path = f"config_backup_strategy_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    shutil.copy(CONFIG_PATH, backup_path)
    
    with open(CONFIG_PATH) as f:
        config = json.load(f)
    
    # 确保strategies键存在
    if 'strategies' not in config:
        config['strategies'] = {}
    
    # 更新策略权重
        config['strategies'][strategy_name] = weights
    
    # 保存更新后的配置
    with open(CONFIG_PATH, 'w') as f:
        json.dump(config, f, indent=4)
    
    return jsonify({"status": "success"})

@app.route('/output/<path:filename>')
def download_file(filename):
    """下载输出文件"""
    return send_from_directory(OUTPUT_DIR, filename)

# 进度回调函数
def update_progress(current, total):
    """更新模拟进度"""
    global simulation_progress
    
    percent = int((current / total) * 100) if total > 0 else 0
    simulation_progress["percent"] = percent
    
    if current % 10 == 0 or current == total:  # 减少进度更新频率
        simulation_progress["message"] = f"模拟中: 第{current}/{total}步"

# 静态文件路由
@app.route('/static/<path:path>')
def serve_static(path):
    """提供静态文件访问"""
    return send_from_directory('static', path)

# 添加专门的结果图片路由
@app.route('/results/<path:filename>')
def serve_results(filename):
    """提供结果图片访问"""
    # 先尝试从static/results目录提供文件
    try:
        print(f"尝试从static/results提供文件: {filename}")
        return send_from_directory('static/results', filename)
    except:
        # 如果找不到，则尝试从output目录提供文件
        print(f"从static/results提供文件失败，尝试从output目录: {filename}")
        try:
            return send_from_directory('output', filename)
        except Exception as e:
            print(f"无法提供文件 {filename}: {str(e)}")
            return f"文件不存在: {filename}", 404

# 添加获取历史模拟结果列表的接口
@app.route('/api/simulation_history', methods=['GET'])
def get_simulation_history():
    """获取历史模拟结果列表"""
    result_files = []
    
    try:
        # 读取结果目录中的所有.pkl文件
        for filename in os.listdir(RESULTS_DIR):
            if filename.endswith('.pkl'):
                # 从文件名中提取时间和策略信息
                parts = filename.replace('.pkl', '').split('_')
                if len(parts) >= 4:
                    date = parts[0]
                    time = parts[1]
                    strategy = parts[2]
                    days = int(parts[3].replace('days', ''))
                    
                    # 格式化时间为可读格式
                    timestamp = f"{date[:4]}-{date[4:6]}-{date[6:]} {time[:2]}:{time[2:4]}:{time[4:]}"
                    
                    result_files.append({
                        "id": filename.replace('.pkl', ''),
                        "timestamp": timestamp,
                        "strategy": strategy,
                        "days": days,
                        "filename": filename
                    })
        
        # 按时间倒序排序，最新的在前面
        result_files.sort(key=lambda x: x['timestamp'], reverse=True)
        
        return jsonify({
            "status": "success",
            "data": result_files
        })
    
    except Exception as e:
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500

# 添加获取指定历史模拟结果的接口
@app.route('/api/simulation_result/<result_id>', methods=['GET'])
def get_simulation_result(result_id):
    """获取指定的历史模拟结果"""
    try:
        # 构建文件路径
        filepath = os.path.join(RESULTS_DIR, f"{result_id}.pkl")
        
        # 检查文件是否存在
        if not os.path.exists(filepath):
            return jsonify({
                "status": "error",
                "error": "指定的结果不存在"
            }), 404
        
        # 读取结果数据
        with open(filepath, 'rb') as f:
            result_data = pickle.load(f)
        
        return jsonify({
            "status": "success",
            "data": result_data
        })
    
    except Exception as e:
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500

# 添加模型训练功能API
@app.route('/api/train_model', methods=['POST'])
def train_model():
    """训练决策模型API"""
    global simulation_progress
    
    # 重置进度
    simulation_progress = {
        "percent": 0,
        "message": "准备训练决策模型...",
        "start_time": time.time()
    }
    
    try:
        # 解析请求数据
        data = request.json
        epochs = int(data.get('epochs', 50))
        batch_size = int(data.get('batch_size', 64))
        
        # 读取配置文件
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            config = json.load(f)
            
        print(f"开始训练模型，epochs: {epochs}, batch_size: {batch_size}")
        
        # 更新进度
        simulation_progress["message"] = "初始化训练环境..."
        simulation_progress["percent"] = 5
        
        try:
            # 导入并使用ev_main.py中的训练逻辑
            from ev_model_training import DataGenerator, train_model as train_model_func
            
            # 更新进度
            simulation_progress["message"] = "生成训练数据..."
            simulation_progress["percent"] = 10
            
            # 生成数据
            data_gen = DataGenerator(num_samples=50000)
            X, y_satisfaction, y_profit, y_grid = data_gen.generate_samples()
            
            # 更新进度
            simulation_progress["message"] = "数据生成完成，准备训练..."
            simulation_progress["percent"] = 20
            
            # 分割数据
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
            
            # 更新进度
            simulation_progress["message"] = "开始训练模型..."
            simulation_progress["percent"] = 30
            
            # 创建进度更新回调
            def progress_update(epoch, epochs):
                progress = 30 + int((epoch / epochs) * 60)  # 从30%到90%
                simulation_progress["percent"] = progress
                simulation_progress["message"] = f"训练模型中: Epoch {epoch}/{epochs}"
            
            # 训练模型
            input_dim = X.shape[1]
            model, history = train_model_func(
                X_train, y_train_satisfaction, y_train_profit, y_train_grid,
                X_val, y_val_satisfaction, y_val_profit, y_val_grid,
                input_dim, batch_size=batch_size, epochs=epochs
            )
            
            # 更新进度
            simulation_progress["message"] = "模型训练完成，评估模型性能..."
            simulation_progress["percent"] = 90
            
            # 生成学习曲线图表
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
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
            
            # 确保结果目录存在
            os.makedirs("static/results", exist_ok=True)
            
            # 保存学习曲线图
            learning_curve_path = f"static/results/learning_curves_{timestamp}.png"
            plt.savefig(learning_curve_path)
            plt.close()
            
            # 保存模型
            model_dir = os.path.dirname(config.get("model", {}).get("model_path", "models/ev_charging_model.pth"))
            os.makedirs(model_dir, exist_ok=True)
            
            import torch
            model_path = os.path.join(model_dir, f"ev_charging_model_{timestamp}.pth")
            torch.save(model.state_dict(), model_path)
            
            # 如果配置文件中有model路径，更新它
            if "model" in config:
                if "model_path" not in config["model"]:
                    config["model"]["model_path"] = model_path
            
            # 保存更新后的配置
            with open(CONFIG_PATH, 'w') as f:
                json.dump(config, f, indent=4)
            
            # 更新进度
            simulation_progress["message"] = "训练完成!"
            simulation_progress["percent"] = 100
            
            # 返回训练结果
            result = {
                "status": "success",
                "message": "模型训练成功",
                "learning_curve": learning_curve_path.replace("static/", ""),
                "model_path": model_path,
                "training_info": {
                    "epochs": epochs,
                    "batch_size": batch_size,
                    "final_loss": history['train_loss'][-1],
                    "validation_loss": history['val_loss'][-1],
                    "timestamp": timestamp
                }
            }
            
            return jsonify(result)
            
        except Exception as train_error:
            import traceback
            error_details = traceback.format_exc()
            print(f"训练模型过程中发生错误: {train_error}\n{error_details}")
            
            # 更新错误状态
            simulation_progress["message"] = f"训练错误: {str(train_error)}"
            simulation_progress["percent"] = 100
            
            return jsonify({
                "status": "error",
                "error": str(train_error),
                "details": error_details
            }), 500
    
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"训练模型API错误: {e}\n{error_details}")
        
        # 更新错误状态
        simulation_progress["message"] = f"错误: {str(e)}"
        simulation_progress["percent"] = 100
        
        return jsonify({
            "status": "error",
            "error": str(e),
            "details": error_details
        }), 500

# 添加系统测试功能API
@app.route('/api/run_tests', methods=['POST'])
def run_tests():
    """运行系统测试API"""
    global simulation_progress
    
    # 重置进度
    simulation_progress = {
        "percent": 0,
        "message": "准备系统测试...",
        "start_time": time.time()
    }
    
    try:
        # 解析请求数据
        data = request.json
        test_type = data.get('test_type', 'all')  # all, environment, scheduler, integrated
        
        # 读取配置文件
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            config = json.load(f)
            
        print(f"开始运行系统测试，测试类型: {test_type}")
        
        # 更新进度
        simulation_progress["message"] = "初始化测试环境..."
        simulation_progress["percent"] = 5
        
        try:
            # 导入并使用ev_system_test.py中的测试逻辑
            from ev_system_test import run_system_tests, run_comprehensive_evaluation
            import unittest
            
            # 测试结果记录
            test_results = {}
            test_summary = {}
            
            # 更新进度
            simulation_progress["message"] = "运行系统测试..."
            simulation_progress["percent"] = 20
            
            # 创建输出目录
            test_output_dir = os.path.join(OUTPUT_DIR, "test_results")
            os.makedirs(test_output_dir, exist_ok=True)
            
            # 将标准输出重定向到文件
            import sys
            from io import StringIO
            original_stdout = sys.stdout
            sys.stdout = test_output = StringIO()
            
            # 运行测试
            if test_type == 'all':
                # 运行所有测试
                test_suite = unittest.defaultTestLoader.discover('.')
                test_runner = unittest.TextTestRunner(verbosity=2)
                test_result = test_runner.run(test_suite)
                
                # 运行综合评估
                evaluation_result = run_comprehensive_evaluation()
                
                # 更新进度
                simulation_progress["message"] = "测试完成，生成评估报告..."
                simulation_progress["percent"] = 80
                
                # 记录测试结果
                test_summary = {
                    "run": test_result.testsRun,
                    "failures": len(test_result.failures),
                    "errors": len(test_result.errors),
                    "skipped": len(test_result.skipped),
                    "success": test_result.wasSuccessful()
                }
                
            else:
                # 根据指定的测试类型运行特定测试
                from ev_system_test import SystemTest
                
                test_loader = unittest.TestLoader()
                if test_type == 'environment':
                    tests = [t for t in dir(SystemTest) if t.startswith('test_environment')]
                elif test_type == 'scheduler':
                    tests = [t for t in dir(SystemTest) if t.startswith('test_scheduler')]
                else:  # integrated
                    tests = [t for t in dir(SystemTest) if t.startswith('test_integrated')]
                
                suite = unittest.TestSuite()
                for test in tests:
                    suite.addTest(SystemTest(test))
                
                test_runner = unittest.TextTestRunner(verbosity=2)
                test_result = test_runner.run(suite)
                
                # 更新进度
                simulation_progress["message"] = "测试完成，生成测试报告..."
                simulation_progress["percent"] = 80
                
                # 记录测试结果
                test_summary = {
                    "run": test_result.testsRun,
                    "failures": len(test_result.failures),
                    "errors": len(test_result.errors),
                    "skipped": len(test_result.skipped),
                    "success": test_result.wasSuccessful()
                }
            
            # 恢复标准输出
            test_output_content = test_output.getvalue()
            sys.stdout = original_stdout
            
            # 保存测试输出到文件
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            test_output_file = os.path.join(test_output_dir, f"test_output_{timestamp}.txt")
            with open(test_output_file, 'w') as f:
                f.write(test_output_content)
            
            # 更新进度
            simulation_progress["message"] = "测试完成!"
            simulation_progress["percent"] = 100
            
            # 返回测试结果
            result = {
                "status": "success",
                "message": "系统测试完成",
                "test_summary": test_summary,
                "test_output_file": f"/output/test_results/test_output_{timestamp}.txt",
                "timestamp": timestamp
            }
            
            return jsonify(result)
            
        except Exception as test_error:
            import traceback
            error_details = traceback.format_exc()
            print(f"测试过程中发生错误: {test_error}\n{error_details}")
            
            # 更新错误状态
            simulation_progress["message"] = f"测试错误: {str(test_error)}"
            simulation_progress["percent"] = 100
            
            return jsonify({
                "status": "error",
                "error": str(test_error),
                "details": error_details
            }), 500
    
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"测试API错误: {e}\n{error_details}")
        
        # 更新错误状态
        simulation_progress["message"] = f"错误: {str(e)}"
        simulation_progress["percent"] = 100
        
        return jsonify({
            "status": "error",
            "error": str(e),
            "details": error_details
        }), 500

if __name__ == '__main__':
    app.run(debug=True)