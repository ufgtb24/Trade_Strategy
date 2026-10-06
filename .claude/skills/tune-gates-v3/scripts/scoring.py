"""按唯一股票日的方向结果评分，并汇总全部连续交易日窗口。

每个非空窗口内先上记 +1、先下记 -1、未触线记 0，按买点日等权
平均；窗口之间只按近期权重平均，不按买点密度再次加权。同日普通
买入对照先按同日期、同波动档预汇总，每个候选仅查询自己买点的档
位均值；它只剩选股，不含择时。

排名分是候选方向成绩比同日普通买入对照多出的部分，默认只给正的
领先按证据打折。绝对方向成绩与随机日基线（全池同口径窗口成绩，
含择时）只报告、不排名。机会只设相对原参数的下限。

默认机会下限与折扣尺度是可审计的工程初值，尚非市场校准结论。本模
块不提供未经校准的置信区间，不将重叠窗口或股票数当作独立证据。
"""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from numbers import Integral, Real

import numpy as np
import pandas as pd

STATES = ("up", "down", "both", "none")
SCORE_FLOOR = -1e100
SCORE_MODE = "matched_difference"
SHRINKAGE_SCORE_MODE = "matched_difference_shrunk"
DEFAULT_SHRINKAGE = {"enabled": True, "tau": 0.1, "bandwidth": 80}
DEFAULT_POLICY = {
    "min_reference_fraction": 0.5,
    "min_recent_reference_fraction": 0.5,
    "min_median_upside": None,
    "min_median_drawdown": None,
}
REMOVED_POLICY_KEYS = {"min_buy_days", "min_recent_buy_days", "min_direction_score", "baseline_tolerance"}


def normalize_shrinkage(settings: Mapping | None = None) -> dict:
    """冻结整轮统计折扣；默认开启，参数不能由单个 trial 自行挑选。

    tau 是预先选定的差异尺度，bandwidth 是相邻窗口起点的相关项跨度。
    这些工程初值没有市场校准含义。
    """
    if settings is not None and not isinstance(settings, Mapping):
        raise ValueError("shrinkage 必须为映射")
    extra = set(settings or {}) - set(DEFAULT_SHRINKAGE)
    if extra:
        raise ValueError(f"未识别的统计折扣设置: {sorted(extra)}")
    out = {**DEFAULT_SHRINKAGE, **(settings or {})}
    if type(out["enabled"]) is not bool:
        raise ValueError("shrinkage.enabled 必须为 bool")
    tau, bandwidth = out["tau"], out["bandwidth"]
    if isinstance(tau, bool) or not isinstance(tau, Real) or not np.isfinite(tau) or tau <= 0:
        raise ValueError("shrinkage.tau 必须为有限正数")
    tau = float(tau)
    if not np.isfinite(tau * tau) or tau * tau == 0:
        raise ValueError("shrinkage.tau 的平方必须可表示为有限正数")
    if (isinstance(bandwidth, bool) or not isinstance(bandwidth, Integral) or
            not 0 <= bandwidth <= np.iinfo(np.int64).max):
        raise ValueError("shrinkage.bandwidth 必须为非负有限范围整数")
    return {"enabled": out["enabled"], "tau": tau, "bandwidth": int(bandwidth)}


