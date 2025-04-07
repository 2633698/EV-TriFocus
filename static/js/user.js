// Global variables
let simulation = {
    running: false,
    history: []
};

// DOM Elements
const startBtn = document.getElementById('btn-start-simulation');
const pauseBtn = document.getElementById('btn-pause-simulation');
const resetBtn = document.getElementById('btn-reset-simulation');
const socProgress = document.getElementById('soc-progress');
const remainingRange = document.getElementById('remaining-range');
const timeSensitivity = document.getElementById('time-sensitivity');
const priceSensitivity = document.getElementById('price-sensitivity');
const rangeAnxiety = document.getElementById('range-anxiety');
const timeSensitivityValue = document.getElementById('time-sensitivity-value');
const priceSensitivityValue = document.getElementById('price-sensitivity-value');
const rangeAnxietyValue = document.getElementById('range-anxiety-value');
const userProfile = document.getElementById('user-profile');
const bookNowBtn = document.getElementById('book-now-btn');

// Initialize the dashboard
document.addEventListener('DOMContentLoaded', function() {
    // Set up event listeners
    setupEventListeners();
    
    // Initialize charts
    initializeCharts();
    
    // Update system time
    updateSystemTime();
    
    // Setup user preferences
    setupUserPreferences();
    
    // Start status update interval
    setInterval(updateSimulationStatus, 1000);
});

// Setup event listeners
function setupEventListeners() {
    // Simulation controls
    startBtn.addEventListener('click', startSimulation);
    pauseBtn.addEventListener('click', pauseSimulation);
    resetBtn.addEventListener('click', resetSimulation);
    
    // User preference sliders
    timeSensitivity.addEventListener('input', updateUserPreferences);
    priceSensitivity.addEventListener('input', updateUserPreferences);
    rangeAnxiety.addEventListener('input', updateUserPreferences);
    
    // Sort and filter
    document.getElementById('sort-method').addEventListener('change', sortRecommendations);
    document.getElementById('filter-method').addEventListener('change', filterRecommendations);
    
    // Book button
    bookNowBtn.addEventListener('click', bookCharging);
    
    // Recommendation selection
    const recommendationButtons = document.querySelectorAll('.recommendation .btn-primary');
    recommendationButtons.forEach(button => {
        button.addEventListener('click', selectCharger);
    });
}

// Initialize charts
function initializeCharts() {
    // User history chart
    const historyChart = document.getElementById('user-history-chart').getContext('2d');
    new Chart(historyChart, {
        type: 'line',
        data: {
            labels: ['12/25', '12/28', '12/29', '1/1', '1/3', '1/5', '1/8'],
            datasets: [{
                label: '充电量 (kWh)',
                data: [25, 48, 32, 35, 28, 42, 38],
                borderColor: '#0d6efd',
                tension: 0.3,
                fill: false
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
                            return `充电量: ${context.raw} kWh`;
                        }
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    title: {
                        display: true,
                        text: '充电量 (kWh)'
                    }
                }
            }
        }
    });
}

// Setup user preferences
function setupUserPreferences() {
    // Set initial values
    timeSensitivityValue.textContent = timeSensitivity.value;
    priceSensitivityValue.textContent = priceSensitivity.value;
    rangeAnxietyValue.textContent = rangeAnxiety.value;
    
    // Update profile
    updateUserProfile();
}

// Update user preferences and profile
function updateUserPreferences() {
    // Update display values
    timeSensitivityValue.textContent = timeSensitivity.value;
    priceSensitivityValue.textContent = priceSensitivity.value;
    rangeAnxietyValue.textContent = rangeAnxiety.value;
    
    // Update profile
    updateUserProfile();
}

// Update user profile based on preferences
function updateUserProfile() {
    const time = parseFloat(timeSensitivity.value);
    const price = parseFloat(priceSensitivity.value);
    const range = parseFloat(rangeAnxiety.value);
    
    if (time >= 0.7 && range >= 0.6) {
        userProfile.textContent = "紧急补电型";
    } else if (price >= 0.7 && time <= 0.4) {
        userProfile.textContent = "经济优先型";
    } else if (time <= 0.5 && price <= 0.5 && range <= 0.5) {
        userProfile.textContent = "平衡考量型";
    } else if (price >= 0.6 && range <= 0.4) {
        userProfile.textContent = "计划充电型";
    } else {
        userProfile.textContent = "普通用户";
    }
}

