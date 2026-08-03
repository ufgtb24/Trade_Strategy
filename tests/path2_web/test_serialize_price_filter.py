"""serialize_per_pattern_result 的 match 级价格过滤(锚 end_node 事件日收盘价)。

语义:end_node 是 eval_meta 声明的「事件成立那一刻」,也是 forward_return 的锚点;
价格过滤与既有窗口过滤共用同一个 ev.start_idx,不引入新锚点。判定是闭区间
(buy_close >= price_min and <= price_max),照搬 dev BreakoutStrategy/analysis/scanner.py:262-263。

用真实 pkl(同 tests/path2_web/test_serialize_multi.py 惯例),无数据时 skip。断言走
「复算 buy_close」自检:先按同一锚点复算出全部窗内 match 的收盘价,再用它构造边界,
不写死幻数。
"""
from pathlib import Path

import pandas as pd
import pytest

from path2_web.serialize import serialize_per_pattern_result
from path2_apps.bottom_breakout_burst import build_pattern, Params, eval_meta
from path2.dag.engine import analyze as engine_analyze

PKL_DIR = Path("datasets/pkls")


def _pick_pkl_with_match():
    """从 datasets/pkls 找一只 bbb 默认参数下能命中的股(无则 None → skip)。"""
    if not PKL_DIR.exists():
        return None
    spec = build_pattern(Params.default())
    for p in sorted(PKL_DIR.glob("*.pkl"))[:200]:      # 限制扫描数避免慢
        df = pd.read_pickle(p)
        if len(df) < 200:
            continue
        win = df.iloc[-300:].reset_index()
        res = engine_analyze(spec, win, Params.default())
        if len(res.matches) > 0:
            return p
    return None


@pytest.fixture
def scene():
    """(res, meta, win, start_ts, end_ts, buy_closes):buy_closes 是按与被测函数
    同一锚点复算出的窗内 match 收盘价列表。"""
    p = _pick_pkl_with_match()
    if p is None:
        pytest.skip("datasets/pkls 里没有能命中的股;skip")
    df = pd.read_pickle(p)
    spec = build_pattern(Params.default())
    win = df.iloc[-300:].reset_index()
    res = engine_analyze(spec, win, Params.default())
    meta = eval_meta()
    start_ts = pd.to_datetime(win["date"].iat[0])
    end_ts = pd.to_datetime(win["date"].iat[-1])
    closes = []
    for m in res.matches:
        ev = m.node_index[meta["end_node"]]
        d = pd.to_datetime(win["date"].iat[ev.start_idx])
        if start_ts <= d <= end_ts:
            closes.append(float(win["close"].iat[ev.start_idx]))
    return res, meta, win, start_ts, end_ts, closes


def _run(scene, **kw):
    res, meta, win, start_ts, end_ts, _ = scene
    return serialize_per_pattern_result(res, end_node=meta["end_node"], label_horizon=5,
                                        win=win, start_ts=start_ts, end_ts=end_ts, **kw)


def test_no_price_filter_is_unchanged(scene):
    """两个参数都不传 → 与今天逐字相同(零回归面守卫)。"""
    *_, closes = scene
    out = _run(scene)
    assert len(out["analysis"]["matches"]) == len(closes)
    assert out["summary"]["matches"] == len(closes)


def test_price_min_above_all_drops_everything(scene):
    *_, closes = scene
    out = _run(scene, price_min=max(closes) + 1.0)
    assert out["analysis"]["matches"] == []
    assert out["summary"]["matches"] == 0
    assert out["max_forward_return"] is None


def test_price_max_below_all_drops_everything(scene):
    *_, closes = scene
    out = _run(scene, price_max=min(closes) - 1.0)
    assert out["analysis"]["matches"] == []
    assert out["summary"]["matches"] == 0


def test_boundary_is_inclusive(scene):
    """闭区间:恰好等于边界的 match 必须保留(dev scanner.py:262-263 用的是 >= / <=,
    若实现写成开区间这里会掉到 0)。"""
    *_, closes = scene
    lo = min(closes)
    out = _run(scene, price_min=lo, price_max=lo)
    kept = len(out["analysis"]["matches"])
    assert kept == sum(1 for c in closes if c == lo)
    assert kept >= 1
