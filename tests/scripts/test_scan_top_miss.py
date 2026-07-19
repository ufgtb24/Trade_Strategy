"""scripts/scan-top-miss.py 冒烟测试:subprocess 跑通 · 输出 markdown 榜结构正确。

用 tmp_path 造小合成 pkl fixture(非真实 datasets/pkls · --pkl-dir override 指向 tmp 目录),
避免 subprocess 扫全宇宙拖慢测试(brief 原版直扫 datasets/pkls/ · 本文件按实施 guidance
采用 adaptation (b):tmp fixture + --pkl-dir override)。
"""
import subprocess
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]


def _mk_flat_pkl(path: Path, n: int = 160) -> None:
    """构造一支全程横盘(无 pattern 命中)的合成 pkl,时间跨度覆盖测试窗口
    [2025-06-01, 2025-07-01](2025-01-01 起 160 个工作日,足够越过 7 月初)。"""
    dates = pd.date_range("2025-01-01", periods=n, freq="B", name="date")
    df = pd.DataFrame({
        "open": [10.0] * n,
        "high": [10.2] * n,
        "low": [9.8] * n,
        "close": [10.0] * n,
        "volume": [1000.0] * n,
    }, index=dates)
    df.to_pickle(path)


def test_scan_top_miss_runs_without_error(tmp_path):
    """脚本能跑通 · 输出 markdown 榜(--pkl-dir 指向 tmp fixture,避免扫全宇宙)。"""
    pkl_dir = tmp_path / "pkls"
    pkl_dir.mkdir()
    _mk_flat_pkl(pkl_dir / "AAA.pkl")
    _mk_flat_pkl(pkl_dir / "BBB.pkl")

    out_file = tmp_path / "top_miss.md"
    result = subprocess.run(
        [sys.executable, "scripts/scan-top-miss.py",
         "--start=2025-06-01", "--end=2025-07-01", "--min-pct=30", "--top-k=5",
         f"--pkl-dir={pkl_dir}", f"--out={out_file}"],
        capture_output=True, text=True, timeout=120, cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr
    assert out_file.exists()
    content = out_file.read_text()
    assert "## Top-5" in content or "# scan-top-miss" in content
