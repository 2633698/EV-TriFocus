// 更新实时电网负载图表
function updateGridLoadChart(data, chartCanvas) {
    // 获取画布上下文
    const ctx = chartCanvas ? chartCanvas.getContext('2d') : document.getElementById('gridLoadChart').getContext('2d');
    const chartId = chartCanvas ? chartCanvas.id : 'gridLoadChart';
    
    // 检查数据存在性
    if (!data || !data.history || !Array.isArray(data.history) || data.history.length === 0) {
        console.error('Invalid data for grid load chart');
        return;
    }
    
    // 提取最新的时间戳和负载数据
    const timestamps = [];
    const baseLoads = [];
    const evLoads = [];
    const totalLoads = [];
    
    // 最多取最近24小时的数据点
    const maxPoints = Math.min(24, data.history.length);
    const historyData = data.history.slice(-maxPoints);
    
    historyData.forEach(point => {
        // 提取时间戳（格式化为小时:分钟）
        let timestamp = '';
        try {
            if (point.timestamp) {
                const date = new Date(point.timestamp);
                timestamp = `${date.getHours()}:${String(date.getMinutes()).padStart(2, '0')}`;
            } else {
                timestamp = 'N/A';
            }
        } catch (e) {
            console.warn('Error parsing timestamp:', e);
            timestamp = 'Error';
        }
        timestamps.push(timestamp);
        
        // 提取电网负载数据
        const gridStatus = point.grid_status || {};
        
        // 获取基础负载（不包括EV负载）
        const baseLoad = gridStatus.current_load || 0;
        
        // 获取EV负载
        const evLoad = gridStatus.ev_load || 0;
        
        // 总负载 = 基础负载 + EV负载
        const totalLoad = gridStatus.grid_load || (baseLoad + evLoad);
        
        baseLoads.push(baseLoad);
        evLoads.push(evLoad);
        totalLoads.push(totalLoad);
    });
    
    // 销毁之前的图表实例（如果存在）
    if (window[`chart_${chartId}`] instanceof Chart) {
        window[`chart_${chartId}`].destroy();
    }
    
    // 创建新的图表
    window[`chart_${chartId}`] = new Chart(ctx, {
        type: 'line',
        data: {
            labels: timestamps,
            datasets: [
                {
                    label: '基础负载',
                    data: baseLoads,
                    backgroundColor: 'rgba(75, 192, 192, 0.2)',
                    borderColor: 'rgba(75, 192, 192, 1)',
                    borderWidth: 2,
                    tension: 0.4,
                    fill: true
                },
                {
                    label: 'EV充电负载',
                    data: evLoads,
                    backgroundColor: 'rgba(255, 99, 132, 0.2)',
                    borderColor: 'rgba(255, 99, 132, 1)',
                    borderWidth: 2,
                    tension: 0.4,
                    fill: true
                },
                {
                    label: '总负载',
                    data: totalLoads,
                    backgroundColor: 'rgba(54, 162, 235, 0.2)',
                    borderColor: 'rgba(54, 162, 235, 1)',
                    borderWidth: 2,
                    tension: 0.4,
                    fill: false
                }
            ]
        },
        options: {
            responsive: true,
            scales: {
                y: {
                    beginAtZero: true,
                    title: {
                        display: true,
                        text: '负载 (kW)'
                    },
                    suggestedMin: 0,
                    suggestedMax: Math.max(10000, Math.max(...totalLoads) * 1.1),
                    ticks: {
                        callback: function(value) {
                            return value.toLocaleString() + ' kW';
                        }
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
                    text: '实时电网负载状况',
                    font: {
                        size: 16
                    }
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return `${context.dataset.label}: ${context.raw.toLocaleString()} kW`;
                        }
                    }
                },
                legend: {
                    position: 'top'
                }
            },
            interaction: {
                intersect: false,
                mode: 'index'
            },
            animation: {
                duration: 500
            }
        }
    });
}