// Sort recommendations
function sortRecommendations() {
    const sortMethod = document.getElementById('sort-method').value;
    const recommendationsContainer = document.getElementById('recommendations-container');
    const recommendations = Array.from(recommendationsContainer.children);
    
    recommendations.sort((a, b) => {
        if (sortMethod === 'distance') {
            const distanceA = parseFloat(a.querySelector('.fa-map-marker-alt').nextSibling.textContent.trim().replace('公里', ''));
            const distanceB = parseFloat(b.querySelector('.fa-map-marker-alt').nextSibling.textContent.trim().replace('公里', ''));
            return distanceA - distanceB;
        } else if (sortMethod === 'time') {
            const timeA = parseFloat(a.querySelector('.fa-hourglass-half').nextSibling.textContent.trim().replace('约', '').replace('分钟', ''));
            const timeB = parseFloat(b.querySelector('.fa-hourglass-half').nextSibling.textContent.trim().replace('约', '').replace('分钟', ''));
            return timeA - timeB;
        } else if (sortMethod === 'price') {
            const priceA = parseFloat(a.querySelector('.fw-bold').textContent.trim().replace('元', ''));
            const priceB = parseFloat(b.querySelector('.fw-bold').textContent.trim().replace('元', ''));
            return priceA - priceB;
        } else {
            // Composite score (default)
            const scoreA = parseFloat(a.querySelector('.score-indicator').textContent.trim());
            const scoreB = parseFloat(b.querySelector('.score-indicator').textContent.trim());
            return scoreB - scoreA; // Higher score first
        }
    });
    
    // Reorder DOM
    recommendations.forEach(recommendation => {
        recommendationsContainer.appendChild(recommendation);
    });
    
    // Add animation effect
    recommendations.forEach(recommendation => {
        recommendation.classList.add('highlight');
        setTimeout(() => {
            recommendation.classList.remove('highlight');
        }, 1000);
    });
}

// Filter recommendations
function filterRecommendations() {
    const filterMethod = document.getElementById('filter-method').value;
    const recommendationsContainer = document.getElementById('recommendations-container');
    const recommendations = Array.from(recommendationsContainer.children);
    
    recommendations.forEach(recommendation => {
        if (filterMethod === 'all') {
            recommendation.style.display = 'block';
        } else if (filterMethod === 'fast') {
            const isFast = recommendation.querySelector('.badge.bg-primary') !== null;
            recommendation.style.display = isFast ? 'block' : 'none';
        } else if (filterMethod === 'slow') {
            const isSlow = recommendation.querySelector('.badge.bg-secondary') !== null;
            recommendation.style.display = isSlow ? 'block' : 'none';
        } else if (filterMethod === 'wait-10') {
            const waitTime = parseFloat(recommendation.querySelector('.fa-hourglass-half').nextSibling.textContent.trim().replace('约', '').replace('分钟', ''));
            recommendation.style.display = waitTime < 10 ? 'block' : 'none';
        } else if (filterMethod === 'wait-20') {
            const waitTime = parseFloat(recommendation.querySelector('.fa-hourglass-half').nextSibling.textContent.trim().replace('约', '').replace('分钟', ''));
            recommendation.style.display = waitTime < 20 ? 'block' : 'none';
        }
    });
}

// Select charger
function selectCharger(event) {
    // Highlight selected recommendation
    const recommendations = document.querySelectorAll('.recommendation');
    recommendations.forEach(rec => {
        rec.classList.remove('border-primary');
    });
    
    const selected = event.target.closest('.recommendation');
    selected.classList.add('border-primary');
    
    // Update charging details
    const chargerName = selected.querySelector('h5').textContent;
    const chargerLocation = selected.querySelector('.text-muted.small').textContent;
    const chargerType = selected.querySelector('.badge.bg-primary, .badge.bg-secondary').textContent;
    const chargerPrice = selected.querySelector('.fa-yuan-sign').nextSibling.textContent.trim();
    const waitTime = selected.querySelector('.fa-hourglass-half').nextSibling.textContent.trim();
    
    // Update UI with selected charger details
    document.querySelector('.card-body h5').textContent = chargerName;
    document.querySelector('.card-body p.text-muted').textContent = chargerLocation;
    document.querySelector('.d-flex:nth-child(5) strong').textContent = chargerType;
    
    // Show success message
    showNotification('充电站详情已更新', 'success');
}

