# Feature Mining Phase 1 — Librarian + Inducer MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Inducer batch + Librarian Beta-Binomial accumulator MVP. Given N samples (Phase 0 三件套), produce a `feature_library/features/` directory with candidate features and ObservationLog accumulated via single-call multi-image GLM-4V-Flash induction.

**Architecture:** 7 new Python modules in `BreakoutStrategy/feature_library/` + 1 method extension on `glm4v_backend.py` + entry script `scripts/feature_mining_phase1.py`. Pure dependency graph (no cycles): `feature_models` → `embedding_l0` / `feature_store` / `observation_log` / `inducer_prompts` → `glm4v_backend` (extended) / `inducer` → `librarian` → entry script.

**Tech Stack:** Python 3.12, zhipuai SDK (glm-4v-flash, ≤5 images per call), fastembed (bge-small-en-v1.5, 384-dim), pyyaml, pandas, scipy.stats.beta. Tests use pytest + unittest.mock; real GLM API only in entry script smoke test.

**Spec reference:** `docs/superpowers/specs/2026-04-27-phase1-librarian-inducer-mvp.md`.

---

## File Structure

### New files

| Path | Responsibility | LOC |
|---|---|---|
| `BreakoutStrategy/feature_library/feature_models.py` | `Candidate` / `Feature` / `ObservationLogEntry` / `Event` / `StatusBand` enum + `derive_status_band()` | ~120 |
| `BreakoutStrategy/feature_library/embedding_l0.py` | `embed_text(text)` + `cosine_similarity(a, b)` 薄封装 news_sentiment.embedding | ~40 |
| `BreakoutStrategy/feature_library/feature_store.py` | features/<id>.yaml CRUD: `save / load / list_all / next_id / exists` + slug generator | ~150 |
| `BreakoutStrategy/feature_library/observation_log.py` | `append_entry / get_active_entries / new_entry_id` (按 (sample, feature) 粒度) | ~80 |
| `BreakoutStrategy/feature_library/inducer_prompts.py` | `INDUCER_SYSTEM_PROMPT` + `build_batch_user_message(samples_meta)` | ~80 |
| `BreakoutStrategy/feature_library/inducer.py` | `batch_induce(sample_ids, backend) -> list[Candidate]` + YAML 解析 | ~120 |
| `BreakoutStrategy/feature_library/librarian.py` | `Librarian` class: `upsert_candidate / lookup_by_cosine / update / recompute` + Beta-Binomial 常量 | ~200 |
| Tests for each above (8 files) | - | ~700 总和 |
| `scripts/feature_mining_phase1.py` | entry script (params 在 main 顶部，无 argparse) | ~120 |

### Modified files

| Path | Modification |
|---|---|
| `BreakoutStrategy/feature_library/glm4v_backend.py` | 新增方法 `batch_describe(chart_paths, user_message) -> str`；保留现有 `describe_chart` |
| `.claude/docs/system_outline.md` | 在 Phase 0 行下追加 Phase 1 行（Task 10） |

### Reused unchanged

- `BreakoutStrategy/news_sentiment/embedding.py` — `embed_texts` / `cosine_similarity_matrix`
- `BreakoutStrategy/feature_library/paths.py` — features 路径需新加常量（Task 3 内一并加）
- `BreakoutStrategy/feature_library/sample_id.py` / `sample_meta.py` / `sample_renderer.py` / `preprocess.py`
- `BreakoutStrategy/analysis/breakout_detector.py`
- `configs/api_keys.yaml`

---

## Task 1: feature_models — 共享 dataclass + StatusBand

**Files:**
- Create: `BreakoutStrategy/feature_library/feature_models.py`
- Create: `BreakoutStrategy/feature_library/tests/test_feature_models.py`

- [ ] **Step 1.1: Write the failing test**

`BreakoutStrategy/feature_library/tests/test_feature_models.py`:

```python
"""Tests for shared dataclasses and status band derivation."""
from datetime import datetime

import pytest

from BreakoutStrategy.feature_library.feature_models import (
    Candidate, Event, Feature, ObservationLogEntry, StatusBand,
    derive_status_band,
)


def test_candidate_dataclass_basic():
    c = Candidate(
        text="盘整缩量后突破",
        supporting_sample_ids=["BO_AAPL_20210617", "BO_MSFT_20220301"],
        K=2, N=5,
    )
    assert c.K == 2
    assert c.N == 5
    assert c.raw_response_excerpt == ""  # default


def test_event_default_C_zero_and_epoch_null():
    e = Event(sample_id="BO_AAPL_20210617", K=1, N=1, source="ai_induction")
    assert e.C == 0
    assert e.epoch_tag is None


def test_observation_log_entry_phase1_fields():
    ent = ObservationLogEntry(
        id="obs-abc123",
        ts=datetime(2026, 4, 27, 14, 30),
        source="ai_induction",
        sample_id="BO_AAPL_20210617",
        K=1, N=1,
        alpha_after=1.5, beta_after=0.5, signal_after=0.07,
    )
    assert ent.epoch_tag is None         # Phase 1 未启用
    assert ent.superseded_by is None     # Phase 1 未启用
    assert ent.C == 0


def test_feature_dataclass_complete():
    f = Feature(
        id="F-001",
        text="盘整缩量后突破",
        embedding=[0.1, 0.2, 0.3],
        alpha=1.5, beta=0.5,
        last_update_ts=datetime(2026, 4, 27, 14, 30),
        provenance="ai_induction",
        observed_samples=["BO_AAPL_20210617"],
        total_K=1, total_N=1, total_C_weighted=0,
        observations=[],
    )
    assert f.research_status == "active"
    assert f.factor_overlap_declared is None


@pytest.mark.parametrize("signal,expected", [
    (0.01, StatusBand.FORGOTTEN),
    (0.04, StatusBand.FORGOTTEN),
    (0.05, StatusBand.CANDIDATE),
    (0.19, StatusBand.CANDIDATE),
    (0.20, StatusBand.SUPPORTED),
    (0.39, StatusBand.SUPPORTED),
    (0.40, StatusBand.CONSOLIDATED),
    (0.59, StatusBand.CONSOLIDATED),
    (0.60, StatusBand.STRONG),
    (0.99, StatusBand.STRONG),
])
def test_derive_status_band_thresholds(signal, expected):
    assert derive_status_band(signal, provenance="ai_induction") == expected


def test_provenance_lock_for_shuffle_origin():
    """provenance startswith 'shuffle-' 时即使 signal 高也锁 candidate（Phase 4+ 防误升级）。"""
    assert derive_status_band(0.80, provenance="shuffle-r1-b0") == StatusBand.CANDIDATE
```

- [ ] **Step 1.2: Run test to verify it fails**

Run: `uv run pytest BreakoutStrategy/feature_library/tests/test_feature_models.py -v`
Expected: ImportError for `feature_models`.

- [ ] **Step 1.3: Implement feature_models.py**

`BreakoutStrategy/feature_library/feature_models.py`:

```python
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
```

- [ ] **Step 1.4: Run test to verify it passes**

Run: `uv run pytest BreakoutStrategy/feature_library/tests/test_feature_models.py -v`
Expected: 15 passed (4 dataclass + 10 parametrized status band + 1 provenance lock).

- [ ] **Step 1.5: Commit**

```bash
git add BreakoutStrategy/feature_library/feature_models.py \
        BreakoutStrategy/feature_library/tests/test_feature_models.py
git commit -m "feat(feature_library): add shared dataclasses + StatusBand

Phase 1 step 1: Candidate / Event / ObservationLogEntry / Feature
+ StatusBand enum + derive_status_band（含 Phase 4+ provenance 锁）。
被 inducer/librarian/observation_log/feature_store 共同依赖。"
```

---

## Task 2: embedding_l0 — fastembed 薄封装

**Files:**
- Create: `BreakoutStrategy/feature_library/embedding_l0.py`
- Create: `BreakoutStrategy/feature_library/tests/test_embedding_l0.py`

- [ ] **Step 2.1: Write the failing test**

`BreakoutStrategy/feature_library/tests/test_embedding_l0.py`:

```python
"""Tests for L0 embedding wrapper."""
import numpy as np
import pytest

from BreakoutStrategy.feature_library.embedding_l0 import (
    embed_text, cosine_similarity,
)


def test_embed_returns_1d_array():
    emb = embed_text("盘整缩量后突破")
    assert isinstance(emb, np.ndarray)
    assert emb.ndim == 1


def test_embed_dimension_is_384():
    """bge-small-en-v1.5 输出 384 维（与 news_sentiment/embedding.py 一致）。"""
    emb = embed_text("test text")
    assert emb.shape == (384,)


def test_cosine_self_similarity_is_one():
    emb = embed_text("盘整缩量后突破")
    assert cosine_similarity(emb, emb) == pytest.approx(1.0, abs=1e-5)


def test_cosine_similar_texts_above_zero():
    a = embed_text("盘整缩量后突破")
    b = embed_text("盘整阶段量能收缩然后突破")
    sim = cosine_similarity(a, b)
    assert 0 < sim <= 1.0  # 中文同语义应正相似


def test_cosine_returns_python_float():
    """避免 numpy.float32 序列化进 yaml 时出问题。"""
    a = embed_text("test")
    b = embed_text("test")
    sim = cosine_similarity(a, b)
    assert isinstance(sim, float)
```

- [ ] **Step 2.2: Run test to verify it fails**

Run: `uv run pytest BreakoutStrategy/feature_library/tests/test_embedding_l0.py -v`
Expected: ImportError for `embedding_l0`.

- [ ] **Step 2.3: Implement embedding_l0.py**

`BreakoutStrategy/feature_library/embedding_l0.py`:

```python
"""L0 embedding 层 — 薄封装 news_sentiment 的 fastembed 接口。

为 feature_library 提供干净的单文本嵌入 + 两向量 cosine API，
避免 librarian 等模块直接依赖 news_sentiment 的批量 / 矩阵 API。
模型：bge-small-en-v1.5（384 维），由 news_sentiment.embedding 加载并缓存。
"""

import numpy as np

from BreakoutStrategy.news_sentiment.embedding import (
    embed_texts as _embed_texts,
    cosine_similarity_matrix as _cosine_similarity_matrix,
)


def embed_text(text: str) -> np.ndarray:
    """单条文本嵌入为 1D np.ndarray（384 维）。"""
    embeddings = _embed_texts([text])
    return embeddings[0]


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """两个 1D embedding 的余弦相似度，返回 Python float（便于 YAML 序列化）。"""
    a_2d = a.reshape(1, -1)
    b_2d = b.reshape(1, -1)
    sim_matrix = _cosine_similarity_matrix(a_2d, b_2d)
    return float(sim_matrix[0, 0])
```

