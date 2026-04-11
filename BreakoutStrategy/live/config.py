"""实盘 UI 配置加载器。"""

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class LiveConfig:
    trial_dir: Path
    data_dir: Path
    scan_window_days: int
    min_price: float
    max_price: float
    min_volume: int
    num_workers: int
    cache_path: Path
    market_timezone: str

    @classmethod
    def load(cls, config_path: Path | None = None) -> "LiveConfig":
        """从 YAML 加载配置。默认使用 BreakoutStrategy/live/config.yaml。

        相对路径会转换为相对于项目根目录的绝对路径。
        """
        project_root = Path(__file__).resolve().parent.parent.parent
        if config_path is None:
            config_path = project_root / "BreakoutStrategy" / "live" / "config.yaml"

        with open(config_path, encoding="utf-8") as f:
            raw = yaml.safe_load(f)

        def _abs(p: str) -> Path:
            path = Path(p)
            return path if path.is_absolute() else project_root / path

        config = cls(
            trial_dir=_abs(raw["trial_dir"]),
            data_dir=_abs(raw["data_dir"]),
            scan_window_days=int(raw["scan_window_days"]),
            min_price=float(raw["min_price"]),
            max_price=float(raw["max_price"]),
            min_volume=int(raw["min_volume"]),
            num_workers=int(raw["num_workers"]),
            cache_path=_abs(raw["cache_path"]),
            market_timezone=str(raw["market_timezone"]),
        )
        # 确保 cache 目录存在
        config.cache_path.parent.mkdir(parents=True, exist_ok=True)
        # 确保 data 目录存在（首次启动时创建，避免 download_stock 的
        # to_pickle 因父目录缺失而失败；多次启动幂等）
        config.data_dir.mkdir(parents=True, exist_ok=True)
        return config
