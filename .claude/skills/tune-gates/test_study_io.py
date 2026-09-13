# -*- coding: utf-8 -*-
"""study_io 单测(tune-gates skill 自带;显式路径跑):
uv run pytest .claude/skills/tune-gates/test_study_io.py -q
测试只读 fixtures/,不读 apps/——删掉 apps/<app> 后本文件必须仍绿。
"""
import json
from pathlib import Path

import pytest

HERE = Path(__file__).parent
import sys; sys.path.insert(0, str(HERE))  # noqa: E702
import subprocess  # noqa: E402
REPO = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
sys.path.insert(0, str(REPO))

import study_io as S  # noqa: E402

FIX = HERE / "fixtures"
STUDY = FIX / "study_bb_v1.py"
BASE = json.loads((FIX / "bb_v1_p2_wide.json").read_text())


def test_load_study_exports_all_eight():
    st = S.load_study(STUDY)
    for name in ("APP_MODULE", "BASE_YAML", "WIDE_OVERRIDES", "SCAN_GRID", "WHERE_LEVELS", "REF_POINT", "TIGHT_WHERES", "FLAG_RULES"):
        assert hasattr(st, name), name


def test_load_study_missing_name_raises(tmp_path):
    p = tmp_path / "study.py"
    p.write_text(STUDY.read_text().replace("FLAG_RULES = [", "FLAG_RULES_X = ["))
    with pytest.raises(ValueError, match="FLAG_RULES"):
        S.load_study(p)


def test_dotted_roundtrip():
    assert S.dotted(("a", "b")) == "a.b" and S.undotted("a.b") == ("a", "b")


def test_require_none_exits():
    with pytest.raises(SystemExit, match="APP 未填"):
        S.require(None, "APP")
    S.require("x", "APP")


def test_reject_e_dims_blocks_scan_grid():
    """I-1 守卫的单元测试:直接喂 `_reject_e_dims` 一个 kind=E 的维,验证响亮拒绝且报错带维名。

    注:这里没有走 `build_classification` → 真 `classify()` 端到端触发 E 分支——本仓库现存
    的全部 5 个 path2_apps/*/dag_spec.py(含本文件的 bb_v1 fixture)里,唯一会改变边的参数
    (`tb.max_span`)同时也是某 detector 的构造参数(`test_multivar_core.py::
    test_probe_detector_dims` 已把这点实测记录为「同时是 edge max_gap 的 SSoT」),真实探针
    结果落在 D 分支而非纯 E 分支;没有任何现成 app 能真实触发纯 E 分类,构造一个专为触发它
    而写的合成 detector/边 app 超出本次修复范围,遂只单测这条守卫本身(而非用 mock/stub
    `multivar_core.classify` 来伪造一次"端到端"通过)。"""
    with pytest.raises(ValueError, match=r"E 维.*sec\.edge_dim"):
        S._reject_e_dims({("sec", "edge_dim"): [1, 2]}, {("sec", "edge_dim"): "E"})


def test_reject_e_dims_allows_non_e_kinds():
    S._reject_e_dims({("sec", "d_dim"): [1, 2]}, {("sec", "d_dim"): "D"})  # 不抛


def test_base_snapshot_equals_frozen_fixture():
    """回归钉子:base_snapshot() 的输出必须与冻结快照逐字一致(params.yaml 或
    WIDE_OVERRIDES 改动而未重生成 fixture 会红)。

    注意:本 fixture 自 2026-08-30 起由 base_snapshot() 自身生成,不再是改造前那份
    「从 2026-08-25 实战 scan 的 params_snapshot 手抄」的独立 oracle(tb 方案 C 换代后
    已无含新字段的生产快照可抄)。值的正确性改由「与 params.yaml ⊕ WIDE_OVERRIDES
    逐字对照」保证,见 task-1 评审记录。"""
    st = S.load_study(STUDY); mod = S.import_app(st)
    assert S.base_snapshot(mod, st) == BASE


import pandas as pd  # noqa: E402  (文件顶部已有 import 区,放到那里)


