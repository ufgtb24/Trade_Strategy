"""加载 trial 产出的 filter.yaml，提取 Top-1 模板和扫描参数。"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class TrialBundle:
    """Trial 加载后的完整上下文。

    Attributes:
        template: filter.yaml 中 median 最高的模板 dict
        thresholds: {factor_key: threshold_value}
        negative_factors: 方向修正后的负向因子集合（mode=lte 的因子）
        scan_params: filter.yaml.scan_params 原样 dict，包含
                     breakout_detector / general_feature / quality_scorer
    """
    template: dict[str, Any]
    thresholds: dict[str, float]
    negative_factors: frozenset[str]
    scan_params: dict[str, Any]


class TrialLoader:
    """从 trial 目录加载 filter.yaml。"""

    def __init__(self, trial_dir: Path):
        self.trial_dir = Path(trial_dir)

    def load(self) -> TrialBundle:
        """加载 filter.yaml 并构造 TrialBundle。

        Raises:
            FileNotFoundError: 如果 trial_dir/filter.yaml 不存在
        """
        filter_yaml = self.trial_dir / "filter.yaml"
        if not filter_yaml.exists():
            raise FileNotFoundError(f"filter.yaml not found: {filter_yaml}")

        with open(filter_yaml, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        templates = data.get("templates", [])
        if not templates:
            raise ValueError(f"filter.yaml has no templates: {filter_yaml}")

        # Top-1 = median 最高（与 validator 的 shrinkage_k=1 对齐）
        top_1 = max(templates, key=lambda t: t.get("median", 0.0))

        meta = data.get("_meta", {})
        optimization = meta.get("optimization", {})
        thresholds = optimization.get("thresholds", {})
        negative_factors = frozenset(optimization.get("negative_factors", []))

        scan_params = data.get("scan_params", {})

        return TrialBundle(
            template=top_1,
            thresholds=thresholds,
            negative_factors=negative_factors,
            scan_params=scan_params,
        )
