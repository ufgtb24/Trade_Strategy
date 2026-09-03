"""致命反驳检验：「财报账龄」是不是「距 burst 起点的形态进展」的马甲？

lead 指派的唯一新任务。我在初稿 §6.3(1) 提出「效应随财报账龄单调衰减 = 准实验证据」，
并自己给它写了两条反驳。反驳 b（账龄 = 日历马甲）已由 probe_age_identification.py 收窄
（日历只解释账龄方差的 33%–45%）。本探针查**反驳 a**：

  财报日会触发 burst ⟹ 账龄小的行系统性更接近 burst 起点 ⟹ 账龄其实编码
  「形态进展到哪一步」。若 fr 依赖形态进展，账龄剖面会单调而与 PEAD 无关。

做法：复刻 path2_web/eval_runner.py::_scan_one 的窗口切法与 match 循环（同口径，
否则 buy_date 对不上），额外记录 burst / bo / tb 各 node 的 start_idx 与日期，
join 回 112 行，算「买点距 burst 起点的 bar 数」与财报账龄的关系。

⚠ 数据来源：主 worktree /home/yu/PycharmProjects/Trade_Strategy/datasets/pkls（**只读**，
本 worktree 的 datasets/pkls 不存在）。不拷贝、不软链、不写入。
⚠ app = path2_apps.bb_v1（112 行的真实来源，meta.module_path 确认），**不是 bottom_burst**。
"""
from __future__ import annotations

import importlib
import json
import subprocess
import sys
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path

import pandas as pd

REPO = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"],
                                    cwd="/home/yu/PycharmProjects/Trade_Strategy-news",
                                    text=True).strip())
sys.path.insert(0, str(REPO))

from path2.dag.engine import analyze as _dag_analyze          # noqa: E402
from path2.debug import set_current_symbol                     # noqa: E402
from path2.eval import _resolve_end_events                     # noqa: E402
from path2_web.data import slice_window                        # noqa: E402
from path2_web.scan import TRADING_TO_CALENDAR_RATIO           # noqa: E402

PKL_DIR = Path("/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls")
OUT = Path(__file__).resolve().parent
MODULE = "path2_apps.bb_v1"
START, END = "2025-01-01", "2026-01-01"
HORIZONS = (40,)
HEAD_BUF = 63
END_NODE = "tb"


def scan_symbol(symbol: str) -> list[dict]:
    set_current_symbol(symbol)
    try:
        df = pd.read_pickle(PKL_DIR / f"{symbol}.pkl")
        mod = importlib.import_module(MODULE)
        params = mod.load_params() if hasattr(mod, "load_params") else mod.Params.default()
        start_ts, end_ts = pd.to_datetime(START), pd.to_datetime(END)
        buf_start = start_ts - pd.Timedelta(days=round(HEAD_BUF * TRADING_TO_CALENDAR_RATIO))
        buf_end = end_ts + pd.Timedelta(days=round(max(HORIZONS) * TRADING_TO_CALENDAR_RATIO))
        win = slice_window(df, buf_start, buf_end)
        if len(win) == 0:
            return []
        spec = mod.build_pattern(params)
        res = _dag_analyze(spec, win, params)
        out = []
        for m in res.matches:
            events = _resolve_end_events(m, END_NODE)
            if not any(start_ts <= win["date"].iat[ev.start_idx] <= end_ts for ev in events):
                continue
            leaf = m.node_index[END_NODE.split(".")[0]]
            rec = {"symbol": symbol,
                   "buy_date": str(win["date"].iat[leaf.start_idx])[:10],
                   "leaf_event_id": leaf.instance_id,
                   "tb_start_idx": leaf.start_idx}
            for node in ("burst", "bo"):
                ev = m.node_index.get(node)
                if ev is None:
                    continue
                rec[f"{node}_start_idx"] = ev.start_idx
                rec[f"{node}_end_idx"] = ev.end_idx
                rec[f"{node}_start_date"] = str(win["date"].iat[ev.start_idx])[:10]
                rec[f"{node}_end_date"] = str(win["date"].iat[ev.end_idx])[:10]
            b = m.node_index.get("burst")
            if b is not None:
                # first_drought = 簇首 bo 距上一根 bo 的 bar 数（bb_v1 要求 >= 40）
                rec["first_drought"] = getattr(b, "first_drought", None)
                if rec["first_drought"]:
                    di = rec["burst_start_idx"] - rec["first_drought"]
                    if 0 <= di < len(win):
                        rec["drought_start_date"] = str(win["date"].iat[di])[:10]
                        rec["bars_since_drought_start"] = leaf.start_idx - di
            # 买点距 burst 起点/终点的 bar 数（同一 win 内，索引差 = 交易日数）
            if "burst_start_idx" in rec:
                rec["bars_since_burst_start"] = leaf.start_idx - rec["burst_start_idx"]
                rec["bars_since_burst_end"] = leaf.start_idx - rec["burst_end_idx"]
            out.append(rec)
        return out
    except Exception as e:                                     # noqa: BLE001
        return [{"symbol": symbol, "error": f"{type(e).__name__}: {e}"}]
    finally:
        set_current_symbol(None)


def main() -> None:
    scores = json.loads((REPO / "docs/research/2026-08-16_news-sentiment-path2-integration"
                                "/repro/full_scores_20260816-193559.json").read_text())
    symbols = sorted({r["symbol"] for r in scores})
    all_rows, errs = [], []
    for i, s in enumerate(symbols, 1):
        if not (PKL_DIR / f"{s}.pkl").exists():
            errs.append((s, "no_pkl")); continue
        rows = scan_symbol(s)
        for r in rows:
            if "error" in r:
                errs.append((s, r["error"]))
            else:
                all_rows.append(r)
        print(f"[{i:3d}/{len(symbols)}] {s:8s} matches={len(rows)}", flush=True)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    p = OUT / f"burst_start_{stamp}.json"
    p.write_text(json.dumps({"module": MODULE, "errors": errs, "rows": all_rows},
                            ensure_ascii=False, indent=1))
    print(f"\n匹配行 {len(all_rows)}，错误 {len(errs)} -> {p}")


if __name__ == "__main__":
    main()
