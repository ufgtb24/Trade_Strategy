"""标注的两个路由:GET /annotations(重放出的当前状态)、POST /annotations/batch(追加一批操作);
以及反馈状态 GET /feedback/status、自上次以来的变化 GET /annotations/changes(文件末尾一节)。

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


def _feedback(oid, start, end, base=None, **extra):
    return {"kind": "feedback", "id": oid, "base": base,
            "value": {"id": oid, "symbol": "AAA", "pattern": "new_step", "app_id": "new_step",
                      "app_ver": "0123456789abcdef", "start": start, "end": end, "target": "range",
                      "source": "picked", "answer": "off_pattern", "nodes": ["plateau"], **extra}}


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


def test_reads_carry_the_match_tolerance_set_in_one_place(snapshot, adir):
    """界面判 match、子框对子段用的容差由读路由带出,值就是 path2_web/annotation/match.py 里的那一处设定(spec 第 10 节)。"""
    from path2_web.annotation import match

    client = _client(snapshot, adir)
    want = {"pos": match.POS_TOL, "neg": match.NEG_TOL, "sub": match.SUB_TOL}
    assert client.get("/annotations").json()["match"] == want
    r = client.post("/annotations/batch", json={"ops": [_box("b-pc-1", "2025-12-01", "2025-12-05")]})
    assert r.json()["match"] == want


def test_feedback_round_trip_and_machines(snapshot, adir):
    """反馈经保存路由写进去、读路由读出来挂在这只股票下;读结果带 machines;范围晚于训练段末日被拒。"""
    client = _client(snapshot, adir)
    fb = _feedback("f-pc-1", "2025-12-01", "2025-12-05")
    r = client.post("/annotations/batch", json={"ops": [fb]})
    assert r.status_code == 200, r.text
    want = {k: v for k, v in fb["value"].items() if k != "symbol"}
    for body in (r.json(), client.get("/annotations").json()):
        assert body["state"]["charts"] == [{"symbol": "AAA", "boxes": [], "samples": [], "feedback": [want]}]
        assert body["machines"] == {"pc": {"through": 1}}
        assert "f-pc-1" in body["revs"]["feedback"]
    files = sorted(p.name for p in adir.iterdir())
    r = client.post("/annotations/batch", json={"ops": [_feedback("f-pc-2", "2025-12-29", "2026-01-05")]})
    assert r.status_code == 400
    assert r.json()["detail"]["reasons"][0]["code"] == "bad_op" and "2025-12-31" in r.text
    assert sorted(p.name for p in adir.iterdir()) == files


def test_feedback_without_answer_saves_through_the_route(snapshot, adir):
    """不带 answer 的反馈(note 必写)经保存路由存得进、读出来没有 answer 键;没写 note 的被拒、不写文件;
    带 answer 的那种随后照样存得进,并能被改写成不带的。"""
    client = _client(snapshot, adir)
    plain = _feedback("f-pc-1", "2025-12-01", "2025-12-05", note="追高了")
    del plain["value"]["answer"]
    r = client.post("/annotations/batch", json={"ops": [plain]})
    assert r.status_code == 200, r.text
    [got] = r.json()["state"]["charts"][0]["feedback"]
    assert got == {k: v for k, v in plain["value"].items() if k != "symbol"} and "answer" not in got

    files = sorted(p.name for p in adir.iterdir())
    bare = _feedback("f-pc-2", "2025-12-08", "2025-12-09")
    del bare["value"]["answer"]
    r = client.post("/annotations/batch", json={"ops": [bare]})
    assert r.status_code == 400
    [reason] = r.json()["detail"]["reasons"]
    assert reason["code"] == "bad_op" and "note" in reason["message"]
    assert sorted(p.name for p in adir.iterdir()) == files

    r = client.post("/annotations/batch", json={"ops": [_feedback("f-pc-2", "2025-12-08", "2025-12-09")]})
    assert r.status_code == 200, r.text
    rewritten = _feedback("f-pc-2", "2025-12-08", "2025-12-09", base=r.json()["revs"]["feedback"]["f-pc-2"], note="补一句")
    del rewritten["value"]["answer"]
    r = client.post("/annotations/batch", json={"ops": [rewritten]})
    assert r.status_code == 200, r.text
    assert all("answer" not in f for f in r.json()["state"]["charts"][0]["feedback"])


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
    monkeypatch.setattr("path2_web.api.load_bars", _forbidden)
    client = _client(snapshot, adir)

    r = client.post("/annotations/batch", json={"ops": [_box("b-pc-1", "2025-12-29", "2026-01-05")]})
    assert r.status_code == 400 and "2025-12-31" in r.json()["detail"]["reasons"][0]["message"]
    r = client.post("/annotations/batch", json={"ops": [_box("b-pc-1", "2025-12-29", "2025-12-31"),
                                                         _sample("s-pc-2", "2025-12-31", ["b-pc-1"])]})
    assert r.status_code == 200
    for body in (r.json(), client.get("/annotations").json()):
        dates = _dates(body)
        assert dates and max(dates) <= TRAIN_END


# ───────────── 反馈状态 GET /feedback/status、自上次以来的变化 GET /annotations/changes ─────────────
# mapping 文件改从临时目录读(<tmp>/mappings/<app>.yaml),不往 path2_apps/ 里写。

@pytest.fixture
def mapping_file(tmp_path, monkeypatch):
    """返回写 mapping 的函数 write(app, text);没写的 app 没有 mapping。"""
    from path2_web import mapping

    mdir = tmp_path / "mappings"
    mdir.mkdir()
    monkeypatch.setattr(mapping, "mapping_path", lambda mod: mdir / f"{mod.__name__.split('.')[-2]}.yaml")

    def write(app: str, text: str):
        (mdir / f"{app}.yaml").write_text(text, encoding="utf-8")
    return write


def _fb(oid, symbol, start, end, target="range", pattern="p", **extra):
    return {"kind": "feedback", "id": oid, "base": None,
            "value": {"id": oid, "symbol": symbol, "pattern": pattern, "app_id": "bo_only",
                      "app_ver": "0123456789abcdef", "start": start, "end": end, "target": target,
                      "source": "picked", "answer": "off_pattern", "nodes": ["bo"], **extra}}


@pytest.fixture
def fake_app(monkeypatch):
    """把状态接口跑 app 的两步换成合成买点:AAA 上有两族,NOPE 读不到行情。返回每次跑 app 的参数记录。"""
    from path2_web.app_run import AppBuys, NoSymbol

    buys = {"AAA": AppBuys(families={"2025-11-10": (), "2025-12-01": ("2025-12-03", "2025-12-04")},
                           event_starts=("2025-11-10", "2025-12-01"), dates=())}
    calls: list = []

    def run_app(mod, cfg, symbol, start, end, params, label_horizon=20):
        calls.append((mod.__name__, symbol, start, end, label_horizon))
        if symbol not in buys:
            raise NoSymbol(f"pkl not found: {symbol}")
        return symbol, None, {"end_node": "bo"}

    monkeypatch.setattr("path2_web.api.run_app", run_app)
    monkeypatch.setattr("path2_web.api.app_buys", lambda res, win, end_node: buys[res])
    return calls


def test_feedback_status_three_states_tags_and_order(snapshot, adir, mapping_file, fake_app):
    """三态各一例(point / range / family 的 matched、unmatched、起点认不出),挂「定义改过」的 matched 不算朱红,
    读不到行情的股票那一条 status 为 null、其余照常;别的 pattern 的反馈不在内。页面上只给 matched / unmatched:
    起点认不出的并进 unmatched,会话给它挂了标签的照样带标签(毛病还在);已经不买的(f-pc-2)即使会话段里
    留着标签也不带。按朱红、不买了却挂着标签的、其余排。
    跑 app 的区间是全历史到训练段末日、label_horizon 20(与 compare 的图一致)。"""
    mapping_file("bo_only", "pattern: p\nfeatures: {w-pc-1: bo}\n"
                            "session: {tags: {f-pc-5: redefined, f-pc-3: for_tuning, f-pc-2: unhandled}}\n")
    store.append_batch({"annotation_dir": str(adir), "machine": "pc"}, [
        _fb("f-pc-1", "AAA", "2025-12-03", "2025-12-03", target="point"),           # 当天有买点 → matched
        _fb("f-pc-2", "AAA", "2025-12-08", "2025-12-10"),                            # 范围里没有 → unmatched
        _fb("f-pc-3", "AAA", "2025-12-10", "2025-12-12", target="family",
            family_start="2025-11-20"),                                              # 起点认不出 → 显示 unmatched
        _fb("f-pc-4", "AAA", "2025-12-15", "2025-12-16", target="family",
            family_start="2025-11-10"),                                              # 起点还在、不买 → unmatched
        _fb("f-pc-5", "AAA", "2025-12-04", "2025-12-04", target="point"),           # matched,但定义改过
        _fb("f-pc-6", "NOPE", "2025-12-04", "2025-12-04", target="point"),          # 读不到行情
        _fb("f-pc-7", "AAA", "2025-12-20", "2025-12-22", target="family",
            family_start="2025-12-01"),                                              # 同起点的族还在买 → matched
        _fb("f-pc-8", "AAA", "2025-12-03", "2025-12-03", target="point", pattern="q"),   # 别的 pattern
    ])
    from path2_web.app_version import app_ver
    import path2_apps.bo_only.dag_spec as bo_only

    body = _client(snapshot, adir).get("/feedback/status", params={"pattern": "p"}).json()
    assert (body["app"], body["app_ver"], body["reason"]) == ("bo_only", app_ver(bo_only), None)
    got = [(i["id"], i["status"], i["tag"], i["red"]) for i in body["items"]]
    assert got == [("f-pc-1", "matched", None, True), ("f-pc-7", "matched", None, True),
                   ("f-pc-3", "unmatched", "for_tuning", False),
                   ("f-pc-5", "matched", "redefined", False), ("f-pc-2", "unmatched", None, False),
                   ("f-pc-4", "unmatched", None, False), ("f-pc-6", None, None, False)]
    reasons = {i["id"]: i["reason"] for i in body["items"]}
    assert "NOPE" in reasons.pop("f-pc-6") and set(reasons.values()) == {None}
    assert sorted(set(fake_app)) == [("path2_apps.bo_only.dag_spec", s, "1900-01-01", TRAIN_END, 20)
                                     for s in ("AAA", "NOPE")]


def test_feedback_status_cache_by_app_version(snapshot, adir, mapping_file, fake_app, monkeypatch):
    """同一版 app 再问一次不再跑 app;app 换了版本(app_ver 变)重跑。读不到行情的股票不进缓存。"""
    mapping_file("bo_only", "pattern: p\nfeatures: {w-pc-1: bo}\n")
    store.append_batch({"annotation_dir": str(adir), "machine": "pc"}, [
        _fb("f-pc-1", "AAA", "2025-12-03", "2025-12-03", target="point"),
        _fb("f-pc-2", "AAA", "2025-12-08", "2025-12-10")])
    client = _client(snapshot, adir)
    first = client.get("/feedback/status", params={"pattern": "p"}).json()
    assert len(fake_app) == 1
    assert client.get("/feedback/status", params={"pattern": "p"}).json() == first
    assert len(fake_app) == 1
    monkeypatch.setattr("path2_web.api.app_ver", lambda mod: "ffffffffffffffff")
    body = client.get("/feedback/status", params={"pattern": "p"}).json()
    assert len(fake_app) == 2 and body["app_ver"] == "ffffffffffffffff"


def test_feedback_status_without_usable_mapping(snapshot, adir, mapping_file, fake_app):
    """没有 mapping、mapping 有问题、两个 app 写了同一个 pattern:app 为 null、没有条目、写明原因,不跑 app。"""
    store.append_batch({"annotation_dir": str(adir), "machine": "pc"},
                       [_fb("f-pc-1", "AAA", "2025-12-03", "2025-12-03", target="point")])
    client = _client(snapshot, adir)

    def ask():
        return client.get("/feedback/status", params={"pattern": "p"}).json()
    body = ask()
    assert (body["app"], body["app_ver"], body["items"]) == (None, None, []) and "p" in body["reason"]
    mapping_file("bo_only", "pattern: p\nfeatures: {w-pc-1: nope}\n")
    assert ask()["app"] is None and "node not in app" in ask()["reason"]
    mapping_file("bo_only", "pattern: p\nfeatures: {w-pc-1: bo}\n")
    mapping_file("new_step", "pattern: p\nfeatures: {w-pc-1: plateau}\n")
    assert ask()["app"] is None and "several apps" in ask()["reason"]
    assert fake_app == []


def test_preview_and_status_carry_the_same_app_ver(snapshot, adir, mapping_file):
    """单股预览的 scan 元信息带 app_ver(前端存反馈时记进记录),与状态接口给的是同一个值;真跑 bo_only。"""
    from path2_web.app_version import app_ver
    import path2_apps.bo_only.dag_spec as bo_only

    mapping_file("bo_only", "pattern: p\nfeatures: {w-pc-1: bo}\n")
    store.append_batch({"annotation_dir": str(adir), "machine": "pc"},
                       [_fb("f-pc-1", "AAA", "2025-12-03", "2025-12-03", target="point")])
    client = _client(snapshot, adir)
    r = client.get("/preview", params={"pattern_id": "bo_only", "symbol": "AAA", "start": "1900-01-01",
                                       "end": TRAIN_END, "label_horizon": 20})
    assert r.status_code == 200, r.text
    assert r.json()["scan"]["app_ver"] == app_ver(bo_only)
    body = client.get("/feedback/status", params={"pattern": "p"}).json()
    assert body["app_ver"] == app_ver(bo_only)
    [item] = body["items"]
    assert item["status"] in ("matched", "unmatched") and item["reason"] is None


def _pos(oid, date, members=(), pattern="p", judgment="pos", base=None):
    return {"kind": "sample", "id": oid, "base": base,
            "value": {"id": oid, "symbol": "AAA", "date": date, "pattern": pattern, "judgment": judgment,
                      "members": list(members)}}


def test_changes_since_session_snapshot(snapshot, adir, mapping_file):
    """定格 {pc: 1} 之后的修改:改判、新增样本、成员框挪边、pattern 定义改动都报出来;since 是定格的 seen。"""
    pc = {"annotation_dir": str(adir), "machine": "pc"}
    store.append_batch(pc, [{"kind": "pattern", "id": "p", "base": None, "value": {"name": "p", "definition": "旧"}},
                            _box("b-pc-1", "2025-12-01", "2025-12-05"),
                            _pos("s-pc-2", "2025-12-08", ["b-pc-1"])])
    revs = store.read_annotations(pc)["revs"]
    store.append_batch(pc, [
        {"kind": "pattern", "id": "p", "base": revs["pattern"]["p"], "value": {"name": "p", "definition": "新"}},
        _box("b-pc-1", "2025-12-02", "2025-12-05", base=revs["box"]["b-pc-1"]),
        _pos("s-pc-2", "2025-12-08", ["b-pc-1"], judgment="neg", base=revs["sample"]["s-pc-2"]),
        _pos("s-pc-3", "2025-12-10")])
    mapping_file("bo_only", "pattern: p\nfeatures: {w-pc-1: bo}\n"
                            "session: {snapshot: {seen: {pc: 1}, samples: [s-pc-2]}}\n")
    body = _client(snapshot, adir).get("/annotations/changes", params={"pattern": "p"}).json()
    assert body["since"] == {"pc": 1} and body["reason"] is None
    assert [(c["kind"], c["id"], c["change"]) for c in body["changes"]] == [
        ("pattern", "p", "definition"), ("sample", "s-pc-2", "judgment"), ("sample", "s-pc-3", "added"),
        ("box", "b-pc-1", "start")]


def test_changes_without_snapshot(snapshot, adir, mapping_file):
    """没有定格时 since 为 null、没有变化、写明原因:没有 mapping、没有会话段、会话段写坏了、会话段里没有 snapshot。
    mapping 自身的问题(node 不在 app 里)不妨碍读定格。"""
    client = _client(snapshot, adir)

    def ask():
        return client.get("/annotations/changes", params={"pattern": "p"}).json()
    body = ask()
    assert body["since"] is None and body["changes"] == [] and "no app" in body["reason"]
    for text, why in (("", "no session snapshot"), ("session: {tags: {f-pc-1: accepted}}\n", "no session snapshot"),
                      ("session: {snapshot: {seen: {pc: -1}, samples: []}}\n", "session.snapshot.seen")):
        mapping_file("bo_only", "pattern: p\nfeatures: {w-pc-1: bo}\n" + text)
        body = ask()
        assert body["since"] is None and body["changes"] == [] and why in body["reason"]
    mapping_file("bo_only", "pattern: p\nfeatures: {w-pc-1: nope}\nsession: {snapshot: {seen: {pc: 0}, samples: []}}\n")
    assert ask() == {"since": {"pc": 0}, "changes": [], "reason": None}


def test_feedback_status_missing_data_dir_is_503(adir, mapping_file, tmp_path):
    """行情目录整个不在:整体 503(同单股预览),不是逐条 status null;真跑 bo_only,不换替身。"""
    mapping_file("bo_only", "pattern: p\nfeatures: {w-pc-1: bo}\n")
    store.append_batch({"annotation_dir": str(adir), "machine": "pc"},
                       [_fb("f-pc-1", "AAA", "2025-12-03", "2025-12-03", target="point")])
    r = _client(tmp_path / "no_such_dir", adir).get("/feedback/status", params={"pattern": "p"})
    assert r.status_code == 503 and "no_such_dir" in r.json()["detail"]
