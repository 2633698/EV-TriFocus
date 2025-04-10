/**
 * 电网负载图表模块
 * 负责处理电网负载数据的图表展示
 */

const gridCharts = {
    loadChart: null,
    chartData: {
        timestamps: [],
        baseLoads: [],
        evLoads: [],
        totalLoads: []
    },
    
    /**
     * 初始化电网负载图表
     */
    initLoadChart: function() {
        try {
            const ctx = document.getElementById('main-grid-load-chart');
            if (!ctx) {
                console.error('无法找到网格负载图表元素 #main-grid-load-chart');
                return;
            }
            
            console.log('正在初始化电网负载图表...');
            
            // 如果已经存在图表实例，先销毁它
            if (this.loadChart) {
                console.log('销毁现有图表实例');
                this.loadChart.destroy();
                this.loadChart = null;
            }
            
            // 清空图表数据
            this.chartData.timestamps = [];
            this.chartData.baseLoads = [];
            this.chartData.evLoads = [];
            this.chartData.totalLoads = [];
            
            // 创建新图表
            this.loadChart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [
                        {
                            label: '基础负载',
                            data: [],
                            borderColor: 'rgba(75, 192, 192, 1)',
                            backgroundColor: 'rgba(75, 192, 192, 0.2)',
                            borderWidth: 2,
                            fill: true
                        },
                        {
                            label: 'EV充电负载',
                            data: [],
                            borderColor: 'rgba(255, 159, 64, 1)',
                            backgroundColor: 'rgba(255, 159, 64, 0.2)',
                            borderWidth: 2,
                            fill: true
                        },
                        {
                            label: '总负载',
                            data: [],
                            borderColor: 'rgba(54, 162, 235, 1)',
                            backgroundColor: 'rgba(54, 162, 235, 0.2)',
                            borderWidth: 2,
                            fill: false
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        x: {
                            title: {
                                display: true,
                                text: '时间'
                            }
                        },
                        y: {
                            beginAtZero: true,
                            title: {
                                display: true,
                                text: '负载 (kW)'
                            },
                            suggestedMin: 0,
                            suggestedMax: 10000
                        }
                    },
                    plugins: {
                        title: {
                            display: true,
                            text: '电网负载监控',
                            font: {
                                size: 16,
                                weight: 'bold'
                            }
                        },
                        tooltip: {
                            mode: 'index',
                            intersect: false,
                            callbacks: {
                                label: function(context) {
                                    let label = context.dataset.label || '';
                                    if (label) {
                                        label += ': ';
                                    }
                                    if (context.parsed.y !== null) {
                                        label += context.parsed.y.toLocaleString() + ' kW';
                                    }
                                    return label;
                                }
                            }
                        },
                        legend: {
                            position: 'top',
                            labels: {
                                font: {
                                    size: 12
                                }
                            }
                        }
                    }
                }
            });
            
            console.log('电网负载图表已初始化');
            return this.loadChart;
        } catch (error) {
            console.error('初始化电网负载图表时发生错误:', error);
            return null;
        }
    },
    
    /**
     * 添加数据点到图表
     * @param {string} timestamp - 时间戳
     * @param {number} baseLoad - 基础负载
     * @param {number} evLoad - EV充电负载
     * @param {number} totalLoad - 总负载
     */
    addDataPoint: function(timestamp, baseLoad, evLoad, totalLoad) {
        try {
            if (!this.loadChart) {
                console.warn('图表未初始化，正在初始化...');
                this.initLoadChart();
                if (!this.loadChart) {
                    console.error('图表初始化失败，无法添加数据点');
                    return;
                }
            }
            
            // 确保参数是有效的数字
            baseLoad = parseFloat(baseLoad) || 0;
            evLoad = parseFloat(evLoad) || 0;
            
            // 如果totalLoad未提供，则计算总负载
            if (isNaN(totalLoad)) {
                totalLoad = baseLoad + evLoad;
            } else {
                totalLoad = parseFloat(totalLoad);
            }
            
            // 格式化时间戳为可读格式
            let formattedTime;
            try {
                if (timestamp && typeof timestamp === 'string') {
                    const date = new Date(timestamp);
                    formattedTime = `${date.getHours()}:${String(date.getMinutes()).padStart(2, '0')}`;
                } else {
                    const now = new Date();
                    formattedTime = `${now.getHours()}:${String(now.getMinutes()).padStart(2, '0')}`;
                }
            } catch (e) {
                console.warn(`无法解析时间戳: ${timestamp}, 使用当前时间`);
                const now = new Date();
                formattedTime = `${now.getHours()}:${String(now.getMinutes()).padStart(2, '0')}`;
            }
            
            // 添加到数据存储
            this.chartData.timestamps.push(formattedTime);
            this.chartData.baseLoads.push(baseLoad);
            this.chartData.evLoads.push(evLoad);
            this.chartData.totalLoads.push(totalLoad);
            
            // 保持最多显示24小时的数据（假设5分钟一个数据点，即288个点）
            const maxPoints = 288;
            if (this.chartData.timestamps.length > maxPoints) {
                this.chartData.timestamps.shift();
                this.chartData.baseLoads.shift();
                this.chartData.evLoads.shift();
                this.chartData.totalLoads.shift();
            }
            
            // 更新图表
            this.updateChart();
            
            console.log(`已添加新数据点: 时间=${formattedTime}, 基础负载=${baseLoad}, EV负载=${evLoad}, 总负载=${totalLoad}`);
        } catch (error) {
            console.error('添加数据点时出错:', error.message);
            console.error('错误堆栈:', error.stack);
        }
    },
    
    /**
     * 批量添加历史数据
     * @param {Array} historicalData - 历史数据数组
     */
    addHistoricalData: function(historicalData) {
        if (!this.loadChart) {
            console.warn('图表未初始化，正在初始化...');
            this.initLoadChart();
        }
        
        if (!historicalData) {
            console.error('历史数据为空');
            return;
        }
        
        if (!Array.isArray(historicalData)) {
            console.error('历史数据格式无效(不是数组):', typeof historicalData);
            return;
        }
        
        if (historicalData.length === 0) {
            console.warn('历史数据数组为空');
            return;
        }
        
        console.log('添加历史数据:', historicalData.length, '个数据点');
        console.log('第一条历史数据示例:', JSON.stringify(historicalData[0]).substring(0, 200) + '...');
        
        try {
            // 清空现有数据
            this.chartData.timestamps = [];
            this.chartData.baseLoads = [];
            this.chartData.evLoads = [];
            this.chartData.totalLoads = [];
            
            // 添加历史数据
            let validPoints = 0;
            let invalidPoints = 0;
            
            historicalData.forEach((dataPoint, index) => {
                if (!dataPoint) {
                    console.warn(`数据点 #${index} 为空`);
                    invalidPoints++;
                    return;
                }
                
                // 检查timestamp字段
                if (!dataPoint.timestamp) {
                    console.warn(`数据点 #${index} 缺少时间戳:`, dataPoint);
                    invalidPoints++;
                    return;
                }
                
                try {
                    // 尝试格式化时间戳
                    let formattedTime;
                    try {
                        formattedTime = new Date(dataPoint.timestamp).toLocaleTimeString();
                    } catch (e) {
                        console.warn(`无法解析时间戳: ${dataPoint.timestamp}, 使用索引替代`);
                        formattedTime = `时间点${index+1}`;
                    }
                    
                    // 提取负载数据，根据不同的数据格式进行处理
                    let baseLoad = 0;
                    let evLoad = 0;
                    let totalLoad = 0;
                    
                    // 处理不同的数据结构
                    if (dataPoint.grid_status) {
                        // 嵌套的grid_status结构
                        baseLoad = dataPoint.grid_status.current_load || 0;
                        evLoad = dataPoint.grid_status.ev_load || 0;
                        totalLoad = dataPoint.grid_status.grid_load || 0;
                    } else {
                        // 直接的负载数据
                        baseLoad = dataPoint.base_load || dataPoint.current_load || 0;
                        evLoad = dataPoint.ev_load || 0;
                        totalLoad = dataPoint.grid_load || 0;
                    }
                    
                    // 确保总负载至少等于基础负载加EV负载
                    if (totalLoad < baseLoad + evLoad) {
                        totalLoad = baseLoad + evLoad;
                    }
                    
                    // 添加格式化后的数据点到图表数据
                    this.chartData.timestamps.push(formattedTime);
                    this.chartData.baseLoads.push(baseLoad);
                    this.chartData.evLoads.push(evLoad);
                    this.chartData.totalLoads.push(totalLoad);
                    
                    // 每10个点记录一次详细信息，避免日志过多
                    if (index % 10 === 0 || index === 0 || index === historicalData.length - 1) {
                        console.log(`数据点 #${index}: 时间=${formattedTime}, 基础负载=${baseLoad}, EV负载=${evLoad}, 总负载=${totalLoad}`);
                    }
                    
                    validPoints++;
                } catch (error) {
                    console.error(`处理数据点 #${index} 时出错:`, error.message);
                    console.error('数据点内容:', JSON.stringify(dataPoint).substring(0, 100));
                    invalidPoints++;
                }
            });
            
            // 打印处理结果
            console.log(`历史数据处理完成: ${validPoints}个有效点, ${invalidPoints}个无效点`);
            
            if (validPoints === 0) {
                console.error('没有有效的数据点，图表无法更新');
                return;
            }
            
            // 限制数据点数量，保留最新的数据
            const maxPoints = 288; // 24小时，每5分钟一个点
            if (this.chartData.timestamps.length > maxPoints) {
                const excess = this.chartData.timestamps.length - maxPoints;
                this.chartData.timestamps = this.chartData.timestamps.slice(excess);
                this.chartData.baseLoads = this.chartData.baseLoads.slice(excess);
                this.chartData.evLoads = this.chartData.evLoads.slice(excess);
                this.chartData.totalLoads = this.chartData.totalLoads.slice(excess);
                console.log(`截断了${excess}个早期数据点，保留最新的${maxPoints}个点`);
            }
            
            // 输出最终使用的数据点范围
            if (this.chartData.timestamps.length > 0) {
                const firstTime = this.chartData.timestamps[0];
                const lastTime = this.chartData.timestamps[this.chartData.timestamps.length - 1];
                console.log(`图表数据点范围: ${firstTime} 至 ${lastTime}`);
            }
            
            // 更新图表
            this.updateChart();
            
            // 强制重绘图表DOM
            setTimeout(() => {
                if (this.loadChart) {
                    console.log('执行延迟更新...');
                    this.loadChart.update('none');
                }
            }, 100);
        } catch (error) {
            console.error('处理历史数据时发生错误:', error.message);
            console.error('错误堆栈:', error.stack);
            
            // 尝试恢复，至少显示一个数据点
            try {
                // 添加一个示例数据点
                const now = new Date();
                const formattedNow = now.toLocaleTimeString();
                this.chartData.timestamps = [formattedNow];
                this.chartData.baseLoads = [5000];
                this.chartData.evLoads = [1000];
                this.chartData.totalLoads = [6000];
                
                console.log('添加应急数据点');
                this.updateChart();
            } catch (recoveryError) {
                console.error('恢复失败:', recoveryError);
            }
        }
    },
    
    /**
     * 更新图表显示
     */
    updateChart: function() {
        if (!this.loadChart) {
            console.error('图表未初始化');
            this.initLoadChart(); // 尝试初始化图表
            if (!this.loadChart) {
                console.error('图表初始化失败，无法更新');
                return;
            }
        }
        
        try {
            // 检查数据是否有效
            if (!this.chartData.timestamps || this.chartData.timestamps.length === 0) {
                console.warn('没有有效的时间戳数据，无法更新图表');
                return;
            }
            
            // 数据长度检查和日志
            const timestampLength = this.chartData.timestamps.length;
            const baseLoadsLength = this.chartData.baseLoads.length;
            const evLoadsLength = this.chartData.evLoads.length;
            const totalLoadsLength = this.chartData.totalLoads.length;
            
            if (timestampLength !== baseLoadsLength || 
                timestampLength !== evLoadsLength || 
                timestampLength !== totalLoadsLength) {
                console.warn(`数据长度不一致: 时间戳=${timestampLength}, 基础负载=${baseLoadsLength}, EV负载=${evLoadsLength}, 总负载=${totalLoadsLength}`);
                // 尝试修复不一致的数据长度
                const minLength = Math.min(timestampLength, baseLoadsLength, evLoadsLength, totalLoadsLength);
                this.chartData.timestamps = this.chartData.timestamps.slice(0, minLength);
                this.chartData.baseLoads = this.chartData.baseLoads.slice(0, minLength);
                this.chartData.evLoads = this.chartData.evLoads.slice(0, minLength);
                this.chartData.totalLoads = this.chartData.totalLoads.slice(0, minLength);
            }
            
            // 打印图表数据概述
            console.log(`正在更新图表，使用${this.chartData.timestamps.length}个数据点`);
            if (this.chartData.timestamps.length > 0) {
                console.log(`数据范围: ${this.chartData.timestamps[0]} 至 ${this.chartData.timestamps[this.chartData.timestamps.length-1]}`);
                console.log(`基础负载范围: ${Math.min(...this.chartData.baseLoads)} - ${Math.max(...this.chartData.baseLoads)} kW`);
                console.log(`EV负载范围: ${Math.min(...this.chartData.evLoads)} - ${Math.max(...this.chartData.evLoads)} kW`);
                console.log(`总负载范围: ${Math.min(...this.chartData.totalLoads)} - ${Math.max(...this.chartData.totalLoads)} kW`);
                
                // 打印部分数据样本
                console.log("数据样本(前5条):");
                for (let i = 0; i < Math.min(5, this.chartData.timestamps.length); i++) {
                    console.log(`[${i}] 时间=${this.chartData.timestamps[i]}, 基础负载=${this.chartData.baseLoads[i]}, EV负载=${this.chartData.evLoads[i]}, 总负载=${this.chartData.totalLoads[i]}`);
                }
            }
            
            // 确保chartjs实例已正确配置
            if (!this.loadChart.data || !this.loadChart.data.datasets || this.loadChart.data.datasets.length < 3) {
                console.error('图表数据结构不正确，重新初始化图表');
                this.resetChart();
                return;
            }
            
            // 更新图表数据
            this.loadChart.data.labels = this.chartData.timestamps;
            this.loadChart.data.datasets[0].data = this.chartData.baseLoads;
            this.loadChart.data.datasets[1].data = this.chartData.evLoads;
            this.loadChart.data.datasets[2].data = this.chartData.totalLoads;
            
            // 调整Y轴范围，确保所有数据可见
            const maxLoad = Math.max(...this.chartData.totalLoads, 10000);  // 最小10000kW，避免空数据时显示异常
            this.loadChart.options.scales.y.max = Math.ceil(maxLoad * 1.1 / 1000) * 1000;  // 向上取整到千，并增加10%余量
            
            // 强制更新图表
            this.loadChart.update('active');
            console.log('图表更新成功');
        } catch (error) {
            console.error('更新图表时发生错误:', error);
            console.error('错误详情:', error.stack);
            
            // 尝试恢复
            this.resetChart();
        }
    },
    
    /**
     * 重置图表
     */
    resetChart: function() {
        if (this.loadChart) {
            this.loadChart.destroy();
            this.loadChart = null;
        }
        
        this.chartData.timestamps = [];
        this.chartData.baseLoads = [];
        this.chartData.evLoads = [];
        this.chartData.totalLoads = [];
        
        this.initLoadChart();
        console.log('电网负载图表已重置');
    }
};

