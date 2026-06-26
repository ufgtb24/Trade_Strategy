# path2_web 复刻 Dev UI 关键交互 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 path2_web 复刻 BreakoutStrategy Dev UI 的几块 K 线交互：缓冲区灰阴影 + 初始 viewport 严格贴 scan 窗、量叠加进价格区底部 20%、横线锁该 bar close、bar tooltip (Date/OHLC/Chg/Volume/RV)、Ctrl 解锁横线跟鼠标，并保留 path2 marker tooltip 优先级。

**Architecture:** 后端 `path2_web/data.py::serialize_ohlc` 新增 `rv` 字段（pandas rolling(63).mean().shift(1)，dev 同口径）。前端新增 `ctrlState.ts` 单例订阅 + `chart.ts` 内抽 4 个纯函数（`buildShadingMarkArea` / `buildVolumeSeriesAndYAxis` / `buildBarTooltipFormatter` / `buildMarkerTooltipFormatter`）。`chart.ts` 整合：grid 3→2、删 markLine 改 markArea、初始 zoom 落 [startIdx, endIdx]、`axisPointer.type='cross'` + horizontal lock-to-close override、global axis-trigger bar tooltip + series-level item-trigger marker tooltip。`KlineChart.vue` 订阅 ctrlState、挂 zr mousemove 维护 mouseY、监听 datazoom 重算 volume scale。

**Tech Stack:** Python 3.12 / pandas / pytest / Vue3 / TypeScript / ECharts / Vitest / Playwright (chromium)

## Global Constraints

- **后端唯一变更**：`path2_web/data.py::serialize_ohlc` 返回的每根 bar dict 新增 `rv: float` 字段。其它接口、字段、签名一律不动。
- **算法常量**：lookback=63、shift(1) 硬编码（不可配）。`pandas.DataFrame.rolling(63, min_periods=1).mean().shift(1)`；inf/nan 清零。
- **颜色常量**（硬编码字符串）：`volume_up = '#D3D3D3'`、`volume_down = '#696969'`、`crosshair_normal = '#0088CC'`、`crosshair_ctrl = '#FF6600'`、阴影 `#808080` alpha `0.15`。
- **4 个纯函数都放在 `chart.ts` 内并 export**（不新建独立 helpers 文件——spec §0 YAGNI 红线）。
- **路径守红线**：后端不算前端 bars 数组的派生量（不返回 startIdx / endIdx / zoom 比例）；前端 `findIndex` 自己算。守 path2_web "纯投影层"契约。
- **Non-goal**：不复刻 dev 的"突破日金色高亮柱"、3 年最小窗下限、degradation 橙虚线、ATR/Active peaks/BO/Peak 字段。
- **Off-by-one 修正**：dev 的灰阴影把 `scan_start_actual` 那根 bar 蒙进灰区（searchsorted side='right' 的副作用）；本 plan **修正**——`bars[startIdx]` 和 `bars[endIdx]` 本身在白区。
- **依赖**：参考 spec `docs/superpowers/specs/2026-06-23-path2-web-dev-ui-replication-design.md` 和 dev 调研 `docs/research/2026-06-23_path2-web-dev-ui-replication/final_report.md`。

---

## File Structure

### Create

- `tests/path2_web/test_data_rv.py` — Backend rv 算法 + 集成测试
- `path2_web_ui/src/render/ctrlState.ts` — 单例 (isPressed/mouseY) + document keydown/keyup 监听
- `path2_web_ui/tests/ctrl-state.spec.ts` — ctrlState 单测
- `path2_web_ui/tests/chart-helpers.spec.ts` — 4 个纯函数单测
- `path2_web_ui/e2e/dev-ui-replication.spec.ts` — E2E 多场景截图验证

### Modify

- `path2_web/data.py` — `serialize_ohlc` 加 rv 字段（约 10 行 + 顶部 import numpy）
- `path2_web_ui/src/render/chart.ts` — 整合 4 个纯函数 + grid 重排 + axisPointer override + tooltip 拆分（修改量主要集中在 `buildKlineOption` 的 `xAxis/yAxis/grid/dataZoom/tooltip/markLine` 几块 + series 配置 xAxisIndex/yAxisIndex 重映射）
- `path2_web_ui/src/components/KlineChart.vue` — 订阅 ctrlState、挂 zr mousemove、监听 datazoom 重算 vol scale

---

## Tasks Overview

| # | 任务 | 大致依赖 |
|---|------|---------|
| 1 | Backend rv 字段 + 测试 | 独立、最先 land |
| 2 | ctrlState.ts + 测试 | 无依赖、可与 1 并行 |
| 3 | `buildShadingMarkArea` + 测试 | 独立 |
| 4 | `buildVolumeSeriesAndYAxis` + 测试 | 独立 |
| 5 | `buildBarTooltipFormatter` + 测试 | 依赖 Task 2 (ctrlState 类型) |
| 6 | `buildMarkerTooltipFormatter`（从 chart.ts 抽出） | 独立 |
| 7 | chart.ts 整合：grid 重排 + 集成 4 helpers + axisPointer override + tooltip 拆分 | 依赖 Task 3/4/5/6 |
| 8 | KlineChart.vue 订阅 ctrlState + 挂 zr mousemove + datazoom 重算 vol | 依赖 Task 7 |
| 9 | Playwright E2E 多场景验证 | 依赖 Task 8 |

---

## Task 1: Backend rv 字段

**Files:**
- Modify: `path2_web/data.py:24-37`（`serialize_ohlc` 函数体内插入 rv 计算）
- Test: `tests/path2_web/test_data_rv.py`（新建）

**Interfaces:**
- Consumes: 无新增（保持 `serialize_ohlc(symbol, win_df)` 签名）
- Produces: 返回字典中 `bars[i]` 多一个 `"rv": float` 字段（其余字段不变）

- [ ] **Step 1: 写失败的算法测试**

创建 `tests/path2_web/test_data_rv.py`：

```python
"""rv 字段算法与口径测试。

dev UI 公式: rv[d] = volume[d] / mean(volume[d-63:d])
实现: rolling(63, min_periods=1).mean().shift(1)
"""
import numpy as np
import pandas as pd
import pytest

from path2_web.data import serialize_ohlc


def _make_df(volumes: list[float]) -> pd.DataFrame:
    n = len(volumes)
    dates = pd.date_range("2024-01-01", periods=n, freq="D")
    return pd.DataFrame(
        {
            "open": [10.0] * n,
            "high": [11.0] * n,
            "low": [9.0] * n,
            "close": [10.5] * n,
            "volume": volumes,
            "date": dates,
        }
    )


def test_rv_at_idx_63_uses_prior_63_bars_as_denominator():
    volumes = [100.0 + i for i in range(70)]
    win_df = _make_df(volumes)
    result = serialize_ohlc("TEST", win_df)
    expected = volumes[63] / float(np.mean(volumes[:63]))
    assert result["bars"][63]["rv"] == pytest.approx(expected, rel=1e-9)


def test_rv_at_idx_0_returns_zero_due_to_shift():
    volumes = [100.0] * 5
    win_df = _make_df(volumes)
    result = serialize_ohlc("TEST", win_df)
    assert result["bars"][0]["rv"] == 0.0


def test_rv_at_idx_1_uses_only_idx_0_avg_under_min_periods():
    volumes = [100.0, 200.0, 300.0]
    win_df = _make_df(volumes)
    result = serialize_ohlc("TEST", win_df)
    assert result["bars"][1]["rv"] == pytest.approx(200.0 / 100.0, rel=1e-9)


def test_rv_zero_denominator_yields_zero_not_inf():
    volumes = [0.0, 0.0, 500.0]
    win_df = _make_df(volumes)
    result = serialize_ohlc("TEST", win_df)
    assert result["bars"][2]["rv"] == 0.0


def test_rv_field_present_on_every_bar_as_float():
    volumes = [100.0] * 10
    win_df = _make_df(volumes)
    result = serialize_ohlc("TEST", win_df)
    for b in result["bars"]:
        assert "rv" in b
        assert isinstance(b["rv"], float)
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd /home/yu/PycharmProjects/Trade_Strategy-bo
uv run pytest tests/path2_web/test_data_rv.py -v
```

Expected: 5 个测试全 FAIL（`KeyError: 'rv'` 或类似）。

- [ ] **Step 3: 实现 serialize_ohlc 加 rv 字段**

修改 `path2_web/data.py`：

