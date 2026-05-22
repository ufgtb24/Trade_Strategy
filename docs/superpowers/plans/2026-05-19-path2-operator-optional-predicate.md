# Path 2 Before/After predicate 可选化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把协议层 `Before`/`After` 的 `predicate` 从必填收敛为 `Optional[Callable]=None`(=窗内 stream 存在性),`window` 改必填 keyword-only;硬切换无 shim,仅 Before/After。

**Architecture:** 纯协议层算子签名+实现+错误路径变更(`path2/operators.py` 两函数),配套测试与权威文档写回。零生产侧调用点(`Before`/`After` 仅 `tests/` 调用,全 `window=` 具名 → 现有测试不改即零破坏证据)。

**Tech Stack:** Python 3.12,frozen dataclass,pytest,`uv run pytest`。

**权威设计稿:** `docs/superpowers/specs/2026-05-19-path2-operator-optional-predicate-design.md`

---

### Task 1: `Before`/`After` 签名+实现+测试(TDD)

**Files:**
- Modify: `path2/operators.py:19-63`(`Before` 19-36 / `At` 39-41 不动 / `After` 44-63)
- Test: `tests/path2/test_operators.py`(末尾追加新段,现有用例一字不改)

- [ ] **Step 1: 追加失败测试**

在 `tests/path2/test_operators.py` 文件**末尾**(第 119 行 `test_any_empty_is_false` 之后)追加:

```python


# ---- predicate 可选化(predicate=None = 窗内 stream 存在性)----
def test_after_predicate_none_stream_existence_true():
    a = _anchor(10, 10)
    # 流里事件已是"达标"事件,predicate=None 只问窗 (10,15] 内有没有
    stream = [_E(event_id="s12", start_idx=12, end_idx=12, ratio=0.0)]
    assert After(a, window=5, stream=stream) is True


def test_after_predicate_none_stream_existence_false():
    a = _anchor(10, 10)
    stream = [_E(event_id="s20", start_idx=20, end_idx=20, ratio=0.0)]
    assert After(a, window=5, stream=stream) is False


def test_after_predicate_none_stream_none_raises():
    a = _anchor(10, 10)
    with pytest.raises(ValueError):
        After(a, window=5)


def test_after_window_zero_short_circuits_before_valueerror():
    a = _anchor(10, 10)
    # window<=0 优先返回 False,不抛 predicate=None+stream=None 的 ValueError
    assert After(a, window=0) is False


def test_before_predicate_none_stream_existence_true():
    a = _anchor(10, 10)
    # 窗 [7,10) 含 end_idx=8
    stream = [_E(event_id="s8", start_idx=8, end_idx=8, ratio=0.0)]
    assert Before(a, window=3, stream=stream) is True


def test_before_predicate_none_stream_existence_false():
    a = _anchor(10, 10)
    stream = [_E(event_id="s2", start_idx=2, end_idx=2, ratio=0.0)]
    assert Before(a, window=3, stream=stream) is False


def test_before_predicate_none_stream_none_raises():
    a = _anchor(10, 10)
    with pytest.raises(ValueError):
        Before(a, window=3)


def test_before_window_zero_short_circuits_before_valueerror():
    a = _anchor(10, 10)
    assert Before(a, window=0) is False
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/path2/test_operators.py -q`
Expected: 8 个新用例 FAIL —— `test_*_predicate_none_stream_existence_*` / `*_window_zero_short_circuits_*` 报 `TypeError`(现签名 `predicate` 必填,`After(a, window=5)` 缺位置实参);`test_*_predicate_none_stream_none_raises` 也因 `TypeError` 而非 `ValueError` 失败。现有旧用例仍 PASS。

- [ ] **Step 3: 改 `Before` 实现**

将 `path2/operators.py` 第 19-36 行整个 `Before` 函数替换为:

```python
def Before(
    anchor: Event,
    predicate: Optional[Callable] = None,
    *,
    window: int,
    stream: Optional[Iterable[Event]] = None,
) -> bool:
    """anchor 之前 window 个 bar 内某时刻满足 predicate。
    窗口 [anchor.start_idx - window, anchor.start_idx)(不含 anchor 自身)。
    predicate=None:仅判定窗内 stream 是否存在任一事件落窗(判据留在产
    stream 的 Detector)。predicate=None 且 stream=None 无流可查 → ValueError。
    """
    if window <= 0:
        return False
    if stream is None:
        if predicate is None:
            raise ValueError(
                "Before: predicate=None 需显式 stream(无流可作存在性检测)"
            )
        lo = max(0, anchor.start_idx - window)
        return any(predicate(i) for i in range(lo, anchor.start_idx))
    return any(
        anchor.start_idx - window <= e.end_idx < anchor.start_idx
        and (predicate is None or predicate(e))
        for e in stream
    )
```

