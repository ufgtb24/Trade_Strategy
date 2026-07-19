# backend_debug · event_class gate 门限 · 设计草案 rev3

> Author: `backend_debug` teammate · rev1 2026-07-16 · rev2 Round 1 peer 收编 · rev3 Round 2 peer 收编
> Scope: Python 后端契约(debug_ctx / detector 埋点 / api handler / 测试)· 前端 UI 归 frontend_ux · 机制质疑归 skeptic

**rev3 changelog**(相对 rev2):
- **§4.4 沉没成本论修正**:承 skeptic Round 2 C1 · 承认 rev2 算术漏洞(测试成本对称)· 论点收窄到"作者纪律早晚建立 · 早建更清晰" + "预建 vs 随需增建"抬到 leader 决策 · 不再声称"迟做 3× 成本"
- **§4.3 AST 契约测试反射 `_CLASS_ID_REGISTRY`**:承 skeptic Round 2 C2 · 硬枚举 → 反射注册表 · 双源消除
- **§8.3 cache-hit 严格 spec**:承 frontend_ux Round 2 pydevd bug 提醒 · cache-hit 必须 skip 整个 detector 路径 + skip 写 env(选项 X 明确 · 选项 Y 拒绝)
- **§14 contextvars 阻力具体化**:承 skeptic Round 2 C3 · 列出"本轮迁"的具体阻力(测试 fixture 重写 · v3 spec 已 landed 一起改动大 · 单 commit revert 成本变化)· 但接受 leader 可选"顺手迁"
- **§5.4 default 与前端 sync**:承 skeptic Round 2 C4 · 明标前端实际 traffic 中 handler `if event_class:` skip 分支几乎不走(前端永远发具体 class · "全部"是 UI 词汇非 wire 层默认)
- **§4.2 composite forward-compat 收窄 + §6.3 role optional 统一 YAGNI**:承 skeptic Round 2 C5 · 删 §4.2 composite 规约段落 · 硬约束为"class_id == event_cls.class_id" · 与 §6.3 拒 role optional 统一立场
- **§13.1 契约 C 升为必需**:承 frontend_ux Round 2 · anchorsOf fallback 是 latent bug(语义偷换)· has_debug_hooks flag 从"可选"升为"v4 必需"
- **§13.2 命名定稿**:frontend_ux Round 2 已接受 `DEBUG_EVENT_CLASS`
- **§15 leader 待决 · 加"预建 vs 随需增建"**:核心决策项 · bo/burst roadmap 依赖(承 skeptic Round 2 leader-defer)

**rev2 changelog**(相对 rev1):
- §8 cache 重写(接 skeptic P2 事实 · 采 frontend_ux §2.5 cache key 含 filter 规格)
- §14 新增 env → contextvars 长期方向
- §2/1.1.5 承 frontend_ux anchor kind 术语泛化观察
- §4.4 沉没成本论(rev3 修正)
- §13 契约 C 精细化 has_debug_hooks flag(rev3 升为必需)

---

## 0. 一句话结论

**在 v3 role-gated debug 的四层 gate 上,平行叠加第五层 `DEBUG_EVENT_CLASS` env,机制、语义、生命周期与 `DEBUG_ROLE` 逐字同构。**

- `debug_break(i, *, role, class_id)` — 双 required kwarg,两 gate 各自独立可省略(env 未设 = 该 gate 不做匹配)
- 组合语义 = `range_match ∧ role_match ∧ class_match`(三 gate all-and · 短路)
- 前端"全部"= handler 不写 `DEBUG_EVENT_CLASS` env(mirror `if role:` 判据)
- 现有 5 处 tb `debug_break` 增 `class_id='tb'` kwarg;handler `finally` 三 env pop;AST 契约测试从 role Counter 扩到 (role, class_id) 二维 Counter
- Backend 不引入 gate_failures cache(混淆 display filter 与 debug filter 两个正交问题;debug 模式下 cache 得被禁掉才对,反而增加复杂度)

**核心洞见**:v3 已把 `debug_break` 从 "range only" 演化到 "range + role"。v4 加 class 是同一模式的第三次扩展 —— 复用 env 层的正交叠加范式,不引入新机制。

---

## 1. 契约现状 recap(避免设计悬空)

### 1.1 v3 已落地(commits `79c1c8c..c84bcbd`)

```python
# path2/debug_ctx.py
def debug_break(i: int, *, role: str) -> None:
    if not _DEBUG_MODE: return          # 生产零成本
    r = _read_range()
    if r is None: return                 # DEBUG_BAR_RANGE 未设 = 不停
    if not (r[0] <= i <= r[1]): return   # 范围外 skip
    required = _read_role()
    if required is not None and required != role: return
    try:
        import pydevd
        pydevd.settrace(suspend=True)
    except ImportError:
        breakpoint()
```

**三个 env**:`DEBUG_MODE`(启动读一次 · 生产总闸)· `DEBUG_BAR_RANGE`(每次现读 · 范围)· `DEBUG_ROLE`(每次现读 · role)。

**5 处埋点(仅 throwback.py)**:
| 位置 | role |
|---|---|
| `_emit_tb_gate` 内 L104 | `'gate'` |
| phase1 success L163 | `'trough'` |
| phase2 rise end L216 | `'end'` |
| phase2 timeout end L221 | `'end'` |
| attempt entry L247 | `'entry'` |

**入口 A brush**(view.ts:513)硬编码 `role='gate'`;入口 D marker 右键(view.ts:553)`anchor.key ∈ {entry, trough, end}` 直接透传为 role。

**handler**(`api.py:198 get_diagnose`):`if role:` 才写 `DEBUG_ROLE` env(空串 = 不写);`finally` 无条件 pop `DEBUG_BAR_RANGE` + `DEBUG_ROLE`。

### 1.1.5 术语泛化的既成事实(rev2 新增 · 承 frontend_ux §2)

v3 引入的 `DEBUG_ROLE` 名字虽从 topology role id 借来,**实际承载语义已是"anchor kind"**:

| 入口 | frontend 供给 role 字面量 | 语义 |
|---|---|---|
| 入口 A brush | 硬编码 `'gate'` | anchor kind = detector 失败判据位置 |
| 入口 D marker 右键 | `anchor.key ∈ {'entry', 'trough', 'end'}` | anchor kind = detector 成功事件的锚点位置 |

**topology role id** 是 `PatternSpec.NodeSpec.node_id`(如 `'first_drought'` / `'tb'`)· 一个 class_id 可被多个 topology role 复用(theoretical · 当前 spec 恰无);

**anchor kind** 是"某个 detector 内部特定的 attempt entry / phase-success bar / gate 失败点"的 5-elements enum。

**今天 tb 是单 topology role · 单 class · 两者字面偶然相等 · 没暴露漂移**。未来一个 detector 若在多 topology role 里共享 · 或多个 role 语义各异 · v3 spec §12 的 anchor.key ≡ role 简单映射就崩了。

**v4 不做名字重构**(改动面大 · 收益低)· 但 **rev2 建议 backend spec 显式标 anchor.key = "detector anchor kind" · topology role id 不参与 debug 门限**。这条 clarification 已算入 rev2 交付。

### 1.2 `event_class` 目前只做序列化过滤(用户诉求的根源)

`api.py:245` 把 `event_class` 塞进 `Query`,`diagnose.py:200 _class_ok` 用它过滤 `gate_failures` **serialize 阶段**:

```python
def _class_ok(gf: GateFailure) -> bool:
    return query.event_class is None or gf.class_id == query.event_class
```

**这不 gate `debug_break`**。detector 是无差别跑完的,`debug_break` 该 fire 都 fire —— 用户 filter 到 `tb` 时,`bo`/`burst` 未来若加 `debug_break('gate')`,仍会命中(v3 的 `role='gate'` 匹配同名 role,不区分 class)。

**用户 pain 精确定位**:v3 role gate 把 tb 内部 4 处 role 隔开了,但没把跨 detector 的同名 role 隔开。future-proof 靠 class gate。

### 1.3 bo/burst 已有 `on_gate` 但无 `debug_break`

`breakout.py::BODetector.emit`(7 处)+ `BurstDetector.detect`(2 处 chain_break + min_bos_insufficient)全都 `self.on_gate(GateFailure(...))`,zero `debug_break`。当作者按 v3 authoring guide 补埋点时:

```python
# 未来 BODetector.emit L317 no_active_peak_broken 后
if self.on_gate is not None:
    self.on_gate(GateFailure(..., class_id='bo', ...))
debug_break(i, role='gate', class_id='bo')   # ← v4 新增
```

**此刻若不加 class gate**,前端 brush + `role='gate'` 会同时停在 bo/burst/tb 所有 gate,重现"多次 F9 才到 tb"的用户 pain。

---

## 2. Focus 1 · `debug_break` signature 选型

### 2.1 推荐 · Option A · 双 required kwarg

