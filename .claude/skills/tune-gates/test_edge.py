# -*- coding: utf-8 -*-
"""edge(优势检查)单测(tune-gates skill 自带;显式路径跑):
uv run pytest .claude/skills/tune-gates/test_edge.py -q -p no:cacheprovider
合成 app(本文件即 app 模块)、合成 pkl、合成交易日历、临时账本目录;不读真实数据目录。
"""
import copy
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
REPO = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
sys.path.insert(0, str(REPO))

import edge as E  # noqa: E402
import holdout as H  # noqa: E402
import ledger as L  # noqa: E402
import multivar_scan as MS  # noqa: E402
from multivar_core import seg_id_of  # noqa: E402
from path2.core import Event  # noqa: E402
from path2.dag import where as Wh  # noqa: E402
from path2.dag.edges import TemporalEdge  # noqa: E402
from path2.dag.nodes import NodeSpec  # noqa: E402
from path2.dag.spec import PatternSpec  # noqa: E402
from path2_web.data import slice_window  # noqa: E402

CAL = pd.bdate_range("2021-08-20", "2026-08-17")
HB, HZ = 250, 40


# ---------------------------------------------------------------- 合成 app:A 点事件 → B 区间事件
@dataclass(frozen=True)
class SynPt(Event):
    pass


@dataclass(frozen=True)
class SynSeg(Event):
    length: int = 0
    depth: int = 0


def _anchors(n):
    return range(40, n - 60, 17)


class SynPtDet:
    event_cls = SynPt

    def __init__(self, width):
        self.width = width

    def detect(self, df):
        return iter([SynPt(p, p, confirm_idx=p) for p in _anchors(len(df))])


class SynSegDet:
    """A 之后 2 根起一段,段长 2 + p%5、深度 p%7;min_len 只在出口把关(过滤型)。"""
    event_cls = SynSeg
    filter_params = {"min_len": ("length", ">=")}

    def __init__(self, min_len):
        self.min_len = min_len

    def detect(self, df):
        out = []
        for p in _anchors(len(df)):
            n = 2 + p % 5
            if n >= self.min_len:
                out.append(SynSeg(p + 2, p + 1 + n, confirm_idx=p + 1 + n, length=n, depth=p % 7))
        return iter(out)


DEFAULTS = {"a": {"width": 1}, "b": {"min_len": 2, "depth_min": 3}}


class Params:
    def __init__(self, d):
        self.d = d

    @classmethod
    def from_dict(cls, d, strict=True):
        return cls(copy.deepcopy(d))

    @classmethod
    def from_yaml(cls, path):
        return cls(copy.deepcopy(DEFAULTS))

    def to_dict(self):
        return copy.deepcopy(self.d)


def build_pattern(p):
    d = p.d
    return PatternSpec(pattern_id="syn_edge",
                       nodes=(NodeSpec("A", detector=SynPtDet(d["a"]["width"])),
                              NodeSpec("B", detector=SynSegDet(d["b"]["min_len"]),
                                       where=(("depth", Wh.attr("depth", ">=", d["b"]["depth_min"])),))),
                       edges=(TemporalEdge("A", "B", min_gap=0, max_gap=5),))


def eval_meta(params=None):
    return {"end_node": "B", "head_buffer_trading_days": 0}


WIDE = {"b": {"min_len": 1, "depth_min": 0}}
APP = sys.modules[__name__]


@pytest.fixture(autouse=True)
def ledger_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("TUNE_LEDGER_DIR", str(tmp_path / "ledger"))
    monkeypatch.setattr(H, "default_calendar", lambda: CAL)


def _common(**kw):
    f = dict(actor="test", round="r1", window=None, label_horizon=None, head_buffer=None, git_head=None,
             base_fingerprint=None, source_fingerprint=None, ruler_fingerprint=None)
    f.update(kw)
    return f


def _open(app="syn"):
    w = H.confirm_windows("2024-01-01", "2025-12-31", calendar=CAL, head_buffer=HB, horizon=HZ)
    L.append(L.make_record("open", app, **_common(window={"start": "2024-01-01", "end": "2025-12-31"},
                                                  label_horizon=HZ, head_buffer=HB), data={**w, "n_probed": 400}))
    return w