```python
"""唯一权威切片 slice_window() + OHLC 序列化。

扫描 worker 与 /ohlc 共用 slice_window,保证 bars[i] ↔ start_idx==i 严格对齐
(同一 (symbol,start,end) 下,K 线第 i 根 == detector 看到的第 i 个位置)。
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def slice_window(df: pd.DataFrame, start_date, end_date) -> pd.DataFrame:
    """按日期双端含端点切片,返回 0-based 行位置的 DataFrame(保留 date 列,不改行序)。

    前提:df.index 是 DatetimeIndex(index.name=="date",沿用既有 pkl 事实)。
    tz-aware 先去 tz;空/非法区间返回空 df。
    """
    if getattr(df.index, "tz", None) is not None:
        df = df.copy()
        df.index = df.index.tz_localize(None)
    win = df.loc[str(start_date):str(end_date)]
    return win.reset_index()      # DatetimeIndex(name='date') → 'date' 列;行号 0-based


def serialize_ohlc(symbol: str, win_df: pd.DataFrame) -> dict:
    """把 slice_window 的结果序列化成 {symbol, bars:[{date,o,h,l,c,v,rv}]}。
    bars[i] 对应 win_df.iloc[i](即 detector 的 start_idx==i)。

    rv (相对成交量) 口径同 dev UI: volume[d] / mean(volume[d-63:d])
    实现 rolling(63, min_periods=1).mean().shift(1); inf/nan 清零。
    """
    avg_vol = win_df["volume"].rolling(63, min_periods=1).mean().shift(1)
    rv_series = (win_df["volume"] / avg_vol).replace([np.inf, -np.inf], 0).fillna(0)
    bars = []
    for i, (_, row) in enumerate(win_df.iterrows()):
        bars.append({
            "date": str(row["date"])[:10],
            "o": float(row["open"]),
            "h": float(row["high"]),
            "l": float(row["low"]),
            "c": float(row["close"]),
            "v": float(row["volume"]),
            "rv": float(rv_series.iloc[i]),
        })
    return {"symbol": symbol, "bars": bars}
```

- [ ] **Step 4: 跑测试确认全过**

```bash
uv run pytest tests/path2_web/test_data_rv.py -v
```

Expected: 5 个测试全 PASS。

- [ ] **Step 5: 跑原有 path2_web 后端测试无回归**

```bash
uv run pytest tests/path2_web/ -v
```

Expected: 全 PASS（特别是 `test_data.py` 和 `test_scan*.py` 无回归）。

- [ ] **Step 6: Commit**

```bash
git add path2_web/data.py tests/path2_web/test_data_rv.py
git commit -m "path2_web/data: bars 新增 rv 字段(dev 同口径 rolling63+shift1)"
```

---

## Task 2: ctrlState 模块 + 测试

**Files:**
- Create: `path2_web_ui/src/render/ctrlState.ts`
- Test: `path2_web_ui/tests/ctrl-state.spec.ts`

**Interfaces:**
- Consumes: 无
- Produces:
  ```typescript
  export const ctrlState: {
    isPressed: () => boolean
    mouseY: () => number
    setMouseY: (y: number) => void
    subscribe: (fn: (pressed: boolean) => void) => () => void
  }
  ```

- [ ] **Step 1: 写失败的单测**

创建 `path2_web_ui/tests/ctrl-state.spec.ts`：

```typescript
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { ctrlState } from '../src/render/ctrlState'

function emitKey(type: 'keydown' | 'keyup', key: string) {
  document.dispatchEvent(new KeyboardEvent(type, { key }))
}

describe('ctrlState', () => {
  beforeEach(() => {
    // 复位状态（如果模块有泄漏）
    if (ctrlState.isPressed()) {
      emitKey('keyup', 'Control')
    }
    ctrlState.setMouseY(0)
  })

  it('keydown(Control) sets isPressed=true and notifies subscribers', () => {
    const cb = vi.fn()
    const unsub = ctrlState.subscribe(cb)
    emitKey('keydown', 'Control')
    expect(ctrlState.isPressed()).toBe(true)
    expect(cb).toHaveBeenCalledWith(true)
    unsub()
  })

  it('keyup(Control) resets isPressed=false', () => {
    const cb = vi.fn()
    const unsub = ctrlState.subscribe(cb)
    emitKey('keydown', 'Control')
    emitKey('keyup', 'Control')
    expect(ctrlState.isPressed()).toBe(false)
    expect(cb).toHaveBeenLastCalledWith(false)
    unsub()
  })

  it('repeated keydown does not double-notify', () => {
    const cb = vi.fn()
    const unsub = ctrlState.subscribe(cb)
    emitKey('keydown', 'Control')
    emitKey('keydown', 'Control')
    emitKey('keydown', 'Control')
    expect(cb).toHaveBeenCalledTimes(1)
    unsub()
  })

  it('window blur forces isPressed=false', () => {
    const cb = vi.fn()
    const unsub = ctrlState.subscribe(cb)
    emitKey('keydown', 'Control')
    window.dispatchEvent(new Event('blur'))
    expect(ctrlState.isPressed()).toBe(false)
    expect(cb).toHaveBeenLastCalledWith(false)
    unsub()
  })

  it('visibilitychange(hidden) forces isPressed=false', () => {
    const cb = vi.fn()
    const unsub = ctrlState.subscribe(cb)
    emitKey('keydown', 'Control')
    Object.defineProperty(document, 'hidden', { value: true, configurable: true })
    document.dispatchEvent(new Event('visibilitychange'))
    expect(ctrlState.isPressed()).toBe(false)
    expect(cb).toHaveBeenLastCalledWith(false)
    Object.defineProperty(document, 'hidden', { value: false, configurable: true })
    unsub()
  })

  it('mouseY pull-mode: setMouseY then mouseY returns same value', () => {
    ctrlState.setMouseY(123.45)
    expect(ctrlState.mouseY()).toBe(123.45)
  })

  it('unsubscribe stops further notifications', () => {
    const cb = vi.fn()
    const unsub = ctrlState.subscribe(cb)
    unsub()
    emitKey('keydown', 'Control')
    expect(cb).not.toHaveBeenCalled()
  })
})
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd /home/yu/PycharmProjects/Trade_Strategy-bo/path2_web_ui
npx vitest run tests/ctrl-state.spec.ts
```

Expected: 模块不存在导致 import 错误。

- [ ] **Step 3: 实现 ctrlState.ts**

创建 `path2_web_ui/src/render/ctrlState.ts`：

```typescript
/**
 * 全局 Ctrl 键状态 + 最近鼠标 y 坐标的单例。
 *
 * - isPressed (订阅模式): Ctrl 按下/释放，订阅者收到通知；
 *   window blur / document visibilitychange(hidden) 时强制复位（防"按住切窗"卡死）。
 * - mouseY (拉模式): chart 实例 zr.on('mousemove') 中 setMouseY，
 *   tooltip formatter 现场 mouseY() 读取；不走 reactive。
 *
 * init() 幂等;首次 subscribe 时挂全局监听。
 */

let isPressed = false
let mouseY = 0
const subs = new Set<(p: boolean) => void>()
let initialized = false

function notify(): void {
  subs.forEach(fn => fn(isPressed))
}

function init(): void {
  if (initialized) return
  initialized = true
  document.addEventListener('keydown', e => {
    if (e.key === 'Control' && !isPressed) {
      isPressed = true
      notify()
    }
  })
  document.addEventListener('keyup', e => {
    if (e.key === 'Control' && isPressed) {
      isPressed = false
      notify()
    }
  })
  window.addEventListener('blur', () => {
    if (isPressed) {
      isPressed = false
      notify()
    }
  })
  document.addEventListener('visibilitychange', () => {
    if (document.hidden && isPressed) {
      isPressed = false
      notify()
    }
  })
}

export const ctrlState = {
  isPressed: () => isPressed,
  mouseY: () => mouseY,
  setMouseY: (y: number) => { mouseY = y },
  subscribe: (fn: (p: boolean) => void) => {
    init()
    subs.add(fn)
    return () => { subs.delete(fn) }
  },
}
```

- [ ] **Step 4: 跑测试确认全过**

```bash
npx vitest run tests/ctrl-state.spec.ts
```

Expected: 7 个测试全 PASS。

- [ ] **Step 5: vue-tsc 类型检查**

```bash
npx vue-tsc --noEmit
```

Expected: 无新增类型错误。

- [ ] **Step 6: Commit**

```bash
git add path2_web_ui/src/render/ctrlState.ts path2_web_ui/tests/ctrl-state.spec.ts
git commit -m "path2_web_ui/ctrlState: Ctrl 键单例 + mouseY 拉模式 + 失焦兜底"
```

---

## Task 3: `buildShadingMarkArea` + 测试

**Files:**
- Modify: `path2_web_ui/src/render/chart.ts`（在文件末尾 export 纯函数）
- Test: `path2_web_ui/tests/chart-helpers.spec.ts`（新建，本任务首次创建）

**Interfaces:**
- Consumes: `Bar[]`（已存在 `../types`）
- Produces:
  ```typescript
  export function buildShadingMarkArea(
    bars: Bar[], scanStart: string, scanEnd: string,
  ): { itemStyle: object; data: Array<[{ xAxis: number }, { xAxis: number }]> } | null
  ```

- [ ] **Step 1: 写失败的单测**

创建 `path2_web_ui/tests/chart-helpers.spec.ts`：