```python
def debug_break(i: int, *, role: str, class_id: str) -> None:
    if not _DEBUG_MODE: return
    r = _read_range()
    if r is None: return
    if not (r[0] <= i <= r[1]): return
    required_role = _read_role()
    if required_role is not None and required_role != role: return
    required_class = _read_class()               # ★ 新增 · mirror _read_role
    if required_class is not None and required_class != class_id: return
    try:
        import pydevd
        pydevd.settrace(suspend=True)
    except ImportError:
        breakpoint()
```

**All-and gate 组合**:三 gate(range / role / class)各自独立 · unset 就 pass · 缺一即停。

**call site 改造**(tb 5 处):
```python
debug_break(gate_idx,   role='gate',   class_id='tb')
debug_break(trough_idx, role='trough', class_id='tb')
debug_break(i - 1,      role='end',    class_id='tb')
debug_break(end_scan,   role='end',    class_id='tb')
debug_break(bo_idx,     role='entry',  class_id='tb')
```

### 2.2 为什么是 A(vs B/C/D)

**Rejected · Option B · 合并 opaque `target: str = "tb.gate"`**
- 拒因 1:破坏正交性。今天 tb.gate,明天用户想"tb 全部 role"或"全部 detector 的 gate",都要在 handler / debug_ctx 里 parse target 字符串,复杂度传导
- 拒因 2:静态可分析性变差。AST 契约测试从 `role='<literal>'` 一段字符串,变成 parse "cls.role" 复合字面量;grep-ability 也降级(想找所有 gate 埋点,不能一 grep 拿全)
- 拒因 3:前端 UI 层从两个正交 selector 强行拼成一个字符串,增负担;错拼字面量 (`"tb.Gate"` vs `"tb.gate"`) 静默 skip,契约锚测试更难写

**Rejected · Option C · 隐式(从 detector context 读)**
- 机制:每 detector 在 `detect()` 入口 `contextvars.ContextVar('current_class_id').set('tb')`,`debug_break` 内部 `.get()`
- 拒因 1:增加隐式状态 · 违反 CLAUDE.md "第一性原理反过度设计"
- 拒因 2:zero 编译期 / 静态分析 attack surface —— 忘 set/reset 静默失效,fallback 到"全 class fire"退化到无
- 拒因 3:contextvar 在 multi-process(scan pool)/ generator(detect 是 iterator)/ pytest fixture 边界的行为都要专门处理,复杂度爆表
- 拒因 4:与 role kwarg 显式 required 的现有纪律不一致,搞混作者心智

**Rejected · Option D · 中央过滤器 list env(`DEBUG_CLASSES="tb,burst"`)**
- 有趣但被用户诉求本身反驳:用户想要的是"单个 class",不是多选;单选特例就是 `DEBUG_EVENT_CLASS="tb"`
- 若未来真需要多选,list env 是 forward-compat 增量(env 值改 CSV,`_read_class` 返 tuple/frozenset,`in` 判定即可),不需要现在预演
- YAGNI:v4 只解决 v3 的一个 pain point,不做超前泛化

**Rejected · Option D' · Hook into detector dispatch**
- 机制:runner 包 `detect()` 迭代,按当前 detector 的 `event_cls.class_id` decide 是否让埋点生效
- 拒因:侵入 dag 引擎层 · 与 debug 无关的代码路径都要扛这个 hook · 违反 CLAUDE.md 严格分层

### 2.3 signature 层 · 一个明确细节:双 required kwarg 抗漏

`role: str` 已是 v3 required kwarg(没 default),`class_id: str` 应完全同规格 · 没 default · 缺 kwarg → TypeError · 编译期即抓。这条纪律与 v3 authoring guide 一脉相承。

**反例(拒)**:`class_id: str = ""` 加 default。默认空串走 v1 兼容 = 不匹配 class,新加埋点忘传 class_id 无声退化 · 全 class fire · 用户 pain 复归。

---

## 3. Focus 2 · Env layout

### 3.1 推荐 · 加 `DEBUG_EVENT_CLASS` 第四个,平级

```python
# path2/debug_ctx.py 新增
def _read_class() -> Optional[str]:
    """读 DEBUG_EVENT_CLASS env · 未设或空串返 None(v3 兼容 fallback:不做 class 匹配)。"""
    c = os.environ.get("DEBUG_EVENT_CLASS")
    return c if c else None
```

Env 全景:
- `DEBUG_MODE`(启动读一次 · 生产总闸 · main.py 消费)
- `DEBUG_BAR_RANGE="lo,hi"`(动态读 · handler 按 start_bar/end_bar 设)
- `DEBUG_ROLE="role"`(动态读 · handler 按 role query 设)
- `DEBUG_EVENT_CLASS="class_id"`(动态读 · handler 按 event_class query 设)★ v4 新增

**bar_range** 是 tuple 语义 · **role** / **class** 都是原子字符串 —— 各占一 env,不需 nest。

### 3.2 为什么不 nest(如 `DEBUG_TARGET="lo,hi;role;class"` 复合)

- Parse 层引脆:分隔符与 role/class 字面量冲突时(colon in class_id 未来某天?)必须转义;转义规则又要文档、又要 pytest
- 现只 3+1=4 个 env,尚未到 refactor 到 JSON payload 的阈值;若未来 >6 个 knob 再考虑
- 与 v2/v3 逐字同构 · 复用现有心智:`handler_write_env → detector_read_env → finally_pop_env` 已成范式,加一列即可
- process-global env 的并发劣势(v3 spec §5 已诚实标注 · single-user debug tool)对 4 个 env vs 3 个 env 没有本质差异,不构成 nest 的理由

### 3.3 为什么 env 而非 request-scoped 状态(如 contextvar)

- 现有 3 env 都靠 process-global,detector 层是"从进程外找 debug 意图" · 复用同一机制
- Async 引入 asyncio 情况下才需换 contextvar/request-scoped(v3 spec §5 R9 已备案);当前 handler 全 sync
- **如果**未来某天引入 async,contextvar 重构应同时改所有 3 个 env,而不是 v4 单点分叉

### 3.4 生命周期硬契约(mirror v3)

handler `finally` 块:
```python
finally:
    os.environ.pop("DEBUG_BAR_RANGE", None)
    os.environ.pop("DEBUG_ROLE", None)
    os.environ.pop("DEBUG_EVENT_CLASS", None)   # ★ v4 新增
```

无条件 pop 三 env(即使本次没写 · 兜底跨 request 污染)。这与 v3 test_finally_pops_debug_role_env_bootstrap_pollution 同样的 preset-then-unset 测试模式适用。

---

## 4. Focus 3 · Migration path · 未来 detector 采纳

### 4.1 Authoring template(v4 版 · 扩 v3 §10)

新 detector 加 `debug_break` 埋点:

```python
# 1. detector 定义 event_cls
class MyEvent(Event):
    class_id = "myclass"

# 2. detector 内每处埋点
debug_break(i, role='gate', class_id='myclass')      # 与 self.event_cls.class_id 严格一致
debug_break(j, role='entry', class_id='myclass')
```

**纪律**(硬约束):
1. `class_id=` kwarg required · str literal (grep-able)
2. `class_id` 字面量 = detector 的 `event_cls.class_id` 字面量 · 单值(单 detector 单 event 类)
3. role 字面量语义自选,可复用 baseline(gate/entry/trough/end)也可自命名(如 platform 的 `lookback_start`)

### 4.2 单 detector · 单 class_id · 硬约束(rev3 收窄 · 承 skeptic C5)

**契约锚测试**(rev3 定稿):`class_id` literal == `detector.event_cls.class_id`。

**rev2 曾提 composite detector 的 forward-compat 讨论 · rev3 收窄删除**。理由:
- v4 spec 只解决 v3 pain point(class 门)· 不为 hypothetical composite detector 预留概念空间
- 与 §6.3 拒绝为 hypothetical 入口 E 松弛 role 硬编码 · 立场统一 · 统一 YAGNI
- 若未来真出现 composite detector(多产事件)· 那时的 debug_break 语义需要重新论证(如"哪段代码归属哪 class"的作者纪律)· 不该在 v4 提前定

**当前铁律**:每个 detector 单产事件(单个 event_cls)· 单 class_id · `debug_break` 里 `class_id` 字面量与 `detector.event_cls.class_id` 严格相等。

### 4.3 Lint / AST test · 反射 `_CLASS_ID_REGISTRY` 消除双源(rev3 承 skeptic C2)

从当前 `test_throwback_debug_roles.py` 拓展 · 一个跨 detector 的通用契约锚测试:

**rev2 曾硬编码 `EXPECTED_CLASS_IDS = {"bo", "burst", "tb", ...}` · rev3 改为反射 `path2/core.py::_CLASS_ID_REGISTRY`**(权威 source · v4 spec 已借它保 Event.class_id 全局唯一):

