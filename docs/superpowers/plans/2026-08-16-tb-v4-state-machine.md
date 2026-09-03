# tb v4 三态状态机 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 t4 throwback detector——post-burst 三态价格行为状态机(UP/DOWN/STABLE,即时 median TR,ratchet 失效线),替换 bb 的 tb node,并落地配套(path2_web 样本消费窗截取、eval 去重、前端副图分色)。

**Architecture:** 新建公共 atom `path2/atoms/throwback_v4.py`(纯状态机函数 + 事件类 + detector,消费 burst 流);bb app 换接线(node id 保持 `tb`);path2_web 的 label 消费面加双边样本窗截取 + eval 聚合加 (symbol,date) 去重视图;前端副图 band 按 end_date 分色。既有 `throwback.py`/`throwback_v1.py`/`throwback_v3.py` 三代**全部不动**。

**Tech Stack:** Python 3.12 + pandas/numpy(path2);Vue3 + TS + ECharts + canvas 副图(path2_web_ui)。

**Spec:** `docs/superpowers/specs/2026-08-16-tb-v4-state-machine-design.md`(定稿;本 plan 从 spec 立论,执行者两份都读)

## Global Constraints

- 本 plan 中所有项目内路径均相对 repo root。
- 测试命令:`uv run pytest <文件>::<测试> -x -q`;前端:`cd path2_web_ui && npx vue-tsc --noEmit && npm run build`(vitest:`npx vitest run <文件>`)。
- 参数定值(spec §8,构造器默认值,逐字抄):`max_rise_k=1.5, stop_confirm_bars=1, vol_window=14, anchor_mode='span_min', max_span=60, measure='close'`。
- 词表:段 outcome ∈ `('rise','weak','break','timeout')`;容器 `machine_outcome ∈ ('break','budget')`。
- 检查顺序(spec §2,不得偏离):全局退出 → 状态转换 → 状态内更新;DOWN 内 rise 臂优先于 stable 计数;peak 更新先于 UP→DOWN 判定;全部严格不等式(`<` 破线/刷新,`>` 反弹,等值不触发)。
- vol(i) = median TR over `[i-vol_window, i-1]`(**不含当根**);vol NaN → rise 臂该 bar 降级不触发,不整机终止。
- 不设 `seg_max`、不设段字段 `trough_price`、无 scb rising 模式、无 stop signal(spec 终审裁决)。
- 事件类遵守 `path2/core.py::Event` 契约(frozen dataclass、kw_only 的 node_id/instance_idx/instance_id 由物化注入、frozen 容器字段一律 tuple)。
- 每个 task:TDD(先 RED 后 GREEN)、独立 commit;commit message 中文、结尾加 `Co-Authored-By: Claude <noreply@anthropic.com>`。
- 实现期凡遇与本 plan 字面冲突处,以 spec 为准;spec 也没有的,现场读代码(锚点已给)定案并在 commit message 里记录偏差。

---

### Task 1: calc 层 `calculate_tr_median`

**Files:**
- Modify: `path2/calc/atr.py`(文件末追加函数)
- Test: `tests/path2/test_calc_atr.py`(文件末追加)

**Interfaces:**
- Produces: `calculate_tr_median(highs: pd.Series, lows: pd.Series, closes: pd.Series, window: int = 14) -> pd.Series`——`vol[i] = median(TR[i-window, i-1])`,热身(i-window<0)为 NaN。Task 3 的 detect 用它预计算 vol 数组。

- [ ] **Step 1: 写失败测试**(追加到 `tests/path2/test_calc_atr.py`)

```python
class TestCalculateTrMedian:
    """t4 vol 单元:median TR 滚动中位数,shift(1) 不含当根。"""

    def _mk(self, closes, window=3):
        n = len(closes)
        return (pd.Series(closes, dtype=float),                    # highs = closes
                pd.Series(closes, dtype=float),                    # lows = closes
                pd.Series(closes, dtype=float))                    # closes

    def test_excludes_current_bar(self):
        # TR 全为 0(high=low=close → TR=0 except 首根 prev_close=NaN 支路),
        # 再放一根大 TR 在中间,验证当根大 TR 不抬高自己
        closes = [10.0] * 8
        closes[5] = 20.0          # i=5 的 TR = max(0, |20-10|, |20-10|) = 10
        h, l, c = self._mk(closes)
        vol = calculate_tr_median(h, l, c, window=3)
        assert np.isnan(vol.iloc[4])                     # [4-3,3] = TR[1..3] = 0+0+0? -> 见下:TR[0] NaN 支路
        # 精确口径:vol[6] = median(TR[3],TR[4],TR[5]) = median(0,0,10) = 0
        assert vol.iloc[6] == 0.0
        # vol[7] = median(TR[4],TR[5],TR[6]) = median(0,10,0) = 0 —— 大 TR 只影响后续窗
        assert vol.iloc[7] == 0.0

    def test_warmup_nan(self):
        h, l, c = self._mk([10.0, 11.0, 12.0, 13.0, 14.0], window=3)
        vol = calculate_tr_median(h, l, c, window=3)
        # vol[i] 需要 TR[i-3..i-1];TR[0] 含 NaN 支路(prev_close NaN → pandas max 仍可用
        # h-l=0;abs 差为 NaN → max(axis=1) 默认 skipna 取 0)。实现须保证:
        assert np.isnan(vol.iloc[3])                     # TR[0] 起算窗不足 3 个有效 TR
        assert not np.isnan(vol.iloc[4])                 # TR[1..3] 有效

    def test_median_not_mean(self):
        # TR 序列 [1,1,1,100]:mean=25.75 被 100 拉爆,median 免疫
        closes = [10.0, 11.0, 12.0, 13.0, 113.0, 114.0]
        h = pd.Series(closes); l = pd.Series(closes); c = pd.Series(closes)
        vol = calculate_tr_median(h, l, c, window=4)
        # vol[5] = median(TR[1],TR[2],TR[3],TR[4]) = median(1,1,1,100) = 1
        assert vol.iloc[5] == 1.0
```

