"""标注存储(path2_web/annotation/store.py)。

钉住的要求:
- 两台机器的文件交错重放,结果与文件的列举顺序无关,两台读出同一个状态;
- 两台各自新建的对象不撞号;重放以后,新编号接在本机最大序号之后(删掉的号也不复用);
- 任何一次保存都只新增一个文件,已有文件的内容哈希不变;没通过的保存一个文件都不写;
- 同一个对象被两台机器在同步前各改一次:后改的那次生效,冲突被记下、说得清是哪个对象;
  只同步到一半(某条修改依据的文件还没到)时不报假冲突,记成 unsynced,同步完就消失;
- 写的人看到过的修改一定排在它前面(两台机器的钟不准也一样);
- 两种因果违规(成员框终点晚于样本日、改框起止越过所属样本的样本日)被拒绝并报出原因;
  四种正常操作(不越界地改框起止、删样本、改名、合并)照常通过;
- 指纹对不上(或本机读不到指纹)时,读结果标出不符,状态照常返回;状态里的 data_fingerprint 是标注所依据的
  指纹(各批一致时),不是本机的;
- 旧文件读出来逐条不变:fixtures/annotation_store_v1 是一组固定的批次文件,重放结果必须与同目录
  expected.json 逐条一致。以后改格式时这组文件和期望都不许改,新版要原样读出它们(spec 4.5);
- 反馈(kind feedback):三种 target 写进去、重放出来原样;每条取值规则各有一例被拒;没有反馈的股票不出
  feedback 键,只有反馈的股票照样在 charts 里;
- 盲看标记(source 不是 picked 的反馈)保存时改不了、删不掉,别的操作照常;绕过保存(同步来的)删改,读结果
  的 violations 列出来、数据不改;
- 会话定格:machines.through 是每台机器从 1 起连续到齐的序号,缺号时停在缺口前;as_of 截出的状态等于
  「只重放到截止序号的批次」,没缺口时就是当时的状态。
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import random
import shutil
from pathlib import Path

import pytest

from path2_web.annotation import store
from path2_web.snapshot_fingerprint import write_manifest

FIXTURE = Path(__file__).parent / "fixtures" / "annotation_store_v1"
UTC = dt.timezone.utc


# ---------------------------------------------------------------- 搭场景的小工具

def _at(hh: int, mm: int = 0) -> dt.datetime:
    """2026-11-03 hh:mm UTC(保存时刻,不是行情日期)。"""
    return dt.datetime(2026, 11, 3, hh, mm, tzinfo=UTC)


def _snapshot(root: Path, name: str, payload: bytes) -> tuple[Path, str]:
    """一个只含一个假 pkl 的训练段副本目录(只为算指纹,内容不是行情),写好指纹清单。"""
    d = root / name
    d.mkdir()
    (d / "AAA.pkl").write_bytes(payload)
    return d, write_manifest(d)["fingerprint"]


def _cfg(adir: Path, machine: str, snapshot: Path | None = None) -> dict:
    cfg = {"annotation_dir": str(adir), "machine": machine}
    if snapshot is not None:
        cfg["view_dataset_dir"] = str(snapshot)
    return cfg


def _adir(root: Path, name: str = "annotations") -> Path:
    d = root / name
    d.mkdir()
    return d


def _op(kind, oid, value, base=None):
    return {"kind": kind, "id": oid, "base": base, "value": value}


def _feature(oid, name, base=None, **extra):
    return _op("feature", oid, {"id": oid, "name": name, **extra}, base)


def _box(oid, start, end, feature=None, symbol="AAPL", base=None, **extra):
    return _op("box", oid, {"id": oid, "symbol": symbol, "feature": feature, "start": start, "end": end, **extra},
               base)


def _sample(oid, date, members, symbol="AAPL", pattern="W底", judgment="pos", base=None, **extra):
    return _op("sample", oid, {"id": oid, "symbol": symbol, "date": date, "pattern": pattern, "judgment": judgment,
                               "members": members, **extra}, base)


def _feedback(oid, start, end=None, target="point", source="picked", answer="neg", note="不该买", symbol="AAPL",
              base=None, **extra):
    """一条反馈;缺省是合法的 point / picked / neg。note=None 表示不带 note;extra 可覆盖任何字段。"""
    v = {"id": oid, "symbol": symbol, "pattern": "new_step", "app_id": "new_step", "app_ver": "0123456789abcdef",
         "start": start, "end": end or start, "target": target, "source": source, "answer": answer}
    if note is not None:
        v["note"] = note
    return _op("feedback", oid, {**v, **extra}, base)


def _write_raw(adir: Path, machine: str, ts: str, seq: int, ops: list[dict]) -> str:
    """绕过保存校验直接写一个批次文件(模拟同步来的、没经过本机校验的修改),返回文件名。"""
    name = f"{machine}-{ts}-{seq}.json"
    doc = {"schema": store.SCHEMA, "data_fingerprint": None,
           "ops": [{"ts": ts, "machine": machine, **op} for op in ops]}
    (adir / name).write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return name


def _delete(kind, oid, base):
    return _op(kind, oid, None, base)


def _rev(cfg, kind, oid):
    return store.read_annotations(cfg)["revs"][kind][oid]


def _boxes(cfg, symbol="AAPL") -> dict:
    charts = {c["symbol"]: c for c in store.read_annotations(cfg)["state"]["charts"]}
    return {b["id"]: b for b in charts[symbol]["boxes"]}


def _hashes(adir: Path) -> dict:
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in adir.iterdir()}


def _sync(a: Path, b: Path) -> None:
    """模拟 Syncthing 同步完:两个目录互相补齐对方有、自己没有的文件(不改已有文件)。"""
    for src, dst in ((a, b), (b, a)):
        for p in src.iterdir():
            if not (dst / p.name).exists():
                shutil.copy2(p, dst / p.name)


def _drop_machine(result: dict) -> dict:
    """读结果里只有 state.machine 随读的机器而变,去掉它再比两台的结果。"""
    out = json.loads(json.dumps(result))
    del out["state"]["machine"]
    del out["next_seq"]
    return out


# ---------------------------------------------------------------- 旧文件读出来逐条不变

def test_golden_v1_replays_to_fixed_state():
    got = store.read_annotations(_cfg(FIXTURE / "batches", "pc"))
    expected = json.loads((FIXTURE / "expected.json").read_text(encoding="utf-8"))
    assert got["state"] == expected["state"]
    assert got["conflicts"] == expected["conflicts"]
    assert got["unsynced"] == expected["unsynced"]
    assert got["violations"] == expected["violations"]
    assert got["next_seq"] == expected["next_seq"]
    assert got["fingerprint"]["recorded"] == expected["recorded_fingerprints"]
    assert got["ignored_files"] == expected["ignored_files"]


# ---------------------------------------------------------------- 重放确定

def _two_machine_history(tmp_path) -> tuple[Path, Path]:
    """pc、upc 各自标注、交错同步,含一次冲突、改名、合并、删除。返回同步完的两个标注目录。"""
    pc_dir, upc_dir = _adir(tmp_path, "pc"), _adir(tmp_path, "upc")
    pc, upc = _cfg(pc_dir, "pc"), _cfg(upc_dir, "upc")
    store.append_batch(pc, [_feature("w-pc-1", "放量"), _box("b-pc-2", "2024-03-01", "2024-03-05", "w-pc-1"),
                            _sample("s-pc-3", "2024-03-08", ["b-pc-2"])], now=_at(9))
    store.append_batch(upc, [_feature("w-upc-1", "缩量"), _box("b-upc-2", "2023-05-01", "2023-05-20", "w-upc-1",
                                                               symbol="MSFT")], now=_at(9, 5))
    _sync(pc_dir, upc_dir)
    base = _rev(pc, "box", "b-pc-2")
    store.append_batch(pc, [_box("b-pc-2", "2024-03-01", "2024-03-04", "w-pc-1", base=base)], now=_at(9, 10))
    store.append_batch(upc, [_box("b-pc-2", "2024-03-02", "2024-03-05", "w-pc-1", base=base, note="upc 改的")],
                       now=_at(9, 20))
    store.append_batch(upc, [_box("b-upc-2", "2023-05-01", "2023-05-20", "w-pc-1", symbol="MSFT",
                                  base=_rev(upc, "box", "b-upc-2")),
                             _delete("feature", "w-upc-1", _rev(upc, "feature", "w-upc-1"))], now=_at(9, 25))
    _sync(pc_dir, upc_dir)
    store.append_batch(pc, [_feature("w-pc-1", "放量突破", base=_rev(pc, "feature", "w-pc-1"))], now=_at(9, 30))
    _sync(pc_dir, upc_dir)
    return pc_dir, upc_dir


def test_replay_independent_of_listing_order(tmp_path, monkeypatch):
    pc_dir, _ = _two_machine_history(tmp_path)
    for adir in (pc_dir, FIXTURE / "batches"):
        cfg = _cfg(adir, "pc")
        baseline = store.read_annotations(cfg)
        names = sorted(p.name for p in adir.iterdir())
        rng = random.Random(0)
        for _ in range(20):
            shuffled = names[:]
            rng.shuffle(shuffled)
            monkeypatch.setattr(store, "_list_names", lambda d, s=shuffled: list(s))
            assert store.read_annotations(cfg) == baseline
        monkeypatch.undo()


def test_both_machines_replay_to_same_state(tmp_path):
    pc_dir, upc_dir = _two_machine_history(tmp_path)
    assert sorted(p.name for p in pc_dir.iterdir()) == sorted(p.name for p in upc_dir.iterdir())
    pc = store.read_annotations(_cfg(pc_dir, "pc"))
    upc = store.read_annotations(_cfg(upc_dir, "upc"))
    assert _drop_machine(pc) == _drop_machine(upc)
    assert (pc["state"]["machine"], upc["state"]["machine"]) == ("pc", "upc")
    # 合并:b-upc-2 改挂 w-pc-1,w-upc-1 已删;改名生效
    assert pc["state"]["features"] == [{"id": "w-pc-1", "name": "放量突破"}]
    assert pc["state"]["charts"][1]["boxes"][0]["feature"] == "w-pc-1"


# ---------------------------------------------------------------- 编号

def test_ids_from_two_machines_never_collide_and_counter_continues(tmp_path):
    adir = _adir(tmp_path)
    pc, upc = _cfg(adir, "pc"), _cfg(adir, "upc")
    assert store.read_annotations(pc)["next_seq"] == 1
    store.append_batch(pc, [_feature("w-pc-1", "放量"), _box("b-pc-2", "2024-03-01", "2024-03-05", "w-pc-1")])
    store.append_batch(upc, [_feature("w-upc-1", "放量"), _box("b-upc-2", "2024-03-01", "2024-03-05", "w-upc-1")])
    state = store.read_annotations(pc)["state"]
    assert [f["id"] for f in state["features"]] == ["w-pc-1", "w-upc-1"]
    assert sorted(_boxes(pc)) == ["b-pc-2", "b-upc-2"]
    assert store.read_annotations(pc)["next_seq"] == 3
    assert store.read_annotations(upc)["next_seq"] == 3

    store.append_batch(pc, [_delete("box", "b-pc-2", _rev(pc, "box", "b-pc-2"))])
    assert store.read_annotations(pc)["next_seq"] == 3          # 删掉的号不复用

    with pytest.raises(store.BatchRejected) as e:              # 用过的号当新建再用
        store.append_batch(pc, [_box("b-pc-2", "2024-04-01", "2024-04-02")])
    assert [r["code"] for r in e.value.reasons] == ["id_taken"]
    with pytest.raises(store.BatchRejected) as e:              # 新建别的机器的号
        store.append_batch(upc, [_box("b-pc-9", "2024-04-01", "2024-04-02")])
    assert [r["code"] for r in e.value.reasons] == ["bad_new_id"]


# ---------------------------------------------------------------- 只新增文件

def test_saving_only_adds_files(tmp_path):
    adir = _adir(tmp_path)
    cfg = _cfg(adir, "pc")
    steps = [
        lambda: [_feature("w-pc-1", "放量"), _feature("w-pc-2", "爆量"),
                 _box("b-pc-3", "2024-03-01", "2024-03-05", "w-pc-1"),
                 _box("b-pc-4", "2024-03-06", "2024-03-08", "w-pc-2", attrs={"w-pc-1": True}),
                 _sample("s-pc-5", "2024-03-08", ["b-pc-3", "b-pc-4"])],
        lambda: [_feature("w-pc-1", "放量突破", base=_rev(cfg, "feature", "w-pc-1"))],                   # 改名
        lambda: [_box("b-pc-4", "2024-03-06", "2024-03-08", "w-pc-1", attrs={},                           # 合并
                      base=_rev(cfg, "box", "b-pc-4")),
                 _delete("feature", "w-pc-2", _rev(cfg, "feature", "w-pc-2"))],
        lambda: [_box("b-pc-3", "2024-03-02", "2024-03-05", "w-pc-1", base=_rev(cfg, "box", "b-pc-3"))],  # 拖框
        lambda: [_delete("sample", "s-pc-5", _rev(cfg, "sample", "s-pc-5"))],                             # 删样本
    ]
    for make_ops in steps:
        before = _hashes(adir)
        name = store.append_batch(cfg, make_ops())
        after = _hashes(adir)
        assert set(after) == set(before) | {name} and name not in before
        assert {k: after[k] for k in before} == before

    before = _hashes(adir)
    with pytest.raises(store.BatchRejected):                    # 没通过的保存一个文件都不写
        store.append_batch(cfg, [_sample("s-pc-6", "2024-03-03", ["b-pc-3"])])
    assert _hashes(adir) == before


# ---------------------------------------------------------------- 冲突

@pytest.mark.parametrize("pc_time, upc_time, winner", [((9, 10), (9, 20), "upc"), ((9, 20), (9, 10), "pc")])
def test_concurrent_edits_later_wins_and_conflict_is_reported(tmp_path, pc_time, upc_time, winner):
    pc_dir, upc_dir = _adir(tmp_path, "pc"), _adir(tmp_path, "upc")
    pc, upc = _cfg(pc_dir, "pc"), _cfg(upc_dir, "upc")
    store.append_batch(pc, [_box("b-pc-1", "2024-03-01", "2024-03-05")], now=_at(9))
    _sync(pc_dir, upc_dir)
    base = _rev(pc, "box", "b-pc-1")
    # 同步前各改一次
    store.append_batch(pc, [_box("b-pc-1", "2024-03-01", "2024-03-05", note="pc", base=base)], now=_at(*pc_time))
    store.append_batch(upc, [_box("b-pc-1", "2024-03-01", "2024-03-05", note="upc", base=base)],
                       now=_at(*upc_time))
    _sync(pc_dir, upc_dir)
    for cfg in (pc, upc):
        result = store.read_annotations(cfg)
        assert _boxes(cfg)["b-pc-1"]["note"] == winner
        [conflict] = result["conflicts"]
        assert (conflict["kind"], conflict["id"], conflict["base"]) == ("box", "b-pc-1", base)
        loser = "pc" if winner == "upc" else "upc"
        assert (conflict["later"]["machine"], conflict["earlier"]["machine"]) == (winner, loser)


def test_half_synced_edit_is_unsynced_not_a_conflict(tmp_path):
    """upc 连改两次;pc 先只收到第二次的文件:不报冲突,记成 unsynced;第一次的文件到了以后两者都为空。"""
    pc_dir, upc_dir = _adir(tmp_path, "pc"), _adir(tmp_path, "upc")
    pc, upc = _cfg(pc_dir, "pc"), _cfg(upc_dir, "upc")
    store.append_batch(pc, [_box("b-pc-1", "2024-03-01", "2024-03-05")], now=_at(9))
    _sync(pc_dir, upc_dir)
    first = store.append_batch(upc, [_box("b-pc-1", "2024-03-01", "2024-03-04", base=_rev(upc, "box", "b-pc-1"))],
                               now=_at(9, 10))
    second = store.append_batch(upc, [_box("b-pc-1", "2024-03-01", "2024-03-03", base=_rev(upc, "box", "b-pc-1"))],
                                now=_at(9, 20))
    shutil.copy2(upc_dir / second, pc_dir / second)
    half = store.read_annotations(pc)
    assert half["conflicts"] == []
    assert half["unsynced"] == [{"kind": "box", "id": "b-pc-1", "base": f"{first[:-5]}#0", "ref": f"{second[:-5]}#0"}]
    _sync(pc_dir, upc_dir)
    full = store.read_annotations(pc)
    assert full["conflicts"] == [] and full["unsynced"] == []
    assert _boxes(pc)["b-pc-1"]["end"] == "2024-03-03"


def test_edit_based_on_seen_change_is_ordered_after_it_despite_clock_skew(tmp_path):
    """upc 的钟比 pc 快:pc 看到 upc 的修改后再改,它的修改仍排在后面、生效,不算冲突。"""
    adir = _adir(tmp_path)
    pc, upc = _cfg(adir, "pc"), _cfg(adir, "upc")
    store.append_batch(upc, [_box("b-upc-1", "2024-03-01", "2024-03-05", note="upc")], now=_at(10))
    name = store.append_batch(pc, [_box("b-upc-1", "2024-03-01", "2024-03-05", note="pc",
                                        base=_rev(pc, "box", "b-upc-1"))], now=_at(9, 55))
    assert name.split("-")[1] > "20261103T100000.000Z"
    assert _boxes(pc)["b-upc-1"]["note"] == "pc"
    assert store.read_annotations(pc)["conflicts"] == []


def test_combined_edits_crossing_sample_date_are_listed_not_changed(tmp_path):
    """两台各自合规的修改,合起来让成员框越过了样本日:读结果列在 violations 里,数据照原样。"""
    pc_dir, upc_dir = _adir(tmp_path, "pc"), _adir(tmp_path, "upc")
    pc, upc = _cfg(pc_dir, "pc"), _cfg(upc_dir, "upc")
    store.append_batch(pc, [_box("b-pc-1", "2024-03-01", "2024-03-05")], now=_at(9))
    _sync(pc_dir, upc_dir)
    store.append_batch(pc, [_sample("s-pc-2", "2024-03-08", ["b-pc-1"])], now=_at(9, 10))
    store.append_batch(upc, [_box("b-pc-1", "2024-03-01", "2024-03-12", base=_rev(upc, "box", "b-pc-1"))],
                       now=_at(9, 20))
    _sync(pc_dir, upc_dir)
    result = store.read_annotations(pc)
    assert [(v["code"], v["sample"], v["box"]) for v in result["violations"]] == \
        [("member_crosses_sample_date", "s-pc-2", "b-pc-1")]
    assert _boxes(pc)["b-pc-1"]["end"] == "2024-03-12"


# ---------------------------------------------------------------- 因果校验

@pytest.fixture
def one_sample(tmp_path):
    """一张图:框 b-pc-1(03-01～03-05)是样本 s-pc-2(样本日 03-08)的成员;框 b-pc-3(03-10～03-12)不是任何样本的成员。"""
    cfg = _cfg(_adir(tmp_path), "pc")
    store.append_batch(cfg, [_feature("w-pc-4", "放量"), _feature("w-pc-5", "缩量"),
                             _box("b-pc-1", "2024-03-01", "2024-03-05", "w-pc-4"),
                             _box("b-pc-3", "2024-03-10", "2024-03-12", "w-pc-5", attrs={"w-pc-4": False}),
                             _sample("s-pc-2", "2024-03-08", ["b-pc-1"])])
    return cfg


def test_rejects_member_ending_after_sample_date(one_sample):
    cfg = one_sample
    with pytest.raises(store.BatchRejected) as e:
        store.append_batch(cfg, [_sample("s-pc-6", "2024-03-11", ["b-pc-3"])])
    [reason] = e.value.reasons
    assert (reason["code"], reason["sample"], reason["box"]) == ("member_crosses_sample_date", "s-pc-6", "b-pc-3")
    assert "2024-03-12" in reason["message"] and "2024-03-11" in reason["message"]

    with pytest.raises(store.BatchRejected) as e:              # 把样本日挪到成员框终点之前也一样
        store.append_batch(cfg, [_sample("s-pc-2", "2024-03-04", ["b-pc-1"], base=_rev(cfg, "sample", "s-pc-2"))])
    assert [r["code"] for r in e.value.reasons] == ["member_crosses_sample_date"]


@pytest.mark.parametrize("start, end", [("2024-03-01", "2024-03-09"), ("2024-03-09", "2024-03-12")])
def test_rejects_box_edit_crossing_its_sample_date(one_sample, start, end):
    cfg = one_sample
    with pytest.raises(store.BatchRejected) as e:
        store.append_batch(cfg, [_box("b-pc-1", start, end, "w-pc-4", base=_rev(cfg, "box", "b-pc-1"))])
    [reason] = e.value.reasons
    assert (reason["code"], reason["sample"], reason["box"]) == ("box_crosses_sample_date", "s-pc-2", "b-pc-1")
    assert "2024-03-08" in reason["message"]


def test_rejects_deleting_member_box_left_in_sample(one_sample):
    cfg = one_sample
    with pytest.raises(store.BatchRejected) as e:
        store.append_batch(cfg, [_delete("box", "b-pc-1", _rev(cfg, "box", "b-pc-1"))])
    assert [(r["code"], r["sample"], r["box"]) for r in e.value.reasons] == [("member_missing", "s-pc-2", "b-pc-1")]
    # 同一批把它从样本成员里拿掉就放行
    store.append_batch(cfg, [_delete("box", "b-pc-1", _rev(cfg, "box", "b-pc-1")),
                             _sample("s-pc-2", "2024-03-08", [], base=_rev(cfg, "sample", "s-pc-2"),
                                     members_edited=True)])


def test_normal_operations_pass(one_sample):
    cfg = one_sample
    # 不越界地改框起止:终点挪到样本日当天、起点往前
    store.append_batch(cfg, [_box("b-pc-1", "2024-02-26", "2024-03-08", "w-pc-4", base=_rev(cfg, "box", "b-pc-1"))])
    # 越过的是别的样本的样本日、它又不是那个样本的成员:放行
    store.append_batch(cfg, [_box("b-pc-3", "2024-03-06", "2024-03-12", "w-pc-5", attrs={"w-pc-4": False},
                                  base=_rev(cfg, "box", "b-pc-3"))])
    # 改名
    store.append_batch(cfg, [_feature("w-pc-4", "放量突破", base=_rev(cfg, "feature", "w-pc-4"))])
    # 合并:把 w-pc-5 并进 w-pc-4(框改挂、属性搬过去),删掉 w-pc-5
    store.append_batch(cfg, [_box("b-pc-3", "2024-03-06", "2024-03-12", "w-pc-4", base=_rev(cfg, "box", "b-pc-3")),
                             _delete("feature", "w-pc-5", _rev(cfg, "feature", "w-pc-5"))])
    # 删样本;之后它的旧成员框可以拖过原来的样本日
    store.append_batch(cfg, [_delete("sample", "s-pc-2", _rev(cfg, "sample", "s-pc-2"))])
    store.append_batch(cfg, [_box("b-pc-1", "2024-02-26", "2024-03-20", "w-pc-4", base=_rev(cfg, "box", "b-pc-1"))])

    result = store.read_annotations(cfg)
    assert result["conflicts"] == [] and result["violations"] == []
    assert result["state"]["features"] == [{"id": "w-pc-4", "name": "放量突破"}]
    chart = result["state"]["charts"][0]
    assert chart["samples"] == []
    assert [(b["id"], b["feature"], b["start"], b["end"]) for b in chart["boxes"]] == \
        [("b-pc-1", "w-pc-4", "2024-02-26", "2024-03-20"), ("b-pc-3", "w-pc-4", "2024-03-06", "2024-03-12")]


@pytest.mark.parametrize("ops, code", [
    ([_box("b-pc-1", "2025-12-30", "2026-01-05")], "bad_op"),                         # 晚于训练段末日
    ([_box("b-pc-1", "2024-03-05", "2024-03-01")], "bad_op"),                         # 起点晚于终点
    ([_box("b-pc-1", "2024-02-30", "2024-03-01")], "bad_op"),                         # 不存在的日期
    ([_box("b-pc-1", "2024-03-01", "2024-03-05", detach=True, attach="b-pc-9")], "bad_op"),
    ([_sample("s-pc-1", "2024-03-05", [], judgment="maybe")], "bad_op"),
    ([_box("b-pc-1", "2024-03-01", "2024-03-05", color="red")], "bad_op"),           # 多出的键
    ([_box("b-pc-1", "2024-03-01", "2024-03-05", symbol="../x")], "bad_op"),
    ([_op("box", "w-pc-1", {"id": "w-pc-1"})], "bad_op"),                             # 编号字母与种类不符
    ([_box("b-pc-1", "2024-03-01", "2024-03-05"), _box("b-pc-1", "2024-03-01", "2024-03-06")], "duplicate_op"),
    ([_delete("box", "b-pc-1", None)], "bad_op"),                                     # 删一个从没有过的框
    ([], "bad_op"),
])
def test_rejects_malformed_ops(tmp_path, ops, code):
    adir = _adir(tmp_path)
    with pytest.raises(store.BatchRejected) as e:
        store.append_batch(_cfg(adir, "pc"), ops)
    assert code in {r["code"] for r in e.value.reasons}
    assert list(adir.iterdir()) == []


# ---------------------------------------------------------------- 指纹

def test_fingerprint_mismatch_is_flagged_and_state_still_returned(tmp_path):
    snap_a, fp_a = _snapshot(tmp_path, "snap_a", b"a")
    snap_b, fp_b = _snapshot(tmp_path, "snap_b", b"b")
    adir = _adir(tmp_path)
    store.append_batch(_cfg(adir, "pc", snap_a), [_box("b-pc-1", "2024-03-01", "2024-03-05")])
    same = store.read_annotations(_cfg(adir, "pc", snap_a))
    assert same["fingerprint"] == {"local": fp_a, "local_error": None,
                                   "recorded": [{"fingerprint": fp_a, "batches": 1}], "consistent": True}
    assert same["state"]["data_fingerprint"] == fp_a

    other = store.read_annotations(_cfg(adir, "pc", snap_b))
    assert other["fingerprint"]["consistent"] is False
    assert other["fingerprint"]["local"] == fp_b
    assert other["fingerprint"]["recorded"] == [{"fingerprint": fp_a, "batches": 1}]
    assert other["state"]["data_fingerprint"] == fp_a           # 标注依据的是 A,不是本机的 B
    assert other["state"]["charts"] == same["state"]["charts"]

    no_manifest = tmp_path / "snap_c"
    no_manifest.mkdir()
    missing = store.read_annotations(_cfg(adir, "pc", no_manifest))
    assert missing["fingerprint"]["consistent"] is False
    assert missing["fingerprint"]["local"] is None and "FINGERPRINT.json" in missing["fingerprint"]["local_error"]
    assert missing["state"]["charts"] == same["state"]["charts"]


# ---------------------------------------------------------------- 目录与坏文件

def test_missing_annotation_dir_is_reported_not_created(tmp_path):
    cfg = _cfg(tmp_path / "nope", "pc")
    with pytest.raises(store.AnnotationDirMissing):
        store.read_annotations(cfg)
    with pytest.raises(store.AnnotationDirMissing):
        store.append_batch(cfg, [_box("b-pc-1", "2024-03-01", "2024-03-05")])
    assert not (tmp_path / "nope").exists()


def test_unreadable_batch_file_names_the_file(tmp_path):
    adir = _adir(tmp_path)
    (adir / "pc-20261103T090000.000Z-1.json").write_text("{broken", encoding="utf-8")
    with pytest.raises(store.AnnotationFileError, match="pc-20261103T090000.000Z-1.json"):
        store.read_annotations(_cfg(adir, "pc"))


def test_hidden_and_misnamed_files_are_skipped(tmp_path):
    adir = _adir(tmp_path)
    (adir / ".stfolder").mkdir()
    (adir / ".pc-20261103T090000.000Z-1.json.123.tmp").write_text("{", encoding="utf-8")
    (adir / "notes.txt").write_text("x", encoding="utf-8")
    result = store.read_annotations(_cfg(adir, "pc"))
    assert result["ignored_files"] == ["notes.txt"]
    assert result["state"]["charts"] == []


# ---------------------------------------------------------------- 还能拆回的合并

def test_golden_v1_lists_its_merge():
    """例子文件里 upc 把「缩量」并进「回踩」:读出这条合并,带被删的词和那个框改前改后的值。"""
    got = store.read_annotations(_cfg(FIXTURE / "batches", "pc"))["merges"]
    assert [(m["ref"], m["machine"], m["feature"], m["into"]) for m in got] == [
        ("upc-20261103T093000.000Z-2#1", "upc", {"id": "w-upc-1", "name": "缩量"}, "w-pc-2")]
    [b] = got[0]["boxes"]
    assert b["id"] == "b-upc-2"
    assert (b["before"]["feature"], b["after"]["feature"]) == ("w-upc-1", "w-pc-2")
    assert b["before"]["symbol"] == "MSFT"


def test_merge_listed_until_split_back_from_any_machine(tmp_path):
    """合并后另一台机器也读得到这条合并(刷新、换机器都能拆回);拆回后不再列出。属性里的那个词也算。"""
    pc_dir, upc_dir = _adir(tmp_path, "pc"), _adir(tmp_path, "upc")
    pc, upc = _cfg(pc_dir, "pc"), _cfg(upc_dir, "upc")
    store.append_batch(pc, [_feature("w-pc-1", "放量"), _feature("w-pc-2", "量大", definition="比前段量大"),
                            _box("b-pc-3", "2024-03-01", "2024-03-05", "w-pc-2"),
                            _box("b-pc-4", "2024-03-06", "2024-03-08", "w-pc-1", attrs={"w-pc-2": True})], now=_at(9))
    r = store.read_annotations(pc)
    store.append_batch(pc, [
        _box("b-pc-3", "2024-03-01", "2024-03-05", "w-pc-1", base=r["revs"]["box"]["b-pc-3"]),
        _box("b-pc-4", "2024-03-06", "2024-03-08", "w-pc-1", attrs={"w-pc-1": True}, base=r["revs"]["box"]["b-pc-4"]),
        _delete("feature", "w-pc-2", r["revs"]["feature"]["w-pc-2"]),
    ], now=_at(9, 5))
    _sync(pc_dir, upc_dir)
    [m] = store.read_annotations(upc)["merges"]
    assert m["feature"] == {"id": "w-pc-2", "name": "量大", "definition": "比前段量大"}
    assert m["into"] == "w-pc-1"
    assert [b["id"] for b in m["boxes"]] == ["b-pc-3", "b-pc-4"]

    r = store.read_annotations(upc)
    store.append_batch(upc, [
        _feature("w-pc-2", "量大", definition="比前段量大", base=r["revs"]["feature"]["w-pc-2"]),
        *[{**_op("box", b["id"], b["before"]), "base": r["revs"]["box"][b["id"]]} for b in m["boxes"]],
    ], now=_at(9, 10))
    assert store.read_annotations(upc)["merges"] == []
    assert _boxes(upc)["b-pc-3"]["feature"] == "w-pc-2"


def test_plain_delete_is_not_a_merge(tmp_path):
    """删一个没人用的词、或删框时顺带删词,都不是合并。"""
    cfg = _cfg(_adir(tmp_path), "pc")
    store.append_batch(cfg, [_feature("w-pc-1", "放量"), _feature("w-pc-2", "备用"),
                             _box("b-pc-3", "2024-03-01", "2024-03-05", "w-pc-1")], now=_at(9))
    r = store.read_annotations(cfg)
    store.append_batch(cfg, [_delete("feature", "w-pc-2", r["revs"]["feature"]["w-pc-2"]),
                             _delete("box", "b-pc-3", r["revs"]["box"]["b-pc-3"]),
                             _delete("feature", "w-pc-1", r["revs"]["feature"]["w-pc-1"])], now=_at(9, 5))
    assert store.read_annotations(cfg)["merges"] == []


# ---------------------------------------------------------------- 反馈

def _value(op) -> dict:
    """状态里的样子:值去掉 symbol(状态里按它分到 charts)。"""
    return {k: x for k, x in op["value"].items() if k != "symbol"}


def test_feedback_round_trips_and_is_bucketed_per_chart(tmp_path):
    """三种 target 和几种边界上合法的写法写进去、重放出来原样;按(start、end、编号)排;
    没有反馈的股票不出 feedback 键,只有反馈的股票照样在 charts 里。"""
    cfg = _cfg(_adir(tmp_path), "pc")
    fbs = [
        _feedback("f-pc-1", "2024-03-08"),                                                      # point
        _feedback("f-pc-2", "2024-03-06", "2024-03-12", target="family", family_start="2024-02-20",
                  answer="off_pattern", note=None, segments=["plateau", "new_step"]),           # family,只有分段
        _feedback("f-pc-3", "2024-03-06", "2024-03-08", target="range", answer="off_pattern",
                  note="整体都不像"),                                                             # range,只有 note
        _feedback("f-pc-4", "2024-03-06", "2024-03-08", target="family", family_start="2024-03-06",
                  segments=["plateau"]),                                                        # neg 带分段也行
        _feedback("f-pc-5", "2025-12-31", source="random", answer="pos", note=None),             # 盲看标记 pos 不用 note
        _feedback("f-pc-6", "2023-05-22", symbol="MSFT", source="removed", answer="off_pattern", note="不像"),
    ]
    store.append_batch(cfg, [*fbs, _box("b-pc-7", "2024-03-01", "2024-03-05"),
                             _box("b-pc-8", "2024-01-02", "2024-01-05", symbol="NVDA")])
    result = store.read_annotations(cfg)
    charts = {c["symbol"]: c for c in result["state"]["charts"]}
    assert list(charts) == ["AAPL", "MSFT", "NVDA"]
    by_id = {op["id"]: op for op in fbs}
    assert charts["AAPL"]["feedback"] == [_value(by_id[i]) for i in ("f-pc-3", "f-pc-4", "f-pc-2", "f-pc-1", "f-pc-5")]
    assert [b["id"] for b in charts["AAPL"]["boxes"]] == ["b-pc-7"]
    assert charts["MSFT"] == {"symbol": "MSFT", "boxes": [], "samples": [], "feedback": [_value(by_id["f-pc-6"])]}
    assert "feedback" not in charts["NVDA"]
    assert list(charts["AAPL"]) == ["symbol", "boxes", "samples", "feedback"]
    assert list(charts["AAPL"]["feedback"][1]) == ["id", "pattern", "app_id", "app_ver", "start", "end", "target",
                                                   "source", "answer", "note", "segments", "family_start"]
    assert sorted(result["revs"]["feedback"]) == [f"f-pc-{n}" for n in range(1, 7)]
    assert result["next_seq"] == 9                              # 反馈和词、框、样本共用一个编号序列
    assert result["violations"] == []


def _bare(**drop) -> dict:
    """缺一个必填键的反馈。"""
    op = _feedback("f-pc-1", "2024-03-08")
    for k in drop:
        del op["value"][k]
    return op


@pytest.mark.parametrize("op, fragment", [
    (_feedback("f-pc-1", "2024-03-08", symbol="../x"), "非法代码"),
    (_feedback("f-pc-1", "2024-03-08", pattern=""), "pattern"),
    (_feedback("f-pc-1", "2024-03-08", app_id=""), "app_id"),
    (_feedback("f-pc-1", "2024-03-08", app_ver=None), "app_ver"),
    (_feedback("f-pc-1", "2024-03-12", "2024-03-08", target="range"), "晚于 end"),
    (_feedback("f-pc-1", "2025-12-29", "2026-01-05", target="range"), "2025-12-31"),       # 晚于训练段末日
    (_feedback("f-pc-1", "2024-02-30", "2024-03-08", target="range"), "不是真实日期"),
    (_feedback("f-pc-1", "2024-03-08", target="week"), "target"),
    (_feedback("f-pc-1", "2024-03-08", source="guess"), "source"),
    (_feedback("f-pc-1", "2024-03-08", answer="pos"), "answer"),                              # 反馈没有 pos
    (_feedback("f-pc-1", "2024-03-08", "2024-03-12"), "point"),                               # point 不是一天
    (_feedback("f-pc-1", "2024-03-08", "2024-03-12", target="family"), "family_start"),
    (_feedback("f-pc-1", "2024-03-08", "2024-03-12", target="family", family_start="2024-03-09"), "family_start"),
    (_feedback("f-pc-1", "2024-03-08", "2024-03-12", target="family", family_start="2024-02-30"), "family_start"),
    (_feedback("f-pc-1", "2024-03-08", "2024-03-12", target="range", family_start="2024-03-01"), "family_start"),
    (_feedback("f-pc-1", "2024-03-08", note=None), "note"),                                   # neg 必须写理由
    (_feedback("f-pc-1", "2024-03-08", note=""), "note"),
    (_feedback("f-pc-1", "2024-03-08", answer="off_pattern", note=None, segments=[]), "至少一样"),
    (_feedback("f-pc-1", "2024-03-08", answer="off_pattern", segments=["plateau", "plateau"]), "segments"),
    (_feedback("f-pc-1", "2024-03-08", answer="off_pattern", segments=[""]), "segments"),
    (_feedback("f-pc-1", "2024-03-08", answer="off_pattern", segments="plateau"), "segments"),
    (_feedback("f-pc-1", "2024-03-08", "2024-03-12", target="family", family_start="2024-03-01", source="random",
               answer="pos"), "盲看标记的 target"),
    (_feedback("f-pc-1", "2024-03-08", "2024-03-12", target="range", source="added", answer="pos"),
     "盲看标记的 target"),
    (_feedback("f-pc-1", "2024-03-08", source="random", answer="maybe"), "盲看标记的 answer"),
    (_feedback("f-pc-1", "2024-03-08", source="random", note=None), "note"),                  # 盲看 neg 必须写理由
    (_feedback("f-pc-1", "2024-03-08", source="tuned_added", answer="off_pattern", note=None, segments=["plateau"]),
     "note"),
    (_feedback("f-pc-1", "2024-03-08", color="red"), "多出"),
    (_bare(app_ver=None), "缺少"),
    (_feedback("s-pc-1", "2024-03-08"), "f-<机器名>-<序号>"),                                # 编号字母与种类不符
])
def test_rejects_malformed_feedback(tmp_path, op, fragment):
    """每条取值规则各一例:只违反这一条,整批拒收、一个文件都不写。"""
    adir = _adir(tmp_path)
    with pytest.raises(store.BatchRejected) as e:
        store.append_batch(_cfg(adir, "pc"), [op])
    [reason] = e.value.reasons
    assert reason["code"] == "bad_op" and fragment in reason["message"]
    assert list(adir.iterdir()) == []


def test_blind_marks_cannot_be_changed_or_deleted(tmp_path):
    """盲看标记改 answer、改 note、改成 picked、删掉都被拒;改、删 picked 的反馈和别的操作照常放行。"""
    adir = _adir(tmp_path)
    cfg = _cfg(adir, "pc")
    blind = _feedback("f-pc-1", "2024-03-08", source="random", answer="pos", note=None)
    store.append_batch(cfg, [blind, _feedback("f-pc-2", "2024-03-11")])
    v, base = blind["value"], _rev(cfg, "feedback", "f-pc-1")
    for value in ({**v, "answer": "neg", "note": "看着不像"},
                  {**v, "note": "补一句"},
                  {**v, "source": "picked", "answer": "neg", "note": "先改成 picked"},
                  None):
        before = _hashes(adir)
        with pytest.raises(store.BatchRejected) as e:
            store.append_batch(cfg, [_op("feedback", "f-pc-1", value, base),
                                     _box("b-pc-3", "2024-03-01", "2024-03-05")])
        assert [(r["code"], r["feedback"]) for r in e.value.reasons] == [("blind_immutable", "f-pc-1")]
        assert _hashes(adir) == before

    store.append_batch(cfg, [_feedback("f-pc-2", "2024-03-11", answer="off_pattern", note=None, segments=["plateau"],
                                       base=_rev(cfg, "feedback", "f-pc-2")),
                             _box("b-pc-3", "2024-03-01", "2024-03-05")])
    store.append_batch(cfg, [_delete("feedback", "f-pc-2", _rev(cfg, "feedback", "f-pc-2"))])
    result = store.read_annotations(cfg)
    assert result["violations"] == []
    assert result["state"]["charts"][0]["feedback"] == [_value(blind)]


def test_blind_mark_changed_by_sync_is_listed_not_changed(tmp_path):
    """同步来的批次不经保存校验:改了或删了盲看标记,读结果在 violations 里列出来,数据照原样;
    这之后保存时只许把它改回原样。"""
    adir = _adir(tmp_path)
    pc = _cfg(adir, "pc")
    blind = _feedback("f-upc-1", "2024-03-08", source="random", answer="pos", note=None)
    v = blind["value"]
    store.append_batch(_cfg(adir, "upc"), [blind], now=_at(9))
    _write_raw(adir, "upc", "20261103T091000.000Z", 2,
               [_op("feedback", "f-upc-1", {**v, "answer": "neg", "note": "改了"}, _rev(pc, "feedback", "f-upc-1"))])
    result = store.read_annotations(pc)
    [viol] = result["violations"]
    assert (viol["code"], viol["feedback"]) == ("blind_immutable", "f-upc-1")
    assert "answer" in viol["message"] and "note" in viol["message"]
    assert result["state"]["charts"][0]["feedback"][0]["answer"] == "neg"

    with pytest.raises(store.BatchRejected) as e:              # 接着改:拒
        store.append_batch(pc, [_op("feedback", "f-upc-1", {**v, "answer": "off_pattern", "note": "再改"},
                                    _rev(pc, "feedback", "f-upc-1"))], now=_at(9, 20))
    assert [r["code"] for r in e.value.reasons] == ["blind_immutable"]
    store.append_batch(pc, [_op("feedback", "f-upc-1", v, _rev(pc, "feedback", "f-upc-1"))], now=_at(9, 20))
    assert store.read_annotations(pc)["violations"] == []      # 改回原样:放行,不再列

    _write_raw(adir, "upc", "20261103T093000.000Z", 3, [_delete("feedback", "f-upc-1", _rev(pc, "feedback", "f-upc-1"))])
    result = store.read_annotations(pc)
    [viol] = result["violations"]
    assert (viol["code"], viol["feedback"]) == ("blind_immutable", "f-upc-1") and "删" in viol["message"]
    assert result["state"]["charts"] == []


# ---------------------------------------------------------------- 会话定格:machines 与 as_of

def test_schema_unchanged_and_golden_v1_machines():
    assert store.SCHEMA == "path2_web.annotation/1"
    got = store.read_annotations(_cfg(FIXTURE / "batches", "pc"))
    assert got["machines"] == {"pc": {"through": 3}, "upc": {"through": 2}}
    assert all("feedback" not in c for c in got["state"]["charts"])


def test_machines_through_counts_only_contiguous_seqs(tmp_path):
    """序号从 1 起连续到哪算到哪:pc 有 1、1、2、4(同号两个文件不影响)→ 2;upc 缺 1 号 → 0。"""
    adir = _adir(tmp_path)
    for n, (machine, ts, seq) in enumerate([("pc", "20261103T090000.000Z", 1), ("pc", "20261103T090500.000Z", 1),
                                            ("pc", "20261103T091000.000Z", 2), ("pc", "20261103T092000.000Z", 4),
                                            ("upc", "20261103T091500.000Z", 2)], start=1):
        _write_raw(adir, machine, ts, seq, [_box(f"b-{machine}-{n}", "2024-03-01", "2024-03-05")])
    assert store.read_annotations(_cfg(adir, "pc"))["machines"] == {"pc": {"through": 2}, "upc": {"through": 0}}


def test_as_of_without_gap_reads_back_the_state_at_that_time(tmp_path):
    """两台交错写同一个目录:定格时记下 {机器: through},之后再怎么改,按它截出来的状态都等于当时读到的。"""
    adir = _adir(tmp_path)
    pc, upc = _cfg(adir, "pc"), _cfg(adir, "upc")
    store.append_batch(pc, [_box("b-pc-1", "2024-03-01", "2024-03-05")], now=_at(9))
    store.append_batch(upc, [_feedback("f-upc-2", "2024-03-08")], now=_at(9, 5))
    store.append_batch(pc, [_box("b-pc-1", "2024-03-01", "2024-03-04", base=_rev(pc, "box", "b-pc-1"))],
                       now=_at(9, 10))
    then = store.read_annotations(pc)
    assert then["machines"] == {"pc": {"through": 2}, "upc": {"through": 1}}
    frozen = {m: x["through"] for m, x in then["machines"].items()}

    store.append_batch(upc, [_box("b-pc-1", "2024-03-01", "2024-03-03", base=_rev(upc, "box", "b-pc-1")),
                             _delete("feedback", "f-upc-2", _rev(upc, "feedback", "f-upc-2"))], now=_at(9, 20))
    store.append_batch(pc, [_feedback("f-pc-3", "2024-03-12")], now=_at(9, 30))
    now = store.read_annotations(pc)
    assert now["machines"] == {"pc": {"through": 3}, "upc": {"through": 2}}
    assert now["state"] != then["state"]

    past = store.read_annotations(pc, as_of=frozen)
    assert past["state"] == then["state"]
    assert past["conflicts"] == [] and past["unsynced"] == []
    assert past["machines"] == now["machines"]                  # machines 照全部文件算,不受 as_of 影响


def test_as_of_with_gap_replays_only_batches_up_to_the_cut(tmp_path):
    """upc 的 2 号还没同步到、3 号先到了:through 停在 1;按它截出的状态等于只重放 pc 1 号与 upc 1 号,
    3 号被截掉(下一轮会被当成新的再报一次)。as_of 里没有的机器整台截掉。"""
    pc_dir, upc_dir, want_dir = _adir(tmp_path, "pc"), _adir(tmp_path, "upc"), _adir(tmp_path, "want")
    pc, upc = _cfg(pc_dir, "pc"), _cfg(upc_dir, "upc")
    p1 = store.append_batch(pc, [_box("b-pc-1", "2024-03-01", "2024-03-05")], now=_at(9))
    u1 = store.append_batch(upc, [_box("b-upc-1", "2023-05-01", "2023-05-20", symbol="MSFT")], now=_at(9, 5))
    u2 = store.append_batch(upc, [_box("b-upc-1", "2023-05-01", "2023-05-19", symbol="MSFT",
                                       base=_rev(upc, "box", "b-upc-1"))], now=_at(9, 10))
    u3 = store.append_batch(upc, [_feedback("f-upc-2", "2023-05-22", symbol="MSFT")], now=_at(9, 15))
    for name in (u1, u3):
        shutil.copy2(upc_dir / name, pc_dir / name)
    shutil.copy2(pc_dir / p1, want_dir / p1)
    shutil.copy2(upc_dir / u1, want_dir / u1)

    full = store.read_annotations(pc)
    assert full["machines"] == {"pc": {"through": 1}, "upc": {"through": 1}}
    assert "feedback" in full["state"]["charts"][1]           # 3 号已到,不截时照常重放
    frozen = {m: x["through"] for m, x in full["machines"].items()}
    cut = store.read_annotations(pc, as_of=frozen)
    assert cut["state"] == store.read_annotations(_cfg(want_dir, "pc"))["state"]
    assert "feedback" not in cut["state"]["charts"][1]

    only_pc = store.read_annotations(pc, as_of={"pc": 1})
    assert [c["symbol"] for c in only_pc["state"]["charts"]] == ["AAPL"]

    shutil.copy2(upc_dir / u2, pc_dir / u2)                     # 缺的 2 号到了:through 接到 3
    full = store.read_annotations(pc)
    assert full["machines"] == {"pc": {"through": 1}, "upc": {"through": 3}}
    assert store.read_annotations(pc, as_of={"pc": 1, "upc": 3})["state"] == full["state"]
