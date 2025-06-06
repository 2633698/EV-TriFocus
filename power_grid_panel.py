import sys
import logging
import random
from datetime import datetime
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget,
    QTableWidgetItem, QHeaderView, QComboBox, QGroupBox, QGridLayout,
    QFormLayout, QPushButton, QDoubleSpinBox # Added missing imports
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

        main_layout = QVBoxLayout(self)
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


        main_layout.addStretch()
        self.setLayout(main_layout)

    def _create_load_monitoring_section(self):
        # ... (Existing code - unchanged)
        group_box = QGroupBox("Power Grid Load Monitoring");group_box.setFont(QFont("Arial", 12, QFont.Weight.Bold));group_layout = QVBoxLayout(group_box)
        controls_layout = QHBoxLayout();controls_layout.addWidget(QLabel("Select Region:"));self.region_combo = QComboBox()
        self.region_combo.addItems(["region_0", "region_1", "All Regions (Aggregated)"]);self.region_combo.currentTextChanged.connect(self._on_region_changed)
        controls_layout.addWidget(self.region_combo);controls_layout.addStretch();group_layout.addLayout(controls_layout);self.load_table = QTableWidget()
        self.load_table.setColumnCount(4);self.load_table.setHorizontalHeaderLabels(["Time", "Total Load (MW)", "Base Load (MW)", "EV Load (MW)"])
        self.load_table.setAlternatingRowColors(True);self.load_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.load_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch);self.load_table.verticalHeader().setVisible(False)
        group_layout.addWidget(self.load_table)
        if HAS_PYQTGRAPH:
            self.load_curves_plot = PlotWidget();self.load_curves_plot.setBackground('w')
            self.load_curves_plot.setLabel('left', 'Load / Generation (MW)', color='#333', **{'font-size': '10pt'})
            self.load_curves_plot.setLabel('bottom', 'Time Step', color='#333', **{'font-size': '10pt'})
            self.load_curves_plot.showGrid(x=True, y=True, alpha=0.3);self.load_curves_plot.addLegend(offset=(-10,10))
            self.total_load_curve = self.load_curves_plot.plot(pen=pg.mkPen(color=(0,0,255),width=2), name="Total Load")
            self.base_load_curve = self.load_curves_plot.plot(pen=pg.mkPen(color=(0,128,0),width=2), name="Base Load")
            self.ev_load_curve = self.load_curves_plot.plot(pen=pg.mkPen(color=(255,0,0),width=2), name="EV Load")
            self.solar_gen_curve_item = self.load_curves_plot.plot(pen=pg.mkPen(color=(255,165,0),width=2), name="Solar Gen.")
            self.wind_gen_curve_item = self.load_curves_plot.plot(pen=pg.mkPen(color=(135,206,235),width=2), name="Wind Gen.")
            group_layout.addWidget(self.load_curves_plot)
        else: group_layout.addWidget(QLabel("PyQtGraph library is required for charts.", alignment=Qt.AlignmentFlag.AlignCenter, styleSheet="color:red;font-weight:bold;padding:20px;"))
        return group_box


    def _create_renewable_analysis_section(self):
        # ... (Existing code - unchanged)
        group_box = QGroupBox("Renewable Energy Coordination");group_box.setFont(QFont("Arial",12,QFont.Weight.Bold));layout=QVBoxLayout(group_box);layout.setSpacing(10);metrics_layout=QHBoxLayout()
        self.renewable_share_label=QLabel("Renewable Charging Share: N/A %");self.renewable_share_label.setFont(QFont("Arial",10));metrics_layout.addWidget(self.renewable_share_label);metrics_layout.addStretch()
        self.v1g_potential_label=QLabel("V1G Dispatch Potential: N/A MW");self.v1g_potential_label.setFont(QFont("Arial",10));metrics_layout.addWidget(self.v1g_potential_label);metrics_layout.addStretch()
        layout.addLayout(metrics_layout);return group_box

    def _create_power_quality_section(self):
        # ... (Existing code - unchanged)
        group_box = QGroupBox("Power Quality & Stability");group_box.setFont(QFont("Arial",12,QFont.Weight.Bold));main_v_layout=QVBoxLayout(group_box);main_v_layout.setSpacing(10);strategy_h_layout=QHBoxLayout()
        strategy_h_layout.addWidget(QLabel("Charging Strategy:"));self.strategy_combo=QComboBox();self.strategy_combo.addItems(["Uncoordinated Charging","Smart Charging (V1G)","V2G Active"])
        self.strategy_combo.currentTextChanged.connect(self._on_strategy_changed);strategy_h_layout.addWidget(self.strategy_combo);strategy_h_layout.addStretch();main_v_layout.addLayout(strategy_h_layout)
        indicators_layout=QGridLayout();indicators_layout.setSpacing(10)
        indicators_layout.addWidget(QLabel("Voltage Stability:"),0,0);self.voltage_stability_label=QLabel("N/A");self.voltage_stability_label.setFont(QFont("Arial",10,QFont.Weight.Bold));indicators_layout.addWidget(self.voltage_stability_label,0,1)
        indicators_layout.addWidget(QLabel("Frequency Stability:"),1,0);self.frequency_stability_label=QLabel("N/A");self.frequency_stability_label.setFont(QFont("Arial",10,QFont.Weight.Bold));indicators_layout.addWidget(self.frequency_stability_label,1,1)
        indicators_layout.addWidget(QLabel("Grid Strain:"),2,0);self.grid_strain_label=QLabel("N/A");self.grid_strain_label.setFont(QFont("Arial",10,QFont.Weight.Bold));indicators_layout.addWidget(self.grid_strain_label,2,1)
        indicators_layout.setColumnStretch(2,1);main_v_layout.addLayout(indicators_layout);return group_box

    def _create_carbon_analysis_section(self):
        # ... (Existing code - unchanged)
        group_box = QGroupBox("Carbon Emission Footprint");group_box.setFont(QFont("Arial",12,QFont.Weight.Bold));layout=QVBoxLayout(group_box);layout.setSpacing(10);metrics_layout=QHBoxLayout()
        self.carbon_intensity_label=QLabel("Real-time Carbon Intensity: N/A gCO₂/kWh");self.carbon_intensity_label.setFont(QFont("Arial",10));metrics_layout.addWidget(self.carbon_intensity_label);metrics_layout.addStretch()
        self.carbon_savings_label=QLabel("Optimized Charging Savings: N/A kg CO₂");self.carbon_savings_label.setFont(QFont("Arial",10));metrics_layout.addWidget(self.carbon_savings_label);metrics_layout.addStretch()
        layout.addLayout(metrics_layout);return group_box

    def _create_regional_comparison_section(self):
        # ... (Existing code - unchanged)
        group_box = QGroupBox("Regional Comparison & Planning Support");group_box.setFont(QFont("Arial",12,QFont.Weight.Bold));layout=QVBoxLayout(group_box);layout.setSpacing(10)
        layout.addWidget(QLabel("Regional Metrics Comparison:"));self.regional_comparison_table=QTableWidget();self.regional_comparison_table.setColumnCount(5)
        self.regional_comparison_table.setHorizontalHeaderLabels(["Region","Total Load (MW)","Load Share (%)","Renewable Share (%)","Carbon Intensity (gCO₂/kWh)"])
        self.regional_comparison_table.setAlternatingRowColors(True);self.regional_comparison_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.regional_comparison_table.horizontalHeader().setStretchLastSection(True);self.regional_comparison_table.verticalHeader().setVisible(False);self.regional_comparison_table.setFixedHeight(150)
        layout.addWidget(self.regional_comparison_table);layout.addWidget(QLabel("Planning Support Insights:"))
        self.peak_load_insight_label=QLabel("Highest Peak Load (Current Sim): N/A");self.peak_load_insight_label.setFont(QFont("Arial",10));layout.addWidget(self.peak_load_insight_label);return group_box

    def _create_grid_dispatch_control_section(self):
        group_box = QGroupBox("Grid Dispatch Control")
        group_box.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        form_layout = QFormLayout(group_box)
        form_layout.setSpacing(10)
        form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        # Charging Priority
        self.charging_priority_combo = QComboBox()
        self.charging_priority_combo.addItems(["Balanced", "Prioritize Renewables", "Minimize Cost", "Peak Shaving"])
        self.charging_priority_combo.currentTextChanged.connect(self._on_charging_priority_changed)
        form_layout.addRow(QLabel("Grid Charging Priority:"), self.charging_priority_combo)

        # Max EV Charging Impact Limit
        max_ev_load_layout = QHBoxLayout()
        self.max_ev_load_spinbox = QDoubleSpinBox()
        self.max_ev_load_spinbox.setRange(0, 10000) # MW
        self.max_ev_load_spinbox.setValue(500)    # Default
        self.max_ev_load_spinbox.setSuffix(" MW")
        max_ev_load_layout.addWidget(self.max_ev_load_spinbox)
        apply_limit_btn = QPushButton("Apply Limit")
        apply_limit_btn.clicked.connect(self._on_apply_max_ev_load_limit)
        max_ev_load_layout.addWidget(apply_limit_btn)
        form_layout.addRow(QLabel("Max EV Fleet Load:"), max_ev_load_layout)

        # V2G Dispatch Request
        v2g_request_layout = QHBoxLayout()
        self.v2g_request_spinbox = QDoubleSpinBox()
        self.v2g_request_spinbox.setRange(0, 1000) # MW
        self.v2g_request_spinbox.setValue(0)
        self.v2g_request_spinbox.setSuffix(" MW")
        v2g_request_layout.addWidget(self.v2g_request_spinbox)
        activate_v2g_btn = QPushButton("Activate V2G")
        activate_v2g_btn.clicked.connect(self._on_activate_v2g_discharge)
        v2g_request_layout.addWidget(activate_v2g_btn)
        form_layout.addRow(QLabel("Request V2G Discharge:"), v2g_request_layout)

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
        logger.debug(f"Strategy changed to: {strategy_text}");strategy_styles={"Uncoordinated Charging":{"voltage":("Risk of Fluctuation","orange"),"frequency":("Slight Fluctuation","orange"),"strain":("Elevated","red")},"Smart Charging (V1G)":{"voltage":("Stable","green"),"frequency":("Stable","green"),"strain":("Normal","green")},"V2G Active":{"voltage":("Dynamic (Managed)","#5DADE2"),"frequency":("Dynamic (Managed)","#5DADE2"),"strain":("Variable (Bidirectional)","#F39C12")}};default_style={"voltage":("N/A","black"),"frequency":("N/A","black"),"strain":("N/A","black")};current_styles=strategy_styles.get(strategy_text,default_style)
        self.voltage_stability_label.setText(current_styles["voltage"][0]);self.voltage_stability_label.setStyleSheet(f"color: {current_styles['voltage'][1]}; font-weight: bold;")
        self.frequency_stability_label.setText(current_styles["frequency"][0]);self.frequency_stability_label.setStyleSheet(f"color: {current_styles['frequency'][1]}; font-weight: bold;")
        self.grid_strain_label.setText(current_styles["strain"][0]);self.grid_strain_label.setStyleSheet(f"color: {current_styles['strain'][1]}; font-weight: bold;")
        self._update_carbon_savings_display()

    def _update_carbon_savings_display(self):
        # ... (Existing code - unchanged)
        if not hasattr(self,'strategy_combo')or not hasattr(self,'carbon_savings_label'):return
        strategy=self.strategy_combo.currentText()
        if strategy=="Smart Charging (V1G)":savings=random.uniform(5,15);self.carbon_savings_label.setText(f"Est. Savings (Smart): {savings:.1f} kg CO₂")
        elif strategy=="V2G Active":savings=random.uniform(10,30);self.carbon_savings_label.setText(f"Est. Savings (V2G): {savings:.1f} kg CO₂")
        else:self.carbon_savings_label.setText("Optimized Charging Savings: N/A")

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
            self.last_plotted_timestamp_count=0;self.renewable_share_label.setText("Renewable Charging Share: N/A %");self.v1g_potential_label.setText("V1G Dispatch Potential: N/A MW");self.carbon_intensity_label.setText("Real-time Carbon Intensity: N/A gCO₂/kWh");self.regional_comparison_table.setRowCount(0);self.peak_load_insight_label.setText("Highest Peak Load (Current Sim): N/A")
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
            if ev_load_latest_kw>1e-3:share=(min(ev_load_latest_kw,renewable_gen_latest_kw)/ev_load_latest_kw)*100;self.renewable_share_label.setText(f"Renewable Charging Share: {share:.1f} %")
            else:self.renewable_share_label.setText("Renewable Charging Share: N/A %")
            non_ev_load_latest_kw=total_load_latest_kw-ev_load_latest_kw;surplus_renewable_kw=renewable_gen_latest_kw-non_ev_load_latest_kw;v1g_potential_mw=max(0,surplus_renewable_kw)/1000;self.v1g_potential_label.setText(f"V1G Dispatch Potential: {v1g_potential_mw:.2f} MW")
            if self.current_region_key=="aggregated":current_ci=aggregated_metrics.get('weighted_carbon_intensity',"N/A");self.carbon_intensity_label.setText(f"Avg. Carbon Intensity: {current_ci:.2f} gCO₂/kWh"if isinstance(current_ci,(float,int))else"Avg. Carbon Intensity: N/A")
            else:current_ci=carbon_intensity_series[-1]if carbon_intensity_series else"N/A";self.carbon_intensity_label.setText(f"Carbon Intensity: {current_ci:.2f} gCO₂/kWh"if isinstance(current_ci,(float,int))else"Carbon Intensity: N/A")
        else:self.renewable_share_label.setText("Renewable Charging Share: N/A %");self.v1g_potential_label.setText("V1G Dispatch Potential: N/A MW");self.carbon_intensity_label.setText("Real-time Carbon Intensity: N/A")
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
            if overall_max_peak_load_kw>0:self.peak_load_insight_label.setText(f"Highest Peak: {overall_max_peak_load_kw/1000:.2f} MW in {peak_load_region_id} at {peak_load_time_str}")
            else:self.peak_load_insight_label.setText("Highest Peak Load (Current Sim): N/A")
        else:self.peak_load_insight_label.setText("Highest Peak Load (Current Sim): N/A")

    def update_prediction_data(self, prediction_values_mw):
        # ... (Existing code - unchanged)
        if not HAS_PYQTGRAPH or not hasattr(self,'load_curves_plot'):return
        if self.predicted_load_curve_item:self.load_curves_plot.removeItem(self.predicted_load_curve_item);self.predicted_load_curve_item=None
        if not prediction_values_mw:return
        start_x=self.last_plotted_timestamp_count;prediction_x_values=list(range(start_x,start_x+len(prediction_values_mw)))
        self.predicted_load_curve_item=self.load_curves_plot.plot(prediction_x_values,prediction_values_mw,pen=pg.mkPen(color=(100,100,255,200),width=2,style=Qt.PenStyle.DashLine),name="Predicted Load")

    def handle_status_update(self, status_data_signal):
        # ... (Existing code - unchanged)
        logger.debug(f"PowerGridPanel: handle_status_update.");self._last_grid_status_data=status_data_signal
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

    app=QApplication(sys.argv)
    dummy_main=DummyMainWindow()
    panel=PowerGridPanel(main_window=dummy_main)
    panel.setWindowTitle("Power Grid Panel Test");panel.resize(800,1200);panel.show()

    # --- Test Signal Connections ---
    def handle_grid_pref_change(name, value): logger.info(f"SIGNAL gridPreferenceChanged: name='{name}', value={value}")
    def handle_v2g_request(amount_mw): logger.info(f"SIGNAL v2gDischargeRequested: amount={amount_mw} MW")
    panel.gridPreferenceChanged.connect(handle_grid_pref_change)
    panel.v2gDischargeRequested.connect(handle_v2g_request)

    logger.info("Initial data load & display (default strategy & limits):")
    status_data_example_signal={'state':{'grid_status':{}},'timestamp':datetime.now().isoformat()}
    panel.handle_status_update(status_data_example_signal)

    logger.info("\nTesting Dispatch Controls:")
    panel.charging_priority_combo.setCurrentText("Prioritize Renewables")
    panel.max_ev_load_spinbox.setValue(300.5)
    # To simulate button click, we can call the slot directly
    panel._on_apply_max_ev_load_limit()
    panel.v2g_request_spinbox.setValue(50.75)
    panel._on_activate_v2g_discharge()

    sys.exit(app.exec())
