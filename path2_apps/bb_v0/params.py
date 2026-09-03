"""Default Params for bb_v0 pattern (V1 throwback 完整备份)。

三件套分工:
- `params.yaml`:web 入口(scan/api/eval_runner)的 SSoT,改完下一次 /scan 即生效(热加载)。
- `Params` + 子 dataclass(BoParams/BurstParams/TbParams/EdgesParams):schema 层
  (字段名/类型),默认值是"yaml 缺失字段时兜底 + CLI 脚本 / tests fixture 默认"。
- `Params.from_yaml`/`load_params`:web 入口统一加载入口,逐 section 校验未知 key。

设计:每个 NodeSpec node(bo/burst/tb)拥有自己的子 dataclass + yaml section,
内含 detector 构造参数 + where 阈值。共用字段(tb.max_start_gap 同时被 ThrowbackDetectorV1
和 burst→tb edge 复用)归入 tb section、edge 显式引用(SSoT)。edges 子 dataclass 留空
作格式契约/未来扩展占位。
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

from path2_apps._params_base import ParamsBase

DEFAULT_YAML_PATH = Path(__file__).parent / "params.yaml"


@dataclass(frozen=True)
class BoParams:
    """BODetector 构造参数。"""
    total_window: int = 10
    min_side_bars: int = 2
    min_relative_height: float = 0.05
    exceed_threshold: float = 0.005
    peak_supersede_threshold: float = 0.03
    bear_drop: Optional[float] = None   # 大阴线 kind:实体跌幅阈值;None=禁用(默认 OFF,仅显式 ON 的 app 启用)
    bear_min_rh: float = 0.20   # 大阴线 kind:相对高度阈值
    vol_baseline_period: int = 63
    peak_measure: str = "high"
    breakout_measure: str = "high"


@dataclass(frozen=True)
class BurstParams:
    """BurstDetector 构造参数(gap_max/min_bos/vol_baseline_period) +
    burst node 的 where 阈值(first_drought_min/distinct_pk_min/vol_spike_min)。

    隐含约束:first_drought_min 必须 > gap_max,否则 first_drought where 退化恒真
    (chain 簇首必是断点,drought > gap_max 结构性必然)。默认 20 > 5 健康。
    """
    gap_max: int = 5
    vol_baseline_period: int = 63
    min_bos: int = 2                # BurstDetector 切串长度 + 业务约束②
    first_drought_min: int = 20     # burst where 阈值(原 THR_DROUGHT)
    distinct_pk_min: int = 4        # burst where 阈值(原 THR_PK)
    vol_spike_min: float = 8.0      # burst where 阈值(原 THR_VOL)


@dataclass(frozen=True)
class TbParams:
    """ThrowbackDetectorV0 构造参数(锚 last_bo 变体:九参数集对应 throwback_v0)。

    anchor 语义 = last_bo 上一根 bar 的 anchor_measure 价(非串内 min)。
    默认值 = p2.yaml 的 tb 段(low/low/no_new_low/close 调参版)。
    """
    max_start_gap: int = 7   # confirm_idx − bo.end ≤ 此值;edge 也用
    max_window: int = 5       # tb.end − tb.start ≤ 此值(买点窗不持续过长)
    atr_window: int = 14      # ATR 回溯窗(取 bo−1 处值)
    big_rise_k: float = 5     # 大涨脱离阈值倍数(high − base_min ≥ k*atr)
    stop_confirm_bars: int = 1   # K bar trough-age 确认阈值
    anchor_measure: str = "low"   # anchor 取值口径(calc.measure)
    support_measure: str = "low"  # 破位比较口径(calc.measure)
    scb_mode: str = "no_new_low"    # confirm 的 SCB 满足方式:no_new_low(现状)/rising(连续不降计数)
    scb_measure: str = "close"      # 判断不创新低/逐步升高的价格口径(calc.measure)


@dataclass(frozen=True)
class EdgesParams:
    """edge-内禀参数容器。当前为空:所有 edge 字段或硬编码(min_gap=1/anchor_field/
    Child(...))或从 node section 引用(max_gap = tb.max_start_gap)。保留作格式契约
    + 未来 edge-only 参数扩展占位。"""
    pass


@dataclass(frozen=True)
class Params(ParamsBase):
    """nested by node:bo/burst/tb/edges 四 section 各自一个子 dataclass。
    读写协议(default / from_yaml / to_dict / from_dict)继承自 ParamsBase;
    本类只留 section 定义 + 各 detector 的 *_kwargs 映射(业务)。"""
    bo: BoParams = field(default_factory=BoParams)
    burst: BurstParams = field(default_factory=BurstParams)
    tb: TbParams = field(default_factory=TbParams)
    edges: EdgesParams = field(default_factory=EdgesParams)

    def bo_kwargs(self) -> dict:
        """BODetector 构造参数(字段一一对应签名)。"""
        return asdict(self.bo)

    def burst_kwargs(self) -> dict:
        """BurstDetector 构造参数(切串参数:gap_max/min_bos/vol_baseline_period)。
        阈值走 burst node 的 where,不传给 detector。"""
        return {
            'gap_max': self.burst.gap_max,
            'min_bos': self.burst.min_bos,
            'vol_baseline_period': self.burst.vol_baseline_period,
        }

    def throwback_kwargs(self) -> dict:
        """ThrowbackDetectorV1 构造参数(字段一一对应签名)。"""
        return asdict(self.tb)


def load_params() -> Params:
    """web 入口统一加载点:读 DEFAULT_YAML_PATH 的 yaml 作 Params(SSoT,热加载)。
    每次调用都重新读 yaml 文件,故 web /scan 每次请求都见最新 yaml(无需重启)。"""
    return Params.from_yaml(DEFAULT_YAML_PATH)
