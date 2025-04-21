// Global variables
let config = {};
let simulation = {
    running: false,
    algorithm: 'rule_based', // Track current algorithm
    updateInterval: null,
    speed: 1000, // Milliseconds per status update
    history: [],
    metricsHistory: {
        timestamps: [],
        userSatisfaction: [],
        operatorProfit: [],
        gridFriendliness: [],
        totalReward: []
    },
    gridLoadHistory: {
        timestamps: [],
        baseLoad: [],
        evLoad: [],
        totalLoad: []
    },
    agentMetrics: {
        userDecisions: 0,
        profitDecisions: 0,
        gridDecisions: 0,
        userAdoption: 0,
        profitAdoption: 0,
        gridAdoption: 0,
        conflicts: []
    },
    notifiedCompletion: false // 添加标志位，记录是否已通知完成
};

// Charts
let metricsChart;
let gridLoadChart;
let userWaitTimeChart;
let chargerHeatmap;
let agentWeightsChart;
let agentRewardsChart;
let conflictsChart;

// DOM Elements
const startBtn = document.getElementById('btn-start-simulation');
const pauseBtn = document.getElementById('btn-pause-simulation');
const resetBtn = document.getElementById('btn-reset-simulation');
const simulationDays = document.getElementById('simulation-days');
const daysValue = document.getElementById('days-value');
const strategySelect = document.getElementById('strategy-select');
const multiAgentSwitch = document.getElementById('multi-agent-switch');
const simulationTime = document.getElementById('simulation-time');
const simulationProgress = document.getElementById('simulation-progress');
const metricUser = document.getElementById('metric-user');
const metricProfit = document.getElementById('metric-profit');
const metricGrid = document.getElementById('metric-grid');
const metricTotal = document.getElementById('metric-total');
const overviewUserSatisfaction = document.getElementById('overview-user-satisfaction');
const overviewOperatorProfit = document.getElementById('overview-operator-profit');
const overviewGridFriendliness = document.getElementById('overview-grid-friendliness');
const overviewTotalScore = document.getElementById('overview-total-score');
const userTrend = document.getElementById('user-trend');
const profitTrend = document.getElementById('profit-trend');
const gridTrend = document.getElementById('grid-trend');
const totalTrend = document.getElementById('total-trend');
const multiAgentCard = document.getElementById('multi-agent-card');
const agentDecisionPanel = document.getElementById('agent-decision-panel');
const userAgentDecisions = document.getElementById('user-agent-decisions');
const profitAgentDecisions = document.getElementById('profit-agent-decisions');
const gridAgentDecisions = document.getElementById('grid-agent-decisions');
const userAgentAdoption = document.getElementById('user-agent-adoption');
const profitAgentAdoption = document.getElementById('profit-agent-adoption');
const gridAgentAdoption = document.getElementById('grid-agent-adoption');
const userAgentReward = document.getElementById('user-agent-reward');
const profitAgentReward = document.getElementById('profit-agent-reward');
const gridAgentReward = document.getElementById('grid-agent-reward');
const resultSelectBtn = document.getElementById('btn-load-result');
const pauseResumeBtn = document.getElementById('pause-resume-btn'); // Get the pause/resume button

let socket = null;
let isPaused = false; // Add a flag to track pause state

// 全局变量来跟踪选中的用户
let selectedUserId = null;

// 全局变量来存储所有创建的提示框
let allMapTooltips = [];

// 清除所有地图提示框
function clearAllMapTooltips() {
    if (allMapTooltips.length > 0) {
        allMapTooltips.forEach(tooltip => {
            if (tooltip && tooltip.destroy) {
                tooltip.destroy();
            }
        });
        allMapTooltips = [];
    }
}

// 在地图更新时检查鼠标位置并更新提示框
function checkMousePositionForTooltips() {
    const mapDiv = document.getElementById('actual-map');
    if (!mapDiv) return;
    
    const icons = [...mapDiv.querySelectorAll('.map-user-icon'), ...mapDiv.querySelectorAll('.map-charger-icon')];
    
    // 获取鼠标位置
    const mouseX = window.mouseX || 0;
    const mouseY = window.mouseY || 0;
    
    // 检查每个图标是否在鼠标下方
    icons.forEach(icon => {
        const rect = icon.getBoundingClientRect();
        if (
            mouseX >= rect.left &&
            mouseX <= rect.right &&
            mouseY >= rect.top &&
            mouseY <= rect.bottom
        ) {
            // 如果鼠标在图标上方，触发mouseenter事件
            const enterEvent = new MouseEvent('mouseenter');
            icon.dispatchEvent(enterEvent);
        }
    });
}

// 跟踪鼠标位置
function trackMousePosition() {
    document.addEventListener('mousemove', (e) => {
        window.mouseX = e.clientX;
        window.mouseY = e.clientY;
    });
}

// 检查jQuery是否可用，如果不可用则创建一个"no-op"函数以避免错误
if (typeof $ === 'undefined') {
    console.warn("jQuery未定义，使用基本兼容模式");
    // 创建一个简单的jQuery替代
    window.$ = function(selector) {
        const elements = document.querySelectorAll(selector);
        return {
            length: elements.length,
            on: function() { return this; },
            off: function() { return this; },
            ready: function(fn) { 
                if (document.readyState !== 'loading') {
                    fn();
                } else {
                    document.addEventListener('DOMContentLoaded', fn);
                }
                return this;
            },
            prop: function() { return this; },
            val: function() { return ""; },
            is: function() { return false; }
        };
    };
    
    // 添加document.ready作为别名
    window.$(document).ready = function(fn) {
        if (document.readyState !== 'loading') {
            fn();
        } else {
            document.addEventListener('DOMContentLoaded', fn);
        }
    };
}

// Initialize the application
$(document).ready(function() {
    console.log("Document is ready, starting initialization");
    
    // 测试API连接
    fetch('/api/config', {
        method: 'GET',
        headers: {
            'Content-Type': 'application/json',
            'X-Test-Mode': 'true'
        }
    })
    .then(response => {
        console.log("API连接测试 - 响应状态:", response.status, response.ok);
        return response.json();
    })
    .then(data => {
        console.log("API连接测试 - 成功获取配置:", data);
    })
    .catch(error => {
        console.error("API连接测试 - 错误:", error);
    });
    
    // 使用安全的DOM方式获取元素引用
    const getElement = (id) => document.getElementById(id);
    
    // 获取DOM元素
    const startBtn = getElement('btn-start-simulation');
    const pauseBtn = getElement('btn-pause-simulation');
    const resetBtn = getElement('btn-reset-simulation');
    
    console.log("获取的DOM元素:", {
        startBtn: startBtn ? "找到" : "未找到",
        pauseBtn: pauseBtn ? "找到" : "未找到",
        resetBtn: resetBtn ? "找到" : "未找到"
    });
    
    // 直接使用原生DOM方法绑定开始按钮
    if (startBtn) {
        startBtn.addEventListener('click', function(e) {
            console.log("开始按钮被点击 (原生DOM绑定)");
            if (typeof startSimulation === 'function') {
                startSimulation();
            }
        });
    }
    
    // 先绑定所有事件监听器，确保用户界面可响应
    setupEventListeners();
    
    // 然后加载配置并更新UI
    loadConfig().then(() => {
        console.log("Configuration loaded successfully");
        
        // 初始化图表
        initializeCharts();
        
        // 设置场景预设
        setupScenarioPresets();
        
        // 配置模态窗口初始化
        initializeConfigModal();
        
        // 确保配置保存按钮绑定事件
        const saveConfigBtn = getElement('save-config');
        if (saveConfigBtn) {
            saveConfigBtn.addEventListener('click', function() {
                console.log('保存配置按钮被点击 (原生DOM)');
                saveConfig();
            });
        }

        // 显示地图内容
        showMapContent();
        
        // 更新系统时间
        updateSystemTime();
        setInterval(updateSystemTime, 1000);
        
        // 定期更新模拟状态
        setInterval(updateSimulationStatus, 1000);
        
        console.log("Initialization complete");
    }).catch(error => {
        console.error("Error during initialization:", error);
    });

    // Initialize WebSocket connection on page load
    document.addEventListener('DOMContentLoaded', () => {
        // ... existing code ...
        connectWebSocket(); // Make sure WebSocket connects on load
    });

    // Make sure buttons are in the correct initial state
    startBtn.disabled = true; // Disabled until WebSocket connects
    stopSimBtn.disabled = true;
    pauseResumeBtn.disabled = true;
});

// Load configuration from server
async function loadConfig() {
    try {
        const response = await fetch('/api/config');
        config = await response.json();
        
        // Apply config to UI
        simulationDays.value = config.environment.simulation_days || 7;
        daysValue.textContent = `${simulationDays.value}天`;
        
        if (config.scheduler && config.scheduler.use_multi_agent) {
            multiAgentSwitch.checked = true;
            toggleMultiAgentUI(true);
        }
        
        // Set strategy based on weights in config
        const weights = config.scheduler.optimization_weights;
        if (weights) {
            if (weights.user_satisfaction > 0.5) {
                strategySelect.value = 'user';
            } else if (weights.operator_profit > 0.5) {
                strategySelect.value = 'profit';
            } else if (weights.grid_friendliness > 0.5) {
                strategySelect.value = 'grid';
            } else {
                strategySelect.value = 'balanced';
            }
        }
        
    } catch (error) {
        console.error('Error loading configuration:', error);
    }
}

// Initialize all charts
function initializeCharts() {
    // 1. Metrics Time Series Chart
    const metricsCtx = document.getElementById('metrics-chart').getContext('2d');
    metricsChart = new Chart(metricsCtx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [
                {
                    label: '用户满意度',
                    data: [],
                    borderColor: '#0d6efd',
                    backgroundColor: 'rgba(13, 110, 253, 0.1)',
                    tension: 0.2,
                    fill: true
                },
                {
                    label: '运营商利润',
                    data: [],
                    borderColor: '#198754',
                    backgroundColor: 'rgba(25, 135, 84, 0.1)',
                    tension: 0.2,
                    fill: true
                },
                {
                    label: '电网友好度',
                    data: [],
                    borderColor: '#0dcaf0',
                    backgroundColor: 'rgba(13, 202, 240, 0.1)',
                    tension: 0.2,
                    fill: true
                },
                {
                    label: '综合评分',
                    data: [],
                    borderColor: '#6c757d',
                    backgroundColor: 'rgba(108, 117, 125, 0.1)',
                    tension: 0.2,
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
                tooltip: {
                    mode: 'index',
                    intersect: false
                },
                zoom: {
                    zoom: {
                        wheel: {
                            enabled: true,
                        },
                        pinch: {
                            enabled: true
                        },
                        mode: 'x',
                    },
                    pan: {
                        enabled: true,
                        mode: 'x',
                    }
                }
            },
            scales: {
                y: {
                    min: -1,
                    max: 1
                }
            }
        }
    });
    
    // 2. Grid Load Chart
    const gridLoadCtx = document.getElementById('grid-load-chart').getContext('2d');
    gridLoadChart = new Chart(gridLoadCtx, {
        type: 'line',
        data: {
            labels: [], // 空标签，随模拟进行添加时间点
            datasets: [
                {
                    label: '电网基础负载',
                    data: [], // 空数据，随模拟进行添加数据点
                    borderColor: 'rgba(75, 192, 192, 1)',
                    backgroundColor: 'rgba(75, 192, 192, 0.2)',
                    fill: true
                },
                {
                    label: '充电负载',
                    data: [], // 空数据，随模拟进行添加数据点
                    borderColor: 'rgba(255, 99, 132, 1)',
                    backgroundColor: 'rgba(255, 99, 132, 0.2)',
                    fill: true
                },
                {
                    label: '总负载',
                    data: [], // 空数据，随模拟进行添加数据点
                    borderColor: 'rgba(54, 162, 235, 1)',
                    backgroundColor: 'rgba(54, 162, 235, 0.2)',
                    fill: false,
                    borderWidth: 2
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true,
                    title: {
                        display: true,
                        text: '负载 (kW)'
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
                title: {
                    display: true,
                    text: '电网负载变化'
                },
                legend: {
                    display: true,
                    position: 'top'
                }
            }
        }
    });
    
    // 3. User Wait Time Chart
    const userWaitCtx = document.getElementById('user-wait-time-chart').getContext('2d');
    userWaitTimeChart = new Chart(userWaitCtx, {
        type: 'bar',
        data: {
            labels: ['0-5分钟', '5-10分钟', '10-15分钟', '15-20分钟', '20-30分钟', '>30分钟'],
            datasets: [{
                label: '用户等待时间分布',
                data: [0, 0, 0, 0, 0, 0],
                backgroundColor: [
                    'rgba(40, 167, 69, 0.7)',
                    'rgba(23, 162, 184, 0.7)',
                    'rgba(255, 193, 7, 0.7)',
                    'rgba(255, 153, 0, 0.7)',
                    'rgba(220, 53, 69, 0.7)',
                    'rgba(108, 117, 125, 0.7)'
                ],
                borderColor: [
                    'rgb(40, 167, 69)',
                    'rgb(23, 162, 184)',
                    'rgb(255, 193, 7)',
                    'rgb(255, 153, 0)',
                    'rgb(220, 53, 69)',
                    'rgb(108, 117, 125)'
                ],
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return `${context.raw} 用户`;
                        }
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    title: {
                        display: true,
                        text: '用户数量'
                    }
                }
            }
        }
    });
    
    // 4. Charger Heatmap (placeholder, will be replaced with actual implementation)
    const chargerHeatmapCtx = document.getElementById('charger-heatmap').getContext('2d');
    chargerHeatmap = new Chart(chargerHeatmapCtx, {
        type: 'bar',
        data: {
            labels: ['充电站1', '充电站2', '充电站3', '充电站4', '充电站5'],
            datasets: [{
                label: '充电桩利用率',
                data: [70, 85, 45, 60, 90],
                backgroundColor: 'rgba(54, 162, 235, 0.7)'
            }]
        },
        options: {
            indexAxis: 'y',
            responsive: true,
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return `利用率: ${context.raw}%`;
                        }
                    }
                }
            },
            scales: {
                x: {
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
    
    // 5. Agent Weights Chart (for multi-agent system)
    const agentWeightsCtx = document.getElementById('agent-weights-chart').getContext('2d');
    agentWeightsChart = new Chart(agentWeightsCtx, {
        type: 'pie',
        data: {
            labels: ['用户满意度智能体', '运营商利润智能体', '电网友好度智能体'],
            datasets: [{
                data: [
                    config.scheduler?.optimization_weights?.user_satisfaction || 0.33,
                    config.scheduler?.optimization_weights?.operator_profit || 0.33,
                    config.scheduler?.optimization_weights?.grid_friendliness || 0.34
                ],
                backgroundColor: [
                    'rgba(13, 110, 253, 0.7)',
                    'rgba(25, 135, 84, 0.7)',
                    'rgba(13, 202, 240, 0.7)'
                ],
                borderColor: [
                    'rgb(13, 110, 253)',
                    'rgb(25, 135, 84)',
                    'rgb(13, 202, 240)'
                ],
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            plugins: {
                legend: {
                    position: 'bottom'
                },
                title: {
                    display: true,
                    text: '智能体权重分配'
                }
            }
        }
    });
    
    // 6. Agent Rewards Chart
    const agentRewardsCtx = document.getElementById('agent-rewards-chart').getContext('2d');
    agentRewardsChart = new Chart(agentRewardsCtx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [
                {
                    label: '用户满意度智能体',
                    data: [],
                    borderColor: '#0d6efd',
                    backgroundColor: 'rgba(13, 110, 253, 0.1)',
                    tension: 0.1
                },
                {
                    label: '运营商利润智能体',
                    data: [],
                    borderColor: '#198754',
                    backgroundColor: 'rgba(25, 135, 84, 0.1)',
                    tension: 0.1
                },
                {
                    label: '电网友好度智能体',
                    data: [],
                    borderColor: '#0dcaf0',
                    backgroundColor: 'rgba(13, 202, 240, 0.1)',
                    tension: 0.1
                }
            ]
        },
        options: {
            responsive: true,
            plugins: {
                legend: {
                    position: 'top'
                },
                title: {
                    display: true,
                    text: '智能体奖励'
                }
            },
            scales: {
                y: {
                    min: 0,
                    max: 1
                }
            }
        }
    });
    
    // 7. Coordination Conflicts Chart
    const conflictsCtx = document.getElementById('coordination-conflicts-chart').getContext('2d');
    conflictsChart = new Chart(conflictsCtx, {
        type: 'bar',
        data: {
            labels: [],
            datasets: [{
                label: '协调冲突数量',
                data: [],
                backgroundColor: 'rgba(220, 53, 69, 0.7)',
                borderColor: 'rgb(220, 53, 69)',
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            plugins: {
                legend: {
                    display: false
                },
                title: {
                    display: true,
                    text: '协调冲突数量'
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    title: {
                        display: true,
                        text: '冲突数量'
                    }
                }
            }
        }
    });
}

// Set up event listeners
function setupEventListeners() {
    console.log("Setting up event listeners");
    
    // 辅助函数：安全地获取DOM元素
    const getElement = (id) => document.getElementById(id);
    
    // 辅助函数：安全地添加事件监听器
    const addClickListener = (elementId, handler) => {
        const element = getElement(elementId);
        if (element) {
            // 先移除所有现有监听器（模拟jQuery的off方法）
            element.replaceWith(element.cloneNode(true));
            // 获取新的元素引用
            const newElement = getElement(elementId);
            if (newElement) {
                newElement.addEventListener('click', handler);
                return true;
            }
        }
        return false;
    };
    
    console.log("按钮元素检查:", {
        "startBtn元素": getElement('btn-start-simulation') ? "存在" : "不存在",
        "pauseBtn元素": getElement('btn-pause-simulation') ? "存在" : "不存在",
        "resetBtn元素": getElement('btn-reset-simulation') ? "存在" : "不存在"
    });
    
    // Start button
    addClickListener('btn-start-simulation', function(e) {
        console.log("Start button clicked (setupEventListeners原生DOM)");
        if (typeof startSimulation === 'function') {
            startSimulation();
        } else {
            console.error("startSimulation函数未定义");
        }
    });
    
    // Pause button
    addClickListener('btn-pause-simulation', function(e) {
        console.log("Pause button clicked (setupEventListeners原生DOM)");
        if (typeof pauseSimulation === 'function') {
            pauseSimulation();
        }
    });
    
    // Reset button
    addClickListener('btn-reset-simulation', function(e) {
        console.log("Reset button clicked (setupEventListeners原生DOM)");
        if (typeof resetSimulation === 'function') {
            resetSimulation();
        }
    });
    
    // Simulation days slider
    const daysSlider = getElement('simulation-days');
    const daysValue = getElement('days-value');
    if (daysSlider && daysValue) {
        daysSlider.addEventListener('input', function() {
            console.log("Simulation days changed:", this.value);
            daysValue.textContent = `${this.value}天`;
        });
    }
    
    // Multi-agent switch
    const multiAgentSwitch = getElement('multi-agent-switch');
    if (multiAgentSwitch) {
        multiAgentSwitch.addEventListener('change', function() {
            console.log("Multi-agent switch changed:", this.checked);
            if (typeof toggleMultiAgentUI === 'function') {
                toggleMultiAgentUI(this.checked);
            }
        });
    }
    
    // Load results button
    const resultSelectBtn = getElement('btn-load-result');
    if (resultSelectBtn) {
        resultSelectBtn.addEventListener('click', function() {
            console.log("Load result button clicked");
            if (typeof showResultsModal === 'function') {
                showResultsModal();
            }
        });
    }
    
    // Apply weights button
    addClickListener('apply-weights', function() {
        console.log("Apply weights button clicked");
        if (typeof applyAgentWeights === 'function') {
            applyAgentWeights();
        }
    });
    
    // Config save button - 确保这个事件被正确绑定
    addClickListener('save-config', function() {
        console.log("Save config button clicked");
        if (typeof saveConfig === 'function') {
            saveConfig();
        }
    });
    
    // Scenario apply button
    addClickListener('apply-scenario', function() {
        console.log("Apply scenario button clicked");
        if (typeof applyScenario === 'function') {
            applyScenario();
        }
    });
    
    // Strategy selection
    const strategySelect = getElement('strategy-select');
    if (strategySelect) {
        strategySelect.addEventListener('change', function() {
            console.log("Strategy changed:", this.value);
            if (typeof updateStrategyUI === 'function') {
                updateStrategyUI(this.value);
            }
        });
    }
    
    // Algorithm selection
    const algorithmSelect = getElement('algorithm-select');
    if (algorithmSelect) {
        algorithmSelect.addEventListener('change', function() {
            console.log("Algorithm changed:", this.value);
            if (typeof handleAlgorithmChange === 'function') {
                handleAlgorithmChange();
            }
        });
    }
    
    // Update multi-agent switch based on algorithm initially
    if (typeof handleAlgorithmChange === 'function') {
        handleAlgorithmChange(); // Call once on load
    }
    
    // Simulation speed controls
    addClickListener('sim-speed-1x', function() {
        console.log("Speed 1x clicked");
        if (typeof setSimulationSpeed === 'function') {
            setSimulationSpeed(1);
        }
    });
    
    addClickListener('sim-speed-2x', function() {
        console.log("Speed 2x clicked");
        if (typeof setSimulationSpeed === 'function') {
            setSimulationSpeed(2);
        }
    });
    
    addClickListener('sim-speed-5x', function() {
        console.log("Speed 5x clicked");
        if (typeof setSimulationSpeed === 'function') {
            setSimulationSpeed(5);
        }
    });
    
    addClickListener('sim-speed-max', function() {
        console.log("Speed max clicked");
        if (typeof setSimulationSpeed === 'function') {
            setSimulationSpeed(0);
        }
    });
    
    console.log("All event listeners setup complete");
}

// Set simulation speed
async function setSimulationSpeed(multiplier) {
    // Remove active class from all speed buttons in that group
    document.querySelectorAll('#navbarNav .btn-group .btn').forEach(btn => btn.classList.remove('active'));

    // Add active class to the clicked button
    let targetButtonId;
    if (multiplier === 1) targetButtonId = 'sim-speed-1x';
    else if (multiplier === 2) targetButtonId = 'sim-speed-2x';
    else if (multiplier === 5) targetButtonId = 'sim-speed-5x';
    else if (multiplier === 0) targetButtonId = 'sim-speed-max';

    if (targetButtonId) {
        const targetButton = document.getElementById(targetButtonId);
        if (targetButton) targetButton.classList.add('active');
    }

    try {
        const response = await fetch('/api/simulation/speed', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ multiplier: multiplier })
        });
        const data = await response.json();
        if (data.status === 'success') {
            let speedText = multiplier === 0 ? "最大" : `${multiplier}x`;
            showNotification(`模拟速度设置为 ${speedText}`, 'info');
            // Backend now controls the speed, no need to manage interval here
        } else {
            showNotification(data.message || '设置速度失败', 'danger');
            // Optionally remove active class on failure
            if (targetButtonId) {
                const targetButton = document.getElementById(targetButtonId);
                if (targetButton) targetButton.classList.remove('active');
            }
        }
    } catch (error) {
        console.error('Error setting simulation speed:', error);
        showNotification('设置速度时出错', 'danger');
        // Optionally remove active class on failure
        if (targetButtonId) {
            const targetButton = document.getElementById(targetButtonId);
            if (targetButton) targetButton.classList.remove('active');
        }
    }
}