注意 `test_warmup_nan` 对 TR[0] 的口径:实现里 `prev_close=closes.shift(1)` 使 TR[0] 的两支路为 NaN,`pd.concat(...).max(axis=1)` 默认 skipna 会把 TR[0] 算成 `high-low`。为让热身语义明确,实现**显式**把 TR[0] 置 NaN(与 Wilder ATR 前 period-1 NaN 的惯例一致),这样 `vol[i]` 在 `[i-window, i-1]` 含 TR[0] 时即 NaN。

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/path2/test_calc_atr.py::TestCalculateTrMedian -x -q`
Expected: FAIL(`ImportError: cannot import name 'calculate_tr_median'`)

- [ ] **Step 3: 实现**(追加到 `path2/calc/atr.py` 末尾)

```python
def calculate_tr_median(highs: pd.Series, lows: pd.Series, closes: pd.Series,
                        window: int = 14) -> pd.Series:
    """t4 波动率单元:vol[i] = median(TR) over [i-window, i-1](不含当根)。

    TR = max(high-low, |high-prev_close|, |low-prev_close|);TR[0] 显式置 NaN
    (prev_close 不存在),窗口含 TR[0] → NaN(热身)。shift(1) 避开当根自指
    (当根大 TR 会同时抬高自己的反弹阈值)。中位数而非均值:TR 右偏,burst 段
    大 TR 拉爆均值;median 表征「典型波动」(spec §1)。
    """
    prev_close = closes.shift(1)
    tr = pd.concat([
        highs - lows,
        (highs - prev_close).abs(),
        (lows - prev_close).abs(),
    ], axis=1).max(axis=1)
    tr.iloc[0] = np.nan
    return tr.rolling(window).median().shift(1)
```

- [ ] **Step 4: 跑测试确认通过 + 全文件回归**

Run: `uv run pytest tests/path2/test_calc_atr.py -q`
Expected: 全 PASS(既有 Wilder ATR / rolling_atr_pct_nanmedian 测试零回归)

- [ ] **Step 5: Commit**

```bash
git add path2/calc/atr.py tests/path2/test_calc_atr.py
git commit -m "feat(calc): calculate_tr_median —— t4 即时 median TR 波动率单元

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 2: 状态机纯函数 `enumerate_segments_v4`

**Files:**
- Create: `path2/atoms/throwback_v4.py`
- Create: `tests/path2/atoms/test_throwback_v4.py`

**Interfaces:**
- Consumes: 无(Task 1 的 vol 由 Task 3 接,本 task 直接注入数组)
- Produces(Task 3/4 依赖,签名逐字):
  - `TbV4Seg = NamedTuple('TbV4Seg', enter=int, exit=int, outcome=str)`
  - `TbV4MachineResult = NamedTuple('TbV4MachineResult', segments=tuple, machine_outcome=str)`
  - `enumerate_segments_v4(closes: np.ndarray, opens: np.ndarray, bo_idx: int, global_bottom: float, vol: np.ndarray, *, max_rise_k: float = 1.5, stop_confirm_bars: int = 1, max_span: int = 60, on_gate=None, vol_window: int = 14) -> TbV4MachineResult`
  - `on_gate` 本 task 仅占位(默认 None 不消费),Task 4 实现三 gate emit。

- [ ] **Step 1: 写测试文件**(全部一次写出;测试直接注入 closes/opens/vol 数组,vol 全 1.0 → rise 阈值 = trough + max_rise_k)

