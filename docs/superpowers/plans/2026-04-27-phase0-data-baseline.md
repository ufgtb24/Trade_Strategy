# Feature Mining Phase 0 — Data Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the data baseline pipeline: given a breakout sample, produce `feature_library/samples/<id>/{chart.png, meta.yaml, nl_description.md}` using GLM-4V-Flash multimodal model in place of Opus.

**Architecture:** New package `BreakoutStrategy/feature_library/` with 5 focused modules: paths constants, sample meta builder (factor values + breakout context), sample chart renderer (matplotlib PNG export reusing existing `CandlestickComponent`), GLM-4V-Flash backend (zhipuai SDK following the existing `GLMBackend` text-only pattern), and a preprocess orchestrator. Entry script at `scripts/feature_mining_phase0.py` runs the vertical slice.

**Tech Stack:** Python 3.11+, matplotlib (already in deps), zhipuai SDK (already in deps, `glm-4v-flash` model), pyyaml, pandas. Tests use pytest with mocked zhipuai client for unit, real API for integration.

**Spec reference:** `docs/superpowers/specs/2026-04-25-feature-induction-framework-design.md` §2.1 (data flow), §4.1 (file system), §5.4 Phase 0 row.

**Out of scope (Phase 1+):** Beta-Binomial / ObservationLog / Librarian / Inducer batch / DeepSeek L1 verify / CLI Scheduler / Critic / Reshuffle.

---

## File Structure

### New files (created in this plan)

| Path | Responsibility | Approx LOC |
|---|---|---|
| `BreakoutStrategy/feature_library/__init__.py` | Package init + public exports | 15 |
| `BreakoutStrategy/feature_library/paths.py` | Filesystem path constants and `sample_dir(id)` resolver | 40 |
| `BreakoutStrategy/feature_library/sample_id.py` | Stable ID generation `BO_<TICKER>_<YYYYMMDD>` from breakout | 30 |
| `BreakoutStrategy/feature_library/sample_meta.py` | Build `meta.yaml` content from `Breakout` object (5 consolidation fields + base context) | 90 |
| `BreakoutStrategy/feature_library/sample_renderer.py` | Render `chart.png` for a breakout window (reuses `CandlestickComponent`) | 110 |
| `BreakoutStrategy/feature_library/glm4v_backend.py` | `GLM4VBackend` class — `glm-4v-flash` multimodal call with retry | 120 |
| `BreakoutStrategy/feature_library/prompts.py` | nl_description SYSTEM_PROMPT + `build_user_message(meta_dict)` | 60 |
| `BreakoutStrategy/feature_library/preprocess.py` | `preprocess_sample(...)` orchestrator | 80 |
| `BreakoutStrategy/feature_library/tests/__init__.py` | empty | 0 |
| `BreakoutStrategy/feature_library/tests/test_paths.py` | paths unit tests | 30 |
| `BreakoutStrategy/feature_library/tests/test_sample_id.py` | id generation tests | 30 |
| `BreakoutStrategy/feature_library/tests/test_sample_meta.py` | meta builder tests | 60 |
| `BreakoutStrategy/feature_library/tests/test_sample_renderer.py` | renderer smoke + fixture tests | 60 |
| `BreakoutStrategy/feature_library/tests/test_prompts.py` | prompt builder tests | 30 |
| `BreakoutStrategy/feature_library/tests/test_glm4v_backend.py` | backend tests with mocked zhipuai client | 90 |
| `BreakoutStrategy/feature_library/tests/test_preprocess.py` | preprocess orchestrator end-to-end (mocked GLM call) | 70 |
| `scripts/feature_mining_phase0.py` | Entry script (no argparse, params at top of `main()`) | 80 |

### Reused existing files (no modification)

- `BreakoutStrategy/UI/charts/components/candlestick.py` — `CandlestickComponent.draw(ax, df)`
- `BreakoutStrategy/news_sentiment/backends/glm_backend.py` — pattern reference
- `BreakoutStrategy/analysis/breakout_detector.py` — `Breakout` dataclass
- `BreakoutStrategy/analysis/features.py` — `FeatureCalculator` for factor values
- `BreakoutStrategy/factor_registry.py` — factor metadata
- `configs/api_keys.yaml` — `zhipuai` key

### Runtime data directory (created at runtime by entry script, not committed)

```
feature_library/
└── samples/
    └── BO_<TICKER>_<YYYYMMDD>/
        ├── meta.yaml
        ├── chart.png
        └── nl_description.md
```

Add `feature_library/` to `.gitignore` so runtime data never enters git.

---

## "5 个盘整字段" Definition (locked here)

Spec §5.4 mentions "5 个盘整字段" without enumeration. Locked for this plan as the 5 consolidation-phase descriptors written into `meta.yaml`:

1. **`consolidation_length_bars`** — number of bars in the consolidation phase before breakout
2. **`consolidation_height_pct`** — `(high - low) / low * 100` of consolidation range
3. **`consolidation_position_vs_52w_high`** — consolidation midpoint distance to 52-week high (percent)
4. **`consolidation_volume_ratio`** — average volume during consolidation / average volume of preceding 60 bars
5. **`consolidation_tightness_atr`** — consolidation height / ATR(14) at breakout day

These are computed from the existing `Breakout` object (already has `bo_index`, `pk_index`, `df_window`). If a field cannot be computed (e.g., insufficient lookback), set to `null`.

---

## Task 1: Package skeleton + paths

**Files:**
- Create: `BreakoutStrategy/feature_library/__init__.py`
- Create: `BreakoutStrategy/feature_library/paths.py`
- Create: `BreakoutStrategy/feature_library/tests/__init__.py`
- Create: `BreakoutStrategy/feature_library/tests/test_paths.py`
- Modify: `.gitignore` (add `feature_library/`)

- [ ] **Step 1.1: Write the failing test for paths**

`BreakoutStrategy/feature_library/tests/test_paths.py`:

```python
"""Tests for feature_library path constants."""
from pathlib import Path

from BreakoutStrategy.feature_library import paths


def test_feature_library_root_is_repo_relative():
    """FEATURE_LIBRARY_ROOT 应位于 repo 根目录下的 feature_library/。"""
    assert paths.FEATURE_LIBRARY_ROOT.name == "feature_library"
    assert paths.FEATURE_LIBRARY_ROOT.is_absolute()


def test_samples_dir_under_root():
    assert paths.SAMPLES_DIR == paths.FEATURE_LIBRARY_ROOT / "samples"


def test_sample_dir_resolution():
    sample_id = "BO_AAPL_20230115"
    expected = paths.SAMPLES_DIR / sample_id
    assert paths.sample_dir(sample_id) == expected


def test_sample_artifact_paths():
    sample_id = "BO_AAPL_20230115"
    base = paths.sample_dir(sample_id)
    assert paths.chart_png_path(sample_id) == base / "chart.png"
    assert paths.meta_yaml_path(sample_id) == base / "meta.yaml"
    assert paths.nl_description_path(sample_id) == base / "nl_description.md"


def test_ensure_sample_dir_creates(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "FEATURE_LIBRARY_ROOT", tmp_path / "feature_library")
    monkeypatch.setattr(paths, "SAMPLES_DIR", paths.FEATURE_LIBRARY_ROOT / "samples")
    sample_id = "BO_TEST_20260101"
    created = paths.ensure_sample_dir(sample_id)
    assert created.is_dir()
    assert created == paths.SAMPLES_DIR / sample_id
```

- [ ] **Step 1.2: Run test to verify it fails**

Run: `uv run pytest BreakoutStrategy/feature_library/tests/test_paths.py -v`
Expected: ImportError or ModuleNotFoundError for `feature_library`.

- [ ] **Step 1.3: Create package skeleton**

`BreakoutStrategy/feature_library/__init__.py`:

```python
"""特征归纳框架 — Phase 0: 数据基线模块。

负责把单条 breakout 样本转换为 feature_library/samples/<id>/
下的三件套：chart.png + meta.yaml + nl_description.md。
"""
```

`BreakoutStrategy/feature_library/tests/__init__.py`: empty file.

