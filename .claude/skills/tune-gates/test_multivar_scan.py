# -*- coding: utf-8 -*-
"""multivar_scan 单测(tune-gates skill 自带;显式路径跑):
uv run pytest .claude/skills/tune-gates/test_multivar_scan.py -q -p no:cacheprovider
共用扫描池、断点续跑 done 集、延迟标签补算与读取。全部合成数据:临时账本目录、合成交易日历、临时 pkl 目录。
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
REPO = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
sys.path.insert(0, str(REPO))

import holdout as H  # noqa: E402
import ledger as L  # noqa: E402
import multivar_scan as MS  # noqa: E402
from multivar_core import STATES, seg_id_of, span_key_json  # noqa: E402
from path2.eval import spans_first_passage  # noqa: E402
from path2_web.data import slice_window  # noqa: E402

CAL = pd.bdate_range("2021-08-20", "2026-08-17")
HB, HZ, K = 250, 40, 1.0
HASH = "manifest-1"
PAST = "2026-01-05T09:00:00"


@pytest.fixture(autouse=True)
def ledger_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("TUNE_LEDGER_DIR", str(tmp_path / "ledger"))


# ---------------------------------------------------------------- 共用扫描池
def _slow_square(item, add):
    time.sleep((item * 7 % 5) * 0.01)          # 打乱完成顺序
    return (item, item * item + add, os.getpid())


def test_scan_pool_result_independent_of_completion_order():
    items = list(range(23))
    seen = {}
    for workers in (1, 4):
        got = []
        MS._scan_pool(items, _slow_square, (5,), workers, got.append)
        assert len(got) == len(items)
        assert all(pid != os.getpid() for *_, pid in got)                 # worker 在子进程跑
        seen[workers] = sorted(r[:2] for r in got)
    assert seen[1] == seen[4] == [(i, i * i + 5) for i in items]


# ---------------------------------------------------------------- 断点续跑与分片提交
def test_done_symbols_is_union_of_four_sources(tmp_path):
    (tmp_path / "longtable").mkdir(); (tmp_path / "baseline").mkdir()
    pd.DataFrame({"symbol": pd.Categorical(["AAA", "BBB", "AAA"]), "x": [1, 2, 3]}).to_parquet(
        tmp_path / "longtable/part-0000.parquet")
    pd.DataFrame({"symbol": ["BBB", "CCC"]}).to_parquet(tmp_path / "baseline/part-0001.parquet")
    MS.commit_shard(tmp_path, "part-0000.parquet"); MS.commit_shard(tmp_path, "part-0001.parquet")
    pd.DataFrame({"symbol": ["ZZZ"]}).to_parquet(tmp_path / "baseline/part-0005.parquet")     # 未提交:不算
    pd.DataFrame({"symbol": ["DDD", "NA"]}).to_csv(tmp_path / "filtered_symbols.csv", index=False)
    pd.DataFrame({"symbol": ["EEE"]}).to_csv(tmp_path / "empty_symbols.csv", index=False)
    done, parts = MS._done_symbols(tmp_path)
    assert done == {"AAA", "BBB", "CCC", "DDD", "NA", "EEE"}
    assert parts["longtable"] == {"AAA", "BBB"} and parts["baseline"] == {"BBB", "CCC"}
    assert parts["filtered"] == ["DDD", "NA"] and parts["empty"] == ["EEE"]
    (tmp_path / "empty_symbols.csv").unlink()
    assert MS._done_symbols(tmp_path)[0] == {"AAA", "BBB", "CCC", "DDD", "NA"}
    assert MS._next_shard(tmp_path) == 6
    MS.drop_uncommitted(tmp_path)
    assert not (tmp_path / "baseline/part-0005.parquet").exists() and MS._next_shard(tmp_path) == 2


def test_next_shard_counts_committed_names(tmp_path):
    assert MS._next_shard(tmp_path) == 0
    MS.commit_shard(tmp_path, "part-0007.parquet")          # 已提交分片的文件被手动删掉:号也不复用
    assert MS._next_shard(tmp_path) == 8


def test_commit_shard_seals_truncated_line(tmp_path):
    (tmp_path / MS.COMMIT_FILE).write_text("shard\npart-00", encoding="utf-8")
    MS.commit_shard(tmp_path, "part-0001.parquet")
    assert "part-0001.parquet" in MS.committed_shards(tmp_path)
    assert MS.committed_shards(tmp_path / "nowhere") is None


def _lt(syms):
    return pd.DataFrame({"symbol": pd.Categorical(syms), "seg_id": np.arange(len(syms), dtype="int64")})


def _base(sym, n):
    return pd.DataFrame({"symbol": [sym] * n, "date": pd.bdate_range("2024-01-02", periods=n), "up": 1})


def _read_dir(d):
    return pd.concat([pd.read_parquet(p) for p in sorted(Path(d).glob("part-*.parquet"))], ignore_index=True)


def test_resume_after_crash_between_baseline_and_longtable(tmp_path, capsys):
    """基线片已落盘、长表片还没写、没提交时进程被杀:续跑删掉这批残片、重扫这批股票,长表行不丢、基线不重复。"""
    for d in MS.SHARD_DIRS:
        (tmp_path / d).mkdir()
    MS.write_shard(tmp_path, 0, {"baseline": _base("AAA", 3), "longtable": _lt(["AAA", "AAA"])})
    MS._write_parquet(_base("BBB", 4), tmp_path / "baseline/part-0001.parquet")
    (tmp_path / "longtable/part-0001.parquet.tmp").write_bytes(b"half")
    done, _parts, n_shard = MS.prepare_resume(tmp_path)
    assert "续跑" in capsys.readouterr().out
    assert done == {"AAA"} and n_shard == 1
    assert not (tmp_path / "baseline/part-0001.parquet").exists()
    assert not (tmp_path / "longtable/part-0001.parquet.tmp").exists()
    MS.write_shard(tmp_path, n_shard, {"baseline": _base("BBB", 4), "longtable": _lt(["BBB"])})   # 重扫 BBB
    lt, bl = _read_dir(tmp_path / "longtable"), _read_dir(tmp_path / "baseline")
    assert sorted(lt["symbol"].astype(str)) == ["AAA", "AAA", "BBB"]
    assert bl["symbol"].value_counts().to_dict() == {"BBB": 4, "AAA": 3}
    assert MS.committed_shards(tmp_path) == {"part-0000.parquet", "part-0001.parquet"}
    assert MS.prepare_resume(tmp_path)[:1] == ({"AAA", "BBB"},)


def test_resume_drops_orphan_segments_shard(tmp_path):
    """延迟模式:买点事件片已写、长表片没写 → 续跑时删掉这片孤儿,补标签不会白算、同一股票不会出现在两片。"""
    for d in MS.SHARD_DIRS:
        (tmp_path / d).mkdir()
    seg = lambda sym: pd.DataFrame([(sym, 1, "[[1,2]]")], columns=MS.SEGMENT_COLS)  # noqa: E731
    MS.write_shard(tmp_path, 0, {"segments": seg("AAA"), "longtable": _lt(["AAA"])})
    MS._write_parquet(seg("BBB"), tmp_path / "segments/part-0001.parquet")
    done, _parts, n_shard = MS.prepare_resume(tmp_path)
    assert done == {"AAA"} and n_shard == 1
    assert [p.name for p in (tmp_path / "segments").glob("part-*.parquet")] == ["part-0000.parquet"]


def test_shards_without_commit_list_are_not_deleted(tmp_path):
    (tmp_path / "longtable").mkdir()
    _lt(["AAA"]).to_parquet(tmp_path / "longtable/part-0000.parquet")
    with pytest.raises(SystemExit, match="提交清单"):
        MS.prepare_resume(tmp_path)
    assert (tmp_path / "longtable/part-0000.parquet").exists()


# ---------------------------------------------------------------- 延迟标签
def _common(**kw):
    f = dict(actor="test", round="r1", window=None, label_horizon=None, head_buffer=None, git_head=None,
             base_fingerprint=None, source_fingerprint=None, ruler_fingerprint=None)
    f.update(kw)
    return f


def _win(data, sym, meta):
    s, e, bs, be = MS._window_bounds(meta["start_date"], meta["end_date"], meta["head_buffer"], meta["label_horizon"])
    win = slice_window(pd.read_pickle(data / f"{sym}.pkl"), bs, be)
    return win, int(win["date"].searchsorted(s, "left")), int(win["date"].searchsorted(e, "right")) - 1


@pytest.fixture
def deferred_run(tmp_path, monkeypatch):
    """一份扫在前向确认窗上的延迟标签模式结果:segments 两片(0000、0002)、longtable 同号两片。"""
    monkeypatch.setattr(H, "default_calendar", lambda: CAL)
    monkeypatch.setattr(MS, "REPO", tmp_path)
    w = H.confirm_windows("2024-01-01", "2025-12-31", calendar=CAL, head_buffer=HB, horizon=HZ)
    L.append(L.make_record("open", "demo", **_common(window={"start": "2024-01-01", "end": "2025-12-31"},
                                                     label_horizon=HZ, head_buffer=HB), data={**w, "n_probed": 400}))
    start = w["confirm"]["forward"]["start"]
    meta = {"app": "demo", "start_date": start, "end_date": str(CAL[CAL.get_loc(pd.Timestamp(start)) + 20].date()),
            "head_buffer": 30, "label_horizon": HZ, "first_passage_k": K, "label_mode": "deferred"}
    out = tmp_path / "outputs/tune_gates/demo/cw"
    for sub in ("longtable", "segments"):
        (out / sub).mkdir(parents=True)
    (out / "longtable/run_meta.json").write_text(json.dumps(meta))
    data = tmp_path / "pkls"; data.mkdir()
    rng = np.random.default_rng(3)
    for sym in ("AAA", "NA", "BBB"):
        close = 10 * np.exp(np.cumsum(rng.normal(0, 0.02, len(CAL))))
        pd.DataFrame({"open": close, "high": close * (1 + rng.uniform(0, 0.03, len(CAL))),
                      "low": close * (1 - rng.uniform(0, 0.03, len(CAL))), "close": close, "volume": 1e6},
                     index=pd.DatetimeIndex(CAL, name="date")).to_pickle(data / f"{sym}.pkl")
    spans = {}
    for sym in ("AAA", "NA", "BBB"):
        _, lo, hi = _win(data, sym, meta)
        spans[sym] = [((lo - 2, lo + 3),), ((lo + 5, lo + 9), (lo + 12, lo + 12)), ((hi - 1, hi + 2),)]
    for shard, syms in (("part-0000.parquet", ("AAA", "NA")), ("part-0002.parquet", ("BBB",))):
        seg = [(sym, seg_id_of(k), span_key_json(k)) for sym in syms for k in spans[sym]]
        pd.DataFrame(seg, columns=MS.SEGMENT_COLS).astype({"seg_id": "int64"}).to_parquet(out / "segments" / shard)
        lt = [(sym, seg_id_of(k), i) for sym in syms for k in spans[sym] for i in range(2)]   # 同一买点事件两行
        pd.DataFrame({"symbol": pd.Categorical([r[0] for r in lt]), "seg_id": np.array([r[1] for r in lt], "int64"),
                      "x": [r[2] for r in lt]}).to_parquet(out / "longtable" / shard)
        MS.commit_shard(out, shard)
    # 写到一半被打断、没提交的买点事件片:补标签不处理它
    pd.DataFrame([("AAA", 1, "[[1,2]]")], columns=MS.SEGMENT_COLS).to_parquet(out / "segments/part-0003.parquet")
    return SimpleNamespace(out=out, meta=meta, data=data, spans=spans, cfg=SimpleNamespace(data_dir=str(data), workers=2))


def _pre():
    r = L.make_record("preregister", "demo", **_common(), data={
        "manifest_hash": HASH, "manifest": {}, "survivorship": {}, "expected_power": {"backward": 0.8, "forward": 0.8}})
    r["ts"] = PAST
    L.append(r)
    L.append(L.make_record("ruling", "demo", **_common(), data={"topic": "power_notified", "value": True,
                                                                 "manifest_hash": HASH}))


def test_compute_deferred_labels_refused_by_guard(deferred_run):
    r = deferred_run
    with pytest.raises(H.HoldoutLocked) as e:
        MS.compute_deferred_labels("demo", "cw", r.cfg, manifest_hash="no-such-manifest", confirm_window="forward")
    assert e.value.reason == "validate_refused"
    _pre()
    with pytest.raises(H.HoldoutLocked) as e:           # 清单齐了,但声明打开的是另一段
        MS.compute_deferred_labels("demo", "cw", r.cfg, manifest_hash=HASH, confirm_window="backward")
    assert e.value.reason == "confirm_overlap"
    assert not (r.out / "labels").exists()


def test_compute_deferred_labels_refuses_full_mode_scan(deferred_run):
    r = deferred_run
    (r.out / "longtable/run_meta.json").write_text(json.dumps({**r.meta, "label_mode": "full"}))
    _pre()
    with pytest.raises(SystemExit, match="不需要补算"):
        MS.compute_deferred_labels("demo", "cw", r.cfg, manifest_hash=HASH, confirm_window="forward")


def test_compute_deferred_labels_matches_direct_first_passage(deferred_run):
    r = deferred_run
    _pre()
    lab = MS.compute_deferred_labels("demo", "cw", r.cfg, manifest_hash=HASH, confirm_window="forward")
    assert lab == r.out / "labels"
    assert sorted(p.name for p in lab.glob("part-*.parquet")) == ["part-0000.parquet", "part-0002.parquet"]
    n = 0
    for shard, syms in (("part-0000.parquet", ("AAA", "NA")), ("part-0002.parquet", ("BBB",))):
        got = pd.read_parquet(lab / shard)
        assert list(got.columns) == MS.LABEL_TABLE_COLS and set(got["symbol"]) == set(syms)
        for sym in syms:
            win, lo, hi = _win(r.data, sym, r.meta)
            for k in r.spans[sym]:
                row = got[(got["symbol"] == sym) & (got["seg_id"] == seg_id_of(k))]
                fp = spans_first_passage(win, k, HZ, K, sample_window=(lo, hi))
                assert len(row) == 1 and [int(row[f"fp_{s}"].iat[0]) for s in STATES] == [fp[s] for s in STATES]
                n += sum(fp.values())
    assert n > 0
    mtimes = {p: p.stat().st_mtime_ns for p in lab.glob("part-*.parquet")}
    MS.compute_deferred_labels("demo", "cw", r.cfg, manifest_hash=HASH, confirm_window="forward")   # 断点续跑:整片跳过
    assert {p: p.stat().st_mtime_ns for p in lab.glob("part-*.parquet")} == mtimes

    frames = list(MS.read_with_labels(r.out / "longtable", ["symbol", "seg_id", "x", "fp_up", "fp_none"]))
    assert [list(f.columns) for f in frames] == [["symbol", "seg_id", "x", "fp_up", "fp_none"]] * 2
    both = pd.concat(frames, ignore_index=True)
    assert len(both) == 2 * sum(len(v) for v in r.spans.values())
    ref = pd.concat([pd.read_parquet(lab / s) for s in ("part-0000.parquet", "part-0002.parquet")])
    ref_up = {(a, b): c for a, b, c in zip(ref["symbol"], ref["seg_id"], ref["fp_up"])}
    assert all(u == ref_up[(str(s), g)] for s, g, u in zip(both["symbol"], both["seg_id"], both["fp_up"]))


def test_read_with_labels_raises_on_missing_labels(deferred_run):
    r = deferred_run
    _pre()
    lab = MS.compute_deferred_labels("demo", "cw", r.cfg, manifest_hash=HASH, confirm_window="forward")
    part = pd.read_parquet(lab / "part-0002.parquet")
    part.iloc[1:].to_parquet(lab / "part-0002.parquet", index=False)          # 少一个买点事件的标签
    with pytest.raises(ValueError, match="找不到标签"):
        list(MS.read_with_labels(r.out / "longtable", ["symbol", "seg_id", "fp_up"]))
    (lab / "part-0002.parquet").unlink()                                       # 整片没补算
    with pytest.raises(ValueError, match="还没补算"):
        list(MS.read_with_labels(r.out / "longtable", ["symbol", "seg_id", "fp_up"]))
    (r.out / MS.COMMIT_FILE).unlink()                                          # 没有提交清单
    with pytest.raises(ValueError, match="提交清单"):
        list(MS.read_with_labels(r.out / "longtable", ["symbol", "seg_id", "fp_up"]))


# ---------------------------------------------------------------- run_meta
def test_run_meta_records_ticker_regex_outside_caliber(tmp_path):
    """股票范围写进 run_meta 但不是口径:小正则试跑后放开全宇宙续跑,run_meta 按本次值重写、不被口径闸拒绝。"""
    import study_io as S
    cl = {"fingerprints": {"study": "st", "source": {"hash": "so"}, "base": "ba", "ruler": "ru"}, "git_head": "abc1234"}
    cfg = SimpleNamespace(start_date="2024-01-01", end_date="2026-01-01", head_buffer=250, label_horizon=40,
                          first_passage_k=5.0, price_min=0.5, price_max=30.0, volume_min=10000.0, ticker_regex="^A[A-B]")
    meta = MS.run_meta_of("demo", cfg, cl, "full")
    assert meta["ticker_regex"] == "^A[A-B]" and "ticker_regex" not in S.RUN_CALIBER
    S.write_run_meta(tmp_path, meta)
    S.write_run_meta(tmp_path, MS.run_meta_of("demo", SimpleNamespace(**{**vars(cfg), "ticker_regex": None}), cl, "full"))
    assert S.load_run_meta(tmp_path)["ticker_regex"] is None
