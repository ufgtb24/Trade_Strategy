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


def test_no_volume_step_hits_once_volume_gates_relaxed():
    """对照:同一不放量走势,把放量下限放到 1 倍以下、新平台缩量上限放到 2 倍以上就命中——反例只卡在
    量上:阶跃不放量,新平台(量 2000)相对阶跃(量 1000)也就谈不上缩量。只放开放量一条仍不命中。"""
    p = Params.default()
    only_vol = replace(p, plateau=replace(p.plateau, step_vol_min=0.5))
    assert has_hit(_synth(step_vols=(1000.0, 1000.0)), only_vol) is False
    both = replace(p, plateau=replace(p.plateau, step_vol_min=0.5, shrink_max=3.0))
    assert has_hit(_synth(step_vols=(1000.0, 1000.0)), both) is True


def test_flat_series_returns_false():
    """全程平稳、没有阶跃 → 无 hit。"""
    closes = [10.0 if j % 2 == 0 else 10.05 for j in range(N)]
    df = pd.DataFrame({"open": closes, "high": [c + 0.1 for c in closes],
                       "low": [c - 0.1 for c in closes], "close": closes, "volume": [1000.0] * N})
    assert has_hit(df) is False


# ── 新加的四条:卡在它上面就不买,放开就买 ──

def _buy_days(df, params=None):
    res = analyze(df, params) if params is not None else analyze(df)
    return sorted({h.node_index["plateau"].today.start_idx for h in res.hits})


def _relaxed(**kw):
    p = Params.default()
    return replace(p, plateau=replace(p.plateau, **kw))


def test_overhead_prior_high_blocks_until_relaxed():
    """阶跃前第 5 根上影线冲到 30(收盘不动):往前 60 根内上方压着前高,一天都不买;放开就买。"""
    df = _synth()
    df.loc[5, "high"] = 30.0
    assert has_hit(df) is False
    assert has_hit(df, _relaxed(overhead_max=10.0)) is True


def test_new_platform_volume_not_shrinking_blocks_until_relaxed():
    """新平台的量(7000)比阶跃平均量(6500)还大,不缩量,不买;放开缩量上限就买。"""
    df = _synth()
    df.loc[NEW_FROM:, "volume"] = 7000.0
    assert has_hit(df) is False
    assert has_hit(df, _relaxed(shrink_max=2.0)) is True


def test_new_low_today_not_settled_next_day_buys():
    """新平台第 30 根收在 14.5(严格新低,收阳):当天不买,第二天站回来照样买;放开企稳就当天也买。"""
    df = _synth()
    df.loc[30, ["open", "close", "low"]] = [14.4, 14.5, 14.3]
    days = _buy_days(df)
    assert 30 not in days and 31 in days
    assert 30 in _buy_days(df, _relaxed(settle_bars=0))


def _big_step_synth():
    """阶跃两根把价位从 10 拉到 45(累计涨 3.48 倍,算特别猛);新平台 44.4 / 44.7 交替、根根收阳。"""
    closes = [10.0 if j % 2 == 0 else 10.05 for j in range(NEW_FROM - 2)] + [25.0, 45.0]
    closes += [44.4 if j % 2 == 0 else 44.7 for j in range(NEW_FROM, N)]
    opens = list(closes)
    for j in range(NEW_FROM, N):
        opens[j] = 44.3
    highs = [c + 0.1 for c in closes]
    highs[STEP[1]] = 46.0
    vols = [1000.0] * (NEW_FROM - 2) + [5000.0, 8000.0] + [2000.0] * (N - NEW_FROM)
    return pd.DataFrame({"open": opens, "high": highs, "low": [c - 0.1 for c in closes],
                         "close": closes, "volume": vols})


def _big_prefix_days(params=None):
    """前缀 [20, 21](累计涨 3.48 倍)那一族的买点日。前缀 [20, 20] 只涨 1.49 倍,不算特别猛,不看它。"""
    res = analyze(_big_step_synth(), params) if params is not None else analyze(_big_step_synth())
    return sorted({h.node_index["plateau"].today.start_idx for h in res.hits
                   if (h.node_index["plateau"].step.start_idx, h.node_index["plateau"].step.end_idx) == STEP})


def test_big_step_waits_before_buying():
    """阶跃特别猛:阶跃后头几天不买,站够 big_wait 天(days ≥ 5,即第 26 根起)照样买;放开等待就提前买。"""
    days = _big_prefix_days()
    assert days and min(days) == STEP[1] + 5
    assert min(_big_prefix_days(_relaxed(big_wait=2))) == STEP[1] + 2
