"""操作日志:看图「说出形态」时每一下点选、改写、拒绝、建卡改卡、建要素改要素都记一行,只追加。

操作日志是唯一真相,要素与形态卡是它的物化结果(见 elements.replay、shapes.replay)。append() 是唯一写入口,
read_all() 按月份文件顺序读回。文件:<状态根>/oplog/<YYYY-MM>.jsonl,每行一条:
{"ts": "YYYY-MM-DDTHH:MM:SS", "op_id": "<uuid4>", "rules_version": 3, "quality_fp": "<16 位>",
 "actor": "user | session", "surface": "chat",
 "act": "shown | pick | unpick | edit | type | reject | first_impression | first_impression_skipped |
         confirm | undo | propose_fact | create_shape | revise_shape | add_case | rename_shape |
         merge_shape | set_status | create_element | revise_element | alias_element | merge_element",
 "target": {"ann_id": "...", "shape_id": "s001", "element_id": "E001", "version": 2, "field": "triggers"},
 "value": ..., "options": [{"sid": "...", "value": "...", "suggested_by": "detector", "rank": 1}],
 "ctx": {"list_id": "...", "list_kind": "bigmoves", "outcome_visible": true, "n_shown": 7}}

摆过没选的、被拒的、改写过的都留在日志里;只有 SHAPE_ACTS 这几类会进形态卡,ELEMENT_ACTS 这几类
会进要素库——这两类只能经决定文件(shapes.apply)写入,直接调 append 写它们会被拒;重算(shapes rebuild)
时还会把它们逐条重新走一遍决定文件的校验(shapes.revalidate)。
rules_version:写入时的校验版本号,由 append 补(写进来的值不作数)。校验规则收紧时 RULES_VERSION 加一,
重走校验时每条按它自己的版本号用当时的规则(rules_at),当时合法、现在不再允许的只提示不拦。现在的工具写的
每一条都带版本号:要素与卡的条目没有这个字段,一律当作被改过、拦下,没有例外。
quality_fp:要素与卡的条目写入时,定义的质量把关所读到的值的指纹(elements.quality_fingerprint),由 append
补(写进来的值不作数,别的条目记 null);第 3 版起才有。重走时据此分辨「写入后配置变了」(只提示)和「写入时
就不合格」(当被改过,拦)。各版的差别见 shapes 模块说明。
propose_fact:用户提了一个现有事实行没有的角度(value {"said": 原话}),只进日志——
照它写成的事实行在 facts.ROWS 里把出处指向这一条(op_id)。
"""
from __future__ import annotations

import contextlib
import contextvars
import json
import uuid
from datetime import datetime
from pathlib import Path

from chart_workflow.state import advance, state_root

ACTORS = ("user", "session")
SHAPE_ACTS = ("create_shape", "revise_shape", "add_case", "rename_shape", "merge_shape", "set_status")
ELEMENT_ACTS = ("create_element", "revise_element", "alias_element", "merge_element")
ACTS = ("shown", "pick", "unpick", "edit", "type", "reject", "first_impression",
        "first_impression_skipped", "confirm", "undo", "propose_fact") + SHAPE_ACTS + ELEMENT_ACTS
FIELDS = ("ts", "op_id", "rules_version", "quality_fp", "actor", "surface", "act", "target", "value", "options",
          "ctx")
TOOL_FIELDS = ("ts", "op_id", "rules_version", "quality_fp")      # 工具补的字段,决定文件里不许自带
VIA_DECISION = object()          # shapes.apply 校验完决定文件后传给 append 的凭据
RULES_VERSION = 3                # 现在的校验版本号;各版差别见 shapes 模块说明
_RULES = contextvars.ContextVar("chart_workflow_rules_version", default=RULES_VERSION)


def rules_now() -> int:
    """当前生效的校验版本号:平时是 RULES_VERSION,重走旧条目时是那条自己的版本号(见 rules_at)。"""
    return _RULES.get()


@contextlib.contextmanager
def rules_at(version: int):
    """在这段代码里按第 version 版的校验规则走(重走旧条目用)。"""
    token = _RULES.set(version)
    try:
        yield
    finally:
        _RULES.reset(token)


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
    rv = e.get("rules_version")
    if rv is not None and (not isinstance(rv, int) or isinstance(rv, bool) or not 1 <= rv <= RULES_VERSION):
        errs.append(f"rules_version 不认识: {rv!r}(现在的工具是第 {RULES_VERSION} 版)")
    fp = e.get("quality_fp")
    if fp is not None and not (isinstance(fp, str) and len(fp) == 16 and all(c in "0123456789abcdef" for c in fp)):
        errs.append(f"quality_fp 格式不对: {fp!r}")
    if e.get("act") == "propose_fact" and not (isinstance(e.get("value"), dict)
                                               and str(e["value"].get("said") or "").strip()):
        errs.append("propose_fact 的 value 要带 said(用户提这个角度的原话)")
    return errs


def append(entries: list[dict], via=None) -> list[dict]:
    """补上 ts / op_id / rules_version(一律是 RULES_VERSION)/ quality_fp(要素与卡的条目记现在的质量把关指纹,
    别的记 null)后一次性追加到当月文件,返回补全后的条目。
    任何一条格式不对就一条都不写。
    要素与形态卡这两类操作只能经决定文件写(shapes.apply 校验后传 via=VIA_DECISION);直接写日志
    不跑来源校验,拒绝。"""
    if via is not VIA_DECISION:
        bad = sorted({e.get("act") for e in entries if isinstance(e, dict)
                      and (e.get("act") in SHAPE_ACTS or e.get("act") in ELEMENT_ACTS)})
        if bad:
            raise ValueError(f"{'、'.join(bad)} 只能经决定文件写(python -m chart_workflow.shapes apply);"
                             f"直接写操作日志不跑来源校验")
    errs = [f"第 {k + 1} 条:{m}" for k, e in enumerate(entries) for m in check_entry(e)]
    if errs:
        raise ValueError("; ".join(errs))
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    from chart_workflow.elements import quality_fingerprint      # 函数内导入:elements 依赖本模块

    fp = quality_fingerprint()
    out = []
    for e in entries:
        full = {k: e.get(k) for k in FIELDS}
        full["ts"] = e.get("ts") or now
        full["op_id"] = e.get("op_id") or str(uuid.uuid4())
        full["rules_version"] = RULES_VERSION
        full["quality_fp"] = fp if (e.get("act") in SHAPE_ACTS or e.get("act") in ELEMENT_ACTS) else None
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
