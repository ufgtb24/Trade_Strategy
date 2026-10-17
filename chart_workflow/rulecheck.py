"""规则来自形态卡时的核对:规则声明的要素与角色要和卡那一版一致;卡的样本上、以及样本股看图范围内的每一天,
规则信号都要和「卡说成立」一致。对照页(contrast)在来源写 shape:<shape_id>@v<版本> 时开工前调用,账本记账时
再由账本自己调一次(不收调用方传来的核对结果);任一不过就拒绝,通过后把声明与核对结果记进账本(rule_implements)。

声明:规则文件(--rule)或 app 模块(--app,即 path2_web 发现机制给出的那个模块)在模块顶层写
    IMPLEMENTS = {"E001": "must", "E002": "must_not", "E004": "bonus"}
即「这条规则实现了哪些要素、各是什么角色」(角色同形态卡:must / bonus / must_not)。要素编号可以写卡上
引用的编号,也可以写它合并后并入的编号(按合并后解析到的那条比)。

「卡说成立」(一天、一只股票的事实表上):卡上必须有的要素全是「是」、有它就不买的全是「否」(按卡上记下的
要素版本判;加分项不参与);卡上有触发时,还要当天出现卡上的某个触发(T1~T8 由事实表判;只剩手写触发时
判定不了)。有要素无法判定(待写代码、回看不够长)或触发判定不了 → 这一天卡判定不了,不比。

两道核对(只比规则和卡是否一致,不碰任何前瞻收益):
  样本:卡那一版及以前加进来的样本,在样本的买点那天按标注的框选起点算事实表,规则信号要和「卡说成立」相同。
        判定不了或读不到行情的样本跳过并列出原因;能核对的样本少于 shape_check.min_samples(默认 3,待验证)
        就拒绝,报错里给两条出路:先给卡加样本,或者这条规则不声明来自形态卡。
  逐日(反例):每只能核对的样本股,在看图范围内(不早于看图下界、不晚于训练段末日)逐日按默认回看算事实表,
        卡能判定的每一天,规则信号都要和「卡说成立」一致;不一致的天数占卡能判定天数的比例超过
        shape_check.max_disagree_share(默认 0,即必须全部一致,待验证)就拒绝,列出不一致的天。
        永远成立、或明显比卡宽的规则在卡说不成立的日子上就过不了。
规则信号:规则文件方式在这只股票截到训练段末日的行情上算一次 signal(df),逐日读;app 方式跑这只股票,
看那天在不在命中里。卡与要素从操作日志重算(先重走全部日志的校验),不读磁盘上的卡与要素文件。
"""
from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path

from chart_workflow.ledger import SHAPE_SOURCE_RE

ROLES = ("must", "bonus", "must_not")
ROLE_TEXT = {"must": "必须有", "bonus": "加分", "must_not": "有它就不买"}
DEFAULTS = {"min_samples": 3, "max_disagree_share": 0.0}     # 与 config 的 shape_check 同值,都待验证
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
    """一天的事实表上「卡说成立」吗(见模块说明):(True / False / None = 判定不了, 判定不了的理由)。"""
    from chart_workflow import elements as E

    ok = True
    for ing in card.get("ingredients", []):
        if ing.get("role") == "bonus" or not ing.get("element"):
            continue
        v, why = E.evaluate_element(els, ing["element"], facts, ing.get("element_version"))
        if v == "unknown":
            return None, f"{E.label(els, ing['element'])} 无法判定({why})"
        ok = ok and (v == "yes" if ing["role"] == "must" else v == "no")
    terms = [t.get("term") for t in card.get("triggers", [])]
    if not ok or not terms:
        return ok, ""
    today = {t.get("tid") for t in facts.get("triggers") or []}
    if any(t in today for t in terms if t != "custom"):
        return True, ""
    if "custom" in terms:
        return None, "卡上表里的触发当天都没出现,手写触发判定不了"
    return False, ""


class _Signals:
    """规则在一只股票上的信号:规则文件方式逐股算一次 signal(df),app 方式逐股跑一次 app。"""

    def __init__(self, cfg: dict, rule: str | None, app: str | None, params: str | None):
        self.cfg, self.rule, self.app, self.params = cfg, rule, app, params
        self._fn = None
        self._cache: dict[str, dict[str, bool] | set] = {}

    def on(self, symbol: str, df) -> dict[str, bool]:
        """{日期: 这天成立吗};df 是截到训练段末日的行情(规则文件方式用)。"""
        import pandas as pd

        from chart_workflow.rules import _app_worker, _signal_bool, app_module_path, load_rule

        if symbol not in self._cache:
            if self.rule:
                self._fn = self._fn or load_rule(self.rule)
                sig = _signal_bool(self._fn, df)
                self._cache[symbol] = {d.strftime("%Y-%m-%d"): bool(x) for d, x in zip(df.index, sig)}
            else:
                py = str(Path(self.params).resolve()) if self.params else None
                _, days, _ = _app_worker((app_module_path(self.app), py, symbol, self.cfg))
                hit = {pd.Timestamp(d).strftime("%Y-%m-%d") for d in days}
                self._cache[symbol] = {d.strftime("%Y-%m-%d"): d.strftime("%Y-%m-%d") in hit for d in df.index}
        return self._cache[symbol]


def _bars(cfg: dict, symbol: str, cache: dict):
    from chart_workflow.loader import read_bars

    if symbol not in cache:
        cache[symbol] = read_bars(cfg, symbol)
    return cache[symbol]


