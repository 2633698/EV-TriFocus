// UI控制器

// 系统状态轮询间隔 (毫秒)
const STATUS_POLL_INTERVAL = 1000;
// 数据更新间隔 (毫秒)
const DATA_UPDATE_INTERVAL = 5000;

// 状态轮询定时器
let statusPollTimer = null;
// 数据更新定时器
let dataUpdateTimer = null;

document.addEventListener('DOMContentLoaded', function() {
    // 初始化UI
    initUI();
    
    // 绑定事件处理
    bindEvents();
    
    // 加载初始数据
    loadInitialData();
});

// 初始化UI
function initUI() {
    // 初始化图表
    initAllCharts();  // 添加这一行，调用charts.js中的函数
    
    // 更新权重显示
    updateWeightValues();
    
    // 检查初始系统状态
    checkSystemStatus();
}

// 绑定事件处理程序
function bindEvents() {
    // 运行按钮点击事件
    document.getElementById('runButton').addEventListener('click', function() {
        runOperation();
    });
    
    // 刷新结果按钮
    document.getElementById('refreshResults').addEventListener('click', function() {
        refreshAllData();
    });
    
    // 导出结果按钮
    document.getElementById('exportResults').addEventListener('click', function() {
        exportResults();
    });
    
    // 权重滑块变化事件
    document.getElementById('userSatisfactionWeight').addEventListener('input', updateWeightValues);
    document.getElementById('operatorProfitWeight').addEventListener('input', updateWeightValues);
    document.getElementById('gridFriendlinessWeight').addEventListener('input', updateWeightValues);
    
    // 运行模式变化事件
    document.getElementById('runMode').addEventListener('change', function() {
        const mode = this.value;
        // 根据模式调整UI元素可见性
        adjustUIByMode(mode);
    });
    
    // 图像模态框事件
    document.querySelectorAll('.result-image').forEach(img => {
        img.addEventListener('click', function() {
            document.getElementById('modalImage').src = this.src;
            document.getElementById('imageModalLabel').textContent = this.alt;
        });
    });
    
    // 策略选择变化事件
    document.getElementById('strategy').addEventListener('change', function() {
        const strategy = this.value;
        // 根据所选策略更新权重显示
        updateStrategyWeights(strategy);
    });
}

// 加载初始数据
async function loadInitialData() {
    // 获取系统配置
    const config = await API.getConfig();
    if (config) {
        applyConfigToUI(config);
    }
    
    // 加载实时数据
    await refreshAllData();
}

// 应用配置到UI
function applyConfigToUI(config) {
    // 环境配置
    if (config.environment) {
        document.getElementById('gridId').value = config.environment.grid_id || 'DEFAULT001';
        document.getElementById('chargerCount').value = config.environment.charger_count || 20;
        document.getElementById('userCount').value = config.environment.user_count || 50;
        document.getElementById('timeStep').value = config.environment.time_step_minutes || 15;
    }
    
    // 模型配置
    if (config.model) {
        document.getElementById('hiddenDim').value = config.model.hidden_dim || 128;
        document.getElementById('taskHiddenDim').value = config.model.task_hidden_dim || 64;
        document.getElementById('modelPath').value = config.model.model_path || 'models/ev_charging_model.pth';
    }
    
    // 调度器配置
    if (config.scheduler) {
        document.getElementById('useTrainedModel').checked = config.scheduler.use_trained_model !== false;
        
        // 权重配置
        if (config.scheduler.optimization_weights) {
            document.getElementById('userSatisfactionWeight').value = config.scheduler.optimization_weights.user_satisfaction || 0.4;
            document.getElementById('operatorProfitWeight').value = config.scheduler.optimization_weights.operator_profit || 0.3;
            document.getElementById('gridFriendlinessWeight').value = config.scheduler.optimization_weights.grid_friendliness || 0.3;
            updateWeightValues();
        }
    }
    
    // 策略配置
    if (config.strategies) {
        const strategySelect = document.getElementById('strategy');
        if (strategySelect.value && config.strategies[strategySelect.value]) {
            updateStrategyWeights(strategySelect.value, config.strategies);
        }
    }
}

