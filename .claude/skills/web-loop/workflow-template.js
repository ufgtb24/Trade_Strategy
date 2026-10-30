export const meta = {
  name: 'web-loop',
  description: '多轮迭代改进运行中的 web 应用：implement → verify（快照/smoke/刷新/截图）→ 多角度评审 → 台账判收敛',
  phases: [{ title: 'iterate', detail: '每轮 implement → verify → review' }],
};

// web-loop 的 Workflow 脚本模板（与 principles.md、wl.mjs、capture.mjs 配套）。
// 不直接运行：主会话写好 <workdir>/args.json 后跑 `node wl.mjs init <workdir>`，init 把校验过的参数与续跑 seed
//   以字面量写进下面的 INJECT 段，生成 <workdir>/workflow.js；主会话再用 Workflow({ scriptPath }) 启动，不传 args。
// 结构：INJECT（init 替换）→ CORE（纯函数：校验、schema、prompt、归并、判据、渲染、回放；wl.mjs 与测试按标记截取求值）
//   → SHELL（调 agent 的薄壳，不写业务逻辑）。
// 运行时约束：不能用 Date.now()、Math.random()、无参 new Date()；没有文件系统；顶层 return 合法。
//   语法检查不能用裸 node --check（会对顶层 return 误报），用 tests/dryrun.mjs 的 checkSyntax()。
// 回放纪律：同样的 cfg + 同样的 agent 结果序列 → 同样的状态 S（wl.mjs 据此从 journal 重建台账）。
//   所以 S 只由 CORE 函数修改，CORE 不改传入的 agent 结果，也不读任何运行时全局量。

// ==== INJECT BEGIN ====
const INJECTED = null;
// ==== INJECT END ====

// ==== CORE BEGIN ====

// ── 常量 ──
const BUILTIN_LENSES = ['ux', 'func', 'code', 'rival', 'razor', 'newbie', 'flow', 'contract'];
const SECTION_LENSES = ['razor', 'newbie', 'flow'];          // 内置但依赖 rubric 专节（任务清单、数法、正确含义、流程顺序）
const DEFAULT_LENSES = { app: ['ux', 'func', 'code'], prototype: ['newbie', 'razor', 'flow', 'contract'] };
const DEFAULT_VIEWPORT = { width: 2560, height: 1440, deviceScaleFactor: 1 };
const REMOVED_KEYS = { states: '截图配方只认 statesPath', captureBackend: '截图只走 capture.mjs', scanSubset: '数据子集写进刷新说明文件', shotsDir: '截图固定在 <workdir>/shots' };
const KINDS = ['frontend', 'backend', 'data', 'none'];
const REVIEW_OPTS = { agentType: 'Explore' };               // 评审质量明显变浅时改回 {}，只改这一处
const EXIT_TEXT = {
  converged: '全部达标', 'evidence-gap': '能修的都修完了，剩下的要人补证据', 'decision-gap': '能改的都改完了，剩下的要你拍板',
  blocked: '环境或代理一再失败', stalled: '评审正常进行，但没有进展', 'max-rounds': '跑满了本 run 的轮数',
  budget: '代理数或预算用完', error: '脚本意外异常', interrupted: '运行被打断，出口以 Workflow 的返回值为准',
};

const COMMON = '【通用约束】全部输出用中文（字段值、标题、说明）。不要用 SendMessage 或 ListAgents，也不要等任何回复；' +
  '需要主会话处理的事（参数错、截图配方错、缺权限）写进返回的 toMain 字段，然后继续本职工作。' +
  '不写报告或总结类文件，结果只通过结构化返回交回。不做 git commit / stash / checkout / reset / clean。';

// ── Schema ──
const STR = { type: 'string' }, STRS = { type: 'array', items: { type: 'string' } };
const TO_MAIN = { type: ['string', 'null'] };
const OPTIONS = { type: 'array', items: { type: 'object', required: ['choice', 'cost'], properties: { choice: STR, cost: STR } } };

const IMPL_SCHEMA = { type: 'object', required: ['kind', 'summary', 'changedFiles', 'attempts', 'hintsRead', 'overrides'],
  properties: {
    kind: { enum: KINDS },
    summary: STR,                                   // ≤10 行：改了什么、为什么
    changedFiles: STRS,
    attempts: { type: 'array', items: { type: 'object', required: ['issueId', 'approach'], properties: { issueId: STR, approach: STR } } },
    hintsRead: STRS,                                // intake 列出的 hint key（本轮已遵循）
    overrides: { type: 'array', items: { type: 'object', required: ['key', 'id', 'action'],
      properties: { key: STR, id: STR, action: STR, requiredStates: STRS, note: STR } } },   // intake 原样转交
    deferred: { type: 'array', items: { type: 'object', required: ['issueId', 'title', 'options', 'recommend'],      // 仅原型模式采信
      properties: { issueId: STR, title: STR, options: OPTIONS, recommend: STR, why: STR } } },
    toMain: TO_MAIN } };

const VERIFY_SCHEMA = { type: 'object', required: ['result'],
  properties: { result: { type: ['string', 'null'] },   // wl.mjs verify 最后一行文本本身（含 sig），由 CORE 解析；命令本身挂了填 null
    note: STR, toMain: TO_MAIN } };

function reviewerSchema(lens) {
  const s = { type: 'object', required: ['known', 'subgoals', 'issues', 'directions'],
    properties: {
      known: { type: 'array', items: { type: 'object', required: ['id', 'status', 'evidence'],
        properties: { id: STR, status: { enum: ['present', 'gone', 'unverifiable', 'decision'] }, evidence: STR, requiredStates: STRS } } },
      subgoals: { type: 'array', items: { type: 'object', required: ['id', 'status', 'evidence'],
        properties: { id: STR, status: { enum: ['met', 'unmet', 'unverifiable'] }, evidence: STR, requiredStates: STRS } } },
      issues: { type: 'array', items: { type: 'object', required: ['title', 'severity', 'detail', 'evidence'],
        properties: { title: STR, severity: { enum: ['must', 'nice'] }, state: { type: ['string', 'null'] },
          subgoal: { type: ['string', 'null'] }, detail: STR, evidence: STR,
          matchesIssueId: { type: ['string', 'null'] }, unverifiable: { type: 'boolean' }, requiredStates: STRS, files: STRS } } },
      directions: { type: 'array', items: { type: 'object', required: ['title', 'options', 'recommend'],
        properties: { title: STR, options: OPTIONS, recommend: STR, why: STR } } },
      toMain: TO_MAIN } };
  if (lens === 'razor') s.properties.counts = { type: 'object', properties: { now: { type: 'object' }, baseline: { type: 'object' } } };
  return s;
}

