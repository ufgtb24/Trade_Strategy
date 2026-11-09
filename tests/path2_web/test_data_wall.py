"""数据墙:2026-01-01 起的行情一律不给用户看(path2_web/data.py 模块说明)。

- read_bars 是网页读行情的唯一入口:校验代码名、去 tz、按日期排序、截到训练段末日 TRAIN_END(代码常量);
- 按代码打开(/ohlc 不给区间)也只给到训练段末日;股票列表只列训练段副本里有的,2026 年才上市的不在、也打不开;
- 配置的目录误指到带 2026 年行情的数据,K 线、网页扫描的 worker 也读不到 2026 年的 bar;
- 单股预览与扫描的区间终点截到 TRAIN_END,起点晚于它 → 400;
- 网页扫描(cap_at_train_end=True)落盘 data_until;研究脚本照旧读完整行情、不带 data_until;
  没有它(或晚于 TRAIN_END)的扫描打不开(409),列表里不给成绩;
- 反馈状态接口跑 app 读到、切出的 K 线不晚于 TRAIN_END;自上次以来的变化接口不读行情。
"""
from __future__ import annotations

import json
import re
import threading
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from path2_web import data as data_mod
from path2_web import scan as scan_mod
from path2_web.app import create_app
from tests.path2_web.conftest import data_cfg

TRAIN_END = "2025-12-31"


def _write_pkl(ddir, symbol: str, start="2025-06-02", end="2026-03-31", tz=None, shuffle=False) -> pd.DataFrame:
    """写一只跨过 2025-12-31 的合成股票(工作日,价格缓慢上行),index 名 date,与真实 pkl 同形。"""
    idx = pd.bdate_range(start, end, name="date", tz=tz)
    n = len(idx)
    close = 10 + np.arange(n) * 0.01
    df = pd.DataFrame({"open": close, "high": close + 0.2, "low": close - 0.2, "close": close,
                       "volume": np.full(n, 1e6)}, index=idx)
    if shuffle:
        df = df.sample(frac=1.0, random_state=0)
    df.to_pickle(ddir / f"{symbol}.pkl")
    return df


@pytest.fixture
def full_dir(tmp_path):
    d = tmp_path / "pkls"
    d.mkdir()
    _write_pkl(d, "AAA")
    return d


def _client(tmp_path, ddir) -> TestClient:
    cfg = {**data_cfg(ddir),
           "scan": {"start_date": "2025-06-02", "end_date": "2025-12-31", "workers": 1, "ticker_regex": None},
           "last_selected_pattern": "bo_only"}
    return TestClient(create_app(config_override=cfg, outputs_root=str(tmp_path / "outputs"),
                                 use_thread_pool=True))


def test_train_end_is_code_constant():
    assert data_mod.TRAIN_END == TRAIN_END


def test_read_bars_caps_sorts_and_strips_tz(tmp_path):
    _write_pkl(tmp_path, "TZ", tz="UTC", shuffle=True)
    df = data_mod.read_bars(tmp_path, "TZ")
    assert df.index.tz is None
    assert df.index.is_monotonic_increasing
    assert df.index.max() <= pd.Timestamp(TRAIN_END)
    assert df.index.min() == pd.Timestamp("2025-06-02")          # 更早的行情(探测器预热)照常在内


@pytest.mark.parametrize("bad", ["../AAA", "a/b", "..", "", " AAA", "AA A", ".hidden", "A..B", "X" * 16, None])
def test_read_bars_rejects_bad_symbol(tmp_path, bad):
    with pytest.raises(ValueError):
        data_mod.read_bars(tmp_path, bad)


def test_read_bars_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        data_mod.read_bars(tmp_path, "NOPE")


def test_ohlc_never_returns_2026_bars(tmp_path, full_dir):
    """配置的目录里的 pkl 带 2026 年行情:/ohlc 请求到 2026-03 也只给到 2025-12-31。"""
    c = _client(tmp_path, full_dir)
    r = c.get("/ohlc", params={"symbol": "AAA", "start": "2025-12-01", "end": "2026-03-31"})
    assert r.status_code == 200, r.text
    dates = [b["date"] for b in r.json()["bars"]]
    assert dates and max(dates) == TRAIN_END
    r = c.get("/ohlc", params={"symbol": "AAA", "start": "2026-01-02", "end": "2026-03-31"})
    assert r.status_code == 200 and r.json()["bars"] == []


