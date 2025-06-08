# EV充电仿真系统性能优化指南

## 概述

本指南介绍了为解决程序卡死问题而实施的性能优化措施，以及如何根据您的系统配置进行调整。

## 已实施的性能优化

### 1. UI更新频率控制

**问题**: 过于频繁的UI更新导致界面卡顿

**解决方案**:
- 添加了200ms的最小更新间隔限制
- 实施选择性UI更新策略（每3次更新中跳过2次重量级更新）
- 将日志级别从info降低为debug，减少日志输出开销

**配置位置**: `ev_charging_gui.py` 中的 `update_throttle_ms` 和 `ui_update_skip_interval`

### 2. 定时器优化

**优化前后对比**:
- 高级图表更新: 500ms → 1000ms
- 运营商面板更新: 5000ms → 8000ms
- 主显示更新: 保持1000ms
- 行程信息更新: 保持2000ms

### 3. 内存管理优化

**新增功能**:
- 自动垃圾回收: 每30秒执行一次
- 历史数据限制: 最多保存1000条记录
- 图表显示点数限制: 最多显示15个数据点

### 4. 条件性更新策略

**重量级操作**（仅在满足条件时执行）:
- 地图数据更新
- 数据表更新
- 区域负载图表更新
- 区域热力图更新
- 运营商面板更新
- 算法比较图表更新

**轻量级操作**（每次都执行）:
- 时间显示更新
- 基本状态更新

## 性能配置文件

### performance_config.json

该文件包含所有性能相关的配置参数：

```json
{
  "performance_optimization": {
    "ui_update_settings": {
      "update_throttle_ms": 200,
      "ui_update_skip_interval": 3
    },
    "timer_intervals": {
      "main_display_timer_ms": 1000,
      "advanced_charts_timer_ms": 1000,
      "operator_panel_timer_ms": 8000,
      "trip_info_timer_ms": 2000
    }
  }
}
```

## 性能监控工具

### performance_monitor.py

新增的性能监控工具可以帮助您：
- 实时监控CPU和内存使用情况
- 跟踪系统性能趋势
- 识别性能瓶颈
- 提供性能警告

**使用方法**:
```python
from performance_monitor import PerformanceWidget

# 在主窗口中添加性能监控组件
performance_widget = PerformanceWidget()
```

## 根据系统配置调整

### 低配置系统（4GB RAM, 双核CPU）

建议调整以下参数：
```python
self.update_throttle_ms = 500  # 增加到500ms
self.ui_update_skip_interval = 5  # 增加跳过间隔
```

定时器间隔增加50%：
- 高级图表: 1500ms
- 运营商面板: 12000ms

### 高配置系统（16GB+ RAM, 8核+ CPU）

可以适当降低限制以获得更流畅的体验：
```python
self.update_throttle_ms = 100  # 降低到100ms
self.ui_update_skip_interval = 2  # 减少跳过间隔
```

### 中等配置系统（8GB RAM, 4核CPU）

使用默认配置即可，或根据实际运行情况微调。

## 故障排除

### 程序仍然卡顿

1. **增加更新间隔**:
   ```python
   self.update_throttle_ms = 400  # 从200ms增加到400ms
   ```

2. **减少UI更新频率**:
   ```python
   self.ui_update_skip_interval = 5  # 从3增加到5
   ```

3. **禁用某些图表**:
   - 临时注释掉重量级图表更新代码
   - 减少同时显示的数据可视化组件

### 界面更新太慢

1. **减少更新间隔**:
   ```python
   self.update_throttle_ms = 100  # 从200ms减少到100ms
   ```

2. **增加UI更新频率**:
   ```python
   self.ui_update_skip_interval = 2  # 从3减少到2
   ```

### 内存占用过高

1. **减少历史数据保存**:
   ```python
   max_history = 500  # 从1000减少到500
   ```

2. **增加垃圾回收频率**:
   ```python
   self.gc_timer.start(15000)  # 从30秒减少到15秒
   ```

## 性能监控指标

### 正常运行指标
- CPU使用率: < 60%
- 内存使用: < 1GB
- UI响应时间: < 200ms

### 警告指标
- CPU使用率: 60-80%
- 内存使用: 1-2GB
- UI响应时间: 200-500ms

### 危险指标
- CPU使用率: > 80%
- 内存使用: > 2GB
- UI响应时间: > 500ms

## 进一步优化建议

### 代码层面
1. **异步处理**: 将重量级计算移到后台线程
2. **数据缓存**: 实施智能数据缓存策略
3. **懒加载**: 仅在需要时加载和更新组件

### 架构层面
1. **模块化**: 将不同功能模块解耦
2. **事件驱动**: 使用事件驱动架构减少轮询
3. **数据流优化**: 优化数据传递和处理流程

## 联系支持

如果在使用过程中遇到性能问题，请：
1. 检查性能监控数据
2. 尝试调整配置参数
3. 记录具体的错误信息和系统配置
4. 联系技术支持团队

---

**注意**: 性能优化是一个持续的过程，建议根据实际使用情况和系统反馈不断调整配置参数。