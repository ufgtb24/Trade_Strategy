# path2_web 调试可视化架构意图

> 最后更新：2026-07-25

覆盖 `path2_web/`（FastAPI 后端）+ `path2_web_ui/`（Vue3 前端）。框架见 [path2.md](path2.md)，应用层见 [path2_apps.md](path2_apps.md)。

---

## 定位与边界

path2 dag pattern 的 **web 调试 / 可视化工具**：选 pattern → 全市场扫描 → K 线叠事件 markers + 拓扑面板 + 漏检诊断侧栏 + 参数探索。

管：把 path2 的分析结果投影成 JSON、并把它渲染成可交互的调试界面。
不管：任何走势语义。检测逻辑在 `path2/`，pattern 结构与阈值在 `path2_apps/`。

对外依赖（改动它们的形状要同步 web）：
- `path2.dag` 的只读结果结构（`path2_web/serialize.py` 顶部 docstring 列了消费的类型）
- `path2.eval` 的前瞻收益计算（label 注入）
- app 包对外暴露的模块级契约（pattern 构建 / 分析入口 / 参数加载 / `eval_meta`），注册闸的校验口径见 `path2_web/discovery.py`
- 成对 event 的诊断复刻边检查时，复用了 `path2.dag` 求解层的内部函数（含私有模块）：path2 改求解语义，这里的诊断口径会跟着变、且不会报错

---

## 两条红线

1. **后端纯投影层**：`path2` 本身零 web 依赖（不引入 JSON / HTTP）；序列化只在 `serialize.py` 发生，且是纯函数——不读文件、不起服务。
2. **前端类型无关渲染器**：渲染只吃后端下发的 `class_id` / `source_tag` / `topology` / `event_styles`，**产品代码零具体事件类型、零 pattern 名硬编码**。

合起来的收益：新增 pattern（新建 path2_apps 子包）时，前后端都零改动。这条收益是这两条红线存在的**全部理由**——任何要求"给某类事件开个特例分支"的改动都在偷走它。

---

## 关键决策与理由

**eval_meta 是 app 的必需协议，不是可选优化。** app 必须交出买点 node 与指标 warm-up 深度，web 才能算缓冲窗与 label。若允许 fallback（猜一个 node、写死一个天数），web 产品代码就得知道具体 app 的常量，红线 2 立刻破。所以在 pattern 注册时就设闸：不合规的 app 直接不入 registry、进 errors 列表，下游因此可以无条件取用、不做兜底。

**双端缓冲切窗。** 起点前推供指标 warm-up、终点后延供前瞻收益；缓冲段事件照旧序列化（K 线上以灰色层可见），但 match 要按买点日期落在严格窗内才算命中。交易日→日历日的换算比例与 `scripts/path2_eval_bottom_breakout_burst.py` 同源，两边口径必须对得上。

**label 叠在投影产物之上**：先投影出 match，再往产物 dict 上补前瞻收益字段；收益本身复用 `path2.eval`，web 不另起一套收益口径。这样投影仍是纯函数，"纯投影"边界不破。

**计数单位有意分家：** `scan.py` 的扫描入口服务 UI，按 match 计（match 是渲染单位）；`eval_runner.py` 服务设计期评估，按买点去重（买点才是评估对象）。这不是不一致，是两种问法。

**排序锚 pattern 与 active pattern 解耦。** 多 pattern 扫描下，左侧列表按哪个 pattern 排序、与右侧渲染哪个 pattern 是两件事：列表单元格点击只切股票，active pattern 只由图表区下拉显式切换。混在一起会让"找漏检场景"这个动作不断打断当前观察对象。

**参数探索的两轴正交模型**（`ParamsChip` + `WorkingCopyDrawer` + 纯函数层 `paramsEditorState.ts`）：
- **内容轴** = 改副本；**视图轴** = 图表用不用副本重算。
- `enabled`（视图轴）的**唯一写者是 chip**；一切内容轴操作绝不碰它。
- 收益：「改副本内容」与「是否在看副本」各留恰好一个入口，不会互相触发。

**三档 level（detected ⊇ qualified ⊇ matched）由一组共享 computed 派生**（`stores/view.ts` + `render/visible.ts`）。K 线与 sidebar **共读同一批派生量**，着色与计数因此不会漂移；任何组件自己重算一份 tier 都会引入不一致。

**漏检诊断按 scope 分派、只跑需要的那一 pass。** 各 scope 的数据依赖彼此正交（有的只要诊断产物、有的只要带 gate_failures 的分析结果），分开跑是为了避免在调试断点场景下被暂停两次。单股即时诊断可以接受重算成本。

**诊断响应允许"部分数据"**：接不上的那块以 caveat（原因码 + 说明）挂在响应上，前端据此显示提示条而不是崩或假装有数据。