- [ ] **Step 2.4: Run test to verify it passes**

Run: `uv run pytest BreakoutStrategy/feature_library/tests/test_embedding_l0.py -v`
Expected: 5 passed.

- [ ] **Step 2.5: Commit**

```bash
git add BreakoutStrategy/feature_library/embedding_l0.py \
        BreakoutStrategy/feature_library/tests/test_embedding_l0.py
git commit -m "feat(feature_library): add L0 embedding wrapper (fastembed facade)

embed_text(text) 返回 384 维 1D ndarray；
cosine_similarity(a, b) 返回 Python float。
薄封装 news_sentiment.embedding 的批量 API。"
```

---

## Task 3: feature_store — features/<id>.yaml CRUD + features 路径常量

**Files:**
- Modify: `BreakoutStrategy/feature_library/paths.py` (加 FEATURES_DIR + 路径辅助)
- Create: `BreakoutStrategy/feature_library/feature_store.py`
- Create: `BreakoutStrategy/feature_library/tests/test_feature_store.py`

- [ ] **Step 3.1: Write the failing test**

`BreakoutStrategy/feature_library/tests/test_feature_store.py`:

```python
"""Tests for FeatureStore (features/<id>.yaml CRUD)."""
from datetime import datetime

import pytest

from BreakoutStrategy.feature_library.feature_models import (
    Feature, ObservationLogEntry,
)
from BreakoutStrategy.feature_library.feature_store import (
    FeatureStore, slugify,
)


@pytest.fixture
def isolated_store(tmp_path, monkeypatch):
    from BreakoutStrategy.feature_library import paths
    monkeypatch.setattr(paths, "FEATURE_LIBRARY_ROOT", tmp_path / "feature_library")
    monkeypatch.setattr(paths, "SAMPLES_DIR", paths.FEATURE_LIBRARY_ROOT / "samples")
    monkeypatch.setattr(paths, "FEATURES_DIR", paths.FEATURE_LIBRARY_ROOT / "features")
    return FeatureStore()


@pytest.fixture
def sample_feature() -> Feature:
    return Feature(
        id="F-001",
        text="盘整缩量后突破",
        embedding=[0.1, 0.2, 0.3],
        alpha=1.5,
        beta=0.5,
        last_update_ts=datetime(2026, 4, 27, 14, 30),
        provenance="ai_induction",
        observed_samples=["BO_AAPL_20210617"],
        total_K=1,
        total_N=1,
        total_C_weighted=0,
        observations=[
            ObservationLogEntry(
                id="obs-aaa",
                ts=datetime(2026, 4, 27, 14, 30),
                source="ai_induction",
                sample_id="BO_AAPL_20210617",
                K=1, N=1,
                alpha_after=1.5, beta_after=0.5, signal_after=0.07,
            )
        ],
    )


def test_save_and_load_roundtrip(isolated_store, sample_feature):
    isolated_store.save(sample_feature)
    loaded = isolated_store.load(sample_feature.id)
    assert loaded.id == sample_feature.id
    assert loaded.text == sample_feature.text
    assert loaded.alpha == sample_feature.alpha
    assert loaded.observations[0].sample_id == "BO_AAPL_20210617"
    assert loaded.observations[0].epoch_tag is None
    assert loaded.observations[0].superseded_by is None


def test_save_creates_yaml_with_correct_filename(isolated_store, sample_feature):
    from BreakoutStrategy.feature_library import paths
    isolated_store.save(sample_feature)
    expected_path = paths.FEATURES_DIR / "F-001-pan-zheng-suo-liang-hou-tu-po.yaml"
    # 中文 slug 退化为空 → 仅 F-001.yaml
    # 实际取英文 slug 化结果，可能两种命名都接受，断言放宽：以 F-001 开头 + .yaml 结尾
    found = list(paths.FEATURES_DIR.glob("F-001*.yaml"))
    assert len(found) == 1, f"expected 1 file matching F-001*.yaml, got {found}"


def test_exists(isolated_store, sample_feature):
    assert not isolated_store.exists("F-001")
    isolated_store.save(sample_feature)
    assert isolated_store.exists("F-001")


def test_next_id_starts_at_001(isolated_store):
    assert isolated_store.next_id() == "F-001"


def test_next_id_increments(isolated_store, sample_feature):
    isolated_store.save(sample_feature)
    assert isolated_store.next_id() == "F-002"


def test_list_all_returns_all_features(isolated_store, sample_feature):
    isolated_store.save(sample_feature)
    f2 = Feature(
        id="F-002", text="另一个",
        embedding=[0.4, 0.5, 0.6],
        alpha=2.0, beta=1.0,
        last_update_ts=datetime(2026, 4, 27, 14, 30),
        provenance="ai_induction",
        observed_samples=["BO_TEST_20240101"],
        total_K=2, total_N=3, total_C_weighted=0,
    )
    isolated_store.save(f2)
    all_features = isolated_store.list_all()
    assert {f.id for f in all_features} == {"F-001", "F-002"}


def test_slugify_chinese_returns_empty():
    assert slugify("盘整缩量后突破") == ""


def test_slugify_english_keeps_kebab():
    assert slugify("Tight Rectangle Basing") == "tight-rectangle-basing"


def test_slugify_truncated_to_30():
    long = "this is a very long text that should be truncated for filename safety"
    assert len(slugify(long)) <= 30


def test_slugify_strips_dangerous_chars():
    assert "/" not in slugify("a/b/c")
    assert "\\" not in slugify(r"a\b\c")
```

- [ ] **Step 3.2: Run test to verify it fails**

Run: `uv run pytest BreakoutStrategy/feature_library/tests/test_feature_store.py -v`
Expected: ImportError.

- [ ] **Step 3.3: Add FEATURES_DIR to paths.py**

Append to `BreakoutStrategy/feature_library/paths.py` (after `SAMPLES_DIR` line):

```python
FEATURES_DIR: Path = FEATURE_LIBRARY_ROOT / "features"


def ensure_features_dir() -> Path:
    """创建并返回 features/ 目录。"""
    FEATURES_DIR.mkdir(parents=True, exist_ok=True)
    return FEATURES_DIR
```

- [ ] **Step 3.4: Implement feature_store.py**

`BreakoutStrategy/feature_library/feature_store.py`:

```python
"""features/<id>.yaml 持久化层。

- save / load 用 yaml.safe_dump/safe_load
- ObservationLog 嵌入 features yaml（按主 spec §4.2 schema）
- 文件名约定：F-NNN-<slug>.yaml（slug 取英文 + 数字 + 连字符前 30 字符；中文丢弃 → 退化为 F-NNN.yaml）
"""

import re
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml

from BreakoutStrategy.feature_library import paths
from BreakoutStrategy.feature_library.feature_models import (
    Feature, ObservationLogEntry,
)

_ID_PATTERN = re.compile(r"^F-(\d{3})-?")


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
```

- [ ] **Step 3.5: Run test to verify it passes**

Run: `uv run pytest BreakoutStrategy/feature_library/tests/test_feature_store.py -v`
Expected: 10 passed.

- [ ] **Step 3.6: Commit**

```bash
git add BreakoutStrategy/feature_library/paths.py \
        BreakoutStrategy/feature_library/feature_store.py \
        BreakoutStrategy/feature_library/tests/test_feature_store.py
git commit -m "feat(feature_library): add FeatureStore (features yaml CRUD)

- paths.FEATURES_DIR + ensure_features_dir
- FeatureStore.save/load/exists/list_all/next_id
- 文件名 F-NNN-<slug>.yaml（中文 text 退化为 F-NNN.yaml）
- ObservationLog 内嵌 features yaml（spec §4.2 schema）"
```

---

## Task 4: observation_log — append + active filter + ID 生成

**Files:**
- Create: `BreakoutStrategy/feature_library/observation_log.py`
- Create: `BreakoutStrategy/feature_library/tests/test_observation_log.py`

- [ ] **Step 4.1: Write the failing test**

`BreakoutStrategy/feature_library/tests/test_observation_log.py`:

```python
"""Tests for observation_log."""
from datetime import datetime

import pytest

from BreakoutStrategy.feature_library.feature_models import (
    Feature, ObservationLogEntry,
)
from BreakoutStrategy.feature_library.feature_store import FeatureStore
from BreakoutStrategy.feature_library.observation_log import (
    append_entry, get_active_entries, new_entry_id,
)


@pytest.fixture
def isolated_store(tmp_path, monkeypatch):
    from BreakoutStrategy.feature_library import paths
    monkeypatch.setattr(paths, "FEATURE_LIBRARY_ROOT", tmp_path / "feature_library")
    monkeypatch.setattr(paths, "SAMPLES_DIR", paths.FEATURE_LIBRARY_ROOT / "samples")
    monkeypatch.setattr(paths, "FEATURES_DIR", paths.FEATURE_LIBRARY_ROOT / "features")
    return FeatureStore()


@pytest.fixture
def empty_feature(isolated_store) -> Feature:
    f = Feature(
        id="F-001", text="test",
        embedding=[0.1], alpha=0.5, beta=0.5,
        last_update_ts=datetime(2026, 4, 27),
        provenance="ai_induction",
        observed_samples=[], total_K=0, total_N=0, total_C_weighted=0,
    )
    isolated_store.save(f)
    return f


def test_new_entry_id_format():
    eid = new_entry_id()
    assert eid.startswith("obs-")
    assert len(eid) >= 8  # obs- + 至少 4 字符


def test_new_entry_id_unique():
    ids = {new_entry_id() for _ in range(100)}
    assert len(ids) == 100  # 全部唯一


def test_append_entry_persists(isolated_store, empty_feature):
    entry = ObservationLogEntry(
        id=new_entry_id(),
        ts=datetime(2026, 4, 27, 14, 30),
        source="ai_induction",
        sample_id="BO_AAPL_20210617",
        K=1, N=1,
        alpha_after=1.5, beta_after=0.5, signal_after=0.07,
    )
    append_entry(isolated_store, "F-001", entry)

    loaded = isolated_store.load("F-001")
    assert len(loaded.observations) == 1
    assert loaded.observations[0].sample_id == "BO_AAPL_20210617"
    assert loaded.observations[0].id == entry.id


def test_get_active_entries_excludes_superseded(isolated_store, empty_feature):
    e1 = ObservationLogEntry(
        id="obs-001",
        ts=datetime(2026, 4, 27),
        source="ai_induction",
        sample_id="BO_X", K=1, N=1,
        alpha_after=1.5, beta_after=0.5, signal_after=0.07,
        superseded_by="obs-002",  # 被 obs-002 覆盖
    )
    e2 = ObservationLogEntry(
        id="obs-002",
        ts=datetime(2026, 4, 27),
        source="ai_induction",
        sample_id="BO_X", K=0, N=1,
        alpha_after=0.5, beta_after=1.5, signal_after=0.01,
    )
    append_entry(isolated_store, "F-001", e1)
    append_entry(isolated_store, "F-001", e2)

    active = get_active_entries(isolated_store, "F-001")
    assert len(active) == 1
    assert active[0].id == "obs-002"


def test_get_active_entries_all_active_when_no_supersede(isolated_store, empty_feature):
    e1 = ObservationLogEntry(
        id="obs-a", ts=datetime(2026, 4, 27),
        source="ai_induction", sample_id="S1", K=1, N=1,
        alpha_after=1.5, beta_after=0.5, signal_after=0.07,
    )
    e2 = ObservationLogEntry(
        id="obs-b", ts=datetime(2026, 4, 27),
        source="ai_induction", sample_id="S2", K=0, N=1,
        alpha_after=1.5, beta_after=1.5, signal_after=0.05,
    )
    append_entry(isolated_store, "F-001", e1)
    append_entry(isolated_store, "F-001", e2)

    active = get_active_entries(isolated_store, "F-001")
    assert len(active) == 2
```