```typescript
import { describe, it, expect } from 'vitest'
import { buildShadingMarkArea } from '../src/render/chart'
import type { Bar } from '../src/types'

function mkBars(dates: string[]): Bar[] {
  return dates.map(d => ({ date: d, o: 10, h: 11, l: 9, c: 10, v: 1000, rv: 1 }))
}

describe('buildShadingMarkArea', () => {
  it('returns null when scan window covers entire bars range', () => {
    const bars = mkBars(['2024-01-01', '2024-01-02', '2024-01-03'])
    const out = buildShadingMarkArea(bars, '2024-01-01', '2024-01-03')
    expect(out).toBeNull()
  })

  it('returns null when scan window covers a single bar exactly', () => {
    const bars = mkBars(['2024-01-01'])
    const out = buildShadingMarkArea(bars, '2024-01-01', '2024-01-01')
    expect(out).toBeNull()
  })

  it('returns left segment only when only left buffer exists', () => {
    // bars: [..., bar2(scan_start), bar3(scan_end)]
    const bars = mkBars(['2024-01-01', '2024-01-02', '2024-01-03', '2024-01-04'])
    const out = buildShadingMarkArea(bars, '2024-01-03', '2024-01-04')
    expect(out).not.toBeNull()
    expect(out!.data).toHaveLength(1)
    // 左段闭区间 [0, startIdx-1] = [0, 1]
    expect(out!.data[0][0]).toEqual({ xAxis: 0 })
    expect(out!.data[0][1]).toEqual({ xAxis: 1 })
  })

  it('returns right segment only when only right buffer exists', () => {
    const bars = mkBars(['2024-01-01', '2024-01-02', '2024-01-03', '2024-01-04'])
    const out = buildShadingMarkArea(bars, '2024-01-01', '2024-01-02')
    expect(out).not.toBeNull()
    expect(out!.data).toHaveLength(1)
    // 右段 [endIdx+1, last] = [2, 3]
    expect(out!.data[0][0]).toEqual({ xAxis: 2 })
    expect(out!.data[0][1]).toEqual({ xAxis: 3 })
  })

  it('returns both segments with off-by-one fix (startIdx/endIdx themselves in white)', () => {
    const bars = mkBars([
      '2024-01-01', '2024-01-02',                       // 左 buffer
      '2024-01-03', '2024-01-04', '2024-01-05',         // scan 窗
      '2024-01-06', '2024-01-07',                       // 右 buffer
    ])
    const out = buildShadingMarkArea(bars, '2024-01-03', '2024-01-05')
    expect(out).not.toBeNull()
    expect(out!.data).toHaveLength(2)
    // 左段 [0, 1] — 即 startIdx-1=1，bar[2](scan_start) 在白区
    expect(out!.data[0]).toEqual([{ xAxis: 0 }, { xAxis: 1 }])
    // 右段 [5, 6] — 即 endIdx+1=5，bar[4](scan_end) 在白区
    expect(out!.data[1]).toEqual([{ xAxis: 5 }, { xAxis: 6 }])
  })

  it('shading itemStyle is dev grey #808080 alpha 0.15', () => {
    const bars = mkBars(['2024-01-01', '2024-01-02', '2024-01-03'])
    const out = buildShadingMarkArea(bars, '2024-01-02', '2024-01-02')
    expect(out).not.toBeNull()
    expect(out!.itemStyle).toEqual({ color: '#808080', opacity: 0.15 })
  })
})
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd /home/yu/PycharmProjects/Trade_Strategy-bo/path2_web_ui
npx vitest run tests/chart-helpers.spec.ts
```

Expected: import 错误（函数未导出）。

- [ ] **Step 3: 实现 buildShadingMarkArea**

在 `path2_web_ui/src/render/chart.ts` 文件**末尾**追加 export：

```typescript
// ─── Pure helpers (Dev UI 复刻) ───────────────────────────────────────────────

/**
 * 计算两段灰色阴影 markArea: [bars[0], bars[startIdx-1]] 和 [bars[endIdx+1], bars[last]]。
 * Off-by-one 修正: bars[startIdx] 和 bars[endIdx] 本身落在白区。
 *
 * @param bars       完整 bars 数组
 * @param scanStart  严格 scan 窗起始日期 (YYYY-MM-DD)
 * @param scanEnd    严格 scan 窗结束日期 (YYYY-MM-DD)
 * @returns          markArea 配置；scan 窗覆盖全集时返回 null
 */
export function buildShadingMarkArea(
  bars: Bar[], scanStart: string, scanEnd: string,
): { itemStyle: { color: string; opacity: number }; data: Array<[{ xAxis: number }, { xAxis: number }]> } | null {
  if (bars.length === 0) return null
  const startIdx = bars.findIndex(b => b.date >= scanStart)
  if (startIdx < 0) return null
  let endIdx = -1
  for (let i = bars.length - 1; i >= 0; i--) {
    if (bars[i].date <= scanEnd) { endIdx = i; break }
  }
  if (endIdx < 0) return null
  const data: Array<[{ xAxis: number }, { xAxis: number }]> = []
  if (startIdx > 0) data.push([{ xAxis: 0 }, { xAxis: startIdx - 1 }])
  if (endIdx < bars.length - 1) data.push([{ xAxis: endIdx + 1 }, { xAxis: bars.length - 1 }])
  if (data.length === 0) return null
  return {
    itemStyle: { color: '#808080', opacity: 0.15 },
    data,
  }
}
```

- [ ] **Step 4: 跑测试确认全过**

```bash
npx vitest run tests/chart-helpers.spec.ts
```

Expected: 6 个测试全 PASS。

- [ ] **Step 5: 类型检查 + 既有测试不回归**

```bash
npx vue-tsc --noEmit
npx vitest run
```

Expected: 全 PASS（特别是 chart.spec.ts 等既有测试）。

- [ ] **Step 6: Commit**

```bash
git add path2_web_ui/src/render/chart.ts path2_web_ui/tests/chart-helpers.spec.ts
git commit -m "path2_web_ui/chart: buildShadingMarkArea 纯函数(off-by-one 修正)"
```

---

## Task 4: `buildVolumeSeriesAndYAxis` + 测试

**Files:**
- Modify: `path2_web_ui/src/render/chart.ts`（在文件末尾追加 export）
- Test: `path2_web_ui/tests/chart-helpers.spec.ts`（扩）

**Interfaces:**
- Consumes: `Bar[]` + visible bar 索引范围
- Produces:
  ```typescript
  export function buildVolumeSeriesAndYAxis(
    bars: Bar[], visStart: number, visEnd: number,
  ): {
    volSeries: { type: 'bar'; name: 'volume'; xAxisIndex: 0; yAxisIndex: 0;
                  barWidth: '100%'; z: 1; data: Array<{ value: number; itemStyle: object }> }
    yAxisOverride: { min: number; max: number }
  }
  ```

- [ ] **Step 1: 写失败的单测**

在 `path2_web_ui/tests/chart-helpers.spec.ts` 文件末尾追加：

