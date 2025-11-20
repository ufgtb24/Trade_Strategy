"""可视化界面配置加载器"""

from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


class UIConfigLoader:
    """可视化界面配置加载器（单例模式）"""

    _instance = None
    _config = None
    _project_root = None

    def __new__(cls, config_path: Optional[str] = None):
        """单例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, config_path: Optional[str] = None):
        """
        初始化配置加载器

        Args:
            config_path: 配置文件路径（可选）
        """
        if self._config is not None:
            return  # 已初始化，跳过

        if config_path is None:
            # 默认路径：项目根目录/configs/visualization/ui_config.yaml
            # 从当前文件向上查找项目根目录
            current_file = Path(__file__)
            # 当前文件: .../Trade_Strategy/BreakthroughStrategy/visualization/interactive/ui_config_loader.py
            # 项目根目录: .../Trade_Strategy
            project_root = current_file.parent.parent.parent.parent
            config_path = project_root / "configs" / "visualization" / "ui_config.yaml"
            # 设置项目根目录
            self._project_root = project_root
        else:
            config_path = Path(config_path)
            # 项目根目录：从配置文件位置向上查找
            # config_path: .../Trade_Strategy/configs/visualization/ui_config.yaml
            # project_root: .../Trade_Strategy
            self._project_root = config_path.parent.parent

        if not config_path.exists():
            raise FileNotFoundError(f"配置文件不存在: {config_path}")

        with open(config_path, "r", encoding="utf-8") as f:
            self._config = yaml.safe_load(f)

    def get_project_root(self) -> Path:
        """
        获取项目根目录

        Returns:
            项目根目录的绝对路径
        """
        return self._project_root

    def get_scan_results_dir(self, absolute: bool = True) -> str:
        """
        获取默认的扫描结果目录路径

        Args:
            absolute: 是否返回绝对路径（默认True）

        Returns:
            扫描结果目录的路径（绝对或相对）
        """
        relative_dir = self._config.get("scan_results", {}).get(
            "default_dir", "outputs/analysis"
        )
        if absolute:
            return str(self._project_root / relative_dir)
        return relative_dir

    def get_recent_scan_file(self) -> Optional[str]:
        """
        获取最近使用的扫描结果文件路径

        Returns:
            最近使用的文件路径，如果没有则返回 None
        """
        recent = self._config.get("scan_results", {}).get("recent_file", "")
        return recent if recent else None

    def set_recent_scan_file(self, file_path: str):
        """
        设置最近使用的扫描结果文件路径

        Args:
            file_path: 文件路径
        """
        if "scan_results" not in self._config:
            self._config["scan_results"] = {}
        self._config["scan_results"]["recent_file"] = file_path

    def get_stock_data_dir(self, absolute: bool = True) -> str:
        """
        获取默认的股票数据目录路径（即 search_paths 的第一个路径）

        Args:
            absolute: 是否返回绝对路径（默认True）

        Returns:
            股票数据目录的路径（绝对或相对）
        """
        # 从 search_paths 获取第一个路径作为默认路径
        search_paths = self._config.get("stock_data", {}).get(
            "search_paths", ["datasets/test_pkls", "datasets/pkls"]
        )
        relative_dir = search_paths[0] if search_paths else "datasets/test_pkls"

        if absolute:
            # 修改：使用 CWD 解析数据路径，以便复用主分支数据
            return str(Path(relative_dir).resolve())
        return relative_dir

    def get_stock_data_search_paths(self, absolute: bool = True) -> List[str]:
        """
        获取股票数据搜索路径列表（按优先级排序）

        Args:
            absolute: 是否返回绝对路径（默认True）

        Returns:
            股票数据搜索路径列表（绝对或相对）
        """
        relative_paths = self._config.get("stock_data", {}).get(
            "search_paths", ["datasets/test_pkls", "datasets/pkls"]
        )
        if absolute:
            # 修改：使用 CWD 解析数据路径，以便复用主分支数据
            return [str(Path(path).resolve()) for path in relative_paths]
        return relative_paths

    def get_window_size(self) -> tuple[int, int]:
        """
        获取默认窗口大小

        Returns:
            (宽度, 高度) 元组
        """
        ui_config = self._config.get("ui", {})
        width = ui_config.get("window_width", 1600)
        height = ui_config.get("window_height", 900)
        return (width, height)

    def get_panel_weights(self) -> tuple[float, float]:
        """
        获取面板宽度比例

        Returns:
            (左侧面板权重, 右侧面板权重) 元组
        """
        ui_config = self._config.get("ui", {})
        left = ui_config.get("left_panel_weight", 0.3)
        right = ui_config.get("right_panel_weight", 0.7)
        return (left, right)

    def get_colors(self) -> Dict[str, str]:
        """
        获取颜色配置

        Returns:
            颜色配置字典
        """
        return self._config.get("ui", {}).get("colors", {})

    def get_all_config(self) -> Dict[str, Any]:
        """
        获取完整配置

        Returns:
            完整配置字典
        """
        return self._config.copy()

    def save_config(self, config_path: Optional[str] = None):
        """
        保存配置到文件（例如保存最近使用的文件路径）

        Args:
            config_path: 配置文件路径（可选，默认使用原路径）
        """
        if config_path is None:
            config_path = (
                self._project_root / "configs" / "visualization" / "ui_config.yaml"
            )
        else:
            config_path = Path(config_path)

        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(self._config, f, allow_unicode=True, default_flow_style=False)

    def get_date_range(self) -> tuple[Optional[str], Optional[str]]:
        """
        获取数据截取时段配置

        Returns:
            (start_date, end_date) 元组
        """
        scan_settings = self._config.get("scan_settings", {})
        start_date = scan_settings.get("start_date")
        end_date = scan_settings.get("end_date")
        return (start_date, end_date)

    def get_display_options_defaults(self) -> Dict[str, bool]:
        """
        获取显示选项默认值

        Returns:
            显示选项默认值字典
        """
        return self._config.get("ui", {}).get(
            "display_options", {"show_peak_score": True, "show_bt_score": True}
        )


def get_ui_config_loader(config_path: Optional[str] = None) -> UIConfigLoader:
    """
    获取全局UI配置加载器实例（单例模式）

    Args:
        config_path: 配置文件路径（可选）

    Returns:
        UIConfigLoader实例
    """
    return UIConfigLoader(config_path)
