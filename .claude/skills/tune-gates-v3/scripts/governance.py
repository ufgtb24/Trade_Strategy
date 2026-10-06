"""v3 的数据使用记录与采用规则；先记消费，再允许调用方读取行情。

本模块不读取股价、不自动补交易日历，也不复用 v1 的流程状态。使用同一账本的
v3 进程通过文件锁串行检查、追加；v1 写入器没有相同的锁纪律，因此同一个 app
不能同时运行 v1 与 v3。calendar 必须是完整、可信的交易日期列表，用于展开旧
账本的前瞻区间。v1 最新 open 的预留数据也受保护。反方向不自动同步：再次使用
v1 前必须核对 v3 账本，不能仅凭旧守卫宣称数据未见。账本不替代如实登记其他研究。
"""
from __future__ import annotations

from bisect import bisect_right
from contextlib import contextmanager
from datetime import date, datetime, timezone
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
from typing import Iterator

BURN_KINDS = frozenset(("discover", "select", "verify", "reconcile", "extrapolate"))
LEGACY_KINDS = BURN_KINDS | {"open", "ruling", "edge", "preregister", "decide"}
STAGES = frozenset(("training", "final", "review"))
SCORE_EPSILON = 1e-12  # 只消除浮点汇总误差，不代表最小业务收益。
_SHA = re.compile(r"[0-9a-f]{64}\Z")


class UsageError(ValueError):
    """使用记录不完整、配置漂移或数据已经暴露；调用方必须停止读取。"""


def canonical_hash(obj: object) -> str:
    """对标准 JSON 对象求稳定摘要；不接受 NaN、Infinity 或非 JSON 值。"""
    raw = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                     allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _date(value: object) -> date:
    if not isinstance(value, str):
        raise UsageError(f"日期必须是 YYYY-MM-DD 字符串，收到 {value!r}")
    try:
        result = date.fromisoformat(value)
    except ValueError as exc:
        raise UsageError(f"无效日期 {value!r}；请使用 YYYY-MM-DD") from exc
    if result.isoformat() != value:
        raise UsageError(f"日期格式不规范 {value!r}；请使用 YYYY-MM-DD")
    return result


def _interval(start: str, end: str, label_end: str) -> dict:
    if not _date(start) <= _date(end) <= _date(label_end):
        raise UsageError("区间必须满足 start <= end <= label_end")
    return {"start": start, "end": end, "label_end": label_end}


def _overlap(a: dict, b: dict) -> bool:
    # 日期均经过规范化，字符串序与日期序一致；首尾均为闭区间。
    return a["start"] <= b["label_end"] and b["start"] <= a["label_end"]


def _identity(app: str, run_id: str, config_hash: str) -> None:
    if not all(isinstance(x, str) and x.strip() for x in (app, run_id)):
        raise UsageError("app 和 run_id 必须是非空字符串")
    if not isinstance(config_hash, str) or not _SHA.fullmatch(config_hash):
        raise UsageError("config_hash 必须是规范的 SHA-256 摘要")


def _read_lines(raw: bytes, path: Path) -> list[dict]:
    if not raw:
        return []
    if not raw.endswith(b"\n"):
        raise UsageError(f"{path} 尾行未完整提交；停止使用，不能丢弃可能的消费记录")
    result = []
    for index, line in enumerate(raw.splitlines(), 1):
        try:
            record = json.loads(line.decode("utf-8"), parse_constant=lambda v: (_ for _ in ()).throw(ValueError(v)))
        except (UnicodeDecodeError, ValueError) as exc:
            raise UsageError(f"{path} 第 {index} 行损坏；需要先核对使用记录") from exc
        if not isinstance(record, dict):
            raise UsageError(f"{path} 第 {index} 行必须是 JSON 对象")
        result.append(record)
    return result


def _validate_v3(record: dict) -> None:
    needed = {"schema", "kind", "app", "run_id", "config_hash", "ts"}
    if record.get("kind") != "abandon":
        needed |= {"stage", "start", "end", "label_end"}
    if set(record) != needed or record.get("schema") != "tune-gates-v3/1":
        raise UsageError("v3 账本出现未知结构；不能推测其消费范围")
    if record["kind"] not in ("reserve", "claim", "abandon"):
        raise UsageError("v3 账本出现未知操作或阶段")
    if record["kind"] != "abandon" and record["stage"] not in STAGES:
        raise UsageError("v3 账本出现未知阶段")
    if record["kind"] == "reserve" and record["stage"] == "training":
        raise UsageError("训练区间不能登记为最终检查预留区间")
    _identity(record["app"], record["run_id"], record["config_hash"])
    if record["kind"] != "abandon":
        _interval(record["start"], record["end"], record["label_end"])
    if not isinstance(record["ts"], str):
        raise UsageError("使用记录缺少写入时间")
    try:
        datetime.fromisoformat(record["ts"])
    except ValueError as exc:
        raise UsageError("使用记录写入时间损坏") from exc