// ── 小工具 ──
const isObj = x => x != null && typeof x === 'object' && !Array.isArray(x);
const isStr = x => typeof x === 'string';
const nonEmpty = x => isStr(x) && x.trim() !== '';
const clone = x => (x === undefined ? undefined : JSON.parse(JSON.stringify(x)));
const uniq = a => [...new Set(a)];
const strs = a => (Array.isArray(a) ? a.filter(isStr) : []);
const clip = (s, n) => { s = s == null ? '' : String(s); return s.length > n ? s.slice(0, n) + '…（截断）' : s; };
const indent = s => String(s).replace(/\n/g, '\n    ');
const q = s => (/^[\w./@:=+,-]+$/.test(String(s)) ? String(s) : `'${String(s).replace(/'/g, `'\\''`)}'`);   // shell 引号
const absIn = (root, p) => (!isStr(p) || !root || p.startsWith('/') ? p : root.replace(/\/$/, '') + '/' + p.replace(/^\.\//, ''));
const stripLine = f => String(f).replace(/:\d+(:\d+)?$/, '').replace(/^\.\//, '');
function rtag(n) { return 'r' + String(n).padStart(2, '0'); }
function roundAgentEstimate(cfg) { return 2 + cfg.lenses.length; }
function budgetDetail(cfg, used) { return `已用 ${used} 个代理，再跑一轮（${roundAgentEstimate(cfg)} 个）会超过上限 ${cfg.maxAgents}`; }

/** 键递归排序后 JSON 序列化，再算 32 位 FNV-1a（按 UTF-16 码元），8 位小写十六进制。只用来校验 verify 结果经 LLM 转交是否走样。 */
function canonHash(x) {
  const canon = v => (Array.isArray(v) ? v.map(canon) : isObj(v) ? Object.keys(v).sort().reduce((o, k) => { o[k] = canon(v[k]); return o; }, {}) : v);
  const s = JSON.stringify(canon(x)) ?? '';
  let h = 0x811c9dc5;
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 0x01000193) >>> 0; }
  return h.toString(16).padStart(8, '0');
}

/** 本轮约定路径：由轮号算出，不经 LLM 转交 */
function paths(cfg, round) {
  const W = cfg.W, rt = rtag(round);
  return { W, rubric: `${W}/rubric.md`, principles: `${cfg.skill}/principles.md`, wl: `node ${q(cfg.skill + '/wl.mjs')}`, cap: `node ${q(cfg.skill + '/capture.mjs')}`,
    manifest: `${W}/shots/${rt}_manifest.json`, r00: `${W}/shots/r00_manifest.json`,
    verifyJson: `${W}/snap/${rt}.verify.json`, rejected: `${W}/snap/${rt}.rejected.diff` };
}

// ── 参数校验（init 与 SHELL 共用）──
/**
 * 校验参数并补默认值。derived 是 init 从文件推出来的量：terms（rubric「术语表」的词）、root（repo root 绝对路径）。
 * 返回 {cfg, errors}；cfg 另带 terms、root、W（运行目录绝对路径）、skill（skill 目录绝对路径）四个推导字段，写回文件时要去掉。
 */
function validateArgs(A, derived) {
  const errors = [];
  if (!isObj(A)) return { cfg: null, errors: ['参数不是对象'] };
  const cfg = clone(A);
  for (const k of Object.keys(REMOVED_KEYS)) if (cfg[k] !== undefined) errors.push(`${k} 已删除（${REMOVED_KEYS[k]}）`);
  cfg.mode = cfg.mode ?? 'app';
  if (!['app', 'prototype'].includes(cfg.mode)) errors.push(`mode 只能是 app 或 prototype：${cfg.mode}`);
  const proto = cfg.mode === 'prototype';
  for (const k of ['runtag', 'workdir', 'goal', 'url', 'statesPath', 'uiDir', 'rubricPath', 'smokeCmd'])
    if (!nonEmpty(cfg[k])) errors.push(`缺少必填项 ${k}`);
  cfg.skillDir = nonEmpty(cfg.skillDir) ? cfg.skillDir : '.claude/skills/web-loop';

  if (cfg.lenses == null) cfg.lenses = DEFAULT_LENSES[proto ? 'prototype' : 'app'].slice();
  if (!Array.isArray(cfg.lenses) || !cfg.lenses.length) { errors.push('lenses 至少 1 个'); cfg.lenses = []; }
  else {
    cfg.lenses = uniq(cfg.lenses);
    for (const L of cfg.lenses) if (!isStr(L) || !/^[a-z][a-z0-9_-]*$/.test(L) || L === 'workflow' || L === 'implementer') errors.push(`角度名不合法：${L}`);
  }

  if (!Array.isArray(cfg.goalSubgoals) || !cfg.goalSubgoals.length) { errors.push('goalSubgoals 至少 1 条'); cfg.goalSubgoals = []; }
  else {
    const seen = new Set();
    cfg.goalSubgoals.forEach((g, k) => {
      if (!isObj(g)) { errors.push(`子项 #${k + 1} 不是对象`); return; }
      if (!nonEmpty(g.id)) errors.push(`子项 #${k + 1} 缺 id`);
      else if (seen.has(g.id)) errors.push(`子项 id 重复：${g.id}`);
      else seen.add(g.id);
      if (!nonEmpty(g.desc)) errors.push(`子项 ${g.id} 缺 desc`);
      if (!Array.isArray(g.lenses) || !g.lenses.length) errors.push(`子项 ${g.id} 要写负责角度 lenses`);
      else for (const L of g.lenses) if (!cfg.lenses.includes(L)) errors.push(`子项 ${g.id} 的负责角度 ${L} 不在 lenses 里`);
      if (g.states != null && !Array.isArray(g.states)) errors.push(`子项 ${g.id} 的 states 要是数组`);
      g.lenses = strs(g.lenses); g.states = strs(g.states);
    });
    cfg.goalSubgoals = cfg.goalSubgoals.filter(isObj);
  }

  const intIn = (v, lo, hi) => Number.isInteger(v) && v >= lo && v <= hi;
  cfg.maxRounds = cfg.maxRounds ?? (proto ? 3 : 5);
  if (!intIn(cfg.maxRounds, 1, 20)) errors.push('maxRounds 取 1～20 的整数');
  // staleRounds 大于 maxRounds 等于本 run 内不判停滞，允许
  cfg.staleRounds = cfg.staleRounds ?? Math.min(2, intIn(cfg.maxRounds, 1, 20) ? cfg.maxRounds : 2);
  if (!intIn(cfg.staleRounds, 1, 20)) errors.push('staleRounds 取 1～20 的整数');
  cfg.maxAgents = cfg.maxAgents ?? null;
  if (cfg.maxAgents !== null && !(Number.isInteger(cfg.maxAgents) && cfg.maxAgents >= 2 + cfg.lenses.length))
    errors.push(`maxAgents 要么为 null，要么是不小于 ${2 + cfg.lenses.length} 的整数`);

  cfg.viewport = { ...DEFAULT_VIEWPORT, ...(isObj(cfg.viewport) ? cfg.viewport : {}) };
  for (const k of ['width', 'height', 'deviceScaleFactor']) if (!(typeof cfg.viewport[k] === 'number' && cfg.viewport[k] > 0)) errors.push(`viewport.${k} 要是正数`);

  cfg.refImages = cfg.refImages ?? [];
  if (!Array.isArray(cfg.refImages)) { errors.push('refImages 要是数组'); cfg.refImages = []; }
  for (const k of ['restartCmd', 'healthUrl', 'refreshDataCmd', 'continueFrom', 'contractPath']) cfg[k] = nonEmpty(cfg[k]) ? cfg[k] : null;
  cfg.schemeFiles = cfg.schemeFiles ?? [];
  if (!Array.isArray(cfg.schemeFiles) || cfg.schemeFiles.some(f => !nonEmpty(f))) { errors.push('schemeFiles 要是非空路径的数组'); cfg.schemeFiles = strs(cfg.schemeFiles); }
  if (proto) {
    if (!cfg.schemeFiles.length) errors.push('原型模式要写 schemeFiles（演示数据、模拟逻辑所在的方案文件）');
    if (!cfg.contractPath) errors.push('原型模式要写 contractPath（后端要求清单）');
  } else {
    if (cfg.schemeFiles.length || cfg.contractPath) errors.push('app 模式下 schemeFiles、contractPath 必须为空');
    if (cfg.lenses.includes('contract')) errors.push('contract 角度核对的是原型的后端要求清单，只用于原型模式');
  }

  cfg.terms = strs(isObj(derived) ? derived.terms : null);
  cfg.root = isObj(derived) && nonEmpty(derived.root) ? derived.root : null;
  cfg.W = absIn(cfg.root, cfg.workdir);
  cfg.skill = absIn(cfg.root, cfg.skillDir);
  return { cfg, errors };
}

// ── 台账 ──
function mkIssue(p) {
  return { id: null, lens: null, title: '', severity: 'must', detail: '', evidence: '', state: null, subgoal: null,
    unverifiable: false, requiredStates: [], humanUnverifiable: false, files: [], status: 'open', waiveReason: null,
    bornRound: null, lastSeenRound: null, fixedRound: null, regressions: 0, reopenedBy: null, disputed: false,
    alsoReportedBy: [], dissent: [], attempts: [], needsDecision: null, proposal: null, decisionId: null, ...p };
}

function initState(cfg, seed) {
  const S = { round: 0, runFirstRound: 1, issues: [], directions: [], subgoals: {}, rounds: [],
    lastKind: 'frontend', forceDataRefresh: false, streak: 0, skipStreak: 0, missStreak: {}, everReviewed: false, bestMet: 0, lastGreenRound: 0,
    counters: {}, doneControl: [], overrideErrors: [], toMain: [], baselineCounts: {}, lastCounts: {}, exit: null, exitDetail: null };
  for (const g of cfg.goalSubgoals) S.subgoals[g.id] = { desc: g.desc, lenses: g.lenses.slice(), byLens: {} };
  for (const L of cfg.lenses) S.missStreak[L] = 0;
  if (seed == null) return S;
  if (!isObj(seed) || seed.v !== 1) throw new Error(`BLOCKED: 续跑 seed 的版本不认识（v=${isObj(seed) ? seed.v : typeof seed}），请用当前的 wl.mjs 重新 init`);
  S.round = Number.isInteger(seed.round) ? seed.round : 0;
  S.runFirstRound = S.round + 1;
  S.issues = (Array.isArray(seed.issues) ? seed.issues : []).filter(isObj).map(i => mkIssue(clone(i)));
  S.directions = (Array.isArray(seed.directions) ? seed.directions : []).filter(isObj).map(clone);
  S.everReviewed = seed.everReviewed === true;
  S.lastKind = KINDS.includes(seed.lastKind) ? seed.lastKind : 'frontend';
  S.baselineCounts = isObj(seed.baselineCounts) ? clone(seed.baselineCounts) : {};
  S.lastCounts = isObj(seed.lastCounts) ? clone(seed.lastCounts) : {};
  S.doneControl = strs(seed.doneControl);
  for (const g of cfg.goalSubgoals) {
    const o = isObj(seed.subgoals) ? seed.subgoals[g.id] : null;
    if (isObj(o) && o.desc === g.desc && isObj(o.byLens)) S.subgoals[g.id].byLens = clone(o.byLens);   // 只认 id 与 desc 都没变的
  }
  for (const i of S.issues)
    if (i.status === 'open' && i.lens !== 'workflow' && !cfg.lenses.includes(i.lens)) { i.status = 'waived'; i.waiveReason = '所属角度本次未启用'; }
  return S;
}

/** 续跑 seed：开着的条目给全字段，fixed / waived 只留骨架 */
function toSeed(S) {
  const slim = i => ({ id: i.id, lens: i.lens, title: i.title, severity: i.severity, state: i.state, status: i.status, fixedRound: i.fixedRound, disputed: i.disputed });
  const subgoals = {};
  for (const [id, g] of Object.entries(S.subgoals || {})) subgoals[id] = { desc: g.desc, lenses: g.lenses, byLens: g.byLens };
  return clone({ v: 1, round: S.round, everReviewed: S.everReviewed, lastKind: S.lastKind,
    baselineCounts: S.baselineCounts || {}, lastCounts: S.lastCounts || {}, doneControl: S.doneControl || [],
    issues: (S.issues || []).map(i => (i.status === 'open' ? i : slim(i))), directions: S.directions || [], subgoals });
}

function newRec(round, kind) {
  return { round, kind, implOk: false, implSummary: '', changedFiles: [], verifyOk: false, verifyNote: '', sigOk: false,
    smoke: null, refreshOk: null, capture: null, reviewed: false, skipReason: null, missingLenses: [],
    fixed: [], born: [], reopened: [], dissents: 0, badMatch: [], untabled: {}, unverifiableRejected: [], goneIgnored: [],
    metDowngraded: [], untabledSubgoals: {}, malformed: [], deferRejected: [], agreed: [], overridesApplied: [],
    schemeTouched: [], envOk: null, noChange: false, kindAdjusted: null, met: [], sg: {},
    openConfirmed: 0, openUnverifiable: 0, progress: false, streak: 0 };
}
const curRec = (S, round) => { const r = S.rounds[S.rounds.length - 1]; return r && r.round === round ? r : null; };
function nextId(S, prefix) { S.counters[prefix] = (S.counters[prefix] || 0) + 1; return `${prefix}-${S.counters[prefix]}`; }

