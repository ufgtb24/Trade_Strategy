# Path 2 Dogfood 验证 — 设计稿

> 日期:2026-05-16
> 状态:已通过用户分节审批,待用户审阅本稿 → 转 writing-plans
> 上游:`docs/research/path2_roadmap.md` #1(经验闸门);`docs/research/path2_spec.md` §9.3;`.claude/docs/modules/path2.md`

## 0. 目标

用一个**完全自包含的两级形态**对 Path 2 协议层做端到端 dogfood,验证框架在真实数据上的贴合度。
这是 roadmap 的**经验闸门**:其"框架贴合度痛点"产出决定后续 #3(stdlib PatternDetector)/ #4(stdlib 模板)的形态与优先级。

边界(沿用项目约束):Path 2 是独立业务,dogfood **不引入** mining/TPE/因子框架;形态仅吃 `df.volume`,零领域辅助函数。

## 1. 范围与产出物

三样产出:

1. **代码改动**:`path2/core.py` 的 `Event.__post_init__` 增 bool-as-idx 卫语 + 回归测试。
   一并把 spec §9.3 / `.claude/docs/modules/path2.md` 的 bool 条目从"知情保留"改写为"已决议:显式拒绝"。
   (这是 §9.3 单项决议,**不等于** roadmap #2 的 §9 全量并入。)
2. **验证报告** `docs/research/path2_dogfood_report.md`:形态/数据;L1→L2 跑通情况;
   **哪些协议层不变式被真实行使且真的成立/真的拦截**;嵌入 AAPL 标注图;
   **框架贴合度痛点**(喂给 #3/#4 的核心交付);bool-as-idx 结论。
3. **确定性回归测试** `tests/path2/test_dogfood_integration.py`:固定 AAPL slice,
   断言精确簇结果 + run() 跨事件不变式真实通过。

**关键边界**:dogfood 的 `VolSpike`/`VolCluster`/两个 Detector 是**验证脚手架,不是 stdlib**
(Chain/Dag/Kof/Neg 那些归 #3/#4)。定义放 `tests/path2/`,**不进 `path2/` 包**。

## 2. 组件与数据流

```
df(AAPL slice).volume
   │  run(VolSpikeDetector(), df)
   ▼
VolSpike 流    L1;字段 ratio: float;volume[i] / rolling20mean(volume) > 2.0 触发;start_idx = end_idx = i
   │  run(VolClusterDetector(), spikes)         # L1→L2,行使 detect(stream) 形态
   ▼
VolCluster 流  L2;字段 count: int、span_bars: int;窗口内 ≥3 个 VolSpike 成簇
   │  Pattern.all(谓词…) 过滤
   ▼
matched clusters ──→ 叠加到 AAPL price + volume 图
```

### 2.1 两个事件(定义在 `tests/path2/` 的一个可被 import 的共享模块,供集成测试与图脚本共用)

- `VolSpike(Event)`:`ratio: float`。单 bar 事件,`start_idx = end_idx = i`,`event_id = f"vs_{i}"`。
- `VolCluster(Event)`:`count: int`、`span_bars: int`。`start_idx = 首成员.start_idx`、
  `end_idx = 末成员.end_idx`,`event_id = f"vc_{start_idx}_{end_idx}"`。

### 2.2 两个检测器

- `VolSpikeDetector.detect(df)`:`i` 从 20 起,`ratio = df.volume[i] / df.volume[i-20:i].mean()`,
  `ratio > 2.0` 则 yield `VolSpike`。
- `VolClusterDetector.detect(spikes)`:消费 **VolSpike 流**(非 df),行使 L2 `detect(stream)` 形态。

### 2.3 L2 成簇规则(确定性、非重叠贪心)

左→右扫 spike 流;当存在 3 个 spike 落在 ≤ W bar(**W = 10**)的窗口内,发射一个 cluster =
恰好那批成员,然后从**末成员之后**继续扫。
非重叠贪心保证 `end_idx` 单调升 + `event_id` 唯一 —— 这正是让 `run()` 跨事件不变式
被**真实行使且真实成立**的关键(不是人为构造,而是真实数据自然满足)。

### 2.4 图生成

报告内嵌的 AAPL 标注图由一次性脚本 `scripts/path2_dogfood_chart.py` 生成
(import `tests/path2/` 的 dogfood 检测器,跑同一 slice,matplotlib 叠加
价格 + volume + VolSpike/VolCluster 标注,存 PNG 到 `docs/research/`)。
保留脚本是为报告可复现,不进 `path2/` 包。

### 2.5 刻意行使的协议层面

| 协议层面 | 如何被行使 |
|---|---|
| `Event` 子类 + frozen + `__post_init__` 不变式 | 真实数据;真实可能遇到 NaN volume → 验证 NaN 卫语真实触发/真实不触发 |
| `Detector` 的 `detect(stream)` 形态 | L2 消费 L1 流而非 df |
| `run()` 链式驱动 + 跨事件不变式(end_idx 升序 / event_id 唯一) | 真实流上真实不触发 |
| `Any` / 窗口算子 + `Pattern.all` 组合 | 在 cluster 上写过滤谓词 |

## 3. bool-as-idx 代码改动

`path2/core.py`,`Event.__post_init__` 内、现有 int 类型卫语**之后**:

```python
if type(self.start_idx) is bool or type(self.end_idx) is bool:
    raise TypeError("start_idx/end_idx 不能是 bool(bool ⊂ int,语义错误)")
```

用 `type(x) is bool` 而非 `isinstance`:`isinstance(True, int)` 为真,只有精确类型判定
能在不破坏 int 卫语的前提下拒 bool。受 `config.RUNTIME_CHECKS` 门控(与同函数其余卫语一致)。

理由对齐既有先例:`features` 属性已用 `not isinstance(v, bool)` 排除 bool —— idx 同理,
`start_idx=True` 当 1 用几乎总是 bug,构造点拦截定位最准。

**配套文档同改**(属本改动一部分):

- `docs/research/path2_spec.md` §9.3:"知情保留" → "已决议:显式拒绝"
- `.claude/docs/modules/path2.md` "已知局限" bool 条:改为已拒绝
- 本设计稿:记录决策

## 4. 测试

- `tests/path2/test_event.py` 增 2 个:
  - `Event(start_idx=True, end_idx=1, ...)` → raise `TypeError`
  - `Event(start_idx=0, end_idx=False, ...)` → raise `TypeError`(`False == 0` 同属语义错)
- `tests/path2/test_dogfood_integration.py`:固定 AAPL 日期区间切片(几百根 bar,跑得快),
  `run()` 链式两级,断言精确簇数 + 成员 idx + run() 不变式无异常。
- 全量 `uv run pytest tests/path2/ -q`;既有 50 测试零回归。

## 5. 错误处理

dogfood 用真实数据。若某 bar `volume` 为 NaN → 协议层 NaN 卫语应在 `VolSpike` 构造点抛错。
**不绕过**:报告如实记录"是否真实遇到 NaN / 卫语是否真实拦截" —— 这本身就是验证信号。

## 6. 非目标(YAGNI)

- 不写 stdlib PatternDetector(Chain/Dag/Kof/Neg)—— 归 #3。
- 不做 spec §9 全量并入 —— 归 #2,本稿只决议 §9.3 单项。
- 不引入第二个标的 / 多形态 —— 单标的单形态足以做经验闸门。
- 不把 dogfood 代码沉淀进 `path2/` 包 —— 它是脚手架。
