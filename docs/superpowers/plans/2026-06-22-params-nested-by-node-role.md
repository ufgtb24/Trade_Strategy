# Params Nested-by-Node-Role 改造 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `path2_apps/bottom_breakout_burst` 的 `Params` 从 flat dataclass + flat yaml 改造为 nested by node role(4 子 dataclass / 4 yaml section: bo/burst/tb/edges),让 yaml 视觉分组按角色清晰、彻底消除"顶层判定"section 错位 + 大小写命名混用 + 死字段(`burst_min_bos`/`burst_vol_ratio_spike_thr`)的三重 smell。

**Architecture:** Nested-by-role schema(tom 从第一性原理裁定):每个 NodeSpec 角色(bo/burst/tb)拥有自己的 sub-dataclass + yaml section,内含 detector 构造参数 + where 阈值。共用字段(`tb.max_start_gap` 同时被 ThrowbackDetector 与 burst→tb edge 复用)采"语义归宿 = 谁定义"原则归入 tb section、edge 在代码里显式引用(SSoT 单一定义)。edges section 保留为空 dataclass(`EdgesParams`)作为格式契约/未来扩展占位。生产代码所有 `params.<field>` 引用改为 `params.<section>.<field>` 路径。

**Tech Stack:** Python 3.12 + frozen dataclass + PyYAML + pytest + uv

## Global Constraints

- 包管理:`uv add` / `uv run` / `uv sync`,所有命令前缀 `uv run`
- 入口脚本不用 argparse,参数声明在 `main()` 顶部(项目纪律,本 plan 无新建入口)
- 注释/文档中文;界面/标识符英文
- 测试用 pytest;`uv run pytest tests/path2 tests/path2_apps tests/path2_web -q` 是回归命令
- pre-existing 失败 `tests/path2/atoms/test_throwback.py::test_evaluate_anchor_measure_close` 与本 plan 无关,可忽略
- 单 session 无监管跑完;每 task 完成立即 commit
- yaml 文件路径 = `path2_apps/bottom_breakout_burst/params.yaml`
- params 文件路径 = `path2_apps/bottom_breakout_burst/params.py`
- 已有的 `load_params()` / `DEFAULT_YAML_PATH` 协议保留(web 入口热加载靠它),`from_yaml` 的"未知 key ValueError 护栏"语义保留并递归到每个子 section

## 设计契约速查(必读)

**4 子 dataclass:**

| Dataclass | 字段(全小写 snake_case) |
|---|---|
| `BoParams` | `total_window`, `min_side_bars`, `min_relative_height`, `exceed_threshold`, `peak_supersede_threshold`, `vol_baseline_period`, `peak_measure`, `breakout_measure` |
| `BurstParams` | `gap_max`, `vol_baseline_period`, `min_bos`, `first_drought_min`, `distinct_pk_min`, `vol_spike_min` |
| `TbParams` | `max_start_gap`, `max_window`, `atr_window`, `big_rise_k`, `pullback_min_atr`, `anchor_measure`, `support_measure` |
| `EdgesParams` | (空,作格式契约占位) |

**命名迁移表(旧 → 新):**

```
bo_total_window              → bo.total_window
bo_min_side_bars             → bo.min_side_bars
bo_min_relative_height       → bo.min_relative_height
bo_exceed_threshold          → bo.exceed_threshold
bo_peak_supersede_threshold  → bo.peak_supersede_threshold
bo_vol_baseline_period       → bo.vol_baseline_period
bo_peak_measure              → bo.peak_measure
bo_breakout_measure          → bo.breakout_measure

burst_gap_max                → burst.gap_max
burst_vol_baseline_period    → burst.vol_baseline_period
MIN_BOS                      → burst.min_bos      (大写改小写,同时消除"顶层判定"section)
THR_DROUGHT                  → burst.first_drought_min   (语义化小写)
THR_PK                       → burst.distinct_pk_min
THR_VOL                      → burst.vol_spike_min
burst_min_bos                → 删除(死字段:被 MIN_BOS 覆盖,生产 0 读者)
burst_vol_ratio_spike_thr    → 删除(死字段:没人读)

throwback_max_start_gap      → tb.max_start_gap   (注意:detector 与 edge 共用,见下)
throwback_max_window         → tb.max_window
throwback_atr_window         → tb.atr_window
throwback_big_rise_k         → tb.big_rise_k
throwback_pullback_min_atr   → tb.pullback_min_atr
throwback_anchor_measure     → tb.anchor_measure
throwback_support_measure    → tb.support_measure
```

**共用字段处置:** `tb.max_start_gap` 同时被 ThrowbackDetector 构造与 burst→tb TemporalEdge 复用。dag_spec.py 内 edge 写法保持 `max_gap=params.tb.max_start_gap`,显式引用 tb section(SSoT),不复制。

**保留协议:** `Params.default()`、`Params.from_yaml(path)`、`load_params()` 函数、`DEFAULT_YAML_PATH` 模块常量、`bo_kwargs()/burst_kwargs()/throwback_kwargs()` 切片函数对外签名不变(返回 dict 给 detector 构造)。`from_yaml` 内部要递归到每个子 section 都校验"未知 key 报错"。

**eval_runner param_overrides:** 当前是 flat dict(如 `{"bo_min_relative_height": 0.02, "MIN_BOS": 2}`),改造为 nested dict(如 `{"bo": {"min_relative_height": 0.02}, "burst": {"min_bos": 2}}`)。worker 内对每个 section 做 `replace(getattr(base, sect), **sect_overrides)`,再 `replace(base, **section_kwargs)` 合并。

---

### Task 1: Refactor params.py to nested 4-dataclass schema

**Files:**
- Modify: `path2_apps/bottom_breakout_burst/params.py`(整体重写)
- Test: `tests/path2/apps/test_params.py`(整体重写)

**Interfaces:**
- Produces:
  - `BoParams`/`BurstParams`/`TbParams`/`EdgesParams` 子 dataclass(frozen)
  - `Params(bo, burst, tb, edges)` 嵌套容器(frozen)
  - `Params.default() -> Params` 返回全默认实例
  - `Params.from_yaml(path) -> Params` 递归加载,任一 section 未知 key 抛 ValueError
  - `load_params() -> Params` 读 `DEFAULT_YAML_PATH`(模块常量,值不变)
  - `Params.bo_kwargs() -> dict`(返回 `asdict(self.bo)`,字段名一一对应 BODetector 签名)
  - `Params.burst_kwargs() -> dict`(返回 `{"gap_max":..., "min_bos":..., "vol_baseline_period":...}`,BurstDetector 签名)
  - `Params.throwback_kwargs() -> dict`(返回 `asdict(self.tb)`,ThrowbackDetector 签名)
- 测试 fixture 用 `Params(bo=BoParams(total_window=20), burst=BurstParams(...), ...)` 嵌套构造;**section 内字段缺省 → 子 dataclass field default 兜底**

- [ ] **Step 1: Write the failing tests**

文件 `tests/path2/apps/test_params.py`:

```python
import os
import tempfile

import pytest

from path2_apps.bottom_breakout_burst.params import (
    Params, BoParams, BurstParams, TbParams, EdgesParams, load_params, DEFAULT_YAML_PATH,
)


def test_default_returns_nested_instances():
    p = Params.default()
    assert isinstance(p.bo, BoParams)
    assert isinstance(p.burst, BurstParams)
    assert isinstance(p.tb, TbParams)
    assert isinstance(p.edges, EdgesParams)


def test_default_bo_defaults():
    bo = Params.default().bo
    assert bo.total_window == 10
    assert bo.min_side_bars == 2
    assert bo.min_relative_height == 0.05
    assert bo.exceed_threshold == 0.005
    assert bo.peak_supersede_threshold == 0.03
    assert bo.vol_baseline_period == 63
    assert bo.peak_measure == "high"
    assert bo.breakout_measure == "high"


def test_default_burst_defaults():
    burst = Params.default().burst
    assert burst.gap_max == 5
    assert burst.vol_baseline_period == 63
    assert burst.min_bos == 2
    assert burst.first_drought_min == 20
    assert burst.distinct_pk_min == 4
    assert burst.vol_spike_min == 8.0


def test_default_tb_defaults():
    tb = Params.default().tb
    assert tb.max_start_gap == 5
    assert tb.max_window == 5
    assert tb.atr_window == 14
    assert tb.big_rise_k == 1.5
    assert tb.pullback_min_atr == 1.0
    assert tb.anchor_measure == "high"
    assert tb.support_measure == "low"


def test_params_frozen_top_and_nested():
    p = Params.default()
    with pytest.raises(Exception):
        p.bo = BoParams()
    with pytest.raises(Exception):
        p.bo.total_window = 99


def test_kwargs_slices_against_detector_signatures():
    """bo_kwargs/burst_kwargs/throwback_kwargs 返回与各 detector __init__ 一一对应的 dict。"""
    p = Params.default()
    bo = p.bo_kwargs()
    assert set(bo) == {'total_window', 'min_side_bars', 'min_relative_height',
                       'exceed_threshold', 'peak_supersede_threshold',
                       'vol_baseline_period', 'peak_measure', 'breakout_measure'}
    assert bo['total_window'] == 10
    burst = p.burst_kwargs()
    assert set(burst) == {'gap_max', 'min_bos', 'vol_baseline_period'}, (
        "burst_kwargs() 必须精确匹配 BurstDetector 签名;阈值走 where 不进 detector"
    )
    assert burst['min_bos'] == 2 and burst['gap_max'] == 5
    tb = p.throwback_kwargs()
    assert set(tb) == {'max_start_gap', 'max_window', 'atr_window',
                       'big_rise_k', 'pullback_min_atr',
                       'anchor_measure', 'support_measure'}


def test_from_yaml_partial_override_at_section_level():
    """yaml 局部 section + section 内局部字段 → 缺失字段用子 dataclass default 兜底。"""
    yaml_text = """
burst:
  first_drought_min: 80
  gap_max: 8
"""
    with tempfile.NamedTemporaryFile('w', suffix='.yaml', delete=False) as f:
        f.write(yaml_text)
        path = f.name
    try:
        p = Params.from_yaml(path)
        assert p.burst.first_drought_min == 80   # yaml 覆盖
        assert p.burst.gap_max == 8              # yaml 覆盖
        assert p.burst.min_bos == 2              # yaml 未提及,用 default
        assert p.bo.total_window == 10           # 整 bo section 缺失,用 default
        assert p.tb.max_start_gap == 5           # 整 tb section 缺失,用 default
    finally:
        os.unlink(path)


def test_from_yaml_rejects_unknown_top_section():
    """yaml 顶层含未知 section → ValueError。"""
    yaml_text = """
bo: { total_window: 20 }
typoooo: { foo: 1 }
"""
    with tempfile.NamedTemporaryFile('w', suffix='.yaml', delete=False) as f:
        f.write(yaml_text)
        path = f.name
    try:
        with pytest.raises(ValueError, match="typoooo"):
            Params.from_yaml(path)
    finally:
        os.unlink(path)


def test_from_yaml_rejects_unknown_section_field():
    """yaml section 内含未知字段 → ValueError(嵌套校验,堵 yaml 弱类型静默无效陷阱)。"""
    yaml_text = """
burst:
  first_drought_min: 30
  bo_typooo: 99
"""
    with tempfile.NamedTemporaryFile('w', suffix='.yaml', delete=False) as f:
        f.write(yaml_text)
        path = f.name
    try:
        with pytest.raises(ValueError, match="bo_typooo"):
            Params.from_yaml(path)
    finally:
        os.unlink(path)


def test_load_params_reads_default_yaml_path():
    """load_params() 真去读 DEFAULT_YAML_PATH (app 同目录 params.yaml)。
    端到端 wiring 测试,防 path 计算错(__file__/相对路径)在重构中断裂。"""
    assert DEFAULT_YAML_PATH.exists(), f"app 目录下应有 params.yaml: {DEFAULT_YAML_PATH}"
    p = load_params()
    assert isinstance(p, Params)
    # yaml 现役为 V3.3 B 方案严值;dataclass default 是宽松值。两者必须分叉,
    # 否则证明 load_params 没真去读 yaml。
    assert p.bo.total_window != Params.default().bo.total_window, (
        "load_params() 读到的 bo.total_window 与 dataclass default 相同;"
        "yaml 应是 V3.3 B 方案严值与 dataclass 宽松默认不同,二者相等暗示 yaml 未真读"
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/path2/apps/test_params.py -v`
Expected: ALL tests FAIL with `ImportError: cannot import name 'BoParams'` 或类似,因为 nested dataclass 还没建。

- [ ] **Step 3: Write the new params.py**

完全重写 `path2_apps/bottom_breakout_burst/params.py`:

```python
"""Default Params for bottom_breakout_burst pattern (nested by node role)。

三件套分工:
- `params.yaml`:web 入口(scan/api/eval_runner)的 SSoT,改完下一次 /scan 即生效(热加载)。
- `Params` + 子 dataclass(BoParams/BurstParams/TbParams/EdgesParams):schema 层
  (字段名/类型),默认值是"yaml 缺失字段时兜底 + CLI 脚本 / tests fixture 默认"。
- `Params.from_yaml`/`load_params`:web 入口统一加载入口,逐 section 校验未知 key。

设计:每个 NodeSpec 角色(bo/burst/tb)拥有自己的子 dataclass + yaml section,
内含 detector 构造参数 + where 阈值。共用字段(tb.max_start_gap 同时被 ThrowbackDetector
和 burst→tb edge 复用)归入 tb section、edge 显式引用(SSoT)。edges 子 dataclass 留空
作格式契约/未来扩展占位。
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Type

DEFAULT_YAML_PATH = Path(__file__).parent / "params.yaml"


@dataclass(frozen=True)
class BoParams:
    """BODetector 构造参数。"""
    total_window: int = 10
    min_side_bars: int = 2
    min_relative_height: float = 0.05
    exceed_threshold: float = 0.005
    peak_supersede_threshold: float = 0.03
    vol_baseline_period: int = 63
    peak_measure: str = "high"
    breakout_measure: str = "high"


@dataclass(frozen=True)
class BurstParams:
    """BurstDetector 构造参数(gap_max/min_bos/vol_baseline_period) +
    burst node 的 where 阈值(first_drought_min/distinct_pk_min/vol_spike_min)。

    隐含约束:first_drought_min 必须 > gap_max,否则 first_drought where 退化恒真
    (chain 簇首必是断点,drought > gap_max 结构性必然)。默认 20 > 5 健康。
    """
    gap_max: int = 5
    vol_baseline_period: int = 63
    min_bos: int = 2                # BurstDetector 切串长度 + 业务约束②
    first_drought_min: int = 20     # burst where 阈值(原 THR_DROUGHT)
    distinct_pk_min: int = 4        # burst where 阈值(原 THR_PK)
    vol_spike_min: float = 8.0      # burst where 阈值(原 THR_VOL)


@dataclass(frozen=True)
class TbParams:
    """ThrowbackDetector 构造参数。注意 max_start_gap 同时被 burst→tb edge 复用
    (语义同步:detector 启动窗紧 vs edge gap 宽 = 矛盾,故单一定义于 tb)。"""
    max_start_gap: int = 5    # tb.start − bo.end ≤ 此值(买点不离 bo 过远);edge 也用
    max_window: int = 5       # tb.end − tb.start ≤ 此值(买点窗不持续过长)
    atr_window: int = 14      # ATR 回溯窗(取 bo−1 处值)
    big_rise_k: float = 1.5
    pullback_min_atr: float = 1.0
    anchor_measure: str = "high"   # anchor 取值口径(calc.measure)
    support_measure: str = "low"   # 破位比较口径(calc.measure)


@dataclass(frozen=True)
class EdgesParams:
    """edge-内禀参数容器。当前为空:所有 edge 字段或硬编码(min_gap=1/anchor_field/
    Child(...))或从 node section 引用(max_gap = tb.max_start_gap)。保留作格式契约
    + 未来 edge-only 参数扩展占位。"""
    pass


@dataclass(frozen=True)
class Params:
    """nested by node role:bo/burst/tb/edges 四 section 各自一个子 dataclass。"""
    bo: BoParams = field(default_factory=BoParams)
    burst: BurstParams = field(default_factory=BurstParams)
    tb: TbParams = field(default_factory=TbParams)
    edges: EdgesParams = field(default_factory=EdgesParams)

    @classmethod
    def default(cls) -> "Params":
        return cls()

    @classmethod
    def from_yaml(cls, path) -> "Params":
        """从 yaml 加载;顶层 + 每个 section 都校验未知 key(嵌套堵 yaml 拼错静默无效陷阱)。
        缺失 section / 缺失字段 → 用子 dataclass field default 兜底。"""
        import yaml
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        # 顶层未知 section 校验
        known_sections = {f.name for f in cls.__dataclass_fields__.values()}
        unknown_top = set(data) - known_sections
        if unknown_top:
            raise ValueError(
                f"params.yaml ({path}) 含未知顶层 section: {sorted(unknown_top)} "
                f"(已知 section: {sorted(known_sections)})"
            )
        section_classes: dict[str, Type] = {
            "bo": BoParams, "burst": BurstParams, "tb": TbParams, "edges": EdgesParams,
        }
        section_instances = {}
        for sect_name, sect_cls in section_classes.items():
            sect_data = data.get(sect_name) or {}
            sect_fields = {f.name for f in sect_cls.__dataclass_fields__.values()}
            unknown_fields = set(sect_data) - sect_fields
            if unknown_fields:
                raise ValueError(
                    f"params.yaml ({path}) section '{sect_name}' 含未知字段: "
                    f"{sorted(unknown_fields)} (可能拼错或字段已删;已知字段集见 {sect_cls.__name__})"
                )
            section_instances[sect_name] = sect_cls(**sect_data)
        return cls(**section_instances)

    def bo_kwargs(self) -> dict:
        """BODetector 构造参数(字段一一对应签名)。"""
        return asdict(self.bo)

    def burst_kwargs(self) -> dict:
        """BurstDetector 构造参数(切串参数:gap_max/min_bos/vol_baseline_period)。
        阈值走 burst node 的 where,不传给 detector。"""
        return {
            'gap_max': self.burst.gap_max,
            'min_bos': self.burst.min_bos,
            'vol_baseline_period': self.burst.vol_baseline_period,
        }

    def throwback_kwargs(self) -> dict:
        """ThrowbackDetector 构造参数(字段一一对应签名)。"""
        return asdict(self.tb)


def load_params() -> Params:
    """web 入口统一加载点:读 DEFAULT_YAML_PATH 的 yaml 作 Params(SSoT,热加载)。
    每次调用都重新读 yaml 文件,故 web /scan 每次请求都见最新 yaml(无需重启)。"""
    return Params.from_yaml(DEFAULT_YAML_PATH)
```

- [ ] **Step 4: Run tests to verify pass (params 部分; yaml 还没改成 nested 故 load_params 会失败,这是预期)**

Run: `uv run pytest tests/path2/apps/test_params.py -v -k 'not load_params'`
Expected: 7 PASS (test_load_params_reads_default_yaml_path 留到 Task 2 修 yaml 后才能过)

Run: `uv run pytest tests/path2/apps/test_params.py::test_load_params_reads_default_yaml_path -v`
Expected: 此测试 FAIL 因为 yaml 还是 flat 格式,from_yaml 校验"未知顶层 section: bo_total_window 等"。这正常,Task 2 修。

- [ ] **Step 5: Commit**

```bash
git add path2_apps/bottom_breakout_burst/params.py tests/path2/apps/test_params.py
git commit -m "path2_apps/params: 重构为 nested by node role 4 子 dataclass

BoParams/BurstParams/TbParams/EdgesParams 4 子 dataclass;Params 持有
+ from_yaml 递归校验未知 key(顶层 section + 每 section 字段两层)。

字段命名迁移(tom 第一性原理裁定):
- MIN_BOS → burst.min_bos(消除\"顶层判定\"section 错位)
- THR_DROUGHT → burst.first_drought_min(语义化小写,与 where 子句同根)
- THR_PK → burst.distinct_pk_min
- THR_VOL → burst.vol_spike_min
- bo_*/throwback_* 全部去前缀进 BoParams/TbParams

死字段删除:burst_min_bos(被 MIN_BOS 覆盖)、burst_vol_ratio_spike_thr(没人读)。

共用字段(throwback_max_start_gap)归入 tb.max_start_gap;edge 在 dag_spec 显式
引用同一字段(SSoT 单一定义,不双写不校验)。

EdgesParams 当前空,作格式契约 + 未来扩展占位。

dag_spec.py / 测试 fixture / yaml 文件 / eval_runner 在后续 task 同步迁移。"
```

---

### Task 2: Rewrite params.yaml to nested 4-section structure

**Files:**
- Modify: `path2_apps/bottom_breakout_burst/params.yaml`(整体重写)

**Interfaces:**
- Consumes: Task 1 的 `BoParams/BurstParams/TbParams/EdgesParams` schema
- Produces: yaml 文件能被 `Params.from_yaml(DEFAULT_YAML_PATH)` 加载,返回与现 V3.3 B 方案严值等价的实例;`load_params()` 测试此后通过

- [ ] **Step 1: Rewrite yaml file**

完全替换 `path2_apps/bottom_breakout_burst/params.yaml` 内容:

```yaml
# Default params for bottom_breakout_burst pattern (V3.3 B 方案,nested by node role)。
# 调参在开发完成后单独进行,本文件先用合理默认值。改完下一次 web /scan 即热加载生效。

bo:
  total_window: 20
  min_side_bars: 6
  min_relative_height: 0.2
  exceed_threshold: 0.003
  peak_supersede_threshold: 0.01
  vol_baseline_period: 63
  peak_measure: high
  breakout_measure: high

burst:
  # detector 构造(切串)
  gap_max: 5
  vol_baseline_period: 63
  # detector + 业务约束② 共用(BurstDetector(min_bos) + len(bo 串) ≥ min_bos)
  min_bos: 2
  # burst node 的 where 阈值(detector 不读,只在 NodeSpec.where 闭合)
  first_drought_min: 20
  distinct_pk_min: 4
  vol_spike_min: 8.0

tb:
  # 注意:max_start_gap 同时被 ThrowbackDetector 与 burst→tb edge 复用
  # (SSoT 单一定义,dag_spec 内 edge 显式引用 params.tb.max_start_gap)
  max_start_gap: 5
  max_window: 5
  atr_window: 14
  big_rise_k: 1.5
  pullback_min_atr: 1.0
  anchor_measure: high
  support_measure: close

# edges 段:当前所有 edge 字段或硬编码(min_gap=1/anchor_field/Child(...))或从 node
# section 引用(max_gap = tb.max_start_gap),故本段当前为空。保留 section 占位以便未来
# 扩展 edge-only 参数(如某新边的 max_lag)。
edges: {}
```

- [ ] **Step 2: Verify load_params now succeeds**

Run: `uv run pytest tests/path2/apps/test_params.py::test_load_params_reads_default_yaml_path -v`
Expected: PASS

Run: `uv run pytest tests/path2/apps/test_params.py -v`
Expected: 8 PASS(全部 Task 1 + 本 task 的测试)

- [ ] **Step 3: Quick sanity verify via Python REPL**