**断点通道走进程 env**：`/diagnose` 写 `DEBUG_*` 环境变量供 `path2.debug_ctx` 消费，让 detector 在指定 bar / 锚点处停下。这是有意的单向注入，避免为调试在 path2 的函数签名里开洞。

---

## 不变式

- **`slice_window` 是唯一切片入口**（`path2_web/data.py`）。所有取窗路径（扫描 worker、各取数 / 诊断端点、设计期评估器）都经它，且同一次渲染涉及的路径共用**同一个窗**（缓冲扫描下即缓冲窗），才能保证 `bars[i] ↔ detector 的 start_idx == i`。破了它，前端 markers 就整体错位——而且是"看起来像检测逻辑出错"的那种错位。
- **每个 node 的 `source_tag` 必须互不相同**：它是前端分轨（band）的身份。`serialize.py` 在静态投影时断言这一点，重复即抛——否则多个 node 挤进同一条轨道、静默坍缩。band 归属一律以后端下发的 `source_tag` 为准，**前端别去解析 `event_id` 前缀**（那是后端算 tag 的内部手法，不是契约）。
- **复合事件的子 event 只以 id 引用下发**（由 event 自己声明的 child 槽位驱动，不硬编码字段名），子对象不内联进父 event——要下钻就按 id 回查 events 全集。
- **单股失败不中断整批**：扫描 worker 的异常转成该股的错误计数，空窗直接跳过；一只票的脏数据不该让全市场扫描白跑。
- **进度流对晚连订阅者补发末态**：扫描已结束后才连上的页面必须立刻收到终态，否则前端永远停在"进行中"。
- **日期串恒为零填充 ISO**（`YYYY-MM-DD`）：前端直接用字符串比较取窗。
- **前瞻收益字段是三态**：键缺失 = 该结果文件根本没有 label（不显示该行）／null = 尾部数据不足（显示占位）／数值 = 真实收益。前端靠"键在不在"判别，**别改成"总是注入 null"**。
- **结果文件自包含**：pattern spec 快照与参数快照都写进文件，离线可独立渲染、也是参数 diff 的锚。**唯一例外是配色**——它是纯 UI 关注点，加载历史扫描时用当前调色板覆盖文件里冻结的那份，调色不必重扫。
- **`path2_web_ui/src/types.ts` 是后端 JSON 的镜像**，是前后端唯一对接面：后端改字段必须同步它（投影之后追加的字段同理）。
- 副图高度合成恒满足 `有效高度 ≤ 画布高度`（`render/subGeometry.ts`），即"永不留白"。

---

## 负知识（改这些地方会静默出错）

- **别复用 `mod.PATTERN_DAG` 去跑扫描或诊断**：它是 import 时一次性 build 的，会与磁盘上的 yaml 漂移。一律 `build_pattern(load_params())`，yaml 是参数 SSoT。
- **worker 里别直接调 `mod.analyze(...)`**：它内部自建 spec，外面拿不到 spec 就挂不上 `on_gate` 收集器（必须在 analyze 之前挂）。所以 worker 有意复刻其内部两步。
- **`attach_and_collect` 之后必须 `detach`**：ProcessPool 会复用进程，残留的 on_gate 会让下一个 symbol / pattern 串扰。
- **参数 dict 由主进程一次读好、直达 worker**：让 worker 各自去读 yaml，会与扫描期间的手工改动竞态。
- **存参数用 round-trip 写法，不要整文件 dump**：`params.yaml` 的注释是字段语义的 SSoT，整文件覆盖会把注释杀光。
- **`DEBUG_*` env 是进程级的**：`/diagnose` handler 的 finally 无条件清空它们，否则会跨 request 污染、甚至让扫描进程池继承后挂死。并发下这套行为未定义——这是单人调试工具的自觉取舍。
- **跨结构对拍别拿 `event_id` 当锚**：pattern 结构一改 event_id 就变，前后两次结果会全判成"新增+删除"。设计期回归对拍锚在 (股票, 买点日期) 这类语义键上。
- **扫描输出根目录锚在 repo root**，不跟随启动时的 CWD。
- 无参数快照的旧扫描文件：参数 chip 整体不渲染（没有锚就没有可信的 diff，宁可不给假 affordance）。
- 休眠草稿**只持久化副本内容**，编辑区里未写入副本的缓冲从不落盘；且刷新后**不自动激活**，需用户显式恢复。

---

## 核心流程

```mermaid
flowchart LR
    A[path2_apps 各 app] -->|注册闸: PATTERN_DAG + eval_meta| B[PatternRegistry]
    B --> C[扫描 worker]
    C -->|缓冲切窗| D[analyze]
    D -->|窗内过滤 + label 注入| E[自包含结果文件]
    E --> F[前端加载]
    F --> G[view store 派生]
    G --> H[K 线 / 拓扑 / 侧栏]
    H -->|漏检查询 scope| I[/diagnose]
    I --> D
    H -->|参数副本| J[/preview]
    J --> D
```

前端永不直连 path2，只吃后端 JSON。
