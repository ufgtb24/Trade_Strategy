"""研究用临时脚本:在随机抽的股票上批量跑 fold_measure.measure,结果逐行写 jsonl(只读训练段副本)。

用法: uv run python docs/research/2026-11-05_band-folding-design/repro/fold_broad.py <n> <seed> <out.jsonl>
"""
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fold_measure import measure, _cfg  # noqa: E402
from path2_web.config import view_dataset_dir  # noqa: E402

APPS = ["new_step", "bottom_burst", "bb_v1"]


def main():
    n, seed, out = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
    syms = sorted(p.stem for p in view_dataset_dir(_cfg).glob("*.pkl"))
    random.Random(seed).shuffle(syms)
    with open(out, "w") as f:
        for sym in syms[:n]:
            for app in APPS:
                try:
                    r = measure(app, sym)
                except Exception as ex:  # noqa: BLE001
                    print("ERR", app, sym, repr(ex), file=sys.stderr)
                    continue
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
            f.flush()


if __name__ == "__main__":
    main()
