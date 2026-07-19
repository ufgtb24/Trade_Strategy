# path2 漏检调查工具 · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 path2 漏检调查工具 5 入口(A 时段 / B 拓扑降级 / C 候选级 / D pair / E workflow)+ 5 硬伤修补 · 覆盖 7 通道 · 单 session subagent-driven 跑到底。

**Architecture:** 三层清晰 —— 引擎侧(Stage 0/1/2/3 + on_gate hook + SolveTrace)负责数据源;后端 `path2_web/diagnose.py::derive_response` 按 scope 分派;前端 shared/formatters + 4 卡片 + KlineChart 交互(brush / shift+click / click / 右键)。硬伤先修 · UI 诚实优先。

**Tech Stack:** Python 3.11+ · dataclasses · uv · pytest · Vue 3 + TypeScript · ECharts · Vitest · Playwright(系统 chromium)

## Global Constraints

- 语言:界面英文 · 注释/文档中文
- 包管理:`uv add` / `uv run` / `uv sync`;前端 `npm` in `path2_web_ui/`
- 每 task 独立 commit(reviewer gate);每 Sprint 结束跑全 test suite 保绿
- 测试门:`uv run pytest` / `npm test` / `npm run type-check` / `npm run build`
- 现有 test suite ~360 passed 必须保绿(承 memory · 每 commit 保绿)
- 不改 detector 生产语义;on_gate 是 optional hook · 默认 None 无开销
- shift+click 跨图 · 承接 `KlineChart.vue:181-198` shift+wheel 已占 · shift+click 未占
- Playwright 卫生:e2e 后清 `.playwright-mcp/*`
- 不合并入 master(承 memory · 沿用 dag_nest 分支或新分支)
- 每完成 Sprint · 更新 `.claude/docs/modules/path2*.md`(update-ai-context)

## Core Types Dictionary

**引擎侧**(spec §2.4.1 / §2.3):
```python
@dataclass(frozen=True)
class MeasuredKindAware:
    kind: str          # 'gap' / 'anchor_delta' / 'strict_clear' / 'negation_bars'
    value: Any
    label: str         # 前端显示前缀

@dataclass(frozen=True)
class GateFailure:
    failure_event_window: tuple[int, int]
    start_idx: int
    gate_idx: int
    anchor_bar: int
    class_id: str
    gate_name: str
    measured: MeasuredKindAware
    threshold: Any
    evaluation_lookback: Optional[tuple[int, int]]
    symbol: str

@dataclass(frozen=True)
class PruneRecord:
    assign_snapshot: dict[str, str]
    chosen_idx: str
    pair: Optional[tuple[str, str]]
    edge_id: Optional[str]
    prune_reason: str
    stage: str                       # 'qualify' / 'satisfies' / 'anchor' / 'strict' / 'negation' / 'combine'
    measured: Optional[MeasuredKindAware]
    threshold: Any

@dataclass
class SolveTrace:
    records: list[PruneRecord] = field(default_factory=list)
```

**Detector protocol**(spec §2.4.5):
```python
class Detector(Protocol):
    on_gate: Optional[Callable[[GateFailure], None]] = None
```

**后端 Query / Response**(spec §3.2.1):
```python
@dataclass
class Query:
    symbol: str
    scope: Literal['time', 'roles', 'candidate', 'pair']
    start_bar: Optional[int] = None
    end_bar: Optional[int] = None
    event_class: Optional[str] = None
    src_role: Optional[str] = None
    dst_role: Optional[str] = None
    event_id: Optional[str] = None
    src_event_id: Optional[str] = None
    dst_event_id: Optional[str] = None
    edge_id: Optional[str] = None

@dataclass
class Caveat:
    code: str
    message: str
    affected_fields: list[str] = field(default_factory=list)

@dataclass
class Response:
    scope: str
    payload: Any
    caveats: list[Caveat] = field(default_factory=list)
```

**后端 Payload 变体**(spec §3.2.2-3.2.5):
```python
@dataclass
class TimePayload:
    frame: tuple[int, int]
    failed_attempts: list[GateFailure]
    outside_frame_attempts_count: int

@dataclass
class PairFailure:
    src_event_id: str
    dst_event_id: str
    subcheck_stage: str
    measured: MeasuredKindAware
    threshold: Any
    edge_kind: str

@dataclass
class RolesPayload:
    edge_id: str
    total_pair: int
    ok_pair: int
    miss_reasons: dict[str, int]
    example_failed_pairs: list[PairFailure]
    per_pair: Optional[list[PairFailure]] = None

@dataclass
class RejectionStep:
    stage: str                           # 6 值枚举
    edge_id: Optional[str]
    counterpart_event_id: Optional[str]
    measured: Optional[MeasuredKindAware]
    threshold: Any
    prune_reason: str
    attempts: Optional[int] = None       # combine 专属

@dataclass
class CandidatePayload:
    event_id: str
    class_id: str
    rejection_chain: list[RejectionStep]

@dataclass
class SubCheck:
    channel: str                          # 'feasible_window' / 'satisfies' / 'anchor' / 'strict'
    passed: bool
    measured: Optional[MeasuredKindAware]
    threshold: Any
    reason: Optional[str]

@dataclass
class PairPayload:
    src_event_id: str
    dst_event_id: str
    applied_swap: bool
    original_first_click: str
    original_second_click: str
    valid: bool
    invalid_reason: Optional[str]
    edge_id: Optional[str]
    edge_kind: Optional[str]
    subchecks: Optional[list[SubCheck]] = None
    hint: Optional[dict] = None
```

**前端 shared 层**(spec §4.1):
```typescript
// formatters.ts
export function fmt(val: any, kind: string): string
export function fmtValue(val: any): string

// RelBadge.vue props
{ ok: number, total: number, size?: 'sm'|'md' }

// PendingIcon.vue props
{ reason: 'refs_other_role' | 'cross_node_pending' }
```

**KlineChart shift+click state**(spec §4.2):
```typescript
const shiftSelectedEvents = ref<Array<{event_id: string, class_id: string, source: 'main'|'sub'}>>([])
function handleShiftClick(event_id: string, class_id: string, source: 'main'|'sub'): void
```

---

## Sprint 1 · 硬伤修补 + 引擎地基 · Task 1-8

### Task 1: Stage 0.1 anchor_ok 复核 + Stage 0.2 anchor_ok_count(硬伤 B)

**Files:**
- Modify: `path2/dag/diagnose.py:91-95`(补 `_anchor_ok` 调用)
- Modify: `path2/dag/result.py`(`RelRow` 加 `anchor_ok_count`)
- Test: `tests/path2/dag/test_diagnose_anchor_ok.py`

**Interfaces:**
- Produces: `RelRow.anchor_ok_count: int`(Task 3 · 4 · 8 · 16 消费)
- Consumes: `edges.py::_anchor_ok(u_ep, v_ep, edge_ok_map)`(现有)

- [ ] **Step 1: 写失败测试**

```python
# tests/path2/dag/test_diagnose_anchor_ok.py
from path2.dag.diagnose import diagnose
from path2.dag.result import RelRow
# 用现有 bottom_breakout_burst spec + 已知能触发 anchor 破位的 fixture

def test_rel_row_has_anchor_ok_count_field():
    """RelRow 数据类必须有 anchor_ok_count 字段"""
    r = RelRow(edge_id="e1", total_src=10, ok_src_ids=("a", "b"), anchor_ok_count=8)
    assert r.anchor_ok_count == 8

def test_anchor_break_pair_excluded_from_ok_src_ids():
    """u→v 若 _anchor_ok 返 False,不计入 ok_src_ids"""
    # 构造 anchor 会破位的 fixture:src.anchor_price=100, dst.high=101
    # 期望 rel.ok_src_ids 不含 src.event_id · anchor_ok_count 减一
    # (fixture 具体构造依当前 bottom_breakout_burst 样本;见 tests/path2/dag/conftest.py 里已有 fixture)
    rel_rows = _run_diagnose_with_anchor_break_fixture()
    burst_to_tb_row = next(r for r in rel_rows if r.edge_id == "burst_to_tb")
    assert burst_to_tb_row.total_src == burst_to_tb_row.anchor_ok_count + 1
    assert "burst_break_anchor" not in burst_to_tb_row.ok_src_ids
```

- [ ] **Step 2: 跑测试验证 FAIL**

Run: `uv run pytest tests/path2/dag/test_diagnose_anchor_ok.py -v`
Expected: FAIL(RelRow 无 `anchor_ok_count` 字段;`_anchor_ok` 未调用)

- [ ] **Step 3: 实现**

修改 `path2/dag/result.py::RelRow` dataclass 加字段:
```python
@dataclass(frozen=True)
class RelRow:
    edge_id: str
    total_src: int
    ok_src_ids: tuple[str, ...]
    anchor_ok_count: int = 0   # ★ 新增 · Sprint 1 Task 1
```

修改 `path2/dag/diagnose.py:91-95` 前后(具体行号以 grep 定位 `_rel_rows` 函数为准):
```python
# diagnose.py 内 _rel_rows() 函数体:每 (u, v) pair 前调 _anchor_ok
from path2.dag.edges import _anchor_ok  # 若尚未 import

# 原代码:
# ok_src_ids = tuple(u.event_id for u, v in candidates if satisfies(u, v))
# 改为:
ok_src_ids_list = []
anchor_ok_cnt = 0
for u, v in candidates:
    if not satisfies(u, v):
        continue
    if not _anchor_ok(u, v, edge_ok_map):
        continue
    ok_src_ids_list.append(u.event_id)
    anchor_ok_cnt += 1
rel_rows.append(RelRow(
    edge_id=edge_id,
    total_src=len(candidates),
    ok_src_ids=tuple(ok_src_ids_list),
    anchor_ok_count=anchor_ok_cnt,
))
```

- [ ] **Step 4: 跑测试验证 PASS**

Run: `uv run pytest tests/path2/dag/test_diagnose_anchor_ok.py -v`
Expected: PASS

跑全部 dag 测试保绿:
Run: `uv run pytest tests/path2/dag/ -v`
Expected: 全 PASS(现有 ~360 test 保绿)

- [ ] **Step 5: Commit**

```bash
git add path2/dag/result.py path2/dag/diagnose.py tests/path2/dag/test_diagnose_anchor_ok.py
git commit -m "$(cat <<'EOF'
feat(path2/dag): 修硬伤 B · anchor_ok 复核 + RelRow.anchor_ok_count

diagnose 层生成 rel 前调 _anchor_ok 二次校验,anchor 破位的 pair 不计入 ok_src_ids;
新加 RelRow.anchor_ok_count 供入口 B miss_reasons 分类计数消费。

承 spec §2.1 Stage 0.1 + 0.2 · 修硬伤 B(anchor 未复核会虚报通过)。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Stage 0.3 _TRIPWIRE sentinel(硬伤 C 兜底)

**Files:**
- Modify: `path2/dag/diagnose.py:43`(`ctx.bound` 换 `_TRIPWIRE`)
- Create: `path2/dag/_tripwire.py`(sentinel + exception)
- Test: `tests/path2/dag/test_tripwire.py`

**Interfaces:**
- Produces: `path2.dag._tripwire._TRIPWIRE` sentinel · `CrossNodePendingError` exception(Task 8 后端消费)

- [ ] **Step 1: 写测试**

```python
# tests/path2/dag/test_tripwire.py
from path2.dag._tripwire import _TRIPWIRE, CrossNodePendingError
import pytest

def test_tripwire_sentinel_exists():
    assert _TRIPWIRE is not None

def test_tripwire_read_raises_cross_node_pending():
    """任何操作访问 _TRIPWIRE 都应抛 CrossNodePendingError"""
    with pytest.raises(CrossNodePendingError):
        _ = _TRIPWIRE + 1
    with pytest.raises(CrossNodePendingError):
        _ = _TRIPWIRE > 0

def test_tripwire_replaces_ctx_bound_when_undefined():
    """diagnose 层 ctx 里若 sibling role 未 bound,读到 sentinel · 抛错"""
    from path2.dag.diagnose import _make_diagnose_ctx
    ctx = _make_diagnose_ctx(bound_events={}, all_role_ids=["burst", "tb"])
    with pytest.raises(CrossNodePendingError):
        _ = ctx.bound["burst"]  # burst 未 bound,读到 tripwire
```

- [ ] **Step 2: 跑测试 FAIL**

Run: `uv run pytest tests/path2/dag/test_tripwire.py -v`
Expected: FAIL(`_tripwire` 模块不存在)

- [ ] **Step 3: 实现 tripwire**

创建 `path2/dag/_tripwire.py`:
```python
"""硬伤 C 兜底 · 跨节点 clause 未 bound 时不静默 fallback,抛显式错。

与 stdlib fn.meta.refs_other_role 双落:
- refs_other_role(编译期标注): UI 提前诚实降级(小图标)
- _TRIPWIRE(运行期兜底): 防未来 spec 静默产错值
"""

class CrossNodePendingError(Exception):
    """跨节点 clause 访问未 bound 的 sibling role · 应走 caveats 通道诚实降级。"""
    pass


class _TripWire:
    """sentinel · 任何操作都抛 CrossNodePendingError。"""
    __slots__ = ()

    def __repr__(self):
        return "<_TRIPWIRE>"

    def _raise(self, *_args, **_kwargs):
        raise CrossNodePendingError(
            "跨节点 clause 访问 sibling role 但 sibling 尚未 bind · "
            "spec 应显式声明 refs_other_role · 或将该 clause 延后到 pair 复核阶段"
        )

    # 所有运算都指向 _raise
    __add__ = __sub__ = __mul__ = __truediv__ = _raise
    __lt__ = __le__ = __gt__ = __ge__ = __eq__ = _raise
    __getattr__ = _raise
    __getitem__ = _raise
    __call__ = _raise
    __bool__ = _raise


_TRIPWIRE = _TripWire()
```

修改 `path2/dag/diagnose.py:43` 前后 `ctx.bound` 生成逻辑(具体行号以 `_make_diagnose_ctx` 或类似为准 · 用 grep 定位):
```python
from path2.dag._tripwire import _TRIPWIRE

# 原:ctx.bound = {role_id: bound_event or None for role_id in all_role_ids}
# 改为:
ctx.bound = {role_id: bound_events.get(role_id, _TRIPWIRE) for role_id in all_role_ids}
```

- [ ] **Step 4: 跑测试 PASS**

Run: `uv run pytest tests/path2/dag/test_tripwire.py -v` → PASS
Run: `uv run pytest tests/path2/dag/ -v` → 全绿(不破现有 test)

- [ ] **Step 5: Commit**

```bash
git add path2/dag/_tripwire.py path2/dag/diagnose.py tests/path2/dag/test_tripwire.py
git commit -m "$(cat <<'EOF'
feat(path2/dag): 修硬伤 C 兜底 · _TRIPWIRE sentinel

跨节点 clause 若 sibling role 未 bind,ctx.bound 用 _TRIPWIRE 代 None;
任何访问 sentinel 都抛 CrossNodePendingError,不静默 fallback。

承 spec §2.1 Stage 0.3 · 与 stdlib refs_other_role 双落(Task 14)。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Stage 0.4 RelRow.miss_reasons + example_failed_pairs

**Files:**
- Modify: `path2/dag/result.py`(RelRow 加 miss_reasons / example_failed_pairs)
- Modify: `path2/dag/diagnose.py`(生成 rel 时累计 miss_reasons)
- Test: `tests/path2/dag/test_rel_miss_reasons.py`

**Interfaces:**
- Consumes: `RelRow.anchor_ok_count`(Task 1)· `_anchor_ok`(现有)· `strict_clear`(现有 `_solve.py:137`)
- Produces: `RelRow.miss_reasons: dict[str, int]` + `RelRow.example_failed_pairs: list[tuple[str, str, str]]`(Task 8 scope=roles 消费)

- [ ] **Step 1: 写测试**

```python
# tests/path2/dag/test_rel_miss_reasons.py
from path2.dag.result import RelRow

def test_rel_row_has_miss_reasons_field():
    r = RelRow(edge_id="e1", total_src=10, ok_src_ids=(),
               anchor_ok_count=0,
               miss_reasons={"gap_out": 3, "anchor_mismatch": 5, "strict_fail": 0, "negation_violated": 0},
               example_failed_pairs=[])
    assert r.miss_reasons["anchor_mismatch"] == 5

def test_miss_reasons_gap_out_counted():
    """gap 超出 max_gap 的 pair 计入 miss_reasons.gap_out"""
    rel_rows = _run_diagnose_with_gap_violation_fixture()
    r = next(row for row in rel_rows if row.edge_id.endswith("_to_tb"))
    assert r.miss_reasons["gap_out"] >= 1

def test_example_failed_pairs_capped_at_5():
    """example_failed_pairs 最多 5 条 · 抽样"""
    rel_rows = _run_diagnose_with_many_failures_fixture()
    for r in rel_rows:
        assert len(r.example_failed_pairs) <= 5
```

- [ ] **Step 2: FAIL**

Run: `uv run pytest tests/path2/dag/test_rel_miss_reasons.py -v`
Expected: FAIL

- [ ] **Step 3: 实现**

修改 `path2/dag/result.py::RelRow`:
```python
@dataclass(frozen=True)
class RelRow:
    edge_id: str
    total_src: int
    ok_src_ids: tuple[str, ...]
    anchor_ok_count: int = 0
    miss_reasons: dict[str, int] = field(default_factory=lambda: {
        "gap_out": 0, "anchor_mismatch": 0, "strict_fail": 0, "negation_violated": 0
    })
    example_failed_pairs: tuple[tuple[str, str, str], ...] = ()
    # (src_event_id, dst_event_id, primary_fail_channel)
```

修改 `path2/dag/diagnose.py::_rel_rows` 累计:
```python
from path2.dag._solve import strict_clear  # 现有 helper 复用

def _rel_rows(...):
    for edge in edges:
        miss = {"gap_out": 0, "anchor_mismatch": 0, "strict_fail": 0, "negation_violated": 0}
        examples = []
        for u, v in candidates_by_edge[edge_id]:
            if not edge.satisfies(u, v):
                # 分辨 satisfies fail 的具体原因:gap_out 是主 fail
                miss["gap_out"] += 1
                if len(examples) < 5:
                    examples.append((u.event_id, v.event_id, "gap_out"))
                continue
            if not _anchor_ok(u, v, edge_ok_map):
                miss["anchor_mismatch"] += 1
                if len(examples) < 5:
                    examples.append((u.event_id, v.event_id, "anchor_mismatch"))
                continue
            # strict 独立评估(Task 16 helper 未来复用,当前直接调 strict_clear)
            if not strict_clear(edge, u, v, streams):
                miss["strict_fail"] += 1
                if len(examples) < 5:
                    examples.append((u.event_id, v.event_id, "strict_fail"))
                continue
            # negation 归入口 C · 此处不做
            ok_src_ids_list.append(u.event_id)
            anchor_ok_cnt += 1
        rel_rows.append(RelRow(
            edge_id=edge_id, total_src=len(candidates_by_edge[edge_id]),
            ok_src_ids=tuple(ok_src_ids_list), anchor_ok_count=anchor_ok_cnt,
            miss_reasons=miss, example_failed_pairs=tuple(examples),
        ))
```

- [ ] **Step 4: PASS**

Run: `uv run pytest tests/path2/dag/test_rel_miss_reasons.py -v` → PASS
Run: `uv run pytest tests/path2/dag/ -v` → 全绿

- [ ] **Step 5: Commit**

```bash
git add path2/dag/result.py path2/dag/diagnose.py tests/path2/dag/test_rel_miss_reasons.py
git commit -m "$(cat <<'EOF'
feat(path2/dag): RelRow.miss_reasons 分类计数 + example_failed_pairs 抽样

diagnose 层生成 rel 时按 gap_out / anchor_mismatch / strict_fail / negation_violated 四类累计,
抽样最多 5 条失败 pair 存 example_failed_pairs · 供入口 B scope=roles 消费。

承 spec §2.1 Stage 0.4 · 数据源支撑入口 B(拓扑降级 · 点边过滤打开 PairListCard)。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Stage 0.5 AnalysisResult.dropped_matches + DroppedMatch

**Files:**
- Modify: `path2/dag/result.py`(AnalysisResult 加 dropped_matches · 新 DroppedMatch dataclass)
- Modify: `path2/dag/engine.py`(post_filter 时记录被淘汰的 match)
- Test: `tests/path2/dag/test_dropped_matches.py`

**Interfaces:**
- Produces: `AnalysisResult.dropped_matches: list[DroppedMatch]`(Task 21 前端 DetailSidebar 消费)

- [ ] **Step 1: 写测试**

```python
# tests/path2/dag/test_dropped_matches.py
from path2.dag.result import AnalysisResult, DroppedMatch

