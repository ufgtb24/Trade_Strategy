"""scope=time · failure_event_window ⊆ 严格包含(Task 15)。

derive_response(query, result=...) 的 result 是可选注入的 AnalysisResult(须已挂 collector
收过 gate_failures,承 diag/spec 的 decoupled 注入模式)。真实 /diagnose 端点尚未在本任务
范围内 recompute+attach(api.py 不在 Task 15 files 内)——故本文件同时覆盖:
  (a) 未注入 result 时的诚实降级(no_analysis_result caveat,brief 原版的字面场景);
  (b) 注入真实 gate_failures 后过滤逻辑本身(brief 字面版本 result 恒 None 会让 event_class
      测试蜕化成 vacuous pass,故此处补真实数据使其有 teeth);
  (c) GateCollector + attach_and_collect/detach 的独立单测;
  (d) 一个真实 app spec 端到端验证:collector 必须挂在 analyze() 之前才能收到 detect() 内部
      emit 的 GateFailure(worker 设计的核心正确性,不能晚挂)。
"""
from dataclasses import replace as dc_replace

import pytest

from path2.dag.engine import analyze as dag_analyze
from path2.dag.gate_failure import GateFailure, MeasuredKindAware
from path2.dag.result import AnalysisResult
from path2_apps.bottom_breakout_burst.dag_spec import build_pattern
from path2_web.diagnose import (
    Caveat,
    Query,
    Response,
    TimePayload,
    _in_frame_strict,
    derive_response,
)
from path2_web.gate_collector import GateCollector, attach_and_collect, detach
from tests.path2.fixtures.positive_case import positive_case


def _fake_result(gate_failures) -> AnalysisResult:
    """构造一个只带 gate_failures 的 AnalysisResult(events/matches 留空,derive_response
    的 scope=time 路径只读 result.gate_failures,不碰其余字段)。"""
    return AnalysisResult(events=(), matches=(), gate_failures=tuple(gate_failures))


# ─── brief 字面 test(补真实 result 注入,见文件头说明) ──────────

def test_scope_time_returns_time_payload():
    q = Query(symbol='DGNX', scope='time', start_bar=100, end_bar=150)
    r = derive_response(q)
    assert r.scope == 'time'
    assert 'failed_attempts' in r.payload.__dict__ or hasattr(r.payload, 'failed_attempts')


def test_strict_subset_filter():
    """failure_event_window 严格 ⊆ user frame · 单点/跨度/框外三种边界"""
    collector = GateCollector()
    m = MeasuredKindAware(kind='gap', value=13, label='gap')
    collector.add(GateFailure(failure_event_window=(105, 118), start_idx=105, gate_idx=118,
                              anchor_bar=118, class_id='tb', gate_name='phase2_break',
                              measured=m, threshold=10, op=None, threshold_param=None,
                              evaluation_lookback=None, symbol='DGNX'))
    # (105, 118) ⊆ [100, 150] · 保留
    collector.add(GateFailure(failure_event_window=(60, 65), start_idx=60, gate_idx=65,
                              anchor_bar=65, class_id='burst', gate_name='chain_break',
                              measured=m, threshold=10, op=None, threshold_param=None,
                              evaluation_lookback=None, symbol='DGNX'))
    # (60, 65) 完全在框外 · 丢弃

    assert _in_frame_strict((105, 118), (100, 150)) is True
    assert _in_frame_strict((90, 105), (100, 150)) is False  # start_idx 溢出 → 定义上不属于该时段
    assert _in_frame_strict((60, 65), (100, 150)) is False
    # collector 本身照原样收下 2 条(过滤逻辑属 derive_response,不属 collector)
    assert len(collector.snapshot()) == 2


def test_event_class_filter():
    """event_class 过滤只留匹配 class_id 的 attempt(真实 result 注入,非 vacuous)。"""
    m = MeasuredKindAware(kind='gap', value=13, label='gap')
    gfs = (
        GateFailure(failure_event_window=(10, 20), start_idx=10, gate_idx=20, anchor_bar=20,
                   class_id='burst', gate_name='chain_break', measured=m, threshold=10,
                   op=None, threshold_param=None,
                   evaluation_lookback=None, symbol='DGNX'),
        GateFailure(failure_event_window=(30, 40), start_idx=30, gate_idx=40, anchor_bar=40,
                   class_id='tb', gate_name='phase2_break', measured=m, threshold=10,
                   op=None, threshold_param=None,
                   evaluation_lookback=None, symbol='DGNX'),
    )
    result = _fake_result(gfs)
    q = Query(symbol='DGNX', scope='time', start_bar=0, end_bar=200, event_class='burst')
    r = derive_response(q, result=result)
    assert len(r.payload.failed_attempts) == 1
    for gf in r.payload.failed_attempts:
        assert gf.class_id == 'burst'