Run:
```bash
uv run python -c "
from path2_apps.bottom_breakout_burst import load_params, Params
p = load_params()
print(f'bo.total_window = {p.bo.total_window} (yaml 严值 20)')
print(f'burst.min_bos = {p.burst.min_bos} (yaml 2,原 MIN_BOS)')
print(f'burst.first_drought_min = {p.burst.first_drought_min} (yaml 20,原 THR_DROUGHT)')
print(f'tb.max_start_gap = {p.tb.max_start_gap}')
print(f'切片函数: bo_kwargs = {list(p.bo_kwargs())}')
print(f'切片函数: burst_kwargs = {p.burst_kwargs()}')
"
```
Expected:
```
bo.total_window = 20 (yaml 严值 20)
burst.min_bos = 2 (yaml 2,原 MIN_BOS)
burst.first_drought_min = 20 (yaml 20,原 THR_DROUGHT)
tb.max_start_gap = 5
切片函数: bo_kwargs = ['total_window', 'min_side_bars', 'min_relative_height', 'exceed_threshold', 'peak_supersede_threshold', 'vol_baseline_period', 'peak_measure', 'breakout_measure']
切片函数: burst_kwargs = {'gap_max': 5, 'min_bos': 2, 'vol_baseline_period': 63}
```

- [ ] **Step 4: Commit**

```bash
git add path2_apps/bottom_breakout_burst/params.yaml
git commit -m "path2_apps/params.yaml: 重写为 nested 4 section(bo/burst/tb/edges)

字段命名全部小写;删 burst_min_bos/burst_vol_ratio_spike_thr 死字段;
MIN_BOS/THR_* 归入 burst section 改语义化小写。edges:{}保留作占位。"
```

---

### Task 3: Migrate dag_spec.py + test_dag_spec.py to nested references

**Files:**
- Modify: `path2_apps/bottom_breakout_burst/dag_spec.py:1-98`
- Modify: `tests/path2_apps/bottom_breakout_burst/test_dag_spec.py:71`

**Interfaces:**
- Consumes: Task 1 的 Params nested 路径(`params.bo.X` / `params.burst.X` / `params.tb.X`)、`bo_kwargs()/burst_kwargs()/throwback_kwargs()` 返回字典(签名不变)
- Produces: `build_pattern(params)` / `analyze` / `matches` / `eval_meta` / `PATTERN_DAG` 对外行为不变,内部引用全部走 nested 路径

- [ ] **Step 1: Read current dag_spec.py structure first to identify all field-access call sites**

Run: `grep -n "params\." path2_apps/bottom_breakout_burst/dag_spec.py`
Expected output(用于参考、确认改造点):
```
40:                 BODetector(**params.bo_kwargs()),
44:                 BurstDetector(**params.burst_kwargs()),
45:                 where=(("first_drought", W.attr("first_drought", ">=", params.THR_DROUGHT)),
46:                        ("distinct_pk",   W.attr("distinct_pk",   ">=", params.THR_PK)),
47:                        ("vol_spike",     W.attr("max_bar_vol_ratio", ">=", params.THR_VOL))),
51:                 ThrowbackDetector(**params.throwback_kwargs()),
58:            min_gap=1, max_gap=params.throwback_max_start_gap,
```
还有 `eval_meta` 内:
```
92:            p.bo_vol_baseline_period,
93:            p.burst_vol_baseline_period,
94:            p.throwback_atr_window,
95:            p.bo_total_window,
```

- [ ] **Step 2: Apply 6 edits to dag_spec.py**

Edit 1(模块 docstring 第 9-12 行的业务约束注释,字段名更新):

old (lines 8-14):
```
约束归宿:
  ② len(bo 串) >= MIN_BOS          -> BurstDetector(min_bos)
  ③ 首 bo.drought >= THR_DROUGHT   -> burst where W.attr("first_drought")
  ⑤ distinct_pk >= THR_PK          -> burst where W.attr("distinct_pk")
  ⑥ Any vol_ratio >= THR_VOL       -> burst where W.attr("max_bar_vol_ratio")
  ⑦ 末 bo 后回踩，身份锚定         -> TemporalEdge(Child(burst,"last_bo"), tb,
                                           anchor_field="anchor_bo_id")
```
new:
```
约束归宿:
  ② len(bo 串) >= burst.min_bos          -> BurstDetector(min_bos)
  ③ 首 bo.drought >= burst.first_drought_min   -> burst where W.attr("first_drought")
  ⑤ distinct_pk >= burst.distinct_pk_min       -> burst where W.attr("distinct_pk")
  ⑥ Any vol_ratio >= burst.vol_spike_min       -> burst where W.attr("max_bar_vol_ratio")
  ⑦ 末 bo 后回踩,身份锚定                -> TemporalEdge(Child(burst,"last_bo"), tb,
                                           anchor_field="anchor_bo_id")
```

Edit 2(line 45-47 where 子句):

old:
```python
                 where=(("first_drought", W.attr("first_drought", ">=", params.THR_DROUGHT)),  # ③
                        ("distinct_pk",   W.attr("distinct_pk",   ">=", params.THR_PK)),        # ⑤
                        ("vol_spike",     W.attr("max_bar_vol_ratio", ">=", params.THR_VOL))),   # ⑥
```
new:
```python
                 where=(("first_drought", W.attr("first_drought", ">=", params.burst.first_drought_min)),  # ③
                        ("distinct_pk",   W.attr("distinct_pk",   ">=", params.burst.distinct_pk_min)),        # ⑤
                        ("vol_spike",     W.attr("max_bar_vol_ratio", ">=", params.burst.vol_spike_min))),   # ⑥
```

Edit 3(line 58 edge 引用):

old:
```python
            min_gap=1, max_gap=params.throwback_max_start_gap,
```
new:
```python
            # max_gap 与 ThrowbackDetector(max_start_gap=...) 共用同一 SSoT (tb.max_start_gap)
            min_gap=1, max_gap=params.tb.max_start_gap,
```

Edit 4(eval_meta 第 91-96 行 head_buffer):

old:
```python
        "head_buffer_trading_days": max(
            p.bo_vol_baseline_period,
            p.burst_vol_baseline_period,
            p.throwback_atr_window,
            p.bo_total_window,
        ),
```
new:
```python
        "head_buffer_trading_days": max(
            p.bo.vol_baseline_period,
            p.burst.vol_baseline_period,
            p.tb.atr_window,
            p.bo.total_window,
        ),
```

- [ ] **Step 3: Update test_dag_spec.py edge assertion**

文件 `tests/path2_apps/bottom_breakout_burst/test_dag_spec.py:71`:

old:
```python
    assert edge.max_gap == Params.default().throwback_max_start_gap
```
new:
```python
    assert edge.max_gap == Params.default().tb.max_start_gap
```

- [ ] **Step 4: Run dag_spec + test_dag_spec tests**

Run: `uv run pytest tests/path2_apps/bottom_breakout_burst/test_dag_spec.py -v`
Expected: ALL PASS

Run: `uv run pytest path2_apps/bottom_breakout_burst/dag_spec.py --collect-only 2>&1 | head -20`
Expected: 无 import error(模块加载成功)

- [ ] **Step 5: Commit**

```bash
git add path2_apps/bottom_breakout_burst/dag_spec.py tests/path2_apps/bottom_breakout_burst/test_dag_spec.py
git commit -m "path2_apps/dag_spec: 引用迁移到 nested params(bo/burst/tb)

params.THR_DROUGHT → params.burst.first_drought_min
params.THR_PK → params.burst.distinct_pk_min
params.THR_VOL → params.burst.vol_spike_min
params.throwback_max_start_gap → params.tb.max_start_gap (edge 复用)
eval_meta head_buffer 用 p.bo/p.burst/p.tb 嵌套访问
模块 docstring 业务约束 ②③⑤⑥ 字段名同步更新"
```

---

### Task 4: Adapt eval_runner.py param_overrides to nested dict + update test_eval_runner.py

