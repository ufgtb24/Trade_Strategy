# -*- coding: utf-8 -*-
"""ledger 单测(tune-gates skill 自带;显式路径跑):
uv run pytest .claude/skills/tune-gates/test_ledger.py -q
只用合成交易日历与临时账本目录(TUNE_LEDGER_DIR),不读数据目录、不碰真实账本。
"""
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

import ledger as L  # noqa: E402

CAL = pd.bdate_range("2023-01-02", "2026-08-17")
TRAIN = {"start": "2024-01-01", "end": "2025-12-31"}
NO_WINDOW = {"window": None, "label_horizon": None}
GOOD = {   # kind -> (公共字段覆盖, 合法 data)
    "open": ({}, {"data_start": "2021-08-20", "data_end": "2026-08-17", "n_probed": 400,
                  "train": {"start": "2024-01-01", "end": "2025-12-31", "label_end": "2026-02-25"},
                  "confirm": {"backward": {"start": "2022-08-18", "end": "2023-11-02", "label_end": "2023-12-29"},
                              "forward": {"start": "2026-02-26", "end": "2026-06-19", "label_end": "2026-08-17"}}}),
    "ruling": (NO_WINDOW, {"topic": "delta", "value": 2.0}),
    "edge": ({}, {"points": {}, "verdict": "有边际"}),
    "select": ({"n_looks": 3}, {"tool": "screen"}),
    "preregister": (NO_WINDOW, {"manifest_hash": "h", "manifest": {}, "survivorship": {},
                                "expected_power": {"backward": 0.6, "forward": 0.7}}),
    "extrapolate": ({}, {"manifest_hash": "h", "confirm_window": "forward", "results": {}}),
    "decide": ({}, {"params": {"sec.alpha": [0.003, 0.0075]}, "selects_on": ["sec.alpha"],
                    "provisional": True, "depends_on": {"sec.beta": 3}}),
    "discover": ({"fc": ["FC-001"]}, {}),
    "verify": ({"fc": ["FC-001"]}, {}),
    "reconcile": ({"fc": ["FC-006"]}, {}),
}


@pytest.fixture(autouse=True)
def ledger_dir(tmp_path, monkeypatch):
    d = tmp_path / "ledger"
    monkeypatch.setenv("TUNE_LEDGER_DIR", str(d))
    return d


def _rec(kind, **kw):
    over, data = GOOD[kind]
    fields = dict(actor="test", round="r1", window=dict(TRAIN), label_horizon=40, head_buffer=250, git_head=None,
                  base_fingerprint=None, source_fingerprint=None, ruler_fingerprint=None)
    fields.update(over)
    fields["data"] = json.loads(json.dumps(data))
    fields.update(kw)
    return L.make_record(kind, "demo", **fields)


# ---------------------------------------------------------------- schema

def test_make_record_defaults():
    r = L.make_record("select", "demo")
    assert r["schema"] == L.SCHEMA and r["kind"] == "select" and r["app"] == "demo"
    assert (r["fc"], r["axes"], r["ref"], r["data"], r["note"], r["n_looks"], r["stock_rule"]) == ([], [], {}, {}, "", 0, "all")
    pd.Timestamp(r["ts"])


def test_every_kind_valid_and_roundtrip(ledger_dir):
    for kind in L.KINDS:
        L.append(_rec(kind))
    got = L.read("demo")
    assert [r["kind"] for r in got] == list(L.KINDS)
    assert L.validate_file(ledger_dir / "demo.jsonl") == got
    assert L.ledger_path("demo") == ledger_dir / "demo.jsonl"


def test_read_missing_file_is_empty():
    assert L.read("nobody") == []


@pytest.mark.parametrize("field", ["round", "window", "git_head", "n_looks", "data"])
def test_missing_common_field_rejected(field):
    r = _rec("select")
    del r[field]
    with pytest.raises(ValueError, match="缺少字段"):
        L.validate_record(r)


def test_unknown_field_and_bad_kind_rejected():
    with pytest.raises(ValueError, match="未知字段"):
        L.validate_record({**_rec("select"), "windows": TRAIN})
    with pytest.raises(ValueError, match="未知记录类型"):
        L.validate_record({**_rec("select"), "kind": "peek"})