// Toggle Multi-Agent UI elements
function toggleMultiAgentUI(show) {
    const multiAgentCard = document.getElementById('multi-agent-card');
    const agentDecisionPanel = document.getElementById('agent-decision-panel');
    const selectedAlgorithm = document.getElementById('algorithm-select')?.value;
    
    // Only show the weights card for 'coordinated_mas'
    const showWeightsCard = show && selectedAlgorithm === 'coordinated_mas';
    
    if (multiAgentCard) {
        multiAgentCard.style.display = showWeightsCard ? 'block' : 'none';
    }
    if (agentDecisionPanel) {
        // Decision panel might be relevant for both coordinated_mas and marl in the future
        // ... (existing code remains unchanged)
    }
}

// Update agent weight displays
function updateAgentWeightDisplay() {
    const userWeight = parseFloat(document.getElementById('user-satisfaction-weight').value);
    const profitWeight = parseFloat(document.getElementById('operator-profit-weight').value);
    const gridWeight = parseFloat(document.getElementById('grid-friendliness-weight').value);
    
    // Update display values
    document.querySelectorAll('.user-weight-display').forEach(el => el.textContent = userWeight.toFixed(2));
    document.querySelectorAll('.profit-weight-display').forEach(el => el.textContent = profitWeight.toFixed(2));
    document.querySelectorAll('.grid-weight-display').forEach(el => el.textContent = gridWeight.toFixed(2));
    
    // Calculate total
    const total = userWeight + profitWeight + gridWeight;
    
    // Normalize if needed (when total != 1)
    if (Math.abs(total - 1) > 0.001) {
        const normalizedUserWeight = userWeight / total;
        const normalizedProfitWeight = profitWeight / total;
        const normalizedGridWeight = gridWeight / total;
        
        // Update chart
        agentWeightsChart.data.datasets[0].data = [
            normalizedUserWeight,
            normalizedProfitWeight,
            normalizedGridWeight
        ];
    } else {
        // Update chart with raw values
        agentWeightsChart.data.datasets[0].data = [userWeight, profitWeight, gridWeight];
    }
    
    agentWeightsChart.update();
}

// Apply agent weights
function applyAgentWeights() {
    const userWeight = parseFloat(document.getElementById('user-satisfaction-weight').value);
    const profitWeight = parseFloat(document.getElementById('operator-profit-weight').value);
    const gridWeight = parseFloat(document.getElementById('grid-friendliness-weight').value);
    
    // Calculate total
    const total = userWeight + profitWeight + gridWeight;
    
    // Normalize weights
    const normalizedUserWeight = userWeight / total;
    const normalizedProfitWeight = profitWeight / total;
    const normalizedGridWeight = gridWeight / total;
    
    // Update config
    config.scheduler.optimization_weights = {
        user_satisfaction: normalizedUserWeight,
        operator_profit: normalizedProfitWeight,
        grid_friendliness: normalizedGridWeight
    };
    
    // If there's a multi-agent section in config, update there too
    if (config.multi_agent && config.multi_agent.agents) {
        if (config.multi_agent.agents.user_satisfaction) {
            config.multi_agent.agents.user_satisfaction.weight = normalizedUserWeight;
        }
        if (config.multi_agent.agents.operator_profit) {
            config.multi_agent.agents.operator_profit.weight = normalizedProfitWeight;
        }
        if (config.multi_agent.agents.grid_friendliness) {
            config.multi_agent.agents.grid_friendliness.weight = normalizedGridWeight;
        }
    }
    
    // Save config to server
    fetch('/api/config', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(config)
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'success') {
            showNotification('权重已更新', 'success');
        } else {
            showNotification('更新权重失败', 'danger');
        }
    })
    .catch(error => {
        console.error('Error updating weights:', error);
        showNotification('更新权重失败', 'danger');
    });
}

// Start simulation
async function startSimulation() {
    console.log("startSimulation 函数被调用");
    
    // 检查模拟是否已经在运行
    if (simulation.running) {
        console.log("模拟已经在运行中，忽略此次点击");
        return;
    }
    
    try {
        // 重置完成通知标志位
        simulation.notifiedCompletion = false;
        
        // 模拟按钮状态先更新
        $('#btn-start-simulation').prop('disabled', true);
        $('#btn-pause-simulation').prop('disabled', false);
        $('#btn-reset-simulation').prop('disabled', false);
        
        // Prepare data for API call
        const days = parseInt(document.getElementById('simulation-days').value) || 7;
        const strategy = document.getElementById('strategy-select').value || 'balanced';
        // Read selected algorithm
        const algorithm = document.getElementById('algorithm-select').value || 'rule_based';
        
        // Show starting notification
        showNotification('启动模拟中...', 'info');
        
        console.log('Starting simulation with settings:', { days, strategy, algorithm });
        
        // Call API to start simulation
        const response = await fetch('/api/simulation/start', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                days: days,
                strategy: strategy,
                algorithm: algorithm // Send selected algorithm
            })
        });
        
        const data = await response.json();
        console.log("API响应:", data);
        
        if (data.status === 'success') {
            // Update simulation state
            simulation.running = true;
            
            // Reset metrics history
            resetSimulationData();
            
            // Show success notification
            showNotification('模拟已启动', 'success');
            
            // If multi-agent is enabled, show related UI
            if (multiAgentSwitch.checked) {
                toggleMultiAgentUI(true);
            }
            
            console.log('Simulation started successfully!');
        } else {
            // 恢复按钮状态
            $('#btn-start-simulation').prop('disabled', false);
            $('#btn-pause-simulation').prop('disabled', true);
            
            console.error('Failed to start simulation:', data.message);
            showNotification(`启动失败: ${data.message}`, 'error');
        }
    } catch (error) {
        // 恢复按钮状态
        $('#btn-start-simulation').prop('disabled', false);
        $('#btn-pause-simulation').prop('disabled', true);
        
        console.error('Error starting simulation:', error);
        showNotification('启动模拟时发生错误，请检查控制台', 'error');
    }
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
            
            // Verify simulation was actually stopped by checking status
            setTimeout(() => {
                fetch('/api/simulation/status')
                .then(response => response.json())
                .then(statusData => {
                    if (statusData.running === true) {
                        // If still running, try stopping again
                        console.warn('Simulation still running after pause attempt, retrying...');
                        fetch('/api/simulation/stop', { method: 'POST' })
                        .then(() => {
                            simulation.running = false;
                            showNotification('模拟已暂停', 'warning');
                        });
                    } else {
                        showNotification('模拟已暂停', 'warning');
                    }
                })
                .catch(error => {
                    console.error('Error verifying simulation pause status:', error);
                });
            }, 500);
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
        // Wait for the simulation to actually stop before proceeding
        setTimeout(() => {
            completeResetWithResults();
        }, 1000);
    } else {
        completeResetWithResults();
    }
}

// Complete the reset process and load the most recent results
function completeResetWithResults() {
    // Reset UI state
    startBtn.disabled = false;
    pauseBtn.disabled = true;
    resetBtn.disabled = false;
    
    // First get the latest simulation results to display
    fetch('/api/simulation/results')
    .then(response => response.json())
    .then(data => {
        if (data.status === 'success' && data.results && data.results.length > 0) {
            // Get the most recent result file
            const latestResult = data.results[0];
            
            // Reset simulation data without clearing charts yet
            simulation.metricsHistory = {
                timestamps: [],
                userSatisfaction: [],
                operatorProfit: [],
                gridFriendliness: [],
                totalReward: []
            };
            
            simulation.gridLoadHistory = {
                timestamps: [],
                baseLoad: [],
                evLoad: [],
                totalLoad: []
            };
            
            simulation.agentMetrics = {
                userDecisions: 0,
                profitDecisions: 0,
                gridDecisions: 0,
                userAdoption: 0,
                profitAdoption: 0,
                gridAdoption: 0,
                conflicts: []
            };
            
            // Load the latest result
            fetch(`/api/simulation/result/${latestResult.filename}`)
            .then(response => response.json())
            .then(resultData => {
                if (resultData.status === 'success') {
                    showNotification('模拟已重置，显示上次模拟的最终结果', 'info');
                    
                    // Update time and progress
                    if (resultData.result.timestamp) {
                        const date = new Date(resultData.result.timestamp);
                        simulationTime.textContent = formatDateTime(date);
                    }
                    
                    // Set progress to 100% for completed simulation
                    simulationProgress.style.width = '100%';
                    simulationProgress.setAttribute('aria-valuenow', 100);
                    simulationProgress.textContent = '100%';
                    
                    // Update metrics
                    if (resultData.result.metrics) {
                        updateMetrics(resultData.result.metrics);
                    }
                    
                    // Update charts with time series data if available
                    if (resultData.metrics_series) {
                        const series = resultData.metrics_series;
                        
                        // Format timestamps
                        const formattedTimestamps = series.timestamps.map(t => {
                            const date = new Date(t);
                            return formatDateTime(date);
                        });
                        
                        // Update simulation metrics history
                        simulation.metricsHistory = {
                            timestamps: formattedTimestamps,
                            userSatisfaction: series.user_satisfaction || [],
                            operatorProfit: series.operator_profit || [],
                            gridFriendliness: series.grid_friendliness || [],
                            totalReward: series.total_reward || []
                        };
                        
                        // Update main metrics chart
                        metricsChart.data.labels = formattedTimestamps;
                        metricsChart.data.datasets[0].data = series.user_satisfaction || [];
                        metricsChart.data.datasets[1].data = series.operator_profit || [];
                        metricsChart.data.datasets[2].data = series.grid_friendliness || [];
                        metricsChart.data.datasets[3].data = series.total_reward || [];
                        metricsChart.update();
                        
                        // Update grid load chart if it exists
                        if (window.gridLoadChart && series.grid_load && series.ev_load) {
                            gridLoadChart.data.labels = formattedTimestamps;
                            gridLoadChart.data.datasets[0].data = series.grid_load;
                            gridLoadChart.data.datasets[1].data = series.ev_load;
                            gridLoadChart.update();
                        }
                    } else {
                        // If no time series data, reset charts
                        resetCharts();
                    }
                    
                    // Update other UI elements with final state
                    if (resultData.result) {
                        updateUIWithStateData(resultData.result);
                    }
                } else {
                    // If loading the result failed, just do a regular reset
                    performStandardReset();
                }
            })
            .catch(error => {
                console.error('Error loading simulation result during reset:', error);
                performStandardReset();
            });
        } else {
            // No results found, do standard reset
            performStandardReset();
        }
    })
    .catch(error => {
        console.error('Error fetching simulation results during reset:', error);
        performStandardReset();
    });
}

// Standard reset without loading previous results
function performStandardReset() {
    // Reset simulation data
    resetSimulationData();
    
    // Reset charts
    resetCharts();
    
    // Reset metrics
    updateMetrics({
        user_satisfaction: 0,
        operator_profit: 0,
        grid_friendliness: 0,
        total_reward: 0
    });
    
    // Reset simulation time and progress
    simulationTime.textContent = '0000-00-00 00:00';
    simulationProgress.style.width = '0%';
    simulationProgress.setAttribute('aria-valuenow', 0);
    simulationProgress.textContent = '0%';
    
    // Reset UI
    startBtn.disabled = false;
    pauseBtn.disabled = true;
    resetBtn.disabled = true;
    
    showNotification('模拟已重置', 'info');
}

// Reset simulation data
function resetSimulationData() {
    simulation.metricsHistory = {
        timestamps: [],
        userSatisfaction: [],
        operatorProfit: [],
        gridFriendliness: [],
        totalReward: []
    };
    
    // 添加电网负载历史数据结构
    simulation.gridLoadHistory = {
        timestamps: [],
        baseLoad: [],
        evLoad: [],
        totalLoad: []
    };
    
    simulation.agentMetrics = {
        userDecisions: 0,
        profitDecisions: 0,
        gridDecisions: 0,
        userAdoption: 0,
        profitAdoption: 0,
        gridAdoption: 0,
        conflicts: []
    };
    
    // 重置完成通知标志位
    simulation.notifiedCompletion = false;
    
    // 重置地图视图
    const mapContainer = document.getElementById('map-container');
    if (mapContainer) {
        // 恢复默认提示信息
        const defaultMessage = mapContainer.querySelector('.bg-light');
        if (defaultMessage) {
            defaultMessage.style.display = '';
        }
        
        // 移除地图内容
        const mapContent = mapContainer.querySelector('#actual-map');
        if (mapContent) {
            mapContent.remove();
        }
    }
}

// Reset all charts
function resetCharts() {
    // Metrics chart
    metricsChart.data.labels = [];
    metricsChart.data.datasets.forEach(dataset => {
        dataset.data = [];
    });
    metricsChart.update();
    
    // Grid load chart
    gridLoadChart.data.labels = [];
    gridLoadChart.data.datasets.forEach(dataset => {
        dataset.data = [];
    });
    gridLoadChart.update();
    
    // User wait time chart
    userWaitTimeChart.data.datasets[0].data = [0, 0, 0, 0, 0, 0];
    userWaitTimeChart.update();
    
    // Charger heatmap (placeholder)
    chargerHeatmap.data.datasets[0].data = [70, 85, 45, 60, 90];
    chargerHeatmap.update();
    
    // Agent rewards chart
    agentRewardsChart.data.labels = [];
    agentRewardsChart.data.datasets.forEach(dataset => {
        dataset.data = [];
    });
    agentRewardsChart.update();
    
    // Conflicts chart
    conflictsChart.data.labels = [];
    conflictsChart.data.datasets[0].data = [];
    conflictsChart.update();
}

// Update simulation status
async function updateSimulationStatus() {
    try {
        // Skip if we're not in a page with simulation status elements
        if (!simulationTime || !simulationProgress) {
            return;
        }
        
        // Call API to get simulation status
        console.log("Fetching simulation status...");
        const response = await fetch('/api/simulation/status');
        
        if (!response.ok) {
            console.error('Failed to fetch simulation status:', response.statusText);
            return;
        }
        
        const data = await response.json();
        console.log('Simulation status:', data);
        
        // Update UI based on running status
        const wasRunning = simulation.running;
        simulation.running = data.running;
        
        // Update button states
        startBtn.disabled = simulation.running;
        pauseBtn.disabled = !simulation.running;
        
        // 检查模拟是否停止
        if (!simulation.running && wasRunning) {
            console.log("Simulation stopped");
            // 只有在未通知过的情况下才显示提示
            if (!simulation.notifiedCompletion) {
                showNotification('模拟已完成或已停止', 'info');
                simulation.notifiedCompletion = true; // 标记已通知
            }
            return; // 模拟已停止，不再更新图表
        }
        
        if (!data.state) {
            console.warn("No state data in simulation status response");
            return;
        }
        
        // Update simulation time
        if (data.state.timestamp) {
            const date = new Date(data.state.timestamp);
            simulationTime.textContent = formatDateTime(date);
        }
        
        // Update progress bar
        if (data.state.progress !== undefined) {
            const progress = Math.min(100, Math.max(0, data.state.progress));
            console.log(`Updating progress bar: ${progress}%`);
            simulationProgress.style.width = `${progress}%`;
            simulationProgress.setAttribute('aria-valuenow', progress);
            simulationProgress.textContent = `${Math.round(progress)}%`;
            
            // 如果进度达到100%，也视为模拟结束
            if (progress >= 100) {
                simulation.running = false;
                // 只有在未通知过的情况下才显示提示
                if (!simulation.notifiedCompletion) {
                    showNotification('模拟已完成', 'success');
                    simulation.notifiedCompletion = true; // 标记已通知
                }
                return; // 模拟已完成，不再更新图表
            }
        }
        
        // 只有在模拟运行中才更新图表数据
        if (simulation.running) {
            // Update metrics
            if (data.state.metrics) {
                updateMetrics(data.state.metrics);
                
                // Add data point to chart
                if (data.state.timestamp) {
                    addMetricsDataPoint(data.state.timestamp, data.state.metrics);
                }
            }
            
            // Update other UI elements with state data
            updateUIWithStateData(data.state);
        }
        
    } catch (error) {
        console.error('Error updating simulation status:', error);
    }
}

