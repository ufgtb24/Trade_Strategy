// W 系列:wl.mjs 的集成测试(临时 git 仓库;需要 playwright+chrome 的用例在不具备时跳过)。
import { readFileSync, writeFileSync, existsSync, mkdirSync, rmSync, utimesSync, mkdtempSync, readdirSync, statSync } from 'node:fs';
import { spawn } from 'node:child_process';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import net from 'node:net';
import http from 'node:http';
import { runScenarios, expect, run, sim, fakeVerify, okReview, newArgs, core, coreInit, coreStep, mustIssue2 } from './dryrun.mjs';
import { WL, SKILL, makeRepo, git, RUBRIC, STATES_OK, PLAYWRIGHT_OK } from './wl-fixture.mjs';

const wlm = await import(WL);
const S = [];
const sc = (id, title, fn, needPw = true) => {
  if (needPw && !PLAYWRIGHT_OK) { console.log(`SKIP ${id} (没有可解析的 playwright / chrome)`); return; }
  S.push([id, title, fn]);
};
const withRepo = (opts, fn) => async () => { const R = makeRepo(opts); try { return await fn(R); } finally { R.cleanup(); } };
const initOk = R => { const r = R.wl('init', R.W); expect(r.code === 0 && /OK：/.test(r.out), 'init 失败: ' + r.out.slice(-600).replace(/\n/g, ' | ')); return r; };
const patchInjected = (R, fn) => { const wf = join(R.W, 'workflow.js'), inj = wlm.loadInjected(wf); fn(inj.args); writeFileSync(wf, wlm.buildWorkflowSource(readFileSync(join(SKILL, 'workflow-template.js'), 'utf8'), inj)); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const rd = (R, p) => (R.exists(p) ? R.read(p).trim() : '(不存在)');

// ── W1 intake ──
sc('W1', 'intake:2 个 hint + 1 个 override 数组;key 正确;--done 过滤;文件名不变', withRepo({}, R => {
  const c = join(R.W, 'control'); mkdirSync(c, { recursive: true });
  writeFileSync(join(c, 'hint-a.md'), 'HINT_A'); writeFileSync(join(c, 'hint-r7.md'), 'HINT_R7');
  writeFileSync(join(c, 'override-x.json'), JSON.stringify([{ id: 'ux-r1-1', action: 'waive', note: 'n' }, { id: 'ux-r1-2', action: 'unverifiable', requiredStates: ['14-b'] }]));
  const r = R.wl('intake', R.W, '--done', '');
  const o = JSON.parse(r.stdout);
  expect(o.hints.map(h => h.key).join() === 'hint-a.md,hint-r7.md' && o.hints[1].text === 'HINT_R7', 'hints=' + JSON.stringify(o.hints));
  expect(o.overrides.map(x => x.key).join() === 'override-x.json#0,override-x.json#1', 'overrides=' + JSON.stringify(o.overrides));
  expect(o.verifyRunning === null, '没有 verify worker 在跑时 verifyRunning 应为 null: ' + JSON.stringify(o.verifyRunning));
  const o2 = JSON.parse(R.wl('intake', R.W, '--done', 'hint-a.md,override-x.json#0').stdout);
  expect(o2.hints.length === 1 && o2.overrides.length === 1 && o2.overrides[0].key === 'override-x.json#1', '--done 未过滤: ' + JSON.stringify(o2));
  expect(readdirSync(c).sort().join() === 'hint-a.md,hint-r7.md,override-x.json', '文件名被改动');
}), false);

// ── W2 init 校验 ──
sc('W2', 'init 校验:缺字段 / 子项角度不在 lenses / workdir 未被忽略 / app 模式用 contract:退出码 1 且点名问题', withRepo({}, R => {
  const bad = (mut, re, name) => {
    R.writeArgs(mut({ ...R.args })); const r = R.wl('init', R.W);
    expect(r.code === 1 && re.test(r.out), `${name}: code=${r.code} out=${r.out.slice(-300)}`);
  };
  bad(a => ({ ...a, goal: '' }), /goal/, '缺 goal');
  bad(a => ({ ...a, goalSubgoals: [{ id: 'G1', desc: 'd', lenses: ['ghost'] }] }), /ghost|lenses|角度/, '子项角度不在 lenses');
  bad(a => ({ ...a, lenses: ['ux', 'contract'] }), /contract/, 'app 模式用 contract');
  R.writeArgs(R.args); writeFileSync(join(R.repo, '.gitignore'), '');
  const r = R.wl('init', R.W);
  expect(r.code === 1 && /gitignore|忽略/.test(r.out), 'workdir 未忽略: ' + r.out.slice(-300));
}), false);

// ── W3 清理旧截图 ──
sc('W3', 'init 清理:3 个旧 run 目录(含 shots),只有最新的保留 shots;.playwright-mcp 不动;无 args.json 的目录不碰', withRepo({}, R => {
  const base = join(R.repo, '.claude/web-loop');
  for (const [k, t] of [['old1', 1000], ['old2', 2000], ['old3', 3000]]) {
    mkdirSync(join(base, k, 'shots'), { recursive: true }); writeFileSync(join(base, k, 'args.json'), '{}'); writeFileSync(join(base, k, 'shots/x.png'), 'x');
    utimesSync(join(base, k, 'args.json'), t, t);
  }
  mkdirSync(join(base, 'not-a-run/shots'), { recursive: true });
  mkdirSync(join(R.repo, '.playwright-mcp'), { recursive: true }); writeFileSync(join(R.repo, '.playwright-mcp/keep.yml'), 'k');
  initOk(R);
  expect(!R.exists('.claude/web-loop/old1/shots') && !R.exists('.claude/web-loop/old2/shots') && R.exists('.claude/web-loop/old3/shots'), '应只保留最新的 old3 的 shots');
  expect(R.exists('.claude/web-loop/not-a-run/shots'), '无 args.json 的目录不应被碰');
  expect(R.exists('.playwright-mcp/keep.yml'), '.playwright-mcp 被动了');
}));

// ── W4 / W4b / W4c ──
const verify = (R, n, kind = 'frontend', ...extra) => R.wl('verify', R.W, '--round', String(n), '--kind', kind, ...extra);
sc('W4', '快照:改已跟踪文件、新建未跟踪文件、删文件 → changed 三项;真 index 与 stash 不变;diff 输出对', withRepo({}, R => {
  initOk(R);
  const idxBefore = R.gitOut('status', '--porcelain'), stashBefore = R.gitOut('stash', 'list');
  R.w('app/a.txt', 'A1\n'); R.w('app/new.txt', 'N\n'); R.wl; require_rm(R, 'app/d.txt');
  const before = R.gitOut('status', '--porcelain'), cachedBefore = R.gitOut('diff', '--cached');
  const v = verify(R, 1);
  expect(v.last && v.last.changedCount === 3 && v.last.snapOk === true, 'verify=' + v.out.slice(-400));
  expect(R.gitOut('status', '--porcelain') === before && R.gitOut('diff', '--cached') === cachedBefore && cachedBefore === '', '真 index 被动了');
  expect(R.gitOut('stash', 'list') === stashBefore, 'stash 被动了');
  const d = R.wl('diff', R.W, '--round', '1').stdout;
  expect(d.includes('app/a.txt') && d.includes('app/new.txt') && d.includes('app/d.txt'), 'diff 输出缺文件');
  void idxBefore;
}));
function require_rm(R, p) { rmSync(join(R.repo, p)); }

sc('W4b', '回滚:开跑前脏文件 P 保持;r1 改 A(绿);r2 改 B、建 C、删 D、主会话改配方 X;smoke 在 B 坏时失败 → rolledBack', withRepo({ smokeCmd: '! grep -q BROKEN app/b.txt' }, R => {
  R.w('app/p.txt', 'P-dirty\n');                                   // 开跑前就有的脏文件
  initOk(R);
  R.w('app/a.txt', 'A-r1\n');
  const v1 = verify(R, 1);
  expect(v1.last.smoke.pass === true, 'r1 应绿: ' + v1.out.slice(-300));
  R.w('app/b.txt', 'B-BROKEN\n'); R.w('app/c.txt', 'C\n'); rmSync(join(R.repo, 'app/d.txt'));
  const xPath = JSON.parse(R.read(`.claude/web-loop/${R.runtag}/args.json`)).statesPath;
  const xBefore = R.read(xPath); R.w(xPath, xBefore + ' ');       // 「主会话」改了配方文件
  const v2 = verify(R, 2);
  expect(v2.last.smoke.pass === false && v2.last.smoke.rolledBack === true && v2.last.smoke.envBroken === false, 'r2 应 rolledBack: ' + JSON.stringify(v2.last && v2.last.smoke));
  expect(rd(R, 'app/a.txt') === 'A-r1', 'A 应保留 r1 的改动: ' + rd(R, 'app/a.txt'));
  expect(rd(R, 'app/b.txt') === 'B0', 'B 应恢复: ' + rd(R, 'app/b.txt'));
  expect(rd(R, 'app/d.txt') === 'D0', 'D 应恢复: ' + rd(R, 'app/d.txt'));
  expect(!R.exists('app/c.txt'), 'C 应被删');
  expect(rd(R, 'app/p.txt') === 'P-dirty', 'P 应保持脏: ' + rd(R, 'app/p.txt'));
  expect(R.read(xPath) === xBefore + ' ', 'X(配方)应保留主会话的修改');
  expect(R.exists(`.claude/web-loop/${R.runtag}/snap/r02.rejected.diff`), '缺 rejected.diff');
}));
sc('W4c', '回滚后 smoke 仍红(环境坏了):改动被放回,envBroken:true', async () => {
  const flagDir = mkdtempSync(join(tmpdir(), 'wl-flag-')), flag = join(flagDir, 'broken');
  const R = makeRepo({ smokeCmd: `test ! -e ${flag}` });
  try {
    initOk(R);
    R.w('app/b.txt', 'B-r2\n'); R.w('app/c.txt', 'C\n'); rmSync(join(R.repo, 'app/d.txt'));
    writeFileSync(flag, '1');                                        // 环境坏了:与代码无关
    const v = verify(R, 1);
    expect(v.last.smoke.pass === false && v.last.smoke.envBroken === true && v.last.smoke.rolledBack === false, 'smoke=' + JSON.stringify(v.last && v.last.smoke));
    expect(rd(R, 'app/b.txt') === 'B-r2' && rd(R, 'app/c.txt') === 'C' && !R.exists('app/d.txt'), '改动应被放回: B=' + rd(R, 'app/b.txt') + ' C=' + rd(R, 'app/c.txt') + ' D=' + rd(R, 'app/d.txt'));
  } finally { R.cleanup(); rmSync(flagDir, { recursive: true, force: true }); }
});

// ── W5 续跑注入 ──
sc('W5', 'init 带 continueFrom:INJECT 段的 seed 等于 toSeed(ledger);workflow.js 可编译', withRepo({}, async R => {
  const old = join(R.repo, '.claude/web-loop/old'); mkdirSync(old, { recursive: true });
  const { cfg, S: st } = coreInit(newArgs({ lenses: ['ux'] }));
  coreStep(cfg, st, 1, { reviews: [okReview(cfg, 'ux', { issues: [mustIssue2('A')] })] });
  coreStep(cfg, st, 2, { reviews: [okReview(cfg, 'ux', { known: [{ id: 'ux-r1-1', status: 'gone', evidence: 'e' }] })] });
  writeFileSync(join(old, 'ledger.json'), JSON.stringify(st));
  R.writeArgs({ ...R.args, continueFrom: '.claude/web-loop/old' });
  initOk(R);
  const inj = wlm.loadInjected(join(R.W, 'workflow.js'));
  expect(JSON.stringify(inj.seed) === JSON.stringify(core().toSeed(JSON.parse(JSON.stringify(st)))), 'seed 与 toSeed(ledger) 不同');
  const fixed = inj.seed.issues.find(i => i.id === 'ux-r1-1');
  expect(fixed && fixed.status === 'fixed' && fixed.detail === undefined, 'fixed 条目应被压缩');
  wlm.loadCore(join(R.W, 'workflow.js'));
}));

// ── W8 rubric 专节 / 冻结 ──
sc('W8', 'init 角度专节:lenses 含 flow 而 rubric 无专节 → 退出码 1 点名 flow;补上通过;rubric.md 冻结且冲突时报错', withRepo({ lenses: ['ux', 'flow'] }, R => {
  R.w('rubric.md', '# 验收\n无专节\n');
  let r = R.wl('init', R.W);
  expect(r.code === 1 && /flow/.test(r.out), '第一次应失败并点名 flow: ' + r.out.slice(-300));
  R.w('rubric.md', RUBRIC);
  initOk(R);
  expect(R.read(`.claude/web-loop/${R.runtag}/rubric.md`) === RUBRIC, '冻结的 rubric.md 应已生成');
  R.w('rubric.md', RUBRIC + '\n改了\n');
  r = R.wl('init', R.W);
  expect(r.code === 1 && /冻结/.test(r.out), 'rubric 与冻结件不同应报错: ' + r.out.slice(-300));
}));

// ── W11 kindAdjusted ──
sc('W11', 'kind=frontend 但 changed 里有 uiDir 之外的 .py 且配了 restartCmd → kindAdjusted:"backend"', withRepo({}, R => {
  initOk(R);
  patchInjected(R, a => { a.restartCmd = 'exit 1'; a.healthUrl = 'http://127.0.0.1:1/'; });
  R.w('app/server.py', 'print(1)\n');
  const v = verify(R, 1, 'frontend');
  expect(v.last && v.last.kindAdjusted === 'backend', 'kindAdjusted=' + (v.last && v.last.kindAdjusted));
}));

// ── W12 原型模式 init ──
sc('W12', 'init 原型模式检查:清单在 workdir 里 / 被忽略 / 仍是骨架 / 术语表缺失;全部正确时 derived.terms = 术语表词', withRepo({ mode: 'prototype' }, R => {
  const set = (o) => R.writeArgs({ ...R.args, ...o });
  set({ contractPath: `.claude/web-loop/${R.runtag}/contract.md` });
  let r = R.wl('init', R.W);
  expect(r.code === 1 && /contractPath|清单/.test(r.out), '清单在 workdir 里应报错: ' + r.out.slice(-200));
  R.w('.gitignore', '.claude/web-loop/\nignored/\n'); set({ contractPath: 'ignored/contract.md' });
  r = R.wl('init', R.W);
  expect(r.code === 1 && /忽略/.test(r.out), '清单被忽略应报错: ' + r.out.slice(-200));
  set({ contractPath: 'app/contract.md' });
  r = R.wl('init', R.W);                                             // 不存在 → 生成骨架并失败
  expect(r.code === 1 && R.exists('app/contract.md'), '应生成骨架并失败: ' + r.out.slice(-200));
  r = R.wl('init', R.W);
  expect(r.code === 1 && /骨架/.test(r.out), '仍是原样骨架应报错: ' + r.out.slice(-200));
  R.w('app/contract.md', '# 后端要求\n\n- 字段 x：string，来源 y\n');
  R.w('rubric.md', '# 验收\n\n## 角度 flow\n看 01-a、02-b\n');
  r = R.wl('init', R.W);
  expect(r.code === 1 && /术语表/.test(r.out), '缺术语表应报错: ' + r.out.slice(-200));
  R.w('rubric.md', RUBRIC);
  initOk(R);
  const inj = wlm.loadInjected(join(R.W, 'workflow.js'));
  expect(JSON.stringify(inj.derived.terms) === JSON.stringify(['方向', '备选']), 'derived.terms=' + JSON.stringify(inj.derived.terms));
}));

// ── W18 标题带编号 ──
sc('W18', 'init:术语表与角度专节的标题前可带编号(「## 7. 术语表」「### 5.1 角度 flow」「## 3 角度 newbie」)', withRepo({ mode: 'prototype' }, R => {
  R.w('app/contract.md', '# 后端要求\n\n- 字段 x：string，来源 y\n');
  R.w('rubric.md', '# 验收\n\n## 7. 术语表\n\n- 方向：一个术语\n- 备选：另一个术语\n\n### 5.1 角度 flow\n\n依次看 01-a、02-b。\n\n## 3 角度 newbie\n\n看 01-a。\n\n## 4) 角度 razor\n数元素\n');
  initOk(R);
  const inj = wlm.loadInjected(join(R.W, 'workflow.js'));
  expect(JSON.stringify(inj.derived.terms) === JSON.stringify(['方向', '备选']), 'derived.terms=' + JSON.stringify(inj.derived.terms));
}));

// ── W13 短结果 ──
sc('W13', 'verify 短结果:smoke 输出含引号、反斜杠、ANSI 色码 → 最后一行可 JSON.parse 且只含短字段;完整 tail 在 snap/rNN.verify.json', withRepo({ smokeCmd: 'bash app/smoke.sh' }, R => {
  R.w('app/smoke.sh', "printf 'q\"uote \\\\ back \\033[31mred\\033[0m\\n'\nexit 0\n");
  git(R.repo, 'add', '-A'); git(R.repo, 'commit', '-qm', 'smoke');
  initOk(R);
  const v = verify(R, 1);
  expect(v.last && v.last.round === 1, '最后一行应是可解析的 JSON: ' + v.out.slice(-300));
  const allowed = new Set(['round', 'kind', 'kindAdjusted', 'envOk', 'noChange', 'journalCopied', 'snapOk', 'changedCount', 'schemeTouched', 'smoke', 'refreshOk', 'capture', 'manifest', 'sig']);
  expect(Object.keys(v.last).every(k => allowed.has(k)), '短结果含多余字段: ' + Object.keys(v.last));
  const full = JSON.parse(R.read(`.claude/web-loop/${R.runtag}/snap/r01.verify.json`));
  const tail = JSON.stringify(full.smoke);
  expect(tail.includes('uote') && tail.includes('back'), '完整结果里应有 smoke 末尾: ' + tail.slice(0, 200));
  expect(core().canonHash((({ sig, ...rest }) => rest)(v.last)) === v.last.sig, 'sig 与 CORE 的 canonHash 不一致');
}));

// ── W9 后端重启 ──
const freePort = () => new Promise(r => { const s = net.createServer(); s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => r(p)); }); });
const getBody = port => new Promise(res => { http.get({ host: '127.0.0.1', port, path: '/', agent: false }, rr => { let b = ''; rr.on('data', d => (b += d)); rr.on('end', () => res(b)); }).on('error', () => res(null)); });
sc('W9', '后端重启:verify --kind backend 后端口上的监听进程号变了、旧进程已退出;restartCmd 起不来则 refreshOk:false', async () => {
  const dir = mkdtempSync(join(tmpdir(), 'wl-srv-')), script = join(dir, 'server.mjs');
  writeFileSync(script, "import http from 'node:http'; http.createServer((q, r) => r.end(String(process.pid))).listen(Number(process.argv[2]), '127.0.0.1');\n");
  const port = await freePort();
  const old = spawn(process.execPath, [script, String(port)], { detached: true, stdio: 'ignore' }); old.unref();
  const R = makeRepo({ extraArgs: { restartCmd: `node ${script} ${port}`, healthUrl: `http://127.0.0.1:${port}/` } });
  let newPid = null;
  try {
    for (let i = 0; i < 30 && !(await getBody(port)); i++) await sleep(200);
    const oldPid = Number(await getBody(port)); expect(oldPid === old.pid, '旧服务没起来');
    initOk(R);
    const v = verify(R, 1, 'backend');
    expect(v.last && v.last.refreshOk === true, 'refreshOk=' + (v.last && v.last.refreshOk) + ' ' + v.out.slice(-300));
    newPid = Number(await getBody(port)) || null;      // 不重试:verify 报 refreshOk 时新服务必须已在监听
    expect(newPid && newPid !== oldPid, '监听进程号应变了: ' + oldPid + '→' + newPid);
    let alive = true; try { process.kill(oldPid, 0); } catch { alive = false; }
    expect(!alive, '旧进程应已退出');
    R.writeArgs({ ...R.args, restartCmd: 'exit 1' });                 // 注入已固化在 workflow.js 里,这里改 args 不影响;改用重新 init 太重 → 直接改 workflow 的注入
    const wf = join(R.W, 'workflow.js'), inj = wlm.loadInjected(wf);
    inj.args.restartCmd = 'exit 1';
    writeFileSync(wf, wlm.buildWorkflowSource(readFileSync(join(SKILL, 'workflow-template.js'), 'utf8'), inj));
    const v2 = verify(R, 2, 'backend');
    expect(v2.last && v2.last.refreshOk === false, 'restartCmd 起不来时 refreshOk 应为 false: ' + (v2.last && v2.last.refreshOk));
  } finally {
    for (const p of [old.pid, newPid]) if (p) { try { process.kill(p, 'SIGKILL'); } catch { /* 已退出 */ } }
    R.cleanup(); rmSync(dir, { recursive: true, force: true });
  }
});