```typescript
import { buildVolumeSeriesAndYAxis } from '../src/render/chart'

function mkBars2(items: Array<{ o: number; h: number; l: number; c: number; v: number }>): Bar[] {
  return items.map((b, i) => ({
    date: `2024-01-${String(i + 1).padStart(2, '0')}`,
    o: b.o, h: b.h, l: b.l, c: b.c, v: b.v, rv: 1,
  }))
}

describe('buildVolumeSeriesAndYAxis', () => {
  it('uses visible-range vol_max for scale (not full bars max)', () => {
    const bars = mkBars2([
      { o: 10, h: 12, l: 9, c: 11, v: 1000 },   // visible
      { o: 11, h: 13, l: 10, c: 12, v: 2000 },  // visible
      { o: 12, h: 14, l: 11, c: 13, v: 5000 },  // NOT visible (big volume should NOT affect scale)
    ])
    const { volSeries, yAxisOverride } = buildVolumeSeriesAndYAxis(bars, 0, 1)
    // displayHeight = priceRange / 0.8 = (13 - 9) / 0.8 = 5
    // displayBottom = 9 - 5 * 0.1 = 8.5
    // visVolMax = max(1000, 2000) = 2000
    // volScale = 5 * 0.2 / 2000 = 0.0005
    expect(yAxisOverride.min).toBeCloseTo(8.5, 9)
    expect(yAxisOverride.max).toBeCloseTo(13.5, 9)
    // bar[0]: value = 8.5 + 1000 * 0.0005 = 9.0
    expect(volSeries.data[0].value).toBeCloseTo(9.0, 9)
    // bar[1]: value = 8.5 + 2000 * 0.0005 = 9.5
    expect(volSeries.data[1].value).toBeCloseTo(9.5, 9)
    // bar[2] uses same scale (full bars data exists but viz uses visible scale)
    expect(volSeries.data[2].value).toBeCloseTo(8.5 + 5000 * 0.0005, 9)
  })

  it('color is up-grey when close>=open, down-grey when close<open', () => {
    const bars = mkBars2([
      { o: 10, h: 11, l: 9, c: 10, v: 100 },   // close==open => up
      { o: 10, h: 11, l: 9, c: 9.5, v: 100 },  // close<open => down
      { o: 10, h: 11, l: 9, c: 10.5, v: 100 }, // close>open => up
    ])
    const { volSeries } = buildVolumeSeriesAndYAxis(bars, 0, 2)
    expect((volSeries.data[0].itemStyle as any).color).toBe('#D3D3D3')
    expect((volSeries.data[1].itemStyle as any).color).toBe('#696969')
    expect((volSeries.data[2].itemStyle as any).color).toBe('#D3D3D3')
  })

  it('does not throw when vol_max is 0 (all-zero visible volumes)', () => {
    const bars = mkBars2([
      { o: 10, h: 11, l: 9, c: 10, v: 0 },
      { o: 10, h: 11, l: 9, c: 10, v: 0 },
    ])
    expect(() => buildVolumeSeriesAndYAxis(bars, 0, 1)).not.toThrow()
    const { volSeries, yAxisOverride } = buildVolumeSeriesAndYAxis(bars, 0, 1)
    // 兜底 visVolMax=1, 所有 value = displayBottom
    expect(volSeries.data.every(d => d.value === yAxisOverride.min)).toBe(true)
  })

  it('volume series uses borderColor black, borderWidth 0.5, opacity 0.8', () => {
    const bars = mkBars2([{ o: 10, h: 11, l: 9, c: 10, v: 100 }])
    const { volSeries } = buildVolumeSeriesAndYAxis(bars, 0, 0)
    const itemStyle = volSeries.data[0].itemStyle as any
    expect(itemStyle.borderColor).toBe('black')
    expect(itemStyle.borderWidth).toBe(0.5)
    expect(itemStyle.opacity).toBe(0.8)
  })

  it('volSeries config: type=bar, name=volume, xAxisIndex=0, yAxisIndex=0, barWidth=100%, z=1', () => {
    const bars = mkBars2([{ o: 10, h: 11, l: 9, c: 10, v: 100 }])
    const { volSeries } = buildVolumeSeriesAndYAxis(bars, 0, 0)
    expect(volSeries.type).toBe('bar')
    expect(volSeries.name).toBe('volume')
    expect(volSeries.xAxisIndex).toBe(0)
    expect(volSeries.yAxisIndex).toBe(0)
    expect(volSeries.barWidth).toBe('100%')
    expect(volSeries.z).toBe(1)
  })
})
```

- [ ] **Step 2: 跑测试确认失败**

```bash
npx vitest run tests/chart-helpers.spec.ts
```

Expected: 新加 5 个测试 FAIL（函数未定义）。

- [ ] **Step 3: 实现 buildVolumeSeriesAndYAxis**

在 `path2_web_ui/src/render/chart.ts` 末尾追加（紧接 `buildShadingMarkArea` 之后）：

```typescript
/**
 * Dev UI 1:1 复刻 — volume 叠加进价格区底部 20% 高度带。
 *
 * 计算可见区间 priceMin/Max → displayHeight = priceRange / 0.8 → displayBottom 留 10% 底部空白。
 * volScale = (displayHeight * 0.2) / visVolMax，每根 bar 的 value = displayBottom + b.v * volScale。
 * yAxis[0].min/max 必须改为 displayBottom/displayTop（不能 scale:true），让 bar baseline 落在 displayBottom。
 *
 * @param bars      完整 bars 数组
 * @param visStart  可见区间起始 bar 索引（含）
 * @param visEnd    可见区间结束 bar 索引（含）
 */
export function buildVolumeSeriesAndYAxis(bars: Bar[], visStart: number, visEnd: number) {
  const visBars = bars.slice(visStart, visEnd + 1)
  const priceMin = Math.min(...visBars.map(b => b.l))
  const priceMax = Math.max(...visBars.map(b => b.h))
  const priceRange = priceMax - priceMin
  const displayHeight = priceRange / 0.8
  const displayBottom = priceMin - displayHeight * 0.1
  const displayTop = displayBottom + displayHeight
  const visVolMax = Math.max(...visBars.map(b => b.v), 1)
  const volScale = (displayHeight * 0.2) / visVolMax

  const volSeries = {
    type: 'bar' as const,
    name: 'volume' as const,
    xAxisIndex: 0 as const,
    yAxisIndex: 0 as const,
    barWidth: '100%' as const,
    z: 1 as const,
    data: bars.map(b => ({
      value: displayBottom + b.v * volScale,
      itemStyle: {
        color: b.c >= b.o ? '#D3D3D3' : '#696969',
        borderColor: 'black',
        borderWidth: 0.5,
        opacity: 0.8,
      },
    })),
  }
  return {
    volSeries,
    yAxisOverride: { min: displayBottom, max: displayTop },
  }
}
```

- [ ] **Step 4: 跑测试确认全过**

```bash
npx vitest run tests/chart-helpers.spec.ts
```

Expected: 11 个测试全 PASS（6 个 Shading + 5 个 Volume）。

- [ ] **Step 5: 类型检查 + 既有测试**

```bash
npx vue-tsc --noEmit
npx vitest run
```

Expected: 全 PASS。

- [ ] **Step 6: Commit**

```bash
git add path2_web_ui/src/render/chart.ts path2_web_ui/tests/chart-helpers.spec.ts
git commit -m "path2_web_ui/chart: buildVolumeSeriesAndYAxis(可见 vol_max + 底部 20%)"
```

---

## Task 5: `buildBarTooltipFormatter` + 测试

**Files:**
- Modify: `path2_web_ui/src/render/chart.ts`（末尾追加 export）
- Test: `path2_web_ui/tests/chart-helpers.spec.ts`（扩）

**Interfaces:**
- Consumes: `Bar[]` + `ctrlState`（Task 2 产物）
- Produces:
  ```typescript
  export function buildBarTooltipFormatter(
    bars: Bar[], ctrlState: { isPressed: () => boolean; mouseY: () => number },
  ): (params: Array<{ seriesName: string; dataIndex: number }>) => string
  ```

- [ ] **Step 1: 写失败的单测**

在 `chart-helpers.spec.ts` 末尾追加：

```typescript
import { buildBarTooltipFormatter } from '../src/render/chart'

function mkBars3(): Bar[] {
  return [
    { date: '2024-01-01', o: 10.00, h: 11.00, l: 9.00, c: 10.50, v: 1000, rv: 0 },
    { date: '2024-01-02', o: 10.50, h: 12.00, l: 10.00, c: 11.55, v: 1500000, rv: 1.5 },
    { date: '2024-01-03', o: 11.55, h: 11.60, l: 10.80, c: 11.00, v: 800000, rv: 0 },
  ]
}

function mkCtrlState(pressed: boolean, y: number) {
  return { isPressed: () => pressed, mouseY: () => y }
}

describe('buildBarTooltipFormatter', () => {
  it('Ctrl mode returns single line "Price: {mouseY}" with 2 decimals', () => {
    const fmt = buildBarTooltipFormatter(mkBars3(), mkCtrlState(true, 12.345))
    const html = fmt([{ seriesName: 'kline', dataIndex: 1 }])
    expect(html).toBe('Price: 12.35')
  })

  it('normal mode shows 8 lines: Date/Open/High/Low/Close/Chg/Volume/RV', () => {
    const fmt = buildBarTooltipFormatter(mkBars3(), mkCtrlState(false, 0))
    const html = fmt([{ seriesName: 'kline', dataIndex: 1 }])
    const lines = html.split('<br/>')
    expect(lines).toHaveLength(8)
    expect(lines[0]).toBe('Date: 2024-01-02')
    expect(lines[1]).toBe('Open:  10.50')
    expect(lines[2]).toBe('High:  12.00')
    expect(lines[3]).toBe('Low:   10.00')
    expect(lines[4]).toBe('Close: 11.55')
    // Chg = (11.55 - 10.50) / 10.50 * 100 = 10.00%
    expect(lines[5]).toBe('Chg:   +10.00%')
    expect(lines[6]).toBe('Volume: 1,500,000')
    expect(lines[7]).toBe('RV:    1.50')
  })

  it('first bar shows Chg=N/A (no prev close)', () => {
    const fmt = buildBarTooltipFormatter(mkBars3(), mkCtrlState(false, 0))
    const html = fmt([{ seriesName: 'kline', dataIndex: 0 }])
    expect(html).toContain('Chg:   N/A')
  })

  it('RV<=0 shows RV=N/A', () => {
    const fmt = buildBarTooltipFormatter(mkBars3(), mkCtrlState(false, 0))
    // bar[2].rv = 0
    const html = fmt([{ seriesName: 'kline', dataIndex: 2 }])
    expect(html).toContain('RV:    N/A')
  })

  it('Chg negative shows minus sign', () => {
    const fmt = buildBarTooltipFormatter(mkBars3(), mkCtrlState(false, 0))
    // bar[2]: (11.00 - 11.55) / 11.55 * 100 ≈ -4.76%
    const html = fmt([{ seriesName: 'kline', dataIndex: 2 }])
    expect(html).toMatch(/Chg:\s+-4\.76%/)
  })

  it('Volume formatted with US thousand separators', () => {
    const fmt = buildBarTooltipFormatter(mkBars3(), mkCtrlState(false, 0))
    const html = fmt([{ seriesName: 'kline', dataIndex: 1 }])
    expect(html).toContain('Volume: 1,500,000')
  })

  it('returns empty string when no kline series in params', () => {
    const fmt = buildBarTooltipFormatter(mkBars3(), mkCtrlState(false, 0))
    const html = fmt([{ seriesName: 'other', dataIndex: 0 }])
    expect(html).toBe('')
  })
})
```

