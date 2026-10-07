"""清单文件(<root>/lists/<list_id>.json)的组装、校验与写入。

格式 schema = "chart_workflow.list/1",三种 kind:
  bigmoves        大涨段清单,无 summary
  contrast        对照清单,有 summary
  contrast_blind  盲看清单,无 summary;marks 只有 decision / entry,metrics 只有 M

写入前校验(任一不过就拒绝写):list_id 合法;所有日期不晚于 train_end;
每个 view_end ≤ train_end;item_id 唯一;分组引用的 item 都存在;
盲看清单不含任何和结果有关的字段。
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

from chart_workflow.config import root_dir
from chart_workflow.features import tags_of
from chart_workflow.panel import trading_dates

SCHEMA = "chart_workflow.list/1"
KINDS = ("bigmoves", "contrast", "contrast_blind")
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


def make_item(row, cfg: dict, blind: bool = False) -> dict:
    """面板里的一行 → 清单里的一条。图窗:决策日往前 view.before_bars 个交易日,
    到 min(t+H, train_end);盲看截到 t + view.blind_after_bars 为止。"""
    sym = row["symbol"]
    t = pd.Timestamp(row["date"])
    dates = trading_dates(cfg, sym)
    i = int(dates.searchsorted(t))
    before = cfg["view"]["before_bars"]
    after = cfg["view"]["blind_after_bars"] if blind else cfg["H"]
    view_start = dates[max(0, i - before)]
    view_end = min(dates[min(len(dates) - 1, i + after)], pd.Timestamp(cfg["train_end"]))
    item = {
        "item_id": f"{sym}@{_d(t)}",
        "symbol": sym,
        "t": _d(t),
        "entry_date": _d(row["entry_date"]),
        "view_start": _d(view_start),
        "view_end": _d(view_end),
        "tags": tags_of(bool(row["gap"]), str(row["vol_tag"] or "")),
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
                       "r60": _num(row["r60"], 4), "vol_mult": _num(row["vol_mult"], 3)}
    return item


def new_list(list_id: str, kind: str, title: str, cfg: dict, params_extra: dict | None = None
             ) -> dict:
    pool = cfg["pool"]
    params = {"k": cfg["k"], "H": cfg["H"],
              "pool": {"price_max": pool["price_max"], "dv_min": pool["dv_min"],
                       "dv_max": pool["dv_max"]}}
    params.update(params_extra or {})
    return {
        "schema": SCHEMA, "list_id": list_id, "kind": kind, "title": title,
        "created_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "train_start": cfg["train_start"], "train_end": cfg["train_end"],
        "params": params, "groups": [], "items": [],
    }


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
    kind = doc.get("kind")
    if kind not in KINDS:
        errs.append(f"kind 不合法: {kind!r}")
    train_end = doc.get("train_end")
    if not isinstance(train_end, str) or not _DATE_RE.match(train_end):
        errs.append(f"train_end 不合法: {train_end!r}")
        raise ListValidationError("; ".join(errs))
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
    if kind == "bigmoves" and "summary" in doc:
        errs.append("大涨段清单不得含 summary")
    if errs:
        raise ListValidationError("; ".join(errs[:20]))


def write_list(doc: dict, cfg: dict) -> Path:
    """校验后写入 <root>/lists/<list_id>.json(先写临时文件再改名)。"""
    doc = clean_json(doc)
    validate(doc)
    out_dir = root_dir(cfg) / "lists"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{doc['list_id']}.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=1))
    tmp.replace(path)
    return path


def deep_link(list_id: str, item_id: str | None = None, port: int | None = None) -> str:
    """path2_web 工作流模式的深链(前端端口取 configs/path2_web.yaml)。"""
    if port is None:
        try:
            from path2_web.config import load_config as _web_cfg
            port = int(_web_cfg()["frontend_port"])
        except Exception:      # noqa: BLE001
            port = 5173
    url = f"http://localhost:{port}/?wf={quote(list_id)}"
    return url + (f"&item={quote(item_id)}" if item_id else "")
