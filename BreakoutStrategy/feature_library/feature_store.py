"""features/<id>.yaml 持久化层。

- save / load 用 yaml.safe_dump/safe_load
- ObservationLog 嵌入 features yaml（按主 spec §4.2 schema）
- 文件名约定：F-NNN-<slug>.yaml（slug 取英文 + 数字 + 连字符前 30 字符；中文丢弃 → 退化为 F-NNN.yaml）
"""

import re
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
import yaml

from BreakoutStrategy.feature_library import paths
from BreakoutStrategy.feature_library.feature_models import (
    Feature, ObservationLogEntry,
)

# \d+ 贪婪捕获所有数字；[.-] 强制后面是 '.'（无 slug）或 '-'（slug 起点），
# 防止 F-1000.yaml 被 \d{3} 误截为 100。
# next_id 用 :03d 格式化，max_n ≥ 999 时自然扩展为 4 位（1000, 1001, ...）。
_ID_PATTERN = re.compile(r"^F-(\d+)[.-]")


def slugify(text: str) -> str:
    """text → kebab-case slug，仅保留 [a-z0-9-]，中文丢弃，截断 30 字符。"""
    lower = text.lower()
    # 仅保留 ASCII 字母、数字、空格、连字符、下划线
    cleaned = re.sub(r"[^a-z0-9\s\-_]", "", lower)
    # 空格 / 下划线 → 连字符；多连字符压缩
    kebab = re.sub(r"[\s_]+", "-", cleaned)
    kebab = re.sub(r"-+", "-", kebab).strip("-")
    return kebab[:30]


def _filename_for(feature_id: str, text: str) -> str:
    slug = slugify(text)
    if slug:
        return f"{feature_id}-{slug}.yaml"
    return f"{feature_id}.yaml"


class FeatureStore:
    """features/<id>.yaml CRUD。"""

    def save(self, feature: Feature) -> Path:
        """保存 feature 到 features/<id>-<slug>.yaml。"""
        paths.ensure_features_dir()
        # 删除可能存在的旧文件（text 改变会导致 slug 变 → 文件名变）
        for stale in paths.FEATURES_DIR.glob(f"{feature.id}-*.yaml"):
            stale.unlink()
        for stale in paths.FEATURES_DIR.glob(f"{feature.id}.yaml"):
            stale.unlink()

        out_path = paths.FEATURES_DIR / _filename_for(feature.id, feature.text)
        out_path.write_text(
            yaml.safe_dump(_feature_to_dict(feature), sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        return out_path

    def load(self, feature_id: str) -> Feature:
        """根据 id 加载 feature。"""
        for fp in paths.FEATURES_DIR.glob(f"{feature_id}-*.yaml"):
            return _feature_from_dict(yaml.safe_load(fp.read_text(encoding="utf-8")))
        for fp in paths.FEATURES_DIR.glob(f"{feature_id}.yaml"):
            return _feature_from_dict(yaml.safe_load(fp.read_text(encoding="utf-8")))
        raise FileNotFoundError(f"feature {feature_id} not found in {paths.FEATURES_DIR}")

    def exists(self, feature_id: str) -> bool:
        if not paths.FEATURES_DIR.exists():
            return False
        return (
            any(paths.FEATURES_DIR.glob(f"{feature_id}-*.yaml"))
            or any(paths.FEATURES_DIR.glob(f"{feature_id}.yaml"))
        )

    def list_all(self) -> list[Feature]:
        if not paths.FEATURES_DIR.exists():
            return []
        features: list[Feature] = []
        for fp in sorted(paths.FEATURES_DIR.glob("F-*.yaml")):
            features.append(_feature_from_dict(yaml.safe_load(fp.read_text(encoding="utf-8"))))
        return features

    def next_id(self) -> str:
        """返回下一个未占用的 F-NNN id（自增）。"""
        if not paths.FEATURES_DIR.exists():
            return "F-001"
        max_n = 0
        for fp in paths.FEATURES_DIR.glob("F-*.yaml"):
            m = _ID_PATTERN.match(fp.name)
            if m:
                max_n = max(max_n, int(m.group(1)))
        return f"F-{max_n + 1:03d}"


def _feature_to_dict(f: Feature) -> dict:
    """Feature → dict for yaml.safe_dump。datetime → ISO 字符串。"""
    d = asdict(f)
    d["last_update_ts"] = f.last_update_ts.isoformat(timespec="seconds")
    d["observations"] = [
        {
            **asdict(o),
            "ts": o.ts.isoformat(timespec="seconds"),
        }
        for o in f.observations
    ]
    return d


def _feature_from_dict(d: dict) -> Feature:
    """yaml.safe_load 出的 dict → Feature。"""
    obs_entries = [
        ObservationLogEntry(
            id=o["id"],
            ts=_parse_ts(o["ts"]),
            source=o["source"],
            sample_id=o["sample_id"],
            K=o["K"],
            N=o["N"],
            alpha_after=o["alpha_after"],
            beta_after=o["beta_after"],
            signal_after=o["signal_after"],
            C=o.get("C", 0),
            epoch_tag=o.get("epoch_tag"),
            superseded_by=o.get("superseded_by"),
            notes=o.get("notes", ""),
        )
        for o in d.get("observations", [])
    ]
    return Feature(
        id=d["id"],
        text=d["text"],
        embedding=d["embedding"],
        alpha=d["alpha"],
        beta=d["beta"],
        last_update_ts=_parse_ts(d["last_update_ts"]),
        provenance=d["provenance"],
        observed_samples=d["observed_samples"],
        total_K=d["total_K"],
        total_N=d["total_N"],
        total_C_weighted=d["total_C_weighted"],
        observations=obs_entries,
        research_status=d.get("research_status", "active"),
        factor_overlap_declared=d.get("factor_overlap_declared"),
    )


def _parse_ts(s) -> datetime:
    if isinstance(s, datetime):
        return s
    return datetime.fromisoformat(s)
