"""标注的两个路由:GET /annotations(重放出的当前状态)、POST /annotations/batch(追加一批操作)。

钉住的要求:
- 沿用现有路由风格,不带 /api 前缀;
- 读接口返回状态、冲突、指纹比对;指纹对不上时标出不符,状态照常返回;
- 追加先校验,违反因果时回 400 并附原因,一个文件都不写;通过就新写一个文件、返回新的读结果;
- 数据墙:两个路由都不读行情(读行情的函数一调就让测试失败),返回里形如 YYYY-MM-DD 的日期都不晚于
  2025-12-31;送来晚于训练段末日的日期被拒绝。批次文件名里的时间戳是保存时刻,不是行情日期,格式也不同。
"""
from __future__ import annotations

import json
import re

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from path2_web.annotation import store
from path2_web.app import create_app
from path2_web.snapshot_fingerprint import write_manifest
from tests.path2_web.conftest import data_cfg

TRAIN_END = "2025-12-31"
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


@pytest.fixture
def snapshot(tmp_path):
    """一个带指纹清单的副本目录,里面那只股票的行情跨过 2025-12-31(用来证明路由不读行情)。"""
    d = tmp_path / "pkls"
    d.mkdir()
    idx = pd.bdate_range("2025-11-03", "2026-02-27", name="date")
    close = 10 + np.arange(len(idx)) * 0.01
    pd.DataFrame({"open": close, "high": close, "low": close, "close": close, "volume": np.full(len(idx), 1e6)},
                 index=idx).to_pickle(d / "AAA.pkl")
    write_manifest(d)
    return d


@pytest.fixture
def adir(tmp_path):
    d = tmp_path / "annotations"
    d.mkdir()
    return d


def _client(snapshot, adir, machine="pc") -> TestClient:
    cfg = {**data_cfg(snapshot), "annotation_dir": str(adir), "machine": machine}
    return TestClient(create_app(config_override=cfg, outputs_root=str(adir.parent / "outputs"),
                                 use_thread_pool=True))


def _box(oid, start, end, base=None, **extra):
    return {"kind": "box", "id": oid, "base": base,
            "value": {"id": oid, "symbol": "AAA", "feature": None, "start": start, "end": end, **extra}}


def _sample(oid, date, members, base=None):
    return {"kind": "sample", "id": oid, "base": base,
            "value": {"id": oid, "symbol": "AAA", "date": date, "pattern": None, "judgment": "pos",
                      "members": members}}


def _dates(obj) -> list[str]:
    return [m.group(0) for m in _DATE.finditer(json.dumps(obj))]


def test_read_empty(snapshot, adir):
    r = _client(snapshot, adir).get("/annotations")
    assert r.status_code == 200
    body = r.json()
    assert body["state"]["charts"] == [] and body["conflicts"] == [] and body["next_seq"] == 1
    assert body["fingerprint"]["consistent"] is True
    assert _client(snapshot, adir).get("/api/annotations").status_code == 404


