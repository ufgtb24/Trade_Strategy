# final_report：class_id 彻底清除 · 第二轮设计研究

- 日期：2026-08-14 · 团队：arch（第一性原理+价值）/ skeptic（红队）/ coder（代码事实官），lead=主会话
- 原始问题：见同目录 `原始问题.md`；背景与方案 A：`context.md`；各成员全文：`arch-notes.md` / `skeptic-notes.md` / `coder-notes.md`
- 结论已三人交叉复核收敛；对 lead 第一轮事实的三处证伪已吸收（§6）

## TL;DR

1. **Q2（第一性原理：值得吗）——值得，无保留条件**。class_id（=Python 类名字符串）不承载任何不可替代信息；版本信息的正确表达位是声明层且三载体已在（pattern_id / node_id 自由命名 / gf.code_location 行级指纹）。
2. **Q1（方案 A 最佳吗）——不是；A'（A 的收紧版）是**。A 的骨架全部经受住四项攻击，A' 只做收紧与补齐、零重设计。
3. **Q3（多维度）——四层概念账持平或减少，新 detector 概念集 4→3，authoring 样板 8-9 处→0 处，零新增必写项，"类名漂移静默失败"整类错误物理消失**。新上升维度：概念死亡边界必须含 skill 文档层。
4. **附带红利**：删 debug class 门顺手修复现存双 bug（右键 debug 三锚全不命中 + diagnose 过滤恒空）。

## Q2：废弃 class_id 的代价评估（arch 主笔，三人收敛）

**第一性原理框架**：一条事件记录的身份回答三个正交问题——
- 唯一性 → `instance_id`（物化层，引擎注入）
- 结构位置 → `node_id`（声明层，pattern 作者赋予语义）
- 实现类型 → `event_cls`（Python 运行时类型系统，`isinstance` 即可判别，不需要字符串化）

`class_id`（类名字符串）在这三轴上无不可替代职能。关键洞察：**版本是声明的属性而非事件的属性**——同一个 `ThrowbackEventV1` 类被 bb_v1 还是 bb_v3 挂载是 pattern 的选择，版本差异的正确表达位是声明层。

**版本信息三载体已存在且更强**：
1. `pattern_id` 本身编码版本（bb_v1 的 v1 ↔ ThrowbackEventV1）；
2. `node_id` 是自由字符串，单 pattern 多版本并存时命名 `tb_v1`/`tb_v3` 即可（bb_v3 的 `tb_seg_v3` 已有先例），架构零改；
3. `GateFailure.code_location`（精确到 `throwback_v1.py:126`）已进前端契约（types.ts:176）并渲染于 attempt 行（FailedAttemptsCard.vue:98）。

**"信息丢失"场景逐一排除**：gate failure 不持久化（scan 文件无 gf 字段，eval_runner.py:72 自认无消费者）→"导出脱上下文回看"场景物理不存在；实时诊断恒带 pattern 上下文；前端区分容器/段/V1 变体早已靠 `child_refs` 结构信息（view.ts:41-50 tbAnchorProfile），不依赖类名。

**代价表收口（五项全清，arch 终稿）**：①版本信息无实际损失（三载体已在）；②共享处置 = attach 哨兵（§4）；③debug 门删除 = 修现存双 bug 非丢功能（§5）；④事件行序列化零增量（class_id 本就不在事件行）；⑤兼容零成本（GateFailure 不落盘——serialize 零输出 failed_attempts，前端 gf 全来自 /diagnose 实时响应，无持久化面即无老文件兼容问题）。

## Q1：方案 A 攻击结果与 A'（skeptic 主笔，coder 代码验证，arch 背书）

### 四项攻击结果

| 攻击面 | 结果 | 要点 |
|---|---|---|
| 共享 detector 模糊性 | **成立（A 唯一实质缺陷）** | gf 错标 node = 诊断归因错向（数据错误非显示降级）。wrapper 变体穷举（广播/链式/置空）全引入新复杂度。**正解=消灭状态：窄禁令**（§A' 第 4 条） |
| debug 删 class 门 | 复核通过 | 30 埋点（实测，非 28）全在 tb 家族；单 pattern 内 (bar, anchor_kind) 唯一命中。class 门的区分度上限=detector 粒度，(bar,anchor_kind) 恰达同一粒度；同 detector 内多出口埋点 class 门本就区分不了（同类名），靠 pause 行号。**注意 fork 论证②的表述错误**（"容器恒 gate/entry"对 v1/v0 不成立，v1:259/269/273 end 埋点挂容器类）——结论侥幸成立，真理由如上 |
| 信息丢失 | 无实质场景 | 见 Q2 |
| web 变更面 | lead 遗漏三处（均轻） | ①`debug_enabled_classes`（serialize.py:267-284/api.py:245/types.ts:23，值已全是 node_id、前端零消费，应改名或删）；②apps docstring 5 处过时 class_id 文案；③gate_collector.py:10-12 注释 |

