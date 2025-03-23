/**
 * charts.js - 电动汽车有序充电调度系统图表功能
 * 
 * 本文件包含所有图表的初始化和更新函数，使用Chart.js库实现数据可视化
 */

// 各种图表的全局引用
let realTimeLoadChart = null;
let strategyComparisonChart = null;
let hourlyLoadChart = null;
let userTypeChart = null;
let hourlyDemandChart = null;
let avgSocChart = null;
let chargingFrequencyChart = null;
let peakLoadChart = null;
let loadVarianceChart = null;
let renewableChart = null;

// 图表颜色配置
const CHART_COLORS = {
    blue: {
        border: 'rgba(54, 162, 235, 1)',
        background: 'rgba(54, 162, 235, 0.2)'
    },
    red: {
        border: 'rgba(255, 99, 132, 1)',
        background: 'rgba(255, 99, 132, 0.2)'
    },
    green: {
        border: 'rgba(75, 192, 192, 1)',
        background: 'rgba(75, 192, 192, 0.2)'
    },
    yellow: {
        border: 'rgba(255, 206, 86, 1)',
        background: 'rgba(255, 206, 86, 0.2)'
    },
    purple: {
        border: 'rgba(153, 102, 255, 1)',
        background: 'rgba(153, 102, 255, 0.2)'
    },
    orange: {
        border: 'rgba(255, 159, 64, 1)',
        background: 'rgba(255, 159, 64, 0.2)'
    }
};

/**
 * 初始化所有图表
 */
function initAllCharts() {
    if (typeof Chart === 'undefined') {
        console.error('Chart.js 未加载，无法初始化图表');
        return;
    }
    
    // 实时负载图表
    initRealTimeLoadChart();
    
    // 策略比较图表
    initStrategyComparisonChart();
    
    // 小时负载图表
    initHourlyLoadChart();
    
    // 用户类型图表
    initUserTypeChart();
    
    // 小时需求图表
    initHourlyDemandChart();
    
    // 平均充电SOC图表
    initAvgSocChart();
    
    // 充电频率图表
    initChargingFrequencyChart();
    
    // 峰值负载图表
    initPeakLoadChart();
    
    // 负载方差图表
    initLoadVarianceChart();
    
    // 可再生能源利用率图表
    initRenewableChart();
}

/**
 * 初始化实时负载图表
 */
function initRealTimeLoadChart() {
    const ctx = document.getElementById('realTimeLoad');
    if (!ctx) return;
    
    // 创建24小时标签
    const hourLabels = Array(24).fill().map((_, i) => `${i}:00`);
    
    realTimeLoadChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: hourLabels,
            datasets: [{
                label: '电网负载 (%)',
                data: Array(24).fill(null),
                borderColor: CHART_COLORS.blue.border,
                backgroundColor: CHART_COLORS.blue.background,
                borderWidth: 2,
                tension: 0.4,
                fill: true
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true,
                    max: 100,
                    title: {
                        display: true,
                        text: '负载 (%)'
                    }
                },
                x: {
                    title: {
                        display: true,
                        text: '时间'
                    }
                }
            },
            plugins: {
                legend: {
                    display: true,
                    position: 'top'
                },
                tooltip: {
                    mode: 'index',
                    intersect: false
                }
            }
        }
    });
}

/**
 * 更新实时负载图表
 * @param {Object} grid 电网状态数据
 */
function updateRealTimeLoadChart(grid) {
    if (!realTimeLoadChart) return;
    
    // 获取当前小时
    const currentHour = new Date().getHours();
    
    // 更新数据点
    realTimeLoadChart.data.datasets[0].data[currentHour] = grid.current_load;
    
    // 高亮峰谷时段
    const isPeakHour = grid.is_peak_hour;
    const isValleyHour = grid.is_valley_hour;
    
    if (isPeakHour) {
        realTimeLoadChart.data.datasets[0].borderColor = CHART_COLORS.red.border;
        realTimeLoadChart.data.datasets[0].backgroundColor = CHART_COLORS.red.background;
    } else if (isValleyHour) {
        realTimeLoadChart.data.datasets[0].borderColor = CHART_COLORS.green.border;
        realTimeLoadChart.data.datasets[0].backgroundColor = CHART_COLORS.green.background;
    } else {
        realTimeLoadChart.data.datasets[0].borderColor = CHART_COLORS.blue.border;
        realTimeLoadChart.data.datasets[0].backgroundColor = CHART_COLORS.blue.background;
    }
    
    realTimeLoadChart.update();
}