- [ ] **Step 4: 改 `After` 实现**

将 `path2/operators.py` 第 44-63 行整个 `After` 函数替换为:

```python
def After(
    anchor: Event,
    predicate: Optional[Callable] = None,
    *,
    window: int,
    stream: Optional[Iterable[Event]] = None,
) -> bool:
    """anchor 之后 window 个 bar 内某时刻满足 predicate。
    窗口 (anchor.end_idx, anchor.end_idx + window](不含 anchor 自身)。
    predicate=None:仅判定窗内 stream 是否存在任一事件落窗(判据留在产
    stream 的 Detector)。predicate=None 且 stream=None 无流可查 → ValueError。
    """
    if window <= 0:
        return False
    if stream is None:
        if predicate is None:
            raise ValueError(
                "After: predicate=None 需显式 stream(无流可作存在性检测)"
            )
        return any(
            predicate(i)
            for i in range(anchor.end_idx + 1, anchor.end_idx + window + 1)
        )
    return any(
        anchor.end_idx < e.end_idx <= anchor.end_idx + window
        and (predicate is None or predicate(e))
        for e in stream
    )
```

注:`At`(39-41)、`Over`(66-77)、`Any`(80-82)与文件首部 import 一字不动(`from typing import Callable, Iterable, Optional` 已在 `operators.py:5`,无需新增 import)。

- [ ] **Step 5: 跑全部算子测试确认通过**

Run: `uv run pytest tests/path2/test_operators.py -q`
Expected: 全 PASS(8 个新用例 + 全部现有旧用例**未改仍通过** = 零破坏证据)。

- [ ] **Step 6: 跑 path2 全量回归**

Run: `uv run pytest tests/path2/ -q`
Expected: 全绿(协议层其余、stdlib、dogfood 均不受影响)。

- [ ] **Step 7: 验收 grep**

Run: `grep -n "def Before\|def After" path2/operators.py`
Expected: 两个签名均含 `predicate: Optional[Callable] = None`、`*,`、`window: int`、`stream: Optional[Iterable[Event]] = None`。

Run: `grep -rn "Before(\|After(" path2/ | grep -v "def Before\|def After"`
Expected: 无输出(确认 `path2/` 内除定义外零调用点,无生产侧需改)。

- [ ] **Step 8: 提交**

```bash
git add path2/operators.py tests/path2/test_operators.py
git commit -m "$(cat <<'EOF'
feat(path2): Before/After predicate 可选化

predicate 必填 → Optional[Callable]=None(=窗内 stream 存在性);
window 改 keyword-only 必填;predicate=None+stream=None → ValueError;
window<=0 短路优先。仅 Before/After,At/Over/Any 不动。现有 test_operators
用例未改仍通过(零破坏)。设计稿 2026-05-19-path2-operator-optional-predicate。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: 权威文档写回

**Files:**
- Modify: `docs/research/path2_spec.md:193-227`(§2.1 `Before` / §2.3 `After`)
- Modify: `docs/path2/path2_api_reference.md:34`、`:36`、`:462-464`
- Modify: `docs/path2/path2_tutorial.md:66`、`:343`

- [ ] **Step 1: 改 spec §2.1 `Before`**

`docs/research/path2_spec.md` 第 196-210 行,把签名代码块与语义条目替换为:

```python
def Before(
    anchor: Event,
    predicate: Optional[Callable] = None,
    *,
    window: int,
    stream: Optional[Iterable[Event]] = None,
) -> bool:
```

**语义**:anchor 之前 `window` 个 bar 内,某个时刻满足 `predicate`。

- **`predicate` 可选**:
  - 省略(`predicate=None`)+ `stream`:仅判定窗内 `stream` 是否存在任一事件落窗(`anchor.start_idx - window <= event.end_idx < anchor.start_idx`),判据留在产 `stream` 的 Detector,**不在算子处二次施加**
  - `predicate(idx: int) -> bool`:对 bar 索引求值(需在 Detector / Pattern 上下文有 `df` 可访问)
  - `predicate(event: Event) -> bool`:配合 `stream`,对事件流求值(True iff 存在 event in stream 满足窗口约束 且 predicate(event))
- **`predicate=None` 且 `stream=None`**:无流可作存在性检测 → 调用时 `ValueError`(协议"绝不静默退化")
- **`window` 必填 keyword-only**:须 `window=N` 具名传
- **窗口边界**:`[anchor.start_idx - window, anchor.start_idx)`(左闭右开,不含 anchor 自身)
- **window<=0**:返回 False(空窗口),**短路优先于上面的 ValueError**

- [ ] **Step 2: 改 spec §2.3 `After`**

`docs/research/path2_spec.md` 第 221-227 行,把标题与语义条目替换为:

### 2.3 `After(anchor, predicate=None, *, window, stream=None)`

**语义**:anchor 之后 `window` 个 bar 内,某个时刻满足 `predicate`。

- 与 `Before` 对称:`predicate` 可选(`predicate=None`+`stream` = 窗内存在性,判据留在 Detector);`predicate=None` 且 `stream=None` → 调用时 `ValueError`;`window` 必填 keyword-only;`window<=0` 返回 False 且短路优先于 ValueError
- 窗口边界:`(anchor.end_idx, anchor.end_idx + window]`(左开右闭,不含 anchor 自身)
- **重要**:由于 Path 2 的"Row 落地 = 字段完成"约束,如果 anchor 自身已经是 Detector yield 出来的事件,**它的 features 已包含 lookforward window 信息**。`After` 算子通常用在**跨事件流**判断,例如 "BO 之后 5 bar 内 vol 流是否有 spike"

- [ ] **Step 3: 改 api_reference 签名行**

`docs/path2/path2_api_reference.md`:

第 34 行 `| 关系算子 | \`Before(anchor, predicate, window)\` | anchor 之前 N bar 内满足 |`
改为 `| 关系算子 | \`Before(anchor, predicate=None, *, window, stream=None)\` | anchor 之前 N bar 内满足;predicate 省略=窗内 stream 存在性 |`

