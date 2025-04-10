// Global variables
let simulation = {
    running: false,
    gridData: {
        hourlyLoad: Array(24).fill(0),
        evLoad: Array(24).fill(0),
        renewableGeneration: []
    }
};

// Charts
let realTimeLoadChart;
let loadCompositionChart;
let evLoadGauge;
let hourlyEvLoadChart;
let renewableEnergyChart;
let schedulingEffectChart;

// DOM Elements
const startBtn = document.getElementById('btn-start-simulation');
const pauseBtn = document.getElementById('btn-pause-simulation');
const resetBtn = document.getElementById('btn-reset-simulation');
const currentLoad = document.getElementById('current-load');
const renewableRatio = document.getElementById('renewable-ratio');
const peakLoadRatio = document.getElementById('peak-load-ratio');
const loadBalanceIndex = document.getElementById('load-balance-index');

// Initialize the dashboard
document.addEventListener('DOMContentLoaded', function() {
    // Set up event listeners
    setupEventListeners();
    
    // Initialize charts
    initializeCharts();
    
    // Update system time
    updateSystemTime();
    
    // Start status update interval
    setInterval(updateSimulationStatus, 1000);
});

// Setup event listeners
function setupEventListeners() {
    // Simulation controls
    startBtn.addEventListener('click', startSimulation);
    pauseBtn.addEventListener('click', pauseSimulation);
    resetBtn.addEventListener('click', resetSimulation);
    
    // Strategy radio buttons
    const strategyRadios = document.querySelectorAll('input[name="load-strategy"]');
    strategyRadios.forEach(radio => {
        radio.addEventListener('change', updateLoadStrategy);
    });
    
    // Time range selector
    document.getElementById('load-time-range').addEventListener('change', updateTimeRange);
}