/**
 * 初始化策略比较雷达图
 */
function initStrategyComparisonChart() {
    const ctx = document.getElementById('strategyComparisonChart');
    if (!ctx) return;
    
    strategyComparisonChart = new Chart(ctx, {
        type: 'radar',
        data: {
            labels: ['用户满意度', '运营商利润', '电网友好度', '综合奖励'],
            datasets: [
                {
                    label: '用户优先策略',
                    data: [0.85, 0.65, 0.55, 0.72],
                    backgroundColor: CHART_COLORS.red.background,
                    borderColor: CHART_COLORS.red.border,
                    pointBackgroundColor: CHART_COLORS.red.border,
                    pointBorderColor: '#fff',
                    pointHoverBackgroundColor: '#fff',
                    pointHoverBorderColor: CHART_COLORS.red.border
                },
                {
                    label: '利润优先策略',
                    data: [0.65, 0.85, 0.60, 0.70],
                    backgroundColor: CHART_COLORS.blue.background,
                    borderColor: CHART_COLORS.blue.border,
                    pointBackgroundColor: CHART_COLORS.blue.border,
                    pointBorderColor: '#fff',
                    pointHoverBackgroundColor: '#fff',
                    pointHoverBorderColor: CHART_COLORS.blue.border
                },
                {
                    label: '电网友好策略',
                    data: [0.60, 0.65, 0.85, 0.70],
                    backgroundColor: CHART_COLORS.green.background,
                    borderColor: CHART_COLORS.green.border,
                    pointBackgroundColor: CHART_COLORS.green.border,
                    pointBorderColor: '#fff',
                    pointHoverBackgroundColor: '#fff',
                    pointHoverBorderColor: CHART_COLORS.green.border
                },
                {
                    label: '平衡策略',
                    data: [0.75, 0.75, 0.75, 0.78],
                    backgroundColor: CHART_COLORS.yellow.background,
                    borderColor: CHART_COLORS.yellow.border,
                    pointBackgroundColor: CHART_COLORS.yellow.border,
                    pointBorderColor: '#fff',
                    pointHoverBackgroundColor: '#fff',
                    pointHoverBorderColor: CHART_COLORS.yellow.border
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            elements: {
                line: {
                    borderWidth: 3
                }
            },
            scales: {
                r: {
                    angleLines: {
                        display: true
                    },
                    suggestedMin: 0,
                    suggestedMax: 1
                }
            }
        }
    });
}

/**
 * 更新策略比较图表
 * @param {Object} result 策略比较结果
 */
function updateStrategyComparisonChart(result) {
    if (!strategyComparisonChart) return;
    
    // 检查是否有必要的数据
    if (!result.strategy_names || !result.user_satisfaction || !result.operator_profit || !result.grid_friendliness || !result.total_reward) {
        return;
    }
    
    // 更新数据集
    strategyComparisonChart.data.datasets = [];
    
    // 颜色列表
    const colors = [
        CHART_COLORS.red,
        CHART_COLORS.blue,
        CHART_COLORS.green,
        CHART_COLORS.yellow,
        CHART_COLORS.purple
    ];
    
    // 为每个策略创建数据集
    result.strategy_names.forEach((strategy, i) => {
        const colorIndex = i % colors.length;
        const color = colors[colorIndex];
        
        strategyComparisonChart.data.datasets.push({
            label: strategy,
            data: [
                result.user_satisfaction[i],
                result.operator_profit[i],
                result.grid_friendliness[i],
                result.total_reward[i]
            ],
            backgroundColor: color.background,
            borderColor: color.border,
            pointBackgroundColor: color.border,
            pointBorderColor: '#fff',
            pointHoverBackgroundColor: '#fff',
            pointHoverBorderColor: color.border
        });
    });
    
    // 更新表格
    updateStrategyTable(result);
    
    strategyComparisonChart.update();
}

/**
 * 更新策略表格
 * @param {Object} result 策略比较结果
 */
function updateStrategyTable(result) {
    const tableBody = document.getElementById('strategyTableBody');
    if (!tableBody) return;
    
    // 清空表格
    tableBody.innerHTML = '';
    
    // 检查是否有必要的数据
    if (!result.strategy_names || !result.user_satisfaction || !result.operator_profit || !result.grid_friendliness || !result.total_reward) {
        return;
    }
    
    // 找出每个指标的最大值
    const maxSatisfaction = Math.max(...result.user_satisfaction);
    const maxProfit = Math.max(...result.operator_profit);
    const maxGrid = Math.max(...result.grid_friendliness);
    const maxReward = Math.max(...result.total_reward);
    
    // 添加策略数据
    result.strategy_names.forEach((strategy, i) => {
        const row = document.createElement('tr');
        
        // 设置单元格内容
        row.innerHTML = `
            <td>${strategy}</td>
            <td ${result.user_satisfaction[i] === maxSatisfaction ? 'class="text-success"' : ''}>${result.user_satisfaction[i].toFixed(2)}</td>
            <td ${result.operator_profit[i] === maxProfit ? 'class="text-success"' : ''}>${result.operator_profit[i].toFixed(2)}</td>
            <td ${result.grid_friendliness[i] === maxGrid ? 'class="text-success"' : ''}>${result.grid_friendliness[i].toFixed(2)}</td>
            <td ${result.total_reward[i] === maxReward ? 'class="text-success"' : ''}>${result.total_reward[i].toFixed(2)}</td>
        `;
        
        tableBody.appendChild(row);
    });
}

/**
 * 初始化小时负载图表
 */
function initHourlyLoadChart() {
    const ctx = document.getElementById('hourlyLoadChart');
    if (!ctx) return;
    
    // 创建24小时标签
    const hourLabels = Array(24).fill().map((_, i) => `${i}:00`);
    
    hourlyLoadChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: hourLabels,
            datasets: [
                {
                    label: '有序调度',
                    data: [40, 35, 30, 28, 27, 30, 45, 60, 75, 80, 82, 84, 80, 75, 70, 65, 70, 75, 85, 80, 70, 60, 50, 45],
                    borderColor: CHART_COLORS.blue.border,
                    backgroundColor: CHART_COLORS.blue.background,
                    borderWidth: 2,
                    tension: 0.4,
                    fill: true
                },
                {
                    label: '无序充电',
                    data: [40, 35, 30, 28, 27, 30, 55, 75, 90, 92, 94, 90, 85, 80, 75, 70, 80, 90, 95, 85, 75, 65, 55, 45],
                    borderColor: CHART_COLORS.red.border,
                    backgroundColor: CHART_COLORS.red.background,
                    borderWidth: 2,
                    tension: 0.4,
                    fill: true
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true,
                    max: 100,
                    title: {
                        display: true,
                        text: '负载 (%)'
                    }
                },
                x: {
                    title: {
                        display: true,
                        text: '时间'
                    }
                }
            },
            plugins: {
                legend: {
                    display: true,
                    position: 'top'
                },
                tooltip: {
                    mode: 'index',
                    intersect: false
                },
                annotation: {
                    annotations: {
                        peakZone1: {
                            type: 'box',
                            xMin: 7,
                            xMax: 11,
                            backgroundColor: 'rgba(255, 99, 132, 0.1)',
                            borderColor: 'rgba(255, 99, 132, 0.3)',
                            label: {
                                display: true,
                                content: '早高峰',
                                position: 'start'
                            }
                        },
                        peakZone2: {
                            type: 'box',
                            xMin: 18,
                            xMax: 22,
                            backgroundColor: 'rgba(255, 99, 132, 0.1)',
                            borderColor: 'rgba(255, 99, 132, 0.3)',
                            label: {
                                display: true,
                                content: '晚高峰',
                                position: 'start'
                            }
                        },
                        valleyZone: {
                            type: 'box',
                            xMin: 0,
                            xMax: 6,
                            backgroundColor: 'rgba(54, 162, 235, 0.1)',
                            borderColor: 'rgba(54, 162, 235, 0.3)',
                            label: {
                                display: true,
                                content: '低谷时段',
                                position: 'start'
                            }
                        }
                    }
                }
            }
        }
    });
}