- [ ] **Step 2: 跑测试确认失败**

```bash
npx vitest run tests/chart-helpers.spec.ts
```

Expected: 7 个新测试 FAIL。

- [ ] **Step 3: 实现 buildBarTooltipFormatter**

在 `path2_web_ui/src/render/chart.ts` 末尾追加：

```typescript
/**
 * Bar tooltip formatter (global axis-trigger)。
 * 普通模式 8 行: Date / Open / High / Low / Close / Chg / Volume / RV
 * Ctrl 模式 1 行: Price: {mouseY:.2f}
 *
 * Ctrl 模式拿 mouseY: ctrlState.mouseY() 由 KlineChart.vue 在 chart.getZr() mousemove
 * 中 convertFromPixel({yAxisIndex:0}) 后 setMouseY 更新。
 */
export function buildBarTooltipFormatter(
  bars: Bar[],
  ctrlState: { isPressed: () => boolean; mouseY: () => number },
) {
  return (params: Array<{ seriesName?: string; dataIndex?: number }>): string => {
    if (ctrlState.isPressed()) {
      return `Price: ${ctrlState.mouseY().toFixed(2)}`
    }
    const klineParam = params.find(p => p.seriesName === 'kline')
    if (!klineParam || typeof klineParam.dataIndex !== 'number') return ''
    const idx = klineParam.dataIndex
    const b = bars[idx]
    if (!b) return ''
    const prev = idx > 0 ? bars[idx - 1] : null
    let chgStr: string
    if (prev) {
      const chg = (b.c - prev.c) / prev.c * 100
      const sign = chg >= 0 ? '+' : ''
      chgStr = `${sign}${chg.toFixed(2)}%`
    } else {
      chgStr = 'N/A'
    }
    const rvStr = b.rv > 0 ? b.rv.toFixed(2) : 'N/A'
    const volStr = Math.round(b.v).toLocaleString('en-US')
    return [
      `Date: ${b.date}`,
      `Open:  ${b.o.toFixed(2)}`,
      `High:  ${b.h.toFixed(2)}`,
      `Low:   ${b.l.toFixed(2)}`,
      `Close: ${b.c.toFixed(2)}`,
      `Chg:   ${chgStr}`,
      `Volume: ${volStr}`,
      `RV:    ${rvStr}`,
    ].join('<br/>')
  }
}
```

**注意**：`Bar` 类型当前可能没有 `rv` 字段。检查 `path2_web_ui/src/types.ts` 中的 Bar 定义，若没有 `rv` 字段需先补：

```bash
grep -n "interface Bar\|type Bar" path2_web_ui/src/types.ts
```

如果 `Bar` 没有 `rv: number`，在 Bar 接口里补一行 `rv: number`（必填字段，与后端 Task 1 契约对齐）。

- [ ] **Step 4: 跑测试确认全过**

```bash
npx vitest run tests/chart-helpers.spec.ts
```

Expected: 18 个测试全 PASS（6 Shading + 5 Volume + 7 BarTooltip）。

- [ ] **Step 5: 类型检查 + 全测试**

```bash
npx vue-tsc --noEmit
npx vitest run
```

Expected: 全 PASS。注意若 Bar 加了 rv 字段，原有 fixture 可能要补 rv（按需修复）。

- [ ] **Step 6: Commit**

```bash
git add path2_web_ui/src/render/chart.ts path2_web_ui/src/types.ts path2_web_ui/tests/chart-helpers.spec.ts
git commit -m "path2_web_ui/chart: buildBarTooltipFormatter(普通 8 行 + Ctrl 单行)"
```

---

## Task 6: `buildMarkerTooltipFormatter`（从 chart.ts 抽出，不改逻辑）

**Files:**
- Modify: `path2_web_ui/src/render/chart.ts`（把现有 `chart.ts:192-213` 的内联 formatter 抽成 export 纯函数）

**Interfaces:**
- Consumes: 现有 `TooltipPayload` 类型 + 现有 `tooltipResolver` / `matchLabel` 回调
- Produces:
  ```typescript
  export function buildMarkerTooltipFormatter(
    tooltipResolver: ((eventId: string) => TooltipPayload) | undefined,
    matchLabel: ((matchId: string) => string | null) | undefined,
  ): (params: { data?: { event_id?: string; match_id?: string } }) => string
  ```

- [ ] **Step 1: 在 chart-helpers.spec.ts 末尾加 sanity 测试**

```typescript
import { buildMarkerTooltipFormatter } from '../src/render/chart'
import type { TooltipPayload } from '../src/render/chart'

describe('buildMarkerTooltipFormatter', () => {
  it('returns matchLabel when params.data has match_id', () => {
    const matchLabel = (id: string) => `MATCH:${id}`
    const fmt = buildMarkerTooltipFormatter(undefined, matchLabel)
    expect(fmt({ data: { match_id: 'm1' } })).toBe('MATCH:m1')
  })

  it('uses tooltipResolver clauses + raw, excludes "members" key', () => {
    const resolver = (_eid: string): TooltipPayload => ({
      clauses: { c1: { measured: 5, op: '>=', threshold: 3, satisfied: true } },
      raw: { foo: 'bar', members: [1, 2, 3] },
    })
    const fmt = buildMarkerTooltipFormatter(resolver, undefined)
    const html = fmt({ data: { event_id: 'e1' } })
    expect(html).toContain('c1: 5 >= 3 ✓')
    expect(html).toContain('foo: bar')
    expect(html).not.toContain('members')
  })

  it('returns empty when no event_id and no resolver', () => {
    const fmt = buildMarkerTooltipFormatter(undefined, undefined)
    expect(fmt({ data: {} })).toBe('')
  })
})
```

- [ ] **Step 2: 跑测试确认失败**

```bash
npx vitest run tests/chart-helpers.spec.ts
```

Expected: 3 个新测试 FAIL。

- [ ] **Step 3: 抽出 buildMarkerTooltipFormatter**

定位 `path2_web_ui/src/render/chart.ts:188-213` 现有的 global tooltip 块：

```typescript
  // ── D2: tooltip formatter ─────────────────────────────────────────────────
  type TooltipOption = { trigger: string; formatter?: (params: any) => string }
  const tooltip: TooltipOption = { trigger: 'item' }
  if (tooltipResolver || matchLabel) {
    tooltip.formatter = (params: any) => {
      const matchId: string | undefined = params?.data?.match_id
      if (matchId) return (matchLabel && matchLabel(matchId)) ?? ''
      const eventId: string | undefined = params?.data?.event_id
      if (!eventId || !tooltipResolver) return ''
      const { clauses, raw } = tooltipResolver(eventId)
      const lines: string[] = []
      for (const [cid, c] of Object.entries(clauses)) {
        const opStr = c.op != null ? ` ${c.op} ${String(c.threshold)}` : ''
        const mark = c.satisfied ? '✓' : '✗'
        lines.push(`${cid}: ${String(c.measured)}${opStr} ${mark}`)
      }
      for (const [k, v] of Object.entries(raw)) {
        if (k === 'members') continue
        lines.push(`${k}: ${String(v)}`)
      }
      return lines.join('<br/>')
    }
  }
```

**保留 `TooltipOption` 局部类型定义**（仍在 `buildKlineOption` 内用），**但**把 formatter 主体抽到 `buildMarkerTooltipFormatter` 纯函数，放在文件末尾：