// ── W10 / W14 / W6 journal ──
const projects = mkdtempSync(join(tmpdir(), 'wl-proj-'));
process.env.WL_PROJECTS_DIR = projects;
const mkJournal = (name, text, mtime) => { const d = join(projects, 'p', 's', 'subagents', 'workflows', name); mkdirSync(d, { recursive: true }); writeFileSync(join(d, 'journal.jsonl'), text); return join(d, 'journal.jsonl'); };
const jl = (label, extra = '') => JSON.stringify({ type: 'started', key: label, label }) + '\n' + JSON.stringify({ type: 'result', key: label, result: JSON.stringify({ x: extra }) }) + '\n';
sc('W10', '找 journal:run.json 指向 / 按内容认并补写 run.json / 多份报错列出;verify 后 journal 副本与原文件逐字节相同', async () => {
  const W = mkdtempSync(join(tmpdir(), 'wl-W-')); mkdirSync(join(W, 'shots'));
  try {
    const jA = mkJournal('wf_A', jl('impl-r01') + jl('verify-r01', `"${W}/shots/r01_manifest.json`));
    rmSync(join(W, 'run.json'), { force: true });
    const f2 = wlm.findJournal(W);                                   // ② 无 run.json,按内容
    expect(f2.path === jA && existsSync(join(W, 'run.json')), '按内容应认中 wf_A 并补写 run.json');
    const f1 = wlm.findJournal(W);                                   // ① 现在有 run.json
    expect(f1.path === jA && f1.source === 'run.json', '应走 run.json: ' + f1.source);
    rmSync(join(W, 'run.json'));
    mkJournal('wf_B', jl('verify-r01', `"${W}/shots/r01_manifest.json`));
    let msg = ''; try { wlm.findJournal(W); } catch (e) { msg = e.message; }
    expect(/wf_A/.test(msg) && /wf_B/.test(msg), '③ 多份应报错并列出两份: ' + msg);
  } finally { rmSync(W, { recursive: true, force: true }); rmSync(projects, { recursive: true, force: true }); mkdirSync(projects, { recursive: true }); }
}, false);
sc('W10b', 'verify 运行后 <W>/journal.jsonl 与 run.json 指向的原文件逐字节相同', withRepo({}, R => {
  initOk(R);
  const jp = mkJournal('wf_C', jl('impl-r01', '中文 "引号" \\ 反斜杠'));
  writeFileSync(join(R.W, 'run.json'), JSON.stringify({ runId: 'wf_C', transcriptDir: join(projects, 'p/s/subagents/workflows/wf_C'), foundBy: 'attach' }));
  const v = verify(R, 1);
  expect(v.last && v.last.journalCopied === true, 'journalCopied=' + (v.last && v.last.journalCopied));
  expect(readFileSync(join(R.W, 'journal.jsonl')).equals(readFileSync(jp)), '副本与原文件不同');
}));
sc('W14', 'journal 按内容认:两份 label 相同,只有一份含 "<W>/shots/ 字样 → 认中那一份', async () => {
  const W = mkdtempSync(join(tmpdir(), 'wl-W-')); mkdirSync(join(W, 'shots'));
  try {
    mkJournal('wf_X', jl('verify-r01', '别处的路径'));
    const jY = mkJournal('wf_Y', jl('verify-r01', `"${W}/shots/r01_manifest.json`));
    expect(wlm.findJournal(W).path === jY, '应认中含本运行目录路径的 wf_Y');
  } finally { rmSync(W, { recursive: true, force: true }); rmSync(projects, { recursive: true, force: true }); mkdirSync(projects, { recursive: true }); }
}, false);
sc('W6', 'journal 解析:半行被跳过;result 为字符串时 parse;全不认识时报错并带出第一行', async () => {
  const good = jl('impl-r01', 'a') + jl('verify-r01', 'b');
  const p = wlm.parseJournal(good + '{"type":"started","key":"k3","lab');
  expect(p.started.join() === 'impl-r01,verify-r01' && p.results['verify-r01'].x === 'b' && p.badLines === 0, '半行应被跳过: ' + JSON.stringify(p));
  let msg = ''; try { wlm.parseJournal('hello\nworld\n'); } catch (e) { msg = e.message; }
  expect(/hello/.test(msg), '全不认识应报错并带第一行: ' + msg);
  const real = process.env.WL_REAL_JOURNAL;                           // 可选:真实 journal 路径,不存在则跳过
  if (real && existsSync(real)) { const r = wlm.parseJournal(readFileSync(real, 'utf8')); expect(r.started.length > 0, '真实 journal 无 started'); }
}, false);