// Initialize charts
function initializeCharts() {
    // 1. Real-time Load Chart
    const realTimeLoadCtx = document.getElementById('real-time-load-chart').getContext('2d');
    realTimeLoadChart = new Chart(realTimeLoadCtx, {
        type: 'line',
        data: {
            labels: Array.from({length: 24}, (_, i) => `${i}:00`),
            datasets: [
                {
                    label: '基础负载',
                    data: [40, 35, 30, 28, 27, 30, 45, 60, 75, 80, 82, 84, 80, 75, 70, 65, 70, 75, 85, 90, 80, 70, 60, 50],
                    borderColor: '#6c757d',
                    backgroundColor: 'rgba(108, 117, 125, 0.1)',
                    borderDashed: [5, 5],
                    tension: 0.1,
                    fill: true
                },
                {
                    label: 'EV充电负载',
                    data: [5, 3, 2, 1, 1, 2, 8, 15, 18, 16, 13, 14, 15, 17, 13, 10, 15, 17, 12, 10, 8, 7, 6, 6],
                    borderColor: '#0dcaf0',
                    backgroundColor: 'rgba(13, 202, 240, 0.2)',
                    tension: 0.1,
                    fill: true
                },
                {
                    label: '总负载',
                    data: [45, 38, 32, 29, 28, 32, 53, 75, 93, 96, 95, 98, 95, 92, 83, 75, 85, 92, 97, 100, 88, 77, 66, 56],
                    borderColor: '#dc3545',
                    backgroundColor: 'rgba(220, 53, 69, 0.1)',
                    tension: 0.1,
                    borderWidth: 2,
                    fill: false
                }
            ]
        },
        options: {
            responsive: true,
            interaction: {
                mode: 'index',
                intersect: false,
            },
            plugins: {
                legend: {
                    position: 'top',
                },
                annotation: {
                    annotations: {
                        peakArea: {
                            type: 'box',
                            xMin: 7,
                            xMax: 10,
                            yMin: 0,
                            yMax: 100,
                            backgroundColor: 'rgba(255, 99, 132, 0.1)',
                            borderColor: 'rgba(255, 99, 132, 0)',
                        },
                        peakArea2: {
                            type: 'box',
                            xMin: 18,
                            xMax: 21,
                            yMin: 0,
                            yMax: 100,
                            backgroundColor: 'rgba(255, 99, 132, 0.1)',
                            borderColor: 'rgba(255, 99, 132, 0)',
                        },
                        valleyArea: {
                            type: 'box',
                            xMin: 0,
                            xMax: 5,
                            yMin: 0,
                            yMax: 100,
                            backgroundColor: 'rgba(54, 162, 235, 0.1)',
                            borderColor: 'rgba(54, 162, 235, 0)',
                        },
                    }
                }
            },
            scales: {
                y: {
                    min: 0,
                    max: 100,
                    title: {
                        display: true,
                        text: '负载（%）'
                    }
                }
            }
        }
    });
    
    // 2. Load Composition Chart
    const loadCompositionCtx = document.getElementById('load-composition-chart').getContext('2d');
    loadCompositionChart = new Chart(loadCompositionCtx, {
        type: 'pie',
        data: {
            labels: ['住宅用电', '商业用电', '工业用电', 'EV充电', '公共设施'],
            datasets: [{
                data: [35, 25, 20, 11, 9],
                backgroundColor: [
                    'rgba(13, 110, 253, 0.7)',
                    'rgba(25, 135, 84, 0.7)',
                    'rgba(255, 193, 7, 0.7)',
                    'rgba(13, 202, 240, 0.7)',
                    'rgba(108, 117, 125, 0.7)'
                ],
                borderColor: [
                    'rgb(13, 110, 253)',
                    'rgb(25, 135, 84)',
                    'rgb(255, 193, 7)',
                    'rgb(13, 202, 240)',
                    'rgb(108, 117, 125)'
                ],
                borderWidth:
                 1
            }]
        },
        options: {
            responsive: true,
            plugins: {
                legend: {
                    position: 'right'
                },
                title: {
                    display: true,
                    text: '负载构成分析'
                }
            }
        }
    });
    
    // 3. EV Load Gauge (simulated with a doughnut chart)
    const evLoadGaugeCtx = document.getElementById('ev-load-gauge').getContext('2d');
    evLoadGauge = new Chart(evLoadGaugeCtx, {
        type: 'doughnut',
        data: {
            labels: ['EV充电负载', '其他负载'],
            datasets: [{
                data: [11, 89],
                backgroundColor: [
                    'rgba(13, 110, 253, 0.7)',
                    'rgba(233, 236, 239, 0.4)'
                ],
                borderColor: [
                    'rgb(13, 110, 253)',
                    'rgba(233, 236, 239, 0)'
                ],
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            cutout: '80%',
            circumference: 360,
            rotation: -90,
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    enabled: false
                }
            }
        }
    });
    
    // 4. Hourly EV Load Chart
    const hourlyEvLoadCtx = document.getElementById('hourly-ev-load-chart').getContext('2d');
    hourlyEvLoadChart = new Chart(hourlyEvLoadCtx, {
        type: 'bar',
        data: {
            labels: Array.from({length: 24}, (_, i) => `${i}:00`),
            datasets: [
                {
                    label: '实际EV充电负载',
                    data: [5, 3, 2, 1, 1, 2, 8, 15, 18, 16, 13, 14, 15, 17, 13, 10, 15, 17, 12, 10, 8, 7, 6, 6],
                    backgroundColor: 'rgba(13, 202, 240, 0.7)',
                    borderColor: 'rgb(13, 202, 240)',
                    borderWidth: 1
                },
                {
                    label: '最优调度计划',
                    data: [8, 7, 6, 5, 4, 5, 9, 12, 15, 13, 12, 12, 14, 15, 12, 10, 13, 15, 10, 9, 8, 7, 6, 9],
                    backgroundColor: 'rgba(25, 135, 84, 0.7)',
                    borderColor: 'rgb(25, 135, 84)',
                    borderWidth: 1,
                    type: 'line',
                    fill: false
                }
            ]
        },
        options: {
            responsive: true,
            plugins: {
                legend: {
                    position: 'top'
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    title: {
                        display: true,
                        text: '负载 (MW)'
                    }
                }
            }
        }
    });
    
    // 5. Renewable Energy Chart
    const renewableEnergyCtx = document.getElementById('renewable-energy-chart').getContext('2d');
    renewableEnergyChart = new Chart(renewableEnergyCtx, {
        type: 'line',
        data: {
            labels: Array.from({length: 24}, (_, i) => `${i}:00`),
            datasets: [
                {
                    label: '太阳能发电',
                    data: [0, 0, 0, 0, 0, 0, 2, 10, 18, 25, 30, 32, 30, 28, 25, 20, 10, 3, 0, 0, 0, 0, 0, 0],
                    borderColor: '#ffc107',
                    backgroundColor: 'rgba(255, 193, 7, 0.2)',
                    tension: 0.3,
                    fill: true
                },
                {
                    label: '风能发电',
                    data: [12, 14, 15, 13, 10, 12, 15, 17, 13, 10, 12, 13, 15, 17, 16, 14, 16, 18, 20, 18, 16, 15, 13, 14],
                    borderColor: '#0dcaf0',
                    backgroundColor: 'rgba(13, 202, 240, 0.2)',
                    tension: 0.3,
                    fill: true
                },
                {
                    label: 'EV充电负载',
                    data: [5, 3, 2, 1, 1, 2, 8, 15, 18, 16, 13, 14, 15, 17, 13, 10, 15, 17, 12, 10, 8, 7, 6, 6],
                    borderColor: '#0d6efd',
                    backgroundColor: 'rgba(13, 110, 253, 0.2)',
                    tension: 0.3,
                    fill: true,
                    borderDash: [5, 5]
                }
            ]
        },
        options: {
            responsive: true,
            plugins: {
                legend: {
                    position: 'top'
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    title: {
                        display: true,
                        text: '发电量/负载 (MW)'
                    }
                }
            }
        }
    });
    
    // 6. Scheduling Effect Chart
    const schedulingEffectCtx = document.getElementById('scheduling-effect-chart').getContext('2d');
    schedulingEffectChart = new Chart(schedulingEffectCtx, {
        type: 'line',
        data: {
            labels: Array.from({length: 24}, (_, i) => `${i}:00`),
            datasets: [
                {
                    label: '有序调度',
                    data: [45, 38, 32, 29, 28, 32, 53, 75, 88, 91, 90, 93, 90, 87, 83, 75, 80, 87, 92, 95, 83, 77, 66, 56],
                    borderColor: '#198754',
                    backgroundColor: 'rgba(25, 135, 84, 0.1)',
                    tension: 0.2,
                    fill: false,
                    borderWidth: 2
                },
                {
                    label: '无序充电',
                    data: [45, 38, 32, 29, 28, 32, 53, 85, 110, 115, 105, 103, 100, 97, 90, 88, 95, 110, 118, 120, 95, 84, 70, 56],
                    borderColor: '#dc3545',
                    backgroundColor: 'rgba(220, 53, 69, 0.1)',
                    tension: 0.2,
                    fill: false,
                    borderWidth: 2
                }
            ]
        },
        options: {
            responsive: true,
            plugins: {
                legend: {
                    position: 'top'
                }
            },
            scales: {
                y: {
                    min: 0,
                    max: 130,
                    title: {
                        display: true,
                        text: '负载 (%)'
                    }
                }
            }
        }
    });
}

