"""要素库:在事实表的行上定出来的是 / 否条件,有自己的编号(E001…),可被几个形态共用。

事实与要素分开:事实(facts.py)只是计算方法加每张图的结果,只给数值和描述、不带判断,没有角色、
不进形态卡;要素是在事实上定出来的是 / 否条件(如「按收盘至少越过一个峰」「最近 20 根里有派发」)。
形态卡引用要素编号,角色(必须有 / 加分 / 有它就不买)写在卡上,同一条要素在不同形态里可以是不同角色。
读同一行事实、条件不同,就是不同的要素(「按收盘至少越过一个峰」与「按收盘连续越过两个峰」)。

    uv run python -m chart_workflow.elements show [<element_id>]
    uv run python -m chart_workflow.elements conds                    # 代码里能算的条件类型
    uv run python -m chart_workflow.elements find --cond C [--variant V] [--param k=v ...]
    uv run python -m chart_workflow.elements eval --facts <事实表快照> [--element E001 ...] [--shape s001]

条件类型(CONDITIONS,写在代码里):每种写明读哪一行事实(按口径分,如按收盘读 F01、按最高价读 F02)、
参数与系统默认值(待验证)、判定函数。现有条件类型算不出的,要素先记「待写代码」。

要素文件 <状态根>/elements/<element_id>.json(chart_workflow.element/1),是操作日志的物化结果
(replay 是纯函数),版本只追加:
{"schema", "element_id": "E001", "name": <来源记录,尽量是用户原话>,
 "origin", "suggested_by", "said_first_match", "suggested_value",     # 谁提的(来源记录字段)
 "aliases": [{"text", "ts", "op_id", "actor", "from"(合并过来的才有)}],
 "status": "active | pending_code | merged", "merged_into": null, "current_version": 1,
 "versions": [{"version", "ts", "op_id", "change", "needs",
               "definition": {"reads": ["F01"], "cond": "peaks_cleared", "variant": "close",
                              "user_params": {"n": 1}, "default_params": {}} | null}]}
status 由当前状态推出:合并过 → merged;当前版本有 definition → active(在用);没有 → pending_code
(待写代码:用户的原话,现有事实与条件类型算不出,needs 写缺什么)。
参数分两类:user_params 是用户说出来或选定的(「两个峰」里的 2),default_params 是系统取的默认值
(待验证);每个参数只在其中一处,两处都没给的由工具按条件类型的默认值补进 default_params。

身份看定义,不看字面:定义 = 读哪几行事实 + 条件类型 + 口径 + user_params(系统默认值不算身份)。
  · 新建的定义和已有要素相同(在用的;已合并的指到它并入的那条)→ 拒绝新建并报那个编号,
    会话把这次的说法用 alias_element 挂上去。字面不同、定义相同的由此归并;定义不同的是两条。
  · 在用要素的身份不变:revise_element 只能改系统默认值,定义变了就是另一条要素,新建。
  · 待写代码的要素写成计算(revise_element 给 definition)时,定义和已有要素相同 → 拒绝,
    提示用 merge_element 并过去(会话先问用户;工具只给合并操作和查重提示)。
  · merge_element 是显式操作:被并的标 merged 与 merged_into,名字和别名挂到并入的那条,
    引用旧编号的卡照常解析到新编号(resolve)。什么都不删。

四类要素操作(写在决定文件里,与形态卡操作一起由 shapes.apply 校验后写进日志、要素和卡):
  create_element  target {"element_id"(可省,自动分配), "as"(可省;同一决定文件里后面用 "$<as>" 指它)}
                  value {"name": <来源记录>, "origin", "suggested_by", "said_first_match", "suggested_value",
                         "definition": {...} | null, "needs"(definition 为 null 时必填)}
  revise_element  target {"element_id"}  value {"definition", "needs", "change"}
  alias_element   target {"element_id"}  value {"text"}
  merge_element   target {"element_id"(被并的)}  value {"into", "reason"}
谁提的:origin 必填;user_written 要带 said_first_match(用户原话);推荐来的 suggested_by 只能是
detector(事实表)/ session / llm / general_knowledge(要素按编号复用,不经 own_library 抄来源)。
要素读的事实行若是用户提的角度(facts.ROWS 的 source),账本记成「你提的角度」,不算系统推荐。

判定(evaluate,纯函数):读一张图的事实表(facts.compute_facts 的输出),答 yes / no / unknown 和一句
理由。只读事实表,事实表只用买点及以前的 K 线,所以判定也读不到买点之后。

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
from chart_workflow.facts import ROWS, VARIANT_TEXT
from chart_workflow.state import StateRootMissing, advance, state_root

SCHEMA = "chart_workflow.element/1"
ELEMENT_ID_RE = re.compile(r"^E(\d{3,})$")
LOCAL_RE = re.compile(r"^[A-Za-z0-9_]+$")
ORIGINS = ("user_written", "suggested_adopted", "suggested_edited")
SUGGESTED_BY = ("detector", "session", "llm", "general_knowledge")
DEF_FIELDS = ("reads", "cond", "variant", "user_params", "default_params")
STATUS_TEXT = {"active": "在用", "pending_code": "待写代码", "merged": "已合并"}
VERDICT_TEXT = {"yes": "是", "no": "否", "unknown": "无法判定"}
BY_TEXT = {"detector": "事实表", "session": "会话", "llm": "大模型", "general_knowledge": "通用常识"}


# ── 条件类型与判定(纯函数,只读事实表的值) ───────────────────────────────────

def _value(rows: dict, fid: str) -> dict:
    v = rows[fid].get("value")
    return v if isinstance(v, dict) else {}


def _peaks_cleared(rows, variant, p):
    fid = CONDITIONS["peaks_cleared"]["variants"][variant][0]
    n = _value(rows, fid).get("n_cleared")
    if not isinstance(n, int) or isinstance(n, bool):
        return None, f"{fid} 里没有越过峰的个数"
    return n >= p["n"], f"{fid} {VARIANT_TEXT[variant]}越过了 {n} 个峰"


def _burst_chain(rows, variant, p):
    chain = (_value(rows, "F03").get(variant) or {}).get("chain")
    if not isinstance(chain, int) or isinstance(chain, bool):
        return None, "F03 里没有最长一串连续突破的峰数(旧快照,重算事实表)"
    return chain >= p["n"], f"F03 {VARIANT_TEXT[variant]}最长一串连着越过 {chain} 个峰"


def _distribution_within(rows, variant, p):
    evs = _value(rows, "F13").get("events")
    if not isinstance(evs, list):
        return None, "F13 里没有派发列表"
    near = [e for e in evs if isinstance(e, dict) and isinstance(e.get("bars_before"), int)
            and e["bars_before"] < p["bars"]]
    if near:
        return True, f"F13 最近 {p['bars']} 根里有派发（" + "、".join(str(e.get("date")) for e in near) + "）"
    return False, f"F13 最近 {p['bars']} 根里没有派发（窗口里共 {len(evs)} 根）"


def _volume_today(rows, variant, p):
    vr = _value(rows, "F07").get("vr")
    if not isinstance(vr, (int, float)) or isinstance(vr, bool):
        return None, "F07 量比算不出(历史不够长)"
    return vr >= p["ratio"], f"F07 买点当天量比 {vr:g}"


# 条件类型:text 用口径(variant)与参数填空;variants:口径 → 读哪几行(没有口径的写 None);
# params:参数名 → (类型, 系统默认值(待验证), 人话名)。
CONDITIONS = {
    "peaks_cleared": {
        "text": "{variant}越过前面的峰至少 {n} 个", "note": "",
        "variants": {"close": ("F01",), "high": ("F02",)},
        "params": {"n": (int, 1, "峰的个数")}, "fn": _peaks_cleared},
    "burst_chain": {
        "text": "{variant}连续越过至少 {n} 个峰",
        "note": "相邻两次首次越过相隔不超过事实表的连续突破间隔(facts.burst_gap_bars)才算连着",
        "variants": {"close": ("F03",), "high": ("F03",)},
        "params": {"n": (int, 2, "连着越过的峰数")}, "fn": _burst_chain},
    "distribution_within": {
        "text": "最近 {bars} 根里有派发", "note": "派发的标准见事实表 F13",
        "variants": {None: ("F13",)},
        "params": {"bars": (int, 20, "往前看几根(含买点当天)")}, "fn": _distribution_within},
    "volume_today_at_least": {
        "text": "买点当天量比至少 {ratio} 倍", "note": "量比的算法见事实表 F07",
        "variants": {None: ("F07",)},
        "params": {"ratio": (float, 3.0, "量比倍数")}, "fn": _volume_today},
}


def evaluate(definition: dict, facts: dict) -> tuple[str, str]:
    """一个定义在一张图的事实表上的判定:("yes" | "no" | "unknown", 理由)。纯函数。"""
    spec = CONDITIONS.get(definition.get("cond"))
    if spec is None:
        return "unknown", f"代码里没有条件类型 {definition.get('cond')!r}"
    rows = {r["fid"]: r for r in facts.get("rows") or [] if isinstance(r, dict)}
    miss = [f for f in definition["reads"] if f not in rows]
    if miss:
        return "unknown", f"事实表里没有 {'、'.join(miss)}"
    params = {**definition.get("default_params", {}), **definition.get("user_params", {})}
    ok, why = spec["fn"](rows, definition.get("variant"), params)
    return ("unknown" if ok is None else "yes" if ok else "no"), why


def evaluate_element(els: dict, eid: str, facts: dict) -> tuple[str, str]:
    """一条要素(合并过的按它并入的那条)在一张图上的判定;待写代码的答 unknown。"""
    el = els[resolve(els, eid)]
    ver = el["versions"][-1]
    if ver.get("definition") is None:
        return "unknown", f"待写代码（{ver.get('needs') or '现有事实算不出'}）"
    return evaluate(ver["definition"], facts)


# ── 定义:规范化、身份、人话 ─────────────────────────────────────────────────

def _coerce(typ, x, path: str) -> tuple[object, list[str]]:
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None, [f"{path}: 必须是数"]
    if typ is int:
        if not isinstance(x, int):
            return None, [f"{path}: 必须是整数"]
        return x, ([] if x >= 1 else [f"{path}: 至少是 1"])
    return float(x), ([] if x > 0 else [f"{path}: 必须大于 0"])


def normalize_definition(d, path: str = "definition") -> tuple[dict | None, list[str]]:
    """校验并补全一个定义:reads 由条件类型和口径推出(给了就要对得上),没给的参数按默认值补进
    default_params,数值转成规范类型。返回 (规范化的定义, 问题清单)。"""
    if not isinstance(d, dict):
        return None, [f"{path}: 必须是对象(现有事实算不出就写 null 并给 needs)"]
    errs = []
    extra = set(d) - set(DEF_FIELDS)
    if extra:
        errs.append(f"{path}: 未知字段 {sorted(extra)}")
    spec = CONDITIONS.get(d.get("cond"))
    if spec is None:
        return None, errs + [f"{path}: cond 不认识 {d.get('cond')!r}(现有:{'、'.join(CONDITIONS)});"
                             f"现有条件类型算不出就先记待写代码(definition 写 null,needs 写缺什么)"]
    variant = d.get("variant")
    if variant not in spec["variants"]:
        errs.append(f"{path}: 口径 variant 只能是 {'/'.join(map(str, spec['variants']))}(现为 {variant!r})")
        return None, errs
    up, dp = d.get("user_params") or {}, d.get("default_params") or {}
    if not isinstance(up, dict) or not isinstance(dp, dict):
        return None, errs + [f"{path}: user_params / default_params 必须是对象"]
    both = set(up) & set(dp)
    if both:
        errs.append(f"{path}: 参数 {sorted(both)} 只能在 user_params 或 default_params 其中一处")
    unknown = (set(up) | set(dp)) - set(spec["params"])
    if unknown:
        errs.append(f"{path}: {d['cond']} 没有参数 {sorted(unknown)}(有 {'、'.join(spec['params'])})")
    out_u, out_d = {}, {}
    for name, (typ, default, _) in spec["params"].items():
        if name in up:
            val, e = _coerce(typ, up[name], f"{path}.user_params.{name}")
            out_u[name] = val
        else:
            val, e = _coerce(typ, dp.get(name, default), f"{path}.default_params.{name}")
            out_d[name] = val
        errs += e
    reads = list(spec["variants"][variant])
    if "reads" in d and list(d["reads"] or []) != reads:
        errs.append(f"{path}: reads 应为 {reads}(由条件类型和口径定)")
    if errs:
        return None, errs
    return {"reads": reads, "cond": d["cond"], "variant": variant,
            "user_params": out_u, "default_params": out_d}, []


def identity(definition: dict) -> str:
    """要素的身份:读哪几行 + 条件类型 + 口径 + 用户说出来或选定的参数(系统默认值不算)。"""
    return json.dumps([sorted(definition["reads"]), definition["cond"], definition["variant"],
                       definition["user_params"]], sort_keys=True, ensure_ascii=False)


def definition_text(definition: dict) -> str:
    spec = CONDITIONS[definition["cond"]]
    params = {**definition["default_params"], **definition["user_params"]}
    shown = {k: (f"{v:g}" if isinstance(v, float) else v) for k, v in params.items()}
    return spec["text"].format(variant=VARIANT_TEXT.get(definition["variant"], ""), **shown)


def params_text(definition: dict) -> str:
    labels = {k: lab for k, (_, _, lab) in CONDITIONS[definition["cond"]]["params"].items()}
    fmt = lambda d: "、".join(f"{labels.get(k, k)} {v:g}" if isinstance(v, float) else f"{labels.get(k, k)} {v}"
                              for k, v in sorted(d.items()))
    parts = []
    if definition["user_params"]:
        parts.append("你定的：" + fmt(definition["user_params"]))
    if definition["default_params"]:
        parts.append("系统默认（待验证）：" + fmt(definition["default_params"]))
    return "；".join(parts) or "没有参数"


# ── 状态:解析、查重 ────────────────────────────────────────────────────────

def resolve(els: dict, eid: str) -> str:
    """沿 merged_into 走到没被合并的那条。"""
    seen = 0
    while els[eid].get("merged_into") and seen < 100:
        eid, seen = els[eid]["merged_into"], seen + 1
    return eid


def find_same(els: dict, definition: dict, exclude: str | None = None) -> str | None:
    """定义相同的已有要素(在用的,或合并前有这个定义的——返回它并入的那条);没有 → None。"""
    key = identity(definition)
    for eid, el in sorted(els.items()):
        d = el["versions"][-1].get("definition")
        if eid != exclude and d is not None and identity(d) == key:
            return resolve(els, eid)
    return None


def similar(els: dict, definition: dict) -> list[str]:
    """条件类型与口径相同、参数不同的在用要素(查重提示)。"""
    out = []
    for eid, el in sorted(els.items()):
        d = el["versions"][-1].get("definition")
        if el["status"] == "active" and d is not None and d["cond"] == definition["cond"] \
                and d["variant"] == definition["variant"] and identity(d) != identity(definition):
            out.append(f"{eid}「{el['name'].get('value')}」（{definition_text(d)}）")
    return out


def _status(el: dict) -> str:
    if el.get("merged_into"):
        return "merged"
    return "active" if el["versions"][-1].get("definition") is not None else "pending_code"


def next_id(ids) -> str:
    nums = [int(m.group(1)) for i in ids if isinstance(i, str) and (m := ELEMENT_ID_RE.fullmatch(i))]
    return f"E{(max(nums) + 1) if nums else 1:03d}"


# ── 操作的校验与重算 ────────────────────────────────────────────────────────

def _validate_origin(rec, path: str, wrapped: bool, need_said: bool) -> list[str]:
    if not isinstance(rec, dict):
        return [f"{path}: 不是对象"]
    errs = []
    if wrapped and not str(rec.get("value") or "").strip():
        errs.append(f"{path}: value 不能为空")
    origin, by = rec.get("origin"), rec.get("suggested_by")
    if origin not in ORIGINS:
        errs.append(f"{path}: origin 必填且只能是 {'/'.join(ORIGINS)}(现为 {origin!r})")
    if origin in ("suggested_adopted", "suggested_edited") and by not in SUGGESTED_BY:
        errs.append(f"{path}: 推荐来的要写 suggested_by({'/'.join(SUGGESTED_BY)})")
    if by is not None and by not in SUGGESTED_BY:
        errs.append(f"{path}: suggested_by 只能是 {'/'.join(SUGGESTED_BY)}(要素按编号复用,不经 own_library)")
    if origin == "suggested_edited" and "suggested_value" not in rec:
        errs.append(f"{path}: 改过的推荐要带 suggested_value(推荐原值)")
    if need_said and origin == "user_written" and not str(rec.get("said_first_match") or "").strip():
        errs.append(f"{path}: 用户提的要素要带 said_first_match(用户原话)")
    for k in ("from_card", "root"):
        if k in rec:
            errs.append(f"{path}: 要素不带 {k}(按编号复用,不抄来源)")
    return errs


def _texts(el: dict) -> set[str]:
    return {" ".join(str(el["name"].get("value") or "").split())} | \
        {" ".join(str(a["text"]).split()) for a in el["aliases"]}


def subst(x, local: dict, path: str, errs: list[str]):
    """"$<as>" → 同一决定文件里 create_element 分到的编号;其余原样。"""
    if isinstance(x, str) and x.startswith("$") and x != "$new":
        if x[1:] not in local:
            errs.append(f"{path}: {x} 没有对应的 create_element(as)")
            return x
        return local[x[1:]]
    return x


def prepare_op(op: dict, els: dict, local: dict, path: str) -> list[str]:
    """校验一条要素操作并就地补全(分配编号、登记 as、解析 $ 引用、规范化定义),
    再作用到预演状态 els 上。返回问题清单(空 = 合格)。"""
    act, v = op["act"], op.get("value")
    tgt = op["target"] = dict(op.get("target") or {})
    if not isinstance(v, dict):
        return [f"{path}: value 必须是对象"]
    errs: list[str] = []
    if act == "create_element":
        eid = tgt.get("element_id")
        if eid is None:
            eid = next_id(set(els) | set(local.values()))
        elif not ELEMENT_ID_RE.fullmatch(str(eid)) or eid in els:
            return [f"{path}: element_id 不合法或已存在 {eid!r}"]
        alias = tgt.pop("as", None)
        if alias is not None and (not isinstance(alias, str) or not LOCAL_RE.fullmatch(alias) or alias in local):
            return [f"{path}: as 只能是字母数字下划线,且同一文件里不重复({alias!r})"]
        errs += _validate_origin(v.get("name"), f"{path}.name", wrapped=True, need_said=False)
        errs += _validate_origin(v, path, wrapped=False, need_said=True)
        defn = v.get("definition")
        if defn is None:
            if not str(v.get("needs") or "").strip():
                errs.append(f"{path}: 没有定义(待写代码)的要素要写 needs(现有事实缺什么)")
        else:
            defn, e = normalize_definition(defn, f"{path}.definition")
            errs += e
            if defn is not None:
                same = find_same(els, defn)
                if same:
                    errs.append(f"{path}: 定义和已有要素 {same}「{els[same]['name'].get('value')}」相同,"
                                f"不新建;把这次的说法用 alias_element 挂到 {same} 上")
                v["definition"] = defn
        if errs:
            return errs
        tgt["element_id"] = eid
        if alias is not None:
            local[alias] = eid
    else:
        eid = subst(tgt.get("element_id"), local, f"{path}.target.element_id", errs)
        tgt["element_id"] = eid
        if errs:
            return errs
        if eid not in els:
            return [f"{path}: 要素 {eid!r} 不存在"]
        el = els[eid]
        if el["status"] == "merged":
            return [f"{path}: {eid} 已合并到 {resolve(els, eid)},对 {resolve(els, eid)} 操作"]
        if act == "revise_element":
            if not str(v.get("change") or "").strip():
                errs.append(f"{path}: change 必填(一句话说这一版改了什么)")
            cur = el["versions"][-1].get("definition")
            defn = v.get("definition")
            if cur is not None:
                if defn is None:
                    return errs + [f"{path}: 在用的要素不能改回待写代码"]
                defn, e = normalize_definition(defn, f"{path}.definition")
                if e:
                    return errs + e
                if identity(defn) != identity(cur):
                    return errs + [f"{path}: 定义变了就是另一条要素(只能改系统默认值);新建一条"]
            elif defn is not None:
                defn, e = normalize_definition(defn, f"{path}.definition")
                if e:
                    return errs + e
                same = find_same(els, defn, exclude=eid)
                if same:
                    return errs + [f"{path}: 写成计算后和已有要素 {same}「{els[same]['name'].get('value')}」"
                                   f"定义相同;问过用户后用 merge_element 把 {eid} 并到 {same}"]
            elif not str(v.get("needs") or "").strip():
                errs.append(f"{path}: 还是待写代码就要写 needs")
            v["definition"] = defn
        elif act == "alias_element":
            text = " ".join(str(v.get("text") or "").split())
            if not text:
                errs.append(f"{path}: text 不能为空")
            elif text in _texts(el):
                errs.append(f"{path}: {eid} 已经有这个说法「{text}」")
        elif act == "merge_element":
            into = subst(v.get("into"), local, f"{path}.into", errs)
            v["into"] = into
            if not errs:
                if into not in els or into == eid:
                    errs.append(f"{path}: 并入的要素 {into!r} 不存在或就是自己")
                elif els[into]["status"] == "merged":
                    errs.append(f"{path}: {into} 已合并到 {resolve(els, into)},并到 {resolve(els, into)}")
        if errs:
            return errs
    step(els, {**op, "ts": op.get("ts") or "预演", "op_id": op.get("op_id")})
    return []


def _version(n: int, op: dict) -> dict:
    v = op["value"]
    return {"version": n, "ts": op["ts"], "op_id": op.get("op_id"), "change": v.get("change") or "新建",
            "needs": v.get("needs") if v.get("definition") is None else None,
            "definition": copy.deepcopy(v.get("definition"))}


def step(els: dict, op: dict) -> None:
    """把一条要素操作作用到 els 上(就地改;不校验,校验在 prepare_op)。"""
    act = op["act"]
    if act not in oplog.ELEMENT_ACTS:
        return
    eid, v = op["target"]["element_id"], op["value"]
    if act == "create_element":
        if eid in els:
            raise ValueError(f"要素 {eid} 已存在")
        el = {"schema": SCHEMA, "element_id": eid, "name": copy.deepcopy(v["name"]),
              **{k: copy.deepcopy(v[k]) for k in ("origin", "suggested_by", "said_first_match",
                                                  "suggested_value") if k in v},
              "aliases": [], "merged_into": None, "current_version": 1, "versions": [_version(1, op)]}
        els[eid] = el
    else:
        if eid not in els:
            raise ValueError(f"要素 {eid!r} 不存在")
        el = els[eid]
        if act == "revise_element":
            el["current_version"] += 1
            el["versions"].append(_version(el["current_version"], op))
        elif act == "alias_element":
            el["aliases"].append({"text": " ".join(str(v["text"]).split()), "ts": op["ts"],
                                  "op_id": op.get("op_id"), "actor": op.get("actor")})
        elif act == "merge_element":
            into = els[v["into"]]
            el["merged_into"] = v["into"]
            have = _texts(into)
            for t in [el["name"].get("value")] + [a["text"] for a in el["aliases"]]:
                t = " ".join(str(t or "").split())
                if t and t not in have:
                    into["aliases"].append({"text": t, "ts": op["ts"], "op_id": op.get("op_id"),
                                            "actor": op.get("actor"), "from": eid})
                    have.add(t)
            into["status"] = _status(into)
    el["status"] = _status(el)


def replay(ops: list[dict]) -> dict[str, dict]:
    """从操作日志从头重算全部要素(纯函数,只看四类要素操作)。"""
    els: dict[str, dict] = {}
    for op in ops:
        step(els, op)
    return els


# ── 读写 ───────────────────────────────────────────────────────────────────

def elements_dir() -> Path:
    return state_root() / "elements"


def canonical(el: dict) -> str:
    return json.dumps(el, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def write_element(el: dict) -> Path:
    d = elements_dir()
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{el['element_id']}.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(canonical(el))
    tmp.replace(path)
    return path


def write_all(els: dict, eids) -> None:
    for eid in sorted(set(eids)):
        write_element(els[eid])
    if eids:
        advance(state_root())                 # 新文件记进水位


def load_all() -> dict[str, dict]:
    """磁盘上的全部要素文件。"""
    d = elements_dir()
    return {p.stem: json.loads(p.read_text()) for p in sorted(d.glob("E*.json"))} if d.exists() else {}


def rebuild(verify: bool) -> list[str]:
    """从日志从头重算全部要素。verify:与磁盘逐字比对,返回不一致清单;否则用重算结果覆盖磁盘。"""
    els = replay(oplog.read_all())
    d = elements_dir()
    on_disk = {p.stem for p in d.glob("*.json")} if d.exists() else set()
    problems = []
    for eid, el in sorted(els.items()):
        p = d / f"{eid}.json"
        if verify:
            if not p.exists():
                problems.append(f"{eid}: 磁盘上没有这条要素")
            elif p.read_text() != canonical(el):
                problems.append(f"{eid}: 磁盘上的要素与日志重算结果不一致")
        else:
            write_element(el)
    if not verify and els:
        advance(state_root())
    for eid in sorted(on_disk - set(els)):
        problems.append(f"{eid}: 磁盘上有这条要素,日志里没有")
    return problems


# ── 人话打印 ───────────────────────────────────────────────────────────────

def origin_text(rec: dict) -> str:
    o, by = rec.get("origin"), rec.get("suggested_by")
    if o == "user_written":
        said = str(rec.get("said_first_match") or "").strip()
        return "你自己说的" + (f"（原话「{said}」）" if said else "")
    if o == "suggested_adopted":
        return f"采纳了{BY_TEXT.get(by, by)}的推荐"
    return f"改过的{BY_TEXT.get(by, by)}推荐（原为 {rec.get('suggested_value')}）"


def angle(definition: dict | None) -> tuple[str | None, list[str]]:
    """要素读的事实行是谁提的角度:("user" | "preset" | None(待写代码), 用户提那几行的操作日志条目)。"""
    if definition is None:
        return None, []
    ops = [ROWS[f]["source"].get("op_id") for f in definition["reads"]
           if f in ROWS and ROWS[f]["source"].get("kind") == "user"]
    return ("user" if ops else "preset"), ops


def label(els: dict, eid: str) -> str:
    """卡上引用的一条要素的短写:编号「名字」,合并过的注明并到哪条。"""
    el = els.get(eid)
    if el is None:
        return f"{eid}（要素库里没有）"
    s = f"{eid}「{el['name'].get('value')}」"
    if el["status"] == "merged":
        r = resolve(els, eid)
        s += f"（已合并到 {r}「{els[r]['name'].get('value')}」）"
    elif el["status"] == "pending_code":
        s += "（待写代码）"
    return s


def render(el: dict) -> str:
    ver = el["versions"][-1]
    d = ver.get("definition")
    lines = [f"{el['element_id']} 「{el['name'].get('value')}」  {STATUS_TEXT[el['status']]}"
             + (f" → {el['merged_into']}" if el.get("merged_into") else "")
             + f"  v{el['current_version']}",
             f"  谁提的：{origin_text(el)}；名字：{origin_text(el['name'])}"]
    if d is None:
        lines.append(f"  待写代码：{ver.get('needs')}")
    else:
        who, ops = angle(d)
        rows = "、".join(f"{f}「{ROWS[f]['title']}」" for f in d["reads"])
        lines.append(f"  条件：{definition_text(d)}（读 {rows}"
                     + ("，你提的角度" if who == "user" else "") + f"）；{params_text(d)}")
    if el["aliases"]:
        lines.append("  别的说法：" + "、".join(
            a["text"] + (f"（从 {a['from']} 并来）" if a.get("from") else "") for a in el["aliases"]))
    return "\n".join(lines)


def render_conds() -> str:
    lines = []
    for cond, spec in CONDITIONS.items():
        reads = "；".join(f"{VARIANT_TEXT.get(v, '不分口径')}读 {'、'.join(rs)}" for v, rs in spec["variants"].items())
        params = "、".join(f"{k}（{lab}，默认 {dv:g}，待验证）" for k, (_, dv, lab) in spec["params"].items())
        lines.append(f"{cond}：{spec['text']}  {reads}  参数 {params}"
                     + (f"  注：{spec['note']}" if spec["note"] else ""))
    return "\n".join(lines)


def _load_facts_snapshot(path: str) -> dict:
    p = Path(path)
    if not p.exists() and not p.is_absolute():
        p = state_root() / path
    doc = json.loads(p.read_text())
    if not isinstance(doc, dict) or not isinstance(doc.get("results"), list):
        raise ValueError(f"{p} 不是事实表快照")
    return doc


def render_eval(snapshot: dict, els: dict, eids: list[str] | None = None, card: dict | None = None) -> str:
    """一份事实表快照里每张图,各要素答是 / 否 / 无法判定。card:按形态卡当前版本的要素与角色列。"""
    from chart_workflow.shapes import ROLE_TEXT                  # 函数内导入:shapes 依赖本模块
    lines = []
    for r in snapshot["results"]:
        f = r["facts"]
        lines.append(f"{f.get('symbol')} 买点 {f.get('buy_date')}" + (f"（标注 {r['ann_id']}）" if r.get("ann_id") else ""))
        if card is not None:
            items = [(ing["element"], ROLE_TEXT.get(ing.get("role"), ing.get("role")))
                     for ing in card["versions"][-1]["card"].get("ingredients", []) if ing.get("element")]
        else:
            items = [(eid, None) for eid in (eids or [e for e, el in sorted(els.items())
                                                      if el["status"] == "active"])]
        for eid, role in items:
            if eid not in els:
                lines.append(f"  {eid}：要素库里没有")
                continue
            verdict, why = evaluate_element(els, eid, f)
            lines.append(f"  {'【' + role + '】' if role else ''}{label(els, eid)}：{VERDICT_TEXT[verdict]}（{why}）")
        if not items:
            lines.append("  (没有要判的要素)")
    return "\n".join(lines)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="要素库")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("show", help="看要素(默认全部)")
    s.add_argument("element_id", nargs="?")
    sub.add_parser("conds", help="代码里能算的条件类型")
    fd = sub.add_parser("find", help="按定义查有没有已有要素(建要素之前查重)")
    fd.add_argument("--cond", required=True)
    fd.add_argument("--variant")
    fd.add_argument("--param", action="append", default=[], help="用户说出来或选定的参数 k=v,可多个")
    ev = sub.add_parser("eval", help="在事实表快照上判定要素(对卡时用)")
    ev.add_argument("--facts", required=True, help="事实表快照(facts 命令写的,可写相对状态根的路径)")
    ev.add_argument("--element", action="append", default=[])
    ev.add_argument("--shape", help="按这张形态卡当前版本引用的要素与角色判")
    args = ap.parse_args(argv)
    try:
        els = replay(oplog.read_all())
        if args.cmd == "show":
            if args.element_id:
                if args.element_id not in els:
                    raise FileNotFoundError(f"要素不存在: {args.element_id}")
                print(render(els[args.element_id]))
            else:
                print("\n\n".join(render(el) for _, el in sorted(els.items())) or "(还没有要素)")
        elif args.cmd == "conds":
            print(render_conds())
        elif args.cmd == "find":
            up = {}
            for kv in args.param:
                k, _, val = kv.partition("=")
                up[k.strip()] = int(val) if re.fullmatch(r"-?\d+", val.strip()) else float(val)
            defn, errs = normalize_definition({"cond": args.cond, "variant": args.variant, "user_params": up})
            if errs:
                raise ValueError("; ".join(errs))
            same = find_same(els, defn)
            print(f"已有：{label(els, same)}" if same else f"没有定义相同的要素（{definition_text(defn)}）")
            for h in similar(els, defn):
                print(f"相近（条件类型和口径相同、参数不同）：{h}")
        else:
            card = None
            if args.shape:
                from chart_workflow.shapes import replay as replay_cards
                card = replay_cards(oplog.read_all()).get(args.shape)
                if card is None:
                    raise FileNotFoundError(f"形态卡不存在: {args.shape}")
            print(render_eval(_load_facts_snapshot(args.facts), els, args.element or None, card))
    except (ValueError, FileNotFoundError, StateRootMissing) as e:
        print(f"错误:{e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
