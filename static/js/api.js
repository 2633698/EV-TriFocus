const API = {
    // 获取系统状态
    getStatus: async function() {
        try {
            const response = await fetch('/api/status');
            return await response.json();
        } catch (error) {
            console.error('获取状态失败:', error);
            return null;
        }
    },
    
    // 获取系统配置
    getConfig: async function() {
        try {
            const response = await fetch('/api/config');
            return await response.json();
        } catch (error) {
            console.error('获取配置失败:', error);
            return null;
        }
    },
    
    // 运行任务
    runTask: async function(mode, params) {
        try {
            const response = await fetch('/api/run', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    mode: mode,
                    params: params
                }),
            });
            return await response.json();
        } catch (error) {
            console.error('运行任务失败:', error);
            return null;
        }
    },
    
    // 获取充电桩状态
    getChargers: async function() {
        try {
            const response = await fetch('/api/chargers');
            return await response.json();
        } catch (error) {
            console.error('获取充电桩状态失败:', error);
            return null;
        }
    },
    
    // 获取用户状态
    getUsers: async function() {
        try {
            const response = await fetch('/api/users');
            return await response.json();
        } catch (error) {
            console.error('获取用户状态失败:', error);
            return null;
        }
    },
    
    // 获取电网状态
    getGrid: async function() {
        try {
            const response = await fetch('/api/grid');
            return await response.json();
        } catch (error) {
            console.error('获取电网状态失败:', error);
            return null;
        }
    },
    
    // 获取调度决策
    getDecisions: async function() {
        try {
            const response = await fetch('/api/decisions');
            return await response.json();
        } catch (error) {
            console.error('获取调度决策失败:', error);
            return null;
        }
    },
    // 获取用户分析数据
    getUserAnalysis: async function() {
        try {
            const response = await fetch('/api/user-analysis');
            return await response.json();
        } catch (error) {
            console.error('获取用户分析数据失败:', error);
            return null;
        }
    },

    // 获取电网分析数据
    getGridAnalysis: async function() {
        try {
            const response = await fetch('/api/grid-analysis');
            return await response.json();
        } catch (error) {
            console.error('获取电网分析数据失败:', error);
            return null;
        }
    }
};