// Start simulation
function startSimulation() {
    // Check if simulation is already running
    if (simulation.running) {
        return;
    }
    
    // Get load strategy
    const strategyInputs = document.querySelectorAll('input[name="load-strategy"]');
    let selectedStrategy = 'balanced';
    
    strategyInputs.forEach(input => {
        if (input.checked) {
            switch(input.id) {
                case 'strategy1':
                    selectedStrategy = 'balanced';
                    break;
                case 'strategy2':
                    selectedStrategy = 'grid';
                    break;
                case 'strategy3':
                    selectedStrategy = 'renewable';
                    break;
                case 'strategy4':
                    selectedStrategy = 'cost';
                    break;
            }
        }
    });
    
    // Send request to start simulation
    fetch('/api/simulation/start', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            days: 7,
            strategy: 'grid', // Grid perspective uses grid-friendly strategy
            use_multi_agent: true,
            load_strategy: selectedStrategy
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'success') {
            simulation.running = true;
            
            // Update UI
            startBtn.disabled = true;
            pauseBtn.disabled = false;
            resetBtn.disabled = false;
            
            showNotification('模拟开始运行', 'success');
            
            // Fetch initial grid data
            fetchGridData();
        } else {
            showNotification(data.message || '启动模拟失败', 'danger');
        }
    })
    .catch(error => {
        console.error('Error starting simulation:', error);
        showNotification('启动模拟失败', 'danger');
    });
}

