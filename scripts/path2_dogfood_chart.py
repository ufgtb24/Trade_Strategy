"""生成 dogfood 验证报告内嵌图:AAPL 收盘价 + 成交量,叠加 VolSpike / VolCluster。

一次性脚本(报告可复现),复用 tests/path2 的 dogfood 检测器与已提交 fixture。

    uv run python scripts/path2_dogfood_chart.py

输出:docs/research/path2_dogfood_chart.png
"""
import sys
from pathlib import Path

# 独立脚本(非 pytest)运行时 repo root 不在 sys.path,需手动加入,
# 否则 `from tests.path2...` 会 ModuleNotFoundError。
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from path2 import run
from tests.path2.dogfood_detectors import VolClusterDetector, VolSpikeDetector

FIXTURE = REPO / "tests" / "path2" / "fixtures" / "aapl_vol_slice.csv"
OUT = REPO / "docs" / "research" / "path2_dogfood_chart.png"


def main() -> None:
    df = pd.read_csv(FIXTURE, index_col="date", parse_dates=True)
    spikes = list(run(VolSpikeDetector(), df))
    clusters = list(run(VolClusterDetector(), iter(spikes)))

    x = range(len(df))
    fig, (ax_p, ax_v) = plt.subplots(
        2, 1, figsize=(14, 7), sharex=True, height_ratios=[2, 1]
    )

    ax_p.plot(x, df["close"].to_numpy(), color="black", lw=0.9, label="close")
    for c in clusters:
        ax_p.axvspan(c.start_idx, c.end_idx, color="orange", alpha=0.35)
        ax_p.text(
            c.start_idx, df["close"].to_numpy().max(), c.event_id,
            fontsize=8, rotation=90, va="top",
        )
    ax_p.set_title(
        "Path 2 dogfood — AAPL slice: VolSpike (L1) + VolCluster (L2)"
    )
    ax_p.legend(loc="upper left")

    vol = df["volume"].to_numpy()
    ax_v.bar(x, vol, color="steelblue", width=1.0)
    sp_idx = [s.start_idx for s in spikes]
    ax_v.scatter(
        sp_idx, [vol[i] for i in sp_idx], color="red", s=20,
        zorder=3, label="VolSpike",
    )
    ax_v.set_ylabel("volume")
    ax_v.legend(loc="upper left")

    fig.tight_layout()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=110)
    print(f"wrote {OUT} | spikes={len(spikes)} clusters={len(clusters)}")


if __name__ == "__main__":
    main()
