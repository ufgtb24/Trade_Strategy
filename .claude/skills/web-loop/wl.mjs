#!/usr/bin/env node
// web-loop 的确定性工具（node CLI，零依赖）。命令：
//   init <W>                                     开跑前校验参数与配方、跑基线 smoke、拍 r00 快照与起点图、生成 <W>/workflow.js
//   verify <W> --round N --kind K [--refreshed] [--no-change-hint]   每轮由 verify 代理调用：留证 → 探环境 → 快照 → smoke（红则退回）→ 刷新 → 截图；最后一行打印带签名的短结果
//                                                真正干活的是 detached 起的 worker（不随 Bash 超时被杀）；前台最多等约 9 分钟，没等到打印 {"pending":true}
//   wait <W> --round N                           继续等那一轮的 verify worker，同样最多约 9 分钟
//   intake <W> --done <逗号分隔的 key>             列出主会话中途放进 control/ 的 hint 与 override（不改文件名）
//   diff <W> --round N | --run [-- 路径…]          本轮或本 run 的代码改动（树 id 不经 LLM）
//   restore <W> --to rNN|green|r00|before-restore [--dry-run]   人工退回（仅在用户要求时）
//   attach <W> <runId> <transcriptDir>           Workflow 启动后立刻记下 journal 位置
//   status <W> [--journal 路径]                   进行中的台账概览（回放 journal）
//   export <W> [--journal 路径] | --from-ledger <文件>   结束后回放 journal，写 ledger.json、SUMMARY.md、各轮原始返回，方向题证据图复制到 <W>/evidence/
//   rubric-diff <旧> <新>                         按节列出两份验收标准的增删行（参数可为文件或运行目录），复用上次标准时只给用户看改动
// 同时导出 loadCore / loadInjected / buildWorkflowSource / findJournal / parseJournal 供测试与 capture.mjs 使用。
// 纪律：不经 LLM 抄写任何 JSON；git 快照只用临时 index（GIT_INDEX_FILE），不碰真 index、HEAD 与 stash，不提交；
//   等待一律用 node 定时器；杀进程只按端口查出的进程号。
import { readFileSync, writeFileSync, existsSync, mkdirSync, copyFileSync, readdirSync, statSync, rmSync, openSync, closeSync, readSync, renameSync } from 'node:fs';
import { spawn, spawnSync } from 'node:child_process';
import { dirname, join, resolve, relative, basename, isAbsolute } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { homedir } from 'node:os';

const SELF = fileURLToPath(import.meta.url), HERE = dirname(SELF);
const TEMPLATE = join(HERE, 'workflow-template.js');
const CORE_BEGIN = '// ==== CORE BEGIN ====', CORE_END = '// ==== CORE END ====';
const INJECT_BEGIN = '// ==== INJECT BEGIN ====', INJECT_END = '// ==== INJECT END ====';
const CORE_NAMES = ['validateArgs', 'canonHash', 'initState', 'applyImpl', 'normalizeImpl', 'normalizeReview', 'normalizeVerify', 'reviewGate',
  'reduceRound', 'markExit', 'finalReturn', 'toSeed', 'replay', 'renderSummary', 'compactLedger', 'implPrompt', 'verifyPrompt', 'reviewerPrompt',
  'reviewerSchema', 'IMPL_SCHEMA', 'VERIFY_SCHEMA', 'REVIEW_OPTS', 'BUILTIN_LENSES', 'SECTION_LENSES', 'COMMON', 'EXIT_TEXT', 'rtag',
  'roundAgentEstimate', 'verifyEffort', 'roundLine'];
const DERIVED_KEYS = ['terms', 'root', 'W', 'skill'];        // validateArgs 推导出的字段，写回 args.json 时去掉
const SMOKE_TIMEOUT = 6 * 60 * 1000;
const VERIFY_WAIT_MS = 9 * 60 * 1000;                      // 前台等 worker 的上限：留出余量给 Bash 的 10 分钟上限
const INTAKE_WAIT_MS = 100 * 1000;                         // intake 不要求调用方加长 timeout：只等到 Bash 默认 2 分钟以内，没等完就报 verifyRunning 让它再跑一次
const SRC_EXT = /\.(py|ts|js|mjs|vue|go|rs|java|rb|json|yaml|yml)$/i;
const CONTRACT_SKELETON = runtag => `# 后端要求清单（${runtag}）\n\n> 原型背后的演示数据和模拟逻辑要求后端提供什么：每个字段、每项计算一节，写明含义、类型、来源或算法。implementer 改动方案文件时同步更新本清单。\n`;
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;

// ── 模板与注入 ──
/** 截取模板（或生成的 workflow.js）的 CORE 段，在空作用域求值 */
export function loadCore(path) {
  const src = readFileSync(path, 'utf8');
  const a = src.indexOf(CORE_BEGIN), b = src.indexOf(CORE_END);
  if (a < 0 || b < a) throw new Error(`${path} 里没有 CORE BEGIN/END 标记`);
  return new Function(src.slice(a + CORE_BEGIN.length, b) + `\nreturn {${CORE_NAMES.map(n => `${n}: typeof ${n} === 'undefined' ? undefined : ${n}`).join(', ')}};`)();
}
/** 截取 workflow.js 的 INJECT 段并求值，得到 INJECTED */
export function loadInjected(path) {
  const src = readFileSync(path, 'utf8');
  const a = src.indexOf(INJECT_BEGIN), b = src.indexOf(INJECT_END);
  if (a < 0 || b < a) throw new Error(`${path} 里没有 INJECT BEGIN/END 标记`);
  return new Function(src.slice(a + INJECT_BEGIN.length, b) + '\nreturn INJECTED;')();
}
/** 把模板的 INJECT 段替换成字面量（init 与测试外壳共用） */
export function buildWorkflowSource(templateSrc, injected) {
  const a = templateSrc.indexOf(INJECT_BEGIN), b = templateSrc.indexOf(INJECT_END);
  if (a < 0 || b < a) throw new Error('模板里没有 INJECT BEGIN/END 标记');
  return templateSrc.slice(0, a + INJECT_BEGIN.length) + `\nconst INJECTED = ${JSON.stringify(injected)};\n` + templateSrc.slice(b);
}
/** 能容纳顶层 return 的语法检查（裸 node --check 会误报） */
function checkWorkflowSyntax(src) {
  new AsyncFunction('args', 'agent', 'parallel', 'pipeline', 'phase', 'log', 'budget', src.replace(/^export\s+const\s+meta\b/m, 'const meta'));
}