第 36 行 `| 关系算子 | \`After(anchor, predicate, window)\` | anchor 之后 N bar 内满足 |`
改为 `| 关系算子 | \`After(anchor, predicate=None, *, window, stream=None)\` | anchor 之后 N bar 内满足;predicate 省略=窗内 stream 存在性 |`

- [ ] **Step 4: 改 api_reference 用法示例**

`docs/path2/path2_api_reference.md` 第 462-464 行的代码块,在 `# BO 之后 5 bar 内 vol_stream 中有放量事件` 示例**之后**追加(保留原显式 predicate 示例不动):

```python
# vol_stream 已是"达标放量"事件流时:省略 predicate,只问窗内有没有
After(bo, window=5, stream=vol_stream)
```

- [ ] **Step 5: 改 tutorial 两处**

`docs/path2/path2_tutorial.md`:

第 66 行 `Before(anchor_event, predicate, window=N)             # anchor 之前 N bar 内满足`
改为 `Before(anchor_event, predicate=None, window=N, stream=...)  # anchor 之前 N bar 内满足;predicate 省略=窗内 stream 存在性`

第 343 行 `\`After(anchor, predicate, stream, window)\` = "anchor 之后 window bar 内,stream 中至少一个事件满足 predicate"。`
改为 `\`After(anchor, predicate=None, *, window, stream=None)\` = "anchor 之后 window bar 内,stream 中至少一个事件满足 predicate;predicate 省略则只判定窗内 stream 存在任一事件,window 须 keyword 传"。`

(第 339 行 `After(anchor=bo, predicate=lambda v: isinstance(v, VolSpike), ...)` 是显式 predicate 调用,新签名下仍合法,**不动**。)

- [ ] **Step 6: 验收 grep**

Run: `grep -n "predicate=None\|keyword-only\|窗内 stream 存在性" docs/research/path2_spec.md docs/path2/path2_api_reference.md docs/path2/path2_tutorial.md`
Expected: spec §2.1/§2.3、api_reference 两行+示例、tutorial 两行均出现新契约措辞。

Run: `grep -rn "After(bo, predicate=lambda v: v.ratio" docs/path2/path2_api_reference.md`
Expected: 仍存在(原显式示例保留,仅新增 predicate=None 变体,非替换)。

- [ ] **Step 7: 提交**

```bash
git add docs/research/path2_spec.md docs/path2/path2_api_reference.md docs/path2/path2_tutorial.md
git commit -m "$(cat <<'EOF'
docs(path2): Before/After predicate 可选化 文档写回

spec §2.1/§2.3 权威契约 + api_reference 签名行/示例 + tutorial 两处:
predicate 可选(=窗内 stream 存在性)、window keyword-only、
predicate=None+stream=None ValueError、window<=0 短路优先。
.claude/docs 留 post-merge update-ai-context 统一刷。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## 收尾(实现完成后,非 plan 任务)

- holistic code review → `finishing-a-development-branch` 合入 `complex_framing`。
- post-merge:`update-ai-context` 刷 `.claude/docs/modules/path2.md`;`docs/research/path2_roadmap.md` §1 追加一行 ad-hoc 协议层改进合入记录(与 #1/#3/#4/role_index 收尾惯例一致)。
