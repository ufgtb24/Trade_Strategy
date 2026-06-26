# path2 bo/pk K线主图渲染 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Implementer 角色一律 sonnet; Reviewer 角色一律 opus。

**Goal:** 引入 `NodeSpec.render_grid` (`'price' | 'time'`) 与 `BOEvent.referenced_points` 两条正交契约协议, 让 bo 主三角钉 K线主图 + pk 编号作为卫星 marker 画在各自 bar 位置, 不破"类型无关渲染器"红线 (前端新增分支 = O(1), 与 atom 数无关)。spec.py 加载入期校验拒绝 (span × render_grid='price')。

**Architecture:** 两条 schema-driven 协议 + 一条校验:
- **render_grid** = NodeSpec 字段, atom 作者声明该节点的事件主 marker 渲染在哪个 ECharts grid (默认 'time' 走 sub-grid; 'price' 钉 K线主图)。前端按 source_tag→TopoNode 反查 → if(render_grid==='price') 二分。
- **referenced_points** = BOEvent payload 字段 (Tuple[Tuple[bar_idx, price, label], ...]), 由 BODetector emit 时填; 前端按字段存在性渲染卫星 marker (dot + text label)。
- **(span × render_grid='price') 校验拒绝** = PatternSpec._validate_render_grid 反射 `n.detector.event_cls.is_point` (Event 基类默认 False, BOEvent 覆写 True), False 时 raise。

**Tech Stack:** Python 3.12 (path2 + path2_web) + Vue 3 + TypeScript + ECharts 5 + vitest + pytest。包管理 uv (Python) / npm (前端)。

## Global Constraints

- **不破"类型无关渲染器"红线**: 前端代码不得读 `e.class_id` 做 if/switch; 所有新分支必须 O(1) 且与 atom 数无关。
- **不升格 pk 为 event / 不出 pk stream / 不引入 PkDetector**。
- **不动 ECharts grid 数量** (保持 3-grid: 价格/量/markers); bo 上 K线只是 yAxisIndex 切到 0。
- **守序保守默认值**: `render_grid` 默认 `'time'`, `referenced_points` 默认 `()`, `is_point` 默认 `False` — 不声明的现役 atom 行为不变。
- **bo 的 `broken_peak_ids` 字段保留** (供 W.attr 读 + 现有测试不破), `referenced_points` 是新增加的几何承载, 两者并存。
- **测试命令**:
  - Python: `uv run pytest <path> -v`
  - 前端: `cd path2_web_ui && npx vitest run <file>`
  - 前端构建: `cd path2_web_ui && npm run build`
- **commit message** 简洁中文 + path 前缀, 例: `path2/dag: NodeSpec.render_grid 字段 + 载入期校验`。

---

## 文件结构概览

### 改动

| 文件 | 改动 | 责任 |
|---|---|---|
| `path2/core.py` | +1 类属性 `is_point: ClassVar[bool] = False` | Event 基类几何承诺 |
| `path2/atoms/breakout.py` | BOEvent 加 `is_point = True` + `referenced_points` 字段 + tuple 兜底; BODetector.emit 填 referenced_points | 点事件几何承诺 + 几何引用 payload |
| `path2/dag/nodes.py` | NodeSpec 加 `render_grid: Literal['price','time'] = 'time'` 字段 | 节点渲染轴声明 |
| `path2/dag/spec.py` | 加 `_validate_render_grid` 方法 + __post_init__ 调用 | 拒绝 span × price 组合 |
| `path2_apps/bottom_breakout_burst/dag_spec.py` | bo 节点 NodeSpec 加 `render_grid='price'` | bo 上 K线主图 |
| `path2_web/serialize.py` | `serialize_pattern` 节点 dict 加 `render_grid` 字段透传 | 前端可读 |
| `path2_web_ui/src/types.ts` | TopoNode 加 `render_grid?` + EventDict 加 `referenced_points?` | 类型镜像 |
| `path2_web_ui/src/render/visible.ts` | 加 `renderGridOf(e, topology, bandKeyOf)` 纯函数 | render_grid 反查 helper |
| `path2_web_ui/src/render/chart.ts` | filtered 按 renderGridOf 一分为二; 加 `price-points` 与 `satellites` 两条新 series | 价格 grid 主三角 + 卫星 marker |

### 测试

| 文件 | 新增测试 |
|---|---|
| `tests/path2/atoms/test_breakout_dataclasses.py` | BOEvent.is_point/referenced_points/tuple 兜底 |
| `tests/path2/atoms/test_breakout_detector.py` | BODetector.emit 填充 referenced_points 内容正确 |
| `tests/path2/dag/test_spec.py` | _validate_render_grid: point 通过 / span × price 抛错 / 默认 'time' 不校验 |
| `tests/path2_apps/bottom_breakout_burst/test_dag_spec.py` | bo 节点 render_grid=='price' |
| `tests/path2_web/test_serialize.py` | serialize_pattern 节点 dict 含 render_grid; serialize_analysis BOEvent 含 referenced_points |
| `path2_web_ui/tests/visible.spec.ts` | renderGridOf 正确反查 + 默认 'time' fallback |
| `path2_web_ui/tests/chart.spec.ts` | render_grid='price' 时 bo 不在 grid2 points 系列内, 在新 price-points 系列里; referenced_points 触发 satellites 系列 |

---

## Task 1: Event.is_point 几何承诺 + NodeSpec.render_grid 字段 + _validate_render_grid 校验

**Files:**
- Modify: `path2/core.py` (Event 基类加 is_point ClassVar)
- Modify: `path2/dag/nodes.py` (NodeSpec 加 render_grid)
- Modify: `path2/dag/spec.py` (PatternSpec.__post_init__ 加 _validate_render_grid)
- Modify: `tests/path2/dag/test_spec.py` (新增 3 个测试)

**Interfaces:**
- Consumes: nothing
- Produces:
  - `path2.core.Event.is_point: ClassVar[bool] = False` (子类可覆写)
  - `path2.dag.nodes.NodeSpec.render_grid: str = 'time'` (字段值约束 `'price' | 'time'`)
  - `PatternSpec._validate_render_grid` 在 NodeSpec.render_grid=='price' 但 detector.event_cls.is_point=False 时抛 ValueError

- [ ] **Step 1: 加测试 — 3 case: 默认通过 / point + price 通过 / span + price 抛错**

在 `tests/path2/dag/test_spec.py` 文件末尾追加:

```python
# ── render_grid × is_point 校验 (新增) ─────────────────────────────────

class _PointEventCls:
    """假 point 几何事件类"""
    class_id = "fakept"
    is_point = True

class _SpanEventCls:
    """假 span 几何事件类 (默认 is_point=False)"""
    class_id = "fakespan"

class _PointDet:
    event_cls = _PointEventCls
    def detect(self, source, df=None):
        return iter(())

class _SpanDet:
    event_cls = _SpanEventCls
    def detect(self, source, df=None):
        return iter(())


def test_render_grid_default_time_passes_for_span_detector():
    """默认 render_grid='time' 不触发 is_point 校验。"""
    nodes = (NodeSpec(node_id="x", detector=_SpanDet()),)
    PatternSpec(pattern_id="p", display_name="P", nodes=nodes, edges=(), root="x")


def test_render_grid_price_passes_for_point_detector():
    """render_grid='price' + point 几何 → 通过。"""
    nodes = (NodeSpec(node_id="x", detector=_PointDet(), render_grid="price"),)
    PatternSpec(pattern_id="p", display_name="P", nodes=nodes, edges=(), root="x")


def test_render_grid_price_rejects_span_detector():
    """render_grid='price' + span 几何 (is_point=False) → 抛 ValueError。"""
    nodes = (NodeSpec(node_id="x", detector=_SpanDet(), render_grid="price"),)
    with pytest.raises(ValueError, match="render_grid='price'"):
        PatternSpec(pattern_id="p", display_name="P", nodes=nodes, edges=(), root="x")
```

- [ ] **Step 2: 运行测试验证失败**

Run: `uv run pytest tests/path2/dag/test_spec.py -v`
Expected: 3 个新测试都失败 (NodeSpec 无 render_grid kwarg → TypeError; PatternSpec 无 _validate_render_grid → 不会抛)

- [ ] **Step 3: 实现 Event.is_point ClassVar**

修改 `path2/core.py`, 在 Event 类内 `class_id: ClassVar[str] = ""` 这一行下面加:

```python
    class_id: ClassVar[str] = ""   # 子类必须覆盖为非空全局唯一值(spec §2.1)
    is_point: ClassVar[bool] = False   # 子类点事件覆写为 True(start_idx==end_idx 几何承诺)
```

- [ ] **Step 4: 实现 NodeSpec.render_grid 字段**

修改 `path2/dag/nodes.py` 的 NodeSpec dataclass, 在 label 字段之后加 render_grid:

```python
@dataclass(frozen=True)
class NodeSpec:
    """拓扑节点 = 一个角色 + 自带生产者 detector + 节点级一元谓词。

    ... (已有 docstring 保留) ...

    render_grid:      事件主 marker 渲染轴 — 'price' 钉 K线主图,需 event_cls.is_point=True;
                      'time' (默认) 走 sub-grid。详见 .claude/docs/modules/path2_web.md。
    """
    node_id: str
    detector: object
    where: Tuple[Tuple[str, WherePredicate], ...] = ()
    consumes_stream: Optional[str] = None
    label: str = ""
    render_grid: str = "time"
```

- [ ] **Step 5: 实现 PatternSpec._validate_render_grid**

修改 `path2/dag/spec.py`, 在 __post_init__ 末尾加一行调用, 然后在 _validate_anchor 方法之后加新方法:

```python
    def __post_init__(self) -> None:
        self._validate_node_ids()
        self._validate_dag()
        self._validate_detector_dag()
        self._validate_where_clauses()
        self._validate_anchor()
        self._validate_render_grid()   # ★ 新增:render_grid='price' 需 event_cls.is_point=True
```

并在文件中现有 `_validate_anchor` 方法的下方 (在 `to_topology` 方法之前) 加:

```python
    def _validate_render_grid(self) -> None:
        """render_grid='price' 当前只允许 point 几何 (event_cls.is_point=True)。
        span × price 落入未定义渲染象限 — 显式拒绝, 避免静默吞 span 信息。
        未来若需 span × price (端点钉价格 + 区间淡色), 见 design §未来扩展路径 E1。"""
        for n in self.nodes:
            if n.render_grid != "price":
                continue
            event_cls = getattr(n.detector, "event_cls", None)
            if event_cls is None:
                raise ValueError(
                    f"PatternSpec._validate_render_grid: node {n.node_id!r} "
                    f"detector has no event_cls — cannot determine geometry"
                )
            if not getattr(event_cls, "is_point", False):
                raise ValueError(
                    f"PatternSpec._validate_render_grid: NodeSpec({n.node_id!r}).render_grid='price' "
                    f"requires point geometry (event_cls.is_point=True), but "
                    f"{event_cls.__name__} is span event. "
                    f"若需 span × price, 见 design §未来扩展路径 E1。"
                )
```

- [ ] **Step 6: 运行测试验证通过**

Run: `uv run pytest tests/path2/dag/test_spec.py -v`
Expected: 3 个新测试 PASS, 原有测试全部 PASS。

- [ ] **Step 7: 跑全集回归确认未破其它模块**

Run: `uv run pytest tests/path2/ -x -q`
Expected: 全绿。

- [ ] **Step 8: Commit**

```bash
git add path2/core.py path2/dag/nodes.py path2/dag/spec.py tests/path2/dag/test_spec.py
git commit -m "$(cat <<'EOF'
path2/dag: NodeSpec.render_grid + 载入期校验

引入 Event.is_point ClassVar 与 NodeSpec.render_grid 字段;
PatternSpec._validate_render_grid 在 render_grid='price' 与
span event_cls (is_point=False) 组合时显式拒绝, 避免静默吞 span 信息。
默认 render_grid='time' 守序保守, 现役 atom 行为不变。
EOF
)"
```

---

## Task 2: BOEvent.is_point/referenced_points 字段 + BODetector.emit 填充

**Files:**
- Modify: `path2/atoms/breakout.py` (BOEvent + BODetector.emit)
- Modify: `tests/path2/atoms/test_breakout_dataclasses.py` (新增 referenced_points / is_point 测试)
- Modify: `tests/path2/atoms/test_breakout_detector.py` (新增 emit 填充测试)

**Interfaces:**
- Consumes:
  - `path2.core.Event.is_point: ClassVar[bool]` (Task 1)
- Produces:
  - `BOEvent.is_point: ClassVar[bool] = True`
  - `BOEvent.referenced_points: Tuple[Tuple[int, float, str], ...] = ()` (bar_idx, price, label) 三元组
  - `BOEvent.__post_init__` 中 tuple 兜底 (类似 broken_peak_ids)
  - `BODetector.emit()` 在 emit BOEvent 时 referenced_points 填 `tuple((p.index, p.price, f"pk{p.pk_id}") for p in broken_peaks)`

- [ ] **Step 1: 加 BOEvent dataclass 测试**

在 `tests/path2/atoms/test_breakout_dataclasses.py` 末尾追加:

```python
def test_bo_event_is_point_class_attr():
    """BOEvent.is_point 是 True (单点几何承诺,供 PatternSpec._validate_render_grid 反射)。"""
    assert BOEvent.is_point is True


def test_bo_event_referenced_points_default_empty_tuple():
    """新增字段 referenced_points 默认空元组。"""
    e = BOEvent(event_id="bo_10", start_idx=10, end_idx=10)
    assert e.referenced_points == ()


def test_bo_event_referenced_points_accepts_tuple():
    """referenced_points 接受 (bar_idx, price, label) 三元组的元组。"""
    pts = ((5, 12.5, "pk0"), (7, 13.0, "pk1"))
    e = BOEvent(event_id="bo_10", start_idx=10, end_idx=10,
                referenced_points=pts)
    assert e.referenced_points == pts
    assert isinstance(e.referenced_points, tuple)


def test_bo_event_referenced_points_is_tuple_from_list():
    """传 list 时强转 tuple (与 broken_peak_ids 同型, 防 in-place mutate)。"""
    e = BOEvent(event_id="bo_10", start_idx=10, end_idx=10,
                referenced_points=[(5, 12.5, "pk0")])
    assert isinstance(e.referenced_points, tuple)
    assert e.referenced_points == ((5, 12.5, "pk0"),)
```

- [ ] **Step 2: 加 BODetector.emit 填充测试**

在 `tests/path2/atoms/test_breakout_detector.py` 末尾追加 (复用同文件 make_df 帮助函数):

```python
def test_emit_populates_referenced_points_with_pk_meta():
    """BODetector.emit 应把每个被突破的 Peak 序列化为 (index, price, f'pk{pk_id}') 入 referenced_points。"""
    # 同 test_simple_bo 的构造: peak at idx 5, BO at idx 11
    closes = [10.0] * 5 + [12.0] + [10.0] * 5 + [13.0]
    df = make_df(closes)
    bos = list(run(BODetector(total_window=10, min_side_bars=2,
                              min_relative_height=0.05, exceed_threshold=0.005,
                              peak_measure="body_top", breakout_measure="body_top"), df))
    assert len(bos) >= 1
    bo = bos[-1]
    assert len(bo.referenced_points) == bo.pk_count   # 与 pk_count 等长
    assert len(bo.referenced_points) == len(bo.broken_peak_ids)
    for (bar_idx, price, label), pk_id in zip(bo.referenced_points, bo.broken_peak_ids):
        assert isinstance(bar_idx, int) and bar_idx >= 0
        assert isinstance(price, float) and price > 0
        assert label == f"pk{pk_id}"   # label 格式锁定
```

- [ ] **Step 3: 运行测试验证失败**

Run: `uv run pytest tests/path2/atoms/test_breakout_dataclasses.py tests/path2/atoms/test_breakout_detector.py -v`
Expected: 4 个新测试都失败 (BOEvent 无 is_point/referenced_points 字段; emit 不填充)。

- [ ] **Step 4: 实现 BOEvent.is_point + referenced_points 字段**

修改 `path2/atoms/breakout.py` 中 BOEvent dataclass (line 26-41):

```python
@dataclass(frozen=True)
class BOEvent(Event):
    """单点突破事件。start_idx == end_idx == BO bar 索引。"""
    class_id = "bo"
    is_point = True   # 点几何承诺,供 PatternSpec._validate_render_grid 反射
    drought: Optional[int] = None
    pk_count: int = 0
    broken_peak_ids: Tuple[int, ...] = ()
    vol_ratio: Optional[float] = None
    peak_vol_max: float = 0.0
    referenced_points: Tuple[Tuple[int, float, str], ...] = ()
    # (bar_idx, price, label) 三元组的元组; render_grid='price' 时前端按字段
    # 存在性渲染卫星 marker (dot + text label); label 由 detector 填字面字符串,
    # 前端不读 label 内容做条件分支。

    def __post_init__(self) -> None:
        super().__post_init__()
        if not isinstance(self.broken_peak_ids, tuple):
            object.__setattr__(self, "broken_peak_ids", tuple(self.broken_peak_ids))
        if not isinstance(self.referenced_points, tuple):
            object.__setattr__(self, "referenced_points",
                               tuple(tuple(p) for p in self.referenced_points))
```

- [ ] **Step 5: 实现 BODetector.emit 填充**

修改 `path2/atoms/breakout.py` 的 BODetector.emit 方法 (line 176-225) 的 return 语句, 改为:

```python
        return BOEvent(
            event_id=span_id(self.event_cls.class_id, i, i),
            start_idx=i,
            end_idx=i,
            drought=drought,
            pk_count=pk_count,
            broken_peak_ids=broken_peak_ids,
            vol_ratio=vol_ratio,
            peak_vol_max=peak_vol_max,
            referenced_points=tuple(
                (p.index, p.price, f"pk{p.pk_id}") for p in broken_peaks
            ),
        )
```

- [ ] **Step 6: 运行测试验证通过**

Run: `uv run pytest tests/path2/atoms/ -v`
Expected: 4 个新测试 PASS, 原有测试 PASS。

- [ ] **Step 7: 跑全集回归**

Run: `uv run pytest tests/path2/ -x -q`
Expected: 全绿。

- [ ] **Step 8: Commit**

```bash
git add path2/atoms/breakout.py tests/path2/atoms/test_breakout_dataclasses.py tests/path2/atoms/test_breakout_detector.py
git commit -m "$(cat <<'EOF'
path2/atoms: BOEvent referenced_points + is_point 几何承诺

BOEvent 加 is_point=True (供 _validate_render_grid 反射) 与
referenced_points 字段; BODetector.emit 把每个被突破 Peak 序列化为
(index, price, f"pk{pk_id}") 入 referenced_points 供前端卫星 marker
渲染。broken_peak_ids 保留供 W.attr 读, 与 referenced_points 并存。
EOF
)"
```

---

## Task 3: bottom_breakout_burst dag_spec 给 bo 节点声明 render_grid='price'

**Files:**
- Modify: `path2_apps/bottom_breakout_burst/dag_spec.py`
- Modify: `tests/path2_apps/bottom_breakout_burst/test_dag_spec.py` (新增 1 个测试)

**Interfaces:**
- Consumes:
  - `NodeSpec.render_grid` 字段 (Task 1)
  - `BOEvent.is_point=True` (Task 2)
- Produces:
  - `bottom_breakout_burst` 的 bo 节点 NodeSpec 含 `render_grid='price'` (校验通过)

- [ ] **Step 1: 加 bo 节点 render_grid 测试**

在 `tests/path2_apps/bottom_breakout_burst/test_dag_spec.py` 末尾追加:

```python
def test_bo_node_declares_render_grid_price():
    """bo 节点声明 render_grid='price' (上 K线主图); 其余节点保持默认 'time'。
    PatternSpec 构造不报错 = 载入期校验 (point + price) 通过。"""
    spec = _spec()
    by = {n.node_id: n for n in spec.nodes}
    assert by["bo"].render_grid == "price"
    assert by["burst"].render_grid == "time"
    assert by["tb"].render_grid == "time"
```

- [ ] **Step 2: 运行测试验证失败**

Run: `uv run pytest tests/path2_apps/bottom_breakout_burst/test_dag_spec.py::test_bo_node_declares_render_grid_price -v`
Expected: FAIL — bo 节点 render_grid 仍是默认 'time'。

