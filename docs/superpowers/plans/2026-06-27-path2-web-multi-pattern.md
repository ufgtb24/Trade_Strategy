# path2_web 多 pattern 同扫与漏检调试 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 path2_web 支持多 pattern 同时扫描:股票列表是命中并集、每 pattern 单开 max(forward_return) 列、可点列头排序;右侧主图/拓扑/侧栏单 active pattern 展示。新增 `path2_apps/bo_only/` 作锚 pattern,核心场景=按 bo 涨幅锚找 bbb(bottom_breakout_burst)漏检。

**Architecture:** N=1 是退化情况、不分叉;统一 schema `MultiScanResultFile` 落 `outputs/path2_web/scans/<ts>.json` 扁平目录;锚 pattern(排序列)与 active pattern(右侧视图)解耦——cell 点击只切股、active pattern 仅由 ChartArea dropdown 显式切;每股每 pattern 都跑完整 analyze 并存完整 analysis(events 全集必存、matches 可空);铁律=所有 pattern 必须声明 eval_meta,discovery 闸过滤,删除所有 fallback 非缓冲路径。

**Tech Stack:** Python 3 / FastAPI / pytest (uv);Vue 3 + Pinia + ECharts + Vite + TypeScript / Vitest / @vue/test-utils;npm 前端构建。

## Global Constraints

- 当前分支:`dag`(增量提交到该分支,**不**新建 worktree)
- 实施使用 `superpowers:subagent-driven-development`:每 task 一个 fresh subagent,task 间 spec + quality 双审;最终 holistic 审。implementer 模型一律 `sonnet`;reviewer 一律 `opus`(memory feedback)
- spec 全文:`docs/superpowers/specs/2026-06-27-path2-web-multi-pattern-design.md`(每 task 引 §X.Y;读 plan 即可实施,不必再回 spec)
- 完整契约不变量:
  - `MultiScanResultFile.per_pattern` 字典键集 ≡ `pattern_ids`(每股每 pattern 必有项,matches 可空)
  - 行入选并集:`any(len(r.per_pattern[pid].analysis.matches) > 0 for pid in pattern_ids)`
  - `max_forward_return` = max over matches 中非 None 的 forward_return;matches 空或全 None → null
  - `head_buffer = max(meta["head_buffer_trading_days"] for pid in pattern_ids)`,label_horizon 全局单值
  - 缓冲段事件可见沿用现状:events 全集照旧序列化、不按窗过滤;matches 仍按窗过滤
- 铁律 eval_meta:discovery 必须验证 `eval_meta` callable + 返回 dict 含 `end_role: str` + `head_buffer_trading_days: int`,缺/错则**跳过该 pattern + log warning**,`/patterns` 不返回
- 锚-active 解耦:列表 cell 点击只 `selectSymbol`,**禁止**动 `activePatternId`;active pattern 切换的唯一入口=ChartArea 顶部 `<select>`
- 不引入新依赖
- 路由不保留旧 per-pattern 前缀(`/scans/{pid}/...` 整条删);旧 `outputs/path2_web/<pid>/<ts>.json` 不读、不迁移、不列(用户手动 rm)
- 测试 gate 四绿:`uv run pytest tests/path2_web`(后端)、`cd path2_web_ui && npm run test`(前端)、`cd path2_web_ui && npx vue-tsc --noEmit`、`cd path2_web_ui && npm run build`
- 删除所有 fallback 到非缓冲扫描的代码分支(见 spec §3.6),铁律下永远不可达
- 前端 cell 默认背景按 `matched`(布尔)染:命中=浅绿、未命中=灰白
- 排序状态:`sortByPid` 初值 null(worker 顺序);点列头第一次 desc、再点同列翻 asc;切到其他列重置该列 desc;无"回 null"三态

---

## File Structure

**新建后端**:
- `path2_apps/bo_only/__init__.py`
- `path2_apps/bo_only/dag_spec.py`
- `path2_apps/bo_only/params.py`
- `path2_apps/bo_only/params.yaml`
- `tests/path2_web/test_discovery_eval_meta_required.py`
- `tests/path2_web/test_scan_multi_pattern.py`
- `tests/path2_web/test_serialize_multi.py`
- `tests/path2_web/test_api_scan_multi.py`
- `tests/path2_web/test_scans_route_flat.py`

**修改后端**:
- `path2_web/discovery.py` — 加 eval_meta 验证闸
- `path2_web/scan.py` — 多 pattern worker + 多 pattern run_scan + 扁平 outputs/scans/ 目录的 list/load/delete
- `path2_web/api.py` — POST /scan 接受 `pattern_ids`、`/scans/` 系列扁平路由、删 `resolve_eval_meta` fallback
- `path2_apps/bottom_breakout_burst/dag_spec.py` — 不动(已有 eval_meta)

**新建前端**:
- `path2_web_ui/tests/unionRows.spec.ts`
- `path2_web_ui/tests/components/SidebarResultList.multi.spec.ts`
- `path2_web_ui/tests/components/SidebarPatternPanel.multi.spec.ts`
- `path2_web_ui/tests/components/ChartArea.activePattern.spec.ts`

**修改前端**:
- `path2_web_ui/src/types.ts` — 加 MultiScanResultFile / PerPatternResult / PerPatternMeta;`StockResult` 重构;`ScanMeta.end_role` 移除、`win_*/label_horizon` 非 optional;`ScanHistoryEntry` 加 `pattern_ids`
- `path2_web_ui/src/api.ts` — startScan body 改 `pattern_ids: string[]`;`listScans()`/`loadScan()`/`deleteScan()` 路径去 pid
- `path2_web_ui/src/stores/view.ts` — state(activePatternId/sortByPid/sortDesc)、computed(patternIds/currentPerStock/effective 三件套/unionRows/sortedRows)、actions(loadScanFile/setActivePattern/setSort)、watch deps 加 activePatternId
- `path2_web_ui/src/stores/scan.ts` — `ScanReq.pattern_id: string` → `pattern_ids: string[]`;`open(scanTs)` 不再需要 patternId 参数
- `path2_web_ui/src/stores/patterns.ts` — 改为多选 `Set<string>`;`last_selected_pattern: string` 字段保留(active 默认值)
- `path2_web_ui/src/components/SidebarPatternPanel.vue` — radio → checkbox + 全选/反选/清空
- `path2_web_ui/src/components/SidebarScanPanel.vue` — disabled 条件 + 起扫描 body 字段
- `path2_web_ui/src/components/SidebarResultList.vue` — N 列 max_ret 渲染 + 列头点击排序 + cell 单元格只 selectSymbol
- `path2_web_ui/src/components/ChartArea.vue` — 顶部加 active pattern `<select>`
- `path2_web_ui/src/components/ScanResultDialog.vue` — 改为读 flat /scans/、显示 pattern_ids chips
- `path2_web_ui/src/render/visible.ts` — `windowOf` 删 `win_*` 回退分支(必有,不回退)

---

## Task 1: 新建 `path2_apps/bo_only/` 子包

**Files:**
- Create: `path2_apps/bo_only/__init__.py`
- Create: `path2_apps/bo_only/dag_spec.py`
- Create: `path2_apps/bo_only/params.py`
- Create: `path2_apps/bo_only/params.yaml`
- Test: 新增 `tests/path2_apps/test_bo_only.py`(若 `tests/path2_apps/` 不存在,创建带 `__init__.py`)

**Interfaces:**
- Produces:
  - `path2_apps.bo_only.dag_spec.PATTERN_DAG: PatternSpec` (单节点 bo,无边)
  - `path2_apps.bo_only.dag_spec.build_pattern(params: Params) -> PatternSpec`
  - `path2_apps.bo_only.dag_spec.analyze(df, params: Optional[Params]=None) -> AnalysisResult`
  - `path2_apps.bo_only.dag_spec.matches(df, params=None) -> bool`
  - `path2_apps.bo_only.dag_spec.eval_meta(params: Optional[Params]=None) -> dict` 返回 `{"end_role": "bo", "head_buffer_trading_days": max(p.bo.vol_baseline_period, p.bo.total_window)}`
  - `path2_apps.bo_only.Params`、`load_params()`、`DEFAULT_YAML_PATH` 同 bottom_breakout_burst 形式

- [ ] **Step 1: 创建 `path2_apps/bo_only/params.yaml`**

```yaml
# bo_only pattern 参数 — 复用 BODetector 默认值。
# 与 bottom_breakout_burst 的 bo section 同义(可独立改),非引用。

bo:
  total_window: 20
  min_side_bars: 6
  min_relative_height: 0.2
  exceed_threshold: 0.003
  peak_supersede_threshold: 0.01
  vol_baseline_period: 63
  peak_measure: high
  breakout_measure: high
```

- [ ] **Step 2: 创建 `path2_apps/bo_only/params.py`**

```python
"""Default Params for bo_only pattern。

单 BODetector 节点 pattern 的参数 schema:仅含 bo section + load_params()。
与 bottom_breakout_burst.params 同形式,独立 yaml 文件。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import yaml

DEFAULT_YAML_PATH = Path(__file__).parent / "params.yaml"


@dataclass(frozen=True)
class BoParams:
    """BODetector 构造参数(与 bottom_breakout_burst.params.BoParams 同 schema)。"""
    total_window: int = 10
    min_side_bars: int = 2
    min_relative_height: float = 0.05
    exceed_threshold: float = 0.005
    peak_supersede_threshold: float = 0.03
    vol_baseline_period: int = 63
    peak_measure: str = "high"
    breakout_measure: str = "high"


@dataclass(frozen=True)
class Params:
    """bo_only 全部 params:仅 bo section。"""
    bo: BoParams = field(default_factory=BoParams)

    @classmethod
    def default(cls) -> "Params":
        return cls()

    @classmethod
    def from_yaml(cls, path: Path) -> "Params":
        raw = yaml.safe_load(path.read_text()) or {}
        bo_section = raw.get("bo", {})
        known = {f.name for f in BoParams.__dataclass_fields__.values()}
        unknown = set(bo_section) - known
        if unknown:
            raise ValueError(f"bo_only params.yaml unknown bo keys: {sorted(unknown)}")
        return cls(bo=BoParams(**bo_section))

    def bo_kwargs(self) -> dict:
        return {f.name: getattr(self.bo, f.name) for f in BoParams.__dataclass_fields__.values()}


def load_params() -> Params:
    """读 params.yaml(SSoT)。yaml 缺失 → Params.default()。"""
    if DEFAULT_YAML_PATH.exists():
        return Params.from_yaml(DEFAULT_YAML_PATH)
    return Params.default()
```

- [ ] **Step 3: 创建 `path2_apps/bo_only/dag_spec.py`**

```python
"""bo_only dag 声明 — 单节点 BODetector,无边。

拓扑:
  节点: bo(孤立 role,无边)
  边:   无

提供 path2_web 协议:eval_meta(end_role=bo, head_buffer=max(vol_baseline_period, total_window))。
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

from path2.dag.nodes import NodeSpec
from path2.dag.spec import PatternSpec
from path2.dag.engine import analyze as _analyze
from path2.atoms.breakout import BODetector

from .params import Params, load_params, DEFAULT_YAML_PATH    # noqa: F401 re-export


def build_pattern(params: Params) -> PatternSpec:
    """单节点 bo dag。"""
    nodes = (
        NodeSpec("bo",
                 BODetector(**params.bo_kwargs()),
                 render_grid="price"),
    )
    edges = ()
    return PatternSpec(
        pattern_id="bo_only",
        display_name="单点突破(bo)",
        nodes=nodes, edges=edges, root="bo",
    )


PATTERN_DAG = build_pattern(Params.default())


def analyze(df: pd.DataFrame, params: Optional[Params] = None):
    p = params or Params.default()
    return _analyze(build_pattern(p), df, p)


def matches(df: pd.DataFrame, params: Optional[Params] = None) -> bool:
    return len(analyze(df, params).matches) > 0


def eval_meta(params: Optional[Params] = None) -> dict:
    """评估元数据:bo 即买点,head_buffer = bo 自身 rolling lookback 最大值。"""
    p = params or Params.default()
    return {
        "end_role": "bo",
        "head_buffer_trading_days": max(
            p.bo.vol_baseline_period,
            p.bo.total_window,
        ),
    }
```

- [ ] **Step 4: 创建 `path2_apps/bo_only/__init__.py`**

```python
"""bo_only — 单 BODetector 节点的 dag 走势包(锚 pattern,服务多 pattern UI 找漏检场景)。

公开 API:
  build_pattern(params) -> PatternSpec
  PATTERN_DAG          : PatternSpec
  analyze(df, params)  -> AnalysisResult
  matches(df, params)  -> bool
  eval_meta(params) -> dict   # end_role=bo, head_buffer=max(vol_baseline_period, total_window)
  Params
  load_params() -> Params
  DEFAULT_YAML_PATH
"""
from .dag_spec import build_pattern, PATTERN_DAG, analyze, matches, eval_meta
from .params import Params, load_params, DEFAULT_YAML_PATH

__all__ = ["build_pattern", "PATTERN_DAG", "analyze", "matches", "eval_meta",
           "Params", "load_params", "DEFAULT_YAML_PATH"]
```

- [ ] **Step 5: 创建 `tests/path2_apps/__init__.py`(如不存在)**

```bash
mkdir -p tests/path2_apps && touch tests/path2_apps/__init__.py
```

- [ ] **Step 6: 创建 `tests/path2_apps/test_bo_only.py`**

```python
"""bo_only pattern 烟雾测试 — 单节点 dag 能扫小数据集出 bo events 与 matches。"""
import pandas as pd

from path2_apps.bo_only import (
    PATTERN_DAG, build_pattern, analyze, matches, eval_meta, Params, load_params,
)


def test_pattern_dag_single_bo_node_no_edges():
    """PATTERN_DAG 是单节点 bo + 零边。"""
    spec = PATTERN_DAG
    assert spec.pattern_id == "bo_only"
    assert [n.node_id for n in spec.nodes] == ["bo"]
    assert spec.edges == ()


def test_build_pattern_returns_consistent_spec():
    """build_pattern 与 PATTERN_DAG 同结构(模块级常量 = build_pattern(default))。"""
    spec = build_pattern(Params.default())
    assert spec.pattern_id == "bo_only"
    assert [n.node_id for n in spec.nodes] == ["bo"]


def test_eval_meta_protocol():
    """eval_meta 协议:end_role=bo, head_buffer=max(vol_baseline_period, total_window)."""
    meta = eval_meta()
    assert meta["end_role"] == "bo"
    p = Params.default()
    assert meta["head_buffer_trading_days"] == max(p.bo.vol_baseline_period, p.bo.total_window)


def test_load_params_uses_yaml(tmp_path, monkeypatch):
    """load_params 从同目录 params.yaml 读 — 实测 default 值与 yaml 一致。"""
    p = load_params()
    # yaml 内 bo.total_window=20(从我们写的 yaml 推),非 BoParams 默认 10
    assert p.bo.total_window == 20


def test_analyze_runs_without_error_on_synthetic_df():
    """analyze 能在合成 df 上跑完不抛(无论是否检出 events)。"""
    n = 100
    df = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=n),
        "open":  [10.0] * n, "high": [11.0] * n,
        "low":   [9.0]  * n, "close":[10.5] * n,
        "volume":[100.0]* n,
    })
    res = analyze(df)
    assert hasattr(res, "events") and hasattr(res, "matches")


def test_matches_bool_wrapper():
    """matches() 是 analyze().matches 非空的 bool。"""
    n = 50
    df = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=n),
        "open":  [10.0] * n, "high": [10.5] * n,
        "low":   [9.5]  * n, "close":[10.0] * n,
        "volume":[100.0]* n,
    })
    assert isinstance(matches(df), bool)
```

- [ ] **Step 7: 运行测试**

```bash
uv run pytest tests/path2_apps/test_bo_only.py -v
```

Expected: 6 PASS

- [ ] **Step 8: Commit**

```bash
git add path2_apps/bo_only/ tests/path2_apps/
git commit -m "feat(path2_apps): add bo_only pattern as anchor for missed-detection workflow"
```

---

## Task 2: discovery.py 加 eval_meta 验证闸 + log warning

**Files:**
- Modify: `path2_web/discovery.py` — `_discover` 加 eval_meta 校验
- Test: 修改/新增 `tests/path2_web/test_discovery_eval_meta_required.py`

**Interfaces:**
- Consumes: 现有 `_discover(apps_pkg) -> (modules, errors)`
- Produces: 修改 `_discover` 在已有 PATTERN_DAG 校验通过后,**新增**:
  - `getattr(mod, "eval_meta", None)` 必须 callable
  - `mod.eval_meta()` 不抛、返回 dict,且必含 `end_role: str` + `head_buffer_trading_days: int`
  - 任一不满足 → 不进 `modules`、加进 `errors[m.name]`、`logging.warning`
- 接口签名不变(仍返回 modules/errors 二元组)

- [ ] **Step 1: 创建 `tests/path2_web/test_discovery_eval_meta_required.py` 写红测试**

