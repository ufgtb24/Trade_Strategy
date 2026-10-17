"""看图工作流模式的路由:读清单、取截断后的 K 线、收标注批次。

纯投影层:只做「校验参数 → 调函数 → 序列化」,不含任何走势语义。
清单由命令行工具 chart_workflow 生成(<root>/lists/<list_id>.json,root 取 config 的 workflow 子树);
标注批次写到 chart_workflow 的状态根(<状态根>/annotations/<batch_id>.json,见 chart_workflow/state.py,
格式 chart_workflow.annotations/2:每条标注多个买点 buy_points,框选起止除「数据有误」外可空;
大涨段清单的改点痕迹 first_buy_points(第一次露出结果时的买点)与 changed_after_reveal(露出结果后
买点改过或清除过);批次头的 list_kind / outcome_visible 由这里读清单文件的 kind 填,不信前端),
打开清单时经 chart_workflow.views.record 记一条「看过」;单张图的事件(放大看了、点了买点或选了判定、
大涨段第一次露出结果、点买点前往右拖看后续)经 POST /workflow/views 再各记一条。K 线经 chart_workflow.loader 只读截断副本
(workflow.dataset_dir),不是副本就 503。

改点痕迹以服务端为准:大涨段批次收进来时,查每张图以前有没有记过 reveal(跨刷新、跨页面会话、跨天,
按 item_id 跨清单查),有就以最早那次的买点为准——first_buy_points 用记录里的值;提交的
first_buy_points 缺失或跟它不一样、或最后的买点跟它不一样,changed_after_reveal 一律置 true。
前端传来的这两个值不作数(只会被并成 true,不会被采信成 false)。peeked_before_buy 同样以服务端为准:
第一次露出结果之前(没露出过 = 到现在)记过这张图的 peek 就置 true。
大涨段标注还由服务端填 outcome_seen_elsewhere:这一条决策日之后的走势在第一次露出结果之前是否已经在别处
露出过,分「仔细看过」与「只在清单里出现过」两级(见 chart_workflow.views.outcome_trail);前端的值不作数,
别的清单种类填 null。大涨段的每条标注都必须是这份清单里的条目。

红线:训练段末日 train_end 之后的数据不出服务端(train_end 先和 loader.HARD_END 取小,配置写成
2026 年也不越过 2025-12-31)——
  /workflow/ohlc       end 先截到 train_end;只给本进程打开过的清单里的图窗(先打开清单才会记「看过」)
  /workflow/lists/{id} 读清单时兜底:view_end 截到 train_end,晚于它的日期标记一律删掉
  POST annotations     所有日期必须不晚于 train_end
本轮看图下界 view_floor(workflow 子树,默认 2025-01-01,待验证)之前的不给看——
  /workflow/lists      任何一条 view_start 早于下界的清单不列出
  /workflow/lists/{id} 这种清单 403
  /workflow/ohlc       start 先截到下界
  POST annotations     框选起止、买点都不得早于下界
拿不到状态根(StateRootMissing,含水位核对不过的 StateRootRegressed)时记不了「看过」:打开清单、
发送标注一律 503,不给图;/workflow/lists 照常列名字,但每项带 blocked = "state_root_missing" 与消息。
/workflow/state 只读地报告状态根在哪、是不是来自环境变量(端到端测试开跑前核对,界面据此显示提示条;
只核对、不写水位,见 chart_workflow.state.check_root)。
"""
from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, StrictBool

from chart_workflow import state as cw_state
from chart_workflow import views
from chart_workflow.loader import HARD_END, NotASnapshot, check_symbol, load_bars
from chart_workflow.state import StateRootMissing, state_root
from path2_web.config import DEFAULT_CONFIG
from path2_web.data import serialize_ohlc, slice_window

_REPO_ROOT = Path(__file__).resolve().parents[1]