```python
"""tb v4 状态机纯函数测试:判据逐条 + 不变式。vol 注入式(绕开 TR 计算)。"""
import numpy as np

from path2.atoms.throwback_v4 import TbV4MachineResult, enumerate_segments_v4


def mk(closes, opens=None, vol=1.0):
    """造 (closes, opens, vol) 数组。opens 缺省 = close*0.99(全部非阴线)。"""
    closes = np.asarray(closes, dtype=float)
    opens = (np.asarray(opens, dtype=float) if opens is not None
             else closes * 0.99)
    vol = np.full(len(closes), float(vol))
    return closes, opens, vol


def run(closes, opens=None, vol=1.0, bo=3, gbot=50.0, k=1.5, K=1, ms=60):
    c, o, v = mk(closes, opens, vol)
    return enumerate_segments_v4(c, o, bo, gbot, v, max_rise_k=k,
                                 stop_confirm_bars=K, max_span=ms)


class TestUpToDown:
    def test_decline_bar_triggers(self):
        # i=4 收跌(99<100)→ DOWN,trough=99;i=5 不刷新 count=1 → STABLE enter=5
        r = run([100, 100, 100, 100, 99, 99.2, 99.3, 99.4])
        assert r.segments[0].enter == 5
        assert r.machine_outcome in ('break', 'budget')

    def test_gapup_red_candle_triggers(self):
        # i=4 高开阴线:close=100.5 > close[3]=100(不收跌)但 close<open=101 → 阴线臂触发
        r = run([100, 100, 100, 100, 100.5, 100.6], opens=[99]*4 + [101, 100.4])
        # i=4 转 DOWN trough=100.5;i=5 close=100.6 > trough? 不刷新,不阴线(100.6>100.4),
        # 不收跌(100.6>100.5)→ UP?i=5 处于 DOWN:close[5]=100.6 > trough+1.5=102 不 rise;
        # 不刷新 → count=1 ≥1 → STABLE enter=5
        assert r.segments[0].enter == 5

    def test_green_up_bar_stays_up(self):
        # 全阳线收涨 → 全程 UP 无段(bo_only 语义)
        r = run([100, 100, 100, 100, 101, 102, 103])
        assert r.segments == ()
        assert r.machine_outcome == 'budget'


class TestDown:
    def test_rise_arm_priority_v_bounce_no_segment(self):
        # i=5 大反弹 101 > trough99+1.5 → 直接 UP 不 STABLE(V 反转不产段);
        # i=6 收跌 → DOWN;i=7 不刷新 → STABLE enter=7;i=8 rise 出段
        r = run([100, 100, 100, 100, 99, 101, 100.9, 101.0, 102.5])
        assert [s.outcome for s in r.segments] == ['rise']
        assert r.segments[0].enter == 7 and r.segments[0].exit == 7

    def test_equal_close_is_no_refresh(self):
        # i=5 close == trough(等值)→ 不刷新,计 1 → STABLE(严格小于才叫刷新)
        r = run([100, 100, 100, 100, 98, 98, 98.5])
        assert r.segments[0].enter == 5   # i=4 DOWN(trough=98);i=5 等值 count=1 → STABLE

    def test_new_low_resets_count(self):
        # i=5 刷新 97(count 清零)→ i=6 不刷新 count=1 → STABLE enter=6
        r = run([100, 100, 100, 100, 98, 97, 97.2])
        assert r.segments[0].enter == 6


class TestStable:
    def test_rise_exit_ratchets(self):
        # trough=98.8(i=5);enter=6;i=7 close=100.5 > 98.8+1.5=100.3 → rise 段 (6,6)
        r = run([100, 100, 100, 100, 99, 98.8, 99.0, 100.5, 98.0])
        # i=8 close=98.0 < gbot(=ratcheted 98.8)→ 段外全局退出,machine='break'(事件保留)
        assert r.segments == [(6, 6, 'rise')]
        assert r.machine_outcome == 'break'

    def test_new_high_arm_exit(self):
        # k=100 → rise 臂不可达,仅 close>peak 臂:peak=close[bo]=100;i=9 close=101>100 → rise
        r = run([100, 100, 100, 100, 95, 90, 85, 86, 87, 101], k=100.0)
        assert r.segments == [(7, 8, 'rise')]   # enter=7(i=7 count=1);exit=i-1=8
        assert r.machine_outcome == 'break'      # 后续无数据 → budget!
        # ↑ 注意:序列结束即预算尽,machine_outcome='budget'(下一用例专门测 break)

    def test_weak_exit_reentry(self):
        # enter=5;i=6 close=97.9 < trough=98 → weak (5,5);→ DOWN trough=97.9;
        # i=7 不刷新 → STABLE enter=7;i=8 rise(97.9+1.5=99.4,close=99.5)
        r = run([100, 100, 100, 100, 99, 99.2, 97.9, 98.0, 99.5])
        assert r.segments == [(5, 5, 'weak'), (7, 7, 'rise')]

    def test_stable_trough_frozen(self):
        # STABLE 内 close 高于 trough 但不达 rise → 不刷新 trough 不出段(静止)
        r = run([100, 100, 100, 100, 98, 98.5, 98.9, 99.0])
        assert r.segments == ()    # 全程无 rise/weak/break → 0 段? enter=5 后一直 STABLE 到预算尽
        assert r.machine_outcome == 'budget'   # 预算尽段内 → 应有 timeout 段!
        # ↑ 修正预期:段内预算尽 → 末段 timeout。见下:

    def test_budget_timeout_closes_segment(self):
        # enter=5 后横住到序列尾(ms=7 只扫到 i=7)→ timeout 段 (5, 7, 'timeout')
        r = run([100, 100, 100, 100, 98, 98.5, 98.9, 99.0], ms=4)
        # bo=3, ms=4 → 扫 i∈[4,7];i=7 处仍 STABLE → (5, 7, 'timeout')
        assert r.segments == [(5, 7, 'timeout')]
        assert r.machine_outcome == 'budget'


class TestGlobalBreak:
    def test_break_truncates_last_segment(self):
        # gbot=90;enter=5;i=7 close=89<90 段内破线 → 末段 (5,6,'break')
        r = run([100, 100, 100, 100, 99, 99.5, 99.6, 89], gbot=90.0)
        assert r.segments == [(5, 6, 'break')]
        assert r.machine_outcome == 'break'

    def test_break_zero_segments(self):
        # 全程 UP 后 i=4 收跌 DOWN;i=5 直接破线 → 0 段 machine='break'
        r = run([100, 100, 100, 100, 99, 49], gbot=90.0)
        assert r.segments == ()
        assert r.machine_outcome == 'break'

    def test_ratchet_chain_then_break(self):
        # 两轮成功后第三轮破抬升线才死:ratchet 生效则机器死于 i=10;
        # 若 gbot 未抬升(恒 50)则不会在 i=10 死(budget)
        r = run([100, 100, 100, 100, 95, 95.5, 97.5,   # 段1: trough=95, enter=5, rise@6
                 97.0, 96.5, 98.2,                     # 段2: trough=96.5, enter=8, rise@9? 验算见 assert
                 96.0], gbot=50.0)
        # gbot 第一次 ratchet → 95;第二次段底须 >95:96.5 ✓;i=10 close=96 < gbot=96.5 → break
        assert r.machine_outcome == 'break'
        assert len(r.segments) == 2


class TestVolWarmup:
    def test_nan_vol_degrades_rise_arm(self):
        # vol[5]=NaN:反弹根 rise 臂跳过 → 落到计数臂入段(V 反弹根成入段根)
        c, o, v = mk([100, 100, 100, 100, 99, 101, 101.5])
        v[5] = np.nan
        r = enumerate_segments_v4(c, o, 3, 50.0, v)
        assert r.segments[0].enter == 5


class TestInvariant:
    def test_peak_monotone_multi_cycle(self):
        # 多轮后 peak 仍 ≥ 初始 100:第二轮 rise 触发后 close>peak 臂仍可用
        r = run([100, 100, 100, 100, 95, 95.5, 97.5, 97.0, 96.5, 98.2, 96.0, 200.0])
        # i=11 close=200 > peak → 无论 trough 深浅 rise 必触发;若 peak 被重置会提前触发
        assert any(s.outcome == 'rise' for s in r.segments)
```

**测试数值自洽性说明(实现者必读):** 上面每个序列在写实现前先手工按 spec §2 伪代码走一遍;`test_new_high_arm_exit` 与 `test_stable_trough_frozen` 中标 `↑ 修正预期` 的两处,以实际伪代码推演为准修正断言(前者:序列耗尽 = 预算尽 → `machine_outcome == 'budget'`;后者:0 段 + budget 意味着从未入段,而该序列 enter=5 已入段,正确预期是 timeout 段——两个用例合并为 `test_budget_timeout_closes_segment` 的形态)。**修正后删除与推演矛盾的用例,保留推演正确的版本。**

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/path2/atoms/test_throwback_v4.py -x -q`
Expected: FAIL(`ModuleNotFoundError: path2.atoms.throwback_v4`)

- [ ] **Step 3: 实现状态机**(`path2/atoms/throwback_v4.py`)

```python
"""throwback v4:post-burst 三态价格行为状态机(UP/DOWN/STABLE)。

设计 spec:docs/superpowers/specs/2026-08-16-tb-v4-state-machine-design.md(定稿)。
核心判据/字段语义/一句话定位见模块内 detector 类与事件类 docstring(Task 3 补全)。
"""
from __future__ import annotations

from typing import Callable, NamedTuple, Optional

import numpy as np


class TbV4Seg(NamedTuple):
    """单个企稳段:enter=入段根(第 K 根不刷新),exit=收口根,outcome=关闭方式。"""
    enter: int
    exit: int
    outcome: str


class TbV4MachineResult(NamedTuple):
    """一台状态机(一个 burst)的完整产出。machine_outcome ∈ ('break','budget')。"""
    segments: tuple[TbV4Seg, ...]
    machine_outcome: str


