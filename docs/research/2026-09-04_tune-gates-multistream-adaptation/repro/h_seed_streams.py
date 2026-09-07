"""方案 H 机制验证:run_streams 只把 `streams = {}` 改成 `streams = dict(seed or {})`,
预置流是否被正确跳过、下游是否与全量重跑逐字相同。只读实验(复制函数体,不改仓库代码)。"""
import sys
from pathlib import Path
import pandas as pd

from path2 import config
from path2.dag.engine import annotate_stream, _translate_refs, _check_children_declarations
from path2.dag._graph import detector_topo_order
from path2.dag.engine import run_streams
from path2.runner import run_bundle
from path2_apps.bb_v1 import dag_spec as APP


def run_streams_seeded(spec, df, params=None, seed=None):
    """= engine.run_streams,唯一差异:streams 初值改成 dict(seed or {})。"""
    by_id = {n.node_id: n for n in spec.nodes}
    children_of = {n.node_id: dict(n.children) for n in spec.nodes if n.children}
    streams = dict(seed or {})            # ★ 唯一改动(原:streams = {})
    materialized, counts, siblings = {}, {}, {}
    for n in spec.nodes:
        if n.detector is not None:
            siblings.setdefault((id(n.detector), n.consumes_stream), []).append(n)
    for nid in detector_topo_order(spec.nodes):
        node = by_id[nid]
        if node.detector is None or nid in streams:
            continue
        key = (id(node.detector), node.consumes_stream)
        if key not in materialized:
            if node.consumes_stream is None:
                materialized[key] = run_bundle(node.detector, df)
            else:
                materialized[key] = run_bundle(node.detector, streams[node.consumes_stream], df)
        bundle = materialized[key]
        for sib in siblings[key]:
            if sib.node_id in streams:
                continue
            streams[sib.node_id] = bundle[sib.produces_stream]
            annotate_stream(counts, sib.node_id, streams[sib.node_id], children_of)
    _translate_refs(streams)
    _check_children_declarations(spec, streams)
    return streams


def sig(evs):
    return [(e.node_id, e.instance_id, e.start_idx, e.end_idx, e.ref_ids) for e in evs]


def main():
    config.set_runtime_checks(True)
    pkls = sorted(Path("/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls").glob("*.pkl"))
    if not pkls:
        sys.exit("datasets/pkls 为空,换一台机器或补数据")
    sym = pkls[0]
    df = pd.read_pickle(sym).reset_index(drop=True)
    p = APP.Params.default()
    spec = APP.build_pattern(p)

    full = run_streams(spec, df)
    print(f"[{sym.stem}] 全量: " + ", ".join(f"{k}={len(v)}" for k, v in full.items()))

    # 只 seed bo+pk 这一组(它们的影响维集合必然相同,故总是整组进出)
    seed = {"bo": full["bo"], "pk": full["pk"]}
    seeded = run_streams_seeded(spec, df, seed=seed)

    assert set(seeded) == set(full), (sorted(seeded), sorted(full))
    same_obj = seeded["bo"] is full["bo"] and seeded["pk"] is full["pk"]
    downstream_equal = all(sig(seeded[k]) == sig(full[k]) for k in ("burst", "tb"))
    print(f"预置流对象未被重建: {same_obj}")
    print(f"下游 burst/tb 逐字相同: {downstream_equal}  "
          f"(burst {len(full['burst'])} / tb {len(full['tb'])})")

    # 反向对照:如果只 seed bo 不 seed pk(半截 seed),会发生什么
    half = run_streams_seeded(spec, df, seed={"bo": full["bo"]})
    print(f"半截 seed(只 bo): bo 仍是原对象={half['bo'] is full['bo']}, "
          f"pk 是新对象={half['pk'] is not full['pk']}, "
          f"下游仍逐字相同={all(sig(half[k]) == sig(full[k]) for k in ('burst', 'tb'))}")




def half_seed_ref_ids_check():
    """lead 提的缺口:半截 seed(只给 bo 不给 pk)时,bo 自己的 ref_ids 会不会坏。
    原脚本只比了下游 burst/tb,没比 bo。"""
    config.set_runtime_checks(True)
    pkls = sorted(Path("/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls").glob("*.pkl"))[:12]
    p = APP.Params.default()
    spec = APP.build_pattern(p)
    bad = ok = 0
    for f in pkls:
        df = pd.read_pickle(f).reset_index(drop=True)
        if len(df) < 300:
            continue
        full = run_streams(spec, df)
        half = run_streams_seeded(spec, df, seed={"bo": full["bo"]})
        same = sig(half["bo"]) == sig(full["bo"])   # sig 含 ref_ids
        n_ref = sum(1 for e in full["bo"] if e.ref_ids)
        ok += same; bad += (not same)
        if not same:
            print(f"  {f.stem}: bo 的 ref_ids 不等")
    print(f"半截 seed 下 bo 自身(含 ref_ids)逐字相同: {ok} 只 / 不同 {bad} 只")
    print("说明:seed 里的 bo 事件来自上一轮完整 run_streams,那一轮 pk 与 bo 同一趟 run_bundle、")
    print("     已被标注,所以 broken_refs 指向的峰有 instance_id,_translate_refs 不会抛。")


main()
half_seed_ref_ids_check()