```typescript
/**
 * Marker tooltip formatter (series-level item-trigger)。
 * 逻辑与原 chart.ts:192-213 等价 (只搬位置不改语义):
 *  - params.data.match_id 命中 → matchLabel 行
 *  - params.data.event_id 命中 + tooltipResolver → clauses + raw (excl. "members")
 */
export function buildMarkerTooltipFormatter(
  tooltipResolver: ((eventId: string) => TooltipPayload) | undefined,
  matchLabel: ((matchId: string) => string | null) | undefined,
) {
  return (params: { data?: { event_id?: string; match_id?: string } }): string => {
    const matchId = params?.data?.match_id
    if (matchId) return (matchLabel && matchLabel(matchId)) ?? ''
    const eventId = params?.data?.event_id
    if (!eventId || !tooltipResolver) return ''
    const { clauses, raw } = tooltipResolver(eventId)
    const lines: string[] = []
    for (const [cid, c] of Object.entries(clauses)) {
      const opStr = c.op != null ? ` ${c.op} ${String(c.threshold)}` : ''
      const mark = c.satisfied ? '✓' : '✗'
      lines.push(`${cid}: ${String(c.measured)}${opStr} ${mark}`)
    }
    for (const [k, v] of Object.entries(raw)) {
      if (k === 'members') continue
      lines.push(`${k}: ${String(v)}`)
    }
    return lines.join('<br/>')
  }
}
```

**暂不动 chart.ts:188-213 的 `tooltip` 变量** —— Task 7 会重写。

- [ ] **Step 4: 跑测试确认全过**

```bash
npx vitest run tests/chart-helpers.spec.ts
```

Expected: 21 个测试全 PASS（含 3 个 Marker）。

- [ ] **Step 5: 类型检查 + 全测试**

```bash
npx vue-tsc --noEmit
npx vitest run
```

Expected: 全 PASS。

- [ ] **Step 6: Commit**

```bash
git add path2_web_ui/src/render/chart.ts path2_web_ui/tests/chart-helpers.spec.ts
git commit -m "path2_web_ui/chart: 抽 buildMarkerTooltipFormatter(原 chart.ts:192-213 逻辑等价搬出)"
```

---

## Task 7: chart.ts 整合 — grid 重排 + 4 helpers + axisPointer override + tooltip 拆分

**Files:**
- Modify: `path2_web_ui/src/render/chart.ts`（主要在 `buildKlineOption` 内部）
- Test: `path2_web_ui/tests/chart.spec.ts`（按需扩，断言 grid/xAxis/dataZoom 数与 markArea 配置）

**Interfaces:**
- Consumes: Task 3/4/5/6 的 4 个 helper exports + Task 2 的 ctrlState（chart.ts 内 import ctrlState）
- Produces: `buildKlineOption` 返回的 option 反映：
  - `grid.length === 2`、`xAxis.length === 2`
  - candlestick series 上挂 `markArea`（来自 `buildShadingMarkArea` 或 null）
  - volume series 用 `buildVolumeSeriesAndYAxis(bars, startIdx, endIdx)` 结果
  - yAxis[0] `min/max` 来自 yAxisOverride
  - `dataZoom[*].start/end` 落到 `[startIdx/N, (endIdx+1)/N] * 100`（有 buffer 时）或 `0/100`（无 buffer 时）
  - global `tooltip: { trigger: 'axis', axisPointer: { type: 'cross', ... }, formatter: buildBarTooltipFormatter(...) }`
  - 每个 marker series（points/intervals/bandLabels/highlight/brackets/price-points/satellites/highlight-price）挂 series-level `tooltip: { trigger: 'item', formatter: buildMarkerTooltipFormatter(...) }`
  - `axisPointer.link: [{ xAxisIndex: [0, 1] }]`
- **签名延伸**：`buildKlineOption` 需新增可选输入 `scanRange?: { startIdx: number; endIdx: number }` 与 `barCount: bars.length` —— 用于算阴影 + dataZoom 落点。`strictWindow` 字段可复用（已存在），但语义现在变成"灰区 + 初始 zoom"的双重驱动。

- [ ] **Step 1: 扩 chart.spec.ts 加 5 项断言（先红）**

读 `path2_web_ui/tests/chart.spec.ts` 当前结构，找 `buildKlineOption` 的现有测试用例（描述 grid/dataZoom 那段），在末尾追加：

```typescript
describe('Dev UI replication (Task 7 integration)', () => {
  function mkBars(n: number): Bar[] {
    return Array.from({ length: n }, (_, i) => ({
      date: `2024-01-${String(i + 1).padStart(2, '0')}`,
      o: 10, h: 11, l: 9, c: 10, v: 100, rv: 1,
    }))
  }

  it('grid layout: 2 grids (was 3)', () => {
    const bars = mkBars(10)
    const opt = buildKlineOption(bars, [], [], <minimal BandRenderInput——按现有 chart.spec.ts 风格构造>)
    expect((opt.grid as any[]).length).toBe(2)
  })

  it('xAxis: 2 axes', () => {
    const bars = mkBars(10)
    const opt = buildKlineOption(bars, [], [], <...>)
    expect((opt.xAxis as any[]).length).toBe(2)
  })

  it('dataZoom initial range locks to [startIdx, endIdx+1] / N * 100', () => {
    const bars = mkBars(10)
    const opt = buildKlineOption(bars, [], [], {
      ...<base>,
      strictWindow: { startIdx: 2, endIdx: 7 },
    })
    const dz0 = (opt.dataZoom as any[])[0]
    expect(dz0.start).toBeCloseTo(20, 5)   // 2/10*100
    expect(dz0.end).toBeCloseTo(80, 5)     // (7+1)/10*100
  })

  it('candlestick series carries markArea with two shading segments when buffer exists both sides', () => {
    const bars = mkBars(10)
    const opt = buildKlineOption(bars, [], [], {
      ...<base>,
      strictWindow: { startIdx: 2, endIdx: 7 },
    })
    const kline = (opt.series as any[]).find(s => s.name === 'kline')
    expect(kline.markArea).toBeDefined()
    expect(kline.markArea.data).toHaveLength(2)
  })

  it('global tooltip is axis-trigger with cross axisPointer', () => {
    const bars = mkBars(10)
    const opt = buildKlineOption(bars, [], [], <...>)
    expect((opt.tooltip as any).trigger).toBe('axis')
    expect((opt.tooltip as any).axisPointer.type).toBe('cross')
  })
})
```

> **说明**：`<minimal BandRenderInput>` / `<base>` 占位由实施者按 `chart.spec.ts` 现有 fixture 风格补齐——chart.spec.ts 里已经在用，直接复用。

- [ ] **Step 2: 跑测试确认失败**

```bash
npx vitest run tests/chart.spec.ts
```

Expected: 新加 5 个测试 FAIL。

- [ ] **Step 3: 改 chart.ts 函数签名（小步）**

`buildKlineOption` 已有 `strictWindow?: { startIdx: number; endIdx: number } | null`，本任务不改签名、继续用。

- [ ] **Step 4: 替换 grid / xAxis / yAxis / dataZoom**

在 `buildKlineOption` 内（约 `chart.ts:230-260` 段），把原 `grid: [...3...]` / `xAxis: [...3...]` / `yAxis: [...4...]` / `dataZoom: [{ xAxisIndex: [0,1,2], start: 0, end: 100 }, ...]` 替换为：

```typescript
  // ── Dev UI 复刻: grid 3→2、初始 zoom 贴 [startIdx, endIdx]、yAxis[0] 动态 min/max ──
  const N = bars.length
  const sw = strictWindow ?? null
  const hasBuffer = sw !== null && (sw.startIdx > 0 || sw.endIdx < N - 1)
  const zoomStart = hasBuffer ? (sw!.startIdx / N) * 100 : 0
  const zoomEnd = hasBuffer ? ((sw!.endIdx + 1) / N) * 100 : 100

  // 初始可见区间 = 严格 scan 窗（有 buffer）或全集
  const initVisStart = sw ? sw.startIdx : 0
  const initVisEnd = sw ? sw.endIdx : N - 1

  // volume + yAxis override (可见区间口径)
  const { volSeries, yAxisOverride } = buildVolumeSeriesAndYAxis(bars, initVisStart, initVisEnd)

  // 灰阴影 markArea (含 off-by-one 修正)
  const shadingMarkArea = sw
    ? buildShadingMarkArea(bars, bars[sw.startIdx].date, bars[sw.endIdx].date)
    : null
```

替换 grid / xAxis / yAxis / dataZoom 块为：

```typescript
    grid: [
      { left: 56, right: 16, top: 40, height: '72%' },     // 新 grid0 价格(含 volume 叠加)
      { left: 56, right: 16, top: '76%', height: '18%' },  // 新 grid1 markers (原 grid2)
    ],
    xAxis: [
      { type: 'category', data: dates, gridIndex: 0, boundaryGap: true,
        axisLine: { onZero: false }, splitLine: { show: false }, min: 'dataMin', max: 'dataMax' },
      { type: 'category', data: dates, gridIndex: 1, boundaryGap: true,
        axisLine: { onZero: false }, axisLabel: { show: false }, splitLine: { show: false } },
    ],
    yAxis: [
      // index 0: 价格(grid0)——固定 min/max 让 volume bar baseline 落在 displayBottom
      { gridIndex: 0, splitArea: { show: true }, min: yAxisOverride.min, max: yAxisOverride.max },
      // index 1: 隐藏 bracket 轴(grid0)
      { scale: true, gridIndex: 0, show: false },
      // index 2: 隐藏 marker 轴(grid1)
      { scale: true, gridIndex: 1, show: false },
    ],
    dataZoom: [
      { type: 'inside', xAxisIndex: [0, 1], start: zoomStart, end: zoomEnd },
      { type: 'slider', xAxisIndex: [0, 1], top: '92%', start: zoomStart, end: zoomEnd },
    ],
```

