# Skill 中 Detector 信息分层建议

> 针对 `.claude/skills/authoring-path2-app/design-heuristics.md` §A 的瘦身建议。
> 起因:讨论该手册是否应减少对 Detector 的细节描述,改为分层组织。

## 用户原观点

design-heuristics.md 中应减少对 Detector 的细节描述,只给出每种 Detector
负责检查哪种事件,让 skill 能根据用户需求选合适的 detector;详细描述放到
detector 自己的 docstring(认为目前已经这样做了);最下一层通过读代码了解详情。
形成三层结构:**skill 速查 → docstring → 源码**,按需深入,而非一开始就把所有
上下文摊开在篇幅有限的 skill 文档里。

## 判断:方向对,需要修正前提

### 同意

三层信息架构(skill 速查 → docstring → 源码)本质是「按需加载上下文」,原则正确。
把"detector 是什么 / 输出哪些字段 / 核心判据怎么算"这类**与使用方式无关、与代码
绑定**的信息归到 docstring,确实比塞进 skill 篇幅更合适——docstring 离代码近,
漂移风险低;skill 离设计任务近,篇幅金贵。

### 需修正的前提:"已经这样做了"不准确

实测 `path2/atoms/breakout.py`:

- `BurstDetector` docstring 较完整(聚类/物化/独立性原则都讲了)
- `BODetector` docstring **只列了 5 步算法骨架,没有失效边界、没有常见误配**
- 其它 detector 未逐一核对,估计类似

"下沉到 docstring"不是"已完成、可以放心删 skill 段落",而是要**先补 docstring,
再瘦身 skill 手册**——顺序反了会丢失上下文。

## 精准拆分方案

§A 当前每条 detector 4-5 块(检测什么 / 输出字段 / 核心判据 / 静默不产 / 常见误配),
**不是均匀全删,而是按归属拆**:

| 内容 | 该去哪 | 理由 |
|---|---|---|
| 检测什么子结构(一句话定位) | 留 skill | 选型层只需这个 |
| 输出字段 | 下沉 docstring(或 Event dataclass docstring) | 跟代码定义同处更稳 |
| 核心判据(算法机制) | 下沉 docstring | 同上 |
| **静默不产的情形**(失效边界) | **留 skill** | 这是「选不选 X」的关键裁决依据,详见下方反例 |
| **常见误配** | **留 skill** | 设计期决策依据,非使用期参考 |

按此口径,§A 每个 detector 大致瘦身到 **5-8 行**(一句话定位 + 失效边界 + 常见误配),
核心判据/字段表全部转到 docstring。skill 篇幅显著释放,但**选型决策依据完整保留**——
这才是 skill 不可替代的视角。

## 一个反例提醒:别把失效边界也下沉

失效边界看起来像"使用细节",但在设计期它决定**该不该选这个 detector**。

例:`ThrowbackDetector` 的"破位即不产"是选型期就要权衡的代价。等到 docstring 才看到,
意味着已经把它写进 dag_spec 了——再回头改拓扑,代价远高于选型时一眼瞥见。

**skill 视角与 docstring 视角的真正分水岭,是「选型 vs 使用」,不是「概要 vs 详细」。**

- docstring 写给"使用 detector 时" → 输出字段、算法机制、参数语义
- design-heuristics 写给"为某需求选 detector 时" → 一句话定位、失效边界、常见误配

## 执行步骤(待用户拍板后)

### 存量(已有 detector)

1. **补 docstring**:逐一为 `path2/atoms/*.py` 中每个 Detector 类的 docstring 补齐
   "核心判据"和"输出字段"(BurstDetector 已较完整,BODetector 等需补)。
   注:Event 字段表可放 Event dataclass 的 docstring,不必塞进 Detector 类。
2. **瘦身 skill**:`design-heuristics.md` §A 每条 detector 删除"输出字段"和"核心判据"段,
   保留"检测什么(一句话)"、"静默不产"、"常见误配"三块。
3. **加交叉引用**:`design-heuristics.md` §A 顶部加一句:"每个 detector 的算法机制 /
   输出字段详见对应 docstring。本节只承载选型期决策依据(失效边界 + 常见误配)。"
   让 skill 在需要细节时引导深入到 docstring 层。

### 增量(SKILL.md 修订——防分层反噬)

只做存量整理不够:若新建/修改 detector 时不写 docstring,半年后分层又会塌——老
detector 补 docstring → 新 detector 又没写 → skill 不得不重新承担细节。所以必须在
SKILL.md 同步落实增量纪律。`authoring-path2-app` skill 是 detector 选型/扩展/新建的
入口(`SKILL.md` 层②),docstring 内容由 skill 在 spec 中产出草稿、随 spec 移交
superpowers 实现——不能假定 superpowers 会主动写,合同要写明。

4. **SKILL.md 层② 新建 detector 流程(第 100-106 行)** 插入"docstring 落地要求"步骤:

   > 新 detector 的 docstring 必须覆盖:核心判据(算法机制)+ 输出字段
   > (Event dataclass 字段含义,也可放 Event 类 docstring)+ 一句话定位
   > (供 `design-heuristics.md` §A 引用)。**docstring 草稿在 spec 中产出,作为
   > 交付物之一移交 superpowers 实现。**

5. **SKILL.md 层② 修改 detector 流程(第 87-99 行)** 与"改输出字段/语义 →
   层③ where 引用复查"**并列**加一条:

   > 改输出字段 / 核心判据 → docstring 同步更新(否则 docstring 与代码漂移,
   > 反噬整个分层信任)。

   这与"yaml 与子 dataclass 必须同步"是同构的纪律:配套文档与代码同 PR 落地、不留 debt。

## 状态

待用户决定是否执行。本文档可在执行后删除。