class UsageLedger:
    """小型追加账本，确保最终检查只读一次且与已消耗区间分开。

    ``reserve`` 在搜索前一次性固定 final 与 review 两个区间。``claim`` 必须在
    标签计算与检测之前执行；登记前只允许读文件末日检查行情是否到齐。它成功
    返回后即视为已经消耗。中断不能重试
    final/review。训练可以重复，但不能进入任何尚未消费的预留区间。abandon 关闭
    本轮并释放未消费预留，不删除暴露记录，不允许重新开启同一轮。
    """

    def __init__(self, path: Path, legacy_path: Path | None = None,
                 calendar: list[str] | None = None):
        self.path = Path(path)
        self.legacy_path = Path(legacy_path) if legacy_path is not None else None
        if self.legacy_path is not None and self.path.resolve() == self.legacy_path.resolve():
            raise UsageError("v3 与 v1 必须使用不同账本文件")
        self.calendar = None
        if calendar is not None:
            parsed = [_date(value) for value in calendar]
            if not parsed or parsed != sorted(set(parsed)):
                raise UsageError("交易日历必须非空、递增且不重复")
            self.calendar = parsed

    @contextmanager
    def _locked(self) -> Iterator[tuple[object, list[dict]]]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a+b") as stream:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            try:
                stream.seek(0)
                records = _read_lines(stream.read(), self.path)
                for record in records:
                    _validate_v3(record)
                yield stream, records
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    @staticmethod
    def _append(stream, records: list[dict]) -> None:
        for record in records:
            _validate_v3(record)
        stream.seek(0, os.SEEK_END)
        stream.write(b"".join((json.dumps(rec, ensure_ascii=False, sort_keys=True,
                                         allow_nan=False) + "\n").encode("utf-8")
                              for rec in records))
        stream.flush()
        os.fsync(stream.fileno())

    def records(self) -> list[dict]:
        """读取记录用于审计，不改变已消费状态。"""
        with self._locked() as (_, records):
            return records

    @staticmethod
    def _same_run(records: list[dict], app: str, run_id: str, config_hash: str,
                  allow_closed: bool = False) -> list[dict]:
        selected = [r for r in records if r["app"] == app and r["run_id"] == run_id]
        if any(r["config_hash"] != config_hash for r in selected):
            raise UsageError("同一次 run 的冻结配置发生变化；禁止继续读取")
        if not allow_closed and any(r["kind"] == "abandon" for r in selected):
            raise UsageError("本轮已经关闭；不能恢复预留或继续读取")
        return selected

    @staticmethod
    def _active_reservations(records: list[dict], app: str) -> list[dict]:
        consumed = {(r["run_id"], r["stage"]) for r in records
                    if r["app"] == app and r["kind"] == "claim"}
        closed = {r["run_id"] for r in records if r["app"] == app and r["kind"] == "abandon"}
        return [r for r in records if r["app"] == app and r["kind"] == "reserve"
                and r["run_id"] not in closed and (r["run_id"], r["stage"]) not in consumed]

    def _legacy_records(self, app: str) -> list[dict]:
        if self.legacy_path is None or not self.legacy_path.exists():
            return []
        records = _read_lines(self.legacy_path.read_bytes(), self.legacy_path)
        for rec in records:
            if rec.get("schema") != 1 or rec.get("kind") not in LEGACY_KINDS or not isinstance(rec.get("app"), str):
                raise UsageError("v1 账本含未知记录，不能确认哪些数据尚未使用")
        return [r for r in records if r["app"] == app]

    def _legacy_reserved(self, app: str) -> list[dict]:
        """保持旧守卫的最新 open 两段保护；decide 不意味着释放预留。"""
        records = self._legacy_records(app)
        opens = [r for r in records if r["kind"] == "open"]
        if not opens:
            if any(r["kind"] == "preregister" for r in records):
                raise UsageError("v1 有冻结清单但找不到开局预留区间，不能确认读取边界")
            return []
        data = opens[-1].get("data")
        windows = data.get("confirm") if isinstance(data, dict) else None
        if not isinstance(windows, dict) or set(windows) != {"backward", "forward"}:
            raise UsageError("v1 最新开局记录缺少完整的两段预留数据")
        result = []
        for window in windows.values():
            if not isinstance(window, dict) or not {"start", "end", "label_end"} <= set(window):
                raise UsageError("v1 预留区间缺少明确的前瞻结束日期")
            result.append(_interval(window["start"], window["end"], window["label_end"]))
        return result

    def _protect_legacy_reservations(self, app: str, interval: dict) -> None:
        if any(_overlap(interval, reserved) for reserved in self._legacy_reserved(app)):
            raise UsageError("本次区间侵入 v1 最新开局记录的预留数据；请先核对并明确迁移旧研究安排")

    def _legacy_burned(self, app: str) -> list[dict]:
        intervals = []
        for rec in self._legacy_records(app):
            if rec["kind"] not in BURN_KINDS:
                continue
            window, horizon = rec.get("window"), rec.get("label_horizon")
            if (not isinstance(window, dict) or not {"start", "end"} <= set(window)
                    or not isinstance(horizon, int) or isinstance(horizon, bool) or horizon <= 0):
                raise UsageError("v1 消费记录缺少可信的买点区间或前瞻长度")
            start, end = _date(window["start"]), _date(window["end"])
            if start > end:
                raise UsageError("v1 消费记录区间倒置")
            # axes 故意不参与筛选：其他特征/参数研究也已暴露过相同数据。
            if self.calendar is None or self.calendar[0] > end:
                raise UsageError("解释 v1 前瞻范围需要完整交易日历；禁止用工作日猜测")
            pos = bisect_right(self.calendar, end)
            if pos + horizon > len(self.calendar):
                raise UsageError("交易日历不足以覆盖 v1 前瞻范围；不能确认数据未被使用")
            intervals.append({"start": start.isoformat(), "end": end.isoformat(),
                              "label_end": self.calendar[pos + horizon - 1].isoformat()})
        return intervals

    def _fresh(self, records: list[dict], app: str, interval: dict) -> None:
        burned = [r for r in records if r["app"] == app and r["kind"] == "claim"]
        burned += self._legacy_burned(app)
        if any(_overlap(interval, used) for used in burned):
            raise UsageError("该区间与已经使用过的数据重叠（包含前瞻日期）；不能作为最终检查或复核")

    @staticmethod
    def _record(app: str, run_id: str, stage: str, config_hash: str,
                interval: dict, kind: str) -> dict:
        return {"schema": "tune-gates-v3/1", "kind": kind, "app": app,
                "run_id": run_id, "stage": stage, "config_hash": config_hash,
                "ts": datetime.now(timezone.utc).isoformat(), **interval}

    def reserve(self, app: str, run_id: str, intervals: list[dict], config_hash: str) -> None:
        """一次预留 final 和 review，二者含前瞻尾部不重叠；重复相同预留幂等。"""
        _identity(app, run_id, config_hash)
        if (not isinstance(intervals, list) or len(intervals) != 2
                or any(not isinstance(i, dict) for i in intervals)
                or {i.get("stage") for i in intervals} != {"final", "review"}):
            raise UsageError("必须一次声明 final 和 review 两个预留区间")
        requested = {}
        for item in intervals:
            if set(item) != {"stage", "start", "end", "label_end"}:
                raise UsageError("预留区间仅接受 stage/start/end/label_end")
            requested[item["stage"]] = _interval(item["start"], item["end"], item["label_end"])
        if requested["final"]["label_end"] >= requested["review"]["start"]:
            raise UsageError("review 必须在 final 全部前瞻日期之后，且不得重叠")
        with self._locked() as (stream, records):
            own = self._same_run(records, app, run_id, config_hash)
            old = {r["stage"]: {key: r[key] for key in ("start", "end", "label_end")}
                   for r in own if r["kind"] == "reserve"}
            if old:
                if old != requested:
                    raise UsageError("已经冻结的预留区间不能修改")
                return
            for interval in requested.values():
                self._protect_legacy_reservations(app, interval)
                self._fresh(records, app, interval)
                if any(_overlap(interval, other) for other in self._active_reservations(records, app)):
                    raise UsageError("该区间已经预留给另一轮最终检查或复核")
            self._append(stream, [self._record(app, run_id, stage, config_hash, interval, "reserve")
                                  for stage, interval in requested.items()])

    def claim_development(self, app: str, run_id: str, start: str, end: str,
                          label_end: str, config_hash: str) -> None:
        """只做方法开发时先登记暴露，不虚设最终验证或复核。

        记录与正式训练共用同一本账，之后不能把本区间称为未见数据。
        此入口不授予 final/review 访问，仍保护已有的旧版和当前预留。
        """
        _identity(app, run_id, config_hash)
        interval = _interval(start, end, label_end)
        with self._locked() as (stream, records):
            own = self._same_run(records, app, run_id, config_hash)
            if any(r['kind'] == 'reserve' for r in own):
                raise UsageError('正式调参轮次须使用 claim；不可切换为方法开发')
            self._protect_legacy_reservations(app, interval)
            if any(_overlap(interval, reserved)
                   for reserved in self._active_reservations(records, app)):
                raise UsageError('方法开发范围侵入尚未消费的预留区间')
            self._append(stream, [self._record(app, run_id, 'training', config_hash,
                                               interval, 'claim')])

    def claim(self, app: str, run_id: str, stage: str, start: str, end: str,
              label_end: str, config_hash: str) -> None:
        """在读取前记录整个暴露区间；final/review 每轮每阶段只许调用一次。"""
        _identity(app, run_id, config_hash)
        if stage not in STAGES:
            raise UsageError(f"未知阶段 {stage!r}")
        interval = _interval(start, end, label_end)
        with self._locked() as (stream, records):
            own = self._same_run(records, app, run_id, config_hash)
            self._protect_legacy_reservations(app, interval)
            reservations = [r for r in own if r["kind"] == "reserve"]
            if len(reservations) != 2 or {r["stage"] for r in reservations} != {"final", "review"}:
                raise UsageError("读取前必须完整冻结 final 和 review 两个预留区间")
            if stage == "review" and not any(r["kind"] == "claim" and r["stage"] == "final" for r in own):
                raise UsageError("复核不能先于该轮最终检查")
            if stage != "training":
                if any(r["kind"] == "claim" and r["stage"] == stage for r in own):
                    raise UsageError("这轮的该检查已经消耗；中断后也不能重算或更换候选")
                reserved = [r for r in own if r["kind"] == "reserve" and r["stage"] == stage]
                if len(reserved) != 1 or any(reserved[0][key] != value for key, value in interval.items()):
                    raise UsageError("检查区间必须精确匹配搜索前冻结的预留区间")
                self._fresh(records, app, interval)
            for reserved in self._active_reservations(records, app):
                if reserved["run_id"] == run_id and reserved["stage"] == stage and stage != "training":
                    continue
                if _overlap(interval, reserved):
                    raise UsageError("本次读取（含前瞻日期）侵入尚未使用的最终检查或复核区间")
            if stage == "training":
                final = next((r for r in own if r["kind"] == "reserve" and r["stage"] == "final"), None)
                if final is None:
                    raise UsageError("训练读取前必须先预留最终检查和复核区间")
                if label_end >= final["start"]:
                    raise UsageError("训练的所有前瞻日期必须止于最终检查开始之前")
            self._append(stream, [self._record(app, run_id, stage, config_hash, interval, "claim")])

    def abandon(self, app: str, run_id: str, config_hash: str) -> None:
        """关闭本轮，释放未消费的预留；历史消费永久保留，不能由此恢复验证机会。"""
        _identity(app, run_id, config_hash)
        with self._locked() as (stream, records):
            own = self._same_run(records, app, run_id, config_hash, allow_closed=True)
            if not own:
                raise UsageError("找不到该轮的使用记录，不能关闭")
            if any(r["kind"] == "abandon" for r in own):
                return
            record = {"schema": "tune-gates-v3/1", "kind": "abandon", "app": app,
                      "run_id": run_id, "config_hash": config_hash,
                      "ts": datetime.now(timezone.utc).isoformat()}
            self._append(stream, [record])


