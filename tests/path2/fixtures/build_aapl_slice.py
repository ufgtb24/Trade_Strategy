"""Provenance for aapl_vol_slice.csv (dogfood 固定 fixture).

该 CSV 已随仓库提交,测试与图脚本直接读它,正常无需重跑本脚本。
仅当需要复核 fixture 来源时,在拥有 datasets/pkls/AAPL.pkl 的环境运行:

    uv run python tests/path2/fixtures/build_aapl_slice.py

切片定义:AAPL.pkl.iloc[759:1079] —— 320 行,含一段真实的密集放量区。
"""
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
SRC = REPO_ROOT / "datasets" / "pkls" / "AAPL.pkl"
OUT = Path(__file__).resolve().parent / "aapl_vol_slice.csv"


def main() -> None:
    df = pd.read_pickle(SRC).iloc[759:1079][
        ["open", "high", "low", "close", "volume"]
    ].copy()
    df.index.name = "date"
    df.to_csv(OUT, float_format="%.6g")
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes, {len(df)} rows)")


if __name__ == "__main__":
    main()