// Pause simulation
function pauseSimulation() {
    if (!simulation.running) {
        return;
    }
    
    fetch('/api/simulation/stop', {
        method: 'POST'
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'success') {
            simulation.running = false;
            
            // Update UI
            startBtn.disabled = false;
            pauseBtn.disabled = true;
            
            showNotification('模拟已暂停', 'warning');
        } else {
            showNotification(data.message || '暂停模拟失败', 'danger');
        }
    })
    .catch(error => {
        console.error('Error pausing simulation:', error);
        showNotification('暂停模拟失败', 'danger');
    });
}

// Reset simulation
function resetSimulation() {
    // If simulation is running, stop it first
    if (simulation.running) {
        pauseSimulation();
    }
    
    // Reset UI
    startBtn.disabled = false;
    pauseBtn.disabled = true;
    resetBtn.disabled = true;
    
    // Reset data
    simulation.gridData = {
        hourlyLoad: Array(24).fill(0),
        evLoad: Array(24).fill(0),
        renewableGeneration: []
    };
    
    // Reset charts
    resetCharts();
    
    // Reset grid status
    currentLoad.textContent = '0%';
    renewableRatio.textContent = '0%';
    peakLoadRatio.textContent = '0%';
    loadBalanceIndex.textContent = '0';
    
    showNotification('模拟已重置', 'info');
}

// Reset charts to initial state
function resetCharts() {
    // Reset real-time load chart
    realTimeLoadChart.data.datasets[0].data = [40, 35, 30, 28, 27, 30, 45, 60, 75, 80, 82, 84, 80, 75, 70, 65, 70, 75, 85, 90, 80, 70, 60, 50];
    realTimeLoadChart.data.datasets[1].data = [5, 3, 2, 1, 1, 2, 8, 15, 18, 16, 13, 14, 15, 17, 13, 10, 15, 17, 12, 10, 8, 7, 6, 6];
    realTimeLoadChart.data.datasets[2].data = [45, 38, 32, 29, 28, 32, 53, 75, 93, 96, 95, 98, 95, 92, 83, 75, 85, 92, 97, 100, 88, 77, 66, 56];
    realTimeLoadChart.update();
    
    // Reset load composition chart
    loadCompositionChart.data.datasets[0].data = [35, 25, 20, 11, 9];
    loadCompositionChart.update();
    
    // Reset EV load gauge
    evLoadGauge.data.datasets[0].data = [11, 89];
    evLoadGauge.update();
    
    // Reset hourly EV load chart
    hourlyEvLoadChart.data.datasets[0].data = [5, 3, 2, 1, 1, 2, 8, 15, 18, 16, 13, 14, 15, 17, 13, 10, 15, 17, 12, 10, 8, 7, 6, 6];
    hourlyEvLoadChart.data.datasets[1].data = [8, 7, 6, 5, 4, 5, 9, 12, 15, 13, 12, 12, 14, 15, 12, 10, 13, 15, 10, 9, 8, 7, 6, 9];
    hourlyEvLoadChart.update();
    
    // Reset renewable energy chart
    renewableEnergyChart.data.datasets[0].data = [0, 0, 0, 0, 0, 0, 2, 10, 18, 25, 30, 32, 30, 28, 25, 20, 10, 3, 0, 0, 0, 0, 0, 0];
    renewableEnergyChart.data.datasets[1].data = [12, 14, 15, 13, 10, 12, 15, 17, 13, 10, 12, 13, 15, 17, 16, 14, 16, 18, 20, 18, 16, 15, 13, 14];
    renewableEnergyChart.data.datasets[2].data = [5, 3, 2, 1, 1, 2, 8, 15, 18, 16, 13, 14, 15, 17, 13, 10, 15, 17, 12, 10, 8, 7, 6, 6];
    renewableEnergyChart.update();
    
    // Reset scheduling effect chart
    schedulingEffectChart.data.datasets[0].data = [45, 38, 32, 29, 28, 32, 53, 75, 88, 91, 90, 93, 90, 87, 83, 75, 80, 87, 92, 95, 83, 77, 66, 56];
    schedulingEffectChart.data.datasets[1].data = [45, 38, 32, 29, 28, 32, 53, 85, 110, 115, 105, 103, 100, 97, 90, 88, 95, 110, 118, 120, 95, 84, 70, 56];
    schedulingEffectChart.update();
}

