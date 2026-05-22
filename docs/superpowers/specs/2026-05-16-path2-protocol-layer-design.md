# Path 2 协议层实现设计稿

> **日期**:2026-05-16
> **范围**:第一个开发周期 —— **仅协议层**(`path2_spec.md` v0.1 §1–§6)
> **状态**:brainstorming 产出,已逐节用户认可,待用户终审 → 转 writing-plans
> **上游**:`docs/research/path2_spec.md` v0.1、`path2_tutorial.md`、`path2_api_reference.md`、`path2_qa.md`
> **独立业务**:Path 2 与 `BreakoutStrategy/` 因子框架无依赖关系,不涉及 mining/TPE/因子框架概念

---

## 决策记录(brainstorming 阶段确定)

| 决策 | 选择 | 理由 |
|---|---|---|
| MVP 边界 | **仅协议层**(spec §1–§6),无 stdlib、无 DSL | spec"瘦核心"哲学;tutorial 例 1–6 仅靠协议层即可跑通,是可用最小闭环 |
| runtime check 默认 | **默认全开,可全局关** | 协议层 MVP 阶段安全网 > 性能;调试期尽早暴露错误 |
| 包位置 | 新建独立顶层包 `path2/` | 独立业务,不进 `BreakoutStrategy/` |
| `df` 访问 | 闭包捕获(算子保持纯函数,不引 `DataSource` 协议) | 与 tutorial 6 例一致 |
| `features` | 默认实现放 base class | spec §1.1.4 允许;dataclass 字段内省成本低 |
| 测试 | TDD + pytest | superpowers `test-driven-development` |

---

## 1. 架构与包布局

`path2/` 独立顶层包,无第三方依赖(仅 stdlib `dataclasses`/`typing`/`math`/`os`)。

```
path2/
  __init__.py      # 公开 API 唯一出口:Event, Detector, TemporalEdge,
                    #   Before, At, After, Over, Any, Pattern, run, config
  core.py          # Event 基类 + Detector(Protocol) + TemporalEdge
  operators.py     # Before/At/After/Over/Any + Pattern.all(纯函数/纯组合)
  runner.py        # run(detector, *source):薄包装,跨事件检查
  config.py        # RUNTIME_CHECKS 开关 + 环境变量覆盖

tests/path2/
  test_event.py        test_detector_protocol.py   test_temporal_edge.py
  test_operators.py    test_pattern.py             test_runner.py
  test_config.py       test_invariants.py
```

**分层职责**:

| 文件 | 职责 | 检查归属 |
|---|---|---|
| `core.py` | 类型定义 + **单事件**不变式 | `__post_init__`(frozen 强制、start≤end、start≥0、NaN 扫描) |
| `runner.py` | 流式驱动 + **跨事件**不变式 | yield `end_idx` 升序、`event_id` 单 run 唯一 |
| `operators.py` | 5 算子 + `Pattern.all` | 无(纯函数零状态) |
| `config.py` | 全局开关 | 被 `core`/`runner` 读取,关掉走 fast-path |

**4 源文件而非 7**:`Detector` 仅几行 `Protocol`、`TemporalEdge` 仅 4 字段 dataclass,单独成文件是仪式;三者同属"核心类型层",`core.py` 内聚合理(遵循 CLAUDE.md"反对过度设计")。

---

## 2. 核心类型详细设计(`core.py`)

### 2.1 `Event` 基类

