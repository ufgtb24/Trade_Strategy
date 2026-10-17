"""调试视图的看图范围护栏:调试视图只露本轮看图范围内的行情与命中。

本轮看图范围 = [看图下界 view_floor, 训练段末日 train_end],与看图工作流同一份(configs 的 workflow 子树,
train_end 先和 chart_workflow.loader.HARD_END 取小,配置写成 2026 年也不越过 2025-12-31)。
调试视图的各接口(path2_web/api.py)都经这里:

- 读行情:一律经 chart_workflow.loader 读截断副本(workflow.dataset_dir),截到 train_end;顶层 dataset_dir
  调试视图不再读。不是副本、副本与账上登记的不是同一份、主目录的账还没登记副本 → 503;代码名不合格 → 400;
  副本里没有这只股票 → 404。探测器预热要的更早的行情照常在内部读。
- K 线(/ohlc):看图下界之前的 bar 只留日期,价格与量置 null——事件与 match 按序号和 K 线对齐,这些 bar
  要占位,但不给看。每张露出了 K 线的图经 chart_workflow.views.record 记一条看过(surface=debug,
  outcome_visible=true:调试视图的图带着买点之后的走势),同一进程里同一图窗只记一次;记不进去就不给图(503)。
- 单股预览(/preview)与扫描(/scan):起止截到看图范围内;扫描结果的 scan 段带
  view_guard = {view_floor, train_end}(这份扫描读的是截断副本、起点不早于这个下界)。
- 打开扫描结果(/scans/{name}):带 view_guard 且范围不比现在宽的照常给。其余的(旧扫描,读的是完整行情)
  只要扫描起点早于看图下界、或分析窗终点晚于训练段末日(缺字段按越界算),就不能打开(409,提示重新扫描)——
  它的命中、标签、成绩、随机日基线都可能用到了范围外的行情;扫描文件是一次性产物,不为旧文件写截取重算,
  重新扫一遍就是带护栏的新文件。
- 扫描列表(/scans/):这种旧扫描照常列名字,但不给命中数、中位数和首次穿越比(那是按范围外的行情算的),
  带 old_scan = true。

只做截取与拦截,不做任何走势判断(纯投影层)。
"""
from __future__ import annotations

import pandas as pd
from fastapi import HTTPException

from chart_workflow import views
from chart_workflow.loader import NotASnapshot, check_snapshot
from chart_workflow.state import StateRootMissing
from path2_web.data import serialize_ohlc, slice_window
from path2_web.workflow import _bars, _data_dir, _is_date, _train_end, _view_floor

_PRICE_KEYS = ("o", "h", "l", "c", "v", "rv")


def bounds(cfg: dict) -> tuple[str, str]:
    """本轮看图范围 (view_floor, train_end)。"""
    return _view_floor(cfg), _train_end(cfg)


def data_dir(cfg: dict) -> str:
    """调试视图读的截断副本目录(先核对是不是副本、是不是账上登记的那一份,不是就 503)。"""
    d = _data_dir(cfg)
    try:
        check_snapshot(d)
    except (NotASnapshot, StateRootMissing) as e:
        raise HTTPException(503, str(e)) from None
    return str(d)


def bars(cfg: dict, symbol: str, end: str | None = None) -> pd.DataFrame:
    """经 chart_workflow.loader 读一只股票,截到 min(end, train_end)(含)。"""
    te = _train_end(cfg)
    return _bars(cfg, symbol, min(str(end), te) if end else te)


def check_dates(start, end) -> None:
    if not (_is_date(start) and _is_date(end)):
        raise HTTPException(400, "start / end 必须是 YYYY-MM-DD")


def clamp_range(cfg: dict, start: str, end: str) -> tuple[str, str]:
    """把 [start, end] 截进看图范围;日期格式不对 → 400;截完为空 → 400。"""
    check_dates(start, end)
    floor, te = bounds(cfg)
    s, e = max(start, floor), min(end, te)
    if s > e:
        raise HTTPException(400, f"{start}~{end} 不在本轮看图范围 {floor}~{te} 内")
    return s, e


def ohlc(cfg: dict, symbol: str, start: str, end: str) -> dict:
    """调试视图的 K 线:截到 train_end,看图下界之前的 bar 只留日期(价格与量 null)。"""
    check_dates(start, end)
    floor, te = bounds(cfg)
    end = min(end, te)
    out = serialize_ohlc(symbol, slice_window(bars(cfg, symbol, end), start, end))
    for b in out["bars"]:
        if b["date"] < floor:
            b.update(dict.fromkeys(_PRICE_KEYS))
    return out


def record_chart(out: dict, seen: set) -> None:
    """露出了 K 线的图记一条看过(surface=debug);seen 是本进程已记过的图窗,同一图窗只记一次。
    记不进去 → 503(不给图)。"""
    shown = [b["date"] for b in out["bars"] if b["o"] is not None]
    if not shown:
        return
    key = (out["symbol"], shown[0], shown[-1])
    if key in seen:
        return
    try:
        views.record(surface="debug", event="show_chart", outcome_visible=True,
                     charts=[{"symbol": key[0], "start": key[1], "end": key[2]}],
                     note="调试视图的 K 线")
    except StateRootMissing as e:
        raise HTTPException(503, str(e)) from None
    except OSError as e:
        raise HTTPException(503, f"看过记录写不进去:{e}") from None
    seen.add(key)


def scan_tag(cfg: dict) -> dict:
    floor, te = bounds(cfg)
    return {"view_floor": floor, "train_end": te}


def is_old_scan(cfg: dict, scan: dict) -> bool:
    """这份扫描是不是要拦的旧扫描:带 view_guard 且范围不比现在宽 → 不要;否则起点早于看图下界、
    或分析窗终点晚于训练段末日(缺字段按越界算)→ 要。"""
    floor, te = bounds(cfg)
    tag = scan.get("view_guard")
    if isinstance(tag, dict) and str(tag.get("view_floor") or "") >= floor \
            and str(tag.get("train_end") or "9999") <= te:
        return False
    start = str(scan.get("start_date") or "")
    win_end = str(scan.get("win_end") or "9999")
    return start < floor or win_end > te


def check_openable(cfg: dict, data: dict) -> None:
    """打开扫描结果前的拦截:要拦的旧扫描 → 409(见模块说明)。"""
    scan = data.get("scan") if isinstance(data.get("scan"), dict) else {}
    if is_old_scan(cfg, scan):
        floor, te = bounds(cfg)
        raise HTTPException(
            409, f"这份扫描是加看图范围护栏之前扫的(区间 {scan.get('start_date')}~{scan.get('end_date')},"
                 f"读的是完整行情),可能含本轮看图范围 {floor}~{te} 以外的命中和走势,不能打开;请重新扫描")


def mark_old_scans(cfg: dict, rows: list[dict]) -> list[dict]:
    """扫描列表:要拦的旧扫描不给命中数、中位数和首次穿越比,带 old_scan = true。
    rows 是 scan.list_scans_flat 的结果(每行带文件里 scan 段的 start_date / win_end / view_guard)。"""
    for row in rows:
        if is_old_scan(cfg, row):
            row["old_scan"] = True
            row["hits"] = None
            for pp in (row.get("per_pattern") or {}).values():
                pp.update(hits=None, median=None, fp=None)
    return rows
