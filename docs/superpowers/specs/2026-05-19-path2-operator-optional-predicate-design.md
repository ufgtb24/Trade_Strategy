# Path 2 协议层:Before/After 关系算子 predicate 可选化 — 设计稿

> 日期:2026-05-19
> 状态:已通过用户分节审批,待用户审阅本稿 → 转 writing-plans
> 上游:`path2/operators.py`、`path2/__init__.py`、`docs/research/path2_spec.md` §1.3、`tests/path2/test_operators.py`
> 约束:走 superpowers 管线;brainstorm 澄清依本仓约定(带推荐项 + tom 选项),本次用户逐问直答未派 tom

## 0. 目标

把协议层关系算子 `Before` / `After` 的 `predicate` 从**必填**收敛为**可选**(`Optional[Callable] = None`):`predicate=None` 时算子只判定"锚点时间窗内 `stream` 是否存在任一事件落窗",不在调用点二次施加判据。同时 `window` 改为**必填 keyword-only**。这是 `path2/__init__` 出口的**冻结公开 API 变更**,采**硬切换、无 shim**。作用域**仅 `Before`/`After`**;`At`/`Over`/`Any` 一字不动。

## 1. 动机(为什么这是消除泄漏抽象,不只是口味)

协议层三角色叙事:`Detector` 是"动词(产出事件)",关系算子(Pattern 组件)"只评估、不产出"。**"什么算合格事件"(如放量 `ratio>=2.0`)是产出方的身份判据,本应固化在产 `stream` 的 Detector 里**。现行签名强制每个含该 `stream` 的关系都重写一遍判据(`After(bo, lambda e: e.ratio>=2.0, window=5, stream=vol)`),把同一份真相散落到 N 个调用点——这是泄漏抽象,违背 CLAUDE.md 第一性原理 / 奥卡姆 / 反过度设计。

`predicate=None` 让"存在性"成为算子的**基准问题**、判据细化变 **opt-in**,比强制写 `lambda e: True` 空壳更符合单一职责。对已有显式 `predicate` 的调用语义零影响。

**关键事实(已查证)**:`tests/path2/`、`docs/path2/` 内**全部** `Before`/`After` 调用点均按 `window=N` 关键字传 `window`、按位置传 `predicate`。故 `window` 改 keyword-only 必填**对现有调用点零破坏**——签名变更风险从"破坏性"降为"近零风险纯增益"。

## 2. 签名与语义契约变更

**`path2/operators.py`**

```python
def Before(anchor: Event,
           predicate: Optional[Callable] = None,
           *, window: int,
           stream: Optional[Iterable[Event]] = None) -> bool
def After(anchor: Event,
          predicate: Optional[Callable] = None,
          *, window: int,
          stream: Optional[Iterable[Event]] = None) -> bool
```

- `window`:位置→**必填 keyword-only**(`*` 之后、无默认)。keyword-only-required 是 Python 成熟惯用法;本仓本就只用 `window=N`,此变更固化既有惯例而非扭曲。
- `predicate`:必填 → `Optional[Callable] = None`。
- **`predicate=None` 语义**:仅判定窗内 `stream` 是否存在任一事件落窗,判据完全留在产 `stream` 的 Detector。
- **`predicate` 给出时**:语义与现状完全一致(窗内存在满足该谓词的事件)。
- 窗口边界、`window<=0 → False` 短路:**均不变**。
- 作用域**仅 `Before`/`After`**。`At(anchor, predicate)`(+⊤ 退化恒 True,无判别力)、`Any(events, predicate)`(容器存在性,另类语义)、`Over(...)`(无 `predicate` 参数)**签名一字不动**。

## 3. 内部实现(None 分支,零开销 fast-path)

`stream` 给定且 `predicate is None` 时,不构造、不逐元素调用空壳闭包——与协议层"`RUNTIME_CHECKS` 关即零开销"同源:

```python
def After(anchor, predicate=None, *, window, stream=None) -> bool:
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

`Before` 对称:窗口 `[anchor.start_idx - window, anchor.start_idx)`,`stream=None` 分支同样先 `window<=0` 再判 `predicate is None`,`stream` 分支条件改为 `(predicate is None or predicate(e))`。`At`/`Over`/`Any` 函数体不动。

## 4. 错误处理

唯一新增失败路径:`predicate=None` 且 `stream=None` → `ValueError`。算子是纯函数无"构造点",故落在**调用算子时**抛,与协议层"绝不静默退化"(bool-as-idx / 标签冲突 ValueError)同源。

顺序契约:`window<=0` 短路 `return False` **保持在最前**,优先于该 `ValueError`——`window<=0` 时连 `stream`/`predicate` 都不看,维持现状语义不回归。

## 5. 调用点 + 测试改造

### 5.1 生产调用点(`path2/`)

`path2/` 内除 `operators.py` 定义本身,无 `Before`/`After` 调用点(`grep` 已验证:调用点仅在 `tests/`)。`path2/__init__.py` 出口名单不变(`Before`/`After` 仍导出,签名变更不涉及导出列表)。

### 5.2 测试改造(`tests/path2/test_operators.py`)

- **现有用例不改**:全部 `window=N` 具名 + `predicate` 位置传,与新签名二进制兼容;不改即零破坏回归证据。
- **新增用例**(均为 `Before` 与 `After` 对称两套):
  1. `predicate=None` + `stream` 内有事件落窗 → `True`
  2. `predicate=None` + `stream` 内无事件落窗 → `False`
  3. `predicate=None` + `stream=None` → `pytest.raises(ValueError)`
  4. `window<=0` + `predicate=None` + `stream=None` → `False`(短路优先于 ValueError)
- `At`/`Any`/`Over` 测试**零改动、零新增**。

## 6. 文档写回(冻结层变更连带)

- **`docs/research/path2_spec.md` §1.3 算子节(权威)**:`predicate` 改可选;`predicate=None`=窗内 `stream` 存在性;`window` keyword-only 必填;`predicate=None`+`stream=None` → ValueError;短路顺序契约。按 role_index 收敛先例,spec 是权威须同步。
- **`docs/path2/path2_api_reference.md`** L34/L36:`Before/After` 签名行补 `predicate` 可选 + `window=` 具名;新增 `predicate=None` 存在性用法示例。
- **`docs/path2/path2_tutorial.md`**、**`docs/path2/path2_stdlib_guide.md`**:出现 `Before/After` 的示例统一 `window=` 具名;择一处展示 `predicate=None`("流已自带阈值,只问窗内有没有")。
- **`.claude/docs/modules/path2.md`**:**本次不改**,留 post-merge `update-ai-context` 统一刷新(与 #1/#3/#4/role_index 惯例一致)。
- **`docs/research/path2_roadmap.md`**:此项为 ad-hoc 协议层改进(非路线 #N);收尾时在 §1 追加一行合入记录即可,不改路线结构。

## 7. 验收标准

- `uv run pytest tests/path2/ -q` 全绿;现有 `test_operators.py` 用例**未改仍通过**(零破坏证据)。
- 新增 4 类用例(Before/After 各一套)确实覆盖:存在/不存在两路、`predicate=None`+`stream=None` ValueError、`window<=0` 短路优先。
- `grep -n "def Before\|def After" path2/operators.py` 签名为 `predicate=None` + `*, window` + `stream=None`。
- `grep -rn "Before(\|After(" path2/` 除定义外零调用点(确认无生产侧需改)。
- `At`/`Over`/`Any` 在 `operators.py` 与 `test_operators.py` 中 `git diff` 为空。

## 8. 非目标(YAGNI)

- 不加任何 shim / 弃用期 / `EXISTS` 哨兵糖(硬切换;方案 B 已否)。
- 不动 `At`/`Over`/`Any` 签名或语义(作用域用户已定仅 Before/After)。
- 不重排 `window`/`predicate` 位置(用户已定 keyword-only window,非位置重排;方案 C 已否)。
- 不改协议层窗口边界 / `window<=0` 语义 / 其它算子。
- 不在本分支改 `.claude/docs/`(post-merge update-ai-context 统一做)。
- 不引入 stdlib 侧任何配套(本次纯协议层算子)。