```python
@dataclass(frozen=True)
class Event(ABC):
    event_id: str
    start_idx: int
    end_idx: int

    def __post_init__(self):
        if not config.RUNTIME_CHECKS:
            return
        # frozen 一致性由 @dataclass 在装饰期原生强制(非 frozen 子类继承 frozen
        # Event 会在类定义时即抛 TypeError),无需在此自检。
        if not isinstance(self.start_idx, int) or not isinstance(self.end_idx, int):
            raise TypeError("start_idx/end_idx 必须是 int")
        if self.start_idx < 0 or self.start_idx > self.end_idx:
            raise ValueError(f"非法区间 [{self.start_idx},{self.end_idx}]")
        for f in dataclasses.fields(self):
            v = getattr(self, f.name)
            if isinstance(v, float) and math.isnan(v):
                raise ValueError(f"字段 {f.name} 为 NaN — 违反'Row 落地=字段完成'")

    @property
    def features(self) -> Mapping[str, float]:
        return {f.name: getattr(self, f.name)
                for f in dataclasses.fields(self)
                if isinstance(getattr(self, f.name), (int, float))
                and not isinstance(getattr(self, f.name), bool)}
```

**子类契约**:子类若自定义 `__post_init__`,**必须** `super().__post_init__()`(dataclass 继承已知约束,文档明写)。`children`/`parent` 不在基类声明(spec §1.1.5 可选约定字段);其升序/时序约束 spec §5.2 明列"不必报错",**MVP 不强制**。

### 2.2 `Detector` 协议

```python
@runtime_checkable
class Detector(Protocol):
    def detect(self, source: Any) -> Iterator[Event]: ...
```

纯结构协议,自身不强制;yield 升序 / `event_id` 唯一在 `runner.run()`。

### 2.3 `TemporalEdge`

```python
@dataclass(frozen=True)
class TemporalEdge:
    earlier: str
    later: str
    min_gap: int = 0
    max_gap: float = math.inf

    def __post_init__(self):
        if config.RUNTIME_CHECKS and (self.min_gap < 0 or self.min_gap > self.max_gap):
            raise ValueError(f"非法 gap 区间 [{self.min_gap},{self.max_gap}]")
```

gap 公式(spec §1.3.1):`gap = later.start_idx - earlier.end_idx`。

### 2.4 spec 偏差(诚实标注,作为 v0.2 反馈)

| # | spec 原文 | 实际实现 | 原因 |
|---|---|---|---|
| ① | §5.1:frozen 检查由协议层代码在 `__init_subclass__` 抛 `TypeError` | **不写任何自定义 frozen 检查** —— 由 Python `@dataclass` 在**装饰期**原生强制 | plan 阶段实测(2026-05-16):非 frozen 子类继承 frozen `Event` 在**类定义时**即被 Python 抛 `TypeError: cannot inherit non-frozen dataclass from a frozen one`,更早更强;原 design 稿设想的"移到 `__post_init__` 自检"经实测为**不可达死代码**(唯一进入路径是完全不加 `@dataclass` 的纯子类,而它继承 `Event` 的 `frozen=True` 而判定通过)。用户已批准删除该死分支(commit `0ecb053`);spec §5.1 frozen 行应在 v0.2 重写为"由 Python `@dataclass` 原生强制,非协议层自检" |
| ② | §1.3:`max_gap: int = math.inf` | `max_gap: float = math.inf` | `math.inf` 是 float,`int` 注解类型不自洽 |

两处属 spec v0.1"等待 plan 验证"正中靶心的反馈,plan 阶段应回写 spec v0.2。偏差① 已在 Task 3 实现中按用户决策落地(删除死代码 + 行为测试改为验证 Python 原生强制)。

---

## 3. `runner.run()` 跨事件检查 + 数据流

### 3.1 `run()` 实现

```python
def run(detector: Detector, *source) -> Iterator[Event]:
    """推荐的 Detector 驱动入口。流式 yield,顺带做跨事件检查。"""
    gen = detector.detect(*source)
    if not config.RUNTIME_CHECKS:
        yield from gen
        return
    last_end = None
    seen_ids: set[str] = set()
    for ev in gen:
        if not isinstance(ev, Event):
            raise TypeError(f"Detector 必须 yield Event,得到 {type(ev).__name__}")
        if last_end is not None and ev.end_idx < last_end:
            raise ValueError(f"yield 违反 end_idx 升序:{ev.end_idx} < {last_end}")
        if ev.event_id in seen_ids:
            raise ValueError(f"event_id 单 run 内重复:{ev.event_id}")
        last_end = ev.end_idx
        seen_ids.add(ev.event_id)
        yield ev
```

