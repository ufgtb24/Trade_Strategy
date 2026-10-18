"""调试模式(chart_workflow/mode.py):上界 2022-09-30 是硬上限(配置、命令行覆盖、读数据口的终点、前瞻收益都越不过);
调试模式只写调试账、正式账一个字节不变、正式水位不读不写;两种模式的账、清单名、清单标记、决定文件互不相通;
调试账能一条命令清空重来,清空只删调试账,指向别处就拒。

正式账在这些测试里是 conftest 的临时状态根(环境变量 CHART_WORKFLOW_STATE_ROOT),调试账是另一个临时目录
(环境变量 CHART_WORKFLOW_DEBUG_STATE_ROOT)。"""
import hashlib
import json
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from chart_workflow import bigmoves, contrast, debugroot, loader, mode, shapes, snaplock, state, views
from chart_workflow.config import DEFAULTS, load_config, root_dir
from chart_workflow.ledger import check_new_list_id, read_ledger, render
from chart_workflow.listfile import ListValidationError, new_list, validate
from chart_workflow.panel import build_panel
from tests.chart_workflow.conftest import make_stock, write_snapshot_manifest

END = pd.Timestamp(mode.DEBUG_END)

RULE = '''
def signal(df):
    return df["close"] > df["close"].rolling(20).max().shift(1)
'''


