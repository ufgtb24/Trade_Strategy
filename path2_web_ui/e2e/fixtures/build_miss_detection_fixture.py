"""E2E-only fixture builder · Task 24(path2 漏检调查工具 · Sprint 3 收尾)。

产出 outputs/path2_web/scans/<FIXED_SCAN_TS>.json(MultiScanResultFile schema,
path2_web/scan.py:run_scan_multi 同款结构),供 miss-detection-walkthrough.spec.ts
的 test.beforeAll 通过既有"打开历史"UI 流程加载。

为什么不能直接用 uv run python scripts/run_path2_web.py 起后再跑一次真实 /scan:
真实 /scan(path2_web/scan.py:_scan_ticker_multi)对每只股票有 any_match 闸——
所有 pattern 全无 match 的股票整支被丢弃、不进 results(scan.py:80-81)。这个闸对
生产扫描是对的(避免结果文件塞满零信号股),但恰恰挡住了本 e2e 要验证的核心场景:
DGNX 全局 0 match(它就是"该出 pattern 却没出"的漏检典范,design spec §1.1 原例),
正常 /scan 永远不会把它纳入 results,UI 的"打开历史→选股"路径就摸不到它。

本脚本复刻 _scan_ticker_multi 的单股分析链路(build_pattern→attach_and_collect→
analyze→detach→serialize_per_pattern_result),但去掉 any_match 闸——强制把
DGNX(entry A · BurstDetector chain_break)和 LIXT(entry B/C/D · 真实 anchor
mismatch + combine 淘汰 + 一对 4-subcheck 全清 pair)两支都写进 results,不代表
生产行为变化(scan.py 本身零改动),纯 e2e 测试夹具。

scan_ts 固定用远期哨兵 "29991231T235959"(> 任何真实时间戳),确保历史列表
(scan_ts 降序)里恒排第一行,测试点"打开历史"弹窗第一行即可命中,不必逐行找
文本、不受本机已有旧 scan 文件或墙钟影响。重复运行本脚本(幂等)会覆盖同名文件。
"""
from __future__ import annotations

import dataclasses
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

import pandas as pd  # noqa: E402

from path2.dag.engine import analyze as _dag_analyze  # noqa: E402
from path2_apps.bottom_breakout_burst import dag_spec as bbb  # noqa: E402
from path2_web.gate_collector import attach_and_collect, detach  # noqa: E402
from path2_web.scan import write_result_file_flat  # noqa: E402
from path2_web.serialize import serialize_per_pattern_result, serialize_pattern  # noqa: E402

FIXED_SCAN_TS = "29991231T235959"
PATTERN_ID = "bottom_burst"
LABEL_HORIZON = 20
# 两支 fixture 股覆盖不相交的 e2e 场景:
#   DGNX · 2025-01-22..2026-04-16 · 全局 0 match · burst chain_break(entry A 头号案例)
#   LIXT · 2021-04-19..2026-04-16 · 全局 0 match · burst_1054_1056/tb_1057 anchor 淘汰
#          链(entry C rejection_chain)+ burst_1054_1055→tb_1057 4-subcheck 全清
#          (entry D 正向)+ 反向点击触发 auto swap(entry D swap)
SYMBOLS = ["DGNX", "LIXT"]
# 宽到覆盖两支股全部历史即可(slice_window 按日期切,超界自动钳到实际可用范围;
# 不必精确对齐 eval_meta head_buffer——两支股最早一根前早已无数据可切)。
START_DATE = "2020-01-01"
END_DATE = "2026-04-20"


def _analyze_symbol(spec, params, symbol: str) -> dict:
    pkl_path = REPO / "datasets" / "pkls" / f"{symbol}.pkl"
    win = pd.read_pickle(pkl_path).reset_index()
    collector = attach_and_collect(spec)
    try:
        res = _dag_analyze(spec, win, params)
    finally:
        detach(spec)
    res = dataclasses.replace(res, gate_failures=collector.snapshot())
    return serialize_per_pattern_result(
        res, end_node="tb", label_horizon=LABEL_HORIZON,
        win=win, start_ts=pd.Timestamp(START_DATE), end_ts=pd.Timestamp(END_DATE),
    )


def main() -> None:
    params = bbb.load_params()
    spec = bbb.build_pattern(params)

    results = []
    for symbol in SYMBOLS:
        per_pattern_out = _analyze_symbol(spec, params, symbol)
        results.append({"symbol": symbol, "per_pattern": {PATTERN_ID: per_pattern_out}})
        n_events = len(per_pattern_out["analysis"]["events"])
        n_matches = per_pattern_out["summary"]["matches"]
        print(f"[fixture] {symbol}: {n_events} events, {n_matches} matches (force-included)")

    result = {
        "pattern_ids": [PATTERN_ID],
        "per_pattern": {
            PATTERN_ID: {"pattern_spec": serialize_pattern(spec), "end_node": "tb"},
        },
        "scan": {
            "scan_ts": FIXED_SCAN_TS,
            "start_date": START_DATE, "end_date": END_DATE,
            "workers": 1,
            "scanned": len(SYMBOLS), "hits": len(SYMBOLS), "errors": 0,
            "dataset_dir": str(REPO / "datasets" / "pkls"),
            "params": "default",
            "win_start": START_DATE, "win_end": END_DATE,
            "label_horizon": LABEL_HORIZON,
            "partial": False,
        },
        "results": results,
    }
    path = write_result_file_flat(result, FIXED_SCAN_TS, outputs_root=str(REPO / "outputs" / "path2_web"))
    print(f"[fixture] wrote {path}")


if __name__ == "__main__":
    main()