// ── 形状校验：任何返回形状都不让 CORE 抛错；不改传入对象 ──
const optsOf = a => (Array.isArray(a) ? a : []).filter(o => isObj(o) && isStr(o.choice)).map(o => ({ choice: o.choice, cost: isStr(o.cost) ? o.cost : '' }));
const toMainOf = x => (isObj(x) && nonEmpty(x.toMain) ? x.toMain : null);
/** 所需数组字段缺失按空数组；类型不对或 kind 非法 → null（整份作废）；数组里形状不对的元素只丢掉那一个 */
function normalizeImpl(x) {
  if (!isObj(x) || !KINDS.includes(x.kind)) return null;
  const f = {};
  for (const k of ['changedFiles', 'attempts', 'hintsRead', 'overrides', 'deferred']) {
    if (x[k] == null) f[k] = [];
    else if (Array.isArray(x[k])) f[k] = x[k];
    else return null;
  }
  return { kind: x.kind, summary: isStr(x.summary) ? x.summary : '', changedFiles: strs(f.changedFiles),
    attempts: f.attempts.filter(a => isObj(a) && nonEmpty(a.issueId) && isStr(a.approach)).map(a => ({ issueId: a.issueId, approach: a.approach })),
    hintsRead: strs(f.hintsRead),
    overrides: f.overrides.filter(o => isObj(o) && nonEmpty(o.key)).map(o => ({ key: o.key, id: isStr(o.id) ? o.id : null,
      action: isStr(o.action) ? o.action : null, requiredStates: strs(o.requiredStates), note: isStr(o.note) ? o.note : '' })),
    deferred: f.deferred.filter(d => isObj(d) && nonEmpty(d.issueId) && isStr(d.title)).map(d => ({ issueId: d.issueId, title: d.title,
      options: optsOf(d.options), recommend: isStr(d.recommend) ? d.recommend : '', why: isStr(d.why) ? d.why : '' })),
    toMain: toMainOf(x) };
}
function normalizeReview(x) {
  if (!isObj(x)) return null;
  const f = {};
  for (const k of ['known', 'subgoals', 'issues', 'directions']) {
    if (x[k] == null) f[k] = [];
    else if (Array.isArray(x[k])) f[k] = x[k];
    else return null;
  }
  const s = v => (isStr(v) ? v : '');
  return {
    known: f.known.filter(k => isObj(k) && isStr(k.id) && ['present', 'gone', 'unverifiable', 'decision'].includes(k.status))
      .map(k => ({ id: k.id, status: k.status, evidence: s(k.evidence), requiredStates: strs(k.requiredStates) })),
    subgoals: f.subgoals.filter(g => isObj(g) && isStr(g.id) && ['met', 'unmet', 'unverifiable'].includes(g.status))
      .map(g => ({ id: g.id, status: g.status, evidence: s(g.evidence), requiredStates: strs(g.requiredStates) })),
    issues: f.issues.filter(i => isObj(i) && nonEmpty(i.title) && ['must', 'nice'].includes(i.severity))
      .map(i => ({ title: i.title, severity: i.severity, state: nonEmpty(i.state) ? i.state : null, subgoal: nonEmpty(i.subgoal) ? i.subgoal : null,
        detail: s(i.detail), evidence: s(i.evidence), matchesIssueId: nonEmpty(i.matchesIssueId) ? i.matchesIssueId : null,
        unverifiable: i.unverifiable === true, requiredStates: strs(i.requiredStates), files: strs(i.files) })),
    directions: f.directions.filter(d => isObj(d) && nonEmpty(d.title))
      .map(d => ({ title: d.title, options: optsOf(d.options), recommend: s(d.recommend), why: s(d.why) })),
    counts: isObj(x.counts) ? { now: isObj(x.counts.now) ? clone(x.counts.now) : null, baseline: isObj(x.counts.baseline) ? clone(x.counts.baseline) : null } : null,
    toMain: toMainOf(x) };
}
/**
 * 从 verify 代理的返回里取出短结果对象（未规整，签名就按它核对）。约定形式是 result = 最后那一行文本本身；
 * 兜底认两种走样：代理把那一行解析成了对象，或包了一层（如 {line:"…"}）。解析不出带 smoke 的对象 → null。
 */
function verifyLine(v) {
  const parse = t => { const line = String(t).trim().split('\n').filter(x => x.trim()).pop(); try { return line ? JSON.parse(line) : null; } catch { return null; } };
  const r = isObj(v) ? v.result : null;
  if (isStr(r)) { const o = parse(r); return isObj(o) && isObj(o.smoke) ? o : null; }
  if (!isObj(r)) return null;
  if (isObj(r.smoke)) return r;
  for (const x of Object.values(r)) if (isStr(x)) { const o = parse(x); if (isObj(o) && isObj(o.smoke)) return o; }
  return null;
}
/** verify 结果规整：取不出短结果 → null */
function normalizeVerify(v) {
  const r = verifyLine(v);
  if (!r) return null;
  const cap = r.capture;
  if (cap != null && !isObj(cap)) return null;
  const tri = x => (x === true ? true : x === false ? false : null);
  return { round: r.round, kind: r.kind, kindAdjusted: nonEmpty(r.kindAdjusted) ? r.kindAdjusted : null,
    envOk: r.envOk !== false, noChange: r.noChange === true, journalCopied: r.journalCopied === true, snapOk: r.snapOk !== false,
    changedCount: Number.isFinite(r.changedCount) ? r.changedCount : null, schemeTouched: strs(r.schemeTouched),
    smoke: { pass: tri(r.smoke.pass), flaky: r.smoke.flaky === true, rolledBack: r.smoke.rolledBack === true, envBroken: r.smoke.envBroken === true },
    refreshOk: tri(r.refreshOk),
    capture: cap == null ? null : { okStates: strs(cap.okStates), failedStates: strs(cap.failedStates), errorStates: strs(cap.errorStates), newErrors: strs(cap.newErrors) },
    manifest: nonEmpty(r.manifest) ? r.manifest : null };
}

/**
 * 这一轮能不能评审。sig 对不上仍可评审（截图在磁盘上），但不按结果开关 wf 条目、okStates 视为未知、不能从这轮收尾。
 * 给了 round 时，结果行里的轮号对不上（转交了别一轮的那行）也按签名不符处理。
 */
function reviewGate(verify, round) {
  const raw = verifyLine(verify);
  const res = normalizeVerify(verify);
  let sigOk = false;
  if (raw && isStr(raw.sig)) { const rest = {}; for (const k of Object.keys(raw)) if (k !== 'sig') rest[k] = raw[k]; sigOk = canonHash(rest) === raw.sig && (round == null || raw.round === round); }
  const out = skipReason => ({ reviewable: !skipReason, skipReason: skipReason || null, sigOk, res,
    okStates: sigOk && res && res.capture ? res.capture.okStates.slice() : null });
  if (!res) return out('verify 未交回');
  if (!res.envOk) return out('服务不可达');
  if (res.noChange) return out('本轮无改动');
  if (res.smoke.pass === false)
    return out(res.smoke.rolledBack ? '本轮改动使 smoke 失败，已退回' : res.smoke.envBroken ? '退回本轮改动后 smoke 仍红（环境或基线坏了）' : 'smoke 失败');
  if (res.smoke.pass !== true) return out('smoke 未跑');
  if (res.refreshOk === false) return out('刷新失败');
  if (!res.capture || !res.capture.okStates.length) return out('无可用截图');
  return out(null);
}

/** 原型模式：条目是否属于方案层（files 落在 schemeFiles 上，或标题与描述里出现术语表的词） */
function inSchemeLayer(cfg, iss) {
  const schemes = cfg.schemeFiles.map(stripLine);
  if ((iss.files || []).some(f => { const p = stripLine(f); return schemes.some(s => p === s || p.startsWith(s.replace(/\/$/, '') + '/') || (cfg.root && p === absIn(cfg.root, s))); })) return true;
  const text = `${iss.title || ''}\n${iss.detail || ''}`;
  return cfg.terms.some(t => t && text.includes(t));
}

/** verify 之前调用：新建本轮记录，吸收 implementer 的返回（kind、overrides、attempts、hint、挂起提议） */
function applyImpl(cfg, S, round, impl) {
  const im = impl == null ? null : normalizeImpl(impl);
  S.lastKind = im ? im.kind : S.lastKind;
  const rec = newRec(round, S.forceDataRefresh ? 'data' : S.lastKind);       // rec.kind 是交给 verify 的档位
  S.rounds.push(rec);
  if (impl != null && !im) rec.malformed.push(`impl-${rtag(round)}`);
  rec.implOk = !!im;
  if (!im) return;
  rec.implSummary = im.summary; rec.changedFiles = im.changedFiles;
  const byId = id => S.issues.find(i => i.id === id);
  for (const o of im.overrides) {
    if (S.doneControl.includes(o.key)) continue;
    S.doneControl.push(o.key);
    const iss = o.id ? byId(o.id) : null;
    let err = null;
    if (!iss) err = `id 不存在：${o.id}`;
    else if (o.action === 'waive') { iss.status = 'waived'; iss.waiveReason = `人工：${o.note}`; }
    else if (o.action === 'unverifiable') {
      iss.unverifiable = true; iss.humanUnverifiable = true;
      iss.requiredStates = o.requiredStates.length ? o.requiredStates : iss.requiredStates.length ? iss.requiredStates : iss.state ? [iss.state] : [];
    } else err = `action 只能是 waive 或 unverifiable：${o.action}`;
    if (err) S.overrideErrors.push({ round, key: o.key, id: o.id, action: o.action, error: err });
    else rec.overridesApplied.push(o.id);
  }
  for (const a of im.attempts) { const iss = byId(a.issueId); if (iss) iss.attempts.push({ round, approach: a.approach }); }
  for (const h of im.hintsRead) if (!S.doneControl.includes(h)) S.doneControl.push(h);
  if (im.toMain) S.toMain.push({ round, from: 'impl', text: im.toMain });
  for (const d of im.deferred) {
    const iss = byId(d.issueId);
    let why = null;
    if (cfg.mode !== 'prototype') why = 'app 模式';
    else if (!iss) why = '条目不存在';
    else if (iss.status !== 'open' || iss.severity !== 'must') why = '不是开着的 must';
    else if (iss.lens === 'workflow') why = '脚本条目不能挂起';
    else if (iss.needsDecision === 'agreed') why = '已同意挂起';
    else if (!inSchemeLayer(cfg, iss)) why = '与方案层无关';
    if (why) { rec.deferRejected.push({ id: d.issueId, reason: why }); continue; }
    // 只是提议：照常算确证 must、不算进展，等负责角度当轮表态（被评方不能自己豁免 must）
    iss.needsDecision = 'proposed';
    iss.proposal = { round, title: d.title, options: d.options, recommend: d.recommend, why: d.why };
  }
}

