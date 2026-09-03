"""scan-top-miss · 全宇宙批量出榜"大涨无 pattern match"股(入口 E · 独立 workflow)。

对 datasets/pkls/ 全集逐股跑 analyze:matches 非空(已命中)的股跳过;matches 为空、且
[start_date, end_date] 窗口内涨幅超过 min_pct% 的股视为"漏检候选"——再对该候选跑一次
scope=time 分派(复用 Task 15 derive_response · gate_collector),取窗口内出现次数最多的
gate_name 拼一条粗根因摘要,最终按涨幅降序输出 Top-K markdown 榜。

参数全部在 main() 起始声明(无 argparse,承 CLAUDE.md 入口规范);允许简单
`--key=value` 命令行 override:

    uv run python scripts/path2/scan-top-miss.py
    uv run python scripts/path2/scan-top-miss.py --start=2025-06-01 --end=2025-07-01 \
        --min-pct=30 --top-k=20 --out=scan_top_miss.md

--pkl-dir override 供测试/临时子集扫描用(不在原设计参数集内,纯附加)。
"""
from __future__ import annotations

import dataclasses
import importlib
import pathlib
import subprocess
import sys
from collections import Counter

# repo root: 用 git rev-parse 位置无关(脚本可能在 scripts/ 或 scripts/<sub>/),
# 勿用 __file__ parents[N]——耦合脚本所在深度,移动目录即坏
REPO = pathlib.Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
sys.path.insert(0, str(REPO))

import pandas as pd  # noqa: E402

from path2.dag.engine import analyze as _dag_analyze  # noqa: E402
from path2.debug import set_current_symbol  # noqa: E402
from path2_web.diagnose import Query, derive_response  # noqa: E402
from path2_web.gate_collector import attach_and_collect, detach  # noqa: E402


def main() -> None:
    # ===== 参数(在此处直接改,无 argparse) =====
    start_date = '2025-06-01'
    end_date = '2025-07-01'
    min_pct = 30.0
    top_k = 20
    out_path = 'scan_top_miss.md'
    pkl_dir = 'datasets/pkls/'
    spec_module = 'path2_apps.bottom_burst.dag_spec'
    # 简单 --key=value override(承 CLAUDE.md · 不用 argparse)
    for a in sys.argv[1:]:
        if a.startswith('--start='):
            start_date = a.split('=', 1)[1]
        elif a.startswith('--end='):
            end_date = a.split('=', 1)[1]
        elif a.startswith('--min-pct='):
            min_pct = float(a.split('=', 1)[1])
        elif a.startswith('--top-k='):
            top_k = int(a.split('=', 1)[1])
        elif a.startswith('--out='):
            out_path = a.split('=', 1)[1]
        elif a.startswith('--pkl-dir='):
            pkl_dir = a.split('=', 1)[1]
    # ============================================

    spec, params = _load_spec(spec_module)
    candidates = []

    pkl_files = sorted(pathlib.Path(pkl_dir).glob('*.pkl'))
    for pkl_file in pkl_files:
        symbol = pkl_file.stem
        set_current_symbol(symbol)
        try:
            result, win = _scan_symbol(spec, params, pkl_file)
        except Exception as e:                                   # noqa: BLE001
            print(f"[warn] {symbol} skipped: {type(e).__name__}: {e}", file=sys.stderr)
            continue
        finally:
            set_current_symbol(None)

        if len(win) == 0:
            continue
        if len(result.matches) > 0:
            continue                                              # 已有 match · 不算漏检

        pct = _compute_pct_change(win, start_date, end_date)
        if pct is None or pct < min_pct:
            continue

        # 跑 scope=time 拿窗口内主导 gate
        start_bar = _date_to_bar(win, start_date)
        end_bar = _date_to_bar(win, end_date)
        query = Query(symbol=symbol, scope='time', start_bar=start_bar, end_bar=end_bar)
        resp = derive_response(query, result=result, spec=spec)
        top_gate = _summarize_top_gate(resp.payload.failed_attempts)
        candidates.append((symbol, pct, start_date, end_date, top_gate))

    candidates.sort(key=lambda x: x[1], reverse=True)
    _write_markdown(out_path, candidates[:top_k], start_date, end_date, min_pct)
    print(f"done: {len(candidates)} candidate(s) found · "
         f"top-{min(top_k, len(candidates))} written to {out_path}")


