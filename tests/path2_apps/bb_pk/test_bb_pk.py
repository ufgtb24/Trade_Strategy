"""bb_pk:多流 bo+pk + burst + tb 端到端。pk 只显示不参与匹配。"""
import pandas as pd
from path2.dag.engine import analyze
from path2_apps.bb_pk.dag_spec import build_pattern, eval_meta
from path2_apps.bb_pk.params import Params


def _df():
    # 非单调确定性序列(裁决替换,原 brief 单调序列不产任何事件):
    # 峰@idx5(high≈12.1) → 回落 → 突破@idx11(high≈13.1) → 再回落。
    # 单调上升序列不会触发峰登记(窗口 argmax 恒在右端),必须非单调才能覆盖 pk 事件物化。
    closes = [10.0] * 5 + [12.0] + [10.0] * 5 + [13.0] + [10.0] * 3
    return pd.DataFrame({"open": list(closes), "high": [c + 0.1 for c in closes],
                         "low": [c - 0.1 for c in closes], "close": list(closes),
                         "volume": [1] * len(closes)})


def test_eval_meta():
    m = eval_meta()
    assert m["end_node"] == "tb"
    assert m["head_buffer_trading_days"] > 0


def test_analyze_pk_solve_false_excluded():
    params = Params.default()
    spec = build_pattern(params)
    res = analyze(spec, _df())
    # 节点齐全
    assert all(n in spec_nodes(spec) for n in ("bo", "pk", "burst", "tb"))
    # pk 不参与匹配:由引擎层 _solve.py 的 `and nodes[nid].solve` 门(_solve.py:106)保障——
    # solve=False 的 node 不进 bound_ids,结构性不产生 match 分量,matches.node_index
    # 恒不含 pk(此处不空转断言 matches,fixture 产不产 match 都不影响该不变量)。
    pk_node = {n.node_id: n for n in spec.nodes}["pk"]
    assert pk_node.solve is False
    for m in res.matches:
        assert "pk" not in m.node_index
    # 事件里 pk 事件存在(物化渲染)
    assert any(e.node_id == "pk" for e in res.events)


def spec_nodes(spec):
    return [n.node_id for n in spec.nodes]