def digest(d: Path) -> dict:
    """目录里每个文件的指纹(含隐藏文件,如临时状态根的水位)。"""
    return {str(p.relative_to(d)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(Path(d).rglob("*")) if p.is_file()}


@pytest.fixture(autouse=True)
def _fresh_caches():
    snaplock._FP.clear()
    snaplock._VERIFIED.clear()
    loader._dates_cached.cache_clear()
    yield
    snaplock._FP.clear()
    snaplock._VERIFIED.clear()
    loader._dates_cached.cache_clear()


@pytest.fixture(autouse=True)
def main_formal(tmp_path, monkeypatch):
    """主目录默认的正式账(调试账不得碰它)在测试里换成 tmp 下的一个位置:真主目录的 .git 测试碰不得。"""
    p = tmp_path / "main_repo" / "outputs" / "chart_workflow"
    monkeypatch.setattr(state, "formal_default", lambda start=None: p)
    return p


@pytest.fixture
def dbg(tmp_path, monkeypatch, state_dir):
    """调试模式 + 已建好的临时调试账;返回 (cfg, pkl_dir, 调试账)。cfg 在调试模式下读,数据与产物都在 tmp。"""
    monkeypatch.setenv(mode.ENV_VAR, mode.DEBUG)
    droot = tmp_path / "debug_state"
    monkeypatch.setenv(state.DEBUG_ENV_VAR, str(droot))
    debugroot.init()
    pkl_dir = tmp_path / "pkls"
    pkl_dir.mkdir()
    write_snapshot_manifest(pkl_dir)
    cfg = load_config(path=tmp_path / "none.yaml", override={
        "dataset_dir": str(pkl_dir), "root": str(tmp_path / "out"), "workers": 1,
        "control": {"n_boot": 50}})
    return cfg, pkl_dir, droot


def _stocks(pkl_dir, n=3, seed=40, end="2026-03-31"):
    for i in range(n):
        make_stock(start="2021-10-08", end=end, seed=seed + i, sigma=0.04).to_pickle(pkl_dir / f"C{i}.pkl")


# ── 模式本身 ─────────────────────────────────────────────────────────────────

def test_mode_env_values(monkeypatch):
    monkeypatch.delenv(mode.ENV_VAR, raising=False)
    assert mode.current() == mode.FORMAL
    monkeypatch.setenv(mode.ENV_VAR, "formal")
    assert mode.current() == mode.FORMAL
    monkeypatch.setenv(mode.ENV_VAR, "debug")
    assert mode.current() == mode.DEBUG
    monkeypatch.setenv(mode.ENV_VAR, "Debug ")          # 拼错了不悄悄当正式模式跑
    with pytest.raises(mode.ModeError):
        mode.current()
    with pytest.raises(mode.ModeError):
        state.state_root()
    with pytest.raises(mode.ModeError):
        load_config()


def test_formal_config_unchanged(tmp_path, monkeypatch):
    """正式模式一个键都不改(没有 mode 键,训练段、下界、内圈年份、root 照旧)。"""
    monkeypatch.delenv(mode.ENV_VAR, raising=False)
    cfg = load_config(path=tmp_path / "none.yaml")
    assert "mode" not in cfg
    for k in ("train_start", "train_end", "view_floor", "root"):
        assert cfg[k] == DEFAULTS[k]
    assert cfg["contrast"]["inner_years"] == DEFAULTS["contrast"]["inner_years"]


def test_debug_range_cannot_be_moved_by_config(tmp_path, monkeypatch):
    """调试模式:yaml 与 override 写的训练段、下界、内圈年份、root 一律换成调试段的。"""
    monkeypatch.setenv(mode.ENV_VAR, mode.DEBUG)
    y = tmp_path / "c.yaml"
    y.write_text("train_start: '2024-01-01'\ntrain_end: '2025-12-31'\nview_floor: '2025-01-01'\n"
                 "contrast:\n  inner_years: ['2025']\nroot: outputs/chart_workflow\n")
    cfg = load_config(path=y, override={"train_end": "2025-06-30", "view_floor": "2022-01-01"})
    assert (cfg["train_start"], cfg["train_end"], cfg["view_floor"]) == (
        mode.DEBUG_START, mode.DEBUG_END, mode.DEBUG_START)
    assert cfg["contrast"]["inner_years"] == ["2021", "2022"]
    assert Path(cfg["root"]).name == "chart_workflow_debug" and cfg["mode"] == mode.DEBUG
    cfg = load_config(path=tmp_path / "none.yaml", override={"root": str(tmp_path / "out")})
    assert Path(cfg["root"]) == tmp_path / "out_debug"


# ── 上界:读数据口、前瞻收益 ───────────────────────────────────────────────────

def test_loader_ceiling_in_debug(dbg, monkeypatch):
    """读数据口:不论 cfg、until、终点参数写多晚,调试模式读出来的行情都不晚于 2022-09-30。"""
    cfg, pkl_dir, _ = dbg
    make_stock(start="2021-10-08", end="2026-03-31").to_pickle(pkl_dir / "AAA.pkl")
    late = {**cfg, "train_end": "2025-12-31"}                       # 绕过 load_config 的 cfg
    assert loader.read_bars(cfg, "AAA").index.max() <= END
    assert loader.read_bars(late, "AAA").index.max() <= END
    assert loader.read_bars(late, "AAA", until="2025-06-30").index.max() <= END
    assert loader.load_bars(pkl_dir, "AAA", "2026-06-30").index.max() <= END
    assert loader.trading_dates(late, "AAA").max() <= END
    assert loader.load_bars(pkl_dir, "AAA", "2022-06-30").index.max() == pd.Timestamp("2022-06-30")
    monkeypatch.setattr(loader, "min", lambda *a: "2099-12-31", raising=False)   # 截断那一步失效
    with pytest.raises(loader.PastHardEnd, match="调试段之后"):
        loader.load_bars(pkl_dir, "AAA", "2026-06-30")


def test_formal_ceiling_unchanged(cw_env, monkeypatch):
    monkeypatch.delenv(mode.ENV_VAR, raising=False)
    cfg, pkl_dir = cw_env
    make_stock(end="2026-03-31").to_pickle(pkl_dir / "AAA.pkl")
    assert loader.read_bars(cfg, "AAA").index.max() == pd.Timestamp(loader.HARD_END)
    assert loader.read_ceiling() == loader.HARD_END


def test_forward_outcomes_finish_inside_debug_segment(dbg, tmp_path):
    """面板(大涨段、对照页的成绩都从它来):每个股票日的观察期都在 2022-09-30 之前走完;把 2022-09-30 之后的
    行情换成随机数,面板一字不差(没拿后面的数据补)。"""
    cfg, pkl_dir, _ = dbg
    _stocks(pkl_dir)
    a = build_panel(cfg, verbose=False)
    assert len(a) > 50
    assert a["date"].min() >= pd.Timestamp(mode.DEBUG_START)
    for col in ("date", "entry_date", "peak_date", "stop_date", "win_end"):
        assert pd.to_datetime(a[col]).max() <= END, col
    rng = np.random.default_rng(7)
    for p in sorted(pkl_dir.glob("*.pkl")):
        df = pd.read_pickle(p)
        after = df.index > END
        df.loc[after, ["open", "high", "low", "close"]] = rng.uniform(1, 500, (after.sum(), 4))
        df.loc[after, "volume"] = rng.uniform(1, 1e9, after.sum())
        df.to_pickle(p)
    snaplock._FP.clear()
    snaplock._VERIFIED.clear()
    b = build_panel(cfg, refresh=True, verbose=False)
    pd.testing.assert_frame_equal(a.reset_index(drop=True), b.reset_index(drop=True))


def test_no_env_var_moves_the_debug_end(dbg, monkeypatch):
    """环境变量只选模式、不带日期:设一串看起来能改日期的环境变量,上界照旧是 2022-09-30。"""
    cfg, pkl_dir, _ = dbg
    make_stock(start="2021-10-08", end="2026-03-31").to_pickle(pkl_dir / "AAA.pkl")
    for name in ("CHART_WORKFLOW_DEBUG_END", "CHART_WORKFLOW_TRAIN_END", "CHART_WORKFLOW_HARD_END",
                 "CHART_WORKFLOW_VIEW_FLOOR", "CHART_WORKFLOW_DEBUG_START"):
        monkeypatch.setenv(name, "2025-12-31")
    assert loader.read_ceiling() == mode.DEBUG_END
    cfg2 = load_config(path=Path(cfg["root"]).parent / "none.yaml")
    assert (cfg2["train_end"], cfg2["view_floor"]) == (mode.DEBUG_END, mode.DEBUG_START)
    assert loader.read_bars(cfg, "AAA").index.max() <= END


def test_facts_and_xcheck_stay_inside_debug_segment(dbg):
    """事实表的买点、跨源比对向 Nasdaq 请求的区间都在调试段内。"""
    from chart_workflow.facts import facts_for
    from chart_workflow.xcheck import NasdaqSource
    cfg, pkl_dir, _ = dbg
    make_stock(start="2021-10-08", end="2026-03-31").to_pickle(pkl_dir / "AAA.pkl")
    with pytest.raises(ValueError, match="2022-09-30"):
        facts_for(cfg, "AAA", "2022-10-03")
    out = facts_for(cfg, "AAA", "2022-06-01")
    assert out["window"][1] == "2022-06-01"
    src = NasdaqSource(cfg, fetch=lambda url, timeout: {})
    assert src.todate == mode.DEBUG_END and src.fromdate < mode.DEBUG_START
    assert Path(src.cache_dir).parts[-3] == "out_debug"


# ── 只写调试账 ───────────────────────────────────────────────────────────────

def test_debug_cli_writes_only_debug_ledger(dbg, tmp_path, monkeypatch, state_dir):
    """调试模式跑大涨段、对照页、聊天贴图记看过:记账全进调试账,清单进 _debug 目录;正式账一个字节不变。"""
    cfg, pkl_dir, droot = dbg
    _stocks(pkl_dir)
    rule = tmp_path / "breakout20.py"
    rule.write_text(RULE)
    monkeypatch.setattr(contrast, "load_config", lambda: cfg)
    monkeypatch.setattr(bigmoves, "load_config", lambda: cfg)
    before = digest(state_dir)
    bigmoves.main(["--list-id", "dbg-big", "--no-xcheck"])
    contrast.main(["--list-id", "dbg-c1", "--rule", str(rule), "--source", "user-text",
                   "--change", "调试", "--no-xcheck"])
    views.record(surface="chat", event="show_chart", outcome_visible=True,
                 charts=[{"symbol": "C0", "start": "2022-01-03", "end": "2022-03-01"}])
    assert digest(state_dir) == before
    assert not (state_dir / "ledger.jsonl").exists() and not (state_dir / "views.jsonl").exists()
    rows = read_ledger()
    assert [r["list_id"] for r in rows] == ["dbg-big", "dbg-c1"] and rows[1]["years"] == ["2021", "2022"]
    assert "调试账" in render(rows) and "累计尝试次数" not in render(rows)
    assert (droot / "ledger.jsonl").exists() and (droot / "views.jsonl").exists()
    assert (droot / "rule_archive").is_dir() and (droot / "config_archive").is_dir()
    lists = Path(cfg["root"]) / "lists"
    assert lists.parent.name == "out_debug"
    for name in ("dbg-big", "dbg-c1"):
        doc = json.loads((lists / f"{name}.json").read_text())
        assert doc["mode"] == mode.DEBUG and doc["title"].startswith("【调试】")
        assert doc["train_end"] == mode.DEBUG_END
        for it in doc["items"]:
            assert it["view_end"] <= mode.DEBUG_END and it["t"] <= mode.DEBUG_END
    assert not (tmp_path / "out").exists()                  # 正式的产物目录没碰
    # 聊天贴图越过调试段终点 → 拒绝
    with pytest.raises(ValueError, match="越出了调试段"):
        views.record(surface="chat", event="show_chart", outcome_visible=True,
                     charts=[{"symbol": "C0", "start": "2022-09-01", "end": "2022-10-31"}])


def _git_repo(path: Path) -> Path:
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty",
                    "-m", "init"], cwd=path, check=True)
    return path


