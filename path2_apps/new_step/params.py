"""new_step 的参数(nested by node)。

三件套分工:
- `params.yaml`:web 入口(scan/api/eval_runner)的 SSoT,改完下一次 /scan 即生效(热加载)。
- `Params` + 子 dataclass(PlateauParams/EdgesParams):schema 层(字段名/类型),默认值是
  "yaml 缺失字段时兜底 + CLI 脚本 / tests fixture 默认"。
- `Params.from_yaml`/`load_params`:web 入口统一加载入口,逐 section 校验未知 key。

设计:整个 pattern 只有一个有 detector 的 node `plateau`,它的 section 同时装
PlateauDetector 的四个构造参数与 plateau where 的九个阈值(step / today 两个子结构 node
的诊断层 where 与父 where 共用同一批阈值,不另设 section)。零边,edges 子 dataclass 留空作格式
契约/未来扩展占位。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from path2_apps._params_base import ParamsBase

DEFAULT_YAML_PATH = Path(__file__).parent / "params.yaml"


@dataclass(frozen=True)
class PlateauParams:
    """PlateauDetector 构造参数(前四个) + plateau where 阈值(其余九个)。

    阈值待验证:初值从用户 10 个正样本量出、留余量。
    """
    # ---- PlateauDetector 构造参数 ----
    old_window: int = 15          # 旧平台根数,也是开段时回看波动的窗(待验证:初值从用户 10 个正样本量出、留余量)
    strong_k: float = 3.0         # 开段 / 并入阶跃的倍数(待验证:初值从用户 10 个正样本量出、留余量)
    max_step_bars: int = 5        # 一段阶跃最多几根(待验证:初值从用户 10 个正样本量出、留余量)
    max_days: int = 40            # 当天距阶跃末根最多几根(待验证:初值从用户 10 个正样本量出、留余量)
    # ---- where 阈值 ----
    old_flat_max: float = 1.2     # 旧平台平:旧平台振幅 / 阶跃高度 上限(待验证:初值从用户 10 个正样本量出、留余量)
    step_rise_min: float = 0.4    # 大涨幅:阶跃累计涨幅下限(待验证:初值从用户 10 个正样本量出、留余量)
    vs_left_min: float = 4.0      # 阶跃比左侧强:阶跃最大单根涨幅 / 旧平台波动 下限(待验证:初值从用户 10 个正样本量出、留余量)
    vs_right_min: float = 2.5     # 阶跃比右侧强:阶跃最大单根涨幅 / 新平台波动 下限(待验证:初值从用户 10 个正样本量出、留余量)
    step_vol_min: float = 3.0     # 平台交界放量:阶跃最大成交量 / 旧平台平均量 下限(待验证:初值从用户 10 个正样本量出、留余量)
    keep_min: float = 0.3         # 新平台守住:新平台最低收盘守住阶跃高度的几成 下限(待验证:初值从用户 10 个正样本量出、留余量)
    calm_max: float = 0.6         # 波动小:新平台振幅 / 阶跃高度 上限(待验证:初值从用户 10 个正样本量出、留余量)
    vs_high_max: float = 1.0      # 没追涨:当天收盘 / 阶跃以来最高价 上限(严格小于)(待验证:初值从用户 10 个正样本量出、留余量)
    body_min: float = 0.0         # 收阳:当天收盘 / 开盘 - 1 下限(严格大于)(待验证:初值从用户 10 个正样本量出、留余量)


@dataclass(frozen=True)
class EdgesParams:
    """edge-内禀参数容器。new_step 零边,当前为空;保留作格式契约 + 未来扩展占位。"""
    pass


@dataclass(frozen=True)
class Params(ParamsBase):
    """nested by node:plateau/edges 两 section 各自一个子 dataclass。
    读写协议(default / from_yaml / to_dict / from_dict)继承自 ParamsBase;
    本类只留 section 定义 + detector 的 *_kwargs 映射(业务)。"""
    plateau: PlateauParams = field(default_factory=PlateauParams)
    edges: EdgesParams = field(default_factory=EdgesParams)

    def plateau_kwargs(self) -> dict:
        """PlateauDetector 构造参数(四个结构参数)。阈值走 where,不传给 detector。"""
        return {
            'old_window': self.plateau.old_window,
            'strong_k': self.plateau.strong_k,
            'max_step_bars': self.plateau.max_step_bars,
            'max_days': self.plateau.max_days,
        }


def load_params() -> Params:
    """web 入口统一加载点:读 DEFAULT_YAML_PATH 的 yaml 作 Params(SSoT,热加载)。
    每次调用都重新读 yaml 文件,故 web /scan 每次请求都见最新 yaml(无需重启)。"""
    return Params.from_yaml(DEFAULT_YAML_PATH)
