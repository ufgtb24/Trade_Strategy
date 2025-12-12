# 技术分析模块功能分析报告

> 分析日期：2025-12-09
> 模块路径：`BreakthroughStrategy/analysis/`

---

## 模块概览

### 活跃入口

技术分析模块目前有 **两个活跃入口**：

| 入口 | 路径 | 说明 |
|------|------|------|
| 批量扫描脚本 | `scripts/analysis/batch_scan.py` | 通过 `ScanManager` 调用 |
| UI 重新计算 | `BreakthroughStrategy/UI/` | 通过 `compute_breakthroughs_from_dataframe` 调用 |

两个入口共用 `ScanManager`（位于 `BreakthroughStrategy/UI/managers/scan_manager.py`），统一使用以下核心组件：

### 活跃代码（正在使用）

| 组件 | 文件 | 功能 |
|------|------|------|
| `BreakthroughDetector` | `breakthrough_detector.py` | 增量式峰值/突破检测 |
| `FeatureCalculator` | `features.py` | 突破特征计算 |
| `QualityScorer` | `quality_scorer.py` | 质量评分（峰值+突破） |

### 陈旧代码（未被使用）

| 文件 | 状态 | 说明 |
|------|------|------|
| ~~`my_detector.py`~~ | ✅ 已删除 | 旧版检测器原型 |
| ~~`multi_stock_detector.py`~~ | ✅ 已删除 | 依赖旧版检测器，有运行时 bug |
| `indicators.py` | 未集成 | 实现了 MA/RSI/RV，但未被任何入口使用 |
| ~~`test/test_quality_improvement.py`~~ | ✅ 已删除 | 引用已删除的旧 API |

---

## 发现的问题

### P0 - 代码质量问题 ✅ 已修复

#### 1. ~~遗留代码未清理（重复实现）~~ ✅ 已删除

| 文件 | 状态 |
|------|------|
| ~~`my_detector.py`~~ | ✅ 已删除 |
| ~~`multi_stock_detector.py`~~ | ✅ 已删除 |

#### 2. ~~测试代码与实现不一致~~ ✅ 已删除

| 文件 | 状态 |
|------|------|
| ~~`test_quality_improvement.py`~~ | ✅ 已删除 |

---

### P1 - 影响评分准确性 ✅ 已修复

#### 3. ~~`merged` 权重是"死权重"~~ ✅ 已修复

已移除 `merged` 权重，将 15% 重新分配给其他维度：
- `volume`: 25% → 30%
- `suppression`: 25% → 30%
- `height`: 15% → 20%

#### 4. ~~连续性计算逻辑问题~~ ✅ 已修复

修改 `features.py` 中的 `_calculate_continuity()` 方法：
- 从突破日**前一天**开始计算
- 避免阴线突破时直接返回 0

---

### P2 - 功能增强（可以改进）

#### 5. 模块导出不完整

`__init__.py` 未导出：
- `TechnicalIndicators` - 技术指标类
- `MultiStockBreakoutMonitor` - 多股票监控器（虽然需要重构）

#### 6. 技术指标未被利用

`indicators.py` 实现了 MA、RSI、相对成交量，但：
- 评分系统未使用这些指标
- 文档未说明用途或集成计划

---

## 已知局限（文档已记录）

| 问题 | 影响 | 文档状态 |
|------|------|---------|
| 峰值确认延迟 | 实时监控时最新峰值无法立即识别 | 已记录，提出"候选峰值"方案但未实现 |
| 稳定性依赖未来数据 | 实时场景返回默认 50 分 | 已记录 |
| pickle 持久化 | 版本兼容性差 | 已记录 |

---

## 改进措施

### P0 - ✅ 已完成

1. ~~**清理 `multi_stock_detector.py`**~~ → 已删除
2. ~~**修复 `test_quality_improvement.py`**~~ → 已删除
3. ~~**处理 `my_detector.py`**~~ → 已删除

### P1 - ✅ 已完成

4. ~~**移除 `merged` 权重**~~ → 已将 15% 重新分配给其他维度
5. ~~**修复连续性计算**~~ → 已改为从突破日前一天开始

### P2 - 待改进

6. **整合技术指标到评分系统**
   - 如：RSI 超买/超卖作为评分因子
   - 或明确指标的使用场景

7. **补充模块导出**
   - 在 `__init__.py` 中导出 `TechnicalIndicators`

---

## 附录：文件清单

```
BreakthroughStrategy/analysis/
├── __init__.py                 # 模块导出（不完整）
├── breakthrough_detector.py    # ✅ 核心检测器（活跃）
├── features.py                 # ✅ 特征计算器（活跃，已修复连续性计算）
├── quality_scorer.py           # ✅ 质量评分器（活跃，已移除死权重）
├── indicators.py               # ⚠️ 技术指标（未被集成）
└── test/
    ├── __init__.py
    └── test_integrated_system.py      # ✅ 集成测试（正常）
```

### 调用链路

```
scripts/analysis/batch_scan.py
    └── ScanManager (UI/managers/scan_manager.py)
            └── compute_breakthroughs_from_dataframe()
                    ├── BreakthroughDetector (analysis/breakthrough_detector.py)
                    ├── FeatureCalculator (analysis/features.py)
                    └── QualityScorer (analysis/quality_scorer.py)

UI 重新计算
    └── ScanManager.scan_stock() 或 compute_breakthroughs_from_dataframe()
            └── (同上)
```