```python
# tests/path2/test_debug_break_class_contract.py (新增)
import ast, pathlib
from path2.core import _CLASS_ID_REGISTRY

DETECTOR_FILES = list(pathlib.Path("path2/atoms").glob("*.py"))

def _registered_class_ids() -> frozenset[str]:
    """import 触发 Event 子类注册 · 保 registry 完整。"""
    import path2.atoms  # noqa: F401 · 触发所有 atom module 的 __init_subclass__ 注册
    return frozenset(_CLASS_ID_REGISTRY.keys())

def test_every_debug_break_has_class_id_str_literal_in_registry():
    valid = _registered_class_ids()
    for py_file in DETECTOR_FILES:
        tree = ast.parse(py_file.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "debug_break":
                class_kw = next((k for k in node.keywords if k.arg == "class_id"), None)
                assert class_kw is not None, f"{py_file}:{node.lineno} missing class_id kwarg"
                assert isinstance(class_kw.value, ast.Constant) and isinstance(class_kw.value.value, str), (
                    f"{py_file}:{node.lineno} class_id must be str literal for grep-ability"
                )
                assert class_kw.value.value in valid, (
                    f"{py_file}:{node.lineno} class_id={class_kw.value.value!r} not registered in _CLASS_ID_REGISTRY"
                )

def test_throwback_class_id_matches_event_cls_declaration():
    """throwback.py 里所有 debug_break call 的 class_id 字面量 == ThrowbackEvent.class_id."""
    from path2.atoms.throwback import ThrowbackEvent
    expected = ThrowbackEvent.class_id
    tree = ast.parse(pathlib.Path("path2/atoms/throwback.py").read_text())
    ids = [next(k.value.value for k in c.keywords if k.arg == "class_id")
           for c in ast.walk(tree)
           if isinstance(c, ast.Call) and getattr(c.func, "id", None) == "debug_break"]
    assert set(ids) == {expected}, f"tb detector should only mark class_id={expected!r}, got {set(ids)}"
```

**优点**(vs rev2 硬编码):
- 未来加 detector · 注册 `class_id = "new"` 自动进 registry · AST test 不需改
- 每 detector 的特化测试反射 `event_cls.class_id`,不硬编码字符串 · 单 source of truth
- 无双源漂移风险

**分层**:
- 通用测试(all detectors) · 保证 class_id kwarg 存在 + literal + 值在 registered set
- 每 detector 特化测试(仿 `test_throwback_debug_roles.py`) · 验 role + class 分布 Counter 匹配 baseline

未来加新 detector 时,把 baseline Counter 加一列即可。**这条纪律 v4 时就写死,避免每加 detector 都靠 code review 记得**。

### 4.4 沉没成本论 · rev3 修正 · 承 skeptic Round 2 C1

**skeptic Round 2 硬推回 rev2 沉没成本表的算术漏洞**(测试成本被隐藏)· 我具体核实后接受修正:

**rev2 表格错误**:声称"今做 ~10 行 vs 迟做 ~15+ 行" · 但把 ~20 个新测试(~400 行)当"一次写就完"、迟做当"回改开销大"。**skeptic 反驳成立**:
- 测试代码今做 · 迟做**规模基本对称**(都是 20 个测试 ~400 行)
- 迟做时确实需要 revise 现有 5 个 role fire integration test 加第三维参数 + role Counter 改 (role, class) Counter · 但**这不是回改 · 是当次自然增写**(那时正在写 bo detector 的 debug_break · 顺手一起)
- "回改所有 detector 埋点"的说法误导 —— 每 detector +1 kwarg 是新增成本 · 不是回改成本

### 4.4.1 修正后立场 · 收窄到"作者纪律早晚"

真沉没成本对比(rev3 诚实版):

| 项 | v4 今做 | 迟到 bo/burst 埋点当天再做 |
|---|---|---|
| 核心代码(debug_ctx + api + tb 5 处) | ~10 行今做 | 同 ~10 行迟做 |
| 20 个新测试 | 今做 ~400 行 | 迟做也 ~400 行 (bo/burst 埋点 PR 内一起写) |
| Marginal per-detector 后续 | +1 kwarg / 埋点 (统一纪律) | +1 kwarg / 埋点 (同) |
| **总成本** | **基本对称** | **基本对称** |

**真差别**(rev3 保留的论据):
- **纪律建立时机**:v4 今做 · v3 authoring guide 立刻扩为"role + class_id 都 required kwarg" · 未来 bo/burst 埋点作者写的每一个 debug_break 天然带 class_id
- **纪律迟做**:v4 只有 role required · bo/burst 埋点作者可能不知要带 class_id · 靠 code review 抓
- **纪律成本差异**:大概 5-10 行 authoring guide 文档改 + 1 次 review nag 成本 · **不到 rev2 声称的量级**

### 4.4.2 skeptic 的核心反驳 · 抬到 leader 决策

skeptic Round 2 counter 的**新论点**(rev2 未回):

> "随需增建更保护未来知道正确形态——你今天设计的 class 门可能不适合 bo 实际的埋点需求(比如 bo 有 7 处 gate,细粒度需求会不同)"

**这是"预建 vs 随需增建"的哲学分歧,不是算术分歧**:

- **预建论(我原立场)**:v3 authoring guide 已确立 role kwarg 纪律 · 加 class_id kwarg 是同规格延续 · 让未来 detector 从第一行就正确 · 用户 pain 已被前端 UX brainstorm(frontend_ux draft)确认真实场景
- **随需增建论(skeptic 立场)**:今天为零收益 · 未来 bo 实际形态不明 · 现在锁死 class_id 粒度可能过粗(未来可能要 event_id 粒度、gate_name 粒度、bar-range subset 粒度等)· 等真需要再选具体粒度更清晰

**我 backend 视角**:
- class 粒度 vs event_id/gate_name 更细粒度:v4 加 class_id kwarg **不阻碍**未来加 event_id / gate_name · 因为 class_id 是**必然**属性(每个 debug_break 归属某 detector · detector 归属某 class) · 而 event_id / gate_name 是**该属性内部**的更细粒度
- 若未来发现要 event_id 门 · 加 `DEBUG_EVENT_ID` env 是**又一维**(orthogonal) · 不需回退 class_id 层
- 所以 class 门是**foundational 层** · event_id 是可选加层 · **不冲突**

**但**这个反驳需要 leader 拍板 · **backend 不能单独裁决"哲学"分歧**。**rev3 抬到 §15 leader 待决**。

### 4.4.3 结论(rev3 收敛)

- rev2 沉没成本"3× 差异"论**撤回**
- 保留"纪律建立时机"轻量论据(v3 role guide + class_id 是同规格延续)
- "预建 vs 随需增建"是 leader 哲学分歧 · §15 显式列出 · 我 backend 倾向预建但接受 leader judgment call

---

## 5. Focus 4 · "全部" 语义

### 5.1 推荐 · Mirror v3 role 的 `if event_class:` 判据

**Handler 写 env**:
```python
if role:
    os.environ["DEBUG_ROLE"] = role
if event_class:                            # ★ v4 新增 · 空串也视同未传
    os.environ["DEBUG_EVENT_CLASS"] = event_class
```

**debug_ctx 读 env**:
```python
def _read_class() -> Optional[str]:
    """未设或空串返 None(v1/v3 兼容 fallback · 不做 class 匹配)。"""
    c = os.environ.get("DEBUG_EVENT_CLASS")
    return c if c else None
```

**debug_break 匹配**:
```python
required_class = _read_class()
if required_class is not None and required_class != class_id: return
```

**语义**:
- 前端 UI 选"全部" · 发 `event_class=` 空串或 omit → handler 不写 env → debug_ctx 视同未设 → 所有 class 都可能 fire(v3 兼容 fallback,与 role 逐字同构)
- 前端选具体 class(如 `"tb"`) → handler 写 `DEBUG_EVENT_CLASS="tb"` → 只 tb 埋点 fire

### 5.2 为什么不用"空串就是全部"作为显式语义

**Rejected · handler 强写 `DEBUG_EVENT_CLASS=""` 表示"全部"**:
- 与 v3 role fallback 逻辑不一致(v3 是"未设或空串"两条 fallback,handler 通过不写实现)
- debug_ctx 层要区分"未设 vs 空串",引入不必要的三态(None / "" / value),Python 惯用二态更清晰
- 空串写 env 触及 subprocess/pool worker 继承时的"父进程有此 env 但值空" corner case · v3 已用"handler 不写 = env 无 → fallback"绕开,v4 沿用

**结论**:handler `if event_class:` 判据 · debug_ctx `_read_class()` 空串也 fallback · 与 v3 `if role:` / `_read_role()` 完全同构。

### 5.3 三态 semantics 对照表

| handler 传入 event_class | env DEBUG_EVENT_CLASS | debug_ctx _read_class() | 匹配语义 |
|---|---|---|---|
| None(未传) | 未设 | None | 不匹配 · 全 class fire |
| `""`(空串) | 未设(if 判据 skip 写) | None | 不匹配 · 全 class fire |
| `"tb"` | `"tb"` | `"tb"` | 严格匹配 · 只 tb fire |

