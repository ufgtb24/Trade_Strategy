"""看一段日期里 app 实际认出了什么(annotation-round skill 的只读工具)。

    uv run python .claude/skills/annotation-round/scripts/look.py <app> <股票> <起> <止>

回答三件事:
1. 这段日期里 app 买了哪几天,每个 hit 的各段起止(每个 node 绑定的事件及其子段);
2. 每条 where 在这些 hit 上的实测值与门槛;
3. 这段日期里没成买点的候选事件(参与求解的 node 上、终点落在这段日期里、没进任何 hit 的事件)卡在哪条
   where。一个候选都没有、或 where 全过却没凑成 hit 的,要查 detector 或边,本工具不管。
另附这几天的 K 线(默认往前多带 10 根,不往后带)。

还没有 app 时,app 那一格写 `-`:不跑任何 app,只出这段日期的 K 线(照标注做第一版 app 之前,看用户框的
那几段、放样本的那几天长什么样):

    uv run python .claude/skills/annotation-round/scripts/look.py - <股票> <起> <止> --before 30

口径
----
- 跑的是**现在工作区里的 app**、现在的默认参数文件(app 的 load_params);改完 app 再跑,看到的就是新版。
  旧版买点只在 round 文件里,本工具不读它。
- 区间与 compare 图上一致:全历史到训练段末日跑一次 app,再按日期筛出要看的那段。行情只经
  path2_web/app_run.py 的 run_app 读(它走 path2_web/data.py 的 read_bars,截到训练段末日)。
- 走势无关:不认任何具体 app、node、字段名。where 的规则与实测值按谓词自带的规则描述(path2/dag/where.py 的
  meta)逐层求值;裸 lambda 写的条件没有规则描述,只给得出过没过。
- 不写任何文件。

参数
----
- app:注册表里的 app 名(dag_spec 的 pattern_id);写 `-` 表示没有 app,只出 K 线;
- 股票、起、止:代码与 YYYY-MM-DD(含两端);
- --before N / --after N:K 线表往前、往后多带几根(默认 10 / 0);--no-bars:不出 K 线表;
- --fields:另列每个 hit 上各事件的全部标量字段(写新 where 之前,看事件上现成有哪些字段、这几天各是多少);
- --max-rows N:每张表最多列几行(默认 60,多了缩短日期范围再看);
- --apps-pkg:app 所在的包(默认 path2_apps;只给试跑用)。
"""
from __future__ import annotations

import argparse
import dataclasses
import sys
from pathlib import Path

import pandas as pd

_BASE_FIELDS = {"start_idx", "end_idx", "confirm_idx", "node_id", "instance_idx", "instance_id", "ref_ids"}


# ───────────────────────── 小工具 ─────────────────────────
def _fmt(v) -> str:
    """实测值、门槛的显示:浮点取 4 位有效数字,其余原样。"""
    if v is None:
        return "None"
    if isinstance(v, bool):
        return str(v).lower()
    if isinstance(v, float):
        return f"{v:.4g}"
    return str(v)


def _span(day: list, ev) -> str:
    """事件的起止日期(同一天只写一个)。"""
    a, b = day[ev.start_idx], day[ev.end_idx]
    return a if a == b else f"{a}～{b}"


def _table(head: list, rows: list) -> list:
    """Markdown 表。"""
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    return out + ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]


