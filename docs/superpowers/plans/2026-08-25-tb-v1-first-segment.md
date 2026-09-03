# tb_v1 首段即停状态机 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `path2/atoms/throwback_v1.py` 从「两阶段流程 + 4 类死开关 + 10 构造参数」重写为「UP/DOWN/STABLE 价格行为状态机、首段收口即停、5 构造参数、毒药闸降为字段 + where」,并把 bb_v1 接线、测试、诊断契约、验证闸全部落地。

**Architecture:** 纯函数 `run_first_segment`(状态机核,与 v4 `enumerate_segments_v4` 同形签名但只产首段)+ 扁平事件 `ThrowbackEventV1`(新增 `max_day_drop` 字段)+ `ThrowbackDetectorV1`(每 burst 一机,vol / measure 列全程一次预计算)。v4(`throwback_v4.py`)冻结不碰;v3 只把从 v1 借的两个 helper 本地化。bb_v1 的 `TbParams` 换成 5+1 字段,毒药闸阈值走 tb node where。

**Tech Stack:** Python 3.12 / pandas / numpy / pytest(`uv run pytest`)· Vue3+TS 前端仅改 hint 文案(`vue-tsc` + `vitest`)· 评估工具 `path2_web.eval_runner`(run_healthcheck / run_regress)与本任务专用 `docs/research/2026-08-25_tb-v1-first-segment/repro/{scan_cmp.py,summarize.py}`。

**Spec:** `docs/superpowers/specs/2026-08-25-tb-v1-first-segment-design.md`(执行者先通读 §2–§5、§7、§10)

## Global Constraints

- 本 plan 中所有项目内路径均相对 repo root;执行 worktree = `/home/yu/PycharmProjects/Trade_Strategy/.claude/worktrees/tb-simplify`(分支 `worktree-tb-simplify`)。数据在 `/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls`(只读,绝不写主目录);worktree 内无 `datasets/`,凡 `data_dir` 一律写上面这个绝对路径。
- 无 worktree 私有 venv:python 命令统一用 `PYTHONPATH=$(git rev-parse --show-toplevel) /home/yu/PycharmProjects/Trade_Strategy-tune_v1/.venv/bin/python`;pytest 用 `/home/yu/PycharmProjects/Trade_Strategy-tune_v1/.venv/bin/python -m pytest`(从 worktree 根运行,`tests/` 已含 conftest)。下文简写 `$PY`。
- **v4 冻结**:`path2/atoms/throwback_v4.py`、`path2_apps/bottom_burst/` 一行不改。
- 状态机判据、检查顺序、严格不等式、收口 end 口径(价格行为类 i-1 / 预算类含末根)以 spec §3 伪代码为准,不得改动;`STABLE` rise 臂是**「或」**(`k·vol` 臂 **or** `close > peak`)。
- debug_break anchor_kind 只用 `entry` / `confirm` / `end` / `gate`(前端 `tbV1Anchors` 契约不变);`confirm`/`end` 必须埋在纯函数状态机分支内,禁止埋在 detect 的结果遍历处。
- gate 名固定三个:`break_no_stable` / `budget_no_stable` / `break_truncate`;rise / weak / timeout 收口不 emit gate。
- 构造参数固定 5 个:`max_rise_k=1.5, stop_confirm_bars=1, vol_window=14, max_span=20, measure='close'`;`max_day_drop_pct` 只在 app params 与 where,**不进 detector**。
- 每个 Task 结束时 `pytest tests/` 必须全绿再 commit;commit message 结尾加 `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`。不 push、不开 PR。
- 扫描/评估落盘到 worktree 的 `outputs/`(gitignored);改前基线已存在,**不要重跑基线**:`outputs/path2_eval/bb_v1_baseline_pre_simplify.json`(250 股/344 窗)、`outputs/path2_eval/bb_v3_baseline_pre_simplify.json`(317/426)、`outputs/path2_web/scans/cmp-old-v1-{train,oos}.json`、`cmp-bo_only-{train,oos}.json`。
- 调工具纪律:中途消息正文至多一句状态行(无代码 token、不预告"我去调用 X"),随后直接发调用;长篇解释只放不再调工具的收尾消息。若发现自己把调用写成了正文文字,不要停笔,在同一条消息里立即发出真正的调用。

---

## 文件结构(改动全景)

| 文件 | 责任 | Task |
|---|---|---|
| `path2/atoms/throwback_v1.py` | 状态机纯函数 + 事件 + detector(重写) | 1, 3 |
| `path2/atoms/throwback_v3.py` | 本地化 `_atr_at` / `_has_stop_signal`(去 v1 依赖) | 2 |
| `path2_apps/bb_v1/{params.py,params.yaml,dag_spec.py}` | 5+1 参数、day_drop where、edge SSoT | 3 |
| `path2_apps/try_conplex_where/{params.py,params.yaml,dag_spec.py}` | 同步签名 | 3 |
| `tests/path2/atoms/test_throwback_v1_machine.py`(新) | 纯函数判据逐条 | 1 |
| `tests/path2/atoms/test_throwback_v1_detector.py`(新) | 事件字段 / e2e outcome / gate / debug 锚 | 3 |
| 删除:`test_throwback.py`、`test_throwback_unified.py`、`test_throwback_v1_scb_mode.py`、`test_throwback_v1_burst_anchor.py`、`test_throwback_v1_toxic_gate.py`、`test_tb_on_gate.py`、`test_tb_e2e_outcomes.py`、`test_throwback_event.py`、`test_throwback_success_debug.py`、`test_throwback_debug_hook.py` | 覆盖并入两个新文件 | 3 |
| `tests/path2/atoms/test_gate_failure_contract.py`、`tests/path2/dag/test_gate_failure_code_location.py`、`tests/path2_apps/bb_v1/test_bb_v1.py` | 改为新 API | 3 |
| `path2_web_ui/src/stores/view.ts` | `tbV1Anchors` hint 文案 | 4 |
| `.claude/skills/feature-study/extract_skeleton.py` | `ATR_WINDOW` 常量注释/来源 | 4 |
| `.claude/skills/diagnose-event/detectors/throwback_v1.md`(新)、`.claude/skills/diagnose-event/reference.md`、`.claude/skills/authoring-path2-detector/reference.md` | 诊断契约 + 索引 + 速查条目 | 5 |
| `docs/research/2026-08-25_tb-v1-first-segment/{verification.md,cmp_table.md}`、`repro/attribute_diff.py` | 验证闸报告 | 6 |

---

### Task 1: 状态机纯函数 `run_first_segment`(与旧代码并存)

**Files:**
- Modify: `path2/atoms/throwback_v1.py`(在 `_emit_tb_gate` 之后、`_find_confirm_idx` 之前插入;旧函数暂留)
- Test: `tests/path2/atoms/test_throwback_v1_machine.py`(新建)

**Interfaces:**
- Consumes: 现有 `_emit_tb_gate(bo_idx, gate_idx, gate_name, measured, threshold, atr_window, on_gate, *, op=None, threshold_param=None)`(第 6 参本 Task 按位置传 `vol_window`;Task 3 改名)、`MeasuredKindAware`、`debug_break`。
- Produces:
  ```python
  class FirstSegment(NamedTuple): enter: int; exit: int; outcome: str   # outcome ∈ _TB_OUTCOMES
  def run_first_segment(closes: np.ndarray, opens: np.ndarray, bo_idx: int, global_bottom: float,
                        vol: np.ndarray, *, max_rise_k: float = 1.5, stop_confirm_bars: int = 1,
                        max_span: int = 20, on_gate=None, vol_window: int = 14,
                        real_closes: Optional[np.ndarray] = None) -> Optional[FirstSegment]
  ```

- [ ] **Step 1: 写失败测试**