def test_debug_never_touches_formal_watermark(tmp_path, monkeypatch, state_dir):
    """主目录里调试账和正式账在同一个仓库:按仓库取水位位置就会落到正式那份。调试模式下写东西、给状态根,
    仓库的 git 公共目录里都不出现水位;直接调水位函数也拒绝。"""
    repo = _git_repo(tmp_path / "repo")
    droot = repo / "outputs" / "chart_workflow_debug"
    monkeypatch.setenv(mode.ENV_VAR, mode.DEBUG)
    monkeypatch.setenv(state.DEBUG_ENV_VAR, str(droot))
    debugroot.init()
    assert state.state_root() == droot.resolve()
    views.record(surface="chat", event="show_chart", outcome_visible=True,
                 charts=[{"symbol": "AAA", "start": "2022-01-03", "end": "2022-03-01"}])
    state.advance(droot)
    assert not (repo / ".git" / "chart_workflow").exists()
    assert not list(droot.glob(".watermark*"))
    with pytest.raises(state.StateRootMissing, match="没有水位"):
        state.watermark_path(droot)
    with pytest.raises(state.StateRootMissing, match="没有水位"):
        state.reset_watermark(droot, "试试")
    monkeypatch.delenv(mode.ENV_VAR)                         # 正式模式也不拿调试账算水位
    with pytest.raises(state.StateRootMissing, match="没有水位"):
        state.watermark_path(droot)
    assert not (repo / ".git" / "chart_workflow").exists()


