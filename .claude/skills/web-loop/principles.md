# principles.md —— Web 迭代改进评审准则(reviewer 与 implementer 共享)

> 本文件是「绝对评分标准」。reviewer 用它判 PASS/FAIL,implementer 用它知道"什么算合格"。
> 双方读同一份,不另设私有 checklist。
> 配合用户提供的 `rubricPath`(项目验收 spec)一起用:本文件给通用底线,spec 给项目特异硬款。

## 0. 总则(最重要,先读)

1. **绝对标准,不是相对找茬**。判定依据是"**当前实现是否满足本次需求(GOAL)+ 下列各轴的硬条款 + 项目 spec**",
   **不是**"我还能不能想出更好的做法 / 还能不能挑出毛病"。满足 = PASS,哪怕不完美、哪怕你能想到更优雅的写法。
   ⚠ 违反此条会导致评审永不收敛(永远挑得出新毛病)。这是本准则存在的首要理由。
2. **问题分两级**:
   - **MUST**(阻塞):违反 GOAL 的核心要求,或违反某轴下标【MUST】的硬条款,或真实 bug/回归。**有 MUST 未解 → 该轴 FAIL**。
   - **NICE**(不阻塞):GOAL 与各轴硬条款都未要求的改进建议。**记录入工作队列,但不阻塞 PASS**。
3. **默认 disposition = changes_requested(尚不可批准)**。只有一个 lens 名下**无任何 open 的 MUST** 时,该 lens 才 PASS。
   全部 lens PASS → 整体 approved。approve 是例外不是默认。
4. **scope 纪律**:GOAL 与项目 spec 标为 Out-of-scope / 明确不做 的东西,**不得列为 MUST**(至多 NICE,或直接不提)。
   防止把"范围外的理想"当成阻塞,退化成无限找茬。
5. **devil's advocate 的正确用法**:严格审"有没有真违反 GOAL/硬条款的硬伤",但**绝不提你自己的替代方案**——
   写成"GOAL/spec 要求了 X 却缺失 / 这里有 bug Y",**不是**"应该改用 Z"。你指出缺陷,不设计方案。
6. **完整性铁律**:不为让循环收敛而假装 PASS;不为凑数把 NICE 谎报成 MUST;不伪造未做的验证。如实判。
7. **reviewer 永久零浏览器(架构铁律)**。reviewer 只 `Read` capture 层已截好的 PNG + 读 git diff/console 文本,**绝不自己开 playwright(MCP 或脚本都禁)**。持有浏览器只属于 capture 单层。违反此条 = 重复采集 +(用 MCP 时)多 agent 抢同一浏览器**串台**(截到别的 reviewer 的页面)。
8. **scope 内只判已截到的证据**。若某判断需要"点了之后才能看到"的状态,那是**capture 层多加一条 state**(写进 states 清单),不是 reviewer 自己去点。capture 产出的 **stateDumps(状态探针)与截图同级,皆为合法证据**——canvas 交互无视觉差异时据 stateDumps 判定。
9. **反锚定 + 正面结论走 verified 通道**。对已知问题表态 stillPresent 必须引用**本轮**证据(截图文件名/字节数/stateDumps/manifest 字段),禁止沿用上轮表述;本轮证据与旧结论矛盾时以本轮为准。issues 只承载缺陷;"已修复/验证通过/全绿"等正面结论一律放 verified 数组,任何 severity 都不得记为 issue。must 仅因证据缺失无法判定(非确证违反)时标 `unverifiable:true`。

---

## 评分轴 ↔ reviewer lens 映射

| 轴 | 负责 lens | 一句话 |
|---|---|---|
| ① 需求满足度 | **func** | GOAL 每条要求是否真的实现,逐条可追溯 |
| ② 功能正确性 | **func** | 交互链路通、无运行时错误 |
| ③ UX 质量 | **ux** | 布局/层级/可见性,无视觉缺陷 |
| ④ 代码质量 | **code** | 无 bug、复用、简化、不引入回归风险 |
| ⑤ 无回归 | **code** | 既有测试通过、既有功能不破坏 |

---

## 轴 ① 需求满足度(lens: func)
**判据**:把 GOAL 拆成可勾选的子项,逐条对照当前实现。
- 【MUST】GOAL 明确要求的每一条功能/行为都已实现且可被观察到(截图或交互验证)。任一条未实现 = MUST-FAIL。
- 【MUST】实现的语义与 GOAL 一致(不是"做了个相似但不对的东西")。
- 【NICE】超出 GOAL 的额外增强。
- **PASS**:GOAL 每条子项都能在界面/行为中追溯到。 **FAIL**:有 GOAL 子项缺失或语义不符。

