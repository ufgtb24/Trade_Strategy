# -*- coding: utf-8 -*-
"""tune.py(调用面薄包装)的测试:接线测试 monkeypatch 下游模块,断言传参与返回摘要;确认窗取数用合成 app
(本文件即 app 模块)+ 合成 pkl + tmp 账本端到端跑。不碰真实 apps/、outputs/ 与账本。"""
import copy
import json
import os
import subprocess
import sys
import types
from dataclasses import dataclass, replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tune  # noqa: E402
import holdout  # noqa: E402
import ledger  # noqa: E402
from path2.core import Event  # noqa: E402
from path2.dag import where as Wh  # noqa: E402
from path2.dag.edges import TemporalEdge  # noqa: E402
from path2.dag.nodes import NodeSpec  # noqa: E402
from path2.dag.spec import PatternSpec  # noqa: E402

CAL = pd.bdate_range("2021-08-20", "2026-08-17")
HB, HZ = 250, 40
PAST = "2026-01-05T09:00:00"
FPS = {"git_head": "abc1234", "base_fingerprint": "b" * 64, "source_fingerprint": "s" * 64, "ruler_fingerprint": "r" * 64}


@pytest.fixture(autouse=True)
def ledger_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("TUNE_LEDGER_DIR", str(tmp_path / "ledger"))


def _common(**kw):
    f = dict(actor="test", round=None, window=None, label_horizon=None, head_buffer=None, git_head=None,
             base_fingerprint=None, source_fingerprint=None, ruler_fingerprint=None)
    f.update(kw)
    return f


def _write_pkls(d: Path, symbols) -> Path:
    d.mkdir()
    rng = np.random.default_rng(7)
    for sym in symbols:
        close = 10 * np.exp(np.cumsum(rng.normal(0, 0.02, len(CAL))))
        pd.DataFrame({"open": close, "high": close * (1 + rng.uniform(0, 0.03, len(CAL))),
                      "low": close * (1 - rng.uniform(0, 0.03, len(CAL))), "close": close, "volume": 1e6},
                     index=pd.DatetimeIndex(CAL, name="date")).to_pickle(d / f"{sym}.pkl")
    return d


def _mk_installed_app(apps: Path, name: str = "demo") -> Path:
    """造一个已接入的 app(main 窗口):study.py + 与之匹配的 classification.json。返回窗口声明目录。"""
    import study_io as S
    d = S.window_dir(name, "main", apps)
    d.mkdir(parents=True)
    study = d / "study.py"
    study.write_text(
        'APP_MODULE = "x.y"\nBASE_YAML = "params.yaml"\nWIDE_OVERRIDES = {}\n'
        'SCAN_GRID = {}\nWHERE_LEVELS = {}\nREF_POINT = {}\n'
        'TIGHT_WHERES = {}\n', encoding="utf-8")
    (d / "classification.json").write_text(json.dumps({
        "app": name, "app_module": "x.y", "base_yaml": "params.yaml",
        "fingerprints": {"study": S.file_sha256(study), "base": "b", "source": {"hash": "s", "files": []}},
    }), encoding="utf-8")
    return d


# ---------------------------------------------------------------- Settings

def test_settings_defaults_match_migrated_values():
    """Settings 默认值:口径与验证旋钮与改造前 apps/bb_v1/run.py 逐项相同;数据目录读配置;预算与筛选四项为新增。"""
    s = tune.Settings()
    assert s.head_buffer == 250
    assert (s.start_date, s.end_date) == ("2024-01-01", "2026-01-01")
    assert (s.label_horizon, s.first_passage_k) == (40, 5.0)
    assert (s.price_min, s.price_max, s.volume_min) == (0.5, 30.0, 10000.0)
    assert s.ticker_regex is None
    assert s.shard_stocks == 200
    assert s.cmp_ticker_regex == r"^[A-Z][A-C]"
    assert (s.cmp_seed, s.cmp_n_random_cells, s.cmp_n_tight_cells) == (11, 64, 12)
    assert s.min_win_bars == 1
    assert (s.fold_col, list(s.folds)) == ("fold_Y", ["2024", "2025"])
    assert s.neighbor_axes == "all"
    assert (s.min_effect_pt, s.min_segments_floor, s.screen_fdr_q, s.noninferiority_pt) == (2.0, 30, 0.10, None)
    assert Path(s.data_dir).is_absolute()
    assert (s.b_boot, s.boot_seed, s.top_n) == (300, 0, 20)
    assert list(s.split_half_seeds) == list(range(20))
    assert s.workers == 16


def test_settings_is_frozen():
    """Settings 不可变:防止某次调用改了它影响后续调用。"""
    s = tune.Settings()
    with pytest.raises(Exception):
        s.head_buffer = 100



# 与 SKILL.md「三、禁止词与人话译法」表逐行对应(该表列出的每个内部机制词都必须能在这里
# 找到能拦住它的条目)——两边任一改动都要同步检查对方,人工维护无自动同步机制。
BANNED = ["MODE=", "MODE", "RUN", "current.py", "run.py", "study.py", "classification.json",
          "run_meta.json", "detection_combos", "HEAD_BUFFER",
          "SCAN_GRID", "WHERE_LEVELS", "REF_POINT", "指纹", "对拍", "长表",
          "mismatch", "三口径", "naive", "optimism", "split-half", "W/F/D/E",
          # 统计与口径的机制词
          "longtable", "cells.npz", "边际", "层匹配", "FP", "置信区间", "工作点", "宽进点", "δ",
          "功效线", "噪声地板", "设计效应", "去簇", "有效样本", "买点事件口径", "逐行口径", "seg_id",
          "单翻转", "两两翻转", "BH", "非劣效", "联合网格", "联合识别", "尺子参数", "退化档", "退化格",
          "差中差", "年交互", "Cochran", "换池", "算术效应", "bootstrap", "入围频率", "赢家诅咒", "选择偏差",
          "确认窗", "holdout", "OOS", "外推窗", "预注册", "preregister", "主确认", "前向核对", "候选配置",
          "回退配置", "决策映射", "族内校正", "provisional", "veto", "depends_on", "exposure", "同窗换股",
          "闸式判定", "条件总体", "登记簿", "对账", "单侧检验", "Westfall", "max-T", "Holm",
          # 两端称呼、阶段编号与内部名
          "学习端", "执行端", "B1", "B2", "B3", "B4", "B5", "validate_backward", "validate_forward",
          "resume_scan", "ask_ruling", "confirm_redo", "gate_family_check",
          # 账本字段名与内部文件名
          "manifest_hash", "extrapolate", "power_notified", "open_low_power", "selects_on", "n_looks",
          "label_horizon", "head_buffer", "stock_rule", "git_head", "base_fingerprint", "source_fingerprint",
          "ruler_fingerprint", "landed_confirmation", "confirm_window",
          "tune.py", "fs.py", "KNOWN_SIGNALS", "adapter.py"]