// Update UI with state data
function updateUIWithStateData(state) {
    // Update agent decisions if available
    if (state.agent_decisions && multiAgentSwitch.checked) {
        updateAgentMetrics(state.agent_decisions);
    }
    
    // 首先更新充电桩数据，以便用户连接线可以找到正确的充电桩位置
    if (state.chargers && state.chargers.length > 0) {
        updateChargerHeatmap(state.chargers);
        // 更新地图视图中的充电桩
        updateMapWithChargers(state.chargers);
    }
    
    // 然后更新用户数据
    if (state.users && state.users.length > 0) {
        updateUserWaitTimeDistribution(state.users);
        // 更新地图视图中的用户
        updateMapWithUsers(state.users);
    }
    
    // 如果有结果数据，清除地图的默认提示信息
    if ((state.users && state.users.length > 0) || (state.chargers && state.chargers.length > 0)) {
        showMapContent();
    }

    // Update metrics (assuming 'metrics' key holds reward values)
    if (state.metrics) {
        updateMetrics(state.metrics);
    }

    // 处理电网数据 - 调整为符合charts.js中updateGridLoadChart的格式
    if (state.grid_status) {
        console.log("updateUIWithStateData: Received grid_status:", JSON.stringify(state.grid_status));
        
        // 直接传递grid_status对象给updateGridLoadChart函数
        updateGridLoadChart(state.grid_status);
        
        // 更新实时负载指标显示
        const totalLoadElement = document.getElementById('totalLoad');
        const evLoadElement = document.getElementById('evLoad');
        const renewableRatioElement = document.getElementById('renewableRatio');

        if (totalLoadElement) {
            // 使用current_load代替grid_load，current_load是实际的kW负载值
            totalLoadElement.textContent = `${(state.grid_status.current_load || 0).toFixed(1)} kW`;
        }
        if (evLoadElement) {
            evLoadElement.textContent = `${(state.grid_status.ev_load || 0).toFixed(1)} kW`;
        }
        if (renewableRatioElement) {
            renewableRatioElement.textContent = `${(state.grid_status.renewable_ratio || 0).toFixed(1)}%`;
        }
    }

    // Update agent decision panel if multi-agent is active and data available
    if (isMultiAgent && state.agent_decisions) {
        // ... existing code ...
    }
}

// 显示地图内容，移除默认提示信息
function showMapContent() {
    const mapContainer = document.getElementById('map-container');
    if (!mapContainer) return;
    
    // 清除默认提示信息
    const defaultMessage = mapContainer.querySelector('.bg-light');
    if (defaultMessage) {
        defaultMessage.style.display = 'none';
    }
    
    // 确保地图容器有内容
    if (!mapContainer.querySelector('#actual-map')) {
        const mapDiv = document.createElement('div');
        mapDiv.id = 'actual-map';
        mapDiv.style.position = 'relative';
        mapDiv.style.height = '100%';
        mapDiv.style.width = '100%';
        mapDiv.style.backgroundColor = '#f1f5f9';
        mapDiv.style.border = '1px solid #dee2e6';
        mapDiv.style.borderRadius = '8px';
        mapDiv.style.overflow = 'hidden';
        mapDiv.style.boxShadow = 'inset 0 0 20px rgba(0,0,0,0.1)';
        
        // 添加网格背景使地图更有层次感
        mapDiv.style.backgroundImage = 'linear-gradient(rgba(130, 130, 130, 0.1) 1px, transparent 1px), linear-gradient(90deg, rgba(130, 130, 130, 0.1) 1px, transparent 1px)';
        mapDiv.style.backgroundSize = '20px 20px';
        
        // 添加城市背景
        const cityBackground = document.createElement('div');
        cityBackground.className = 'city-background';
        cityBackground.style.position = 'absolute';
        cityBackground.style.top = '0';
        cityBackground.style.left = '0';
        cityBackground.style.width = '100%';
        cityBackground.style.height = '100%';
        cityBackground.style.zIndex = '1';
        cityBackground.style.opacity = '0.2';
        cityBackground.style.backgroundImage = "url('https://cdn.jsdelivr.net/gh/devicons/devicon/icons/javascript/javascript-original.svg')";
        cityBackground.style.backgroundSize = 'cover';
        cityBackground.style.backgroundPositionCenter = 'center';
        cityBackground.style.filter = 'grayscale(100%)';
        mapDiv.appendChild(cityBackground);
        
        // 添加地图控制面板
        const mapControls = document.createElement('div');
        mapControls.className = 'map-controls position-absolute top-0 start-0 m-2 p-2 bg-white rounded shadow d-flex flex-column gap-2';
        mapControls.style.zIndex = '50';
        mapControls.innerHTML = `
            <div class="form-check form-switch">
                <input class="form-check-input" type="checkbox" id="show-all-entities" checked>
                <label class="form-check-label" for="show-all-entities">显示全部实体</label>
            </div>
            <div class="btn-group btn-group-sm">
                <button id="zoom-in-btn" class="btn btn-outline-secondary"><i class="fas fa-search-plus"></i></button>
                <button id="zoom-out-btn" class="btn btn-outline-secondary"><i class="fas fa-search-minus"></i></button>
                <button id="reset-view-btn" class="btn btn-outline-secondary"><i class="fas fa-home"></i></button>
            </div>
        `;
        mapDiv.appendChild(mapControls);
        
        // 添加地图图例
        const legend = document.createElement('div');
        legend.className = 'map-legend position-absolute bottom-0 start-0 m-2 p-2 bg-white rounded shadow';
        legend.style.zIndex = '20';
        legend.style.maxWidth = '90%';
        legend.style.display = 'flex';
        legend.style.flexWrap = 'wrap';
        legend.style.gap = '8px';
        legend.style.alignItems = 'center';
        legend.innerHTML = `
            <div class="d-flex align-items-center">
                <div class="map-user-icon user-idle me-2" style="position:relative; width:24px; height:24px; transform:none; display:inline-flex;">
                    <i class="fas fa-car fa-xs"></i>
                </div>
                <span class="small">用户-空闲</span>
            </div>
            <div class="d-flex align-items-center">
                <div class="map-user-icon user-waiting me-2" style="position:relative; width:24px; height:24px; transform:none; display:inline-flex;">
                    <i class="fas fa-clock fa-xs"></i>
                </div>
                <span class="small">用户-等待</span>
            </div>
            <div class="d-flex align-items-center">
                <div class="map-user-icon user-charging me-2" style="position:relative; width:24px; height:24px; transform:none; display:inline-flex;">
                    <i class="fas fa-car fa-xs"></i>
                </div>
                <span class="small">用户-充电</span>
            </div>
            <div class="d-flex align-items-center">
                <div class="map-charger-icon charger-available me-2" style="position:relative; width:24px; height:24px; transform:none; display:inline-flex;">
                    <i class="fas fa-charging-station fa-xs"></i>
                </div>
                <span class="small">充电桩-可用</span>
            </div>
            <div class="d-flex align-items-center">
                <div class="map-charger-icon charger-occupied me-2" style="position:relative; width:24px; height:24px; transform:none; display:inline-flex;">
                    <i class="fas fa-bolt fa-xs"></i>
                </div>
                <span class="small">充电桩-占用</span>
            </div>
            <div class="d-flex align-items-center">
                <div class="map-charger-icon charger-failure me-2" style="position:relative; width:24px; height:24px; transform:none; display:inline-flex;">
                    <i class="fas fa-exclamation-triangle fa-xs"></i>
                </div>
                <span class="small">充电桩-故障</span>
            </div>
        `;
        mapDiv.appendChild(legend);
        
        mapContainer.appendChild(mapDiv);
        
        // 添加事件监听器
        const showAllEntitiesCheckbox = document.getElementById('show-all-entities');
        showAllEntitiesCheckbox.addEventListener('change', function() {
            updateMapVisibility(this.checked);
        });
        
        // 缩放按钮和重置视图
        document.getElementById('zoom-in-btn').addEventListener('click', function() {
            zoomMap(1.2);
        });
        
        document.getElementById('zoom-out-btn').addEventListener('click', function() {
            zoomMap(0.8);
        });
        
        document.getElementById('reset-view-btn').addEventListener('click', function() {
            resetMapView();
        });
    }
}

// 更新地图中的用户位置
function updateMapWithUsers(users) {
    console.log("Updating map with users:", users.length);
    const mapContainer = document.getElementById('map-container');
    if (!mapContainer) return;
    
    // 清除所有地图提示框
    clearAllMapTooltips();
    
    // 确保地图容器已创建并清除默认文本
    showMapContent();
    
    const mapDiv = document.getElementById('actual-map');
    if (!mapDiv) return;
    
    // 获取是否显示所有实体
    const showAllEntities = document.getElementById('show-all-entities')?.checked ?? true;
    
    // 创建或获取用户图层
    let usersLayer = mapDiv.querySelector('.users-layer');
    if (!usersLayer) {
        usersLayer = document.createElement('div');
        usersLayer.className = 'users-layer position-absolute';
        usersLayer.style.top = '0';
        usersLayer.style.left = '0';
        usersLayer.style.width = '100%';
        usersLayer.style.height = '100%';
        usersLayer.style.pointerEvents = 'none';
        usersLayer.style.zIndex = '10';
        mapDiv.appendChild(usersLayer);
    }
    
    // 清空现有用户图标
    usersLayer.innerHTML = '';
    
    // 确保有用户数据
    if (!users || users.length === 0) {
        console.warn("No users data to display on map");
        return;
    }
    
    // 根据是否显示所有实体选择用户数量
    const displayUsers = showAllEntities ? users : users.slice(0, 15);
    
    // 如果没有显示所有实体，则显示限制标题
    const limitNotice = mapDiv.querySelector('.display-limit-notice');
    if (limitNotice) {
        limitNotice.style.display = showAllEntities ? 'none' : 'block';
    } else if (!showAllEntities) {
        const displayLimitText = document.createElement('div');
        displayLimitText.className = 'display-limit-notice position-absolute top-0 start-50 translate-middle-x mt-2 p-1 bg-white rounded shadow small';
        displayLimitText.style.zIndex = '30';
        displayLimitText.innerHTML = '为展示清晰，仅显示部分用户和充电桩';
        mapDiv.appendChild(displayLimitText);
    }
    
    // 计算地图边界坐标
    const validPositions = users
        .filter(u => u.current_position && u.current_position.lat && u.current_position.lng)
        .map(u => u.current_position);
        
    if (validPositions.length === 0) {
        console.warn("No valid user positions found");
        return;
    }
    
    const minLat = Math.min(...validPositions.map(p => p.lat));
    const maxLat = Math.max(...validPositions.map(p => p.lat));
    const minLng = Math.min(...validPositions.map(p => p.lng));
    const maxLng = Math.max(...validPositions.map(p => p.lng));
    
    // 确保地图边界是有效的
    if (isNaN(minLat) || isNaN(maxLat) || isNaN(minLng) || isNaN(maxLng)) {
        console.error("Invalid map boundaries calculated:", { minLat, maxLat, minLng, maxLng });
        return;
    }
    
    // 创建充电桩位置映射
    const chargerPositions = {};
    const chargerElements = mapDiv.querySelectorAll('.charger-icon');
    chargerElements.forEach(chargerEl => {
        const chargerId = chargerEl.getAttribute('data-charger-id');
        if (chargerId) {
            chargerPositions[chargerId] = {
                x: parseFloat(chargerEl.style.left),
                y: parseFloat(chargerEl.style.top)
            };
        }
    });
    
    console.log(`Displaying ${displayUsers.length} users on map`);
    
    // 在地图上显示用户
    displayUsers.forEach(user => {
        if (!user.current_position || !user.current_position.lat || !user.current_position.lng) {
            console.warn("User has invalid position:", user.user_id);
            return;
        }
        
        // 将地理坐标转换为地图上的像素坐标
        let x = ((user.current_position.lng - minLng) / (maxLng - minLng)) * 100;
        let y = ((user.current_position.lat - minLat) / (maxLat - minLat)) * 100;
        
        // 添加微小的随机偏移量以减少图标重叠 (视觉效果，不影响实际位置)
        const mapWidth = mapDiv.offsetWidth; // 获取地图容器宽度
        const mapHeight = mapDiv.offsetHeight; // 获取地图容器高度
        const iconSizeApproxPx = 30; // 图标大致尺寸（像素）
        
        // 计算偏移量占容器百分比，目标是偏移大约半个图标的像素值
        const xOffsetPercent = (Math.random() - 0.5) * (iconSizeApproxPx / mapWidth * 100) * 0.8;
        const yOffsetPercent = (Math.random() - 0.5) * (iconSizeApproxPx / mapHeight * 100) * 0.8;
        
        x += xOffsetPercent;
        y += yOffsetPercent;
        
        // 确保偏移后仍在边界内 (稍微扩展一点点边界)
        x = Math.max(0.5, Math.min(99.5, x));
        y = Math.max(0.5, Math.min(99.5, y));

        if (isNaN(x) || isNaN(y)) {
            console.warn("Invalid user position calculated:", { x, y, user: user.user_id });
            return;
        }
        
        // 如果用户有路径，绘制路径线和路径点
        if (user.route && user.route.length > 1 && user.status === 'traveling') {
            // 转换所有路径点坐标
            const routePoints = user.route.map(point => {
                return {
                    x: ((point.lng - minLng) / (maxLng - minLng)) * 100,
                    y: ((point.lat - minLat) / (maxLat - minLat)) * 100
                };
            });
            
            // 确定线条样式类
            const isSelected = user.user_id === selectedUserId;
            const pathLineClass = isSelected ? 'path-line-selected' : 'path-line';
            
            // 绘制路径线段
            for (let i = 0; i < routePoints.length - 1; i++) {
                const p1 = routePoints[i];
                const p2 = routePoints[i + 1];
                
                // 计算线段长度和角度
                const dx = p2.x - p1.x;
                const dy = p2.y - p1.y;
                const length = Math.sqrt(dx * dx + dy * dy);
                const angle = Math.atan2(dy, dx) * 180 / Math.PI;
                
                // 创建路径线段
                const pathSegment = document.createElement('div');
                pathSegment.className = `${pathLineClass} position-absolute`;
                pathSegment.style.height = isSelected ? '3px' : '1.5px';
                pathSegment.setAttribute('data-user-id', user.user_id);
                
                // 设置线段位置和变换
                pathSegment.style.width = `${length}%`;
                pathSegment.style.left = `${p1.x}%`;
                pathSegment.style.top = `${p1.y}%`;
                pathSegment.style.transformOrigin = '0 0';
                pathSegment.style.transform = `rotate(${angle}deg)`;
                
                usersLayer.appendChild(pathSegment);
                
                // 如果是中间路径点，添加路径点标记
                if (i > 0 && i < routePoints.length - 1) {
                    const waypoint = document.createElement('div');
                    waypoint.className = 'waypoint position-absolute';
                    waypoint.style.width = isSelected ? '8px' : '6px';
                    waypoint.style.height = isSelected ? '8px' : '6px';
                    waypoint.style.borderRadius = '50%';
                    waypoint.style.backgroundColor = isSelected ? 'rgba(30, 144, 255, 0.8)' : 'rgba(173, 216, 230, 0.6)';
                    waypoint.style.transform = 'translate(-50%, -50%)';
                    waypoint.style.left = `${p1.x}%`;
                    waypoint.style.top = `${p1.y}%`;
                    waypoint.style.zIndex = isSelected ? '5' : '4';
                    
                    usersLayer.appendChild(waypoint);
                }
            }
        }
        
        // 创建用户图标 - 使用新的用户图标样式
        const userIcon = document.createElement('div');
        userIcon.className = 'map-user-icon position-absolute';
        userIcon.setAttribute('data-user-id', user.user_id);
        userIcon.style.left = `${x}%`;
        userIcon.style.top = `${y}%`;
        userIcon.style.transform = 'translate(-50%, -50%)';
        userIcon.style.pointerEvents = 'auto'; // 允许鼠标事件
        
        // 如果是选中的用户，添加边框
        if (user.user_id === selectedUserId) {
            userIcon.style.border = '2px solid #1e90ff';
            userIcon.style.boxShadow = '0 0 10px rgba(30, 144, 255, 0.8)';
        }
        
        // 根据用户状态设置图标类和图标
        let userClass = 'user-idle';  // 默认状态
        let icon = 'fa-car';          // 默认图标
        
        if (user.status === 'charging') {
            userClass = 'user-charging';
            // 闪电图标会通过CSS伪元素自动添加
        } else if (user.status === 'waiting') {
            userClass = 'user-waiting';
            icon = 'fa-clock';
        } else if (user.status === 'traveling') {
            userClass = 'user-driving';
            icon = 'fa-car';
        }
        
        userIcon.classList.add(userClass);
        userIcon.innerHTML = `<i class="fas ${icon} fa-sm"></i>`;
        
        // 使用Tippy.js创建提示框
        const userTemplate = document.createElement('div');
        userTemplate.className = 'map-tooltip';
        userTemplate.innerHTML = `
            <div class="map-tooltip-header">用户 ${user.user_id.split('_')[1] || user.user_id}</div>
            <div class="map-tooltip-content">
                <div><strong>状态:</strong> <span class="map-tooltip-status ${getStatusClass(user.status)}">${getStatusText(user.status)}</span></div>
                <div><strong>电量:</strong> ${user.soc ? user.soc.toFixed(1) : '未知'}%</div>
                
                <div class="map-tooltip-section">
                    <div class="map-tooltip-section-title">用户信息</div>
                    <div><strong>用户类型:</strong> ${user.user_type || '普通用户'}</div>
                    <div><strong>偏好类型:</strong> ${user.preference_type || '标准'}</div>
                    <div><strong>优先级:</strong> ${user.priority || '普通'}</div>
                    <div><strong>活跃度:</strong> ${user.activity_level || '中等'}</div>
                </div>

                <div class="map-tooltip-section">
                    <div class="map-tooltip-section-title">车辆信息</div>
                    <div><strong>车型:</strong> ${user.vehicle_type || '标准电动车'}</div>
                    <div><strong>电池容量:</strong> ${user.battery_capacity ? user.battery_capacity + ' kWh' : '未知'}</div>
                    <div><strong>充电效率:</strong> ${user.charging_efficiency ? (user.charging_efficiency * 100).toFixed(1) + '%' : '未知'}</div>
                    <div><strong>最大充电功率:</strong> ${user.max_charging_power ? user.max_charging_power.toFixed(1) + ' kW' : '未知'}</div>
                </div>

                ${user.destination || user.target_charger || user.target_location || user.arrival_time || user.distance_to_target ? `
                <div class="map-tooltip-section">
                    <div class="map-tooltip-section-title">行程信息</div>
                    ${user.destination ? `<div><strong>目的地:</strong> ${user.destination}</div>` : ''}
                    ${user.target_charger ? `<div><strong>目标充电桩:</strong> ${user.target_charger.split('_')[1] || user.target_charger}</div>` : ''}
                    ${user.target_location ? `<div><strong>目标区域:</strong> ${user.target_location}</div>` : ''}
                    ${user.arrival_time ? `<div><strong>预计到达:</strong> ${formatSimpleTime(user.arrival_time)}</div>` : ''}
                    ${user.distance_to_target ? `<div><strong>剩余距离:</strong> ${user.distance_to_target.toFixed(1)} 公里</div>` : ''}
                </div>
                ` : ''}

                ${user.status === 'waiting' || user.status === 'charging' ? `
                <div class="map-tooltip-section">
                    <div class="map-tooltip-section-title">充电信息</div>
                    ${user.wait_time ? `<div><strong>等待时间:</strong> ${formatDuration(user.wait_time)}</div>` : ''}
                    ${user.charging_start_time ? `<div><strong>开始充电:</strong> ${formatSimpleTime(user.charging_start_time)}</div>` : ''}
                    ${user.charging_end_time ? `<div><strong>预计结束:</strong> ${formatSimpleTime(user.charging_end_time)}</div>` : ''}
                    ${user.required_energy !== undefined ? `<div><strong>需要电量:</strong> ${user.required_energy.toFixed(1)} kWh</div>` : ''}
                    ${user.charging_power !== undefined ? `<div><strong>当前充电功率:</strong> ${user.charging_power.toFixed(1)} kW</div>` : ''}
                    ${user.current_charger ? `<div><strong>当前充电桩:</strong> ${user.current_charger.split('_')[1] || user.current_charger}</div>` : ''}
                    ${user.queue_position !== undefined ? `<div><strong>队列位置:</strong> 第 ${user.queue_position + 1} 位</div>` : ''}
                    ${user.target_soc !== undefined ? `<div><strong>目标电量:</strong> ${user.target_soc.toFixed(1)}%</div>` : ''}
                    ${user.remaining_time !== undefined ? `<div><strong>剩余时间:</strong> ${formatDuration(user.remaining_time)}</div>` : ''}
                    ${user.charging_mode ? `<div><strong>充电模式:</strong> ${user.charging_mode === 'fast' ? '快充' : '慢充'}</div>` : ''}
                </div>
                ` : ''}

                ${user.cost !== undefined || user.estimated_total_cost !== undefined || user.price_per_kwh !== undefined || user.service_fee !== undefined ? `
                <div class="map-tooltip-section">
                    <div class="map-tooltip-section-title">费用信息</div>
                    ${user.cost !== undefined ? `<div><strong>当前费用:</strong> ¥${user.cost.toFixed(2)}</div>` : ''}
                    ${user.estimated_total_cost !== undefined ? `<div><strong>预计总费用:</strong> ¥${user.estimated_total_cost.toFixed(2)}</div>` : ''}
                    ${user.price_per_kwh !== undefined ? `<div><strong>电价:</strong> ¥${user.price_per_kwh.toFixed(2)}/kWh</div>` : ''}
                    ${user.service_fee !== undefined ? `<div><strong>服务费:</strong> ¥${user.service_fee.toFixed(2)}</div>` : ''}
                    ${user.total_cost !== undefined ? `<div><strong>累计费用:</strong> ¥${user.total_cost.toFixed(2)}</div>` : ''}
                </div>
                ` : ''}
            </div>
        `;
        
        // 保存提示框实例
        const tooltip = tippy(userIcon, {
            content: userTemplate,
            arrow: true,
            theme: 'light',
            placement: 'top',
            duration: [300, 200],
            animation: 'shift-away',
            interactive: true,
            allowHTML: true,
            maxWidth: 320,
            trigger: 'mouseenter focus',
            appendTo: document.body
        });
        
        allMapTooltips.push(tooltip);
        
        // 添加点击事件 - 选择/取消选择用户
        userIcon.addEventListener('click', function(e) {
            e.stopPropagation(); // 防止事件冒泡
            
            if (selectedUserId === user.user_id) {
                // 取消选择
                selectedUserId = null;
            } else {
                // 选择新用户
                selectedUserId = user.user_id;
            }
            
            // 重新绘制地图以更新显示
            updateMapWithUsers(users);
        });
        
        usersLayer.appendChild(userIcon);
    });
    
    // 更新地图视图的用户数据计数
    updateMapStatistics('users', users.length, displayUsers.length);
    
    // 检查鼠标位置以更新悬停提示框
    checkMousePositionForTooltips();
}