/** 一轮的归并与出口判定（含脚本条目、评审归并、统计、出口） */
function reduceRound(cfg, S, round, verify, reviews) {
  let rec = curRec(S, round);
  if (!rec) { rec = newRec(round, S.lastKind); S.rounds.push(rec); }
  const gate = reviewGate(verify, round), res = gate.res, rt = rtag(round), P = paths(cfg, round);
  if (isObj(verify) && verify.result != null && !res) rec.malformed.push(`verify-${rt}`);
  rec.verifyOk = !!res; rec.sigOk = gate.sigOk; rec.reviewed = gate.reviewable; rec.skipReason = gate.skipReason;
  rec.verifyNote = isObj(verify) && isStr(verify.note) ? clip(verify.note, 500) : '';
  if (res) {
    rec.smoke = res.smoke; rec.refreshOk = res.refreshOk; rec.envOk = res.envOk; rec.noChange = res.noChange;
    rec.kindAdjusted = res.kindAdjusted; rec.schemeTouched = res.schemeTouched;
    rec.capture = res.capture ? { ok: res.capture.okStates, failed: res.capture.failedStates, newErrors: res.capture.newErrors } : null;
  }
  if (toMainOf(verify)) S.toMain.push({ round, from: 'verify', text: verify.toMain });
  const byId = id => S.issues.find(i => i.id === id);

  // 1) 脚本条目：只在签名对得上时按 verify 结果开关
  const openWf = (id, title, detail, state) => {
    let iss = byId(id);
    if (!iss) { iss = mkIssue({ id, lens: 'workflow', title, severity: 'must', detail, state: state || null, status: 'open', bornRound: round }); S.issues.push(iss); rec.born.push(id); }
    else if (iss.status === 'fixed') { iss.status = 'open'; iss.regressions++; rec.reopened.push(id); }
    iss.lastSeenRound = round; iss.detail = detail;
  };
  const closeWf = id => { const iss = byId(id); if (iss && iss.status === 'open') { iss.status = 'fixed'; iss.fixedRound = round; rec.fixed.push(id); } };
  if (res && gate.sigOk) {
    if (res.smoke.rolledBack) {
      openWf('wf-regress', `第 ${round} 轮改动使 smoke 失败，已退回`, `smoke 输出见 ${P.verifyJson}；被退回的改动见 ${P.rejected}`);
      S.lastGreenRound = round;                      // 退回后复跑是绿的，green 快照已更新为退回后的树
    }
    if (res.smoke.pass === true) { closeWf('wf-regress'); S.lastGreenRound = round; }
    const c = res.capture;
    if (c) {
      for (const s of c.failedStates) openWf('wf-state-' + s, '截图失败：' + s, `原因见 ${P.manifest} 中该态的 error`, s);
      for (const s of c.okStates) closeWf('wf-state-' + s);
      for (const s of c.newErrors) openWf('wf-pageerror-' + s, '新出现页面报错：' + s, `报错原文见 ${P.manifest} 中该态的 pageErrors`, s);
      for (const s of c.okStates) if (!c.errorStates.includes(s)) closeWf('wf-pageerror-' + s);
    }
  }

  // 按说明文件刷新数据是在 verify 之前做的：这一轮若被退回，后端与数据还停在被拒的代码上，下一轮强制再刷一次
  if (res && rec.kind === 'data' && res.refreshOk === true) S.forceDataRefresh = false;
  if (res && gate.sigOk && res.smoke.rolledBack && rec.kind === 'data' && mdRefresh(cfg)) S.forceDataRefresh = true;

  // 2) 评审归并
  const R = cfg.lenses.map((L, k) => {
    const raw = gate.reviewable && Array.isArray(reviews) ? reviews[k] : null;
    const r = raw == null ? null : normalizeReview(raw);
    if (raw != null && !r) rec.malformed.push(`review-${L}-${rt}`);
    return r;
  });
  if (gate.reviewable) {
    const okSet = gate.okStates ? new Set(gate.okStates) : null;
    const accept = Rs => Rs.length > 0 && (okSet === null || Rs.some(s => !okSet.has(s)));   // 点名的态本轮已截成功就不采信
    // 第一遍：各角度对自己名下条目与负责子项的表态（只碰自己名下的东西，与角度顺序无关）
    cfg.lenses.forEach((L, k) => {
      const r = R[k];
      if (!r) { rec.missingLenses.push(L); return; }
      const own = S.issues.filter(i => i.status === 'open' && i.lens === L), ownIds = own.map(i => i.id), tabled = new Set();
      for (const kn of r.known) {
        const iss = own.find(i => i.id === kn.id && i.status === 'open');
        if (!iss) continue;
        tabled.add(iss.id);
        const present = () => { iss.lastSeenRound = round; iss.evidence = kn.evidence; if (!iss.humanUnverifiable) iss.unverifiable = false; };
        if (kn.status === 'gone') {
          if (okSet && iss.state && !okSet.has(iss.state)) { rec.goneIgnored.push(iss.id); continue; }   // 那个态本轮没截成功，凭不了证据
          iss.status = 'fixed'; iss.fixedRound = round; rec.fixed.push(iss.id);
          if (iss.reopenedBy) { iss.disputed = true; iss.reopenedBy = null; }
          iss.needsDecision = null;
        } else if (kn.status === 'present') {
          present();
          if (iss.needsDecision === 'proposed') { iss.needsDecision = null; rec.deferRejected.push({ id: iss.id, reason: '负责角度不同意' }); }
        } else if (kn.status === 'unverifiable') {
          const Rs = kn.requiredStates.length ? kn.requiredStates : iss.requiredStates.length ? iss.requiredStates : iss.state ? [iss.state] : [];
          if (accept(Rs)) { iss.lastSeenRound = round; iss.evidence = kn.evidence; iss.unverifiable = true; iss.requiredStates = Rs; }
          else { present(); rec.unverifiableRejected.push(iss.id); }
        } else {                                     // decision：同意这条要用户拍板
          if (iss.needsDecision === 'proposed') {
            present();
            const p = iss.proposal || {};
            const did = nextId(S, `dir-impl-r${round}`);
            S.directions.push({ id: did, lens: 'implementer', round, title: p.title || iss.title, options: p.options || [], recommend: p.recommend || '', why: p.why || '', alsoBy: [], issueId: iss.id });
            iss.needsDecision = 'agreed'; iss.decisionId = did; rec.agreed.push(iss.id);
          } else if (iss.needsDecision === 'agreed') present();
          else { present(); rec.deferRejected.push({ id: iss.id, reason: '没有挂起提议却回 decision，按 present 处理' }); }
        }
      }
      const untabled = ownIds.filter(id => !tabled.has(id));
      if (untabled.length) rec.untabled[L] = untabled;
      const mine = cfg.goalSubgoals.filter(g => g.lenses.includes(L)), said = new Set();
      for (const e of r.subgoals) {
        const g = mine.find(x => x.id === e.id);
        if (!g) continue;
        said.add(g.id);
        let status = e.status, Rs = e.requiredStates.length ? e.requiredStates : g.states;
        if (status === 'unverifiable' && !accept(Rs)) { status = 'unmet'; rec.unverifiableRejected.push(g.id); }
        if (status === 'met' && okSet && g.states.length && !g.states.some(s => okSet.has(s))) { status = 'unverifiable'; Rs = g.states; rec.metDowngraded.push(g.id); }
        S.subgoals[g.id].byLens[L] = { status, evidence: e.evidence, requiredStates: status === 'unverifiable' ? Rs : [], round };
      }
      const missed = mine.filter(g => !said.has(g.id)).map(g => g.id);
      if (missed.length) rec.untabledSubgoals[L] = missed;
    });
    // 第二遍：新问题、引用、方向题、计数
    cfg.lenses.forEach((L, k) => {
      const r = R[k];
      if (!r) return;
      for (const it of r.issues) {
        let unverifiable = it.unverifiable, Rs = it.requiredStates.slice(), rejected = false;
        if (unverifiable && !Rs.length && it.state) Rs = [it.state];
        if (unverifiable && !accept(Rs)) { unverifiable = false; rejected = true; }
        const m = it.matchesIssueId ? byId(it.matchesIssueId) : null;
        if (m && m.status === 'open') { m.lastSeenRound = round; if (m.lens !== L && !m.alsoReportedBy.includes(L)) m.alsoReportedBy.push(L); continue; }
        if (m && m.status === 'fixed') {
          const reopen = by => { m.status = 'open'; m.regressions++; m.reopenedBy = by; m.lastSeenRound = round; m.evidence = it.evidence; rec.reopened.push(m.id); };
          if (L === m.lens) reopen(null);
          else if (m.fixedRound === round || m.disputed) { m.dissent.push({ round, lens: L, evidence: it.evidence }); rec.dissents++; }
          else reopen(L);
          continue;
        }
        if (m && m.status === 'waived') continue;
        if (it.matchesIssueId && !m) rec.badMatch.push(it.matchesIssueId);
        const same = S.issues.find(i => i.lens === L && i.status === 'open' && i.title === it.title);
        if (same) { same.lastSeenRound = round; continue; }
        const id = nextId(S, `${L}-r${round}`);
        S.issues.push(mkIssue({ id, lens: L, title: it.title, severity: it.severity, detail: it.detail, evidence: it.evidence,
          state: it.state, subgoal: it.subgoal, unverifiable, requiredStates: unverifiable ? Rs : it.requiredStates, files: it.files,
          bornRound: round, lastSeenRound: round }));
        rec.born.push(id);
        if (rejected) rec.unverifiableRejected.push(id);
      }
      for (const d of r.directions) {
        const ex = S.directions.find(x => x.title === d.title);
        if (ex) { if (ex.lens !== L && !ex.alsoBy.includes(L)) ex.alsoBy.push(L); continue; }
        S.directions.push({ id: nextId(S, `dir-${L}-r${round}`), lens: L, round, title: d.title, options: d.options, recommend: d.recommend, why: d.why, alsoBy: [] });
      }
      if (r.counts) {
        if (!S.baselineCounts[L] && r.counts.baseline) S.baselineCounts[L] = r.counts.baseline;
        if (r.counts.now) S.lastCounts[L] = r.counts.now;
      }
      if (r.toMain) S.toMain.push({ round, from: `review-${L}`, text: r.toMain });
    });
  }

  // 3) 统计
  const isMustOpen = i => i.status === 'open' && i.severity === 'must';
  const confirmedOpen = S.issues.filter(i => isMustOpen(i) && !i.unverifiable);
  const unverifOpen = S.issues.filter(i => isMustOpen(i) && i.unverifiable);
  const sg = {};
  for (const g of cfg.goalSubgoals) {
    if (!gate.reviewable) { sg[g.id] = 'pending'; continue; }
    const st = g.lenses.map(L => { const b = S.subgoals[g.id].byLens[L]; return b && b.round === round ? b.status : 'pending'; });   // 只认本轮证据
    // 未表态视同 pending，排在 unverifiable 之前：子项还有负责角度没给结论时，不能算「只剩取证缺口」
    sg[g.id] = st.every(x => x === 'met') ? 'met' : st.includes('unmet') ? 'unmet' : st.includes('pending') ? 'pending' : 'unverifiable';
  }
  const met = Object.keys(sg).filter(id => sg[id] === 'met');
  // wf-regress 被关闭不算进展：那只是回到上一轮的状态
  const fixedNow = S.issues.filter(i => i.status === 'fixed' && i.fixedRound === round && i.severity === 'must' && i.id !== 'wf-regress').length;
  const progress = fixedNow > 0 || met.length > S.bestMet || rec.agreed.length > 0;
  S.bestMet = Math.max(S.bestMet, met.length);
  if (gate.reviewable && !S.everReviewed) { S.everReviewed = true; S.streak = 0; }     // 第一个评审轮只作起点
  else S.streak = progress ? 0 : S.streak + 1;
  S.skipStreak = gate.reviewable || (res && res.noChange) ? 0 : S.skipStreak + 1;     // noChange 只计入 streak
  if (gate.reviewable) cfg.lenses.forEach((L, k) => { S.missStreak[L] = R[k] ? 0 : (S.missStreak[L] || 0) + 1; });

  // 4) 出口（按序取第一个成立的）
  const closable = gate.reviewable && rec.missingLenses.length === 0 && gate.sigOk;   // 签名对不上的轮不能收尾
  const vals = Object.values(sg);
  const confirmedX = confirmedOpen.filter(i => i.needsDecision !== 'agreed');
  const agreedOpen = S.issues.filter(i => i.status === 'open' && i.needsDecision === 'agreed');
  const unmetIds = Object.keys(sg).filter(id => sg[id] === 'unmet');
  let exit = null, detail = null;
  if (closable && !confirmedOpen.length && !unverifOpen.length && vals.every(v => v === 'met')) exit = 'converged';
  else if (closable && !confirmedOpen.length && !vals.some(v => v === 'unmet' || v === 'pending')) exit = 'evidence-gap';
  else if (closable && cfg.mode === 'prototype' && !confirmedX.length && agreedOpen.length && !vals.includes('pending')
    && unmetIds.every(id => agreedOpen.some(i => i.subgoal === id))) exit = 'decision-gap';
  else if (res && !res.envOk) { exit = 'blocked'; detail = 'url 不可达，服务没在跑'; }
  else if (res && res.smoke.envBroken) { exit = 'blocked'; detail = '退回本轮改动后 smoke 仍红：环境或基线坏了；本轮改动已放回'; }
  else if (res && res.smoke.pass === false && !res.smoke.rolledBack) { exit = 'blocked'; detail = 'smoke 红且无法退回（快照不可用），工作区停在本轮改动后的状态'; }
  else if (S.skipStreak >= 2) { exit = 'blocked'; detail = '连续两轮没能评审：' + S.rounds.slice(-2).map(r => `${rtag(r.round)} ${r.skipReason}`).join('；'); }
  else if (cfg.lenses.some(L => S.missStreak[L] >= 2)) { exit = 'blocked'; detail = cfg.lenses.filter(L => S.missStreak[L] >= 2).map(L => `角度 ${L} 连续两轮没交回`).join('；'); }
  else if (S.streak >= cfg.staleRounds) {
    exit = 'stalled';
    detail = `连续 ${S.streak} 轮没有进展。开着的确证 must：${confirmedOpen.map(i => i.id).join('、') || '无'}；未达成的子项：${Object.keys(sg).filter(id => sg[id] !== 'met').join('、') || '无'}`;
  }
  if (exit) markExit(S, exit, detail);

  // 5) 收尾
  S.round = round;
  Object.assign(rec, { openConfirmed: confirmedOpen.length, openUnverifiable: unverifOpen.length, met, sg, progress, streak: S.streak });
}