### 5.4 前端实际 traffic · handler skip 分支几乎不走(rev3 承 skeptic C4)

**frontend_ux Round 2 已 concede**"debug 默认 = first-enabled-class"(不是"全部") · pill UI 显示 "🎯 调试焦点: tb"(first-enabled) · URL 发 `event_class=tb`(具体值,非空)。

**这意味着前端实际 traffic 中**:
- 用户切"全部"是**显式选** · 不是 default · 出现频率极低(可能低于 5%)
- 常态 traffic 全带具体 `event_class=<class>` · handler `if event_class:` 恒真 · DEBUG_EVENT_CLASS 恒被写
- §5.3 表的"未传"和"空串"两行在实际 traffic 中几乎不发生

**backend 契约后果**:
- **无变化** · handler 判据 `if event_class:` 仍需(保 curl / legacy / hypothetical UI 演进兼容)
- 但**监控 / 日志 / 观察层期望值应调整**:生产 dev 中若观察到 DEBUG_EVENT_CLASS 从未写,说明前端 UX 演进了(如 pill 强制 first-enabled) · 不代表 bug
- **测试**:单元测试仍需覆盖三态(user-friendly · 保 curl edge case) · 但集成测试的"典型 traffic"应集中在 `event_class=<class>` case

**若 skeptic 追问 "前端永远发具体 · 那 handler 判据是否可 hard-require event_class"**:
- 不 · 保 fallback 是 curl 场景兼容 + 保 frontend UI hypothetical 变动的余量
- 判据成本 = 1 行 if · 保留

### 5.5 前端 UI 休眠(rev3 承 frontend_ux Round 2 · 后端契约影响)

**frontend_ux 已 concede**:pill UI 只在 `debugClassOptions.length > 1` 时显示 · 今天 tb 唯一有 debug_break · pill 休眠为静态标签("🎯 调试焦点: tb(本 pattern 仅 tb 装了 debug 断点)")。

**后端契约影响**:
- **零改动**:前端 pill 休眠 = 前端 UI 决策 · 后端不感知
- **契约 C(has_debug_hooks)提供 `debug_enabled_classes` 数组** · 前端消费此数组 `.length > 1` 判据 · **反向证明契约 C 必须做**(未来 bo/burst 加埋点时 · 后端返 `["tb", "bo"]` · 前端自动激活 pill)
- **backend 视角 endorse**:让作者纪律驱动 UI 激活 · 免除"改 detector 埋点忘改前端 UI 配置"的漂移风险

---

## 6. Focus 5 · Role 与 Class 组合 · 硬编码 role='gate' 是否松弛

### 6.1 现状 · 入口 A brush 硬编码 `role='gate'`

`view.ts:513` 附近前端调用 `getTimeDiagnose(...)` 时 `role='gate'` 是硬编码字面量 · 语义 = "看框选窗口内的 gate 失败"。入口 D marker 右键 anchor.key 直接透传为 role(entry/trough/end)。

### 6.2 用户提出的问题 · "只 tb + 无 role narrowing" 会 fire 4 处 tb 埋点?

不 · 前端入口 A 已硬编码 `role='gate'` · 后端组合是 `role_match(gate) ∧ class_match(tb)` · 只 tb 里的 role='gate' 那一处 fire(即 `_emit_tb_gate` L104)。

**但**:如果未来前端加入口 E(如"只按 class 过滤 · 不指定 role"),role 就得 optional。让我们分析这种可能性:

### 6.3 推荐 · **保持 role 硬编码 'gate'** · 关切在前端不在后端

后端 debug_break 三 gate 已经 all-and 独立可省 · 不需要为此改后端。

**理由**:
- 入口 A brush 的语义就是"框选窗内的失败" = "gate" 失败,不是"入口 entry 也算失败"。这是入口 A 的定义(见 v3 spec §12 "入口 A" 术语定义)
- 若前端未来想要"框选 + 全 role",前端调用 `getTimeDiagnose(..., role='')` 即可(handler `if role:` fallback);后端零改动
- role 硬编码不是"后端约束",是"入口 A 的 UX 语义合同";改这个是前端产品决定,不该后端 backend 一厢情愿松弛

### 6.4 已否决 · 让 role optional 反而更好?

**Rejected**:后端 `role: Optional[str] = None` 让 role 变成"unset 就全 fire",看似灵活,实则:
- 会诱导前端漏写 role · 未来入口 A 若忘 role='gate' 硬编码 · debug_ctx 无 role gate · 所有 role fire · 复归 v2 pain
- 现 required kwarg(v3 authoring guide 条 1)是安全 net;打破它换灵活性不划算
- 前端可以主动传空串实现同效(见 6.3)

### 6.5 组合示例矩阵(供 QA 参考)

前端两入口 + 前端 event_class filter 三 knob 的产出:

| 入口 | frontend 发的 role | frontend 发的 event_class | handler 写 env | 命中埋点(tb detector,单 detector 假设) |
|---|---|---|---|---|
| A brush + 全部 | `"gate"` | `""` | 写 DEBUG_ROLE=gate | 只 tb.gate L104 |
| A brush + tb | `"gate"` | `"tb"` | 写 DEBUG_ROLE=gate + DEBUG_EVENT_CLASS=tb | 只 tb.gate L104(同上) |
| A brush + burst(hypothetical) | `"gate"` | `"burst"` | 写 DEBUG_ROLE=gate + DEBUG_EVENT_CLASS=burst | 只 burst detector 的 role='gate' 埋点(未来加) |
| D marker + tb.entry | `"entry"` | `"tb"` | 写 DEBUG_ROLE=entry + DEBUG_EVENT_CLASS=tb | 只 tb.entry L247 |
| D marker + tb.trough | `"trough"` | `"tb"` | 写 DEBUG_ROLE=trough + DEBUG_EVENT_CLASS=tb | 只 tb.trough L163 |
| 未来入口 · 只 class | `""` | `"tb"` | 只写 DEBUG_EVENT_CLASS=tb | tb 5 处全 fire(role fallback all) |
| curl 无任何 gate | `""`/omit | `""`/omit | 都不写 | 全 fire(v1 兼容) |

**Key observation**:入口 A + tb 语义与入口 A + 全部,在只有 tb detector 有 gate 埋点的今天完全等价 · 但未来 bo/burst 加 gate 埋点后,前者只停 tb.gate,后者停三个 detector 的所有 gate · **这就是用户诉求 3(scaling)的真实体现**。

---

## 7. Focus 6 · 测试契约

### 7.1 推荐扩展方案

**分三层测试**(与 v3 test 结构对齐):

#### 7.1.1 单元 · `test_debug_ctx.py` 扩

添加 class gate 的 8-10 个测试(mirror v3 role gate):
```python
def test_class_env_unset_fires_any_class(fresh_debug_ctx, fire_counter, monkeypatch):
    monkeypatch.setenv("DEBUG_BAR_RANGE", "100,200")
    # DEBUG_EVENT_CLASS 未设
    fresh_debug_ctx.debug_break(150, role="gate", class_id="tb")
    fresh_debug_ctx.debug_break(150, role="gate", class_id="bo")
    assert len(fire_counter) == 2

def test_class_env_tb_only_tb_fires(fresh_debug_ctx, fire_counter, monkeypatch):
    monkeypatch.setenv("DEBUG_BAR_RANGE", "100,200")
    monkeypatch.setenv("DEBUG_EVENT_CLASS", "tb")
    fresh_debug_ctx.debug_break(150, role="gate", class_id="tb")   # fire
    fresh_debug_ctx.debug_break(150, role="gate", class_id="bo")   # skip
    assert len(fire_counter) == 1

def test_class_env_empty_fallback(fresh_debug_ctx, fire_counter, monkeypatch):
    monkeypatch.setenv("DEBUG_BAR_RANGE", "100,200")
    monkeypatch.setenv("DEBUG_EVENT_CLASS", "")
    fresh_debug_ctx.debug_break(150, role="gate", class_id="tb")
    fresh_debug_ctx.debug_break(150, role="gate", class_id="bo")
    assert len(fire_counter) == 2   # 空串 = fallback = all fire

def test_class_id_kwarg_required_typeerror(fresh_debug_ctx):
    with pytest.raises(TypeError, match="class_id"):
        fresh_debug_ctx.debug_break(150, role="gate")   # missing class_id

def test_role_and_class_both_match_fires(...):    # 双 gate all-and
def test_role_match_class_mismatch_skips(...):    # 短路验证
def test_role_mismatch_class_match_skips(...):    # 对偶
def test_all_three_gates_match_fires(...):        # range + role + class
```

#### 7.1.2 契约锚 · `test_throwback_debug_roles.py` 扩 + 新加通用测试