- [ ] **Step 4.2: Run test to verify it fails**

Run: `uv run pytest BreakoutStrategy/feature_library/tests/test_observation_log.py -v`
Expected: ImportError.

- [ ] **Step 4.3: Implement observation_log.py**

`BreakoutStrategy/feature_library/observation_log.py`:

```python
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
```

- [ ] **Step 4.4: Run test to verify it passes**

Run: `uv run pytest BreakoutStrategy/feature_library/tests/test_observation_log.py -v`
Expected: 5 passed.

- [ ] **Step 4.5: Commit**

```bash
git add BreakoutStrategy/feature_library/observation_log.py \
        BreakoutStrategy/feature_library/tests/test_observation_log.py
git commit -m "feat(feature_library): add observation_log helpers

- new_entry_id() 生成 obs-<8hex> 唯一 ID
- append_entry(store, feature_id, entry) 持久化新 obs
- get_active_entries(store, feature_id) 过滤 superseded_by 非 null
  （Phase 1 全部 active；Phase 1.5+ 启用 supersede 时此处生效）"
```

---

## Task 5: glm4v_backend.batch_describe — 多图单次调用扩展

**Files:**
- Modify: `BreakoutStrategy/feature_library/glm4v_backend.py`
- Modify: `BreakoutStrategy/feature_library/tests/test_glm4v_backend.py`

- [ ] **Step 5.1: Write the failing test**

Append to `BreakoutStrategy/feature_library/tests/test_glm4v_backend.py`:

```python
def test_batch_describe_sends_multiple_image_blocks(tmp_path):
    """batch_describe 应在一个 user content 中塞多个 image_url 块。"""
    from unittest.mock import MagicMock, patch
    from BreakoutStrategy.feature_library.glm4v_backend import GLM4VBackend

    # 准备 3 张假图
    chart_paths = []
    for i in range(3):
        p = tmp_path / f"chart_{i}.png"
        p.write_bytes(f"fake-png-{i}".encode())
        chart_paths.append(p)

    backend = GLM4VBackend(api_key="test-key")
    fake_response = MagicMock()
    fake_response.choices = [MagicMock(message=MagicMock(
        content="batch result", reasoning_content=None,
    ))]

    with patch.object(backend._client.chat.completions, "create",
                      return_value=fake_response) as mock_create:
        result = backend.batch_describe(
            chart_paths=chart_paths,
            user_message="请归纳这 3 张图的共性",
        )

    assert result == "batch result"
    user_content = mock_create.call_args.kwargs["messages"][1]["content"]
    image_blocks = [c for c in user_content if c["type"] == "image_url"]
    text_blocks = [c for c in user_content if c["type"] == "text"]
    assert len(image_blocks) == 3
    assert len(text_blocks) == 1
    # 顺序：所有 image 在前，text 在后（Inducer 看完图再读说明）
    image_indices = [i for i, c in enumerate(user_content) if c["type"] == "image_url"]
    text_indices = [i for i, c in enumerate(user_content) if c["type"] == "text"]
    assert max(image_indices) < min(text_indices)


def test_batch_describe_raises_on_too_many_images(tmp_path):
    """超过 5 张应在调用 API 前 raise ValueError。"""
    from BreakoutStrategy.feature_library.glm4v_backend import GLM4VBackend, GLM4V_MAX_IMAGES

    chart_paths = []
    for i in range(GLM4V_MAX_IMAGES + 1):
        p = tmp_path / f"chart_{i}.png"
        p.write_bytes(b"fake")
        chart_paths.append(p)

    backend = GLM4VBackend(api_key="test-key")
    with pytest.raises(ValueError, match="too many images"):
        backend.batch_describe(chart_paths=chart_paths, user_message="x")


def test_batch_describe_raises_on_zero_images():
    """空列表抛 ValueError。"""
    from BreakoutStrategy.feature_library.glm4v_backend import GLM4VBackend

    backend = GLM4VBackend(api_key="test-key")
    with pytest.raises(ValueError, match="at least 1 image"):
        backend.batch_describe(chart_paths=[], user_message="x")


def test_batch_describe_uses_system_prompt_from_param(tmp_path):
    """batch_describe 接受可选 system_prompt 参数（Inducer 注入自己的 prompt）。"""
    from unittest.mock import MagicMock, patch
    from BreakoutStrategy.feature_library.glm4v_backend import GLM4VBackend

    p = tmp_path / "c.png"
    p.write_bytes(b"fake")
    backend = GLM4VBackend(api_key="test-key")
    fake_resp = MagicMock()
    fake_resp.choices = [MagicMock(message=MagicMock(content="ok", reasoning_content=None))]
    with patch.object(backend._client.chat.completions, "create",
                      return_value=fake_resp) as mock_create:
        backend.batch_describe(
            chart_paths=[p], user_message="x",
            system_prompt="custom inducer prompt",
        )
    messages = mock_create.call_args.kwargs["messages"]
    assert messages[0]["content"] == "custom inducer prompt"


def test_batch_describe_default_uses_glm4v_system_prompt(tmp_path):
    """不传 system_prompt 时使用现有 GLM4V SYSTEM_PROMPT 作为兜底。"""
    from unittest.mock import MagicMock, patch
    from BreakoutStrategy.feature_library.glm4v_backend import GLM4VBackend
    from BreakoutStrategy.feature_library.prompts import SYSTEM_PROMPT

    p = tmp_path / "c.png"
    p.write_bytes(b"fake")
    backend = GLM4VBackend(api_key="test-key")
    fake_resp = MagicMock()
    fake_resp.choices = [MagicMock(message=MagicMock(content="ok", reasoning_content=None))]
    with patch.object(backend._client.chat.completions, "create",
                      return_value=fake_resp) as mock_create:
        backend.batch_describe(chart_paths=[p], user_message="x")
    messages = mock_create.call_args.kwargs["messages"]
    assert messages[0]["content"] == SYSTEM_PROMPT
```

- [ ] **Step 5.2: Run test to verify they fail**

Run: `uv run pytest BreakoutStrategy/feature_library/tests/test_glm4v_backend.py -v`
Expected: 5 new tests fail (AttributeError for `batch_describe` / `GLM4V_MAX_IMAGES`).

- [ ] **Step 5.3: Add batch_describe + GLM4V_MAX_IMAGES to glm4v_backend.py**

Modify `BreakoutStrategy/feature_library/glm4v_backend.py`:

After `MAX_RETRIES = 2`, add:

```python
GLM4V_MAX_IMAGES = 5  # GLM-4V-Flash 服务端硬限（实验确认 n=8 报错 1210）
```

Inside `class GLM4VBackend`, after `describe_chart` method, add:

```python
    def batch_describe(
        self,
        chart_paths: list[Path],
        user_message: str,
        *,
        system_prompt: str | None = None,
    ) -> str:
        """对多张 chart.png 单次调用 glm-4v-flash 生成共性描述。

        Args:
            chart_paths: chart.png 路径列表（≤ GLM4V_MAX_IMAGES 张）
            user_message: 上下文 prompt（可含每张图的 sample_id / 元数据）
            system_prompt: 可选 system 角色 prompt（None 用 prompts.SYSTEM_PROMPT）

        Returns:
            模型回复文本；失败返回空字符串

        Raises:
            ValueError: chart_paths 为空 / 超过 GLM4V_MAX_IMAGES
        """
        if not chart_paths:
            raise ValueError("batch_describe needs at least 1 image")
        if len(chart_paths) > GLM4V_MAX_IMAGES:
            raise ValueError(
                f"too many images: {len(chart_paths)} > {GLM4V_MAX_IMAGES} "
                f"(GLM-4V-Flash 服务端硬限)"
            )

        sys_msg = system_prompt if system_prompt is not None else SYSTEM_PROMPT

        # user content：所有 image_url 在前，text 在后（图先于说明）
        user_content: list[dict] = [
            {"type": "image_url", "image_url": {"url": _encode_image_as_data_url(p)}}
            for p in chart_paths
        ]
        user_content.append({"type": "text", "text": user_message})

        messages = [
            {"role": "system", "content": sys_msg},
            {"role": "user", "content": user_content},
        ]

        for attempt in range(MAX_RETRIES):
            try:
                response = self._client.chat.completions.create(
                    model=GLM4V_MODEL_ID,
                    messages=messages,
                    temperature=self._temperature,
                )
                return self._extract_content(response)
            except Exception as e:
                if attempt == 0:
                    logger.warning(f"[GLM4V batch] call failed: {e}, retrying...")
                    continue
                logger.error(f"[GLM4V batch] call failed after retry: {e}")

        return ""
```

- [ ] **Step 5.4: Run test to verify all glm4v_backend tests pass**

Run: `uv run pytest BreakoutStrategy/feature_library/tests/test_glm4v_backend.py -v`
Expected: 12 passed (原 7 + 新 5).

- [ ] **Step 5.5: Commit**

```bash
git add BreakoutStrategy/feature_library/glm4v_backend.py \
        BreakoutStrategy/feature_library/tests/test_glm4v_backend.py
git commit -m "feat(feature_library): extend GLM4VBackend with batch_describe

- batch_describe(chart_paths, user_message, system_prompt=None)
  单次调用塞 ≤5 张图（GLM4V_MAX_IMAGES 服务端硬限）
- 顺序：图在前 + 文本在后
- 可选 system_prompt 让 Inducer 注入自己的角色 prompt
- 复用 describe_chart 的 retry / 内容回收逻辑"
```

---