// Update load strategy
function updateLoadStrategy() {
    const strategyInputs = document.querySelectorAll('input[name="load-strategy"]');
    let selectedStrategy = '';
    
    strategyInputs.forEach(input => {
        if (input.checked) {
            selectedStrategy = input.id;
        }
    });
    
    // Update hourly EV load chart based on selected strategy
    let optimalLoad;
    
    switch(selectedStrategy) {
        case 'strategy1': // 平滑负载曲线
            optimalLoad = [8, 7, 6, 5, 4, 5, 9, 12, 15, 13, 12, 12, 14, 15, 12, 10, 13, 15, 10, 9, 8, 7, 6, 9];
            break;
        case 'strategy2': // 削峰填谷
            optimalLoad = [10, 9, 8, 7, 6, 8, 6, 8, 10, 9, 10, 12, 14, 15, 12, 10, 9, 8, 7, 8, 9, 10, 12, 14];
            break;
        case 'strategy3': // 可再生能源优先
            optimalLoad = [3, 4, 5, 4, 3, 4, 6, 15, 20, 22, 25, 27, 25, 24, 20, 18, 12, 7, 5, 3, 2, 3, 4, 5];
            break;
        case 'strategy4': // 成本最小化
            optimalLoad = [18, 16, 14, 12, 10, 12, 8, 6, 8, 10, 12, 11, 10, 9, 8, 6, 5, 6, 8, 7, 6, 10, 12, 14];
            break;
        default:
            optimalLoad = [8, 7, 6, 5, 4, 5, 9, 12, 15, 13, 12, 12, 14, 15, 12, 10, 13, 15, 10, 9, 8, 7, 6, 9];
    }
    
    // Update chart
    hourlyEvLoadChart.data.datasets[1].data = optimalLoad;
    hourlyEvLoadChart.update();
    
    showNotification('调度策略已更新', 'success');
}

// Update time range for load chart
function updateTimeRange() {
    const timeRange = document.getElementById('load-time-range').value;
    
    // Update x-axis labels based on selected time range
    if (timeRange === '24h') {
        // Just use hourly labels for 24 hours
        realTimeLoadChart.data.labels = Array.from({length: 24}, (_, i) => `${i}:00`);
    } else if (timeRange === '7d') {
        // Use day labels for 7 days
        realTimeLoadChart.data.labels = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'];
        // Generate random data for 7 days (simplified)
        realTimeLoadChart.data.datasets[0].data = Array.from({length: 7}, () => Math.random() * 30 + 40);
        realTimeLoadChart.data.datasets[1].data = Array.from({length: 7}, () => Math.random() * 10 + 5);
        realTimeLoadChart.data.datasets[2].data = realTimeLoadChart.data.datasets[0].data.map((val, idx) => 
            val + realTimeLoadChart.data.datasets[1].data[idx]);
    } else if (timeRange === '30d') {
        // Use week labels for 30 days
        realTimeLoadChart.data.labels = ['第1周', '第2周', '第3周', '第4周', '第5周'];
        // Generate random data for 5 weeks (simplified)
        realTimeLoadChart.data.datasets[0].data = Array.from({length: 5}, () => Math.random() * 20 + 50);
        realTimeLoadChart.data.datasets[1].data = Array.from({length: 5}, () => Math.random() * 8 + 8);
        realTimeLoadChart.data.datasets[2].data = realTimeLoadChart.data.datasets[0].data.map((val, idx) => 
            val + realTimeLoadChart.data.datasets[1].data[idx]);
    }
    
    realTimeLoadChart.update();
}

// Fetch grid data
function fetchGridData() {
    fetch('/api/grid')
        .then(response => response.json())
        .then(data => {
            updateGridData(data);
        })
        .catch(error => {
            console.error('Error fetching grid data:', error);
        });
}