// 更新地图中的充电桩位置
function updateMapWithChargers(chargers) {
    const mapContainer = document.getElementById('map-container');
    if (!mapContainer) return;
    
    // 清除所有地图提示框
    clearAllMapTooltips();
    
    // 确保地图容器已创建
    showMapContent();
    
    const mapDiv = document.getElementById('actual-map');
    if (!mapDiv) return;
    
    // 获取是否显示所有实体
    const showAllEntities = document.getElementById('show-all-entities')?.checked ?? true;
    
    // 创建或获取充电桩图层
    let chargersLayer = mapDiv.querySelector('.chargers-layer');
    if (!chargersLayer) {
        chargersLayer = document.createElement('div');
        chargersLayer.className = 'chargers-layer position-absolute';
        chargersLayer.style.top = '0';
        chargersLayer.style.left = '0';
        chargersLayer.style.width = '100%';
        chargersLayer.style.height = '100%';
        chargersLayer.style.pointerEvents = 'none';
        chargersLayer.style.zIndex = '9';
        mapDiv.appendChild(chargersLayer);
    }
    
    // 清空现有充电桩图标
    chargersLayer.innerHTML = '';
    
    // 根据是否显示所有实体选择充电桩数量
    const displayChargers = showAllEntities ? chargers : chargers.slice(0, 20);
    
    // 计算地图边界坐标
    const positions = chargers.map(c => c.position).filter(Boolean);
    if (positions.length === 0) {
        console.warn('updateMapWithChargers: No valid chargers data');
        return;
    }
    
    const minLat = Math.min(...positions.map(p => p.lat || 30.5));
    const maxLat = Math.max(...positions.map(p => p.lat || 31.0));
    const minLng = Math.min(...positions.map(p => p.lng || 114.0));
    const maxLng = Math.max(...positions.map(p => p.lng || 114.5));
    
    // 收集地点信息
    const locations = {};
    displayChargers.forEach(charger => {
        if (charger?.location && charger?.position) {
            if (!locations[charger.location]) {
                locations[charger.location] = {
                    name: charger.location,
                    lat: charger.position.lat,
                    lng: charger.position.lng,
                    count: 0
                };
            }
            locations[charger.location].count++;
            
            // 略微调整位置中心计算
            locations[charger.location].lat = (locations[charger.location].lat * (locations[charger.location].count - 1) + charger.position.lat) / locations[charger.location].count;
            locations[charger.location].lng = (locations[charger.location].lng * (locations[charger.location].count - 1) + charger.position.lng) / locations[charger.location].count;
        }
    });
    
    // 添加筛选按钮
    let filterGroup = mapDiv.querySelector('.location-filter');
    if (!filterGroup) {
        filterGroup = document.createElement('div');
        filterGroup.className = 'location-filter position-absolute top-0 end-0 m-3 bg-white p-2 rounded shadow';
        filterGroup.style.zIndex = '20';
        
        // 添加全部按钮
        const allButton = document.createElement('button');
        allButton.className = 'btn btn-sm btn-outline-primary active me-1 mb-1';
        allButton.textContent = '全部';
        allButton.onclick = () => filterByLocation('all');
        filterGroup.appendChild(allButton);
    
    // 为每个地点添加筛选按钮
        Object.keys(locations).forEach(location => {
        const button = document.createElement('button');
            button.className = 'btn btn-sm btn-outline-secondary me-1 mb-1';
            button.textContent = location;
            button.setAttribute('data-location', location);
            button.onclick = () => filterByLocation(location);
        filterGroup.appendChild(button);
    });
        
        mapDiv.appendChild(filterGroup);
    }
    
    // 在地图上显示充电桩
    displayChargers.forEach(charger => {
        if (!charger.position) return;
        
        // 将地理坐标转换为地图上的像素坐标
        const x = ((charger.position.lng - minLng) / (maxLng - minLng)) * 100;
        const y = ((charger.position.lat - minLat) / (maxLat - minLat)) * 100;
        
        // 创建充电桩图标 - 使用新的充电桩图标样式
        const chargerIcon = document.createElement('div');
        chargerIcon.className = 'map-charger-icon position-absolute';
        
        // 确保charger_id存在再调用split
        if (charger.charger_id) {
            chargerIcon.setAttribute('data-charger-id', charger.charger_id);
        }
        
        if (charger.location) {
            chargerIcon.setAttribute('data-location', charger.location);
        }
        
        chargerIcon.style.left = `${x}%`;
        chargerIcon.style.top = `${y}%`;
        chargerIcon.style.transform = 'translate(-50%, -50%)';
        chargerIcon.style.pointerEvents = 'auto'; // 允许鼠标事件
        
        // 根据充电桩状态设置图标类和图标
        let chargerClass, icon;
        
        switch (charger.status) {
            case 'available':
                chargerClass = 'charger-available';
                icon = 'fa-charging-station';
                break;
            case 'occupied':
                chargerClass = 'charger-occupied';
                icon = 'fa-bolt';
                break;
            case 'failure':
                chargerClass = 'charger-failure'; 
                icon = 'fa-exclamation-triangle';
                break;
            default:
                chargerClass = '';
                icon = 'fa-charging-station';
        }
        
        chargerIcon.classList.add(chargerClass);
        
        // 如果是快充，添加快充标识
        if (charger.power_level && charger.power_level > 50) {
            chargerIcon.classList.add('fast-charger');
        }
        
        chargerIcon.innerHTML = `<i class="fas ${icon}"></i>`;
        
        // 如果有排队的用户，添加队列数量徽章
        if (charger.queue && charger.queue.length > 0) {
            const queueBadge = document.createElement('div');
            queueBadge.className = 'queue-badge';
            queueBadge.textContent = charger.queue.length;
            chargerIcon.appendChild(queueBadge);
        }
        
        // 使用Tippy.js创建提示框
        const chargerTemplate = document.createElement('div');
        chargerTemplate.className = 'map-tooltip';
        chargerTemplate.innerHTML = `
            <div class="map-tooltip-header">充电桩 ${charger.charger_id?.split('_')[1] || charger.charger_id || '未知'}</div>
            <div class="map-tooltip-content">
                <div><strong>状态:</strong> <span class="map-tooltip-status ${getChargerStatusClass(charger.status)}">${getChargerStatusText(charger.status)}</span></div>
                
                <div class="map-tooltip-section">
                    <div class="map-tooltip-section-title">基本信息</div>
                    <div><strong>位置:</strong> ${charger.location || '未知'}</div>
                    <div><strong>类型:</strong> ${charger.type === 'fast' ? '快速充电' : charger.type === 'slow' ? '慢速充电' : charger.type || '标准'}</div>
                    <div><strong>功率:</strong> ${charger.power_level || 0} kW</div>
                    <div><strong>运营商:</strong> ${charger.operator || '未知'}</div>
                </div>
                
                <div class="map-tooltip-section">
                    <div class="map-tooltip-section-title">使用情况</div>
                    <div><strong>队列:</strong> ${charger.queue ? charger.queue.length : 0} 人等待</div>
                    ${charger.current_user ? `<div><strong>当前使用者:</strong> 用户 ${charger.current_user.split('_')[1] || charger.current_user}</div>` : ''}
                    ${charger.utilization_rate !== undefined ? `<div><strong>利用率:</strong> ${charger.utilization_rate.toFixed(1)}%</div>` : ''}
                    ${charger.availability_rate !== undefined ? `<div><strong>可用率:</strong> ${charger.availability_rate.toFixed(1)}%</div>` : ''}
                </div>
                
                ${charger.status === 'occupied' ? `
                <div class="map-tooltip-section">
                    <div class="map-tooltip-section-title">当前充电信息</div>
                    ${charger.charging_start_time ? `<div><strong>开始时间:</strong> ${formatSimpleTime(charger.charging_start_time)}</div>` : ''}
                    ${charger.charging_end_time ? `<div><strong>预计结束:</strong> ${formatSimpleTime(charger.charging_end_time)}</div>` : ''}
                    ${charger.current_power ? `<div><strong>当前功率:</strong> ${charger.current_power.toFixed(1)} kW</div>` : ''}
                    ${charger.energy_delivered !== undefined ? `<div><strong>已输出电量:</strong> ${charger.energy_delivered.toFixed(1)} kWh</div>` : ''}
                </div>
                ` : ''}
                
                ${charger.status === 'failure' ? `
                <div class="map-tooltip-section">
                    <div class="map-tooltip-section-title">故障信息</div>
                    <div><strong>故障类型:</strong> ${charger.failure_type || '未知故障'}</div>
                    ${charger.failure_time ? `<div><strong>故障时间:</strong> ${formatSimpleTime(charger.failure_time)}</div>` : ''}
                    ${charger.estimated_repair_time ? `<div><strong>预计修复:</strong> ${formatSimpleTime(charger.estimated_repair_time)}</div>` : ''}
                </div>
                ` : ''}
                
                <div class="map-tooltip-section">
                    <div class="map-tooltip-section-title">经济数据</div>
                    ${charger.daily_revenue !== undefined ? `<div><strong>今日收入:</strong> ¥${charger.daily_revenue.toFixed(2)}</div>` : ''}
                    ${charger.price_per_kwh !== undefined ? `<div><strong>电价:</strong> ¥${charger.price_per_kwh.toFixed(2)}/kWh</div>` : ''}
                    ${charger.service_fee !== undefined ? `<div><strong>服务费:</strong> ¥${charger.service_fee.toFixed(2)}</div>` : ''}
                </div>
            </div>
        `;
        
        // 保存提示框实例
        const tooltip = tippy(chargerIcon, {
            content: chargerTemplate,
            arrow: true,
            theme: 'light',
            placement: 'top',
            duration: [300, 200],
            animation: 'shift-away',
            interactive: true,
            allowHTML: true,
            maxWidth: 320,
            trigger: 'mouseenter focus', 
            appendTo: document.body
        });
        
        allMapTooltips.push(tooltip);
        
        chargersLayer.appendChild(chargerIcon);
    });
    
    // 添加地点名称标签
    Object.values(locations).forEach(location => {
        const x = ((location.lng - minLng) / (maxLng - minLng)) * 100;
        const y = ((location.lat - minLat) / (maxLat - minLat)) * 100;
        
        const locationLabel = document.createElement('div');
        locationLabel.className = 'location-label position-absolute bg-dark text-white px-3 py-2 rounded-pill shadow text-center';
        locationLabel.style.left = `${x}%`;
        locationLabel.style.top = `${y - 5}%`;  // 稍微向上偏移
        locationLabel.style.transform = 'translate(-50%, -100%)';
        locationLabel.style.zIndex = '8';
        locationLabel.style.fontSize = '0.9rem';
        locationLabel.style.fontWeight = 'bold';
        locationLabel.textContent = `${location.name} (${location.count})`;
        
        // 添加闪亮图标
        const locationIcon = document.createElement('div');
        locationIcon.className = 'location-icon position-absolute';
        locationIcon.style.bottom = '-8px';
        locationIcon.style.left = '50%';
        locationIcon.style.transform = 'translateX(-50%)';
        locationIcon.style.color = '#fff';
        locationIcon.innerHTML = '<i class="fas fa-map-marker-alt"></i>';
        locationLabel.appendChild(locationIcon);
        
        chargersLayer.appendChild(locationLabel);
    });
    
    // 统计不同状态的充电桩数量
    const availableCount = chargers.filter(c => c.status === 'available').length;
    const occupiedCount = chargers.filter(c => c.status === 'occupied').length;
    const failureCount = chargers.filter(c => c.status === 'failure').length;
    
    // 更新地图视图的充电桩数据计数
    updateMapStatistics('chargers', chargers.length, {
        display: displayChargers.length,
        available: availableCount,
        occupied: occupiedCount,
        failure: failureCount
    });
    
    // 检查鼠标位置以更新悬停提示框
    checkMousePositionForTooltips();
}

// 根据用户状态获取CSS类
function getStatusClass(status) {
    switch (status) {
        case 'charging': return 'status-charging';
        case 'waiting': return 'status-waiting';
        case 'traveling': return 'status-idle';
        default: return 'status-idle';
    }
}

// 根据充电桩状态获取CSS类
function getChargerStatusClass(status) {
    switch (status) {
        case 'available': return 'status-charging';
        case 'occupied': return 'status-waiting';
        case 'failure': return 'status-failure';
        default: return 'status-idle';
    }
}

// 格式化时间为简单格式 HH:MM
function formatSimpleTime(dateStr) {
    if (!dateStr) return '';
    const date = new Date(dateStr);
    return `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`;
}

// 格式化时长
function formatDuration(minutes) {
    if (minutes < 60) {
        return `${minutes} 分钟`;
    } else {
        const hours = Math.floor(minutes / 60);
        const mins = minutes % 60;
        return `${hours} 小时 ${mins} 分钟`;
    }
}

// 初始化时添加鼠标跟踪
document.addEventListener('DOMContentLoaded', function() {
    // 其他初始化代码...
    
    // 初始化鼠标位置跟踪
    trackMousePosition();
});

// ... existing code ...

// 获取用户友好的状态文本
function getStatusText(status) {
    switch(status) {
        case 'charging': return '充电中';
        case 'waiting': return '等待中';
        case 'traveling': return '行驶中';
        case 'idle': return '空闲';
        default: return status;
    }
}

// 获取充电桩友好的状态文本
function getChargerStatusText(status) {
    switch(status) {
        case 'available': return '可用';
        case 'occupied': return '占用中';
        case 'failure': return '故障';
        default: return status;
    }
}

// 更新地图统计信息
function updateMapStatistics(type, count, details = null) {
    const mapContainer = document.getElementById('map-container');
    if (!mapContainer) return;
    
    const mapContent = mapContainer.querySelector('#actual-map');
    if (!mapContent) return;
    
    // 查找或创建统计信息容器
    let statsDiv = mapContent.querySelector('.map-statistics');
    if (!statsDiv) {
        statsDiv = document.createElement('div');
        statsDiv.className = 'map-statistics position-absolute bottom-0 end-0 m-3 p-2 bg-white rounded shadow';
        statsDiv.style.zIndex = '30';
        mapContent.appendChild(statsDiv);
    }
    
    // 更新统计信息
    if (type === 'users') {
        let userStats = statsDiv.querySelector('.user-stats');
        if (!userStats) {
            userStats = document.createElement('div');
            userStats.className = 'user-stats mb-2';
            statsDiv.appendChild(userStats);
        }
        
        // 第二个参数可能是显示的用户数
        const displayCount = typeof details === 'number' ? details : count;
        userStats.innerHTML = `
            <div class="d-flex align-items-center mb-1">
                <div class="map-user-icon user-idle me-2" style="position:relative; width:24px; height:24px; transform:none; display:inline-flex;">
                    <i class="fas fa-car fa-xs"></i>
                </div>
                <div>
                    <div class="fw-bold">用户总数: <span class="ms-1">${count}</span></div>
                    <div class="small text-muted">显示: ${displayCount}/${count}</div>
                </div>
            </div>
        `;
    } else if (type === 'chargers') {
        let chargerStats = statsDiv.querySelector('.charger-stats');
        if (!chargerStats) {
            chargerStats = document.createElement('div');
            chargerStats.className = 'charger-stats';
            statsDiv.appendChild(chargerStats);
        }
        
        if (details) {
            const displayCount = details.display || count;
            chargerStats.innerHTML = `
                <div class="d-flex align-items-center mb-1">
                    <div class="map-charger-icon charger-available me-2" style="position:relative; width:24px; height:24px; transform:none; display:inline-flex;">
                        <i class="fas fa-charging-station fa-xs"></i>
                    </div>
                    <div>
                        <div class="fw-bold">充电桩总数: <span class="ms-1">${count}</span></div>
                        <div class="small text-muted">显示: ${displayCount}/${count}</div>
                    </div>
                </div>
                <div class="d-flex justify-content-between mt-1 small">
                    <span class="badge bg-success me-1">可用: ${details.available}</span>
                    <span class="badge bg-warning me-1">占用: ${details.occupied}</span>
                    <span class="badge bg-danger">故障: ${details.failure}</span>
                </div>
            `;
        } else {
            chargerStats.innerHTML = `
                <div class="d-flex align-items-center">
                    <div class="map-charger-icon charger-available me-2" style="position:relative; width:24px; height:24px; transform:none; display:inline-flex;">
                        <i class="fas fa-charging-station fa-xs"></i>
                    </div>
                    <div class="fw-bold">充电桩总数: <span class="ms-1">${count}</span></div>
                </div>
            `;
        }
    }
}

// 地图位置筛选功能
function filterByLocation(location) {
    const mapDiv = document.getElementById('actual-map');
    if (!mapDiv) return;
    
    // 更新筛选按钮状态
    const filterButtons = mapDiv.querySelectorAll('.location-filter button');
    filterButtons.forEach(button => {
        if ((button.getAttribute('data-location') === location) || 
            (button.textContent === '全部' && location === 'all')) {
            button.className = 'btn btn-sm btn-primary mb-1';
        } else {
            button.className = 'btn btn-sm btn-outline-secondary mb-1';
        }
    });
    
    // 筛选充电桩图标
    const chargerIcons = mapDiv.querySelectorAll('.charger-icon');
    chargerIcons.forEach(icon => {
        if (location === 'all' || icon.getAttribute('data-location') === location) {
            icon.style.display = 'flex';
            icon.style.animation = icon.style.animation.replace('none', '');
        } else {
            icon.style.display = 'none';
            // 保存原来的动画
            if (icon.style.animation && icon.style.animation !== 'none') {
                icon._savedAnimation = icon.style.animation;
                icon.style.animation = 'none';
            }
        }
    });
    
    // 筛选地点标签
    const locationLabels = mapDiv.querySelectorAll('.location-label');
    locationLabels.forEach(label => {
        const labelText = label.textContent;
        const labelLocation = labelText.split(' (')[0];
        if (location === 'all' || labelLocation === location) {
            label.style.display = 'block';
        } else {
            label.style.display = 'none';
        }
    });
    
    // 根据显示的充电桩筛选用户路线
    const userLines = mapDiv.querySelectorAll('.connection-line');
    userLines.forEach(line => {
        // 临时做法: 根据显示的充电桩决定是否显示连接线
        if (location === 'all') {
            line.style.display = 'block';
        } else {
            // 简单方法, 当筛选器激活时隐藏所有线条
            line.style.display = 'none';
        }
    });
}

