"""bottom_burst dag 声明结构测试。"""
from path2.dag.edges import TemporalEdge
from path2.atoms.breakout import BODetector, BurstDetector, BOEvent, BurstEvent
from path2.atoms.throwback_v4 import ThrowbackDetectorV4, ThrowbackEventV4, ThrowbackSegmentV4
from path2_apps.bottom_burst.dag_spec import build_pattern
from path2_apps.bottom_burst.params import Params


def _spec():
    return build_pattern(Params.default())


def test_dag_spec_nodes_bo_burst_consumes():
    """dag 含 5 nodes：bo/pk/burst/tb + 子结构 tb_seg；burst consumes bo 流，tb consumes burst 流。"""
    from path2_apps.bottom_burst.dag_spec import PATTERN_DAG
    ids = {n.node_id for n in PATTERN_DAG.nodes}
    assert ids == {"bo", "burst", "pk", "tb", "tb_seg"}
    by = {n.node_id: n for n in PATTERN_DAG.nodes}
    assert by["pk"].solve is False   # pk 孤立显示 node:不参与匹配
    assert by["burst"].consumes_stream == "bo"          # burst consumes bo 流
    assert by["tb"].consumes_stream == "burst"          # tb consumes burst 流(ThrowbackDetectorV4 吃 BurstEvent)
    # bo 无边 = 孤立 node(残缺 match 由 analyze 出口过滤)
    endpoints = {ep for e in PATTERN_DAG.edges for ep in (e.src, e.dst)}
    assert "bo" not in endpoints


def test_nodes_present_and_typed():
    """5 nodes(bo/pk/burst/tb + 子结构 tb_seg)，各 detector 类型和事件类验证。"""
    spec = _spec()
    by = {n.node_id: n for n in spec.nodes}
    assert set(by) == {"bo", "burst", "pk", "tb", "tb_seg"}
    assert by["bo"].detector is by["pk"].detector   # bo/pk 共享同一 detector(兄弟机制一次 detect 填满两流)
    assert by["bo"].event_cls is BOEvent   # BODetector 多流(产 bo+pk),无 event_cls,归一化值取自 node
    assert by["burst"].detector.event_cls is BurstEvent
    assert by["tb"].detector.event_cls is ThrowbackEventV4
    assert isinstance(by["bo"].detector, BODetector)
    assert isinstance(by["burst"].detector, BurstDetector)
    assert isinstance(by["tb"].detector, ThrowbackDetectorV4)
    # 子结构 node:无 detector,event_cls/produced_by 归一化回填(children 逆映射)
    assert by["tb_seg"].detector is None
    assert by["tb_seg"].event_cls is ThrowbackSegmentV4
    assert by["tb_seg"].produced_by == "tb"


def test_bo_is_plain_isolated_node():
    """bo 是孤立 plain node（无 where、无边）。"""
    bo = {n.node_id: n for n in _spec().nodes}["bo"]
    assert bo.where == ()                                  # 无 where（孤立 node）


def test_burst_node_structure():
    """burst consumes bo 流，where 包含三个条件(③⑤⑥)，vol_spike 字段为 max_bar_vol_ratio。"""
    burst = {n.node_id: n for n in _spec().nodes}["burst"]
    assert burst.consumes_stream == "bo"
    assert {cid for cid, _ in burst.where} == {"first_drought", "distinct_pk", "vol_spike"}  # ③⑤⑥
    # ⑥ 字段名已更新为 max_bar_vol_ratio
    vol_spike_pred = dict(burst.where)["vol_spike"]
    assert vol_spike_pred.meta["field"] == "max_bar_vol_ratio"
    assert isinstance(burst.detector, BurstDetector)
    # C2 迁移:members 槽声明引用独立 bo node
    assert burst.children == {"members": "bo"}


def test_tb_consumes_burst_stream():
    """ThrowbackDetectorV4 吃 BurstEvent，tb consumes burst 流（多源 L2+）。"""
    tb = {n.node_id: n for n in _spec().nodes}["tb"]
    assert tb.consumes_stream == "burst"
    # C2 迁移:segments 槽声明引用子结构 node tb_seg
    assert tb.children == {"segments": "tb_seg"}