- [ ] **Step 1.4: Implement paths.py**

`BreakoutStrategy/feature_library/paths.py`:

```python
"""特征库文件系统路径常量。

统一管理 feature_library/ 根目录及其子结构的路径解析，
避免散落的字符串拼接。所有路径均返回绝对 Path。
"""

from pathlib import Path

# 项目根目录（repo root），由本文件所在位置反推
_REPO_ROOT = Path(__file__).resolve().parents[2]

FEATURE_LIBRARY_ROOT: Path = _REPO_ROOT / "feature_library"
SAMPLES_DIR: Path = FEATURE_LIBRARY_ROOT / "samples"


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
```

- [ ] **Step 1.5: Run test to verify it passes**

Run: `uv run pytest BreakoutStrategy/feature_library/tests/test_paths.py -v`
Expected: 5 passed.

- [ ] **Step 1.6: Add feature_library/ to .gitignore**

Append to `.gitignore`:

```
# Feature mining runtime data (generated by feature_library pipeline)
feature_library/
```

- [ ] **Step 1.7: Commit**

```bash
git add BreakoutStrategy/feature_library/__init__.py \
        BreakoutStrategy/feature_library/paths.py \
        BreakoutStrategy/feature_library/tests/__init__.py \
        BreakoutStrategy/feature_library/tests/test_paths.py \
        .gitignore
git commit -m "feat(feature_library): add package skeleton + paths constants

Phase 0 step 1: 引入 BreakoutStrategy/feature_library/ 包，定义
samples/<id>/{chart.png, meta.yaml, nl_description.md} 路径解析。
runtime data dir feature_library/ 加入 .gitignore。"
```

---

## Task 2: Sample ID generation

**Files:**
- Create: `BreakoutStrategy/feature_library/sample_id.py`
- Create: `BreakoutStrategy/feature_library/tests/test_sample_id.py`

- [ ] **Step 2.1: Write the failing test**

`BreakoutStrategy/feature_library/tests/test_sample_id.py`:

```python
"""Tests for sample ID generation."""
from datetime import date

import pandas as pd

from BreakoutStrategy.feature_library.sample_id import generate_sample_id


def test_generate_from_ticker_and_date_object():
    sample_id = generate_sample_id(ticker="AAPL", bo_date=date(2023, 1, 15))
    assert sample_id == "BO_AAPL_20230115"


def test_generate_from_ticker_and_pandas_timestamp():
    ts = pd.Timestamp("2024-12-03")
    sample_id = generate_sample_id(ticker="MSFT", bo_date=ts)
    assert sample_id == "BO_MSFT_20241203"


def test_ticker_uppercased():
    sample_id = generate_sample_id(ticker="aapl", bo_date=date(2023, 1, 15))
    assert sample_id == "BO_AAPL_20230115"


def test_strips_dot_in_ticker():
    """部分美股 ticker 含点号（如 BRK.B），需替换为下划线以适配文件系统。"""
    sample_id = generate_sample_id(ticker="BRK.B", bo_date=date(2023, 1, 15))
    assert sample_id == "BO_BRK_B_20230115"
```

- [ ] **Step 2.2: Run test to verify it fails**

Run: `uv run pytest BreakoutStrategy/feature_library/tests/test_sample_id.py -v`
Expected: ImportError.

- [ ] **Step 2.3: Implement sample_id.py**

`BreakoutStrategy/feature_library/sample_id.py`:

```python
"""Sample ID 生成。

样本 ID 形如 BO_AAPL_20230115，作为 feature_library/samples/ 子目录名
+ 后续 ObservationLog / cooccurrence 引用主键。
"""

from datetime import date, datetime

import pandas as pd


def generate_sample_id(ticker: str, bo_date) -> str:
    """从 ticker 和突破日期生成稳定的 sample ID。

    Args:
        ticker: 股票代码（自动转大写，点号替换为下划线）
        bo_date: 突破日期，可以是 date / datetime / pandas.Timestamp

    Returns:
        形如 "BO_AAPL_20230115" 的字符串
    """
    if isinstance(bo_date, pd.Timestamp):
        date_str = bo_date.strftime("%Y%m%d")
    elif isinstance(bo_date, (date, datetime)):
        date_str = bo_date.strftime("%Y%m%d")
    else:
        raise TypeError(f"bo_date 类型不支持：{type(bo_date)}")

    safe_ticker = ticker.upper().replace(".", "_")
    return f"BO_{safe_ticker}_{date_str}"
```

- [ ] **Step 2.4: Run test to verify it passes**

Run: `uv run pytest BreakoutStrategy/feature_library/tests/test_sample_id.py -v`
Expected: 4 passed.

- [ ] **Step 2.5: Commit**

```bash
git add BreakoutStrategy/feature_library/sample_id.py \
        BreakoutStrategy/feature_library/tests/test_sample_id.py
git commit -m "feat(feature_library): add sample_id generator

格式 BO_<TICKER>_<YYYYMMDD>，自动 upper-case + 点号→下划线。"
```

---

## Task 3: Consolidation field calculator (5 fields)

**Files:**
- Create: `BreakoutStrategy/feature_library/consolidation_fields.py`
- Create: `BreakoutStrategy/feature_library/tests/test_consolidation_fields.py`

- [ ] **Step 3.1: Write the failing test**

`BreakoutStrategy/feature_library/tests/test_consolidation_fields.py`:

```python
"""Tests for consolidation field calculator (5 字段)."""
import numpy as np
import pandas as pd
import pytest

from BreakoutStrategy.feature_library.consolidation_fields import (
    compute_consolidation_fields,
)


@pytest.fixture
def synthetic_df():
    """构造 100 个交易日的合成数据：前 60 天波动，后 30 天紧凑盘整，最后突破。"""
    n = 100
    dates = pd.date_range("2023-01-01", periods=n, freq="B")
    rng = np.random.default_rng(seed=42)

    # 前 60 天：波动 20-30
    pre_close = rng.uniform(20, 30, 60)
    # 后 30 天：紧凑盘整 28-32
    consol_close = rng.uniform(28, 32, 30)
    # 突破日：跳到 35
    breakout_close = np.array([35.0])

    closes = np.concatenate([pre_close, consol_close, breakout_close])
    highs = closes * 1.02
    lows = closes * 0.98
    opens = closes * 1.0
    volumes = np.concatenate([
        rng.uniform(800_000, 1_200_000, 60),       # 前期均量 ~1M
        rng.uniform(400_000, 600_000, 30),         # 盘整期缩量 ~500K
        np.array([2_500_000]),                     # 突破日放量
    ])

    return pd.DataFrame({
        "Open": opens, "High": highs, "Low": lows, "Close": closes,
        "Volume": volumes,
    }, index=dates)


def test_returns_5_keys(synthetic_df):
    fields = compute_consolidation_fields(
        df=synthetic_df, bo_index=90, pk_index=60,
    )
    assert set(fields.keys()) == {
        "consolidation_length_bars",
        "consolidation_height_pct",
        "consolidation_position_vs_52w_high",
        "consolidation_volume_ratio",
        "consolidation_tightness_atr",
    }


def test_length_bars_equals_bo_minus_pk(synthetic_df):
    fields = compute_consolidation_fields(
        df=synthetic_df, bo_index=90, pk_index=60,
    )
    assert fields["consolidation_length_bars"] == 30


def test_volume_ratio_below_one_for_quiet_consolidation(synthetic_df):
    """合成数据盘整期均量 ~500K vs 前期 ~1M，比值应 < 1。"""
    fields = compute_consolidation_fields(
        df=synthetic_df, bo_index=90, pk_index=60,
    )
    assert 0 < fields["consolidation_volume_ratio"] < 1.0


def test_height_pct_positive(synthetic_df):
    fields = compute_consolidation_fields(
        df=synthetic_df, bo_index=90, pk_index=60,
    )
    assert fields["consolidation_height_pct"] > 0


def test_insufficient_lookback_returns_null(synthetic_df):
    """pk_index 太小时无法计算 volume_ratio 的前置 60 bars，应返回 None。"""
    fields = compute_consolidation_fields(
        df=synthetic_df, bo_index=30, pk_index=20,
    )
    assert fields["consolidation_volume_ratio"] is None
```