- [ ] **Step 3: 修改 dag_spec.py 给 bo 节点加 render_grid='price'**

修改 `path2_apps/bottom_breakout_burst/dag_spec.py` 的 build_pattern 函数, 在 bo NodeSpec 处加 render_grid 参数:

```python
    nodes = (
        # bo 孤立 role: 无边, 残缺 match 由 analyze 出口过滤
        # render_grid='price': bo 主三角钉 K线主图; pk 通过 referenced_points 字段
        # 作为卫星 marker 画在各自 bar 位置 (见 design §正面回答 Q2)
        NodeSpec("bo",
                 BODetector(**params.bo_kwargs()),
                 render_grid="price"),
        # ②③⑤⑥ 突破爆发(BurstDetector 消费 bo 流,嵌套 event)
        NodeSpec("burst",
                 BurstDetector(**params.burst_kwargs()),
                 where=(("first_drought", W.attr("first_drought", ">=", params.THR_DROUGHT)),
                        ("distinct_pk",   W.attr("distinct_pk",   ">=", params.THR_PK)),
                        ("vol_spike",     W.attr("max_bar_vol_ratio", ">=", params.THR_VOL))),
                 consumes_stream="bo", label="突破爆发"),
        # ⑦ 末突破后回踩(ThrowbackDetector 消费 bo 流:吃 BOEvent,不能吃 BurstEvent)
        NodeSpec("tb",
                 ThrowbackDetector(**params.throwback_kwargs()),
                 consumes_stream="bo", label="回踩确认"),
    )
```

- [ ] **Step 4: 运行测试验证通过**

Run: `uv run pytest tests/path2_apps/bottom_breakout_burst/ -v`
Expected: 全绿。

- [ ] **Step 5: 跑全集回归**

Run: `uv run pytest -x -q`
Expected: 全绿。

- [ ] **Step 6: Commit**

```bash
git add path2_apps/bottom_breakout_burst/dag_spec.py tests/path2_apps/bottom_breakout_burst/test_dag_spec.py
git commit -m "$(cat <<'EOF'
path2_apps/bbb: bo 节点声明 render_grid='price'

让 bo 主三角钉 K线主图; pk 通过 referenced_points 字段作为卫星
marker 渲染。验证 PatternSpec 载入期校验通过 (BOEvent.is_point=True)。
EOF
)"
```

---

## Task 4: serialize_pattern 节点 dict 加 render_grid 透传

**Files:**
- Modify: `path2_web/serialize.py` (serialize_pattern 节点 dict)
- Modify: `tests/path2_web/test_serialize.py` (新增 2 个测试)

**Interfaces:**
- Consumes:
  - `NodeSpec.render_grid` (Task 1)
  - bo 节点声明 `render_grid='price'` (Task 3)
  - `BOEvent.referenced_points` (Task 2)
- Produces:
  - `serialize_pattern(spec)["topology"]["nodes"][i]["render_grid"]` 透传 NodeSpec.render_grid
  - `serialize_analysis(res)["events"][i]["referenced_points"]` 已通过 _event_to_dict 的 fields 遍历自动透传 (无需改 serialize, 验证即可)

- [ ] **Step 1: 加测试**

在 `tests/path2_web/test_serialize.py` 末尾追加:

```python
def test_serialize_pattern_nodes_have_render_grid():
    """serialize_pattern 节点 dict 透传 render_grid; bo='price', 其余='time'。"""
    from path2_apps.bottom_breakout_burst.dag_spec import PATTERN_DAG
    out = serialize.serialize_pattern(PATTERN_DAG)
    by = {n["node_id"]: n for n in out["topology"]["nodes"]}
    assert by["bo"]["render_grid"] == "price"
    assert by["burst"]["render_grid"] == "time"
    assert by["tb"]["render_grid"] == "time"


def test_serialize_analysis_bo_events_have_referenced_points():
    """serialize_analysis 的 bo event dict 含 referenced_points (list of [bar_idx, price, label])。
    通过 _event_to_dict 的 fields 遍历自动透传, 验证 _jsonable 把 tuple of tuples 正确转 list of lists。"""
    res = _analyze_positive()
    out = serialize.serialize_analysis(res)
    bo_events = [e for e in out["events"] if e["class_id"] == "bo"]
    assert len(bo_events) >= 1
    for bo in bo_events:
        assert "referenced_points" in bo
        rp = bo["referenced_points"]
        assert isinstance(rp, list)
        for item in rp:
            assert isinstance(item, list)
            assert len(item) == 3
            bar_idx, price, label = item
            assert isinstance(bar_idx, int)
            assert isinstance(price, float)
            assert isinstance(label, str) and label.startswith("pk")
```

- [ ] **Step 2: 运行测试验证失败**

Run: `uv run pytest tests/path2_web/test_serialize.py -v`
Expected: 第一个测试 FAIL ("render_grid" 不在 node dict); 第二个测试可能 PASS (因为 _event_to_dict 自动透传, 但取决于 Task 2/3 是否生效)。

- [ ] **Step 3: 修改 serialize_pattern 加 render_grid 透传**

修改 `path2_web/serialize.py` 的 `serialize_pattern` 函数 (line 202-230) 内构造 node dict 处, 加 render_grid:

```python
    nodes = []
    for tn in topo.nodes:
        n = by_id[tn.node_id]
        node = {
            "node_id": tn.node_id,
            "class_id": tn.class_id,
            "label": tn.label,
            "where_rules": _rules_from_where(n.where),
            "source_tag": _source_tag_of(n.detector),
            "render_grid": n.render_grid,   # ★ 新增:透传 NodeSpec.render_grid
        }
        nodes.append(node)
```

- [ ] **Step 4: 运行测试验证通过**

Run: `uv run pytest tests/path2_web/test_serialize.py -v`
Expected: 全绿。

- [ ] **Step 5: 跑全集 path2_web 回归**

Run: `uv run pytest tests/path2_web/ -x -q`
Expected: 全绿。

- [ ] **Step 6: Commit**

```bash
git add path2_web/serialize.py tests/path2_web/test_serialize.py
git commit -m "$(cat <<'EOF'
path2_web/serialize: serialize_pattern 透传 render_grid

节点 dict 加 render_grid 字段; BOEvent.referenced_points 通过
_event_to_dict 的 fields 遍历自动透传 (tuple of tuples → list of lists)。
EOF
)"
```

---

## Task 5: 前端 types.ts 加 render_grid + referenced_points 字段

**Files:**
- Modify: `path2_web_ui/src/types.ts` (TopoNode + EventDict)
- Modify: `path2_web_ui/tests/fixtures.ts` (PATTERN fixture 给 bo 加 render_grid)
- Modify: `path2_web_ui/tests/types.spec.ts` (新增断言)

**Interfaces:**
- Consumes:
  - 后端 serialize 输出 (Task 4)
