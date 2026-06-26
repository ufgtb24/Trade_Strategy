import numpy as np
import pandas as pd

from path2_apps.bottom_breakout_burst import matches
from path2_apps.bottom_breakout_burst.params import Params, BoParams, BurstParams


def _synth_positive():
    """构造完整正例:
      - phase 1 (0-99):   高位下跌 150 → 75 (~50%)
      - phase 2 (100-219): 横盘,含三个小 peak
      - phase 2b (220-239): 低位平台(低于任意 peak),确保首 BO 在此后,drought ≥ 20
      - phase 3 (240-258): 连续单调小步 BO,小量(vol=1200),pct_gain 小
      - phase 3' (idx 259): 末 BO — vol=10000(20 日内最大),pct_change=+12%(最大),阳线
      - phase 4 (bo+1..): throwback — 回落≥1×ATR → 双根止跌 → 大涨≥1.5×ATR,low全程守anchor
      - phase 5: 续填上行至 ≥320 根
    """
    rng = np.random.default_rng(42)
    closes = []
    highs = []
    lows = []
    opens = []
    vols = []

    # phase 1: high-drop (200 → 75,~63% drop)。
    for i in range(100):
        c = 200.0 - (i / 100.0) * 125.0 + rng.normal(0, 0.3)
        opens.append(c + rng.normal(0, 0.1))
        closes.append(c)
        highs.append(c * 1.01)
        lows.append(c * 0.99)
        vols.append(1000.0 + rng.normal(0, 50))

    # phase 2: sideways with peaks at 120, 150, 180
    for i in range(100, 220):
        base = 75.0 + 0.4 * np.sin((i - 100) * 0.2) + rng.normal(0, 0.2)
        if i in (120, 150, 180):
            base += 2.0  # peak
        opens.append(base - 0.2)
        closes.append(base)
        highs.append(base * 1.01)
        lows.append(base * 0.99)
        vols.append(1000.0 + rng.normal(0, 50))

    # phase 2b: low flat zone (220-239) — 价格低于所有 peak,确保 phase3 首 BO drought ≥ 20
    for i in range(220, 240):
        base = 74.5 + rng.normal(0, 0.1)
        opens.append(base - 0.1)
        closes.append(base)
        highs.append(base + 0.2)
        lows.append(base - 0.2)
        vols.append(900.0)

    # phase 3 (240-258): 单调小步 BO,pct_gain ≈ 0.25%/bar,vol=1200(20 日内最大约 1200)
    base3 = 75.0
    for i in range(240, 259):
        base3 += 0.20
        opens.append(base3 - 0.05)
        closes.append(base3)
        highs.append(base3 + 0.5)  # 制造可突破的 peak
        lows.append(base3 - 0.2)
        vols.append(1200.0)

    # phase 3' (idx 259): 末 BO — 阳线放量(vol=10000 >> 1200,pct_change=+12%)
    # close[258] ≈ 78.8; anchor = high[258] ≈ 79.3
    prev_c = closes[-1]  # close[258] ≈ 78.8
    bo_close = prev_c * 1.12          # +12% 阳线
    opens.append(prev_c)
    closes.append(bo_close)
    highs.append(bo_close * 1.02)     # bo 峰(惯性高点)
    lows.append(prev_c * 0.999)
    vols.append(10000.0)

    # phase 4: 回落 → 双根止跌 → 大涨(纯走势,low 全程守 anchor)
    # ATR(14)@259≈1.46(bo 根 +12% 的大 TR 抬高 Wilder ATR);anchor=high[258]=79.3(精确,phase3 high=close+0.5)
    anchor = prev_c + 0.5             # ≈ high[258]
    # 3 根回落段(low 守 anchor;回落门 peak−low[trough] 中 peak 由 bo 根 high≈90 主导,实测回落≈9.7≈6.7×ATR,远超 1×ATR 门)
    for lo, c in [(anchor + 3.0, anchor + 3.5),   # 回落起
                  (anchor + 1.5, anchor + 2.0),   # 续跌
                  (anchor + 1.0, anchor + 1.6)]:   # trough 附近(low≈anchor+1)
        opens.append(c + 0.3)         # 阴/小实体
        closes.append(c)
        highs.append(c + 0.5)
        lows.append(lo)
        vols.append(3000.0)
    # 2 根不创新低 + 止跌证据(bullish+close_up → c>o 且 c>prev_c)
    base_trough = closes[-1]
    for c in [base_trough + 0.8, base_trough + 1.6]:
        opens.append(c - 0.6)         # 阳线(c>o → bullish + close_up)
        closes.append(c)
        highs.append(c + 0.4)
        lows.append(anchor + 1.2)     # 守 anchor 且 ≥ trough(不创新低)
        vols.append(3000.0)
    # 大涨根:high − base_min ≥ big_rise_k(1.5)×ATR → 触发大涨,end 取前一根
    big_c = closes[-1] + 6.0
    opens.append(closes[-1])
    closes.append(big_c)
    highs.append(big_c + 1.0)
    lows.append(anchor + 2.0)         # 守 anchor
    vols.append(5000.0)

    # phase 5: 从当前长度续填到 ≥320(上行根)
    while len(closes) < 320:
        pc = closes[-1]
        c = pc + 0.2 + rng.normal(0, 0.1)
        opens.append(c - 0.1)
        closes.append(c)
        highs.append(c * 1.01)
        lows.append(c * 0.99)
        vols.append(1000.0)

    return pd.DataFrame({
        'open': opens,
        'high': highs,
        'low': lows,
        'close': closes,
        'volume': vols,
    })


