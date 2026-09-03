---
name: authoring-path2-detector
description: Use when 用户要创建或修改 event 类 / detector(path2/atoms 公共 atom、app 内自定义、嵌套容器事件、on_gate 接线),或 authoring-path2-app 层②转场至此。纯选型(该用哪个 detector)经入口分诊短路回 app 设计流。
---

# Authoring a path2 Detector / Event

创建或修改 event 类 / detector 的完整工作流,自顶向下:分诊(Step 0)→ 判据设计
确认(Step 1)→ spec 落盘(Step 2)→ 移交 `/implement`(Step 3)→ 验证闸
(Step 4)→ on_gate 接线(Step 5)。每一步与用户确认;本 skill 只做设计与编排、
**不自己写代码**——实现一律移交用户手敲的 `/implement`。

## When to Use / NOT
- **用**:
  - 新建 path2/atoms 公共 atom(新的走势无关子结构)
  - 修改公共 detector(增补字段 / 改判据 / 改语义)
  - app 内自定义 detector(走势特异形状偏见)
  - 事件类结构修改(字段 / child_slots / child())
- **不用**:
  - detector 选型分诊(该用哪个 detector / 约束降到哪层)——归 authoring-path2-app
  - app 拓扑 / 参数 / where 表达(where 构建 = app 范畴,本 skill 只占字段供给面:
    where 要引用的字段怎么设计 / 预计算)——归 authoring-path2-app
  - 诊断已有事件(为什么没生成 / 没 match)——归 diagnose-event

## REQUIRED BACKGROUND(开工先读)
1. 本目录 reference.md(全部六节,自包含)——§1 detector 速查(Step 1 失效边界写法
   参考)/ §2 事件类规范(Step 1 confirm_idx 两问)/ §3 嵌套容器实现(Step 1-2 容器
   设计)/ §4 on_gate 接线(Step 5 四条核对)/ §5 docstring 合同 + 公共库纪律
   (Step 2 合同三要素 / Step 4 regress 义务)/ §6 诊断契约同步(Step 6 义务)
2. 本目录 reference.md §7(引擎侧契约与负知识:身份双轴 / children vs ref_slots / 事件端点 vs 检测过程 / 多流 produces / 负知识清单)
3. `path2/CONTEXT.md`(术语:event/detector/confirm_idx/复合事件 等词的确切含义)——**grep 查词,别整读**

**红线**:凡具体参数值 / 判据阈值 / 字段名,一律现场读代码(`path2/atoms/*.py` /
`path2/core.py`),绝不引用任何文档内嵌快照;reference.md 各节只负责告诉你去读
哪里、问什么问题,使用时仍须现场读代码核对。

## Step 0 分诊(四路)

先判定任务属于哪一路——不是所有任务都走完整流程:

| 路由 | 条件 | 去向 |
|---|---|---|
| 新建公共 atom | 新的物理子结构,≥2 条不相关走势会用 / 单一通用物理事件 | 公共路径(Step 0.5 基线) |
| 修改公共 detector | 现有 atom 增补字段 / 改判据 / 改语义 | 公共路径(Step 0.5 改前基线 + 全引用 app 盘点) |
| app 内自定义 | 走势特异形状偏见(协议允许 app 直接 import) | 不涉公共库 gate,仍走 Step 1-5 |
| 事件类修改 | 只改事件结构(字段 / child_slots / child()),不动判据 | 轻量:Step 1 → 2 → 5(无 regress 全量义务,仍跑引用方测试) |

- 选型分诊不是本 skill 的活:该用哪个 detector / 约束降到哪层(where / 边 /
  字段 / 新 detector)一律先回 authoring-path2-app 分诊
- 边界不清晰的:任务核心是「写 / 改 detector 或事件类」→ 进本 skill;核心是
  app 结构 / 参数 / 选型 → 回 app 设计流

## Step 0.5 公共路径基线(仅公共路径)

