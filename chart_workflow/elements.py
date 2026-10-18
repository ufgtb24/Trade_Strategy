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
    「无法判定」)。恒成立、不可能成立的定义也拒绝:按值声明的上下界判;根数的上界是规则逐日判要素时
    事实表窗口的根数(不框选:买点前 default_lookback_bars 根加买点);
    量比、涨幅、比值数学上没有边界,声明的是合理范围(待验证),at_least / at_most 的阈值落在范围外按
    「近乎恒成立 / 近乎不可能」拒绝;between 只有一端落在合理范围外时原样保留两端,打印要素时给提示
    (definition_hints);百分比写成整数(30% 写成 30)出界时报错里提示单位。
    这些都是现在(第 3 版)的校验规则;重走旧日志条目时按那条自己的版本(shapes 模块说明)。
    这一段都是写入时的质量把关,其中边界、根数上界、合理范围取决于当时的配置:重走日志里已有的条目时
    (quality_as_notices)先把不合格的记下来、不当错误,between 也不按现在的硬边界改写(会改写时同样记下);
    写入时工具记下这些把关读到的值的指纹(quality_fingerprint),重走时指纹没变却不合格就当被改过,指纹变了只提示。
  · 现有事实行都算不出的角度才记「待写代码」(definition 为 null,needs 写缺什么)。

身份看定义,不看字面(same_meaning):读的行、值、条件类型、口径相同,并且 user_params 相同(系统默认值
不算身份),或者两处参数合在一起相同——同一个参数不论写在 user_params 还是 default_params 都按同一条算。
同一个意思只许一种写法,换个条件类型写出来的同义定义当场拒绝并指出该怎么写:
  · events_at_least 的 k 至少 2(k = 1 就是 events_any);
  · between 的一端碰到(或越过)值本来就取不到的硬边界(个数、根数、比例的上下界,比值不小于 0、涨跌幅不小于
    -1)就是 at_least / at_most:不拒绝,规范化成那一种再查重(两端都碰到就是恒成立,拒绝);只落在合理范围
    外的软边界不改写;个数的阈值必须是整数;
  · 各值声明里的 same_as:跨行或跨类型的同义写法(如「按收盘连续越过 1 个峰」= F01 越过个数至少 1、
    「最近 1 根里有放量段」= F07 当天量比、「涨前状态是深跌」= dd250 至多深跌线),拒绝并指到规范写法;
  · 「算不出时判否」的值(F04、F06 的 vs_latest_run)的阈值盖住了值能取到的整个范围(at_least 不高于下界、
    at_most 不低于上界)就只是在问那个东西在不在,拒绝并指到那一条。
  互为反面的写法(「最近 20 根里有派发」与「…没有派发」、at_least 2 与 at_most 1)是两条要素:
  意思相反,配上相反的角色才等价,那是卡上的事。
  其余去重规则:
  · 新建的定义和在用的要素相同 → 拒绝新建并报那个编号,会话把这次的说法用 alias_element 挂上去。
    已合并要素的定义不算到它并入的那条头上。
  · 在用要素的身份不变:revise_element 只能改系统默认值,定义变了就是另一条要素,新建。
  · 待写代码的要素写成计算(revise_element 给 definition,并带这个定义是谁定的)时,定义和已有要素相同
    → 拒绝,提示用 merge_element 并过去(会话先问用户;工具只给合并操作和查重提示)。
  · merge_element 是显式操作,只许合并定义相同的两条:在用的直接比;待写代码的要带它写成计算的定义和
    是谁定的,工具核对相同才并,被并的先追加写成计算的那一版。被并的标 merged 与 merged_into,名字和别名
    挂到并入的那条,新卡引用旧编号会被拒、查询时解析到新编号(resolve)。什么都不删。
  · 形态卡每个版本记下每个要素当时的版本号(工具填):判定、打印、账本都按记下的那一版取定义和来源,
    要素后来的修订与合并不改变旧卡版本的含义。