- Produces:
  - `TopoNode.render_grid?: 'price' | 'time'`
  - `EventDict.referenced_points?: Array<[number, number, string]>` (bar_idx, price, label)

- [ ] **Step 1: 改 types.spec.ts 加断言 (TDD: 字段必须可访问)**

在 `path2_web_ui/tests/types.spec.ts` 的 `it('fixtures conform...')` 内末尾追加 (在最后一个 expect 之后):

```typescript
    // render_grid 字段 (新增)
    const boNode = PATTERN.topology.nodes.find(n => n.node_id === 'bo')!
    expect(boNode.render_grid).toBe('price')
    const tbNode = PATTERN.topology.nodes.find(n => n.node_id === 'tb')!
    // render_grid 是可选字段, 不显式声明时 fixture 也不写
    expect(tbNode.render_grid === undefined || tbNode.render_grid === 'time').toBe(true)
    // referenced_points 字段 (新增)
    const bo9 = ANALYSIS.events.find(e => e.event_id === 'bo9')!
    expect(Array.isArray(bo9.referenced_points)).toBe(true)
```

- [ ] **Step 2: 改 fixtures.ts: bo 节点加 render_grid, bo9 事件加 referenced_points**

修改 `path2_web_ui/tests/fixtures.ts` 中 PATTERN.topology.nodes 数组的 bo 节点条目, 加 render_grid; ANALYSIS.events 中 bo9 加 referenced_points:

```typescript
      { node_id: 'bo', class_id: 'bo', label: '突破点串', source_tag: 'bo',
        render_grid: 'price',
        where_rules: [{ clause_id: 'first_drought', op: '>=', threshold: 60 }] },
```

并在 ANALYSIS.events 的 bo9 条目加 referenced_points:

```typescript
    { class_id: 'bo', event_id: 'bo9', source_tag: 'bo', start_idx: 9, end_idx: 9, drought: 88, vol_ratio: 3.2,
      referenced_points: [[5, 12.5, 'pk0'], [7, 13.0, 'pk1']] },
```

- [ ] **Step 3: 运行测试验证失败 (类型错误)**

Run: `cd path2_web_ui && npx vitest run tests/types.spec.ts`
Expected: FAIL — TopoNode 无 render_grid 字段, EventDict.referenced_points 类型不匹配 → ts/test 报错。

- [ ] **Step 4: 改 types.ts 加字段**

修改 `path2_web_ui/src/types.ts` 的 TopoNode 接口:

```typescript
export interface TopoNode {
  node_id: string; class_id: string; label: string
  source_tag: string
  render_grid?: 'price' | 'time'   // 新增:渲染轴声明,缺省视同 'time'
  where_rules: WhereRule[]
}
```

并修改 EventDict (注意 EventDict 已有 `[attr: string]: unknown` 平铺通配, 但显式声明 referenced_points 让类型更精确):

```typescript
export interface EventDict {
  class_id: string; event_id: string; start_idx: number; end_idx: number
  source_tag: string
  referenced_points?: Array<[number, number, string]>   // 新增:(bar_idx, price, label) 三元组数组
  [attr: string]: unknown
}
```

- [ ] **Step 5: 运行测试验证通过**

Run: `cd path2_web_ui && npx vitest run tests/types.spec.ts`
Expected: PASS。

- [ ] **Step 6: 跑全前端测试回归 (类型可能影响其他测试)**

Run: `cd path2_web_ui && npm test`
Expected: 全绿 (新字段都是可选, 旧测试无影响)。

- [ ] **Step 7: Commit**

```bash
git add path2_web_ui/src/types.ts path2_web_ui/tests/fixtures.ts path2_web_ui/tests/types.spec.ts
git commit -m "$(cat <<'EOF'
path2_web_ui/types: TopoNode.render_grid + EventDict.referenced_points

后端契约镜像 (Task 4); fixtures 给 bo 加 render_grid='price' 与
referenced_points 示例数据供 chart/visible 测试复用。
EOF
)"
```

---

## Task 6: visible.ts 加 renderGridOf 纯函数

**Files:**
- Modify: `path2_web_ui/src/render/visible.ts`
- Modify: `path2_web_ui/tests/visible.spec.ts` (新增 3 个测试)

**Interfaces:**
- Consumes:
  - `TopoNode.render_grid?` (Task 5)
- Produces:
  - `renderGridOf(e: EventDict, topology: Topology, bandKeyOf: (e: EventDict) => string): 'price' | 'time'`
  - 通过 source_tag → TopoNode 反查 render_grid; 找不到或字段缺省 → fallback 'time'。

- [ ] **Step 1: 加测试**

在 `path2_web_ui/tests/visible.spec.ts` 文件中导入语句处加 renderGridOf:

```typescript
import {
  bandKeyOf, deriveTagMap, isolatedNodeIds, isQualifiedRow,
  qualifiedIdsOf, eventTierOf, roleOfEventByBand, isBandVisible,
  renderGridOf,   // ★ 新增
} from '../src/render/visible'
```

并在 `describe('visible §3 band/tier', () => {` 块内末尾 (在 `})` 闭合前) 追加 3 个 it:

```typescript
  it('renderGridOf: bo 节点声明 price → 返回 price', () => {
    const topoWithBoPrice = {
      nodes: [
        { node_id: 'bo', class_id: 'bo', label: '', source_tag: 'bo',
          render_grid: 'price' as const, where_rules: [] },
        { node_id: 'tb', class_id: 'tb', label: '', source_tag: 'tb', where_rules: [] },
      ],
      edges: [],
    }
    const bandKeyOfFn = (e: EventDict) => e.source_tag
    expect(renderGridOf(ev('bo9', 'bo'), topoWithBoPrice, bandKeyOfFn)).toBe('price')
  })

  it('renderGridOf: tb 节点未声明 → fallback time', () => {
    const topoWithBoPrice = {
      nodes: [
        { node_id: 'bo', class_id: 'bo', label: '', source_tag: 'bo',
          render_grid: 'price' as const, where_rules: [] },
        { node_id: 'tb', class_id: 'tb', label: '', source_tag: 'tb', where_rules: [] },
      ],
      edges: [],
    }
    const bandKeyOfFn = (e: EventDict) => e.source_tag
    expect(renderGridOf(ev('tb1', 'tb'), topoWithBoPrice, bandKeyOfFn)).toBe('time')
  })

  it('renderGridOf: bandKey 匹配不到 TopoNode → fallback time', () => {
    const topoEmpty = { nodes: [], edges: [] }
    const bandKeyOfFn = (e: EventDict) => e.source_tag
    expect(renderGridOf(ev('x1', 'ghost'), topoEmpty, bandKeyOfFn)).toBe('time')
  })
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd path2_web_ui && npx vitest run tests/visible.spec.ts`
Expected: FAIL — `renderGridOf` 未导出。

- [ ] **Step 3: 实现 renderGridOf**

在 `path2_web_ui/src/render/visible.ts` 文件末尾 (在 `formatForwardReturn` 函数之后) 追加:

```typescript
/** event 主 marker 渲染轴反查:source_tag → TopoNode.render_grid;
 *  缺省 / 找不到 → 'time' (守序保守, 与后端 NodeSpec.render_grid 默认值对齐)。 */
export function renderGridOf(
  e: EventDict,
  topology: Topology,
  bandKey: (e: EventDict) => string,
): 'price' | 'time' {
  const tag = bandKey(e)
  const node = topology.nodes.find((n) => n.source_tag === tag)
  return node?.render_grid ?? 'time'
}
```

- [ ] **Step 4: 运行测试验证通过**

Run: `cd path2_web_ui && npx vitest run tests/visible.spec.ts`
Expected: PASS。

- [ ] **Step 5: 跑全前端测试**

Run: `cd path2_web_ui && npm test`
Expected: 全绿。

- [ ] **Step 6: Commit**

```bash
git add path2_web_ui/src/render/visible.ts path2_web_ui/tests/visible.spec.ts
git commit -m "$(cat <<'EOF'
path2_web_ui/render: renderGridOf 纯函数 (source_tag → render_grid)

供 chart.ts 按事件主 marker 渲染轴二分; 缺省 fallback 'time' 守序保守。
EOF
)"
```

---

## Task 7: chart.ts 按 render_grid 分流 + price-points 与 satellites 两条新 series

**Files:**
- Modify: `path2_web_ui/src/render/chart.ts`
- Modify: `path2_web_ui/tests/chart.spec.ts` (新增 4 个测试)

**Interfaces:**
- Consumes:
  - `renderGridOf` (Task 6)
  - `EventDict.referenced_points?` (Task 5)
- Produces:
  - `buildKlineOption` 返回的 ECharts option 新增 2 条 series:
    - `name: 'price-points'`, type 'custom', xAxisIndex=0, yAxisIndex=0 — bo 主三角钉 K线
    - `name: 'satellites'`, type 'custom', xAxisIndex=0, yAxisIndex=0 — 卫星 marker (dot + label)
  - 现有 `name: 'points'` series 只接收 render_grid='time' 的点事件。

**实现思路** (供 implementer 与 reviewer 对齐):
1. 在 buildKlineOption 内部计算 `filtered` 之后, 用 `renderGridOf(e, topology, bandKeyOf)` 把 filtered 分成 priceAnchored 与 timeAnchored。
2. timeAnchored 走原 splitGeometry → points/intervals 流。
3. priceAnchored 产出 pricePointData (value=[start_idx, y], y = bars[start_idx].h * 1.005)。
4. 所有 priceAnchored 事件的 referenced_points 平铺成 satelliteData (value=[bar_idx, price], label)。
5. 加 2 条 series 到 series 数组末尾 (在 highlight 之后或之前任意位置)。
6. renderItem: pricePointTriangle = 三角 (复用 renderPoint 的几何但 yAxisIndex=0 用 api.coord 转 [x, y]); renderSatellite = 圆点 + text label。

