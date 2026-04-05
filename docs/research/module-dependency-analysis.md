# BreakoutStrategy 非核心模块依赖分析

> 日期: 2026-04-02 | 核心模块: analysis, mining, news_sentiment, UI

## 一、非核心子目录依赖矩阵

| 模块 | 文件数 | analysis 引用 | mining 引用 | news_sentiment 引用 | UI 引用 | scripts 引用 | 建议 |
|------|--------|:---:|:---:|:---:|:---:|:---:|------|
| `signals/` | 0 (.py) | - | - | - | - | - | **删除** |
| `backtest/` | 2 | - | - | - | - | realtime_pool_backtest | **删除** |
| `shadow_pool/` | 5 | - | - | - | - | shadow_mode_backtest | **删除** |
| `simple_pool/` | 7 | - | - | - | - | simple_pool_backtest | **删除** |
| `daily_pool/` | 17 | - | - | - | - | daily_pool_backtest | **删除** |
| `observation/` | 16 | - | - | - | **UI/main.py x2** | 5 个 backtest 脚本 | **待定** |

## 二、observation 与 UI 的耦合细节

`UI/main.py` 中有两处 lazy import:
1. L459: `from BreakoutStrategy.observation.adapters import BreakoutJSONAdapter` -- 用于加载扫描结果 JSON
2. L1653: `from BreakoutStrategy.observation import create_backtest_pool_manager` -- "Add to Pool" 功能

这两个功能属于 **观察池交互** (非扫描/挖掘核心流程)。如果删除 observation，需要同时移除 UI 中的观察池相关代码。

## 三、根级共享文件

| 文件 | 被核心模块引用 | 建议 |
|------|:---:|------|
| `factor_registry.py` | analysis(2), mining(10), UI(3) | **保留** -- 核心共享依赖 |
| `__init__.py` | 仅文档性质 | **保留** -- 更新 docstring 即可 |

## 四、configs 目录

| 配置 | 引用者 | 建议 |
|------|--------|------|
| `configs/params/` | mining, UI | **保留** |
| `configs/scan_config.yaml` | UI | **保留** |
| `configs/ui_config.yaml` | UI | **保留** |
| `configs/user_scan_config.yaml` | UI | **保留** |
| `configs/api_keys.yaml` | news_sentiment | **保留** |
| `configs/news_sentiment.yaml` | news_sentiment | **保留** |
| `configs/daily_pool/` | 仅 daily_pool | **删除** |
| `configs/simple_pool/` | 仅 simple_pool | **删除** |
| `configs/buy_condition_config.yaml` | 仅 observation | **删除** |
| `configs/templates/` | 空目录 | **删除** |

## 五、scripts 目录

| 脚本 | 依赖模块 | 建议 |
|------|----------|------|
| `visualization/interactive_viewer.py` | UI | **保留** |
| `benchmark_samplers.py` | mining, factor_registry | **保留** |
| `experiments/collect_validation_data.py` | news_sentiment | **保留** |
| `data/` | 无非核心依赖 | **保留** |
| `backtest/daily_pool_backtest.py` | daily_pool, observation | **删除** |
| `backtest/shadow_mode_backtest.py` | shadow_pool, observation | **删除** |
| `backtest/simple_pool_backtest.py` | simple_pool, observation | **删除** |
| `backtest/realtime_pool_backtest.py` | backtest | **删除** |
| `backtest/trade_backtest.py` | observation, analysis | **删除** |
| `backtest/evaluator_demo.py` | observation | **删除** |

## 六、可安全删除清单

```
# 模块 (无核心依赖)
BreakoutStrategy/signals/          # 空模块，仅 __pycache__
BreakoutStrategy/backtest/
BreakoutStrategy/shadow_pool/
BreakoutStrategy/simple_pool/
BreakoutStrategy/daily_pool/

# observation -- 需先移除 UI/main.py 中 L459, L1653 及相关观察池方法
BreakoutStrategy/observation/

# 配置
configs/daily_pool/
configs/simple_pool/
configs/buy_condition_config.yaml
configs/templates/

# 脚本
scripts/backtest/                  # 整个目录（所有脚本均依赖非核心模块）
```

**注意**: 删除 `observation/` 前必须清理 `UI/main.py` 中的两处 import 及关联的 `add_to_observation_pool()` 方法，否则运行时会报 ImportError。其余模块可直接删除，无副作用。
