"""批量扫描配置加载器

管理扫描配置的加载、访问和持久化。

支持双配置文件架构：
- 默认配置文件：configs/analysis/config.yaml（只读，作为默认值）
- 用户配置文件：configs/analysis/user_config.yaml（用户自定义，可覆盖）
"""

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import yaml


class UIScanConfigLoader:
    """批量扫描配置加载器（单例模式）

    采用双配置文件架构：
    - 默认配置文件：configs/analysis/config.yaml（只读）
    - 用户配置文件：configs/analysis/user_config.yaml（可覆盖）

    加载优先级：用户配置 > 默认配置
    """

    _instance = None
    _config = None
    _default_config_path = None
    _user_config_path = None
    _project_root = None
    _using_user_config = False
    _listeners: List[Callable] = []

    def __new__(cls, config_path: Optional[str] = None):
        """单例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._listeners = []
        return cls._instance

    def __init__(self, config_path: Optional[str] = None):
        """
        初始化配置加载器

        Args:
            config_path: 默认配置文件路径（可选，默认 configs/analysis/config.yaml）
        """
        if self._config is not None:
            return  # 已初始化，跳过

        if config_path is None:
            # 默认路径：项目根目录/configs/analysis/config.yaml
            current_file = Path(__file__)
            # 当前文件: .../Trade_Strategy/BreakthroughStrategy/UI/config/scan_config_loader.py
            # 项目根目录: .../Trade_Strategy
            self._project_root = current_file.parent.parent.parent.parent
            self._default_config_path = (
                self._project_root / "configs" / "analysis" / "config.yaml"
            )
        else:
            self._default_config_path = Path(config_path)
            # 项目根目录：假设配置文件在 configs/analysis/ 下
            self._project_root = self._default_config_path.parent.parent.parent

        # 用户配置文件：与默认配置同级
        self._user_config_path = (
            self._default_config_path.parent / "user_config.yaml"
        )

        self._load_config()

    def _load_config(self):
        """加载配置文件（优先用户配置，否则默认配置）"""
        if self._user_config_path.exists():
            with open(self._user_config_path, "r", encoding="utf-8") as f:
                self._config = yaml.safe_load(f)
            self._using_user_config = True
        elif self._default_config_path.exists():
            with open(self._default_config_path, "r", encoding="utf-8") as f:
                self._config = yaml.safe_load(f)
            self._using_user_config = False
        else:
            raise FileNotFoundError(
                f"配置文件不存在: {self._default_config_path}"
            )

    def reload(self):
        """重新加载配置文件"""
        self._load_config()
        self._notify_listeners()

    # ===== 监听器模式 =====

    def add_listener(self, callback: Callable):
        """添加配置变化监听器"""
        if callback not in self._listeners:
            self._listeners.append(callback)

    def remove_listener(self, callback: Callable):
        """移除监听器"""
        if callback in self._listeners:
            self._listeners.remove(callback)

    def _notify_listeners(self):
        """通知所有监听器"""
        for listener in self._listeners:
            try:
                listener()
            except Exception as e:
                print(f"Error in scan config listener: {e}")

    # ===== 项目路径 =====

    def get_project_root(self) -> Path:
        """获取项目根目录"""
        return self._project_root

    def get_config_path(self) -> Path:
        """获取当前活跃的配置文件路径"""
        if self._using_user_config:
            return self._user_config_path
        return self._default_config_path

    def get_default_config_path(self) -> Path:
        """获取默认配置文件路径"""
        return self._default_config_path

    def get_user_config_path(self) -> Path:
        """获取用户配置文件路径"""
        return self._user_config_path

    def is_using_user_config(self) -> bool:
        """返回当前是否使用用户配置"""
        return self._using_user_config

    def reset_to_default(self):
        """重置为默认配置：删除用户配置文件，加载默认配置"""
        if self._user_config_path.exists():
            self._user_config_path.unlink()
        self._load_config()
        self._notify_listeners()

    # ===== 扫描模式 =====

    def get_scan_mode(self) -> str:
        """
        获取当前扫描模式

        Returns:
            "csv" - CSV索引模式（每只股票独立时间范围）
            "global" - 全局时间范围模式
        """
        csv_file = self._config.get("data", {}).get("csv_file")
        return "csv" if csv_file else "global"

    # ===== 数据源配置 =====

    def get_data_dir(self) -> str:
        """获取股票数据目录（绝对路径）"""
        data_dir = self._config.get("data", {}).get("data_dir", "datasets/pkls")
        path = Path(data_dir)
        if not path.is_absolute():
            path = self._project_root / data_dir
        return str(path)

    def set_data_dir(self, path: str):
        """设置股票数据目录"""
        if "data" not in self._config:
            self._config["data"] = {}
        self._config["data"]["data_dir"] = path
        self._notify_listeners()

    def get_max_stocks(self) -> Optional[int]:
        """获取最大扫描股票数（None表示不限制）"""
        return self._config.get("data", {}).get("max_stocks")

    def set_max_stocks(self, n: Optional[int]):
        """设置最大扫描股票数"""
        if "data" not in self._config:
            self._config["data"] = {}
        self._config["data"]["max_stocks"] = n
        self._notify_listeners()

    # ===== 全局时间范围模式 =====

    def get_date_range(self) -> Tuple[Optional[str], Optional[str]]:
        """
        获取全局时间范围

        Returns:
            (start_date, end_date) 元组，None表示不限制
        """
        data = self._config.get("data", {})
        return (data.get("start_date"), data.get("end_date"))

    def set_date_range(self, start_date: Optional[str], end_date: Optional[str]):
        """设置全局时间范围"""
        if "data" not in self._config:
            self._config["data"] = {}
        self._config["data"]["start_date"] = start_date
        self._config["data"]["end_date"] = end_date
        self._notify_listeners()

    # ===== CSV索引模式 =====

    def get_csv_file(self) -> Optional[str]:
        """获取CSV索引文件路径"""
        return self._config.get("data", {}).get("csv_file")

    def set_csv_file(self, path: Optional[str]):
        """
        设置CSV索引文件路径

        Args:
            path: CSV文件路径，None表示禁用CSV模式
        """
        if "data" not in self._config:
            self._config["data"] = {}
        self._config["data"]["csv_file"] = path
        self._notify_listeners()

    def get_relative_months(self) -> Tuple[int, int]:
        """
        获取CSV模式的相对时间范围参数

        Returns:
            (mon_before, mon_after) 元组
        """
        data = self._config.get("data", {})
        return (data.get("mon_before", 3), data.get("mon_after", 1))

    def set_relative_months(self, mon_before: int, mon_after: int):
        """设置CSV模式的相对时间范围参数"""
        if "data" not in self._config:
            self._config["data"] = {}
        self._config["data"]["mon_before"] = mon_before
        self._config["data"]["mon_after"] = mon_after
        self._notify_listeners()

    # ===== 输出配置 =====

    def get_output_dir(self) -> str:
        """获取扫描结果输出目录（绝对路径）"""
        output_dir = self._config.get("output", {}).get(
            "output_dir", "outputs/scan_results"
        )
        path = Path(output_dir)
        if not path.is_absolute():
            path = self._project_root / output_dir
        return str(path)

    def set_output_dir(self, path: str):
        """设置扫描结果输出目录"""
        if "output" not in self._config:
            self._config["output"] = {}
        self._config["output"]["output_dir"] = path
        self._notify_listeners()

    # ===== 性能配置 =====

    def get_num_workers(self) -> int:
        """获取并行worker数量，默认为 CPU 核心数 - 2"""
        import os

        default_workers = max(1, (os.cpu_count() or 4) - 2)
        num_workers = self._config.get("performance", {}).get("num_workers")
        return num_workers if num_workers is not None else default_workers

    def set_num_workers(self, n: int):
        """设置并行worker数量"""
        if "performance" not in self._config:
            self._config["performance"] = {}
        self._config["performance"]["num_workers"] = n
        self._notify_listeners()

    # ===== 参数配置引用 =====

    def get_params_file(self) -> str:
        """获取参数配置文件路径（绝对路径）"""
        params_file = self._config.get("params", {}).get(
            "config_file", "configs/analysis/params/ui_params.yaml"
        )
        path = Path(params_file)
        if not path.is_absolute():
            path = self._project_root / params_file
        return str(path)

    def set_params_file(self, path: str):
        """设置参数配置文件路径"""
        if "params" not in self._config:
            self._config["params"] = {}
        self._config["params"]["config_file"] = path
        self._notify_listeners()

    # ===== 回测标签配置 =====

    def get_label_configs(self) -> List[Dict[str, int]]:
        """
        获取回测标签配置

        Returns:
            标签配置列表，如 [{"min_days": 5, "max_days": 20}]
            如果未配置，返回默认值
        """
        label_section = self._config.get("label", {})
        label_configs = label_section.get("label_configs", [])

        # 向后兼容：如果没有配置，使用默认值
        if not label_configs:
            return [{"min_days": 5, "max_days": 20}]

        return label_configs

    def set_label_configs(self, configs: List[Dict[str, int]]):
        """
        设置回测标签配置

        Args:
            configs: 标签配置列表，如 [{"min_days": 5, "max_days": 20}]
        """
        if "label" not in self._config:
            self._config["label"] = {}
        self._config["label"]["label_configs"] = configs
        self._notify_listeners()

    def get_label_config_string(self) -> str:
        """
        获取标签配置的字符串表示（用于 UI 显示）

        Returns:
            格式化字符串，如 "5-20"
        """
        configs = self.get_label_configs()
        if configs:
            first = configs[0]
            return f"{first.get('min_days', 5)}-{first.get('max_days', 20)}"
        return "5-20"

    def set_label_config_from_string(self, label_str: str):
        """
        从字符串解析并设置标签配置

        Args:
            label_str: 格式 "min_days-max_days"，如 "5-20"

        Raises:
            ValueError: 格式不正确或数值无效
        """
        parts = label_str.strip().split("-")
        if len(parts) != 2:
            raise ValueError(f"Invalid format: expected 'min-max', got '{label_str}'")

        try:
            min_days = int(parts[0].strip())
            max_days = int(parts[1].strip())
        except ValueError:
            raise ValueError(f"Invalid numbers in '{label_str}'")

        if min_days <= 0 or max_days <= 0:
            raise ValueError("Days must be positive")
        if min_days >= max_days:
            raise ValueError("min_days must be less than max_days")

        self.set_label_configs([{"min_days": min_days, "max_days": max_days}])

    # ===== 完整配置 =====

    def get_all_config(self) -> Dict[str, Any]:
        """获取完整配置（副本）"""
        return self._config.copy()

    # ===== 持久化 =====

    def save(self):
        """保存配置到用户配置文件"""
        with open(self._user_config_path, "w", encoding="utf-8") as f:
            yaml.dump(
                self._config,
                f,
                allow_unicode=True,
                default_flow_style=False,
                sort_keys=False,
            )
        self._using_user_config = True

    # ===== 便捷方法 =====

    def load_csv_stock_list(self) -> Dict[str, Tuple[str, str]]:
        """
        加载CSV股票列表并计算每只股票的时间范围

        Returns:
            Dict[symbol, (start_date, end_date)]

        Raises:
            ValueError: 未配置CSV文件或CSV模式未启用
            FileNotFoundError: CSV文件不存在
        """
        csv_file = self.get_csv_file()
        if not csv_file:
            raise ValueError("CSV mode not enabled (csv_file is null)")

        mon_before, mon_after = self.get_relative_months()

        # 复用 batch_scan.py 的解析逻辑
        return self._parse_csv_stock_list(csv_file, mon_before, mon_after)

    def _parse_csv_stock_list(
        self, csv_path: str, mon_before: int, mon_after: int
    ) -> Dict[str, Tuple[str, str]]:
        """
        解析CSV文件，计算每只股票的时间范围

        Args:
            csv_path: CSV文件路径
            mon_before: 基准日期前N个月
            mon_after: 基准日期后N个月

        Returns:
            Dict[symbol, (start_date, end_date)]
        """
        import pandas as pd
        from dateutil.relativedelta import relativedelta

        csv_path = Path(csv_path)
        if not csv_path.exists():
            raise FileNotFoundError(f"CSV file not found: {csv_path}")

        # 读取CSV
        try:
            df = pd.read_csv(csv_path)
        except Exception as e:
            raise ValueError(f"Failed to read CSV file: {e}")

        # 验证必需列
        if "date" not in df.columns or "name" not in df.columns:
            raise ValueError(
                f"CSV must contain 'date' and 'name' columns. "
                f"Found columns: {list(df.columns)}"
            )

        # 参数验证
        if mon_before < 0 or mon_after < 0:
            raise ValueError(
                f"mon_before and mon_after must be non-negative, "
                f"got mon_before={mon_before}, mon_after={mon_after}"
            )

        # 计算相对时间范围
        stock_time_ranges = {}
        failed_symbols = []

        for idx, row in df.iterrows():
            try:
                symbol = str(row["name"]).strip()
                if not symbol:
                    raise ValueError("Empty symbol name")

                base_date = pd.to_datetime(row["date"])

                # 使用 relativedelta 精确计算月份
                start_date = base_date - relativedelta(months=mon_before)
                end_date = base_date + relativedelta(months=mon_after)

                stock_time_ranges[symbol] = (
                    start_date.strftime("%Y-%m-%d"),
                    end_date.strftime("%Y-%m-%d"),
                )
            except Exception as e:
                failed_symbols.append(f"Row {idx + 2}: {symbol} - {str(e)}")

        # 报告解析失败
        if failed_symbols:
            print(f"警告: {len(failed_symbols)} 条记录解析失败:")
            for msg in failed_symbols[:5]:
                print(f"  - {msg}")
            if len(failed_symbols) > 5:
                print(f"  ... 还有 {len(failed_symbols) - 5} 个错误")

        # 确保至少有一只有效股票
        if not stock_time_ranges:
            raise ValueError(
                f"No valid stocks found in CSV file. "
                f"Total rows: {len(df)}, Failed: {len(failed_symbols)}"
            )

        return stock_time_ranges

    def get_scan_summary(self) -> str:
        """
        获取当前扫描配置的摘要描述

        Returns:
            配置摘要字符串，如 "CSV mode: 150 stocks, ±6/1 months"
        """
        mode = self.get_scan_mode()

        if mode == "csv":
            csv_file = self.get_csv_file()
            mon_before, mon_after = self.get_relative_months()
            csv_name = Path(csv_file).name if csv_file else "unknown"
            return f"CSV: {csv_name} (±{mon_before}/{mon_after} months)"
        else:
            start, end = self.get_date_range()
            start_str = start or "beginning"
            end_str = end or "now"
            return f"Global: {start_str} ~ {end_str}"


def get_ui_scan_config_loader(
    config_path: Optional[str] = None,
) -> UIScanConfigLoader:
    """
    获取全局扫描配置加载器实例（单例模式）

    Args:
        config_path: 配置文件路径（可选）

    Returns:
        UIScanConfigLoader实例
    """
    return UIScanConfigLoader(config_path)