## Task 6: inducer_prompts — INDUCER_SYSTEM_PROMPT + build_batch_user_message

**Files:**
- Create: `BreakoutStrategy/feature_library/inducer_prompts.py`
- Create: `BreakoutStrategy/feature_library/tests/test_inducer_prompts.py`

- [ ] **Step 6.1: Write the failing test**

`BreakoutStrategy/feature_library/tests/test_inducer_prompts.py`:

```python
"""Tests for inducer_prompts."""
from BreakoutStrategy.feature_library.inducer_prompts import (
    INDUCER_SYSTEM_PROMPT, build_batch_user_message,
)


def test_system_prompt_requires_yaml_format():
    """SYSTEM_PROMPT 应明确要求 YAML 输出，不允许 markdown 代码块。"""
    assert "yaml" in INDUCER_SYSTEM_PROMPT.lower() or "YAML" in INDUCER_SYSTEM_PROMPT
    assert "candidates:" in INDUCER_SYSTEM_PROMPT


def test_system_prompt_requires_K_at_least_2():
    """SYSTEM_PROMPT 应要求 K ≥ 2 以排除单图噪声。"""
    assert "≥ 2" in INDUCER_SYSTEM_PROMPT or ">= 2" in INDUCER_SYSTEM_PROMPT or "至少 2" in INDUCER_SYSTEM_PROMPT


def test_system_prompt_requires_supporting_sample_ids():
    assert "supporting_sample_ids" in INDUCER_SYSTEM_PROMPT


def test_build_batch_user_message_contains_all_sample_ids():
    metas = [
        {
            "sample_id": "BO_AAPL_20210617",
            "ticker": "AAPL", "bo_date": "2021-06-17",
            "breakout_day": {"open": 130, "high": 135, "low": 129, "close": 134, "volume": 100_000_000},
            "consolidation": {
                "consolidation_length_bars": 30,
                "consolidation_height_pct": 5.2,
                "consolidation_position_vs_52w_high": -3.1,
                "consolidation_volume_ratio": 0.55,
                "consolidation_tightness_atr": 1.8,
            },
        },
        {
            "sample_id": "BO_MSFT_20220301",
            "ticker": "MSFT", "bo_date": "2022-03-01",
            "breakout_day": {"open": 290, "high": 300, "low": 289, "close": 298, "volume": 50_000_000},
            "consolidation": {
                "consolidation_length_bars": 25,
                "consolidation_height_pct": 4.0,
                "consolidation_position_vs_52w_high": -1.0,
                "consolidation_volume_ratio": 0.62,
                "consolidation_tightness_atr": 1.5,
            },
        },
    ]
    msg = build_batch_user_message(metas)
    assert "BO_AAPL_20210617" in msg
    assert "BO_MSFT_20220301" in msg
    assert "AAPL" in msg
    assert "MSFT" in msg
    assert "2021-06-17" in msg
    assert "2022-03-01" in msg


def test_build_batch_user_message_handles_null_consolidation_field():
    metas = [
        {
            "sample_id": "BO_TEST_20240101",
            "ticker": "TEST", "bo_date": "2024-01-01",
            "breakout_day": {"open": 10, "high": 11, "low": 10, "close": 11, "volume": 1_000_000},
            "consolidation": {
                "consolidation_length_bars": 5,
                "consolidation_height_pct": None,
                "consolidation_position_vs_52w_high": None,
                "consolidation_volume_ratio": 0.7,
                "consolidation_tightness_atr": None,
            },
        },
    ]
    msg = build_batch_user_message(metas)
    assert "N/A" in msg or "未知" in msg


def test_build_batch_user_message_numbers_each_sample():
    """user message 中每个 sample 应有 [1] [2] 这样的编号便于模型对应图序。"""
    metas = [
        {"sample_id": f"BO_S{i}_20240101", "ticker": "S", "bo_date": "2024-01-01",
         "breakout_day": {"open": 1, "high": 1, "low": 1, "close": 1, "volume": 1},
         "consolidation": {"consolidation_length_bars": 1, "consolidation_height_pct": 1.0,
                           "consolidation_position_vs_52w_high": 0.0,
                           "consolidation_volume_ratio": 1.0,
                           "consolidation_tightness_atr": 1.0}}
        for i in range(3)
    ]
    msg = build_batch_user_message(metas)
    assert "[1]" in msg
    assert "[2]" in msg
    assert "[3]" in msg
```

- [ ] **Step 6.2: Run test to verify it fails**

Run: `uv run pytest BreakoutStrategy/feature_library/tests/test_inducer_prompts.py -v`
Expected: ImportError.

- [ ] **Step 6.3: Implement inducer_prompts.py**

`BreakoutStrategy/feature_library/inducer_prompts.py`:

```python
"""Inducer batch 模式 prompt 模板。

INDUCER_SYSTEM_PROMPT 定义 Inducer 角色 + YAML 输出格式 + K≥2 等约束。
build_batch_user_message 把 N 个 sample 的 meta dict 拼成图序对应的 user 消息。
"""

from typing import Any


INDUCER_SYSTEM_PROMPT = (
    "你是 K 线形态归纳专家。我会给你一批同一个研究主题的 K 线图（每张图含突破日 / 盘整起点标注），"
    "还有每张图的关键数值上下文。你的任务是找出这批图共有的、有判别意义的形态规律。\n\n"
    "输出严格遵守以下 YAML 格式（不含 markdown 代码块、不含 ```yaml 围栏）：\n\n"
    "candidates:\n"
    "  - text: \"<规律的自然语言描述，30~100 字>\"\n"
    "    supporting_sample_ids: [<支持该规律的 sample_id 列表>]\n"
    "  - text: \"...\"\n"
    "    supporting_sample_ids: [...]\n\n"
    "约束：\n"
    "- 至少需要 2 张图同时呈现某规律才能列为 candidate（K ≥ 2）\n"
    "- 如果你认为没有跨图共性，输出 candidates: []\n"
    "- 不要输出 batch 总样本数 N，由调用方推断\n"
    "- 不要使用 markdown 代码块、列表标题、解释段落\n"
    "- 单条 candidate 的 text 应可独立理解（不要\"如上所述\"之类的引用）\n"
    "- supporting_sample_ids 的元素必须严格匹配 user 消息中给出的 sample_id\n"
)


def build_batch_user_message(samples_meta: list[dict[str, Any]]) -> str:
    """构造发送给 GLM-4V-Flash 的 user 文本（与 N 张 image_url 同消息）。

    每个 sample 用 [1] / [2] 编号对应图序，含 ticker / bo_date / breakout_day OHLCV /
    consolidation 5 字段。N/A 字段显式标出。
    """

    def fmt(v) -> str:
        return f"{v:.2f}" if isinstance(v, (int, float)) and not isinstance(v, bool) else "N/A"

    lines = [
        f"我给你 {len(samples_meta)} 张 K 线图，按顺序对应以下 sample_ids：\n"
    ]
    for i, meta in enumerate(samples_meta, start=1):
        bo = meta["breakout_day"]
        consol = meta["consolidation"]
        lines.append(
            f"\n[{i}] sample_id: {meta['sample_id']}\n"
            f"    ticker: {meta['ticker']}\n"
            f"    bo_date: {meta['bo_date']}\n"
            f"    breakout_day: open={fmt(bo['open'])} high={fmt(bo['high'])} "
            f"low={fmt(bo['low'])} close={fmt(bo['close'])} volume={fmt(bo['volume'])}\n"
            f"    consolidation: length={fmt(consol['consolidation_length_bars'])} bars, "
            f"height={fmt(consol['consolidation_height_pct'])}%, "
            f"vs_52w_high={fmt(consol['consolidation_position_vs_52w_high'])}%, "
            f"volume_ratio={fmt(consol['consolidation_volume_ratio'])}, "
            f"tightness_atr={fmt(consol['consolidation_tightness_atr'])}"
        )
    lines.append("\n\n请按 SYSTEM_PROMPT 要求归纳这批样本的共性规律。")
    return "".join(lines)
```

- [ ] **Step 6.4: Run test to verify it passes**

Run: `uv run pytest BreakoutStrategy/feature_library/tests/test_inducer_prompts.py -v`
Expected: 6 passed.

- [ ] **Step 6.5: Commit**

```bash
git add BreakoutStrategy/feature_library/inducer_prompts.py \
        BreakoutStrategy/feature_library/tests/test_inducer_prompts.py
git commit -m "feat(feature_library): add INDUCER_SYSTEM_PROMPT + batch user message

- INDUCER_SYSTEM_PROMPT: 中文角色 + YAML 输出契约 + K≥2 约束
- build_batch_user_message: [N] 编号对应图序 + 5 个 consolidation 字段 + N/A 处理"
```

---

## Task 7: inducer.batch_induce — 多图调用 + YAML 解析

**Files:**
- Create: `BreakoutStrategy/feature_library/inducer.py`
- Create: `BreakoutStrategy/feature_library/tests/test_inducer.py`

- [ ] **Step 7.1: Write the failing test**

`BreakoutStrategy/feature_library/tests/test_inducer.py`:

```python
"""Tests for inducer.batch_induce."""
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
import yaml

from BreakoutStrategy.feature_library.feature_models import Candidate
from BreakoutStrategy.feature_library.inducer import batch_induce


@pytest.fixture
def isolated_paths(tmp_path, monkeypatch):
    from BreakoutStrategy.feature_library import paths
    monkeypatch.setattr(paths, "FEATURE_LIBRARY_ROOT", tmp_path / "feature_library")
    monkeypatch.setattr(paths, "SAMPLES_DIR", paths.FEATURE_LIBRARY_ROOT / "samples")
    monkeypatch.setattr(paths, "FEATURES_DIR", paths.FEATURE_LIBRARY_ROOT / "features")
    return paths


@pytest.fixture
def fake_samples(tmp_path, isolated_paths):
    """构造 3 个假 samples（chart.png + meta.yaml + nl_description.md）。"""
    sample_ids = []
    for i, ticker in enumerate(["AAPL", "MSFT", "GOOG"]):
        sid = f"BO_{ticker}_2024010{i+1}"
        sample_dir = isolated_paths.SAMPLES_DIR / sid
        sample_dir.mkdir(parents=True, exist_ok=True)
        (sample_dir / "chart.png").write_bytes(b"fake-png-bytes")
        meta = {
            "sample_id": sid,
            "ticker": ticker,
            "bo_date": f"2024-01-0{i+1}",
            "breakout_day": {"open": 100.0, "high": 102.0, "low": 99.0, "close": 101.0, "volume": 1_000_000},
            "consolidation": {
                "consolidation_length_bars": 30,
                "consolidation_height_pct": 5.0,
                "consolidation_position_vs_52w_high": -2.0,
                "consolidation_volume_ratio": 0.6,
                "consolidation_tightness_atr": 1.8,
            },
        }
        (sample_dir / "meta.yaml").write_text(yaml.safe_dump(meta), encoding="utf-8")
        (sample_dir / "nl_description.md").write_text("desc", encoding="utf-8")
        sample_ids.append(sid)
    return sample_ids


