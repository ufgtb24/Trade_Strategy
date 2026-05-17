"""§7.4-A:用 BarwiseDetector 重写 dogfood VolSpikeDetector,证明
(1) 子类只剩领域判据、无显式扫描循环(吃掉痛点1 样板);
(2) 经 run() 产出与旧实现逐字段等价(11 idx 金标准 pin 死)。
"""
import inspect
from pathlib import Path

import pandas as pd

from path2 import run, span_id
from path2.stdlib.templates import BarwiseDetector
from tests.path2.dogfood_detectors import VolSpike, VolSpikeDetector

FIXTURE = Path(__file__).parent / "fixtures" / "aapl_vol_slice.csv"


def _load():
    return pd.read_csv(FIXTURE, index_col="date", parse_dates=True)


class BarwiseVolSpike(BarwiseDetector):
    """重写版:只剩 emit 内领域判据,无显式扫描循环。
    用 to_numpy() 切片 + .mean() 与旧实现逐位等价(bit-exact ratio)。"""

    LOOKBACK = 20
    THRESHOLD = 2.0

    def emit(self, df, i):
        if i < self.LOOKBACK:
            return None
        # 每 bar 重取 numpy 视图:与旧实现逐位等价,本测试规模可忽略开销
        vol = df["volume"].to_numpy()
        mean = vol[i - self.LOOKBACK : i].mean()
        ratio = float(vol[i] / mean)
        if ratio > self.THRESHOLD:
            return VolSpike(
                event_id=span_id("vs", i, i),
                start_idx=i,
                end_idx=i,
                ratio=ratio,
            )
        return None


def test_rewrite_is_field_equivalent_to_legacy():
    df = _load()
    ref = list(run(VolSpikeDetector(), df))
    got = list(run(BarwiseVolSpike(), df))

    def proj(xs):
        return [(s.start_idx, s.end_idx, s.event_id, s.ratio) for s in xs]

    assert proj(got) == proj(ref)


def test_rewrite_hits_gold_pinned_indices():
    df = _load()
    got = list(run(BarwiseVolSpike(), df))
    assert [s.start_idx for s in got] == [
        34, 60, 61, 67, 97, 130, 176, 194, 264, 265, 267
    ]
    assert got[0].event_id == "vs_34"  # span_id 单点塌缩在真实数据上生效


def test_rewritten_subclass_has_no_explicit_scan_loop():
    # 痛点1 收口判据:重写后子类体不含显式扫描循环
    src = inspect.getsource(BarwiseVolSpike)
    # 注:getsource 含 docstring/注释,故本类内这些文本也须无 for/while/range( 字面量
    assert "for " not in src
    assert "while " not in src
    assert "range(" not in src


from path2 import Chain
from path2.core import TemporalEdge

# §7.4-B:同一条 L1 spike 流喂 Chain(A→B,gap∈[1,10]),诚实 pin 真实产出。
# 下面 _CHAIN_REAL 由 Step 2 首跑真值回填(同任务内固化,不留 TODO)。
_CHAIN_REAL: list[tuple[int, int, int]] = [(60, 61, 2), (61, 67, 2), (264, 265, 2), (265, 267, 2)]  # (start_idx, end_idx, len(children)) — §7.4-B 实跑真值固化


def test_chain_chaining_invariants_hold():
    df = _load()
    spikes = list(run(BarwiseVolSpike(), df))
    d = Chain(
        edges=[TemporalEdge("A", "B", min_gap=1, max_gap=10)],
        A=spikes,
        B=spikes,
        label="sp",
    )
    matches = list(run(d))
    # 协议层不变式经 run() 真实贯通:
    assert matches, "Chain 在真实 spike 流上应有非空产出"
    ends = [m.end_idx for m in matches]
    assert ends == sorted(ends), "end_idx 升序(run() 不变式真实成立)"
    ids = [m.event_id for m in matches]
    assert len(ids) == len(set(ids)), "event_id 单 run 唯一"
    for m in matches:
        assert all(isinstance(c, VolSpike) for c in m.children)
        assert m.pattern_label == "sp"


def test_chain_real_output_pinned():
    df = _load()
    spikes = list(run(BarwiseVolSpike(), df))
    d = Chain(
        edges=[TemporalEdge("A", "B", min_gap=1, max_gap=10)],
        A=spikes,
        B=spikes,
        label="sp",
    )
    got = [(m.start_idx, m.end_idx, len(m.children)) for m in run(d)]
    assert got == _CHAIN_REAL  # Step 2 回填后此断言固化真实产出