- [ ] **Step 5: 替换 tooltip + axisPointer**

把现有 `chart.ts:188-213` 的 global `tooltip` 块改写为：

```typescript
  // ── Dev UI 复刻: global axis-trigger bar tooltip + 横线锁 close 由 KlineChart.vue 监听 updateAxisPointer 处理 ──
  const tooltip = {
    trigger: 'axis' as const,
    axisPointer: {
      type: 'cross' as const,
      lineStyle: { color: '#0088CC', type: 'dashed', width: 1.5, opacity: 0.7 },
      label: { show: false },
      snap: true,
    },
    formatter: buildBarTooltipFormatter(bars, ctrlState),
  }

  const markerTooltip = (tooltipResolver || matchLabel)
    ? { trigger: 'item' as const, formatter: buildMarkerTooltipFormatter(tooltipResolver, matchLabel) }
    : undefined
```

并在文件顶部 `import` 区加：

```typescript
import { ctrlState } from './ctrlState'
```

- [ ] **Step 6: 替换 axisPointer.link 与 candlestick series 的 markLine→markArea**

定位 `chart.ts` 里 `axisPointer: { link: [{ xAxisIndex: [0, 1, 2] }] }`，改为 `[0, 1]`。

定位 candlestick series（`name: 'kline'`），删 `markLine` 配置，加 `markArea`：

```typescript
  const klineSeries: Record<string, unknown> = {
    type: 'candlestick', name: 'kline', data: candle, xAxisIndex: 0, yAxisIndex: 0,
  }
  if (shadingMarkArea) {
    klineSeries.markArea = shadingMarkArea
  }
```

- [ ] **Step 7: 替换原 volume series 引用**

定位原 `chart.ts:263-264` 的 volume bar series（`{ type: 'bar', name: 'volume', data: volume, xAxisIndex: 1, yAxisIndex: 1, ... }`），整段替换为引用 `volSeries`：

```typescript
      // 成交量(叠加在 grid0 价格区底部 20%，来自 buildVolumeSeriesAndYAxis)
      volSeries,
```

- [ ] **Step 8: Remap series xAxisIndex/yAxisIndex**

对 series 数组里所有 marker 系列：
- `points`: `xAxisIndex: 2, yAxisIndex: 2` → `xAxisIndex: 1, yAxisIndex: 2`
- `intervals`: 同 points
- `bandLabels`: 同 points
- `highlight`: 同 points
- `brackets`: `xAxisIndex: 0, yAxisIndex: 3` → `xAxisIndex: 0, yAxisIndex: 1`
- `price-points`: 不变（xAxisIndex: 0, yAxisIndex: 0）
- `satellites`: 不变
- `highlight-price`: 不变

并对**每个** marker series（无论 grid0 或 grid1 上的）添加 `tooltip: markerTooltip`：

```typescript
      { type: 'custom', name: 'points', xAxisIndex: 1, yAxisIndex: 2, data: pointData,
        renderItem: renderPoint, encode: { x: 0 }, z: 10, tooltip: markerTooltip },
      // ... 其余 series 同样追加 tooltip: markerTooltip
```

- [ ] **Step 9: 在新 grid1（markers 区）也叠灰阴影**

为了"两 grid 视觉一致"（spec §3.3 要求），在 grid1 上的任一 marker series（例如 `bandLabels`）上也挂同样的 `shadingMarkArea`：

```typescript
      { type: 'custom', name: 'bandLabels', xAxisIndex: 1, yAxisIndex: 2,
        data: bandLabelData,
        renderItem: <...renderBandLabel...>,
        markArea: shadingMarkArea ?? undefined,
        tooltip: markerTooltip },
```

> 若 bandLabels 数据为空，可挑另一个 grid1 series（如 points 或 intervals）挂 markArea；目标只是覆盖 grid1 区域。

- [ ] **Step 10: 跑全部测试**

```bash
npx vue-tsc --noEmit
npx vitest run
```

Expected: 全 PASS（含本任务新加 5 个 + 原有所有）。如果原 chart.spec.ts 的某些 fixture 因签名/字段变更而失败，逐个修正（按新 grid/xAxis 数调断言）。

- [ ] **Step 11: Commit**

```bash
git add path2_web_ui/src/render/chart.ts path2_web_ui/tests/chart.spec.ts
git commit -m "path2_web_ui/chart: grid 3→2 + 集成 4 helpers + axisPointer cross + tooltip 拆分"
```

---

## Task 8: KlineChart.vue 订阅 ctrlState + zr mousemove + datazoom 重算 vol

**Files:**
- Modify: `path2_web_ui/src/components/KlineChart.vue`
- Test: `path2_web_ui/tests/components/ChartArea.spec.ts` 或类似（按需扩组件测试）

**Interfaces:**
- Consumes: `ctrlState` (Task 2)、`buildVolumeSeriesAndYAxis` (Task 4)、`chart` 实例（由 KlineChart.vue 创建的 ECharts 实例）
- Produces: 三个运行时副作用：
  1. Ctrl 切换 → `chart.setOption` 改 axisPointer 颜色 + snap
  2. 鼠标移动 → `ctrlState.setMouseY(...)`
  3. 用户 zoom/pan → 重算 volSeries.data + yAxis[0].min/max 并 setOption

- [ ] **Step 1: 读现有 KlineChart.vue**

```bash
grep -n "onMounted\|onUnmounted\|chart\\.\|setOption\|getZr\|datazoom\|on(\|mousemove" path2_web_ui/src/components/KlineChart.vue | head -30
```

定位 setup 块、onMounted、chart 实例变量名。

- [ ] **Step 2: 加 ctrlState 订阅**

在 KlineChart.vue 的 `<script setup>` 段，import ctrlState：

```typescript
import { ctrlState } from '../render/ctrlState'
import { buildVolumeSeriesAndYAxis } from '../render/chart'
```

onMounted 块内（在 `chart.setOption(option)` 之后）：

```typescript
const unsubCtrl = ctrlState.subscribe((pressed) => {
  chart.setOption({
    tooltip: {
      axisPointer: {
        lineStyle: { color: pressed ? '#FF6600' : '#0088CC' },
        snap: !pressed,
      },
    },
  })
})

// 鼠标移动 → 维护 ctrlState.mouseY
chart.getZr().on('mousemove', (e: { offsetX: number; offsetY: number }) => {
  const arr = chart.convertFromPixel({ yAxisIndex: 0 }, [e.offsetX, e.offsetY])
  if (Array.isArray(arr) && typeof arr[1] === 'number') {
    ctrlState.setMouseY(arr[1])
  }
})

// 用户 zoom/pan → 重算 volume scale + yAxis
chart.on('datazoom', () => {
  const dz = (chart.getOption() as any).dataZoom?.[0]
  if (!dz) return
  const start = typeof dz.start === 'number' ? dz.start : 0
  const end = typeof dz.end === 'number' ? dz.end : 100
  const N = bars.value.length
  const visStart = Math.max(0, Math.round((start / 100) * N))
  const visEnd = Math.min(N - 1, Math.round((end / 100) * N) - 1)
  if (visEnd < visStart) return
  const { volSeries, yAxisOverride } = buildVolumeSeriesAndYAxis(bars.value, visStart, visEnd)
  chart.setOption({
    series: [{ name: 'volume', data: volSeries.data }],
    yAxis: [{ min: yAxisOverride.min, max: yAxisOverride.max }, {}, {}],   // 仅改 yAxis[0]
  })
})
```

onUnmounted 块：

```typescript
unsubCtrl()
chart.getZr().off('mousemove')
chart.off('datazoom')
```

> **注意**：实际 KlineChart.vue 的 chart 实例变量名、bars 变量名可能与示例不同；按现有约定改名。`yAxis` 数组里 `{}` 是占位（不动 index 1/2），ECharts 允许只更新指定 axis 的字段。

- [ ] **Step 3: 横线锁 close — updateAxisPointer 监听**

继续在 onMounted 内加：

```typescript
chart.on('updateAxisPointer', (e: any) => {
  if (ctrlState.isPressed()) return  // Ctrl 模式跳过，让 ECharts 默认横线跟鼠标
  // 取首个 axis 信息找 dataIndex
  const dataIdx = e?.dataIndex ?? e?.seriesAxesInfo?.[0]?.dataIndex
  if (typeof dataIdx !== 'number') return
  const b = bars.value[dataIdx]
  if (!b) return
  // 锁 y axisPointer 到 bars[idx].c
  chart.setOption({
    tooltip: { axisPointer: { /* ECharts y axisPointer value 字段，实施时查文档确认 */ value: b.c, axis: 'y' } },
  })
})
```

