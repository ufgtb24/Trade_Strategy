# -*- coding: utf-8 -*-
"""tune-gates · 确认窗:从数据覆盖推算边界 + 读标签入口的机械守卫。

调参只准读训练窗的标签。训练窗前后各留一段确认窗(往前 backward / 前向 forward),与训练窗
之间各隔一个 label 窗长,两边的标签不共用同一段行情;调参结束、验证清单冻结之后,由
validate 各开一次。边界不靠人记,由 `confirm_windows` 从数据文件的实际覆盖算出,写进账本
的 open 记录;所有读标签的入口(scan 完整标签模式、cell、find、screen、edge、validate、
extract.build_from_longtable、fs.run)先调 `guard_label_access`。

数据覆盖的口径(`probe_coverage`):按文件名排序后以固定种子抽样 n_sample 只股票,
每只只取日期索引;某日被 ≥ 一半的抽样股覆盖才算「全市场有数据」,data_start / data_end
= 这样的日子里最早 / 最晚的一天。用多数口径而不是全体并集的首尾,是为了不让个别异常文件
(下载更早或更晚、日期错位)把边界拉走;晚上市股、退市股在任一端都是少数,也不影响。
交易日历 = 抽样股日期并集截到 [data_start, data_end]。
"""
from __future__ import annotations

import functools
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

SKILL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SKILL_DIR))

import ledger  # noqa: E402

REPO = ledger.REPO
sys.path.insert(0, str(REPO))

MIN_COVER_FRAC = 0.5
WINDOW_WORDS = {"backward": "训练期之前留出的那段验证数据", "forward": "训练期之后留出的那段验证数据"}


class HoldoutLocked(PermissionError):
    """读取被确认窗守卫拒绝。消息是给用户看的人话;reason 供调用方分支:
      no_open              app 还没有 open 记录
      confirm_overlap      读取与确认窗重叠,且没有可用的例外
      validate_refused     validate 例外的拒绝条件之一成立
      gate_family_refused  闸子族补检的放行条件缺了一条"""
    REASONS = ("no_open", "confirm_overlap", "validate_refused", "gate_family_refused")

    def __init__(self, message: str, *, reason: str):
        if reason not in self.REASONS:
            raise ValueError(f"未知的拒绝原因 {reason!r},只能是 {self.REASONS}")
        super().__init__(message)
        self.reason = reason


# ---------------------------------------------------------------- 数据覆盖与交易日历

@functools.lru_cache(maxsize=8)
def _probe(data_dir: str, n_sample: int, seed: int) -> tuple:
    pkls = sorted(Path(data_dir).glob("*.pkl"))
    if not pkls:
        raise FileNotFoundError(f"数据目录里没有股票数据文件: {data_dir}")
    pick = np.sort(np.random.default_rng(seed).choice(len(pkls), size=min(n_sample, len(pkls)), replace=False))
    per_stock = []
    for i in pick:
        idx = pd.DatetimeIndex(pd.read_pickle(pkls[i]).index).normalize().unique()
        if len(idx):
            per_stock.append(idx.values)
    if not per_stock:
        raise ValueError(f"抽到的股票数据文件全是空的: {data_dir}")
    cover = pd.Series(np.concatenate(per_stock)).value_counts()
    days = pd.DatetimeIndex(cover.index)
    majority = days[cover.values >= MIN_COVER_FRAC * len(per_stock)]
    data_start, data_end = majority.min(), majority.max()
    days = days.sort_values()
    return days[(days >= data_start) & (days <= data_end)], data_start, data_end, len(per_stock)


def trading_calendar(data_dir, n_sample: int = 400, seed: int = 0) -> pd.DatetimeIndex:
    """抽样股日期并集(截到 data_start..data_end),确定性抽样,结果缓存。"""
    return _probe(str(Path(data_dir).resolve()), n_sample, seed)[0]


def probe_coverage(data_dir, n_sample: int = 400, seed: int = 0) -> dict:
    """{"data_start", "data_end", "n_probed"}:口径见模块文档;n_probed = 抽到的非空数据文件数。"""
    _, start, end, n = _probe(str(Path(data_dir).resolve()), n_sample, seed)
    return {"data_start": start.strftime("%Y-%m-%d"), "data_end": end.strftime("%Y-%m-%d"), "n_probed": n}


def default_data_dir() -> Path:
    """数据目录单一来源:configs/path2_web.yaml 的 dataset_dir(相对路径按 REPO 解析)。"""
    from path2_web.config import load_config
    d = Path(load_config()["dataset_dir"])
    return d if d.is_absolute() else REPO / d


def default_calendar() -> pd.DatetimeIndex:
    return trading_calendar(default_data_dir())


# ---------------------------------------------------------------- 确认窗推算

def _day(t) -> str:
    return pd.Timestamp(t).strftime("%Y-%m-%d")


