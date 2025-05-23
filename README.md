# EV-TriFocus: 智能电动汽车充电调度仿真平台

## 项目概述

EV-TriFocus 是一个先进的电动汽车 (EV) 充电调度仿真平台。它旨在模拟和评估在不同场景下（用户行为、电网负载、可再生能源利用率）的各种智能充电调度算法的性能。该平台提供了一个动态的环境，用于测试和比较包括基于规则、多智能体系统 (MAS) 和强化学习 (MARL) 在内的多种调度策略，目标是优化用户满意度、运营商利润和电网友好性这三个关键维度。

项目提供了一个基于 Web 的用户界面，用于配置模拟参数、运行模拟、实时监控关键指标以及查看和分析历史模拟结果。此外，它还支持通过命令行界面 (CLI) 运行模拟，方便进行批量测试和集成到自动化流程中。

## 主要特性

* **模块化仿真环境**:
  * 模拟动态变化的电动汽车用户行为（包括出行、充电需求、SOC 变化）。
  * 模拟具有不同类型和状态的充电桩网络。
  * 模拟电网负载、可再生能源发电和实时电价。
* **可插拔的调度算法**:
  * 支持多种调度算法，方便比较和扩展：
    * **基于规则 (Rule-Based)**: 根据预定义的启发式规则和加权评分进行决策。
    * **无序充电 (Uncoordinated)**: 作为基准，模拟用户随机选择最近可用充电桩的行为。
    * **多智能体强化学习 (MARL)**: 每个充电桩作为一个智能体，通过 Q-learning 学习最优调度策略。
    * **协调式多智能体系统 (Coordinated MAS)**: 包含多个目标导向的智能体（用户满意度、运营商利润、电网友好性），通过协调器进行决策。
  * 易于添加新的自定义调度算法。
* **三维目标优化**: 核心目标是平衡用户满意度、运营商利润和电网友好性。
* **Web 用户界面**:
  * 通过网页配置模拟参数。
  * 启动、停止和监控模拟过程。
  * 实时图表展示关键性能指标 (KPIs)。
  * 查看和比较历史模拟结果。
* **命令行界面 (CLI)**:
  * 支持无头模式运行模拟。
  * 通过命令行参数覆盖配置，方便批量实验。
  * 可将模拟结果输出到 JSON 文件。
* **高度可配置**:
  * 通过 `config.json` 文件可以详细配置环境参数（用户数量、充电桩类型和数量、电网特性、行为模型等）、算法特定参数、日志记录等。
* **详细的日志和结果输出**:
  * 记录详细的系统运行日志和模拟步骤数据。
  * 模拟结果以 JSON 格式保存，便于后续分析和可视化。

## 项目结构

```
Ev-trifocus/
├── algorithms/                  # 存放不同调度算法的实现
│   ├── __init__.py
│   ├── base_scheduler.py      # 调度算法的抽象基类
│   ├── rule_based_scheduler.py  # 基于规则的调度器
│   ├── uncoordinated_scheduler.py # 无序充电调度器
│   ├── marl/                    # MARL 算法包
│   │   ├── __init__.py
│   │   ├── agent.py             # MARL Agent 类
│   │   ├── marl_scheduler.py    # MARL 调度器 (实现 BaseScheduler)
│   │   ├── marl_system.py       # MARL 系统 (管理 Agents)
│   │   └── state_action.py      # MARL 状态/动作/奖励辅助函数
│   └── coordinated_mas/         # Coordinated MAS 算法包
│       ├── __init__.py
│       ├── mas_scheduler.py     # MAS 调度器 (实现 BaseScheduler)
│       └── multi_agent_system_impl.py # MAS 系统、智能体和协调器实现
│       # 可选: 如果 MAS 智能体过大，可以拆分到 agents/ 子目录
│       # ├── agents/
│       # │   ├── __init__.py
│       # │   ├── user_agent.py
│       # │   ├── profit_agent.py
│       # │   └── grid_agent.py
│       # └── coordinator.py
├── core/                        # 存放核心业务逻辑
│   ├── __init__.py
│   ├── environment.py         # ChargingEnvironment 类 (重构后)
│   ├── scheduler_manager.py   # ChargingSchedulerManager 类 (管理算法实例)
│   ├── simulation_runner.py   # SimulationRunner 类 (管理模拟生命周期)
│   ├── station_operations.py  # 充电站操作模拟逻辑
│   ├── system_setup.py        # 系统初始化逻辑
│   └── user_behavior.py       # 用户行为模拟逻辑
│   # └── utils.py             # (可选) 核心工具函数
├── models/                      # 存放机器学习模型文件 (包括 MARL Q-tables)
│   └── marl/                  # (建议) MARL Q 表的子目录
│       └── q_tables.pkl       # (示例)
├── output/                      # 存放模拟结果 JSON 文件
├── routes/                      # 存放 Flask API 蓝图
│   ├── __init__.py
│   ├── config_api.py          # 配置 API
│   ├── data_api.py            # 数据获取 API (用户、充电桩、结果)
│   ├── debug_api.py           # 调试 API
│   ├── recommendation_api.py  # 用户推荐 API
│   ├── simulation_api.py      # 模拟控制 API
│   ├── statistics_api.py      # 统计数据 API
│   └── ui.py                  # HTML 页面路由
├── static/                      # 静态文件 (CSS, JS, Images) - 无需更改
│   ├── css/
│   │   └── style.css
│   ├── js/
│   │   ├── charts.js
│   │   ├── grid-charts.js
│   │   ├── grid.js
│   │   ├── main.js
│   │   ├── operator.js
│   │   └── user.js
│   └── templates/             # HTML 模板 - 无需更改
│       ├── admin.html
│       ├── grid.html
│       ├── index.html
│       ├── operator.html
│       └── user.html
├── app.py                       # Flask 应用入口 (精简后)
├── cli.py                       # 命令行界面入口
├── config.json                  # 配置文件 (包含更多参数)
├── config_manager.py            # 配置加载和管理模块
├── requirements.txt             # Python 依赖
├── ev_model_training.py         # (保留) 深度学习模型训练脚本 (如果仍需)
├── README.md                    # 本文件
└── .gitignore                   # (建议添加) Git 忽略文件
```

