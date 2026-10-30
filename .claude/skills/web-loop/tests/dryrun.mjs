// web-loop dry-run 外壳:不派真 agent,真跑 workflow-template.js 的控制流。
// 加载方式:把模板源码里的 `export const meta` 改成 `const meta`,整体包进 AsyncFunction 执行,
//   因此顶层 `return`(把 SUMMARY 交回主会话)与顶层 `await` 都合法,且每次 run 互相隔离、不落临时文件。
// 注入:agent / parallel / pipeline / phase / log / budget / args;Date.now / Math.random / 无参 new Date 与真 runtime 一样会抛错。
// 用法:const { calls, logs, phases, result, error } = await run(args, (label, prompt, opts) => 返回值或 undefined);
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
export const TEMPLATE_PATH = process.env.WEBLOOP_TEMPLATE || resolve(here, '..', 'workflow-template.js');
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;

export const A0 = { url: 'http://localhost:1', goal: 'g', workdir: '/w', rubricPath: '/w/r.md', runtag: 'rt', uiDir: '/u', shotsDir: '/w/shots', smokeCmd: 'true' };
export const SUB_G1 = [{ id: 'G1', desc: 'd', verifiable_via: 'screenshot' }];
export const V_G1 = { verified: [{ title: 'G1', evidence: 'e', coveredSubgoals: ['G1'] }] };

export const THROW = Symbol('THROW');
export const pad = r => `r${String(r).padStart(2, '0')}`;
export const rnum = l => parseInt((String(l).match(/-r(\d\d)$/) || [])[1] || '0', 10);
export const lensOf = l => (String(l).match(/^review-(\w+)-r\d\d$/) || [])[1];

export function stripExport(src) {
  return src.replace(/^export\s+const\s+meta\b/m, 'const meta');
}
/** 语法检查:接受顶层 return / await(替代旧的「裸顶层 node --check」) */
export function checkSyntax(src = readFileSync(TEMPLATE_PATH, 'utf8')) {
  new AsyncFunction('args', 'agent', 'parallel', 'pipeline', 'phase', 'log', 'budget', stripExport(src));
}

/** 各 label 的缺省「一切顺利」返回;未知 label 返回 undefined(与真 runtime 里 schema 缺省一致) */
export function base(label) {
  if (label === 'cleanup-old-runs') return { cleaned_runtags: [], deleted_mcp: false };
  if (label === 'pw-selfcheck') return { ok: true };
  if (label === 'preflight') return { rubricFound: true, smokeBaselineGreen: true };
  if (label === 'write-goal') return { wrote: true };
  if (label.startsWith('read-state-')) return { exists: false, forbiddenApproaches: [], entries: [], totalLines: 300, p1_skip_reason: null };
  if (label.startsWith('impl-')) return { reviewer_stuck: false, kind: 'frontend' };
  if (label.startsWith('smoke-')) return { pass: true };
  if (label.startsWith('refresh-')) return { ready: true, kind: 'frontend' };
  if (label.startsWith('capture-')) return { shots: [{ state: '01', path: '/w/shots/x.png', bytes: 10 }] };
  if (label.startsWith('read-impl-stuck-')) return { ok: true, stuck: false, summary: '' };
  if (label.startsWith('meta-agent-')) return { forbiddenApproaches: [], prioritizedMustIds: [], p1_skip_reason: 'no-stall', escapeRequest: null };
  if (lensOf(label)) return verdict(lensOf(label));
  return undefined;
}
export const verdict = (lens, o = {}) => ({ lens, verdict: 'pass', mustFixOpen: 0, issues: [], verified: [], knownIssuesStatus: [], ...o });

function guardedDate() {
  const D = function (...a) {
    if (!a.length) throw new Error('new Date() 无参在 workflow 里非法(破坏 resume)');
    return new Date(...a);
  };
  D.now = () => { throw new Error('Date.now() 在 workflow 里非法(破坏 resume)'); };
  D.parse = Date.parse; D.UTC = Date.UTC;
  return D;
}
function guardedMath() {
  const M = Object.create(Math);
  M.random = () => { throw new Error('Math.random() 在 workflow 里非法(破坏 resume)'); };
  return M;
}