@pytest.mark.parametrize("kind,key", [("open", "confirm"), ("open", "n_probed"), ("ruling", "topic"), ("edge", "verdict"),
                                      ("select", "tool"), ("preregister", "expected_power"),
                                      ("extrapolate", "confirm_window"), ("decide", "depends_on"),
                                      ("decide", "selects_on")])
def test_data_missing_key_rejected(kind, key):
    r = _rec(kind)
    del r["data"][key]
    with pytest.raises(ValueError, match="data 缺少"):
        L.validate_record(r)


@pytest.mark.parametrize("kind,mutate,msg", [
    ("select", lambda r: r.update(n_looks=0), "n_looks 至少为 1"),
    ("select", lambda r: r["data"].update(tool="plateau"), "tool"),
    ("ruling", lambda r: r["data"].update(topic="whatever"), "topic"),
    ("extrapolate", lambda r: r["data"].update(confirm_window="middle"), "confirm_window"),
    ("decide", lambda r: r["data"].update(params={"sec.alpha": 0.0075}), "params"),
    ("decide", lambda r: r["data"].update(provisional="yes"), "provisional"),
    ("preregister", lambda r: r["data"].update(expected_power={"forward": 0.7}), "expected_power"),
    ("open", lambda r: r["data"]["confirm"].pop("forward"), "两段"),
    ("open", lambda r: r["data"]["train"].pop("label_end"), "label_end"),
    ("discover", lambda r: r.update(fc=[]), "fc 非空"),
    ("discover", lambda r: r.update(fc=["FC1"]), "FC-xxx"),
    ("select", lambda r: r.update(axes=["exceed_threshold"]), "轴名"),
    ("select", lambda r: r.update(window=None), "window"),
    ("select", lambda r: r.update(window={"start": "2025-01-01", "end": "2024-01-01"}), "起点晚于终点"),
    ("select", lambda r: r.update(label_horizon=0), "label_horizon"),
    ("select", lambda r: r.update(ref={"a.csv": "not-a-hash"}), "ref"),
    ("select", lambda r: r["data"].update(x=float("nan")), "标准 JSON"),
])
def test_bad_values_rejected(kind, mutate, msg):
    r = _rec(kind)
    mutate(r)
    with pytest.raises(ValueError, match=msg):
        L.validate_record(r)


def test_axis_names_both_forms_accepted():
    L.validate_record(_rec("select", axes=["sec.alpha", "feature:omega"]))


# ---------------------------------------------------------------- 截断尾行 / 中间行损坏

def _lines(n):
    return [json.dumps(_rec("select", note=f"#{i}"), ensure_ascii=False) for i in range(n)]


def test_truncated_tail_tolerated(ledger_dir):
    ledger_dir.mkdir(parents=True)
    p = ledger_dir / "demo.jsonl"
    p.write_bytes(("\n".join(_lines(2)) + "\n").encode() + _lines(1)[0].encode()[:37])
    assert [r["note"] for r in L.read("demo")] == ["#0", "#1"]
    assert len(L.validate_file(p)) == 2


def test_truncated_tail_inside_multibyte_char_tolerated(ledger_dir):
    ledger_dir.mkdir(parents=True)
    tail = json.dumps(_rec("select", note="中文备注"), ensure_ascii=False).encode()
    cut = tail.index("中".encode()) + 1          # 切在一个汉字的字节中间
    (ledger_dir / "demo.jsonl").write_bytes((_lines(1)[0] + "\n").encode() + tail[:cut])
    assert len(L.read("demo")) == 1


def test_middle_line_corruption_raises(ledger_dir):
    ledger_dir.mkdir(parents=True)
    a, b = _lines(2)
    (ledger_dir / "demo.jsonl").write_text(a + "\n" + b[:40] + "\n" + b + "\n")
    with pytest.raises(ValueError, match="第 2 行损坏"):
        L.read("demo")


def test_invalid_record_line_reports_line_number(ledger_dir):
    ledger_dir.mkdir(parents=True)
    bad = _rec("select", n_looks=0)
    (ledger_dir / "demo.jsonl").write_text(_lines(1)[0] + "\n" + json.dumps(bad) + "\n")
    with pytest.raises(ValueError, match="第 2 行"):
        L.read("demo")


def test_complete_last_line_without_newline_kept_and_append_continues(ledger_dir):
    ledger_dir.mkdir(parents=True)
    (ledger_dir / "demo.jsonl").write_text(_lines(1)[0])
    assert len(L.read("demo")) == 1
    L.append(_rec("select", note="next"))
    assert [r["note"] for r in L.read("demo")] == ["#0", "next"]