def confirm_windows(train_start, train_end, *, calendar, head_buffer: int, horizon: int) -> dict:
    """由训练窗与交易日历推出两段确认窗,返回与 open 记录 data 同形的 dict(n_probed 由调用方补)。

    日历首尾即 data_start / data_end。规则:
      前向 start = 训练窗 label_end 之后第一个交易日;end = 使 label_end(end) <= data_end 的最后一个交易日。
      往前 end   = 使 label_end(end) < 训练窗 start 的最后一个交易日;start = data_start 之后第 head_buffer 个交易日。
    于是训练窗与两段确认窗的 [start, label_end] 两两不相交。任一段排不下(数据不够)→ ValueError。"""
    cal = pd.DatetimeIndex(calendar).normalize().unique().sort_values()
    ts, te = pd.Timestamp(train_start), pd.Timestamp(train_end)
    if ts > te:
        raise ValueError(f"训练窗起点晚于终点: {train_start} > {train_end}")
    train_le = ledger.label_end(te, horizon, cal)

    f0 = cal.searchsorted(train_le, side="right")
    f1 = len(cal) - 1 - horizon                      # label_end(cal[p]) = cal[p + horizon] <= cal[-1]
    if f0 > f1:
        raise ValueError(f"训练窗之后的新数据还不够:训练期买点的涨跌结果要看到 {_day(train_le)},"
                         f"数据只到 {_day(cal[-1])},排不出一段带 {horizon} 个交易日结果的验证数据")
    j = cal.searchsorted(ts, side="left")            # 训练窗第一个交易日
    b1 = j - horizon - 1                             # cal[p + horizon] < cal[j]
    b0 = head_buffer
    if b0 > b1:
        raise ValueError(f"训练窗之前的历史数据不够:数据从 {_day(cal[0])} 开始,扣掉 {head_buffer} 个交易日的"
                         f"回看缓冲和 {horizon} 个交易日的隔离期后,排不出验证数据")

    def seg(p0, p1):
        return {"start": _day(cal[p0]), "end": _day(cal[p1]), "label_end": _day(ledger.label_end(cal[p1], horizon, cal))}

    return {"data_start": _day(cal[0]), "data_end": _day(cal[-1]),
            "train": {"start": _day(ts), "end": _day(te), "label_end": _day(train_le)},
            "confirm": {"backward": seg(b0, b1), "forward": seg(f0, f1)}}


# ---------------------------------------------------------------- 守卫

def guard_label_access(app, buy_start, buy_end, purpose: str, *, manifest_hash: str | None = None,
                       confirm_window: str | None = None, calendar=None) -> None:
    """读标签之前调用;不允许 → HoldoutLocked(人话)。

    - app 没有 open 记录 → 拒绝。
    - 读取区间 [buy_start, label_end(buy_end)] 与最新 open 记录的任一确认窗 [start, label_end] 相交 → 拒绝。
    - 例外只有两种,都要给 manifest_hash、confirm_window,且读取只碰到 confirm_window 那一段:
      purpose == "validate":`_validate_refusal` 的五条拒绝条件全不成立(正式开窗);
      purpose == "gate_family":`_gate_family_refusal` 的三条放行条件全满足(学习端在同一次开窗里
      补检闸子族,不算再开一次窗)。
    calendar 缺省用数据目录的交易日历(单测传合成日历)。label 后缀长度取 open 记录的 label_horizon。"""
    if confirm_window is not None and confirm_window not in WINDOW_WORDS:
        raise ValueError(f"confirm_window 只能是 {tuple(WINDOW_WORDS)} 之一: {confirm_window!r}")
    if pd.Timestamp(buy_start) > pd.Timestamp(buy_end):
        raise ValueError(f"读取区间起点晚于终点: {buy_start} > {buy_end}")
    recs = ledger.read(app)
    opens = [r for r in recs if r["kind"] == "open"]
    if not opens:
        raise HoldoutLocked(f"「{app}」还没做开局核对:还没划出哪几段数据要留到最后做验证,"
                            "所以现在不能读任何涨跌结果。请先做开局核对。", reason="no_open")
    op = opens[-1]
    cal = default_calendar() if calendar is None else calendar
    horizon = op["label_horizon"]
    read = {"start": buy_start, "end": buy_end}
    hits = [n for n in WINDOW_WORDS if ledger.overlaps(read, op["data"]["confirm"][n], horizon, cal)]
    if not hits:
        return
    if purpose in ("validate", "gate_family") and manifest_hash and confirm_window:
        if hits != [confirm_window]:
            other = WINDOW_WORDS[next(n for n in hits if n != confirm_window)]
            raise HoldoutLocked(f"这次读取碰到了{other},而这次声明要打开的是{WINDOW_WORDS[confirm_window]};"
                                "一次只能打开声明的那一段。", reason="confirm_overlap")
        if purpose == "validate":
            why, code = _validate_refusal(recs, op, manifest_hash, confirm_window, cal), "validate_refused"
        else:
            why, code = _gate_family_refusal(recs, manifest_hash, confirm_window), "gate_family_refused"
        if why is None:
            return
        raise HoldoutLocked(why, reason=code)
    names = "、".join(f"{WINDOW_WORDS[n]}({op['data']['confirm'][n]['start']} 到 {op['data']['confirm'][n]['end']} 的买点)"
                     for n in hits)
    raise HoldoutLocked(f"这次要读 {_day(buy_start)} 到 {_day(buy_end)} 的买点(连同之后 {horizon} 个交易日的涨跌结果),"
                        f"和{names}重叠了。这段时间的数据是留给最后验证用的,调参阶段不能读它的涨跌结果。",
                        reason="confirm_overlap")


