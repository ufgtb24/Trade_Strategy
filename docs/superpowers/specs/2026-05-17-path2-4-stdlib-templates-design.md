# Path 2 #4 设计稿:stdlib 常用 Detector 模板 + id 便利(BarwiseDetector / span_id)

> 日期:2026-05-17 · 上游:roadmap #4 · brainstorming 产出
> 范围声明:Path 2 是独立的多级事件表达框架,**与 mining / TPE / 因子框架 / Condition_Ind / BreakoutStrategy 等概念无关**,本设计严禁引入。
> 协议层(`path2/`)+ #3 stdlib PatternDetector(`Chain/Dag/Kof/Neg`)均已冻结;本设计**不改协议层任何字段/类型,不改 #3 任何代码/行为**,只在其上叠两个新符号。
> 决策依据:多轮第一性原理裁定(tom),每条经 adopt/redo gate;关键裁定经硬核查纠正两次(D1 pinned 测试 / §7.4 Kof 代码级核查)。

> **写回横幅(plan 起草期实现核查驱动)**:brainstorming 原裁定「痛点2 = 窗口聚合归 #3 `Kof`」被 plan 阶段对 `Kof` 的代码级核查**证伪**——`Kof` 是 k-of-n **边松弛**(全标签必在场、成员数=label 数恒为编译期常量),**本质无法表达「滑动窗口内 ≥N(动态计数)」**(证据:`_kof_dfs:310/334` 全 label 必赋值 + 各 label 独立扫后缀无单 match 内互斥;`resolve_labels:46-57` 同类流多角色构造期 ValueError;且 Kof 枚举/回溯+全成员非重叠消费 ≠ 旧贪心锚首成员分组)。**红线不变**(#4 不造 `WindowedDetector`/任何贪心计数 detector),但理由已改(见 §3、§8);§7.4 已据此降级(见 §7)。本横幅所述为权威,正文 §3/§7/§8 已同步。

---

## 0. 目标与定位

#4 = stdlib「日常便利层」:在协议层 + #3 PatternDetector 之外,沉淀**有 dogfood 真实证据支撑、高频且易错**的样板。

经狠砍 YAGNI,#4 **净交付 2 个公开符号**:

| 符号 | 类型 | 解决的 dogfood §5 痛点 |
|---|---|---|
| `BarwiseDetector` | `abc.ABC`(`path2/stdlib/templates.py`,新文件) | 痛点1 的下半:逐 bar 扫描主循环样板(`for i in range(...): compute; if cond: yield`) |
| `span_id` | 公开纯函数(`path2/stdlib/_ids.py`,在既有文件新增) | 痛点3:`event_id` 命名编码区间/单点的样板 |

公开出口:二者经 `path2/stdlib/__init__` → `path2/__init__`,与 `Chain/Kof/...` 并列。

**#4 刻意不沉淀任何 Event 类**(理由见 §1)。

---

## 1. Q1 裁定:#4 不沉淀任何 Event 类

备忘清单(qa.md B)曾列 `BarEvent`/`Peak`/`BO`/`VolSpike`/`MACrossOver`。**全部砍**,逐条理由:

- `Peak`/`BO`:命名直指突破选股业务,违反 §0「Path 2 与 BreakoutStrategy 无关」硬约束;其 Path 2 内最小定义无 dogfood 证据。
- `VolSpike`/`MACrossOver`:领域形态,非框架原语,零 dogfood 证据(dogfood 的 `VolSpike` 是脚手架里使用方私有的领域 Event 子类,带私有判据字段 `ratio`)。
- `BarEvent`(经 redo gate 二次审查后亦砍):用「只有 dogfood 真实痛点或显然高频才进」同一把尺,`BarEvent` 没过——dogfood L1 **从未把裸 OHLCV 行物化成通用 bar Event**,而是直接在 `df["volume"]` numpy 上扫描后 yield 带 `ratio` 的领域子类。#4 内**无任何消费者**:`BarwiseDetector` 模板体只调 `emit` 并 yield 其返回值,模板代码不构造/不引用任何 Event 类;用户 `emit` 返回的是自己的领域 Event 子类;下游 `run()`/`Kof` 只要求协议层 `Event` 基类。`BarEvent` 落在「通用到无人用、专用到不存在」的空档。

**第一性原理收尾**:协议层 `core.Event` 已是通用 frozen row 基类,`.features` 已自动覆盖任意子类的 int/float 标量字段(排除 bool);用户真实 L1 事件**总是带使用方私有的领域判据字段**,这类按定义无法被 stdlib 预先沉淀。故 `.features` 默认实现无需在 #4 补充(Q4 的一半;反驳 roadmap 列项,协议层默认已正确)。

