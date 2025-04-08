// 更新电网负载图表
function updateGridLoadChart(data) {
    const gridLoadCtx = document.getElementById('gridLoadChart').getContext('2d');
    
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
        
        // 获取EV负载（确保存在）
        const evLoad = gridStatus.ev_load || 0; // 移除0.2系数,显示实际负载
        
        // 总负载 = 基础负载 + EV负载
        const totalLoad = baseLoad + evLoad;
        
        baseLoads.push(baseLoad);
        evLoads.push(evLoad);
        totalLoads.push(totalLoad);
    });
    
    // 销毁之前的图表实例（如果存在）
    if (window.gridLoadChart instanceof Chart) {
        window.gridLoadChart.destroy();
    }
    
    // 创建新的图表
    window.gridLoadChart = new Chart(gridLoadCtx, {
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
                    // 动态计算y轴最大值
                    suggestedMax: Math.max(...totalLoads) * 1.1
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
                    text: '电网负载状况',
                    font: {
                        size: 16
                    }
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return `${context.dataset.label}: ${context.raw.toFixed(2)} kW`;
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