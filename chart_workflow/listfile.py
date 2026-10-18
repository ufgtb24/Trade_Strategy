"""清单文件(<root>/lists/<list_id>.json)的组装、校验与写入。

格式 schema = "chart_workflow.list/1",四种 kind(每条都带证券类别 sec_class / sec_source /
sec_label / sec_known,名录里查不到的 sec_label 为「未知（名录里查不到）」):
  bigmoves        大涨段清单,无 summary
  contrast        对照清单,有 summary
  contrast_blind  盲看清单,无 summary;marks 只有 decision / entry,metrics 只有 M
  card_hits       卡成立日清单(cardhits.py,只在调试模式下用),无 summary;图窗终点 view_end 就是成立日 t,
                  标完「是 / 不是」才露到 reveal_end;marks 只有 decision,metrics 为空,不带跨源比对

写入前校验(任一不过就拒绝写):list_id 合法;所有日期不晚于 train_end;
每个 view_end ≤ train_end;item_id 唯一;分组引用的 item 都存在;
盲看清单不含任何和结果有关的字段(包括逐段的跨源比对结果)。同名清单已存在就拒绝写
(FileExistsError):重新生成会覆盖旧清单,账本里的那一轮就对不上了。
调试模式(mode.py):清单带 mode = debug、标题加【调试】,清单名以 dbg- 开头,train_end 不晚于调试段终点;
正式模式拒绝带调试标记或 dbg- 开头的清单(正式清单不带 mode,格式不变)。

图窗(view_window)是 make_item 与「同股不互相露底」(drop_window_overlaps)共用的唯一口径:
同一只股票的两条,谁的决策日都不得落在另一条的完整图窗里(起点截到看图下界之后、到图窗终点),
否则打开一张图就露出另一条的决策日和后续走势。
"""
from __future__ import annotations

import json
import math
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import numpy as np
import pandas as pd

from chart_workflow import mode
from chart_workflow.config import root_dir
from chart_workflow.features import tags_of
from chart_workflow.panel import trading_dates
from chart_workflow.securities import CLASS_LABELS, classify_with_source, load_cached_names, load_exchanges

SCHEMA = "chart_workflow.list/1"
KINDS = ("bigmoves", "contrast", "contrast_blind", "card_hits")
LIST_ID_RE = re.compile(r"^(?!\.)(?!.*\.\.)[A-Za-z0-9_\-.]+$")   # 不以点开头、不含 ..
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
BLIND_MARKS = {"decision", "entry"}
BLIND_METRICS = {"M"}


class ListValidationError(ValueError):
    pass


def _d(x) -> str:
    return pd.Timestamp(x).strftime("%Y-%m-%d")


def _num(x, nd: int = 6):
    if x is None:
        return None
    x = float(x)
    return None if not math.isfinite(x) else round(x, nd)


def clean_json(obj):
    """NaN / inf → None,numpy 标量 → Python 标量(JSON 不认 NaN)。"""
    if isinstance(obj, dict):
        return {k: clean_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean_json(v) for v in obj]
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (float, np.floating)):
        return None if not math.isfinite(float(obj)) else float(obj)
    return obj


_EXCHANGES: dict[str, dict] = {}


def exchange_of(cfg: dict, symbol: str) -> str | None:
    """交易所(NASDAQ / NYSE / AMEX),证券名单缓存里没有就是 None。"""
    key = str(root_dir(cfg))
    if key not in _EXCHANGES:
        _EXCHANGES[key] = load_exchanges(cfg)
    return _EXCHANGES[key].get(symbol)


_NAMES: dict[str, dict] = {}


def security_fields(cfg: dict, symbol: str) -> dict:
    """证券类别四个字段(只读证券名录缓存,不联网):名录里查不到的标「未知（名录里查不到）」。"""
    key = str(root_dir(cfg))
    if key not in _NAMES:
        _NAMES[key] = load_cached_names(cfg)
    cls, src = classify_with_source(symbol, _NAMES[key].get(symbol))
    known = src != "code_rule"
    return {"sec_class": cls, "sec_source": src,
            "sec_label": CLASS_LABELS.get(cls, cls) if known else "未知（名录里查不到）",
            "sec_known": known}


def view_window(cfg: dict, symbol: str, t, blind: bool = False) -> tuple[pd.Timestamp, pd.Timestamp]:
    """一条的图窗 (起点, 终点):决策日往前 view.before_bars 个交易日,起点截到看图下界 view_floor
    (之后第一个交易日;view_floor 为空时不截),到 min(t+H, train_end);盲看截到 t + view.blind_after_bars。"""
    t = pd.Timestamp(t)
    dates = trading_dates(cfg, symbol)
    i = int(dates.searchsorted(t))
    before = cfg["view"]["before_bars"]
    after = cfg["view"]["blind_after_bars"] if blind else cfg["H"]
    view_start = dates[max(0, i - before)]
    floor = cfg.get("view_floor")
    if floor:
        view_start = max(view_start, dates[min(int(dates.searchsorted(pd.Timestamp(floor))), i)])
    view_end = min(dates[min(len(dates) - 1, i + after)], pd.Timestamp(cfg["train_end"]))
    return view_start, view_end


