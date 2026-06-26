// web-loop skill 的 Workflow 脚本模板(参数化,与 principles.md 配套)。
// 主会话读本文件作为 Workflow({script}) 的 script,args 由 skill 注入。
// 验证:裸顶层 node --check ✓(顶层 throw/await 合法)+ tests/dryrun.mjs 场景全绿。
// ⚠ 禁 Date.now()/Math.random()(破坏 resume);fail-fast 用 throw —— 顶层 return 在 ESM module 非法。
// 2026-06-12 改进(docs/tmp/2026-06-12-web-loop-skill-improvements.md):stateProbe 第二证据通道/
//   吞异常禁令/capture 跨轮记忆/反锚定/verified 通道/台账冻结 staleness/exitReason 三值/
//   verdict 台账推导/unverifiable 单列。
export const meta = {
  name: "web-iterate-review",
  description: "多轮迭代改进运行中的 web:pw自检→preflight→[implement→smoke gate→refresh→shoot→并行review→收敛]",
  phases: ["setup", "iterate", "finalize"]
};

// ── args(skill 注入)──
// ⚠ Workflow runtime 把传入的 args **整体序列化成 JSON 字符串**(实测 typeof args==="string"),
//    必须先 parse 再解构,否则字段全 undefined → 第一个 agent 因空 URL 崩。
//    对两种入参都安全:字符串走 JSON.parse;对象(mock dry-run / 未来 runtime 改动)直接用;parse 失败兜底 {}。
const A = (typeof args === 'string'
  ? (() => { try { return JSON.parse(args) } catch { return {} } })()
  : args) || {};
const URL=A.url, GOAL=A.goal, WORKDIR=A.workdir, RUBRIC_PATH=A.rubricPath, RUNTAG=A.runtag;
const GOAL_SUBGOALS = A.goalSubgoals ?? [];
const REF_IMAGES = A.refImages ?? [];
// ★ P3-3:默认值调整(2026-06-22 audit B#15):maxRounds 6→5(80%+ run r2 触发 P1,5 轮已足);
//   staleRounds 2→3(P1_TRIGGER_STREAK=max(1, STALE_ROUNDS-1)=2,P1 在 r2 触发对齐;原 2→1 太激进)
const MAX_ROUNDS=A.maxRounds??5, STALE_ROUNDS=A.staleRounds??3, SCAN_SUBSET=A.scanSubset??null;
const SMOKE_CMD=A.smokeCmd??"echo no-smoke && false", RESTART_CMD=A.restartCmd??null, HEALTH_URL=A.healthUrl??null;
const UI_DIR=A.uiDir, SHOTS_DIR=A.shotsDir, REFRESH_DATA_CMD=A.refreshDataCmd??null;
const REVIEW_LENSES=A.lenses??["ux","func","code"];
// capture 后端:mcp(默认,系统chrome,白送console) | script(channel:chrome串行) | script-parallel(逃生口,多独立实例并行)
const CAPTURE_BACKEND=A.captureBackend??"mcp";
// capture 要观测的状态轨迹清单(矩阵的行=功能轴);默认=项目无关最小自洽态(首屏)。
// ⚠ 保留 ?? 兜底:它是"无 states 也能 dry-run"的来源,不可删空。具体项目传 states 字段覆盖(示例见 examples/<项目>.md)。
const STATES=A.states??[
  { state:"01-initial", recipe:"goto '/' 等 networkidle + 1000ms(首屏)" },
];
// 共享片段(一处定义、多处复用):系统 chrome launch 行 + capture manifest 形状
const CHROME_LAUNCH="import { chromium } from '@playwright/test';chromium.launch({ channel:'chrome', args:['--no-sandbox','--disable-dev-shm-usage'] })";
const MANIFEST_SHAPE="返回结构化 manifest:shots[{state,path,bytes,error?}] + consoleErrors[] + pageErrors[] + failedRequests[] + stateDumps{state→probe结果}(带 probe 的 state 必填;无 probe 可省)。";
// 吞异常禁令:取证失败的原因本身就是证据(实证:TypeError 被 catch 静默吞 → 同一错法盲拍三轮)
const CAPTURE_ERR_RULE="⚠ 铁律:脚本/执行中任何 try/catch 兜底,必须把 e.message(连同可得的 stack 首行)原样写进该 state 的 manifest error 字段;禁止静默 return null/false 后换路硬试。";