def test_edges_calibrated():
    """单边 burst.last_bo→tb：TemporalEdge + anchor_field="anchor_bo_id"。"""
    spec = _spec()
    assert len(spec.edges) == 1
    edge = spec.edges[0]
    assert isinstance(edge, TemporalEdge)
    assert edge.src_selector == "last_bo"              # ⑦ 锚末 bo
    assert edge.dst == "tb"
    assert edge.min_gap == 1
    assert edge.max_gap == Params.default().tb.max_span
    assert edge.anchor_field == "anchor_bo_id"


def test_to_topology_three_nodes_one_edge():
    """topo 含 5 nodes(含 pk + 子结构 tb_seg)，1 边 TemporalEdge(burst→tb)。"""
    topo = _spec().to_topology()
    assert {n.node_id for n in topo.nodes} == {"bo", "burst", "pk", "tb", "tb_seg"}
    kinds = {(e.src, e.dst): e.kind for e in topo.edges}
    assert kinds == {("burst", "tb"): "TemporalEdge"}


def test_bo_node_declares_render_grid_price():
    """bo 节点声明 render_grid='price' (上 K线主图); 其余节点保持默认 'time'。
    PatternSpec 构造不报错 = 载入期校验 (point + price) 通过。"""
    spec = _spec()
    by = {n.node_id: n for n in spec.nodes}
    assert by["bo"].render_grid == "price"
    assert by["burst"].render_grid == "time"
    assert by["tb"].render_grid == "time"


import pickle
from path2_apps.bottom_burst.dag_spec import analyze


# ---------------------------------------------------------------------------
# tb node 换线 ThrowbackDetectorV4(2026-08-16 语义换代,spec §8)
# ---------------------------------------------------------------------------

import numpy as np
import pandas as pd

from path2_apps.bottom_burst.dag_spec import build_pattern as _bp, eval_meta
from path2_apps.bottom_burst.params import load_params, BoParams, BurstParams
from path2.atoms.throwback_v4 import ThrowbackEventV4, ThrowbackSegmentV4


def _synth_tb_v4_positive():
    """合成正例(结构同 test_matches._synth_positive):

    高位下跌 → 横盘(含小 peaks) → 低位平台(drought ≥ 20) → 连续小步 BO →
    末 BO 放量 → 回落 3 根进 DOWN → 2 根不刷新小阳(第 1 根即入 STABLE) →
    大涨收段(rise) → 续填上行。V4 语义下产 1 容器 ≥1 段。
    """
    rng = np.random.default_rng(42)
    opens, closes, highs, lows, vols = [], [], [], [], []

    # phase 1: 高位下跌 200 → 75
    for i in range(100):
        c = 200.0 - (i / 100.0) * 125.0 + rng.normal(0, 0.3)
        opens.append(c + rng.normal(0, 0.1)); closes.append(c)
        highs.append(c * 1.01); lows.append(c * 0.99)
        vols.append(1000.0 + rng.normal(0, 50))

    # phase 2: 横盘含三小 peak
    for i in range(100, 220):
        base = 75.0 + 0.4 * np.sin((i - 100) * 0.2) + rng.normal(0, 0.2)
        if i in (120, 150, 180):
            base += 2.0
        opens.append(base - 0.2); closes.append(base)
        highs.append(base * 1.01); lows.append(base * 0.99)
        vols.append(1000.0 + rng.normal(0, 50))

    # phase 2b: 低位平台(低于所有 peak,保证首 BO drought ≥ 20)
    for i in range(220, 240):
        base = 74.5 + rng.normal(0, 0.1)
        opens.append(base - 0.1); closes.append(base)
        highs.append(base + 0.2); lows.append(base - 0.2)
        vols.append(900.0)

    # phase 3 (240-258): 单调小步 BO
    base3 = 75.0
    for i in range(240, 259):
        base3 += 0.20
        opens.append(base3 - 0.05); closes.append(base3)
        highs.append(base3 + 0.5); lows.append(base3 - 0.2)
        vols.append(1200.0)

    # phase 3' (idx 259): 末 BO 放量阳线 +12%
    prev_c = closes[-1]
    bo_close = prev_c * 1.12
    opens.append(prev_c); closes.append(bo_close)
    highs.append(bo_close * 1.02); lows.append(prev_c * 0.999)
    vols.append(10000.0)

    # phase 4: 回落 3 根(low 守 burst span 底)→ 2 根不刷新小阳 → 1 根大涨
    anchor = prev_c + 0.5
    for lo, c in [(anchor + 3.0, anchor + 3.5), (anchor + 1.5, anchor + 2.0),
                  (anchor + 1.0, anchor + 1.6)]:
        opens.append(c + 0.3); closes.append(c)
        highs.append(c + 0.5); lows.append(lo)
        vols.append(3000.0)
    base_trough = closes[-1]
    for c in [base_trough + 0.1, base_trough + 0.2]:
        opens.append(c - 0.3); closes.append(c)
        highs.append(c + 0.15); lows.append(anchor + 1.2)
        vols.append(3000.0)
    big_c = closes[-1] + 6.0
    opens.append(closes[-1]); closes.append(big_c)
    highs.append(big_c + 1.0); lows.append(anchor + 2.0)
    vols.append(5000.0)

    # phase 5: 续填上行至 ≥320
    while len(closes) < 320:
        pc = closes[-1]
        c = pc + 0.2 + rng.normal(0, 0.1)
        opens.append(c - 0.1); closes.append(c)
        highs.append(c * 1.01); lows.append(c * 0.99)
        vols.append(1000.0)

    return pd.DataFrame({'open': opens, 'high': highs, 'low': lows,
                         'close': closes, 'volume': vols})