def test_batch_induce_parses_valid_yaml(fake_samples):
    fake_backend = MagicMock()
    fake_backend.batch_describe.return_value = (
        "candidates:\n"
        "  - text: 盘整缩量后突破\n"
        "    supporting_sample_ids: [BO_AAPL_20240101, BO_MSFT_20240102]\n"
        "  - text: 突破日大量\n"
        "    supporting_sample_ids: [BO_AAPL_20240101, BO_MSFT_20240102, BO_GOOG_20240103]\n"
    )
    candidates = batch_induce(sample_ids=fake_samples, backend=fake_backend)
    assert len(candidates) == 2
    assert candidates[0].text == "盘整缩量后突破"
    assert candidates[0].K == 2
    assert candidates[0].N == 3
    assert candidates[1].K == 3


def test_batch_induce_filters_K_lt_2(fake_samples):
    """SYSTEM_PROMPT 要求 K ≥ 2，单独支持的 candidate 应被过滤。"""
    fake_backend = MagicMock()
    fake_backend.batch_describe.return_value = (
        "candidates:\n"
        "  - text: 单图独有\n"
        "    supporting_sample_ids: [BO_AAPL_20240101]\n"
        "  - text: 双图共性\n"
        "    supporting_sample_ids: [BO_AAPL_20240101, BO_MSFT_20240102]\n"
    )
    candidates = batch_induce(sample_ids=fake_samples, backend=fake_backend)
    assert len(candidates) == 1
    assert candidates[0].text == "双图共性"


def test_batch_induce_filters_unknown_sample_ids(fake_samples):
    """LLM 幻觉出的 sample_id（不在 batch 内）应被过滤。"""
    fake_backend = MagicMock()
    fake_backend.batch_describe.return_value = (
        "candidates:\n"
        "  - text: 含幻觉 ID\n"
        "    supporting_sample_ids: [BO_AAPL_20240101, BO_FAKE_99999999]\n"
    )
    candidates = batch_induce(sample_ids=fake_samples, backend=fake_backend)
    # K=1 (filtered to AAPL only) → < 2 → 整条被过滤
    assert len(candidates) == 0


def test_batch_induce_empty_candidates_yaml(fake_samples):
    fake_backend = MagicMock()
    fake_backend.batch_describe.return_value = "candidates: []"
    candidates = batch_induce(sample_ids=fake_samples, backend=fake_backend)
    assert candidates == []


def test_batch_induce_invalid_yaml_returns_empty(fake_samples):
    fake_backend = MagicMock()
    fake_backend.batch_describe.return_value = "this is: not valid: : yaml: text"
    candidates = batch_induce(sample_ids=fake_samples, backend=fake_backend)
    assert candidates == []


def test_batch_induce_empty_backend_response(fake_samples):
    fake_backend = MagicMock()
    fake_backend.batch_describe.return_value = ""
    candidates = batch_induce(sample_ids=fake_samples, backend=fake_backend)
    assert candidates == []


def test_batch_induce_raises_on_too_many_samples():
    fake_backend = MagicMock()
    with pytest.raises(ValueError, match="exceeds max_batch_size"):
        batch_induce(
            sample_ids=[f"BO_S{i}_20240101" for i in range(6)],
            backend=fake_backend,
            max_batch_size=5,
        )


def test_batch_induce_raises_on_missing_sample_artifacts(isolated_paths):
    """sample 目录不存在时抛 FileNotFoundError。"""
    fake_backend = MagicMock()
    with pytest.raises(FileNotFoundError, match="BO_MISSING_20240101"):
        batch_induce(
            sample_ids=["BO_MISSING_20240101"],
            backend=fake_backend,
        )


def test_batch_induce_passes_charts_and_message_to_backend(fake_samples):
    """验证 backend.batch_describe 收到正确的 chart_paths + user_message。"""
    fake_backend = MagicMock()
    fake_backend.batch_describe.return_value = "candidates: []"
    batch_induce(sample_ids=fake_samples, backend=fake_backend)

    call_kwargs = fake_backend.batch_describe.call_args.kwargs
    assert len(call_kwargs["chart_paths"]) == 3
    assert "BO_AAPL_20240101" in call_kwargs["user_message"]
    assert call_kwargs["system_prompt"]  # 显式传 INDUCER_SYSTEM_PROMPT
```

- [ ] **Step 7.2: Run test to verify it fails**

Run: `uv run pytest BreakoutStrategy/feature_library/tests/test_inducer.py -v`
Expected: ImportError.

- [ ] **Step 7.3: Implement inducer.py**

`BreakoutStrategy/feature_library/inducer.py`:

```python
"""Inducer batch 模式：N 张样本一次 GLM-4V-Flash 调用 → 候选 features。

输入：sample_ids（每个对应 samples/<id>/ 三件套已存在）+ GLM4VBackend
输出：list[Candidate]

错误处理：
- backend 失败（返回空字符串）→ 返回 []
- LLM 输出非合法 YAML → log warning + 返回 []
- candidate.supporting_sample_ids 含 batch 外的 ID → 过滤
- 过滤后 K < 2 → 整条 candidate 丢弃
"""

import logging

import yaml

from BreakoutStrategy.feature_library import paths
from BreakoutStrategy.feature_library.feature_models import Candidate
from BreakoutStrategy.feature_library.glm4v_backend import (
    GLM4V_MAX_IMAGES, GLM4VBackend,
)
from BreakoutStrategy.feature_library.inducer_prompts import (
    INDUCER_SYSTEM_PROMPT, build_batch_user_message,
)

logger = logging.getLogger(__name__)

MIN_K = 2  # K < 2 的 candidate 被过滤（spec INDUCER_SYSTEM_PROMPT 约束）
RAW_RESPONSE_EXCERPT_LEN = 500


def batch_induce(
    sample_ids: list[str],
    backend: GLM4VBackend,
    *,
    max_batch_size: int = GLM4V_MAX_IMAGES,
) -> list[Candidate]:
    """对 N 个 sample 做 Inducer batch 归纳。

    Args:
        sample_ids: 样本 ID 列表（必须每个对应 samples/<id>/ 三件套已存在）
        backend: GLM4VBackend 实例
        max_batch_size: 单次 GLM 调用塞图上限（默认 GLM4V_MAX_IMAGES = 5）

    Returns:
        candidates 列表（可能为空）

    Raises:
        ValueError: sample_ids 数量超过 max_batch_size
        FileNotFoundError: 某 sample 的 chart.png / meta.yaml 缺失
    """
    if len(sample_ids) > max_batch_size:
        raise ValueError(
            f"sample_ids count {len(sample_ids)} exceeds max_batch_size {max_batch_size}"
        )

    # 加载每个 sample 的 chart_path + meta dict
    chart_paths = []
    metas = []
    for sid in sample_ids:
        chart = paths.chart_png_path(sid)
        meta_p = paths.meta_yaml_path(sid)
        if not chart.exists() or not meta_p.exists():
            raise FileNotFoundError(
                f"sample {sid} 三件套不完整：chart={chart.exists()}, meta={meta_p.exists()}"
            )
        chart_paths.append(chart)
        metas.append(yaml.safe_load(meta_p.read_text(encoding="utf-8")))

    user_message = build_batch_user_message(metas)
    raw = backend.batch_describe(
        chart_paths=chart_paths,
        user_message=user_message,
        system_prompt=INDUCER_SYSTEM_PROMPT,
    )

    if not raw:
        logger.warning("[Inducer] backend.batch_describe 返回空字符串")
        return []

    return _parse_candidates(raw, batch_sample_ids=sample_ids)


def _parse_candidates(raw: str, batch_sample_ids: list[str]) -> list[Candidate]:
    """从 LLM 原始 YAML 输出解析 + 过滤为 Candidate 列表。"""
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as e:
        logger.warning(f"[Inducer] YAML 解析失败: {e}; raw={raw[:200]}...")
        return []

    if not isinstance(data, dict) or "candidates" not in data:
        logger.warning(f"[Inducer] LLM 输出 schema 错（缺 candidates 键）: {raw[:200]}...")
        return []

    candidates_raw = data.get("candidates") or []
    if not isinstance(candidates_raw, list):
        logger.warning(f"[Inducer] candidates 不是 list: {type(candidates_raw)}")
        return []

    batch_ids_set = set(batch_sample_ids)
    N = len(batch_sample_ids)
    out: list[Candidate] = []
    excerpt = raw[:RAW_RESPONSE_EXCERPT_LEN]

    for c_raw in candidates_raw:
        if not isinstance(c_raw, dict):
            continue
        text = c_raw.get("text")
        sup_ids = c_raw.get("supporting_sample_ids", [])
        if not text or not isinstance(sup_ids, list):
            continue
        # 过滤幻觉 ID
        valid_sup = [s for s in sup_ids if s in batch_ids_set]
        K = len(valid_sup)
        if K < MIN_K:
            continue
        out.append(Candidate(
            text=str(text).strip(),
            supporting_sample_ids=valid_sup,
            K=K, N=N,
            raw_response_excerpt=excerpt,
        ))

    return out
```

- [ ] **Step 7.4: Run test to verify it passes**

Run: `uv run pytest BreakoutStrategy/feature_library/tests/test_inducer.py -v`
Expected: 9 passed.

- [ ] **Step 7.5: Commit**

```bash
git add BreakoutStrategy/feature_library/inducer.py \
        BreakoutStrategy/feature_library/tests/test_inducer.py
git commit -m "feat(feature_library): add inducer.batch_induce

- 加载 N 张 chart + meta（按 sample_id）
- 调 backend.batch_describe（INDUCER_SYSTEM_PROMPT + build_batch_user_message）
- 解析 YAML 输出 → Candidate 列表
- 过滤：YAML 错 / schema 错 / K<2 / 含 batch 外 sample_id"
```

---

## Task 8: librarian — Beta-Binomial 累积 + L0 merge + recompute

**Files:**
- Create: `BreakoutStrategy/feature_library/librarian.py`
- Create: `BreakoutStrategy/feature_library/tests/test_librarian.py`

- [ ] **Step 8.1: Write the failing test**

`BreakoutStrategy/feature_library/tests/test_librarian.py`:

```python
"""Tests for Librarian (Beta-Binomial 累积 + L0 merge)."""
from datetime import datetime
from unittest.mock import MagicMock

import numpy as np
import pytest