def _gate_list_only(manifest) -> bool:
    """学习端轮外单独冻结的闸清单:只有闸子族、没有确认子族。它不是调参的验证清单,不参与「是不是最新」的比较。"""
    return isinstance(manifest, dict) and "gate_family" in manifest and "family" not in manifest


def _validate_refusal(recs: list, op: dict, manifest_hash: str, confirm_window: str, cal) -> str | None:
    """§4.5 五条拒绝条件,任一成立返回拒绝理由(人话),全不成立返回 None。"""
    pre = [r for r in recs if r["kind"] == "preregister"]
    mine = [r for r in pre if r["data"]["manifest_hash"] == manifest_hash]
    if not mine:
        return "要打开留作最后验证的数据,必须先把验证内容冻结成清单;这份清单没有冻结记录,不能打开。"
    p = mine[-1]
    if datetime.fromisoformat(p["ts"]) >= datetime.now():
        return "这份验证清单的冻结时间不早于这次打开,不算「先冻结、后开窗」,不能打开。"

    def ruled(topic):
        return any(r["kind"] == "ruling" and r["data"]["topic"] == topic and r["data"].get("manifest_hash") == manifest_hash
                   for r in recs)

    if not ruled("power_notified"):
        return "这份验证清单的预期把握还没有告诉用户,不能打开留作最后验证的数据。"
    power = p["data"]["expected_power"][confirm_window]
    if power < 0.5 and not ruled("open_low_power"):
        return (f"按这份清单,{WINDOW_WORDS[confirm_window]}验证出结果的预期把握只有约 {power:.0%},不到一半;"
                "用户还没有明确同意在把握不足时照样打开,不能打开。")
    cw = op["data"]["confirm"][confirm_window]
    if any(r["kind"] == "extrapolate" and ledger.overlaps(r["window"], cw, op["label_horizon"], cal) for r in recs):
        return f"{WINDOW_WORDS[confirm_window]}已经打开过一次了,每段留作最后验证的数据只能打开一次。"
    comparable = [r for r in pre if r["data"]["manifest_hash"] == manifest_hash or not _gate_list_only(r["data"]["manifest"])]
    latest = max(enumerate(comparable), key=lambda ir: (datetime.fromisoformat(ir[1]["ts"]), ir[0]))[1]
    if latest["data"]["manifest_hash"] != manifest_hash:
        return "这份验证清单不是最新冻结的那一份,只能按最新的清单打开。"
    return None


def _gate_family_refusal(recs: list, manifest_hash: str, confirm_window: str) -> str | None:
    """闸子族补检的三条放行条件,缺哪条返回哪条的拒绝理由(人话),全满足返回 None:
      a. 这一段已按这份清单开过(extrapolate,清单哈希与确认窗都对上);
      b. 这份清单的 preregister 里 manifest 带非空的 gate_family;
      c. 闸子族在这一段还没按这份清单检过(无同清单同确认窗的 verify)。"""
    def same(r):
        return r["data"].get("manifest_hash") == manifest_hash and r["data"].get("confirm_window") == confirm_window

    words = WINDOW_WORDS[confirm_window]
    if not any(r["kind"] == "extrapolate" and same(r) for r in recs):
        return f"{words}还没有按这份验证清单打开过;闸的补检只能跟在这一段的正式验证之后做。"
    mine = [r for r in recs if r["kind"] == "preregister" and r["data"]["manifest_hash"] == manifest_hash]
    manifest = mine[-1]["data"]["manifest"] if mine else None
    if not (isinstance(manifest, dict) and manifest.get("gate_family")):
        return "这份验证清单里没有列出要检验的闸(或找不到这份清单的冻结记录),不能借它在留作验证的数据上检验闸。"
    if any(r["kind"] == "verify" and same(r) for r in recs):
        return f"这份验证清单里的闸已经在{words}上检验过一次了,每段只能检验一次。"
    return None
