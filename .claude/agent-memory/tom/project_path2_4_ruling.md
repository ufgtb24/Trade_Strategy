---
name: path2-4-ruling
description: tom 对 Path 2 #4 (stdlib Event/Detector 模板) brainstorming 阶段的第一性原理裁定结论
metadata:
  type: project
---

Path 2 #4 = stdlib 常用 Event 类 / Detector 模板。tom 于 2026-05-17 brainstorming 阶段给出收缩裁定:

- 进 stdlib 仅 2 个:`BarwiseDetector`(逐 bar 扫描 ABC,用户实现 `emit(df,i)`→自己的领域 Event 子类,唯一 Detector 模板)、`span_id`(纯函数 id 生成器,单点退化)。
- 砍掉:**BarEvent**(adopt gate 复审证伪:无 dogfood 证据/#4 内无消费者,用户真实 L1 总是带领域字段的 Event 子类,与被砍的 VolSpike 同把尺)、VolSpike/MACrossOver/Peak/BO(无 dogfood 证据或违反 §0)、DataSource 协议(协议层 Any 瘦核已验证)、ThresholdDetector(Barwise 退化特例)、FSMDetector/WindowedDetector(零证据)、span_of/.features 补充(协议层已够)。
- #4 不沉淀任何 Event 类;`BarwiseDetector.emit` 返回 `Optional[Event]`(协议层基类),用户构造自己的子类。
- **D1 定稿(别名方案被 test_ids.py:9 硬证伪后)**:`default_event_id` 原样冻结=#3 内部专用(s==e 输出非塌缩 `vc_5_5`,已 pin,_advance.py:121 依赖,不进公开出口);`span_id`=全新独立公开函数(s==e 塌缩 `kind_i`/区间 `kind_s_e`),`path2.span_id` 出口。二者语义本质不同(#3 标跨成员 span 恒区间;#4 标单点事件)、刻意不归一、互不依赖——奥卡姆正解(实体数=必要语义数,flag 归一才是过度设计)。`_ids.py` docstring「#4 替换本桩」预期作废。
- **痛点2 红线理由已修正(§7.4 实现核查证伪"Kof 覆盖"声明)**:Kof = 固定 n 元 k-of-n 边松弛(`_kof_dfs:310` 全 label 必赋值,松弛的是边满足数非成员数),**不覆盖** dogfood VolCluster 的"同流滑动窗口 ≥N 计数";且单流复用多角色被 `resolve_labels:46-57` 同类名冲突拒绝/`_kof_dfs` 允许同事件多 label 选中而退化。红线(#4 不造 WindowedDetector/任何贪心计数 detector)**不变**,但理由从"已被 Kof 覆盖"改为"该滑动计数样板无足够复用证据进 stdlib(dogfood 仅用一次),使用方自管,待 #5/#7 真实重复再立"。
- **§7.4 验证降级**:Kof 不能 pin 死复刻 dogfood 2 簇(`vc_60_67`/`vc_264_267`)。§7.4-A=L1 等价+模板无循环(D3 核心,充分);§7.4-B=Kof 串联改为诚实 pin 真实产出,单任务两步(步骤1 首跑得真值→步骤2 同任务回填字面量断言,不留 TODO),只验"#4 产出能喂 #3+run() 链式贯通",不复刻旧贪心。
- spec §7.2(d) runtime check 生产默认 判定出 #4 范围,归 #7 远期。

**Why:** 用户要 YAGNI 狠砍 + 奥卡姆;dogfood §5 痛点是裁定唯一证据来源。
**How to apply:** 后续 #4 spec/plan SendMessage 追问时以此为基线;若 plan 试图引入 WindowedDetector 或捞回 runtime-check 默认,按本裁定挡回。详见对话裁定原文,roadmap 指针见 [[project_path2_roadmap_pointer]]。