// ── W7 export ──
sc('W7', 'export:跑通一个收敛的 run → 假 journal → SUMMARY 含全部章节,converged 时「没有阻塞项」,ledger.json 有出口', withRepo({ lenses: ['ux'] }, async R => {
  initOk(R);
  const inj = wlm.loadInjected(join(R.W, 'workflow.js'));
  const a = inj.args;
  const r = await run(a, sim(a, {}), { injected: inj });
  expect(!r.error && r.result.exitReason === 'converged', 'dryrun 应收敛: ' + (r.error && r.error.message) + ' ' + JSON.stringify(r.result && r.result.exitReason));
  const lines = []; r.calls.forEach((c, i) => { lines.push(JSON.stringify({ type: 'started', key: i, label: c.label })); lines.push(JSON.stringify({ type: 'result', key: i, result: JSON.stringify(c.result) })); });
  const jp = join(R.W, 'fake-journal.jsonl'); writeFileSync(jp, lines.join('\n') + '\n');
  const e = R.wl('export', R.W, '--journal', jp);
  expect(e.code === 0, 'export 失败: ' + e.out.slice(-400));
  const sum = R.read(`.claude/web-loop/${R.runtag}/SUMMARY.md`);
  for (const h of ['需要你做的事', '子项', '还开着的确证问题', '待人工取证', '方向题', '可选改进', '评审分歧', '每轮走势', '本 run 改动的文件', '给主会话的留言', '台账修正与异常', '截图对照', '怎么续跑与退回'])
    expect(new RegExp(`^##+\\s*${h}`, 'm').test(sum), 'SUMMARY 缺章节 ' + h);
  expect(/没有阻塞项/.test(sum), 'converged 时应写「没有阻塞项」');
  const led = JSON.parse(R.read(`.claude/web-loop/${R.runtag}/ledger.json`));
  expect(led.meta && led.meta.exitReason === 'converged', 'ledger.meta.exitReason=' + (led.meta && led.meta.exitReason));
}));

