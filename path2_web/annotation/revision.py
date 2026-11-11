"""会话侧一轮的三个函数:开头定格(start_round)、读齐这一轮的输入(round_digest)、改完之后的改版报告
(revision_report)——每改一版 app(或调一次参),报出这一版对反馈、买点、样本结论的影响
(spec 6.13「会话侧 · 改版报告」、6.14「会话每轮的固定动作」、6.6「调参后的报告」)。

一轮的顺序(照做,次序不能换)
-----------------------------
① start_round(pattern, out_path):用**改之前**的 app 把要看的股票全跑一遍,连同上一轮的定格存进 round 文件;
   它打印一段新快照的 YAML——**立刻**把它写进 `path2_apps/<app>/mapping.yaml` 会话段的 `snapshot`(只替换
   snapshot,会话段的 conditions、tags 原样保留;mapping 还没有会话段就整段加进去)。这一步就是「开头定格」:
   此后用户再改的标注归下一轮。这个 pattern 还没有 app 时照常定格(不跑买点),快照等建好 app 和 mapping 再写。
② round_digest(pattern, round_path):这一轮要看的东西一次读齐(定义、mapping、账本、上一轮以来的变化、
   按 issue 分组的反馈、全部样本),返回给会话读的 Markdown。状态用 round 文件里改之前的买点算。
③ 改 app(或调参)。
④ revision_report(pattern, round_path):用现在的 app 重跑同一批股票,和 round 文件求差,返回给用户看的
   Markdown 报告。定格时还没有 app 的那一轮没有旧版可比,同一个函数改出「第一版」报告:用建好的 app 跑
   全部样本的股票,逐张给结论(一致 / 相反 / 没比)。

round 文件
----------
放 `outputs/annotation_rounds/<pattern 名>/<YYYY-MM-DD>-<n>.json`(`outputs/` 不入库;n 是当天第几轮,从 1 起)。
不放会话的 scratchpad:那里按会话隔离,会话断了新会话找不到,「中途断掉接着做」就落空。改版报告在会话记完账之后
由会话存成同名的 `.report.md`;**有 round 文件、没有同名报告 = 这一轮没走完**,新会话接着做、不再定格。
`outputs/` 各 worktree 不共用,一轮要在同一个工作目录里走完。

禁忌
----
- **不要用 `git stash` 回到旧版 app 去补旧买点**:主目录里用户没提交的改动会被一起收走。旧版买点只来自
  round 文件;round 文件丢了,这一版就没有对照,下一轮从头来。
- 一轮只调一次 start_round。新快照写进 mapping 之后再调,它会把这份新快照当成「上一轮」,这一轮用户改的标注
  就从报告里漏掉了(app 若已改过,存下的也不是旧版买点)。会话中途断掉时,mapping 里的新快照和 round 文件
  都还在,直接接着做后面几步;为此 round 文件已存在时 start_round 拒绝覆盖,同一个目录里这个 pattern 还有
  没走完的一轮(有 round 文件、没有同名 .report.md)时换个文件名也拒绝。
- 把有 app 的 pattern 当成「还没有 app」去定格,旧版买点就没存下、补不回。所以没有 app 的定格必须显式传
  no_app=True,并且分不清有没有 app 时(见 _ensure_no_app)照样拒绝。
- 本模块不写 mapping.yaml、不写标注、不存报告:只打印要写的 YAML、返回 Markdown,写入由会话做。读标注只经
  store.read_annotations,读 mapping 只经 mapping.read_mappings。

怎么调(会话用 uv run python -c;R 是上面说的 round 文件路径)
----------------------------------------------------------
    uv run python -c "from path2_web.annotation.revision import start_round; start_round('new_step', 'R')"
    # ……把打印的 snapshot 写进 mapping.yaml……
    uv run python -c "from path2_web.annotation.revision import round_digest; print(round_digest('new_step', 'R'))"
    # ……改 app……
    uv run python -c "from path2_web.annotation.revision import revision_report; print(revision_report('new_step', 'R'))"

cfg 缺省读 path2_web.config.load_config()(会话是独立进程,读的就是网页那份配置);registry 缺省现建
path2_web.discovery.PatternRegistry()。两者都可传入(测试用)。

对照的口径
----------
- 旧 = 上一轮定格时的标注 × 改版前的买点;新 = 这一轮定格时的标注 × 改版后的买点。「定格时的标注」用
  read_annotations(as_of=定格的 seen) 截出(按机器 + 序号截;缺号之后已到的批次截掉,下一轮当新的再报,只多报
  不漏报)。没有上一轮定格(第一轮)时旧标注就是新标注,只比 app 的改动。
- 股票 = 旧标注 ∪ 新标注里这个 pattern 有样本或反馈的股票。每只都用全历史区间(1900-01-01 到训练段末日)、
  label_horizon 20 跑 app,与 compare 图上、反馈状态接口看到的买点一致(path2_web/app_run.py 的 app_buys)。
- 反馈只看用户自己挑的(来源 picked);盲看标记的回归等盲看实施时再加。一条反馈的内容是 note 加 nodes;
  记录里若还带着 answer、dag(store 模块说明「反馈」),报告和摘要都不输出、不拿来分类。
- issue:带同一个 issue 值的几处反馈是一个 issue,不带的各自一个(用反馈编号当名字)。
- 判法全部复用 path2_web/annotation/match.py:反馈状态 feedback_status、朱红 is_red、样本 match 用
  sample_match(按 K 线根数算距离);样本级的改动用 path2_web/annotation/changes.py 的 pattern_changes 取
  (与 GET /annotations/changes 同一个函数)。

报告的六节
----------
报告开头写 app 改没改、对照的是哪两份、没比的股票;mapping 会话段写坏时写一句「会话段读不到」(原因标签没读到,
朱红按没有标签算),否则 mapping 里的定格不是这一轮开头那份时提醒一句。
① 各条反馈的状态新旧对照(只列变了的;一条写成「链接（落在 node）「理由前几个字」（编号，issue 值）」,没点
   node、没写理由的那一段就没有);随后「各 issue 现在」:有一处还在买、有一处 lost、或这一版有一处状态变了的
   issue 各一行(标了几处、还在买几处、lost 几处、这一版变了几处),其余只给个数。「变了」= 旧状态 ≠ 新状态,
   上一轮没有、这一轮新标的那处也算;这一轮删掉的反馈不属于任何 issue,只在逐条那一段出现。每条现在是 lost 的
   留一行待会话交代「改好了 / 认法变了」;
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
第一版报告(定格时还没有 app)没有这六节:只有一节「样本结论」,三个张数,相反的、没比的、一致的逐张列出。

链接格式:`<前端地址>#symbol=<代码>&date=<YYYY-MM-DD>&pattern=<pattern 名>&mode=compare`,前端地址缺省
`http://localhost:<配置的 frontend_port>/`,值按查询串编码(前端用 URLSearchParams 解)。
"""
from __future__ import annotations