function markExit(S, reason, detail) { S.exit = reason; S.exitDetail = detail ?? null; }

/** verify 的 effort：data 档且刷新方式是说明文件时要照文件操作，用 medium；其余 low */
function verifyEffort(cfg, S) {
  const rec = S.rounds[S.rounds.length - 1];
  return (rec ? rec.kind : S.lastKind) === 'data' && mdRefresh(cfg) ? 'medium' : 'low';
}
const mdRefresh = cfg => isStr(cfg.refreshDataCmd) && /\.md$/i.test(cfg.refreshDataCmd.trim());

/** 每轮一行紧凑记录（log 用，运行记录的 logs 会完整保留） */
function roundLine(S) {
  const r = S.rounds[S.rounds.length - 1];
  if (!r) return '';
  const total = Object.keys(S.subgoals).length;
  const shots = r.capture ? `${r.capture.ok.length}/${r.capture.ok.length + r.capture.failed.length}` : '-';
  return `${rtag(r.round)} kind=${r.kind}${r.kindAdjusted ? '→' + r.kindAdjusted : ''} smoke=${smokeWord(r)} shots=${shots} sig=${r.sigOk ? 'ok' : 'bad'}` +
    ` reviewed=${r.reviewed ? 'Y' : 'N(' + r.skipReason + ')'} fixed=[${r.fixed.join(',')}] born=[${r.born.join(',')}] reopened=[${r.reopened.join(',')}]` +
    ` openMust=${r.openConfirmed}${r.openUnverifiable ? '+' + r.openUnverifiable + '待取证' : ''} met=${r.met.length}/${total} streak=${r.streak}${S.exit ? ' exit=' + S.exit : ''}`;
}
function smokeWord(r) {
  const s = r.smoke;
  if (!s) return '-';
  if (s.pass === true) return s.flaky ? 'flaky' : 'pass';
  if (s.rolledBack) return 'rolledBack';
  if (s.envBroken) return 'envBroken';
  return s.pass === false ? 'fail' : '-';
}

/** 顶层 return 的精简台账：journal 读不到时的兜底与即时概览 */
function compactLedger(S) {
  const last = [...S.rounds].reverse().find(r => r.reviewed);
  return { round: S.round, exit: S.exit,
    issues: S.issues.map(i => ({ id: i.id, lens: i.lens, severity: i.severity, status: i.status, unverifiable: i.unverifiable, title: i.title, state: i.state, needsDecision: i.needsDecision })),
    subgoals: last ? last.sg : {}, directions: S.directions.map(d => `${d.id} ${d.title}`),
    rounds: S.rounds.map(r => `${rtag(r.round)} kind=${r.kind} smoke=${smokeWord(r)} reviewed=${r.reviewed ? 'Y' : 'N'} fixed=${r.fixed.length} born=${r.born.length} openMust=${r.openConfirmed} met=${r.met.length} streak=${r.streak}`) };
}

function finalReturn(cfg, S, used) {
  const out = { exitReason: S.exit, exitDetail: S.exitDetail, rounds: S.round, runFirstRound: S.runFirstRound, agentsUsed: used,
    workdir: cfg.workdir, next: `node ${q(cfg.skill + '/wl.mjs')} export ${q(cfg.W)}`, ledger: compactLedger(S) };
  if (cfg.debug === true) out.state = S;
  return out;
}

// ── prompt ──
const issueHead = i => `- ${i.id} [${i.lens}] ${i.title}${i.state ? `（态 ${i.state}）` : ''}${i.subgoal ? `（子项 ${i.subgoal}）` : ''}${i.regressions ? `（回归 ${i.regressions} 次）` : ''}`;
const issueOneLine = i => `- ${i.id} [${i.lens}] ${clip(i.title, 80)}${i.state ? `（态 ${i.state}）` : ''}`;
function issueFull(i, dLen, eLen) {
  const out = [issueHead(i)];
  if (i.detail) out.push(`  detail：${indent(clip(i.detail, dLen))}`);
  if (i.evidence) out.push(`  evidence：${indent(clip(i.evidence, eLen))}`);
  if ((i.files || []).length) out.push(`  files：${i.files.join('、')}`);
  if (i.unverifiable) out.push(`  取证缺口：需要态 ${(i.requiredStates || []).join('、') || '（未点名）'}`);
  return out.join('\n');
}
function proposalText(p) {
  if (!p) return '';
  const opts = (p.options || []).map(o => `${o.choice}（代价：${o.cost}）`).join(' / ');
  return `implementer 提议挂起，交用户拍板：${p.title}；选项：${opts || '（未写）'}；推荐：${p.recommend || '（未写）'}${p.why ? '；理由：' + p.why : ''}`;
}
function byStateGroups(list) {
  const groups = new Map();
  for (const i of list) { const k = i.state || '（未指定态）'; if (!groups.has(k)) groups.set(k, []); groups.get(k).push(i); }
  return groups;
}
function refsBlock(cfg, how) {
  const refs = cfg.refImages.filter(isObj);
  if (!refs.length) return '（无参考图）';
  if (!how) return '（本角度不读参考图）';
  return [how, 'role=goal 是目标态，要靠近；role=baseline 是改进前现状，只用来对比有没有前进，不是目标；role=anti-example 是负例，要远离。',
    ...refs.map(r => `- ${absIn(cfg.root, r.path)} · role=${r.role || '?'}${r.description ? ' · ' + r.description : ''}` +
      (strs(r.relatedSubgoals).length ? ` · 子项 ${r.relatedSubgoals.join('、')}` : '') + (r.relatedState ? ` · 态 ${r.relatedState}` : ''))].join('\n');
}
function latestByLens(g) {
  return Object.entries(g.byLens || {}).map(([L, b]) => `${L}=${b.status}（${rtag(b.round)}${b.evidence ? '：' + clip(b.evidence, 200) : ''}）`).join('；');
}