/**
 * 更新小时负载图表
 * @param {Object} hourlyLoad 小时负载数据
 */
function updateHourlyLoadChart(hourlyLoad) {
    if (!hourlyLoadChart || !hourlyLoad) return;
    
    // 检查是否有必要的数据
    if (!hourlyLoad.with_scheduling || !hourlyLoad.without_scheduling) {
        return;
    }
    
    // 更新数据集
    hourlyLoadChart.data.datasets[0].data = hourlyLoad.with_scheduling;
    hourlyLoadChart.data.datasets[1].data = hourlyLoad.without_scheduling;
    
    // 更新电网影响表格
    updateGridImpactTable(hourlyLoad);
    
    hourlyLoadChart.update();
}

/**
 * 更新电网影响表格
 * @param {Object} analysis 电网影响分析结果
 */
function updateGridImpactTable(analysis) {
    const tableBody = document.getElementById('gridImpactTableBody');
    if (!tableBody) return;
    
    // 检查是否有必要的数据
    if (!analysis.peak_load || !analysis.load_variance || !analysis.renewable_utilization) {
        return;
    }
    
    // 清空表格
    tableBody.innerHTML = '';
    
    // 峰值负载行
    const peakRow = document.createElement('tr');
    const peakImprovement = analysis.peak_load.reduction_percentage;
    peakRow.innerHTML = `
        <td>峰值负载削减</td>
        <td>${analysis.peak_load.with_scheduling.toFixed(1)}%</td>
        <td>${analysis.peak_load.without_scheduling.toFixed(1)}%</td>
        <td class="text-success">${peakImprovement.toFixed(1)}%↓</td>
    `;
    tableBody.appendChild(peakRow);
    
    // 负载方差行
    const varianceRow = document.createElement('tr');
    const varianceImprovement = analysis.load_variance.improvement_percentage;
    varianceRow.innerHTML = `
        <td>负载方差</td>
        <td>${analysis.load_variance.with_scheduling.toFixed(1)}</td>
        <td>${analysis.load_variance.without_scheduling.toFixed(1)}</td>
        <td class="text-success">${varianceImprovement.toFixed(1)}%↓</td>
    `;
    tableBody.appendChild(varianceRow);
    
    // 可再生能源利用率行
    const renewableRow = document.createElement('tr');
    const renewableImprovement = analysis.renewable_utilization.improvement_percentage;
    renewableRow.innerHTML = `
        <td>可再生能源利用率</td>
        <td>${analysis.renewable_utilization.with_scheduling.toFixed(1)}%</td>
        <td>${analysis.renewable_utilization.without_scheduling.toFixed(1)}%</td>
        <td class="text-success">${renewableImprovement.toFixed(1)}%↑</td>
    `;
    tableBody.appendChild(renewableRow);
}

