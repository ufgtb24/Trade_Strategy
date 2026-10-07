"""看图工作流模式的路由:读清单、取截断后的 K 线、收标注批次。

纯投影层:只做读文件、按 train_end 截断、校验后写文件,不含任何走势语义。
清单由命令行工具 chart_workflow 生成(<root>/lists/<list_id>.json);标注批次由这里写到
<root>/annotations/<batch_id>.json。root / train_end 取 config 的 workflow 子树。

红线:训练段末日 train_end 之后的数据不出服务端——
  /workflow/ohlc       end 先截到 train_end
  /workflow/lists/{id} 读清单时兜底:view_end 截到 train_end,晚于它的日期标记一律删掉
  POST annotations     所有日期必须不晚于 train_end
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from path2_web.config import DEFAULT_CONFIG
from path2_web.data import serialize_ohlc, slice_window

_REPO_ROOT = Path(__file__).resolve().parents[1]

# 与 chart_workflow/listfile.py 的 LIST_ID_RE 同口径:字母数字 _ - .,不以点开头、不含 ..
_LIST_ID_RE = re.compile(r"^(?!\.)(?!.*\.\.)[A-Za-z0-9_\-.]+$")
_SYMBOL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.\-]{0,14}$")
_BATCH_RE = re.compile(r"^\d{8}T\d{6}(-\d+)?$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_LABELS = ("positive", "negative")
NOTE_MAX = 500
BUY_AFTER_MAX = 5          # 买点最多落在形态结束后几个交易日内(待验证)


class AnnotationIn(BaseModel):
    ann_id: Optional[str] = None
    item_id: str
    symbol: str
    range_start: str
    range_end: str
    buy_date: Optional[str] = None
    label: str
    note: str = ""
    updated_at: Optional[str] = None


class AnnotationBatchIn(BaseModel):
    list_id: str
    annotations: list[AnnotationIn]


def _now() -> datetime:
    """本地时间(独立成函数,测试里替换它来造 batch_id 冲突)。"""
    return datetime.now()


def _wf_cfg(cfg: dict) -> dict:
    return {**DEFAULT_CONFIG["workflow"], **(cfg.get("workflow") or {})}


def _root(cfg: dict) -> Path:
    p = Path(_wf_cfg(cfg)["root"])
    return p if p.is_absolute() else _REPO_ROOT / p


def _train_end(cfg: dict) -> str:
    return str(_wf_cfg(cfg)["train_end"])


def _check_list_id(list_id: str) -> None:
    if not list_id or not _LIST_ID_RE.fullmatch(list_id):
        raise HTTPException(400, f"非法清单名: {list_id!r}")


def _check_symbol(symbol: str) -> None:
    if not symbol or not _SYMBOL_RE.fullmatch(symbol):
        raise HTTPException(400, f"非法代码: {symbol!r}")


def _is_date(s) -> bool:
    if not isinstance(s, str) or not _DATE_RE.match(s):
        return False
    try:
        pd.Timestamp(s)
    except ValueError:
        return False
    return True


def clip_list(doc: dict, train_end: str) -> dict:
    """读清单时的截断兜底:view_end 截到 train_end;marks 里晚于 train_end 的日期标记删掉。"""
    for it in doc.get("items") or []:
        if isinstance(it.get("view_end"), str) and it["view_end"] > train_end:
            it["view_end"] = train_end
        marks = it.get("marks")
        if isinstance(marks, dict):
            it["marks"] = {k: v for k, v in marks.items()
                           if not (_is_date(v) and v > train_end)}
    return doc


def build_workflow_router(*, get_config) -> APIRouter:
    router = APIRouter(prefix="/workflow")

    def _read_json(path: Path) -> dict | None:
        try:
            return json.loads(path.read_text())
        except (OSError, ValueError):
            return None

    @router.get("/lists")
    def wf_lists():
        d = _root(get_config()) / "lists"
        out = []
        for p in sorted(d.glob("*.json")) if d.exists() else []:
            doc = _read_json(p)
            if not isinstance(doc, dict) or not _LIST_ID_RE.fullmatch(p.stem):
                continue
            out.append({"list_id": p.stem, "kind": doc.get("kind"), "title": doc.get("title"),
                        "created_at": doc.get("created_at"),
                        "n_items": len(doc.get("items") or [])})
        out.sort(key=lambda x: x["created_at"] or "", reverse=True)
        return out

    @router.get("/lists/{list_id}")
    def wf_list(list_id: str):
        _check_list_id(list_id)
        cfg = get_config()
        p = _root(cfg) / "lists" / f"{list_id}.json"
        if not p.exists():
            raise HTTPException(404, f"清单不存在: {list_id}")
        doc = _read_json(p)
        if not isinstance(doc, dict):
            raise HTTPException(500, f"清单文件损坏: {list_id}")
        return clip_list(doc, _train_end(cfg))

    @router.get("/ohlc")
    def wf_ohlc(symbol: str, start: str, end: str):
        _check_symbol(symbol)
        if not (_is_date(start) and _is_date(end)):
            raise HTTPException(400, "start / end 必须是 YYYY-MM-DD")
        cfg = get_config()
        end = min(end, _train_end(cfg))
        pkl = Path(cfg["dataset_dir"]) / f"{symbol}.pkl"
        if not pkl.exists():
            raise HTTPException(404, f"pkl not found: {symbol}")
        win = slice_window(pd.read_pickle(pkl), start, end)
        return serialize_ohlc(symbol, win)

    def _validate(ann: AnnotationIn, cfg: dict, dates_cache: dict) -> list[str]:
        errs = []
        tag = ann.item_id
        train_end = _train_end(cfg)
        if not _SYMBOL_RE.fullmatch(ann.symbol or ""):
            return [f"{tag}: 非法代码 {ann.symbol!r}"]
        for name in ("range_start", "range_end") + (("buy_date",) if ann.buy_date else ()):
            v = getattr(ann, name)
            if not _is_date(v):
                errs.append(f"{tag}: {name} 不是日期 {v!r}")
            elif v > train_end:
                errs.append(f"{tag}: {name}={v} 晚于训练段末日 {train_end}")
        if errs:
            return errs
        if ann.range_start > ann.range_end:
            errs.append(f"{tag}: 起点晚于终点")
        if ann.label not in _LABELS:
            errs.append(f"{tag}: label 必须是 positive / negative")
        if len(ann.note or "") > NOTE_MAX:
            errs.append(f"{tag}: 备注超过 {NOTE_MAX} 字")
        if ann.buy_date:
            if ann.buy_date < ann.range_start:
                errs.append(f"{tag}: 买点早于形态起点")
            elif ann.buy_date > ann.range_end:
                if ann.symbol not in dates_cache:
                    pkl = Path(cfg["dataset_dir"]) / f"{ann.symbol}.pkl"
                    if not pkl.exists():
                        return errs + [f"{tag}: 找不到 {ann.symbol} 的行情"]
                    dates_cache[ann.symbol] = slice_window(
                        pd.read_pickle(pkl), "1900-01-01", train_end)["date"]
                d = dates_cache[ann.symbol]
                n_after = int(((d > pd.Timestamp(ann.range_end))
                               & (d <= pd.Timestamp(ann.buy_date))).sum())
                if n_after > BUY_AFTER_MAX:
                    errs.append(f"{tag}: 买点在形态结束后 {n_after} 个交易日,"
                                f"最多 {BUY_AFTER_MAX} 个")
        return errs

    @router.post("/annotations")
    def wf_post_annotations(req: AnnotationBatchIn):
        _check_list_id(req.list_id)
        cfg = get_config()
        if not req.annotations:
            raise HTTPException(400, "没有可发送的标注")
        errs: list[str] = []
        cache: dict = {}
        for a in req.annotations:
            errs += _validate(a, cfg, cache)
        if errs:
            raise HTTPException(400, "; ".join(errs[:20]))
        now = _now()
        out_dir = _root(cfg) / "annotations"
        out_dir.mkdir(parents=True, exist_ok=True)
        base = now.strftime("%Y%m%dT%H%M%S")
        batch_id, k = base, 1
        while (out_dir / f"{batch_id}.json").exists():
            k += 1
            batch_id = f"{base}-{k}"
        anns = []
        for a in req.annotations:
            d = a.model_dump()
            d["ann_id"] = d.get("ann_id") or str(uuid.uuid4())
            d["updated_at"] = d.get("updated_at") or now.strftime("%Y-%m-%dT%H:%M:%S")
            anns.append(d)
        doc = {
            "schema": "chart_workflow.annotations/1",
            "batch_id": batch_id,
            "created_at": now.strftime("%Y-%m-%dT%H:%M:%S"),
            "list_id": req.list_id,
            "train_end": _train_end(cfg),
            "annotations": anns,
        }
        path = out_dir / f"{batch_id}.json"
        path.write_text(json.dumps(doc, ensure_ascii=False, indent=1))
        return {"batch_id": batch_id, "path": str(path), "n": len(anns)}

    @router.get("/annotations")
    def wf_list_annotations():
        d = _root(get_config()) / "annotations"
        out = []
        for p in sorted(d.glob("*.json")) if d.exists() else []:
            if not _BATCH_RE.fullmatch(p.stem):
                continue
            doc = _read_json(p)
            if not isinstance(doc, dict):
                continue
            out.append({"batch_id": p.stem, "list_id": doc.get("list_id"),
                        "n": len(doc.get("annotations") or []),
                        "created_at": doc.get("created_at")})
        out.sort(key=lambda x: (x["created_at"] or "", x["batch_id"]), reverse=True)
        return out

    return router
