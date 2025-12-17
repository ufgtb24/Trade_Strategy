---
name: prototype-bonus-analysis
description: Use when new bonus factors are proposed in research docs and need statistical validation before full system implementation. Triggered when user wants to analyze experimental bonuses using bonus_combination_analysis.py without modifying the core BreakoutScorer, UI, or configs.
---

# Prototype Bonus Analysis

## Overview

在不修改核心系统（BreakoutScorer、UI、配置）的前提下，通过最小改动让 `bonus_combination_analysis.py` 分析尚未正式实现的实验性 bonus 因子。核心原则：**仅修改分析管道（3 个文件），验证有效性后再决定是否正式实现**。

## 输入

用户提供的新 bonus 定义，通常来自 `docs/research/bonus_system_analysis.md` 的改进建议，包含：
- bonus 名称
- 计算逻辑（公式 / 阈值 / level 定义）
- 所需原始数据字段

## 数据可用性判定

分析脚本的数据源是 `outputs/scan_results/scan_results_*.json`。新 bonus 所需的原始数据分两类：

**Type A — JSON 中已有字段**（零成本接入）：
```
breakout_type, intraday_change_pct, price, volume_surge_ratio,
momentum, pk_momentum, gain_5d, annual_volatility,
gap_up_pct, recent_breakout_count, days_since_last_breakout,
all_peaks[].volume_surge_ratio, all_peaks[].relative_height
```

**Type B — JSON 中不存在**（需回读 `.pkl`）：
```
MA 均线值、OHLC 四价、绝对成交量、外部基准数据等
```

```dot
digraph data_availability {
  rankdir=LR;
  "新 bonus 所需数据" [shape=diamond];
  "JSON 已有?" [shape=diamond];
  "Type A: 直接在\nbuild_dataframe() 计算" [shape=box];
  "Type B: 需回读 .pkl\n创建预加载函数" [shape=box];

  "新 bonus 所需数据" -> "JSON 已有?";
  "JSON 已有?" -> "Type A: 直接在\nbuild_dataframe() 计算" [label="是"];
  "JSON 已有?" -> "Type B: 需回读 .pkl\n创建预加载函数" [label="否"];
}
```

## pkl 文件格式

`datasets/pkls/{symbol}.pkl` 是 pandas DataFrame，通过 `pd.read_pickle()` 加载：
- **索引**：`pd.DatetimeIndex`（日期型，如 `2024-05-20`）
- **列**：`['open', 'high', 'low', 'close', 'volume']`（float64）
- **日期匹配**：JSON 中 `bo["date"]` 是字符串 `"2024-05-20"`，pkl 索引需用 `df.index.strftime("%Y-%m-%d")` 转换后匹配

## 实施流程

### Step 1: 数据可用性分类

对每个新 bonus，判定所需原始数据属于 Type A 还是 Type B。

### Step 2: 编写 Level 计算函数

在 `scripts/analysis/_prototype_bonuses.py` 中编写纯函数。

**命名规范**：`calc_{bonus_name}_level(...)` → 返回 `int`（0, 1, 2, ...）

**Level 级数**：参照现有 bonus 惯例，大多数用 2-3 级（0/1/2 或 0/1/2/3）。初始分级可用原始值的分位数确定：
```python
# 确定阈值的辅助方法：先不分级，看原始值分布
df['close_pos_raw'] = ...  # 原始计算值
print(df['close_pos_raw'].describe())  # 用 25%/50%/75% 分位点作为候选阈值
```

**Type A 示例**（candle_pattern，使用 JSON 已有字段）：
```python
def calc_candle_pattern_level(breakout_type: str, intraday_change_pct: float) -> int:
    if breakout_type != "yang":
        return 0
    if abs(intraday_change_pct) >= 0.03:
        return 2
    return 1
```

**Type B 参考实现**（precompute + trend）：
```python
import pandas as pd
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

def precompute_stock_data(data: dict, need_ohlc=False, ma_periods=()) -> dict:
    """
    预加载 .pkl 文件，返回 {symbol: {date_str: {field: value}}}

    Args:
        data: 已加载的 scan_results JSON 字典
        need_ohlc: 是否提取 open/high/low/close
        ma_periods: 需要计算的 MA 周期元组，如 (50, 200)
    """
    symbols = {s["symbol"] for s in data["results"]}
    lookup = {}

    for symbol in symbols:
        pkl_path = PROJECT_ROOT / "datasets" / "pkls" / f"{symbol}.pkl"
        if not pkl_path.exists():
            continue

        df = pd.read_pickle(pkl_path)
        date_strs = df.index.strftime("%Y-%m-%d")

        # 预计算 MA
        mas = {p: df["close"].rolling(p).mean() for p in ma_periods}
        # 预计算平均成交量
        avg_vol = df["volume"].rolling(20).mean() if need_ohlc else None

        date_data = {}
        for i, ds in enumerate(date_strs):
            entry = {}
            if need_ohlc:
                entry.update({
                    "open": float(df["open"].iloc[i]),
                    "high": float(df["high"].iloc[i]),
                    "low": float(df["low"].iloc[i]),
                    "close": float(df["close"].iloc[i]),
                })
                if avg_vol is not None and pd.notna(avg_vol.iloc[i]):
                    entry["avg_volume_20"] = float(avg_vol.iloc[i])
            for p in ma_periods:
                val = mas[p].iloc[i]
                if pd.notna(val):
                    entry[f"ma_{p}"] = float(val)
            if entry:  # 仅保存非空条目
                date_data[ds] = entry
        lookup[symbol] = date_data

    return lookup


def calc_trend_level(price: float, ma_200, ma_50=None) -> int:
    if ma_200 is None or price <= ma_200:
        return 0
    if ma_50 is not None and ma_50 > ma_200:
        return 2  # 强顺势：价格 > MA200 且 MA50 > MA200
    return 1
```