from BreakoutStrategy.feature_library.feature_models import (
    Candidate, Event, Feature, StatusBand,
)
from BreakoutStrategy.feature_library.feature_store import FeatureStore
from BreakoutStrategy.feature_library.librarian import (
    ALPHA_PRIOR, BETA_PRIOR, L0_MERGE_THRESHOLD, Librarian,
)


@pytest.fixture
def isolated_store(tmp_path, monkeypatch):
    from BreakoutStrategy.feature_library import paths
    monkeypatch.setattr(paths, "FEATURE_LIBRARY_ROOT", tmp_path / "feature_library")
    monkeypatch.setattr(paths, "SAMPLES_DIR", paths.FEATURE_LIBRARY_ROOT / "samples")
    monkeypatch.setattr(paths, "FEATURES_DIR", paths.FEATURE_LIBRARY_ROOT / "features")
    return FeatureStore()


@pytest.fixture
def fake_embedder():
    """每条不同 text 返回不同 embedding；相同 text 返回完全相同 embedding。"""
    embedder = MagicMock()
    cache = {}
    def _embed(text):
        if text not in cache:
            cache[text] = np.random.RandomState(hash(text) % 2**31).rand(384)
            cache[text] = cache[text] / np.linalg.norm(cache[text])  # 单位向量
        return cache[text]
    embedder.embed_text.side_effect = _embed
    embedder.cosine_similarity.side_effect = lambda a, b: float(np.dot(a, b))
    return embedder


@pytest.fixture
def lib(isolated_store, fake_embedder):
    return Librarian(store=isolated_store, embedder=fake_embedder)


def test_upsert_creates_new_feature_when_no_match(lib, isolated_store):
    cand = Candidate(
        text="盘整缩量后突破",
        supporting_sample_ids=["S1", "S2"],
        K=2, N=3,
    )
    feature = lib.upsert_candidate(
        candidate=cand,
        batch_sample_ids=["S1", "S2", "S3"],
        source="ai_induction",
    )
    assert feature.id == "F-001"
    assert feature.text == "盘整缩量后突破"
    assert feature.alpha == pytest.approx(ALPHA_PRIOR + 2)  # K=2
    assert feature.beta == pytest.approx(BETA_PRIOR + 1)    # N-K=1
    assert set(feature.observed_samples) == {"S1", "S2", "S3"}
    # 3 个 obs entry（每个 sample 一条）
    loaded = isolated_store.load("F-001")
    assert len(loaded.observations) == 3


def test_upsert_merges_when_cosine_above_threshold(lib, isolated_store):
    """两个完全一样的 text → cosine=1.0 → 合并。"""
    cand1 = Candidate(text="盘整缩量", supporting_sample_ids=["S1", "S2"], K=2, N=3)
    cand2 = Candidate(text="盘整缩量", supporting_sample_ids=["S4", "S5"], K=2, N=3)

    f1 = lib.upsert_candidate(cand1, batch_sample_ids=["S1", "S2", "S3"], source="ai_induction")
    f2 = lib.upsert_candidate(cand2, batch_sample_ids=["S4", "S5", "S6"], source="ai_induction")

    assert f1.id == f2.id == "F-001"  # 合并到同一 feature
    loaded = isolated_store.load("F-001")
    assert loaded.alpha == pytest.approx(ALPHA_PRIOR + 4)  # K=2+2
    assert loaded.beta == pytest.approx(BETA_PRIOR + 2)    # N-K=1+1
    assert set(loaded.observed_samples) == {"S1", "S2", "S3", "S4", "S5", "S6"}


def test_upsert_creates_new_when_cosine_below_threshold(lib, isolated_store):
    """两个完全不同的 text → cosine 低 → 各自新建。"""
    cand1 = Candidate(text="盘整缩量", supporting_sample_ids=["S1", "S2"], K=2, N=2)
    cand2 = Candidate(text="完全不相关的另一种规律", supporting_sample_ids=["S3", "S4"], K=2, N=2)

    f1 = lib.upsert_candidate(cand1, batch_sample_ids=["S1", "S2"], source="ai_induction")
    f2 = lib.upsert_candidate(cand2, batch_sample_ids=["S3", "S4"], source="ai_induction")

    assert f1.id == "F-001"
    assert f2.id == "F-002"
    assert isolated_store.load("F-001").text != isolated_store.load("F-002").text


def test_lookup_by_cosine_returns_above_threshold(lib, isolated_store, fake_embedder):
    cand = Candidate(text="规律 A", supporting_sample_ids=["S1", "S2"], K=2, N=2)
    lib.upsert_candidate(cand, batch_sample_ids=["S1", "S2"], source="ai_induction")

    target_emb = fake_embedder.embed_text("规律 A")
    matches = lib.lookup_by_cosine(target_emb, threshold=L0_MERGE_THRESHOLD)
    assert len(matches) == 1
    assert matches[0].id == "F-001"


def test_recompute_from_observations(lib, isolated_store):
    cand = Candidate(text="规律 A", supporting_sample_ids=["S1", "S2"], K=2, N=3)
    lib.upsert_candidate(cand, batch_sample_ids=["S1", "S2", "S3"], source="ai_induction")

    feature = lib.recompute("F-001")
    expected_alpha = ALPHA_PRIOR + 2
    expected_beta = BETA_PRIOR + 1
    assert feature.alpha == pytest.approx(expected_alpha)
    assert feature.beta == pytest.approx(expected_beta)


def test_signal_computed_via_p5(lib, isolated_store):
    """signal_after = beta.ppf(0.05, α, β)，应在 (0, 1) 之间。"""
    cand = Candidate(text="规律 A", supporting_sample_ids=["S1", "S2", "S3"], K=3, N=3)
    feature = lib.upsert_candidate(cand, batch_sample_ids=["S1", "S2", "S3"], source="ai_induction")
    loaded = isolated_store.load("F-001")
    last_obs = loaded.observations[-1]
    assert 0 < last_obs.signal_after < 1


def test_observation_entries_per_sample(lib, isolated_store):
    """每个 batch_sample 写一条 obs（按粒度 (sample, feature)）。"""
    cand = Candidate(text="规律 A", supporting_sample_ids=["S1"], K=1, N=3)
    # 注意：K=1 在真实流程会被 inducer 过滤，此处直接构造 cand 是允许的
    lib.upsert_candidate(cand, batch_sample_ids=["S1", "S2", "S3"], source="ai_induction")

    loaded = isolated_store.load("F-001")
    sample_ids_in_obs = [o.sample_id for o in loaded.observations]
    assert sorted(sample_ids_in_obs) == ["S1", "S2", "S3"]
    # 支持的 sample 是 K=1，未支持的是 K=0
    s1_obs = next(o for o in loaded.observations if o.sample_id == "S1")
    s2_obs = next(o for o in loaded.observations if o.sample_id == "S2")
    assert s1_obs.K == 1
    assert s2_obs.K == 0
    assert s1_obs.N == 1
    assert s2_obs.N == 1


def test_status_band_strong_when_high_signal(lib, isolated_store):
    """连续多次 K=N 应让 P5 升到 strong 区间。"""
    for i in range(20):
        cand = Candidate(
            text=f"规律 A",
            supporting_sample_ids=[f"S{i*3+1}", f"S{i*3+2}", f"S{i*3+3}"],
            K=3, N=3,
        )
        lib.upsert_candidate(
            cand,
            batch_sample_ids=[f"S{i*3+1}", f"S{i*3+2}", f"S{i*3+3}"],
            source="ai_induction",
        )

    loaded = isolated_store.load("F-001")
    # α ≈ 60.5, β ≈ 0.5 → P5 应 > 0.6
    from BreakoutStrategy.feature_library.feature_models import derive_status_band
    band = derive_status_band(loaded.observations[-1].signal_after, loaded.provenance)
    assert band == StatusBand.STRONG
```

- [ ] **Step 8.2: Run test to verify it fails**

Run: `uv run pytest BreakoutStrategy/feature_library/tests/test_librarian.py -v`
Expected: ImportError.

- [ ] **Step 8.3: Implement librarian.py**

`BreakoutStrategy/feature_library/librarian.py`:

```python
"""Librarian — Beta-Binomial 累积 + L0 merge + features 库管理。

核心 API：
- upsert_candidate(candidate, batch_sample_ids, source)
- lookup_by_cosine(embedding, threshold)
- update(feature_id, event)
- recompute(feature_id)

Phase 1 简化：
- 不实施 epoch_tag / superseded_by 实际逻辑（schema 占位）
- LAMBDA_DECAY = 1.0（无时间衰减）
- GAMMA = 1.0 + C 始终 0（无 counter 加权）
- 不防 ObservationLog 重复 entry（暂允许，Phase 1.5 加去重）
"""

from datetime import datetime
from typing import Optional

import numpy as np
import scipy.stats

from BreakoutStrategy.feature_library.embedding_l0 import embed_text, cosine_similarity
from BreakoutStrategy.feature_library.feature_models import (
    Candidate, Event, Feature, ObservationLogEntry,
)
from BreakoutStrategy.feature_library.feature_store import FeatureStore
from BreakoutStrategy.feature_library.observation_log import (
    append_entry, new_entry_id,
)

# Beta-Binomial 常量（主 spec §3 + Phase 1 简化）
ALPHA_PRIOR = 0.5
BETA_PRIOR = 0.5
LAMBDA_DECAY = 1.0    # Phase 1 无衰减
GAMMA = 1.0           # Phase 1 不参与（C 始终 0）

# L0 合并阈值（Phase 1 brainstorming 决策）
L0_MERGE_THRESHOLD = 0.85


class _EmbedderProtocol:
    """duck-typed 接口：embed_text(text) + cosine_similarity(a, b)"""


