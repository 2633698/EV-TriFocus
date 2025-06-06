import sys
import logging
import random
from datetime import datetime
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget,
    QTableWidgetItem, QHeaderView, QComboBox, QGroupBox, QGridLayout,
    QFormLayout, QPushButton, QDoubleSpinBox, QScrollArea # Added missing imports
)
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtCore import Qt, pyqtSignal # Added pyqtSignal

logger = logging.getLogger(__name__)

try:
    import pyqtgraph as pg
    from pyqtgraph import PlotWidget
    HAS_PYQTGRAPH = True
except ImportError:
    HAS_PYQTGRAPH = False

class PowerGridPanel(QWidget):
    # Define Signals
    gridPreferenceChanged = pyqtSignal(str, object) # preference_name, value
    v2gDischargeRequested = pyqtSignal(float)    # discharge_amount_mw

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.current_region_key = "region_0"

        self.predicted_load_curve_item = None
        self.solar_gen_curve_item = None
        self.wind_gen_curve_item = None
        self.last_plotted_timestamp_count = 0
        self._last_grid_status_data = None
        self.decision_impact_plot = None # Initialize plot attribute
        self.pre_decision_load_curve = None
        self.post_decision_load_curve = None
        self.algorithm_comparison_plot = None
        self.bar_items = {} # To store bar graph items for algorithm comparison
        self.metric_categories = ["峰值降低 (%)", "负载均衡提升 (StdDev)", "新能源占比 (%)"]


        # Create a content widget and a layout for it
        scroll_content_widget = QWidget()
        main_layout = QVBoxLayout(scroll_content_widget) # This layout will hold all group boxes
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(15)

        load_monitoring_group = self._create_load_monitoring_section()
        main_layout.addWidget(load_monitoring_group)

        renewable_analysis_group = self._create_renewable_analysis_section()
        main_layout.addWidget(renewable_analysis_group)

        power_quality_group = self._create_power_quality_section()
        main_layout.addWidget(power_quality_group)

        carbon_analysis_group = self._create_carbon_analysis_section()
        main_layout.addWidget(carbon_analysis_group)

        regional_comparison_group = self._create_regional_comparison_section()
        main_layout.addWidget(regional_comparison_group)

        dispatch_control_group = self._create_grid_dispatch_control_section()
        main_layout.addWidget(dispatch_control_group)

        decision_impact_group = self._create_decision_impact_section() # New section
        main_layout.addWidget(decision_impact_group)                   # Add to layout

        algorithm_comparison_group = self._create_algorithm_comparison_section() # New algo comparison section
        main_layout.addWidget(algorithm_comparison_group)                      # Add to layout

        main_layout.addStretch() # Add stretch to the content layout

        # Create scroll area and set the content widget
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(scroll_content_widget)

        # Set up the main layout for the PowerGridPanel itself
        panel_main_layout = QVBoxLayout(self)
        panel_main_layout.setContentsMargins(0,0,0,0) # Optional: remove margins if scroll area handles padding
        panel_main_layout.addWidget(scroll_area)
        self.setLayout(panel_main_layout)


        # Initialize UI elements that depend on other UI elements
        if hasattr(self, 'strategy_combo'):
             self._on_strategy_changed(self.strategy_combo.currentText())
        if hasattr(self, 'carbon_savings_label'): # Ensure it exists before calling
            self._update_carbon_savings_display()

        # Emit initial states for dispatch controls
        if hasattr(self, 'charging_priority_combo'):
            self._on_charging_priority_changed(self.charging_priority_combo.currentText())
        if hasattr(self, 'max_ev_load_spinbox'):
            self._on_apply_max_ev_load_limit()

        if HAS_PYQTGRAPH and self.decision_impact_plot: # Test call for the new chart
            self.update_decision_impact_chart([100, 120, 110, 130, 125], [90, 100, 95, 110, 105])

        if HAS_PYQTGRAPH and self.algorithm_comparison_plot: # Test call for algo comparison chart
            dummy_comp_data = {
                'peak_reduction': {'uncoordinated': 15, 'coordinated': 25},
                'load_balance': {'uncoordinated': 0.8, 'coordinated': 0.4}, # Lower is better for std dev
                'renewable_share': {'uncoordinated': 20, 'coordinated': 35}
            }
            self.update_algorithm_comparison_chart(dummy_comp_data)


        # self.setLayout(main_layout) # This is now panel_main_layout

    # Method for creating the decision impact section
    def _create_decision_impact_section(self):
        group_box = QGroupBox("决策影响分析")
        group_box.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        layout = QVBoxLayout(group_box)

        if HAS_PYQTGRAPH:
            self.decision_impact_plot = PlotWidget()
            self.decision_impact_plot.setBackground('w')
            self.decision_impact_plot.setLabel('left', '负荷 (MW)', color='#333', **{'font-size': '10pt'})
            self.decision_impact_plot.setLabel('bottom', '时间', color='#333', **{'font-size': '10pt'}) # Using '时间' (Time) for x-axis
            self.decision_impact_plot.showGrid(x=True, y=True, alpha=0.3)
            self.decision_impact_plot.addLegend(offset=(-10,10))

            # Define plot curves
            self.pre_decision_load_curve = self.decision_impact_plot.plot(
                pen=pg.mkPen(color=(255, 100, 100), style=Qt.PenStyle.DashLine, width=2),
                name="决策前负荷"
            )
            self.post_decision_load_curve = self.decision_impact_plot.plot(
                pen=pg.mkPen(color=(100, 255, 100), width=2),
                name="决策后负荷"
            )
            layout.addWidget(self.decision_impact_plot)
        else:
            error_label = QLabel("图表功能需要 PyQtGraph 库。")
            error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            error_label.setStyleSheet("color:red; font-weight:bold; padding:20px;")
            layout.addWidget(error_label)

        return group_box

    # Placeholder method to update the decision impact chart
    def update_decision_impact_chart(self, pre_decision_data, post_decision_data):
        if HAS_PYQTGRAPH and self.pre_decision_load_curve and self.post_decision_load_curve:
            # Ensure data is in a format pg can use (e.g. list of numbers)
            pre_data_points = [float(d) for d in pre_decision_data if isinstance(d, (int, float))]
            post_data_points = [float(d) for d in post_decision_data if isinstance(d, (int, float))]

            self.pre_decision_load_curve.setData(list(range(len(pre_data_points))), pre_data_points)
            self.post_decision_load_curve.setData(list(range(len(post_data_points))), post_data_points)

            # Potentially adjust x-axis ticks if number of points changes significantly
            # For now, simple range is used. If timestamps are available, use them.
            if pre_data_points or post_data_points:
                 self.decision_impact_plot.getAxis('bottom').setTicks([]) # Clear old ticks if any specific ones were set
        else:
            logger.debug("PyQtGraph not available or curves not initialized. Skipping chart update.")

    def _create_algorithm_comparison_section(self):
        group_box = QGroupBox("调度算法对比")
        group_box.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        layout = QVBoxLayout(group_box)

        if HAS_PYQTGRAPH:
            self.algorithm_comparison_plot = PlotWidget()
            self.algorithm_comparison_plot.setBackground('w')
            self.algorithm_comparison_plot.setLabel('left', '指标值', color='#333', **{'font-size': '10pt'})
            self.algorithm_comparison_plot.setLabel('bottom', '对比维度', color='#333', **{'font-size': '10pt'})
            self.algorithm_comparison_plot.showGrid(x=True, y=True, alpha=0.3)
            # self.algorithm_comparison_plot.addLegend() # Legend will be implicit via BarGraphItem names

            # Bar items will be created/updated in the update method
            # Set X-axis ticks
            ticks = [(i, name) for i, name in enumerate(self.metric_categories)]
            self.algorithm_comparison_plot.getAxis('bottom').setTicks([ticks])

            layout.addWidget(self.algorithm_comparison_plot)
        else:
            error_label = QLabel("图表功能需要 PyQtGraph 库。")
            error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            error_label.setStyleSheet("color:red; font-weight:bold; padding:20px;")
            layout.addWidget(error_label)

        return group_box

    def update_algorithm_comparison_chart(self, comparison_data):
        if not HAS_PYQTGRAPH or not self.algorithm_comparison_plot:
            logger.debug("PyQtGraph not available or algo comparison plot not initialized.")
            return

        # Clear previous bar items if any, to prevent overplotting on updates
        for item_name in list(self.bar_items.keys()): # Iterate over a copy of keys
            self.algorithm_comparison_plot.removeItem(self.bar_items[item_name])
            del self.bar_items[item_name]

        bar_width = 0.3
        num_metrics = len(self.metric_categories)
        x_positions = list(range(num_metrics))

        algorithms = ['uncoordinated', 'coordinated']
        algo_labels = {'uncoordinated': '无序充电', 'coordinated': '集中调度'}
        colors = {'uncoordinated': (255, 100, 100, 150), 'coordinated': (100, 255, 100, 150)} # Red-ish, Green-ish

        for i, algo_key in enumerate(algorithms):
            heights = []
            current_x_positions = [x + (i - 0.5) * bar_width for x in x_positions] # Shift for side-by-side

            # Ensure data keys match self.metric_categories or map them
            # For this example, let's assume comparison_data keys are 'peak_reduction', 'load_balance', 'renewable_share'
            data_keys_ordered = ['peak_reduction', 'load_balance', 'renewable_share']
            for metric_key_internal in data_keys_ordered:
                heights.append(comparison_data.get(metric_key_internal, {}).get(algo_key, 0))

            bar_name = f"{algo_labels[algo_key]}" # Legend name from BarGraphItem

            bar_item = pg.BarGraphItem(x=current_x_positions, height=heights, width=bar_width,
                                       brush=pg.mkBrush(color=colors[algo_key]), name=bar_name)
            self.algorithm_comparison_plot.addItem(bar_item)
            self.bar_items[f"{algo_key}"] = bar_item # Store to manage later if needed (e.g. for selective updates)

        # Explicitly add legend after items are added if it wasn't showing up
        # Check if a legend already exists, remove it to add a fresh one
        if self.algorithm_comparison_plot.plotItem.legend:
            self.algorithm_comparison_plot.plotItem.legend.scene().removeItem(self.algorithm_comparison_plot.plotItem.legend)
        self.algorithm_comparison_plot.addLegend(offset=(-10,10))


    def _create_load_monitoring_section(self):
        # ... (Existing code - unchanged)
        group_box = QGroupBox("电网负荷监控");group_box.setFont(QFont("Arial", 12, QFont.Weight.Bold));group_layout = QVBoxLayout(group_box)
        controls_layout = QHBoxLayout();controls_layout.addWidget(QLabel("选择区域:"));self.region_combo = QComboBox()
        self.region_combo.addItems(["region_0", "region_1", "All Regions (Aggregated)"]);self.region_combo.currentTextChanged.connect(self._on_region_changed) # Note: Region names are IDs, not translated
        controls_layout.addWidget(self.region_combo);controls_layout.addStretch();group_layout.addLayout(controls_layout);self.load_table = QTableWidget()
        self.load_table.setColumnCount(4);self.load_table.setHorizontalHeaderLabels(["时间", "总负荷 (MW)", "基础负荷 (MW)", "电动汽车负荷 (MW)"])
        self.load_table.setAlternatingRowColors(True);self.load_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.load_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch);self.load_table.verticalHeader().setVisible(False)
        group_layout.addWidget(self.load_table)
        if HAS_PYQTGRAPH:
            self.load_curves_plot = PlotWidget();self.load_curves_plot.setBackground('w')
            self.load_curves_plot.setLabel('left', '负荷 / 发电 (MW)', color='#333', **{'font-size': '10pt'})
            self.load_curves_plot.setLabel('bottom', '时间步', color='#333', **{'font-size': '10pt'})
            self.load_curves_plot.showGrid(x=True, y=True, alpha=0.3);self.load_curves_plot.addLegend(offset=(-10,10))
            self.total_load_curve = self.load_curves_plot.plot(pen=pg.mkPen(color=(0,0,255),width=2), name="总负荷")
            self.base_load_curve = self.load_curves_plot.plot(pen=pg.mkPen(color=(0,128,0),width=2), name="基础负荷")
            self.ev_load_curve = self.load_curves_plot.plot(pen=pg.mkPen(color=(255,0,0),width=2), name="电动汽车负荷")
            self.solar_gen_curve_item = self.load_curves_plot.plot(pen=pg.mkPen(color=(255,165,0),width=2), name="太阳能发电")
            self.wind_gen_curve_item = self.load_curves_plot.plot(pen=pg.mkPen(color=(135,206,235),width=2), name="风能发电")
            group_layout.addWidget(self.load_curves_plot)
        else: group_layout.addWidget(QLabel("图表功能需要 PyQtGraph 库。", alignment=Qt.AlignmentFlag.AlignCenter, styleSheet="color:red;font-weight:bold;padding:20px;"))
        return group_box


    def _create_renewable_analysis_section(self):
        # ... (Existing code - unchanged)
        group_box = QGroupBox("新能源协调");group_box.setFont(QFont("Arial",12,QFont.Weight.Bold));layout=QVBoxLayout(group_box);layout.setSpacing(10);metrics_layout=QHBoxLayout()
        self.renewable_share_label=QLabel("可再生能源充电占比: N/A %");self.renewable_share_label.setFont(QFont("Arial",10));metrics_layout.addWidget(self.renewable_share_label);metrics_layout.addStretch()
        self.v1g_potential_label=QLabel("V1G 调度潜力: N/A MW");self.v1g_potential_label.setFont(QFont("Arial",10));metrics_layout.addWidget(self.v1g_potential_label);metrics_layout.addStretch()
        layout.addLayout(metrics_layout);return group_box

    def _create_power_quality_section(self):
        # ... (Existing code - unchanged)
        group_box = QGroupBox("电能质量与稳定性");group_box.setFont(QFont("Arial",12,QFont.Weight.Bold));main_v_layout=QVBoxLayout(group_box);main_v_layout.setSpacing(10);strategy_h_layout=QHBoxLayout()
        strategy_h_layout.addWidget(QLabel("充电策略:"));self.strategy_combo=QComboBox();self.strategy_combo.addItems(["无序充电","智能充电 (V1G)","V2G激活"])
        self.strategy_combo.currentTextChanged.connect(self._on_strategy_changed);strategy_h_layout.addWidget(self.strategy_combo);strategy_h_layout.addStretch();main_v_layout.addLayout(strategy_h_layout)
        indicators_layout=QGridLayout();indicators_layout.setSpacing(10)
        indicators_layout.addWidget(QLabel("电压稳定性:"),0,0);self.voltage_stability_label=QLabel("N/A");self.voltage_stability_label.setFont(QFont("Arial",10,QFont.Weight.Bold));indicators_layout.addWidget(self.voltage_stability_label,0,1)
        indicators_layout.addWidget(QLabel("频率稳定性:"),1,0);self.frequency_stability_label=QLabel("N/A");self.frequency_stability_label.setFont(QFont("Arial",10,QFont.Weight.Bold));indicators_layout.addWidget(self.frequency_stability_label,1,1)
        indicators_layout.addWidget(QLabel("电网应变:"),2,0);self.grid_strain_label=QLabel("N/A");self.grid_strain_label.setFont(QFont("Arial",10,QFont.Weight.Bold));indicators_layout.addWidget(self.grid_strain_label,2,1)
        indicators_layout.setColumnStretch(2,1);main_v_layout.addLayout(indicators_layout);return group_box

    def _create_carbon_analysis_section(self):
        # ... (Existing code - unchanged)
        group_box = QGroupBox("碳排放足迹");group_box.setFont(QFont("Arial",12,QFont.Weight.Bold));layout=QVBoxLayout(group_box);layout.setSpacing(10);metrics_layout=QHBoxLayout()
        self.carbon_intensity_label=QLabel("实时碳强度: N/A gCO₂/kWh");self.carbon_intensity_label.setFont(QFont("Arial",10));metrics_layout.addWidget(self.carbon_intensity_label);metrics_layout.addStretch()
        self.carbon_savings_label=QLabel("优化充电节省: N/A kg CO₂");self.carbon_savings_label.setFont(QFont("Arial",10));metrics_layout.addWidget(self.carbon_savings_label);metrics_layout.addStretch()
        layout.addLayout(metrics_layout);return group_box

    def _create_regional_comparison_section(self):
        # ... (Existing code - unchanged)
        group_box = QGroupBox("区域对比与规划支持");group_box.setFont(QFont("Arial",12,QFont.Weight.Bold));layout=QVBoxLayout(group_box);layout.setSpacing(10)
        layout.addWidget(QLabel("区域指标对比:"));self.regional_comparison_table=QTableWidget();self.regional_comparison_table.setColumnCount(5)
        self.regional_comparison_table.setHorizontalHeaderLabels(["区域","总负荷 (MW)","负荷占比 (%)","可再生能源占比 (%)","碳强度 (gCO₂/kWh)"]) # "Region" is "区域"
        self.regional_comparison_table.setAlternatingRowColors(True);self.regional_comparison_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.regional_comparison_table.horizontalHeader().setStretchLastSection(True);self.regional_comparison_table.verticalHeader().setVisible(False);self.regional_comparison_table.setFixedHeight(150)
        layout.addWidget(self.regional_comparison_table);layout.addWidget(QLabel("规划支持洞察:"))
        self.peak_load_insight_label=QLabel("最高峰值负荷 (当前仿真): N/A");self.peak_load_insight_label.setFont(QFont("Arial",10));layout.addWidget(self.peak_load_insight_label);return group_box

    def _create_grid_dispatch_control_section(self):
        group_box = QGroupBox("电网调度控制")
        group_box.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        form_layout = QFormLayout(group_box)
        form_layout.setSpacing(10)
        form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        # Charging Priority
        self.charging_priority_combo = QComboBox()
        self.charging_priority_combo.addItems(["均衡", "优先可再生能源", "成本最小化", "削峰"])
        self.charging_priority_combo.currentTextChanged.connect(self._on_charging_priority_changed)
        form_layout.addRow(QLabel("电网充电优先级:"), self.charging_priority_combo)

        # Max EV Charging Impact Limit
        max_ev_load_layout = QHBoxLayout()
        self.max_ev_load_spinbox = QDoubleSpinBox()
        self.max_ev_load_spinbox.setRange(0, 10000) # MW
        self.max_ev_load_spinbox.setValue(500)    # Default
        self.max_ev_load_spinbox.setSuffix(" MW")
        max_ev_load_layout.addWidget(self.max_ev_load_spinbox)
        apply_limit_btn = QPushButton("应用限制")
        apply_limit_btn.clicked.connect(self._on_apply_max_ev_load_limit)
        max_ev_load_layout.addWidget(apply_limit_btn)
        form_layout.addRow(QLabel("最大电动汽车集群负荷:"), max_ev_load_layout)

        # V2G Dispatch Request
        v2g_request_layout = QHBoxLayout()
        self.v2g_request_spinbox = QDoubleSpinBox()
        self.v2g_request_spinbox.setRange(0, 1000) # MW
        self.v2g_request_spinbox.setValue(0)
        self.v2g_request_spinbox.setSuffix(" MW")
        v2g_request_layout.addWidget(self.v2g_request_spinbox)
        activate_v2g_btn = QPushButton("激活V2G")
        activate_v2g_btn.clicked.connect(self._on_activate_v2g_discharge)
        v2g_request_layout.addWidget(activate_v2g_btn)
        form_layout.addRow(QLabel("请求V2G放电:"), v2g_request_layout)

        return group_box

    def _on_charging_priority_changed(self, priority_text):
        logger.info(f"Grid Charging Priority changed to: {priority_text}")
        self.gridPreferenceChanged.emit("charging_priority", priority_text)

    def _on_apply_max_ev_load_limit(self):
        value = self.max_ev_load_spinbox.value()
        logger.info(f"Max EV Fleet Load limit applied: {value} MW")
        self.gridPreferenceChanged.emit("max_ev_fleet_load_mw", value)

    def _on_activate_v2g_discharge(self):
        value = self.v2g_request_spinbox.value()
        logger.info(f"V2G Discharge requested: {value} MW")
        self.v2gDischargeRequested.emit(value)
        # Optionally reset spinbox after activation or provide feedback
        # self.v2g_request_spinbox.setValue(0)

    def _on_strategy_changed(self, strategy_text):
        # ... (Existing code - unchanged)
        logger.debug(f"Strategy changed to: {strategy_text}");strategy_styles={"无序充电":{"voltage":("波动风险","orange"),"frequency":("轻微波动","orange"),"strain":("升高","red")},"智能充电 (V1G)":{"voltage":("稳定","green"),"frequency":("稳定","green"),"strain":("正常","green")},"V2G激活":{"voltage":("动态(管理中)","#5DADE2"),"frequency":("动态(管理中)","#5DADE2"),"strain":("可变(双向)","#F39C12")}};default_style={"voltage":("N/A","black"),"frequency":("N/A","black"),"strain":("N/A","black")};current_styles=strategy_styles.get(strategy_text,default_style)
        self.voltage_stability_label.setText(current_styles["voltage"][0]);self.voltage_stability_label.setStyleSheet(f"color: {current_styles['voltage'][1]}; font-weight: bold;")
        self.frequency_stability_label.setText(current_styles["frequency"][0]);self.frequency_stability_label.setStyleSheet(f"color: {current_styles['frequency'][1]}; font-weight: bold;")
        self.grid_strain_label.setText(current_styles["strain"][0]);self.grid_strain_label.setStyleSheet(f"color: {current_styles['strain'][1]}; font-weight: bold;")
        self._update_carbon_savings_display()

    def _update_carbon_savings_display(self):
        # ... (Existing code - unchanged)
        if not hasattr(self,'strategy_combo')or not hasattr(self,'carbon_savings_label'):return
        strategy=self.strategy_combo.currentText()
        if strategy=="智能充电 (V1G)":savings=random.uniform(5,15);self.carbon_savings_label.setText(f"预计节省 (智能): {savings:.1f} kg CO₂")
        elif strategy=="V2G激活":savings=random.uniform(10,30);self.carbon_savings_label.setText(f"预计节省 (V2G): {savings:.1f} kg CO₂")
        else:self.carbon_savings_label.setText("优化充电节省: N/A")

    def _on_region_changed(self, region_text):
        # ... (Existing code - unchanged)
        if region_text=="All Regions (Aggregated)":self.current_region_key="aggregated"
        else:self.current_region_key=region_text
        self.handle_status_update(self._last_grid_status_data if self._last_grid_status_data else{})

    def _get_regional_data_series(self, time_series_data, series_key, num_timestamps):
        # ... (Existing code - unchanged)
        regional_data_map=time_series_data.get('regional_data',{})
        if self.current_region_key=="aggregated":
            aggregated_series=[0.0]*num_timestamps;
            if not regional_data_map:return aggregated_series
            count=0
            for r_data in regional_data_map.values():
                series=r_data.get(series_key,[])
                if len(series)==num_timestamps:aggregated_series=[sum(x)for x in zip(aggregated_series,series)];count+=1
                else:logger.warning(f"Agg. Length mismatch for '{series_key}'. Expected {num_timestamps}, got {len(series)}.")
            return aggregated_series
        elif self.current_region_key in regional_data_map:return regional_data_map[self.current_region_key].get(series_key,[0.0]*num_timestamps)
        return[0.0]*num_timestamps

    def update_load_data(self, combined_grid_data):
        # ... (Existing code - unchanged, including reset_ui_to_na and all data population logic)
        logger.debug(f"Updating load data for region: {self.current_region_key}");time_series_data=combined_grid_data.get('time_series',{});aggregated_metrics=combined_grid_data.get('aggregated_metrics',{});regional_comparison_data=combined_grid_data.get('regional_comparison',{})
        def reset_ui_to_na():
            self.load_table.setRowCount(0)
            if HAS_PYQTGRAPH:self.total_load_curve.clear();self.base_load_curve.clear();self.ev_load_curve.clear();
            if self.predicted_load_curve_item:self.load_curves_plot.removeItem(self.predicted_load_curve_item);self.predicted_load_curve_item=None
            if self.solar_gen_curve_item:self.solar_gen_curve_item.clear()
            if self.wind_gen_curve_item:self.wind_gen_curve_item.clear()
            self.last_plotted_timestamp_count=0;self.renewable_share_label.setText("可再生能源充电占比: N/A %");self.v1g_potential_label.setText("V1G 调度潜力: N/A MW");self.carbon_intensity_label.setText("实时碳强度: N/A gCO₂/kWh");self.regional_comparison_table.setRowCount(0);self.peak_load_insight_label.setText("最高峰值负荷 (当前仿真): N/A")
        if not time_series_data or'timestamps'not in time_series_data or'regional_data'not in time_series_data:reset_ui_to_na();return
        timestamps=time_series_data.get('timestamps',[]);num_timestamps=len(timestamps)
        if num_timestamps==0:reset_ui_to_na();return
        self.last_plotted_timestamp_count=num_timestamps;total_load_series=self._get_regional_data_series(time_series_data,'total_load',num_timestamps);base_load_series=self._get_regional_data_series(time_series_data,'base_load',num_timestamps);ev_load_series=self._get_regional_data_series(time_series_data,'ev_load',num_timestamps);solar_gen_series=self._get_regional_data_series(time_series_data,'solar_generation',num_timestamps);wind_gen_series=self._get_regional_data_series(time_series_data,'wind_generation',num_timestamps);carbon_intensity_series=self._get_regional_data_series(time_series_data,'carbon_intensity',num_timestamps)
        self.load_table.setRowCount(0);self.load_table.setRowCount(num_timestamps)
        for i,ts_str in enumerate(timestamps):
            display_time=ts_str;
            try:dt_obj=datetime.fromisoformat(ts_str.replace('Z','+00:00'));display_time=dt_obj.strftime('%H:%M:%S')
            except ValueError:pass
            self.load_table.setItem(i,0,QTableWidgetItem(display_time));self.load_table.setItem(i,1,QTableWidgetItem(f"{total_load_series[i]/1000:.2f}"));self.load_table.setItem(i,2,QTableWidgetItem(f"{base_load_series[i]/1000:.2f}"));self.load_table.setItem(i,3,QTableWidgetItem(f"{ev_load_series[i]/1000:.2f}"))
            for col in range(4):
                if self.load_table.item(i,col):self.load_table.item(i,col).setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        if HAS_PYQTGRAPH:
            x_vals=list(range(num_timestamps));self.total_load_curve.setData(x_vals,[v/1000 for v in total_load_series]);self.base_load_curve.setData(x_vals,[v/1000 for v in base_load_series]);self.ev_load_curve.setData(x_vals,[v/1000 for v in ev_load_series]);self.solar_gen_curve_item.setData(x_vals,[v/1000 for v in solar_gen_series]);self.wind_gen_curve_item.setData(x_vals,[v/1000 for v in wind_gen_series])
            if num_timestamps>0:
                tick_interval=max(1,num_timestamps//10);ticks=[(i,datetime.fromisoformat(timestamps[i].replace('Z','+00:00')).strftime('%H:%M'))for i in range(0,num_timestamps,tick_interval)if i<len(timestamps)]
                try:self.load_curves_plot.getAxis('bottom').setTicks([ticks])
                except Exception as e:logger.error(f"Error setting X-axis ticks: {e}")
        if num_timestamps>0:
            ev_load_latest_kw=ev_load_series[-1];total_load_latest_kw=total_load_series[-1];solar_latest_kw=solar_gen_series[-1];wind_latest_kw=wind_gen_series[-1];renewable_gen_latest_kw=solar_latest_kw+wind_latest_kw
            if ev_load_latest_kw>1e-3:share=(min(ev_load_latest_kw,renewable_gen_latest_kw)/ev_load_latest_kw)*100;self.renewable_share_label.setText(f"可再生能源充电占比: {share:.1f} %")
            else:self.renewable_share_label.setText("可再生能源充电占比: N/A %")
            non_ev_load_latest_kw=total_load_latest_kw-ev_load_latest_kw;surplus_renewable_kw=renewable_gen_latest_kw-non_ev_load_latest_kw;v1g_potential_mw=max(0,surplus_renewable_kw)/1000;self.v1g_potential_label.setText(f"V1G 调度潜力: {v1g_potential_mw:.2f} MW")
            if self.current_region_key=="aggregated":current_ci=aggregated_metrics.get('weighted_carbon_intensity',"N/A");self.carbon_intensity_label.setText(f"平均碳强度: {current_ci:.2f} gCO₂/kWh"if isinstance(current_ci,(float,int))else"平均碳强度: N/A") # "Avg. Carbon Intensity"
            else:current_ci=carbon_intensity_series[-1]if carbon_intensity_series else"N/A";self.carbon_intensity_label.setText(f"碳强度: {current_ci:.2f} gCO₂/kWh"if isinstance(current_ci,(float,int))else"碳强度: N/A") # "Carbon Intensity"
        else:self.renewable_share_label.setText("可再生能源充电占比: N/A %");self.v1g_potential_label.setText("V1G 调度潜力: N/A MW");self.carbon_intensity_label.setText("实时碳强度: N/A")
        self._update_carbon_savings_display()
        if total_load_series:last_total_load_mw=total_load_series[-1]/1000;dummy_predictions=[max(0,last_total_load_mw+random.uniform(-last_total_load_mw*0.1,last_total_load_mw*0.1))for _ in range(24)];self.update_prediction_data(dummy_predictions)
        self.regional_comparison_table.setRowCount(0)
        if regional_comparison_data and'regions'in regional_comparison_data and'metrics'in regional_comparison_data:
            regions=regional_comparison_data['regions'];metrics=regional_comparison_data['metrics'];self.regional_comparison_table.setRowCount(len(regions))
            for i,region_id in enumerate(regions):
                total_load_kw=metrics.get('current_total_load',[])[i]if i<len(metrics.get('current_total_load',[]))else 0;load_share=metrics.get('grid_load_percentage',[])[i]if i<len(metrics.get('grid_load_percentage',[]))else 0;renewable_share=metrics.get('renewable_ratio',[])[i]if i<len(metrics.get('renewable_ratio',[]))else 0;ci=metrics.get('carbon_intensity',[])[i]if i<len(metrics.get('carbon_intensity',[]))else 0
                self.regional_comparison_table.setItem(i,0,QTableWidgetItem(str(region_id)));self.regional_comparison_table.setItem(i,1,QTableWidgetItem(f"{total_load_kw/1000:.2f}"));self.regional_comparison_table.setItem(i,2,QTableWidgetItem(f"{load_share:.1f}"));self.regional_comparison_table.setItem(i,3,QTableWidgetItem(f"{renewable_share*100:.1f}"));self.regional_comparison_table.setItem(i,4,QTableWidgetItem(f"{ci:.2f}"))
                for col in range(5):
                    if self.regional_comparison_table.item(i,col):self.regional_comparison_table.item(i,col).setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        overall_max_peak_load_kw=0;peak_load_region_id="N/A";peak_load_time_str="N/A";regional_ts_data=time_series_data.get('regional_data',{});all_timestamps=time_series_data.get('timestamps',[])
        if regional_ts_data and all_timestamps:
            for region_id,r_data in regional_ts_data.items():
                current_region_loads=r_data.get('total_load',[])
                if current_region_loads:
                    max_load_in_region_kw=max(current_region_loads)
                    if max_load_in_region_kw>overall_max_peak_load_kw:overall_max_peak_load_kw=max_load_in_region_kw;peak_load_region_id=region_id;peak_idx=current_region_loads.index(max_load_in_region_kw)
                    if peak_idx<len(all_timestamps):
                        try:dt_obj=datetime.fromisoformat(all_timestamps[peak_idx].replace('Z','+00:00'));peak_load_time_str=dt_obj.strftime('%Y-%m-%d %H:%M')
                        except ValueError:peak_load_time_str=all_timestamps[peak_idx]
            if overall_max_peak_load_kw>0:self.peak_load_insight_label.setText(f"最高峰值: {overall_max_peak_load_kw/1000:.2f} MW 位于 {peak_load_region_id} 时间 {peak_load_time_str}") # "Highest Peak", "in", "at"
            else:self.peak_load_insight_label.setText("最高峰值负荷 (当前仿真): N/A")
        else:self.peak_load_insight_label.setText("最高峰值负荷 (当前仿真): N/A")

    def update_prediction_data(self, prediction_values_mw):
        # ... (Existing code - unchanged)
        if not HAS_PYQTGRAPH or not hasattr(self,'load_curves_plot'):return
        if self.predicted_load_curve_item:self.load_curves_plot.removeItem(self.predicted_load_curve_item);self.predicted_load_curve_item=None
        if not prediction_values_mw:return
        start_x=self.last_plotted_timestamp_count;prediction_x_values=list(range(start_x,start_x+len(prediction_values_mw)))
        self.predicted_load_curve_item=self.load_curves_plot.plot(prediction_x_values,prediction_values_mw,pen=pg.mkPen(color=(100,100,255,200),width=2,style=Qt.PenStyle.DashLine),name="预测负荷")

    def handle_status_update(self, status_data_signal):
        # ... (Existing code - unchanged)
        logger.debug(f"PowerGridPanel: handle_status_update.");self._last_grid_status_data=status_data_signal
        # Example of how you might update it with real data later - FOR TESTING VISUALS
        # if HAS_PYQTGRAPH and self.decision_impact_plot:
        #     # Replace with actual data fetching logic for pre/post decision
        #     dummy_pre = [random.randint(80,150) for _ in range(self.last_plotted_timestamp_count if self.last_plotted_timestamp_count > 0 else 5)]
        #     dummy_post = [val - random.randint(5, 20) for val in dummy_pre]
        #     self.update_decision_impact_chart(dummy_pre, dummy_post)
        if not(self.main_window and self.main_window.simulation_worker and self.main_window.simulation_worker.environment and hasattr(self.main_window.simulation_worker.environment,'grid_simulator')):self.update_load_data({});return
        try:
            time_series_data=self.main_window.simulation_worker.environment.grid_simulator.get_time_series_data()
            grid_overall_status=self.main_window.simulation_worker.environment.grid_simulator.get_status()
            combined_data={"time_series":time_series_data if time_series_data else{},"aggregated_metrics":grid_overall_status.get('aggregated_metrics',{})if grid_overall_status else{},"regional_comparison":grid_overall_status.get('regional_comparison',{})if grid_overall_status else{}}
            if time_series_data:self.update_load_data(combined_data)
            else:logger.warning("Failed to extract time_series_data from grid_simulator.");self.update_load_data({})
        except Exception as e:logger.error(f"Error in handle_status_update: {e}",exc_info=True);self.update_load_data({})


if __name__ == '__main__':
    from PyQt6.QtWidgets import QApplication, QMainWindow
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # --- Dummy classes for testing ---
    class DummyGridSimulator:
        def get_time_series_data(self):
            num_points=random.randint(5,10);timestamps=[(datetime(2023,1,1,i,j*15,0)).isoformat()+"Z" for i in range(2) for j in range(4)];num_points=len(timestamps);regional_data={};self.region_names=[f"region_{reg_idx}"for reg_idx in range(2)]
            for reg_key in self.region_names:regional_data[reg_key]={'total_load':[random.uniform(80e3,150e3)for _ in range(num_points)],'base_load':[random.uniform(60e3,100e3)for _ in range(num_points)],'ev_load':[random.uniform(10e3,50e3)for _ in range(num_points)],'solar_generation':[random.uniform(0,40e3)for _ in range(num_points)],'wind_generation':[random.uniform(0,30e3)for _ in range(num_points)],'carbon_intensity':[random.uniform(100,500)for _ in range(num_points)]}
            return{'timestamps':timestamps,'regional_data':regional_data}
        def get_status(self):
            num_regions=len(getattr(self,'region_names',['region_0','region_1']));return{'aggregated_metrics':{'weighted_carbon_intensity':random.uniform(150,450)},'regional_comparison':{'regions':getattr(self,'region_names',['region_0','region_1']),'metrics':{'current_total_load':[random.uniform(80e3,150e3)for _ in range(num_regions)],'grid_load_percentage':[random.uniform(0.3,0.7)*100 for _ in range(num_regions)],'renewable_ratio':[random.uniform(0.1,0.6)for _ in range(num_regions)],'carbon_intensity':[random.uniform(100,500)for _ in range(num_regions)]}}}
    class DummyEnvironment:__init__=lambda self:setattr(self,'grid_simulator',DummyGridSimulator())
    class DummySimulationWorker:__init__=lambda self:setattr(self,'environment',DummyEnvironment())
    class DummyMainWindow(QMainWindow):__init__=lambda self:(super().__init__(),setattr(self,'simulation_worker',DummySimulationWorker()))

    # Method _create_decision_impact_section MOVED INTO PowerGridPanel CLASS
    # Method update_decision_impact_chart MOVED INTO PowerGridPanel CLASS

    app=QApplication(sys.argv)
    dummy_main=DummyMainWindow()
    panel=PowerGridPanel(main_window=dummy_main)
    panel.setWindowTitle("电网面板测试");panel.resize(800,2000);panel.show() # Increased height for new panel

    # --- Test Signal Connections ---
    def handle_grid_pref_change(name, value): logger.info(f"信号 gridPreferenceChanged: 名称='{name}', 值={value}") # SIGNAL, name, value
    def handle_v2g_request(amount_mw): logger.info(f"信号 v2gDischargeRequested: 电量={amount_mw} MW") # SIGNAL, amount
    panel.gridPreferenceChanged.connect(handle_grid_pref_change)
    panel.v2gDischargeRequested.connect(handle_v2g_request)

    logger.info("初始数据加载和显示 (默认策略和限制):") # Initial data load & display (default strategy & limits):
    status_data_example_signal={'state':{'grid_status':{}},'timestamp':datetime.now().isoformat()}
    panel.handle_status_update(status_data_example_signal)

    logger.info("\n测试调度控制:") # Testing Dispatch Controls:
    panel.charging_priority_combo.setCurrentText("优先可再生能源") # Prioritize Renewables
    panel.max_ev_load_spinbox.setValue(300.5)
    # To simulate button click, we can call the slot directly
    panel._on_apply_max_ev_load_limit()
    panel.v2g_request_spinbox.setValue(50.75)
    panel._on_activate_v2g_discharge()

    sys.exit(app.exec())