**Files:**
- Modify: `path2_web/eval_runner.py:41-46`(worker 内 base + override 合并逻辑)
- Modify: `tests/path2_web/test_eval_runner.py:12-16`(RELAXED dict 改 nested)

**Interfaces:**
- Consumes: Task 1 的 `Params` 嵌套结构
- Produces: `param_overrides` 协议从 flat dict 改为 nested dict (`{"bo": {...}, "burst": {...}}`),worker 内对每个 section 用 `dataclasses.replace(getattr(base, sect), **sect_overrides)` 局部 patch 后再 `replace(base, **section_kwargs)` 合并

- [ ] **Step 1: Update eval_runner.py worker logic**

文件 `path2_web/eval_runner.py:41-46`:

old:
```python
    symbol = Path(pkl_path).stem
    try:
        df = pd.read_pickle(pkl_path)
        mod = importlib.import_module(module_path)
        base = mod.load_params() if hasattr(mod, "load_params") else mod.Params.default()
        params = replace(base, **param_overrides) if param_overrides else base
```
new:
```python
    symbol = Path(pkl_path).stem
    try:
        df = pd.read_pickle(pkl_path)
        mod = importlib.import_module(module_path)
        base = mod.load_params() if hasattr(mod, "load_params") else mod.Params.default()
        if param_overrides:
            # nested dict:{"bo": {"min_relative_height": 0.02}, "burst": {"min_bos": 2}, ...}
            # 对每个 section 局部 patch 子 dataclass,再合并回顶层 Params。
            section_kwargs = {sect: replace(getattr(base, sect), **sect_overrides)
                              for sect, sect_overrides in param_overrides.items()}
            params = replace(base, **section_kwargs)
        else:
            params = base
```

也更新 `_eval_ticker` docstring(行 33-39):

old:
```python
    """Worker:读 pkl → 双端缓冲切窗 → analyze → 窗内过滤 + 按买点去重 → 多 horizon 收益。

    模块级函数(ProcessPool pickle 安全)。base = mod.load_params() 读 app 同目录
    params.yaml(SSoT),param_overrides 经 replace(base, **overrides) 叠加(dict 跨
    进程 pickle 安全)。语义:override 在 yaml base 之上,与 web /scan 结果可比。
    有效性 = 买点起点日期 ∈ [start, end];去重 = 按 end_role event_id(评估对象是买点)。
    返回 (symbol, rows, err|None);单股异常捕获返回 err,绝不抛。
    """
```
new:
```python
    """Worker:读 pkl → 双端缓冲切窗 → analyze → 窗内过滤 + 按买点去重 → 多 horizon 收益。

    模块级函数(ProcessPool pickle 安全)。base = mod.load_params() 读 app 同目录
    params.yaml(SSoT)。param_overrides 是 **nested dict**(如 {"bo":{"min_relative_height":0.02},
    "burst":{"min_bos":2}}),worker 内逐 section 用 dataclasses.replace 局部 patch
    子 dataclass 后合并(跨进程 pickle 安全)。语义:override 在 yaml base 之上,
    与 web /scan 结果可比。有效性 = 买点起点日期 ∈ [start, end];去重 = 按 end_role
    event_id(评估对象是买点)。返回 (symbol, rows, err|None);单股异常捕获返回 err,绝不抛。
    """
```

- [ ] **Step 2: Update RELAXED dict in test_eval_runner.py**

文件 `tests/path2_web/test_eval_runner.py:10-16`:

old:
```python
APP = "path2_apps.bottom_breakout_burst"
# _synth_positive 的宽松命中参数(来源:tests/path2/apps/test_matches.py::test_matches_positive,
# 以 overrides dict 形式喂给评估器,验证 param_overrides 链路)
RELAXED = dict(
    bo_min_relative_height=0.02, burst_min_bos=2, MIN_BOS=2,
    THR_DROUGHT=20, THR_PK=2, THR_VOL=3.0,
    bo_peak_measure="body_top", bo_breakout_measure="body_top",
)
```
new:
```python
APP = "path2_apps.bottom_breakout_burst"
# _synth_positive 的宽松命中参数(来源:tests/path2/apps/test_matches.py::test_matches_positive,
# 以 nested overrides dict 形式喂给评估器,验证 param_overrides 链路)。
# nested dict 协议:顶层 key = section 名(bo/burst/tb/edges),value = section 内字段 dict。
RELAXED = dict(
    bo=dict(
        min_relative_height=0.02,
        peak_measure="body_top",
        breakout_measure="body_top",
    ),
    burst=dict(
        min_bos=2,
        first_drought_min=20,
        distinct_pk_min=2,
        vol_spike_min=3.0,
    ),
)
```

- [ ] **Step 3: Run eval_runner tests**

Run: `uv run pytest tests/path2_web/test_eval_runner.py -v`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add path2_web/eval_runner.py tests/path2_web/test_eval_runner.py
git commit -m "path2_web/eval_runner: param_overrides 协议改 nested dict

