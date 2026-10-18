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
  - 同一只股票的两次,谁的成立日都不落在另一次的完整图窗里(listfile.drop_window_overlaps,图窗到露出终点):
    否则标一张的时候会从另一张露出它后面的走势。
  - 先按固定种子打乱,再按这个顺序去掉互相露底的,取前 max_items 次(默认 MAX_ITEMS = 30,待验证)。种子由账上
    登记的训练数据副本指纹和卡的编号、版本算出:同一张卡同一版重跑,清单一样。
  - 卡上有手写触发(算不出哪天该成立)、有待写代码的要素(哪天都判定不了)、在调试段里一天都不成立、成立的都看过了:
    不生成清单,打印为什么和出路,在 card_review/lists.jsonl 记一行(小结里列出来),不当错误。
  每条的图窗从成立日往前 view.before_bars 根(截到看图下界)到成立日本身(view_end = t);露出终点 reveal_end
  = 成立日后 H 根(截到训练段末日)。marks 只有成立日,不带指标、标签、跨源比对;没有买入日,entry_date 写成立日。
  清单名默认 dbg-hits-<卡编号>-v<版本>;同名已存在就停。

标「是 / 不是」(网页 POST /workflow/card_marks 调 record_mark):标之前后端只放行到成立日的 K 线,标完才放行到
reveal_end,并记一条看过(show_chart,看得到结果)。可以改,但改的那一下已经看过后面的走势:每一下都追加一行,
first 标出这张图的第一下。小结按第一下算(看走势之前的判断),改过的单独列出(待验证)。

归类(classify):「不是」的理由、记成待写代码的要素各带一个类别。类别由会话归(by = session);用户可以改,
会话照用户的话记(by = user)。每次归类追加一行,以最后一行为准,历史都留着。类别(CATEGORIES):
  缺一个量 quantity              事实表加一行就行,平卡照样能用
  先后 relation:sequence         事件关系:先发生这个、再发生那个
  同一件事 relation:same_event   事件关系:两个条件说的是同一件事(放量就发生在那次突破当天)
  跨事件比较 relation:compare    事件关系:拿一件事的量去比另一件事的量(回踩没跌破平台上沿)
  挑哪一次 relation:which        事件关系:有好几次时指定是哪一次
  其他 other                     平卡照样能用、也不缺量(阈值不对、数据有误、说不清……)
待写代码的要素 = 要素库里任何一版没有定义(definition 为 null)的要素;它的 needs 原样保留,类别另记在这里。

小结(summary):打印,并在 card_review/summaries/ 存一份。列出调试账里建了几张卡(不算已并入别的卡的);每张卡
各版成立日清单的条数,第一下标「是」「不是」各几张、还没标的、看过走势后改了的;「不是」的理由和待写代码的要素
各类别各有多少、附原话和谁归的、还没归类的;碰到过关系类问题的卡占几成;按默认判法(超过 SWITCH_SHARE = 一半
就建议改成「事件加关系」,待验证)给一句建议。原始数字全列,结论由用户拍板。
「这张卡碰到过关系类问题」= 下面任一条成立:
  - 这张卡任何一版的成立日清单里,有一张第一下标「不是」、理由归成事件关系;
  - 这张卡任何一版引用过的要素(合并过的连同它并入的那条)里,有记成待写代码、归成事件关系的。

存放(都在 <调试账>/card_review/ 下,只追加):
  lists.jsonl       每次生成一行:清单名、卡与版本、条数、抽了多少股票、多少次成立、去掉多少、种子;
                    没生成清单的也记一行(list_id 为 null,empty 写原因)
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