// ── W19 方向题证据图 ──
const fakeJournal = (R, calls) => { const lines = []; calls.forEach((c, i) => { lines.push(JSON.stringify({ type: 'started', key: i, label: c.label })); lines.push(JSON.stringify({ type: 'result', key: i, result: JSON.stringify(c.result) })); });
  const jp = join(R.W, 'fake-journal.jsonl'); writeFileSync(jp, lines.join('\n') + '\n'); return jp; };
sc('W19', 'init 注入起点截图结果;起点评审的方向题:export 把 r00 整页图与局部图复制进 evidence/<id>/ 并嵌进 SUMMARY;shots 清掉后再 export 仍沿用', withRepo({ lenses: ['ux'] }, async R => {
  initOk(R);
  const inj = wlm.loadInjected(join(R.W, 'workflow.js'));
  expect(inj.start && inj.start.okStates.join() === '01-a,02-b' && /r00_manifest\.json$/.test(inj.start.manifest), 'INJECTED.start 不对: ' + JSON.stringify(inj.start));
  const a = inj.args;
  const dir = { title: 'DIR_T', options: [{ choice: 'a', cost: 'c' }], recommend: 'a', why: 'w', states: ['r00_01-a.png'] };   // 评审写成文件名也认
  const r = await run(a, sim(a, { review: (L, n) => (n === 0 ? { directions: [dir] } : undefined) }), { injected: inj });
  expect(!r.error, 'dryrun 出错: ' + (r.error && r.error.message));
  const jp = fakeJournal(R, r.calls);
  const e = R.wl('export', R.W, '--journal', jp);
  expect(e.code === 0, 'export 失败: ' + e.out.slice(-400));
  const id = JSON.parse(R.read(`.claude/web-loop/${R.runtag}/ledger.json`)).directions[0].id, ev = join(R.W, 'evidence', id);
  const files = existsSync(ev) ? readdirSync(ev).sort() : [];
  expect(files.includes('r00_01-a.png') && files.some(f => /^r00_01-a__box\.png$/.test(f)) && !files.some(f => /02-b/.test(f)), 'evidence 文件不对: ' + files.join(','));
  const sum = () => R.read(`.claude/web-loop/${R.runtag}/SUMMARY.md`);
  expect(sum().includes(`![${id}](evidence/${id}/r00_01-a.png)`), 'SUMMARY 没嵌证据图');
  rmSync(join(R.W, 'shots'), { recursive: true, force: true });
  expect(R.wl('export', R.W, '--journal', jp).code === 0 && sum().includes(`evidence/${id}/r00_01-a__box.png`), 'shots 清掉后再 export 应沿用 evidence');
}));
sc('W20', 'rubric-diff:按节列出增删行;参数可为运行目录(取冻结的 rubric.md);没差别时说没有差别', withRepo({}, R => {
  R.w('old.md', '# 标准\n\n## 角度 ux\n\n- 按钮等宽\n- 不要灰字\n\n## 旧节\n\n- x\n');
  R.w('new.md', '# 标准\n\n## 角度 ux\n\n- 按钮等宽\n- 灰字只给空态\n\n## 新节\n\n- y\n');
  const lines = wlm.rubricDiff(R.read('old.md'), R.read('new.md'));
  expect(lines.includes('~ 「角度 ux」') && lines.includes('    - - 不要灰字') && lines.includes('    + - 灰字只给空态'), '改动节不对: ' + lines.join(' | '));
  const dup = wlm.rubricDiff('# T\n## 角度 ux\n### must\n- a\n## 角度 func\n### must\n- a\n```\n# 代码注释\n```\n', '# T\n## 角度 ux\n### must\n## 角度 func\n### must\n- a\n```\n# 代码注释\n```\n');
  expect(dup.includes('~ 「角度 ux › must」') && dup.includes('    - - a') && !dup.some(l => /func|代码注释/.test(l)), '同名小节或代码块处理不对: ' + dup.join(' | '));
  expect(lines.includes('+ 新增一节「新节」') && lines.includes('- 删掉一节「旧节」') && !lines.some(l => /按钮等宽/.test(l)), '增删节不对: ' + lines.join(' | '));
  writeFileSync(join(R.W, 'rubric.md'), R.read('old.md'));
  const o = R.wl('rubric-diff', R.W, 'new.md');
  expect(o.code === 0 && o.out.includes('灰字只给空态'), '运行目录参数不认: ' + o.out);
  expect(/没有差别/.test(R.wl('rubric-diff', 'old.md', 'old.md').out), '同一份应说没有差别');
}), false);