// 更新地图可见性（显示/隐藏所有实体）
function updateMapVisibility(showAll) {
    console.log("Updating map visibility, showAll:", showAll);
    const mapDiv = document.getElementById('actual-map');
    if (!mapDiv) return;
    
    // 获取用户和充电桩数据
    let users = [];
    let chargers = [];
    
    if (simulation.running) {
        // 如果模拟正在运行，尝试从最新状态获取数据
        fetch('/api/simulation/status')
            .then(response => response.json())
            .then(data => {
                if (data.state) {
                    users = data.state.users || [];
                    chargers = data.state.chargers || [];
                    
                    // 更新地图
                    updateMapWithUsers(users);
                    updateMapWithChargers(chargers);
                    
                    // 更新显示限制提示
                    const limitNotice = mapDiv.querySelector('.display-limit-notice');
                    if (limitNotice) {
                        limitNotice.style.display = showAll ? 'none' : 'block';
                    }
                }
            })
            .catch(error => {
                console.error('Error updating map visibility:', error);
            });
    } else {
        // 如果模拟未运行，只更新显示状态
        const usersLayer = mapDiv.querySelector('.users-layer');
        const chargersLayer = mapDiv.querySelector('.chargers-layer');
        
        if (usersLayer) {
            const userIcons = usersLayer.querySelectorAll('.user-icon');
            userIcons.forEach((icon, index) => {
                icon.style.display = showAll || index < 15 ? 'flex' : 'none';
            });
        }
        
        if (chargersLayer) {
            const chargerIcons = chargersLayer.querySelectorAll('.charger-icon');
            chargerIcons.forEach((icon, index) => {
                icon.style.display = showAll || index < 20 ? 'flex' : 'none';
            });
        }
        
        // 更新显示限制提示
        const limitNotice = mapDiv.querySelector('.display-limit-notice');
        if (limitNotice) {
            limitNotice.style.display = showAll ? 'none' : 'block';
        } else if (!showAll) {
            const displayLimitText = document.createElement('div');
            displayLimitText.className = 'display-limit-notice position-absolute top-0 start-50 translate-middle-x mt-2 p-1 bg-white rounded shadow small';
            displayLimitText.style.zIndex = '30';
            displayLimitText.innerHTML = '为展示清晰，仅显示部分用户和充电桩';
            mapDiv.appendChild(displayLimitText);
        }
    }
}

// 缩放地图
function zoomMap(factor) {
    const mapDiv = document.getElementById('actual-map');
    if (!mapDiv) return;
    
    // 获取当前缩放级别
    const currentScale = parseFloat(mapDiv.getAttribute('data-scale') || '1');
    const newScale = currentScale * factor;
    
    // 限制缩放范围
    const scale = Math.max(0.5, Math.min(2, newScale));
    
    // 更新缩放属性
    mapDiv.setAttribute('data-scale', scale);
    
    // 应用缩放
    const usersLayer = mapDiv.querySelector('.users-layer');
    const chargersLayer = mapDiv.querySelector('.chargers-layer');
    
    if (usersLayer) usersLayer.style.transform = `scale(${scale})`;
    if (chargersLayer) chargersLayer.style.transform = `scale(${scale})`;
    
    // 更新原点以确保缩放围绕中心点
    if (usersLayer) usersLayer.style.transformOrigin = 'center center';
    if (chargersLayer) chargersLayer.style.transformOrigin = 'center center';
}

// 重置地图视图
function resetMapView() {
    const mapDiv = document.getElementById('actual-map');
    if (!mapDiv) return;
    
    // 重置缩放
    mapDiv.setAttribute('data-scale', '1');
    
    const usersLayer = mapDiv.querySelector('.users-layer');
    const chargersLayer = mapDiv.querySelector('.chargers-layer');
    
    if (usersLayer) {
        usersLayer.style.transform = 'scale(1)';
        usersLayer.style.transformOrigin = 'center center';
    }
    
    if (chargersLayer) {
        chargersLayer.style.transform = 'scale(1)';
        chargersLayer.style.transformOrigin = 'center center';
    }
    
    // 重置位置筛选
    filterByLocation('all');
    
    // 重置显示所有实体
    const showAllEntitiesCheckbox = document.getElementById('show-all-entities');
    if (showAllEntitiesCheckbox && !showAllEntitiesCheckbox.checked) {
        showAllEntitiesCheckbox.checked = true;
        updateMapVisibility(true);
    }
}

// Update metrics display
function updateMetrics(metrics) {
    if (!metrics) {
        console.warn('No metrics data provided to updateMetrics function');
        return;
    }
    
    console.log('Updating metrics with:', metrics);
    
    try {
        // Get previous values for trend calculation
        const prevUserValue = parseFloat(metricUser.textContent) || 0;
        const prevProfitValue = parseFloat(metricProfit.textContent) || 0;
        const prevGridValue = parseFloat(metricGrid.textContent) || 0;
        const prevTotalValue = parseFloat(metricTotal.textContent) || 0;
        
        // Format and update metric values
        const userValue = parseFloat(metrics.user_satisfaction) || 0;
        const profitValue = parseFloat(metrics.operator_profit) || 0;
        const gridValue = parseFloat(metrics.grid_friendliness) || 0;
        const totalValue = parseFloat(metrics.total_reward) || 0;
        
        // Update text display
        metricUser.textContent = userValue.toFixed(2);
        metricProfit.textContent = profitValue.toFixed(2);
        metricGrid.textContent = gridValue.toFixed(2);
        metricTotal.textContent = totalValue.toFixed(2);
        
        // Update overview values with animation
        animateValueUpdate(overviewUserSatisfaction, userValue.toFixed(2));
        animateValueUpdate(overviewOperatorProfit, profitValue.toFixed(2));
        animateValueUpdate(overviewGridFriendliness, gridValue.toFixed(2));
        animateValueUpdate(overviewTotalScore, totalValue.toFixed(2));
        
        // Update trend indicators
        updateTrend(userTrend, userValue, prevUserValue);
        updateTrend(profitTrend, profitValue, prevProfitValue);
        updateTrend(gridTrend, gridValue, prevGridValue);
        updateTrend(totalTrend, totalValue, prevTotalValue);
    } catch (error) {
        console.error('Error updating metrics display:', error);
    }
}

// Add metrics data to charts
function addMetricsDataPoint(timestamp, metrics) {
    if (!timestamp || !metrics) {
        console.warn('Missing data for metrics chart update');
        return;
    }
    
    try {
        const dateStr = typeof timestamp === 'string' ? timestamp : timestamp.toISOString();
        // 使用简化的时间格式
        const timeLabel = formatSimulationTime(dateStr);
        
        // Add to history arrays
        simulation.metricsHistory.timestamps.push(timeLabel);
        simulation.metricsHistory.userSatisfaction.push(parseFloat(metrics.user_satisfaction) || 0);
        simulation.metricsHistory.operatorProfit.push(parseFloat(metrics.operator_profit) || 0);
        simulation.metricsHistory.gridFriendliness.push(parseFloat(metrics.grid_friendliness) || 0);
        simulation.metricsHistory.totalReward.push(parseFloat(metrics.total_reward) || 0);
        
        // Keep last 24 hours of data (96 points at 15-min intervals)
        const maxPoints = 96;
        if (simulation.metricsHistory.timestamps.length > maxPoints) {
            simulation.metricsHistory.timestamps.shift();
            simulation.metricsHistory.userSatisfaction.shift();
            simulation.metricsHistory.operatorProfit.shift();
            simulation.metricsHistory.gridFriendliness.shift();
            simulation.metricsHistory.totalReward.shift();
        }
        
        // Update metrics chart
        if (metricsChart) {
            metricsChart.data.labels = simulation.metricsHistory.timestamps;
            metricsChart.data.datasets[0].data = simulation.metricsHistory.userSatisfaction;
            metricsChart.data.datasets[1].data = simulation.metricsHistory.operatorProfit;
            metricsChart.data.datasets[2].data = simulation.metricsHistory.gridFriendliness;
            metricsChart.data.datasets[3].data = simulation.metricsHistory.totalReward;
            metricsChart.update();
        }
    } catch (error) {
        console.error('Error adding metrics data point:', error);
    }
}

// Update agent metrics
function updateAgentMetrics(agentDecisions) {
    // Count decisions for each agent
    const userDecisions = Object.keys(agentDecisions.user_agent || {}).length;
    const profitDecisions = Object.keys(agentDecisions.profit_agent || {}).length;
    const gridDecisions = Object.keys(agentDecisions.grid_agent || {}).length;
    
    // Count conflicts
    let conflicts = 0;
    
    // For each user ID, check if agents have different decisions
    const allUserIds = new Set([
        ...Object.keys(agentDecisions.user_agent || {}),
        ...Object.keys(agentDecisions.profit_agent || {}),
        ...Object.keys(agentDecisions.grid_agent || {})
    ]);
    
    allUserIds.forEach(userId => {
        const decisions = new Set();
        if (agentDecisions.user_agent && agentDecisions.user_agent[userId]) {
            decisions.add(agentDecisions.user_agent[userId]);
        }
        if (agentDecisions.profit_agent && agentDecisions.profit_agent[userId]) {
            decisions.add(agentDecisions.profit_agent[userId]);
        }
        if (agentDecisions.grid_agent && agentDecisions.grid_agent[userId]) {
            decisions.add(agentDecisions.grid_agent[userId]);
        }
        
        if (decisions.size > 1) {
            conflicts++;
        }
    });
    
    // Update agent metrics
    simulation.agentMetrics.userDecisions += userDecisions;
    simulation.agentMetrics.profitDecisions += profitDecisions;
    simulation.agentMetrics.gridDecisions += gridDecisions;
    simulation.agentMetrics.conflicts.push(conflicts);
    
    // Update decision counts in UI
    userAgentDecisions.textContent = simulation.agentMetrics.userDecisions;
    profitAgentDecisions.textContent = simulation.agentMetrics.profitDecisions;
    gridAgentDecisions.textContent = simulation.agentMetrics.gridDecisions;
    
    // Calculate and update adoption rates
    const totalDecisions = simulation.agentMetrics.userDecisions + simulation.agentMetrics.profitDecisions + simulation.agentMetrics.gridDecisions;
    if (totalDecisions > 0) {
        userAgentAdoption.textContent = Math.round((simulation.agentMetrics.userDecisions / totalDecisions) * 100) + "%";
        profitAgentAdoption.textContent = Math.round((simulation.agentMetrics.profitDecisions / totalDecisions) * 100) + "%";
        gridAgentAdoption.textContent = Math.round((simulation.agentMetrics.gridDecisions / totalDecisions) * 100) + "%";
    }
    
    // Update agent rewards
    userAgentReward.textContent = (Math.random() * 0.3 + 0.5).toFixed(2); // Placeholder
    profitAgentReward.textContent = (Math.random() * 0.3 + 0.5).toFixed(2); // Placeholder
    gridAgentReward.textContent = (Math.random() * 0.3 + 0.5).toFixed(2); // Placeholder
    
    // Update charts
    updateAgentRewardsChart();
    updateConflictsChart();
}

// Update agent rewards chart
function updateAgentRewardsChart() {
    const timeLabels = simulation.metricsHistory.timestamps;
    
    // Generate some simulated reward values for now (these would come from the backend in a real system)
    const userRewards = simulation.metricsHistory.userSatisfaction.map(v => Math.min(1, Math.max(0, v * (1 + (Math.random() * 0.2 - 0.1)))));
    const profitRewards = simulation.metricsHistory.operatorProfit.map(v => Math.min(1, Math.max(0, v * (1 + (Math.random() * 0.2 - 0.1)))));
    const gridRewards = simulation.metricsHistory.gridFriendliness.map(v => Math.min(1, Math.max(0, ((v + 1) / 2) * (1 + (Math.random() * 0.2 - 0.1)))));
    
    agentRewardsChart.data.labels = timeLabels;
    agentRewardsChart.data.datasets[0].data = userRewards;
    agentRewardsChart.data.datasets[1].data = profitRewards;
    agentRewardsChart.data.datasets[2].data = gridRewards;
    agentRewardsChart.update();
}

// Update conflicts chart
function updateConflictsChart() {
    // Use the last 10 conflicts for visualization
    const timeLabels = simulation.metricsHistory.timestamps.slice(-simulation.agentMetrics.conflicts.length);
    
    conflictsChart.data.labels = timeLabels;
    conflictsChart.data.datasets[0].data = simulation.agentMetrics.conflicts;
    conflictsChart.update();
}

// Update user wait time distribution
function updateUserWaitTimeDistribution(users) {
    // Placeholder - in a real implementation, you would get actual wait times from the backend
    // Here we're simulating wait times based on user SOC (higher SOC, longer wait time)
    const waitTimeCounts = [0, 0, 0, 0, 0, 0]; // [0-5, 5-10, 10-15, 15-20, 20-30, >30]
    
    users.forEach(user => {
        // Simulate wait time based on SOC - higher SOC means less urgency, potentially longer waits
        let waitTimeMinutes;
        
        if (user.soc < 20) {
            waitTimeMinutes = Math.random() * 5; // 0-5 min
        } else if (user.soc < 40) {
            waitTimeMinutes = 5 + Math.random() * 5; // 5-10 min
        } else if (user.soc < 60) {
            waitTimeMinutes = 10 + Math.random() * 5; // 10-15 min
        } else if (user.soc < 80) {
            waitTimeMinutes = 15 + Math.random() * 5; // 15-20 min
        } else {
            waitTimeMinutes = 20 + Math.random() * 10; // 20-30 min
        }
        
        // Occasionally add some users with very long wait times
        if (Math.random() < 0.1) {
            waitTimeMinutes = 30 + Math.random() * 15; // >30 min
        }
        
        // Categorize wait time
        if (waitTimeMinutes <= 5) {
            waitTimeCounts[0]++;
        } else if (waitTimeMinutes <= 10) {
            waitTimeCounts[1]++;
        } else if (waitTimeMinutes <= 15) {
            waitTimeCounts[2]++;
        } else if (waitTimeMinutes <= 20) {
            waitTimeCounts[3]++;
        } else if (waitTimeMinutes <= 30) {
            waitTimeCounts[4]++;
        } else {
            waitTimeCounts[5]++;
        }
    });
    
    // Update chart
    userWaitTimeChart.data.datasets[0].data = waitTimeCounts;
    userWaitTimeChart.update();
}

// Update charger heatmap
function updateChargerHeatmap(chargers) {
    // 确保chargerHeatmap存在
    if (!chargerHeatmap) {
        console.warn('Charger heatmap not initialized');
        return;
    }
    
    // 根据充电桩数量选择合适的显示数量
    const maxDisplayChargers = 20; // 最多显示的充电桩数量
    const displayChargers = chargers.slice(0, Math.min(chargers.length, maxDisplayChargers));
    
    // 设置滚动功能以允许查看更多充电桩
    const shouldEnableScroll = chargers.length > 10;
    
    // 准备标签和数据
    const chargerLabels = displayChargers.map(c => {
        // 安全地获取charger_id，处理可能的undefined情况
        if (c.charger_id && typeof c.charger_id === 'string') {
            return `充电桩 ${c.charger_id.split('_')[1] || ''}`;
        }
        return `充电桩 ${Math.random().toString(36).substr(2, 5)}`; // 生成一个随机ID作为后备
    });
    
    // 计算基于当前状态的利用率数据
    const utilizationData = displayChargers.map(c => {
        // 基于状态计算利用率
        if (c.status === 'occupied') {
            return 80 + Math.random() * 20; // 80-100% for occupied
        } else if (c.status === 'available') {
            const queueLength = c.queue ? c.queue.length : 0;
            return queueLength * 20; // 20% for each user in queue
        } else if (c.status === 'failure') {
            return 0; // 0% for failed chargers
        }
        return Math.random() * 30; // random value for unknown status
    });
    
    // 更新图表数据和选项
    chargerHeatmap.data.labels = chargerLabels;
    chargerHeatmap.data.datasets[0].data = utilizationData;
    
    // 为y轴启用滚动
    chargerHeatmap.options.scales.y.ticks = {
        autoSkip: false,
        maxRotation: 0,
        minRotation: 0
    };
    
    // 添加滚动功能
    if (shouldEnableScroll) {
        chargerHeatmap.options.scales.y = {
            ...chargerHeatmap.options.scales.y,
            min: 0,
            max: 9, // 显示10个条目
            ticks: {
                autoSkip: false,
                maxRotation: 0,
                minRotation: 0
            }
        };
        
        // 确保已经设置了滚动插件
        if (!chargerHeatmap.options.plugins.zoom) {
            chargerHeatmap.options.plugins.zoom = {
                pan: {
                    enabled: true,
                    mode: 'y',
                    threshold: 10,
                },
                zoom: {
                    wheel: {
                        enabled: true,
                    },
                    pinch: {
                        enabled: true
                    },
                    mode: 'y',
                }
            };
        } else {
            chargerHeatmap.options.plugins.zoom.pan.enabled = true;
            chargerHeatmap.options.plugins.zoom.pan.mode = 'y';
            chargerHeatmap.options.plugins.zoom.zoom.wheel.enabled = true;
            chargerHeatmap.options.plugins.zoom.zoom.mode = 'y';
        }
    } else {
        // 禁用滚动（如果只有少量条目）
        if (chargerHeatmap.options.plugins.zoom) {
            chargerHeatmap.options.plugins.zoom.pan.enabled = false;
            chargerHeatmap.options.plugins.zoom.zoom.wheel.enabled = false;
        }
    }
    
    // 更新图表
    chargerHeatmap.update();
    
    // 添加使用提示
    const heatmapContainer = document.getElementById('charger-heatmap').parentNode;
    if (shouldEnableScroll && !heatmapContainer.querySelector('.scroll-hint')) {
        const scrollHint = document.createElement('div');
        scrollHint.className = 'scroll-hint small text-muted text-center mt-1';
        scrollHint.innerHTML = '提示: 使用鼠标滚轮上下滚动查看更多充电桩';
        heatmapContainer.appendChild(scrollHint);
    }
}

