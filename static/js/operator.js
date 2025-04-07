// Global variables
let simulation = {
    running: false,
    chargerData: [],
    revenueData: {
        daily: [],
        weekly: [],
        monthly: []
    },
    utilizationData: []
};

// DOM Elements
const startBtn = document.getElementById('btn-start-simulation');
const pauseBtn = document.getElementById('btn-pause-simulation');
const resetBtn = document.getElementById('btn-reset-simulation');
const transactionCount = document.getElementById('transaction-count');
const todayRevenue = document.getElementById('today-revenue');
const avgChargeTime = document.getElementById('avg-charge-time');
const utilizationRate = document.getElementById('utilization-rate');
const chargerTableBody = document.getElementById('charger-table-body');

// Charts
let hourlyDemandChart;
let locationUsageChart;
let userTypeChart;
let userProfileChart;
let revenueCompositionChart;
let demandForecastChart;

// Initialize the dashboard
document.addEventListener('DOMContentLoaded', function() {
    // Setup event listeners
    setupEventListeners();
    
    // Initialize charts
    initializeCharts();
    
    // Update system time
    updateSystemTime();
    
    // Start status update interval
    setInterval(updateSimulationStatus, 1000);
    
    // Initialize tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
});

// Setup event listeners
function setupEventListeners() {
    // Simulation controls
    startBtn.addEventListener('click', startSimulation);
    pauseBtn.addEventListener('click', pauseSimulation);
    resetBtn.addEventListener('click', resetSimulation);
    
    // Price management
    document.getElementById('apply-price-btn').addEventListener('click', applyPriceSettings);
    
    // Charger status filter
    document.getElementById('charger-status-filter').addEventListener('change', filterChargers);
    
    // Charger search
    document.getElementById('charger-search').addEventListener('input', searchChargers);
    
    // Tab events
    const operationTabs = document.getElementById('operation-tabs');
    if (operationTabs) {
        operationTabs.addEventListener('shown.bs.tab', function(event) {
            // Resize charts when tab is shown
            if (event.target.id === 'time-tab') {
                hourlyDemandChart.resize();
            } else if (event.target.id === 'location-tab') {
                locationUsageChart.resize();
            } else if (event.target.id === 'user-tab') {
                userTypeChart.resize();
                userProfileChart.resize();
            } else if (event.target.id === 'revenue-tab') {
                revenueCompositionChart.resize();
            }
        });
    }
}