@pytest.fixture(scope="module")
def cl():
    st = S.load_study(STUDY); mod = S.import_app(st)
    return S.build_classification("bb_v1_fixture", st, mod, STUDY)


def test_classification_matches_hand_transcribed_values(cl):
    """迁移正确性:与迁移前三个脚本里手抄的分类/字段逐项相等(旧 region_find.py:43-48、compare_longtable.py:155-156)。

    2026-08-30 起 tb 三项已随方案 C 换代重推,不再等同迁移期手抄值(见下方 F→W 说明)。"""
    assert cl["kinds"] == {"bo.min_relative_height": "D", "bo.exceed_threshold": "D", "burst.gap_max": "D",
                           "burst.min_bos": "F", "tb.stop_confirm_bars": "D", "tb.max_rise_k": "D",
                           "tb.max_day_drop_pct": "W", "burst.first_drought_min": "W", "burst.distinct_pk_min": "W",
                           "burst.vol_spike_min": "W", "burst.peak_age_min": "W"}
    # tb.max_day_drop_pct 在方案 C 下是 W 维(见 test_multivar_equiv.py 头注实测记录:
    # throwback_kwargs() 弹出该字段、只接成 tb node 的 where 子句,故 filter_fields 不再
    # 含它、where_fields 反而多出它这一条——与旧 F 维版本(该字段曾是 detector 构造参数)相反。
    assert cl["filter_fields"] == {"burst.min_bos": ["burst", "count", ">="]}
    assert cl["where_fields"] == {"burst.first_drought_min": ["burst", "first_drought", ">="],
                                  "burst.distinct_pk_min": ["burst", "distinct_pk", ">="],
                                  "burst.vol_spike_min": ["burst", "max_bar_vol_ratio", ">="],
                                  "burst.peak_age_min": ["burst", "peak_age_max", ">="],
                                  "tb.max_day_drop_pct": ["tb", "max_day_drop", "<"]}
    assert cl["end_node"] == "tb" and cl["bound_nodes"] == ["burst", "tb"]
    assert cl["detection_combos"] == 1024
    assert cl["ref_params"] == BASE
    assert cl["detector_nodes"]["bo.min_relative_height"] == ["bo", "pk"]
    # bo 与 pk 共享同一个 BODetector 实例(一趟同时产两条流),故该维同时改变两个 node


def test_derived_axes_order_and_content(cl):
    combo, preds = S.derived_axes(cl)
    assert list(combo) == ["bo.min_relative_height", "bo.exceed_threshold", "burst.gap_max", "tb.stop_confirm_bars", "tb.max_rise_k"]
    # preds = F 维(SCAN_GRID 序,现只剩 burst.count 一条)+ W 维(WHERE_LEVELS 序,
    # tb.max_day_drop_pct 现挪到 WHERE_LEVELS 末位,故 tb.day_drop 排到最后而非紧跟 F 维)
    assert preds == [("burst.count", ">=", [1, 2, 3, 4]),
                     ("burst.first_drought", ">=", [0, 20, 40]), ("burst.distinct_pk", ">=", [1, 3, 4]),
                     ("burst.max_bar_vol_ratio", ">=", [0, 10, 15]), ("burst.peak_age_max", ">=", [0, 125]),
                     ("tb.max_day_drop", "<", [None, 0.2])]


def test_pred_mask_is_op_aware(cl):
    df = pd.DataFrame({"burst.gap_max": [8, 8, 12], "burst.count": [1, 3, 3], "tb.max_day_drop": [0.1, 0.3, 0.1],
                       "burst.first_drought": [0, 25, 25]})
    m = S.pred_mask(df, {("burst", "gap_max"): 8, ("burst", "min_bos"): 2, ("tb", "max_day_drop_pct"): 0.2,
                         ("burst", "first_drought_min"): 20}, cl)
    assert m.tolist() == [False, False, False]      # 行1 count<2;行2 day_drop>=0.2;行3 gap_max!=8
    m2 = S.pred_mask(df, {("burst", "gap_max"): 8, ("tb", "max_day_drop_pct"): None}, cl)
    assert m2.tolist() == [True, True, False]       # None → 不加谓词