// Update grid data
function updateGridData(data) {
    // Update simulation grid data
    if (data.base_load) {
        simulation.gridData.hourlyLoad = data.base_load;
    }
    
    // Update charts with real data if available
    if (data.base_load && data.base_load.length === 24) {
        realTimeLoadChart.data.datasets[0].data = data.base_load;
        
        // Calculate total load
        const totalLoad = data.base_load.map((val, idx) => {
            const evLoad = simulation.gridData.evLoad[idx] || 0;
            return val + evLoad;
        });
        
        realTimeLoadChart.data.datasets[2].data = totalLoad;
        realTimeLoadChart.update();
    }
}

// Update grid metrics
function updateGridMetrics(metrics) {
    console.log("updateGridMetrics called with:", metrics);
    
    // 确保所有数据都是数字类型
    const safeMetrics = {
        current_load: parseFloat(metrics.current_load || 0),
        renewable_ratio: parseFloat(metrics.renewable_ratio || 0),
        peak_load_ratio: parseFloat(metrics.peak_load_ratio || 0),
        load_balance_index: parseFloat(metrics.load_balance_index || 0)
    };
    
    // 更新当前负载
    if (currentLoad) {
        animateCounter(currentLoad, parseInt(currentLoad.textContent) || 0, safeMetrics.current_load, '', '%');
    }
    
    // 更新可再生能源比例
    if (renewableRatio) {
        animateCounter(renewableRatio, parseInt(renewableRatio.textContent) || 0, safeMetrics.renewable_ratio, '', '%');
    }
    
    // 更新峰值负载比例
    if (peakLoadRatio) {
        animateCounter(peakLoadRatio, parseInt(peakLoadRatio.textContent) || 0, safeMetrics.peak_load_ratio, '', '%');
    }
    
    // 更新负载平衡指数
    if (loadBalanceIndex) {
        animateCounter(loadBalanceIndex, parseFloat(loadBalanceIndex.textContent) || 0, safeMetrics.load_balance_index, '', '');
    }
    
    console.log("Grid metrics updated successfully");
}

// Animate counter
function animateCounter(element, start, end, prefix = '', suffix = '') {
    if (!element) return;
    
    const duration = 1000; // ms
    const stepTime = 50; // ms
    const steps = duration / stepTime;
    const increment = (end - start) / steps;
    let current = start;
    
    const timer = setInterval(() => {
        current += increment;
        
        if ((increment > 0 && current >= end) || (increment < 0 && current <= end)) {
            clearInterval(timer);
            current = end;
        }
        
        // Format number
        let formattedValue;
        if (Number.isInteger(end)) {
            formattedValue = Math.round(current).toLocaleString();
        } else {
            formattedValue = current.toFixed(2);
        }
        
        element.textContent = `${prefix}${formattedValue}${suffix}`;
    }, stepTime);
}

// Update EV load data
function updateEvLoad(evLoad) {
    if (!evLoad || evLoad.length !== 24) return;
    
    // Update simulation data
    simulation.gridData.evLoad = evLoad;
    
    // Update chart
    hourlyEvLoadChart.data.datasets[0].data = evLoad;
    hourlyEvLoadChart.update();
    
    // Update real-time load chart
    realTimeLoadChart.data.datasets[1].data = evLoad;
    
    // Update total load
    const baseLoad = realTimeLoadChart.data.datasets[0].data;
    const totalLoad = baseLoad.map((val, idx) => val + evLoad[idx]);
    realTimeLoadChart.data.datasets[2].data = totalLoad;
    realTimeLoadChart.update();
    
    // Update EV load gauge
    const totalGridLoad = totalLoad.reduce((sum, val) => sum + val, 0);
    const totalEvLoad = evLoad.reduce((sum, val) => sum + val, 0);
    const evPercentage = Math.round((totalEvLoad / totalGridLoad) * 100);
    
    evLoadGauge.data.datasets[0].data = [evPercentage, 100 - evPercentage];
    evLoadGauge.update();
    document.getElementById('ev-load-percentage').textContent = `${evPercentage}%`;
}

