---
name: write-detector
description: 新写或修改 path2 的 detector、事件类：现成的 detector 认不出用户框的那种形状，要给事件加一个字段供条件读，要改某个 detector 的认法，或 detector 本身有毛病要修。用户说「新写一个 detector」「现成的认不出这种形状」「给 XX 加个字段」「改一下 XX 的认法」「XX 这个 detector 有 bug」时使用；标注的一轮（annotation-round）改 app 时遇到这几种情况也转到这里。
---

# 写 / 改 detector 与事件类

**方向归用户，翻译归会话。** 用户在图上框出例子、写下特征定义，这就是需求的全部；detector 怎么切段、字段叫什么、参数放哪，会话自己定、自己写、自己验，不逐项找用户确认，不另写设计文档，不进 plan mode。只有两种情况回到用户面前（见「什么时候问用户」）。

本 skill 是一套做事顺序（本文）加一份「写 detector 该知道什么」的手册（[reference.md](reference.md)）。

## 和别的 skill 的分工

| 事情 | 归谁 |
|---|---|
| 该用哪个 detector、一条约束放在 node / where / 边的哪一层、where 的门槛取多少 | `annotation-round`（它的 `references/writing-app.md`） |
| detector 与事件类怎么写；where 要读的量怎么算成事件上的字段 | 本 skill |
| 已有的事件为什么没生成、没命中 | `diagnose-event` |
| 只调参数取值 | `tune-gates-v3` |

## 红线

1. **现场读代码。** 具体参数值、判据、字段名一律读 `path2/atoms/*.py`、`path2/core.py`、app 包里的代码，不引用任何文档里抄下来的数（包括本 skill 的手册——它只告诉你去读哪里、问什么）。
2. **行情只到 2025-12-31。** 看 K 线、跑 app 只经 `annotation-round` 的看图脚本或 `path2_web/app_run.py` 的 `run_app`（它们读训练段副本 `datasets/pkls_until_20251231`）。`path2_web/eval_runner.py` 的三个函数读行情的目录缺省是完整行情：一律加 `data_dir='datasets/pkls_until_20251231'`，`end` 不晚于 `'2025-12-31'`。不读 `datasets/pkls`。
3. **标注只读。** 读标注只经 `path2_web/annotation/store.py` 的 `read_annotations`；不打开、不写 `annotations/` 下的文件。
4. **由 `annotation-round` 转来时，它的红线照旧有效**——尤其「先定格，再碰 app」：本轮的 round 文件存在之后才改任何 `.py`。
5. **入库的测试不读行情。** 测试用合成 K 线；拿真实行情核对考题是一次性的运行，不写成测试。
6. **不提交。**

## 开工先读

- [reference.md](reference.md)：§0 红线、§2 事件类规范、§5 公共库纪律、§7 引擎侧契约**必读**。其余用到再读：改现成 detector 读 §1 里它那一条，新写时读一两条相近的当样板；复合事件或埋调试断点读 §3；`on_gate` 读 §4；诊断说明读 §6；同一趟要产两种事件读 §8。
- 要用的词先 `grep -n '词' path2/GLOSSARY.md`，只读那一段。

## 0. 认输入

| 来由 | 必须带着什么 |
|---|---|
| **认形状**：新写 detector、改认法、加一个判断要读的字段 | **考题**：用户框过的例子（哪只股票、框的起止日期、是哪个特征）、特征定义原话、where 要读什么量。`annotation-round` 转来时它带着。用户直接开口而没有例子时，先请他指出是在哪几张图上看到的、在标注工具里框出来（或指出已有的标注）——脱离图的描述不直接变成 detector |
| **工程性修改**：修 bug、重构、补调试断点、补 `on_gate`，不改认出什么 | 不要考题；检验标准换成「改前改后认出的东西一个不差」（第 4 步的对拍） |

先把考题那几段 K 线看一遍再设计（没有 app 也能看）：

```bash
uv run python .claude/skills/annotation-round/scripts/look.py - <股票> <起> <止> --before 30
```

## 1. 定放在哪