# ── 两种模式互不相通 ──────────────────────────────────────────────────────────

def test_state_roots_do_not_cross(dbg, tmp_path, monkeypatch, state_dir):
    cfg, _, droot = dbg
    assert state.state_root() == droot.resolve()            # 调试模式不认 CHART_WORKFLOW_STATE_ROOT
    monkeypatch.setenv(state.DEBUG_ENV_VAR, str(state_dir))  # 调试模式指到正式账
    with pytest.raises(state.WrongModeRoot):
        state.state_root()
    inner = state_dir / "sub"                                # 指到正式账里面(哪怕放了调试账标记)
    inner.mkdir()
    (inner / state.DEBUG_MARKER).write_text("x")
    monkeypatch.setenv(state.DEBUG_ENV_VAR, str(inner))
    with pytest.raises(state.WrongModeRoot):
        state.state_root()
    fresh = tmp_path / "never_made"                          # 还没建:停下,不悄悄新建
    monkeypatch.setenv(state.DEBUG_ENV_VAR, str(fresh))
    with pytest.raises(state.StateRootMissing, match="还没建"):
        state.state_root()
    assert not fresh.exists()
    monkeypatch.delenv(mode.ENV_VAR)                          # 正式模式指到调试账
    monkeypatch.setenv(state.ENV_VAR, str(droot))
    with pytest.raises(state.WrongModeRoot):
        state.state_root()
    with pytest.raises(ValueError, match="调试账"):
        state.init(droot)                                     # 也不能在调试账里开正式格式的账