def test_skill_md_human_templates_contain_no_banned_words():
    """给用户说的话里不得出现内部机制词。

    SKILL.md 的「禁止词与人话译法」一节列出了译法;本测试检查「什么时候停下来问用户」
    一节的人话模板本身干净——那些句子是要原样说给用户听的。
    """
    skill = Path(__file__).resolve().parent / "SKILL.md"
    text = skill.read_text(encoding="utf-8")
    start = text.index("## 二、什么时候停下来问用户")
    end = text.index("## 三、禁止词与人话译法")
    section = text[start:end]
    hits = [w for w in BANNED if w in section]
    assert not hits, f"人话模板里混进了内部机制词: {hits}"


def test_judgment_card_contains_no_banned_words():
    """判据卡是本任务唯一给用户读的产物,整份都该是人话——不摘录切片,全文都要干净。"""
    card = tune.REPO / "docs" / "explain" / "tune-gates_调参判据卡.md"
    text = card.read_text(encoding="utf-8")
    hits = [w for w in BANNED if w in text]
    assert not hits, f"判据卡里混进了内部机制词: {hits}"

# ---------------------------------------------------------------- 单源:δ 与指纹

def test_resolve_delta_ruling_then_settings():
    """δ:账本里最近一条 δ 裁定(点)优先,没有裁定取 Settings;坏的裁定取值响亮报错。"""
    assert tune.resolve_delta("demo") == tune.Settings().min_effect_pt / 100
    assert tune.resolve_delta("demo", tune.Settings(min_effect_pt=3.0)) == 0.03
    tune.record_ruling("demo", "delta", 2.5)
    assert tune.resolve_delta("demo", tune.Settings(min_effect_pt=3.0)) == 0.025
    ledger.append(ledger.make_record("ruling", "demo", **_common(), data={"topic": "delta", "value": -1}))
    with pytest.raises(ValueError, match="不是正数"):
        tune.resolve_delta("demo")


def test_fingerprints_single_source_keeps_values(monkeypatch):
    """四个指纹只有 ledger.fingerprints_for 一份算法:bb_v1 main 窗口上与抽取前的算法逐位相同,
    ledger.current_fingerprints 与 grid_propose.code_fingerprints 都经它算。"""
    import grid_propose
    import study_io as S
    study = S.load_study(S.study_path("bb_v1", "main"))
    mod = S.import_app(study)
    base = S.base_snapshot(mod, study)
    spec = mod.build_pattern(mod.Params.from_dict(base, strict=True))
    before = {"git_head": S._git_head(), "base_fingerprint": S.canonical_hash(base),
              "source_fingerprint": S.source_fingerprint(S.source_files(mod, spec))["hash"],
              "ruler_fingerprint": ledger.ruler_fingerprint()}
    assert ledger.current_fingerprints("bb_v1", "main") == before
    assert grid_propose.code_fingerprints(mod, base) == before
    calls = []
    monkeypatch.setattr(ledger, "fingerprints_for", lambda m, b: calls.append((m, b)) or {"marker": 1})
    assert ledger.current_fingerprints("bb_v1", "main") == {"marker": 1}
    assert grid_propose.code_fingerprints(mod, base) == {"marker": 1}
    assert calls == [(mod, base), (mod, base)]


# ---------------------------------------------------------------- 状态、开局、裁定

def test_status_is_stage_derivation(monkeypatch):
    calls = []
    fake = types.ModuleType("stages")
    fake.derive = lambda app, **kw: calls.append((app, kw)) or {"app": app, "next": {"action": "x"}}
    monkeypatch.setitem(sys.modules, "stages", fake)
    cfg = tune.Settings(b_boot=7)
    assert tune.status("demo", cfg=cfg) == {"app": "demo", "next": {"action": "x"}}
    assert calls == [("demo", {"cfg": cfg})]


def test_open_round_probes_data_files_and_writes_open(tmp_path):
    """机械闸 7:确认窗从数据文件实际覆盖推出;这一轮两段没验证完不许重划,验证完才能开下一轮。"""
    data = _write_pkls(tmp_path / "pkls", ("AAA", "BBB", "CCC"))
    cfg = tune.Settings(data_dir=str(data))
    out = tune.open_round("demo", cfg=cfg)
    cal = holdout.trading_calendar(data)
    end = cal[cal <= pd.Timestamp(cfg.end_date)][-1]
    expected = holdout.confirm_windows(cfg.start_date, end, calendar=cal, head_buffer=cfg.head_buffer,
                                       horizon=cfg.label_horizon)
    rec = ledger.read("demo")[-1]
    assert rec["kind"] == "open" and rec["data"] == {**expected, "n_probed": 3}
    assert rec["window"] == {"start": cfg.start_date, "end": str(end.date())}
    assert (rec["label_horizon"], rec["head_buffer"]) == (cfg.label_horizon, cfg.head_buffer)
    assert out["confirm"] == expected["confirm"] and out["n_probed"] == 3 and out["record"] == rec
    with pytest.raises(SystemExit, match="开局核对"):
        tune.open_round("demo", cfg=cfg)
    for cw in ledger.CONFIRM_NAMES:
        seg = expected["confirm"][cw]
        ledger.append(ledger.make_record(
            "extrapolate", "demo", **_common(window={"start": seg["start"], "end": seg["end"]},
                                             label_horizon=cfg.label_horizon, head_buffer=cfg.head_buffer),
            n_looks=1, data={"manifest_hash": "h", "confirm_window": cw, "results": {}}))
    tune.open_round("demo", cfg=cfg)
    assert [r["kind"] for r in ledger.read("demo")].count("open") == 2