def _relaxed_params():
    """宽松阈值(同 test_matches._synth_positive 配套调校,便于 bo/burst 稳定命中)。"""
    from path2_apps.bottom_burst.params import Params
    return Params(
        bo=BoParams(min_relative_height=0.02,
                    peak_measure="body_top", breakout_measure="body_top"),
        burst=BurstParams(min_bos=2, first_drought_min=20,
                          distinct_pk_min=2, vol_spike_min=3.0),
    )


class TestTbV4Wiring:
    """tb node 换线 V4:detector 类/流源/子结构/eval_meta/端到端冒烟。"""

    def test_build_pattern_uses_v4(self):
        spec = _bp(load_params())
        by = {n.node_id: n for n in spec.nodes}
        assert type(by["tb"].detector).__name__ == 'ThrowbackDetectorV4'
        assert by["tb"].consumes_stream == 'burst'
        seg = [n for n in spec.nodes if n.node_id == 'tb_seg'][0]
        assert seg.event_cls.__name__ == 'ThrowbackSegmentV4'

    def test_eval_meta_end_node_unchanged(self):
        m = eval_meta(load_params())
        assert m['end_node'] == 'tb.segments'
        assert isinstance(m['head_buffer_trading_days'], int)

    def test_analyze_smoke(self):
        """端到端:合成 df 走完整 bo→burst→回踩链,断言 tb 产出 V4 容器且 segments 槽非空。"""
        res = analyze(_synth_tb_v4_positive(), _relaxed_params())
        tbs = [e for e in res.events if getattr(e, 'node_id', '') == 'tb']
        assert tbs, "应产出 tb 容器事件"
        assert all(isinstance(t, ThrowbackEventV4) for t in tbs)
        assert all(t.segments for t in tbs), "tb 容器 segments 槽非空"
        assert all(isinstance(s, ThrowbackSegmentV4) for t in tbs for s in t.segments)

    def test_segments_named_by_children_declaration(self):
        """段物化命名:children 声明 segments→tb_seg,段 node_id/instance_id 前缀
        均为 tb_seg(annotate_stream 命名表);容器保持 tb。"""
        res = analyze(_synth_tb_v4_positive(), _relaxed_params())
        segs = [s for e in res.events if getattr(e, 'node_id', '') == 'tb'
                for s in e.segments]
        assert segs
        assert all(s.node_id == 'tb_seg' for s in segs)
        assert all(s.instance_id.startswith('tb_seg_') for s in segs)


class TestEventStyles:
    """event_styles 无显式声明,全走 serialize `_event_styles` 兜底调色板
    (首现序槽位 [2]tb/[3]tb_seg 与撤下的显式声明值同步)。tb_seg 用区别于
    bo 兜底绿(#16f943)的饱和绿——同色会触发 deriveNodeColors 明度散开。"""

    def test_palette_assigns_by_node_order(self):
        from path2_web.serialize import serialize_pattern
        spec = build_pattern(load_params())
        assert spec.event_styles == {}   # 显式声明已撤,全走兜底
        styles = serialize_pattern(spec)["event_styles"]
        # 首现序调色板:pk 加入后取槽位 [1],burst/tb/tb_seg 顺移;tb_seg 仍区别于 bo 兜底绿
        assert styles == {"bo": "#16f943", "pk": "#2563eb", "burst": "#FF1500",
                          "tb": "#14b24e", "tb_seg": "#7c3aed"}