```python
# tests/path2/atoms/test_throwback_v1_machine.py
"""tb v1 首段状态机纯函数测试:判据逐条(spec §3 检查顺序)+ 三 gate + debug 锚。

约定:vol 注入式常数 1.0(k=1.5 → 反弹阈 trough+1.5);opens 缺省 = close*0.99(无阴线,
UP→DOWN 只靠收跌);bo=3(closes[0..3] 平台),gbot=50(不触发破线,除非显式给)。
"""
import numpy as np
import pytest

import path2.atoms.throwback_v1 as tb
from path2.atoms.throwback_v1 import FirstSegment, run_first_segment


def mk(closes, opens=None, vol=1.0):
    closes = np.asarray(closes, dtype=float)
    opens = (np.asarray(opens, dtype=float) if opens is not None else closes * 0.99)
    vol = (np.asarray(vol, dtype=float) if np.ndim(vol) else np.full(len(closes), float(vol)))
    return closes, opens, vol


def run(closes, opens=None, vol=1.0, bo=3, gbot=50.0, k=1.5, K=1, ms=60, on_gate=None,
        real_closes=None):
    c, o, v = mk(closes, opens, vol)
    return run_first_segment(c, o, bo, gbot, v, max_rise_k=k, stop_confirm_bars=K,
                             max_span=ms, on_gate=on_gate, vol_window=14,
                             real_closes=(None if real_closes is None
                                          else np.asarray(real_closes, dtype=float)))


class TestUpToDown:
    def test_decline_bar_then_stable_K1_then_rise(self):
        # i=4 收跌 99<100 → DOWN trough=99;i=5 99.5 不刷新且 <100.5 → cnt=1≥1 → STABLE enter=5;
        # i=6 120 > 99+1.5 → rise,exit=5
        assert run([100, 100, 100, 100, 99, 99.5, 120]) == FirstSegment(5, 5, 'rise')

    def test_red_bar_triggers_down_even_if_close_up(self):
        opens = [99, 99, 99, 99, 102, 100, 100]        # i=4 阴线:close 101 < open 102
        assert run([100, 100, 100, 100, 101, 101.2, 130], opens) == FirstSegment(5, 5, 'rise')

    def test_no_pullback_stays_up_and_returns_none(self):
        gates = []
        assert run([100, 100, 100, 100, 101, 101.2, 130], ms=3, on_gate=gates.append) is None
        assert [g.gate_name for g in gates] == ['budget_no_stable']


class TestDown:
    def test_new_low_refreshes_trough_and_resets_count(self):
        # K=2:i=4 DOWN trough=99;i=5 98.5 刷新 cnt=0;i=6 98.6 cnt=1;i=7 98.7 cnt=2 → enter=7
        assert run([100, 100, 100, 100, 99, 98.5, 98.6, 98.7, 130], K=2) == FirstSegment(7, 7, 'rise')

    def test_equal_value_is_not_refresh(self):
        # i=5 close == trough(99)→ 不刷新 → cnt=1 → enter=5
        assert run([100, 100, 100, 100, 99, 99, 130]) == FirstSegment(5, 5, 'rise')

    def test_rebound_returns_to_up_not_death(self):
        # i=4 DOWN trough=99;i=5 101 > 100.5 → UP(不判死);i=6 100<101 收跌 → DOWN trough=100;
        # i=7 100.2 → enter=7;i=8 130 → rise
        assert run([100, 100, 100, 100, 99, 101, 100, 100.2, 130]) == FirstSegment(7, 7, 'rise')

    def test_vol_nan_degrades_rebound_arm(self):
        # i=5 105 本应反弹回 UP,但 vol NaN → 反弹臂降级 → 计数 → enter=5;i=6 130 > peak → rise
        vol = [1.0] * 7
        vol[5] = float('nan'); vol[6] = float('nan')
        assert run([100, 100, 100, 100, 99, 105, 130], vol=vol) == FirstSegment(5, 5, 'rise')


class TestStable:
    def test_rise_by_peak_arm_only(self):
        # k=100 → vol 臂不可达;i=6 100.5 > peak=100 → rise
        assert run([100, 100, 100, 100, 99, 99.5, 100.5], k=100) == FirstSegment(5, 5, 'rise')

    def test_rise_by_vol_arm_below_peak(self):
        # i=6 92.5 > 90+1.5(仍低于 peak 100)→ rise
        assert run([100, 100, 100, 100, 90, 90.5, 92.5]) == FirstSegment(5, 5, 'rise')

    def test_equal_to_peak_is_not_rise_then_timeout_includes_last_bar(self):
        # ms=3 → end=6;i=6 close==peak 不触发;扫满 STABLE → timeout,end=6(含末根)
        assert run([100, 100, 100, 100, 99, 99.5, 100], k=100, ms=3) == FirstSegment(5, 6, 'timeout')

    def test_weak_exit(self):
        assert run([100, 100, 100, 100, 95, 95.5, 94.9]) == FirstSegment(5, 5, 'weak')

    def test_end_clamped_to_last_bar(self):
        # n=7,ms=60 → end=6;STABLE 到末根 → timeout(5,6)
        assert run([100, 100, 100, 100, 99, 99.5, 99.6], k=100) == FirstSegment(5, 6, 'timeout')


class TestGlobalBottom:
    def test_break_before_stable_returns_none_with_gate(self):
        gates = []
        assert run([100, 100, 100, 100, 97], gbot=98, on_gate=gates.append) is None
        assert len(gates) == 1
        g = gates[0]
        assert g.gate_name == 'break_no_stable'
        assert g.failure_event_window == (4, 4) and g.start_idx == 4 and g.gate_idx == 4
        assert g.anchor_bar == 3
        assert g.measured.kind == 'anchor_delta' and g.measured.value == pytest.approx(97 - 98)

    def test_break_truncate_in_stable_still_yields_event(self):
        gates = []
        assert run([100, 100, 100, 100, 95, 95.5, 93], gbot=94,
                   on_gate=gates.append) == FirstSegment(5, 5, 'break')
        assert [g.gate_name for g in gates] == ['break_truncate']
        assert gates[0].gate_idx == 6

    def test_equal_to_gbot_is_not_break(self):
        assert run([100, 100, 100, 100, 95, 95.5, 130], gbot=95) == FirstSegment(5, 5, 'rise')

    def test_budget_no_stable_gate_fields(self):
        gates = []
        assert run([100, 101, 102, 103, 104, 105, 106], ms=3, on_gate=gates.append) is None
        g = gates[0]
        assert g.gate_name == 'budget_no_stable'
        assert g.gate_idx == 6 and g.failure_event_window == (4, 6)
        assert g.measured.kind == 'count' and g.measured.value == 3

    def test_no_gate_when_on_gate_none(self):
        assert run([100, 100, 100, 100, 97], gbot=98) is None   # 不抛、不 emit


class TestRealCloses:
    def test_red_arm_uses_real_close_not_measure(self):
        # measure 列全程不阴线(opens 99),但真 close[4]=98 < open 99 → 阴线 → DOWN trough=101(measure)
        opens = [99] * 7
        real = [100, 100, 100, 100, 98, 100, 100]
        assert run([100, 100, 100, 100, 101, 101.5, 130], opens,
                   real_closes=real) == FirstSegment(5, 5, 'rise')
        assert run([100, 100, 100, 100, 101, 101.5, 130], opens, ms=3) is None


class TestDebugAnchors:
    def test_fire_sequence_confirm_then_end(self, monkeypatch):
        calls = []
        monkeypatch.setattr(tb, 'debug_break',
                            lambda i, *, anchor_kind, **_kw: calls.append((anchor_kind, i)))
        assert run([100, 100, 100, 100, 99, 99.5, 120]) == FirstSegment(5, 5, 'rise')
        assert calls == [('confirm', 5), ('end', 5)]

    def test_timeout_end_anchor_is_last_bar(self, monkeypatch):
        calls = []
        monkeypatch.setattr(tb, 'debug_break',
                            lambda i, *, anchor_kind, **_kw: calls.append((anchor_kind, i)))
        run([100, 100, 100, 100, 99, 99.5, 100], k=100, ms=3)
        assert calls == [('confirm', 5), ('end', 6)]

    def test_bo_at_last_bar_empty_scan(self):
        gates = []
        assert run([100, 100, 100, 100, 100], bo=4, on_gate=gates.append) is None
        assert [g.gate_name for g in gates] == ['budget_no_stable']
```

- [ ] **Step 2: 跑测试确认失败**

Run: `$PY -m pytest tests/path2/atoms/test_throwback_v1_machine.py -q`
Expected: ImportError(`FirstSegment` / `run_first_segment` 不存在)。

- [ ] **Step 3: 实现纯函数**(插到 `throwback_v1.py` 的 `_emit_tb_gate` 定义之后;文件顶部补 `import numpy as np`)

```python
class FirstSegment(NamedTuple):
    """首段结果:enter=入段根(第 K 根不刷新根),exit=收口根,outcome ∈ _TB_OUTCOMES。"""
    enter: int
    exit: int
    outcome: str


def run_first_segment(
    closes: np.ndarray, opens: np.ndarray, bo_idx: int, global_bottom: float,
    vol: np.ndarray, *,
    max_rise_k: float = 1.5, stop_confirm_bars: int = 1, max_span: int = 20,
    on_gate: Optional[Callable[[GateFailure], None]] = None, vol_window: int = 14,
    real_closes: Optional[np.ndarray] = None,
) -> Optional[FirstSegment]:
    """UP/DOWN/STABLE 价格行为状态机,**首段收口即停**(spec §3,检查顺序固定不可换)。

    扫描 [bo+1, min(bo+max_span, n-1)],每根按序:
      0. close < global_bottom → 终止:STABLE 中 → (enter, i-1, 'break') 并 emit break_truncate;
         入段前 → emit break_no_stable,返回 None。
      1. UP:peak = max(peak, close)(更新先于转换判定);阴线(真 close < open)或收跌
         (close < close[i-1])→ DOWN,trough = close,count = 0。
      2. DOWN:close < trough(严格)→ 刷新 trough、count 清零;否则 close > trough + k·vol(i)
         → 回 UP(反弹不判死,等下一轮回踩;vol NaN 时该臂降级不触发);否则 count += 1,
         count ≥ K → STABLE,enter = i(第 K 根不刷新根本身)。
      3. STABLE:close > trough + k·vol(i) **或** close > peak → (enter, i-1, 'rise');
         close < trough → (enter, i-1, 'weak')。两者都终止。
    预算扫满仍 STABLE → (enter, end, 'timeout')(含末根);未入段 → emit budget_no_stable,None。
    全部数值比较用 closes/opens 所代表的 measure 列;阴线臂用 real_closes(None 时退回 closes)。
    全部严格不等式(等值不触发)。debug_break:confirm@enter、end@收口根(埋在判据现场)。
    rise / weak / timeout 收口不 emit gate。
    """
    n = len(closes)
    end = min(bo_idx + max_span, n - 1)
    state = 'UP'
    peak = float(closes[bo_idx])
    trough = float('inf')
    cnt = 0
    gbot = float(global_bottom)
    enter = -1

    def vol_at(i: int) -> Optional[float]:
        v = float(vol[i])
        return v if v == v else None          # NaN → None(反弹臂降级)

    for i in range(bo_idx + 1, end + 1):
        c = float(closes[i])
        # ══ 0 全局退出(最高优先)══
        if c < gbot:
            if state == 'STABLE':
                _emit_tb_gate(bo_idx, i, 'break_truncate',
                              MeasuredKindAware(kind='anchor_delta', value=c - gbot, label='破位差'),
                              0.0, vol_window, on_gate, op='>=', threshold_param=None)
                debug_break(i - 1, anchor_kind='end')
                return FirstSegment(enter, i - 1, 'break')
            _emit_tb_gate(bo_idx, i, 'break_no_stable',
                          MeasuredKindAware(kind='anchor_delta', value=c - gbot, label='破位差'),
                          0.0, vol_window, on_gate, op='>=', threshold_param=None)
            return None
        # ══ 1 UP ══
        if state == 'UP':
            if c > peak:
                peak = c
            red = (float(real_closes[i]) if real_closes is not None else c) < float(opens[i])
            if red or c < float(closes[i - 1]):
                state, trough, cnt = 'DOWN', c, 0
        # ══ 2 DOWN ══
        elif state == 'DOWN':
            v = vol_at(i)
            if c < trough:
                trough, cnt = c, 0
            elif v is not None and c > trough + max_rise_k * v:
                state = 'UP'
            else:
                cnt += 1
                if cnt >= stop_confirm_bars:
                    state, enter = 'STABLE', i
                    debug_break(i, anchor_kind='confirm')
        # ══ 3 STABLE ══
        else:
            v = vol_at(i)
            if (v is not None and c > trough + max_rise_k * v) or c > peak:
                debug_break(i - 1, anchor_kind='end')
                return FirstSegment(enter, i - 1, 'rise')
            if c < trough:
                debug_break(i - 1, anchor_kind='end')
                return FirstSegment(enter, i - 1, 'weak')
    if state == 'STABLE':
        debug_break(end, anchor_kind='end')
        return FirstSegment(enter, end, 'timeout')
    _emit_tb_gate(bo_idx, end, 'budget_no_stable',
                  MeasuredKindAware(kind='count', value=max_span, label='max_span 扫满(未入段)'),
                  max_span, vol_window, on_gate)
    return None
```

- [ ] **Step 4: 跑测试确认通过**

Run: `$PY -m pytest tests/path2/atoms/test_throwback_v1_machine.py -q` → 全 PASS;再 `$PY -m pytest tests/ -q` 全绿(旧代码未动)。