function implPrompt(cfg, S, round) {
  const P = paths(cfg, round), proto = cfg.mode === 'prototype';
  const open = S.issues.filter(i => i.status === 'open');
  const must = open.filter(i => i.severity === 'must' && !i.unverifiable && i.needsDecision !== 'agreed')
    .sort((a, b) => (b.lens === 'workflow') - (a.lens === 'workflow'));
  const out = [`你是 web-loop 第 ${round} 轮的 implementer：改进一个正在运行的 web 应用，改的是已有代码。`];
  out.push(`【第一步】跑 \`${P.wl} intake ${q(P.W)} --done ${q(S.doneControl.join(','))}\`，读主会话中途放的纠错文件。` +
    'hint 是人工指示，优先级最高，遵循后把它的 key 填进 hintsRead；overrides 原样填进返回值的 overrides（key 不变）。' +
    '输出里 verifyRunning 不为 null 时，上一轮的 verify 还在改工作区：再跑一次 intake 等它结束，不要先动代码。');
  out.push(`【GOAL（原文）】\n${cfg.goal}`);
  out.push('【子项】\n' + cfg.goalSubgoals.map(g => `- ${g.id} · ${g.desc} · 负责：${g.lenses.join('、')}` +
    (g.states.length ? ` · 态：${g.states.join('、')}` : '') + (g.measurable ? ` · 可度量：${g.measurable}` : '') +
    ` · 最近评审：${latestByLens(S.subgoals[g.id]) || '（还没有）'}`).join('\n'));
  out.push('【参考图】' + refsBlock(cfg, '按需读图对照。'));
  const mustLines = [];
  const rb = must.some(i => i.id === 'wf-regress') ? [...S.rounds].reverse().find(r => r.smoke && r.smoke.rolledBack) : null;
  if (rb) { const Q = paths(cfg, rb.round); mustLines.push(`（${rtag(rb.round)} 的改动被退回了：先读被退回的改动 ${Q.rejected} 和 ${Q.verifyJson} 里的 smoke 输出末尾，弄清 smoke 为什么红，再决定怎么重做）`); }
  for (const [st, list] of byStateGroups(must)) {
    mustLines.push(`▸ ${st}`);
    for (const i of list) {
      let s = issueFull(i, 800, 400);
      if (i.needsDecision === 'proposed') s += '\n  （你提议过挂起，负责评审还没同意，仍要处理）';
      const at = (i.attempts || []).slice(-3);
      if (at.length) s += `\n  已试过：${at.map(a => `${rtag(a.round)} ${clip(a.approach, 200)}`).join('；')}。上轮评审仍判存在。`;
      mustLines.push(s);
    }
  }
  out.push('【必须处理】' + (mustLines.length ? '\n' + mustLines.join('\n') : '无'));
  const gaps = open.filter(i => i.severity === 'must' && i.unverifiable);
  out.push('【待人工取证（不用改，列出供参考）】' + (gaps.length ? '\n' + gaps.map(i => `- ${i.id} ${i.title}（需要态 ${i.requiredStates.join('、')}）`).join('\n') : '无'));
  out.push('【方向题（等用户决定，不要自行实现）】' + (S.directions.length ? '\n' + S.directions.map(d => `- ${d.title}`).join('\n') : '无'));
  if (proto) {
    const agreed = open.filter(i => i.needsDecision === 'agreed');
    out.push('【等你拍板（负责评审已同意挂起，不要动）】' + (agreed.length ? '\n' + agreed.map(i => `- ${i.id} ${i.title}`).join('\n') : '无'));
  }
  const nice = open.filter(i => i.severity === 'nice');
  out.push('【可选（nice）】' + (nice.length ? '\n' + nice.slice(0, 20).map(i => `- ${i.id} ${clip(i.title, 80)}`).join('\n') + (nice.length > 20 ? `\n（另有 ${nice.length - 20} 条未列）` : '') : '无'));
  const recent = S.issues.filter(i => i.status === 'fixed' && i.fixedRound != null && i.fixedRound >= round - 2);
  out.push('【最近两轮修好的（不要改回去）】' + (recent.length ? '\n' + recent.map(i => `- ${i.id} ${clip(i.title, 80)}`).join('\n') : '无'));
  const kinds = ['`frontend`（只改了前端，或改动不用重启就生效）'];
  if (cfg.restartCmd) kinds.push('`backend`（改了后端，要重启）');
  if (cfg.refreshDataCmd) kinds.push('`data`（改了数据或扫描逻辑，要重启并刷新数据）');
  kinds.push('`none`（本轮没改代码）');
  out.push(['【规则】',
    '- 先读相关代码，确认现状，再动手。',
    '- 试过、评审仍判存在的做法不要原样重试；要重试就在 summary 里写明这次有什么不同。每条处理过的 must 在 attempts 里写一句这次的做法。',
    '- 不改截图配方文件、验收标准和运行目录里的参数文件；配方有问题写进 toMain。',
    `- kind 按实际改动填，本 run 只支持：${kinds.join('、')}。`].join('\n'));
  if (proto) {
    out.push(['【原型模式：方案层与界面层】',
      `- 方案层 = 这些方案文件里的字段与计算：${cfg.schemeFiles.map(f => absIn(cfg.root, f)).join('、')}；以及 rubric「术语表」里的词：${cfg.terms.join('、') || '（无）'}。`,
      '- 方案层的 must，如果 rubric「已定决定」里没有现成答案，不要改，写进返回值的 deferred 挂起：写清选项、各自代价和推荐。挂起要等该条目的负责评审同意才生效，在那之前它仍算必须处理。',
      '- 界面层（其余一切）照常改。',
      `- 补充演示数据或改动方案文件时，同一轮里同步更新后端要求清单 ${absIn(cfg.root, cfg.contractPath)}，每个新字段都要写进去。`,
      '- 负责评审没同意（判仍存在）的挂起提议，照常修。'].join('\n'));
  }
  out.push(`【自查】要看效果就用 \`${P.cap} shoot --workdir ${q(P.W)} --round ${round} --only <态,…> --out ${q(P.W + '/scratch/impl-' + rtag(round))}\`，不要自己写截图脚本。自查截图不作为评审证据。`);
  out.push(`【标准】验收标准（本 run 冻结）：${P.rubric}；评审准则：${P.principles}。`);
  out.push(COMMON);
  return out.join('\n\n');
}

function verifyPrompt(cfg, S, round) {
  const P = paths(cfg, round), rec = curRec(S, round), kind = rec ? rec.kind : S.lastKind;
  const prev = S.rounds.find(r => r.round === round - 1);
  // 只有上一轮评审过、本轮又没应用 override 时，「无改动」才能直接沿用上一轮的评审结论
  const hint = !!(prev && prev.reviewed) && !(rec && rec.overridesApplied.length);
  const md = kind === 'data' && mdRefresh(cfg);
  const cmd = `${P.wl} verify ${q(P.W)} --round ${round} --kind ${kind}${hint ? ' --no-change-hint' : ''}${md ? ' --refreshed' : ''}`;
  const out = [`你是 web-loop 第 ${round} 轮的 verify：只负责跑一条命令并把结果原样转交。`];
  if (md) out.push(`【先刷新数据】本轮改动涉及数据：先按 ${absIn(cfg.root, cfg.refreshDataCmd)} 的说明把数据刷新做完（这一步可以多调几次工具），再跑下面的命令。`);
  out.push(`【命令】（Bash 的 timeout 必须设为 600000）\n${cmd}`);
  out.push('它会依次做快照、smoke、刷新、截图，最后一行打印一段 JSON。返回值的 result 是一个字符串：填带 sig 的那一行文本本身，不改动任何字符（含 sig），不要把它改写成对象，也不要再包一层字段。' +
    `最后一行是 {"pending":true,…} 时说明还没跑完（活由后台进程在做）：再跑 \`${P.wl} wait ${q(P.W)} --round ${round}\`（timeout 同样设 600000），直到拿到带 sig 的那行；拿到之前不要交回。` +
    '最后一行带 error 字段、或命令异常退出时，result 填 null，把 error 或输出末尾几行写进 note。不要读截图，不要做别的检查，不要修任何东西。');
  out.push(COMMON);
  return out.join('\n\n');
}

/** 角色说明：内置角度压成几行；其余角度完全按 rubric 专节判 */
function lensBrief(cfg, L, P) {
  const noClick = '你不能点击，只能把截图清单里排好顺序的状态当作一次连贯操作来判；专节没排出来的步骤，记 unverifiable，requiredStates 写缺的那个态。';
  const b = {
    ux: '界面评审：看截图评视觉、布局、层级、可见性（列挤压、侧栏被撑没、重叠、截断、对齐）。优先看数据最密集、渲染最复杂的态。读全部成功态的整页图，局部图按需读。',
    func: '功能评审：首要是逐条复核你负责的子项（需求满足度），其次读 manifest 里的报错文本与探针结果，结合截图判功能是否正确。读自己子项的态、自己名下条目所在的态、manifest 里有报错的态，其余按需。',
    code: '代码评审：读本轮 diff（命令见证据段），评 bug、违反 rubric 红线、回归风险。默认不读图，读 diff 和 manifest 里的报错文本，需要时才看截图。可在 issues 的 files 写问题所在的 path:line，不写修法。',
    rival: '第二位独立复核员：与其他评审用同一份标准，独立判一遍；专找最容易被放过的违反：同一个词在两处意思不同、同一个标签来自两个来源、规则随阶段或页面变、看图一眼会读错的地方。读全部成功态的整页图。',
    razor: '剃刀：对截图里每个界面元素（列、签、按钮、计数、颜色）问 rubric 列的哪个用户任务需要它，答不出 = must（写明它是什么、在哪张截图）。再按 rubric 的数法数本轮的概念数、要记的规则数、屏上固定词数，任一项高于起点 = must（写出本轮数与起点）。只指出多出来的东西，不设计替代方案。读全部成功态的整页图。',
    newbie: '新手第一眼：你几周没碰这个工具、记不清内部词、色弱、不看悬停。先只看截图，心里记下每个签、列、颜色你以为是什么意思、下一步会点哪；再读 rubric 的术语与正确含义逐条对照：读错、读不出、会让你点错下一步 = must（写明读成了什么、正确是什么、哪张截图）。' +
      '同一概念在两处有两种叫法，或同一个词在两处意思不同，也记 must。读对的不立条目。读全部成功态的整页图。',
    flow: `模拟用户走流程：按 ${P.rubric} 里「角度 flow」专节列出的状态顺序，把截图当成一次连贯操作来判：每一步下一步该做什么是否看得出、前后状态是否衔接、走完能不能完成专节写的任务。${noClick}`,
    contract: `后端要求一致性：读后端要求清单 ${absIn(cfg.root, cfg.contractPath)}、方案文件 ${cfg.schemeFiles.map(f => absIn(cfg.root, f)).join('、')}，以及本轮 diff（命令见证据段）。must 只有三类：` +
      '① 本轮改了方案文件，清单没跟上；② 清单里有、代码里没有，或代码里有、清单里没有的字段或计算；③ 本轮改变了方案层的含义或计算，而这项改动不在 rubric「已定决定」里。' +
      '「后端可能拿不到」「这样算是否合理」一律写进 directions，不记 must。',
  }[L];
  return b || `你是『${L}』评审角度。看哪些状态、判什么、什么算 must，完全按 ${P.rubric} 里『角度 ${L}』专节；专节要你按顺序看一串状态时，就按截图清单里的顺序把它们当作一次连贯的操作流程来判，你自己不能点击。`;
}
const REFS_HOW = { ux: '先读全部参考图，按 role 区分对待。', rival: '先读全部参考图，按 role 区分对待。', func: '看说明即可，对照子项时按需读图。', flow: '看说明即可，需要时读图。' };

