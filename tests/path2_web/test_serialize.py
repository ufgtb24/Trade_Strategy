from dataclasses import dataclass
from typing import Tuple

from tests.path2.dag._oracle import Ev
from tests.path2.fixtures.positive_case import positive_case
from path2 import Event
from path2_apps.bottom_burst import dag_spec
from path2_web import serialize


def _analyze_positive():
    df, params = positive_case()
    return dag_spec.analyze(df, params)   # 宽松 params → 必有 >=1 hit


def test_jsonable_handles_tuple_none_nan_nested():
    assert serialize._jsonable((1, 2, 3)) == [1, 2, 3]
    assert serialize._jsonable(None) is None
    assert serialize._jsonable(3.5) == 3.5
    # 嵌套对象 fallback 不抛
    class X: pass
    assert isinstance(serialize._jsonable(X()), str)


def test_serialize_events_flatten_subclass_attrs():
    res = _analyze_positive()
    out = serialize.serialize_analysis(res)
    # F14 修正:out_events 追加容器 child(V4 一容器多段 → +全部容器段数总和)
    tb_containers = [e for e in res.events if getattr(e, "node_id", "") == "tb"]
    n_children = sum(len(c.segments) for c in tb_containers)
    assert n_children >= 1
    assert len(out["events"]) == len(res.events) + n_children
    e0 = out["events"][0]
    assert {"instance_id", "node_id", "instance_idx", "start_idx", "end_idx"} <= set(e0)
    # 子类属性平铺(burst event 必有 count/distinct_pk)
    burst = next(e for e in out["events"] if e["node_id"] == "burst")
    assert "count" in burst and "distinct_pk" in burst
    assert isinstance(burst["distinct_pk"], int)


def test_serialize_hit_node_index_and_trace():
    res = _analyze_positive()
    out = serialize.serialize_analysis(res)
    assert len(out["hits"]) >= 1
    m = out["hits"][0]
    assert {"hit_id", "start_idx", "end_idx", "node_index", "children", "predicate_trace"} <= set(m)
    # 实例流:node_index 每节点值 = instance_id 字符串(与事件行同源);bo 不进 node_index(isolated)
    assert isinstance(m["node_index"]["burst"], str) and "#" in m["node_index"]["burst"]
    assert isinstance(m["node_index"]["tb"], str) and "#" in m["node_index"]["tb"]
    assert "bo" not in m["node_index"]
    # children = node_index 展平,instance_id 列表
    assert isinstance(m["children"], list) and all(isinstance(c, str) for c in m["children"])
    # trace:where_results 是富化 witness(measured/op/threshold)
    pt = m["predicate_trace"]
    # burst 的 3 个 where 子句:distinct_pk 有 measured/op/threshold
    burst_wr = pt["where_results"]["burst"]
    assert set(burst_wr) >= {"first_drought", "distinct_pk", "vol_spike"}
    dpk = burst_wr["distinct_pk"]
    assert dpk["op"] == ">=" and "measured" in dpk and "satisfied" in dpk
    # edge witness:"src→dst" key + src/dst instance_id + measured
    assert any("→" in k for k in pt["edge_results"])
    ew = next(iter(pt["edge_results"].values()))
    assert {"satisfied", "measured", "src", "dst"} <= set(ew)


def test_summarize_counts_by_node_id_plus_hits():
    res = _analyze_positive()
    s = serialize.summarize(res)
    assert s["hits"] == len(res.hits)
    assert "burst" in s and "bo" in s
    # 计数 == events 全集里该 node_id 数量
    n_bo = sum(1 for e in res.events if e.node_id == "bo")
    assert s["bo"] == n_bo


