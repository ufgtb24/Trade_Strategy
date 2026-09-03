"""Default Params for bb_v1 pattern (V1 throwback 完整备份)。

三件套分工:
- `params.yaml`:web 入口(scan/api/eval_runner)的 SSoT,改完下一次 /scan 即生效(热加载)。
- `Params` + 子 dataclass(BoParams/BurstParams/TbParams/EdgesParams):schema 层
  (字段名/类型),默认值是"yaml 缺失字段时兜底 + CLI 脚本 / tests fixture 默认"。
- `Params.from_yaml`/`load_params`:web 入口统一加载入口,逐 section 校验未知 key。

设计:每个 NodeSpec node(bo/burst/tb)拥有自己的子 dataclass + yaml section,
内含 detector 构造参数 + where 阈值。共用字段(tb.max_span 同时被 ThrowbackDetectorV1
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
    burst node 的 where 阈值(first_drought_min/distinct_pk_min/vol_spike_min/peak_age_min)。

    隐含约束:first_drought_min 必须 > gap_max,否则 first_drought where 退化恒真
    (chain 簇首必是断点,drought > gap_max 结构性必然)。默认 20 > 5 健康。
    """
    gap_max: int = 5
    vol_baseline_period: int = 63
    min_bos: int = 2                # BurstDetector 切串长度 + 业务约束②
    first_drought_min: int = 20     # burst where 阈值(原 THR_DROUGHT)
    distinct_pk_min: int = 4        # burst where 阈值(原 THR_PK)
    vol_spike_min: float = 8.0      # burst where 阈值(原 THR_VOL)
    peak_age_min: int = 125     # burst where 阈值:簇内某 bo 距其突破峰 ≥ 此 bar 数(防阴跌反弹,无结构性下界约束)


@dataclass(frozen=True)
class TbParams:
    """ThrowbackDetectorV1 构造参数(5 个,首段即停状态机,2026-08-25 重写)+ tb node where 阈值。

    资格型门槛不进 detector:max_day_drop_pct 只作 tb where(W.attr("max_day_drop", "<", thr)),
    throwback_kwargs() 不含它。max_span 同时是 burst→tb edge 的 max_gap(SSoT)。
    默认值:max_rise_k / stop_confirm_bars / vol_window 沿用 v4 定值;max_span=20 为占位,
    由 2026-08-25 验证闸三档对比后拍板。
    """
    max_rise_k: float = 1.5          # 反弹/脱离阈值(median TR 倍数),DOWN→UP 与 STABLE rise 共用
    stop_confirm_bars: int = 1       # K 根不刷新入段(enter = 第 K 根不刷新根)
    vol_window: int = 14             # median TR 滚动窗(即时取 i-1)
    max_span: int = 20               # 全局预算 [bo+1, bo+max_span];edge max_gap 同值
    measure: str = "close"           # 全部数值比较口径(calc.measure);阴线臂恒 close/open
    max_day_drop_pct: Optional[float] = 0.20  # 资格型 where 阈值:回踩段单日跌幅 ≥ 此值 → where 拦;None=不加该 where


@dataclass(frozen=True)
class EdgesParams:
    """edge-内禀参数容器。当前为空:所有 edge 字段或硬编码(min_gap=1/anchor_field/
    Child(...))或从 node section 引用(max_gap = tb.max_span)。保留作格式契约
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
        """ThrowbackDetectorV1 构造参数(5 键);max_day_drop_pct 是 where 阈值,不传 detector。"""
        d = asdict(self.tb)
        d.pop('max_day_drop_pct')
        return d


def load_params() -> Params:
    """web 入口统一加载点:读 DEFAULT_YAML_PATH 的 yaml 作 Params(SSoT,热加载)。
    每次调用都重新读 yaml 文件,故 web /scan 每次请求都见最新 yaml(无需重启)。"""
    return Params.from_yaml(DEFAULT_YAML_PATH)