def test_open_by_symbol_draws_until_train_end(tmp_path, full_dir):
    """spec 1.8「按代码打开任何一只股票 → 图最晚画到 2025-12-31」:/ohlc 不给区间时,
    行情跨过 2025-12-31 的股票也只给到训练段末日。"""
    r = _client(tmp_path, full_dir).get("/ohlc", params={"symbol": "AAA"})
    assert r.status_code == 200, r.text
    dates = [b["date"] for b in r.json()["bars"]]
    assert dates[0] == "2025-06-02" and dates[-1] == TRAIN_END


def test_listed_in_2026_not_in_list_and_not_openable(tmp_path):
    """spec 1.8「2026 年才上市的股票 → 不出现在股票列表里,按代码也打不开」:训练段副本生成时跳过截完为空的
    股票,所以副本里没有它;列表只列副本里的 pkl,按代码打开回 404。"""
    snap = tmp_path / "snap"
    snap.mkdir()
    _write_pkl(snap, "AAA", end=TRAIN_END)               # 副本:截到训练段末日
    (snap / "FINGERPRINT.json").write_text("{}")
    c = _client(tmp_path, snap)
    listed = c.get("/symbols").json()
    assert listed == ["AAA"]
    assert c.get("/ohlc", params={"symbol": "NEW26"}).status_code == 404


def test_listed_in_2026_not_openable_even_if_dir_misconfigured(tmp_path, full_dir):
    """配置的目录误指到完整行情(里面有 2026 年才上市的股票):按代码打开它照样 404,不给空图。"""
    _write_pkl(full_dir, "NEW26", start="2026-01-05")
    r = _client(tmp_path, full_dir).get("/ohlc", params={"symbol": "NEW26"})
    assert r.status_code == 404


def test_symbols_route_returns_codes_only(tmp_path, full_dir):
    """/symbols 只回代码,不带任何日期或 K 线(目录里的行情跨过 2025-12-31 也一样)。"""
    r = _client(tmp_path, full_dir).get("/symbols")
    assert r.status_code == 200 and r.json() == ["AAA"]


def test_ohlc_symbol_and_date_checks(tmp_path, full_dir):
    c = _client(tmp_path, full_dir)
    assert c.get("/ohlc", params={"symbol": "../pkls/AAA", "start": "2025-12-01", "end": "2025-12-31"}).status_code == 400
    assert c.get("/ohlc", params={"symbol": "NOPE", "start": "2025-12-01", "end": "2025-12-31"}).status_code == 404
    assert c.get("/ohlc", params={"symbol": "AAA", "start": "2025/12/01", "end": "2025-12-31"}).status_code == 400


def test_missing_data_dir_is_503(tmp_path):
    c = _client(tmp_path, tmp_path / "no_such_dir")
    r = c.get("/ohlc", params={"symbol": "AAA", "start": "2025-12-01", "end": "2025-12-31"})
    assert r.status_code == 503


def test_preview_end_clamped_and_start_after_train_end_400(tmp_path, full_dir):
    c = _client(tmp_path, full_dir)
    r = c.get("/preview", params={"pattern_id": "bo_only", "symbol": "AAA", "start": "2025-10-01",
                                  "end": "2026-03-31", "label_horizon": 20})
    assert r.status_code == 200, r.text
    assert r.json()["scan"]["end_date"] == TRAIN_END
    r = c.get("/preview", params={"pattern_id": "bo_only", "symbol": "AAA", "start": "2026-01-05",
                                  "end": "2026-03-31", "label_horizon": 20})
    assert r.status_code == 400


def _write_oscillating_pkl(ddir, symbol: str) -> pd.DataFrame:
    """一只来回波动、2026 年 1 月起放量大涨的合成股票(2024-06 ~ 2026-03):用完整行情跑 bo_only,
    2026 年有 bo、pk;截到 2025-12-31 跑就没有。"""
    idx = pd.bdate_range("2024-06-03", "2026-03-31", name="date")
    n = len(idx)
    close = 10 + 1.5 * np.sin(np.arange(n) / 9.0) + np.random.default_rng(0).normal(0, 0.15, n)
    late = idx >= pd.Timestamp("2026-01-05")
    close[late] += np.linspace(0, 8, late.sum())
    vol = np.where(late, 4e6, 1e6)
    df = pd.DataFrame({"open": close, "high": close + 0.3, "low": close - 0.3, "close": close,
                       "volume": vol}, index=idx)
    df.to_pickle(ddir / f"{symbol}.pkl")
    return df


