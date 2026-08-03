"""扫描 + 排序 —— 复制到 scratchpad,改 CONFIGS 与 WINDOWS。

三种用法(对应 SKILL 流程 3/4/6):
- 单因子消融:CONFIGS = 每个旋钮各动一次
- 坐标扫描:  CONFIGS = 以当前最优为中心、每维几个候选值
- 多窗口复核:WINDOWS 填 ≥2 个不相交时间窗,按「最差窗 score」排序

排序一律用区间无关口径(eval_skeleton 的 median 列),窗均值只作刷分对照。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from eval_skeleton import baseline_median, run_config, fmt  # noqa: E402

# ===== CONFIG(只改这里) =====
WINDOWS = {                                  # ≥2 个不相交窗;要关必须显式说明理由
    "2024": ("2024-01-01", "2025-01-01"),
    "2025": ("2025-01-01", "2026-01-01"),
}
CONFIGS = [                                  # (tag, overrides)
    ("现状", {}),
    # ("K0", {"tb": {"stop_confirm_bars": 0}}),
]
OUT = Path("sweep_result.json")
# ============================


def main():
    bases = {w: baseline_median(*rng) for w, rng in WINDOWS.items()}
    for w, b in bases.items():
        print(f"对照基线 {w} = {b:.4f}")

    out = []
    for tag, ov in CONFIGS:
        row = {"tag": tag, "overrides": ov, "windows": {}}
        for w, (st, en) in WINDOWS.items():
            det, s = run_config(ov, st, en, tag=f"{tag}@{w}", baseline_median=bases[w])
            row["windows"][w] = s
            det.to_csv(f"detail_{tag}_{w}.csv".replace("/", "_"), index=False)
            print("  " + fmt(s), flush=True)
        scored = [s for s in row["windows"].values() if s.get("score") is not None]
        row["worst_score"] = min(s["score"] for s in scored) if scored else None
        row["all_gate"] = all(s.get("gate") for s in row["windows"].values())
        out.append(row)

    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"\n== 按最差窗 score 排序(全窗过硬门的) ==")
    ranked = [r for r in out if r["all_gate"] and r["worst_score"] is not None]
    for r in sorted(ranked, key=lambda r: -r["worst_score"]):
        ns = " ".join(f"{w}:n={s['n']}" for w, s in r["windows"].items())
        print(f"{r['tag']:<20s} worst={r['worst_score']:.4f}  {ns}")
    dropped = [r["tag"] for r in out if r not in ranked]
    if dropped:
        print(f"未过硬门(n≥N0 且 q25≥0),已排除:{dropped}")


if __name__ == "__main__":
    main()