def _load_spec(module_path: str):
    """import dag_spec module · load_params()(热加载 yaml)兜底 Params.default() · build_pattern。"""
    m = importlib.import_module(module_path)
    load_params_fn = getattr(m, 'load_params', None)
    params = load_params_fn() if callable(load_params_fn) else None
    if params is None:
        params = m.Params.default()
    spec = m.build_pattern(params)
    return spec, params


def _scan_symbol(spec, params, pkl_file: pathlib.Path):
    """读 pkl → reset_index 转正 0-based 位置(承生产惯例 slice_window 的输出形态,
    'date' 从 DatetimeIndex 落回普通列)→ 挂 gate collector → analyze → detach。

    返回 (AnalysisResult(已附 gate_failures), win)。collector 必须在 analyze() 之前挂
    才能收到 detect() 内部 emit 的 GateFailure(同 scan.py::_scan_ticker_multi 的既定做法)。
    """
    raw = pd.read_pickle(pkl_file)
    win = raw.reset_index()
    collector = attach_and_collect(spec)
    try:
        result = _dag_analyze(spec, win, params)
    finally:
        detach(spec)
    result = dataclasses.replace(result, gate_failures=collector.snapshot())
    return result, win


def _date_to_bar(win: pd.DataFrame, date_str: str) -> int:
    """date → 最近 bar 位置。pandas 3.x 已移除 Index.get_loc(method=) · 改用
    searchsorted 手写 nearest;越界(早于首根 / 晚于末根)钳制到边界。"""
    ts = pd.Timestamp(date_str)
    dates = win['date']
    n = len(dates)
    pos = int(dates.searchsorted(ts))
    if pos <= 0:
        return 0
    if pos >= n:
        return n - 1
    before, after = dates.iat[pos - 1], dates.iat[pos]
    return pos - 1 if (ts - before) <= (after - ts) else pos


def _compute_pct_change(win: pd.DataFrame, start_date: str, end_date: str):
    """(close[end] / close[start] - 1) * 100;越界日期钳制到边界 bar,close 为 0 时返回 None。"""
    if len(win) == 0 or 'date' not in win.columns:
        return None
    s = _date_to_bar(win, start_date)
    e = _date_to_bar(win, end_date)
    c0 = win['close'].iat[s]
    c1 = win['close'].iat[e]
    if c0 == 0:
        return None
    return (c1 / c0 - 1) * 100


def _summarize_top_gate(failed_attempts) -> str:
    """选窗口内出现次数最多的 gate_name · 拼一条含 measured/threshold 的样例摘要。"""
    if not failed_attempts:
        return "无 attempt 采集(可能 detector 未触发 on_gate,或漏检窗口内本就无判据触碰)"
    counts = Counter(gf.gate_name for gf in failed_attempts)
    top_name, top_count = counts.most_common(1)[0]
    sample = next(gf for gf in failed_attempts if gf.gate_name == top_name)
    return f"{top_name}(实测 {sample.measured.value} vs 阈 {sample.threshold} · 共 {top_count} 次)"


def _write_markdown(path: str, candidates, start: str, end: str, min_pct: float) -> None:
    with open(path, 'w') as f:
        f.write(f"# scan-top-miss · {start} -> {end}\n\n")
        f.write(f"筛选:涨幅 > {min_pct}% · matches 为空 · 按涨幅降序\n\n")
        f.write(f"## Top-{len(candidates)}\n\n")
        for i, (symbol, pct, s, e, gate) in enumerate(candidates, 1):
            f.write(f"{i}. **{symbol}** · {s} -> {e} · +{pct:.1f}%\n")
            f.write(f"   - {gate}\n\n")


if __name__ == '__main__':
    main()