def _adjust_score(raw: float | None, baseline: float | None,
                  windows: dict, settings: dict) -> tuple[float | None, dict]:
    """排名分：领先 Δ=Z-B，开启折扣时取 min(Δ, λΔ)，只给正的领先打折。

    λ 由配对窗口差的工作误差刻度算出，证据越薄 λ 越小。领先为负时照原
    值计分：若也乘 λ，证据薄、劣势大的候选会被拉近 0，反超为负的现役。
    误差不可识别（常量差、单一窗口或零误差）时 λ=0，正领先记 0、负领先
    照原值，因此不会胜过一切为负的现役。空窗口的影响项为 0，保留真实日
    历间隔。Bartlett 相关项计算是误差原型，不是校准过的置信区间。
    """
    info = {**settings, "experimental": settings["enabled"], "calibrated": False,
            "variance": None, "factor": None, "used_lags": 0, "status": "disabled"}
    if raw is None:
        info["status"] = "no_opportunities"
        return None, info
    delta = raw - baseline
    if abs(delta) <= 1e-12:
        # 全池恒等配比的浮点舍入不构成观测领先或劣势。
        if settings["enabled"]:
            info.update(factor=0.0, status="zero_observed_difference")
        return 0.0, info
    if not settings["enabled"]:
        return delta, info
    active = windows["active"]
    contrasts = windows["score"][active] - windows["matched_score"][active]
    psi = np.zeros(len(active), dtype=float)
    psi[active] = windows["weights"][active] * (contrasts - delta)
    energy = float(psi @ psi)
    variance = energy
    bandwidth = settings["bandwidth"]
    used_lags = min(bandwidth, len(psi) - 1)
    for lag in range(1, used_lags + 1):
        variance += 2 * (1 - lag / (bandwidth + 1)) * float(psi[lag:] @ psi[:-lag])
    tolerance = 32 * np.finfo(float).eps * max(energy, np.finfo(float).tiny)
    if not np.isfinite(variance) or variance < -tolerance:
        raise ValueError("统计折扣的工作误差计算不可用，不能据此继续排名")
    variance = max(0.0, variance)
    info.update(variance=variance, used_lags=used_lags)
    if len(contrasts) < 2 or np.ptp(contrasts) <= 1e-12 or variance <= tolerance:
        info.update(factor=0.0, status="unidentified_variance_full_shrinkage")
        return min(delta, 0.0), info
    prior_variance = settings["tau"] ** 2
    factor = prior_variance / (prior_variance + variance)
    info.update(factor=factor, status="experimental_uncalibrated")
    return min(delta, factor * delta), info


def normalize_policy(policy: Mapping | None = None) -> dict:
    """补齐规则；机会只设相对原参数的下限，允许相等。

    机会供给不加入排名分。空间及回撤只有显式给出数值才成为要求；回撤
    使用带符号收益（例如 -0.2），越高表示跌幅越小。
    """
    if policy is not None and not isinstance(policy, Mapping):
        raise ValueError("policy 必须为映射")
    removed = set(policy or {}) & REMOVED_POLICY_KEYS
    if removed:
        raise ValueError(f"评分规则 {sorted(removed)} 已删除：机会只用相对原参数的下限；方向不设绝对下限")
    extras = set(policy or {}) - set(DEFAULT_POLICY)
    if extras:
        raise ValueError(f"未识别的评分规则: {sorted(extras)}")
    out = {**DEFAULT_POLICY, **(policy or {})}
    for key, value in out.items():
        if key in ("min_median_upside", "min_median_drawdown") and value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, Real) or not np.isfinite(value):
            raise ValueError(f"{key} 必须为有限数")
        if key in ("min_reference_fraction", "min_recent_reference_fraction") and not 0 <= value <= 1:
            raise ValueError(f"{key} 必须在 0 与 1 之间")
        out[key] = float(value)
    return out


def _rows(rows: pd.DataFrame) -> pd.DataFrame:
    """校验完整、唯一股票日标签；close 口径不能出现同日双穿。"""
    required = {"symbol", "date", "upside", *STATES}
    if not isinstance(rows, pd.DataFrame) or not required <= set(rows.columns):
        raise ValueError(f"日结果需要列 {sorted(required)}")
    out = rows.copy()
    if out["symbol"].isna().any() or not out["symbol"].map(lambda x: isinstance(x, str) and bool(x)).all():
        raise ValueError("symbol 必须是非空字符串")
    dates = pd.to_datetime(out["date"], errors="raise")
    if dates.isna().any():
        raise ValueError("日期不能缺失")
    if dates.dt.tz is not None:
        dates = dates.dt.tz_localize(None)
    out["date"] = dates.dt.normalize()
    if out.duplicated(["symbol", "date"]).any():
        raise ValueError("同一股票同一天只能有一行")
    try:
        states = out[list(STATES)].to_numpy(dtype=float)
        for column in ("upside", "drawdown", "M"):
            if column in out:
                values = out[column].to_numpy(dtype=float)
                if not np.isfinite(values).all() or (column == "M" and not (values > 0).all()):
                    raise ValueError(f"{column} 须为有限数；M 还须为正数")
                out[column] = values
    except (ValueError, TypeError) as exc:
        raise ValueError("日标签须为有限数；M 还须为正数") from exc
    if not np.isfinite(states).all() or not np.isin(states, [0, 1]).all() or not (states.sum(axis=1) == 1).all():
        raise ValueError("方向必须恰有一个状态为 1，其余为 0")
    if (states[:, STATES.index("both")] != 0).any():
        raise ValueError("收盘首次穿越不能有 both；不得混用盘中标签")
    out[list(STATES)] = states.astype(np.int8)
    return out


