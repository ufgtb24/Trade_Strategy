"""截断副本是屏障:读数据口只读带 SNAPSHOT.json 的目录、返回值最后一天不晚于 2025-12-31;
截断副本生成本身不出错、不改原数据;chart_workflow 里只有 loader / snapshot 碰 read_pickle;
训练段末日不得晚于 HARD_END。"""
import json
from pathlib import Path

import pandas as pd
import pytest

from chart_workflow import loader
from chart_workflow.config import REPO_ROOT, load_config
from chart_workflow.loader import HARD_END, NotASnapshot, read_bars
from chart_workflow.snapshot import SnapshotError, build_snapshot, main as snapshot_main
from tests.chart_workflow.conftest import make_stock, write_snapshot_manifest


def test_read_bars_requires_snapshot(tmp_path):
    d = tmp_path / "raw"
    d.mkdir()
    make_stock().to_pickle(d / "AAA.pkl")
    cfg = load_config(path=tmp_path / "none.yaml", override={"dataset_dir": str(d)})
    with pytest.raises(NotASnapshot) as ei:
        read_bars(cfg, "AAA")
    assert "python -m chart_workflow.snapshot" in str(ei.value)


def test_read_bars_never_past_hard_end(cw_env):
    cfg, pkl_dir = cw_env
    df = make_stock(end="2026-03-31")                # 故意放 2026 年的行
    assert df.index.max() > pd.Timestamp("2026-01-01")
    df.to_pickle(pkl_dir / "AAA.pkl")
    out = read_bars(cfg, "AAA")
    assert out.index.max() <= pd.Timestamp(HARD_END)
    assert out.index.max() == pd.Timestamp("2025-12-31")
    assert read_bars(cfg, "AAA", until="2025-07-14").index.max() == pd.Timestamp("2025-07-14")
    # until 晚于 HARD_END 也不放行
    assert read_bars(cfg, "AAA", until="2026-02-01").index.max() <= pd.Timestamp(HARD_END)


def test_manifest_with_late_cutoff_rejected(cw_env):
    cfg, pkl_dir = cw_env
    make_stock().to_pickle(pkl_dir / "AAA.pkl")
    write_snapshot_manifest(pkl_dir, cutoff="2026-03-31")
    with pytest.raises(NotASnapshot):
        read_bars(cfg, "AAA")


def test_train_end_after_hard_end_rejected(tmp_path):
    with pytest.raises(ValueError):
        load_config(path=tmp_path / "none.yaml", override={"train_end": "2026-01-02"})


def _src(tmp_path) -> Path:
    src = tmp_path / "src"
    src.mkdir()
    make_stock(end="2026-03-31", seed=1).to_pickle(src / "AAA.pkl")
    tz = make_stock(end="2026-02-27", seed=2)
    tz.index = tz.index.tz_localize("America/New_York")
    tz.to_pickle(src / "TZ.pkl")
    make_stock(start="2026-01-05", end="2026-03-31", seed=3).to_pickle(src / "NEW.pkl")   # 截完为空
    return src


def test_snapshot_build(tmp_path, capsys):
    src = _src(tmp_path)
    before = {p.name: p.read_bytes() for p in src.iterdir()}
    dst = tmp_path / "dst"
    man = build_snapshot(src, dst, verbose=False)
    assert man["n_files"] == 2 and man["n_skipped_empty"] == 1
    assert set(man["files"]) == {"AAA.pkl", "TZ.pkl"}
    assert man["max_date"] <= "2025-12-31" and man["cutoff"] == "2025-12-31"
    saved = json.loads((dst / "SNAPSHOT.json").read_text())
    assert saved == man and saved["src"] == str(src.resolve())
    for name, info in man["files"].items():
        df = pd.read_pickle(dst / name)
        assert df.index.max() <= pd.Timestamp("2025-12-31")
        assert len(df) == info["n_rows"] and info["last_date"] == df.index.max().strftime("%Y-%m-%d")
        assert list(df.columns) == ["open", "high", "low", "close", "volume"]
        assert df.index.tz is None
    assert not (dst / "NEW.pkl").exists()
    assert {p.name: p.read_bytes() for p in src.iterdir()} == before      # 原数据一个字节不变
    assert loader.check_snapshot(dst)["cutoff"] == "2025-12-31"
    assert not list(tmp_path.glob(".dst.*"))                              # 临时目录不留下


def test_snapshot_refuses_late_cutoff_and_existing_dst(tmp_path):
    src = _src(tmp_path)
    with pytest.raises(SnapshotError):
        build_snapshot(src, tmp_path / "x", cutoff="2026-01-05", verbose=False)
    assert not (tmp_path / "x").exists()
    dst = tmp_path / "dst"
    build_snapshot(src, dst, verbose=False)
    with pytest.raises(SnapshotError):
        build_snapshot(src, dst, verbose=False)
    man = build_snapshot(src, dst, cutoff="2025-06-30", rebuild=True, verbose=False)
    assert man["max_date"] <= "2025-06-30"
    assert pd.read_pickle(dst / "AAA.pkl").index.max() <= pd.Timestamp("2025-06-30")
    with pytest.raises(SystemExit):
        snapshot_main(["--src", str(src), "--dst", str(tmp_path / "y"), "--cutoff", "2026-01-05"])


def test_read_pickle_only_in_loader_and_snapshot():
    """读数据口唯一:chart_workflow 下只有 loader.py / snapshot.py 出现 read_pickle;后端看图工作流不直接读。"""
    hits = sorted(p.name for p in (REPO_ROOT / "chart_workflow").glob("*.py")
                  if "read_pickle" in p.read_text())
    assert hits == ["loader.py", "snapshot.py"]
    wf = (REPO_ROOT / "path2_web" / "workflow.py").read_text()
    assert "read_pickle" not in wf and "chart_workflow.loader" in wf