# ─── 补充:result 未注入的诚实降级 · GateCollector/attach/detach 单测 · 真实端到端捕获 ──

def test_no_result_injected_returns_no_analysis_result_caveat():
    """result 未注入(端点层尚未 recompute+attach,Task 15 范围外)→ 空 payload + 说明性 caveat,
    不是 Task 8 遗留的 on_gate_hook_not_landed(那条已随 Task 9-14 落地过时)。"""
    q = Query(symbol='DGNX', scope='time', start_bar=100, end_bar=150)
    r = derive_response(q)
    assert r.payload == TimePayload(frame=(100, 150), failed_attempts=[])
    codes = [c.code for c in r.caveats]
    assert codes == ['no_analysis_result']


def test_result_with_empty_gate_failures_no_caveat():
    """result 已注入但 gate_failures=()(该 symbol 确实无 gate 失败,非"未注入")→ 干净空
    payload、无 no_analysis_result caveat 误报。"""
    result = _fake_result(())
    q = Query(symbol='DGNX', scope='time', start_bar=0, end_bar=200)
    r = derive_response(q, result=result)
    assert r.payload.failed_attempts == []
    codes = [c.code for c in r.caveats]
    assert 'no_analysis_result' not in codes


def test_gate_collector_add_snapshot_clear():
    m = MeasuredKindAware(kind='count', value=1, label='bo数')
    gf = GateFailure(failure_event_window=(1, 2), start_idx=1, gate_idx=2, anchor_bar=2,
                     class_id='burst', gate_name='min_bos_insufficient', measured=m,
                     threshold=2, op=None, threshold_param=None,
                     evaluation_lookback=None, symbol='X')
    c = GateCollector()
    assert c.snapshot() == ()
    c.add(gf)
    c.add(gf)
    assert c.snapshot() == (gf, gf)
    c.clear()
    assert c.snapshot() == ()


def test_attach_and_collect_and_detach_walk_spec_nodes():
    """attach_and_collect 把每个 node.detector.on_gate 接到同一 collector.add;detach 后
    全部复位 None(worker 每 symbol/pattern 跑完必须清干净,防同进程串扰下一轮)。"""
    _, params = positive_case()
    spec = build_pattern(params)
    collector = attach_and_collect(spec)
    # 绑定方法每次取都是新对象(obj.method is obj.method 恒 False),用 == 比较
    # __self__/__func__ 而非 is。
    assert all(node.detector.on_gate == collector.add for node in spec.nodes)
    detach(spec)
    assert all(node.detector.on_gate is None for node in spec.nodes)


def test_attach_before_analyze_captures_real_gate_failures():
    """worker 设计的核心正确性:collector 必须在 analyze() 跑之前挂上,才能收到 detect()
    内部 emit 的 GateFailure——晚挂(如跑完 mod.analyze() 再看 res.spec)收不到任何东西,
    这正是 Task 15 不能直接调 mod.analyze() 的原因(见 scan.py/eval_runner.py 的 adaptation)。
    用 burst.min_bos 抬到不可能达到,逼 min_bos_insufficient 必然在流末尾触发。

    spec 另两 node(bo/tb)也各自挂了同一 collector,detect() 全程也会正常吐出各自的
    gate_failure(bo 5 gate + tb 4 gate,Task 11/12)——这是三 atom 共享一次 analyze() 调用的
    真实行为,不是本测试的关注点;只断言"至少捕到我们特意逼出的 burst/min_bos_insufficient
    这一条",不断言"全部都是 burst"(那是错的,已被本测试的前一版本坐实)。"""
    df, params = positive_case()
    tight_params = dc_replace(params, burst=dc_replace(params.burst, min_bos=999))
    spec = build_pattern(tight_params)
    collector = attach_and_collect(spec)
    try:
        dag_analyze(spec, df, tight_params)
    finally:
        detach(spec)
    gate_failures = collector.snapshot()
    assert len(gate_failures) >= 1
    assert any(gf.class_id == 'burst' and gf.gate_name == 'min_bos_insufficient'
              for gf in gate_failures)
    assert all(node.detector.on_gate is None for node in spec.nodes)