def _summary_checked(rows: pd.DataFrame) -> dict:
    counts = {key: int(rows[key].sum()) for key in STATES}
    resolved = counts["up"] + counts["down"]
    size = len(rows)
    return {
        "median_upside": float(rows["upside"].median()) if size else None,
        "median_drawdown": float(rows["drawdown"].median()) if size and "drawdown" in rows else None,
        "drawdown_p10": float(rows["drawdown"].quantile(0.1)) if size and "drawdown" in rows else None,
        "count": int(size), "stocks": int(rows["symbol"].nunique()), **counts,
        "direction_count": resolved,
        "direction": counts["up"] / resolved if resolved else None,
        "direction_score": (counts["up"] - counts["down"]) / size if size else None,
        "resolved_fraction": resolved / size if size else None,
    }


def summary(rows: pd.DataFrame) -> dict:
    """返回合并买点诊断；direction_score 包括未触线，direction 不包括。"""
    return _summary_checked(_rows(rows))


class WindowPlan:
    """冻结一次股票池快照和窗口日历，后续候选只查询所选股票日。

    构造时顺带算一次全池同口径窗口成绩，作为随机日基线（含择时）；之后
    候选只与它相减，不重扫池子。

    baseline 的唯一股票日期及标签在构造时复制并冻结。之后同一来源
    对象仅作为句柄，不重新扫描；要更改股票池或标签必须新建计划。
    不同对象可作为同一快照的重排副本传入，但首次需完整核对。
    horizon 是标签的前瞻期限元数据；窗口长度不须大于它，因为窗口
    用于机会发生日期汇总，不用来假定相邻窗口独立。
    """

    def __init__(self, baseline: pd.DataFrame, horizon: int, window_days: int = 21,
                 half_life_days: float = 252, recent_days: int = 126,
                 shrinkage: Mapping | None = None):
        self._shrinkage = normalize_shrinkage(shrinkage)
        self.score_mode = SHRINKAGE_SCORE_MODE if self._shrinkage["enabled"] else SCORE_MODE
        for name, value in (("horizon", horizon), ("window_days", window_days), ("recent_days", recent_days)):
            if isinstance(value, bool) or not isinstance(value, Integral) or value < 1:
                raise ValueError(f"{name} 必须为正整数")
        if isinstance(half_life_days, bool) or not isinstance(half_life_days, Real) or not np.isfinite(half_life_days) or half_life_days <= 0:
            raise ValueError("half_life_days 必须为有限正数")
        frozen = _rows(baseline)
        if not len(frozen):
            raise ValueError("窗口计划需要非空基线")
        self.horizon, self.window_days, self.recent_days = int(horizon), int(window_days), int(recent_days)
        self.half_life_days = float(half_life_days)
        self.dates = pd.DatetimeIndex(sorted(frozen["date"].unique()))
        if len(self.dates) < window_days:
            raise ValueError("可评价交易日少于窗口长度")
        self._accepted_baselines = [baseline]
        self._baseline = frozen
        self._keys = pd.MultiIndex.from_frame(frozen[["symbol", "date"]])
        self._date_indices = self.dates.get_indexer(frozen["date"])
        self._values = frozen[["up", "down", "both", "none"]].to_numpy(dtype=float)
        self._direction = self._values[:, 0] - self._values[:, 1]
        self._group_values = np.empty_like(self._values)
        self.baseline_matching = "date_and_M_quintile" if "M" in frozen else "date_only_no_M"
        # 每个日期最多五个波动档；同 M 值从不按股票名拆开。
        for positions in frozen.groupby("date", sort=False).indices.values():
            if "M" in frozen:
                volatility = frozen.iloc[positions]["M"].to_numpy(dtype=float)
                cuts = np.unique(np.quantile(volatility, [0.2, 0.4, 0.6, 0.8]))
                bins = np.searchsorted(cuts, volatility, side="left")
            else:
                bins = np.zeros(len(positions), dtype=int)
            for bin_id in np.unique(bins):
                members = positions[bins == bin_id]
                self._group_values[members] = self._values[members].mean(axis=0)
        self._matched_direction = self._group_values[:, 0] - self._group_values[:, 1]
        # 整只股票重抽在冻结时的股票集合上进行。
        codes, self._stocks = pd.factorize(frozen["symbol"], sort=True)
        self._stock_codes = codes.astype(np.int64)
        self._baseline_summary = _summary_checked(frozen)
        self.starts = np.arange(len(self.dates) - self.window_days + 1)
        self.ends = self.starts + self.window_days - 1
        ages = len(self.dates) - 1 - self.ends
        self._time_weights = np.exp2(-ages / self.half_life_days)
        pool = self._windows_checked(frozen, np.arange(len(frozen)))
        self.random_day_score = float(pool["weights"][pool["active"]] @ pool["score"][pool["active"]])
        for array in (self._values, self._direction, self._group_values, self._matched_direction,
                      self._date_indices, self._stock_codes, self.starts, self.ends, self._time_weights):
            array.flags.writeable = False

    def _indices_checked(self, rows: pd.DataFrame) -> np.ndarray:
        keys = pd.MultiIndex.from_frame(rows[["symbol", "date"]])
        indices = self._keys.get_indexer(keys)
        if (indices < 0).any():
            raise ValueError("候选日期必须属于建立窗口计划的基线全集")
        # 只核对候选行，防止同一股票日混入另一评价定义的标签。
        columns = ["upside", *STATES]
        columns += [name for name in ("M", "drawdown") if name in rows and name in self._baseline]
        expected = self._baseline.iloc[indices][columns].to_numpy(dtype=float)
        if not np.array_equal(expected, rows[columns].to_numpy(dtype=float)):
            raise ValueError("候选标签与窗口计划的冻结标签不一致；请为新标签创建新计划")
        return indices

    def assert_baseline(self, baseline: pd.DataFrame) -> None:
        """同一快照句柄为常数开销；另传副本时核对整个全集与标签。"""
        if any(baseline is item for item in self._accepted_baselines):
            return
        checked = _rows(baseline)
        if len(checked) != len(self._baseline) or set(checked.columns) & {"M", "drawdown"} != set(self._baseline.columns) & {"M", "drawdown"}:
            raise ValueError("比较基线必须与窗口计划的原始基线全集一致")
        self._indices_checked(checked)
        self._accepted_baselines.append(baseline)

    def _windows_checked(self, rows: pd.DataFrame, indices: np.ndarray,
                         weights: np.ndarray | None = None) -> dict:
        """weights 是每个股票日的重复次数，缺省全 1；整只重抽时传入抽中次数。"""
        n_dates = len(self.dates)
        date_ids = self._date_indices[indices]
        w = np.ones(len(indices)) if weights is None else np.asarray(weights, dtype=float)
        daily_count = np.bincount(date_ids, weights=w, minlength=n_dates)
        daily_direction = np.bincount(date_ids, weights=w * self._direction[indices], minlength=n_dates)
        daily_matched = np.bincount(date_ids, weights=w * self._matched_direction[indices], minlength=n_dates)

        def rolling(values):
            prefix = np.concatenate(([0], np.cumsum(values)))
            return prefix[self.ends + 1] - prefix[self.starts]

        counts = rolling(daily_count)
        active = counts > 0
        scores = np.full(len(counts), np.nan)
        matched = np.full(len(counts), np.nan)
        np.divide(rolling(daily_direction), counts, out=scores, where=active)
        np.divide(rolling(daily_matched), counts, out=matched, where=active)
        weights = np.zeros(len(counts), dtype=float)
        if active.any():
            # 先减去最近活跃窗口的年龄，避免很旧的稀疏机会权重全下溢为 0。
            # 仅乘共同常数，仍是原先近期权重在非空窗口上的条件归一。
            relative_ages = self.ends[active].max() - self.ends[active]
            active_weights = np.exp2(-relative_ages / self.half_life_days)
            weights[active] = active_weights / active_weights.sum()
        return {"count": counts, "score": scores, "matched_score": matched,
                "active": active, "weights": weights, "starts": self.starts.copy(),
                "ends": self.ends.copy(), "daily_count": daily_count,
                "daily_direction_sum": daily_direction, "daily_matched_sum": daily_matched}

    def window_statistics(self, rows: pd.DataFrame) -> dict:
        """给研究返回按真实日历排序的窗口数组；空窗口值 NaN、权重 0。"""
        checked = _rows(rows)
        return self._windows_checked(checked, self._indices_checked(checked))

    def summarize(self, rows: pd.DataFrame) -> dict:
        """返回方向成绩 Z、同日普通买入对照 B、领先 Z-B、排名分、对随机日
        基线的差及覆盖，不施加约束。"""
        checked = _rows(rows)
        indices = self._indices_checked(checked)
        candidate = _summary_checked(checked)
        windows = self._windows_checked(checked, indices)
        active, weights = windows["active"], windows["weights"]
        score = float(weights[active] @ windows["score"][active]) if active.any() else None
        matched_score = float(weights[active] @ windows["matched_score"][active]) if active.any() else None
        adjusted, shrinkage = _adjust_score(score, matched_score, windows, self._shrinkage)
        recent_start = max(0, len(self.dates) - self.recent_days)
        date_ids = self._date_indices[indices]
        recent = date_ids >= recent_start
        states = self._group_values[indices].sum(axis=0)
        resolved = float(states[0] + states[1])
        matched_summary = {
            "count": len(checked), **{key: float(states[i]) for i, key in enumerate(STATES)},
            "direction_count": resolved,
            "direction": float(states[0] / resolved) if resolved > 0 else None,
            "direction_score": float((states[0] - states[1]) / len(checked)) if len(checked) else None,
            # 分组均值足够精确计算方向；不把组内中位数误称混合后的中位数。
            "median_upside": None, "median_drawdown": None,
        }
        coverage = {
            "stocks": candidate["stocks"],
            "time_blocks": int(len(np.unique(date_ids // self.window_days))),
            "active_dates": int(len(np.unique(date_ids))),
            "recent_days": min(self.recent_days, len(self.dates)),
            "recent_buy_days": int(recent.sum()),
            "recent_active_dates": int(len(np.unique(date_ids[recent]))),
            "active_window_fraction": float(active.mean()),
            "weighted_active_window_fraction": float(self._time_weights[active].sum() / self._time_weights.sum()),
        }
        return {
            **candidate, "score": adjusted, "score_mode": self.score_mode,
            "shrinkage": shrinkage,
            "raw_direction_score": score, "pooled_direction_score": candidate["direction_score"],
            "matched_direction_score": matched_score,
            "direction_difference": score - matched_score if score is not None else None,
            "random_day_score": self.random_day_score,
            "random_day_difference": score - self.random_day_score if score is not None else None,
            "raw_median_upside": candidate["median_upside"],
            "coverage": coverage,
            "window": {
                "total": int(len(active)), "active": int(active.sum()), "empty": int((~active).sum()),
                "days": self.window_days, "half_life_days": self.half_life_days,
                "median_direction_score": float(np.median(windows["score"][active])) if active.any() else None,
                "recent_window_score": float(windows["score"][-1]) if active[-1] else None,
                "recent_window_count": int(windows["count"][-1]),
            },
            "baseline_matching": self.baseline_matching,
            "summaries": {"candidate": candidate, "matched_baseline": matched_summary,
                          "baseline": deepcopy(self._baseline_summary)},
            "evidence_status": "uncalibrated_no_independent_sample_claim",
        }

    def stock_bootstrap(self, rows: pd.DataFrame, resamples: int = 200, seed: int = 0) -> dict:
        """整只股票有放回重抽，估计方向成绩 Z 与领先 Δ 的偶然波动（未校准）。

        每次在冻结时的股票集合上抽同样多只股票，抽中几次就把该股全部买点
        日计几次。抽空（候选股票全未抽中）的次数单列；非空不足两次时标准差
        为 None。
        """
        if isinstance(resamples, bool) or not isinstance(resamples, Integral) or resamples < 1:
            raise ValueError("resamples 必须为正整数")
        checked = _rows(rows)
        indices = self._indices_checked(checked)
        codes = self._stock_codes[indices]
        rng = np.random.default_rng(seed)
        draws = rng.multinomial(len(self._stocks), np.full(len(self._stocks), 1 / len(self._stocks)),
                                size=int(resamples))
        z, delta = [], []
        for draw in draws:
            windows = self._windows_checked(checked, indices, draw[codes])
            active, weights = windows["active"], windows["weights"]
            if active.any():
                z.append(float(weights[active] @ windows["score"][active]))
                delta.append(z[-1] - float(weights[active] @ windows["matched_score"][active]))
        sd = lambda values: float(np.std(values, ddof=1)) if len(values) >= 2 else None
        return {"resamples": int(resamples), "seed": seed, "stocks": len(self._stocks),
                "z_sd": sd(z), "delta_sd": sd(delta), "empty_fraction": 1 - len(z) / int(resamples)}


def summarize(rows: pd.DataFrame, plan: WindowPlan) -> dict:
    """供开发检查使用的无约束候选汇总，与正式评分共用同一计算。"""
    return plan.summarize(rows)


def _hard_constraints(candidate: dict, reference: dict, policy: dict) -> tuple[list[str], list[float]]:
    names = ["reference_opportunity_floor", "recent_reference_opportunity_floor"]
    recent_count = candidate["coverage"]["recent_buy_days"]
    reference_recent = reference["coverage"]["recent_buy_days"]
    values = [
        (policy["min_reference_fraction"] * reference["count"] - candidate["count"]) / max(1, reference["count"]),
        (policy["min_recent_reference_fraction"] * reference_recent - recent_count) / max(1, reference_recent),
    ]
    for metric, key in (("median_upside", "min_median_upside"), ("median_drawdown", "min_median_drawdown")):
        if policy[key] is not None:
            names.append(key)
            values.append(1.0 if candidate[metric] is None else policy[key] - candidate[metric])
    return names, [float(value) for value in values]


def assess(rows: pd.DataFrame, reference: pd.DataFrame, baseline: pd.DataFrame,
           plan: WindowPlan, policy: Mapping | None = None) -> dict:
    """按整轮冻结的排名分排名；机会与可选空间/回撤要求检查原始观察值。"""
    rules = normalize_policy(policy)
    plan.assert_baseline(baseline)
    candidate, old = plan.summarize(rows), plan.summarize(reference)
    names, constraints = _hard_constraints(candidate, old, rules)
    candidate["summaries"]["reference"] = old["summaries"]["candidate"]
    candidate["policy"] = rules
    candidate["score_floor_used"] = candidate["score"] is None
    return {
        "score": candidate["score"] if candidate["score"] is not None else SCORE_FLOOR,
        "constraints": constraints, "constraint_names": names,
        "feasible": all(value <= 0 for value in constraints), "statistics": candidate,
    }


def comparison(candidate: pd.DataFrame, reference: pd.DataFrame, baseline: pd.DataFrame,
               plan: WindowPlan, policy: Mapping | None = None) -> dict:
    """最后检查与复核沿用搜索的排名分及同一约束，只提供观测差异。

    证据算法尚未校准，窗口覆盖不能证明改善显著，因此不生成区间。
    """
    evaluated = assess(candidate, reference, baseline, plan, policy)
    new, old = evaluated["statistics"], plan.summarize(reference)
    new_score, old_score = new["score"], old["score"]
    new_upside, old_upside = new["median_upside"], old["median_upside"]
    return {
        "score_mode": new["score_mode"],
        "score_difference": new_score - old_score if new_score is not None and old_score is not None else None,
        "new_score": new_score, "reference_score": old_score,
        "new_direction_score": new["raw_direction_score"],
        "reference_direction_score": old["raw_direction_score"],
        "new_matched_direction_score": new["matched_direction_score"],
        "reference_matched_direction_score": old["matched_direction_score"],
        "new_direction_difference": new["direction_difference"],
        "reference_direction_difference": old["direction_difference"],
        "random_day_score": new["random_day_score"],
        "new_random_day_difference": new["random_day_difference"],
        "reference_random_day_difference": old["random_day_difference"],
        "shrinkage": {"candidate": new["shrinkage"], "reference": old["shrinkage"]},
        "upside_difference": new_upside - old_upside if new_upside is not None and old_upside is not None else None,
        "hard_constraints_passed": evaluated["feasible"],
        "constraint_names": evaluated["constraint_names"], "constraints": evaluated["constraints"],
        "evidence_status": new["evidence_status"],
        "summaries": new["summaries"], "baseline_matching": plan.baseline_matching,
        "coverage": {"candidate": new["coverage"], "reference": old["coverage"]},
        "window": {"candidate": new["window"], "reference": old["window"]},
        "policy": new["policy"],
    }
