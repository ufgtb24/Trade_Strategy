"""取命中:path2 app 方式,或规则文件方式。两种方式都输出 (symbol, date) 列表。

app 方式(--app <pattern_id> [--params <yaml>]),以 path2_web/eval_runner.py::_eval_ticker
为范本:eval_meta() 给出买点 node 与首部缓冲交易日数,按缓冲往前切窗、截到训练段末日;
build_pattern(params) + analyze;买点日取 end_node 各 event 的 sample_bar_indices();
买点不得早于确认根(start_idx >= confirm_idx,否则报错);只留训练段内的日子,同股同日去重。

规则文件方式(--rule <path>.py):文件里定义 `def signal(df) -> pd.Series`,返回与 df 对齐
的布尔序列,True 表示这一天收盘时成立。df 只含截到训练段末日的行情。
因果自检(必做):每只命中股票随机抽 causal_samples 个命中日 t,把 df 截到 t 再算一次,
t 处结果必须仍为 True,否则抛 CausalityError 并列出违规的股票和日期。

只对面板里出现过的股票(有池内股票日的)跑;命中再和面板连接才有标签,所以不在池内或
标签无效的命中自然落掉。
"""
from __future__ import annotations

import hashlib
import importlib
import importlib.util
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from chart_workflow.panel import read_stock

TRADING_TO_CALENDAR_RATIO = 1.65   # 与 path2_web/scan.py 同值:交易日 → 日历日


class CausalityError(RuntimeError):
    """规则文件偷看了未来:截到 t 再算,t 处结果变了。"""

    def __init__(self, violations: list[tuple[str, str]]):
        self.violations = violations
        lines = "\n".join(f"  {s} @ {d}" for s, d in violations[:50])
        more = f"\n  …共 {len(violations)} 处" if len(violations) > 50 else ""
        super().__init__(f"规则因果自检失败:截到当日再算结果不同(偷看了未来)\n{lines}{more}")


# ── 规则文件方式 ─────────────────────────────────────────────────────────────

