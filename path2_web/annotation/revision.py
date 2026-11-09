"""会话侧的定格与改版报告:每改一版 app(或调一次参),报出这一版对反馈、买点、样本结论的影响
(spec 6.13「会话侧 · 改版报告」、6.14「会话每轮的固定动作」第 1～3 条、6.6「调参后的报告」)。

一轮的顺序(照做,次序不能换)
-----------------------------
① start_round(pattern, out_path):用**改之前**的 app 把要看的股票全跑一遍,连同上一轮的定格存进 round 文件
   (放 scratchpad,不入库);它打印一段新快照的 YAML——**立刻**把它写进 `path2_apps/<app>/mapping.yaml` 会话段的
   `snapshot`(只替换 snapshot,会话段的 conditions、tags 原样保留)。这一步就是「开头定格」:此后用户再改的
   标注归下一轮。
② 改 app(或调参)。
③ revision_report(pattern, round_path):用现在的 app 重跑同一批股票,和 round 文件求差,返回给用户看的
   Markdown 报告。

禁忌
----
- **不要用 `git stash` 回到旧版 app 去补旧买点**:主目录里用户没提交的改动会被一起收走。旧版买点只来自
  round 文件;round 文件丢了,这一版就没有对照,下一轮从头来。
- 一轮只调一次 start_round。新快照写进 mapping 之后再调,它会把这份新快照当成「上一轮」,这一轮用户改的标注
  就从报告里漏掉了(app 若已改过,存下的也不是旧版买点)。会话中途断掉时,mapping 里的新快照和 scratchpad 里的
  round 文件都还在,直接接着做 ②、③;为此 round 文件已存在时 start_round 拒绝覆盖。
- 本模块不写 mapping.yaml、不写标注:只打印要写的 YAML,写入由会话做。读标注只经 store.read_annotations,
  读 mapping 只经 mapping.read_mappings。

怎么调(会话用 uv run python -c)
-------------------------------
    uv run python -c "from path2_web.annotation.revision import start_round; start_round('new_step', '<scratchpad>/round.json')"
    # ……把打印的 snapshot 写进 mapping.yaml,再改 app……
    uv run python -c "from path2_web.annotation.revision import revision_report; print(revision_report('new_step', '<scratchpad>/round.json'))"

cfg 缺省读 path2_web.config.load_config()(会话是独立进程,读的就是网页那份配置);registry 缺省现建
path2_web.discovery.PatternRegistry()。两者都可传入(测试用)。

对照的口径
----------
- 旧 = 上一轮定格时的标注 × 改版前的买点;新 = 这一轮定格时的标注 × 改版后的买点。「定格时的标注」用
  read_annotations(as_of=定格的 seen) 截出(按机器 + 序号截;缺号之后已到的批次截掉,下一轮当新的再报,只多报
  不漏报)。没有上一轮定格(第一轮)时旧标注就是新标注,只比 app 的改动。
- 股票 = 旧标注 ∪ 新标注里这个 pattern 有样本或反馈的股票。每只都用全历史区间(1900-01-01 到训练段末日)、
  label_horizon 20 跑 app,与 compare 图上、反馈状态接口看到的买点一致(path2_web/app_run.py 的 app_buys)。
- 反馈只看用户自己挑的(来源 picked);盲看标记的回归等盲看实施时再加。
- 判法全部复用 path2_web/annotation/match.py:反馈状态 feedback_status、朱红 is_red、样本 match 用
  sample_match(按 K 线根数算距离);样本级的改动用 path2_web/annotation/changes.py 的 pattern_changes 取
  (与 GET /annotations/changes 同一个函数)。

报告的六节
----------
报告开头写 app 改没改、对照的是哪两份、没比的股票;mapping 会话段写坏时写一句「会话段读不到」(原因标签没读到,
朱红按没有标签算),否则 mapping 里的定格不是这一轮开头那份时提醒一句。
① 各条反馈的状态新旧对照(只列变了的),每条现在是 lost 的留一行待会话交代「改好了 / 认法变了」;
② 反馈范围里砍掉的买点日:只给个数;
③ 反馈范围外砍掉的、④ 新长出来的买点日:按族(hit 起点日期)折叠,每族一行「X 天剩 Y 天」「X 天变 Y 天」和一个
   落在 compare 的链接(链接日期取这一族第一个变了的买点日);两节合起来细看以 FOLD_LIMIT 族为限,按变化
   天数从大到小挑,其余给个数。砍掉的日子归它在改版前所在的族,新长的归改版后所在的族(某天同属两族时两族
   各记一次);
⑤ 样本结论(✓ = 正样本 matched、负样本 unmatched;✗ 相反)的翻转:只数新旧两边都有结论、✓ / ✗ 变了的样本,
   按原因拆——样本有样本级改动(改判、换样本日)的归「你改标注造成的」,其余归「app 改动造成的」;新放、挪进
   的样本没有旧结论,不算翻转,另起一行计数(✓ 几张、✗ 几张)并逐张列出;另点名经用户改动(新放、挪进、改判、
   换样本日)的正样本里,样本日正好落在 app 买点日上的,注明落在旧版、新版还是两版都有——旧版买点是用户改标注
   时页面上看得到的,要防的是照着它放样本;
⑥ 删掉、挪走的正样本全部列出(它们在新标注里没有结论,进不了⑤),点名其中旧版 app 原来就认不出的。
六节都没有东西时报告写「无变化」。调参后的报告(6.6)同样用这一对函数。

链接格式:`<前端地址>#symbol=<代码>&date=<YYYY-MM-DD>&pattern=<pattern 名>&mode=compare`,前端地址缺省
`http://localhost:<配置的 frontend_port>/`,值按查询串编码(前端用 URLSearchParams 解)。
"""
from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Optional
from urllib.parse import quote, urlencode