- [ ] **Step 5: Commit**

```bash
git add path2/atoms/throwback_v1.py tests/path2/atoms/test_throwback_v1_machine.py
git commit -m "feat(tb-v1): 首段即停状态机纯函数 run_first_segment(与旧两阶段并存)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: throwback_v3 本地化 `_atr_at` / `_has_stop_signal`(去 v1 依赖,零行为变化)

**Files:**
- Modify: `path2/atoms/throwback_v3.py:40`(删 `from path2.atoms.throwback_v1 import _atr_at, _has_stop_signal`,加本地定义)

**Interfaces:** v3 内 `_atr_at(df, idx, period) -> float`、`_has_stop_signal(df, i) -> bool` 签名与行为逐字不变。

- [ ] **Step 1: 替换 import 为本地定义**

把 `throwback_v3.py` 第 40 行 `from path2.atoms.throwback_v1 import _atr_at, _has_stop_signal` 删除;在 import 区加 `from path2.calc.atr import calculate_atr`;在模块常量 `_TB_SEG_OUTCOMES` 之前粘贴(从当前 `throwback_v1.py` 逐字复制):

```python
# ── 从 throwback_v1(2026-08-25 重写前)逐字搬入的私有 helper(v3 为冻结遗留,不再依赖 v1)──
_STOP_SIGNALS = ('lower_shadow', 'bullish', 'close_up')


def _positive_signals(df: pd.DataFrame, i: int) -> List[str]:
    """5 类积极信号 OR;返回所有触发的信号名称列表(可空)。

    阈值(Nison/Bulkowski 教科书):
      doji:         body/rng ≤ 0.10
      lower_shadow: (min(o,c)-l)/rng ≥ 0.50
      bullish:      c > o
      close_up:     c > prev_c
      gap_up:       open[i] > close[i-1]
    """
    o = float(df['open'].iat[i])
    c = float(df['close'].iat[i])
    h = float(df['high'].iat[i])
    l = float(df['low'].iat[i])
    rng = max(h - l, 1e-9)
    body = abs(c - o)
    prev_c = float(df['close'].iat[i - 1]) if i > 0 else c

    sigs: List[str] = []
    if body / rng <= 0.10:
        sigs.append('doji')
    if (min(o, c) - l) / rng >= 0.50:
        sigs.append('lower_shadow')
    if c > o:
        sigs.append('bullish')
    if c > prev_c:
        sigs.append('close_up')
    if i > 0 and o > df['close'].iat[i - 1]:
        sigs.append('gap_up')
    return sigs


def _has_stop_signal(df: pd.DataFrame, i: int) -> bool:
    """该根是否含止跌 K 线证据(下影/阳线/收涨之一)。"""
    sigs = _positive_signals(df, i)
    return any(s in sigs for s in _STOP_SIGNALS)


def _atr_at(df: pd.DataFrame, idx: int, period: int) -> float:
    """idx 处的 Wilder ATR;越界/NaN → 0.0。"""
    atr = calculate_atr(df['high'], df['low'], df['close'], period)
    v = float(atr.iat[idx])
    return v if v == v else 0.0   # NaN != NaN → fallback 0.0
```

- [ ] **Step 2: 跑 v3 / bb_v3 测试**

Run: `$PY -m pytest tests/path2/atoms/test_throwback_v3.py tests/path2/atoms/test_throwback_v3_debug_anchor_kinds.py tests/path2_apps -q` → PASS;`grep -n "throwback_v1" path2/atoms/throwback_v3.py` → 只剩 docstring 提及,无 import。

- [ ] **Step 3: bb_v3 regress 零 DIFF**

写临时脚本到 scratchpad 并运行(不进 repo):

```python
import sys; sys.path.insert(0, "<worktree 绝对路径>")
from path2_web.eval_runner import run_regress
out = run_regress(baseline_path="<worktree>/outputs/path2_eval/bb_v3_baseline_pre_simplify.json",
                  data_dir="/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls", workers=24,
                  out_path="<worktree>/outputs/path2_eval/bb_v3_regress_task2.json")
print(len(out["added"]), len(out["removed"]), out["unchanged_count"])
```
Expected: `0 0 426`。非零 = 搬迁出错,必修。

- [ ] **Step 4: Commit**

```bash
git add path2/atoms/throwback_v3.py
git commit -m "refactor(tb-v3): 本地化 _atr_at/_has_stop_signal,解除对 throwback_v1 的依赖(regress 零 DIFF)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: 重写事件 / detector,接线 bb_v1 与沙盒 app,重做测试面(原子切换)

**Files:**
- Modify: `path2/atoms/throwback_v1.py`(整文件重写,保留 Task 1 的 `FirstSegment` / `run_first_segment`)
- Modify: `path2_apps/bb_v1/params.py`(`TbParams` + `throwback_kwargs`)、`path2_apps/bb_v1/params.yaml`(tb 段)、`path2_apps/bb_v1/dag_spec.py`(tb where / edge / eval_meta / docstring)
- Modify: `path2_apps/try_conplex_where/params.py`(`TbParams`)、`params.yaml`(tb 段)、`dag_spec.py:136,159`
- Create: `tests/path2/atoms/test_throwback_v1_detector.py`
- Delete: `tests/path2/atoms/{test_throwback.py,test_throwback_unified.py,test_throwback_v1_scb_mode.py,test_throwback_v1_burst_anchor.py,test_throwback_v1_toxic_gate.py,test_tb_on_gate.py,test_tb_e2e_outcomes.py,test_throwback_event.py,test_throwback_success_debug.py,test_throwback_debug_hook.py}`
- Modify: `tests/path2/atoms/test_gate_failure_contract.py`(`test_tb_gate_invariant_op_and_param_same_nullability` + import)、`tests/path2/dag/test_gate_failure_code_location.py:42-80`、`tests/path2_apps/bb_v1/test_bb_v1.py`

**Interfaces:**
- Consumes: Task 1 的 `run_first_segment` / `FirstSegment`;`path2.calc.atr.calculate_tr_median(highs, lows, closes, window) -> pd.Series`;`path2.calc.measure.measure_series(df, measure) -> pd.Series`、`measure_at(df, i, measure)`、`VALID_MEASURES`。
- Produces:
  ```python
  @dataclass(frozen=True)
  class ThrowbackEventV1(Event): anchor_bo_id: str = ""; outcome: str = "rise"; max_day_drop: float = 0.0
  class ThrowbackDetectorV1:
      has_debug_hooks = True; event_cls = ThrowbackEventV1; on_gate = None
      def __init__(self, *, max_rise_k: float = 1.5, stop_confirm_bars: int = 1,
                   vol_window: int = 14, max_span: int = 20, measure: str = 'close')
      def detect(self, burst_stream, df) -> Iterator[ThrowbackEventV1]
  _emit_tb_gate(bo_idx, gate_idx, gate_name, measured, threshold, vol_window, on_gate, *, op=None, threshold_param=None)
  _revert_max_day_drop(df, bo_idx, confirm_idx) -> float   # 逐字保留
  # bb_v1: TbParams(max_rise_k, stop_confirm_bars, vol_window, max_span, measure, max_day_drop_pct)
  #        Params.throwback_kwargs() -> 5 键(不含 max_day_drop_pct)
  ```

- [ ] **Step 1: 删除旧测试文件**

```bash
git rm tests/path2/atoms/test_throwback.py tests/path2/atoms/test_throwback_unified.py \
  tests/path2/atoms/test_throwback_v1_scb_mode.py tests/path2/atoms/test_throwback_v1_burst_anchor.py \
  tests/path2/atoms/test_throwback_v1_toxic_gate.py tests/path2/atoms/test_tb_on_gate.py \
  tests/path2/atoms/test_tb_e2e_outcomes.py tests/path2/atoms/test_throwback_event.py \
  tests/path2/atoms/test_throwback_success_debug.py tests/path2/atoms/test_throwback_debug_hook.py
```

- [ ] **Step 2: 写新 detector 测试(失败)**

