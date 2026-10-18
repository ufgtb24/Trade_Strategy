"""事实脚本:给一只股票和一个买点,只用买点当天及以前的 K 线,列出一张固定顺序的事实表、
口径分歧、触发候选与买前失效模板。算得出来的事实由机器列,信不信由用户点。

    uv run python -m chart_workflow.facts --batch <batch_id> [--ann <ann_id>] [--json]
    uv run python -m chart_workflow.facts --symbol S --buy-date D [--range-start D] [--json]
    uv run python -m chart_workflow.facts --rows                       # 列出全部事实行与出处
    uv run python -m chart_workflow.facts --check-row "<标题>" --reads a,b   # 新增一行之前查重

事实只是计算方法(ROWS 里的一行)加每张图的结果(下面的 rows),只给数值和描述、不带判断,
没有角色、不进形态卡;是 / 否条件是要素(elements.py),在这些行上定出来。每一行标出处(source):
预设的,或者用户提的角度(哪天提的、原话、那次提的操作日志条目)。
每行 value 里哪些量能拿来立要素,由 elements.VALUES 声明;value 里的事件列表(F05 all_runs、F09、F11、
F13、F14、F15)列全窗口里的全部(描述和图上标记可能只列几段),每个事件带 bars_before
(买点 − 事件最后一根,0 = 买点当天)。

输出(compute_facts 的返回值,键顺序固定,数值统一保留 4 位小数):
{"schema": "chart_workflow.facts/1", "facts_code": "<本文件源码 sha256 前 12 位>",
 "symbol": "QMMM", "buy_date": "2025-07-14",
 "window": ["2025-02-28", "2025-07-14"], "window_source": "box | default",
 "rows": [{"fid": "F01", "group": "峰与突破", "title": "按收盘越过的峰", "text": "<人话>",
           "value": {...}, "chart_dates": ["2025-03-12", ...],      # 图上该标出的日期
           "variant": "close" | "high" | null, "unfinished": false, "divergence": "DV1" | null,
           "source": {"kind": "preset"} | {"kind": "user", "date", "said", "op_id"}}],
 "divergences": [{"dvid": "DV1", "rows": ["F01", "F02"], "question": "...",
                  "options": [{"variant": "close", "text": "..."}, ...]}],
 "triggers": [{"tid": "T5", "kind": TRIGGERS["T5"][0], "text": "...", "chart_dates": [...],
               "variants": ["close", "high"]}],
 "invalidation_templates": [{"iid": "I1", "text": "..."}, {"iid": "I2", "text": "..."}]}

事实表是一张检查单,不是推荐榜:F01~F15 每次按同样顺序全部列出,没有的写「没有」开头的一句;
不排序、不打分。口径分歧只在同一说法的两种理解在这张图上结论不同时才生成(DV1 峰按收盘还是
最高价、DV2 派发看多远、DV3 放量指哪段)。触发候选只列买点当天命中的(T1~T8 固定顺序),
一个都没命中时为空列表。买前失效模板固定、不预勾。参数在 config 的 facts 子树(全部待验证)。
停牌日(当天没成交)的量比判定不了,记 null、不当 0(当 0 的话,写在量比上的「至多 x」会在停牌日判成「是」):
F05~F07 和触发里的量比都按这个口径;F06 的均量比(这几天均量 ÷ 最近一段放量段均量)读到停牌日也判定不了。

红线:compute_facts 第一步就把 K 线截到买点当天(含),之后的任何计算都读不到买点之后的数据
(有「把买点之后换成随机数,输出一字不差」的测试守住);读数据只经 loader(截断副本),
不 import 标签口径(labels)、对照(control)、面板(panel)、清单(listfile)等模块,不读清单文件
(清单里有结果字段)。年份闸:facts_for 只接受看图下界到训练段末日之间的买点;回看可以读到
下界之前(比如 2024 年),但只以数字进事实表。

快照:每次给用户看过的事实表写到 <状态根>/facts/<batch_id>.json(临时查询为
facts/adhoc-<YYYYmmddTHHMMSS>.json),同名已存在就加 -2、-3……,只增不改:
{"schema": "chart_workflow.facts_snapshot/1", "created_at", "batch_id",
 "results": [{"ann_id", "item_id", "facts": <compute_facts 的输出>}]}
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from chart_workflow.annotations import read_batch
from chart_workflow.config import DEFAULTS, load_config
from chart_workflow.features import feature_frame
from chart_workflow.loader import read_bars
from chart_workflow.state import StateRootMissing, advance, state_root
from path2.atoms.breakout import BODetector
from path2.atoms.distribution import DistributionDetector
from path2.atoms.platform import PlatformDetector
from path2.atoms.throwback import ThrowbackDetector
from path2.atoms.trend import TrendSegmentDetector
from path2.calc.atr import rolling_atr_pct_nanmedian
from path2.calc.volume import calculate_vol_ratio
from path2.runner import run, run_bundle

SCHEMA = "chart_workflow.facts/1"
SNAPSHOT_SCHEMA = "chart_workflow.facts_snapshot/1"
FACTS_CODE = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()[:12]

# 事实表的固定行。每一行是一种计算方法(分组、标题、读哪些量 reads、出处 source),
# 每张图的结果是 compute_facts 输出里的那一行。事实只给数值和描述、不带判断,没有角色、不进形态卡;
# 要素(elements.py)在这些行上定是 / 否条件。
# 出处:PRESET = 预设;用户提的角度做成的行写 {"kind": "user", "date": 哪天提的, "said": 原话,
# "op_id": 那次提的操作日志条目(act = propose_fact)}——在它上面立的要素,账本记成「你提的角度」。
# reads 用来查重:新增一行之前跑 python -m chart_workflow.facts --check-row,
# 同名或读同样量的已有行会列出来(只提示,不拦)。
PRESET = {"kind": "preset"}
ROWS = {
    "F01": {"group": "峰与突破", "title": "按收盘越过的峰", "reads": ("peaks_close",), "source": PRESET},
    "F02": {"group": "峰与突破", "title": "按最高价越过的峰", "reads": ("peaks_high",), "source": PRESET},
    "F03": {"group": "峰与突破", "title": "几天内连续突破",
            "reads": ("peaks_close", "peaks_high", "first_clear"), "source": PRESET},
    "F04": {"group": "峰与突破", "title": "越过的峰最早是多久以前",
            "reads": ("peaks_close", "peaks_high", "first_clear"), "source": PRESET},
    "F05": {"group": "成交量", "title": "放量段", "reads": ("vol_ratio",), "source": PRESET},
    "F06": {"group": "成交量", "title": "买点前几天缩量", "reads": ("vol_ratio",), "source": PRESET},
    "F07": {"group": "成交量", "title": "买点当天量倍数", "reads": ("vol_ratio",), "source": PRESET},
    "F08": {"group": "涨跌与位置", "title": "涨前状态", "reads": ("pre_state",), "source": PRESET},
    "F09": {"group": "涨跌与位置", "title": "近期走势区段", "reads": ("trend_segments",), "source": PRESET},
    "F10": {"group": "涨跌与位置", "title": "当天跳空", "reads": ("gap",), "source": PRESET},
    "F11": {"group": "涨跌与位置", "title": "买点前有平台段", "reads": ("platform_segments",),
            "source": PRESET},
    "F12": {"group": "涨跌与位置", "title": "买点前一段走势", "reads": ("close_path",), "source": PRESET},
    "F13": {"group": "派发", "title": "近期派发", "reads": ("distribution",), "source": PRESET},
    "F14": {"group": "回踩", "title": "突破后回踩企稳", "reads": ("throwback",), "source": PRESET},
    "F15": {"group": "回踩", "title": "回踩被越过的峰后收盘收回",
            "reads": ("peaks_close", "peaks_high", "first_clear", "low"), "source": PRESET},
}
TRIGGERS = {
    "T1": ("bo_day", "突破当天"), "T2": ("burst_last", "连续突破的最后一根"),
    "T3": ("new_high_20", "收盘创 20 日新高"), "T4": ("pullback_reclaim", "回落后收回"),
    "T5": ("retest_reclaim", "回踩被越过的峰后收回"), "T6": ("gap", "当天跳空"),
    "T7": ("dry_day", "当天缩量"), "T8": ("tb_entry", "回踩企稳开始"),
}
INVALIDATIONS = {"I1": "越过峰之后、触发之前，收盘跌回被越过的峰之下", "I2": "买点前出现派发"}

VARIANT_TEXT = {"close": "按收盘", "high": "按最高价"}
REGIME_TEXT = {"up": "上涨", "down": "下跌", "sideways": "横走"}
TB_EXIT_TEXT = {"rise": "回升脱离", "break": "下跌脱离", "timeout": "满窗", "distribute": "派发",
                "oversold": "跌破锚点"}
UNFINISHED_TEXT = "这一段在你点的那天还没走完，当时看不出来"
CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮"


# ── 小工具 ──────────────────────────────────────────────────────────────────

def _r(x):
    """数值统一 round 到 4 位;NaN / inf → None;numpy 标量 → Python 标量。"""
    if x is None:
        return None
    if isinstance(x, (bool, np.bool_)):
        return bool(x)
    if isinstance(x, (int, np.integer)):
        return int(x)
    x = float(x)
    return round(x, 4) if math.isfinite(x) else None


class _Ctx:
    """一次计算的上下文:截好的 K 线数组、日期串、窗口、参数。"""

    def __init__(self, df: pd.DataFrame, rs: int, fcfg: dict, features_cfg: dict, m_period: int):
        self.df = df
        self.o = df["open"].to_numpy(float)
        self.h = df["high"].to_numpy(float)
        self.l = df["low"].to_numpy(float)
        self.c = df["close"].to_numpy(float)
        self.v = df["volume"].to_numpy(float)
        self.d = [t.strftime("%Y-%m-%d") for t in df.index]
        self.ib = len(df) - 1
        self.rs = rs
        self.p = fcfg
        self.features_cfg = features_cfg
        self.m_period = m_period
        self.year = df.index[-1].year
        vr = calculate_vol_ratio(df["volume"], int(fcfg["vol_baseline"])).to_numpy(float)
        self.vr = np.where(self.v > 0, vr, np.nan)     # 停牌(当天没成交)的量比判定不了,不给 0
        self.bars = df.reset_index()          # 'date' 列 + 0-based 行号,喂 detector

    def md(self, i: int) -> str:
        """图上日期的短写:同年 M/D,跨年 YYYY/M/D。"""
        t = self.df.index[i]
        return f"{t.month}/{t.day}" if t.year == self.year else f"{t.year}/{t.month}/{t.day}"


def _px(x: float) -> str:
    return f"{x:.1f}" if x >= 100 else f"{x:.2f}" if x >= 1 else f"{x:.3g}"


def _pct(x) -> str:
    return "—" if x is None or not math.isfinite(x) else f"{x * 100:+.1f}%"


def _times(x) -> str:
    return "—" if x is None or not math.isfinite(x) else f"{x:.1f} 倍"


def _span(ctx: "_Ctx", a: int, b: int) -> str:
    return ctx.md(a) if a == b else f"{ctx.md(a)}–{ctx.md(b)}"


def _row(fid, text, value, dates, variant=None, unfinished=False) -> dict:
    d = ROWS[fid]
    return {"fid": fid, "group": d["group"], "title": d["title"], "text": text, "value": value,
            "chart_dates": sorted(set(dates)), "variant": variant,
            "unfinished": bool(unfinished), "divergence": None, "source": dict(d["source"])}


# ── 峰与突破 ────────────────────────────────────────────────────────────────

def _swing_peaks(ctx: _Ctx, ser: np.ndarray) -> list[dict]:
    """[rs, ib-1] 里的大尺度峰:ser[i] ≥ max(ser[a..b]),a = max(0, i−side),b = min(ib, i+side),
    且右侧根数 b−i ≥ min(side, swing_right_min);相隔 ≤ side 根的只留峰价更高的(相等留较晚的);
    取峰价最高的 max_peaks 个,按日期排。每个峰记越过与否(买点收盘 > 峰价)与首次越过日
    (峰之后第一根收盘 > 峰价)。"""
    side = int(ctx.p["swing_side"])
    need_right = min(side, int(ctx.p["swing_right_min"]))
    ib = ctx.ib
    cands = []
    for i in range(ctx.rs, ib):
        a, b = max(0, i - side), min(ib, i + side)
        if b - i >= need_right and ser[i] >= ser[a:b + 1].max():
            cands.append(i)
    kept: list[int] = []
    for i in cands:
        if kept and i - kept[-1] <= side:
            if ser[i] >= ser[kept[-1]]:
                kept[-1] = i
        else:
            kept.append(i)
    top = sorted(sorted(kept, key=lambda i: (-ser[i], i))[:int(ctx.p["max_peaks"])])
    out = []
    for i in top:
        price = float(ser[i])
        after = np.flatnonzero(ctx.c[i + 1:ib + 1] > price)
        fc = int(i + 1 + after[0]) if len(after) else None
        out.append({"idx": i, "price": price, "cleared": bool(ctx.c[ib] > price), "fc": fc})
    return out


def _peaks_row(ctx: _Ctx, fid: str, variant: str, peaks: list[dict]) -> dict:
    value = {"n_peaks": len(peaks), "n_cleared": sum(p["cleared"] for p in peaks),
             "peaks": [{"date": ctx.d[p["idx"]], "price": _r(p["price"]), "cleared": p["cleared"],
                        "first_clear": ctx.d[p["fc"]] if p["fc"] is not None else None}
                       for p in peaks]}
    dates = [ctx.d[p["idx"]] for p in peaks] + [ctx.d[p["fc"]] for p in peaks if p["fc"] is not None]
    if not peaks:
        return _row(fid, "没有（窗口里找不到大尺度峰）", value, [], variant)
    listing = "、".join(f"{ctx.md(p['idx'])} {_px(p['price'])}" for p in peaks)
    cleared = [p for p in peaks if p["cleared"]]
    head = (f"{VARIANT_TEXT[variant]}：窗口里有 {len(peaks)} 个峰（{listing}），"
            f"买点收盘 {_px(ctx.c[ctx.ib])}")
    if not cleared:
        text = head + " 一个都没越过"
    else:
        part = "都越过了" if len(cleared) == len(peaks) else (
            f"越过了 {len(cleared)} 个（" + "、".join(ctx.md(p["idx"]) for p in cleared) + "）")
        text = head + f" {part}，首次越过在 " + "、".join(ctx.md(p["fc"]) for p in cleared)
        rest = [p for p in peaks if not p["cleared"]]
        if rest:
            text += "；没越过的：" + "、".join(f"{ctx.md(p['idx'])}（{_px(p['price'])}）" for p in rest)
    return _row(fid, text, value, dates, variant)


def _burst(ctx: _Ctx, peaks: list[dict]) -> tuple[list[int], bool, list[int], int]:
    """越过了的峰的首次越过日(排序);相邻两次相隔 ≤ burst_gap_bars 根算连续突破。
    另返回最长的一串连续突破里有几个峰(chain;没有越过的峰为 0,只越过一个为 1)。"""
    fcs = sorted(p["fc"] for p in peaks if p["cleared"])
    gap = int(ctx.p["burst_gap_bars"])
    pair_idx = sorted({x for a, b in zip(fcs, fcs[1:]) if b - a <= gap for x in (a, b)})
    chain = cur = min(1, len(fcs))
    for a, b in zip(fcs, fcs[1:]):
        cur = cur + 1 if b - a <= gap else 1
        chain = max(chain, cur)
    return fcs, bool(pair_idx), pair_idx, chain


def _burst_row(ctx: _Ctx, peaks_by: dict) -> dict:
    value, parts, dates = {}, [], []
    for var in ("close", "high"):
        fcs, burst, pair, chain = _burst(ctx, peaks_by[var])
        value[var] = {"dates": [ctx.d[i] for i in fcs], "burst": burst, "chain": chain}
        dates += [ctx.d[i] for i in pair]
        if not fcs:
            parts.append(f"{VARIANT_TEXT[var]}：没有越过的峰")
        elif len(fcs) == 1:
            parts.append(f"{VARIANT_TEXT[var]}：只越过 1 个峰（{ctx.md(fcs[0])}），谈不上连续")
        else:
            days = "、".join(ctx.md(i) for i in fcs)
            verdict = (f"其中相隔 ≤ {ctx.p['burst_gap_bars']} 根的算连续突破（"
                       + "、".join(ctx.md(i) for i in pair) + f"），最长一串连着越过 {chain} 个峰") if burst else \
                f"相邻两次都相隔超过 {ctx.p['burst_gap_bars']} 根，不算连续"
            parts.append(f"{VARIANT_TEXT[var]}：首次越过在 {days}，{verdict}")
    if not value["close"]["dates"] and not value["high"]["dates"]:
        text = "没有（两种口径都没有越过的峰）"
    else:
        text = "；".join(parts)
    return _row("F03", text, value, dates)


def _oldest_row(ctx: _Ctx, peaks_by: dict) -> dict:
    value, parts, dates = {}, [], []
    for var in ("close", "high"):
        cl = [p for p in peaks_by[var] if p["cleared"]]
        if not cl:
            value[var] = None
            parts.append(f"{VARIANT_TEXT[var]}：没有越过的峰")
            continue
        p = max(cl, key=lambda p: ctx.ib - p["idx"])
        value[var] = {"bars": ctx.ib - p["idx"], "peak_date": ctx.d[p["idx"]]}
        dates.append(ctx.d[p["idx"]])
        parts.append(f"{VARIANT_TEXT[var]}：最早是 {ctx.md(p['idx'])} 那个峰，离买点 {ctx.ib - p['idx']} 根")
    text = "没有（两种口径都没有越过的峰）" if not dates else "；".join(parts)
    return _row("F04", text, value, dates)


# ── 成交量 ─────────────────────────────────────────────────────────────────

def _vol_run_spans(ctx: _Ctx) -> list[dict]:
    """窗口里量比 ≥ vol_run_min 的日子连成段:两段之间隔着的不达标根数 ≤ vol_run_gap 就合并;
    全部段按日期排。平均量比按段的起止之间全部根数算(含合并进来的间隔日;停牌日的量比判定不了,不计入)。"""
    vr = ctx.vr
    days = [i for i in range(ctx.rs, ctx.ib + 1) if math.isfinite(vr[i]) and vr[i] >= ctx.p["vol_run_min"]]
    runs: list[list[int]] = []
    for i in days:
        if runs and i - runs[-1][1] - 1 <= int(ctx.p["vol_run_gap"]):
            runs[-1][1] = i
        else:
            runs.append([i, i])
    info = []
    for a, b in runs:
        seg = vr[a:b + 1]
        info.append({"a": a, "b": b, "max": float(np.nanmax(seg)), "mean": float(np.nanmean(seg)),
                     "vol_mean": float(np.mean(ctx.v[a:b + 1]))})
    return info


def _vol_runs(ctx: _Ctx) -> list[dict]:
    """列在描述里的放量段:按段内最大量比取前 max_vol_runs 段,再按日期排;其中离买点最近的标 latest。"""
    info = _vol_run_spans(ctx)
    top = sorted(sorted(info, key=lambda r: (-r["max"], r["a"]))[:int(ctx.p["max_vol_runs"])],
                 key=lambda r: r["a"])
    for r in top:
        r["latest"] = r is top[-1]
    return top


def _vol_rule(ctx: _Ctx) -> str:
    return f"当日量 ÷ 前 {ctx.p['vol_baseline']} 日均量"


def _vol_runs_row(ctx: _Ctx, runs: list[dict]) -> dict:
    """runs:描述里列的几段(按最大量比取前几段);all_runs:窗口里全部放量段,带离买点根数
    (买点 − 段的最后一根),供要素判「最近 N 根里有没有」。"""
    value = {"rule": _vol_rule(ctx),
             "runs": [{"start": ctx.d[r["a"]], "end": ctx.d[r["b"]], "max_vr": _r(r["max"]),
                       "mean_vr": _r(r["mean"]), "latest": r["latest"]} for r in runs],
             "all_runs": [{"start": ctx.d[r["a"]], "end": ctx.d[r["b"]], "max_vr": _r(r["max"]),
                           "bars_before": ctx.ib - r["b"]} for r in _vol_run_spans(ctx)]}
    dates = [ctx.d[r["a"]] for r in runs] + [ctx.d[r["b"]] for r in runs]
    if not runs:
        text = f"没有（量比 = {_vol_rule(ctx)}，窗口里没有 ≥ {ctx.p['vol_run_min']:g} 倍的日子）"
    else:
        segs = "；".join(
            f"{_span(ctx, r['a'], r['b'])} 最大 {_times(r['max'])}、平均 {_times(r['mean'])}"
            + ("（离买点最近）" if r["latest"] else "") for r in runs)
        text = f"量比 = {_vol_rule(ctx)}；放量（量比 ≥ {ctx.p['vol_run_min']:g}）{len(runs)} 段：{segs}"
    return _row("F05", text, value, dates)


def _dry_row(ctx: _Ctx, runs: list[dict]) -> dict:
    n = int(ctx.p["dry_days"])
    idx = list(range(max(0, ctx.ib - n + 1), ctx.ib + 1))
    vrs = [ctx.vr[i] for i in idx]
    dry = all(math.isfinite(x) and x < 1 for x in vrs)
    latest = next((r for r in runs if r["latest"]), None)
    # 均量比读到的日子(这几天 + 最近一段放量段)里有停牌日就判定不了:all_traded 记 null,要素判 unknown
    read = idx + list(range(latest["a"], latest["b"] + 1)) if latest else []
    traded = all(ctx.v[i] > 0 for i in read)
    ratio = (float(np.mean(ctx.v[idx])) / latest["vol_mean"]
             if latest and traded and latest["vol_mean"] > 0 else None)
    value = {"days": [{"date": ctx.d[i], "vr": _r(ctx.vr[i])} for i in idx], "dry": dry,
             "vs_latest_run": _r(ratio), "all_traded": True if traded else None}
    text = (f"买点前 {len(idx)} 天（含买点当天）量比 "
            + "、".join("—" if not math.isfinite(x) else f"{x:.2f}" for x in vrs)
            + ("，都低于 1（缩量）" if dry
               else "，有算不出量比的日子（—：回看不够长，或当天没成交）" if not all(map(math.isfinite, vrs))
               else "，不是都低于 1"))
    text += (f"；这几天均量是最近一段放量段均量的 {ratio:.2f}" if ratio is not None
             else "；这几天或最近一段放量段里有停牌日（当天没成交），均量比判定不了" if not traded
             else "；窗口里没有放量段可比")
    return _row("F06", text, value, [ctx.d[i] for i in idx])


def _today_vol_row(ctx: _Ctx) -> dict:
    x = ctx.vr[ctx.ib]
    if not ctx.v[ctx.ib] > 0:
        text = "没有（当天没成交，停牌，量比判定不了）"
    elif not math.isfinite(x):
        text = f"没有（量比要前 {ctx.p['vol_baseline']} 根的均量做基线：历史不够，或前面一直没成交）"
    else:
        text = f"买点当天量比 {x:.2f}（{_vol_rule(ctx)}）"
    return _row("F07", text, {"vr": _r(x)}, [ctx.d[ctx.ib]])


# ── 涨跌与位置 ─────────────────────────────────────────────────────────────

def _m_series(ctx: _Ctx) -> np.ndarray:
    df = ctx.df
    return rolling_atr_pct_nanmedian(df["high"], df["low"], df["close"],
                                     period=ctx.m_period).to_numpy(float)


def _pre_state_row(ctx: _Ctx, M: np.ndarray) -> dict:
    feat = feature_frame(ctx.df, M, ctx.features_cfg).iloc[-1]
    value = {"pre_state": str(feat["pre_state"]), "dd250": _r(feat["dd250"]), "r60": _r(feat["r60"]),
             "width40": _r(feat["width40"]), "M": _r(M[ctx.ib])}
    width = "—" if value["width40"] is None else f"{value['width40'] * 100:.1f}%"
    text = (f"{feat['pre_state']}（离 250 日最高 {_pct(value['dd250'])}，"
            f"60 日涨幅 {_pct(value['r60'])}，40 日振幅占收盘 {width}；回看不够长的项记为 —）")
    return _row("F08", text, value, [ctx.d[ctx.ib]])


def _segments_overlapping(ctx: _Ctx, events) -> list:
    """和窗口有重叠的全部区段(按时间排)。"""
    return [e for e in events if e.end_idx >= ctx.rs]


def _more_text(n_all: int, n_shown: int) -> str:
    return f"（窗口里共 {n_all} 段，只列最近 {n_shown} 段）" if n_all > n_shown else ""


def _trend_row(ctx: _Ctx) -> dict:
    """描述和图上标记只列最近 6 段;value 里是和窗口重叠的全部区段,带离买点根数(买点 − 段的最后一根)。"""
    evs = _segments_overlapping(ctx, run(TrendSegmentDetector(), ctx.bars))
    segs = evs[-6:]
    items = [{"start": ctx.d[e.start_idx], "end": ctx.d[e.end_idx], "regime": e.regime,
              "unfinished": e.end_idx == ctx.ib, "bars_before": ctx.ib - e.end_idx} for e in evs]
    unfinished = any(x["unfinished"] for x in items)
    if not items:
        text = "没有（K 线太短，分不出走势区段）"
    else:
        text = _more_text(len(evs), len(segs)) + "；".join(
            f"{ctx.md(e.start_idx)}–{ctx.md(e.end_idx)} {REGIME_TEXT.get(e.regime, e.regime)}"
            + (f"（{UNFINISHED_TEXT}）" if e.end_idx == ctx.ib else "") for e in segs)
    dates = [ctx.d[e.start_idx] for e in segs] + [ctx.d[e.end_idx] for e in segs]
    return _row("F09", text, {"segments": items}, dates,
                unfinished=unfinished)


def _gap_row(ctx: _Ctx, M: np.ndarray) -> dict:
    ib = ctx.ib
    if ib < 1:
        return _row("F10", "没有（买点前没有 K 线）",
                    {"gap": None, "gap_m_flag": False, "M": None}, [])
    gap = ctx.o[ib] / ctx.c[ib - 1] - 1.0
    m = M[ib]
    k = float(ctx.features_cfg["gap_m"])
    flag = bool(math.isfinite(m) and gap >= k * m)
    text = (f"当天开盘相对前一天收盘 {_pct(gap)}；"
            + (f"{'达到' if flag else '不到'} {k:g} 倍 M（M = {_pct(m).lstrip('+')}），"
               f"{'算' if flag else '不算'}跳空" if math.isfinite(m) else "M 回看不够，不判跳空"))
    return _row("F10", text,
                {"gap": _r(gap), "gap_m_flag": flag, "M": _r(m)}, [ctx.d[ib]])


def _platform_row(ctx: _Ctx) -> dict:
    """描述和图上标记只列最近 4 段;value 里是和窗口重叠的全部平台段,带离买点根数。"""
    evs = _segments_overlapping(ctx, run(PlatformDetector(), ctx.bars))
    segs = evs[-4:]
    items = [{"start": ctx.d[e.start_idx], "end": ctx.d[e.end_idx], "range_pct": _r(e.range_pct),
              "unfinished": e.end_idx == ctx.ib, "bars_before": ctx.ib - e.end_idx} for e in evs]
    if not items:
        text = "没有"
    else:
        text = _more_text(len(evs), len(segs)) + "；".join(
            f"{ctx.md(e.start_idx)}–{ctx.md(e.end_idx)} 振幅 {_pct(e.range_pct).lstrip('+')}"
            + (f"（{UNFINISHED_TEXT}）" if e.end_idx == ctx.ib else "") for e in segs)
    dates = [ctx.d[e.start_idx] for e in segs] + [ctx.d[e.end_idx] for e in segs]
    return _row("F11", text, {"segments": items}, dates,
                unfinished=any(x["unfinished"] for x in items))


def _steady_row(ctx: _Ctx) -> dict:
    s0 = max(ctx.rs, ctx.ib - int(ctx.p["steady_n"]) + 1)
    c = ctx.c[s0:ctx.ib + 1]
    o = ctx.o[s0:ctx.ib + 1]
    n = len(c)
    rise = c[-1] / c[0] - 1.0 if n else None
    up_ratio = float(np.mean(c > o)) if n else None
    run_max = np.maximum.accumulate(c) if n else c
    max_dd = float(np.max(1.0 - c / run_max)) if n else None
    r2 = None
    if n >= 3 and np.all(c > 0):
        y = np.log(c)
        x = np.arange(n, dtype=float)
        slope, icpt = np.polyfit(x, y, 1)
        ss_res = float(np.sum((y - (slope * x + icpt)) ** 2))
        ss_tot = float(np.sum((y - y.mean()) ** 2))
        r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else None
    value = {"n": n, "start": ctx.d[s0], "rise": _r(rise), "up_ratio": _r(up_ratio),
             "max_dd": _r(max_dd), "r2": _r(r2)}
    text = (f"最后 {n} 根（{ctx.md(s0)} 起）：涨幅 {_pct(rise)}，收阳 {up_ratio * 100:.0f}%，"
            f"期间收盘最大回撤 {_pct(-max_dd)}，"
            f"对数价格对时间的直线拟合 R² = {'—' if r2 is None else f'{r2:.2f}'}")
    return _row("F12", text, value, [ctx.d[s0], ctx.d[ctx.ib]])


# ── 派发 ───────────────────────────────────────────────────────────────────

def _dist_row(ctx: _Ctx) -> tuple[dict, list[dict]]:
    det = DistributionDetector()
    evs = [e for e in run(det, ctx.bars) if ctx.rs <= e.start_idx <= ctx.ib]
    nrec = int(ctx.p["recent_dist_bars"])
    items = [{"date": ctx.d[e.start_idx], "vr": _r(e.vol_ratio), "upper_shadow": _r(e.upper_shadow_ratio),
              "bars_before": ctx.ib - e.start_idx} for e in evs]
    recent = any(x["bars_before"] < nrec for x in items)
    wide = [i for i in range(ctx.rs, ctx.ib + 1)
            if ctx.c[i] < ctx.o[i] and math.isfinite(ctx.vr[i]) and ctx.vr[i] >= det.vol_threshold][-6:]
    value = {"events": items, "recent_bars": nrec, "recent": recent,
             "wide": [{"date": ctx.d[i], "vr": _r(ctx.vr[i])} for i in wide]}
    rule = (f"放量 ≥ {det.vol_threshold:g} 倍、上影占整根 ≥ {det.upper_shadow_threshold:g} 的阴线")
    if not items:
        text = f"没有（{rule}）"
    else:
        text = (f"窗口里有 {len(items)} 根派发（{rule}）："
                + "；".join(f"{ctx.md(e.start_idx)} 量比 {e.vol_ratio:.1f}、上影占 {e.upper_shadow_ratio:.2f}，"
                           f"离买点 {ctx.ib - e.start_idx} 根" for e in evs)
                + f"；最近 {nrec} 根里{'有' if recent else '没有'}")
    if wide:
        text += (f"。另：窗口里收阴且量比 ≥ {det.vol_threshold:g} 的日子有 "
                 + "、".join(ctx.md(i) for i in wide))
    dates = [x["date"] for x in items]
    return _row("F13", text, value, dates), items


# ── 回踩 ───────────────────────────────────────────────────────────────────

def _tb_row(ctx: _Ctx) -> tuple[dict, list[dict]]:
    bos = [b for b in run_bundle(BODetector(), ctx.bars)["bo"] if ctx.rs <= b.start_idx <= ctx.ib]
    tbd = ThrowbackDetector()
    segs = []
    for bo in bos:
        for ev in tbd.detect([bo], ctx.bars):
            for s in ev.segments:
                segs.append({"bo": bo.start_idx, "a": s.start_idx, "b": s.end_idx, "exit": s.outcome,
                             # 段在买点那天被数据末尾强制收成「满窗」:当时还没走完
                             "unfinished": s.end_idx == ctx.ib and s.outcome == "timeout"})
    value = {"segments": [{"bo": ctx.d[s["bo"]], "start": ctx.d[s["a"]], "end": ctx.d[s["b"]],
                           "exit": s["exit"], "unfinished": s["unfinished"], "bars_before": ctx.ib - s["b"]}
                          for s in segs]}
    if not segs:
        text = "没有"
    else:
        text = "；".join(
            f"{ctx.md(s['bo'])} 突破后回踩，{ctx.md(s['a'])} 企稳、{ctx.md(s['b'])} 退出"
            + (f"（{UNFINISHED_TEXT}）" if s["unfinished"]
               else f"（{TB_EXIT_TEXT.get(s['exit'], s['exit'])}）") for s in segs)
    dates = [ctx.d[s["a"]] for s in segs] + [ctx.d[s["b"]] for s in segs]
    return _row("F14", text, value, dates,
                unfinished=any(s["unfinished"] for s in segs)), segs


def _retest(ctx: _Ctx, peaks: list[dict]) -> list[dict]:
    """首次越过日在买点前 retest_lookback_bars 根以内的峰;首次越过日之后到买点(含)有一天
    最低价 < 峰价、且买点收盘 > 峰价 → 记这个峰和最低价最低的那天。"""
    look = int(ctx.p["retest_lookback_bars"])
    out = []
    for p in peaks:
        fc = p["fc"]
        if fc is None or ctx.ib - fc > look or not ctx.c[ctx.ib] > p["price"]:
            continue
        lows = ctx.l[fc + 1:ctx.ib + 1]
        if len(lows) and lows.min() < p["price"]:
            j = fc + 1 + int(np.argmin(lows))
            out.append({"peak": p["idx"], "price": p["price"], "fc": fc, "low_idx": j, "low": float(ctx.l[j])})
    return out


def _retest_row(ctx: _Ctx, peaks_by: dict) -> dict:
    value, parts, dates = {}, [], []
    for var in ("close", "high"):
        hits = _retest(ctx, peaks_by[var])
        value[var] = [{"peak_date": ctx.d[x["peak"]], "price": _r(x["price"]),
                       "first_clear": ctx.d[x["fc"]], "low_date": ctx.d[x["low_idx"]],
                       "low": _r(x["low"]), "bars_before": ctx.ib - x["low_idx"]} for x in hits]
        for x in hits:
            dates += [ctx.d[x["peak"]], ctx.d[x["low_idx"]]]
        if hits:
            parts.append(f"{VARIANT_TEXT[var]}：" + "；".join(
                f"{ctx.md(x['fc'])} 越过的 {ctx.md(x['peak'])} 那个峰（{_px(x['price'])}），"
                f"{ctx.md(x['low_idx'])} 最低 {_px(x['low'])} 跌回峰下，买点收盘收回" for x in hits))
        else:
            parts.append(f"{VARIANT_TEXT[var]}：没有")
    text = ("没有（两种口径都没有）" if not value["close"] and not value["high"]
            else "；".join(parts))
    return _row("F15", text, value, dates)


# ── 口径分歧、触发、失效模板 ─────────────────────────────────────────────────

def _divergences(ctx: _Ctx, rows: dict, peaks_by: dict, dist: list[dict], runs: list[dict]) -> list[dict]:
    out = []
    n_c, n_h = rows["F01"]["value"]["n_cleared"], rows["F02"]["value"]["n_cleared"]
    if n_c != n_h:
        opts = []
        for var in ("close", "high"):
            pk = peaks_by[var]
            cl = [p for p in pk if p["cleared"]]
            miss = [p for p in pk if not p["cleared"]]
            t = f"{VARIANT_TEXT[var]}：越过 {len(cl)} 个"
            if cl:
                t += "（" + "、".join(f"{ctx.md(p['idx'])} {_px(p['price'])}" for p in cl) + "）"
            if miss:
                t += "，" + "、".join(f"{ctx.md(p['idx'])} 那个峰（{_px(p['price'])}）" for p in miss) + "没越过"
            opts.append({"variant": var, "text": t,
                         "chart_dates": sorted({ctx.d[p["idx"]] for p in pk})})
        out.append({"dvid": "DV1", "rows": ["F01", "F02"],
                    "question": "「越过峰」按收盘还是按最高价算？", "options": opts})
    nrec = int(ctx.p["recent_dist_bars"])
    if dist and not any(x["bars_before"] < nrec for x in dist):
        days = "、".join(ctx.md(ctx.d.index(x["date"])) for x in dist)
        dd = [x["date"] for x in dist]
        out.append({"dvid": "DV2", "rows": ["F13"],
                    "question": f"窗口里有派发（{days}），但离买点都超过 {nrec} 根，它算不算数？",
                    "options": [{"variant": "stricter", "text": f"这根不算剧烈（派发标准要更严）：{days}",
                                 "chart_dates": dd},
                                {"variant": "recent_only", "text": f"它离买点够远（只看最近 {nrec} 根）：{days}",
                                 "chart_dates": dd}]})
    if len(runs) >= 2:
        biggest = max(runs, key=lambda r: (r["max"], r["a"]))
        if not biggest["latest"]:
            out.append({"dvid": "DV3", "rows": ["F05"], "question": "「放量」指哪一段？",
                        "options": [{"variant": f"run{k + 1}",
                                     "text": f"{_span(ctx, r['a'], r['b'])} 最大 {_times(r['max'])}"
                                             + ("（离买点最近）" if r["latest"] else ""),
                                     "chart_dates": [ctx.d[r["a"]], ctx.d[r["b"]]]}
                                    for k, r in enumerate(runs)]})
    return out


def _triggers(ctx: _Ctx, peaks_by: dict, tb_segs: list[dict]) -> list[dict]:
    p, ib, c, o, h, l = ctx.p, ctx.ib, ctx.c, ctx.o, ctx.h, ctx.l
    out = []
    # T1 突破当天 / T2 连续突破的最后一根
    t1, t2 = {}, {}
    gap = int(p["burst_gap_bars"])
    for var in ("close", "high"):
        today = [x for x in peaks_by[var] if x["cleared"] and x["fc"] == ib]
        if today:
            t1[var] = today
            others = [x["fc"] for x in peaks_by[var] if x["cleared"] and x["fc"] is not None
                      and ib - gap <= x["fc"] < ib]
            if others:
                t2[var] = sorted(others)
    if t1:
        out.append({"tid": "T1", "kind": TRIGGERS["T1"][0], "variants": sorted(t1),
                    "text": "；".join(f"{VARIANT_TEXT[v]}口径：今天是首次收盘越过 "
                                     + "、".join(f"{ctx.md(x['idx'])} 那个峰（{_px(x['price'])}）" for x in t1[v])
                                     + "的日子" for v in ("close", "high") if v in t1),
                    "chart_dates": sorted({ctx.d[x["idx"]] for v in t1 for x in t1[v]} | {ctx.d[ib]})})
    if t2:
        out.append({"tid": "T2", "kind": TRIGGERS["T2"][0], "variants": sorted(t2),
                    "text": "；".join(f"{VARIANT_TEXT[v]}口径：前 {gap} 根内还有一次首次越过（"
                                     + "、".join(ctx.md(i) for i in t2[v]) + "），今天是这串连续突破的最后一根"
                                     for v in ("close", "high") if v in t2),
                    "chart_dates": sorted({ctx.d[i] for v in t2 for i in t2[v]} | {ctx.d[ib]})})
    n = int(p["new_high_bars"])
    if ib >= n and c[ib] > c[ib - n:ib].max():
        out.append({"tid": "T3", "kind": TRIGGERS["T3"][0], "variants": [],
                    "text": f"收盘创 {n} 日新高（{_px(c[ib])} 高于前 {n} 根的最高收盘 {_px(c[ib - n:ib].max())}）",
                    "chart_dates": [ctx.d[ib]]})
    pb, pbh = int(p["pullback_bars"]), int(p["pullback_high_bars"])
    if ib >= pbh:
        drop = l[ib - pb:ib].min() / h[ib - pbh:ib].max() - 1.0
        if drop < -float(p["pullback_min"]) and c[ib] > h[ib - 1]:
            out.append({"tid": "T4", "kind": TRIGGERS["T4"][0], "variants": [],
                        "text": f"前 {pb} 根的最低比前 {pbh} 根的最高回落了 {_pct(drop)}，今天收盘高过昨天最高",
                        "chart_dates": [ctx.d[ib - 1], ctx.d[ib]]})
    t5 = {}
    look = int(p["retest_lookback_bars"])
    for var in ("close", "high"):
        hit = [x for x in peaks_by[var] if x["fc"] is not None and ib - look <= x["fc"] < ib
               and l[ib] < x["price"] < c[ib]]
        if hit:
            t5[var] = hit
    if t5:
        out.append({"tid": "T5", "kind": TRIGGERS["T5"][0], "variants": sorted(t5),
                    "text": "；".join(f"{VARIANT_TEXT[v]}口径：当天盘中跌到 "
                                     + "、".join(f"{ctx.md(x['fc'])} 越过的峰（{_px(x['price'])}）" for x in t5[v])
                                     + "之下，收盘收回" for v in ("close", "high") if v in t5),
                    "chart_dates": sorted({ctx.d[x["fc"]] for v in t5 for x in t5[v]} | {ctx.d[ib]})})
    if ib >= 1:
        g = o[ib] / c[ib - 1] - 1.0
        if abs(g) >= float(p["gap_abs"]):
            out.append({"tid": "T6", "kind": TRIGGERS["T6"][0], "variants": [],
                        "text": f"当天跳空 {_pct(g)}（开盘相对前一天收盘）", "chart_dates": [ctx.d[ib]]})
    vr = ctx.vr[ib]
    if math.isfinite(vr) and vr < float(p["dry_day_ratio"]):    # 停牌(当天没成交)量比判定不了,不算缩量
        out.append({"tid": "T7", "kind": TRIGGERS["T7"][0], "variants": [],
                    "text": f"当天缩量（量比 {vr:.2f}，低于 {p['dry_day_ratio']:g}）", "chart_dates": [ctx.d[ib]]})
    starts = [s for s in tb_segs if s["a"] == ib]
    if starts:
        out.append({"tid": "T8", "kind": TRIGGERS["T8"][0], "variants": [],
                    "text": "今天是突破后回踩企稳段的起点（" + "、".join(f"{ctx.md(s['bo'])} 突破" for s in starts) + "）",
                    "chart_dates": sorted({ctx.d[s["bo"]] for s in starts} | {ctx.d[ib]})})
    return out


def _invalidation(peaks_by: dict) -> list[dict]:
    out = []
    if any(p["cleared"] for v in ("close", "high") for p in peaks_by[v]):
        out.append({"iid": "I1", "text": INVALIDATIONS["I1"]})
    out.append({"iid": "I2", "text": INVALIDATIONS["I2"]})
    return out


# ── 入口 ───────────────────────────────────────────────────────────────────

def compute_facts(df: pd.DataFrame, buy_date: str, range_start: str | None = None,
                  fcfg: dict | None = None, features_cfg: dict | None = None,
                  m_period: int = 20) -> dict:
    """纯函数。第一步就把 df 截到 buy_date(含)——调用方传进更长的 df 也只读到买点。
    buy_date 不是 df 里的交易日 → ValueError。range_start 为空时窗口起点取买点前
    default_lookback_bars 个交易日(window_source="default")。"""
    fcfg = {**DEFAULTS["facts"], **(fcfg or {})}
    features_cfg = {**DEFAULTS["features"], **(features_cfg or {})}
    if getattr(df.index, "tz", None) is not None:
        df = df.copy()
        df.index = df.index.tz_localize(None)
    t = pd.Timestamp(buy_date)
    df = df.sort_index()
    df = df.loc[df.index <= t, ["open", "high", "low", "close", "volume"]]
    if len(df) == 0 or df.index[-1] != t:
        raise ValueError(f"买点 {buy_date} 不是这只股票的交易日")
    df.index.name = "date"
    ib = len(df) - 1
    if range_start:
        if pd.Timestamp(range_start) > t:
            raise ValueError(f"框选起点 {range_start} 晚于买点 {buy_date}")
        rs, src = int(df.index.searchsorted(pd.Timestamp(range_start))), "box"
    else:
        rs, src = max(0, ib - int(fcfg["default_lookback_bars"])), "default"
    ctx = _Ctx(df, rs, fcfg, features_cfg, m_period)

    peaks_by = {"close": _swing_peaks(ctx, ctx.c), "high": _swing_peaks(ctx, ctx.h)}
    runs = _vol_runs(ctx)
    M = _m_series(ctx)
    f13, dist = _dist_row(ctx)
    f14, tb_segs = _tb_row(ctx)
    rows = [
        _peaks_row(ctx, "F01", "close", peaks_by["close"]),
        _peaks_row(ctx, "F02", "high", peaks_by["high"]),
        _burst_row(ctx, peaks_by),
        _oldest_row(ctx, peaks_by),
        _vol_runs_row(ctx, runs),
        _dry_row(ctx, runs),
        _today_vol_row(ctx),
        _pre_state_row(ctx, M),
        _trend_row(ctx),
        _gap_row(ctx, M),
        _platform_row(ctx),
        _steady_row(ctx),
        f13,
        f14,
        _retest_row(ctx, peaks_by),
    ]
    by_fid = {r["fid"]: r for r in rows}
    divs = _divergences(ctx, by_fid, peaks_by, dist, runs)
    for dv in divs:
        for fid in dv["rows"]:
            by_fid[fid]["divergence"] = dv["dvid"]
    return {
        "schema": SCHEMA, "facts_code": FACTS_CODE, "symbol": None, "buy_date": ctx.d[ib],
        "window": [ctx.d[rs], ctx.d[ib]], "window_source": src,
        "rows": rows, "divergences": divs,
        "triggers": _triggers(ctx, peaks_by, tb_segs),
        "invalidation_templates": _invalidation(peaks_by),
    }


def facts_for(cfg: dict, symbol: str, buy_date: str, range_start: str | None = None) -> dict:
    """经 loader.read_bars(cfg, symbol, until=buy_date) 读数据后调 compute_facts。
    年份闸:buy_date 早于 cfg["view_floor"] 或晚于 cfg["train_end"] → ValueError。"""
    floor = cfg.get("view_floor")
    if floor and buy_date < floor:
        raise ValueError(f"买点 {buy_date} 早于本轮看图下界 {floor}")
    if buy_date > cfg["train_end"]:
        raise ValueError(f"买点 {buy_date} 晚于训练段末日 {cfg['train_end']}")
    df = read_bars(cfg, symbol, until=buy_date)
    out = compute_facts(df, buy_date, range_start, fcfg=cfg["facts"],
                        features_cfg=cfg["features"], m_period=cfg["m_period"])
    out["symbol"] = symbol
    return out


def render(f: dict) -> str:
    """一张事实表的人话打印:分组、①②… 编号、分歧、命中的触发、失效模板。"""
    lines = [f"{f['symbol']} 买点 {f['buy_date']}  窗口 {f['window'][0]} → {f['window'][1]}"
             f"（{'你框的起点' if f['window_source'] == 'box' else '没框,取买点前一段'}）"]
    group = None
    for k, r in enumerate(f["rows"]):
        if r["group"] != group:
            group = r["group"]
            lines.append(f"\n【{group}】")
        tag = f"  ⟨口径分歧 {r['divergence']}⟩" if r["divergence"] else ""
        src = r.get("source") or PRESET
        if src.get("kind") == "user":
            tag += f"  ⟨你提的角度，{src.get('date')}⟩"
        lines.append(f"{CIRCLED[k]} {r['title']}：{r['text']}{tag}")
    if f["divergences"]:
        lines.append("\n【口径分歧】")
        for dv in f["divergences"]:
            lines.append(f"{dv['dvid']} {dv['question']}")
            for o in dv["options"]:
                lines.append(f"    · {o['text']}")
    lines.append("\n【买点当天命中的触发】")
    lines += ([f"{t['tid']} {t['text']}" for t in f["triggers"]]
              or ["(一个都没命中,请用户自己说一句)"])
    lines.append("\n【买前失效(模板,不预勾)】")
    lines += [f"{i['iid']} {i['text']}" for i in f["invalidation_templates"]]
    return "\n".join(lines)


def source_text(src: dict) -> str:
    if src.get("kind") == "user":
        return f"你提的角度（{src.get('date')}，原话「{src.get('said')}」，操作日志 {src.get('op_id')}）"
    return "预设"


def check_rows(rows: dict | None = None) -> list[str]:
    """事实行登记本身的问题:字段缺失、标题重复、出处不合格(用户提的要写 date / said / op_id)。"""
    rows = ROWS if rows is None else rows
    errs, titles = [], {}
    for fid, d in rows.items():
        if not (isinstance(d.get("group"), str) and isinstance(d.get("title"), str)
                and isinstance(d.get("reads"), tuple) and d["reads"]):
            errs.append(f"{fid}: 要有 group、title 和非空的 reads")
        src = d.get("source") or {}
        if src.get("kind") == "user":
            miss = [k for k in ("date", "said", "op_id") if not str(src.get(k) or "").strip()]
            if miss:
                errs.append(f"{fid}: 用户提的角度要写 {'、'.join(miss)}")
        elif src != PRESET:
            errs.append(f"{fid}: source 只能是预设或用户提的角度")
        if d.get("title") in titles:
            errs.append(f"{fid}: 标题和 {titles[d['title']]} 重复")
        titles.setdefault(d.get("title"), fid)
    return errs


def check_new_row(title: str, reads, rows: dict | None = None) -> list[str]:
    """新增一行之前的查重提示(只提示,不拦):同名的行、读的量完全相同的行、读到相同量的行。"""
    rows = ROWS if rows is None else rows
    title = " ".join(str(title).split())
    reads = {str(x).strip() for x in reads if str(x).strip()}
    known = {x for d in rows.values() for x in d["reads"]}
    hints = []
    for fid, d in rows.items():
        if " ".join(d["title"].split()) == title:
            hints.append(f"同名：{fid}「{d['title']}」")
    for fid, d in rows.items():
        shared = reads & set(d["reads"])
        if not shared:
            continue
        how = "读的量完全相同" if set(d["reads"]) == reads else f"也读 {'、'.join(sorted(shared))}"
        hints.append(f"{how}：{fid}「{d['title']}」（读 {'、'.join(d['reads'])}）")
    unknown = sorted(reads - known)
    if unknown:
        hints.append(f"现有行都没读过的量：{'、'.join(unknown)}（现有的量：{'、'.join(sorted(known))}）")
    return hints


def source_warnings(ops: list[dict], rows: dict | None = None) -> list[str]:
    """用户提的角度做成的行,操作日志里找不到那次提的条目(op_id,act = propose_fact)就报。"""
    rows = ROWS if rows is None else rows
    proposed = {o.get("op_id") for o in ops if o.get("act") == "propose_fact"}
    return [f"{fid}: 出处写的操作日志条目 {d['source'].get('op_id')} 不在日志里(或不是 propose_fact)"
            for fid, d in rows.items()
            if d["source"].get("kind") == "user" and d["source"].get("op_id") not in proposed]


def render_rows() -> str:
    lines = [f"{fid} {d['group']}／{d['title']}  读 {'、'.join(d['reads'])}  出处：{source_text(d['source'])}"
             for fid, d in ROWS.items()]
    try:
        from chart_workflow.oplog import read_all
        lines += [f"⚠ {w}" for w in source_warnings(read_all())]
    except StateRootMissing as e:
        lines.append(f"(没核对出处里的操作日志条目:{e})")
    return "\n".join(lines)


def write_snapshot(batch_id: str, results: list[dict], stem: str | None = None) -> Path:
    """写 <状态根>/facts/<stem>.json(已存在就加 -2、-3……,只增不改)。"""
    d = state_root() / "facts"
    d.mkdir(parents=True, exist_ok=True)
    stem = stem or batch_id
    path, k = d / f"{stem}.json", 1
    while path.exists():
        k += 1
        path = d / f"{stem}-{k}.json"
    doc = {"schema": SNAPSHOT_SCHEMA, "created_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
           "batch_id": batch_id, "results": results}
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=1))
    tmp.replace(path)
    advance(d.parent)                    # 新文件记进水位
    return path


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="事实表")
    ap.add_argument("--batch", help="标注批次 id(读 <状态根>/annotations/<id>.json)")
    ap.add_argument("--ann", help="只算这一条标注")
    ap.add_argument("--symbol")
    ap.add_argument("--buy-date")
    ap.add_argument("--range-start")
    ap.add_argument("--json", action="store_true", help="只把结果 JSON 打到标准输出")
    ap.add_argument("--rows", action="store_true", help="列出全部事实行(计算方法)与出处")
    ap.add_argument("--check-row", metavar="TITLE", help="新增事实行之前查重:同名或读同样量的已有行")
    ap.add_argument("--reads", default="", help="和 --check-row 一起:新行读哪些量,逗号分隔")
    args = ap.parse_args(argv)
    if args.rows:
        print(render_rows())
        return
    if args.check_row:
        hints = check_new_row(args.check_row, args.reads.split(","))
        print("\n".join(hints) if hints else "没有同名或读同样量的已有行")
        return
    if bool(args.batch) == bool(args.symbol):
        ap.error("--batch 与 --symbol 二选一")
    cfg = load_config()
    results, errors = [], []
    try:
        root = state_root()
        if args.batch:
            batch = read_batch(root / "annotations" / f"{args.batch}.json")
            anns = [a for a in batch["annotations"] if not args.ann or a["ann_id"] == args.ann]
            if args.ann and not anns:
                raise ValueError(f"批次 {args.batch} 里没有标注 {args.ann}")
            for a in anns:
                for bp in a["buy_points"]:
                    try:
                        f = facts_for(cfg, a["symbol"], bp["date"], a.get("range_start"))
                    except (ValueError, FileNotFoundError) as e:
                        errors.append(f"{a['symbol']} {bp['date']}({a['ann_id']}):{e}")
                        continue
                    results.append({"ann_id": a["ann_id"], "item_id": a["item_id"], "facts": f})
            batch_id, stem = args.batch, None
        else:
            if not args.buy_date:
                ap.error("--symbol 要和 --buy-date 一起给")
            f = facts_for(cfg, args.symbol, args.buy_date, args.range_start)
            results.append({"ann_id": None, "item_id": None, "facts": f})
            batch_id = None
            stem = "adhoc-" + datetime.now().strftime("%Y%m%dT%H%M%S")
        path = write_snapshot(batch_id, results, stem) if results else None
    except (ValueError, FileNotFoundError, StateRootMissing) as e:
        print(f"错误:{e}", file=sys.stderr)
        sys.exit(2)
    out = sys.stderr if args.json else sys.stdout
    if args.json:
        print(json.dumps({"snapshot": str(path) if path else None, "results": results,
                          "errors": errors}, ensure_ascii=False))
    else:
        for r in results:
            print(("—" * 40) + (f"\n标注 {r['ann_id']}" if r["ann_id"] else ""))
            print(render(r["facts"]))
    for e in errors:
        print(f"跳过 {e}", file=sys.stderr)
    if path:
        print(f"\n快照 → {path}", file=out)


if __name__ == "__main__":
    main()
