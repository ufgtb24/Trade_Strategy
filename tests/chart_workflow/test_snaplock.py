"""副本登记:指纹按文件内容算(改修改时间不变、改内容 / 多文件就变、原样拷贝不变);第一次登记与换副本
都要显式命令(换副本要写原因并留记录);本机副本与登记的不一致时读数据、记账都停下并写出两边指纹;
没登记就停(主目录与临时状态根一样);state show 显示两边指纹;指纹只算 pkl 与清单;进程运行中原地改了
副本,读它或核对整份副本时就发现(不用重启)。"""
import json
import os
import shutil
import subprocess

import pytest

from chart_workflow import snaplock, state, views
from chart_workflow.loader import read_bars
from tests.chart_workflow.conftest import make_stock

pytestmark = pytest.mark.real_snaplock


def _fresh():
    """清掉进程内记住的指纹与核对结果(真实使用里换了副本要重启进程)。"""
    snaplock._FP.clear()
    snaplock._VERIFIED.clear()


@pytest.fixture
def snap(cw_env, monkeypatch):
    cfg, pkl_dir = cw_env
    for i, sym in enumerate(("AAA", "BBB")):
        make_stock(seed=i).to_pickle(pkl_dir / f"{sym}.pkl")
    monkeypatch.setattr(snaplock, "local_dataset_dir", lambda: pkl_dir)
    _fresh()
    yield cfg, pkl_dir
    _fresh()


def test_fingerprint_by_content_not_mtime(snap, tmp_path):
    _, d = snap
    a = snaplock.fingerprint(d, use_memo=False)
    assert len(a["sha"]) == 64 and a["n_files"] == 2 and a["cutoff"] == "2025-12-31"
    os.utime(d / "AAA.pkl", (1_000_000_000, 1_000_000_000))          # 只改修改时间
    assert snaplock.fingerprint(d, use_memo=False)["sha"] == a["sha"]
    copy = tmp_path / "copy"
    shutil.copytree(d, copy, copy_function=shutil.copyfile)             # 原样拷贝(不带修改时间)
    assert snaplock.fingerprint(copy, use_memo=False)["sha"] == a["sha"]
    make_stock(seed=9).to_pickle(copy / "AAA.pkl")                      # 改了一个文件的内容
    assert snaplock.fingerprint(copy, use_memo=False)["sha"] != a["sha"]
    (d / "CCC.pkl").write_bytes((d / "BBB.pkl").read_bytes())          # 多一个文件
    b = snaplock.fingerprint(d, use_memo=False)
    assert b["sha"] != a["sha"] and b["n_files"] == 3


def test_register_and_replace_need_explicit_commands(snap, state_dir, capsys):
    _, d = snap
    assert snaplock.read_lock(state_dir) is None
    state.main(["snapshot-register", "--generated-on", "upc"])
    lock = snaplock.read_lock(state_dir)
    cur = lock["current"]
    assert cur["sha"] == snaplock.fingerprint(d, use_memo=False)["sha"]
    assert cur["n_files"] == 2 and cur["generated_on"] == "upc" and cur["created_at"]
    assert lock["history"] == []
    assert "已登记副本" in capsys.readouterr().out
    with pytest.raises(SystemExit):                                     # 已登记:不能再「第一次登记」
        state.main(["snapshot-register"])
    assert "snapshot-replace" in capsys.readouterr().err
    with pytest.raises(SystemExit):                                     # 换副本不写原因不行
        state.main(["snapshot-replace"])
    make_stock(seed=7).to_pickle(d / "BBB.pkl")
    _fresh()
    state.main(["snapshot-replace", "--reason", "测试:换一份副本"])
    lock = snaplock.read_lock(state_dir)
    assert len(lock["history"]) == 1
    h = lock["history"][0]
    assert h["reason"] == "测试:换一份副本" and h["old"]["sha"] == cur["sha"]
    assert h["new"]["sha"] == lock["current"]["sha"] != cur["sha"]
    with pytest.raises(ValueError, match="原因"):
        snaplock.replace(state_dir, d, "  ")


def test_mismatch_stops_reads_and_writes(snap, state_dir, capsys):
    cfg, d = snap
    snaplock.register(state_dir, d, "upc")
    assert len(read_bars(cfg, "AAA"))                                   # 一致:照常读
    make_stock(seed=5).to_pickle(d / "AAA.pkl")                        # 本机副本变了
    _fresh()
    registered = snaplock.read_lock(state_dir)["current"]["sha"]
    local = snaplock.fingerprint(d, use_memo=False)["sha"]
    with pytest.raises(snaplock.SnapshotMismatch) as ei:
        read_bars(cfg, "AAA")
    msg = str(ei.value)
    assert snaplock.MISMATCH_TEXT in msg and registered in msg and local in msg
    # 记账入口也停:看过记录、账本都经状态根
    with pytest.raises(snaplock.SnapshotMismatch):
        views.record(surface="manual", event="show_chart", outcome_visible=True,
                     charts=[{"symbol": "AAA", "start": "2025-02-03", "end": "2025-03-03"}],
                     note="测试", ts="2026-10-17T10:00:00", backfill=True)
    assert not (state_dir / "views.jsonl").exists()
    with pytest.raises(SystemExit):
        state.main(["show"])
    err = capsys.readouterr().err
    assert snaplock.MISMATCH_TEXT in err