- [ ] **Step 3.2: Run test to verify it fails**

Run: `uv run pytest BreakoutStrategy/feature_library/tests/test_consolidation_fields.py -v`
Expected: ImportError.

- [ ] **Step 3.3: Implement consolidation_fields.py**

`BreakoutStrategy/feature_library/consolidation_fields.py`:

```python
"""计算 nl_description 所需的 5 个盘整阶段描述字段。

输入：原始 OHLCV df + 突破点 bo_index + 盘整起点 pk_index
输出：dict[str, float | None] — 5 个字段，无法计算时返回 None
"""

from typing import Optional

import numpy as np
import pandas as pd

ATR_PERIOD = 14
PRE_CONSOL_VOLUME_LOOKBACK = 60
WEEKS_52_BARS = 252  # 美股交易日


def compute_consolidation_fields(
    df: pd.DataFrame, bo_index: int, pk_index: int,
) -> dict[str, Optional[float]]:
    """计算盘整阶段 5 字段。

    Args:
        df: OHLCV DataFrame，列名首字母大写（Open/High/Low/Close/Volume）
        bo_index: 突破日 index
        pk_index: 盘整起点（前一个 peak）index

    Returns:
        5 字段字典，元素为 float 或 None（数据不足时）
    """
    result = {
        "consolidation_length_bars": _length_bars(bo_index, pk_index),
        "consolidation_height_pct": _height_pct(df, bo_index, pk_index),
        "consolidation_position_vs_52w_high": _position_vs_52w_high(df, bo_index, pk_index),
        "consolidation_volume_ratio": _volume_ratio(df, bo_index, pk_index),
        "consolidation_tightness_atr": _tightness_atr(df, bo_index, pk_index),
    }
    return result


def _length_bars(bo_index: int, pk_index: int) -> int:
    return int(bo_index - pk_index)


def _height_pct(df: pd.DataFrame, bo_index: int, pk_index: int) -> Optional[float]:
    consol = df.iloc[pk_index:bo_index]
    if len(consol) < 2:
        return None
    high = consol["High"].max()
    low = consol["Low"].min()
    if low <= 0:
        return None
    return float((high - low) / low * 100)


def _position_vs_52w_high(
    df: pd.DataFrame, bo_index: int, pk_index: int,
) -> Optional[float]:
    """盘整中位价对 52 周高的距离百分比（负值 = 距离高点；正值 = 突破高点）。"""
    if bo_index < WEEKS_52_BARS:
        return None
    consol = df.iloc[pk_index:bo_index]
    if len(consol) < 2:
        return None
    consol_mid = float((consol["High"].max() + consol["Low"].min()) / 2)
    high_52w = float(df.iloc[bo_index - WEEKS_52_BARS:bo_index]["High"].max())
    if high_52w <= 0:
        return None
    return (consol_mid - high_52w) / high_52w * 100


def _volume_ratio(
    df: pd.DataFrame, bo_index: int, pk_index: int,
) -> Optional[float]:
    """盘整期均量 / 盘整前 60 bars 均量。"""
    if pk_index < PRE_CONSOL_VOLUME_LOOKBACK:
        return None
    consol = df.iloc[pk_index:bo_index]
    pre = df.iloc[pk_index - PRE_CONSOL_VOLUME_LOOKBACK:pk_index]
    if len(consol) < 2 or len(pre) < 2:
        return None
    consol_vol = float(consol["Volume"].mean())
    pre_vol = float(pre["Volume"].mean())
    if pre_vol <= 0:
        return None
    return consol_vol / pre_vol


def _tightness_atr(
    df: pd.DataFrame, bo_index: int, pk_index: int,
) -> Optional[float]:
    """盘整 height / ATR(14) at breakout day。"""
    if bo_index < ATR_PERIOD:
        return None
    consol = df.iloc[pk_index:bo_index]
    if len(consol) < 2:
        return None
    height = float(consol["High"].max() - consol["Low"].min())
    atr_window = df.iloc[bo_index - ATR_PERIOD:bo_index]
    tr = np.maximum.reduce([
        atr_window["High"].values - atr_window["Low"].values,
        np.abs(atr_window["High"].values - atr_window["Close"].shift(1).values),
        np.abs(atr_window["Low"].values - atr_window["Close"].shift(1).values),
    ])
    atr = float(np.nanmean(tr))
    if atr <= 0:
        return None
    return height / atr
```

- [ ] **Step 3.4: Run test to verify it passes**

Run: `uv run pytest BreakoutStrategy/feature_library/tests/test_consolidation_fields.py -v`
Expected: 5 passed.

- [ ] **Step 3.5: Commit**

```bash
git add BreakoutStrategy/feature_library/consolidation_fields.py \
        BreakoutStrategy/feature_library/tests/test_consolidation_fields.py
git commit -m "feat(feature_library): add 5-field consolidation calculator

字段：length_bars / height_pct / position_vs_52w_high /
volume_ratio / tightness_atr。数据不足时返回 None。"
```

---

## Task 4: Sample meta builder

**Files:**
- Create: `BreakoutStrategy/feature_library/sample_meta.py`
- Create: `BreakoutStrategy/feature_library/tests/test_sample_meta.py`

- [ ] **Step 4.1: Write the failing test**

`BreakoutStrategy/feature_library/tests/test_sample_meta.py`:

```python
"""Tests for sample meta.yaml builder."""
from datetime import datetime

import numpy as np
import pandas as pd
import pytest
import yaml

from BreakoutStrategy.feature_library.sample_meta import (
    build_meta, write_meta_yaml,
)


@pytest.fixture
def synthetic_df():
    n = 300  # 含 52 周回看
    dates = pd.date_range("2023-01-01", periods=n, freq="B")
    rng = np.random.default_rng(seed=42)
    closes = rng.uniform(20, 35, n)
    return pd.DataFrame({
        "Open": closes, "High": closes * 1.02, "Low": closes * 0.98,
        "Close": closes, "Volume": rng.uniform(500_000, 1_500_000, n),
    }, index=dates)


def test_meta_top_level_keys(synthetic_df):
    meta = build_meta(
        sample_id="BO_AAPL_20240301",
        ticker="AAPL",
        bo_date=pd.Timestamp("2024-03-01"),
        df_window=synthetic_df,
        bo_index=290,
        pk_index=260,
        picked_at=datetime(2026, 4, 27, 10, 30),
    )
    assert meta["sample_id"] == "BO_AAPL_20240301"
    assert meta["ticker"] == "AAPL"
    assert meta["bo_date"] == "2024-03-01"
    assert meta["picked_at"] == "2026-04-27T10:30:00"
    assert "consolidation" in meta
    assert "breakout_day" in meta


def test_consolidation_block_has_5_fields(synthetic_df):
    meta = build_meta(
        sample_id="BO_AAPL_20240301",
        ticker="AAPL",
        bo_date=pd.Timestamp("2024-03-01"),
        df_window=synthetic_df,
        bo_index=290,
        pk_index=260,
        picked_at=datetime(2026, 4, 27, 10, 30),
    )
    consol = meta["consolidation"]
    assert set(consol.keys()) == {
        "consolidation_length_bars",
        "consolidation_height_pct",
        "consolidation_position_vs_52w_high",
        "consolidation_volume_ratio",
        "consolidation_tightness_atr",
    }


def test_breakout_day_block(synthetic_df):
    meta = build_meta(
        sample_id="BO_AAPL_20240301",
        ticker="AAPL",
        bo_date=pd.Timestamp("2024-03-01"),
        df_window=synthetic_df,
        bo_index=290,
        pk_index=260,
        picked_at=datetime(2026, 4, 27, 10, 30),
    )
    bo = meta["breakout_day"]
    assert "open" in bo and "high" in bo and "low" in bo
    assert "close" in bo and "volume" in bo


def test_write_meta_yaml_roundtrip(tmp_path, synthetic_df, monkeypatch):
    from BreakoutStrategy.feature_library import paths
    monkeypatch.setattr(paths, "FEATURE_LIBRARY_ROOT", tmp_path / "feature_library")
    monkeypatch.setattr(paths, "SAMPLES_DIR", paths.FEATURE_LIBRARY_ROOT / "samples")

    sample_id = "BO_TEST_20240301"
    meta = build_meta(
        sample_id=sample_id, ticker="TEST",
        bo_date=pd.Timestamp("2024-03-01"),
        df_window=synthetic_df, bo_index=290, pk_index=260,
        picked_at=datetime(2026, 4, 27, 10, 30),
    )
    out_path = write_meta_yaml(sample_id, meta)
    assert out_path.exists()

    loaded = yaml.safe_load(out_path.read_text())
    assert loaded["sample_id"] == sample_id
    assert loaded["ticker"] == "TEST"
```

