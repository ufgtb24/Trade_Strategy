"""要素库:在事实表的行上定出来的是 / 否条件,有自己的编号(E001…),可被几个形态共用。

事实与要素分开:事实(facts.py)只是计算方法加每张图的结果,只给数值和描述、不带判断,没有角色、
不进形态卡;要素是在事实上定出来的是 / 否条件(如「按收盘至少越过一个峰」「最近 20 根里有派发」)。
形态卡引用要素编号,角色(必须有 / 加分 / 有它就不买)写在卡上,同一条要素在不同形态里可以是不同角色。

    uv run python -m chart_workflow.elements show [<element_id>]
    uv run python -m chart_workflow.elements conds                    # 每行事实能判定的值与通用条件类型
    uv run python -m chart_workflow.elements find --row F05 --value runs --cond events_any [--variant V] [--param k=v ...]
    uv run python -m chart_workflow.elements eval --facts <事实表快照> [--element E001 ...] [--shape s001]

F01～F15 每一行都能直接立要素,不用写代码:
  · 每行事实声明自己有哪些可判定的值(VALUES):名字、类型(个数 / 数 / 是非 / 类别 / 事件列表)、
    在事实值里的取法、有没有口径(按收盘 / 按最高价)、值的上下界、算不出(null)时怎么判、
    事件带不带日期和离买点根数。
  · 少量通用条件类型(CONDS)覆盖这些值:个数与数 → at_least / at_most / between;
    是非 → is_true / is_false;类别 → is_one_of;事件列表 → events_any / events_none(最近 N 根里有 / 没有,
    不给 N 就是整个看图窗口)/ events_at_least(至少 k 个)。
  · 定义 = {"row", "value", "cond", "variant", "user_params", "default_params"},建要素时当场校验:
    行、值、条件类型不存在,类型不匹配,口径不对,参数缺 / 多 / 类型不对,一律拒绝(不拖到判定时答
    「无法判定」)。恒成立、不可能成立的定义也拒绝。
  · 现有事实行都算不出的角度才记「待写代码」(definition 为 null,needs 写缺什么)。

身份看定义,不看字面:身份 = 读的行 + 值 + 条件类型 + 口径 + user_params(系统默认值不算身份)。
同一个意思只许一种写法,换个条件类型写出来的同义定义当场拒绝并指出该怎么写:
  · events_at_least 的 k 至少 2(k = 1 就是 events_any);
  · between 的一端碰到值的上下界就是 at_least / at_most;个数的阈值必须是整数;
  · 各值声明里的 same_as:跨行或跨类型的同义写法(如「按收盘连续越过 1 个峰」= F01 越过个数至少 1、
    「最近 1 根里有放量段」= F07 当天量比、「涨前状态是深跌」= dd250 至多深跌线),拒绝并指到规范写法;
  · 「算不出时判否」的值(F04、F06 的 vs_latest_run)在下界上的 at_least 只是在问那个东西在不在,拒绝。
  互为反面的写法(「最近 20 根里有派发」与「…没有派发」、at_least 2 与 at_most 1)是两条要素:
  意思相反,配上相反的角色才等价,那是卡上的事。
  其余去重规则:
  · 新建的定义和已有要素相同(在用的;已合并的指到它并入的那条)→ 拒绝新建并报那个编号,
    会话把这次的说法用 alias_element 挂上去。
  · 在用要素的身份不变:revise_element 只能改系统默认值,定义变了就是另一条要素,新建。
  · 待写代码的要素写成计算(revise_element 给 definition)时,定义和已有要素相同 → 拒绝,
    提示用 merge_element 并过去(会话先问用户;工具只给合并操作和查重提示)。
  · merge_element 是显式操作:被并的标 merged 与 merged_into,名字和别名挂到并入的那条,
    引用旧编号的卡照常解析到新编号(resolve)。什么都不删。

要素文件 <状态根>/elements/<element_id>.json(chart_workflow.element/1),是操作日志的物化结果
(replay 是纯函数),版本只追加:
{"schema", "element_id": "E001", "name": <来源记录,尽量是用户原话>,
 "origin", "suggested_by", "said_first_match", "suggested_value",     # 谁提的(来源记录字段)
 "aliases": [{"text", "ts", "op_id", "actor", "from"(合并过来的才有)}],
 "status": "active | pending_code | merged", "merged_into": null, "current_version": 1,
 "versions": [{"version", "ts", "op_id", "change", "needs",
               "definition": {"row": "F01", "value": "n_cleared", "cond": "at_least", "variant": null,
                              "user_params": {"x": 1}, "default_params": {}} | null}]}
status 由当前状态推出:合并过 → merged;当前版本有 definition → active(在用);没有 → pending_code。
参数分两类:user_params 是用户说出来或选定的(「两个峰」里的 2),default_params 是系统取的默认值
(待验证);每个参数只在其中一处。没有隐藏默认值:条件类型要的参数必须写在两处之一
(events_* 的 bars 可省,省了就是整个看图窗口);is_one_of 选哪几类是这条要素的意思本身,只能是 user_params。

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
理由。只读事实表,事实表只用买点及以前的 K 线,所以判定也读不到买点之后。值是 null 时按值的声明:
默认 unknown(回看不够长);说的那个东西不存在的(没有越过的峰、窗口里没有放量段)判 no;
判定依赖的输入算不出的(needs)判 unknown。旧快照里缺字段 → unknown,提示重算事实表。

红线:不 import 标签口径(labels)、对照(control)、面板(panel)、清单(listfile),不读清单文件。
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import re
import sys
from functools import lru_cache
from pathlib import Path

from chart_workflow import oplog
from chart_workflow.config import load_config
from chart_workflow.facts import REGIME_TEXT, ROWS, VARIANT_TEXT
from chart_workflow.features import PRE_STATES
from chart_workflow.state import StateRootMissing, advance, state_root

SCHEMA = "chart_workflow.element/1"
ELEMENT_ID_RE = re.compile(r"^E(\d{3,})$")
LOCAL_RE = re.compile(r"^[A-Za-z0-9_]+$")
ORIGINS = ("user_written", "suggested_adopted", "suggested_edited")
SUGGESTED_BY = ("detector", "session", "llm", "general_knowledge")
DEF_FIELDS = ("row", "value", "cond", "variant", "user_params", "default_params")
STATUS_TEXT = {"active": "在用", "pending_code": "待写代码", "merged": "已合并"}
VERDICT_TEXT = {"yes": "是", "no": "否", "unknown": "无法判定"}
BY_TEXT = {"detector": "事实表", "session": "会话", "llm": "大模型", "general_knowledge": "通用常识"}
KIND_TEXT = {"count": "个数", "number": "数", "bool": "是非", "category": "类别", "events": "事件列表"}
VARIANTS = ("close", "high")


@lru_cache(maxsize=1)
def _facts_cfg() -> dict:
    return load_config()["facts"]


@lru_cache(maxsize=1)
def _features_cfg() -> dict:
    return load_config()["features"]


# ── 每行事实声明的可判定值 ─────────────────────────────────────────────────
# kind:count(整数)/ number / bool / category / events。title:人话名,"{variant}" 换成口径。
# path:在这一行事实值(row["value"])里的取法,"." 分层,"{variant}" 换成口径。
# variants:有口径的值写口径列表,没有的不写(定义里 variant 就是 null)。
# lo / hi:值的下界 / 上界(写 ("cfg", 键) 的从 config 的 facts 子树取),用来拒绝恒成立、不可能、
#          以及一端碰到边界的 between(那是 at_least / at_most)。
# none:值是 null 时怎么判;不写 = unknown(回看不够长);("no", 理由) = 说的那个东西不存在,判否。
# exists:none 判否的值,在下界上的 at_least 等于问哪一条(拒绝时提示)。
# needs:这些取法(可含 "*" 表示列表里每一项)有一个是 null 就答 unknown(判定所依赖的输入算不出)。
# choices:类别的全部取值。events:{"date": 事件日期字段, "bars_before": 带不带离买点根数};
# where:事件过滤(声明的一部分,不是参数)。unit:显示用,pct 按百分比、times 按倍数。
# same_as:函数 (cond, params, variant) → 提示 | None,这样写等于另一条定义时拒绝并指到规范写法。

def _chain_same(cond, p, variant):
    row = "F01" if variant == "close" else "F02"
    if cond == "at_least" and p["x"] == 1:
        return f"连续越过至少 1 个峰就是越过至少 1 个峰:写成 {row} 的 n_cleared at_least 1"
    if cond == "at_most" and p["x"] == 0:
        return f"连续越过的峰数至多 0 就是一个峰都没越过:写成 {row} 的 n_cleared at_most 0"
    return None


def _runs_same(cond, p, variant):
    if p.get("bars") == 1:
        return ("最近 1 根里有没有放量段就是买点当天量比够不够放量线:写成 F07 的 vr at_least / at_most"
                f"(放量线 {_facts_cfg()['vol_run_min']:g} 是系统默认,用户没说倍数就放 default_params)")
    return None


def _pre_state_same(cond, p, variant):
    deep = _features_cfg()["deep_drop_dd250"]
    vals = set(p["values"])
    if vals == {"深跌"}:
        return (f"「深跌」只看离 250 日最高这一项:写成 F08 的 dd250 at_most(深跌线 {deep:g} 是系统默认,"
                "用户没说幅度就放 default_params)")
    if vals == set(PRE_STATES) - {"深跌"}:
        return (f"「不是深跌」只看离 250 日最高这一项:写成 F08 的 dd250 at_least(深跌线 {deep:g} 是系统默认,"
                "用户没说幅度就放 default_params)")
    return None


_EVENTS = {"bars_before": True}
_MAXP = ("cfg", "max_peaks")

VALUES: dict[str, dict[str, dict]] = {
    "F01": {
        "n_peaks": {"kind": "count", "title": "按收盘找到的峰个数", "path": "n_peaks", "lo": 0, "hi": _MAXP},
        "n_cleared": {"kind": "count", "title": "按收盘越过的峰个数", "path": "n_cleared", "lo": 0, "hi": _MAXP},
    },
    "F02": {
        "n_peaks": {"kind": "count", "title": "按最高价找到的峰个数", "path": "n_peaks", "lo": 0, "hi": _MAXP},
        "n_cleared": {"kind": "count", "title": "按最高价越过的峰个数", "path": "n_cleared", "lo": 0, "hi": _MAXP},
    },
    "F03": {
        "chain": {"kind": "count", "title": "{variant}最长一串连续越过的峰数", "path": "{variant}.chain",
                  "variants": VARIANTS, "lo": 0, "hi": _MAXP, "same_as": _chain_same},
    },
    "F04": {
        "bars": {"kind": "count", "title": "{variant}最早越过的那个峰离买点的根数", "path": "{variant}.bars",
                 "variants": VARIANTS, "lo": 1, "none": ("no", "没有越过的峰"),
                 "exists": "{variant}至少越过一个峰(F01 / F02 的 n_cleared at_least 1)"},
    },
    "F05": {
        "runs": {"kind": "events", "title": "放量段", "path": "all_runs",
                 "events": {"date": "start", **_EVENTS}, "same_as": _runs_same},
    },
    "F06": {
        "dry": {"kind": "bool", "title": "买点前几天（含当天）量比都低于 1", "path": "dry", "needs": ("days.*.vr",)},
        "vs_latest_run": {"kind": "number", "title": "买点前几天均量 ÷ 最近一段放量段均量",
                          "path": "vs_latest_run", "lo": 0, "unit": "times",
                          "none": ("no", "窗口里没有放量段可比"),
                          "exists": "窗口里有放量段(F05 的 runs events_any)"},
    },
    "F07": {
        "vr": {"kind": "number", "title": "买点当天量比", "path": "vr", "lo": 0, "unit": "times"},
    },
    "F08": {
        "pre_state": {"kind": "category", "title": "涨前状态", "path": "pre_state", "choices": PRE_STATES,
                      "same_as": _pre_state_same},
        "dd250": {"kind": "number", "title": "收盘离 250 日最高的幅度", "path": "dd250", "lo": -1, "hi": 0, "unit": "pct"},
        "r60": {"kind": "number", "title": "60 日涨幅", "path": "r60", "lo": -1, "unit": "pct"},
        "width40": {"kind": "number", "title": "40 日振幅占收盘", "path": "width40", "lo": 0, "unit": "pct"},
        "M": {"kind": "number", "title": "日常波动幅度 M", "path": "M", "lo": 0, "unit": "pct"},
    },
    "F09": {
        f"{reg}_segments": {"kind": "events", "title": f"{REGIME_TEXT[reg]}段", "path": "segments",
                            "where": {"regime": reg}, "events": {"date": "start", **_EVENTS}}
        for reg in ("up", "down", "sideways")
    },
    "F10": {
        "gap": {"kind": "number", "title": "当天开盘相对前一天收盘", "path": "gap", "lo": -1, "unit": "pct"},
        "gap_m_flag": {"kind": "bool", "title": "开盘跳空够 gap_m 倍 M", "path": "gap_m_flag", "needs": ("M",)},
    },
    "F11": {
        "segments": {"kind": "events", "title": "平台段", "path": "segments", "events": {"date": "start", **_EVENTS}},
    },
    "F12": {
        "rise": {"kind": "number", "title": "买点前一段的涨幅", "path": "rise", "lo": -1, "unit": "pct"},
        "up_ratio": {"kind": "number", "title": "买点前一段的收阳比例", "path": "up_ratio", "lo": 0, "hi": 1,
                     "unit": "pct"},
        "max_dd": {"kind": "number", "title": "买点前一段的收盘最大回撤", "path": "max_dd", "lo": 0, "hi": 1,
                   "unit": "pct"},
        "r2": {"kind": "number", "title": "买点前一段的对数价格直线拟合 R²", "path": "r2", "lo": 0, "hi": 1},
    },
    "F13": {
        "events": {"kind": "events", "title": "派发", "path": "events", "events": {"date": "date", **_EVENTS}},
    },
    "F14": {
        "segments": {"kind": "events", "title": "回踩企稳段", "path": "segments",
                     "events": {"date": "start", **_EVENTS}},
    },
    "F15": {
        "events": {"kind": "events", "title": "{variant}回踩被越过的峰后收回", "path": "{variant}",
                   "variants": VARIANTS, "events": {"date": "low_date", **_EVENTS}},
    },
}

# 通用条件类型:kinds 能用在哪类值上;need 必填参数;opt 可省参数;text 人话模板。
CONDS = {
    "at_least": {"kinds": ("count", "number"), "need": ("x",), "opt": (), "text": "{v}至少 {x}"},
    "at_most": {"kinds": ("count", "number"), "need": ("x",), "opt": (), "text": "{v}至多 {x}"},
    "between": {"kinds": ("count", "number"), "need": ("lo", "hi"), "opt": (), "text": "{v}在 {lo} 到 {hi} 之间"},
    "is_true": {"kinds": ("bool",), "need": (), "opt": (), "text": "{v}：是"},
    "is_false": {"kinds": ("bool",), "need": (), "opt": (), "text": "{v}：否"},
    "is_one_of": {"kinds": ("category",), "need": ("values",), "opt": (), "text": "{v}是{values}"},
    "events_any": {"kinds": ("events",), "need": (), "opt": ("bars",), "text": "{span}有{v}"},
    "events_none": {"kinds": ("events",), "need": (), "opt": ("bars",), "text": "{span}没有{v}"},
    "events_at_least": {"kinds": ("events",), "need": ("k",), "opt": ("bars",), "text": "{span}至少有 {k} 个{v}"},
}
PARAM_TEXT = {"x": "阈值", "lo": "下限", "hi": "上限", "values": "取哪几类", "k": "至少几个",
              "bars": "往前看几根，含买点当天"}
USER_ONLY = ("values",)


def check_values() -> list[str]:
    """VALUES 与 CONDS 的自检:每行事实都有可判定的值,声明字段齐全且自洽。"""
    errs = [f"{fid}: 没有声明可判定的值" for fid in ROWS if not VALUES.get(fid)]
    errs += [f"{fid}: 不是事实行" for fid in VALUES if fid not in ROWS]
    for fid, vals in VALUES.items():
        for name, s in vals.items():
            at = f"{fid}.{name}"
            if s["kind"] not in KIND_TEXT:
                errs.append(f"{at}: kind 不认识")
            if ("{variant}" in s["path"]) != bool(s.get("variants")):
                errs.append(f"{at}: path 里有没有口径要和 variants 一致")
            if (s["kind"] == "events") != ("events" in s):
                errs.append(f"{at}: 只有事件列表带 events")
            if (s["kind"] == "category") != ("choices" in s):
                errs.append(f"{at}: 只有类别带 choices")
            if bool(s.get("none")) != bool(s.get("exists")):
                errs.append(f"{at}: 算不出判否的值要写 exists")
    return errs


# ── 判定(纯函数,只读事实表的值) ────────────────────────────────────────────

def _bound(spec: dict, key: str):
    b = spec.get(key)
    return _facts_cfg()[b[1]] if isinstance(b, tuple) else b


def _vtitle(spec: dict, variant) -> str:
    return spec["title"].replace("{variant}", VARIANT_TEXT.get(variant, ""))


def _walk(root, path: str, variant):
    """按取法走事实值:(找到没有, 值)。路上碰到 null → (True, None);键不存在 → (False, None)。"""
    cur = root
    for key in path.replace("{variant}", str(variant)).split("."):
        if cur is None:
            return True, None
        if not isinstance(cur, dict) or key not in cur:
            return False, None
        cur = cur[key]
    return True, cur


def _collect(cur, keys: list[str]) -> list:
    """needs 取法下的全部叶子;"*" 展开列表;缺键或 null 记 None。"""
    if not keys:
        return [cur]
    k, rest = keys[0], keys[1:]
    if k == "*":
        return [x for item in cur for x in _collect(item, rest)] if isinstance(cur, list) else [None]
    if not isinstance(cur, dict) or cur.get(k) is None:
        return [None]
    return _collect(cur[k], rest)


def _num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def fmt_value(spec: dict, x) -> str:
    if spec.get("unit") == "pct":
        return f"{x * 100:+g}%" if spec["kind"] == "number" and (spec.get("lo") or 0) < 0 else f"{x * 100:g}%"
    if spec.get("unit") == "times":
        return f"{x:g} 倍"
    return f"{x:g}" if isinstance(x, float) else str(x)


def _span(p: dict) -> str:
    return f"最近 {p['bars']} 根里" if p.get("bars") is not None else "窗口里"


def _judge(fid: str, spec: dict, variant, cond: str, p: dict, x) -> tuple[str, str]:
    name, kind = _vtitle(spec, variant), spec["kind"]
    bad = ("unknown", f"{fid} 的{name}类型不对（{x!r}），重算事实表")
    if kind in ("count", "number"):
        if not _num(x) or (kind == "count" and not isinstance(x, int)):
            return bad
        ok = {"at_least": lambda: x >= p["x"], "at_most": lambda: x <= p["x"],
              "between": lambda: p["lo"] <= x <= p["hi"]}[cond]()
        return ("yes" if ok else "no"), f"{fid} {name} {fmt_value(spec, x)}"
    if kind == "bool":
        if not isinstance(x, bool):
            return bad
        return ("yes" if x == (cond == "is_true") else "no"), f"{fid} {name}：{'是' if x else '否'}"
    if kind == "category":
        if x not in spec["choices"]:
            return bad
        return ("yes" if x in p["values"] else "no"), f"{fid} {name}：{x}"
    if not isinstance(x, list) or not all(isinstance(e, dict) for e in x):
        return bad
    items = [e for e in x if all(e.get(k) == v for k, v in spec.get("where", {}).items())]
    bars = p.get("bars")
    if bars is not None and not all(isinstance(e.get("bars_before"), int) for e in items):
        return "unknown", f"{fid} 的{name}没有离买点根数（旧快照），重算事实表"
    near = [e for e in items if bars is None or e["bars_before"] < bars]
    n = len(near)
    ok = {"events_any": n >= 1, "events_none": n == 0, "events_at_least": n >= p.get("k", 1)}[cond]
    why = f"{fid} {_span(p)}有 {n} 个{name}"
    if near:
        why += "（" + "、".join(str(e.get(spec["events"]["date"])) for e in near) + "）"
    if bars is not None:
        why += f"；窗口里共 {len(items)} 个"
    return ("yes" if ok else "no"), why


def evaluate(definition: dict, facts: dict) -> tuple[str, str]:
    """一个定义在一张图的事实表上的判定:("yes" | "no" | "unknown", 理由)。纯函数。"""
    fid, vname, variant = definition.get("row"), definition.get("value"), definition.get("variant")
    spec = VALUES.get(fid, {}).get(vname)
    if spec is None or definition.get("cond") not in CONDS:
        return "unknown", f"代码里没有 {fid} 的 {vname} 或条件类型 {definition.get('cond')!r}"
    rows = {r["fid"]: r for r in facts.get("rows") or [] if isinstance(r, dict)}
    if fid not in rows:
        return "unknown", f"事实表里没有 {fid}"
    root, name = rows[fid].get("value"), _vtitle(spec, variant)
    found, x = _walk(root, spec["path"], variant)
    if not found:
        return "unknown", f"{fid} 里没有{name}（旧快照），重算事实表"
    for need in spec.get("needs", ()):
        if None in _collect(root, need.split(".")):
            return "unknown", f"{fid} 的{name}算不出（它要用的 {need} 回看不够长）"
    if x is None:
        none = spec.get("none")
        if none:
            return none[0], f"{fid} {none[1]}"
        return "unknown", f"{fid} 的{name}算不出（回看不够长）"
    params = {**definition.get("default_params", {}), **definition.get("user_params", {})}
    return _judge(fid, spec, variant, definition["cond"], params, x)


def evaluate_element(els: dict, eid: str, facts: dict) -> tuple[str, str]:
    """一条要素(合并过的按它并入的那条)在一张图上的判定;待写代码的答 unknown。"""
    el = els[resolve(els, eid)]
    ver = el["versions"][-1]
    if ver.get("definition") is None:
        return "unknown", f"待写代码（{ver.get('needs') or '现有事实算不出'}）"
    return evaluate(ver["definition"], facts)


# ── 定义:规范化、身份、人话 ─────────────────────────────────────────────────

def _coerce_param(name: str, kind: str, spec: dict, x, at: str) -> tuple[object, list[str]]:
    """一个参数转成规范类型:个数的阈值、k、bars 是整数;数的阈值是浮点;values 按 choices 顺序排。"""
    if name == "values":
        if not isinstance(x, list) or not x or not all(isinstance(v, str) for v in x):
            return None, [f"{at}: 必须是非空的类别列表"]
        bad = [v for v in x if v not in spec["choices"]]
        if bad:
            return None, [f"{at}: 没有这些类别 {bad}(有 {'、'.join(spec['choices'])})"]
        if len(set(x)) != len(x):
            return None, [f"{at}: 类别重复"]
        return [c for c in spec["choices"] if c in x], []
    if not _num(x):
        return None, [f"{at}: 必须是数"]
    if name in ("k", "bars") or kind == "count":
        if float(x) != int(x):
            return None, [f"{at}: 必须是整数"]
        x = int(x)
        if name == "bars" and x < 1:
            return None, [f"{at}: 至少是 1"]
        if name == "k" and x < 2:
            return None, [f"{at}: 至少是 2(至少 1 个就是 events_any,写成 events_any)"]
        return x, []
    return float(x), []


def _semantic_errors(fid: str, vname: str, spec: dict, cond: str, p: dict, variant, at: str) -> list[str]:
    """恒成立 / 不可能 / 换种写法就是另一条定义的,拒绝。"""
    name, kind = _vtitle(spec, variant), spec["kind"]
    lo_b, hi_b = _bound(spec, "lo"), _bound(spec, "hi")
    exists = spec.get("exists", "").replace("{variant}", VARIANT_TEXT.get(variant, ""))

    def trivial(what):
        if exists:
            return [f"{at}: {name}{what}在有值时总成立,没有值时判否,所以它只是在问「{exists}」,直接用那一条"]
        return [f"{at}: {name}{what}恒成立({name}在 {lo_b if lo_b is not None else '-∞'} 到 "
                f"{hi_b if hi_b is not None else '+∞'} 之间),不能当条件"]

    errs: list[str] = []
    if cond == "at_least":
        if lo_b is not None and p["x"] <= lo_b:
            errs += trivial(f"至少 {p['x']}")
        elif hi_b is not None and p["x"] > hi_b:
            errs.append(f"{at}: {name}不会超过 {hi_b},至少 {p['x']} 不可能成立")
    elif cond == "at_most":
        if hi_b is not None and p["x"] >= hi_b:
            errs += trivial(f"至多 {p['x']}")
        elif lo_b is not None and p["x"] < lo_b:
            errs.append(f"{at}: {name}不会低于 {lo_b},至多 {p['x']} 不可能成立")
    elif cond == "between":
        lo, hi = p["lo"], p["hi"]
        if lo > hi or (kind == "number" and lo == hi):
            errs.append(f"{at}: 下限要小于上限" + ("(个数可以相等,表示正好几个)" if kind == "count" else ""))
        elif lo_b is not None and lo <= lo_b:
            errs.append(f"{at}: 下限 {lo} 碰到了{name}的下界 {lo_b},等于至多 {hi}:写成 at_most")
        elif hi_b is not None and hi >= hi_b:
            errs.append(f"{at}: 上限 {hi} 碰到了{name}的上界 {hi_b},等于至少 {lo}:写成 at_least")
    elif cond == "is_one_of" and len(p["values"]) == len(spec["choices"]):
        errs.append(f"{at}: 选了全部类别,恒成立,不能当条件")
    elif cond.startswith("events_") and p.get("bars") is not None and not spec["events"].get("bars_before"):
        errs.append(f"{at}: {fid} 的{name}没有离买点根数,不能限定最近 N 根")
    if not errs and spec.get("same_as"):
        hint = spec["same_as"](cond, p, variant)
        if hint:
            errs.append(f"{at}: 同一个意思只许一种写法——{hint}")
    return errs


def normalize_definition(d, path: str = "definition") -> tuple[dict | None, list[str]]:
    """校验并规范化一个定义:行、值、条件类型、口径、参数都对得上声明;参数转成规范类型;
    拒绝恒成立、不可能、同义换写的定义。返回 (规范化的定义, 问题清单)。"""
    if not isinstance(d, dict):
        return None, [f"{path}: 必须是对象(现有事实算不出就写 null 并给 needs)"]
    errs = []
    extra = set(d) - set(DEF_FIELDS)
    if extra:
        errs.append(f"{path}: 未知字段 {sorted(extra)}")
    fid, vname, cond = d.get("row"), d.get("value"), d.get("cond")
    if fid not in VALUES:
        return None, errs + [f"{path}: row 不认识 {fid!r}(现有 {'、'.join(VALUES)});现有事实行都算不出的角度,"
                             f"先记待写代码(definition 写 null,needs 写缺什么)"]
    spec = VALUES[fid].get(vname)
    if spec is None:
        have = "、".join(f"{k}({KIND_TEXT[s['kind']]})" for k, s in VALUES[fid].items())
        return None, errs + [f"{path}: {fid} 没有可判定的值 {vname!r}(有 {have})"]
    ctype = CONDS.get(cond)
    if ctype is None:
        return None, errs + [f"{path}: cond 不认识 {cond!r}(现有 {'、'.join(CONDS)})"]
    kind = spec["kind"]
    if kind not in ctype["kinds"]:
        ok = "、".join(c for c, t in CONDS.items() if kind in t["kinds"])
        return None, errs + [f"{path}: {fid} 的 {vname} 是{KIND_TEXT[kind]},不能用 {cond}(能用 {ok})"]
    variant = d.get("variant")
    if spec.get("variants"):
        if variant not in spec["variants"]:
            return None, errs + [f"{path}: 口径 variant 只能是 {'/'.join(spec['variants'])}(现为 {variant!r})"]
    elif variant is not None:
        return None, errs + [f"{path}: {fid} 的 {vname} 不分口径,variant 写 null(现为 {variant!r})"]
    up, dp = d.get("user_params") or {}, d.get("default_params") or {}
    if not isinstance(up, dict) or not isinstance(dp, dict):
        return None, errs + [f"{path}: user_params / default_params 必须是对象"]
    allowed = ctype["need"] + ctype["opt"]
    both = set(up) & set(dp)
    if both:
        errs.append(f"{path}: 参数 {sorted(both)} 只能在 user_params 或 default_params 其中一处")
    unknown = (set(up) | set(dp)) - set(allowed)
    if unknown:
        errs.append(f"{path}: {cond} 没有参数 {sorted(unknown)}(有 {'、'.join(allowed) or '无'})")
    missing = [n for n in ctype["need"] if n not in up and n not in dp]
    if missing:
        errs.append(f"{path}: {cond} 缺参数 {missing}(用户说了的放 user_params,系统取的放 default_params)")
    errs += [f"{path}: {n} 是这条要素的意思本身,只能放 user_params" for n in USER_ONLY if n in dp]
    if errs:
        return None, errs
    out_u, out_d = {}, {}
    for src, out, where in ((up, out_u, "user_params"), (dp, out_d, "default_params")):
        for n in allowed:
            if n in src:
                out[n], e = _coerce_param(n, kind, spec, src[n], f"{path}.{where}.{n}")
                errs += e
    if errs:
        return None, errs
    errs = _semantic_errors(fid, vname, spec, cond, {**out_d, **out_u}, variant, path)
    if errs:
        return None, errs
    return {"row": fid, "value": vname, "cond": cond, "variant": variant,
            "user_params": out_u, "default_params": out_d}, []


def identity(definition: dict) -> str:
    """要素的身份:读的行 + 值 + 条件类型 + 口径 + 用户说出来或选定的参数(系统默认值不算)。"""
    return json.dumps([definition["row"], definition["value"], definition["cond"], definition["variant"],
                       definition["user_params"]], sort_keys=True, ensure_ascii=False)


def definition_text(definition: dict) -> str:
    spec = VALUES[definition["row"]][definition["value"]]
    p = {**definition["default_params"], **definition["user_params"]}
    shown = {k: fmt_value(spec, v) for k, v in p.items() if k in ("x", "lo", "hi")}
    if "values" in p:
        shown["values"] = p["values"][0] if len(p["values"]) == 1 else " / ".join(p["values"]) + " 之一"
    if "k" in p:
        shown["k"] = p["k"]
    return CONDS[definition["cond"]]["text"].format(v=_vtitle(spec, definition["variant"]), span=_span(p), **shown)


def params_text(definition: dict) -> str:
    spec = VALUES[definition["row"]][definition["value"]]

    def show(k, v):
        if k in ("x", "lo", "hi"):
            return fmt_value(spec, v)
        return " / ".join(v) if isinstance(v, list) else str(v)

    fmt = lambda d: "、".join(f"{PARAM_TEXT.get(k, k)} {show(k, v)}" for k, v in sorted(d.items()))
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
    """读同一行同一个值(口径也相同)、条件类型或参数不同的在用要素(查重提示)。"""
    out = []
    for eid, el in sorted(els.items()):
        d = el["versions"][-1].get("definition")
        if el["status"] == "active" and d is not None and (d["row"], d["value"], d["variant"]) == \
                (definition["row"], definition["value"], definition["variant"]) \
                and identity(d) != identity(definition):
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
    """要素读的事实行是谁提的角度:("user" | "preset" | None(待写代码), 用户提那一行的操作日志条目)。"""
    if definition is None:
        return None, []
    src = ROWS.get(definition["row"], {}).get("source", {})
    return ("user", [src.get("op_id")]) if src.get("kind") == "user" else ("preset", [])


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
        who, _ = angle(d)
        lines.append(f"  条件：{definition_text(d)}（读 {d['row']}「{ROWS[d['row']]['title']}」的 {d['value']}"
                     + ("，你提的角度" if who == "user" else "") + f"）；{params_text(d)}")
    if el["aliases"]:
        lines.append("  别的说法：" + "、".join(
            a["text"] + (f"（从 {a['from']} 并来）" if a.get("from") else "") for a in el["aliases"]))
    return "\n".join(lines)


def _value_line(name: str, spec: dict) -> str:
    kind = spec["kind"]
    bits = [f"{name}：{spec['title'].replace('{variant}', '')}（{KIND_TEXT[kind]}"]
    if spec.get("variants"):
        bits.append("，口径 " + " / ".join(f"{v}={VARIANT_TEXT[v]}" for v in spec["variants"]))
    lo, hi = _bound(spec, "lo"), _bound(spec, "hi")
    if lo is not None or hi is not None:
        bits.append(f"，范围 {'' if lo is None else lo}～{'' if hi is None else hi}")
    if kind == "category":
        bits.append("，取值 " + " / ".join(spec["choices"]))
    if kind == "events":
        bits.append(f"，带日期（{spec['events']['date']}）" + ("、离买点根数" if spec["events"].get("bars_before") else ""))
    if spec.get("none"):
        bits.append(f"，{spec['none'][1]}时判否")
    if spec.get("unit") == "pct":
        bits.append("，写成小数（0.3 = 30%）")
    return "".join(bits) + "）"


def render_conds() -> str:
    lines = ["通用条件类型："]
    for cond, t in CONDS.items():
        params = "、".join([f"{n}（{PARAM_TEXT[n]}）" for n in t["need"]]
                          + [f"{n}（{PARAM_TEXT[n]}，可省，省了就是整个看图窗口）" for n in t["opt"]])
        lines.append(f"  {cond}：用于{' / '.join(KIND_TEXT[k] for k in t['kinds'])}；参数 {params or '无'}")
    lines.append("每行事实能判定的值（参数都要写明：用户说的放 user_params，系统取的放 default_params，待验证）：")
    for fid, vals in VALUES.items():
        lines.append(f"  {fid}「{ROWS[fid]['title']}」")
        lines += [f"    {_value_line(name, spec)}" for name, spec in vals.items()]
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


def _parse_param(kv: str) -> tuple[str, object]:
    k, _, val = kv.partition("=")
    k, val = k.strip(), val.strip()
    if k == "values":
        return k, [v.strip() for v in val.split(",") if v.strip()]
    return k, int(val) if re.fullmatch(r"-?\d+", val) else float(val)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="要素库")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("show", help="看要素(默认全部)")
    s.add_argument("element_id", nargs="?")
    sub.add_parser("conds", help="每行事实能判定的值与通用条件类型")
    fd = sub.add_parser("find", help="按定义查有没有已有要素(建要素之前查重)")
    fd.add_argument("--row", required=True)
    fd.add_argument("--value", required=True)
    fd.add_argument("--cond", required=True)
    fd.add_argument("--variant")
    fd.add_argument("--param", action="append", default=[],
                    help="用户说出来或选定的参数 k=v,可多个;values 用逗号分隔")
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
            up = dict(_parse_param(kv) for kv in args.param)
            defn, errs = normalize_definition({"row": args.row, "value": args.value, "cond": args.cond,
                                               "variant": args.variant, "user_params": up})
            if errs:
                raise ValueError("; ".join(errs))
            same = find_same(els, defn)
            print(f"已有：{label(els, same)}" if same else f"没有定义相同的要素（{definition_text(defn)}）")
            for h in similar(els, defn):
                print(f"相近（读同一个值，条件类型或参数不同）：{h}")
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
