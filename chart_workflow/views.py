"""看过记录:用户每看一次图(网页打开清单、看图工作流里放大 / 标注单张图、调试视图里看一张图或预览一只
股票、调试视图打开扫描结果、会话在聊天里贴图、补记历史接触)都记一行。

record() 是写 <状态根>/views.jsonl 的唯一入口(后端打开清单、收单张图事件、调试视图取 K 线时调用;
会话经下面的命令行调用)。对照页排除看过的样本、按尝试扣运气都要用这份记录;以哪一级为准、排除逻辑
本身不在这里。

行格式(每行一个 JSON):
{"ts": "YYYY-MM-DDTHH:MM:SS",
 "surface": "web | debug | chat | manual",   # 看图工作流 / 调试视图 / 会话在聊天里贴的图 / 补记
 "event": "open_list | show_chart | zoom_chart | annotate_chart | reveal | peek_chart",
 "list_id": "r001-bigmoves" | null, "list_kind": "bigmoves" | null,
 "outcome_visible": true,                 # 看图时看不看得到结果:盲看清单为 false,其余为 true
 "list_sha12": "<清单内容 sha256 前 12 位>" | null,
 "snapshot": "viewed_lists/<list_id>@<sha12>.json" | null,
 "charts": [{"symbol": "DJT", "start": "2023-07-21", "end": "2024-03-11"}],   # show_chart 用
 "note": "", "backfill": false,
 "outside_reason": "…",                   # 只有聊天里记了下界以外的图窗时才有
 "item_id": "DJT@2025-06-02",             # 单张图事件才有
 "buy_points": [{"date", "primary"}]}     # 只有 reveal 才有:露出结果那一刻的买点

事件:
  open_list       打开整份清单(整份都算看过,保守口径);调试视图打开扫描结果也记这个(list_kind = debug_scan)
  show_chart      看了一张图:调试视图取 K 线或单股预览(surface = debug)、会话在聊天里贴图、补记
  zoom_chart      看图工作流里放大看了某一张图
  annotate_chart  看图工作流里给某一张图点了买点或选了判定
  reveal          大涨段清单里某一张图第一次露出结果(买点从无到有),带当时的买点;
                  后端收标注时以这张图最早那次 reveal 的买点为准(见 first_reveals)
  peek_chart      大涨段清单里某一张图点买点前把窗口往右拖、看了决策日之后的走势
单张图事件每张图每种在一次打开清单里只记一次(前端去重)。

大涨段标注收进来时,后端用 outcome_trail 从全部看过记录查这一条决策日之后的走势,在这张图第一次露出结果
之前是否已经在别处露出过(同代码、图窗盖住决策日之后那段、看得到结果),分两级记:
  careful   仔细看过:单张图的放大、标注、露出结果、往右拖看后续,调试视图看那只股票的图,聊天贴图,补记
  in_list   只在清单里出现过:只是打开过含它的清单(看图工作流或调试视图打开整份清单)
看图工作流里大涨段的图没露出结果前只露到决策日后 PRE_REVEAL_RIGHT_MAX 根;同一份大涨段清单里的同股条目
按生成规则看不到彼此的决策日,只会从左端露出一点别条的后续(左端残留),不计;这一条自己(同一个条目,
在哪份大涨段清单里都一样)露出结果前那一小段是设计上就给看的,也不计;这一条自己往右拖看后续另记
peeked_before_buy,不算「别处」。以哪一级为准由流程骨架定,这里只如实记。

会话在聊天里贴图(surface = chat)时,图窗(以及记整份清单时清单里每条的图窗)不得早于本轮看图下界
view_floor、不得晚于训练段末日:越界就拒绝,提醒会话这张图本不该贴。确实要记(例如用户主动贴了旧图),
显式加 --allow-outside 并用 --reason 写明原因,原因记进这一行。补记(manual)不受此限:历史接触本来就早。
写完调 state.advance,把新行记进水位。

打开清单时整份清单都算看过(保守口径):viewed_lists/<list_id>@<sha12>.json 不存在就写一份,
只存每条的 item_id / symbol / t / view_start / view_end 和清单的 kind / title / created_at /
train_end,不存任何结果数值;清单文件日后被删,看过的范围也不丢。

    uv run python -m chart_workflow.views record --surface chat --symbol S --start D --end D \\
        --outcome-visible yes|no [--note …]
    uv run python -m chart_workflow.views record --surface manual --backfill --ts 2026-10-16T09:50:52 \\
        --list-id r001-bigmoves --symbol DJT --start 2023-07-21 --end 2024-03-11 --outcome-visible yes \\
        --note "补记:…"
    uv run python -m chart_workflow.views show [--symbol S]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path

from chart_workflow import state as _state
from chart_workflow.config import load_config, root_dir
from chart_workflow.state import StateRootMissing, state_root

SURFACES = ("web", "debug", "chat", "manual")
EVENTS = ("open_list", "show_chart", "zoom_chart", "annotate_chart", "reveal", "peek_chart")
CHART_EVENTS = ("zoom_chart", "annotate_chart", "reveal", "peek_chart")     # 看图工作流里的单张图事件
CAREFUL_EVENTS = ("show_chart",) + CHART_EVENTS              # 仔细看过:单张图(另加聊天贴图、补记)
PRE_REVEAL_RIGHT_MAX = 15        # 大涨段露出结果前一张图最多露到决策日后几根(与前端 INITIAL_RIGHT_MAX 同值)
SNAPSHOT_SCHEMA = "chart_workflow.viewed_list/1"
ITEM_FIELDS = ("item_id", "symbol", "t", "view_start", "view_end")
LIST_FIELDS = ("kind", "title", "created_at", "train_end")
# 与清单文件名同口径:字母数字 _ - .,不以点开头、不含 ..
_LIST_ID_RE = re.compile(r"^(?!\.)(?!.*\.\.)[A-Za-z0-9_\-.]+$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")


def views_path() -> Path:
    return state_root() / "views.jsonl"


def list_sha12(doc: dict) -> str:
    """清单内容指纹:规范化 JSON(键排序)的 sha256 前 12 位。"""
    raw = json.dumps(doc, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def _snapshot(root: Path, list_id: str, doc: dict) -> tuple[str, str]:
    sha = list_sha12(doc)
    rel = f"viewed_lists/{list_id}@{sha}.json"
    path = root / rel
    if not path.exists():
        snap = {"schema": SNAPSHOT_SCHEMA, "list_id": list_id, "sha12": sha,
                **{k: doc.get(k) for k in LIST_FIELDS},
                "items": [{k: it.get(k) for k in ITEM_FIELDS}
                          for it in doc.get("items") or [] if isinstance(it, dict)]}
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(snap, ensure_ascii=False, indent=1))
        tmp.replace(path)
    return sha, rel


def _check_charts(charts) -> list[dict]:
    out = []
    for c in charts or []:
        sym, s, e = c.get("symbol"), c.get("start"), c.get("end")
        if not (isinstance(sym, str) and sym and isinstance(s, str) and isinstance(e, str)
                and _DATE_RE.match(s) and _DATE_RE.match(e) and s <= e):
            raise ValueError(f"图窗不合法: {c!r}")
        out.append({"symbol": sym, "start": s, "end": e})
    return out


def _outside(windows: list[tuple[str, str, str]], floor: str | None, train_end: str) -> list[str]:
    """越过看图下界或训练段末日的图窗,一条一句。"""
    out = []
    for sym, s, e in windows:
        if floor and str(s) < floor:
            out.append(f"{sym} {s}→{e} 早于本轮看图下界 {floor}")
        elif str(e) > train_end:
            out.append(f"{sym} {s}→{e} 晚于训练段末日 {train_end}")
    return out


def record(*, surface: str, event: str, outcome_visible: bool, list_id: str | None = None,
           list_kind: str | None = None, list_doc: dict | None = None, charts=None,
           note: str = "", ts: str | None = None, backfill: bool = False,
           allow_outside: bool = False, outside_reason: str = "", item_id: str | None = None,
           buy_points: list | None = None) -> dict:
    """追加一行看过记录,返回这一行。参数不合法 → ValueError;拿不到状态根 → StateRootMissing。
    surface = chat 时图窗越过看图下界或训练段末日 → ValueError,除非 allow_outside 且写了 outside_reason。"""
    if surface not in SURFACES:
        raise ValueError(f"surface 必须是 {SURFACES} 之一: {surface!r}")
    if event not in EVENTS:
        raise ValueError(f"event 必须是 {EVENTS} 之一: {event!r}")
    if not isinstance(outcome_visible, bool):
        raise ValueError("outcome_visible 必须是 true / false")
    if backfill and (not ts or not str(note).strip()):
        raise ValueError("补记必须给 ts 和写明来源的 note")
    if ts is not None and not _TS_RE.match(str(ts)):
        raise ValueError(f"ts 必须是 YYYY-MM-DDTHH:MM:SS: {ts!r}")
    if list_id is not None and not _LIST_ID_RE.fullmatch(list_id):
        raise ValueError(f"清单名不合法: {list_id!r}")
    charts = _check_charts(charts)
    if event == "show_chart" and not charts:
        raise ValueError("show_chart 必须给图窗(symbol / start / end)")
    if event == "open_list" and not list_id:
        raise ValueError("open_list 必须给 list_id")
    if event in CHART_EVENTS:
        if not (isinstance(item_id, str) and item_id and list_id and len(charts) == 1):
            raise ValueError(f"{event} 必须给 list_id、item_id 和这张图的图窗")
    elif item_id is not None:
        raise ValueError("只有单张图事件才带 item_id")
    if event == "reveal":
        if not (isinstance(buy_points, list) and buy_points and all(
                isinstance(b, dict) and isinstance(b.get("date"), str) and _DATE_RE.match(b["date"])
                and isinstance(b.get("primary"), bool) for b in buy_points)):
            raise ValueError("reveal 必须带露出结果那一刻的买点 [{date, primary}]")
        buy_points = [{"date": b["date"], "primary": b["primary"]} for b in buy_points]
    elif buy_points is not None:
        raise ValueError("只有 reveal 才带买点")
    reason = str(outside_reason or "").strip()
    if surface == "chat":
        cfg = load_config()
        wins = [(c["symbol"], c["start"], c["end"]) for c in charts]
        wins += [(it.get("symbol"), it.get("view_start"), it.get("view_end"))
                 for it in (list_doc or {}).get("items") or [] if isinstance(it, dict)]
        bad = _outside(wins, cfg.get("view_floor"), str(cfg["train_end"]))
        if bad and not (allow_outside and reason):
            raise ValueError("聊天里贴的图越界:" + ";".join(bad[:5]) +
                             "。这张图本不该贴;确实要记(例如用户主动贴了旧图),加 --allow-outside 并用 "
                             "--reason 写明原因")
        if not bad:
            reason = ""
    root = state_root()
    sha, snap = None, None
    if list_doc is not None:
        sha, snap = _snapshot(root, list_id, list_doc)
    row = {"ts": ts or datetime.now().strftime("%Y-%m-%dT%H:%M:%S"), "surface": surface,
           "event": event, "list_id": list_id, "list_kind": list_kind,
           "outcome_visible": outcome_visible, "list_sha12": sha, "snapshot": snap,
           "charts": charts, "note": note, "backfill": bool(backfill)}
    if surface == "chat" and reason:
        row["outside_reason"] = reason
    if item_id is not None:
        row["item_id"] = item_id
    if buy_points is not None:
        row["buy_points"] = buy_points
    with (root / "views.jsonl").open("a") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    _state.advance(root)
    return row


def read_views() -> list[dict]:
    p = views_path()
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text().splitlines() if line.strip()]


def first_reveals(rows: list[dict] | None = None) -> dict[str, dict]:
    """每张图(item_id,跨清单)最早那次 reveal 行:{item_id: 行}。跨刷新、跨页面会话、跨天都算。
    rows:已读出的看过记录(省得重读)。"""
    out: dict[str, dict] = {}
    for r in read_views() if rows is None else rows:
        if r.get("event") != "reveal" or not r.get("item_id"):
            continue
        cur = out.get(r["item_id"])
        if cur is None or str(r.get("ts")) < str(cur.get("ts")):
            out[r["item_id"]] = r
    return out


def _t_of(item_id) -> str | None:
    m = re.fullmatch(r".+@(\d{4}-\d{2}-\d{2})", str(item_id or ""))
    return m.group(1) if m else None


def _pre_reveal_end(t: str, end: str) -> str:
    """大涨段露出结果前一张图最多露到哪天:决策日后 PRE_REVEAL_RIGHT_MAX 个工作日(节假日只会让真实那根更早)。"""
    import pandas as pd

    return min(str(end), (pd.Timestamp(t) + pd.offsets.BDay(PRE_REVEAL_RIGHT_MAX)).strftime("%Y-%m-%d"))


def _exposed(r: dict, reveals: dict, snap) -> list[tuple]:
    """一行看过记录露出了哪些 (条目, 代码, 起点, 终点)。大涨段清单里那时还没露出结果的图只露到决策日后几根;
    露出结果、往右拖看后续的那张图按整个图窗。"""
    big = r.get("list_kind") == "bigmoves"

    def cut(item_id, sym, start, end, t):
        rv = reveals.get(item_id)
        if big and t and not (rv and str(rv.get("ts")) <= str(r.get("ts"))):
            return item_id, sym, start, _pre_reveal_end(t, end)
        return item_id, sym, start, end

    out = []
    if r.get("snapshot"):
        for it in snap(r["snapshot"]).get("items") or []:
            out.append(cut(it.get("item_id"), it.get("symbol"), it.get("view_start"), it.get("view_end"),
                           it.get("t")))
    for c in r.get("charts") or []:
        if r.get("event") in ("reveal", "peek_chart"):
            out.append((r.get("item_id"), c["symbol"], c["start"], c["end"]))
        else:
            out.append(cut(r.get("item_id"), c["symbol"], c["start"], c["end"], _t_of(r.get("item_id"))))
    return out


def outcome_trail(item: dict, list_id: str, rows: list[dict] | None = None) -> dict:
    """大涨段清单里一条(item:清单里的这一条,要 item_id / symbol / t / view_end)的露出痕迹:
    {"first_reveal": 最早那次 reveal 行 | None,
     "peeked": 第一次露出结果前(没露出过 = 到现在)有没有往右拖看过后续(任何清单里的这一条),
     "seen_elsewhere": {"level": "careful | in_list" | None, "before": 截止时刻 | None,
                        "careful": [出处], "in_list": [出处]}}
    出处 = {"ts", "surface", "event", "list_id", "item_id"}。截止时刻 = 这张图第一次露出结果的时刻(同一秒的
    也算在前,保守);没露出过就是到现在。见模块说明。"""
    rows = read_views() if rows is None else rows
    reveals = first_reveals(rows)
    item_id, sym, t, end = item["item_id"], item["symbol"], str(item["t"]), str(item["view_end"])
    rv = reveals.get(item_id)
    before = str(rv["ts"]) if rv else None
    root = state_root()
    cache: dict[str, dict] = {}

    def snap(rel):
        if rel not in cache:
            try:
                cache[rel] = json.loads((root / rel).read_text())
            except (OSError, ValueError):
                cache[rel] = {}
        return cache[rel]

    peeked, careful, in_list = False, [], []
    for r in rows:
        if before is not None and str(r.get("ts")) > before:
            continue
        if r.get("item_id") == item_id:            # 这一条自己的单张图事件
            peeked = peeked or r.get("event") == "peek_chart"
            continue
        if not r.get("outcome_visible") or r.get("list_id") == list_id:     # 盲看;同一份清单只有左端残留
            continue
        big = r.get("list_kind") == "bigmoves"
        if not any(s == sym and str(a) <= end and str(b) > t and not (big and iid == item_id)
                   for iid, s, a, b in _exposed(r, reveals, snap)):
            continue
        ref = {k: r.get(k) for k in ("ts", "surface", "event", "list_id", "item_id")}
        if r.get("surface") in ("chat", "manual") or r.get("event") in CAREFUL_EVENTS:
            careful.append(ref)
        else:
            in_list.append(ref)
    level = "careful" if careful else "in_list" if in_list else None
    return {"first_reveal": rv, "peeked": peeked,
            "seen_elsewhere": {"level": level, "before": before, "careful": careful, "in_list": in_list}}


def viewed_set() -> set[tuple[str, str, str]]:
    """看过的 (symbol, view_start, view_end):open_list 行引用的清单快照里的全部条目,加 show_chart 的图窗。"""
    root = state_root()
    out: set[tuple[str, str, str]] = set()
    seen_snaps: set[str] = set()
    for r in read_views():
        for c in r.get("charts") or []:
            out.add((c["symbol"], c["start"], c["end"]))
        snap = r.get("snapshot")
        if snap and snap not in seen_snaps:
            seen_snaps.add(snap)
            try:
                doc = json.loads((root / snap).read_text())
            except (OSError, ValueError):
                continue
            for it in doc.get("items") or []:
                out.add((it.get("symbol"), it.get("view_start"), it.get("view_end")))
    return out


def _yes_no(s: str) -> bool:
    if s in ("yes", "true", "1"):
        return True
    if s in ("no", "false", "0"):
        return False
    raise argparse.ArgumentTypeError("只认 yes / no")


def _render(rows: list[dict], symbol: str | None) -> str:
    lines = []
    for r in rows:
        charts = r.get("charts") or []
        if symbol and not any(c["symbol"] == symbol for c in charts):
            snap = r.get("snapshot")
            hit = False
            if snap:
                try:
                    doc = json.loads((state_root() / snap).read_text())
                    hit = any(it.get("symbol") == symbol for it in doc.get("items") or [])
                except (OSError, ValueError):
                    pass
            if not hit:
                continue
        what = (f"清单 {r['list_id']}" if r["event"] == "open_list"
                else "、".join(f"{c['symbol']} {c['start']}→{c['end']}" for c in charts))
        if r["event"] != "open_list" and r.get("list_id"):
            what += f"(清单 {r['list_id']})"
        what = {"zoom_chart": "放大看了 ", "annotate_chart": "标注了 ",
                "reveal": "露出结果 "}.get(r["event"], "") + what
        if r.get("buy_points"):
            what += " 买点 " + "、".join(("★" if b["primary"] else "") + b["date"]
                                         for b in r["buy_points"])
        tags = [r["surface"], "看得到结果" if r["outcome_visible"] else "看不到结果"]
        if r.get("backfill"):
            tags.append("补记")
        if r.get("outside_reason"):
            tags.append(f"越界照记:{r['outside_reason']}")
        note = f" · {r['note']}" if r.get("note") else ""
        lines.append(f"{r['ts']}  {what}  [{' / '.join(tags)}]{note}")
    return "\n".join(lines) if lines else "(没有记录)"


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="看过记录")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("record", help="记一条看过(聊天里贴的图 / 补记历史接触)")
    a.add_argument("--surface", required=True, choices=("chat", "manual"))
    a.add_argument("--symbol")
    a.add_argument("--start")
    a.add_argument("--end")
    a.add_argument("--list-id")
    a.add_argument("--outcome-visible", required=True, type=_yes_no)
    a.add_argument("--note", default="")
    a.add_argument("--ts")
    a.add_argument("--backfill", action="store_true")
    a.add_argument("--allow-outside", action="store_true",
                   help="聊天里贴的图越过看图下界或训练段末日也照记(必须同时用 --reason 写原因)")
    a.add_argument("--reason", default="", help="--allow-outside 的原因")
    s = sub.add_parser("show")
    s.add_argument("--symbol")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "show":
            rows = read_views()
            print(_render(rows, args.symbol))
            print(f"\n共 {len(rows)} 条看过记录({views_path()})")
            return
        list_doc, list_kind = None, None
        if args.symbol:
            if not (args.start and args.end):
                raise ValueError("给了 --symbol 就要同时给 --start 和 --end")
            event, charts = "show_chart", [{"symbol": args.symbol, "start": args.start,
                                            "end": args.end}]
        else:
            if not args.list_id:
                raise ValueError("要么给 --symbol --start --end(一张图),要么给 --list-id(整份清单)")
            event, charts = "open_list", None
        if args.list_id:
            p = root_dir(load_config()) / "lists" / f"{args.list_id}.json"
            if _LIST_ID_RE.fullmatch(args.list_id) and p.exists():
                doc = json.loads(p.read_text())
                list_kind = doc.get("kind")
                list_doc = doc if event == "open_list" else None
        row = record(surface=args.surface, event=event, outcome_visible=args.outcome_visible,
                     list_id=args.list_id, list_kind=list_kind, list_doc=list_doc, charts=charts,
                     note=args.note, ts=args.ts, backfill=args.backfill,
                     allow_outside=args.allow_outside, outside_reason=args.reason)
    except (ValueError, StateRootMissing) as e:
        print(f"错误:{e}", file=sys.stderr)
        sys.exit(2)
    print(f"已记:{row['ts']} {row['event']} → {views_path()}")


if __name__ == "__main__":
    main()