import yaml

from path2_web import mapping as mapping_mod
from path2_web.annotation import match
from path2_web.annotation.changes import pattern_changes
from path2_web.annotation.store import read_annotations
from path2_web.app_run import AppBuys, BarsUnavailable, app_buys, run_app
from path2_web.app_version import app_ver
from path2_web.config import DEFAULT_CONFIG, load_config
from path2_web.data import TRAIN_END

ROUND_FORMAT = "path2_web.revision_round/1"   # round 文件的格式标记
FIRST_DAY = "1900-01-01"   # 全历史区间的起点(同前端 stores/appLink.ts 调单股预览)
LABEL_HORIZON = 20         # 同上
FOLD_LIMIT = 12            # ③④ 合起来细看几族
NOTE_CHARS = 30            # 报告里反馈理由最多显示几个字

# 会改变样本 match 的样本级改动(pattern_changes 的 change 取值);只改 note、成员框的不算
_MATCH_CHANGES = frozenset({"added", "moved_in", "judgment", "date", "symbol"})
_JUDGMENT = {"pos": "正样本", "neg": "负样本"}


# ───────────────────────── 读 mapping、标注,跑 app ─────────────────────────
def _registry():
    """现建 app 注册表(会导入全部 app,所以只在需要时建)。"""
    from path2_web.discovery import PatternRegistry
    return PatternRegistry()


def _mapping_of(pattern: str, registry) -> tuple[dict, object]:
    """写了这个 pattern 的那个 mapping 及其 app 模块。没有或有几个 → ValueError。

    mapping 的 problem(features、notes 对不上 dag 等)不拦:改版途中 app 改了 node 名、mapping 还没跟上是常事,
    报告照出;两个 app 写了同一个 pattern 时分不清是哪个 app,拦。"""
    ms = [m for m in mapping_mod.read_mappings(registry) if m["pattern"] == pattern]
    if not ms:
        raise ValueError(f"没有哪个 app 的 mapping.yaml 写了 pattern {pattern!r}")
    if len(ms) > 1:
        raise ValueError(f"pattern {pattern!r} 被几个 app 的 mapping 写了: {', '.join(m['app'] for m in ms)}")
    return ms[0], registry.get(ms[0]["app"])


def _pattern_objects(state: Mapping, pattern: str) -> tuple[dict, dict]:
    """状态里这个 pattern 的样本、反馈(全部来源),按编号:({id: 样本}, {id: 反馈}),都带上所在股票 symbol。"""
    samples, feedback = {}, {}
    for c in state["charts"]:
        for s in c["samples"]:
            if s["pattern"] == pattern:
                samples[s["id"]] = {**s, "symbol": c["symbol"]}
        for f in c.get("feedback", []):
            if f["pattern"] == pattern:
                feedback[f["id"]] = {**f, "symbol": c["symbol"]}
    return samples, feedback