改前先摸清影响面并落盘基线,再停下向用户确认:

1. grep 找出全部引用该 detector / atom 的 app(新建场景同样要跑一遍,确认引用
   清单为空——防遗漏既有同名或类似实现)
2. 逐个 `run_eval` 落盘基线(引用清单为空则跳过,留待实现后首次落盘)
3. **公共库 gate**:`AskUserQuestion` 停下向用户确认——公共 atom 影响所有引用
   它的 app,进库 / 修改决定必须用户点头,不得自作主张

## Step 1 判据设计确认(inline, AskUserQuestion)

与用户逐项确认,一项一项问,不批量:

1. **检测什么子结构**(语义对位):这个 detector 检测的物理子结构是什么?产出什么
   事件(点事件 / 宽事件 / 嵌套容器)?与现有 atom 的边界在哪?
2. **边界情况与静默不产场景**:哪些情形下有意不产事件(如窗口首部不足、判据不
   满足)?先按 reference §1 的失效边界写法把清单列出来,再写判据
3. **输出字段表**:逐字段确认名称 / 类型 / 语义 / 是否预计算;字段表必须过
   **confirm_idx 两问**(reference §2):① 成立条件是什么 → 观察窗口是什么;② 砍掉
   end_idx 还能判定成立吗——能 → 确认型(confirm == start,一确认就生);不能 →
   回顾型(confirm == end)。买点锚点字段必须 ≥ confirm_idx(前瞻闸)
3b. **参数归位表**(reference §2「参数归位原则」):每个门槛 / 旋钮逐个回答「它改变
   **哪些 K 线属于这个事件**(几何),还是只决定**这个事件算不算数**(资格)?」——
   资格型一律**不进构造函数**:原始量落字段、阈值由 app where 表达(bb_v1 的
   first_drought / distinct_pk / vol_spike 即此类);几何型才进构造函数,且要再标
   一层「过滤型 / 结构型 / 状态机型」。产出物 = 一张四列表(参数 / 归位 / 类型 /
   调参成本),随字段表进 spec。理由:where 阈值调参零成本(宽进一次、事后切档),
   构造参数每档一次全宇宙重扫(状态机型还不能跨档复用上游)——归位决定了这个
   detector 日后好不好调,而且**同一个量不能构造函数设门、where 再设门**(宽进
   放不开)
4. **普适 vs app 特异**:形状偏见是走势通用(→ 公共 atom,公共路径)还是单 app
   特异(→ app 内自定义,不进公共库)?——结论与 Step 0 路由不一致时回 Step 0 重判
5. **容器场景**(事件要装子事件序列):按 reference §3 设计 child_slots 结构
   (slot 名 = 父内家庭身份,声明于父 children 的 key)与 child() 端点选择器语义
   ——槽位名与端点选择器名不同层,别混;参考实现 `path2/atoms/breakout.py` 的
   BurstEvent

### 多流场景(同一趟 detect 产第二条流)

个别副产物**有独立生命周期、且无法脱离主事件的计算过程单独算出来**:主事件不发生
它依然存在(排除 children 嵌套),又写不出只吃 df 的纯函数单独算它(排除独立
detector)——它落 detector 副产物四格分类的 **4b 格**,用多流表达:同一趟 detect
内 yield 多条命名流。四格判据(可判定,逐问):

1. 是"没能成为事件的失败尝试"?→ **GateFailure**;是纯标量派生量?→ **事件字段**
2. 生命周期被某个主事件包含(主事件不发生它就不存在)?→ **children 嵌套**
3. 生命周期独立 → 问"能不能被一个独立 detector 单独算出来?":
   - 能(不需要主事件计算过程的中间状态)→ **拆独立 detector + consumes_stream**
     (格 4a),不要多流
   - 不能(需要主事件计算过程的中间状态)→ **多流**(格 4b)

