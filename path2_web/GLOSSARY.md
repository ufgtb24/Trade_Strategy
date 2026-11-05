# path2_web

path2 的调试可视化工具：把分析结果投影成 JSON、再渲染成可交互的界面。这里是界面自己的词汇——事件在图上怎么摆、显示到哪一档、参数怎么试、漏检从哪查。

覆盖 `path2_web/`（FastAPI 后端）与 `path2_web_ui/`（Vue3 前端）。这一层不含任何走势语义：界面不知道 bo 和 burst 各是什么，只按 node 分轨、按 where 分列。核心词（事件 / node / hit / where）见 [path2](../path2/GLOSSARY.md)。

## Language

### 数据与流程

**扫描 / scan**：
对全宇宙股票逐只跑一遍选定的 app，把命中与统计落盘成一个结果文件。

**临时计算**：
用当前 yaml 参数即时重算一只选中的股票，不落盘、不进扫描结果，专给「改完参数立刻看效果」的调参循环用。

**Working Copy**：
某个 app 参数的可编辑副本；改副本的内容与让图表用不用副本，是两件独立的事。

**锚 pattern、active pattern**：
左栏列表按哪个 app 排序筛股叫锚 pattern，右侧图表当前渲染哪个 app 叫 active pattern；两者正交，点单元格只切股、不切 active pattern。两者选的都是 app，不是 pattern 本身。

### 显示深度

**显示档位 / level**：
全局的显示深度旋钮，三档从浅到深依次是 detected、qualified、in_hit。

**detected、qualified、in_hit**：
一个事件的三档可追溯深度，依次收窄——被检测出来、通过了所在 node 的全部 where、进了某一次 hit。

### 图上的几何

**主图**：
K 线蜡烛所在的图；声明为钉价格轴的点事件画在这里（如 bo 三角与它突破的那些 pk）。

**副图**：
事件区，横轴与主图对齐；主图之外的事件都在这里，纵向没有价格含义、只表示「哪根 K 线上发生了什么」。

**band**：
副图里的一条轨，一个 node 一条。

**lane**：
一条 band 内部为了不让重叠事件互相压住而分出的泳道。

**bracket**：
一次 hit 的时间跨度在图上的样子——一条带圈号的横带，圈号是它在本图内的编号；标注里 sample 的跨度也画在这条轨上，画虚线、不带圈号。

**tag**：
= a small box shown next to a thing to give one status or conclusion about it.
说的时候带上种类：`match tag`（sample 与 hit 比较的结果）、`diff tag`（sample 的 member box 与 mapping 比）、`tier tag`（框底下 app 认到哪一档）、`link tag`（相邻两段 app 连没连上）。
_Avoid_: 签 —— 已改称 tag；差 tag、档位 tag、两段之间的 tag —— 已改称 diff tag、tier tag、link tag。

### 面板

**拓扑面板**：
pattern 的 DAG 图，同时是 node 的控制器：点节点切显隐，双击拉这个 node 的诊断。

**诊断侧栏**：
右侧的漏斗总览与逐次命中留痕：每个 node 一行三档计数，展开看候选逐条卡在哪。

**漏检入口**：
回答「为什么这个事件或这条关系没命中」的几个固定查询口径——按时段查失败的 attempt、按 node 看 miss 分布、指定两个事件问它们为什么没连上。

### 标注工具

**off_pattern / 不像**：
= a blind-review answer given when the hit does not have the shape of the pattern at all.
盲看作答的三个取值之一；另两个 `pos`、`neg` 与样本的 judgment 同义（是这个 pattern、当天会买 / 像这个 pattern、当天看得出不该买）。`off_pattern` 说 app 认出的东西连样子都不对，毛病在翻译：dag 缺一样 `must`，或 where 太松；`neg` 说样子对、pattern 缺一条 `must_not`。两者指向相反的改法，所以分开。盲看随机部分里判 `off_pattern` 的张数是忠实度计数，只说明 app 有没有走样，不说明赚不赚钱。
_Avoid_: 不是 —— 分不出是 `off_pattern` 还是 `neg`。

**review / 复核**：
= the `next` value shown while an app that passed the final check is in provisional use and waits for enough new data to be checked again.
标注工具页头「下一步」一格的取值之一，旁边写最早能复核的日期；和 tune-gates-v3 的复核阶段同名（它的三段数据叫 `training` / `final` / `review`）。复核用和最后检查同一条写死的及格线，只用最后检查之后新来的数据；过了是继续使用，没过是撤回。显示它时该做的是等，不是改结构或再送检。

**known**：
= a key on a blind-review card, pressed when the user remembers how that chart went on.
按下后这张不作答、不进比例，补抽一张随机的。盲看只藏得住后续走势，藏不住记忆，所以由用户自己说「这张我认得」；工具不记用户看过什么，这个键是唯一的出口。