def test_record_ruling_writes_and_rejects():
    rec = tune.record_ruling("demo", "power_notified", True, manifest_hash="abc", note="已告知")
    assert ledger.read("demo")[-1] == rec
    assert rec["data"] == {"topic": "power_notified", "value": True, "manifest_hash": "abc"} and rec["note"] == "已告知"
    with pytest.raises(SystemExit, match="清单哈希"):
        tune.record_ruling("demo", "open_low_power", True)
    with pytest.raises(SystemExit, match="正数"):
        tune.record_ruling("demo", "delta", 0)
    with pytest.raises(ValueError, match="topic"):
        tune.record_ruling("demo", "nope", 1)
    assert tune.record_ruling("demo", "delete_gate", {"b.g": 0})["data"]["value"] == {"b.g": 0}
    assert tune.record_ruling("demo", "delete_gate", None)["data"]["value"] is None       # 决定不删
    for bad in ("b.g", {"feature:x": 0}, {"nodot": 0}):
        with pytest.raises(SystemExit, match="删闸裁定"):
            tune.record_ruling("demo", "delete_gate", bad)
    assert len(ledger.read("demo")) == 3


# ---------------------------------------------------------------- 接线:优势检查、定范围、落地

def test_edge_wiring(tmp_path, monkeypatch):
    """放开值缺省取最近写过的窗口声明;δ 取裁定;m 预估 = 2 ×(检测参数个数 × 2 + 在役闸数),不看建议档给没给出。"""
    import edge as E
    import grid_propose as G
    import study_io as S
    apps = tmp_path / "apps"
    for i, (w, wide) in enumerate((("old", {"b": {"g": 1}}), ("new", {"b": {"g": 0}}))):
        p = S.study_path("demo", w, apps)
        p.parent.mkdir(parents=True)
        p.write_text(f"APP_MODULE = 'x'\nBASE_YAML = 'params.yaml'\nWIDE_OVERRIDES = {wide!r}\nSCAN_GRID = {{}}\n"
                     "WHERE_LEVELS = {}\nREF_POINT = {}\nTIGHT_WHERES = {}\n", encoding="utf-8")
        os.utime(p, (1_000_000 + i, 1_000_000 + i))
    monkeypatch.setattr(S, "APPS_DIR", apps)
    calls = []
    admission = {"a.x": {"kind": "D", "category": "检测参数"}, "a.y": {"kind": "D", "category": "检测参数"},
                 "a.r": {"kind": "D", "category": "尺子"}, "b.g": {"kind": "W", "category": G.CAT_IN_SERVICE},
                 "b.h": {"kind": "W", "category": G.CAT_NEW}, "b.k": {"kind": "F", "category": G.CAT_USEFUL}}
    monkeypatch.setattr(G, "propose_ranges", lambda app, module, **kw: calls.append(("ranges", app, module, kw)) or {
        "screen_design": {"alts": {"a.x": [1]}}, "admission": admission})     # 样本少时建议档不全,不影响预估
    monkeypatch.setattr(E, "run", lambda app, cfg, **kw: calls.append(("run", app, cfg, kw)) or {
        "report": "edge_report.md", "verdicts": {"working": {"pooled": "有边际"}}, "source_note": None, "record": {}})
    tune.record_ruling("demo", "delta", 3)
    cfg = tune.Settings(b_boot=40, boot_seed=2)
    out = tune.edge("demo", cfg=cfg, restart=True)
    assert calls[0] == ("ranges", "demo", "path2_apps.demo.dag_spec", {"cfg": cfg})
    assert calls[1] == ("run", "demo", cfg, {"wide_overrides": {"b": {"g": 0}}, "delta": 0.03, "m": 2 * (2 * 2 + 2),
                                             "B": 40, "seed": 2, "restart": True})
    assert out == {"report": "edge_report.md", "verdicts": {"working": {"pooled": "有边际"}}, "source_note": None,
                   "delta": 0.03, "m_estimate": {"m": 12, "detect_params": 2, "gates_in_service": 2}}
    tune.edge("demo", wide_overrides={"b": {"g": 5}}, cfg=cfg)
    assert calls[-1][3]["wide_overrides"] == {"b": {"g": 5}}
    monkeypatch.setattr(S, "APPS_DIR", tmp_path / "empty")
    with pytest.raises(SystemExit, match="放开值"):
        tune.edge("demo", cfg=cfg)


def test_propose_install_adopt_wiring(monkeypatch):
    import adopt
    import grid_propose as G
    calls = []
    monkeypatch.setattr(G, "propose_ranges", lambda *a, **kw: calls.append(("ranges", a, kw)) or {"legality": {}})
    monkeypatch.setattr(G, "install_study", lambda *a, **kw: calls.append(("install", a, kw)) or {"design": "screen"})
    monkeypatch.setattr(adopt, "adopt", lambda *a, **kw: calls.append(("adopt", a, kw)) or {"written": False})
    cfg = tune.Settings(head_buffer=30)
    assert tune.propose_ranges("demo", cfg=cfg) == {"legality": {}}
    assert tune.install("demo", window="s1", stage="screen", wide_overrides={"b": {"g": 0}},
                        scan_grid={("a", "x"): [1, 2]}, where_levels={}, cfg=cfg) == {"design": "screen"}
    assert tune.adopt("demo", window="j1", changes={"a.x": 2}, provisional=True, verified=False, selects_on=["a.x"],
                      depends_on={}, reason="联合识别选中", validation={"manifest_hash": "h"}) == {"written": False}
    assert calls == [
        ("ranges", ("demo", "path2_apps.demo.dag_spec"), {"base_yaml": "params.yaml", "cfg": cfg, "sample_stocks": 200}),
        ("install", ("demo",), {"window": "s1", "stage": "screen", "app_module": "path2_apps.demo.dag_spec",
                                "base_yaml": "params.yaml", "wide_overrides": {"b": {"g": 0}},
                                "scan_grid": {("a", "x"): [1, 2]}, "where_levels": {}, "tight_wheres": {},
                                "cfg": cfg, "apps_dir": None}),
        ("adopt", ("demo",), {"window": "j1", "changes": {"a.x": 2}, "provisional": True, "verified": False,
                              "selects_on": ["a.x"], "depends_on": {}, "reason": "联合识别选中", "confirm": False,
                              "validation": {"manifest_hash": "h"}})]