def test_list_names_and_tags_do_not_cross(dbg, monkeypatch):
    cfg, _, _ = dbg
    with pytest.raises(mode.ModeError, match="dbg-"):
        check_new_list_id(cfg, "r001-bigmoves")               # 调试模式的清单名必须 dbg- 开头
    check_new_list_id(cfg, "dbg-r001")
    doc = new_list("dbg-r001", "bigmoves", "大涨段", cfg)
    assert doc["mode"] == mode.DEBUG
    validate(doc)
    formal_doc = {**doc, "list_id": "dbg-r002"}
    formal_doc.pop("mode")
    with pytest.raises(ListValidationError, match="正式模式"):
        validate(formal_doc)                                  # 没有调试标记的清单,调试模式不写
    with pytest.raises(ListValidationError, match="调试段终点"):
        validate({**doc, "train_end": "2025-12-31"})
    monkeypatch.delenv(mode.ENV_VAR)
    with pytest.raises(mode.ModeError, match="正式模式不收"):
        check_new_list_id(cfg, "dbg-r003")                    # 调试时忘了带模式环境变量:当场报错
    with pytest.raises(ListValidationError, match="调试模式"):
        validate({**doc, "list_id": "r003"})                  # 带调试标记的清单,正式模式不写
    assert "mode" not in new_list("r004", "bigmoves", "大涨段", load_config())


def test_forgotten_mode_env_is_caught_on_cli(dbg, tmp_path, monkeypatch, state_dir):
    """调试会话里某条命令忘了带 CHART_WORKFLOW_MODE=debug:大涨段、对照页、聊天记看过、形态卡决定文件都当场拒绝,
    正式账一个字节不变。"""
    cfg, pkl_dir, _ = dbg
    monkeypatch.delenv(mode.ENV_VAR)
    formal = load_config(path=tmp_path / "none.yaml", override={
        "dataset_dir": str(pkl_dir), "root": str(tmp_path / "out"), "workers": 1})
    monkeypatch.setattr(bigmoves, "load_config", lambda: formal)
    monkeypatch.setattr(contrast, "load_config", lambda: formal)
    rule = tmp_path / "r.py"
    rule.write_text(RULE)
    before = digest(state_dir)
    with pytest.raises(SystemExit):
        bigmoves.main(["--list-id", "dbg-big", "--no-xcheck"])
    with pytest.raises(SystemExit):
        contrast.main(["--list-id", "dbg-c1", "--rule", str(rule), "--source", "user-text",
                       "--change", "x", "--no-xcheck"])
    with pytest.raises(SystemExit):
        views.main(["record", "--surface", "chat", "--list-id", "dbg-big", "--outcome-visible", "yes"])
    with pytest.raises(shapes.ShapeValidationError, match="正式模式不收"):
        shapes.apply({"schema": shapes.DECISION_SCHEMA, "mode": "debug", "ops": [{"act": "shown"}]})
    assert digest(state_dir) == before


def test_decision_mode_tripwire(monkeypatch):
    ok = {"schema": shapes.DECISION_SCHEMA, "ops": []}
    monkeypatch.delenv(mode.ENV_VAR, raising=False)
    shapes.check_decision_mode(ok)
    shapes.check_decision_mode({**ok, "mode": "formal"})
    with pytest.raises(shapes.ShapeValidationError):
        shapes.check_decision_mode({**ok, "mode": "debug"})
    monkeypatch.setenv(mode.ENV_VAR, mode.DEBUG)
    shapes.check_decision_mode({**ok, "mode": "debug"})
    with pytest.raises(shapes.ShapeValidationError, match="mode"):
        shapes.check_decision_mode(ok)


@pytest.mark.real_snaplock
def test_debug_snapshot_lock_is_checked(tmp_path, monkeypatch, state_dir):
    """调试账登记的是和正式账同一份副本;本机副本换了就停下;新建时本机副本和正式账登记的不是同一份就拒绝,
    什么都不建。"""
    local = tmp_path / "snap"
    local.mkdir()
    write_snapshot_manifest(local)
    monkeypatch.setattr(snaplock, "local_dataset_dir", lambda: local)
    snaplock.register(state_dir, local, "测试")
    monkeypatch.setenv(mode.ENV_VAR, mode.DEBUG)
    droot = tmp_path / "d"
    monkeypatch.setenv(state.DEBUG_ENV_VAR, str(droot))
    debugroot.init()
    assert snaplock.read_lock(droot)["current"]["sha"] == snaplock.read_lock(state_dir)["current"]["sha"]
    assert state.state_root() == droot.resolve()
    write_snapshot_manifest(local, cutoff="2025-12-30")         # 本机副本变了
    snaplock._FP.clear()
    snaplock._VERIFIED.clear()
    with pytest.raises(snaplock.SnapshotMismatch, match="debugroot clear"):
        state.state_root()
    other = tmp_path / "d2"
    monkeypatch.setenv(state.DEBUG_ENV_VAR, str(other))
    with pytest.raises(debugroot.DebugRootRefused, match="不是同一份"):
        debugroot.init()
    assert not other.exists()