```python
# tests/path2/atoms/test_throwback_v1_detector.py
"""ThrowbackEventV1 + ThrowbackDetectorV1(首段即停)测试:字段 / e2e 四 outcome / gate 契约 /
debug 锚 fire 序列 / 排序不变式 / max_day_drop 字段。

fixture 约定:_base_series 造 n 根平台 (o=h=l=c=base),vol_window=3 让 median TR 在第 4 根即有效
(TR=2:high-low),便于用小数据流。bo 由 _bo/_burst 造,burst span 单根(gbot=span 内 measure 最小)。
"""
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

import path2.atoms.throwback_v1 as tb
from path2.atoms.breakout import BOEvent, BurstEvent
from path2.atoms.throwback_v1 import ThrowbackDetectorV1, ThrowbackEventV1, _revert_max_day_drop
from path2.dag.gate_failure import GateFailure
from path2.debug import set_current_symbol


def _make_df(rows):
    return pd.DataFrame(rows, columns=['open', 'high', 'low', 'close', 'volume'])


def _bo(idx):
    return BOEvent(start_idx=idx, end_idx=idx, confirm_idx=idx, instance_id=f"bo_{idx}#0")


def _burst(*bos):
    first, last = bos[0], bos[-1]
    return BurstEvent(start_idx=first.start_idx, end_idx=last.end_idx,
                      confirm_idx=last.end_idx, members=tuple(bos))


def _base_series(n, base=100.0):
    # high-low=2 → TR=2 → median TR=2;k=1.5 → 反弹阈 trough+3
    return [(base, base + 1.0, base - 1.0, base, 1000) for _ in range(n)]


def _det(**kw):
    d = dict(max_rise_k=1.5, stop_confirm_bars=1, vol_window=3, max_span=20, measure='close')
    d.update(kw)
    return ThrowbackDetectorV1(**d)


@pytest.fixture(autouse=True)
def _reset_symbol():
    yield
    set_current_symbol(None)


class TestInit:
    def test_defaults_and_measure_validation(self):
        d = ThrowbackDetectorV1()
        assert d._kw == dict(max_rise_k=1.5, stop_confirm_bars=1, vol_window=14, max_span=20,
                             measure='close')
        with pytest.raises(ValueError):
            ThrowbackDetectorV1(measure='nope')
        assert ThrowbackDetectorV1.event_cls is ThrowbackEventV1
        assert ThrowbackDetectorV1.on_gate is None and ThrowbackDetectorV1.has_debug_hooks


class TestEventFields:
    def test_rise_event_fields(self):
        rows = _base_series(10)
        rows[9] = (100.0, 104.0, 100.0, 103.0, 5000)         # bo_9,span_min=min close[9..9]=103
        rows += [(103.0, 103.5, 102.0, 102.5, 1000),         # 10 收跌 → DOWN trough=102.5
                 (102.5, 103.0, 102.0, 102.8, 1000),         # 11 不刷新 → STABLE enter=11
                 (102.8, 108.0, 102.8, 107.0, 1000)]         # 12 107 > 102.5+1.5*medTR → rise
        df = _make_df(rows)
        evs = list(_det().detect([_burst(_bo(9))], df))
        assert len(evs) == 1
        e = evs[0]
        assert (e.start_idx, e.end_idx, e.confirm_idx) == (11, 11, 11)
        assert e.outcome == 'rise' and e.anchor_bo_id == 'bo_9#0'
        assert e.max_day_drop == pytest.approx(_revert_max_day_drop(df, 9, 11))
        assert e.max_day_drop == pytest.approx((103.0 - 102.5) / 103.0)

    def test_break_by_span_min_uses_burst_span(self):
        # burst span [7,9]:close[7]=101 是 span 内最小 → gbot=101;回踩 close 100.5 <101 → 入段前破线 → 不产
        rows = _base_series(10)
        rows[7] = (101.0, 102.0, 100.0, 101.0, 3000)
        rows[9] = (103.0, 104.0, 102.0, 103.0, 5000)
        rows += [(103.0, 103.5, 100.0, 100.5, 1000)]
        df = _make_df(rows)
        assert list(_det().detect([_burst(_bo(7), _bo(9))], df)) == []

    def test_boundary_bo_skipped(self):
        df = _make_df(_base_series(6))
        assert list(_det().detect([_burst(_bo(0))], df)) == []       # bo<1
        assert list(_det().detect([_burst(_bo(6))], df)) == []       # bo>=len


class TestOutcomesE2E:
    def _df(self):
        rows = _base_series(10)
        rows[9] = (100.0, 104.0, 100.0, 103.0, 5000)                  # bo_9(gbot 103)
        rows += [(103.0, 103.5, 102.0, 102.5, 1000),                  # 10 DOWN trough=102.5(≥103? 否→)
                 ]
        return rows

    def test_weak_outcome(self):
        rows = _base_series(10)
        rows[9] = (100.0, 104.0, 95.0, 96.0, 5000)                    # bo_9,gbot=96
        rows += [(96.0, 97.0, 95.5, 98.0, 1000),                      # 10 阳线收涨 → 仍 UP
                 (98.0, 98.5, 97.0, 97.5, 1000),                      # 11 收跌 → DOWN trough=97.5
                 (97.5, 98.0, 97.0, 97.6, 1000),                      # 12 不刷新 → STABLE enter=12
                 (97.6, 97.8, 96.5, 97.0, 1000)]                      # 13 97 < 97.5 → weak,end=12
        evs = list(_det().detect([_burst(_bo(9))], _make_df(rows)))
        assert [(e.start_idx, e.end_idx, e.outcome) for e in evs] == [(12, 12, 'weak')]

    def test_break_outcome_in_stable(self):
        rows = _base_series(10)
        rows[9] = (100.0, 104.0, 99.0, 100.0, 5000)                   # gbot=100
        rows += [(100.0, 100.5, 99.5, 99.8, 1000),                    # 10 收跌 → DOWN?  99.8<100=gbot → 破线
                 ]
        # 99.8 < gbot 入段前 → 不产;换成先企稳再破线:
        rows = _base_series(10)
        rows[9] = (100.0, 104.0, 99.0, 100.0, 5000)                   # gbot=100
        rows += [(101.0, 101.5, 100.2, 100.4, 1000),                  # 10 阴线(100.4<101)→ DOWN trough=100.4
                 (100.4, 100.9, 100.3, 100.5, 1000),                  # 11 不刷新 → STABLE enter=11
                 (100.5, 100.6, 99.0, 99.5, 1000)]                    # 12 99.5<gbot → break,end=11
        gates = []
        det = _det(); det.on_gate = gates.append
        set_current_symbol("T")
        evs = list(det.detect([_burst(_bo(9))], _make_df(rows)))
        assert [(e.start_idx, e.end_idx, e.outcome) for e in evs] == [(11, 11, 'break')]
        assert [g.gate_name for g in gates] == ['break_truncate']

    def test_timeout_outcome_includes_last_bar(self):
        rows = _base_series(10)
        rows[9] = (100.0, 104.0, 100.0, 103.0, 5000)
        rows += [(103.0, 103.5, 102.0, 102.5, 1000),                  # 10 DOWN trough=102.5
                 (102.5, 103.0, 102.0, 102.6, 1000),                  # 11 STABLE enter=11
                 (102.6, 103.0, 102.2, 102.7, 1000),                  # 12 横盘
                 (102.7, 103.0, 102.2, 102.65, 1000)]                 # 13 末根,横盘
        evs = list(_det(max_span=4).detect([_burst(_bo(9))], _make_df(rows)))   # end=min(13, 13)
        assert [(e.start_idx, e.end_idx, e.outcome) for e in evs] == [(11, 13, 'timeout')]

    def test_multiple_bursts_sorted_by_end_then_start(self):
        rows = _base_series(10)
        rows[9] = (100.0, 104.0, 100.0, 103.0, 5000)
        rows += [(103.0, 103.5, 102.0, 102.5, 1000), (102.5, 103.0, 102.0, 102.8, 1000),
                 (102.8, 108.0, 102.8, 107.0, 1000)]                   # bo_9 → (11,11,'rise')
        rows += _base_series(6, base=107.0)
        rows[18] = (107.0, 112.0, 107.0, 110.0, 5000)                  # bo_18
        rows += [(110.0, 110.5, 109.0, 109.5, 1000), (109.5, 110.0, 109.0, 109.8, 1000),
                 (109.8, 116.0, 109.8, 115.0, 1000)]                   # → (20,20,'rise')
        df = _make_df(rows)
        evs = list(_det().detect([_burst(_bo(18)), _burst(_bo(9))], df))   # 乱序喂入
        assert [(e.start_idx, e.end_idx) for e in evs] == [(11, 11), (20, 20)]
        assert [e.anchor_bo_id for e in evs] == ['bo_9#0', 'bo_18#0']


class TestGateContract:
    def test_break_no_stable_gate_fields(self):
        rows = _base_series(10)
        rows[9] = (100.0, 104.0, 100.0, 103.0, 5000)
        rows += [(103.0, 103.5, 100.0, 100.5, 1000)]                   # 10 <gbot=103 → break_no_stable
        gates = []
        det = _det(); det.on_gate = gates.append
        set_current_symbol("SYM")
        assert list(det.detect([_burst(_bo(9))], _make_df(rows))) == []
        assert len(gates) == 1
        g = gates[0]
        assert isinstance(g, GateFailure) and g.gate_name == 'break_no_stable'
        assert g.failure_event_window == (10, 10) and g.start_idx == 10 and g.gate_idx == 10
        assert g.anchor_bar == 9 and g.symbol == 'SYM'
        assert g.evaluation_lookback == (10 - 3, 9)
        assert g.threshold_param is None or g.op is not None

    def test_budget_no_stable_gate(self):
        rows = _base_series(10)
        rows[9] = (100.0, 104.0, 100.0, 103.0, 5000)
        rows += [(103.0, 105.0, 103.0, 104.0, 1000), (104.0, 106.0, 104.0, 105.0, 1000)]  # 一路涨
        gates = []
        det = _det(max_span=2); det.on_gate = gates.append
        assert list(det.detect([_burst(_bo(9))], _make_df(rows))) == []
        assert [g.gate_name for g in gates] == ['budget_no_stable']
        assert gates[0].gate_idx == 11 and gates[0].measured.value == 2

    def test_no_gate_on_success_paths(self):
        rows = _base_series(10)
        rows[9] = (100.0, 104.0, 100.0, 103.0, 5000)
        rows += [(103.0, 103.5, 102.0, 102.5, 1000), (102.5, 103.0, 102.0, 102.8, 1000),
                 (102.8, 108.0, 102.8, 107.0, 1000)]
        gates = []
        det = _det(); det.on_gate = gates.append
        assert len(list(det.detect([_burst(_bo(9))], _make_df(rows)))) == 1
        assert gates == []

    def test_emit_helper_skips_debug_break_when_on_gate_none(self, monkeypatch):
        calls = []
        monkeypatch.setattr(tb, 'debug_break', lambda i, *, anchor_kind, **_kw: calls.append(i))
        from path2.dag.gate_failure import MeasuredKindAware
        tb._emit_tb_gate(9, 12, 'break_no_stable', MeasuredKindAware(kind='count', value=0.0, label='x'),
                         0.0, 14, None)
        assert calls == []
        collected = []
        tb._emit_tb_gate(9, 12, 'break_no_stable', MeasuredKindAware(kind='count', value=0.0, label='x'),
                         0.0, 14, collected.append)
        assert calls == [12] and len(collected) == 1


class TestDebugAnchors:
    def test_success_fire_sequence_entry_confirm_end(self):
        rows = _base_series(10)
        rows[9] = (100.0, 104.0, 100.0, 103.0, 5000)
        rows += [(103.0, 103.5, 102.0, 102.5, 1000), (102.5, 103.0, 102.0, 102.8, 1000),
                 (102.8, 108.0, 102.8, 107.0, 1000)]
        with patch('path2.atoms.throwback_v1.debug_break') as mock_break:
            evs = list(_det().detect([_burst(_bo(9))], _make_df(rows)))
        calls = [(c.kwargs['anchor_kind'], c.args[0]) for c in mock_break.call_args_list]
        assert calls == [('entry', 9), ('confirm', 11), ('end', 11)]
        assert (evs[0].start_idx, evs[0].end_idx) == (11, 11)      # 锚 bar 与事件字段对齐

    def test_failure_fire_sequence_entry_gate(self):
        rows = _base_series(10)
        rows[9] = (100.0, 104.0, 100.0, 103.0, 5000)
        rows += [(103.0, 103.5, 100.0, 100.5, 1000)]
        det = _det(); det.on_gate = lambda gf: None
        with patch('path2.atoms.throwback_v1.debug_break') as mock_break:
            list(det.detect([_burst(_bo(9))], _make_df(rows)))
        calls = [(c.kwargs['anchor_kind'], c.args[0]) for c in mock_break.call_args_list]
        assert calls == [('entry', 9), ('gate', 10)]


class TestRevertMaxDayDrop:
    def test_algorithm_unchanged(self):
        rows = _base_series(10)
        rows += [(100.0, 101.0, 90.0, 92.0, 1000),     # 10 阴线 revert_idx=10:drop (100-92)/100=0.08
                 (92.0, 93.0, 80.0, 82.0, 1000),       # 11 drop (92-82)/92≈0.1087
                 (82.0, 84.0, 81.0, 83.0, 1000)]       # 12 收涨
        df = _make_df(rows)
        assert _revert_max_day_drop(df, 9, 12) == pytest.approx((92.0 - 82.0) / 92.0)
        assert _revert_max_day_drop(df, 9, 9) == 0.0
```