要素文件 <状态根>/elements/<element_id>.json(chart_workflow.element/1),是操作日志的物化结果
(replay 是纯函数),版本只追加:
{"schema", "element_id": "E001", "name": <来源记录,尽量是用户原话>,
 "origin", "suggested_by", "said_first_match", "suggested_value",     # 谁提的(来源记录字段)
 "aliases": [{"text", "ts", "op_id", "actor", "from"(合并过来的才有)}],
 "status": "active | pending_code | merged", "merged_into": null, "current_version": 1,
 "versions": [{"version", "ts", "op_id", "change", "needs",
               "definition": {"row": "F01", "value": "n_cleared", "cond": "at_least", "variant": null,
                              "user_params": {"x": 1}, "default_params": {}} | null,
               "definition_origin": <这一版的定义是谁定的(来源记录字段)> | null}]}
status 由当前状态推出:合并过 → merged;当前版本有 definition → active(在用);没有 → pending_code。
参数分两类:user_params 是用户说出来或选定的(「两个峰」里的 2),default_params 是系统取的默认值
(待验证);每个参数只在其中一处。没有隐藏默认值:条件类型要的参数必须写在两处之一
(events_* 的 bars 可省,省了就是整个看图窗口);is_one_of 选哪几类是这条要素的意思本身,只能是 user_params。

四类要素操作(写在决定文件里,与形态卡操作一起由 shapes.apply 校验后写进日志、要素和卡):
  create_element  target {"element_id"(可省,自动分配), "as"(可省;同一决定文件里后面用 "$<as>" 指它)}
                  value {"name": <来源记录>, "origin", "suggested_by", "said_first_match", "suggested_value",
                         "definition": {...} | null, "needs"(definition 为 null 时必填)}
  revise_element  target {"element_id"}  value {"definition", "needs", "change",
                                                 来源记录字段(待写代码写成计算时必填:定义是谁定的)}
  alias_element   target {"element_id"}  value {"text"}
  merge_element   target {"element_id"(被并的)}  value {"into", "reason",
                                                       "definition" + 来源记录字段(被并的是待写代码时必填)}
谁提的:origin 必填;user_written 要带 said_first_match(用户原话);推荐来的 suggested_by 只能是
detector(事实表)/ session / llm / general_knowledge(要素按编号复用,不经 own_library 抄来源)。
要素读的事实行若是用户提的角度(facts.ROWS 的 source),且出处指的「提出角度」日志条目存在、排在这一版
要素建立之前,账本记成「你提的角度」,不算系统推荐;否则按预设记。

判定(evaluate,纯函数):读一张图的事实表(facts.compute_facts 的输出),答 yes / no / unknown 和一句
理由。只读事实表,事实表只用买点及以前的 K 线,所以判定也读不到买点之后。值是 null 时按值的声明:
默认 unknown(回看不够长);说的那个东西不存在的(没有越过的峰、窗口里没有放量段)判 no;
判定依赖的输入算不出的(needs)判 unknown。旧快照里缺字段 → unknown,提示重算事实表。