# ── 清空重来:只删调试账,指向别处就拒 ─────────────────────────────────────────

def _fill(droot: Path) -> None:
    for rel in ("annotations/20220101T000000.json", "oplog/2026-10.jsonl", "viewed_lists/dbg-x@1.json",
                "cache/panel_x.parquet", "facts/f.json"):
        (droot / rel).parent.mkdir(parents=True, exist_ok=True)
        (droot / rel).write_text("x\n")
    (droot / "ledger.jsonl").write_text('{"r": 1}\n')
    (droot / "data_errors.json").write_text("{}")


def test_clear_wipes_debug_ledger_keeps_cache(dbg, tmp_path, state_dir):
    _, _, droot = dbg
    _fill(droot)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_text("别删我")
    (droot / "lists").symlink_to(outside, target_is_directory=True)    # 认识的名字,但是个链接
    (droot / "snapshot_lock.json.tmp").write_text("x")                 # 工具留下的临时文件
    before = digest(state_dir)
    path, removed = debugroot.clear()
    assert path == droot.resolve()
    assert sorted(p.name for p in droot.iterdir()) == ["DEBUG_LEDGER.md", "cache", "snapshot_lock.json"]
    assert (droot / "cache" / "panel_x.parquet").exists()
    assert "ledger.jsonl" in removed and "lists" in removed and "cache" not in removed
    assert (outside / "keep.txt").read_text() == "别删我"        # 符号链接只删链接本身
    assert digest(state_dir) == before
    assert state.state_root() == droot.resolve()                # 清空后照常能用
    assert read_ledger() == []


@pytest.mark.parametrize("where", ["formal", "inside_formal", "parent_of_formal", "repo", "repo_parent",
                                   "foreign_nonempty", "formal_marker_elsewhere"])
def test_clear_refuses_anything_but_debug_ledger(dbg, tmp_path, monkeypatch, state_dir, where):
    from chart_workflow.config import REPO_ROOT
    other = tmp_path / "other"
    other.mkdir()
    (other / "important.txt").write_text("x")
    target = {"formal": state_dir, "inside_formal": state_dir / "annotations",
              "parent_of_formal": state_dir.parent, "repo": Path(REPO_ROOT),
              "repo_parent": Path(REPO_ROOT).parent, "foreign_nonempty": other,
              "formal_marker_elsewhere": state_dir}[where]
    if where == "formal_marker_elsewhere":                       # 正式账挪到别处,调试账指向一个带正式标记的目录
        target = tmp_path / "looks_formal"
        target.mkdir()
        (target / state.MARKER).write_text("x")
        (target / "ledger.jsonl").write_text("{}\n")
    monkeypatch.setenv(state.DEBUG_ENV_VAR, str(target))
    monkeypatch.setattr(state, "debug_default", lambda start=None: tmp_path / "the_default_debug_root")
    before = digest(state_dir)
    snap = sorted(p.name for p in target.iterdir()) if target.is_dir() else None
    with pytest.raises(debugroot.DebugRootRefused):
        debugroot.clear()
    with pytest.raises(debugroot.DebugRootRefused):
        debugroot.init()
    assert digest(state_dir) == before
    if snap is not None and where not in ("repo", "repo_parent"):
        assert sorted(p.name for p in target.iterdir()) == snap


def test_clear_refuses_git_tracked(dbg, tmp_path, monkeypatch):
    repo = _git_repo(tmp_path / "repo2")
    d = repo / "outputs" / "chart_workflow_debug"
    d.mkdir(parents=True)
    (d / state.DEBUG_MARKER).write_text("x")
    (d / "ledger.jsonl").write_text("{}\n")
    subprocess.run(["git", "add", "-f", "outputs"], cwd=repo, check=True)
    monkeypatch.setenv(state.DEBUG_ENV_VAR, str(d))
    with pytest.raises(debugroot.DebugRootRefused, match="git"):
        debugroot.clear()
    assert (d / "ledger.jsonl").exists()