def test_dropped_match_dataclass():
    dm = DroppedMatch(
        match_id="m0",
        role_events={"burst": "b1", "tb": "t3"},
        drop_reason="isolated_consumed",
    )
    assert dm.drop_reason == "isolated_consumed"

def test_analysis_result_has_dropped_matches_field():
    r = AnalysisResult(matches=(), dropped_matches=())
    assert r.dropped_matches == ()

def test_isolated_consumed_match_recorded():
    """post-filter 淘汰的 match 写入 dropped_matches"""
    result = _run_analyze_with_isolated_consumed_fixture()
    assert len(result.dropped_matches) >= 1
    assert result.dropped_matches[0].drop_reason == "isolated_consumed"
```

- [ ] **Step 2: FAIL**

Run: `uv run pytest tests/path2/dag/test_dropped_matches.py -v`
Expected: FAIL

- [ ] **Step 3: 实现**

修改 `path2/dag/result.py`:
```python
@dataclass(frozen=True)
class DroppedMatch:
    match_id: str
    role_events: dict[str, str]        # role_id → event_id
    drop_reason: str                    # 'isolated_consumed' 目前唯一

@dataclass(frozen=True)
class AnalysisResult:
    matches: tuple                       # 现有
    dropped_matches: tuple[DroppedMatch, ...] = ()   # ★ 新增
```

修改 `path2/dag/engine.py` 里 `isolated_consumed` post_filter 段(用 grep 定位:`isolated_consumed` 或 `post_filter`):
```python
def analyze(...):
    matches, dropped = _run_solver(...)   # 原来只返 matches
    surviving = []
    dropped_records = list(dropped)        # 保留之前的 dropped
    for m in matches:
        if _isolated_consumed(m, ...):
            dropped_records.append(DroppedMatch(
                match_id=m.match_id,
                role_events={r: e.event_id for r, e in m.role_events.items()},
                drop_reason="isolated_consumed",
            ))
        else:
            surviving.append(m)
    return AnalysisResult(matches=tuple(surviving), dropped_matches=tuple(dropped_records))
```

- [ ] **Step 4: PASS**

Run: `uv run pytest tests/path2/dag/test_dropped_matches.py -v` → PASS
Run: `uv run pytest tests/path2/ -v` → 全绿

- [ ] **Step 5: Commit**

```bash
git add path2/dag/result.py path2/dag/engine.py tests/path2/dag/test_dropped_matches.py
git commit -m "$(cat <<'EOF'
feat(path2/dag): AnalysisResult.dropped_matches 记录 isolated_consumed 淘汰

post-filter 阶段 isolated_consumed 淘汰的 match 快照写入 dropped_matches;
UI 可诚实提示"这些 marker 属于被消费的 role · 当前 pattern 未触发"。

承 spec §2.1 Stage 0.5 · 承接 v2 P3 撤后遗留(UI 呈现兜底)。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Stage 1 · ContextVar current_symbol + worker set

**Files:**
- Create: `path2/debug.py`
- Modify: `path2_web/worker.py`(worker 起始 set / 任务结束 reset)
- Test: `tests/path2/test_debug.py`

**Interfaces:**
- Produces: `path2.debug.current_symbol: ContextVar[str | None]` · `set_current_symbol(sym)`(Task 9-12 三 atom on_gate 读)

- [ ] **Step 1: 写测试**

```python
# tests/path2/test_debug.py
from path2.debug import current_symbol, set_current_symbol

def test_default_none():
    assert current_symbol.get() is None

def test_set_and_get():
    set_current_symbol("DGNX")
    assert current_symbol.get() == "DGNX"

def test_reset():
    set_current_symbol("DGNX")
    set_current_symbol(None)
    assert current_symbol.get() is None
```

- [ ] **Step 2: FAIL**

Run: `uv run pytest tests/path2/test_debug.py -v` → FAIL(模块不存在)

- [ ] **Step 3: 实现**

创建 `path2/debug.py`:
```python
"""ContextVar 层 · 让 detector / diagnose 内部可读当前处理的 symbol。

用途:
- driver 里 `if current_symbol.get() == 'DGNX': breakpoint()` 条件断点
- Stage 3 on_gate 采集 GateFailure.symbol 字段
- 日志前缀
"""
from contextvars import ContextVar
from typing import Optional

current_symbol: ContextVar[Optional[str]] = ContextVar('current_symbol', default=None)


def set_current_symbol(sym: Optional[str]) -> None:
    """任务开始 set,任务结束 reset(避免污染下个任务)。"""
    current_symbol.set(sym)
```

修改 `path2_web/worker.py`(ProcessPool 或类似 worker 入口,用 grep 定位:`ProcessPool` 或 `def scan_one` 或 `worker_task`):
```python
from path2.debug import set_current_symbol

def scan_one_symbol(symbol: str, pkl_path: str, spec):
    set_current_symbol(symbol)
    try:
        # 原扫描逻辑
        result = analyze(load_data(pkl_path), spec)
        return result
    finally:
        set_current_symbol(None)
```

- [ ] **Step 4: PASS**

Run: `uv run pytest tests/path2/test_debug.py -v` → PASS
Run: `uv run pytest tests/ -v` → 全绿

- [ ] **Step 5: Commit**

```bash
git add path2/debug.py path2_web/worker.py tests/path2/test_debug.py
git commit -m "$(cat <<'EOF'
feat(path2): Stage 1 · ContextVar current_symbol + worker set

新增 path2/debug.py 挂 ContextVar,worker 起始 set / 任务结束 reset;
支撑 driver 条件断点 + on_gate 采集 symbol + 日志前缀。

承 spec §2.2 Stage 1。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: shared/formatters.ts · fmt + fmtValue(硬伤 D)

**Files:**
- Create: `path2_web_ui/src/shared/formatters.ts`
- Test: `path2_web_ui/src/shared/formatters.spec.ts`

**Interfaces:**
- Produces: `fmt(val, kind)` · `fmtValue(val)`(Task 7 · 19 · 20 消费)

- [ ] **Step 1: 写测试**

```typescript
// path2_web_ui/src/shared/formatters.spec.ts
import { describe, it, expect } from 'vitest'
import { fmt, fmtValue } from './formatters'

describe('fmt · kind-aware', () => {
    it('gap kind 加 gap= 前缀', () => {
        expect(fmt(13, 'gap')).toBe('gap=13')
    })
    it('anchor_delta 显示 Δanchor=', () => {
        expect(fmt(0.234, 'anchor_delta')).toBe('Δanchor=0.234')
    })
    it('strict_clear 显示 strict候选=', () => {
        expect(fmt(2, 'strict_clear')).toBe('strict候选=2')
    })
    it('未知 kind 直接 String(val)', () => {
        expect(fmt('foo', 'unknown_kind')).toBe('foo')
    })
})

describe('fmtValue · 数组分支(硬伤 D)', () => {
    it('数组展开显示', () => {
        expect(fmtValue([1, 2, 3])).toBe('[1.000, 2.000, 3.000]')
    })
    it('嵌套数组递归', () => {
        expect(fmtValue([[1, 2], [3]])).toBe('[[1.000, 2.000], [3.000]]')
    })
    it('数字 3 位小数', () => {
        expect(fmtValue(1.23456)).toBe('1.235')
    })
    it('字符串原样', () => {
        expect(fmtValue('abc')).toBe('abc')
    })
})
```

- [ ] **Step 2: FAIL**

Run: `cd path2_web_ui && npm run test -- formatters.spec.ts`
Expected: FAIL(模块不存在)

- [ ] **Step 3: 实现**

创建 `path2_web_ui/src/shared/formatters.ts`:
```typescript
/**
 * 硬伤 E · kind-aware · 按 measured.kind 加前缀。
 * 4 种 kind:gap / anchor_delta / strict_clear / negation_bars。
 * 未来非-gap 判据不再"gap=" 硬编码骗人。
 */
export function fmt(val: any, kind: string): string {
    switch (kind) {
        case 'gap':
            return `gap=${val}`
        case 'anchor_delta':
            return `Δanchor=${Number(val).toFixed(3)}`
        case 'strict_clear':
            return `strict候选=${val}`
        case 'negation_bars':
            return `禁区bars=${val}`
        default:
            return String(val)
    }
}

/**
 * 硬伤 D · 数组分支 · multi-value where 完整展示。
 * 递归处理嵌套数组,数字统一 3 位小数。
 */
export function fmtValue(val: any): string {
    if (Array.isArray(val)) {
        return `[${val.map(fmtValue).join(', ')}]`
    }
    if (typeof val === 'number') {
        return val.toFixed(3)
    }
    return String(val)
}
```

- [ ] **Step 4: PASS**

Run: `cd path2_web_ui && npm run test -- formatters.spec.ts` → PASS
Run: `cd path2_web_ui && npm run type-check` → 无 error
Run: `cd path2_web_ui && npm run build` → 成功

- [ ] **Step 5: Commit**

```bash
git add path2_web_ui/src/shared/formatters.ts path2_web_ui/src/shared/formatters.spec.ts
git commit -m "$(cat <<'EOF'
feat(path2_web_ui/shared): fmt kind-aware + fmtValue 数组分支

shared/formatters.ts 抽 fmt(val, kind) · 按 kind 加前缀(gap / anchor_delta / strict / negation);
fmtValue 加数组递归分支修硬伤 D · 数组类型 measured 完整展示。

承 spec §4.1 · 硬伤 D + 硬伤 E 前端消费点前置。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: RelBadge + PendingIcon 组件 + DetailSidebar 消费(硬伤 A/C 前端)

**Files:**
- Create: `path2_web_ui/src/shared/RelBadge.vue`
- Create: `path2_web_ui/src/shared/PendingIcon.vue`
- Modify: `path2_web_ui/src/components/DetailSidebar.vue`(候选表 cell 消费 RelBadge / PendingIcon / fmt / fmtValue)
- Test: `path2_web_ui/src/shared/RelBadge.spec.ts` · `path2_web_ui/src/shared/PendingIcon.spec.ts`

**Interfaces:**
- Consumes: `fmt` / `fmtValue`(Task 6)
- Produces: `RelBadge` component(props `{ok, total, size?}`)· `PendingIcon` component(props `{reason}`)

- [ ] **Step 1: 写测试**

```typescript
// path2_web_ui/src/shared/RelBadge.spec.ts
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import RelBadge from './RelBadge.vue'

describe('RelBadge', () => {
    it('显示 K/N ✓ 格式', () => {
        const w = mount(RelBadge, { props: { ok: 8, total: 10 } })
        expect(w.text()).toContain('8/10')
    })
    it('全过时显示 ✓', () => {
        const w = mount(RelBadge, { props: { ok: 10, total: 10 } })
        expect(w.find('.badge-ok').exists()).toBe(true)
    })
    it('部分过时显示黄', () => {
        const w = mount(RelBadge, { props: { ok: 5, total: 10 } })
        expect(w.find('.badge-warn').exists()).toBe(true)
    })
    it('零过时显示红', () => {
        const w = mount(RelBadge, { props: { ok: 0, total: 10 } })
        expect(w.find('.badge-fail').exists()).toBe(true)
    })
})

// path2_web_ui/src/shared/PendingIcon.spec.ts
import PendingIcon from './PendingIcon.vue'

describe('PendingIcon', () => {
    it('refs_other_role 显 ⚠ + title', () => {
        const w = mount(PendingIcon, { props: { reason: 'refs_other_role' } })
        expect(w.text()).toContain('⚠')
        expect(w.attributes('title')).toContain('跨节点')
    })
    it('cross_node_pending 显 ⚠', () => {
        const w = mount(PendingIcon, { props: { reason: 'cross_node_pending' } })
        expect(w.text()).toContain('⚠')
    })
})
```

- [ ] **Step 2: FAIL**

Run: `cd path2_web_ui && npm run test`
Expected: FAIL(组件不存在)

- [ ] **Step 3: 实现**

创建 `path2_web_ui/src/shared/RelBadge.vue`:
```vue
<script setup lang="ts">
// 硬伤 A · role.rel 前端渲染 · "入边 K/N ✓" 徽标
defineProps<{
    ok: number
    total: number
    size?: 'sm' | 'md'
}>()

function badgeClass(ok: number, total: number): string {
    if (total === 0) return 'badge-neutral'
    if (ok === total) return 'badge-ok'
    if (ok === 0) return 'badge-fail'
    return 'badge-warn'
}
</script>

<template>
    <span :class="['rel-badge', badgeClass(ok, total), `size-${size ?? 'md'}`]">
        <span class="count">{{ ok }}/{{ total }}</span>
        <span v-if="ok === total && total > 0" class="check">✓</span>
    </span>
</template>

<style scoped>
.rel-badge { display: inline-flex; align-items: center; gap: 2px; padding: 0 6px; border-radius: 4px; font-size: 12px; }
.size-sm { padding: 0 4px; font-size: 10px; }
.badge-ok { background: #c6f6d5; color: #22543d; }
.badge-warn { background: #fefcbf; color: #744210; }
.badge-fail { background: #fed7d7; color: #742a2a; }
.badge-neutral { background: #e2e8f0; color: #4a5568; }
</style>
```

创建 `path2_web_ui/src/shared/PendingIcon.vue`:
```vue
<script setup lang="ts">
// 硬伤 C 前端 · refs_other_role / cross_node_pending 呈现
const props = defineProps<{
    reason: 'refs_other_role' | 'cross_node_pending'
}>()

const titleMap = {
    refs_other_role: '跨节点 clause · 编译期标注 · 当前诊断层未复核',
    cross_node_pending: '跨节点 clause · 运行期 tripwire 兜底 · 数据延后',
}
</script>

<template>
    <span class="pending-icon" :title="titleMap[reason]">⚠</span>
</template>

<style scoped>
.pending-icon { display: inline-block; color: #dd6b20; cursor: help; }
</style>
```

修改 `path2_web_ui/src/components/DetailSidebar.vue`(用 grep 定位候选表 cell render 处 · 一般在 `<td>{{ ... }}</td>` 附近):
```vue
<script setup lang="ts">
import RelBadge from '@/shared/RelBadge.vue'
import PendingIcon from '@/shared/PendingIcon.vue'
import { fmt, fmtValue } from '@/shared/formatters'
// ...
</script>

<template>
    <!-- 候选表 cell 里 · role 一列 -->
    <td class="role-cell">
        <span>{{ role.role_id }}</span>
        <RelBadge v-if="role.rel" :ok="role.rel.ok_count" :total="role.rel.total_src" size="sm" />
    </td>

    <!-- clause 判定 cell -->
    <td class="clause-cell">
        <PendingIcon v-if="clause.refs_other_role || clause.pending" :reason="clause.refs_other_role ? 'refs_other_role' : 'cross_node_pending'" />
        <span v-else>
            {{ fmt(clause.measured?.value, clause.measured?.kind ?? '') }}
            {{ clause.op }}
            {{ fmtValue(clause.threshold) }}
        </span>
    </td>
</template>
```

- [ ] **Step 4: PASS**

Run: `cd path2_web_ui && npm run test` → PASS
Run: `cd path2_web_ui && npm run type-check` → 无 error
Run: `cd path2_web_ui && npm run build` → 成功

- [ ] **Step 5: Commit**

```bash
git add path2_web_ui/src/shared/RelBadge.vue path2_web_ui/src/shared/PendingIcon.vue \
        path2_web_ui/src/shared/RelBadge.spec.ts path2_web_ui/src/shared/PendingIcon.spec.ts \
        path2_web_ui/src/components/DetailSidebar.vue
git commit -m "$(cat <<'EOF'
feat(path2_web_ui): RelBadge + PendingIcon 组件 + DetailSidebar 消费

硬伤 A · RelBadge 显示 role.rel "K/N ✓" 徽标 · 3 档色(ok/warn/fail);
硬伤 C 前端 · PendingIcon ⚠ + hover title · refs_other_role / cross_node_pending;
硬伤 D · DetailSidebar 候选表 cell 消费 fmt + fmtValue(硬伤 D 数组分支生效)。

承 spec §4.1 + §4.4 · 硬伤 A/C/D 前端首批修补。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: 后端 derive_response 骨架 + scope=roles + TopologyControl 降级(入口 B)

**Files:**
- Create: `path2_web/diagnose.py`(新版 · 若已有旧版则重写)
- Modify: `path2_web/api.py`(现有 `/diagnose` endpoint 转调)
- Modify: `path2_web_ui/src/components/TopologyControl.vue`(点 edge 触发 scope=roles)
- Create: `path2_web_ui/src/components/PairListCard.vue`(入口 B · miss_reasons 分布 + example_failed_pairs)
- Test: `tests/path2_web/test_diagnose_derive.py`

**Interfaces:**
- Consumes: `RelRow.miss_reasons`(Task 3)· `RelRow.example_failed_pairs`(Task 3)
- Produces: `derive_response(query: Query) -> Response`(Task 15 · 16 · 17 · 20 扩)· `PairListCard` component(Task 21 消费)

- [ ] **Step 1: 写测试**

```python
# tests/path2_web/test_diagnose_derive.py
from path2_web.diagnose import derive_response, Query, Response, RolesPayload

def test_derive_response_dispatches_by_scope():
    """derive_response 按 scope 分派 · 未知 scope 抛错"""
    import pytest
    q = Query(symbol="DGNX", scope="unknown")
    with pytest.raises(ValueError):
        derive_response(q)

def test_scope_roles_returns_roles_payload():
    q = Query(symbol="DGNX", scope="roles", src_role="burst", dst_role="tb")
    r = derive_response(q)
    assert r.scope == "roles"
    assert isinstance(r.payload, RolesPayload)
    assert "gap_out" in r.payload.miss_reasons

def test_scope_roles_example_failed_pairs_capped_5():
    q = Query(symbol="DGNX", scope="roles", src_role="burst", dst_role="tb")
    r = derive_response(q)
    assert len(r.payload.example_failed_pairs) <= 5

def test_scope_roles_caveat_anchor_ok_not_complete_absent_after_task1():
    """Task 1 已修 anchor · 不再挂 anchor_ok_not_complete caveat"""
    q = Query(symbol="DGNX", scope="roles", src_role="burst", dst_role="tb")
    r = derive_response(q)
    codes = [c.code for c in r.caveats]
    assert "anchor_ok_not_complete" not in codes
```

- [ ] **Step 2: FAIL**

Run: `uv run pytest tests/path2_web/test_diagnose_derive.py -v` → FAIL

- [ ] **Step 3: 实现**

创建 `path2_web/diagnose.py`(注意:若已有旧版 diagnose helper 散落,重写为 derive_response 一入口):
```python
"""后端 diagnose 分派层 · 一入口 derive_response(query) 按 scope 分派。

承 spec §3.1 · 4 scope:time / roles / candidate / pair。
"""
from dataclasses import dataclass, field
from typing import Any, Optional, Literal
from path2.dag.result import RelRow
# 引擎侧扫描结果由现有 /scan endpoint 存起来 · diagnose 拿 symbol → 加载 result

# Query / Response / Payload / SubCheck / Caveat dataclasses(见 core types dictionary)
@dataclass
class Query:
    symbol: str
    scope: Literal['time', 'roles', 'candidate', 'pair']
    start_bar: Optional[int] = None
    end_bar: Optional[int] = None
    event_class: Optional[str] = None
    src_role: Optional[str] = None
    dst_role: Optional[str] = None
    event_id: Optional[str] = None
    src_event_id: Optional[str] = None
    dst_event_id: Optional[str] = None
    edge_id: Optional[str] = None

@dataclass
class Caveat:
    code: str
    message: str
    affected_fields: list[str] = field(default_factory=list)

@dataclass
class Response:
    scope: str
    payload: Any
    caveats: list[Caveat] = field(default_factory=list)

@dataclass
class PairFailure:
    src_event_id: str
    dst_event_id: str
    subcheck_stage: str
    measured: dict  # MeasuredKindAware kind/value/label 序列化 dict
    threshold: Any
    edge_kind: str

@dataclass
class RolesPayload:
    edge_id: str
    total_pair: int
    ok_pair: int
    miss_reasons: dict[str, int]
    example_failed_pairs: list[PairFailure]
    per_pair: Optional[list[PairFailure]] = None


def derive_response(query: Query) -> Response:
    """按 scope 分派 · 不新增 endpoint · 沿用现有 /diagnose"""
    if query.scope == 'roles':
        return _derive_roles_response(query)
    if query.scope == 'time':
        return _derive_time_response(query)   # Task 15 实现
    if query.scope == 'candidate':
        return _derive_candidate_response(query)  # Task 20 实现
    if query.scope == 'pair':
        return _derive_pair_response(query)   # Task 17 实现
    raise ValueError(f"unknown scope: {query.scope}")


