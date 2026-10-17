"""规则来自形态卡时的核对:规则声明的要素与角色要和卡那一版一致,规则在卡的样本上的信号要和卡上要素的
判定一致。对照页(contrast)在来源写 shape:<shape_id>@v<版本> 时开工前调用,不一致就拒绝;通过后把
规则声明的要素记进账本(rule_implements)。

声明:规则文件(--rule)或 app 模块(--app,即 path2_web 发现机制给出的那个模块)在模块顶层写
    IMPLEMENTS = {"E001": "must", "E002": "must_not", "E004": "bonus"}
即「这条规则实现了哪些要素、各是什么角色」(角色同形态卡:must / bonus / must_not)。要素编号可以写卡上
引用的编号,也可以写它合并后并入的编号(按合并后解析到的那条比)。

一致性核对(只在卡的样本图上做,不扫全市场):卡那一版及以前加进来的样本,在样本的买点那天按标注的框选
起点(没框选就用默认回看)算一次事实表,卡上必须有 / 有它就不买的要素按卡上记下的版本判定——全部必须有
都是「是」、全部有它就不买都是「否」就是「卡说成立」,否则「卡说不成立」;加分项不参与。规则在同一天的
信号要和它相同。有要素无法判定(待写代码、回看不够长)或那天读不到行情的样本跳过并列出原因;一个能核对的
样本都没有也拒绝(核对不了就不认这个来源)。规则信号:规则文件方式把行情截到买点当天再算 signal(df),
取最后一天;app 方式跑这只股票,看买点那天在不在命中里。
"""
from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path

from chart_workflow.ledger import SHAPE_SOURCE_RE

ROLES = ("must", "bonus", "must_not")
ROLE_TEXT = {"must": "必须有", "bonus": "加分", "must_not": "有它就不买"}


class RuleShapeMismatch(ValueError):
    """规则和它声明来自的形态卡对不上。"""


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


def _card_version(source: str) -> tuple[dict, dict, int]:
    from chart_workflow.shapes import load_card

    m = SHAPE_SOURCE_RE.fullmatch(source)
    card = load_card(m.group(1))
    n = int(m.group(2))
    ver = next((v for v in card["versions"] if v["version"] == n), None)
    if ver is None:
        raise FileNotFoundError(f"形态卡 {m.group(1)} 没有版本 v{n}")
    return card, ver, n


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


def _card_says(ings: list[dict], els: dict, facts: dict) -> tuple[bool | None, str]:
    from chart_workflow import elements as E

    ok = True
    for ing in ings:
        if ing.get("role") == "bonus" or not ing.get("element"):
            continue
        v, why = E.evaluate_element(els, ing["element"], facts, ing.get("element_version"))
        if v == "unknown":
            return None, f"{E.label(els, ing['element'])} 无法判定({why})"
        ok = ok and (v == "yes" if ing["role"] == "must" else v == "no")
    return ok, ""


def _rule_signal(cfg: dict, symbol: str, day: str, rule: str | None, app: str | None,
                 params: str | None, cache: dict) -> bool:
    import pandas as pd

    from chart_workflow.loader import read_bars
    from chart_workflow.rules import _app_worker, _signal_bool, app_module_path, load_rule

    if rule:
        df = read_bars(cfg, symbol, until=day)
        if len(df) == 0 or df.index[-1] != pd.Timestamp(day):
            raise ValueError(f"{day} 不是 {symbol} 的交易日")
        return bool(_signal_bool(load_rule(rule), df)[-1])
    if symbol not in cache:
        py = str(Path(params).resolve()) if params else None
        _, days, _ = _app_worker((app_module_path(app), py, symbol, cfg))
        cache[symbol] = {pd.Timestamp(d).strftime("%Y-%m-%d") for d in days}
    return day in cache[symbol]


def check_samples(cfg: dict, card: dict, ver: dict, n: int, els: dict, anns: dict, *,
                  rule: str | None, app: str | None, params: str | None) -> dict:
    """卡的样本图上,规则信号和卡上要素的判定是否一致。返回 {"checked": 个数, "skipped": [原因]};
    有不一致的、或一个能核对的都没有 → RuleShapeMismatch。"""
    from chart_workflow.facts import facts_for

    ings = ver["card"].get("ingredients", [])
    shape = f"{card['shape_id']}@v{n}"
    bad, skipped, checked, cache = [], [], 0, {}
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
            says, why = _card_says(ings, els, facts)
            if says is None:
                skipped.append(f"{tag}:{why}")
                continue
            sig = _rule_signal(cfg, a["symbol"], day, rule, app, params, cache)
        except (ValueError, FileNotFoundError) as e:
            skipped.append(f"{tag}:{e}")
            continue
        checked += 1
        if sig != says:
            bad.append(f"{tag}:卡上要素判定{'成立' if says else '不成立'},规则信号{'成立' if sig else '不成立'}")
    if bad:
        raise RuleShapeMismatch(f"规则在形态卡 {shape} 的样本上和卡上要素的判定不一致:" + ";".join(bad))
    if checked == 0:
        raise RuleShapeMismatch(f"形态卡 {shape} 没有能核对的样本,核对不了规则和卡是否一致"
                                + (":" + ";".join(skipped) if skipped else "(卡上没有样本)"))
    return {"checked": checked, "skipped": skipped}


def check_rule_against_shape(source: str, cfg: dict, *, rule: str | None = None, app: str | None = None,
                             params: str | None = None) -> dict:
    """来源是形态卡时的全部核对。返回要记进账本的 {"source", "declared": [...], "samples_checked",
    "samples_skipped"};任何一项不过 → RuleShapeMismatch(卡或版本不存在 → FileNotFoundError)。"""
    from chart_workflow import elements as E
    from chart_workflow.shapes import _ann_index

    card, ver, n = _card_version(source)
    els = E.load_all()
    declared = check_declaration(declared_implements(rule, app), ver, els, f"{card['shape_id']}@v{n}")
    res = check_samples(cfg, card, ver, n, els, _ann_index(), rule=rule, app=app, params=params)
    return {"source": source, "declared": declared, "samples_checked": res["checked"],
            "samples_skipped": res["skipped"]}
