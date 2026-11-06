"""new_step dag 声明结构测试(第二版:唯一 node plateau + 四个子结构 node,零边)。"""
from path2_apps.new_step import dag_spec
from path2_apps.new_step.dag_spec import PATTERN_DAG, build_pattern
from path2_apps.new_step.params import Params
from path2_apps.new_step.plateau import (
    NewPlatform, OldPlatform, PlateauDetector, PlateauEvent, Step, Today,
)
from path2_web import mapping as mapping_mod

PARENT_WHERE = ["old_flat", "step_big", "step_strong", "step_vol",
                "new_hold", "new_calm", "no_chase", "bull_close"]


def _by():
    return {n.node_id: n for n in build_pattern(Params.default()).nodes}


def test_nodes_and_children():
    """五个 node:plateau(有 detector)+ 四个子结构 node,children 槽 → node 一一对应。"""
    by = _by()
    assert set(by) == {"plateau", "old_plat", "step", "new_plat", "today"}
    plateau = by["plateau"]
    assert isinstance(plateau.detector, PlateauDetector)
    assert plateau.event_cls is PlateauEvent
    assert plateau.children == {"old": "old_plat", "step": "step", "new": "new_plat", "today": "today"}
    assert plateau.consumes_stream is None          # 只吃 K 线
    assert plateau.render_grid == "time"
    assert plateau.solve is True
    expect_cls = {"old_plat": OldPlatform, "step": Step, "new_plat": NewPlatform, "today": Today}
    for nid, cls in expect_cls.items():
        n = by[nid]
        assert n.detector is None
        assert n.event_cls is cls
        assert n.produced_by == "plateau"           # children 逆映射回填
        assert n.consumes_stream is None and n.render_grid == "time"


def test_detector_built_from_params():
    """PlateauDetector 的四个构造参数取自 plateau section。"""
    p = Params.default()
    det = _by()["plateau"].detector
    assert (det.old_window, det.strong_k, det.max_step_bars, det.max_days) == (
        p.plateau.old_window, p.plateau.strong_k, p.plateau.max_step_bars, p.plateau.max_days)
    assert p.plateau_kwargs() == {"old_window": 15, "strong_k": 3.0, "max_step_bars": 5, "max_days": 40}


def test_zero_edges():
    spec = build_pattern(Params.default())
    assert spec.pattern_id == "new_step"
    assert spec.edges == ()
    topo = spec.to_topology()
    assert {n.node_id for n in topo.nodes} == {"plateau", "old_plat", "step", "new_plat", "today"}
    assert list(topo.edges) == []


def test_parent_where_names_and_thresholds():
    """plateau 挂八条 where(clause 名 = 用户词的英文标识),阈值取自 params。"""
    p = Params.default().plateau
    where = _by()["plateau"].where
    assert [cid for cid, _ in where] == PARENT_WHERE
    w = dict(where)
    assert w["old_flat"].meta == {"kind": "attr", "field": "old_flat_ratio", "op": "<=",
                                  "threshold": p.old_flat_max}
    assert w["step_big"].meta["kind"] == "child" and w["step_big"].meta["key"] == "step"
    assert w["step_big"].meta["inner"]["field"] == "rise"
    assert w["step_strong"].meta["kind"] == "and"
    left, right = w["step_strong"].meta["children"]
    assert left["kind"] == "child" and left["inner"]["field"] == "vs_left"
    assert right["field"] == "vs_right" and right["threshold"] == p.vs_right_min
    assert w["step_vol"].meta["inner"]["field"] == "vol_ratio"
    assert w["new_hold"].meta["field"] == "keep_ratio"
    assert w["new_calm"].meta["field"] == "calm_ratio"
    assert (w["no_chase"].meta["field"], w["no_chase"].meta["op"]) == ("vs_high", "<")
    assert w["bull_close"].meta["key"] == "today"
    assert (w["bull_close"].meta["inner"]["field"], w["bull_close"].meta["inner"]["op"]) == ("body", ">")


def test_substructure_where_shares_predicates_with_parent():
    """子结构 node 的诊断层 where 与父 where 共用同一谓词对象。"""
    by = _by()
    w = dict(by["plateau"].where)
    step_w = dict(by["step"].where)
    today_w = dict(by["today"].where)
    assert list(step_w) == ["step_big", "vs_left", "step_vol"]
    assert list(today_w) == ["bull_close"]
    assert by["old_plat"].where == () and by["new_plat"].where == ()

    # W.child 不暴露内层谓词对象,只在 meta["inner"] 里放内层的 meta 原对象;
    # 每次 W.attr 调用都新造 meta,故 meta 同一 ⇔ 谓词同一
    for clause, sub in (("step_big", step_w["step_big"]), ("step_vol", step_w["step_vol"]),
                        ("bull_close", today_w["bull_close"])):
        assert w[clause].meta["inner"] is sub.meta
    left_child = w["step_strong"].children[0]
    assert left_child.meta["inner"] is step_w["vs_left"].meta


def test_pattern_dag_is_default_build():
    assert {n.node_id for n in PATTERN_DAG.nodes} == set(_by())
    assert [cid for cid, _ in {n.node_id: n for n in PATTERN_DAG.nodes}["plateau"].where] == PARENT_WHERE


def test_dag_spec_reexports_params():
    """web 只 import .dag_spec:Params / load_params / DEFAULT_YAML_PATH 须从 dag_spec 可取。"""
    assert dag_spec.Params is Params
    assert callable(dag_spec.load_params)
    assert dag_spec.DEFAULT_YAML_PATH.name == "params.yaml"


class _Registry:
    def __init__(self, mods):
        self._mods = mods

    def ids(self):
        return sorted(self._mods)

    def get(self, app):
        return self._mods.get(app)


def test_mapping_has_no_problem():
    """new_step 的 mapping.yaml:node 都在 dag 里,没有 problem。"""
    [m] = mapping_mod.read_mappings(_Registry({"new_step": dag_spec}))
    assert m["problem"] is None
    assert m["pattern"] == "new_step"
    assert m["features"] == {"w-pc-11": "plateau"}