// Initialize charts
function initializeCharts() {
    // 1. Hourly Demand Chart
    const hourlyDemandCtx = document.getElementById('hourly-demand-chart').getContext('2d');
    hourlyDemandChart = new Chart(hourlyDemandCtx, {
        type: 'line',
        data: {
            labels: Array.from({length: 24}, (_, i) => `${i}:00`),
            datasets: [
                {
                    label: '日均充电交易量',
                    data: [8, 5, 3, 2, 1, 2, 6, 12, 18, 20, 15, 14, 19, 21, 18, 14, 10, 13, 22, 19, 15, 12, 10, 9],
                    borderColor: '#0d6efd',
                    backgroundColor: 'rgba(13, 110, 253, 0.1)',
                    tension: 0.3,
                    fill: true
                }
            ]
        },
        options: {
            responsive: true,
            plugins: {
                legend: {
                    position: 'top',
                },
                annotation: {
                    annotations: {
                        peakZone1: {
                            type: 'box',
                            xMin: 7,
                            xMax: 11,
                            yMin: 0,
                            yMax: 'max',
                            backgroundColor: 'rgba(255, 99, 132, 0.1)',
                            borderColor: 'rgba(255, 99, 132, 0)'
                        },
                        peakZone2: {
                            type: 'box',
                            xMin: 17,
                            xMax: 21,
                            yMin: 0,
                            yMax: 'max',
                            backgroundColor: 'rgba(255, 99, 132, 0.1)',
                            borderColor: 'rgba(255, 99, 132, 0)'
                        },
                        valleyZone: {
                            type: 'box',
                            xMin: 0,
                            xMax: 6,
                            yMin: 0,
                            yMax: 'max',
                            backgroundColor: 'rgba(54, 162, 235, 0.1)',
                            borderColor: 'rgba(54, 162, 235, 0)'
                        }
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    title: {
                        display: true,
                        text: '交易量'
                    }
                }
            }
        }
    });
    
    // 2. Location Usage Chart
    const locationUsageCtx = document.getElementById('location-usage-chart').getContext('2d');
    locationUsageChart = new Chart(locationUsageCtx, {
        type: 'bar',
        data: {
            labels: ['城东充电站', '南湖科技园', '西区工业园', '北城商务区', '中央车站'],
            datasets: [
                {
                    label: '利用率',
                    data: [85, 72, 65, 78, 52],
                    backgroundColor: [
                        'rgba(13, 110, 253, 0.7)',
                        'rgba(25, 135, 84, 0.7)',
                        'rgba(255, 193, 7, 0.7)',
                        'rgba(13, 202, 240, 0.7)',
                        'rgba(111, 66, 193, 0.7)'
                    ],
                    borderColor: [
                        'rgb(13, 110, 253)',
                        'rgb(25, 135, 84)',
                        'rgb(255, 193, 7)',
                        'rgb(13, 202, 240)',
                        'rgb(111, 66, 193)'
                    ],
                    borderWidth: 1
                }
            ]
        },
        options: {
            responsive: true,
            plugins: {
                legend: {
                    display: false
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    max: 100,
                    title: {
                        display: true,
                        text: '利用率 (%)'
                    }
                }
            }
        }
    });
    
    // 3. User Type Chart
    const userTypeCtx = document.getElementById('user-type-chart').getContext('2d');
    userTypeChart = new Chart(userTypeCtx, {
        type: 'pie',
        data: {
            labels: ['私家车', '出租车', '网约车', '物流车'],
            datasets: [
                {
                    data: [45, 25, 20, 10],
                    backgroundColor: [
                        'rgba(13, 110, 253, 0.7)',
                        'rgba(25, 135, 84, 0.7)',
                        'rgba(255, 193, 7, 0.7)',
                        'rgba(220, 53, 69, 0.7)'
                    ],
                    borderColor: [
                        'rgb(13, 110, 253)',
                        'rgb(25, 135, 84)',
                        'rgb(255, 193, 7)',
                        'rgb(220, 53, 69)'
                    ],
                    borderWidth: 1
                }
            ]
        },
        options: {
            responsive: true,
            plugins: {
                legend: {
                    position: 'bottom'
                },
                title: {
                    display: true,
                    text: '用户类型分布'
                }
            }
        }
    });
    
    // 4. User Profile Chart
    const userProfileCtx = document.getElementById('user-profile-chart').getContext('2d');
    userProfileChart = new Chart(userProfileCtx, {
        type: 'pie',
        data: {
            labels: ['紧急补电型', '经济优先型', '平衡考量型', '计划充电型'],
            datasets: [
                {
                    data: [30, 25, 30, 15],
                    backgroundColor: [
                        'rgba(220, 53, 69, 0.7)',
                        'rgba(13, 202, 240, 0.7)',
                        'rgba(111, 66, 193, 0.7)',
                        'rgba(25, 135, 84, 0.7)'
                    ],
                    borderColor: [
                        'rgb(220, 53, 69)',
                        'rgb(13, 202, 240)',
                        'rgb(111, 66, 193)',
                        'rgb(25, 135, 84)'
                    ],
                    borderWidth: 1
                }
            ]
        },
        options: {
            responsive: true,
            plugins: {
                legend: {
                    position: 'bottom'
                },
                title: {
                    display: true,
                    text: '用户画像分布'
                }
            }
        }
    });
    
    // 5. Revenue Composition Chart
    const revenueCompositionCtx = document.getElementById('revenue-composition-chart').getContext('2d');
    revenueCompositionChart = new Chart(revenueCompositionCtx, {
        type: 'doughnut',
        data: {
            labels: ['电费收入', '服务费收入', '会员费收入', '广告收入', '增值服务'],
            datasets: [
                {
                    data: [65, 15, 10, 5, 5],
                    backgroundColor: [
                        'rgba(13, 110, 253, 0.7)',
                        'rgba(25, 135, 84, 0.7)',
                        'rgba(255, 193, 7, 0.7)',
                        'rgba(13, 202, 240, 0.7)',
                        'rgba(111, 66, 193, 0.7)'
                    ],
                    borderColor: [
                        'rgb(13, 110, 253)',
                        'rgb(25, 135, 84)',
                        'rgb(255, 193, 7)',
                        'rgb(13, 202, 240)',
                        'rgb(111, 66, 193)'
                    ],
                    borderWidth: 1
                }
            ]
        },
        options: {
            responsive: true,
            plugins: {
                legend: {
                    position: 'bottom'
                },
                title: {
                    display: true,
                    text: '收入构成分析'
                }
            }
        }
    });
    
    // 6. Demand Forecast Chart
    const demandForecastCtx = document.getElementById('demand-forecast-chart').getContext('2d');
    demandForecastChart = new Chart(demandForecastCtx, {
        type: 'line',
        data: {
            labels: ['周一', '周二', '周三', '周四', '周五', '周六', '周日'],
            datasets: [
                {
                    label: '需求预测',
                    data: [320, 345, 330, 360, 390, 420, 380],
                    borderColor: '#0d6efd',
                    backgroundColor: 'rgba(13, 110, 253, 0.1)',
                    tension: 0.3,
                    fill: true
                },
                {
                    label: '历史数据',
                    data: [310, 330, 320, 340, 380, 410, 370],
                    borderColor: '#6c757d',
                    backgroundColor: 'rgba(108, 117, 125, 0.1)',
                    borderDash: [5, 5],
                    tension: 0.3,
                    fill: false
                }
            ]
        },
        options: {
            responsive: true,
            plugins: {
                legend: {
                    position: 'top'
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return `${context.dataset.label}: ${context.raw} 次/日`;
                        }
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: false,
                    title: {
                        display: true,
                        text: '充电次数/日'
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
    
    // Get price settings
    const basePrice = parseFloat(document.getElementById('base-price').value);
    const peakMarkup = parseFloat(document.getElementById('peak-markup').value);
    const valleyDiscount = parseFloat(document.getElementById('valley-discount').value);
    const serviceFee = parseFloat(document.getElementById('service-fee').value);
    const fastChargeRate = parseFloat(document.getElementById('fast-charge-rate').value);
    
    // Send request to start simulation
    fetch('/api/simulation/start', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            days: 7,
            strategy: 'profit', // Operator perspective uses profit-oriented strategy
            use_multi_agent: true,
            price_settings: {
                base_price: basePrice,
                peak_markup: peakMarkup,
                valley_discount: valleyDiscount,
                service_fee: serviceFee,
                fast_charge_rate: fastChargeRate
            }
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
            
            // Fetch initial charger data
            fetchChargerData();
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
    simulation.chargerData = [];
    simulation.revenueData = {
        daily: [],
        weekly: [],
        monthly: []
    };
    simulation.utilizationData = [];
    
    // Reset charts
    resetCharts();
    
    // Reset stats
    transactionCount.textContent = '0';
    todayRevenue.textContent = '¥0';
    avgChargeTime.textContent = '0分钟';
    utilizationRate.textContent = '0%';
    
    showNotification('模拟已重置', 'info');
}

// Reset charts to initial state
function resetCharts() {
    // Reset hourly demand chart
    hourlyDemandChart.data.datasets[0].data = [8, 5, 3, 2, 1, 2, 6, 12, 18, 20, 15, 14, 19, 21, 18, 14, 10, 13, 22, 19, 15, 12, 10, 9];
    hourlyDemandChart.update();
    
    // Reset location usage chart
    locationUsageChart.data.datasets[0].data = [85, 72, 65, 78, 52];
    locationUsageChart.update();
    
    // Reset user charts
    userTypeChart.data.datasets[0].data = [45, 25, 20, 10];
    userTypeChart.update();
    
    userProfileChart.data.datasets[0].data = [30, 25, 30, 15];
    userProfileChart.update();
    
    // Reset revenue chart
    revenueCompositionChart.data.datasets[0].data = [65, 15, 10, 5, 5];
    revenueCompositionChart.update();
    
    // Reset forecast chart
    demandForecastChart.data.datasets[0].data = [320, 345, 330, 360, 390, 420, 380];
    demandForecastChart.data.datasets[1].data = [310, 330, 320, 340, 380, 410, 370];
    demandForecastChart.update();
}

// Apply price settings
function applyPriceSettings() {
    // Get values
    const basePrice = parseFloat(document.getElementById('base-price').value);
    const peakMarkup = parseFloat(document.getElementById('peak-markup').value);
    const valleyDiscount = parseFloat(document.getElementById('valley-discount').value);
    const serviceFee = parseFloat(document.getElementById('service-fee').value);
    const fastChargeRate = parseFloat(document.getElementById('fast-charge-rate').value);
    
    // Validate values
    if (isNaN(basePrice) || isNaN(peakMarkup) || isNaN(valleyDiscount) || isNaN(serviceFee) || isNaN(fastChargeRate)) {
        showNotification('请输入有效的价格设置', 'danger');
        return;
    }
    
    // Calculate estimated impact
    const revenueChange = (peakMarkup / 10) + (serviceFee * 5) - (valleyDiscount / 15);
    const userChange = (peakMarkup / 20) + (serviceFee * 3) - (valleyDiscount / 8);
    const demandChange = ((valleyDiscount / 5) - (peakMarkup / 25) - (serviceFee * 2));
    
    // Update simulation results
    showNotification('价格策略已更新', 'success');
    
    // If simulation is running, send updated price settings to backend
    if (simulation.running) {
        fetch('/api/config', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                grid: {
                    normal_price: basePrice,
                    peak_price: basePrice * (1 + peakMarkup/100),
                    valley_price: basePrice * (1 - valleyDiscount/100)
                }
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                console.log('Price settings updated');
            }
        })
        .catch(error => {
            console.error('Error updating price settings:', error);
        });
    }
}

// Filter chargers by status
function filterChargers() {
    const status = document.getElementById('charger-status-filter').value;
    const rows = chargerTableBody.querySelectorAll('tr');
    
    rows.forEach(row => {
        if (status === 'all') {
            row.style.display = '';
        } else {
            const statusCell = row.querySelector('td:nth-child(4)');
            const statusText = statusCell.textContent.toLowerCase();
            row.style.display = statusText.includes(status) ? '' : 'none';
        }
    });
}

// Search chargers
function searchChargers() {
    const query = document.getElementById('charger-search').value.toLowerCase();
    const rows = chargerTableBody.querySelectorAll('tr');
    
    rows.forEach(row => {
        const text = row.textContent.toLowerCase();
        row.style.display = text.includes(query) ? '' : 'none';
    });
}

// Fetch charger data
function fetchChargerData() {
    fetch('/api/chargers')
        .then(response => response.json())
        .then(data => {
            simulation.chargerData = data;
            updateChargerTable(data);
        })
        .catch(error => {
            console.error('Error fetching charger data:', error);
        });
}

// Update charger table
function updateChargerTable(chargers) {
    // Clear table
    chargerTableBody.innerHTML = '';
    
    // Add rows
    chargers.forEach(charger => {
        const row = document.createElement('tr');
        
        // Determine status
        let statusBadge;
        if (charger.queue_length >= 3) {
            statusBadge = '<span class="badge bg-warning">队列已满</span>';
        } else if (charger.health_score < 70) {
            statusBadge = '<span class="badge bg-danger">故障</span>';
        } else {
            statusBadge = charger.queue_length > 0 ? 
                '<span class="badge bg-primary">使用中</span>' : 
                '<span class="badge bg-success">空闲</span>';
        }
        
        // Calculate daily revenue (simulated)
        const dailyRevenue = Math.round(
            (charger.queue_length * 2 + 3) * 
            (charger.health_score / 100) * 
            (charger.max_power / 60) * 
            100
        );
        
        row.innerHTML = `
            <td>${charger.charger_id}</td>
            <td>${charger.location || '未知位置'}</td>
            <td><span class="badge ${charger.type === 'fast' ? 'bg-primary' : 'bg-secondary'}">${charger.type === 'fast' ? '快充' : '慢充'}</span></td>
            <td>${statusBadge}</td>
            <td>
                <div class="progress" style="height: 6px;">
                    <div class="progress-bar ${charger.health_score >= 80 ? 'bg-success' : (charger.health_score >= 70 ? 'bg-warning' : 'bg-danger')}" style="width: ${charger.health_score}%;"></div>
                </div>
                <span class="small">${charger.health_score}%</span>
            </td>
            <td>${charger.queue_length}/3</td>
            <td>¥${dailyRevenue}</td>
            <td>
                <button class="btn btn-sm btn-outline-primary me-1" data-bs-toggle="tooltip" title="详情">
                    <i class="fas fa-info-circle"></i>
                </button>
                <button class="btn btn-sm btn-outline-secondary" data-bs-toggle="tooltip" title="维护">
                    <i class="fas fa-wrench"></i>
                </button>
            </td>
        `;
        
        chargerTableBody.appendChild(row);
    });
    
    // Reinitialize tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
}

// Update simulation metrics
function updateSimulationMetrics(data) {
    // Update transaction count with animation
    animateCounter(transactionCount, parseInt(transactionCount.textContent.replace(/,/g, '')), data.transaction_count || 347);
    
    // Update revenue with animation
    const currentRevenue = parseFloat(todayRevenue.textContent.replace(/[^0-9.-]+/g, ''));
    animateCounter(todayRevenue, currentRevenue, data.revenue || 12845, '¥');
    
    // Update average charge time
    const currentTime = parseInt(avgChargeTime.textContent);
    animateCounter(avgChargeTime, currentTime, data.avg_charge_time || 42, '', '分钟');
    
    // Update utilization rate
    const currentRate = parseFloat(utilizationRate.textContent);
    animateCounter(utilizationRate, currentRate, data.utilization_rate || 68.4, '', '%');
}

// Animate counter
function animateCounter(element, start, end, prefix = '', suffix = '') {
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
            formattedValue = current.toFixed(1);
        }
        
        element.textContent = `${prefix}${formattedValue}${suffix}`;
    }, stepTime);
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
                // Update chargers if available
                if (data.state.chargers && data.state.chargers.length > 0) {
                    updateChargerTable(data.state.chargers);
                    
                    // 更新充电桩统计信息
                    updateChargerStatistics(data.state.chargers);
                }
                
                // Update metrics with some simulated data based on real metrics
                const metricsData = {
                    transaction_count: Math.round(Math.random() * 100 + 300),
                    revenue: Math.round(Math.random() * 2000 + 11000),
                    avg_charge_time: Math.round(Math.random() * 10 + 35),
                    utilization_rate: (Math.random() * 10 + 60).toFixed(1)
                };
                
                // 使用真实指标数据如果可用
                if (data.state.metrics) {
                    metricsData.utilization_rate = (data.state.metrics.operator_profit * 100).toFixed(1);
                }
                
                updateSimulationMetrics(metricsData);
            }
        })
        .catch(error => {
            console.error('Error updating simulation status:', error);
        });
}