**设计要点**:

- `*source` 变参转发,支撑 spec §1.2.1 的 L2+ 形态 `detect(event_stream, df)`
- **不物化流**:generator 边跑边查,每事件 O(1),内存只占 `seen_ids` —— 保持 spec §1.2.2 流式
- `end_idx` 升序按 spec §1.2.2 允许等值,仅 `<` 判违规
- `seen_ids` 作用域 = 单次 `run()` 调用,精确对应 spec §1.1.1"单次 run 内唯一"
- checks 关时 `yield from` 直通,零开销

### 3.2 数据流(运行时全景)

```
用户写: class MyDetector  +  class MyEvent(Event)        ← 用户代码
            │
   events = list(run(MyDetector(), df))                  ← run() 驱动
            │   每个 MyEvent 构造时已过 __post_init__ 单事件检查
            │   run() 再叠加 跨事件检查(升序 / id 唯一)
            ▼
   pat = Pattern.all(lambda e: Before(e,...), lambda e: e.x>=θ)   ← 算子+组合子
            │
   matched = [e for e in events if pat(e)]               ← 调用方过滤
            │
   多层: l1=list(run(L1Det(),df)); l2=list(run(L2Det(),l1,df))    ← Detector 串联
```

**两层安全网**:单事件不变式在**构造点**(`__post_init__`,即便不走 `run()` 也生效);跨事件不变式在 **`run()`**。

### 3.3 `run()` 非强制

直接 `list(MyDetector().detect(df))` 仍可用(tutorial 例 1–6 写法),只是少跨事件检查;`run()` 是推荐驱动,不强制(不破坏 tutorial 极简心智模型)。

**文档跟进项(非阻塞,不在第一周期代码范围)**:tutorial/api_reference 例子应在后续文档轮次补充 `run()` 作为推荐驱动的说明。

---

## 4. 错误处理 + `config` 开关

### 4.1 `config.py`

```python
import os

def _env_off(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("0", "false", "off", "no")

RUNTIME_CHECKS: bool = not _env_off("PATH2_RUNTIME_CHECKS")

def set_runtime_checks(enabled: bool) -> None:
    """运行时全局切换(测试 / 生产热关)。"""
    global RUNTIME_CHECKS
    RUNTIME_CHECKS = enabled
```

**两个控制面**:环境变量(进程启动期)+ `set_runtime_checks()`(运行时热切),均全局。

**强制约定**:`core.py`/`runner.py` 必须 `import config` 后用 `config.RUNTIME_CHECKS` 属性访问,**禁止** `from config import RUNTIME_CHECKS`(否则 import 期把值拷死,热切失效)。测试用例覆盖热切生效。

### 4.2 错误处理总表

**必报错(`RUNTIME_CHECKS` 开时)**:

| 违规 | 错误类型 | 抛出位置(本实现) | spec 依据 |
|---|---|---|---|
| 子类非 `frozen` dataclass | `TypeError` | **Python `@dataclass` 装饰期原生强制**(非协议层代码) | §5.1 行1(偏差①:实测 Python 在类定义时即拒绝,无需自检) |
| float 字段 NaN | `ValueError` | `Event.__post_init__` | §5.1 行2 |
| `start_idx>end_idx` 或 `<0` | `ValueError` | `Event.__post_init__` | §5.1 行4 |
| `start/end_idx` 非 int | `TypeError` | `Event.__post_init__` | 本实现补强(类型卫语) |
| yield 非 `Event` 对象 | `TypeError` | `runner.run()` | 本实现补强 |
| yield `end_idx` 非升序 | `ValueError` | `runner.run()` | §5.1 行3 |
| `event_id` 单 run 重复 | `ValueError` | `runner.run()` | §5.1 行5 |
| `TemporalEdge` `min_gap<0` 或 `>max_gap` | `ValueError` | `TemporalEdge.__post_init__` | 本实现补强(spec §5.2 未强制 → 可选增强) |