sc('W21', 'copyEvidence:整页图加裁剪图、态名写成文件名也认;延续方向题从上一个 run 的 evidence/ 取;重新复制前清掉旧图;没来源时沿用已有的', () => {
  const root = mkdtempSync(join(tmpdir(), 'wl-ev-')), W = join(root, 'run2'), old = join(root, 'run1', 'evidence', 'dir-ux-r1-1');
  try {
    const put = (p, s = 'png') => { mkdirSync(join(p, '..'), { recursive: true }); writeFileSync(p, s); };
    for (const f of ['r00_01-a.png', 'r00_01-a__box.png', 'r00_02-b.png', 'r02_01-a.png']) put(join(W, 'shots', f));
    put(join(old, 'r01_03-c.png'));
    put(join(W, 'evidence', 'dir-ux-r0-1', 'stale.png'));
    const dirs = [{ id: 'dir-ux-r0-1', shotTag: 'r00', states: ['r00_01-a.png'] }, { id: 'dir-ux-r1-1', shotTag: null, evidenceFrom: 'run1/evidence/dir-ux-r1-1', states: ['03-c'] },
      { id: 'dir-func-r2-1', shotTag: 'r02', states: ['09-none'] }];
    put(join(W, 'evidence', 'dir-func-r2-1', 'kept.png'));
    const ev = wlm.copyEvidence(W, root, dirs);
    expect(ev['dir-ux-r0-1'].join() === 'evidence/dir-ux-r0-1/r00_01-a.png,evidence/dir-ux-r0-1/r00_01-a__box.png', '本 run 方向题: ' + ev['dir-ux-r0-1']);
    expect(ev['dir-ux-r1-1'].join() === 'evidence/dir-ux-r1-1/r01_03-c.png', '延续方向题: ' + ev['dir-ux-r1-1']);
    expect(ev['dir-func-r2-1'].join() === 'evidence/dir-func-r2-1/kept.png', '没来源时应沿用已有的: ' + ev['dir-func-r2-1']);
  } finally { rmSync(root, { recursive: true, force: true }); }
}, false);

