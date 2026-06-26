# web-loop 全面审核 — Team 共享 Brief

## 任务
对 web-loop skill 做全面审核,产出 final_report.md 落在本目录。

**用户核心问题**:
1. 还有哪些**不足的硬伤**(破契约 / 红线 / 内部不一致 / latent bug / 实操痛点)
2. 还有哪些**设计不合理**(过度设计 / 复杂度堆叠 / 反 YAGNI / 内部矛盾 / 抽象错位)
3. 是否能够承担**自动改进**的职责(meta-agent / decision_log / forbidden / reviewer_stuck 等机制是否实质支撑了"无人值守自动改进")
4. 需要哪些**改进**(可行改动清单)
5. 注意评估改进的 **token 成本**(每条改动的代价 vs 收益)

## 关键文件(只读)
- `.claude/skills/web-loop/SKILL.md`(已实施一轮 P0+P1 全套 + 第二轮 plan dedup)
- `.claude/skills/web-loop/principles.md`(评审准则)
- `.claude/skills/web-loop/workflow-template.js`(670 行 ESM Workflow 脚本)
- `.claude/skills/web-loop/examples/path2.md`(项目特化范例)
- `.claude/skills/web-loop/tests/*.mjs`(已有测试覆盖)

## 已知相关 research(可选 Read,信息密度高)
- `docs/research/2026-06-21_web-loop-decision-layer-redesign/final_report.md`(P0+P1 决策层 redesign)
- `docs/research/2026-06-19_web-loop-goal-persistence/final_report.md`(GOAL 三件套)
- `docs/research/2026-06-03-web-loop-skill-feasibility.md`(初始可行性)
- memory `~/.claude/projects/-home-yu-PycharmProjects-Trade-Strategy/memory/project_web_loop_decision_layer_redesign.md`

## 关键 memory 上下文(已浓缩)
- web-loop 是用户已落地的多轮自动评审 skill;唯一真实使用者 = path2(扫描+ECharts canvas UI)
- implementer = opus(SKILL 例外条款);其他 sonnet
- 已实施:GOAL 三件套 + 三判据(oscillating/treadmill/missingStates)+ paused 续修 + P1 meta-agent(forbiddenApproaches 注入下轮 implementer)+ reviewer_stuck 信号回流 + 第二轮 plan dedup(reviewerPrompt 加 planDedupBlock 自查)
- 历史 reviews 窗口刚砍到 N-1 only(传递性论据,2026-06-22 commit 02420b4+137874f)

## Team 分工(三 teammate + lead)

### teammate A · architect_critic
**focus**:架构合理性 + 通用性边界 + 反模式
- capture/review 解耦的实然 vs 应然落地
- 智能入口层(主会话内,SKILL §2a/2b/2c)的现实负担与可靠性边界
- GOAL 持久化三件套(goal.md + goal.json + refs/)是否过度
- reviewer 永久零浏览器红线在 path2 实测后是否仍最优(canvas/stateDumps 路线)
- 通用性宣称("通用于任意 web 项目")vs 仅 path2 实测的现状
- args 字段集是否仍 minimal(11+ 字段的复杂度)
- SKILL.md 内已实施 vs 已 cargo-cult-doc 的边界

### teammate B · autoimprove_critic(用户特别关注)
**focus**:自动改进能力 = "无人值守跑 N 轮后是否真能解需求"
- P0 §3.4 三机检判据(oscillating/treadmill/missingStates)的失败模式覆盖率
- P1 meta-agent(opus,forbiddenApproaches/prioritizedMustIds/escapeRequest)三字段够不够、缺没缺
- decision_log + forbiddenApproaches 注入 implementer prompt 优先级 3 的实效:implementer 真会规避吗?
- reviewer_stuck 信号回流(implementer 中转,reviewer 不读历史 reviews)的盲点
- planDedupBlock(reviewer 自查 + 临界规则强制换主线)的真实兜底强度
- 续修协议(paused.md + human-hint 三选一)与 resumeFromRunId 同 session 限制的实操痛点
- 是否仍存在"自动改进自己改不动 / 必依赖人"的硬阻塞;若有,人介入门槛(写 human-hint vs 直接手工修)的 cost-benefit
- 5 级 prompt 优先级模板(P1-P5)的实效:implementer 真的按层级听话吗?

### teammate C · cost_critic
**focus**:token 成本 + 改进 ROI
- 估算单 run 全程的 token 量级(setup + iterate N 轮 + finalize)
  - implementer = opus(单轮大约多大 prompt + 输出)
  - reviewer ×3 lens(opus / sonnet?读 SKILL 确认)× N 轮
  - capture / smoke / refresh / persist sonnet 段
  - P1 meta-agent opus 每次触发
- 估算 maxRounds=6 / staleRounds=2 默认配置下的典型 total tokens
- A / B 给出的改进建议,逐条估 token 影响(增加 prompt 段、增加 schema 字段、增加 sub-pass、增加 agent 调用)
- 哪些改进**净降低 token**(收紧 prompt / 早 stall / 删冗余 schema)
- 哪些改进**显著增 token**但 ROI 高
- 哪些改进 token 成本 vs 价值不划算 → 应放弃

## 工作流
1. **Phase 1 · 独立调研**(各自先深读、各自产 raw findings)
   - 每个 teammate 在本目录下产中间 md(`A_raw.md` / `B_raw.md` / `C_raw.md`)
   - 字段:硬伤清单 / 设计不合理点 / 改进建议(B 额外:自动改进职责评估)
2. **Phase 2 · 跨 teammate 交叉验证**(SendMessage,聚焦关键发现互相挑战)
   - A → B:架构反模式是否阻塞自动改进
   - B → C:改进建议的 token 含义
   - C → A:成本最优的精简点是否影响架构正确性
   - 每个 teammate 收到挑战后修正或坚持,在 raw md 末尾追加"交叉验证修正"段
3. **Phase 3 · lead 综合**(lead 读三份 raw md + SendMessage 历史,综合写 final_report.md)

## 红线
- 全程**不动代码**;只读 + 思考 + 写 md
- final_report.md 必须 actionable(每条改进 → 具体文件位置 + 改动幅度 + token 影响估)
- 不空泛("应增强自动化"是空泛 — "在 P1 meta-agent schema 加 `reviewer_lens_disagreement_count` 字段触发 escapeRequest"才是 actionable)
- 严禁动机性推理(memory `feedback_argument_discipline`)
- 别假装 path2 之外的项目已落地;通用性宣称要区分"骨架通用" vs "实测通用"

## 输出
最终产物 = `docs/research/2026-06-22_web-loop-comprehensive-audit/final_report.md`(lead 写,综合所有 teammate)
中间产物 = `A_raw.md` / `B_raw.md` / `C_raw.md` + 各自交叉验证段