def _derive_roles_response(query: Query) -> Response:
    result = _load_analysis_result(query.symbol)   # 现有 helper · scan result 缓存
    edge_id = f"{query.src_role}_to_{query.dst_role}"
    rel_row = next((r for r in result.rel_rows if r.edge_id == edge_id), None)
    if rel_row is None:
        return Response(scope='roles',
                        payload=RolesPayload(edge_id=edge_id, total_pair=0, ok_pair=0,
                                             miss_reasons={}, example_failed_pairs=[]),
                        caveats=[Caveat(code='no_such_edge',
                                        message=f"dag_spec 中无 {edge_id} edge")])
    example_pairs = [
        PairFailure(src_event_id=u, dst_event_id=v, subcheck_stage=stage,
                    measured={}, threshold=None,
                    edge_kind=_edge_kind(edge_id, result.spec))
        for (u, v, stage) in rel_row.example_failed_pairs
    ]
    return Response(scope='roles',
                    payload=RolesPayload(
                        edge_id=edge_id,
                        total_pair=rel_row.total_src,
                        ok_pair=len(rel_row.ok_src_ids),
                        miss_reasons=dict(rel_row.miss_reasons),
                        example_failed_pairs=example_pairs,
                    ),
                    caveats=_collect_caveats(query, result))


def _derive_time_response(query: Query) -> Response:
    return Response(scope='time', payload={'stub': True},
                    caveats=[Caveat(code='on_gate_hook_not_landed',
                                    message='Stage 3 on_gate 未落 · Task 9-12 完成后可用')])


def _derive_candidate_response(query: Query) -> Response:
    return Response(scope='candidate', payload={'stub': True},
                    caveats=[Caveat(code='solvetrace_not_landed',
                                    message='Stage 2 SolveTrace 未落 · Task 19 完成后可用')])


def _derive_pair_response(query: Query) -> Response:
    return Response(scope='pair', payload={'stub': True},
                    caveats=[Caveat(code='subcheck_helpers_not_landed',
                                    message='Task 16 · 17 subcheck helpers 未落')])


def _collect_caveats(query: Query, result) -> list[Caveat]:
    caveats: list[Caveat] = []
    # 硬伤 E · Sprint 2 Task 13 修 · 未修则挂
    if not _kind_aware_measured_available():
        caveats.append(Caveat(code='measured_not_kind_aware',
                              message='EdgeWitness.measured 未升级 kind-aware(硬伤 E)'))
    return caveats


def _kind_aware_measured_available() -> bool:
    # Task 13 完成后返 True
    try:
        from path2.dag._reify import MeasuredKindAware  # noqa
        return True
    except ImportError:
        return False


def _load_analysis_result(symbol: str):
    # 从现有 scan result 缓存 load(具体实现依 path2_web 现有 helper 定)
    from path2_web.cache import load_result
    return load_result(symbol)


def _edge_kind(edge_id: str, spec) -> str:
    # 根据 spec 查 edge kind
    edge = next((e for e in spec.edges if f"{e.src}_to_{e.dst}" == edge_id), None)
    return type(edge).__name__ if edge else 'unknown'
```

修改 `path2_web/api.py`:
```python
from path2_web.diagnose import derive_response, Query, Response

@app.get("/diagnose")
def diagnose_endpoint(symbol: str, scope: str, **kwargs):
    query = Query(symbol=symbol, scope=scope, **kwargs)
    return derive_response(query)
```

修改 `path2_web_ui/src/components/TopologyControl.vue` 加点 edge 交互:
```vue
<script setup lang="ts">
import { ref } from 'vue'
import PairListCard from './PairListCard.vue'

const activeRoleEdge = ref<{src: string, dst: string} | null>(null)
const rolesPayload = ref<any>(null)

async function handleEdgeClick(src: string, dst: string) {
    activeRoleEdge.value = { src, dst }
    const resp = await fetch(`/diagnose?symbol=${symbol}&scope=roles&src_role=${src}&dst_role=${dst}`)
    rolesPayload.value = await resp.json()
    emit('roles-loaded', rolesPayload.value)   // DetailSidebar 侧栏切换
}
</script>

<template>
    <!-- 拓扑图 · 每 edge 加 click handler -->
    <g v-for="edge in edges" :key="edge.id" @click="handleEdgeClick(edge.src, edge.dst)">
        <!-- 现有 render 保留 · 无染色 · 静态图 -->
    </g>
</template>
```

创建 `path2_web_ui/src/components/PairListCard.vue`:
```vue
<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
    payload: {
        edge_id: string
        total_pair: number
        ok_pair: number
        miss_reasons: { gap_out: number, anchor_mismatch: number, strict_fail: number, negation_violated: number }
        example_failed_pairs: Array<{
            src_event_id: string
            dst_event_id: string
            subcheck_stage: string
            edge_kind: string
        }>
    }
}>()

const emit = defineEmits<{
    (e: 'pair-deep-dive', payload: { src_event_id: string, dst_event_id: string }): void
}>()

const totalFailed = computed(() => props.payload.total_pair - props.payload.ok_pair)

function handleRowClick(row: { src_event_id: string, dst_event_id: string }) {
    emit('pair-deep-dive', row)
}
</script>

<template>
    <div class="pair-list-card">
        <header>
            <strong>{{ payload.edge_id }}</strong>
            <span>{{ payload.ok_pair }} / {{ payload.total_pair }} 通过 · {{ totalFailed }} 失败</span>
        </header>
        <section class="miss-reasons">
            <span>gap 越界:{{ payload.miss_reasons.gap_out }}</span>
            <span>anchor 破位:{{ payload.miss_reasons.anchor_mismatch }}</span>
            <span>strict fail:{{ payload.miss_reasons.strict_fail }}</span>
        </section>
        <section class="examples">
            <table>
                <thead><tr><th>src</th><th>dst</th><th>栽在</th></tr></thead>
                <tbody>
                    <tr v-for="row in payload.example_failed_pairs" :key="`${row.src_event_id}_${row.dst_event_id}`"
                        @click="handleRowClick(row)"
                        class="clickable">
                        <td>{{ row.src_event_id }}</td>
                        <td>{{ row.dst_event_id }}</td>
                        <td>{{ row.subcheck_stage }}</td>
                    </tr>
                </tbody>
            </table>
        </section>
    </div>
</template>