**y 派生公式** (报告 §未解争议 #1): 用 `bars[start_idx].h * 1.005`, 简单可靠。

- [ ] **Step 1: 加测试**

在 `path2_web_ui/tests/chart.spec.ts` 文件末尾找到合适位置 (在最后一个 `})` 闭合前的 describe 块内) 追加。先查看 EVENTS 数组并替换 bo9 加 referenced_points, 然后在 TOPOLOGY 加 render_grid 标注。修改 const TOPOLOGY 中 bo 节点:

```typescript
const TOPOLOGY: Topology = {
  nodes: [
    { node_id: 'down',  class_id: 'trend', label: '下跌段', source_tag: 'trend0', where_rules: [] },
    { node_id: 'side',  class_id: 'trend', label: '横盘段', source_tag: 'trend1', where_rules: [] },
    { node_id: 'bo',    class_id: 'bo',    label: '',       source_tag: 'bo',
      render_grid: 'price',                                              // ★ 新增
      where_rules: [] },
    { node_id: 'burst', class_id: 'burst', label: '爆发段', source_tag: 'burst',  where_rules: [] },
    { node_id: 'tb',    class_id: 'tb',    label: '回踩',   source_tag: 'tb',     where_rules: [] },
  ],
  edges: [
    ...
  ],
}
```

并修改 EVENTS 中 bo9 加 referenced_points:

```typescript
  { class_id: 'bo', event_id: 'bo9', source_tag: 'bo', start_idx: 9, end_idx: 9,
    referenced_points: [[5, 12.5, 'pk0'], [7, 13.0, 'pk1']] },
```

文件内现有 bars 数组应包含至少 21 根 (覆盖 start_idx 0..20)。如不存在请翻 fixtures / 或在文件内 inline 21 根 bars:

```typescript
const BARS: Bar[] = Array.from({ length: 25 }, (_, i) => ({
  date: `2024-01-${String(i + 1).padStart(2, '0')}`,
  o: 10, h: 12, l: 9, c: 11, v: 1000,
}))
```

(若已存在请复用。)

在 describe 末尾追加 4 个新 it (注意 import 顶部需加 renderGridOf):

```typescript
import { renderGridOf } from '../src/render/visible'

describe('chart render_grid 分流 + satellites', () => {
  function buildInput(level: Level): BandRenderInput {
    const { tagToNodes, tagList } = deriveTagMap(TOPOLOGY.nodes)
    const isolated = isolatedNodeIds(TOPOLOGY)
    const mIds = matchedIds(MATCHES)
    return {
      topology: TOPOLOGY, isolatedNodeIds: isolated, tagList, level,
      roleColors: { down: '#f59e0b', side: '#f59e0b', burst: '#2563eb', tb: '#16a34a', bo: '#dc2626' },
      eventTier: (e) => eventTierOf(e, mIds, new Set()),
      roleOfEventByBand: (e) => roleOfEventByBand(e, tagToNodes, tagList),
      bandKeyOf: (e) => bandKeyOf(e, tagList),
    }
  }

  it('bo 节点 render_grid=price → bo 事件不进 grid2 points 系列', () => {
    const opt: any = buildKlineOption(BARS, EVENTS, MATCHES, buildInput('detected'))
    const points = opt.series.find((s: any) => s.name === 'points')
    expect(points).toBeTruthy()
    // grid2 points 不应包含 bo 事件 (它们去 price-points)
    const boInGrid2 = points.data.filter((d: any) =>
      ['bo9', 'bo11', 'boX'].includes(d.event_id)
    )
    expect(boInGrid2.length).toBe(0)
    // tb 仍在 grid2 points
    const tbInGrid2 = points.data.filter((d: any) => d.event_id === 'tb16')
    expect(tbInGrid2.length).toBe(1)
  })

  it('新 price-points 系列存在并包含 bo 事件 (yAxisIndex=0 → grid0)', () => {
    const opt: any = buildKlineOption(BARS, EVENTS, MATCHES, buildInput('detected'))
    const pp = opt.series.find((s: any) => s.name === 'price-points')
    expect(pp).toBeTruthy()
    expect(pp.xAxisIndex).toBe(0)
    expect(pp.yAxisIndex).toBe(0)
    expect(pp.data.map((d: any) => d.event_id).sort()).toEqual(['bo11', 'bo9', 'boX'])
    // value = [start_idx, price-derived y]; y 应高于 bar high (12 * 1.005 = 12.06)
    const bo9row = pp.data.find((d: any) => d.event_id === 'bo9')
    expect(bo9row.value[0]).toBe(9)
    expect(bo9row.value[1]).toBeCloseTo(12 * 1.005, 5)
  })

  it('新 satellites 系列承载 bo.referenced_points (每点一条 record)', () => {
    const opt: any = buildKlineOption(BARS, EVENTS, MATCHES, buildInput('detected'))
    const sat = opt.series.find((s: any) => s.name === 'satellites')
    expect(sat).toBeTruthy()
    expect(sat.xAxisIndex).toBe(0)
    expect(sat.yAxisIndex).toBe(0)
    // bo9 有 2 个 referenced_points (在 EVENTS fixture 里), 应在 satellites.data 中
    expect(sat.data.length).toBeGreaterThanOrEqual(2)
    const labels = sat.data.map((d: any) => d.label)
    expect(labels).toContain('pk0')
    expect(labels).toContain('pk1')
    // value = [bar_idx, price] 透传
    const pk0 = sat.data.find((d: any) => d.label === 'pk0')
    expect(pk0.value).toEqual([5, 12.5])
  })

  it('时间锚定事件 (tb / trend / burst) 仍走原 grid2 通道', () => {
    const opt: any = buildKlineOption(BARS, EVENTS, MATCHES, buildInput('detected'))
    const points = opt.series.find((s: any) => s.name === 'points')
    const intervals = opt.series.find((s: any) => s.name === 'intervals')
    // tb 是 point → grid2 points
    expect(points.data.some((d: any) => d.event_id === 'tb16')).toBe(true)
    // burst / down / side 是 interval → grid2 intervals
    const intervalIds = intervals.data.map((d: any) => d.event_id)
    expect(intervalIds).toContain('burst1')
    expect(intervalIds).toContain('down1')
  })
})
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd path2_web_ui && npx vitest run tests/chart.spec.ts`
Expected: 4 个新测试 FAIL — `price-points` 与 `satellites` 系列不存在; bo 事件仍在 points 系列。

- [ ] **Step 3: 实现 chart.ts render_grid 分流 + 两条新 series**

修改 `path2_web_ui/src/render/chart.ts`:

(a) 顶部导入 `renderGridOf`:

```typescript
import { isBandVisible, renderGridOf } from './visible'
```

(b) 在 buildKlineOption 函数内, 计算完 `filtered` (line 56-58 处的 `events.filter(...)`) 之后, 在 `const eColor = ...` 之前插入分流:

```typescript
  // ── render_grid 分流: priceAnchored 上 K线主图(grid0); 其余走原 grid2 通道 ──
  const priceAnchored = filtered.filter((e) => renderGridOf(e, topology, bandKeyOf) === 'price')
  const timeAnchored = filtered.filter((e) => renderGridOf(e, topology, bandKeyOf) !== 'price')
```

(c) 将原本的 `const { points, intervals } = splitGeometry(filtered)` 改为:

```typescript
  const { points, intervals } = splitGeometry(timeAnchored)
```

(d) 在 `splitGeometry` 调用后、`packedIntervals` 计算前, 加 price-points 数据构造:

```typescript
  // price-anchored 主三角: y 派生 = bars[start_idx].h * 1.005 (高于 bar high 0.5%)
  const pricePointData = priceAnchored.map((e) => {
    const bar = bars[e.start_idx]
    const y = bar ? bar.h * 1.005 : 0
    return {
      value: [e.start_idx, y],
      event_id: e.event_id,
      tier: eventTier(e),
      itemStyle: { color: eColor(e) },
    }
  })

  // satellites: 任何 anchor='price' event 的 referenced_points 平铺渲染
  // (前端不读 label 内容做条件, 只透传)
  const satelliteData: Array<{ value: number[]; event_id: string; label: string; itemStyle: object }> = []
  for (const e of priceAnchored) {
    const rp = e.referenced_points
    if (!rp || !Array.isArray(rp)) continue
    for (const [barIdx, price, label] of rp as Array<[number, number, string]>) {
      satelliteData.push({
        value: [barIdx, price],
        event_id: e.event_id,
        label,
        itemStyle: { color: eColor(e) },
      })
    }
  }
```

(e) 在 series 数组中加两条新 series (放在已有 highlight 之后):

```typescript
      // D2: 选中 event 描边高亮(最高 z,不影响原 points/intervals)
      { type: 'custom', name: 'highlight', xAxisIndex: 2, yAxisIndex: 2,
        data: highlightData, renderItem: renderHighlight, encode: { x: 0 }, z: 20 },

      // ── render_grid='price' 主三角(grid0) ──
      { type: 'custom', name: 'price-points', xAxisIndex: 0, yAxisIndex: 0,
        data: pricePointData, renderItem: renderPricePoint, encode: { x: 0, y: 1 }, z: 12 },

      // ── 卫星 marker(referenced_points → grid0, dot + label) ──
      { type: 'custom', name: 'satellites', xAxisIndex: 0, yAxisIndex: 0,
        data: satelliteData, renderItem: renderSatellite, encode: { x: 0, y: 1 }, z: 13 },
```

(f) 在文件末尾 (renderBandLabel 函数之后) 追加两个新 renderItem 函数:

```typescript
// price-anchored 主三角: 在 (x, y_price) 位置画一个向下指的三角 (与 grid2 三角风格区分)
function renderPricePoint(params: any, api: any) {
  const x = api.coord([api.value(0), api.value(1)])[0]
  const y = api.coord([api.value(0), api.value(1)])[1]
  const w = 6
  return {
    type: 'polygon',
    shape: { points: [[x, y - 8], [x - w, y - 2], [x + w, y - 2]] },
    style: api.style(),
  }
}

// 卫星 marker: (bar_idx, price) 位置画一个圆点 + label 字符串
function renderSatellite(params: any, api: any) {
  const x = api.coord([api.value(0), api.value(1)])[0]
  const y = api.coord([api.value(0), api.value(1)])[1]
  const label: string = (params.data as any)?.label ?? ''
  return {
    type: 'group',
    children: [
      { type: 'circle', shape: { cx: x, cy: y, r: 3 }, style: api.style() },
      { type: 'text',
        style: { text: label, x: x + 5, y: y - 5,
          fill: api.style().fill ?? '#334155',
          fontSize: 10, textVerticalAlign: 'bottom' } },
    ],
  }
}
```

- [ ] **Step 4: 运行测试验证通过**

Run: `cd path2_web_ui && npx vitest run tests/chart.spec.ts`
Expected: 全 PASS (新 4 个 + 旧测试)。

- [ ] **Step 5: 跑全前端测试 + 构建**

Run:
```bash
cd path2_web_ui && npm test
```
Expected: 全绿。

Run:
```bash
cd path2_web_ui && npm run build
```
Expected: vue-tsc 通过 + vite build 成功 (无 TS 错误)。

- [ ] **Step 6: Commit**

```bash
git add path2_web_ui/src/render/chart.ts path2_web_ui/tests/chart.spec.ts
git commit -m "$(cat <<'EOF'
path2_web_ui/render: chart 按 render_grid 分流 + 卫星 marker

filtered events 按 renderGridOf 一分为二: 'price' 走新 price-points
系列 (grid0 主三角, y=bars[start_idx].h*1.005); 'time' 走原 grid2
通道。priceAnchored.referenced_points 平铺成 satellites 系列 (grid0
圆点 + label 文本)。前端不读 label 内容做条件, schema-driven。
EOF
)"
```

---

## Task 8: 端到端集成验证 (build + 全 Python + 全前端 + smoke)

**Files:** 无新增/修改, 仅运行全集验证。

**Interfaces:** 验证 Task 1-7 集成无回归。

- [ ] **Step 1: Python 全集**

Run: `uv run pytest -q`
Expected: 全绿 (含原有所有用例 + 本 plan 新增的 ~10 个测试)。若有红, 根据失败信息回到对应 Task 修补。

- [ ] **Step 2: 前端 vitest 全集**

Run: `cd path2_web_ui && npm test`
Expected: 全绿。

- [ ] **Step 3: 前端 build (vue-tsc + vite)**

Run: `cd path2_web_ui && npm run build`
Expected: 输出 dist/ 无 TS 错误。

- [ ] **Step 4: serialize 端到端连通 smoke**

用 Python 直接跑一次 serialize_pattern + serialize_analysis, 打印关键字段:

```bash
uv run python -c "
from path2_apps.bottom_breakout_burst.dag_spec import PATTERN_DAG
from tests.path2.fixtures.positive_case import positive_case
from path2_apps.bottom_breakout_burst import dag_spec as bbb
from path2_web import serialize

pattern_out = serialize.serialize_pattern(PATTERN_DAG)
bo_node = next(n for n in pattern_out['topology']['nodes'] if n['node_id'] == 'bo')
print('bo.render_grid =', bo_node['render_grid'])
assert bo_node['render_grid'] == 'price'

df, params = positive_case()
res = bbb.analyze(df, params)
analysis_out = serialize.serialize_analysis(res)
bos = [e for e in analysis_out['events'] if e['class_id'] == 'bo']
print('bo events found:', len(bos))
print('first bo referenced_points sample:', bos[0]['referenced_points'][:3])
assert all('referenced_points' in e for e in bos)
assert all(isinstance(e['referenced_points'], list) for e in bos)
print('SMOKE OK')
"
```

Expected: 输出包含 `bo.render_grid = price`, `bo events found: <N>`, `referenced_points` 是 list of [bar_idx, price, label] 列表, 末行 `SMOKE OK`。

- [ ] **Step 5: Commit 集成验证标签** (非必需, 仅作里程碑)

如果以上四步全绿且无任何代码改动, 跳过 commit。如有调整, 加一个收尾 commit:

```bash
# 仅当有改动时
git status   # 确认有改
git add -A
git commit -m "$(cat <<'EOF'
path2: bo/pk render_grid 端到端集成验证

全 pytest / vitest / vue-tsc / build / serialize smoke 全绿。
EOF
)"
```

---

## Self-Review

**1. Spec coverage** (final_report.md 章节 → 任务映射):
- 结论速览 (A) render_grid → Task 1 (NodeSpec 字段) + Task 3 (dag_spec 声明) + Task 4 (serialize) + Task 5/6/7 (前端)
- 结论速览 (B) referenced_points → Task 2 (BOEvent 字段 + emit) + Task 4 (serialize 自动透传) + Task 5/7 (前端 types + chart satellites)
- §span × render_grid='price' 载入期校验 → Task 1 (_validate_render_grid)
- §字段命名理由 (anchor → render_grid) → 命名在 Task 1 已用 render_grid, 无歧义
- §pk 处理:不升格 event → Task 2 (referenced_points 是 BOEvent 字段, 非新 detector); 全程未引入 PkDetector / pk stream
- §落地最小变更面 7 个文件 → Task 1-7 一一对应
- YAGNI 6 条:本 plan 未引入任一 YAGNI 项 (无 anchor_to_price boolean / 无新 grid / 无双方案 fallback / 无 axisPointer cross / 无 dist 字段 / 无 pk event)
- §未来扩展路径 E1/E2 → 不在本 plan 范围内 (报告明示 YAGNI)

**2. Placeholder scan**: 无 TBD/TODO; 每个步骤都给了完整代码与命令; expected output 都写了具体期望; 无 "similar to Task N" 占位。

**3. Type consistency check**:
- Python 端: `is_point: ClassVar[bool]` 一致 (core.py 定义, breakout.py 覆写, spec.py 反射)。
- Python 端: `render_grid: str` 一致 (nodes.py 定义, spec.py 校验, dag_spec.py 设置, serialize.py 透传)。
- Python 端: `referenced_points: Tuple[Tuple[int, float, str], ...]` 一致 (breakout.py 定义/填充, serialize.py 自动 jsonable)。
- TS 端: `TopoNode.render_grid?: 'price' | 'time'` 一致 (types.ts 定义, visible.ts renderGridOf 读, chart.ts 使用)。
- TS 端: `EventDict.referenced_points?: Array<[number, number, string]>` 一致 (types.ts 定义, chart.ts satellite 平铺读)。
- 函数名一致: 全文用 `renderGridOf` (Task 6 定义, Task 7 import 使用)。

无类型不一致。

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-19-bo-pk-render-grid.md`.

**用户偏好**: 单 session 无监管 subagent-driven 执行 (CLAUDE.md `.claude/rules/plan-execution.md` 默认), Implementer=sonnet, Reviewer=opus, 每 task 双审 (spec/quality) + 末轮 holistic。

可直接在新 session 粘贴以下命令启动:

```
/superpowers:subagent-driven-development /home/yu/PycharmProjects/Trade_Strategy/docs/superpowers/plans/2026-06-19-bo-pk-render-grid.md
```

或 (若 skill 入口要求显式 args 形式):

```
请用 superpowers:subagent-driven-development skill 执行 plan: /home/yu/PycharmProjects/Trade_Strategy/docs/superpowers/plans/2026-06-19-bo-pk-render-grid.md
模型分工: Implementer=sonnet, Reviewer (Spec/Code Quality/Final)=opus
执行节奏: 每 task 完成立即触发 spec + quality 双审, 全部 task 完毕后跑 final holistic 审。
```