---

## 2. Q2 裁定:不引入 `DataSource` 协议

协议层 `Detector.detect(source: Any)` + `run(detector, *source)` 的 `Any` 瘦核是经 dogfood 验证的已决策。`BarwiseDetector` 直接吃 `pd.DataFrame`(L1 模板的天然输入);L2 / 跨层聚合由 #3 PatternDetector 吃 `Iterable[Event]`。**协议层零改动**,不为想象中的「多数据源」造抽象。

---

## 3. Q3 裁定:仅 `BarwiseDetector`;窗口聚合归 #3 `Kof`(红线)

备忘清单曾列 `Barwise/Threshold/FSM/Windowed`:

- `BarwiseDetector`:**进**。对应 dogfood 主体扫描样板,唯一同时满足「真实证据 + 高频 + 易错 + 未被 #3 覆盖」。
- `ThresholdDetector`:砍。阈值穿越是 `BarwiseDetector.emit` 内一行领域判据的退化特例,不值独立类。
- `FSMDetector` / `WindowedDetector`:砍,零 dogfood 证据。

**红线(实现期最大风险,spec 显式封死)**:#4 **严禁**重造任何窗口/聚合/滑动计数原语(`WindowedDetector`、贪心 cluster detector 等)。**理由(经 plan 期 Kof 核查修正)**:dogfood 痛点2「窗口内 ≥N 个」是**滑动动态计数**,#3 `Kof` 是 k-of-n 边松弛(成员数恒=label 数),**并不覆盖**它(详见写回横幅);该滑动计数样板**目前无足够复用证据进 stdlib**——dogfood 仅一次出现,使用方暂自管(如 dogfood 脚手架 `VolClusterDetector` 的做法),待 #5/#7 出现真实重复再立类。红线不依赖任何「已被某 Detector 覆盖」的声明,故更稳:#4 只做「逐 bar 单点」这一层,前瞻/窗口/聚合一律不进 #4。

### 3.1 `BarwiseDetector` 精确契约(D2 钉死)

```python
import abc
from typing import Iterator, Optional
import pandas as pd
from path2.core import Event


class BarwiseDetector(abc.ABC):
    """逐 bar 单点扫描模板。用户子类只实现领域判据 emit,模板拥有扫描主循环。

    与协议层协作:run(MyDet(), df) → detect(df) → 逐 i 调 emit → 流式 yield。
    模板对 i 零领域假设,不做任何跨事件校验(end_idx 升序 / event_id 唯一
    由协议层 run() 负责)。
    """

    @abc.abstractmethod
    def emit(self, df: pd.DataFrame, i: int) -> Optional[Event]:
        """检视第 i 根 bar。命中返回用户自己的 Event 子类实例,否则 None。

        lookback 由领域子类自管:不够 lookback 时 `return None`
        (例:`if i < self.LOOKBACK: return None`)。
        event_id 由子类在此自行生成(可用 path2.span_id 便利)。
        """
        ...

    def detect(self, df: pd.DataFrame) -> Iterator[Event]:
        for i in range(len(df)):
            ev = self.emit(df, i)
            if ev is not None:
                yield ev
```

裁定要点(第一性原理,均经 gate):

- **lookback 不进模板契约**:lookback 大小是领域知识(20 日均量是 VolSpike 判据,不是扫描框架属性)。模板暴露 `warmup: int` 会把领域参数焊进框架契约并引入隐式契约,属过度设计。主循环固定 `range(len(df))`,lookback 由用户在 `emit` 里 `return None` 跳过(一行,零歧义)。模板对 `i` 零假设 = 真正零领域假设。
- **模板不碰 event_id**:`kind` 前缀(`vs`/`vc`)是领域命名,模板无从知晓;代填必须猜 kind 或强加格式,破坏零领域假设。用户在 `emit` 里用 `span_id("vs", i, i)`(D1 提供的便利,非强制)。
- **模板零跨事件校验**:`end_idx` 升序 / `event_id` 单 run 唯一全部留协议层 `run()`(`runner.py` 已确认做这两项)。模板做校验 = 与 `run()` 重复且二义。模板只做 `for + emit + None 过滤`。
- **协议兼容**:类有 `detect(source)`,结构兼容 `Detector` Protocol;协议层零改动。

---

## 4. Q4 / D1 裁定:`span_id` 公开纯函数 + `default_event_id` 原样不动

### 4.1 现状

