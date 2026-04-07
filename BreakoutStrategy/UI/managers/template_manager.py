"""模板匹配管理器 — 加载 filter YAML 并执行突破-模板匹配"""

import yaml
from pathlib import Path


class TemplateManager:
    """加载组合模板配置并匹配突破"""

    def __init__(self):
        self.templates = []
        self.thresholds = {}
        self.negative_factors = frozenset()
        self.sample_size = 0
        self._loaded = False
        self.scan_params = {}

    @property
    def loaded(self) -> bool:
        return self._loaded

    def load_filter_yaml(self, path: str) -> dict:
        """加载 filter YAML 文件。

        Args:
            path: YAML 文件路径

        Returns:
            解析后的完整 YAML dict
        """
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        meta = data.get("_meta", {})
        optimization = meta.get("optimization", {})

        self.templates = data.get("templates", [])
        self.thresholds = optimization.get("thresholds", {})
        self.negative_factors = frozenset(optimization.get("negative_factors", []))
        self.sample_size = meta.get("sample_size", 0)
        self.scan_params = data.get("scan_params", {})
        self._loaded = True

        return data

    def get_template_display_list(self) -> list[dict]:
        """返回模板显示信息列表，按 median 降序排列。

        Returns:
            [{"name": str, "median": float, "count": int, "ratio": float}, ...]
        """
        result = []
        for tmpl in self.templates:
            count = tmpl.get("count", 0)
            ratio = (count / self.sample_size * 100) if self.sample_size > 0 else 0.0
            result.append({
                "name": tmpl["name"],
                "median": tmpl.get("median", 0.0),
                "count": count,
                "ratio": ratio,
            })
        result.sort(key=lambda x: x["median"], reverse=True)
        return result

    def match_breakout(self, bo_data: dict, template: dict) -> bool:
        """判断单个突破是否匹配模板。

        Args:
            bo_data: 突破数据 dict（来自 JSON 或 Breakout 对象属性）
            template: 模板 dict，包含 "factors" 列表

        Returns:
            是否所有因子均满足阈值
        """
        for factor in template["factors"]:
            threshold = self.thresholds.get(factor)
            if threshold is None:
                continue  # 该因子无阈值配置，跳过
            value = bo_data.get(factor)
            if value is None:
                return False
            if factor in self.negative_factors:
                if value > threshold:
                    return False
            else:
                if value < threshold:
                    return False
        return True

    def match_stock(self, stock_result: dict, template: dict) -> list[int]:
        """返回某只股票中匹配模板的突破索引列表。

        Args:
            stock_result: scan_data["results"] 中的单个股票 dict
            template: 选中的模板 dict

        Returns:
            匹配的突破在 breakouts 列表中的索引
        """
        matched_indices = []
        for i, bo in enumerate(stock_result.get("breakouts", [])):
            if self.match_breakout(bo, template):
                matched_indices.append(i)
        return matched_indices

    def match_all_stocks(self, scan_data: dict, template: dict) -> dict:
        """批量匹配所有股票。

        Args:
            scan_data: 完整的 scan_results dict
            template: 选中的模板 dict

        Returns:
            {symbol: [matched_breakout_indices]}
        """
        result = {}
        for stock in scan_data.get("results", []):
            if "error" in stock:
                continue
            symbol = stock["symbol"]
            matched = self.match_stock(stock, template)
            result[symbol] = matched
        return result

    def find_template_by_name(self, name: str) -> dict | None:
        """按名称查找模板。"""
        for tmpl in self.templates:
            if tmpl["name"] == name:
                return tmpl
        return None

    def check_compatibility(self, scan_metadata: dict) -> tuple[bool, list[str]]:
        """检查 scan_results 的参数与模板 scan_params 是否兼容。

        Args:
            scan_metadata: JSON 文件的 scan_metadata dict

        Returns:
            (is_compatible, mismatch_details)
        """
        if not self.scan_params:
            return True, []  # 旧版模板无 scan_params，跳过检查

        mismatches = []

        # 1. 比较 detector_params
        template_detector = self.scan_params.get("breakout_detector", {})
        json_detector = scan_metadata.get("detector_params", {})
        detector_keys = [
            "total_window", "min_side_bars", "min_relative_height",
            "exceed_threshold", "peak_supersede_threshold",
            "peak_measure", "breakout_mode",
        ]
        for key in detector_keys:
            t_val = template_detector.get(key)
            j_val = json_detector.get(key)
            if t_val is not None and j_val is not None and t_val != j_val:
                mismatches.append(f"detector.{key}: template={t_val}, scan={j_val}")

        # 2. 比较 feature_calculator_params（结构映射）
        template_general = self.scan_params.get("general_feature", {})
        template_quality = self.scan_params.get("quality_scorer", {})
        json_feature = scan_metadata.get("feature_calculator_params", {})

        feature_map = {
            ("general_feature", "atr_period"): "atr_period",
            ("general_feature", "ma_period"): "ma_period",
            ("general_feature", "stability_lookforward"): "stability_lookforward",
            ("quality_scorer.pbm_factor", "lookback"): "continuity_lookback",
            ("quality_scorer.overshoot_factor", "gain_window"): "gain_window",
            ("quality_scorer.pk_mom_factor", "lookback"): "pk_lookback",
        }
        for (source, src_key), json_key in feature_map.items():
            if source == "general_feature":
                t_val = template_general.get(src_key)
            else:
                factor_name = source.split(".")[-1]
                t_val = template_quality.get(factor_name, {}).get(src_key)
            j_val = json_feature.get(json_key)
            if t_val is not None and j_val is not None and t_val != j_val:
                mismatches.append(f"feature.{json_key}: template={t_val}, scan={j_val}")

        return len(mismatches) == 0, mismatches

    def get_scan_params(self) -> dict:
        """返回模板嵌入的扫描参数（完整 all_factor.yaml 结构）"""
        return self.scan_params

    def clear(self):
        """清空状态。"""
        self.templates = []
        self.thresholds = {}
        self.negative_factors = frozenset()
        self.sample_size = 0
        self.scan_params = {}
        self._loaded = False
