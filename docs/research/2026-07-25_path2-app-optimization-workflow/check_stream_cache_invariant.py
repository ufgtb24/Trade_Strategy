"""检验「detect 一次 / solve 多次」缓存的健全性不变量。

本次研究（2026-07-25）提出的整个优化工作流，地基是下面这条不变量：

    改 where / edge 参数  ⟹  run_streams 产出的事件流【逐字不变】，只需重跑 solve
    改 detector 参数      ⟹  事件流会变，必须重扫

它成立的原因是 `path2/dag/engine.py::run_streams` 的物化键是
`(id(node.detector), node.consumes_stream)` —— 缓存粒度是 detector 对象、不是 spec。
所以边集合 / where 子句 / 节点子集都不影响事件流。

⚠ 这条不变量【可能被静默破坏】：只要有人把一个阈值从 NodeSpec.where 挪进 detector
构造参数（或反之），缓存就会开始给出错误结果，而且不报错。所以这个脚本值得在
detector 代码或 params 结构变动后重跑一次。

用法：
    uv run python docs/research/2026-07-25_path2-app-optimization-workflow/check_stream_cache_invariant.py [票数]

预期输出：
    改 where 三阈值后 streams 全等的股数: N/N        ← 必须相等，否则缓存不健全
    改 detector 内部(gap_max)后全等的股数: 远小于 N  ← 必须显著小于 N，否则对照失效
"""
from __future__ import annotations

import glob
import pathlib
import sys
from dataclasses import replace

REPO = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

import pandas as pd  # noqa: E402

from path2.dag.engine import run_streams  # noqa: E402
from path2.dag._solve import compile_plan, solve  # noqa: E402
from path2_apps.bottom_breakout_burst import load_params  # noqa: E402
from path2_apps.bottom_breakout_burst.dag_spec import build_pattern  # noqa: E402
from path2_web.data import slice_window  # noqa: E402

START, END = "2025-01-01", "2026-01-01"


def fingerprint(streams) -> tuple:
    """事件流的逐字指纹：每个 node 的 event_id 序列。"""
    return tuple(sorted((nid, tuple(e.event_id for e in evs)) for nid, evs in streams.items()))


def main() -> None:
    n_tickers = int(sys.argv[1]) if len(sys.argv) > 1 else 120

    p_base = load_params()
    # A: 现状；B: 只动 where 三阈值（应全等）；C: 动 detector 内部（应大量不等）
    p_where = replace(p_base, burst=replace(p_base.burst, first_drought_min=5,
                                            distinct_pk_min=1, vol_spike_min=1.0))
    p_det = replace(p_base, burst=replace(p_base.burst, gap_max=p_base.burst.gap_max + 7))

    pkls = sorted(glob.glob(str(REPO / "datasets/pkls/*.pkl")))[:n_tickers]
    n = eq_where = eq_det = 0
    matches = {"A": 0, "B": 0}

    for pk in pkls:
        try:
            df = slice_window(pd.read_pickle(pk), START, END)
            if df is None or len(df) < 60:
                continue
            s_a = run_streams(build_pattern(p_base), df, p_base)
            s_b = run_streams(build_pattern(p_where), df, p_where)
            s_c = run_streams(build_pattern(p_det), df, p_det)
        except Exception:
            continue
        n += 1
        eq_where += fingerprint(s_a) == fingerprint(s_b)
        eq_det += fingerprint(s_a) == fingerprint(s_c)
        matches["A"] += len(solve(compile_plan(build_pattern(p_base)), s_a))
        matches["B"] += len(solve(compile_plan(build_pattern(p_where)), s_b))

    print(f"可用票数 n = {n}")
    print(f"改 where 三阈值后 streams 全等的股数 : {eq_where}/{n}"
          f"   {'✅ 缓存健全' if eq_where == n else '❌ 不变量已被破坏 —— 缓存不可用'}")
    print(f"改 detector(gap_max) 后全等的股数    : {eq_det}/{n}"
          f"   {'✅ 对照有效' if eq_det < n else '❌ 对照失效(该参数无影响?)'}")
    print(f"solve 结果 matches: 现状={matches['A']}  松 where={matches['B']}"
          f"   {'✅ where 确在 solve 时生效' if matches['A'] != matches['B'] else '❌ where 未生效'}")


if __name__ == "__main__":
    main()