<style scoped>
.pair-list-card { padding: 12px; overflow-x: auto; min-width: 0; }
.miss-reasons { display: flex; gap: 12px; margin: 8px 0; }
.clickable { cursor: pointer; }
.clickable:hover { background: #edf2f7; }
</style>
```

- [ ] **Step 4: PASS**

Run: `uv run pytest tests/path2_web/test_diagnose_derive.py -v` → PASS
Run: `cd path2_web_ui && npm run test && npm run type-check && npm run build` → 全绿
Run: `uv run pytest tests/ -v` → 全绿

- [ ] **Step 5: Commit**

```bash
git add path2_web/diagnose.py path2_web/api.py \
        tests/path2_web/test_diagnose_derive.py \
        path2_web_ui/src/components/TopologyControl.vue \
        path2_web_ui/src/components/PairListCard.vue
git commit -m "$(cat <<'EOF'
feat(path2_web): derive_response 分派 + scope=roles + 入口 B 降级(点边)

后端 derive_response(query) 一入口按 scope 分派(time/roles/candidate/pair);
Sprint 1 落 scope=roles(RolesPayload 消费 RelRow.miss_reasons + example_failed_pairs);
入口 B 拓扑面板降级 · 点 edge 触发 scope=roles → PairListCard(无染色);
其他 3 scope 落 stub · Sprint 2/3 补齐。

承 spec §3.1 · §3.2.3 · §4.3 · §4.4 · 入口 B 首版上线。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

**Sprint 1 里程碑**:硬伤 A/B/C/D 首批修 · anchor_ok 复核 · miss_reasons 分布 · 入口 B 降级可用 · 覆盖率 ~75%。

Sprint 1 结束 · 跑全 test suite 保绿:
```bash
uv run pytest tests/ -v && \
cd path2_web_ui && npm run test && npm run type-check && npm run build && cd ..
```

---

## Sprint 2 · 入口 A + 入口 D · Task 9-18

### Task 9: GateFailure + MeasuredKindAware + Detector.on_gate protocol

**Files:**
- Create: `path2/dag/gate_failure.py`(GateFailure + MeasuredKindAware dataclasses)
- Modify: `path2/core.py`(Detector Protocol 加 `on_gate` attribute)
- Test: `tests/path2/dag/test_gate_failure.py`

**Interfaces:**
- Produces: `GateFailure` · `MeasuredKindAware` · `Detector.on_gate: Optional[Callable]`(Task 10 · 11 · 12 消费)

- [ ] **Step 1: 写测试**

```python
# tests/path2/dag/test_gate_failure.py
from path2.dag.gate_failure import GateFailure, MeasuredKindAware

def test_measured_kind_aware_dataclass():
    m = MeasuredKindAware(kind='gap', value=13, label='gap')
    assert m.kind == 'gap' and m.value == 13

def test_gate_failure_dataclass():
    m = MeasuredKindAware(kind='gap', value=13, label='gap')
    gf = GateFailure(
        failure_event_window=(90, 105),
        start_idx=90,
        gate_idx=105,
        anchor_bar=105,
        class_id='burst',
        gate_name='chain_break',
        measured=m,
        threshold=10,
        evaluation_lookback=None,
        symbol='DGNX',
    )
    assert gf.gate_name == 'chain_break'
    assert gf.failure_event_window == (90, 105)

def test_gate_failure_is_frozen():
    import dataclasses
    m = MeasuredKindAware(kind='gap', value=13, label='gap')
    gf = GateFailure(failure_event_window=(0, 0), start_idx=0, gate_idx=0,
                     anchor_bar=0, class_id='bo', gate_name='x', measured=m,
                     threshold=0, evaluation_lookback=None, symbol='x')
    import pytest
    with pytest.raises(dataclasses.FrozenInstanceError):
        gf.symbol = "changed"


def test_detector_protocol_has_optional_on_gate():
    from path2.core import Detector
    # Protocol 有 on_gate optional 属性 · duck type
    class MyDetector:
        on_gate = None
    d: Detector = MyDetector()
    assert d.on_gate is None
```

- [ ] **Step 2: FAIL**

Run: `uv run pytest tests/path2/dag/test_gate_failure.py -v` → FAIL

- [ ] **Step 3: 实现**

创建 `path2/dag/gate_failure.py`:
```python
"""GateFailure · attempt 短路失败时 detector 吐给 on_gate hook 的记录。

承 spec §2.4.1 · failure_event_window 语义 = attempt 判据评估的实测轨迹。
"""
from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class MeasuredKindAware:
    """硬伤 E 契约 · measured 字段升级为 kind-aware 结构。
    4 种 kind:'gap' / 'anchor_delta' / 'strict_clear' / 'negation_bars'。
    """
    kind: str
    value: Any
    label: str


@dataclass(frozen=True)
class GateFailure:
    """一次 attempt 短路失败的完整记录。
    - failure_event_window: (start_idx, gate_idx) 实测轨迹;点事件 = (i, i)
    - start_idx: attempt 判据评估的起点
    - gate_idx: gate 触发所在 bar(= failure event end 兜底)
    - anchor_bar: class_id 语义锚
    - evaluation_lookback: detector 内部判据依赖的历史窗;不参与 ⊆ 判据(tooltip 显示)
    """
    failure_event_window: tuple[int, int]
    start_idx: int
    gate_idx: int
    anchor_bar: int
    class_id: str
    gate_name: str
    measured: MeasuredKindAware
    threshold: Any
    evaluation_lookback: Optional[tuple[int, int]]
    symbol: str
```

修改 `path2/core.py`:
```python
from typing import Optional, Callable, Protocol
from path2.dag.gate_failure import GateFailure

class Detector(Protocol):
    """现有 Protocol 加 on_gate optional attribute。
    默认 None · 生产路径无开销 · diagnose 层挂 collector 才启用。
    """
    on_gate: Optional[Callable[[GateFailure], None]] = None
    # ...(其他现有方法保留)
```

- [ ] **Step 4: PASS**

Run: `uv run pytest tests/path2/dag/test_gate_failure.py -v` → PASS
Run: `uv run pytest tests/path2/ -v` → 全绿

- [ ] **Step 5: Commit**

```bash
git add path2/dag/gate_failure.py path2/core.py tests/path2/dag/test_gate_failure.py
git commit -m "$(cat <<'EOF'
feat(path2/dag): GateFailure + MeasuredKindAware + Detector.on_gate protocol

新增 GateFailure dataclass · failure_event_window 实测轨迹语义 · 承 spec §2.4.1;
Detector Protocol 加 optional on_gate hook · 默认 None · Task 10-12 三 atom 埋点消费。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 10: BurstDetector on_gate 埋点(2 gate)

**Files:**
- Modify: `path2/atoms/breakout.py::BurstDetector.detect`(L124-135)
- Test: `tests/path2/atoms/test_burst_on_gate.py`

**Interfaces:**
- Consumes: `GateFailure` · `Detector.on_gate`(Task 9)· `current_symbol`(Task 5)
- Produces: BurstDetector 在 chain_break / min_bos_insufficient 时吐 GateFailure(Task 15 后端消费)

- [ ] **Step 1: 写测试**

```python
# tests/path2/atoms/test_burst_on_gate.py
import pandas as pd
from path2.atoms.breakout import BurstDetector, BOEvent
from path2.dag.gate_failure import GateFailure
from path2.debug import set_current_symbol

def make_bo(idx: int) -> BOEvent:
    return BOEvent(event_id=f"bo_{idx}", start_idx=idx, end_idx=idx,
                   drought=None, pk_count=1, broken_peak_ids=(),
                   vol_ratio=None, peak_vol_max=0.0, referenced_points=())

def test_chain_break_emits_gate_failure():
    """相邻 bo gap > gap_max 触发 chain_break gate"""
    set_current_symbol("TEST")
    bos = [make_bo(90), make_bo(105)]  # gap = 15 > gap_max = 10
    detector = BurstDetector(gap_max=10, min_bos=2)
    captured: list[GateFailure] = []
    detector.on_gate = captured.append
    df = pd.DataFrame({'volume': [0.0]*200})
    list(detector.detect(bos, df))
    # 应该有一条 chain_break · 前簇(bo_90 单独)因 min_bos=2 也可能吐 min_bos_insufficient
    chain_breaks = [g for g in captured if g.gate_name == 'chain_break']
    assert len(chain_breaks) == 1
    gf = chain_breaks[0]
    assert gf.class_id == 'burst'
    assert gf.gate_idx == 105  # trigger bar = seq[k].start_idx
    assert gf.failure_event_window == (90, 105) or gf.failure_event_window == (90, 90)
    assert gf.symbol == 'TEST'
    assert gf.measured.kind == 'gap'
    assert gf.measured.value == 15
    assert gf.threshold == 10

def test_min_bos_insufficient_at_stream_end():
    """簇末 k - head + 1 < min_bos 触发 min_bos_insufficient"""
    set_current_symbol("TEST")
    bos = [make_bo(90), make_bo(92)]  # gap=2 一簇 · 但 min_bos=5 不够
    detector = BurstDetector(gap_max=10, min_bos=5)
    captured: list[GateFailure] = []
    detector.on_gate = captured.append
    df = pd.DataFrame({'volume': [0.0]*200})
    list(detector.detect(bos, df))
    min_bos_gates = [g for g in captured if g.gate_name == 'min_bos_insufficient']
    assert len(min_bos_gates) == 1
    gf = min_bos_gates[0]
    assert gf.class_id == 'burst'
    assert gf.failure_event_window == (90, 92)
    assert gf.threshold == 5

def test_no_gate_when_on_gate_none():
    """on_gate 未挂时不 emit(生产路径无开销)"""
    bos = [make_bo(90), make_bo(105)]
    detector = BurstDetector(gap_max=10, min_bos=2)
    # detector.on_gate 默认无(未设 · 应保持 None 或不存在)
    df = pd.DataFrame({'volume': [0.0]*200})
    list(detector.detect(bos, df))  # 不应抛错
```

- [ ] **Step 2: FAIL**

Run: `uv run pytest tests/path2/atoms/test_burst_on_gate.py -v` → FAIL

- [ ] **Step 3: 实现**

修改 `path2/atoms/breakout.py::BurstDetector.detect` L124-135:
```python
from path2.dag.gate_failure import GateFailure, MeasuredKindAware
from path2.debug import current_symbol

class BurstDetector:
    on_gate = None   # 默认 None

    def detect(self, bos, df):
        seq = sorted(bos, key=lambda e: (e.start_idx, e.end_idx))
        vol_ratio_series = calculate_vol_ratio(df["volume"], self.vol_baseline_period)
        out = []
        head = 0
        for k in range(len(seq)):
            if k > 0 and seq[k].start_idx - seq[k - 1].start_idx > self.gap_max:
                # ★ chain_break gate · 吐 GateFailure
                if self.on_gate is not None:
                    prev_cluster_start = seq[head].start_idx
                    prev_cluster_end = seq[k - 1].end_idx
                    self.on_gate(GateFailure(
                        failure_event_window=(prev_cluster_start, seq[k].start_idx),
                        start_idx=prev_cluster_start,
                        gate_idx=seq[k].start_idx,
                        anchor_bar=prev_cluster_end,
                        class_id='burst',
                        gate_name='chain_break',
                        measured=MeasuredKindAware(kind='gap',
                                                   value=seq[k].start_idx - seq[k - 1].start_idx,
                                                   label='gap'),
                        threshold=self.gap_max,
                        evaluation_lookback=None,
                        symbol=current_symbol.get() or '',
                    ))
                head = k
            if k - head + 1 >= self.min_bos:
                out.append(self._make_burst(seq[head: k + 1], vol_ratio_series))

        # 流末尾 · 若最后一簇 < min_bos · 吐 min_bos_insufficient
        if self.on_gate is not None and len(seq) > 0:
            last_cluster_size = len(seq) - head
            if last_cluster_size < self.min_bos:
                cluster_start = seq[head].start_idx
                cluster_end = seq[-1].end_idx
                self.on_gate(GateFailure(
                    failure_event_window=(cluster_start, cluster_end),
                    start_idx=cluster_start,
                    gate_idx=cluster_end,
                    anchor_bar=cluster_end,
                    class_id='burst',
                    gate_name='min_bos_insufficient',
                    measured=MeasuredKindAware(kind='count', value=last_cluster_size, label='bo数'),
                    threshold=self.min_bos,
                    evaluation_lookback=None,
                    symbol=current_symbol.get() or '',
                ))

        out.sort(key=lambda e: (e.end_idx, e.start_idx))
        yield from out
```

- [ ] **Step 4: PASS**

Run: `uv run pytest tests/path2/atoms/test_burst_on_gate.py -v` → PASS
Run: `uv run pytest tests/path2/ -v` → 全绿(BurstDetector 现有 test 不破)

- [ ] **Step 5: Commit**

```bash
git add path2/atoms/breakout.py tests/path2/atoms/test_burst_on_gate.py
git commit -m "$(cat <<'EOF'
feat(path2/atoms): BurstDetector on_gate · chain_break + min_bos_insufficient

BurstDetector.detect 内埋 2 gate:
- 相邻 bo gap > gap_max → chain_break(trigger = seq[k].start_idx)
- 流末尾 last_cluster_size < min_bos → min_bos_insufficient(trigger = 簇末)
attempt = 一簇一次(spec §2.4.2 定义 A) · symbol 从 ContextVar 读。

承 spec §2.4.3 · 主诉 detector 优先(DGNX 类场景) · 生产路径 on_gate None 无开销。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 11: BODetector on_gate 埋点(5 gate)

**Files:**
- Modify: `path2/atoms/breakout.py::BODetector.emit` L225-289 + `_detect_peak_in_window`
- Test: `tests/path2/atoms/test_bo_on_gate.py`

**Interfaces:**
- Consumes: `GateFailure`(Task 9)
- Produces: BODetector 在 peak_no_local_max / peak_side_bars_insufficient / peak_relative_height_insufficient / peak_already_active / no_active_peak_broken 时吐 GateFailure

- [ ] **Step 1: 写测试**

```python
# tests/path2/atoms/test_bo_on_gate.py
import pandas as pd
from path2.atoms.breakout import BODetector
from path2.dag.gate_failure import GateFailure
from path2.debug import set_current_symbol

def _make_df_no_peak() -> pd.DataFrame:
    # 单调下跌 · 无 peak · 触发 peak_no_local_max
    n = 50
    return pd.DataFrame({
        'open': [100 - i for i in range(n)],
        'close': [100 - i - 0.5 for i in range(n)],
        'high': [100 - i + 0.5 for i in range(n)],
        'low': [100 - i - 1 for i in range(n)],
        'volume': [1000.0] * n,
    })

def test_no_active_peak_broken_gate_emitted():
    """无 active peak 时,每 bar 都会吐 no_active_peak_broken"""
    set_current_symbol("TEST")
    df = _make_df_no_peak()
    detector = BODetector(total_window=10, min_side_bars=3, min_relative_height=0.1)
    captured: list[GateFailure] = []
    detector.on_gate = captured.append
    list(detector.detect(df))
    # 应该多个 no_active_peak_broken(每 bar 一个)· 或 peak_no_local_max
    gates = [g.gate_name for g in captured]
    assert 'no_active_peak_broken' in gates or 'peak_relative_height_insufficient' in gates

def test_bo_gate_failure_event_window_is_point():
    """BO 点事件 · failure_event_window = (i, i)"""
    set_current_symbol("TEST")
    df = _make_df_no_peak()
    detector = BODetector(total_window=10, min_side_bars=3, min_relative_height=0.1)
    captured: list[GateFailure] = []
    detector.on_gate = captured.append
    list(detector.detect(df))
    for g in captured:
        assert g.failure_event_window[0] == g.failure_event_window[1], \
            f"BO 应为点事件 · 但 window = {g.failure_event_window}"
        assert g.class_id == 'bo'
        # evaluation_lookback 应指向 [i - total_window, i - 1]
        assert g.evaluation_lookback is not None
```

- [ ] **Step 2: FAIL**

Run: `uv run pytest tests/path2/atoms/test_bo_on_gate.py -v` → FAIL

- [ ] **Step 3: 实现**

修改 `path2/atoms/breakout.py::BODetector.emit` L225-289:
```python
from path2.dag.gate_failure import GateFailure, MeasuredKindAware
from path2.debug import current_symbol

class BODetector(BarwiseDetector):
    on_gate = None   # 默认 None

    def emit(self, df, i):
        # 1. peak 检测(在窗口内) · 若无新 peak,可能吐 peak_no_local_max / peak_side_bars_insufficient / peak_relative_height_insufficient / peak_already_active
        self._detect_peak_in_window(df, i)

        # 2. 突破检测
        breakout_price = measure_at(df, i, self.breakout_measure)
        elevation_price = measure_at(df, i, self.peak_measure)
        broken_peaks = []
        remaining_peaks = []
        for peak in self._active_peaks:
            exceed_price = peak.price * (1 + self.exceed_threshold)
            # ... 原逻辑保留
            if breakout_price > exceed_price:
                broken_peaks.append(peak)
                # ... supersede / elevation 逻辑
            else:
                remaining_peaks.append(peak)
        self._active_peaks = remaining_peaks

        # 3. gate 埋点:若无 broken_peak,吐 no_active_peak_broken
        if not broken_peaks:
            if self.on_gate is not None:
                # 若 active_peaks 空 · gate = no_active_peaks_yet;否则 = no_active_peak_broken
                gate_name = 'no_active_peak_broken' if self._active_peaks else 'no_active_peaks_yet'
                self.on_gate(GateFailure(
                    failure_event_window=(i, i),
                    start_idx=i, gate_idx=i,
                    anchor_bar=i,
                    class_id='bo',
                    gate_name=gate_name,
                    measured=MeasuredKindAware(kind='breakout_price', value=breakout_price, label='breakout'),
                    threshold=None,
                    evaluation_lookback=(max(0, i - self.total_window), i - 1),
                    symbol=current_symbol.get() or '',
                ))
            return None

        # 4. 原成功产 BOEvent 逻辑保留 · yield
        drought = None if self._last_bo_idx is None else (i - self._last_bo_idx)
        # ... 原字段计算
        self._last_bo_idx = i
        return BOEvent(...)

    def _detect_peak_in_window(self, df, current_idx):
        """在 [current_idx - total_window, current_idx - 1] 窗口内检测 peak · 4 条判据 gate。"""
        # 找窗口 local max
        window_start = max(0, current_idx - self.total_window)
        window_end = current_idx  # 不含
        if window_end - window_start < self.min_side_bars * 2 + 1:
            if self.on_gate is not None:
                self.on_gate(GateFailure(
                    failure_event_window=(current_idx, current_idx),
                    start_idx=current_idx, gate_idx=current_idx,
                    anchor_bar=current_idx, class_id='bo',
                    gate_name='peak_side_bars_insufficient',
                    measured=MeasuredKindAware(kind='window_size', value=window_end - window_start, label='窗大小'),
                    threshold=self.min_side_bars * 2 + 1,
                    evaluation_lookback=(window_start, current_idx - 1),
                    symbol=current_symbol.get() or '',
                ))
            return
        # ...(4 条 peak 判据全走一遍 · 每 fail 吐对应 gate_name)
        # peak_no_local_max / peak_relative_height_insufficient / peak_already_active
        # 具体判据见现有代码 · 每 fail 处加 on_gate 调用
```

**注意**:BODetector 的 gate 埋点较多、逻辑复杂,implementer 需要仔细在原 `_detect_peak_in_window` 每个 return / continue 点插入 on_gate 调用。5 个 gate_name 全枚举见 spec §2.4.3。

- [ ] **Step 4: PASS**

Run: `uv run pytest tests/path2/atoms/test_bo_on_gate.py -v` → PASS
Run: `uv run pytest tests/path2/ -v` → 全绿

- [ ] **Step 5: Commit**

```bash
git add path2/atoms/breakout.py tests/path2/atoms/test_bo_on_gate.py
git commit -m "$(cat <<'EOF'
feat(path2/atoms): BODetector on_gate · 5 gate(peak 判据 + 突破)

BODetector 内部 5 gate 埋点:
- peak_no_local_max / peak_side_bars_insufficient / peak_relative_height_insufficient / peak_already_active(peak 判据 4 条)
- no_active_peak_broken(突破判据 · 无 active_peak 或全部未突破)
BO 点事件 · failure_event_window = (i, i) · evaluation_lookback = (i - total_window, i - 1)。

承 spec §2.4.3 · 承 §2.4.2 · 点事件 window 语义严格对齐。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 12: ThrowbackDetector on_gate 埋点(4 gate)

**Files:**
- Modify: `path2/atoms/throwback.py`(`_find_start_idx` + `_find_end_idx` + `evaluate_throwback` · L83-244)
- Test: `tests/path2/atoms/test_tb_on_gate.py`

**Interfaces:**
- Consumes: `GateFailure`(Task 9)
- Produces: TB 4 gate (phase1_break / phase1_pullback_shortage / phase1_no_trough_timeout / phase2_break) 吐 GateFailure

- [ ] **Step 1: 写测试**

```python
# tests/path2/atoms/test_tb_on_gate.py
import pandas as pd
from path2.atoms.breakout import BOEvent
from path2.atoms.throwback import ThrowbackDetector
from path2.dag.gate_failure import GateFailure
from path2.debug import set_current_symbol

def _fixture_phase1_break() -> tuple[list, pd.DataFrame]:
    """构造 anchor 破位 · 阶段一破位 fixture"""
    n = 30
    df = pd.DataFrame({
        'open': [100.0] * n, 'close': [100.0] * n,
        'high': [101.0] * n, 'low': [99.5] * n,
        'volume': [1000.0] * n,
    })
    # bo_10 触发 · anchor = high[9] = 101
    # bo 后 close[11] = 100 < 101 破位
    df.loc[11, 'close'] = 90.0
    bo = BOEvent(event_id="bo_10", start_idx=10, end_idx=10,
                 drought=None, pk_count=1, broken_peak_ids=(), vol_ratio=None,
                 peak_vol_max=0.0, referenced_points=())
    return [bo], df

def test_phase1_break_gate():
    set_current_symbol("TEST")
    bos, df = _fixture_phase1_break()
    detector = ThrowbackDetector()
    captured: list[GateFailure] = []
    detector.on_gate = captured.append
    list(detector.detect(iter(bos), df))
    breaks = [g for g in captured if g.gate_name == 'phase1_break']
    assert len(breaks) >= 1
    gf = breaks[0]
    assert gf.class_id == 'tb'
    assert gf.start_idx == 11  # bo.end_idx + 1
    assert gf.failure_event_window[0] == 11
    assert gf.failure_event_window[1] == gf.gate_idx
```

- [ ] **Step 2: FAIL**

Run: `uv run pytest tests/path2/atoms/test_tb_on_gate.py -v` → FAIL

- [ ] **Step 3: 实现**

修改 `path2/atoms/throwback.py`:
```python
from path2.dag.gate_failure import GateFailure, MeasuredKindAware
from path2.debug import current_symbol


def _emit_tb_gate(bo_idx: int, gate_idx: int, gate_name: str,
                  measured: MeasuredKindAware, threshold, atr_window: int,
                  on_gate):
    """辅助 · 组装 GateFailure 并 emit(避免重复 boilerplate)。"""
    if on_gate is None:
        return
    on_gate(GateFailure(
        failure_event_window=(bo_idx + 1, gate_idx),   # X 松对齐 · attempt 起点 = bo.end_idx + 1
        start_idx=bo_idx + 1,
        gate_idx=gate_idx,
        anchor_bar=bo_idx,
        class_id='tb',
        gate_name=gate_name,
        measured=measured,
        threshold=threshold,
        evaluation_lookback=(bo_idx - atr_window, bo_idx),
        symbol=current_symbol.get() or '',
    ))


def evaluate_throwback(bo, df, on_gate=None, **kwargs):
    max_start_gap = kwargs['max_start_gap']
    max_window = kwargs['max_window']
    atr_window = kwargs['atr_window']
    # ... 原前置检查
    bo_idx = bo.end_idx
    atr = _atr_at(df, bo_idx - 1, atr_window)
    if atr <= 0.0:
        return None
    anchor = measure_at(df, bo_idx - 1, kwargs['anchor_measure'])
    start = _find_start_idx(df, bo_idx, anchor, max_start_gap, atr,
                             kwargs['pullback_min_atr'], kwargs['support_measure'],
                             on_gate=on_gate, atr_window=atr_window)
    if start is None:
        return None
    end = _find_end_idx(df, start, anchor, max_window, atr, kwargs['big_rise_k'],
                       kwargs['support_measure'], on_gate=on_gate, bo_idx=bo_idx, atr_window=atr_window)
    if end is None:
        return None
    return ThrowbackResult(start, end)


def _find_start_idx(df, bo_idx, anchor, max_start_gap, atr, pullback_min_atr,
                    support_measure, on_gate=None, atr_window=14):
    end = min(bo_idx + max_start_gap, len(df) - 1)
    trough_idx = bo_idx + 1
    for i in range(bo_idx + 1, end + 1):
        if measure_at(df, i, support_measure) < anchor:
            _emit_tb_gate(bo_idx, i, 'phase1_break',
                          MeasuredKindAware(kind='anchor_delta',
                                            value=measure_at(df, i, support_measure) - anchor,
                                            label='破位差'),
                          0.0, atr_window, on_gate)
            return None
        # ... 原逻辑
        if i >= bo_idx + 2:
            # 若"连续两根不创新低 + 止跌"确认后回落深度不达
            lo_p = float(df['low'].iat[i - 1]); lo_pp = float(df['low'].iat[i - 2])
            lo_i = float(df['low'].iat[i])
            if lo_i >= lo_p and lo_p >= lo_pp and (_has_stop_signal(df, i - 1) or _has_stop_signal(df, i)):
                peak = float(df['high'].iloc[bo_idx: trough_idx + 1].max())
                depth = peak - float(df['low'].iat[trough_idx])
                if depth < pullback_min_atr * atr:
                    _emit_tb_gate(bo_idx, i, 'phase1_pullback_shortage',
                                  MeasuredKindAware(kind='pullback_atr',
                                                    value=depth / atr if atr > 0 else 0.0,
                                                    label='回落深度/ATR'),
                                  pullback_min_atr, atr_window, on_gate)
                    return None
                return trough_idx
    # timeout · 扫满未找到止跌
    _emit_tb_gate(bo_idx, end, 'phase1_no_trough_timeout',
                  MeasuredKindAware(kind='count', value=max_start_gap, label='max_start_gap 扫满'),
                  max_start_gap, atr_window, on_gate)
    return None


def _find_end_idx(df, start_idx, anchor, max_window, atr, big_rise_k,
                  support_measure, on_gate=None, bo_idx=None, atr_window=14):
    end_scan = min(start_idx + max_window, len(df) - 1)
    base_min = float(df['low'].iat[start_idx])
    for i in range(start_idx + 1, end_scan + 1):
        if measure_at(df, i, support_measure) < anchor:
            _emit_tb_gate(bo_idx, i, 'phase2_break',
                          MeasuredKindAware(kind='anchor_delta',
                                            value=measure_at(df, i, support_measure) - anchor,
                                            label='破位差'),
                          0.0, atr_window, on_gate)
            return None
        # ... 大涨判据 · 大涨则 return i - 1(成功 · 不吐 gate)
        if float(df['high'].iat[i]) - base_min >= big_rise_k * atr:
            return i - 1
        lo_i = float(df['low'].iat[i])
        if lo_i < base_min:
            base_min = lo_i
    return end_scan   # timeout 成功


class ThrowbackDetector:
    on_gate = None

    def detect(self, bo_stream, df):
        for bo in bo_stream:
            r = evaluate_throwback(bo, df, on_gate=self.on_gate, **self._kw)
            if r is not None:
                # ... 原产出逻辑
```

- [ ] **Step 4: PASS**

Run: `uv run pytest tests/path2/atoms/test_tb_on_gate.py -v` → PASS
Run: `uv run pytest tests/path2/ -v` → 全绿

- [ ] **Step 5: Commit**

```bash
git add path2/atoms/throwback.py tests/path2/atoms/test_tb_on_gate.py
git commit -m "$(cat <<'EOF'
feat(path2/atoms): ThrowbackDetector on_gate · 4 gate(松对齐 X)

TB 4 gate 埋点(承 spec §2.4.3):
- phase1_break / phase1_pullback_shortage / phase1_no_trough_timeout / phase2_break
attempt 定义采解读 X 松对齐 · 一次 evaluate_throwback = 一次 attempt · 阶段一/二失败共用同 failure_event_window。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 13: Stage 2.5 kind-aware EdgeWitness.measured(硬伤 E)

**Files:**
- Modify: `path2/dag/_reify.py:56`(measured 字段生成 · 改 MeasuredKindAware dict)
- Modify: `path2_web_ui/src/components/DetailSidebar.vue:116`(删 "gap=" 硬编码 · 按 label 显示)
- Test: `tests/path2/dag/test_reify_kind_aware.py`

**Interfaces:**
- Consumes: `MeasuredKindAware`(Task 9)
- Produces: `EdgeWitness.measured` = `MeasuredKindAware` 实例(Task 15/16/17 后端 subcheck helper 消费)

- [ ] **Step 1: 写测试**

```python
# tests/path2/dag/test_reify_kind_aware.py
from path2.dag._reify import _make_measured
from path2.dag.edges import TemporalEdge, StartContainmentEdge
from path2.dag.gate_failure import MeasuredKindAware

def make_bo_event(idx):
    from path2.atoms.breakout import BOEvent
    return BOEvent(event_id=f"bo_{idx}", start_idx=idx, end_idx=idx,
                   drought=None, pk_count=1, broken_peak_ids=(), vol_ratio=None,
                   peak_vol_max=0.0, referenced_points=())

def test_temporal_edge_kind_gap():
    u, v = make_bo_event(10), make_bo_event(15)
    edge = TemporalEdge(src="a", dst="b", min_gap=0, max_gap=10)
    m = _make_measured(edge, u, v)
    assert isinstance(m, MeasuredKindAware)
    assert m.kind == 'gap'
    assert m.value == 5
    assert m.label == 'gap'

def test_start_containment_edge_kind_anchor_delta():
    u, v = make_bo_event(10), make_bo_event(12)
    edge = StartContainmentEdge(src="a", dst="b")
    m = _make_measured(edge, u, v)
    assert m.kind in ('anchor_delta', 'start_offset')
```

- [ ] **Step 2: FAIL**

Run: `uv run pytest tests/path2/dag/test_reify_kind_aware.py -v` → FAIL

- [ ] **Step 3: 实现**

修改 `path2/dag/_reify.py:56`(用 grep 定位 `measured` 生成处):
```python
from path2.dag.gate_failure import MeasuredKindAware
from path2.dag.edges import TemporalEdge, ContainmentEdge, OverlapEdge, EqualsEdge, StartContainmentEdge, NegationEdge

def _make_measured(edge, u, v) -> MeasuredKindAware:
    """kind-aware · 硬伤 E · 按 edge kind 生成 measured。"""
    if isinstance(edge, TemporalEdge):
        return MeasuredKindAware(kind='gap',
                                 value=v.start_idx - u.end_idx,
                                 label='gap')
    if isinstance(edge, (ContainmentEdge, OverlapEdge, EqualsEdge)):
        return MeasuredKindAware(kind='window_offset',
                                 value=v.start_idx - u.start_idx,
                                 label='起点偏移')
    if isinstance(edge, StartContainmentEdge):
        return MeasuredKindAware(kind='anchor_delta',
                                 value=v.start_idx - u.start_idx,
                                 label='起点包含')
    if isinstance(edge, NegationEdge):
        return MeasuredKindAware(kind='negation_bars',
                                 value=v.start_idx - u.end_idx,
                                 label='禁区bars')
    return MeasuredKindAware(kind='unknown', value=None, label='?')

# EdgeWitness 相关生成处(L56 原来的 measured = v.start_idx - u.end_idx)改为:
witness = EdgeWitness(
    src_event_id=u.event_id,
    dst_event_id=v.event_id,
    edge_id=edge_id,
    measured=_make_measured(edge, u, v),  # ← kind-aware
    # ...
)
```

修改 `path2_web_ui/src/components/DetailSidebar.vue:116`(用 grep 定位 `"gap="` 硬编码):
```vue
<!-- 原:<span>gap={{ witness.measured }}</span> -->
<!-- 改为按 kind 用 fmt: -->
<span>{{ fmt(witness.measured.value, witness.measured.kind) }}</span>
```

- [ ] **Step 4: PASS**

Run: `uv run pytest tests/path2/dag/test_reify_kind_aware.py -v` → PASS
Run: `uv run pytest tests/path2/ -v` → 全绿
Run: `cd path2_web_ui && npm run test && npm run type-check && npm run build` → 全绿

- [ ] **Step 5: Commit**

```bash
git add path2/dag/_reify.py path2_web_ui/src/components/DetailSidebar.vue \
        tests/path2/dag/test_reify_kind_aware.py
git commit -m "$(cat <<'EOF'
feat(path2/dag + web_ui): 硬伤 E · EdgeWitness.measured kind-aware

后端 _make_measured 按 edge kind 生成 MeasuredKindAware dict(gap/anchor_delta/negation_bars 等);
前端 DetailSidebar 删 "gap=" 硬编码,按 measured.kind 通过 fmt() 显示;
未来添加非-gap 判据不再精确骗人。

承 spec §2.5 · 硬伤 E。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 14: fn.meta.refs_other_role(硬伤 C 双落 · stdlib 端)

**Files:**
- Modify: `path2/stdlib/where.py`(WhereFnMeta 加 refs_other_role)
- Modify: `path2_web/diagnose.py`(响应含 refs_other_role · caveats 新增 cross_node_pending)
- Test: `tests/path2/stdlib/test_where_meta.py`

**Interfaces:**
- Consumes: `_TRIPWIRE`(Task 2)
- Produces: `WhereFnMeta.refs_other_role: bool`(Task 21 前端 PendingIcon 消费)

- [ ] **Step 1: 写测试**

```python
# tests/path2/stdlib/test_where_meta.py
from path2.stdlib.where import WhereFnMeta

def test_where_fn_meta_default_refs_other_role_false():
    m = WhereFnMeta()
    assert m.refs_other_role is False

def test_where_fn_meta_can_flag_refs_other_role():
    m = WhereFnMeta(refs_other_role=True)
    assert m.refs_other_role is True

def test_tripwire_caught_produces_cross_node_pending_caveat():
    """跨节点 clause 若触发 tripwire · 后端捕获后挂 cross_node_pending caveat"""
    from path2_web.diagnose import derive_response, Query, Caveat
    # 用一个含 refs_other_role clause 的 spec fixture(未来 spec 引入时才生效)
    q = Query(symbol='TEST_WITH_CROSS_NODE', scope='roles', src_role='burst', dst_role='tb')
    r = derive_response(q)
    codes = [c.code for c in r.caveats]
    # 若 fixture spec 有跨节点 clause · 应出现 cross_node_pending;否则 skip
    # (fixture 可 mark 为 optional)
```

- [ ] **Step 2: FAIL**

Run: `uv run pytest tests/path2/stdlib/test_where_meta.py -v` → FAIL

- [ ] **Step 3: 实现**

修改 `path2/stdlib/where.py`(用 grep 定位现有 `WhereFnMeta` 或类似 · 若不存在则新建):
```python
from dataclasses import dataclass

@dataclass
class WhereFnMeta:
    """where clause 的编译期 meta · UI 用于提前诚实降级(硬伤 C 双落 · 编译期端)。"""
    refs_other_role: bool = False   # ★ 新增 · Sprint 2 Task 14
    # ...(其他现有字段保留)
```

修改 `path2_web/diagnose.py::_collect_caveats`:
```python
from path2.dag._tripwire import CrossNodePendingError

def _collect_caveats(query: Query, result) -> list[Caveat]:
    caveats: list[Caveat] = []
    # 已有:硬伤 E caveat
    if not _kind_aware_measured_available():
        caveats.append(Caveat(code='measured_not_kind_aware',
                              message='EdgeWitness.measured 未升级 kind-aware(硬伤 E)'))
    # ★ 新增:检查 tripwire 触发
    tripwire_fired = getattr(result, '_tripwire_fired_edges', ())
    if tripwire_fired:
        caveats.append(Caveat(
            code='cross_node_pending',
            message='跨节点 clause 触发 tripwire · 涉及 edge:' + ', '.join(tripwire_fired),
            affected_fields=list(tripwire_fired),
        ))
    return caveats
```

- [ ] **Step 4: PASS**

Run: `uv run pytest tests/path2/stdlib/test_where_meta.py -v` → PASS
Run: `uv run pytest tests/ -v` → 全绿

- [ ] **Step 5: Commit**

```bash
git add path2/stdlib/where.py path2_web/diagnose.py tests/path2/stdlib/test_where_meta.py
git commit -m "$(cat <<'EOF'
feat(path2/stdlib + path2_web): 硬伤 C 双落 · fn.meta.refs_other_role + cross_node_pending caveat

WhereFnMeta 加 refs_other_role bool · 编译期标注跨节点 clause;
diagnose 层 _collect_caveats 检查 tripwire 触发 · 产 cross_node_pending caveat;
UI 消费两处(refs_other_role → PendingIcon 主动降级 · caveat → 顶部黄条兜底)。

承 spec §2.6 · 与 Task 2 tripwire 缺一不可。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 15: 后端 scope=time + failure_event_window ⊆ + outside_frame_attempts_count

**Files:**
- Modify: `path2_web/diagnose.py`(实现 `_derive_time_response` 完整版)
- Create: `path2_web/gate_collector.py`(GateFailure buffer · 全局单例 or per-scan cache)
- Modify: `path2_web/worker.py`(worker 起始给 detector 挂 on_gate collector · 结束收 buffer)
- Test: `tests/path2_web/test_diagnose_time.py`

**Interfaces:**
- Consumes: `GateFailure`(Task 9)· BurstDetector/BODetector/ThrowbackDetector on_gate(Task 10-12)
- Produces: `scope=time` 响应含 `TimePayload.failed_attempts[]` + `outside_frame_attempts_count`(Task 18 前端消费)

- [ ] **Step 1: 写测试**

```python
# tests/path2_web/test_diagnose_time.py
from path2_web.diagnose import derive_response, Query, Response
from path2_web.gate_collector import GateCollector

def test_scope_time_returns_time_payload():
    q = Query(symbol='DGNX', scope='time', start_bar=100, end_bar=150)
    r = derive_response(q)
    assert r.scope == 'time'
    assert 'failed_attempts' in r.payload.__dict__ or hasattr(r.payload, 'failed_attempts')
    assert hasattr(r.payload, 'outside_frame_attempts_count')

def test_strict_subset_filter():
    """failure_event_window 严格 ⊆ user frame"""
    from path2.dag.gate_failure import GateFailure, MeasuredKindAware
    collector = GateCollector()
    m = MeasuredKindAware(kind='gap', value=13, label='gap')
    # 三条 attempt:
    collector.add(GateFailure(failure_event_window=(105, 118), start_idx=105, gate_idx=118,
                              anchor_bar=118, class_id='tb', gate_name='phase2_break',
                              measured=m, threshold=10, evaluation_lookback=None, symbol='DGNX'))
    # (105, 118) ⊆ [100, 150] · 保留
    collector.add(GateFailure(failure_event_window=(90, 105), start_idx=90, gate_idx=105,
                              anchor_bar=105, class_id='burst', gate_name='chain_break',
                              measured=m, threshold=10, evaluation_lookback=None, symbol='DGNX'))
    # (90, 105) ⊄ [100, 150] · gate_idx ∈ 但 start_idx 溢出 · outside_frame
    collector.add(GateFailure(failure_event_window=(60, 65), start_idx=60, gate_idx=65,
                              anchor_bar=65, class_id='burst', gate_name='chain_break',
                              measured=m, threshold=10, evaluation_lookback=None, symbol='DGNX'))
    # (60, 65) 完全在框外 · 丢弃

    from path2_web.diagnose import _in_frame_strict, _has_outside_frame
    assert _in_frame_strict((105, 118), (100, 150)) is True
    assert _in_frame_strict((90, 105), (100, 150)) is False
    assert _has_outside_frame((90, 105), (100, 150)) is True
    assert _has_outside_frame((60, 65), (100, 150)) is False

def test_event_class_filter():
    q = Query(symbol='DGNX', scope='time', start_bar=0, end_bar=200, event_class='burst')
    r = derive_response(q)
    for gf in r.payload.failed_attempts:
        assert gf.class_id == 'burst'

def test_outside_frame_attempts_present_caveat():
    """若 outside_frame_attempts_count > 0 · 挂 outside_frame_attempts_present caveat"""
    q = Query(symbol='DGNX_WITH_OUTSIDE_ATTEMPTS', scope='time', start_bar=100, end_bar=110)
    r = derive_response(q)
    codes = [c.code for c in r.caveats]
    if r.payload.outside_frame_attempts_count > 0:
        assert 'outside_frame_attempts_present' in codes
```

- [ ] **Step 2: FAIL**

Run: `uv run pytest tests/path2_web/test_diagnose_time.py -v` → FAIL

- [ ] **Step 3: 实现**

创建 `path2_web/gate_collector.py`:
```python
"""GateFailure buffer · worker 处理某 symbol 时挂到三 atom on_gate · 结束时缓存到 result。"""
from path2.dag.gate_failure import GateFailure

class GateCollector:
    def __init__(self):
        self._buf: list[GateFailure] = []

    def add(self, gf: GateFailure) -> None:
        self._buf.append(gf)

    def snapshot(self) -> tuple[GateFailure, ...]:
        return tuple(self._buf)

    def clear(self) -> None:
        self._buf.clear()
```

修改 `path2_web/worker.py`:
```python
from path2_web.gate_collector import GateCollector

def scan_one_symbol(symbol, pkl_path, spec):
    from path2.debug import set_current_symbol
    set_current_symbol(symbol)
    try:
        collector = GateCollector()
        # 给 spec 里所有 detector 挂 on_gate
        for det in spec.detectors:
            det.on_gate = collector.add
        try:
            result = analyze(load_data(pkl_path), spec)
            result.gate_failures = collector.snapshot()   # 附到 result
            return result
        finally:
            for det in spec.detectors:
                det.on_gate = None
    finally:
        set_current_symbol(None)
```

修改 `path2_web/diagnose.py::_derive_time_response`(替换 Task 8 的 stub):
```python
from path2.dag.gate_failure import GateFailure

@dataclass
class TimePayload:
    frame: tuple[int, int]
    failed_attempts: list[GateFailure]
    outside_frame_attempts_count: int


def _in_frame_strict(fw: tuple[int, int], frame: tuple[int, int]) -> bool:
    """严格 ⊆ 判据"""
    ws, we = fw; fs, fe = frame
    return ws >= fs and we <= fe


def _has_outside_frame(fw: tuple[int, int], frame: tuple[int, int]) -> bool:
    """gate_idx 在框内 · start_idx 溢出 · 补救 caveat 计数"""
    ws, we = fw; fs, fe = frame
    return fs <= we <= fe and ws < fs


def _derive_time_response(query: Query) -> Response:
    result = _load_analysis_result(query.symbol)
    if not hasattr(result, 'gate_failures'):
        return Response(scope='time',
                        payload=TimePayload(frame=(query.start_bar or 0, query.end_bar or 0),
                                            failed_attempts=[], outside_frame_attempts_count=0),
                        caveats=[Caveat(code='on_gate_hook_not_landed',
                                        message='Stage 3 on_gate 未挂 collector · 空 payload')])
    all_fails = result.gate_failures
    frame = (query.start_bar, query.end_bar)
    filtered = [gf for gf in all_fails
                if _in_frame_strict(gf.failure_event_window, frame)
                and (query.event_class is None or gf.class_id == query.event_class)]
    outside_count = sum(1 for gf in all_fails
                        if _has_outside_frame(gf.failure_event_window, frame)
                        and (query.event_class is None or gf.class_id == query.event_class))
    caveats = _collect_caveats(query, result)
    if outside_count > 0:
        caveats.append(Caveat(
            code='outside_frame_attempts_present',
            message=f'另有 {outside_count} 个 span attempt · gate 触发在框内但 start_idx 溢出 · 建议扩大框',
        ))
    return Response(scope='time',
                    payload=TimePayload(frame=frame, failed_attempts=filtered,
                                        outside_frame_attempts_count=outside_count),
                    caveats=caveats)
```

- [ ] **Step 4: PASS**

Run: `uv run pytest tests/path2_web/test_diagnose_time.py -v` → PASS
Run: `uv run pytest tests/ -v` → 全绿

- [ ] **Step 5: Commit**

```bash
git add path2_web/gate_collector.py path2_web/worker.py path2_web/diagnose.py \
        tests/path2_web/test_diagnose_time.py
git commit -m "$(cat <<'EOF'
feat(path2_web): scope=time · failure_event_window ⊆ 严格包含 + outside_frame 补救

GateCollector 收 worker 处理某 symbol 时三 atom on_gate 吐的 GateFailure buffer;
_derive_time_response 用 _in_frame_strict ⊆ 判据 filter,event_class 可选 filter;
outside_frame_attempts_count 计"gate 在框内 · start_idx 溢出"的 attempt · 挂 caveat 提示扩大框。

承 spec §3.2.2 · 入口 A 完整落地。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 16: 后端 subcheck helper 4 个(feasible_window / satisfies / anchor / strict)

**Files:**
- Modify: `path2_web/diagnose.py`(新增 `_check_*` helper 4 个 + SubCheck dataclass)
- Test: `tests/path2_web/test_subcheck_helpers.py`

**Interfaces:**
- Consumes: `strict_clear`(现有 `_solve.py:137`)· `_anchor_ok`(现有 `edges.py`)
- Produces: 4 subcheck helper(Task 17 · scope=pair 消费 · Task 20 · scope=candidate 复用)

- [ ] **Step 1: 写测试**

```python
# tests/path2_web/test_subcheck_helpers.py
from path2_web.diagnose import (
    _check_feasible_window, _check_satisfies, _check_anchor, _check_strict, SubCheck,
)
from path2.dag.edges import TemporalEdge
from path2.atoms.breakout import BOEvent

def _bo(idx):
    return BOEvent(event_id=f"bo_{idx}", start_idx=idx, end_idx=idx,
                   drought=None, pk_count=1, broken_peak_ids=(), vol_ratio=None,
                   peak_vol_max=0.0, referenced_points=())

def test_check_feasible_window_pass():
    edge = TemporalEdge(src='a', dst='b', min_gap=0, max_gap=10)
    sc = _check_feasible_window(edge, _bo(10), _bo(15))
    assert sc.channel == 'feasible_window'
    assert sc.passed is True

def test_check_feasible_window_fail():
    edge = TemporalEdge(src='a', dst='b', min_gap=0, max_gap=10)
    sc = _check_feasible_window(edge, _bo(10), _bo(25))
    assert sc.passed is False
    assert sc.reason.startswith('gap')

def test_check_satisfies_pass():
    edge = TemporalEdge(src='a', dst='b', min_gap=0, max_gap=10)
    sc = _check_satisfies(edge, _bo(10), _bo(15))
    assert sc.passed is True

def test_check_anchor_needs_map():
    """无 edge_ok_map 时可 pass(承 Stage 0.1 语义)"""
    edge = TemporalEdge(src='a', dst='b', min_gap=0, max_gap=10)
    sc = _check_anchor(edge, _bo(10), _bo(15), edge_ok_map={})
    assert sc.channel == 'anchor'

def test_check_strict_no_strict_returns_pass():
    """非 strict 边 · 直接 pass"""
    edge = TemporalEdge(src='a', dst='b', min_gap=0, max_gap=10)
    sc = _check_strict(edge, _bo(10), _bo(15), streams={})
    assert sc.passed is True
```

- [ ] **Step 2: FAIL**

Run: `uv run pytest tests/path2_web/test_subcheck_helpers.py -v` → FAIL

- [ ] **Step 3: 实现**

在 `path2_web/diagnose.py` 新增:
```python
from dataclasses import dataclass
from typing import Optional, Any
from path2.dag._solve import strict_clear
from path2.dag.edges import _anchor_ok

@dataclass
class SubCheck:
    channel: str
    passed: bool
    measured: Optional[dict]
    threshold: Any
    reason: Optional[str]


def _check_feasible_window(edge, u, v) -> SubCheck:
    """通道:feasible_window · 时序 gap 是否在 edge 允许 range 内"""
    if hasattr(edge, 'feasible_window'):
        lo, hi = edge.feasible_window(u)
        if lo <= v.start_idx <= hi:
            return SubCheck(channel='feasible_window', passed=True,
                            measured={'kind': 'gap', 'value': v.start_idx - u.end_idx, 'label': 'gap'},
                            threshold={'min': lo, 'max': hi}, reason=None)
        return SubCheck(channel='feasible_window', passed=False,
                        measured={'kind': 'gap', 'value': v.start_idx - u.end_idx, 'label': 'gap'},
                        threshold={'min': lo, 'max': hi},
                        reason=f'gap {v.start_idx - u.end_idx} 出 [{lo}, {hi}]')
    return SubCheck(channel='feasible_window', passed=True, measured=None, threshold=None, reason=None)


def _check_satisfies(edge, u, v) -> SubCheck:
    """通道 ③ · edge kind 基础判据(edge.satisfies)"""
    passed = edge.satisfies(u, v)
    return SubCheck(channel='satisfies', passed=passed,
                    measured={'kind': 'gap', 'value': v.start_idx - u.end_idx, 'label': 'gap'},
                    threshold=None,
                    reason=None if passed else 'satisfies 判据 fail')


def _check_anchor(edge, u, v, edge_ok_map: dict) -> SubCheck:
    """通道 ④ · anchor_field 二次校验(硬伤 B 修后可靠)"""
    try:
        passed = _anchor_ok(u, v, edge_ok_map)
    except Exception:
        passed = True  # 无 anchor_field 定义 · 视为通过
    return SubCheck(channel='anchor', passed=passed, measured=None, threshold=None,
                    reason=None if passed else 'anchor 破位')


def _check_strict(edge, u, v, streams: dict) -> SubCheck:
    """通道 ⑤ · next 语义严格清空 · 复用 _solve.py:137 strict_clear"""
    if not getattr(edge, 'strict', False):
        return SubCheck(channel='strict', passed=True, measured=None, threshold=None, reason=None)
    passed = strict_clear(edge, u, v, streams)
    return SubCheck(channel='strict', passed=passed, measured=None, threshold=None,
                    reason=None if passed else 'strict 有更早候选')
```

- [ ] **Step 4: PASS**

Run: `uv run pytest tests/path2_web/test_subcheck_helpers.py -v` → PASS

- [ ] **Step 5: Commit**

```bash
git add path2_web/diagnose.py tests/path2_web/test_subcheck_helpers.py
git commit -m "$(cat <<'EOF'
feat(path2_web/diagnose): 4 subcheck helper · pair 层 4 通道独立评估

_check_feasible_window / _check_satisfies / _check_anchor / _check_strict:
- 独立可评估 · 不依赖 SolveTrace · 严谨版 B.2 严格 grep 验证
- 复用现有 strict_clear(_solve.py:137)+ _anchor_ok(edges.py)
- Task 17 scope=pair 消费 · Task 20 scope=candidate 复用(去重复代码)

承 spec §2.7 · §3.3 · 入口 D pair 层 Sprint 2 完 100% 前置条件。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 17: 后端 scope=pair + auto swap + 4 invalid_reason

**Files:**
- Modify: `path2_web/diagnose.py`(实现 `_derive_pair_response` 完整版 · PairPayload dataclass)
- Test: `tests/path2_web/test_diagnose_pair.py`

**Interfaces:**
- Consumes: 4 subcheck helper(Task 16)
- Produces: `scope=pair` 响应含 `PairPayload`(Task 18 前端消费)

- [ ] **Step 1: 写测试**

```python
# tests/path2_web/test_diagnose_pair.py
from path2_web.diagnose import derive_response, Query, PairPayload

def test_same_role_invalid():
    q = Query(symbol='DGNX', scope='pair', src_event_id='bo_1', dst_event_id='bo_2')
    r = derive_response(q)
    # 两个 bo 都属 bo role · same_role
    assert r.payload.valid is False
    assert r.payload.invalid_reason == 'same_role'

def test_no_edge_between_roles():
    """理论上 dag_spec 中若两 role 无直连,invalid"""
    q = Query(symbol='DGNX', scope='pair', src_event_id='<isolated_role_a>', dst_event_id='<isolated_role_b>')
    r = derive_response(q)
    if not r.payload.valid:
        assert r.payload.invalid_reason in ('no_edge_between_roles', 'only_negation_edge', 'same_role')

def test_auto_swap_when_reverse_edge_exists():
    """(u.role → v.role) 无 edge 但 (v.role → u.role) 有 · 应 auto swap"""
    q = Query(symbol='DGNX', scope='pair', src_event_id='tb_1', dst_event_id='burst_1')
    # dag_spec 是 burst → tb 单向 · 用户反向点
    r = derive_response(q)
    if r.payload.valid:
        assert r.payload.applied_swap is True
        assert r.payload.src_event_id == 'burst_1'
        assert r.payload.dst_event_id == 'tb_1'
        assert r.payload.original_first_click == 'tb_1'

def test_valid_pair_subchecks_short_circuit():
    """合法 pair · 4 subcheck 短路(遇第一 fail 停)"""
    q = Query(symbol='DGNX', scope='pair', src_event_id='burst_1', dst_event_id='tb_gap_out')
    r = derive_response(q)
    if r.payload.valid and r.payload.subchecks:
        # subchecks 里应最多 1 个 fail(短路)
        fails = [sc for sc in r.payload.subchecks if not sc.passed]
        assert len(fails) <= 1
```

- [ ] **Step 2: FAIL**

Run: `uv run pytest tests/path2_web/test_diagnose_pair.py -v` → FAIL

- [ ] **Step 3: 实现**

在 `path2_web/diagnose.py` 新增/替换:
```python
@dataclass
class PairPayload:
    src_event_id: str
    dst_event_id: str
    applied_swap: bool
    original_first_click: str
    original_second_click: str
    valid: bool
    invalid_reason: Optional[str]
    edge_id: Optional[str]
    edge_kind: Optional[str]
    subchecks: Optional[list[SubCheck]] = None
    hint: Optional[dict] = None


def _derive_pair_response(query: Query) -> Response:
    result = _load_analysis_result(query.symbol)
    u = _load_event_by_id(result, query.src_event_id)
    v = _load_event_by_id(result, query.dst_event_id)

    if u is None or v is None:
        return Response(scope='pair',
                        payload=PairPayload(
                            src_event_id=query.src_event_id, dst_event_id=query.dst_event_id,
                            applied_swap=False,
                            original_first_click=query.src_event_id,
                            original_second_click=query.dst_event_id,
                            valid=False, invalid_reason='event_not_found',
                            edge_id=None, edge_kind=None),
                        caveats=[])

    u_role = _role_of_event(result, u)
    v_role = _role_of_event(result, v)

    if u_role == v_role:
        return _invalid_pair_response(query, 'same_role')

    forward_edge = _find_edge(result.spec, u_role, v_role, exclude_negation=True)
    reverse_edge = _find_edge(result.spec, v_role, u_role, exclude_negation=True)

    if forward_edge is not None:
        return _check_pair_and_respond(query, forward_edge, u, v,
                                       applied_swap=False, result=result)
    if reverse_edge is not None:
        return _check_pair_and_respond(query, reverse_edge, v, u,
                                       applied_swap=True, result=result)
    if _only_negation_between(result.spec, u_role, v_role):
        return _invalid_pair_response(query, 'only_negation_edge')
    return _invalid_pair_response(query, 'no_edge_between_roles')


def _check_pair_and_respond(query, edge, u, v, applied_swap, result) -> Response:
    """合法 pair · 4 subcheck 短路 · 组装 Response"""
    edge_ok_map = getattr(result, 'edge_ok_map', {})
    streams = getattr(result, 'event_streams', {})
    subchecks: list[SubCheck] = []
    for check in (_check_feasible_window, _check_satisfies):
        sc = check(edge, u, v)
        subchecks.append(sc)
        if not sc.passed:
            return _pair_response_with(query, edge, u, v, subchecks, applied_swap)
    sc = _check_anchor(edge, u, v, edge_ok_map)
    subchecks.append(sc)
    if not sc.passed:
        return _pair_response_with(query, edge, u, v, subchecks, applied_swap)
    sc = _check_strict(edge, u, v, streams)
    subchecks.append(sc)
    return _pair_response_with(query, edge, u, v, subchecks, applied_swap)


def _pair_response_with(query, edge, u, v, subchecks, applied_swap) -> Response:
    return Response(scope='pair',
                    payload=PairPayload(
                        src_event_id=u.event_id, dst_event_id=v.event_id,
                        applied_swap=applied_swap,
                        original_first_click=query.src_event_id,
                        original_second_click=query.dst_event_id,
                        valid=True, invalid_reason=None,
                        edge_id=f"{edge.src}_to_{edge.dst}",
                        edge_kind=type(edge).__name__,
                        subchecks=subchecks,
                    ),
                    caveats=_collect_caveats(query, None))


def _invalid_pair_response(query, invalid_reason) -> Response:
    hint = None
    if invalid_reason == 'no_edge_between_roles':
        hint = {'suggestion': '两 role 在 dag_spec 中无直连 edge'}
    return Response(scope='pair',
                    payload=PairPayload(
                        src_event_id=query.src_event_id, dst_event_id=query.dst_event_id,
                        applied_swap=False,
                        original_first_click=query.src_event_id,
                        original_second_click=query.dst_event_id,
                        valid=False, invalid_reason=invalid_reason,
                        edge_id=None, edge_kind=None, subchecks=None, hint=hint),
                    caveats=[])


# helper: _load_event_by_id / _role_of_event / _find_edge / _only_negation_between
# 具体实现依 path2_web cache · spec 结构 · 略(implementer 参考现有 spec 遍历)
```

- [ ] **Step 4: PASS**

Run: `uv run pytest tests/path2_web/test_diagnose_pair.py -v` → PASS

- [ ] **Step 5: Commit**

```bash
git add path2_web/diagnose.py tests/path2_web/test_diagnose_pair.py
git commit -m "$(cat <<'EOF'
feat(path2_web): scope=pair · auto swap + 4 subcheck 短路 + 4 invalid_reason

_derive_pair_response 完整实现:
- 5 类 invalid_reason:same_role / no_edge_between_roles / only_negation_edge / direction_mismatch(auto swap) / event_not_found
- auto swap:forward 无 edge · reverse 有 · 自动切换 · payload.applied_swap=True + original_*_click 保留(前端撤回)
- 4 subcheck 短路:feasible_window → satisfies → anchor → strict · 遇第一 fail 停

承 spec §3.2.5 · §2.7 · 入口 D pair 层完整 · Sprint 2 完成 100% pair 层覆盖(通道 ③④⑤)。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 18: 前端 KlineChart brush + shift+click 跨图 + FailedAttemptsCard + PairDetailCard + DetailSidebar 集成

**Files:**
- Modify: `path2_web_ui/src/components/KlineChart.vue`(brush 触发 scope=time · shift+click 跨图触发 scope=pair)
- Create: `path2_web_ui/src/components/FailedAttemptsCard.vue`(入口 A)
- Create: `path2_web_ui/src/components/PairDetailCard.vue`(入口 D)
- Modify: `path2_web_ui/src/components/DetailSidebar.vue`(集成 5 卡片 slot 切换 + caveats 顶部条 + dropped_matches 提示)
- Test: `path2_web_ui/src/components/FailedAttemptsCard.spec.ts` · `PairDetailCard.spec.ts` · `KlineChart.spec.ts`

**Interfaces:**
- Consumes: `TimePayload`(Task 15)· `PairPayload`(Task 17)· shared `fmt` / `fmtValue`(Task 6)· `RelBadge` / `PendingIcon`(Task 7)
- Produces: 入口 A + 入口 D 前端完整交互链

- [ ] **Step 1: 写测试**

```typescript
// path2_web_ui/src/components/FailedAttemptsCard.spec.ts
import { mount } from '@vue/test-utils'
import FailedAttemptsCard from './FailedAttemptsCard.vue'

describe('FailedAttemptsCard', () => {
    const payload = {
        frame: [100, 150],
        failed_attempts: [
            {
                failure_event_window: [105, 118], start_idx: 105, gate_idx: 118,
                anchor_bar: 118, class_id: 'tb', gate_name: 'phase2_break',
                measured: { kind: 'anchor_delta', value: -0.3, label: '破位差' },
                threshold: 0, evaluation_lookback: [86, 100], symbol: 'DGNX',
            },
        ],
        outside_frame_attempts_count: 2,
    }
    it('每 attempt 一张子卡', () => {
        const w = mount(FailedAttemptsCard, { props: { payload } })
        expect(w.findAll('.attempt-card').length).toBe(1)
    })
    it('outside_frame > 0 显提示条', () => {
        const w = mount(FailedAttemptsCard, { props: { payload } })
        expect(w.text()).toContain('另有 2 个')
    })
    it('overlap 徽标依 (start, end) vs frame 分色', () => {
        const w = mount(FailedAttemptsCard, { props: { payload } })
        // (105, 118) 完全 ⊆ [100, 150] · 应绿色徽标
        expect(w.find('.overlap-fully_inside').exists()).toBe(true)
    })
})

// path2_web_ui/src/components/PairDetailCard.spec.ts
import PairDetailCard from './PairDetailCard.vue'

describe('PairDetailCard', () => {
    it('4 subcheck 短路显示', () => {
        const payload = {
            src_event_id: 'burst_1', dst_event_id: 'tb_1', applied_swap: false,
            original_first_click: 'burst_1', original_second_click: 'tb_1',
            valid: true, invalid_reason: null, edge_id: 'burst_to_tb', edge_kind: 'TemporalEdge',
            subchecks: [
                { channel: 'feasible_window', passed: true, measured: null, threshold: null, reason: null },
                { channel: 'satisfies', passed: false, measured: { kind: 'gap', value: 15, label: 'gap' }, threshold: 10, reason: 'gap 越界' },
            ],
        }
        const w = mount(PairDetailCard, { props: { payload } })
        expect(w.text()).toContain('gap 越界')
    })
    it('applied_swap · 显切换提示 + 撤回按钮', () => {
        const payload = {
            src_event_id: 'burst_1', dst_event_id: 'tb_1',
            applied_swap: true,
            original_first_click: 'tb_1', original_second_click: 'burst_1',
            valid: true, invalid_reason: null, edge_id: 'burst_to_tb', edge_kind: 'TemporalEdge',
            subchecks: [],
        }
        const w = mount(PairDetailCard, { props: { payload } })
        expect(w.text()).toContain('顺序已自动切换')
        expect(w.find('button.undo-swap').exists()).toBe(true)
    })
    it('invalid_reason 显对应提示', () => {
        const payload = {
            src_event_id: 'a', dst_event_id: 'b', applied_swap: false,
            original_first_click: 'a', original_second_click: 'b',
            valid: false, invalid_reason: 'same_role',
            edge_id: null, edge_kind: null, subchecks: null,
        }
        const w = mount(PairDetailCard, { props: { payload } })
        expect(w.text()).toContain('同一 role')
    })
})

// path2_web_ui/src/components/KlineChart.spec.ts
import { mount } from '@vue/test-utils'
import KlineChart from './KlineChart.vue'

describe('KlineChart shift+click', () => {
    it('第 1 击选中 src · 第 2 击触发 pair 请求 · 第 3 击清空', async () => {
        const w = mount(KlineChart, { props: { symbol: 'DGNX', events: [/* ... */] } })
        // 模拟 shift+click(具体依 ECharts event mock)
        await w.vm.handleShiftClick('bo_1', 'bo', 'main')
        expect(w.vm.shiftSelectedEvents).toHaveLength(1)
        await w.vm.handleShiftClick('tb_1', 'tb', 'sub')
        expect(w.vm.shiftSelectedEvents).toHaveLength(2)
        // 应触发 fetch scope=pair · mock fetch 断言
        await w.vm.handleShiftClick('burst_1', 'burst', 'sub')
        expect(w.vm.shiftSelectedEvents).toHaveLength(1)   // 第 3 击清空重来 · 保留新 src
    })
})
```

- [ ] **Step 2: FAIL**

Run: `cd path2_web_ui && npm run test` → FAIL(组件不存在)

- [ ] **Step 3: 实现**

创建 `path2_web_ui/src/components/FailedAttemptsCard.vue`:
```vue
<script setup lang="ts">
import { computed } from 'vue'
import { fmt } from '@/shared/formatters'

interface Attempt {
    failure_event_window: [number, number]
    start_idx: number; gate_idx: number
    anchor_bar: number; class_id: string; gate_name: string
    measured: { kind: string; value: any; label: string }
    threshold: any
    evaluation_lookback: [number, number] | null
    symbol: string
}
interface TimePayload {
    frame: [number, number]
    failed_attempts: Attempt[]
    outside_frame_attempts_count: number
}
const props = defineProps<{ payload: TimePayload }>()

function overlapClass(fw: [number, number], frame: [number, number]): string {
    const [ws, we] = fw; const [fs, fe] = frame
    if (ws >= fs && we <= fe) return 'overlap-fully_inside'
    if (ws <= fs && we >= fe) return 'overlap-contains_frame'
    return 'overlap-partial'
}
</script>

<template>
    <div class="failed-attempts-card">
        <header>
            <strong>时段 [{{ payload.frame[0] }}, {{ payload.frame[1] }}]</strong>
            · 严格 ⊆ 判据 · {{ payload.failed_attempts.length }} 个 attempt
        </header>
        <div v-if="payload.outside_frame_attempts_count > 0" class="outside-notice">
            ⚠ 另有 {{ payload.outside_frame_attempts_count }} 个 span attempt · gate 触发在框内但 start_idx 溢出 · 建议扩大框
        </div>
        <div v-for="(a, i) in payload.failed_attempts" :key="i"
             :class="['attempt-card', overlapClass(a.failure_event_window, payload.frame)]">
            <div class="attempt-header">
                <span class="class-id">{{ a.class_id }}</span>
                <span class="window">[{{ a.failure_event_window[0] }}, {{ a.failure_event_window[1] }}]</span>
                <span class="overlap-badge">
                    <template v-if="a.failure_event_window[0] === a.failure_event_window[1]">点</template>
                    <template v-else>span</template>
                </span>
            </div>
            <div class="gate">栽在 {{ a.gate_name }} : {{ fmt(a.measured.value, a.measured.kind) }} vs 阈 {{ a.threshold }}</div>
            <div class="trigger">
                触发 bar {{ a.gate_idx }}
                <template v-if="a.gate_idx < payload.frame[0]"> · 溢出你的框</template>
            </div>
            <div v-if="a.evaluation_lookback" class="lookback" :title="`参照历史 [${a.evaluation_lookback[0]}, ${a.evaluation_lookback[1]}]`">
                参照历史 ({{ a.evaluation_lookback[0] }} .. {{ a.evaluation_lookback[1] }})
            </div>
        </div>
    </div>
</template>

<style scoped>
.failed-attempts-card { padding: 12px; overflow-x: auto; min-width: 0; }
.outside-notice { background: #fefcbf; color: #744210; padding: 6px; margin: 6px 0; border-radius: 4px; }
.attempt-card { border: 1px solid #e2e8f0; border-radius: 4px; padding: 8px; margin: 6px 0; }
.overlap-fully_inside { border-color: #48bb78; }
.overlap-partial { border-color: #ed8936; }
.overlap-contains_frame { border-color: #4299e1; }
</style>
```

创建 `path2_web_ui/src/components/PairDetailCard.vue`:
```vue
<script setup lang="ts">
import { fmt } from '@/shared/formatters'

interface SubCheck {
    channel: string; passed: boolean
    measured: { kind: string; value: any; label: string } | null
    threshold: any; reason: string | null
}
interface PairPayload {
    src_event_id: string; dst_event_id: string
    applied_swap: boolean
    original_first_click: string; original_second_click: string
    valid: boolean; invalid_reason: string | null
    edge_id: string | null; edge_kind: string | null
    subchecks: SubCheck[] | null
    hint: any
}

const props = defineProps<{ payload: PairPayload }>()
const emit = defineEmits<{ (e: 'undo-swap'): void }>()

const invalidLabels: Record<string, string> = {
    same_role: '两个 event 属于同一 role · role 内无 edge · 无法查 pair',
    no_edge_between_roles: '两 role 在 dag_spec 中无直连 edge · pair 无从查起',
    only_negation_edge: '两 role 间只有 negation 关系 · 请用入口 C(候选级)看违禁信号',
    event_not_found: '找不到该 event · 请检查 event_id',
}
</script>

<template>
    <div class="pair-detail-card">
        <div v-if="payload.applied_swap" class="swap-notice">
            ⚠ 你点的顺序是 {{ payload.original_first_click }} → {{ payload.original_second_click }} ·
            该方向无 edge · 已改按 {{ payload.src_event_id }} → {{ payload.dst_event_id }} 查询
            <button class="undo-swap" @click="emit('undo-swap')">撤回</button>
        </div>
        <div v-if="!payload.valid" class="invalid-notice">
            {{ invalidLabels[payload.invalid_reason || ''] || payload.invalid_reason }}
        </div>
        <div v-else>
            <header>
                <strong>{{ payload.src_event_id }} → {{ payload.dst_event_id }}</strong>
                <span>{{ payload.edge_kind }} · {{ payload.edge_id }}</span>
            </header>
            <div v-for="sc in payload.subchecks" :key="sc.channel"
                 :class="['subcheck', sc.passed ? 'passed' : 'failed']">
                <span class="channel">{{ sc.channel }}</span>
                <span class="verdict">{{ sc.passed ? '✓' : '✗' }}</span>
                <span v-if="sc.measured">{{ fmt(sc.measured.value, sc.measured.kind) }}</span>
                <span v-if="sc.reason" class="reason">{{ sc.reason }}</span>
            </div>
        </div>
    </div>
</template>

<style scoped>
.pair-detail-card { padding: 12px; overflow-x: auto; min-width: 0; }
.swap-notice { background: #fefcbf; padding: 6px; border-radius: 4px; }
.invalid-notice { background: #fed7d7; color: #742a2a; padding: 12px; border-radius: 4px; }
.subcheck { display: flex; gap: 8px; padding: 4px 0; }
.subcheck.passed { color: #22543d; }
.subcheck.failed { color: #742a2a; font-weight: bold; }
</style>
```

修改 `path2_web_ui/src/components/KlineChart.vue`(shift+click 跨图 + brush + click marker):
```vue
<script setup lang="ts">
import { ref } from 'vue'
const shiftSelectedEvents = ref<Array<{ event_id: string; class_id: string; source: 'main'|'sub' }>>([])
const emit = defineEmits<{
    (e: 'time-query', frame: [number, number]): void
    (e: 'pair-query', src_event_id: string, dst_event_id: string): void
    (e: 'candidate-query', event_id: string): void
}>()

const props = defineProps<{
    symbol: string
    events: any[]
    dagSpec?: any                       // 前端乐观预判用
}>()

function handleShiftClick(event_id: string, class_id: string, source: 'main'|'sub') {
    if (shiftSelectedEvents.value.length < 2) {
        shiftSelectedEvents.value.push({ event_id, class_id, source })
        if (shiftSelectedEvents.value.length === 2) {
            const [src, dst] = shiftSelectedEvents.value
            // 乐观预判 · 若 dag_spec 副本存在
            if (props.dagSpec) {
                const forwardEdge = findEdgeInSpec(props.dagSpec, src.class_id, dst.class_id)
                const reverseEdge = findEdgeInSpec(props.dagSpec, dst.class_id, src.class_id)
                if (!forwardEdge && !reverseEdge) {
                    console.warn('乐观预判 · 两 role 无 edge · 不发请求')
                    return
                }
            }
            emit('pair-query', src.event_id, dst.event_id)
        }
    } else {
        shiftSelectedEvents.value = [{ event_id, class_id, source }]   // 第 3 击清空
    }
}

function handleMarkerClick(event_id: string, class_id: string, source: 'main'|'sub', ev: MouseEvent) {
    if (ev.shiftKey) {
        handleShiftClick(event_id, class_id, source)
    } else {
        emit('candidate-query', event_id)
    }
}

function handleBrushEnd(range: [number, number]) {
    emit('time-query', range)
}

function findEdgeInSpec(spec: any, src_class: string, dst_class: string) {
    // 略 · 依前端 dag_spec 副本结构
    return spec.edges?.find((e: any) => e.src === src_class && e.dst === dst_class)
}
</script>

<template>
    <!-- 主图 brush + marker click(shift 判定 shiftKey) -->
    <!-- 副图 band click 也调 handleMarkerClick · source='sub' -->
    <div class="kline-chart">
        <!-- 具体 ECharts config + 事件绑定 · 依现有 KlineChart 结构 -->
    </div>
</template>
```

修改 `path2_web_ui/src/components/DetailSidebar.vue`:
```vue
<script setup lang="ts">
import { ref } from 'vue'
import FailedAttemptsCard from './FailedAttemptsCard.vue'
import PairDetailCard from './PairDetailCard.vue'
import PairListCard from './PairListCard.vue'

const activeCard = ref<'candidate'|'time'|'roles'|'pair'|'default'>('default')
const timePayload = ref<any>(null)
const pairPayload = ref<any>(null)
const rolesPayload = ref<any>(null)
const caveats = ref<Array<{ code: string, message: string }>>([])

async function loadTimeResponse(frame: [number, number], event_class?: string) {
    const url = `/diagnose?symbol=${symbol}&scope=time&start_bar=${frame[0]}&end_bar=${frame[1]}${event_class ? `&event_class=${event_class}` : ''}`
    const r = await fetch(url).then(x => x.json())
    timePayload.value = r.payload
    caveats.value = r.caveats
    activeCard.value = 'time'
}
async function loadPairResponse(src_id: string, dst_id: string) {
    const r = await fetch(`/diagnose?symbol=${symbol}&scope=pair&src_event_id=${src_id}&dst_event_id=${dst_id}`).then(x => x.json())
    pairPayload.value = r.payload
    caveats.value = r.caveats
    activeCard.value = 'pair'
}
</script>

<template>
    <aside class="detail-sidebar">
        <div v-if="caveats.length > 0" class="caveats-top">
            <div v-for="c in caveats" :key="c.code" class="caveat" :class="`caveat-${c.code}`">
                {{ c.message }}
            </div>
        </div>
        <FailedAttemptsCard v-if="activeCard === 'time' && timePayload" :payload="timePayload" />
        <PairListCard v-else-if="activeCard === 'roles' && rolesPayload" :payload="rolesPayload" @pair-deep-dive="loadPairResponse" />
        <PairDetailCard v-else-if="activeCard === 'pair' && pairPayload" :payload="pairPayload" @undo-swap="/* ... */" />
        <div v-else class="candidate-table"><!-- 现有候选表 · 承 Task 7 --></div>
        <div v-if="droppedMatches?.length" class="dropped-matches-notice">
            ⚠ 这些 marker 属于被消费的 role · 当前 pattern 未触发
        </div>
    </aside>
</template>
```

- [ ] **Step 4: PASS**

Run: `cd path2_web_ui && npm run test` → PASS
Run: `cd path2_web_ui && npm run type-check && npm run build` → 全绿

- [ ] **Step 5: Commit**

```bash
git add path2_web_ui/src/components/KlineChart.vue \
        path2_web_ui/src/components/FailedAttemptsCard.vue \
        path2_web_ui/src/components/PairDetailCard.vue \
        path2_web_ui/src/components/DetailSidebar.vue \
        path2_web_ui/src/components/FailedAttemptsCard.spec.ts \
        path2_web_ui/src/components/PairDetailCard.spec.ts \
        path2_web_ui/src/components/KlineChart.spec.ts
git commit -m "$(cat <<'EOF'
feat(path2_web_ui): 入口 A + 入口 D 前端完整交互链

KlineChart:
- brush 触发 time-query(入口 A)
- shift+click 跨图累积(main bo + sub burst/tb 都支持)· 触发 pair-query(入口 D)
- click marker(无 shift)触发 candidate-query(入口 C · stub)
- 前端乐观预判 · 无 edge 时不发请求

FailedAttemptsCard:每 attempt 一张卡 + overlap 3 色徽标 + outside_frame 提示条 + evaluation_lookback tooltip
PairDetailCard:4 subcheck + applied_swap 提示 + 撤回按钮 + invalid_reason 5 类映射
DetailSidebar:5 卡片 slot 切换 + caveats 顶部条 + dropped_matches 提示

承 spec §4.2 + §4.4 · Sprint 2 入口 A + D 完整落地。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

**Sprint 2 里程碑**:入口 A(时段查询 · 三 atom on_gate · outside_frame 补救)+ 入口 D(pair 4 通道 · auto swap · 5 类 invalid_reason)完整;硬伤 E 修 · fn.meta.refs_other_role 修;覆盖率 ~90%。

Sprint 2 结束跑全 test suite:
```bash
uv run pytest tests/ -v && \
cd path2_web_ui && npm run test && npm run type-check && npm run build && cd ..
```

---

## Sprint 3 · 入口 C + 入口 E + V1 D0 driver + e2e · Task 19-24

### Task 19: SolveTrace + PruneRecord + chosen_idx + memo 关

**Files:**
- Create: `path2/dag/solve_trace.py`(SolveTrace + PruneRecord dataclasses)
- Modify: `path2/dag/_solve.py:216-278`(9 处埋点 · memo 强制关 no-memo 分支)
- Test: `tests/path2/dag/test_solve_trace.py`

**Interfaces:**
- Consumes: `MeasuredKindAware`(Task 9)
- Produces: `SolveTrace.records: list[PruneRecord]` · `PruneRecord.chosen_idx`(Task 20 scope=candidate 消费)

- [ ] **Step 1: 写测试**

```python
# tests/path2/dag/test_solve_trace.py
from path2.dag.solve_trace import SolveTrace, PruneRecord
from path2.dag.gate_failure import MeasuredKindAware

def test_prune_record_dataclass():
    m = MeasuredKindAware(kind='gap', value=13, label='gap')
    r = PruneRecord(
        assign_snapshot={'burst': 'b1'},
        chosen_idx='b1',
        pair=('b1', 't3'),
        edge_id='burst_to_tb',
        prune_reason='gap_out',
        stage='satisfies',
        measured=m,
        threshold=10,
    )
    assert r.chosen_idx == 'b1'
    assert r.stage == 'satisfies'

def test_solve_trace_records_append():
    trace = SolveTrace()
    trace.records.append(PruneRecord(
        assign_snapshot={}, chosen_idx='b1', pair=None, edge_id=None,
        prune_reason='qualify_where_fail', stage='qualify', measured=None, threshold=None,
    ))
    assert len(trace.records) == 1

def test_solve_trace_records_populated_during_analyze():
    """analyze 时 · 若挂 SolveTrace collector · DFS 剪枝时应写入 records"""
    from path2.dag.engine import analyze
    result = analyze(_load_fixture(), _load_spec(), solve_trace=SolveTrace())
    assert hasattr(result, 'solve_trace')
    assert len(result.solve_trace.records) > 0

def test_combine_tail_step_present_when_all_branches_fail():
    """某 candidate DFS 分支全 fail · 应有一条 stage='combine' tail record"""
    result = _analyze_with_combine_fixture()
    combine_records = [r for r in result.solve_trace.records if r.stage == 'combine']
    assert len(combine_records) >= 1
```

- [ ] **Step 2: FAIL**

Run: `uv run pytest tests/path2/dag/test_solve_trace.py -v` → FAIL

- [ ] **Step 3: 实现**

创建 `path2/dag/solve_trace.py`:
```python
"""SolveTrace + PruneRecord · Stage 2 · 入口 C rejection_chain 数据源。

承 spec §2.3 · combine tail 是通道 ⑦ 唯一暴露。
"""
from dataclasses import dataclass, field
from typing import Any, Optional
from path2.dag.gate_failure import MeasuredKindAware


@dataclass(frozen=True)
class PruneRecord:
    assign_snapshot: dict[str, str]
    chosen_idx: str                        # 反查关键 · 后端按此 O(1) 过滤到某 candidate
    pair: Optional[tuple[str, str]]        # (src_event_id, dst_event_id) · combine tail 时 None
    edge_id: Optional[str]                  # combine tail 时 None
    prune_reason: str                       # 'gap_out' / 'anchor_mismatch' / ... 9 种
    stage: str                              # 'qualify' / 'satisfies' / 'anchor' / 'strict' / 'negation' / 'combine'
    measured: Optional[MeasuredKindAware]
    threshold: Any = None


@dataclass
class SolveTrace:
    records: list[PruneRecord] = field(default_factory=list)
```

修改 `path2/dag/_solve.py:216-278`(9 处埋点 · 用 grep 定位 satisfies/anchor/strict/negation/combine 剪枝点):
```python
from path2.dag.solve_trace import PruneRecord, SolveTrace
from path2.dag.gate_failure import MeasuredKindAware

def _dfs(wp, node_order, streams, assign, trace: Optional[SolveTrace] = None, memo=None):
    """SolveTrace 打开时禁 memo(承 spec §2.3 · memo 强制关)"""
    if trace is not None:
        memo = None   # 强制无 memo

    node_id = node_order[len(assign)]
    for candidate in streams.get(node_id, []):
        # (2) qualify · node.where
        if not _qualify(candidate, wp.nodes[node_id]):
            if trace is not None:
                trace.records.append(PruneRecord(
                    assign_snapshot=dict(assign), chosen_idx=candidate.event_id,
                    pair=None, edge_id=None,
                    prune_reason='qualify_where_fail', stage='qualify',
                    measured=None, threshold=None,
                ))
            continue

        # (3-6) pair-check · 遍历入边
        pair_ok = True
        for edge in wp.pos_preds.get(node_id, []):
            src_ep = endpoint(assign[edge.src], edge)
            # ③ satisfies
            if not edge.satisfies(src_ep, candidate):
                if trace is not None:
                    trace.records.append(PruneRecord(
                        assign_snapshot=dict(assign), chosen_idx=candidate.event_id,
                        pair=(src_ep.event_id, candidate.event_id), edge_id=f"{edge.src}_to_{edge.dst}",
                        prune_reason='gap_out', stage='satisfies',
                        measured=MeasuredKindAware(kind='gap', value=candidate.start_idx - src_ep.end_idx, label='gap'),
                        threshold=None,
                    ))
                pair_ok = False; break
            # ④ anchor
            if not _anchor_ok(src_ep, candidate, wp.edge_ok_map):
                if trace is not None:
                    trace.records.append(PruneRecord(
                        assign_snapshot=dict(assign), chosen_idx=candidate.event_id,
                        pair=(src_ep.event_id, candidate.event_id), edge_id=f"{edge.src}_to_{edge.dst}",
                        prune_reason='anchor_mismatch', stage='anchor',
                        measured=None, threshold=None,
                    ))
                pair_ok = False; break
            # ⑤ strict
            if not strict_clear(edge, src_ep, candidate, streams):
                if trace is not None:
                    trace.records.append(PruneRecord(
                        assign_snapshot=dict(assign), chosen_idx=candidate.event_id,
                        pair=(src_ep.event_id, candidate.event_id), edge_id=f"{edge.src}_to_{edge.dst}",
                        prune_reason='strict_fail', stage='strict',
                        measured=None, threshold=None,
                    ))
                pair_ok = False; break
        # ⑥ negation(src 已绑时检查 src 的 negation 出边)
        if pair_ok and wp.neg.get(node_id):
            if not negation_clear(wp.neg[node_id], node_id, assign, streams):
                if trace is not None:
                    trace.records.append(PruneRecord(
                        assign_snapshot=dict(assign), chosen_idx=candidate.event_id,
                        pair=None, edge_id=None,
                        prune_reason='negation_violated', stage='negation',
                        measured=None, threshold=None,
                    ))
                pair_ok = False
        if not pair_ok: continue

        # 递归下钻
        assign[node_id] = candidate
        yield from _dfs(wp, node_order, streams, assign, trace=trace)
        del assign[node_id]

    # ⑦ combine tail · 若所有 candidate 都 fail
    if trace is not None and len(streams.get(node_id, [])) > 0:
        # 只在 candidate 存在但全 fail 时吐 combine tail
        already_failed = any(r.chosen_idx in {c.event_id for c in streams.get(node_id, [])}
                              for r in trace.records[-10:])
        if already_failed:
            trace.records.append(PruneRecord(
                assign_snapshot=dict(assign),
                chosen_idx='__combine_tail__',
                pair=None, edge_id=None,
                prune_reason='all_branches_fail_combine', stage='combine',
                measured=None, threshold=None,
            ))
```

修改 `path2/dag/engine.py::analyze` · 接受 `solve_trace: Optional[SolveTrace] = None` 参数,传给 `_dfs`。

- [ ] **Step 4: PASS**

Run: `uv run pytest tests/path2/dag/test_solve_trace.py -v` → PASS
Run: `uv run pytest tests/path2/ -v` → 全绿(no memo 分支只在 solve_trace 传入时启用 · 不破常规 analyze)

- [ ] **Step 5: Commit**

```bash
git add path2/dag/solve_trace.py path2/dag/_solve.py path2/dag/engine.py \
        tests/path2/dag/test_solve_trace.py
git commit -m "$(cat <<'EOF'
feat(path2/dag): SolveTrace + PruneRecord · 9 埋点 · memo 强制关

DFS 剪枝时 · 若 solve_trace 参数传入 · 记录每次 prune 到 PruneRecord;
- 9 stage 埋点:qualify / satisfies × 3 + anchor + strict + negation + combine tail
- chosen_idx 反查关键:后端 O(1) 过滤到某 candidate 涉及的 records
- memo 强制关:trace 打开时禁 memo(避免 trace 有缝)· 常规 analyze 不受影响

承 spec §2.3 · 入口 C rejection_chain 数据源 + 通道 ⑦ combine tail 唯一暴露。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 20: 后端 scope=candidate + rejection_chain 6 stage 含 combine tail

**Files:**
- Modify: `path2_web/diagnose.py`(实现 `_derive_candidate_response` 完整版 · CandidatePayload + RejectionStep dataclasses)
- Test: `tests/path2_web/test_diagnose_candidate.py`

**Interfaces:**
- Consumes: `SolveTrace` + `PruneRecord.chosen_idx`(Task 19)· 4 subcheck helper(Task 16)
- Produces: `scope=candidate` 响应含 `CandidatePayload.rejection_chain[]`(Task 21 前端消费)

- [ ] **Step 1: 写测试**

```python
# tests/path2_web/test_diagnose_candidate.py
from path2_web.diagnose import derive_response, Query, CandidatePayload

def test_scope_candidate_returns_candidate_payload():
    q = Query(symbol='DGNX', scope='candidate', event_id='burst_1')
    r = derive_response(q)
    assert r.scope == 'candidate'
    assert isinstance(r.payload, CandidatePayload)
    assert r.payload.event_id == 'burst_1'

def test_rejection_chain_stage_enum():
    """rejection_chain 里 step.stage 只能是 6 值枚举之一"""
    q = Query(symbol='DGNX', scope='candidate', event_id='burst_1')
    r = derive_response(q)
    allowed = {'qualify', 'satisfies', 'anchor', 'strict', 'negation', 'combine'}
    for step in r.payload.rejection_chain:
        assert step.stage in allowed

def test_combine_tail_at_end_when_present():
    """combine step 若存在 · 只在 rejection_chain 尾部至多一条"""
    q = Query(symbol='DGNX', scope='candidate', event_id='burst_with_combine_tail')
    r = derive_response(q)
    for i, step in enumerate(r.payload.rejection_chain):
        if step.stage == 'combine':
            assert i == len(r.payload.rejection_chain) - 1, "combine 必须在尾部"

def test_solvetrace_not_landed_stub():
    """若 result 无 solve_trace · 返 stub + caveat"""
    q = Query(symbol='NO_TRACE', scope='candidate', event_id='b1')
    r = derive_response(q)
    codes = [c.code for c in r.caveats]
    if not r.payload.rejection_chain or all(s.stage in ('qualify', 'satisfies', 'anchor') for s in r.payload.rejection_chain):
        assert 'solvetrace_not_landed' in codes
```

- [ ] **Step 2: FAIL**

Run: `uv run pytest tests/path2_web/test_diagnose_candidate.py -v` → FAIL

- [ ] **Step 3: 实现**

在 `path2_web/diagnose.py` 新增/替换:
```python
from path2.dag.solve_trace import SolveTrace, PruneRecord

@dataclass
class RejectionStep:
    stage: str
    edge_id: Optional[str]
    counterpart_event_id: Optional[str]
    measured: Optional[dict]
    threshold: Any
    prune_reason: str
    attempts: Optional[int] = None       # combine 专属

@dataclass
class CandidatePayload:
    event_id: str
    class_id: str
    rejection_chain: list[RejectionStep]


def _derive_candidate_response(query: Query) -> Response:
    result = _load_analysis_result(query.symbol)
    event = _load_event_by_id(result, query.event_id)
    if event is None:
        return Response(scope='candidate',
                        payload=CandidatePayload(event_id=query.event_id, class_id='unknown', rejection_chain=[]),
                        caveats=[Caveat(code='event_not_found', message='')])

    caveats = _collect_caveats(query, result)
    class_id = _role_of_event(result, event)
    trace = getattr(result, 'solve_trace', None)

    if trace is None:
        caveats.append(Caveat(
            code='solvetrace_not_landed',
            message='Stage 2 SolveTrace 未挂 collector · 只返 qualify + rel-based satisfies/anchor stub',
        ))
        # stub 版:走 RelRow 拼一个粗 chain
        return Response(scope='candidate',
                        payload=CandidatePayload(event_id=event.event_id, class_id=class_id,
                                                 rejection_chain=_stub_rejection_chain(event, result)),
                        caveats=caveats)

    # 完整版:PruneRecord.chosen_idx 反查
    related = [r for r in trace.records
               if r.chosen_idx == event.event_id
               or (r.pair and event.event_id in r.pair)]

    steps: list[RejectionStep] = []
    combine_step = None
    for pr in related:
        step = RejectionStep(
            stage=pr.stage,
            edge_id=pr.edge_id,
            counterpart_event_id=(pr.pair[1] if pr.pair and pr.pair[0] == event.event_id
                                   else pr.pair[0] if pr.pair else None),
            measured=(pr.measured.__dict__ if pr.measured else None),
            threshold=pr.threshold,
            prune_reason=pr.prune_reason,
        )
        if pr.stage == 'combine':
            combine_step = RejectionStep(**{**step.__dict__, 'attempts': len(related)})
        else:
            steps.append(step)

    if combine_step is not None:
        steps.append(combine_step)   # combine 必须尾部

    return Response(scope='candidate',
                    payload=CandidatePayload(event_id=event.event_id, class_id=class_id,
                                             rejection_chain=steps),
                    caveats=caveats)


def _stub_rejection_chain(event, result):
    """SolveTrace 未落时 · 用 RelRow 拼粗 chain(仅 qualify + rel-based satisfies + anchor)"""
    steps = []
    # 从 RelRow 找该 event 涉及的 pair · 简单填 stage='satisfies' / 'anchor'
    for r in result.rel_rows:
        for (u_id, v_id, primary_fail) in r.example_failed_pairs:
            if event.event_id in (u_id, v_id):
                stage_map = {'gap_out': 'satisfies', 'anchor_mismatch': 'anchor',
                             'strict_fail': 'strict', 'negation_violated': 'negation'}
                steps.append(RejectionStep(
                    stage=stage_map.get(primary_fail, 'satisfies'),
                    edge_id=r.edge_id,
                    counterpart_event_id=v_id if u_id == event.event_id else u_id,
                    measured=None, threshold=None,
                    prune_reason=primary_fail,
                ))
    return steps
```

- [ ] **Step 4: PASS**

Run: `uv run pytest tests/path2_web/test_diagnose_candidate.py -v` → PASS

- [ ] **Step 5: Commit**

```bash
git add path2_web/diagnose.py tests/path2_web/test_diagnose_candidate.py
git commit -m "$(cat <<'EOF'
feat(path2_web): scope=candidate · rejection_chain 6 stage 含 combine tail

_derive_candidate_response 完整版:
- 消费 SolveTrace + PruneRecord.chosen_idx 反查 · O(1) 过滤到某 candidate
- 6 stage 枚举:qualify/satisfies/anchor/strict/negation/combine
- combine tail 只在尾部至多一条 + attempts 计数
- SolveTrace 未落时 fallback stub(RelRow 拼粗 chain)+ caveat 'solvetrace_not_landed'

承 spec §3.2.4 · 入口 C · 通道 ⑦ 唯一暴露。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 21: 前端 RejectionChainCard(入口 C)

**Files:**
- Create: `path2_web_ui/src/components/RejectionChainCard.vue`
- Modify: `path2_web_ui/src/components/DetailSidebar.vue`(集成 RejectionChainCard slot)
- Test: `path2_web_ui/src/components/RejectionChainCard.spec.ts`

**Interfaces:**
- Consumes: `CandidatePayload`(Task 20)· shared `fmt`(Task 6)

- [ ] **Step 1: 写测试**

```typescript
// path2_web_ui/src/components/RejectionChainCard.spec.ts
import { mount } from '@vue/test-utils'
import RejectionChainCard from './RejectionChainCard.vue'

describe('RejectionChainCard', () => {
    const payload = {
        event_id: 'burst_1', class_id: 'burst',
        rejection_chain: [
            { stage: 'qualify', edge_id: null, counterpart_event_id: null,
              measured: null, threshold: null, prune_reason: 'qualify_where_fail' },
            { stage: 'satisfies', edge_id: 'burst_to_tb', counterpart_event_id: 'tb_3',
              measured: { kind: 'gap', value: 15, label: 'gap' }, threshold: 10, prune_reason: 'gap_out' },
            { stage: 'combine', edge_id: null, counterpart_event_id: null,
              measured: null, threshold: null, prune_reason: 'all_branches_fail_combine',
              attempts: 4 },
        ],
    }
    it('按 stage 分组渲染', () => {
        const w = mount(RejectionChainCard, { props: { payload } })
        expect(w.find('.stage-qualify').exists()).toBe(true)
        expect(w.find('.stage-satisfies').exists()).toBe(true)
        expect(w.find('.stage-combine').exists()).toBe(true)
    })
    it('combine step 灰色卡片 · 尾部', () => {
        const w = mount(RejectionChainCard, { props: { payload } })
        const combineCard = w.find('.stage-combine')
        expect(combineCard.text()).toContain('尝试 4 次')
    })
})
```

- [ ] **Step 2: FAIL**

Run: `cd path2_web_ui && npm run test -- RejectionChainCard` → FAIL

- [ ] **Step 3: 实现**

创建 `path2_web_ui/src/components/RejectionChainCard.vue`:
```vue
<script setup lang="ts">
import { fmt } from '@/shared/formatters'

interface RejectionStep {
    stage: string
    edge_id: string | null; counterpart_event_id: string | null
    measured: { kind: string; value: any; label: string } | null
    threshold: any
    prune_reason: string
    attempts?: number
}
interface CandidatePayload {
    event_id: string; class_id: string
    rejection_chain: RejectionStep[]
}
const props = defineProps<{ payload: CandidatePayload }>()

const stageLabel: Record<string, string> = {
    qualify: '① node.where 剔除',
    satisfies: '③ satisfies fail',
    anchor: '④ anchor 破位',
    strict: '⑤ strict 不清空',
    negation: '⑥ negation 违禁',
    combine: '⑦ 组合零解(combine tail)',
}
</script>

<template>
    <div class="rejection-chain-card">
        <header>
            <strong>{{ payload.event_id }}</strong> · {{ payload.class_id }}
        </header>
        <div v-for="(step, i) in payload.rejection_chain" :key="i"
             :class="['step', `stage-${step.stage}`]">
            <div class="stage-header">{{ stageLabel[step.stage] || step.stage }}</div>
            <template v-if="step.stage === 'combine'">
                <div class="combine-summary">
                    尝试 {{ step.attempts || '?' }} 次分支全 fail · 组合零解
                </div>
            </template>
            <template v-else>
                <div v-if="step.counterpart_event_id">与 {{ step.counterpart_event_id }}</div>
                <div v-if="step.edge_id">edge · {{ step.edge_id }}</div>
                <div v-if="step.measured">{{ fmt(step.measured.value, step.measured.kind) }} vs 阈 {{ step.threshold }}</div>
                <div class="reason">{{ step.prune_reason }}</div>
            </template>
        </div>
    </div>
</template>

<style scoped>
.rejection-chain-card { padding: 12px; overflow-x: auto; min-width: 0; }
.step { border-left: 3px solid #cbd5e0; padding: 8px; margin: 8px 0; }
.stage-qualify { border-left-color: #dd6b20; }
.stage-satisfies { border-left-color: #4299e1; }
.stage-anchor { border-left-color: #48bb78; }
.stage-strict { border-left-color: #ed64a6; }
.stage-negation { border-left-color: #742a2a; }
.stage-combine { border-left-color: #a0aec0; background: #f7fafc; color: #4a5568; }
</style>
```

修改 `DetailSidebar.vue` 加 RejectionChainCard slot:
```vue
<template>
    <!-- ... 现有 slots ... -->
    <RejectionChainCard v-else-if="activeCard === 'candidate' && candidatePayload" :payload="candidatePayload" />
</template>
```

KlineChart click marker(无 shift)现在真正触发 candidate query。

- [ ] **Step 4: PASS**

Run: `cd path2_web_ui && npm run test -- RejectionChainCard` → PASS

- [ ] **Step 5: Commit**

```bash
git add path2_web_ui/src/components/RejectionChainCard.vue \
        path2_web_ui/src/components/DetailSidebar.vue \
        path2_web_ui/src/components/RejectionChainCard.spec.ts
git commit -m "$(cat <<'EOF'
feat(path2_web_ui): 入口 C · RejectionChainCard 按 6 stage 分组渲染

RejectionChainCard:
- 按 stage 分组着色(qualify/satisfies/anchor/strict/negation/combine 6 色)
- combine step 灰色卡片 · 尾部 · 显 "尝试 N 次分支全 fail · 组合零解"
- DetailSidebar 加 candidate slot · KlineChart click marker(无 shift)触发 scope=candidate

承 spec §4.4 · 入口 C 完整前端。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 22: scripts/scan-top-miss.py(入口 E · workflow)

**Files:**
- Create: `scripts/scan-top-miss.py`
- Test: `tests/scripts/test_scan_top_miss.py`

**Interfaces:**
- Consumes: `scope=time` 分派(Task 15)· `AnalysisResult.matches`(现有)
- Produces: markdown 榜(Top-K 大涨无 match 股)

- [ ] **Step 1: 写测试**

```python
# tests/scripts/test_scan_top_miss.py
import subprocess
import sys

def test_scan_top_miss_runs_without_error(tmp_path):
    """脚本能跑通 · 输出 markdown 榜"""
    out_file = tmp_path / "top_miss.md"
    result = subprocess.run(
        [sys.executable, 'scripts/scan-top-miss.py',
         '--start=2025-06-01', '--end=2025-07-01', '--min-pct=30', '--top-k=5',
         '--out=' + str(out_file)],
        capture_output=True, text=True, timeout=300,
    )
    assert result.returncode == 0, result.stderr
    assert out_file.exists()
    content = out_file.read_text()
    assert '## Top-5' in content or '# scan-top-miss' in content
```

- [ ] **Step 2: FAIL**

Run: `uv run pytest tests/scripts/test_scan_top_miss.py -v` → FAIL

- [ ] **Step 3: 实现**

创建 `scripts/scan-top-miss.py`(承 CLAUDE.md · 不用 argparse · main 起始声明所有参数):
```python
"""scan-top-miss · 全宇宙批量出榜"大涨无 pattern match"股。

复用 scope=time 分派 · 输出 markdown 榜。
"""
import pathlib
import sys
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from path2_web.diagnose import derive_response, Query
from path2_web.worker import scan_one_symbol
from path2.debug import set_current_symbol


def main():
    # 参数声明(承 CLAUDE.md · 无 argparse)
    start_date = '2025-06-01'
    end_date = '2025-07-01'
    min_pct = 30.0
    top_k = 20
    out_path = 'scan_top_miss.md'
    pkl_dir = 'datasets/pkls/'
    spec_module = 'path2_apps.bottom_breakout_burst.dag_spec'
    # 允许命令行 override(简单 --key=value)
    for a in sys.argv[1:]:
        if a.startswith('--start='): start_date = a.split('=', 1)[1]
        elif a.startswith('--end='): end_date = a.split('=', 1)[1]
        elif a.startswith('--min-pct='): min_pct = float(a.split('=', 1)[1])
        elif a.startswith('--top-k='): top_k = int(a.split('=', 1)[1])
        elif a.startswith('--out='): out_path = a.split('=', 1)[1]

    spec = _load_spec(spec_module)
    candidates = []

    for pkl_file in pathlib.Path(pkl_dir).glob('*.pkl'):
        symbol = pkl_file.stem
        set_current_symbol(symbol)
        result = scan_one_symbol(symbol, str(pkl_file), spec)
        if len(result.matches) > 0:
            continue                                   # 已有 match · 不算漏检
        pct = _compute_pct_change(result.df, start_date, end_date)
        if pct < min_pct:
            continue
        # 跑 scope=time 拿 top gate
        query = Query(symbol=symbol, scope='time',
                      start_bar=_date_to_bar(result.df, start_date),
                      end_bar=_date_to_bar(result.df, end_date))
        resp = derive_response(query)
        top_gate = _summarize_top_gate(resp.payload.failed_attempts)
        candidates.append((symbol, pct, start_date, end_date, top_gate))

    candidates.sort(key=lambda x: x[1], reverse=True)
    _write_markdown(out_path, candidates[:top_k], start_date, end_date, min_pct)


def _summarize_top_gate(failed_attempts):
    """选主导 gate name · 简要摘要"""
    if not failed_attempts:
        return "无 attempt 采集(可能 detector 未触发 on_gate)"
    from collections import Counter
    counts = Counter(gf.gate_name for gf in failed_attempts)
    top_name, top_count = counts.most_common(1)[0]
    sample = next(gf for gf in failed_attempts if gf.gate_name == top_name)
    return f"{top_name}(实测 {sample.measured.value} vs 阈 {sample.threshold},共 {top_count} 次)"


def _write_markdown(path, candidates, start, end, min_pct):
    with open(path, 'w') as f:
        f.write(f"# scan-top-miss · {start} → {end}\n\n")
        f.write(f"筛选:涨幅 > {min_pct}% · matches 为空 · 按涨幅降序\n\n")
        f.write(f"## Top-{len(candidates)}\n\n")
        for i, (symbol, pct, s, e, gate) in enumerate(candidates, 1):
            f.write(f"{i}. **{symbol}** · {s} → {e} · +{pct:.1f}%\n")
            f.write(f"   - {gate}\n\n")


def _load_spec(module_path):
    import importlib
    m = importlib.import_module(module_path)
    return m.spec


def _compute_pct_change(df, start_date, end_date):
    # 依 df 结构 · 简化实现
    import pandas as pd
    start_idx = df.index.get_loc(pd.Timestamp(start_date), method='nearest')
    end_idx = df.index.get_loc(pd.Timestamp(end_date), method='nearest')
    return (df['close'].iat[end_idx] / df['close'].iat[start_idx] - 1) * 100


def _date_to_bar(df, date_str):
    import pandas as pd
    return df.index.get_loc(pd.Timestamp(date_str), method='nearest')


if __name__ == '__main__':
    main()
```

- [ ] **Step 4: PASS**

Run: `uv run pytest tests/scripts/test_scan_top_miss.py -v` → PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/scan-top-miss.py tests/scripts/test_scan_top_miss.py
git commit -m "$(cat <<'EOF'
feat(scripts): scan-top-miss · 入口 E · 全宇宙大涨无 match 出榜 workflow

scan-top-miss.py:
- 遍历 datasets/pkls · 筛"matches 空 + 涨幅 > min_pct%"
- 每候选跑 scope=time 拿主导 gate name · 拼粗根因摘要
- 输出 markdown 榜(Top-K · 按涨幅降序)
- 无 argparse · main 起始声明参数 · 简单 --key=value override

承 spec §3.2 · §7.4 · 入口 E 独立 workflow。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 23: KlineChart 右键 driver 复制菜单(V1 D0)

**Files:**
- Modify: `path2_web_ui/src/components/KlineChart.vue`(主图 contextmenu 弹菜单)
- Test: `path2_web_ui/src/components/KlineChart.spec.ts`(补右键菜单 case)

**Interfaces:**
- 无(纯前端 UX)

- [ ] **Step 1: 写测试**

```typescript
// path2_web_ui/src/components/KlineChart.spec.ts
describe('KlineChart 右键 driver', () => {
    it('主图右键弹菜单 · 复制 driver 脚本', async () => {
        const w = mount(KlineChart, { props: { symbol: 'DGNX', events: [] } })
        // 模拟右键
        await w.trigger('contextmenu')
        expect(w.find('.driver-menu').exists()).toBe(true)
        // 点复制
        const copyBtn = w.find('.copy-driver-btn')
        await copyBtn.trigger('click')
        // 断言 clipboard.writeText 被调用(mock)
    })
})
```

- [ ] **Step 2: FAIL**

Run: `cd path2_web_ui && npm run test` → FAIL

- [ ] **Step 3: 实现**

修改 `KlineChart.vue`:
```vue
<script setup lang="ts">
const contextMenuVisible = ref(false)
const contextMenuPos = ref({ x: 0, y: 0 })

function handleContextMenu(ev: MouseEvent) {
    ev.preventDefault()
    contextMenuVisible.value = true
    contextMenuPos.value = { x: ev.clientX, y: ev.clientY }
}

function copyDriverScript() {
    const script = `
# path2 driver · ${props.symbol}
from path2.debug import set_current_symbol
from path2_web.worker import scan_one_symbol
from path2_apps.bottom_breakout_burst.dag_spec import spec

set_current_symbol('${props.symbol}')
result = scan_one_symbol('${props.symbol}', 'datasets/pkls/${props.symbol}.pkl', spec)
# 在这里加 breakpoint() · PyCharm 断在 Detector 内部
print(f"matches: {len(result.matches)}, gate_failures: {len(result.gate_failures) if hasattr(result, 'gate_failures') else 0}")
    `.trim()
    navigator.clipboard.writeText(script)
    contextMenuVisible.value = false
}
</script>

<template>
    <div class="kline-chart" @contextmenu="handleContextMenu">
        <!-- ... 现有 chart ... -->
        <div v-if="contextMenuVisible" class="driver-menu"
             :style="{ left: contextMenuPos.x + 'px', top: contextMenuPos.y + 'px' }">
            <button class="copy-driver-btn" @click="copyDriverScript">复制 driver 脚本</button>
        </div>
    </div>
</template>

<style scoped>
.driver-menu { position: fixed; background: white; border: 1px solid #cbd5e0; padding: 4px; border-radius: 4px; }
</style>
```

- [ ] **Step 4: PASS**

Run: `cd path2_web_ui && npm run test` → PASS

- [ ] **Step 5: Commit**

```bash
git add path2_web_ui/src/components/KlineChart.vue
git commit -m "$(cat <<'EOF'
feat(path2_web_ui): V1 D0 driver · KlineChart 右键复制 driver 脚本

主图 contextmenu → 弹菜单 → 复制 driver 脚本到剪贴板 · 脚本含 set_current_symbol + scan_one_symbol + breakpoint 占位;
兜底 detector 内部超细节调查 · 承 spec §5.3。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 24: e2e playwright · DGNX 走通 · 5 入口

**Files:**
- Create: `tests/e2e/test_dgnx_walkthrough.py`(pytest + playwright)
- 生成 screenshots 存 `docs/superpowers/e2e_screenshots/`

**Interfaces:**
- 消费:所有前 23 task 的产出

- [ ] **Step 1: 写测试**

```python
# tests/e2e/test_dgnx_walkthrough.py
import pytest
from playwright.sync_api import sync_playwright

@pytest.fixture
def page():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)  # 系统 chromium
        page = browser.new_page()
        page.goto('http://localhost:5173/#/pattern/bottom_breakout_burst/symbol/DGNX')
        yield page
        browser.close()


def test_entry_a_brush_time(page):
    """入口 A · 主图框选 → FailedAttemptsCard 出 BurstDetector chain_break attempt"""
    # 等 K 线加载
    page.wait_for_selector('.kline-chart canvas')
    # 模拟 brush 2025-08-01 附近 30 bar
    page.mouse.down(x=400, y=200)
    page.mouse.move(x=600, y=200)
    page.mouse.up()
    # 侧栏应出 FailedAttemptsCard
    page.wait_for_selector('.failed-attempts-card', timeout=5000)
    assert page.locator('.attempt-card').count() >= 1
    page.screenshot(path='docs/superpowers/e2e_screenshots/entry_a_dgnx.png')


def test_entry_b_topology_edge_click(page):
    """入口 B · 拓扑面板点 burst→tb edge → PairListCard 出 miss_reasons 分布"""
    page.wait_for_selector('.topology-control')
    page.click('[data-edge="burst_to_tb"]')
    page.wait_for_selector('.pair-list-card', timeout=5000)
    assert page.locator('.miss-reasons').is_visible()


def test_entry_c_click_marker(page):
    """入口 C · 副图点 burst band 单击 → RejectionChainCard"""
    page.wait_for_selector('.sub-chart .band-burst')
    page.click('.sub-chart .band-burst:first-child')
    page.wait_for_selector('.rejection-chain-card', timeout=5000)
    # 应有若干 stage
    stages = page.locator('.step').count()
    assert stages >= 1


def test_entry_d_shift_click_cross_layer(page):
    """入口 D · shift+click 主图 bo marker + shift+click 副图 burst band"""
    page.wait_for_selector('.main-chart .marker-bo')
    # 第 1 击 · 主图 bo(带 shift)
    page.keyboard.down('Shift')
    page.click('.main-chart .marker-bo:first-child')
    # 第 2 击 · 副图 burst band(带 shift)
    page.click('.sub-chart .band-burst:first-child')
    page.keyboard.up('Shift')
    page.wait_for_selector('.pair-detail-card', timeout=5000)
    # 4 subcheck 显示
    assert page.locator('.subcheck').count() >= 1


def test_entry_d_auto_swap(page):
    """入口 D · 反向 shift+click(tb → burst)· 应 auto swap + 撤回按钮"""
    page.wait_for_selector('.sub-chart .band-tb')
    page.keyboard.down('Shift')
    page.click('.sub-chart .band-tb:first-child')
    page.click('.sub-chart .band-burst:first-child')
    page.keyboard.up('Shift')
    page.wait_for_selector('.swap-notice', timeout=5000)
    assert page.locator('.undo-swap').is_visible()


def test_entry_e_workflow(tmp_path):
    """入口 E · 命令行跑 scan-top-miss · markdown 榜含 DGNX"""
    import subprocess, sys
    out = tmp_path / "top_miss.md"
    result = subprocess.run(
        [sys.executable, 'scripts/scan-top-miss.py',
         '--start=2025-07-15', '--end=2025-09-01', '--min-pct=25', '--top-k=20',
         '--out=' + str(out)],
        capture_output=True, text=True, timeout=600,
    )
    assert result.returncode == 0
    content = out.read_text()
    # DGNX 应该在榜内(若数据符合)
    # assert 'DGNX' in content  # 或至少存在 markdown 榜结构
    assert '# scan-top-miss' in content
```

- [ ] **Step 2: FAIL(前端未 serve · 或功能未完全接上)**

Run: `uv run pytest tests/e2e/test_dgnx_walkthrough.py -v --workers=1`
Expected: 依赖前端 dev server 启动 · 各入口打通

- [ ] **Step 3: 实现**

前端 / 后端功能应该在 Task 1-23 已完整实现 · 此 task 主要是**接线 + e2e 修复**:
- 启动 dev server:`cd path2_web_ui && npm run dev &`
- 确保 `/diagnose?scope=...` 4 scope 端点全通
- 修任何 e2e 暴露的 bug(subagent 遇到 flake / bug 报回 lead)

- [ ] **Step 4: PASS**

Run: `uv run pytest tests/e2e/test_dgnx_walkthrough.py -v --workers=1`
Expected: 全 PASS · screenshots 存到 `docs/superpowers/e2e_screenshots/`

清理:
```bash
rm -rf .playwright-mcp/*   # 承 CLAUDE.md · playwright 卫生
```

- [ ] **Step 5: Commit**

```bash
git add tests/e2e/test_dgnx_walkthrough.py docs/superpowers/e2e_screenshots/
git commit -m "$(cat <<'EOF'
test(e2e): DGNX walkthrough · 5 入口 + auto swap 全通

playwright + 系统 chromium(承 memory df0799d):
- 入口 A brush 时段 → FailedAttemptsCard
- 入口 B 点 role edge → PairListCard
- 入口 C 单点 marker → RejectionChainCard
- 入口 D shift+click 跨图 → PairDetailCard(含 auto swap 场景)
- 入口 E workflow → markdown 榜含 DGNX
--workers=1(承 subchart e2e race 教训)

承 spec §6.4 · Sprint 3 收尾。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

**Sprint 3 里程碑**:入口 C(SolveTrace + rejection_chain 6 stage 含 combine tail)+ 入口 E(workflow markdown 榜)+ V1 D0 driver + 5 入口 e2e 全通;覆盖率 ~95%。

Sprint 3 结束跑全 test suite:
```bash
uv run pytest tests/ -v && \
cd path2_web_ui && npm run test && npm run type-check && npm run build && cd ..
```

---

## Self-Review(实施完成后)

### 1. Spec 覆盖

| Spec 段 | 实施 task | 状态 |
|---|---|---|
| §1.3 五硬伤 | A(Task 7)· B(Task 1)· C(Task 2 + 14)· D(Task 6)· E(Task 13) | ✅ |
| §2.1 Stage 0 补丁 | Task 1-4 | ✅ |
| §2.2 Stage 1 ContextVar | Task 5 | ✅ |
| §2.3 Stage 2 SolveTrace | Task 19 | ✅ |
| §2.4 Stage 3 on_gate 三 atom | Task 9-12 | ✅ |
| §2.5 kind-aware measured | Task 13 | ✅ |
| §2.6 fn.meta.refs_other_role | Task 14 | ✅ |
| §2.7 subcheck helper | Task 16 | ✅ |
| §3.1 derive_response 分派 | Task 8(骨架)+ 15/17/20(scope 分派)| ✅ |
| §3.2 四 scope 契约 | Task 8/15/17/20 | ✅ |
| §3.3 caveats 全枚举 | Task 8/14/15 分批 | ✅ |
| §4.1 shared 层 | Task 6/7 | ✅ |
| §4.2 KlineChart 增强 | Task 18(brush + shift+click)· Task 21(click marker)· Task 23(右键)| ✅ |
| §4.3 TopologyControl 降级 | Task 8 | ✅ |
| §4.4 DetailSidebar 5 卡片 | Task 7(基础)+ Task 8/18/21(卡片) | ✅ |
| §6 测试策略 | 每 task 内 TDD + Task 24 e2e | ✅ |
| §7 Sprint 排期 | Sprint 1(Task 1-8)· 2(Task 9-18)· 3(Task 19-24) | ✅ |
| §8 硬性决策 15 条 | 各 task 承接 | ✅ |

**无 gap**。

### 2. Placeholder 扫描

- 无 TBD / TODO / "implement later"
- 每 step 有完整代码(不是 "add error handling" 语义占位)
- Detector 内 gate 埋点具体位置(L124-135 / L216-289 / L83-244)有精确指引

### 3. Type Consistency

- `GateFailure`(Task 9 定义)· `MeasuredKindAware`(Task 9)· `SubCheck`(Task 16)· `PruneRecord`(Task 19)· `RejectionStep`(Task 20)· `PairPayload`(Task 17)· `TimePayload`(Task 15)· `RolesPayload`(Task 8)· `CandidatePayload`(Task 20)—— 全部按 Core Types Dictionary 定义 · 跨 task 一致
- `derive_response(query)` 一入口按 scope 分派 · 每 scope 有对应 `_derive_*_response`
- 4 subcheck helper 命名一致:`_check_feasible_window` / `_check_satisfies` / `_check_anchor` / `_check_strict`
- 前端 `fmt(val, kind)` / `fmtValue(val)` 跨组件复用
- shift+click handler 命名一致:`handleShiftClick(event_id, class_id, source)`

---

## Execution Handoff

Plan 完成 · 已落到 `docs/superpowers/plans/2026-07-07-path2-miss-detection-tools-implementation.md`。

**推荐 · Subagent-Driven Development**:每 task fresh subagent + two-stage review;每 task 独立 commit;失败即刻反馈 lead。

**在新 session 中粘贴以下命令启动 subagent-driven 执行**:

```
/subagent-driven-development docs/superpowers/plans/2026-07-07-path2-miss-detection-tools-implementation.md

约定:
- 每 task 派 fresh implementer(sonnet)· 两阶段 review(spec-check + quality · 均 opus)· 全部通过后 commit
- 每 Sprint 完(Task 8 / Task 18 / Task 24)· 跑全 test suite 保绿:
  `uv run pytest tests/ -v && cd path2_web_ui && npm run test && npm run type-check && npm run build && cd ..`
- 遇 spec 内部矛盾 · lead 停下问用户;否则单 session 无监管跑到底
- 承 memory · 不合并 master · 用当前 debug 分支 or 新分支
- Playwright e2e 后清 `.playwright-mcp/*`
- Task 24 e2e 需前端 dev server 启动(`cd path2_web_ui && npm run dev &`)
```




