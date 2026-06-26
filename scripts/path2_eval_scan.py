"""参数化扫描评估入口(authoring-path2-app skill 的评估器,final_report §8.9)。

三 mode 共享 path2_web/eval_runner.py 骨架:
  eval        全宇宙命中 + 多 horizon forward_return 统计(判据 2)
  regress     与改前 baseline(一次 eval 的结果 JSON)按 (symbol, buy_date) 对拍
  healthcheck 新建/改动 detector 后数量级体检 + 目标票命中确认

参数全部在 main() 起始声明(无 argparse,CLAUDE.md 入口规范)。
skill/subagent 程序化调用直接走库函数,不必改本文件:
  uv run python -c "from path2_web.eval_runner import run_eval; import json; \
out = run_eval(module_path='path2_apps.bottom_breakout_burst', \
start='2024-01-01', end='2025-01-01'); \
print(json.dumps({'meta': out['meta'], 'per_horizon': out['per_horizon']}, ensure_ascii=False))"
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from path2_web.eval_runner import run_eval, run_healthcheck, run_regress


def main() -> None:
    # ===== 参数(在此处直接改) =====
    MODE: str = "eval"                        # eval | regress | healthcheck
    MODULE_PATH: str = "path2_apps.bottom_breakout_burst"   # app 包路径(非 dag_spec 子模块)
    START_DATE: str = "2024-01-01"
    END_DATE: str = "2025-01-01"
    HORIZONS: tuple[int, ...] = (5, 10, 20)
    PARAM_OVERRIDES: Optional[dict] = None   # 例:{"THR_DROUGHT": 20};None=Params.default()
    BASELINE_PATH: Optional[str] = None      # eval 模式不读
    TARGET_TICKER: Optional[str] = None      # mode=healthcheck 选填:目标票
    MIN_TICKERS, MAX_TICKERS = 1, 500        # healthcheck 数量级区间
    DATA_DIR: str = str(REPO / "datasets" / "pkls")
    MAX_WORKERS: int = 26
    TICKER_REGEX: Optional[str] = None       # 例 r"^AAP.*" 仅扫子集
    OUT_PATH: Optional[str] = "outputs/path2_eval/bbb_baseline.json"
    # ================================
    common = dict(data_dir=DATA_DIR, workers=MAX_WORKERS,
                  ticker_regex=TICKER_REGEX, out_path=OUT_PATH)
    if MODE == "eval":
        out = run_eval(module_path=MODULE_PATH, start=START_DATE, end=END_DATE,
                       horizons=HORIZONS, param_overrides=PARAM_OVERRIDES, **common)
        m = out["meta"]
        print(f"tickers_hit={m['tickers_hit']} buy_windows={m['buy_windows']} "
              f"errors={m['errors']} elapsed={m['elapsed_s']}s")
        for n, s in out["per_horizon"].items():
            print(f"ret_{n}: count={s['count']} mean={s['mean']} "
                  f"median={s['median']} win_rate={s['win_rate']}")
    elif MODE == "regress":
        out = run_regress(baseline_path=BASELINE_PATH,
                          param_overrides=PARAM_OVERRIDES, **common)
        print(f"added={len(out['added'])} removed={len(out['removed'])} "
              f"unchanged={out['unchanged_count']}")
    elif MODE == "healthcheck":
        out = run_healthcheck(module_path=MODULE_PATH, start=START_DATE,
                              end=END_DATE, target_ticker=TARGET_TICKER,
                              min_tickers=MIN_TICKERS, max_tickers=MAX_TICKERS,
                              param_overrides=PARAM_OVERRIDES, **common)
        print(f"tickers_hit={out['universe_hit_tickers']} "
              f"magnitude_ok={out['magnitude_ok']} "
              f"target_matches={out['target_matches']}")
    else:
        raise ValueError(f"unknown MODE {MODE!r}")
    print(f"json -> {out['meta']['out_path']}")


if __name__ == "__main__":
    main()