// ── prompt 安全转义(M5.2 铁律,2026-06-19 web-loop GOAL 持久化设计)──
// 模板字面量内嵌用户字符串必须先 JSON.stringify 包裹避免 ${...} 重解析 / 截断。
function safeInsert(s) {
  if (s == null) return '';
  return JSON.stringify(String(s)).slice(1, -1)
    .replace(/\\n/g, '\n')
    .replace(/\$/g, '\\$');   // 防 prompt 文本里被 agent 误读为模板占位符
}
function safeBlock(s, fence = '```') {
  if (s == null) return `${fence}\n${fence}`;
  // 把用户串里的 fence 字符替换为零宽避免提前关闭代码块。
  const safe = String(s).replace(new RegExp(fence, 'g'), fence.replace(/`/g, '​`'));
  return `${fence}\n${safe}\n${fence}`;
}
function summarizeSubgoals(subgoals) {
  if (!Array.isArray(subgoals) || !subgoals.length) {
    return '(无 goalSubgoals — 智能入口层未拆子项,本次循环 GOAL 子项复核机制将不生效;详 final_report §5.1)';
  }
  return subgoals.map(g =>
    `- ${safeInsert(g.id)} · ${safeInsert(g.desc)} · verifiable_via=${safeInsert(g.verifiable_via)} · measurable=${safeInsert(g.measurable || '主观')}` +
    (Array.isArray(g.relatedRefs) && g.relatedRefs.length ? ` · refs=[${g.relatedRefs.map(safeInsert).join(',')}]` : '') +
    (Array.isArray(g.relatedStates) && g.relatedStates.length ? ` · states=[${g.relatedStates.map(safeInsert).join(',')}]` : '')
  ).join('\n');
}
function summarizeRefImages(refs) {
  if (!Array.isArray(refs) || !refs.length) {
    return '(无 ref — 本次 GOAL 纯文字驱动,reviewer 第一步建基准跳过 refs Read)';
  }
  return refs.map(r =>
    `- ${safeInsert(r.path)} · role=${safeInsert(r.role)} · ${safeInsert(r.description)}` +
    (Array.isArray(r.relatedSubgoals) && r.relatedSubgoals.length ? ` · subgoals=[${r.relatedSubgoals.map(safeInsert).join(',')}]` : '') +
    (r.relatedState ? ` · state=${safeInsert(r.relatedState)}` : '') +
    (r.downsampled ? ' · ⚠ 已降采样' : '')
  ).join('\n');
}

let issues=[], history=[], seqCounter={}, verifiedLog=[], lastShotErrors=[], subgoalCoverage={};
function nextId(lens,round){ const k=`${lens}-r${round}`; seqCounter[k]=(seqCounter[k]||0)+1; return `${k}-${seqCounter[k]}`; }

function mergeIssues(issues, present, round){           // lens-归属状态机(已对抗验证)
  const presentLenses=new Set(present.map(v=>v.lens)); const reportedStillIn=new Set();
  for(const v of present){
    for(const it of (v.issues||[])) if(it.matchesIssueId) reportedStillIn.add(it.matchesIssueId);
    for(const k of (v.knownIssuesStatus||[])) if(k.stillPresent) reportedStillIn.add(k.id);
  }
  const goneByOwner=new Set();
  for(const iss of issues){
    if(iss.status!=="open"&&iss.status!=="regressed") continue;
    const owner=present.find(v=>v.lens===iss.lens);
    const k=owner&&(owner.knownIssuesStatus||[]).find(x=>x.id===iss.id);
    if(k&&typeof k.unverifiable==="boolean") iss.unverifiable=k.unverifiable;
    if(k&&k.stillPresent===false) goneByOwner.add(iss.id);
  }
  for(const iss of issues){
    if(iss.status==="open"||iss.status==="regressed"){
      if(reportedStillIn.has(iss.id)) iss.lastSeenRound=round;
      else if(goneByOwner.has(iss.id)&&presentLenses.has(iss.lens)){ iss.status="fixed"; iss.lastSeenRound=round; }
    }
  }
  for(const v of present){
    for(const it of (v.issues||[])){
      if(it.matchesIssueId){
        const h=issues.find(x=>x.id===it.matchesIssueId);
        if(h&&h.status==="fixed"){
          h.status="regressed"; h.lastSeenRound=round; h.regressionCount=(h.regressionCount||0)+1;
          // ★ P0-1 part (i):regressed 时 append 新一轮 nextStepPlan 历史
          (h.nextStepPlanHistory ||= []).push({
            round,
            rootCauseHypothesis: it.rootCauseHypothesis || null,
            affectedFiles: it.affectedFiles || [],
            suggestedFix: it.suggestedFix || null,
            nextStepPlan: it.nextStepPlan || null
          });
        }
      } else {
        const dup=issues.find(x=>x.lens===v.lens&&x.title===it.title&&(x.status==="open"||x.status==="regressed"));
        if(!dup) issues.push({
          id: nextId(v.lens, round),
          lens: v.lens,
          title: it.title,
          severity: it.severity,
          unverifiable: it.unverifiable === true,
          status: "open",
          bornRound: round,
          lastSeenRound: round,
          // ★ P0-1 part (i):跨轮决策字段历史(供 planDedupBlock 自检 + reviewer 跨轮对比)
          nextStepPlanHistory: [{
            round,
            rootCauseHypothesis: it.rootCauseHypothesis || null,
            affectedFiles: it.affectedFiles || [],
            suggestedFix: it.suggestedFix || null,
            nextStepPlan: it.nextStepPlan || null
          }]
        });
      }
    }
  }
}

function reviewerPrompt(lens,{round,GOAL,RUBRIC_PATH,shotList,issuesJson,consoleNote,probeNote,verifiedJson,goalSubgoalsSummary,refImagesSummary,WORKDIR,stuckSignal}){
  const brief={
    ux:"你是 UX/界面 reviewer。主要靠看截图:Read 每张 PNG,评视觉/布局/层级/可见性(列挤压、侧栏被撑没、重叠)。优先核查数据最密集/渲染最复杂的那张(最易暴露布局崩坏)。**refs 处理:必读全图(按 role 三档严格区分)。**",
    func:"你是功能 reviewer。**首要任务 = 对照 GOAL 子项清单逐条复核(轴① 需求满足度)**,在 verified 数组覆盖每条子项的本轮证据。其次读 console/failedRequests 文本 + 看截图状态判功能。**refs 处理:看 description 摘要 + role 摘要;不强制 Read 图(对照 verifiable_via=screenshot 的子项时按需 Read)。**",
    code:"你是代码质量 reviewer。主要读 git diff,评 bug / 违反 rubric 红线 / 回归。截图仅旁证。**refs 处理:不强制读图,refs 列表仅供查阅(确认本轮 diff 与视觉目标无方向相左)。**\n⚠⚠ code lens 必填 4 决策字段(P0 §3.2,2026-06-21 final_report):每条 issue 必填 rootCauseHypothesis(≤2 句机制假设)+ 必填 affectedFiles(\"path:line\" 数组,本轮代码现场)+ 必填 nextStepPlan(策略级 3-8 行 plan,模板「读 X → 改 Y 主线 → 验证 Z → 不要再试 W」,**禁代码级** prescription——禁具体 old_string→new_string / 函数体 snippet / 行号 patch;仅写策略 + 风险 + 验证方法 + 禁止重试什么),suggestedFix 可选(若给出 implementer 可推翻)。ux/func lens 这 4 字段可空。",
  }[lens];
  const stalePrimer = `\n⚠⚠ 语义聚类 / mustStaleStreak 防脆性(P0 §3.3,2026-06-21 final_report):对所有 open must,**优先用 matchesIssueId 引用现有 id**,只有判定为「真新增 bug」(真实独立缺陷,非旧 bug 换措辞)才新立 issue id。reviewer 换措辞重写同 bug = mustStaleStreak 重置 = STALE 退出失效 = 用户反复迭代痛点直接来源。`;
  // ★ P1-5:合并 reflectBlock + planDedupBlock + 强制判断题(三段防 "plan 主线反复" 死循环 → 1 段)
  //   前置依赖 P0-1 三件套(nextStepPlanHistory 字段持久化 + stuckSignal 程序化注入)
  const dedupBlock = (round >= 2 && lens === "code") ? `\n【plan 主线自查 + reviewer_stuck 信号回流(code lens · round≥2,P1-5 合并段)】\n\n` +
`▶ 信号 A · 上轮 implementer 自报(workflow 程序化注入 from schema)\n${stuckSignal || '(无,Task 1 stuckSignal 未注入或上轮 ok=false)'}\n\n` +
`▶ 信号 B · 历史 nextStepPlan 自检(issuesJson.nextStepPlanHistory 字段)\n  本 prompt 上方 issuesJson 中每条 must 含 nextStepPlanHistory 数组(P0-1 part i 已持久化)。\n  对照你即将写的 plan 主线(affectedFiles 集合 + 修法核心一句话),与历史 nextStepPlan 主线对比:\n  · 若判断本轮 plan 与历史本质相同 → nextStepPlan 顶部加 "[同主线 r<N>] 原因:<具体失败证据>"\n  · 具体失败证据 = 引用上轮 impl.md 反根因 / git diff / console / 截图特征,可 grep 定位;\n    不接受 "再试一次" / "本轮重新尝试" 空洞理由\n  · 若举不出具体证据 → 直接换主线(不写 "[同主线]" 注释)\n\n` +
`▶ 临界规则 · 强制换主线\n  · 信号 A reviewer_stuck=true && 信号 B 判定主线相同 → 强制换主线(双信号最高确信)\n  · 若换不了(找不到其他根因)→ escapeRequest 标 reviewer_disagreement 退出\n\n` +
`▶ 真二选一倾向 · 默认查重收紧\n  · 信号 A reviewer_stuck=false && 信号 A 反根因为空 && 信号 B 判定主线相同\n    → 缺乏跨角色信号区分 case(a)plan 错 / case(b)impl 错 / case(f)刷新假阴\n    → 默认换主线(救 case(a)/(g) 优先;case(b) 走 implementer 反根因 + mustStaleStreak 兜底)\n    → 坚持重出必须举具体失败证据;无证据即换主线\n\n` +
`注:自检结果落入 nextStepPlan 字符串字面即可(可 grep "\\[同主线 r" 事后监控);不引入新 schema 字段。\n本段不破 reviewer 红线 — 信号源 implementer schema(下游可观察)+ issuesJson(状态机持久),非 reviewer 自己读历史 reviews。` : '';
  const refsReadInstr={
    ux:`【第一步 · 建立视觉基准(role 严格区分)】Read ${RUBRIC_PATH}(固定验收标准);再 Read ${WORKDIR}/refs/manifest.json,**按 ref role 三档分别处理每张图**:\n  · role=goal      → 这是"做成这样"的目标态。Read 它建立视觉基准 = 本轮截图应**靠近**它。\n  · role=baseline  → ⚠ 这是"改进前现状",**不是目标**!Read 它只为对比"本轮相对现状有无前进",**禁止把它当 goal 模仿**。\n  · role=anti-example → ⚠ 这是"勿做成这样"的负例。Read 它建立"应**远离**它"的反向锚,本轮截图越像它越是违反 GOAL。\n若 manifest.json 为空(refs/ 无图,用户未贴) → 本步骤跳过,直接进第二步;不报错。\n⚠ 此步在判 rubric / issues 之前必做(refs 非空时);跳过即默认本轮截图为基准 = 漂移。`,
    func:`【第一步 · 建立基准(轻量)】Read ${RUBRIC_PATH};Read ${WORKDIR}/refs/manifest.json 看每张 ref 的 role + description 摘要,**不强制 Read 图**;对照 GOAL 子项中 verifiable_via=screenshot 的几条时,按需 Read 对应 ref 图(看 relatedSubgoals 字段定位)。manifest.json 为空时跳过。`,
    code:`【第一步 · 建立基准(代码侧)】Read ${RUBRIC_PATH};refs 列表仅供查阅,**不强制 Read 图**;判 git diff 与视觉目标方向是否相左时,可选 Read 对应 role=goal 的 ref 摘要。`,
  }[lens];
  return `${brief}
⚠ 你是 review 层,**永久零浏览器**:只 Read capture 层已截好的 PNG + 读 git diff,**禁碰 playwright(MCP/脚本都禁)**。理由:持有浏览器只属于 capture 单层;reviewer 各自截图会重复采集 +(用 MCP 时)串台。看图足以判 rubric。
${stalePrimer}${dedupBlock}

【本次 GOAL(原文,逐字不变;完整版以 ${WORKDIR}/goal.md 为准)】
${GOAL}

【GOAL 子项清单(完整版以 ${WORKDIR}/goal.md 为准)】
${goalSubgoalsSummary}

【参考图(refs/,详 ${WORKDIR}/refs/manifest.json;⚠ role 三档严格区分,baseline/anti-example 禁模仿/反向远离)】
${refImagesSummary}

${refsReadInstr}

【截图 r${round}】
${shotList}
${consoleNote}
${probeNote||""}

【第二步 · GOAL 子项逐条复核】对照上面 GOAL 子项清单,每条:
  ⚠⚠ 关键:【evidence 必须绑本轮真实可定位证据】对每条子项,verified 数组的 evidence 字段必须含至少一项可被 grep 验证的标识:
    · screenshot 类 → 截图文件路径(精确到 \`<SHOTS_DIR>/<rtag>_<state>.png\`)+ 一句"哪几像素特征体现该子项"(如 "K线 grid 顶端到底端占视口 ≥640px / 视口 1080px = 0.59")
    · console 类   → console 输出行原文片段 + manifest.consoleErrors 索引
    · probe 类     → stateDumps 的 key 名 + 该 key 的本轮取值
    · diff 类      → git diff 中函数名 / 文件名 + 行号
  ⚠ 仅写"看起来满足" / "已实现" / "测试通过" 等不可定位修辞 = evidence 不合格,该子项 coveredSubgoals 不计入,收敛判据不通过。
  - 在 verified 数组里增一项 \`{ title: "G<id> · <desc>", evidence: "<本轮证据原文>", coveredSubgoals: ["G<id>"] }\`
  - 子项 verifiable_via 字段告诉你看哪类证据
  - 若证据不足以判定 → 在 issues 增一项 unverifiable:true,绑 matchesSubgoal: "G<id>";若是 STATES 缺失 → 同时填 requiredStates:[<state>]
⚠ 即使 issues 台账无新增,GOAL 子项仍要逐条表态——这是绕过"清 must 即 pass"的反锚定关。

【反锚定 · 先回讲 GOAL 再判 rubric】用你自己的话复述 GOAL(一两句)+ 列出本轮你判定的 GOAL 子项 id 集合 → 写进 verdict 的 goalEcho 字段。
⚠ goalEcho 字段仅作"开始判定前的注意力归位",**不作为 verdict / 收敛判定依据**。收敛判定看 coveredSubgoals 集合与 evidence 绑定(下面"绝对标准"段)。

【已验证项(各轮 verified 结论,勿重复质疑、勿再立 issue)】
${verifiedJson||"[]"}

【已知问题】逐条在 knownIssuesStatus 表态 stillPresent。⚠ 反锚定:表态必须引用**本轮**证据(截图文件名/字节数/stateDumps/manifest 字段),禁止沿用上轮表述;本轮证据与旧结论矛盾时以本轮为准。must 若仅因取证失败/证据缺失而无法判定(非确证违反),在该条 knownIssuesStatus(或新 issue)上标 unverifiable:true:
${issuesJson}

【绝对标准】must(违反 rubric/GOAL/bug/console error,挡 pass)|nice(不挡)。
**收敛判定:无 open must AND 全 GOAL 子项被本轮 verified 覆盖(coveredSubgoals 集合 ⊇ goalSubgoals.id 集合)→ pass。**
不因"更好做法"fail。out-of-scope 不当 must。绝不提替代方案。完整性铁律。issues 只放缺陷;"已修复/验证通过/全绿"等正面结论一律放 verified 数组(title+evidence+coveredSubgoals),任何 severity 都不得进 issues。mustFixOpen=本 lens 当前 open must 数。按 schema 输出。`;
}

// capture 脚本分支 prompt(独立 chromium，node 直接控制写入路径)；isParallel=多实例并行逃生口 vs 单 browser 串行。
function scriptCapturePrompt(rtag,stateLines,isParallel){
  return `【${rtag} · capture(脚本${isParallel?"·并行逃生口":"·串行"},系统 chrome)】在 ${UI_DIR} 写临时 _shot.mjs(跑完删),`+
    `${CHROME_LAUNCH}=系统 Google Chrome(非内置 chromium;`+
    (isParallel
      ? `各 state 用**独立 browser 实例** Promise.all 并行截——独立实例天生无串台,海量慢分叉逃生口)。`
      : `单 browser 串行按 recipe 逐态截)。`)+
    `注册 console(error)/pageerror/requestfailed。每态 locator auto-wait,失败记 error 不中断,存 ${SHOTS_DIR}/${rtag}_<state>.png。${CAPTURE_ERR_RULE}\n状态清单:\n${stateLines}\n跑 cd ${UI_DIR} && node _shot.mjs "${URL}" "${SHOTS_DIR}" "${rtag}"。${MANIFEST_SHAPE}`;
}

const REVIEWER_SCHEMA={ type:"object", required:["lens","verdict","mustFixOpen","issues"],
  properties:{ lens:{type:"string"}, verdict:{enum:["pass","fail"]}, mustFixOpen:{type:"integer"},
    // 注意力归位仪式,不进收敛判据(M4.5,2026-06-19 GOAL 持久化设计 v2.E)
    goalEcho:{type:"string"},
    coveredSubgoalIds:{type:"array", items:{type:"string"}},
    issues:{type:"array", items:{type:"object", required:["title","severity"],
      properties:{ matchesIssueId:{type:["string","null"]}, matchesSubgoal:{type:["string","null"]}, title:{type:"string"}, severity:{enum:["must","nice"]}, unverifiable:{type:"boolean"}, requiredStates:{type:"array", items:{type:"string"}}, detail:{type:"string"}, evidence:{type:"string"},
        // ★ 2026-06-21 P0 §3.2 — 决策层根因 + 策略级 plan(code lens 必填、其他 lens 可空)
        rootCauseHypothesis:{type:["string","null"]},
        affectedFiles:{type:"array", items:{type:"string"}},
        suggestedFix:{type:["string","null"]},
        nextStepPlan:{type:["string","null"]} }}},
    // verified 数组的 title + evidence + coveredSubgoals 都必填(M4.6)
    verified:{type:"array", items:{type:"object", required:["title","evidence","coveredSubgoals"],
      properties:{ title:{type:"string"}, evidence:{type:"string"}, coveredSubgoals:{type:"array", items:{type:"string"}} }}},
    knownIssuesStatus:{type:"array", items:{type:"object", required:["id","stillPresent"], properties:{ id:{type:"string"}, stillPresent:{type:"boolean"}, unverifiable:{type:"boolean"}, note:{type:"string"} }}} } };

// ── P1 meta-agent schema(物理禁双源真理:无 issues / verified / rootCauseHypothesis 字段)──
// final_report §4.2 / redesigner-proposal §6.3.1:
//   forbiddenApproaches = 跨轮"试过且失败"清单,下轮 implementer prompt 优先级 3
//   prioritizedMustIds  = 仅排序,不新增不删除 must
//   escapeRequest       = 元判断退出通道(4 类),非 null 触发 paused.md
const META_AGENT_SCHEMA = { type:"object", required:["forbiddenApproaches"],
  properties:{
    forbiddenApproaches:{ type:"array",
      items:{ type:"object", required:["issueId","triedMethod","why_failed_evidence"],
        properties:{ issueId:{type:"string"}, triedMethod:{type:"string"}, why_failed_evidence:{type:"string"} }}},
    prioritizedMustIds:{ type:"array", items:{type:"string"} },
    // ★ P1-1(B 路径 1):p1_skip_reason 让 LLM 显式标"本轮无 forbidden 信号"而非伪造占位;
    //   非 null 时下游 implementer prompt 跳过 forbiddenApproaches 段
    p1_skip_reason:{ type:["string","null"],
      enum:["no-stall","reviewer-already-clear","forbidden-not-applicable",null] },
    escapeRequest:{ type:["object","null"],
      // ★ P1-6:enum 加第 5 类 capture_layer_bug(STATES 对但 capture 层 playwright/MCP 路径问题,
      //   人介入指引 = 调浏览器 debug,与 missing_state=补 STATES 截然不同)
      properties:{ type:{enum:["missing_state","capture_layer_bug","rubric_too_strict","goal_unrealistic","reviewer_disagreement"]}, detail:{type:"string"} }}
  }};

// ════ setup(fail-fast 用 throw,顶层 return 在 ESM 非法)════
phase("setup");
// ★ P3-1:setup 顶部清理旧 runtag shots/ + .playwright-mcp/(SKILL.md §运维确认 已写,代码缺失,2026-06-22 audit 补)
// 清理只按显式路径枚举,绝不 git clean / 泛扫 untracked(已有红线,见 SKILL.md L218);
// 豁免:.web-loop-refresh.md、各 run 文字记录(SUMMARY.md/issues.json/reviews/)、goal.md/refs/、当前 run 目录
await agent(
  `【setup · cleanup】清理旧 run 残留(只删 shots + playwright-mcp,保 文字记录 + goal/refs + 当前 run):\n` +
  `1) bash 列出 \`.claude/web-loop/\` 下所有目录(\`ls -d .claude/web-loop/*/\` 2>/dev/null)。\n` +
  `2) 对每个目录,**排除当前 runtag=${RUNTAG}**(不动当前 run):\n` +
  `   - 若目录内含 shots/ 子目录,bash 删除:\`rm -rf .claude/web-loop/<其他 runtag>/shots\`\n` +
  `   - 但**不删** \`SUMMARY.md\` / \`issues.json\` / \`verified.json\` / \`reviews/\` / \`goal.md\` / \`refs/\`(文字记录 + GOAL 三件套)\n` +
  `3) bash 整删 \`.playwright-mcp/\`:\`rm -rf .playwright-mcp\`(若存在)\n` +
  `4) 返回 cleaned_runtags 数组(被清理 shots 的旧 runtag 列表),deleted_mcp 布尔。\n` +
  `⚠ 绝不 \`git clean\`、绝不删任何 \`.web-loop-refresh.md\`、绝不删 path2 主线代码 / docs / scripts / configs 等仓库其他文件。`,
  { label:"cleanup-old-runs", phase:"setup", model:"sonnet",
    schema:{ type:"object", required:["cleaned_runtags","deleted_mcp"],
      properties:{ cleaned_runtags:{type:"array", items:{type:"string"}}, deleted_mcp:{type:"boolean"} } } });

const pwOk = await agent(
  `【playwright 自检 / fail-fast】在 ${UI_DIR} 内写临时 _pwcheck.mjs(跑完删),`+
  `${CHROME_LAUNCH}=系统 Google Chrome(省下载、与 capture 默认 MCP 同一浏览器):`+
  `(a) goto 'about:blank'→screenshot /tmp/_pw.png→确认非空(测系统 chrome 可启动);`+
  `(b) goto '${URL}'→记 resp.status()(测 workflow agent 连宿主 localhost)→close。cd ${UI_DIR} && node _pwcheck.mjs。`+
  (CAPTURE_BACKEND==="mcp"?`(c) 另:ToolSearch 试加载 mcp__plugin_playwright_playwright__browser_navigate,记 mcpLoadable(加载到=true;capture 会据此决定 MCP 还是退脚本,此处不阻塞)。`:``)+
  `返回 ok(a+b 成功且 URL status==200)+错误文本+mcpLoadable。`,
  { label:"pw-selfcheck", phase:"setup", model:"sonnet", schema:{ type:"object", required:["ok"], properties:{ ok:{type:"boolean"}, error:{type:"string"}, mcpLoadable:{type:"boolean"} } } });
if(!pwOk || !pwOk.ok){ log(`BLOCKED: playwright 自检失败(${pwOk?.error||'?'})`); throw new Error(`BLOCKED: 沙箱跑不了 playwright 或连不上 ${URL}`); }

const pre = await agent(
  `【前置巡检 / fail-fast】1) Read ${RUBRIC_PATH} 确认可读。`+(HEALTH_URL?` 2) curl -sf ${HEALTH_URL} 得200。`:``)+
  ` 3) smoke 基线:跑 ${SMOKE_CMD} 须本就全绿(否则无法区分回归来源)。 4) mkdir -p ${WORKDIR} ${SHOTS_DIR}。写 ${WORKDIR}/preflight.md。`,
  { label:"preflight", phase:"setup", model:"sonnet", schema:{ type:"object", required:["rubricFound","smokeBaselineGreen"], properties:{ rubricFound:{type:"boolean"}, backendUp:{type:"boolean"}, smokeBaselineGreen:{type:"boolean"}, note:{type:"string"} } } });
if(!pre || !pre.rubricFound){ throw new Error("BLOCKED: rubric 不可读"); }
if(!pre.smokeBaselineGreen){ throw new Error("BLOCKED: smoke 基线非全绿,先修基线"); }

// ── setup · write-goal(★ P1-3:删 goal.json,GOAL 三件套→1.5 件套;goal.json 是 cargo doc)──
// reviewer/implementer 每轮 Read 完整版,prompt 段只放摘要(M1.4 / M4.1)。
const subgoalsBlock = summarizeSubgoals(GOAL_SUBGOALS);
const refsBlock = summarizeRefImages(REF_IMAGES);
// ★ P1-3:删 goal.json(GOAL 三件套 → 1.5 件套;goal.json 是 cargo doc,reviewer/impl 都不读)
await agent(
  `【setup · write-goal】把本次 GOAL 持久化到 ${WORKDIR}/goal.md(人可读;reviewer/implementer 每轮 Read 完整版,prompt 段只放摘要):\n\n` +
  safeBlock(
    `# 本次 GOAL\n\n${safeInsert(GOAL)}\n\n` +
    `## 子项清单(${GOAL_SUBGOALS.length} 条;reviewer 每轮逐条复核)\n\n${subgoalsBlock}\n\n` +
    `## 参考图(${REF_IMAGES.length} 张;主会话「智能入口层 §2c」持久化,详 ${WORKDIR}/refs/manifest.json)\n\n${refsBlock}\n\n` +
    `> 完整版以本文件为准;reviewer/implementer prompt 内嵌的是摘要,如有不一致以本文件为准。`,
    '```markdown'
  ) + '\n\n' +
  `⚠ 写完用 \`test -f ${WORKDIR}/goal.md\` 校验存在。\n` +
  `⚠ 此 agent 不重写 refs/(refs 由主会话「智能入口层 §2c」预先持久化);仅校验 ${WORKDIR}/refs/manifest.json 路径有效(若 refImages 非空)。`,
  { label:"write-goal", phase:"setup", model:"sonnet", schema:{ type:"object", required:["wrote"], properties:{ wrote:{type:"boolean"}, note:{type:"string"} } } }
);

// ════ iterate ════
phase("iterate");
let round=0, mustStaleStreak=0, converged=false, stalled=false, pausedReason=null;
let coveredSubgoalsUnchangedRounds=0, gitDiffSmallRounds=0;
let lastCoveredSubgoalsKey='';
while(round < MAX_ROUNDS && !converged && !stalled){
  round += 1;
  const rtag=`r${String(round).padStart(2,"0")}`;
  const openIssues=issues.filter(i=>i.status==="open"||i.status==="regressed");
  // ★ P0-2:reviewer 只看 open/regressed(principles.md §9 红线:fixed/closed 走 verified 通道);
  // 同时节省 -15-30k input/run(C estimator)
  const activeIssues = issues.filter(i => i.status === "open" || i.status === "regressed");
  const issuesJson = JSON.stringify(activeIssues, null, 2);

  // ── implementer(M1.4 顺序固化 + M2.5 role-conditional refs,2026-06-19 GOAL 持久化设计)──
  const implLabel = `impl-${rtag}`;
  const hasGoalRef = REF_IMAGES.some(r => r.role === 'goal');
  const subgoalsSummary = summarizeSubgoals(GOAL_SUBGOALS);
  const refsSummary = summarizeRefImages(REF_IMAGES);
  const verifiedSummary = verifiedLog.length
    ? verifiedLog.map(v => `- r${v.round}/${v.lens}: ${safeInsert(v.title)}${v.coveredSubgoals ? ' [' + v.coveredSubgoals.join(',') + ']' : ''}`).join('\n')
    : '(尚无 verified — 第一轮)';
  const refsLineForImpl = hasGoalRef
    ? `【参考图(refs/,⚠ 第一轮必读 role=goal 的图)】\n${refsSummary}`
    : (REF_IMAGES.length
        ? `【参考图(refs/,可选 — 本轮 refs 均为 baseline/anti-example,勿模仿,仅作"远离"参考)】\n${refsSummary}`
        : `【参考图】(无 ref — 本次 GOAL 纯文字驱动)`);

  // ── 5 级指令优先级(P0 §3.5a-i / §3.5a-ii,2026-06-21 final_report)──
  // 1. human-hint-r{N}.md(用户人工指令,若存在)
  // 2. 本轮 must.nextStepPlan + rootCauseHypothesis + affectedFiles(权威·必从)
  // 3. (P1)decision_log.json 的 forbiddenApproaches(Task 11 注入,本 task 占位段)
  // 4. 历史 reviews/round_<N-1>.md / round_<N-2>.md(参考补充)
  // 5. 历史 rounds/<N-1>/impl.md 反根因段(implementer 自己上轮的判断)
  const mustWithDecision = round === 1
    ? null
    : openIssues.filter(i=>i.severity==="must");
  const mustBlock = mustWithDecision
    ? safeBlock(JSON.stringify(mustWithDecision, null, 2), '```json')
    : '(第一轮无残留 must)';
  const humanHintRead = `【权威 · 必须遵循(用户人工指令)】先 bash 检测 \`test -f ${WORKDIR}/human-hint-r${round}.md\` —— 若存在则 \`Read ${WORKDIR}/human-hint-r${round}.md\`(权威最高于一切),消化后 \`mv ${WORKDIR}/human-hint-r${round}.md ${WORKDIR}/human-hint-r${round}.consumed.md\` 防止下轮重复消费;不存在则跳过。`;
  // ★ P1-2:合并 read-decision-log + p1-diffstat,round=1 short-circuit(decision_log 空、diff 大)
  let dlog = { exists:false, forbiddenApproaches:[], entries:[], totalLines:0, p1_skip_reason:null };
  let gitDiffTotal = 0;
  if (round >= 2) {
    const merged = await agent(
      `【${rtag} · read-state】合并两件事:\n` +
      `(a) bash 检测 \`${WORKDIR}/decision_log.json\` 是否存在;若存在 Read 整文件,返回 entries 数组 + 所有 entry 的 forbiddenApproaches union + 最后一条 entry 的 p1_skip_reason 字段(若存在且非 null 则原样返回,否则 null);若文件不存在则 exists=false / forbiddenApproaches=[] / entries=[] / p1_skip_reason=null。\n` +
      `(b) bash 跑 \`git diff --stat 2>/dev/null | tail -1\`,从末行 "X insertions(+), Y deletions(-)" 求 X+Y 得 totalLines;无 commit 或失败返回 0。\n` +
      `返回 { exists, forbiddenApproaches, entries, totalLines, p1_skip_reason }。`,
      { label:`read-state-${rtag}`, phase:"iterate", model:"sonnet",
        schema:{ type:"object", required:["exists","forbiddenApproaches","totalLines"],
          properties:{
            exists:{ type:"boolean" },
            forbiddenApproaches:{ type:"array",
              items:{ type:"object",
                properties:{ issueId:{type:"string"}, triedMethod:{type:"string"}, why_failed_evidence:{type:"string"} }}},
            entries:{ type:"array" },
            totalLines:{ type:"integer" },
            p1_skip_reason:{ type:["string","null"] }}}}
    );
    dlog = merged || dlog;
    gitDiffTotal = merged?.totalLines || 0;
  }
  // round=1 时 dlog/gitDiffTotal 均为 default 空值,无需 agent 调用
  const forbiddenList = (dlog?.p1_skip_reason) ? [] : (dlog?.forbiddenApproaches || []);
  const skipNote = dlog?.p1_skip_reason
    ? `\n⚠ 最近 P1 meta-agent 标 p1_skip_reason="${dlog.p1_skip_reason}",本轮无 forbidden 累积。\n`
    : '';
  const decisionLog = (round >= 2 && forbiddenList.length)
    ? `【权威 · 必须规避(跨轮 forbidden,P1 meta-agent 累计产物,${forbiddenList.length} 条)】\n` +
      safeBlock(JSON.stringify(forbiddenList, null, 2), '```json') +
      `\n⚠ 这些 (issueId, triedMethod) 组合在本 run 跨轮试过且失败(why_failed_evidence 含证据),**不得重试**;若你必须重试,在 impl.md 首段单独标 "重试理由:..." 说明为什么这次会成功。`
    : skipNote.trim();
  const historyReviews = round >= 2 ? `【参考补充(历史 reviews · 仅最近 1 轮)】\n- Read ${WORKDIR}/reviews/round_${String(round - 1).padStart(2,'0')}.md(必读)\n用于验证本轮 nextStepPlan 与上轮的差异、确认 P1 forbiddenApproaches 提炼无漏;若发现 P1 漏掉重要信号,在 impl.md 标 "P1 漏检:..."。\n⚠ 仅读上 1 轮 reviews —— 远历史走权威·必须规避(跨轮 forbidden)累积清单 + 上轮 impl.md 反根因段(参考补充)。传递性论据:r${round - 1} implementer 已就 plan_${round - 1} vs plan_${round - 2 >= 1 ? round - 2 : '?'} 重复性做过判断并标进 r${round - 1}/impl.md reviewer_stuck,无需 r${round} 重做。` : '';
  const histImpl = round >= 2 ? `【参考补充(历史 impl.md 反根因)】Read ${WORKDIR}/rounds/${round - 1}/impl.md 首段——上轮自己写的 reviewer_stuck 判断 / 反根因记录。若有 "反根因:实际机制是 Z" 段,本轮优先验证 Z 假设。` : '';

  await agent(
    `【${rtag} · implementer】改进运行中的 web(改 bug / 改进现有代码,非从零)。\n\n` +
    `${humanHintRead}\n\n` +
    `【本次 GOAL(原文,逐字不变;完整版以 ${WORKDIR}/goal.md 为准)】\n${safeInsert(GOAL)}\n\n` +
    `【GOAL 子项清单(${GOAL_SUBGOALS.length} 条;完整版以 ${WORKDIR}/goal.md 为准)】\n${subgoalsSummary}\n\n` +
    `${refsLineForImpl}\n\n` +
    `【已 verified 子项(勿破坏)】\n${verifiedSummary}\n\n` +
    `【权威 · 必须遵循(本轮 must / 决策字段;含 nextStepPlan / rootCauseHypothesis / affectedFiles / suggestedFix 四决策字段,code lens 给的策略,2026-06-21 P0 §3.2/§3.5a-i)】\n` +
    (round === 1
      ? `(第一轮无残留 must)\n` + (hasGoalRef ? '⚠ 第一轮必读 role=goal 的 ref 建立视觉心智图。\n' : '')
      : `${mustBlock}\n\n⚠ 改前必做:\n  1. 对每条 must,先 Read affectedFiles 列出的具体行号(确认 reviewer 描述的现状与本轮真实代码一致;reviewer 看的是上轮 diff,本轮代码可能已变)。\n  2. 一句话回讲"我理解根因是 X,我要按 nextStepPlan 第 N 步改的是 Y"(写进 impl.md 首段)。\n  3. 若 nextStepPlan 给了具体 suggestedFix,可推翻——但需在 impl.md 标 "推翻 suggestedFix 因为 W"。\n  4. **勿引入新问题,勿偏离 GOAL 全局**(每改一条 must,反问自己是否拉远了某 verified 子项)。\n`
    ) + `\n` +
    `${decisionLog}\n\n${historyReviews}\n\n${histImpl}\n\n` +
    `【实施者输出 schema(P0-1 part ii 已强制 reviewer_stuck 等字段)】\n${round >= 2 ? `本轮 implementer 输出 schema 必填 \`{reviewer_stuck:boolean, planRepetition:string, mdSnippet:string, kind:enum}\`,workflow 程序化读后注入下轮 reviewer prompt(替代旧 bash cat 路径)。\n· reviewer_stuck=true → "r${round} plan 与 r${round-1} plan 本质相同、试过没解决"\n· reviewer_stuck=false → "r${round} plan 不重复,按真实证据推进"\n· planRepetition → 若 stuck=true 给一句话简述(上轮 plan 试过 X 失败于 Y、本轮我改在 Z)\n· mdSnippet → 写入 impl.md 首段的最终文本(含 reviewer_stuck 行 + 反根因若有)\n\nimpl.md 首段(信息冗余 + 人可读取证):\n\`\`\`\n- reviewer_stuck: <同 schema>\n- plan 重复分析: <同 planRepetition>\n- 本轮我会按 plan 第 N 步改 <文件:行号>\n- 反根因(若有): <"实际机制是 Z">\n\`\`\`` : '(第一轮无上轮 plan,reviewer_stuck schema 字段填 false,kind 字段照填即可)'}\n\n` +
    `⚠ 改前 \`git diff\` 看现状,勿破坏已 fixed 功能。完成写 ${WORKDIR}/rounds/${round}/impl.md,**首段固定结构如上 + 第二段往后:首行 kind=frontend|backend|data,然后正文叙述本轮改了什么**。`,
    { label:implLabel, phase:"iterate", model:"opus",
      // ★ P0-1 part (ii):implementer 输出 schema 强制 reviewer_stuck 三字段 + kind
      // 跨轮信号源(B#8 主推):取代当前靠 prompt 让 LLM 在 impl.md 首段标 reviewer_stuck
      // 的脆弱方案。schema 化后 workflow 可程序化 read,reviewer 红线不破(数据源是
      // implementer 自报,非 reviewer 读历史)。
      schema: { type:"object", required:["reviewer_stuck","kind"],
        properties:{
          reviewer_stuck: { type:"boolean" },
          planRepetition: { type:"string" },
          mdSnippet: { type:"string" },
          kind: { enum:["frontend","backend","data","none"] }
        } } }
  ); // forbiddenApproaches union 已通过 decisionLog 段内插(见上方 read-decision-log agent)

  const smoke=await agent(`【${rtag} · smoke】跑 ${SMOKE_CMD}。全绿 pass:true;红 pass:false+摘要。`,
    { label:`smoke-${rtag}`, phase:"iterate", model:"sonnet", schema:{ type:"object", required:["pass"], properties:{ pass:{type:"boolean"}, summary:{type:"string"} } } });
  if(!smoke || !smoke.pass){
    await agent(`本轮致回归(${smoke?.summary||'?'})。回滚:**只跑 \`git checkout -- .\`**(回滚本轮对已跟踪文件的修改)。`+
      `⚠ **绝不 \`git clean\` 全仓库**——它会删 WORKDIR 外的未跟踪文件(plan 文档/配置/新建示例等),曾是真实事故。`+
      `若本轮 implementer 新建了未跟踪源文件(git status 看),只精确 rm 明确属于本轮、在源码区内的那几个;拿不准则保留并在 note 记下交下轮处理。`, { label:`rollback-${rtag}`, phase:"iterate", model:"sonnet" });
    issues.push({ id:`regress-${rtag}`, lens:"code", severity:"must", title:`改动致回归已回滚:${smoke?.summary||''}`, status:"open", bornRound:round, lastSeenRound:round });
    history.push({ round, rolledBack:true }); continue;
  }

  const refresh=await agent(`【${rtag} · refresh】读 ${WORKDIR}/rounds/${round}/impl.md 首行 kind,按档刷新:\n`+
    `- frontend:HMR 自动 → page.reload()+networkidle(纯前端,绝不碰数据层)。复用现有数据态(免重新触发数据生成)。\n`+
    `- backend:${RESTART_CMD?`\`${RESTART_CMD}\``:'〔restartCmd〕'}(⚠ kill 旧进程**按 PID/端口精确**如 lsof -ti:8000|xargs -r kill,**绝不用 pkill -f <进程名模式>**——会误杀正在执行该命令的本 shell 致 Exit144) → curl -sf ${HEALTH_URL||'〔healthUrl〕'} 轮询至200 → 前端 reload。复用现有数据态。\n`+
    `- data:【仅此档走 fallback】重启后端 + 触发数据刷新。`+
      (REFRESH_DATA_CMD?`refreshDataCmd=\`${REFRESH_DATA_CMD}\`:`:`refreshDataCmd 未提供:`)+
      `若以 .md 结尾 → **read 该说明文件**(项目内多步刷新约定,如重扫+poll)按步骤执行;否则非空 → 当 shell 命令直接跑(单步,如 DB seed/缓存清空);否则 → 报 must(data 改动但无刷新方式)。完成后前端 reload。\n`+
    `- none:无需刷新 → 直接 reload。\n`+
    `就绪写 refresh.md,返回 ready+kind。`,
    { label:`refresh-${rtag}`, phase:"iterate", model:"sonnet", schema:{ type:"object", required:["ready"], properties:{ ready:{type:"boolean"}, kind:{enum:["frontend","backend","data","none"]}, note:{type:"string"} } } });
  if(!refresh || !refresh.ready){
    issues.push({ id:`infra-${rtag}`, lens:"code", severity:"must", title:"刷新/重启/重扫失败,不可评审", status:"open", bornRound:round, lastSeenRound:round });
    history.push({ round, skippedReview:true }); continue;
  }

  // probe = stateProbe 第二证据通道:截图之外按 state 采集 store/DOM 状态(canvas 交互无视觉差异时的判定依据)
  const stateLines=STATES.map(s=>`- ${s.state}: ${s.recipe}`+(s.probe?`\n  〔probe〕完成 recipe 后执行 page.evaluate(() => (${s.probe})),返回值原样记入 manifest stateDumps["${s.state}"];evaluate 抛错则把错误文本记入该 state 的 error。`:``)).join("\n");
  const captureMemo=lastShotErrors.length?`【上轮取证失败记录——本轮必须换方法解决(换定位方式/换证据通道),不得原样重试】\n${lastShotErrors.join("\n")}\n`:``;
  const capturePrompt = CAPTURE_BACKEND==="mcp"
    ? captureMemo+`【${rtag} · capture(MCP 单点串行,系统 chrome)】用 playwright MCP。先 ToolSearch 加载 `+
      `mcp__plugin_playwright_playwright__browser_navigate / browser_take_screenshot / browser_click,无法加载则 mcpUnavailable=true 直接返回(由调用方退脚本)。`+
      `前提:后端在线(curl -s -o/dev/null -w '%{http_code}' ${HEALTH_URL||URL}=200)。对下列每个 state **串行**执行其 recipe(navigate/click/dblclick + 对应 wait),每态 browser_take_screenshot 截图。`+
      `⚠ MCP 相对 filename 实际落在 MCP 默认输出位置(.playwright-mcp 或项目根),**不一定是 ${SHOTS_DIR}**:截完后用 bash 把刚截出的文件 **mv 到 ${SHOTS_DIR}/${rtag}_<state>.png**(别假设默认落点,可先从工具返回值或 ls 定位实际文件再 mv),manifest 的 path **报 mv 后的最终路径**;对每个 path 用 test -f 确认存在且非空,否则该态记 error。底线:manifest 每个 path 都指向真实可 Read 的文件。`+
      `navigate 自动捕获 console,汇总。某态失败记 error 不中断。${CAPTURE_ERR_RULE}\n状态清单:\n${stateLines}\n${MANIFEST_SHAPE}`
    : captureMemo+scriptCapturePrompt(rtag, stateLines, CAPTURE_BACKEND==="script-parallel");

  let shots=await agent(capturePrompt, { label:`capture-${rtag}`, phase:"iterate", model:"sonnet", schema:{ type:"object", required:["shots"], properties:{
      shots:{type:"array", items:{type:"object", properties:{ state:{type:"string"}, path:{type:["string","null"]}, bytes:{type:"integer"}, error:{type:"string"} }}},
      consoleErrors:{type:"array", items:{type:"string"}}, pageErrors:{type:"array", items:{type:"string"}}, failedRequests:{type:"array"},
      stateDumps:{type:"object"}, mcpUnavailable:{type:"boolean"} } } });
  // MCP 不可用 或 运行时无图(navigate 抛错/shots 全无 path)→ 自动退脚本(channel:chrome)再截一次
  if(CAPTURE_BACKEND==="mcp" && (shots?.mcpUnavailable || !(shots?.shots||[]).some(s=>s.path))){
    log(`${rtag}: MCP capture 无可用图,退脚本(channel:chrome)`);
    shots=await agent(captureMemo+scriptCapturePrompt(rtag, stateLines, false),
      { label:`capture-fallback-${rtag}`, phase:"iterate", model:"sonnet", schema:{ type:"object", required:["shots"], properties:{
        shots:{type:"array", items:{type:"object", properties:{ state:{type:"string"}, path:{type:["string","null"]}, bytes:{type:"integer"}, error:{type:"string"} }}},
        consoleErrors:{type:"array", items:{type:"string"}}, pageErrors:{type:"array", items:{type:"string"}}, failedRequests:{type:"array"}, stateDumps:{type:"object"} } } });
  }
  lastShotErrors=(shots?.shots||[]).filter(s=>s.error).map(s=>`${s.state}: ${s.error}`);
  const okShots=(shots?.shots||[]).filter(s=>s.path);
  if(!okShots.length){
    issues.push({ id:`shot-${rtag}`, lens:"code", severity:"must", title:"截图全失败,无图可评", status:"open", bornRound:round, lastSeenRound:round });
    history.push({ round, skippedReview:true }); continue;
  }
  const shotList=okShots.map(s=>`${s.path} (${s.state})`).join("\n");
  const errLines=[...(shots.consoleErrors||[]), ...(shots.pageErrors||[]), ...((shots.failedRequests||[]).map(r=>`REQFAIL ${r.url||r}`))];
  const consoleNote=errLines.length?`【控制台/网络错误(func 必判 must)】\n${errLines.join("\n")}`:`【控制台/网络】干净。`;
  const dumps=shots?.stateDumps||{};
  const probeNote=Object.keys(dumps).length?`【状态探针 stateDumps(与截图同级证据,直接据此判定交互/状态是否生效)】\n${JSON.stringify(dumps)}`:``;

  const goalSubgoalsSummaryForReviewer = summarizeSubgoals(GOAL_SUBGOALS);
  const refImagesSummaryForReviewer = summarizeRefImages(REF_IMAGES);
  // ★ P0-1 part (iii):程序化 read 上轮 implementer 输出 schema(已含 reviewer_stuck),
  // 拼成纯字符串供 reviewerPrompt 内插。一轮一次,reviewer × 3 lens 共用。
  let stuckSignal = '';
  if (round >= 2) {
    const sigRead = await agent(
      `【${rtag} · read-impl-stuck】bash 跑 \`test -f ${WORKDIR}/rounds/${round - 1}/impl.md && head -40 ${WORKDIR}/rounds/${round - 1}/impl.md\` 返回首段;然后用 regex 抽出 "reviewer_stuck: <true|false>" 与 "plan 重复分析: ..." 两行内容,组装成两行字符串。若 impl.md 不存在或无 reviewer_stuck 行,返回 ok=false。`,
      { label:`read-impl-stuck-${rtag}`, phase:"iterate", model:"sonnet",
        schema:{ type:"object", required:["ok"],
          properties:{ ok:{type:"boolean"}, stuck:{type:"boolean"}, summary:{type:"string"} } } });
    if (sigRead?.ok) {
      stuckSignal = `- reviewer_stuck: ${sigRead.stuck === true ? 'true' : 'false'}\n- plan 重复分析: ${safeInsert(sigRead.summary || '(空)')}`;
    }
  }
  const verdicts=await parallel(REVIEW_LENSES.map(lens=>()=>agent(
    reviewerPrompt(lens,{
      round, GOAL, RUBRIC_PATH, shotList, issuesJson, consoleNote, probeNote,
      verifiedJson: JSON.stringify(verifiedLog),
      goalSubgoalsSummary: goalSubgoalsSummaryForReviewer,
      refImagesSummary: refImagesSummaryForReviewer,
      WORKDIR, stuckSignal,
    }),
    { label:`review-${lens}-${rtag}`, phase:"iterate", model:"opus", schema:REVIEWER_SCHEMA })));

  const present=verdicts.filter(Boolean);
  const allPresent=present.length===REVIEW_LENSES.length;
  // verifiedLog 收集 + 按子项 id 聚合(M4.4)
  for(const v of present) for(const k of (v.verified||[])) verifiedLog.push({ round, lens:v.lens, title:k.title, evidence:k.evidence, coveredSubgoals:k.coveredSubgoals||[] });
  const statusBefore=new Map(issues.map(i=>[i.id,i.status]));
  mergeIssues(issues, present, round);
  // verdict 从台账推导:lens 名下有 open/regressed 的确证 must(非 unverifiable)→ 不得 pass(申报矛盾时强制 fail,保留 declaredVerdict 供审计)
  for(const v of present){
    const blocking=issues.some(i=>i.lens===v.lens&&(i.status==="open"||i.status==="regressed")&&i.severity==="must"&&!i.unverifiable);
    if(blocking&&v.verdict!=="fail"){ v.declaredVerdict=v.verdict; v.verdict="fail"; }
  }
  const openMust=issues.filter(i=>(i.status==="open"||i.status==="regressed")&&i.severity==="must");
  const allPass=allPresent&&present.every(v=>v.verdict==="pass");
  const newMust=openMust.filter(i=>i.bornRound===round).length;
  // 停滞 = must 台账完全冻结:无新增 且 无任何 must 状态转移(修复/回归都算进展,重置 streak)
  const mustTransitions=issues.filter(i=>i.severity==="must"&&i.status!==(statusBefore.get(i.id)??i.status)).length;
  mustStaleStreak=(newMust===0&&mustTransitions===0)?mustStaleStreak+1:0;

  // 收敛判据加严(M1.3,2026-06-19 GOAL 持久化设计):
  // (a) allPass + openMust==0(旧) AND (b) 全 GOAL 子项在本轮被某 lens 用合法 evidence 覆盖。
  // 跨轮聚合:subgoalCoverage[G_id] = [{round,lens,evidence}, ...](M4.4)
  // ⚠ 此块必须在 history.push 之前(history.push 引用 coveredThisRound / allSubgoalsCovered;否则 TDZ)
  subgoalCoverage = {};
  for(const v of verifiedLog){
    for(const sg of (v.coveredSubgoals||[])){
      (subgoalCoverage[sg] ??= []).push({round:v.round, lens:v.lens, evidence:v.evidence});
    }
  }
  // 本轮 covered:只看 round===当前 round 的 verified 收集到的 coveredSubgoals(防"曾经覆盖过就一直算覆盖")
  const coveredThisRound = new Set();
  for(const v of present) for(const k of (v.verified||[])) for(const sg of (k.coveredSubgoals||[])) coveredThisRound.add(sg);
  const subgoalIds = (GOAL_SUBGOALS||[]).map(g=>g.id);
  const allSubgoalsCovered = subgoalIds.length === 0
    ? true   // 无子项 = 智能入口层未拆,不阻塞收敛(降级到旧判据;SUMMARY 会标注此 risk)
    : subgoalIds.every(id => coveredThisRound.has(id));  // coveredThisRound 聚合自本轮 verified.coveredSubgoals

  history.push({ round, verdicts:present.map(v=>({lens:v.lens,verdict:v.verdict,...(v.declaredVerdict?{declaredVerdict:v.declaredVerdict}:{}),n:(v.issues||[]).length})), openMust:openMust.length, newMust, mustStaleStreak, coveredThisRound:[...coveredThisRound], allSubgoalsCovered });
  // ── P1 触发计数器(coveredSubgoals 集合连续 N 轮未增 / git diff 连续 N 轮 < 5 行)──
  const coveredKey = [...coveredThisRound].sort().join('|');
  if (round >= 2 && coveredKey === lastCoveredSubgoalsKey) coveredSubgoalsUnchangedRounds++;
  else coveredSubgoalsUnchangedRounds = 0;
  lastCoveredSubgoalsKey = coveredKey;
  // git diff 行数:轻量调一次 bash 探(脚本内 bash 是 agent 调用,只能延迟到下方)
  await agent(`写 ${WORKDIR}/issues.json(覆写)=${JSON.stringify(issues)};写 ${WORKDIR}/verified.json(覆写)=${JSON.stringify(verifiedLog)};追加 ${WORKDIR}/reviews/round_${round}.md。`, { label:`persist-${rtag}`, phase:"iterate", model:"sonnet" });

  converged=(allPass && openMust.length===0 && allSubgoalsCovered);
  stalled=(!converged && allPresent && mustStaleStreak>=STALE_ROUNDS);

  // ────────── 3 条机检判据(P0 §3.4,2026-06-21 final_report skeptic §2)──────────
  // 触发任一 = workflow stall,写 paused.md + 退出循环(保留 issues/verified/refs)
  // 续修协议(§3.7):用户写 ${WORKDIR}/human-hint-r${round+1}.md + Workflow({resumeFromRunId})

  // 判据 1:同一 must 跨轮"修复 → 回归"震荡 ≥ 2 次
  // 含义:implementer 在两个修法之间反复横跳 = ② 多 must 互冲硬证据
  const oscillating = issues.some(i =>
    i.severity === 'must' && (i.regressionCount || 0) >= 2 &&
    (i.status === 'open' || i.status === 'regressed')
  );

  // 判据 2:同 lens 新 must 累计 ≥ 老 must fixed 累计 且最近 2 轮差值单调不降
  // 含义:每修一个旧 must 引入一个新 must(原地踏步;因 id 不同 mustStaleStreak 不计)
  const treadmill = REVIEW_LENSES.some(lens => {
    const recent2 = history.slice(-2);
    if (recent2.length < 2 || round < 3) return false;
    const newCumByRound = history.map((_, idx) =>
      history.slice(0, idx + 1).reduce((s, h) =>
        s + (Array.isArray(h.verdicts) && h.verdicts.find(v => v.lens === lens) ? (h.newMust || 0) : 0), 0));
    const fixedCum = issues.filter(i =>
      i.lens === lens && i.status === 'fixed').length;
    const lastNewCum = newCumByRound[newCumByRound.length - 1];
    const prevNewCum = newCumByRound[newCumByRound.length - 2];
    return lastNewCum >= fixedCum && lastNewCum > 0 && lastNewCum >= prevNewCum;
  });

  // 判据 3:同 GOAL 子项 unverifiable 跨 ≥ 2 轮 + requiredStates 集合有重叠
  // 含义:capture STATES 漏一必要状态,workflow 内无法补,必须人补 STATES
  const missingStates = (GOAL_SUBGOALS || []).some(g => {
    const recent = issues.filter(i =>
      i.matchesSubgoal === g.id && i.unverifiable &&
      Array.isArray(i.requiredStates) && i.requiredStates.length);
    if (recent.length < 2) return false;
    const allStates = recent.flatMap(i => i.requiredStates);
    return new Set(allStates).size < allStates.length;  // 至少一 state 在多 issue 重复
  });

  pausedReason = oscillating ? 'oscillating'
              : treadmill ? 'treadmill'
              : missingStates ? 'missingStates'
              : null;

  if (pausedReason && !converged) {
    // 写 paused.md(P0 §3.7 续修协议,sketch §2.5)
    const pausedBody = `# PAUSED · runtag=${RUNTAG} · round=${round}\n\n` +
      `触发判据:**${pausedReason}**\n\n` +
      `## 判据 1 · oscillating(${oscillating})\n含义:同 must 跨轮 fixed→regressed 震荡 ≥2 次(implementer 在两修法间反复横跳;多 must 互冲硬证据)。\n${oscillating ? `震荡 must id 清单:${JSON.stringify(issues.filter(i=>i.severity==='must'&&(i.regressionCount||0)>=2).map(i=>i.id))}` : '未触发。'}\n\n` +
      `## 判据 2 · treadmill(${treadmill})\n含义:同 lens 新 must 累计 ≥ 修复累计且最近 2 轮差值单调不降(每修一旧 must 引入一新 must;mustStaleStreak 因 id 不同不计 = STALE 盲区)。\n\n` +
      `## 判据 3 · missingStates(${missingStates})\n含义:GOAL 子项 unverifiable 跨 ≥2 轮 + requiredStates 重叠 = capture STATES 漏一必要状态(workflow 内无能力补,必须人补 STATES 后重启)。\n\n` +
      `## 当前 open must 完整台账\n\`\`\`json\n${JSON.stringify(issues.filter(i=>(i.status==='open'||i.status==='regressed')&&i.severity==='must'),null,2)}\n\`\`\`\n\n` +
      `## 续修指引(P0 §3.7,零 runtime 改动)\n\n` +
      `1. 检查截图 \`${SHOTS_DIR}/${RUNTAG}_*.png\` + 完整 issues.json + verified.json + reviews/round_${String(round).padStart(2,'0')}.md\n` +
      `2. 决策三选一:\n` +
      `   a) **rubric/STATES/refImages 错位** → 改 args 起新 run\n` +
      `   b) **implementer 走偏 / reviewer 根因猜错** → 写 \`${WORKDIR}/human-hint-r${round + 1}.md\`(自然语言一段描述真实根因 / 该改什么文件),然后主会话调 \`Workflow({resumeFromRunId: "${RUNTAG}"})\` 续跑同 run、保留已 verified\n` +
      `   c) **弃 workflow** → 转主会话 + 主会话直接调 sonnet implementer 手工修\n\n` +
      `⚠ 仅同 session 内 resume 可用(SKILL.md L138 已说);跨 session 切换需起新 run。\n`;
    await agent(
      `写两文件(P2-3 append-only):\n` +
      `1) **用 Write 工具**写 ${WORKDIR}/paused.latest.md(覆写,只含本次 stall 全文):\n${safeBlock(pausedBody, '~~~')}\n\n` +
      `2) 然后 bash 跑 \`cat ${WORKDIR}/paused.latest.md >> ${WORKDIR}/paused.history.md && printf '\\n---\\n' >> ${WORKDIR}/paused.history.md\` append 进历史(若 history 不存在自然创建)。`,
      { label:`paused-${rtag}`, phase:"iterate", model:"sonnet" }
    );
    log(`PAUSED at r${round}: ${pausedReason}`);
    stalled = true;  // 兼用现有 stalled 出口走 finalize
  }

  // ────────── P1 缩窄版 meta-agent(final_report §4.2,2026-06-21)──────────
  // 位置:reviewer 后 / 下轮 implementer 前 → 触发条件具备时,本轮 reviewer 已出 must,
  //       meta-agent 写 decision_log.json,下轮 implementer prompt 优先级 3 内插。
  // 触发:三通道 OR(oscillating/treadmill 已被 §3.4 paused.md 截获,P1 只在未 paused
  //       且 P1_TRIGGER_STREAK 命中时触发),P1_TRIGGER_STREAK 与 staleRounds 自适应耦合。
  // schema 物理禁双源真理:仅 forbiddenApproaches / prioritizedMustIds / escapeRequest。
  const P1_TRIGGER_STREAK = Math.max(1, STALE_ROUNDS - 1);
  // 原 p1-diffstat agent 已被 read-state 合并(P1-2),gitDiffTotal 已在 read-state 阶段取得
  const diffLines = gitDiffTotal;
  if (round >= 2 && diffLines < 5) gitDiffSmallRounds++;
  else gitDiffSmallRounds = 0;

  const p1Triggered = !converged && !pausedReason && round >= 2 && (
    mustStaleStreak >= P1_TRIGGER_STREAK ||
    coveredSubgoalsUnchangedRounds >= P1_TRIGGER_STREAK ||
    gitDiffSmallRounds >= P1_TRIGGER_STREAK
  );

  if (p1Triggered) {
    log(`P1 meta-agent triggered at r${round} (streak=${mustStaleStreak}/cov=${coveredSubgoalsUnchangedRounds}/diff=${gitDiffSmallRounds}, threshold=${P1_TRIGGER_STREAK})`);
    const recentReviewsList = [round, round - 1, round - 2].filter(r => r >= 1).map(r =>
      `- ${WORKDIR}/reviews/round_${String(r).padStart(2,'0')}.md`).join('\n');
    const recentImplList = [round, round - 1, round - 2].filter(r => r >= 1).map(r =>
      `- ${WORKDIR}/rounds/${r}/impl.md`).join('\n');

    const metaResult = await agent(
      `【${rtag} · meta-agent】P1 元层 agent(opus)。本轮触发判据 ` +
      `mustStaleStreak=${mustStaleStreak} / coveredSubgoalsUnchangedRounds=${coveredSubgoalsUnchangedRounds} / gitDiffSmallRounds=${gitDiffSmallRounds}(P1_TRIGGER_STREAK=${P1_TRIGGER_STREAK})。\n\n` +
      `【你的任务(redesigner-proposal §6.3 缩窄版)】\n` +
      `跨轮综合最近 ≤3 轮 reviews + impl.md + git log + decision_log.json,产出 3 字段(见 schema):\n` +
      `1. forbiddenApproaches:跨轮"试过且失败"清单(下轮 implementer 强制规避)\n` +
      `2. prioritizedMustIds:仅排序 issues.json 已有 must id 子集(不新增不删除)\n` +
      `2.5. p1_skip_reason(可空):若你判断本轮无真"试过且失败"案例(reviewer 已 clear / 无 stall / forbidden 不适用本轮),填非空字符串 "no-stall"|"reviewer-already-clear"|"forbidden-not-applicable" 之一,forbiddenApproaches 可为空数组;若有真案例则 p1_skip_reason 留 null。\n` +
      `3. escapeRequest(可空):元判断退出通道(4 类)\n\n` +
      `【⚠ 强约束 · 不破双源真理】reviewer 的 issues/verified 是台账真相,你**不质疑、不修改、不复判**;若产生对某 must 的不同看法,必须走 \`escapeRequest.type=reviewer_disagreement\` 通道(强制人工介入,不让 implementer 选边)。\n\n` +
      `【输入(Read 这些文件,不重传内容)】\n` +
      `- ${WORKDIR}/goal.md(GOAL 原文 + 子项)\n` +
      `- ${WORKDIR}/refs/manifest.json(若存在;视觉目标参考)\n` +
      `- 最近 ≤3 轮 reviews:\n${recentReviewsList}\n` +
      `- 最近 ≤3 轮 impl.md:\n${recentImplList}\n` +
      `- ${WORKDIR}/decision_log.json(若存在;上轮 P1 输出,跨轮防重复)\n\n` +
      `【其他证据 inline】\n` +
      `- 当前 issues 完整台账:${safeBlock(JSON.stringify(issues, null, 2), '\`\`\`json')}\n` +
      `- 当前 verifiedLog:${safeBlock(JSON.stringify(verifiedLog, null, 2), '\`\`\`json')}\n` +
      `- bash: cd ${UI_DIR} && git log --oneline -${Math.min(round, 5)}(若 implementer 都在源码区改动)\n\n` +
      `【escapeRequest 5 类语义】\n` +
      `- \`missing_state\` → capture STATES 漏一必要状态(workflow 内无能力补,人补 STATES 后起新 run)\n` +
      `- \`capture_layer_bug\` → STATES 配对、但 capture agent 连续 ≥2 轮 capture 同 id 失败(playwright/MCP/sandbox/network 路径问题;人介入 = 调浏览器 debug,不是补 STATES)\n` +
      `- \`rubric_too_strict\` → rubric 验收门设过高,合理实现都判 fail(改 rubric 起新 run)\n` +
      `- \`goal_unrealistic\` → GOAL 本身在当前架构下做不到(改 goal 起新 run 或转主会话设计)\n` +
      `- \`reviewer_disagreement\` → 你判断某 must 的根因/严重度与 reviewer 不一致(强制人工介入)\n\n` +
      `按 schema 输出。`,
      { label:`meta-agent-${rtag}`, phase:"iterate", model:"opus", schema:META_AGENT_SCHEMA });

    // 落 decision_log.json append-only
    if (metaResult) {
      const logEntry = {
        round,
        forbiddenApproaches: metaResult.forbiddenApproaches || [],
        prioritizedMustIds: metaResult.prioritizedMustIds || [],
        p1_skip_reason: metaResult.p1_skip_reason || null,
        escapeRequest: metaResult.escapeRequest || null
      };
      await agent(
        `【${rtag} · decision-log-append】把本轮 meta-agent 输出 append 到 ${WORKDIR}/decision_log.json(若文件不存在则初始化为 \`{"entries":[]}\`;append 后 entries 数组追加本轮 entry)。bash 推荐:\n` +
        `\`\`\`bash\n` +
        `python3 -c "import json,os,sys; p='${WORKDIR}/decision_log.json'; d=json.load(open(p)) if os.path.exists(p) else {'entries':[]}; d['entries'].append(json.loads(sys.argv[1])); json.dump(d, open(p,'w'), indent=2, ensure_ascii=False)" '${safeInsert(JSON.stringify(logEntry))}'\n` +
        `\`\`\`\n` +
        `若用户环境无 python3,fallback 写一个 node ESM 等价脚本到 \`/tmp/_dlog.mjs\` 跑完即删。`,
        { label:`decision-log-${rtag}`, phase:"iterate", model:"sonnet" }
      );

      // escapeRequest 非 null → 触发等同 paused.md 流程
      if (metaResult.escapeRequest && metaResult.escapeRequest.type) {
        pausedReason = 'escapeRequest';
        const escapeBody = `# PAUSED · runtag=${RUNTAG} · round=${round}\n\n` +
          `触发判据:**escapeRequest**(P1 meta-agent §4.2)\n\n` +
          `## escapeRequest.type = ${metaResult.escapeRequest.type}\n\n` +
          `${safeInsert(metaResult.escapeRequest.detail || '')}\n\n` +
          `## 续修指引\n\n` +
          `- \`missing_state\` → 补 STATES(args.states),起新 run\n` +
          `- \`rubric_too_strict\` → 改 rubric / goal,起新 run\n` +
          `- \`goal_unrealistic\` → 转主会话设计 / 重定义 GOAL,起新 run\n` +
          `- \`reviewer_disagreement\` → 主会话人工裁定 reviewer vs meta-agent 哪条对,写 \`${WORKDIR}/human-hint-r${round + 1}.md\` 后 \`Workflow({resumeFromRunId: "${RUNTAG}"})\`\n`;
        await agent(
          `写两文件(P2-3 append-only):\n` +
          `1) **用 Write 工具**写 ${WORKDIR}/paused.latest.md(覆写,只含本次 escape 全文):\n${safeBlock(escapeBody, '~~~')}\n\n` +
          `2) 然后 bash append 进 ${WORKDIR}/paused.history.md: \`cat ${WORKDIR}/paused.latest.md >> ${WORKDIR}/paused.history.md && printf '\\n---\\n' >> ${WORKDIR}/paused.history.md\`(同上路径,若 history 不存在自然创建)。`,
          { label:`paused-escape-${rtag}`, phase:"iterate", model:"sonnet" }
        );
        log(`PAUSED at r${round}: escapeRequest=${metaResult.escapeRequest.type}`);
        stalled = true;
      }
    }
  }
}

