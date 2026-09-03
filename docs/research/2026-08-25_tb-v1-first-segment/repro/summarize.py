"""汇总对比扫描(scan_cmp.py 产物)为一张表:每个 scan 一行。

列:name / window / hits / matches / fr_median / fr_q25 / fr_q75 / FP=up/(up+down+both) /
n_fp / random_ratio / random_n。只报数字,不下结论(评估纪律:带基线对照、小样本计数标注)。

用法:PYTHONPATH=<repo> python docs/research/2026-08-25_tb-v1-first-segment/repro/summarize.py
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

REPO = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
SCANS = REPO / "outputs/path2_web/scans"


def main() -> None:
    # ===== 参数(在此处直接改) =====
    NAMES = [
        "cmp-old-v1-train", "cmp-old-v1-oos",
        "cmp-bo_only-train", "cmp-bo_only-oos",
        # 改后档位(Task 6 补):
        "cmp-new-v1-span12-train", "cmp-new-v1-span12-oos",
        "cmp-new-v1-span20-train", "cmp-new-v1-span20-oos",
        "cmp-new-v1-span60-train", "cmp-new-v1-span60-oos",
    ]
    OUT_MD = REPO / "docs/research/2026-08-25_tb-v1-first-segment/cmp_table.md"
    # =====================================

    rows = []
    for name in NAMES:
        path = SCANS / f"{name}.json"
        if not path.exists():
            rows.append(f"| {name} | (缺文件) | | | | | | | | |")
            continue
        d = json.loads(path.read_text())
        pid = d["pattern_ids"][0]
        pp = d["per_pattern"][pid]
        st, fp = pp["stats"], pp["first_passage_stats"]
        s = d["scan"]
        n_fp = fp["up"] + fp["down"] + fp["both"]
        ratio = fp["up"] / n_fp if n_fp else float("nan")
        rows.append(
            f"| {name} | {s['start_date']}..{s['end_date']} | {s['hits']} | {st['count']} | "
            f"{st['median']:.4f} | {st['q25']:.4f} | {st['q75']:.4f} | {ratio:.4f} | {n_fp} | "
            f"{fp['random_ratio']:.4f} | {fp['random_n']} |")
    header = ("| scan | window | hits | matches | fr_med | fr_q25 | fr_q75 | FP | n_fp | "
              "random_FP | random_n |\n|---|---|---|---|---|---|---|---|---|---|---|")
    text = header + "\n" + "\n".join(rows) + "\n"
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("# 对比扫描汇总(head_buffer=250 · label 40 · first_passage k=5)\n\n" + text)
    print(text)
    print(f"→ {OUT_MD}")


if __name__ == "__main__":
    main()
