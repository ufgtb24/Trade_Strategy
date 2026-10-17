"""操作日志:看图「说出形态」时每一下点选、改写、拒绝、建卡改卡都记一行,只追加。

操作日志是唯一真相,形态卡是它的物化结果(见 shapes.replay)。append() 是唯一写入口,
read_all() 按月份文件顺序读回。文件:<状态根>/oplog/<YYYY-MM>.jsonl,每行一条:
{"ts": "YYYY-MM-DDTHH:MM:SS", "op_id": "<uuid4>", "actor": "user | session", "surface": "chat",
 "act": "shown | pick | unpick | edit | type | reject | first_impression | first_impression_skipped |
         confirm | undo | create_shape | revise_shape | add_case | rename_shape | merge_shape | set_status",
 "target": {"ann_id": "...", "shape_id": "s001", "version": 2, "field": "triggers"},
 "value": ..., "options": [{"sid": "...", "value": "...", "suggested_by": "detector", "rank": 1}],
 "ctx": {"list_id": "...", "list_kind": "bigmoves", "outcome_visible": true, "n_shown": 7}}

摆过没选的、被拒的、改写过的都留在日志里;只有 SHAPE_ACTS 这几类会进形态卡。
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path

from chart_workflow.state import advance, state_root

ACTORS = ("user", "session")
SHAPE_ACTS = ("create_shape", "revise_shape", "add_case", "rename_shape", "merge_shape", "set_status")
ACTS = ("shown", "pick", "unpick", "edit", "type", "reject", "first_impression",
        "first_impression_skipped", "confirm", "undo") + SHAPE_ACTS
FIELDS = ("ts", "op_id", "actor", "surface", "act", "target", "value", "options", "ctx")


def oplog_dir() -> Path:
    return state_root() / "oplog"


def check_entry(e) -> list[str]:
    """一条日志条目的格式问题(空列表 = 合格;不含 ts / op_id 也合格,append 时补)。"""
    if not isinstance(e, dict):
        return [f"条目不是对象: {e!r}"]
    errs = []
    extra = set(e) - set(FIELDS)
    if extra:
        errs.append(f"未知字段 {sorted(extra)}")
    if e.get("act") not in ACTS:
        errs.append(f"act 不合法: {e.get('act')!r}")
    if e.get("actor") not in ACTORS:
        errs.append(f"actor 必须是 user / session: {e.get('actor')!r}")
    if not isinstance(e.get("surface"), str) or not e.get("surface"):
        errs.append("surface 必填")
    for k in ("target", "ctx"):
        if e.get(k) is not None and not isinstance(e[k], dict):
            errs.append(f"{k} 必须是对象")
    if e.get("options") is not None and not isinstance(e["options"], list):
        errs.append("options 必须是列表")
    return errs


def append(entries: list[dict]) -> list[dict]:
    """补上 ts / op_id 后一次性追加到当月文件,返回补全后的条目。任何一条格式不对就一条都不写。"""
    errs = [f"第 {k + 1} 条:{m}" for k, e in enumerate(entries) for m in check_entry(e)]
    if errs:
        raise ValueError("; ".join(errs))
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    out = []
    for e in entries:
        full = {k: e.get(k) for k in FIELDS}
        full["ts"] = e.get("ts") or now
        full["op_id"] = e.get("op_id") or str(uuid.uuid4())
        out.append(full)
    by_month: dict[str, list[str]] = {}
    for e in out:
        by_month.setdefault(e["ts"][:7], []).append(json.dumps(e, ensure_ascii=False))
    d = oplog_dir()
    d.mkdir(parents=True, exist_ok=True)
    for month, lines in sorted(by_month.items()):
        with (d / f"{month}.jsonl").open("a") as f:
            f.write("".join(line + "\n" for line in lines))
    advance(d.parent)                    # 新行记进水位
    return out


def read_all() -> list[dict]:
    """按月份文件名顺序、文件内按行序读回全部条目。"""
    d = oplog_dir()
    out = []
    for p in sorted(d.glob("*.jsonl")) if d.exists() else []:
        out += [json.loads(line) for line in p.read_text().splitlines() if line.strip()]
    return out