- [ ] **Step 4.2: Run test to verify it fails**

Run: `uv run pytest BreakoutStrategy/feature_library/tests/test_sample_meta.py -v`
Expected: ImportError.

- [ ] **Step 4.3: Implement sample_meta.py**

`BreakoutStrategy/feature_library/sample_meta.py`:

```python
"""构建 samples/<id>/meta.yaml 内容。

meta.yaml 含：sample_id / ticker / bo_date / picked_at /
breakout_day OHLCV / consolidation 5 字段。
后续可扩展（factor 原值 / 用户备注 / archetype tag 等）。
"""

from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from BreakoutStrategy.feature_library import paths
from BreakoutStrategy.feature_library.consolidation_fields import (
    compute_consolidation_fields,
)


def build_meta(
    sample_id: str,
    ticker: str,
    bo_date: pd.Timestamp,
    df_window: pd.DataFrame,
    bo_index: int,
    pk_index: int,
    picked_at: datetime,
) -> dict[str, Any]:
    """构建 meta.yaml 的 dict 内容。

    Args:
        sample_id: 形如 BO_AAPL_20240301
        ticker: 股票代码（已 upper）
        bo_date: 突破日期
        df_window: 包含 bo_index / pk_index 上下文的 OHLCV 切片
        bo_index: 突破日在 df_window 中的位置
        pk_index: 盘整起点在 df_window 中的位置
        picked_at: 用户挑选时间

    Returns:
        可直接 yaml.safe_dump 的 dict
    """
    bo_row = df_window.iloc[bo_index]
    consol = compute_consolidation_fields(df_window, bo_index, pk_index)

    return {
        "sample_id": sample_id,
        "ticker": ticker,
        "bo_date": bo_date.strftime("%Y-%m-%d"),
        "picked_at": picked_at.isoformat(timespec="seconds"),
        "breakout_day": {
            "open": float(bo_row["Open"]),
            "high": float(bo_row["High"]),
            "low": float(bo_row["Low"]),
            "close": float(bo_row["Close"]),
            "volume": float(bo_row["Volume"]),
        },
        "consolidation": consol,
    }


def write_meta_yaml(sample_id: str, meta: dict[str, Any]) -> Path:
    """将 meta dict 写入 samples/<id>/meta.yaml，返回写入路径。"""
    paths.ensure_sample_dir(sample_id)
    out_path = paths.meta_yaml_path(sample_id)
    out_path.write_text(yaml.safe_dump(meta, sort_keys=False, allow_unicode=True))
    return out_path
```

- [ ] **Step 4.4: Run test to verify it passes**

Run: `uv run pytest BreakoutStrategy/feature_library/tests/test_sample_meta.py -v`
Expected: 4 passed.

- [ ] **Step 4.5: Commit**

```bash
git add BreakoutStrategy/feature_library/sample_meta.py \
        BreakoutStrategy/feature_library/tests/test_sample_meta.py
git commit -m "feat(feature_library): add meta.yaml builder + writer

含 sample_id / ticker / bo_date / picked_at / breakout_day OHLCV /
consolidation 5 字段。yaml.safe_dump 落盘。"
```

---

## Task 5: Sample chart renderer

**Files:**
- Create: `BreakoutStrategy/feature_library/sample_renderer.py`
- Create: `BreakoutStrategy/feature_library/tests/test_sample_renderer.py`

- [ ] **Step 5.1: Write the failing test**

`BreakoutStrategy/feature_library/tests/test_sample_renderer.py`:

```python
"""Tests for sample chart renderer."""
import numpy as np
import pandas as pd
import pytest

from BreakoutStrategy.feature_library.sample_renderer import render_sample_chart


@pytest.fixture
def synthetic_df():
    n = 100
    dates = pd.date_range("2023-01-01", periods=n, freq="B")
    rng = np.random.default_rng(seed=42)
    closes = rng.uniform(20, 35, n)
    return pd.DataFrame({
        "Open": closes, "High": closes * 1.02, "Low": closes * 0.98,
        "Close": closes, "Volume": rng.uniform(500_000, 1_500_000, n),
    }, index=dates)


def test_render_creates_png_file(tmp_path, synthetic_df, monkeypatch):
    from BreakoutStrategy.feature_library import paths
    monkeypatch.setattr(paths, "FEATURE_LIBRARY_ROOT", tmp_path / "feature_library")
    monkeypatch.setattr(paths, "SAMPLES_DIR", paths.FEATURE_LIBRARY_ROOT / "samples")

    out_path = render_sample_chart(
        sample_id="BO_TEST_20230301",
        df_window=synthetic_df,
        bo_index=90,
        pk_index=60,
    )
    assert out_path.exists()
    assert out_path.suffix == ".png"
    assert out_path.stat().st_size > 5_000  # PNG 至少 5KB（确认非空）


def test_render_idempotent(tmp_path, synthetic_df, monkeypatch):
    """重复渲染应覆盖原文件，不报错。"""
    from BreakoutStrategy.feature_library import paths
    monkeypatch.setattr(paths, "FEATURE_LIBRARY_ROOT", tmp_path / "feature_library")
    monkeypatch.setattr(paths, "SAMPLES_DIR", paths.FEATURE_LIBRARY_ROOT / "samples")

    sample_id = "BO_TEST_20230301"
    p1 = render_sample_chart(sample_id, synthetic_df, 90, 60)
    p2 = render_sample_chart(sample_id, synthetic_df, 90, 60)
    assert p1 == p2
    assert p2.exists()
```

- [ ] **Step 5.2: Run test to verify it fails**

Run: `uv run pytest BreakoutStrategy/feature_library/tests/test_sample_renderer.py -v`
Expected: ImportError.

- [ ] **Step 5.3: Implement sample_renderer.py**

`BreakoutStrategy/feature_library/sample_renderer.py`:

```python
"""渲染 samples/<id>/chart.png — AI 友好的静态 K 线图。

复用 BreakoutStrategy/UI/charts/components/candlestick.py 的
CandlestickComponent.draw 在 matplotlib Axes 上绘制 K 线主体；
本模块负责构造 Figure、添加 volume subplot、标注 bo / pk 位置、
导出 PNG（不交互、固定尺寸、统一风格）。
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # 无显示后端，避免 GUI 依赖
import matplotlib.pyplot as plt
import pandas as pd

from BreakoutStrategy.feature_library import paths
from BreakoutStrategy.UI.charts.components.candlestick import CandlestickComponent

CHART_DPI = 100
CHART_FIGSIZE = (12, 8)
PRICE_PANEL_RATIO = 3
VOLUME_PANEL_RATIO = 1


def render_sample_chart(
    sample_id: str,
    df_window: pd.DataFrame,
    bo_index: int,
    pk_index: int,
) -> Path:
    """渲染单个 breakout 样本的 K 线图为 PNG。

    Args:
        sample_id: 样本 ID
        df_window: OHLCV DataFrame，DatetimeIndex
        bo_index: 突破日 index
        pk_index: 盘整起点 index

    Returns:
        生成的 PNG 文件绝对路径
    """
    paths.ensure_sample_dir(sample_id)
    out_path = paths.chart_png_path(sample_id)

    fig, (ax_price, ax_vol) = plt.subplots(
        2, 1,
        figsize=CHART_FIGSIZE, dpi=CHART_DPI,
        gridspec_kw={"height_ratios": [PRICE_PANEL_RATIO, VOLUME_PANEL_RATIO]},
        sharex=True,
    )

    # 主图：K 线
    CandlestickComponent.draw(ax_price, df_window)

    # 标注 pk 与 bo 垂直线
    ax_price.axvline(x=pk_index, color="#FF9800", linestyle="--",
                     linewidth=1.5, label="pk (consolidation start)")
    ax_price.axvline(x=bo_index, color="#2196F3", linestyle="--",
                     linewidth=1.5, label="bo (breakout)")
    ax_price.set_title(f"{sample_id}")
    ax_price.set_ylabel("Price")
    ax_price.legend(loc="upper left")
    ax_price.grid(True, alpha=0.3)

    # 副图：volume bar
    ax_vol.bar(range(len(df_window)), df_window["Volume"], color="#888888", width=0.8)
    ax_vol.axvline(x=pk_index, color="#FF9800", linestyle="--", linewidth=1.0)
    ax_vol.axvline(x=bo_index, color="#2196F3", linestyle="--", linewidth=1.0)
    ax_vol.set_ylabel("Volume")
    ax_vol.set_xlabel("Bar Index")
    ax_vol.grid(True, alpha=0.3)

    fig.tight_layout()
    fig.savefig(out_path, format="png", bbox_inches="tight")
    plt.close(fig)

    return out_path
```