匹配 Params nested 重构:{\"bo\":{\"min_relative_height\":0.02}, \"burst\":{...}} 形态。
worker 内逐 section 用 dataclasses.replace 局部 patch 子 dataclass,再合并回顶层
Params。test_eval_runner.RELAXED dict 同步重写。"
```

---

### Task 5: Migrate remaining test fixtures (test_matches.py + positive_case.py)

**Files:**
- Modify: `tests/path2/apps/test_matches.py:135-147, 262-273, 276-288, 290-296, 299-305, 350-360`
- Modify: `tests/path2/fixtures/positive_case.py:12-19`

**Interfaces:**
- Consumes: Task 1 的 Params nested 构造 + BoParams/BurstParams/TbParams
- Produces: 测试 fixture 全部用 `Params(bo=BoParams(...), burst=BurstParams(...), ...)` 嵌套构造

- [ ] **Step 1: Update positive_case.py fixture**

文件 `tests/path2/fixtures/positive_case.py:14-18`:

old:
```python
    params = Params(
        bo_min_relative_height=0.02,
        burst_min_bos=2, MIN_BOS=2,
        THR_DROUGHT=20, THR_PK=2, THR_VOL=3.0,
    )
```
new:
```python
    from path2_apps.bottom_breakout_burst.params import BoParams, BurstParams
    params = Params(
        bo=BoParams(min_relative_height=0.02),
        burst=BurstParams(min_bos=2, first_drought_min=20, distinct_pk_min=2, vol_spike_min=3.0),
    )
```

- [ ] **Step 2: Update test_matches.py — first fixture (test_matches_positive line 139-146)**

old:
```python
    p_relaxed = Params(
        bo_min_relative_height=0.02,
        burst_min_bos=2, MIN_BOS=2,
        THR_DROUGHT=20,
        THR_PK=2,
        THR_VOL=3.0,
        bo_peak_measure="body_top", bo_breakout_measure="body_top",  # fixture 按 body_top 调校;high 默认由全宇宙 gate 覆盖
    )
```
new:
```python
    p_relaxed = Params(
        bo=BoParams(
            min_relative_height=0.02,
            peak_measure="body_top", breakout_measure="body_top",   # fixture 按 body_top 调校;high 默认由全宇宙 gate 覆盖
        ),
        burst=BurstParams(min_bos=2, first_drought_min=20, distinct_pk_min=2, vol_spike_min=3.0),
    )
```

- [ ] **Step 3: Update test_matches.py imports (line 1-10 区域)**

在 test_matches.py 顶部找到 `from path2_apps.bottom_breakout_burst.params import Params`(如有),改为:
```python
from path2_apps.bottom_breakout_burst.params import Params, BoParams, BurstParams
```
(找不到的话在 imports 区域加这行。`TbParams`/`EdgesParams` 不需 import,test_matches 不用)

- [ ] **Step 4: Update test_matches.py — test_matches_no_drought_returns_false (line 263-272)**

old:
```python
    p = Params(
        bo_min_relative_height=0.02,
        burst_min_bos=2, MIN_BOS=2,
        THR_DROUGHT=60,  # 默认值,fixture 的首 BO drought 远小于此
        THR_PK=2,
        THR_VOL=3.0,
        bo_peak_measure="body_top", bo_breakout_measure="body_top",  # fixture 按 body_top 调校;high 默认由全宇宙 gate 覆盖
    )
```
new:
```python
    p = Params(
        bo=BoParams(
            min_relative_height=0.02,
            peak_measure="body_top", breakout_measure="body_top",
        ),
        burst=BurstParams(min_bos=2, first_drought_min=60, distinct_pk_min=2, vol_spike_min=3.0),
        # first_drought_min=60:fixture 的首 BO drought 远小于此 → 谓词 ③ 不命中
    )
```

- [ ] **Step 5: Update test_matches.py — test_matches_no_throwback_returns_false (line 277-286)**

old:
```python
    p = Params(
        bo_min_relative_height=0.02,
        burst_min_bos=2, MIN_BOS=2,
        THR_DROUGHT=20,
        THR_PK=2,
        THR_VOL=3.0,
        bo_peak_measure="body_top", bo_breakout_measure="body_top",  # fixture 按 body_top 调校;high 默认由全宇宙 gate 覆盖
    )
```
new:
```python
    p = Params(
        bo=BoParams(
            min_relative_height=0.02,
            peak_measure="body_top", breakout_measure="body_top",
        ),
        burst=BurstParams(min_bos=2, first_drought_min=20, distinct_pk_min=2, vol_spike_min=3.0),
    )
```

- [ ] **Step 6: Update test_matches.py — test_matches_no_prior_down_returns_false (line 292-295)**

old:
```python
    p = Params(
        MIN_BOS=3, THR_DROUGHT=20, THR_PK=2, THR_VOL=1.5,
    )
```
new:
```python
    p = Params(
        burst=BurstParams(min_bos=3, first_drought_min=20, distinct_pk_min=2, vol_spike_min=1.5),
    )
```

- [ ] **Step 7: Update test_matches.py — test_matches_shallow_prior_down_returns_false (line 300-304)**

old:
```python
    p = Params(
        MIN_BOS=3, THR_DROUGHT=20, THR_PK=2, THR_VOL=1.5,
    )
```
new:
```python
    p = Params(
        burst=BurstParams(min_bos=3, first_drought_min=20, distinct_pk_min=2, vol_spike_min=1.5),
    )
```

- [ ] **Step 8: Update test_matches.py — any remaining `Params(...)` constructor uses around line 350-360**

打开文件 `tests/path2/apps/test_matches.py`,grep 找剩余 `Params(`:

Run: `grep -n "Params(" tests/path2/apps/test_matches.py`

对每个剩余 case 应用同款 nested 改造模式:
- `bo_X` → `bo=BoParams(X=...)` (BoParams 字段名去掉 `bo_` 前缀)
- `MIN_BOS` → `burst=BurstParams(min_bos=...)`
- `THR_DROUGHT` → `burst=BurstParams(first_drought_min=...)`
- `THR_PK` → `burst=BurstParams(distinct_pk_min=...)`
- `THR_VOL` → `burst=BurstParams(vol_spike_min=...)`
- `burst_min_bos`/`burst_vol_ratio_spike_thr` → 删除(死字段)

如果 line 350-360 包含 fixture:

old(类似):
```python
    p = Params(
        bo_min_relative_height=0.02,
        burst_min_bos=2, MIN_BOS=2,
        THR_DROUGHT=20, THR_PK=2, THR_VOL=3.0,
        bo_peak_measure="body_top", bo_breakout_measure="body_top",
    )
```
new(套用模板):
```python
    p = Params(
        bo=BoParams(
            min_relative_height=0.02,
            peak_measure="body_top", breakout_measure="body_top",
        ),
        burst=BurstParams(min_bos=2, first_drought_min=20, distinct_pk_min=2, vol_spike_min=3.0),
    )
```

- [ ] **Step 9: Run test_matches + positive_case 相关测试**

Run: `uv run pytest tests/path2/apps/test_matches.py -v`
Expected: ALL PASS

Run: `uv run pytest tests/path2/ -q -k 'positive_case or test_matches'`
Expected: ALL PASS

- [ ] **Step 10: Commit**

```bash
git add tests/path2/apps/test_matches.py tests/path2/fixtures/positive_case.py
git commit -m "tests/path2: 迁移 fixture 到 nested Params(bo/burst/...)

test_matches.py / positive_case.py 全部 Params(bo_X=, MIN_BOS=, THR_*=) 改为
Params(bo=BoParams(X=...), burst=BurstParams(min_bos=, first_drought_min=, ...))。
死字段 burst_min_bos / burst_vol_ratio_spike_thr 在 fixture 内自然消失。"
```

---

### Task 6: Full pytest regression + e2e hot-reload + unknown-key verification

**Files:** (无文件修改,仅验证)

**Interfaces:**
- Consumes: 前 5 个 task 的全部改动
- Produces: 全 path2 regression 绿(518 passed + 1 pre-existing throwback fail 无关);web 后端启动后改 yaml 不重启即生效;yaml 拼错 key 报 500

- [ ] **Step 1: Run full regression**

Run: `uv run pytest tests/path2 tests/path2_apps tests/path2_web -q`
Expected: `518 passed, 2 skipped, 1 failed` (failed = `tests/path2/atoms/test_throwback.py::test_evaluate_anchor_measure_close`,pre-existing 与本 plan 无关)

如果有任何**新失败**,说明前面 task 漏改某个字段引用。打开失败 trace,grep 失败 module 查 `params\.[A-Z_]+` 残留大写名 / `params\.bo_` 或 `burst_min_bos` 残留 flat 名;补齐改动后重跑直到绿。

- [ ] **Step 2: Start web backend in background**

Run:
```bash
pkill -f 'path2_web' 2>/dev/null; sleep 2
cat > /tmp/start_web.sh << 'EOF'
#!/bin/bash
cd /home/yu/PycharmProjects/Trade_Strategy
exec uv run python -m path2_web.main > /tmp/path2_web.log 2>&1
EOF
chmod +x /tmp/start_web.sh
nohup /tmp/start_web.sh > /dev/null 2>&1 &
sleep 5
tail -3 /tmp/path2_web.log
```
Expected:
```
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

- [ ] **Step 3: Verify /patterns reflects current yaml**

Run:
```bash
curl -sS http://127.0.0.1:8000/patterns | python -c "
import json, sys
data = json.load(sys.stdin)
for n in data[0]['topology']['nodes']:
    if n['node_id'] == 'burst':
        print('burst where_rules (反映当前 yaml):')
        for r in n['where_rules']: print(f'  {r}')"
```
Expected:
```
burst where_rules (反映当前 yaml):
  {'clause_id': 'first_drought', 'op': '>=', 'threshold': 20}
  {'clause_id': 'distinct_pk', 'op': '>=', 'threshold': 4}
  {'clause_id': 'vol_spike', 'op': '>=', 'threshold': 8.0}
```

- [ ] **Step 4: Modify yaml in place (no web restart) + verify hot-reload**

Run:
```bash
cp path2_apps/bottom_breakout_burst/params.yaml /tmp/yaml_orig_nested.yaml
# 把 burst.distinct_pk_min 从 4 改成 3, vol_spike_min 从 8.0 改成 5.5
python -c "
import pathlib
p = pathlib.Path('path2_apps/bottom_breakout_burst/params.yaml')
txt = p.read_text()
txt = txt.replace('distinct_pk_min: 4', 'distinct_pk_min: 3')
txt = txt.replace('vol_spike_min: 8.0', 'vol_spike_min: 5.5')
p.write_text(txt)
"
echo '=== 改后 /patterns 立即反映(web 未重启): ==='
curl -sS http://127.0.0.1:8000/patterns | python -c "
import json, sys
data = json.load(sys.stdin)
for n in data[0]['topology']['nodes']:
    if n['node_id'] == 'burst':
        for r in n['where_rules']: print(f'  {r}')"
```
Expected:
```
=== 改后 /patterns 立即反映(web 未重启): ===
  {'clause_id': 'first_drought', 'op': '>=', 'threshold': 20}
  {'clause_id': 'distinct_pk', 'op': '>=', 'threshold': 3}
  {'clause_id': 'vol_spike', 'op': '>=', 'threshold': 5.5}
```

- [ ] **Step 5: Restore yaml + verify revert**

Run:
```bash
cp /tmp/yaml_orig_nested.yaml path2_apps/bottom_breakout_burst/params.yaml
echo '=== 还原后 /patterns 反映还原: ==='
curl -sS http://127.0.0.1:8000/patterns | python -c "
import json, sys
data = json.load(sys.stdin)
for n in data[0]['topology']['nodes']:
    if n['node_id'] == 'burst':
        for r in n['where_rules']: print(f'  {r}')"
```
Expected: distinct_pk=4, vol_spike=8.0 还原。

- [ ] **Step 6: Test unknown-key guard (顶层 section + section 内字段两层)**

Run:
```bash
# 测试 1:未知顶层 section
echo 'foooo: { bar: 1 }' >> path2_apps/bottom_breakout_burst/params.yaml
echo '=== 未知顶层 section 应 500: ==='
curl -sS http://127.0.0.1:8000/patterns | head -c 100
cp /tmp/yaml_orig_nested.yaml path2_apps/bottom_breakout_burst/params.yaml

# 测试 2:section 内未知字段
python -c "
import pathlib
p = pathlib.Path('path2_apps/bottom_breakout_burst/params.yaml')
txt = p.read_text()
txt = txt.replace('  gap_max: 5', '  gap_max: 5\n  typoooo: 99')
p.write_text(txt)
"
echo '=== section 内未知字段应 500: ==='
curl -sS http://127.0.0.1:8000/patterns | head -c 100
echo
echo '=== 看 server log 确认 ValueError: ==='
tail -5 /tmp/path2_web.log | grep -A2 "typoooo\|foooo\|ValueError" | head -10
cp /tmp/yaml_orig_nested.yaml path2_apps/bottom_breakout_burst/params.yaml
```
Expected:
```
=== 未知顶层 section 应 500: ===
Internal Server Error
=== section 内未知字段应 500: ===
Internal Server Error
=== 看 server log 确认 ValueError: ===
... ValueError: params.yaml (...) section 'burst' 含未知字段: ['typoooo'] ...
```

- [ ] **Step 7: Clean up + final regression**

Run:
```bash
pkill -f 'path2_web' 2>/dev/null
rm -f /tmp/yaml_orig_nested.yaml /tmp/start_web.sh /tmp/path2_web.log
# 确认 yaml 真还原(无残留改动)
git diff path2_apps/bottom_breakout_burst/params.yaml
```
Expected: `git diff` 输出 empty(yaml 干净还原成 task 2 落地状态)

Run: `uv run pytest tests/path2 tests/path2_apps tests/path2_web -q`
Expected: 同 Step 1,518 passed + 1 pre-existing fail。

- [ ] **Step 8: Commit verification artifacts (无文件改动,仅记录)**

如本 task 实际未改任何文件(预期),跳过 commit。如发现回归补改了字段,把那些改动合并到对应前置 task 的 commit(用 `git commit --amend` 或 fixup)而非新 commit。

---

### Task 7: Update authoring-path2-app skill docs

**Files:**
- Modify: `.claude/skills/authoring-path2-app/SKILL.md`
- Modify: `.claude/skills/authoring-path2-app/design-heuristics.md`

**Interfaces:**
- Consumes: 前 6 task 落地的 nested schema 现实
- Produces: skill 文档反映 nested 三件套 + 节奏更新(新建 app 必须建 nested params.py + 4 section yaml)

- [ ] **Step 1: Update SKILL.md — Step 0.5 现状盘点(L44 区域)**

找到 SKILL.md 中 "现场读" 这段(描述 Step 0.5):

old(片段):
```
1. **现场读** `path2_apps/<id>/dag_spec.py` + `params.py` + `params.yaml`:
   - dag_spec.py + params.py 看节点集/边集/detector 选型 + **字段 schema**(名/类型)
   - **params.yaml 看 web 真用的当前值**(SSoT;dataclass 字段 default 只是 yaml 缺失字段时的兜底 / CLI/tests fixture 默认,不是 web 真值)
   盘点扑空(目录不存在或空壳)→ 改判创建。
```
new(片段):
```
1. **现场读** `path2_apps/<id>/dag_spec.py` + `params.py` + `params.yaml`:
   - dag_spec.py 看节点集/边集/detector 选型
   - params.py 看 **nested schema** (BoParams/BurstParams/TbParams/EdgesParams 4 子 dataclass,
     字段名/类型) + 切片函数(bo_kwargs/burst_kwargs/throwback_kwargs)
   - **params.yaml 看 web 真用的当前值**(SSoT 4 section: bo/burst/tb/edges;
     dataclass 子字段 default 只是 yaml 缺失字段时的兜底 / CLI/tests fixture 默认,不是 web 真值)
   盘点扑空(目录不存在或空壳)→ 改判创建。
```

- [ ] **Step 2: Update SKILL.md — 层③ 参数初值落地纪律**

找到层③段落,把"参数落地纪律(三件套分工)"那一节整体替换:

old(整段):
```
**参数落地纪律(三件套分工)**:
- **`params.yaml` = SSoT**:web 入口(scan/api/eval_runner)真读,改完下一次 /scan 即生效
  (热加载,无需重启 web);所有真用值写这里。
- **`params.py` = schema 层**:字段名/类型注解(IDE/mypy 安全 + `bo_kwargs()`/`tb_kwargs()`/
  `burst_kwargs()` 切片函数 + `from_yaml` 加载器);**dataclass 字段 default = yaml 缺失字段
  时的兜底 + CLI 脚本 / tests fixture 默认**,不是 web 真值。
- **新建 app 必须同时落 `params.py`+`params.yaml`**:`params.py` 经 `from .params import
  Params, load_params, DEFAULT_YAML_PATH` 在包 init **和** `dag_spec.py` 都 re-export(web
  registry 注册 `.dag_spec` 路径,worker 拿到子模块,故 dag_spec 也需 re-export)。
- **eval_runner `param_overrides` dict 叠加在 yaml base 之上**:语义 = 在当前扫描值上做
  微调对比迭代;不破坏 yaml SSoT。
```
new(整段):
```
**参数落地纪律(三件套分工,nested by node role)**:
- **`params.yaml` = SSoT**:web 入口(scan/api/eval_runner)真读,改完下一次 /scan 即生效
  (热加载,无需重启 web);所有真用值写这里。**yaml 必须是 nested 4 section: bo/burst/tb/edges**
  (与子 dataclass 一一对应)。
- **`params.py` = nested schema 层**:4 子 dataclass(`BoParams`/`BurstParams`/`TbParams`/
  `EdgesParams`)各持有该 node 角色的 detector 构造参数 + where 阈值;`Params` 容器持有
  4 子 dataclass 实例。切片函数 `bo_kwargs()`/`burst_kwargs()`/`throwback_kwargs()` 返回
  detector 构造 dict(返回 dict 签名不变,内部从子 dataclass 取值)。`from_yaml` 递归校验
  顶层 section + 每 section 字段两层未知 key,堵 yaml 拼错静默无效。**子 dataclass 字段 default
  = yaml 缺失字段时的兜底 + CLI 脚本 / tests fixture 默认**,不是 web 真值。
- **新建 app 必须同时落 `params.py`(4 子 dataclass + Params 容器 + from_yaml + load_params)
  + `params.yaml`(4 section)**;`params.py` 经 `from .params import Params, load_params,
  DEFAULT_YAML_PATH` 在包 init **和** `dag_spec.py` 都 re-export(web registry 注册 `.dag_spec`
  路径,worker 拿到子模块,故 dag_spec 也需 re-export)。
- **共用字段归宿原则**:同一字段被 detector 与 edge 同时读时(如 `tb.max_start_gap` 既给
  ThrowbackDetector 又给 burst→tb edge),按"语义归宿 = 谁定义"放入该 detector 的 section
  (SSoT 单一定义),dag_spec 内 edge 显式引用同字段。**禁双写**(双写允许漂移即是 bug)。
- **eval_runner `param_overrides` 是 nested dict**:形如 `{"bo": {"min_relative_height": 0.02},
  "burst": {"min_bos": 2}}`。worker 内对每个 section 用 `dataclasses.replace` 局部 patch。
  语义 = 在 yaml base 上做对比迭代,不破坏 SSoT。
- **EdgesParams 当前留空**作格式契约 + 未来 edge-only 参数扩展占位(eg. 某新边自己的 max_lag)。
```

- [ ] **Step 3: Update SKILL.md — Step 3 落地文件清单**

找到 "## Step 3 产出 spec + 移交实现" 段落:

old(片段):
```
spec 已增量写就,补齐:落地文件清单 `path2_apps/<id>/{dag_spec,params,__init__}.py +
params.yaml`(结构对照现存 app 现场读;特别注意 yaml 是 web SSoT、必须落,
不能只写 params.py)。
```
new(片段):
```
spec 已增量写就,补齐:落地文件清单 `path2_apps/<id>/{dag_spec,params,__init__}.py +
params.yaml`(结构对照现存 app 现场读)。**params.py 必须建 4 子 dataclass(BoParams/
BurstParams/TbParams/EdgesParams)+ Params 容器持有它们;params.yaml 必须 4 section
(bo/burst/tb/edges)与之一一对应。** yaml 是 web SSoT、必须落,不能只写 params.py。
EdgesParams 若 app 内 edge 都用硬编码 / node-section 引用,留空 dataclass + yaml `edges: {}`
作格式契约。
```

- [ ] **Step 4: Update SKILL.md — 层② 字段同步纪律**

找到层② "修改现有 detector" 分支末尾的"字段重命名/新增"那条:

old(片段):
```
  5. **字段重命名/新增**:`params.py` Params dataclass 字段必须与 `params.yaml` 的 key
     一一对应——yaml 含未知字段会被 `from_yaml` ValueError 拒掉(护栏堵静默无效);
     yaml 改名时 params.py 字段名也必须同改,反之亦然。
```
new(片段):
```
  5. **字段重命名/新增**:`params.py` 子 dataclass(BoParams/BurstParams/TbParams)字段必须与
     `params.yaml` 对应 section 的 key 一一对应——yaml 顶层未知 section 或 section 内未知
     字段都会被 `from_yaml` ValueError 拒掉(护栏堵静默无效);yaml 改名时子 dataclass 字段
     必须同改,反之亦然。**跨 section 移动字段**(如 burst 字段挪到 tb)也要同步两处。
```

- [ ] **Step 5: Update design-heuristics.md — §D evaluator override 语义**

找到 design-heuristics.md §D 末尾的 "param_overrides 叠加语义" 那段:

old(片段):
```
**param_overrides 叠加语义**:worker 内 `base = mod.load_params()`(读 app 同目录
params.yaml,SSoT),然后 `replace(base, **param_overrides)`——dict 字段覆盖 yaml
对应字段。意味着:**内存迭代评估器的 base 与 web /scan 是同一套 yaml 值**,
override 在它上面微调对比,结果与 web 扫描可比。纯调参路收敛后,把胜出值写回
yaml 即让 web 真生效(不必改源代码)。
```
new(片段):
```
**param_overrides 叠加语义(nested dict)**:worker 内 `base = mod.load_params()`(读 app
同目录 params.yaml,SSoT),`param_overrides` 是 **nested dict**(如
`{"bo": {"min_relative_height": 0.02}, "burst": {"min_bos": 2}}`),worker 内对每个 section
用 `dataclasses.replace(getattr(base, sect), **sect_overrides)` 局部 patch 子 dataclass,
再 `replace(base, **section_kwargs)` 合并。意味着:**内存迭代评估器的 base 与 web /scan
是同一套 yaml 值**,override 在它上面微调对比,结果与 web 扫描可比。纯调参路收敛后,
把胜出值写回 yaml 对应 section 即让 web 真生效(不必改源代码)。
```

- [ ] **Step 6: Commit**

```bash
git add .claude/skills/authoring-path2-app/SKILL.md .claude/skills/authoring-path2-app/design-heuristics.md
git commit -m "skill/authoring-path2-app: 同步 nested params 三件套纪律

Step 0.5 现状盘点 / 层③ 参数初值落地 / Step 3 文件清单 / 层② 字段同步纪律 /
design-heuristics §D override 语义,全部更新反映 nested by node role 设计:
- 4 子 dataclass (BoParams/BurstParams/TbParams/EdgesParams) + 4 yaml section
- 共用字段归宿 \"语义 = 谁定义\" 原则 (SSoT 单一定义,禁双写)
- param_overrides 改 nested dict 协议
- EdgesParams 留空作格式契约 + 未来扩展占位"
```

---

### Task 8: Final regression + status check

**Files:** (无文件修改)

**Interfaces:**
- Consumes: 所有前置 task
- Produces: 全 8 个 commit 落盘,树干干净,全测试绿

- [ ] **Step 1: Final full regression**

Run: `uv run pytest tests/path2 tests/path2_apps tests/path2_web -q`
Expected: `518 passed, 2 skipped, 1 failed`(pre-existing throwback,无关)

- [ ] **Step 2: Verify git log shape**

Run: `git log --oneline -10`
Expected: 看到本 plan 落地的 6 个 commit(task 1, 2, 3, 4, 5, 7),task 6 与 task 8 不创建 commit。

- [ ] **Step 3: Verify git status clean**

Run: `git status`
Expected:
```
On branch dag
nothing to commit, working tree clean
```
(或仅有 untracked files 不在本 plan 范围内)

如果 git status 显示未提交的本 plan 改动,逐个 add/commit 补齐(应该在 task 1-5/7 内已 commit,这里只是兜底)。

---

## Self-Review Summary

**Spec coverage:**
- ✅ nested 4 子 dataclass + 4 yaml section (Task 1, 2)
- ✅ 小写命名 + 删大写 MIN_BOS/THR_* (Task 1, 2)
- ✅ 删死字段 burst_min_bos / burst_vol_ratio_spike_thr (Task 1)
- ✅ 共用字段 tb.max_start_gap 单一定义 + edge 显式引用 (Task 1, 3)
- ✅ EdgesParams 作格式契约保留 (Task 1)
- ✅ from_yaml 递归 unknown-key 校验 (Task 1, 6)
- ✅ load_params 协议保留 (Task 1, 2)
- ✅ web 三入口(scan/api/eval_runner)继续用 load_params(已在前回合接通,本 plan 不动) (Task 6 e2e)
- ✅ eval_runner param_overrides 改 nested dict (Task 4)
- ✅ 所有 dag_spec / 测试 fixture 引用迁移 (Task 3, 4, 5)
- ✅ skill 文档更新 (Task 7)
- ✅ e2e 热加载实测 + 未知 key 护栏实测 (Task 6)

**Placeholder scan:** 无 TBD/TODO/"similar to"/"add appropriate error handling" 等。

**Type consistency:**
- `BoParams` 字段名 = bo_kwargs 返回 dict 的 key = BODetector __init__ 参数名 ✅
- `BurstParams.min_bos` ≠ flat `MIN_BOS`、`first_drought_min` ≠ `THR_DROUGHT`,但在 plan 中迁移表一致使用 ✅
- `TbParams.max_start_gap` 同时被 dag_spec edge 引用,plan 中 Task 3 明确 ✅
- `param_overrides` 协议变 nested,Task 4 RELAXED dict 与 worker 解析一致 ✅