def test_default_location_with_old_formal_style_root(dbg, tmp_path, monkeypatch):
    """调试账的默认位置上以前被人用正式格式 init 过(只有 STATE_ROOT.md、副本登记、临时水位):调试模式拒绝用它,
    新建也拒绝(提示用 clear);clear 照常清掉重建。"""
    d = tmp_path / "main" / "outputs" / "chart_workflow_debug"
    d.mkdir(parents=True)
    for name in (state.MARKER, "snapshot_lock.json", ".watermark.json"):
        (d / name).write_text("x")
    monkeypatch.delenv(state.DEBUG_ENV_VAR)
    monkeypatch.setattr(state, "debug_default", lambda start=None: d)
    with pytest.raises(state.WrongModeRoot, match="clear"):
        state.state_root()
    with pytest.raises(debugroot.DebugRootRefused, match="clear"):
        debugroot.init()
    path, removed = debugroot.clear()
    assert path == d.resolve() and sorted(removed) == sorted([state.MARKER, "snapshot_lock.json", ".watermark.json"])
    assert state.state_root() == d.resolve()


def test_init_is_idempotent(dbg):
    _, _, droot = dbg
    (droot / "ledger.jsonl").write_text('{"r": 1}\n')
    debugroot.init()
    assert (droot / "ledger.jsonl").read_text() == '{"r": 1}\n'


def test_state_show_in_debug(dbg, capsys):
    state.main(["show"])
    out = capsys.readouterr().out
    assert mode.DEBUG_LABEL in out and "调试账" in out and "没有水位" in out
    with pytest.raises(SystemExit):
        state.main(["reset-watermark", "--reason", "x"])


def test_clear_stops_on_unknown_entries(dbg, tmp_path):
    """清空只删认识的条目:顶层有不认识的东西(文件、目录、链接)就停下、列出来,一样都不删。"""
    _, _, droot = dbg
    _fill(droot)
    (droot / "notes.txt").write_text("用户自己的笔记")
    (droot / "photos").mkdir()
    outside = tmp_path / "outside2"
    outside.mkdir()
    (outside / "keep.txt").write_text("x")
    (droot / "link").symlink_to(outside, target_is_directory=True)
    before = digest(droot)
    with pytest.raises(debugroot.DebugRootRefused, match="不认识") as ei:
        debugroot.clear()
    assert all(n in str(ei.value) for n in ("notes.txt", "photos", "link"))
    assert digest(droot) == before and (droot / "photos").is_dir()


@pytest.mark.parametrize("how", ["default", "env"])
def test_symlinked_debug_location_refused(dbg, tmp_path, monkeypatch, how):
    """调试账的位置本身是符号链接:新建、清空都拒绝(按解析之前的路径判断),链接指向的目录一样都不删。"""
    _, _, droot = dbg
    _fill(droot)
    link = tmp_path / "linked_debug_root"
    link.symlink_to(droot, target_is_directory=True)
    if how == "default":
        monkeypatch.delenv(state.DEBUG_ENV_VAR)
        monkeypatch.setattr(state, "debug_default", lambda start=None: link)
    else:
        monkeypatch.setenv(state.DEBUG_ENV_VAR, str(link))
    before = digest(droot)
    with pytest.raises(debugroot.DebugRootRefused, match="符号链接"):
        debugroot.clear()
    with pytest.raises(debugroot.DebugRootRefused, match="符号链接"):
        debugroot.init()
    assert digest(droot) == before


def test_debug_root_never_inside_any_formal_ledger(dbg, tmp_path, monkeypatch, main_formal, state_dir):
    """两个环境变量同时指错(正式账变量指临时目录、调试账变量指主目录正式账下面一个不存在的子目录):
    新建、清空、给状态根都拒绝,主目录正式账里什么都不建;往上任何一层有正式账标记的目录同样拒绝。"""
    main_formal.mkdir(parents=True)
    (main_formal / state.MARKER).write_text("x")
    (main_formal / "ledger.jsonl").write_text('{"r": 1}\n')
    before = digest(main_formal)
    for target in (main_formal / "debug_sub", main_formal):
        monkeypatch.setenv(state.DEBUG_ENV_VAR, str(target))
        with pytest.raises(debugroot.DebugRootRefused, match="正式账"):
            debugroot.init()
        with pytest.raises(debugroot.DebugRootRefused, match="正式账"):
            debugroot.clear()
        with pytest.raises(state.WrongModeRoot):
            state.state_root()
    assert digest(main_formal) == before and not (main_formal / "debug_sub").exists()
    other = tmp_path / "some_old_copy_of_formal"                # 既不是环境变量指的、也不是主目录的
    other.mkdir()
    (other / state.MARKER).write_text("x")
    deep = other / "a" / "b"
    monkeypatch.setenv(state.DEBUG_ENV_VAR, str(deep))
    with pytest.raises(debugroot.DebugRootRefused, match="那一层有标记"):
        debugroot.init()
    assert not (other / "a").exists()
    deep.mkdir(parents=True)
    (deep / state.DEBUG_MARKER).write_text("x")
    with pytest.raises(state.WrongModeRoot, match="那一层有标记"):
        state.state_root()


