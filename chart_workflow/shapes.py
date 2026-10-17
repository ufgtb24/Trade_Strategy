"""形态卡:一种形态引用哪些要素、各是什么角色、触发、为什么会涨、卖法。

要素(是 / 否条件,有自己的编号 E001…)在要素库里(elements.py),形态卡只引用要素编号,角色
(必须有 / 加分 / 有它就不买)写在卡上——同一条要素在不同形态里可以是不同角色。事实表的行(facts.py)
只是计算方法与每张图的结果,不进形态卡。口径分歧的回答,就是在两条候选要素里选一条。

操作日志(oplog.py)是唯一真相,形态卡与要素都是它的物化结果:replay(ops) 是纯函数,只看
create_shape / revise_shape / add_case / rename_shape / merge_shape / set_status 六类(要素的四类见
elements.py);摆过没选的、被拒的都只进日志、不进卡。写入流程:校验 → 追加日志 → 从全部日志重算受影响的
要素与卡 → 写文件(规范化 JSON:ensure_ascii=False, indent=1, sort_keys=True,先写临时文件再换名)。
要素与卡这两类操作只能经决定文件写进日志(oplog.append 拒绝直接写)。正常写入、账本取数、重算(rebuild)
前都先把日志里每条要素与卡的操作按顺序重新走一遍决定文件的校验(revalidate)。

校验规则分版本:每条日志写入时记下当时的校验版本号(rules_version,工具补),重走时按它自己的版本用当时的
规则——规则收紧不追溯旧条目。两种结果分开报:
  · 连它自己那一版的规则都不合格、或者校验补全后和日志里记的不一样(工具补的字段对不上)、或者版本号比前面的
    条目旧 / 不认识 → 日志可能被改过(手写进日志、改过工具补的字段),拦:写入和账本取数都停,重算不覆盖磁盘;
  · 在它那一版合法、按现在的规则不再允许 → 只提示(rebuild --verify 逐条列出,其余入口提示一句),不拦。
各版的差别(没有版本号的旧条目算第 1 版):
  第 1 版:卡上要素项可以没记要素版本号(那时判定一律按最新版本);卡上角色记成用户定的不必带原话;
          根数的上界按整个看图范围(看图下界到训练段末日的工作日数,与默认回看取大);
          between 一端碰到值的上下界就拒绝(要求写成 at_least / at_most)。
  第 2 版:卡上每个要素项都记要素版本号;角色记成用户定的要带 said_first_match;根数的上界按规则逐日判时的
          事实表窗口(买点前 default_lookback_bars 根加买点);between 一端碰到值本来就取不到的硬边界时规范化成
          at_least / at_most,只落在「合理范围」之外的软边界原样保留两端、只给提示(elements 模块说明)。

    uv run python -m chart_workflow.shapes apply <决定.json>
    uv run python -m chart_workflow.shapes show [<shape_id>]
    uv run python -m chart_workflow.shapes show --pending
    uv run python -m chart_workflow.shapes rebuild [--verify]     # 形态卡与要素一起重算 / 比对

来源记录(每个会变成规则条件的值包一层;数值门槛不包):
{"value": ..., "origin": "user_written | suggested_adopted | suggested_edited",
 "suggested_by": "own_library | detector | llm | general_knowledge | session",
 "suggested_value": ..., "said_first_match": "用户先说的一句里对得上的原话",
 "from_card": {"shape_id": "s001", "version": 2, "ref": "i1"},   # own_library 复用时会话只填这个
 "root": {<own_library 复用时,那条值当初入库时的来源记录,由工具从旧卡里抄>}}
规则(validate,任一不过就拒绝写入并列出全部问题):origin 必填;推荐来的(adopted / edited)要写
suggested_by;改过的推荐要带 suggested_value(用户自己写的也可以带,记下当时摆着的推荐);
触发引用触发候选(term 不是 custom)时永远算推荐——推荐来的只能是 detector 或 own_library,
用户自己写的(手写触发 custom 也一样)必须带非空 said_first_match;卡上要素项的角色记成用户定的,同样要带。
形态卡上要素那一项的来源记录记的是「角色是谁定的」(把这条要素以这个角色放进这个形态);
要素本身是谁提的记在要素库里。
从你以前的形态卡复用(own_library)时,会话只填 from_card:旧卡编号 shape_id、版本 version、编号 ref
(要素那一项 ing_id、触发 trig_id、story、exit_pref),只能从同一类的项抄(故事从故事、触发从触发);
不接受会话自带的 root。工具去旧卡那个版本里找到那一条,把它当初的来源(它本身也是复用的,就取它的 root,一直到底)抄成 root;引用的要素(合并过的按并入
的那条比)或触发编号和旧卡那一条对不上、卡 / 版本 / 那一条不存在,都拒绝。算条件构成时递归到 root,
防止采纳过的系统推荐经用户的卡转一手被洗成用户来源。
包一层的粒度:每个要素项、每个触发、每个分歧答案、形态名字、story、exit_pref、每个样本的买点与形态认领。

形态卡 <状态根>/shapes/<shape_id>.json(chart_workflow.shape/1):
{"schema", "shape_id": "s001", "name": <来源记录>, "aliases": [旧名], "status": "draft | confirmed |
 in_trial | judged | merged", "merged_into": null, "current_version": 1,
 "versions": [{"version", "ts", "change", "after_seeing_outcome", "list_kind", "from_ann",
               "card": {"ingredients": [{"ing_id", "element": "E001", "role": "must | bonus | must_not",
                                          "element_version": <这一版建立时那条要素的版本号,工具填>,
                                          <来源记录字段:角色是谁定的>}],
                        "triggers": [{"trig_id", "term": "T1..T8 | custom", "text", <来源记录字段>}],
                        "story": <来源记录> | null, "exit_pref": <来源记录> | null}}],
 "cases": [{"ann_id", "batch_id", "buy_date": <来源记录>, "trigger_ref": "t1", "shape_claim": <来源记录>,
            "divergence_answers": [{"dvid", "options": ["E001", "E002"], "choice": <来源记录,value 是选中的要素>}],
            "facts_ref", "version"}]}
新写的卡版本只能引用要素库里在用或待写代码的要素(合并过的要引用它并入的那条),同一条要素在一张卡里
只出现一次;旧版本里引用的编号合并后照常能解析(elements.resolve)。判定、打印、账本都按卡上记下的
要素版本取定义和来源(旧日志里的卡没记版本号的,取那条要素自己的当前版本)。
版本只追加;改名只改 name,旧名进 aliases;合并时被并的卡写 status = merged 与 merged_into。
after_seeing_outcome 由这一版引用的标注(from_ann)所在批次头的 outcome_visible 推出(v1 批次按 true;
没引用标注时取决定文件 ctx 的 outcome_visible,缺省按 true),apply 时算好写进日志,replay 只照抄。
show --pending 会提示可能重复的卡:两张卡当前版本引用的要素与角色、触发都相同(只提示,合并要用户确认后
显式 merge_shape)。

决定文件(会话把聊天里定下的一批东西写成一个文件,一次写进日志、要素和卡;全部校验通过才写,任何一条不过
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
四类要素操作(create_element / revise_element / alias_element / merge_element)见 elements.py。
同一个决定文件里,后面的操作用 shape_id = "$new" 指这个文件里最近一次 create_shape 建的卡;
create_element 带 target.as 时,后面用 "$<as>" 指它建的要素(卡上的 element、分歧的选项与答案、
要素操作的 target 与 into 都可以这样写)。

红线:不 import 标签口径(labels)、对照(control)、面板(panel)、清单(listfile),不读清单文件。
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from pathlib import Path

from chart_workflow import elements as E
from chart_workflow import oplog
from chart_workflow.annotations import iter_batches
from chart_workflow.facts import INVALIDATIONS, ROWS, TRIGGERS
from chart_workflow.state import StateRootMissing, state_root

SCHEMA = "chart_workflow.shape/1"
DECISION_SCHEMA = "chart_workflow.decision/1"
ORIGINS = E.ORIGINS
SUGGESTED_BY = ("own_library", "detector", "llm", "general_knowledge", "session")
ROLES = ("must", "bonus", "must_not")
STATUSES = ("draft", "confirmed", "in_trial", "judged", "merged")
ORIGIN_FIELDS = ("origin", "suggested_by", "suggested_value", "said_first_match", "from_card", "root")
ROOT_FIELDS = ("origin", "suggested_by", "suggested_value", "said_first_match")
SHAPE_ID_RE = re.compile(r"^s(\d{3,})$")
NEW_REF = "$new"
TRIGGER_TERMS = tuple(TRIGGERS) + ("custom",)
ING_FIELDS = ("ing_id", "element", "role") + ORIGIN_FIELDS
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

def validate(rec, path: str, term: str | None = None, wrapped: bool = True, role: bool = False) -> list[str]:
    """一条来源记录的问题清单。wrapped:要求带 value(要素项 / 触发的来源字段直接摊在条目上,不带 value)。
    term:这个值引用的触发候选编号(custom 或 None 表示不引用)。role:这是卡上要素项的来源(角色是谁定的)。"""
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
    if term == "custom" and origin == "user_written" and not str(rec.get("said_first_match") or "").strip():
        errs.append(f"{path}: 自己写的触发记成用户说的,要带 said_first_match(用户原话)")
    if role and origin == "user_written" and oplog.rules_now() >= 2 \
            and not str(rec.get("said_first_match") or "").strip():
        errs.append(f"{path}: 角色记成用户定的,要带 said_first_match(用户原话)")
    refs_table = term is not None and term != "custom"
    if refs_table:
        if origin == "user_written" and not str(rec.get("said_first_match") or "").strip():
            errs.append(f"{path}: 引用 {term} 却记成用户自己写的,要带 said_first_match(用户先说的原话)")
        if origin in ("suggested_adopted", "suggested_edited") and by not in ("detector", "own_library",
                                                                              None):
            errs.append(f"{path}: {term} 是事实脚本给的触发候选,推荐来源只能是 detector 或 own_library")
    if "root" in rec:
        errs.append(f"{path}: 不要自带 root;复用旧卡只给 from_card(旧卡编号、版本、要素编号),"
                    f"当初的来源由工具从旧卡里抄")
    fc = rec.get("from_card")
    if by == "own_library":
        if not (isinstance(fc, dict) and isinstance(fc.get("shape_id"), str)
                and isinstance(fc.get("version"), int) and not isinstance(fc.get("version"), bool)
                and isinstance(fc.get("ref"), str) and fc["ref"]):
            errs.append(f"{path}: 从你以前的形态卡复用的值要带 from_card "
                        f"{{shape_id, version(整数), ref(要素编号)}}")
    elif fc is not None:
        errs.append(f"{path}: 只有 suggested_by = own_library 的值才带 from_card")
    return errs


def _element(card: dict, ref: str) -> tuple[dict | None, tuple | None, str | None]:
    """卡的某个版本里 ref 指的那一条、它引用的东西(要素项 → ("element", 编号),触发 → ("term", 编号);
    story、exit_pref 没有引用,为 None)和它是哪一类(ingredient / trigger / story / exit_pref)。"""
    for ing in card.get("ingredients", []):
        if ing.get("ing_id") == ref:
            return ing, ("element", ing.get("element")), "ingredient"
    for t in card.get("triggers", []):
        if t.get("trig_id") == ref:
            return t, ("term", t.get("term")), "trigger"
    if ref in ("story", "exit_pref") and isinstance(card.get(ref), dict):
        return card[ref], None, ref
    return None, None, None


def _kind_of(sub: str) -> str:
    """value 里一条来源记录是哪一类(按它在 value 里的位置)。"""
    if sub.startswith("card.ingredients"):
        return "ingredient"
    if sub.startswith("card.triggers"):
        return "trigger"
    if sub.startswith("card."):
        return sub[len("card."):]
    if sub.startswith("divergence_answers"):
        return "divergence_choice"
    return sub


def _bottom(el: dict) -> dict:
    """一条值当初的来源:它本身是复用的就取它的 root(已到底),否则取它自己的来源字段。"""
    if el.get("suggested_by") == "own_library" and isinstance(el.get("root"), dict):
        return copy.deepcopy(el["root"])
    return {k: copy.deepcopy(el[k]) for k in ROOT_FIELDS if k in el}


def _origin_records(act: str, v: dict):
    """一条形态操作 value 里所有来源记录:(记录, 引用的东西, 路径)。"""
    if act in ("create_shape", "rename_shape") and isinstance(v.get("name"), dict):
        yield v["name"], None, "name"
    card = v.get("card") if act in ("create_shape", "revise_shape") else None
    if isinstance(card, dict):
        for k, ing in enumerate(card.get("ingredients", [])):
            if isinstance(ing, dict):
                yield ing, ("element", ing.get("element")), f"card.ingredients[{k}]"
        for k, t in enumerate(card.get("triggers", [])):
            if isinstance(t, dict):
                yield t, ("term", t.get("term")), f"card.triggers[{k}]"
        for key in ("story", "exit_pref"):
            if isinstance(card.get(key), dict):
                yield card[key], None, f"card.{key}"
    if act == "add_case":
        for key in ("buy_date", "shape_claim"):
            if isinstance(v.get(key), dict):
                yield v[key], None, key
        for k, da in enumerate(v.get("divergence_answers") or []):
            if isinstance(da.get("choice"), dict):
                yield da["choice"], None, f"divergence_answers[{k}].choice"


def _same_ref(new, old, els: dict) -> bool:
    """复用时引用的东西是否相同:要素按合并后解析到的那条比,触发按编号比。"""
    if new is None or old is None:
        return new == old
    if new[0] != old[0]:
        return False
    if new[0] == "element" and new[1] in els and old[1] in els:
        return E.resolve(els, new[1]) == E.resolve(els, old[1])
    return new[1] == old[1]


def resolve_own_library(act: str, v: dict, cards: dict, els: dict, path: str) -> list[str]:
    """把 value 里每条 own_library 复用的 root 从旧卡里抄过来(就地改)。返回问题清单。"""
    errs = []
    for rec, ref, sub in _origin_records(act, v):
        if rec.get("suggested_by") != "own_library":
            continue
        fc = rec["from_card"]
        where = f"{path}.{sub}"
        card = cards.get(fc["shape_id"])
        if card is None:
            errs.append(f"{where}: 旧卡 {fc['shape_id']} 不存在")
            continue
        ver = next((x for x in card["versions"] if x["version"] == fc["version"]), None)
        if ver is None:
            errs.append(f"{where}: 旧卡 {fc['shape_id']} 没有版本 v{fc['version']}")
            continue
        el, old_ref, old_kind = _element(ver["card"], fc["ref"])
        if el is None:
            errs.append(f"{where}: 旧卡 {fc['shape_id']} v{fc['version']} 里没有 {fc['ref']!r}")
            continue
        if old_kind != _kind_of(sub):
            errs.append(f"{where}: 只能从旧卡同一类的项复用来源(这一项是 {_kind_of(sub)},"
                        f"旧卡的 {fc['ref']!r} 是 {old_kind})")
            continue
        if ref is not None and not _same_ref(ref, old_ref, els):
            errs.append(f"{where}: 引用 {ref[1]},旧卡那一条引用的是 {old_ref[1] if old_ref else '别的东西'},"
                        f"不是同一个东西")
            continue
        rec["root"] = _bottom(el)
    return errs


def validate_card(card, path: str, els: dict) -> list[str]:
    """一个卡版本的格式,以及它引用的要素是否在要素库里(els 是预演状态)。"""
    if not isinstance(card, dict):
        return [f"{path}: 不是对象"]
    errs = []
    extra = set(card) - {"ingredients", "triggers", "story", "exit_pref"}
    if extra:
        errs.append(f"{path}: 未知字段 {sorted(extra)}")
    ings = card.get("ingredients", [])
    if not isinstance(ings, list):
        return errs + [f"{path}.ingredients: 必须是列表"]
    seen, used = set(), {}
    for k, ing in enumerate(ings):
        p = f"{path}.ingredients[{k}]"
        if not isinstance(ing, dict):
            errs.append(f"{p}: 不是对象")
            continue
        extra = set(ing) - set(ING_FIELDS)
        if extra:
            errs.append(f"{p}: 未知字段 {sorted(extra)}(要素项只写 ing_id、element、role 和来源记录;"
                        f"条件、口径、参数在要素库里)")
        iid, eid = ing.get("ing_id"), ing.get("element")
        if not isinstance(iid, str) or not iid or iid in seen:
            errs.append(f"{p}: ing_id 缺失或重复 {iid!r}")
        seen.add(iid)
        if eid not in els:
            errs.append(f"{p}: 要素 {eid!r} 不在要素库里(先 create_element;现有事实算不出的也建一条待写代码的)")
        elif els[eid]["status"] == "merged":
            errs.append(f"{p}: {eid} 已合并到 {E.resolve(els, eid)},引用 {E.resolve(els, eid)}")
        elif eid in used:
            errs.append(f"{p}: 要素 {eid} 在这张卡里已经出现过({used[eid]}),一张卡里只出现一次")
        else:
            used[eid] = iid
        if ing.get("role") not in ROLES:
            errs.append(f"{p}: role 只能是 {'/'.join(ROLES)}")
        errs += validate(ing, p, None, wrapped=False, role=True)
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


def _validate_value(act: str, v, path: str, els: dict) -> list[str]:
    """六类形态操作 value 的格式(要素引用对 els 核对)。"""
    if not isinstance(v, dict):
        return [f"{path}: value 必须是对象"]
    errs = []
    if act in ("create_shape", "rename_shape"):
        errs += validate(v.get("name"), f"{path}.name")
        if isinstance(v.get("name"), dict) and not str(v["name"].get("value") or "").strip():
            errs.append(f"{path}.name: 名字不能为空")
    if act in ("create_shape", "revise_shape"):
        errs += validate_card(v.get("card"), f"{path}.card", els)
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
            p = f"{path}.divergence_answers[{k}]"
            if not isinstance(da, dict) or not isinstance(da.get("dvid"), str):
                errs.append(f"{p}: 要有 dvid")
                continue
            opts = da.get("options")
            if not (isinstance(opts, list) and len(opts) >= 2 and len(set(map(str, opts))) == len(opts)):
                errs.append(f"{p}: options 是两条以上不同的候选要素编号(口径分歧就是在候选要素里选一条)")
            else:
                miss = [o for o in opts if o not in els]
                if miss:
                    errs.append(f"{p}: 候选要素 {miss} 不在要素库里")
            errs += validate(da.get("choice"), f"{p}.choice")
            if isinstance(opts, list) and isinstance(da.get("choice"), dict) \
                    and da["choice"].get("value") not in opts:
                errs.append(f"{p}.choice: 选的要从 options 里挑")
    if act == "merge_shape" and not isinstance(v.get("into"), str):
        errs.append(f"{path}: into 必填")
    if act == "set_status" and v.get("status") not in STATUSES[:-1]:
        errs.append(f"{path}: status 只能是 {'/'.join(STATUSES[:-1])}(并卡用 merge_shape)")
    return errs


def _subst_refs(act: str, v, local: dict, path: str) -> list[str]:
    """形态操作里的 "$<as>" 换成同一决定文件里 create_element 分到的编号(就地改)。"""
    errs: list[str] = []
    if not isinstance(v, dict):
        return errs
    card = v.get("card") if act in ("create_shape", "revise_shape") else None
    if isinstance(card, dict):
        for k, ing in enumerate(card.get("ingredients") or []):
            if isinstance(ing, dict) and "element" in ing:
                ing["element"] = E.subst(ing["element"], local, f"{path}.card.ingredients[{k}].element", errs)
    if act == "add_case":
        for k, da in enumerate(v.get("divergence_answers") or []):
            if not isinstance(da, dict):
                continue
            if isinstance(da.get("options"), list):
                da["options"] = [E.subst(o, local, f"{path}.divergence_answers[{k}].options", errs)
                                 for o in da["options"]]
            if isinstance(da.get("choice"), dict) and "value" in da["choice"]:
                da["choice"]["value"] = E.subst(da["choice"]["value"], local,
                                                f"{path}.divergence_answers[{k}].choice", errs)
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


class _State:
    """预演状态:卡、要素、用过的 shape_id。"""

    def __init__(self, ops: list[dict]):
        self.cards = replay(ops)
        self.els = E.replay(ops)
        self.ids = set(self.cards) | {(o.get("target") or {}).get("shape_id") for o in ops}


def _prepare_ops(raw_ops: list, head: dict, st: _State, anns: dict, where) -> tuple[list[dict], list[str]]:
    """逐条校验并补全(分配 shape_id / element_id、解析 $new 与 $<as>、规范化要素定义、抄 own_library 的
    root、记下卡上每个要素当时的版本号、推出 after_seeing_outcome / list_kind / batch_id),合格的作用到
    预演状态 st 上。where(k):第 k 条的位置说明。返回 (补全后的条目, 问题清单)。"""
    errs: list[str] = []
    head_ctx = head.get("ctx") or {}
    local: dict[str, str] = {}                       # create_element 的 as → 分到的编号
    last_new = None
    out = []
    for k, raw in enumerate(raw_ops):
        path = where(k)
        if not isinstance(raw, dict):
            errs.append(f"{path}: 不是对象")
            continue
        if any(k in raw for k in oplog.TOOL_FIELDS):
            errs.append(f"{path}: 不要自带 {' / '.join(oplog.TOOL_FIELDS)}")
        op = copy.deepcopy(raw)
        op.setdefault("actor", head.get("actor"))
        op.setdefault("surface", head.get("surface"))
        op.setdefault("ctx", head_ctx)
        e = oplog.check_entry(op)
        if e:
            errs += [f"{path}: {m}" for m in e]
            continue
        act = op["act"]
        if act in oplog.ELEMENT_ACTS:
            e = E.prepare_op(op, st.els, local, path)
            if e:
                errs += e
                continue
            out.append(op)
            continue
        if act not in oplog.SHAPE_ACTS:
            out.append(op)
            continue
        op["target"] = dict(op.get("target") or {})
        v = op.get("value")
        e = _subst_refs(act, v, local, path)
        if e:
            errs += e
            continue
        sid = op["target"].get("shape_id")
        if act == "create_shape":
            if sid is None:
                sid = _next_id(st.ids)
            elif not SHAPE_ID_RE.fullmatch(str(sid)):
                errs.append(f"{path}: shape_id 不合法 {sid!r}")
                continue
            st.ids.add(sid)
            last_new = sid
        e = _validate_value(act, v, path, st.els)
        if e:
            errs += e
            continue
        e = resolve_own_library(act, v, st.cards, st.els, path)
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
            for ing in v["card"].get("ingredients", []):      # 记下卡这一版引用的每个要素当时的版本
                ing["element_version"] = st.els[ing["element"]]["current_version"]
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
            _step(st.cards, {**op, "ts": "预演"})
        except ValueError as ex:
            errs.append(f"{path}: {ex}")
            continue
        out.append(op)
    return out, errs


def prepare(decision: dict, existing_ops: list[dict], anns: dict) -> tuple[list[dict], dict]:
    """校验决定文件并补全(见 _prepare_ops)。返回 (待追加的条目, 重算后的全部卡)。
    任何问题 → ShapeValidationError(列出全部)。"""
    if not isinstance(decision, dict) or decision.get("schema") != DECISION_SCHEMA:
        raise ShapeValidationError([f"schema 必须是 {DECISION_SCHEMA}"])
    ops = decision.get("ops")
    if not isinstance(ops, list) or not ops:
        raise ShapeValidationError(["ops 必须是非空列表"])
    st = _State(existing_ops)
    out, errs = _prepare_ops(ops, decision, st, anns, lambda k: f"ops[{k}]")
    if errs:
        raise ShapeValidationError(errs)
    return out, st.cards


def _as_decision_op(op: dict) -> dict:
    """日志里的一条要素 / 卡操作还原成决定文件里的写法:去掉 ts / op_id / rules_version 和工具补的东西
    (own_library 抄来的 root、卡上记下的要素版本号),好让它重新走一遍决定文件的校验。"""
    raw = copy.deepcopy({k: v for k, v in op.items() if k not in oplog.TOOL_FIELDS})
    v = raw.get("value")
    if raw.get("act") in oplog.SHAPE_ACTS and isinstance(v, dict):
        for rec, _, _ in _origin_records(raw["act"], v):
            if rec.get("suggested_by") == "own_library":
                rec.pop("root", None)
        card = v.get("card") if isinstance(v.get("card"), dict) else {}
        for ing in card.get("ingredients") or []:
            if isinstance(ing, dict):
                ing.pop("element_version", None)
    return raw


def _old_format_tolerant(redone: dict, logged: dict) -> dict:
    """第 1 版的卡可以没记要素版本号(那时判定一律按最新版本):日志里没有这个字段的,重算结果也去掉再比。
    只容忍「没有」,记了而且和重算的不同照样算对不上;只给第 1 版的条目用(见 revalidate)。"""
    v, lv = redone.get("value"), logged.get("value")
    if redone.get("act") not in ("create_shape", "revise_shape") or not isinstance(lv, dict):
        return redone
    old = [i for i in ((lv.get("card") or {}).get("ingredients") or []) if isinstance(i, dict)]
    if not old or any("element_version" in i for i in old):
        return redone
    redone = copy.deepcopy(redone)
    for ing in redone["value"]["card"].get("ingredients", []):
        ing.pop("element_version", None)
    return redone


def _redo(op: dict, st: "_State", anns: dict, version: int, where) -> tuple[list[str], bool]:
    """按第 version 版的规则把这一条重新走一遍决定文件的校验(在 st 的副本上):(问题, 补全结果和日志里一样吗)。"""
    trial = copy.deepcopy(st)
    with oplog.rules_at(version):
        out, errs = _prepare_ops([_as_decision_op(op)], {}, trial, anns, where)
    if errs:
        return errs, False
    redone = {**out[0], "ts": op.get("ts"), "op_id": op.get("op_id")}
    if "rules_version" in op:
        redone["rules_version"] = op["rules_version"]
    if version == 1:
        redone = _old_format_tolerant(redone, op)
    return [], redone == op


def revalidate(ops: list[dict], anns: dict) -> tuple[list[str], list[str]]:
    """把日志里每条要素与形态卡的操作按顺序重新走一遍决定文件的校验(当时的状态 = 它前面的日志重算出来的),
    每条按它自己的校验版本号(没有算第 1 版)用当时的规则。返回 (问题, 提示):
    问题 = 连自己那一版都不合格、补全结果和日志里记的不一样、版本号不认识或比前面的条目旧(可能被改过,拦);
    提示 = 在自己那一版合法、按现在的规则不再允许(只提示)。直接写进日志、绕开决定文件的操作在这里现形。"""
    st = _State([])
    problems, notices = [], []
    newest = 1
    for k, op in enumerate(ops):
        act = op.get("act")
        v = op.get("rules_version")
        v = 1 if v is None else v
        where = lambda _, k=k, op=op: f"日志第 {k + 1} 条({op.get('act')},{op.get('op_id')})"
        if act in oplog.SHAPE_ACTS or act in oplog.ELEMENT_ACTS:
            if not isinstance(v, int) or isinstance(v, bool) or not 1 <= v <= oplog.RULES_VERSION:
                problems.append(f"{where(0)}: 校验版本号 {v!r} 不认识(现在的工具是第 {oplog.RULES_VERSION} 版),"
                                f"可能被改过,或者是更新的工具写的")
            elif v < newest:
                problems.append(f"{where(0)}: 校验版本号是第 {v} 版,比前面的条目(第 {newest} 版)旧,可能被改过")
            else:
                errs, same = _redo(op, st, anns, v, where)
                if errs:
                    problems += [f"{m}(这条连写入时的第 {v} 版规则都不合格,可能被改过)" for m in errs]
                elif not same:
                    problems.append(f"{where(0)}: 重新校验补全后和日志里记的不一样(日志被改过,或没经决定文件写入)")
                elif v < oplog.RULES_VERSION:
                    errs, same = _redo(op, st, anns, oplog.RULES_VERSION, where)
                    if errs or not same:
                        why = ";".join(m.split(": ", 1)[-1] for m in errs) or "按现在的规则补全出来的样子不同"
                        notices.append(f"{where(0)}: 写入时按第 {v} 版规则合法,现在的规则不再允许(只提示,不影响使用):{why}")
        if isinstance(v, int) and not isinstance(v, bool):
            newest = max(newest, v)
        try:
            E.step(st.els, op)
            _step(st.cards, op)
        except ValueError as ex:
            problems.append(f"日志第 {k + 1} 条({act},{op.get('op_id')}): {ex}")
        sid = (op.get("target") or {}).get("shape_id")
        if sid:
            st.ids.add(sid)
    return problems, notices


def touched_elements(ops: list[dict]) -> list[str]:
    out = set()
    for o in ops:
        if o["act"] in oplog.ELEMENT_ACTS:
            out.add(o["target"]["element_id"])
            if o["act"] == "merge_element":
                out.add(o["value"]["into"])
    return sorted(out)


def checked_ops() -> list[dict]:
    """读全部操作日志,先把每条要素与卡的操作重走一遍决定文件的校验(revalidate);有问题(可能被改过)→
    ShapeValidationError,列出是哪几条;只有提示(旧版合法、现在不再允许)时在标准错误提示一句、照常返回。
    正常写入之前、账本取数之前都先过这一道。"""
    ops = oplog.read_all()
    bad, notices = revalidate(ops, _ann_index())
    if bad:
        raise ShapeValidationError(["操作日志里有可能被改过的条目(手写进日志、改过工具补的字段),先处理:"] + bad)
    if notices:
        print(f"提示:操作日志里有 {len(notices)} 条是按旧版校验规则写的,当时合法、现在的规则不再允许"
              f"(只提示,不影响使用;逐条看:python -m chart_workflow.shapes rebuild --verify)", file=sys.stderr)
    return ops


def checked_state() -> tuple[list[dict], dict, dict]:
    """(全部日志, 卡, 要素):日志先过 checked_ops,卡与要素从日志重算,不读磁盘上的卡与要素文件。"""
    ops = checked_ops()
    return ops, replay(ops), E.replay(ops)


def apply(decision: dict) -> tuple[list[dict], list[str]]:
    """校验(先重走全部日志,再校验这个决定文件)→ 追加日志 → 从全部日志重算受影响的要素与卡 → 写文件。
    返回 (追加的条目, 受影响的 shape_id);受影响的要素编号见 touched_elements(追加的条目)。"""
    existing = checked_ops()
    ops, _ = prepare(decision, existing, _ann_index())
    written = oplog.append(ops, oplog.VIA_DECISION)
    all_ops = oplog.read_all()
    E.write_all(E.replay(all_ops), touched_elements(written))
    cards = replay(all_ops)
    touched = sorted({o["target"]["shape_id"] for o in written if o["act"] in oplog.SHAPE_ACTS})
    for sid in touched:
        write_card(cards[sid])
    return written, touched


def rebuild(verify: bool) -> list[str]:
    """从日志从头重算全部要素与卡。先把每条要素与卡的操作重新走一遍决定文件的校验(revalidate):
    verify 时把有问题的列进返回的问题清单;不 verify 时有问题就 ShapeValidationError,不覆盖磁盘。
    只是提示的(旧版合法、现在不再允许)逐条打到标准错误,不进问题清单。
    verify:与磁盘逐字比对,返回不一致清单;否则用重算结果覆盖磁盘。"""
    bad, notices = revalidate(oplog.read_all(), _ann_index())
    if bad and not verify:
        raise ShapeValidationError(bad)
    for m in notices:
        print(f"提示:{m}", file=sys.stderr)
    problems = bad + E.rebuild(verify)
    cards = replay(oplog.read_all())
    d = shapes_dir()
    on_disk = {p.stem for p in d.glob("*.json")} if d.exists() else set()
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
    if term in ROWS:                              # 旧格式的要素项(引用事实行编号)只用于打印
        return f"{term} {ROWS[term]['title']}"
    if term in TRIGGERS:
        return f"{term} {TRIGGERS[term][1]}"
    return f"{term} {INVALIDATIONS.get(term, '')}"


def _ing_text(i: dict, els: dict) -> str:
    """卡上一个要素项:编号「名字」:条件(角色是谁定的)。条件按卡上记下的那一版要素(旧卡没记版本就取
    这条要素自己的当前版本),不跟后来的修订与合并。"""
    if "element" not in i:
        return f"{_term_text(i.get('term'), i.get('text'))}（{origin_text(i)}）"
    eid = i["element"]
    s = E.label(els, eid)
    if eid in els:
        n = i.get("element_version")
        ver = E.element_version(els, eid, n) if n else els[eid]["versions"][-1]
        d = ver.get("definition")
        s += f"：{E.definition_text(d)}" if d is not None else "：卡这一版建立时待写代码"
        if n and n != els[eid]["current_version"]:
            s += f"（卡上记的是 v{n}，要素现在是 v{els[eid]['current_version']}）"
    return s + f"（角色：{origin_text(i)}）"


def render(card: dict, els: dict | None = None) -> str:
    """一张卡的人话打印。els:要素库(缺省从操作日志重算)。"""
    els = E.replay(oplog.read_all()) if els is None else els
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
            lines.append(f"    · {_ing_text(i, els)}")
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


def possible_duplicates(cards: dict, els: dict) -> list[list[str]]:
    """当前版本引用的要素(按合并后解析)与角色、触发(编号与自写文字)都相同的卡,两张以上成一组。
    只是提示:绝不自动合并。"""
    groups: dict[str, list[str]] = {}
    for sid, c in sorted(cards.items()):
        if c["status"] == "merged":
            continue
        cc = c["versions"][-1]["card"]
        ings = sorted((E.resolve(els, i["element"]) if i.get("element") in els else str(i.get("element")),
                       i.get("role")) for i in cc.get("ingredients", []))
        trigs = sorted((t.get("term"), " ".join(str(t.get("text") or "").split()))
                       for t in cc.get("triggers", []))
        groups.setdefault(json.dumps([ings, trigs], ensure_ascii=False), []).append(sid)
    return [g for g in groups.values() if len(g) > 1]


def render_pending() -> str:
    from chart_workflow.views import read_views

    ops = oplog.read_all()
    cards = replay(ops)
    els = E.replay(ops)
    lines = ["【现有形态卡】"]
    lines += [f"  {sid} 「{c['name']['value']}」 {STATUS_TEXT.get(c['status'], c['status'])} "
              f"v{c['current_version']}，样本 {len(c['cases'])} 个" for sid, c in sorted(cards.items())] \
        or ["  (还没有)"]
    dups = possible_duplicates(cards, els)
    if dups:
        lines.append("\n【可能重复的形态卡(引用的要素和角色、触发都相同;要不要合并,问过用户再 merge_shape)】")
        lines += [f"  {'、'.join(g)}" for g in dups]
    todo = [eid for eid, el in sorted(els.items()) if el["status"] == "pending_code"]
    lines.append(f"\n【要素库】在用 {sum(el['status'] == 'active' for el in els.values())} 条，"
                 f"待写代码 {len(todo)} 条，已合并 {sum(el['status'] == 'merged' for el in els.values())} 条")
    lines += [f"  待写代码 {E.label(els, eid)}：{els[eid]['versions'][-1].get('needs')}" for eid in todo]
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
            els = E.replay(oplog.read_all())
            all_ops = oplog.read_all()
            for eid in touched_elements(written):
                print(E.render(els[eid], all_ops))
            for sid in touched:
                print(render(load_card(sid), els))
        elif args.cmd == "show":
            if args.pending:
                print(render_pending())
            elif args.shape_id:
                print(render(load_card(args.shape_id)))
            else:
                ops = oplog.read_all()
                cards, els = replay(ops), E.replay(ops)
                print("\n\n".join(render(c, els) for _, c in sorted(cards.items())) or "(还没有形态卡)")
        else:
            problems = rebuild(args.verify)
            for p in problems:
                print(p)
            if args.verify:
                if problems:
                    sys.exit(1)
                print("全部要素与形态卡和操作日志重算结果一致")
            else:
                print(f"已用日志重算结果覆盖要素与形态卡 → {E.elements_dir()}、{shapes_dir()}")
    except (ValueError, FileNotFoundError, StateRootMissing) as e:     # 含 ShapeValidationError
        print(f"错误:{e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