// ════ finalize ════
phase("finalize");
const exitReason=converged?"converged":(stalled?"stalled":"max-rounds-hit");
const leftoverMust=issues.filter(i=>(i.status==="open"||i.status==="regressed")&&i.severity==="must");
const leftoverUnverifiable=leftoverMust.filter(i=>i.unverifiable);
const leftoverConfirmed=leftoverMust.filter(i=>!i.unverifiable);
const finalizeGoalBlock = (GOAL_SUBGOALS||[]).length
  ? (GOAL_SUBGOALS.map(g => {
      const covered = subgoalCoverage[g.id]||[];
      const lastUnv = issues.find(i => i.matchesSubgoal===g.id && i.unverifiable);
      const status = covered.length ? '✓' : (lastUnv ? '?' : '✗');
      const detail = covered.length
        ? `verified by: ${covered.map(c=>`r${c.round}/${c.lens}`).join('; ')}`
        : (lastUnv ? `unverifiable: ${safeInsert(lastUnv.title||'')}` : '本次未覆盖,需人工复盘');
      return `- ${status} **${safeInsert(g.id)}** · ${safeInsert(g.desc)} — ${detail}`;
    }).join('\n'))
  : '(无 goalSubgoals — 智能入口层未拆子项,详 "## 已知设计 risk" 节;收敛判据已降级到旧规则)';