```python
"""discovery 闸:pattern 必须声明 eval_meta 协议,否则跳过 + warning。"""
import logging
import pytest

from path2_web.discovery import _discover, PatternRegistry


def test_real_apps_pass_gate():
    """真实 path2_apps 下的 bottom_breakout_burst 与 bo_only 都过闸。"""
    modules, errors = _discover("path2_apps")
    assert "bottom_breakout_burst" in modules
    assert "bo_only" in modules
    # 不应当因 eval_meta 闸误杀任一现有 pattern
    assert errors == {} or all("eval_meta" not in str(e) for e in errors.values()), errors


def test_fake_app_missing_eval_meta_is_filtered(tmp_path, monkeypatch, caplog):
    """fake_app 不声明 eval_meta → 不进 registry + log warning。"""
    # 用 tmp_path 仿造 path2_apps 包结构
    apps_dir = tmp_path / "fake_apps"
    apps_dir.mkdir()
    (apps_dir / "__init__.py").write_text("")
    sub = apps_dir / "no_meta"
    sub.mkdir()
    (sub / "__init__.py").write_text("")
    (sub / "dag_spec.py").write_text(
        "from path2.dag.nodes import NodeSpec\n"
        "from path2.dag.spec import PatternSpec\n"
        "from path2.atoms.breakout import BODetector\n"
        "PATTERN_DAG = PatternSpec(pattern_id='no_meta', display_name='x',\n"
        "                         nodes=(NodeSpec('bo', BODetector()),), edges=(), root='bo')\n"
        "def analyze(df, params=None): return None\n"
        "# 故意不定义 eval_meta\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    with caplog.at_level(logging.WARNING):
        modules, errors = _discover("fake_apps")
    assert "no_meta" not in modules
    assert "no_meta" in errors
    assert "eval_meta" in errors["no_meta"]
    assert any("eval_meta" in r.message for r in caplog.records)


def test_fake_app_eval_meta_missing_end_role(tmp_path, monkeypatch, caplog):
    """eval_meta 返回 dict 缺 end_role → 跳过 + warning。"""
    apps_dir = tmp_path / "fake_apps2"
    apps_dir.mkdir()
    (apps_dir / "__init__.py").write_text("")
    sub = apps_dir / "bad_meta"
    sub.mkdir()
    (sub / "__init__.py").write_text("")
    (sub / "dag_spec.py").write_text(
        "from path2.dag.nodes import NodeSpec\n"
        "from path2.dag.spec import PatternSpec\n"
        "from path2.atoms.breakout import BODetector\n"
        "PATTERN_DAG = PatternSpec(pattern_id='bad_meta', display_name='x',\n"
        "                         nodes=(NodeSpec('bo', BODetector()),), edges=(), root='bo')\n"
        "def analyze(df, params=None): return None\n"
        "def eval_meta(params=None): return {'head_buffer_trading_days': 60}   # 缺 end_role\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    with caplog.at_level(logging.WARNING):
        modules, errors = _discover("fake_apps2")
    assert "bad_meta" not in modules
    assert "bad_meta" in errors


def test_fake_app_eval_meta_missing_head_buffer(tmp_path, monkeypatch, caplog):
    """eval_meta 返回 dict 缺 head_buffer_trading_days → 跳过 + warning。"""
    apps_dir = tmp_path / "fake_apps3"
    apps_dir.mkdir()
    (apps_dir / "__init__.py").write_text("")
    sub = apps_dir / "bad_meta2"
    sub.mkdir()
    (sub / "__init__.py").write_text("")
    (sub / "dag_spec.py").write_text(
        "from path2.dag.nodes import NodeSpec\n"
        "from path2.dag.spec import PatternSpec\n"
        "from path2.atoms.breakout import BODetector\n"
        "PATTERN_DAG = PatternSpec(pattern_id='bad_meta2', display_name='x',\n"
        "                         nodes=(NodeSpec('bo', BODetector()),), edges=(), root='bo')\n"
        "def analyze(df, params=None): return None\n"
        "def eval_meta(params=None): return {'end_role': 'bo'}   # 缺 head_buffer\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    with caplog.at_level(logging.WARNING):
        modules, errors = _discover("fake_apps3")
    assert "bad_meta2" not in modules
    assert "bad_meta2" in errors


def test_fake_app_eval_meta_raises(tmp_path, monkeypatch, caplog):
    """eval_meta 调用抛异常 → 跳过 + warning。"""
    apps_dir = tmp_path / "fake_apps4"
    apps_dir.mkdir()
    (apps_dir / "__init__.py").write_text("")
    sub = apps_dir / "throw_meta"
    sub.mkdir()
    (sub / "__init__.py").write_text("")
    (sub / "dag_spec.py").write_text(
        "from path2.dag.nodes import NodeSpec\n"
        "from path2.dag.spec import PatternSpec\n"
        "from path2.atoms.breakout import BODetector\n"
        "PATTERN_DAG = PatternSpec(pattern_id='throw_meta', display_name='x',\n"
        "                         nodes=(NodeSpec('bo', BODetector()),), edges=(), root='bo')\n"
        "def analyze(df, params=None): return None\n"
        "def eval_meta(params=None): raise RuntimeError('boom')\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    with caplog.at_level(logging.WARNING):
        modules, errors = _discover("fake_apps4")
    assert "throw_meta" not in modules
    assert "throw_meta" in errors
```

- [ ] **Step 2: 运行测试,确认红失败**

```bash
uv run pytest tests/path2_web/test_discovery_eval_meta_required.py -v
```

Expected: 3-5 红测试 FAIL(目前 _discover 不验证 eval_meta)

- [ ] **Step 3: 改 `path2_web/discovery.py::_discover` 加 eval_meta 闸**

替换 `path2_web/discovery.py` 整体:

```python
"""pattern 发现:扫 path2_apps/*/ 找含 PATTERN_DAG + eval_meta 的包,建 {pattern_id: module} 注册表。

新 app 必须:
1. 模块级常量 PATTERN_DAG
2. callable analyze(df, params=None)
3. callable eval_meta(params=None) -> {"end_role": str, "head_buffer_trading_days": int}

任一缺失 / 报错 → 跳过 + log warning,/patterns 不返回。
"""
from __future__ import annotations

import importlib
import logging
import pkgutil
import sys

log = logging.getLogger(__name__)


def _validate_eval_meta(mod, name: str) -> str | None:
    """检查 mod 满足 eval_meta 协议;返回错误说明 str(None=OK)。"""
    fn = getattr(mod, "eval_meta", None)
    if not callable(fn):
        return "missing callable eval_meta()"
    load_params = getattr(mod, "load_params", None)
    try:
        meta = fn(load_params()) if callable(load_params) else fn()
    except Exception as e:           # noqa: BLE001
        return f"eval_meta() raised: {type(e).__name__}: {e}"
    if not isinstance(meta, dict):
        return f"eval_meta() returned non-dict: {type(meta).__name__}"
    if "end_role" not in meta or not isinstance(meta["end_role"], str):
        return "eval_meta() missing or non-str 'end_role'"
    if ("head_buffer_trading_days" not in meta
            or not isinstance(meta["head_buffer_trading_days"], int)):
        return "eval_meta() missing or non-int 'head_buffer_trading_days'"
    return None


def _discover(apps_pkg: str):
    """返回 (modules: {pattern_id: module}, errors: {sub_pkg_name: err_str})。"""
    modules, errors = {}, {}
    try:
        pkg = importlib.import_module(apps_pkg)
    except Exception as e:
        return modules, {apps_pkg: f"{type(e).__name__}: {e}"}
    for m in pkgutil.iter_modules(pkg.__path__):
        if not m.ispkg:
            continue
        try:
            mod = importlib.import_module(f"{apps_pkg}.{m.name}.dag_spec")
            dag = getattr(mod, "PATTERN_DAG", None)
            if dag is None:
                continue
            err = _validate_eval_meta(mod, m.name)
            if err:
                errors[m.name] = f"eval_meta gate: {err}"
                log.warning("pattern %r skipped: %s", m.name, err)
                continue
            modules[dag.pattern_id] = mod
        except Exception as e:
            errors[m.name] = f"{type(e).__name__}: {e}"
    return modules, errors


class PatternRegistry:
    """缓存含 PATTERN_DAG + 合规 eval_meta 的 app 模块。
    refresh 重扫;invalidate 弹某 pattern 子模块缓存。"""

    def __init__(self, apps_pkg: str = "path2_apps"):
        self.apps_pkg = apps_pkg
        self._modules: dict = {}
        self._errors: dict = {}
        self.refresh()

    def refresh(self) -> None:
        importlib.invalidate_caches()
        self._modules, self._errors = _discover(self.apps_pkg)

    def ids(self) -> list:
        return sorted(self._modules)

    def errors(self) -> dict:
        return dict(self._errors)

    def get(self, pattern_id: str):
        return self._modules.get(pattern_id)

    def module_path(self, pattern_id: str):
        mod = self._modules.get(pattern_id)
        return mod.__name__ if mod else None

    def invalidate(self, pattern_id: str) -> None:
        mod = self._modules.get(pattern_id)
        if mod is None:
            return
        app_prefix = mod.__name__.rsplit(".", 1)[0]
        for name in [n for n in sys.modules if n == app_prefix or n.startswith(app_prefix + ".")]:
            sys.modules.pop(name, None)
        self.refresh()
```

- [ ] **Step 4: 运行测试,确认绿**

```bash
uv run pytest tests/path2_web/test_discovery_eval_meta_required.py tests/path2_web/test_discovery.py -v
```

Expected: 全 PASS;`test_real_apps_pass_gate` 验证 bottom_breakout_burst + bo_only 都过闸

- [ ] **Step 5: 跑全套 path2_web 测试确认无回归**

```bash
uv run pytest tests/path2_web/ -v
```

Expected: 多数 PASS;预期失败=后续 task 才修的(已有 test_scan/test_api/test_eval_meta_resolve 等),记录失败列表但不阻塞本 task

- [ ] **Step 6: Commit**

```bash
git add path2_web/discovery.py tests/path2_web/test_discovery_eval_meta_required.py
git commit -m "feat(discovery): enforce eval_meta protocol as iron rule"
```

---

## Task 3: serialize.py 加多 pattern 投影助手

**Files:**
- Modify: `path2_web/serialize.py` — 加 `serialize_per_pattern_result(res, end_role, label_horizon, win, start_ts, end_ts)` 助手
- Test: 新建 `tests/path2_web/test_serialize_multi.py`

**Interfaces:**
- Consumes: `serialize_analysis(res)`、`summarize(res)`、`path2.eval.match_forward_returns`
- Produces:
  ```python
  def serialize_per_pattern_result(res, end_role: str, label_horizon: int,
                                    win: pd.DataFrame,
                                    start_ts: pd.Timestamp,
                                    end_ts:   pd.Timestamp) -> dict:
      """单股单 pattern 结果投影。

      返回 {"summary": dict, "analysis": dict, "max_forward_return": float | None}。
      - analysis.events:全集照旧(含缓冲段)
      - analysis.matches:按 [start_ts, end_ts] 过滤 + 注入 forward_return
      - summary["matches"]:窗内 match 数(改写 summarize 结果的 "matches" 键)
      - max_forward_return:max over matches 中非 None 的 forward_return;空 / 全 None → None
      """
  ```

- [ ] **Step 1: 创建 `tests/path2_web/test_serialize_multi.py` 写红测试**

```python
"""serialize_per_pattern_result — 单股单 pattern 投影,加 max_forward_return。"""
from pathlib import Path
import pandas as pd
import pytest

from path2_web.serialize import serialize_per_pattern_result
from path2_apps.bottom_breakout_burst import build_pattern, Params, eval_meta
from path2.dag.engine import analyze as engine_analyze


PKL_DIR = Path("datasets/pkls")


def _pick_pkl_with_match() -> Path:
    """从 datasets/pkls 找一只 bbb 默认参数下能命中的股(若无,返 None,测试 skip)。"""
    if not PKL_DIR.exists():
        return None
    spec = build_pattern(Params.default())
    for p in sorted(PKL_DIR.glob("*.pkl"))[:200]:    # 限制扫描数避免慢
        df = pd.read_pickle(p)
        if len(df) < 200:
            continue
        win = df.iloc[-300:]
        res = engine_analyze(spec, win, Params.default())
        if len(res.matches) > 0:
            return p
    return None


def test_per_pattern_result_schema():
    """返回字典含 summary/analysis/max_forward_return 三键,分别是 dict/dict/float|None。"""
    p = _pick_pkl_with_match()
    if p is None:
        pytest.skip("no pkl with matches; skip")
    df = pd.read_pickle(p)
    spec = build_pattern(Params.default())
    win = df.iloc[-300:].reset_index(drop=True)
    res = engine_analyze(spec, win, Params.default())
    meta = eval_meta()
    start_ts = pd.to_datetime(win["date"].iat[len(win) // 2])
    end_ts   = pd.to_datetime(win["date"].iat[-1])
    out = serialize_per_pattern_result(res, end_role=meta["end_role"],
                                       label_horizon=5, win=win,
                                       start_ts=start_ts, end_ts=end_ts)
    assert set(out.keys()) == {"summary", "analysis", "max_forward_return"}
    assert isinstance(out["summary"], dict)
    assert isinstance(out["analysis"], dict)
    assert out["max_forward_return"] is None or isinstance(out["max_forward_return"], float)


def test_per_pattern_events_full_set_kept():
    """events 全集照旧(不按窗过滤),matches 按窗过滤。"""
    p = _pick_pkl_with_match()
    if p is None:
        pytest.skip("no pkl with matches; skip")
    df = pd.read_pickle(p)
    spec = build_pattern(Params.default())
    win = df.iloc[-300:].reset_index(drop=True)
    res = engine_analyze(spec, win, Params.default())
    meta = eval_meta()
    # 极窄过滤窗:只允许 win 末尾 5 bar 的 match
    start_ts = pd.to_datetime(win["date"].iat[-5])
    end_ts   = pd.to_datetime(win["date"].iat[-1])
    out = serialize_per_pattern_result(res, end_role=meta["end_role"],
                                       label_horizon=5, win=win,
                                       start_ts=start_ts, end_ts=end_ts)
    # events 全集与原 res.events 一致(数量)
    assert len(out["analysis"]["events"]) == len(res.events)
    # matches 是 res.matches 子集
    assert len(out["analysis"]["matches"]) <= len(res.matches)


def test_max_forward_return_null_when_matches_empty():
    """matches 过滤后空 → max_forward_return = None。"""
    p = _pick_pkl_with_match()
    if p is None:
        pytest.skip("no pkl with matches; skip")
    df = pd.read_pickle(p)
    spec = build_pattern(Params.default())
    win = df.iloc[-300:].reset_index(drop=True)
    res = engine_analyze(spec, win, Params.default())
    meta = eval_meta()
    # 完全在 win 之外的过滤窗 → 0 match 入选
    start_ts = pd.to_datetime("1900-01-01")
    end_ts   = pd.to_datetime("1900-01-02")
    out = serialize_per_pattern_result(res, end_role=meta["end_role"],
                                       label_horizon=5, win=win,
                                       start_ts=start_ts, end_ts=end_ts)
    assert out["analysis"]["matches"] == []
    assert out["max_forward_return"] is None


def test_summary_matches_key_reflects_window():
    """summary['matches'] 是窗内 match 数(非全集)。"""
    p = _pick_pkl_with_match()
    if p is None:
        pytest.skip("no pkl with matches; skip")
    df = pd.read_pickle(p)
    spec = build_pattern(Params.default())
    win = df.iloc[-300:].reset_index(drop=True)
    res = engine_analyze(spec, win, Params.default())
    meta = eval_meta()
    start_ts = pd.to_datetime("1900-01-01")
    end_ts   = pd.to_datetime("1900-01-02")
    out = serialize_per_pattern_result(res, end_role=meta["end_role"],
                                       label_horizon=5, win=win,
                                       start_ts=start_ts, end_ts=end_ts)
    assert out["summary"]["matches"] == 0
```

- [ ] **Step 2: 运行测试,确认红失败**

```bash
uv run pytest tests/path2_web/test_serialize_multi.py -v
```

Expected: `ImportError: cannot import name 'serialize_per_pattern_result'`

- [ ] **Step 3: 在 `path2_web/serialize.py` 末尾追加 `serialize_per_pattern_result`**

文件末尾追加:

```python
def serialize_per_pattern_result(res, end_role: str, label_horizon: int,
                                  win, start_ts, end_ts) -> dict:
    """单股单 pattern 投影,服务多 pattern worker。

    args:
        res: AnalysisResult(已 analyze 完整 buf_win)
        end_role: pattern 的买点 role(从 eval_meta 取)
        label_horizon: 前瞻收益天数
        win: 已切好的 DataFrame(含 date 列 + OHLC)
        start_ts/end_ts: pd.Timestamp,严格窗左右边界(含)

    返回 {summary, analysis, max_forward_return}:
      - analysis.events: 全集照旧(含缓冲段;K 线灰色层数据源)
      - analysis.matches: 仅保留 end_role event 起点 ∈ [start_ts, end_ts] 的 match,
                          每条注入 forward_return
      - summary["matches"]: 窗内 match 数(覆写)
      - max_forward_return: max over filtered matches 中非 None 的 forward_return;
                            空 / 全 None → None
    """
    from path2.eval import match_forward_returns

    ret_by_id: dict = {}
    for m in res.matches:
        ev = m.role_index[end_role]
        buy_date = win["date"].iat[ev.start_idx]
        if not (start_ts <= buy_date <= end_ts):
            continue
        ret_by_id[m.event_id] = match_forward_returns(
            m, end_role, win, [label_horizon])[label_horizon]
    analysis = serialize_analysis(res)
    analysis["matches"] = [
        {**md, "forward_return": ret_by_id[md["event_id"]]}
        for md in analysis["matches"] if md["event_id"] in ret_by_id
    ]
    summary = summarize(res)
    summary["matches"] = len(analysis["matches"])

    rets = [md["forward_return"] for md in analysis["matches"]
            if md["forward_return"] is not None]
    max_ret = max(rets) if rets else None

    return {"summary": summary, "analysis": analysis, "max_forward_return": max_ret}
```

- [ ] **Step 4: 运行测试,确认绿**

