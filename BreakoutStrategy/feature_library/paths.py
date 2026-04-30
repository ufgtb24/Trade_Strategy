"""特征库文件系统路径常量。

统一管理 feature_library/ 根目录及其子结构的路径解析，
避免散落的字符串拼接。所有路径均返回绝对 Path。
"""

from pathlib import Path

# 项目根目录（repo root），由本文件所在位置反推
_REPO_ROOT = Path(__file__).resolve().parents[2]

FEATURE_LIBRARY_ROOT: Path = _REPO_ROOT / "feature_library"
SAMPLES_DIR: Path = FEATURE_LIBRARY_ROOT / "samples"
FEATURES_DIR: Path = FEATURE_LIBRARY_ROOT / "features"


def ensure_features_dir() -> Path:
    """创建并返回 features/ 目录。"""
    FEATURES_DIR.mkdir(parents=True, exist_ok=True)
    return FEATURES_DIR


def sample_dir(sample_id: str) -> Path:
    """返回某 sample 的目录路径。"""
    return SAMPLES_DIR / sample_id


def chart_png_path(sample_id: str) -> Path:
    return sample_dir(sample_id) / "chart.png"


def meta_yaml_path(sample_id: str) -> Path:
    return sample_dir(sample_id) / "meta.yaml"


def nl_description_path(sample_id: str) -> Path:
    return sample_dir(sample_id) / "nl_description.md"


def ensure_sample_dir(sample_id: str) -> Path:
    """创建并返回 sample 目录（如已存在则保留）。"""
    target = sample_dir(sample_id)
    target.mkdir(parents=True, exist_ok=True)
    return target