// 根据选择的策略更新权重显示
function updateStrategyWeights(strategy, strategies) {
    if (!strategies) {
        // 如果没有提供策略配置，尝试从预定义配置获取
        strategies = {
            'user': { user_satisfaction: 0.6, operator_profit: 0.2, grid_friendliness: 0.2 },
            'profit': { user_satisfaction: 0.2, operator_profit: 0.6, grid_friendliness: 0.2 },
            'grid': { user_satisfaction: 0.2, operator_profit: 0.2, grid_friendliness: 0.6 },
            'balanced': { user_satisfaction: 0.33, operator_profit: 0.33, grid_friendliness: 0.34 }
        };
    }
    
    // 检查策略是否存在
    if (strategies[strategy]) {
        const weights = strategies[strategy];
        document.getElementById('userSatisfactionWeight').value = weights.user_satisfaction;
        document.getElementById('operatorProfitWeight').value = weights.operator_profit;
        document.getElementById('gridFriendlinessWeight').value = weights.grid_friendliness;
        updateWeightValues();
    }
}

// 更新权重值显示
function updateWeightValues() {
    const userWeight = parseFloat(document.getElementById('userSatisfactionWeight').value);
    const profitWeight = parseFloat(document.getElementById('operatorProfitWeight').value);
    const gridWeight = parseFloat(document.getElementById('gridFriendlinessWeight').value);
    
    document.getElementById('userWeightValue').textContent = userWeight.toFixed(2);
    document.getElementById('profitWeightValue').textContent = profitWeight.toFixed(2);
    document.getElementById('gridWeightValue').textContent = gridWeight.toFixed(2);
    
    const sum = userWeight + profitWeight + gridWeight;
    document.getElementById('weightSum').textContent = sum.toFixed(2);
    
    // 如果权重和相差太多，警告用户
    const weightSumElement = document.getElementById('weightSum');
    if (Math.abs(sum - 1.0) > 0.05) {
        weightSumElement.classList.add('text-danger');
    } else {
        weightSumElement.classList.remove('text-danger');
    }
}

// 根据运行模式调整UI
function adjustUIByMode(mode) {
    // 可以根据不同模式显示/隐藏不同配置选项
    const daysInput = document.getElementById('days');
    const strategySelect = document.getElementById('strategy');
    
    switch(mode) {
        case 'train':
            daysInput.disabled = true;
            strategySelect.disabled = true;
            document.getElementById('modelSettings').classList.remove('d-none');
            break;
        case 'evaluate':
            daysInput.disabled = false;
            strategySelect.disabled = false;
            document.getElementById('modelSettings').classList.remove('d-none');
            break;
        case 'simulate':
            daysInput.disabled = false;
            strategySelect.disabled = false;
            document.getElementById('modelSettings').classList.add('d-none');
            break;
        case 'visualize':
            daysInput.disabled = true;
            strategySelect.disabled = false;
            document.getElementById('modelSettings').classList.add('d-none');
            break;
        case 'test':
            daysInput.disabled = true;
            strategySelect.disabled = true;
            document.getElementById('modelSettings').classList.add('d-none');
            break;
        case 'all':
            daysInput.disabled = false;
            strategySelect.disabled = false;
            document.getElementById('modelSettings').classList.remove('d-none');
            break;
    }
}