def enumerate_segments_v4(
    closes: np.ndarray, opens: np.ndarray, bo_idx: int, global_bottom: float,
    vol: np.ndarray, *,
    max_rise_k: float = 1.5, stop_confirm_bars: int = 1, max_span: int = 60,
    on_gate: Optional[Callable] = None, vol_window: int = 14,
) -> TbV4MachineResult:
    """三态状态机(spec §2,检查顺序固定)。

    UP:peak 更新(含触发根)→ 首根阴线或收跌转 DOWN;DOWN:严格新低刷新 trough
    (计数清零)、rise 臂优先(close > trough + max_rise_k·vol(i),vol NaN 降级不
    触发)、count≥K 入 STABLE;STABLE:rise 或 close>peak 收段并 ratchet
    global_bottom=trough,破段底收 weak 转 DOWN 重滚(re-entry 原生)。任何状态
    close < global_bottom 机器终止(段内则末段 'break' 截断)。预算 max_span 扫满
    段内 → 'timeout' 收口。全判据无前瞻;on_gate 由 Task 4 接线(本版本不消费)。
    """
    n = len(closes)
    end = min(bo_idx + max_span, n - 1)
    state = 'UP'
    peak = float(closes[bo_idx])
    trough = float('inf')
    cnt = 0
    gbot = float(global_bottom)
    enter = -1
    segs: list[TbV4Seg] = []

    def vol_at(i: int) -> Optional[float]:
        v = float(vol[i])
        return v if v == v else None          # NaN → None(rise 臂降级)

    for i in range(bo_idx + 1, end + 1):
        c = float(closes[i])
        # ══ 0 全局退出(最高优先)══
        if c < gbot:
            if state == 'STABLE':
                segs.append(TbV4Seg(enter, i - 1, 'break'))
            return TbV4MachineResult(tuple(segs), 'break')
        # ══ 1 UP ══
        if state == 'UP':
            if c > peak:
                peak = c                       # 更新先于转换判定(peak 含触发根)
            if c < float(opens[i]) or c < float(closes[i - 1]):
                state, trough, cnt = 'DOWN', c, 0
        # ══ 2 DOWN ══
        elif state == 'DOWN':
            v = vol_at(i)
            if c < trough:                     # 严格小于才叫刷新(等值=不刷新)
                trough, cnt = c, 0
            elif v is not None and c > trough + max_rise_k * v:
                state = 'UP'                   # rise 臂优先于 stable(V 反转不产段)
            elif cnt >= stop_confirm_bars:
                state, enter = 'STABLE', i     # trough 即段底,无需冻结变量
            else:
                cnt += 1
        # ══ 3 STABLE ══
        else:
            v = vol_at(i)
            if (v is not None and c > trough + max_rise_k * v) or (c > peak):
                gbot = trough                  # ratchet(INV-1:gbot ≤ trough 恒成立)
                segs.append(TbV4Seg(enter, i - 1, 'rise'))
                state = 'UP'
                if c > peak:
                    peak = c
            elif c < trough:
                segs.append(TbV4Seg(enter, i - 1, 'weak'))
                state, trough, cnt = 'DOWN', c, 0
    if state == 'STABLE':
        segs.append(TbV4Seg(enter, end, 'timeout'))   # 预算类含末根
    return TbV4MachineResult(tuple(segs), 'budget')
```

- [ ] **Step 4: 跑测试确认通过**(按 Step 1 说明修正过断言后)

Run: `uv run pytest tests/path2/atoms/test_throwback_v4.py -q`
Expected: 全 PASS。若某用例失败,先手工重推该序列(伪代码逐根走)再判断是测试错还是实现错——**判据语义以 spec §2 为准,不得为实现迁就测试**。

- [ ] **Step 5: Commit**

```bash
git add path2/atoms/throwback_v4.py tests/path2/atoms/test_throwback_v4.py
git commit -m "feat(atoms): tb v4 三态状态机纯函数 enumerate_segments_v4

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 3: 事件类 + ThrowbackDetectorV4

**Files:**
- Modify: `path2/atoms/throwback_v4.py`(追加)
- Modify: `tests/path2/atoms/test_throwback_v4.py`(追加)

**Interfaces:**
- Consumes: Task 1 `calculate_tr_median`;Task 2 `enumerate_segments_v4`/`TbV4Seg`/`TbV4MachineResult`;`path2/core.py::Event`;`path2/atoms/breakout.py::BurstEvent/BOEvent`(burst 流输入);`path2/calc/measure.py::VALID_MEASURES/measure_at`。
- Produces(Task 5 依赖,签名逐字):
  - `ThrowbackSegmentV4(Event)`:`anchor_bo_id: str = ""`、`outcome: str = "weak"`
  - `ThrowbackEventV4(Event)`:`segments: tuple = ()`、`anchor_bo_id: str = ""`、`outcome: str = "weak"`(末段)、`machine_outcome: str = "break"`;`child_slots()` 返回 `{"segments": self.segments}`
  - `ThrowbackDetectorV4(max_rise_k=1.5, stop_confirm_bars=1, vol_window=14, anchor_mode='span_min', max_span=60, measure='close')`;`detect(self, burst_stream, df)`;类属性 `has_debug_hooks=True`、`event_cls=ThrowbackEventV4`、`on_gate=None`

- [ ] **Step 1: 写失败测试**(追加;burst 构造参考 `tests/path2/atoms/test_throwback_v1_burst_anchor.py` 现有的合成 bo/burst helper——现场读该文件,复制其构造模式,勿自造)

```python
class TestDetector:
    """detect 装配:anchor 三模式 / 容器结构 / 排序 / 0 段不产。"""

    def _mk_burst(self, df, start, end, bo_idxs):
        """按 test_throwback_v1_burst_anchor.py 的模式构造 BurstEvent(现场读后对齐)。"""
        ...   # ← 用该文件现成 helper/构造方式,不在本 plan 重复定义

    def test_container_structure(self):
        # 一 burst 一容器:span=[首段 enter, 末段 exit],confirm=首段 enter,
        # child_slots={'segments': ...},machine_outcome 正确透传
        ...

    def test_anchor_three_modes(self):
        # span_min = burst span 全部 bar measure 最小;min_bo = 各 bo 当根取 min;
        # last_bo = last_bo.end_idx-1 处 measure。构造 df 使三者取值不同,断言段行为差异
        ...

    def test_zero_segments_no_event(self):
        # 全程 UP 的 burst → detect 不产(无容器)
        ...

    def test_sorted_by_end(self):
        # 多 burst 乱序输入 → 输出 (end_idx, start_idx) 升序(run() 不变式)
        ...

    def test_invalid_params_raise(self):
        # measure 不在 VALID_MEASURES / anchor_mode 不在三值 → ValueError
        ...
```