// 更新静态总览图表
function updateGridLoadOverview(data) {
    const ctx = document.getElementById('gridLoadChart').getContext('2d');
    
    // 检查数据存在性
    if (!data || !data.history || !Array.isArray(data.history) || data.history.length === 0) {
        console.error('Invalid data for grid load overview');
        return;
    }
    
    // 按天对数据进行分组
    const dailyData = {};
    data.history.forEach(point => {
        try {
            const date = new Date(point.timestamp);
            const dayKey = date.toISOString().split('T')[0];
            if (!dailyData[dayKey]) {
                dailyData[dayKey] = {
                    baseLoads: Array(24).fill(0),
                    evLoads: Array(24).fill(0),
                    totalLoads: Array(24).fill(0),
                    counts: Array(24).fill(0)
                };
            }
            
            const hour = date.getHours();
            const gridStatus = point.grid_status || {};
            
            dailyData[dayKey].baseLoads[hour] += gridStatus.current_load || 0;
            dailyData[dayKey].evLoads[hour] += gridStatus.ev_load || 0;
            dailyData[dayKey].totalLoads[hour] += gridStatus.grid_load || 0;
            dailyData[dayKey].counts[hour]++;
        } catch (e) {
            console.warn('Error processing data point:', e);
        }
    });
    
    // 计算每小时的平均值
    const hours = Array.from({length: 24}, (_, i) => `${i}:00`);
    const avgBaseLoads = Array(24).fill(0);
    const avgEvLoads = Array(24).fill(0);
    const avgTotalLoads = Array(24).fill(0);
    
    Object.values(dailyData).forEach(day => {
        for (let i = 0; i < 24; i++) {
            if (day.counts[i] > 0) {
                avgBaseLoads[i] += day.baseLoads[i] / day.counts[i];
                avgEvLoads[i] += day.evLoads[i] / day.counts[i];
                avgTotalLoads[i] += day.totalLoads[i] / day.counts[i];
            }
        }
    });
    
    const daysCount = Object.keys(dailyData).length;
    if (daysCount > 0) {
        for (let i = 0; i < 24; i++) {
            avgBaseLoads[i] /= daysCount;
            avgEvLoads[i] /= daysCount;
            avgTotalLoads[i] /= daysCount;
        }
    }
    
    // 销毁之前的图表实例
    if (window.gridLoadOverview instanceof Chart) {
        window.gridLoadOverview.destroy();
    }
    
    // 创建新的总览图表
    window.gridLoadOverview = new Chart(ctx, {
        type: 'line',
        data: {
            labels: hours,
            datasets: [
                {
                    label: '平均基础负载',
                    data: avgBaseLoads,
                    backgroundColor: 'rgba(75, 192, 192, 0.2)',
                    borderColor: 'rgba(75, 192, 192, 1)',
                    borderWidth: 2,
                    tension: 0.4,
                    fill: true
                },
                {
                    label: '平均EV充电负载',
                    data: avgEvLoads,
                    backgroundColor: 'rgba(255, 99, 132, 0.2)',
                    borderColor: 'rgba(255, 99, 132, 1)',
                    borderWidth: 2,
                    tension: 0.4,
                    fill: true
                },
                {
                    label: '平均总负载',
                    data: avgTotalLoads,
                    backgroundColor: 'rgba(54, 162, 235, 0.2)',
                    borderColor: 'rgba(54, 162, 235, 1)',
                    borderWidth: 2,
                    tension: 0.4,
                    fill: false
                }
            ]
        },
        options: {
            responsive: true,
            scales: {
                y: {
                    beginAtZero: true,
                    title: {
                        display: true,
                        text: '负载 (kW)'
                    },
                    suggestedMin: 0,
                    suggestedMax: Math.max(10000, Math.max(...avgTotalLoads) * 1.1),
                    ticks: {
                        callback: function(value) {
                            return value.toLocaleString() + ' kW';
                        }
                    }
                },
                x: {
                    title: {
                        display: true,
                        text: '时间 (小时)'
                    }
                }
            },
            plugins: {
                title: {
                    display: true,
                    text: '日均电网负载分布',
                    font: {
                        size: 16
                    }
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return `${context.dataset.label}: ${context.raw.toLocaleString()} kW`;
                        }
                    }
                },
                legend: {
                    position: 'top'
                }
            },
            interaction: {
                intersect: false,
                mode: 'index'
            }
        }
    });
} 