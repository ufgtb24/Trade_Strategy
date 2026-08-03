"""评估管线骨架 —— 复制到 scratchpad,只改顶部 CONFIG 常量。

产出「每买点窗一行」的明细 + 汇总(含 score / 硬门 / 双 label 列)。

口径(与 scripts/path2_eval_<app>.py 对齐):
- 双端缓冲切窗:首部 eval_meta.head_buffer_trading_days(指标 warm-up)、
  尾部 max(HORIZONS)(label 可见),交易日→日历日按 1.65 折算;
- 有效性 = end_node event 起点日期 ∈ [start, end];
- 去重 = 同 end_node event_id 只计一次(评估对象是买点窗,不是 match);
- label_window = 窗内逐日 max(high[t+1..t+N])/close[t]-1 的均值(path2.eval,受窗宽影响);
- label_first  = 只取窗第一天的同一算式(**区间无关,排序一律用它**,见 SKILL 关卡 2)。

自检门(硬闸,失败即 raise):label 逐观测用独立实现重算并比对。
索引错位时所有统计静默全错,自检是数据链路唯一的正确性证明。禁止注释掉。

## 与 path2_web.eval_runner 的关系(别"好心"改成直接调 run_eval)

`param_overrides` 的 nested-dict 叠加语义与 `eval_runner._eval_ticker` **逐字对齐**
(base = load_params() 读 yaml SSoT,逐 section `dataclasses.replace` 后合并),
所以本脚本的数字与 web /scan、与 run_eval 可比——已实测:两年 n / median / score
与 eval_runner 口径逐字一致。

**但不能直接用 `run_eval` 替掉本脚本的执行层**:它每行只出 `returns`(窗均值口径),
不出「买点窗第一天」的区间无关 label,而那正是 SKILL 关卡 2 防刷分的排序依据。
换成 run_eval = 关卡 2 静默失效 = 缩窗可以白拿分而没人看得见。

**该复用 eval_runner 的地方是 `run_regress`**(见 SKILL 流程第 7 步误伤审查):
它按 (symbol, buy_date) 对拍改前 baseline,removed 行带改前收益,
正好回答"这次调参误伤了哪些高 forward_return 票"——本脚本不提供这个。
"""
from __future__ import annotations

import importlib
import sys
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from pathlib import Path

REPO_OVERRIDE = None    # ← 脚本被复制到 repo 外(scratchpad)时,填 repo 根目录绝对路径


def _find_repo() -> Path:
    """定位 repo root。顺序:显式覆盖 → cwd 向上 → 脚本位置向上。

    不用 __file__.parents[N]:本脚本设计为被复制到 scratchpad 使用,
    固定层数一复制就断(且断得很隐蔽——DATA_DIR 指向不存在的目录,
    glob 返回空,一路静默产出空 DataFrame)。
    """
    if REPO_OVERRIDE:
        return Path(REPO_OVERRIDE)
    for base in (Path.cwd(), Path(__file__).resolve().parent):
        for p in (base, *base.parents):
            if (p / "path2_apps").is_dir() and (p / "datasets" / "pkls").is_dir():
                return p
    raise RuntimeError(
        "找不到 repo root(需同时含 path2_apps/ 与 datasets/pkls/)。"
        "脚本在 repo 外运行时,请填顶部 REPO_OVERRIDE 常量。")


REPO = _find_repo()
sys.path.insert(0, str(REPO))

import pandas as pd  # noqa: E402

from path2.eval import match_forward_returns  # noqa: E402
from path2_web.data import slice_window  # noqa: E402

# ===== CONFIG(只改这里) =====
APP = "bottom_breakout_burst"        # 待调参的 app
BASELINE_APP = "bo_only"             # 平凡对照 = 同上游参数、去掉待评估过滤层的退化版
HORIZONS = (5, 10, 20)               # label horizon 列表;主口径取最后一个
N0 = 200                             # 收缩常数,同时是硬门(SKILL 关卡 3)
WORKERS = 26
DATA_DIR = REPO / "datasets" / "pkls"
# ============================

RATIO = 1.65                          # 交易日→日历日
MAIN_H = HORIZONS[-1]


def _load(app: str):
    m = importlib.import_module(f"path2_apps.{app}")
    return m


def build_params(app: str, overrides: dict):
    """overrides = {section: {field: value}};空 dict = 用 app 的 params.yaml 原值。"""
    p = _load(app).load_params()
    for sect, kv in (overrides or {}).items():
        p = replace(p, **{sect: replace(getattr(p, sect), **kv)})
    return p


def _fwd(win: pd.DataFrame, t: int, n: int):
    """独立实现的单日前瞻收益(自检用,勿与 path2.eval 共用代码)。"""
    if t + n >= len(win):
        return None
    return float(win["high"].iloc[t + 1: t + n + 1].max()) / float(win["close"].iat[t]) - 1.0