def adoption(metrics: dict, stage: str = "final",
             previous_status: dict | str | None = None) -> dict:
    """按固定规则判定采用状态，不读取或修改正式参数。

    metrics 必须给 hard_constraints_passed（bool）与 score_difference（有限数值；
    不可计算时为 None）。最后检查与复核用同一条规则：要求都满足且排名分高过
    原参数时，最后检查给 provisional（暂用）、复核给 retained（继续使用）；
    否则最后检查给 reject（不采用）、复核给 rollback（撤回）。复核只适用于
    当前暂用的参数。
    """
    if stage not in {"final", "review"}:
        raise ValueError("adoption 只接受 final/review")
    if not isinstance(metrics.get("hard_constraints_passed"), bool):
        raise ValueError("hard_constraints_passed 必须明确为 bool")
    difference = metrics.get("score_difference")
    if difference is not None and (isinstance(difference, bool) or not isinstance(difference, (int, float))
                                   or not math.isfinite(difference)):
        raise ValueError("score_difference 必须是有限数值")
    if stage == "review":
        prior = previous_status.get("status") if isinstance(previous_status, dict) else previous_status
        if prior != "provisional":
            raise ValueError("预定复核仅适用于当前暂用的参数")
    rejection = "rollback" if stage == "review" else "reject"
    if not metrics["hard_constraints_passed"]:
        status, reason = rejection, "未满足预先固定的机会或显式空间/回撤要求"
    elif difference is None:
        status, reason = rejection, "缺少可比较的买入日结果，不能认定排名分有所改善"
    elif difference <= SCORE_EPSILON:
        status, reason = rejection, "排名分没有高过原参数"
    elif stage == "final":
        status, reason = "provisional", "排名分高过原参数且要求都满足；暂用，按预定日期复核"
    else:
        status, reason = "retained", "复核期排名分仍高过原参数且要求都满足；继续使用"
    return {"status": status, "reason": reason, "provisional": status == "provisional"}