def test_append_drops_truncated_tail_first(ledger_dir):
    L.append(_rec("select", note="a"))
    with open(ledger_dir / "demo.jsonl", "ab") as f:
        f.write(b'{"schema": 1, "ts": "2026-09')
    L.append(_rec("select", note="b"))
    raw = (ledger_dir / "demo.jsonl").read_text()
    assert raw.endswith("\n") and raw.count("\n") == 2
    assert [r["note"] for r in L.read("demo")] == ["a", "b"]


def test_append_rejects_invalid_record_without_writing(ledger_dir):
    with pytest.raises(ValueError):
        L.append(_rec("select", n_looks=0))
    assert not (ledger_dir / "demo.jsonl").exists()


# ---------------------------------------------------------------- ref 哈希

def test_ref_checked_on_append(tmp_path, ledger_dir):
    art = tmp_path / "cells.csv"
    art.write_text("a,b\n1,2\n")
    sha = L.sha256_file(art)
    L.append(_rec("select", ref={str(art): sha}))
    with pytest.raises(ValueError, match="哈希不一致"):
        L.append(_rec("select", ref={str(art): "0" * 64}))
    with pytest.raises(ValueError, match="不存在"):
        L.append(_rec("select", ref={str(tmp_path / "gone.csv"): sha}))
    L.append(_rec("select", ref={str(tmp_path / "gone.csv"): sha}), check_refs=False)
    rel = ".claude/skills/tune-gates/ledger.py"                       # 相对路径按 REPO 解析
    L.append(_rec("select", ref={rel: L.sha256_file(L.REPO / rel)}))
    assert len(L.read("demo")) == 3


def test_validate_file_does_not_recheck_ref_hashes(tmp_path, ledger_dir):
    art = tmp_path / "cells.csv"
    art.write_text("v1")
    L.append(_rec("select", ref={str(art): L.sha256_file(art)}))
    art.write_text("v2")                                        # 产物之后合法地变了
    assert len(L.read("demo")) == 1


# ---------------------------------------------------------------- 窗口运算

def test_label_end_counts_trading_days_after_buy_end():
    pos = CAL.searchsorted(pd.Timestamp("2025-12-31"), side="right")
    assert L.label_end("2025-12-31", 40, CAL) == CAL[pos + 39]
    assert L.label_end("2025-12-31", 1, CAL) == pd.Timestamp("2026-01-01")
    # 非交易日的 buy_end 与它之前最后一个交易日同一个 label_end
    assert L.label_end("2025-06-07", 40, CAL) == L.label_end("2025-06-06", 40, CAL)


def test_label_end_extrapolates_past_calendar_end():
    n_after = len(CAL) - CAL.searchsorted(pd.Timestamp("2026-08-10"), side="right")
    assert L.label_end("2026-08-10", 40, CAL) == CAL[-1] + pd.offsets.BDay(40 - n_after)
    assert L.label_end("2027-01-04", 5, CAL) == pd.Timestamp("2027-01-11")


def test_overlaps_includes_label_suffix_both_ways():
    a = {"start": "2024-01-01", "end": "2024-03-29"}
    le = L.label_end(a["end"], 40, CAL)
    touch = {"start": str(le.date()), "end": "2024-12-31"}
    after = {"start": str(CAL[CAL.get_loc(le) + 1].date()), "end": "2024-12-31"}
    assert L.overlaps(a, touch, 40, CAL) and L.overlaps(touch, a, 40, CAL)
    assert not L.overlaps(a, after, 40, CAL) and not L.overlaps(after, a, 40, CAL)
    assert L.overlaps(a, {"start": "2023-01-02", "end": "2023-01-02"}, 400, CAL)   # b 的 label 后缀盖住 a


