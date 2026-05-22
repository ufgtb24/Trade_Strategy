# Path 2 `Overlaps` 多 mode 区间关系算子 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在协议层新增 `Overlaps(anchor, mode, predicate=None, *, stream) -> bool`——5 mode 区间关系存在性算子(宽义 overlap=任意相交)。

**Architecture:** 纯协议层加法:`path2/operators.py` 新增 `Overlaps` + 私有 `_overlaps_one` 关系判定 + `_OVERLAP_MODES` 常量;`path2/__init__.py` 导出;配套测试与文档写回。零生产侧调用点,不改任何现有算子。

**Tech Stack:** Python 3.12,frozen dataclass,pytest,`uv run pytest`。

**权威设计稿:** `docs/superpowers/specs/2026-05-22-path2-overlaps-operator-design.md`

---

### Task 1: `Overlaps` 算子 + 导出 + 测试(TDD)

**Files:**
- Modify: `path2/operators.py`(在 `Any`(末尾 100 行)之后追加 `_OVERLAP_MODES` / `_overlaps_one` / `Overlaps`;现有函数与 import 不动——`Optional`/`Callable`/`Iterable` 已在 `operators.py:5`)
- Modify: `path2/__init__.py`(import 行 + `__all__` 加 `Overlaps`)
- Test: `tests/path2/test_operators.py`(末尾追加新段,现有用例一字不改)

- [ ] **Step 1: 追加失败测试**

在 `tests/path2/test_operators.py` 文件**末尾**(现有最后一个测试 `test_any_empty_is_false` 之后)追加。注:`_E` / `_anchor` 已在该文件定义(`_E(event_id, start_idx, end_idx, ratio=0.0, ...)`、`_anchor(s, e)` 返回 `_E(event_id=f"a_{s}_{e}", start_idx=s, end_idx=e)`),`Overlaps` 需加入文件顶部 import。

先把 `tests/path2/test_operators.py:7` 的
```python
from path2.operators import After, Any, At, Before, Over
```
改为
```python
from path2.operators import After, Any, At, Before, Over, Overlaps
```

再在文件末尾追加:

```python


# ---- Overlaps(5 mode 区间关系存在性)----
def _ev(s, e):
    return _E(event_id=f"b_{s}_{e}", start_idx=s, end_idx=e)


def test_overlaps_contains():
    a = _anchor(10, 20)
    assert Overlaps(a, "contains", stream=[_ev(12, 15)]) is True   # 整体在内
    assert Overlaps(a, "contains", stream=[_ev(8, 15)]) is False    # 左探出


def test_overlaps_within():
    a = _anchor(12, 15)
    assert Overlaps(a, "within", stream=[_ev(10, 20)]) is True      # B 吞掉 A
    assert Overlaps(a, "within", stream=[_ev(13, 14)]) is False     # B 在 A 内


def test_overlaps_overlapped_front():
    a = _anchor(10, 20)
    assert Overlaps(a, "overlapped_front", stream=[_ev(5, 12)]) is True   # B 前探入
    # meets:e.end == a.start 不算真交叠
    assert Overlaps(a, "overlapped_front", stream=[_ev(5, 10)]) is False
    # e.end == a.end 是 within(B 含 A),非 front
    assert Overlaps(a, "overlapped_front", stream=[_ev(5, 20)]) is False


def test_overlaps_overlapped_back():
    a = _anchor(10, 20)
    assert Overlaps(a, "overlapped_back", stream=[_ev(15, 25)]) is True   # B 后延伸
    # meets:e.start == a.end 不算真交叠
    assert Overlaps(a, "overlapped_back", stream=[_ev(20, 25)]) is False
    # e.start == a.start 是 within,非 back
    assert Overlaps(a, "overlapped_back", stream=[_ev(10, 25)]) is False


def test_overlaps_equals():
    a = _anchor(10, 20)
    assert Overlaps(a, "equals", stream=[_ev(10, 20)]) is True
    assert Overlaps(a, "equals", stream=[_ev(10, 19)]) is False


def test_overlaps_a_equals_b_hits_contains_within_equals():
    a = _anchor(10, 20)
    b = [_ev(10, 20)]
    assert Overlaps(a, "contains", stream=b) is True
    assert Overlaps(a, "within", stream=b) is True
    assert Overlaps(a, "equals", stream=b) is True


def test_overlaps_mode_set_any_of():
    a = _anchor(10, 20)
    b = [_ev(5, 12)]                       # 仅满足 overlapped_front
    assert Overlaps(a, {"contains", "overlapped_front"}, stream=b) is True
    assert Overlaps(a, {"contains", "within"}, stream=b) is False


def test_overlaps_point_events_coincide():
    a = _anchor(10, 10)                    # 点事件
    assert Overlaps(a, "contains", stream=[_ev(10, 10)]) is True   # 同 idx 共现
    assert Overlaps(a, "within", stream=[_ev(10, 10)]) is True
    assert Overlaps(a, "equals", stream=[_ev(10, 10)]) is True
    assert Overlaps(a, "contains", stream=[_ev(11, 11)]) is False
    # 点事件下 overlap 类永不命中
    assert Overlaps(a, "overlapped_front", stream=[_ev(10, 10)]) is False


def test_overlaps_predicate_filter():
    a = _anchor(10, 20)
    b = [_E(event_id="x", start_idx=12, end_idx=15, ratio=1.0)]
    # 关系成立但 predicate 否决 → False
    assert Overlaps(a, "contains", lambda e: e.ratio >= 2.0, stream=b) is False
    assert Overlaps(a, "contains", lambda e: e.ratio >= 1.0, stream=b) is True


def test_overlaps_empty_stream_is_false():
    a = _anchor(10, 20)
    assert Overlaps(a, "contains", stream=[]) is False


def test_overlaps_unknown_mode_raises():
    a = _anchor(10, 20)
    with pytest.raises(ValueError):
        Overlaps(a, "during", stream=[_ev(12, 15)])


def test_overlaps_empty_mode_set_raises():
    a = _anchor(10, 20)
    with pytest.raises(ValueError):
        Overlaps(a, set(), stream=[_ev(12, 15)])


def test_overlaps_negation_no_b_during_a():
    a = _anchor(10, 20)
    d = [_ev(30, 30)]                      # 点事件,落在 a 之外
    assert (not Overlaps(a, "contains", stream=d)) is True   # 期间无 D
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/path2/test_operators.py -q`
Expected: 新用例 FAIL/ERROR —— `ImportError`/`cannot import name 'Overlaps'`(尚未定义)。