# ---------------------------------------------------------------- 闸
def test_gate_specs_where_and_filter_gates():
    gates = E.gate_specs(APP, DEFAULTS, WIDE)
    assert gates == [
        {"param": "b.min_len", "kind": "F", "node": "B", "field": "length", "op": ">=", "production": 2, "wide": 1},
        {"param": "b.depth_min", "kind": "W", "node": "B", "field": "depth", "op": ">=", "production": 3, "wide": 0}]
    same = E.gate_specs(APP, DEFAULTS, {"b": {"depth_min": 3}})      # 正式值本来就是放开的:换相邻值试
    assert same[0]["kind"] == "W" and same[0]["field"] == "depth"


def test_gate_specs_rejects_non_gate_params():
    with pytest.raises(ValueError, match="不是闸"):
        E.gate_specs(APP, DEFAULTS, {"a": {"width": 5}})
    with pytest.raises(ValueError, match="不在正式参数里"):
        E.gate_specs(APP, DEFAULTS, {"b": {"nope": 1}})


# ---------------------------------------------------------------- 比较点
def test_points_dedup_and_working_rule():
    gates = [{"param": "b.depth_min", "kind": "W", "node": "B", "field": "depth", "op": ">=", "production": 3, "wide": 0},
             {"param": "b.cap", "kind": "W", "node": "B", "field": "cap", "op": "<", "production": None, "wide": None}]
    rows = [("S1", 1, 10, 1), ("S1", 1, 10, 5),        # 同一买点日两个前缀,一行过闸
            ("S1", 1, 11, 1), ("S1", 1, 11, 5),
            ("S1", 2, 20, 1), ("S1", 2, 20, 2),        # 两行都不过
            ("S2", 1, 10, None)]                        # 字段缺失算不过
    bars = pd.DataFrame(rows, columns=["symbol", "seg_id", "t", "B.depth"])
    bars["B.cap"] = 99.0
    pts = E.points(bars, gates)
    key = lambda df: sorted(map(tuple, df[["symbol", "seg_id", "t"]].values.tolist()))  # noqa: E731
    assert key(pts["wide"]) == [("S1", 1, 10), ("S1", 1, 11), ("S1", 2, 20), ("S2", 1, 10)]
    assert key(pts["working"]) == [("S1", 1, 10), ("S1", 1, 11)]


# ---------------------------------------------------------------- 守卫
def test_scan_refused_on_confirm_window(tmp_path, monkeypatch):
    monkeypatch.setattr(E, "REPO", tmp_path)
    cfg = SimpleNamespace(start_date="2024-01-01", end_date="2025-12-31")
    with pytest.raises(H.HoldoutLocked) as e:
        E.scan("syn", cfg, wide_overrides=WIDE)
    assert e.value.reason == "no_open"
    w = _open()
    fw = w["confirm"]["forward"]
    with pytest.raises(H.HoldoutLocked) as e:
        E.scan("syn", SimpleNamespace(start_date=fw["start"], end_date=fw["end"]), wide_overrides=WIDE)
    assert e.value.reason == "confirm_overlap"
    assert not (tmp_path / "outputs").exists()


# ---------------------------------------------------------------- 扫描(合成 pkl)
def _write_pkls(d: Path):
    d.mkdir()
    rng = np.random.default_rng(5)
    n = len(CAL)
    for sym, level, vol in (("AAA", 10, 1e6), ("BBB", 20, 1e6), ("LOW", 10, 10.0), ("HIGH", 500, 1e6)):
        close = level * np.exp(np.cumsum(rng.normal(0, 0.02, n)))
        pd.DataFrame({"open": close, "high": close * (1 + rng.uniform(0, 0.03, n)),
                      "low": close * (1 - rng.uniform(0, 0.03, n)), "close": close, "volume": vol},
                     index=pd.DatetimeIndex(CAL, name="date")).to_pickle(d / f"{sym}.pkl")


def _scan_cfg(data):
    return SimpleNamespace(data_dir=str(data), start_date="2024-01-01", end_date="2025-12-31", head_buffer=30,
                           label_horizon=HZ, first_passage_k=1.0, price_min=0.5, price_max=100.0, volume_min=1000.0,
                           ticker_regex=None, shard_stocks=2, workers=2, screen_fdr_q=0.1)