def test_serialize_pattern_topology_and_rules():
    from path2_apps.bottom_burst.dag_spec import PATTERN_DAG
    out = serialize.serialize_pattern(PATTERN_DAG)
    assert out["pattern_id"] == "bottom_burst"
    topo = out["topology"]
    ids = {n["node_id"] for n in topo["nodes"]}
    assert ids == {"bo", "burst", "pk", "tb", "tb_seg"}   # 4 独立 node + 子结构 tb_seg
    # 子结构 node(无 detector):materialize_keys 空
    seg = next(n for n in topo["nodes"] if n["node_id"] == "tb_seg")
    assert seg["materialize_keys"] == []
    # produced_by 透传:子结构 tb_seg 的物化来源 = 父容器 tb
    assert seg["produced_by"] == "tb"
    # bo 节点:isolated plain node
    bo = next(n for n in topo["nodes"] if n["node_id"] == "bo")
    assert bo["produced_by"] is None     # 独立 node 物化来源为空
    # burst 节点:ONCE,where_rules 含 3 个阈值(first_drought/distinct_pk/vol_spike)
    burst = next(n for n in topo["nodes"] if n["node_id"] == "burst")
    burst_rules = {r["clause_id"]: r for r in burst["where_rules"]}
    assert {"first_drought", "distinct_pk", "vol_spike"} <= set(burst_rules)
    assert burst_rules["first_drought"]["op"] == ">=" and isinstance(burst_rules["first_drought"]["threshold"], (int, float))
    assert burst_rules["distinct_pk"]["op"] == ">=" and isinstance(burst_rules["distinct_pk"]["threshold"], (int, float))
    assert burst_rules["vol_spike"]["op"] == ">=" and isinstance(burst_rules["vol_spike"]["threshold"], float)
    # 唯一边: burst.last_bo → tb (TemporalEdge, anchor)
    edge_rules = {(e["src"], e["dst"]): e for e in topo["edges"]}
    assert edge_rules[("burst", "tb")]["kind"] == "TemporalEdge"  # 回踩锚末 bo
    assert "gap" in edge_rules[("burst", "tb")]["rule"]


def test_serialize_pattern_event_styles_fallback():
    from path2_apps.bottom_burst.dag_spec import PATTERN_DAG
    out = serialize.serialize_pattern(PATTERN_DAG)
    # PATTERN_DAG.event_styles 为空 → 后端按 node_id 兜底补齐
    styles = out["event_styles"]
    assert set(styles) >= {"burst", "bo", "tb"}
    assert all(isinstance(c, str) and c.startswith("#") for c in styles.values())


def test_serialize_child_combinator_rule():
    from path2.dag import where as W
    from path2_web.serialize import _rules_from_where
    # W.child 返回 _Pred,meta={'kind':'child','key':'first_bo','inner':{...}}
    pred = W.child("first_bo", W.attr("drought", ">=", 60))
    rules = _rules_from_where([("c1", pred)])
    assert any(r.get("kind") == "child" and r.get("key") == "first_bo" for r in rules)


from path2_web.serialize import serialize_pattern


def test_serialize_pattern_nodes_have_render_grid():
    """serialize_pattern 节点 dict 透传 render_grid; bo='price', 其余='time'。"""
    from path2_apps.bottom_burst.dag_spec import PATTERN_DAG
    out = serialize.serialize_pattern(PATTERN_DAG)
    by = {n["node_id"]: n for n in out["topology"]["nodes"]}
    assert by["bo"]["render_grid"] == "price"
    assert by["burst"]["render_grid"] == "time"
    assert by["tb"]["render_grid"] == "time"


def test_serialize_pattern_nodes_have_is_point():
    """serialize_pattern 节点 dict 透传事件类的 is_point:声明了点几何的类为 True,其余 False;
    子结构 node 同样投影(取它声明的 event_cls)。前端按 node 分点 / 条,不按实例长度。"""
    from path2_apps.bottom_burst.dag_spec import PATTERN_DAG as BB
    from path2_apps.new_step.dag_spec import PATTERN_DAG as NS
    bb = {n["node_id"]: n["is_point"] for n in serialize.serialize_pattern(BB)["topology"]["nodes"]}
    assert bb == {"bo": True, "pk": True, "burst": False, "tb": False, "tb_seg": False}
    ns = {n["node_id"]: n["is_point"] for n in serialize.serialize_pattern(NS)["topology"]["nodes"]}
    # step 有一根长的前缀,但类没声明点几何 → False(一根长的照样画成格,不画成 ▼)
    assert ns == {"plateau": False, "old_plat": False, "step": False, "new_plat": False, "today": True}
    assert all(type(v) is bool for v in [*bb.values(), *ns.values()])