# ───────────────────────── where:按规则描述逐层求值 ─────────────────────────
def _leaves(meta, ev, prefix: str = "") -> list:
    """一条 where 的规则描述(谓词的 meta)在事件 ev 上逐层展开成叶子。

    返回 [(标签, 规则文字, 实测值文字, 过没过)];过没过为 None 表示这一片没有规则描述(裸 lambda、成员序列
    上的自定义聚合),给不出实测值。组合子(and / or / not)展开成它的各片,标签前带上组合方式。"""
    from path2.dag import where as W

    kind = (meta or {}).get("kind")
    if kind == "attr":
        field, op, thr = meta["field"], meta["op"], meta["threshold"]
        v = getattr(ev, field, None)
        return [(prefix + field, f"{op} {_fmt(thr)}", _fmt(v), bool(W.attr(field, op, thr)(ev)))]
    if kind == "child":
        key = meta["key"]
        if meta.get("inner") is None:
            return [(f"{prefix}{key}.(自定义)", "自定义判断", "—", None)]
        return _leaves(meta["inner"], ev.child(key), f"{prefix}{key}.")
    if kind == "children":
        return [(f"{prefix}{meta['key']}[](自定义聚合)", "自定义判断", "—", None)]
    if kind in ("and", "or", "not"):
        word = {"and": "", "or": "任一:", "not": "取反:"}[kind]
        out = []
        for sub in meta.get("children", ()):
            out += [(word + lab, rule, val, ok) for lab, rule, val, ok in _leaves(sub, ev, prefix)]
        return out
    return [(f"{prefix}(自定义)", "自定义判断", "—", None)]


def _where_columns(spec, node_ids) -> list:
    """这些 node 上全部 where 的叶子列:[(node_id, clause_id, 谓词)]。"""
    by = {n.node_id: n for n in spec.nodes}
    return [(nid, cid, fn) for nid in node_ids for cid, fn in by[nid].where]


def _where_cells(cols: list, events: dict) -> tuple[list, list]:
    """一行(一个 hit 或一个候选)在各 where 上的格子。events 是 {node_id: 事件}。

    返回 (表头, 格子):表头每列「node.条件名: 字段 规则」;格子是实测值,没过的后面带 ✗;整条没过而叶子里
    看不出是哪片时(自定义判断)写「✗」。"""
    head, cells = [], []
    for nid, cid, fn in cols:
        ev = events.get(nid)
        leaves = _leaves(getattr(fn, "meta", None), ev) if ev is not None else []
        passed = bool(fn(ev)) if ev is not None else None
        for lab, rule, val, ok in leaves or [("(没有这个 node 的事件)", "", "—", None)]:
            head.append(f"{nid}.{cid}: {lab} {rule}".strip())
            if ok is None:
                cells.append("—" if passed is None else ("过" if passed else "✗"))
            else:
                cells.append(val if ok else f"{val} ✗")
    return head, cells


# ───────────────────────── 段:node 绑定的事件及其子段 ─────────────────────────
def _segments(spec, day: list, events: dict) -> str:
    """一个 hit 里各 node 的事件起止,连同每个子段槽(槽名 → 子 node)。"""
    by = {n.node_id: n for n in spec.nodes}
    parts = []
    for nid, ev in events.items():
        text = f"{nid} {_span(day, ev)}"
        subs = []
        for slot, val in ev.child_slots().items():
            child_id = by[nid].children.get(slot, "?")
            name = slot if child_id == slot else f"{slot}→{child_id}"
            if isinstance(val, tuple):
                shown = "、".join(_span(day, c) for c in val[:6]) + ("…" if len(val) > 6 else "")
                subs.append(f"{name} {len(val)} 段({shown})")
            else:
                subs.append(f"{name} {_span(day, val)}")
        parts.append(text + (" [" + "; ".join(subs) + "]" if subs else ""))
    return " ／ ".join(parts)


def _scalar_fields(ev) -> dict:
    """事件上除基类字段外的全部标量字段(数字、字符串、布尔、None)。"""
    out = {}
    for f in dataclasses.fields(ev):
        if f.name in _BASE_FIELDS:
            continue
        v = getattr(ev, f.name)
        if v is None or isinstance(v, (int, float, str, bool)):
            out[f.name] = v
    return out


def _field_lines(day: list, events: dict) -> list:
    """--fields:每个事件及其单事件子段的标量字段,一行一个事件。"""
    lines = []
    for nid, ev in events.items():
        lines.append(f"  - {nid}:" + "、".join(f"{k}={_fmt(v)}" for k, v in _scalar_fields(ev).items()))
        for slot, val in ev.child_slots().items():
            for c in (val if isinstance(val, tuple) else (val,))[:6]:
                lines.append(f"    - {nid}.{slot}({_span(day, c)}):"
                             + "、".join(f"{k}={_fmt(v)}" for k, v in _scalar_fields(c).items()))
    return lines


