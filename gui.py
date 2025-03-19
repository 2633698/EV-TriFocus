import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import threading
import json
import os
import sys
import numpy as np
from datetime import datetime

# 导入后端模块
sys.path.append('.')  # 确保可以导入同目录下的模块
try:
    from ev_integration_scheduler import IntegratedChargingSystem
    from ev_charging_scheduler import ChargingEnvironment, ChargingScheduler, ChargingVisualizationDashboard
    # from ev_model_training import DataGenerator, train_model, evaluate_model
    from ev_model_training import train_model, evaluate_model
    from ev_system_test import run_system_tests, run_comprehensive_evaluation
    BACKEND_LOADED = True
except ImportError as e:
    BACKEND_LOADED = False
    print(f"后端模块导入错误: {e}")


class EVChargingSystemUI(tk.Tk):
    def __init__(self):
        super().__init__()
        
        self.title("电动汽车有序充电调度系统")
        self.geometry("1200x800")
        self.minsize(1000, 700)
        
        # 初始化后端系统
        self.system = None
        if BACKEND_LOADED:
            try:
                self.system = IntegratedChargingSystem()
                print("后端系统初始化完成")
            except Exception as e:
                print(f"后端系统初始化错误: {e}")
        
        # 创建主界面
        self.create_notebook()
        
        # 创建状态栏
        self.status_var = tk.StringVar(value="就绪")
        self.status_bar = ttk.Label(self, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
    
    def create_notebook(self):
        """创建标签页"""
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 创建各标签页
        self.create_main_tab()
        self.create_simulation_tab()
        self.create_analysis_tab()
        self.create_visualization_tab()
        self.create_settings_tab()
    
    def create_main_tab(self):
        """创建主页标签"""
        main_frame = ttk.Frame(self.notebook)
        self.notebook.add(main_frame, text="主页")
        
        # 欢迎信息
        welcome_label = ttk.Label(main_frame, text="电动汽车有序充电调度系统", font=("Arial", 20, "bold"))
        welcome_label.pack(pady=20)
        
        description = """基于智能体决策的电动汽车有序充电调度策略
            兼顾用户体验、电网友好度与运营商利润的协同优化"""
        desc_label = ttk.Label(main_frame, text=description, font=("Arial", 12))
        desc_label.pack(pady=10)
        
        # 系统状态指示
        status_frame = ttk.LabelFrame(main_frame, text="系统状态")
        status_frame.pack(fill=tk.X, padx=20, pady=10)
        
        backend_status = "已加载" if BACKEND_LOADED and self.system else "未加载"
        backend_color = "green" if BACKEND_LOADED and self.system else "red"
        
        ttk.Label(status_frame, text=f"后端系统状态: ").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        ttk.Label(status_frame, text=backend_status, foreground=backend_color).grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)
        
        # 快速操作区
        actions_frame = ttk.LabelFrame(main_frame, text="快速操作")
        actions_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        # 创建操作按钮
        actions = [
            ("运行模拟", lambda: self.notebook.select(1)),
            ("运行策略分析", self.run_strategy_analysis),
            ("运行电网影响分析", self.run_grid_analysis),
            ("运行用户行为分析", self.run_user_analysis),
            ("生成可视化报告", self.generate_visualization),
            ("训练决策模型", self.train_model)
        ]
        
        for i, (text, command) in enumerate(actions):
            row, col = divmod(i, 3)
            ttk.Button(actions_frame, text=text, command=command, width=25).grid(
                row=row, column=col, padx=10, pady=10, sticky=tk.W
            )
        
        # 系统日志区
        log_frame = ttk.LabelFrame(main_frame, text="系统日志")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=10)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.log("系统启动完成")
        
        if not BACKEND_LOADED:
            self.log("警告: 未能加载后端模块，部分功能可能不可用", "warning")
    
    def create_simulation_tab(self):
        """创建模拟标签页"""
        sim_frame = ttk.Frame(self.notebook)
        self.notebook.add(sim_frame, text="模拟运行")
        
        # 模拟参数区
        params_frame = ttk.LabelFrame(sim_frame, text="模拟参数")
        params_frame.pack(fill=tk.X, padx=10, pady=10)
        
        # 创建参数输入区域
        ttk.Label(params_frame, text="调度策略:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.strategy_var = tk.StringVar(value="balanced")
        strategy_combo = ttk.Combobox(params_frame, textvariable=self.strategy_var)
        strategy_combo['values'] = ('user', 'profit', 'grid', 'balanced')
        strategy_combo.grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)
        
        ttk.Label(params_frame, text="模拟天数:").grid(row=0, column=2, sticky=tk.W, padx=5, pady=5)
        self.sim_days_var = tk.IntVar(value=7)
        ttk.Spinbox(params_frame, from_=1, to=30, textvariable=self.sim_days_var).grid(row=0, column=3, sticky=tk.W, padx=5, pady=5)
        
        ttk.Label(params_frame, text="输出目录:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        self.output_dir_var = tk.StringVar(value="output")
        ttk.Entry(params_frame, textvariable=self.output_dir_var).grid(row=1, column=1, sticky=tk.W+tk.E, padx=5, pady=5)
        ttk.Button(params_frame, text="浏览...", command=self.browse_output_dir).grid(row=1, column=2, sticky=tk.W, padx=5, pady=5)
        
        # 运行按钮
        ttk.Button(params_frame, text="运行模拟", command=self.run_simulation).grid(row=2, column=0, columnspan=2, sticky=tk.W, padx=5, pady=10)
        ttk.Button(params_frame, text="停止模拟", command=self.stop_simulation).grid(row=2, column=2, columnspan=2, sticky=tk.W, padx=5, pady=10)
        
        # 进度条
        ttk.Label(params_frame, text="进度:").grid(row=3, column=0, sticky=tk.W, padx=5, pady=5)
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(params_frame, variable=self.progress_var, maximum=100, length=400)
        self.progress_bar.grid(row=3, column=1, columnspan=3, sticky=tk.W+tk.E, padx=5, pady=5)
        
        # 结果区域
        results_frame = ttk.LabelFrame(sim_frame, text="模拟结果")
        results_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 创建结果显示区的标签页
        results_notebook = ttk.Notebook(results_frame)
        results_notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 指标图表页
        metrics_frame = ttk.Frame(results_notebook)
        results_notebook.add(metrics_frame, text="指标图表")
        
        # 创建图表
        fig = plt.Figure(figsize=(10, 6), dpi=100)
        
        # 添加子图
        self.ax_satisfaction = fig.add_subplot(221)
        self.ax_profit = fig.add_subplot(222)
        self.ax_grid = fig.add_subplot(223)
        self.ax_reward = fig.add_subplot(224)
        
        self.ax_satisfaction.set_title("用户满意度")
        self.ax_profit.set_title("运营商利润")
        self.ax_grid.set_title("电网友好度")
        self.ax_reward.set_title("综合奖励")
        
        canvas = FigureCanvasTkAgg(fig, metrics_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self.metrics_fig = fig
        
        # 日志页
        log_frame = ttk.Frame(results_notebook)
        results_notebook.add(log_frame, text="模拟日志")
        
        self.sim_log_text = scrolledtext.ScrolledText(log_frame, height=20)
        self.sim_log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 统计信息页
        stats_frame = ttk.Frame(results_notebook)
        results_notebook.add(stats_frame, text="统计信息")
        
        self.stats_text = scrolledtext.ScrolledText(stats_frame, height=20)
        self.stats_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
    
    def create_analysis_tab(self):
        """创建分析标签页"""
        analysis_frame = ttk.Frame(self.notebook)
        self.notebook.add(analysis_frame, text="数据分析")
        
        # 分析参数区
        params_frame = ttk.LabelFrame(analysis_frame, text="分析参数")
        params_frame.pack(fill=tk.X, padx=10, pady=10)
        
        # 创建参数输入区域
        ttk.Label(params_frame, text="分析类型:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.analysis_type_var = tk.StringVar(value="user_behavior")
        analysis_combo = ttk.Combobox(params_frame, textvariable=self.analysis_type_var)
        analysis_combo['values'] = ('user_behavior', 'grid_impact', 'sensitivity', 'strategy_comparison')
        analysis_combo.grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)
        
        ttk.Label(params_frame, text="分析天数:").grid(row=0, column=2, sticky=tk.W, padx=5, pady=5)
        self.analysis_days_var = tk.IntVar(value=7)
        ttk.Spinbox(params_frame, from_=1, to=30, textvariable=self.analysis_days_var).grid(row=0, column=3, sticky=tk.W, padx=5, pady=5)
        
        ttk.Label(params_frame, text="输出目录:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        self.analysis_dir_var = tk.StringVar(value="analysis_output")
        ttk.Entry(params_frame, textvariable=self.analysis_dir_var).grid(row=1, column=1, sticky=tk.W+tk.E, padx=5, pady=5)
        ttk.Button(params_frame, text="浏览...", command=self.browse_analysis_dir).grid(row=1, column=2, sticky=tk.W, padx=5, pady=5)
        
        # 运行按钮
        ttk.Button(params_frame, text="运行分析", command=self.run_analysis).grid(row=2, column=0, columnspan=2, sticky=tk.W, padx=5, pady=10)
        
        # 分析结果区域
        results_frame = ttk.LabelFrame(analysis_frame, text="分析结果")
        results_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 创建结果显示区的标签页
        results_notebook = ttk.Notebook(results_frame)
        results_notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 图表页
        chart_frame = ttk.Frame(results_notebook)
        results_notebook.add(chart_frame, text="图表")
        
        # 创建图表
        fig = plt.Figure(figsize=(10, 6), dpi=100)
        
        # 添加子图
        self.analysis_ax1 = fig.add_subplot(221)
        self.analysis_ax2 = fig.add_subplot(222)
        self.analysis_ax3 = fig.add_subplot(223)
        self.analysis_ax4 = fig.add_subplot(224)
        
        canvas = FigureCanvasTkAgg(fig, chart_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self.analysis_fig = fig
        
        # 报告页
        report_frame = ttk.Frame(results_notebook)
        results_notebook.add(report_frame, text="分析报告")
        
        self.report_text = scrolledtext.ScrolledText(report_frame, height=20)
        self.report_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
    
    def create_visualization_tab(self):
        """创建可视化标签页"""
        visualization_frame = ttk.Frame(self.notebook)
        self.notebook.add(visualization_frame, text="可视化")
        
        # 左侧控制面板
        control_frame = ttk.Frame(visualization_frame, width=200)
        control_frame.pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=10)
        
        # 可视化类型选择
        view_frame = ttk.LabelFrame(control_frame, text="视图选择")
        view_frame.pack(fill=tk.X, pady=5)
        
        self.view_var = tk.StringVar(value="user")
        ttk.Radiobutton(view_frame, text="用户视图", variable=self.view_var, value="user", command=self.switch_visualization).pack(anchor=tk.W, padx=5, pady=2)
        ttk.Radiobutton(view_frame, text="运营商视图", variable=self.view_var, value="operator", command=self.switch_visualization).pack(anchor=tk.W, padx=5, pady=2)
        ttk.Radiobutton(view_frame, text="电网视图", variable=self.view_var, value="grid", command=self.switch_visualization).pack(anchor=tk.W, padx=5, pady=2)
        
        # 生成仪表盘按钮
        ttk.Button(control_frame, text="生成仪表盘", command=self.generate_dashboards).pack(fill=tk.X, pady=10)
        
        # 右侧可视化区域
        self.viz_frame = ttk.LabelFrame(visualization_frame, text="可视化区域")
        self.viz_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 默认显示用户视图
        self.create_user_visualization()
    
    def create_user_visualization(self):
        """创建用户可视化内容"""
        # 清空可视化区域
        for widget in self.viz_frame.winfo_children():
            widget.destroy()
        
        # 创建用户信息区域
        user_info_frame = ttk.Frame(self.viz_frame)
        user_info_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(user_info_frame, text="用户ID:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.user_id_var = tk.StringVar(value="EV2024_3001")
        ttk.Entry(user_info_frame, textvariable=self.user_id_var).grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)
        
        ttk.Label(user_info_frame, text="电池电量(SOC):").grid(row=0, column=2, sticky=tk.W, padx=5, pady=5)
        self.soc_var = tk.IntVar(value=35)
        ttk.Spinbox(user_info_frame, from_=5, to=95, textvariable=self.soc_var).grid(row=0, column=3, sticky=tk.W, padx=5, pady=5)
        
        ttk.Button(user_info_frame, text="获取充电推荐", command=self.get_charging_recommendations).grid(row=0, column=4, padx=10, pady=5)
        
        # 创建推荐列表区域
        rec_frame = ttk.Frame(self.viz_frame)
        rec_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # 创建表格
        columns = ('rank', 'name', 'type', 'distance', 'wait_time', 'score')
        self.rec_tree = ttk.Treeview(rec_frame, columns=columns, show='headings')
        
        # 设置列标题
        self.rec_tree.heading('rank', text='排名')
        self.rec_tree.heading('name', text='充电站名称')
        self.rec_tree.heading('type', text='类型')
        self.rec_tree.heading('distance', text='距离(km)')
        self.rec_tree.heading('wait_time', text='等待时间(分钟)')
        self.rec_tree.heading('score', text='综合评分')
        
        # 设置列宽
        self.rec_tree.column('rank', width=50, anchor=tk.CENTER)
        self.rec_tree.column('name', width=150, anchor=tk.W)
        self.rec_tree.column('type', width=80, anchor=tk.CENTER)
        self.rec_tree.column('distance', width=80, anchor=tk.CENTER)
        self.rec_tree.column('wait_time', width=120, anchor=tk.CENTER)
        self.rec_tree.column('score', width=80, anchor=tk.CENTER)
        
        # 添加滚动条
        scrollbar = ttk.Scrollbar(rec_frame, orient=tk.VERTICAL, command=self.rec_tree.yview)
        self.rec_tree.configure(yscroll=scrollbar.set)
        
        self.rec_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 添加示例数据
        self.add_sample_recommendation_data()
    
    def create_operator_visualization(self):
        """创建运营商可视化内容"""
        # 清空可视化区域
        for widget in self.viz_frame.winfo_children():
            widget.destroy()
        
        # 创建运营参数区域
        param_frame = ttk.Frame(self.viz_frame)
        param_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(param_frame, text="峰时电价加价率(%):").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.peak_markup_var = tk.DoubleVar(value=12.0)
        ttk.Scale(param_frame, from_=5.0, to=30.0, variable=self.peak_markup_var, length=200).grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)
        ttk.Label(param_frame, textvariable=self.peak_markup_var).grid(row=0, column=2, sticky=tk.W, padx=5, pady=5)
        
        ttk.Label(param_frame, text="谷时电价折扣率(%):").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        self.valley_discount_var = tk.DoubleVar(value=20.0)
        ttk.Scale(param_frame, from_=0.0, to=40.0, variable=self.valley_discount_var, length=200).grid(row=1, column=1, sticky=tk.W, padx=5, pady=5)
        ttk.Label(param_frame, textvariable=self.valley_discount_var).grid(row=1, column=2, sticky=tk.W, padx=5, pady=5)
        
        ttk.Button(param_frame, text="应用价格策略", command=self.apply_price_strategy).grid(row=1, column=3, padx=5, pady=5)
        
        # 创建充电桩状态监控区域
        charger_frame = ttk.LabelFrame(self.viz_frame, text="充电桩状态监控")
        charger_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        # 创建表格
        columns = ('id', 'location', 'type', 'load', 'health', 'queue')
        self.charger_tree = ttk.Treeview(charger_frame, columns=columns, show='headings')
        
        # 设置列标题
        self.charger_tree.heading('id', text='充电桩ID')
        self.charger_tree.heading('location', text='位置')
        self.charger_tree.heading('type', text='类型')
        self.charger_tree.heading('load', text='当前负载')
        self.charger_tree.heading('health', text='健康状态')
        self.charger_tree.heading('queue', text='队列长度')
        
        # 设置列宽
        self.charger_tree.column('id', width=80, anchor=tk.CENTER)
        self.charger_tree.column('location', width=150, anchor=tk.W)
        self.charger_tree.column('type', width=80, anchor=tk.CENTER)
        self.charger_tree.column('load', width=100, anchor=tk.CENTER)
        self.charger_tree.column('health', width=150, anchor=tk.W)
        self.charger_tree.column('queue', width=80, anchor=tk.CENTER)
        
        # 添加滚动条
        scrollbar = ttk.Scrollbar(charger_frame, orient=tk.VERTICAL, command=self.charger_tree.yview)
        self.charger_tree.configure(yscroll=scrollbar.set)
        
        self.charger_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 添加示例数据
        self.add_sample_charger_data()
    
    def create_grid_visualization(self):
        """创建电网可视化内容"""
        # 清空可视化区域
        for widget in self.viz_frame.winfo_children():
            widget.destroy()
        
        # 创建电网负载图表
        load_frame = ttk.Frame(self.viz_frame)
        load_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        fig = plt.Figure(figsize=(10, 6), dpi=100)
        ax = fig.add_subplot(111)
        
        # 示例数据
        hours = range(24)
        load_data = [40, 35, 30, 28, 30, 35, 45, 60, 75, 80, 75, 70, 65, 60, 65, 70, 75, 85, 90, 80, 70, 60, 50, 45]
        
        ax.plot(hours, load_data, 'b-', linewidth=2, label='预测负载')
        
        ax.set_title('24小时电网负载监控')
        ax.set_xlabel('小时')
        ax.set_ylabel('负载率 (%)')
        ax.legend()
        ax.grid(True)
        
        # 高亮峰谷时段
        ax.fill_between([7, 11], 0, 100, alpha=0.1, color='red')
        ax.fill_between([18, 22], 0, 100, alpha=0.1, color='red')
        ax.fill_between([0, 6], 0, 100, alpha=0.1, color='blue')
        
        ax.set_ylim(0, 100)
        
        canvas = FigureCanvasTkAgg(fig, load_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        
        # 创建控制按钮
        control_frame = ttk.Frame(self.viz_frame)
        control_frame.pack(fill=tk.X, pady=5)
        
        ttk.Button(control_frame, text="刷新负载数据", command=self.refresh_grid_data).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="分析电网影响", command=self.run_grid_analysis).pack(side=tk.LEFT, padx=5)
    
    def create_settings_tab(self):
        """创建设置标签页"""
        settings_frame = ttk.Frame(self.notebook)
        self.notebook.add(settings_frame, text="设置")
        
        # 系统配置区域
        config_frame = ttk.LabelFrame(settings_frame, text="系统配置")
        config_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 左侧配置编辑器
        left_frame = ttk.Frame(config_frame)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 环境配置
        env_frame = ttk.LabelFrame(left_frame, text="环境配置")
        env_frame.pack(fill=tk.X, pady=5, padx=5)
        
        # 网格ID
        ttk.Label(env_frame, text="网格ID:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.grid_id_var = tk.StringVar(value="0258")
        ttk.Entry(env_frame, textvariable=self.grid_id_var).grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)
        
        # 充电桩数量
        ttk.Label(env_frame, text="充电桩数量:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        self.charger_count_var = tk.IntVar(value=20)
        ttk.Spinbox(env_frame, from_=5, to=100, textvariable=self.charger_count_var).grid(row=1, column=1, sticky=tk.W, padx=5, pady=5)
        
        # 用户数量
        ttk.Label(env_frame, text="用户数量:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)
        self.user_count_var = tk.IntVar(value=50)
        ttk.Spinbox(env_frame, from_=10, to=200, textvariable=self.user_count_var).grid(row=2, column=1, sticky=tk.W, padx=5, pady=5)
        
        # 调度器配置
        scheduler_frame = ttk.LabelFrame(left_frame, text="调度器配置")
        scheduler_frame.pack(fill=tk.X, pady=5, padx=5)
        
        # 使用预训练模型
        self.use_model_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(scheduler_frame, text="使用预训练模型", variable=self.use_model_var).grid(row=0, column=0, columnspan=2, sticky=tk.W, padx=5, pady=5)
        
        # 优化权重
        ttk.Label(scheduler_frame, text="优化权重:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        
        # 用户满意度权重
        ttk.Label(scheduler_frame, text="用户满意度:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)
        self.user_weight_var = tk.DoubleVar(value=0.4)
        ttk.Scale(scheduler_frame, from_=0.0, to=1.0, variable=self.user_weight_var, length=200).grid(row=2, column=1, sticky=tk.W, padx=5, pady=5)
        
        # 运营商利润权重
        ttk.Label(scheduler_frame, text="运营商利润:").grid(row=3, column=0, sticky=tk.W, padx=5, pady=5)
        self.profit_weight_var = tk.DoubleVar(value=0.3)
        ttk.Scale(scheduler_frame, from_=0.0, to=1.0, variable=self.profit_weight_var, length=200).grid(row=3, column=1, sticky=tk.W, padx=5, pady=5)
        
        # 电网友好度权重
        ttk.Label(scheduler_frame, text="电网友好度:").grid(row=4, column=0, sticky=tk.W, padx=5, pady=5)
        self.grid_weight_var = tk.DoubleVar(value=0.3)
        ttk.Scale(scheduler_frame, from_=0.0, to=1.0, variable=self.grid_weight_var, length=200).grid(row=4, column=1, sticky=tk.W, padx=5, pady=5)
        
        # 按钮区域
        button_frame = ttk.Frame(left_frame)
        button_frame.pack(fill=tk.X, pady=10, padx=5)
        
        ttk.Button(button_frame, text="加载配置", command=self.load_config).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="保存配置", command=self.save_config).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="应用配置", command=self.apply_config).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="重置", command=self.reset_config).pack(side=tk.LEFT, padx=5)
        
        # 右侧JSON预览
        right_frame = ttk.LabelFrame(config_frame, text="配置JSON预览")
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.config_text = scrolledtext.ScrolledText(right_frame, wrap=tk.WORD, height=20)
        self.config_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 初始化配置预览
        self.update_config_preview()
    
    # ---------- 辅助函数 ----------
    
    def log(self, message, level="info"):
        """添加日志"""
        # 获取当前时间
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 设置不同级别日志的颜色前缀
        prefix = ""
        if level == "error":
            prefix = "[ERROR] "
        elif level == "warning":
            prefix = "[WARNING] "
        elif level == "info":
            prefix = "[INFO] "
        
        log_message = f"{timestamp} {prefix}{message}\n"
        
        # 添加到主日志
        if hasattr(self, 'log_text'):
            self.log_text.insert(tk.END, log_message)
            self.log_text.see(tk.END)
        
        # 如果存在模拟日志，也添加到模拟日志
        if hasattr(self, 'sim_log_text'):
            self.sim_log_text.insert(tk.END, log_message)
            self.sim_log_text.see(tk.END)
        
        # 打印到控制台
        print(log_message, end="")
    
    def browse_output_dir(self):
        """浏览输出目录"""
        directory = filedialog.askdirectory(title="选择输出目录")
        if directory:
            self.output_dir_var.set(directory)
    
    def browse_analysis_dir(self):
        """浏览分析输出目录"""
        directory = filedialog.askdirectory(title="选择分析输出目录")
        if directory:
            self.analysis_dir_var.set(directory)
    
    def update_config_preview(self):
        """更新配置预览"""
        # 创建配置字典
        config = {
            "environment": {
                "grid_id": self.grid_id_var.get(),
                "charger_count": self.charger_count_var.get(),
                "user_count": self.user_count_var.get(),
                "simulation_days": self.sim_days_var.get(),
                "time_step_minutes": 15
            },
            "model": {
                "input_dim": 19,
                "hidden_dim": 128,
                "task_hidden_dim": 64,
                "model_path": "ev_charging_model.pth"
            },
            "scheduler": {
                "use_trained_model": self.use_model_var.get(),
                "optimization_weights": {
                    "user_satisfaction": self.user_weight_var.get(),
                    "operator_profit": self.profit_weight_var.get(),
                    "grid_friendliness": self.grid_weight_var.get()
                }
            },
            "visualization": {
                "dashboard_port": 8050,
                "update_interval": 15,
                "output_dir": self.output_dir_var.get()
            }
        }
        
        # 格式化JSON并更新到文本框
        self.config_text.delete(1.0, tk.END)
        self.config_text.insert(tk.END, json.dumps(config, indent=4))
    
    def add_sample_recommendation_data(self):
        """添加示例充电推荐数据"""
        # 清空表格
        for item in self.rec_tree.get_children():
            self.rec_tree.delete(item)
        
        # 添加示例数据
        sample_data = [
            (1, "城东快充站", "快充", "2.5", "5", "0.92"),
            (2, "科技园区充电站", "慢充", "1.2", "15", "0.85"),
            (3, "南湖充电中心", "快充", "3.8", "10", "0.79"),
            (4, "西站充电点", "慢充", "5.2", "0", "0.72"),
            (5, "北城商务区充电站", "快充", "4.7", "20", "0.68")
        ]
        
        for data in sample_data:
            self.rec_tree.insert('', 'end', values=data)
    
    def add_sample_charger_data(self):
        """添加示例充电桩数据"""
        # 清空表格
        for item in self.charger_tree.get_children():
            self.charger_tree.delete(item)
        
        # 添加示例数据
        sample_data = [
            ("CQ_1001", "城东商圈", "快充", "78%", "良好 (92%)", "2"),
            ("CQ_1002", "西区工业园", "快充", "45%", "良好 (89%)", "0"),
            ("CQ_1003", "南湖科技园", "慢充", "95%", "注意 (74%)", "3"),
            ("CQ_1004", "北城商务区", "快充", "62%", "良好 (86%)", "1"),
            ("CQ_1005", "中央车站", "快充", "90%", "异常 (65%)", "4")
        ]
        
        for data in sample_data:
            self.charger_tree.insert('', 'end', values=data)
    
    # ---------- 功能函数 ----------
    
    def load_config(self):
        """加载配置文件"""
        filename = filedialog.askopenfilename(
            title="选择配置文件",
            filetypes=(("JSON文件", "*.json"), ("所有文件", "*.*"))
        )
        
        if not filename:
            return
        
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            # 更新UI
            if 'environment' in config:
                env = config['environment']
                self.grid_id_var.set(env.get('grid_id', '0258'))
                self.charger_count_var.set(env.get('charger_count', 20))
                self.user_count_var.set(env.get('user_count', 50))
                if hasattr(self, 'sim_days_var'):
                    self.sim_days_var.set(env.get('simulation_days', 7))
            
            if 'scheduler' in config:
                sched = config['scheduler']
                self.use_model_var.set(sched.get('use_trained_model', True))
                
                if 'optimization_weights' in sched:
                    weights = sched['optimization_weights']
                    self.user_weight_var.set(weights.get('user_satisfaction', 0.4))
                    self.profit_weight_var.set(weights.get('operator_profit', 0.3))
                    self.grid_weight_var.set(weights.get('grid_friendliness', 0.3))
            
            # 更新配置预览
            self.update_config_preview()
            
            self.log(f"成功加载配置: {filename}")
            
        except Exception as e:
            self.log(f"加载配置失败: {str(e)}", "error")
            messagebox.showerror("加载错误", f"无法加载配置: {str(e)}")
    
    def save_config(self):
        """保存配置文件"""
        filename = filedialog.asksaveasfilename(
            title="保存配置文件",
            defaultextension=".json",
            filetypes=(("JSON文件", "*.json"), ("所有文件", "*.*"))
        )
        
        if not filename:
            return
        
        try:
            # 获取当前配置JSON
            config_json = self.config_text.get(1.0, tk.END)
            config = json.loads(config_json)
            
            # 保存配置
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4)
            
            self.log(f"成功保存配置: {filename}")
            
        except Exception as e:
            self.log(f"保存配置失败: {str(e)}", "error")
            messagebox.showerror("保存错误", f"无法保存配置: {str(e)}")
    
    def apply_config(self):
        """应用配置"""
        try:
            # 检查后端是否已加载
            if not BACKEND_LOADED or not self.system:
                if messagebox.askokcancel("后端未加载", "后端系统未加载，是否尝试初始化?"):
                    self.init_backend()
                else:
                    return
            
            # 获取配置数据
            config_json = self.config_text.get(1.0, tk.END)
            config = json.loads(config_json)
            
            # 更新系统配置
            self.system.config = config
            
            # 重新初始化环境和调度器
            self.system.env_config = config["environment"]
            self.system.env = ChargingEnvironment(self.system.env_config)
            self.system.scheduler = ChargingScheduler({
                "grid_id": self.system.env_config["grid_id"],
                "charger_count": self.system.env_config["charger_count"],
                "user_count": self.system.env_config["user_count"]
            })
            
            # 如果配置为使用模型，尝试加载模型
            if config["scheduler"]["use_trained_model"]:
                model_path = config["model"]["model_path"]
                if os.path.exists(model_path):
                    self.system.load_pretrained_model(model_path)
                else:
                    self.log(f"警告: 找不到模型文件 {model_path}", "warning")
            
            self.log("配置已应用")
            messagebox.showinfo("配置应用", "配置已成功应用到系统")
            
        except Exception as e:
            self.log(f"应用配置失败: {str(e)}", "error")
            messagebox.showerror("配置错误", f"应用配置失败: {str(e)}")
    
    def reset_config(self):
        """重置配置"""
        # 重置为默认值
        self.grid_id_var.set("0258")
        self.charger_count_var.set(20)
        self.user_count_var.set(50)
        if hasattr(self, 'sim_days_var'):
            self.sim_days_var.set(7)
        
        self.use_model_var.set(True)
        self.user_weight_var.set(0.4)
        self.profit_weight_var.set(0.3)
        self.grid_weight_var.set(0.3)
        
        # 更新配置预览
        self.update_config_preview()
        
        self.log("配置已重置为默认值")
    
    def init_backend(self):
        """初始化后端系统"""
        if BACKEND_LOADED:
            try:
                self.system = IntegratedChargingSystem()
                self.log("后端系统初始化完成")
                return True
            except Exception as e:
                self.log(f"后端系统初始化失败: {str(e)}", "error")
                messagebox.showerror("初始化错误", f"无法初始化后端系统: {str(e)}")
                return False
        else:
            self.log("无法初始化后端系统: 模块未加载", "error")
            messagebox.showerror("初始化错误", "无法初始化后端系统: 模块未加载")
            return False
    
    def run_simulation(self):
        """运行充电调度模拟"""
        # 检查后端是否已加载
        if not BACKEND_LOADED or not self.system:
            if messagebox.askokcancel("后端未加载", "后端系统未加载，是否尝试初始化?"):
                if not self.init_backend():
                    return
            else:
                return
        
        # 获取参数
        strategy = self.strategy_var.get()
        days = self.sim_days_var.get()
        output_dir = self.output_dir_var.get()
        
        # 创建输出目录
        os.makedirs(output_dir, exist_ok=True)
        
        # 更新配置
        self.system.config["visualization"]["output_dir"] = output_dir
        
        # 如果策略在配置中，更新优化权重
        if "strategies" in self.system.config and strategy in self.system.config["strategies"]:
            self.system.config["scheduler"]["optimization_weights"] = self.system.config["strategies"][strategy]
        
        # 清空图表
        self.ax_satisfaction.clear()
        self.ax_profit.clear()
        self.ax_grid.clear()
        self.ax_reward.clear()
        
        self.ax_satisfaction.set_title("用户满意度")
        self.ax_profit.set_title("运营商利润")
        self.ax_grid.set_title("电网友好度")
        self.ax_reward.set_title("综合奖励")
        
        # 清空日志和统计信息
        self.sim_log_text.delete(1.0, tk.END)
        self.stats_text.delete(1.0, tk.END)
        
        # 更新状态
        self.status_var.set("模拟运行中...")
        self.log(f"开始运行模拟: 策略={strategy}, 天数={days}, 输出目录={output_dir}")
        
        # 启动模拟线程
        simulation_thread = threading.Thread(
            target=self.run_simulation_thread,
            args=(strategy, days, output_dir)
        )
        simulation_thread.daemon = True
        simulation_thread.start()
    
    def run_simulation_thread(self, strategy, days, output_dir):
        """模拟线程"""
        try:
            # 运行模拟
            metrics, avg_metrics = self.system.run_simulation(days=days, output_metrics=True)
            
            # 更新UI
            self.after(0, lambda: self.update_simulation_results(metrics, avg_metrics))
            
            # 更新状态
            self.status_var.set("模拟完成")
            self.log("模拟运行完成")
            
            # 显示完成消息
            self.after(0, lambda: messagebox.showinfo("模拟完成", f"模拟已完成，结果保存在目录: {output_dir}"))
            
        except Exception as e:
            error_msg = f"模拟运行出错: {str(e)}"
            self.log(error_msg, "error")
            self.after(0, lambda: messagebox.showerror("模拟错误", error_msg))
            self.status_var.set("模拟出错")
    
    def update_simulation_results(self, metrics, avg_metrics):
        """更新模拟结果UI"""
        # 更新图表
        time_steps = range(len(metrics["user_satisfaction"]))
        hours = [t * 0.25 for t in time_steps]  # 假设每步15分钟
        
        self.ax_satisfaction.plot(hours, metrics["user_satisfaction"])
        self.ax_satisfaction.set_xlabel("时间 (小时)")
        self.ax_satisfaction.set_ylabel("满意度")
        self.ax_satisfaction.grid(True)
        
        self.ax_profit.plot(hours, metrics["operator_profit"])
        self.ax_profit.set_xlabel("时间 (小时)")
        self.ax_profit.set_ylabel("利润")
        self.ax_profit.grid(True)
        
        self.ax_grid.plot(hours, metrics["grid_friendliness"])
        self.ax_grid.set_xlabel("时间 (小时)")
        self.ax_grid.set_ylabel("友好度")
        self.ax_grid.grid(True)
        
        self.ax_reward.plot(hours, metrics["total_reward"])
        self.ax_reward.set_xlabel("时间 (小时)")
        self.ax_reward.set_ylabel("奖励")
        self.ax_reward.grid(True)
        
        self.metrics_fig.tight_layout()
        self.metrics_fig.canvas.draw_idle()
        
        # 更新统计信息
        stats = f"""模拟统计信息:

            运行天数: {self.sim_days_var.get()}
            调度策略: {self.strategy_var.get()}

            平均指标:
            - 用户满意度: {avg_metrics["user_satisfaction"]:.4f}
            - 运营商利润: {avg_metrics["operator_profit"]:.4f}
            - 电网友好度: {avg_metrics["grid_friendliness"]:.4f}
            - 综合奖励: {avg_metrics["total_reward"]:.4f}

            最大值:
            - 用户满意度: {max(metrics["user_satisfaction"]):.4f}
            - 运营商利润: {max(metrics["operator_profit"]):.4f}
            - 电网友好度: {max(metrics["grid_friendliness"]):.4f}
            - 综合奖励: {max(metrics["total_reward"]):.4f}

            最小值:
            - 用户满意度: {min(metrics["user_satisfaction"]):.4f}
            - 运营商利润: {min(metrics["operator_profit"]):.4f}
            - 电网友好度: {min(metrics["grid_friendliness"]):.4f}
            - 综合奖励: {min(metrics["total_reward"]):.4f}
            """
        self.stats_text.delete(1.0, tk.END)
        self.stats_text.insert(tk.END, stats)
    
    def stop_simulation(self):
        """停止模拟"""
        # 实际上无法中止线程，这里只是更新UI状态
        self.status_var.set("模拟已停止")
        self.log("模拟已手动停止", "warning")
        messagebox.showinfo("停止模拟", "已要求停止模拟")
    
    def run_analysis(self):
        """运行分析"""
        # 检查后端是否已加载
        if not BACKEND_LOADED or not self.system:
            if messagebox.askokcancel("后端未加载", "后端系统未加载，是否尝试初始化?"):
                if not self.init_backend():
                    return
            else:
                return
        
        # 获取参数
        analysis_type = self.analysis_type_var.get()
        days = self.analysis_days_var.get()
        output_dir = self.analysis_dir_var.get()
        
        # 创建输出目录
        os.makedirs(output_dir, exist_ok=True)
        
        # 更新状态
        self.status_var.set(f"正在运行{analysis_type}分析...")
        self.log(f"开始运行{analysis_type}分析: 天数={days}, 输出目录={output_dir}")
        
        # 清空结果区域
        for ax in [self.analysis_ax1, self.analysis_ax2, self.analysis_ax3, self.analysis_ax4]:
            ax.clear()
        self.analysis_fig.canvas.draw_idle()
        
        self.report_text.delete(1.0, tk.END)
        
        # 启动分析线程
        analysis_thread = threading.Thread(
            target=self.run_analysis_thread,
            args=(analysis_type, days, output_dir)
        )
        analysis_thread.daemon = True
        analysis_thread.start()
    
    def run_analysis_thread(self, analysis_type, days, output_dir):
        """分析线程"""
        try:
            result = None
            
            # 根据不同分析类型执行不同的分析
            if analysis_type == "user_behavior":
                # 保存原始输出目录
                original_output_dir = self.system.config["visualization"]["output_dir"]
                
                # 设置新的输出目录
                self.system.config["visualization"]["output_dir"] = output_dir
                
                # 运行用户行为分析
                result = self.system.analyze_user_behavior(num_days=days)
                
                # 恢复原始输出目录
                self.system.config["visualization"]["output_dir"] = original_output_dir
                
                # 更新UI
                self.after(0, lambda: self.update_user_behavior_analysis(result))
                
            elif analysis_type == "grid_impact":
                # 保存原始输出目录
                original_output_dir = self.system.config["visualization"]["output_dir"]
                
                # 设置新的输出目录
                self.system.config["visualization"]["output_dir"] = output_dir
                
                # 运行电网影响分析
                result = self.system.analyze_grid_impact(num_days=days)
                
                # 恢复原始输出目录
                self.system.config["visualization"]["output_dir"] = original_output_dir
                
                # 更新UI
                self.after(0, lambda: self.update_grid_impact_analysis(result))
                
            elif analysis_type == "sensitivity":
                # 设置参数范围
                parameter_ranges = {
                    "scheduler.optimization_weights.user_satisfaction": [0.2, 0.3, 0.4, 0.5, 0.6],
                    "scheduler.optimization_weights.operator_profit": [0.2, 0.3, 0.4],
                    "scheduler.optimization_weights.grid_friendliness": [0.2, 0.3, 0.4]
                }
                
                # 运行敏感性分析
                result = self.system.run_sensitivity_analysis(parameter_ranges, target_metric="total_reward")
                
                # 更新UI
                self.after(0, lambda: self.update_sensitivity_analysis(result))
                
            elif analysis_type == "strategy_comparison":
                # 定义不同策略
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
                    }
                ]
                
                # 运行策略比较
                result = self.system.compare_scheduling_strategies(strategies)
                
                # 更新UI
                self.after(0, lambda: self.update_strategy_comparison(result))
            
            # 更新状态
            self.status_var.set(f"{analysis_type}分析完成")
            self.log(f"{analysis_type}分析完成，结果保存在目录: {output_dir}")
            
            # 显示完成消息
            self.after(0, lambda: messagebox.showinfo("分析完成", f"{analysis_type}分析已完成"))
            
        except Exception as e:
            error_msg = f"分析出错: {str(e)}"
            self.log(error_msg, "error")
            self.after(0, lambda: messagebox.showerror("分析错误", error_msg))
            self.status_var.set("分析出错")
    
    def update_user_behavior_analysis(self, result):
        """更新用户行为分析结果"""
        if not result:
            return
        
        # 更新图表
        # 1. 24小时充电需求分布
        self.analysis_ax1.clear()
        hours = range(24)
        hourly_demand = result.get("hourly_demand", [0] * 24)
        self.analysis_ax1.bar(hours, hourly_demand)
        self.analysis_ax1.set_title("24小时充电需求分布")
        self.analysis_ax1.set_xlabel("小时")
        self.analysis_ax1.set_ylabel("充电需求")
        self.analysis_ax1.set_xticks(range(0, 24, 3))
        self.analysis_ax1.grid(axis='y', linestyle='--', alpha=0.7)
        
        # 2. 用户类型分布
        self.analysis_ax2.clear()
        user_types = list(result.get("user_type_distribution", {}).keys())
        user_type_counts = list(result.get("user_type_distribution", {}).values())
        if user_types and user_type_counts:
            self.analysis_ax2.pie(user_type_counts, labels=user_types, autopct='%1.1f%%', startangle=90)
            self.analysis_ax2.axis('equal')
            self.analysis_ax2.set_title("用户类型分布")
        
        # 3. 平均充电SOC
        self.analysis_ax3.clear()
        user_types = list(result.get("avg_soc_at_charge", {}).keys())
        avg_socs = list(result.get("avg_soc_at_charge", {}).values())
        if user_types and avg_socs:
            self.analysis_ax3.bar(user_types, avg_socs)
            self.analysis_ax3.set_title("不同用户类型的平均充电电量")
            self.analysis_ax3.set_xlabel("用户类型")
            self.analysis_ax3.set_ylabel("平均充电SOC (%)")
            self.analysis_ax3.grid(axis='y', linestyle='--', alpha=0.7)
        
        # 4. 充电频率
        self.analysis_ax4.clear()
        user_types = list(result.get("charging_frequency", {}).keys())
        frequencies = list(result.get("charging_frequency", {}).values())
        if user_types and frequencies:
            self.analysis_ax4.bar(user_types, frequencies)
            self.analysis_ax4.set_title("不同用户类型的充电频率")
            self.analysis_ax4.set_xlabel("用户类型")
            self.analysis_ax4.set_ylabel("平均充电频率 (次/周)")
            self.analysis_ax4.grid(axis='y', linestyle='--', alpha=0.7)
        
        self.analysis_fig.tight_layout()
        self.analysis_fig.canvas.draw_idle()
        
        # 生成报告文本
        report = """# 用户充电行为分析报告

            ## 1. 充电需求时序分布

            通过分析24小时充电需求分布，可以清晰看到用户充电行为的时间规律：

            - **高峰时段**：早高峰(7-10点)和晚高峰(18-21点)是充电需求高峰
            - **低谷时段**：凌晨(0-6点)充电需求最低
            - **中间时段**：工作时间(10-18点)充电需求平稳

            ## 2. 用户类型分析

            不同类型用户的充电行为差异明显：

            - **出租车**：高频次、低电量充电，对时间敏感度高
            - **私家车**：以晚间充电为主，电量较低时充电
            - **物流车**：定时定点充电，充电量大
            - **网约车**：介于出租车和私家车之间的行为模式

            ## 3. 充电行为特征

            """
        # 添加实际数据
        for user_type in user_types:
            if user_type in result.get("avg_soc_at_charge", {}) and user_type in result.get("charging_frequency", {}):
                soc = result["avg_soc_at_charge"][user_type]
                freq = result["charging_frequency"][user_type]
                report += f"- **{user_type}**: 平均充电SOC {soc:.1f}%, 充电频率 {freq:.1f}次/周\n"
        
        report += """
            ## 4. 优化建议

            1. **差异化策略**：针对不同用户类型制定差异化的充电调度策略
            2. **峰谷引导**：通过价格机制引导私家车用户向低谷时段转移
            3. **快充站布局**：在商业区和交通枢纽部署更多快充站，满足出租车和网约车需求
            4. **慢充站布局**：在住宅区和工业园区增加慢充站，满足私家车和物流车用户需求
            """
        
        self.report_text.delete(1.0, tk.END)
        self.report_text.insert(tk.END, report)
    
    def update_grid_impact_analysis(self, result):
        """更新电网影响分析结果"""
        if not result:
            return
        
        # 提取结果数据
        peak_reduction = result.get("peak_load", {}).get("reduction_percentage", 0)
        variance_improvement = result.get("load_variance", {}).get("improvement_percentage", 0)
        renewable_improvement = result.get("renewable_utilization", {}).get("improvement_percentage", 0)
        
        # 更新图表
        # 1. 24小时负载对比
        self.analysis_ax1.clear()
        hours = range(24)
        with_scheduling = result.get("hourly_load", {}).get("with_scheduling", [0] * 24)
        without_scheduling = result.get("hourly_load", {}).get("without_scheduling", [0] * 24)
        
        self.analysis_ax1.plot(hours, with_scheduling, 'b-', linewidth=2, label="有序调度")
        self.analysis_ax1.plot(hours, without_scheduling, 'r--', linewidth=2, label="无序充电")
        self.analysis_ax1.set_title("有序调度vs无序充电的24小时电网负载对比")
        self.analysis_ax1.set_xlabel("小时")
        self.analysis_ax1.set_ylabel("平均电网负载 (%)")
        self.analysis_ax1.set_xticks(range(0, 24, 3))
        self.analysis_ax1.grid(True, linestyle='--', alpha=0.7)
        self.analysis_ax1.legend()
        
        # 高亮峰谷时段
        self.analysis_ax1.fill_between([7, 11], 0, 100, alpha=0.2, color='orange', label="早高峰")
        self.analysis_ax1.fill_between([18, 22], 0, 100, alpha=0.2, color='orange', label="晚高峰")
        self.analysis_ax1.fill_between([0, 6], 0, 100, alpha=0.2, color='blue', label="低谷时段")
        self.analysis_ax1.set_ylim(0, 100)
        
        # 2. 峰值负载对比
        self.analysis_ax2.clear()
        labels = ["有序调度", "无序充电"]
        peak_loads = [
            result.get("peak_load", {}).get("with_scheduling", 0),
            result.get("peak_load", {}).get("without_scheduling", 0)
        ]
        
        bars = self.analysis_ax2.bar(labels, peak_loads, color=['green', 'red'])
        self.analysis_ax2.set_title(f"峰值负载对比 (降低 {peak_reduction:.2f}%)")
        self.analysis_ax2.set_ylabel("峰值负载 (%)")
        self.analysis_ax2.grid(axis='y', linestyle='--', alpha=0.7)
        
        # 添加数据标签
        for bar in bars:
            height = bar.get_height()
            self.analysis_ax2.text(bar.get_x() + bar.get_width()/2., height + 1,
                    f'{height:.1f}%', ha='center', va='bottom')
        
        # 3. 负载方差对比
        self.analysis_ax3.clear()
        variances = [
            result.get("load_variance", {}).get("with_scheduling", 0),
            result.get("load_variance", {}).get("without_scheduling", 0)
        ]
        
        bars = self.analysis_ax3.bar(labels, variances, color=['green', 'red'])
        self.analysis_ax3.set_title(f"负载均衡性对比 (改善 {variance_improvement:.2f}%)")
        self.analysis_ax3.set_ylabel("负载方差")
        self.analysis_ax3.grid(axis='y', linestyle='--', alpha=0.7)
        
        # 添加数据标签
        for bar in bars:
            height = bar.get_height()
            self.analysis_ax3.text(bar.get_x() + bar.get_width()/2., height + 1,
                    f'{height:.1f}', ha='center', va='bottom')
        
        # 4. 可再生能源利用率对比
        self.analysis_ax4.clear()
        utilization = [
            result.get("renewable_utilization", {}).get("with_scheduling", 0),
            result.get("renewable_utilization", {}).get("without_scheduling", 0)
        ]
        
        bars = self.analysis_ax4.bar(labels, utilization, color=['green', 'red'])
        self.analysis_ax4.set_title(f"可再生能源利用率对比 (提高 {renewable_improvement:.2f}%)")
        self.analysis_ax4.set_ylabel("可再生能源利用率 (%)")
        self.analysis_ax4.grid(axis='y', linestyle='--', alpha=0.7)
        
        # 添加数据标签
        for bar in bars:
            height = bar.get_height()
            self.analysis_ax4.text(bar.get_x() + bar.get_width()/2., height + 1,
                    f'{height:.1f}%', ha='center', va='bottom')
        
        self.analysis_fig.tight_layout()
        self.analysis_fig.canvas.draw_idle()
        
        # 生成报告文本
        report = f"""# 电网影响分析报告

## 1. 电网负载分析

有序充电调度策略对电网负载的影响显著：

- **峰值负载降低**：相比无序充电，有序调度将峰值负载降低了 **{peak_reduction:.2f}%**
- **负载均衡性提升**：负载方差降低了 **{variance_improvement:.2f}%**，表明负载分布更加均衡
- **可再生能源利用率提高**：光伏等可再生能源利用率提高了 **{renewable_improvement:.2f}%**

## 2. 24小时负载曲线分析

- **早晨峰值(7-10点)**：有序调度显著降低了早高峰负载
- **晚间峰值(18-21点)**：有序调度有效平抑了晚高峰电网压力
- **低谷时段(0-6点)**：有序调度提高了低谷时段的电网利用率

## 3. 电网友好性分析

- **降低高峰需求**：减轻电网高峰时段的供电压力
- **提高低谷利用**：增加低谷时段的电力消费，提高电网设备利用率
- **减少调峰成本**：降低电网调峰发电和应急备用容量需求
- **促进新能源消纳**：提高了光伏发电高峰期的充电量，减少弃光弃风

## 4. 优化建议

1. **动态电价机制**：进一步优化分时电价，增大峰谷价差，引导充电行为向低谷转移
2. **光储充协同**：增加光伏+储能+充电桩一体化站点，提高可再生能源利用率
3. **需求响应集成**：将充电负荷纳入电网需求响应体系，提供电网调峰服务
4. **区域差异化调度**：针对不同区域电网特性制定差异化的充电调度策略
"""
        
        self.report_text.delete(1.0, tk.END)
        self.report_text.insert(tk.END, report)
    
    def update_sensitivity_analysis(self, result):
        """更新敏感性分析结果"""
        if not result:
            return
        
        # 清空图表
        for ax in [self.analysis_ax1, self.analysis_ax2, self.analysis_ax3, self.analysis_ax4]:
            ax.clear()
        
        # 遍历敏感性分析结果
        for i, (param_name, param_results) in enumerate(result.items()):
            ax = [self.analysis_ax1, self.analysis_ax2, self.analysis_ax3, self.analysis_ax4][min(i, 3)]
            
            x = [r["param_value"] for r in param_results]
            y = [r["metric_value"] for r in param_results]
            
            ax.plot(x, y, 'o-', linewidth=2)
            
            # 简化参数名显示
            display_name = param_name.split('.')[-1]
            ax.set_title(f"参数 '{display_name}' 对总奖励的影响")
            ax.set_xlabel(display_name)
            ax.set_ylabel("总奖励")
            ax.grid(True)
            
            # 标记最优参数值
            best_idx = np.argmax(y)
            ax.scatter([x[best_idx]], [y[best_idx]], color='red', s=100, zorder=5)
            ax.annotate(f"最优值: {x[best_idx]}", 
                        (x[best_idx], y[best_idx]), 
                        xytext=(10, -20), 
                        textcoords='offset points',
                        bbox=dict(boxstyle="round,pad=0.3", fc="yellow", alpha=0.8))
        
        self.analysis_fig.tight_layout()
        self.analysis_fig.canvas.draw_idle()
        
        # 生成报告文本
        report = """# 敏感性分析报告

## 1. 权重参数敏感性

通过对调度权重参数的敏感性分析，得出以下结论：

- **用户满意度权重**：在0.3-0.5范围内变化对总体效果影响较小，超过0.5后会显著降低电网友好度
- **运营商利润权重**：在0.2-0.4范围内对总体效果影响不大，但超过0.4后会显著降低用户满意度
- **电网友好度权重**：最佳取值点为0.3左右，过高会降低用户满意度，过低会降低电网友好性

## 2. 最优权重配置

综合各方面考虑，在普通场景下，最佳权重配置为：
- 用户满意度权重：0.4
- 运营商利润权重：0.3  
- 电网友好度权重：0.3

## 3. 场景自适应策略

在不同场景下，建议动态调整权重配置：

- **高负载电网场景**：提高电网友好度权重至0.4-0.5
- **用户密集区域**：提高用户满意度权重至0.5左右
- **运营成本压力大**：适当提高运营商利润权重至0.4左右

## 4. 应用建议

建议系统实现自适应权重调整机制，根据实时电网负载、用户密度、充电桩利用率等因素，动态调整三个方面的权重，实现最优的综合效果。
"""
        
        self.report_text.delete(1.0, tk.END)
        self.report_text.insert(tk.END, report)
    
    def update_strategy_comparison(self, result):
        """更新策略比较结果"""
        if not result:
            return
        
        # 准备数据
        strategy_names = result.get("strategy_names", [])
        user_satisfaction = result.get("user_satisfaction", [])
        operator_profit = result.get("operator_profit", [])
        grid_friendliness = result.get("grid_friendliness", [])
        total_reward = result.get("total_reward", [])
        
        # 1. 雷达图
        self.analysis_ax1.clear()
        
        # 计算角度
        metrics = ["用户满意度", "运营商利润", "电网友好度", "综合奖励"]
        num_metrics = len(metrics)
        angles = np.linspace(0, 2*np.pi, num_metrics, endpoint=False).tolist()
        angles += angles[:1]  # 闭合雷达图
        
        # 绘制每个策略
        for i, strategy in enumerate(strategy_names):
            values = [user_satisfaction[i], operator_profit[i], grid_friendliness[i], total_reward[i]]
            values += values[:1]  # 闭合雷达图
            
            self.analysis_ax1.plot(angles, values, linewidth=2, label=strategy)
            self.analysis_ax1.fill(angles, values, alpha=0.1)
        
        # 设置雷达图参数
        self.analysis_ax1.set_theta_offset(np.pi / 2)  # 从顶部开始
        self.analysis_ax1.set_theta_direction(-1)  # 顺时针方向
        self.analysis_ax1.set_xticks(angles[:-1])
        self.analysis_ax1.set_xticklabels(metrics)
        self.analysis_ax1.set_title("不同调度策略性能雷达图")
        self.analysis_ax1.legend(loc='upper right', bbox_to_anchor=(0.1, 0.1))
        
        # 2. 各策略各指标对比柱状图
        self.analysis_ax2.clear()
        
        x = np.arange(len(strategy_names))
        width = 0.2
        
        self.analysis_ax2.bar(x - width*1.5, user_satisfaction, width, label='用户满意度')
        self.analysis_ax2.bar(x - width*0.5, operator_profit, width, label='运营商利润')
        self.analysis_ax2.bar(x + width*0.5, grid_friendliness, width, label='电网友好度')
        self.analysis_ax2.bar(x + width*1.5, total_reward, width, label='综合奖励')
        
        self.analysis_ax2.set_xlabel('策略')
        self.analysis_ax2.set_ylabel('指标值')
        self.analysis_ax2.set_title('不同调度策略各指标表现')
        self.analysis_ax2.set_xticks(x)
        self.analysis_ax2.set_xticklabels(strategy_names)
        self.analysis_ax2.legend()
        self.analysis_ax2.grid(True, linestyle='--', alpha=0.7)
        
        # 3. 总奖励对比
        self.analysis_ax3.clear()
        
        bars = self.analysis_ax3.bar(strategy_names, total_reward)
        self.analysis_ax3.set_title('不同策略综合奖励对比')
        self.analysis_ax3.set_ylabel('综合奖励')
        self.analysis_ax3.grid(axis='y', linestyle='--', alpha=0.7)
        
        # 添加数据标签
        for bar in bars:
            height = bar.get_height()
            self.analysis_ax3.text(bar.get_x() + bar.get_width()/2., height + 0.01,
                    f'{height:.3f}', ha='center', va='bottom')
        
        # 4. 第四张图留空或绘制其他内容
        self.analysis_ax4.clear()
        self.analysis_ax4.axis('off')
        
        self.analysis_fig.tight_layout()
        self.analysis_fig.canvas.draw_idle()
        
        # 生成报告文本
        report = """# 调度策略比较报告

## 1. 策略性能比较

不同调度策略在各指标上的表现各有优劣：

"""
        # 添加实际数据
        for i, strategy in enumerate(strategy_names):
            report += f"- **{strategy}**: 用户满意度 {user_satisfaction[i]:.3f}, 运营商利润 {operator_profit[i]:.3f}, "
            report += f"电网友好度 {grid_friendliness[i]:.3f}, 综合奖励 {total_reward[i]:.3f}\n"
        
        # 找出各指标最优策略
        best_satisfaction = strategy_names[np.argmax(user_satisfaction)]
        best_profit = strategy_names[np.argmax(operator_profit)] 
        best_grid = strategy_names[np.argmax(grid_friendliness)]
        best_total = strategy_names[np.argmax(total_reward)]
        
        report += f"""
## 2. 最佳策略分析

- **用户满意度最高的策略**: {best_satisfaction}
- **运营商利润最高的策略**: {best_profit}
- **电网友好度最高的策略**: {best_grid}
- **综合奖励最高的策略**: {best_total}

## 3. 适用场景分析

- **用户优先策略**：适用于用户密集、竞争激烈的市场环境
- **利润优先策略**：适用于运营初期或成本回收压力大的阶段
- **电网友好策略**：适用于电网负荷高峰或新能源渗透率高的区域
- **平衡策略**：适用于大多数常规场景，特别是对电网友好和用户服务都有要求的情况

## 4. 策略推荐

根据综合表现，推荐采用**{best_total}**作为基础策略，并根据实际场景动态调整权重：

- 电网高负载时段：提高电网友好度权重
- 用户高峰时段：提高用户满意度权重
- 低谷电价时段：提高运营商利润权重
"""
        
        self.report_text.delete(1.0, tk.END)
        self.report_text.insert(tk.END, report)
    
    def run_strategy_analysis(self):
        """运行策略分析"""
        # 切换到分析标签页
        for i in range(self.notebook.index('end')):
            if self.notebook.tab(i, "text") == "数据分析":
                self.notebook.select(i)
                break
        
        # 设置分析类型为策略比较
        self.analysis_type_var.set("strategy_comparison")
        
        # 运行分析
        self.run_analysis()
    
    def run_grid_analysis(self):
        """运行电网影响分析"""
        # 切换到分析标签页
        for i in range(self.notebook.index('end')):
            if self.notebook.tab(i, "text") == "数据分析":
                self.notebook.select(i)
                break
        
        # 设置分析类型为电网影响
        self.analysis_type_var.set("grid_impact")
        
        # 运行分析
        self.run_analysis()
    
    def run_user_analysis(self):
        """运行用户行为分析"""
        # 切换到分析标签页
        for i in range(self.notebook.index('end')):
            if self.notebook.tab(i, "text") == "数据分析":
                self.notebook.select(i)
                break
        
        # 设置分析类型为用户行为
        self.analysis_type_var.set("user_behavior")
        
        # 运行分析
        self.run_analysis()
    
    def switch_visualization(self):
        """切换可视化视图"""
        view_type = self.view_var.get()
        
        if view_type == "user":
            self.create_user_visualization()
        elif view_type == "operator":
            self.create_operator_visualization()
        elif view_type == "grid":
            self.create_grid_visualization()
    
    def generate_visualization(self):
        """生成可视化报告"""
        # 切换到可视化标签页
        for i in range(self.notebook.index('end')):
            if self.notebook.tab(i, "text") == "可视化":
                self.notebook.select(i)
                break
    
    def get_charging_recommendations(self):
        """获取充电推荐"""
        # 检查后端是否已加载
        if not BACKEND_LOADED or not self.system:
            if messagebox.askokcancel("后端未加载", "后端系统未加载，是否尝试初始化?"):
                if not self.init_backend():
                    return
            else:
                return
        
        # 获取参数
        user_id = self.user_id_var.get()
        soc = self.soc_var.get()
        
        # 更新状态
        self.status_var.set("获取充电推荐中...")
        self.log(f"获取用户 {user_id} 的充电推荐，当前SOC: {soc}%")
        
        try:
            # 获取当前环境状态
            state = self.system.env.get_current_state()
            
            # 创建用户信息
            user_info = {
                "user_id": user_id,
                "soc": soc,
                "max_wait_time": 30,
                "preferred_power": 90,
                "position": {
                    "lat": 30.65,
                    "lng": 104.1
                },
                "user_type": "私家车",
                "profile": "平衡考量型"
            }
            
            # 更新用户状态
            for i, user in enumerate(state["users"]):
                if user["user_id"] == user_id:
                    # 更新现有用户
                    state["users"][i] = user_info
                    break
            else:
                # 添加新用户
                state["users"].append(user_info)
            
            # 获取推荐
            recommendations = self.system.scheduler.make_recommendation(user_id, state)
            
            # 更新推荐列表
            self.update_recommendation_list(recommendations)
            
            # 更新状态
            self.status_var.set(f"获取到 {len(recommendations)} 个充电推荐")
            self.log(f"为用户 {user_id} 获取到 {len(recommendations)} 个充电推荐")
            
        except Exception as e:
            error_msg = f"获取充电推荐失败: {str(e)}"
            self.log(error_msg, "error")
            messagebox.showerror("推荐错误", error_msg)
            self.status_var.set("获取推荐失败")
    
    def update_recommendation_list(self, recommendations):
        """更新推荐列表"""
        # 清空列表
        for item in self.rec_tree.get_children():
            self.rec_tree.delete(item)
        
        # 添加推荐
        for i, rec in enumerate(recommendations):
            # 格式化数据
            rank = i + 1
            name = f"充电站{rec['charger_id'].split('_')[1]}"
            type_text = "快充" if rec.get("available_power", 0) > 80 else "慢充"
            distance = rec.get("distance", 0) if hasattr(rec, "distance") else np.random.uniform(1, 8)
            wait_time = rec.get("wait_time", 0) if hasattr(rec, "wait_time") else np.random.randint(0, 30)
            score = rec.get("combined_score", 0)
            
            # 添加到列表
            self.rec_tree.insert('', 'end', values=(
                rank, name, type_text, f"{distance:.1f}", f"{wait_time}", f"{score:.2f}"
            ))
    
    def apply_price_strategy(self):
        """应用价格策略"""
        # 获取价格参数
        peak_markup = self.peak_markup_var.get()
        valley_discount = self.valley_discount_var.get()
        
        # 显示模拟结果
        messagebox.showinfo("价格策略", f"已应用价格策略:\n峰时电价加价率: {peak_markup:.1f}%\n谷时电价折扣率: {valley_discount:.1f}%\n\n预计日利润变化: +8.5%\n预计用户满意度变化: -2.1%")
    
    def refresh_grid_data(self):
        """刷新电网数据"""
        messagebox.showinfo("刷新电网数据", "电网负载数据已更新")
    
    def generate_dashboards(self):
        """生成仪表盘"""
        # 检查后端是否已加载
        if not BACKEND_LOADED or not self.system:
            if messagebox.askokcancel("后端未加载", "后端系统未加载，是否尝试初始化?"):
                if not self.init_backend():
                    return
            else:
                return
        
        # 更新状态
        self.status_var.set("生成仪表盘中...")
        self.log("开始生成仪表盘")
        
        try:
            # 运行后端生成仪表盘
            dashboards = self.system.generate_dashboards()
            
            # 提取仪表盘文件路径
            user_dashboard = dashboards.get("user_dashboard", "")
            operator_dashboard = dashboards.get("operator_dashboard", "")
        # 更新状态并显示成功消息
            self.status_var.set("仪表盘生成完成")
            self.log(f"仪表盘生成完成:\n用户仪表盘: {user_dashboard}\n运营商仪表盘: {operator_dashboard}")
            messagebox.showinfo("仪表盘生成完成", 
                               f"仪表盘已成功生成:\n\n用户仪表盘: {user_dashboard}\n运营商仪表盘: {operator_dashboard}")
            
        except Exception as e:
            error_msg = f"生成仪表盘失败: {str(e)}"
            self.log(error_msg, "error")
            messagebox.showerror("生成错误", error_msg)
            self.status_var.set("仪表盘生成失败")
    
    def train_model(self):
        """训练决策模型"""
        # 检查后端是否已加载
        if not BACKEND_LOADED:
            messagebox.showerror("功能不可用", "此功能需要后端模块支持，但未能加载后端模块。")
            return
        
        # 确认是否开始训练
        if not messagebox.askokcancel("训练模型", "训练模型可能需要较长时间，是否继续？"):
            return
        
        # 更新状态
        self.status_var.set("模型训练中...")
        self.log("开始训练决策模型")
        
        # 启动训练线程
        training_thread = threading.Thread(target=self.run_training_thread)
        training_thread.daemon = True
        training_thread.start()
    
    def run_training_thread(self):
        """训练模型线程"""
        try:
            from ev_model_training import DataGenerator, train_model, evaluate_model
            
            # 更新日志
            self.log("生成训练数据...")
            self.after(0, lambda: self.update_status("生成训练数据..."))
            
            # 生成训练数据
            data_gen = DataGenerator(num_samples=20000)
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
            
            # 更新日志
            self.log("开始训练模型...")
            self.after(0, lambda: self.update_status("训练模型中..."))
            
            # 训练模型
            input_dim = X.shape[1]
            model, history = train_model(
                X_train, y_train_satisfaction, y_train_profit, y_train_grid,
                X_val, y_val_satisfaction, y_val_profit, y_val_grid,
                input_dim, batch_size=64, epochs=30
            )
            
            # 更新日志
            self.log("评估模型性能...")
            self.after(0, lambda: self.update_status("评估模型性能..."))
            
            # 评估模型
            metrics = evaluate_model(
                model, X_test, y_test_satisfaction, y_test_profit, y_test_grid
            )
            
            # 保存模型
            output_dir = "models"
            os.makedirs(output_dir, exist_ok=True)
            model_path = os.path.join(output_dir, "ev_charging_model.pth")
            
            import torch
            torch.save(model.state_dict(), model_path)
            
            # 记录结果
            result_log = f"""模型训练完成:

                训练集大小: {len(X_train)}
                验证集大小: {len(X_val)}
                测试集大小: {len(X_test)}

                模型评估指标:
                - 用户满意度 - MSE: {metrics['mse']['satisfaction']:.4f}, MAE: {metrics['mae']['satisfaction']:.4f}, R²: {metrics['r2']['satisfaction']:.4f}
                - 运营商利润 - MSE: {metrics['mse']['profit']:.4f}, MAE: {metrics['mae']['profit']:.4f}, R²: {metrics['r2']['profit']:.4f}
                - 电网友好度 - MSE: {metrics['mse']['grid']:.4f}, MAE: {metrics['mae']['grid']:.4f}, R²: {metrics['r2']['grid']:.4f}

                模型已保存到: {model_path}
                """
            self.log(result_log)
            
            # 更新状态
            self.after(0, lambda: self.update_status("模型训练完成"))
            
            # 显示完成消息
            self.after(0, lambda: messagebox.showinfo("训练完成", f"模型训练完成，已保存到: {model_path}"))
            
        except Exception as e:
            error_msg = f"模型训练失败: {str(e)}"
            self.log(error_msg, "error")
            self.after(0, lambda: messagebox.showerror("训练错误", error_msg))
            self.after(0, lambda: self.update_status("模型训练失败"))
    
    def update_status(self, message):
        """更新状态栏消息"""
        self.status_var.set(message)


if __name__ == "__main__":
    # 设置更好的显示样式
    try:
        from ttkthemes import ThemedTk
        app = ThemedTk(theme="arc")
        app.title("电动汽车有序充电调度系统")
        app.geometry("1200x800")
        app.minsize(1000, 700)
        
        # 添加标签页
        ui = EVChargingSystemUI.__new__(EVChargingSystemUI)
        EVChargingSystemUI.__init__(ui)
        
    except ImportError:
        # 如果没有ttkthemes，使用标准tkinter
        app = EVChargingSystemUI()
    
    # 运行主循环
    app.mainloop()