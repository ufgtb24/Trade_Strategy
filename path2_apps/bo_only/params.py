"""Default Params for bo_only pattern。

单 BODetector 节点 pattern 的参数 schema:仅含 bo section + load_params()。
与 bottom_breakout_burst.params 同形式,独立 yaml 文件。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from path2_apps._params_base import ParamsBase

DEFAULT_YAML_PATH = Path(__file__).parent / "params.yaml"


@dataclass(frozen=True)
class BoParams:
    """BODetector 构造参数(与 bottom_breakout_burst.params.BoParams 同 schema)。"""
    total_window: int = 10
    min_side_bars: int = 2
    min_relative_height: float = 0.05
    exceed_threshold: float = 0.005
    peak_supersede_threshold: float = 0.03
    vol_baseline_period: int = 63
    peak_measure: str = "high"
    breakout_measure: str = "high"


@dataclass(frozen=True)
class Params(ParamsBase):
    """bo_only 全部 params:仅 bo section。
    读写协议(default / from_yaml / to_dict / from_dict)继承自 ParamsBase。"""
    bo: BoParams = field(default_factory=BoParams)

    def bo_kwargs(self) -> dict:
        return {f.name: getattr(self.bo, f.name) for f in BoParams.__dataclass_fields__.values()}


def load_params() -> Params:
    """读 params.yaml(SSoT)。yaml 缺失 → Params.default()。"""
    if DEFAULT_YAML_PATH.exists():
        return Params.from_yaml(DEFAULT_YAML_PATH)
    return Params.default()
