// wl.mjs / capture.mjs 集成测试的临时仓库夹具:在系统临时目录里造一个 git 仓库(含静态页、配方、验收标准、args),
// 并提供在其中跑 wl.mjs 的小函数。不碰真实仓库;用完 cleanup()。
import { mkdtempSync, writeFileSync, mkdirSync, rmSync, readFileSync, existsSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { tmpdir } from 'node:os';
import { join, dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
export const SKILL = resolve(here, '..');
export const WL = join(SKILL, 'wl.mjs');
// 截图器要从 uiDir 解析 @playwright/test:用本仓库的前端目录(若 worktree 里没装,退到主目录那份);都没有则 PLAYWRIGHT_OK=false,集成测试跳过
const candUi = [resolve(SKILL, '..', '..', '..', 'path2_web_ui'), '/home/yu/PycharmProjects/Trade_Strategy/path2_web_ui'];
export const UI_DIR = candUi.find(d => existsSync(join(d, 'node_modules', '@playwright'))) || null;
export const PLAYWRIGHT_OK = !!UI_DIR && (existsSync('/usr/bin/google-chrome') || existsSync(join(process.env.HOME || '', '.cache/ms-playwright')));

export const git = (cwd, ...a) => spawnSync('git', a, { cwd, encoding: 'utf8' });
export const RUBRIC = '# 验收标准\n\n## 术语表\n\n- 方向：一个术语\n- 备选：另一个术语\n\n## 角度 flow\n\n依次看 01-a、02-b，判流程是否通顺。\n\n## 角度 newbie\n\n看 01-a。\n\n## 角度 razor\n\n数元素。\n';
export const STATES = [
  { state: '01-a', note: 'ok 态', probe: '({mode: S.mode})', expect: { mode: 'a' }, crops: [{ name: 'box', selector: '#box' }] },
  { state: '02-b', note: 'expect 不符', probe: '({mode: S.mode})', expect: { mode: 'WRONG' } },
  { state: '03-c', note: '选择器找不到', crops: [{ name: 'nope', selector: '#nope' }] },
];
export const STATES_OK = [STATES[0], { state: '02-b', note: 'ok 态 2', probe: '({mode: S.mode})', expect: { mode: 'a' } }];

/** opts: { mode, states, lenses, smokeCmd, extraArgs, runtag } */
export function makeRepo(opts = {}) {
  const repo = mkdtempSync(join(tmpdir(), 'wl-repo-'));
  const runtag = opts.runtag || 'rt1';
  const w = (p, c) => { mkdirSync(dirname(join(repo, p)), { recursive: true }); writeFileSync(join(repo, p), c); };
  git(repo, 'init', '-q'); git(repo, 'config', 'user.email', 't@t'); git(repo, 'config', 'user.name', 't');
  w('.gitignore', '.claude/web-loop/\n');
  w('app/index.html', '<!doctype html><meta charset=utf-8><body><div id="box">放量突破</div><script>window.S={mode:"a"}</script></body>');
  for (const f of ['a', 'b', 'd', 'p']) w(`app/${f}.txt`, f.toUpperCase() + '0\n');
  w('app/data.js', 'export const scheme = 1;\n');
  w('rubric.md', RUBRIC);
  w('docs/plan.md', 'x\n');
  git(repo, 'add', '-A'); git(repo, 'commit', '-qm', 'init');
  const W = join(repo, '.claude/web-loop', runtag);
  mkdirSync(W, { recursive: true });
  const statesRel = `.claude/web-loop/${runtag}/states.json`;
  writeFileSync(join(repo, statesRel), JSON.stringify(opts.states || STATES_OK, null, 1));
  const args = { runtag, workdir: `.claude/web-loop/${runtag}`, goal: 'GOAL', goalSubgoals: [{ id: 'G1', desc: 'd', lenses: [(opts.lenses || ['ux', 'func'])[0]], states: ['01-a'] }],
    lenses: opts.lenses || ['ux', 'func'], url: 'file://' + join(repo, 'app/index.html'), statesPath: statesRel, uiDir: UI_DIR || 'ui', rubricPath: 'rubric.md',
    smokeCmd: opts.smokeCmd || 'test ! -e app/BROKEN', maxRounds: 3, skillDir: SKILL, ...(opts.extraArgs || {}) };
  if (opts.mode === 'prototype') Object.assign(args, { mode: 'prototype', schemeFiles: ['app/data.js'], contractPath: 'app/contract.md', lenses: opts.lenses || ['newbie', 'flow', 'contract'] },
    { goalSubgoals: [{ id: 'G1', desc: 'd', lenses: ['newbie'], states: ['01-a'] }] }, opts.extraArgs || {});
  const writeArgs = a => writeFileSync(join(W, 'args.json'), JSON.stringify(a, null, 2));
  writeArgs(args);
  return { repo, W, runtag, args, writeArgs, w, cleanup: () => rmSync(repo, { recursive: true, force: true }),
    read: p => readFileSync(join(repo, p), 'utf8'), exists: p => existsSync(join(repo, p)),
    wl: (...a) => runWl(repo, ...a), gitOut: (...a) => git(repo, ...a).stdout };
}
export function runWl(cwd, ...a) {
  const env = { ...process.env, ...(a.at(-1) && typeof a.at(-1) === 'object' && !Array.isArray(a.at(-1)) ? a.pop().env : {}) };
  const r = spawnSync(process.execPath, [WL, ...a], { cwd, encoding: 'utf8', env, timeout: 300000 });
  const out = (r.stdout || '') + (r.stderr || '');
  const lines = (r.stdout || '').split('\n').filter(l => l.trim());
  let last = null; try { last = JSON.parse(lines.at(-1)); } catch { /* 非 JSON */ }
  return { code: r.status, out, stdout: r.stdout || '', last };
}