import datetime as dt
import importlib
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


def _find_mapping(pattern: str, registry) -> Optional[tuple[dict, object]]:
    """写了这个 pattern 的那个 mapping 及其 app 模块;没有哪个 app 写它 → None(这个 pattern 还没有 app);
    有几个 → ValueError(分不清是哪个 app)。

    mapping 的 problem(features、notes 对不上 dag 等)不拦:改版途中 app 改了 node 名、mapping 还没跟上是常事。"""
    ms = [m for m in mapping_mod.read_mappings(registry) if m["pattern"] == pattern]
    if not ms:
        return None
    if len(ms) > 1:
        raise ValueError(f"pattern {pattern!r} 被几个 app 的 mapping 写了: {', '.join(m['app'] for m in ms)}")
    return ms[0], registry.get(ms[0]["app"])


def _unregistered_mapping_files(registry) -> list[tuple[str, Path]]:
    """磁盘上不属于任何已注册 app 的 mapping 文件:[(app 目录名, 路径)]。

    按「apps 包下每个子目录里的 mapping 文件,凡所在目录不是已注册 app 的」算,不只看注册表记下的出错项:
    导入失败、缺 eval_meta 的会记进出错项,而没有 PATTERN_DAG、或 pattern_id 撞名被盖掉的是悄悄跳过的。
    registry 不带 apps_pkg(测试用的替身)时为空。"""
    pkg = getattr(registry, "apps_pkg", None)
    if pkg is None:
        return []
    try:
        roots = [Path(p) for p in importlib.import_module(pkg).__path__]
    except Exception:
        return []
    registered = {Path(registry.get(app).__file__).parent.resolve() for app in registry.ids()}
    return [(f.parent.name, f) for root in roots for f in sorted(root.glob(f"*/{mapping_mod.MAPPING_FILE}"))
            if f.parent.resolve() not in registered]


def _unfinished_rounds(folder: Path, pattern: str) -> list[str]:
    """folder 里这个 pattern 没走完的 round 文件名:是 start_round 写的、pattern 相同、没有同名的 .report.md。"""
    out = []
    for f in sorted(folder.glob("*.json")) if folder.is_dir() else []:
        try:
            rnd = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(rnd, dict) and rnd.get("format") == ROUND_FORMAT and rnd.get("pattern") == pattern \
                and not f.with_name(f.stem + ".report.md").exists():
            out.append(f.name)
    return out


