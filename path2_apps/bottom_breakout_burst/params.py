"""Default Params for bottom_breakout_burst pattern (nested by node)。

三件套分工:
- `params.yaml`:web 入口(scan/api/eval_runner)的 SSoT,改完下一次 /scan 即生效(热加载)。
- `Params` + 子 dataclass(BoParams/BurstParams/TbParams/EdgesParams):schema 层
  (字段名/类型),默认值是"yaml 缺失字段时兜底 + CLI 脚本 / tests fixture 默认"。
- `Params.from_yaml`/`load_params`:web 入口统一加载入口,逐 section 校验未知 key。

设计:每个 NodeSpec node(bo/burst/tb)拥有自己的子 dataclass + yaml section,
内含 detector 构造参数 + where 阈值。共用字段(tb.max_start_gap 同时被 ThrowbackDetector
和 burst→tb edge 复用)归入 tb section、edge 显式引用(SSoT)。edges 子 dataclass 留空
作格式契约/未来扩展占位。
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Type

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
    """ThrowbackDetector 构造参数。注意 max_start_gap 同时被 burst→tb edge 复用
    (语义同步:detector 启动窗紧 vs edge gap 宽 = 矛盾,故单一定义于 tb)。"""
    max_start_gap: int = 5    # tb.start − bo.end ≤ 此值(买点不离 bo 过远);edge 也用
    max_window: int = 5       # tb.end − tb.start ≤ 此值(买点窗不持续过长)
    atr_window: int = 14      # ATR 回溯窗(取 bo−1 处值)
    big_rise_k: float = 1.5
    pullback_min_atr: float = 1.0
    anchor_measure: str = "high"   # anchor 取值口径(calc.measure)
    support_measure: str = "low"   # 破位比较口径(calc.measure)


@dataclass(frozen=True)
class EdgesParams:
    """edge-内禀参数容器。当前为空:所有 edge 字段或硬编码(min_gap=1/anchor_field/
    Child(...))或从 node section 引用(max_gap = tb.max_start_gap)。保留作格式契约
    + 未来 edge-only 参数扩展占位。"""
    pass


@dataclass(frozen=True)
class Params:
    """nested by node:bo/burst/tb/edges 四 section 各自一个子 dataclass。"""
    bo: BoParams = field(default_factory=BoParams)
    burst: BurstParams = field(default_factory=BurstParams)
    tb: TbParams = field(default_factory=TbParams)
    edges: EdgesParams = field(default_factory=EdgesParams)

    @classmethod
    def default(cls) -> "Params":
        return cls()

    @classmethod
    def from_yaml(cls, path) -> "Params":
        """从 yaml 加载;顶层 + 每个 section 都校验未知 key(嵌套堵 yaml 拼错静默无效陷阱)。
        缺失 section / 缺失字段 → 用子 dataclass field default 兜底。"""
        import yaml
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        # 顶层未知 section 校验
        known_sections = {f.name for f in cls.__dataclass_fields__.values()}
        unknown_top = set(data) - known_sections
        if unknown_top:
            raise ValueError(
                f"params.yaml ({path}) 含未知顶层 section: {sorted(unknown_top)} "
                f"(已知 section: {sorted(known_sections)})"
            )
        section_classes: dict[str, Type] = {
            "bo": BoParams, "burst": BurstParams, "tb": TbParams, "edges": EdgesParams,
        }
        section_instances = {}
        for sect_name, sect_cls in section_classes.items():
            sect_data = data.get(sect_name) or {}
            sect_fields = {f.name for f in sect_cls.__dataclass_fields__.values()}
            unknown_fields = set(sect_data) - sect_fields
            if unknown_fields:
                raise ValueError(
                    f"params.yaml ({path}) section '{sect_name}' 含未知字段: "
                    f"{sorted(unknown_fields)} (可能拼错或字段已删;已知字段集见 {sect_cls.__name__})"
                )
            section_instances[sect_name] = sect_cls(**sect_data)
        return cls(**section_instances)

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