Run: `$PY -m pytest tests/path2/atoms/test_throwback_v1_detector.py -q` → FAIL(新签名 / 字段不存在)。

- [ ] **Step 3: 重写 `path2/atoms/throwback_v1.py`**

整文件替换为下面内容(`FirstSegment` / `run_first_segment` 逐字沿用 Task 1 的实现,放在标注位置):

```python
"""throwback v1(2026-08-25 重写):post-burst **首段即停**的价格行为状态机。

一句话定位:每 burst 一台 UP/DOWN/STABLE 机器,DOWN 找底(K 根不刷新入段)、STABLE 为唯一
买点窗,rise / weak / break / timeout 任一收口即终止;一 burst 至多一个扁平事件。与 v4
(throwback_v4.py,多段容器 + ratchet + re-entry)的唯一差异 = 首段收口即停(2026-08-25
用户裁定:多段无意义,先做对单次买入)。

核心判据:见 run_first_segment docstring(spec §3 伪代码逐条对应,含检查顺序与严格不等式约定)。
口径:单一 measure(默认 close)统一全部数值比较;阴线臂恒用真 close/open;波动单位 =
median TR 即时取 i-1(calc.atr.calculate_tr_median,vol NaN 热身 → 反弹臂降级);
global_bottom = burst span [start_idx, end_idx] 内 measure 最小(旧 span_min,固定)。
可执行窗语义不变:窗内每 bar 都是即时买入日,label pipeline 逐日消费(end_node='tb')。
输出字段:见 ThrowbackEventV1。资格型门槛(回踩段单日跌幅)只出字段 max_day_drop,阈值由
app where 表达(bb_v1:W.attr("max_day_drop", "<", max_day_drop_pct)),detector 不设门。

设计文档:docs/superpowers/specs/2026-08-25-tb-v1-first-segment-design.md。
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Callable, ClassVar, Iterable, Iterator, List, NamedTuple, Optional

import numpy as np
import pandas as pd

from path2.atoms.breakout import BurstEvent
from path2.calc.atr import calculate_tr_median
from path2.calc.measure import VALID_MEASURES, measure_at, measure_series
from path2.core import Event
from path2.dag.gate_failure import GateFailure, MeasuredKindAware
from path2.debug import current_symbol
from path2.debug_ctx import debug_break


# tb 事件结局值域:首段四种收口方式
_TB_OUTCOMES = ("rise", "weak", "break", "timeout")


def _revert_max_day_drop(df: pd.DataFrame, bo_idx: int, confirm_idx: int) -> float:
    """回踩段 [revert_idx, confirm_idx] 内最大单日跌幅(pct 口径;资格型原始量,落字段 max_day_drop)。

    revert_idx = bo 后第一根「阴线(c<o)或收跌(c<c_prev)」bar(找不到则 bo+1);
    段内遍历收跌日,返回 max (c[i-1]-c[i])/c[i-1](无收跌日 → 0.0)。
    只用 ≤confirm_idx 的数据(无前瞻)。口径拍板(2026-08-18 研究,
    docs/research/2026-08-18_tb-v1-revert-quality/):绝对跌幅优于 TR 中位数归一。
    """
    c = df['close']
    o = df['open']
    revert_idx = bo_idx + 1
    for i in range(bo_idx + 1, confirm_idx + 1):
        if float(c.iat[i]) < float(o.iat[i]) or float(c.iat[i]) < float(c.iat[i - 1]):
            revert_idx = i
            break
    max_drop = 0.0
    for i in range(revert_idx, confirm_idx + 1):
        ci, cprev = float(c.iat[i]), float(c.iat[i - 1])
        if ci < cprev and cprev > 0:
            max_drop = max(max_drop, (cprev - ci) / cprev)
    return max_drop


def _emit_tb_gate(bo_idx: int, gate_idx: int, gate_name: str,
                  measured: MeasuredKindAware, threshold,
                  vol_window: int,
                  on_gate: Optional[Callable[[GateFailure], None]],
                  *, op: Optional[str] = None,
                  threshold_param: Optional[str] = None) -> None:
    """辅助 · 组装 GateFailure 并 emit。

    一 burst 一次 run_first_segment = 一次 attempt,attempt 起点 = bo+1;
    failure_event_window=(bo+1, gate_idx);evaluation_lookback=(gate_idx-vol_window, gate_idx-1)
    (median TR 即时窗,随 gate_idx 移动)。on_gate is None → 早退(生产路径零开销,
    非 scan/diagnose 分野:真实 scan 也挂 collector)。
    """
    if on_gate is None:
        return
    debug_break(gate_idx, anchor_kind='gate', stop_at_frame=sys._getframe(1))
    on_gate(GateFailure(
        failure_event_window=(bo_idx + 1, gate_idx),
        start_idx=bo_idx + 1,
        gate_idx=gate_idx,
        anchor_bar=bo_idx,
        gate_name=gate_name,
        measured=measured,
        threshold=threshold,
        op=op,
        threshold_param=threshold_param,
        evaluation_lookback=(gate_idx - vol_window, gate_idx - 1),
        symbol=current_symbol.get() or '',
    ))


# ── 状态机纯函数(Task 1 实现,逐字沿用)──
class FirstSegment(NamedTuple):
    ...  # Task 1 的定义


def run_first_segment(...):
    ...  # Task 1 的实现(注意:内部对 _emit_tb_gate 的第 6 个位置参数现在语义就是 vol_window)


@dataclass(frozen=True)
class ThrowbackEventV1(Event):
    """突破后可执行整理买窗事件(首段即停)。span=[enter, exit];confirm_idx = start_idx
    (确认型:企稳在 enter 根已成立,砍掉 end 仍可判)。

    outcome = 窗口关闭原因,四值 ∈ _TB_OUTCOMES:
    - "rise":   close > trough + k·vol 或 close > peak → 涨前一根收窗(成功脱离);
    - "weak":   close < trough → 企稳被跌破前一根收窗;
    - "break":  close < global_bottom(burst span 内最低)→ 破位前一根收窗(事件仍产);
    - "timeout": 预算 max_span 扫满仍在段内 → 末根收窗(含末根)。
    事件存在 ⟺ 首次 DOWN→STABLE 发生;入段前破线 / 预算尽未入段不产。

    输出字段(where 可引用):
    - anchor_bo_id:  本实例来源 bo(burst 末 bo)的 instance_id;
    - outcome:       上述四值;
    - max_day_drop:  资格型原始量——回踩段 [bo 后首根阴线或收跌, enter] 内单日最大跌幅
                     (pct;无收跌日 0.0;无前瞻)。阈值由 app where 表达(bb_v1 day_drop 闸)。
    """
    anchor_bo_id: str = ""
    outcome: str = "rise"
    max_day_drop: float = 0.0


class ThrowbackDetectorV1:
    """派生 detector:消费 burst 流,每 burst 一台首段即停状态机,产扁平事件。

    参数(5 个,全部几何/口径参数;资格型门槛不在此):
      max_rise_k=1.5      反弹/脱离阈值,vol(i) 倍数;DOWN→UP 反弹臂与 STABLE rise 出口共用
      stop_confirm_bars=1 K = 不刷新根数,enter = 第 K 根不刷新根本身
      vol_window=14       median TR 滚动窗(即时取 i-1;非 Wilder ATR)
      max_span=20         全局预算,扫描 [bo+1, bo+max_span];与 app edge max_gap 共用 SSoT
      measure='close'     全部数值比较口径(阴线臂恒 close/open)
    global_bottom = burst span [start_idx, end_idx] 内 measure 最小值(固定,不再可选)。
    核心判据见 run_first_segment。多源 L2+ detector(detect(self, burst_stream, df) 双参,
    走 run() 变参透传);输出按 (end_idx, start_idx) 升序(run() 升序不变式);同窗口多 bo
    各产一条(实例流语义,各带单来源 anchor_bo_id)。vol 与 measure 列全程一次预计算。
    """
    has_debug_hooks: ClassVar[bool] = True

    event_cls = ThrowbackEventV1
    on_gate = None   # Detector.on_gate protocol 静态声明;默认 None = 生产路径无开销

    def __init__(self, *, max_rise_k: float = 1.5, stop_confirm_bars: int = 1,
                 vol_window: int = 14, max_span: int = 20, measure: str = 'close'):
        if measure not in VALID_MEASURES:
            raise ValueError(f"measure 必须在 {VALID_MEASURES},实际 {measure!r}")
        self._kw = dict(max_rise_k=max_rise_k, stop_confirm_bars=stop_confirm_bars,
                        vol_window=vol_window, max_span=max_span, measure=measure)

    def detect(self, burst_stream: Iterable[BurstEvent], df: pd.DataFrame) -> Iterator[ThrowbackEventV1]:
        events: List[ThrowbackEventV1] = []
        vol = calculate_tr_median(df['high'], df['low'], df['close'],
                                  self._kw['vol_window']).values
        measure = self._kw['measure']
        closes = measure_series(df, measure).values
        opens = df['open'].values
        real_closes = df['close'].values
        for burst in burst_stream:
            last_bo = burst.members[-1]
            bo = last_bo.end_idx
            debug_break(bo, anchor_kind='entry')   # attempt 入口(每 burst 一次)
            if bo < 1 or bo >= len(df):
                continue
            gbot = min(measure_at(df, i, measure)
                       for i in range(burst.start_idx, burst.end_idx + 1))
            seg = run_first_segment(
                closes, opens, bo, float(gbot), vol,
                max_rise_k=self._kw['max_rise_k'],
                stop_confirm_bars=self._kw['stop_confirm_bars'],
                max_span=self._kw['max_span'],
                on_gate=self.on_gate, vol_window=self._kw['vol_window'],
                real_closes=real_closes)
            if seg is None:
                continue
            events.append(ThrowbackEventV1(
                start_idx=seg.enter, end_idx=seg.exit,
                confirm_idx=seg.enter,
                anchor_bo_id=last_bo.instance_id,
                outcome=seg.outcome,
                max_day_drop=_revert_max_day_drop(df, bo, seg.enter)))
        events.sort(key=lambda e: (e.end_idx, e.start_idx))   # run() 要 end 升序
        yield from events
```