# ── 看过记录:两种模式各记各的 ────────────────────────────────────────────────

def test_debug_mode_views_only_inside_debug_segment(dbg, state_dir):
    """调试模式:越出调试段的图,不分聊天还是补记、加了 --allow-outside 也不收,提示去正式模式记;调试账、正式账
    都一行不多。"""
    _, _, droot = dbg
    before_f, before_d = digest(state_dir), digest(droot)
    cases = [dict(surface="chat", charts=[{"symbol": "AAA", "start": "2025-03-03", "end": "2025-05-30"}],
                  allow_outside=True, outside_reason="用户主动贴的"),
             dict(surface="manual", backfill=True, ts="2026-10-18T09:00:00", note="补记",
                  charts=[{"symbol": "AAA", "start": "2025-03-03", "end": "2025-05-30"}]),
             dict(surface="manual", charts=[{"symbol": "AAA", "start": "2022-08-01", "end": "2022-11-30"}]),
             dict(surface="manual", charts=[{"symbol": "AAA", "start": "2021-06-01", "end": "2021-12-31"}]),
             dict(surface="chat", event="open_list", list_id="dbg-x", list_doc={"kind": "bigmoves", "items": [
                 {"item_id": "A@2022-03-01", "symbol": "A", "view_start": "2022-01-03", "view_end": "2022-04-29"},
                 {"item_id": "B@2023-03-01", "symbol": "B", "view_start": "2023-01-03", "view_end": "2023-04-28"}]})]
    for kw in cases:
        kw = {"event": "show_chart", "outcome_visible": True, **kw}
        with pytest.raises(ValueError, match="越出了调试段") as ei:
            views.record(**kw)
        assert "正式模式下记" in str(ei.value)
    assert digest(state_dir) == before_f and digest(droot) == before_d
    views.record(surface="manual", event="show_chart", outcome_visible=True,
                 charts=[{"symbol": "AAA", "start": "2021-10-08", "end": "2022-09-30"}])   # 调试段以内照收


def test_formal_mode_refuses_views_inside_debug_segment(state_dir, monkeypatch):
    """正式模式:整张都在调试段里的图,聊天加 --allow-outside、手动、补记都不收,提示带上模式变量;
    只是一部分落在调试段里的照旧(补记不受看图下界限制)。"""
    monkeypatch.delenv(mode.ENV_VAR, raising=False)
    before = digest(state_dir)
    for kw in (dict(surface="chat", allow_outside=True, outside_reason="忘了带模式变量"),
               dict(surface="manual"),
               dict(surface="manual", backfill=True, ts="2026-10-18T09:00:00", note="补记")):
        with pytest.raises(ValueError, match="整张都在调试段") as ei:
            views.record(event="show_chart", outcome_visible=True,
                         charts=[{"symbol": "AAA", "start": "2022-01-03", "end": "2022-03-01"}], **kw)
        assert f"{mode.ENV_VAR}=debug" in str(ei.value)
    assert digest(state_dir) == before
    views.record(surface="manual", event="show_chart", outcome_visible=True, backfill=True,
                 ts="2026-10-18T09:00:00", note="补记:跨进预检段",
                 charts=[{"symbol": "AAA", "start": "2022-08-01", "end": "2022-11-30"}])
    with pytest.raises(SystemExit):                              # 命令行同样拦
        views.main(["record", "--surface", "chat", "--symbol", "AAA", "--start", "2022-01-03", "--end",
                    "2022-03-01", "--outcome-visible", "yes", "--allow-outside", "--reason", "x"])