唯一灰区:同一结构的不同侧面落在不同格 → 取最严格的那格;有任一必需侧面落 4b,
整体就走 4b。**负面裁定:性能理由不足以进 4b**——能被独立算、只是重算贵,老老实实
拆两个 detector,多流不是为省 CPU 存在的。

**多流写法**:
- 类级声明 `produces = {"流名": event_cls}`(Detector Protocol 的 produces,
  ClassVar);单流 detector 不写 produces、detect 直接 yield 裸 Event。**多流
  detector 不写 `event_cls`**(`stream_schema` 只认 `produces`,写了 `event_cls`
  也会被忽略,只留误导)。
- detect 内 `yield (流名, event)` 按流产出。
- **多流 detector 单流入口 `run()` 会拒绝(raise ValueError),用
  `run_bundle(detector, *source)`**——返回 `{流名: [Event]}`(声明驱动,空流也存在)。
- 事件类引用槽位 `ref_slots()`:返回 `{"槽名": self.xxx_refs} if self.xxx_refs else {}`
  (单/组引用统一;默认空)。引擎在全部流标注完统一翻译进 `Event.ref_ids`
  (`Tuple[(槽名, ids)]`,按槽名字典序排列,真 instance_id;`ref_ids_of(槽名)` 按槽名
  取值,缺槽返回 `()`);引用事件池外对象(instance_id 仍 None)视为 detect bug,
  报错。引用槽字段本身(如 `broken_refs`)不进 payload,下游只拿 `ref_ids` 里的 id。

示例(骨架可运行;真实多流 API 同 `tests/path2/dogfood_multistream.py` 的
RangeNoteDetector):

```python
from dataclasses import dataclass
from typing import Iterator, Tuple

import pandas as pd

from path2.core import Event
from path2.runner import run_bundle        # 多流入口(run() 会拒绝)

@dataclass(frozen=True)
class RangeEvent(Event):
    start_idx: int = 0
    end_idx: int = 0
    confirm_idx: int = 0

@dataclass(frozen=True)
class NoteEvent(Event):
    start_idx: int = 0
    end_idx: int = 0
    confirm_idx: int = 0
    anchor_refs: Tuple[Event, ...] = ()

    def ref_slots(self):
        return {"anchor": self.anchor_refs} if self.anchor_refs else {}

class RangeNoteDetector:
    """每 span 根产一个 range(该窗 high 最高点),随后 1 根内产 note 引用它。"""
    produces = {"range": RangeEvent, "note": NoteEvent}   # ★ 多流声明

    def __init__(self, span: int = 3, min_bars: int = 5):
        self.span, self.min_bars = span, min_bars
        self.on_gate = None

    def detect(self, df: pd.DataFrame) -> Iterator[Tuple[str, Event]]:
        highs = df["high"].to_numpy()
        for i in range(len(df)):
            if i < self.min_bars:
                continue
            if i % self.span == 0:
                lo = max(0, i - self.span)
                j = int(highs[lo:i + 1].argmax()) + lo
                rng = RangeEvent(start_idx=lo, end_idx=i, confirm_idx=i)
                yield ("range", rng)
                if i + 1 < len(df):
                    yield ("note", NoteEvent(
                        start_idx=i + 1, end_idx=i + 1, confirm_idx=i + 1,
                        anchor_refs=(rng,)))

det = RangeNoteDetector()
streams = run_bundle(det, df)                  # {"range": [...], "note": [...]}(声明驱动,空流也存在)

# ref_slots 翻译在引擎层(run_streams/analyze),不是 run_bundle:
from path2.dag.engine import analyze
from path2.dag.nodes import NodeSpec
from path2.dag.spec import PatternSpec
spec = PatternSpec("p", edges=(), nodes=[
    NodeSpec("range", det, produces_stream="range"),
    NodeSpec("note", det, produces_stream="note", solve=False),
])
res = analyze(spec, df)
# 统一翻译后 note 的 ref_slots → Event.ref_ids 里的一个槽:
# res.events 中 note.ref_ids_of("anchor") == (对应 range 的 instance_id,)
```