def _symbols(*groups: Mapping) -> set:
    return {o["symbol"] for g in groups for o in g.values()}


def _run_all(mod, cfg: dict, symbols) -> tuple[dict, dict]:
    """当前 app 逐只跑一遍:({股票: AppBuys}, {读不到行情的股票: 原因})。区间与 compare 的图一致。"""
    load = getattr(mod, "load_params", None)
    params = load() if callable(load) and symbols else None
    buys, missing = {}, {}
    for sym in sorted(symbols):
        try:
            res, win, meta = run_app(mod, cfg, sym, FIRST_DAY, TRAIN_END, params, LABEL_HORIZON)
        except BarsUnavailable as e:
            missing[sym] = str(e)
            continue
        buys[sym] = app_buys(res, win, meta["end_node"])
    return buys, missing


# ───────────────────────── ① 开头定格 ─────────────────────────
def start_round(pattern: str, out_path, *, cfg: Optional[dict] = None, registry=None) -> dict:
    """一轮开头:定格 + 用改之前的 app 存下旧买点。

    参数:pattern 是标注里的 pattern 名;out_path 是 round 文件(JSON,放 scratchpad;已存在 → FileExistsError);
    cfg、registry 缺省见模块说明。

    做的事:
    1. 由 mapping 找到 app,把 mapping 会话段里现有的 snapshot 抄下来记作 prev(没有为 None;会话段写坏了
       → ValueError,先修好再来,否则分不清上一轮定在哪);
    2. 读当前标注,新快照 = {seen: {机器: 从 1 起连续到齐的序号}, samples: 这个 pattern 的样本编号(按 seen
       截出的状态), at: 今天};
    3. 股票 = prev 时的状态 ∪ 新快照时的状态里这个 pattern 有样本或反馈的股票,当前 app 逐只跑出买点;
    4. 写 round 文件 {format, pattern, app_id, app_ver, prev, snapshot, buys: {股票: AppBuys}, unavailable:
       {读不到行情的股票: 原因}},打印要写进 mapping 的新快照 YAML。
    返回写进 round 文件的那个字典。
    """
    cfg = load_config() if cfg is None else cfg
    registry = _registry() if registry is None else registry
    out = Path(out_path)
    if out.exists():
        raise FileExistsError(
            f"round 文件已存在: {out}。一轮只调一次 start_round;中途断掉就直接用它接着改 app、出报告,"
            "真要重开一轮先确认 mapping 里的 snapshot 还是上一轮的,再换个文件名")
    m, mod = _mapping_of(pattern, registry)
    if m["session_problem"] is not None:
        raise ValueError(f"app {m['app']} 的 mapping 会话段写坏了,先修好: {m['session_problem']}")
    prev = (m["session"] or {}).get("snapshot")
    prev = json.loads(json.dumps(prev)) if prev else None

    seen = {k: v["through"] for k, v in read_annotations(cfg)["machines"].items()}
    samples, feedback = _pattern_objects(read_annotations(cfg, as_of=seen)["state"], pattern)
    symbols = _symbols(samples, feedback)
    if prev is not None:
        symbols |= _symbols(*_pattern_objects(read_annotations(cfg, as_of=prev["seen"])["state"], pattern))
    snapshot = {"seen": seen, "samples": sorted(samples), "at": dt.date.today().isoformat()}

    buys, missing = _run_all(mod, cfg, symbols)
    rnd = {"format": ROUND_FORMAT, "pattern": pattern, "app_id": m["app"], "app_ver": app_ver(mod),
           "prev": prev, "snapshot": snapshot,
           "buys": {s: b.to_dict() for s, b in buys.items()}, "unavailable": missing}
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "x", encoding="utf-8") as f:
        f.write(json.dumps(rnd, ensure_ascii=False, indent=1) + "\n")

    print(f"# round 文件: {out}(股票 {len(symbols)} 只,读不到行情 {len(missing)} 只)")
    print(f"# 立刻写进 {mapping_mod.mapping_path(mod)}:只替换 session 下的 snapshot,conditions、tags 原样保留")
    print(yaml.safe_dump({"session": {"snapshot": snapshot}}, allow_unicode=True, sort_keys=False,
                         default_flow_style=None), end="")
    return rnd