function reviewerPrompt(cfg, S, round, L, verify) {
  const P = paths(cfg, round), gate = reviewGate(verify, round), rec = curRec(S, round);
  const newbie = L === 'newbie', seesDiff = L === 'code' || L === 'contract';
  const issues = S.issues || [];
  const own = issues.filter(i => i.status === 'open' && i.lens === L);
  const mySg = cfg.goalSubgoals.filter(g => g.lenses.includes(L));
  const out = [`你是 web-loop 第 ${round} 轮的评审，角度：${L}。`, lensBrief(cfg, L, P)];
  out.push('【取证方式】你零浏览器、只读：只 Read 截图器已截好的图和文件，不碰 playwright，不创建任何文件。一次并行 Read 多张图。' +
    '看不清就读 manifest 里该态的局部图（crops 字段）；局部图也不够时记 unverifiable，requiredStates 写「<态>__需要局部图」。');
  out.push(`【GOAL（原文）】\n${cfg.goal}`);
  out.push('【你负责的子项】' + (mySg.length ? '在 subgoals 里逐条给出本轮结论（met / unmet / unverifiable）：\n' + mySg.map(g => `- ${g.id} · ${g.desc}` +
    (g.measurable ? ` · 可度量：${g.measurable}` : '') + (g.states.length ? ` · 态：${g.states.join('、')}` : '')).join('\n') : '本角度不负责子项，subgoals 交空数组。'));
  out.push('【参考图】' + refsBlock(cfg, REFS_HOW[L] || (BUILTIN_LENSES.includes(L) ? null : '按专节需要读图。')));
  const ev = [`- 本轮截图清单：${P.manifest}（整页图、局部图、探针结果、报错都在里面；只看 ok 为 true 的态）`,
    `- 开跑前起点：${P.r00}（开跑前就有的报错不算本次的问题）`];
  if (seesDiff) {
    const filt = L === 'contract' ? ' -- ' + [...cfg.schemeFiles, cfg.contractPath].filter(Boolean).map(q).join(' ') : '';
    ev.push(`- 本轮代码改动：\`${P.wl} diff ${q(P.W)} --round ${round}${filt}\`（可加 -- <路径> 过滤）`);
  }
  if (L === 'code' && rec) ev.push(`- implementer 自述（只给代码角度）：${indent(clip(rec.implSummary || '（未交回）', 1500))}\n- 改动文件：${(rec.changedFiles || []).join('、') || '（未列）'}`);
  if (gate.sigOk && gate.res && gate.res.capture && gate.res.capture.failedStates.length)
    ev.push(`- 本轮截图失败的态（这些态没有截图，不要猜；原因见清单里该态的 error）：${gate.res.capture.failedStates.join('、')}`);
  else if (!gate.sigOk) ev.push('- 本轮各态截没截成功，以清单里各态的 ok 字段为准。');
  out.push('【证据】\n' + ev.join('\n'));
  out.push('【你名下待复核的问题】' + (own.length
    ? '必须逐条在 known 里按 id 表态：present（仍存在）/ gone（已修好）/ unverifiable（本轮证据判不了，requiredStates 写需要哪个态）' +
      (own.some(i => i.needsDecision) ? ' / decision（同意这条要用户拍板）' : '') + '。\n' +
      own.map(i => {
        let s = issueFull(i, 400, 300);
        if (i.needsDecision === 'proposed') s += `\n  ${proposalText(i.proposal)}\n  同意它要用户拍板就回 decision，不同意就照常回 present。`;
        if (i.needsDecision === 'agreed') s += '\n  已同意挂起、等用户拍板：仍存在回 decision 或 present，修好了回 gone。';
        if (i.reopenedBy) s += `\n  （由角度 ${i.reopenedBy} 重开，请复核）`;
        return s;
      }).join('\n')
    : '无，known 交空数组。'));
  if (!newbie) {
    const others = issues.filter(i => i.status === 'open' && i.lens !== L);
    const fixed = issues.filter(i => i.status === 'fixed').sort((a, b) => (b.fixedRound || 0) - (a.fixedRound || 0));
    out.push('【其他角度开着的问题】（同一件事用 matchesIssueId 引用，不另立，也不替它表态）' + (others.length ? '\n' + others.map(issueOneLine).join('\n') : '无'));
    out.push('【已修好的问题】（复现了就用 matchesIssueId 引用它来报）' + (fixed.length ? '\n' + fixed.slice(0, 40).map(i => `- ${i.id} ${clip(i.title, 60)}`).join('\n') +
      (fixed.length > 40 ? `\n（另有 ${fixed.length - 40} 条更早修好的未列）` : '') : '无'));
    out.push('【已有方向题（不要重复提）】' + ((S.directions || []).length ? '\n' + S.directions.map(d => `- ${clip(d.title, 80)}`).join('\n') : '无'));
  }
  out.push(['【判法】',
    `- 绝对标准：对照冻结的验收标准判 pass/fail，不因「有更好做法」判不过；must 挡收敛（违反标准或 GOAL、bug、页面报错），nice 不挡（定义见 ${P.principles} 的 §0）。超出范围的不当 must。不提替代方案。正面结论不写进 issues。`,
    '- 子项的 evidence 必须是本轮可以定位的证据：截图文件名加看到了什么、探针的键和值、报错原文、diff 里的文件和函数。',
    '- 根因在截图配方或缺少某个状态的问题，一律 unverifiable:true，并在 requiredStates 写出需要哪个态（可以是清单里还没有的新态名）。点名的态如果本轮已经截成功，会被按确证问题处理。',
    '- 复现已修好的问题用 matchesIssueId 引用它，不要换个说法另立一条。',
    '- 需要用户拍板的取舍写进 directions（写明选项、各自代价、推荐），不进 issues。',
    '- issues 的 state 写问题所在的态；detail 不超过 6 行，evidence 不超过 3 行。'].join('\n'));
  if (L === 'razor') {
    const base = S.baselineCounts && S.baselineCounts.razor;
    out.push('【计数】每轮都要在 counts.now 里按 rubric 的数法填本轮计数，并和起点对照。' +
      (base ? `起点计数：${JSON.stringify(base)}。` : `本 run 还没有起点计数：先按同一数法数 r00 起点图（见 ${P.r00}），填进 counts.baseline。`));
  }
  out.push(newbie
    ? `【标准】先看截图、记下第一眼读法，再 Read ${P.rubric}（本 run 冻结的验收标准）对照正确含义；评审准则见 ${P.principles}。标准在本 run 内冻结，有异议写进 toMain 或 directions，不要自行放宽或加码。`
    : `【标准】第一步 Read ${P.rubric}（本 run 冻结的验收标准）；评审准则见 ${P.principles}。标准在本 run 内冻结，有异议写进 toMain 或 directions，不要自行放宽或加码。`);
  out.push(COMMON);
  return out.join('\n\n');
}

// ── 回放（wl.mjs status / export 用）──
/**
 * 按 SHELL 同样的顺序重放 journal 里的结果。view = { results: {label: result}, started: [按开始顺序的 label] }；
 * mode = 'live'（进行中：停在未完成的环节并报告阶段）| 'end'（已结束：缺结果视为 null）。
 * end 模式下某轮 verify 从没开始过，说明 run 在 implementer 阶段被打断（SHELL 那时也不会归并这一轮），就此停下。
 */
function replay(cfg, seed, view, mode) {
  const S = initState(cfg, seed);
  const R = isObj(view) && isObj(view.results) ? view.results : {};
  const started = new Set(isObj(view) && Array.isArray(view.started) ? view.started : []);
  const has = l => Object.prototype.hasOwnProperty.call(R, l);
  const live = mode === 'live';
  let stage = null, n = 0;
  while (!S.exit && n < cfg.maxRounds) {
    const round = S.round + 1, rt = rtag(round);
    const li = `impl-${rt}`, lv = `verify-${rt}`, lr = cfg.lenses.map(L => `review-${L}-${rt}`);
    if (!started.has(li) && !started.has(lv)) { if (live && n) stage = `${rt} 即将开始`; break; }
    if (!started.has(lv)) { if (live) stage = has(li) ? `${rt} verify 即将开始` : `${rt} implementer 进行中`; break; }
    if (live && !has(lv)) { stage = `${rt} verify 进行中`; break; }
    const verify = has(lv) ? R[lv] : null;
    const gate = reviewGate(verify, round);
    let reviews = null;
    if (gate.reviewable) {
      const done = lr.filter(has), later = started.has(`impl-${rtag(round + 1)}`);
      if (live && !later && done.length < lr.length) {
        stage = `${rt} 评审中：${done.length ? done.map(l => l.replace(/^review-|-r\d+$/g, '')).join('、') + ' 已交回' : '还没有角度交回'}`;
        break;
      }
      reviews = lr.map(l => (has(l) ? R[l] : null));
    }
    applyImpl(cfg, S, round, has(li) ? R[li] : null);
    reduceRound(cfg, S, round, verify, reviews);
    n++;
  }
  if (!live && !S.exit) {
    if (n >= cfg.maxRounds) markExit(S, 'max-rounds', null);
    else if (cfg.maxAgents != null && started.size + roundAgentEstimate(cfg) > cfg.maxAgents) markExit(S, 'budget', budgetDetail(cfg, started.size));
    else markExit(S, 'interrupted', '回放没有找到出口：运行时预算、错误或被手动停止，请看 Workflow 的返回值');
  }
  return { S, stage: S.exit ? null : stage, agentsUsed: started.size, exitReason: S.exit };
}

// ── SUMMARY（wl.mjs export 写盘；内容一字不差来自台账）──
/**
 * info（wl.mjs 从文件算好传入，都可缺省）：{ runId, agentsUsed, changed: [{status, path}], journalNote }
 */