# ───────────────────────── 主流程 ─────────────────────────
def look(app: str, symbol: str, start: str, end: str, *, before: int = 10, after: int = 0, bars: bool = True,
         fields: bool = False, max_rows: int = 60, apps_pkg: str = "path2_apps", cfg=None) -> str:
    """跑一次现在的 app,返回这段日期的 Markdown 说明(各节见模块说明)。

    参数:app 是注册表里的 app 名;symbol、start、end 是股票与日期(含两端);before / after 是 K 线表多带的
    根数,bars 为假时不出 K 线表;fields 为真时另列各事件的标量字段;max_rows 是每张表的行数上限;cfg 缺省读网页那份配置。
    app 不在注册表里 → SystemExit(带上没注册上的原因);读不到行情的异常原样抛出。
    """
    from path2.eval import _resolve_end_events
    from path2_web.annotation.revision import FIRST_DAY, LABEL_HORIZON
    from path2_web.app_run import app_buys, run_app, solving_nodes
    from path2_web.app_version import app_ver
    from path2_web.config import load_config
    from path2_web.data import TRAIN_END
    from path2_web.discovery import PatternRegistry

    cfg = load_config() if cfg is None else cfg
    reg = PatternRegistry(apps_pkg)
    mod = reg.get(app)
    if mod is None:
        raise SystemExit(f"注册表里没有 app {app!r};已注册: {reg.ids()};没注册上的: {reg.errors()}")
    load = getattr(mod, "load_params", None)
    params = load() if callable(load) else None
    res, win, meta = run_app(mod, cfg, symbol, FIRST_DAY, TRAIN_END, params, LABEL_HORIZON)
    spec, end_node = res.spec, meta["end_node"]
    day = pd.to_datetime(win["date"]).dt.strftime("%Y-%m-%d").tolist()
    buys = app_buys(res, win, end_node)

    def in_range(d: str) -> bool:
        return start <= d <= end

    out = [f"# {app} · {symbol} · {start}～{end}", "",
           f"- 跑的是现在工作区里的 app(版本指纹 {app_ver(mod)})和它现在的默认参数;买点 node:`{end_node}`",
           f"- 这只股票的行情:{day[0]}～{day[-1]}(截到训练段末日 {TRAIN_END})" if day else "- 这只股票没有行情",
           ""]

    # ── 买点:这段日期里有买点日的 hit ──
    hits = []
    for h in res.hits:
        days = sorted({day[i] for ev in _resolve_end_events(h, end_node)
                       for i in range(ev.start_idx, ev.end_idx + 1)})
        mine = [d for d in days if in_range(d)]
        if mine:
            hits.append((mine[0], day[h.start_idx], h, mine, days))
    hits.sort(key=lambda x: (x[0], x[1]))
    buy_days = sorted({d for _, _, _, mine, _ in hits for d in mine})
    families = sorted({fam for _, fam, _, _, _ in hits})
    out += ["## 买点", ""]
    if not hits:
        out += ["这段日期里 app 一天都没买。", ""]
    else:
        out += [f"这段日期里买了 {len(buy_days)} 天、{len(hits)} 个 hit,起点分属 {len(families)} 族"
                f"(族 = hit 起点相同的一组):{'、'.join(families)}。", "",
                "各段起止(每个 node 绑定的事件;方括号里是它的子段,`槽→子 node`):", ""]
        rows = [(_span_days(mine), fam, _segments(spec, day, dict(h.node_index)))
                for _, fam, h, mine, _ in hits[:max_rows]]
        out += _table(["买点日", "hit 起点", "各段"], rows)
        cols = _where_columns(spec, [n.node_id for n in spec.nodes if n.node_id in hits[0][2].node_index])
        if cols:
            out += ["", "每条 where 的实测值(表头是「node.条件名: 字段 规则」;买得成的 hit 每格都过):", ""]
            head = _where_cells(cols, dict(hits[0][2].node_index))[0]
            rows = [[_span_days(mine), *_where_cells(cols, dict(h.node_index))[1]] for _, _, h, mine, _ in hits[:max_rows]]
            out += _table(["买点日", *head], rows)
        else:
            out += ["", "这个 app 参与求解的 node 上没有 where。"]
        edges = [(k, w) for k, w in ((hits[0][2].predicate_trace.edge_results or {}).items()
                                     if hits[0][2].predicate_trace else [])]
        if edges:
            out += ["", "边的实测值(单位是 K 线根数):", ""]
            rows = []
            for _, _, h, mine, _ in hits[:max_rows]:
                er = h.predicate_trace.edge_results
                rows.append([_span_days(mine), *[f"{getattr(er[k].measured, 'label', '')} "
                                                 f"{_fmt(getattr(er[k].measured, 'value', None))}" for k, _ in edges]])
            out += _table(["买点日", *[f"{s}→{d}" for (s, d), _ in edges]], rows)
        if len(hits) > max_rows:
            out += ["", f"另有 {len(hits) - max_rows} 个 hit 没列出,缩短日期范围再看。"]
        if fields:
            out += ["", "各事件的标量字段(where 能直接读的):", ""]
            for _, _, h, mine, _ in hits[:max_rows]:
                out += [f"- {_span_days(mine)}", *_field_lines(day, dict(h.node_index))]
        out.append("")

    # ── 没成买点的候选:参与求解的 node 上、终点落在这段日期里、不在任何 hit 里的事件 ──
    bound = {id(e) for h in res.hits for e in (h.node_index or {}).values()}
    solving = solving_nodes(spec)
    by = {n.node_id: n for n in spec.nodes}
    cands = [e for e in res.events
             if e.node_id in solving and id(e) not in bound and e.node_id in by
             and in_range(day[e.end_idx])]
    cands.sort(key=lambda e: (day[e.end_idx], day[e.start_idx], e.node_id))
    out += ["## 没成买点的候选", ""]
    if not cands:
        out += ["参与求解的 node 上,没有别的事件在这段日期里结束:没买的那几天,detector 连候选都没切出来"
                "(要查 detector 为什么没切出来,本工具不管)。", ""]
    else:
        out += [f"参与求解的 node 上,另有 {len(cands)} 个事件在这段日期里结束、没进任何 hit。"
                "带 ✗ 的格是没过的条件;一行里没有 ✗ 的是 where 全过、却没凑成 hit(差的是边上的关系伙伴)。", ""]
        for nid in [n.node_id for n in spec.nodes if any(e.node_id == n.node_id for e in cands)]:
            mine = [e for e in cands if e.node_id == nid]
            cols = _where_columns(spec, [nid])
            out += [f"node `{nid}`({len(mine)} 个):", ""]
            if not cols:
                out += _table(["事件起止", "各段"], [(_span(day, e), _segments(spec, day, {nid: e}))
                                                     for e in mine[:max_rows]])
            else:
                head = _where_cells(cols, {nid: mine[0]})[0]
                out += _table(["事件起止", "各段", *head],
                              [[_span(day, e), _segments(spec, day, {nid: e}), *_where_cells(cols, {nid: e})[1]]
                               for e in mine[:max_rows]])
            if len(mine) > max_rows:
                out += ["", f"另有 {len(mine) - max_rows} 个没列出,缩短日期范围再看。"]
            if fields:
                out += ["", "标量字段:", ""]
                for e in mine[:max_rows]:
                    out += [f"- {_span(day, e)}", *_field_lines(day, {nid: e})]
            out.append("")

    # ── K 线 ──
    if bars:
        out += _bar_lines(win, day, start, end, before, after, set(buys.buy_days))
    return "\n".join(out) + "\n"


