"""截断副本是屏障:读数据口只读带 SNAPSHOT.json 的目录、返回值最后一天不晚于 2025-12-31
(其他层都失效时硬上限照样挡住,最后一道闸是显式抛错不是 assert)、代码名过格式校验;
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


def test_hard_end_holds_even_when_other_layers_fail(cw_env, tmp_path, monkeypatch):
    """训练段末日那一层失效(配置写成 2026 年绕过 load_config、直接用 2026 年的终点调读数据口、
    把数据目录指到全量目录再伪造一份副本清单):结果仍不晚于 HARD_END。"""
    cfg, pkl_dir = cw_env
    make_stock(end="2026-03-31").to_pickle(pkl_dir / "AAA.pkl")
    late = {**cfg, "train_end": "2026-06-30"}
    assert read_bars(late, "AAA").index.max() == pd.Timestamp(HARD_END)
    assert read_bars(late, "AAA", until="2026-02-01").index.max() == pd.Timestamp(HARD_END)
    assert loader.load_bars(pkl_dir, "AAA", "2026-06-30").index.max() == pd.Timestamp(HARD_END)
    assert len(loader.trading_dates(late, "AAA")) and \
        loader.trading_dates(late, "AAA").max() == pd.Timestamp(HARD_END)
    full = tmp_path / "full"                              # 全量目录 + 伪造的副本清单
    full.mkdir()
    make_stock(end="2026-05-29", seed=5).to_pickle(full / "AAA.pkl")
    write_snapshot_manifest(full)
    assert loader.load_bars(full, "AAA", "2026-12-31").index.max() == pd.Timestamp(HARD_END)


def test_last_guard_is_an_explicit_raise(cw_env, monkeypatch):
    """截断那一步失效时,最后一道闸显式抛 PastHardEnd;读数据口里没有 assert(python -O 会去掉它)。"""
    import ast
    cfg, pkl_dir = cw_env
    make_stock(end="2026-03-31").to_pickle(pkl_dir / "AAA.pkl")
    monkeypatch.setattr(loader, "min", lambda *a: "2099-12-31", raising=False)   # 让截断失效
    with pytest.raises(loader.PastHardEnd, match="验证段"):
        loader.load_bars(pkl_dir, "AAA", "2026-06-30")
    tree = ast.parse((REPO_ROOT / "chart_workflow" / "loader.py").read_text())
    assert not [n for n in ast.walk(tree) if isinstance(n, ast.Assert)]


@pytest.mark.parametrize("bad", ["../pkls/AAA", "..", "A..A", "a/b", "a\\b", "", " AAA", ".AAA",
                                 "AAA\x00", "A" * 16, "/etc/passwd"])
def test_symbol_format_checked(cw_env, bad):
    cfg, pkl_dir = cw_env
    make_stock().to_pickle(pkl_dir / "AAA.pkl")
    with pytest.raises(ValueError, match="非法代码"):
        read_bars(cfg, bad)
    with pytest.raises(ValueError, match="非法代码"):
        loader.load_bars(pkl_dir, bad, HARD_END)


def test_real_symbols_pass_format_check():
    for sym in ("AAPL", "BRK.B", "BF-B", "A", "ZVZZT", "GOOG.WS1"):
        assert loader.check_symbol(sym) == sym


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


def test_snapshot_cli_refuses_existing_and_warns_about_replace(tmp_path, capsys):
    """命令行:目标目录已存在就拒绝覆盖(原样不动);生成成功时醒目提示「当正式副本后换副本要走显式命令」。"""
    src = _src(tmp_path)
    dst = tmp_path / "dst"
    snapshot_main(["--src", str(src), "--dst", str(dst)])
    out = capsys.readouterr().out
    assert "!!" in out and "snapshot-replace --reason" in out and "snapshot-register" in out
    before = {p.name: p.read_bytes() for p in dst.iterdir()}
    with pytest.raises(SystemExit):
        snapshot_main(["--src", str(src), "--dst", str(dst)])
    err = capsys.readouterr().err
    assert "已存在" in err and "不覆盖" in err and "snapshot-replace" in err
    assert {p.name: p.read_bytes() for p in dst.iterdir()} == before


def test_read_pickle_only_in_loader_and_snapshot():
    """读数据口唯一:chart_workflow 下只有 loader.py / snapshot.py 出现 read_pickle;后端看图工作流不直接读。"""
    hits = sorted(p.name for p in (REPO_ROOT / "chart_workflow").glob("*.py")
                  if "read_pickle" in p.read_text())
    assert hits == ["loader.py", "snapshot.py"]
    wf = (REPO_ROOT / "path2_web" / "workflow.py").read_text()
    assert "read_pickle" not in wf and "chart_workflow.loader" in wf
