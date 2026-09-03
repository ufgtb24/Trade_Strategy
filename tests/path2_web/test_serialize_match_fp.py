"""serialize_per_pattern_result:match 级 buy_date + first_passage 四态。
不变式:非 None 的 first_passage 四态逐项求和 == match_fp_counts。"""
from pathlib import Path
import pandas as pd
import pytest

from path2_web.serialize import serialize_per_pattern_result
from path2_apps.bb_v1.dag_spec import build_pattern, eval_meta
from path2_apps.bb_v1.params import Params
from path2.dag.engine import analyze as engine_analyze

PKL_DIR = Path("datasets/pkls")


def _wide():
    d = Params.default().to_dict()
    d["burst"].update(first_drought_min=0, distinct_pk_min=1, vol_spike_min=0, peak_age_min=0)
    d["tb"]["max_day_drop_pct"] = None
    return Params.from_dict(d)


@pytest.fixture
def scene():
    if not PKL_DIR.exists():
        pytest.skip("datasets/pkls 缺失")
    p = _wide(); spec = build_pattern(p)
    for pk in sorted(PKL_DIR.glob("A*.pkl"))[:300]:
        df = pd.read_pickle(pk)
        if len(df) < 400:
            continue
        win = df.iloc[-600:].reset_index()
        res = engine_analyze(spec, win, p)
        if res.matches:
            return res, eval_meta(p), win, pd.to_datetime(win["date"].iat[0]), pd.to_datetime(win["date"].iat[-1])
    pytest.skip("无命中股")


def _run(scene, **kw):
    res, meta, win, s, e = scene
    return serialize_per_pattern_result(res, end_node=meta["end_node"], label_horizon=5,
                                        win=win, start_ts=s, end_ts=e, **kw)


def test_fields_present_and_sum_invariant(scene):
    out = _run(scene)
    ms = out["analysis"]["matches"]
    assert ms
    tot = {"up": 0, "down": 0, "both": 0, "none": 0}
    for m in ms:
        assert isinstance(m["buy_date"], str) and len(m["buy_date"]) == 10
        fp = m["first_passage"]
        assert fp is None or set(fp) == set(tot)
        if fp is not None:
            for k in tot:
                tot[k] += fp[k]
    assert tot == out["match_fp_counts"]
    assert any(m["first_passage"] is not None for m in ms)


def test_buy_date_is_end_node_start(scene):
    res, meta, win, *_ = scene
    out = _run(scene)
    by_id = {m.match_id: m for m in res.matches}
    for md in out["analysis"]["matches"]:
        ev = by_id[md["match_id"]].node_index[meta["end_node"].split(".")[0]]
        assert md["buy_date"] == str(pd.to_datetime(win["date"].iat[ev.start_idx]).date())


def test_disabled_first_passage_gives_none(scene):
    out = _run(scene, first_passage_enabled=False)
    assert all(m["first_passage"] is None for m in out["analysis"]["matches"])
    assert out["match_fp_counts"] == {"up": 0, "down": 0, "both": 0, "none": 0}