# ───────────────────────── ③ 改版报告 ─────────────────────────
@dataclass
class _Ctx:
    """出报告要用的全部输入(旧 / 新各一份)。"""
    pattern: str
    link_base: str
    old_buys: dict             # {股票: AppBuys},改版前
    new_buys: dict             # {股票: AppBuys},改版后
    s_old: dict                # 旧标注里这个 pattern 的样本
    s_new: dict
    f_old: dict                # 旧标注里这个 pattern 的反馈(只 picked)
    f_new: dict
    state_new: Mapping         # 新标注的整个状态(查挪走的样本挪到了哪)
    tags: dict                 # mapping 会话段的原因标签
    ann_changes: dict = field(default_factory=dict)   # {样本编号: 会改变 match 的样本级改动}

    def link(self, symbol: str, date: str) -> str:
        q = urlencode({"symbol": symbol, "date": date, "pattern": self.pattern, "mode": "compare"}, quote_via=quote)
        return f"{self.link_base}#{q}"


def _span(start: str, end: str) -> str:
    return start if start == end else f"{start}～{end}"


def _short(text: Optional[str]) -> str:
    """反馈理由的前几个字(用户写的内容,原样只去换行)。"""
    t = " ".join((text or "").split())
    return t if len(t) <= NOTE_CHARS else t[:NOTE_CHARS] + "…"


def _fb_label(ctx: _Ctx, fb: Mapping) -> str:
    """一条反馈的显示:链接(股票 + 日期范围,落在 start)、答案、理由或分段、编号。"""
    what = f"「{_short(fb['note'])}」" if fb.get("note") else \
        f"（分段 {', '.join(fb['segments'])}）" if fb.get("segments") else ""
    return (f"[{fb['symbol']} {_span(fb['start'], fb['end'])}]({ctx.link(fb['symbol'], fb['start'])}) "
            f"`{fb['answer']}`{what}（{fb['id']}）")


def _fb_status(fb: Optional[Mapping], buys: Mapping) -> str:
    """反馈在一组买点下的状态;没有这条 → 'absent';这只股票读不到行情 → 'na'。"""
    if fb is None:
        return "absent"
    b = buys.get(fb["symbol"])
    return "na" if b is None else match.feedback_status(fb, b)


def _status_text(s: str) -> str:
    return {"absent": "（没有这条）", "na": "（读不到行情）"}.get(s, f"`{s}`")


def _lost_lines(ctx: _Ctx, now: Mapping) -> list[str]:
    """现在是 lost 的反馈,每条留一行待会话交代。now 是 {反馈编号: 现在的状态}。"""
    lost = [fid for fid, s in now.items() if s == "lost"]
    if not lost:
        return []
    return ["`lost` 的反馈（起点认不出），每条请交代一句是改好了、还是认法变了：",
            *[f"- {_fb_label(ctx, ctx.f_new[fid])}：（待填：改好了 / 认法变了）" for fid in lost], ""]


def _fb_order(ctx: _Ctx, fid: str) -> tuple:
    f = ctx.f_new.get(fid) or ctx.f_old[fid]
    return f["symbol"], f["start"], f["end"], fid


def _section_feedback(ctx: _Ctx) -> tuple[list[str], bool, dict]:
    """① 反馈的状态。返回 (行, 有没有变化, {反馈编号: 现在的状态})。"""
    lines = ["## ① 反馈的状态", ""]
    ids = sorted(ctx.f_old.keys() | ctx.f_new.keys(), key=lambda i: _fb_order(ctx, i))
    now = {fid: _fb_status(ctx.f_new[fid], ctx.new_buys) for fid in ids if fid in ctx.f_new}
    if not ids:
        return lines + ["这个 pattern 还没有反馈。", ""], False, now
    changed = []
    for fid in ids:
        old = _fb_status(ctx.f_old.get(fid), ctx.old_buys)
        new = now.get(fid, "absent")
        if old != new:
            fb = ctx.f_new.get(fid) or ctx.f_old[fid]
            changed.append(f"- {_fb_label(ctx, fb)}：{_status_text(old)} → {_status_text(new)}")
    rest = len(ids) - len(changed)
    lines += (changed + (["", f"其余 {rest} 条没变。"] if rest else [])) if changed else ["状态都没变。"]
    lines += ["", _now_summary(ctx, now), ""]
    return lines + _lost_lines(ctx, now), bool(changed), now