### 替代方案裁决（B/C/D 全弃）

- **B（detector 显式传 nid）**：`detect()` 签名拿不到 node_id（node_id 是引擎层概念，detector 阶段恒 None，core.py:68）；反向注入破坏走势-无关分层；13 构造点 vs wrapper 1 处。弃。
- **C（spec 层非类名 tag）**：与 node_id 一一映射纯冗余=class_id 换名还魂。"彻底"的划线判据（arch-skeptic 对辩精确化）：**是否承担类型-身份轴职能（分组/过滤/归属键）**——`gate_name`（判据名）合法，spec tag 用于分组即还魂。弃。
- **D（code_location/gate_name 当分组键）**：分组键语义错位，用户心智是"哪个 node 失败"非"哪个文件"。弃。

### A' 最终形态（= A 骨架 + 五处收紧）

1. **TopoNode.class_id 删字段**（spec.py:21/24 投影产物，全 repo 零读者——比 A 更简：A 预估的"web 消费迁移"不存在）。
2. **GateFailure 删 class_id、加 `node_id: str = ''`**（带默认值，13 生产 + 6 测试构造点全 kwargs 形态，删 kwarg 零位置参数风险）；值由 gate_collector per-node wrapper `replace` 注入（一处改，detector 作者零感知）。
3. **debug 四门→三门**：debug_ctx 删 class 门/_read_class_id/DEBUG_EVENT_CLASS；30 埋点删 `class_id=` kwarg；api/前端删 event_class 通道；**右键 debug e2e 进验收**（顺手修复双 bug，见 §5）。
4. **产-gate detector 共享窄禁令**（消灭状态优于处理状态；产 gate 三 atom detector 无状态全量 detect、共享零收益 × on_gate 需单 node 挂载 = 矛盾状态应消灭）。不碰 down/side 共享 TrendDetector 的合法场景。挂载位置的团队分歧与 lead 裁定见 §4。
5. **变更清单补齐三处**（上表 web 变更面）。

## Q3：多维度评估（coder 主笔，arch 上升）

- **新 detector authoring**：现状模板（throwback_v1）= 8 处 `class_id=XXX.__name__` 样板（7 debug_break + 1 GateFailure helper；v3 形态 9 处）→ A' 后 **0 处**；**全 atoms 43 个传值点全消**；零新增必写项（wrapper 零感知、GateFailure 加默认值零改兼容）。"类名漂移静默失败"有 3 处历史前科（skill 踩坑清单 SKILL.md:165-166、v3 复制注释自认 v3.py:55-57、d64083be 现 bug）→ A' 后该类错误**物理消失**（没有可错的值）。
- **概念账**：声明层 −1（死字段）；detector 层 −1（样板+同步点+skill 对拍维度全消）；web 层身份轴统一（`__name__` 反射对齐胶水消失）；debug 层四门→三门。新 detector 概念集 4→3。
- **★ 新维度——概念的文档半衰期**（arch 上升）：skill 是 AI authoring 的教学源，代码清、skill 不清 = 概念复活通道。已发现 2 份必须同步：`authoring-path2-detector` reference.md（97-99 stale，还在教已消灭的旧体系）、`diagnose-event` detectors/（按类名组织）。**"彻底"的执行范围 = 代码 + 契约 + skill 三层**。
- **实施面盘点**（coder）：后端 10 文件 + 前端 5 文件 + 测试 24 文件 107 处（重灾区 test_debug_ctx 42 / test_v3_debug_anchor_kinds 17 / test_diagnose_class_env 21 / test_diagnose_time 10）+ skill 文档 2 份。dag_spec 层零代码改动（NodeSpec 本无 class_id 字段）。老 scan 文件兼容成本为零（gf 不落盘）。

## 4. 分歧裁定记录（lead，含最终轮变化）

