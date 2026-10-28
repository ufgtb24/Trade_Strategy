"""调试视图的看图范围护栏:调试视图只露本轮看图范围内的行情与命中。

本轮看图范围 = [看图下界 view_floor, 训练段末日 train_end],与看图工作流同一份(configs 的 workflow 子树,
train_end 先和读行情的上限 chart_workflow.loader.read_ceiling() 取小,配置写成 2026 年也不越过 2025-12-31)。
调试模式(chart_workflow.mode)下看图范围是调试段 2021-10-01..2022-09-30(代码常量,配置改不了),读行情一律截到
2022-09-30;扫描结果的护栏标记另带 mode = debug,两种模式只打开自己的扫描。
调试视图的各接口(path2_web/api.py)都经这里:

- 读行情:一律经 chart_workflow.loader 读截断副本(workflow.dataset_dir),截到 train_end;顶层 dataset_dir
  调试视图不再读。不是副本、副本与账上登记的不是同一份、主目录的账还没登记副本 → 503;代码名不合格 → 400;
  副本里没有这只股票 → 404。探测器预热要的更早的行情照常在内部读。
- K 线(/ohlc):看图下界之前的 bar 只留日期,价格与量置 null——事件与 match 按序号和 K 线对齐,这些 bar
  要占位,但不给看。每张露出了 K 线的图经 chart_workflow.views.record 记一条看过(surface=debug,
  outcome_visible=true:调试视图的图带着买点之后的走势),同一进程里同一图窗只记一次;记不进去就不给图(503;
  图窗和当前模式对不上——正式模式下整张都在调试段里——是 409,见 chart_workflow.views)。
- 单股预览(/preview)与扫描(/scan):起止截到看图范围内;扫描结果的 scan 段带
  view_guard = {view_floor, train_end, snapshot_sha}(这份扫描读的是截断副本、起点不早于这个下界、
  副本按内容的指纹是多少)。
- 事件与诊断也只露下界及以后:预览、扫描(落盘时和打开时)、诊断在返回之前删掉锚点(事件声明的最早一根
  bar,serialize.event_anchor;分析结果和诊断用同一条规则)早于看图下界的事件、诊断行和失败尝试,留下的
  事件与 match 里指向它们的引用、事件字段里指向它们的编号一并删掉或置空(serialize.redact_before);
  内部照常用长预热计算。诊断的分析窗起点不早于「下界往前推这个 app 声明的预热天数」;按 bar 诊断的
  框选起点不早于下界那根(截到它),框选终点早于它就 400;成对诊断点到下界之前的事件也 400。
  诊断里的计数(总数、通过数、各失败原因的个数)是整段分析窗的统计,原样保留,只删行和样例。
- 打开扫描结果(/scans/{name}):带 view_guard、属于当前模式、范围不比现在宽、副本指纹和现在的副本一致的照常给;
  没有 view_guard 的一律当旧扫描拦(409,提示重新扫描)——它读的可能是完整行情、没经副本核对、带着预热段的事件;
  另一种模式的扫描(标记里的 mode 对不上)、副本指纹对不上(换过副本)的也拦。扫描文件是一次性产物,不为旧文件
  写截取重算,重新扫一遍就是带护栏的新文件。
- 扫描列表(/scans/):要拦的扫描照常列名字,但不给命中数、中位数和首次穿越比,带 old_scan = true。
- 记看过:单股预览记这只股票和它露出的区间(到前瞻窗终点,截到训练段末日);打开扫描按整份清单的口径记一条
  open_list(list_kind = debug_scan,清单快照里每只股票一条,图窗是扫描区间到前瞻窗终点)。记不进去就不给。

已知残留(有意接受):留下的事件和诊断失败记录里的派生值(峰的相对高度、判定的实测值、量比、距峰根数等)
是检测器用长预热算的,可能带着下界之前行情的零星数值,例如由峰价和相对高度能算回下界前某一根的最低价、
由相邻两个量比能算回下界前某一天的成交量;match 编号里也带着截断前的起点位置。原始数值在调试视图的事件
悬停面板里看得到,要换算才能得出下界前的价格或成交量,K 线上不显示;按用户「不放大不算看过」的口径不算看过。
检测代码(path2/)不为护栏改动,这里也不认具体事件类型去逐个清理。

只做截取与拦截,不做任何走势判断(纯投影层)。

护栏开关(workflow.debug_view_guard,缺省 true):设成 false 时调试视图改读顶层 dataset_dir 的完整行情
(不必是截断副本),读出来照样截到训练段末日 train_end(与读行情上限取小,不越过 2025-12-31);
不核对副本、不设看图下界、不记看过。打开扫描时只拦没有护栏标记的旧扫描、另一种模式的扫描和
train_end 比现在晚的扫描。开关关着扫出来的文件 snapshot_sha 为 null,开关打开后当换过副本拦掉。
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder

from chart_workflow import mode as cw_mode
from chart_workflow import views
from chart_workflow.loader import NotASnapshot, check_snapshot, check_symbol, read_ceiling
from chart_workflow.snaplock import fingerprint
from chart_workflow.state import StateRootMissing
from path2_web.data import serialize_ohlc, slice_window
from path2_web.serialize import event_anchor, redact_before
from path2_web.workflow import (_REPO_ROOT, _bars, _data_dir, _is_date, _train_end, _view_floor,
                                _wf_cfg)

TRADING_TO_CALENDAR_RATIO = 1.65   # 与 path2_web/scan.py 同值:交易日 → 日历日

_PRICE_KEYS = ("o", "h", "l", "c", "v", "rv")

_NO_FLOOR = "1900-01-01"   # 护栏关掉时的看图下界:等于不设


def unguarded(cfg: dict) -> bool:
    """护栏开关关着(workflow.debug_view_guard 为 false)。"""
    return _wf_cfg(cfg).get("debug_view_guard", True) is False


def raw_bars(ddir, symbol: str, end: str) -> pd.DataFrame:
    """护栏关着时读一只股票:ddir/<symbol>.pkl 不必是截断副本;去 tz、按日期排序,截到
    min(end, read_ceiling())(含)。代码名不合格 → ValueError;文件不存在 → FileNotFoundError。"""
    check_symbol(symbol)
    df = pd.read_pickle(Path(ddir) / f"{symbol}.pkl")
    if getattr(df.index, "tz", None) is not None:
        df = df.copy()
        df.index = df.index.tz_localize(None)
    df = df.sort_index()
    return df[df.index <= pd.Timestamp(min(str(end), read_ceiling()))]


def bounds(cfg: dict) -> tuple[str, str]:
    """本轮看图范围 (view_floor, train_end);护栏关着时不设下界。"""
    return (_NO_FLOOR if unguarded(cfg) else _view_floor(cfg)), _train_end(cfg)


def data_dir(cfg: dict) -> str:
    """调试视图读的行情目录。护栏开着:截断副本(先核对是不是副本、是不是账上登记的那一份,不是就 503);
    关着:顶层 dataset_dir。"""
    if unguarded(cfg):
        d = Path(cfg["dataset_dir"])
        return str(d if d.is_absolute() else _REPO_ROOT / d)
    d = _data_dir(cfg)
    try:
        check_snapshot(d)
    except (NotASnapshot, StateRootMissing) as e:
        raise HTTPException(503, str(e)) from None
    return str(d)


def bars(cfg: dict, symbol: str, end: str | None = None) -> pd.DataFrame:
    """读一只股票,截到 min(end, train_end)(含)。护栏开着经 chart_workflow.loader 读截断副本。"""
    te = _train_end(cfg)
    until = min(str(end), te) if end else te
    if not unguarded(cfg):
        return _bars(cfg, symbol, until)
    try:
        return raw_bars(data_dir(cfg), symbol, until)
    except FileNotFoundError:
        raise HTTPException(404, f"pkl not found: {symbol}") from None
    except ValueError as e:                  # 代码名不合格
        raise HTTPException(400, str(e)) from None


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


def _record(**kw) -> None:
    try:
        views.record(surface="debug", outcome_visible=True, **kw)
    except StateRootMissing as e:
        raise HTTPException(503, str(e)) from None
    except ValueError as e:              # 图窗和当前模式对不上(看过记录两种模式各记各的)
        raise HTTPException(409, str(e)) from None
    except OSError as e:
        raise HTTPException(503, f"看过记录写不进去:{e}") from None


def record_chart(cfg: dict, out: dict, seen: set) -> None:
    """露出了 K 线的图记一条看过(surface=debug);seen 是本进程已记过的图窗,同一图窗只记一次。
    记不进去 → 503(不给图)。护栏关着不记。"""
    if unguarded(cfg):
        return
    shown = [b["date"] for b in out["bars"] if b["o"] is not None]
    if not shown:
        return
    key = (out["symbol"], shown[0], shown[-1])
    if key in seen:
        return
    _record(event="show_chart", charts=[{"symbol": key[0], "start": key[1], "end": key[2]}],
            note="调试视图的 K 线")
    seen.add(key)


def record_preview(cfg: dict, symbol: str, start: str, end: str) -> None:
    """单股预览露出了这只股票 [start, end](end 是前瞻窗终点)的命中与成绩:记一条看过。记不进去 → 503。
    护栏关着不记。"""
    if unguarded(cfg):
        return
    _record(event="show_chart", charts=[{"symbol": symbol, "start": start, "end": min(end, _train_end(cfg))}],
            note="调试视图的单股预览")


def _scan_list_id(name: str) -> str:
    return "debug-scan-" + (re.sub(r"[^A-Za-z0-9_\-.]", "_", name).strip(".") or "x").replace("..", "__")


def record_scan_open(cfg: dict, name: str, data: dict) -> None:
    """打开扫描:结果列表露出每只命中股的成绩,按整份清单的口径记一条 open_list。记不进去 → 503。
    护栏关着不记。"""
    if unguarded(cfg):
        return
    scan = data.get("scan") or {}
    start = max(str(scan.get("start_date") or ""), _view_floor(cfg))
    end = min(str(scan.get("win_end") or scan.get("end_date") or ""), _train_end(cfg))
    items = [{"item_id": f"{r.get('symbol')}@{start}", "symbol": r.get("symbol"), "t": None,
              "view_start": start, "view_end": end} for r in data.get("results") or []]
    _record(event="open_list", list_id=_scan_list_id(name), list_kind="debug_scan",
            list_doc={"kind": "debug_scan", "title": f"调试视图扫描 {name}", "created_at": scan.get("scan_ts"),
                      "train_end": _train_end(cfg), "items": items},
            note=f"调试视图打开扫描 {name}")


def current_snapshot_sha(cfg: dict) -> str | None:
    """现在的截断副本按内容的指纹;读不了(不是副本等)或护栏关着为 None。"""
    if unguarded(cfg):
        return None
    try:
        return fingerprint(_data_dir(cfg))["sha"]
    except (NotASnapshot, StateRootMissing, OSError):
        return None


def scan_tag(cfg: dict, ddir: str) -> dict:
    """扫描结果的护栏标记;调试模式另带 mode = debug(正式模式的标记格式不变)。
    护栏关着:snapshot_sha 为 None,另带 unguarded = true(扫描 worker 据此不经 loader 读)。"""
    floor, te = bounds(cfg)
    if unguarded(cfg):
        tag = {"view_floor": floor, "train_end": te, "snapshot_sha": None, "unguarded": True}
    else:
        tag = {"view_floor": floor, "train_end": te, "snapshot_sha": fingerprint(ddir)["sha"]}
    if cw_mode.is_debug():
        tag["mode"] = cw_mode.DEBUG
    return tag


def scan_block_reason(cfg: dict, scan: dict, sha: str | None) -> str | None:
    """这份扫描为什么要拦(None = 不拦):没有护栏标记 → 旧扫描;属于另一种模式;范围比现在宽;
    副本指纹和现在的不一致。"""
    floor, te = bounds(cfg)
    tag = scan.get("view_guard")
    if not isinstance(tag, dict):
        return (f"这份扫描是加看图范围护栏之前扫的(区间 {scan.get('start_date')}~{scan.get('end_date')}),"
                f"读的可能是完整行情、带着预热段的事件,可能含本轮看图范围 {floor}~{te} 以外的命中和走势")
    foreign = cw_mode.foreign_reason(tag, "扫描")
    if foreign:
        return foreign
    off = unguarded(cfg)
    if (not off and str(tag.get("view_floor") or "") < floor) or str(tag.get("train_end") or "9999") > te:
        return (f"这份扫描的看图范围 {tag.get('view_floor')}~{tag.get('train_end')} 比本轮 {floor}~{te} 宽")
    if not off and (not tag.get("snapshot_sha") or tag.get("snapshot_sha") != sha):
        return "这份扫描读的截断副本和现在的不是同一份(换过副本,或扫描时没记副本指纹)"
    return None


def is_old_scan(cfg: dict, scan: dict, sha: str | None = None) -> bool:
    return scan_block_reason(cfg, scan, sha) is not None


def check_openable(cfg: dict, data: dict) -> None:
    """打开扫描结果前的拦截:要拦的扫描 → 409(见模块说明)。"""
    scan = data.get("scan") if isinstance(data.get("scan"), dict) else {}
    why = scan_block_reason(cfg, scan, current_snapshot_sha(cfg))
    if why:
        raise HTTPException(409, f"{why},不能打开;请重新扫描")


def redact_scan(data: dict) -> dict:
    """打开扫描时再删一遍锚点早于看图下界的事件(落盘时已删过,这里兜底,幂等);某只股票没记
    view_floor_idx → 409。就地改并返回。"""
    for r in data.get("results") or []:
        for pid, out in (r.get("per_pattern") or {}).items():
            if not isinstance(out, dict) or "analysis" not in out:
                continue
            if not isinstance(out.get("view_floor_idx"), int):
                raise HTTPException(409, f"这份扫描里 {r.get('symbol')} 的 {pid} 没记看图下界那根的位置,"
                                         f"不能打开;请重新扫描")
            out["analysis"] = redact_before(out["analysis"], out["view_floor_idx"])
    return data


def mark_old_scans(cfg: dict, rows: list[dict]) -> list[dict]:
    """扫描列表:要拦的扫描不给命中数、中位数和首次穿越比,带 old_scan = true。
    rows 是 scan.list_scans_flat 的结果(每行带文件里 scan 段的 start_date / win_end / view_guard)。"""
    sha = current_snapshot_sha(cfg)
    for row in rows:
        if is_old_scan(cfg, row, sha):
            row["old_scan"] = True
            row["hits"] = None
            for pp in (row.get("per_pattern") or {}).values():
                pp.update(hits=None, median=None, fp=None)
    return rows


# ── 诊断 ─────────────────────────────────────────────────────────────────────

def floor_index(win: pd.DataFrame, cfg: dict) -> int:
    """看图下界那根在 win 里的行号(win 有 date 列)。"""
    return int(win["date"].searchsorted(pd.Timestamp(bounds(cfg)[0]), "left"))


def diagnose_start(cfg: dict, start: str, head_buffer_days: int) -> str:
    """诊断的分析窗起点:不早于「看图下界往前推 head_buffer_days 个交易日(按日历日折算)」。"""
    lo = (pd.Timestamp(bounds(cfg)[0])
          - pd.Timedelta(days=round(head_buffer_days * TRADING_TO_CALENDAR_RATIO))).strftime("%Y-%m-%d")
    return max(start, lo)


def clamp_bars(start_bar, end_bar, floor_idx: int):
    """按 bar 诊断的框选:起点截到下界那根;终点早于它 → 400。"""
    if end_bar is not None and end_bar < floor_idx:
        raise HTTPException(400, "框选的那段早于本轮看图下界,不给诊断")
    if start_bar is not None:
        start_bar = max(start_bar, floor_idx)
    return start_bar, end_bar


def event_anchors(events) -> dict:
    """事件对象 → {instance_id: 锚点};锚点规则与分析结果的删减相同(serialize.event_anchor:事件声明的最早一根
    bar,按字段命名约定取)。"""
    return {e.instance_id: event_anchor(vars(e)) for e in events}


def diag_anchors(diag) -> dict:
    """NodeDiagnostics 里出现过的事件的锚点:instance_id → 锚点。"""
    return event_anchors(row.event for rd in getattr(diag, "nodes", {}).values() for row in rd.attr)


def redact_diagnostics(out: dict, floor_idx: int, anchors: dict) -> dict:
    """legacy 诊断(serialize_diagnostics 的结果):删掉锚点(anchors,见 diag_anchors;查不到按 attr 行的
    start_idx)早于下界的 attr 行;rel 行的通过事件列表只留还在的事件。计数原样保留(整段分析窗的统计)。
    就地改并返回。"""
    keep = set()
    for nd in (out.get("nodes") or {}).values():
        nd["attr"] = [r for r in nd.get("attr") or []
                      if anchors.get(r.get("instance_id"), r.get("start_idx", -1)) >= floor_idx]
        keep |= {r["instance_id"] for r in nd["attr"]}
    for nd in (out.get("nodes") or {}).values():
        for r in nd.get("rel") or []:
            r["ok_src_ids"] = [i for i in r.get("ok_src_ids") or [] if i in keep]
    return out


def redact_scoped(resp, floor_idx: int, *, diag=None, result=None) -> dict:
    """按 scope 的诊断回应(derive_response 的结果):转成 JSON 形状后删掉下界之前的东西——
    nodes:失败样例里任一端事件的锚点早于下界(或查不到)就删;time:失败尝试的轨迹起点、判据起点、语义锚
    任一早于下界就删;pair:点到的事件锚点早于下界 → 400。锚点规则同分析结果(event_anchors)。"""
    d = jsonable_encoder(resp)
    payload = d.get("payload") or {}
    if d.get("scope") == "nodes":
        anchors = diag_anchors(diag)
        ok = lambda i: anchors.get(i, -1) >= floor_idx
        for key in ("example_failed_pairs", "per_pair"):
            if isinstance(payload.get(key), list):
                payload[key] = [p for p in payload[key] if ok(p.get("src_event_id")) and ok(p.get("dst_event_id"))]
    elif d.get("scope") == "time":
        payload["failed_attempts"] = [
            g for g in payload.get("failed_attempts") or []
            if min((g.get("failure_event_window") or [floor_idx])[0], g.get("start_idx", floor_idx),
                   g.get("anchor_bar", floor_idx)) >= floor_idx]
    elif d.get("scope") == "pair":
        anchors = event_anchors(getattr(result, "events", None) or [])
        for key in ("src_event_id", "dst_event_id"):
            iid = payload.get(key)
            if iid is not None and anchors.get(iid, floor_idx) < floor_idx:
                raise HTTPException(400, "点到的事件早于本轮看图下界,不给诊断")
    return d