const INJECT_BEGIN = '// ==== INJECT BEGIN ====', INJECT_END = '// ==== INJECT END ====';
/** 生成注入后的 workflow 源码:优先用 wl.mjs 导出的 buildWorkflowSource(与 init 同一份),没有则按约定自己替换 */
export async function buildSource(templateSrc, injected) {
  try {
    const wl = await import(resolve(here, '..', 'wl.mjs'));
    if (typeof wl.buildWorkflowSource === 'function') return wl.buildWorkflowSource(templateSrc, injected);
  } catch { /* wl.mjs 尚未落地 */ }
  const a = templateSrc.indexOf(INJECT_BEGIN), b = templateSrc.indexOf(INJECT_END);
  if (a < 0 || b < a) throw new Error('模板里没有 INJECT BEGIN/END 标记');
  return templateSrc.slice(0, a + INJECT_BEGIN.length) + `\nconst INJECTED = ${JSON.stringify(injected)};\n` + templateSrc.slice(b);
}
/**
 * @param args    脚本入参对象
 * @param respond (label, prompt, opts) => 预设返回值;返回 undefined 则用 base(label);可 throw 模拟 agent 抛错;返回 null 模拟被跳过
 * @param o       { argsForm(旧模板): 'string'|'object'; seed: 新设计的续跑 seed; injected: 直接指定 INJECTED(可为 null 模拟未经 init); maxAgentCalls: 死循环保险 }
 */
export async function run(args, respond = () => undefined, o = {}) {
  const calls = [], logs = [], phases = [];
  const cap = o.maxAgentCalls ?? 2000;
  const agent = async (prompt, opts = {}) => {
    if (calls.length >= cap) throw new Error(`dryrun: agent 调用超过 ${cap},疑似死循环`);
    const label = opts.label || '';
    calls.push({ i: calls.length, label, prompt: String(prompt), opts });
    const c = calls[calls.length - 1];
    const r0 = await respond(label, String(prompt), opts);
    if (r0 === THROW) { c.threw = true; throw new Error('dryrun THROW'); }
    const r = r0 === undefined ? base(label) : r0;
    c.result = r;
    return r;
  };
  const parallel = async thunks => Promise.all(thunks.map(async t => { try { return await t(); } catch { return null; } }));
  const pipeline = async (items, ...stages) => Promise.all(items.map(async (it, idx) => {
    let v = it;
    for (const s of stages) v = await s(v, it, idx);
    return v;
  }));
  const phase = t => { phases.push(t); };
  const log = m => { logs.push(String(m)); };
  const budget = { total: null, remaining: () => Infinity };
  let result, error = null;
  try {
    let src = readFileSync(TEMPLATE_PATH, 'utf8');
    let argv;
    if (src.includes(INJECT_BEGIN)) {          // 新设计:args 与 seed 由 init 注入 INJECT 段,运行时 args 为 undefined
      const injected = 'injected' in o ? o.injected : { v: 1, args, seed: o.seed ?? null };
      src = await buildSource(src, injected);
      argv = undefined;
    } else argv = o.argsForm === 'object' ? args : JSON.stringify(args);   // 旧模板:args 字符串/对象
    const fn = new AsyncFunction('args', 'agent', 'parallel', 'pipeline', 'phase', 'log', 'budget', 'Date', 'Math', stripExport(src));
    result = await fn(argv, agent, parallel, pipeline, phase, log, budget, guardedDate(), guardedMath());
  } catch (e) { error = e; }
  const out = { calls, logs, phases, result, error };
  // 通用回放钩子:凡 debug:true 且出口不是 budget/error 的 run,自动把 calls 转成假 journal 回放,深比较 S(skeptic 建议)
  if (args && args.debug && result && result.state && !error && !['budget', 'error'].includes(result.exitReason) && !o.noReplay) {
    try {
      const injected = 'injected' in o ? o.injected : null;
      const C = core(); const { cfg } = (() => { const v = C.validateArgs(args, injected && injected.derived); return v; })();
      const results = {}, started = [];
      for (const c of calls) { started.push(c.label); if (c.result !== undefined && !c.threw) results[c.label] = c.result; }
      const rep = C.replay(cfg, o.seed ?? null, { results, started }, 'end');
      out.replayCheck = { ok: deepEqual(rep.S, result.state), exitOk: rep.exitReason === result.exitReason };
    } catch (e) { out.replayCheck = { ok: false, exitOk: false, error: String(e.message) }; }
  }
  return out;
}

// ── 断言/查询小工具 ──
export const byPrefix = (calls, p) => calls.filter(c => c.label.startsWith(p));
export const byLabel = (calls, l) => calls.find(c => c.label === l);
export const agentCount = calls => calls.length;
/** 从 persist 的 prompt 里抠 issues.json 正文(旧格式;新设计改了 persist 后在此处适配) */
export function issuesFromPersist(calls, rtag) {
  const c = byLabel(calls, `persist-${rtag}`);
  if (!c) return null;
  const m = c.prompt.match(/issues\.json\(覆写\)=(.*?);写 /s);
  try { return m ? JSON.parse(m[1]) : null; } catch { return null; }
}
/** 退出信息:优先取脚本返回值里的结构,退而取日志里含 done 的行 */
export function exitText({ logs, result }) {
  const l = logs.find(x => /done/.test(x));
  return l || (result && JSON.stringify(result).slice(0, 400)) || '';
}
export const pausedCalls = calls => calls.filter(c => c.label.startsWith('paused-'));
export const pausedCriteria = calls => pausedCalls(calls).map(c => (c.prompt.match(/触发判据:\*\*(\w+)/) || [])[1]);