红线:不 import 标签口径(labels)、对照(control)、面板(panel)、清单(listfile),不读清单文件。
"""
from __future__ import annotations

import argparse
import contextlib
import contextvars
import copy
import hashlib
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


_QUALITY = contextvars.ContextVar("chart_workflow_quality_sink", default=None)


@contextlib.contextmanager
def quality_as_notices(sink: list):
    """重走日志里已有的条目时用(shapes.revalidate):定义的质量把关(恒成立 / 不可能 / 根数上界 / 合理范围 /
    同义换写,边界取决于当时的配置)不合格时把问题记进 sink、不当错误;between 不按现在的硬边界改写,会改写时
    同样记一条进 sink。"""
    token = _QUALITY.set(sink)
    try:
        yield
    finally:
        _QUALITY.reset(token)


@lru_cache(maxsize=1)
def _features_cfg() -> dict:
    return load_config()["features"]


# ── 每行事实声明的可判定值 ─────────────────────────────────────────────────
# kind:count(整数)/ number / bool / category / events。title:人话名,"{variant}" 换成口径。
# path:在这一行事实值(row["value"])里的取法,"." 分层,"{variant}" 换成口径。
# variants:有口径的值写口径列表,没有的不写(定义里 variant 就是 null)。
# lo / hi:值的下界 / 上界,用来拒绝恒成立、不可能;一端碰到(或越过)边界的 between 只剩另一端,按 at_least /
#          at_most 规范化(再和已有要素查重)。
#          ("cfg", 键) 从 config 的 facts 子树取;("win", 偏移) = 事实表窗口多少根 + 偏移(见 max_window_bars)。
#          soft = True:数学上没有边界(量比、涨幅、比值),这里是合理范围(待验证)——at_least / at_most 的阈值
#          落在范围外按「近乎恒成立 / 近乎不可能」拒绝;between 只有一端落在范围外时原样保留两端、只给提示;
#          百分比写成了整数(30% 写成 30)时会出界,报错里提示单位。
# hard:soft 的值本来就取不到的边界(比值不小于 0、涨跌幅不小于 -1),(下界, 上界),没有写 None。
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
_MAXB = ("win", -1)                    # 离买点的根数最多是窗口长度减一

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
                 "variants": VARIANTS, "lo": 1, "hi": _MAXB, "none": ("no", "没有越过的峰"),
                 "exists": "{variant}至少越过一个峰(F01 / F02 的 n_cleared at_least 1)"},
    },
    "F05": {
        "runs": {"kind": "events", "title": "放量段", "path": "all_runs",
                 "events": {"date": "start", **_EVENTS}, "same_as": _runs_same},
    },
    "F06": {
        "dry": {"kind": "bool", "title": "买点前几天（含当天）量比都低于 1", "path": "dry", "needs": ("days.*.vr",)},
        "vs_latest_run": {"kind": "number", "title": "买点前几天均量 ÷ 最近一段放量段均量",
                          "path": "vs_latest_run", "lo": 0.01, "hi": 10, "soft": True, "hard": (0, None),
                          "unit": "times",
                          "none": ("no", "窗口里没有放量段可比"),
                          "exists": "窗口里有放量段(F05 的 runs events_any)"},
    },
    "F07": {
        "vr": {"kind": "number", "title": "买点当天量比", "path": "vr", "lo": 0.05, "hi": 100, "soft": True,
               "hard": (0, None), "unit": "times"},
    },
    "F08": {
        "pre_state": {"kind": "category", "title": "涨前状态", "path": "pre_state", "choices": PRE_STATES,
                      "same_as": _pre_state_same},
        "dd250": {"kind": "number", "title": "收盘离 250 日最高的幅度", "path": "dd250", "lo": -1, "hi": 0, "unit": "pct"},
        "r60": {"kind": "number", "title": "60 日涨幅", "path": "r60", "lo": -0.95, "hi": 20, "soft": True,
                "hard": (-1, None), "unit": "pct"},
        "width40": {"kind": "number", "title": "40 日振幅占收盘", "path": "width40", "lo": 0.005, "hi": 10,
                    "soft": True, "hard": (0, None), "unit": "pct"},
        "M": {"kind": "number", "title": "日常波动幅度 M", "path": "M", "lo": 0.002, "hi": 1, "soft": True,
              "hard": (0, None), "unit": "pct"},
    },
    "F09": {
        f"{reg}_segments": {"kind": "events", "title": f"{REGIME_TEXT[reg]}段", "path": "segments",
                            "where": {"regime": reg}, "events": {"date": "start", **_EVENTS}}
        for reg in ("up", "down", "sideways")
    },
    "F10": {
        "gap": {"kind": "number", "title": "当天开盘相对前一天收盘", "path": "gap", "lo": -0.9, "hi": 3,
                "soft": True, "hard": (-1, None), "unit": "pct"},
        "gap_m_flag": {"kind": "bool", "title": "开盘跳空够 gap_m 倍 M", "path": "gap_m_flag", "needs": ("M",)},
    },
    "F11": {
        "segments": {"kind": "events", "title": "平台段", "path": "segments", "events": {"date": "start", **_EVENTS}},
    },
    "F12": {
        "rise": {"kind": "number", "title": "买点前一段的涨幅", "path": "rise", "lo": -0.95, "hi": 20,
                 "soft": True, "hard": (-1, None), "unit": "pct"},
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

def max_window_bars() -> int:
    """事实表窗口多少根:规则逐日判要素时不框选,窗口取买点前 default_lookback_bars 根,含买点共这么多加一根。
    根数类的值(离买点多少根、最近 N 根)按它定上界——超过它的阈值在规则里等于整个窗口。卡的样本按用户框的
    起点算,框得比这长时样本上能取到更大的根数,这里不放宽(待验证)。
    第 1 版校验规则(重走旧日志条目时,见 shapes 模块说明)按整个看图范围:看图下界到训练段末日的工作日数。"""
    if oplog.rules_now() < 2:
        import pandas as pd

        cfg = load_config()
        span = len(pd.bdate_range(str(cfg.get("view_floor") or cfg["train_start"]), str(cfg["train_end"])))
        return max(int(cfg["facts"]["default_lookback_bars"]) + 1, span)
    return int(_facts_cfg()["default_lookback_bars"]) + 1


def _bound(spec: dict, key: str):
    b = spec.get(key)
    if isinstance(b, tuple):
        return max_window_bars() + b[1] if b[0] == "win" else _facts_cfg()[b[1]]
    return b


def _plain(x):
    """去掉函数(same_as 这类代码本身不进指纹,改代码要加校验版本号),元组按列表。"""
    if isinstance(x, dict):
        return {k: _plain(v) for k, v in x.items() if not callable(v)}
    if isinstance(x, (list, tuple)):
        return [_plain(v) for v in x]
    return x


def quality_fingerprint() -> str:
    """定义的质量把关(恒成立 / 不可能 / 根数上界 / 合理范围 / 同义换写)实际读到的全部值的指纹:每个可判定的值
    按现在的配置解析出来的上下界与硬边界、合理范围、单位、类别、事件属性,根数上界(事实表窗口),以及同义换写
    提示里引用的放量线、深跌线。不管来自配置还是代码常量,任何一个变了指纹就变。工具写日志时记进要素与形态卡
    的条目(oplog.append),重走时据此分辨「写入后配置变了」和「写入时就不合格」。"""
    table = {f"{fid}.{vname}": {**_plain(spec), "lo": _bound(spec, "lo"), "hi": _bound(spec, "hi")}
             for fid, vals in VALUES.items() for vname, spec in vals.items()}       # 硬边界:soft 的在声明里,其余就是上下界
    table["_window"] = max_window_bars()
    table["_said"] = [_facts_cfg()["vol_run_min"], _features_cfg()["deep_drop_dd250"]]
    return hashlib.sha256(json.dumps(table, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()[:16]


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


def element_version(els: dict, eid: str, version: int | None = None) -> dict:
    """要素的一个版本。version 给了(形态卡上记下的版本号)→ 就取卡上引用的那条要素的那一版,不跟合并;
    没给 → 合并过的按它并入的那条,取当前版本。"""
    if version is not None:
        vs = els[eid]["versions"]
        if not 1 <= version <= len(vs):
            raise ValueError(f"{eid} 没有版本 v{version}")
        return vs[version - 1]
    return els[resolve(els, eid)]["versions"][-1]


def evaluate_element(els: dict, eid: str, facts: dict, version: int | None = None) -> tuple[str, str]:
    """一条要素在一张图上的判定;待写代码的答 unknown。version:形态卡上记下的版本号(按那一版的定义判,
    要素后来修订、合并都不影响);不给就按合并后的当前版本。"""
    ver = element_version(els, eid, version)
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


def _unit_hint(spec: dict, x) -> str:
    """百分比写成了整数(30% 写成 30)时出界:提示单位。"""
    lo, hi = _bound(spec, "lo"), _bound(spec, "hi")
    if spec.get("unit") == "pct" and abs(x) >= 1 and (lo is None or x / 100 >= lo) \
            and (hi is None or x / 100 <= hi):
        return f"(像是把百分数直接写成了数:{x:g}% 要写成 {x / 100:g})"
    return ""


def _semantic_errors(fid: str, vname: str, spec: dict, cond: str, p: dict, variant, at: str) -> list[str]:
    """恒成立 / 不可能 / 换种写法就是另一条定义的,拒绝。"""
    name, kind = _vtitle(spec, variant), spec["kind"]
    lo_b, hi_b = _bound(spec, "lo"), _bound(spec, "hi")
    soft = "近乎" if spec.get("soft") else ""
    span = f"{lo_b if lo_b is not None else '-∞'} 到 {hi_b if hi_b is not None else '+∞'}"
    rng = f"{name}的合理范围是 {span},待验证" if soft else f"{name}在 {span} 之间"
    exists = spec.get("exists", "").replace("{variant}", VARIANT_TEXT.get(variant, ""))

    def trivial(what):
        if exists:
            return [f"{at}: {name}{what}在有值时{soft}总成立,没有值时判否,所以它只是在问「{exists}」,直接用那一条"]
        return [f"{at}: {name}{what}{soft}恒成立({rng}),不能当条件"]

    def impossible(what, x):
        return [f"{at}: {name}{what}{soft}不可能成立({rng}){_unit_hint(spec, x)}"]

    errs: list[str] = []
    if cond == "at_least":
        if lo_b is not None and p["x"] <= lo_b:
            errs += trivial(f"至少 {p['x']}")
        elif hi_b is not None and p["x"] > hi_b:
            errs += impossible(f"至少 {p['x']}", p["x"])
    elif cond == "at_most":
        if hi_b is not None and p["x"] >= hi_b:
            errs += trivial(f"至多 {p['x']}")
        elif lo_b is not None and p["x"] < lo_b:
            errs += impossible(f"至多 {p['x']}", p["x"])
    elif cond == "between":
        lo, hi = p["lo"], p["hi"]
        if lo > hi or (kind == "number" and lo == hi):
            errs.append(f"{at}: 下限要小于上限" + ("(个数可以相等,表示正好几个)" if kind == "count" else ""))
        elif oplog.rules_now() < 2:                   # 第 1 版:一端碰到边界就要求换写法
            if lo_b is not None and lo <= lo_b:
                errs.append(f"{at}: 下限 {lo} 碰到了{name}的下界 {lo_b},等于至多 {hi}:写成 at_most")
            elif hi_b is not None and hi >= hi_b:
                errs.append(f"{at}: 上限 {hi} 碰到了{name}的上界 {hi_b}{_unit_hint(spec, hi)},等于至少 {lo}:写成 at_least")
        elif hi_b is not None and hi > hi_b and _unit_hint(spec, hi):
            errs.append(f"{at}: 上限 {hi} 越过了{name}的上界 {hi_b}{_unit_hint(spec, hi)}")
        elif lo_b is not None and lo <= lo_b and hi_b is not None and hi >= hi_b:
            errs += trivial(f"在 {lo} 到 {hi} 之间")
    elif cond == "is_one_of" and len(p["values"]) == len(spec["choices"]):
        errs.append(f"{at}: 选了全部类别,恒成立,不能当条件")
    elif cond.startswith("events_") and p.get("bars") is not None:
        if not spec["events"].get("bars_before"):
            errs.append(f"{at}: {fid} 的{name}没有离买点根数,不能限定最近 N 根")
        elif p["bars"] >= max_window_bars():
            errs.append(f"{at}: 最近 {p['bars']} 根不比事实表窗口短(规则逐日判时不框选,窗口共 {max_window_bars()} 根),"
                        f"等于整个窗口:不写 bars")
    if not errs and spec.get("same_as"):
        hint = spec["same_as"](cond, p, variant)
        if hint:
            errs.append(f"{at}: 同一个意思只许一种写法——{hint}")
    return errs


def _hard(spec: dict) -> tuple:
    """值本来就取不到的边界:硬边界的值就是它声明的上下界;soft 的值(合理范围)另声明 hard。"""
    if spec.get("soft"):
        return tuple(spec.get("hard") or (None, None))
    return _bound(spec, "lo"), _bound(spec, "hi")


def _one_sided(spec: dict, up: dict, dp: dict) -> tuple[str, dict, dict]:
    """between 只有一端碰到(或越过)值本来就取不到的硬边界时只剩另一端:上限碰到上界 → at_least 下限,
    下限碰到下界 → at_most 上限;参数留在原来那一处(用户说的还是用户说的)。只落在「合理范围」之外的软边界
    不改写(见 definition_hints)。两端都碰到、都没碰到、上下限颠倒、上限像把百分数写成了数 → 原样返回
    between,由 _semantic_errors 判。"""
    p = {**dp, **up}
    lo, hi = p["lo"], p["hi"]
    lo_b, hi_b = _hard(spec)
    hit_lo = lo_b is not None and lo <= lo_b
    hit_hi = hi_b is not None and hi >= hi_b
    soft_hi = _bound(spec, "hi")
    if lo > hi or (spec["kind"] == "number" and lo == hi) or hit_lo == hit_hi \
            or (soft_hi is not None and hi > soft_hi and _unit_hint(spec, hi)):
        return "between", up, dp
    keep, cond = ("lo", "at_least") if hit_hi else ("hi", "at_most")
    move = lambda d: {"x": d[keep]} if keep in d else {}
    return cond, move(up), move(dp)


def normalize_definition(d, path: str = "definition") -> tuple[dict | None, list[str]]:
    """校验并规范化一个定义:行、值、条件类型、口径、参数都对得上声明;参数转成规范类型;一端碰到边界的
    between 按 at_least / at_most 规范化(见 _one_sided);拒绝恒成立、不可能、同义换写的定义(重走日志里已有的
    条目时这几项只记提示,见 quality_as_notices)。返回 (规范化的定义, 问题清单)。"""
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
    sink = _QUALITY.get()
    if cond == "between" and oplog.rules_now() >= 2:
        if sink is None:
            cond, out_u, out_d = _one_sided(spec, out_u, out_d)
        elif _one_sided(spec, out_u, out_d)[0] != "between":
            sink.append(f"{path}: between 有一端碰到了{_vtitle(spec, variant)}本来就取不到的边界,"
                        f"等于 {_one_sided(spec, out_u, out_d)[0]}")
    errs = _semantic_errors(fid, vname, spec, cond, {**out_d, **out_u}, variant, path)
    if errs and sink is None:
        return None, errs
    if errs:
        sink.extend(errs)
    return {"row": fid, "value": vname, "cond": cond, "variant": variant,
            "user_params": out_u, "default_params": out_d}, []


def definition_hints(definition: dict) -> list[str]:
    """合法但值得提醒的地方(不拒绝、不改写):between 只有一端落在合理范围(待验证)之外,那一端几乎不起作用。"""
    spec = VALUES[definition["row"]][definition["value"]]
    if definition["cond"] != "between" or not spec.get("soft"):
        return []
    p = {**definition["default_params"], **definition["user_params"]}
    lo_b, hi_b = _bound(spec, "lo"), _bound(spec, "hi")
    name = _vtitle(spec, definition["variant"])
    out = []
    if hi_b is not None and p["hi"] > hi_b:
        out.append(f"{name}的上限 {fmt_value(spec, p['hi'])},在合理范围(到 {fmt_value(spec, hi_b)},待验证)之外,"
                   f"这一端几乎不起作用;照你写的两端保留")
    if lo_b is not None and p["lo"] < lo_b:
        out.append(f"{name}的下限 {fmt_value(spec, p['lo'])},在合理范围(从 {fmt_value(spec, lo_b)} 起,待验证)之外,"
                   f"这一端几乎不起作用;照你写的两端保留")
    return out


def identity(definition: dict) -> str:
    """要素的身份:读的行 + 值 + 条件类型 + 口径 + 用户说出来或选定的参数(系统默认值不算)。"""
    return json.dumps([definition["row"], definition["value"], definition["cond"], definition["variant"],
                       definition["user_params"]], sort_keys=True, ensure_ascii=False)


def same_meaning(a: dict, b: dict) -> bool:
    """两个定义是不是同一条要素:行、值、条件类型、口径相同,并且用户参数相同(系统默认值不算身份),
    或者把两处参数合在一起相同——同一个参数不论写在 user_params 还是 default_params 都按同一条算
    (「量比至少 3」用户说的和系统默认的,不能借换个位置并存)。"""
    head = lambda d: [d["row"], d["value"], d["cond"], d["variant"]]
    if head(a) != head(b):
        return False
    merged = lambda d: {**d["default_params"], **d["user_params"]}
    return a["user_params"] == b["user_params"] or merged(a) == merged(b)


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
    """和这个定义是同一条要素的在用要素(见 same_meaning);没有 → None。已合并的要素不算——
    合并只许发生在定义相同的两条之间,不把被并那条的定义算到并入的那条头上。"""
    for eid, el in sorted(els.items()):
        d = el["versions"][-1].get("definition")
        if eid != exclude and el["status"] == "active" and d is not None and same_meaning(d, definition):
            return eid
    return None


def similar(els: dict, definition: dict) -> list[str]:
    """读同一行同一个值(口径也相同)、条件类型或参数不同的在用要素(查重提示)。"""
    out = []
    for eid, el in sorted(els.items()):
        d = el["versions"][-1].get("definition")
        if el["status"] == "active" and d is not None and (d["row"], d["value"], d["variant"]) == \
                (definition["row"], definition["value"], definition["variant"]) \
                and not same_meaning(d, definition):
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
                same = find_same(els, defn, exclude=eid)
                if same:
                    return errs + [f"{path}: 这样改完和已有要素 {same}「{els[same]['name'].get('value')}」"
                                   f"成了同一条,不能改"]
            elif defn is not None:
                defn, e = normalize_definition(defn, f"{path}.definition")
                if e:
                    return errs + e
                errs += _validate_origin(v, f"{path}(写成计算是谁定的)", wrapped=False, need_said=True)
                same = find_same(els, defn, exclude=eid)
                if same:
                    return errs + [f"{path}: 写成计算后和已有要素 {same}「{els[same]['name'].get('value')}」"
                                   f"定义相同;问过用户后用 merge_element 把 {eid} 并到 {same}"
                                   f"(合并时带上这条定义和是谁定的,工具核对相同才合并)"]
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
                elif els[into]["status"] != "active":
                    errs.append(f"{path}: {into} 还是待写代码,比不了是不是同一个意思;只能并到在用的要素上")
                else:
                    errs += _merge_errors(el, els[into], v, path)
        if errs:
            return errs
    step(els, {**op, "ts": op.get("ts") or "预演", "op_id": op.get("op_id")})
    return []


def _merge_errors(el: dict, into: dict, v: dict, path: str) -> list[str]:
    """合并只许发生在定义相同的两条之间(就地把 v["definition"] 规范化)。在用的直接比;待写代码的要带
    它写成计算的定义和是谁定的(origin 等),工具核对和并入的那条相同才合并。"""
    src, dst = el["versions"][-1].get("definition"), into["versions"][-1]["definition"]
    eid, iid = el["element_id"], into["element_id"]
    if src is not None:
        if "definition" in v:
            return [f"{path}: {eid} 已经在用,合并不用带 definition"]
        if not same_meaning(src, dst):
            return [f"{path}: 只能合并定义相同的两条:{eid}({definition_text(src)})和 "
                    f"{iid}({definition_text(dst)})不是同一个意思"]
        return []
    if v.get("definition") is None:
        return [f"{path}: {eid} 还是待写代码:合并要带它写成计算的定义(definition)和是谁定的(origin 等),"
                f"工具核对和 {iid} 相同才合并"]
    defn, errs = normalize_definition(v["definition"], f"{path}.definition")
    errs += _validate_origin(v, f"{path}(写成计算是谁定的)", wrapped=False, need_said=True)
    if defn is not None:
        v["definition"] = defn
        if not same_meaning(defn, dst):
            errs.append(f"{path}: {eid} 写成计算({definition_text(defn)})和 {iid}({definition_text(dst)})"
                        f"不是同一个意思,不能合并")
    return errs


ORIGIN_KEYS = ("origin", "suggested_by", "said_first_match", "suggested_value")


def _origin_of(v: dict) -> dict:
    return {k: copy.deepcopy(v[k]) for k in ORIGIN_KEYS if k in v}


def _version(n: int, op: dict, definition_origin: dict | None = None, change: str | None = None) -> dict:
    """一个版本。definition_origin:这一版的定义是谁定的(建要素时就是要素的来源;待写代码写成计算、
    合并时由那条操作带来;只改系统默认值的版本沿用上一版的)。待写代码的版本为 None。"""
    v = op["value"]
    has = v.get("definition") is not None
    return {"version": n, "ts": op["ts"], "op_id": op.get("op_id"), "change": change or v.get("change") or "新建",
            "needs": None if has else v.get("needs"),
            "definition": copy.deepcopy(v.get("definition")),
            "definition_origin": copy.deepcopy(definition_origin) if has else None}


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
              "aliases": [], "merged_into": None, "current_version": 1,
              "versions": [_version(1, op, _origin_of(v))]}
        els[eid] = el
    else:
        if eid not in els:
            raise ValueError(f"要素 {eid!r} 不存在")
        el = els[eid]
        if act == "revise_element":
            prev = el["versions"][-1]
            who = _origin_of(v) if prev.get("definition") is None else prev.get("definition_origin")
            el["current_version"] += 1
            el["versions"].append(_version(el["current_version"], op, who))
        elif act == "alias_element":
            el["aliases"].append({"text": " ".join(str(v["text"]).split()), "ts": op["ts"],
                                  "op_id": op.get("op_id"), "actor": op.get("actor")})
        elif act == "merge_element":
            into = els[v["into"]]
            if v.get("definition") is not None:          # 待写代码的:先记下写成计算的这一版,再并
                el["current_version"] += 1
                el["versions"].append(_version(el["current_version"], op, _origin_of(v),
                                               change=f"写成计算,和 {v['into']} 相同,并入"))
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


def angle(ver: dict, ops: list[dict]) -> tuple[str | None, list[str]]:
    """要素这一版读的事实行是谁提的角度:("user" | "preset" | None(待写代码), 用户提那一行的操作日志条目)。
    只有代码里写的出处(facts.ROWS 的 source)指向的那条「提出角度」(propose_fact)真在日志里、
    而且排在这一版的定义建立之前,才算用户提的角度;否则按预设的算。"""
    definition = ver.get("definition")
    if definition is None:
        return None, []
    src = ROWS.get(definition["row"], {}).get("source", {})
    if src.get("kind") != "user":
        return "preset", []
    pos = {o.get("op_id"): k for k, o in enumerate(ops)}
    k = pos.get(src.get("op_id"))
    here = pos.get(ver.get("op_id"), len(ops))
    if k is None or ops[k].get("act") != "propose_fact" or k >= here:
        return "preset", []
    return "user", [src["op_id"]]


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


def render(el: dict, ops: list[dict] | None = None) -> str:
    """一条要素的人话打印。ops:操作日志(判断「你提的角度」用;缺省现读)。"""
    ver = el["versions"][-1]
    d = ver.get("definition")
    lines = [f"{el['element_id']} 「{el['name'].get('value')}」  {STATUS_TEXT[el['status']]}"
             + (f" → {el['merged_into']}" if el.get("merged_into") else "")
             + f"  v{el['current_version']}",
             f"  谁提的：{origin_text(el)}；名字：{origin_text(el['name'])}"]
    if d is None:
        lines.append(f"  待写代码：{ver.get('needs')}")
    else:
        who, _ = angle(ver, oplog.read_all() if ops is None else ops)
        lines.append(f"  条件：{definition_text(d)}（读 {d['row']}「{ROWS[d['row']]['title']}」的 {d['value']}"
                     + ("，你提的角度" if who == "user" else "") + f"）；{params_text(d)}")
        if ver.get("definition_origin") and ver["version"] > 1:
            lines.append(f"  定义是谁定的：{origin_text(ver['definition_origin'])}（v{ver['version']}）")
        lines += [f"  提示：{h}" for h in definition_hints(d)]
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
        bits.append(f"，{'合理范围（待验证）' if spec.get('soft') else '范围'} "
                    f"{'' if lo is None else lo}～{'' if hi is None else hi}")
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
        if card is not None:            # 按卡上记下的要素版本判
            items = [(ing["element"], ROLE_TEXT.get(ing.get("role"), ing.get("role")), ing.get("element_version"))
                     for ing in card["versions"][-1]["card"].get("ingredients", []) if ing.get("element")]
        else:
            items = [(eid, None, None) for eid in (eids or [e for e, el in sorted(els.items())
                                                            if el["status"] == "active"])]
        for eid, role, version in items:
            if eid not in els:
                lines.append(f"  {eid}：要素库里没有")
                continue
            verdict, why = evaluate_element(els, eid, f, version)
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
        ops = oplog.read_all()
        els = replay(ops)
        if args.cmd == "show":
            if args.element_id:
                if args.element_id not in els:
                    raise FileNotFoundError(f"要素不存在: {args.element_id}")
                print(render(els[args.element_id], ops))
            else:
                print("\n\n".join(render(el, ops) for _, el in sorted(els.items())) or "(还没有要素)")
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