class Librarian:
    """Beta-Binomial 累积器 + L0 merge + features 库管理。"""

    def __init__(self, store: FeatureStore, embedder=None):
        self.store = store
        self.embedder = embedder if embedder is not None else _DefaultEmbedder()

    def upsert_candidate(
        self,
        candidate: Candidate,
        *,
        batch_sample_ids: list[str],
        source: str = "ai_induction",
    ) -> Feature:
        """处理 Inducer 一条 candidate：合并到老 feature 或新建。

        步骤：
        1. embed candidate.text → embedding
        2. lookup_by_cosine 找命中的老 feature（取 cosine 最高）
        3a. 命中 → 用老 feature.id；3b. 未命中 → create_new_feature
        4. 对 batch_sample_ids 中每个 sample 写一条 ObservationLogEntry
           （在 supporting_sample_ids 内 K=1，否则 K=0；N 始终 1）
        5. recompute(feature_id) → 重算 (α, β) + signal
        """
        embedding = self.embedder.embed_text(candidate.text)
        matches = self.lookup_by_cosine(embedding, threshold=L0_MERGE_THRESHOLD)

        if matches:
            target_id = matches[0].id  # cosine 最高的
        else:
            target_id = self._create_new_feature(
                text=candidate.text,
                embedding=embedding,
                provenance=source,
            )

        supporting_set = set(candidate.supporting_sample_ids)
        for sid in batch_sample_ids:
            in_support = sid in supporting_set
            event = Event(
                sample_id=sid,
                K=1 if in_support else 0,
                N=1,
                source=source,
            )
            self.update(target_id, event)

        return self.recompute(target_id)

    def lookup_by_cosine(
        self, embedding: np.ndarray, threshold: float = L0_MERGE_THRESHOLD,
    ) -> list[Feature]:
        """返回 cosine ≥ threshold 的 features，按 cosine 降序。"""
        all_features = self.store.list_all()
        scored: list[tuple[float, Feature]] = []
        for f in all_features:
            f_emb = np.array(f.embedding)
            sim = self.embedder.cosine_similarity(embedding, f_emb)
            if sim >= threshold:
                scored.append((sim, f))
        scored.sort(key=lambda x: (-x[0], x[1].id))  # cosine 降序，并列 id 升序
        return [f for _, f in scored]

    def update(self, feature_id: str, event: Event) -> None:
        """单条 ObservationLog 事件入库（不立即 recompute）。

        signal_after / alpha_after / beta_after 在此处用临时计算值占位，
        recompute() 会从全部 active obs 重算并覆盖最后一条 obs 的快照。
        """
        feature = self.store.load(feature_id)
        # 计算事件后的临时 (α, β)（不含此事件后的衰减，供 obs 快照）
        tmp_alpha = feature.alpha + event.K
        tmp_beta = feature.beta + (event.N - event.K - event.C) + GAMMA * event.C
        tmp_signal = _safe_p5(tmp_alpha, tmp_beta)

        entry = ObservationLogEntry(
            id=new_entry_id(),
            ts=datetime.now(),
            source=event.source,
            sample_id=event.sample_id,
            K=event.K,
            N=event.N,
            C=event.C,
            alpha_after=tmp_alpha,
            beta_after=tmp_beta,
            signal_after=tmp_signal,
            epoch_tag=event.epoch_tag,
            notes=event.notes,
        )
        # 也更新 feature 的 observed_samples + total_K/N 即时（recompute 会覆盖 alpha/beta）
        if event.sample_id not in feature.observed_samples:
            feature.observed_samples.append(event.sample_id)
        feature.total_K += event.K
        feature.total_N += event.N
        feature.total_C_weighted += GAMMA * event.C
        feature.alpha = tmp_alpha
        feature.beta = tmp_beta
        feature.last_update_ts = datetime.now()
        feature.observations.append(entry)
        self.store.save(feature)

    def recompute(self, feature_id: str) -> Feature:
        """从 ObservationLog 重放计算 (α, β)，更新 features yaml + 派生 signal。"""
        feature = self.store.load(feature_id)
        active = [o for o in feature.observations if o.superseded_by is None]

        alpha = ALPHA_PRIOR + sum(o.K for o in active)
        beta = (
            BETA_PRIOR
            + sum(o.N - o.K - o.C for o in active)
            + GAMMA * sum(o.C for o in active)
        )

        feature.alpha = alpha
        feature.beta = beta
        feature.last_update_ts = datetime.now()

        # 更新最后一条 obs 的快照（让人眼能看到当前 signal）
        if active:
            last_signal = _safe_p5(alpha, beta)
            active[-1].alpha_after = alpha
            active[-1].beta_after = beta
            active[-1].signal_after = last_signal

        self.store.save(feature)
        return feature

    def _create_new_feature(
        self, text: str, embedding: np.ndarray, provenance: str,
    ) -> str:
        new_id = self.store.next_id()
        feature = Feature(
            id=new_id,
            text=text,
            embedding=embedding.tolist(),
            alpha=ALPHA_PRIOR,
            beta=BETA_PRIOR,
            last_update_ts=datetime.now(),
            provenance=provenance,
            observed_samples=[],
            total_K=0,
            total_N=0,
            total_C_weighted=0.0,
            observations=[],
        )
        self.store.save(feature)
        return new_id


class _DefaultEmbedder:
    """默认 embedder = embedding_l0 模块函数（避免 Librarian 强依赖具体类）。"""

    def embed_text(self, text: str) -> np.ndarray:
        return embed_text(text)

    def cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        return cosine_similarity(a, b)


def _safe_p5(alpha: float, beta: float) -> float:
    """计算 P5 = beta.ppf(0.05, α, β)，加防御以避免 scipy 的边界 NaN。"""
    if alpha <= 0 or beta <= 0:
        return 0.0
    try:
        return float(scipy.stats.beta.ppf(0.05, alpha, beta))
    except (ValueError, FloatingPointError):
        return 0.0
```

- [ ] **Step 8.4: Run test to verify it passes**

Run: `uv run pytest BreakoutStrategy/feature_library/tests/test_librarian.py -v`
Expected: 8 passed.

- [ ] **Step 8.5: Commit**

```bash
git add BreakoutStrategy/feature_library/librarian.py \
        BreakoutStrategy/feature_library/tests/test_librarian.py
git commit -m "feat(feature_library): add Librarian (Beta-Binomial + L0 merge)

- upsert_candidate: L0 cosine 命中合并 / 未命中新建 +
  按 batch_sample_ids 写 ObservationLogEntry（每 sample 1 条）+
  recompute (α, β) + P5
- lookup_by_cosine: cosine ≥ 0.85 命中，按 cosine 降序
- recompute: 从 active obs 重放 (α, β)；signal = beta.ppf(0.05, α, β)
- 常量：ALPHA_PRIOR=BETA_PRIOR=0.5 / LAMBDA=GAMMA=1.0（Phase 1 简化）/
  L0_MERGE_THRESHOLD=0.85"
```

---

## Task 9: Phase 1 entry script — 端到端真实跑通

**Files:**
- Create: `scripts/feature_mining_phase1.py`

- [ ] **Step 9.1: Implement entry script**

`scripts/feature_mining_phase1.py`:

```python
"""Phase 1 vertical slice 入口脚本。

运行方式：
    uv run python scripts/feature_mining_phase1.py

参数全部在 main() 起始位置声明（CLAUDE.md 要求，不用 argparse）。
默认从 datasets/pkls/ 加载指定 ticker，调用 BreakoutDetector 找前 N 个 breakouts，
对每个跑 Phase 0 preprocess（如未跑过），然后用 Inducer 多图 batch 归纳，
Librarian 累积入 features 库。

依赖 GLM-4V-Flash 真实 API 调用（zhipuai key from configs/api_keys.yaml）。
"""

from datetime import datetime
from pathlib import Path

import pandas as pd
import yaml

from BreakoutStrategy.analysis.breakout_detector import BreakoutDetector
from BreakoutStrategy.feature_library import paths
from BreakoutStrategy.feature_library.feature_models import derive_status_band
from BreakoutStrategy.feature_library.feature_store import FeatureStore
from BreakoutStrategy.feature_library.glm4v_backend import (
    GLM4V_MAX_IMAGES, GLM4VBackend,
)
from BreakoutStrategy.feature_library.inducer import batch_induce
from BreakoutStrategy.feature_library.librarian import Librarian
from BreakoutStrategy.feature_library.preprocess import preprocess_sample
from BreakoutStrategy.feature_library.sample_id import generate_sample_id

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_zhipuai_key() -> str:
    cfg_path = REPO_ROOT / "configs" / "api_keys.yaml"
    keys = yaml.safe_load(cfg_path.read_text())
    api_key = keys.get("zhipuai", "")
    if not api_key:
        raise RuntimeError("configs/api_keys.yaml 中 zhipuai key 为空")
    return api_key


def _load_pkl(ticker: str) -> pd.DataFrame:
    pkl_path = REPO_ROOT / "datasets" / "pkls" / f"{ticker}.pkl"
    if not pkl_path.exists():
        raise FileNotFoundError(f"未找到 {pkl_path}")
    return pd.read_pickle(pkl_path)


def _ensure_samples(
    ticker: str, count: int, backend: GLM4VBackend,
) -> list[str]:
    """获取 N 个 sample_id；缺失的调 preprocess_sample 补齐。"""
    df = _load_pkl(ticker)
    print(f"[Phase 1] {ticker} 数据范围 {df.index[0].date()} ~ {df.index[-1].date()}, {len(df)} bars")

    detector = BreakoutDetector(symbol=ticker)
    breakouts = detector.batch_add_bars(df)
    print(f"[Phase 1] 检测到 {len(breakouts)} 个 breakouts，取前 {count} 个")

    if len(breakouts) < count:
        raise RuntimeError(
            f"breakouts 数 {len(breakouts)} < 请求 {count}，换 ticker 或减小 count"
        )

    targets = breakouts[:count]
    sample_ids: list[str] = []

    for i, bo in enumerate(targets, start=1):
        bo_index = bo.current_index
        # pk_index 取最近被突破的 peak（与 Phase 0 entry script 一致语义）
        # broken_peaks 包含突破事件同时跨越的所有 peaks；取 index 最大者作为
        # consolidation 起点（聚焦最直接的盘整窗口，避免长 base 稀释信号）
        pk_index = (
            max(p.index for p in bo.broken_peaks)
            if bo.broken_peaks else bo_index - 1
        )
        bo_date = df.index[bo_index]
        sid = generate_sample_id(ticker=ticker, bo_date=bo_date)

        if (
            paths.chart_png_path(sid).exists()
            and paths.meta_yaml_path(sid).exists()
            and paths.nl_description_path(sid).exists()
        ):
            print(f"[Phase 1] [{i}/{count}] sample {sid} 已存在，跳过 preprocess")
        else:
            print(f"[Phase 1] [{i}/{count}] preprocess sample {sid} ...")
            window_start = max(0, bo_index - 200)
            df_window = df.iloc[window_start: bo_index + 1]
            local_bo = bo_index - window_start
            local_pk = max(0, pk_index - window_start)
            preprocess_sample(
                ticker=ticker,
                bo_date=bo_date,
                df_window=df_window,
                bo_index=local_bo,
                pk_index=local_pk,
                picked_at=datetime.now(),
                backend=backend,
            )
        sample_ids.append(sid)

    return sample_ids


