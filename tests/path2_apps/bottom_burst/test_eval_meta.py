"""eval_meta 协议:end_node 手声明 + head_buffer 从 Params 推导(参数改动自动传导)。"""
from dataclasses import replace

from path2_apps.bottom_burst import eval_meta
from path2_apps.bottom_burst.params import Params


def test_default_meta():
    """默认参数:end_node=tb.segments(路径声明买点=tb 容器 segments 槽的企稳段),
    head_buffer=63(=bo_vol_baseline_period,当前最大 lookback)。"""
    assert eval_meta() == {"end_node": "tb.segments", "head_buffer_trading_days": 63}


def test_head_buffer_tracks_params():
    """改大某 lookback 字段 → head_buffer 跟着动(推导而非手写常量)。"""
    p = replace(Params.default(), bo=replace(Params.default().bo, vol_baseline_period=200))
    assert eval_meta(p)["head_buffer_trading_days"] == 200
