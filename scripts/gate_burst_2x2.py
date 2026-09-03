"""tb v2 实施 gate:burst 2×2 析因 {span,chain}×{greedy,all_ends} 全集扫描。

四格变体注入 = 替换 dag_spec.BurstDetector 模块属性(进程池 fork 前打补丁,Linux fork 继承)。
每格输出 outputs/gate_<cell>.txt(命中 ticker);终端报 hit 数 / burst 体积 / A/B/AB 析因。
参数在 main() 起始声明(无 argparse)。bo/tb 固定为 v2 新世界,只变 burst 物化。
"""
from __future__ import annotations

import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from path2.atoms.breakout import BurstDetector
import path2_apps.bottom_burst.dag_spec as dag_spec_mod
from path2_apps.bottom_burst.dag_spec import analyze
from path2_apps.bottom_burst.params import Params
from path2_web.data import slice_window

OLD_MAX_SPAN = 20      # 旧 span 口径(退役的 burst_max_span 默认)


class _SpanGreedy(BurstDetector):
    """(1) 旧现状:span 总跨度窗 + 贪心极大段(i=j 不回头)。"""
    def detect(self, bos, df):
        seq = sorted(bos, key=lambda e: (e.start_idx, e.end_idx))
        out, i, n = [], 0, len(seq)
        while i < n:
            first = seq[i]
            j = i + 1
            while j < n and (seq[j].start_idx - first.start_idx) <= OLD_MAX_SPAN:
                j += 1
            seg = seq[i:j]
            if len(seg) >= self.min_bos:
                out.append(self._make_burst(seg))
            i = j
        out.sort(key=lambda e: (e.end_idx, e.start_idx))
        yield from out


class _ChainGreedy(BurstDetector):
    """(2) chain 聚类 + 互斥极大簇(每簇一实例,归因辅助)。"""
    def detect(self, bos, df):
        seq = sorted(bos, key=lambda e: (e.start_idx, e.end_idx))
        out, head, n = [], 0, len(seq)
        for k in range(1, n + 1):
            if k == n or seq[k].start_idx - seq[k - 1].start_idx > self.gap_max:
                seg = seq[head:k]
                if len(seg) >= self.min_bos:
                    out.append(self._make_burst(seg))
                head = k
        out.sort(key=lambda e: (e.end_idx, e.start_idx))
        yield from out


class _SpanAllEnds(BurstDetector):
    """(3) 每 end 回望 span 固定窗(用户批判的形态,归因辅助)。"""
    def detect(self, bos, df):
        seq = sorted(bos, key=lambda e: (e.start_idx, e.end_idx))
        out = []
        for k, b in enumerate(seq):
            i = k
            while i > 0 and b.start_idx - seq[i - 1].start_idx <= OLD_MAX_SPAN:
                i -= 1
            seg = seq[i:k + 1]
            if len(seg) >= self.min_bos:
                out.append(self._make_burst(seg))
        out.sort(key=lambda e: (e.end_idx, e.start_idx))
        yield from out


CELLS = {
    "span_greedy": _SpanGreedy,      # (1) burst 轴基线
    "chain_greedy": _ChainGreedy,    # (2)
    "span_allends": _SpanAllEnds,    # (3)
    "chain_allends": BurstDetector,  # (4) 目标=生产实现
}


def _check(pkl_path: Path, params: Params, start: str, end: str):
    """worker:返回 (ticker, hit, n_burst_events, err)。analyze 一遍同时取 matches 与体积。"""
    ticker = pkl_path.stem
    try:
        df = pd.read_pickle(pkl_path)
        win = slice_window(df, start, end)
        if len(win) == 0:
            return (ticker, False, 0, None)
        res = analyze(win, params)
        n_burst = sum(1 for e in res.events if e.node_id == "burst")
        return (ticker, len(res.matches) > 0, n_burst, None)
    except Exception as e:
        return (ticker, False, 0, f"{type(e).__name__}: {e}")


def main() -> None:
    # ===== 参数 =====
    DATA_DIR = REPO / "datasets" / "pkls"
    OUT_DIR = REPO / "outputs"
    START_DATE, END_DATE = "2024-01-01", "2025-01-01"   # 与 path2_filter 同窗口
    MAX_WORKERS = 26
    PARAMS = Params.default()
    # ================

    pkls = sorted(DATA_DIR.glob("*.pkl"))
    OUT_DIR.mkdir(exist_ok=True)
    hits: dict[str, set] = {}
    vols: dict[str, int] = {}

    for cell, variant in CELLS.items():
        dag_spec_mod.BurstDetector = variant          # ★ 进程池 fork 前打补丁
        t0 = time.perf_counter()
        matched, total_burst, errors = set(), 0, 0
        with ProcessPoolExecutor(max_workers=MAX_WORKERS) as ex:
            futs = [ex.submit(_check, p, PARAMS, START_DATE, END_DATE) for p in pkls]
            for f in as_completed(futs):
                ticker, hit, n_burst, err = f.result()
                if err:
                    errors += 1
                    continue
                total_burst += n_burst
                if hit:
                    matched.add(ticker)
        hits[cell] = matched
        vols[cell] = total_burst
        (OUT_DIR / f"gate_{cell}.txt").write_text("\n".join(sorted(matched)) + "\n")
        print(f"[{cell}] hit={len(matched)} burst_events={total_burst} "
              f"errors={errors} elapsed={time.perf_counter() - t0:.0f}s")

    h1, h2 = len(hits["span_greedy"]), len(hits["chain_greedy"])
    h3, h4 = len(hits["span_allends"]), len(hits["chain_allends"])
    print(f"\n聚类主效应 B=(2)-(1)={h2 - h1}  枚举族主效应 A=(4)-(2)={h4 - h2}  "
          f"交互 AB=(4)-(3)-(2)+(1)={h4 - h3 - h2 + h1}")
    print(f"new=(4)-(1): {sorted(hits['chain_allends'] - hits['span_greedy'])}")
    print(f"LOST=(1)-(4): {sorted(hits['span_greedy'] - hits['chain_allends'])}")
    print(f"体积(burst_events/cell): { {c: vols[c] for c in CELLS} }")


if __name__ == "__main__":
    main()