def _ensure_no_app(pattern: str, registry) -> None:
    """走「这个 pattern 还没有 app」之前的兜底:分不清有没有 app 时报 ValueError、不定格。

    定格时把有 app 的 pattern 当成没有 app,旧版买点就没存下,这一轮再也补不回;所以两种情形一律拦:
    - 已注册 app 的 mapping 读不出 pattern(文件写坏、pattern 行丢了):它可能正是这个 pattern 的;
    - 没注册上的 app(导入失败、缺 eval_meta、没被认出来),磁盘上的 mapping 写的是这个 pattern,或那份
      mapping 读不出。"""
    unreadable = [m["app"] for m in mapping_mod.read_mappings(registry)
                  if m["pattern"] is None and m["problem"] is not None]
    if unreadable:
        raise ValueError(f"app {', '.join(unreadable)} 的 mapping.yaml 读不出 pattern,分不清 pattern {pattern!r} "
                         "有没有 app:先把它修好(只动 mapping.yaml),不要当成还没有 app 去定格")
    for app, f in _unregistered_mapping_files(registry):
        try:
            raw = yaml.safe_load(f.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            raw = None
        if not isinstance(raw, dict) or raw.get("pattern") == pattern:
            raise ValueError(f"目录 {app} 的 app 没注册上(导入失败、缺 eval_meta 或没被认出来),而它的 mapping.yaml "
                             f"{'写的正是' if isinstance(raw, dict) else '读不出,可能写的是'} pattern {pattern!r}:"
                             "这不是还没有 app,不要定格、也不要改 app,把没注册上的原因告诉用户")


def _mapping_of(pattern: str, registry) -> tuple[dict, object]:
    """同 _find_mapping,但没有 app 也报 ValueError(改版报告要有 app 才比得出)。"""
    found = _find_mapping(pattern, registry)
    if found is None:
        raise ValueError(f"没有哪个 app 的 mapping.yaml 写了 pattern {pattern!r}")
    return found


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
def start_round(pattern: str, out_path, *, no_app: bool = False, cfg: Optional[dict] = None,
                registry=None) -> dict:
    """一轮开头:定格 + 用改之前的 app 存下旧买点。

    参数:pattern 是标注里的 pattern 名;out_path 是 round 文件(JSON,位置见模块说明「round 文件」;已存在 →
    FileExistsError);no_app=True 表示调用方确认这个 pattern 真的还没有 app(见下);cfg、registry 缺省见
    模块说明。

    下面几种情形一律 ValueError、不写 round 文件(都是定格错了补不回的):
    - out_path 所在目录里,这个 pattern 还有没走完的一轮(有 round 文件、没有同名 .report.md):接着那一轮做;
    - 没有 app 的 pattern,标注里又没有它的任何东西(没有样本、反馈,也不在 pattern 表里):多半是名字敲错了
      (有 app 的不查:用户把样本全挪走也是正常的一轮);
    - 没有哪个已注册 app 的 mapping 写这个 pattern,而调用方没传 no_app=True:可能是 pattern 改过名、mapping
      丢了或写错、app 没被认出来,要逐条排除后才能当成没有 app;
    - 传了 no_app=True,但分不清有没有 app(_ensure_no_app),或这个 pattern 其实有 app。

    做的事:
    1. 由 mapping 找到 app,把 mapping 会话段里现有的 snapshot 抄下来记作 prev(没有为 None;会话段写坏了
       → ValueError,先修好再来,否则分不清上一轮定在哪);几个 app 的 mapping 写了这个 pattern → ValueError;
    2. 读当前标注,新快照 = {seen: {机器: 从 1 起连续到齐的序号}, samples: 这个 pattern 的样本编号(按 seen
       截出的状态), at: 今天};
    3. 股票 = prev 时的状态 ∪ 新快照时的状态里这个 pattern 有样本或反馈的股票,当前 app 逐只跑出买点;
    4. 写 round 文件 {format, pattern, app_id, app_ver, prev, snapshot, buys: {股票: AppBuys}, unavailable:
       {读不到行情的股票: 原因}},打印要写进 mapping 的新快照 YAML。
    返回写进 round 文件的那个字典。

    这个 pattern 还没有 app(没有哪个 mapping 写它)时照常定格:不跑买点,round 文件里 app_id、app_ver、prev 为
    None,buys、unavailable 为空;打印的快照等建好 app 和 mapping 之后写进它的会话段。没有 mapping 就没有地方
    记上一轮的定格:定格之后一直没建出 app、又另开一轮时,新一轮的 prev 仍为 None(接着做没走完的那一轮就
    遇不到)。
    """
    cfg = load_config() if cfg is None else cfg
    registry = _registry() if registry is None else registry
    out = Path(out_path)
    if out.exists():
        raise FileExistsError(
            f"round 文件已存在: {out}。这一轮已经定格过,不要再定格、也不要换个文件名重来"
            "(再定格一次,这一轮用户改的标注就从报告里漏掉了):直接用它接着改 app、出报告")
    unfinished = _unfinished_rounds(out.parent, pattern)
    if unfinished:
        raise ValueError(f"pattern {pattern!r} 还有没走完的一轮({', '.join(unfinished)} 没有同名的 .report.md):"
                         "不要再定格,接着那一轮做完(出报告、记账、存报告)再开新的一轮")
    found = _find_mapping(pattern, registry)
    if found is None:
        _ensure_no_app(pattern, registry)
        if not no_app:
            raise ValueError(
                f"没有哪个已注册 app 的 mapping.yaml 写了 pattern {pattern!r}。这不一定是还没有 app:pattern 改过名、"
                "mapping.yaml 丢了或 pattern 写错、app 没被认出来,都是这个样子,而当成没有 app 去定格就存不下旧版买点。"
                "逐条排除、确认它真的还没有 app 之后,再传 no_app=True 定格")
    elif no_app:
        raise ValueError(f"pattern {pattern!r} 已有 app {found[0]['app']},不要传 no_app=True")
    m, mod = found if found is not None else (None, None)
    if m is not None and m["session_problem"] is not None:
        raise ValueError(f"app {m['app']} 的 mapping 会话段写坏了,先修好: {m['session_problem']}")
    prev = ((m["session"] or {}).get("snapshot") if m is not None else None)
    prev = json.loads(json.dumps(prev)) if prev else None

    seen = {k: v["through"] for k, v in read_annotations(cfg)["machines"].items()}
    state = read_annotations(cfg, as_of=seen)["state"]
    samples, feedback = _pattern_objects(state, pattern)
    if m is None and not samples and not feedback and pattern not in {p["name"] for p in state["patterns"]}:
        raise ValueError(f"标注里没有 pattern {pattern!r} 的任何东西(没有样本、反馈,pattern 表里也没有):名字敲错了?")
    symbols = _symbols(samples, feedback)
    if prev is not None:
        symbols |= _symbols(*_pattern_objects(read_annotations(cfg, as_of=prev["seen"])["state"], pattern))
    snapshot = {"seen": seen, "samples": sorted(samples), "at": dt.date.today().isoformat()}

    buys, missing = _run_all(mod, cfg, symbols) if m is not None else ({}, {})
    rnd = {"format": ROUND_FORMAT, "pattern": pattern, "app_id": m["app"] if m is not None else None,
           "app_ver": app_ver(mod) if m is not None else None, "prev": prev, "snapshot": snapshot,
           "buys": {s: b.to_dict() for s, b in buys.items()}, "unavailable": missing}
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "x", encoding="utf-8") as f:
        f.write(json.dumps(rnd, ensure_ascii=False, indent=1) + "\n")

    if m is None:
        print(f"# round 文件: {out}(这个 pattern 还没有 app,没跑买点)")
        print("# 建好 app 和 mapping.yaml 之后,把下面这段写进它的会话段")
    else:
        print(f"# round 文件: {out}(股票 {len(symbols)} 只,读不到行情 {len(missing)} 只)")
        print(f"# 立刻写进 {mapping_mod.mapping_path(mod)}:只替换 session 下的 snapshot,conditions、tags 原样保留")
    print(yaml.safe_dump({"session": {"snapshot": snapshot}}, allow_unicode=True, sort_keys=False,
                         default_flow_style=None), end="")
    return rnd


# ───────────────────────── ④ 改版报告 ─────────────────────────
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
        return _link(self.link_base, self.pattern, symbol, date)


def _link(link_base: str, pattern: str, symbol: str, date: str) -> str:
    """落在 compare 那只股票那一天的链接(格式见模块说明)。"""
    q = urlencode({"symbol": symbol, "date": date, "pattern": pattern, "mode": "compare"}, quote_via=quote)
    return f"{link_base}#{q}"


def _span(start: str, end: str) -> str:
    return start if start == end else f"{start}～{end}"


def _short(text: Optional[str]) -> str:
    """反馈理由的前几个字(用户写的内容,原样只去换行)。"""
    t = " ".join((text or "").split())
    return t if len(t) <= NOTE_CHARS else t[:NOTE_CHARS] + "…"


def _fb_label(ctx: _Ctx, fb: Mapping) -> str:
    """一条反馈的显示:链接(股票 + 日期范围,落在 start)、点出的 node、理由、编号(与别处共享时带上 issue 值)。
    没点 node 就没有「落在」那个括号,没写理由就没有「」。"""
    issue = f"，issue {fb['issue']}" if fb.get("issue") else ""
    return (f"[{fb['symbol']} {_span(fb['start'], fb['end'])}]({ctx.link(fb['symbol'], fb['start'])}) "
            f"{_fb_content(fb)}（{fb['id']}{issue}）")