/**
 * 初始化用户类型图表
 */
function initUserTypeChart() {
    const ctx = document.getElementById('userTypeChart');
    if (!ctx) return;
    
    userTypeChart = new Chart(ctx, {
        type: 'pie',
        data: {
            labels: ['出租车', '私家车', '网约车', '物流车'],
            datasets: [{
                data: [25, 40, 20, 15],
                backgroundColor: [
                    CHART_COLORS.red.background,
                    CHART_COLORS.blue.background,
                    CHART_COLORS.yellow.background,
                    CHART_COLORS.green.background
                ],
                borderColor: [
                    CHART_COLORS.red.border,
                    CHART_COLORS.blue.border,
                    CHART_COLORS.yellow.border,
                    CHART_COLORS.green.border
                ],
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'right'
                },
                title: {
                    display: true,
                    text: '用户类型分布'
                }
            }
        }
    });
}

/**
 * 更新用户类型图表
 * @param {Object} userTypeDistribution 用户类型分布数据
 */
function updateUserTypeChart(userTypeDistribution) {
    if (!userTypeChart || !userTypeDistribution) return;
    
    // 提取标签和数据
    const labels = Object.keys(userTypeDistribution);
    const data = Object.values(userTypeDistribution);
    
    // 更新图表数据
    userTypeChart.data.labels = labels;
    userTypeChart.data.datasets[0].data = data;
    
    userTypeChart.update();
}

