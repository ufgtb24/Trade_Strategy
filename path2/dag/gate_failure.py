"""GateFailure · attempt 短路失败时 detector 吐给 on_gate hook 的记录。

承 spec §2.4.1 · failure_event_window 语义 = attempt 判据评估的实测轨迹。
"""
# on_gate 编写指南(四条: attempt 边界 / failure_event_window / evaluation_lookback /
# measured.kind)已迁入 .claude/skills/authoring-path2-detector/reference.md §4。
import os
import sys
from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class MeasuredKindAware:
    """kind-aware measured · 承硬伤 E · 前端按 kind 分派 fmt(shared/formatters.ts)。

    kind 是自由字符串、非闭合枚举:detector/edge 作者可为新 gate 自造新 kind;
    前端 formatters.ts 若无对应 case,走 default 分支落原值(不报错、只是没前缀)。

    截至 2026-07-08 生产实际传出的 kind:
    - Detector 侧(GateFailure.measured):
        · 'gap'                   BODetector · atr 距离过近判据
        · 'count'                 BODetector bo数 / TB 预算扫满无段(v4 budget_no_stable)
        · 'anchor_delta'          TB phase1/phase2_break · 破位偏移
        · 'pullback_atr'          TB 阶段一 · 回落深度/atr
        · 'breakout_price'        BODetector · 突破价
        · 'window_start'          BODetector · 窗口起点
        · 'side_bars_offset'      BODetector · 峰-窗首侧翼
        · 'peak_idx'              BODetector · 已存在 peak 索引
        · 'window_min_low'        BODetector · 窗口最低价
        · 'relative_height'       BODetector · 相对高度
    - Edge 侧(EdgeWitness.measured · dag/_reify._make_measured):
        · 'gap'                   邻接 Edge
        · 'window_offset'         Containment / Overlap / Equals
        · 'anchor_delta'          anchor 边
        · 'negation_bars'         NegationEdge
        · 'unknown'               兜底 · 未识别 edge 类型

    formatters.ts 已有专属前缀 case:gap / anchor_delta / negation_bars /
    window_offset / unknown / strict_clear(留位、生产未使用);其余 kind →
    default 分支落 String(val)。
    """
    kind: str
    value: Any
    label: str


@dataclass(frozen=True)
class GateFailure:
    """一次 attempt 短路失败的完整记录。
    - failure_event_window: (start_idx, gate_idx) 实测轨迹;点事件 = (i, i)
    - start_idx: attempt 判据评估的起点
    - gate_idx: gate 触发所在 bar(= failure event end 兜底)
    - anchor_bar: 语义锚(bar 位置)
    - op / threshold_param: spec 2026-07-13 · 通过条件比较符 + params.yaml 短名。
      契约不变式(spec 2026-07-12 放松版):threshold_param is not None ==> op is not None。
      sentinel-numeric 场景允许 op 非 None + threshold_param None。
    - evaluation_lookback: detector 内部判据依赖的历史窗;不参与 ⊆ 判据(tooltip 显示)
    - code_location: spec 2026-07-12 · sys._getframe 自动抓 caller
    """
    failure_event_window: tuple[int, int]
    start_idx: int
    gate_idx: int
    anchor_bar: int
    gate_name: str
    measured: MeasuredKindAware
    threshold: Any
    op: Optional[str]
    threshold_param: Optional[str]
    evaluation_lookback: Optional[tuple[int, int]]
    symbol: str
    # 追加字段, 带默认值 → 既有 kwargs 构造点全兼容(先例:code_location)
    node_id: str = ''   # 所属 node_id(gate_collector per-node wrapper 注入;detector 构造阶段为空)
    stream: Optional[str] = None   # 所属命名流(gate_collector 路由用;单流恒 None)
    code_location: str = ''

    def __post_init__(self):
        """自动抓 caller 位置写入 code_location(仅当调用方未显式传值).

        帧遍历规则(spec 2026-07-12 §2.2):
        1. 跳过 gate_failure.py 内部帧(本 __post_init__)
        2. 跳过 dataclass 自动生成的 __init__ 帧(CPython 3.12 里 filename='<string>'
           或 funcname='__init__' 兜底)
        3. 跳过 throwback 系模块的 _emit_tb_gate* helper 帧(v1/v3/v4,前缀匹配)
        4. 落到首个"真 caller"帧, 写入 '{basename}:{lineno}'

        显式传入非空 code_location 时直接跳过, 便于测试固定值.
        用 object.__setattr__ 绕 frozen 限制 —— 标准 post-init 惯用法.
        """
        if self.code_location:
            return
        frame = sys._getframe(1)
        try:
            while frame is not None:
                filename = os.path.basename(frame.f_code.co_filename)
                funcname = frame.f_code.co_name
                if filename == 'gate_failure.py':
                    frame = frame.f_back
                    continue
                if filename == '<string>' or funcname == '__init__':
                    frame = frame.f_back
                    continue
                if funcname.startswith('_emit_tb_gate'):
                    frame = frame.f_back
                    continue
                object.__setattr__(
                    self, 'code_location', f'{filename}:{frame.f_lineno}'
                )
                return
            object.__setattr__(self, 'code_location', '<unknown>')
        finally:
            del frame  # 避免帧引用循环