def _bar_lines(win, day: list, start: str, end: str, before: int, after: int, buy_days) -> list:
    """K 线表:[start, end] 里的每根,往前、往后各多带几根。buy_days 为 None 表示没有 app,不出「买」一栏。"""
    out = ["## K 线", ""]
    idx = [i for i, d in enumerate(day) if start <= d <= end]
    if not idx:
        return out + ["这段日期里没有交易日(或超出了这只股票的行情)。", ""]
    lo, hi = max(0, idx[0] - before), min(len(day) - 1, idx[-1] + after)
    vol_ma = win["volume"].rolling(20, min_periods=1).mean().shift(1)
    rows = []
    for i in range(lo, hi + 1):
        r = win.iloc[i]
        chg = "" if i == 0 else f"{(r['close'] / win['close'].iat[i - 1] - 1) * 100:+.1f}%"
        ratio = vol_ma.iat[i]
        vr = "" if not ratio or pd.isna(ratio) else f"{r['volume'] / ratio:.1f}"
        mark = ("▼" if buy_days and day[i] in buy_days else "") + ("" if start <= day[i] <= end else "(范围外)")
        rows.append((day[i], f"{r['open']:.4g}", f"{r['high']:.4g}", f"{r['low']:.4g}", f"{r['close']:.4g}",
                     chg, f"{r['volume']:.4g}", vr, mark))
    note = "「量比」= 当天成交量 ÷ 前 20 根的平均量。"
    out += [("▼ = 现在的 app 在这天买;" if buy_days is not None else "") + note, ""]
    return out + _table(["日期", "开", "高", "低", "收", "涨跌", "量", "量比", "买" if buy_days is not None else "备注"], rows)