def _now_summary(ctx: _Ctx, now: Mapping) -> str:
    """现在各状态几条(朱红按会话的原因标签判,见 match.is_red)。"""
    red = sum(match.is_red(s, ctx.tags.get(i)) for i, s in now.items())
    n = {k: sum(s == k for s in now.values()) for k in ("lost", "unmatched", "na")}
    text = f"现在 {len(now)} 条反馈：朱红 {red} 条、`lost` {n['lost']} 条、`unmatched` {n['unmatched']} 条"
    return text + (f"、读不到行情 {n['na']} 条。" if n["na"] else "。")


@dataclass(frozen=True)
class _Fold:
    """③④ 里的一族:kind 'cut'(范围外砍掉)/ 'grown'(新长出来)。"""
    kind: str
    symbol: str
    start: str        # 族的起点(hit 起点日期)
    before: int       # 改版前这一族(或这些日子)有几天买点
    after: int        # 改版后剩几天 / 变成几天
    changed: int      # 这一族里砍掉(范围外)/ 新长的天数
    first: str        # 第一个变了的买点日(链接落在这天)
    in_range: int = 0  # cut 时:这一族另有几天砍在反馈范围里

    def sort_key(self):
        return (-self.changed, self.symbol, self.start, self.kind)


def _day_changes(ctx: _Ctx) -> tuple[int, list[_Fold]]:
    """② 反馈范围里砍掉的买点日数;③④ 按族折叠的条目。两边都跑出了买点的股票才比。"""
    in_range_total, folds = 0, []
    fbs = [*ctx.f_old.values(), *ctx.f_new.values()]
    for sym in sorted(ctx.old_buys.keys() & ctx.new_buys.keys()):
        ob, nb = ctx.old_buys[sym], ctx.new_buys[sym]
        old_days, new_days = set(ob.buy_days), set(nb.buy_days)
        ranges = [(f["start"], f["end"]) for f in fbs if f["symbol"] == sym]
        cut = old_days - new_days
        cut_in = {d for d in cut if any(s <= d <= e for s, e in ranges)}
        cut_out, grown = cut - cut_in, new_days - old_days
        in_range_total += len(cut_in)
        for start, days in ob.families.items():
            c = set(days) & cut_out
            if c:
                folds.append(_Fold("cut", sym, start, len(days), len(set(days) - cut), len(c), min(c),
                                   len(set(days) & cut_in)))
        for start, days in nb.families.items():
            g = set(days) & grown
            if g:
                folds.append(_Fold("grown", sym, start, len(set(days) - grown), len(days), len(g), min(g)))
    return in_range_total, folds


def _section_days(ctx: _Ctx) -> tuple[list[str], bool]:
    """②③④。返回 (行, 有没有变化)。"""
    in_range, folds = _day_changes(ctx)
    picked = set(sorted(folds, key=_Fold.sort_key)[:FOLD_LIMIT])
    lines = ["## ② 反馈范围里砍掉的买点", "",
             f"共 {in_range} 天。" if in_range else "没有。", ""]
    for kind, title in (("cut", "## ③ 反馈范围外砍掉的买点（按族）"), ("grown", "## ④ 新长出来的买点（按族）")):
        mine = sorted((f for f in folds if f.kind == kind), key=_Fold.sort_key)
        lines += [title, ""]
        if not mine:
            lines += ["没有。", ""]
            continue
        lines.append(f"共 {sum(f.changed for f in mine)} 天、{len(mine)} 族。")
        for f in mine:
            if f not in picked:
                continue
            head = f"- [{f.symbol} {f.start} 起的一族]({ctx.link(f.symbol, f.first)})"
            if kind == "cut":
                extra = f"，另有 {f.in_range} 天砍在反馈范围里" if f.in_range else ""
                lines.append(f"{head}：{f.before} 天剩 {f.after} 天{extra}")
            else:
                lines.append(f"{head}：新长出的一族，{f.after} 天" if f.before == 0 else
                             f"{head}：{f.before} 天变 {f.after} 天")
        rest = [f for f in mine if f not in picked]
        if rest:
            lines.append(f"- 另有 {len(rest)} 族（共 {sum(f.changed for f in rest)} 天）没列出。")
        lines.append("")
    return lines, bool(in_range or folds)