def test_ref_point_must_cover_exactly_D_dims(tmp_path):
    st = S.load_study(STUDY); mod = S.import_app(st)
    bad = tmp_path / "study.py"
    bad.write_text(STUDY.read_text().replace('"tb.max_rise_k": 1.5', '"tb.max_rise_k_x": 1.5'))
    with pytest.raises(ValueError, match="REF_POINT"):
        S.build_classification("x", S.load_study(bad), mod, bad)


def test_write_and_load_classification(cl, tmp_path):
    p = S.write_classification("appx", cl, apps_dir=tmp_path)
    assert p == tmp_path / "appx" / "classification.json"
    assert S.load_classification("appx", apps_dir=tmp_path) == cl


def test_fingerprints_present_and_source_lists_app_and_detector_files(cl):
    fp = cl["fingerprints"]
    assert set(fp) == {"source", "base", "study"} and len(fp["source"]["hash"]) == 64
    files = fp["source"]["files"]
    assert any(f.endswith("path2_apps/bb_v1/dag_spec.py") for f in files)
    assert any(f.endswith("path2/atoms/throwback_v1.py") for f in files)
    assert files == sorted(files)


def test_base_fingerprint_ignores_yaml_comments(tmp_path):
    """指纹算的是展开后快照,不是文件字节:改注释/空白/顺序不报变更。"""
    st = S.load_study(STUDY); mod = S.import_app(st)
    y = S.app_dir(mod) / st.BASE_YAML
    alt = tmp_path / st.BASE_YAML; alt.write_text("# 只加一行注释\n" + y.read_text())
    class St2:  # 同 study 但 BASE_YAML 指向 tmp 副本
        pass
    for n in S.STUDY_NAMES: setattr(St2, n, getattr(st, n))
    orig_app_dir = S.app_dir
    S.app_dir = lambda m: tmp_path            # 只为本测试临时改向
    try:
        snap2 = S.base_snapshot(mod, St2)
    finally:
        S.app_dir = orig_app_dir
    assert S.canonical_hash(snap2) == S.canonical_hash(S.base_snapshot(mod, st))


def test_snapshot_diff_labels(cl):
    old = cl["ref_params"]
    import copy; new = copy.deepcopy(old)
    # 底座常量取 tb.vol_window(方案 C 起 tb 已无 max_window;vol_window 同样是不进
    # 网格的 tb 底座常量,BASE 里现值 14):既不在 SCAN_GRID 也不在 WHERE_LEVELS。
    new["tb"]["vol_window"] = 10              # 底座常量
    new["burst"]["gap_max"] = 10              # D 维
    new["tb"]["brand_new"] = 3                # 新增
    del new["bo"]["total_window"]             # 删除
    d = {k: (o, n, lab) for k, o, n, lab in S.snapshot_diff(old, new, cl)}
    assert d["tb.vol_window"] == (14, 10, "底座常量 · 全部检测组合受影响 · 长表过期")
    assert d["burst.gap_max"] == (8, 10, "D 维 · 网格档位覆盖 · 仅参照格坐标需核对")
    assert d["tb.brand_new"] == (None, 3, "新增 · 未进网格 · 将以新值作底座常量")
    assert d["bo.total_window"] == (20, None, "删除 · build 时 Params.from_dict(strict) 会失败")
    assert set(d) == {"tb.vol_window", "burst.gap_max", "tb.brand_new", "bo.total_window"}


def test_check_report_all_consistent_and_study_changed(cl, tmp_path):
    st = S.load_study(STUDY); mod = S.import_app(st)
    rep = S.check_report("bb_v1_fixture", st, mod, cl, STUDY)
    assert rep.splitlines()[0].startswith("source:    一致") and "base:      一致" in rep and "study:     一致" in rep
    alt = tmp_path / "study.py"; alt.write_text(STUDY.read_text() + "\n# touched\n")
    rep2 = S.check_report("bb_v1_fixture", S.load_study(alt), mod, cl, alt)
    assert "study:     已变更" in rep2
    with pytest.raises(SystemExit, match="study.py 已改"):
        S.check_study_matches(cl, alt)
    S.check_study_matches(cl, STUDY)


