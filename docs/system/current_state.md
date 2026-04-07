# 🟢 开发进度追踪

**当前焦点**: Simple Pool MVP 版本

## 进度概览
- [x] [02 突破扫描模块](../modules/specs/02_突破扫描模块_IMPL.md) (已实现 - 2026-03-13 更新：因子计算重构+pre_vol因子)
- [x] [12 交互式UI](../modules/specs/12_交互式UI_IMPL.md) (已实现 - 2026-03-13 更新：FACTOR_REGISTRY驱动参数编辑)
- [ ] 01 数据层 (High Priority)
- [ ] 03 搜索系统 (High Priority)
- [x] 08 回测系统 (已实现 - 基于观察池的回测引擎)
- [x] [04 观察池系统(Realtime)](../modules/specs/04_观察池系统_IMPL.md) (已实现 - 四维评估系统)
- [x] [13 Daily观察池](../modules/specs/13_Daily观察池_IMPL.md) (已实现 - 阶段状态机模型)
- [x] [14 Simple Pool](../modules/specs/14_Simple_Pool_IMPL.md) (已实现 - 2026-01-08 新增：MVP 即时判断模型)
- [ ] 05-07 实盘交易系统 (Medium Priority)
- [x] [15 数据挖掘](../modules/specs/15_数据挖掘模块_IMPL.md) (已实现 - 方向单一来源+Trial物化闭环+非单调检测+样本外验证)
- [x] [16 新闻情感分析](../modules/specs/16_新闻情感分析_IMPL.md) (已实现 - 多源采集+可插拔Backend+时间衰减+缓存)
- [ ] 09 配置管理 (Low Priority)
- [ ] 10 工具与辅助 (Low Priority)

> *详细设计文档请查阅 `docs/modules/specs/`*

## 最新更新 (2026-03-23)

### 新闻情感分析模块增强
- **时间衰减加权**：采样层（时间加权 FPS）+ 汇总层（时间加权聚合），近期新闻权重更高，处理情绪反转场景
- **缓存机制**：SQLite 两层缓存（NewsItem + SentimentResult），增量采集，支持连续突破/批量扫描/回测复用
- **max_items 动态化**：`clamp(10√days, 15, 100)`，根据时间跨度自适应

---

## 历史更新 (2026-03-13)

### FACTOR_REGISTRY SSOT 完整闭环
- 因子注册表扩展至 12 个因子（新增 pre_vol）
- `features.py` 重构：每个因子独立 `_calculate_xxx()` 方法
- `param_writer` / `factor_diagnosis`：修复 SSOT 泄漏，为 YAML 中缺失的因子自动合成默认条目
- `input_factory.py`：`param_value=None` 时 fallback 到 schema default，UI 参数编辑器零适配
- 整个新因子工作流（注册→计算→评分→挖掘→写回→UI 编辑）实现完全自动化

---

## 历史更新 (2026-02-11)

### 突破评分模型升级
- 评分模型从 8 个 Bonus 升级至 10 个 Bonus + 1 个惩罚
- 新增：DayStr（合并 Gap+DailyReturn）、PBM、Streak、PK-Momentum、Overshoot penalty
- 移除：Gap、DailyReturn、Continuity 旧 Bonus
- 文档同步更新至 `02_突破扫描模块_IMPL.md`

---

## 历史更新 (2026-01-09)

### Scan Configuration 股票筛选条件
- 在 UI 扫描配置中新增股票筛选条件（仅 Global Time Range 模式有效）
- `min_price` / `max_price`：价格范围限制
- `min_volume`：最小平均成交量限制

---

## 历史更新 (2026-01-08)

### Simple Pool MVP 版本
- 新增独立的 MVP 观察池 `BreakoutStrategy/simple_pool/`
- 即时判断模型：无状态机，三条件并行检查
- 仅 4 个核心参数（vs 旧系统 29 个）
- 简化支撑位检测：`min(low[-N:])`
- 完全独立，不依赖 daily_pool

---

## 历史更新 (2026-01-04)

### Daily 观察池系统
- 新增独立的日K级别观察池 `BreakoutStrategy/daily_pool/`
- 阶段状态机模型：INITIAL → PULLBACK → CONSOLIDATION → REIGNITION → SIGNAL
- 三维度分析器：价格模式、波动率、成交量
- 证据聚合模式：分析器独立分析，状态机综合判断
- 回测引擎：`DailyBacktestEngine`

---

## 历史更新 (2026-01-01)

### 文档整合
- 更新三大核心模块的实现文档（突破扫描、UI、观察池）
- 添加观察池四维评估系统的完整架构说明
- UI 文档新增"观察池集成"章节

### 观察池四维评估系统
- `CompositeBuyEvaluator`: 组合评估器，整合四维度评估
- 四维度：时间窗口(20%)、价格确认(40%)、成交量验证(25%)、风险过滤(门槛)
- 支持 ATR 标准化的价格确认评估

### 观察池适配器模块
- `BreakoutJSONAdapter`: JSON 扫描结果 ↔ Breakout 对象转换
- `EvaluationContextBuilder`: 构建买入评估上下文
- UI 的 `_load_from_json_cache()` 已重构为使用适配器

### 回测引擎
- `BacktestEngine`: 基于观察池的回测引擎
- 入口脚本: `scripts/backtest/pool_backtest.py`
- 支持止盈止损、多仓位管理、绩效统计

### UI 观察池集成
- "Add to Pool" 按钮
- `add_to_observation_pool()`: 将当前突破添加到观察池
- `show_pool_status()`: 显示池状态
- 懒加载设计，按需初始化观察池管理器