function renderSummary(cfg, S, info) {
  info = info || {};
  const W = cfg.W, wl = `node ${q(cfg.skill + '/wl.mjs')}`, exit = S.exit || 'interrupted';
  const last = S.rounds[S.rounds.length - 1] || null;
  const lastRev = [...S.rounds].reverse().find(r => r.reviewed) || null;
  const lastCap = [...S.rounds].reverse().find(r => r.capture) || null;
  const open = S.issues.filter(i => i.status === 'open');
  const confirmed = open.filter(i => i.severity === 'must' && !i.unverifiable);
  const gaps = open.filter(i => i.severity === 'must' && i.unverifiable);
  const restoreCmd = `${wl} restore ${q(W)} --to green --dry-run`;
  const sgOf = id => (lastRev ? lastRev.sg[id] || 'pending' : 'pending');
  const out = [];
  const sec = (title, lines) => { out.push('', `## ${title}`, '', ...(lines.length ? lines : ['（无）'])); };

  out.push(`# web-loop 运行总结：${cfg.runtag}`, '');
  out.push(`- 结论：${EXIT_TEXT[exit] || exit}（\`${exit}\`）${S.exitDetail ? '。' + S.exitDetail : ''}`);
  out.push(`- 轮次：${rtag(S.runFirstRound)}～${rtag(S.round)}（本 run ${Math.max(0, S.round - S.runFirstRound + 1)} 轮，上限 ${cfg.maxRounds}）；代理数：${info.agentsUsed ?? '未知'}；模式：${cfg.mode}；评审角度：${cfg.lenses.join('、')}`);
  if (info.runId) out.push(`- runId：${info.runId}`);
  if (info.journalNote) out.push(`- 注意：${info.journalNote}`);

  // 需要你做的事
  const todo = [];
  const lastSmoke = !last || !last.smoke ? '未跑' : last.smoke.pass === true ? '绿' : last.smoke.rolledBack ? '红（本轮改动已退回，工作区回到退回后的绿状态）' : last.smoke.pass === false ? '红' : '未跑';
  todo.push(`- 工作区：最后一轮 smoke 是${lastSmoke}；最近一次绿是 ${rtag(S.lastGreenRound)}${S.lastGreenRound === 0 ? '（开跑前）' : ''}。`);
  if (!['converged', 'evidence-gap'].includes(exit) || !(last && last.smoke && last.smoke.pass === true))
    todo.push(`- 要退回到最近一次绿：先跑 \`${restoreCmd}\` 看要动哪些路径，确认后去掉 --dry-run。`);
  if (exit === 'converged') todo.push('- 没有阻塞项：全部子项达成，没有开着的 must。');
  if (exit === 'evidence-gap') {
    for (const i of gaps) todo.push(`- 补证据：${i.id} ${i.title}，需要态 ${i.requiredStates.join('、') || '（未点名）'}`);
    for (const g of cfg.goalSubgoals) if (sgOf(g.id) === 'unverifiable')
      todo.push(`- 补证据：子项 ${g.id}，需要态 ${uniq(Object.values(S.subgoals[g.id].byLens).flatMap(b => b.requiredStates || [])).join('、') || '（未点名）'}`);
  }
  if (exit === 'decision-gap') for (const i of open.filter(x => x.needsDecision === 'agreed')) {
    const d = S.directions.find(x => x.id === i.decisionId);
    todo.push(`- 等你拍板：${i.id} ${i.title} ↔ 方向题 ${i.decisionId}${d ? '「' + d.title + '」' : ''}`);
  }
  if (exit === 'stalled') for (const i of confirmed)
    todo.push(`- 卡住：${i.id} [${i.lens}] ${i.title}${i.attempts.length ? '；试过：' + i.attempts.map(a => `${rtag(a.round)} ${clip(a.approach, 120)}`).join('；') : ''}`);
  if (exit === 'blocked' || exit === 'error' || exit === 'interrupted') todo.push(`- 原因：${S.exitDetail || '（无）'}`);
  if (S.directions.length) todo.push(`- 方向题 ${S.directions.length} 个，全文见下方「方向题」。`);
  sec('需要你做的事', todo);

  sec('子项', cfg.goalSubgoals.length ? ['| 子项 | 负责角度 | 状态 | 最近证据 |', '|---|---|---|---|',
    ...cfg.goalSubgoals.map(g => `| ${g.id} ${clip(g.desc, 60).replace(/\|/g, '/')} | ${g.lenses.join('、')} | ${sgOf(g.id)} | ${clip(latestByLens(S.subgoals[g.id]), 300).replace(/\|/g, '/').replace(/\n/g, ' ')} |`)] : []);

  const grouped = [];
  for (const [st, list] of byStateGroups(confirmed)) { grouped.push(`**${st}**`, ''); for (const i of list) grouped.push(issueFull(i, 600, 300) + (i.needsDecision ? `\n  （${i.needsDecision === 'agreed' ? '已同意挂起，等你拍板' : '提议挂起，待负责角度表态'}）` : '')); grouped.push(''); }
  sec('还开着的确证问题', grouped);
  sec('待人工取证', gaps.map(i => `- ${i.id} [${i.lens}] ${i.title}：需要态 ${i.requiredStates.join('、') || '（未点名）'}${i.humanUnverifiable ? '（人工标注）' : ''}`));
  sec('方向题', S.directions.flatMap(d => [`### ${d.id}：${d.title}`, `- 提出：${d.lens}（${rtag(d.round)}）${d.alsoBy.length ? '；也提到的角度：' + d.alsoBy.join('、') : ''}${d.issueId ? '；对应条目 ' + d.issueId : ''}`,
    ...d.options.map(o => `- 选项「${o.choice}」：${o.cost}`), `- 推荐：${d.recommend || '（未写）'}${d.why ? '。理由：' + d.why : ''}`, '']));
  sec('可选改进', open.filter(i => i.severity === 'nice').map(i => `- ${i.id} [${i.lens}] ${i.title}${i.state ? `（态 ${i.state}）` : ''}`));
  sec('评审分歧', S.issues.filter(i => i.dissent.length || i.disputed || i.alsoReportedBy.length).map(i =>
    `- ${i.id} [${i.lens}] ${i.title}：${i.disputed ? '负责角度判修好后又被别的角度重开过；' : ''}${i.dissent.map(d => `${rtag(d.round)} ${d.lens} 不同意（${clip(d.evidence, 120)}）`).join('；')}${i.alsoReportedBy.length ? '；也报告的角度：' + i.alsoReportedBy.join('、') : ''}`));
  sec('每轮走势', ['| 轮 | kind | smoke | 截图 | 评审 | 修好 | 新增 | 重开 | 开着的确证 must | 子项达成 | streak |', '|---|---|---|---|---|---|---|---|---|---|---|',
    ...S.rounds.map(r => `| ${rtag(r.round)} | ${r.kind}${r.kindAdjusted ? '→' + r.kindAdjusted : ''} | ${smokeWord(r)} | ${r.capture ? `${r.capture.ok.length}/${r.capture.ok.length + r.capture.failed.length}` : '-'} | ${r.reviewed ? '是' + (r.sigOk ? '' : '（签名不符）') : '否：' + r.skipReason} | ${r.fixed.join(' ') || '-'} | ${r.born.join(' ') || '-'} | ${r.reopened.join(' ') || '-'} | ${r.openConfirmed}${r.openUnverifiable ? `（另 ${r.openUnverifiable} 待取证）` : ''} | ${r.met.length}/${cfg.goalSubgoals.length} | ${r.streak} |`)]);
  sec('本 run 改动的文件', Array.isArray(info.changed) ? info.changed.map(c => `- ${c.status} ${c.path}`) : ['（快照不可用，没有列出）']);
  sec('给主会话的留言', S.toMain.map(m => `- ${rtag(m.round)} ${m.from}：${m.text}`));
  const fixes = [];
  for (const e of S.overrideErrors) fixes.push(`- override 无效（${rtag(e.round)} ${e.key}）：${e.error}`);
  for (const r of S.rounds) {
    const t = rtag(r.round), add = (name, v) => { if (v && (Array.isArray(v) ? v.length : Object.keys(v).length)) fixes.push(`- ${t} ${name}：${Array.isArray(v) ? v.map(x => (isObj(x) ? JSON.stringify(x) : x)).join('、') : JSON.stringify(v)}`); };
    add('引用了不存在的 id（按新条目入账）', r.badMatch); add('名下条目没表态', r.untabled); add('负责子项没表态', r.untabledSubgoals);
    add('取证缺口不采信（点名的态已截成功）', r.unverifiableRejected); add('判修好但所在态没截成功（未生效）', r.goneIgnored);
    add('判达成但子项的态都没截成功（降为待取证）', r.metDowngraded); add('返回形状不对（按缺席处理）', r.malformed);
    add('挂起不生效', r.deferRejected); add('角度缺席', r.missingLenses);
    if (r.kindAdjusted) fixes.push(`- ${t} 档位按实际改动调整为 ${r.kindAdjusted}`);
    if (r.verifyNote) fixes.push(`- ${t} verify 备注：${r.verifyNote}`);
  }
  sec('台账修正与异常', fixes);
  const shots = [];
  if (lastCap) {
    const lt = rtag(lastCap.round);
    for (const s of lastCap.capture.ok) shots.push(`- ${s}：${W}/shots/r00_${s}.png → ${W}/shots/${lt}_${s}.png`);
    for (const s of lastCap.capture.failed) shots.push(`- ${s}：${W}/shots/r00_${s}.png → ${W}/shots/${lt}_${s}.failed.png（截图失败）`);
  }
  sec('截图对照', shots);
  if (cfg.mode === 'prototype') {
    const touched = S.rounds.filter(r => r.schemeTouched.length).map(r => `- ${rtag(r.round)} 动过方案文件：${r.schemeTouched.join('、')}`);
    const deferred = S.issues.filter(i => i.needsDecision).map(i => `- ${i.id} ${i.title}：${i.needsDecision === 'agreed' ? '已同意挂起 ↔ ' + i.decisionId : '提议挂起，未获同意'}`);
    sec('原型产出', [`- 后端要求清单：${absIn(cfg.root, cfg.contractPath)}`, `- 本 run 对清单的改动：\`${wl} diff ${q(W)} --run -- ${q(cfg.contractPath)}\``,
      '- 方案受影响的地方（方案文档本身由主会话经用户同意后再改）：', ...(touched.length || deferred.length ? [...touched, ...deferred] : ['  （无）'])]);
  }
  sec('怎么续跑与退回', [
    `- 续跑：新建运行目录，参数文件基本照旧（可按本总结改截图配方、子项、角度），加 \`"continueFrom": "${cfg.workdir}"\`，再跑 \`${wl} init <新运行目录>\`。轮号接着 ${rtag(S.round + 1)} 往下编。`,
    `- 人工退回：最近一次 smoke 绿是 ${rtag(S.lastGreenRound)}；\`${restoreCmd}\` 先列出要动的路径，确认后去掉 --dry-run。`]);
  return out.join('\n') + '\n';
}

// ==== CORE END ====

// ==== SHELL ====
if (!INJECTED || INJECTED.v !== 1) throw new Error('BLOCKED: workflow.js 未经 wl.mjs init 生成');
const { cfg, errors } = validateArgs(INJECTED.args, INJECTED.derived);
if (errors.length) throw new Error('BLOCKED: args 无效：' + errors.join('；'));

let used = 0, threw = null;
// 计数 + 接住 throw（预算耗尽时 agent() 会抛）；抛过一次之后不再派
async function call(prompt, opts) {
  if (threw) return null;
  used++;
  try { return await agent(prompt, opts); } catch (e) { threw = String((e && e.message) || e); return null; }
}

const S = initState(cfg, INJECTED.seed ?? null);       // seed 版本不认识时抛 BLOCKED（此时一个 agent 都还没派）

phase('iterate');
try {
  for (let i = 0; i < cfg.maxRounds && !S.exit && !threw; i++) {
    if (cfg.maxAgents != null && used + roundAgentEstimate(cfg) > cfg.maxAgents) { markExit(S, 'budget', budgetDetail(cfg, used)); break; }
    const round = S.round + 1, rt = rtag(round);
    const impl = await call(implPrompt(cfg, S, round), { label: `impl-${rt}`, phase: 'iterate', schema: IMPL_SCHEMA });
    if (threw) break;                                   // implementer 阶段就耗尽了：这一轮不归并（回放同样停在这里）
    applyImpl(cfg, S, round, impl);
    const verify = await call(verifyPrompt(cfg, S, round), { label: `verify-${rt}`, phase: 'iterate', effort: verifyEffort(cfg, S), schema: VERIFY_SCHEMA });
    const gate = reviewGate(verify, round);
    const reviews = gate.reviewable
      ? await parallel(cfg.lenses.map(L => () => call(reviewerPrompt(cfg, S, round, L, verify), { label: `review-${L}-${rt}`, phase: 'iterate', ...REVIEW_OPTS, schema: reviewerSchema(L) })))
      : null;
    reduceRound(cfg, S, round, verify, reviews);       // 含出口判定
    log(roundLine(S));
  }
  if (!S.exit) markExit(S, threw ? 'budget' : 'max-rounds', threw);
} catch (e) { markExit(S, 'error', String((e && e.message) || e)); }
return finalReturn(cfg, S, used);
