"""看图工作流模式的路由:读清单、取截断后的 K 线、收标注批次。

纯投影层:只做「校验参数 → 调函数 → 序列化」,不含任何走势语义。
清单由命令行工具 chart_workflow 生成(<root>/lists/<list_id>.json,root 取 config 的 workflow 子树);
标注批次写到 chart_workflow 的状态根(<状态根>/annotations/<batch_id>.json,见 chart_workflow/state.py,
格式 chart_workflow.annotations/2:每条标注多个买点 buy_points,框选起止除「数据有误」外可空;批次头的
list_kind / outcome_visible 由这里读清单文件的 kind 填,不信前端),
打开清单时经 chart_workflow.views.record 记一条「看过」。K 线经 chart_workflow.loader 只读截断副本
(workflow.dataset_dir),不是副本就 503。

红线:训练段末日 train_end 之后的数据不出服务端——
  /workflow/ohlc       end 先截到 train_end
  /workflow/lists/{id} 读清单时兜底:view_end 截到 train_end,晚于它的日期标记一律删掉
  POST annotations     所有日期必须不晚于 train_end
本轮看图下界 view_floor(workflow 子树,默认 2025-01-01,待验证)之前的不给看——
  /workflow/lists      任何一条 view_start 早于下界的清单不列出
  /workflow/lists/{id} 这种清单 403
  /workflow/ohlc       start 先截到下界
  POST annotations     框选起止、买点都不得早于下界
拿不到状态根(StateRootMissing)时记不了「看过」:打开清单、发送标注一律 503,不给图;
/workflow/lists 照常列名字,但每项带 blocked = "state_root_missing" 与消息。
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

from chart_workflow import views
from chart_workflow.loader import NotASnapshot, load_bars
from chart_workflow.state import StateRootMissing, state_root
from path2_web.config import DEFAULT_CONFIG
from path2_web.data import serialize_ohlc, slice_window

_REPO_ROOT = Path(__file__).resolve().parents[1]

# 与 chart_workflow/listfile.py 的 LIST_ID_RE 同口径:字母数字 _ - .,不以点开头、不含 ..
_LIST_ID_RE = re.compile(r"^(?!\.)(?!.*\.\.)[A-Za-z0-9_\-.]+$")
_SYMBOL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.\-]{0,14}$")
_BATCH_RE = re.compile(r"^\d{8}T\d{6}(-\d+)?$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_LABELS = ("positive", "negative", "data_error")   # 正例 / 反例 / 数据有误
NOTE_MAX = 500
BUY_AFTER_MAX = 5          # 框选了起止时,买点最多落在形态结束后几个交易日内(待验证)
BUY_POINTS_MAX = 10        # 一张图最多几个买点(待验证)
BATCH_SCHEMA = "chart_workflow.annotations/2"


class BuyPointIn(BaseModel):
    date: str
    primary: bool = False


class AnnotationIn(BaseModel):
    ann_id: Optional[str] = None
    item_id: str
    symbol: str
    range_start: Optional[str] = None
    range_end: Optional[str] = None
    buy_points: list[BuyPointIn] = []
    buy_date: Optional[str] = None          # v1 兼容:有它且 buy_points 为空 → 转成一个主买点
    label: str
    note: str = ""
    peeked_before_buy: bool = False
    updated_at: Optional[str] = None


def _buy_points(ann: AnnotationIn) -> list[dict]:
    """买点规范化:v1 的 buy_date 转成一个主买点;都没标主买点时,日期最早的设为主买点。"""
    bps = [{"date": b.date, "primary": b.primary} for b in ann.buy_points]
    if not bps and ann.buy_date:
        bps = [{"date": ann.buy_date, "primary": True}]
    if bps and not any(b["primary"] for b in bps):
        min(bps, key=lambda b: b["date"])["primary"] = True
    return bps


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


def _view_floor(cfg: dict) -> str:
    return str(_wf_cfg(cfg)["view_floor"])


def _data_dir(cfg: dict) -> Path:
    p = Path(_wf_cfg(cfg)["dataset_dir"])
    return p if p.is_absolute() else _REPO_ROOT / p


def _state_root() -> Path:
    try:
        return state_root()
    except StateRootMissing as e:
        raise HTTPException(503, str(e)) from None


def _bars(cfg: dict, symbol: str, end: str) -> pd.DataFrame:
    """经 chart_workflow.loader 读截断副本:不是副本 → 503;没有这只股票 → 404。"""
    try:
        return load_bars(_data_dir(cfg), symbol, end)
    except NotASnapshot as e:
        raise HTTPException(503, str(e)) from None
    except FileNotFoundError:
        raise HTTPException(404, f"pkl not found: {symbol}") from None


def _before_floor(doc: dict, floor: str) -> bool:
    """清单里有没有图窗起点早于看图下界的条目。"""
    return any(not isinstance(it, dict) or str(it.get("view_start") or "") < floor
               for it in doc.get("items") or [])


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
        cfg = get_config()
        floor = _view_floor(cfg)
        try:
            state_root()
            blocked = None
        except StateRootMissing as e:
            blocked = str(e)
        d = _root(cfg) / "lists"
        out = []
        for p in sorted(d.glob("*.json")) if d.exists() else []:
            doc = _read_json(p)
            if not isinstance(doc, dict) or not _LIST_ID_RE.fullmatch(p.stem):
                continue
            if _before_floor(doc, floor):
                continue
            row = {"list_id": p.stem, "kind": doc.get("kind"), "title": doc.get("title"),
                   "created_at": doc.get("created_at"), "n_items": len(doc.get("items") or [])}
            if blocked:
                row["blocked"] = "state_root_missing"
                row["blocked_message"] = blocked
            out.append(row)
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
        floor = _view_floor(cfg)
        if _before_floor(doc, floor):
            raise HTTPException(403, f"这份清单的图窗早于本轮看图下界 {floor}，不能打开")
        kind = doc.get("kind")
        try:      # 记不了「看过」就不给图
            views.record(surface="web", event="open_list", outcome_visible=kind != "contrast_blind",
                         list_id=list_id, list_kind=kind, list_doc=doc)
        except StateRootMissing as e:
            raise HTTPException(503, str(e)) from None
        except OSError as e:
            raise HTTPException(503, f"看过记录写不进去:{e}") from None
        return clip_list(doc, _train_end(cfg))

    @router.get("/ohlc")
    def wf_ohlc(symbol: str, start: str, end: str):
        _check_symbol(symbol)
        if not (_is_date(start) and _is_date(end)):
            raise HTTPException(400, "start / end 必须是 YYYY-MM-DD")
        cfg = get_config()
        start = max(start, _view_floor(cfg))
        end = min(end, _train_end(cfg))
        win = slice_window(_bars(cfg, symbol, end), start, end)
        return serialize_ohlc(symbol, win)

    def _validate(ann: AnnotationIn, cfg: dict, dates_cache: dict) -> list[str]:
        errs = []
        tag = ann.item_id
        train_end = _train_end(cfg)
        floor = _view_floor(cfg)
        if not _SYMBOL_RE.fullmatch(ann.symbol or ""):
            return [f"{tag}: 非法代码 {ann.symbol!r}"]
        if ann.label not in _LABELS:
            errs.append(f"{tag}: label 必须是 positive / negative / data_error")
        if len(ann.note or "") > NOTE_MAX:
            errs.append(f"{tag}: 备注超过 {NOTE_MAX} 字")
        bps = _buy_points(ann)
        has_range = ann.range_start is not None or ann.range_end is not None
        if ann.label == "data_error" and not (ann.range_start and ann.range_end):
            errs.append(f"{tag}: 标「数据有误」要框选起止")
        elif has_range and not (ann.range_start and ann.range_end):
            errs.append(f"{tag}: 框选起止要成对")
        if ann.label == "positive" and not bps:
            errs.append(f"{tag}: 正例至少要一个买点")
        if len(bps) > BUY_POINTS_MAX:
            errs.append(f"{tag}: 买点最多 {BUY_POINTS_MAX} 个")
        dates = [b["date"] for b in bps]
        if len(set(dates)) != len(dates):
            errs.append(f"{tag}: 买点重复")
        if sum(b["primary"] for b in bps) > 1:
            errs.append(f"{tag}: 主买点至多一个")
        named = [("range_start", ann.range_start), ("range_end", ann.range_end)] if has_range else []
        named += [("买点", d) for d in dates]
        for name, v in named:
            if v is None:
                continue
            if not _is_date(v):
                errs.append(f"{tag}: {name} 不是日期 {v!r}")
            elif v > train_end:
                errs.append(f"{tag}: {name}={v} 晚于训练段末日 {train_end}")
            elif v < floor:
                errs.append(f"{tag}: {name}={v} 早于本轮看图下界 {floor}")
        if errs:
            return errs
        if not (ann.range_start and ann.range_end):
            return errs
        if ann.range_start > ann.range_end:
            return [f"{tag}: 起点晚于终点"]
        for d in dates:          # 框选了起止:每个买点须在框内或框后 BUY_AFTER_MAX 个交易日内
            if d < ann.range_start:
                errs.append(f"{tag}: 买点 {d} 早于形态起点")
            elif d > ann.range_end:
                if ann.symbol not in dates_cache:
                    try:
                        df = _bars(cfg, ann.symbol, train_end)
                    except HTTPException as e:
                        if e.status_code != 404:
                            raise
                        return errs + [f"{tag}: 找不到 {ann.symbol} 的行情"]
                    dates_cache[ann.symbol] = slice_window(df, "1900-01-01", train_end)["date"]
                ds = dates_cache[ann.symbol]
                n_after = int(((ds > pd.Timestamp(ann.range_end)) & (ds <= pd.Timestamp(d))).sum())
                if n_after > BUY_AFTER_MAX:
                    errs.append(f"{tag}: 买点 {d} 在形态结束后 {n_after} 个交易日,"
                                f"最多 {BUY_AFTER_MAX} 个")
        return errs

    @router.post("/annotations")
    def wf_post_annotations(req: AnnotationBatchIn):
        _check_list_id(req.list_id)
        cfg = get_config()
        root = _state_root()
        if not req.annotations:
            raise HTTPException(400, "没有可发送的标注")
        lst = _read_json(_root(cfg) / "lists" / f"{req.list_id}.json")
        if not isinstance(lst, dict):
            raise HTTPException(400, f"读不到清单 {req.list_id},批次头的清单种类无从填写")
        list_kind = lst.get("kind")
        errs: list[str] = []
        cache: dict = {}
        for a in req.annotations:
            errs += _validate(a, cfg, cache)
        if errs:
            raise HTTPException(400, "; ".join(errs[:20]))
        now = _now()
        out_dir = root / "annotations"
        out_dir.mkdir(parents=True, exist_ok=True)
        base = now.strftime("%Y%m%dT%H%M%S")
        batch_id, k = base, 1
        while (out_dir / f"{batch_id}.json").exists():
            k += 1
            batch_id = f"{base}-{k}"
        anns = []
        for a in req.annotations:
            d = a.model_dump(exclude={"buy_date", "buy_points"})
            d["buy_points"] = _buy_points(a)
            d["ann_id"] = d.get("ann_id") or str(uuid.uuid4())
            d["updated_at"] = d.get("updated_at") or now.strftime("%Y-%m-%dT%H:%M:%S")
            anns.append(d)
        doc = {
            "schema": BATCH_SCHEMA,
            "batch_id": batch_id,
            "created_at": now.strftime("%Y-%m-%dT%H:%M:%S"),
            "list_id": req.list_id,
            "list_kind": list_kind,
            "outcome_visible": list_kind != "contrast_blind",
            "train_end": _train_end(cfg),
            "annotations": anns,
        }
        path = out_dir / f"{batch_id}.json"
        path.write_text(json.dumps(doc, ensure_ascii=False, indent=1))
        return {"batch_id": batch_id, "path": str(path), "n": len(anns)}

    @router.get("/annotations")
    def wf_list_annotations():
        d = _state_root() / "annotations"
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