def test_app_run_for_compare_stops_at_train_end(tmp_path, full_dir):
    """`app` / `compare` 模式跑 app 的那一次 /preview(区间:这只股票的全部 K 线,前端起点给 1900-01-01、
    终点给训练段末日;见 path2_web_ui/src/stores/appLink.ts):app 的全部输出都落在截到 2025-12-31 的
    K 线里。

    - 配置的目录误指到带 2026 年行情的数据,2026 年的大涨在完整行情里会出 bo、pk(对照组证明这组数据测得出泄漏);
    - 输出的事件、hit 与按代码打开的 K 线(/ohlc 不给区间)逐根对齐:和直接拿截断的 K 线跑 app 得到的完全一样,
      每个下标都在那些 K 线里,hit 的买点日不晚于训练段末日;
    - 回给前端的区间终点(scan.end_date、scan.win_end)也不晚于训练段末日。"""
    import path2_apps.bo_only.dag_spec as bo_only
    from path2_web.serialize import serialize_analysis

    full = _write_oscillating_pkl(full_dir, "BBB")
    c = _client(tmp_path, full_dir)
    bars = c.get("/ohlc", params={"symbol": "BBB"}).json()["bars"]
    assert bars[-1]["date"] == TRAIN_END
    n = len(bars)

    r = c.get("/preview", params={"pattern_id": "bo_only", "symbol": "BBB", "start": "1900-01-01",
                                  "end": TRAIN_END, "label_horizon": 20})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["scan"]["end_date"] == TRAIN_END and body["scan"]["win_end"] <= TRAIN_END

    events, hits = body["analysis"]["events"], body["analysis"]["hits"]
    assert events and hits
    for d in events + hits:
        idx = [v for k, v in d.items() if k.endswith("_idx") and isinstance(v, int)]
        assert idx and max(idx) < n, d
    for m in hits:
        assert all(e < n for _, e in m["buy_span"]) and m["buy_date"] <= TRAIN_END

    capped = full.loc[:TRAIN_END].reset_index()
    direct = serialize_analysis(bo_only.analyze(capped, bo_only.load_params()))["events"]
    key = lambda e: (e["instance_id"], e["start_idx"], e["end_idx"])
    assert sorted(map(key, events)) == sorted(map(key, direct))

    # 对照:拿完整行情跑,2026 年有事件(下标越过截断的 K 线)
    leaked = bo_only.analyze(full.reset_index(), bo_only.load_params())
    assert any(e.end_idx >= n for e in leaked.events)


def test_post_scan_clamps_end_and_reads_configured_dir(tmp_path, full_dir, monkeypatch):
    """POST /scan:区间终点截到训练段末日,读配置的目录;起点晚于训练段末日 → 400。"""
    got: dict = {}
    done = threading.Event()

    def fake_run(**kw):
        got.update(kw)
        done.set()
        return {"scan": {"hit_stocks": 0, "errors": 0, "scanned": 0}}
    monkeypatch.setattr(scan_mod, "run_scan_multi", fake_run)
    c = _client(tmp_path, full_dir)
    r = c.post("/scan", json={"pattern_ids": ["bo_only"], "start_date": "2025-06-02",
                              "end_date": "2026-03-31", "workers": 1, "label_horizon": 20})
    assert r.status_code == 200, r.text
    assert done.wait(10)
    assert got["end_date"] == TRAIN_END and got["data_dir"] == str(full_dir)
    assert got["cap_at_train_end"] is True
    r = c.post("/scan", json={"pattern_ids": ["bo_only"], "start_date": "2026-01-05",
                              "end_date": "2026-03-31", "workers": 1, "label_horizon": 20})
    assert r.status_code == 400