const finalizeRefsBlock = (REF_IMAGES||[]).length
  ? REF_IMAGES.map(r => `- \`${safeInsert(r.path)}\` · role=${safeInsert(r.role)} · ${safeInsert(r.description)}${r.downsampled?' · ⚠ 已自动降采样':''}${(r.relatedSubgoals||[]).length?` · subgoals=[${r.relatedSubgoals.map(safeInsert).join(',')}]`:''}`).join('\n')
  : '(无 ref — 本次 GOAL 纯文字驱动)';

const finalizeMissingStates = issues.filter(i => i.unverifiable && Array.isArray(i.requiredStates) && i.requiredStates.length)
  .map(i => `- ${safeInsert(i.title||'')}: requiredStates=[${i.requiredStates.map(safeInsert).join(', ')}]`).join('\n') || '(无 — 本次 capture STATES 覆盖完整)';

const finalizePausedBlock = pausedReason
  ? `## ⚠ PAUSED · 触发判据 ${pausedReason} · 续修指引\n\n` +
    `本 run 在 r${round} 被机检判据触发暂停(详 \`${WORKDIR}/paused.md\`)。三选一:\n` +
    `1. 改 args(rubric/STATES/refImages 错位)起新 run\n` +
    `2. 写 \`${WORKDIR}/human-hint-r${round + 1}.md\`(自然语言)+ 主会话调 \`Workflow({resumeFromRunId: "${RUNTAG}"})\` 续跑同 run、保留已 verified\n` +
    `3. 弃 workflow,转主会话手工修\n\n` +
    `⚠ resumeFromRunId 仅同 session 有效(SKILL.md L138);跨 session 切换需起新 run。\n\n`
  : '';