// Book charging
function bookCharging() {
    // Show booking confirmation
    const bookingModal = new bootstrap.Modal(document.createElement('div'));
    bookingModal._element.innerHTML = `
        <div class="modal-dialog">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title">预约确认</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                </div>
                <div class="modal-body">
                    <div class="alert alert-success">
                        <i class="fas fa-check-circle me-2"></i>
                        预约成功！
                    </div>
                    <p>您已成功预约 <strong>城东快充站</strong> 的充电服务。</p>
                    <p>预计等待时间: <strong>约10分钟</strong></p>
                    <p>预计充电费用: <strong>25.5元</strong></p>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">关闭</button>
                    <button type="button" class="btn btn-primary" data-bs-dismiss="modal">
                        <i class="fas fa-directions me-1"></i>导航前往
                    </button>
                </div>
            </div>
        </div>
    `;
    
    document.body.appendChild(bookingModal._element);
    bookingModal.show();
    
    bookingModal._element.addEventListener('hidden.bs.modal', function() {
        document.body.removeChild(bookingModal._element);
    });
    
    // Add to history
    addChargingHistory();
}

// Add charging to history
function addChargingHistory() {
    const historyList = document.getElementById('charging-history');
    const newItem = document.createElement('li');
    newItem.className = 'list-group-item d-flex justify-content-between align-items-center';
    
    const now = new Date();
    const formattedDate = `${now.getFullYear()}-${(now.getMonth()+1).toString().padStart(2, '0')}-${now.getDate().toString().padStart(2, '0')} ${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}`;
    
    newItem.innerHTML = `
        <div>
            <strong>城东快充站</strong>
            <div class="text-muted small">${formattedDate}</div>
        </div>
        <span>充电30kWh</span>
    `;
    
    // Add to the top of the list
    historyList.insertBefore(newItem, historyList.firstChild);
    
    // Limit history items
    if (historyList.children.length > 5) {
        historyList.removeChild(historyList.lastChild);
    }
    
    // Update monthly stats
    document.getElementById('month-charge-count').textContent = '13次';
    document.getElementById('month-charge-cost').textContent = '¥445';
}

