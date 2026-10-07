"""同日对照、领先、偶然波动、分年、扎堆度、毕业判定。

对照的范围:同一日期 t、池内、有有效标签的全部股票日(包括候选自己),即整张面板。

分档:每天按 M_t 用 qcut(q = min(max_bands, n // min_per_band), duplicates='drop')
切档,n 是当天面板行数;q < 2 时整天一档。一个 (日期, 档) 叫一个格子,记
档内方向值均值 B_dir、档内 mag 值、档内股票日数。

一组命中(同股同日已去重)的指标:
  方向领先 = mean_i(dir_i) − mean_i(B_dir[格子_i])
  幅度领先 = median_i(mag_i) − 对照混合中位数;对照混合:每个命中 i 所在格子里的全部
            mag 值,每个值权重 1/格内个数(每个命中合计贡献权重 1),合在一起取加权中位数
偶然波动:命中按 symbol 分组,有放回抽满原 symbol 数,对照不动,重复 n_boot 次(seed 固定),
  取领先的标准差(ddof=1)× 放大系数(命中数 ≥ noise_large_n 用 inflate_large,否则 inflate_small)。
分年:按决策日 t 的年份分别算,另加「全部」一行。
扎堆度(「全部」命中):单 ISO 周命中占比最大值、单只股票命中占比最大值、不同股票数 / 周数。
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

ALL_SCOPE = "全部"


def _ns(dates) -> np.ndarray:
    """日期统一成 datetime64[ns](parquet 读回可能换单位,做键前先对齐)。"""
    return pd.to_datetime(pd.Series(dates)).values.astype("datetime64[ns]")


def weighted_median(values: np.ndarray, weights: np.ndarray, presorted: bool = False) -> float:
    """加权中位数:累计权重第一次 ≥ 总权重一半处的值;恰好等于一半时与下一个值取平均。

    等权时与 np.median 完全一致(偶数个取中间两个的平均)。
    """
    values = np.asarray(values, dtype=float)
    weights = np.asarray(weights, dtype=float)
    keep = weights > 0
    values, weights = values[keep], weights[keep]
    if len(values) == 0:
        return float("nan")
    if not presorted:
        order = np.argsort(values, kind="mergesort")
        values, weights = values[order], weights[order]
    cw = np.cumsum(weights)
    half = cw[-1] / 2.0
    i = int(np.searchsorted(cw, half - 1e-12 * cw[-1], side="left"))
    i = min(i, len(values) - 1)
    if math.isclose(cw[i], half, rel_tol=1e-9, abs_tol=1e-12) and i + 1 < len(values):
        return float((values[i] + values[i + 1]) / 2.0)
    return float(values[i])


def assign_bands(panel: pd.DataFrame, max_bands: int = 5, min_per_band: int = 20) -> np.ndarray:
    """每行所属的格子编号(日期 × 档,全局唯一整数)。"""
    band = np.zeros(len(panel), dtype=np.int64)
    for _, idx in panel.groupby("date", sort=False).indices.items():
        n = len(idx)
        q = min(max_bands, n // min_per_band)
        if q >= 2:
            codes = pd.qcut(panel["M"].values[idx], q=q, labels=False, duplicates="drop")
            band[idx] = np.asarray(codes, dtype=np.int64)
    keys = pd.DataFrame({"date": panel["date"].values, "band": band})
    return keys.groupby(["date", "band"], sort=True).ngroup().values.astype(np.int64)


class Control:
    """整张面板上的同日对照。panel 需含 date / symbol / M / dir / mag 列。"""

    def __init__(self, panel: pd.DataFrame, ccfg: dict):
        self.panel = panel.reset_index(drop=True)
        self.cell = assign_bands(self.panel, ccfg["max_bands"], ccfg["min_per_band"])
        n_cells = int(self.cell.max()) + 1 if len(self.cell) else 0
        self.count = np.bincount(self.cell, minlength=n_cells).astype(float)
        dir_sum = np.bincount(self.cell, weights=self.panel["dir"].values.astype(float),
                              minlength=n_cells)
        with np.errstate(invalid="ignore", divide="ignore"):
            self.b_dir = dir_sum / self.count
        mag = self.panel["mag"].values.astype(float)
        order = np.argsort(mag, kind="mergesort")
        self.mag_sorted = mag[order]
        self.cell_sorted = self.cell[order]
        self.n_cells = n_cells
        self._row = {(s, d): i for i, (s, d) in
                     enumerate(zip(self.panel["symbol"].values, _ns(self.panel["date"])))}

    def rows_of(self, hits: pd.DataFrame) -> np.ndarray:
        """命中 (symbol, date) → 面板行号(同股同日去重,保持首次出现顺序);不在面板里的丢弃。"""
        rows = [self._row.get((s, d)) for s, d in zip(hits["symbol"].values, _ns(hits["date"]))]
        return np.array(pd.unique(np.array([r for r in rows if r is not None], dtype=np.int64)),
                        dtype=np.int64)

    def _subset(self, cells: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """只保留命中碰到的格子里的已排序 mag 值(加权中位数只看这些)。"""
        touched = np.zeros(self.n_cells, dtype=bool)
        touched[cells] = True
        mask = touched[self.cell_sorted]
        return self.cell_sorted[mask], self.mag_sorted[mask]

    def ctrl_mag_median(self, hit_cells: np.ndarray, subset=None) -> float:
        """对照混合中位数。hit_cells:每个命中所在格子(可重复)。subset:_subset 的结果。"""
        cs, vs = subset if subset is not None else self._subset(hit_cells)
        h = np.bincount(hit_cells, minlength=self.n_cells).astype(float)
        w = h[cs] / self.count[cs]
        return weighted_median(vs, w, presorted=True)

    def evaluate(self, rows: np.ndarray, ccfg: dict, with_noise: bool = True) -> dict:
        """一组命中(面板行号,已去重)的一行统计。"""
        n = len(rows)
        base = {"n_hits": int(n), "n_stocks": 0, "n_weeks": 0,
                "hit_dir_mean": None, "ctrl_dir_mean": None, "dir_lead": None, "dir_noise": None,
                "hit_mag_median": None, "ctrl_mag_median": None, "mag_lead": None,
                "mag_noise": None}
        if n == 0:
            return base
        p = self.panel
        sym = p["symbol"].values[rows]
        dates = pd.DatetimeIndex(p["date"].values[rows])
        iso = dates.isocalendar()
        weeks = (iso["year"].astype(str) + "-" + iso["week"].astype(str)).values
        dirs = p["dir"].values[rows].astype(float)
        mags = p["mag"].values[rows].astype(float)
        cells = self.cell[rows]
        subset = self._subset(cells)

        hit_dir = float(dirs.mean())
        ctrl_dir = float(self.b_dir[cells].mean())
        hit_mag = float(np.median(mags))
        ctrl_mag = self.ctrl_mag_median(cells, subset)
        base.update({
            "n_stocks": int(len(set(sym))), "n_weeks": int(len(set(weeks))),
            "hit_dir_mean": hit_dir, "ctrl_dir_mean": ctrl_dir, "dir_lead": hit_dir - ctrl_dir,
            "hit_mag_median": hit_mag, "ctrl_mag_median": ctrl_mag, "mag_lead": hit_mag - ctrl_mag,
        })
        if with_noise:
            d_noise, m_noise = self.noise(rows, ccfg, subset)
            base["dir_noise"], base["mag_noise"] = d_noise, m_noise
        return base

    def noise(self, rows: np.ndarray, ccfg: dict, subset) -> tuple[float, float]:
        """按股票整只重抽的偶然波动(已乘放大系数)。"""
        p = self.panel
        sym = p["symbol"].values[rows]
        uniq, inv = np.unique(sym, return_inverse=True)
        groups = [rows[inv == g] for g in range(len(uniq))]
        dir_all = p["dir"].values.astype(float)
        mag_all = p["mag"].values.astype(float)
        rng = np.random.default_rng(ccfg["seed"])
        d_leads, m_leads = [], []
        for _ in range(int(ccfg["n_boot"])):
            pick = rng.integers(0, len(groups), len(groups))
            r = np.concatenate([groups[g] for g in pick])
            c = self.cell[r]
            d_leads.append(dir_all[r].mean() - self.b_dir[c].mean())
            m_leads.append(np.median(mag_all[r]) - self.ctrl_mag_median(c, subset))
        inflate = (ccfg["inflate_large"] if len(rows) >= ccfg["noise_large_n"]
                   else ccfg["inflate_small"])
        if len(d_leads) < 2:
            return 0.0, 0.0
        return (float(np.std(d_leads, ddof=1) * inflate),
                float(np.std(m_leads, ddof=1) * inflate))


def concentration(panel: pd.DataFrame, rows: np.ndarray) -> dict:
    if len(rows) == 0:
        return {"max_week_share": None, "max_stock_share": None, "n_stocks": 0, "n_weeks": 0}
    dates = pd.DatetimeIndex(panel["date"].values[rows])
    iso = dates.isocalendar()
    weeks = pd.Series(iso["year"].astype(str) + "-" + iso["week"].astype(str)).value_counts()
    stocks = pd.Series(panel["symbol"].values[rows]).value_counts()
    n = len(rows)
    return {"max_week_share": float(weeks.iloc[0] / n), "max_stock_share": float(stocks.iloc[0] / n),
            "n_stocks": int(len(stocks)), "n_weeks": int(len(weeks))}


def graduation(rows_by_scope: dict, conc: dict, years: list[str], gcfg: dict) -> dict:
    """毕业判定:五项检查全过才算通过。缺数据(None)的检查一律判不通过。"""
    allr = rows_by_scope.get(ALL_SCOPE) or {}
    dl, ml, dn = allr.get("dir_lead"), allr.get("mag_lead"), allr.get("dir_noise")
    checks = {
        "dir_lead": dl is not None and dl >= gcfg["dir_lead_min"],
        "mag_lead": ml is not None and ml > gcfg["mag_lead_min"],
        "each_year": all((rows_by_scope.get(y) or {}).get("dir_lead") is not None
                         and rows_by_scope[y]["dir_lead"] > 0 for y in years),
        "beyond_noise": dl is not None and dn is not None and dl >= gcfg["noise_mult"] * dn,
        "not_clustered": (conc.get("max_week_share") is not None
                          and conc["max_week_share"] <= gcfg["max_week_share"]
                          and conc["max_stock_share"] <= gcfg["max_stock_share"]),
    }
    return {"passed": all(checks.values()), "checks": checks}


def train_years(cfg: dict) -> list[str]:
    y0 = pd.Timestamp(cfg["train_start"]).year
    y1 = pd.Timestamp(cfg["train_end"]).year
    return [str(y) for y in range(y0, y1 + 1)]


def summarize(control: Control, rows: np.ndarray, cfg: dict) -> dict:
    """清单 summary:「全部」+ 每个训练年份各一行,扎堆度,毕业判定。"""
    ccfg = cfg["control"]
    years = train_years(cfg)
    p = control.panel
    out_rows = []
    by_scope: dict = {}
    hit_years = pd.DatetimeIndex(p["date"].values[rows]).year.astype(str) if len(rows) else []
    for scope in [ALL_SCOPE] + years:
        r = rows if scope == ALL_SCOPE else rows[np.asarray(hit_years) == scope]
        row = {"scope": scope, **control.evaluate(r, ccfg)}
        out_rows.append(row)
        by_scope[scope] = row
    conc = concentration(p, rows)
    return {
        "rows": out_rows,
        "concentration": {"max_week_share": conc["max_week_share"],
                          "max_stock_share": conc["max_stock_share"]},
        "graduation": graduation(by_scope, conc, years, cfg["graduation"]),
    }