def test_run_meta_roundtrip_and_caliber_guard(tmp_path):
    meta = {"app": "x", "start_date": "2024-01-01", "end_date": "2026-01-01", "head_buffer": 250,
            "label_horizon": 40, "first_passage_k": 5.0, "price_min": 0.5, "price_max": 30.0, "volume_min": 10000.0,
            "study_fingerprint": "abc", "git_head": "0000000", "written_at": "t"}
    S.write_run_meta(tmp_path, meta)
    assert S.load_run_meta(tmp_path)["head_buffer"] == 250
    S.write_run_meta(tmp_path, {**meta, "written_at": "t2", "git_head": "1111111"})   # 非口径字段可变
    with pytest.raises(SystemExit, match="head_buffer"):
        S.write_run_meta(tmp_path, {**meta, "head_buffer": 63})                       # 口径字段变 → 拒绝续跑
    with pytest.raises(SystemExit, match="run_meta.json 不存在"):
        S.load_run_meta(tmp_path / "nope")


def test_check_run_matches_classification(cl):
    S.check_run_matches_classification({"study_fingerprint": cl["fingerprints"]["study"]}, cl)
    with pytest.raises(SystemExit, match="study"):
        S.check_run_matches_classification({"study_fingerprint": "zzz"}, cl)


def _write_regenerable_fixture(tmp_path, *, app_module: str, base_yaml: str,
                                study_app_module: str, source_files: list = None,
                                run_base_fingerprint: str = None) -> tuple:
    """给 check_regenerable 的单测搭一套自洽假树:apps/demo/{study.py,classification.json} +
    longtable/run_meta.json,study 指纹与 run_meta 记录一致(study/classification 两条链都过)。
    `app_module`(classification 里的,只影响链 4 的底座路径拼接)与
    `study_app_module`(study.py 的 APP_MODULE,只影响链 5 的 import_app)刻意分开传,
    好让两条链的通过/失败能分别控制。返回 (apps_dir, longtable_dir)。"""
    import study_io as S
    apps_dir = tmp_path / "apps"; app_dir = apps_dir / "demo"; app_dir.mkdir(parents=True)
    study_text = (
        f"APP_MODULE = {study_app_module!r}\nBASE_YAML = {base_yaml!r}\n"
        "WIDE_OVERRIDES = {}\nSCAN_GRID = {}\nWHERE_LEVELS = {}\n"
        "REF_POINT = {}\nTIGHT_WHERES = {}\nFLAG_RULES = []\n"
    )
    study_p = app_dir / "study.py"; study_p.write_text(study_text, encoding="utf-8")
    study_fp = S.file_sha256(study_p)
    cl = {"app_module": app_module, "base_yaml": base_yaml,
          "fingerprints": {"study": study_fp, "base": "irrelevant",
                           "source": {"hash": "irrelevant", "files": source_files or []}}}
    (app_dir / "classification.json").write_text(json.dumps(cl), encoding="utf-8")
    lt = tmp_path / "longtable"; lt.mkdir()
    meta = {"app": "demo", "study_fingerprint": study_fp}
    if run_base_fingerprint is not None:          # 不传 = 模拟 2026-09-12 之前产出的长表(链 6 判不了)
        meta["base_fingerprint"] = run_base_fingerprint
    (lt / "run_meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return apps_dir, lt


def test_check_regenerable_reports_missing_base_yaml(tmp_path):
    """底座 yaml 不存在(本任务的动机场景,如 2026-08-25 长表缺席的 p2.yaml)→ 不可再生,
    原因里点名那个具体文件——不是"随便什么原因都行"。

    评审 Important 2:旧版这个测试传的 `apps_dir=tmp_path/"apps"` 从未创建,执行在
    「classification.json 不存在」那步就 return 了,根本没走到底座检查;`assert reasons`
    没有牙齿,把底座检查整段删掉这个测试照样绿。这里改造成造齐 study/classification 全套、
    让前两条链都过,只让底座文件缺席,断言点名到具体文件名。"""
    apps_dir, lt = _write_regenerable_fixture(
        tmp_path, app_module="nonexistent_module_for_test_xyz.dag_spec", base_yaml="p2_missing.yaml",
        study_app_module="nonexistent_module_for_test_xyz.dag_spec")
    import study_io as S
    ok, reasons = S.check_regenerable(lt, apps_dir=apps_dir)
    assert ok is False
    assert any("p2_missing.yaml" in r for r in reasons)


def test_check_regenerable_base_content_recompute_failure_falls_to_unregenerable(tmp_path):
    """链 5(底座内容重算,评审 Important 1b 新增)测的是"失败落在安全侧":import app 失败时
    (app 已退役、环境缺依赖等)不能因为"查不出来"就放行,必须判不可再生。

    这里让 `classification.json` 的 `base_yaml` 指向仓库里真实存在的一个文件
    (`path2_apps/bb_v1/params.yaml`),使链 4 的存在性检查**通过、不产生 reason**,专测链 5;
    但 study.py 的 `APP_MODULE` 指向一个不存在的模块,`import_app` 必然抛异常 → 落进
    `check_regenerable` 的 except 分支 → reasons 带上失败原因、ok is False。"""
    apps_dir, lt = _write_regenerable_fixture(
        tmp_path, app_module="path2_apps.bb_v1.dag_spec", base_yaml="params.yaml",
        study_app_module="nonexistent_module_for_test_xyz.dag_spec")
    import study_io as S
    ok, reasons = S.check_regenerable(lt, apps_dir=apps_dir)
    assert ok is False
    assert not any("底座" in r and "不存在" in r for r in reasons)   # 链 4 的存在性检查确实通过了
    assert any("重算底座快照失败" in r for r in reasons)             # 链 5 的失败落在安全侧


def test_check_regenerable_missing_classification_still_reports_study_mismatch(tmp_path):
    """classification.json 不存在 → 链 3 必要早退,但链 2(study 指纹,不依赖 classification)
    排在早退之前先跑过——早退不该把它已经收集到的 reason 丢掉。

    评审修复轮 2:重写 Important 2 的两个测试后,「classification.json 不存在」这条早退分支
    反而没了专门测试(旧版是 apps_dir 从未创建、误打误撞覆盖到它)。这里补回来,顺带钉住
    本轮把链 2 挪到早退之前换来的东西:即使因为 classification 缺失被早退拦下,study 指纹
    不符这条独立证据也不会被吞掉。"""
    import json
    import study_io as S
    apps_dir = tmp_path / "apps"; app_dir = apps_dir / "demo"; app_dir.mkdir(parents=True)
    (app_dir / "study.py").write_text("X = 1\n", encoding="utf-8")   # 内容随意,故意不匹配指纹
    lt = tmp_path / "longtable"; lt.mkdir()
    (lt / "run_meta.json").write_text(json.dumps({"app": "demo", "study_fingerprint": "does-not-match"}),
                                      encoding="utf-8")

    ok, reasons = S.check_regenerable(lt, apps_dir=apps_dir)
    assert ok is False
    assert any("study.py 已改" in r for r in reasons)          # 链 2:早退之前已经跑过,没被吞
    assert any("classification.json" in r for r in reasons)    # 链 3:必要早退本身


def test_check_regenerable_missing_run_meta_is_unknown_not_deletable(tmp_path):
    """没有 run_meta 的长表 → 归属不明,必须报不可再生(只报不删)。"""
    import study_io as S
    lt = tmp_path / "longtable"; lt.mkdir()
    ok, reasons = S.check_regenerable(lt, apps_dir=tmp_path / "apps")
    assert ok is False
    assert any("run_meta" in r for r in reasons)


def test_run_meta_carries_source_and_base_fingerprints(tmp_path):
    """run_meta 要留 source/base 指纹副本,好让从长表侧出发的核对拿得到它们。"""
    import study_io as S
    meta = {"app": "demo", "start_date": "2024-01-01", "end_date": "2026-01-01",
            "head_buffer": 250, "label_horizon": 40, "first_passage_k": 5.0,
            "price_min": 0.5, "price_max": 30.0, "volume_min": 10000.0,
            "study_fingerprint": "aaa", "source_fingerprint": "bbb",
            "base_fingerprint": "ccc", "git_head": "0000000", "written_at": "t"}
    S.write_run_meta(tmp_path, meta)
    got = S.load_run_meta(tmp_path)
    assert got["source_fingerprint"] == "bbb"
    assert got["base_fingerprint"] == "ccc"


def test_source_and_base_fingerprints_are_run_caliber():
    """源码指纹与底座指纹**都**参与口径校验。

    2026-09-12 推翻了此前的判断(原文:"source/base 指纹不参与口径校验:它们变了是'不可再生',
    不是'混窗'")。推翻理由:那个判断只覆盖了「扫完之后才变」——那确实只是不可再生。但还有
    「扫的中途变」:一份长表跨多轮续跑扫完全宇宙,中途改了 detector 或底座,已扫的股票用旧配置、
    后扫的用新配置,最终按格聚合出来的计数混了两种东西。这与混窗同类(一份长表内部不自洽),
    且 `check_regenerable` 只看得见最后一轮的指纹,会把它报成可再生——假阳,落在删除侧。
    两道闸分工:`write_run_meta` 从源头拦"中途变",`check_regenerable` 事后判"扫完之后变"。
    """
    import study_io as S
    assert "source_fingerprint" in S.RUN_CALIBER
    assert "base_fingerprint" in S.RUN_CALIBER
    assert set(S.LATE_CALIBER) == {"source_fingerprint", "base_fingerprint"}   # 缺键时放过的那两个


def test_append_exposure_is_append_only(tmp_path):
    """两次写入产生两行,先写的不被覆盖。"""
    import json
    import study_io as S
    (tmp_path / "demo").mkdir()
    S.append_exposure("demo", {"ts": "t1", "c_hat": {"a": 1}}, apps_dir=tmp_path)
    p = S.append_exposure("demo", {"ts": "t2", "c_hat": {"a": 2}}, apps_dir=tmp_path)
    lines = p.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2
    assert json.loads(lines[0])["ts"] == "t1"
    assert json.loads(lines[1])["ts"] == "t2"


def test_append_exposure_requires_existing_app_dir(tmp_path):
    import study_io as S
    with pytest.raises(SystemExit):
        S.append_exposure("nope", {"ts": "t"}, apps_dir=tmp_path)


# ---- 链 6:长表自己的底座溯源(2026-09-12 新增,补 setup 之后 regenerable 假阳的缝隙) ----

_FIX = dict(app_module="nonexistent_module_for_test_xyz.dag_spec", base_yaml="p2_missing.yaml",
            study_app_module="nonexistent_module_for_test_xyz.dag_spec")


def test_check_regenerable_detects_longtable_base_drift(tmp_path):
    """长表记录的底座指纹 != classification 现在记录的 → 点名报出来。

    这条链补的缝隙:链 1~5 全是「当前代码 vs classification」,所以 `tune.setup()` 一重建
    分类表(底座指纹换成当前 yaml 的),链 5 恒通过、`regenerable` 假阳——而长表仍是旧底座
    扫的。实例见 apps/bb_v1/notes.md §11.1 坑 3。
    """
    apps_dir, lt = _write_regenerable_fixture(tmp_path, run_base_fingerprint="OLDBASE0123456789", **_FIX)
    ok, reasons = S.check_regenerable(lt, apps_dir=apps_dir)
    assert ok is False
    hits = [r for r in reasons if "另一份底座下扫的" in r]
    assert len(hits) == 1 and "OLDBASE0123456789"[:16] in hits[0]


def test_check_regenerable_base_fingerprint_match_does_not_report_drift(tmp_path):
    """反向:长表记录的底座指纹与 classification 一致时,链 6 **不该**报。

    没有这条反向断言,链 6 写成"恒报"也能让上面那个测试绿——那样每一份长表都会被判不可
    再生,而该函数的语义轴是"假阳(该 False 却 True)危险",恒报 False 虽不危险却会让
    整条判据失去区分力。
    """
    apps_dir, lt = _write_regenerable_fixture(tmp_path, run_base_fingerprint="irrelevant", **_FIX)
    ok, reasons = S.check_regenerable(lt, apps_dir=apps_dir)
    assert not any("另一份底座下扫的" in r for r in reasons)
    assert not any("base_fingerprint 缺失" in r for r in reasons)


def test_check_regenerable_missing_base_fingerprint_is_unknown_not_regenerable(tmp_path):
    """2026-09-12 之前产出的长表没有 base_fingerprint 字段 → 判不了,并入不可再生(保守侧)。"""
    apps_dir, lt = _write_regenerable_fixture(tmp_path, **_FIX)
    ok, reasons = S.check_regenerable(lt, apps_dir=apps_dir)
    assert ok is False
    assert any("base_fingerprint 缺失" in r for r in reasons)


# ---- base_fingerprint 进 RUN_CALIBER:一份长表全程必须同一个底座(2026-09-12) ----

_META = {"app": "x", "start_date": "2024-01-01", "end_date": "2026-01-01", "head_buffer": 250,
         "label_horizon": 40, "first_passage_k": 5.0, "price_min": 0.5, "price_max": 30.0,
         "volume_min": 10000.0, "study_fingerprint": "abc", "git_head": "0", "written_at": "t"}


def test_run_meta_rejects_base_drift_on_resume(tmp_path):
    """底座变了就不许往同一份长表里续写。

    为什么这是硬要求:一份长表跨多轮扫完全宇宙,最终被当成「同一套检测配置下的候选集合」
    按格聚合。中途底座变过的话,不同股票的行来自不同配置,按格聚合出来的计数不是同一个东西。
    """
    S.write_run_meta(tmp_path, {**_META, "base_fingerprint": "BASE_A"})
    S.write_run_meta(tmp_path, {**_META, "base_fingerprint": "BASE_A", "written_at": "t2"})  # 同底座可续
    with pytest.raises(SystemExit, match="base_fingerprint"):
        S.write_run_meta(tmp_path, {**_META, "base_fingerprint": "BASE_B"})


def test_run_meta_legacy_without_base_fingerprint_still_resumable(tmp_path):
    """2026-09-12 之前产出的 run_meta 没有这个键 → 不拦(拦它没有依据,还会让扫到一半的
    window 续不动),放过并把新字段写进去,下一轮就有依据了。

    另一道防线不受影响:`check_regenerable` 链 6 对缺字段的长表照样报「判不了」。
    """
    legacy = {k: v for k, v in _META.items()}          # 刻意不含这两个后加的指纹
    S.write_run_meta(tmp_path, legacy)
    assert "base_fingerprint" not in S.load_run_meta(tmp_path)
    S.write_run_meta(tmp_path, {**legacy, "base_fingerprint": "BASE_A",
                                "source_fingerprint": "SRC_A"})            # 放过
    assert S.load_run_meta(tmp_path)["base_fingerprint"] == "BASE_A"       # 且已补上
    with pytest.raises(SystemExit, match="base_fingerprint"):              # 补上之后就开始拦
        S.write_run_meta(tmp_path, {**legacy, "base_fingerprint": "BASE_B", "source_fingerprint": "SRC_A"})
    with pytest.raises(SystemExit, match="source_fingerprint"):            # detector 中途改了同样拦
        S.write_run_meta(tmp_path, {**legacy, "base_fingerprint": "BASE_A", "source_fingerprint": "SRC_B"})