def test_setup_regenerates_classification(tmp_path, monkeypatch):
    import study_io as S
    apps = tmp_path / "apps"
    p = S.study_path("demo", "w1", apps)
    p.parent.mkdir(parents=True)
    p.write_text("# 研究声明\n", encoding="utf-8")
    cl = {"design": "grid", "kinds": {}, "filter_fields": {}, "where_fields": {}, "end_node": "e", "bound_nodes": [],
          "detection_combos": 1, "fingerprints": {"source": {"files": ["f.py"]}}}
    calls = []
    monkeypatch.setattr(S, "load_study", lambda path: "study")
    monkeypatch.setattr(S, "import_app", lambda study: "mod")
    monkeypatch.setattr(S, "build_classification", lambda *a: calls.append(("build", a)) or cl)
    monkeypatch.setattr(S, "write_classification", lambda *a, **kw: calls.append(("write", a, kw)))
    out = tune.setup("demo", window="w1", apps_dir=apps)
    assert calls == [("build", ("demo", "w1", "study", "mod", p)), ("write", ("demo", "w1", cl), {"apps_dir": apps})]
    assert out["design"] == "grid" and out["source_files"] == ["f.py"]
    with pytest.raises(SystemExit, match="不存在"):
        tune.setup("demo", window="w2", apps_dir=apps)


def test_retire_dry_run_returns_plan_without_deleting(tmp_path):
    """confirm=False 只返回清单,一个文件都不能少。"""
    apps = tmp_path / "apps"
    _mk_installed_app(apps)
    (apps / "demo" / "notes.md").write_text("# notes\n", encoding="utf-8")
    # _execute_delete 无论 confirm 取值都先查 _worktree_dirty(app_setup.py 的既有行为),该函数要求 app_dir
    # 能被 git 发现所属仓库,故 tmp_path 需先 git init;不需要 commit——status --porcelain 不依赖 identity 配置。
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    before = sorted(str(p) for p in (apps / "demo").rglob("*"))
    plan = tune.retire("demo", confirm=False, apps_dir=apps, repo=tmp_path)
    assert {Path(x["path"]).name for x in plan["must"]} >= {"study.py", "classification.json"}
    assert "notes.md" in {Path(x["path"]).name for x in plan["keep"]}
    assert sorted(str(p) for p in (apps / "demo").rglob("*")) == before      # 一个都没删


def test_retire_refuses_unknown_app(tmp_path):
    with pytest.raises(SystemExit):
        tune.retire("nope", confirm=False, apps_dir=tmp_path / "apps", repo=tmp_path)


# ---------------------------------------------------------------- 接线:扫描、核对、识别

def test_scan_and_compare_wiring(tmp_path, monkeypatch):
    import compare_longtable
    import multivar_scan
    monkeypatch.setattr(tune, "REPO", tmp_path)
    calls = []

    def fake_scan(app, cfg, out_dir, *, label_mode):
        calls.append(("scan", app, out_dir, label_mode, cfg.ticker_regex))
        lt = tmp_path / out_dir / "longtable"
        lt.mkdir(parents=True)
        (lt / "run_meta.json").write_text(json.dumps({"label_mode": "deferred"}), encoding="utf-8")
        (lt / "part-0000.parquet").write_bytes(b"")

    def fake_compare(app, cfg, longtable_dir):
        calls.append(("compare", app, longtable_dir, cfg.cmp_seed))
        (tmp_path / longtable_dir).parent.joinpath("compare_longtable.log").write_text(
            "study_fingerprint=x ruler_fingerprint=y\n对拍 80 股×格(10 只有效股 × 8 项),mismatch=0,1s;"
            "compared_symbols=10 sampled_symbols=10 universe_symbols=10\n", encoding="utf-8")

    monkeypatch.setattr(multivar_scan, "run", fake_scan)
    monkeypatch.setattr(compare_longtable, "run", fake_compare)
    out = tune.scan("demo", window="w1", ticker_regex="^A")
    assert out == {"app": "demo", "window": "w1", "out_dir": str(tmp_path / "outputs/tune_gates/demo/w1"),
                   "label_mode": "deferred", "n_shards": 1}         # 返回实际模式(扫描区间碰到留出数据时被改走)
    res = tune.compare("demo", window="w1", cmp_seed=3)
    assert calls == [("scan", "demo", "outputs/tune_gates/demo/w1", "full", "^A"),
                     ("compare", "demo", "outputs/tune_gates/demo/w1/longtable", 3)]
    assert res["mismatch"] == 0 and res["log"].endswith("compare_longtable.log")


def test_screen_find_cell_wiring(tmp_path, monkeypatch):
    """筛选 / 联合识别的 δ 取裁定;联合识别不再有跳过一致性验证的开关;单格查询的键是参数键。"""
    import region_find
    import screen
    monkeypatch.setattr(tune, "REPO", tmp_path)
    calls = []
    monkeypatch.setattr(screen, "run", lambda app, window, cfg, **kw: calls.append(("screen", app, window, kw))
                        or {"survivors": ["a.x"]})
    monkeypatch.setattr(region_find, "run", lambda app, cfg, lt, **kw: calls.append(("find", app, lt, kw))
                        or {"verdict": "稳健"})
    monkeypatch.setattr(region_find, "cell_query", lambda app, window, levels, **kw: calls.append(
        ("cell", app, window, levels, kw)) or {"count_unit": "event"})
    assert tune.screen("demo", window="s1", working_point={"b.g": 0}) == {"survivors": ["a.x"]}
    tune.record_ruling("demo", "delta", 2.5)
    assert tune.find("demo", window="j1") == {"verdict": "稳健"}
    assert tune.cell("demo", window="j1", note="看现值", **{"a.x": 1, "b.g": None}) == {"count_unit": "event"}
    assert calls == [("screen", "demo", "s1", {"delta": 0.02, "working_point": {"b.g": 0}}),
                     ("find", "demo", str(tmp_path / "outputs/tune_gates/demo/j1/longtable"), {"delta": 0.025}),
                     ("cell", "demo", "j1", {"a.x": 1, "b.g": None}, {"note": "看现值"})]
    with pytest.raises(TypeError):
        tune.find("demo", window="j1", force=True)


