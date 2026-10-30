#!/usr/bin/env node
// web-loop 的截图器（node CLI + 可 import）。执行结构化截图配方，评审只读它的产出（浏览器只由这一层持有）。
//   shoot   --workdir W --round N [--only a,b] [--out DIR]   截各态整页图与局部图，写 rNN_manifest.json；最后一行打印 summary JSON
//   check   --workdir W                                      起浏览器打开 url，打印 {ok, status, browser, error}
//   contact --workdir W --round N                            把该轮各态整页图排成缩略总览 rNN_contact.png
// 带 --out 是自查模式：写到 DIR，不和上一份清单比，不签名。只有浏览器起不来或参数错时退出码非 0；
//   有失败态时退出码仍是 0（失败是数据，不是程序错误）。
// 导出纯函数 validateStates / lintStates / matchExpect / computeNewErrors / buildSummary 供 wl.mjs 与测试使用。
import { readFileSync, writeFileSync, existsSync, mkdirSync, readdirSync, rmSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { createRequire } from 'node:module';
import { join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const STEP_KEYS = ['wait', 'eval', 'waitFor', 'click', 'press', 'css', 'pw'];
const NAME_RE = /^[A-Za-z0-9_-]+$/;
const DEFAULT_VIEWPORT = { width: 2560, height: 1440, deviceScaleFactor: 1 };
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
const isObj = x => x != null && typeof x === 'object' && !Array.isArray(x);
const rtag = n => 'r' + String(n).padStart(2, '0');
const firstLine = e => String((e && e.message) || e).split('\n')[0];
const clip = (s, n) => { s = String(s ?? ''); return s.length > n ? s.slice(0, n) + '…' : s; };
const fmt = v => (typeof v === 'string' ? v : v === undefined ? 'undefined' : JSON.stringify(v));
const sleep = ms => new Promise(r => setTimeout(r, ms));

// ── 纯函数 ──
/** 校验截图配方，返回错误列表（空 = 通过） */
export function validateStates(states) {
  const errs = [];
  if (!Array.isArray(states) || !states.length) return ['截图配方要是非空数组'];
  const seen = new Set();
  states.forEach((s, k) => {
    const at = `第 ${k + 1} 个态`;
    if (!isObj(s)) { errs.push(`${at} 不是对象`); return; }
    const name = s.state;
    if (typeof name !== 'string' || !NAME_RE.test(name)) errs.push(`${at} 的 state 名不合法：${fmt(name)}（只能用字母、数字、_、-）`);
    else if (seen.has(name)) errs.push(`态名重复：${name}`);
    else seen.add(name);
    const tag = typeof name === 'string' ? `态 ${name}` : at;
    for (const k2 of ['note', 'path', 'probe']) if (s[k2] != null && typeof s[k2] !== 'string') errs.push(`${tag} 的 ${k2} 要是字符串`);
    if (s.fullPage != null && typeof s.fullPage !== 'boolean') errs.push(`${tag} 的 fullPage 要是布尔值`);
    if (s.viewport != null) {
      if (!isObj(s.viewport)) errs.push(`${tag} 的 viewport 要是对象`);
      else for (const d of ['width', 'height', 'deviceScaleFactor']) if (s.viewport[d] != null && !(typeof s.viewport[d] === 'number' && s.viewport[d] > 0)) errs.push(`${tag} 的 viewport.${d} 要是正数`);
    }
    if (s.steps != null && !Array.isArray(s.steps)) errs.push(`${tag} 的 steps 要是数组`);
    (Array.isArray(s.steps) ? s.steps : []).forEach((st, i) => {
      const keys = isObj(st) ? Object.keys(st) : [];
      if (keys.length !== 1) { errs.push(`${tag} 的 step ${i + 1} 要恰好一个键`); return; }
      const [key] = keys, v = st[key];
      if (!STEP_KEYS.includes(key)) errs.push(`${tag} 的 step ${i + 1} 用了未知的键 ${key}（只认 ${STEP_KEYS.join(' / ')}）`);
      else if (key === 'wait' ? !(typeof v === 'number' && v >= 0) : typeof v !== 'string' || !v.trim()) errs.push(`${tag} 的 step ${i + 1}（${key}）取值不对`);
    });
    if (s.expect != null) {
      if (!isObj(s.expect)) errs.push(`${tag} 的 expect 要是对象`);
      if (typeof s.probe !== 'string' || !s.probe.trim()) errs.push(`${tag} 写了 expect 却没有 probe`);
    }
    if (s.crops != null && !Array.isArray(s.crops)) errs.push(`${tag} 的 crops 要是数组`);
    const cn = new Set();
    (Array.isArray(s.crops) ? s.crops : []).forEach((c, i) => {
      if (!isObj(c) || typeof c.name !== 'string' || !NAME_RE.test(c.name)) { errs.push(`${tag} 的 crop ${i + 1} 名不合法`); return; }
      if (cn.has(c.name)) errs.push(`${tag} 的 crop 名重复：${c.name}`);
      cn.add(c.name);
      const hasSel = typeof c.selector === 'string' && c.selector.trim(), hasClip = isObj(c.clip);
      if (!!hasSel === !!hasClip) errs.push(`${tag} 的 crop ${c.name} 要在 selector 与 clip 里恰好写一个`);
      if (hasClip && !['x', 'y', 'width', 'height'].every(d => typeof c.clip[d] === 'number')) errs.push(`${tag} 的 crop ${c.name} 的 clip 要有数字 x、y、width、height`);
    });
  });
  return errs;
}
/** 配方的写法提醒（不算错误）：禁止用 || 写兜底、探针要记录目标、能断言的写 expect */
export function lintStates(states) {
  const out = [];
  for (const s of Array.isArray(states) ? states : []) {
    if (!isObj(s)) continue;
    const texts = [s.probe, ...(Array.isArray(s.steps) ? s.steps.flatMap(st => (isObj(st) ? Object.values(st).filter(v => typeof v === 'string') : [])) : [])];
    if (texts.some(t => typeof t === 'string' && t.includes('||'))) out.push(`态 ${s.state} 的配方里有 ||：配方禁止用 || 写兜底（选错目标会被悄悄掩盖）`);
    if (s.probe && s.expect == null) out.push(`态 ${s.state} 有 probe 没有 expect：能断言的请写进 expect`);
  }
  return out;
}
const getPath = (obj, k) => (isObj(obj) && Object.prototype.hasOwnProperty.call(obj, k) ? obj[k]
  : k.includes('.') ? k.split('.').reduce((o, p) => (o != null && typeof o === 'object' ? o[p] : undefined), obj) : isObj(obj) ? obj[k] : undefined);
/**
 * 对探针结果做部分深比较：expected 里出现的键必须相等，没出现的不管；数组按位比较且长度相等；键可写成 a.b 读嵌套路径。
 * 一致返回 null；不一致返回 {path, expected, actual, message}。
 */
export function matchExpect(actual, expected, path = '') {
  const mism = () => ({ path: path || '(根)', expected, actual, message: `expect 不符：${path || '(根)'} 期望 ${fmt(expected)} 实际 ${fmt(actual)}` });
  if (isObj(expected)) {
    if (actual == null || typeof actual !== 'object') return mism();
    for (const k of Object.keys(expected)) { const r = matchExpect(getPath(actual, k), expected[k], path ? `${path}.${k}` : k); if (r) return r; }
    return null;
  }
  if (Array.isArray(expected)) {
    if (!Array.isArray(actual) || actual.length !== expected.length) return mism();
    for (let i = 0; i < expected.length; i++) { const r = matchExpect(actual[i], expected[i], `${path}[${i}]`); if (r) return r; }
    return null;
  }
  return Object.is(actual, expected) || actual === expected ? null : mism();
}
/** 报错文本归一：取首行，去掉 :行:列 数字 */
const normErr = s => String(s).split('\n')[0].replace(/:\d+(:\d+)?/g, '').trim();
/**
 * 新出现的页面报错：某态在上一份清单里存在，而这一份的 pageErrors 里出现了上一份没有的文本。
 * 上一份缺失、或上一份没有这个态，都不算（开跑前就有的报错不自动立条目）。
 */
export function computeNewErrors(prev, cur) {
  if (!isObj(prev) || !Array.isArray(prev.states) || !isObj(cur) || !Array.isArray(cur.states)) return [];
  const before = new Map(prev.states.filter(isObj).map(s => [s.state, new Set((s.pageErrors || []).map(normErr))]));
  return cur.states.filter(s => isObj(s) && before.has(s.state) && (s.pageErrors || []).some(e => !before.get(s.state).has(normErr(e)))).map(s => s.state);
}
export function buildSummary(manifest, prev = null) {
  const st = Array.isArray(manifest && manifest.states) ? manifest.states : [];
  return { okStates: st.filter(s => s.ok).map(s => s.state), failedStates: st.filter(s => !s.ok).map(s => s.state),
    errorStates: st.filter(s => (s.pageErrors || []).length).map(s => s.state), newErrors: computeNewErrors(prev, manifest) };
}

// ── 环境 ──
function gitRoot(dir) {
  const r = spawnSync('git', ['-C', dir, 'rev-parse', '--show-toplevel'], { encoding: 'utf8' });
  if (r.status !== 0) throw new Error(`${dir} 不在 git 仓库里`);
  return r.stdout.trim();
}
/** 独立运行时从 <W>/args.json 取参数（init 写回的版本已补默认值） */
function loadCfg(W) {
  const a = JSON.parse(readFileSync(join(W, 'args.json'), 'utf8'));
  return { ...a, viewport: { ...DEFAULT_VIEWPORT, ...(isObj(a.viewport) ? a.viewport : {}) } };
}
function readStates(root, cfg) {
  const p = resolve(root, cfg.statesPath);
  let states;
  try { states = JSON.parse(readFileSync(p, 'utf8')); } catch (e) { throw new Error(`截图配方读不到或不是合法 JSON：${p}：${e.message}`); }
  const errs = validateStates(states);
  if (errs.length) throw new Error('截图配方不合法：\n' + errs.join('\n'));
  return states;
}
/** 从 uiDir 解析 @playwright/test 或 playwright（项目自己的依赖），系统 chrome 优先，起不来退回自带 chromium */
async function launch(root, cfg) {
  const req = createRequire(resolve(root, cfg.uiDir) + '/');
  let chromium = null;
  for (const name of ['@playwright/test', 'playwright']) {
    let p;
    try { p = req.resolve(name); } catch { continue; }
    const mod = await import(pathToFileURL(p).href);
    chromium = mod.chromium || (mod.default && mod.default.chromium);
    if (chromium) break;
  }
  if (!chromium) throw new Error(`在 ${cfg.uiDir} 下解析不到 @playwright/test 或 playwright（先在该目录装依赖）`);
  const args = ['--no-sandbox', '--disable-dev-shm-usage'];
  try { return { browser: await chromium.launch({ channel: 'chrome', args }), name: 'chrome' }; }
  catch (e1) {
    try { return { browser: await chromium.launch({ args }), name: 'chromium' }; }
    catch (e2) { throw new Error(`浏览器起不来：chrome：${firstLine(e1)}；chromium：${firstLine(e2)}`); }
  }
}
async function runStep(page, key, v) {
  if (key === 'wait') return page.waitForTimeout(v);
  if (key === 'eval') return page.evaluate(src => (0, eval)(src), v);
  if (key === 'waitFor') return page.waitForSelector(v, { timeout: 15000 });
  if (key === 'click') return page.click(v, { timeout: 10000 });
  if (key === 'press') return page.keyboard.press(v);
  if (key === 'css') return page.addStyleTag({ content: v });
  if (key === 'pw') return new AsyncFunction('page', v)(page);
}
/**
 * 只对截图这一步重试：Chrome 偶发「Unable to capture screenshot」，重拍即过。最多再试 2 次、间隔 300 毫秒，次数记进 manifest。
 * 超时不重试（多半是元素不可见，重试只会白等）；步骤、探针、expect 的失败是数据，根本不经过这里。
 */
async function withShotRetry(rec, fn) {
  for (let k = 0; ; k++) {
    try { return await fn(); }
    catch (e) {
      if (k >= 2 || /Timeout \d+ms exceeded/.test(String(e && e.message))) throw e;
      rec.shotRetries++;
      await sleep(300);
    }
  }
}
async function shootOne(browser, cfg, st, dir, rt) {
  const vp = { ...cfg.viewport, ...(st.viewport || {}) };
  const ctx = await browser.newContext({ viewport: { width: vp.width, height: vp.height }, deviceScaleFactor: vp.deviceScaleFactor || 1 });
  const page = await ctx.newPage();
  const rec = { state: st.state, note: st.note || '', ok: false, error: null, shot: null, crops: [], probe: null, consoleErrors: [], pageErrors: [], failedRequests: [], shotRetries: 0 };
  page.on('console', m => { if (m.type() === 'error') rec.consoleErrors.push(clip(m.text(), 500)); });
  page.on('pageerror', e => { rec.pageErrors.push(clip((e && (e.stack || e.message)) || String(e), 800)); });
  page.on('requestfailed', r => { rec.failedRequests.push(clip(`${r.method()} ${r.url()} ${(r.failure() && r.failure().errorText) || ''}`, 300)); });
  const base = join(dir, `${rt}_${st.state}`);
  for (const f of [`${base}.png`, `${base}.failed.png`]) rmSync(f, { force: true });
  try {
    const url = cfg.url + (st.path || '');
    try { await page.goto(url, { waitUntil: 'load', timeout: 30000 }); } catch (e) { throw new Error(`打开页面 ${url}：${firstLine(e)}`); }
    const steps = st.steps || [];
    for (let i = 0; i < steps.length; i++) {
      const [key, v] = Object.entries(steps[i])[0];
      try { await runStep(page, key, v); } catch (e) { throw new Error(`step ${i + 1} (${key} ${clip(typeof v === 'string' ? v.split('\n')[0] : v, 60)})：${firstLine(e)}`); }
    }
    if (st.probe) {
      try { rec.probe = await page.evaluate(src => (0, eval)(src), st.probe); } catch (e) { throw new Error(`probe：${firstLine(e)}`); }
      if (st.expect) { const m = matchExpect(rec.probe, st.expect); if (m) throw new Error(m.message); }
    }
    try { await withShotRetry(rec, () => page.screenshot({ path: `${base}.png`, fullPage: !!st.fullPage })); } catch (e) { throw new Error(`截图：${firstLine(e)}`); }
    rec.shot = `${base}.png`;
    for (const c of st.crops || []) {
      const p = `${base}__${c.name}.png`;
      if (c.selector) {
        const loc = page.locator(c.selector);
        if ((await loc.count()) === 0) throw new Error(`crop ${c.name}：选择器 ${c.selector} 找不到`);
        try { await withShotRetry(rec, () => loc.first().screenshot({ path: p, timeout: 10000 })); } catch (e) { throw new Error(`crop ${c.name}：${firstLine(e)}`); }
      } else {
        try { await withShotRetry(rec, () => page.screenshot({ path: p, clip: c.clip })); } catch (e) { throw new Error(`crop ${c.name}：${firstLine(e)}`); }
      }
      rec.crops.push({ name: c.name, path: p });
    }
    rec.ok = true;
  } catch (e) {
    rec.error = String((e && e.message) || e);                // 不吞异常：原始报错就是证据
    rec.crops = []; rec.shot = null;
    rmSync(`${base}.png`, { force: true });
    try { await withShotRetry(rec, () => page.screenshot({ path: `${base}.failed.png`, fullPage: !!st.fullPage })); rec.shot = `${base}.failed.png`; } catch { /* 页面已不可用 */ }
  } finally { await ctx.close().catch(() => {}); }
  return rec;
}
/** 上一份清单：shots/ 里轮号小于 N 的最大一份（含 r00） */
function prevManifest(dir, round) {
  const ns = existsSync(dir) ? readdirSync(dir).map(f => f.match(/^r(\d\d)_manifest\.json$/)).filter(Boolean).map(m => +m[1]).filter(n => n < round) : [];
  if (!ns.length) return null;
  try { return JSON.parse(readFileSync(join(dir, `${rtag(Math.max(...ns))}_manifest.json`), 'utf8')); } catch { return null; }
}

// ── 命令 ──
export async function shoot({ W, round, only = null, out = null, cfg = null, root = null, log = m => console.log(m) }) {
  W = resolve(W); root = root || gitRoot(W); cfg = cfg || loadCfg(W);
  const N = Number(round);
  if (!Number.isInteger(N) || N < 0) throw new Error('--round 要是非负整数');
  let states = readStates(root, cfg);
  if (only && only.length) {
    const miss = only.filter(s => !states.some(x => x.state === s));
    if (miss.length) throw new Error(`配方里没有这些态：${miss.join('、')}`);
    states = states.filter(s => only.includes(s.state));
  }
  const dir = out ? resolve(out) : join(W, 'shots'), rt = rtag(N);
  mkdirSync(dir, { recursive: true });
  const { browser, name } = await launch(root, cfg);
  const manifest = { round: N, url: cfg.url, browser: name, viewport: cfg.viewport, states: [] };
  try {
    for (const st of states) {
      log(`[capture ${rt}] ${st.state} …`);
      const r = await shootOne(browser, cfg, st, dir, rt);
      manifest.states.push(r);
      log(`[capture ${rt}] ${st.state} ${r.ok ? 'ok' : '失败：' + r.error.split('\n')[0]}`);
    }
  } finally { await browser.close().catch(() => {}); }
  const mpath = join(dir, `${rt}_manifest.json`);
  writeFileSync(mpath, JSON.stringify(manifest, null, 2));
  return { round: N, manifest: mpath, browser: name, ...buildSummary(manifest, out ? null : prevManifest(dir, N)) };
}
export async function check({ W, cfg = null, root = null }) {
  W = resolve(W); root = root || gitRoot(W); cfg = cfg || loadCfg(W);
  let browser, name;
  try { ({ browser, name } = await launch(root, cfg)); } catch (e) { return { ok: false, status: null, browser: null, error: firstLine(e) }; }
  try {
    const page = await browser.newPage();
    const resp = await page.goto(cfg.url, { waitUntil: 'load', timeout: 30000 });
    const status = resp ? resp.status() : null;
    return { ok: status == null || status < 400, status, browser: name, error: null };
  } catch (e) { return { ok: false, status: null, browser: name, error: firstLine(e) }; }
  finally { await browser.close().catch(() => {}); }
}
const escHtml = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
/** 缩略总览：每格宽 480 像素，下方写态名；失败态红框并写出错误首行。不依赖图像库，用同一个浏览器渲染。 */
export async function contact({ W, round, cfg = null, root = null }) {
  W = resolve(W); root = root || gitRoot(W); cfg = cfg || loadCfg(W);
  const rt = rtag(Number(round)), dir = join(W, 'shots');
  const man = JSON.parse(readFileSync(join(dir, `${rt}_manifest.json`), 'utf8'));
  const cols = Math.max(1, Math.min(4, man.states.length));
  const cells = man.states.map(s => {
    const img = s.shot && existsSync(s.shot) ? `<img src="${escHtml(pathToFileURL(s.shot).href)}">` : '<div class="none">（没有截图）</div>';
    return `<figure class="${s.ok ? 'ok' : 'bad'}">${img}<figcaption>${escHtml(s.state)}${s.ok ? '' : `<br><span>${escHtml(String(s.error || '').split('\n')[0].slice(0, 160))}</span>`}</figcaption></figure>`;
  }).join('\n');
  const html = `<!doctype html><meta charset="utf-8"><style>
body{margin:0;padding:12px;background:#fff;font:14px/1.3 monospace;color:#000}
main{display:grid;grid-template-columns:repeat(${cols},480px);gap:12px}
figure{margin:0;border:2px solid #ccc;background:#f4f4f4}
figure.bad{border:4px solid #d00}
img{display:block;width:480px;max-height:640px;object-fit:contain;object-position:top}
.none{height:120px;display:flex;align-items:center;justify-content:center}
figcaption{padding:4px 6px;background:#fff}
figcaption span{color:#d00}
</style><title>${rt} contact</title><main>${cells}</main>`;
  const htmlPath = join(dir, `${rt}_contact.html`), png = join(dir, `${rt}_contact.png`);
  writeFileSync(htmlPath, html);
  const { browser } = await launch(root, cfg);
  try {
    const page = await browser.newPage({ viewport: { width: cols * 480 + (cols - 1) * 12 + 24 + 16, height: 600 } });
    await page.goto(pathToFileURL(htmlPath).href, { waitUntil: 'load', timeout: 60000 });
    await page.waitForFunction(() => [...document.images].every(i => i.complete), null, { timeout: 30000 }).catch(() => {});
    await withShotRetry({ shotRetries: 0 }, () => page.screenshot({ path: png, fullPage: true }));
  } finally { await browser.close().catch(() => {}); rmSync(htmlPath, { force: true }); }
  return png;
}

// ── CLI ──
function parseArgs(argv) {
  const o = { _: [] };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a.startsWith('--')) o[a.slice(2)] = argv[++i];
    else o._.push(a);
  }
  return o;
}
async function main(argv) {
  const o = parseArgs(argv), cmd = o._[0];
  if (!o.workdir) throw new Error('缺 --workdir');
  if (cmd === 'shoot') {
    if (o.round == null) throw new Error('缺 --round');
    const s = await shoot({ W: o.workdir, round: o.round, only: o.only ? o.only.split(',').map(x => x.trim()).filter(Boolean) : null, out: o.out || null });
    console.log(JSON.stringify(s));
    return 0;
  }
  if (cmd === 'check') { const r = await check({ W: o.workdir }); console.log(JSON.stringify(r)); return r.ok ? 0 : 1; }
  if (cmd === 'contact') { if (o.round == null) throw new Error('缺 --round'); console.log(await contact({ W: o.workdir, round: o.round })); return 0; }
  console.error('用法：capture.mjs shoot|check|contact --workdir W [--round N] [--only a,b] [--out DIR]');
  return 2;
}
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main(process.argv.slice(2)).then(c => process.exit(c ?? 0), e => { console.error('ERROR: ' + firstLine(e)); process.exit(1); });
}