// ── 小工具 ──
const rtag = n => 'r' + String(n).padStart(2, '0');
const sleep = ms => new Promise(r => setTimeout(r, ms));
const say = (...a) => console.log(...a);
const tailLines = (s, n) => String(s || '').replace(/\x1b\[[0-9;]*[A-Za-z]/g, '').split('\n').slice(-n).join('\n');
const isObj = x => x != null && typeof x === 'object' && !Array.isArray(x);
function readJson(p, what) {
  let t;
  try { t = readFileSync(p, 'utf8'); } catch { throw new Error(`读不到 ${what || p}：${p}`); }
  try { return JSON.parse(t); } catch (e) { throw new Error(`${what || p} 不是合法 JSON：${e.message}`); }
}
const readIf = p => (existsSync(p) ? readFileSync(p, 'utf8').trim() : null);
function gitRoot(dir) {
  const r = spawnSync('git', ['-C', dir, 'rev-parse', '--show-toplevel'], { encoding: 'utf8' });
  if (r.status !== 0) throw new Error(`${dir} 不在 git 仓库里`);
  return r.stdout.trim();
}
/** git 调用：idx 给定时用临时 index；路径默认按字面解释（check-ignore 不支持，要传 literal:false） */
function git(root, args, { idx = null, input = undefined, literal = true } = {}) {
  const env = { ...process.env };
  if (literal) env.GIT_LITERAL_PATHSPECS = '1';
  if (idx) env.GIT_INDEX_FILE = idx;
  const r = spawnSync('git', args, { cwd: root, env, input, encoding: 'utf8', maxBuffer: 256 * 1024 * 1024 });
  return { code: r.status, out: r.stdout || '', err: (r.stderr || '') + (r.error ? String(r.error) : '') };
}
function gitOk(root, args, opts) {
  const r = git(root, args, opts);
  if (r.code !== 0) throw new Error(`git ${args.slice(0, 3).join(' ')} 失败：${tailLines(r.err, 5)}`);
  return r.out;
}
/** 在 repo root 用 bash 跑一条命令，收集合并输出；超时杀整个进程组 */
function runShell(cmd, { cwd, timeoutMs = SMOKE_TIMEOUT } = {}) {
  return new Promise(res => {
    const child = spawn('/bin/bash', ['-c', cmd], { cwd, detached: true, stdio: ['ignore', 'pipe', 'pipe'] });
    let out = '', timedOut = false;
    const add = d => { out += d; if (out.length > 4e6) out = out.slice(-2e6); };
    child.stdout.on('data', add); child.stderr.on('data', add);
    const t = setTimeout(() => { timedOut = true; try { process.kill(-child.pid, 'SIGKILL'); } catch { /* 已退出 */ } }, timeoutMs);
    child.on('error', e => { clearTimeout(t); res({ code: 127, out: out + String(e), timedOut }); });
    child.on('close', code => { clearTimeout(t); res({ code: timedOut ? 124 : code, out, timedOut }); });
  });
}
/** 探 url：http(s) 发 GET（收到响应且非 5xx 即通），file:// 查文件存在 */
async function probeUrl(url, timeoutMs = 5000) {
  if (url.startsWith('file:')) { const p = fileURLToPath(url.split('#')[0].split('?')[0]); return { ok: existsSync(p), status: null }; }
  const ac = new AbortController(), t = setTimeout(() => ac.abort(), timeoutMs);
  try { const r = await fetch(url, { signal: ac.signal, redirect: 'manual' }); return { ok: r.status < 500, status: r.status }; }
  catch (e) { return { ok: false, status: null, error: String(e.cause?.code || e.message) }; }
  finally { clearTimeout(t); }
}
function listenPids(port) {
  const r = spawnSync('lsof', ['-ti', `tcp:${port}`, '-sTCP:LISTEN'], { encoding: 'utf8' });
  if (r.error) throw new Error('需要 lsof 才能按端口找后端进程：' + r.error.message);
  return [...new Set((r.stdout || '').split(/\s+/).filter(Boolean).map(Number))];
}
async function waitUntil(fn, ms, every = 300) {
  const end = performance.now() + ms;
  for (;;) { if (await fn()) return true; if (performance.now() > end) return false; await sleep(every); }
}

// ── 运行目录上下文 ──
function ctxOf(Warg, { needWorkflow = true } = {}) {
  if (!Warg) throw new Error('缺少运行目录参数');
  const W = resolve(Warg);
  if (!existsSync(W)) throw new Error(`运行目录不存在：${W}`);
  const root = gitRoot(W);
  const wf = join(W, 'workflow.js');
  if (!existsSync(wf)) { if (needWorkflow) throw new Error(`${wf} 不存在：先跑 wl.mjs init`); return { W, root }; }
  const core = loadCore(wf), injected = loadInjected(wf);
  const { cfg } = core.validateArgs(injected.args, { root, ...(injected.derived || {}) });   // 用注入时的 root，保证回放与运行时同一份 cfg
  return { W, root, core, injected, cfg, snap: join(W, 'snap'), idx: join(W, 'snap', 'snap.idx') };
}
const relRoot = (root, p) => relative(root, resolve(root, p));
/** 快照与回滚都不管的路径：截图配方、验收标准源、.claude/web-loop/ 下的一切、运行目录 */
function exemptFn(ctx) {
  const { root, cfg, W } = ctx;
  const files = new Set([relRoot(root, cfg.statesPath), relRoot(root, cfg.rubricPath)]);
  const dirs = ['.claude/web-loop/', relative(root, W) + '/'];
  return p => files.has(p) || dirs.some(d => p.startsWith(d));
}

// ── 快照（临时 index）──
function snapshotTree(ctx) {
  gitOk(ctx.root, ['add', '-A'], { idx: ctx.idx });
  return gitOk(ctx.root, ['write-tree'], { idx: ctx.idx }).trim();
}
/** 两棵树之间变了的路径（去掉豁免路径） */
function diffTrees(ctx, a, b) {
  const out = gitOk(ctx.root, ['diff-tree', '-r', '-z', '--no-renames', '--name-status', a, b]);
  const parts = out.split('\0').filter(x => x !== '');
  const exempt = exemptFn(ctx), res = [];
  for (let i = 0; i + 1 < parts.length; i += 2) if (!exempt(parts[i + 1])) res.push({ status: parts[i], path: parts[i + 1] });
  return res;
}
const treeOf = (ctx, name) => readIf(join(ctx.snap, `${name}.tree`));
/** 第 N 轮开工前的树：上一轮退回后的树 → 上一轮交回后的树 → r00 */
const preTree = (ctx, N) => treeOf(ctx, `${rtag(N - 1)}.restored`) || treeOf(ctx, rtag(N - 1)) || treeOf(ctx, 'r00');
/** 把 paths 恢复成 tree 里的样子：tree 里有的从 tree 检出，没有的删掉。只动这些路径。 */
function restoreTo(ctx, tree, paths) {
  if (!paths.length) return { restored: [], deleted: [] };
  const ridx = join(ctx.snap, 'restore.idx');
  const inTree = new Set();
  for (let i = 0; i < paths.length; i += 500)
    gitOk(ctx.root, ['ls-tree', '-r', '-z', '--name-only', tree, '--', ...paths.slice(i, i + 500)]).split('\0').filter(Boolean).forEach(p => inTree.add(p));
  const restored = paths.filter(p => inTree.has(p)), deleted = paths.filter(p => !inTree.has(p));
  gitOk(ctx.root, ['read-tree', tree], { idx: ridx });
  for (let i = 0; i < restored.length; i += 500) gitOk(ctx.root, ['checkout-index', '-f', '--', ...restored.slice(i, i + 500)], { idx: ridx });
  for (const p of deleted) rmSync(join(ctx.root, p), { force: true });
  return { restored, deleted };
}
function statesHash(ctx) {
  const p = resolve(ctx.root, ctx.cfg.statesPath);
  const t = readIf(p);
  if (t == null) return 'missing';
  try { return ctx.core.canonHash(JSON.parse(t)); } catch { return ctx.core.canonHash(t); }
}

// ── journal ──
const projectsDir = () => process.env.WL_PROJECTS_DIR || join(homedir(), '.claude', 'projects');
/** 递归找所有 workflows/<id>/journal.jsonl（不写死层级） */
function allJournals(dir = projectsDir(), depth = 6) {
  const out = [];
  let ents;
  try { ents = readdirSync(dir, { withFileTypes: true }); } catch { return out; }
  for (const e of ents) {
    if (!e.isDirectory()) continue;
    const p = join(dir, e.name);
    if (e.name === 'workflows') {
      let runs = [];
      try { runs = readdirSync(p, { withFileTypes: true }); } catch { /* 读不了就跳过 */ }
      for (const r of runs) if (r.isDirectory() && existsSync(join(p, r.name, 'journal.jsonl'))) out.push(join(p, r.name, 'journal.jsonl'));
    } else if (depth > 0) out.push(...allJournals(p, depth - 1));
  }
  return out;
}
/** 按内容认 journal：含 `"<W 绝对路径>/shots/` 字样的那份（verify 结果里的 manifest 路径带它；label 在不同 run 之间会重复，不能按 label 认） */
function journalsByContent(W, maxAgeMs = null) {
  const needle = `"${W}/shots/`, now = Date.now();
  return allJournals().filter(j => {
    try { if (maxAgeMs != null && now - statSync(j).mtimeMs > maxAgeMs) return false; return headOf(j, 256 * 1024).includes(needle); } catch { return false; }
  });
}
/** 只读文件开头一段：第 1 轮 verify 的结果紧跟在 implementer 的结果之后，字样一定落在开头，不必整读 */
function headOf(p, n) {
  const fd = openSync(p, 'r');
  try { const b = Buffer.alloc(n); return b.toString('utf8', 0, readSync(fd, b, 0, n, 0)); } finally { closeSync(fd); }
}
function writeRunJson(W, journalPath, foundBy) {
  const transcriptDir = dirname(journalPath);
  writeFileSync(join(W, 'run.json'), JSON.stringify({ runId: basename(transcriptDir), transcriptDir, foundBy }, null, 2));
}
/**
 * 找 journal。顺序：--journal → run.json 的 transcriptDir → 按 runId 递归找 → 按内容兜底（唯一时补写 run.json）→ 本地副本。
 * 返回 { path, source, raw: 是否原始文件, note }；都找不到时抛错。
 */
export function findJournal(W, { journal = null } = {}) {
  W = resolve(W);
  if (journal) { if (!existsSync(journal)) throw new Error(`--journal 指定的文件不存在：${journal}`); return { path: resolve(journal), source: '--journal', raw: true, note: null }; }
  const rj = existsSync(join(W, 'run.json')) ? readJson(join(W, 'run.json'), 'run.json') : null;
  if (rj && rj.transcriptDir && existsSync(join(rj.transcriptDir, 'journal.jsonl'))) return { path: join(rj.transcriptDir, 'journal.jsonl'), source: 'run.json', raw: true, note: null };
  if (rj && rj.runId) {
    const hit = allJournals().filter(j => basename(dirname(j)) === rj.runId);
    if (hit.length === 1) return { path: hit[0], source: 'runId', raw: true, note: null };
  }
  const byContent = journalsByContent(W);
  if (byContent.length === 1) { if (!rj) writeRunJson(W, byContent[0], 'content'); return { path: byContent[0], source: 'content', raw: true, note: null }; }
  if (byContent.length > 1) throw new Error(`有多份 journal 都含本运行目录的截图路径，无法确定是哪一份，请用 --journal 指定：\n${byContent.join('\n')}`);
  const local = join(W, 'journal.jsonl');
  if (existsSync(local)) return { path: local, source: 'local', raw: false, note: '只找到运行目录里的 journal 副本，它可能缺最后一轮' };
  throw new Error('找不到这次 run 的 journal（run.json 缺失或失效、按内容也没认出来）。可以用 --journal 指定；或者把 Workflow 返回值里的 ledger 写进文件，再用 export --from-ledger <文件> 出简版总结');
}
/** 逐行解析 journal：started 记 key→label 与开始顺序，result 记 label→result；最后一行写了一半时跳过 */
export function parseJournal(text) {
  const lines = String(text).split('\n');
  let lastIdx = lines.length - 1;
  while (lastIdx >= 0 && !lines[lastIdx].trim()) lastIdx--;
  const keyLabel = new Map(), started = [], results = {}, toolsUsed = {};
  let badLines = 0;
  for (let k = 0; k <= lastIdx; k++) {
    const l = lines[k];
    if (!l.trim()) continue;
    let o;
    try { o = JSON.parse(l); } catch { if (k !== lastIdx) badLines++; continue; }
    if (!isObj(o)) continue;
    if (o.type === 'started' && typeof o.label === 'string') {
      if (o.key != null) keyLabel.set(o.key, o.label);
      if (!started.includes(o.label)) started.push(o.label);
    } else if (o.type === 'result') {
      const label = keyLabel.get(o.key) || (typeof o.label === 'string' ? o.label : null);
      if (!label) continue;
      let r = o.result;
      if (typeof r === 'string') { try { r = JSON.parse(r); } catch { /* 保留原字符串 */ } }
      results[label] = r === undefined ? null : r;
      if (Array.isArray(o.toolsUsed)) toolsUsed[label] = o.toolsUsed;
    }
  }
  if (!started.length && !Object.keys(results).length) {
    const first = lines.find(l => l.trim()) || '（空文件）';
    throw new Error(`journal 里一条 started / result 都没解析出来，第一行：${first.slice(0, 300)}。运行时的 journal 格式可能变了，请看运行目录里 run-record.json 的 logs`);
  }
  return { started, results, toolsUsed, badLines };
}
/** 运行记录 <会话目录>/workflows/<runId>.json（会话目录 = transcriptDir 往上三级） */
function runRecordPath(W) {
  const p = join(W, 'run.json');
  if (!existsSync(p)) return null;
  const rj = readJson(p, 'run.json');
  if (!rj.transcriptDir || !rj.runId) return null;
  const f = join(resolve(rj.transcriptDir, '..', '..', '..'), 'workflows', `${rj.runId}.json`);
  return existsSync(f) ? f : null;
}
function readRunRecord(W) {
  const local = join(W, 'run-record.json'), p = runRecordPath(W) || (existsSync(local) ? local : null);
  if (!p) return null;
  try { const r = readJson(p); if (typeof r.result === 'string') { try { r.result = JSON.parse(r.result); } catch { /* 保留 */ } } return r; } catch { return null; }
}

// ── init ──
const esc = s => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
// 标题前面可以带编号（「## 7. 术语表」「### 5.1 角度 flow」）
const NUM = '(?:[0-9]+(?:\\.[0-9]+)*\\.?\\s*)?';
const hasLensSection = (text, L) => new RegExp(`^#{2,4}\\s*${NUM}(角度|lens)[\\s:：]+${esc(L)}\\s*$`, 'im').test(text);
function sectionText(text, re) {
  const lines = text.split('\n'), i = lines.findIndex(l => re.test(l));
  if (i < 0) return null;
  const level = (lines[i].match(/^#+/) || ['##'])[0].length, body = [];
  for (let k = i + 1; k < lines.length; k++) { const m = lines[k].match(/^(#+)\s/); if (m && m[1].length <= level) break; body.push(lines[k]); }
  return body.join('\n');
}
/** rubric「## 术语表」里每行 `- <词>：<含义>` 的词 */
function glossaryTerms(text) {
  const sec = sectionText(text, new RegExp(`^#{2,4}\\s*${NUM}术语表\\s*$`));
  if (sec == null) return null;
  return sec.split('\n').map(l => l.match(/^\s*[-*]\s+(.+?)[：:]/)).filter(Boolean).map(m => m[1].replace(/`/g, '').trim()).filter(Boolean);
}
function renderGoal(cfg) {
  const L = [`# GOAL（${cfg.runtag}）`, '', cfg.goal, '', '## 子项', ''];
  for (const g of cfg.goalSubgoals) L.push(`- ${g.id} · ${g.desc} · 负责：${g.lenses.join('、')}${g.states.length ? ' · 态：' + g.states.join('、') : ''}${g.measurable ? ' · 可度量：' + g.measurable : ''}`);
  if (cfg.refImages.length) { L.push('', '## 参考图', ''); for (const r of cfg.refImages) L.push(`- ${r.path} · role=${r.role || '?'}${r.description ? ' · ' + r.description : ''}`); }
  L.push('', `模式：${cfg.mode}；评审角度：${cfg.lenses.join('、')}；maxRounds：${cfg.maxRounds}`);
  return L.join('\n') + '\n';
}
/** 清理旧截图：同级运行目录里只保留最近一个与 continueFrom 那个的 shots/；不碰 .playwright-mcp/ */
function cleanupOldShots(W, keepAbs) {
  const parent = dirname(W), cleaned = [];
  let sibs = [];
  try { sibs = readdirSync(parent, { withFileTypes: true }).filter(e => e.isDirectory()).map(e => join(parent, e.name)); } catch { return cleaned; }
  sibs = sibs.filter(d => d !== W && existsSync(join(d, 'args.json')));          // 只认 web-loop 运行目录
  const mtime = d => statSync(join(d, 'args.json')).mtimeMs;
  sibs.sort((a, b) => mtime(b) - mtime(a));
  const keep = new Set([sibs[0], keepAbs].filter(Boolean));
  for (const d of sibs) if (!keep.has(d) && existsSync(join(d, 'shots'))) { rmSync(join(d, 'shots'), { recursive: true, force: true }); cleaned.push(basename(d)); }
  return cleaned;
}

async function cmdInit(Warg) {
  if (!Warg) throw new Error('用法：wl.mjs init <运行目录>');
  const W = resolve(Warg), root = gitRoot(W);
  const core = loadCore(TEMPLATE);
  const cap = await import(pathToFileURL(join(HERE, 'capture.mjs')).href);
  const raw = readJson(join(W, 'args.json'), 'args.json');
  const errs = [], warns = [];
  // 1. 参数
  const { cfg, errors } = core.validateArgs(raw, { root });
  errs.push(...errors);
  if (!errors.length && resolve(root, cfg.workdir) !== W) errs.push(`args.workdir（${cfg.workdir}）与运行目录 ${W} 不一致（workdir 相对 repo root）`);
  if (errors.length) return fail(errs);
  // 2. 运行目录必须被忽略
  if (git(root, ['check-ignore', '-q', W], { literal: false }).code !== 0) errs.push(`运行目录没有被 .gitignore 忽略：${relative(root, W)}（.claude/web-loop/ 必须在 .gitignore 里）`);
  // 3. 验收标准与角度专节
  const rubricSrc = resolve(root, cfg.rubricPath), principles = join(cfg.skill, 'principles.md');
  const rubric = readIf(rubricSrc);
  if (rubric == null) errs.push(`验收标准读不到：${rubricSrc}`);
  if (!existsSync(principles)) errs.push(`principles.md 读不到：${principles}`);
  const frozen = join(W, 'rubric.md');
  if (rubric != null) {
    const need = cfg.lenses.filter(L => !core.BUILTIN_LENSES.includes(L) || core.SECTION_LENSES.includes(L));
    for (const L of need) if (!hasLensSection(rubric, L)) errs.push(`验收标准缺「## 角度 ${L}」专节（自定义角度与 ${core.SECTION_LENSES.join('、')} 都要有：看哪些状态、判什么、什么算 must、对哪些子项负责）`);
    if (existsSync(frozen) && readFileSync(frozen, 'utf8') !== readFileSync(rubricSrc, 'utf8'))
      errs.push(`${frozen} 已冻结且与 ${cfg.rubricPath} 内容不同：跑的过程中不改判断标准，要改请新建运行目录`);
  }
  // 4. 截图配方
  let states = null;
  try { states = readJson(resolve(root, cfg.statesPath), '截图配方 statesPath'); } catch (e) { errs.push(e.message); }
  if (states) {
    errs.push(...cap.validateStates(states));
    if (Array.isArray(states)) {
      for (const s of states) {
        const w = (s && s.viewport && s.viewport.width) || cfg.viewport.width;
        if (s && !(s.crops || []).length && w > 1600) warns.push(`态 ${s.state} 没有声明 crops：小字区域请声明局部图（评审不能自己裁图）`);
      }
      warns.push(...cap.lintStates(states));
      if (cfg.lenses.includes('flow') && rubric) {
        const sec = sectionText(rubric, new RegExp(`^#{2,4}\\s*${NUM}(角度|lens)[\\s:：]+flow\\s*$`, 'i')) || '';
        if (states.filter(s => s && s.state && sec.includes(s.state)).length < 2) warns.push('「角度 flow」专节要按顺序列出流程经过的状态（用截图配方里的态名），否则 flow 评审只能记 unverifiable');
      }
    }
  }
  // 4b. 原型模式
  let terms = [];
  if (cfg.mode === 'prototype') {
    for (const f of cfg.schemeFiles) if (!existsSync(resolve(root, f))) errs.push(`方案文件不存在：${f}`);
    for (const f of cfg.mockFiles) if (!existsSync(resolve(root, f))) errs.push(`模拟逻辑文件不存在：${f}`);
    const cp = resolve(root, cfg.contractPath);
    if (cp === W || cp.startsWith(W + '/')) errs.push('后端要求清单 contractPath 不能放在运行目录里（要随代码快照一起回滚）');
    else if (git(root, ['check-ignore', '-q', cp], { literal: false }).code === 0) errs.push(`后端要求清单被 .gitignore 忽略了：${cfg.contractPath}（要放在原型旁边、不被忽略的位置）`);
    else if (!existsSync(cp)) { mkdirSync(dirname(cp), { recursive: true }); writeFileSync(cp, CONTRACT_SKELETON(cfg.runtag)); errs.push(`已在 ${cfg.contractPath} 生成后端要求清单骨架：请先按原型现状补齐每个字段与计算，再重跑 init`); }
    else if (readFileSync(cp, 'utf8') === CONTRACT_SKELETON(cfg.runtag)) errs.push(`后端要求清单 ${cfg.contractPath} 还是原样骨架：请先按原型现状补齐，再重跑 init`);
    if (rubric != null) { terms = glossaryTerms(rubric); if (terms == null) { errs.push('原型模式的验收标准要有「## 术语表」一节（每行 `- 词：含义`）'); terms = []; } }
  }
  // 5～6. 参考图与续跑来源
  for (const r of cfg.refImages) if (!r || !r.path || !existsSync(resolve(root, r.path))) errs.push(`参考图不存在：${r && r.path}`);
  const contAbs = cfg.continueFrom ? resolve(root, cfg.continueFrom) : null;
  if (contAbs && !existsSync(join(contAbs, 'ledger.json'))) errs.push(`续跑来源没有 ledger.json：${cfg.continueFrom}（先对旧 run 跑 wl.mjs export）`);
  for (const w of warns) say('提醒：' + w);
  if (errs.length) return fail(errs);

  // 7. 清理旧截图
  const cleaned = cleanupOldShots(W, contAbs);
  if (cleaned.length) say(`已清理旧截图：${cleaned.join('、')}`);
  // 8. 基线 smoke
  say('跑基线 smoke …');
  const sm = await runShell(cfg.smokeCmd, { cwd: root });
  if (sm.code !== 0) return fail([`开跑前 smoke 就不过（退出码 ${sm.code}${sm.timedOut ? '，超时' : ''}）：先修好基线。输出末尾：\n${tailLines(sm.out, 40)}`]);
  // 9. 后端健康
  if (cfg.healthUrl) {
    const h = await probeUrl(cfg.healthUrl);
    if (h.status !== 200) return fail([`healthUrl 没返回 200：${cfg.healthUrl}（${h.status ?? h.error}）`]);
  }
  // 10. 浏览器与 url
  const ck = await cap.check({ W, cfg, root });
  if (!ck.ok) return fail([`截图器打不开页面：${ck.error || ck.status}（${cfg.url}）`]);
  // 11. 快照 index 与 r00 树
  const ctx = { W, root, cfg, core, snap: join(W, 'snap'), idx: join(W, 'snap', 'snap.idx') };
  mkdirSync(ctx.snap, { recursive: true });
  if (git(root, ['read-tree', 'HEAD'], { idx: ctx.idx }).code !== 0) gitOk(root, ['read-tree', '--empty'], { idx: ctx.idx });
  const r00 = snapshotTree(ctx);
  writeFileSync(join(ctx.snap, 'r00.tree'), r00 + '\n');
  writeFileSync(join(ctx.snap, 'green.tree'), r00 + '\n');
  writeFileSync(join(ctx.snap, 'r00.states'), statesHash(ctx) + '\n');
  // 12. 起点图（同时是配方体检）
  say('截起点图 r00 …');
  const s0 = await cap.shoot({ W, round: 0, cfg, root });
  if (s0.failedStates.length) {
    const man = readJson(s0.manifest);
    return fail(['起点图有失败态，配方要先修好：', ...man.states.filter(s => !s.ok).map(s => `  ${s.state}：${s.error}`)]);
  }
  // 13. 缩略总览（主会话开跑前只看这一张）
  const contactPng = await cap.contact({ W, round: 0, cfg, root });
  // 14. 冻结标准、写 goal.md、补默认值写回 args.json、生成 workflow.js
  writeFileSync(frozen, readFileSync(rubricSrc, 'utf8'));
  writeFileSync(join(W, 'goal.md'), renderGoal(cfg));
  const back = { ...cfg };
  for (const k of [...DERIVED_KEYS, 'debug']) delete back[k];
  writeFileSync(join(W, 'args.json'), JSON.stringify(back, null, 2) + '\n');
  const seed = contAbs ? core.toSeed(readJson(join(contAbs, 'ledger.json'), '续跑来源 ledger.json')) : null;
  // start：起点评审用的 r00 结果，直接注入、不经 LLM 转交
  const injected = { v: 1, args: back, seed, derived: { terms, root }, start: { okStates: s0.okStates, errorStates: s0.errorStates, manifest: s0.manifest } };
  const src = buildWorkflowSource(readFileSync(TEMPLATE, 'utf8'), injected);
  checkWorkflowSyntax(src);
  const chk = core.validateArgs(injected.args, injected.derived);
  if (chk.errors.length) return fail(chk.errors);
  if (seed) core.initState(chk.cfg, seed);                    // seed 版本不认识时在这里就暴露
  writeFileSync(join(W, 'workflow.js'), src);
  say(`OK：${relative(root, W)} 已就绪（${states.length} 个态，r00 全部截成功${seed ? `；续跑，轮号从 ${rtag(seed.round + 1)} 起` : ''}）。`);
  say(`下一步：1) Read ${contactPng} 确认截到的是想要的画面；2) Workflow({ scriptPath: "${join(W, 'workflow.js')}" })，不传 args；`);
  say(`        3) 启动后立刻 node ${join(HERE, 'wl.mjs')} attach ${W} <runId> <Transcript dir>`);
  return 0;
}
function fail(errs) {
  console.error('init 未通过：');
  for (const e of errs) console.error('- ' + e);
  return 1;
}

// ── verify ──
async function copyJournalForVerify(ctx, N, full) {
  const { W } = ctx;
  try {
    const rp = join(W, 'run.json');
    if (existsSync(rp)) {
      const rj = readJson(rp, 'run.json'), src = rj.transcriptDir && join(rj.transcriptDir, 'journal.jsonl');
      if (src && existsSync(src)) { copyFileSync(src, join(W, 'journal.jsonl')); return true; }
      full.notes.push(`run.json 指向的 journal 不存在：${src}`);
      return false;
    }
    if (N < 2) return false;                                   // 第 1 轮 verify 的结果还没写进 journal，认不出
    const hits = journalsByContent(W, 24 * 3600 * 1000);
    if (hits.length === 1) { copyFileSync(hits[0], join(W, 'journal.jsonl')); writeRunJson(W, hits[0], 'content'); return true; }
    full.notes.push(hits.length ? `有 ${hits.length} 份 journal 含本运行目录的截图路径，没有复制：${hits.join('、')}` : '没找到含本运行目录截图路径的 journal');
  } catch (e) { full.notes.push('复制 journal 失败：' + e.message); }
  return false;
}
async function restartBackend(ctx, N, full) {
  const { cfg, root, W } = ctx;
  if (!cfg.restartCmd || !cfg.healthUrl) return { ok: false, note: '缺 restartCmd 或 healthUrl，无法重启后端' };
  const u = new URL(cfg.healthUrl), port = Number(u.port || (u.protocol === 'https:' ? 443 : 80));
  const old = listenPids(port);
  for (const pid of old) { try { process.kill(pid, 'SIGTERM'); } catch { /* 已退出 */ } }
  if (!(await waitUntil(() => listenPids(port).length === 0, 10000))) {
    for (const pid of listenPids(port).filter(p => old.includes(p))) { try { process.kill(pid, 'SIGKILL'); } catch { /* 已退出 */ } }
    await waitUntil(() => listenPids(port).length === 0, 5000);
  }
  const log = join(W, 'snap', `restart-${rtag(N)}.log`), fd = openSync(log, 'a');
  const child = spawn('/bin/bash', ['-c', cfg.restartCmd], { cwd: root, detached: true, stdio: ['ignore', fd, fd] });
  child.unref(); closeSync(fd);
  let exitCode = null, now = [], ok = false;
  child.on('exit', c => { exitCode = c; });
  // 返回 200 且端口上的监听进程号换了才算成功（防把旧进程当成新进程）；restartCmd 非 0 退出且端口没人监听就不再等
  await waitUntil(async () => {
    const h = await probeUrl(cfg.healthUrl, 3000);
    now = listenPids(port);
    ok = h.status === 200 && now.length > 0 && !now.some(p => old.includes(p));
    return ok || (exitCode != null && exitCode !== 0 && now.length === 0);
  }, 90000, 500);
  const r = { ok, port, oldPids: old, newPids: now, log };
  if (!ok) r.note = `健康检查没通过或监听进程号没变${exitCode != null ? `（restartCmd 已退出，退出码 ${exitCode}）` : ''}；日志末尾：\n${tailLines(readIf(log) || '', 20)}`;
  full.restart = r;
  return r;
}
// verify 分前台与 worker：worker detached 运行，跑完把短结果行写进 snap/rNN.verify.out 再删锁；
// 前台（与 wait）只轮询这个文件。这样 smoke 跑得再久，回滚也不会在 Bash 超时时被杀在半路。
const verifyFiles = (ctx, N) => { const b = join(ctx.snap, `${rtag(N)}.verify`); return { out: b + '.out', lock: b + '.lock', log: b + '.log' }; };
const pidAlive = pid => { try { process.kill(pid, 0); return true; } catch (e) { return e.code === 'EPERM'; } };
const lockAlive = lock => { const t = readIf(lock); return !!t && pidAlive(Number(t)); };
function verifyArgsOf(o) {
  const N = Number(o.round), kind = o.kind;
  if (!Number.isInteger(N) || N < 1) throw new Error('--round 要是正整数');
  if (!['frontend', 'backend', 'data', 'none'].includes(kind)) throw new Error('--kind 只能是 frontend / backend / data / none');
  return { N, kind };
}
async function cmdVerify(Warg, o) {
  if (o.worker) return verifyWorker(Warg, o);
  const ctx = ctxOf(Warg), { N, kind } = verifyArgsOf(o), F = verifyFiles(ctx, N);
  mkdirSync(ctx.snap, { recursive: true });
  let child = null;
  // 同一轮已经跑完或正在跑：不再起第二个（重跑会拿已退回的工作区重拍快照，搞乱 pre 树）
  if (!existsSync(F.out) && !lockAlive(F.lock)) {
    const fd = openSync(F.log, 'a');
    const argv = [SELF, 'verify', ctx.W, '--round', String(N), '--kind', kind, ...(o.refreshed ? ['--refreshed'] : []), ...(o.noChangeHint ? ['--no-change-hint'] : []), '--worker'];
    child = spawn(process.execPath, argv, { cwd: ctx.root, detached: true, stdio: ['ignore', fd, fd] });
    child.unref(); closeSync(fd);
    writeFileSync(F.lock, String(child.pid));
  }
  return awaitVerify(ctx, N, o, child);
}
async function cmdWait(Warg, o) {
  const ctx = ctxOf(Warg), N = Number(o.round), F = verifyFiles(ctx, N);
  if (!Number.isInteger(N) || N < 1) throw new Error('用法：wl.mjs wait <W> --round N');
  if (!existsSync(F.out) && !existsSync(F.lock)) throw new Error(`第 ${N} 轮没有在跑的 verify（先跑 wl.mjs verify）`);
  return awaitVerify(ctx, N, o, null);
}
/** 等 worker 写出结果行：等到就打印（前面附上进度日志），超时打印 pending，worker 死了打印 error */
async function awaitVerify(ctx, N, o, child) {
  const F = verifyFiles(ctx, N), end = performance.now() + (o.waitMs != null ? Number(o.waitMs) : VERIFY_WAIT_MS);
  let exited = false;
  if (child) child.on('exit', () => { exited = true; });
  const logTail = () => { const t = tailLines(readIf(F.log) || '', 30); if (t.trim()) say(t); };
  for (;;) {
    if (existsSync(F.out)) { logTail(); say(readFileSync(F.out, 'utf8').trim()); return 0; }
    if (exited || !lockAlive(F.lock)) {
      await sleep(300);                                       // worker 先写结果再删锁，再看一眼
      if (existsSync(F.out)) continue;
      logTail(); say(JSON.stringify({ round: N, error: `verify worker 已退出但没有写出结果，详情见 ${F.log}` })); return 0;
    }
    if (performance.now() > end) { say(JSON.stringify({ pending: true, round: N })); return 0; }
    await sleep(500);
  }
}
async function verifyWorker(Warg, o) {
  const ctx = ctxOf(Warg), { N } = verifyArgsOf(o), F = verifyFiles(ctx, N);
  const emit = line => { writeFileSync(F.out + '.tmp', line + '\n'); renameSync(F.out + '.tmp', F.out); };
  try { await doVerify(ctx, o, emit); }
  catch (e) { emit(JSON.stringify({ round: N, error: 'verify 异常：' + (e && e.message || e) })); }
  finally { rmSync(F.lock, { force: true }); }
  return 0;
}
async function doVerify(ctx, o, emit) {
  const { W, root, cfg, core } = ctx;
  const { N, kind } = verifyArgsOf(o);
  const rt = rtag(N), log = m => say(`[verify ${rt}] ${m}`);
  mkdirSync(ctx.snap, { recursive: true });
  const full = { round: N, kind, refreshed: !!o.refreshed, noChangeHint: !!o.noChangeHint, notes: [] };
  const short = { round: N, kind, kindAdjusted: null, envOk: true, noChange: false, journalCopied: false, snapOk: false, changedCount: 0, schemeTouched: [],
    smoke: { pass: null, flaky: false, rolledBack: false, envBroken: false }, refreshOk: null, capture: null, manifest: join(W, 'shots', `${rt}_manifest.json`) };
  const finish = () => {
    full.short = short;
    writeFileSync(join(ctx.snap, `${rt}.verify.json`), JSON.stringify(full, null, 2));
    short.sig = core.canonHash(short);                        // 签名覆盖除 sig 以外的全部短字段
    emit(JSON.stringify(short));                              // 结果行只经 .out 交给前台，不进进度日志（免得打印两遍）
    return 0;
  };
  // 0. 留证与环境
  short.journalCopied = await copyJournalForVerify(ctx, N, full);
  log('探 url …');
  let env = await probeUrl(cfg.url);
  for (let t = 0; !env.ok && t < 15; t++) { await sleep(2000); env = await probeUrl(cfg.url); }   // dev server 瞬断几秒不该停掉整个 run
  full.env = env;
  if (!env.ok) { short.envOk = false; full.notes.push(`url 不可达：${cfg.url}`); return finish(); }
  // 1. 快照
  let cur = null, pre = null, changed = [];
  try {
    cur = snapshotTree(ctx);
    writeFileSync(join(ctx.snap, `${rt}.tree`), cur + '\n');
    pre = preTree(ctx, N);
    if (!pre) throw new Error('找不到开工前的树（snap/r00.tree 缺失）');
    changed = diffTrees(ctx, pre, cur);
    short.snapOk = true;
  } catch (e) { full.notes.push('快照失败：' + e.message); }
  short.changedCount = changed.length;
  full.changed = changed.slice(0, 50); full.changedCount = changed.length; full.preTree = pre; full.tree = cur;
  const sh = statesHash(ctx);
  writeFileSync(join(ctx.snap, `${rt}.states`), sh + '\n');
  if (cfg.mode === 'prototype') {
    const sch = cfg.schemeFiles.map(f => relRoot(root, f));
    short.schemeTouched = changed.map(c => c.path).filter(p => sch.some(s => p === s || p.startsWith(s.replace(/\/$/, '') + '/'))).slice(0, 10);
  }
  // 2. smoke：红先原样复测一次；仍红就按快照只退回本轮改动，再复跑区分「改坏了」与「环境坏了」
  log('跑 smoke …');
  full.smoke = [];
  const smoke = async label => { const r = await runShell(cfg.smokeCmd, { cwd: root }); full.smoke.push({ label, code: r.code, timedOut: r.timedOut, tail: tailLines(r.out, 40) }); return r.code === 0; };
  let green = await smoke('首跑');
  if (!green && await smoke('复测')) { green = true; short.smoke.flaky = true; }
  if (green) {
    short.smoke.pass = true;
    if (cur) writeFileSync(join(ctx.snap, 'green.tree'), cur + '\n');
  } else {
    short.smoke.pass = false;
    if (!short.snapOk) { full.notes.push('smoke 红而快照不可用：没有退回，工作区停在本轮改动后的状态'); return finish(); }
    const paths = changed.map(c => c.path);
    if (!paths.length) { short.smoke.envBroken = true; full.notes.push('本轮没有改动而 smoke 仍红：环境或基线坏了'); return finish(); }
    log(`smoke 红，退回本轮改动（${paths.length} 个路径）…`);
    writeFileSync(join(ctx.snap, `${rt}.rejected.diff`), gitOk(root, ['diff', '--no-renames', pre, cur, '--', ...paths]));
    full.rollback = restoreTo(ctx, pre, paths);
    if (await smoke('退回后')) {
      const restored = snapshotTree(ctx);
      writeFileSync(join(ctx.snap, `${rt}.restored.tree`), restored + '\n');
      writeFileSync(join(ctx.snap, 'green.tree'), restored + '\n');
      short.smoke.rolledBack = true;
    } else {
      full.putBack = restoreTo(ctx, cur, paths);               // 不是本轮改动造成的：把改动放回去
      short.smoke.envBroken = true;
      full.notes.push('退回本轮改动后 smoke 仍红：环境或基线坏了；本轮改动已放回');
    }
    return finish();
  }
  // 2b. 本轮无改动：评审结果必然与上一轮相同，不截图不评审
  const prevStates = readIf(join(ctx.snap, `${rtag(N - 1)}.states`)) || readIf(join(ctx.snap, 'r00.states'));
  if (short.snapOk && !changed.length && sh === prevStates && o.noChangeHint && ['frontend', 'none'].includes(kind)) {
    short.noChange = true; return finish();
  }
  // 3. 刷新
  let eff = kind;
  const uiRel = relRoot(root, cfg.uiDir).replace(/\/$/, '') + '/';
  if (['frontend', 'none'].includes(kind) && cfg.restartCmd && changed.some(c => SRC_EXT.test(c.path) && !c.path.startsWith(uiRel))) { eff = 'backend'; short.kindAdjusted = 'backend'; }
  let ref = { ok: true };
  const restart = async () => { try { return await restartBackend(ctx, N, full); } catch (e) { return { ok: false, note: '重启后端失败：' + e.message }; } };
  if (eff === 'backend') { log('重启后端 …'); ref = await restart(); }
  else if (eff === 'data') {
    const cmd = cfg.refreshDataCmd;
    if (!cmd) ref = { ok: false, note: '没配 refreshDataCmd，无法刷新数据' };
    else if (/\.md$/i.test(cmd.trim())) ref = o.refreshed ? { ok: true, note: '已由 verify 代理按说明文件刷新' } : { ok: false, note: `需先按说明文件 ${cmd} 刷新数据，再带 --refreshed 跑本命令` };
    else {
      log('重启后端并刷新数据 …');
      ref = await restart();
      if (ref.ok) { const r = await runShell(cmd, { cwd: root }); ref = { ok: r.code === 0, note: r.code === 0 ? '' : `refreshDataCmd 退出码 ${r.code}`, tail: tailLines(r.out, 40) }; }
    }
  }
  short.refreshOk = !!ref.ok; full.refresh = { kind: eff, ...ref };
  if (!ref.ok) return finish();
  // 4. 截图（进程内调用截图器）
  try {
    const cap = await import(pathToFileURL(join(HERE, 'capture.mjs')).href);
    const s = await cap.shoot({ W, round: N, cfg, root, log: m => say(m) });
    short.capture = { okStates: s.okStates, failedStates: s.failedStates, errorStates: s.errorStates, newErrors: s.newErrors };
    full.capture = s;
  } catch (e) { full.notes.push('截图器失败：' + e.message); }
  return finish();
}

// ── intake / diff / restore / attach ──
async function cmdIntake(Warg, o) {
  const W = resolve(Warg), dir = join(W, 'control');
  // 上一轮的 verify worker 若还在跑（verify 代理没等到结果就交回了），它可能还在退回工作区：先等它结束
  const snap = join(W, 'snap'), end = performance.now() + (o.waitMs != null ? Number(o.waitMs) : INTAKE_WAIT_MS);
  const running = () => (existsSync(snap) ? readdirSync(snap) : []).filter(f => /^r\d\d\.verify\.lock$/.test(f))
    .filter(f => !existsSync(join(snap, f.replace(/\.lock$/, '.out'))) && lockAlive(join(snap, f))).map(f => ({ round: +f.slice(1, 3), pid: Number(readIf(join(snap, f))) }));
  while (running().length && performance.now() < end) await sleep(1000);
  const verifyRunning = running()[0] || null;
  const done = new Set(String(o.done || '').split(',').map(s => s.trim()).filter(Boolean));
  const hints = [], overrides = [];
  const files = existsSync(dir) ? readdirSync(dir).sort() : [];
  for (const f of files) {
    if (/^hint-.*\.md$/.test(f) && !done.has(f)) hints.push({ key: f, text: readFileSync(join(dir, f), 'utf8') });
    if (/^override-.*\.json$/.test(f)) {
      let arr;
      try { const v = JSON.parse(readFileSync(join(dir, f), 'utf8')); arr = Array.isArray(v) ? v : [v]; }
      catch (e) { const key = `${f}#0`; if (!done.has(key)) overrides.push({ key, id: null, action: 'invalid', requiredStates: [], note: `JSON 解析失败：${e.message}` }); continue; }
      arr.forEach((x, k) => {
        const key = `${f}#${k}`;
        if (done.has(key)) return;
        overrides.push({ key, id: isObj(x) && typeof x.id === 'string' ? x.id : null, action: isObj(x) && typeof x.action === 'string' ? x.action : 'invalid',
          requiredStates: isObj(x) && Array.isArray(x.requiredStates) ? x.requiredStates : [], note: isObj(x) && typeof x.note === 'string' ? x.note : '' });
      });
    }
  }
  say(JSON.stringify({ verifyRunning, hints, overrides }, null, 2));
  return 0;
}
function latestTree(ctx) {
  const ns = existsSync(ctx.snap) ? readdirSync(ctx.snap).map(f => f.match(/^r(\d\d)\.tree$/)).filter(Boolean).map(m => +m[1]).filter(n => n > 0) : [];
  if (!ns.length) return treeOf(ctx, 'r00');
  const n = Math.max(...ns);
  return treeOf(ctx, `${rtag(n)}.restored`) || treeOf(ctx, rtag(n));
}
function cmdDiff(Warg, o) {
  const ctx = ctxOf(Warg);
  let a, b;
  if (o.run) { a = treeOf(ctx, 'r00'); b = latestTree(ctx); }
  else {
    const N = Number(o.round);
    if (!Number.isInteger(N) || N < 1) throw new Error('用法：wl.mjs diff <W> --round N | --run [-- 路径…]');
    a = preTree(ctx, N); b = treeOf(ctx, rtag(N));
    if (!b) throw new Error(`第 ${N} 轮还没有快照（snap/${rtag(N)}.tree）`);
  }
  if (!a || !b) throw new Error('快照不全，无法 diff');
  process.stdout.write(gitOk(ctx.root, ['diff', '--no-renames', a, b, ...(o.paths.length ? ['--', ...o.paths] : [])]));
  return 0;
}
function cmdRestore(Warg, o) {
  const ctx = ctxOf(Warg);
  const to = o.to;
  if (!to) throw new Error('用法：wl.mjs restore <W> --to rNN|green|r00|before-restore [--dry-run]');
  const target = /^r\d\d$/.test(to) ? treeOf(ctx, `${to}.restored`) || treeOf(ctx, to) : treeOf(ctx, to);
  if (!target) throw new Error(`找不到目标快照 snap/${to}.tree`);
  const cur = snapshotTree(ctx);
  const paths = diffTrees(ctx, target, cur);
  say(`目标 ${to}（${target.slice(0, 10)}）与当前工作区之间变了 ${paths.length} 个路径（不含截图配方、验收标准、运行目录）：`);
  for (const c of paths) say(`  ${c.status}\t${c.path}`);
  if (o.dryRun) { say('（--dry-run：没有改动任何文件）'); return 0; }
  writeFileSync(join(ctx.snap, 'before-restore.tree'), cur + '\n');
  const r = restoreTo(ctx, target, paths.map(c => c.path));
  say(`已恢复 ${r.restored.length} 个、删除 ${r.deleted.length} 个。撤销这次退回：wl.mjs restore ${ctx.W} --to before-restore`);
  return 0;
}
function cmdAttach(Warg, runId, transcriptDir) {
  if (!Warg || !runId || !transcriptDir) throw new Error('用法：wl.mjs attach <W> <runId> <transcriptDir>');
  const W = resolve(Warg), td = resolve(transcriptDir);
  if (!existsSync(td)) throw new Error(`transcriptDir 不存在：${td}`);
  writeFileSync(join(W, 'run.json'), JSON.stringify({ runId, transcriptDir: td, foundBy: 'attach' }, null, 2));
  say(`已写 ${join(W, 'run.json')}`);
  return 0;
}

// ── status / export ──
function loadView(ctx, journalOpt) {
  const j = findJournal(ctx.W, { journal: journalOpt });
  return { j, view: parseJournal(readFileSync(j.path, 'utf8')) };
}
function cmdStatus(Warg, o) {
  const ctx = ctxOf(Warg);
  const { j, view } = loadView(ctx, o.journal);
  const rec = readRunRecord(ctx.W);
  const ended = rec && rec.status && rec.status !== 'running';
  const rep = ctx.core.replay(ctx.cfg, ctx.injected.seed, view, ended ? 'end' : 'live', ctx.injected.start);
  if (ended && rep.S.exit === 'interrupted' && isObj(rec.result) && rec.result.exitReason) ctx.core.markExit(rep.S, rec.result.exitReason, rec.result.exitDetail);
  const S = rep.S, cfg = ctx.cfg;
  say(`run：${cfg.runtag}　journal：${j.path}（${j.source}${j.note ? '；' + j.note : ''}）　已派代理：${rep.agentsUsed}`);
  say(S.exit ? `已结束：${S.exit}（${ctx.core.EXIT_TEXT[S.exit] || ''}）${S.exitDetail ? '。' + S.exitDetail : ''}` : `进行中：${rep.stage || '等待下一步'}`);
  say('\n每轮走势：'); for (const l of ctx.core.compactLedger(S).rounds) say('  ' + l);
  const open = S.issues.filter(i => i.status === 'open' && i.severity === 'must');
  const conf = open.filter(i => !i.unverifiable), gaps = open.filter(i => i.unverifiable);
  say(`\n开着的确证 must（${conf.length}）：`); for (const i of conf) say(`  - ${i.id} [${i.lens}] ${i.title}${i.state ? `（态 ${i.state}）` : ''}${i.needsDecision ? `（${i.needsDecision}）` : ''}`);
  if (gaps.length) { say(`取证缺口（${gaps.length}）：`); for (const i of gaps) say(`  - ${i.id} [${i.lens}] ${i.title}：需要态 ${i.requiredStates.join('、')}`); }
  const last = [...S.rounds].reverse().find(r => r.reviewed);
  say('子项：' + (cfg.goalSubgoals.map(g => `${g.id}=${last ? last.sg[g.id] : 'pending'}`).join('　') || '无'));
  if (S.directions.length) { say('方向题：'); for (const d of S.directions) say(`  - ${d.id} ${d.title}`); }
  if (S.toMain.length) { say('给主会话的留言：'); for (const m of S.toMain) say(`  - ${rtag(m.round)} ${m.from}：${m.text}`); }
  if (S.overrideErrors.length) { say('override 错误：'); for (const e of S.overrideErrors) say(`  - ${e.key}：${e.error}`); }
  return 0;
}
function renderFromLedger(L) {
  const led = isObj(L) && isObj(L.ledger) ? L.ledger : L;
  const out = [`# web-loop 运行总结（简版，来自 Workflow 返回值；journal 读不到）`, '', `- 结论：\`${led.exit || L.exitReason || '未知'}\`${L.exitDetail ? '。' + L.exitDetail : ''}`, `- 最后一轮：${rtag(led.round || 0)}`, '',
    '## 条目', '', '| id | 角度 | 级别 | 状态 | 待取证 | 标题 | 态 |', '|---|---|---|---|---|---|---|'];
  for (const i of led.issues || []) out.push(`| ${i.id} | ${i.lens} | ${i.severity} | ${i.status} | ${i.unverifiable ? '是' : ''} | ${String(i.title).replace(/\|/g, '/')} | ${i.state || ''} |`);
  out.push('', '## 子项', '', ...Object.entries(led.subgoals || {}).map(([k, v]) => `- ${k}：${v}`), '', '## 方向题', '', ...(led.directions || []).map(d => `- ${d}`), '', '## 每轮走势', '', ...(led.rounds || []).map(r => `- ${r}`));
  return out.join('\n') + '\n';
}
// 方向题的证据图复制到 <W>/evidence/<方向题 id>/：init 清理旧 run 只删 shots/，证据图要留到用户拍板之后。
// 本 run 提的：从 <W>/shots 按 shotTag 取，态名带 "__" 的按单张裁剪图取，否则取整页图加它的全部裁剪图。
// 续跑延续下来的（shotTag 为空）：从上一个 run 的 evidence/ 取（evidenceFrom，相对 repo root）。
// 取到图时先清空目标目录再复制（同一运行目录重新 init 后编号可能重复，不混进旧图）；一张都取不到时沿用目录里已有的。
// 返回 { 方向题 id: [相对 W 的路径] }，交给 renderSummary 嵌图。
export function copyEvidence(W, root, directions) {
  const shots = join(W, 'shots'), out = {};
  const have = existsSync(shots) ? readdirSync(shots) : [];
  for (const d of directions || []) {
    const dest = join(W, 'evidence', d.id), src = [];
    if (d.shotTag) {
      for (const raw of Array.isArray(d.states) ? d.states : []) {
        const s = String(raw).replace(/^r\d\d_/, '').replace(/\.png$/, '');   // 评审有时写成文件名
        const base = `${d.shotTag}_${s}`;
        for (const f of have) if (f === `${base}.png` || (!s.includes('__') && f.startsWith(`${base}__`) && f.endsWith('.png'))) src.push(join(shots, f));
      }
    } else if (d.evidenceFrom) {
      const from = resolve(root, d.evidenceFrom);
      if (from !== dest && existsSync(from)) for (const f of readdirSync(from)) if (f.endsWith('.png')) src.push(join(from, f));
    }
    if (src.length) {
      rmSync(dest, { recursive: true, force: true });
      mkdirSync(dest, { recursive: true });
      for (const f of src) copyFileSync(f, join(dest, basename(f)));
    }
    const got = existsSync(dest) ? readdirSync(dest).filter(f => f.endsWith('.png')).sort() : [];
    if (got.length) out[d.id] = got.map(f => `evidence/${d.id}/${f}`);
  }
  return out;
}
async function cmdExport(Warg, o) {
  if (o.fromLedger) {
    const W = resolve(Warg);
    writeFileSync(join(W, 'SUMMARY.md'), renderFromLedger(readJson(resolve(o.fromLedger), '--from-ledger 文件')));
    say(join(W, 'SUMMARY.md'));
    return 0;
  }
  const ctx = ctxOf(Warg);
  const { W, cfg, core } = ctx;
  const j = findJournal(W, { journal: o.journal });
  const local = join(W, 'journal.jsonl');
  if (j.raw && resolve(j.path) !== local) copyFileSync(j.path, local);
  const rrp = runRecordPath(W);
  if (rrp) copyFileSync(rrp, join(W, 'run-record.json'));
  const view = parseJournal(readFileSync(existsSync(local) ? local : j.path, 'utf8'));
  const rep = core.replay(cfg, ctx.injected.seed, view, 'end', ctx.injected.start);
  const S = rep.S, rec = readRunRecord(W);
  if (S.exit === 'interrupted' && rec && isObj(rec.result) && rec.result.exitReason) core.markExit(S, rec.result.exitReason, rec.result.exitDetail);
  let changed = null;
  try { const a = treeOf(ctx, 'r00'), b = latestTree(ctx); if (a && b) changed = diffTrees(ctx, a, b); } catch { /* 快照不可用 */ }
  const runId = existsSync(join(W, 'run.json')) ? readJson(join(W, 'run.json')).runId : null;
  writeFileSync(join(W, 'ledger.json'), JSON.stringify({ ...S, meta: { runtag: cfg.runtag, runId, exitReason: S.exit, agentsUsed: rep.agentsUsed } }, null, 2));
  const evidence = copyEvidence(W, ctx.root, S.directions);
  writeFileSync(join(W, 'SUMMARY.md'), core.renderSummary(cfg, S, { runId, agentsUsed: rep.agentsUsed, changed, journalNote: j.note, evidence }));
  for (const [label, r] of Object.entries(view.results)) {
    let m, dir, name;
    if ((m = label.match(/^review-(.+)-r(\d\d)$/))) { dir = join(W, 'reviews', `round_${m[2]}`); name = `${m[1]}.json`; }
    else if ((m = label.match(/^(impl|verify)-r(\d\d)$/))) { dir = join(W, 'rounds', `round_${m[2]}`); name = `${m[1]}.json`; }
    else continue;
    mkdirSync(dir, { recursive: true });
    writeFileSync(join(dir, name), JSON.stringify(r, null, 2));
  }
  say(join(W, 'SUMMARY.md'));
  return 0;
}

// ── rubric-diff：复用上次的验收标准时，只把改动给用户过目 ──
// 按标题分节、节内按行集合比（忽略空行与行首尾空白）；改写的一行显示为一删一增。节名带上级标题（文档标题不算），
// 免得各角度下同名的「must」小节并成一节；代码块里的 # 行不算标题。参数可以是文件，也可以是运行目录（取其冻结的 rubric.md）。
function sectionsOf(text) {
  const top = '（第一个标题之前）', out = new Map([[top, []]]), path = [];
  let cur = top, fence = false;
  for (const line of String(text).split('\n')) {
    if (/^\s*(```|~~~)/.test(line)) fence = !fence;
    const m = !fence && line.match(/^(#{1,6})\s+(.*)$/);
    if (m) {
      const lv = m[1].length;
      path.length = lv - 1; path[lv - 1] = m[2].trim();
      cur = path.slice(1).filter(Boolean).join(' › ') || path[0];
      if (!out.has(cur)) out.set(cur, []);
      continue;
    }
    if (line.trim()) out.get(cur).push(line.trim());
  }
  return out;
}
export function rubricDiff(oldText, newText) {
  const A = sectionsOf(oldText), B = sectionsOf(newText), lines = [];
  for (const [h, bl] of B) {
    if (!A.has(h)) { if (bl.length) lines.push(`+ 新增一节「${h}」`, ...bl.map(l => `    + ${l}`)); continue; }
    const al = A.get(h), as = new Set(al), bs = new Set(bl);
    const del = al.filter(l => !bs.has(l)), add = bl.filter(l => !as.has(l));
    if (del.length || add.length) lines.push(`~ 「${h}」`, ...del.map(l => `    - ${l}`), ...add.map(l => `    + ${l}`));
  }
  for (const [h, al] of A) if (!B.has(h) && al.length) lines.push(`- 删掉一节「${h}」`, ...al.map(l => `    - ${l}`));
  return lines;
}
function cmdRubricDiff(a, b) {
  if (!a || !b) { console.error('用法：wl.mjs rubric-diff <旧验收标准或运行目录> <新验收标准或运行目录>'); return 2; }
  const text = p => { const f = resolve(p), r = join(f, 'rubric.md'); return readFileSync(existsSync(r) ? r : f, 'utf8'); };
  const lines = rubricDiff(text(a), text(b));
  say(lines.length ? lines.join('\n') : '两份验收标准没有差别（只比非空行）');
  return 0;
}

// ── CLI ──
function parseArgs(argv) {
  const o = { _: [], paths: [] };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--') { o.paths = argv.slice(i + 1); break; }
    if (a.startsWith('--')) {
      const k = a.slice(2).replace(/-([a-z])/g, (_, c) => c.toUpperCase());
      if (['refreshed', 'noChangeHint', 'run', 'dryRun', 'worker'].includes(k)) o[k] = true;
      else o[k] = argv[++i];
    } else o._.push(a);
  }
  return o;
}
async function main(argv) {
  const o = parseArgs(argv), [cmd, W, ...rest] = o._;
  switch (cmd) {
    case 'init': return cmdInit(W);
    case 'verify': return cmdVerify(W, o);
    case 'wait': return cmdWait(W, o);
    case 'intake': return cmdIntake(W, o);
    case 'diff': return cmdDiff(W, o);
    case 'restore': return cmdRestore(W, o);
    case 'attach': return cmdAttach(W, rest[0], rest[1]);
    case 'status': return cmdStatus(W, o);
    case 'export': return cmdExport(W, o);
    case 'rubric-diff': return cmdRubricDiff(W, rest[0]);
    default:
      console.error('用法：wl.mjs init|verify|wait|intake|diff|restore|attach|status|export|rubric-diff <运行目录> …（见文件头注释）');
      return 2;
  }
}
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main(process.argv.slice(2)).then(code => process.exit(code ?? 0), e => { console.error('ERROR: ' + (e && e.message || e)); process.exit(1); });
}
