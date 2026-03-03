# 🟢 开发进度追踪

**当前焦点**: 信号扫描系统

## 已实现模块

| 模块 | 状态 | 说明 |
|------|------|------|
| [突破扫描模块](../modules/specs/02_突破扫描模块_IMPL.md) | ✅ 已实现 | 凸点识别、突破检测、质量评分 |
| [交互式UI](../modules/specs/12_交互式UI_IMPL.md) | ✅ 已实现 | 批量扫描、交互浏览、参数调整、符号筛选 |
| [Simple Pool](../modules/specs/14_Simple_Pool_IMPL.md) | ✅ 已实现 | MVP 即时判断模型，4 核心参数 |
| [绝对信号系统](../modules/specs/15_绝对信号系统_IMPL.md) | ✅ 已实现 | 4 种信号检测 (B/V/Y/D)，按数量排序 |
| [联合信号判断系统](../modules/specs/16_联合信号判断系统_IMPL.md) | ✅ 已实现 | 加权强度 (pk_num/tr_num) + 异常走势过滤 (amplitude) |

> *详细设计文档请查阅 `docs/modules/specs/`*

---

## 最新更新 (2026-02-06)

### 联合信号系统 Level 1
- 新增 `signals/composite.py`：加权强度计算、序列标签生成、异常走势检测
- `SignalStats` 扩展：weighted_sum / sequence_label / amplitude / turbulent
- 排序改为按 weighted_sum 降序（替代原 signal_count）
- 异常走势检测：lookback 窗口内价格振幅 >= 80% 时，仅 D 信号计入加权

---

## 最新更新 (2026-02-03)

### UI 模块增强
- 新增 `SymbolFilterPanel`：6 checkbox 控制图表符号显示 (B/V/Y/D/Peak/Trough)
- 新增 `NavigationManager`：全局键盘导航 (↑/↓/Enter)
- 新增 `RescanModeDialog`：Rescan 模式选择（覆盖/新建）
- 新增 `ColumnConfigDialog`：股票列表列配置
- 配置管理子系统：参数加载器、状态管理器、YAML 注释保留

### 信号检测系统增强
- **双底检测器 (DoubleTroughDetector)** 替代原 VReversalDetector
  - 增加反弹约束：TR1 后必须有 ≥10% 反弹
  - 结构更清晰：TR1（绝对底）→ 反弹 → TR2（次底确认）
- 新增 `scan_single_stock()` 公共 API：UI 分析模式与批量扫描共享检测逻辑
- 支撑分析集成：B/D 信号填充 `support_status`

---

## 历史更新 (2026-01-23)

### 配置文件迁移
- 将 `display_config.yaml` 和 `ui_config.yaml` 移动到 `configs/signals/` 目录
- 统一信号系统相关配置的存放位置
- 配置文件现位于 `configs/signals/` 下：
  - `absolute_signals.yaml` - 信号检测器参数
  - `ui_config.yaml` - UI 布局配置
  - `display_config.yaml` - K线图表显示范围

### 文档更新
- 更新信号系统实现文档（15_绝对信号系统_IMPL.md）
- 更新 UI 模块实现文档（12_交互式UI_IMPL.md）
- 文档反映最新的配置文件位置和架构

---

## 历史更新 (2026-01-09)

### Scan Configuration 股票筛选条件
- 在 UI 扫描配置中新增股票筛选条件（仅 Global Time Range 模式有效）
- `min_price` / `max_price`：价格范围限制
- `min_volume`：最小平均成交量限制
- 不满足条件的股票在扫描阶段直接跳过

---

## 历史更新 (2026-01-08)

### Simple Pool MVP 版本
- 新增独立的 MVP 观察池 `BreakoutStrategy/simple_pool/`
- 即时判断模型：无状态机，三条件并行检查
- 仅 4 个核心参数（vs 旧系统 29 个）
- 简化支撑位检测：`min(low[-N:])`

---

## 历史更新 (2026-01-01)

### 文档整合
- 更新三大核心模块的实现文档（突破扫描、UI、观察池）
- 添加观察池四维评估系统的完整架构说明

### UI 观察池集成
- "Add to Pool" 按钮
- 懒加载设计，按需初始化观察池管理器