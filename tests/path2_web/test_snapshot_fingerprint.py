"""训练段副本指纹(path2_web/snapshot_fingerprint.py)与补写 / 核对脚本(scripts/data/snapshot_fingerprint.py)。

钉住的要求:
- 同一个目录算两次指纹相同;改任一 pkl 的一个字节、增删或改名一个 pkl,指纹都变;
- 目录里非 pkl 的文件(清单本身、旧 SNAPSHOT.json、同步工具的隐藏文件)不进指纹;
- 没有清单时读指纹明确报错(ManifestMissing);
- 补写只新增清单一个文件,不动任何 pkl;已有清单不重写;
- 股票列表(按 *.pkl 列举)和 read_bars 都不把清单当成股票。
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from path2_web import data as data_mod
from path2_web import scan as scan_mod
from path2_web.snapshot_fingerprint import (
    MANIFEST_NAME, ManifestMissing, compute_manifest, read_fingerprint, read_manifest, write_manifest,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_script():
    """按路径加载入口脚本(scripts/data 不是包,不能 import)。"""
    path = REPO_ROOT / "scripts" / "data" / "snapshot_fingerprint.py"
    spec = importlib.util.spec_from_file_location("snapshot_fingerprint_script_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _write_pkl(ddir: Path, symbol: str, n: int = 30, base: float = 10.0) -> None:
    idx = pd.bdate_range("2025-06-02", periods=n, name="date")
    close = base + np.arange(n) * 0.01
    pd.DataFrame({"open": close, "high": close + 0.2, "low": close - 0.2, "close": close,
                  "volume": np.full(n, 1e6)}, index=idx).to_pickle(ddir / f"{symbol}.pkl")


@pytest.fixture
def snap(tmp_path) -> Path:
    d = tmp_path / "snap"
    d.mkdir()
    for k, sym in enumerate(["AAA", "BBB", "CCC"]):
        _write_pkl(d, sym, base=10.0 + k)
    return d


def _pkl_hashes(d: Path) -> dict:
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(d.glob("*.pkl"))}


def test_same_dir_twice_same_fingerprint(snap):
    a, b = compute_manifest(snap), compute_manifest(snap)
    assert a == b
    assert a["n_files"] == 3 and len(a["fingerprint"]) == 64


def test_manifest_bytes_deterministic(snap):
    """清单只由数据决定:写两次,字节完全相同(不记时间、机器)。"""
    write_manifest(snap)
    first = (snap / MANIFEST_NAME).read_bytes()
    write_manifest(snap)
    assert (snap / MANIFEST_NAME).read_bytes() == first


def test_one_byte_change_changes_fingerprint(snap):
    before = compute_manifest(snap)["fingerprint"]
    p = snap / "BBB.pkl"
    raw = bytearray(p.read_bytes())
    raw[-1] ^= 0x01
    p.write_bytes(bytes(raw))
    assert compute_manifest(snap)["fingerprint"] != before


def test_add_remove_rename_change_fingerprint(snap):
    fps = {compute_manifest(snap)["fingerprint"]}
    _write_pkl(snap, "DDD")
    fps.add(compute_manifest(snap)["fingerprint"])
    (snap / "AAA.pkl").unlink()
    fps.add(compute_manifest(snap)["fingerprint"])
    (snap / "CCC.pkl").rename(snap / "CCD.pkl")           # 内容不变,只改名
    fps.add(compute_manifest(snap)["fingerprint"])
    assert len(fps) == 4


def test_non_pkl_files_do_not_enter_fingerprint(snap):
    before = compute_manifest(snap)["fingerprint"]
    write_manifest(snap)
    (snap / "SNAPSHOT.json").write_text("{}")
    (snap / ".stignore").write_text("x")
    assert compute_manifest(snap)["fingerprint"] == before


def test_read_fingerprint_missing_manifest_is_explicit(snap):
    with pytest.raises(ManifestMissing, match=MANIFEST_NAME):
        read_fingerprint(snap)
    assert issubclass(ManifestMissing, FileNotFoundError)


def test_read_fingerprint_after_write(snap):
    written = write_manifest(snap)
    assert read_fingerprint(snap) == written["fingerprint"] == compute_manifest(snap)["fingerprint"]


def test_read_manifest_rejects_malformed(snap):
    (snap / MANIFEST_NAME).write_text(json.dumps({"fingerprint": "nothex"}))
    with pytest.raises(ValueError):
        read_fingerprint(snap)


def test_manifest_file_hashes_match_independent_sha256(snap):
    """清单里每个文件的哈希就是该文件内容的 sha256。"""
    assert write_manifest(snap)["files"] == _pkl_hashes(snap)


# ---------- 补写与核对(脚本) ----------

def test_backfill_writes_only_manifest_and_leaves_pkls(snap):
    script = _load_script()
    before_hashes = _pkl_hashes(snap)
    before_names = sorted(p.name for p in snap.iterdir())
    code, _ = script.backfill(snap)
    assert code == 0
    assert _pkl_hashes(snap) == before_hashes
    assert sorted(p.name for p in snap.iterdir()) == sorted(before_names + [MANIFEST_NAME])
    assert read_fingerprint(snap) == compute_manifest(snap)["fingerprint"]


def test_backfill_never_rewrites_existing_manifest(snap):
    script = _load_script()
    script.backfill(snap)
    recorded = (snap / MANIFEST_NAME).read_bytes()
    assert script.backfill(snap)[0] == 0                      # 一致:什么都不做
    _write_pkl(snap, "DDD")
    code, lines = script.backfill(snap)                        # 不一致:拒绝
    assert code == 1 and "拒绝" in lines[0]
    assert (snap / MANIFEST_NAME).read_bytes() == recorded


def test_check_exit_codes_and_diff(snap):
    script = _load_script()
    assert script.check(snap)[0] == 2                          # 没有清单
    write_manifest(snap)
    code, lines = script.check(snap)
    assert code == 0 and lines[0] == f"指纹 {read_fingerprint(snap)}"
    _write_pkl(snap, "DDD")
    (snap / "AAA.pkl").unlink()
    _write_pkl(snap, "BBB", base=99.0)
    code, lines = script.check(snap)
    text = "\n".join(lines)
    assert code == 1
    assert "added: DDD.pkl" in text and "removed: AAA.pkl" in text and "changed: BBB.pkl" in text


# ---------- 清单不被当成股票 ----------

def test_stock_listing_skips_manifest(snap):
    write_manifest(snap)
    (snap / "SNAPSHOT.json").write_text("{}")
    assert [p.stem for p in scan_mod._list_pkls(str(snap), None)] == ["AAA", "BBB", "CCC"]


@pytest.mark.parametrize("symbol", ["FINGERPRINT", MANIFEST_NAME])
def test_read_bars_does_not_read_manifest(snap, symbol):
    write_manifest(snap)
    with pytest.raises((FileNotFoundError, ValueError)):
        data_mod.read_bars(snap, symbol)