def check_samples(cfg: dict, card: dict, ver: dict, n: int, els: dict, anns: dict, sig: _Signals,
                  bars: dict) -> dict:
    """卡的样本图上,规则信号和「卡说成立」是否一致。返回 {"checked", "skipped": [原因], "symbols": [能核对的股票]};
    有不一致的、或能核对的少于最少个数 → RuleShapeMismatch。"""
    from chart_workflow.facts import facts_for

    shape = f"{card['shape_id']}@v{n}"
    need = int(_settings(cfg)["min_samples"])
    bad, skipped, checked, symbols = [], [], 0, set()
    for case in card.get("cases") or []:
        if case.get("version", 0) > n:
            continue
        a = anns.get(case["ann_id"])
        day = (case.get("buy_date") or {}).get("value")
        tag = f"样本 {case['ann_id']}" + (f"({a['symbol']} 买点 {day})" if a else "")
        if a is None or not day:
            skipped.append(f"{tag}:找不到标注或买点")
            continue
        try:
            facts = facts_for(cfg, a["symbol"], day, a.get("range_start"))
            says, why = card_says(ver["card"], els, facts)
            if says is None:
                skipped.append(f"{tag}:{why}")
                continue
            got = sig.on(a["symbol"], _bars(cfg, a["symbol"], bars)).get(day)
            if got is None:
                raise ValueError(f"{day} 不是 {a['symbol']} 的交易日")
        except (ValueError, FileNotFoundError) as e:
            skipped.append(f"{tag}:{e}")
            continue
        checked += 1
        symbols.add(a["symbol"])
        if got != says:
            bad.append(f"{tag}:卡说{'成立' if says else '不成立'},规则信号{'成立' if got else '不成立'}")
    if bad:
        raise RuleShapeMismatch(f"规则在形态卡 {shape} 的样本上和卡说的不一致:" + ";".join(bad))
    if checked < need:
        why = (";跳过的:" + ";".join(skipped)) if skipped else ""
        raise RuleShapeMismatch(
            f"形态卡 {shape} 能核对的样本只有 {checked} 个,至少要 {need} 个(待验证),核对不了规则和卡是否一致{why}。"
            f"两条出路:先给卡加样本(add_case),或者这条规则不声明来自形态卡(来源写 user-text / mining 等)")
    return {"checked": checked, "skipped": skipped, "symbols": sorted(symbols)}


def check_days(cfg: dict, card: dict, ver: dict, n: int, els: dict, symbols: list[str], sig: _Signals,
               bars: dict) -> dict:
    """反例核对:每只样本股在看图范围内逐日比规则信号和「卡说成立」。返回 {"days", "unknown", "disagree": 个数,
    "examples": [前几个不一致的天]};不一致的比例超过容差、或卡一天都判定不了 → RuleShapeMismatch。"""
    import pandas as pd

    from chart_workflow.facts import compute_facts

    shape = f"{card['shape_id']}@v{n}"
    lo, hi = pd.Timestamp(cfg.get("view_floor") or cfg["train_start"]), pd.Timestamp(cfg["train_end"])
    days, unknown, bad = 0, 0, []
    for sym in symbols:
        df = _bars(cfg, sym, bars)
        got = sig.on(sym, df)
        for d in df.index[(df.index >= lo) & (df.index <= hi)]:
            day = d.strftime("%Y-%m-%d")
            try:
                facts = compute_facts(df, day, None, fcfg=cfg["facts"], features_cfg=cfg["features"],
                                      m_period=cfg["m_period"])
            except ValueError:
                unknown += 1
                continue
            says, _ = card_says(ver["card"], els, facts)
            if says is None:
                unknown += 1
                continue
            days += 1
            if got.get(day) != says:
                bad.append((sym, day, says, got.get(day)))
    if days == 0:
        raise RuleShapeMismatch(f"形态卡 {shape} 在样本股的看图范围内一天都判定不了,核对不了规则和卡是否一致")
    share = len(bad) / days
    tol = float(_settings(cfg)["max_disagree_share"])
    examples = [f"{s} {d}:卡说{'成立' if c else '不成立'},规则{'成立' if r else '不成立'}" for s, d, c, r in bad]
    if share > tol:
        raise RuleShapeMismatch(
            f"规则和形态卡 {shape} 在样本股看图范围内逐日比:卡能判定的 {days} 天里有 {len(bad)} 天不一致"
            f"(容差 {tol:.0%},待验证):" + ";".join(examples[:SHOW_DAYS])
            + (f";…共 {len(bad)} 天" if len(bad) > SHOW_DAYS else ""))
    return {"days": days, "unknown": unknown, "disagree": len(bad), "examples": examples[:SHOW_DAYS]}


def check_rule_against_shape(source: str, cfg: dict, *, rule: str | None = None, app: str | None = None,
                             params: str | None = None) -> dict:
    """来源是形态卡时的全部核对。返回要记进账本的 {"source", "declared", "samples_checked", "samples_skipped",
    "days_checked", "days_unknown", "days_disagree", "disagree_examples"};任何一项不过 → RuleShapeMismatch
    (日志校验不过 → ShapeValidationError;卡或版本不存在 → FileNotFoundError)。"""
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
    declared = check_declaration(declared_implements(rule, app), ver, els, f"{card['shape_id']}@v{n}")
    sig, bars = _Signals(cfg, rule, app, params), {}
    res = check_samples(cfg, card, ver, n, els, _ann_index(), sig, bars)
    daily = check_days(cfg, card, ver, n, els, res["symbols"], sig, bars)
    return {"source": source, "declared": declared, "samples_checked": res["checked"],
            "samples_skipped": res["skipped"], "days_checked": daily["days"], "days_unknown": daily["unknown"],
            "days_disagree": daily["disagree"], "disagree_examples": daily["examples"]}
