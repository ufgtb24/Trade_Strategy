"""共享 dataclass、StatusBand enum、status band 派生逻辑。

被 inducer / librarian / observation_log / feature_store 共同依赖。
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class StatusBand(str, Enum):
    """P5 派生的 5 档语义带。继承 str 让 yaml.safe_dump 输出干净字符串。"""
    FORGOTTEN = "forgotten"
    CANDIDATE = "candidate"
    SUPPORTED = "supported"
    CONSOLIDATED = "consolidated"
    STRONG = "strong"


# 状态带阈值（左闭右开），与主 spec §3.4 一致
_STATUS_BAND_THRESHOLDS: list[tuple[float, float, StatusBand]] = [
    (0.00, 0.05, StatusBand.FORGOTTEN),
    (0.05, 0.20, StatusBand.CANDIDATE),
    (0.20, 0.40, StatusBand.SUPPORTED),
    (0.40, 0.60, StatusBand.CONSOLIDATED),
    (0.60, 1.01, StatusBand.STRONG),  # 上界 1.01 涵盖 signal=1.0
]


def derive_status_band(signal: float, provenance: str) -> StatusBand:
    """从 P5 信号 + provenance 派生状态带。

    Phase 4+ 约束：若 provenance startswith 'shuffle-'，强制锁 candidate
    （防止 Reshuffle 在固定样本集上虚假升级）。
    """
    if provenance.startswith("shuffle-"):
        return StatusBand.CANDIDATE
    for lo, hi, band in _STATUS_BAND_THRESHOLDS:
        if lo <= signal < hi:
            return band
    return StatusBand.STRONG  # safety net


@dataclass
class Candidate:
    """Inducer 单条产出 — 一条候选规律。"""
    text: str
    supporting_sample_ids: list[str]
    K: int
    N: int
    raw_response_excerpt: str = ""


@dataclass
class Event:
    """单条 (sample, feature) 评估事件 — 喂给 Librarian.update 的输入。"""
    sample_id: str
    K: int
    N: int
    source: str
    C: int = 0
    epoch_tag: Optional[str] = None
    notes: str = ""


@dataclass
class ObservationLogEntry:
    """ObservationLog 单条审计条目（按 (sample, feature) 粒度）。"""
    id: str
    ts: datetime
    source: str
    sample_id: str
    K: int
    N: int
    alpha_after: float
    beta_after: float
    signal_after: float
    C: int = 0
    epoch_tag: Optional[str] = None
    superseded_by: Optional[str] = None
    notes: str = ""


@dataclass
class Feature:
    """Feature 完整状态（与 features/<id>.yaml 一一对应）。"""
    id: str
    text: str
    embedding: list[float]
    alpha: float
    beta: float
    last_update_ts: datetime
    provenance: str
    observed_samples: list[str]
    total_K: int
    total_N: int
    total_C_weighted: float
    observations: list[ObservationLogEntry] = field(default_factory=list)
    research_status: str = "active"
    factor_overlap_declared: Optional[str] = None


# ---- yaml.safe_dump 兼容 ----
import yaml as _yaml


def _status_band_representer(dumper: _yaml.SafeDumper, data: StatusBand):
    """让 yaml.safe_dump 把 StatusBand 实例序列化为其 .value 字符串。"""
    return dumper.represent_str(data.value)


_yaml.SafeDumper.add_representer(StatusBand, _status_band_representer)