- [ ] **Step 3: 实现 `Overlaps`**

在 `path2/operators.py` 文件**末尾**(`Any` 函数之后)追加:

```python


_OVERLAP_MODES = {
    "contains",
    "within",
    "overlapped_front",
    "overlapped_back",
    "equals",
}


def _overlaps_one(a: Event, e: Event, mode: str) -> bool:
    """单个 mode 下 e 是否与 a 成该区间关系(A=a 锚点,B=e)。"""
    if mode == "contains":            # A 包含 B
        return a.start_idx <= e.start_idx and e.end_idx <= a.end_idx
    if mode == "within":              # A 属于 B
        return e.start_idx <= a.start_idx and a.end_idx <= e.end_idx
    if mode == "overlapped_front":    # A 前端被叠:B 从前方探入
        return e.start_idx < a.start_idx and a.start_idx < e.end_idx < a.end_idx
    if mode == "overlapped_back":     # A 后端被叠:B 从 A 内延伸到后方
        return a.start_idx < e.start_idx < a.end_idx and a.end_idx < e.end_idx
    # mode == "equals":同段
    return e.start_idx == a.start_idx and e.end_idx == a.end_idx


def Overlaps(
    anchor: Event,
    mode: "str | Iterable[str]",
    predicate: Optional[Callable] = None,
    *,
    stream: Iterable[Event],
) -> bool:
    """stream 中是否存在与 anchor 成指定区间关系的事件(宽义 overlap=任意相交)。

    mode:单个 mode 字符串或一组(set/list),任一命中即 True。5 种(A=anchor,B=事件):
      "contains"          A 包含 B: a.start <= e.start and e.end <= a.end
      "within"            A 属于 B: e.start <= a.start and a.end <= e.end
      "overlapped_front"  A 前端被叠: e.start < a.start and a.start < e.end < a.end
      "overlapped_back"   A 后端被叠: a.start < e.start < a.end and a.end < e.end
      "equals"            同段: e.start == a.start and e.end == a.end
    包含用 <=(共享端点归包含,A==B 同时命中 contains/within/equals);重叠要真交叠
    (meets 单点相接不命中)。predicate 给出则与关系判定 AND。stream 必填(区间关系
    对裸 bar 索引无意义,故无 stream=None 索引形态)。
    """
    modes = {mode} if isinstance(mode, str) else set(mode)
    if not modes:
        raise ValueError("Overlaps: mode 不能为空")
    unknown = modes - _OVERLAP_MODES
    if unknown:
        raise ValueError(
            f"Overlaps: 未知 mode {unknown}; 合法值 {sorted(_OVERLAP_MODES)}"
        )
    return any(
        any(_overlaps_one(anchor, e, m) for m in modes)
        and (predicate is None or predicate(e))
        for e in stream
    )
```

