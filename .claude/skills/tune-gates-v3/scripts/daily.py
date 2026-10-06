"""独立 v3 的逐买点日评价；访问许可由调用者在创建或使用本对象前检查。

本模块不搜索参数、不写参数文件、不维护样本使用账本。每个评价器固定股票、
日期和评价方式，收盘首次穿越标签按股只算一次；检测只接触买点截止日及以前的数据。
"""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
import hashlib
import importlib
import json
from numbers import Integral
from pathlib import Path

import numpy as np
import pandas as pd

from path2.calc.atr import FP_ATR_WINDOW
from path2.eval import _resolve_end_events


COLUMNS = ["symbol", "date", "upside", "up", "down", "both", "none", "M", "drawdown"]
# 行情到齐的整体比例下限（待验证）：退市或下载失败的股票不会再更新，不能逐只强求。
READY_FRACTION = 0.9


def overlay_params(baseline: dict, changes: dict) -> dict:
    """递归叠加参数，返回新字典；未改动的值保留完整原参数快照。"""
    if not isinstance(baseline, Mapping) or not isinstance(changes, Mapping):
        raise TypeError("参数及其改动必须是字典")
    result = deepcopy(dict(baseline))
    for key, value in changes.items():
        if isinstance(value, Mapping) and isinstance(result.get(key), Mapping):
            result[key] = overlay_params(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def stable_hash(value) -> str:
    """对有限 JSON 值作稳定摘要；浮点值不取整、不按精度合并。"""
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False,
                         allow_nan=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _empty() -> pd.DataFrame:
    return pd.DataFrame({"symbol": pd.Series(dtype="object"),
                         "date": pd.Series(dtype="object"),
                         "upside": pd.Series(dtype="float64"),
                         **{state: pd.Series(dtype="int8")
                            for state in ("up", "down", "both", "none")},
                         "M": pd.Series(dtype="float64"),
                         "drawdown": pd.Series(dtype="float64")})


def _date(value) -> pd.Timestamp:
    value = pd.Timestamp(value)
    if pd.isna(value):
        raise ValueError("日期不能为空")
    if value.tzinfo is not None:
        value = value.tz_localize(None)
    return value.normalize()


def _daily_close_labels(frame: pd.DataFrame, symbol: str, start: pd.Timestamp,
                        end: pd.Timestamp, horizon: int, k: float) -> pd.DataFrame:
    """一次生成完整未来窗口内的收盘首次穿越、盘中空间和回撤标签。

    M 沿用 TR/close 最近 FP_ATR_WINDOW 根的中位数，包含买入日、不含未来；
    上线 close[t]*(1+k*M[t])、下线 close[t]/(1+k*M[t]) 在入场时固定。
    从 t+1 至 t+horizon 按 close 判先上/先下/未触线。both 恒为 0，仅保留旧
    表接口。upside=max(high[t+1:t+H])/close[t]-1；drawdown 对应 min(low)。

    滚动最高最低与合法价格计数避免逐起点 DataFrame 切片；按未来偏移批处理
    尚未触线的起点，触线后不再比较。时间上界 O(N*H)，额外空间 O(N)，不建
    N*H 价格矩阵。原波动尺度的完整滚动窗规则不变，坏价/缺未来不能算未触线。
    """
    if frame.empty:
        return _empty()
    prices = frame[["high", "low", "close"]].to_numpy(dtype=float)
    valid = np.isfinite(prices).all(axis=1) & (prices > 0).all(axis=1)
    valid &= prices[:, 0] >= prices[:, 1]
    clean = frame[["high", "low", "close"]].copy()
    clean.loc[~valid, :] = np.nan
    previous = clean["close"].shift(1)
    tr = pd.concat([clean["high"] - clean["low"],
                    (clean["high"] - previous).abs(),
                    (clean["low"] - previous).abs()], axis=1).max(axis=1)
    # 完整窗中没有 NaN 时，pandas 滚动中位数与逐窗 np.nanmedian 数值相同。
    scale = (tr / clean["close"]).rolling(FP_ATR_WINDOW).median().to_numpy()
    future_high = clean["high"].rolling(horizon).max().shift(-horizon).to_numpy()
    future_low = clean["low"].rolling(horizon).min().shift(-horizon).to_numpy()
    future_valid = pd.Series(valid).rolling(horizon).sum().shift(-horizon).to_numpy()
    dates = pd.DatetimeIndex(frame["date"])
    eligible = ((dates >= start) & (dates <= end) & valid &
                np.isfinite(scale) & (scale > 0) & (future_valid == horizon))
    indices = np.flatnonzero(eligible)
    if not len(indices):
        return _empty()
    close = prices[:, 2]
    entry = close[indices]
    factor = 1 + k * scale[indices]
    upper, lower = entry * factor, entry / factor
    direction = np.zeros(len(indices), dtype=np.int8)
    active = np.arange(len(indices))
    for offset in range(1, horizon + 1):
        if not len(active):
            break
        future_close = close[indices[active] + offset]
        up, down = future_close >= upper[active], future_close <= lower[active]
        direction[active[up]] = 1
        direction[active[down]] = -1
        active = active[~(up | down)]
    return pd.DataFrame({
        "symbol": symbol, "date": dates[indices].strftime("%Y-%m-%d"),
        "upside": future_high[indices] / entry - 1,
        "up": (direction == 1).astype(np.int8),
        "down": (direction == -1).astype(np.int8),
        "both": np.zeros(len(indices), dtype=np.int8),
        "none": (direction == 0).astype(np.int8), "M": scale[indices],
        "drawdown": future_low[indices] / entry - 1,
    }, columns=COLUMNS)


class DailyEvaluator:
    """固定数据范围内评价任意合法候选，返回股票与日期去重后的逐日结果。

    app_module 可为可导入的模块名或模块对象。baseline_params 是完整原参数，
    evaluate 的参数可为局部改动。loader(symbol) 可注入合成数据；默认只读
    data_dir 下的 .pkl 或 .pickle。loader 返回原历史后，本模块先裁至 label_end，
    检测时进一步裁至 end；样本日期只取闭区间 [start, end]。history_start
    非空时，在计算 M 或检测前另裁掉此前历史；None 表示调用方已授权输入的
    全部较早历史，或 loader 已按许可裁切。不能只登记买点日期却暗中使用预留历史。
    required_price_end 非空时检查行情整体是否已更新至该日：只看本阶段开始时
    还在更新的股票（未裁切末日不早于 start），其中末日到达该日的比例须不低于
    READY_FRACTION。未到齐的股票照常保留，有完整后续的买点仍计入，名单记入
    结果 attrs 的 stale_symbols。该日由调用方按冻结交易日历给出，不以系统日期
    已过代替实际数据齐备。None 不施加此末端要求。

    实例首次使用时读取固定数据快照；文件随后变化不会悄悄混入本轮评价，
    要使用新数据须创建新实例。调用方负责在读取前授予该范围的访问许可。

    因果检查仅保证买点事件已确认；完整命中的祖先或 where 仍可能读取后来
    才知道的字段。本类不将完整命中当作逐日可交易的证明，调用方在正式采用前
    必须核查该条件或另做逐日前缀验证。结果 attrs 明确标记此检查范围。
    """

    def __init__(self, app_module, baseline_params: dict, data_dir: Path,
                 symbols: list[str], start: str, end: str, label_end: str,
                 horizon: int, k: float, code_token: str = "", loader=None,
                 history_start: str | None = None, required_price_end: str | None = None):
        if isinstance(horizon, bool) or not isinstance(horizon, Integral) or horizon < 1:
            raise ValueError("后续观察交易日数必须是正整数")
        if not np.isfinite(k) or k <= 0:
            raise ValueError("上下目标线的系数必须是有限正数")
        self.start, self.end, self.label_end = map(_date, (start, end, label_end))
        if not self.start <= self.end <= self.label_end:
            raise ValueError("必须满足开始日不晚于结束日，结束日不晚于后续数据截止日")
        self.history_start = _date(history_start) if history_start is not None else None
        if self.history_start is not None and self.history_start > self.start:
            raise ValueError("回看历史开始日不能晚于买点开始日")
        self.required_price_end = _date(required_price_end) if required_price_end is not None else None
        if self.required_price_end is not None and self.required_price_end > self.label_end:
            raise ValueError("要求的行情末日不能晚于后续数据截止日")
        self.app = importlib.import_module(app_module) if isinstance(app_module, str) else app_module
        self._baseline_params = deepcopy(baseline_params)
        stable_hash(self._baseline_params)
        original = self.app.Params.from_dict(self._baseline_params, strict=True)
        self._end_node = self.app.eval_meta(params=original)["end_node"]
        if not isinstance(self._end_node, str) or not self._end_node:
            raise ValueError("eval_meta 必须给出非空 end_node")
        self.data_dir = Path(data_dir)
        self.symbols = sorted(set(symbols))
        for symbol in self.symbols:
            if not isinstance(symbol, str) or not symbol or symbol in (".", "..") or any(c in symbol for c in ("/", "\\", "\0")):
                raise ValueError("股票名称必须是单个文件名，不可包含路径")
        self.horizon, self.k, self.code_token = int(horizon), float(k), code_token
        self._loader = loader or self._load
        self._frames: dict[str, pd.DataFrame] = {}
        self._labels: dict[str, pd.DataFrame] = {}
        self._versions: dict[str, str] = {}
        self._cache: dict[str, pd.DataFrame] = {}
        self._baseline: pd.DataFrame | None = None
        self._trimmed: dict[str, pd.DataFrame] = {}
        self._last: dict[str, pd.Timestamp | None] = {}
        self.stale: list[str] | None = None

    def _load(self, symbol: str) -> pd.DataFrame:
        """按项目实际 .pkl 命名读入，也接受单独存在的 .pickle 文件。"""
        for suffix in (".pkl", ".pickle"):
            path = self.data_dir / f"{symbol}{suffix}"
            if path.is_file():
                return pd.read_pickle(path)
        raise FileNotFoundError(f"没有找到股票数据：{symbol}.pkl 或 {symbol}.pickle")

    def _read(self, symbol: str) -> pd.DataFrame:
        """读入一只股票并裁到许可范围；记下未裁切的末日供到齐检查。"""
        raw = self._loader(symbol)
        if not isinstance(raw, pd.DataFrame):
            raise TypeError("数据加载器必须返回 DataFrame")
        dates = pd.DatetimeIndex(pd.to_datetime(raw["date"] if "date" in raw else raw.index))
        if dates.tz is not None:
            dates = dates.tz_localize(None)
        dates = dates.normalize()
        self._last[symbol] = dates.max() if len(dates) else None
        keep = dates <= self.label_end
        if self.history_start is not None:
            keep &= dates >= self.history_start
        frame = raw.loc[keep].copy(deep=True).reset_index(drop=True)
        frame["date"] = dates[keep]
        if not frame["date"].is_monotonic_increasing or frame["date"].duplicated().any():
            raise ValueError(f"{symbol} 的交易日必须递增且不重复")
        required = {"high", "low", "close"}
        if not required.issubset(frame):
            raise ValueError(f"{symbol} 缺少价格列：{sorted(required - set(frame))}")
        for column in required:
            frame[column] = pd.to_numeric(frame[column], errors="raise")
        return frame

    def check_ready(self) -> dict:
        """在登记与标签计算之前检查行情整体是否已更新到 required_price_end。

        分母是未裁切末日不早于 start 的股票（本阶段开始时还在更新）；其中末日
        早于 required_price_end 的记为未到齐。到齐比例低于 READY_FRACTION 或
        分母为 0 时报错。每个文件每个评价器只读一次，读到的帧留给后续评价。
        """
        if self.required_price_end is None:
            return {}
        for symbol in self.symbols:
            if symbol not in self._last:
                self._trimmed[symbol] = self._read(symbol)
        live = [s for s in self.symbols if self._last[s] is not None and self._last[s] >= self.start]
        stale = [s for s in live if self._last[s] < self.required_price_end]
        ready = len(live) - len(stale)
        expected = self.required_price_end.strftime("%Y-%m-%d")
        if not live or ready / len(live) < READY_FRACTION:
            raise ValueError(f"行情整体尚未更新：到齐 {ready} / 应到 {len(live)}，要求至少到 {expected}")
        # 通过后才记下名单，失败的检查再次调用仍会失败。
        self.stale = stale
        return {"required_price_end": expected, "ready": ready, "expected": len(live),
                "stale_symbols": list(stale)}

    def _prepare(self) -> None:
        """先查行情到齐，再生成股票固定的标签和检测输入；每股最多算一次标签。"""
        if self._baseline is not None:
            return
        self.check_ready()
        for symbol in self.symbols:
            if symbol in self._frames:
                continue
            frame = self._trimmed.pop(symbol) if symbol in self._trimmed else self._read(symbol)
            labels = _daily_close_labels(frame, symbol, self.start, self.end,
                                         self.horizon, self.k)
            self._labels[symbol] = labels
            self._frames[symbol] = frame.loc[frame["date"] <= self.end].copy(deep=True)
            hashed = pd.util.hash_pandas_object(frame, index=True).to_numpy().tobytes()
            self._versions[symbol] = hashlib.sha256(hashed).hexdigest()
        self._baseline = (pd.concat(list(self._labels.values()), ignore_index=True)
                          if self._labels else _empty())
        self._baseline.attrs["data_versions"] = deepcopy(self._versions)
        self._baseline.attrs["history_start"] = (self.history_start.strftime("%Y-%m-%d")
                                                  if self.history_start is not None else None)
        self._baseline.attrs["required_price_end"] = (self.required_price_end.strftime("%Y-%m-%d")
                                                       if self.required_price_end is not None else None)
        self._baseline.attrs["stale_symbols"] = list(self.stale or [])

    @property
    def baseline(self) -> pd.DataFrame:
        """全部拥有完整未来标签的股票日期；调用方修改副本不影响缓存。"""
        self._prepare()
        return self._baseline.copy(deep=True)

    def evaluate(self, params: dict) -> pd.DataFrame:
        """评价候选；attrs 分开记录可识别、可评价和暂不能评价的买点日数量。"""
        full = overlay_params(self._baseline_params, params)
        return self._evaluate_app(self.app, full, expected_end=self._end_node)

    def evaluate_control(self, app_module, params: dict) -> pd.DataFrame:
        """评价固定对照，复用本实例的标签和检测截止数据，不重新生成未来标签。

        params 是对照 app 的完整参数快照；调用方负责在搜索前固定，不能跟随
        候选改变。对照可有自己的 end_node 和首部回看；缓存包含 app 与精确参数。
        """
        module = importlib.import_module(app_module) if isinstance(app_module, str) else app_module
        full = deepcopy(params)
        stable_hash(full)
        return self._evaluate_app(module, full)

    def _evaluate_app(self, module, full: dict, expected_end: str | None = None) -> pd.DataFrame:
        """对同一固定数据快照运行 app；候选与对照共用日期提取和缓存规则。"""
        # 在读取股票数据之前发现拼错的参数、非法声明和不存在的买点协议。
        p = module.Params.from_dict(full, strict=True)
        module.build_pattern(p)
        meta = module.eval_meta(params=p)
        end_node = meta["end_node"]
        if not isinstance(end_node, str) or not end_node:
            raise ValueError("eval_meta 必须给出非空 end_node")
        if expected_end is not None and end_node != expected_end:
            raise ValueError("候选不能改变原参数规定的买点 end_node")
        head_buffer = meta.get("head_buffer_trading_days", 0)
        if isinstance(head_buffer, bool) or not isinstance(head_buffer, Integral) or head_buffer < 0:
            raise ValueError("首部回看交易日数必须是非负整数")
        head_buffer = int(head_buffer)
        self._prepare()
        module_key = getattr(module, "__name__", f"{type(module).__name__}@{id(module)}")
        key = stable_hash({"app": module_key, "params": full, "code": self.code_token,
                           "versions": self._versions, "start": str(self.start),
                           "history_start": str(self.history_start),
                           "required_price_end": str(self.required_price_end),
                           "end": str(self.end), "label_end": str(self.label_end),
                           "horizon": self.horizon, "k": self.k, "end_node": end_node,
                           "head_buffer_trading_days": head_buffer})
        if key in self._cache:
            return self._cache[key].copy(deep=True)
        pieces, detected_count, warmup_excluded_count = [], 0, 0
        for symbol in self.symbols:
            frame = self._frames[symbol]
            dates, insufficient_history = set(), set()
            if not frame.empty:
                result = module.analyze(frame.copy(deep=True), params=p)
                for match in result.matches:
                    for event in _resolve_end_events(match, end_node):
                        # match.confirm_idx 是整组区间的尾部，不能拿它替代买点事件确认日。
                        for index in event.sample_bar_indices():
                            if isinstance(index, bool) or not isinstance(index, Integral) or not 0 <= index < len(frame):
                                raise ValueError("买点事件给出了检测输入范围外或非整数的样本下标")
                            if index < event.confirm_idx:
                                continue
                            date = frame["date"].iat[index]
                            if self.start <= date <= self.end:
                                target = insufficient_history if index < head_buffer else dates
                                target.add(date.strftime("%Y-%m-%d"))
            detected_count += len(dates)
            warmup_excluded_count += len(insufficient_history)
            labels = self._labels[symbol]
            pieces.append(labels.loc[labels["date"].isin(dates)])
        result = pd.concat(pieces, ignore_index=True) if pieces else _empty()
        result.attrs.update(detected_count=detected_count, eligible_count=len(result),
                            unavailable_count=detected_count - len(result),
                            causality="event-confirm-only", data_versions=deepcopy(self._versions),
                            history_start=self._baseline.attrs["history_start"],
                            required_price_end=self._baseline.attrs["required_price_end"],
                            stale_symbols=list(self._baseline.attrs["stale_symbols"]),
                            head_buffer_trading_days=head_buffer,
                            warmup_excluded_count=warmup_excluded_count)
        self._cache[key] = result.copy(deep=True)
        return result
