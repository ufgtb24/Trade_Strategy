# -*- coding: utf-8 -*-
"""tune.py 的测试。全部在 tmp_path 假树上跑,不碰真实 apps/ 与 outputs/。"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tune  # noqa: E402


def _mk_installed_app(apps: Path, name: str = "demo") -> Path:
    """造一个已接入的 app:study.py + 与之匹配的 classification.json。"""
    import study_io as S
    d = apps / name
    d.mkdir(parents=True)
    study = d / "study.py"
    study.write_text(
        'APP_MODULE = "x.y"\nBASE_YAML = "params.yaml"\nWIDE_OVERRIDES = {}\n'
        'SCAN_GRID = {}\nWHERE_LEVELS = {}\nREF_POINT = {}\n'
        'TIGHT_WHERES = {}\nFLAG_RULES = []\n', encoding="utf-8")
    (d / "classification.json").write_text(json.dumps({
        "app": name, "app_module": "x.y", "base_yaml": "params.yaml",
        "fingerprints": {"study": S.file_sha256(study), "base": "b", "source": {"hash": "s", "files": []}},
    }), encoding="utf-8")
    return d


def _mk_installed_app_real(apps: Path, name: str = "demo_real") -> Path:
    """造一个指向真实 bb_v1 dag_spec 的已接入 app,分类表用 build_classification 真算——
    让 source_stale/base_stale 的"未过期"路径有真实依据,不是伪造一个凑巧相等的哈希。
    SCAN_GRID/WHERE_LEVELS 留空:只为了让 build_classification 跑通,不测分类本身。"""
    import study_io as S
    d = apps / name
    d.mkdir(parents=True)
    study_p = d / "study.py"
    study_p.write_text(
        "APP_MODULE = 'path2_apps.bb_v1.dag_spec'\nBASE_YAML = 'params.yaml'\n"
        "WIDE_OVERRIDES = {}\nSCAN_GRID = {}\nWHERE_LEVELS = {}\n"
        "REF_POINT = {}\nTIGHT_WHERES = {}\nFLAG_RULES = []\n", encoding="utf-8")
    st = S.load_study(study_p)
    mod = S.import_app(st)
    cl = S.build_classification(name, st, mod, study_p)
    S.write_classification(name, cl, apps_dir=apps)
    return d


def test_status_reports_not_installed(tmp_path):
    """没有 study.py → installed=False,其余字段不炸。"""
    st = tune.status("nope", apps_dir=tmp_path / "apps", repo=tmp_path)
    assert st["installed"] is False
    assert st["scanned_shards"] == 0
    assert st["classification_stale"] is None


def test_status_detects_stale_classification(tmp_path):
    """study.py 改过而 classification.json 没重生成 → classification_stale=True。"""
    apps = tmp_path / "apps"
    d = _mk_installed_app(apps)
    (d / "study.py").write_text("APP_MODULE = 'changed'\n", encoding="utf-8")
    st = tune.status("demo", apps_dir=apps, repo=tmp_path)
    assert st["installed"] is True
    assert st["classification_stale"] is True


def test_status_counts_scan_progress_and_exposure(tmp_path):
    """分片数与 exposure 轮次都从文件系统现场数出来。"""
    apps = tmp_path / "apps"
    d = _mk_installed_app(apps)
    (d / "exposure.jsonl").write_text('{"ts":"t1"}\n{"ts":"t2"}\n', encoding="utf-8")
    lt = tmp_path / "outputs" / "tune_gates" / "demo" / "main" / "longtable"
    lt.mkdir(parents=True)
    (lt / "part-000.parquet").write_bytes(b"")
    (lt / "part-001.parquet").write_bytes(b"")
    st = tune.status("demo", apps_dir=apps, repo=tmp_path)
    assert st["scanned_shards"] == 2
    assert st["exposure_rounds"] == 2
    assert st["found"] is False
    assert st["classification_stale"] is False  # 指纹匹配的正常反例,防"恒 True"式坏实现蒙混过关


def test_status_handles_corrupt_classification(tmp_path):
    """classification.json 内容损坏(非法 JSON)→ classification_stale=True,不抛异常。"""
    apps = tmp_path / "apps"
    d = _mk_installed_app(apps)
    (d / "classification.json").write_text("{not valid json", encoding="utf-8")
    st = tune.status("demo", apps_dir=apps, repo=tmp_path)
    assert st["installed"] is True
    assert st["classification_stale"] is True


def test_status_handles_check_regenerable_failure(tmp_path):
    """run_meta.json 损坏(非法 JSON)→ check_regenerable 会抛,status() 必须接住并倒向保守侧。"""
    apps = tmp_path / "apps"
    d = _mk_installed_app(apps)
    lt = tmp_path / "outputs" / "tune_gates" / "demo" / "main" / "longtable"
    lt.mkdir(parents=True)
    (lt / "part-000.parquet").write_bytes(b"")
    (lt / "run_meta.json").write_text("{not valid json", encoding="utf-8")
    st = tune.status("demo", apps_dir=apps, repo=tmp_path)
    assert st["regenerable"] is False
    assert st["regenerable_reasons"]  # 原因非空,能看出到底是什么坏了
    assert "JSONDecodeError" in st["regenerable_reasons"][0]


def test_status_source_and_base_stale_are_false_when_nothing_changed(tmp_path):
    """★ Important B:真实 app、分类表由 build_classification 真算 → source_stale/base_stale
    都该判"未过期"——这是"未检测到不一致"的正例,防止一个恒 True/恒 None 的坏实现蒙混过关。"""
    apps = tmp_path / "apps"
    _mk_installed_app_real(apps)
    st = tune.status("demo_real", apps_dir=apps, repo=tmp_path)
    assert st["source_stale"] is False
    assert st["base_stale"] is False


def test_status_detects_source_stale(tmp_path):
    """classification.json 记录的源码指纹被改过(模拟 detector 代码改了)→ source_stale=True,
    不牵连 base_stale。"""
    apps = tmp_path / "apps"
    d = _mk_installed_app_real(apps)
    cl_p = d / "classification.json"
    cl = json.loads(cl_p.read_text(encoding="utf-8"))
    cl["fingerprints"]["source"]["hash"] = "0" * 64
    cl_p.write_text(json.dumps(cl), encoding="utf-8")
    st = tune.status("demo_real", apps_dir=apps, repo=tmp_path)
    assert st["source_stale"] is True
    assert st["base_stale"] is False


def test_status_detects_base_stale(tmp_path):
    """classification.json 记录的底座指纹被改过(模拟 params.yaml 改了)→ base_stale=True,
    不牵连 source_stale。"""
    apps = tmp_path / "apps"
    d = _mk_installed_app_real(apps)
    cl_p = d / "classification.json"
    cl = json.loads(cl_p.read_text(encoding="utf-8"))
    cl["fingerprints"]["base"] = "not-the-real-hash"
    cl_p.write_text(json.dumps(cl), encoding="utf-8")
    st = tune.status("demo_real", apps_dir=apps, repo=tmp_path)
    assert st["source_stale"] is False
    assert st["base_stale"] is True


def test_status_fingerprint_check_falls_back_to_none_on_import_failure(tmp_path):
    """study.py 指向的 app_module 根本不存在(如接入环境被破坏)→ source_stale/base_stale
    落到保守侧 None,原因不吞,status() 本身不能被带崩(与 regenerable 分支同款纪律)。"""
    apps = tmp_path / "apps"
    _mk_installed_app(apps, name="broken")   # APP_MODULE="x.y",不存在
    st = tune.status("broken", apps_dir=apps, repo=tmp_path)
    assert st["source_stale"] is None
    assert st["base_stale"] is None
    assert st.get("fingerprint_check_error")


def test_settings_defaults_match_migrated_values():
    """迁移正确性:Settings 的默认值必须与改造前 apps/bb_v1/run.py 的取值逐项相同。"""
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
    assert s.min_count_per_fold == 100
    assert s.neighbor_axes == "all"
    assert (s.b_boot, s.boot_seed, s.top_n) == (300, 0, 20)
    assert list(s.split_half_seeds) == list(range(20))
    assert s.workers == 16


def test_settings_is_frozen():
    """Settings 不可变:防止某次调用改了它影响后续调用。"""
    s = tune.Settings()
    with pytest.raises(Exception):
        s.head_buffer = 100


def test_retire_dry_run_returns_plan_without_deleting(tmp_path):
    """confirm=False 只返回清单,一个文件都不能少。"""
    apps = tmp_path / "apps"
    d = _mk_installed_app(apps)
    (d / "notes.md").write_text("# notes\n", encoding="utf-8")
    # _execute_delete 无论 confirm 取值都先查 _worktree_dirty(app_setup.py 的既有行为,
    # 本 task 不改动它),该函数要求 app_dir 能被 git 发现所属仓库,故 tmp_path 需先 git init;
    # 不需要 commit——status --porcelain 不依赖 identity 配置。
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    before = sorted(p.name for p in d.iterdir())
    plan = tune.retire("demo", confirm=False, apps_dir=apps, repo=tmp_path)
    assert {Path(x["path"]).name for x in plan["must"]} >= {"study.py", "classification.json"}
    assert "notes.md" in {Path(x["path"]).name for x in plan["keep"]}
    assert sorted(p.name for p in d.iterdir()) == before      # 一个都没删


def test_retire_refuses_unknown_app(tmp_path):
    with pytest.raises(SystemExit):
        tune.retire("nope", confirm=False, apps_dir=tmp_path / "apps", repo=tmp_path)


def _install_kwargs_that_fails_in_setup():
    """一份 install() 顶部 classify() 能过、但 setup() 内 build_classification 的
    TIGHT_WHERES 守卫会拒的网格:TIGHT_WHERES 里塞一个不在 SCAN_GRID ∪ WHERE_LEVELS 里的
    维(burst.distinct_pk_min),复现评审实测的那条真实失败路径。用真实 app
    path2_apps.bb_v1.dag_spec,只取够触发 D/W 两条分类路径的最小字段子集。"""
    return dict(
        app_module="path2_apps.bb_v1.dag_spec",
        wide_overrides={"burst": {"first_drought_min": 0, "distinct_pk_min": 1,
                                  "vol_spike_min": 0, "peak_age_min": 0},
                        "tb": {"max_day_drop_pct": None}},
        scan_grid={("bo", "min_relative_height"): [0.1, 0.15, 0.2, 0.3],
                  ("burst", "gap_max"): [4, 8, 12, 20]},
        where_levels={("burst", "first_drought_min"): [0, 20, 40]},
        tight_wheres={"BAD": {("burst", "distinct_pk_min"): 999}},  # 网格外的维
    )


def test_install_rolls_back_overwritten_study_on_setup_failure(tmp_path):
    """★ I-2(修复轮 2):study.py 已存在(该 app 有历史扫描结果)时,写盘后 setup() 失败
    必须原样还原旧文件——旧文件已被覆盖、新分类表又生不出来是真损失,不能就地留半成品。"""
    apps = tmp_path / "apps"
    d = apps / "bb_v1_install_rollback"; d.mkdir(parents=True)
    old_bytes = b"# -*- coding: utf-8 -*-\nAPP_MODULE = 'old'\n"
    (d / "study.py").write_bytes(old_bytes)
    with pytest.raises(ValueError):
        tune.install("bb_v1_install_rollback", apps_dir=apps, **_install_kwargs_that_fails_in_setup())
    assert (d / "study.py").read_bytes() == old_bytes, "旧 study.py 必须逐字节还原"


def test_install_leaves_no_residue_when_study_did_not_exist(tmp_path):
    """★ I-2:该 app 之前未接入(study.py 不存在)时,写盘后 setup() 失败不得凭空留下一个
    半成品 study.py。"""
    apps = tmp_path / "apps"
    with pytest.raises(ValueError):
        tune.install("bb_v1_install_new", apps_dir=apps, **_install_kwargs_that_fails_in_setup())
    assert not (apps / "bb_v1_install_new" / "study.py").exists()


def test_find_refuses_when_never_compared(monkeypatch):
    """★ Important E:红线由 find() 自己核——从未 compare 过(compared=False)必须响亮拒绝,
    不做任何事(不该走到 import region_find 这一步)。"""
    monkeypatch.setattr(tune, "status", lambda a, w="main": {"compared": False, "compare_mismatch": None})
    with pytest.raises(SystemExit, match="尚未通过一致性验证"):
        tune.find("demo")


def test_find_refuses_when_compare_crashed_midway(monkeypatch):
    """compared=True 但 compare_mismatch=None——验证日志文件存在但半路崩溃留下的,不是
    「跑完且为 0」,必须按同一条红线拒绝,不能只看 compared。"""
    monkeypatch.setattr(tune, "status", lambda a, w="main": {"compared": True, "compare_mismatch": None})
    with pytest.raises(SystemExit, match="尚未通过一致性验证"):
        tune.find("demo")


def test_find_refuses_when_mismatch_nonzero(monkeypatch):
    monkeypatch.setattr(tune, "status", lambda a, w="main": {"compared": True, "compare_mismatch": 3})
    with pytest.raises(SystemExit, match="尚未通过一致性验证"):
        tune.find("demo")


def test_find_proceeds_when_compared_and_mismatch_zero(monkeypatch):
    """红线满足时正常放行,真的会调用 region_find.run(不是被吞掉的空操作)。"""
    import region_find
    calls = []
    monkeypatch.setattr(tune, "status", lambda a, w="main": {"compared": True, "compare_mismatch": 0})
    monkeypatch.setattr(region_find, "run", lambda *a, **kw: calls.append(a))
    tune.find("demo")
    assert calls, "红线满足时应真的调用 region_find.run"


def test_find_force_bypasses_the_gate(monkeypatch):
    """force=True 是逃生舱:即使一致性验证从未跑过也放行。"""
    import region_find
    calls = []
    monkeypatch.setattr(tune, "status", lambda a, w="main": {"compared": False, "compare_mismatch": None})
    monkeypatch.setattr(region_find, "run", lambda *a, **kw: calls.append(a))
    tune.find("demo", force=True)
    assert calls, "force=True 时应跳过红线检查、正常调用 region_find.run"


# 与 SKILL.md「三、禁止词与人话译法」表逐行对应(该表列出的每个内部机制词都必须能在这里
# 找到能拦住它的条目)——两边任一改动都要同步检查对方,人工维护无自动同步机制。
BANNED = ["MODE=", "MODE", "RUN", "current.py", "run.py", "study.py", "classification.json",
          "run_meta.json", "exposure.jsonl", "detection_combos", "HEAD_BUFFER",
          "SCAN_GRID", "WHERE_LEVELS", "REF_POINT", "指纹", "对拍", "长表",
          "mismatch", "三口径", "naive", "optimism", "split-half", "W/F/D/E"]


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