| 情形 | 放哪 | 额外要做的 |
|---|---|---|
| 只为这一个走势服务、带形状偏见（例：固定取阶跃前若干根当旧平台、按某一段的波动倍数开段） | app 包内，如 `path2_apps/new_step/plateau.py` | 无。**拿不准就走这条** |
| 走势无关，至少两条不相关的走势会用，或表达单一通用物理事件 | `path2/atoms/` 新建 | 先问用户 |
| 改 `path2/atoms/` 里现成的（加字段、改判据、改语义） | 原地改 | 先问用户；动手前给每个用到它的 app 存基线 |
| 只改事件类的结构（字段、`child_slots`、`child()`），不动判据 | 原地改 | 属公共的同上一行 |

动公共 detector 之前，按这个顺序：

1. grep 出全部用到它的 app（新建也 grep 一遍，防已有同名或相近的实现）。
2. 问用户一次（问法见「什么时候问用户」）。
3. 用户同意后、改任何代码之前，给每个受影响的 app 存一份基线：

   ```bash
   uv run python -c "from path2_web.eval_runner import run_eval; run_eval(module_path='path2_apps.<app>', start='<起>', end='2025-12-31', data_dir='datasets/pkls_until_20251231', out_path='outputs/path2_eval/<app>_baseline.json')"
   ```

   代码改了之后就再也存不出改前的基线。

## 2. 设计

按顺序定下面五样，**写进 detector 和事件类的 docstring**——它就是设计记录，不另起文档。

1. **认什么。** 对着考题，用一句话写出它认的结构，产出点事件、宽事件还是复合事件（`path2/GLOSSARY.md`），和现成 detector 的边界在哪。
2. **什么时候不产。** 先列清单再写判据（写法参考 reference §1）。然后把考题逐个过一遍：每个例子都不能落在清单里。
3. **字段表。** where 拿不到 K 线，它要读的每个量都必须是事件上算好的字段。逐字段过 reference §2 的 `confirm_idx` 两问；字段的值必须在事件确认那一刻已经知道；买点锚的字段不早于 `confirm_idx`。
4. **参数归位**（reference §2「参数归位原则」）。每个门槛问一句：它改变「哪些 K 线属于这个事件」，还是只决定「这个事件算不算数」？后者不进构造函数——原始量落字段，门槛留给 app 的 where。构造函数里只留让事件定义成立的最松取值；同一个量不在构造函数和 where 里各设一道门。
5. **结构。** 事件里要装子段 → reference §3。同一趟检测还要产另一种东西 → 先按 reference §8 的四格判据定它该是字段、子段、另一个 detector 还是第二条流。

考题怎么判对上（框看终点那天有没有事件在场，样本看买点日）在 `annotation-round` 的 `references/writing-app.md` 第 2 节，设计时照它：事件要在用户画完框的那种日子上在场。

### 什么时候问用户

只有两种，都用 AskUserQuestion，白话讲清「在决定什么、选了会怎样」，推荐项放第一，不问门槛、不问字段名、不报内部名词：

1. **动公共 detector 之前。** 说清：改它会连带影响哪几个 app；另一条路是在这个 app 里单写一个，代价是什么。
2. **考题定不下来的方向分叉。** 两种认法都认得出全部考题，但在考题之外会认出明显不同的东西（例：分两天爬上去的算不算一次阶跃）。给每种认法各举一两只股票的具体日期。
   - 由 `annotation-round` 转来、它的清单已经出过题：不在这里另开一轮问答。先按更贴近特征定义原话字面意思的那种写完，把这道分叉连同两种认法各多认、少认哪些交回它，写进改版报告里它补的那一段，下一轮作为「要你定」的题。
   - 用户直接开口的：当场问。

其余一律自己定，交付时列出来给用户过目：字段名、切段细节、判据顺序、参数归位、构造参数的取值（标「待验证」）。

## 3. 写

照 reference 写。几条最容易出事的：

- 事件类 `@dataclass(frozen=True)`，容器字段一律 tuple；身份字段（`node_id` / `instance_id`）不读、不拼。
- K 线回看只在 detector 里；where 里不写要回看的 lambda。
- detector 不在两次 `detect()` 之间留状态。
- 复合事件的 `child_slots()` 无条件返回声明过的全部槽名（成员为空也给空 tuple）；app 的 node 上要有对应的 `children` 声明。
- 每个「这次没认出来」的短路点接上 `on_gate`（reference §4 四条逐一对）；多流时归属照 §4「gf 归属」。
- 埋调试断点时，前端的锚点表同一次改动里跟上（reference §3「debug 菜单契约」），断点埋在判据执行的现场。
- 入库测试：合成 K 线，覆盖判据顺序、第 2 步「什么时候不产」清单里的每一条、字段取值。公共的放 `tests/path2/atoms/`，app 内的放 `tests/path2_apps/<app>/`。