- [ ] **Step 5.4: Run test to verify it passes**

Run: `uv run pytest BreakoutStrategy/feature_library/tests/test_sample_renderer.py -v`
Expected: 2 passed.

- [ ] **Step 5.5: Commit**

```bash
git add BreakoutStrategy/feature_library/sample_renderer.py \
        BreakoutStrategy/feature_library/tests/test_sample_renderer.py
git commit -m "feat(feature_library): add sample chart renderer (PNG export)

复用 CandlestickComponent.draw，新建 Agg 后端 Figure，
添加 volume 子面板 + pk/bo 垂直标注，导出 chart.png。"
```

---

## Task 6: nl_description prompt module

**Files:**
- Create: `BreakoutStrategy/feature_library/prompts.py`
- Create: `BreakoutStrategy/feature_library/tests/test_prompts.py`

- [ ] **Step 6.1: Write the failing test**

`BreakoutStrategy/feature_library/tests/test_prompts.py`:

```python
"""Tests for nl_description prompts."""
from BreakoutStrategy.feature_library.prompts import (
    SYSTEM_PROMPT, build_user_message,
)


def test_system_prompt_non_empty():
    assert SYSTEM_PROMPT
    assert "K-line" in SYSTEM_PROMPT or "K 线" in SYSTEM_PROMPT


def test_user_message_includes_meta_fields():
    meta = {
        "sample_id": "BO_AAPL_20230115",
        "ticker": "AAPL",
        "bo_date": "2023-01-15",
        "breakout_day": {
            "open": 130.0, "high": 135.0, "low": 129.0,
            "close": 134.0, "volume": 100_000_000,
        },
        "consolidation": {
            "consolidation_length_bars": 30,
            "consolidation_height_pct": 5.2,
            "consolidation_position_vs_52w_high": -3.1,
            "consolidation_volume_ratio": 0.55,
            "consolidation_tightness_atr": 1.8,
        },
    }
    msg = build_user_message(meta)
    assert "AAPL" in msg
    assert "2023-01-15" in msg
    assert "30" in msg  # length_bars
    assert "5.2" in msg  # height_pct


def test_user_message_handles_null_fields():
    meta = {
        "sample_id": "BO_AAPL_20230115",
        "ticker": "AAPL",
        "bo_date": "2023-01-15",
        "breakout_day": {
            "open": 130.0, "high": 135.0, "low": 129.0,
            "close": 134.0, "volume": 100_000_000,
        },
        "consolidation": {
            "consolidation_length_bars": 30,
            "consolidation_height_pct": None,
            "consolidation_position_vs_52w_high": None,
            "consolidation_volume_ratio": 0.55,
            "consolidation_tightness_atr": None,
        },
    }
    msg = build_user_message(meta)
    assert "N/A" in msg or "null" in msg or "unknown" in msg.lower()
```

- [ ] **Step 6.2: Run test to verify it fails**

Run: `uv run pytest BreakoutStrategy/feature_library/tests/test_prompts.py -v`
Expected: ImportError.

- [ ] **Step 6.3: Implement prompts.py**

`BreakoutStrategy/feature_library/prompts.py`:

```python
"""nl_description 生成所用 prompt 模板。

SYSTEM_PROMPT 定义 GLM-4V-Flash 的角色（K 线分析师）+ 输出规范
（结构化自然语言段落，不包含 JSON / markdown 代码块）。
build_user_message 把 meta dict 拼成"图像 + 上下文文本"的 user 消息。
"""

from typing import Any


SYSTEM_PROMPT = (
    "You are an expert technical analyst describing US stock K-line breakout charts. "
    "Given a chart image and quantitative context, write a precise, structured "
    "natural-language description (Chinese) that will be used as input to a downstream "
    "feature induction system.\n\n"
    "Required output structure (plain text, no markdown code blocks):\n"
    "1. 一段总览（突破前后的整体走势特征）\n"
    "2. 盘整阶段细节（形态 / 量能 / 紧致度，引用上下文中的数值）\n"
    "3. 突破日特征（K 线形态 / 量能跳变 / 与盘整边界的位置关系）\n"
    "4. 上下文中的隐含规律假说（不强制，可空）\n\n"
    "约束：\n"
    "- 不要输出 JSON / markdown 代码块 / 标题符号\n"
    "- 数值引用时保留 1-2 位小数\n"
    "- 字段为 N/A 时跳过该数值，不要编造\n"
    "- 篇幅 200~400 中文字符\n"
)


def build_user_message(meta: dict[str, Any]) -> str:
    """构造发送给 GLM-4V-Flash 的 user 文本（与图像同消息）。"""
    bo = meta["breakout_day"]
    consol = meta["consolidation"]

    def fmt(v) -> str:
        return f"{v:.2f}" if isinstance(v, (int, float)) else "N/A"

    return (
        f"标的：{meta['ticker']}\n"
        f"突破日：{meta['bo_date']}\n"
        f"突破日 OHLCV：open={fmt(bo['open'])} high={fmt(bo['high'])} "
        f"low={fmt(bo['low'])} close={fmt(bo['close'])} "
        f"volume={fmt(bo['volume'])}\n"
        f"\n盘整阶段量化字段：\n"
        f"- 持续时长（bars）：{fmt(consol['consolidation_length_bars'])}\n"
        f"- 高度百分比：{fmt(consol['consolidation_height_pct'])}%\n"
        f"- 距 52 周高点：{fmt(consol['consolidation_position_vs_52w_high'])}%\n"
        f"- 量能比（盘整 / 盘整前 60 bars）：{fmt(consol['consolidation_volume_ratio'])}\n"
        f"- 紧致度（高度 / ATR14）：{fmt(consol['consolidation_tightness_atr'])}\n"
        f"\n请按 SYSTEM_PROMPT 要求描述这张 K 线图。"
    )
```

- [ ] **Step 6.4: Run test to verify it passes**

Run: `uv run pytest BreakoutStrategy/feature_library/tests/test_prompts.py -v`
Expected: 3 passed.

- [ ] **Step 6.5: Commit**

```bash
git add BreakoutStrategy/feature_library/prompts.py \
        BreakoutStrategy/feature_library/tests/test_prompts.py
git commit -m "feat(feature_library): add nl_description prompts

SYSTEM_PROMPT 定义 GLM-4V-Flash 角色与输出结构；
build_user_message 拼装 meta 上下文，N/A 字段跳过。"
```

---

## Task 7: GLM-4V-Flash backend

**Files:**
- Create: `BreakoutStrategy/feature_library/glm4v_backend.py`
- Create: `BreakoutStrategy/feature_library/tests/test_glm4v_backend.py`

- [ ] **Step 7.1: Write the failing test**

`BreakoutStrategy/feature_library/tests/test_glm4v_backend.py`:

```python
"""Tests for GLM-4V-Flash multimodal backend."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from BreakoutStrategy.feature_library.glm4v_backend import GLM4VBackend


@pytest.fixture
def fake_chart(tmp_path) -> Path:
    p = tmp_path / "chart.png"
    p.write_bytes(b"fake-png-bytes-for-test")
    return p


def test_describe_chart_returns_string(fake_chart):
    backend = GLM4VBackend(api_key="test-key")
    fake_response = MagicMock()
    fake_response.choices = [MagicMock(message=MagicMock(
        content="这是一段 GLM-4V-Flash 返回的 K 线描述。",
        reasoning_content=None,
    ))]
    with patch.object(backend._client.chat.completions, "create",
                      return_value=fake_response) as mock_create:
        result = backend.describe_chart(
            chart_path=fake_chart,
            user_message="标的：AAPL\n突破日：2023-01-15",
        )

    assert result == "这是一段 GLM-4V-Flash 返回的 K 线描述。"
    mock_create.assert_called_once()
    call_kwargs = mock_create.call_args.kwargs
    assert call_kwargs["model"] == "glm-4v-flash"
    messages = call_kwargs["messages"]
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    user_content = messages[1]["content"]
    assert isinstance(user_content, list)
    assert any(c["type"] == "image_url" for c in user_content)
    assert any(c["type"] == "text" for c in user_content)


def test_describe_chart_image_is_base64_data_url(fake_chart):
    backend = GLM4VBackend(api_key="test-key")
    fake_response = MagicMock()
    fake_response.choices = [MagicMock(message=MagicMock(
        content="ok", reasoning_content=None,
    ))]
    with patch.object(backend._client.chat.completions, "create",
                      return_value=fake_response) as mock_create:
        backend.describe_chart(
            chart_path=fake_chart, user_message="ctx",
        )
    user_content = mock_create.call_args.kwargs["messages"][1]["content"]
    image_block = next(c for c in user_content if c["type"] == "image_url")
    url = image_block["image_url"]["url"]
    assert url.startswith("data:image/png;base64,")


def test_describe_chart_retries_once_on_exception(fake_chart):
    backend = GLM4VBackend(api_key="test-key")
    fake_ok = MagicMock()
    fake_ok.choices = [MagicMock(message=MagicMock(
        content="recovered", reasoning_content=None,
    ))]

    with patch.object(backend._client.chat.completions, "create",
                      side_effect=[Exception("transient"), fake_ok]) as mock_create:
        result = backend.describe_chart(
            chart_path=fake_chart, user_message="ctx",
        )
    assert result == "recovered"
    assert mock_create.call_count == 2


def test_describe_chart_returns_empty_after_two_failures(fake_chart):
    backend = GLM4VBackend(api_key="test-key")
    with patch.object(backend._client.chat.completions, "create",
                      side_effect=Exception("permanent")):
        result = backend.describe_chart(
            chart_path=fake_chart, user_message="ctx",
        )
    assert result == ""


def test_extract_content_falls_back_to_reasoning(fake_chart):
    """thinking 模式下 content 为空时应从 reasoning_content 回收。"""
    backend = GLM4VBackend(api_key="test-key")
    fake_response = MagicMock()
    fake_response.choices = [MagicMock(message=MagicMock(
        content="", reasoning_content="思考后输出：xxx 描述",
    ))]
    with patch.object(backend._client.chat.completions, "create",
                      return_value=fake_response):
        result = backend.describe_chart(
            chart_path=fake_chart, user_message="ctx",
        )
    assert "xxx 描述" in result
```

- [ ] **Step 7.2: Run test to verify it fails**

Run: `uv run pytest BreakoutStrategy/feature_library/tests/test_glm4v_backend.py -v`
Expected: ImportError.

- [ ] **Step 7.3: Implement glm4v_backend.py**

`BreakoutStrategy/feature_library/glm4v_backend.py`:

```python
"""GLM-4V-Flash 多模态后端 — 替代 spec 中的 Opus 多模态。

参考 BreakoutStrategy/news_sentiment/backends/glm_backend.py 的模式：
zhipuai SDK + 单次重试 + thinking 模式 reasoning_content 回收。
模型 ID 固定 glm-4v-flash（免费多模态）。

接口：describe_chart(chart_path, user_message) → str（纯文本描述）
"""

import base64
import logging
from pathlib import Path

from zhipuai import ZhipuAI

from BreakoutStrategy.feature_library.prompts import SYSTEM_PROMPT

logger = logging.getLogger(__name__)

GLM4V_MODEL_ID = "glm-4v-flash"
DEFAULT_TEMPERATURE = 0.3
MAX_RETRIES = 2


class GLM4VBackend:
    """GLM-4V-Flash 多模态调用封装。"""

    def __init__(self, api_key: str, temperature: float = DEFAULT_TEMPERATURE):
        if not api_key:
            raise ValueError("GLM4VBackend 需要非空 zhipuai api_key")
        self._client = ZhipuAI(api_key=api_key)
        self._temperature = temperature

    def describe_chart(self, chart_path: Path, user_message: str) -> str:
        """对单张 chart.png 调用 glm-4v-flash 生成自然语言描述。

        Args:
            chart_path: chart.png 的绝对路径
            user_message: 上下文 prompt（meta 字段 + 任务说明）

        Returns:
            模型生成的描述文本；失败时返回空字符串
        """
        image_data_url = _encode_image_as_data_url(chart_path)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": image_data_url}},
                {"type": "text", "text": user_message},
            ]},
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
                    logger.warning(f"[GLM4V] call failed: {e}, retrying...")
                    continue
                logger.error(f"[GLM4V] call failed after retry: {e}")

        return ""

    @staticmethod
    def _extract_content(response) -> str:
        msg = response.choices[0].message
        content = (msg.content or "").strip()
        if content:
            return content
        # thinking 模式回收
        reasoning = getattr(msg, "reasoning_content", "") or ""
        return reasoning.strip()


def _encode_image_as_data_url(chart_path: Path) -> str:
    """读取 PNG 文件，编码为 data: URL（zhipuai SDK 支持的图像传入格式）。"""
    raw = chart_path.read_bytes()
    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:image/png;base64,{b64}"
```

- [ ] **Step 7.4: Run test to verify it passes**

Run: `uv run pytest BreakoutStrategy/feature_library/tests/test_glm4v_backend.py -v`
Expected: 5 passed.

- [ ] **Step 7.5: Commit**

```bash
git add BreakoutStrategy/feature_library/glm4v_backend.py \
        BreakoutStrategy/feature_library/tests/test_glm4v_backend.py
git commit -m "feat(feature_library): add GLM-4V-Flash multimodal backend

替代 spec 中的 Opus 多模态。zhipuai SDK，模型 glm-4v-flash，
data URL 图像传入，单次重试，thinking 模式 reasoning_content 回收。"
```

---

## Task 8: Preprocess orchestrator

**Files:**
- Create: `BreakoutStrategy/feature_library/preprocess.py`
- Create: `BreakoutStrategy/feature_library/tests/test_preprocess.py`

- [ ] **Step 8.1: Write the failing test**

`BreakoutStrategy/feature_library/tests/test_preprocess.py`:

```python
"""Tests for preprocess orchestrator (chart + meta + nl_description)."""
from datetime import datetime
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

from BreakoutStrategy.feature_library.preprocess import preprocess_sample


@pytest.fixture
def synthetic_df():
    n = 300
    dates = pd.date_range("2023-01-01", periods=n, freq="B")
    rng = np.random.default_rng(seed=42)
    closes = rng.uniform(20, 35, n)
    return pd.DataFrame({
        "Open": closes, "High": closes * 1.02, "Low": closes * 0.98,
        "Close": closes, "Volume": rng.uniform(500_000, 1_500_000, n),
    }, index=dates)


def test_preprocess_creates_three_artifacts(tmp_path, synthetic_df, monkeypatch):
    from BreakoutStrategy.feature_library import paths
    monkeypatch.setattr(paths, "FEATURE_LIBRARY_ROOT", tmp_path / "feature_library")
    monkeypatch.setattr(paths, "SAMPLES_DIR", paths.FEATURE_LIBRARY_ROOT / "samples")

    fake_backend = MagicMock()
    fake_backend.describe_chart.return_value = "GLM-4V 返回的描述文本"

    sample_id = preprocess_sample(
        ticker="AAPL",
        bo_date=pd.Timestamp("2024-03-01"),
        df_window=synthetic_df,
        bo_index=290,
        pk_index=260,
        picked_at=datetime(2026, 4, 27, 10, 30),
        backend=fake_backend,
    )

    assert sample_id == "BO_AAPL_20240301"
    assert paths.chart_png_path(sample_id).exists()
    assert paths.meta_yaml_path(sample_id).exists()
    nl_path = paths.nl_description_path(sample_id)
    assert nl_path.exists()
    assert nl_path.read_text().strip() == "GLM-4V 返回的描述文本"


def test_preprocess_calls_backend_with_chart_and_message(tmp_path, synthetic_df, monkeypatch):
    from BreakoutStrategy.feature_library import paths
    monkeypatch.setattr(paths, "FEATURE_LIBRARY_ROOT", tmp_path / "feature_library")
    monkeypatch.setattr(paths, "SAMPLES_DIR", paths.FEATURE_LIBRARY_ROOT / "samples")

    fake_backend = MagicMock()
    fake_backend.describe_chart.return_value = "ok"

    preprocess_sample(
        ticker="AAPL",
        bo_date=pd.Timestamp("2024-03-01"),
        df_window=synthetic_df,
        bo_index=290,
        pk_index=260,
        picked_at=datetime(2026, 4, 27, 10, 30),
        backend=fake_backend,
    )

    fake_backend.describe_chart.assert_called_once()
    call_kwargs = fake_backend.describe_chart.call_args.kwargs
    assert call_kwargs["chart_path"] == paths.chart_png_path("BO_AAPL_20240301")
    assert "AAPL" in call_kwargs["user_message"]
    assert "2024-03-01" in call_kwargs["user_message"]


def test_preprocess_skips_nl_when_backend_returns_empty(tmp_path, synthetic_df, monkeypatch):
    """backend 返回空字符串（GLM call 失败）时，仍写 chart + meta，但 nl_description.md 含 fallback 标记。"""
    from BreakoutStrategy.feature_library import paths
    monkeypatch.setattr(paths, "FEATURE_LIBRARY_ROOT", tmp_path / "feature_library")
    monkeypatch.setattr(paths, "SAMPLES_DIR", paths.FEATURE_LIBRARY_ROOT / "samples")

    fake_backend = MagicMock()
    fake_backend.describe_chart.return_value = ""

    sample_id = preprocess_sample(
        ticker="AAPL",
        bo_date=pd.Timestamp("2024-03-01"),
        df_window=synthetic_df,
        bo_index=290,
        pk_index=260,
        picked_at=datetime(2026, 4, 27, 10, 30),
        backend=fake_backend,
    )

    nl_text = paths.nl_description_path(sample_id).read_text()
    assert "PREPROCESS_FAILED" in nl_text
```

- [ ] **Step 8.2: Run test to verify it fails**

Run: `uv run pytest BreakoutStrategy/feature_library/tests/test_preprocess.py -v`
Expected: ImportError.

- [ ] **Step 8.3: Implement preprocess.py**

`BreakoutStrategy/feature_library/preprocess.py`:

```python
"""单样本预处理 — Phase 0 vertical slice 入口。

输入：(ticker, bo_date, df_window, bo_index, pk_index, picked_at, backend)
输出：sample_id（已落盘 chart.png + meta.yaml + nl_description.md）

调用顺序：
1. 生成 sample_id
2. 渲染 chart.png
3. 构建 meta dict + 写 meta.yaml
4. 调 backend.describe_chart → 写 nl_description.md
   （backend 返回空字符串时写 PREPROCESS_FAILED 标记，不抛异常）
"""

from datetime import datetime
from typing import Protocol

import pandas as pd

from BreakoutStrategy.feature_library import paths
from BreakoutStrategy.feature_library.prompts import build_user_message
from BreakoutStrategy.feature_library.sample_id import generate_sample_id
from BreakoutStrategy.feature_library.sample_meta import build_meta, write_meta_yaml
from BreakoutStrategy.feature_library.sample_renderer import render_sample_chart


class _MultimodalBackend(Protocol):
    def describe_chart(self, *, chart_path, user_message: str) -> str: ...


PREPROCESS_FAILED_MARKER = (
    "PREPROCESS_FAILED: backend returned empty response. "
    "请检查 GLM-4V-Flash API key / 网络连接 / 配额，重新运行 preprocess。"
)


def preprocess_sample(
    *,
    ticker: str,
    bo_date: pd.Timestamp,
    df_window: pd.DataFrame,
    bo_index: int,
    pk_index: int,
    picked_at: datetime,
    backend: _MultimodalBackend,
) -> str:
    """完整预处理一个 breakout 样本，返回 sample_id。"""
    sample_id = generate_sample_id(ticker=ticker, bo_date=bo_date)

    # 1. 渲染图（先于 meta，便于 backend 立即可用）
    chart_path = render_sample_chart(
        sample_id=sample_id,
        df_window=df_window,
        bo_index=bo_index,
        pk_index=pk_index,
    )

    # 2. 构建 meta
    meta = build_meta(
        sample_id=sample_id,
        ticker=ticker.upper(),
        bo_date=bo_date,
        df_window=df_window,
        bo_index=bo_index,
        pk_index=pk_index,
        picked_at=picked_at,
    )
    write_meta_yaml(sample_id, meta)

    # 3. 调 backend 生成 nl_description
    user_msg = build_user_message(meta)
    nl_text = backend.describe_chart(
        chart_path=chart_path, user_message=user_msg,
    )

    # 4. 写 nl_description.md（失败时写 fallback 标记）
    nl_path = paths.nl_description_path(sample_id)
    nl_path.write_text(nl_text if nl_text else PREPROCESS_FAILED_MARKER)

    return sample_id
```

- [ ] **Step 8.4: Run test to verify it passes**

Run: `uv run pytest BreakoutStrategy/feature_library/tests/test_preprocess.py -v`
Expected: 3 passed.

- [ ] **Step 8.5: Commit**

```bash
git add BreakoutStrategy/feature_library/preprocess.py \
        BreakoutStrategy/feature_library/tests/test_preprocess.py
git commit -m "feat(feature_library): add preprocess orchestrator (vertical slice)

输入 breakout 上下文 + backend，串联 render_chart →
build_meta → write_meta_yaml → backend.describe_chart →
write nl_description.md。空响应写 PREPROCESS_FAILED 标记。"
```

---

## Task 9: Entry script

**Files:**
- Create: `scripts/feature_mining_phase0.py`

- [ ] **Step 9.1: Write the entry script**

`scripts/feature_mining_phase0.py`:

```python
"""Phase 0 vertical slice 入口脚本。

运行方式：
    uv run python scripts/feature_mining_phase0.py

参数全部在 main() 起始位置声明（CLAUDE.md 要求，不用 argparse）。
默认从 datasets/pkls/ 加载指定 ticker，调用 BreakoutDetector 找到第一个
满足条件的 breakout，做单样本 preprocess。

依赖 GLM-4V-Flash 真实 API 调用（zhipuai key from configs/api_keys.yaml）。
"""

from datetime import datetime
from pathlib import Path

import pandas as pd
import yaml

from BreakoutStrategy.analysis.breakout_detector import BreakoutDetector
from BreakoutStrategy.feature_library import paths
from BreakoutStrategy.feature_library.glm4v_backend import GLM4VBackend
from BreakoutStrategy.feature_library.preprocess import preprocess_sample


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_zhipuai_key() -> str:
    cfg_path = REPO_ROOT / "configs" / "api_keys.yaml"
    keys = yaml.safe_load(cfg_path.read_text())
    api_key = keys.get("zhipuai", "")
    if not api_key:
        raise RuntimeError(
            f"configs/api_keys.yaml 中 zhipuai key 为空，请填写后重试"
        )
    return api_key


def _load_pkl(ticker: str) -> pd.DataFrame:
    pkl_path = REPO_ROOT / "datasets" / "pkls" / f"{ticker}.pkl"
    if not pkl_path.exists():
        raise FileNotFoundError(f"未找到 {pkl_path}")
    return pd.read_pickle(pkl_path)


def main() -> None:
    # ---------------- 参数声明区 ----------------
    ticker: str = "AAPL"                          # 目标股票
    sample_count: int = 1                         # 处理几个 breakout
    breakout_detector_config: dict = {}           # 默认参数即可
    # -------------------------------------------

    print(f"[Phase 0] 加载 {ticker} 历史数据...")
    df = _load_pkl(ticker)
    print(f"[Phase 0] 数据范围 {df.index[0].date()} ~ {df.index[-1].date()}, {len(df)} bars")

    print(f"[Phase 0] 检测 breakouts...")
    detector = BreakoutDetector(config=breakout_detector_config)
    breakouts = detector.detect(df)
    print(f"[Phase 0] 检测到 {len(breakouts)} 个 breakouts，取前 {sample_count} 个")

    if not breakouts:
        print(f"[Phase 0] 无 breakout，退出")
        return

    print(f"[Phase 0] 加载 zhipuai API key...")
    api_key = _load_zhipuai_key()
    backend = GLM4VBackend(api_key=api_key)

    targets = breakouts[:sample_count]
    for i, bo in enumerate(targets, start=1):
        print(f"\n[Phase 0] [{i}/{len(targets)}] 处理 BO bo_index={bo.bo_index} ...")
        sample_id = preprocess_sample(
            ticker=ticker,
            bo_date=df.index[bo.bo_index],
            df_window=df.iloc[max(0, bo.bo_index - 200): bo.bo_index + 1],
            bo_index=min(bo.bo_index, 200),
            pk_index=min(bo.pk_index, 200) if bo.pk_index is not None else 0,
            picked_at=datetime.now(),
            backend=backend,
        )
        print(f"[Phase 0] 完成 sample_id={sample_id}")
        print(f"[Phase 0]   chart.png: {paths.chart_png_path(sample_id)}")
        print(f"[Phase 0]   meta.yaml: {paths.meta_yaml_path(sample_id)}")
        print(f"[Phase 0]   nl_description.md: {paths.nl_description_path(sample_id)}")
        print(f"[Phase 0]   nl_description 摘录: "
              f"{paths.nl_description_path(sample_id).read_text()[:120]}...")


if __name__ == "__main__":
    main()
```

- [ ] **Step 9.2: Smoke test the entry script**

Run: `uv run python scripts/feature_mining_phase0.py`
Expected: 输出形如：

```
[Phase 0] 加载 AAPL 历史数据...
[Phase 0] 数据范围 ... ~ ..., NNNN bars
[Phase 0] 检测 breakouts...
[Phase 0] 检测到 N 个 breakouts，取前 1 个
[Phase 0] 加载 zhipuai API key...
[Phase 0] [1/1] 处理 BO bo_index=...
[Phase 0] 完成 sample_id=BO_AAPL_<YYYYMMDD>
[Phase 0]   chart.png: /home/yu/PycharmProjects/Trade_Strategy/feature_library/samples/BO_AAPL_<YYYYMMDD>/chart.png
[Phase 0]   meta.yaml: ...
[Phase 0]   nl_description.md: ...
[Phase 0]   nl_description 摘录: ...
```

验证以下事实：
- 三个文件均生成且非空
- chart.png 用图片查看器打开是合理的 K 线图（含 pk/bo 垂直线）
- meta.yaml 含 5 个 consolidation 字段
- nl_description.md 是中文描述，**不**是 PREPROCESS_FAILED 标记（说明 GLM-4V-Flash 真实调通）

如 nl_description.md 是 PREPROCESS_FAILED：
- 检查 zhipuai key 有效性（手动用 curl 调一次 glm-4v-flash）
- 检查网络可达 https://open.bigmodel.cn/

- [ ] **Step 9.3: Verify BreakoutDetector signature compatibility**

如 Step 9.2 报错 `BreakoutDetector(config=...)` 签名不符（检测器接口可能有差异），按照实际签名调整 entry script，并在 commit message 中记录调整。

参考检测器构造方式应从 `BreakoutStrategy/analysis/breakout_detector.py` 顶部的 class 定义直接读取。

- [ ] **Step 9.4: Commit**

```bash
git add scripts/feature_mining_phase0.py
git commit -m "feat(feature_library): add Phase 0 entry script

uv run python scripts/feature_mining_phase0.py 跑通端到端：
PKL → BreakoutDetector → preprocess_sample → samples/<id>/{chart.png,meta.yaml,nl_description.md}。
参数声明在 main() 起始（CLAUDE.md 要求）。"
```

---

## Task 10: Phase 0 结尾验证 + 文档

**Files:**
- Modify: `.claude/docs/system_outline.md` （新模块入口加一行）

- [ ] **Step 10.1: 跑全套测试**

Run: `uv run pytest BreakoutStrategy/feature_library/tests/ -v`
Expected: 22+ tests passed (paths 5 + sample_id 4 + consolidation_fields 5 + sample_meta 4 + sample_renderer 2 + prompts 3 + glm4v_backend 5 + preprocess 3 = 31 项).

- [ ] **Step 10.2: 验证 vertical slice 完整产出**

```bash
ls -la feature_library/samples/BO_AAPL_*/
```

预期看到 chart.png + meta.yaml + nl_description.md 三个文件。

- [ ] **Step 10.3: 在 .claude/docs/system_outline.md 中追加模块入口（一行）**

参考 `.claude/docs/system_outline.md` 现有"已实现模块"区块，追加：

```
- BreakoutStrategy/feature_library/ — Phase 0 数据基线（sample 预处理：chart.png + meta.yaml + nl_description.md via GLM-4V-Flash）
```

- [ ] **Step 10.4: Final commit**

```bash
git add .claude/docs/system_outline.md
git commit -m "docs: register feature_library module in system outline (Phase 0)"
```

- [ ] **Step 10.5: Phase 0 完成宣告**

确认以下 acceptance criteria 全部满足：

| # | 验收项 | 通过判据 |
|---|---|---|
| AC1 | 包结构完整 | `BreakoutStrategy/feature_library/` 含 8 个 Python 模块（不计 tests）|
| AC2 | 单元测试全过 | `uv run pytest BreakoutStrategy/feature_library/tests/ -v` 全部 PASS |
| AC3 | 端到端 vertical slice 跑通 | `uv run python scripts/feature_mining_phase0.py` 真实生成 3 件套 |
| AC4 | nl_description 由 GLM-4V-Flash 真实生成 | nl_description.md 内容是中文描述，**非** PREPROCESS_FAILED |
| AC5 | meta.yaml 含 5 个 consolidation 字段 | `yq '.consolidation | keys' feature_library/samples/.../meta.yaml` 含 5 项 |
| AC6 | chart.png 含 pk/bo 标注 | 视觉检查 |
| AC7 | runtime data 不进 git | `git status` 不显示 `feature_library/` 下文件 |
| AC8 | 入口脚本无 argparse | 检查 `scripts/feature_mining_phase0.py` 用 main() 顶部参数声明 |

全部通过后可进入 Phase 1（Librarian + Inducer MVP）。

---

## Phase 0 → Phase 1 衔接说明

Phase 0 产出的 `feature_library/samples/<id>/` 三件套是 Phase 1 的输入。Phase 1 将引入：

- `BreakoutStrategy/feature_library/librarian.py` — Beta-Binomial (α, β) 累积 + ObservationLog
- `BreakoutStrategy/feature_library/inducer.py` — Inducer batch 模式调用（用 GLM-4V-Flash 替代 Opus，多图对比）
- `BreakoutStrategy/feature_library/observation_log.py` — 按 (sample, feature) 粒度的事件日志
- `feature_library/features/<id>.yaml` 文件 schema 实现

Phase 1 不在本计划范围；待 Phase 0 闭环验证后另起 plan。