**实施备注**：ECharts API 里"锁 y axisPointer value"具体字段语法不稳定，若 setOption 路径不通，回退到**方案 2**——在 candlestick series 上动态加 `markLine: { data: [{ yAxis: b.c }] }`，每次 updateAxisPointer 都 setOption 更新。两方案任选可达效果即可，spec 已明确允许。

onUnmounted 加 `chart.off('updateAxisPointer')`。

- [ ] **Step 4: vue-tsc 类型检查**

```bash
cd /home/yu/PycharmProjects/Trade_Strategy-bo/path2_web_ui
npx vue-tsc --noEmit
```

Expected: 无类型错误。

- [ ] **Step 5: build 验证**

```bash
npm run build
```

Expected: 成功（无编译错误）。

- [ ] **Step 6: 全 vitest 不回归**

```bash
npx vitest run
```

Expected: 全 PASS。

- [ ] **Step 7: Commit**

```bash
git add path2_web_ui/src/components/KlineChart.vue
git commit -m "path2_web_ui/KlineChart: 订阅 ctrlState + zr mousemove + datazoom 重算 vol + 横线锁 close"
```

---

## Task 9: Playwright E2E 多场景截图验证

**Files:**
- Create: `path2_web_ui/e2e/dev-ui-replication.spec.ts`

**Interfaces:**
- Consumes: 运行中的 path2_web 后端 + path2_web_ui 前端（按 memory `project_path2_web_buffered_labels` 既有 E2E 方法启动）
- Produces: 四个场景截图 + 显式断言

- [ ] **Step 1: 读现有 E2E spec 风格**

```bash
ls path2_web_ui/e2e/
head -80 path2_web_ui/e2e/flow.spec.ts
```

确认 Playwright config、fixtures、启动 server 的方式。

- [ ] **Step 2: 写 E2E spec**

创建 `path2_web_ui/e2e/dev-ui-replication.spec.ts`：

```typescript
import { test, expect } from '@playwright/test'

/**
 * Dev UI 复刻 E2E（参照 path2_web_buffered_labels 既有方法启动 server + 扫描出命中）。
 *
 * 4 个场景:
 *  1. 初始加载: viewport 严格落在 [scan_start, scan_end]，左右灰区不可见
 *  2. 左滑后: 左侧灰区可见，bars[startIdx] 在白区（off-by-one 修正）
 *  3. hover bar + Ctrl 切换: 普通 8 行 + 蓝色横线，Ctrl 模式 Price: x.xx + 橙色横线
 *  4. hover marker: marker tooltip 优先（含 path2 clauses + raw）
 */

test.describe('Dev UI replication', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    // <按既有 E2E 方法触发扫描 + 选第一只命中股票，逻辑参考 flow.spec.ts>
  })

  test('initial viewport locks to [scan_start, scan_end]', async ({ page }) => {
    const chart = page.locator('.kline-chart canvas').first()
    await expect(chart).toBeVisible()
    // 初始截图（灰区不可见）
    await expect(page).toHaveScreenshot('initial-viewport.png', { maxDiffPixels: 200 })
  })

  test('after pan left, grey buffer becomes visible and scan_start bar stays in white', async ({ page }) => {
    const chart = page.locator('.kline-chart canvas').first()
    await chart.hover()
    // ECharts 的 dataZoom inside 模式：模拟左滑（按 spec 既有 scroll/drag 测试方法）
    const box = await chart.boundingBox()
    if (!box) test.fail()
    await page.mouse.move(box!.x + box!.width / 2, box!.y + box!.height / 2)
    await page.mouse.wheel(-200, 0)  // 左滑出 buffer
    await page.waitForTimeout(300)
    await expect(page).toHaveScreenshot('after-pan-left.png', { maxDiffPixels: 200 })
  })

  test('hover bar shows 8-line tooltip; Ctrl toggles to Price single line', async ({ page }) => {
    const chart = page.locator('.kline-chart canvas').first()
    const box = await chart.boundingBox()
    if (!box) test.fail()
    await page.mouse.move(box!.x + box!.width * 0.5, box!.y + box!.height * 0.4)
    await page.waitForTimeout(200)
    // 普通模式 tooltip 含 Date/Open/Close/Chg/Volume/RV 关键字
    const tooltipNormal = page.locator('.ec-tooltip, [class*="tooltip"]').first()
    await expect(tooltipNormal).toContainText('Date:')
    await expect(tooltipNormal).toContainText('Volume:')
    await expect(tooltipNormal).toContainText('RV:')
    // 按 Ctrl
    await page.keyboard.down('Control')
    await page.mouse.move(box!.x + box!.width * 0.5, box!.y + box!.height * 0.4 + 1)  // 触发 mousemove
    await page.waitForTimeout(200)
    await expect(tooltipNormal).toContainText('Price:')
    await expect(tooltipNormal).not.toContainText('Volume:')
    await page.keyboard.up('Control')
  })

  test('hover marker shows marker tooltip not bar tooltip', async ({ page }) => {
    // <定位 grid1 markers 区某个 marker；按既有方法获取 marker 像素位置>
    // 然后 hover 上面，断言 tooltip 含 path2 内省字段而非 Date/Volume
    await expect(page).toHaveScreenshot('hover-marker.png', { maxDiffPixels: 200 })
  })
})
```

> **实施提醒**：spec 里的 `<...>` 占位由实施者按 `flow.spec.ts` 等既有 E2E 现成 helper 补齐（启动 server、选股票、模拟交互的样板代码）。**不要发明新框架/库**——只用 path2_web_ui 已有的 Playwright fixtures。

- [ ] **Step 3: 跑 E2E（首次生成 baseline screenshot）**

```bash
cd /home/yu/PycharmProjects/Trade_Strategy-bo/path2_web_ui
npx playwright test e2e/dev-ui-replication.spec.ts --update-snapshots
```

Expected: 4 个测试全 PASS（首次生成 baseline）。如果有失败，调整 fixture 或断言。

- [ ] **Step 4: 再次跑确认稳定**

```bash
npx playwright test e2e/dev-ui-replication.spec.ts
```

Expected: 全 PASS。

- [ ] **Step 5: 全测试无回归**

```bash
cd /home/yu/PycharmProjects/Trade_Strategy-bo
uv run pytest tests/path2_web/ -v
cd path2_web_ui
npx vitest run
npx vue-tsc --noEmit
npm run build
```

Expected: 全 PASS / 全绿。

- [ ] **Step 6: Commit**

```bash
cd /home/yu/PycharmProjects/Trade_Strategy-bo
git add path2_web_ui/e2e/dev-ui-replication.spec.ts path2_web_ui/e2e/dev-ui-replication.spec.ts-snapshots/
git commit -m "path2_web_ui/e2e: dev UI 复刻 4 场景 Playwright 截图验证"
```

---

## Self-Review Checklist (本 plan 写完后自检)

- [x] **Spec coverage**:
  - 初始显示范围（灰区+严格 zoom）→ Task 3 + Task 7
  - Grid 重排 3→2 → Task 7
  - Volume 叠加 + 跟随 zoom 重算 → Task 4 + Task 7 + Task 8
  - 十字线（竖线吸附 bar 中心 + 横线锁 close）→ Task 7 (axisPointer) + Task 8 (updateAxisPointer 监听)
  - Bar tooltip 8 行 → Task 5 + Task 7
  - Marker tooltip 优先 → Task 6 + Task 7
  - Ctrl 解锁横线 → Task 2 + Task 8
  - 后端 rv → Task 1
- [x] **Placeholder scan**: 已扫，无 TBD/TODO；Task 7 / Task 9 中允许 implementer 现场补 fixture 处已明确标注（chart.spec.ts 现有风格、E2E 用现有 helper）。
- [x] **Type consistency**: `ctrlState` 接口签名在 Task 2 定义，Task 5 / Task 7 / Task 8 引用一致；`buildVolumeSeriesAndYAxis` 返回值结构 Task 4 与 Task 7 / Task 8 引用一致；`buildShadingMarkArea` 返回值结构 Task 3 与 Task 7 一致；Bar 类型加 rv 字段在 Task 5 明确处理。
- [x] **Plan 不拆段**: 9 task 单 session 跑完，无前段实施大分叉迫使后段重写的判据。

---

## Execution Handoff

**Plan 已保存到** `docs/superpowers/plans/2026-06-23-path2-web-dev-ui-replication.md`。

两种执行方式：

1. **Subagent-Driven（推荐）** — 每 task fresh subagent + 两段审（Implementer=sonnet / Reviewer=opus），用户在 task 间审查中间结果。
2. **Inline Execution** — 当前 session 用 `executing-plans` 串跑，含 checkpoint。

按用户既定偏好：**默认 Subagent-Driven**，executing-plans 在新 session。