// ── 迷你场景框架:每个场景独立记 PASS/FAIL,不因一个失败中断 ──
export async function runScenarios(scenarios, { filter = process.env.SCN } = {}) {
  let fail = 0, pass = 0;
  for (const [id, title, fn] of scenarios) {
    if (filter && !id.match(new RegExp(filter))) continue;
    try {
      const notes = await fn();
      console.log(`PASS ${id} ${title}${notes ? ' :: ' + notes : ''}`);
      pass++;
    } catch (e) {
      console.log(`FAIL ${id} ${title} :: ${String(e.message).split('\n')[0]}`);
      fail++;
    }
  }
  console.log(`-- ${pass} passed, ${fail} failed`);
  return fail;
}
export function expect(cond, msg) { if (!cond) throw new Error(msg); }
export function expectNoError(res) {
  if (res.replayCheck && !(res.replayCheck.ok && res.replayCheck.exitOk)) throw new Error('回放与运行不一致(自动钩子): ' + JSON.stringify(res.replayCheck));
  if (res.error) throw new Error('模板抛错: ' + (res.error.stack || res.error).toString().split('\n').slice(0, 2).join(' | ')); }

// ════════ 新设计(CORE/SHELL 结构)支持 ════════
const CORE_BEGIN = '// ==== CORE BEGIN ====', CORE_END = '// ==== CORE END ====';
const CORE_NAMES = 'verifyLine, normalizeImpl, normalizeReview, REVIEW_OPTS, COMMON, validateArgs, canonHash, initState, applyImpl, reviewGate, reduceRound, markExit, toSeed, replay, renderSummary, compactLedger, implPrompt, verifyPrompt, reviewerPrompt, finalReturn, normalizeVerify, BUILTIN_LENSES, verifyEffort, roundLine, reviewerSchema, IMPL_SCHEMA, VERIFY_SCHEMA, rtag, roundAgentEstimate';
/** 按标记截取 CORE 并在空作用域求值(与 wl.mjs 的 loadCore 同口径,测试不依赖 wl.mjs) */
export function loadCoreSource(path = TEMPLATE_PATH) {
  const src = readFileSync(path, 'utf8');
  const a = src.indexOf(CORE_BEGIN), b = src.indexOf(CORE_END);
  if (a < 0 || b < a) throw new Error('模板里没有 CORE BEGIN/END 标记');
  return src.slice(a + CORE_BEGIN.length, b);
}
export function loadCore(path = TEMPLATE_PATH) {
  const body = loadCoreSource(path) + `\nreturn {${CORE_NAMES.split(', ').map(n => `${n}: typeof ${n} === 'undefined' ? undefined : ${n}`).join(', ')}};`;
  return new Function(body)();
}
let _core = null;
export const core = () => (_core ||= loadCore());

