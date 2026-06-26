# bottom_breakout_burst: role 精简 + tb anchor + burst 区间放量 设计 spec

> 起点:dag_spec.py 现状 5 节点(bo/down/side/burst/tb)+ 3 边。
> 改动起点层:层①(拓扑)+ 层②(detector 公共 atom 增强)+ 层③(参数初值)。
> Baseline 已存: `outputs/path2_eval/bbb_pre_role_simplify.json` (tickers_hit=10, buy_windows=14, errors=0)。

## 层① 拓扑(已过 gate ✓)

### 决定:3 节点 + 1 边,burst.last_bo → tb 边附 anchor_field

**节点**:
- `bo` (BODetector,孤立流源,无边)
- `burst` (BurstDetector,consumes "bo",新放量字段见层②)
- `tb` (ThrowbackDetector,consumes "bo",已自带 anchor_bo_id 字段)

**边**(唯一一条):
```python
TemporalEdge(
    Child("burst", "last_bo"),
    "tb",
    min_gap=1,
    max_gap=params.throwback_max_start_gap,
    anchor_field="anchor_bo_id",   # ← 新加:tb.anchor_bo_id == last_bo.event_id
)
```

`anchor_src_field` 默认 `'event_id'`,无需显式传。

### 删除项
- 节点 `down`、`side`
- 边 `TemporalEdge("down","side", gap[1,5])`
- 边 `ContainmentEdge("side", Child("burst","first_bo"))`
- TrendSegmentDetector 不再被实例化(down_det / side_det 一并去掉)

### 关键设计点
1. **bo 仍保留作流源**:burst.consumes_stream="bo" / tb.consumes_stream="bo" 都需要它做名字解析;残缺单 role match 由 analyze 出口过滤丢弃(机制不变)
2. **anchor_field 是 codebase 的第一个现役业务消费者**:之前 ThrowbackEvent.anchor_bo_id 字段已存在(`throwback.py:181`、detector 内 `anchor_bo_id=bo.event_id` 已赋值),只是没有 dag 边消费;本改动接通
3. **gap 约束保留**:虽然 anchor_field 已强制 "tb 来自 last_bo",但显式 gap[1, max_start_gap] 保留作声明完整性 + 与 detector 内置语义双重防御
4. **命中量预期放宽**:删 down/side 后,burst 不再被前置形态约束;当前 10/14 可能上升数倍(用户已知)

### 被否方案
- (无,层① 一次通过)

## 层② detector(已过 gate ✓)

### 决定:BurstDetector 公共 atom 增强(语义彻底替换 + 参数化)

**BurstEvent 字段变更**(`path2/atoms/breakout.py`):
- **删** `max_vol_ratio: float`(旧:bo 内 max vol_ratio,被语义替换)
- **加** `max_bar_vol_ratio: float = 0.0`(新:burst 区间 [start, end] 内任一 bar 的 vol_ratio 最大值,**含非 BO bar**)
- 其它字段不变(count / distinct_pk / first_drought / members)

**BurstDetector 接口变更**:
```python
class BurstDetector:
    def __init__(self, gap_max: int, min_bos: int, vol_baseline_period: int = 63):
        # 新加 vol_baseline_period (3 个月默认 = 63 交易日)
        ...

    def detect(self, bos, df):
        # 全 df 算一次 vol_ratio 序列
        vol_ratio = calculate_vol_ratio(df["volume"], self.vol_baseline_period)
        # ... 原有切串 + 调 _make_burst(seg, vol_ratio)

    def _make_burst(self, seg, vol_ratio):
        start, end = seg[0].start_idx, seg[-1].end_idx
        bar_vols = vol_ratio.iloc[start : end + 1].dropna()
        max_bar_vol_ratio = float(bar_vols.max()) if len(bar_vols) else 0.0
        return BurstEvent(
            ...,
            max_bar_vol_ratio=max_bar_vol_ratio,
            # 删除 max_vol_ratio=...
        )
```

**ThrowbackDetector / ThrowbackEvent**:**零改动**。`anchor_bo_id` 字段已存在(`throwback.py:181`)、detector 已在 `line 214` 赋值 `anchor_bo_id=bo.event_id`。

### 受影响文件清单(实现期改)
- `path2/atoms/breakout.py`:BurstEvent 字段 + BurstDetector __init__/detect/_make_burst
- 9 个测试需同步:`tests/path2/atoms/test_burst.py` / `test_breakout_detector.py` / `test_throwback.py` / `tests/path2/test_event_id_unchanged.py` / `test_class_id_registry.py` / `tests/path2/dag/test_multilayer.py` / `tests/path2_apps/bottom_breakout_burst/test_dag_spec.py` / `tests/path2/atoms/test_breakout_dataclasses.py` / `tests/path2/atoms/test_throwback_event.py` —— 其中实际涉及 max_vol_ratio 字段引用的需要把字段名换成 max_bar_vol_ratio + 更新 fixture 期望值;不涉及的(class_id / event_id / dag_spec 结构等)跑 regress 即可
- `path2_apps/bottom_breakout_burst/params.py`:见层③

### 受影响 app 清单(regress 范围)
- 仅 `path2_apps/bottom_breakout_burst/`(grep 已确认全仓只一个 app 消费 BurstDetector)
- baseline 在层①已存:`outputs/path2_eval/bbb_pre_role_simplify.json`