* **`algorithms/`**: 包含所有调度算法的模块化实现。每种算法都继承自 `base_scheduler.py` 中的基类。
* **`core/`**: 包含仿真的核心逻辑，如环境定义、模拟运行控制、用户和充电站行为模拟等。
* **`models/`**: 用于存储训练好的机器学习模型，例如 MARL 代理的 Q 表。
* **`output/`**: 默认的模拟结果输出目录。
* **`routes/`**: Flask 应用的 API 路由，按功能组织在不同的蓝图文件中。
* **`static/`**: 包含 Web 界面的所有前端资源（HTML 模板、CSS 样式表、JavaScript 文件）。
* **`app.py`**: Flask Web 应用的主入口点，负责初始化应用和注册蓝图。
* **`cli.py`**: 命令行界面的入口点，用于在无图形界面的情况下运行模拟。
* **`config.json`**: JSON 格式的配置文件，用于定义模拟环境、算法参数等。
* **`config_manager.py`**: 用于加载、合并默认配置和管理 `config.json` 的模块。

## 安装与设置

1. **环境要求**:

   * Python 3.8+ (推荐)
   * pip (Python 包安装器)
2. **克隆仓库** (如果适用):

   ```bash
   git clone <repository_url>
   cd Ev-trifocus
   ```
3. **创建虚拟环境** (推荐):

   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/macOS
   # venv\Scripts\activate    # Windows
   ```
4. **安装依赖**:

   ```bash
   pip install -r requirements.txt
   ```

   (请确保 `requirements.txt` 文件包含了所有必要的库，例如 Flask, NumPy, (可能还有 PyTorch 用于 MARL 或其他模型)。)
5. **配置文件**:

   * 项目首次运行时，如果 `config.json` 文件不存在，系统会根据 `config_manager.py` 中的 `DEFAULT_CONFIG` 自动创建一个。
   * 您可以根据需要编辑 `config.json` 来调整模拟参数。建议先查阅 `config_manager.py` 中的默认配置结构以了解所有可配置项。

## 运行应用

### Web 用户界面

要启动 Web 应用和用户界面，请运行：

```bash
python app.py
```

默认情况下，应用将在 `http://127.0.0.1:5000` 上可用。您可以通过浏览器访问此地址来使用 Web 界面。

### 命令行界面 (CLI)

要通过命令行运行模拟，请使用 `cli.py`。它支持多种参数来覆盖 `config.json` 中的设置。

基本用法:

```bash
python cli.py
```

带参数的示例:

```bash
python cli.py --days 3 --algorithm marl --strategy grid --output results/marl_grid_3days.json
```

可用的命令行参数:

* `--days DAYS`: 模拟运行的天数。
* `--algorithm ALGORITHM`: 要使用的调度算法 (`rule_based`, `marl`, `coordinated_mas`, `uncoordinated`)。
* `--strategy STRATEGY`: 优化策略的名称（对应 `config.json` 中 `strategies` 部分的键，如 `balanced`, `grid`, `profit`, `user`）。这主要影响基于规则和协调式 MAS 算法的权重。
* `--output OUTPUT_PATH`: 保存模拟结果的 JSON 文件路径。
* `--config CONFIG_PATH`: (可选) 指定配置文件的路径 (默认为 `config.json`)。

运行 `python cli.py --help` 查看所有可用选项。

## 配置说明

系统的核心行为和参数通过 `config.json` 文件进行控制。该文件允许用户详细定制：

* **环境参数 (`environment`)**: 用户数量、类型分布、行为模式；充电站数量、充电桩类型和分布、故障率；地图边界；电网基础负载、可再生能源发电曲线、电价时段等。
* **调度器参数 (`scheduler`)**:
  * 选择要使用的 `scheduling_algorithm`。
  * 为每种算法配置特定的参数（例如，`rule_based_params`, `marl_config`, `coordinated_mas_params`）。这包括 MARL 的学习率、探索率、Q 表路径，或基于规则算法的评分权重等。
* **策略权重 (`strategies`)**: 定义不同优化目标（用户满意度、运营商利润、电网友好性）的预设权重组合，可在 UI 或 CLI 中选择。
* **模拟参数 (`simulation_params`)**: 如模拟速度控制相关的默认延迟。
* **日志参数 (`logging`)**: 日志级别和日志文件名。
* **模型训练参数 (`model_training_params`)**: 如果使用 `ev_model_training.py` 训练深度学习模型，相关参数在此定义。

建议在修改配置前备份原始 `config.json` 文件。

## 未来工作与贡献 (可选)

* 实现更复杂的电网动态模型。
* 集成更先进的预测模型（如负载预测、用户行为预测）。
* 扩展 Web 界面的可视化和分析功能。
* 添加更多样化的调度算法进行比较。
* 完善单元测试和集成测试。

欢迎对本项目做出贡献！请参考贡献指南 (如果提供) 或通过 Issue 进行讨论。