export const STATES = ['01-a', '02-b'];
/** 新设计缺省 args:1 个子项归 ux,3 个角度 */
export function newArgs(o = {}) {
  return { runtag: 'rt', workdir: '.claude/web-loop/rt', goal: 'GOAL_TEXT', url: 'http://localhost:1/', statesPath: '.claude/web-loop/rt/states.json',
    uiDir: 'ui', rubricPath: 'rubric.md', smokeCmd: 'true', maxRounds: 5, staleRounds: 2, lenses: ['ux', 'func', 'code'],
    goalSubgoals: [{ id: 'G1', desc: 'SUBGOAL_G1', lenses: ['ux'] }], ...o };
}
/** 生成带正确 sig 的 verify 返回(design §2.5 的短字段形状)。failed 可传 [{state,error}] 或 failedStates 传名字数组;tamper:true 改坏 sig */
export function fakeVerify(o = {}) {
  const { round = 1, kind = 'frontend', kindAdjusted = null, okStates = STATES, failed = [], failedStates = failed.map(f => (typeof f === 'string' ? f : f.state)),
    errorStates = [], newErrors = [], smokePass = true, flaky = false, rolledBack = false, envBroken = false, refreshOk = true, envOk = true, noChange = false,
    form = 'string', snapOk = true, changedCount = 1, schemeTouched = [], journalCopied = true, noCapture = false, tamper = false, hash = core().canonHash } = o;
  const res = { round, kind, kindAdjusted, envOk, noChange, journalCopied, snapOk, changedCount, schemeTouched,
    smoke: { pass: smokePass, flaky, rolledBack, envBroken }, refreshOk, manifest: `/abs/.claude/web-loop/rt/shots/r${String(round).padStart(2, '0')}_manifest.json`,
    capture: (!smokePass || !refreshOk || noCapture || !envOk || noChange) ? null : { okStates, failedStates, errorStates, newErrors } };
  res.sig = hash(res);
  if (tamper) res.sig = res.sig.slice(0, -1) + (res.sig.endsWith('0') ? '1' : '0');
  // 缺省走约定形式(最后一行 JSON 文本);object/wrapped/noisy 用来测 verifyLine 的各种容错
  const txt = JSON.stringify(res);
  const result = form === 'object' ? res : form === 'wrapped' ? { line: txt } : form === 'noisy' ? '[verify r01] 探 url …\n[capture r01] 01-a ok\n' + txt + '\n' : txt;
  return { result, note: '', toMain: null };
}
export const okImpl = (o = {}) => ({ kind: 'frontend', summary: 'IMPL_SUMMARY', changedFiles: [], attempts: [], hintsRead: [], overrides: [], deferred: [], toMain: null, ...o });
/** 评审返回:缺省对自己负责的子项判 met、没有问题 */
export function okReview(args, lens, o = {}) {
  const subgoals = (args.goalSubgoals || []).filter(g => (g.lenses || []).includes(lens)).map(g => ({ id: g.id, status: 'met', evidence: 'e' }));
  return { known: [], subgoals, issues: [], directions: [], toMain: null, ...o };
}
export const mustIssue2 = (title, o = {}) => ({ title, severity: 'must', detail: 'DETAIL ' + title, evidence: 'EVID ' + title, state: null, subgoal: null, ...o });
/**
 * 新设计的脚本化 respond。h = { impl(round), verify(round)->fakeVerify 选项或完整返回, review(lens, round, prompt)->okReview 的覆盖项或完整返回/null/THROW, other(label,prompt) }
 * 返回 undefined 的 handler 用缺省。
 */
export function sim(args, h = {}) {
  return (label, prompt) => {
    let m;
    if ((m = label.match(/^impl-r(\d\d)$/))) { const r = +m[1]; const v = h.impl ? h.impl(r, prompt) : undefined; return v === undefined ? okImpl() : v; }
    if ((m = label.match(/^verify-r(\d\d)$/))) { const r = +m[1]; const v = h.verify ? h.verify(r, prompt) : undefined;
      if (v === undefined) return fakeVerify({ round: r }); return (v && v.result !== undefined) || v === null || v === THROW ? v : fakeVerify({ round: r, ...v }); }
    if ((m = label.match(/^review-([a-z0-9_-]+)-r(\d\d)$/))) { const r = +m[2]; const v = h.review ? h.review(m[1], r, prompt) : undefined;
      if (v === undefined) return okReview(args, m[1]); if (v === null || v === THROW || (v && v.issues !== undefined && v.known !== undefined)) return v; return okReview(args, m[1], v); }
    return h.other ? h.other(label, prompt) : undefined;
  };
}
/** 跑新设计的模板;args 缺省 newArgs() */
export const runNew = (args, h, o) => { const a = args.debug === false ? args : { ...args, debug: true }; return run(a, sim(a, h), o); };   // 缺省开 debug:true,让每个 run 自动做回放一致性检查
export function deepEqual(a, b) { return JSON.stringify(sortKeys(a)) === JSON.stringify(sortKeys(b)); }
function sortKeys(x) { if (Array.isArray(x)) return x.map(sortKeys); if (x && typeof x === 'object') return Object.fromEntries(Object.keys(x).sort().map(k => [k, sortKeys(x[k])])); return x; }

/** 直接用 CORE 推进状态(单元式):step(cfg,S,round,{impl,verify,reviews}) */
export function coreStep(cfg, S, round, { impl = okImpl(), verify = fakeVerify({ round }), reviews } = {}) {
  const C = core();
  C.applyImpl(cfg, S, round, impl);
  const gate = C.reviewGate(verify);
  const rv = gate.reviewable ? (reviews || cfg.lenses.map(L => okReview(cfg, L))) : null;
  C.reduceRound(cfg, S, round, verify, rv);
  return S.rounds[S.rounds.length - 1];
}
export function coreInit(argsObj, seed = null) {
  const C = core(); const { cfg, errors } = C.validateArgs(argsObj);
  if (errors.length) throw new Error('validateArgs: ' + errors.join(';'));
  return { cfg, S: C.initState(cfg, seed) };
}
