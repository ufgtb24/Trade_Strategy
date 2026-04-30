"""ObservationLog 操作 — append + 过滤 active + 生成 entry id。

按 (sample_id, feature_id) 粒度，每条事件一个 ObservationLogEntry。
本期 superseded_by 始终 null（Phase 1.5 才启用），但过滤逻辑已就位。
"""

import uuid

from BreakoutStrategy.feature_library.feature_models import ObservationLogEntry
from BreakoutStrategy.feature_library.feature_store import FeatureStore


def new_entry_id() -> str:
    """生成形如 'obs-a1b2c3d4' 的唯一 entry id。"""
    return f"obs-{uuid.uuid4().hex[:8]}"


def append_entry(
    store: FeatureStore, feature_id: str, entry: ObservationLogEntry,
) -> None:
    """加载 feature → append entry 到 observations → 保存。"""
    feature = store.load(feature_id)
    feature.observations.append(entry)
    store.save(feature)


def get_active_entries(
    store: FeatureStore, feature_id: str,
) -> list[ObservationLogEntry]:
    """返回 superseded_by is None 的 entries（Phase 1 全部 active）。"""
    feature = store.load(feature_id)
    return [o for o in feature.observations if o.superseded_by is None]