删除的旧符号:`_STOP_SIGNALS`、`_positive_signals`、`_has_stop_signal`、`_atr_at`、`_find_confirm_idx`、`_find_end_idx`、`evaluate_throwback`、`ThrowbackResult`,以及 `calculate_atr`、`BOEvent` import。全库 `grep -rn "evaluate_throwback\|ThrowbackResult\|_find_confirm_idx" --include=*.py .` 只应命中 `throwback_v3.py` / `throwback_v4.py` / `throwback.py` 自身的同名或注释。

- [ ] **Step 4: 接线 bb_v1**

`path2_apps/bb_v1/params.py` 的 `TbParams` 整类替换:

```python
@dataclass(frozen=True)
class TbParams:
    """ThrowbackDetectorV1 构造参数(5 个,首段即停状态机,2026-08-25 重写)+ tb node where 阈值。

    资格型门槛不进 detector:max_day_drop_pct 只作 tb where(W.attr("max_day_drop", "<", thr)),
    throwback_kwargs() 不含它。max_span 同时是 burst→tb edge 的 max_gap(SSoT)。
    默认值:max_rise_k / stop_confirm_bars / vol_window 沿用 v4 定值;max_span=20 为占位,
    由 2026-08-25 验证闸三档对比后拍板。
    """
    max_rise_k: float = 1.5          # 反弹/脱离阈值(median TR 倍数),DOWN→UP 与 STABLE rise 共用
    stop_confirm_bars: int = 1       # K 根不刷新入段(enter = 第 K 根不刷新根)
    vol_window: int = 14             # median TR 滚动窗(即时取 i-1)
    max_span: int = 20               # 全局预算 [bo+1, bo+max_span];edge max_gap 同值
    measure: str = "close"           # 全部数值比较口径(calc.measure);阴线臂恒 close/open
    max_day_drop_pct: Optional[float] = 0.20  # 资格型 where 阈值:回踩段单日跌幅 ≥ 此值 → where 拦;None=不加该 where
```

`Params.throwback_kwargs` 替换:

```python
    def throwback_kwargs(self) -> dict:
        """ThrowbackDetectorV1 构造参数(5 键);max_day_drop_pct 是 where 阈值,不传 detector。"""
        d = asdict(self.tb)
        d.pop('max_day_drop_pct')
        return d
```

模块 docstring 里「共用字段(tb.max_start_gap …)」改为 `tb.max_span`。

`path2_apps/bb_v1/params.yaml` 的 `tb:` 段整段替换:

```yaml
tb:
  max_rise_k: 1.5         # 反弹/脱离阈值(median TR 倍数)
  stop_confirm_bars: 1    # K 根不刷新入段
  vol_window: 14          # median TR 滚动窗(即时取 i-1)
  max_span: 20            # 全局预算 [bo+1, bo+max_span];edge max_gap 同值(SSoT)。占位值,验证闸后拍板
  measure: close          # 全部数值比较口径;阴线臂恒 close/open
  max_day_drop_pct: 0.20  # 资格型 where 阈值(2026-08-18 定案):回踩段单日跌幅≥此值→tb where 拦;null=不加该 where
```

`path2_apps/bb_v1/dag_spec.py`:
1. import 补 `from typing import Optional`(已有)并保持 `from path2.dag import where as W`;
2. tb `NodeSpec` 改为:
```python
        # ⑦⑨ 末突破后回踩(V1 首段即停状态机,消费 burst 流,锚 last_bo);⑨ 资格型 where:回踩段单日跌幅
        NodeSpec("tb",
                 ThrowbackDetectorV1(**params.throwback_kwargs()),
                 where=(() if params.tb.max_day_drop_pct is None else
                        (("day_drop", W.attr("max_day_drop", "<", params.tb.max_day_drop_pct)),)),
                 consumes_stream="burst"),
```
3. edge:`min_gap=1, max_gap=params.tb.max_span,` 注释改「max_gap 与 ThrowbackDetectorV1(max_span=...) 共用同一 SSoT (tb.max_span)」;
4. `eval_meta` 里 `p.tb.atr_window` → `p.tb.vol_window`;
5. 模块 docstring 约束表补一行 `⑨ 回踩段单日跌幅 < tb.max_day_drop_pct -> tb where W.attr("max_day_drop")`,并把「默认参数 = tune 分支 p2.yaml(V1 调参版)」改为「tb 参数 = 2026-08-25 首段状态机重写默认值」。

- [ ] **Step 5: 接线 try_conplex_where(沙盒,同签名)**

`path2_apps/try_conplex_where/params.py::TbParams` 整类替换为与 bb_v1 **相同**的 6 字段(默认同 bb_v1,docstring 首行改「ThrowbackDetectorV1 构造参数(首段即停)+ where 阈值」);`throwback_kwargs` 同 bb_v1(`pop('max_day_drop_pct')`)。`params.yaml` `tb:` 段替换为与 bb_v1 相同六行。`dag_spec.py:136` `max_gap=params.tb.max_start_gap` → `max_gap=params.tb.max_span`;`:159` `p.tb.atr_window` → `p.tb.vol_window`;tb NodeSpec 不加 where(沙盒只玩 burst where)。

验证:`$PY -c "import path2_apps.try_conplex_where.dag_spec as m; print(m.PATTERN_DAG.pattern_id)"` 不炸。

- [ ] **Step 6: 改跨模块测试**

`tests/path2/atoms/test_gate_failure_contract.py`:第 6 行 import 改为 `from path2.atoms.throwback_v1 import ThrowbackDetectorV1`,加 `from path2.atoms.breakout import BurstEvent`;`test_tb_gate_invariant_op_and_param_same_nullability` 整函数替换:

```python
def test_tb_gate_invariant_op_and_param_same_nullability():
    """跑 ThrowbackDetectorV1 触发一个真实 tb gate(break_no_stable:入段前 close < span_min)。"""
    set_current_symbol("TEST")
    rows = [(100.0, 101.0, 99.0, 100.0, 1000.0)] * 10
    rows[9] = (100.0, 104.0, 100.0, 103.0, 5000.0)      # bo_9,gbot=103
    rows += [(103.0, 103.5, 100.0, 100.5, 1000.0)]      # 10 < gbot → break_no_stable
    df = pd.DataFrame(rows, columns=['open', 'high', 'low', 'close', 'volume'])
    from path2.atoms.breakout import BOEvent as _BOEvent
    bo = _BOEvent(start_idx=9, end_idx=9, confirm_idx=9, instance_id="bo_9#0")
    burst = BurstEvent(start_idx=9, end_idx=9, confirm_idx=9, members=(bo,))
    det = ThrowbackDetectorV1(vol_window=3)
    captured: list[GateFailure] = []
    det.on_gate = captured.append
    list(det.detect([burst], df))
    assert len(captured) > 0, "tb fixture 未触发任何 gate → 契约测试 vacuous"
    for g in captured:
        if g.threshold_param is not None:
            assert g.op is not None, \
                f'契约违约:{g.gate_name} · threshold_param={g.threshold_param!r} 但 op is None'
```

`tests/path2/dag/test_gate_failure_code_location.py::test_code_location_skips_emit_tb_gate_helper` 整函数替换:

```python
def test_code_location_skips_emit_tb_gate_helper():
    """走 throwback_v1._emit_tb_gate 路径时,code_location 应指回调用者所在文件
    (throwback_v1.py 内的 run_first_segment),而非 helper 自身."""
    from path2.atoms.throwback_v1 import ThrowbackDetectorV1
    from path2.atoms.breakout import BOEvent, BurstEvent
    from path2.debug import set_current_symbol
    import pandas as pd

    set_current_symbol("TEST")
    try:
        rows = [(100.0, 101.0, 99.0, 100.0, 1000.0)] * 10
        rows[9] = (100.0, 104.0, 100.0, 103.0, 5000.0)
        rows += [(103.0, 103.5, 100.0, 100.5, 1000.0)]      # 入段前破 span_min → break_no_stable
        df = pd.DataFrame(rows, columns=['open', 'high', 'low', 'close', 'volume'])
        bo = BOEvent(start_idx=9, end_idx=9, confirm_idx=9, instance_id="bo_9#0")
        burst = BurstEvent(start_idx=9, end_idx=9, confirm_idx=9, members=(bo,))
        det = ThrowbackDetectorV1(vol_window=3)
        captured: list[GateFailure] = []
        det.on_gate = captured.append
        list(det.detect([burst], df))

        assert len(captured) >= 1, 'tb fixture 未触发任何 gate → 测试 vacuous'
        for gf in captured:
            assert 'throwback_v1.py' in gf.code_location, \
                f'{gf.gate_name}: code_location={gf.code_location!r},expected throwback_v1.py'
    finally:
        set_current_symbol(None)
```

`tests/path2_apps/bb_v1/test_bb_v1.py`:
- `test_pattern_id_and_topology` 里 `assert e.max_gap == Params.default().tb.max_start_gap` → `== Params.default().tb.max_span`;
- `test_throwback_kwargs_match_v1_signature` 整函数替换:
```python
def test_throwback_kwargs_match_v1_signature():
    """throwback_kwargs 五键一一喂给 V1 detector;max_day_drop_pct 是 where 阈值不在其中。"""
    p = Params.default()
    kw = p.throwback_kwargs()
    assert set(kw) == {"max_rise_k", "stop_confirm_bars", "vol_window", "max_span", "measure"}
    d = ThrowbackDetectorV1(**kw)
    assert d._kw["max_span"] == p.tb.max_span and d._kw["measure"] == "close"


def test_tb_where_day_drop():
    """⑨ 资格型闸:tb node where 只有 day_drop,字段 max_day_drop,op '<',阈值来自 params;None 时无 where。"""
    p = Params.default()
    nodes = {n.node_id: n for n in build_pattern(p).nodes}
    where = dict(nodes["tb"].where)
    assert set(where) == {"day_drop"}
    pred = where["day_drop"]
    assert pred.meta["field"] == "max_day_drop" and pred.meta["op"] == "<"
    assert pred.meta["threshold"] == p.tb.max_day_drop_pct == 0.20
    from dataclasses import replace
    p2 = replace(p, tb=replace(p.tb, max_day_drop_pct=None))
    nodes2 = {n.node_id: n for n in build_pattern(p2).nodes}
    assert nodes2["tb"].where == ()
```
- `test_eval_meta` 保持 `{"end_node": "tb", "head_buffer_trading_days": 63}`(vol_window 14 < 63);
- `test_analyze_smoke_real_data` 里 `"datasets/pkls/AA.pkl"` 改为绝对路径 `"/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls/AA.pkl"`(worktree 无 datasets;若该测试原本用相对路径且在主目录能跑,改绝对路径两边都能跑)。

