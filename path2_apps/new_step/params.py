"""new_step 的参数(nested by node)。

三件套分工:
- `params.yaml`:web 入口(scan/api/eval_runner)的 SSoT,改完下一次 /scan 即生效(热加载)。
- `Params` + 子 dataclass(BoParams/BurstParams/TbParams/EdgesParams):schema 层
  (字段名/类型),默认值是"yaml 缺失字段时兜底 + CLI 脚本 / tests fixture 默认"。
- `Params.from_yaml`/`load_params`:web 入口统一加载入口,逐 section 校验未知 key。

设计:每个 NodeSpec node(bo/burst/tb)拥有自己的子 dataclass + yaml section,
内含 detector 构造参数 + where 阈值。共用字段(tb.max_span 同时被 ThrowbackDetectorV4
和 burst→tb edge 复用)归入 tb section、edge 显式引用(SSoT)。edges 子 dataclass 留空
作格式契约/未来扩展占位。
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path

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
    vol_baseline_period: int = 63
    peak_measure: str = "high"
    breakout_measure: str = "high"


@dataclass(frozen=True)
class BurstParams:
    """BurstDetector 构造参数(gap_max/min_bos/vol_baseline_period) +
    burst node 的 where 阈值(distinct_pk_min/vol_spike_min)。

    不设「突破前沉寂多久」的闸:标注里「底部平稳」只是加分项,不是必须条件。
    """
    gap_max: int = 8
    vol_baseline_period: int = 63
    min_bos: int = 1                # BurstDetector 切串长度
    distinct_pk_min: int = 2        # 站上新平台:这串突破越过的不同峰数下限
    vol_spike_min: float = 5.0      # 阶跃放量:串内最大单根量比下限


@dataclass(frozen=True)
class TbParams:
    """ThrowbackDetectorV4 构造参数(2026-08-16 三态状态机换代,spec §8 参数表)。

    六字段与 ThrowbackDetectorV4.__init__ 一一对应。max_span 同时被
    burst→tb edge 复用(SSoT 单一定义:edge 语义 = 首段 enter 与 bo 的 gap
    上限,与状态机扫描预算 bo+1..bo+max_span 同源)。
    """
    max_rise_k: float = 1.5        # 反弹/脱离阈值,vol(i) 倍数;DOWN→UP 与 STABLE→UP 两臂共用
    stop_confirm_bars: int = 1     # 不刷新根数 K(达 K 当根入段)
    vol_window: int = 14           # median TR 滚动窗(即时取 i-1);非 Wilder ATR
    anchor_mode: str = "span_min"  # global_bottom 取法:'last_bo'/'min_bo'/'span_min'
    max_span: int = 60             # 全局预算(burst 末起);edge 的 max_gap 也用
    measure: str = "close"         # 单一口径(全部比较同口径)


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
        """ThrowbackDetector 构造参数(字段一一对应签名)。"""
        return asdict(self.tb)


def load_params() -> Params:
    """web 入口统一加载点:读 DEFAULT_YAML_PATH 的 yaml 作 Params(SSoT,热加载)。
    每次调用都重新读 yaml 文件,故 web /scan 每次请求都见最新 yaml(无需重启)。"""
    return Params.from_yaml(DEFAULT_YAML_PATH)