`...` 处按所引 helper 模式补全为可运行代码——**测试断言语义已给全**(容器字段、三种锚取值、0 段、排序、校验异常),构造方式复用既有测试文件的现成模式。

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/path2/atoms/test_throwback_v4.py::TestDetector -x -q`
Expected: FAIL(`ImportError: ThrowbackDetectorV4`)

- [ ] **Step 3: 实现**(追加到 `path2/atoms/throwback_v4.py`;结构模板 = `path2/atoms/throwback_v3.py` 的 detector 段,现场对照)

```python
# ── 追加 imports ──
# from dataclasses import dataclass
# from typing import ClassVar, Iterable, Iterator, List
# import pandas as pd
# from path2.atoms.breakout import BurstEvent
# from path2.calc.atr import calculate_tr_median
# from path2.calc.measure import VALID_MEASURES, measure_at
# from path2.core import Event
# from path2.debug_ctx import debug_break


@dataclass(frozen=True)
class ThrowbackSegmentV4(Event):
    """企稳段。span=[enter, exit];confirm=enter(确认型);段内每 bar 是 eval 买点样本。
    outcome ∈ ('rise','weak','break','timeout');break 仅末段。"""
    anchor_bo_id: str = ""
    outcome: str = "weak"


@dataclass(frozen=True)
class ThrowbackEventV4(Event):
    """一 burst 的企稳段容器(确认型:confirm=start=首段 enter)。outcome=末段关闭方式;
    machine_outcome ∈ ('break','budget') = 整机死法(与末段 outcome 独立,B1)。"""
    segments: tuple[ThrowbackSegmentV4, ...] = ()
    anchor_bo_id: str = ""
    outcome: str = "weak"
    machine_outcome: str = "break"

    def child_slots(self):
        return {"segments": self.segments}


class ThrowbackDetectorV4:
    """派生 detector:消费 burst 流,每 burst 一台三态状态机,产容器事件。

    核心判据见 enumerate_segments_v4 docstring(spec §2)。vol 全程一次预计算
    (calculate_tr_median,即时取 i-1);数值比较用 measure(默认 close),阴线臂
    恒用 close/open(K 线形态判据);anchor 三模式:span_min(burst span 全 bar
    measure 最小,默认)/ min_bo(各 bo 当根取 min)/ last_bo(末 bo 上一根)。
    多源 L2+(detect(burst_stream, df));输出按 (end_idx, start_idx) 升序;
    前缀族同 cluster 多 burst → 多容器各带单来源 anchor_bo_id,不去重。
    """
    has_debug_hooks: ClassVar[bool] = True
    event_cls = ThrowbackEventV4
    on_gate = None

    def __init__(self, *, max_rise_k: float = 1.5, stop_confirm_bars: int = 1,
                 vol_window: int = 14, anchor_mode: str = 'span_min',
                 max_span: int = 60, measure: str = 'close'):
        if measure not in VALID_MEASURES:
            raise ValueError(f"measure 必须在 {VALID_MEASURES},实际 {measure!r}")
        if anchor_mode not in ('last_bo', 'min_bo', 'span_min'):
            raise ValueError(f"anchor_mode 必须是 'last_bo'|'min_bo'|'span_min',实际 {anchor_mode!r}")
        self._kw = dict(max_rise_k=max_rise_k, stop_confirm_bars=stop_confirm_bars,
                        vol_window=vol_window, anchor_mode=anchor_mode,
                        max_span=max_span, measure=measure)

    def detect(self, burst_stream, df):
        events: List[ThrowbackEventV4] = []
        vol = calculate_tr_median(df['high'], df['low'], df['close'],
                                  self._kw['vol_window']).values
        measure = self._kw['measure']
        for burst in burst_stream:
            last_bo = burst.members[-1]
            bo = last_bo.end_idx
            if bo < 1 or bo >= len(df):
                continue
            mode = self._kw['anchor_mode']
            if mode == 'last_bo':
                gbot = measure_at(df, bo - 1, measure)
            elif mode == 'min_bo':
                gbot = min(measure_at(df, b.end_idx, measure) for b in burst.members)
            else:  # span_min
                gbot = min(measure_at(df, i, measure)
                           for i in range(burst.start_idx, burst.end_idx + 1))
            res = enumerate_segments_v4(
                measure_col.values, df['open'].values, bo, float(gbot), vol,
                max_rise_k=self._kw['max_rise_k'],
                stop_confirm_bars=self._kw['stop_confirm_bars'],
                max_span=self._kw['max_span'],
                on_gate=self.on_gate, vol_window=self._kw['vol_window'])
            if not res.segments:
                continue
            src_id = last_bo.instance_id
            segs = tuple(
                ThrowbackSegmentV4(start_idx=s.enter, end_idx=s.exit,
                                   confirm_idx=s.enter, anchor_bo_id=src_id,
                                   outcome=s.outcome)
                for s in res.segments)
            events.append(ThrowbackEventV4(
                start_idx=segs[0].start_idx, end_idx=segs[-1].end_idx,
                confirm_idx=segs[0].start_idx, segments=segs,
                anchor_bo_id=src_id, outcome=segs[-1].outcome,
                machine_outcome=res.machine_outcome))
        events.sort(key=lambda e: (e.end_idx, e.start_idx))   # run() 要 end 升序
        yield from events
```

注意:`measure_col` 未在上文定义——**measure 列的取法现场读 `path2/calc/measure.py::measure_at`**:若其内部按 measure 名取列,则 detect 里先用同样方式物化数值列(如 `measure_col = df['close'] if measure=='close' else df[...]`,以 measure_at 的实现为准对齐;**阴线臂恒用 close/open**,不随 measure 变)。把 `enumerate_segments_v4` 的第一个参数喂该列的 `.values`,保证状态机数值比较与 anchor 定价同口径。

- [ ] **Step 4: 跑测试确认通过 + 全目录回归**

Run: `uv run pytest tests/path2/atoms/test_throwback_v4.py tests/path2/atoms/test_throwback_v3.py -q`
Expected: 全 PASS(v3 既有测试零回归)

- [ ] **Step 5: Commit**

```bash
git add path2/atoms/throwback_v4.py tests/path2/atoms/test_throwback_v4.py
git commit -m "feat(atoms): ThrowbackDetectorV4 容器装配(anchor 三模式/排序/机器结局)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 4: gate 接线(三 gate)+ debug_break 埋点

**Files:**
- Modify: `path2/atoms/throwback_v4.py`(`enumerate_segments_v4` 消费 on_gate;加 `_emit_tb_gate_v4` helper;detect 加 debug_break)
- Modify: `tests/path2/atoms/test_throwback_v4.py`(追加)