def drop_window_overlaps(df: pd.DataFrame, cfg: dict, blind: bool = False,
                         min_gap_bars: int = 0) -> pd.DataFrame:
    """同股不互相露底:按 df 的行序逐条贪心,一条只有在 ① 它的决策日不落在已取中的同股任一条的
    图窗里、② 已取中的同股任一条的决策日不落在它的图窗里、③ 与已取中的同股各条相隔超过
    min_gap_bars 个交易日时才取。df 要有 symbol / date 列;返回取中的行(保持原行序)。
    图窗与交易日序号只在同股已有取中的条目时才算(只出现一次的股票不读行情)。"""
    keep = []
    taken: dict[str, list[pd.Timestamp]] = {}
    cache: dict[tuple[str, pd.Timestamp], tuple[pd.Timestamp, pd.Timestamp, int]] = {}

    def geo(sym: str, t: pd.Timestamp) -> tuple[pd.Timestamp, pd.Timestamp, int]:
        if (sym, t) not in cache:
            s, e = view_window(cfg, sym, t, blind=blind)
            cache[(sym, t)] = (s, e, int(trading_dates(cfg, sym).searchsorted(t)))
        return cache[(sym, t)]

    for idx, sym, d in zip(df.index, df["symbol"].values, df["date"].values):
        t = pd.Timestamp(d)
        mine = taken.setdefault(sym, [])
        if mine:
            s, e, i = geo(sym, t)
            ok = True
            for t2 in mine:
                s2, e2, i2 = geo(sym, t2)
                if s2 <= t <= e2 or s <= t2 <= e or abs(i - i2) <= min_gap_bars:
                    ok = False
                    break
            if not ok:
                continue
        mine.append(t)
        keep.append(idx)
    return df.loc[keep]


def make_item(row, cfg: dict, blind: bool = False) -> dict:
    """面板里的一行 → 清单里的一条。图窗见 view_window。"""
    sym = row["symbol"]
    t = pd.Timestamp(row["date"])
    view_start, view_end = view_window(cfg, sym, t, blind=blind)
    item = {
        "item_id": f"{sym}@{_d(t)}",
        "symbol": sym,
        "exchange": exchange_of(cfg, sym),      # 只作信息保留,网页目前不用
        "t": _d(t),
        "entry_date": _d(row["entry_date"]),
        "view_start": _d(view_start),
        "view_end": _d(view_end),
        "tags": tags_of(bool(row["gap"]), str(row["vol_tag"] or "")),
        **security_fields(cfg, sym),            # 不含结果,盲看清单也写
    }
    if blind:
        item["marks"] = {"decision": _d(t), "entry": _d(row["entry_date"])}
        item["metrics"] = {"M": _num(row["M"])}
        return item
    item["marks"] = {"decision": _d(t), "entry": _d(row["entry_date"]),
                     "up_line": _num(row["U"], 4), "down_line": _num(row["D"], 4),
                     "peak_date": _d(row["peak_date"])}
    item["metrics"] = {"rel": _num(row["rel"], 4), "rise": _num(row["rise"], 4),
                       "M": _num(row["M"]), "dir": int(row["dir"]), "mag": _num(row["mag"], 4),
                       "dd": _num(row["dd"], 4), "dd250": _num(row["dd250"], 4),
                       "r60": _num(row["r60"], 4), "vol_mult": _num(row["vol_mult"], 3),
                       "max_jump": _num(row.get("max_jump"), 3)}
    return item


def new_list(list_id: str, kind: str, title: str, cfg: dict, params_extra: dict | None = None
             ) -> dict:
    pool = cfg["pool"]
    params = {"k": cfg["k"], "H": cfg["H"], "view_floor": cfg.get("view_floor"),
              "pool": {"price_max": pool["price_max"], "dv_min": pool["dv_min"],
                       "dv_max": pool["dv_max"], "m_min": pool["m_min"]}}
    params.update(params_extra or {})
    doc = {
        "schema": SCHEMA, "list_id": list_id, "kind": kind, "title": title,
        "created_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "train_start": cfg["train_start"], "train_end": cfg["train_end"],
        "params": params, "groups": [], "items": [],
    }
    if mode.is_debug():          # 调试模式的清单带标记,正式模式打不开;正式清单的格式不变
        doc["mode"] = mode.DEBUG
        doc["title"] = f"【调试】{title}"
    return doc