注:`At`/`Before`/`After`/`Over`/`Any` 与文件 import **一字不动**(`from typing import Callable, Iterable, Optional` 已在 `operators.py:5`)。

- [ ] **Step 4: 导出 `Overlaps`**

`path2/__init__.py`:
- 第 6 行 `from path2.operators import After, Any, At, Before, Over`
  改为 `from path2.operators import After, Any, At, Before, Over, Overlaps`
- `__all__` 中 `"Any",`(第 19 行)之后加一行 `    "Overlaps",`

- [ ] **Step 5: 跑算子测试确认通过**

Run: `uv run pytest tests/path2/test_operators.py -q`
Expected: 全 PASS(新 13 用例 + 全部现有旧用例未改仍通过)。

- [ ] **Step 6: path2 全量回归**

Run: `uv run pytest tests/path2/ -q`
Expected: 全绿。

- [ ] **Step 7: 验收 grep**

Run: `grep -n "def Overlaps" path2/operators.py`
Expected: 签名 `def Overlaps(anchor: Event, mode: "str | Iterable[str]", predicate: Optional[Callable] = None, *, stream: Iterable[Event]) -> bool:`(分行)。

Run: `python -c "from path2 import Overlaps; print('ok')"`
Expected: `ok`(导出生效)。

- [ ] **Step 8: 提交**

```bash
git add path2/operators.py path2/__init__.py tests/path2/test_operators.py
git commit -m "$(cat <<'EOF'
feat(path2): Overlaps 多 mode 区间关系算子

新增协议层 Overlaps(anchor, mode, predicate=None, *, stream)->bool:
5 mode(contains/within/overlapped_front/overlapped_back/equals)宽义
相交存在性,mode 可传一组任一命中;包含用<=、重叠要真交叠、meets 不命中;
stream 必填无索引形态、无 window。涵盖原 During 用例。现有 test_operators
用例未改仍通过(零破坏)。设计稿 2026-05-22-path2-overlaps-operator。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: 文档写回

**Files:**
- Modify: `docs/research/path2_spec.md`(§2 关系算子节,在 `### 2.5 \`Any(...)\`` 之后新增 `### 2.6 \`Overlaps(...)\``)
- Modify: `docs/path2/path2_api_reference.md`(关系算子表新增 `Overlaps` 行 + 用法示例)
- Modify: `docs/path2/path2_tutorial.md`(补 `Overlaps` 用法一处)

- [ ] **Step 1: spec §2 新增 Overlaps 节**

在 `docs/research/path2_spec.md` 中定位 `### 2.5 \`Any(events, predicate)\`` 节的末尾(到下一个 `##` 或 `###` 之前),在其后插入:

````
### 2.6 `Overlaps(anchor, mode, predicate=None, *, stream)`

```python
def Overlaps(
    anchor: Event,
    mode: "str | Iterable[str]",
    predicate: Optional[Callable] = None,
    *, stream: Iterable[Event],
) -> bool:
```

**语义**:`stream` 中是否存在与 `anchor` 成指定**区间关系**的事件。"overlap" 取**宽泛义 = 任意相交**,`mode` 描述相交形状。返回 `bool`(存在性)。

- **5 个 mode**(A = anchor,B = stream 事件):

  | `mode` | 含义 | 判据 |
  |---|---|---|
  | `"contains"` | A 包含 B | `A.start ≤ B.start ∧ B.end ≤ A.end` |
  | `"within"` | A 属于 B | `B.start ≤ A.start ∧ A.end ≤ B.end` |
  | `"overlapped_front"` | A 前端被叠 | `B.start < A.start ∧ A.start < B.end < A.end` |
  | `"overlapped_back"` | A 后端被叠 | `A.start < B.start < A.end ∧ A.end < B.end` |
  | `"equals"` | 同段 | `B.start == A.start ∧ B.end == A.end` |