def _fb_content(fb: Mapping) -> str:
    """一条反馈(或一个 issue)的内容:`（落在 a、b）「理由前几个字」`,两样都可能没有。"""
    nodes = fb.get("nodes") or []
    return (f"（落在 {'、'.join(nodes)}）" if nodes else "") + \
        (f"「{_short(fb['note'])}」" if fb.get("note") else "")


def _fb_status(fb: Optional[Mapping], buys: Mapping) -> str:
    """反馈在一组买点下的状态;没有这条 → 'absent';这只股票读不到行情 → 'na'。"""
    if fb is None:
        return "absent"
    b = buys.get(fb["symbol"])
    return "na" if b is None else match.feedback_status(fb, b)


def _status_text(s: str) -> str:
    return {"absent": "（没有这条）", "na": "（读不到行情）", "lost": "起点认不出"}.get(s, f"`{s}`")


def _lost_lines(ctx: _Ctx, now: Mapping) -> list[str]:
    """现在是 lost 的反馈,每条留一行待会话交代。now 是 {反馈编号: 现在的状态}。"""
    lost = [fid for fid, s in now.items() if s == "lost"]
    if not lost:
        return []
    return ["起点认不出的反馈（页面上显示成 `unmatched`），每条请交代一句是改好了、还是认法变了：",
            *[f"- {_fb_label(ctx, ctx.f_new[fid])}：（待填：改好了 / 认法变了）" for fid in lost], ""]


def _fb_order(ctx: _Ctx, fid: str) -> tuple:
    """各写各的排前(按股票、日期);共享同一个 issue 的几处挨在一起。"""
    f = ctx.f_new.get(fid) or ctx.f_old[fid]
    return f.get("issue") or "", f["symbol"], f["start"], f["end"], fid


def _issue_groups(fbs: Mapping) -> list[tuple[str, list[str]]]:
    """把反馈按 issue 分组:[(名字, [反馈编号])]。带同一个 issue 值的为一组,名字就是那个值;不带的各自一组,
    名字是那条反馈的编号。组内按(股票、起止、编号)排,组按第一次出现的先后。"""
    groups: dict = {}
    order = sorted(fbs, key=lambda i: (fbs[i]["symbol"], fbs[i]["start"], fbs[i]["end"], i))
    for fid in order:
        issue = fbs[fid].get("issue")
        groups.setdefault(("issue", issue) if issue else ("single", fid), []).append(fid)
    return [(key[1], ids) for key, ids in groups.items()]


def _issue_rank(statuses: list[str]) -> int:
    """issue 的排序档:有处还在买的在前,有 lost 的其次,其余在后。"""
    return 0 if "matched" in statuses else 1 if "lost" in statuses else 2


def _issue_lines(ctx: _Ctx, now: Mapping, changed: set) -> list[str]:
    """各 issue 现在怎样:有一处还在买(matched)、有一处 lost、或这一版有一处状态变了的 issue 各一行(标了
    几处、还在买几处、lost 几处、这一版变了几处),其余只给个数。只有一处的 issue 用那条反馈的编号当名字。
    now 是 {反馈编号: 现在的状态};changed 是这一版状态变了的反馈编号(上一轮没有、这一轮新标的也算)。"""
    rows, quiet = [], 0
    for name, ids in _issue_groups({fid: ctx.f_new[fid] for fid in now}):
        statuses = [now[fid] for fid in ids]
        still, lost, moved = statuses.count("matched"), statuses.count("lost"), sum(fid in changed for fid in ids)
        if not (still or lost or moved):
            quiet += 1
            continue
        text = f"- `{name}`{_fb_content(ctx.f_new[ids[0]])}：{len(ids)} 处，还在买 {still} 处"
        text += (f"，起点认不出 {lost} 处" if lost else "") + (f"，这一版变了 {moved} 处" if moved else "")
        rows.append((_issue_rank(statuses), name, text))
    if not rows and not quiet:
        return []
    lines = ["各 issue 现在：", *[text for _, _, text in sorted(rows)]]
    if quiet:
        lines.append(f"另有 {quiet} 个 issue 各处都不买了、这一版没变。")
    return lines + [""]


def _section_feedback(ctx: _Ctx) -> tuple[list[str], bool, dict]:
    """① 反馈的状态。返回 (行, 有没有变化, {反馈编号: 现在的状态})。"""
    lines = ["## ① 反馈的状态", ""]
    ids = sorted(ctx.f_old.keys() | ctx.f_new.keys(), key=lambda i: _fb_order(ctx, i))
    now = {fid: _fb_status(ctx.f_new[fid], ctx.new_buys) for fid in ids if fid in ctx.f_new}
    if not ids:
        return lines + ["这个 pattern 还没有反馈。", ""], False, now
    changed, changed_ids = [], set()
    for fid in ids:
        old = _fb_status(ctx.f_old.get(fid), ctx.old_buys)
        new = now.get(fid, "absent")
        if old != new:
            fb = ctx.f_new.get(fid) or ctx.f_old[fid]
            changed.append(f"- {_fb_label(ctx, fb)}：{_status_text(old)} → {_status_text(new)}")
            changed_ids.add(fid)
    rest = len(ids) - len(changed)
    lines += (changed + (["", f"其余 {rest} 条没变。"] if rest else [])) if changed else ["状态都没变。"]
    lines += ["", _now_summary(ctx, now), ""]
    return lines + _issue_lines(ctx, now, changed_ids) + _lost_lines(ctx, now), bool(changed), now


def _now_summary(ctx: _Ctx, now: Mapping) -> str:
    """现在各状态几条(朱红按会话的原因标签判,见 match.is_red)。"""
    red = sum(match.is_red(s, ctx.tags.get(i)) for i, s in now.items())
    n = {k: sum(s == k for s in now.values()) for k in ("lost", "unmatched", "na")}
    text = f"现在 {len(now)} 条反馈：朱红 {red} 条、起点认不出 {n['lost']} 条、`unmatched` {n['unmatched']} 条"
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