`tests/path2/atoms/test_trend.py:120` 不改(import 目标仍存在)。

- [ ] **Step 7: 全量测试**

Run: `$PY -m pytest tests/ -q` → 全绿。`grep -rn "max_start_gap\|atr_window\|big_rise_k\|judged_measure\|scb_mode\|anchor_mode" path2_apps/bb_v1 path2_apps/try_conplex_where path2/atoms/throwback_v1.py` → 0 命中。

- [ ] **Step 8: Commit**

```bash
git add -A path2/atoms/throwback_v1.py path2_apps/bb_v1 path2_apps/try_conplex_where tests/
git commit -m "feat(tb-v1)!: 重写为首段即停状态机(5 参数),毒药闸降为 max_day_drop 字段 + bb_v1 where

删 judged/reference 双口径、scb rising、anchor_mode、止跌信号池、两段预算;bb_v1 tb 参数换代
(max_span 为 edge SSoT)。旧 scan 需重扫生效。

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: 前端 hint 文案 + feature-study 常量注释

**Files:**
- Modify: `path2_web_ui/src/stores/view.ts`(`tbV1Anchors` 三个 hint 字符串)
- Modify: `.claude/skills/feature-study/extract_skeleton.py:48`

**Interfaces:** 前端 anchor key/bar 不变(entry/confirm/end ↔ boBar/start_idx/end_idx)。

- [ ] **Step 1: 改三处 hint**

`tbV1Anchors` 内:
- entry: `hint: '停在一次回踩评估的入口 · 看 anchor / atr 起点'` → `hint: '停在本 burst 状态机入口(每 burst 一次)· 看 global_bottom(span 内 measure 最小)与 vol 起点'`
- confirm: `hint: '停在企稳确认根 · 看 trough_idx / stop signal'` → `hint: '停在入段根(第 K 根不刷新)· 看 state / trough / cnt / peak'`
- end: `hint: '停在段收口 · 看大涨 / timeout 两分支'` → `hint: '停在段收口根 · 看 rise / weak / break / timeout 哪条收口'`

- [ ] **Step 2: extract_skeleton 常量**

`ATR_WINDOW = 14               # params tb.atr_window(控制列用)` → `VOL_WINDOW = 14               # params tb.vol_window(median TR 窗,控制列用;2026-08-25 tb_v1 换代前叫 atr_window)`,并把文件内其余 `ATR_WINDOW` 引用改名(`grep -n ATR_WINDOW .claude/skills/feature-study/extract_skeleton.py` 逐处改)。

- [ ] **Step 3: 前端检查**

Run(在 `path2_web_ui/`):`npx vue-tsc --noEmit && npx vitest run` → 绿。

- [ ] **Step 4: Commit**

```bash
git add path2_web_ui/src/stores/view.ts .claude/skills/feature-study/extract_skeleton.py
git commit -m "chore(tb-v1): 前端 V1 锚点 hint 语义化 + feature-study 常量随参数换代

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: 诊断契约 + 索引 + 速查条目

**Files:**
- Create: `.claude/skills/diagnose-event/detectors/throwback_v1.md`
- Modify: `.claude/skills/diagnose-event/reference.md:55`
- Modify: `.claude/skills/authoring-path2-detector/reference.md`(§1 在 `### ThrowbackDetectorV4` 之前插入条目)

- [ ] **Step 1: 写契约文件**(以实际代码为准核对签名后写)

```markdown
# node 语义契约 · tb(bb_v1 · throwback_v1 首段即停状态机)

> 本文由 **authoring-path2-detector** 在创建/修改本 detector 时同步维护——诊断"为什么"的语义依据,与代码必须一致;不一致时以代码为准(代码是 SSoT)。
> 首次沉淀:2026-08-25 tb_v1 重写(spec `docs/superpowers/specs/2026-08-25-tb-v1-first-segment-design.md`)。

模块:`path2/atoms/throwback_v1.py` · 消费者:bb_v1 的 `tb` node(扁平事件,`eval_meta.end_node = 'tb'`)、try_conplex_where(沙盒)

一句话定位:每 burst 一台 UP/DOWN/STABLE 机器,首段收口即停——DOWN 找底(K 根不刷新入段)、STABLE 为唯一买点窗;rise / weak / break / timeout 任一收口即终止。与 v4 的唯一差异 = 不产第二段(无 ratchet / re-entry / 容器)。

## 事件结构
- `ThrowbackEventV1`(node_id `tb`):span=[enter, exit];confirm=start(确认型);`outcome ∈ ('rise','weak','break','timeout')`;`anchor_bo_id` = 末 bo instance_id;`max_day_drop` = 回踩段 [bo 后首根阴线/收跌, enter] 单日最大跌幅(资格型原始量,bb_v1 where `day_drop`:`max_day_drop < max_day_drop_pct`)。
- 一 burst 至多一个事件;同 span 多 bo 各产一条(不去重)。

## API 签名
```python
run_first_segment(closes, opens, bo_idx, global_bottom, vol, *, max_rise_k=1.5, stop_confirm_bars=1,
                  max_span=20, on_gate=None, vol_window=14, real_closes=None) -> Optional[FirstSegment(enter, exit, outcome)]
ThrowbackDetectorV1(*, max_rise_k=1.5, stop_confirm_bars=1, vol_window=14, max_span=20, measure='close')
    .detect(burst_stream, df) -> Iterator[ThrowbackEventV1]   # 多源 L2+
```
参数语义:`max_rise_k` 反弹/脱离阈值(median TR 倍数,两臂共用)/ `stop_confirm_bars` K 不刷新根数(enter=第 K 根)/ `vol_window` median TR 窗(即时取 i-1,NaN 热身 → 反弹臂降级)/ `max_span` 全局预算 [bo+1, bo+max_span],= bb_v1 edge max_gap(SSoT)/ `measure` 全部数值比较口径,阴线臂恒 close/open。global_bottom = burst span 内 measure 最小(固定)。

## 状态机判据顺序(每根,固定)
0. close < global_bottom → 终止:STABLE 中 → (enter, i-1, 'break')(事件仍产);入段前 → 不产
1. UP:peak = max(peak, close)(先更新);阴线(真 close<open)或收跌 → DOWN(trough=close, cnt=0)
2. DOWN:① close < trough → 刷新、cnt=0 ② close > trough + k·vol(i) → 回 UP(不判死) ③ cnt+=1,cnt ≥ K → STABLE enter=i
3. STABLE:① close > trough + k·vol(i) **或** close > peak → (enter, i-1, 'rise') ② close < trough → (enter, i-1, 'weak')
4. 收尾:预算尽仍 STABLE → (enter, end, 'timeout')(含末根);未入段 → 不产
全部严格不等式(等值不触发)。

## gate 名表
| gate_name | 触发 | measured.kind | 事件 |
|---|---|---|---|
| `break_no_stable` | 入段前 close < global_bottom | anchor_delta | 不产 |
| `budget_no_stable` | 预算尽未入段 | count | 不产 |
| `break_truncate` | STABLE 中 close < global_bottom | anchor_delta | 产(outcome=break) |
window:`failure_event_window=(bo+1, gate_idx)`;`evaluation_lookback=(gate_idx-vol_window, gate_idx-1)`;`anchor_bar=bo`。**rise / weak / timeout 收口不 emit gate**——靠 outcome / debug 锚诊断。毒药闸不再是 gate:看 tb node where `day_drop` 的 predicate_trace。
debug_break 三锚:`entry`@bo(每 burst)/ `confirm`@enter / `end`@exit;失败路 `entry` → `gate`。前端 `tbV1Anchors`(entry/confirm/end)。

## 典型失效模式
- bo < 1 / bo ≥ len(df):不启动(不 emit gate)
- 全程 UP 无回踩(一路阳线收涨)→ `budget_no_stable`(bo_only 语义,正确静默)
- 持续阴跌每根刷新 trough、cnt 恒零 → 陪跑满 max_span → `budget_no_stable`(max_span 别过大)
- V 反弹:DOWN 反弹臂回 UP 不判死;预算内再无回踩 → `budget_no_stable`
- 事件产了但 match 没了:看 tb where `day_drop`(max_day_drop ≥ 0.20)或 edge gap(enter − bo > max_span 不可能;gap 按 edge min_gap=1)
- 参数名换代:`max_start_gap/max_window/atr_window/big_rise_k/judged_measure/reference_measure/scb_mode/anchor_mode` 已不存在

## 骨架 B 变体(局部重算该 burst)
```python
from path2.atoms.throwback_v1 import run_first_segment
from path2.calc.atr import calculate_tr_median
from path2.calc.measure import measure_at, measure_series
tbp = snapshot['tb']                     # scan params_snapshot 的 tb 段
vol = calculate_tr_median(df['high'], df['low'], df['close'], tbp['vol_window']).values
bo = burst.end_idx
gbot = min(measure_at(df, i, tbp['measure']) for i in range(burst.start_idx, burst.end_idx + 1))
gates = []
seg = run_first_segment(measure_series(df, tbp['measure']).values, df['open'].values, bo, float(gbot), vol,
                        max_rise_k=tbp['max_rise_k'], stop_confirm_bars=tbp['stop_confirm_bars'],
                        max_span=tbp['max_span'], on_gate=gates.append, vol_window=tbp['vol_window'],
                        real_closes=df['close'].values)
# seg None → 看 gates[0].gate_name;seg 非 None → (enter, exit, outcome);
# 再算 _revert_max_day_drop(df, bo, seg.enter) 对照 where 阈值
```
```

- [ ] **Step 2: 索引与速查**

`.claude/skills/diagnose-event/reference.md:55` 改为:
`- \`detectors/throwback_v1.md\` — V1 首段即停状态机(\`path2/atoms/throwback_v1.py\`,bb_v1):run_first_segment、三 gate(break_no_stable / budget_no_stable / break_truncate)、rise/weak/timeout 不 emit、day_drop 走 where`

`.claude/skills/authoring-path2-detector/reference.md` §1 在 `### ThrowbackDetectorV4` 之前插入:

```markdown
### ThrowbackDetectorV1（path2/atoms/throwback_v1.py）
- **检测什么**：一句话定位——post-burst 首段即停状态机：UP/DOWN/STABLE 三态，DOWN 找底（K 根不刷新入段）、STABLE 为唯一买点窗，rise / weak / break / timeout 任一收口即终止；一 burst 至多一个扁平事件（无容器、无 re-entry）。诊断契约：`diagnose-event/detectors/throwback_v1.md`
- **静默不产的情形**（失效边界）：
  1. `bo < 1` / `bo >= len(df)`：不启动（不 emit gate）；
  2. 入段前 close < global_bottom（burst span 内 measure 最小）→ `break_no_stable`；
  3. 预算 `max_span` 尽未入段（全程 UP 无回踩 / 持续阴跌每根刷新 trough）→ `budget_no_stable`；
  4. V 反弹：DOWN 反弹臂回 UP **不判死**（与旧 v1 的 rise-before-confirm 整 attempt 判死不同）；
  5. 毒药闸不再静默不产：事件照产、`max_day_drop` 字段由 app where 拦（bb_v1 `day_drop`）。
- **常见误配**：① 参数名换代——`max_start_gap/max_window/atr_window/big_rise_k/judged_measure/reference_measure/scb_mode/anchor_mode` 已不存在，现为 `max_rise_k/stop_confirm_bars/vol_window/max_span/measure`（vol 是 median TR 非 Wilder ATR）；② `max_span` 与 bb_v1 edge `max_gap` 共用 SSoT，改预算两处同查；③ `max_day_drop_pct` 是 where 阈值，传给 detector 会 TypeError；④ STABLE rise 臂是「k·vol **或** 创 peak 新高」；⑤ `eval_meta.end_node = 'tb'`（扁平，非 `tb.segments`）。
```

- [ ] **Step 3: Commit**

```bash
git add .claude/skills/diagnose-event/detectors/throwback_v1.md .claude/skills/diagnose-event/reference.md .claude/skills/authoring-path2-detector/reference.md
git commit -m "docs(skills): tb_v1 诊断契约 + 速查条目(首段即停状态机)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: 验证闸(healthcheck / regress 归因 / max_span 三档对比)

**Files:**
- Create: `docs/research/2026-08-25_tb-v1-first-segment/repro/attribute_diff.py`
- Modify: `docs/research/2026-08-25_tb-v1-first-segment/repro/scan_cmp.py`(CONFIGS)、`repro/summarize.py`(NAMES)
- Create: `docs/research/2026-08-25_tb-v1-first-segment/verification.md`(+ 由 summarize 生成的 `cmp_table.md`)

**Interfaces:** 消费 `path2_web.eval_runner.run_healthcheck / run_regress`、改前基线文件(Global Constraints 列表)、`run_first_segment`。

- [ ] **Step 1: healthcheck**(scratchpad 脚本)

```python
import sys; sys.path.insert(0, "<worktree>")
from path2_web.eval_runner import run_healthcheck
out = run_healthcheck(module_path="path2_apps.bb_v1.dag_spec", start="2024-01-01", end="2026-08-25",
                      data_dir="/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls", workers=24,
                      out_path="<worktree>/outputs/path2_eval/bb_v1_healthcheck_task6.json")
print(out["magnitude_ok"], out["universe_hit_tickers"], out["universe_buy_windows"], out["meta"]["errors"])
```
Expected:`magnitude_ok=True`、errors=0、命中股数与 344 窗基线同量级(几十到几百)。

- [ ] **Step 2: regress vs bb_v1 基线 + 归因**

```python
import sys; sys.path.insert(0, "<worktree>")
from path2_web.eval_runner import run_regress
out = run_regress(baseline_path="<worktree>/outputs/path2_eval/bb_v1_baseline_pre_simplify.json",
                  data_dir="/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls", workers=24,
                  out_path="<worktree>/outputs/path2_eval/bb_v1_regress_task6.json")
print("added", len(out["added"]), "removed", len(out["removed"]), "unchanged", out["unchanged_count"])
```

然后写 `repro/attribute_diff.py`(进 repo):对 regress 文件里 removed / added 各取前 5 条(按 symbol 去重),用 `path2_web.data.slice_window` 切与基线 `meta` 同窗(`start`/`end`/`head_buffer_trading_days`)的 df,`path2_apps.bb_v1.dag_spec.analyze(df, load_params())` 重跑,把该股 burst 逐个喂 `run_first_segment(..., on_gate=gates.append)`,打印每个 burst 的 `(enter, exit, outcome)` 或 gate 名,以及旧事件(基线行的 `buy_date`)落在哪。脚本骨架:

```python
"""regress DIFF 归因:抽样 removed/added 各 5 股,局部重算新机器首段 + gate,解释每条差异来路。"""
import json, pickle, subprocess, sys
from pathlib import Path
REPO = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
sys.path.insert(0, str(REPO))
from path2_web.data import slice_window
from path2_apps.bb_v1.dag_spec import analyze, load_params
from path2.atoms.throwback_v1 import run_first_segment, _revert_max_day_drop
from path2.calc.atr import calculate_tr_median
from path2.calc.measure import measure_at, measure_series

def main():
    REGRESS = REPO / "outputs/path2_eval/bb_v1_regress_task6.json"
    DATA = Path("/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls")
    N = 5
    r = json.loads(REGRESS.read_text()); meta = r["meta"]
    p = load_params(); tbp = p.tb
    for kind in ("removed", "added"):
        seen = []
        for row in r[kind]:
            if row["symbol"] in seen: continue
            seen.append(row["symbol"])
            if len(seen) > N: break
            df = slice_window(pickle.load(open(DATA / f"{row['symbol']}.pkl", "rb")),
                              meta["win_start"], meta["win_end"])   # 与基线同窗(键名以 regress meta 实际为准)
            res = analyze(df, p)
            bursts = [e for e in res.events if e.node_id == "burst"]
            vol = calculate_tr_median(df['high'], df['low'], df['close'], tbp.vol_window).values
            print(f"== {kind} {row['symbol']} buy_date={row['buy_date']} ==")
            for b in bursts:
                gates = []; bo = b.end_idx
                gbot = min(measure_at(df, i, tbp.measure) for i in range(b.start_idx, b.end_idx + 1))
                seg = run_first_segment(measure_series(df, tbp.measure).values, df['open'].values, bo, gbot, vol,
                                        max_rise_k=tbp.max_rise_k, stop_confirm_bars=tbp.stop_confirm_bars,
                                        max_span=tbp.max_span, on_gate=gates.append, vol_window=tbp.vol_window,
                                        real_closes=df['close'].values)
                dd = _revert_max_day_drop(df, bo, seg.enter) if seg else None
                print(f"  burst bo={bo} date={df.index[bo].date()} → {seg} gate={[g.gate_name for g in gates]} max_day_drop={dd}")

if __name__ == "__main__":
    main()
```
(`meta` 里窗口键名与 `res.events` 属性名以实际文件/对象为准,执行时 `print(meta.keys())` 核对后再改。)

归因规则:removed 必须落在 {入段前 break_no_stable / budget_no_stable / 新 enter 落在旧 buy_date 之外 / `max_day_drop ≥ 0.20` 被 where 拦} 之一;added 必须落在 {旧 v1 会判死(反弹先于确认 / 7 根预算内无确认)但新机器入段} 之一。任何一条解释不了 → 当 bug 处理,回 Task 3 修。

- [ ] **Step 3: max_span 三档 × 两窗对比扫描**

`repro/scan_cmp.py` 的 CONFIGS 改为(旧基线与 bo_only 已存在,不重跑):

```python
    CONFIGS = [
        dict(pattern_id="bb_v1", out_name="cmp-new-v1-span12-train", overrides={"tb": {"max_span": 12}}, window=TRAIN),
        dict(pattern_id="bb_v1", out_name="cmp-new-v1-span12-oos",   overrides={"tb": {"max_span": 12}}, window=OOS),
        dict(pattern_id="bb_v1", out_name="cmp-new-v1-span20-train", overrides={"tb": {"max_span": 20}}, window=TRAIN),
        dict(pattern_id="bb_v1", out_name="cmp-new-v1-span20-oos",   overrides={"tb": {"max_span": 20}}, window=OOS),
        dict(pattern_id="bb_v1", out_name="cmp-new-v1-span60-train", overrides={"tb": {"max_span": 60}}, window=TRAIN),
        dict(pattern_id="bb_v1", out_name="cmp-new-v1-span60-oos",   overrides={"tb": {"max_span": 60}}, window=OOS),
    ]
```
Run: `PYTHONPATH=$(git rev-parse --show-toplevel) $PY docs/research/2026-08-25_tb-v1-first-segment/repro/scan_cmp.py`(每个约 1-2 min)。然后 `summarize.py` 的 NAMES 把注释掉的六行打开,运行生成 `cmp_table.md`。

- [ ] **Step 4: 写 `verification.md`**

内容(只报数字,不下好坏结论):① healthcheck 数字;② bb_v3 regress 0/0(Task 2)与 bb_v1 regress added/removed/unchanged + 10 条抽样归因逐条一行;③ `cmp_table.md` 全表 + 一段读表说明:每档相对旧 v1 与 bo_only 的 match 数 / fr_med / FP 差值,训练窗与外推窗分列,`n_fp < 100` 的格标「小样本」;④ 明确写「max_span 默认值待用户拍板;当前 yaml 为 20 占位」;⑤ 列出 spec §12 的遗留项。

- [ ] **Step 5: Commit**

```bash
git add docs/research/2026-08-25_tb-v1-first-segment
git commit -m "docs(research): tb_v1 首段状态机验证闸——healthcheck/regress 归因/max_span 三档对比

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Self-Review

- **Spec coverage**:§2/§3 → Task 1;§4.1 字段 / §4.2 参数 → Task 3;§5.1-5.3 gate/埋点 → Task 1+3(测试断言 fire 序列与 gate 字段);§6 模块结构与 v3 搬迁 → Task 2+3;§7 接线(bb_v1 + try_conplex_where + eval_meta + edge SSoT)→ Task 3;§8 docstring 合同 → Task 3 代码内;§9 影响面(前端 hint / skeleton / code_location 测试)→ Task 3+4;§10 验证闸六条 → Task 2(bb_v3 零 DIFF)+ Task 6;§11 诊断契约 → Task 5。§12 遗留不实施。
- **Placeholder scan**:Task 3 Step 3 中 `FirstSegment` / `run_first_segment` 写「逐字沿用 Task 1」——Task 1 已给完整代码,实施者按文件内已有实现保留即可,非占位;`attribute_diff.py` 的 `meta` 键名标注「以实际文件为准并核对」,是显式的运行期核对步骤。
- **Type consistency**:`run_first_segment(closes, opens, bo_idx, global_bottom, vol, *, max_rise_k, stop_confirm_bars, max_span, on_gate, vol_window, real_closes)` 在 Task 1/3/5/6 一致;`_emit_tb_gate` 第 6 位置参数 Task 1 以位置传、Task 3 改名 `vol_window`,调用方式不变;`ThrowbackDetectorV1._kw` 五键与 `TbParams`/`throwback_kwargs` 五键一致;事件字段 `max_day_drop` 与 where 字段名一致;gate 名三处一致。