```bash
uv run pytest tests/path2_web/test_serialize_multi.py -v
```

Expected: 4 PASS (有 skip 表示数据集缺,但不能 FAIL;如本机已无 datasets/pkls,允许 skip)

- [ ] **Step 5: Commit**

```bash
git add path2_web/serialize.py tests/path2_web/test_serialize_multi.py
git commit -m "feat(serialize): add serialize_per_pattern_result for multi-pattern worker"
```

---

## Task 4: scan.py 多 pattern worker + run_scan + 扁平 outputs

**Files:**
- Modify: `path2_web/scan.py` — 几乎重写整个文件(保留 ScanCancelled / TRADING_TO_CALENDAR_RATIO / 老 analyze_single)
- Test: 新建 `tests/path2_web/test_scan_multi_pattern.py`;`tests/path2_web/test_scan.py` 和 `test_scan_buffered.py` 不再适用(改造后旧单 pattern 接口已删除),task 末 Step 标记跳过

**Interfaces:**
- Produces:
  ```python
  def _scan_ticker_multi(pkl_path: str, module_paths: dict,
                         start_date: str, end_date: str,
                         buf_start: str, buf_end: str,
                         end_roles: dict, label_horizon: int) -> tuple:
      """返回 (symbol, per_pattern_dict | None, err | None)。
      per_pattern_dict 为 None = 该股不入选并集(所有 pattern 0 match)。"""

  def run_scan_multi(*, data_dir,
                     pattern_specs_json: dict,      # pid -> serialized spec(写入文件)
                     module_paths: dict,            # pid -> "path2_apps.bo_only"
                     pattern_ids: list,             # 用于校验 + 顺序
                     end_roles: dict,               # pid -> end_role
                     head_buffer_trading_days: int, # 已是 max
                     label_horizon: int,
                     start_date, end_date, workers, ticker_regex, scan_ts,
                     outputs_root="outputs/path2_web", on_progress=lambda *a: None,
                     executor_factory=None, cancel_event=None, save_event=None) -> dict:
      """落 outputs/path2_web/scans/<scan_ts>.json 的 MultiScanResultFile。"""

  def list_scans_flat(outputs_root: str = "outputs/path2_web") -> list[dict]:
      """[{scan_ts, pattern_ids, hits, total, size, partial}, ...],按 scan_ts 倒序。"""

  def load_scan_flat(scan_ts: str, outputs_root: str = "outputs/path2_web") -> dict:
      """读 outputs_root/scans/<scan_ts>.json。"""

  def delete_scan_flat(scan_ts: str, outputs_root: str = "outputs/path2_web") -> None:
      """删 outputs_root/scans/<scan_ts>.json;不存在 → FileNotFoundError。"""
  ```
- 删除:`_scan_ticker`、`analyze_single` 中 `end_role=None` 分支、`run_scan` 现签名、`write_result_file`、`list_scans/load_scan/delete_scan`(per-pattern 路径)

- [ ] **Step 1: 创建 `tests/path2_web/test_scan_multi_pattern.py` 写红测试(用线程池 + tmp_path)**

```python
"""多 pattern 同扫:落 MultiScanResultFile + 并集语义 + per_pattern 字典键集等于 pattern_ids。"""
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import pytest

from path2_web.scan import run_scan_multi, list_scans_flat, load_scan_flat, delete_scan_flat
from path2_web.serialize import serialize_pattern
from path2_apps.bottom_breakout_burst import build_pattern as build_bbb, Params as PBbb
from path2_apps.bo_only import build_pattern as build_bo, Params as PBo


PKL_DIR = Path("datasets/pkls")


@pytest.fixture
def tiny_pkls(tmp_path):
    """造 2 只合成 pkl 放在 tmp_path/data。"""
    data = tmp_path / "data"
    data.mkdir()
    n = 200
    base = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=n),
        "open":  [10.0]*n, "high": [11.0]*n,
        "low":   [9.0]*n,  "close":[10.5]*n,
        "volume":[100.0]*n,
    })
    base.to_pickle(data / "AAA.pkl")
    base.to_pickle(data / "BBB.pkl")
    return str(data)


def test_multi_scan_falls_into_flat_dir(tmp_path, tiny_pkls):
    """落盘到 outputs_root/scans/<ts>.json(非 per-pattern 子目录)。"""
    outputs = tmp_path / "out"
    specs = {
        "bo_only": serialize_pattern(build_bo(PBo.default())),
        "bottom_breakout_burst": serialize_pattern(build_bbb(PBbb.default())),
    }
    module_paths = {"bo_only": "path2_apps.bo_only",
                    "bottom_breakout_burst": "path2_apps.bottom_breakout_burst"}
    end_roles = {"bo_only": "bo", "bottom_breakout_burst": "tb"}
    run_scan_multi(
        data_dir=tiny_pkls,
        pattern_specs_json=specs, module_paths=module_paths,
        pattern_ids=["bo_only", "bottom_breakout_burst"],
        end_roles=end_roles, head_buffer_trading_days=120, label_horizon=20,
        start_date="2024-02-01", end_date="2024-06-30",
        workers=2, ticker_regex=None, scan_ts="20260627T120000",
        outputs_root=str(outputs),
        executor_factory=lambda w: ThreadPoolExecutor(max_workers=w),
    )
    flat_file = outputs / "scans" / "20260627T120000.json"
    assert flat_file.exists()
    blob = json.loads(flat_file.read_text())
    assert blob["pattern_ids"] == ["bo_only", "bottom_breakout_burst"]
    assert set(blob["per_pattern"]) == {"bo_only", "bottom_breakout_burst"}


def test_multi_scan_each_per_pattern_has_full_keys(tmp_path, tiny_pkls):
    """results 每行 per_pattern 字典键集 ≡ pattern_ids。"""
    outputs = tmp_path / "out"
    specs = {
        "bo_only": serialize_pattern(build_bo(PBo.default())),
        "bottom_breakout_burst": serialize_pattern(build_bbb(PBbb.default())),
    }
    module_paths = {"bo_only": "path2_apps.bo_only",
                    "bottom_breakout_burst": "path2_apps.bottom_breakout_burst"}
    end_roles = {"bo_only": "bo", "bottom_breakout_burst": "tb"}
    result = run_scan_multi(
        data_dir=tiny_pkls,
        pattern_specs_json=specs, module_paths=module_paths,
        pattern_ids=["bo_only", "bottom_breakout_burst"],
        end_roles=end_roles, head_buffer_trading_days=120, label_horizon=20,
        start_date="2024-02-01", end_date="2024-06-30",
        workers=2, ticker_regex=None, scan_ts="20260627T120001",
        outputs_root=str(outputs),
        executor_factory=lambda w: ThreadPoolExecutor(max_workers=w),
    )
    # 即便合成数据 0 命中,结果文件仍正确 schema
    for r in result["results"]:
        assert set(r["per_pattern"]) == {"bo_only", "bottom_breakout_burst"}


def test_list_scans_flat_returns_pattern_ids(tmp_path, tiny_pkls):
    """list_scans_flat 返回的 entry 含 pattern_ids 字段。"""
    outputs = tmp_path / "out"
    specs = {"bo_only": serialize_pattern(build_bo(PBo.default()))}
    module_paths = {"bo_only": "path2_apps.bo_only"}
    end_roles = {"bo_only": "bo"}
    run_scan_multi(
        data_dir=tiny_pkls,
        pattern_specs_json=specs, module_paths=module_paths,
        pattern_ids=["bo_only"],
        end_roles=end_roles, head_buffer_trading_days=63, label_horizon=20,
        start_date="2024-02-01", end_date="2024-06-30",
        workers=2, ticker_regex=None, scan_ts="20260627T120002",
        outputs_root=str(outputs),
        executor_factory=lambda w: ThreadPoolExecutor(max_workers=w),
    )
    rows = list_scans_flat(str(outputs))
    assert any(r["scan_ts"] == "20260627T120002" and r["pattern_ids"] == ["bo_only"]
               for r in rows)


def test_load_scan_flat_round_trip(tmp_path, tiny_pkls):
    """run_scan_multi → load_scan_flat round-trip 字典等价。"""
    outputs = tmp_path / "out"
    specs = {"bo_only": serialize_pattern(build_bo(PBo.default()))}
    module_paths = {"bo_only": "path2_apps.bo_only"}
    end_roles = {"bo_only": "bo"}
    saved = run_scan_multi(
        data_dir=tiny_pkls,
        pattern_specs_json=specs, module_paths=module_paths,
        pattern_ids=["bo_only"],
        end_roles=end_roles, head_buffer_trading_days=63, label_horizon=20,
        start_date="2024-02-01", end_date="2024-06-30",
        workers=2, ticker_regex=None, scan_ts="20260627T120003",
        outputs_root=str(outputs),
        executor_factory=lambda w: ThreadPoolExecutor(max_workers=w),
    )
    loaded = load_scan_flat("20260627T120003", str(outputs))
    assert loaded["pattern_ids"] == saved["pattern_ids"]
    assert loaded["scan"]["scan_ts"] == saved["scan"]["scan_ts"]


def test_delete_scan_flat(tmp_path, tiny_pkls):
    """delete_scan_flat 删除文件;再删抛 FileNotFoundError。"""
    outputs = tmp_path / "out"
    specs = {"bo_only": serialize_pattern(build_bo(PBo.default()))}
    module_paths = {"bo_only": "path2_apps.bo_only"}
    end_roles = {"bo_only": "bo"}
    run_scan_multi(
        data_dir=tiny_pkls,
        pattern_specs_json=specs, module_paths=module_paths,
        pattern_ids=["bo_only"],
        end_roles=end_roles, head_buffer_trading_days=63, label_horizon=20,
        start_date="2024-02-01", end_date="2024-06-30",
        workers=2, ticker_regex=None, scan_ts="20260627T120004",
        outputs_root=str(outputs),
        executor_factory=lambda w: ThreadPoolExecutor(max_workers=w),
    )
    delete_scan_flat("20260627T120004", str(outputs))
    assert not (outputs / "scans" / "20260627T120004.json").exists()
    with pytest.raises(FileNotFoundError):
        delete_scan_flat("20260627T120004", str(outputs))


def test_multi_scan_buf_start_takes_max_head_buffer(tmp_path, tiny_pkls):
    """head_buffer_trading_days 进 win_start = start - head_buf * 1.65 日历日。"""
    outputs = tmp_path / "out"
    specs = {
        "bo_only": serialize_pattern(build_bo(PBo.default())),
        "bottom_breakout_burst": serialize_pattern(build_bbb(PBbb.default())),
    }
    module_paths = {"bo_only": "path2_apps.bo_only",
                    "bottom_breakout_burst": "path2_apps.bottom_breakout_burst"}
    end_roles = {"bo_only": "bo", "bottom_breakout_burst": "tb"}
    saved = run_scan_multi(
        data_dir=tiny_pkls,
        pattern_specs_json=specs, module_paths=module_paths,
        pattern_ids=["bo_only", "bottom_breakout_burst"],
        end_roles=end_roles, head_buffer_trading_days=120, label_horizon=20,
        start_date="2024-02-01", end_date="2024-06-30",
        workers=2, ticker_regex=None, scan_ts="20260627T120005",
        outputs_root=str(outputs),
        executor_factory=lambda w: ThreadPoolExecutor(max_workers=w),
    )
    assert saved["scan"]["win_start"] < "2024-02-01"
    assert saved["scan"]["label_horizon"] == 20
    assert saved["scan"]["win_end"] > "2024-06-30"
```

- [ ] **Step 2: 跑测试确认红失败**

```bash
uv run pytest tests/path2_web/test_scan_multi_pattern.py -v
```

Expected: `ImportError: cannot import name 'run_scan_multi'`

- [ ] **Step 3: 改 `path2_web/scan.py` — 整体重写**

替换 `path2_web/scan.py` 整体:

```python
"""并发扫描(多 pattern):每只股读 pkl 一次 → slice_window → 对每 pattern analyze → 聚合 → 落盘。

铁律:所有 pattern 必须经 discovery eval_meta 闸,故扫描永远走 buffered 路径,
end_role/head_buffer/label_horizon 三者永远非 None。删除旧非缓冲分支。

结果文件 schema MultiScanResultFile(spec §3.1):
  {pattern_ids, per_pattern: {pid: {pattern_spec, end_role}},
   scan: {...win_*/label_horizon/scanned/hits/errors/...},
   results: [{symbol, per_pattern: {pid: {summary, analysis, max_forward_return}}}, ...]}
"""
from __future__ import annotations

import importlib
import json
import os
import re
import signal
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

from path2_web.data import slice_window
from path2_web.serialize import serialize_per_pattern_result

TRADING_TO_CALENDAR_RATIO = 1.65   # 交易日 → 日历日(与 scripts/path2_eval_bottom_breakout_burst.py 同源)


class ScanCancelled(Exception):
    """run_scan_multi 检测到 cancel_event 已 set,主动退出。"""


def _scan_ticker_multi(pkl_path, module_paths, start_date, end_date,
                       buf_start, buf_end, end_roles, label_horizon):
    """单股多 pattern worker(模块级,ProcessPool pickle 安全)。

    返回 (symbol, per_pattern_dict | None, err | None):
      per_pattern_dict 为 None = 该股不入选并集(所有 pattern matches 全空)。
      err 非 None = 该股扫描异常,errors++,不进 results。

    每股 read_pkl 一次,buf_win 切一次,然后逐 pattern import+analyze+投影。
    """
    symbol = Path(pkl_path).stem
    try:
        df = pd.read_pickle(pkl_path)
        win = slice_window(df, buf_start, buf_end)
        if len(win) == 0:
            return (symbol, None, None)
        start_ts = pd.to_datetime(start_date)
        end_ts   = pd.to_datetime(end_date)

        per_pattern: dict = {}
        any_match = False
        for pid, mod_path in module_paths.items():
            mod = importlib.import_module(mod_path)
            _load = getattr(mod, "load_params", None)
            res = mod.analyze(win, _load() if callable(_load) else None)
            out = serialize_per_pattern_result(
                res, end_role=end_roles[pid], label_horizon=label_horizon,
                win=win, start_ts=start_ts, end_ts=end_ts)
            per_pattern[pid] = out
            if out["summary"]["matches"] > 0:
                any_match = True

        if not any_match:
            return (symbol, None, None)
        return (symbol, per_pattern, None)
    except Exception as e:           # noqa: BLE001
        return (symbol, None, f"{type(e).__name__}: {e}")


def _aggregate_multi(results_iter, total: int, pattern_ids: list,
                     on_progress) -> dict:
    """聚合 worker 结果(纯逻辑,不起进程)。on_progress(scanned,total,hits,errors) 每 ticker 调一次。"""
    results, scanned, hits, errors = [], 0, 0, 0
    for symbol, per_pattern, err in results_iter:
        scanned += 1
        if err is not None:
            errors += 1
        elif per_pattern is not None:
            hits += 1
            results.append({"symbol": symbol, "per_pattern": per_pattern})
        on_progress(scanned, total, hits, errors)
    results.sort(key=lambda r: r["symbol"])
    return {"results": results, "scanned": scanned, "hits": hits, "errors": errors}


def _list_pkls(data_dir: str, ticker_regex):
    pkls = sorted(Path(data_dir).glob("*.pkl"))
    if ticker_regex:
        pat = re.compile(ticker_regex)
        pkls = [p for p in pkls if pat.match(p.stem)]
    return pkls


def run_scan_multi(*, data_dir,
                   pattern_specs_json: dict,
                   module_paths: dict,
                   pattern_ids: list,
                   end_roles: dict,
                   head_buffer_trading_days: int,
                   label_horizon: int,
                   start_date, end_date, workers, ticker_regex, scan_ts,
                   outputs_root="outputs/path2_web",
                   on_progress=lambda *a: None,
                   executor_factory=None,
                   cancel_event=None, save_event=None) -> dict:
    """并发扫 data_dir/*.pkl,多 pattern 同时跑 + 落盘 MultiScanResultFile(spec §3.1)。

    cancel_event set + save_event set → break 优雅退出(已聚结果落盘,scan.partial=True);
    cancel_event set 但 save_event 未 set → 抛 ScanCancelled。
    """
    if executor_factory is None:
        executor_factory = lambda w: ProcessPoolExecutor(max_workers=w)
    pkls = _list_pkls(data_dir, ticker_regex)
    total = len(pkls)

    start_ts, end_ts = pd.to_datetime(start_date), pd.to_datetime(end_date)
    buf_start = start_ts - pd.Timedelta(days=round(head_buffer_trading_days * TRADING_TO_CALENDAR_RATIO))
    buf_end   = end_ts   + pd.Timedelta(days=round(label_horizon * TRADING_TO_CALENDAR_RATIO))
    win_start, win_end = str(buf_start.date()), str(buf_end.date())

    def _iter():
        ex = executor_factory(max(1, workers))
        try:
            futs = [ex.submit(_scan_ticker_multi, str(p), module_paths,
                              start_date, end_date, win_start, win_end,
                              end_roles, label_horizon) for p in pkls]
            for fut in as_completed(futs):
                if cancel_event is not None and cancel_event.is_set():
                    # 强制终止 worker(同老 run_scan 套路:SIGKILL + waitpid 死亡确认)
                    pids = [p.pid for p in list(getattr(ex, "_processes", {}).values())
                            if p.pid is not None]
                    for pid in pids:
                        try:
                            os.kill(pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                    ex.shutdown(wait=False, cancel_futures=True)
                    for pid in pids:
                        try:
                            os.waitpid(pid, 0)
                        except ChildProcessError:
                            pass
                    if save_event is not None and save_event.is_set():
                        break
                    raise ScanCancelled()
                yield fut.result()
        finally:
            ex.shutdown(wait=False)

    agg = _aggregate_multi(_iter(), total, pattern_ids, on_progress)
    partial = save_event is not None and save_event.is_set()
    per_pattern_meta = {pid: {"pattern_spec": pattern_specs_json[pid],
                              "end_role": end_roles[pid]}
                        for pid in pattern_ids}
    result = {
        "pattern_ids": pattern_ids,
        "per_pattern": per_pattern_meta,
        "scan": {
            "scan_ts": scan_ts,
            "start_date": str(start_date), "end_date": str(end_date),
            "workers": workers,
            "scanned": agg["scanned"], "hits": agg["hits"], "errors": agg["errors"],
            "dataset_dir": str(data_dir), "params": "default",
            "win_start": win_start, "win_end": win_end,
            "label_horizon": label_horizon,
            "partial": partial,
        },
        "results": agg["results"],
    }
    write_result_file_flat(result, scan_ts, outputs_root)
    return result


def write_result_file_flat(result: dict, scan_ts: str, outputs_root: str) -> Path:
    out_dir = Path(outputs_root) / "scans"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{scan_ts}.json"
    path.write_text(json.dumps(result, ensure_ascii=False))
    return path


def list_scans_flat(outputs_root: str = "outputs/path2_web") -> list[dict]:
    """[{scan_ts, pattern_ids, hits, total, size, partial}, ...],按 scan_ts 倒序。
    单文件 json 读 pattern_ids / scan.hits / scan.scanned / scan.partial;读不出 → 全 None/False。"""
    d = Path(outputs_root) / "scans"
    if not d.exists():
        return []
    rows = []
    for p in d.glob("*.json"):
        try:
            blob = json.loads(p.read_text())
            pattern_ids = blob.get("pattern_ids", [])
            scan_section = blob["scan"]
            hits = scan_section.get("hits")
            total = scan_section.get("scanned")
            partial = bool(scan_section.get("partial", False))
        except (json.JSONDecodeError, KeyError, OSError):
            pattern_ids, hits, total, partial = [], None, None, False
        rows.append({"scan_ts": p.stem, "pattern_ids": pattern_ids,
                     "hits": hits, "total": total,
                     "size": p.stat().st_size, "partial": partial})
    rows.sort(key=lambda r: r["scan_ts"], reverse=True)
    return rows


def load_scan_flat(scan_ts: str, outputs_root: str = "outputs/path2_web") -> dict:
    path = Path(outputs_root) / "scans" / f"{scan_ts}.json"
    return json.loads(path.read_text())


def delete_scan_flat(scan_ts: str, outputs_root: str = "outputs/path2_web") -> None:
    """删 outputs_root/scans/<scan_ts>.json;不存在 → FileNotFoundError(原生)。"""
    path = Path(outputs_root) / "scans" / f"{scan_ts}.json"
    path.unlink()
```