// Update simulation status
function updateSimulationStatus() {
    if (!simulation.running && startBtn.disabled) {
        // Simulation was stopped externally
        startBtn.disabled = false;
        pauseBtn.disabled = true;
        return;
    }
    
    if (!simulation.running) {
        return;
    }
    
    fetch('/api/simulation/status')
        .then(response => response.json())
        .then(data => {
            if (data.running !== simulation.running) {
                simulation.running = data.running;
                startBtn.disabled = data.running;
                pauseBtn.disabled = !data.running;
            }
            
            if (data.state) {
                // Update grid status
                const gridLoad = data.state.grid_load || 65;
                
                // Update metrics with real data when available
                const metricsData = {
                    current_load: data.state.grid_load || 0,
                    renewable_ratio: data.state.metrics?.renewable_ratio || 0,
                    peak_load_ratio: 0,
                    load_balance_index: 0.8
                };
                
                // Use real metrics if available
                if (data.state.metrics) {
                    // 首先检查数据格式并打印日志
                    console.log("Grid metrics received:", data.state.metrics);
                    
                    // 检查电网友好度指标的值和类型
                    const gridFriendliness = data.state.metrics.grid_friendliness;
                    console.log("Grid friendliness value:", gridFriendliness, "type:", typeof gridFriendliness);
                    
                    // 确保电网友好度指标是数字且存在
                    if (gridFriendliness !== undefined && gridFriendliness !== null) {
                        // 尝试转换为数字类型
                        const gridValue = parseFloat(gridFriendliness);
                        
                        if (!isNaN(gridValue)) {
                            // 将grid_friendliness从[-1,1]映射到更合适的显示范围
                            metricsData.load_balance_index = ((1 + gridValue) * 0.5).toFixed(2); // 映射到[0,1]
                            metricsData.peak_load_ratio = Math.round(50 + gridValue * 25); // 映射到[25,75]
                            
                            console.log("Grid friendliness processed:", {
                                original: gridValue,
                                loadBalanceIndex: metricsData.load_balance_index,
                                peakLoadRatio: metricsData.peak_load_ratio
                            });
                        } else {
                            console.error("Grid friendliness value is not a valid number:", gridFriendliness);
                        }
                    } else {
                        console.warn("Grid friendliness value is missing or undefined");
                    }
                    
                    // 使用实际的可再生能源比例
                    if (typeof data.state.metrics.renewable_ratio === 'number') {
                        metricsData.renewable_ratio = data.state.metrics.renewable_ratio;
                    }
                    
                    // 使用实际的负载数据
                    if (typeof data.state.metrics.grid_load === 'number') {
                        metricsData.current_load = data.state.metrics.grid_load;
                    } else if (typeof data.state.grid_load === 'number') {
                        metricsData.current_load = data.state.grid_load;
                    }
                }
                
                // 确保所有指标都是数字类型
                Object.keys(metricsData).forEach(key => {
                    if (typeof metricsData[key] === 'string') {
                        metricsData[key] = parseFloat(metricsData[key]) || 0;
                    }
                });
                
                console.log("Updating grid metrics with:", metricsData);
                updateGridMetrics(metricsData);
                
                // Update EV load chart with real data if available
                if (data.state.grid_load !== undefined) {
                    updateRealTimeLoadChart(data.state.grid_load);
                } else {
                    // Generate EV load data (simple simulation based on time of day)
                    const currentHour = new Date().getHours();
                    const evLoad = Array(24).fill(0).map((_, hour) => {
                        let baseLoad;
                        if (hour >= 7 && hour <= 10) {
                            // Morning peak
                            baseLoad = 15 + Math.random() * 5;
                        } else if (hour >= 18 && hour <= 21) {
                            // Evening peak
                            baseLoad = 16 + Math.random() * 6;
                        } else if (hour >= 23 || hour <= 5) {
                            // Night valley
                            baseLoad = 3 + Math.random() * 3;
                        } else {
                            // Normal hours
                            baseLoad = 10 + Math.random() * 5;
                        }
                        
                        // Highlight current hour with a bit more randomness
                        return hour === currentHour ? baseLoad + Math.random() * 3 : baseLoad;
                    });
                    
                    updateEvLoad(evLoad);
                }
            }
        })
        .catch(error => {
            console.error('Error updating simulation status:', error);
        });
}

// Update system time
function updateSystemTime() {
    const now = new Date();
    const formattedTime = formatDateTime(now);
    document.getElementById('current-system-time').textContent = formattedTime;
    
    // Update every second
    setTimeout(updateSystemTime, 1000);
}