**不报错 / 行为未定义(MVP 不实现,与 spec §5.2 一致)**:

- 跨 run / 跨 Detector 的 `event_id` 冲突
- `children` 顺序错乱
- `parent.end_idx > self.start_idx`

`RUNTIME_CHECKS` 关时:以上全部不触发,fast-path 零开销。

**补强项定位**:三处"本实现补强"是 spec 未明列但合理的类型/边界卫语,不与 spec 冲突(spec §5 是最小必报集,未禁止补强);一并作为 v0.2 反馈候选。

---

## 5. 测试策略(TDD)

**框架**:pytest,`uv run pytest`。**纪律**:superpowers `test-driven-development` —— 每单元先写测试看 RED,再实现到 GREEN,再 REFACTOR。

**构建顺序(依赖拓扑,逐单元 RED→GREEN)**:

| # | 单元 | 关键测试用例 |
|---|---|---|
| 1 | `config` | 默认 ON;`PATH2_RUNTIME_CHECKS=0/false/off/no` 各变体;`set_runtime_checks()` 热切生效;属性访问语义(改 `config.X` 能传播,验证禁用 `from import` 必要性) |
| 2 | `Event` | 合法构造;非 frozen 子类→`TypeError`;`start>end`/`start<0`→`ValueError`;非 int idx→`TypeError`;float NaN→`ValueError`;`features` 默认提取(含/排除 bool);子类 `__post_init__` 须 `super()`;checks 关时非法事件静默构造 |
| 3 | `TemporalEdge` | 默认值(`min_gap=0`/`max_gap=inf`);`min_gap<0`→`ValueError`;`min_gap>max_gap`→`ValueError`;frozen 可作 dict key(spec §1.3.2);checks 关时绕过 |
| 4 | `Detector`(Protocol) | 结构化鸭子类型:合规类 `isinstance` 通过(`runtime_checkable`),无需继承 |
| 5 | `operators` | Before:idx 形态窗口 `[start-w,start)`、事件流形态、`window=0`→False、anchor 自身排除;At:≡`predicate(anchor)`;After:窗口 `(end,end+w]`、跨流形态、边界排除;Over:6 个 op、list 属性 reduce 习语;Any:至少一个、空→False、默认 predicate |
| 6 | `Pattern.all` | AND;空→True(vacuous);短路;可嵌套 |
| 7 | `runner.run()` | `*source` 多参转发;流式惰性(用"晚抛错 generator"证明未物化);升序强制(等值 OK、递减→`ValueError`);单 run 内 id 唯一;非 Event yield→`TypeError`;checks 关→`yield from` 直通;两次 `run()` 的 `seen_ids` 作用域独立 |
| 8 | `test_invariants` | 端到端:玩具 Detector+Event 经 `run()` → `Pattern.all` 过滤,证明组件可组合;checks 开/关端到端行为差异 |

**覆盖原则**:§5.1 每行 + 每个"补强"行都有先失败的测试;每个算子有边界测试;`config` 热切有专门证明。

---

## 6. 后续周期(超出本设计稿范围,仅备忘)

- stdlib:`ChainPatternDetector`/`DagPatternDetector`/`KofPatternDetector`/`NegPatternDetector`(spec §7.1 已确定必做);常用 Event 类 / Detector 模板(`path2_qa.md` Q1 备忘 B)
- DSL 层(spec §7.2,可选)
- spec v0.2 回写(偏差① ② + 三处补强项)
- tutorial/api_reference 补 `run()` 推荐驱动说明
- 与 `BreakoutStrategy/` 集成边界(spec §7.2)

---

**设计稿结束。**