def _verdict(s: Mapping, buys: Mapping) -> Optional[tuple[str, bool]]:
    """样本在一组买点下的结论 (match, 一致与否);这只股票读不到行情 → None。"""
    b = buys.get(s["symbol"])
    if b is None:
        return None
    m = match.sample_match(s["date"], s["judgment"], b.buy_days, b.dates)
    return m, (m == "matched") == (s["judgment"] == "pos")


def _mark(v: tuple[str, bool]) -> str:
    return "✓" if v[1] else "✗"


def _sample_label(ctx: _Ctx, s: Mapping) -> str:
    return f"[{s['symbol']} {s['date']}]({ctx.link(s['symbol'], s['date'])}) {_JUDGMENT[s['judgment']]}（{s['id']}）"


def _why(ctx: _Ctx, sid: str) -> str:
    """样本级改动的说法。"""
    ch, old, new = ctx.ann_changes[sid], ctx.s_old.get(sid), ctx.s_new[sid]
    parts = []
    if "added" in ch:
        parts.append("新放")
    if "moved_in" in ch:
        parts.append("挪进这个 pattern")
    if "judgment" in ch and old is not None:
        parts.append(f"改判：{_JUDGMENT[old['judgment']]} → {_JUDGMENT[new['judgment']]}")
    if "date" in ch and old is not None:
        parts.append(f"换样本日：{old['date']} → {new['date']}")
    if "symbol" in ch and old is not None:
        parts.append(f"换股票：{old['symbol']} → {new['symbol']}")
    return "；".join(parts)


def _on_buy_day(ctx: _Ctx, s: Mapping) -> Optional[str]:
    """样本日落在哪一版 app 的买点日上:'旧版' / '新版' / '两版';都不在 → None。"""
    old, new = ctx.old_buys.get(s["symbol"]), ctx.new_buys.get(s["symbol"])
    on_old = old is not None and s["date"] in old.buy_days
    on_new = new is not None and s["date"] in new.buy_days
    return "两版" if on_old and on_new else "旧版" if on_old else "新版" if on_new else None


def _section_flips(ctx: _Ctx) -> tuple[list[str], bool, int]:
    """⑤ 样本结论的翻转。返回 (行, 有没有变化, 读不到行情没比的样本数)。

    翻转只数新旧两边都有结论的样本;新放、挪进的没有旧结论,另起一行计数;删掉、挪走的进 ⑥。"""
    app_worse, app_better, by_you, fresh, named, na = [], [], [], [], [], 0
    fresh_ok = 0
    for sid in sorted(ctx.s_new, key=lambda i: (ctx.s_new[i]["symbol"], ctx.s_new[i]["date"], i)):
        s = ctx.s_new[sid]
        if sid in ctx.ann_changes and s["judgment"] == "pos":
            where = _on_buy_day(ctx, s)
            if where is not None:
                named.append(f"- {_sample_label(ctx, s)}（{_why(ctx, sid)}）：落在{where}的买点日上")
        new = _verdict(s, ctx.new_buys)
        old = _verdict(ctx.s_old[sid], ctx.old_buys) if sid in ctx.s_old else None
        if new is None or (sid in ctx.s_old and old is None):
            na += 1
            continue
        if sid not in ctx.s_old:   # 新放、挪进:没有旧结论
            fresh.append(f"- {_sample_label(ctx, s)}（{_why(ctx, sid)}）：{_mark(new)}（`{new[0]}`）")
            fresh_ok += new[1]
        elif old[1] == new[1]:
            continue
        elif sid in ctx.ann_changes:
            by_you.append(f"- {_sample_label(ctx, s)}（{_why(ctx, sid)}）：{_mark(old)} → {_mark(new)}"
                          f"（`{old[0]}` → `{new[0]}`）")
        else:
            row = f"- {_sample_label(ctx, s)}：{_mark(old)} → {_mark(new)}（`{old[0]}` → `{new[0]}`）"
            (app_worse if old[1] else app_better).append(row)
    n_app, n_you = len(app_worse) + len(app_better), len(by_you)
    lines = ["## ⑤ 样本结论的翻转", ""]
    if n_app + n_you == 0:
        lines += ["没有翻转。", ""]
    else:
        lines += [f"翻了 {n_app + n_you} 张：app 改的 {n_app}、你改标注的 {n_you}。", ""]
        if n_app:
            lines.append("app 改动造成的：")
            if app_worse:
                lines += ["", "变坏（✓ → ✗）：", *app_worse]
            if app_better:
                lines += ["", "变好（✗ → ✓）：", *app_better]
            lines.append("")
        if n_you:
            lines += ["你改标注造成的：", *by_you, ""]
    if fresh:
        lines += [f"新放 / 挪进 {len(fresh)} 张：✓ {fresh_ok}、✗ {len(fresh) - fresh_ok}（没有旧结论，不算翻转）。",
                  *fresh, ""]
    if named:
        lines += ["你新放或改过的正样本里，样本日正好是 app 买点日的（旧版买点是改版前页面上看得到的）：", *named, ""]
    return lines, bool(n_app + n_you or fresh or named), na