def _synth_no_burst():
    """阴性:无连续突破段(全程 sideways,无 BO)"""
    rng = np.random.default_rng(0)
    n = 250
    closes = [10.0 + 0.02 * np.sin(i * 0.3) + rng.normal(0, 0.03) for i in range(n)]
    return pd.DataFrame({
        'open': closes,
        'high': [c + 0.05 for c in closes],
        'low': [c - 0.05 for c in closes],
        'close': closes,
        'volume': [1000.0] * n,
    })


def test_matches_positive():
    df = _synth_positive()
    p = Params.default()
    # 此 fixture 使用较低阈值便于稳定命中
    p_relaxed = Params(
        bo=BoParams(
            min_relative_height=0.02,
            peak_measure="body_top", breakout_measure="body_top",   # fixture 按 body_top 调校;high 默认由全宇宙 gate 覆盖
        ),
        burst=BurstParams(min_bos=2, first_drought_min=20, distinct_pk_min=2, vol_spike_min=3.0),
    )
    assert matches(df, p_relaxed) is True


def test_matches_no_burst_returns_false():
    df = _synth_no_burst()
    assert matches(df) is False


def test_matches_no_sideways_returns_false():
    # 全程上涨 (无 sideways 段) → ① 不命中
    rng = np.random.default_rng(7)
    n = 250
    closes = list(np.linspace(10.0, 20.0, n) + rng.normal(0, 0.05, n))
    df = pd.DataFrame({
        'open': closes,
        'high': [c + 0.1 for c in closes],
        'low': [c - 0.1 for c in closes],
        'close': closes,
        'volume': [1000.0] * n,
    })
    assert matches(df) is False


def _synth_no_drought():
    """阴性(I1):首 BO drought 不够大 → 谓词 ③ 不命中。

    与 _synth_positive 相同结构,但 phase 1 缩短 + phase 2 缩短,使首 BO
    的 drought(距上次 BO 间隔)不够 THR_DROUGHT。最简策略:在 phase 2
    前段制造一个 BO,然后 burst 紧随其后(drought 小)。
    """
    rng = np.random.default_rng(43)
    closes = []
    highs = []
    lows = []
    opens = []
    vols = []

    # phase 1 短:仅 20 bar
    for i in range(20):
        c = 12.0 - (i / 20.0) * 1.5 + rng.normal(0, 0.05)
        opens.append(c - 0.02)
        closes.append(c)
        highs.append(c + 0.1)
        lows.append(c - 0.1)
        vols.append(1000.0)

    # 早期 BO(idx ~ 30):制造 peak 然后突破(让 _last_bo_idx 被设置)
    for i in range(20, 35):
        if i == 25:
            c = 11.3  # peak
        elif i == 31:
            c = 11.7  # 早突破
        else:
            c = 10.5 + rng.normal(0, 0.05)
        opens.append(c - 0.02)
        closes.append(c)
        highs.append(c + 0.1)
        lows.append(c - 0.1)
        vols.append(1000.0)

    # 紧随其后的 burst(drought 仅 ~10 bar,远小于 THR_DROUGHT=60)
    sideways_start = 35
    for i in range(sideways_start, 50):
        base = 10.5 + 0.05 * np.sin((i - sideways_start) * 0.2) + rng.normal(0, 0.03)
        if i in (38, 42):
            base += 0.25  # 小 peak
        opens.append(base - 0.02)
        closes.append(base)
        highs.append(base + 0.1)
        lows.append(base - 0.1)
        vols.append(1000.0)

    # 紧接 burst
    for i, target in zip(range(50, 70),
                         [10.9, 11.0, 11.1, 10.9, 11.0, 11.2, 11.1, 11.0, 11.3, 11.2,
                          11.4, 11.3, 11.5, 11.4, 11.3, 11.6, 11.5, 11.4, 11.7, 11.6]):
        opens.append(target - 0.05)
        closes.append(target)
        highs.append(target + 0.15)
        lows.append(target - 0.1)
        vols.append(4500.0 if i in (51, 58, 65) else 1200.0)

    # 平台填补长度
    for i in range(70, 250):
        c = 11.7 + rng.normal(0, 0.05)
        opens.append(c - 0.02)
        closes.append(c)
        highs.append(c + 0.05)
        lows.append(c - 0.05)
        vols.append(1000.0)

    return pd.DataFrame({
        'open': opens,
        'high': highs,
        'low': lows,
        'close': closes,
        'volume': vols,
    })