// 执行操作
async function runOperation() {
    // 获取表单数据
    const mode = document.getElementById('runMode').value;
    const strategy = document.getElementById('strategy').value;
    const days = parseInt(document.getElementById('days').value);
    const outputDir = document.getElementById('outputDir').value;
    const logLevel = document.getElementById('logLevel').value;
    
    // 获取其他配置
    const params = {
        strategy: strategy,
        days: days,
        outputDir: outputDir,
        logLevel: logLevel,
        
        // 环境配置
        gridId: document.getElementById('gridId').value,
        chargerCount: document.getElementById('chargerCount').value,
        userCount: document.getElementById('userCount').value,
        timeStep: document.getElementById('timeStep').value,
        
        // 模型配置
        hiddenDim: document.getElementById('hiddenDim').value,
        taskHiddenDim: document.getElementById('taskHiddenDim').value,
        useTrainedModel: document.getElementById('useTrainedModel').checked,
        modelPath: document.getElementById('modelPath').value,
        
        // 权重配置
        userSatisfactionWeight: document.getElementById('userSatisfactionWeight').value,
        operatorProfitWeight: document.getElementById('operatorProfitWeight').value,
        gridFriendlinessWeight: document.getElementById('gridFriendlinessWeight').value
    };
    
    // 显示进度条
    document.getElementById('simulationProgress').style.display = 'block';
    document.getElementById('runButton').disabled = true;
    
    try {
        // 调用API启动任务
        const response = await API.runTask(mode, params);
        
        if (response && response.taskId) {
            // 开始轮询任务状态
            startStatusPolling();
        } else {
            throw new Error('任务启动失败');
        }
    } catch (error) {
        showError('启动任务失败: ' + error.message);
        document.getElementById('runButton').disabled = false;
    }
}

// 显示错误消息
function showError(message) {
    // 创建错误提示
    const errorDiv = document.createElement('div');
    errorDiv.className = 'alert alert-danger alert-dismissible fade show';
    errorDiv.role = 'alert';
    errorDiv.innerHTML = `
        <strong>错误!</strong> ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
    `;
    
    // 添加到页面
    const container = document.querySelector('.container-fluid');
    container.insertBefore(errorDiv, container.firstChild);
    
    // 5秒后自动关闭
    setTimeout(() => {
        const alert = bootstrap.Alert.getOrCreateInstance(errorDiv);
        alert.close();
    }, 5000);
}

// 开始轮询任务状态
function startStatusPolling() {
    if (statusPollTimer) {
        clearInterval(statusPollTimer);
    }
    
    statusPollTimer = setInterval(async function() {
        try {
            const status = await API.getStatus();
            
            if (status) {
                updateProgressUI(status);
                
                // 如果任务完成或失败，停止轮询
                if (status.status === 'completed' || status.status === 'failed') {
                    clearInterval(statusPollTimer);
                    document.getElementById('runButton').disabled = false;
                    
                    // 任务完成后更新数据显示
                    if (status.status === 'completed') {
                        await refreshAllData();
                    } else if (status.status === 'failed') {
                        showError(status.message || '任务执行失败');
                    }
                }
            }
        } catch (error) {
            console.error('轮询状态失败:', error);
        }
    }, STATUS_POLL_INTERVAL);
}

// 更新进度UI
function updateProgressUI(status) {
    document.getElementById('progressText').textContent = `${Math.round(status.progress)}%`;
    document.getElementById('progressBar').style.width = `${status.progress}%`;
    document.getElementById('statusMessage').textContent = status.message || '处理中...';
    
    // 如果任务完成，显示结果
    if (status.status === 'completed' && status.result) {
        updateResultsUI(status.result);
    }
}

// 更新结果UI
function updateResultsUI(result) {
    // 更新指标显示
    if (result.avg_metrics) {
        updateMetricsDisplay(result.avg_metrics);
    }
    
    // 如果有图表数据，更新图表
    if (result.metrics) {
        updateCharts(result.metrics);
    }
    
    // 如果是评估结果，更新评估表格
    if (result.strategy_names && result.user_satisfaction) {
        updateEvaluationTable(result);
    }
    
    // 如果是用户分析结果，更新用户分析图表
    if (result.hourly_demand) {
        updateUserAnalysisCharts(result);
    }
    
    // 如果是电网分析结果，更新电网分析图表
    if (result.hourly_load) {
        updateGridAnalysisCharts(result);
    }
}