// Format date and time
function formatDateTime(date) {
    const year = date.getFullYear();
    const month = (date.getMonth() + 1).toString().padStart(2, '0');
    const day = date.getDate().toString().padStart(2, '0');
    const hours = date.getHours().toString().padStart(2, '0');
    const minutes = date.getMinutes().toString().padStart(2, '0');
    
    return `${year}-${month}-${day} ${hours}:${minutes}`;
}

// Show notification
function showNotification(message, type = 'info') {
    // Create notification element
    const notification = document.createElement('div');
    notification.className = `toast align-items-center text-white bg-${type} border-0`;
    notification.role = 'alert';
    notification.setAttribute('aria-live', 'assertive');
    notification.setAttribute('aria-atomic', 'true');
    
    notification.innerHTML = `
        <div class="d-flex">
            <div class="toast-body">
                ${message}
            </div>
            <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
        </div>
    `;
    
    // Add to document
    if (!document.querySelector('.toast-container')) {
        const toastContainer = document.createElement('div');
        toastContainer.className = 'toast-container position-fixed top-0 end-0 p-3';
        document.body.appendChild(toastContainer);
    }
    
    document.querySelector('.toast-container').appendChild(notification);
    
    // Show notification
    const toast = new bootstrap.Toast(notification, {
        delay: 3000
    });
    toast.show();
    
    // Remove after hiding
    notification.addEventListener('hidden.bs.toast', function() {
        this.remove();
    });
}

// 更新实时负荷图表
function updateRealTimeLoadChart(gridLoad) {
    if (!realTimeLoadChart) return;
    
    // 获取当前小时
    const currentHour = new Date().getHours();
    
    // 基本负荷数据 (假设这是从电网获取的基础负荷)
    const baseLoad = simulation.gridData.hourlyLoad || Array(24).fill(50);
    
    // 更新当前小时的负荷
    if (typeof gridLoad === 'number') {
        baseLoad[currentHour] = gridLoad;
    }
    
    // 更新图表数据
    realTimeLoadChart.data.datasets[0].data = baseLoad;
    
    // 计算EV负荷
    const evLoad = simulation.gridData.evLoad || Array(24).fill(10);
    
    // 计算总负荷
    const totalLoad = baseLoad.map((val, idx) => {
        return val + evLoad[idx];
    });
    
    // 更新总负荷数据
    realTimeLoadChart.data.datasets[2].data = totalLoad;
    
    // 更新图表
    realTimeLoadChart.update();
}

// 加载模拟结果时处理电网视图的更新
window.loadSimulationResult = function(filename) {
    fetch(`/api/simulation/result/${filename}`)
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                // 通知用户已加载结果
                showNotification(`已加载模拟结果: ${filename}`, 'success');
                
                // 更新电网负荷信息
                if (data.result.grid_load !== undefined) {
                    updateRealTimeLoadChart(data.result.grid_load);
                }
                
                // 更新电网指标
                if (data.result.metrics) {
                    const gridFriendliness = data.result.metrics.grid_friendliness || 0;
                    const metricsData = {
                        current_load: data.result.grid_load || 65,
                        renewable_ratio: Math.round(35 + gridFriendliness * 15),
                        peak_load_ratio: Math.round(65 + gridFriendliness * 10),
                        load_balance_index: (0.8 + gridFriendliness * 0.2).toFixed(2)
                    };
                    updateGridMetrics(metricsData);
                }
                
                // 更新模拟状态
                simulation.running = false;
                if (startBtn) startBtn.disabled = false;
                if (pauseBtn) pauseBtn.disabled = true;
                
                // 更新时间显示
                if (data.result.timestamp) {
                    const date = new Date(data.result.timestamp);
                    if (document.getElementById('simulation-time')) {
                        document.getElementById('simulation-time').textContent = formatDateTime(date);
                    }
                }
            } else {
                showNotification(`加载模拟结果时出错: ${data.message || '未知错误'}`, 'danger');
            }
        })
        .catch(error => {
            console.error('Error loading simulation result:', error);
            showNotification(`加载模拟结果时出错: ${error.message}`, 'danger');
        });
};