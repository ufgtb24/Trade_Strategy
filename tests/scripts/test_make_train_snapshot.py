"""scripts/data/make_train_snapshot.py 生成副本时顺带写指纹清单:清单与副本内容对得上,且不被当成股票。"""
import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from path2_web.snapshot_fingerprint import MANIFEST_NAME, compute_manifest, read_fingerprint

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_module():
    """按路径加载入口脚本(scripts/data 不是包,不能 import)。"""
    path = REPO_ROOT / "scripts" / "data" / "make_train_snapshot.py"
    spec = importlib.util.spec_from_file_location("make_train_snapshot_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _write_pkl(ddir: Path, symbol: str) -> None:
    idx = pd.bdate_range("2025-12-01", "2026-01-30", name="date")
    close = 10 + np.arange(len(idx)) * 0.01
    pd.DataFrame({"open": close, "high": close, "low": close, "close": close,
                  "volume": np.full(len(idx), 1e6)}, index=idx).to_pickle(ddir / f"{symbol}.pkl")


def test_build_writes_matching_manifest(tmp_path):
    mod = _load_module()
    src, dst = tmp_path / "src", tmp_path / "dst"
    src.mkdir()
    for sym in ("AAA", "BBB"):
        _write_pkl(src, sym)
    out = mod.build(src, dst, "2025-12-31", rebuild=False)
    assert (dst / MANIFEST_NAME).is_file()
    assert out["fingerprint"] == read_fingerprint(dst) == compute_manifest(dst)["fingerprint"]
    assert sorted(p.name for p in dst.glob("*.pkl")) == ["AAA.pkl", "BBB.pkl"]   # 清单不是 pkl
    assert not any(p.name.startswith(".") for p in dst.iterdir())                # 没留临时文件