## 4. 验

按顺序做，前一项不过不做后一项。

1. **测试。** `uv run pytest tests/path2 tests/path2_apps/<app> -q`（改了公共 detector 时，受影响的各 app 的测试一起跑）。
2. **考题。** 在每只有考题的股票上跑看图脚本，逐个核对：框终点那天，这个 node 有事件在场；子框对得上子段。

   ```bash
   uv run python .claude/skills/annotation-round/scripts/look.py <app> <股票> <起> <止> --fields
   ```

   认不出的例子不许略过：要么改到认出，要么写明它卡在哪条判据、为什么这条判据不该为它放宽，交回去由用户看。字段名、子段声明写错只有在有事件的股票上才报得出来，所以这一步不能只跑一只。
3. **体检**（新写或改了判据时）。看认出的股票数是不是一个合理的量级（不是 0、不是几乎全部）、那只有考题的股票认没认出、有没有报错——返回值里的 `magnitude_ok`、`target_hits` 都为真，`meta.errors` 为 0：

   ```bash
   uv run python -c "from path2_web.eval_runner import run_healthcheck; run_healthcheck(module_path='path2_apps.<app>', start='<起>', end='2025-12-31', target_ticker='<一只有考题的股票>', data_dir='datasets/pkls_until_20251231')"
   ```

4. **对拍**（改了公共 detector，或做工程性修改时）。对每个受影响的 app：

   ```bash
   uv run python -c "from path2_web.eval_runner import run_regress; run_regress(baseline_path='outputs/path2_eval/<app>_baseline.json', data_dir='datasets/pkls_until_20251231')"
   ```

   「不改变现有行为」是假设，多出与消失的买点都是零才是证据；只加字段也要跑。不是零就逐条归类：这次改动本来就要的（接受，报给用户），意料之外的（必须修）。新建的公共 detector 没有旧行为可比，以体检为准。
5. **引用方复查。** 改了输出字段或语义：grep 各 app 的 `dag_spec.py` 里读这个字段的 where，确认还成立。
6. **调试锚点对拍**（动过调试断点时）：埋了断点的 node 在前端锚点表里有条目，表里露出的每一档后端都有对应的断点（reference §3）。

## 5. 同步说明

- **诊断说明**（reference §6）：新建或改了判据、`on_gate`、签名、事件结构，同步 `.claude/skills/diagnose-event/detectors/<模块名>.md`，以实际代码为准；新 detector 还要在 `diagnose-event/reference.md` 的「detector 语义契约索引」加一行。只做了不动这些的小改，核对一遍现有说明还准不准。
- **速查条目**：新 detector 在本 skill 的 reference §1 加一条（一句话定位、什么时候不产、常见误配）；改了认法就改对应那条。
- **docstring**：核心判据、输出字段、一句话定位三样齐全，与最终代码一致。

## 6. 交回

由 `annotation-round` 转来的，把下面几样交回它（它接着改 app、出改版报告），不单独向用户汇报：

- 新 node 上能读的字段，各是什么意思；
- 什么时候不产；
- 哪些考题没认出、卡在哪；
- 有没有待用户定的方向分叉；
- 动没动公共 detector，对拍结果。

用户直接开口的，收尾时用业务话说：现在认得出什么、哪几个例子没认出及原因、连带影响了哪些 app、有哪些自己定下来请他过目的取舍。不报函数名、字段名、脚本名。

## 容易犯的错

- 没问用户就动 `path2/atoms/`；或动了之后不对全部受影响的 app 对拍。
- 改完才想起存基线（改前的行为已经算不出来）。
- 拿「认得差不多」交差：有考题没认出却不写明原因。
- 把「算不算数」的门槛塞进构造函数，理由是「别的 detector 也这么写」——惯例不是理由，调参成本才是：where 的门槛事后切档零成本，构造参数每换一档要全部重扫。
- 为了让某个考题过关去拧门槛。门槛归调参；detector 这一层只保证形状切得出来、量算得对。
- 字段的值要到事件确认之后才知道（偷看后面的 K 线）。
- 改了字段或判据，没同步 docstring、诊断说明和引用它的 where。
- 断点埋在判据函数返回之后的结果遍历处（停下时过程变量已经没了）。
- 在子代理里向用户提问（提问只能在主会话）。