- [ ] **Step 4: 跑新测试,确认绿**

```bash
uv run pytest tests/path2_web/test_scan_multi_pattern.py -v
```

Expected: 6 PASS

- [ ] **Step 5: 删除旧单 pattern 测试(已不适用)**

```bash
git rm tests/path2_web/test_scan.py tests/path2_web/test_scan_buffered.py
```

- [ ] **Step 6: Commit**

```bash
git add path2_web/scan.py tests/path2_web/test_scan_multi_pattern.py
git commit -m "feat(scan): multi-pattern worker + flat outputs/scans dir"
```

---

## Task 5: api.py 改造 routes — POST /scan 接受 pattern_ids、/scans 扁平、删 fallback

**Files:**
- Modify: `path2_web/api.py`(几乎重写整个 build_router)
- Test: 新建 `tests/path2_web/test_api_scan_multi.py`、`tests/path2_web/test_scans_route_flat.py`
- 现有 `tests/path2_web/test_api.py` 部分用例失效(per-pattern 路径)→ 同 task 内修

**Interfaces:**
- Produces 路由:
  - `POST /scan` body `{pattern_ids: List[str], start_date, end_date, workers, ticker_regex, label_horizon}` → `{scan_id}`
  - `GET /scans/` → `[ScanHistoryEntry]`(每 entry 含 `pattern_ids`)
  - `GET /scans/{scan_ts}` → MultiScanResultFile
  - `DELETE /scans/{scan_ts}` → `{ok: true}`
  - `GET /diagnose?pattern_id&symbol&start&end` 不变
  - `GET /preview?pattern_id&symbol&start&end&label_horizon` body 不变(仍单 pid)
  - `GET /patterns`、`GET /ohlc`、`GET /config`、`PUT /config`、`POST /scan/{id}/cancel`、`GET /scan/{id}/stream` 不变
- 删除:`/scans/{pid}`、`/scans/{pid}/{ts}`、`DELETE /scans/{pid}/{ts}` 三条
- `resolve_eval_meta` → `require_eval_meta(mod)` 缺时 raise(铁律下 discovery 闸过,api 不应见 None)

- [ ] **Step 1: 创建 `tests/path2_web/test_scans_route_flat.py` 写测试**

```python
"""扁平 /scans/、/scans/{ts}、DELETE /scans/{ts} 路由。"""
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from path2_web.app import create_app
from path2_web.scan import run_scan_multi
from path2_web.serialize import serialize_pattern
from path2_apps.bo_only import build_pattern as build_bo, Params as PBo


@pytest.fixture
def app_with_one_scan(tmp_path):
    """造 1 个 multi-scan 结果文件 + TestClient。"""
    # 造 2 只合成 pkl
    data = tmp_path / "data"
    data.mkdir()
    n = 200
    base = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=n),
        "open": [10.0]*n, "high": [11.0]*n,
        "low":  [9.0]*n,  "close":[10.5]*n, "volume":[100.0]*n,
    })
    base.to_pickle(data / "AAA.pkl")
    base.to_pickle(data / "BBB.pkl")

    outputs = tmp_path / "out"
    specs = {"bo_only": serialize_pattern(build_bo(PBo.default()))}
    run_scan_multi(
        data_dir=str(data),
        pattern_specs_json=specs,
        module_paths={"bo_only": "path2_apps.bo_only"},
        pattern_ids=["bo_only"],
        end_roles={"bo_only": "bo"},
        head_buffer_trading_days=63, label_horizon=20,
        start_date="2024-02-01", end_date="2024-06-30",
        workers=1, ticker_regex=None, scan_ts="20260627T130000",
        outputs_root=str(outputs),
        executor_factory=lambda w: ThreadPoolExecutor(max_workers=w),
    )

    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({
        "dataset_dir": str(data),
        "scan": {"start_date": "2024-02-01", "end_date": "2024-06-30",
                 "workers": 1, "ticker_regex": None, "label_horizon": 20},
        "last_selected_pattern": "bo_only",
    }))
    app = create_app(config_path=cfg_path, outputs_root=str(outputs),
                     use_thread_pool=True)
    return TestClient(app), outputs


def test_get_scans_flat_lists_entries(app_with_one_scan):
    client, _ = app_with_one_scan
    r = client.get("/scans/")
    assert r.status_code == 200
    rows = r.json()
    assert any(row["scan_ts"] == "20260627T130000"
               and row["pattern_ids"] == ["bo_only"]
               for row in rows)


def test_get_scans_ts_loads_multi_file(app_with_one_scan):
    client, _ = app_with_one_scan
    r = client.get("/scans/20260627T130000")
    assert r.status_code == 200
    blob = r.json()
    assert blob["pattern_ids"] == ["bo_only"]
    assert "per_pattern" in blob and "bo_only" in blob["per_pattern"]


def test_delete_scans_ts(app_with_one_scan):
    client, outputs = app_with_one_scan
    r = client.delete("/scans/20260627T130000")
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    assert not (Path(outputs) / "scans" / "20260627T130000.json").exists()


def test_get_scans_ts_404_missing(app_with_one_scan):
    client, _ = app_with_one_scan
    r = client.get("/scans/00000000T000000")
    assert r.status_code == 404


def test_delete_scans_ts_404_missing(app_with_one_scan):
    client, _ = app_with_one_scan
    r = client.delete("/scans/00000000T000000")
    assert r.status_code == 404
```

- [ ] **Step 2: 创建 `tests/path2_web/test_api_scan_multi.py` 写测试**

```python
"""POST /scan 接受 pattern_ids: List[str]。"""
import json
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from path2_web.app import create_app


@pytest.fixture
def app(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    n = 100
    pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=n),
        "open":[10.0]*n, "high":[11.0]*n, "low":[9.0]*n,
        "close":[10.5]*n, "volume":[100.0]*n,
    }).to_pickle(data / "AAA.pkl")

    outputs = tmp_path / "out"
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({
        "dataset_dir": str(data),
        "scan": {"start_date": "2024-02-01", "end_date": "2024-06-30",
                 "workers": 1, "ticker_regex": None, "label_horizon": 20},
        "last_selected_pattern": "bo_only",
    }))
    return TestClient(create_app(config_path=cfg_path, outputs_root=str(outputs),
                                  use_thread_pool=True))


def test_post_scan_accepts_pattern_ids(app):
    """POST /scan 接受 pattern_ids 数组,返回 scan_id。"""
    r = app.post("/scan", json={
        "pattern_ids": ["bo_only", "bottom_breakout_burst"],
        "start_date": "2024-02-01",
        "end_date": "2024-06-30",
        "workers": 1,
        "label_horizon": 20,
    })
    assert r.status_code == 200
    assert "scan_id" in r.json()


def test_post_scan_empty_pattern_ids_422(app):
    """空数组 → 422 Unprocessable。"""
    r = app.post("/scan", json={
        "pattern_ids": [],
        "start_date": "2024-02-01", "end_date": "2024-06-30",
        "workers": 1, "label_horizon": 20,
    })
    assert r.status_code == 422


def test_post_scan_unknown_pattern_404(app):
    """未注册 pattern_id → 404。"""
    r = app.post("/scan", json={
        "pattern_ids": ["does_not_exist"],
        "start_date": "2024-02-01", "end_date": "2024-06-30",
        "workers": 1, "label_horizon": 20,
    })
    assert r.status_code == 404


def test_post_scan_dedupes_duplicates(app):
    """pattern_ids 重复 → 后端自动去重(dict 自然去重),不报错。"""
    r = app.post("/scan", json={
        "pattern_ids": ["bo_only", "bo_only"],
        "start_date": "2024-02-01", "end_date": "2024-06-30",
        "workers": 1, "label_horizon": 20,
    })
    assert r.status_code == 200
```

- [ ] **Step 3: 跑测试确认红失败**

```bash
uv run pytest tests/path2_web/test_scans_route_flat.py tests/path2_web/test_api_scan_multi.py -v
```

Expected: 路由不存在 / ScanRequest 字段失配 → 多条 FAIL

- [ ] **Step 4: 改 `path2_web/api.py`(替换关键函数,保留 ScanManager 不变)**

替换 `path2_web/api.py` 的 `ScanRequest`、`resolve_eval_meta`、`build_router` 三块。注意 `ScanManager` 类、`stream` 方法、cancel 行为完全保留。

```python
"""HTTP 路由 + SSE 扫描编排。create_app 注入 registry/config/outputs_root。"""
from __future__ import annotations

import asyncio
import json
import threading
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, HTTPException, Request
from fastapi import Path as FPath
from pydantic import BaseModel, Field, field_validator
from sse_starlette.sse import EventSourceResponse

from path2_web import scan as scan_mod
from path2_web.data import slice_window, serialize_ohlc
from path2_web.diagnose import diagnose_symbol
from path2_web.serialize import serialize_pattern


class ScanRequest(BaseModel):
    pattern_ids: list[str] = Field(..., min_length=1)
    start_date: str
    end_date: str
    workers: int = 8
    ticker_regex: str | None = None
    label_horizon: int = 20

    @field_validator("pattern_ids")
    @classmethod
    def _dedupe(cls, v: list[str]) -> list[str]:
        seen: set = set()
        out: list = []
        for x in v:
            if x not in seen:
                seen.add(x)
                out.append(x)
        return out


def require_eval_meta(mod) -> dict:
    """读 app 模块 eval_meta() 协议。铁律下 discovery 已闸过滤,api 调到此处不可能 None。
    若仍 None / 字段不全 → ValueError(防御性,非业务路径)。
    """
    fn = getattr(mod, "eval_meta", None)
    if not callable(fn):
        raise ValueError("eval_meta missing or non-callable (discovery gate failed)")
    load_params = getattr(mod, "load_params", None)
    meta = fn(load_params()) if callable(load_params) else fn()
    if not isinstance(meta, dict) or "end_role" not in meta or "head_buffer_trading_days" not in meta:
        raise ValueError(f"eval_meta returned invalid dict: {meta!r}")
    return meta


class ScanManager:
    """每个 scan_id 一个 asyncio.Queue + cancel_event;后台线程跑阻塞 run_scan,
    进度经 call_soon_threadsafe 投递。cancel(scan_id) set cancel_event → run_scan
    检测点抛 ScanCancelled → runner 捕获并发 done {cancelled: true}。"""

    def __init__(self):
        self._scans: dict = {}

    def start(self, loop, scan_id, job, done_meta_fn):
        q: asyncio.Queue = asyncio.Queue()
        cancel_event = threading.Event()
        save_event = threading.Event()
        self._scans[scan_id] = {"queue": q, "done": False, "last": None,
                                "cancel": cancel_event, "save": save_event}

        def on_progress(scanned, total, hits, errors):
            evt = {"scanned": scanned, "total": total, "hits": hits, "errors": errors}
            self._scans[scan_id]["last"] = evt
            loop.call_soon_threadsafe(q.put_nowait, evt)

        def runner():
            try:
                result = job(on_progress, cancel_event, save_event)
                done = {"type": "done", **done_meta_fn(result)}
            except scan_mod.ScanCancelled:
                done = {"type": "done", "cancelled": True, "error": None,
                        "hits": 0, "errors": 0, "total": 0}
            except Exception as e:           # noqa: BLE001
                done = {"type": "done", "error": f"{type(e).__name__}: {e}",
                        "hits": 0, "errors": 0, "total": 0}
            self._scans[scan_id]["last"] = done
            self._scans[scan_id]["done"] = True
            loop.call_soon_threadsafe(q.put_nowait, done)

        loop.run_in_executor(None, runner)

    def cancel(self, scan_id, save: bool = False) -> bool:
        entry = self._scans.get(scan_id)
        if entry is None:
            return False
        if save:
            entry["save"].set()
        entry["cancel"].set()
        return True

    async def stream(self, scan_id):
        entry = self._scans.get(scan_id)
        if entry is None:
            yield {"event": "message", "data": '{"type":"error","msg":"unknown scan_id"}'}
            return
        q = entry["queue"]
        if entry["done"] and entry["last"] is not None:
            yield {"event": "message", "data": json.dumps(entry["last"], ensure_ascii=False)}
            return
        while True:
            evt = await q.get()
            yield {"event": "message", "data": json.dumps(evt, ensure_ascii=False)}
            if evt.get("type") == "done":
                return


def build_router(*, registry, config_path, get_config, set_config,
                 outputs_root, use_thread_pool=False) -> APIRouter:
    router = APIRouter()
    manager = ScanManager()
    _exec_factory = ((lambda w: ThreadPoolExecutor(max_workers=w)) if use_thread_pool
                     else (lambda w: ProcessPoolExecutor(max_workers=w)))

    _TS_PATTERN = r"^\d{8}T\d{6}$"

    @router.get("/patterns")
    def get_patterns():
        out = []
        for pid in registry.ids():
            mod = registry.get(pid)
            _load = getattr(mod, "load_params", None)
            spec = mod.build_pattern(_load()) if callable(_load) else mod.PATTERN_DAG
            out.append(serialize_pattern(spec))
        return out

    @router.get("/ohlc")
    def get_ohlc(symbol: str, start: str, end: str):
        cfg = get_config()
        pkl = Path(cfg["dataset_dir"]) / f"{symbol}.pkl"
        if not pkl.exists():
            raise HTTPException(404, f"pkl not found: {symbol}")
        win = slice_window(pd.read_pickle(pkl), start, end)
        return serialize_ohlc(symbol, win)

    @router.get("/config")
    def read_config():
        return get_config()

    @router.put("/config")
    def write_config(cfg: dict):
        set_config(cfg)
        return {"ok": True}

    @router.get("/scans/")
    def scans_list_flat():
        return scan_mod.list_scans_flat(outputs_root)

    @router.get("/scans/{scan_ts}")
    def scan_load_flat(scan_ts: str = FPath(..., pattern=_TS_PATTERN)):
        try:
            return scan_mod.load_scan_flat(scan_ts, outputs_root)
        except FileNotFoundError:
            raise HTTPException(404, "scan not found")

    @router.delete("/scans/{scan_ts}")
    def scan_delete_flat(scan_ts: str = FPath(..., pattern=_TS_PATTERN)):
        try:
            scan_mod.delete_scan_flat(scan_ts, outputs_root)
        except FileNotFoundError:
            raise HTTPException(404, "scan not found")
        return {"ok": True}

    @router.get("/diagnose")
    def get_diagnose(pattern_id: str, symbol: str, start: str, end: str):
        mod = registry.get(pattern_id)
        if mod is None:
            raise HTTPException(404, f"unknown pattern: {pattern_id}")
        cfg = get_config()
        pkl = Path(cfg["dataset_dir"]) / f"{symbol}.pkl"
        if not pkl.exists():
            raise HTTPException(404, f"pkl not found: {symbol}")
        win = slice_window(pd.read_pickle(pkl), start, end)
        spec = mod.build_pattern(mod.load_params())
        return diagnose_symbol(spec, win, None, symbol=symbol, pattern_id=pattern_id)

    @router.get("/preview")
    def get_preview(pattern_id: str, symbol: str, start: str, end: str,
                    label_horizon: int = 20):
        """单股临时计算 — 复刻 multi-scan worker 的 buffered+label 链路,不落盘,单 pattern。"""
        mod = registry.get(pattern_id)
        if mod is None:
            raise HTTPException(404, f"unknown pattern: {pattern_id}")
        cfg = get_config()
        pkl = Path(cfg["dataset_dir"]) / f"{symbol}.pkl"
        if not pkl.exists():
            raise HTTPException(404, f"pkl not found: {symbol}")

        try:
            meta = require_eval_meta(mod)
            end_role = meta["end_role"]
            head_buf = meta["head_buffer_trading_days"]
            start_ts, end_ts = pd.to_datetime(start), pd.to_datetime(end)
            buf_start = str((start_ts - pd.Timedelta(days=round(head_buf * scan_mod.TRADING_TO_CALENDAR_RATIO))).date())
            buf_end   = str((end_ts   + pd.Timedelta(days=round(label_horizon * scan_mod.TRADING_TO_CALENDAR_RATIO))).date())

            # 复刻 worker 单 pattern 调用
            df = pd.read_pickle(pkl)
            win = slice_window(df, buf_start, buf_end)
            _load = getattr(mod, "load_params", None)
            res = mod.analyze(win, _load() if callable(_load) else None)
            from path2_web.serialize import serialize_per_pattern_result
            out = serialize_per_pattern_result(
                res, end_role=end_role, label_horizon=label_horizon,
                win=win, start_ts=start_ts, end_ts=end_ts)
            pattern_spec = serialize_pattern(mod.build_pattern(mod.load_params()))
            scan_meta = {
                "start_date": start, "end_date": end,
                "win_start": buf_start, "win_end": buf_end,
                "label_horizon": label_horizon, "end_role": end_role,
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(500, f"{type(e).__name__}: {e}") from e
        return {"analysis": out["analysis"], "summary": out["summary"],
                "pattern_spec": pattern_spec, "scan": scan_meta}

    @router.post("/scan")
    async def post_scan(req: ScanRequest):
        # 校验所有 pattern_id 在 registry
        for pid in req.pattern_ids:
            if registry.get(pid) is None:
                raise HTTPException(404, f"unknown pattern: {pid}")
        cfg = get_config()
        scan_ts = time.strftime("%Y%m%dT%H%M%S")

        specs: dict = {}
        module_paths: dict = {}
        end_roles: dict = {}
        head_bufs: list = []
        for pid in req.pattern_ids:
            mod = registry.get(pid)
            spec_json = serialize_pattern(mod.build_pattern(mod.load_params()))
            specs[pid] = spec_json
            module_paths[pid] = registry.module_path(pid)
            meta = require_eval_meta(mod)
            end_roles[pid] = meta["end_role"]
            head_bufs.append(meta["head_buffer_trading_days"])
        head_buffer = max(head_bufs)
        loop = asyncio.get_running_loop()

        def job(on_progress, cancel_event, save_event):
            return scan_mod.run_scan_multi(
                data_dir=cfg["dataset_dir"],
                pattern_specs_json=specs,
                module_paths=module_paths,
                pattern_ids=req.pattern_ids,
                end_roles=end_roles,
                head_buffer_trading_days=head_buffer,
                label_horizon=req.label_horizon,
                start_date=req.start_date, end_date=req.end_date,
                workers=req.workers, ticker_regex=req.ticker_regex,
                scan_ts=scan_ts, outputs_root=outputs_root,
                on_progress=on_progress, executor_factory=_exec_factory,
                cancel_event=cancel_event, save_event=save_event,
            )

        def done_meta(result):
            s = result["scan"]
            return {"pattern_ids": req.pattern_ids, "scan_ts": scan_ts,
                    "hits": s["hits"], "errors": s["errors"], "total": s["scanned"],
                    "partial": bool(s.get("partial", False))}

        manager.start(loop, scan_ts, job, done_meta)
        return {"scan_id": scan_ts}

    @router.get("/scan/{scan_id}/stream")
    async def scan_stream(scan_id: str, request: Request):
        return EventSourceResponse(manager.stream(scan_id))

    @router.post("/scan/{scan_id}/cancel")
    def scan_cancel(scan_id: str, save: bool = False):
        if not manager.cancel(scan_id, save=save):
            raise HTTPException(404, "scan not running or unknown")
        return {"ok": True}

    return router
```