/**
 * 初始化充电需求图表
 */
function initHourlyDemandChart() {
    const ctx = document.getElementById('hourlyDemandChart');
    if (!ctx) return;
    
    // 创建24小时标签
    const hourLabels = Array(24).fill().map((_, i) => `${i}:00`);
    
    hourlyDemandChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: hourLabels,
            datasets: [{
                label: '充电需求',
                data: [5, 4, 3, 2, 2, 3, 8, 15, 20, 18, 15, 14, 16, 15, 13, 14, 16, 22, 25, 20, 15, 10, 8, 6],
                backgroundColor: CHART_COLORS.blue.background,
                borderColor: CHART_COLORS.blue.border,
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true,
                    title: {
                        display: true,
                        text: '需求数量'
                    }
                },
                x: {
                    title: {
                        display: true,
                        text: '时间'
                    }
                }
            },
            plugins: {
                legend: {
                    display: true,
                    position: 'top'
                },
                tooltip: {
                    mode: 'index',
                    intersect: false
                }
            }
        }
    });
}

/**
 * 更新充电需求图表
 * @param {Array} hourlyDemand 小时充电需求数据
 */
function updateHourlyDemandChart(hourlyDemand) {
    if (!hourlyDemandChart || !hourlyDemand) return;
    
    // 更新数据
    hourlyDemandChart.data.datasets[0].data = hourlyDemand;
    
    hourlyDemandChart.update();
}

/**
 * 初始化平均充电SOC图表
 */
function initAvgSocChart() {
    const ctx = document.getElementById('avgSocChart');
    if (!ctx) return;
    
    avgSocChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: ['出租车', '私家车', '网约车', '物流车'],
            datasets: [{
                label: '平均充电SOC (%)',
                data: [25, 45, 30, 20],
                backgroundColor: CHART_COLORS.green.background,
                borderColor: CHART_COLORS.green.border,
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true,
                    max: 100,
                    title: {
                        display: true,
                        text: 'SOC (%)'
                    }
                },
                x: {
                    title: {
                        display: true,
                        text: '用户类型'
                    }
                }
            },
            plugins: {
                legend: {
                    display: true,
                    position: 'top'
                },
                tooltip: {
                    mode: 'index',
                    intersect: false
                }
            }
        }
    });
}

/**
 * 更新平均充电SOC图表
 * @param {Object} avgSocData 平均充电SOC数据
 */
function updateAvgSocChart(avgSocData) {
    if (!avgSocChart || !avgSocData) return;
    
    // 提取标签和数据
    const labels = Object.keys(avgSocData);
    const data = Object.values(avgSocData);
    
    // 更新图表数据
    avgSocChart.data.labels = labels;
    avgSocChart.data.datasets[0].data = data;
    
    avgSocChart.update();
}

/**
 * 初始化充电频率图表
 */
function initChargingFrequencyChart() {
    const ctx = document.getElementById('chargingFrequencyChart');
    if (!ctx) return;
    
    chargingFrequencyChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: ['出租车', '私家车', '网约车', '物流车'],
            datasets: [{
                label: '平均充电频率 (次/周)',
                data: [14, 3, 10, 5],
                backgroundColor: CHART_COLORS.orange.background,
                borderColor: CHART_COLORS.orange.border,
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true,
                    title: {
                        display: true,
                        text: '频率 (次/周)'
                    }
                },
                x: {
                    title: {
                        display: true,
                        text: '用户类型'
                    }
                }
            },
            plugins: {
                legend: {
                    display: true,
                    position: 'top'
                },
                tooltip: {
                    mode: 'index',
                    intersect: false
                }
            }
        }
    });
}

/**
 * 更新充电频率图表
 * @param {Object} frequencyData 充电频率数据
 */