def _synth_no_throwback():
    """阴性:末 BO 后 low 跌破 anchor → evaluate_throwback 返回 None → 不产 tb 事件 → False。

    复用 _synth_positive 主体,但将 idx 260 的 low/close 改到 anchor 以下。
    anchor = high[258] ≈ 79.3;将 low[260] = 74.0(明确跌破)。
    """
    df = _synth_positive()
    df_copy = df.copy()
    # anchor = high[258] ≈ 79.3;idx 260 的 low 改到 74 → low 跌破 anchor → evaluate_throwback 返回 None
    df_copy.loc[260, 'low'] = 74.0
    df_copy.loc[260, 'close'] = 75.0
    df_copy.loc[260, 'open'] = 76.0
    return df_copy


def test_matches_no_drought_returns_false():
    df = _synth_no_drought()
    # 用与正例同的宽松阈值(便于 burst 命中),drought 谓词应单独筛掉
    p = Params(
        bo=BoParams(
            min_relative_height=0.02,
            peak_measure="body_top", breakout_measure="body_top",
        ),
        burst=BurstParams(min_bos=2, first_drought_min=60, distinct_pk_min=2, vol_spike_min=3.0),
        # first_drought_min=60:fixture 的首 BO drought 远小于此 → 谓词 ③ 不命中
    )
    assert matches(df, p) is False


def test_matches_no_throwback_returns_false():
    """末 BO 后 low 跌破 anchor → evaluate_throwback 返回 None → 不产 tb 事件 → matches False。"""
    df = _synth_no_throwback()
    p = Params(
        bo=BoParams(
            min_relative_height=0.02,
            peak_measure="body_top", breakout_measure="body_top",
        ),
        burst=BurstParams(min_bos=2, first_drought_min=20, distinct_pk_min=2, vol_spike_min=3.0),
    )
    assert matches(df, p) is False


def test_matches_no_prior_down_returns_false():
    """fixture 满足 ①②③⑤⑥⑦ 但 first_bo 前 lookback_bars 内无 down 段 → False"""
    df = _synth_no_prior_down()
    p = Params(
        burst=BurstParams(min_bos=3, first_drought_min=20, distinct_pk_min=2, vol_spike_min=1.5),
    )
    assert matches(df, p) is False


def test_matches_shallow_prior_down_returns_false():
    """前置 down 存在但 drawdown < 0.25(浅回调) → False"""
    df = _synth_shallow_prior_down()
    p = Params(
        burst=BurstParams(min_bos=3, first_drought_min=20, distinct_pk_min=2, vol_spike_min=1.5),
    )
    assert matches(df, p) is False


def _synth_no_prior_down():
    """构造:长期上涨 → 高位横盘 → 突破。无 down 段。"""
    import numpy as np
    import pandas as pd
    n = 300
    dates = pd.date_range("2024-01-01", periods=n)
    up = np.linspace(50, 100, 150)
    flat = 100 + np.random.RandomState(0).uniform(-1, 1, 130)
    breakout = np.linspace(100, 110, 20)
    closes = pd.Series(np.concatenate([up, flat, breakout]), index=dates)
    df = pd.DataFrame({
        'open': closes,
        'high': closes * 1.005,
        'low': closes * 0.995,
        'close': closes,
        'volume': pd.Series([1e6] * n, index=dates),
    })
    return df


def _synth_shallow_prior_down():
    """构造:浅回调(drawdown ~ 10%)→ 横盘 → 突破。回调不足 25%。"""
    import numpy as np
    import pandas as pd
    n = 300
    dates = pd.date_range("2024-01-01", periods=n)
    up = np.linspace(80, 100, 80)
    shallow_down = np.linspace(100, 90, 50)
    flat = 90 + np.random.RandomState(0).uniform(-1, 1, 150)
    breakout = np.linspace(90, 100, 20)
    closes = pd.Series(np.concatenate([up, shallow_down, flat, breakout]), index=dates)
    df = pd.DataFrame({
        'open': closes,
        'high': closes * 1.005,
        'low': closes * 0.995,
        'close': closes,
        'volume': pd.Series([1e6] * n, index=dates),
    })
    return df


# ---------------------------------------------------------------------------
# last_bo 自身 throwback 失败 → False
# ---------------------------------------------------------------------------

def test_matches_broken_throwback_returns_false():
    """末 BO 自身 post-bo low 跌破 anchor → evaluate_throwback 返回 None → 不产 tb 事件 → matches False。"""
    df = _synth_no_throwback()
    p = Params(
        bo=BoParams(
            min_relative_height=0.02,
            peak_measure="body_top", breakout_measure="body_top",
        ),
        burst=BurstParams(min_bos=2, first_drought_min=20, distinct_pk_min=2, vol_spike_min=3.0),
    )
    assert matches(df, p) is False