# ---------------------------------------------------------------- 冻结验证清单

PRE_CL = {"app": "demo", "window": "j1", "design": "grid", "ref_point_scope": "all", "app_module": "x.dag_spec",
          "base_yaml": "params.yaml", "kinds": {"det.th": "D", "det.span": "D", "gate.n": "F", "gate.age": "W"},
          "scan_grid": {"det.th": [1, 2, 3], "det.span": [5, 10], "gate.n": [1, 2]},
          "where_levels": {"gate.age": [0, 60]}, "filter_fields": {"gate.n": ["g", "count", ">="]},
          "where_fields": {"gate.age": ["g", "age", ">="]}, "wide_overrides": {"gate": {"age": 0, "n": 1}},
          "ref_point": {"det.th": 2, "det.span": 10, "gate.n": 2, "gate.age": 60}}


def test_preregister_wiring(monkeypatch):
    """展开决策映射(非劣效界取 Settings)+ 闸子族有闸才并 + 预期把握 + 幸存者偏差 → 写 preregister;
    把握不足一半时只在返回里标明要先问用户,不代写「照样打开」的裁定。"""
    import study_io as S
    monkeypatch.setattr(S, "load_classification", lambda app, window, *a, **kw: PRE_CL)
    monkeypatch.setattr(ledger, "current_fingerprints", lambda app, window: dict(FPS))
    monkeypatch.setattr(tune, "_formal", lambda cl: {"det.th": 2, "det.span": 10, "gate.n": 2, "gate.age": 60})
    ledger.append(ledger.make_record(
        "select", "demo", **_common(window={"start": "2024-01-01", "end": "2025-12-31"}, label_horizon=HZ,
                                    head_buffer=HB), n_looks=5,
        data={"tool": "find", "window_name": "j1", "optimism": 0.004}))
    rng = np.random.default_rng(0)
    symbols = np.array([f"S{i:04d}" for i in range(400)], dtype=object)
    seen = {}

    def train_sums(app, window, cl, configs, cfg, background):
        seen["train"] = (app, window, configs, background)
        rate = [0.50 + 0.08 * (c["det.th"] == 3) + 0.005 * (c["gate.age"] == 0) for c in configs]
        D = rng.poisson(40, (len(symbols), len(configs)))
        return rng.binomial(D, rate), D, D + 4, np.full(len(configs), 2000), symbols, {"end_date": "2026-01-01"}

    win_events = {"n": 2000}
    monkeypatch.setattr(tune, "_train_sums", train_sums)
    monkeypatch.setattr(tune, "_window_events", lambda app, cw, decl, configs, cfg: seen.setdefault("win", []).append(
        (cw, decl, configs)) or dict.fromkeys(configs, win_events["n"]))
    monkeypatch.setattr(tune, "_price_after_train", lambda syms, data_dir, end: (
        pd.Series(np.where(np.arange(len(syms)) < 20, 0.5, 10.0), index=syms),
        pd.Series(np.linspace(-0.9, 0.5, len(syms)), index=syms)))
    families = [{"gates": [{"param": "gate.n"}], "features": None}, None]
    monkeypatch.setattr(tune, "_gate_family", lambda app, window, changes, extra: seen.setdefault("gf", []).append(
        (window, changes, extra)) or families.pop(0))

    out = tune.preregister("demo", changes={"det.th": 3, "gate.age": 0}, extra=[{"param": "gate.n", "cuts": [2]}])
    rec = ledger.read("demo")[-1]
    m = rec["data"]["manifest"]
    assert rec["kind"] == "preregister" and out["record"] == rec and out["manifest_hash"] == rec["data"]["manifest_hash"]
    assert m["train_window"] == "j1" and seen["train"][1] == "j1" and seen["train"][3] == PRE_CL["ref_point"]
    assert {c["key"]: c["kind"] for c in m["family"]["changes"]} == {"det.th": "detect", "gate.age": "delete_gate"}
    assert m["family"]["delta"] == tune.Settings().min_effect_pt / 100 and m["B"] == tune.Settings().b_boot
    assert m["family"]["strength_order"] == ["det.th", "gate.age"]
    assert m["confirm_scan"] == {"app_module": "x.dag_spec", "base_yaml": "params.yaml",
                                 "wide_overrides": {"gate": {"age": 0, "n": 1}},
                                 "scan_grid": {"det.th": [2, 3], "gate.n": [1, 2]}, "where_levels": {"gate.age": [0, 60]}}
    assert [w[0] for w in seen["win"]] == ["backward", "forward"]
    assert all(w[1] == m["confirm_scan"] and w[2] == m["family"]["configs"] for w in seen["win"])
    assert m["gate_family"] == {"gates": [{"param": "gate.n"}], "features": None} and out["gate_family"] is True
    assert seen["gf"][0] == ("j1", {"det.th": 3, "gate.age": 0}, [{"param": "gate.n", "cuts": [2]}])
    assert m["expected_power"]["optimism"] == 0.004 and m["fingerprints"] == FPS
    h1 = m["family"]["hypotheses"][0]
    assert (h1["a"], h1["b"]) == ("K", "base") and m["train_est"][h1["id"]] > 0.05
    assert isinstance(m["survivorship"]["flag"], bool)
    assert out["needs_user_consent"] is False and min(out["expected_power"].values()) >= 0.5

    win_events["n"] = 5                                       # 确认窗买点事件很少 → 窗口误差大、把握不足
    out = tune.preregister("demo", changes={"det.th": 3, "gate.age": 0}, window="j1")
    m = ledger.read("demo")[-1]["data"]["manifest"]
    assert "gate_family" not in m and out["gate_family"] is False
    assert out["needs_user_consent"] is True and "先问用户" in out["text"]
    assert not [r for r in ledger.read("demo") if r["kind"] == "ruling"]

    with pytest.raises(SystemExit, match="不在这个窗口的网格上"):
        tune.preregister("demo", changes={"nope.x": 1}, window="j1")
    with pytest.raises(SystemExit, match="就是工作点的取值"):
        tune.preregister("demo", changes={"det.th": 2}, window="j1")