def test_append_then_read(snapshot, adir):
    client = _client(snapshot, adir)
    r = client.post("/annotations/batch", json={"ops": [_box("b-pc-1", "2025-12-01", "2025-12-05"),
                                                         _sample("s-pc-2", "2025-12-08", ["b-pc-1"])]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert [p.name for p in adir.iterdir()] == [body["file"]]
    assert body["state"]["charts"][0]["samples"][0]["members"] == ["b-pc-1"]
    assert body["next_seq"] == 3
    assert client.get("/annotations").json()["state"] == body["state"]


def test_reads_carry_the_membership_defaults_set_in_one_place(snapshot, adir):
    """界面推断成员框用的 GAP、NEAR 由读路由带出,值就是参照实现模块里的那一处设定(读和保存后的读结果都带)。"""
    from path2_web.annotation import membership

    client = _client(snapshot, adir)
    want = {"gap": membership.GAP, "near": membership.NEAR}
    assert client.get("/annotations").json()["membership"] == want
    r = client.post("/annotations/batch", json={"ops": [_box("b-pc-1", "2025-12-01", "2025-12-05")]})
    assert r.json()["membership"] == want


def test_append_violation_is_rejected_with_reasons(snapshot, adir):
    client = _client(snapshot, adir)
    client.post("/annotations/batch", json={"ops": [_box("b-pc-1", "2025-12-01", "2025-12-05"),
                                                     _sample("s-pc-2", "2025-12-08", ["b-pc-1"])]})
    files = sorted(p.name for p in adir.iterdir())
    base = client.get("/annotations").json()["revs"]["box"]["b-pc-1"]
    r = client.post("/annotations/batch", json={"ops": [_box("b-pc-1", "2025-12-01", "2025-12-10", base=base)]})
    assert r.status_code == 400
    [reason] = r.json()["detail"]["reasons"]
    assert (reason["code"], reason["sample"], reason["box"]) == ("box_crosses_sample_date", "s-pc-2", "b-pc-1")
    r = client.post("/annotations/batch", json={"ops": [_sample("s-pc-3", "2025-12-03", ["b-pc-1"])]})
    assert r.status_code == 400
    assert r.json()["detail"]["reasons"][0]["code"] == "member_crosses_sample_date"
    r = client.post("/annotations/batch", json={"ops": [], "extra": 1})
    assert r.status_code == 400
    assert sorted(p.name for p in adir.iterdir()) == files


def test_read_reports_conflict_and_fingerprint_mismatch(snapshot, adir, tmp_path):
    other = tmp_path / "other_snapshot"
    other.mkdir()
    (other / "BBB.pkl").write_bytes(b"not the same data")
    write_manifest(other)
    pc = {"annotation_dir": str(adir), "machine": "pc", **data_cfg(snapshot)}
    upc = {"annotation_dir": str(adir), "machine": "upc", **data_cfg(other)}
    store.append_batch(pc, [_box("b-pc-1", "2025-12-01", "2025-12-05")])
    base = store.read_annotations(pc)["revs"]["box"]["b-pc-1"]
    store.append_batch(pc, [_box("b-pc-1", "2025-12-01", "2025-12-04", base=base)])
    store.append_batch(upc, [_box("b-pc-1", "2025-12-02", "2025-12-05", base=base)])   # 没看到 pc 的第二次修改

    body = _client(snapshot, adir).get("/annotations").json()
    [conflict] = body["conflicts"]
    assert (conflict["kind"], conflict["id"]) == ("box", "b-pc-1")
    assert (conflict["later"]["machine"], conflict["earlier"]["machine"]) == ("upc", "pc")
    assert body["fingerprint"]["consistent"] is False
    assert body["state"]["charts"][0]["boxes"] == [{"id": "b-pc-1", "feature": None,
                                                    "start": "2025-12-02", "end": "2025-12-05"}]


def test_annotation_dir_missing_is_503(snapshot, tmp_path):
    client = _client(snapshot, tmp_path / "missing")
    assert client.get("/annotations").status_code == 503
    assert client.post("/annotations/batch", json={"ops": [_box("b-pc-1", "2025-12-01", "2025-12-05")]}) \
        .status_code == 503
    assert not (tmp_path / "missing").exists()


def test_routes_never_read_market_data_nor_return_2026(snapshot, adir, monkeypatch):
    def _forbidden(*a, **k):
        raise AssertionError("标注路由读了行情")

    monkeypatch.setattr(pd, "read_pickle", _forbidden)
    monkeypatch.setattr("path2_web.data.read_bars", _forbidden)
    monkeypatch.setattr("path2_web.api.read_bars", _forbidden)
    client = _client(snapshot, adir)

    r = client.post("/annotations/batch", json={"ops": [_box("b-pc-1", "2025-12-29", "2026-01-05")]})
    assert r.status_code == 400 and "2025-12-31" in r.json()["detail"]["reasons"][0]["message"]
    r = client.post("/annotations/batch", json={"ops": [_box("b-pc-1", "2025-12-29", "2025-12-31"),
                                                         _sample("s-pc-2", "2025-12-31", ["b-pc-1"])]})
    assert r.status_code == 200
    for body in (r.json(), client.get("/annotations").json()):
        dates = _dates(body)
        assert dates and max(dates) <= TRAIN_END