function updateChargingFrequencyChart(frequencyData) {
    if (!chargingFrequencyChart || !frequencyData) return;
    
    // 提取标签和数据
    const labels = Object.keys(frequencyData);
    const data = Object.values(frequencyData);
    
    // 更新图表数据
    chargingFrequencyChart.data.labels = labels;
    chargingFrequencyChart.data.datasets[0].data = data;
    
    chargingFrequencyChart.update();
}

/**
 * 初始化峰值负载图表
 */
function initPeakLoadChart() {
    const ctx = document.getElementById('peakLoadChart');
    if (!ctx) return;
    
    peakLoadChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: ['有序调度', '无序充电'],
            datasets: [{
                label: '峰值负载 (%)',
                data: [78.5, 94.2],
                backgroundColor: [
                    CHART_COLORS.green.background,
                    CHART_COLORS.red.background
                ],
                borderColor: [
                    CHART_COLORS.green.border,
                    CHART_COLORS.red.border
                ],
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true,
                    max: 100,
                    title: {
                        display: true,
                        text: '负载 (%)'
                    }
                }
            },
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    mode: 'index',
                    intersect: false
                }
            }
        }
    });
}

/**
 * 初始化负载方差图表
 */
function initLoadVarianceChart() {
    const ctx = document.getElementById('loadVarianceChart');
    if (!ctx) return;
    
    loadVarianceChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: ['有序调度', '无序充电'],
            datasets: [{
                label: '负载方差',
                data: [124.3, 256.8],
                backgroundColor: [
                    CHART_COLORS.green.background,
                    CHART_COLORS.red.background
                ],
                borderColor: [
                    CHART_COLORS.green.border,
                    CHART_COLORS.red.border
                ],
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true,
                    title: {
                        display: true,
                        text: '方差'
                    }
                }
            },
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    mode: 'index',
                    intersect: false
                }
            }
        }
    });
}

/**
 * 初始化可再生能源利用率图表
 */
function initRenewableChart() {
    const ctx = document.getElementById('renewableChart');
    if (!ctx) return;
    
    renewableChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: ['有序调度', '无序充电'],
            datasets: [{
                label: '可再生能源利用率 (%)',
                data: [48.5, 32.1],
                backgroundColor: [
                    CHART_COLORS.green.background,
                    CHART_COLORS.red.background
                ],
                borderColor: [
                    CHART_COLORS.green.border,
                    CHART_COLORS.red.border
                ],
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true,
                    max: 100,
                    title: {
                        display: true,
                        text: '利用率 (%)'
                    }
                }
            },
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    mode: 'index',
                    intersect: false
                }
            }
        }
    });
}

/**
 * 更新用户分析图表
 * @param {Object} analysis 用户行为分析结果
 */
function updateUserAnalysisCharts(analysis) {
    // 更新用户类型分布
    if (analysis.user_type_distribution) {
        updateUserTypeChart(analysis.user_type_distribution);
    }
    
    // 更新充电需求分布
    if (analysis.hourly_demand && hourlyDemandChart) {
        updateHourlyDemandChart(analysis.hourly_demand);
    }
    
    // 更新平均充电SOC
    if (analysis.avg_soc_at_charge && avgSocChart) {
        updateAvgSocChart(analysis.avg_soc_at_charge);
    }
    
    // 更新充电频率
    if (analysis.charging_frequency && chargingFrequencyChart) {
        updateChargingFrequencyChart(analysis.charging_frequency);
    }
}

/**
 * 更新电网分析图表
 * @param {Object} analysis 电网影响分析结果
 */
function updateGridAnalysisCharts(analysis) {
    // 更新小时负载
    if (analysis.hourly_load) {
        updateHourlyLoadChart(analysis.hourly_load);
    }
    
    // 更新峰值负载
    if (analysis.peak_load && peakLoadChart) {
        peakLoadChart.data.datasets[0].data = [
            analysis.peak_load.with_scheduling,
            analysis.peak_load.without_scheduling
        ];
        peakLoadChart.update();
    }
    
    // 更新负载均衡
    if (analysis.load_variance && loadVarianceChart) {
        loadVarianceChart.data.datasets[0].data = [
            analysis.load_variance.with_scheduling,
            analysis.load_variance.without_scheduling
        ];
        loadVarianceChart.update();
    }
    
    // 更新可再生能源利用
    if (analysis.renewable_utilization && renewableChart) {
        renewableChart.data.datasets[0].data = [
            analysis.renewable_utilization.with_scheduling,
            analysis.renewable_utilization.without_scheduling
        ];
        renewableChart.update();
    }
}