PRE_CL_OLD = {**PRE_CL, "ref_point_scope": "D", "ref_point": {"det.th": 3, "det.span": 10}}


def test_preregister_landed_decision_on_old_window(monkeypatch):
    """已落地定案的事后验证:新值等于正式值且最近一条定案的新值就是它 → 改前值取定案前的值;
    工作点只写了检测参数的旧窗口,闸的现值取正式参数落到档位上,落不到或改前值不在档位上 → 人话拒绝。"""
    import study_io as S
    formal = {"det.th": 3, "det.span": 10, "gate.n": 2, "gate.age": 60}
    monkeypatch.setattr(S, "load_classification", lambda app, window, *a, **kw: PRE_CL_OLD)
    monkeypatch.setattr(ledger, "current_fingerprints", lambda app, window: dict(FPS))
    monkeypatch.setattr(tune, "_formal", lambda cl: dict(formal))

    def decide(params):
        ledger.append(ledger.make_record("decide", "demo", **_common(), axes=sorted(params), data={
            "params": params, "selects_on": sorted(params), "provisional": True, "depends_on": {}}), check_refs=False)

    decide({"det.th": [2, 3]})
    rng = np.random.default_rng(1)
    symbols = np.array([f"S{i:04d}" for i in range(300)], dtype=object)
    seen = {}

    def train_sums(app, window, cl, configs, cfg, background):
        seen["train"] = (configs, background)
        rate = [0.50 + 0.08 * (c["det.th"] == 3) + 0.01 * (c["gate.age"] == 0) for c in configs]
        D = rng.poisson(40, (len(symbols), len(configs)))
        return rng.binomial(D, rate), D, D + 4, np.full(len(configs), 2000), symbols, {"end_date": "2026-01-01"}

    monkeypatch.setattr(tune, "_train_sums", train_sums)
    monkeypatch.setattr(tune, "_window_events", lambda app, cw, decl, configs, cfg: dict.fromkeys(configs, 2000))
    monkeypatch.setattr(tune, "_price_after_train", lambda syms, data_dir, end: (
        pd.Series(10.0, index=syms), pd.Series(np.linspace(-0.5, 0.5, len(syms)), index=syms)))
    monkeypatch.setattr(tune, "_gate_family", lambda app, window, changes, extra: None)

    tune.preregister("demo", changes={"det.th": 3, "gate.age": 0}, window="j1")
    m = ledger.read("demo")[-1]["data"]["manifest"]
    assert {c["key"]: (c["old"], c["new"]) for c in m["family"]["changes"]} == {"det.th": (2, 3), "gate.age": (60, 0)}
    assert (m["family"]["configs"]["base"], m["family"]["configs"]["K"]) == (
        {"det.th": 2, "gate.age": 60}, {"det.th": 3, "gate.age": 0})
    assert seen["train"][1] == {"det.th": 3, "det.span": 10, "gate.n": 2, "gate.age": 60}
    assert m["confirm_scan"]["scan_grid"]["det.th"] == [2, 3]

    formal["gate.n"] = 5                                        # 闸的正式值落不到旧窗口的档位上
    with pytest.raises(SystemExit, match="落不到档位上"):
        tune.preregister("demo", changes={"det.th": 3, "gate.age": 0}, window="j1")
    formal["gate.n"] = 2
    decide({"det.th": [7, 3]})                                  # 定案前的值不在训练窗口的档位上
    with pytest.raises(SystemExit, match="改前值 7"):
        tune.preregister("demo", changes={"det.th": 3, "gate.age": 0}, window="j1")
    decide({"det.th": [3, 1]})                                  # 最近一条定案不是它:按工作点算,不算改动
    with pytest.raises(SystemExit, match="就是工作点的取值"):
        tune.preregister("demo", changes={"det.th": 3}, window="j1")


def test_record_discovery(tmp_path):
    rec = tune.record_discovery("demo", fc=["FC-011"], axes=["burst.peak_age_min", "feature:atr_pct_20"],
                                window={"start": "2024-01-01", "end": "2025-12-31"}, note="筛选草稿确认登记")
    assert ledger.read("demo")[-1] == rec and rec["kind"] == "discover" and rec["n_looks"] == 1
    assert rec["ref"] == {tune.REGISTRY: ledger.sha256_file(ledger.REPO / tune.REGISTRY)}
    assert rec["label_horizon"] == tune.Settings().label_horizon and rec["note"] == "筛选草稿确认登记"
    doc = tmp_path / "draft.md"
    doc.write_text("草稿\n", encoding="utf-8")
    rec = tune.record_discovery("demo", fc=["FC-012"], axes=["b.g"], window={"start": "2024-01-01", "end": "2024-06-30"},
                                note="x", ref={str(doc): ledger.sha256_file(doc)}, label_horizon=20)
    assert rec["ref"] == {str(doc): ledger.sha256_file(doc)} and rec["label_horizon"] == 20
    with pytest.raises(SystemExit, match="轴名"):
        tune.record_discovery("demo", fc=["FC-013"], axes=["nodot"], window={"start": "2024-01-01", "end": "2024-02-01"},
                              note="x")
    with pytest.raises(ValueError, match="fc"):
        tune.record_discovery("demo", fc=[], axes=["b.g"], window={"start": "2024-01-01", "end": "2024-02-01"}, note="x")
    assert [r["kind"] for r in ledger.read("demo")] == ["discover", "discover"]


def test_validation_source_only_when_both_windows_opened():
    """两段都开完才给出定案记验证结论要的出处;只认这份清单的开窗记录。"""
    def opened(cw, h, ts):
        rec = ledger.make_record("extrapolate", "demo", **_common(window={"start": "2026-03-02", "end": "2026-06-18"},
                                                                  label_horizon=HZ), n_looks=1,
                                 data={"manifest_hash": h, "confirm_window": cw, "results": {}})
        rec["ts"] = ts
        ledger.append(rec)

    opened("forward", "h1", "2026-09-01T10:00:00")
    opened("backward", "h0", "2026-09-01T11:00:00")
    assert tune._validation("demo", "h1") is None
    opened("backward", "h1", "2026-09-02T10:00:00")
    assert tune._validation("demo", "h1") == {"manifest_hash": "h1", "extrapolate": {
        "backward": "2026-09-02T10:00:00", "forward": "2026-09-01T10:00:00"}}