def _read_round(pattern: str, round_path) -> dict:
    """读 start_round 写的 round 文件;不是它写的、或是别的 pattern 的 → ValueError。"""
    rnd = json.loads(Path(round_path).read_text(encoding="utf-8"))
    if rnd.get("format") != ROUND_FORMAT:
        raise ValueError(f"不是 start_round 写的 round 文件: {round_path}")
    if rnd["pattern"] != pattern:
        raise ValueError(f"round 文件是 pattern {rnd['pattern']!r} 的,不是 {pattern!r}")
    return rnd


def _link_base(cfg: dict, link_base: Optional[str]) -> str:
    """链接前缀:没给就取 `http://localhost:<配置的 frontend_port>/`。"""
    if link_base is not None:
        return link_base
    return f"http://localhost:{cfg.get('frontend_port', DEFAULT_CONFIG['frontend_port'])}/"


def _session_notes(m: Mapping, snap: Mapping) -> list[str]:
    """报告开头关于 mapping 会话段的提醒:会话段读不到时说明;否则里面的定格不是这一轮开头那份时提醒写上。"""
    if m["session_problem"] is not None:
        return [f"- 会话段读不到（原因：{m['session_problem']}），原因标签没读到，朱红按没有标签算"]
    written = (m["session"] or {}).get("snapshot") or {}
    if (written.get("seen"), written.get("samples")) != (snap["seen"], snap["samples"]):
        return [f"- 注意：{m['app']} 的 mapping.yaml 里的定格不是这一轮开头那份；没写进去的话先写上，"
                "否则下一轮会把这一轮的标注改动再报一遍"]
    return []


def _first_report(pattern: str, rnd: Mapping, link_base: str, cfg: dict, registry) -> str:
    """第一版报告:这一轮定格时还没有 app(round 文件里没有旧版买点),现在建好了。用现在的 app 跑这一轮定格时
    这个 pattern 全部样本的股票,逐张给结论(一致 = 正样本 matched、负样本 unmatched;相反;读不到行情的没比),
    相反的排前,每张带落在 compare 的链接。没有反馈各节、没有新旧对照。现在还没有 app → ValueError。"""
    found = _find_mapping(pattern, registry)
    if found is None:
        raise ValueError(f"pattern {pattern!r} 这一轮定格时还没有 app,现在也没有哪个 app 的 mapping.yaml 写它:"
                         "没有 app 可跑,先建好 app 和 mapping 再出报告")
    m, mod = found
    snap = rnd["snapshot"]
    samples, _ = _pattern_objects(read_annotations(cfg, as_of=snap["seen"])["state"], pattern)
    buys, missing = _run_all(mod, cfg, _symbols(samples))
    verdicts = {sid: _verdict(s, buys) for sid, s in samples.items()}
    order = sorted(samples, key=lambda i: (samples[i]["symbol"], samples[i]["date"], i))
    groups = {False: [i for i in order if verdicts[i] is not None and not verdicts[i][1]],
              None: [i for i in order if verdicts[i] is None],
              True: [i for i in order if verdicts[i] is not None and verdicts[i][1]]}

    def row(sid: str) -> str:
        s, v = samples[sid], verdicts[sid]
        label = (f"[{s['symbol']} {s['date']}]({_link(link_base, pattern, s['symbol'], s['date'])}) "
                 f"{_JUDGMENT[s['judgment']]}（{sid}）")
        return f"- {label}：读不到行情" if v is None else f"- {label}：{_mark(v)}（`{v[0]}`）"

    lines = [f"# {pattern} 改版报告（第一版）", "",
             f"- app：{m['app']}（第一版：这一轮定格时还没有 app，没有旧版可比，只列各样本的结论）",
             f"- 对照：这一轮定格时的标注配第一版 app 的买点；共 {len(_symbols(samples))} 只股票"]
    if missing:
        lines.append(f"- 读不到行情、没比的股票：{'、'.join(sorted(missing))}")
    lines += _session_notes(m, snap) + ["", "## 样本结论", ""]
    if not samples:
        return "\n".join(lines + ["这个 pattern 还没有样本。", ""])
    lines += [f"样本 {len(samples)} 张：一致（✓）{len(groups[True])}、相反（✗）{len(groups[False])}、"
              f"没比 {len(groups[None])}。", ""]
    lines += ["和 app 相反的：", *[row(i) for i in groups[False]], ""] if groups[False] else ["没有和 app 相反的。", ""]
    if groups[None]:
        lines += ["没比的：", *[row(i) for i in groups[None]], ""]
    if groups[True]:
        lines += ["一致的：", *[row(i) for i in groups[True]], ""]
    return "\n".join(lines)


def revision_report(pattern: str, round_path, link_base: Optional[str] = None, *,
                    cfg: Optional[dict] = None, registry=None) -> str:
    """一轮结尾:用现在的 app 重跑,和 round 文件求差,返回给用户看的 Markdown 报告(六节见模块说明)。

    参数:pattern 是标注里的 pattern 名(须与 round 文件一致);round_path 是 start_round 写的文件;link_base
    是落在 compare 的链接前缀,缺省 `http://localhost:<配置的 frontend_port>/`;cfg、registry 缺省见模块说明。

    旧标注 = read_annotations(as_of=round 文件里的 prev.seen)(prev 为空就等于新标注);新标注 =
    read_annotations(as_of=round 文件里新快照的 seen);旧买点 = round 文件;新买点 = 现在重跑。
    round 文件是在还没有 app 时定格的(app_id 为 None):没有旧版可比,改出「第一版」报告(_first_report)——
    用现在的 app 跑这一轮定格时这个 pattern 全部样本的股票,逐张给结论;到这时还没有 app → ValueError。
    mapping 会话段里的 snapshot 不是 round 文件里那份新快照时,报告开头提醒一句(没写进去,下一轮会重报);
    会话段写坏了(读不到)时改写一句「会话段读不到」,不再提醒定格,原因标签当作没有。
    """
    cfg = load_config() if cfg is None else cfg
    registry = _registry() if registry is None else registry
    rnd = _read_round(pattern, round_path)
    link_base = _link_base(cfg, link_base)
    if rnd["app_id"] is None:
        return _first_report(pattern, rnd, link_base, cfg, registry)
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
    head += _session_notes(m, snap) + [""]

    if not (fb_changed or days_changed or flipped or gone):
        body = ["**无变化**：反馈的状态、买点日、样本结论都和改版前一样。", "",
                f"样本 {len(s_new)} 张。" + (_now_summary(ctx, now) if now else "这个 pattern 还没有反馈。"), ""]
        return "\n".join(head + body + _lost_lines(ctx, now))
    return "\n".join(head + fb_lines + day_lines + flip_lines + gone_lines)