- **边界**:包含用 `≤`(共享端点归包含,`A==B` 同时命中 contains/within/equals);重叠要**真交叠**(meets 单点相接不命中)。
- **`mode` 可传一组**:任一命中即 `True`(any-of)。未知 mode / 空 mode 集合 → `ValueError`。
- **`stream` 必填 keyword-only**:区间-区间关系对裸 bar 索引无意义,故**无** `stream=None` 索引形态。`predicate` 给出则与关系判定 AND。
- 与 `Before`/`After`(纯前/纯后,end_idx 不交)**互补**:`Overlaps` 是相交族。
- 点事件下 `contains`/`within`/`equals` 等价(= 同 idx 共现),overlap 类永不命中。
- 备注:多 mode 为使用方需求的设计选择(覆盖了"单语义最小"的初始倾向)。
````

- [ ] **Step 2: api_reference 关系算子表新增行**

`docs/path2/path2_api_reference.md`:定位关系算子索引表中 `| 关系算子 | \`Any(events, predicate)\` | 容器至少一个满足 |` 那一行,在其后插入一行:

```
| 关系算子 | `Overlaps(anchor, mode, predicate=None, *, stream)` | stream 中存在与 anchor 成区间关系的事件;mode∈{contains/within/overlapped_front/overlapped_back/equals},可传一组 |
```

- [ ] **Step 3: api_reference 用法示例**

`docs/path2/path2_api_reference.md`:在该文件 §2 详细算子节的末尾(最后一个算子小节之后、下一个 `##` 之前)追加一个 `Overlaps` 小节:

````
### `Overlaps` — 区间关系存在性(宽义 overlap=任意相交)

```python
# ABC 期间不发生 D(D 多为点事件;点事件下 contains 即"同 idx 落在 [A.start, A.end]")
not Overlaps(m, "contains", stream=d_events)

# D 与 m 部分穿插(前/后任一向)
Overlaps(m, {"overlapped_front", "overlapped_back"}, stream=d_events)

# 存在与 a 精确同段 / 点事件同刻共现的 b
Overlaps(a, "equals", stream=b_events)

# 叠加额外判据(关系成立 且 ratio>=2)
Overlaps(m, "contains", lambda e: e.ratio >= 2.0, stream=d_events)
```

5 mode 判据见 spec §2.6。包含用 `≤`、重叠要真交叠(meets 不命中);`stream` 必填、无 `window`、无索引形态。
````

- [ ] **Step 4: tutorial 补 Overlaps 用法**

`docs/path2/path2_tutorial.md`:在关系算子相关小节(出现 `Before`/`After` 速查或讲解处)附近,追加一段:

```
`Overlaps(anchor, mode, *, stream)` = "stream 中是否存在与 anchor 成区间关系的事件"。
mode ∈ {"contains", "within", "overlapped_front", "overlapped_back", "equals"},可传一组(任一命中)。
"overlap" 取宽义=任意相交;包含用 ≤、重叠要真交叠。典型:`not Overlaps(m, "contains", stream=d)` = "m 期间不发生 d"。
```

- [ ] **Step 5: 验收 grep**

Run: `grep -rn "Overlaps" docs/research/path2_spec.md docs/path2/path2_api_reference.md docs/path2/path2_tutorial.md`
Expected: spec §2.6、api_reference 表行 + 示例小节、tutorial 一段均命中;5 mode 字符串拼写一致(`overlapped_front`/`overlapped_back`,非 `overlap_*`)。

Run: `grep -rn "overlap_front\|overlap_back" docs/`
Expected: 无输出(无旧拼写残留)。

- [ ] **Step 6: 提交**

```bash
git add docs/research/path2_spec.md docs/path2/path2_api_reference.md docs/path2/path2_tutorial.md
git commit -m "$(cat <<'EOF'
docs(path2): Overlaps 算子文档写回

spec §2.6 权威定义 + api_reference 表行/示例 + tutorial 用法:
5 mode 区间关系存在性、mode 可传一组、宽义 overlap、stream 必填无索引形态。
.claude/docs 留 post-merge update-ai-context 统一刷。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## 收尾(实现完成后,非 plan 任务)

- holistic code review → `finishing-a-development-branch` 合入 `complex_framing`。
- post-merge:`update-ai-context` 刷 `.claude/docs/modules/path2.md`(协议层算子加 `Overlaps`);`docs/research/path2_roadmap.md` §1 追加一行 ad-hoc 协议层改进合入记录(与既有惯例一致)。