# 与 chart_workflow/listfile.py 的 LIST_ID_RE 同口径:字母数字 _ - .,不以点开头、不含 ..
_LIST_ID_RE = re.compile(r"^(?!\.)(?!.*\.\.)[A-Za-z0-9_\-.]+$")
_BATCH_RE = re.compile(r"^\d{8}T\d{6}(-\d+)?$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_LABELS = ("positive", "negative", "data_error")   # 正例 / 反例 / 数据有误
NOTE_MAX = 500
BUY_AFTER_MAX = 5          # 框选了起止时,买点最多落在形态结束后几个交易日内(待验证)
BUY_POINTS_MAX = 10        # 一张图最多几个买点(待验证)
BATCH_SCHEMA = "chart_workflow.annotations/2"


class BuyPointIn(BaseModel):
    date: str
    primary: StrictBool = False


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
    peeked_before_buy: StrictBool = False
    # 大涨段清单的改点痕迹:第一次露出结果时的买点(null = 没露出过),露出后买点改过或清除过
    first_buy_points: Optional[list[BuyPointIn]] = None
    changed_after_reveal: StrictBool = False
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


class ChartViewIn(BaseModel):
    """看图工作流里的单张图事件:zoom = 放大看了;annotate = 点了买点或选了判定;
    reveal = 大涨段第一次露出结果(带当时的买点);peek = 大涨段点买点前往右拖看了后续。"""
    list_id: str
    item_id: str
    event: str
    buy_points: Optional[list[BuyPointIn]] = None


_CHART_EVENTS = {"zoom": "zoom_chart", "annotate": "annotate_chart", "reveal": "reveal",
                 "peek": "peek_chart"}


def _bp_key(bps) -> set[tuple[str, bool]]:
    return {(b["date"], bool(b["primary"])) for b in bps or []}


def _now() -> datetime:
    """本地时间(独立成函数,测试里替换它来造 batch_id 冲突)。"""
    return datetime.now()


def _wf_cfg(cfg: dict) -> dict:
    return {**DEFAULT_CONFIG["workflow"], **(cfg.get("workflow") or {})}


def _root(cfg: dict) -> Path:
    p = Path(_wf_cfg(cfg)["root"])
    return p if p.is_absolute() else _REPO_ROOT / p


def _train_end(cfg: dict) -> str:
    """训练段末日:配置值和 HARD_END 取小(配置写成 2026 年也不越过硬上限)。"""
    return min(str(_wf_cfg(cfg)["train_end"]), HARD_END)


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
    """经 chart_workflow.loader 读截断副本:不是副本、与账上登记的副本不是同一份(或主目录的账还没登记)
    → 503;没有这只股票 → 404。"""
    try:
        return load_bars(_data_dir(cfg), symbol, end)
    except (NotASnapshot, StateRootMissing) as e:
        raise HTTPException(503, str(e)) from None
    except FileNotFoundError:
        raise HTTPException(404, f"pkl not found: {symbol}") from None
    except ValueError as e:                  # 代码名不合格(loader.check_symbol)
        raise HTTPException(400, str(e)) from None


def _before_floor(doc: dict, floor: str) -> bool:
    """清单里有没有图窗起点早于看图下界的条目。"""
    return any(not isinstance(it, dict) or str(it.get("view_start") or "") < floor
               for it in doc.get("items") or [])


def _check_list_id(list_id: str) -> None:
    if not list_id or not _LIST_ID_RE.fullmatch(list_id):
        raise HTTPException(400, f"非法清单名: {list_id!r}")


def _check_symbol(symbol: str) -> None:
    try:
        check_symbol(symbol)
    except ValueError:
        raise HTTPException(400, f"非法代码: {symbol!r}") from None


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


def _validate_bps(bps: list[dict], tag: str, name: str) -> list[str]:
    errs = []
    if len(bps) > BUY_POINTS_MAX:
        errs.append(f"{tag}: {name}最多 {BUY_POINTS_MAX} 个")
    dates = [b["date"] for b in bps]
    if len(set(dates)) != len(dates):
        errs.append(f"{tag}: {name}重复")
    if sum(b["primary"] for b in bps) > 1:
        errs.append(f"{tag}: {name}里主买点至多一个")
    return errs


def build_workflow_router(*, get_config) -> APIRouter:
    router = APIRouter(prefix="/workflow")
    # 本进程打开过的清单里的图窗:symbol → [(起点, 终点)](已截到看图下界与训练段末日)。
    # /workflow/ohlc 只给落在其中某个图窗里的请求,绕开「打开清单」(不记看过)就取不到 K 线。
    opened: dict[str, set[tuple[str, str]]] = {}

    def _read_json(path: Path) -> dict | None:
        try:
            return json.loads(path.read_text())
        except (OSError, ValueError):
            return None

    @router.get("/state")
    def wf_state():
        """状态根在哪、是不是来自环境变量、能不能用(只读,不建任何东西)。"""
        from_env = bool(os.environ.get(cw_state.ENV_VAR))
        try:
            path = str(cw_state.locate())
        except StateRootMissing as e:
            return {"path": None, "from_env": from_env, "env_var": cw_state.ENV_VAR,
                    "ok": False, "message": str(e)}
        try:
            cw_state.check_root()                   # 只核对,不写水位
            ok, msg = True, None
        except StateRootMissing as e:
            ok, msg = False, str(e)
        return {"path": path, "from_env": from_env, "env_var": cw_state.ENV_VAR,
                "ok": ok, "message": msg}

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
        doc = clip_list(doc, _train_end(cfg))
        for it in doc.get("items") or []:
            sym, vs, ve = it.get("symbol"), it.get("view_start"), it.get("view_end")
            if isinstance(sym, str) and _is_date(vs) and _is_date(ve):
                opened.setdefault(sym, set()).add((max(vs, floor), ve))
        return doc

    @router.post("/views")
    def wf_chart_view(req: ChartViewIn):
        """记一条单张图事件(看过记录);图窗取清单里这一条的(截到看图下界与训练段末日)。"""
        _check_list_id(req.list_id)
        event = _CHART_EVENTS.get(req.event)
        if event is None:
            raise HTTPException(400, f"event 只能是 {'/'.join(_CHART_EVENTS)}")
        cfg = get_config()
        p = _root(cfg) / "lists" / f"{req.list_id}.json"
        if not p.exists():
            raise HTTPException(404, f"清单不存在: {req.list_id}")
        doc = _read_json(p)
        if not isinstance(doc, dict):
            raise HTTPException(500, f"清单文件损坏: {req.list_id}")
        floor, train_end = _view_floor(cfg), _train_end(cfg)
        if _before_floor(doc, floor):
            raise HTTPException(403, f"这份清单的图窗早于本轮看图下界 {floor}，不能打开")
        doc = clip_list(doc, train_end)
        it = next((x for x in doc.get("items") or [] if x.get("item_id") == req.item_id), None)
        if it is None:
            raise HTTPException(404, f"清单 {req.list_id} 里没有 {req.item_id}")
        bps = None
        if event == "reveal":
            bps = [{"date": b.date, "primary": b.primary} for b in req.buy_points or []]
            errs = [] if bps else ["reveal 必须带露出结果那一刻的买点"]
            errs += _validate_bps(bps, req.item_id, "买点")
            for b in bps:
                if not _is_date(b["date"]) or b["date"] < floor or b["date"] > train_end:
                    errs.append(f"买点 {b['date']!r} 不是日期或越过了本轮看图范围 {floor}~{train_end}")
            if errs:
                raise HTTPException(400, "; ".join(errs))
        elif req.buy_points is not None:
            raise HTTPException(400, "只有 reveal 才带买点")
        kind = doc.get("kind")
        try:
            row = views.record(surface="web", event=event, outcome_visible=kind != "contrast_blind",
                               list_id=req.list_id, list_kind=kind, item_id=req.item_id,
                               charts=[{"symbol": it.get("symbol"),
                                        "start": max(str(it.get("view_start")), floor),
                                        "end": str(it.get("view_end"))}],
                               buy_points=bps)
        except StateRootMissing as e:
            raise HTTPException(503, str(e)) from None
        except ValueError as e:
            raise HTTPException(400, str(e)) from None
        except OSError as e:
            raise HTTPException(503, f"看过记录写不进去:{e}") from None
        return {"ok": True, "ts": row["ts"]}

    @router.get("/ohlc")
    def wf_ohlc(symbol: str, start: str, end: str):
        _check_symbol(symbol)
        if not (_is_date(start) and _is_date(end)):
            raise HTTPException(400, "start / end 必须是 YYYY-MM-DD")
        cfg = get_config()
        start = max(start, _view_floor(cfg))
        end = min(end, _train_end(cfg))
        if not any(a <= start and end <= b for a, b in opened.get(symbol, ())):
            raise HTTPException(403, "这段 K 线不在本次打开过的清单图窗里;先在看图工作流里打开清单"
                                     "(打开时会记一条看过)")
        win = slice_window(_bars(cfg, symbol, end), start, end)
        return serialize_ohlc(symbol, win)

    def _validate(ann: AnnotationIn, cfg: dict, dates_cache: dict) -> list[str]:
        errs = []
        tag = ann.item_id
        train_end = _train_end(cfg)
        floor = _view_floor(cfg)
        try:
            check_symbol(ann.symbol)
        except ValueError:
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
        errs += _validate_bps(bps, tag, "买点")
        dates = [b["date"] for b in bps]
        first = [{"date": b.date, "primary": b.primary} for b in ann.first_buy_points or []]
        errs += _validate_bps(first, tag, "第一次露出结果时的买点")
        named = [("range_start", ann.range_start), ("range_end", ann.range_end)] if has_range else []
        named += [("买点", d) for d in dates]
        named += [("第一次露出结果时的买点", b["date"]) for b in first]
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
        ids = {it.get("item_id") for it in lst.get("items") or [] if isinstance(it, dict)}
        for a in req.annotations:
            errs += _validate(a, cfg, cache)
            if list_kind == "bigmoves" and a.item_id not in ids:
                errs.append(f"{a.item_id}: 不在清单 {req.list_id} 里")
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
            d = a.model_dump(exclude={"buy_date", "buy_points", "first_buy_points"})
            d["buy_points"] = _buy_points(a)
            d["first_buy_points"] = (None if a.first_buy_points is None else
                                     [{"date": b.date, "primary": b.primary} for b in a.first_buy_points])
            d["ann_id"] = d.get("ann_id") or str(uuid.uuid4())
            d["updated_at"] = d.get("updated_at") or now.strftime("%Y-%m-%dT%H:%M:%S")
            anns.append(d)
        if list_kind == "bigmoves":           # 改点痕迹、看过后续、别处露出过:以服务端的看过记录为准
            items = {it.get("item_id"): it for it in lst.get("items") or [] if isinstance(it, dict)}
            try:
                rows = views.read_views()
            except StateRootMissing as e:
                raise HTTPException(503, str(e)) from None
            def dates_of(sym):
                try:
                    return _bars(cfg, sym, _train_end(cfg)).index
                except HTTPException:
                    return None

            for d in anns:
                trail = views.outcome_trail(items[d["item_id"]], req.list_id, rows, dates_of)
                d["peeked_before_buy"] = bool(d["peeked_before_buy"] or trail["peeked"])
                d["outcome_seen_elsewhere"] = trail["seen_elsewhere"]
                rv = trail["first_reveal"]
                if rv is None:
                    continue
                rec = [{"date": b["date"], "primary": bool(b["primary"])} for b in rv["buy_points"]]
                d["changed_after_reveal"] = bool(
                    d["changed_after_reveal"] or _bp_key(d["first_buy_points"]) != _bp_key(rec)
                    or _bp_key(d["buy_points"]) != _bp_key(rec))
                d["first_buy_points"] = rec
        else:
            for d in anns:
                d["outcome_seen_elsewhere"] = None
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
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=1))
        tmp.replace(path)
        cw_state.advance(root)
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
