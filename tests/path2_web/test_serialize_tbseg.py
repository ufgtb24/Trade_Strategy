"""serialize 主动挖容器 child(tb_seg)进 out_events(F14 修正)的回归测试。

实例流契约(2026-08-13 重构):事件行标识 = instance_id/node_id;容器 child 引用由
child_refs(instance_id 列表)承载,挖出的子事件独立成行。段的 node_id 由 children
声明命名表赋为子结构 node("tb_seg",2026-08-17 方案 A),不再与容器共享。

注:import 必须放在函数体内——conftest 的 autouse fixture 把 load_params 换成
Params.default()(测试用宽松参数),函数内 import 才能在运行时绑到被 stub 的版本。
"""


def test_serialize_tbseg_walked_from_container():
    import pickle
    from path2_apps.bottom_burst.dag_spec import analyze, load_params
    from path2_web.data import slice_window
    from path2_web.serialize import serialize_analysis

    df = slice_window(pickle.load(open("datasets/pkls/ACUT.pkl", "rb")),
                      "2024-09-19", "2026-03-08")
    res = analyze(df, load_params())
    if not res.matches:                      # AA 无 tb 命中时用合成断言跳过?不——必须有命中
        raise AssertionError("AA 无 match,换数据/窗口")
    out = serialize_analysis(res)
    tbs = [e for e in out["events"] if e.get("node_id") == "tb"]
    assert tbs, "tb 容器不在 out_events"
    # 挖出的段 == 全部容器声明的段并集(child_refs 由 serialize_analysis 挖出补充;
    # 多变容器场景;单容器是特例)
    seg_ids = {sid for tb in tbs for sid in tb.get("child_refs", {}).get("segments", [])}
    assert seg_ids, "tb 容器无 segments child_refs"
    ev_ids = {e["instance_id"] for e in out["events"]}
    assert seg_ids <= ev_ids, "child_refs 引用的段未作为独立事件行挖出"
    # 挖出的段事件行 node_id = 子结构 node(children 声明命名表),instance_id 前缀随之
    seg_rows = [e for e in out["events"] if e["instance_id"] in seg_ids]
    assert all(e.get("node_id") == "tb_seg" for e in seg_rows)
    assert all(e["instance_id"].startswith("tb_seg_") for e in seg_rows)