### Step 3: 集成到 build_dataframe()

修改 `scripts/analysis/bonus_combination_analysis.py` 的 `build_dataframe()` 函数：

1. **文件头部**添加 import：
```python
from _prototype_bonuses import calc_xxx_level  # Type A
from _prototype_bonuses import precompute_stock_data, calc_yyy_level  # Type B
```

2. **JSON 加载后**（仅 Type B 需要）添加预加载：
```python
stock_data = precompute_stock_data(data, need_ohlc=True, ma_periods=(50, 200))
```

3. **breakout 循环中**添加 level 计算：
```python
# --- 原型 Bonus ---
xxx_level = calc_xxx_level(breakout_type, intraday_change_pct)

# Type B: 从预加载数据取值
aux = stock_data.get(symbol, {}).get(bo["date"], {})
yyy_level = calc_yyy_level(bo["price"], aux.get("ma_200"), aux.get("ma_50"))
```

4. **rows.append({...})** 中添加新列：
```python
"xxx_level": xxx_level,
"yyy_level": yyy_level,
```

### Step 4: 注册到分析框架

修改 `scripts/analysis/_analysis_functions.py`：

```python
BONUS_COLS = [
    # ... 现有 bonus ...
    'xxx_level', 'yyy_level',  # 原型 bonus
]

BONUS_DISPLAY = {
    # ... 现有映射 ...
    'xxx_level': 'XxxName',
    'yyy_level': 'YyyName',
}
```

### Step 5: 运行分析

```bash
uv run python scripts/analysis/bonus_combination_analysis.py
```

检查输出报告中新 bonus 的：
- Spearman 相关系数（r > 0 且 p < 0.001 → 有效信号）
- Level 单调性（median 随 level 递增 → 有效分级）
- 与现有因子的交互效应

## 修改文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `scripts/analysis/_prototype_bonuses.py` | 新建 | Level 计算纯函数 + 预加载函数（如需） |
| `scripts/analysis/bonus_combination_analysis.py` | 修改 `build_dataframe()` | 集成新 level 计算 |
| `scripts/analysis/_analysis_functions.py` | 修改 `BONUS_COLS` + `BONUS_DISPLAY` | 注册新因子 |

**不改的文件**：`BreakoutScorer`、`features.py`、UI、configs — 全部不动。

## 从原型到正式实现的路径

统计验证通过后，正式实现路径：
1. `features.py` → 添加原始特征计算
2. `Breakout` dataclass → 添加新字段
3. `breakout_scorer.py` → 添加 `_get_xxx_bonus()` 方法
4. `scan_manager.py` → 序列化新字段到 JSON
5. `scan_params.yaml` → 添加阈值/乘数配置
6. 重新运行全量扫描
7. 分析脚本改为从 JSON 读取（不再回读 .pkl）

## Type B 性能注意事项

- 预加载 .pkl 约 50-100ms/只股票，918 只约 1-2 分钟
- 内存占用约 1-2 GB（全量日期映射）
- 优化：仅保留 breakout 日期附近数据，或缓存预计算结果为 pickle

## 常见错误

| 错误 | 正确做法 |
|------|---------|
| 修改 BreakoutScorer 做"临时"实验 | 只改分析管道，不碰核心系统 |
| 硬编码阈值后忘记调整 | 先跑原始值分布 `.describe()`，用分位数定阈值后迭代 |
| Type B 预加载时加载全部字段 | 按需设置 `need_ohlc` / `ma_periods`，减少内存 |
| 忘记在 `BONUS_COLS` 注册新列 | 不注册就不会出现在分析报告中 |
| 对 Type A bonus 也做 .pkl 预加载 | 能从 JSON 取的数据不要回读 .pkl |
| Type B 日期匹配时类型不对 | pkl 索引是 DatetimeIndex，JSON date 是字符串，用 `strftime` 转换 |
| pkl 文件不存在时崩溃 | `precompute_stock_data` 中 `if not pkl_path.exists(): continue` |