def load_rule(path) -> callable:
    path = Path(path).resolve()
    spec = importlib.util.spec_from_file_location(f"_cw_rule_{path.stem}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    fn = getattr(mod, "signal", None)
    if not callable(fn):
        raise ValueError(f"规则文件 {path} 里没有 signal(df) 函数")
    return fn


def _signal_bool(fn, df: pd.DataFrame) -> np.ndarray:
    s = fn(df)
    if not isinstance(s, pd.Series) or len(s) != len(df):
        raise ValueError("signal(df) 必须返回与 df 等长的 pd.Series")
    return s.fillna(False).astype(bool).values


def _rule_worker(args):
    rule_path, symbol, cfg = args
    fn = load_rule(rule_path)
    df = read_stock(cfg, symbol)
    if len(df) == 0:
        return symbol, [], []
    sig = _signal_bool(fn, df)
    lo = pd.Timestamp(cfg["train_start"])
    pos = np.flatnonzero(sig & (df.index >= lo))
    dates = [df.index[i] for i in pos]
    bad = []
    if len(pos):
        rng = np.random.default_rng(
            [cfg["rules"]["seed"], int(hashlib.md5(symbol.encode()).hexdigest()[:8], 16)])
        n = min(int(cfg["rules"]["causal_samples"]), len(pos))
        for i in rng.choice(pos, size=n, replace=False):
            cut = df.iloc[: i + 1]
            if not _signal_bool(fn, cut)[-1]:
                bad.append((symbol, df.index[i].strftime("%Y-%m-%d")))
    return symbol, dates, bad


def hits_from_rule(rule_path, symbols, cfg: dict) -> pd.DataFrame:
    """规则文件方式取命中。违反因果自检 → CausalityError。"""
    rule_path = str(Path(rule_path).resolve())
    load_rule(rule_path)                       # 先在主进程验一下能加载
    jobs = [(rule_path, s, cfg) for s in symbols]
    results = _map(_rule_worker, jobs, cfg)
    bad = [b for _, _, bs in results for b in bs]
    if bad:
        raise CausalityError(sorted(bad))
    rows = [(s, d) for s, ds, _ in results for d in ds]
    return _hits_frame(rows)


def rule_fingerprint(rule_path) -> str:
    return hashlib.sha256(Path(rule_path).read_bytes()).hexdigest()[:10]


# ── app 方式 ────────────────────────────────────────────────────────────────

def _app_module(pattern_id: str):
    from path2_web.discovery import PatternRegistry
    reg = PatternRegistry()
    mp = reg.module_path(pattern_id)
    if mp is None:
        raise ValueError(f"找不到 pattern {pattern_id!r}(可用:{reg.ids()})")
    return mp


def _app_params(mod, params_yaml):
    if params_yaml:
        return mod.Params.from_yaml(Path(params_yaml))
    if hasattr(mod, "load_params"):
        return mod.load_params()
    return mod.Params.default()


def _app_worker(args):
    module_path, params_yaml, symbol, cfg = args
    from path2.dag.engine import analyze
    from path2.eval import _resolve_end_events

    mod = importlib.import_module(module_path)
    params = _app_params(mod, params_yaml)
    meta = mod.eval_meta(params)
    end_node, head = meta["end_node"], int(meta["head_buffer_trading_days"])
    df = read_stock(cfg, symbol)                      # 已截到训练段末日
    lo = pd.Timestamp(cfg["train_start"])
    buf_start = lo - pd.Timedelta(days=round(head * TRADING_TO_CALENDAR_RATIO))
    win = df[df.index >= buf_start].reset_index()     # 'date' 列 + 0-based 行号
    if len(win) == 0:
        return symbol, [], []
    spec = mod.build_pattern(params)
    res = analyze(spec, win, params)
    days: set = set()
    for m in res.matches:
        for ev in _resolve_end_events(m, end_node):
            if ev.start_idx < ev.confirm_idx:
                raise ValueError(
                    f"因果闸失效:{symbol} end_node='{end_node}' 买点 start_idx={ev.start_idx} "
                    f"< confirm_idx={ev.confirm_idx}({ev.__class__.__name__})")
            for t in ev.sample_bar_indices():
                if 0 <= t < len(win) and win["date"].iat[t] >= lo:
                    days.add(win["date"].iat[t])
    return symbol, sorted(days), []


def hits_from_app(pattern_id: str, params_yaml, symbols, cfg: dict) -> pd.DataFrame:
    module_path = _app_module(pattern_id)
    py = str(Path(params_yaml).resolve()) if params_yaml else None
    jobs = [(module_path, py, s, cfg) for s in symbols]
    results = _map(_app_worker, jobs, cfg)
    rows = [(s, d) for s, ds, _ in results for d in ds]
    return _hits_frame(rows)


# ── 公共 ────────────────────────────────────────────────────────────────────

def _map(fn, jobs, cfg):
    workers = max(1, int(cfg.get("workers", 1)))
    if workers == 1 or len(jobs) < 20:
        return [fn(j) for j in jobs]
    with ProcessPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(fn, jobs, chunksize=8))


def _hits_frame(rows) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=["symbol", "date"])
    if len(df):
        df["date"] = pd.to_datetime(df["date"])
    return df.drop_duplicates().sort_values(["date", "symbol"]).reset_index(drop=True)


def join_panel(hits: pd.DataFrame, panel: pd.DataFrame) -> pd.DataFrame:
    """命中和面板连接:只留池内、有有效标签的股票日(同股同日去重)。"""
    if len(hits) == 0:
        return panel.iloc[0:0].copy()
    h = hits[["symbol", "date"]].drop_duplicates().copy()
    h["date"] = pd.to_datetime(h["date"]).astype("datetime64[ns]")
    p = panel.copy()
    p["date"] = pd.to_datetime(p["date"]).astype("datetime64[ns]")
    return p.merge(h, on=["symbol", "date"], how="inner").reset_index(drop=True)