def _run_scan(tmp_path, full_dir, monkeypatch, name: str, **kw) -> tuple[dict, list]:
    """直接调 run_scan_multi 扫 full_dir(行情到 2026-03);返回 (结果, worker 读到的每只股票的最后一天)。"""
    seen_max: list = []
    real_slice = scan_mod.slice_window

    def spy(df, start, end):
        seen_max.append(df.index.max())
        return real_slice(df, start, end)
    monkeypatch.setattr(scan_mod, "slice_window", spy)
    from path2_web.discovery import PatternRegistry
    from path2_web.serialize import serialize_pattern
    reg = PatternRegistry()
    mod = reg.get("bo_only")
    out = tmp_path / "outputs"
    res = scan_mod.run_scan_multi(
        data_dir=str(full_dir), pattern_specs_json={"bo_only": serialize_pattern(mod.build_pattern(mod.load_params()))},
        module_paths={"bo_only": reg.module_path("bo_only")}, pattern_ids=["bo_only"],
        end_nodes={"bo_only": mod.eval_meta()["end_node"]}, head_buffer_trading_days=20, label_horizon=20,
        start_date="2025-07-01", end_date="2026-03-31", workers=1, ticker_regex=None, scan_ts=name, name=name,
        outputs_root=str(out), executor_factory=lambda w: ThreadPoolExecutor(max_workers=w), **kw)
    return res, seen_max


def test_web_scan_worker_reads_capped_bars_and_marks_data_until(tmp_path, full_dir, monkeypatch):
    """cap_at_train_end=True(网页扫描):worker 经 read_bars 读(看不到 2026 年的 bar),
    落盘 scan.data_until = TRAIN_END,网页能打开。"""
    res, seen_max = _run_scan(tmp_path, full_dir, monkeypatch, "20261102T000000", cap_at_train_end=True)
    assert res["scan"]["data_until"] == TRAIN_END
    assert seen_max and max(seen_max) <= pd.Timestamp(TRAIN_END)
    c = _client(tmp_path, full_dir)
    assert c.get("/scans/20261102T000000").status_code == 200
    row = next(r for r in c.get("/scans/").json() if r["name"] == "20261102T000000")
    assert "old_scan" not in row


def test_script_scan_reads_full_data_and_cannot_be_opened(tmp_path, full_dir, monkeypatch):
    """不传 cap_at_train_end(研究脚本,如 scan-wide.py):照旧读完整行情,不写 data_until,网页打不开。"""
    res, seen_max = _run_scan(tmp_path, full_dir, monkeypatch, "20261102T000001")
    assert "data_until" not in res["scan"]
    assert max(seen_max) > pd.Timestamp(TRAIN_END)
    c = _client(tmp_path, full_dir)
    assert c.get("/scans/20261102T000001").status_code == 409
    row = next(r for r in c.get("/scans/").json() if r["name"] == "20261102T000001")
    assert row["old_scan"] is True


@pytest.mark.parametrize("scan_section", [
    {"hit_stocks": 1, "scanned": 1},                                  # 截断之前扫的:没有 data_until
    {"hit_stocks": 1, "scanned": 1, "data_until": "2026-03-31"},      # 晚于训练段末日
])
def test_scan_beyond_data_wall_refused_and_numbers_hidden(tmp_path, full_dir, scan_section):
    scans = tmp_path / "outputs" / "scans"
    scans.mkdir(parents=True)
    (scans / "old.json").write_text(json.dumps({
        "pattern_ids": ["bo_only"], "scan": {"scan_ts": "20260906T231146", **scan_section},
        "per_pattern": {"bo_only": {"stats": {"median": 0.12},
                                    "first_passage_stats": {"n_bars": 3, "ratio": 0.5, "random_ratio": 0.4}}},
        "results": [{"symbol": "AAA", "per_pattern": {"bo_only": {"summary": {"hits": 1}}}}]}))
    c = _client(tmp_path, full_dir)
    assert c.get("/scans/old").status_code == 409
    row = next(r for r in c.get("/scans/").json() if r["name"] == "old")
    assert row["old_scan"] is True and row["hit_stocks"] is None
    assert row["per_pattern"]["bo_only"] | {"params_consistent": None} == \
        {"hits": None, "median": None, "fp": None, "params_consistent": None}
    assert c.delete("/scans/old").status_code == 200                # 删照常能删


def _feedback_client(tmp_path, ddir, monkeypatch, mapping_text: str) -> TestClient:
    """带临时标注目录、mapping 改从临时目录读(bo_only 写 mapping_text)的客户端。"""
    from path2_web import mapping

    mdir = tmp_path / "mappings"
    mdir.mkdir()
    (mdir / "bo_only.yaml").write_text(mapping_text, encoding="utf-8")
    monkeypatch.setattr(mapping, "mapping_path", lambda mod: mdir / f"{mod.__name__.split('.')[-2]}.yaml")
    adir = tmp_path / "annotations"
    adir.mkdir()
    cfg = {**data_cfg(ddir), "annotation_dir": str(adir), "machine": "pc"}
    return TestClient(create_app(config_override=cfg, outputs_root=str(tmp_path / "outputs"),
                                 use_thread_pool=True))