- [ ] **Step 5: 清理失效的旧测试**

```bash
git rm tests/path2_web/test_eval_meta_resolve.py
```

`test_api.py` 内涉及 `/scans/{pid}/...` 的用例需要适配,直接在文件内改:

打开 `tests/path2_web/test_api.py`,把测试中所有 `client.get("/scans/<pid>")` 改为 `client.get("/scans/")`、`client.get("/scans/<pid>/<ts>")` 改为 `client.get("/scans/<ts>")`、`client.delete("/scans/<pid>/<ts>")` 改为 `client.delete("/scans/<ts>")`。具体改动按 grep 出的行号修;若不便修就 delete 它(测试已被新 test_scans_route_flat 覆盖)。`POST /scan` body 的 `pattern_id` 改为 `pattern_ids: [...]`。

- [ ] **Step 6: 跑全 path2_web 测试套件,确认绿**

```bash
uv run pytest tests/path2_web/ -v
```

Expected: 全 PASS(扣去 test_serialize_multi 的可能 skip)

- [ ] **Step 7: Commit**

```bash
git add path2_web/api.py tests/path2_web/test_api_scan_multi.py \
        tests/path2_web/test_scans_route_flat.py tests/path2_web/test_api.py
git commit -m "feat(api): POST /scan pattern_ids array + flat /scans/* routes"
```

---

## Task 6: types.ts + api.ts 前端契约镜像

**Files:**
- Modify: `path2_web_ui/src/types.ts` — 加 MultiScanResultFile / PerPatternResult / PerPatternMeta;ScanMeta.end_role 移除、win_*/label_horizon 非 optional;ScanHistoryEntry 加 pattern_ids
- Modify: `path2_web_ui/src/api.ts` — startScan body / listScans / loadScan / deleteScan 路径改

**Interfaces:**
- Produces TS 类型:
  - `PerPatternResult { summary, analysis, max_forward_return: number | null }`
  - `PerPatternMeta { pattern_spec: SerializedPattern, end_role: string }`
  - `StockResult { symbol, per_pattern: Record<string, PerPatternResult> }`
  - `MultiScanResultFile { pattern_ids, per_pattern, scan, results }`
  - `ScanHistoryEntry { ..., pattern_ids: string[] }`
- Produces API client:
  - `startScan(req: ScanReq)` body 改 `{pattern_ids: string[]}`
  - `listScans()` 无参,GET `/scans/`
  - `loadScan(scanTs: string)` GET `/scans/{ts}`
  - `deleteScan(scanTs: string)` DELETE `/scans/{ts}`

- [ ] **Step 1: 改 `path2_web_ui/src/types.ts`**

替换文件相应段:

```ts
// spec §7 后端 JSON 契约的 TS 镜像。字段名与后端严格一致。

export interface WhereRule { clause_id: string; op: string | null; threshold: unknown }
export interface TopoNode {
  node_id: string; class_id: string; label: string
  source_tag: string
  render_grid?: 'price' | 'time'
  where_rules: WhereRule[]
}
export interface TopoEdge { src: string; dst: string; kind: string; rule: string }
export interface Topology { nodes: TopoNode[]; edges: TopoEdge[] }
export interface SerializedPattern {
  pattern_id: string; display_name: string
  topology: Topology; event_styles: Record<string, string>
}

export interface EventDict {
  class_id: string; event_id: string; start_idx: number; end_idx: number
  source_tag: string
  referenced_points?: Array<[number, number, string]>
  [attr: string]: unknown
}

export interface ClauseWitness {
  satisfied: boolean; measured: unknown; op: string | null
  threshold: unknown
}
export interface EdgeWitness { satisfied: boolean; measured: number; src: string; dst: string }
export interface PredicateTrace {
  where_results: Record<string, Record<string, ClauseWitness>>
  edge_results: Record<string, EdgeWitness>
}
export interface MatchDict {
  event_id: string; start_idx: number; end_idx: number
  role_index: Record<string, string>
  children: string[]
  predicate_trace: PredicateTrace | null
  forward_return?: number | null
}
export interface Analysis { events: EventDict[]; matches: MatchDict[] }

// ── 多 pattern schema ───────────────────────────────────────────────
export interface PerPatternResult {
  summary: Record<string, number>            // {class_id: count} ∪ {matches: n}
  analysis: Analysis
  max_forward_return: number | null
}
export interface PerPatternMeta {
  pattern_spec: SerializedPattern
  end_role: string
}
export interface ScanMeta {
  scan_ts: string; start_date: string; end_date: string; workers: number
  scanned: number; hits: number; errors: number; dataset_dir: string; params: string
  win_start: string; win_end: string                  // 必有(非 optional)
  label_horizon: number                                // 必有(非 optional)
  partial?: boolean
}
export interface StockResult {
  symbol: string
  per_pattern: Record<string, PerPatternResult>        // key = pattern_id
}
export interface MultiScanResultFile {
  pattern_ids: string[]
  per_pattern: Record<string, PerPatternMeta>          // key = pattern_id
  scan: ScanMeta
  results: StockResult[]
}

export interface Bar { date: string; o: number; h: number; l: number; c: number; v: number; rv: number }
export interface Ohlc { symbol: string; bars: Bar[] }

export interface AttrRow {
  event_id: string; start_idx: number; end_idx: number
  clauses: Record<string, ClauseWitness>
}
export interface RelRow { src: string; kind: string; total_src: number; ok_count: number; ok_src_ids: string[] }
export interface RoleDiag { attr: AttrRow[]; rel: RelRow[] }
export interface Diagnostics {
  symbol: string; pattern_id: string; roles: Record<string, RoleDiag>; note: string
}

export interface ScanProgress { scanned: number; total: number; hits: number; errors: number }
export interface ScanDone {
  type: 'done'; hits: number; errors: number; total: number
  pattern_ids?: string[]; scan_ts?: string; error?: string | null
  cancelled?: boolean
  partial?: boolean
}

export interface ScanHistoryEntry {
  scan_ts: string
  pattern_ids: string[]                                 // 新增
  hits: number | null
  total: number | null
  size: number
  partial: boolean
}

export interface AppConfig {
  dataset_dir: string
  scan: { start_date: string; end_date: string; workers: number; ticker_regex: string | null; label_horizon?: number }
  last_selected_pattern: string
}

export function isPoint(e: { start_idx: number; end_idx: number }): boolean {
  return e.start_idx === e.end_idx
}

export type Level = 'matched' | 'qualified' | 'detected'
export type Tier = Level
```

- [ ] **Step 2: 改 `path2_web_ui/src/api.ts`**

替换 `startScan` / `listScans` / `loadScan` / `deleteScan` / `ScanReq`:

```ts
import type {
  SerializedPattern, MultiScanResultFile, Ohlc, Diagnostics, AppConfig,
  ScanProgress, ScanDone, ScanHistoryEntry, Analysis, ScanMeta,
} from './types'

const BASE = (import.meta as any).env?.VITE_API_BASE ?? 'http://localhost:8000'

async function getJson<T>(path: string): Promise<T> {
  const r = await fetch(`${BASE}${path}`)
  if (!r.ok) throw new Error(`GET ${path} → ${r.status}: ${await r.text()}`)
  return r.json() as Promise<T>
}

export function getPatterns(): Promise<SerializedPattern[]> {
  return getJson('/patterns')
}
export function getOhlc(symbol: string, start: string, end: string): Promise<Ohlc> {
  return getJson(`/ohlc?symbol=${encodeURIComponent(symbol)}&start=${start}&end=${end}`)
}
export function listScans(): Promise<ScanHistoryEntry[]> {
  return getJson('/scans/')
}
export function loadScan(scanTs: string): Promise<MultiScanResultFile> {
  return getJson(`/scans/${scanTs}`)
}
export function deleteScan(scanTs: string): Promise<{ok: true}> {
  return fetch(`${BASE}/scans/${scanTs}`, { method: 'DELETE' })
    .then(r => r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`)))
}
export function cancelScan(scanId: string, save: boolean = false): Promise<{ok: true}> {
  const url = `${BASE}/scan/${scanId}/cancel?save=${save}`
  const ok = navigator.sendBeacon(url)
  return ok ? Promise.resolve({ok: true})
            : Promise.reject(new Error('sendBeacon enqueue failed'))
}
export function getDiagnose(patternId: string, symbol: string, start: string, end: string): Promise<Diagnostics> {
  return getJson(`/diagnose?pattern_id=${patternId}&symbol=${encodeURIComponent(symbol)}&start=${start}&end=${end}`)
}
export function getConfig(): Promise<AppConfig> {
  return getJson('/config')
}
export async function putConfig(cfg: AppConfig): Promise<void> {
  const r = await fetch(`${BASE}/config`, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(cfg),
  })
  if (!r.ok) throw new Error(`PUT /config → ${r.status}`)
}

export interface ScanReq {
  pattern_ids: string[]
  start_date: string
  end_date: string
  workers: number
  ticker_regex: string | null
  label_horizon: number
}

export async function startScan(req: ScanReq): Promise<string> {
  const r = await fetch(`${BASE}/scan`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(req),
  })
  if (!r.ok) throw new Error(`POST /scan → ${r.status}`)
  return (await r.json()).scan_id
}

export function streamScan(
  scanId: string, onEvent: (e: ScanProgress | ScanDone) => void, onError: (e: unknown) => void,
): EventSource {
  const es = new EventSource(`${BASE}/scan/${scanId}/stream`)
  es.onmessage = (ev: MessageEvent) => {
    const data = JSON.parse(ev.data)
    onEvent(data)
    if (data.type === 'done') es.close()
  }
  es.onerror = (e) => onError(e)
  return es
}

export interface PreviewResp {
  analysis: Analysis
  summary: Record<string, number>
  pattern_spec: SerializedPattern
  scan: ScanMeta
}

export function getPreview(
  patternId: string, symbol: string, start: string, end: string, labelHorizon: number
): Promise<PreviewResp> {
  return getJson(
    `/preview?pattern_id=${encodeURIComponent(patternId)}`
    + `&symbol=${encodeURIComponent(symbol)}`
    + `&start=${start}&end=${end}&label_horizon=${labelHorizon}`)
}
```

- [ ] **Step 3: 跑 tsc 检查类型**

```bash
cd path2_web_ui && npx vue-tsc --noEmit
```

Expected: 报多处错误(view store / 组件还没改),记录但允许后续 task 修

- [ ] **Step 4: Commit**

```bash
git add path2_web_ui/src/types.ts path2_web_ui/src/api.ts
git commit -m "feat(ui): multi-pattern types mirror + api client paths"
```

---

## Task 7: render/visible.ts 收紧 windowOf

**Files:**
- Modify: `path2_web_ui/src/render/visible.ts` — `windowOf` 删 fallback,加 require 断言
- Test: 修改/扩展 `path2_web_ui/tests/visible.spec.ts`(若存在)或新建 `visible.windowof.spec.ts`

**Interfaces:**
- Consumes: 旧 `windowOf(scan)` 接受 scan 可缺 win_*
- Produces: 新 `windowOf(scan)` 要求 scan.win_start/win_end 必有;缺则 throw

- [ ] **Step 1: 创建/更新测试 `path2_web_ui/tests/visible.windowof.spec.ts`**

```ts
import { describe, it, expect } from 'vitest'
import { windowOf } from '../src/render/visible'
import type { ScanMeta } from '../src/types'

const baseScan: ScanMeta = {
  scan_ts: '20260627T120000',
  start_date: '2024-01-01', end_date: '2024-06-30',
  workers: 1, scanned: 100, hits: 5, errors: 0,
  dataset_dir: '/data', params: 'default',
  win_start: '2023-08-01', win_end: '2024-07-15',
  label_horizon: 20,
}