**分歧**：产-gate detector 共享的窄禁令挂哪——skeptic 终稿主张 PatternSpec 声明期校验（`hasattr(detector,'on_gate')` 判据）；coder 主张 attach_and_collect 哨兵（~4 行）；arch 裁定轨迹三轮（哨兵→接受禁令→**终稿转回哨兵**）。

**终裁（skeptic 终轮行权提出第三选项后）：attach 侧延迟 raise（挂雷式）**——attach_and_collect 用 seen dict by `id(det)` 检测同一 detector 对象被 ≥2 node 引用（**零作者配合**）；共享时覆盖挂 `_boom` wrapper，**该 detector 首条 gate failure 真到达时 raise RuntimeError**（报错文案带修法"产 gate failure 的 detector 须一 node 一实例"）。零误杀：TrendDetector 等合法共享从不 emit gf → 雷永不动 → 正常运行；错误直达 author 且首炸于首次真实扫描（bo/tb gf 高频必触发）；检测点与错误发作点 100% 重合。~8 行 + 辅（authoring skill reference §4 补一句共享禁令提示）。

**冒泡面实证（coder 终轮验证，全四点可行）**：engine.py 零 try/except（raise 从 on_gate 回调无损冒泡）；scan.py:136-137 与 eval_runner.py:117-118 均为 `except Exception → per-symbol error`（不裸崩进程池，错误进 symbol 级结果）；api /diagnose 走 FastAPI 默认 500（需 400 再加两行，非必需）。三路径均 finally detach/pop 零泄漏；**零专门异常类型、零额外行数**（现状 except Exception 已全覆盖，skeptic 担心的专门异常类型转 scan error 不需要）；eval 不豁免（豁免=开洞+多代码）。trend.py 零 on_gate 调用实证——down/side 合法共享在挂雷形态下零行为差异。实施细节（_boom 报错文案含 detector 类名+修法、非法共享真 emit→raise 含修法关键词测试、合法 Trend 共享零行为差异测试、detach 复位回归锚）见 coder-notes §10 附节末。

裁定轨迹（诚实记录，三轮收敛）：
- 第一轮收口：attach 期立即 raise + `hasattr(detector,'on_gate')` 过滤（判据依赖类级声明；存量五处全有：breakout.py:124/:238、throwback.py:282、throwback_v0.py:366、throwback_v1.py:398、throwback_v3.py:265，模板自带零新增，漂移只剩假阳性方向=误拦报错，安全）。
- coder 终稿曾主"哨兵值降级"，核验 skeptic 三条反驳（论域滑动/注释循环论证/哨兵显示层语义未定义）后全部成立、干净认错撤回；gf.node_id 在共享产 gate 场景结构上无真值（on_gate 是实例属性、gate_collector.py:41-44 attach 无条件赋值、单槽后写胜），哨兵值无下游消费价值。
- **skeptic 终轮**：认输声明期禁令（arch 递归缺陷论在时间维度成立），行使修正权提出**延迟 raise**（判据沿用 seen-dict、行为改 raise）——融合"raise 行为（skeptic）× seen-dict 判据（coder）× 运行时真值（arch）"三方最强论据。**论据强度修正（coder 终轮实测，诚实记录）**：原引"忘写类级声明但 emit gf 且被共享 → hasattr 静默漏判 vs 延迟 raise 正确炸"的对比按现有 atoms 形态不成立——产 gate detector 生产路径裸读 `self.on_gate`（breakout.py:141、throwback 系透传），忘写类级声明的 detector 首次 detect 即 AttributeError，物理活不到 attach/共享场景；该对比仅在 getattr 防御式读法的理论边缘成立。延迟 raise 的实际优势为：判据更简（零判据维度，连 hasattr 都不需要）+ 零误杀由"不 emit 不炸"天然保证 + 覆盖防御式读法边缘。终裁结论不受影响（判据简与零误杀论证独立成立）。skeptic 对静默哨兵的两点终局保留：a) 哨兵行显示层语义未定义（下拉过滤归哪类？全显=重复计数、单列=新 UI 概念）；b) 静默降级在单人开发流可能永不被察觉（成百上千条 gf 中一行 node_id='' 淹没）。lead 终裁采纳第三选项为 A' 第 4 条最终形态。