def bars_only(symbol: str, start: str, end: str, *, before: int = 10, after: int = 0, cfg=None) -> str:
    """没有 app 时只看 K 线:经 path2_web/app_run.py 的 load_bars 读训练段副本(截到训练段末日),不跑任何 app。"""
    from path2_web.app_run import load_bars
    from path2_web.config import load_config
    from path2_web.data import TRAIN_END, slice_window

    cfg = load_config() if cfg is None else cfg
    win = slice_window(load_bars(cfg, symbol), "1900-01-01", TRAIN_END)
    day = pd.to_datetime(win["date"]).dt.strftime("%Y-%m-%d").tolist()
    out = [f"# {symbol} · {start}～{end}(只看 K 线,没有跑 app)", "",
           f"- 这只股票的行情:{day[0]}～{day[-1]}(截到训练段末日 {TRAIN_END})" if day else "- 这只股票没有行情", ""]
    return "\n".join(out + _bar_lines(win, day, start, end, before, after, None)) + "\n"


def _span_days(days: list) -> str:
    """一个 hit 在这段日期里的买点日:一天写一天,多天写首尾与天数。"""
    return days[0] if len(days) == 1 else f"{days[0]}～{days[-1]}({len(days)} 天)"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="看一段日期里 app 实际认出了什么(只读)")
    ap.add_argument("app", help="注册表里的 app 名;还没有 app 时写 - ,只出 K 线")
    ap.add_argument("symbol", help="股票代码")
    ap.add_argument("start", help="起(YYYY-MM-DD)")
    ap.add_argument("end", help="止(YYYY-MM-DD,含)")
    ap.add_argument("--before", type=int, default=10, help="K 线表往前多带几根(默认 10)")
    ap.add_argument("--after", type=int, default=0, help="K 线表往后多带几根(默认 0)")
    ap.add_argument("--no-bars", action="store_true", help="不出 K 线表")
    ap.add_argument("--fields", action="store_true", help="另列各事件的全部标量字段")
    ap.add_argument("--max-rows", type=int, default=60, help="每张表最多几行(默认 60)")
    ap.add_argument("--apps-pkg", default="path2_apps", help="app 所在的包(试跑用)")
    a = ap.parse_args(argv)
    if a.start > a.end:
        ap.error("起不能晚于止")
    root = Path(__file__).resolve().parents[4]
    if str(root) not in sys.path:      # 从仓库根以外的目录调起时也找得到 path2_web
        sys.path.insert(0, str(root))
    if a.app == "-":
        print(bars_only(a.symbol, a.start, a.end, before=a.before, after=a.after), end="")
        return 0
    print(look(a.app, a.symbol, a.start, a.end, before=a.before, after=a.after, bars=not a.no_bars, fields=a.fields,
               max_rows=a.max_rows, apps_pkg=a.apps_pkg), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