describe('windowOf', () => {
  it('returns win_start/win_end from buffered scan meta', () => {
    expect(windowOf(baseScan)).toEqual({ start: '2023-08-01', end: '2024-07-15' })
  })

  it('throws when win_start is missing(铁律下不应发生,防御)', () => {
    const bad = { ...baseScan, win_start: undefined as any }
    expect(() => windowOf(bad)).toThrow()
  })
})
```

- [ ] **Step 2: 查看现有 `windowOf` 实现**

```bash
grep -n "windowOf" /home/yu/PycharmProjects/Trade_Strategy/path2_web_ui/src/render/visible.ts
```

定位函数签名,根据现有逻辑修改:

- [ ] **Step 3: 改 `path2_web_ui/src/render/visible.ts` 的 `windowOf` 函数**

将原 `windowOf` 函数替换为(其他 export 不动):

```ts
export function windowOf(scan: Pick<ScanMeta, 'win_start' | 'win_end' | 'start_date' | 'end_date'>):
  { start: string; end: string } {
  // 铁律 eval_meta 后 win_*/end_role/label_horizon 永远非 null;
  // 旧文件回退分支删除(spec §3.6)。
  if (!scan.win_start || !scan.win_end) {
    throw new Error('windowOf: scan.win_start/win_end required (eval_meta 铁律下应永远非空)')
  }
  return { start: scan.win_start, end: scan.win_end }
}
```

- [ ] **Step 4: 跑测试,确认绿**

```bash
cd path2_web_ui && npm run test -- visible
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add path2_web_ui/src/render/visible.ts path2_web_ui/tests/visible.windowof.spec.ts
git commit -m "refactor(ui): tighten windowOf to require win_* (eval_meta iron rule)"
```

---

## Task 8: stores/patterns.ts + scan.ts 重写为多选

**Files:**
- Modify: `path2_web_ui/src/stores/patterns.ts` — 改 `selectedId: string | null` 为 `selectedIds: Set<string>`,保留 `lastSelectedPattern` 字段服务 active 默认
- Modify: `path2_web_ui/src/stores/scan.ts` — `run(req)` 参数 ScanReq pattern_ids 数组;`open(scanTs)` 不再需 patternId

**Interfaces:**
- Produces:
  - `usePatternsStore().selectedIds: Set<string>`
  - `usePatternsStore().toggleSelected(id: string)` / `selectAll()` / `selectNone()` / `invertSelection()`
  - `useScanStore().run(req: ScanReq)`
  - `useScanStore().open(scanTs: string)` — 不再带 patternId
  - `useScanStore().history` 元素是 `ScanHistoryEntry`(已含 pattern_ids)

- [ ] **Step 1: 改 `path2_web_ui/src/stores/patterns.ts`**

```bash
cat /home/yu/PycharmProjects/Trade_Strategy/path2_web_ui/src/stores/patterns.ts
```

阅读现有内容后,改为如下(保留 `loadPatterns` 之类原有 action 行为):

```ts
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { SerializedPattern } from '../types'
import { getPatterns } from '../api'

export const usePatternsStore = defineStore('patterns', () => {
  const list = ref<SerializedPattern[]>([])
  const selectedIds = ref<Set<string>>(new Set())
  const loaded = ref(false)

  async function loadPatterns() {
    list.value = await getPatterns()
    loaded.value = true
  }

  function toggleSelected(id: string) {
    const s = new Set(selectedIds.value)
    if (s.has(id)) s.delete(id); else s.add(id)
    selectedIds.value = s
  }
  function selectAll() {
    selectedIds.value = new Set(list.value.map(p => p.pattern_id))
  }
  function selectNone() {
    selectedIds.value = new Set()
  }
  function invertSelection() {
    const s = new Set<string>()
    for (const p of list.value) if (!selectedIds.value.has(p.pattern_id)) s.add(p.pattern_id)
    selectedIds.value = s
  }

  const selectedArray = computed(() => Array.from(selectedIds.value))

  return { list, loaded, selectedIds, selectedArray,
           loadPatterns, toggleSelected, selectAll, selectNone, invertSelection }
})
```

- [ ] **Step 2: 改 `path2_web_ui/src/stores/scan.ts`**

替换文件:

```ts
import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { ScanProgress, ScanDone, ScanHistoryEntry } from '../types'
import { startScan, streamScan, listScans, loadScan, deleteScan, cancelScan, type ScanReq } from '../api'
import { useViewStore } from './view'