def make_item(cfg: dict, symbol: str, t: str) -> dict:
    """清单里的一条:图窗到成立日为止,露出终点另记(见模块说明)。"""
    start, end = view_window(cfg, symbol, t)
    t = _d(t)
    return {"item_id": f"{symbol}@{t}", "symbol": symbol, "t": t, "entry_date": t,
            "view_start": _d(start), "view_end": t, "reveal_end": _d(end),
            "tags": [], "marks": {"decision": t}, "metrics": {}, **security_fields(cfg, symbol)}


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
    if not fresh:
        row["empty"] = {"kind": "all_seen",
                        "text": f"这一版卡在调试段里成立 {len(eps)} 次,都已经仔细看过后面的走势(样本、以前标过的),"
                                f"标的时候已经知道涨跌,不再列",
                        "way_out": "这张卡在调试段上的证据已经用完了;要更多就放宽卡,或等正式段"}
        _append("lists.jsonl", row)
        return {"row": row, "path": None, "doc": None}
    seed = _seed(pool_seed, shape_id, n)
    order = sorted(fresh)
    random.Random(seed).shuffle(order)
    df = pd.DataFrame(order, columns=["symbol", "date"]).assign(date=lambda x: pd.to_datetime(x["date"]))
    kept = drop_window_overlaps(df, cfg)
    row["n_overlap_dropped"] = len(df) - len(kept)
    picked = kept.head(max_items)
    params = {k: row[k] for k in ("shape_id", "version", "card_name", "n_stocks_sample", "n_stocks_pool",
                                  "n_pool_positive", "n_episodes", "n_too_early", "n_seen_excluded",
                                  "n_overlap_dropped", "pool_order_seed")}
    params.update(max_items=max_items, sample_seed=str(seed), card_lines=card_lines(ver["card"], els))
    doc = new_list(list_id, KIND, f"卡成立日 {shape_id}@v{n}「{name}」（{len(picked)} 张）", cfg, {KIND: params})
    doc["items"] = [make_item(cfg, s, _d(d)) for s, d in zip(picked["symbol"], picked["date"])]
    ids = [it["item_id"] for it in doc["items"]]
    doc["groups"] = [{"key": "all", "title": f"全部（{len(ids)}）", "item_ids": ids}]
    path = write_list(doc, cfg)
    row.update(list_id=list_id, n_items=len(ids), item_ids=ids)
    try:
        _append("lists.jsonl", row)
    except BaseException:
        path.unlink(missing_ok=True)          # 不留没登记的清单
        raise
    return {"row": row, "path": path, "doc": doc}


# ── 标「是 / 不是」 ──────────────────────────────────────────────────────────

def record_mark(doc: dict, item_id: str, verdict: str, reason: str = "", surface: str = "web") -> dict:
    """记一下「是 / 不是」(只追加),返回这一行。doc 是卡成立日清单。不在调试模式、清单不对、参数不对 →
    CardHitsRefused;调试账不可用 → StateRootMissing。"""
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
        raise CardHitsRefused(f"理由最多 {REASON_MAX} 字")
    if verdict == "yes":
        reason = ""
    p = (doc.get("params") or {}).get(KIND) or {}
    lid = doc.get("list_id")
    prior = any(m.get("list_id") == lid and m.get("item_id") == item_id for m in read_marks())
    row = {"ts": _now(), "mark_id": uuid.uuid4().hex[:12], "list_id": lid, "item_id": item_id,
           "symbol": it.get("symbol"), "t": it.get("t"), "shape_id": p.get("shape_id"), "version": p.get("version"),
           "verdict": verdict, "reason": reason, "first": not prior, "surface": surface}
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
    marks = [m for m in read_marks() if m["verdict"] == "no" and ("mark", m["mark_id"]) not in cats]
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


