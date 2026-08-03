"""code_location 手二契约:__post_init__ 用 sys._getframe 抓 caller、
跳过 gate_failure.py 自身 + CPython 3.12 dataclass 生成的 <string>/__init__ 帧
+ throwback.py 的 _emit_tb_gate helper 帧。"""
from path2.dag.gate_failure import GateFailure, MeasuredKindAware


def _make_gf(**overrides):
    """在本文件内直接构造 GateFailure(不经 helper);默认字段为占位。"""
    base = dict(
        failure_event_window=(0, 0),
        start_idx=0, gate_idx=0, anchor_bar=0,
        class_id='bo', gate_name='test',
        measured=MeasuredKindAware(kind='count', value=0, label=''),
        threshold=None, op=None, threshold_param=None,
        evaluation_lookback=None, symbol='TEST',
    )
    base.update(overrides)
    return GateFailure(**base)


def test_code_location_from_direct_caller():
    """本测试文件直接调 GateFailure(...) → code_location 应含本文件 basename."""
    gf = _make_gf()
    assert 'test_gate_failure_code_location.py' in gf.code_location, \
        f'expected test file in code_location, got {gf.code_location!r}'


def test_code_location_skips_gate_failure_py():
    """不应把 gate_failure.py(__post_init__ 自身)当 caller."""
    gf = _make_gf()
    assert 'gate_failure.py' not in gf.code_location, \
        f'{gf.code_location!r} unexpectedly contains gate_failure.py'


def test_code_location_skips_dataclass_init_string_frame():
    """CPython 3.12 dataclass 生成的 __init__ co_filename=='<string>' 必须跳过."""
    gf = _make_gf()
    assert '<string>' not in gf.code_location, \
        f'{gf.code_location!r} leaked <string> frame'


def test_code_location_skips_emit_tb_gate_helper():
    """走 throwback._emit_tb_gate 路径时,code_location 应指回调用者所在文件
    (throwback.py 内的 evaluate_throwback),而非 helper 自身.

    fixture 复用 test_gate_failure_contract.py::
    test_tb_gate_invariant_op_and_param_same_nullability 的构造(bo_idx=15,
    确保 Wilder ATR 首个有效值(idx=atr_window-1=13)已就绪、不会因 atr==0.0
    短路提前 return None),保证 phase1_break 真实触发、captured 非空。
    """
    from path2.atoms.throwback import evaluate_throwback
    from path2.atoms.breakout import BOEvent
    from path2.debug import set_current_symbol
    import pandas as pd

    set_current_symbol("TEST")
    try:
        n = 30
        bo_idx = 15
        df = pd.DataFrame({
            'open': [100.0] * n, 'close': [100.0] * n,
            'high': [101.0] * n, 'low': [99.5] * n,
            'volume': [1000.0] * n,
        })
        # anchor = high[bo_idx-1] = 101;bo 后 close[bo_idx+1] = 90 < anchor → phase1_break
        df.loc[bo_idx + 1, 'close'] = 90.0
        bo = BOEvent(event_id=f"bo_{bo_idx}", start_idx=bo_idx, end_idx=bo_idx, confirm_idx=bo_idx,
                     drought=None, pk_count=1, broken_peak_ids=(), vol_ratio=None,
                     peak_vol_max=0.0, referenced_points=())
        captured: list[GateFailure] = []
        evaluate_throwback(bo, df, on_gate=captured.append)

        assert len(captured) >= 1, 'tb fixture 未触发任何 gate → 测试 vacuous'
        for gf in captured:
            # 帧跳过后应落到 throwback.py 内(evaluate_throwback),而非 _emit_tb_gate helper 自身
            assert 'throwback.py' in gf.code_location, \
                f'{gf.gate_name}: code_location={gf.code_location!r},expected throwback.py'
    finally:
        set_current_symbol(None)


def test_code_location_explicit_wins():
    """显式传入 code_location 时,__post_init__ 不覆盖."""
    gf = _make_gf(code_location='explicit.py:99')
    assert gf.code_location == 'explicit.py:99'


def test_code_location_default_fallback_to_unknown(monkeypatch):
    """帧链提前耗尽(f_back 立即为 None)时应兜底为 '<unknown>'
    (spec §8.1.C:685 · 旧/新版本兼容分支的存在意义).

    用 monkeypatch 把 sys._getframe 换成只返回单帧、且该帧匹配跳过规则①
    (filename=='gate_failure.py')又 f_back=None 的假帧:while 循环第一轮就把
    frame 推进到 None、跳出循环,落到 fallback 赋值。
    """
    import sys

    class _FakeCode:
        def __init__(self, filename, name):
            self.co_filename = filename
            self.co_name = name

    class _FakeFrame:
        def __init__(self, filename, name, f_back=None):
            self.f_code = _FakeCode(filename, name)
            self.f_back = f_back
            self.f_lineno = 0

    fake_frame = _FakeFrame('gate_failure.py', '__post_init__', f_back=None)
    monkeypatch.setattr(sys, '_getframe', lambda depth=0: fake_frame)

    gf = _make_gf()
    assert gf.code_location == '<unknown>', \
        f'expected fallback to <unknown>, got {gf.code_location!r}'
