## 系统架构

目前系统由以下五个主要模块组成：

1. **充电环境模拟模块** (ChargingEnvironment)：模拟电网状态、充电桩及用户行为
2. **模型训练模块** (Model Training)：基于多任务学习训练决策模型
3. **充电调度模块** (ChargingScheduler)：生成最优充电桩分配策略
4. **集成调度系统** (IntegratedChargingSystem)：整合各模块并提供统一接口
5. **可视化与评价模块** (Visualization & Evaluation)：展示系统运行状态和评估系统性能

### 架构图

```
+-------------------+    +-------------------+    +-------------------+
|  充电环境模拟模块  |<-->|    模型训练模块    |<-->|    充电调度模块    |
+-------------------+    +-------------------+    +-------------------+
          ^                        ^                       ^
          |                        |                       |
          v                        v                       v
+--------------------------------------------------------------------+
|                         集成调度系统                                |
+--------------------------------------------------------------------+
                                ^
                                |
                                v
+--------------------------------------------------------------------+
|             可视化与评价模块(暂时在终端中用命令行交互)               |
+--------------------------------------------------------------------+
```


1. **环境配置 (environment)**
   ```json
   "environment": {
       "grid_id": "DEFAULT001",
       "charger_count": 20,
       "user_count": 50,
       "simulation_days": 7,
       "time_step_minutes": 15
   }
   ```

2. **模型配置 (model)**
   ```json
   "model": {
       "input_dim": 19,
       "hidden_dim": 128,
       "task_hidden_dim": 64,
       "model_path": "models/ev_charging_model.pth"
   }
   ```

3. **调度器配置 (scheduler)**
   ```json
   "scheduler": {
       "use_trained_model": true,
       "optimization_weights": {
           "user_satisfaction": 0.4,
           "operator_profit": 0.3,
           "grid_friendliness": 0.3
       }
   }
   ```

4. **可视化配置 (visualization)**
   ```json
   "visualization": {
       "dashboard_port": 8050,
       "update_interval": 15,
       "output_dir": "output"
   }
   ```

5. **策略配置 (strategies)**
   ```json
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
   ```

### 运行参数

系统支持以下命令行参数：

- `--mode`：运行模式 (simulate, train, evaluate, visualize, test, all)
- `--config`：配置文件路径
- `--days`：模拟天数
- `--strategy`：使用的策略 (user, profit, grid, balanced)
- `--output_dir`：输出目录
- `--log_level`：日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)

例如：
```
python ev_main.py --mode all --strategy balanced --days 14 --output_dir results
```

## 系统评价与测试

### 评价指标

1. **用户满意度**
   - 等待时间因子
   - 充电功率匹配度
   - 价格满意度

2. **运营商利润**
   - 充电收入
   - 电网采购成本
   - 设备折旧成本

3. **电网友好度**
   - 峰值负载削减
   - 负载方差
   - 可再生能源利用率

### 测试场景

系统通过以下四种典型场景进行全面测试：

1. **正常工作日**：用户数量适中，充电需求稳定
2. **假日高峰**：用户数量增加，充电资源紧张
3. **低负载夜间**：用户较少，电网负载低
4. **充电桩故障**：部分充电桩不可用，资源受限


## 使用指南

### 快速开始

1. **安装依赖**
   ```
   pip install -r requirements.txt
   ```

2. **运行模拟**
   ```
   python ev_main.py --mode simulate --strategy balanced --days 7
   ```

3. **训练模型**
   ```
   python ev_main.py --mode train
   ```

4. **评估策略**
   ```
   python ev_main.py --mode evaluate
   ```

5. **运行全流程**
   ```
   python ev_main.py --mode all
   ```