**多流 on_gate**:产 gate 的多流 detector emit GateFailure 时填 `stream=流名`(单流
恒 None),gate_collector 按流路由归属(见 authoring-path2-app skill)。

确认完成后进入 Step 2 落盘。

## Step 2 spec 落盘

把确认过的设计写成 spec(放 `.scratch/<id>/spec.md`,与 issue tracker 约定一致),四要素缺一不可:

1. **判据**:核心判据算法机制(产出判定逻辑、参数)
2. **字段表 + 参数归位表**:Step 1 确认的完整字段表,以及每个门槛的归位(资格型
   → 字段 + where;几何型 → 构造参数并标过滤 / 结构 / 状态机型)
3. **docstring 合同**(reference §5 三要素):① 核心判据算法机制 ② 输出字段含义
   ③ 一句话定位(供 reference §1 速查引用)。**docstring 草稿在 spec 中产出**、
   作为交付物之一移交实现——不能假定实现者会主动写,合同必须写明
4. **影响面清单**:Step 0.5 盘点的引用 app 清单与回归义务(公共路径:全引用 app
   regress 对拍;轻量路径:引用方测试)。detector 若埋 `debug_break` 或改 anchor_kind
   → 影响面清单补"前端 anchorsOf 同步条目"(契约见 reference §3 debug 菜单契约);
   埋 `debug_break` 时 spec 一并写明**埋点位置**——anchor 的判据执行现场、禁结果
   遍历处(纪律见 reference §3「埋点位置纪律」)

容器场景补两项:child_slots 结构设计 + children 声明(父 NodeSpec 的 children
key 与子结构 node 一行 NodeSpec)。

## Step 3 移交实现

- 把 spec 路径交回用户,由用户手敲 `/implement <spec 路径>`(该 skill 禁止模型自调)
- 设计确认必须在主会话完成,不在 subagent 里与用户交互

## Step 4 验证闸

1. `run_healthcheck(module_path=..., target_ticker=...)`:数量级 ok + 目标命中 +
   errors 不飙高
2. **公共路径**:对每个受影响 app `run_regress(baseline_path=...)` 对拍——
   「不改变现有行为」是假设,零 DIFF 才是证据;纯增补字段也要跑。非零 = 意外
   行为变化,分类:意图内(接受)/ 意外(必修)。新建公共 atom 无既有行为可对拍,
   验证以 run_healthcheck + 引用 app 的 run_eval 正常产出为准
3. 改了输出字段 / 语义 → 引用方 where 复查(app 侧 dag_spec 是否仍成立)
4. 改了 `debug_break` → 前端 `anchorsOf` key 集合对拍:埋 `debug_break` 的 node_id
   必须在 anchorsOf 有条目,且 anchorsOf 暴露的每个 anchor_kind 必须后端有 ≥1 个
   同 anchor_kind 的 debug_break(契约见 reference §3)

regress 义务细则见 reference §5。

## Step 5 on_gate 接线检查(L1 Detector 必做)

新加 Detector 需要在每个 attempt 短路点 emit 一条 GateFailure,按 reference §4
四条逐一核对:

1. **attempt 边界**:一次 emit = 一次 attempt,按 detector 的自然扫描单位划分
   (点事件逐 bar / 簇事件每簇 / 触发式每次触发)
2. **failure_event_window**:attempt 从起点到 gate 触发的实测轨迹——点事件恒
   (i, i);跨度事件 = (attempt_start, gate_idx),若成功此 window 就是 event 的
   [start_idx, end_idx]。入口 A 的严格 ⊆ 判据全靠这个字段,语义偏差会错分 attempt