### 被否方案
- B(双字段保留):未来 app 假设不成立,字段冗余增加 BurstEvent 复杂度
- C(布尔字段):违反 path2 "detector 算原始数值 / where 判阈值" 设计手法

## 层③ 参数初值(待最终 gate)

### Params 字段变更(`path2_apps/bottom_breakout_burst/params.py`)

**删除**(down/side role 退场带走):
- `trend_ma_period / trend_sideways_eps / trend_hysteresis_bars` 三个 trend_* 字段
- `trend_kwargs()` 方法
- `pred4_lookback_bars`(dead 字段,本就不消费)
- `pred4_min_drawdown`(down where 用,删 down 后无消费者)

**改值**:
- `MIN_BOS: int = 3` → `2`(用户要求 burst 内 bo 总数 ≥ 2)
- `THR_PK: int = 3` → `4`(用户要求 peak 总数 > 3,即 ≥ 4)
- `THR_VOL: float = 3.0` → `8.0`(新字段 max_bar_vol_ratio 语义不同、阈值大幅提升)
- `THR_DROUGHT: int = 20` 保持(burst 内首 bo 旱期未变)

**新增**:
- `burst_vol_baseline_period: int = 63`(BurstDetector 新参数;默认 3 月,与 bo_vol_baseline_period 同语义但独立)

**`burst_kwargs()` 增字段**:
```python
def burst_kwargs(self) -> dict:
    return {
        'gap_max': self.burst_gap_max,
        'min_bos': self.MIN_BOS,
        'vol_baseline_period': self.burst_vol_baseline_period,   # 新
    }
```

### dag_spec.py 落地(完整新形态)

```python
# 顶部 import 删:TrendSegmentDetector 不再用
from path2.dag.nodes import NodeSpec
from path2.dag.edges import TemporalEdge, Child
from path2.dag.spec import PatternSpec
from path2.dag.engine import analyze as _analyze
from path2.dag import where as W
from path2.atoms.breakout import BODetector, BurstDetector
from path2.atoms.throwback import ThrowbackDetector

def build_pattern(params: Params) -> PatternSpec:
    nodes = (
        NodeSpec("bo", BODetector(**params.bo_kwargs())),
        NodeSpec("burst",
                 BurstDetector(**params.burst_kwargs()),
                 where=(
                     ("first_drought",  W.attr("first_drought",   ">=", params.THR_DROUGHT)),
                     ("distinct_pk",    W.attr("distinct_pk",     ">=", params.THR_PK)),
                     ("vol_spike",      W.attr("max_bar_vol_ratio", ">=", params.THR_VOL)),  # 字段改名
                 ),
                 consumes_stream="bo", label="突破爆发"),
        NodeSpec("tb",
                 ThrowbackDetector(**params.throwback_kwargs()),
                 consumes_stream="bo", label="回踩确认"),
    )
    edges = (
        TemporalEdge(
            Child("burst", "last_bo"), "tb",
            min_gap=1, max_gap=params.throwback_max_start_gap,
            anchor_field="anchor_bo_id",   # ← 新加:tb.anchor_bo_id == last_bo.event_id
        ),
    )
    return PatternSpec(
        pattern_id="bottom_breakout_burst",
        display_name="底部反转突破爆发",
        nodes=nodes, edges=edges, root="burst",
    )
```

### eval_meta 调整

```python
def eval_meta(params):
    return {
        "end_role": "tb",
        "head_buffer_trading_days": max(
            p.bo_vol_baseline_period,
            p.burst_vol_baseline_period,   # 新:burst 也有 rolling baseline
            p.throwback_atr_window,
            p.bo_total_window,
            # 删 trend_ma_period
        ),
    }
```

## Step 3:落地文件清单

| 文件 | 改动 |
|---|---|
| `path2/atoms/breakout.py` | BurstEvent 字段(删 max_vol_ratio 加 max_bar_vol_ratio)+ BurstDetector(__init__ 加 vol_baseline_period,detect 算 vol_ratio 序列,_make_burst 算 max_bar_vol_ratio) |
| `path2_apps/bottom_breakout_burst/params.py` | 删 trend_* + pred4_* 字段;改 MIN_BOS=2 / THR_PK=4 / THR_VOL=8;加 burst_vol_baseline_period=63;改 burst_kwargs() |
| `path2_apps/bottom_breakout_burst/dag_spec.py` | 删 down/side 节点 + 2 边 + TrendSegmentDetector import / 实例化;新 1 边带 anchor_field;burst where 字段名 max_vol_ratio→max_bar_vol_ratio;eval_meta head_buffer 公式更新 |
| 9 个测试文件 | 同步字段名 / detector 参数 / dag 结构(详见层② 受影响文件清单) |

## Step 4 验证

- **判据 1(形态)**:web UI 看几个命中,确认仍是"突破爆发→回踩"形态
- **判据 2(统计 regress)**:
  ```bash
  uv run python -c "from path2_web.eval_runner import run_regress; run_regress(
      baseline_path='outputs/path2_eval/bbb_pre_role_simplify.json',
      out_path='outputs/path2_eval/bbb_post_role_simplify.json',
  )"
  ```
  期望 DIFF 大量 added(删 down/side 放宽命中量),removed 可能少量(放量阈值 8 比旧 3 严)。**逐项判**:意图内(接受)/ 意外(必修)。
- **anchor_field 新机能验证**:取一个 match,人工核对 `tb.anchor_bo_id == match.role_index["burst"].child("last_bo").event_id`

