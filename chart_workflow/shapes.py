"""形态卡:一种形态由哪些要素组成、各按什么口径算、触发、买前失效、为什么会涨、卖法。

操作日志(oplog.py)是唯一真相,形态卡是它的物化结果:replay(ops) 是纯函数,只看
create_shape / revise_shape / add_case / rename_shape / merge_shape / set_status 六类;
摆过没选的、被拒的都只进日志、不进卡。写入流程:校验 → 追加日志 → 从全部日志重算受影响的卡 → 写卡
(规范化 JSON:ensure_ascii=False, indent=1, sort_keys=True,先写临时文件再换名)。

    uv run python -m chart_workflow.shapes apply <决定.json>
    uv run python -m chart_workflow.shapes show [<shape_id>]
    uv run python -m chart_workflow.shapes show --pending
    uv run python -m chart_workflow.shapes rebuild [--verify]

来源记录(每个会变成规则条件的值包一层;数值门槛不包):
{"value": ..., "origin": "user_written | suggested_adopted | suggested_edited",
 "suggested_by": "own_library | detector | llm | general_knowledge | session",
 "suggested_value": ..., "said_first_match": "用户先说的一句里对得上的原话",
 "root": {<own_library 复用时,那条值当初入库时的来源记录>}}
规则(validate,任一不过就拒绝写入并列出全部问题):origin 必填;推荐来的(adopted / edited)要写
suggested_by;改过的推荐要带 suggested_value(用户自己写的也可以带,记下当时摆着的推荐);
引用事实表行 / 触发候选 / 失效模板(term 不是 custom)的值永远算推荐——推荐来的只能是
detector 或 own_library,用户自己写的必须带非空 said_first_match;own_library 必须带 root,
算条件构成时递归到 root,防止采纳过的系统推荐经用户的卡转一手被洗成用户来源。
包一层的粒度:每个要素(及 choices 里每一项)、每个触发、每个分歧答案、形态名字、story、exit_pref、
每个样本的买点与形态认领。

形态卡 <状态根>/shapes/<shape_id>.json(chart_workflow.shape/1):
{"schema", "shape_id": "s001", "name": <来源记录>, "aliases": [旧名], "status": "draft | confirmed |
 in_trial | judged | merged", "merged_into": null, "current_version": 1,
 "versions": [{"version", "ts", "change", "after_seeing_outcome", "list_kind", "from_ann",
               "card": {"ingredients": [{"ing_id", "term": "F01..F15 | T1..T8 | I1 | I2 | custom",
                                          "text"(custom 必填), "role": "must | bonus | must_not",
                                          <来源记录字段>, "choices": {名: <来源记录>}}],
                        "triggers": [{"trig_id", "term": "T1..T8 | custom", "text", <来源记录字段>}],
                        "story": <来源记录> | null, "exit_pref": <来源记录> | null}}],
 "cases": [{"ann_id", "batch_id", "buy_date": <来源记录>, "trigger_ref": "t1", "shape_claim": <来源记录>,
            "divergence_answers": [{"dvid", "options", "choice": <来源记录>}], "facts_ref", "version"}]}
版本只追加;改名只改 name,旧名进 aliases;合并时被并的卡写 status = merged 与 merged_into。
after_seeing_outcome 由这一版引用的标注(from_ann)所在批次头的 outcome_visible 推出(v1 批次按 true;
没引用标注时取决定文件 ctx 的 outcome_visible,缺省按 true),apply 时算好写进日志,replay 只照抄。

决定文件(会话把聊天里定下的一批东西写成一个文件,一次写进日志和卡;全部校验通过才写,任何一条不过
就一条都不写):
{"schema": "chart_workflow.decision/1", "actor": "session", "surface": "chat", "ctx": {...},
 "ops": [<操作日志条目,不含 ts / op_id;actor / surface / ctx 缺省取文件头>]}
六类形态操作的 target / value:
  create_shape  target {"shape_id"(可省,自动分配 s001、s002…)}  value {"name", "card", "change", "from_ann"}
  revise_shape  target {"shape_id"}  value {"card", "change", "from_ann"}
  add_case      target {"shape_id"}  value {"ann_id", "batch_id", "buy_date", "trigger_ref", "shape_claim",
                                           "divergence_answers", "facts_ref"}
  rename_shape  target {"shape_id"}  value {"name"}
  merge_shape   target {"shape_id"}  value {"into"}
  set_status    target {"shape_id"}  value {"status"}
同一个决定文件里,后面的操作用 shape_id = "$new" 指这个文件里最近一次 create_shape 建的卡。

红线:不 import 标签口径(labels)、对照(control)、面板(panel)、清单(listfile),不读清单文件。
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from pathlib import Path

from chart_workflow import oplog
from chart_workflow.annotations import iter_batches
from chart_workflow.facts import INVALIDATIONS, ROWS, TRIGGERS
from chart_workflow.state import StateRootMissing, state_root

SCHEMA = "chart_workflow.shape/1"
DECISION_SCHEMA = "chart_workflow.decision/1"
ORIGINS = ("user_written", "suggested_adopted", "suggested_edited")
SUGGESTED_BY = ("own_library", "detector", "llm", "general_knowledge", "session")
ROLES = ("must", "bonus", "must_not")
STATUSES = ("draft", "confirmed", "in_trial", "judged", "merged")
ORIGIN_FIELDS = ("origin", "suggested_by", "suggested_value", "said_first_match", "root")
SHAPE_ID_RE = re.compile(r"^s(\d{3,})$")
NEW_REF = "$new"
CARD_TERMS = tuple(ROWS) + tuple(TRIGGERS) + tuple(INVALIDATIONS) + ("custom",)
TRIGGER_TERMS = tuple(TRIGGERS) + ("custom",)
ROLE_TEXT = {"must": "必须有", "bonus": "加分", "must_not": "有它就不买"}
BY_TEXT = {"detector": "事实表", "own_library": "你以前的形态卡", "llm": "大模型",
           "general_knowledge": "通用常识", "session": "会话"}
STATUS_TEXT = {"draft": "草稿", "confirmed": "已确认", "in_trial": "试验中", "judged": "已判定",
               "merged": "已并入别的卡"}


class ShapeValidationError(ValueError):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("决定文件不合格:\n  " + "\n  ".join(errors))


# ── 来源记录与卡的校验 ───────────────────────────────────────────────────────

def validate(rec, path: str, term: str | None = None, wrapped: bool = True,
             is_root: bool = False) -> list[str]:
    """一条来源记录的问题清单。wrapped:要求带 value(要素 / 触发的来源字段直接摊在条目上,不带 value)。
    term:这个值引用的事实表行 / 触发 / 失效模板编号(custom 或 None 表示不引用)。"""
    if not isinstance(rec, dict):
        return [f"{path}: 不是对象"]
    errs = []
    if wrapped and "value" not in rec:
        errs.append(f"{path}: 缺 value")
    origin = rec.get("origin")
    by = rec.get("suggested_by")
    if origin not in ORIGINS:
        errs.append(f"{path}: origin 必填且只能是 {'/'.join(ORIGINS)}(现为 {origin!r})")
    if origin in ("suggested_adopted", "suggested_edited") and by not in SUGGESTED_BY:
        errs.append(f"{path}: 推荐来的值要写 suggested_by({'/'.join(SUGGESTED_BY)})")
    if by is not None and by not in SUGGESTED_BY:
        errs.append(f"{path}: suggested_by 不合法 {by!r}")
    if origin == "suggested_edited" and "suggested_value" not in rec:
        errs.append(f"{path}: 改过的推荐要带 suggested_value(推荐原值)")
    refs_table = term is not None and term != "custom"
    if refs_table and not is_root:
        if origin == "user_written" and not str(rec.get("said_first_match") or "").strip():
            errs.append(f"{path}: 引用 {term} 却记成用户自己写的,要带 said_first_match(用户先说的原话)")
        if origin in ("suggested_adopted", "suggested_edited") and by not in ("detector", "own_library",
                                                                              None):
            errs.append(f"{path}: {term} 来自事实表,推荐来源只能是 detector 或 own_library")
    if by == "own_library":
        root = rec.get("root")
        if not isinstance(root, dict):
            errs.append(f"{path}: 从你以前的形态卡复用的值要带 root(当初入库时的来源记录)")
        else:
            errs += validate(root, f"{path}.root", term, wrapped=False, is_root=True)
    return errs


def validate_card(card, path: str = "card") -> list[str]:
    if not isinstance(card, dict):
        return [f"{path}: 不是对象"]
    errs = []
    extra = set(card) - {"ingredients", "triggers", "story", "exit_pref"}
    if extra:
        errs.append(f"{path}: 未知字段 {sorted(extra)}")
    ings = card.get("ingredients", [])
    if not isinstance(ings, list):
        return errs + [f"{path}.ingredients: 必须是列表"]
    seen = set()
    for k, ing in enumerate(ings):
        p = f"{path}.ingredients[{k}]"
        if not isinstance(ing, dict):
            errs.append(f"{p}: 不是对象")
            continue
        iid, term = ing.get("ing_id"), ing.get("term")
        if not isinstance(iid, str) or not iid or iid in seen:
            errs.append(f"{p}: ing_id 缺失或重复 {iid!r}")
        seen.add(iid)
        if term not in CARD_TERMS:
            errs.append(f"{p}: term 不认识 {term!r}")
        if term == "custom" and not str(ing.get("text") or "").strip():
            errs.append(f"{p}: 自己写的要素(custom)要带 text")
        if ing.get("role") not in ROLES:
            errs.append(f"{p}: role 只能是 {'/'.join(ROLES)}")
        errs += validate(ing, p, term, wrapped=False)
        choices = ing.get("choices") or {}
        if not isinstance(choices, dict):
            errs.append(f"{p}.choices: 必须是对象")
        else:
            for name, ch in choices.items():      # 口径选择本身不引用事实表编号
                errs += validate(ch, f"{p}.choices.{name}")
    trigs = card.get("triggers", [])
    if not isinstance(trigs, list):
        return errs + [f"{path}.triggers: 必须是列表"]
    seen = set()
    for k, t in enumerate(trigs):
        p = f"{path}.triggers[{k}]"
        if not isinstance(t, dict):
            errs.append(f"{p}: 不是对象")
            continue
        tid, term = t.get("trig_id"), t.get("term")
        if not isinstance(tid, str) or not tid or tid in seen:
            errs.append(f"{p}: trig_id 缺失或重复 {tid!r}")
        seen.add(tid)
        if term not in TRIGGER_TERMS:
            errs.append(f"{p}: term 不认识 {term!r}")
        if term == "custom" and not str(t.get("text") or "").strip():
            errs.append(f"{p}: 自己写的触发(custom)要带 text")
        errs += validate(t, p, term, wrapped=False)
    for key in ("story", "exit_pref"):
        if card.get(key) is not None:
            errs += validate(card[key], f"{path}.{key}")
    return errs


def _validate_value(act: str, v, path: str) -> list[str]:
    """六类形态操作 value 的格式(不看状态)。"""
    if not isinstance(v, dict):
        return [f"{path}: value 必须是对象"]
    errs = []
    if act in ("create_shape", "rename_shape"):
        errs += validate(v.get("name"), f"{path}.name")
        if isinstance(v.get("name"), dict) and not str(v["name"].get("value") or "").strip():
            errs.append(f"{path}.name: 名字不能为空")
    if act in ("create_shape", "revise_shape"):
        errs += validate_card(v.get("card"), f"{path}.card")
        if not str(v.get("change") or "").strip():
            errs.append(f"{path}: change 必填(一句话说这一版改了什么)")
        if not isinstance(v.get("from_ann", []), list):
            errs.append(f"{path}: from_ann 必须是列表")
    if act == "add_case":
        if not isinstance(v.get("ann_id"), str):
            errs.append(f"{path}: ann_id 必填")
        errs += validate(v.get("buy_date"), f"{path}.buy_date")
        errs += validate(v.get("shape_claim"), f"{path}.shape_claim")
        for k, da in enumerate(v.get("divergence_answers") or []):
            if not isinstance(da, dict) or not isinstance(da.get("dvid"), str):
                errs.append(f"{path}.divergence_answers[{k}]: 要有 dvid")
                continue
            errs += validate(da.get("choice"), f"{path}.divergence_answers[{k}].choice")
    if act == "merge_shape" and not isinstance(v.get("into"), str):
        errs.append(f"{path}: into 必填")
    if act == "set_status" and v.get("status") not in STATUSES[:-1]:
        errs.append(f"{path}: status 只能是 {'/'.join(STATUSES[:-1])}(并卡用 merge_shape)")
    return errs


# ── 重算(纯函数) ───────────────────────────────────────────────────────────

def _version(n: int, op: dict) -> dict:
    v = op["value"]
    return {"version": n, "ts": op["ts"], "change": v["change"],
            "after_seeing_outcome": bool(v.get("after_seeing_outcome", True)),
            "list_kind": v.get("list_kind"), "from_ann": list(v.get("from_ann") or []),
            "card": copy.deepcopy(v["card"])}


def _step(cards: dict, op: dict) -> None:
    """把一条形态操作作用到 cards 上(就地改)。和状态对不上 → ValueError。"""
    act = op["act"]
    if act not in oplog.SHAPE_ACTS:
        return
    sid = (op.get("target") or {}).get("shape_id")
    v = op["value"]
    if act == "create_shape":
        if sid in cards:
            raise ValueError(f"形态卡 {sid} 已存在")
        cards[sid] = {"schema": SCHEMA, "shape_id": sid, "name": copy.deepcopy(v["name"]),
                      "aliases": [], "status": "draft", "merged_into": None, "current_version": 1,
                      "versions": [_version(1, op)], "cases": []}
        return
    if sid not in cards:
        raise ValueError(f"形态卡 {sid!r} 不存在")
    c = cards[sid]
    if act == "revise_shape":
        n = c["current_version"] + 1
        c["versions"].append(_version(n, op))
        c["current_version"] = n
    elif act == "add_case":
        ref = v.get("trigger_ref")
        cur = c["versions"][-1]["card"]
        if ref is not None and ref not in {t["trig_id"] for t in cur.get("triggers", [])}:
            raise ValueError(f"{sid} 当前版本里没有触发 {ref!r}")
        c["cases"].append({"ann_id": v["ann_id"], "batch_id": v.get("batch_id"),
                           "buy_date": copy.deepcopy(v["buy_date"]), "trigger_ref": ref,
                           "shape_claim": copy.deepcopy(v["shape_claim"]),
                           "divergence_answers": copy.deepcopy(v.get("divergence_answers") or []),
                           "facts_ref": v.get("facts_ref"), "version": c["current_version"]})
    elif act == "rename_shape":
        old = c["name"].get("value")
        if old not in c["aliases"]:
            c["aliases"].append(old)
        c["name"] = copy.deepcopy(v["name"])
    elif act == "merge_shape":
        if v["into"] == sid or v["into"] not in cards:
            raise ValueError(f"{sid} 不能并入 {v['into']!r}")
        c["status"], c["merged_into"] = "merged", v["into"]
    elif act == "set_status":
        c["status"] = v["status"]


def replay(ops: list[dict]) -> dict[str, dict]:
    """从操作日志从头重算全部形态卡(纯函数,只看六类形态操作)。"""
    cards: dict[str, dict] = {}
    for op in ops:
        _step(cards, op)
    return cards


# ── 读写 ───────────────────────────────────────────────────────────────────

def shapes_dir() -> Path:
    return state_root() / "shapes"


def canonical(card: dict) -> str:
    return json.dumps(card, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def write_card(card: dict) -> Path:
    d = shapes_dir()
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{card['shape_id']}.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(canonical(card))
    tmp.replace(path)
    return path


def load_card(shape_id: str) -> dict:
    p = shapes_dir() / f"{shape_id}.json"
    if not SHAPE_ID_RE.fullmatch(shape_id or "") or not p.exists():
        raise FileNotFoundError(f"形态卡不存在: {shape_id}")
    return json.loads(p.read_text())


def _ann_index() -> dict[str, dict]:
    """ann_id → {batch_id, outcome_visible, list_kind, symbol, buy_points, label}(读全部标注批次)。"""
    out = {}
    for p, b, _ in iter_batches(state_root() / "annotations"):
        if b is None:
            continue
        for a in b["annotations"]:
            out[a["ann_id"]] = {"batch_id": b["batch_id"], "outcome_visible": b["outcome_visible"],
                                "list_kind": b["list_kind"], "list_id": b["list_id"], **a}
    return out


def _next_id(ids) -> str:
    nums = [int(m.group(1)) for i in ids if isinstance(i, str) and (m := SHAPE_ID_RE.fullmatch(i))]
    return f"s{(max(nums) + 1) if nums else 1:03d}"


def prepare(decision: dict, existing_ops: list[dict], anns: dict) -> tuple[list[dict], dict]:
    """校验决定文件并补全(分配 shape_id、解析 $new、推出 after_seeing_outcome / list_kind / batch_id)。
    返回 (待追加的条目, 重算后的全部卡)。任何问题 → ShapeValidationError(列出全部)。"""
    errs: list[str] = []
    if not isinstance(decision, dict) or decision.get("schema") != DECISION_SCHEMA:
        raise ShapeValidationError([f"schema 必须是 {DECISION_SCHEMA}"])
    ops = decision.get("ops")
    if not isinstance(ops, list) or not ops:
        raise ShapeValidationError(["ops 必须是非空列表"])
    head_ctx = decision.get("ctx") or {}
    cards = replay(existing_ops)
    ids = set(cards) | {(o.get("target") or {}).get("shape_id") for o in existing_ops}
    last_new = None
    out = []
    for k, raw in enumerate(ops):
        path = f"ops[{k}]"
        if not isinstance(raw, dict):
            errs.append(f"{path}: 不是对象")
            continue
        if "ts" in raw or "op_id" in raw:
            errs.append(f"{path}: 不要自带 ts / op_id")
        op = copy.deepcopy(raw)
        op.setdefault("actor", decision.get("actor"))
        op.setdefault("surface", decision.get("surface"))
        op.setdefault("ctx", head_ctx)
        e = oplog.check_entry(op)
        if e:
            errs += [f"{path}: {m}" for m in e]
            continue
        act = op["act"]
        if act not in oplog.SHAPE_ACTS:
            out.append(op)
            continue
        op["target"] = dict(op.get("target") or {})
        v = op.get("value")
        sid = op["target"].get("shape_id")
        if act == "create_shape":
            if sid is None:
                sid = _next_id(ids)
            elif not SHAPE_ID_RE.fullmatch(str(sid)):
                errs.append(f"{path}: shape_id 不合法 {sid!r}")
                continue
            ids.add(sid)
            last_new = sid
        e = _validate_value(act, v, path)
        if e:
            errs += e
            continue
        if sid == NEW_REF:
            if last_new is None:
                errs.append(f"{path}: 用了 $new,但前面没有 create_shape")
                continue
            sid = last_new
        op["target"]["shape_id"] = sid
        if act in ("create_shape", "revise_shape"):
            refs = v.get("from_ann") or []
            missing = [a for a in refs if a not in anns]
            if missing:
                errs.append(f"{path}: from_ann 引用了不存在的标注 {missing}")
                continue
            if refs:
                v["after_seeing_outcome"] = any(anns[a]["outcome_visible"] for a in refs)
                kinds = {anns[a]["list_kind"] for a in refs}
                v["list_kind"] = kinds.pop() if len(kinds) == 1 else None
            else:
                v["after_seeing_outcome"] = bool(op["ctx"].get("outcome_visible", True))
                v["list_kind"] = op["ctx"].get("list_kind")
        if act == "add_case":
            a = anns.get(v["ann_id"])
            if a is None:
                errs.append(f"{path}: 标注 {v['ann_id']} 不存在")
                continue
            if v.get("batch_id") not in (None, a["batch_id"]):
                errs.append(f"{path}: 标注 {v['ann_id']} 在批次 {a['batch_id']},不是 {v['batch_id']}")
                continue
            v["batch_id"] = a["batch_id"]
        try:
            _step(cards, {**op, "ts": "预演"})
        except ValueError as ex:
            errs.append(f"{path}: {ex}")
            continue
        out.append(op)
    if errs:
        raise ShapeValidationError(errs)
    return out, cards


def apply(decision: dict) -> tuple[list[dict], list[str]]:
    """校验 → 追加日志 → 从全部日志重算受影响的卡 → 写卡。返回 (追加的条目, 受影响的 shape_id)。"""
    existing = oplog.read_all()
    ops, _ = prepare(decision, existing, _ann_index())
    written = oplog.append(ops)
    cards = replay(oplog.read_all())
    touched = sorted({o["target"]["shape_id"] for o in written if o["act"] in oplog.SHAPE_ACTS})
    for sid in touched:
        write_card(cards[sid])
    return written, touched


def rebuild(verify: bool) -> list[str]:
    """从日志从头重算全部卡。verify:与磁盘逐字比对,返回不一致清单;否则用重算结果覆盖磁盘。"""
    cards = replay(oplog.read_all())
    d = shapes_dir()
    on_disk = {p.stem for p in d.glob("*.json")} if d.exists() else set()
    problems = []
    for sid, card in sorted(cards.items()):
        p = d / f"{sid}.json"
        if verify:
            if not p.exists():
                problems.append(f"{sid}: 磁盘上没有这张卡")
            elif p.read_text() != canonical(card):
                problems.append(f"{sid}: 磁盘上的卡与日志重算结果不一致")
        else:
            write_card(card)
    for sid in sorted(on_disk - set(cards)):
        problems.append(f"{sid}: 磁盘上有这张卡,日志里没有")
    return problems


# ── 人话打印 ───────────────────────────────────────────────────────────────

def origin_text(rec: dict) -> str:
    o, by = rec.get("origin"), rec.get("suggested_by")
    if o == "user_written":
        t = "你自己说的"
    elif o == "suggested_adopted":
        t = f"采纳了{BY_TEXT.get(by, by)}的推荐"
    else:
        t = f"改过的{BY_TEXT.get(by, by)}推荐（原为 {_fmt(rec.get('suggested_value'))}）"
    if by == "own_library" and isinstance(rec.get("root"), dict):
        t += f"，最初是{origin_text(rec['root'])}"
    return t


def _fmt(x) -> str:
    if isinstance(x, list):
        return " / ".join(_fmt(i) for i in x)
    return "—" if x is None else str(x)


def _term_text(term: str, text: str | None = None) -> str:
    if term == "custom":
        return text or "(自己写的)"
    if term in ROWS:
        return f"{term} {ROWS[term][1]}"
    if term in TRIGGERS:
        return f"{term} {TRIGGERS[term][1]}"
    return f"{term} {INVALIDATIONS.get(term, '')}"


def render(card: dict) -> str:
    ver = card["versions"][-1]
    cc = ver["card"]
    lines = [f"{card['shape_id']} 「{card['name']['value']}」（{origin_text(card['name'])}）"
             f"  状态：{STATUS_TEXT.get(card['status'], card['status'])}"
             + (f"→ 并入 {card['merged_into']}" if card.get("merged_into") else "")
             + f"  当前版本 v{card['current_version']}"
             + ("（在看得到结果的清单上改出来的）" if ver["after_seeing_outcome"] else "（盲看时改出来的）")]
    if card["aliases"]:
        lines.append("  曾用名：" + "、".join(map(str, card["aliases"])))
    for role in ROLES:
        ings = [i for i in cc.get("ingredients", []) if i["role"] == role]
        if not ings:
            continue
        lines.append(f"  【{ROLE_TEXT[role]}】")
        for i in ings:
            ch = "；".join(f"{name}：{_fmt(c['value'])}（{origin_text(c)}）"
                          for name, c in (i.get("choices") or {}).items())
            lines.append(f"    · {_term_text(i['term'], i.get('text'))}（{origin_text(i)}）"
                         + (f"；{ch}" if ch else ""))
    if cc.get("triggers"):
        lines.append("  【触发】")
        for t in cc["triggers"]:
            lines.append(f"    · {t['trig_id']} {_term_text(t['term'], t.get('text'))}（{origin_text(t)}）")
    for key, label in (("story", "为什么会涨"), ("exit_pref", "卖法")):
        if cc.get(key):
            lines.append(f"  【{label}】{_fmt(cc[key]['value'])}（{origin_text(cc[key])}）")
    lines.append(f"  样本 {len(card['cases'])} 个"
                 + ("：" + "、".join(f"{c['ann_id'][:8]}@{_fmt(c['buy_date']['value'])}"
                                    for c in card["cases"][:10]) if card["cases"] else ""))
    return "\n".join(lines)


def _ledger_attempts() -> tuple[int, int]:
    """(累计尝试, 总行数):直接读账本文件,不 import 账本模块(它依赖对照模块)。"""
    p = state_root() / "ledger.jsonl"
    rows = [json.loads(x) for x in p.read_text().splitlines() if x.strip()] if p.exists() else []
    return sum(1 for r in rows if r.get("kind") != "bigmoves"), len(rows)


def render_pending() -> str:
    from chart_workflow.views import read_views

    cards = replay(oplog.read_all())
    lines = ["【现有形态卡】"]
    lines += [f"  {sid} 「{c['name']['value']}」 {STATUS_TEXT.get(c['status'], c['status'])} "
              f"v{c['current_version']}，样本 {len(c['cases'])} 个" for sid, c in sorted(cards.items())] \
        or ["  (还没有)"]
    used = {cs["ann_id"] for c in cards.values() for cs in c["cases"]}
    lines.append("\n【还没被任何形态卡的样本引用的标注(待处理,按批次)】")
    n_pending = 0
    for p, b, err in iter_batches(state_root() / "annotations"):
        if b is None:
            lines.append(f"  {p.name}:读不了({err})")
            continue
        todo = [a for a in b["annotations"] if a["label"] != "data_error" and a["ann_id"] not in used]
        if not todo:
            continue
        n_pending += len(todo)
        lines.append(f"  批次 {b['batch_id']}(清单 {b['list_id']}，"
                     f"{'看得到结果' if b['outcome_visible'] else '看不到结果'}):")
        for a in todo:
            bps = "、".join(("★" if bp["primary"] else "") + bp["date"] for bp in a["buy_points"]) or "无买点"
            lines.append(f"    · {a['ann_id']} {a['symbol']} {a['label']} 买点 {bps}"
                         + (f" 备注：{a['note']}" if a.get("note") else ""))
    if not n_pending:
        lines.append("  (没有)")
    lines.append("\n【操作日志最后 10 条】")
    ops = oplog.read_all()
    for o in ops[-10:]:
        tgt = o.get("target") or {}
        lines.append(f"  {o['ts']} {o['actor']} {o['act']} "
                     + " ".join(f"{k}={v}" for k, v in tgt.items()))
    if not ops:
        lines.append("  (还没有)")
    attempts, n_rows = _ledger_attempts()
    lines.append(f"\n看过记录 {len(read_views())} 条；账本 {n_rows} 行，累计尝试 {attempts} 次（大涨段轮不计入）")
    return "\n".join(lines)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="形态卡")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("apply", help="把一个决定文件写进操作日志和形态卡")
    a.add_argument("path")
    s = sub.add_parser("show")
    s.add_argument("shape_id", nargs="?")
    s.add_argument("--pending", action="store_true", help="给新会话接着推的一页汇总")
    r = sub.add_parser("rebuild")
    r.add_argument("--verify", action="store_true", help="只比对,不覆盖")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "apply":
            decision = json.loads(Path(args.path).read_text())
            written, touched = apply(decision)
            print(f"已写 {len(written)} 条操作日志 → {oplog.oplog_dir()}")
            for sid in touched:
                print(render(load_card(sid)))
        elif args.cmd == "show":
            if args.pending:
                print(render_pending())
            elif args.shape_id:
                print(render(load_card(args.shape_id)))
            else:
                cards = replay(oplog.read_all())
                print("\n\n".join(render(c) for _, c in sorted(cards.items())) or "(还没有形态卡)")
        else:
            problems = rebuild(args.verify)
            for p in problems:
                print(p)
            if args.verify:
                if problems:
                    sys.exit(1)
                print("全部形态卡与操作日志重算结果一致")
            else:
                print(f"已用日志重算结果覆盖形态卡 → {shapes_dir()}")
    except (ValueError, FileNotFoundError, StateRootMissing) as e:     # 含 ShapeValidationError
        print(f"错误:{e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