3. **evaluation_lookback**:判据依赖的历史窗,前端 tooltip 显示、不参与 ⊆——
   判据只看当前 → None;看 rolling ATR / lookback 极值 → (start, end)
4. **measured.kind**:自由字符串标签,前端 formatters.ts 按 kind 分派格式化。
   复用已有枚举 → 前端已有专属前缀;自造新 kind → 走 default 分支落 String(value)
   不报错但没前缀,**需要前缀就顺手加一个 formatters case**

多流 detector 额外一条:gf 归**本该诞生的那个事件所在的流**(`GateFailure(...,
stream=流名)`),不是归 detector 本身或触发判据的上游流——例子与细则见 reference §4。

挂载:Detector 类里声明 `on_gate = None` 类属性(生产路径无开销),诊断层挂
collector 时在实例上覆盖。参考实现按事件形态对号(reference §4 列了三个样板)。

## Step 6 诊断契约同步(必做)

实现完成后,按 reference §6 同步维护 `diagnose-event/detectors/<模块名>.md`
(新建 / 修改判据、gate、签名、事件结构时):API 签名(以实际代码为准)、参数口径、
状态机判据顺序、gate 名表(含不 emit gate 的退段)、典型失效模式、骨架 B 变体。
轻量修改只核对契约是否仍准确;契约与代码冲突以代码为准。

- 契约层归本 skill 维护(作者知识,产出时最全);协议层与实战沉淀层归
  diagnose-event 自持——两 skill 分工见 reference §6,别越界重复
- 新增 detector 时,同步检查 diagnose-event reference.md 的
  「detector 语义契约索引」是否需要补条目

## Red Flags

- 公共 atom 不先 AskUserQuestion 确认就动手 / 修改后不对全部受影响 app 做
  regress 对拍(「不改变现有行为」是假设,零 DIFF 才是证据)
- 在 subagent 里问用户(AskUserQuestion 仅主会话可用,设计确认必须留在主会话)
- docstring 合同缺失就移交实现(docstring 草稿要在 spec 中产出,不能甩给实现)
- 把选型问题(该用哪个 detector)带进本 skill 的设计流程——选型归 app 设计流
  分诊,先回去分诊再回来
- 在 where 里 lambda 硬算需要回看的约束(必须进 detector 字段预计算,where 只读
  单实例自身属性)
- 把「资格型」门槛(不改事件几何、只决定事件算不算数的阈值,如最短根数 / 确认
  名次 / 量比上限)塞进构造函数,理由是「与 Platform / Burst 惯例一致」或「结构性
  阈值本来就在 detector 内」——惯例不是理由,调参成本才是:where 阈值零成本、
  构造参数每档一次全宇宙重扫;同一个量构造函数设门 + where 再设门 = 双重门,
  tune-gates 宽进放不到机制下限(reference §2「参数归位原则」)
- 静默改已确认的判据决定(判据 / 字段的任何改动都要回到用户面前确认)
- 改输出字段 / 核心判据后不同步更新 docstring 合同与 where 引用(字段改了,
  合同与引用方一起改)
- 在 anchorsOf 暴露的锚点在该 node 的 detector 内无匹配 debug_break,或 debug_break
  的 bar(i)与前端 anchor.bar 不严格相等(违反项数守恒 / 参数对齐契约 = "菜单显示但不停")
- 产出 / 修改 detector 后不同步 `diagnose-event/detectors/<模块名>.md` 诊断契约
  (作者知识在产出时最全,拖到诊断实战才补 = 重复逆向工程,且诊断会先撞一次
  API/语义错配——本次教训:tb v3 诊断时脑内映射 V1 签名)
- `debug_break` 埋在判据函数返回后的结果遍历处(如 `for s in res.segments:
  debug_break(...)`)——pause 时状态机已跑完、过程变量销毁,看不到机器如何运行
  (纪律见 reference §3「埋点位置纪律」;反面实例 = tb v4 初版把段锚点埋结果遍历处)