def test_burned_filters_kind_axes_and_window():
    w24 = {"start": "2024-01-01", "end": "2024-12-31"}
    L.append(_rec("discover", axes=["sec.beta"], window=w24))
    L.append(_rec("select", axes=["sec.alpha", "sec.beta"], window=dict(TRAIN)))
    L.append(_rec("open", axes=["sec.alpha"]))
    L.append(_rec("decide", axes=["sec.alpha"]))
    L.append(_rec("discover", fc=["FC-004"], axes=[], window=w24))                  # 方法结论,无轴
    le = L.label_end("2024-12-31", 40, CAL)
    just_in = {"start": str(le.date()), "end": "2025-06-30"}
    just_out = {"start": str(CAL[CAL.get_loc(le) + 1].date()), "end": "2025-06-30"}
    only_pk = lambda win: [r["kind"] for r in L.burned("demo", win, ["sec.beta"], CAL)
                           if r["axes"] == ["sec.beta"]]
    assert only_pk(just_in) == ["discover"]
    assert only_pk(just_out) == []
    assert [r["kind"] for r in L.burned("demo", just_out, ["sec.alpha"], CAL)] == ["select"]
    assert [r["kind"] for r in L.burned("demo", w24, None, CAL)] == ["discover", "select", "discover"]
    assert L.burned("demo", {"start": "2026-06-01", "end": "2026-06-30"}, None, CAL) == []


def test_looks_sums_n_looks_over_touching_records():
    L.append(_rec("select", n_looks=3, axes=["sec.alpha", "sec.gamma"]))
    L.append(_rec("discover", n_looks=1, axes=["sec.gamma"]))
    L.append(_rec("edge", n_looks=5, axes=[]))
    assert L.looks("demo", ["sec.alpha"]) == 3
    assert L.looks("demo", ["sec.gamma"]) == 4
    assert L.looks("demo", ["sec.alpha", "sec.gamma"]) == 4
    assert L.looks("demo", ["sec.delta"]) == 0


def test_latest_returns_last_matching_record():
    assert L.latest("demo", "ruling") is None
    L.append(_rec("ruling", round=1, note="r1-a"))
    L.append(_rec("ruling", round=2, note="r2"))
    L.append(_rec("select", round=2, note="sel"))
    L.append(_rec("ruling", round=1, note="r1-b"))
    assert L.latest("demo", "ruling")["note"] == "r1-b"
    assert L.latest("demo", "ruling", round=2)["note"] == "r2"
    assert L.latest("demo", "select", round=1) is None
    assert L.latest("demo", "edge") is None
    with pytest.raises(ValueError, match="未知记录类型"):
        L.latest("demo", "rulings")
    with pytest.raises(ValueError, match="公共字段"):
        L.latest("demo", "ruling", topic="delta")


# ---------------------------------------------------------------- 指纹

def test_ruler_fingerprint_order_bytes_and_missing(tmp_path, monkeypatch):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "a.py").write_text("A = 1\n")
    (tmp_path / "pkg" / "b.py").write_text("B = 2\n")
    monkeypatch.setattr(L, "RULER_FILES", ("a.py", "pkg/b.py"))
    fp = L.ruler_fingerprint(tmp_path)
    assert len(fp) == 64 and fp == L.ruler_fingerprint(tmp_path)
    monkeypatch.setattr(L, "RULER_FILES", ("pkg/b.py", "a.py"))
    assert L.ruler_fingerprint(tmp_path) != fp
    monkeypatch.setattr(L, "RULER_FILES", ("a.py", "pkg/b.py"))
    (tmp_path / "a.py").write_text("A = 3\n")
    assert L.ruler_fingerprint(tmp_path) != fp
    (tmp_path / "pkg" / "b.py").unlink()
    with pytest.raises(FileNotFoundError, match="pkg/b.py"):
        L.ruler_fingerprint(tmp_path)


def test_current_fingerprints_shape(tmp_path, monkeypatch):
    for rel in ("r1.py", "r2.py"):
        (tmp_path / rel).write_text(rel)
    monkeypatch.setattr(L, "RULER_FILES", ("r1.py", "r2.py"))
    monkeypatch.setattr(L, "REPO", tmp_path)
    monkeypatch.setattr(L.ruler_fingerprint, "__defaults__", (tmp_path,))
    monkeypatch.setattr(L, "_study_path", lambda app, window: HERE / "fixtures" / "study_bb_v1.py")
    fp = L.current_fingerprints("demo", "main")
    assert set(fp) == set(L.FINGERPRINT_FIELDS)
    assert all(len(fp[k]) == 64 for k in ("base_fingerprint", "source_fingerprint", "ruler_fingerprint"))
    assert fp["ruler_fingerprint"] == L.ruler_fingerprint(tmp_path) and fp["git_head"]