## 轴 ② 功能正确性(lens: func)
**判据**:关键交互链路端到端跑通,无运行时错误。
- 【MUST】核心交互链路可完成(本项目链路占位:〔项目特化:填本项目主链路,path2 见 examples/path2.md §4〕)。
- 【MUST】**无 console error、无 pageerror、无未捕获异常**(console error/pageerror 体现在 capture 产出的 manifest 文本里;func reviewer 读这些文本判定,不自截)。
- 【MUST】无 4xx/5xx 破坏性网络错误致功能不可用(预期内的 404 如"扫描进行中"除外)。
- 【NICE】边缘 case 的优雅处理(空态、加载态文案)。
- **PASS**:主链路通 + 控制台干净。 **FAIL**:链路断 / 有 console error / 关键请求失败。

## 轴 ③ UX 质量(lens: ux,主要靠看截图)
**判据**:对照截图评布局与可用性。绝对底线是"无明显视觉缺陷",不是"达到设计大师水准"。
- 【MUST】**无布局崩坏**:无元素溢出/截断、无列被挤压到不可读、无面板/侧栏被意外撑没或重叠遮挡(这些是 web 前端反复出现的真实布局 bug)。
- 【MUST】关键交互元素**可见且可达**(按钮/开关/可点区域没被遮挡、对比度足以看清)。
- 【MUST】状态切换有正确视觉反馈(如开关 role 后图面确实变化)。
- 【NICE】间距/配色/动效/信息密度的美化建议。
- **PASS**:布局不崩 + 关键元素可见可达 + 状态反馈正确。 **FAIL**:有任一视觉缺陷 MUST。

## 轴 ④ 代码质量(lens: code,主要靠读 git diff)
**判据**:读本轮改动,审正确性与是否埋雷。
- 【MUST】本轮改动**无逻辑 bug**(空指针、错误边界、错用 API、状态未更新)。
- 【MUST】**不违反项目架构红线**(〔项目特化:填本项目架构红线,path2 见 examples/path2.md §4〕)。
- 【NICE】重复代码可抽取、过度复杂可简化、命名可改进、可复用既有工具未复用。
- **PASS**:无 bug + 不破架构红线。 **FAIL**:有 bug 或破红线。NICE 项不挡 PASS。

## 轴 ⑤ 无回归(lens: code)
**判据**:既有测试与既有功能不被本轮改动破坏。
- 【MUST】**既有测试套件通过**。〔项目特化:填本项目 smoke 命令(= workflow 的 smokeCmd),path2 见 examples/path2.md §4〕
- 【MUST】本轮未破坏 GOAL 之外的既有功能(reviewer 抽查与本轮无关的关键链路是否仍正常)。
- 【MUST】若上一轮某问题已 fixed,本轮不得使其复现(regression)。
- **PASS**:测试全绿 + 既有功能未退化。 **FAIL**:测试红 / 既有功能被破坏 / 出现 regression。
  (注:此轴与 workflow 的 smoke 回归 gate 协同——smoke 红会先触发回滚;此轴是 reviewer 的二次人工复核。)

---

## capture / review 解耦(为何这样设计)

**判据(决定"浏览器并发度"的不是 reviewer 怎么分)**:是否需多 agent 并发持浏览器,只取决于 **capture 是否需要并发推进多条「有状态、各异的交互轨迹」**,与 reviewer 的维度数/功能数无关。reviewer 消费的是 PNG/console/diff,不是浏览器控制权。

- **功能 × 维度是正交两轴**:`states 清单(行=功能/界面)× lenses(列=ux/func/code)`。capture 填行(多截几态),review 填列(多并行几个 lens)。多界面 ⇒ capture 多截几态,**reviewer 数不随界面膨胀**。
- **串台只属于"共享一个 MCP 单例浏览器"**。独立 `chromium.launch()` 实例(含 `channel:'chrome'` 系统 chrome)天生不串台(已实测:3 实例并行各截各的)。所以 reviewer 各自持浏览器才是串台根源——禁止;capture 单点串行独占,绕开串台。
- **效率(ρ=重叠度判据)**:web-loop 三 lens 看同一批被改界面(高 ρ),单点 capture 截一次、三 reviewer 复用 = 严格最优;"reviewer 各自截"在高 ρ 下是 ρ 倍重复浪费。仅当 states 海量、单态慢、分叉不可串行复用时,才在 **capture 层内部**开"独立 chromium 并行"(无 reviewer 语义、无串台),**绝不**在 review 层开"各持浏览器"。

## 项目特化占位(复用到其他项目时填这些)
本文件给通用底线;每个轴里标〔项目特化:…〕的占位,由对应项目填值。**path2 的全套特化值见 `examples/path2.md` §4**(核心链路 / 架构红线 / smoke 命令 / 项目 spec)。换其他项目时照 `examples/path2.md` 的结构另写一份 `examples/<项目>.md`。
