"""new_step 端到端:合成 K 线走 analyze / has_hit(默认参数)。

正例:旧平台微小波动 → 两根放量大阳线 → 平稳新平台(每根都收阳、收在阶跃最高价之下)。
反例:同一走势,只把阶跃两根的成交量压回旧平台水平(阶跃不放量)。
"""
from dataclasses import replace

import pandas as pd

from path2.eval import _resolve_end_events
from path2_apps.new_step import analyze, eval_meta, has_hit
from path2_apps.new_step.params import Params
from path2_apps.new_step.plateau import PlateauEvent, Today

N = 60
STEP = (20, 21)          # 阶跃两根
NEW_FROM = 22            # 新平台首根


def _synth(step_vols=(5000.0, 8000.0)):
    """0..19 旧平台 10.0/10.05 交替(量 1000);20、21 两根大阳线 12.5、15.0(21 根最高 15.5);
    22..59 新平台 14.8/14.9 交替,开盘一律 14.75(根根收阳),量 2000。

    默认阈值下只有前缀 [20, 21] 过闸:单前缀 [20, 20] 累计涨幅约 24% < 40%(大涨幅不成立)。
    """
    closes = [10.0 if j % 2 == 0 else 10.05 for j in range(NEW_FROM - 2)] + [12.5, 15.0]
    closes += [14.8 if j % 2 == 0 else 14.9 for j in range(NEW_FROM, N)]
    opens = list(closes)
    for j in range(NEW_FROM, N):
        opens[j] = 14.75
    highs = [c + 0.1 for c in closes]
    highs[STEP[1]] = 15.5
    lows = [c - 0.1 for c in closes]
    vols = [1000.0] * (NEW_FROM - 2) + list(step_vols) + [2000.0] * (N - NEW_FROM)
    return pd.DataFrame({"open": opens, "high": highs, "low": lows, "close": closes, "volume": vols})


def test_has_hit_positive():
    assert has_hit(_synth()) is True


def test_each_hit_buys_on_a_single_bar_today():
    """每个 hit 的买点(eval_meta 的 end_node 解析出的 event)恰是一根:plateau 实例的当天。"""
    res = analyze(_synth())
    assert res.hits
    end_node = eval_meta()["end_node"]
    days = []
    for h in res.hits:
        plateau = h.node_index["plateau"]
        assert isinstance(plateau, PlateauEvent)
        (today,) = _resolve_end_events(h, end_node)
        assert isinstance(today, Today)
        assert today.node_id == "today"
        assert today.start_idx == today.end_idx == today.confirm_idx == plateau.end_idx
        assert (plateau.step.start_idx, plateau.step.end_idx) == STEP
        days.append(today.start_idx)
    # 阶跃后第一天(新平台首根)不产;之后到数据末尾每天一个 hit
    assert sorted(days) == list(range(STEP[1] + 2, N))


def test_no_volume_step_returns_false():
    """阶跃不放量(两根量 = 旧平台均量)→ 平台交界放量不成立 → 无 hit。"""
    assert has_hit(_synth(step_vols=(1000.0, 1000.0))) is False


def test_no_volume_step_hits_once_volume_gate_relaxed():
    """对照:同一不放量走势,只把放量下限放到 1 倍以下就命中——反例确实只卡在放量这一条。"""
    p = Params.default()
    p = replace(p, plateau=replace(p.plateau, step_vol_min=0.5))
    assert has_hit(_synth(step_vols=(1000.0, 1000.0)), p) is True


def test_flat_series_returns_false():
    """全程平稳、没有阶跃 → 无 hit。"""
    closes = [10.0 if j % 2 == 0 else 10.05 for j in range(N)]
    df = pd.DataFrame({"open": closes, "high": [c + 0.1 for c in closes],
                       "low": [c - 0.1 for c in closes], "close": closes, "volume": [1000.0] * N})
    assert has_hit(df) is False
