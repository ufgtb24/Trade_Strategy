# path2_apps/try_conplex_where/dag_spec.py
"""try_complex_where — 嵌套复杂 where 的试验田(sandbox)。

拓扑照抄 bottom_breakout_burst(bo / burst / tb + 1 条边),**唯一用途是让你随便改
burst 节点的 where**,看引擎怎么判、UI 怎么显示。改坏了也不影响主 app。

═══ 怎么用 ═══
1. 改下面 build_pattern 里 burst 的 where=(...) —— 每条 clause 独立一块,
   注释掉整块就是关掉该条约束。
2. 重启后端(uv run python scripts/path2/run_path2_web.py),在 web UI 左上 Patterns
   列表勾选 try_complex_where 再扫描。
3. 三处看判定:
   - K 线 hover burst marker → tooltip 出完整缩进树(每层实测值都有)
   - 右侧候选表展开 burst → 单元格 n/m(kind) 聚合,悬停出逐分支明细
   - 拓扑面板 hover burst 方框 → 规则表达式串

═══ 顶层 AND 是不变式 ═══
where 是 (clause_id, 谓词) 的元组,**顶层各 clause 之间恒为 AND**。想要 OR 就写进
单条 clause 内部(见 ②③)。别把 OR 的两个分支拆成两条平级 clause —— 那是 AND,
语义完全不同。

═══ 组合子速查 ═══
  W.attr(field, op, thr)   叶子比较;op ∈ >= > <= < == !=
                           字段值为 None 时恒判 False(不抛错)
  W.any(a, b, ...)      OR  —— 任一成立
  W.all(a, b, ...)         AND —— 全部成立
  W.not_(a)                NOT —— 取反
  W.child(key, pred)       把 pred 作用到 event.child(key) 这个子事件上
  W.children(key, agg)     把 agg(子事件序列) 作用到 event.children(key)
  lambda e: <bool 表达式>   任意 Python 逻辑;能跑,但 UI 只显示一个 ✓/✗,
                           没有实测值/阈值明细(没有 meta 可读)
组合子可任意层嵌套,层数不限。诊断走全量求值(**不短路**),所以 or 的第一支
已经为真时,第二支的实测值照样算出来给你看 —— 这正是调阈值时最需要的信息。

═══ 可引用字段速查 ═══
  burst (BurstEvent):
    count              int    串里 bo 的个数
    distinct_pk        int    串内不同峰的个数
    max_bar_vol_ratio  float  串内单根最大量比
    first_drought      int    串首 bo 距上一个 bo 的间隔(稀疏度)
    child("first_bo") / child("last_bo") -> BOEvent
    children("members") -> Tuple[BOEvent]
  bo (BOEvent):
    drought       Optional[int]    距上一个 bo 的间隔
    pk_count      int              击破的峰数
    vol_ratio     Optional[float]  突破当根量比
    peak_vol_max  float            峰处最大量
  tb (ThrowbackEvent):
    anchor_bo_id  str
  以上 event 都还有基类字段:start_idx / end_idx / event_id / class_id
"""
from __future__ import annotations

from typing import Optional

from path2.dag.nodes import NodeSpec
from path2.dag.edges import TemporalEdge, Child
from path2.dag.spec import PatternSpec
from path2.stdlib.app import make_app
from path2.dag import where as W
from path2.atoms.breakout import BODetector, BurstDetector
from path2.atoms.throwback import ThrowbackDetector

from .params import Params, load_params, DEFAULT_YAML_PATH    # noqa: F401 re-export 供 web worker