# ───────────────────────── 这一轮的输入摘要 ─────────────────────────
_VERDICT = {True: "一致", False: "相反", None: "没比"}
_VERDICT_ORDER = {False: 0, None: 1, True: 2}   # 相反的排前,没比的其次


def _quoted(text: Optional[str], indent: str = "") -> list[str]:
    """用户写的原文,逐行引用(不截断、不改字);没写 → 一行「（没写）」。"""
    if not (text or "").strip():
        return [f"{indent}> （没写）"]
    return [f"{indent}> {line}" for line in text.splitlines()]


def _one_line(text: Optional[str]) -> str:
    """用户写的原文压成一行(只把换行、连续空白并成一个空格,不截断)。"""
    return " ".join((text or "").split())


def _feature_name(features: Mapping, fid: Optional[str]) -> str:
    """特征编号 → 给人看的名字;框还没起名、词表里已没有这个编号时各有说法。"""
    if fid is None:
        return "（没起名）"
    return features[fid]["name"] if fid in features else f"{fid}（词表里没有）"


def _digest_definitions(state: Mapping, pattern: str, samples: Mapping, boxes: Mapping,
                        m: Optional[Mapping]) -> list[str]:
    """「定义」一节:pattern 定义原文;这个 pattern 的样本收的框用到的特征(当特征或当属性)加上 mapping 里写了的
    特征,各带定义原文与对到的 node,没对到 node 的单列。"""
    lines = ["## 定义", ""]
    pat = next((p for p in state["patterns"] if p["name"] == pattern), None)
    if pat is None:
        lines += ["标注的 pattern 表里没有这个 pattern。", ""]
    else:
        lines += ["pattern 定义：", *_quoted(pat.get("definition")), ""]
    features = {f["id"]: f for f in state["features"]}
    mapped = dict(m["features"]) if m is not None else {}
    used = set(mapped)
    for s in samples.values():
        for bid in s["members"]:
            box = boxes.get(bid)
            if box is not None:
                used |= {box["feature"], *box.get("attrs", {})} - {None}
    order = [fid for fid in features if fid in used] + sorted(used - set(features))

    def row(fid: str) -> list[str]:
        node = f" → node `{mapped[fid]}`" if fid in mapped else ""
        if fid not in features:
            return [f"- `{fid}`（词表里没有这个编号）{node}"]
        return [f"- `{fid}` {features[fid]['name']}{node}", *_quoted(features[fid].get("definition"), "  ")]

    on_node = [fid for fid in order if fid in mapped]
    off_node = [fid for fid in order if fid not in mapped]
    if not order:
        lines += ["这个 pattern 的样本还没有收框，mapping 里也没有写特征。", ""]
    if on_node:
        lines += ["对到 node 的特征：", *[x for fid in on_node for x in row(fid)], ""]
    if off_node:
        lines += ["还没对到 node 的特征" + ("：" if m is not None else "（还没有 app）："),
                  *[x for fid in off_node for x in row(fid)], ""]
    return lines


def _digest_mapping(m: Optional[Mapping]) -> list[str]:
    """「mapping」与「账本」两节:app 名、notes、mapping 与会话段的问题;会话段现有的 conditions、tags。"""
    if m is None:
        return ["## mapping", "", "还没有 app，也没有 mapping。", "", "## 账本", "", "还没有 app，没有账本。", ""]
    lines = ["## mapping", "", f"- app：`{m['app']}`"]
    if m["notes"]:
        lines += ["- notes：", *[f"  - `{k}`：{_one_line(v)}" for k, v in m["notes"].items()]]
    else:
        lines.append("- notes：没有")
    if m["problem"] is not None:
        lines.append(f"- mapping 的问题（有问题的 mapping，compare 用不了）：{m['problem']}")
    if m["session_problem"] is not None:
        lines.append(f"- 会话段的问题：{m['session_problem']}")
    lines += ["", "## 账本", ""]
    if m["session_problem"] is not None:
        return lines + ["会话段读不到，账本当作空的；先修好再记账。", ""]
    session = m["session"] or {}
    conds, tags = session.get("conditions") or [], session.get("tags") or {}
    if conds:
        lines += [f"conditions（{len(conds)} 行）：",
                  *[f"- `{c['where']}` ← {'、'.join(c['from']) or '（没写来源）'}：{c['state'] or '（没写）'}" for c in conds]]
    else:
        lines.append("conditions：没有。")
    if tags:
        lines += [f"tags（{len(tags)} 条）：", *[f"- {fid} `{tag}`" for fid, tag in tags.items()]]
    else:
        lines.append("tags：没有。")
    return lines + [""]


def _digest_changes(state_prev: Optional[Mapping], state: Mapping, pattern: str) -> list[str]:
    """「上一轮以来的变化」一节:pattern_changes 的结果,同一个对象的几条并成一行;没有上一轮时注明。"""
    lines = ["## 上一轮以来的变化", ""]
    if state_prev is None:
        return lines + ["没有上一轮的定格（第一轮），不比。", ""]
    by_obj: dict = {}
    for c in pattern_changes(state_prev, state, pattern):
        by_obj.setdefault((c["kind"], c["id"]), []).append(c["change"])
    if not by_obj:
        return lines + ["没有变化。", ""]
    where = {}
    for st in (state_prev, state):       # 后读的新状态盖掉旧的
        for c in st["charts"]:
            where.update({("sample", s["id"]): f"{c['symbol']} {s['date']}" for s in c["samples"]})
            where.update({("box", b["id"]): f"{c['symbol']} {_span(b['start'], b['end'])}" for b in c["boxes"]})
    for (kind, oid), changes in by_obj.items():
        at = f"（{where[(kind, oid)]}）" if (kind, oid) in where else ""
        lines.append(f"- {kind} `{oid}`{at}：{'、'.join(f'`{x}`' for x in changes)}")
    return lines + [""]


