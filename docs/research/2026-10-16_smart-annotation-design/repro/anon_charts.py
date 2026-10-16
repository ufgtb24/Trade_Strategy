"""临时实验:把 2025 年大涨段画成匿名图(无代码、无日期、价格以首根收盘=100 重定基、量按窗内均量归一),
供「没有上下文的模型能否认出这是哪只股票 / 哪段时间」的小测试用。

只读 2025-01-01..2025-12-31 的数据;读入后立刻截断,不打印、不保存任何 2026 年及以后的数据。
输出 PNG 到 scratchpad(argv[1]),文件名只用编号,不含代码。
"""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

REPO = Path(__file__).resolve().parents[4]
LO, HI = "2025-01-01", "2025-12-31"

# (编号, item_id, 是否截到决策日)
CASES = [
    ("c1", "OPEN@2025-06-20", False),
    ("c2", "ABVX@2025-07-11", False),
    ("c3", "QMMM@2025-08-05", False),
    ("c4", "OPEN@2025-06-20", True),
]


def load(symbol: str) -> pd.DataFrame:
    df = pd.read_pickle(REPO / "datasets" / "pkls" / f"{symbol}.pkl")
    return df.loc[LO:HI]


def render(df: pd.DataFrame, path: Path) -> None:
    base = df["close"].iloc[0]
    o, h, l, c = (df[k] / base * 100 for k in ("open", "high", "low", "close"))
    v = df["volume"] / df["volume"].mean()
    x = range(len(df))
    fig, (ax, axv) = plt.subplots(2, 1, figsize=(10, 6), sharex=True,
                                  gridspec_kw={"height_ratios": [3, 1]})
    for i, oo, hh, ll, cc in zip(x, o, h, l, c):
        col = "black" if cc >= oo else "grey"
        ax.vlines(i, ll, hh, color=col, linewidth=0.8)
        ax.add_patch(plt.Rectangle((i - 0.3, min(oo, cc)), 0.6, max(abs(cc - oo), 1e-6),
                                   color=col, fill=(cc < oo)))
    axv.bar(list(x), v, color="grey", width=0.7)
    ax.set_ylabel("price (first close = 100)")
    axv.set_ylabel("volume / window mean")
    axv.set_xlabel("trading day #")
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def main() -> None:
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    items = {i["item_id"]: i for i in json.loads(
        (REPO / "outputs/chart_workflow/lists/r002-bigmoves-2025.json").read_text())["items"]}
    for cid, item_id, trunc in CASES:
        it = items[item_id]
        df = load(it["symbol"]).loc[it["view_start"]:(it["t"] if trunc else it["view_end"])]
        assert df.index.max() <= pd.Timestamp(HI)
        render(df, out / f"{cid}.png")
        print(cid, len(df), "bars")


if __name__ == "__main__":
    main()