def build_pattern(params: Params) -> PatternSpec:
    """参数化声明工厂。**要改 where 就改这里**(burst 节点)。"""
    nodes = (
        # bo:孤立 node(无边),兼作 burst / tb 的流源
        NodeSpec("bo",
                 BODetector(**params.bo_kwargs()),
                 render_grid="price"),

        NodeSpec("burst",
                 BurstDetector(**params.burst_kwargs()),
                 # ══════════ 试验区:随便改下面这些 clause ══════════
                 where=(
                     # ① 最简形态:单个叶子比较。阈值取自 params.yaml,改 yaml 即时生效
                     #    (不用改 Python)。
                     ("first_drought",
                      W.attr("first_drought", ">=", params.burst.first_drought_min)),

                     # ② OR:两个条件满足其一即可 —— (A OR B)
                     #    比"拆成两条平级 clause"宽松:平级是 AND,这里是 OR。
                     ("pk_or_vol",
                      W.any(
                          W.attr("distinct_pk", ">=", params.burst.distinct_pk_min),
                          W.attr("max_bar_vol_ratio", ">=", params.burst.vol_spike_min),
                      )),

                     # ③ 三层嵌套:A OR (B AND NOT C)
                     #    阈值故意写字面量,方便直接改数字看判定怎么变。
                     ("nested_demo",
                      W.any(
                          W.attr("count", ">=", 3),
                          W.all(
                              W.attr("max_bar_vol_ratio", ">=", 5.0),
                              W.not_(W.attr("distinct_pk", "<=", 1)),
                          ),
                      )),

                     # ④ 嵌套进子事件:把谓词委托给 burst 串里的首个 bo。
                     #    可选 key:"first_bo" / "last_bo"。
                     #    ⚠ 已知显示局限(非本 sandbox 的 bug,core 行为):child clause 的
                     #    witness 只带实测值,不带 op/threshold —— 候选表会显示成
                     #    "2" 而不是 "2 (>=1)"。阈值在拓扑面板的规则串里能看到。
                     #    原因:阈值存在 meta["inner"] 里,而 witness 只读 meta 顶层。
                     ("first_bo_pk",
                      W.child("first_bo", W.attr("pk_count", ">=", 1))),

                     # ⑤ 【默认关闭】整组聚合:agg 收到的是 members 序列(Tuple[BOEvent])。
                     #    能跑,但裸 lambda 没有 meta → UI 只能显示 ✓/✗,无实测值。
                     # ("members_span",
                     #  W.children("members",
                     #             lambda bos: (bos[-1].end_idx - bos[0].start_idx) <= 60)),

                     # ⑥ 【默认关闭】裸 lambda:任意 Python 布尔表达式,同样无诊断明细。
                     #    想快速试一个复杂判据、暂时不在乎 UI 显示时用它。
                     # ("raw_lambda",
                     #  lambda e: (e.distinct_pk >= 2 or e.max_bar_vol_ratio >= 8.0)
                     #            and e.first_drought >= 10),
                 ),
                 # ═════════════════════════════════════════════════
                 consumes_stream="bo"),

        NodeSpec("tb",
                 ThrowbackDetector(**params.throwback_kwargs()),
                 consumes_stream="bo"),
    )
    edges = (
        # 末 bo → tb 回踩,anchor_field 保证 tb 锚定的就是这个 bo
        TemporalEdge(
            Child("burst", "last_bo"), "tb",
            min_gap=1, max_gap=params.tb.max_start_gap,
            anchor_field="anchor_bo_id",
        ),
    )
    return PatternSpec(
        # 必须与主 app 的 "bottom_burst" 不同 —— discovery 按 pattern_id 建索引
        # (path2_web/discovery.py:60),撞名会让两个 app 互相覆盖。
        pattern_id="try_complex_where",
        nodes=nodes, edges=edges,
    )


analyze, matches, PATTERN_DAG = make_app(default_params=Params.default, build_pattern=build_pattern)


def eval_meta(params: Optional[Params] = None) -> dict:
    """评估元数据(path2_web 铁律协议):end_node(买点 node)+ 首部缓冲交易日数。"""
    p = params or Params.default()
    return {
        "end_node": "tb",
        "head_buffer_trading_days": max(
            p.bo.vol_baseline_period,
            p.burst.vol_baseline_period,
            p.tb.atr_window,
            p.bo.total_window,
        ),
    }