// 更新充电桩统计信息
function updateChargerStatistics(chargers) {
    if (!chargers || chargers.length === 0) return;
    
    // 统计不同状态的充电桩数量
    const availableCount = chargers.filter(c => c.status === 'available').length;
    const occupiedCount = chargers.filter(c => c.status === 'occupied').length;
    const failureCount = chargers.filter(c => c.status === 'failure').length;
    
    // 统计分类
    const fastCount = chargers.filter(c => c.type === 'fast').length;
    const slowCount = chargers.filter(c => c.type === 'slow').length;
    
    // 统计收入情况
    const totalRevenue = chargers.reduce((sum, c) => sum + (c.daily_revenue || 0), 0);
    const avgRevenue = totalRevenue / chargers.length;
    
    // 更新显示
    const statsElement = document.getElementById('charger-statistics');
    if (statsElement) {
        statsElement.innerHTML = `
            <div class="card mt-3">
                <div class="card-header">充电桩统计</div>
                <div class="card-body">
                    <div class="row">
                        <div class="col-md-6">
                            <p><strong>总数:</strong> ${chargers.length}</p>
                            <p><strong>可用:</strong> ${availableCount} (${Math.round(availableCount/chargers.length*100)}%)</p>
                            <p><strong>占用:</strong> ${occupiedCount} (${Math.round(occupiedCount/chargers.length*100)}%)</p>
                            <p><strong>故障:</strong> ${failureCount} (${Math.round(failureCount/chargers.length*100)}%)</p>
                        </div>
                        <div class="col-md-6">
                            <p><strong>快充:</strong> ${fastCount} (${Math.round(fastCount/chargers.length*100)}%)</p>
                            <p><strong>慢充:</strong> ${slowCount} (${Math.round(slowCount/chargers.length*100)}%)</p>
                            <p><strong>总收入:</strong> ¥${totalRevenue.toFixed(2)}</p>
                            <p><strong>平均收入:</strong> ¥${avgRevenue.toFixed(2)}</p>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }
}

// 加载模拟结果时处理运营商视图的更新
window.loadSimulationResult = function(filename) {
    fetch(`/api/simulation/result/${filename}`)
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                // 通知用户已加载结果
                showNotification(`已加载模拟结果: ${filename}`, 'success');
                
                // 更新充电桩信息
                if (data.result.chargers && data.result.chargers.length > 0) {
                    updateChargerTable(data.result.chargers);
                    updateChargerStatistics(data.result.chargers);
                }
                
                // 更新运营商指标
                if (data.result.metrics) {
                    const metricsData = {
                        transaction_count: Math.round(data.result.users ? data.result.users.length * 0.8 : 350),
                        revenue: Math.round(data.result.metrics.operator_profit * 10000 + 10000),
                        avg_charge_time: 42,
                        utilization_rate: (data.result.metrics.operator_profit * 100).toFixed(1)
                    };
                    updateSimulationMetrics(metricsData);
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