**Extend existing**:role Counter 已有 · 加 class_id Counter · 加 (role, class_id) tuple Counter:
```python
EXPECTED_ROLE_CLASS_COUNTER = Counter({
    ("gate", "tb"): 1,
    ("trough", "tb"): 1,
    ("end", "tb"): 2,
    ("entry", "tb"): 1,
})

def test_throwback_role_class_distribution_matches_baseline():
    calls = _collect_debug_break_calls()
    pairs = [
        (next(k.value.value for k in c.keywords if k.arg == "role"),
         next(k.value.value for k in c.keywords if k.arg == "class_id"))
        for c in calls
    ]
    assert Counter(pairs) == EXPECTED_ROLE_CLASS_COUNTER
```

**Add generic**:见 §4.3 的 `test_debug_break_class_contract.py`。

#### 7.1.3 集成 · `test_diagnose_role_integration.py` 扩

添加 class fire recorder + 4 组合场景(2x2 role x class):
```python
@pytest.fixture
def fire_recorder(monkeypatch):
    hits: list[tuple[int, str, str]] = []
    def wrapped(i: int, *, role: str, class_id: str) -> None:
        # 复刻 real debug_break 判据
        if not dc._DEBUG_MODE: return
        r = dc._read_range()
        if r is None: return
        if not (r[0] <= i <= r[1]): return
        required_role = dc._read_role()
        if required_role is not None and required_role != role: return
        required_class = dc._read_class()
        if required_class is not None and required_class != class_id: return
        hits.append((i, role, class_id))
    monkeypatch.setattr(dc, "debug_break", wrapped)
    monkeypatch.setattr("path2.atoms.throwback.debug_break", wrapped)
    return hits

def test_class_tb_only_tb_fires(client, fire_recorder):
    r = client.get(_url(role="gate", event_class="tb"))
    assert r.status_code == 200
    classes = {c for _, _, c in fire_recorder}
    assert classes <= {"tb"}   # 允许空(数据没触发)· 若非空必须 == tb

def test_class_burst_no_tb_fires_yet_but_no_regression(client, fire_recorder):
    """v4 引入前 burst 没埋点 · 此测试预留 · 加了 burst debug_break 后即改 assert 精确"""
    r = client.get(_url(role="gate", event_class="burst"))
    assert r.status_code == 200
    # 当前 · burst 未埋 debug_break · classes 应为空(tb 也不 fire 因为 class 不匹配)
    classes = {c for _, _, c in fire_recorder}
    assert "tb" not in classes   # ★ 反证 · 证明 class gate 起作用了

def test_no_class_v1_compat_all_classes_fire(client, fire_recorder):
    r = client.get(_url(role="gate", event_class=None))
    # 无 class filter · 走 v1 兼容 · tb 埋点应 fire
    ...
```

#### 7.1.4 handler env 测试 · `test_diagnose_role_env.py` 扩

添加与 role env 对偶的 class env 测试:
```python
def test_class_query_writes_debug_event_class_env_during_request(...)
def test_no_class_query_does_not_write_debug_event_class_env(...)
def test_empty_class_query_does_not_write_debug_event_class_env(...)
def test_finally_pops_all_three_envs_on_success(...)
def test_finally_pops_debug_event_class_bootstrap_pollution(...)
```

### 7.2 test scope 完整表(regression 防御)

| 测试类别 | 文件 | v3 已有 | v4 需增 |
|---|---|---|---|
| debug_ctx 单元(gate 组合) | test_debug_ctx.py | role 8 测 | +class 8 测 + 4 组合测 |
| detector 埋点契约锚 | test_throwback_debug_roles.py | role Counter | +class Counter + (role,class) Counter |
| detector 埋点通用契约 | test_debug_break_class_contract.py | 不存在 | 新加 · 跨 atoms 静态验证 |
| handler env 生命周期 | test_diagnose_role_env.py | role env 5 测 | +class env 5 测 |
| 集成 · pydevd counter | test_diagnose_role_integration.py | role fire 5 测 | +class fire 4 测 |

**总增量**:约 20 个新测试;沿 v3 模板 · 每个 <20 行 · 无新概念。

---

## 8. Focus 7 · Backend caching · rev2 重写 · 与 class 门正交 · 独立 refactor

### 8.1 rev1 论证的修正 · 承 skeptic P2 观察

**rev1 §8 拒 cache 的具体论证是**"cache 优化 display 直接破坏 debug"。该论证在 skeptic §4.3 的 cache key 规格(`key = (symbol, start, end, pattern_id, spec_hash)` · **不含** event_class)下**成立** —— cache hit 时 detector 不跑 · debug pause 不发生 · debug 破坏。

**但 frontend_ux §2.5 提出的 cache key 规格**(`key = symbol+start+end+pattern_id+spec_hash+event_class+start_bar+end_bar` · **含** event_class + bar range)**改变分析**:
- filter 变 = key 变 = cache miss = 重跑 = 允许 pause · 与用户 UX 直觉一致(改 filter = 显式换调查目标)
- 同 filter + 同区间 + 反复 brush 相同区间 = key 同 = cache hit = 无重跑 = 无 pause · 满足 skeptic 的 root smell 拔除

**修正后立场**:cache 与 class 门是**正交增量** · 可以同做:
- Cache 减少同参数重复请求的 CPU / debug pause 冗余(用户重复 brush 或界面自动 refetch)
- Class 门减少单次请求内的 pause 次数(用户选 tb · 一次 brush 只停 tb 埋点)

### 8.2 事实核实 · skeptic P2 观察准确

**skeptic §4.1 引用的链路是真实的**(rev2 grep 证实 · 见 §1.2):

- `DetailSidebar.vue:362-366` `onTimeEventClassChange`:filter 变即 `view.triggerTimeQuery(frame[0], frame[1], v)`
- `view.ts:509` `triggerTimeQuery` 发 `/diagnose scope=time&start_bar=...&end_bar=...&event_class=...`
- `api.py:212-215` handler 顶部 `if start_bar/end_bar: os.environ["DEBUG_BAR_RANGE"] = ...; if role: os.environ["DEBUG_ROLE"] = role`
- `api.py:236-241` `attach_and_collect` + `_dag_analyze_engine` + `detach` · 每次都跑

**用户 pain 溯源**:filter 变 → 后端重跑 detector → 若 debug_break 埋点在窗口内 · fire pause · resume N 次才回到 UI。今天只 tb 有埋点 · 未来 bo/burst 加 · pause 次数放大。

### 8.3 若做 cache · 具体规格(承 frontend_ux §2.5)

**Cache key**:`(symbol, start, end, pattern_id, spec_hash, event_class, start_bar, end_bar, role)`

**Cache 层级**:handler 内 `functools.lru_cache` 或手写 dict + LRU=16 · per-process · config PUT 时显式 `.clear()`。

**Cache 语义**:
- key 完全一致 = cache hit = 直接返 cached response · **不写 env · 不跑 detector · 无 pause**
- key 任一字段变化 = cache miss = 走 handler 原逻辑(写 env · 跑 detector · 可能 pause)· 结果存 cache

**关键 · cache hit 时 handler 顶部的 env 写入怎么办**:

**rev3 定稿 · 选项 X · cache hit 严格 skip detector + skip 写 env**(承 frontend_ux Round 2 pydevd bug 提醒):

frontend_ux 观察到 `debug_ctx.py:56-57` doc 明说 `pydevd.settrace(suspend=True)` **每次都 fire** —— 若 cache hit 仍走 handler 顶部写 env + 走 detector 路径 · debug_break 会命中 · pydevd 会 pause · **cache 就完全失效**(所谓"hit"根本没兑现)。

**rev3 严格 spec**:
```python
def get_diagnose(...):
    # 1. 先构造 cache key(不写任何 env)
    cache_key = (symbol, start, end, pattern_id, spec_hash,
                 event_class, start_bar, end_bar, role)
    if cache_key in _cache:
        return _cache[cache_key]   # ★ cache hit · 直接返 · 不写 env · 不跑 detector · zero side effect

    # 2. cache miss · 才走原路径(写 env + attach_and_collect + analyze + detach)
    if start_bar is not None and end_bar is not None:
        os.environ["DEBUG_BAR_RANGE"] = f"{start_bar},{end_bar}"
    if role:
        os.environ["DEBUG_ROLE"] = role
    if event_class:
        os.environ["DEBUG_EVENT_CLASS"] = event_class
    try:
        ...
        response = build_response(...)
        _cache[cache_key] = response
        return response
    finally:
        os.environ.pop("DEBUG_BAR_RANGE", None)
        os.environ.pop("DEBUG_ROLE", None)
        os.environ.pop("DEBUG_EVENT_CLASS", None)
```

**优点**:
- Cache hit 完全零副作用 · pydevd 不 fire · 语义干净兑现
- Handler 结构清晰(先 cache · 后 detector)
- Finally pop 只在 miss 路径执行 · 与写 env 对偶

**已否决 · 选项 Y · cache hit 仍写 env**:
- 语义错(pydevd 每次都 fire · cache 假装"hit"但断点还 pause · 直接违反 cache 目标)
- rev2 曾提"选项 Y 语义不干净但 handler 结构少改" · **rev3 因 pydevd 硬事实撤回选项 Y**