def _section_removed(ctx: _Ctx) -> tuple[list[str], bool]:
    """⑥ 删掉、挪走的正样本。返回 (行, 有没有变化)。"""
    where_now = {s["id"]: s["pattern"] for c in ctx.state_new["charts"] for s in c["samples"]}
    gone = [ctx.s_old[i] for i in sorted(ctx.s_old.keys() - ctx.s_new.keys(),
                                         key=lambda i: (ctx.s_old[i]["symbol"], ctx.s_old[i]["date"], i))]
    pos = [s for s in gone if s["judgment"] == "pos"]
    n_neg = len(gone) - len(pos)
    lines = ["## ⑥ 删掉、挪走的正样本", ""]
    if not pos:
        lines.append("没有。")
    for s in pos:
        if s["id"] not in where_now:
            how = "删掉了"
        elif where_now[s["id"]] is None:
            how = "挪回 unsorted"
        else:
            how = f"挪到 {where_now[s['id']]}"
        v = _verdict(s, ctx.old_buys)
        if v is None:
            was = "旧版读不到行情"
        elif v[0] == "unmatched":
            was = "**旧版 app 原来就认不出**（`unmatched`）"
        else:
            was = "旧版 ✓"
        lines.append(f"- {_sample_label(ctx, s)}：{how}；{was}")
    if n_neg:
        lines.append(f"另有删掉、挪走的负样本 {n_neg} 张。")
    return lines + [""], bool(gone)