skeptic 首选的 spec 声明期禁令仍记为可选增强；其异议与优先序全文 skeptic-notes §9。时序说明：arch 终轮通报与 lead 终裁交错（其"维持 hasattr 版"基于终裁前文本）；其对延迟 raise 的独立评估为"判据纯度严格不劣于 hasattr 版（零反射依赖/零假阳性/发作点字面重合）"、并已告知 coder 实施倾向 gf 到达检测无异议——与终裁同向，无未决。**降级/置哨兵值形态确认淘汰**（arch 第一轮与 skeptic 均曾否决"置空→新 unknown 语义"：那是处理状态而非消灭状态；arch 终稿转述中的"node_id='' 降级"按此纠正）。skeptic 首选的 spec 声明期校验记为**可选增强**（若未来要求不跑 attach 也能发现非法共享再升级；其反驳③"spec.py:209-228 _validate_render_grid 已有读 detector 声明属性的校验先例"成立，升级无机制障碍）。

论据沉淀（供实施者理解为何 attach 优先）：
1. 判据有效性等价（arch 收口修正，2026-08-14 终轮）：spec 期与 attach 期判据是同一 hasattr 反射——类级 on_gate 声明现状五处全有（breakout.py:124/:238、throwback.py:282、throwback_v0.py:366、throwback_v1.py:398、throwback_v3.py:265；模板/协议自带，零新增成本），漂移风险只剩假阳性方向（声明了不 emit 又被共享 → 误拦报错，安全方向、教育作者）。两形态剩余差异纯实施细节，终裁选 attach 期另有理由 2/3；arch 三轮论据错误根源（从 core.py Protocol TYPE_CHECKING 推断而未 grep atoms）已记 arch-notes §2.1。
2. **检测点与错误唯一发作点重合**：共享归属错误只在 gate failure 被 collect（attach 场景）时发作；author 写 spec 时并不知道哪个 detector 产 gate（要读源码才知道），声明期报错的时机优势实际价值很小。
3. skeptic 对 coder 的有效反驳记录在案：coder"spec 层 raise 推翻 docstring 载明合法共享"系论域滑动（窄禁令不禁无 on_gate 的 Trend 共享）——该弱理由作废，不影响收口（收口另有独立理由 1/2）。
4. **机械面先例齐备（coder 亲验）**：throwback.py:299-307 旧版 detect 层已有真·on_gate 包装先例（wrapper 链式兼容：detect 内层 → collector wrapper → collector.add）；gate_failure.py:71-72 code_location 默认值字段先例（新字段 node_id 同款兼容手法）。

此分歧为实施细节级——四方对"消灭产-gate-detector 共享状态（raise，非降级）"本身无分歧。

## 5. 附带发现（随 A' 修复/清理）

1. **双 bug 链**（d64083be 引入，A' 第 3 条顺手修复）：view.ts:825 传 `event.node_id`（'tb'）→ api.py:293 `DEBUG_EVENT_CLASS='tb'` ≠ 后端比较的 `'ThrowbackEventV1'` → debug_ctx.py:79-81 class 门恒 false 不 pause；同时 diagnose.py:215 过滤恒空 failed_attempts。两者只影响右键 debug 路径（入口 A 正常）——与用户"点击失效"观察吻合。验收须含右键 debug e2e。
2. **stale 残渣**：scripts/gate_burst_2x2.py:94 运行必 AttributeError（实测 `e.class_id` 不存在）；try_conplex_where/dag_spec.py:50、bottom_burst/dag_spec.py:60 docstring 旧体系文案。
3. **baseline 说明**：历史 baseline 提法的 `test_throwback_debug_anchor_kinds 4 failed` 已被后续 commit 修复转绿；当前后端 0 failed。

## 6. 对第一轮（lead context.md）的事实证伪（三人独立收敛）

1. class_id 源头之一实为 **TopoNode.class_id**（spec.py 投影产物）而非 NodeSpec（nodes.py 无此字段）；且全库零读者，删除零连带。
2. "gate 失败不产出 event"以偏概全：phase2_break/weak 产 event 且 emit gate（throwback_v1.py:253-270）——不影响 A' 前提（gf 不持有 event 引用）。
3. 基数修正：debug 埋点 30 处（非 ~28）；GateFailure 生产构造点 13 处（非注释称 10）。

## 方向定位（arch）

本次是 2026-08-06 三轴身份方案的收尾：身份概念收敛为 **node_id + instance_id 双轴，event_cls 退回 Python 类型系统、不再进入字符串契约**。前端已完成 node_id 化（anchorsOf/tbAnchorProfile），后端 debug class 门是链路唯一残留 `__name__` 环节——A' 是修断层，不是新设计。