### 8.4 Cache 与 class 门的优先级 · 由 leader 定

**都做的场景**(未来 bo/burst 埋点后):
- 用户第一次 brush [200,300] + filter=tb:cache miss · 写 3 env · detector 全跑 · 只 tb.gate 埋点 fire · 用户看 tb.gate 断点
- 用户切 filter 到 bo:key 变 · cache miss · 写 3 env(DEBUG_EVENT_CLASS=bo)· detector 全跑 · 只 bo.gate 埋点 fire · 用户看 bo.gate 断点
- 用户 undo · 切 filter 回 tb:key = 原 · cache hit · 无重跑 · 展示原 tb 结果 · 无 pause · **root smell 拔除**
- 用户改 brush 区间 [200,400] + filter=tb:key 变 · cache miss · 新 brush 触发新 debug session

**只做 class 门 · 不做 cache 场景**:
- v4 落 class 门增量(~10 行)· cache 留下一 PR · zero breaking
- 用户 pain 已比 v3 显著缓解(切 filter 时只 fire 用户选中 class · 未来 bo/burst 埋点后不再噪声炸)
- "重跑"本身仍在但只是 CPU 成本(单股 <100ms 可接受)

**推荐**:class 门 P0(bo/burst 埋点后不能没)· cache P1(是 UX 优化 · 优先级 leader 定)· 两者独立 task · plan 可拆两 task 分别 subagent-driven。

### 8.5 client-side display cache 是否仍需

frontend_ux rev2 已接"filter 变 = 显式重新 debug 意图 · cache 是优化层 · filter 是语义层" · 意思是**前端不做 client-side cache** · 后端 handler cache 是唯一层。

**backend 视角 endorse**:client-side cache 与 backend cache 语义可能漂 · 单一 cache 层易维护 · 且 handler cache 命中判据由后端权威。

---

## 9. Focus 8 · Integration test 演进最小集

### 9.1 现状

`test_diagnose_role_integration.py` 5 个测试断言 `roles_fired == {'gate'}` 等 · assert role-purity。

### 9.2 推荐扩展 · 加 class-purity + 组合矩阵

**Minimum regression-preventing set**(4+ 新测试):

```python
# 1. class-purity 主线
def test_class_tb_only_tb_fires(client, fire_recorder):
    r = client.get(_url(role=None, event_class="tb"))
    classes = {c for _, _, c in fire_recorder}
    assert classes <= {"tb"}

# 2. class + role 组合(用户主诉场景 · 入口 A brush + tb filter)
def test_role_gate_class_tb_only_tb_gate_fires(client, fire_recorder):
    r = client.get(_url(role="gate", event_class="tb"))
    pairs = {(role, cls) for _, role, cls in fire_recorder}
    assert pairs <= {("gate", "tb")}

# 3. class filter 隔离 hypothetical 未来 detector(v4 之后加 bo/burst debug_break 时改精确)
def test_class_bo_no_tb_fires(client, fire_recorder):
    r = client.get(_url(role="gate", event_class="bo"))
    classes = {c for _, _, c in fire_recorder}
    assert "tb" not in classes   # tb detector 的 debug_break 不 fire · class gate 起作用

# 4. 三 gate 全设 · 兼容 curl 场景
def test_no_gates_v1_compat_all_fire(client, fire_recorder):
    r = client.get(_url(role=None, event_class=None))
    classes = {c for _, _, c in fire_recorder}
    assert "tb" in classes   # v1 兼容 · tb 至少 fire(TSLA 2025 数据几乎必有 bo 触发)
```

### 9.3 未来加 bo/burst debug_break 时的测试演进

当作者按 authoring guide 给 bo/burst 加 `debug_break(x, role='gate', class_id='bo')` 后:

- Test 3 要改为 `assert "bo" in classes` (精确断言) — 会自动 fail 当前 test suite,提醒作者补测
- 加一个 `test_class_bo_only_bo_fires` mirror test_class_tb_only_tb_fires
- 加一个组合矩阵测试:`test_role_gate_class_burst_only_burst_gate_fires`

**长期 · 契约**:每加一个新 detector 的 debug_break 埋点,integration test 加一组 (n+1) 测试。规模化下每 detector 4-5 测试。

---

## 10. 总结 · 与 v3 spec 的关系

v4 完全是 v3 的**平行叠加** · zero 新概念:

| 层 | v3 状态 | v4 增量 |
|---|---|---|
| 生产总闸 | `DEBUG_MODE` | 不变 |
| 范围 gate | `DEBUG_BAR_RANGE` | 不变 |
| Role gate | `DEBUG_ROLE` + `_read_role` + role kwarg | 不变 |
| Class gate | 不存在 | 新加 `DEBUG_EVENT_CLASS` + `_read_class` + `class_id` kwarg |
| handler 写 env | `if role:` | +`if event_class:` |
| handler pop env | 两 env `finally` pop | 三 env `finally` pop |
| 前端 role 供给 | 入口 A 硬编 gate / 入口 D anchor.key | 不变(前端 event_class 传参归 frontend_ux) |
| 契约锚测试 | role Counter | +class_id Counter + (role, class_id) Counter + 跨 detector 通用测试 |
| 集成测试 | roles_fired 断言 | +classes_fired 断言 + 组合矩阵 |

**总 backend 代码增量**:
- `debug_ctx.py` +4 行(`_read_class` 函数 + 2 行 gate 判据)
- `throwback.py` +5 处 `class_id='tb'` kwarg(每处 +1 kwarg)
- `api.py` +2 行(handler 写 env 判据 + finally pop)
- 测试 ~20 个新测试(每个 <20 行)

**契约兼容性**:
- v1 curl(不传 role / event_class):完全兼容 · 全 fire
- v3 curl(传 role 不传 event_class):完全兼容 · 只匹配 role 的 fire · 不做 class 过滤
- v4 UI 新姿势(传 event_class):新增能力 · 精确 gate

---

## 11. 未来演进 · 前置考虑

### 11.1 若 class gate 数量爆炸(>10 detector)

现设计单选 · 若用户想"多选(tb+bo)":
- forward-compat 增量:`DEBUG_EVENT_CLASS="tb,bo"` CSV · `_read_class` 返 `frozenset` · debug_break `if required_class is not None and class_id not in required_class` · 变 in 判定
- Handler 层不改(直接透传字符串)
- 前端 UI 层加 checkbox multi-select
- **零 signature 破坏 · 不影响现有单选场景**

### 11.2 若加"排除 class"语义(如"看除 tb 外的所有")

- `DEBUG_EVENT_CLASS="!tb"` · debug_break 判据 `startswith('!')` 反转
- 前端 UI 层加 "排除" 复选框
- **本轮不做,YAGNI**

### 11.3 若引入 async / 并发 debug

- v3 spec §5 R9 已备案 · 三 env 一起 refactor 到 request-scoped(contextvar)
- v4 加的 `DEBUG_EVENT_CLASS` 沿用同一 refactor 路径 · 不产生额外债

---

## 12. 契约不变量(供 spec 与 plan 引用)

1. **`debug_break` signature 硬约束**:`(i, *, role: str, class_id: str)` · 两 kwarg 都 required · 无 default
2. **`class_id` 字面量约束**:必须 str literal · grep-able · 值 ∈ registered class_id set(靠 `test_debug_break_class_contract.py` 抓)
3. **单 detector class_id 单值**:一个 detector 内所有 `debug_break` 的 `class_id` 相等 · 且 == detector 的 `event_cls.class_id` (未来 composite detector 除外 · 需 spec 显式论证)
4. **handler finally pop 三 env** · 无条件 · 保跨 request 隔离
5. **debug_ctx 三 gate all-and 短路**:range → role → class 顺序 · 任一失败即返 · 全部匹配才 fire
6. **v1 / v3 兼容 fallback**:env 未设或空串一律视同"不过滤" · 全 fire · 保 curl / legacy 测试
7. **前端 event_class 空串或 omit == 全部**:handler `if event_class:` 判据 · 与 v3 role 同规格

---

## 13. 待 peer review 的开放问题

### 13.1 契约 C · `debug_enabled_classes` · rev3 从"可选"升为 v4 必需(承 frontend_ux Round 2)

**frontend_ux Round 2 揭露 anchorsOf fallback 的 latent bug**:frontend_ux 原方案用 `DEBUG_ENABLED_CLASSES = anchorsOf 键去 _default`(view.ts:63)做"有 debug_break 埋点"的 fallback · **这是语义偷换** —— `anchorsOf` 原语义是"入口 D marker 右键的 anchor 计算表"、不是"detector 有没有 debug_break"。今天 tb 两者重合是巧合 · 未来 detector 埋 debug_break 但没在 anchorsOf 定义(如某 detector 只支持入口 A brush、不支持入口 D right-click)→ UI pill 选不到但断点会触发 → 用户 pain。

**rev3 升级**:`has_debug_hooks` flag 从"rev2 可选"升为"v4 必需"。理由 = 前端 fallback 是 bug · 后端必须给权威 source。

