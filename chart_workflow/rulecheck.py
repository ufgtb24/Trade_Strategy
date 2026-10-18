"""规则来自形态卡时的核对:规则声明的要素与角色要和卡那一版一致;卡的样本上、以及样本股与随机抽的一批股票在
看图范围内的每一天,规则信号都要和「卡说成立」一致。对照页(contrast)在来源写 shape:<shape_id>@v<版本> 时开工前
调用,账本记账时再由账本自己调一次(不收调用方传来的核对结果);任一不过就拒绝,通过后把声明与核对结果记进账本
(rule_implements)。

声明:规则文件(--rule)或 app 模块(--app,即 path2_web 发现机制给出的那个模块)在模块顶层写
    IMPLEMENTS = {"E001": "must", "E002": "must_not", "E004": "bonus"}
即「这条规则实现了哪些要素、各是什么角色」(角色同形态卡:must / bonus / must_not)。要素编号可以写卡上
引用的编号,也可以写它合并后并入的编号(按合并后解析到的那条比)。

「卡说成立」(一天、一只股票的事实表上):卡上必须有的要素全是「是」、有它就不买的全是「否」(按卡上记下的
要素版本判;加分项不参与);卡上有触发时,还要当天出现卡上的某个触发(T1~T8 由事实表判)。有要素无法判定
(待写代码、回看不够长、停牌日——当天没成交——的量比)→ 这一天卡判定不了,不比。不成立时报错写明是哪个要素
不对,或者当天缺的是哪个触发。
卡上有手写触发(custom,没有能算的定义)就核对不了规则哪天该成立:直接拒绝,点名是哪个触发。出路:换成表里的
触发;或者在事实表加一行把它算出来——加了之后它要改写成卡上的要素,卡的意思从「几个触发任一个就算」变成「这一项
也必须满足」,想保住原意要在触发表里加一项(改代码)。

三处用同一个口径:规则拿不到用户的框,只能按固定回看(不框选,买点前 default_lookback_bars 根)算事实表,
所以样本核对和逐日核对也按固定回看判卡。各项下限都在配置 shape_check 里,全部待验证。
两道核对(只比规则和卡是否一致,不碰任何前瞻收益或成绩):
  样本:卡那一版及以前加进来的样本,在样本的买点那天按固定回看判卡,规则信号要和「卡说成立」相同。
        另按用户框的窗口判一次:两者判得不同的样本单独列出(这张卡在固定回看下表达不了用户框选时的意思),
        这是卡的问题,不作为拒规则的理由,也不算进能核对的个数。判定不了或读不到行情的样本跳过并列出原因;
        能核对的样本少于 min_samples(默认 3)、或其中买点当天卡成立的少于 min_positive_samples(默认 2;
        卡在样本上都不成立时,永远不成立的规则也全对)就拒绝,报错里写清缺在哪、出路是什么。
  逐日:跑两批股票——全部样本股(样本有没有被排除、跳过都算:逐日按固定回看判,和框无关),加上从训练副本
        随机抽的股票:抽股顺序全局固定,种子是账上登记的训练数据副本指纹(和卡的编号、版本都无关,
        draw_pool / pool_order),沿这个顺序往下取看图范围内
        有交易日的股票,直到「这一版卡在上面有卡成立日」的满 pool_positive_stocks 只(默认 40),最多取
        pool_max_stocks 只(默认 300);取到的不论有没有卡成立日都进逐日比较(没有的,规则在上面也必须
        不成立);取满上限还凑不够就拒,报错写明找到几只、上限多少、怎么调高、调高要多花多少时间。
        比卡窄的规则抓不抓得住,取决于有卡成立日的股票有几只,不取决于一共抽了几只,所以下限按只数定。
        在看图范围内(不早于看图下界、不晚于训练段末日)逐日按固定回看判卡,卡能判定的每一天,规则信号都要
        和「卡说成立」一致;不一致的天数占卡能判定天数的比例超过 max_disagree_share(默认 0,即必须全部一致)
        就拒绝,列出不一致的天。永远成立、比卡宽的规则在卡不成立的日子上露馅,比卡窄、永远不成立的规则在
        卡成立的日子上露馅;卡判「不成立」的天少于 min_negative_days(默认 20)时也拒绝。
        抽股顺序事先算得出来,有人刻意照这批股票去凑过滤条件照样防不住——这一点接受:每次核对现抽一批,
        会变成「失败不记账、可以反复重抽」,更糟。
规则信号:规则文件方式在这只股票截到训练段末日的行情上算一次 signal(df),逐日读;app 方式跑这只股票,
看那天在不在命中里。卡与要素从操作日志重算(先重走全部日志的校验),不读磁盘上的卡与要素文件。
逐日核对按股票并行(cfg["workers"]);逐日卡说什么、规则信号在进程内缓存,键含卡与要素的全部内容、配置、
规则文件指纹和这只股票的数据文件(大小、修改时间),所以同一次运行里记账时的第二次核对不重算,任何输入变了就重算;
app 方式的信号每次重算(app 代码不进指纹)。
"""
from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import random
from pathlib import Path