def revision_report(pattern: str, round_path, link_base: Optional[str] = None, *,
                    cfg: Optional[dict] = None, registry=None) -> str:
    """一轮结尾:用现在的 app 重跑,和 round 文件求差,返回给用户看的 Markdown 报告(六节见模块说明)。

    参数:pattern 是标注里的 pattern 名(须与 round 文件一致);round_path 是 start_round 写的文件;link_base
    是落在 compare 的链接前缀,缺省 `http://localhost:<配置的 frontend_port>/`;cfg、registry 缺省见模块说明。

    旧标注 = read_annotations(as_of=round 文件里的 prev.seen)(prev 为空就等于新标注);新标注 =
    read_annotations(as_of=round 文件里新快照的 seen);旧买点 = round 文件;新买点 = 现在重跑。
    mapping 会话段里的 snapshot 不是 round 文件里那份新快照时,报告开头提醒一句(没写进去,下一轮会重报);
    会话段写坏了(读不到)时改写一句「会话段读不到」,不再提醒定格,原因标签当作没有。
    """
    cfg = load_config() if cfg is None else cfg
    registry = _registry() if registry is None else registry
    rnd = json.loads(Path(round_path).read_text(encoding="utf-8"))
    if rnd.get("format") != ROUND_FORMAT:
        raise ValueError(f"不是 start_round 写的 round 文件: {round_path}")
    if rnd["pattern"] != pattern:
        raise ValueError(f"round 文件是 pattern {rnd['pattern']!r} 的,不是 {pattern!r}")
    if link_base is None:
        link_base = f"http://localhost:{cfg.get('frontend_port', DEFAULT_CONFIG['frontend_port'])}/"
    m, mod = _mapping_of(pattern, registry)
    prev, snap = rnd["prev"], rnd["snapshot"]

    state_new = read_annotations(cfg, as_of=snap["seen"])["state"]
    state_old = read_annotations(cfg, as_of=prev["seen"])["state"] if prev else state_new
    s_old, f_old = _pattern_objects(state_old, pattern)
    s_new, f_new = _pattern_objects(state_new, pattern)
    old_buys = {s: AppBuys.from_dict(d) for s, d in rnd["buys"].items()}
    ran_before = set(old_buys) | set(rnd["unavailable"])
    symbols = ran_before | _symbols(s_old, f_old, s_new, f_new)
    new_buys, new_missing = _run_all(mod, cfg, symbols)

    changes: dict = {}
    for c in pattern_changes(state_old, state_new, pattern):
        if c["kind"] == "sample" and c["change"] in _MATCH_CHANGES:
            changes.setdefault(c["id"], set()).add(c["change"])
    session = m["session"] or {}
    ctx = _Ctx(pattern=pattern, link_base=link_base, old_buys=old_buys, new_buys=new_buys,
               s_old=s_old, s_new=s_new,
               f_old={i: f for i, f in f_old.items() if f["source"] == "picked"},
               f_new={i: f for i, f in f_new.items() if f["source"] == "picked"},
               state_new=state_new, tags=dict(session.get("tags") or {}), ann_changes=changes)

    fb_lines, fb_changed, now = _section_feedback(ctx)
    day_lines, days_changed = _section_days(ctx)
    flip_lines, flipped, n_na = _section_flips(ctx)
    gone_lines, gone = _section_removed(ctx)

    # ── 报告头 ──
    head = [f"# {pattern} 改版报告", ""]
    if m["app"] != rnd["app_id"]:
        head.append(f"- app：由 {rnd['app_id']} 换成了 {m['app']}")
    else:
        same = "没改" if app_ver(mod) == rnd["app_ver"] else "改过"
        head.append(f"- app：{m['app']}（这个 app 自己的代码和默认参数{same}）")
    if prev:
        head.append(f"- 对照：上一轮定格时的标注配改版前的买点，对这一轮定格时的标注配改版后的买点；"
                    f"共 {len(symbols)} 只股票")
    else:
        head.append(f"- 对照：第一轮，没有上一轮的定格，两边用同一份标注，只比 app 的改动；共 {len(symbols)} 只股票")
    missing = sorted(set(rnd["unavailable"]) | set(new_missing))
    not_run = sorted(symbols - ran_before - set(missing))   # 开头没跑过的(按理不会有:两次读的是同一份定格)
    if missing:
        head.append(f"- 读不到行情、没比的股票：{'、'.join(missing)}")
    if not_run:
        head.append(f"- 开头没跑、没有旧买点的股票：{'、'.join(not_run)}")
    if n_na:
        head.append(f"- 因此没比的样本 {n_na} 张")
    written = session.get("snapshot") or {}
    if m["session_problem"] is not None:
        head.append(f"- 会话段读不到（原因：{m['session_problem']}），原因标签没读到，朱红按没有标签算")
    elif (written.get("seen"), written.get("samples")) != (snap["seen"], snap["samples"]):
        head.append(f"- 注意：{m['app']} 的 mapping.yaml 里的定格不是这一轮开头那份；没写进去的话先写上，"
                    "否则下一轮会把这一轮的标注改动再报一遍")
    head.append("")

    if not (fb_changed or days_changed or flipped or gone):
        body = ["**无变化**：反馈的状态、买点日、样本结论都和改版前一样。", "",
                f"样本 {len(s_new)} 张。" + (_now_summary(ctx, now) if now else "这个 pattern 还没有反馈。"), ""]
        return "\n".join(head + body + _lost_lines(ctx, now))
    return "\n".join(head + fb_lines + day_lines + flip_lines + gone_lines)