def _print_library_summary(store: FeatureStore, recently_affected: list) -> None:
    all_features = store.list_all()
    print(f"\n[Phase 1] features 库当前状态：{len(all_features)} features")
    for f in sorted(all_features, key=lambda x: x.id):
        signal = f.observations[-1].signal_after if f.observations else 0.0
        band = derive_status_band(signal, f.provenance)
        text_preview = f.text[:40] + ("..." if len(f.text) > 40 else "")
        print(
            f"  {f.id} [{band.value:13s}] α={f.alpha:.2f} β={f.beta:.2f} "
            f"P5={signal:.3f} obs={len(f.observations)} text=\"{text_preview}\""
        )

    if recently_affected:
        affected_ids = sorted({f.id for f in recently_affected})
        print(
            f"[Phase 1] 本轮新增 / 强化 features：{', '.join(affected_ids)}"
            f"（共 {len(affected_ids)} 条）"
        )
    print(f"[Phase 1] features 文件位置：{paths.FEATURES_DIR}")


def main() -> None:
    # ---------------- 参数声明区 ----------------
    ticker: str = "AAPL"                          # 目标股票
    sample_count: int = 5                         # 处理几个 breakout（≤ GLM4V_MAX_IMAGES）
    skip_preprocess: bool = False                 # True 时跳过 Phase 0 preprocess（假定 samples 已存在）
    inducer_max_batch: int = GLM4V_MAX_IMAGES     # GLM-4V-Flash 单次上限 5
    # -------------------------------------------

    if sample_count > inducer_max_batch:
        raise ValueError(
            f"sample_count={sample_count} > inducer_max_batch={inducer_max_batch}"
        )

    print(f"[Phase 1] 加载 zhipuai API key...")
    api_key = _load_zhipuai_key()
    backend = GLM4VBackend(api_key=api_key)

    print(f"[Phase 1] 准备 {sample_count} 个 samples...")
    if skip_preprocess:
        # 复用现有 samples（不重新 preprocess）
        sample_ids = sorted(
            d.name for d in paths.SAMPLES_DIR.iterdir()
            if d.is_dir() and d.name.startswith(f"BO_{ticker.upper()}_")
        )[:sample_count]
        if len(sample_ids) < sample_count:
            raise RuntimeError(
                f"现有 samples 数 {len(sample_ids)} < 请求 {sample_count}，"
                f"取消 skip_preprocess 重跑"
            )
        print(f"[Phase 1] 复用现有 samples: {sample_ids}")
    else:
        sample_ids = _ensure_samples(
            ticker=ticker, count=sample_count, backend=backend,
        )

    print(f"\n[Phase 1] Inducer batch 归纳 {len(sample_ids)} 张样本...")
    candidates = batch_induce(
        sample_ids=sample_ids[:inducer_max_batch],
        backend=backend,
    )
    print(f"[Phase 1] Inducer 产出 {len(candidates)} 个 candidate features")
    for i, c in enumerate(candidates, start=1):
        print(f"  [{i}] K={c.K}/N={c.N} text=\"{c.text[:60]}{'...' if len(c.text) > 60 else ''}\"")

    if not candidates:
        print("[Phase 1] 无 candidate，退出（features 库不变）")
        _print_library_summary(FeatureStore(), recently_affected=[])
        return

    print(f"\n[Phase 1] Librarian 累积 candidates 入库...")
    store = FeatureStore()
    librarian = Librarian(store=store)
    affected = []
    for c in candidates:
        feature = librarian.upsert_candidate(
            candidate=c,
            batch_sample_ids=sample_ids[:inducer_max_batch],
            source="ai_induction",
        )
        affected.append(feature)

    _print_library_summary(store, recently_affected=affected)


if __name__ == "__main__":
    main()
```

- [ ] **Step 9.2: Smoke test the entry script**

Run: `uv run python scripts/feature_mining_phase1.py`

Expected output sketch:
```
[Phase 1] 加载 zhipuai API key...
[Phase 1] 准备 5 个 samples...
[Phase 1] AAPL 数据范围 ... ~ ..., NNNN bars
[Phase 1] 检测到 N 个 breakouts，取前 5 个
[Phase 1] [1/5] sample BO_AAPL_xxxxxxxx 已存在，跳过 preprocess
...（或者 preprocess 调用）
[Phase 1] Inducer batch 归纳 5 张样本...
[Phase 1] Inducer 产出 N 个 candidate features
  [1] K=3/N=5 text="盘整缩量后突破..."
  ...
[Phase 1] Librarian 累积 candidates 入库...
[Phase 1] features 库当前状态：N features
  F-001 [supported    ] α=4.50 β=1.50 P5=0.32 obs=5 text="..."
  ...
[Phase 1] 本轮新增 / 强化 features：F-001（共 1 条）
[Phase 1] features 文件位置：/home/yu/PycharmProjects/Trade_Strategy/feature_library/features
```

通过判据：
- 进程正常退出（exit 0）
- features/F-*.yaml 至少 1 个
- 每个 yaml 含完整 schema 字段（含 epoch_tag/superseded_by/provenance 字段, 默认 null）
- ObservationLog 条目数 = candidates 数 × 5

如出错：
- 若 zhipuai key 无效 → 检查 configs/api_keys.yaml
- 若 fastembed 加载慢 → 第一次 ~30s 下载模型，后续秒级
- 若 BreakoutDetector 接口变了 → 看 Phase 0 entry script 的实际签名做调整

- [ ] **Step 9.3: Verify outputs**

```bash
ls -la /home/yu/PycharmProjects/Trade_Strategy/feature_library/features/
```

应看到至少 1 个 F-*.yaml 文件。

```bash
cat /home/yu/PycharmProjects/Trade_Strategy/feature_library/features/F-001*.yaml
```

应包含完整 schema：id / text / embedding / alpha / beta / last_update_ts / provenance /
observed_samples / total_K / total_N / total_C_weighted / observations / research_status /
factor_overlap_declared。每条 observation 应含 id / ts / source / epoch_tag (null) /
sample_id / K / N / C / alpha_after / beta_after / signal_after / superseded_by (null) / notes。

- [ ] **Step 9.4: Commit**

```bash
git add scripts/feature_mining_phase1.py
git commit -m "feat(feature_library): add Phase 1 entry script

uv run python scripts/feature_mining_phase1.py 跑通端到端：
PKL → BreakoutDetector → 5 张 samples（复用 / preprocess）→
Inducer batch（GLM-4V-Flash 单次 ≤5 张）→ Librarian 累积入 features 库
+ 打印库摘要（α / β / P5 / status_band / obs 数）。
参数声明在 main() 起始（CLAUDE.md 要求）。"
```

---

## Task 10: Phase 1 acceptance verification + system_outline 更新

**Files:**
- Modify: `.claude/docs/system_outline.md`

- [ ] **Step 10.1: Run full test suite**

Run: `uv run pytest BreakoutStrategy/feature_library/tests/ -v`

Expected: ~98 tests passed:
- Phase 0 unchanged: 28（除 glm4v_backend 文件外）
- glm4v_backend 增至 12（原 7 + Phase 1 加 5）
- Phase 1 new: 58（feature_models 15 + embedding_l0 5 + feature_store 10 + observation_log 5 + inducer_prompts 6 + inducer 9 + librarian 8）
- Total: ~98（允许 ±5 因实施期个别断言增减）

If any test fails, fix before proceeding.

- [ ] **Step 10.2: Verify Phase 1 vertical slice artifact**

```bash
ls -la /home/yu/PycharmProjects/Trade_Strategy/feature_library/features/ \
       /home/yu/PycharmProjects/Trade_Strategy/feature_library/samples/
```

Expected:
- `samples/` 至少 5 个 BO_AAPL_*/ 子目录（Phase 0 + Phase 1 累计）
- `features/` 至少 1 个 F-*.yaml

读一个 features yaml 验证 schema 完整：
```bash
cat /home/yu/PycharmProjects/Trade_Strategy/feature_library/features/F-001*.yaml | head -30
```

- [ ] **Step 10.3: Update .claude/docs/system_outline.md**

Read existing file:
```bash
cat /home/yu/PycharmProjects/Trade_Strategy/.claude/docs/system_outline.md
```

Find the row added by Phase 0 (mentioning "Phase 0 数据基线"). Replace it with:

```
| 特征库 MVP | `BreakoutStrategy/feature_library/` | — | Phase 0 数据基线（chart + meta + nl_description via GLM-4V-Flash）+ Phase 1 Librarian + Inducer batch 归纳（Beta-Binomial 累积 features 库） |
```

- [ ] **Step 10.4: Commit**

```bash
git add .claude/docs/system_outline.md
git commit -m "docs: register Phase 1 Librarian + Inducer in system outline"
```

- [ ] **Step 10.5: Validate Phase 1 acceptance criteria**

| AC | 通过判据 | 验证 |
|---|---|---|
| AC1 包结构完整 | 7 新模块 + 1 修改（glm4v_backend）| `ls BreakoutStrategy/feature_library/*.py` |
| AC2 全测试 PASS | 80+ tests | Step 10.1 |
| AC3 端到端 entry script 跑通 | scripts/feature_mining_phase1.py 不报错完成 | Step 9.2 |
| AC4 GLM-4V-Flash 多图调通 | Inducer 产出 ≥0 candidate（可能 0 但 API 调通）| Step 9.2 输出含 "Inducer 产出 N 个 candidate" |
| AC5 features 库非空 | feature_library/features/F-*.yaml 至少 1 个 | Step 10.2 |
| AC6 features yaml schema 完整 | 含 epoch_tag/superseded_by/provenance（null）| Step 10.2 cat 验证 |
| AC7 ObservationLog 按 sample 粒度 | 每条 obs 含 sample_id；同 batch 多条 | Step 10.2 cat 验证 |
| AC8 Beta-Binomial 公式正确 | recompute 单元测试覆盖 | Task 8 测试 |
| AC9 L0 merge 工作 | 两相似 candidate 合并到同 feature | Task 8 测试 |
| AC10 runtime 不进 git | features/ 在 .gitignore | `git status` 不含 features/ |

If all 10 ACs pass, Phase 1 is complete. Phase 1.5 / 2 / 3 plans can be drafted next.

---

## Out of Scope（搁置到对应 Phase）

- DeepSeek L1 verify backend → Phase 1.5
- merge-policy 三选项（full / supersede-only / reject-merge）→ Phase 1.5
- ObservationLog supersede 机制实际逻辑 → Phase 1.5
- Replay 队列（pending_replays.yaml）→ Phase 1.5
- Path V incremental verify → Phase 2
- `feature-mine` CLI 命令套件 → Phase 2
- chunked batch（>5 张样本拆多次调用）→ Phase 2
- 被动提醒（孤儿 / health / pending replays）→ Phase 2
- INDEX.md 自动生成 → Phase 2
- Critic 角色 → Phase 3
- Reshuffle / archetype hint → Phase 4+