from chart_workflow.ledger import SHAPE_SOURCE_RE

ROLES = ("must", "bonus", "must_not")
ROLE_TEXT = {"must": "必须有", "bonus": "加分", "must_not": "有它就不买"}
DEFAULTS = {"min_samples": 3, "min_positive_samples": 2, "max_disagree_share": 0.0, "min_negative_days": 20,
            "pool_positive_stocks": 40, "pool_max_stocks": 300}      # 与 config 的 shape_check 同值,都待验证
SHOW_DAYS = 10


class RuleShapeMismatch(ValueError):
    """规则和它声明来自的形态卡对不上。"""


def _settings(cfg: dict) -> dict:
    return {**DEFAULTS, **(cfg.get("shape_check") or {})}


def declared_implements(rule: str | None = None, app: str | None = None) -> dict:
    """读规则文件或 app 模块顶层的 IMPLEMENTS。没写或格式不对 → RuleShapeMismatch。"""
    if rule:
        path = Path(rule).resolve()
        spec = importlib.util.spec_from_file_location(f"_cw_rule_decl_{path.stem}", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        where = f"规则文件 {path.name}"
    else:
        from chart_workflow.rules import app_module_path

        mod = importlib.import_module(app_module_path(app))
        where = f"app {app}({mod.__name__})"
    decl = getattr(mod, "IMPLEMENTS", None)
    if not isinstance(decl, dict) or not decl:
        raise RuleShapeMismatch(f"来源写的是形态卡,{where} 要在模块顶层声明 IMPLEMENTS = "
                                f"{{要素编号: 角色}}(角色 {' / '.join(ROLES)}),说明它实现了卡上哪些要素")
    bad = [f"{k!r}: {v!r}" for k, v in decl.items() if not isinstance(k, str) or v not in ROLES]
    if bad:
        raise RuleShapeMismatch(f"{where} 的 IMPLEMENTS 格式不对(角色只能是 {' / '.join(ROLES)}):"
                                + "、".join(bad))
    return dict(decl)


def check_declaration(decl: dict, ver: dict, els: dict, shape: str) -> list[dict]:
    """声明和卡那一版的要素、角色是否一致(按合并后解析到的编号比)。返回要记进账本的声明;
    不一致 → RuleShapeMismatch,列出差在哪。"""
    from chart_workflow import elements as E

    unknown = sorted(k for k in decl if k not in els)
    if unknown:
        raise RuleShapeMismatch(f"IMPLEMENTS 里的 {'、'.join(unknown)} 不在要素库里")
    card = {}
    for ing in ver["card"].get("ingredients", []):
        if ing.get("element"):
            card[E.resolve(els, ing["element"])] = ing["role"]
    mine = {}
    for k, role in decl.items():
        r = E.resolve(els, k)
        if r in mine and mine[r] != role:
            raise RuleShapeMismatch(f"IMPLEMENTS 里 {k} 合并后是 {r},和另一项角色不同")
        mine[r] = role
    errs = [f"规则没声明卡上的 {E.label(els, r)}（{ROLE_TEXT[card[r]]}）" for r in sorted(set(card) - set(mine))]
    errs += [f"规则声明了卡上没有的 {E.label(els, r)}（{ROLE_TEXT[mine[r]]}）" for r in sorted(set(mine) - set(card))]
    errs += [f"{E.label(els, r)}:卡上是「{ROLE_TEXT[card[r]]}」,规则声明的是「{ROLE_TEXT[mine[r]]}」"
             for r in sorted(set(card) & set(mine)) if card[r] != mine[r]]
    if errs:
        raise RuleShapeMismatch(f"规则声明的要素和形态卡 {shape} 对不上:" + ";".join(errs))
    return [{"element": k, "element_resolved": E.resolve(els, k), "role": role} for k, role in sorted(decl.items())]


def card_says(card: dict, els: dict, facts: dict) -> tuple[bool | None, str]:
    """一天的事实表上「卡说成立」吗(见模块说明):(True / False / None = 判定不了, 理由)。理由:判定不了时
    说哪个要素判定不了;不成立时说是哪个要素不对,或者要素都成立但当天缺卡上的哪个触发。
    前提:卡上没有手写触发(来源写形态卡时 check_rule_against_shape 先拒了这种卡)。"""
    from chart_workflow import elements as E
    from chart_workflow.facts import TRIGGERS

    why_not = ""
    for ing in card.get("ingredients", []):
        if ing.get("role") == "bonus" or not ing.get("element"):
            continue
        v, why = E.evaluate_element(els, ing["element"], facts, ing.get("element_version"))
        if v == "unknown":
            return None, f"{E.label(els, ing['element'])} 无法判定({why})"
        if not why_not and v != ("yes" if ing["role"] == "must" else "no"):
            why_not = f"{E.label(els, ing['element'])} 是「{'是' if v == 'yes' else '否'}」(卡上是「{ROLE_TEXT[ing['role']]}」)"
    if why_not:
        return False, why_not
    terms = [t.get("term") for t in card.get("triggers", [])]
    if not terms:
        return True, ""
    today = {t.get("tid") for t in facts.get("triggers") or []}
    if any(t in today for t in terms):
        return True, ""
    return False, "要素都成立,当天缺卡上的触发 " + "、".join(f"{t}({TRIGGERS[t][1]})" for t in terms)


def custom_triggers(card: dict) -> list[str]:
    """卡上的手写触发(没有能算的定义),每个一句:「t2「放量站上年线」」。"""
    return [f"{t.get('trig_id')}「{t.get('text') or ''}」" for t in card.get("triggers", []) if t.get("term") == "custom"]


_CACHE: dict = {}       # 进程内缓存:一次对照页运行里开工前和记账时各核对一次,第二次直接用(键含全部输入)
_CACHE_MAX = 4096


def _remember(key, value) -> None:
    if len(_CACHE) >= _CACHE_MAX:
        _CACHE.clear()
    _CACHE[key] = value


def _view_range(cfg: dict):
    import pandas as pd

    return pd.Timestamp(cfg.get("view_floor") or cfg["train_start"]), pd.Timestamp(cfg["train_end"])


def _stamp(cfg: dict, symbol: str) -> tuple:
    """这只股票数据的身份(文件、大小、修改时间、截到哪天),做缓存的键。代码名不合格 → ValueError;
    文件不在 → FileNotFoundError。"""
    from chart_workflow.config import dataset_dir
    from chart_workflow.loader import check_symbol

    check_symbol(symbol)
    p = (Path(dataset_dir(cfg)) / f"{symbol}.pkl").resolve()
    st = p.stat()
    return str(p), st.st_size, st.st_mtime_ns, str(cfg["train_end"])


def _digest(*parts) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def _signal(cfg: dict, rule: str | None, app: str | None, params: str | None, symbol: str, df) -> dict[str, bool]:
    """规则在一只股票上的信号 {日期: 这天成立吗}:规则文件方式在截到训练段末日的行情 df 上算一次 signal(df);
    app 方式跑一次这只股票,看那天在不在命中里。"""
    import pandas as pd

    from chart_workflow.rules import _app_worker, _signal_bool, app_module_path, load_rule

    if rule:
        sig = _signal_bool(load_rule(rule), df)
        return {d.strftime("%Y-%m-%d"): bool(x) for d, x in zip(df.index, sig)}
    py = str(Path(params).resolve()) if params else None
    _, days, _ = _app_worker((app_module_path(app), py, symbol, cfg))
    hit = {pd.Timestamp(d).strftime("%Y-%m-%d") for d in days}
    return {d.strftime("%Y-%m-%d"): d.strftime("%Y-%m-%d") in hit for d in df.index}


def _verdicts(cfg: dict, card: dict, els: dict, df) -> dict[str, tuple]:
    """看图范围内(看图下界到训练段末日)逐日按固定回看判卡:{日期: (卡说, 理由)},判定不了的是 (None, 理由)。"""
    from chart_workflow.facts import compute_facts

    lo, hi = _view_range(cfg)
    out = {}
    for d in df.index[(df.index >= lo) & (df.index <= hi)]:
        day = d.strftime("%Y-%m-%d")
        try:
            facts = compute_facts(df, day, None, fcfg=cfg["facts"], features_cfg=cfg["features"],
                                  m_period=cfg["m_period"])
        except ValueError as e:
            out[day] = (None, f"事实表算不了({e})")
            continue
        out[day] = card_says(card, els, facts)
    return out


def _stock_job(job):
    """一只股票要补算的核对材料(多只时在子进程里跑):(代码, 读不了的原因 | None, 逐日卡说 | None, 规则信号 | None)。"""
    from chart_workflow.loader import read_bars

    cfg, symbol, card, els, rule, app, params, want_says, want_signal = job
    try:
        df = read_bars(cfg, symbol)
    except (ValueError, FileNotFoundError) as e:
        return symbol, str(e), None, None
    return (symbol, None, _verdicts(cfg, card, els, df) if want_says else None,
            _signal(cfg, rule, app, params, symbol, df) if want_signal else None)


def _run_jobs(jobs: list, cfg: dict) -> list:
    """多只时按 cfg["workers"] 开进程池(Linux 上默认 fork 方式启动子进程)。现在的入口(对照页命令、记账命令)
    走到核对这一步时都是单线程;以后要从多线程的进程(比如网页后端)调用,fork 有死锁风险,要改用 forkserver
    方式启动(ProcessPoolExecutor 的 mp_context)。"""
    workers = max(1, int(cfg.get("workers", 1)))
    if workers == 1 or len(jobs) < 2:
        return [_stock_job(j) for j in jobs]
    from concurrent.futures import ProcessPoolExecutor

    with ProcessPoolExecutor(max_workers=min(workers, len(jobs))) as ex:
        return list(ex.map(_stock_job, jobs))


def materials(cfg: dict, card: dict, els: dict, symbols: list[str], rule: str | None, app: str | None,
              params: str | None, *, says: bool = True) -> dict[str, tuple]:
    """每只股票的核对材料 {代码: (读不了的原因 | None, {日期: (卡说, 理由)} | None, {日期: 规则成立吗} | None)}。
    says=False 只要规则信号。进程内缓存:逐日卡说按(卡与要素、配置、这只股票的数据)记,规则文件的信号按(规则
    指纹、配置、这只股票的数据)记;app 方式的信号不缓存(app 代码不进指纹)。缺的才算,多只时按 cfg["workers"] 并行。"""
    from chart_workflow.rules import rule_identity

    ck = _digest(card, els, cfg)
    rk = _digest(rule_identity(rule, app, params), cfg) if rule else None    # app 代码不进指纹:信号不缓存
    out, have, jobs = {}, {}, []
    for s in symbols:
        try:
            stamp = _stamp(cfg, s)
        except (ValueError, FileNotFoundError) as e:
            out[s] = (str(e), None, None)
            continue
        keys = (("says", ck, s, stamp), ("signal", rk, s, stamp) if rk else None)
        have[s] = [keys, _CACHE.get(keys[0]) if says else None, _CACHE.get(keys[1]) if rk else None]
        want_says, want_signal = says and have[s][1] is None, have[s][2] is None
        if want_says or want_signal:
            jobs.append((cfg, s, card, els, rule, app, params, want_says, want_signal))
    for s, err, v, g in _run_jobs(jobs, cfg):
        if err is not None:
            out[s] = (err, None, None)
            del have[s]
            continue
        for k, x in ((1, v), (2, g)):
            if x is not None:
                have[s][k] = x
                if have[s][0][k - 1]:
                    _remember(have[s][0][k - 1], x)
    for s, (_, v, g) in have.items():
        out[s] = (None, v, g)
    return out


def _cases(card: dict, n: int, anns: dict) -> list[tuple]:
    """卡那一版及以前加进来的样本:[(样本, 标注 | None, 买点)]。"""
    return [(c, anns.get(c["ann_id"]), (c.get("buy_date") or {}).get("value"))
            for c in card.get("cases") or [] if c.get("version", 0) <= n]


def sample_stocks(card: dict, n: int, anns: dict) -> list[str]:
    """逐日核对要跑的样本股:卡那一版及以前的全部样本所在的股票,样本有没有被排除、跳过都算。"""
    return sorted({a["symbol"] for _, a, _ in _cases(card, n, anns) if a})


def pool_seed(cfg: dict) -> str:
    """抽股顺序的种子:账上登记的训练数据副本指纹(先核对本机副本就是登记的那一份)。"""
    from chart_workflow import snaplock
    from chart_workflow.config import dataset_dir
    from chart_workflow.state import locate

    snaplock.verify(dataset_dir(cfg))
    return snaplock.read_lock(locate())["current"]["sha"]


def pool_order(cfg: dict, seed: str, exclude) -> list[str]:
    """抽股顺序:训练副本的全部股票去掉 exclude(样本股),按 seed(账上登记的副本指纹,见 pool_seed)打乱。
    顺序全局固定,和卡的编号、版本都无关:所有卡都沿同一个顺序往下取,换编号、换版本挑不了股票。顺序事先算得
    出来,有人刻意照这批股票去凑过滤条件照样防不住——这一点接受:每次核对现抽一批,会变成「失败不记账、可以
    反复重抽」,更糟。"""
    from chart_workflow.securities import local_symbols

    skip = set(exclude)
    cands = [s for s in local_symbols(cfg) if s not in skip]
    random.Random(int.from_bytes(hashlib.sha256(seed.encode()).digest()[:8], "big")).shuffle(cands)
    return cands


def draw_pool(cfg: dict, card: dict, els: dict, seed: str, exclude, rule: str | None, app: str | None,
              params: str | None) -> dict:
    """沿抽股顺序往下取看图范围里有交易日的股票,直到「这一版卡在上面有卡成立日」的满 pool_positive_stocks
    只(默认 40),最多取 pool_max_stocks 只(默认 300;都待验证)。抽到的股票不论有没有卡成立日都进逐日比较。
    分批算(每批按目前有卡成立日的比例估还要几只),结果按顺序截到凑满的那一只,和分批方式、进程数无关。
    返回 {"stocks": [抽到的,按抽的顺序], "positive": [其中有卡成立日的], "mats": {代码: 核对材料},
    "seconds": 用时}。"""
    import math
    import time

    from chart_workflow.loader import trading_dates

    st = _settings(cfg)
    need, cap = int(st["pool_positive_stocks"]), int(st["pool_max_stocks"])
    workers = max(1, int(cfg.get("workers", 1)))
    lo, hi = _view_range(cfg)
    order = iter(pool_order(cfg, seed, exclude))
    drawn, positive, mats, t0 = [], [], {}, time.time()
    while len(positive) < need and len(drawn) < cap:
        want = need - len(positive)
        size = math.ceil(want * len(drawn) / len(positive)) if positive else want
        size = min(max(size, workers), cap - len(drawn))
        batch = []
        for s in order:
            try:
                d = trading_dates(cfg, s)
            except (ValueError, FileNotFoundError):
                continue
            if ((d >= lo) & (d <= hi)).any():
                batch.append(s)
                if len(batch) >= size:
                    break
        if not batch:
            break                                        # 股票池取完了
        got = materials(cfg, card, els, batch, rule, app, params)
        for s in batch:
            drawn.append(s)
            mats[s] = got[s]
            err, says, _ = got[s]
            if err is None and any(x is True for x, _ in says.values()):
                positive.append(s)
                if len(positive) >= need:
                    break
    return {"stocks": drawn, "positive": positive, "mats": mats, "seconds": time.time() - t0}


def check_samples(cfg: dict, card: dict, ver: dict, n: int, els: dict, anns: dict, mats: dict) -> dict:
    """卡的样本上,规则信号和「卡说成立」是否一致。卡按固定回看(买点前 default_lookback_bars 根,和逐日核对、
    规则同一个口径)判;另按用户框的窗口判一次,两者判得不同的样本单独列出(这张卡在固定回看下表达不了用户
    框选时的意思),不比、不算进能核对的个数。mats:样本股的规则信号(见 materials)。返回 {"checked",
    "positive": 买点当天卡成立的个数, "skipped": [原因], "unexpressible": [说明]};有不一致的、能核对的少于
    min_samples、或其中卡成立的少于 min_positive_samples → RuleShapeMismatch。"""
    from chart_workflow.facts import facts_for

    shape = f"{card['shape_id']}@v{n}"
    st = _settings(cfg)
    lookback = int(cfg["facts"]["default_lookback_bars"])
    bad, skipped, unexpressible, checked, positive = [], [], [], 0, 0
    for case, a, day in _cases(card, n, anns):
        tag = f"样本 {case['ann_id']}" + (f"({a['symbol']} 买点 {day})" if a else "")
        if a is None or not day:
            skipped.append(f"{tag}:找不到标注或买点")
            continue
        try:
            says, why = card_says(ver["card"], els, facts_for(cfg, a["symbol"], day, None))
            if says is None:
                skipped.append(f"{tag}:{why}")
                continue
            err, _, sig = mats[a["symbol"]]
            if err is not None:
                raise ValueError(err)
            got = sig.get(day)
            if got is None:
                raise ValueError(f"{day} 不是 {a['symbol']} 的交易日")
        except (ValueError, FileNotFoundError) as e:
            skipped.append(f"{tag}:{e}")
            continue
        if a.get("range_start"):
            try:
                boxed, _ = card_says(ver["card"], els, facts_for(cfg, a["symbol"], day, a["range_start"]))
            except (ValueError, FileNotFoundError):
                boxed = None
            if boxed is not None and boxed != says:
                unexpressible.append(f"{tag}:按你框的窗口(从 {a['range_start']} 起)卡{'成立' if boxed else '不成立'},"
                                     f"按固定回看(买点前 {lookback} 根)卡{'成立' if says else '不成立'}")
                continue
        checked += 1
        positive += says
        if got != says:
            bad.append(f"{tag}:卡说{'成立' if says else f'不成立({why})'},规则信号{'成立' if got else '不成立'}")
    if bad:
        raise RuleShapeMismatch(f"规则在形态卡 {shape} 的样本上和卡说的不一致:" + ";".join(bad))
    need = int(st["min_samples"])
    if checked < need:
        why = ""
        if unexpressible:
            why += (f";其中 {len(unexpressible)} 个样本按你框选的窗口和按固定回看判得不同——这张卡在固定回看下"
                    f"表达不了你框选时的意思,这些样本不拿来核对规则:" + ";".join(unexpressible))
        if skipped:
            why += ";跳过的:" + ";".join(skipped)
        raise RuleShapeMismatch(
            f"形态卡 {shape} 能核对的样本只有 {checked} 个,至少要 {need} 个(待验证),核对不了规则和卡是否一致{why}。"
            f"两条出路:先给卡加样本(add_case),或者这条规则不声明来自形态卡(来源写 user-text / mining 等)")
    need = int(st["min_positive_samples"])
    if positive < need:
        raise RuleShapeMismatch(
            f"形态卡 {shape} 能核对的 {checked} 个样本里,买点当天卡成立的只有 {positive} 个,至少要 {need} 个"
            f"(待验证):卡在你的买点上都不成立,永远不成立、或比卡窄的规则在这些样本上也全对,核对不出什么。"
            f"出路:先给卡加买点当天卡成立的样本,或者改卡让它在你的买点上成立,或者这条规则不声明来自形态卡")
    return {"checked": checked, "positive": positive, "skipped": skipped, "unexpressible": unexpressible}


def check_days(cfg: dict, card: dict, n: int, symbols: list[str], mats: dict, where: str) -> dict:
    """逐日核对:symbols(样本股加随机抽的股票)在看图范围内逐日比规则信号和「卡说成立」。where:报错里怎么称呼
    这批股票。返回 {"days", "negative", "positive", "unknown", "disagree": 个数, "examples": [前几个不一致的天],
    "unreadable": [读不了的股票]};不一致的比例超过容差、或卡判「不成立」的天少于 min_negative_days →
    RuleShapeMismatch。"""
    shape = f"{card['shape_id']}@v{n}"
    st = _settings(cfg)
    days, negative, unknown, bad, unreadable = 0, 0, 0, [], []
    for sym in symbols:
        err, says_by_day, got = mats[sym]
        if err is not None:
            unreadable.append(f"{sym}:{err}")
            continue
        for day, (says, why) in says_by_day.items():
            if says is None:
                unknown += 1
                continue
            days += 1
            negative += not says
            if got.get(day) != says:
                bad.append((sym, day, says, why, got.get(day)))
    positive = days - negative
    tol = float(st["max_disagree_share"])
    examples = [f"{s} {d}:卡说{'成立' if c else f'不成立({w})'},规则{'成立' if r else '不成立'}"
                for s, d, c, w, r in bad]
    if days and len(bad) / days > tol:
        raise RuleShapeMismatch(
            f"规则和形态卡 {shape} 在{where}看图范围内逐日比:卡能判定的 {days} 天里有 {len(bad)} 天不一致"
            f"(容差 {tol:.0%},待验证):" + ";".join(examples[:SHOW_DAYS])
            + (f";…共 {len(bad)} 天" if len(bad) > SHOW_DAYS else ""))
    need = int(st["min_negative_days"])
    if negative < need:
        raise RuleShapeMismatch(
            f"形态卡 {shape} 在{where}看图范围内卡判「不成立」的只有 {negative} 天(卡能判定 {days} 天),至少要 "
            f"{need} 天(待验证)才看得出规则是不是比卡宽(永远成立的规则在卡成立的日子上也全对)。"
            f"出路:给卡加别的股票、别的时段的样本,让核对的股票里有更多卡不成立的日子")
    return {"days": days, "negative": negative, "positive": positive, "unknown": unknown, "disagree": len(bad),
            "examples": examples[:SHOW_DAYS], "unreadable": unreadable}


def check_rule_against_shape(source: str, cfg: dict, *, rule: str | None = None, app: str | None = None,
                             params: str | None = None) -> dict:
    """来源是形态卡时的全部核对。返回要记进账本的 {"source", "declared", "facts_code", "samples_checked",
    "samples_positive", "samples_skipped", "samples_unexpressible", "sample_stocks", "pool_stocks",
    "pool_positive_stocks", "pool_order_seed", "stocks_unreadable", "days_checked", "days_negative",
    "days_positive", "days_unknown", "days_disagree", "disagree_examples"}(facts_code:判卡用的事实表代码版本;
    pool_order_seed:抽股顺序的种子,即账上登记的副本指纹);任何一项不过 → RuleShapeMismatch
    (日志校验不过 → ShapeValidationError;卡或版本不存在 → FileNotFoundError)。"""
    from chart_workflow.facts import FACTS_CODE
    from chart_workflow.shapes import _ann_index, checked_state

    if not (rule or app):
        raise RuleShapeMismatch("来源写的是形态卡,要给出规则(规则文件或 app)才能核对")
    m = SHAPE_SOURCE_RE.fullmatch(source)
    _, cards, els = checked_state()
    card = cards.get(m.group(1))
    if card is None:
        raise FileNotFoundError(f"形态卡不存在: {m.group(1)}")
    n = int(m.group(2))
    ver = next((v for v in card["versions"] if v["version"] == n), None)
    if ver is None:
        raise FileNotFoundError(f"形态卡 {m.group(1)} 没有版本 v{n}")
    shape = f"{card['shape_id']}@v{n}"
    custom = custom_triggers(ver["card"])
    if custom:
        raise RuleShapeMismatch(
            f"形态卡 {shape} 上的触发 {'、'.join(custom)} 是手写触发,没有能算的定义,核对不了规则哪天该成立。"
            f"两条出路:一是换成表里的触发(T1~T8),卡上的意思不变;二是在事实表加一行把它算出来"
            f"(先记一条提角度的日志 propose_fact,再照它写事实行)——加了之后这个触发要改写成卡上的要素,"
            f"卡的意思会从「几个触发里出现任一个就算」变成「这一项也必须满足」;想保住「任一个就算」的原意,"
            f"要在触发表里加一项,这需要改代码")
    declared = check_declaration(declared_implements(rule, app), ver, els, shape)
    anns = _ann_index()
    samples = sample_stocks(card, n, anns)
    res = check_samples(cfg, card, ver, n, els, anns,
                        materials(cfg, ver["card"], els, samples, rule, app, params, says=False))
    seed = pool_seed(cfg)
    pool = draw_pool(cfg, ver["card"], els, seed, samples, rule, app, params)
    need, cap = int(_settings(cfg)["pool_positive_stocks"]), int(_settings(cfg)["pool_max_stocks"])
    if len(pool["positive"]) < need:
        raise RuleShapeMismatch(
            f"形态卡 {shape} 的随机抽股:沿固定顺序抽了 {len(pool['stocks'])} 只(上限 {cap} 只),其中有卡成立日的"
            f"只有 {len(pool['positive'])} 只,至少要 {need} 只(待验证)。卡成立的日子太少,看不出规则是不是比卡窄。"
            f"出路:在配置 shape_check.pool_max_stocks 调高抽股上限——这次抽 {len(pool['stocks'])} 只用了 "
            f"{pool['seconds']:.0f} 秒,耗时大致随抽的只数等比例增加;或者放宽卡,让它在更多股票上成立")
    stocks = samples + pool["stocks"]
    daily = check_days(cfg, card, n, stocks, materials(cfg, ver["card"], els, stocks, rule, app, params),
                       f"样本股和随机抽的 {len(pool['stocks'])} 只股票" if pool["stocks"] else "样本股")
    return {"source": source, "declared": declared, "facts_code": FACTS_CODE, "samples_checked": res["checked"],
            "samples_positive": res["positive"], "samples_skipped": res["skipped"],
            "samples_unexpressible": res["unexpressible"], "sample_stocks": samples, "pool_stocks": pool["stocks"],
            "pool_positive_stocks": pool["positive"], "pool_order_seed": seed,
            "stocks_unreadable": daily["unreadable"], "days_checked": daily["days"], "days_negative": daily["negative"], "days_positive": daily["positive"],
            "days_unknown": daily["unknown"], "days_disagree": daily["disagree"], "disagree_examples": daily["examples"]}