// 更新指标显示
function updateMetricsDisplay(metrics) {
    // 更新核心指标卡片
    if (metrics.user_satisfaction !== undefined) {
        document.getElementById('userSatisfaction').textContent = metrics.user_satisfaction.toFixed(4);
        document.getElementById('userSatisfactionBar').style.width = `${metrics.user_satisfaction * 100}%`;
    }
    
    if (metrics.operator_profit !== undefined) {
        document.getElementById('operatorProfit').textContent = metrics.operator_profit.toFixed(4);
        document.getElementById('operatorProfitBar').style.width = `${metrics.operator_profit * 100}%`;
    }
    
    if (metrics.grid_friendliness !== undefined) {
        // 确保grid_friendliness在0-1范围内显示
        const normalizedValue = (metrics.grid_friendliness + 1) / 2; // 从[-1,1]转换到[0,1]
        document.getElementById('gridFriendliness').textContent = metrics.grid_friendliness.toFixed(4);
        document.getElementById('gridFriendlinessBar').style.width = `${normalizedValue * 100}%`;
    }
    
    if (metrics.total_reward !== undefined) {
        document.getElementById('totalReward').textContent = metrics.total_reward.toFixed(4);
        document.getElementById('totalRewardBar').style.width = `${metrics.total_reward * 100}%`;
    }
}


// 刷新所有数据
async function refreshAllData() {
    try {
        // 获取充电桩状态
        const chargersData = await API.getChargers();
        if (chargersData && chargersData.chargers) {
            updateChargersTable(chargersData.chargers);
        }
        
        // 获取调度决策
        const decisionsData = await API.getDecisions();
        if (decisionsData && decisionsData.decisions) {
            updateSchedulingTable(decisionsData.decisions);
        }
        
        // 获取电网状态
        const gridData = await API.getGrid();
        if (gridData && gridData.grid) {
            updateGridDisplay(gridData.grid);
        }
        
        // 获取用户分析数据
        const userAnalysis = await API.getUserAnalysis();
        if (userAnalysis) {
            updateUserAnalysisCharts(userAnalysis);
        }
        
        // 获取电网分析数据
        const gridAnalysis = await API.getGridAnalysis();
        if (gridAnalysis) {
            updateGridAnalysisCharts(gridAnalysis);
        }
        
        // 开始定时更新数据
        startDataUpdates();
        
    } catch (error) {
        console.error('刷新数据失败:', error);
        showError('刷新数据失败: ' + error.message);
    }
}

// 开始定时更新数据
function startDataUpdates() {
    if (dataUpdateTimer) {
        clearInterval(dataUpdateTimer);
    }
    
    dataUpdateTimer = setInterval(async function() {
        try {
            // 获取充电桩状态
            const chargersData = await API.getChargers();
            if (chargersData && chargersData.chargers) {
                updateChargersTable(chargersData.chargers);
            }
            
            // 获取调度决策
            const decisionsData = await API.getDecisions();
            if (decisionsData && decisionsData.decisions) {
                updateSchedulingTable(decisionsData.decisions);
            }
            
            // 获取电网状态
            const gridData = await API.getGrid();
            if (gridData && gridData.grid) {
                updateGridDisplay(gridData.grid);
                
                // 更新实时负载图表
                if (window.realTimeLoadChart) {
                    updateRealTimeLoadChart(gridData.grid);
                }
            }
        } catch (error) {
            console.error('更新数据失败:', error);
        }
    }, DATA_UPDATE_INTERVAL);
}

// 更新充电桩表格
function updateChargersTable(chargers) {
    const tableBody = document.getElementById('chargerTableBody');
    if (!tableBody) return;
    
    // 清空表格
    tableBody.innerHTML = '';
    
    // 添加充电桩数据
    chargers.forEach(charger => {
        const row = document.createElement('tr');
        
        // 确定充电桩状态
        let statusClass = 'charger-status-available';
        let statusText = '空闲';
        
        if (charger.health_score < 70) {
            statusClass = 'charger-status-maintenance';
            statusText = '维护中';
        } else if (charger.queue_length > 0) {
            statusClass = 'charger-status-busy';
            statusText = '使用中';
        }
        
        row.innerHTML = `
            <td>${charger.charger_id}</td>
            <td>${charger.position ? getLocationName(charger.position) : '未知'}</td>
            <td>${charger.charger_type === 'fast' ? '快充' : '慢充'}</td>
            <td><span class="charger-status-indicator ${statusClass}"></span>${statusText}</td>
            <td>${charger.queue_length}</td>
            <td>${charger.health_score.toFixed(0)}%</td>
        `;
        
        tableBody.appendChild(row);
    });
}