// Update grid load chart
function updateGridLoadChart(gridStatus) {
    // 确保gridStatus对象存在
    if (!gridStatus) {
        console.warn('未收到电网状态数据');
        return;
    }

    try {
        // 直接使用时间序列图的时间标签
        const timeLabel = simulation.metricsHistory.timestamps[simulation.metricsHistory.timestamps.length - 1];
        
        // 提取电网负载数据
        const baseLoad = gridStatus.current_load ? (gridStatus.current_load - (gridStatus.ev_load || 0)) : 0;
        const evLoad = gridStatus.ev_load || 0;
        const totalLoad = gridStatus.current_load || 0;
        
        // 添加到历史数据数组
        simulation.gridLoadHistory.timestamps = simulation.metricsHistory.timestamps; // 直接使用相同的时间数组
        simulation.gridLoadHistory.baseLoad.push(baseLoad);
        simulation.gridLoadHistory.evLoad.push(evLoad);
        simulation.gridLoadHistory.totalLoad.push(totalLoad);
        
        // 保持与时间序列图相同的数据点数量
        const maxPoints = simulation.metricsHistory.timestamps.length;
        while (simulation.gridLoadHistory.baseLoad.length > maxPoints) {
            simulation.gridLoadHistory.baseLoad.shift();
            simulation.gridLoadHistory.evLoad.shift();
            simulation.gridLoadHistory.totalLoad.shift();
        }
        
        // 更新图表
        if (gridLoadChart) {
            gridLoadChart.data.labels = simulation.metricsHistory.timestamps;
            gridLoadChart.data.datasets[0].data = simulation.gridLoadHistory.baseLoad;
            gridLoadChart.data.datasets[1].data = simulation.gridLoadHistory.evLoad;
            gridLoadChart.data.datasets[2].data = simulation.gridLoadHistory.totalLoad;
            gridLoadChart.update();
        } else {
            console.warn("gridLoadChart not initialized. Grid load chart will not be updated.");
        }
    } catch (e) {
        console.error("Error updating grid-load-chart:", e);
    }

    // 更新负载指标显示
    const totalLoadElement = document.getElementById('totalLoad');
    const evLoadElement = document.getElementById('evLoad');
    const renewableRatioElement = document.getElementById('renewableRatio');

    if (totalLoadElement) {
        totalLoadElement.textContent = `${(gridStatus.current_load || 0).toFixed(1)} kW`;
    }
    if (evLoadElement) {
        evLoadElement.textContent = `${(gridStatus.ev_load || 0).toFixed(1)} kW`;
    }
    if (renewableRatioElement) {
        renewableRatioElement.textContent = `${(gridStatus.renewable_ratio || 0).toFixed(1)}%`;
    }
}

// Update trend indicators
function updateTrend(element, current, previous) {
    if (!element) return;
    
    const diff = current - previous;
    const percentChange = (diff / Math.max(0.01, Math.abs(previous))) * 100;
    
    if (diff > 0) {
        element.innerHTML = `<i class="fas fa-arrow-up"></i> ${Math.abs(percentChange).toFixed(2)}%`;
        element.className = 'text-success';
    } else if (diff < 0) {
        element.innerHTML = `<i class="fas fa-arrow-down"></i> ${Math.abs(percentChange).toFixed(2)}%`;
        element.className = 'text-danger';
    } else {
        element.innerHTML = `<i class="fas fa-arrows-alt-h"></i> 0.00%`;
        element.className = 'text-secondary';
    }
}

// Animate value update
function animateValueUpdate(element, newValue) {
    if (!element) return;
    
    // 检查newValue是否为数字或可转换为数字的字符串
    if (typeof newValue !== 'number' && typeof newValue !== 'string') {
        console.warn('animateValueUpdate: newValue is not a number or string', newValue);
        return;
    }
    
    // 确保newValue是数字
    const numericValue = typeof newValue === 'string' ? parseFloat(newValue) : newValue;
    if (isNaN(numericValue)) {
        console.warn('animateValueUpdate: newValue cannot be converted to a number', newValue);
        return;
    }
    
    const oldValue = parseFloat(element.textContent);
    const difference = numericValue - oldValue;
    
    if (Math.abs(difference) < 0.01) {
        element.textContent = numericValue.toFixed(2);
        return;
    }
    
    // Add highlight class for animation
    element.classList.add('highlight');
    
    // Remove highlight class after animation completes
    setTimeout(() => {
        element.classList.remove('highlight');
    }, 1500);
    
    // Update value
    element.textContent = numericValue.toFixed(2);
}

// Format date and time
function formatDateTime(date) {
    // Handle invalid date inputs
    if (!date) {
        console.error('Invalid date input: null or undefined');
        return 'Invalid Date';
    }
    
    // Convert string to date object if needed
    if (typeof date === 'string') {
        try {
            date = new Date(date);
        } catch (e) {
            console.error('Error parsing date string:', e, date);
            return date; // Return the original string if parsing fails
        }
    }
    
    // Check if date is valid after conversion
    if (!(date instanceof Date) || isNaN(date.getTime())) {
        console.error('Invalid Date object:', date);
        return 'Invalid Date';
    }
    
    try {
        // Format with year, month, day, hour, and minute
        return `${date.getFullYear()}-${(date.getMonth() + 1).toString().padStart(2, '0')}-${date.getDate().toString().padStart(2, '0')} ${date.getHours().toString().padStart(2, '0')}:${date.getMinutes().toString().padStart(2, '0')}`;
    } catch (e) {
        console.error('Date formatting error:', e);
        return date.toString();
    }
}

// Update system time
function updateSystemTime() {
    const now = new Date();
    const formattedTime = formatDateTime(now);
    document.getElementById('current-system-time').textContent = formattedTime;
    
    // Update every second
    setTimeout(updateSystemTime, 1000);
}

// Initialize configuration modal
function initializeConfigModal() {
    // Environment config
    const configGridId = document.getElementById('config-grid-id');
    const configChargerCount = document.getElementById('config-charger-count');
    const configUserCount = document.getElementById('config-user-count');
    const configSimulationDays = document.getElementById('config-simulation-days');
    const configTimeStep = document.getElementById('config-time-step');
    const configUseModel = document.getElementById('config-use-model');
    const configUseMultiAgent = document.getElementById('config-use-multi-agent');
    
    // 检查元素是否存在
    if (configGridId) configGridId.value = config.environment?.grid_id || 'DEFAULT001';
    if (configChargerCount) configChargerCount.value = config.environment?.charger_count || 20;
    if (configUserCount) configUserCount.value = config.environment?.user_count || 50;
    if (configSimulationDays) configSimulationDays.value = config.environment?.simulation_days || 7;
    if (configTimeStep) configTimeStep.value = config.environment?.time_step_minutes || 15;
    
    // Scheduler config
    if (configUseModel) configUseModel.checked = config.scheduler?.use_trained_model || false;
    if (configUseMultiAgent) configUseMultiAgent.checked = config.scheduler?.use_multi_agent || false;
    
    // Weights
    const userWeight = config.scheduler?.optimization_weights?.user_satisfaction || 0.4;
    const profitWeight = config.scheduler?.optimization_weights?.operator_profit || 0.3;
    const gridWeight = config.scheduler?.optimization_weights?.grid_friendliness || 0.3;
    
    const configUserWeight = document.getElementById('config-user-weight');
    const configProfitWeight = document.getElementById('config-profit-weight');
    const configGridWeight = document.getElementById('config-grid-weight');
    const configUserWeightValue = document.getElementById('config-user-weight-value');
    const configProfitWeightValue = document.getElementById('config-profit-weight-value');
    const configGridWeightValue = document.getElementById('config-grid-weight-value');
    
    if (configUserWeight) configUserWeight.value = userWeight;
    if (configProfitWeight) configProfitWeight.value = profitWeight;
    if (configGridWeight) configGridWeight.value = gridWeight;
    
    if (configUserWeightValue) configUserWeightValue.textContent = userWeight.toFixed(2);
    if (configProfitWeightValue) configProfitWeightValue.textContent = profitWeight.toFixed(2);
    if (configGridWeightValue) configGridWeightValue.textContent = gridWeight.toFixed(2);
    
    // Update weight values when sliders change
    if (configUserWeight) {
        configUserWeight.addEventListener('input', function() {
            if (configUserWeightValue) configUserWeightValue.textContent = parseFloat(this.value).toFixed(2);
        });
    }
    
    if (configProfitWeight) {
        configProfitWeight.addEventListener('input', function() {
            if (configProfitWeightValue) configProfitWeightValue.textContent = parseFloat(this.value).toFixed(2);
        });
    }
    
    if (configGridWeight) {
        configGridWeight.addEventListener('input', function() {
            if (configGridWeightValue) configGridWeightValue.textContent = parseFloat(this.value).toFixed(2);
        });
    }
    
    // Grid config
    const configNormalPrice = document.getElementById('config-normal-price');
    const configPeakPrice = document.getElementById('config-peak-price');
    const configValleyPrice = document.getElementById('config-valley-price');
    
    if (configNormalPrice) configNormalPrice.value = config.grid?.normal_price || 0.85;
    if (configPeakPrice) configPeakPrice.value = config.grid?.peak_price || 1.2;
    if (configValleyPrice) configValleyPrice.value = config.grid?.valley_price || 0.4;
    
    // Create hour checkboxes for peak and valley hours
    const peakHoursContainer = document.getElementById('peak-hours-checkboxes');
    const valleyHoursContainer = document.getElementById('valley-hours-checkboxes');
    
    if (peakHoursContainer) peakHoursContainer.innerHTML = '';
    if (valleyHoursContainer) valleyHoursContainer.innerHTML = '';
    
    const peakHours = config.grid?.peak_hours || [7, 8, 9, 10, 18, 19, 20, 21];
    const valleyHours = config.grid?.valley_hours || [0, 1, 2, 3, 4, 5];
    
    if (peakHoursContainer && valleyHoursContainer) {
        for (let hour = 0; hour < 24; hour++) {
            // Peak hours
            const peakLabel = document.createElement('label');
            peakLabel.className = 'hour-checkbox';
            
            const peakCheckbox = document.createElement('input');
            peakCheckbox.type = 'checkbox';
            peakCheckbox.className = 'peak-hour-checkbox';
            peakCheckbox.value = hour;
            peakCheckbox.checked = peakHours.includes(hour);
            
            peakLabel.appendChild(peakCheckbox);
            peakLabel.appendChild(document.createTextNode(` ${hour}:00 `));
            peakHoursContainer.appendChild(peakLabel);
            
            // Valley hours
            const valleyLabel = document.createElement('label');
            valleyLabel.className = 'hour-checkbox';
            
            const valleyCheckbox = document.createElement('input');
            valleyCheckbox.type = 'checkbox';
            valleyCheckbox.className = 'valley-hour-checkbox';
            valleyCheckbox.value = hour;
            valleyCheckbox.checked = valleyHours.includes(hour);
            
            valleyLabel.appendChild(valleyCheckbox);
            valleyLabel.appendChild(document.createTextNode(` ${hour}:00 `));
            valleyHoursContainer.appendChild(valleyLabel);
        }
    }
    
    // Model config
    const configModelPath = document.getElementById('config-model-path');
    const configInputDim = document.getElementById('config-input-dim');
    const configHiddenDim = document.getElementById('config-hidden-dim');
    const configTaskHiddenDim = document.getElementById('config-task-hidden-dim');
    
    if (configModelPath) configModelPath.value = config.model?.model_path || 'models/ev_charging_model.pth';
    if (configInputDim) configInputDim.value = config.model?.input_dim || 19;
    if (configHiddenDim) configHiddenDim.value = config.model?.hidden_dim || 128;
    if (configTaskHiddenDim) configTaskHiddenDim.value = config.model?.task_hidden_dim || 64;
}