def test_scan_writes_bars_and_baseline_and_resumes(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(E, "REPO", tmp_path)
    monkeypatch.setattr(E, "_app_module", lambda app: __name__)
    monkeypatch.setattr(E, "_fingerprints", lambda mod, spec, params: {
        "git_head": "abc1234", "base_fingerprint": "b", "source_fingerprint": "s", "ruler_fingerprint": "r"})
    _open()
    data = tmp_path / "pkls"
    _write_pkls(data)
    cfg = _scan_cfg(data)
    out = E.scan("syn", cfg, wide_overrides=WIDE)
    assert out == tmp_path / "outputs/tune_gates/syn/edge"
    meta = json.loads((out / "run_meta.json").read_text())
    assert meta["gates"] == E.gate_specs(APP, DEFAULTS, WIDE) and meta["wide_overrides"] == WIDE
    committed = MS.committed_shards(out)
    bars = pd.concat([pd.read_parquet(p) for p in sorted((out / "bars").glob("part-*.parquet")) if p.name in committed])
    base = pd.concat([pd.read_parquet(p) for p in sorted((out / "baseline").glob("part-*.parquet")) if p.name in committed])
    assert list(bars.columns) == E.BAR_COLS + ["B.length", "B.depth"]
    # 定范围读取的格式约定:run_meta 的放开值键名 wide_overrides、嵌套 {section: {field: 值}};闸字段列名 node.field
    assert json.loads((out / "run_meta.json").read_text())["wide_overrides"] == {"b": {"min_len": 1, "depth_min": 0}}
    assert list(bars.columns)[len(E.BAR_COLS):] == [f"{g['node']}.{g['field']}" for g in meta["gates"]]
    assert list(base.columns) == MS.BASELINE_COLS
    assert set(bars["symbol"].astype(str)) == {"AAA", "BBB"} and set(base["symbol"].astype(str)) == {"AAA", "BBB"}
    assert pd.read_csv(out / "filtered_symbols.csv", keep_default_na=False)["symbol"].tolist() == ["LOW"]
    assert pd.read_csv(out / "empty_symbols.csv", keep_default_na=False)["symbol"].tolist() == ["HIGH"]
    assert (bars[["up", "down", "both", "none"]].sum(axis=1) == 1).all() and (bars["M"] > 0).all()

    s, e, bs, be = MS._window_bounds(cfg.start_date, cfg.end_date, cfg.head_buffer, cfg.label_horizon)
    for sym in ("AAA", "BBB"):
        win = slice_window(pd.read_pickle(data / f"{sym}.pkl"), bs, be)
        lo, hi = int(win["date"].searchsorted(s, "left")), int(win["date"].searchsorted(e, "right")) - 1
        expected = []
        for p in _anchors(len(win)):
            n = 2 + p % 5
            st, en = p + 2, p + 1 + n
            if not (lo <= st <= hi and cfg.price_min <= win["close"].iat[st] <= cfg.price_max):
                continue
            expected += [(t, seg_id_of(((st, en),)), n, p % 7) for t in range(st, en + 1)
                         if lo <= t <= hi and t + HZ < len(win)]
        got = bars[bars["symbol"] == sym]
        assert sorted(zip(got["t"], got["seg_id"], got["B.length"], got["B.depth"])) == sorted(expected)
        assert (got["date"].to_numpy() == win["date"].to_numpy()[got["t"].to_numpy()]).all()

    capsys.readouterr()
    assert meta["ticker_regex"] is None
    E.scan("syn", cfg, wide_overrides=WIDE)                            # 断点续跑
    assert "股票 0 待扫" in capsys.readouterr().out
    assert MS.committed_shards(out) == committed
    E.scan("syn", SimpleNamespace(**{**vars(cfg), "ticker_regex": "^AAA"}), wide_overrides=WIDE)   # 换股票范围照常续跑
    assert json.loads((out / "run_meta.json").read_text())["ticker_regex"] == "^AAA"
    assert MS.committed_shards(out) == committed
    with pytest.raises(SystemExit, match="restart"):
        E.scan("syn", cfg, wide_overrides={"b": {"min_len": 1, "depth_min": 1}})


# ---------------------------------------------------------------- run(注入合成样本)
GATES = [{"param": "b.depth_min", "kind": "W", "node": "B", "field": "depth", "op": ">=", "production": 3, "wide": 0}]


def _fake_scan(tmp_path):
    def scan(app, cfg, *, wide_overrides, restart=False):
        out = tmp_path / "outputs/tune_gates" / app / "edge"
        for d in E.SHARD_DIRS:
            (out / d).mkdir(parents=True, exist_ok=True)
        (out / "run_meta.json").write_text(json.dumps({
            "app": app, "start_date": cfg.start_date, "end_date": cfg.end_date, "head_buffer": cfg.head_buffer,
            "label_horizon": cfg.label_horizon, "wide_overrides": wide_overrides, "gates": GATES,
            "git_head": "abc1234", "base_fingerprint": "b", "source_fingerprint": "s", "ruler_fingerprint": "r"}))
        rng = np.random.default_rng(11)
        dates = pd.bdate_range("2024-01-02", periods=60).append(pd.bdate_range("2025-01-02", periods=60))
        states = np.array(["up", "down", "both", "none"])

        def draw(p, size):
            s = rng.choice(4, size=size, p=p)
            return {x: (s == i).astype("int8") for i, x in enumerate(states)}

        nb = 150 * len(dates)
        base = pd.DataFrame({"symbol": np.repeat([f"B{i:03d}" for i in range(150)], len(dates)),
                             "date": np.tile(dates, 150), "M": rng.uniform(0.01, 0.05, nb), "c0_atr_pct": 0.02,
                             **draw([0.35, 0.35, 0.1, 0.2], nb)})
        rows = []
        for i in range(50):
            for j in range(8):
                good = j < 3                                               # 过闸的段少、表现好;不过闸的段多、表现差
                d0 = rng.integers(0, len(dates) - 3)
                st = draw([0.75, 0.1, 0.05, 0.1] if good else [0.05, 0.7, 0.05, 0.2], 3)
                for k in range(3):
                    for depth in ((1, 5) if good else (1, 2)):
                        rows.append({"symbol": f"P{i:03d}", "t": 100 + d0 + k, "date": dates[d0 + k],
                                     "M": rng.uniform(0.01, 0.05), "c0_atr_pct": 0.02,
                                     **{x: st[x][k] for x in states}, "seg_id": 1000 * i + j, "B.depth": depth})
        bars = pd.DataFrame(rows)
        MS.write_shard(out, 0, {"bars": bars[E.BAR_COLS + ["B.depth"]], "baseline": base[MS.BASELINE_COLS]})
        return out
    return scan


def test_run_writes_report_and_edge_record(tmp_path, monkeypatch):
    from test_tune import BANNED
    monkeypatch.setattr(E, "scan", _fake_scan(tmp_path))
    cfg = SimpleNamespace(start_date="2024-01-01", end_date="2025-12-31", head_buffer=30, label_horizon=HZ,
                          screen_fdr_q=0.1)
    r = E.run("syn", cfg, wide_overrides=WIDE, delta=0.02, m=10, B=60, seed=1)
    report = Path(r["report"])
    text = report.read_text(encoding="utf-8")
    assert not [w for w in BANNED if w in text]
    assert "同一天、同样波动水平的随机买入日" in text and "来自现在开着的闸" in text and "估计" in text
    for internal in ("seg_id", "edge_core", "resolution", "n_pl", "coverage", "回踩"):
        assert internal not in text

    rec = L.read("syn")[-1]
    L.validate_record(rec)
    assert rec == r["record"] and rec["kind"] == "edge" and rec["n_looks"] == 1
    assert rec["window"] == {"start": "2024-01-01", "end": "2025-12-31"} and rec["axes"] == ["b.depth_min"]
    assert rec["ref"] == {str(report.resolve()): L.sha256_file(report)}
    d = rec["data"]
    assert set(d["points"]) == {"wide", "working"} and set(d["points"]["working"]) == {"2024", "2025", "pooled"}
    assert d["verdicts"]["working"]["pooled"] == "有边际" == d["verdict"]
    assert d["verdicts"]["wide"]["pooled"] == "没有" and d["source_note"] == "优势来自在役闸"
    res = d["resolution"]
    assert res["r_bar_source"] == "标定先验" and res["m"] == 10 and res["deff"] > 0 and 0 < res["s_dec"] < 1
    assert d["delta"] == 0.02 and d["n_rows"] == {"wide": 50 * 8 * 3, "working": 50 * 3 * 3}