def summary(save: bool = True) -> dict:
    """汇总调试账里的证据(见模块说明);save 时在 card_review/summaries/ 存一份。"""
    require_debug()
    _, cards, els = shapes.checked_state()
    lists, marks, cats = read_lists(), read_marks(), current_categories()

    def cat_of(target, tid):
        c = cats.get((target, tid))
        return None if c is None else {"category": c["category"], "by": c["by"], "changes": c["changes"],
                                       "note": c.get("note") or ""}

    live = {sid: c for sid, c in sorted(cards.items()) if c["status"] != "merged"}
    pending_els = {eid: {"element_id": eid, "label": E.label(els, eid), "needs": _needs(el),
                         "status": el["status"], "category": cat_of("element", eid)}
                   for eid, el in sorted(els.items()) if ever_pending(el)}
    reasons, changed_all, per_card = [], [], []
    for sid, card in live.items():
        out_lists, touched = [], []
        for r in [x for x in lists if x.get("shape_id") == sid]:
            if r.get("list_id") is None:
                out_lists.append({"version": r["version"], "list_id": None, "empty": r.get("empty")})
                continue
            mk = marks_of(r["list_id"], marks)
            firsts = [v["first"] for v in mk.values()]
            changed = [{"item_id": k, "first": v["first"], "latest": v["latest"]} for k, v in mk.items()
                       if (v["latest"]["verdict"], v["latest"]["reason"]) != (v["first"]["verdict"], v["first"]["reason"])]
            for f in firsts:
                if f["verdict"] == "no":
                    rr = {**{k: f[k] for k in ("mark_id", "list_id", "item_id", "shape_id", "version", "reason")},
                          "category": cat_of("mark", f["mark_id"])}
                    reasons.append(rr)
                    if rr["category"] and rr["category"]["category"] in RELATION:
                        touched.append(f"成立日清单 {r['list_id']} 里 {f['item_id']} 标「不是」:{f['reason']}"
                                       f"({CATEGORIES[rr['category']['category']]})")
            changed_all += [{**c, "list_id": r["list_id"]} for c in changed]
            out_lists.append({"version": r["version"], "list_id": r["list_id"], "n_items": r["n_items"],
                              "yes": sum(f["verdict"] == "yes" for f in firsts),
                              "no": sum(f["verdict"] == "no" for f in firsts),
                              "unmarked": r["n_items"] - len(firsts), "changed": len(changed)})
        refs = _card_elements(card, els)
        for eid in refs:
            pe = pending_els.get(eid)
            if pe and pe["category"] and pe["category"]["category"] in RELATION:
                touched.append(f"引用的 {pe['label']},缺:{pe['needs'] or '—'}"
                               f"({CATEGORIES[pe['category']['category']]})")
        name = card["name"].get("value") if isinstance(card.get("name"), dict) else card.get("name")
        per_card.append({"shape_id": sid, "name": name, "status": card["status"],
                         "current_version": card["current_version"], "lists": out_lists,
                         "pending_elements": [eid for eid in refs if eid in pending_els],
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
    n_cards = len(per_card)
    n_touched = sum(bool(c["touched_relation"]) for c in per_card)
    share = n_touched / n_cards if n_cards else None
    out = {"ts": _now(), "n_cards": n_cards, "n_merged": len(cards) - n_cards, "cards": per_card,
           "by_category": by_cat, "unclassified": unclassified, "changed_after_reveal": changed_all,
           "n_cards_touched_relation": n_touched, "share_touched_relation": share,
           "switch_share": SWITCH_SHARE,
           "suggest_switch": None if share is None else share > SWITCH_SHARE,
           "n_cards_without_evidence": sum(not any(x.get("yes") or x.get("no") for x in c["lists"])
                                           and not c["pending_elements"] for c in per_card)}
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


def render_summary(s: dict) -> str:
    """小结的人话版本。"""
    L = [mode.DEBUG_LABEL, f"调试账里建了 {s['n_cards']} 张形态卡"
         + (f"(另有 {s['n_merged']} 张已并入别的卡,不算)" if s["n_merged"] else "") + "。", ""]
    for c in s["cards"]:
        L.append(f"■ {c['shape_id']}「{c['name']}」(现在 v{c['current_version']},"
                 f"{shapes.STATUS_TEXT.get(c['status'], c['status'])})")
        if not c["lists"]:
            L.append("  还没生成成立日清单")
        for x in c["lists"]:
            if x["list_id"] is None:
                L.append(f"  v{x['version']}:没生成清单——{(x.get('empty') or {}).get('text', '')}")
            else:
                L.append(f"  v{x['version']} 成立日清单 {x['list_id']}:{x['n_items']} 张,第一下标「是」{x['yes']} 张、"
                         f"「不是」{x['no']} 张,还没标 {x['unmarked']} 张"
                         + (f",看过走势后改了 {x['changed']} 张" if x["changed"] else ""))
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
            L.append(f"    · {e['label']} 缺:{e['needs'] or '—'} {_by(e['category'])}")
    u = s["unclassified"]
    if u["reasons"] or u["elements"]:
        L.append(f"  还没归类:理由 {len(u['reasons'])} 条、要素 {len(u['elements'])} 条(pending 列出编号)")
    if s["changed_after_reveal"]:
        L += ["", f"看过走势后改了的 {len(s['changed_after_reveal'])} 张(不进上面的数):"]
        for c in s["changed_after_reveal"]:
            f, la = c["first"], c["latest"]
            L.append(f"  · {c['item_id']}:第一下「{VERDICT_TEXT[f['verdict']]}」{f['reason']} → "
                     f"后来「{VERDICT_TEXT[la['verdict']]}」{la['reason']}")
    L.append("")
    if s["share_touched_relation"] is None:
        L.append("还没有形态卡,谈不上要不要改写法。")
    else:
        L.append(f"碰到过关系类问题的卡:{s['n_cards_touched_relation']} / {s['n_cards']} 张"
                 f"({s['share_touched_relation']:.0%});还没有任何证据的卡 {s['n_cards_without_evidence']} 张。")
        verdict = ("建议把形态卡改成「事件加关系」" if s["suggest_switch"] else "暂不建议改,平的要素组合还够用")
        L.append(f"按默认判法(超过 {s['switch_share']:.0%} 的卡碰到过就建议改,待验证):{verdict}。"
                 + ("还有没归类的,归完可能会变。" if u["reasons"] or u["elements"] else "") + "结论由你拍板。")
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
          f"调试段开头、没列),去掉以前仔细看过后面走势的 "
          f"{row['n_seen_excluded']} 次、同股互相露底的 {row['n_overlap_dropped']} 次,列 {row['n_items']} 张")
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