/**
 * 更新评估表格
 * @param {Object} result 评估结果
 */
function updateEvaluationTable(result) {
    const tableBody = document.getElementById('evaluationTableBody');
    if (!tableBody) return;
    
    // 清空表格
    tableBody.innerHTML = '';
    
    // 指标名列表
    const metrics = ['user_satisfaction', 'operator_profit', 'grid_friendliness', 'total_reward'];
    const metricNames = ['用户满意度', '运营商利润', '电网友好度', '综合奖励'];
    
    // 添加评估数据
    metrics.forEach((metric, i) => {
        if (result[metric]) {
            const values = result[metric];
            const row = document.createElement('tr');
            
            // 计算统计值
            const avg = values.reduce((sum, val) => sum + val, 0) / values.length;
            const max = Math.max(...values);
            const min = Math.min(...values);
            
            // 计算标准差
            const variance = values.reduce((sum, val) => sum + Math.pow(val - avg, 2), 0) / values.length;
            const std = Math.sqrt(variance);
            
            row.innerHTML = `
                <td>${metricNames[i]}</td>
                <td>${avg.toFixed(4)}</td>
                <td>${max.toFixed(4)}</td>
                <td>${min.toFixed(4)}</td>
                <td>${std.toFixed(4)}</td>
            `;
            
            tableBody.appendChild(row);
        }
    });
}

/**
 * 更新图表数据
 * @param {Object} metrics 指标数据
 */
function updateCharts(metrics) {
    // 更新各项指标图表
    if (metrics.user_satisfaction) {
        updateUserSatisfactionChart(metrics.user_satisfaction);
    }
    
    if (metrics.operator_profit) {
        updateOperatorProfitChart(metrics.operator_profit);
    }
    
    if (metrics.grid_friendliness) {
        updateGridFriendlinessChart(metrics.grid_friendliness);
    }
    
    if (metrics.total_reward) {
        updateTotalRewardChart(metrics.total_reward);
    }
    
    // 更新结果图表的URL
    updateResultImages();
}

/**
 * 更新结果图像URL（添加时间戳避免缓存）
 */
function updateResultImages() {
    const chargingResultImage = document.getElementById('chargingResultImage');
    if (chargingResultImage) {
        chargingResultImage.src = `api/results/charging_scheduler_results.png?t=${Date.now()}`;
    }
    
    const learningCurvesImage = document.getElementById('learningCurvesImage');
    if (learningCurvesImage) {
        learningCurvesImage.src = `api/results/learning_curves.png?t=${Date.now()}`;
    }
}

/**
 * 为数字创建带颜色的标签
 * @param {number} value 数值
 * @param {boolean} isHigherBetter 数值越高越好
 * @param {number} threshold 阈值
 * @returns {string} HTML字符串
 */
function createColoredLabel(value, isHigherBetter = true, threshold = 0.7) {
    let colorClass = '';
    
    if (isHigherBetter) {
        colorClass = value >= threshold ? 'text-success' : (value >= threshold * 0.8 ? 'text-warning' : 'text-danger');
    } else {
        colorClass = value <= threshold ? 'text-success' : (value <= threshold * 1.2 ? 'text-warning' : 'text-danger');
    }
    
    return `<span class="${colorClass}">${value.toFixed(4)}</span>`;
}

// 导出函数，使其可在其他文件中使用
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        initAllCharts,
        updateRealTimeLoadChart,
        updateStrategyComparisonChart,
        updateHourlyLoadChart,
        updateUserTypeChart,
        updateUserAnalysisCharts,
        updateGridAnalysisCharts,
        updateCharts,
        updateEvaluationTable
    };
}