**Interfaces:**
- Consumes: `path2/dag/gate_failure.py::GateFailure/MeasuredKindAware`(签名现场读 `path2/atoms/throwback_v1.py::_emit_tb_gate`——helper 模板);`path2/debug_ctx.py::debug_break`;`path2/debug.py::current_symbol`。
- Produces: gate 名表(逐字):`break_no_stable`(全局退出时 0 段)/ `break_truncate`(全局退出截断末段,事件仍产)/ `budget_no_stable`(预算尽 0 段);**段级收口(rise/weak/timeout)不 emit;段外破线且 ≥1 段也不 emit**(机器已完成产出,非截断)。`failure_event_window=(bo_idx+1, gate_idx)`;`evaluation_lookback=(gate_idx-vol_window, gate_idx-1)`;`anchor_bar=bo_idx`;`measured.kind`:'anchor_delta'(破位类)/'count'(预算类)。

- [ ] **Step 1: 写失败测试**

```python
class TestGates:
    """gate 只收整机短路点(spec §7)。collector = 简单 list append。"""

    def _run_collect(self, **kw):
        collected = []
        r = run(**kw)   # 需给 run() 加 on_gate 透传(见 Step 3 测试 helper 修改)
        return r, collected

    def test_break_no_stable(self):
        # 0 段 + 破线 → 1 条 gate 'break_no_stable',measured.kind='anchor_delta'
        ...

    def test_break_truncate(self):
        # 段内破线截断 → 'break_truncate' emit 且事件(段)仍产
        ...

    def test_budget_no_stable(self):
        # 预算尽 0 段(全程 UP)→ 'budget_no_stable',kind='count'
        ...

    def test_no_gate_on_normal_exits(self):
        # rise/weak/timeout 段收口、段外破线且已有段 → collector 空
        ...


class TestDebugHooks:
    """debug_break 埋点:entry(bo 根)/ confirm(段 enter 根)/ end(收口根)。
    测法照 tests/path2/atoms/test_throwback_debug_hook.py 现有模式(现场读)。"""
    ...
```

(`...` 处按 Task 2 的 `run()` helper 加 `on_gate` 形参后补全;断言语义已给全。)

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/path2/atoms/test_throwback_v4.py::TestGates -x -q`
Expected: FAIL(on_gate 未被消费,collector 空)

- [ ] **Step 3: 实现**

`_emit_tb_gate_v4` 从 `throwback_v1._emit_tb_gate` 逐字复制改名,两处差异:`evaluation_lookback=(gate_idx - vol_window, gate_idx - 1)`;docstring 注明 t4 gate 名表。`enumerate_segments_v4` 在三个短路点插入 emit(全局退出 0 段 / 全局退出段内 / 预算尽 0 段),`on_gate is None` 时零开销直接 return。detect 内 debug_break:`entry` 于 `bo` 根、`confirm` 于每段 `enter` 根、`end` 于每段收口根(口径对照 `throwback_v3.py` 现有埋点:rise/weak/break 用 `i-1`、timeout 用 `end`)。

- [ ] **Step 4: 跑测试确认通过 + 契约回归**

Run: `uv run pytest tests/path2/atoms/test_throwback_v4.py tests/path2/atoms/test_gate_failure_contract.py tests/path2/atoms/test_debug_break_class_contract.py -q`
Expected: 全 PASS

- [ ] **Step 5: Commit**

```bash
git add path2/atoms/throwback_v4.py tests/path2/atoms/test_throwback_v4.py
git commit -m "feat(atoms): tb v4 gate 三件套(整机短路点)+ debug 埋点

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 5: bb 接线(换 tb node 到 V4)

**Files:**
- Modify: `path2_apps/bottom_burst/dag_spec.py`
- Modify: `path2_apps/bottom_burst/params.py`(ThrowbackParams 重写)
- Modify: `path2_apps/bottom_burst/params.yaml`(tb 段重写)
- Test: `tests/path2/apps/bottom_breakout_burst/`(追加;该目录为 bb app 既有测试位置)

**Interfaces:**
- Consumes: Task 3 `ThrowbackDetectorV4`/`ThrowbackSegmentV4`。
- Produces: bb_v1 pattern 的 tb node 产出 V4 容器;`eval_meta` 的 `end_node` 保持 `'tb.segments'`(node id `tb` 与槽名 `segments` 均不变,前端/eval 消费方零改名);边 `max_gap = params.tb.max_span`(与 detector 同 SSoT,语义 = 首段 enter 与 bo 的 gap 上限)。

- [ ] **Step 1: 写失败测试**

```python
class TestTbV4Wiring:
    def test_build_pattern_uses_v4(self):
        spec = build_pattern(load_params())
        tb = [n for n in spec.nodes if n.node_id == 'tb'][0]
        assert type(tb.produced_by).__name__ == 'ThrowbackDetectorV4'
        assert tb.consumes_stream == 'burst'
        # 子结构 node event_cls = ThrowbackSegmentV4
        seg = [n for n in spec.nodes if n.node_id == 'tb_seg'][0]
        assert seg.event_cls.__name__ == 'ThrowbackSegmentV4'

    def test_eval_meta_end_node_unchanged(self):
        m = eval_meta(load_params())
        assert m['end_node'] == 'tb.segments'
        assert isinstance(m['head_buffer_trading_days'], int)

    def test_analyze_smoke(self):
        # 合成 df(含一次 bo→burst→回踩企稳结构)跑 analyze,断言 tb 容器出现且
        # segments 槽非空。合成 df 构造参考本目录既有测试的 fixture(现场读)。
        ...
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/path2/apps/bottom_breakout_burst/ -k v4 -x -q`
Expected: FAIL(现 wired 的是旧 ThrowbackDetector、consumes_stream='bo')

- [ ] **Step 3: 实现改动**

