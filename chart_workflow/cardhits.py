"""卡成立日清单(只在调试模式下用):建好一张形态卡后,在调试段里找出「卡说成立」的那些天,列成一份能在看图
工作流里翻的清单;用户逐张标「是 / 不是」(「不是」写一句为什么),会话给「不是」的理由和待写代码的要素归类,
小结命令把这些证据汇总起来,帮用户判断形态卡要不要从「平的要素组合」改成「事件加关系」。

    CHART_WORKFLOW_MODE=debug uv run python -m chart_workflow.cardhits make --shape s001 [--version 2] \\
        [--list-id dbg-hits-s001-v2] [--max 30]
    CHART_WORKFLOW_MODE=debug uv run python -m chart_workflow.cardhits pending        # 还没归类的
    CHART_WORKFLOW_MODE=debug uv run python -m chart_workflow.cardhits classify --mark <标记编号> --category 先后 \\
        [--by session|user] [--note …]
    CHART_WORKFLOW_MODE=debug uv run python -m chart_workflow.cardhits classify --element E003 --category 缺一个量
    CHART_WORKFLOW_MODE=debug uv run python -m chart_workflow.cardhits summary

只在调试模式下用:正式模式下这几条命令、这种清单(listfile 的 card_hits)、网页上的「是 / 不是」一律拒绝。
东西只写调试账(<调试账>/card_review/)和调试模式的清单目录,不进正式账、不记账本、不算尝试。

生成清单(make):
  - 股票:和规则核对(rulecheck)逐日判卡的同一批——卡那一版的样本股,加沿全局固定顺序抽的随机池
    (rulecheck.draw_pool:抽到「这一版卡有成立日」的满 shape_check.pool_positive_stocks 只为止,最多抽
    pool_max_stocks 只)。在看图范围(调试段)里逐日按固定回看判卡,和规则核对同一个口径(rulecheck.materials)。
  - 连续几个交易日都成立算一次,取第一天(成立日);判定不了或不成立的一天把前后隔开(待验证)。
  - 成立日至少在看图下界之后 bigmoves.floor_context_bars 个交易日(和大涨段同一个口径,按这只股票自己的交易日):
    图上要留出成立之前的形态;紧挨着下界就成立的,那一段多半在下界之前就开始了,第一天也不是真的第一天。
  - 去掉以前已经仔细看过后面走势的(views.outcome_trail 的「仔细看过」,例如卡自己的样本、以前的成立日清单里
    标过的):标的时候已经知道涨跌了。只在清单里出现过的照留。
  - 去掉成立日之后的走势(到露出终点为止)已经在打开过的卡成立日清单里画出来过的:那几份打开时没标的图画到它们
    自己的成立日,这次的成立日落在那段里,后续就已经给用户看过了(看过记录里有的才算;生成了没打开的清单不挡)。
    挡路的清单、生成目录、打开的链接记进登记(prior_blockers)并打印出来。反过来的方向——这次的图画着的部分盖住了
    以前某张还没标的图的后续——生成时不管,到标那张旧图时再记(见下面「揭开后才标」)。
  - 同一份清单里同一只股票的两次,整段可见范围不许有任何交叠(listfile.drop_window_overlaps 的 disjoint):
    否则标一张的时候会从另一张露出它后面的走势。所以一只股票在一份清单里大致只有一张,是这只股票在调试段里几次
    成立里随机挑的一次;这张图成立日之前的部分里,卡也成立过的天标出来(card_true_runs,都在成立日之前,不露后续),
    看得出卡在同一段里是不是连着成立了好几次。
  - 先按固定种子打乱,再按这个顺序去掉互相露底的,取前 max_items 次(默认 MAX_ITEMS = 30,待验证)。种子由账上
    登记的训练数据副本指纹和卡的编号、版本算出:同一张卡同一版重跑,清单一样。
  - 卡上有手写触发(算不出哪天该成立)、有待写代码的要素(哪天都判定不了)、在调试段里一天都不成立、成立的都看过了、
    后续都已经在打开过的清单里画出来过:不生成清单,打印为什么和出路,在 card_review/lists.jsonl 记一行(小结里
    列出来),不当错误。
  每条的图窗从成立日往前 view.before_bars 根(截到看图下界)到成立日本身(view_end = t);露出终点 reveal_end
  = 成立日后 H 根(截到训练段末日)。marks 只有成立日,不带指标、标签、跨源比对;没有买入日,entry_date 写成立日。
  清单名默认 dbg-hits-<卡编号>-v<版本>;同名已存在就停——清单目录里有这个文件,或者调试账的生成登记里有这个名字
  (调试账是各个目录共用的一本,清单文件却在各自目录里:在别的目录生成过同名清单,这里再生成一份,小结就会重复计数)。
  生成时把清单内容的指纹记进登记;网页打开、标记时清单内容必须和登记的一样(is_registered):调试账清空过、或者是
  别处生成的同名清单,标了也进不了小结,一律拒绝,提示重新生成。

标「是 / 不是」(网页 POST /workflow/card_marks:先 check_mark 校验,通过了才记一条看过、再 record_mark):标之前
后端只放行到成立日的 K 线,标完才放行到 reveal_end,并记一条看过(show_chart,看得到结果)。可以改,但改的那一下
已经看过后面的走势:每一下都追加一行,first 标出这张图的第一下。小结按第一下算(看走势之前的判断),改过的单独
列出、不进统计(待验证);只有第一下的「不是」要归类。
揭开后才标:标第一下之前,这份清单生成以后别处(别的清单、别的界面;看过记录里每次画出的范围)已经画出过这张图
成立日之后的走势,照收,这一行带 seen_before_mark(出处),不进统计、不用归类,小结单独列出。清单生成以前的接触
不算,那由生成时管。

归类(classify):「不是」的理由、记成待写代码的要素各带一个类别。类别由会话归(by = session);用户可以改,
会话照用户的话记(by = user)。每次归类追加一行,以最后一行为准,历史都留着。类别(CATEGORIES):
  缺一个量 quantity              事实表加一行就行,平卡照样能用
  先后 relation:sequence         事件关系:先发生这个、再发生那个
  同一件事 relation:same_event   事件关系:两个条件说的是同一件事(放量就发生在那次突破当天)
  跨事件比较 relation:compare    事件关系:拿一件事的量去比另一件事的量(回踩没跌破平台上沿)
  挑哪一次 relation:which        事件关系:有好几次时指定是哪一次
  其他 other                     平卡照样能用、也不缺量(阈值不对、数据有误、说不清……)
待写代码的要素 = 要素库里任何一版没有定义(definition 为 null)的要素;它的 needs 原样保留,类别另记在这里。

小结(summary):打印,并在 card_review/summaries/ 存一份。生成登记里同名的清单只算第一次(早先的重复登记不重复计数)。
列出调试账里建了几张卡(不算已并入别的卡的);每张卡各版成立日清单:已标几张 / 共几张,第一下标「是」几张、「不是」
几张、其中归成关系类的几张,还没标的、看过走势后改了的;「不是」的理由和待写代码的要素各类别各有多少、附原话和
谁归的、还没归类的;不按卡算的两个比例(所有第一下「不是」的理由里关系类占几成、所有记成待写代码的要素里关系类
占几成,每条要素只算一次,分母都只算归了类的);碰到过关系类问题的卡占几成,分母只算有证据的卡(任何一版的清单里
有计入统计的标注,或者引用过记成待写代码、已经归了类的要素),连同没证据的卡另给一个数;揭开后才标的单独列条数。
还有没归类的、计入统计的标注少于 MIN_MARKS 下(默认 30,待验证)或者没有有证据的卡时,不给建议,写明还差什么;
否则按默认判法(有证据的卡里超过 SWITCH_SHARE = 一半碰到过,就建议改成「事件加关系」,待验证)给一句建议,同一句
写明凭了几下标注。原始数字全列,结论由用户拍板。
「这张卡碰到过关系类问题」= 下面任一条成立:
  - 这张卡任何一版的成立日清单里,有一张第一下标「不是」、理由归成事件关系;
  - 这张卡任何一版引用过的要素(合并过的连同它并入的那条)里,有记成待写代码、归成事件关系的;这条要素别的卡
    也引用的,注明和哪几张卡共用(一条共用要素会让每张引用它的卡都算碰到过)。

存放(都在 <调试账>/card_review/ 下,只追加):
  lists.jsonl       每次生成一行:清单名、卡与版本、条数、每张的可见范围、清单内容指纹、生成在哪个目录、抽了多少
                    股票、多少次成立、去掉多少(挡路的清单)、种子;没生成清单的也记一行(list_id 为 null,empty 写原因)
  marks.jsonl       每一下「是 / 不是」一行
  categories.jsonl  每次归类一行
  summaries/        小结存档(<时刻>.json)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import uuid
from collections import Counter
from datetime import datetime
from pathlib import Path

import pandas as pd

from chart_workflow import elements as E
from chart_workflow import mode, rulecheck, shapes, views
from chart_workflow.config import load_config
from chart_workflow.ledger import check_new_list_id
from chart_workflow.listfile import deep_link, drop_window_overlaps, new_list, security_fields, view_window, write_list
from chart_workflow.loader import trading_dates
from chart_workflow.state import StateRootMissing, state_root

KIND = "card_hits"
DIR = "card_review"
MAX_ITEMS = 30           # 每张卡每版至多列几次(待验证)
REASON_MAX = 500
SWITCH_SHARE = 0.5       # 碰到过关系类问题的卡超过这个比例,就建议改成「事件加关系」(待验证)
MIN_MARKS = 30           # 计入统计的标注少于这么多下,不给改不改的建议(待验证)
VERDICTS = ("yes", "no")
VERDICT_TEXT = {"yes": "是", "no": "不是"}
BY = ("session", "user")
BY_TEXT = {"session": "会话归的", "user": "你改的"}
CATEGORIES = {
    "quantity": "缺一个量",
    "relation:sequence": "事件关系·先后",
    "relation:same_event": "事件关系·同一件事",
    "relation:compare": "事件关系·跨事件比较",
    "relation:which": "事件关系·挑哪一次",
    "other": "其他",
}
CATEGORY_HINT = {
    "quantity": "事实表加一行就行,平卡照样能用",
    "relation:sequence": "先发生这个、再发生那个",
    "relation:same_event": "两个条件说的是同一件事",
    "relation:compare": "拿一件事的量去比另一件事的量",
    "relation:which": "有好几次时指定是哪一次",
    "other": "平卡照样能用、也不缺量(阈值不对、数据有误、说不清……)",
}
ALIASES = {"缺一个量": "quantity", "先后": "relation:sequence", "同一件事": "relation:same_event",
           "跨事件比较": "relation:compare", "挑哪一次": "relation:which", "其他": "other"}
RELATION = tuple(k for k in CATEGORIES if k.startswith("relation:"))
PICK_NOTE = ("同一只股票大致只列一张(两张的可见范围不许交叠),是它在调试段里几次成立中随机挑的一次;"
             "图上成立日之前的灰色段是卡也成立过的天")


class CardHitsRefused(ValueError):
    """不在调试模式、或卡 / 标记 / 归类对不上。"""


def require_debug(what: str = "卡成立日清单") -> None:
    if not mode.is_debug():
        raise CardHitsRefused(f"{what}只在调试模式下用(在调试段上攒证据,不进正式账):命令前带上 "
                              f"{mode.ENV_VAR}={mode.DEBUG};网页用 scripts/path2/run_path2_web_debug.py 启动")


def review_dir() -> Path:
    """<调试账>/card_review(不在调试模式 → CardHitsRefused;调试账不可用 → StateRootMissing)。"""
    require_debug()
    return state_root() / DIR


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _append(name: str, row: dict) -> None:
    d = review_dir()
    d.mkdir(parents=True, exist_ok=True)
    with (d / name).open("a") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _read(name: str) -> list[dict]:
    p = review_dir() / name
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text().splitlines() if line.strip()]


def read_lists() -> list[dict]:
    return _read("lists.jsonl")


def read_marks() -> list[dict]:
    return _read("marks.jsonl")


def read_categories() -> list[dict]:
    return _read("categories.jsonl")


# ── 生成清单 ─────────────────────────────────────────────────────────────────

def episodes(says: dict[str, tuple]) -> list[str]:
    """逐日卡说 {日期: (卡说, 理由)}(看图范围里的每个交易日)→ 每段连续成立的第一天,日期升序。
    判定不了(None)或不成立的一天把前后隔开。"""
    out, prev = [], False
    for day in sorted(says):
        cur = says[day][0] is True
        if cur and not prev:
            out.append(day)
        prev = cur
    return out


def _seed(pool_seed: str, shape_id: str, n: int) -> int:
    return int.from_bytes(hashlib.sha256(f"{pool_seed}|{shape_id}@v{n}".encode()).digest()[:8], "big")


def _d(x) -> str:
    return pd.Timestamp(x).strftime("%Y-%m-%d")


def true_runs_before(says: dict[str, tuple], start: str, t: str) -> list[list[str]]:
    """图窗里成立日之前、卡也成立过的天,按连续段 [[起, 止], …](都早于 t、不早于 start)。"""
    out, cur = [], None
    for day in sorted(d for d in says if start <= d < t):
        if says[day][0] is True:
            if cur is None:
                cur = [day, day]
                out.append(cur)
            else:
                cur[1] = day
        else:
            cur = None
    return out


def make_item(cfg: dict, symbol: str, t: str, says: dict[str, tuple] | None = None) -> dict:
    """清单里的一条:图窗到成立日为止,露出终点另记;card_true_runs 是成立日之前卡也成立过的天(见模块说明)。"""
    start, end = view_window(cfg, symbol, t)
    t = _d(t)
    return {"item_id": f"{symbol}@{t}", "symbol": symbol, "t": t, "entry_date": t,
            "view_start": _d(start), "view_end": t, "reveal_end": _d(end),
            "card_true_runs": true_runs_before(says or {}, _d(start), t),
            "tags": [], "marks": {"decision": t}, "metrics": {}, **security_fields(cfg, symbol)}


def registered_lists() -> dict[str, dict]:
    """生成登记里每个清单名第一次的那一行(早先同名的重复登记只认第一次)。"""
    out: dict[str, dict] = {}
    for r in read_lists():
        if r.get("list_id") and r["list_id"] not in out:
            out[r["list_id"]] = r
    return out


def is_registered(doc: dict) -> bool:
    """这份卡成立日清单的内容和调试账生成登记里同名的那一份一样(见模块说明)。"""
    r = registered_lists().get(doc.get("list_id"))
    return r is not None and r.get("list_sha12") == views.list_sha12(doc)


def unregistered_text(doc: dict) -> str:
    return (f"卡成立日清单 {doc.get('list_id')} 不在现在这本调试账的生成登记里(调试账清空过,或者是在别的目录生成的"
            f"同名清单、内容不一样),标了也进不了小结;重新生成一份再标")


def _drawn_by_card_lists(rows: list[dict]) -> dict[str, list[tuple[str, str, str]]]:
    """卡成立日清单打开以后画出过的 K 线(看过记录里有的;没打开过的清单不算):{代码: [(起, 止, 清单名)]}。"""
    out: dict[str, list[tuple[str, str, str]]] = {}
    for d in views.drawn_ranges(rows):
        if d["list_kind"] == KIND:
            out.setdefault(d["symbol"], []).append((d["start"], d["end"], d["list_id"]))
    return out


def _blockers_text(blockers: list[dict]) -> str:
    return ";".join(f"{b['list_id']} 挡了 {b['n']} 次(在 {b['lists_dir'] or '别的目录'} 生成,在那个目录起调试网页后"
                    f"打开 {deep_link(b['list_id'])})" for b in blockers)


def _where(seen: list[dict]) -> str:
    """揭开后才标的出处,给人看:清单名;不在清单里的看图(聊天贴图、补记)写「清单以外」。"""
    return "、".join(sorted({str(x.get("list_id") or "清单以外") for x in seen}))


def seen_before_mark(doc: dict, it: dict) -> list[dict]:
    """这份清单生成以后,别处(别的清单、别的界面)已经画出过这张图成立日之后的走势:[出处 {ts, list_id, event}]。
    这份清单自己的不算(标这张时自己露出的、打开时画到成立日的)。"""
    lid = doc.get("list_id")
    since = str((registered_lists().get(lid) or {}).get("ts") or "")
    sym, t, end = it.get("symbol"), str(it.get("t")), str(it.get("reveal_end"))
    out = []
    for d in views.drawn_ranges():
        if d["symbol"] == sym and d["list_id"] != lid and d["ts"] >= since and d["end"] > t and d["start"] <= end:
            src = {k: d[k] for k in ("ts", "list_id", "event")}
            if src not in out:
                out.append(src)
    return out


def _first_allowed(cfg: dict, symbol: str) -> str | None:
    """这只股票最早能列的成立日:看图下界之后第 bigmoves.floor_context_bars 个交易日;交易日不够 → None。"""
    floor = cfg.get("view_floor") or cfg["train_start"]
    try:
        dates = trading_dates(cfg, symbol)
    except (ValueError, FileNotFoundError):
        return None
    after = dates[dates >= pd.Timestamp(floor)]
    n = int(cfg["bigmoves"]["floor_context_bars"])
    return _d(after[n]) if len(after) > n else None


def card_lines(card: dict, els: dict) -> list[str]:
    """卡这一版写了什么(网页上清单顶上显示,标「不是」时好对着说):每个角色一行,触发一行。"""
    from chart_workflow.facts import TRIGGERS

    out = []
    for role in ("must", "must_not", "bonus"):
        parts = []
        for ing in card.get("ingredients", []):
            if ing.get("role") != role or not ing.get("element"):
                continue
            d = E.element_version(els, ing["element"], ing.get("element_version")).get("definition")
            parts.append(E.label(els, ing["element"]) + (f"({E.definition_text(d)})" if d else ""))
        if parts:
            out.append(f"{rulecheck.ROLE_TEXT[role]}:" + "、".join(parts))
    trig = [f"{t['term']} {TRIGGERS[t['term']][1]}" if t.get("term") in TRIGGERS else f"手写「{t.get('text') or ''}」"
            for t in card.get("triggers", [])]
    if trig:
        out.append("触发(当天出现任一个):" + "、".join(trig))
    return out


def _cannot_list(card: dict, els: dict) -> dict | None:
    """这一版卡逐日判不了的原因(None = 判得了):手写触发、待写代码的要素。"""
    custom = rulecheck.custom_triggers(card)
    if custom:
        return {"kind": "custom_trigger",
                "text": f"卡上的触发 {'、'.join(custom)} 是手写触发,没有能算的定义,算不出哪天该成立",
                "way_out": "换成表里的触发(T1~T8),或者在事实表加一行把它算出来再改写成卡上的要素"}
    pend = []
    for ing in card.get("ingredients", []):
        if ing.get("role") == "bonus" or not ing.get("element"):
            continue
        if E.element_version(els, ing["element"], ing.get("element_version")).get("definition") is None:
            pend.append(E.label(els, ing["element"]))
    if pend:
        return {"kind": "pending_code",
                "text": f"卡上的 {'、'.join(pend)} 是待写代码,哪天都判定不了,这张卡在哪天都判不出成立",
                "way_out": "先把这条要素写成计算(或换成能算的要素)再生成;它缺什么记在要素的 needs 里,"
                           "顺手用 classify --element 给它归个类"}
    return None


def _never_text(stats: dict) -> str:
    top = "、".join(f"{w}({k} 天)" for w, k in stats["why_false"][:3]) or "—"
    unk = "、".join(f"{w}({k} 天)" for w, k in stats["why_unknown"][:2])
    return (f"这一版卡在调试段里一天都不成立:看了 {stats['stocks']} 只股票、卡能判定的 {stats['days']} 天全是「不成立」"
            f"(另有 {stats['unknown']} 天判定不了{'：' + unk if unk else ''})。最常见的不成立原因:{top}")


def make(shape_id: str, version: int | None = None, list_id: str | None = None, max_items: int = MAX_ITEMS,
         cfg: dict | None = None) -> dict:
    """生成卡成立日清单(见模块说明)。返回 {"row": 记进 lists.jsonl 的那一行, "path": 清单文件 | None,
    "doc": 清单 | None}。生成不了(手写触发、待写代码、一天都不成立、都看过了)时 path / doc 为 None,
    row["empty"] 写原因。不在调试模式、卡不存在、清单名用过 → CardHitsRefused / ValueError;
    调试账不可用 → StateRootMissing。"""
    require_debug()
    cfg = cfg or load_config()
    state_root()
    _, cards, els = shapes.checked_state()
    card = cards.get(shape_id)
    if card is None:
        have = "、".join(sorted(cards)) or "一张都没有"
        raise CardHitsRefused(f"调试账里没有形态卡 {shape_id}(有的:{have})")
    if card["status"] == "merged":
        raise CardHitsRefused(f"形态卡 {shape_id} 已并入 {card.get('merged_into')},生成它并入的那张的清单")
    n = int(version or card["current_version"])
    ver = next((v for v in card["versions"] if v["version"] == n), None)
    if ver is None:
        raise CardHitsRefused(f"形态卡 {shape_id} 没有版本 v{n}(现在是 v{card['current_version']})")
    max_items = int(max_items)
    if max_items < 1:
        raise CardHitsRefused("--max 至少是 1")
    default_id = list_id is None
    list_id = list_id or f"dbg-hits-{shape_id}-v{n}"
    try:
        check_new_list_id(cfg, list_id)
    except mode.ModeError:
        raise
    except ValueError as e:
        if default_id:
            raise CardHitsRefused(f"这一版卡的成立日清单已经生成过({list_id}),接着标就行:{deep_link(list_id)};"
                                  f"确实要另生成一份,用 --list-id 换个名字(会去掉已经标过的)") from None
        raise CardHitsRefused(str(e)) from None
    reg = registered_lists().get(list_id)
    if reg is not None:
        raise CardHitsRefused(f"调试账的生成登记里已经有清单 {list_id}({reg.get('ts')} 在 {reg.get('lists_dir') or '别的目录'} "
                              f"生成):调试账是各个目录共用的一本,同名再生成一份,小结会重复计数。接着标那一份,"
                              f"或者用 --list-id 换个名字")
    name = card["name"].get("value") if isinstance(card.get("name"), dict) else card.get("name")
    row = {"ts": _now(), "list_id": None, "shape_id": shape_id, "version": n, "card_name": name, "n_items": 0}
    why = _cannot_list(ver["card"], els)
    if why:
        row["empty"] = why
        _append("lists.jsonl", row)
        return {"row": row, "path": None, "doc": None}
    anns = shapes._ann_index()
    samples = rulecheck.sample_stocks(card, n, anns)
    pool_seed = rulecheck.pool_seed(cfg)
    pool = rulecheck.draw_pool(cfg, ver["card"], els, pool_seed, samples, None, None, None)
    mats = {**rulecheck.materials(cfg, ver["card"], els, samples, None, None, None), **pool["mats"]}
    stocks = samples + [s for s in pool["stocks"] if s not in samples]
    eps, unreadable = [], []
    why_false, why_unknown = Counter(), Counter()
    days = unknown = early = 0
    for s in stocks:
        err, says, _ = mats[s]
        if err is not None:
            unreadable.append(f"{s}:{err}")
            continue
        first_ok = _first_allowed(cfg, s)
        for d in episodes(says):
            if first_ok is None or d < first_ok:
                early += 1
            else:
                eps.append((s, d))
        for v, w in says.values():
            if v is None:
                unknown += 1
                why_unknown[w] += 1
            else:
                days += 1
                if v is False:
                    why_false[w] += 1
    stats = {"stocks": len(stocks) - len(unreadable), "days": days, "unknown": unknown,
             "why_false": why_false.most_common(5), "why_unknown": why_unknown.most_common(3)}
    row.update(n_stocks_sample=len(samples), n_stocks_pool=len(pool["stocks"]),
               n_pool_positive=len(pool["positive"]), n_episodes=len(eps), n_too_early=early,
               unreadable=unreadable[:10], pool_order_seed=pool_seed)
    if not eps and early:
        row["empty"] = {"kind": "too_early",
                        "text": f"这一版卡在调试段里成立 {early} 次,都紧挨着调试段开头(看图下界之后不到 "
                                f"{cfg['bigmoves']['floor_context_bars']} 个交易日),图上留不出成立之前的形态",
                        "way_out": "这张卡在调试段上没有能看的成立日;要更多就放宽卡,或等正式段"}
        _append("lists.jsonl", row)
        return {"row": row, "path": None, "doc": None}
    if not eps:
        row["empty"] = {"kind": "never", "text": _never_text(stats),
                        "way_out": "卡比你的意思窄:看最常见的不成立原因是哪条要素,放宽它或换一条"}
        _append("lists.jsonl", row)
        return {"row": row, "path": None, "doc": None}
    rows = views.read_views()

    def dates_of(sym):
        try:
            return trading_dates(cfg, sym)
        except (ValueError, FileNotFoundError):
            return None

    fresh = []
    for s, d in eps:
        _, end = view_window(cfg, s, d)
        item = {"item_id": f"{s}@{d}", "symbol": s, "t": d, "view_end": _d(end)}
        if views.outcome_trail(item, list_id, rows, dates_of)["seen_elsewhere"]["level"] != "careful":
            fresh.append((s, d))
    row["n_seen_excluded"] = len(eps) - len(fresh)
    drawn = _drawn_by_card_lists(rows)
    clean, blockers = [], Counter()
    for s, d in fresh:
        end = _d(view_window(cfg, s, d)[1])
        hit = {lid for a, b, lid in drawn.get(s, ()) if b > d and a <= end}     # 这次成立日之后的走势已经画出来过
        if hit:
            blockers.update(hit)
        else:
            clean.append((s, d))
    row["n_prior_drawn"] = len(fresh) - len(clean)
    regs = registered_lists()
    row["prior_blockers"] = [{"list_id": lid, "n": k, "lists_dir": (regs.get(lid) or {}).get("lists_dir")}
                             for lid, k in sorted(blockers.items(), key=lambda x: (-x[1], str(x[0])))]
    if not clean and fresh:
        row["empty"] = {"kind": "prior_drawn",
                        "text": f"这一版卡在调试段里还能列的 {len(fresh)} 次,成立日之后的走势都已经在以前打开过的卡成立日"
                                f"清单里画出来过,标的时候已经知道涨跌:{_blockers_text(row['prior_blockers'])}",
                        "way_out": "这些天的后续已经给你看过,标不标那几份都改不回来;要更多就放宽卡、换一张卡,"
                                   "或者清空调试账从头来(debugroot clear,全部调试工作一起丢)"}
        _append("lists.jsonl", row)
        return {"row": row, "path": None, "doc": None}
    if not clean:
        row["empty"] = {"kind": "all_seen",
                        "text": f"这一版卡在调试段里成立 {len(eps)} 次,都已经仔细看过后面的走势(样本、以前标过的),"
                                f"标的时候已经知道涨跌,不再列",
                        "way_out": "这张卡在调试段上的证据已经用完了;要更多就放宽卡,或等正式段"}
        _append("lists.jsonl", row)
        return {"row": row, "path": None, "doc": None}
    fresh = clean
    seed = _seed(pool_seed, shape_id, n)
    order = sorted(fresh)
    random.Random(seed).shuffle(order)
    df = pd.DataFrame(order, columns=["symbol", "date"]).assign(date=lambda x: pd.to_datetime(x["date"]))
    kept = drop_window_overlaps(df, cfg, disjoint=True)
    row["n_overlap_dropped"] = len(df) - len(kept)
    picked = kept.head(max_items)
    params = {k: row[k] for k in ("shape_id", "version", "card_name", "n_stocks_sample", "n_stocks_pool",
                                  "n_pool_positive", "n_episodes", "n_too_early", "n_seen_excluded",
                                  "n_prior_drawn", "n_overlap_dropped", "pool_order_seed")}
    params.update(max_items=max_items, sample_seed=str(seed), card_lines=card_lines(ver["card"], els),
                  note=PICK_NOTE)
    doc = new_list(list_id, KIND, f"卡成立日 {shape_id}@v{n}「{name}」（{len(picked)} 张）", cfg, {KIND: params})
    doc["items"] = [make_item(cfg, s, _d(d), mats[s][1]) for s, d in zip(picked["symbol"], picked["date"])]
    ids = [it["item_id"] for it in doc["items"]]
    doc["groups"] = [{"key": "all", "title": f"全部（{len(ids)}）", "item_ids": ids}]
    path = write_list(doc, cfg)
    doc = json.loads(path.read_text())        # 指纹按落盘的内容算(网页读的就是它)
    row.update(list_id=list_id, n_items=len(ids), item_ids=ids, list_sha12=views.list_sha12(doc),
               lists_dir=str(path.parent),
               items=[{k: it[k] for k in ("item_id", "symbol", "t", "view_start", "reveal_end")} for it in doc["items"]])
    try:
        _append("lists.jsonl", row)
    except BaseException:
        path.unlink(missing_ok=True)          # 不留没登记的清单
        raise
    return {"row": row, "path": path, "doc": doc}


# ── 标「是 / 不是」 ──────────────────────────────────────────────────────────

def check_mark(doc: dict, item_id: str, verdict: str, reason: str = "") -> tuple[dict, str]:
    """标「是 / 不是」之前的全部校验(网页在记看过、放行之前先调它):通过 → (这一条, 规范化后的理由);
    不在调试模式、清单不对或没登记、参数不对 → CardHitsRefused;调试账不可用 → StateRootMissing。"""
    require_debug()
    if not isinstance(doc, dict) or doc.get("kind") != KIND:
        raise CardHitsRefused("只有卡成立日清单才标「是 / 不是」")
    foreign = mode.foreign_reason(doc, "清单")
    if foreign:
        raise CardHitsRefused(foreign)
    it = next((x for x in doc.get("items") or [] if isinstance(x, dict) and x.get("item_id") == item_id), None)
    if it is None:
        raise CardHitsRefused(f"清单 {doc.get('list_id')} 里没有 {item_id}")
    if verdict not in VERDICTS:
        raise CardHitsRefused(f"只能标 是(yes)或 不是(no): {verdict!r}")
    reason = str(reason or "").strip()
    if verdict == "no" and not reason:
        raise CardHitsRefused("标「不是」要写一句为什么")
    if len(reason) > REASON_MAX:
        raise CardHitsRefused(f"理由最多 {REASON_MAX} 字(现在 {len(reason)} 字)")
    if not is_registered(doc):
        raise CardHitsRefused(unregistered_text(doc))
    return it, ("" if verdict == "yes" else reason)


def record_mark(doc: dict, item_id: str, verdict: str, reason: str = "", surface: str = "web") -> dict:
    """记一下「是 / 不是」(只追加),返回这一行。doc 是卡成立日清单(落盘的内容)。校验见 check_mark。"""
    it, reason = check_mark(doc, item_id, verdict, reason)
    p = (doc.get("params") or {}).get(KIND) or {}
    lid = doc.get("list_id")
    prior = any(m.get("list_id") == lid and m.get("item_id") == item_id for m in read_marks())
    row = {"ts": _now(), "mark_id": uuid.uuid4().hex[:12], "list_id": lid, "item_id": item_id,
           "symbol": it.get("symbol"), "t": it.get("t"), "shape_id": p.get("shape_id"), "version": p.get("version"),
           "verdict": verdict, "reason": reason, "first": not prior, "surface": surface}
    seen = [] if prior else seen_before_mark(doc, it)
    if seen:                                  # 揭开后才标:照收,不进统计
        row["seen_before_mark"] = seen
    _append("marks.jsonl", row)
    return row


def marks_of(list_id: str, marks: list[dict] | None = None) -> dict[str, dict]:
    """一份清单里每张图的标记:{item_id: {"first": 第一下, "latest": 最后一下, "n": 一共几下}}。"""
    out: dict[str, dict] = {}
    for m in read_marks() if marks is None else marks:
        if m.get("list_id") != list_id:
            continue
        cur = out.setdefault(m["item_id"], {"first": m, "latest": m, "n": 0})
        cur["latest"] = m
        cur["n"] += 1
    return out


# ── 归类 ──────────────────────────────────────────────────────────────────────

def category_code(text: str) -> str:
    """类别的代码(认代码,也认中文简称);不认识 → CardHitsRefused,列出全部类别。"""
    t = str(text or "").strip()
    code = ALIASES.get(t, t)
    if code not in CATEGORIES:
        opts = ";".join(f"{c}({CATEGORIES[c]}:{CATEGORY_HINT[c]})" for c in CATEGORIES)
        raise CardHitsRefused(f"不认识的类别 {text!r}。可选(写代码或中文简称都行):{opts}")
    return code


def ever_pending(el: dict) -> bool:
    """这条要素有没有哪一版是待写代码(没有定义)。"""
    return any(v.get("definition") is None for v in el.get("versions") or [])


def classify(target: str, target_id: str, category: str, by: str = "session", note: str = "") -> dict:
    """给一条「不是」的理由(target = mark,标记编号)或一条记成待写代码的要素(target = element,要素编号)
    归类,追加一行并返回。对不上 → CardHitsRefused。"""
    require_debug()
    code = category_code(category)
    if by not in BY:
        raise CardHitsRefused(f"--by 只能是 session(会话归的)或 user(用户改的): {by!r}")
    if target == "mark":
        m = next((x for x in read_marks() if x.get("mark_id") == target_id), None)
        if m is None:
            raise CardHitsRefused(f"没有标记 {target_id}(用 pending 看还没归类的标记编号)")
        if m["verdict"] != "no":
            raise CardHitsRefused(f"标记 {target_id} 标的是「是」,只给「不是」的理由归类")
        if not m.get("first"):
            raise CardHitsRefused(f"标记 {target_id} 是看过走势后改的那一下,不进统计,不用归类(只给每张图的第一下归类)")
        if m.get("seen_before_mark"):
            raise CardHitsRefused(f"标记 {target_id} 是揭开后才标的(这张图的后续先在 {_where(m['seen_before_mark'])} "
                                  f"画出来过),不进统计,不用归类")
    elif target == "element":
        _, _, els = shapes.checked_state()
        if target_id not in els:
            raise CardHitsRefused(f"要素库里没有 {target_id}")
        if not ever_pending(els[target_id]):
            raise CardHitsRefused(f"{E.label(els, target_id)} 没有记成过待写代码,只给待写代码的要素归类")
    else:
        raise CardHitsRefused(f"target 只能是 mark / element: {target!r}")
    row = {"ts": _now(), "target": target, "target_id": target_id, "category": code, "by": by,
           "note": str(note or "").strip()}
    _append("categories.jsonl", row)
    return row


def current_categories(rows: list[dict] | None = None) -> dict[tuple[str, str], dict]:
    """(target, target_id) → 最后一次归类那一行(带 "changes": 一共归过几次)。"""
    out: dict[tuple[str, str], dict] = {}
    for r in read_categories() if rows is None else rows:
        k = (r["target"], r["target_id"])
        out[k] = {**r, "changes": out.get(k, {}).get("changes", 0) + 1}
    return out


def pending() -> dict:
    """还没归类的:「不是」的标记、记成待写代码的要素。"""
    require_debug()
    cats = current_categories()
    _, _, els = shapes.checked_state()
    regs = registered_lists()
    marks = [m for m in read_marks() if m["verdict"] == "no" and m.get("first") and not m.get("seen_before_mark")
             and m["list_id"] in regs and ("mark", m["mark_id"]) not in cats]
    elements = [{"element_id": eid, "label": E.label(els, eid), "needs": _needs(el)}
                for eid, el in sorted(els.items()) if ever_pending(el) and ("element", eid) not in cats]
    return {"marks": marks, "elements": elements}


def _needs(el: dict) -> str:
    return next((v.get("needs") for v in reversed(el.get("versions") or [])
                 if v.get("definition") is None and v.get("needs")), "") or ""


# ── 小结 ──────────────────────────────────────────────────────────────────────

def _card_elements(card: dict, els: dict) -> list[str]:
    """这张卡任何一版引用过的要素,合并过的连同它并入的那条。"""
    out = set()
    for v in card.get("versions") or []:
        for ing in v["card"].get("ingredients", []):
            eid = ing.get("element")
            if eid and eid in els:
                out |= {eid, E.resolve(els, eid)}
    return sorted(out)


def _share(k: int, n: int) -> float | None:
    return k / n if n else None


def summary(save: bool = True) -> dict:
    """汇总调试账里的证据(见模块说明);save 时在 card_review/summaries/ 存一份。"""
    require_debug()
    _, cards, els = shapes.checked_state()
    regs, marks, cats = registered_lists(), read_marks(), current_categories()
    empties: dict[tuple[str, int], dict] = {}
    for r in read_lists():
        if r.get("list_id") is None:
            empties[(r["shape_id"], r["version"])] = r          # 同一版没生成清单的,只留最后一次

    def cat_of(target, tid):
        c = cats.get((target, tid))
        return None if c is None else {"category": c["category"], "by": c["by"], "changes": c["changes"],
                                       "note": c.get("note") or ""}

    def is_rel(c):
        return bool(c) and c["category"] in RELATION

    live = {sid: c for sid, c in sorted(cards.items()) if c["status"] != "merged"}
    refs = {sid: _card_elements(c, els) for sid, c in live.items()}
    pending_els = {eid: {"element_id": eid, "label": E.label(els, eid), "needs": _needs(el),
                         "status": el["status"], "category": cat_of("element", eid),
                         "cards": sorted(sid for sid, r in refs.items() if eid in r)}
                   for eid, el in sorted(els.items()) if ever_pending(el)}
    reasons, changed_all, late_all, per_card = [], [], [], []
    for sid, card in live.items():
        out_lists, touched = [], []
        tot = {"n_items": 0, "marked": 0, "late": 0, "counted": 0, "yes": 0, "no": 0, "no_relation": 0}
        for lid, r in [(k, v) for k, v in regs.items() if v.get("shape_id") == sid]:
            mk = marks_of(lid, marks)
            firsts = [v["first"] for v in mk.values()]
            late = [v["first"] for v in mk.values() if v["first"].get("seen_before_mark")]
            counted = [f for f in firsts if not f.get("seen_before_mark")]
            changed = [{"item_id": k, "first": v["first"], "latest": v["latest"]} for k, v in mk.items()
                       if not v["first"].get("seen_before_mark")
                       and (v["latest"]["verdict"], v["latest"]["reason"]) != (v["first"]["verdict"], v["first"]["reason"])]
            n_rel = 0
            for f in counted:
                if f["verdict"] != "no":
                    continue
                rr = {**{k: f[k] for k in ("mark_id", "list_id", "item_id", "shape_id", "version", "reason")},
                      "category": cat_of("mark", f["mark_id"])}
                reasons.append(rr)
                if is_rel(rr["category"]):
                    n_rel += 1
                    touched.append(f"成立日清单 {lid} 里 {f['item_id']} 标「不是」:{f['reason']}"
                                   f"({CATEGORIES[rr['category']['category']]})")
            changed_all += [{**c, "list_id": lid} for c in changed]
            late_all += [{"list_id": lid, "item_id": f["item_id"], "first": f, "seen": f["seen_before_mark"]}
                         for f in late]
            x = {"version": r["version"], "list_id": lid, "n_items": r["n_items"], "marked": len(firsts),
                 "late": len(late), "counted": len(counted),
                 "yes": sum(f["verdict"] == "yes" for f in counted), "no": sum(f["verdict"] == "no" for f in counted),
                 "no_relation": n_rel, "unmarked": r["n_items"] - len(firsts), "changed": len(changed)}
            out_lists.append(x)
            for k in tot:
                tot[k] += x[k]
        for (esid, ever), r in sorted(empties.items()):
            if esid == sid and not any(x["version"] == ever for x in out_lists):
                out_lists.append({"version": ever, "list_id": None, "empty": r.get("empty")})
        out_lists.sort(key=lambda x: (x["version"], x["list_id"] or ""))
        mine = [eid for eid in refs[sid] if eid in pending_els]
        for eid in mine:
            pe = pending_els[eid]
            if is_rel(pe["category"]):
                others = [c for c in pe["cards"] if c != sid]
                touched.append(f"引用的 {pe['label']},缺:{pe['needs'] or '—'}"
                               f"({CATEGORIES[pe['category']['category']]})"
                               + (f",和 {'、'.join(others)} 共用" if others else ""))
        name = card["name"].get("value") if isinstance(card.get("name"), dict) else card.get("name")
        per_card.append({"shape_id": sid, "name": name, "status": card["status"],
                         "current_version": card["current_version"], "lists": out_lists, "totals": tot,
                         "pending_elements": mine,
                         "has_evidence": tot["counted"] > 0 or any(pending_els[e]["category"] for e in mine),
                         "touched_relation": touched})
    by_cat: dict[str, dict] = {c: {"reasons": [], "elements": []} for c in CATEGORIES}
    unclassified = {"reasons": [r for r in reasons if r["category"] is None],
                    "elements": [e for e in pending_els.values() if e["category"] is None]}
    for r in reasons:
        if r["category"]:
            by_cat[r["category"]["category"]]["reasons"].append(r)
    for e in pending_els.values():
        if e["category"]:
            by_cat[e["category"]["category"]]["elements"].append(e)
    rc = [r for r in reasons if r["category"]]
    ec = [e for e in pending_els.values() if e["category"]]
    ratios = {"reasons": {"n": len(reasons), "classified": len(rc), "relation": sum(is_rel(r["category"]) for r in rc)},
              "elements": {"n": len(pending_els), "classified": len(ec),
                           "relation": sum(is_rel(e["category"]) for e in ec)}}
    for v in ratios.values():
        v["share"] = _share(v["relation"], v["classified"])
    n_cards = len(per_card)
    n_ev = sum(c["has_evidence"] for c in per_card)
    n_touched = sum(bool(c["touched_relation"]) for c in per_card)
    share = _share(n_touched, n_ev)
    n_counted = sum(c["totals"]["counted"] for c in per_card)
    gaps = []                                 # 证据还差什么(有一条就不给建议)
    if unclassified["reasons"] or unclassified["elements"]:
        gaps.append(f"还有 {len(unclassified['reasons'])} 条「不是」的理由、{len(unclassified['elements'])} 条待写代码的"
                    f"要素没归类(pending 列出编号)")
    if n_counted < MIN_MARKS:
        gaps.append(f"计入统计的标注一共 {n_counted} 下,至少要 {MIN_MARKS} 下(默认,待验证)")
    if share is None:
        gaps.append("还没有有证据的形态卡")
    out = {"ts": _now(), "n_cards": n_cards, "n_merged": len(cards) - n_cards, "cards": per_card,
           "by_category": by_cat, "unclassified": unclassified, "changed_after_reveal": changed_all,
           "late_marks": late_all, "n_marks_counted": n_counted, "min_marks": MIN_MARKS,
           "ratios": ratios, "n_cards_with_evidence": n_ev, "n_cards_touched_relation": n_touched,
           "share_touched_relation": share, "share_touched_relation_all_cards": _share(n_touched, n_cards),
           "switch_share": SWITCH_SHARE, "not_enough": gaps,
           "suggest_switch": None if gaps else share > SWITCH_SHARE}
    if save:
        d = review_dir() / "summaries"
        d.mkdir(parents=True, exist_ok=True)
        stem = datetime.now().strftime("%Y%m%dT%H%M%S")
        p, k = d / f"{stem}.json", 1
        while p.exists():
            k += 1
            p = d / f"{stem}-{k}.json"
        p.write_text(json.dumps(out, ensure_ascii=False, indent=1))
        out["saved_to"] = str(p)
    return out


def _by(cat: dict) -> str:
    more = f",归过 {cat['changes']} 次" if cat["changes"] > 1 else ""
    return f"[{BY_TEXT[cat['by']]}{more}]"


def _pct(x: float | None) -> str:
    return "—" if x is None else f"{x:.0%}"


def render_summary(s: dict) -> str:
    """小结的人话版本。"""
    L = [mode.DEBUG_LABEL, f"调试账里建了 {s['n_cards']} 张形态卡"
         + (f"(另有 {s['n_merged']} 张已并入别的卡,不算)" if s["n_merged"] else "")
         + f",其中有证据的 {s['n_cards_with_evidence']} 张(有计入统计的标注,或者引用过归了类的待写代码要素)。",
         f"每份成立日清单里,{PICK_NOTE}。", ""]
    for c in s["cards"]:
        L.append(f"■ {c['shape_id']}「{c['name']}」(现在 v{c['current_version']},"
                 f"{shapes.STATUS_TEXT.get(c['status'], c['status'])})" + ("" if c["has_evidence"] else ",还没有证据"))
        if not c["lists"]:
            L.append("  还没生成成立日清单")
        for x in c["lists"]:
            if x["list_id"] is None:
                L.append(f"  v{x['version']}:没生成清单——{(x.get('empty') or {}).get('text', '')}")
            else:
                L.append(f"  v{x['version']} 成立日清单 {x['list_id']}:已标 {x['marked']} / {x['n_items']} 张"
                         + (f"(其中揭开后才标 {x['late']} 张,不进统计)" if x["late"] else "")
                         + f";第一下标「是」{x['yes']} 张、「不是」{x['no']} 张,其中归成关系类的 {x['no_relation']} 张"
                         + (f";看过走势后改了 {x['changed']} 张" if x["changed"] else ""))
        if c["pending_elements"]:
            L.append(f"  引用过的待写代码要素:{'、'.join(c['pending_elements'])}")
        L.append("  碰到过关系类问题:" + ("是。" + ";".join(c["touched_relation"]) if c["touched_relation"] else "没有"))
    L += ["", "「不是」的理由(每张图按第一下算)和待写代码的要素,按类别:"]
    for code, label in CATEGORIES.items():
        b = s["by_category"][code]
        L.append(f"  {label}:理由 {len(b['reasons'])} 条,要素 {len(b['elements'])} 条")
        for r in b["reasons"]:
            L.append(f"    · {r['item_id']}({r['shape_id']}@v{r['version']}):「{r['reason']}」{_by(r['category'])}")
        for e in b["elements"]:
            L.append(f"    · {e['label']} 缺:{e['needs'] or '—'} {_by(e['category'])}"
                     + (f"(引用它的卡:{'、'.join(e['cards'])})" if e["cards"] else ""))
    u = s["unclassified"]
    if u["reasons"] or u["elements"]:
        L.append(f"  还没归类:理由 {len(u['reasons'])} 条、要素 {len(u['elements'])} 条(pending 列出编号)")
    rr, re_ = s["ratios"]["reasons"], s["ratios"]["elements"]
    L += ["", "不按卡算:",
          f"  所有第一下「不是」的理由 {rr['n']} 条,归了类的 {rr['classified']} 条里关系类 {rr['relation']} 条"
          f"({_pct(rr['share'])})",
          f"  所有记成待写代码的要素 {re_['n']} 条(每条只算一次),归了类的 {re_['classified']} 条里关系类 "
          f"{re_['relation']} 条({_pct(re_['share'])})"]
    if s["changed_after_reveal"]:
        L += ["", f"看过走势后改了的 {len(s['changed_after_reveal'])} 张(不进上面的数):"]
        for c in s["changed_after_reveal"]:
            f, la = c["first"], c["latest"]
            L.append(f"  · {c['item_id']}:第一下「{VERDICT_TEXT[f['verdict']]}」{f['reason']} → "
                     f"后来「{VERDICT_TEXT[la['verdict']]}」{la['reason']}")
    if s["late_marks"]:
        L += ["", f"揭开后才标的 {len(s['late_marks'])} 张(这张图成立日之后的走势先在别处画出来过,不进上面的数):"]
        for c in s["late_marks"]:
            L.append(f"  · {c['item_id']}(清单 {c['list_id']}):先在 {_where(c['seen'])} 看到过后续,"
                     f"标的是「{VERDICT_TEXT[c['first']['verdict']]}」{c['first']['reason']}")
    L.append("")
    if s["share_touched_relation"] is not None:
        L.append(f"碰到过关系类问题的卡:有证据的 {s['n_cards_with_evidence']} 张里 {s['n_cards_touched_relation']} 张"
                 f"({_pct(s['share_touched_relation'])});连同没证据的是 {s['n_cards_touched_relation']} / "
                 f"{s['n_cards']} 张。")
    if s["not_enough"]:
        L.append("证据还不够,先不给改不改的建议:" + ";".join(s["not_enough"]) + "。")
    else:
        verdict = ("建议把形态卡改成「事件加关系」" if s["suggest_switch"] else "暂不建议改,平的要素组合还够用")
        L.append(f"按默认判法(有证据的卡里超过 {s['switch_share']:.0%} 碰到过就建议改,待验证),凭计入统计的 "
                 f"{s['n_marks_counted']} 下标注、有证据的 {s['n_cards_with_evidence']} 张卡:{verdict}。结论由你拍板。")
    if s.get("saved_to"):
        L.append(f"(这份小结存在 {s['saved_to']})")
    return "\n".join(L)


# ── 命令行 ────────────────────────────────────────────────────────────────────

def _print_make(res: dict) -> None:
    row = res["row"]
    head = f"形态卡 {row['shape_id']}@v{row['version']}「{row['card_name']}」"
    if res["path"] is None:
        e = row["empty"]
        print(f"提示:{head} 没生成成立日清单。{e['text']}。出路:{e['way_out']}。(已记进调试账,小结里会列出来)")
        return
    print(f"写入 {res['path']}(调试模式的清单;标记和小结只写调试账,不进正式账、不记账本、不算尝试)")
    print(f"{head}:样本股 {row['n_stocks_sample']} 只 + 随机抽 {row['n_stocks_pool']} 只(其中有成立日的 "
          f"{row['n_pool_positive']} 只);连续成立算一次,共 {row['n_episodes']} 次(另有 {row['n_too_early']} 次紧挨着"
          f"调试段开头、没列),去掉以前仔细看过后面走势的 {row['n_seen_excluded']} 次、后续走势已在以前打开过的清单里"
          f"画出来的 {row['n_prior_drawn']} 次、同股互相露底的 {row['n_overlap_dropped']} 次,列 {row['n_items']} 张"
          f"(同一只股票大致一张,随机挑其中一次)")
    if row["prior_blockers"]:
        print("  后续走势已画出来的那几次,挡路的清单:" + _blockers_text(row["prior_blockers"]))
    if row.get("unreadable"):
        print("读不了的股票:" + ";".join(row["unreadable"]), file=sys.stderr)
    print("打开:", deep_link(row["list_id"]))
    print("在网页里每张点「是」或「不是」(「不是」写一句为什么);标完才露出成立日之后的走势。")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="卡成立日清单(只在调试模式下用)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    mk = sub.add_parser("make", help="生成一张卡的成立日清单")
    mk.add_argument("--shape", required=True)
    mk.add_argument("--version", type=int, default=None, help="卡的版本,默认当前版本")
    mk.add_argument("--list-id", default=None, help="默认 dbg-hits-<卡编号>-v<版本>")
    mk.add_argument("--max", type=int, default=MAX_ITEMS, help=f"至多列几次,默认 {MAX_ITEMS}(待验证)")
    sub.add_parser("pending", help="还没归类的「不是」理由与待写代码要素")
    cl = sub.add_parser("classify", help="给「不是」的理由或待写代码的要素归类")
    g = cl.add_mutually_exclusive_group(required=True)
    g.add_argument("--mark", help="标记编号(pending 里列着)")
    g.add_argument("--element", help="要素编号")
    cl.add_argument("--category", required=True,
                    help="类别:" + " / ".join(f"{c}({v})" for c, v in CATEGORIES.items()) + ";也认中文简称")
    cl.add_argument("--by", default="session", choices=BY, help="谁归的:session(会话,默认)/ user(用户改的)")
    cl.add_argument("--note", default="")
    sm = sub.add_parser("summary", help="小结")
    sm.add_argument("--no-save", action="store_true", help="只打印,不存档")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "make":
            _print_make(make(args.shape, args.version, args.list_id, args.max))
        elif args.cmd == "pending":
            p = pending()
            print(f"还没归类的「不是」:{len(p['marks'])} 条")
            for m in p["marks"]:
                print(f"  {m['mark_id']}  {m['item_id']}({m['shape_id']}@v{m['version']}):「{m['reason']}」")
            print(f"还没归类的待写代码要素:{len(p['elements'])} 条")
            for e in p["elements"]:
                print(f"  {e['element_id']}  {e['label']} 缺:{e['needs'] or '—'}")
            print("类别:" + ";".join(f"{v}({c}):{CATEGORY_HINT[c]}" for c, v in CATEGORIES.items()))
        elif args.cmd == "classify":
            target, tid = ("mark", args.mark) if args.mark else ("element", args.element)
            r = classify(target, tid, args.category, args.by, args.note)
            print(f"已归类:{tid} → {CATEGORIES[r['category']]}({BY_TEXT[r['by']]})")
        else:
            print(render_summary(summary(save=not args.no_save)))
    except (ValueError, StateRootMissing, FileNotFoundError) as e:
        print(f"错误:{e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
