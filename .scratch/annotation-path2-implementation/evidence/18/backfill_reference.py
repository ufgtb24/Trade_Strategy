"""票 18:给 4 条整族反馈补存基准 event 起止(reference),只经 append_batch 新写一个批次文件。

在本票 worktree 根目录、用本 worktree 的 .venv 运行(当前代码:存储校验、判法都是票 17 的):

    .venv/bin/python <本文件> plan   --annotation-dir D --out-dir O
    .venv/bin/python <本文件> status --annotation-dir D --out O/status.json
    .venv/bin/python <本文件> write  --annotation-dir D --out-dir O --expect-ops-sha256 H [--approved Qnn]

- 标注目录 D 必须显式给,没有默认值;D 就是配置的标注目录(annotation_dir,即主目录 annotations/)时,
  write 另要 --approved Qnn(用户点过头的那个问题),否则拒绝。试跑用 D 的字节拷贝(scratchpad 里)。
- 要加的起止取自 old_reference.json(old_reference.py 在写反馈那一版 new_step 里算出的)。
- 读标注只经 read_annotations;写只经 append_batch,只调一次。
- 这 4 条之外什么都不动;每条操作的 value = 这条反馈当前的整条记录(补回 symbol)+ reference,base 取它当前
  最后一次修改(read_annotations 的 revs)。

plan:核对前提(4 条都在、是 new_step 的整族反馈、app_ver 1afa716bc5248d4b、family_start 与算起止时用的一致、
  还没有 reference、旧版这一族的买点日范围恰是反馈的 start / end),算出操作与它的哈希(ops_sha256)。
  plan.json 只记编号、股票、base、要加的 reference、每条记录的哈希,不记 note 等标注原文。
status:4 条在当前 new_step 下的状态——判法原始三态(match.feedback_status)、把范围换成没有买点的一天再判的
  三态(只看「同一次形状还在买」那一支),以及 GET /feedback/status 页面上显示的状态。
write:重读标注、重算操作,哈希必须等于 --expect-ops-sha256(送审之后这 4 条被改过、base 变了,就不写);
  写前写后各取一次标注目录的文件清单与 sha256;写完重放核对:已有文件一个没变、只多了这一个批次文件;
  除这 4 条多出 reference 外整个状态逐字不变;冲突、未同步、越界、不合格文件名没有新增;这 4 条的
  note、nodes 不变(annotation-round 摘要判「内容改过」只比这两样)。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

from path2_web.annotation import match
from path2_web.annotation.store import append_batch, read_annotations
from path2_web.app_run import app_buys, run_app
from path2_web.config import annotation_dir, load_config
from path2_web.data import TRAIN_END
from path2_web.discovery import PatternRegistry

HERE = Path(__file__).resolve().parent
OLD_REFERENCE = HERE / "old_reference.json"
APP = "new_step"
OLD_APP_VER = "1afa716bc5248d4b"
REFERENCE = "step"


def _sha(obj) -> str:
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def _cfg(adir: str) -> dict:
    return {**load_config(), "annotation_dir": str(Path(adir).resolve())}


def _is_real_dir(adir: str) -> bool:
    return Path(adir).resolve() == annotation_dir(load_config()).resolve()


def _records(state: dict) -> dict:
    """状态里全部反馈:{id: (股票, 记录)}。"""
    return {fb["id"]: (c["symbol"], fb) for c in state["charts"] for fb in c.get("feedback", [])}


def _old_reference() -> dict:
    d = json.loads(OLD_REFERENCE.read_text())
    if d["app_ver"] != OLD_APP_VER or d["reference_node"] != REFERENCE:
        sys.exit(f"old_reference.json 不是 {OLD_APP_VER} / {REFERENCE} 算的")
    return {f["id"]: f for f in d["feedback"]}


def build_ops(r: dict) -> tuple[list[dict], list[dict]]:
    """按当前标注算出要写的操作;前提不成立就退出。返回 (ops, 不含标注原文的摘要)。"""
    old, recs, ops, rows = _old_reference(), _records(r["state"]), [], []
    for fid, o in old.items():
        if fid not in recs:
            sys.exit(f"{fid} 不在标注里")
        sym, fb = recs[fid]
        want = {"symbol": o["symbol"], "pattern": APP, "app_id": APP, "app_ver": OLD_APP_VER, "target": "family",
                "source": "picked", "family_start": o["family_start"]}
        got = {"symbol": sym, **{k: fb.get(k) for k in want if k != "symbol"}}
        if got != want:
            sys.exit(f"{fid} 前提不符:{got} ≠ {want}")
        if "reference" in fb:
            sys.exit(f"{fid} 已经带 reference,不补")
        if o["family_buy_range"] != [fb["start"], fb["end"]]:
            sys.exit(f"{fid} 旧版这一族的买点日范围 {o['family_buy_range']} 不是反馈的 [{fb['start']}, {fb['end']}]")
        if not o["reference"]["spans"]:
            sys.exit(f"{fid} 旧版这一族取不到基准 event")
        value = {"id": fb["id"], "symbol": sym, **{k: v for k, v in fb.items() if k != "id"},
                 "reference": o["reference"]}
        base = r["revs"]["feedback"][fid]
        ops.append({"kind": "feedback", "id": fid, "base": base, "value": value})
        rows.append({"id": fid, "symbol": sym, "base": base, "family_start": fb["family_start"],
                     "range": [fb["start"], fb["end"]], "reference": o["reference"],
                     "record_sha256_before": _sha(fb)})
    return ops, rows


def _files(adir: str) -> dict:
    """标注目录里的全部文件(含隐藏的、子目录里的):{相对路径: {size, sha256}}。只算字节哈希,不解析。"""
    root, out = Path(adir), {}
    for dp, _, names in os.walk(root):
        for n in names:
            p = Path(dp) / n
            out[p.relative_to(root).as_posix()] = {"size": p.stat().st_size,
                                                    "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
    return dict(sorted(out.items()))


def _strip(state: dict, ids) -> dict:
    """状态的拷贝,去掉这几条反馈的 reference(写后与写前比用)。"""
    s = json.loads(json.dumps(state))
    for c in s["charts"]:
        for fb in c.get("feedback", []):
            if fb["id"] in ids:
                fb.pop("reference", None)
    return s


def cmd_plan(a) -> None:
    r = read_annotations(_cfg(a.annotation_dir))
    ops, rows = build_ops(r)
    out = {"annotation_dir_is_real": _is_real_dir(a.annotation_dir), "ops_sha256": _sha(ops), "n_ops": len(ops),
           "batch_counts": r["machines"], "conflicts": len(r["conflicts"]), "unsynced": len(r["unsynced"]),
           "violations": len(r["violations"]), "ignored_files": r["ignored_files"],
           "fingerprint": r["fingerprint"], "rows": rows}
    Path(a.out_dir).mkdir(parents=True, exist_ok=True)
    (Path(a.out_dir) / "plan.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps(out, ensure_ascii=False, indent=1))


def cmd_status(a) -> None:
    from fastapi.testclient import TestClient
    from path2_web.app import create_app

    cfg = _cfg(a.annotation_dir)
    recs = _records(read_annotations(cfg)["state"])
    mod = PatternRegistry().get(APP)
    params = mod.load_params()
    rows = {}
    for fid in _old_reference():
        sym, fb = recs[fid]
        res, win, meta = run_app(mod, cfg, sym, "1900-01-01", TRAIN_END, params, 20)
        buys = app_buys(res, win, meta["end_node"], reference=REFERENCE)
        no_range = {**fb, "start": "1900-01-02", "end": "1900-01-02"}
        rows[fid] = {"symbol": sym, "has_reference": "reference" in fb,
                     "raw": match.feedback_status(fb, buys),
                     "raw_without_range_buys": match.feedback_status(no_range, buys)}
    with tempfile.TemporaryDirectory() as outputs:      # 扫描结果目录用不到,给个临时的,不碰 outputs/
        client = TestClient(create_app(config_override=cfg, outputs_root=outputs, use_thread_pool=True))
        resp = client.get("/feedback/status", params={"pattern": APP})
    resp.raise_for_status()
    body = resp.json()
    for it in body["items"]:
        if it["id"] in rows:
            rows[it["id"]]["shown"] = it["status"]
            rows[it["id"]]["red"] = it["red"]
    out = {"app_ver": body["app_ver"], "reason": body["reason"], "rows": rows}
    Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps(out, ensure_ascii=False, indent=1))


def cmd_write(a) -> None:
    real = _is_real_dir(a.annotation_dir)
    if real and not a.approved:
        sys.exit("这是真实的标注目录:要 --approved Qnn(用户点过头的问题)才写")
    cfg, out = _cfg(a.annotation_dir), Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    before_files = _files(a.annotation_dir)
    before = read_annotations(cfg)
    ops, rows = build_ops(before)
    if _sha(ops) != a.expect_ops_sha256:
        sys.exit(f"操作哈希 {_sha(ops)} 不等于送审的 {a.expect_ops_sha256}:送审之后标注变了,不写")
    (out / "before_files.json").write_text(json.dumps(before_files, indent=1) + "\n")
    name = append_batch(cfg, ops)
    after_files = _files(a.annotation_dir)
    (out / "after_files.json").write_text(json.dumps(after_files, indent=1) + "\n")
    after = read_annotations(cfg)

    ids = {op["id"] for op in ops}
    recs_b, recs_a = _records(before["state"]), _records(after["state"])
    checks = {
        "only_new_file_is_the_batch": sorted(set(after_files) - set(before_files)) == [name],
        "no_file_removed": set(before_files) <= set(after_files),
        "existing_files_unchanged": all(after_files[k] == v for k, v in before_files.items()),
        "state_equal_except_reference": _strip(after["state"], ids) == before["state"],
        "reference_as_planned": all(recs_a[op["id"]][1].get("reference") == op["value"]["reference"] for op in ops),
        "conflicts_unchanged": after["conflicts"] == before["conflicts"],
        "unsynced_unchanged": after["unsynced"] == before["unsynced"],
        "violations_unchanged": after["violations"] == before["violations"],
        "ignored_files_unchanged": after["ignored_files"] == before["ignored_files"],
        "fingerprint_consistent": after["fingerprint"]["consistent"] == before["fingerprint"]["consistent"]
                                  and after["state"]["data_fingerprint"] == before["state"]["data_fingerprint"],
        "note_and_nodes_unchanged": all(
            (recs_b[i][1].get("note"), sorted(recs_b[i][1].get("nodes") or []))
            == (recs_a[i][1].get("note"), sorted(recs_a[i][1].get("nodes") or [])) for i in ids),
    }
    result = {"annotation_dir_is_real": real, "approved": a.approved, "batch_file": name,
              "batch_sha256": after_files[name]["sha256"], "ops_sha256": _sha(ops), "rows": rows,
              "files_before": len(before_files), "files_after": len(after_files),
              "state_sha256_before": _sha(before["state"]), "state_sha256_after_without_reference":
                  _sha(_strip(after["state"], ids)), "checks": checks, "all_ok": all(checks.values())}
    (out / "write_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=1))
    if not result["all_ok"]:
        sys.exit("写后核对没过(见 write_result.json)")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    pl = sub.add_parser("plan")
    pl.add_argument("--annotation-dir", required=True)
    pl.add_argument("--out-dir", required=True)
    st = sub.add_parser("status")
    st.add_argument("--annotation-dir", required=True)
    st.add_argument("--out", required=True)
    wr = sub.add_parser("write")
    wr.add_argument("--annotation-dir", required=True)
    wr.add_argument("--out-dir", required=True)
    wr.add_argument("--expect-ops-sha256", required=True)
    wr.add_argument("--approved", default=None, help="写真实标注目录时必给:用户点过头的问题编号,如 Q12")
    a = p.parse_args()
    {"plan": cmd_plan, "status": cmd_status, "write": cmd_write}[a.cmd](a)


if __name__ == "__main__":
    main()