def _srgb_lin(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _rgb(hexcolor: str) -> tuple:
    h = hexcolor.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _luminance(hexcolor: str) -> float:
    r, g, b = (_srgb_lin(c) for c in _rgb(hexcolor))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a: str, b: str) -> float:
    la, lb = sorted([_luminance(a), _luminance(b)], reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _lab(hexcolor: str) -> tuple:
    """sRGB → CIELAB(D65)。"""
    r, g, b = (_srgb_lin(c) for c in _rgb(hexcolor))
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883
    f = [t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116 for t in (x, y, z)]
    return 116 * f[1] - 16, 500 * (f[0] - f[1]), 200 * (f[1] - f[2])


_BAND_BG = "#f3f4f6"      # 副图浅灰底
_QUALIFIED = "#9ca3af"    # qualified 档的深灰(path2_web_ui/src/render/colors.ts)
_B_COOL, _B_WARM = -20.0, 20.0   # b* 冷暖界线(待验证);两线之间的颜色不分冷暖,判不合格


def _palette_problems(pal) -> list:
    """按用户的配色规则检查一组调色板,返回问题列表(空 = 合格)。
    用户靠冷暖与深浅分色:相邻两色冷暖相反;每色中等深度、离浅底与 qualified 灰够远。
    冷暖看 CIELAB b*(黄-蓝轴,红绿色盲也保留):绿的 b* 为正、算暖,所以橘-绿相邻会被抓出来。"""
    out = []
    temp = []
    for c in pal:
        L, _, bs = _lab(c)
        if not 40 <= L <= 55:
            out.append(f"{c}: L* {L:.1f} 不在 40～55")
        if _contrast(c, _BAND_BG) < 3.5:
            out.append(f"{c}: 对副图浅灰底对比度 {_contrast(c, _BAND_BG):.2f} < 3.5")
        if _contrast(c, _QUALIFIED) < 1.6:
            out.append(f"{c}: 对 qualified 灰对比度 {_contrast(c, _QUALIFIED):.2f} < 1.6")
        if bs <= _B_COOL:
            temp.append("cool")
        elif bs >= _B_WARM:
            temp.append("warm")
        else:
            temp.append(None)
            out.append(f"{c}: b* {bs:.1f} 冷暖不明")
    for i in range(len(pal) - 1):
        if temp[i] is not None and temp[i] == temp[i + 1]:
            out.append(f"{pal[i]} 与 {pal[i + 1]} 相邻却同为 {temp[i]}")
    if len(set(c.lower() for c in pal)) < len(pal):
        out.append("有重复颜色")
    return out


def test_palette_is_colorblind_safe():
    """现用的兜底调色板通过配色检查。"""
    assert _palette_problems(serialize._PALETTE) == []


def test_palette_check_rejects_known_bad_palettes():
    """负面对照:检查本身要能抓出坏色板,否则它坏了也看不出来。
    - 橘与正绿相邻(用户点名分不清的一对;旧判据「蓝分量 > 红分量」会把绿判成冷色而放过);
    - 换色前的旧色板(亮绿 #16f943 在白底上几乎看不见,红 #FF1500 与绿 #14b24e 相邻)。"""
    orange_green = ["#5b6fd6", "#d97706", "#00a829", "#c0392b", "#1e5a96"]
    probs = _palette_problems(orange_green)
    assert any("#d97706 与 #00a829 相邻却同为 warm" in p for p in probs), probs
    old = ["#16f943", "#2563eb", "#FF1500", "#14b24e", "#7c3aed", "#0891b2", "#ca8a04"]
    probs = _palette_problems(old)
    assert any(p.startswith("#16f943") for p in probs), probs
    assert any("#FF1500 与 #14b24e 相邻却同为 warm" in p for p in probs), probs


def test_registered_apps_fit_in_palette():
    """每个已注册 app 的 node 数 ≤ 色板长度:超出会从头循环,同色 node 被前端按明度散开、
    可能出中等深度。第 6 个 node 出现时在这里报出来,而不是界面上静默变色。"""
    from path2_web.discovery import PatternRegistry
    reg = PatternRegistry()
    assert reg.ids(), reg.errors()
    for pid in reg.ids():
        nodes = serialize.serialize_pattern(reg.get(pid).PATTERN_DAG)["topology"]["nodes"]
        assert len(nodes) <= len(serialize._PALETTE), (pid, [n["node_id"] for n in nodes])


def test_palette_assigns_new_step_nodes_in_topology_order():
    """new_step 五个 node 按拓扑首现序各取一色,相邻两条轨冷暖相反。"""
    from path2_apps.new_step.dag_spec import PATTERN_DAG as NS
    styles = serialize.serialize_pattern(NS)["event_styles"]
    p = serialize._PALETTE
    assert styles == {"plateau": p[0], "old_plat": p[1], "step": p[2], "new_plat": p[3], "today": p[4]}


def test_burst_event_dict_child_refs_protocol():
    """child_refs 承载 BurstEvent.members(schema-driven,不硬编码字段名);
    顶层 members 字段消失(不留兼容层)。"""
    res = _analyze_positive()
    out = serialize.serialize_analysis(res)
    events = out["events"]
    burst = next(e for e in events if e["node_id"] == "burst")
    # 顶层无 members
    assert "members" not in burst, "payload 里不再有顶层 members 字段(由 child_refs 承载)"
    # child_refs["members"] 是 instance_id 列表
    assert "child_refs" in burst, "所有 event 必须携带 child_refs"
    assert burst["child_refs"].get("members"), "BurstEvent child_refs.members 非空"
    assert all(isinstance(x, str) and "#" in x for x in burst["child_refs"]["members"])
    bo_ids = {e["instance_id"] for e in events if e["node_id"] == "bo"}
    for mid in burst["child_refs"]["members"]:
        assert mid in bo_ids


def test_leaf_event_child_refs_empty():
    """叶子 event(BOEvent)child_refs 是空 dict;容器(tb)child_refs 承载 segments 引用。

    注意:段(ThrowbackSegment)与容器(ThrowbackEvent)同 node_id"tb"(annotate_instances
    嵌套 child 继承父 node_id),二者以 child_refs 区分——容器非空、段为空。"""
    res = _analyze_positive()
    out = serialize.serialize_analysis(res)
    events = out["events"]
    # 叶子:bo 事件 child_refs 空
    for e in events:
        if e["node_id"] == "bo":
            assert e.get("child_refs") == {}, f"{e['instance_id']}: 叶子 event child_refs 必须为空 dict"
    # 容器:携带非空 segments 引用的 tb 事件(段与容器同 node_id,以 child_refs 区分)
    containers = [e for e in events if e["node_id"] == "tb"
                  and e.get("child_refs", {}).get("segments")]
    assert containers, "应有携带 segments 的 tb 容器"
    for c in containers:
        assert set(c["child_refs"].keys()) == {"segments"}


def test_serialize_pattern_edges_anchor_field():
    """topology.edges 每条边携带 anchor_field(str 或 None);bottom_burst 的 burst→tb 边
    anchor_field = 'anchor_bo_id'。"""
    from path2_apps.bottom_burst.dag_spec import PATTERN_DAG
    result = serialize.serialize_pattern(PATTERN_DAG)
    edges = result["topology"]["edges"]
    assert len(edges) >= 1
    for e in edges:
        assert "anchor_field" in e, f"每条边必须携带 anchor_field 键(值可为 None): {e!r}"
    # burst→tb 边 anchor_field 为 'anchor_bo_id'
    burst_tb = next(e for e in edges if e["src"] == "burst" and e["dst"] == "tb")
    assert burst_tb["anchor_field"] == "anchor_bo_id"


def test_serialize_analysis_bo_events_have_ref_ids():
    """serialize_analysis 的 bo/pk event dict 输出 ref_ids(取代原始引用对象递归展开)。
    引用走 ref_slots 协议:broken_refs/superseded_refs 已由引擎物化收编进
    e.ref_ids,_event_to_dict 跳过这两个原始字段、末尾统一从 ref_ids 生成
    dict 形 {槽名: [instance_id, ...]}。"""
    res = _analyze_positive()
    out = serialize.serialize_analysis(res)
    bo_events = [e for e in out["events"] if e["node_id"] == "bo"]
    assert len(bo_events) >= 1
    for bo in bo_events:
        assert "referenced_points" not in bo
        assert "broken_refs" not in bo
        assert "ref_ids" in bo
        broken = bo["ref_ids"]["broken"]   # 每个 bo 恒突破 >=1 个峰,非空
        assert isinstance(broken, list) and broken
        for iid in broken:
            assert isinstance(iid, str) and iid   # 翻译为 instance_id 字符串,非嵌套 dict
    pk_events = [e for e in out["events"] if e["node_id"] == "pk"]
    assert len(pk_events) >= 1
    for pk in pk_events:
        assert "superseded_refs" not in pk
        assert "ref_ids" in pk   # 多数峰未被吃,ref_ids 可为 {}


def test_serialize_analysis_events_no_nested_event_dict():
    """payload 去递归嵌套:json.dumps(out["events"]) 里不出现嵌套事件 dict——任何
    事件 dict 的字段值(递归穿透 list)都不含"instance_id 键的 dict"(旧实现把
    broken_refs 里的 PeakEvent 对象递归展开成嵌套 dict,现改为 ref_ids 引用槽,
    总长度相对旧实现显著缩小,无需断言具体数字)。"""
    import json

    def _has_nested_event_dict(v):
        if isinstance(v, dict):
            return "instance_id" in v or any(_has_nested_event_dict(x) for x in v.values())
        if isinstance(v, list):
            return any(_has_nested_event_dict(x) for x in v)
        return False

    res = _analyze_positive()
    out = serialize.serialize_analysis(res)
    dumped = json.loads(json.dumps(out["events"]))   # sanity:仍可 json 序列化
    assert dumped   # 下限:fixture 必须真产出事件,否则下面的循环空转恒绿
    for e in dumped:
        for v in e.values():   # 只检查顶层 event dict 的字段值,不含事件 dict 自身的 instance_id 键
            assert not _has_nested_event_dict(v), f"字段值中出现嵌套事件 dict: {e}"


def test_ref_field_skip_survives_unresolvable_forward_ref():
    """_ref_field_names 的 typing.get_type_hints 解析失败时(局部类前向引用,
    类所在模块 globalns 里找不到该局部名)必须回退到字面注解字符串判据,而不是
    "不跳过"——不跳过 = 原始引用对象重新递归展开进 payload,即本 task 要修的
    嵌套膨胀 bug 复发。

    构造手法:字段类型写成显式字符串前向引用,指向一个只在本函数局部存在的
    名字(_UndefinedLocalEvent,故意不定义)。get_type_hints 用 cls.__module__
    的 globalns 解析注解,该模块顶部已 `from typing import Tuple`(排除
    Tuple 本身不可解析的干扰),但 _UndefinedLocalEvent 是纯局部名,globalns
    里必然没有 → NameError,精确覆盖到 _ref_field_names 的 except 回退分支。
    """
    @dataclass(frozen=True)
    class _LocalRefEvent(Event):
        refs: "Tuple[_UndefinedLocalEvent, ...]" = ()   # noqa: F821 (故意不可解析,测回退路径)

        def ref_slots(self):
            return {"x": self.refs} if self.refs else {}

    ev = _LocalRefEvent(start_idx=0, end_idx=0, confirm_idx=0)
    row = serialize._event_to_dict(ev)
    assert "refs" not in row


def test_clause_to_dict_recursive():
    from path2.dag import where as W
    from path2_web.serialize import _clause_to_dict

    @dataclass(frozen=True)
    class _E:
        pk: int = 0
        vol: float = 0.0

    w = W.any(W.attr("pk", ">=", 4), W.attr("vol", ">=", 8.0)).witness(_E(pk=5))
    d = _clause_to_dict(w)
    assert d["satisfied"] is True and d["label"] == "or"
    assert [c["label"] for c in d["children"]] == ["pk", "vol"]
    assert [c["measured"] for c in d["children"]] == [5, 0.0]
    assert "children" not in d["children"][0]          # 叶子不带空 children 键


def test_clause_to_dict_flat_leaf_unchanged():
    from dataclasses import dataclass
    from path2.dag import where as W
    from path2_web.serialize import _clause_to_dict

    @dataclass(frozen=True)
    class _E:
        pk: int = 0

    d = _clause_to_dict(W.attr("pk", ">=", 4).witness(_E(pk=3)))
    assert d["satisfied"] is False and d["measured"] == 3
    assert d["op"] == ">=" and d["threshold"] == 4
    assert "children" not in d


def test_rules_from_where_recursive():
    from path2.dag import where as W
    from path2_web.serialize import _rules_from_where
    pred = W.any(W.attr("pk", ">=", 4), W.attr("vol", ">=", 8.0))
    rules = _rules_from_where([("pk_or_vol", pred),
                               ("first_drought", W.attr("first_drought", ">=", 20))])
    assert rules[0]["clause_id"] == "pk_or_vol" and rules[0]["kind"] == "or"
    kids = rules[0]["children"]
    assert [k["field"] for k in kids] == ["pk", "vol"]
    assert [k["op"] for k in kids] == [">=", ">="]
    # 叶子顶层 rule:旧键保留 + 新增 kind/field
    assert rules[1]["clause_id"] == "first_drought"
    assert rules[1]["op"] == ">=" and rules[1]["threshold"] == 20
    assert rules[1]["kind"] == "attr" and rules[1]["field"] == "first_drought"


def test_serialize_hit_has_leaf_instance_id():
    """每个被过滤的 hit dict 注入 leaf(= end_node 事件 instance_id 字符串)。
    win 取 positive_case df 全量 + 合成 date 列(serialize 用 win['date'] 定位买点日)。"""
    import pandas as pd
    df, params = positive_case()
    res = dag_spec.analyze(df, params)
    win = df.copy()
    win["date"] = pd.date_range("2024-01-01", periods=len(win))
    start_ts = pd.to_datetime(win["date"].iat[0])
    end_ts = pd.to_datetime(win["date"].iat[-1])
    out = serialize.serialize_per_pattern_result(
        res, end_node="tb", label_horizon=5,
        win=win, start_ts=start_ts, end_ts=end_ts)
    assert out["analysis"]["hits"]
    for md in out["analysis"]["hits"]:
        assert isinstance(md.get("leaf"), str) and "#" in md["leaf"]
        assert "leaf_event_id" not in md, "leaf_event_id 兼容字段已随 event_id 体系删除"


def _make_price_df(n=30):
    """单调上行日线(买点窗内首穿四态全 none,便于断言累加总数)。"""
    import numpy as np
    import pandas as pd
    closes = 100.0 + np.arange(n) * 1.0
    return pd.DataFrame({
        'open': closes - 0.3,
        'high': closes + 0.2,
        'low': closes - 0.2,
        'close': closes,
        'volume': np.full(n, 1e6),
        'date': pd.date_range("2024-01-01", periods=n),
    })


def test_fp_counts_dedup_shared_leaf():
    """共享 leaf 的多 hit:首穿四态只按 leaf 累加一次(买点日是物理属性)。"""
    from tests.path2.dag._oracle import Ev
    from path2.dag._solve import Solution, compile_plan
    from path2.dag.nodes import NodeSpec
    from path2.dag.edges import TemporalEdge
    from path2.dag.spec import PatternSpec
    from path2.dag._reify import reify
    from path2.dag.result import AnalysisResult
    from path2_web.serialize import serialize_per_pattern_result

    class _StubDetector:
        """占位 detector:只声明 event_cls(compile_plan 不调 detect,streams 直给)。"""
        event_cls = Ev

    # 两上游(A)共享同一 leaf(B),span 相同:放宽后两个 hit 可见
    nodes = [NodeSpec("A", detector=_StubDetector()), NodeSpec("B", detector=_StubDetector())]
    edges = [TemporalEdge("A", "B", min_gap=0, max_gap=100)]
    plan = compile_plan(PatternSpec(pattern_id="p", nodes=tuple(nodes), edges=tuple(edges)))
    a1, a2 = Ev("a_1", 0, 5), Ev("a_2", 0, 5)
    b = Ev("b_1", 25, 27)   # 买点窗置于 df 后段:rolling(20) 的 M 样本充足(前 19 根为 NaN)
    m1 = reify(Solution(assign={"A": a1, "B": b}, chosen_idx={}), streams={}, plan=plan)
    m2 = reify(Solution(assign={"A": a2, "B": b}, chosen_idx={}), streams={}, plan=plan)
    res = AnalysisResult(events=(), hits=(m1, m2), spec=None)
    win = _make_price_df(30)
    out = serialize_per_pattern_result(res, end_node="B", label_horizon=2,
                                       win=win, start_ts=win["date"].iat[0],
                                       end_ts=win["date"].iat[-1],
                                       first_passage_enabled=True, first_passage_k=5.0)
    assert out["hit_fp_counts"] == {"up": 0, "down": 0, "both": 0, "none": 3}


# ── 实例流:契约层实例视图(instance_id / hit leaf) ──

class _FakeDet:
    """合成 detector:忽略输入源,直接吐已构造好的 canned 事件序列(多实例流用)。"""
    event_cls = Ev

    def __init__(self, evs):
        self._evs = evs

    def detect(self, *source):
        return iter(self._evs)


def _analyze_dup_stream():
    """src 流内同 node_id 同 span 两实例(仅 pos 不同)→ 多实例 res(engine 全流程)。

    与 test_engine_hit_id_disambiguate 同构:两实例各产一个 hit(hit id 碰撞
    由 engine 消歧为 #0/#1);events = (s0×2, d0)。"""
    from path2.dag.engine import analyze
    from path2.dag.spec import PatternSpec
    from path2.dag.nodes import NodeSpec
    from path2.dag.edges import TemporalEdge
    spec = PatternSpec(pattern_id="dup", nodes=(
        NodeSpec(node_id="src", detector=_FakeDet(
            [Ev("s0", 5, 10, pos=0), Ev("s0", 5, 10, pos=1)])),
        NodeSpec(node_id="dst", detector=_FakeDet([Ev("d0", 20, 20)])),
    ), edges=(TemporalEdge("src", "dst", min_gap=0, max_gap=100),))
    return analyze(spec, None)


def test_serialize_events_instance_id_contract():
    """事件行新契约:instance_id/node_id/instance_idx 恒在;无 event_id/
    source_tag/instance_key/class_id。"""
    payload = serialize.serialize_analysis(_analyze_dup_stream())
    for r in payload["events"]:
        assert {"instance_id", "node_id", "instance_idx"} <= set(r)
        assert "#" in r["instance_id"]         # 恒带 #idx
        for banned in ("event_id", "source_tag", "instance_key", "class_id"):
            assert banned not in r, f"{banned} 残留"


def test_serialize_hit_instance_refs():
    """hit 行:node_index 值为 instance_id 字符串;children 全实例化;hit_id。"""
    payload = serialize.serialize_analysis(_analyze_dup_stream())
    for m in payload["hits"]:
        assert "hit_id" in m and "event_id" not in m
        for nid, ref in m["node_index"].items():
            assert isinstance(ref, str) and "#" in ref
        for c in m["children"]:
            assert isinstance(c, str) and "#" in c


def test_serialize_child_refs_instanced():
    """事件行 child_refs 值全实例化(instance_id 列表)。"""
    from tests.path2.dag._oracle import WideEv
    from path2.dag.result import AnalysisResult
    # 带 child 的容器(实例化标注),child_refs 才有非空断言面(Ev 无 child_slots)
    w1 = WideEv("w0", 0, 5, node_id="w0", instance_idx=0, instance_id="w0_0_5#0",
                kids=(Ev("k0", 0, 0, node_id="k0", instance_idx=0, instance_id="k0_0#0"),))
    res = AnalysisResult(events=(w1,), hits=(), spec=None)
    payload = serialize.serialize_analysis(res)
    for r in payload["events"]:
        for slot, ids in (r.get("child_refs") or {}).items():
            for i in ids:
                assert isinstance(i, str) and "#" in i


def test_serialize_events_multi_instance_rows():
    """同 node_id 多实例序列化为多行,instance_id(#idx)区分;单实例也恒输出 #idx。"""
    from tests.path2.dag._oracle import WideEv
    from path2.dag.result import AnalysisResult
    # 同 node_id 两容器实例,各带一个同 node_id 的 child(挖取路径验证不丢多实例)
    w1 = WideEv("w0", 0, 5, node_id="w0", instance_idx=0, instance_id="w0_0_5#0",
                kids=(Ev("k0", 0, 0, node_id="k0", instance_idx=0, instance_id="k0_0#0"),))
    w2 = WideEv("w0", 10, 15, node_id="w0", instance_idx=1, instance_id="w0_10_15#1",
                kids=(Ev("k0", 10, 10, node_id="k0", instance_idx=1, instance_id="k0_10#1"),))
    res = AnalysisResult(events=(w1, w2), hits=(), spec=None)
    out = serialize.serialize_analysis(res)
    rows = [r for r in out["events"] if r["node_id"] == "w0"]
    assert len(rows) == 2, f"多实例应序列化 2 行,got {len(rows)}"
    assert {r["instance_id"] for r in rows} == {"w0_0_5#0", "w0_10_15#1"}
    # child 挖取:两个 child 都保留(不丢多实例),各自 instance_id
    kids = [r for r in out["events"] if r["node_id"] == "k0"]
    assert len(kids) == 2, f"child 挖取不应丢多实例,got {len(kids)}"
    assert {r["instance_id"] for r in kids} == {"k0_0#0", "k0_10#1"}
    # 实例级字段各自保留:child_refs 各指其 own kid
    by_id = {r["instance_id"]: r for r in rows}
    assert by_id["w0_0_5#0"]["child_refs"]["kids"] == ["k0_0#0"]
    assert by_id["w0_10_15#1"]["child_refs"]["kids"] == ["k0_10#1"]


def test_serialize_hit_multi_instance_leaf():
    """hit 行 leaf = end_node 事件 instance_id 字符串(与事件行同源)。"""
    import pandas as pd
    res = _analyze_dup_stream()
    win = pd.DataFrame({"open": [100.0] * 30, "high": [101.0] * 30,
                        "low": [99.0] * 30, "close": [100.0] * 30,
                        "date": pd.date_range("2024-01-01", periods=30)})
    start_ts = win["date"].iat[0]
    end_ts = win["date"].iat[-1]
    out = serialize.serialize_per_pattern_result(
        res, end_node="dst", label_horizon=2,
        win=win, start_ts=start_ts, end_ts=end_ts)
    evs = out["analysis"]["events"]
    # events:s0 两实例 #0/#1;d0 单实例也恒输出 #0
    assert {r["instance_id"] for r in evs if r["node_id"] == "src"} == {"src_5_10#0", "src_5_10#1"}
    d0 = next(r for r in evs if r["node_id"] == "dst")
    assert d0["instance_id"] == "dst_20#0"
    # 两 hit 共享 leaf d0:leaf = d0 行的 instance_id 字符串(与事件行同源)
    assert len(out["analysis"]["hits"]) == 2
    for md in out["analysis"]["hits"]:
        assert md["leaf"] == "dst_20#0"
        assert "leaf_event_id" not in md
    # end_node 锚到多实例 src:两 hit 的 leaf 各自定位到具体实例(instance_id 区分)
    out2 = serialize.serialize_per_pattern_result(
        res, end_node="src", label_horizon=2,
        win=win, start_ts=start_ts, end_ts=end_ts)
    leafs = {md["leaf"] for md in out2["analysis"]["hits"]}
    assert leafs == {"src_5_10#0", "src_5_10#1"}


def test_fp_counts_dedup_same_span_instances():
    """end_node 事件是不同实例但 span 相同:同一个买点,首穿四态只计一次、leaf_count 计 1。

    引擎按 (node, span) 编 #idx,dst 两实例物化成 dst_25_27#0 / #1;两 hit 的 leaf
    各指一个实例,buy_span 相同。首穿去重与 scan 聚合都按 span 认买点。"""
    import json
    from path2.dag.engine import analyze
    from path2.dag.spec import PatternSpec
    from path2.dag.nodes import NodeSpec
    from path2.dag.edges import TemporalEdge
    from path2_web.scan import _buy_point_stats
    spec = PatternSpec(pattern_id="dup_span", nodes=(
        NodeSpec(node_id="src", detector=_FakeDet([Ev("s0", 0, 5)])),
        # 买点窗置于 df 后段:rolling(20) 的 M 样本充足(前 19 根为 NaN)
        NodeSpec(node_id="dst", detector=_FakeDet(
            [Ev("d0", 25, 27, pos=0), Ev("d0", 25, 27, pos=1)])),
    ), edges=(TemporalEdge("src", "dst", min_gap=0, max_gap=100),))
    res = analyze(spec, None)
    win = _make_price_df(30)
    out = serialize.serialize_per_pattern_result(
        res, end_node="dst", label_horizon=2,
        win=win, start_ts=win["date"].iat[0], end_ts=win["date"].iat[-1],
        first_passage_enabled=True, first_passage_k=5.0)
    ms = out["analysis"]["hits"]
    assert len(ms) == 2
    assert {md["leaf"] for md in ms} == {"dst_25_27#0", "dst_25_27#1"}
    assert all(md["buy_span"] == [[25, 27]] for md in ms)
    # 首穿四态只计一次:3 个买点日,第二条 hit 的 first_passage 为 None
    assert out["hit_fp_counts"] == {"up": 0, "down": 0, "both": 0, "none": 3}
    assert [md["first_passage"] is not None for md in ms] == [True, False]
    assert ms[0]["first_passage"] == {"up": 0, "down": 0, "both": 0, "none": 3}
    # scan 聚合(经 JSON 往返,buy_span 为 list):同一买点 span → leaf_count 1、被 2 hit 共享
    results = json.loads(json.dumps([{"symbol": "AAA", "per_pattern": {"dup_span": out}}]))
    st = _buy_point_stats(results, "dup_span")
    assert st["leaf_count"] == 1
    assert st["shared_leaf_stats"]["n_shared_leaves"] == 1
    assert st["shared_leaf_stats"]["per_leaf_hit_count_distribution"] == [(2, 1)]


def test_serialize_hit_node_index_instanced():
    """hit node_index 每节点值 = instance_id 字符串,与事件行 instance_id 同源。"""
    res = _analyze_dup_stream()   # 同 node_id(s0)双实例 + 两 hit,node_index 引用它们
    payload = serialize.serialize_analysis(res)
    hits = payload["hits"]
    assert len(hits) == 2
    ev_rows = {r["instance_id"]: r for r in payload["events"]}
    for m in hits:
        for nid, ref in m["node_index"].items():
            assert isinstance(ref, str), f"node_index[{nid}] 应为 instance_id 字符串, 实为 {ref!r}"
            assert ref in ev_rows, f"{ref} 不在事件行(instance_id 编号不同源)"
    # 双实例场景:src 节点的 instance_id 能区分两个实例(两 hit 各引用一个)
    src_refs = [ref for m in hits for nid, ref in m["node_index"].items()
                if nid == "src"]
    assert len({r for r in src_refs}) >= 2, "同 node_id 双实例的 instance_id 应区分"