// ── W15 restore ──
sc('W15', 'restore:--dry-run 只列路径不动文件;真恢复回到 green 状态并可用 before-restore 撤销', withRepo({}, R => {
  initOk(R);
  R.w('app/a.txt', 'A-r1\n');
  const v1 = verify(R, 1);
  expect(v1.last.smoke.pass === true, 'r1 应绿');
  R.w('app/a.txt', 'A-later\n'); R.w('app/extra.txt', 'E\n'); rmSync(join(R.repo, 'app/d.txt'));
  const snapshot = () => ['app/a.txt', 'app/extra.txt', 'app/d.txt'].map(p => rd(R, p)).join('|');
  const before = snapshot();
  const dry = R.wl('restore', R.W, '--to', 'green', '--dry-run');
  expect(dry.code === 0 && /app\/a\.txt/.test(dry.out) && /app\/extra\.txt/.test(dry.out) && /app\/d\.txt/.test(dry.out), 'dry-run 应列出三个路径: ' + dry.out);
  expect(/dry-run/.test(dry.out), 'dry-run 应声明没有改动');
  expect(snapshot() === before, 'dry-run 不应改动任何文件');
  expect(!R.exists(`.claude/web-loop/${R.runtag}/snap/before-restore.tree`), 'dry-run 不应写 before-restore');
  const real = R.wl('restore', R.W, '--to', 'green');
  expect(real.code === 0, 'restore 失败: ' + real.out);
  expect(rd(R, 'app/a.txt') === 'A-r1' && !R.exists('app/extra.txt') && rd(R, 'app/d.txt') === 'D0', '应回到 green: ' + snapshot());
  const undo = R.wl('restore', R.W, '--to', 'before-restore');
  expect(undo.code === 0 && snapshot() === before, '撤销后应回到 restore 前: ' + snapshot());
}));