// Start simulation
function startSimulation() {
    // Check if simulation is already running
    if (simulation.running) {
        return;
    }
    
    // Get user preferences
    const time = parseFloat(timeSensitivity.value);
    const price = parseFloat(priceSensitivity.value);
    const range = parseFloat(rangeAnxiety.value);
    
    // Send request to start simulation
    fetch('/api/simulation/start', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            days: 7,
            strategy: 'user', // User perspective uses user-oriented strategy
            use_multi_agent: true,
            user_preferences: {
                time_sensitivity: time,
                price_sensitivity: price,
                range_anxiety: range
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
    
    // Reset SOC
    updateSOC(45);
    
    showNotification('模拟已重置', 'info');
}

// Update SOC and remaining range
function updateSOC(value) {
    // Update SOC progress bar
    socProgress.style.width = `${value}%`;
    socProgress.textContent = `${value}%`;
    socProgress.setAttribute('aria-valuenow', value);
    
    // Update remaining range (assuming 400km max range)
    const range = Math.round((value / 100) * 400);
    remainingRange.textContent = range;
    
    // Change color based on SOC
    if (value < 20) {
        socProgress.className = 'progress-bar bg-danger';
    } else if (value < 40) {
        socProgress.className = 'progress-bar bg-warning';
    } else {
        socProgress.className = 'progress-bar bg-success';
    }
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
                // Get user from state
                const users = data.state.users || [];
                if (users.length > 0) {
                    // Use first user as the example user
                    const user = users[0];
                    
                    // Update SOC
                    updateSOC(user.soc);
                    
                    // Update user info card
                    updateUserInfo(user);
                    
                    // Update recommendations if this is the user view
                    if (typeof updateRecommendations === 'function') {
                        updateRecommendations(users, data.state.chargers || []);
                    }
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

// In user.js, add:

function updateRecommendations() {
    if (!simulation.running) return;
    
    // Get current user
    const userId = document.getElementById('user-id-selector').value || 'USER_0001';
    
    // Get user preferences
    const timeSensitivity = parseFloat(document.getElementById('time-sensitivity').value);
    const priceSensitivity = parseFloat(document.getElementById('price-sensitivity').value);
    const rangeAnxiety = parseFloat(document.getElementById('range-anxiety').value);
    
    // Fetch recommendations
    fetch('/api/user/recommendations', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            user_id: userId,
            preferences: {
                time_sensitivity: timeSensitivity,
                price_sensitivity: priceSensitivity,
                range_anxiety: rangeAnxiety
            }
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'success') {
            // Update user info
            if (data.user) {
                document.getElementById('soc-progress').style.width = `${data.user.soc}%`;
                document.getElementById('soc-progress').textContent = `${Math.round(data.user.soc)}%`;
                document.getElementById('remaining-range').textContent = Math.round(data.user.soc * 4);  // 4km per % SOC
                document.getElementById('user-profile').textContent = data.user.user_profile;
            }
            
            // Update recommendations
            const container = document.getElementById('recommendations-container');
            container.innerHTML = '';
            
            data.recommendations.forEach(recommendation => {
                // Create recommendation card
                const card = document.createElement('div');
                card.className = 'recommendation p-3 mb-3 border rounded';
                
                // Format features list
                const featuresBadges = recommendation.features.map(feature => 
                    `<span class="badge ${getBadgeClass(feature)}">${feature}</span>`
                ).join(' ');
                
                // Colorize score
                let scoreColor = 'bg-success';
                if (recommendation.score < 60) {
                    scoreColor = 'bg-danger';
                } else if (recommendation.score < 80) {
                    scoreColor = 'bg-primary';
                }
                
                card.innerHTML = `
                    <div class="row">
                        <div class="col-md-5">
                            <div class="d-flex align-items-center">
                                <div class="score-indicator ${scoreColor} text-white rounded-circle d-flex align-items-center justify-content-center me-3" style="width: 60px; height: 60px;">
                                    <h3 class="mb-0">${recommendation.score}</h3>
                                </div>
                                <div>
                                    <h5 class="mb-1">${recommendation.location}</h5>
                                    <div class="text-muted small">ID: ${recommendation.charger_id}</div>
                                    <div>
                                        <span class="badge ${recommendation.type === 'fast' ? 'bg-primary' : 'bg-secondary'}">${recommendation.type === 'fast' ? '快充' : '慢充'}</span>
                                        ${featuresBadges}
                                    </div>
                                </div>
                            </div>
                        </div>
                        <div class="col-md-7">
                            <div class="row">
                                <div class="col-4">
                                    <div class="text-center">
                                        <div>
                                            <i class="fas fa-map-marker-alt text-primary"></i>
                                            <span>${recommendation.distance}公里</span>
                                        </div>
                                        <div class="text-muted small">
                                            <i class="fas fa-car"></i>
                                            <span>${Math.round(recommendation.distance * 2)}分钟</span>
                                        </div>
                                    </div>
                                </div>
                                <div class="col-4">
                                    <div class="text-center">
                                        <div>
                                            <i class="fas fa-hourglass-half text-warning"></i>
                                            <span>约${recommendation.waiting_time}分钟</span>
                                        </div>
                                        <div class="text-muted small">
                                            <i class="fas fa-user"></i>
                                            <span>${recommendation.queue_length}人等待</span>
                                        </div>
                                    </div>
                                </div>
                                <div class="col-4">
                                    <div class="text-center">
                                        <div>
                                            <i class="fas fa-bolt text-success"></i>
                                            <span>${recommendation.charging_power}kW</span>
                                        </div>
                                        <div class="text-muted small">
                                            <i class="fas fa-yuan-sign"></i>
                                            <span>${recommendation.price}元/度</span>
                                        </div>
                                    </div>
                                </div>
                            </div>
                            <div class="mt-2">
                                <div class="d-flex justify-content-between align-items-center">
                                    <div>
                                        <span class="text-muted small">充电30度预计</span>
                                        <span class="fw-bold">${recommendation.estimated_cost}元</span>
                                    </div>
                                    <button class="btn btn-sm btn-outline-primary nav-btn">
                                        <i class="fas fa-directions me-1"></i>导航
                                    </button>
                                    <button class="btn btn-sm btn-primary select-btn" data-charger-id="${recommendation.charger_id}">
                                        <i class="fas fa-check me-1"></i>选择此站
                                    </button>
                                </div>
                            </div>
                        </div>
                    </div>
                `;
                
                container.appendChild(card);
                
                // Add click handler for selection
                card.querySelector('.select-btn').addEventListener('click', function() {
                    selectCharger(recommendation);
                });
            });
        }
    });
}

function getBadgeClass(feature) {
    switch(feature) {
        case '低谷电价': return 'bg-success';
        case '有光伏': return 'bg-info';
        case '便利位置': return 'bg-warning';
        default: return 'bg-secondary';
    }
}

// Update recommendations every 5 seconds
setInterval(updateRecommendations, 5000);

// 更新用户信息卡片
function updateUserInfo(user) {
    // 更新用户信息卡片内容
    if (!user) return;
    
    const userInfoCard = document.getElementById('user-info-card');
    if (!userInfoCard) return;
    
    // 查找所有需要更新的元素
    const userIdElem = userInfoCard.querySelector('#user-id');
    const userTypeElem = userInfoCard.querySelector('#user-type');
    const userProfileElem = userInfoCard.querySelector('#user-profile');
    const vehicleTypeElem = userInfoCard.querySelector('#vehicle-type');
    const socElem = userInfoCard.querySelector('#soc');
    const batteryCapacityElem = userInfoCard.querySelector('#battery-capacity');
    const currentRangeElem = userInfoCard.querySelector('#current-range');
    const statusElem = userInfoCard.querySelector('#user-status');
    const locationElem = userInfoCard.querySelector('#user-location');
    const travelInfoElem = userInfoCard.querySelector('#travel-info');
    
    // 更新各项信息
    if (userIdElem) userIdElem.textContent = user.user_id || '未知';
    
    if (userTypeElem) {
        let userTypeText = '未知';
        switch(user.user_type) {
            case 'private': userTypeText = '私家车'; break;
            case 'taxi': userTypeText = '出租车'; break;
            case 'ride_hailing': userTypeText = '网约车'; break;
            case 'logistics': userTypeText = '物流车'; break;
        }
        userTypeElem.textContent = userTypeText;
    }
    
    if (userProfileElem) {
        let profileText = '未知';
        switch(user.user_profile) {
            case 'urgent': profileText = '紧急用户'; break;
            case 'economic': profileText = '经济型用户'; break;
            case 'flexible': profileText = '灵活型用户'; break;
            case 'anxious': profileText = '里程焦虑型'; break;
        }
        userProfileElem.textContent = profileText;
    }
    
    if (vehicleTypeElem) {
        let vehicleText = '未知';
        switch(user.vehicle_type) {
            case 'sedan': vehicleText = '轿车'; break;
            case 'suv': vehicleText = 'SUV'; break;
            case 'compact': vehicleText = '紧凑型'; break;
            case 'luxury': vehicleText = '豪华型'; break;
            case 'truck': vehicleText = '卡车'; break;
        }
        vehicleTypeElem.textContent = vehicleText;
    }
    
    if (socElem && user.soc !== undefined) {
        socElem.textContent = `${user.soc.toFixed(1)}%`;
        
        // 更新电量进度条
        const socProgress = userInfoCard.querySelector('#soc-progress');
        if (socProgress) {
            socProgress.style.width = `${user.soc}%`;
            
            // 根据电量设置颜色
            if (user.soc < 20) {
                socProgress.className = 'progress-bar bg-danger';
            } else if (user.soc < 50) {
                socProgress.className = 'progress-bar bg-warning';
            } else {
                socProgress.className = 'progress-bar bg-success';
            }
        }
    }
    
    if (batteryCapacityElem && user.battery_capacity !== undefined) {
        batteryCapacityElem.textContent = `${user.battery_capacity} kWh`;
    }
    
    if (currentRangeElem && user.current_range !== undefined) {
        currentRangeElem.textContent = `${user.current_range.toFixed(1)} km`;
    }
    
    if (statusElem && user.status) {
        let statusText = '空闲';
        let statusClass = 'text-secondary';
        
        switch(user.status) {
            case 'traveling':
                statusText = '行驶中';
                statusClass = 'text-primary';
                break;
            case 'charging':
                statusText = '充电中';
                statusClass = 'text-success';
                break;
            case 'waiting':
                statusText = '等待中';
                statusClass = 'text-warning';
                break;
        }
        
        statusElem.textContent = statusText;
        statusElem.className = statusClass;
    }
    
    // 更新位置信息
    if (locationElem && user.current_position) {
        const lat = user.current_position.lat.toFixed(4);
        const lng = user.current_position.lng.toFixed(4);
        locationElem.textContent = `(${lat}, ${lng})`;
    }
    
    // 更新行程信息
    if (travelInfoElem) {
        let travelHtml = '';
        
        if (user.status === 'traveling') {
            // 显示目的地信息
            if (user.destination) {
                const destLat = user.destination.lat.toFixed(4);
                const destLng = user.destination.lng.toFixed(4);
                travelHtml += `<div class="mb-2">
                    <i class="fas fa-map-marker-alt text-danger me-1"></i>
                    <strong>目的地:</strong> (${destLat}, ${destLng})
                </div>`;
            }
            
            // 显示已行驶距离
            if (user.traveled_distance !== undefined) {
                travelHtml += `<div class="mb-2">
                    <i class="fas fa-road text-secondary me-1"></i>
                    <strong>已行驶:</strong> ${user.traveled_distance.toFixed(1)} km
                </div>`;
            }
            
            // 显示剩余时间
            if (user.time_to_destination !== undefined) {
                const minutes = Math.floor(user.time_to_destination);
                const seconds = Math.floor((user.time_to_destination - minutes) * 60);
                travelHtml += `<div class="mb-2">
                    <i class="fas fa-clock text-warning me-1"></i>
                    <strong>预计到达:</strong> ${minutes}分${seconds}秒
                </div>`;
            }
            
            // 显示行驶速度
            if (user.travel_speed !== undefined) {
                travelHtml += `<div class="mb-2">
                    <i class="fas fa-tachometer-alt text-primary me-1"></i>
                    <strong>行驶速度:</strong> ${user.travel_speed.toFixed(1)} km/h
                </div>`;
            }
            
            // 路径点信息
            if (user.waypoints && user.waypoints.length > 0) {
                travelHtml += `<div>
                    <i class="fas fa-map text-success me-1"></i>
                    <strong>路径点:</strong> ${user.waypoints.length}个
                </div>`;
            }
        } else if (user.status === 'charging' || user.status === 'waiting') {
            // 显示目标充电桩
            if (user.target_charger) {
                travelHtml += `<div class="mb-2">
                    <i class="fas fa-charging-station text-success me-1"></i>
                    <strong>充电桩:</strong> ${user.target_charger}
                </div>`;
            }
            
            // 如果是等待状态，显示队列信息
            if (user.status === 'waiting') {
                travelHtml += `<div>
                    <i class="fas fa-users text-warning me-1"></i>
                    <strong>等待中</strong>
                </div>`;
            }
        } else {
            travelHtml = '<div class="text-center text-muted py-2">用户当前空闲</div>';
        }
        
        travelInfoElem.innerHTML = travelHtml;
    }
}

// 加载模拟结果时处理用户视图的更新
window.loadSimulationResult = function(filename) {
    fetch(`/api/simulation/result/${filename}`)
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                // 通知用户已加载结果
                showNotification(`已加载模拟结果: ${filename}`, 'success');
                
                // 更新用户信息
                if (data.result.users && data.result.users.length > 0) {
                    const user = data.result.users[0]; // 使用第一个用户作为示例
                    updateSOC(user.soc);
                    updateUserInfo(user);
                    
                    // 更新充电推荐列表
                    if (typeof updateRecommendations === 'function') {
                        updateRecommendations(data.result.users, data.result.chargers || []);
                    }
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