await agent(
  `写 ${WORKDIR}/SUMMARY.md(runtag=${RUNTAG})。**顶部强制 4 节**(按下面顺序;若 pausedReason 非空,PAUSED 节放最顶上),其余节按 v2.6 之前的规则不变:\n\n` +
  finalizePausedBlock +
  `## 本次 GOAL\n\n` +
  safeBlock(`${safeInsert(GOAL)}\n\n### 子项清单(逐条覆盖状态;✓=本次 verified / ✗=未覆盖 / ?=unverifiable)\n\n${finalizeGoalBlock}\n\n> 完整版以 ${WORKDIR}/goal.md 为准。`, '```markdown') + `\n\n` +
  `## 参考图\n\n` +
  safeBlock(finalizeRefsBlock, '```markdown') + `\n\n` +
  `## 待补 STATES(unverifiable_due_to_missing_state)\n\n` +
  safeBlock(finalizeMissingStates, '```markdown') + `\n\n> 这些 issue 因 capture STATES 清单未含相应观察轴而无法判定;请下次 run 在主会话「智能入口层」补 STATES 后重跑。\n\n` +
  `## 已知设计 risk(架构边界,需人工复核)\n\n` +
  safeBlock(
    `1. **主会话拆 goalSubgoals + 分 ref role 是 single point of failure**:任何依赖 LLM 首轮拆解的设计都有同源故障(reviewer 同源 / tom 二审同源)。本次回讲点头是最低兜底,不严格验证 6 字段拆法。**请复盘者人工校验**:本次子项拆解(共 ${(GOAL_SUBGOALS||[]).length} 条)是否完整覆盖 GOAL 原文,refs role 分配是否正确。详 \`docs/research/2026-06-19_web-loop-goal-persistence/final_report.md\` §5.1。\n` +
    `2. **中途增量贴图 / 中途口语补子项无通道**:args 启动冻结是 GOAL 持久化语义本身。若本次 run 中途出现新需求 / 新参考图,需作为**新 run** 启动,不能注入跑到 r${round} 的 Workflow。详 final_report §5.2。`,
    '```markdown'
  ) + `\n\n` +
  `## 退出信息(原有节,保留)\n` +
  `退出 = ${exitReason}(converged=验收达标;stalled=must 台账连续 ${STALE_ROUNDS} 轮冻结、循环榨不出增量、交还人类,**非**收敛达标;max-rounds-hit=触顶),${round} 轮,走势=${JSON.stringify(history)},残留 must(确证缺陷)=${JSON.stringify(leftoverConfirmed)},待人工取证(unverifiable:仅证据缺失)=${JSON.stringify(leftoverUnverifiable)},残留 nice=${JSON.stringify(issues.filter(i=>i.severity==="nice"&&i.status!=="fixed"))},已验证项=${JSON.stringify(verifiedLog)}(SUMMARY 单列一节,与残留问题分开)。` +
  (SCAN_SUBSET&&converged?`\n⚠ 迭代用数据子集 ${SCAN_SUBSET} 压墙钟,终轮须用全量数据复核(按项目刷新方式重跑、不带子集过滤)+ 确认渲染。`:``) +
  `\n⚠ 完整性:不得把 stalled/max-rounds 伪装成 converged。`,
  { label:"finalize", phase:"finalize", model:"opus" }
);
log(`web-iterate-review done: ${exitReason}, ${round} rounds, ${leftoverMust.length} must left`);