// ── W16 / W17:verify 拆成前台 + detached worker(I1) ──
sc('W16', 'verify 等待上限很小:先返回 pending;wait 拿到完整短行;锁已删、结果文件在;同一轮再次 verify 幂等(不重复起 worker)', withRepo({ smokeCmd: 'sleep 3; test ! -e app/BROKEN' }, R => {
  initOk(R);
  R.w('app/a.txt', 'A-r1\n');
  const snapDir = `.claude/web-loop/${R.runtag}/snap`;
  const v = verify(R, 1, 'frontend', '--wait-ms', '500');
  expect(v.last && v.last.pending === true && v.last.round === 1, '应先返回 pending: ' + v.out.slice(-300));
  const w = R.wl('wait', R.W, '--round', '1', '--wait-ms', '120000');
  expect(w.last && w.last.round === 1 && w.last.smoke && w.last.smoke.pass === true && w.last.capture && w.last.sig, 'wait 应拿到完整短行: ' + w.out.slice(-400));
  expect(core().canonHash((({ sig, ...rest }) => rest)(w.last)) === w.last.sig, 'sig 应与 CORE 的 canonHash 一致');
  expect(R.exists(`${snapDir}/r01.verify.out`) && R.exists(`${snapDir}/r01.verify.json`) && !R.exists(`${snapDir}/r01.verify.lock`), '结果文件应在、锁应已删');
  expect(rd(R, 'app/a.txt') === 'A-r1', '工作区应与正常跑完一致');
  const again = verify(R, 1, 'frontend', '--wait-ms', '500');
  expect(again.last && again.last.sig === w.last.sig, '同一轮再次 verify 应直接给出已有结果: ' + again.out.slice(-200));
}));
sc('W17', '红路径 + 很小的等待上限:先 pending;等 worker 跑完后 rolledBack 的结果与 restored.tree 都在,工作区已退回', withRepo({ smokeCmd: 'sleep 1; ! grep -q BROKEN app/b.txt' }, R => {
  initOk(R);
  R.w('app/b.txt', 'B-BROKEN\n'); R.w('app/c.txt', 'C\n');
  const snapDir = `.claude/web-loop/${R.runtag}/snap`;
  const v = verify(R, 1, 'frontend', '--wait-ms', '300');
  expect(v.last && v.last.pending === true, '应先返回 pending: ' + v.out.slice(-300));
  const w = R.wl('wait', R.W, '--round', '1', '--wait-ms', '180000');
  expect(w.last && w.last.smoke && w.last.smoke.rolledBack === true && w.last.smoke.pass === false, 'wait 应给出 rolledBack: ' + w.out.slice(-400));
  expect(R.exists(`${snapDir}/r01.restored.tree`) && R.exists(`${snapDir}/r01.rejected.diff`), '缺 restored.tree 或 rejected.diff');
  expect(rd(R, 'app/b.txt') === 'B0' && !R.exists('app/c.txt'), '工作区应已退回: B=' + rd(R, 'app/b.txt'));
}));

const fail = await runScenarios(S);
rmSync(projects, { recursive: true, force: true });
process.exit(fail ? 1 : 0);