def _dates_in(obj, path: str = ""):
    """递归找出所有 YYYY-MM-DD 形式的字符串(只看 items 内部)。"""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _dates_in(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _dates_in(v, f"{path}[{i}]")
    elif isinstance(obj, str) and _DATE_RE.match(obj):
        yield path, obj


def validate(doc: dict) -> None:
    """不合格就抛 ListValidationError(列出所有问题)。"""
    errs: list[str] = []
    lid = doc.get("list_id", "")
    if not isinstance(lid, str) or not LIST_ID_RE.fullmatch(lid):
        errs.append(f"list_id 不合法: {lid!r}")
    else:
        try:
            mode.check_list_id(lid)
        except mode.ModeError as e:
            errs.append(str(e))
    foreign = mode.foreign_reason(doc, "清单")
    if foreign:
        errs.append(foreign)
    kind = doc.get("kind")
    if kind not in KINDS:
        errs.append(f"kind 不合法: {kind!r}")
    train_end = doc.get("train_end")
    if not isinstance(train_end, str) or not _DATE_RE.match(train_end):
        errs.append(f"train_end 不合法: {train_end!r}")
        raise ListValidationError("; ".join(errs))
    if mode.is_debug() and train_end > mode.DEBUG_END:
        errs.append(f"调试模式的清单 train_end={train_end} 晚于调试段终点 {mode.DEBUG_END}")
        train_end = mode.DEBUG_END
    items = doc.get("items") or []
    ids = [it.get("item_id") for it in items]
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup:
        errs.append(f"item_id 重复: {dup[:10]}")
    for it in items:
        for path, d in _dates_in(it, it.get("item_id", "?")):
            if d > train_end:
                errs.append(f"日期晚于训练段末日 {train_end}: {path}={d}")
        if str(it.get("view_end", "")) > train_end:
            errs.append(f"view_end 晚于训练段末日: {it.get('item_id')}")
    known = set(ids)
    for g in doc.get("groups") or []:
        missing = [i for i in g.get("item_ids", []) if i not in known]
        if missing:
            errs.append(f"分组 {g.get('key')} 引用了不存在的 item: {missing[:5]}")
    if kind == "contrast_blind":
        if "summary" in doc:
            errs.append("盲看清单不得含 summary")
        for it in items:
            extra_m = set(it.get("marks", {})) - BLIND_MARKS
            extra_x = set(it.get("metrics", {})) - BLIND_METRICS
            if extra_m or extra_x:
                errs.append(f"盲看清单含结果字段: {it.get('item_id')} "
                            f"{sorted(extra_m | extra_x)}")
            if "xcheck" in it:
                errs.append(f"盲看清单不得含跨源比对结果: {it.get('item_id')}")
    if kind == "bigmoves" and "summary" in doc:
        errs.append("大涨段清单不得含 summary")
    if kind == "card_hits":
        errs += _card_hits_errors(doc, train_end)
    if errs:
        raise ListValidationError("; ".join(errs[:20]))


def _card_hits_errors(doc: dict, train_end: str) -> list[str]:
    """卡成立日清单的额外校验:只在调试模式下写;每条的图窗终点就是成立日(标完之前不露后面的走势),
    露出终点 reveal_end 不早于成立日、不晚于训练段末日;不带任何和结果有关的字段。"""
    errs = []
    if not mode.is_debug():
        errs.append("卡成立日清单只在调试模式下用,正式模式不写")
    if "summary" in doc:
        errs.append("卡成立日清单不得含 summary")
    for it in doc.get("items") or []:
        tag = it.get("item_id")
        t, end, rev = it.get("t"), it.get("view_end"), it.get("reveal_end")
        if end != t:
            errs.append(f"卡成立日清单的图窗终点要是成立日: {tag} view_end={end!r} t={t!r}")
        if not (isinstance(rev, str) and _DATE_RE.match(rev) and str(t) <= rev <= train_end):
            errs.append(f"露出终点 reveal_end 要在成立日到训练段末日 {train_end} 之间: {tag} {rev!r}")
        if set(it.get("marks") or {}) - {"decision"} or it.get("metrics"):
            errs.append(f"卡成立日清单含结果字段: {tag}")
        if "xcheck" in it:
            errs.append(f"卡成立日清单不得含跨源比对结果: {tag}")
    return errs


def write_list(doc: dict, cfg: dict) -> Path:
    """校验后写入 <root>/lists/<list_id>.json(先写临时文件再改名)。同名清单已存在 → FileExistsError。"""
    doc = clean_json(doc)
    validate(doc)
    out_dir = root_dir(cfg) / "lists"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{doc['list_id']}.json"
    if path.exists():
        raise FileExistsError(f"清单 {doc['list_id']} 已存在:同名重新生成会覆盖旧清单、账本对不上,"
                              f"换一个清单名")
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=1))
    tmp.replace(path)
    return path


def deep_link(list_id: str, item_id: str | None = None, port: int | None = None) -> str:
    """path2_web 工作流模式的深链(前端端口取 configs/path2_web.yaml;调试模式取调试模式网页的前端端口)。"""
    if port is None:
        key = "debug_mode_frontend_port" if mode.is_debug() else "frontend_port"
        try:
            from path2_web.config import load_config as _web_cfg
            port = int(_web_cfg()[key])
        except Exception:      # noqa: BLE001
            port = 5181 if mode.is_debug() else 5173
    url = f"http://localhost:{port}/?wf={quote(list_id)}"
    return url + (f"&item={quote(item_id)}" if item_id else "")