def test_show_reports_both_fingerprints(snap, state_dir, capsys):
    _, d = snap
    with pytest.raises(SystemExit):                                     # 临时状态根没登记也停
        state.main(["show"])
    cap = capsys.readouterr()
    assert "本机训练数据副本" in cap.out and "没有登记" in cap.err
    snaplock.register(state_dir, d, "upc")
    state.main(["show"])
    out = capsys.readouterr().out
    sha = snaplock.read_lock(state_dir)["current"]["sha"]
    assert out.count(sha) == 2 and "一致" in out


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                   env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
                        "GIT_COMMITTER_EMAIL": "t@t", "PATH": "/usr/bin:/bin:/usr/local/bin",
                        "HOME": str(cwd)})


def test_default_root_must_register(snap, tmp_path, monkeypatch):
    """主目录的账没登记副本就停(读数据和拿状态根都停);登记后照常。"""
    cfg, d = snap
    main = tmp_path / "main"
    root = main / "outputs" / "chart_workflow"
    root.mkdir(parents=True)
    _git(main, "init", "-q", "-b", "master")
    (root / state.MARKER).write_text(state.MARKER_TEXT)
    monkeypatch.delenv(state.ENV_VAR, raising=False)
    monkeypatch.setattr(state, "REPO_ROOT", main)
    monkeypatch.setattr(state, "locate", lambda start=main: root)
    with pytest.raises(snaplock.SnapshotNotRegistered, match="snapshot-register"):
        state.state_root(start=main)
    with pytest.raises(snaplock.SnapshotNotRegistered):
        read_bars(cfg, "AAA")
    snaplock.register(root, d, "upc")
    assert state.state_root(start=main) == root
    assert len(read_bars(cfg, "AAA"))


def test_lock_file_tracked_by_git_and_listed():
    from chart_workflow.config import REPO_ROOT
    r = subprocess.run(["git", "check-ignore", "-q", "--no-index",
                        "outputs/chart_workflow/snapshot_lock.json"], cwd=REPO_ROOT)
    assert r.returncode == 1                                           # 不被忽略 → 受 git 跟踪
    assert "snapshot_lock.json" in state.MARKER_TEXT


def test_manifest_records_host(tmp_path):
    from chart_workflow.snapshot import build_snapshot
    src = tmp_path / "src"
    src.mkdir()
    make_stock(end="2026-03-31").to_pickle(src / "AAA.pkl")
    man = build_snapshot(src, tmp_path / "dst", verbose=False)
    assert man["host"] and json.loads((tmp_path / "dst" / "SNAPSHOT.json").read_text())["host"]
    assert snaplock.fingerprint(tmp_path / "dst", use_memo=False)["generated_on"] == man["host"]


def test_temp_root_unregistered_stops_too(snap, state_dir):
    """环境变量指的临时状态根没登记副本:读数据、拿状态根一样停(不再顺带关掉核对)。"""
    cfg, d = snap
    with pytest.raises(snaplock.SnapshotNotRegistered):
        read_bars(cfg, "AAA")
    with pytest.raises(snaplock.SnapshotNotRegistered):
        state.state_root()
    snaplock.register(state_dir, d, "upc")
    assert len(read_bars(cfg, "AAA")) and state.state_root() == state_dir


def test_fingerprint_counts_only_pkl_and_manifest(snap, tmp_path):
    """同步工具留下的隐藏文件、别的杂文件不进指纹:拷过去多一个 .stignore 也是同一份。"""
    _, d = snap
    a = snaplock.fingerprint(d, use_memo=False)
    (d / ".stignore").write_text("x")
    (d / "notes.txt").write_text("y")
    (d / "sub").mkdir()
    assert snaplock.fingerprint(d, use_memo=False)["sha"] == a["sha"]
    assert snaplock.fingerprint(d)["sha"] == a["sha"]
    (d / "SNAPSHOT.json").write_text((d / "SNAPSHOT.json").read_text() + " ")   # 清单本身算
    assert snaplock.fingerprint(d, use_memo=False)["sha"] != a["sha"]


def test_in_place_change_detected_without_restart(snap, state_dir):
    """进程运行中原地改了副本里的 pkl(清单没动):不清进程内的记忆,下次读它就停;
    读别的股票、拿状态根(核对整份副本)也停。"""
    cfg, d = snap
    snaplock.register(state_dir, d, "upc")
    assert len(read_bars(cfg, "AAA")) and len(read_bars(cfg, "BBB"))
    df = make_stock(seed=0)
    df["close"] = 999.0
    df.to_pickle(d / "AAA.pkl")                                           # 原地改,SNAPSHOT.json 不动
    with pytest.raises(snaplock.SnapshotMismatch):
        read_bars(cfg, "AAA")
    with pytest.raises(snaplock.SnapshotMismatch):
        state.state_root()
    with pytest.raises(snaplock.SnapshotMismatch):
        read_bars(cfg, "BBB")


def test_in_place_change_same_size_and_mtime_kept_is_still_caught_on_full_check(snap, state_dir):
    """只比大小和修改时间:内容改了但两者都被刻意保持不变时,读单只股票的快路径看不出来;
    重新按内容算(换副本登记、state show 用的 use_memo=False)照样对不上。"""
    cfg, d = snap
    snaplock.register(state_dir, d, "upc")
    raw = bytearray((d / "AAA.pkl").read_bytes())
    st = (d / "AAA.pkl").stat()
    raw[-10] ^= 0xFF
    (d / "AAA.pkl").write_bytes(bytes(raw))
    os.utime(d / "AAA.pkl", ns=(st.st_atime_ns, st.st_mtime_ns))
    assert snaplock.fingerprint(d, use_memo=False)["sha"] != snaplock.read_lock(state_dir)["current"]["sha"]