// 根据位置获取区域名称
function getLocationName(position) {
    // 简化版，实际应用中可以使用地理编码服务
    const lat = position.lat;
    const lng = position.lng;
    
    if (lat > 30.65 && lng > 104.1) return '城东商圈';
    if (lat > 30.65 && lng < 104.1) return '西区工业园';
    if (lat < 30.55) return '南湖科技园';
    if (lat > 30.55 && lat < 30.65 && lng > 104.1) return '中央车站';
    return '北城商务区';
}

// 更新调度表格
function updateSchedulingTable(decisions) {
    const tableBody = document.getElementById('schedulingTableBody');
    if (!tableBody) return;
    
    // 清空表格
    tableBody.innerHTML = '';
    
    // 添加调度决策数据
    decisions.forEach(decision => {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${decision.user_id}</td>
            <td>${getUserTypeName(decision.user_type)}</td>
            <td>${decision.soc}%</td>
            <td>${decision.charger_id}</td>
            <td>${decision.wait_time}分钟</td>
            <td>¥${decision.estimated_cost.toFixed(1)}</td>
        `;
        
        tableBody.appendChild(row);
    });
}

// 获取用户类型名称
function getUserTypeName(type) {
    switch(type) {
        case 'taxi': return '出租车';
        case 'private': return '私家车';
        case 'ride_hailing': return '网约车';
        case 'logistics': return '物流车';
        case '出租车': return '出租车';
        case '私家车': return '私家车';
        case '网约车': return '网约车';
        case '物流车': return '物流车';
        default: return type || '未知';
    }
}

// 更新电网显示
function updateGridDisplay(grid) {
    // 更新实时负载图表
    if (window.realTimeLoadChart) {
        updateRealTimeLoadChart(grid);
    }
    
    // 更新当前电价显示
    const currentPrice = document.getElementById('current-price');
    if (currentPrice && grid.current_price !== undefined) {
        currentPrice.textContent = `${grid.current_price.toFixed(2)}元/度`;
    }
    
    // 更新电网负载
    const gridLoad = document.getElementById('grid-load');
    if (gridLoad && grid.current_load !== undefined) {
        gridLoad.textContent = `${grid.current_load.toFixed(0)}%`;
    }
    
    // 更新当前时间
    const currentTime = document.getElementById('current-time');
    if (currentTime) {
        currentTime.textContent = new Date().toLocaleString('zh-CN');
    }
}

// 导出结果
function exportResults() {
    // 创建一个包含所有结果的对象
    const exportData = {
        timestamp: new Date().toISOString(),
        metrics: {
            user_satisfaction: document.getElementById('userSatisfaction').textContent,
            operator_profit: document.getElementById('operatorProfit').textContent,
            grid_friendliness: document.getElementById('gridFriendliness').textContent,
            total_reward: document.getElementById('totalReward').textContent
        },
        config: {
            mode: document.getElementById('runMode').value,
            strategy: document.getElementById('strategy').value,
            days: document.getElementById('days').value,
            charger_count: document.getElementById('chargerCount').value,
            user_count: document.getElementById('userCount').value
        }
    };
    
    // 将对象转换为JSON
    const dataStr = JSON.stringify(exportData, null, 2);
    
    // 创建一个Blob
    const blob = new Blob([dataStr], { type: 'application/json' });
    
    // 创建下载链接
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `ev_charging_results_${new Date().toISOString().slice(0,10)}.json`;
    
    // 触发下载
    document.body.appendChild(a);
    a.click();
    
    // 清理
    setTimeout(() => {
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }, 0);
}

// 检查系统状态
async function checkSystemStatus() {
    try {
        const status = await API.getStatus();
        
        if (status && status.status === 'running') {
            // 如果有任务正在运行，显示进度条并禁用运行按钮
            document.getElementById('simulationProgress').style.display = 'block';
            document.getElementById('runButton').disabled = true;
            
            // 开始轮询状态
            startStatusPolling();
        }
    } catch (error) {
        console.error('检查系统状态失败:', error);
    }
}

// 更新评估表格
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
    
    // 更新策略比较图表
    if (window.strategyComparisonChart && result.strategy_names) {
        updateStrategyComparisonChart(result);
    }
}

// 初始化图表
function initCharts() {
    if (typeof Chart === 'undefined') {
        console.error('Chart.js 未加载，无法初始化图表');
        return;
    }
    
    // 初始化实时负载图表
    initRealTimeLoadChart();
    
    // 初始化策略比较图表
    initStrategyComparisonChart();
    
    // 初始化小时负载图表
    initHourlyLoadChart();
    
    // 初始化用户类型图表
    initUserTypeChart();
}

// 初始化实时负载图表
function initRealTimeLoadChart() {
    const ctx = document.getElementById('realTimeLoad');
    if (!ctx) return;
    
    // 创建24小时标签
    const hourLabels = Array(24).fill().map((_, i) => `${i}:00`);
    
    window.realTimeLoadChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: hourLabels,
            datasets: [{
                label: '电网负载 (%)',
                data: Array(24).fill(null),
                borderColor: 'rgba(54, 162, 235, 1)',
                backgroundColor: 'rgba(54, 162, 235, 0.2)',
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

// 更新实时负载图表
function updateRealTimeLoadChart(grid) {
    if (!window.realTimeLoadChart) return;
    
    // 获取当前小时
    const currentHour = new Date().getHours();
    
    // 更新数据点
    window.realTimeLoadChart.data.datasets[0].data[currentHour] = grid.current_load;
    
    // 高亮峰谷时段
    const isPeakHour = grid.is_peak_hour;
    const isValleyHour = grid.is_valley_hour;
    
    if (isPeakHour) {
        window.realTimeLoadChart.data.datasets[0].borderColor = 'rgba(255, 99, 132, 1)';
        window.realTimeLoadChart.data.datasets[0].backgroundColor = 'rgba(255, 99, 132, 0.2)';
    } else if (isValleyHour) {
        window.realTimeLoadChart.data.datasets[0].borderColor = 'rgba(75, 192, 192, 1)';
        window.realTimeLoadChart.data.datasets[0].backgroundColor = 'rgba(75, 192, 192, 0.2)';
    } else {
        window.realTimeLoadChart.data.datasets[0].borderColor = 'rgba(54, 162, 235, 1)';
        window.realTimeLoadChart.data.datasets[0].backgroundColor = 'rgba(54, 162, 235, 0.2)';
    }
    
    window.realTimeLoadChart.update();
}

// 初始化策略比较图表
function initStrategyComparisonChart() {
    const ctx = document.getElementById('strategyComparisonChart');
    if (!ctx) return;
    
    window.strategyComparisonChart = new Chart(ctx, {
        type: 'radar',
        data: {
            labels: ['用户满意度', '运营商利润', '电网友好度', '综合奖励'],
            datasets: [
                {
                    label: '用户优先策略',
                    data: [0.85, 0.65, 0.55, 0.72],
                    backgroundColor: 'rgba(255, 99, 132, 0.2)',
                    borderColor: 'rgba(255, 99, 132, 1)',
                    pointBackgroundColor: 'rgba(255, 99, 132, 1)',
                    pointBorderColor: '#fff',
                    pointHoverBackgroundColor: '#fff',
                    pointHoverBorderColor: 'rgba(255, 99, 132, 1)'
                },
                {
                    label: '利润优先策略',
                    data: [0.65, 0.85, 0.60, 0.70],
                    backgroundColor: 'rgba(54, 162, 235, 0.2)',
                    borderColor: 'rgba(54, 162, 235, 1)',
                    pointBackgroundColor: 'rgba(54, 162, 235, 1)',
                    pointBorderColor: '#fff',
                    pointHoverBackgroundColor: '#fff',
                    pointHoverBorderColor: 'rgba(54, 162, 235, 1)'
                },
                {
                    label: '电网友好策略',
                    data: [0.60, 0.65, 0.85, 0.70],
                    backgroundColor: 'rgba(75, 192, 192, 0.2)',
                    borderColor: 'rgba(75, 192, 192, 1)',
                    pointBackgroundColor: 'rgba(75, 192, 192, 1)',
                    pointBorderColor: '#fff',
                    pointHoverBackgroundColor: '#fff',
                    pointHoverBorderColor: 'rgba(75, 192, 192, 1)'
                },
                {
                    label: '平衡策略',
                    data: [0.75, 0.75, 0.75, 0.78],
                    backgroundColor: 'rgba(255, 206, 86, 0.2)',
                    borderColor: 'rgba(255, 206, 86, 1)',
                    pointBackgroundColor: 'rgba(255, 206, 86, 1)',
                    pointBorderColor: '#fff',
                    pointHoverBackgroundColor: '#fff',
                    pointHoverBorderColor: 'rgba(255, 206, 86, 1)'
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

// 更新策略比较图表
function updateStrategyComparisonChart(result) {
    if (!window.strategyComparisonChart) return;
    
    // 检查是否有必要的数据
    if (!result.strategy_names || !result.user_satisfaction || !result.operator_profit || !result.grid_friendliness || !result.total_reward) {
        return;
    }
    
    // 更新数据集
    window.strategyComparisonChart.data.datasets = [];
    
    // 颜色列表
    const colors = [
        { border: 'rgba(255, 99, 132, 1)', background: 'rgba(255, 99, 132, 0.2)' },
        { border: 'rgba(54, 162, 235, 1)', background: 'rgba(54, 162, 235, 0.2)' },
        { border: 'rgba(75, 192, 192, 1)', background: 'rgba(75, 192, 192, 0.2)' },
        { border: 'rgba(255, 206, 86, 1)', background: 'rgba(255, 206, 86, 0.2)' },
        { border: 'rgba(153, 102, 255, 1)', background: 'rgba(153, 102, 255, 0.2)' }
    ];
    
    // 为每个策略创建数据集
    result.strategy_names.forEach((strategy, i) => {
        const colorIndex = i % colors.length;
        const color = colors[colorIndex];
        
        window.strategyComparisonChart.data.datasets.push({
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
    
    window.strategyComparisonChart.update();
}

// 初始化小时负载图表
function initHourlyLoadChart() {
    const ctx = document.getElementById('hourlyLoadChart');
    if (!ctx) return;
    
    // 创建24小时标签
    const hourLabels = Array(24).fill().map((_, i) => `${i}:00`);
    
    window.hourlyLoadChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: hourLabels,
            datasets: [
                {
                    label: '有序调度',
                    data: [40, 35, 30, 28, 27, 30, 45, 60, 75, 80, 82, 84, 80, 75, 70, 65, 70, 75, 85, 80, 70, 60, 50, 45],
                    borderColor: 'rgba(54, 162, 235, 1)',
                    backgroundColor: 'rgba(54, 162, 235, 0.2)',
                    borderWidth: 2,
                    tension: 0.4,
                    fill: true
                },
                {
                    label: '无序充电',
                    data: [40, 35, 30, 28, 27, 30, 55, 75, 90, 92, 94, 90, 85, 80, 75, 70, 80, 90, 95, 85, 75, 65, 55, 45],
                    borderColor: 'rgba(255, 99, 132, 1)',
                    backgroundColor: 'rgba(255, 99, 132, 0.2)',
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
                }
            }
        }
    });
}

// 更新小时负载图表
function updateHourlyLoadChart(hourlyLoad) {
    if (!window.hourlyLoadChart || !hourlyLoad) return;
    
    // 检查是否有必要的数据
    if (!hourlyLoad.with_scheduling || !hourlyLoad.without_scheduling) {
        return;
    }
    
    // 更新数据集
    window.hourlyLoadChart.data.datasets[0].data = hourlyLoad.with_scheduling;
    window.hourlyLoadChart.data.datasets[1].data = hourlyLoad.without_scheduling;
    
    window.hourlyLoadChart.update();
}

// 初始化用户类型图表
function initUserTypeChart() {
    const ctx = document.getElementById('userTypeChart');
    if (!ctx) return;
    
    window.userTypeChart = new Chart(ctx, {
        type: 'pie',
        data: {
            labels: ['出租车', '私家车', '网约车', '物流车'],
            datasets: [{
                data: [25, 40, 20, 15],
                backgroundColor: [
                    'rgba(255, 99, 132, 0.7)',
                    'rgba(54, 162, 235, 0.7)',
                    'rgba(255, 206, 86, 0.7)',
                    'rgba(75, 192, 192, 0.7)'
                ],
                borderColor: [
                    'rgba(255, 99, 132, 1)',
                    'rgba(54, 162, 235, 1)',
                    'rgba(255, 206, 86, 1)',
                    'rgba(75, 192, 192, 1)'
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

// 更新用户类型图表
function updateUserTypeChart(userTypeDistribution) {
    if (!window.userTypeChart || !userTypeDistribution) return;
    
    // 提取标签和数据
    const labels = Object.keys(userTypeDistribution);
    const data = Object.values(userTypeDistribution);
    
    // 更新图表数据
    window.userTypeChart.data.labels = labels;
    window.userTypeChart.data.datasets[0].data = data;
    
    window.userTypeChart.update();
}

// 更新用户分析图表
function updateUserAnalysisCharts(analysis) {
    // 更新用户类型分布
    if (analysis.user_type_distribution) {
        updateUserTypeChart(analysis.user_type_distribution);
    }
    
    // 更新充电需求分布
    if (analysis.hourly_demand && window.hourlyDemandChart) {
        window.hourlyDemandChart.data.datasets[0].data = analysis.hourly_demand;
        window.hourlyDemandChart.update();
    }
    
    // 更新平均充电SOC
    if (analysis.avg_soc_at_charge && window.avgSocChart) {
        const labels = Object.keys(analysis.avg_soc_at_charge);
        const data = Object.values(analysis.avg_soc_at_charge);
        
        window.avgSocChart.data.labels = labels;
        window.avgSocChart.data.datasets[0].data = data;
        window.avgSocChart.update();
    }
    
    // 更新充电频率
    if (analysis.charging_frequency && window.chargingFrequencyChart) {
        const labels = Object.keys(analysis.charging_frequency);
        const data = Object.values(analysis.charging_frequency);
        
        window.chargingFrequencyChart.data.labels = labels;
        window.chargingFrequencyChart.data.datasets[0].data = data;
        window.chargingFrequencyChart.update();
    }
}

// 更新电网分析图表
function updateGridAnalysisCharts(analysis) {
    // 更新小时负载
    if (analysis.hourly_load) {
        updateHourlyLoadChart(analysis.hourly_load);
    }
    
    // 更新峰值负载
    if (analysis.peak_load && window.peakLoadChart) {
        window.peakLoadChart.data.datasets[0].data = [
            analysis.peak_load.with_scheduling,
            analysis.peak_load.without_scheduling
        ];
        window.peakLoadChart.update();
    }
    
    // 更新负载均衡
    if (analysis.load_variance && window.loadVarianceChart) {
        window.loadVarianceChart.data.datasets[0].data = [
            analysis.load_variance.with_scheduling,
            analysis.load_variance.without_scheduling
        ];
        window.loadVarianceChart.update();
    }
    
    // 更新可再生能源利用
    if (analysis.renewable_utilization && window.renewableChart) {
        window.renewableChart.data.datasets[0].data = [
            analysis.renewable_utilization.with_scheduling,
            analysis.renewable_utilization.without_scheduling
        ];
        window.renewableChart.update();
    }
}

// 更新图表数据
function updateCharts(metrics) {
    // 这里可以更新各种图表的数据
    // 示例：更新结果图表的URL
    const chargingResultImage = document.getElementById('chargingResultImage');
    if (chargingResultImage) {
        chargingResultImage.src = `api/results/charging_scheduler_results.png?t=${Date.now()}`;
    }
    
    const learningCurvesImage = document.getElementById('learningCurvesImage');
    if (learningCurvesImage) {
        learningCurvesImage.src = `api/results/learning_curves.png?t=${Date.now()}`;
    }
}