def test_gate_family_merges_only_when_nonempty(monkeypatch):
    plans = [{"gates": [], "features": None}, {"gates": [{"param": "b.g"}], "features": None}]
    calls = []
    fake = SimpleNamespace(plan=lambda app, window, **kw: calls.append((app, window, kw)) or plans.pop(0))
    monkeypatch.setattr(tune, "_feature_study", lambda: fake)
    assert tune._gate_family("demo", "j1", {"a.x": 2}) is None
    assert tune._gate_family("demo", "j1", {"a.x": 2}) == {"gates": [{"param": "b.g"}], "features": None}
    assert calls[0] == ("demo", "j1", {"extra": None, "config": {"a.x": 2}, "in_round": True})
    plans.append({"gates": [], "features": {"features": ["f1"]}})           # 只有同批特征也并
    extra = [{"features": ["f1"], "csv": "d.csv"}]
    assert tune._gate_family("demo", "j1", {"a.x": 2}, extra) == {"gates": [], "features": {"features": ["f1"]}}
    assert calls[-1][2]["extra"] == extra


def test_feature_study_loaded_by_path_shares_delta():
    """学习端模块按文件路径加载;它的 δ 与这里同一个取法。"""
    fs = tune._feature_study()
    assert Path(fs.__file__).resolve() == tune.FEATURE_STUDY_FS.resolve()
    tune.record_ruling("demo_fs", "delta", 1.5)
    assert fs.resolve_delta("demo_fs") == tune.resolve_delta("demo_fs") == 0.015


# ---------------------------------------------------------------- 确认窗取数:合成 app 端到端
@dataclass(frozen=True)
class SynPt(Event):
    pass


@dataclass(frozen=True)
class SynSeg(Event):
    length: int = 0
    depth: int = 0


class SynPtDet:
    event_cls = SynPt

    def __init__(self, step):
        self.step = step

    def detect(self, df):
        return iter([SynPt(p, p, confirm_idx=p) for p in range(3, len(df) - 5, self.step)])


class SynSegDet:
    """每 7 根起一段:段长 2 + k%4、深度 k%5(k = 段序号);min_len 只在出口把关(过滤型)。"""
    event_cls = SynSeg
    filter_params = {"min_len": ("length", ">=")}

    def __init__(self, min_len):
        self.min_len = min_len

    def detect(self, df):
        out = []
        for k, p in enumerate(range(5, len(df) - 5, 7)):
            n = 2 + k % 4
            if n >= self.min_len:
                out.append(SynSeg(p, p + n - 1, confirm_idx=p + n - 1, length=n, depth=k % 5))
        return iter(out)


DEFAULTS = {"a": {"step": 11}, "b": {"min_len": 2, "depth_min": 3}}


class Params:
    def __init__(self, d):
        self.d = d

    @classmethod
    def from_dict(cls, d, strict=True):
        return cls(copy.deepcopy(d))

    @classmethod
    def from_yaml(cls, path):
        return cls(copy.deepcopy(DEFAULTS))

    def to_dict(self):
        return copy.deepcopy(self.d)


def build_pattern(p):
    d = p.d
    return PatternSpec(pattern_id="syn_tune",
                       nodes=(NodeSpec("A", detector=SynPtDet(d["a"]["step"])),
                              NodeSpec("B", detector=SynSegDet(d["b"]["min_len"]),
                                       where=(("depth", Wh.attr("depth", ">=", d["b"]["depth_min"])),))),
                       edges=(TemporalEdge("A", "B", min_gap=0, max_gap=5),))


def eval_meta(params=None):
    return {"end_node": "B", "head_buffer_trading_days": 0}


SYN = "syn"
WIDE = {"b": {"min_len": 1, "depth_min": 0}}
DECL = {"app_module": __name__, "base_yaml": "params.yaml", "wide_overrides": WIDE,
        "scan_grid": {"a.step": [11, 13], "b.min_len": [1, 2]}, "where_levels": {"b.depth_min": [0, 3]}}


def _pin_apps_dir(monkeypatch, apps: Path):
    """研究声明根目录指到 tmp(扫描与补算标签内部按缺省根目录找声明,只能在这里钉住)。"""
    import study_io as S
    monkeypatch.setattr(S, "APPS_DIR", apps)
    for fn, n_pos in (("window_dir", 2), ("study_path", 2), ("load_classification", 2), ("write_classification", 3)):
        orig = getattr(S, fn)
        monkeypatch.setattr(S, fn, lambda *a, _o=orig, _n=n_pos, **kw: _o(*a[:_n], apps_dir=apps))


@pytest.fixture
def syn(tmp_path, monkeypatch):
    import multivar_scan as MS
    import validate as V
    monkeypatch.setattr(holdout, "default_calendar", lambda: CAL)
    monkeypatch.setattr(tune, "REPO", tmp_path)
    monkeypatch.setattr(MS, "REPO", tmp_path)
    _pin_apps_dir(monkeypatch, tmp_path / "apps")
    data = _write_pkls(tmp_path / "pkls", ("AAA", "BBB", "CCC", "DDD", "EEE", "FFF"))
    cfg = tune.Settings(data_dir=str(data), head_buffer=30, label_horizon=HZ, first_passage_k=1.0, price_max=100.0,
                        volume_min=1000.0, shard_stocks=2, workers=2, b_boot=50)
    w = holdout.confirm_windows("2024-01-01", "2025-12-31", calendar=CAL, head_buffer=HB, horizon=HZ)
    ledger.append(ledger.make_record("open", SYN, **_common(window={"start": "2024-01-01", "end": "2025-12-31"},
                                                            label_horizon=HZ, head_buffer=HB),
                                     data={**w, "n_probed": 6}))
    fam = V.expand_family([V.Change("a.step", 11, 13, "detect", 3.0), V.Change("b.depth_min", 3, 0, "delete_gate", 1.0)],
                          delta=0.02)
    manifest = {"family": fam, "train_est": {h["id"]: 0.03 for h in fam["hypotheses"]}, "alpha": 0.05,
                "method": "maxT", "B": 50, "seed": 0, "expected_power": {"backward": 0.8, "forward": 0.8},
                "survivorship": {"flag": False, "text": ""},
                "fingerprints": ledger.fingerprints_for(sys.modules[__name__], {"a": {"step": 11}, **WIDE}),
                "round": None, "train_window": "train", "confirm_scan": DECL,
                "gate_family": {"gates": [{"param": "b.min_len", "column": "B.length"}], "features": None}}
    h = V.manifest_hash(manifest)
    rec = ledger.make_record("preregister", SYN, **_common(), axes=["a.step", "b.depth_min"], data={
        "manifest_hash": h, "manifest": manifest, "expected_power": manifest["expected_power"],
        "survivorship": manifest["survivorship"]})
    rec["ts"] = PAST
    ledger.append(rec)
    tune.record_ruling(SYN, "power_notified", True, manifest_hash=h)
    return SimpleNamespace(tmp=tmp_path, cfg=cfg, confirm=w["confirm"], manifest=manifest, hash=h)