`path2/stdlib/_ids.py` 现有 `default_event_id(kind, start_idx, end_idx) -> f"{kind}_{start_idx}_{end_idx}"`(恒区间,不塌缩),被 `_advance.py:121` 用于构造 #3 `PatternMatch` 的 id;`tests/path2/stdlib/test_ids.py:5/9` 已 **pinned** 其语义,其中 `:9` 显式钉死 `default_event_id("vc",5,5) == "vc_5_5"`(s==e 非塌缩)。

### 4.2 裁定:两函数并存,语义刻意不同(经 redo gate 纠正)

初版「`default_event_id = span_id` 薄别名」方案**已被 `test_ids.py:9` pinned 测试硬证伪**(别名会让该断言变 `vc_5` 而 break,且 #3 已主动锁定 s==e 非塌缩语义)。定稿:

- `default_event_id`:**一字节不改**,实现保持 `f"{k}_{s}_{e}"`。#3 PatternDetector 内部专用(其 `PatternMatch` 跨成员 span 概念上恒区间,s==e 亦输出 `kind_s_e`)。**不进公开出口**(`path2/__init__` 不暴露它),公开面只一个 id 函数。
- `span_id`:**全新独立公开函数**,单点塌缩:

```python
def span_id(kind: str, start_idx: int, end_idx: int) -> str:
    """单点(start==end)→ f"{kind}_{start}";区间 → f"{kind}_{start}_{end}"。"""
    return f"{kind}_{start_idx}" if start_idx == end_idx else f"{kind}_{start_idx}_{end_idx}"
```

  签名刻意与 `default_event_id` 一致;一个函数吸收 dogfood 两种真实惯例(`vs_{i}` / `vc_{s}_{e}`),无 mode 开关、无第二参数(奥卡姆)。

### 4.3 `_ids.py` docstring 须钉死的定性(消歧)

> `default_event_id` = #3 PatternDetector 专用,跨成员 span 恒区间、s==e 亦输出 `kind_s_e`,**不对外暴露**;`span_id` = #4 单点/区间事件公开便利,s==e 塌缩 `kind_i`。二者语义不同、刻意不统一、互不依赖。原「#4 替换本桩」预期经 #4 设计核查作废——#3 已用 pinned 测试主动锁定区间语义,#3/#4 id 语义本质不同,无可共享单一桩;记此句溯源,防未来误归一。

### 4.4 奥卡姆论证(为何两个 id 函数不是过度设计)

剃刀砍无谓实体,不砍数量。两个 id 语义是 #3 用 pinned 测试**主动锁定**的客观事实(#3 标跨成员 span 恒区间;#4 标本质单点 bar),非 #4 引入。归一必丢语义:塌缩 break #3;不塌缩则 #4 单点带冗余尾(`vs_34_34`)、无法表达 dogfood 惯例;`collapse: bool` flag 技术上能归一却把两语义塞一函数靠 flag 分叉,认知负担更高且默认值必坑一类调用方——那才是过度设计。实体数 = 必要语义数 = 奥卡姆正解。

---

## 5. Q5 裁定:runtime check 生产默认 — 出 #4 范围

spec §7.2(d)「runtime check 生产环境是否默认关闭」:机制已在协议层(`config.RUNTIME_CHECKS` + env `PATH2_RUNTIME_CHECKS` + `set_runtime_checks()`),**默认值策略与 #4 的 Event/Detector 便利层正交**。判定**出 #4 范围**,归 roadmap #7(Path 2 自有下游流水线,远期)。#4 不动 `config`,防 scope 蔓延。

---

## 6. #4 推荐骨架

```
path2/stdlib/
  templates.py      ← 新文件:BarwiseDetector(abc.ABC)
  _ids.py           ← 既有文件:default_event_id 原样不动 + 新增 span_id + 改 docstring(§4.3)
  __init__.py       ← 出口加 BarwiseDetector, span_id
path2/__init__.py   ← 出口加 BarwiseDetector, span_id(与 Chain/Kof 并列)
```

公开 API 净增:`path2.BarwiseDetector`、`path2.span_id`(2 个符号)。协议层 / #3 代码 **零改动**。#4 **不沉淀任何 Event 类**。

边界:#4 ⊂ stdlib「日常便利层」,只做「逐 bar 单点扫描」+「id 便利」;前瞻/窗口/聚合 = #3 PatternDetector;schema/不变式/run = 协议层。

---

## 7. 验证设计(D3 钉死)

#4 无新业务语义,**最强验证 = 对 dogfood 已 pin 死的旧行为做等价改写**(老 idx 是金标准,比造新形态更强的回归证据)。项 1–3 + §7.4(拆 A/B),缺一不可:

1. **样板消除(核心)**:用 `BarwiseDetector` 重写 dogfood 的 `VolSpikeDetector`,重写后子类体**只剩 `emit` 内领域判据**(`ratio = vol[i]/mean(...); return VolSpike(...) if ratio>2 else None` + `if i<LOOKBACK: return None`),**不得出现** `for i in range(...)` 主循环。「重写后子类不含显式扫描循环」作为可检收口判据——直接证明吃掉痛点1 样板循环。
2. **行为逐事件等价(核心)**:重写版经 `run()` 驱动,产出与 dogfood pin 死的 11 个 idx `[34,60,61,67,97,130,176,194,264,265,267]` 及各自 `ratio` **逐字段相等**。复用已提交 fixture `tests/path2/fixtures/aapl_vol_slice.csv`,确定可复现。
3. **`span_id` 契约 + #3 零回归**:对照单测钉死「刻意不同」为可检契约:
   ```python
   assert default_event_id("vc", 5, 5) == "vc_5_5"   # #3 内部:span 恒区间(已 pin)
   assert span_id("vc", 5, 5)          == "vc_5"      # #4 公开:单点塌缩
   assert span_id("vc", 60, 67)        == "vc_60_67"  # #4 公开:区间
   ```
   且 `_ids.py` 改动后 **#3 现有 156 测试全过**(证明 `default_event_id` 一字节不改、对 #3 零行为变更)。
**§7.4 端到端串联 #3(经 plan 期 Kof 核查拆 A/B)**:

- **§7.4-A(核心,充分)**:即上述项 1+2——L1 逐事件 pin 死 11 idx + 子类无显式循环。这已**充分**证明 #4 的真实价值命题(模板吃掉痛点1 样板循环 + 行为保真);§7.4-A 单独成立即 #4 验证下限。
- **§7.4-B(补充,降级为诚实 pin)**:验证「#4 模板产出能经 `run()` 喂给 #3 PatternDetector + `run()` 链式贯通」。**不复刻** dogfood 旧贪心 2 簇——`Kof` 是 k-of-n 边松弛(全标签必在场、成员数恒=label 数),**本质无法表达滑动「窗口内 ≥N」**(写回横幅;#3 设计权威:Kof「全标签必在场 no partial」)。故 §7.4-B 取**诚实 pin**:用一个 #3 PatternDetector(`Chain`,最简:声明 spike→spike 一条 `TemporalEdge`、`max_gap` 取定值,经 key/具名流把 L1 spike 流接入)消费 #4 重写版的 L1 流,**单验证任务两步**——步骤1 首次运行得真实产出 `G_real`(`[(pm.start_idx, pm.end_idx, len(pm.children)), ...]`),步骤2 **同一任务内**把 `G_real` 回填为字面量断言并固化(**不留 TODO / 不留占位**;plan 把"先跑得真值再于同任务回填"写成显式两步)。验证目标仅:链式 `run(#3Det, run(BarwiseRewrite(), df))` 不抛、产出非空且 end_idx 升序、event_id 唯一(协议层不变式真实贯通)。

> §7.4-B 用 `Chain` 而非 `Kof`/`Neg`:`Chain` 是表达「两个 spike 有时间先后 + gap 约束」的最简 #3 消费者,足以证「#4 产出能喂 #3」;不追求复刻任何旧业务分组(诚实原则:复现即真,不强行等于旧贪心)。`Chain` 单边的精确 `edges`/标签接入由 plan 依 `Chain.__init__` 与 `resolve_labels` 实情写死。

不需要新形态/新数据/新 dogfood(会引入无关变量)。痛点2 红线由 §3(理由已修正)单独封死,不依赖 §7.4-B。

---

## 8. 最大设计风险

实现期被诱导造滑动窗口/贪心计数原语(`WindowedDetector`、cluster detector 等)。**§3 红线**(理由已修正为「无足够复用证据进 stdlib,使用方自管,待 #5/#7」,不依赖任何 Detector 覆盖声明)单独封死:plan 阶段不得新增任何窗口/聚合/计数类,#4 只交付 `BarwiseDetector` + `span_id`。次要风险:§7.4-B 误被写成「强行复刻 dogfood 2 簇」——已降级为诚实 pin `Chain` 真实产出(§7),plan 必须照 A/B 拆分实现。

---

## 9. 工作模式

按 roadmap §4:走完整 brainstorm→spec→plan→subagent-driven,独立 worktree。设计阶段每问派 tom(已完成,本稿即产出);plan 阶段同。