def _digest_place(fb: Mapping, link: str, status: str, tag: Optional[str], buys: Optional["AppBuys"],
                  pos_samples: list, since: Optional[str]) -> str:
    """issue 里的一处:链接、target、状态、标签、范围里在买的日子、范围里用户的正样本、编号与相对上一轮的变化。"""
    target = f"`{fb['target']}`" + (f"（起点 {fb['family_start']}）" if fb["target"] == "family" else "")
    parts = [f"[{fb['symbol']} {_span(fb['start'], fb['end'])}]({link}) {target} {status}"]
    if tag is not None:
        parts[0] += f"，标签 `{tag}`" + ("（挂了它不算朱红）" if tag == mapping_mod.TAG_REDEFINED else "")
    if buys is not None:
        inside = [d for d in buys.buy_days if fb["start"] <= d <= fb["end"]]
        parts.append(f"范围里在买 {len(inside)} 天" + (f"：{'、'.join(inside)}" if inside else ""))
        if fb["target"] == "family":
            outside = [d for d in buys.families.get(fb["family_start"], ()) if not fb["start"] <= d <= fb["end"]]
            if outside:
                parts.append(f"同一族在范围外还买 {len(outside)} 天：{'、'.join(outside)}")
    if pos_samples:
        parts.append("范围里你的正样本：" + "、".join(f"{s['date']}（{s['id']}）" for s in pos_samples))
    return "  - " + "；".join(parts) + f"（{fb['id']}{'，' + since if since else ''}）"


def _digest_issues(ctx_link, picked: Mapping, f_prev: Optional[Mapping], samples: Mapping, buys: Mapping,
                   has_app: bool, m: Optional[Mapping]) -> list[str]:
    """「issue」一节:picked 的反馈按 issue 分组(_issue_groups),每组的 nodes、note 全文、账本里指着它的条件、
    各处的状态。有处还在买的组在前,有 lost 的其次。answer、dag 不输出。"""
    lines = ["## issue", ""]
    if not picked:
        return lines + ["这个 pattern 还没有反馈。", ""]
    session = (m["session"] or {}) if m is not None else {}
    tags, conds = session.get("tags") or {}, session.get("conditions") or []

    def status_of(fb: Mapping) -> str:
        return _fb_status(fb, buys) if has_app else "na"

    def status_text(s: str) -> str:
        return ("读不到行情" if has_app else "没比") if s == "na" else f"`{s}`"

    now = {fid: status_of(fb) for fid, fb in picked.items()}
    groups = sorted(_issue_groups(picked), key=lambda g: (_issue_rank([now[i] for i in g[1]]), g[0]))
    n_still, n_lost = sum(s == "matched" for s in now.values()), sum(s == "lost" for s in now.values())
    lines.append(f"共 {len(groups)} 个 issue、{len(picked)} 处；" +
                 (f"还在买 {n_still} 处、起点认不出 {n_lost} 处。" if has_app else "还没有 app，状态没比。"))
    lines.append("")
    for name, ids in groups:
        first = picked[ids[0]]
        still = sum(now[i] == "matched" for i in ids)
        lines.append(f"### `{name}`（{len(ids)} 处" + (f"，还在买 {still} 处）" if has_app else "）"))
        nodes = first.get("nodes") or []
        lines.append("- 落在：" + ("、".join(nodes) if nodes else "没点 node"))
        lines += ["- note：", *_quoted(first.get("note"), "  ")]
        mine = [c for c in conds if set(c["from"]) & set(ids)]
        lines.append("- 账本：" + ("；".join(f"`{c['where']}`（{c['state'] or '没写'}）" for c in mine)
                                   if mine else "还没有条件"))
        lines.append("- 各处：")
        for fid in ids:
            fb = picked[fid]
            pos = sorted((s for s in samples.values() if s["symbol"] == fb["symbol"] and s["judgment"] == "pos"
                          and fb["start"] <= s["date"] <= fb["end"]), key=lambda s: (s["date"], s["id"]))
            since = None
            if f_prev is not None:
                was = f_prev.get(fid)
                if was is None:
                    since = "上一轮之后新标的"
                elif (was.get("note"), sorted(was.get("nodes") or [])) != \
                        (fb.get("note"), sorted(fb.get("nodes") or [])):
                    since = "内容改过"
            lines.append(_digest_place(fb, ctx_link(fb["symbol"], fb["start"]), status_text(now[fid]),
                                       tags.get(fid), buys.get(fb["symbol"]) if has_app else None, pos, since))
        lines.append("")
    return lines


def _digest_samples(ctx_link, samples: Mapping, boxes: Mapping, features: Mapping, buys: Mapping,
                    has_app: bool) -> list[str]:
    """「样本」一节:这个 pattern 的全部样本,和 app 相反的排前;每张带 note、结论和它收的成员框。"""
    lines = ["## 样本", ""]
    if not samples:
        return lines + ["这个 pattern 还没有样本。", ""]
    verdicts = {sid: (_verdict(s, buys) if has_app else None) for sid, s in samples.items()}
    agree = {sid: (v[1] if v is not None else None) for sid, v in verdicts.items()}
    n = {k: sum(a is k for a in agree.values()) for k in (True, False, None)}
    lines.append(f"共 {len(samples)} 张：一致 {n[True]}、相反 {n[False]}、没比 {n[None]}"
                 + ("。" if has_app else "（还没有 app）。"))
    lines.append("")
    for sid in sorted(samples, key=lambda i: (_VERDICT_ORDER[agree[i]], samples[i]["symbol"], samples[i]["date"], i)):
        s, v = samples[sid], verdicts[sid]
        mark = f"**{_VERDICT[False]}**" if agree[sid] is False else _VERDICT[agree[sid]]
        match_text = f"，`{v[0]}`" if v is not None else ""
        lines.append(f"- {mark} [{s['symbol']} {s['date']}]({ctx_link(s['symbol'], s['date'])}) "
                     f"{_JUDGMENT[s['judgment']]}{match_text}（{sid}）")
        if (s.get("note") or "").strip():
            lines.append(f"  - note：{_one_line(s['note'])}")
        if not s["members"]:
            lines.append("  - （没收框）")
        for bid in s["members"]:
            box = boxes.get(bid)
            if box is None or box["symbol"] != s["symbol"]:
                lines.append(f"  - 框 `{bid}`（不在这只股票上）")
                continue
            text = f"  - 框 `{bid}` {_feature_name(features, box['feature'])} {_span(box['start'], box['end'])}"
            if box.get("attrs"):
                text += "；属性：" + "、".join(f"{_feature_name(features, k)} {'是' if x else '否'}"
                                               for k, x in box["attrs"].items())
            if (box.get("note") or "").strip():
                text += f"；note：{_one_line(box['note'])}"
            lines.append(text)
    return lines + [""]