def test_confirm_rows_guards_itself_before_reading(syn, monkeypatch):
    """学习端的确认窗取数口自己过守卫:这份清单在这段还没开过窗 → 拒绝,一行都不读。"""
    import multivar_scan as MS
    read = []
    monkeypatch.setattr(MS, "read_with_labels", lambda *a, **kw: read.append(a) or iter(()))
    with pytest.raises(holdout.HoldoutLocked) as e:
        tune.confirm_rows(SYN, "forward", {"a.step": 13}, ["B.length"])
    assert e.value.reason == "gate_family_refused" and read == []

def test_validate_deferred_window_sums_equal_full_label_scan(syn, monkeypatch):
    """确认窗取数:延迟标签扫描 → 过守卫补算标签 → 逐片接标签按买点事件口径汇总,每个配置格的每股 U/D/N 与同一合成
    数据上完整标签模式直接扫出来的逐位相等;学习端的确认窗取数口与完整标签模式的行一致。"""
    import grid_propose as G
    import multivar_scan as MS
    import region_core as RC
    import study_io as S
    captured = {}
    orig = tune._window_sums

    def spy(*a, **kw):
        res = orig(*a, **kw)
        captured.update(res)
        return res

    monkeypatch.setattr(tune, "_window_sums", spy)
    ledger.append(ledger.make_record("preregister", SYN, **_common(), data={    # 学习端轮外单独冻结的闸清单:不挡开窗
        "manifest_hash": "gates-only", "manifest": {"gate_family": {"gates": [{"param": "b.min_len"}]}},
        "expected_power": {"backward": 0.0, "forward": 0.0}, "survivorship": {"checked": False}}))
    out = tune.validate(SYN, confirm_window="forward", cfg=syn.cfg)
    assert out["manifest_hash"] == syn.hash and "训练期之后" in out["text"] and out["validation"] is None
    ext = [r for r in ledger.read(SYN) if r["kind"] == "extrapolate"]
    assert len(ext) == 1 and ext[0]["data"]["confirm_window"] == "forward"
    configs = syn.manifest["family"]["configs"]
    assert set(captured) == set(configs)
    with pytest.raises(holdout.HoldoutLocked, match="打开过一次"):
        tune.validate(SYN, confirm_window="forward", cfg=syn.cfg)

    seg = syn.confirm["forward"]
    G.install_study(SYN, window="ref_full", stage="grid", app_module=__name__, base_yaml="params.yaml",
                    wide_overrides=WIDE, scan_grid={("a", "step"): [11, 13], ("b", "min_len"): [1, 2]},
                    where_levels={("b", "depth_min"): [0, 3]}, tight_wheres={}, cfg=syn.cfg)
    monkeypatch.setattr(holdout, "guard_label_access", lambda *a, **kw: None)   # 对照组:完整标签模式直接算
    MS.run(SYN, replace(syn.cfg, start_date=seg["start"], end_date=seg["end"]), "outputs/tune_gates/syn/ref_full",
           label_mode="full")
    ref_out = syn.tmp / "outputs/tune_gates/syn/ref_full"
    committed = MS.committed_shards(ref_out)
    shards = [p for p in sorted((ref_out / "longtable").glob("part-*.parquet")) if p.name in committed]
    combo, preds = S.derived_axes(S.load_classification(SYN, "ref_full"))
    prep = RC.prepare_shards(shards, combo, preds, "fold_Y", ["all"], segment_cols=["seg_id"],
                             fold_from=("buy_date", lambda s: np.full(len(s), "all", dtype=object)))
    cells = [RC.cell_index(combo, preds, {"a.step": c["a.step"], "B.length": 2, "B.depth": c["b.depth_min"]})
             for c in configs.values()]
    U, D, N = RC.stock_sums(prep, cells, fold_mode="pooled")
    for j, name in enumerate(configs):
        ref = pd.DataFrame({"U": U[:, j, 0], "D": D[:, j, 0], "N": N[:, j, 0]},
                           index=pd.Index(prep.symbols, name="symbol"))
        pd.testing.assert_frame_equal(captured[name], ref)
    assert captured["K"]["D"].sum() > 0 and captured["base"]["D"].sum() > 0
    assert not captured["K"].equals(captured["base"])

    rows = tune.confirm_rows(SYN, "forward", {"a.step": 13}, ["B.length", "B.depth", "Z.absent"])
    assert list(rows.columns) == ["symbol", "date", "year", "seg_id", "B.length", "B.depth", "M", "c0_atr_pct",
                                  "up", "down", "both", "none"]
    full = pd.concat([pd.read_parquet(p) for p in shards], ignore_index=True)
    full = full[full["a.step"] == 13].rename(columns={f"fp_{s}": s for s in ("up", "down", "both", "none")})
    full["symbol"] = full["symbol"].astype(str)
    key = ["symbol", "seg_id", "B.length", "B.depth", "up", "down", "both", "none"]
    pd.testing.assert_frame_equal(rows[key].sort_values(key).reset_index(drop=True),
                                  full[key].drop_duplicates().sort_values(key).reset_index(drop=True), check_dtype=False)
    with pytest.raises(SystemExit, match="取不出这个组合"):
        tune.confirm_rows(SYN, "forward", {"a.step": 12}, ["B.depth"])