---


**问题**:frontend_ux `debugClassOptions` computed 需知道"哪些 class 有 debug_break 埋点" · 目前靠前端 `DEBUG_ENABLED_CLASSES` 硬编码(view.ts:63)· 后端硬编码 detector 埋点 · 两侧存在漂移风险(后端加 gate 前端忘补 · 用户选不到)。

**推荐 · Detector 类上加 `has_debug_hooks: ClassVar[bool] = False` 静态声明**:

```python
# throwback.py::ThrowbackDetector
class ThrowbackDetector:
    event_cls = ThrowbackEvent
    on_gate = None
    has_debug_hooks = True   # ★ v4 · 作者显式声明埋了 debug_break

# breakout.py::BODetector (未加埋点)
class BODetector(BarwiseDetector):
    event_cls = BOEvent
    on_gate = None
    has_debug_hooks = False   # ★ 显式声明未埋 · 默认继承 False
```

**serialize_pattern 消费**:
```python
# path2_web/serialize.py::serialize_pattern
def serialize_pattern(spec) -> dict:
    ...
    debug_enabled_classes = sorted({
        node.detector.event_cls.class_id
        for node in spec.nodes
        if getattr(node.detector, 'has_debug_hooks', False)
    })
    return {..., "debug_enabled_classes": debug_enabled_classes}
```

**契约**:
- 作者纪律:埋 `debug_break` 时必须同时把 detector class 的 `has_debug_hooks = True`(与埋点同一 diff)
- Lint 兜底:AST test 静态扫 detector 文件 · 有 `debug_break` call 但类上 `has_debug_hooks != True` → test fail(防漂移)

**vs 静态 grep 判据(备选 · rejected)**:每次 serialize 时静态 grep detector 源文件 · 简单但慢(serialize 高频)· 且没显式作者声明契约

**priority**:frontend_ux §3.5 说"倾向后期做" · 我建议**同 v4 一起做**(增量小 · 免除未来漂移风险)。若 leader 觉得多余 · 可延后 · 前端硬编码 + 约定同步。

### 13.2 命名定稿 · `DEBUG_EVENT_CLASS`(rev3 承 frontend_ux Round 2 接受)

frontend_ux Round 2 明确接受 backend 命名 · 理由采信我的可读性论据(URL query `event_class` 与 env 字面对齐 · 免 handler 内 mental map)。**v4 定稿采 `DEBUG_EVENT_CLASS`**。

---

## 14. Env → contextvars 长期方向(rev2 新增 · 承 skeptic §5)

**skeptic §5 观点**:env 是 process-global · 并发时 race · 若这轮有余力顺手迁 contextvars。

**backend 部分接受 · 表态**:

### 14.1 v4 不迁 contextvars · 只加第四 env · 具体阻力(rev3 承 skeptic C3)

skeptic Round 2 C3 追问:"本轮已是 breaking window · 顺手迁 contextvar 边际成本近零 · 具体阻力是什么?"

**rev3 明列具体阻力**(而非概括说"独立 refactor"):

1. **测试 fixture 全改**:v3 已 landed 的 `test_debug_ctx.py` 用 `monkeypatch.setenv("DEBUG_ROLE", ...)` 模式(fresh_debug_ctx + fire_counter fixture · 15 个测试)· 迁 contextvars 需改为 `token = _role.set("gate"); ...; _role.reset(token)` · 每 fixture / 每测试都要改。**估算**:15 个测试 × 每个 ~5 行改动 = ~75 行测试代码 refactor
2. **v3 authoring guide 已 landed**:spec §6.2 里的"用 monkeypatch stub pydevd.settrace 为计数器"是既定测试模板 · 迁 contextvars 后模板要重写 · 未来 detector 作者的心智模型要重训
3. **integration test `test_diagnose_role_integration.py`**:5 个测试的 `_read_range()/_read_role()` reimport + env 覆盖 pattern 全改
4. **breaking window 边际成本近零 = 部分真**:v4 已改 debug_break signature(加 class_id kwarg) · handler 加一行 env write · 但 contextvars 迁移动的是**读端 + 生命周期管理**,与 signature 增 kwarg 是**不同层面** · 混做增加 review 难度 · 用户不容易分辨"哪个改动引入了 regression"

5. **v3 spec 里承诺的 "handler `finally` 无条件 pop 三 env" 契约**:contextvars 版本变成"reset(token)"而非 env pop · v3 spec §12 的 contract #7 术语需重定义 · docs 同步

**净判断**:
- 阻力总量 ~75 行测试改 + 15 行核心 + spec/docs 改 = ~100 行 refactor · 中等 blast radius
- vs 单纯 class 门 ~10 核心 + ~400 测试新增(new · 不 refactor)
- 混做增量总规模翻倍 · leader 若 revert 需要区分"是 class 门有问题还是 contextvars 迁移有问题" · 定位成本高

**给 leader 的具体建议**:
- **P0 · v4 只加第四 env**(与 v3 三 env 一致 · finally pop · 单 commit)
- **P1 · v5 独立 spec · 三 env 一起搬 contextvars**(spec 写清 v4→v5 迁移 · 一次到位)
- **若 leader 判断此项 blast radius 可接受 · 也可 v4 顺手迁**(我 backend 不推荐但接受)

### 14.2 contextvars 迁移应作为 v5 独立 spec · 三 env 一起搬

**统一形态**(未来 v5 参考):
```python
# path2/debug_ctx.py (v5)
import contextvars

_bar_range: contextvars.ContextVar[Optional[tuple[int, int]]] = contextvars.ContextVar(
    "debug_bar_range", default=None
)
_role: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "debug_role", default=None
)
_event_class: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "debug_event_class", default=None
)

def debug_break(i: int, *, role: str, class_id: str) -> None:
    if not _DEBUG_MODE: return
    r = _bar_range.get()
    if r is None or not (r[0] <= i <= r[1]): return
    required_role = _role.get()
    if required_role is not None and required_role != role: return
    required_class = _event_class.get()
    if required_class is not None and required_class != class_id: return
    # fire

# handler (v5)
async def get_diagnose(...):
    tokens = []
    if start_bar/end_bar: tokens.append(_bar_range.set((start_bar, end_bar)))
    if role: tokens.append(_role.set(role))
    if event_class: tokens.append(_event_class.set(event_class))
    try:
        ...
    finally:
        for t in tokens: t.var.reset(t)
```

**优点**:
- async / concurrent handler 天然隔离(每 request 自己 context)
- ProcessPool worker 需显式 copy_context 才继承 · 不再意外污染
- reset() 精准恢复上次值 · finally pop 简化

**缺点**:
- 需修改单元测试(monkeypatch env 变成 set/reset context) · fixture 全改
- 与 v3 前的 curl 场景兼容性变化(curl 不发 web 请求 · 不进 handler · 就没 context · context.get() 默认 None · 仍全 fire · **实际兼容**)

### 14.3 v4 与 v5 的兼容性

**v4 环境变量 · v5 contextvars** 是**替换**(不是叠加)。v4 → v5 迁移 = 一次性重构:
- 所有 `os.environ.get(...)` 换成 `.get()` context var
- 所有 handler `os.environ["..."] = ...` 换成 `.set(...)` 拿 token · finally reset(token)
- 单元测试 fixture 从 `monkeypatch.setenv` 换 context var set

**v4 加第四 env 不增加 v5 迁移成本** —— 因为 v5 迁移是 wholesale replacement · 一次改三 env 与一次改四 env 复杂度基本同。

---

## 15. rev3 · leader 待决清单(收敛后)

三人 Round 2 后 · 收敛 3 项 · 保留 5 项 leader 决策。**加粗为 rev3 新增或修正**:

### 15.0 已收敛(rev3 无争议)

- **命名**:`DEBUG_EVENT_CLASS`(frontend_ux Round 2 接受 backend 立场)
- **契约 C 必需性**:`has_debug_hooks: ClassVar[bool]` flag 是 v4 必需(frontend_ux Round 2 揭 anchorsOf fallback bug · rev3 §13.1 升级)
- **AST test 反射注册表**:硬枚举 → `_CLASS_ID_REGISTRY`(skeptic C2 有理 · rev3 §4.3 落地)
- **cache-hit 严格 spec**:cache hit skip detector + skip 写 env(frontend_ux pydevd bug 提醒 · rev3 §8.3 落地)
- **§4.2 composite forward-compat 收窄**:统一 YAGNI 立场(skeptic C5 · rev3 §4.2 落地)
- **前端 UI 休眠**:pill `debugClassOptions.length ≤ 1` 时静态标签(frontend_ux Round 2 concede)· 后端契约 zero 变化
- **默认值分二档**:sidebar=全部 / debug=first-enabled-class · **skeptic + frontend_ux 已达成共识**(非 backend"中立"待决 · rev2 §15 项 3 表述已 stale · rev3 移入收敛区)

### 15.1 leader 决策项(rev3)