def round_digest(pattern: str, round_path, link_base: Optional[str] = None, *,
                 cfg: Optional[dict] = None, registry=None) -> str:
    """这一轮的输入摘要:会话动手之前要看的东西,一次读齐,返回 Markdown(给会话读,不直接给用户)。

    固定在 start_round 之后、改 app 之前调。参数同 revision_report:pattern 须与 round 文件一致;round_path 是
    start_round 写的文件;link_base 是落在 compare 的链接前缀。

    口径:标注取这一轮定格时的(read_annotations(as_of=round 文件里新快照的 seen)),定格之后用户再改的不进来;
    反馈状态与样本结论一律用 round 文件里存的买点算(改之前的 app),不重跑 app、不读行情——所以改完 app 之后
    再调,状态也不变(看改后的用 revision_report)。

    各节:
    - 定义:pattern 定义原文;这个 pattern 的样本收的框用到的特征(当特征或当属性)加上 mapping 里写了的特征,
      各带编号、名字、定义原文、对到的 node,没对到的单列;
    - mapping:app 名、notes、mapping 自身的问题、会话段的问题;
    - 账本:会话段现有的 conditions、tags;
    - 上一轮以来的变化:pattern_changes(上一轮定格的状态 → 这一轮定格的状态),没有上一轮时注明;
    - issue:来源是 picked 的反馈按 issue 分组(带同一个 issue 值的为一组,不带的各自一组、用反馈编号当名字)。
      每组:nodes、note 全文、账本里 from 含它任一处编号的条件;各处:链接、target、状态、会话标签、范围里在买
      的日子(一族另写同一族在范围外还买的日子)、范围里用户自己的正样本、编号、相对上一轮是新标的还是内容
      改过。有处还在买的组在前,有 lost 的其次;
    - 样本:这个 pattern 的全部样本,和 app 相反的(正样本没买到、负样本买了)排前;每张:结论(一致 / 相反 /
      没比)、链接、judgment、match、编号、note,以及它收的成员框(编号、特征名、起止、属性、note);
    - 没比的:读不到行情的股票。
    反馈记录里若带着 answer、dag(见 store 模块说明「反馈」),这里不输出:它们不表示任何意思,不拿来分类。

    round 文件是在还没有 app 时定格的(app_id 为 None):照出定义、变化、样本,状态与结论都写「没比」(建好 app
    之后各样本的结论看 revision_report 的第一版报告);这时若已经建好了 mapping,mapping 与账本两节照它现在的
    样子出。不写 mapping、不写标注。
    """
    cfg = load_config() if cfg is None else cfg
    registry = _registry() if registry is None else registry
    rnd = _read_round(pattern, round_path)
    link_base = _link_base(cfg, link_base)
    found = _find_mapping(pattern, registry)
    m = found[0] if found is not None else None
    prev, snap = rnd["prev"], rnd["snapshot"]
    has_app = rnd["app_id"] is not None

    read = read_annotations(cfg, as_of=snap["seen"])
    state = read["state"]
    state_prev = read_annotations(cfg, as_of=prev["seen"])["state"] if prev else None
    samples, feedback = _pattern_objects(state, pattern)
    picked = {i: f for i, f in feedback.items() if f["source"] == "picked"}
    f_prev = None
    if state_prev is not None:
        f_prev = {i: f for i, f in _pattern_objects(state_prev, pattern)[1].items() if f["source"] == "picked"}
    boxes = {b["id"]: {**b, "symbol": c["symbol"]} for c in state["charts"] for b in c["boxes"]}
    features = {f["id"]: f for f in state["features"]}
    buys = {s: AppBuys.from_dict(d) for s, d in rnd["buys"].items()}

    def link(symbol: str, date: str) -> str:
        return _link(link_base, pattern, symbol, date)

    head = [f"# {pattern} 这一轮的输入", "",
            f"- 口径：这一轮定格时的标注（定格于 {snap.get('at', '?')}）配改 app 之前的买点；"
            "定格之后用户再改的标注、改完 app 之后的买点都不在这里"]
    if has_app:
        head.append(f"- app：`{rnd['app_id']}`")
    else:
        head.append("- app：定格时还没有 app，没有买点可比，下面的状态、结论都是「没比」")
    head.append("- 上一轮：" + (f"有定格（{prev.get('at', '日期没记')}）" if prev else "没有（第一轮）"))
    if rnd["unavailable"]:
        head.append(f"- 读不到行情、没比的股票：{'、'.join(sorted(rnd['unavailable']))}")
    if read["conflicts"] or read["violations"]:
        head.append(f"- 标注里有 {len(read['conflicts'])} 条冲突、{len(read['violations'])} 条违规"
                    "（read_annotations 的 conflicts、violations），先看一眼")
    if not read["fingerprint"]["consistent"]:
        head.append("- 标注记下的数据指纹和本机的训练段副本对不上（或本机读不到指纹）")
    if m is not None and m["session_problem"] is None:
        written = (m["session"] or {}).get("snapshot") or {}
        if (written.get("seen"), written.get("samples")) != (snap["seen"], snap["samples"]):
            head.append(f"- 注意：{m['app']} 的 mapping.yaml 里的定格不是这一轮开头那份，先写上")
    head.append("")

    tail = ["## 没比的", ""]
    if not has_app:
        tail.append("还没有 app，全部没比。")
    elif rnd["unavailable"]:
        tail += [f"- {sym}：{why}" for sym, why in sorted(rnd["unavailable"].items())]
    else:
        tail.append("没有读不到行情的股票。")
    return "\n".join(head + _digest_definitions(state, pattern, samples, boxes, m) + _digest_mapping(m)
                     + _digest_changes(state_prev, state, pattern)
                     + _digest_issues(link, picked, f_prev, samples, buys, has_app, m)
                     + _digest_samples(link, samples, boxes, features, buys, has_app) + tail)