// 页面加载完成后初始化图表
document.addEventListener('DOMContentLoaded', function() {
    console.log('DOM加载完成，正在初始化电网负载图表...');
    
    // 确保gridCharts对象在全局可用
    window.gridCharts = gridCharts;
    
    // 初始化图表
    gridCharts.initLoadChart();
    
    // 设置定期更新
    setInterval(() => {
        fetch('/api/grid')
            .then(response => response.json())
            .then(data => {
                if (data && data.grid_status) {
                    const currentTime = new Date().toISOString();
                    const baseLoad = data.grid_status.current_load || 0;
                    const evLoad = data.grid_status.ev_load || 0;
                    const totalLoad = data.grid_status.grid_load || (baseLoad + evLoad);
                    
                    gridCharts.addDataPoint(currentTime, baseLoad, evLoad, totalLoad);
                    
                    // 更新实时负载指标
                    const totalLoadElement = document.getElementById('totalLoad');
                    const evLoadElement = document.getElementById('evLoad');
                    const renewableRatioElement = document.getElementById('renewableRatio');
                    
                    if (totalLoadElement) {
                        totalLoadElement.textContent = `${Math.round(totalLoad).toLocaleString()} kW`;
                    }
                    if (evLoadElement) {
                        evLoadElement.textContent = `${Math.round(evLoad).toLocaleString()} kW`;
                    }
                    if (renewableRatioElement) {
                        renewableRatioElement.textContent = 
                            `${Math.round((data.grid_status.renewable_ratio || 0) * 100)}%`;
                    }
                }
            })
            .catch(error => {
                console.error('获取电网数据失败:', error);
            });
    }, 5000);
    
    console.log('Grid Charts 模块已初始化并暴露到全局 window.gridCharts');
}); 