#### 决策 1 · **预建 vs 随需增建**(核心哲学 · 决定 v4 是否做 class 门)

- **预建论(backend 立场)**:v3 authoring guide 已确立 role kwarg 纪律 · v4 加 class_id kwarg 是同规格延续 · 未来 bo/burst 埋点作者天然带 class_id
- **随需增建论(skeptic 立场)**:今天为零收益(tb 唯一埋点)· 未来 bo 实际形态不明 · 现在锁死 class 粒度可能过粗 · 等真需要再选具体粒度更清晰
- **决策依赖**:bo/burst 埋点距今多远?若下一 sprint 就埋 · 预建明显对;若 3+ sprint 才埋 · 随需增建明显对
- **backend 承认**:rev2 沉没成本"3× 差异"论已撤回(见 §4.4)· 此决策不是算术分歧 · 是哲学分歧 · leader 必须拍
- **对 leader 建议**:如果 leader 手上无 bo/burst roadmap · **默认走随需增建**(skeptic 立场)· 因为"未来知识"总比"预设"值大

#### 决策 2 · Cache 优先级(承 skeptic P2 有效 · frontend_ux hybrid 方案落地)

- Cache 与 class 门是**正交**(rev3 §8 已 aligned 三人共识)· 都可以做
- **backend 立场**:Cache P1(优化) · class 门 P0(bo/burst 埋点后不能没)
- 若并做 · plan 拆两 task 分别 subagent-driven
- **对 leader 建议**:若走"决策 1 随需增建 · 暂不做 class 门" · cache 仍应做(独立优化 · 消除 filter 变即重跑的 pain · 不依赖埋点 roadmap)

#### 决策 3 · contextvars 迁移(承 skeptic C3 · rev3 §14 具体阻力列出)

- **backend 立场**:v5 独立 spec · v4 只加第四 env(具体阻力 ~100 行 refactor · 见 §14.1)
- **skeptic 立场**:本轮 breaking window 顺手 · 边际成本近零
- **对 leader 建议**:若 leader 觉得 ~100 行 refactor blast radius 可接受 · 顺手迁 · 我 backend 不反对 · 只是不推

#### 决策 4 · IDE 条件断点 vs env-based coupling(skeptic §2.1 替代 A)

- **skeptic 精确表述**(rev3 Round 2 澄清):他 §2.1 承认"用户需要打开源码找到行号"这个 pain 是弱论(用户已知行号 · brief 里就出现) · 但 **IDE 条件断点方案本身** 在 speculative pain 场景下 100% apply(PyCharm 条件 `class_id == 'tb'` 一行搞定 · 完美 pinpoint · 零后端成本)
- skeptic Round 2 concede "web UI 单点控制"是独立价值 · IDE 是替代 A 不完全取代 web UI
- **backend 立场**:v4 保留 env-based coupling(web UI 单点控制) · IDE 条件断点是文档化的补充路径(speculative pain 场景下用户可用 PyCharm 条件语言层解决)
- **对 leader 建议**:v4 spec 加一段"IDE 条件断点作为替代路径 · web UI 未激活的场景可回退"文档化 · 零代码成本

#### 决策 5 · rev2 沉没成本论已撤回 · 是否影响 v4 scope

- rev2 §4.4 声称"今做 10 行 vs 迟做 30 行" · rev3 §4.4 撤回(测试成本对称)
- 此撤回意味着 **class 门"迟做"没有比"现在做"贵多少** · 强化 skeptic 随需增建论(决策 1)
- **对 leader 判断**:if 决策 1 走"随需增建" · v4 scope 收窄为:cache(独立 refactor) + IDE 条件断点文档化 + 契约 C `has_debug_hooks` flag(独立 · 前端 pill vocabulary 需要)· class 门推迟到 bo 埋点当天

### 15.2 rev3 后 minimum viable v4(若 leader 走随需增建)

若 leader 判 class 门是 speculative · v4 最小可行范围:
1. **契约 C**:`has_debug_hooks` flag + `serialize_pattern` 返 `debug_enabled_classes` · ~20 行 · 支持前端 pill UI(即使今天 pill 休眠 · 也不会漂移)
2. **cache(可选 · 建议做)**:handler request-hash cache · ~50 行 · 拔"filter 变即重跑"root smell
3. **IDE 条件断点文档化**:v4 spec 加一节"如需 class 精准 · 用 PyCharm 断点条件 `class_id == 'tb'`" · 零代码

**若 leader 走预建**:v4 = 上面 3 项 + class 门(~10 行 + ~400 行测试)· 一次到位。

---

## 16. rev2 与 rev1 的关键区别

| 部分 | rev1 立场 | rev2 立场 |
|---|---|---|
| §8 cache | 拒 · "混淆两目标 · 破坏 debug" | 接受 · 与 class 门正交 · 采 frontend_ux cache key 含 filter 规格 |
| §14 contextvars | 未涉 | 明确 v4 不迁 · v5 独立 refactor · 三 env 一起搬 |
| §2 术语 | 未涉 | 承 frontend_ux 观察 · v3 `DEBUG_ROLE` 事实上承载 "anchor kind" · spec 需显式标 |
| §4.4 沉没成本 | 未涉 | 显式论证今做 vs 迟做代价不对称 · 反 skeptic P3 YAGNI |
| §13 契约 C | 简单提"1 行 class_ids" | 精细化到 detector 类 `has_debug_hooks` flag + lint 兜底 |
| §15 leader 待决 | 隐藏在文中 | 显式清单 · 6 项分歧点 · 一览便决 |
| §11.1 CSV 多选 | 未涉 v4 优先级 | 明确 v4 单选 · CSV 是 v5+ 增量 |

**主体不变**:
- signature Option A(双 required kwarg)· env `DEBUG_EVENT_CLASS`
- handler `if event_class:` mirror role · finally 三 env pop
- role 硬编码 'gate' 保留
- AST 契约锚测试拓 (role, class_id) 二维 Counter + 跨 detector 通用

---

## 17. rev3 与 rev2 的关键区别

| 部分 | rev2 立场 | rev3 立场 |
|---|---|---|
| §4.2 composite forward-compat | 保留概念空间 · 未来 composite spec 显式论证 | 删除 · 硬约束 class_id == event_cls.class_id · 统一 YAGNI |
| §4.3 AST test 允许集 | 硬编码 `EXPECTED_CLASS_IDS = {...}` | 反射 `_CLASS_ID_REGISTRY` · 单 source of truth |
| §4.4 沉没成本论 | 声称"今做 10 行 vs 迟做 30 行" | **撤回 3× 差异算术** · 收窄到"作者纪律早晚建立" · 抬"预建 vs 随需增建"到 leader |
| §5 三态表 | 表格描述完整 | +§5.4 承前端实际 traffic skip 分支几乎不走 · +§5.5 前端 UI 休眠 |
| §8.3 cache-hit spec | 选项 X 推荐 · 选项 Y 缺点是"语义不干净" | 选项 X 严格必需 · 选项 Y **因 pydevd 每次都 fire 硬事实撤回** |
| §13.1 契约 C | rev2 "可选 · 未来打开" | rev3 **升为 v4 必需** · frontend_ux anchorsOf fallback 是 latent bug |
| §13.2 命名 | 分歧未 resolve | frontend_ux Round 2 接受 · 定稿 `DEBUG_EVENT_CLASS` |
| §14 contextvars 阻力 | 概括说"独立 refactor" | 具体列 ~100 行 refactor breakdown · leader 可选 |
| §15 leader 待决 | 6 项分歧 | 3 项收敛 · 5 项 leader 决策 · 加 "预建 vs 随需增建"核心哲学项 · minimum viable v4 两分支明列 |

**主体不变**:
- signature 双 required kwarg(role + class_id)
- env `DEBUG_EVENT_CLASS` 平行叠加 · handler `if event_class:` 判据 · finally 三 env pop
- role 硬编码 'gate' 保留(§6)
- v1/v3 兼容 fallback 保留

---

_rev3 完成 · idle for leader synthesis · Round 2 三人分歧已收敛 6 项 · 剩 4 项抬 leader · 三方 idle 就位 · 无 rev4 触发_

**三方 idle 确认**:
- **backend_debug (self)** · rev3 落定
- **frontend_ux** · rev3 lock · 命名/契约C/cache spec 全 sync · 无 rev4 触发
- **skeptic** · rev3 lock · substantive 修正接受 · 沉没成本论 + contextvars 本轮迁 明确"交 leader 判断题"不再打

**剩 leader 决策**(rev3 §15.1):
1. 预建 vs 随需增建(决定 class 门做/不做 · 依赖 bo/burst 埋点 roadmap)
2. Cache 优先级(backend 建议 P1 · 独立于决策 1)
3. contextvars 迁移(backend 主 v5 独立 · skeptic 反打"两 commit 分开 preserve revert 粒度"是新论点 · leader 可选)
4. IDE 条件断点文档化(v4 spec 加一段 · 零代码)