def _eval_one(args):
    app, params, head_buf, start, end, end_node, pkl = args
    ticker = pkl.stem
    try:
        mod = _load(app)
        df = pd.read_pickle(pkl)
        s_ts, e_ts = pd.to_datetime(start), pd.to_datetime(end)
        win = slice_window(df,
                           s_ts - pd.Timedelta(days=round(head_buf * RATIO)),
                           e_ts + pd.Timedelta(days=round(MAIN_H * RATIO)))
        if len(win) == 0:
            return (ticker, [], None)
        res = mod.analyze(win, params)
        rows, seen = [], set()
        for m in res.matches:
            ev = m.node_index[end_node]          # ⚠ 不是 role_index(已改名)
            buy_date = win["date"].iat[ev.start_idx]
            if not (s_ts <= buy_date <= e_ts) or ev.event_id in seen:
                continue
            seen.add(ev.event_id)
            rets = match_forward_returns(m, end_node, win, HORIZONS)
            row = {"ticker": ticker, "buy_date": str(buy_date)[:10],
                   "n_buy_days": ev.end_idx - ev.start_idx + 1,
                   "outcome": getattr(ev, "outcome", "")}
            for n in HORIZONS:
                row[f"win_{n}"] = rets[n]         # 窗均值口径(受窗宽影响)
            row["first"] = _fwd(win, ev.start_idx, MAIN_H)   # 区间无关口径 ← 排序用它
            # 自检:单日窗(start==end)时两口径必须一致
            if ev.start_idx == ev.end_idx and row[f"win_{MAIN_H}"] is not None:
                if abs(row[f"win_{MAIN_H}"] - row["first"]) > 1e-9:
                    raise AssertionError(
                        f"{ticker} {buy_date}: 单日窗两口径不一致 "
                        f"{row[f'win_{MAIN_H}']} vs {row['first']} — 索引对齐已损坏")
            rows.append(row)
        return (ticker, rows, None)
    except Exception as e:
        return (ticker, [], f"{type(e).__name__}: {e}")


def run_config(overrides: dict, start: str, end: str, app: str = APP,
               tag: str = "", baseline_median: float | None = None):
    """跑一个配置,返回 (detail_df, summary)。baseline_median=None 时 score 为 None。"""
    params = build_params(app, overrides)
    mod = _load(app)
    meta = mod.eval_meta(params)
    end_node, head_buf = meta["end_node"], meta["head_buffer_trading_days"]
    pkls = sorted(DATA_DIR.glob("*.pkl"))
    rows, errors = [], []
    with ProcessPoolExecutor(max_workers=WORKERS) as ex:
        for _t, r, err in ex.map(
                _eval_one,
                [(app, params, head_buf, start, end, end_node, p) for p in pkls],
                chunksize=20):
            if err:
                errors.append(err)
            else:
                rows.extend(r)
    detail = pd.DataFrame(rows)
    if len(detail) == 0:
        return detail, {"tag": tag, "n": 0, "errors": len(errors), "score": None,
                        "gate": False, "overrides": overrides}
    s_first = detail["first"].dropna()
    s_win = detail[f"win_{MAIN_H}"].dropna()
    n = len(detail)
    med = float(s_first.median())
    summary = {
        "tag": tag, "overrides": overrides, "n": n,
        "tickers": int(detail["ticker"].nunique()),
        "buy_days": int(detail["n_buy_days"].sum()),
        "median": med,                                   # 区间无关口径 ← 主口径
        "median_window": float(s_win.median()),          # 窗均值口径(仅对照,防刷分)
        "q25": float(s_first.quantile(0.25)),
        "q75": float(s_first.quantile(0.75)),
        "win_rate": float((s_first > 0).mean()),
        "errors": len(errors),
    }
    summary["score"] = ((n / (n + N0)) * (med - baseline_median)
                        if baseline_median is not None else None)
    summary["gate"] = bool(n >= N0 and summary["q25"] >= 0)
    return detail, summary


def baseline_median(start: str, end: str) -> float:
    """平凡对照的主口径中位数。**每个时间窗都要重算**(市场平移,见 SKILL 关卡 1)。"""
    det, _ = run_config({}, start, end, app=BASELINE_APP, tag="baseline")
    return float(det["first"].dropna().median())


def fmt(s: dict) -> str:
    def f(k, p=4):
        v = s.get(k)
        return "None" if v is None else f"{v:.{p}f}"
    return (f"{s['tag']:<20s} n={s['n']:5d} med={f('median')} "
            f"med_win={f('median_window')} q25={f('q25')} "
            f"score={f('score')} gate={'Y' if s.get('gate') else 'n'}")


if __name__ == "__main__":
    import json
    START, END = "2025-01-01", "2026-01-01"
    bm = baseline_median(START, END)
    print(f"平凡对照({BASELINE_APP}) median = {bm:.4f}")
    ov = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    det, s = run_config(ov, START, END, tag="current", baseline_median=bm)
    print(fmt(s))
