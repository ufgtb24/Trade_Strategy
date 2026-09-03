"""code_location 手二契约:__post_init__ 用 sys._getframe 抓 caller、
跳过 gate_failure.py 自身 + CPython 3.12 dataclass 生成的 <string>/__init__ 帧
+ throwback 系模块的 _emit_tb_gate* helper 帧(v1 精确名;v3/v4 前缀匹配)。"""
from path2.dag.gate_failure import GateFailure, MeasuredKindAware


def _make_gf(**overrides):
    """在本文件内直接构造 GateFailure(不经 helper);默认字段为占位。"""
    base = dict(
        failure_event_window=(0, 0),
        start_idx=0, gate_idx=0, anchor_bar=0,
        gate_name='test',
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


def test_code_location_skips_emit_tb_gate_v4_helper():
    """直调 throwback_v4._emit_tb_gate_v4 时,helper 帧同样被跳过(前缀匹配),
    code_location 指回本测试文件——精确名单 '_emit_tb_gate' 不含 v3/v4 时,
    v4 的 gate code_location 会全部错误地指向 helper 自身。"""
    from path2.atoms.throwback_v4 import _emit_tb_gate_v4

    captured: list[GateFailure] = []
    _emit_tb_gate_v4(
        bo_idx=3, gate_idx=5, gate_name='budget_no_stable',
        measured=MeasuredKindAware(kind='count', value=60, label='max_span 扫满'),
        threshold=60, vol_window=14, on_gate=captured.append)

    assert len(captured) == 1, 'fixture 未触发 gate → 测试 vacuous'
    gf = captured[0]
    assert 'throwback_v4.py' not in gf.code_location, \
        f'code_location={gf.code_location!r} 指向 helper 自身,应跳过 v4 helper 帧'
    assert 'test_gate_failure_code_location.py' in gf.code_location, \
        f'code_location={gf.code_location!r} 应指回本测试文件(真 caller)'


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
