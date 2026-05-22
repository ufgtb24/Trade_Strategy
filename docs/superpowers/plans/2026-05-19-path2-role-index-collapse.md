# PatternMatch.role_index Collapse 实现 Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `PatternMatch.role_index` 由 `Mapping[str, tuple[Event, ...]] | None` 收敛为 `Mapping[str, Event] | None`(冻结公开 API 硬切换,无 shim)。

**Architecture:** 四个 PatternDetector 共用唯一产出点 `_emit`,改一处即覆盖全部;类型 + `_emit` + `__post_init__` 不变式 + `advance_neg` 取值 + 全部 pin 死该契约的测试**必须同一 commit 落地**(否则 `pytest tests/path2/` 无法绿)——故为一个原子任务。文档写回(用户文档 + #3 设计稿横幅)为独立非代码 commit。

**Tech Stack:** Python 3.12,`uv run pytest`,frozen dataclass。

**上游 spec:** `docs/superpowers/specs/2026-05-19-path2-role-index-collapse-design.md`

---

### Task 1: 核心 collapse(生产代码 + 全部 pin 测试,单一绿 commit)

**Files:**
- Modify: `path2/stdlib/pattern_match.py`(类型 + `__post_init__`)
- Modify: `path2/stdlib/_advance.py`(`_emit` L134;`advance_neg` 取值 L522 + docstring L485)
- Test: `tests/path2/stdlib/test_pattern_match.py`(整文件重写)
- Test: `tests/path2/stdlib/test_kof.py`、`test_advance_dag.py`、`test_integration.py`、`test_labels.py`、`test_neg.py`(机械改造)

- [ ] **Step 1: 重写 `tests/path2/stdlib/test_pattern_match.py` 表达新契约(整文件覆盖)**

```python
from dataclasses import dataclass

import pytest

from path2.core import Event
from path2.stdlib.pattern_match import PatternMatch


@dataclass(frozen=True)
class _A(Event):
    pass


def _a(s, e=None):
    e = s if e is None else e
    return _A(event_id=f"a_{s}_{e}", start_idx=s, end_idx=e)


def test_construct_ok_and_role_index_single():
    a1, a2 = _a(1), _a(3)
    m = PatternMatch(
        event_id="chain_1_3",
        start_idx=1,
        end_idx=3,
        children=(a1, a2),
        role_index={"A": a1, "B": a2},
        pattern_label="chain",
    )
    assert m.role_index["A"] == a1
    assert m.role_index["B"] == a2
    assert m.children == (a1, a2)
    assert m.pattern_label == "chain"


def test_children_must_be_start_idx_ascending():
    a1, a2 = _a(1), _a(3)
    with pytest.raises(ValueError):
        PatternMatch(
            event_id="x", start_idx=1, end_idx=3,
            children=(a2, a1),  # 逆序
            role_index={"A": a1, "B": a2},
            pattern_label="chain",
        )


def test_role_index_values_must_equal_children():
    a1, a2 = _a(1), _a(3)
    with pytest.raises(ValueError):
        PatternMatch(
            event_id="x", start_idx=1, end_idx=3,
            children=(a1,),                       # 少了 a2
            role_index={"A": a1, "B": a2},
            pattern_label="chain",
        )
```

> 说明:原 `test_each_role_tuple_internally_ascending`(tuple 内逆序)**删除** —— 单 `Event` 无内部顺序,对应不变式已删,该用例不可达。

- [ ] **Step 2: 运行确认 FAIL(旧代码)**

Run: `uv run pytest tests/path2/stdlib/test_pattern_match.py -q`
Expected: FAIL。旧 `__post_init__` 对 `role_index={"A": a1}` 执行 `for label, tup in ri.items(): if list(tup) != sorted(tup, ...)` → 对单个 `_A` 实例 `list(a1)` / `sorted(a1)` 抛 `TypeError`。

- [ ] **Step 3: 改 `path2/stdlib/pattern_match.py`**

把现有文件第 11 行起的类体替换为(类型注释 + `__post_init__` 重写;`from __future__`/imports 不动):

```python
@dataclass(frozen=True)
class PatternMatch(Event):
    # 协议层继承:event_id, start_idx, end_idx
    children: tuple[Event, ...] = ()
    role_index: Mapping[str, Event] | None = None  # 标签 -> 该标签命中的唯一 Event
    pattern_label: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()
        if not config.RUNTIME_CHECKS:
            return
        ri = self.role_index or {}
        # children 必须按 start_idx 升序(§3.3)
        if list(self.children) != sorted(
            self.children, key=lambda e: e.start_idx
        ):
            raise ValueError("children 未按 start_idx 升序")
        # role_index 值集合 == children 集合(两视图不漂移)
        if {id(e) for e in ri.values()} != {id(e) for e in self.children}:
            raise ValueError("role_index 值集合 != children 集合")
```

> 删掉的是原"各 role tuple 按 start_idx 升序"循环(单 `Event` 恒真空);保留 children 升序;等价校验由"扁平化 tuple"改为"值集合"。

- [ ] **Step 4: 改 `path2/stdlib/_advance.py` 的 `_emit`(L134)**

旧:
```python
        role_index={lab: (assign[lab],) for lab in assign},
```
新:
```python
        role_index={lab: assign[lab] for lab in assign},
```

- [ ] **Step 5: 改 `path2/stdlib/_advance.py` 的 `advance_neg` 取值**

实代码 L522,旧:
```python
            e_anchor = m.role_index[anchor_label][0]
```
新:
```python
            e_anchor = m.role_index[anchor_label]
```

docstring 内伪代码 L485,旧:
```python
         - `e_anchor = m.role_index[p.anchor][0]`
```
新:
```python
         - `e_anchor = m.role_index[p.anchor]`
```

- [ ] **Step 6: 运行 `test_pattern_match.py` 确认 PASS**

Run: `uv run pytest tests/path2/stdlib/test_pattern_match.py -q`
Expected: PASS(3 passed)。

- [ ] **Step 7: 机械改造其余 pin 死旧 tuple 契约的测试**

`tests/path2/stdlib/test_kof.py`:
- L46-47 旧:
  ```python
      assert m.role_index["A"] == (ev(0, 0),)
      assert m.role_index["B"] == (ev(10, 10),)
  ```
  新:
  ```python
      assert m.role_index["A"] == ev(0, 0)
      assert m.role_index["B"] == ev(10, 10)
  ```
- `test_a_kof_id_shared_seq_byte_identical` 内末尾循环,旧:
  ```python
      for m in ms:
          flat = set()
          for vals in m.role_index.values():
              flat.update(vals)
          assert flat == set(m.children)
  ```
  新:
  ```python
      for m in ms:
          assert set(m.role_index.values()) == set(m.children)
  ```
  同函数 docstring 行 `flatten(role_index.values()) == children。` 改为 `set(role_index.values()) == children。`

`tests/path2/stdlib/test_advance_dag.py`:
- L45 旧:`    assert m.role_index["A"][0].start_idx == 0`
  新:`    assert m.role_index["A"].start_idx == 0`
- L339-343 旧:
  ```python
      for m in out:
          flat = [c for tup in m.role_index.values() for c in tup]
          assert {id(c) for c in flat} == {id(c) for c in m.children}
          for tup in m.role_index.values():
              starts = [c.start_idx for c in tup]
              assert starts == sorted(starts)
  ```
  新:
  ```python
      for m in out:
          assert {id(e) for e in m.role_index.values()} == {id(c) for c in m.children}
  ```

`tests/path2/stdlib/test_integration.py`:
- L66 旧:`    assert ms[0].role_index["L1"][0].pattern_label == "L1"`
  新:`    assert ms[0].role_index["L1"].pattern_label == "L1"`

`tests/path2/stdlib/test_labels.py`:
- L96 旧:`        children=(child,), role_index={"A": (child,)},`
  新:`        children=(child,), role_index={"A": child},`

`tests/path2/stdlib/test_neg.py`:
- `test_neg_R6_N_not_in_children_or_role_index` 内,旧:
  ```python
      from itertools import chain as ichain
      all_ri = set(ichain.from_iterable(v for v in m.role_index.values()))
      assert all_ri == flat_children
  ```
  新:
  ```python
      all_ri = set(m.role_index.values())
      assert all_ri == flat_children
  ```
- `test_neg_R10_run_invariants` 内,旧:
  ```python
      from itertools import chain as ichain
      for m in results:
          all_ri = set(ichain.from_iterable(m.role_index.values()))
          assert all_ri == set(m.children)
          for tup in m.role_index.values():
              starts = [e.start_idx for e in tup]
              assert starts == sorted(starts)
  ```
  新:
  ```python
      for m in results:
          assert set(m.role_index.values()) == set(m.children)
  ```

> 不动:`set(m.role_index) == {...}` / `set(m.role_index.keys()) == {...}` / `"N" not in m.role_index` 等键断言(键集合不受类型变更影响)。

- [ ] **Step 8: 全量回归**

Run: `uv run pytest tests/path2/ -q`
Expected: 全部 PASS,0 failed(基线 169 减去删除的 1 个 tuple-内序用例 = 168 passed,以实际为准;关键是 0 failed/0 error)。

- [ ] **Step 9: 验收 grep(spec §6)**

Run:
```bash
grep -rn "role_index.*\[0\]" path2/ tests/ docs/path2/ ; echo "rc=$?"
grep -rn "tuple\[Event" path2/stdlib/pattern_match.py ; echo "rc=$?"
```
Expected:两条均无输出且 `rc=1`(无残留 `[0]` 解包、`pattern_match.py` 无 `tuple[Event`)。

- [ ] **Step 10: Commit**

```bash
git add path2/stdlib/pattern_match.py path2/stdlib/_advance.py \
  tests/path2/stdlib/test_pattern_match.py tests/path2/stdlib/test_kof.py \
  tests/path2/stdlib/test_advance_dag.py tests/path2/stdlib/test_integration.py \
  tests/path2/stdlib/test_labels.py tests/path2/stdlib/test_neg.py
git commit -m "$(cat <<'EOF'
refactor(path2-stdlib): collapse PatternMatch.role_index 为 Mapping[str,Event]

四 Detector 每标签恒单成员,tuple 包装零信息量。硬切换无 shim:
类型 + _emit + __post_init__(删真空排序不变式,留值集合等价)+
advance_neg 取值 + 全部 pin 测试同 commit 落地。169→168(删 tuple-内序用例)。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: 文档写回(用户文档 + #3 设计稿横幅,非代码 commit)

**Files:**
- Modify: `docs/path2/path2_stdlib_guide.md`(§2 示例 + §7 字段表/不变式/示例)
- Modify: `docs/superpowers/specs/2026-05-16-path2-stdlib-pattern-detectors-design.md`(§2.1/§2.2 上方加写回横幅)

- [ ] **Step 1: 改 `docs/path2/path2_stdlib_guide.md`**

L74 旧:`    print(m.event_id, m.role_index["bo"][0].start_idx)`
新:`    print(m.event_id, m.role_index["bo"].start_idx)`

L181 旧:
```
| `role_index` | `Mapping[str, tuple[Event, ...]] \| None` | `标签 → 命中实例 tuple`(每个 tuple 内按 `start_idx` 升序,**恒 tuple**) |
```
新:
```
| `role_index` | `Mapping[str, Event] \| None` | `标签 → 该标签命中的唯一 `Event``(四个 Detector 结构性每标签单成员;否定标签不在内) |
```

L184 旧:
```
不变式(`RUNTIME_CHECKS` 开时强制,违反 `ValueError`):每个 role tuple 按 `start_idx` 升序;`children` 按 `start_idx` 升序;`role_index` 扁平化集合 == `children` 集合(两视图不漂移)。
```
新:
```
不变式(`RUNTIME_CHECKS` 开时强制,违反 `ValueError`):`children` 按 `start_idx` 升序;`role_index` 值集合 == `children` 集合(两视图不漂移)。
```

L188 旧:`    bo   = m.role_index["bo"][0]          # 标签取成员`
新:`    bo   = m.role_index["bo"]             # 标签取该标签命中的 Event`

> L168 `否定标签结构性不进 children/role_index` 语义不变,不动。

- [ ] **Step 2: 在 #3 设计稿加写回横幅**

在 `docs/superpowers/specs/2026-05-16-path2-stdlib-pattern-detectors-design.md` 中,定位到包含
```
class PatternMatch(Event):
```
的 ```python 代码块,在该代码块**起始 ` ```python ` 行的上方**插入下列横幅(原文 L58-74 全部保留不动,仅在上方加注):

```markdown
> ⚠️ **写回横幅(2026-05-19,role_index collapse)**:下文 §2.1 `role_index: Mapping[str, tuple[Event, ...]]` 与 §2.2「`role_index` 值恒为 `tuple`」裁定中的理由"**Kof 一标签多命中**"已被 #3 自身实现(`_advance.py` `_kof_dfs`/`_emit` 每标签恒单成员)**证伪** —— 与 `path2_spec.md` §9 偏差①(frozen 自检为死代码)同类。据此 `role_index` 已收敛为 `Mapping[str, Event]`(硬切换无 shim);§2.2 一致性不变式相应改为「`children` 升序 + `role_index` 值集合 == `children` 集合」(删除"各 tuple 内升序",单 `Event` 下恒真空);§2.2 提及的 `single(label)` 糖随理由失效**作废**。权威依据见 `docs/superpowers/specs/2026-05-19-path2-role-index-collapse-design.md`。原文以下保留为历史,不重写。
```

- [ ] **Step 3: Commit**

```bash
git add docs/path2/path2_stdlib_guide.md \
  docs/superpowers/specs/2026-05-16-path2-stdlib-pattern-detectors-design.md
git commit -m "$(cat <<'EOF'
docs(path2): role_index collapse 写回 — stdlib_guide §7 + #3 设计稿横幅

stdlib_guide 字段表/不变式/示例改单 Event;#3 设计稿加写回横幅,
记 tuple 理由"Kof 一标签多命中"经实现证伪 + collapse 决策指针。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## 收尾说明(非任务,执行者须知)

- `.claude/docs/modules/path2.md:51`("role_index 标签→升序 tuple 恒 tuple")**不在本 plan 改** —— 按 #1/#3/#4 既定惯例,合入后统一跑 `update-ai-context` 刷新(该文件只反映合入后代码状态)。
- `docs/research/path2_spec.md` 无 `role_index`(协议层不含 stdlib),无需改。
- 全程不引入 shim / 弃用期 / `single(label)` 糖;不动 `children` 类型。

## Self-Review(plan 作者已执行)

1. **Spec 覆盖**:spec §2(类型+_emit)→ Task1 Step3-4;§3(不变式)→ Step3;§4.1(advance_neg)→ Step5;§4.2(测试)→ Step1/7;§5(文档+#3写回)→ Task2;§6(验收)→ Step8-9;§7(非目标)→ 收尾说明。无缺口。
2. **占位符扫描**:无 TBD/含糊;每个代码步给出确切 old/new。
3. **类型一致**:全程 `Mapping[str, Event] | None`;`_emit` 产 `{lab: assign[lab]}`;不变式用 `ri.values()` 单值集合;`advance_neg` 取 `m.role_index[anchor_label]`;测试断言 `== ev(...)` / `.start_idx` 与之自洽。