def _feedback_op(oid, symbol, start, end):
    return {"kind": "feedback", "id": oid, "base": None,
            "value": {"id": oid, "symbol": symbol, "pattern": "p", "app_id": "bo_only", "app_ver": "0" * 16,
                      "start": start, "end": end, "target": "range", "source": "picked", "answer": "neg",
                      "note": "x"}}


def test_feedback_status_reads_bars_only_until_train_end(tmp_path, full_dir, monkeypatch):
    """反馈状态接口跑 app:配置的目录误指到带 2026 年行情的数据,app 读到、跑到的 K 线也不晚于 2025-12-31;
    返回里没有晚于训练段末日的日期。几种参数(有反馈的 pattern、没有 mapping 的 pattern、怪名字)都一样。"""
    import path2_web.app_run as app_run

    _write_oscillating_pkl(full_dir, "BBB")
    c = _feedback_client(tmp_path, full_dir, monkeypatch, "pattern: p\nfeatures: {w-pc-1: bo}\n")
    r = c.post("/annotations/batch", json={"ops": [_feedback_op("f-pc-1", "BBB", "2025-12-01", TRAIN_END),
                                                    _feedback_op("f-pc-2", "AAA", "2025-06-02", "2025-12-30")]})
    assert r.status_code == 200, r.text

    seen: list = []
    real_read, real_slice = data_mod.read_bars, app_run.slice_window

    def spy_read(d, symbol):
        df = real_read(d, symbol)
        seen.append(df.index.max())
        return df

    def spy_slice(df, start, end):
        out = real_slice(df, start, end)
        seen.append(pd.Timestamp(out["date"].max()))
        return out
    monkeypatch.setattr(data_mod, "read_bars", spy_read)
    monkeypatch.setattr(app_run, "slice_window", spy_slice)

    for pattern in ("p", "no_such_pattern", "../p", "2026-03-31"):
        r = c.get("/feedback/status", params={"pattern": pattern})
        assert r.status_code == 200, r.text
        body = r.json()
        if pattern == "p":
            assert [i["status"] is not None for i in body["items"]] == [True, True]
        # reason 会照抄请求里的 pattern 名(参数,不是行情日期),不算
        dates = re.findall(r"\d{4}-\d{2}-\d{2}", json.dumps({k: v for k, v in body.items() if k != "reason"}))
        assert all(d <= TRAIN_END for d in dates)
    assert len(seen) == 4 and max(seen) <= pd.Timestamp(TRAIN_END)   # 两只股票各读一次、切一次(之后走缓存)


def test_annotation_changes_never_reads_bars(tmp_path, full_dir, monkeypatch):
    """GET /annotations/changes 只读标注与 mapping,不读行情(读行情的函数一调就让测试失败)。"""
    c = _feedback_client(tmp_path, full_dir, monkeypatch,
                         "pattern: p\nfeatures: {w-pc-1: bo}\nsession: {snapshot: {seen: {pc: 1}, samples: []}}\n")
    for ops in ([_feedback_op("f-pc-1", "AAA", "2025-12-01", "2025-12-05")],
                [{"kind": "sample", "id": "s-pc-2", "base": None,
                  "value": {"id": "s-pc-2", "symbol": "AAA", "date": "2025-12-08", "pattern": "p",
                            "judgment": "pos", "members": []}}]):
        assert c.post("/annotations/batch", json={"ops": ops}).status_code == 200

    def _forbidden(*a, **k):
        raise AssertionError("变化接口读了行情")
    monkeypatch.setattr(pd, "read_pickle", _forbidden)
    monkeypatch.setattr(data_mod, "read_bars", _forbidden)
    monkeypatch.setattr("path2_web.app_run.load_bars", _forbidden)
    monkeypatch.setattr("path2_web.api.load_bars", _forbidden)
    monkeypatch.setattr("path2_web.api.run_app", _forbidden)
    for pattern in ("p", "q", "2026-03-31"):
        r = c.get("/annotations/changes", params={"pattern": pattern})
        assert r.status_code == 200, r.text
    assert c.get("/annotations/changes", params={"pattern": "p"}).json() == {
        "since": {"pc": 1}, "changes": [{"kind": "sample", "id": "s-pc-2", "change": "added"}], "reason": None}