1. `params.py`:`ThrowbackParams` 字段替换为新参数集(与 `ThrowbackDetectorV4.__init__` 一一对应):`max_rise_k: float = 1.5`、`stop_confirm_bars: int = 1`、`vol_window: int = 14`、`anchor_mode: str = 'span_min'`、`max_span: int = 60`、`measure: str = 'close'`(删除旧字段 `max_start_gap/max_window/atr_window/anchor_measure/trend_lookback/k_exit/k1/k2/M/stop_confirm_bars 旧语义`)。
2. `params.yaml` tb 段重写为同名六参数 + 中文注释(参数定值与定值依据从 spec §8 抄:`max_span=60` 拐点依据、`stop_confirm_bars=1` 依据各一行)。
3. `dag_spec.py`:import 换 `from path2.atoms.throwback_v4 import ThrowbackDetectorV4, ThrowbackSegmentV4`;tb NodeSpec 改 `consumes_stream="burst"`;`NodeSpec("tb_seg", event_cls=ThrowbackSegmentV4)`;边 `max_gap=params.tb.max_start_gap` → `max_gap=params.tb.max_span`(注释同步:与 ThrowbackDetectorV4(max_span) 共用同一 SSoT)。
4. `dag_spec.py::eval_meta`:`p.tb.atr_window` → `p.tb.vol_window`。
5. 全库残留清查:`grep -rn "max_start_gap\|tb\.atr_window\|k_exit\|trend_lookback" --include="*.py" --include="*.yaml" path2_apps/bottom_burst path2_web path2_web_ui/src configs` 逐条处理(测试 fixture 的旧字段同步替换;`path2/atoms/` 旧三代文件内的引用**不动**)。

- [ ] **Step 4: 跑测试确认通过 + bb 全量回归 + 冒烟**

Run: `uv run pytest tests/path2/apps/bottom_breakout_burst/ -q && uv run python -c "
import pandas as pd
from path2_apps.bottom_burst import load_params, analyze
df = pd.read_pickle('datasets/pkls/ADAG.pkl')
res = analyze(df, load_params())
tbs = [e for e in res.events if getattr(e, 'node_id', '') == 'tb']
print('tb events:', len(tbs), '| matches:', len(res.matches))
"
Expected: 测试全 PASS;冒烟输出 tb events > 0(若 ADAG 在当前 yaml 参数下无命中,换 `/tmp` 下任一 66 命中股重试;数量级合理即可——**语义换代,无 golden 对拍**,spec §12 已声明 t1 交集仅 11%)

- [ ] **Step 5: Commit**

```bash
git add path2_apps/bottom_burst/ tests/path2/apps/bottom_breakout_burst/
git commit -m "feat(bb): tb node 换线 ThrowbackDetectorV4(语义换代,边 max_gap=max_span)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 6: `path2/eval.py` 样本消费窗截取

**Files:**
- Modify: `path2/eval.py`(`match_forward_returns` / `match_first_passage`)
- Test: `tests/path2/test_eval.py`(追加)

**Interfaces:**
- Consumes: 无(独立于 Task 1-5,**可与 detector 线并行**)。
- Produces: 两函数各加可选参 `sample_window: Optional[tuple[int, int]] = None`(win 行号含端,`(lo, hi)`);`None` = 现行为(全量,向后兼容)。逐买点日 `t` 仅当 `lo <= t <= hi` 参与。Task 7 用它传 `[start_ts 行号, end_ts 行号]`。

- [ ] **Step 1: 写失败测试**(追加;`PatternMatch`/容器构造沿用 `tests/path2/test_eval.py` 既有 fixture 模式,现场读)

```python
class TestSampleWindow:
    def test_forward_returns_clipped(self):
        # 容器两段 span [10,12] 与 [20,22];sample_window=(0, 15) → 只有第一段 3 天参与
        # 断言:与手工构造的仅 [10,12] 段结果逐值相等
        ...

    def test_first_passage_clipped(self):
        # 同上容器;fp 四态计数只数窗内日
        ...

    def test_none_keeps_behavior(self):
        # sample_window=None 结果与不加参数完全一致(回归护栏)
        ...
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/path2/test_eval.py::TestSampleWindow -x -q`
Expected: FAIL(Unexpected keyword argument 'sample_window')

- [ ] **Step 3: 实现**

两函数的逐日循环处(`for t in ev.sample_bar_indices()`)统一加过滤:`if sample_window is not None and not (sample_window[0] <= t <= sample_window[1]): continue`。docstring 各补一句:t4 配套的样本消费窗(spec §10 样本消费窗截取)——跨界 tb_seg 只取窗内部分计样本;label 前瞻窗不受截取影响(仍看未来 N 根)。

- [ ] **Step 4: 跑测试确认通过 + eval 全量回归**

Run: `uv run pytest tests/path2/test_eval.py tests/path2/test_first_passage.py -q`
Expected: 全 PASS(既有测试零回归——默认 None 路径逐字不变)

- [ ] **Step 5: Commit**

```bash
git add path2/eval.py tests/path2/test_eval.py
git commit -m "feat(eval): label 消费函数加 sample_window 双边截取(t4 样本消费窗)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 7: path2_web 接样本截取 + eval 去重

**Files:**
- Modify: `path2_web/serialize.py`(`serialize_per_pattern_result`)
- Modify: `path2_web/eval_runner.py`(`_eval_ticker` / `_leaf_stats` / summary 聚合)
- Test: `tests/path2_web/`(追加;web 既有测试位置现场 ls 定位)

**Interfaces:**
- Consumes: Task 6 `sample_window`。
- Produces:
  - 截取:scan/eval 两条 worker 路径的一切逐日消费(`match_forward_returns` / `match_first_passage` / `n_buy_days`)统一传 `sample_window=(lo, hi)`,`lo/hi` = win 内 `start_ts`/`end_ts` 的行号(`win['date'].searchsorted`,含端);matches 过滤口径**不变**(任一起点 ∈ [start,end])。
  - 去重:eval 报表新增**日级去重视图**——worker 内对每 match 的截窗样本日输出 `sample_dates: list[str]`;聚合层新增 `dedup_daily` 统计(按 (symbol, date) 去重逐日收益分布 + `consensus_days` 字段 = 被多 match 覆盖的日数);旧 match 级统计**保留**为诊断口径。

- [ ] **Step 1: 写失败测试**

```python
class TestSampleClipping:
    def test_serialize_clips_crossing_segment(self):
        # 构造 res:一 match 的 tb 段 span 跨 end_ts;win/日期已知。
        # 断言注入的 forward_return 只用窗内日(与手工截窗期望值相等)
        ...

    def test_n_buy_days_clipped(self):
        # rows['n_buy_days'] 只数窗内日
        ...