// Save configuration
function saveConfig() {
    console.log('保存配置函数被调用');
    
    try {
        // 声明configToSave变量
        let configToSave;
        
        // 检查jQuery是否可用
        if (typeof $ === 'undefined') {
            console.warn('jQuery未定义，使用原生JavaScript');
            
            // 使用原生JavaScript收集配置
            const getValueById = (id) => {
                const el = document.getElementById(id);
                return el ? el.value : '';
            };
            
            const getCheckedById = (id) => {
                const el = document.getElementById(id);
                return el ? el.checked : false;
            };
            
            configToSave = {
                environment: {
                    grid_id: getValueById("config-grid-id") || "",
                    station_count: parseInt(getValueById("config-station-count")) || 20,
                    chargers_per_station: parseInt(getValueById("config-chargers-per-station")) || 20,
                    user_count: parseInt(getValueById("config-user-count")) || 1000,
                    region_count: parseInt(getValueById("config-region-count")) || 5,
                    simulation_days: parseInt(getValueById("config-simulation-days")) || 7,
                    time_step_minutes: parseInt(getValueById("config-time-step")) || 15,
                    map_bounds: {
                        min_lat: parseFloat(getValueById("config-min-lat")) || 30.5,
                        max_lat: parseFloat(getValueById("config-max-lat")) || 31.0,
                        min_lng: parseFloat(getValueById("config-min-lng")) || 114.0,
                        max_lng: parseFloat(getValueById("config-max-lng")) || 114.5
                    }
                },
                scheduler: {
                    use_trained_model: getCheckedById("config-use-model"),
                    use_multi_agent: getCheckedById("config-use-multi-agent"),
                    optimization_weights: {
                        user_satisfaction: parseFloat(getValueById("config-user-weight")) || 0.33,
                        operator_profit: parseFloat(getValueById("config-profit-weight")) || 0.33,
                        grid_friendliness: parseFloat(getValueById("config-grid-weight")) || 0.34
                    }
                },
                model: {
                    model_path: getValueById("config-model-path") || "",
                    input_dim: parseInt(getValueById("config-input-dim")) || 19,
                    hidden_dim: parseInt(getValueById("config-hidden-dim")) || 128,
                    task_hidden_dim: parseInt(getValueById("config-task-hidden-dim")) || 64
                }
            };
        } else {
            // 使用jQuery收集配置表单中的所有值
            configToSave = {
                environment: {
                    grid_id: $("#config-grid-id").val() || "",
                    station_count: parseInt($("#config-station-count").val()) || 20,
                    chargers_per_station: parseInt($("#config-chargers-per-station").val()) || 20,
                    user_count: parseInt($("#config-user-count").val()) || 1000,
                    region_count: parseInt($("#config-region-count").val()) || 5,
                    simulation_days: parseInt($("#config-simulation-days").val()) || 7,
                    time_step_minutes: parseInt($("#config-time-step").val()) || 15,
                    map_bounds: {
                        min_lat: parseFloat($("#config-min-lat").val()) || 30.5,
                        max_lat: parseFloat($("#config-max-lat").val()) || 31.0,
                        min_lng: parseFloat($("#config-min-lng").val()) || 114.0,
                        max_lng: parseFloat($("#config-max-lng").val()) || 114.5
                    }
                },
                scheduler: {
                    use_trained_model: $("#config-use-model").is(":checked"),
                    use_multi_agent: $("#config-use-multi-agent").is(":checked"),
                    optimization_weights: {
                        user_satisfaction: parseFloat($("#config-user-weight").val()) || 0.33,
                        operator_profit: parseFloat($("#config-profit-weight").val()) || 0.33,
                        grid_friendliness: parseFloat($("#config-grid-weight").val()) || 0.34
                    }
                },
                model: {
                    model_path: $("#config-model-path").val() || "",
                    input_dim: parseInt($("#config-input-dim").val()) || 19,
                    hidden_dim: parseInt($("#config-hidden-dim").val()) || 128,
                    task_hidden_dim: parseInt($("#config-task-hidden-dim").val()) || 64
                }
            };
        }

        console.log('准备发送配置:', configToSave);

        // 使用原生fetch API发送配置到服务器
        fetch("/api/config", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify(configToSave)
        })
        .then(response => {
            console.log('收到初始响应:', response);
            if (!response.ok) {
                throw new Error(`服务器响应错误: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            console.log('配置保存响应:', data);
            if (data.success) {
                showNotification("配置已成功保存", "success");
                
                // 关闭模态窗口 - 使用原生或jQuery方法
                const configModal = document.getElementById('configModal');
                if (configModal && typeof bootstrap !== 'undefined') {
                    const modalInstance = bootstrap.Modal.getInstance(configModal);
                    if (modalInstance) {
                        modalInstance.hide();
                    }
                } else if (typeof $ !== 'undefined') {
                    $("#configModal").modal("hide");
                }
                
                // 更新UI以反映新配置
                if (data.config) {
                    updateUIFromConfig(data.config);
                }
            } else {
                showNotification("保存配置失败: " + (data.error || "未知错误"), "danger");
            }
        })
        .catch(error => {
            console.error('保存配置错误:', error);
            showNotification("保存配置时发生错误: " + error.message, "danger");
        });
    } catch (e) {
        console.error('保存配置过程中发生错误:', e);
        showNotification("处理配置数据时出错: " + e.message, "danger");
    }
}

// Update UI from config
function updateUIFromConfig() {
    // Update simulation days slider
    simulationDays.value = config.environment.simulation_days;
    daysValue.textContent = `${simulationDays.value}天`;
    
    // Update multi-agent switch
    multiAgentSwitch.checked = config.scheduler.use_multi_agent;
    toggleMultiAgentUI(config.scheduler.use_multi_agent);
    
    // Update strategy selection based on weights
    const weights = config.scheduler.optimization_weights;
    
    if (weights.user_satisfaction > 0.5) {
        strategySelect.value = 'user';
    } else if (weights.operator_profit > 0.5) {
        strategySelect.value = 'profit';
    } else if (weights.grid_friendliness > 0.5) {
        strategySelect.value = 'grid';
    } else {
        strategySelect.value = 'balanced';
    }
    
    // Update agent weights chart
    if (agentWeightsChart) {
        agentWeightsChart.data.datasets[0].data = [
            weights.user_satisfaction,
            weights.operator_profit,
            weights.grid_friendliness
        ];
        agentWeightsChart.update();
    }
    
    // Update weight sliders in multi-agent card
    document.getElementById('user-satisfaction-weight').value = weights.user_satisfaction;
    document.getElementById('operator-profit-weight').value = weights.operator_profit;
    document.getElementById('grid-friendliness-weight').value = weights.grid_friendliness;
    
    // Update weight displays
    document.querySelectorAll('.user-weight-display').forEach(el => el.textContent = weights.user_satisfaction.toFixed(2));
    document.querySelectorAll('.profit-weight-display').forEach(el => el.textContent = weights.operator_profit.toFixed(2));
    document.querySelectorAll('.grid-weight-display').forEach(el => el.textContent = weights.grid_friendliness.toFixed(2));
}

// Setup scenario presets
function setupScenarioPresets() {
    document.getElementById('apply-scenario').addEventListener('click', function() {
        const scenario = document.getElementById('scenario-select').value;
        
        switch(scenario) {
            case 'normal':
                // Normal workday - default settings
                document.getElementById('charger-count').value = 20;
                document.getElementById('user-count').value = 50;
                break;
            case 'peak':
                // Holiday peak - more users, same chargers
                document.getElementById('charger-count').value = 20;
                document.getElementById('user-count').value = 80;
                break;
            case 'night':
                // Low load night - fewer users
                document.getElementById('charger-count').value = 20;
                document.getElementById('user-count').value = 30;
                break;
            case 'failure':
                // Charger failure - fewer chargers
                document.getElementById('charger-count').value = 15;
                document.getElementById('user-count').value = 50;
                break;
        }
        
        showNotification('场景已应用', 'success');
    });
}

// Update strategy UI
function updateStrategyUI(strategy) {
    // Get weights from predefined strategies
    let weights;
    
    if (strategy === 'user') {
        weights = config.strategies?.user || {
            user_satisfaction: 0.6,
            operator_profit: 0.2,
            grid_friendliness: 0.2
        };
    } else if (strategy === 'profit') {
        weights = config.strategies?.profit || {
            user_satisfaction: 0.2,
            operator_profit: 0.6,
            grid_friendliness: 0.2
        };
    } else if (strategy === 'grid') {
        weights = config.strategies?.grid || {
            user_satisfaction: 0.2,
            operator_profit: 0.2,
            grid_friendliness: 0.6
        };
    } else {
        weights = config.strategies?.balanced || {
            user_satisfaction: 0.33,
            operator_profit: 0.33,
            grid_friendliness: 0.34
        };
    }
    
    // Update config
    config.scheduler.optimization_weights = weights;
    
    // Update UI
    document.getElementById('user-satisfaction-weight').value = weights.user_satisfaction;
    document.getElementById('operator-profit-weight').value = weights.operator_profit;
    document.getElementById('grid-friendliness-weight').value = weights.grid_friendliness;
    
    // Update weight displays
    document.querySelectorAll('.user-weight-display').forEach(el => el.textContent = weights.user_satisfaction.toFixed(2));
    document.querySelectorAll('.profit-weight-display').forEach(el => el.textContent = weights.operator_profit.toFixed(2));
    document.querySelectorAll('.grid-weight-display').forEach(el => el.textContent = weights.grid_friendliness.toFixed(2));
    
    // Update agent weights chart
    if (agentWeightsChart) {
        agentWeightsChart.data.datasets[0].data = [
            weights.user_satisfaction,
            weights.operator_profit,
            weights.grid_friendliness
        ];
        agentWeightsChart.update();
    }
}

// Apply scenario
function applyScenario() {
    const scenario = document.getElementById('scenario-select').value;
    const chargerCount = parseInt(document.getElementById('charger-count').value);
    const userCount = parseInt(document.getElementById('user-count').value);
    
    // Update config
    config.environment.charger_count = chargerCount;
    config.environment.user_count = userCount;
    
    // Add special settings for each scenario
    if (scenario === 'night') {
        // Night mode - adjust peak/valley hours
        config.grid.peak_hours = [18, 19, 20, 21];
        config.grid.valley_hours = [22, 23, 0, 1, 2, 3, 4, 5, 6];
    } else if (scenario === 'failure') {
        // Add failure rate setting (placeholder)
        config.environment.charger_failure_rate = 0.3;
    } else {
        // Reset to default settings
        config.grid.peak_hours = [7, 8, 9, 10, 18, 19, 20, 21];
        config.grid.valley_hours = [0, 1, 2, 3, 4, 5];
        config.environment.charger_failure_rate = 0;
    }
    
    // Save config
    fetch('/api/config', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(config)
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'success') {
            showNotification('场景已应用', 'success');
        } else {
            showNotification('应用场景失败', 'danger');
        }
    })
    .catch(error => {
        console.error('Error applying scenario:', error);
        showNotification('应用场景失败', 'danger');
    });
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

// 显示结果选择模态框
function showResultsModal() {
    // 检查是否已存在模态框，如果存在则移除
    let existingModal = document.getElementById('resultsModal');
    if (existingModal) {
        existingModal.remove();
    }
    
    // 创建模态框
    const modalHTML = `
    <div class="modal fade" id="resultsModal" tabindex="-1" aria-labelledby="resultsModalLabel" aria-hidden="true">
        <div class="modal-dialog modal-lg">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title" id="resultsModalLabel">已保存的模拟结果</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                </div>
                <div class="modal-body">
                    <div class="table-responsive">
                        <table class="table table-striped table-hover">
                            <thead>
                                <tr>
                                    <th>文件名</th>
                                    <th>创建时间</th>
                                    <th>模拟时间</th>
                                    <th>进度</th>
                                    <th>用户满意度</th>
                                    <th>操作</th>
                                </tr>
                            </thead>
                            <tbody id="results-table-body">
                                <tr>
                                    <td colspan="6" class="text-center">正在加载结果...</td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">关闭</button>
                </div>
            </div>
        </div>
    </div>
    `;
    
    // 添加到文档
    document.body.insertAdjacentHTML('beforeend', modalHTML);
    
    // 获取模态框实例
    const resultsModal = new bootstrap.Modal(document.getElementById('resultsModal'));
    
    // 显示模态框
    resultsModal.show();
    
    // 获取结果列表
    fetchSimulationResults();
}

// 获取所有已保存的模拟结果
async function fetchSimulationResults() {
    try {
        const response = await fetch('/api/simulation/results');
        
        if (!response.ok) {
            throw new Error('Failed to fetch simulation results');
        }
        
        const data = await response.json();
        
        if (data.status === 'success') {
            displaySimulationResults(data.results);
        } else {
            throw new Error(data.message || 'Failed to fetch simulation results');
        }
    } catch (error) {
        console.error('Error fetching simulation results:', error);
        document.getElementById('results-table-body').innerHTML = `
            <tr>
                <td colspan="6" class="text-center text-danger">
                    获取模拟结果时出错: ${error.message}
                </td>
            </tr>
        `;
    }
}

// 显示模拟结果列表
function displaySimulationResults(results) {
    const tableBody = document.getElementById('results-table-body');
    
    if (!results || results.length === 0) {
        tableBody.innerHTML = `
            <tr>
                <td colspan="6" class="text-center">没有找到模拟结果</td>
            </tr>
        `;
        return;
    }
    
    let html = '';
    
    results.forEach(result => {
        const created = new Date(result.created).toLocaleString();
        const simulationTime = result.timestamp ? new Date(result.timestamp).toLocaleString() : 'Unknown';
        const progress = result.progress ? `${Math.round(result.progress)}%` : 'N/A';
        const userSatisfaction = result.metrics && result.metrics.user_satisfaction ? 
            result.metrics.user_satisfaction.toFixed(2) : 'N/A';
        
        html += `
            <tr>
                <td>${result.filename}</td>
                <td>${created}</td>
                <td>${simulationTime}</td>
                <td>${progress}</td>
                <td>${userSatisfaction}</td>
                <td>
                    <button class="btn btn-sm btn-primary" onclick="loadSimulationResult('${result.filename}')">
                        加载
                    </button>
                </td>
            </tr>
        `;
    });
    
    tableBody.innerHTML = html;
}

// 设置全局函数以便onclick调用
window.loadSimulationResult = async function(filename) {
    try {
        const response = await fetch(`/api/simulation/result/${filename}`);
        
        if (!response.ok) {
            throw new Error('Failed to load simulation result');
        }
        
        const data = await response.json();
        
        if (data.status === 'success') {
            // 关闭模态框
            const resultsModal = bootstrap.Modal.getInstance(document.getElementById('resultsModal'));
            resultsModal.hide();
            
            // 更新UI
            showNotification(`已加载模拟结果: ${filename}`, 'success');
            
            // 重置模拟状态
            simulation.running = false;
            startBtn.disabled = false;
            pauseBtn.disabled = true;
            
            // 清除旧数据
            resetSimulationData();
            
            // 如果有时间戳，更新时间显示
            if (data.result.timestamp) {
                const date = new Date(data.result.timestamp);
                simulationTime.textContent = formatDateTime(date);
            }
            
            // 更新进度条
            if (data.result.progress !== undefined) {
                const progress = Math.min(100, Math.max(0, data.result.progress));
                simulationProgress.style.width = `${progress}%`;
                simulationProgress.setAttribute('aria-valuenow', progress);
                simulationProgress.textContent = `${Math.round(progress)}%`;
            }
            
            // 更新指标
            if (data.result.metrics) {
                updateMetrics(data.result.metrics);
            }
            
            // 更新时间序列数据和图表
            if (data.result.metrics_series) {
                const series = data.result.metrics_series;
                
                // 将时间系列数据添加到模拟历史记录中
                simulation.metricsHistory = {
                    timestamps: series.timestamps.map(t => {
                        const date = new Date(t);
                        return formatDateTime(date);
                    }),
                    userSatisfaction: series.user_satisfaction || [],
                    operatorProfit: series.operator_profit || [],
                    gridFriendliness: series.grid_friendliness || [],
                    totalReward: series.total_reward || []
                };
                
                // 更新主指标图表
                if (metricsChart) {
                    metricsChart.data.labels = simulation.metricsHistory.timestamps;
                    metricsChart.data.datasets[0].data = simulation.metricsHistory.userSatisfaction;
                    metricsChart.data.datasets[1].data = simulation.metricsHistory.operatorProfit;
                    metricsChart.data.datasets[2].data = simulation.metricsHistory.gridFriendliness;
                    metricsChart.data.datasets[3].data = simulation.metricsHistory.totalReward;
                    metricsChart.update();
                }
                
                // 更新电网负载图表
                if (gridLoadChart && series.grid_load && series.ev_load) {
                    // 构建符合charts.js中updateGridLoadChart期望的数据格式
                    const gridData = {
                        history: []
                    };
                    
                    // 为每个时间点创建历史记录
                    for (let i = 0; i < series.grid_load.length; i++) {
                        gridData.history.push({
                            timestamp: series.timestamps[i],
                            grid_status: {
                                current_load: series.grid_load[i] || 0,
                                ev_load: series.ev_load[i] || 0,
                                renewable_ratio: series.renewable_ratio[i] || 0
                            }
                        });
                    }
                    
                    // 调用charts.js中的函数更新图表
                    updateGridLoadChart(gridData);
                    console.log("Updated grid load chart with filtered time series data");
                }
                
                // 如果启用了多智能体，更新相关图表
                if (multiAgentSwitch.checked && agentRewardsChart && conflictsChart) {
                    updateAgentRewardsChart();
                    updateConflictsChart();
                }
            }
            
            // 更新其他UI元素
            updateUIWithStateData(data.result);
        } else {
            throw new Error(data.message || 'Failed to load simulation result');
        }
    } catch (error) {
        console.error('Error loading simulation result:', error);
        showNotification(`加载模拟结果时出错: ${error.message}`, 'danger');
    }
};

// 更新地图统计信息
function updateMapStatistics(type, count, details = null) {
    const mapContainer = document.getElementById('map-container');
    if (!mapContainer) return;
    
    const mapContent = mapContainer.querySelector('#actual-map');
    if (!mapContent) return;
    
    // 查找或创建统计信息容器
    let statsDiv = mapContent.querySelector('.map-statistics');
    if (!statsDiv) {
        statsDiv = document.createElement('div');
        statsDiv.className = 'map-statistics position-absolute bottom-0 end-0 m-3 p-2 bg-white rounded shadow';
        statsDiv.style.zIndex = '30';
        mapContent.appendChild(statsDiv);
    }
    
    // 更新统计信息
    if (type === 'users') {
        let userStats = statsDiv.querySelector('.user-stats');
        if (!userStats) {
            userStats = document.createElement('div');
            userStats.className = 'user-stats mb-2';
            statsDiv.appendChild(userStats);
        }
        
        // 第二个参数可能是显示的用户数
        const displayCount = typeof details === 'number' ? details : count;
        userStats.innerHTML = `
            <div class="d-flex align-items-center mb-1">
                <div class="map-user-icon user-idle me-2" style="position:relative; width:24px; height:24px; transform:none; display:inline-flex;">
                    <i class="fas fa-car fa-xs"></i>
                </div>
                <div>
                    <div class="fw-bold">用户总数: <span class="ms-1">${count}</span></div>
                    <div class="small text-muted">显示: ${displayCount}/${count}</div>
                </div>
            </div>
        `;
    } else if (type === 'chargers') {
        let chargerStats = statsDiv.querySelector('.charger-stats');
        if (!chargerStats) {
            chargerStats = document.createElement('div');
            chargerStats.className = 'charger-stats';
            statsDiv.appendChild(chargerStats);
        }
        
        if (details) {
            const displayCount = details.display || count;
            chargerStats.innerHTML = `
                <div class="d-flex align-items-center mb-1">
                    <div class="map-charger-icon charger-available me-2" style="position:relative; width:24px; height:24px; transform:none; display:inline-flex;">
                        <i class="fas fa-charging-station fa-xs"></i>
                    </div>
                    <div>
                        <div class="fw-bold">充电桩总数: <span class="ms-1">${count}</span></div>
                        <div class="small text-muted">显示: ${displayCount}/${count}</div>
                    </div>
                </div>
                <div class="d-flex justify-content-between mt-1 small">
                    <span class="badge bg-success me-1">可用: ${details.available}</span>
                    <span class="badge bg-warning me-1">占用: ${details.occupied}</span>
                    <span class="badge bg-danger">故障: ${details.failure}</span>
                </div>
            `;
        } else {
            chargerStats.innerHTML = `
                <div class="d-flex align-items-center">
                    <div class="map-charger-icon charger-available me-2" style="position:relative; width:24px; height:24px; transform:none; display:inline-flex;">
                        <i class="fas fa-charging-station fa-xs"></i>
                    </div>
                    <div class="fw-bold">充电桩总数: <span class="ms-1">${count}</span></div>
                </div>
            `;
        }
    }
}

// 加载模拟结果
function loadSimulationResult(filename) {
    if (!filename) {
        console.error("No filename provided to loadSimulationResult");
        return;
    }
    
    console.log("Loading simulation result:", filename);
    showNotification('正在加载模拟结果...', 'info');
    
    fetch(`/api/simulation/result/${filename}`)
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            // 检查返回状态
            if (data.status !== 'success') {
                showNotification(`加载失败: ${data.message}`, 'error');
                return;
            }
            
            console.log("Received simulation result data:", data);
            
            // 重置模拟状态
            simulation.running = false;
            startBtn.disabled = false;
            pauseBtn.disabled = true;
            
            // 清除旧数据
            resetSimulationData();
            
            // 初始化结果对象，避免undefined错误
            const result = data.result || {};
            
            // 更新用户
            if (result.users && Array.isArray(result.users) && result.users.length > 0) {
                updateMapWithUsers(result.users);
            }
            
            // 更新充电桩
            if (result.chargers && Array.isArray(result.chargers) && result.chargers.length > 0) {
                updateMapWithChargers(result.chargers);
            }
            
            // 更新进度条
            if (simulationProgress && result.progress !== undefined) {
                const progress = Math.min(100, Math.max(0, result.progress));
                simulationProgress.style.width = `${progress}%`;
                simulationProgress.setAttribute('aria-valuenow', progress);
                simulationProgress.textContent = `${Math.round(progress)}%`;
            }
            
            // 更新指标
            if (result.metrics) {
                updateMetrics(result.metrics);
            }
            
            // 处理时间序列数据
            let hasTimeSeriesData = false;
            
            // 确保metrics_series存在并含有时间点
            if (data.metrics_series && 
                data.metrics_series.timestamps && 
                Array.isArray(data.metrics_series.timestamps) && 
                data.metrics_series.timestamps.length > 0) {
                
                console.log("Processing time series data with", data.metrics_series.timestamps.length, "timestamps");
                hasTimeSeriesData = true;
                
                // 确保所有数组都存在，防止undefined错误
                const timestamps = data.metrics_series.timestamps;
                const userSatisfaction = Array.isArray(data.metrics_series.user_satisfaction) ? 
                    data.metrics_series.user_satisfaction : new Array(timestamps.length).fill(0);
                const operatorProfit = Array.isArray(data.metrics_series.operator_profit) ? 
                    data.metrics_series.operator_profit : new Array(timestamps.length).fill(0);
                const gridFriendliness = Array.isArray(data.metrics_series.grid_friendliness) ? 
                    data.metrics_series.grid_friendliness : new Array(timestamps.length).fill(0);
                const totalReward = Array.isArray(data.metrics_series.total_reward) ? 
                    data.metrics_series.total_reward : new Array(timestamps.length).fill(0);
                
                // 始终跳过第一个点，直接从索引1开始（索引0可能是最后一个点的复制）
                // 只有在数组长度大于1时才跳过第一个点
                const startIndex = timestamps.length > 1 ? 1 : 0;
                
                console.log(`Skipping first point, starting from index ${startIndex}`);
                
                // 按顺序绘制剩余的点
                const filteredTimestamps = timestamps.slice(startIndex);
                const filteredUserSatisfaction = userSatisfaction.slice(startIndex);
                const filteredOperatorProfit = operatorProfit.slice(startIndex);
                const filteredGridFriendliness = gridFriendliness.slice(startIndex);
                const filteredTotalReward = totalReward.slice(startIndex);
                
                console.log(`Using ${filteredTimestamps.length} data points for visualization`);
                
                // 同样处理电网负载数据
                let filteredGridLoad = [];
                let filteredEVLoad = [];
                
                if (Array.isArray(data.metrics_series.grid_load) && 
                    Array.isArray(data.metrics_series.ev_load)) {
                    filteredGridLoad = data.metrics_series.grid_load.slice(startIndex);
                    filteredEVLoad = data.metrics_series.ev_load.slice(startIndex);
                }
                
                // 转换时间戳为可读格式
                const formattedTimestamps = filteredTimestamps.map(ts => formatDateTime(ts));
                
                // 更新模拟历史记录
                simulation.metricsHistory = {
                    timestamps: formattedTimestamps,
                    userSatisfaction: filteredUserSatisfaction,
                    operatorProfit: filteredOperatorProfit,
                    gridFriendliness: filteredGridFriendliness,
                    totalReward: filteredTotalReward,
                    grid_load: filteredGridLoad,
                    ev_load: filteredEVLoad
                };
                
                // 如果有时间点，更新模拟时间显示
                if (formattedTimestamps.length > 0 && simulationTime) {
                    const lastTimestamp = filteredTimestamps[filteredTimestamps.length - 1];
                    simulationTime.textContent = formatDateTime(lastTimestamp);
                    console.log("Updated simulation time to:", formatDateTime(lastTimestamp));
                }
                
                // 更新主要指标图表
                if (metricsChart) {
                    metricsChart.data.labels = formattedTimestamps;
                    metricsChart.data.datasets[0].data = filteredUserSatisfaction;
                    metricsChart.data.datasets[1].data = filteredOperatorProfit;
                    metricsChart.data.datasets[2].data = filteredGridFriendliness;
                    metricsChart.data.datasets[3].data = filteredTotalReward;
                    metricsChart.update();
                    console.log("Updated metrics chart with filtered time series data");
                }
                
                // 更新电网负载图表
                if (gridLoadChart && filteredGridLoad.length > 0 && filteredEVLoad.length > 0) {
                    // 构建符合charts.js中updateGridLoadChart期望的数据格式
                    const gridData = {
                        history: []
                    };
                    
                    // 为每个时间点创建历史记录
                    for (let i = 0; i < formattedTimestamps.length; i++) {
                        gridData.history.push({
                            timestamp: filteredTimestamps[i],
                            grid_status: {
                                current_load: filteredGridLoad[i] || 0,
                                ev_load: filteredEVLoad[i] || 0,
                                renewable_ratio: filteredRenewableRatio[i] || 0
                            }
                        });
                    }
                    
                    // 调用charts.js中的函数更新图表
                    updateGridLoadChart(gridData);
                    console.log("Updated grid load chart with filtered time series data");
                }
            }
            
            // 如果没有时间序列数据，但有单个时间点数据，使用该数据
            if (!hasTimeSeriesData && result.timestamp && result.metrics) {
                console.log("No time series data, using single data point");
                
                const timestamp = formatDateTime(result.timestamp);
                
                // 使用单个数据点
                simulation.metricsHistory = {
                    timestamps: [timestamp],
                    userSatisfaction: [result.metrics.user_satisfaction || 0],
                    operatorProfit: [result.metrics.operator_profit || 0],
                    gridFriendliness: [result.metrics.grid_friendliness || 0],
                    totalReward: [result.metrics.total_reward || 0]
                };
                
                // 更新模拟时间显示
                if (simulationTime) {
                    simulationTime.textContent = timestamp;
                    console.log("Updated simulation time to:", timestamp);
                }
                
                // 更新图表
                if (metricsChart) {
                    metricsChart.data.labels = [timestamp];
                    metricsChart.data.datasets[0].data = [result.metrics.user_satisfaction || 0];
                    metricsChart.data.datasets[1].data = [result.metrics.operator_profit || 0];
                    metricsChart.data.datasets[2].data = [result.metrics.grid_friendliness || 0];
                    metricsChart.data.datasets[3].data = [result.metrics.total_reward || 0];
                    metricsChart.update();
                    console.log("Updated metrics chart with single data point");
                }
                
                // 更新电网负载图表
                if (gridLoadChart) {
                    gridLoadChart.data.labels = [timestamp];
                    gridLoadChart.data.datasets[0].data = [result.grid_load || 0];
                    gridLoadChart.data.datasets[1].data = [result.ev_load || 0];
                    gridLoadChart.update();
                    console.log("Updated grid load chart with single data point");
                }
            }
            
            showNotification('模拟结果加载成功', 'success');
        })
        .catch(error => {
            console.error('加载模拟结果时出错:', error);
            showNotification(`加载模拟结果时出错: ${error.message}`, 'error');
        });
}

// 更新主要指标图表
function updateMainMetricsChart() {
    if (!mainMetricsChart) return;
    
    // 检查是否有数据
    if (!simulation.metricsHistory || 
        !simulation.metricsHistory.timestamps ||
        simulation.metricsHistory.timestamps.length === 0) {
        console.warn("No metrics history data available for chart update");
        return;
    }
    
    console.log("Updating main metrics chart with", simulation.metricsHistory.timestamps.length, "data points");
    
    // 正确格式化时间戳以便在x轴上清晰展示
    const formattedLabels = simulation.metricsHistory.timestamps.map(ts => {
        try {
            // 首先检查是否已经是格式化后的字符串
            if (typeof ts === 'string' && ts.includes('-') && ts.includes(':')) {
                // 已经格式化的情况，只提取时间部分 (HH:MM)
                const timePart = ts.split(' ')[1];
                if (timePart && timePart.includes(':')) {
                    return timePart.substring(0, 5); // 只取HH:MM部分
                }
                return ts;
            }
            
            // 否则假设是ISO日期字符串并转换
            const date = new Date(ts);
            if (isNaN(date.getTime())) {
                console.warn("Invalid timestamp in metrics history:", ts);
                return "无效时间";
            }
            
            // 返回格式化为HH:MM的时间
            return `${date.getHours().toString().padStart(2, '0')}:${date.getMinutes().toString().padStart(2, '0')}`;
        } catch (e) {
            console.error("Error formatting chart timestamp:", e);
            return "错误";
        }
    });
    
    // 更新图表数据
    mainMetricsChart.data.labels = formattedLabels;
    
    // 使用安全的数据访问方式
    const metrics = simulation.metricsHistory.metrics || {};
    mainMetricsChart.data.datasets[0].data = Array.isArray(simulation.metricsHistory.userSatisfaction) ? 
        simulation.metricsHistory.userSatisfaction : metrics.user_satisfaction || [];
    mainMetricsChart.data.datasets[1].data = Array.isArray(simulation.metricsHistory.operatorProfit) ? 
        simulation.metricsHistory.operatorProfit : metrics.operator_profit || [];
    mainMetricsChart.data.datasets[2].data = Array.isArray(simulation.metricsHistory.gridFriendliness) ? 
        simulation.metricsHistory.gridFriendliness : metrics.grid_friendliness || [];
    mainMetricsChart.data.datasets[3].data = Array.isArray(simulation.metricsHistory.totalReward) ? 
        simulation.metricsHistory.totalReward : metrics.total_reward || [];
    
    mainMetricsChart.update();
}

// Update trend indicators
function updateTrend(element, current, previous) {
    if (!element) return;
    
    const diff = current - previous;
    const percentChange = (diff / Math.max(0.01, Math.abs(previous))) * 100;
    
    if (diff > 0) {
        element.innerHTML = `<i class="fas fa-arrow-up"></i> ${Math.abs(percentChange).toFixed(2)}%`;
        element.className = 'text-success';
    } else if (diff < 0) {
        element.innerHTML = `<i class="fas fa-arrow-down"></i> ${Math.abs(percentChange).toFixed(2)}%`;
        element.className = 'text-danger';
    } else {
        element.innerHTML = `<i class="fas fa-arrows-alt-h"></i> 0.00%`;
        element.className = 'text-secondary';
    }
}

// Animate value update
function animateValueUpdate(element, newValue) {
    if (!element) return;
    
    // 检查newValue是否为数字或可转换为数字的字符串
    if (typeof newValue !== 'number' && typeof newValue !== 'string') {
        console.warn('animateValueUpdate: newValue is not a number or string', newValue);
        return;
    }
    
    // 确保newValue是数字
    const numericValue = typeof newValue === 'string' ? parseFloat(newValue) : newValue;
    if (isNaN(numericValue)) {
        console.warn('animateValueUpdate: newValue cannot be converted to a number', newValue);
        return;
    }
    
    const oldValue = parseFloat(element.textContent);
    const difference = numericValue - oldValue;
    
    if (Math.abs(difference) < 0.01) {
        element.textContent = numericValue.toFixed(2);
        return;
    }
    
    // Add highlight class for animation
    element.classList.add('highlight');
    
    // Remove highlight class after animation completes
    setTimeout(() => {
        element.classList.remove('highlight');
    }, 1500);
    
    // Update value
    element.textContent = numericValue.toFixed(2);
}

// Format date and time
function formatDateTime(date) {
    // Handle invalid date inputs
    if (!date) {
        console.error('Invalid date input: null or undefined');
        return 'Invalid Date';
    }
    
    // Convert string to date object if needed
    if (typeof date === 'string') {
        try {
            date = new Date(date);
        } catch (e) {
            console.error('Error parsing date string:', e, date);
            return date; // Return the original string if parsing fails
        }
    }
    
    // Check if date is valid after conversion
    if (!(date instanceof Date) || isNaN(date.getTime())) {
        console.error('Invalid Date object:', date);
        return 'Invalid Date';
    }
    
    try {
        // Format with year, month, day, hour, and minute
        return `${date.getFullYear()}-${(date.getMonth() + 1).toString().padStart(2, '0')}-${date.getDate().toString().padStart(2, '0')} ${date.getHours().toString().padStart(2, '0')}:${date.getMinutes().toString().padStart(2, '0')}`;
    } catch (e) {
        console.error('Date formatting error:', e);
        return date.toString();
    }
}

// Update system time
function updateSystemTime() {
    const now = new Date();
    const formattedTime = formatDateTime(now);
    document.getElementById('current-system-time').textContent = formattedTime;
    
    // Update every second
    setTimeout(updateSystemTime, 1000);
}

// Initialize configuration modal
function initializeConfigModal() {
    // Environment config
    const configGridId = document.getElementById('config-grid-id');
    const configChargerCount = document.getElementById('config-charger-count');
    const configUserCount = document.getElementById('config-user-count');
    const configSimulationDays = document.getElementById('config-simulation-days');
    const configTimeStep = document.getElementById('config-time-step');
    const configUseModel = document.getElementById('config-use-model');
    const configUseMultiAgent = document.getElementById('config-use-multi-agent');
    
    // 检查元素是否存在
    if (configGridId) configGridId.value = config.environment?.grid_id || 'DEFAULT001';
    if (configChargerCount) configChargerCount.value = config.environment?.charger_count || 20;
    if (configUserCount) configUserCount.value = config.environment?.user_count || 50;
    if (configSimulationDays) configSimulationDays.value = config.environment?.simulation_days || 7;
    if (configTimeStep) configTimeStep.value = config.environment?.time_step_minutes || 15;
    
    // Scheduler config
    if (configUseModel) configUseModel.checked = config.scheduler?.use_trained_model || false;
    if (configUseMultiAgent) configUseMultiAgent.checked = config.scheduler?.use_multi_agent || false;
    
    // Weights
    const userWeight = config.scheduler?.optimization_weights?.user_satisfaction || 0.4;
    const profitWeight = config.scheduler?.optimization_weights?.operator_profit || 0.3;
    const gridWeight = config.scheduler?.optimization_weights?.grid_friendliness || 0.3;
    
    const configUserWeight = document.getElementById('config-user-weight');
    const configProfitWeight = document.getElementById('config-profit-weight');
    const configGridWeight = document.getElementById('config-grid-weight');
    const configUserWeightValue = document.getElementById('config-user-weight-value');
    const configProfitWeightValue = document.getElementById('config-profit-weight-value');
    const configGridWeightValue = document.getElementById('config-grid-weight-value');
    
    if (configUserWeight) configUserWeight.value = userWeight;
    if (configProfitWeight) configProfitWeight.value = profitWeight;
    if (configGridWeight) configGridWeight.value = gridWeight;
    
    if (configUserWeightValue) configUserWeightValue.textContent = userWeight.toFixed(2);
    if (configProfitWeightValue) configProfitWeightValue.textContent = profitWeight.toFixed(2);
    if (configGridWeightValue) configGridWeightValue.textContent = gridWeight.toFixed(2);
    
    // Update weight values when sliders change
    if (configUserWeight) {
        configUserWeight.addEventListener('input', function() {
            if (configUserWeightValue) configUserWeightValue.textContent = parseFloat(this.value).toFixed(2);
        });
    }
    
    if (configProfitWeight) {
        configProfitWeight.addEventListener('input', function() {
            if (configProfitWeightValue) configProfitWeightValue.textContent = parseFloat(this.value).toFixed(2);
        });
    }
    
    if (configGridWeight) {
        configGridWeight.addEventListener('input', function() {
            if (configGridWeightValue) configGridWeightValue.textContent = parseFloat(this.value).toFixed(2);
        });
    }
    
    // Grid config
    const configNormalPrice = document.getElementById('config-normal-price');
    const configPeakPrice = document.getElementById('config-peak-price');
    const configValleyPrice = document.getElementById('config-valley-price');
    
    if (configNormalPrice) configNormalPrice.value = config.grid?.normal_price || 0.85;
    if (configPeakPrice) configPeakPrice.value = config.grid?.peak_price || 1.2;
    if (configValleyPrice) configValleyPrice.value = config.grid?.valley_price || 0.4;
    
    // Create hour checkboxes for peak and valley hours
    const peakHoursContainer = document.getElementById('peak-hours-checkboxes');
    const valleyHoursContainer = document.getElementById('valley-hours-checkboxes');
    
    if (peakHoursContainer) peakHoursContainer.innerHTML = '';
    if (valleyHoursContainer) valleyHoursContainer.innerHTML = '';
    
    const peakHours = config.grid?.peak_hours || [7, 8, 9, 10, 18, 19, 20, 21];
    const valleyHours = config.grid?.valley_hours || [0, 1, 2, 3, 4, 5];
    
    if (peakHoursContainer && valleyHoursContainer) {
        for (let hour = 0; hour < 24; hour++) {
            // Peak hours
            const peakLabel = document.createElement('label');
            peakLabel.className = 'hour-checkbox';
            
            const peakCheckbox = document.createElement('input');
            peakCheckbox.type = 'checkbox';
            peakCheckbox.className = 'peak-hour-checkbox';
            peakCheckbox.value = hour;
            peakCheckbox.checked = peakHours.includes(hour);
            
            peakLabel.appendChild(peakCheckbox);
            peakLabel.appendChild(document.createTextNode(` ${hour}:00 `));
            peakHoursContainer.appendChild(peakLabel);
            
            // Valley hours
            const valleyLabel = document.createElement('label');
            valleyLabel.className = 'hour-checkbox';
            
            const valleyCheckbox = document.createElement('input');
            valleyCheckbox.type = 'checkbox';
            valleyCheckbox.className = 'valley-hour-checkbox';
            valleyCheckbox.value = hour;
            valleyCheckbox.checked = valleyHours.includes(hour);
            
            valleyLabel.appendChild(valleyCheckbox);
            valleyLabel.appendChild(document.createTextNode(` ${hour}:00 `));
            valleyHoursContainer.appendChild(valleyLabel);
        }
    }
    
    // Model config
    const configModelPath = document.getElementById('config-model-path');
    const configInputDim = document.getElementById('config-input-dim');
    const configHiddenDim = document.getElementById('config-hidden-dim');
    const configTaskHiddenDim = document.getElementById('config-task-hidden-dim');
    
    if (configModelPath) configModelPath.value = config.model?.model_path || 'models/ev_charging_model.pth';
    if (configInputDim) configInputDim.value = config.model?.input_dim || 19;
    if (configHiddenDim) configHiddenDim.value = config.model?.hidden_dim || 128;
    if (configTaskHiddenDim) configTaskHiddenDim.value = config.model?.task_hidden_dim || 64;
}

// Handle algorithm selection change
function handleAlgorithmChange() {
    const algorithmSelect = document.getElementById('algorithm-select');
    const multiAgentSwitch = document.getElementById('multi-agent-switch');
    const strategySelect = document.getElementById('strategy-select');

    if (!algorithmSelect || !multiAgentSwitch || !strategySelect) return;

    const selectedAlgorithm = algorithmSelect.value;
    simulation.algorithm = selectedAlgorithm; // Update global state

    // Update the disabled MAS switch based on algorithm
    multiAgentSwitch.checked = (selectedAlgorithm === 'coordinated_mas' || selectedAlgorithm === 'marl');

    // Disable strategy selection if MARL is chosen (weights are not used)
    strategySelect.disabled = (selectedAlgorithm === 'marl');

    // Show/hide MARL-specific UI elements (like agent weights panel)
    toggleMultiAgentUI(selectedAlgorithm === 'coordinated_mas'); // Only show weights for coordinated_mas for now
}

function connectWebSocket() {
    // ... existing code ...

    socket.onmessage = function(event) {
        if (isPaused) { // Check if paused
            return; // Skip update if paused
        }
        // ... existing code ...
    };

    socket.onopen = function(event) {
        console.log("WebSocket connection opened.");
        startSimBtn.disabled = false;
        stopSimBtn.disabled = true;
        pauseResumeBtn.disabled = true; // Initially disabled
        statusDiv.textContent = 'Connected. Ready to start simulation.';
        statusDiv.className = 'alert alert-success';
        hideLoadingOverlay(); // Hide loading overlay on successful connection
    };

    socket.onclose = function(event) {
        console.log("WebSocket connection closed.", event);
        startSimBtn.disabled = false; // Allow restarting
        stopSimBtn.disabled = true;
        pauseResumeBtn.disabled = true; // Disable pause when not running
        statusDiv.textContent = 'Disconnected. Please refresh or try starting again.';
        statusDiv.className = 'alert alert-danger';
        socket = null; // Reset socket variable
        hideLoadingOverlay(); // Hide loading overlay on close/error
    };

    socket.onerror = function(error) {
        console.error("WebSocket error:", error);
        startSimBtn.disabled = false;
        stopSimBtn.disabled = true;
        pauseResumeBtn.disabled = true; // Disable pause on error
        statusDiv.textContent = 'Connection error. Please check the server and refresh.';
        statusDiv.className = 'alert alert-danger';
        socket = null; // Reset socket variable
        hideLoadingOverlay(); // Hide loading overlay on close/error
    };
}

// ... existing code ...
startSimBtn.addEventListener('click', () => {
    if (socket && socket.readyState === WebSocket.OPEN) {
        // ... existing code ...
        statusDiv.textContent = 'Simulation running...';
        statusDiv.className = 'alert alert-info';
        startSimBtn.disabled = true;
        stopSimBtn.disabled = false;
        pauseResumeBtn.disabled = false; // Enable pause when running
        isPaused = false; // Ensure not paused when starting
        pauseResumeBtn.textContent = 'Pause'; // Set initial text
        // ... existing code ...
    } else {
        // ... existing code ...
    }
});

stopSimBtn.addEventListener('click', () => {
    if (socket && socket.readyState === WebSocket.OPEN) {
        // ... existing code ...
        statusDiv.textContent = 'Simulation stopped by user.';
        statusDiv.className = 'alert alert-warning';
        startSimBtn.disabled = false;
        stopSimBtn.disabled = true;
        pauseResumeBtn.disabled = true; // Disable pause when stopped
        pauseResumeBtn.textContent = 'Pause'; // Reset text
        isPaused = false; // Reset pause state
        // ... existing code ...
    } else {
        // ... existing code ...
    }
});

// Add event listener for the pause/resume button
pauseResumeBtn.addEventListener('click', () => {
    if (socket && socket.readyState === WebSocket.OPEN && !stopSimBtn.disabled) { // Only works if running
        isPaused = !isPaused; // Toggle pause state
        if (isPaused) {
            pauseResumeBtn.textContent = 'Resume';
            statusDiv.textContent = 'Simulation paused.';
            statusDiv.className = 'alert alert-secondary';
            // Optionally disable other controls when paused if needed
            // stopSimBtn.disabled = true;
        } else {
            pauseResumeBtn.textContent = 'Pause';
            statusDiv.textContent = 'Simulation running...';
            statusDiv.className = 'alert alert-info';
            // Re-enable controls if they were disabled
            // stopSimBtn.disabled = false;
        }
    }
});

// Initialize WebSocket connection on page load
document.addEventListener('DOMContentLoaded', () => {
    // ... existing code ...
    connectWebSocket(); // Make sure WebSocket connects on load
});

// Make sure buttons are in the correct initial state
startSimBtn.disabled = true; // Disabled until WebSocket connects
stopSimBtn.disabled = true;
pauseResumeBtn.disabled = true;
// ... existing code ...
// ... existing code ...

// 定期更新图表
setInterval(() => {
    // 只在模拟运行时更新
    if (simulation.running) {
        fetch('/api/grid_status')
            .then(response => response.json())
            .then(data => {
                // 确保数据中包含模拟时间
                if (data && data.simulation_time) {
                    updateGridLoadChart(data);
                } else {
                    console.warn('Grid status data missing simulation time');
                }
            })
            .catch(error => {
                console.error('获取电网状态失败:', error);
            });
    }
}, 5000);

// 页面加载时初始化图表
document.addEventListener('DOMContentLoaded', () => {
    initializeGridLoadChart();
});

// ... existing code ...

// 添加一个简化的时间格式化函数，只显示时:分，不显示日期
function formatSimulationTime(dateStr) {
    try {
        const date = new Date(dateStr);
        if (isNaN(date.getTime())) {
            return "无效时间";
        }
        // 只返回小时和分钟，格式为"HH:MM"
        return `${date.getHours().toString().padStart(2, '0')}:${date.getMinutes().toString().padStart(2, '0')}`;
    } catch (e) {
        console.error('模拟时间格式化错误:', e);
        return "时间错误";
    }
}

// Add metrics data to charts
function addMetricsDataPoint(timestamp, metrics) {
    if (!timestamp || !metrics) {
        console.warn('Missing data for metrics chart update');
        return;
    }
    
    try {
        const dateStr = typeof timestamp === 'string' ? timestamp : timestamp.toISOString();
        // 使用简化的时间格式
        const timeLabel = formatSimulationTime(dateStr);
        
        // Add to history arrays
        simulation.metricsHistory.timestamps.push(timeLabel);
        simulation.metricsHistory.userSatisfaction.push(parseFloat(metrics.user_satisfaction) || 0);
        simulation.metricsHistory.operatorProfit.push(parseFloat(metrics.operator_profit) || 0);
        simulation.metricsHistory.gridFriendliness.push(parseFloat(metrics.grid_friendliness) || 0);
        simulation.metricsHistory.totalReward.push(parseFloat(metrics.total_reward) || 0);
        
        // Keep last 24 hours of data (96 points at 15-min intervals)
        const maxPoints = 96;
        if (simulation.metricsHistory.timestamps.length > maxPoints) {
            simulation.metricsHistory.timestamps.shift();
            simulation.metricsHistory.userSatisfaction.shift();
            simulation.metricsHistory.operatorProfit.shift();
            simulation.metricsHistory.gridFriendliness.shift();
            simulation.metricsHistory.totalReward.shift();
        }
        
        // Update metrics chart
        if (metricsChart) {
            metricsChart.data.labels = simulation.metricsHistory.timestamps;
            metricsChart.data.datasets[0].data = simulation.metricsHistory.userSatisfaction;
            metricsChart.data.datasets[1].data = simulation.metricsHistory.operatorProfit;
            metricsChart.data.datasets[2].data = simulation.metricsHistory.gridFriendliness;
            metricsChart.data.datasets[3].data = simulation.metricsHistory.totalReward;
            metricsChart.update();
        }
    } catch (error) {
        console.error('Error adding metrics data point:', error);
    }
}

// 每5秒更新一次系统状态
setInterval(() => {
    if (document.getElementById('system-status-container')) {
        fetch('/api/system_state')
            .then(response => response.json())
            .then(data => {
                // 检查数据
                if (!data) return;
                
                // 更新系统状态指标
                const metrics = document.getElementById('metrics-overview');
                if (metrics) {
                    // 获取各项指标值并更新
                    const userSatisfaction = data.metrics?.user_satisfaction || 0;
                    const operatorProfit = data.metrics?.operator_profit || 0;
                    const gridFriendliness = data.metrics?.grid_friendliness || 0;
                    const totalScore = data.metrics?.total_reward || 0;
                    
                    document.getElementById('user-satisfaction-value').textContent = userSatisfaction.toFixed(2);
                    document.getElementById('operator-profit-value').textContent = operatorProfit.toFixed(2);
                    document.getElementById('grid-friendliness-value').textContent = gridFriendliness.toFixed(2);
                    document.getElementById('total-score-value').textContent = totalScore.toFixed(2);
                }
                
                // 更新充电站状态
                updateChargingStationsUI(data.charging_stations || []);
            })
            .catch(error => {
                console.error('Error fetching system state:', error);
            });
    }
}, 5000);

// 页面加载时初始化图表
document.addEventListener('DOMContentLoaded', () => {
    initializeGridLoadChart();
});

// End of file