export const useScanStore = defineStore('scan', () => {
  const progress = ref<ScanProgress | null>(null)
  const running = ref(false)
  const lastDone = ref<ScanDone | null>(null)
  const history = ref<ScanHistoryEntry[]>([])
  const currentScanId = ref<string | null>(null)
  const cancelling = ref(false)
  let _eventSource: EventSource | null = null

  async function run(req: ScanReq) {
    running.value = true
    progress.value = null
    lastDone.value = null
    const id = await startScan(req)
    currentScanId.value = id
    const es = streamScan(id, (e) => {
      if ((e as ScanDone).type === 'done') {
        const done = e as ScanDone
        lastDone.value = done
        running.value = false
        if (!done.error && !done.cancelled) {
          void refreshHistory()
          if (done.scan_ts) void open(done.scan_ts)
        }
      } else if (!cancelling.value) {
        progress.value = e as ScanProgress
      }
    }, () => { running.value = false; es.close() })
    _eventSource = es
  }

  async function refreshHistory() {
    history.value = await listScans()
  }

  async function open(scanTs: string) {
    const f = await loadScan(scanTs)
    useViewStore().loadScanFile(f)
  }

  async function remove(scanTs: string) {
    await deleteScan(scanTs)
  }

  async function cancel(save: boolean): Promise<void> {
    if (!currentScanId.value || !running.value || cancelling.value) return
    cancelling.value = true
    const scanId = currentScanId.value
    try {
      await cancelScan(scanId, save)
      if (_eventSource) {
        _eventSource.close()
        _eventSource = null
      }
      await new Promise(r => setTimeout(r, 300))
      if (save) {
        for (let i = 0; i < 30; i++) {
          const list = await listScans()
          const entry = list.find(e => e.scan_ts === scanId)
          if (entry) {
            history.value = list
            await open(scanId)
            lastDone.value = { type: 'done', hits: entry.hits ?? 0, errors: 0,
                               total: entry.total ?? 0, partial: true,
                               scan_ts: scanId }
            break
          }
          await new Promise(r => setTimeout(r, 200))
        }
      } else {
        lastDone.value = { type: 'done', hits: 0, errors: 0, total: 0,
                           cancelled: true, scan_ts: scanId }
      }
      running.value = false
    } finally {
      cancelling.value = false
    }
  }

  return { progress, running, lastDone, history, currentScanId,
           run, refreshHistory, open, remove, cancel }
})
```

- [ ] **Step 3: 跑 vitest 看哪些 store 测试需调整**

```bash
cd path2_web_ui && npm run test
```

预期失败:`tests/stores.spec.ts` 等可能引用旧 `_currentPatternId` / `open(patternId, scanTs)` 接口。打开报错的 spec,把:
- `open(patternId, scanTs)` 改为 `open(scanTs)`
- `useScanStore().run({pattern_id: 'x', ...})` 改为 `run({pattern_ids: ['x'], ...})`
- `usePatternsStore().selectedId` 引用改为 `selectedIds`(若有)

- [ ] **Step 4: 改完后再跑测试**

```bash
cd path2_web_ui && npm run test
```

Expected: 多数 PASS;view store 相关 spec 仍可能红(下一 task 修)

- [ ] **Step 5: Commit**

```bash
git add path2_web_ui/src/stores/patterns.ts path2_web_ui/src/stores/scan.ts path2_web_ui/tests/
git commit -m "feat(ui): patterns multi-select + scan store flat paths"
```

---

## Task 9: view store 改造 — activePatternId + unionRows + sortedRows + effective 三件套

**Files:**
- Modify: `path2_web_ui/src/stores/view.ts` — state + computed + actions + watch
- Test: 新建 `path2_web_ui/tests/view.multi.spec.ts`、`unionRows.spec.ts`

**Interfaces:**
- Produces:
  - `state: activePatternId: Ref<string | null>, sortByPid: Ref<string | null>, sortDesc: Ref<boolean>`
  - `computed: patternIds, currentPerStock, pattern, currentAnalysis, effectivePattern, effectiveAnalysis, effectiveScan, unionRows, sortedRows`
  - `action: setActivePattern(pid), setSort(pid)`
  - `loadScanFile(f: MultiScanResultFile)` 初始化 activePatternId(优先 last_selected_pattern,否则 pattern_ids[0])
  - diag watch deps 加 `activePatternId`
  - **cell 点击只 selectSymbol、不动 activePatternId**

- [ ] **Step 1: 创建 `path2_web_ui/tests/unionRows.spec.ts`**

```ts
/**
 * unionRows / sortedRows 派生测试。
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useViewStore } from '../src/stores/view'
import type { MultiScanResultFile } from '../src/types'

const emptyAnalysis = { events: [], matches: [] }

function makeFile(): MultiScanResultFile {
  return {
    pattern_ids: ['bo_only', 'bbb'],
    per_pattern: {
      bo_only: { pattern_spec: { pattern_id: 'bo_only', display_name: 'bo', topology: { nodes: [], edges: [] }, event_styles: {} }, end_role: 'bo' },
      bbb:     { pattern_spec: { pattern_id: 'bbb',     display_name: 'bbb', topology: { nodes: [], edges: [] }, event_styles: {} }, end_role: 'tb' },
    },
    scan: {
      scan_ts: '20260627T120000', start_date: '2024-01-01', end_date: '2024-06-30',
      workers: 1, scanned: 3, hits: 3, errors: 0, dataset_dir: '/d', params: 'default',
      win_start: '2023-09-01', win_end: '2024-07-15', label_horizon: 20,
    },
    results: [
      { symbol: 'AAA', per_pattern: {
        bo_only: { summary: { matches: 2 }, analysis: emptyAnalysis, max_forward_return: 0.34 },
        bbb:     { summary: { matches: 1 }, analysis: emptyAnalysis, max_forward_return: 0.10 },
      }},
      { symbol: 'BBB', per_pattern: {
        bo_only: { summary: { matches: 1 }, analysis: emptyAnalysis, max_forward_return: 0.50 },
        bbb:     { summary: { matches: 0 }, analysis: emptyAnalysis, max_forward_return: null },
      }},
      { symbol: 'CCC', per_pattern: {
        bo_only: { summary: { matches: 0 }, analysis: emptyAnalysis, max_forward_return: null },
        bbb:     { summary: { matches: 1 }, analysis: emptyAnalysis, max_forward_return: 0.20 },
      }},
    ],
  }
}

describe('unionRows / sortedRows', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('unionRows shape: cells per pattern with max_ret and matched bool', () => {
    const v = useViewStore()
    v.loadScanFile(makeFile())
    expect(v.unionRows.length).toBe(3)
    const a = v.unionRows.find(r => r.symbol === 'AAA')!
    expect(a.cells.map(c => c.pid)).toEqual(['bo_only', 'bbb'])
    expect(a.cells[0].max_ret).toBeCloseTo(0.34)
    expect(a.cells[1].matched).toBe(true)
    const b = v.unionRows.find(r => r.symbol === 'BBB')!
    expect(b.cells[1].max_ret).toBeNull()
    expect(b.cells[1].matched).toBe(false)
  })

  it('default sortByPid is null → sortedRows preserves worker order', () => {
    const v = useViewStore()
    v.loadScanFile(makeFile())
    expect(v.sortByPid).toBeNull()
    expect(v.sortedRows.map(r => r.symbol)).toEqual(['AAA', 'BBB', 'CCC'])
  })

  it('sort by bo_only desc puts highest max_ret first; null sinks last', () => {
    const v = useViewStore()
    v.loadScanFile(makeFile())
    v.setSort('bo_only')
    expect(v.sortByPid).toBe('bo_only')
    expect(v.sortDesc).toBe(true)
    expect(v.sortedRows.map(r => r.symbol)).toEqual(['BBB', 'AAA', 'CCC'])
  })

  it('clicking same column twice flips to asc; null still sinks last', () => {
    const v = useViewStore()
    v.loadScanFile(makeFile())
    v.setSort('bo_only')
    v.setSort('bo_only')
    expect(v.sortDesc).toBe(false)
    expect(v.sortedRows.map(r => r.symbol)).toEqual(['AAA', 'BBB', 'CCC'])
  })

  it('switching to another column resets to desc on that column', () => {
    const v = useViewStore()
    v.loadScanFile(makeFile())
    v.setSort('bo_only')
    v.setSort('bo_only')   // asc
    v.setSort('bbb')
    expect(v.sortByPid).toBe('bbb')
    expect(v.sortDesc).toBe(true)
    expect(v.sortedRows.map(r => r.symbol)).toEqual(['CCC', 'AAA', 'BBB'])
  })

  it('union row condition: at least one pattern has matches > 0', () => {
    const v = useViewStore()
    v.loadScanFile(makeFile())
    // CCC bbb matched=1, BBB bo_only matched=1, AAA both >0 → all 3 in union
    expect(v.unionRows.map(r => r.symbol).sort()).toEqual(['AAA', 'BBB', 'CCC'])
  })
})
```

- [ ] **Step 2: 创建 `path2_web_ui/tests/view.multi.spec.ts`**

```ts
import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useViewStore } from '../src/stores/view'
import { useConfigStore } from '../src/stores/config'
import type { MultiScanResultFile } from '../src/types'

function makeFile(): MultiScanResultFile {
  return {
    pattern_ids: ['bo_only', 'bbb'],
    per_pattern: {
      bo_only: { pattern_spec: { pattern_id: 'bo_only', display_name: 'bo', topology: { nodes: [], edges: [] }, event_styles: {} }, end_role: 'bo' },
      bbb:     { pattern_spec: { pattern_id: 'bbb',     display_name: 'bbb', topology: { nodes: [], edges: [] }, event_styles: {} }, end_role: 'tb' },
    },
    scan: {
      scan_ts: '20260627T120000', start_date: '2024-01-01', end_date: '2024-06-30',
      workers: 1, scanned: 1, hits: 1, errors: 0, dataset_dir: '/d', params: 'default',
      win_start: '2023-09-01', win_end: '2024-07-15', label_horizon: 20,
    },
    results: [
      { symbol: 'AAA', per_pattern: {
        bo_only: { summary: { matches: 1 }, analysis: { events: [], matches: [] }, max_forward_return: 0.1 },
        bbb:     { summary: { matches: 1 }, analysis: { events: [], matches: [] }, max_forward_return: 0.2 },
      }},
    ],
  }
}

describe('view store — multi pattern', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('loadScanFile prefers config.last_selected_pattern when in pattern_ids', () => {
    const cfg = useConfigStore()
    cfg.config.last_selected_pattern = 'bbb'
    const v = useViewStore()
    v.loadScanFile(makeFile())
    expect(v.activePatternId).toBe('bbb')
  })

  it('loadScanFile falls back to pattern_ids[0] when last_selected not in pattern_ids', () => {
    const cfg = useConfigStore()
    cfg.config.last_selected_pattern = 'not_present'
    const v = useViewStore()
    v.loadScanFile(makeFile())
    expect(v.activePatternId).toBe('bo_only')
  })

  it('pattern computed reflects activePatternId', () => {
    const v = useViewStore()
    v.loadScanFile(makeFile())
    v.setActivePattern('bo_only')
    expect(v.pattern?.pattern_id).toBe('bo_only')
    v.setActivePattern('bbb')
    expect(v.pattern?.pattern_id).toBe('bbb')
  })

  it('currentAnalysis reads per_pattern[activePatternId].analysis', () => {
    const v = useViewStore()
    v.loadScanFile(makeFile())
    v.selectSymbol('AAA')
    v.setActivePattern('bo_only')
    expect(v.currentAnalysis).not.toBeNull()
  })

  it('effective triple uses preview when symbol AND pattern_id match', () => {
    const v = useViewStore()
    v.loadScanFile(makeFile())
    v.selectSymbol('AAA')
    v.setActivePattern('bo_only')
    // Mock preview state
    ;(v as any).preview = {
      symbol: 'AAA',
      analysis: { events: [{}], matches: [] },
      pattern_spec: { pattern_id: 'bo_only', display_name: 'preview-bo', topology: { nodes: [], edges: [] }, event_styles: {} },
      scan: {},
    }
    ;(v as any).previewEnabled = true
    expect(v.effectivePattern?.display_name).toBe('preview-bo')
    // 切到 bbb → preview pattern_id 不匹配 → 退回扫描结果
    v.setActivePattern('bbb')
    expect(v.effectivePattern?.pattern_id).toBe('bbb')
  })
})
```

- [ ] **Step 3: 改 `path2_web_ui/src/stores/view.ts`(几乎重写)**

替换文件:

```ts
// 视图状态:scanFile / symbol / activePatternId / role 显隐 / 选中对象;
// 派生 unionRows/sortedRows/pattern/currentAnalysis/effective 三件套。
import { defineStore } from 'pinia'
import { computed, ref, shallowRef, watch } from 'vue'
import type {
  MultiScanResultFile, StockResult, PerPatternResult,
  MatchDict, EventDict, Tier, Diagnostics, Level, SerializedPattern, Analysis, ScanMeta,
} from '../types'
import { deriveRoleColors } from '../render/colors'
import {
  deriveTagMap, isolatedNodeIds,
  qualifiedIdsOf, matchedIds as matchedIdsOf,
  bandKeyOf, eventTierOf, windowOf,
} from '../render/visible'
import { getDiagnose, getPreview, type PreviewResp } from '../api'
import { useConfigStore } from './config'

export type Selected =
  | { kind: 'match'; matchId: string }
  | { kind: 'role'; nodeId: string }
  | null

export type UnionCell = { pid: string; max_ret: number | null; matched: boolean }
export type UnionRow  = { symbol: string; cells: UnionCell[] }

export const useViewStore = defineStore('view', () => {
  // ── state ────────────────────────────────────────────────────────
  const scanFile = ref<MultiScanResultFile | null>(null)
  const symbol = ref<string | null>(null)
  const activePatternId = ref<string | null>(null)
  const sortByPid = ref<string | null>(null)
  const sortDesc = ref(true)

  const roleVisible = ref<Record<string, boolean>>({})
  const selected = ref<Selected>(null)
  const level = ref<Level>('matched')
  const selectedEventId = ref<string | null>(null)
  const hoveredEventId = ref<string | null>(null)
  const diag = ref<Diagnostics | null>(null)

  const previewEnabled = ref(false)
  const preview = shallowRef<{
    symbol: string
    analysis: PreviewResp['analysis']
    pattern_spec: PreviewResp['pattern_spec']
    scan: PreviewResp['scan']
  } | null>(null)
  const previewLoading = ref(false)
  const previewError = ref<string | null>(null)

  // ── computed ─────────────────────────────────────────────────────
  const patternIds = computed<string[]>(() => scanFile.value?.pattern_ids ?? [])

  const currentPerStock = computed<StockResult | null>(() =>
    scanFile.value?.results.find(r => r.symbol === symbol.value) ?? null)

  const pattern = computed<SerializedPattern | null>(() => {
    if (!activePatternId.value || !scanFile.value) return null
    return scanFile.value.per_pattern[activePatternId.value]?.pattern_spec ?? null
  })

  const currentAnalysis = computed<Analysis | null>(() => {
    if (!activePatternId.value) return null
    return currentPerStock.value?.per_pattern[activePatternId.value]?.analysis ?? null
  })

  // preview-aware effective 三件套
  const _previewHits = computed(() =>
    previewEnabled.value && preview.value
    && preview.value.symbol === symbol.value
    && preview.value.pattern_spec.pattern_id === activePatternId.value)

  const effectivePattern = computed<SerializedPattern | null>(() =>
    _previewHits.value ? preview.value!.pattern_spec : pattern.value)

  const effectiveAnalysis = computed<Analysis | null>(() =>
    _previewHits.value ? preview.value!.analysis : currentAnalysis.value)

  const effectiveScan = computed<ScanMeta | PreviewResp['scan'] | null>(() => {
    if (_previewHits.value) return preview.value!.scan
    return scanFile.value?.scan ?? null
  })

  // 列表 union / sort
  const unionRows = computed<UnionRow[]>(() => {
    const f = scanFile.value
    if (!f) return []
    return f.results.map(r => ({
      symbol: r.symbol,
      cells: f.pattern_ids.map(pid => {
        const pp: PerPatternResult | undefined = r.per_pattern[pid]
        return {
          pid,
          max_ret: pp?.max_forward_return ?? null,
          matched: (pp?.summary?.matches ?? 0) > 0,
        }
      }),
    }))
  })

  const sortedRows = computed<UnionRow[]>(() => {
    const rows = unionRows.value
    const pid = sortByPid.value
    if (!pid) return rows
    const dir = sortDesc.value ? -1 : 1
    return [...rows].sort((a, b) => {
      const av = a.cells.find(c => c.pid === pid)?.max_ret
      const bv = b.cells.find(c => c.pid === pid)?.max_ret
      // null 永远沉底(无论升降)
      if (av == null && bv == null) return 0
      if (av == null) return 1
      if (bv == null) return -1
      return (av - bv) * dir
    })
  })

  // K 线 / 拓扑 等下游派生(同旧)
  const roleColors = computed(() =>
    effectivePattern.value ? deriveRoleColors(effectivePattern.value.topology, effectivePattern.value.event_styles) : {})

  // ── actions ──────────────────────────────────────────────────────
  function loadScanFile(f: MultiScanResultFile) {
    scanFile.value = f
    roleVisible.value = {}
    selected.value = null
    selectedEventId.value = null
    hoveredEventId.value = null
    sortByPid.value = null
    sortDesc.value = true
    symbol.value = f.results[0]?.symbol ?? null
    previewEnabled.value = false
    preview.value = null
    previewError.value = null
    // active 默认值:优先 config.last_selected_pattern 若在 pattern_ids 中
    const cfg = useConfigStore()
    const last = cfg.config?.last_selected_pattern
    activePatternId.value = (last && f.pattern_ids.includes(last))
      ? last : (f.pattern_ids[0] ?? null)
  }
  function clearScanFile() {
    scanFile.value = null
    symbol.value = null
    activePatternId.value = null
    sortByPid.value = null
    roleVisible.value = {}
    selected.value = null
    selectedEventId.value = null
    hoveredEventId.value = null
    previewEnabled.value = false
    preview.value = null
    previewError.value = null
  }
  function selectSymbol(s: string) {
    // 锚-active 解耦:只切股、不动 activePatternId
    symbol.value = s
    selected.value = null
    selectedEventId.value = null
    hoveredEventId.value = null
    preview.value = null
    previewError.value = null
    if (previewEnabled.value) void runPreview()
  }
  function setActivePattern(pid: string) {
    activePatternId.value = pid
    const cfg = useConfigStore()
    if (cfg.config) cfg.config.last_selected_pattern = pid
    if (previewEnabled.value) void runPreview()
  }
  function setSort(pid: string) {
    if (sortByPid.value === pid) {
      sortDesc.value = !sortDesc.value
    } else {
      sortByPid.value = pid
      sortDesc.value = true
    }
  }
  function toggleRole(nodeId: string) {
    roleVisible.value = { ...roleVisible.value, [nodeId]: roleVisible.value[nodeId] === false }
  }
  function selectMatch(matchId: string) { selected.value = { kind: 'match', matchId } }
  function selectRole(nodeId: string) { selected.value = { kind: 'role', nodeId } }
  function clearSelection() { selected.value = null }
  function setLevel(l: Level) { level.value = l }
  function selectEvent(id: string | null) { selectedEventId.value = id }
  function hoverEvent(id: string | null) { hoveredEventId.value = id }

  async function setPreviewEnabled(v: boolean): Promise<void> {
    previewEnabled.value = v
    if (v) await runPreview()
    else { preview.value = null; previewError.value = null }
  }

  async function runPreview(): Promise<void> {
    if (!scanFile.value || !symbol.value || !activePatternId.value) return
    previewLoading.value = true
    previewError.value = null
    const reqSymbol = symbol.value
    const reqPid = activePatternId.value
    const reqEnabled = previewEnabled.value
    try {
      const baseScan = scanFile.value.scan
      const labelHorizon = baseScan.label_horizon ?? 20
      const resp = await getPreview(reqPid, reqSymbol,
                                     baseScan.start_date, baseScan.end_date, labelHorizon)
      if (symbol.value !== reqSymbol || activePatternId.value !== reqPid
          || previewEnabled.value !== reqEnabled) return
      preview.value = { symbol: reqSymbol, analysis: resp.analysis,
                        pattern_spec: resp.pattern_spec, scan: resp.scan }
    } catch (e: any) {
      if (symbol.value !== reqSymbol || activePatternId.value !== reqPid
          || previewEnabled.value !== reqEnabled) return
      previewError.value = String(e?.message ?? e)
    } finally {
      if (symbol.value === reqSymbol && activePatternId.value === reqPid
          && previewEnabled.value === reqEnabled)
        previewLoading.value = false
    }
  }
  function clearPreview(): void {
    preview.value = null
    previewError.value = null
  }

  // diag 预取 watch:依赖 activePatternId
  watch([symbol, scanFile, activePatternId, preview, previewEnabled], async () => {
    if (!symbol.value || !scanFile.value || !activePatternId.value) {
      diag.value = null
      return
    }
    const reqSymbol = symbol.value
    const reqPid = activePatternId.value
    try {
      const eff = effectiveScan.value ?? scanFile.value.scan
      const w = windowOf(eff as any)
      const d = await getDiagnose(reqPid, symbol.value, w.start, w.end)
      if (symbol.value !== reqSymbol || activePatternId.value !== reqPid) return
      diag.value = d
    } catch { if (symbol.value === reqSymbol && activePatternId.value === reqPid) diag.value = null }
  }, { immediate: true })

  const selectedMatch = computed<MatchDict | null>(() => {
    const sel = selected.value
    if (sel?.kind !== 'match' || !effectiveAnalysis.value) return null
    return effectiveAnalysis.value.matches.find(m => m.event_id === sel.matchId) ?? null
  })

  const tagMap = computed(() => effectivePattern.value
    ? deriveTagMap(effectivePattern.value.topology.nodes)
    : { tagToNodes: {} as Record<string, string[]>, tagList: [] as string[] })

  const isolated = computed<Set<string>>(() => effectivePattern.value
    ? isolatedNodeIds(effectivePattern.value.topology) : new Set())

  const matchedIds = computed<Set<string>>(() => matchedIdsOf(
    effectiveAnalysis.value?.matches ?? [], effectiveAnalysis.value?.events ?? []))

  const qualifiedIds = computed<Set<string>>(() => qualifiedIdsOf(diag.value))

  function bandKey(e: EventDict): string { return bandKeyOf(e, tagMap.value.tagList) }
  function eventTier(e: EventDict): Tier { return eventTierOf(e, matchedIds.value, qualifiedIds.value) }

  return {
    scanFile, symbol, activePatternId, sortByPid, sortDesc,
    roleVisible, selected,
    level, selectedEventId, hoveredEventId, diag,
    previewEnabled, preview, previewLoading, previewError,
    patternIds, currentPerStock, pattern, currentAnalysis,
    effectivePattern, effectiveAnalysis, effectiveScan,
    unionRows, sortedRows,
    roleColors, selectedMatch, tagMap, isolated, matchedIds, qualifiedIds,
    loadScanFile, clearScanFile, selectSymbol, setActivePattern, setSort,
    toggleRole, selectMatch, selectRole, clearSelection,
    setLevel, selectEvent, hoverEvent,
    setPreviewEnabled, runPreview, clearPreview,
    bandKey, eventTier,
  }
})
```

- [ ] **Step 4: 跑 vitest 验证**

```bash
cd path2_web_ui && npm run test -- unionRows view.multi
```

Expected: 全 PASS

- [ ] **Step 5: 跑全套 vitest 看其他组件 spec 哪些破**

```bash
cd path2_web_ui && npm run test
```

记录 fail 列表(KlineChart/DetailSidebar 等组件 spec 可能因 store API 变化 fail),后续 task 一并修。

- [ ] **Step 6: Commit**

```bash
git add path2_web_ui/src/stores/view.ts path2_web_ui/tests/unionRows.spec.ts path2_web_ui/tests/view.multi.spec.ts
git commit -m "feat(ui): view store activePatternId + unionRows + sortedRows + preview-aware effective triple"
```

---

## Task 10: SidebarPatternPanel checkbox 多选

**Files:**
- Modify: `path2_web_ui/src/components/SidebarPatternPanel.vue`
- Test: 新建 `path2_web_ui/tests/components/SidebarPatternPanel.multi.spec.ts`

**Interfaces:**
- Consumes: `usePatternsStore().{list, selectedIds, toggleSelected, selectAll, selectNone, invertSelection}`

- [ ] **Step 1: 创建 spec `path2_web_ui/tests/components/SidebarPatternPanel.multi.spec.ts`**

```ts
import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { mount } from '@vue/test-utils'
import SidebarPatternPanel from '../../src/components/SidebarPatternPanel.vue'
import { usePatternsStore } from '../../src/stores/patterns'

const patternsFixture = [
  { pattern_id: 'bo_only', display_name: 'bo', topology: { nodes: [], edges: [] }, event_styles: {} },
  { pattern_id: 'bbb',     display_name: 'BBB pattern', topology: { nodes: [], edges: [] }, event_styles: {} },
]

describe('SidebarPatternPanel — checkbox multi-select', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('renders one checkbox per pattern', () => {
    const ps = usePatternsStore()
    ps.list = patternsFixture as any
    ps.loaded = true
    const w = mount(SidebarPatternPanel)
    const checks = w.findAll('input[type="checkbox"]')
    expect(checks.length).toBeGreaterThanOrEqual(2)
  })

  it('click checkbox toggles selectedIds', async () => {
    const ps = usePatternsStore()
    ps.list = patternsFixture as any
    ps.loaded = true
    const w = mount(SidebarPatternPanel)
    const firstCheck = w.find('input[type="checkbox"][data-pid="bo_only"]')
    await firstCheck.setValue(true)
    expect(ps.selectedIds.has('bo_only')).toBe(true)
    await firstCheck.setValue(false)
    expect(ps.selectedIds.has('bo_only')).toBe(false)
  })

  it('Select All button selects all', async () => {
    const ps = usePatternsStore()
    ps.list = patternsFixture as any
    ps.loaded = true
    const w = mount(SidebarPatternPanel)
    await w.find('[data-action="select-all"]').trigger('click')
    expect(ps.selectedIds.size).toBe(2)
  })

  it('Clear button clears selection', async () => {
    const ps = usePatternsStore()
    ps.list = patternsFixture as any
    ps.loaded = true
    ps.selectAll()
    const w = mount(SidebarPatternPanel)
    await w.find('[data-action="select-none"]').trigger('click')
    expect(ps.selectedIds.size).toBe(0)
  })
})
```

- [ ] **Step 2: 跑测试确认红失败**

```bash
cd path2_web_ui && npm run test -- SidebarPatternPanel
```

Expected: 因 SidebarPatternPanel 现是 radio 而非 checkbox → FAIL

- [ ] **Step 3: 改 `path2_web_ui/src/components/SidebarPatternPanel.vue`**

```vue
<template>
  <div class="panel">
    <div class="hdr">
      <span class="title">Patterns</span>
      <div class="actions">
        <button data-action="select-all"  @click="ps.selectAll">全选</button>
        <button data-action="select-none" @click="ps.selectNone">清空</button>
        <button data-action="invert"      @click="ps.invertSelection">反选</button>
      </div>
    </div>
    <div v-if="!ps.loaded" class="hint">加载中…</div>
    <div v-for="p in ps.list" :key="p.pattern_id" class="row">
      <label>
        <input type="checkbox"
               :data-pid="p.pattern_id"
               :checked="ps.selectedIds.has(p.pattern_id)"
               @change="ps.toggleSelected(p.pattern_id)" />
        <span class="name">{{ p.display_name }}</span>
        <span class="pid" :title="p.pattern_id">{{ p.pattern_id }}</span>
      </label>
    </div>
  </div>
</template>

<script setup lang="ts">
import { usePatternsStore } from '../stores/patterns'
const ps = usePatternsStore()
</script>

<style scoped>
.panel { padding: 6px 10px; border-bottom: 1px solid #e5e7eb; }
.hdr { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.title { font-weight: 600; }
.actions button { font-size: 11px; margin-left: 4px; padding: 1px 6px;
                  border: 1px solid #cbd5e1; background: #fff; cursor: pointer; }
.row { padding: 2px 0; }
.row label { display: flex; align-items: center; gap: 6px; cursor: pointer; font-size: 12px; }
.name { font-weight: 500; }
.pid { color: #94a3b8; font-size: 10px; }
.hint { font-size: 12px; color: #64748b; }
</style>
```

- [ ] **Step 4: 跑测试确认绿**

```bash
cd path2_web_ui && npm run test -- SidebarPatternPanel
```

Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
git add path2_web_ui/src/components/SidebarPatternPanel.vue path2_web_ui/tests/components/SidebarPatternPanel.multi.spec.ts
git commit -m "feat(ui): SidebarPatternPanel checkbox multi-select"
```

---

## Task 11: SidebarScanPanel button + body 改

**Files:**
- Modify: `path2_web_ui/src/components/SidebarScanPanel.vue`

**Interfaces:**
- Consumes: `usePatternsStore().selectedArray`、`useScanStore().run(req)`
- Produces: 起扫描按钮 disabled 条件 = `selectedArray.length === 0`;run body 用 `pattern_ids: selectedArray`

- [ ] **Step 1: 阅读现有 `SidebarScanPanel.vue`**

```bash
cat /home/yu/PycharmProjects/Trade_Strategy/path2_web_ui/src/components/SidebarScanPanel.vue
```

- [ ] **Step 2: 改 `SidebarScanPanel.vue`**

在 `<script setup>` 中,把 `usePatternsStore().selectedId` 引用全部改为 `usePatternsStore().selectedArray`:
- 起扫描按钮的 `:disabled` 中,把 `!patterns.selectedId` 改为 `patterns.selectedArray.length === 0`
- 调 `scan.run({...})` 时,把 `pattern_id: patterns.selectedId` 改为 `pattern_ids: patterns.selectedArray`
- 其余(start_date/end_date/workers/label_horizon)不动

不需要写专门 spec(Task 10 的 selectAll 已间接验证 selectedArray 行为)。

- [ ] **Step 3: 跑 build 确认无 TS error**

```bash
cd path2_web_ui && npx vue-tsc --noEmit
```

Expected: SidebarScanPanel 这块无错(其他组件 task 后续修)

- [ ] **Step 4: Commit**

```bash
git add path2_web_ui/src/components/SidebarScanPanel.vue
git commit -m "feat(ui): SidebarScanPanel uses selectedArray + pattern_ids body"
```

---

## Task 12: SidebarResultList N 列 + 列头排序 + cell 只切股

**Files:**
- Modify: `path2_web_ui/src/components/SidebarResultList.vue`
- Test: 新建 `path2_web_ui/tests/components/SidebarResultList.multi.spec.ts`

**Interfaces:**
- Consumes: `useViewStore().{scanFile, symbol, patternIds, sortedRows, sortByPid, sortDesc, selectSymbol, setSort}` + preview 工具栏(同旧 effectivePattern 视角)

- [ ] **Step 1: 创建 `SidebarResultList.multi.spec.ts`**

```ts
import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { mount } from '@vue/test-utils'
import SidebarResultList from '../../src/components/SidebarResultList.vue'
import { useViewStore } from '../../src/stores/view'

const emptyAnalysis = { events: [], matches: [] }
const file = {
  pattern_ids: ['bo_only', 'bbb'],
  per_pattern: {
    bo_only: { pattern_spec: { pattern_id: 'bo_only', display_name: 'BO', topology: { nodes: [], edges: [] }, event_styles: {} }, end_role: 'bo' },
    bbb:     { pattern_spec: { pattern_id: 'bbb',     display_name: 'BBB', topology: { nodes: [], edges: [] }, event_styles: {} }, end_role: 'tb' },
  },
  scan: { scan_ts: '20260627T120000', start_date: '2024-01-01', end_date: '2024-06-30',
          workers: 1, scanned: 2, hits: 2, errors: 0, dataset_dir: '/d', params: 'd',
          win_start: '2023-09-01', win_end: '2024-07-15', label_horizon: 20 },
  results: [
    { symbol: 'AAA', per_pattern: {
      bo_only: { summary: { matches: 1 }, analysis: emptyAnalysis, max_forward_return: 0.34 },
      bbb:     { summary: { matches: 1 }, analysis: emptyAnalysis, max_forward_return: 0.10 },
    }},
    { symbol: 'BBB', per_pattern: {
      bo_only: { summary: { matches: 1 }, analysis: emptyAnalysis, max_forward_return: 0.50 },
      bbb:     { summary: { matches: 0 }, analysis: emptyAnalysis, max_forward_return: null },
    }},
  ],
}

describe('SidebarResultList — multi-pattern', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('renders N column headers from pattern_ids', () => {
    const v = useViewStore()
    v.loadScanFile(file as any)
    const w = mount(SidebarResultList)
    const ths = w.findAll('th[data-col-pid]')
    const pids = ths.map(th => th.attributes('data-col-pid'))
    expect(pids).toEqual(['bo_only', 'bbb'])
  })

  it('renders max_forward_return per cell, null shows —', () => {
    const v = useViewStore()
    v.loadScanFile(file as any)
    const w = mount(SidebarResultList)
    const cells = w.findAll('td[data-cell-pid]')
    // BBB.bbb 的单元格是 null
    const bbb_bbb = cells.find(c =>
      c.element.closest('tr')?.querySelector('.sym')?.textContent === 'BBB'
      && c.attributes('data-cell-pid') === 'bbb')!
    expect(bbb_bbb.text()).toContain('—')
  })

  it('clicking column header sets sortByPid desc; second click flips asc', async () => {
    const v = useViewStore()
    v.loadScanFile(file as any)
    const w = mount(SidebarResultList)
    const th = w.find('th[data-col-pid="bo_only"]')
    await th.trigger('click')
    expect(v.sortByPid).toBe('bo_only')
    expect(v.sortDesc).toBe(true)
    await th.trigger('click')
    expect(v.sortDesc).toBe(false)
  })

  it('cell click selects symbol but does NOT change activePatternId', async () => {
    const v = useViewStore()
    v.loadScanFile(file as any)
    v.setActivePattern('bbb')
    const before = v.activePatternId
    const w = mount(SidebarResultList)
    const td = w.find('td[data-cell-pid="bo_only"]')
    await td.trigger('click')
    expect(v.activePatternId).toBe(before)        // 不变
    // 切了股
    expect(v.symbol).toBeTruthy()
  })

  it('symbol cell click selects symbol', async () => {
    const v = useViewStore()
    v.loadScanFile(file as any)
    const w = mount(SidebarResultList)
    const sym = w.find('td.sym')
    await sym.trigger('click')
    expect(v.symbol).toBeTruthy()
  })

  it('matched cells get .matched class', () => {
    const v = useViewStore()
    v.loadScanFile(file as any)
    const w = mount(SidebarResultList)
    // AAA bbb matched=1 → .matched
    const c = w.findAll('td[data-cell-pid="bbb"]')
      .find(td => td.element.closest('tr')?.querySelector('.sym')?.textContent === 'AAA')!
    expect(c.classes()).toContain('matched')
  })
})
```

- [ ] **Step 2: 跑测试看 fail**

```bash
cd path2_web_ui && npm run test -- SidebarResultList
```

Expected: 现 SidebarResultList 还是单列 + badges → FAIL

- [ ] **Step 3: 改 `SidebarResultList.vue` — 重写表格 + 排序**

```vue
<template>
  <div class="list">
    <div class="preview-bar">
      <label class="toggle">
        <input type="checkbox" :checked="previewEnabled"
               :disabled="!scanFile"
               @change="onToggle($event)" />
        <span>用 yaml 临时计算</span>
        <button class="refresh" title="重算当前股(yaml 改过后用)"
                :disabled="!canRefresh" @click="view.runPreview">↻</button>
      </label>
      <div v-if="previewLoading" class="status">计算中…</div>
      <div v-if="previewError" class="error">
        临时计算失败: {{ previewError }}
        <a @click="onCloseError">×</a>
      </div>
    </div>

    <div v-if="!scanFile" class="hint">未加载扫描结果</div>
    <table v-else class="multi">
      <thead>
        <tr>
          <th class="sym">symbol</th>
          <th v-for="pid in patternIds" :key="pid"
              :data-col-pid="pid"
              :title="pid"
              class="col"
              @click="view.setSort(pid)">
            {{ displayNameOf(pid) }}
            <span v-if="sortByPid === pid" class="sort-ind">
              {{ sortDesc ? '▼' : '▲' }}
            </span>
          </th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in sortedRows" :key="row.symbol"
            :class="{ active: row.symbol === symbol }">
          <td class="sym" @click="view.selectSymbol(row.symbol)">{{ row.symbol }}</td>
          <td v-for="cell in row.cells" :key="cell.pid"
              :data-cell-pid="cell.pid"
              :class="['col', { matched: cell.matched }]"
              @click="view.selectSymbol(row.symbol)">
            {{ fmt(cell.max_ret) }}
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { storeToRefs } from 'pinia'
import { useViewStore } from '../stores/view'
const view = useViewStore()
const { scanFile, symbol, preview, previewEnabled, previewLoading, previewError,
        patternIds, sortedRows, sortByPid, sortDesc } = storeToRefs(view)

const canRefresh = computed(() =>
  previewEnabled.value && !!preview.value && !previewLoading.value
  && preview.value?.symbol === symbol.value)

function displayNameOf(pid: string): string {
  return scanFile.value?.per_pattern[pid]?.pattern_spec.display_name ?? pid
}
function fmt(v: number | null): string {
  if (v == null) return '—'
  const pct = (v * 100).toFixed(1)
  return v >= 0 ? `+${pct}%` : `${pct}%`
}
function onToggle(e: Event) {
  void view.setPreviewEnabled((e.target as HTMLInputElement).checked)
}
function onCloseError() { view.clearPreview() }
</script>

<style scoped>
.list { overflow-y: auto; height: 100%; display: flex; flex-direction: column; }
.preview-bar { padding: 6px 10px; border-bottom: 1px solid #e5e7eb; background: #f8fafc; }
.toggle { display: flex; align-items: center; gap: 6px; cursor: pointer; font-size: 12px; }
.toggle input { cursor: pointer; }
.refresh { margin-left: auto; padding: 1px 6px; font-size: 14px;
           border: 1px solid #cbd5e1; background: #fff; cursor: pointer; }
.refresh:disabled { opacity: 0.4; cursor: not-allowed; }
.status { font-size: 11px; color: #64748b; margin-top: 4px; }
.error { font-size: 11px; color: #ef4444; margin-top: 4px; }
.error a { cursor: pointer; margin-left: 6px; }

.hint { padding: 8px 12px; font-size: 12px; color: #64748b; }
table.multi { width: 100%; border-collapse: collapse; font-size: 12px; }
table.multi th, table.multi td { padding: 4px 6px; border-bottom: 1px solid #f1f5f9; text-align: left; }
table.multi th.col { cursor: pointer; user-select: none; }
table.multi th.col:hover { background: #f1f5f9; }
table.multi .sort-ind { color: #2563eb; margin-left: 2px; }
table.multi td.sym { font-weight: 600; cursor: pointer; }
table.multi td.col { cursor: pointer; text-align: right; background: #fafafa; }
table.multi td.col.matched { background: #dcfce7; }
tr.active { background: #eff6ff; }
</style>
```

- [ ] **Step 4: 跑测试,确认绿**

```bash
cd path2_web_ui && npm run test -- SidebarResultList
```

Expected: 6 PASS

- [ ] **Step 5: Commit**

```bash
git add path2_web_ui/src/components/SidebarResultList.vue path2_web_ui/tests/components/SidebarResultList.multi.spec.ts
git commit -m "feat(ui): SidebarResultList N columns + sortable headers + cell click只切股"
```

---

## Task 13: ChartArea 顶部 active pattern dropdown

**Files:**
- Modify: `path2_web_ui/src/components/ChartArea.vue`
- Test: 新建 `path2_web_ui/tests/components/ChartArea.activePattern.spec.ts`

**Interfaces:**
- Consumes: `useViewStore().{patternIds, activePatternId, setActivePattern, scanFile}`

- [ ] **Step 1: 创建 spec**

```ts
import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { mount } from '@vue/test-utils'
import ChartArea from '../../src/components/ChartArea.vue'
import { useViewStore } from '../../src/stores/view'

const file = {
  pattern_ids: ['bo_only', 'bbb'],
  per_pattern: {
    bo_only: { pattern_spec: { pattern_id: 'bo_only', display_name: 'BO', topology: { nodes: [], edges: [] }, event_styles: {} }, end_role: 'bo' },
    bbb:     { pattern_spec: { pattern_id: 'bbb', display_name: 'BBB', topology: { nodes: [], edges: [] }, event_styles: {} }, end_role: 'tb' },
  },
  scan: { scan_ts: '20260627T120000', start_date: '2024-01-01', end_date: '2024-06-30',
          workers: 1, scanned: 1, hits: 1, errors: 0, dataset_dir: '/d', params: 'd',
          win_start: '2023-09-01', win_end: '2024-07-15', label_horizon: 20 },
  results: [],
}

describe('ChartArea — active pattern dropdown', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('renders select with one option per pattern_id', () => {
    const v = useViewStore()
    v.loadScanFile(file as any)
    const w = mount(ChartArea)
    const sel = w.find('select[data-role="active-pattern"]')
    expect(sel.exists()).toBe(true)
    const opts = sel.findAll('option')
    expect(opts.map(o => o.attributes('value'))).toEqual(['bo_only', 'bbb'])
  })

  it('change select calls setActivePattern', async () => {
    const v = useViewStore()
    v.loadScanFile(file as any)
    const w = mount(ChartArea)
    const sel = w.find('select[data-role="active-pattern"]')
    await sel.setValue('bbb')
    expect(v.activePatternId).toBe('bbb')
  })
})
```

- [ ] **Step 2: 阅读 ChartArea 现有结构**

```bash
cat /home/yu/PycharmProjects/Trade_Strategy/path2_web_ui/src/components/ChartArea.vue | head -60
```

- [ ] **Step 3: 在 ChartArea 顶部 level 控件附近插入 `<select>`**

定位现有 level 控件 `<div class="level-control">` 或类似容器,在同一行加入:

```vue
<select :value="view.activePatternId ?? ''"
        data-role="active-pattern"
        @change="onActivePatternChange"
        class="active-pattern-select"
        v-if="view.patternIds.length > 0">
  <option v-for="pid in view.patternIds" :key="pid" :value="pid">
    {{ view.scanFile?.per_pattern[pid]?.pattern_spec.display_name ?? pid }}
  </option>
</select>
```

`<script setup>` 中加:
```ts
function onActivePatternChange(e: Event) {
  view.setActivePattern((e.target as HTMLSelectElement).value)
}
```

`<style scoped>` 中加:
```css
.active-pattern-select { margin-left: 8px; font-size: 12px; padding: 2px 4px; }
```

- [ ] **Step 4: 跑测试**

```bash
cd path2_web_ui && npm run test -- ChartArea.activePattern
```

Expected: 2 PASS

- [ ] **Step 5: Commit**

```bash
git add path2_web_ui/src/components/ChartArea.vue path2_web_ui/tests/components/ChartArea.activePattern.spec.ts
git commit -m "feat(ui): ChartArea top dropdown for active pattern selection"
```

---

## Task 14: ScanResultDialog 改读扁平 /scans 路径

**Files:**
- Modify: `path2_web_ui/src/components/ScanResultDialog.vue`

**Interfaces:**
- Consumes: `useScanStore().{history, refreshHistory, open, remove}`(history entry 已含 pattern_ids)

- [ ] **Step 1: 阅读现有实现**

```bash
cat /home/yu/PycharmProjects/Trade_Strategy/path2_web_ui/src/components/ScanResultDialog.vue
```

- [ ] **Step 2: 改 ScanResultDialog**

把所有 `useScanStore().refreshHistory(patternId)` 改为 `useScanStore().refreshHistory()`;`open(patternId, scanTs)` 改为 `open(scanTs)`;`remove(patternId, scanTs)` 改为 `remove(scanTs)`。

每行渲染加 pattern_ids chips(竖排或横排):
```vue
<span v-for="pid in entry.pattern_ids" :key="pid" class="chip">{{ pid }}</span>
```

`<style scoped>` 加:
```css
.chip { display: inline-block; padding: 1px 6px; background: #e5e7eb;
        border-radius: 8px; font-size: 10px; margin-right: 4px; }
```

去掉所有 "选 pattern" 的 prop / 入参——dialog 现在跨 pattern。

- [ ] **Step 3: build 检查**

```bash
cd path2_web_ui && npx vue-tsc --noEmit && npm run build
```

Expected: 全绿

- [ ] **Step 4: Commit**

```bash
git add path2_web_ui/src/components/ScanResultDialog.vue
git commit -m "feat(ui): ScanResultDialog reads flat /scans, shows pattern_ids chips"
```

---

## Task 15: 全链路 gate + 手动 playwright e2e

**Files:**
- 无新建,跑测试

- [ ] **Step 1: 后端全部 pytest**

```bash
uv run pytest tests/path2_web tests/path2_apps -v
```

Expected: 全 PASS(允许 datasets/pkls 不在时的 skip)

- [ ] **Step 2: 前端 vitest + tsc + build**

```bash
cd path2_web_ui && npm run test
cd path2_web_ui && npx vue-tsc --noEmit
cd path2_web_ui && npm run build
```

Expected: 三绿

- [ ] **Step 3: 启动 web 服务**

```bash
uv run python scripts/run_path2_web.py &
sleep 2
```

(假设 `scripts/run_path2_web.py` 是入口;若不是,用 `path2_web/main.py`)

- [ ] **Step 4: 用 playwright MCP 跑 N=1 退化路径手动 e2e**

按 spec §5.2 的 e2e 测试条目 1:
- Navigate to `http://localhost:5173`(或前端实际端口)
- SidebarPatternPanel 只勾 bbb
- 起扫描,等待完成
- 验证列表只有 1 列 ret(bbb)、能点击列头排序
- 点击一只命中股,右侧 K 线 + 拓扑 + 侧栏 渲染正常
- 截图保存

- [ ] **Step 5: N=2 主路径手动 e2e**

按 spec §5.2 的 e2e 测试条目 2:
- SidebarPatternPanel 勾 [bo_only, bbb]
- 起扫描,等待完成
- 验证列表 2 列 ret;点 bo_only 列头降序
- 点一只 bo.ret 高、bbb.ret = — 的股
- 验证:右侧 activePattern dropdown 默认值符合 last_selected_pattern;K 线/拓扑/侧栏 显示 active pattern(bbb)的视图;diag 漏斗显示 detected≥qualified≥matched=0
- 切下拉到 bo_only,验证视图切换
- 切回 bbb,勾"用 yaml 临时计算",验证 preview 加载新 active pattern 的结果
- 截图保存

- [ ] **Step 6: 清理 playwright MCP 临时目录**

```bash
rm -rf .playwright-mcp/*
```

- [ ] **Step 7: 关闭 web 服务**

(取决于运行方式,可手动 fg + Ctrl-C 或 kill PID)

- [ ] **Step 8: Final Commit(若有 e2e 修补)**

```bash
git status
# 若有改动:
git add -A
git commit -m "test: multi-pattern e2e verified (N=1 degenerate + N=2 main path)"
```

---

## Self-Review Notes

(在所有 task 完成后,subagent-driven 的 holistic reviewer 应核对以下几点:)

1. **spec 覆盖**:对 spec §1~§9 每节,本 plan 都有对应 task。§1/§2 原则在 Global Constraints + 各 task 内贯彻;§3 后端→Task 2-5;§4 前端 store/组件→Task 6-14;§5 数据流时序由 worker + view store 共同实现,无单独 task(行为正确性由测试覆盖);§6 错误处理在 discovery gate + 422 校验 + 404 处理;§7 测试在每 task TDD;§8 实施顺序即 Task 1-15;§9 显式排除在本 plan 中不实施。
2. **类型一致性**:`PerPatternResult`(后端 dict 键 `summary/analysis/max_forward_return`)与 TS `PerPatternResult` 字段名一致;`PerPatternMeta` 字段 `pattern_spec/end_role` 前后端一致;`pattern_ids` 在 ScanRequest / done 事件 / ScanHistoryEntry / MultiScanResultFile 同名同序。
3. **铁律落地**:Task 2 discovery 闸,Task 5 删 `resolve_eval_meta` fallback、改 `require_eval_meta`,Task 7 删 `windowOf` fallback,Task 4 永远走 buffered 分支无 None 分支。
4. **锚-active 解耦红线**:Task 9 view store `selectSymbol` 注释明确"不动 activePatternId";Task 12 cell 点击 spec 第 4 条直接验证不变。
5. **N=1 退化**:Task 15 Step 4 专门走 N=1 路径验证视觉无回归。

---

## 执行命令(在新 session 中粘贴)

```
请用 superpowers:subagent-driven-development 执行 docs/superpowers/plans/2026-06-27-path2-web-multi-pattern.md 这份 plan。
- implementer 模型 sonnet;reviewer 模型 opus(每 task spec + quality 双审、最终 holistic 审)。
- 不开 worktree,在当前分支 dag 增量提交。
- 每 task 完成后跑该 task 的测试 gate(后端 uv run pytest、前端 npm run test 等)绿了再进下一 task。
- Task 15 是最终全链路 gate + 手动 playwright e2e,按 plan 步骤跑。
- 整 plan 完成后给出最终 holistic 报告。
```