class TestDedupDaily:
    def test_duplicate_day_counted_once(self):
        # 两 match(前缀族重叠机)段交叠,同 (symbol, date) → dedup 日级收益只计一票,
        # consensus_days 标记该日
        ...
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/path2_web/ -k "clip or dedup" -x -q`
Expected: FAIL(无此行为)

- [ ] **Step 3: 实现**

1. 两 worker(`scan.py::_scan_ticker_multi` 调 serialize 处、`eval_runner.py::_eval_ticker`)计算 `lo = int(win['date'].searchsorted(start_ts, 'left'))`、`hi = int(win['date'].searchsorted(end_ts, 'right')) - 1`,传 `sample_window=(lo, hi)` 给 `match_forward_returns` / `match_first_passage`;`n_buy_days` 的集合推导同步过滤。
2. `eval_runner._eval_ticker`:rows 加 `"sample_dates": [str(win['date'].iat[t])[:10] for t in 截窗后的并集日]`;新增 worker 内日级收益计算(逐 (symbol,t) 一次,同日跨 match 同值天然去重):`"day_returns": {date: {horizon: ret}}`。
3. 聚合层(读 `_summarize_flat` / `_leaf_stats` 现场):新增 `dedup_daily` 汇总——展开全部 rows 的 day_returns 按 (symbol, date) 去重后过 `_summarize_flat`,输出 `{dedup_count, dedup_mean, ..., consensus_days}`(consensus_days = 被多 match sample_dates 覆盖的日数);挂进 eval 输出的 summary(新键,不改旧键)。
4. 前端 tooltip 若有逐字段绑定 eval summary,`consensus_days` 暂不展示(Task 8 只做分色;展示留后续)。

- [ ] **Step 4: 跑测试确认通过 + web 回归**

Run: `uv run pytest tests/path2_web/ -q`
Expected: 全 PASS(既有 serialize/scan 测试零回归——不加 sample_window 的旧断言路径行为不变)

- [ ] **Step 5: Commit**

```bash
git add path2_web/ tests/path2_web/
git commit -m "feat(web): 样本消费窗双边截取 + eval 日级去重视图(伪复制修复)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 8: 前端副图 band 按 end_date 分色

**Files:**
- Modify: `path2_web_ui/src/render/chart.ts`(或副图 band interval 绘制的实际所在——`render/subGeometry.ts` 是几何,绘制调用现场 grep `BAND_MARKER_H` 定位)
- Modify: `path2_web_ui/src/stores/view.ts`(仅当 `anchorsOf['tb']` 的锚点细分对 V4 事件不兼容时;V4 与 V2 同为容器+segments,node_id `tb` 不变,预期零改或小改)
- Test: `path2_web_ui/src/render/__tests__/`(现场定位;vitest)

**Interfaces:**
- Consumes: 前端已有 `scanEnd` 概念(`chart.ts::buildShadingMarkArea` —— 主图 K 线窗边界灰色阴影的现成先例,`visible.ts::windowOf` 提供 start_date/end_date)。
- Produces: 副图 band interval 与 scanEnd 相交时拆两段绘制——窗内段维持三档 level 色(matched 彩色),窗后段用灰色(与 detected/traced 灰色系一致,色值取 `render/colors.ts` 现有灰);主图已有 shading 不动。

- [ ] **Step 1: 写失败测试**(把拆分逻辑抽成纯函数测)

```typescript
// 纯函数 splitIntervalAtScanEnd(interval, scanEndIdx):
//   interval 完全在窗内 → [interval]
//   interval 完全在窗外 → [interval(灰)]
//   跨界 → [窗内段, 窗后段(灰)]
describe('splitIntervalAtScanEnd', () => { /* 三个 case + 边界=endIdx 本身归窗内 */ })
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd path2_web_ui && npx vitest run src/render`(具体测试文件现场定位)
Expected: FAIL(函数不存在)

- [ ] **Step 3: 实现**——抽出 `splitIntervalAtScanEnd` 纯函数 + 在副图 band interval 绘制处消费;`anchorsOf['tb']`:构造一个 V4 容器样例(node_id 'tb'、child_refs segments、锚 entry/confirm/end)在浏览器 dev 环境(或 vitest 快照)验证现有 profile 命中,不兼容才改。

- [ ] **Step 4: 三绿验证**

Run: `cd path2_web_ui && npx vue-tsc --noEmit && npm run build && npx vitest run`
Expected: 全绿

- [ ] **Step 5: Commit**

```bash
git add path2_web_ui/
git commit -m "feat(ui): 副图 band 按 end_date 分色(窗内彩色/窗后灰色,机器轨迹可见)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 9: 文档收尾(主会话执行,不派 subagent)

**Files:**
- Create: `.claude/skills/diagnose-event/detectors/throwback_v4.md`(模板 = `diagnose-event/detectors/throwback_v3.md`,七要素:事件结构 / API 签名 / 参数语义 / 状态机判据顺序 / gate 名表(含「段级收口不 emit」的退段标注)/ 典型失效模式 / 骨架 B 变体)
- Modify: `.claude/skills/authoring-path2-detector/reference.md`(§1 速查加 ThrowbackDetectorV4 条目:一句话定位 + 失效边界六条 + 常见误配)
- Modify: `.claude/docs/modules/path2.md`(经 `update-ai-context` skill,主会话 invoke)

- [ ] 核对实现与 spec §11 docstring 合同逐字落地(三要素齐全);核对 §6 失效边界六条在测试中各有至少一个用例;核对 anchorsOf 契约(项数守恒 + bar 严格相等)。
- [ ] 运行 `update-ai-context` 刷新 `.claude/docs/modules/path2.md`(tb v4 入库)与 `path2_apps.md`(bb 接线变化)。
- [ ] Commit:`docs: tb v4 诊断契约 + reference 速查 + AI 上下文同步`。

---

## Self-Review 结论

- **Spec 覆盖**:spec §1(初始化/vol/anchor 三模式)→ Task 1/3;§2(状态机+顺序+不变式)→ Task 2;§3/§4(事件结构/字段表,含 machine_outcome)→ Task 3;§5(标准化)→ Global Constraints + Task 1/2;§6(失效边界)→ Task 2/3 测试;§7(gate/埋点)→ Task 4;§8(参数定值)→ Task 3 构造器默认 + Task 5 yaml;§9 裁决 → 已内化到各 task;§10(样本截取/去重/前端分色/bb 接线)→ Task 5/6/7/8;§11 docstring → Task 3 + Task 9 核对;§12 验证结论 → Task 5 冒烟说明。无遗漏。
- **占位符扫描**:Task 3/4/5/6/7 的 `...` 处均已注明「断言语义给全 + 构造方式指向具体既有文件模式(现场读)」——这是本仓库 plan 惯例(语义锚点代替死代码),非 TBD;所有签名/参数名/gate 名/词表逐字给出。
- **类型一致性**:`enumerate_segments_v4`/`TbV4Seg`/`TbV4MachineResult`/`ThrowbackDetectorV4`/`sample_window` 在 Task 2/3/4/6/7 间签名一致;`machine_outcome` 值域 ('break','budget') 全文一致。
