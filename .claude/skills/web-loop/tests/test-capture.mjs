// C1:capture.mjs 的纯函数;C2:截图器集成(需要本机能解析到 playwright 与 chrome,否则跳过)。
import { readFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import { runScenarios, expect } from './dryrun.mjs';
import { SKILL, makeRepo, STATES, STATES_OK, PLAYWRIGHT_OK, UI_DIR } from './wl-fixture.mjs';

const cap = await import(join(SKILL, 'capture.mjs'));
const S = [];
const sc = (id, title, fn) => S.push([id, title, fn]);

sc('C1a', 'matchExpect:部分深比较、嵌套路径、不符时报路径', () => {
  expect(cap.matchExpect({ mode: 'a', box: 'x', extra: 1 }, { mode: 'a', box: 'x' }) === null, '部分比较应通过');
  expect(cap.matchExpect({ a: { b: 2 } }, { 'a.b': 2 }) === null, '嵌套路径 a.b 应能读');
  const m = cap.matchExpect({ box: '平台' }, { box: '放量突破' });
  expect(m && m.path === 'box' && /期望 放量突破 实际 平台/.test(m.message), '不符应报出路径与期望/实际: ' + JSON.stringify(m));
  expect(cap.matchExpect({ list: [1, 2] }, { list: [1, 2, 3] }) !== null, '数组长度不等应不符');
  expect(cap.matchExpect(null, { a: 1 }) !== null, 'actual 为 null 应不符');
});
sc('C1b', 'computeNewErrors:上一份缺失/没有该态不算;已有旧报错的态冒出新文本要抓出', () => {
  const mk = (...st) => ({ states: st.map(([state, pageErrors]) => ({ state, pageErrors })) });
  expect(cap.computeNewErrors(null, mk(['a', ['e']])).length === 0, '上一份缺失不算新');
  expect(cap.computeNewErrors(mk(['b', []]), mk(['a', ['e']])).length === 0, '上一份没有该态不算新');
  expect(cap.computeNewErrors(mk(['a', []]), mk(['a', ['TypeError x']])).join() === 'a', '无→有 应算新');
  expect(cap.computeNewErrors(mk(['a', ['Old err']]), mk(['a', ['Old err']])).length === 0, '同文本不算新');
  expect(cap.computeNewErrors(mk(['a', ['Old err']]), mk(['a', ['Old err', 'Brand new']])).join() === 'a', 'N2:旧报错之外冒新文本要抓出');
  expect(cap.computeNewErrors(mk(['a', ['Err at x.js:10:5']]), mk(['a', ['Err at x.js:12:9']])).length === 0, '仅行列号变化不算新');
});
sc('C1c', 'validateStates:拒重名、未知 step 键、非法态名;lintStates 提醒 ||', () => {
  expect(cap.validateStates(STATES_OK).length === 0, '合法配方应通过');
  expect(cap.validateStates([{ state: 'a' }, { state: 'a' }]).some(e => /重复/.test(e)), '应拒重名');
  expect(cap.validateStates([{ state: 'a b' }]).some(e => /不合法/.test(e)), '应拒非法态名');
  expect(cap.validateStates([{ state: 'a', steps: [{ hover: '#x' }] }]).some(e => /未知的键/.test(e)), '应拒未知 step 键');
  expect(cap.validateStates([{ state: 'a', steps: [{ wait: 1, click: '#x' }] }]).some(e => /恰好一个键/.test(e)), '应拒多键 step');
  expect(cap.validateStates([{ state: 'a', expect: { x: 1 } }]).some(e => /没有 probe/.test(e)), 'expect 无 probe 应拒');
  expect(cap.lintStates([{ state: 'a', probe: '({b: x || y})' }]).some(w => /\|\|/.test(w)), 'lint 应提醒 ||');
});
sc('C1d', 'buildSummary:okStates/failedStates/errorStates/newErrors', () => {
  const man = { states: [{ state: 'a', ok: true, pageErrors: [] }, { state: 'b', ok: false, pageErrors: [] }, { state: 'c', ok: true, pageErrors: ['E'] }] };
  const s = cap.buildSummary(man, { states: [{ state: 'c', pageErrors: [] }] });
  expect(s.okStates.join() === 'a,c' && s.failedStates.join() === 'b' && s.errorStates.join() === 'c' && s.newErrors.join() === 'c', JSON.stringify(s));
});

if (PLAYWRIGHT_OK) {
  sc('C2', '截图器集成:ok / expect 不符 / 选择器找不到 三个态 + contact', async () => {
    const R = makeRepo({ states: STATES });
    try {
      const { shoot, contact } = cap;
      const cfg = JSON.parse(readFileSync(join(R.W, 'args.json'), 'utf8'));
      cfg.viewport = { width: 1000, height: 700, deviceScaleFactor: 1 };
      const s = await shoot({ W: R.W, round: 1, cfg, root: R.repo });
      expect(s.okStates.join() === '01-a', 'okStates=' + s.okStates);
      expect(s.failedStates.join() === '02-b,03-c', 'failedStates=' + s.failedStates);
      const man = JSON.parse(readFileSync(join(R.W, 'shots/r01_manifest.json'), 'utf8'));
      const by = n => man.states.find(x => x.state === n);
      expect(/expect 不符：mode 期望 WRONG 实际 a/.test(by('02-b').error || ''), '02-b error=' + by('02-b').error);
      expect(by('03-c').ok === false && /nope/.test(by('03-c').error || ''), '03-c error=' + by('03-c').error);
      expect(existsSync(join(R.W, 'shots/r01_01-a.png')), '缺整页图');
      expect(by('01-a').crops.length === 1 && existsSync(by('01-a').crops[0].path), '缺局部图');
      expect(existsSync(join(R.W, 'shots/r01_02-b.failed.png')), '失败态应另存 .failed.png');
      expect(man.browser && man.viewport, 'manifest 缺 browser/viewport');
      expect(man.states.every(x => typeof x.shotRetries === 'number'), 'manifest 每个态应有 shotRetries 计数');
      const png = await contact({ W: R.W, round: 1, cfg, root: R.repo });
      expect(existsSync(png) && /r01_contact\.png$/.test(png), 'contact 路径=' + png);
    } finally { R.cleanup(); }
  });
  sc('C3', 'discover:每个看得见的可点控件一个态;选择器经复查唯一且命中同一元素;隐藏/禁用/外链不收;没选择器的与超上限的列出;不覆盖正式配方', async () => {
    const R = makeRepo({});
    try {
      R.w('app/d.html', `<!doctype html><meta charset=utf-8><body>
<button data-act="save">保存</button><button>保存</button><button>保存草稿</button>
<div><div role="tab" id="t1">Tab One</div></div><div><div role="tab">第二页</div></div>
<a href="#x">锚点</a><a href="https://example.com">外链</a>
<button style="display:none">隐藏</button><button disabled>禁用</button>
<span onclick="1">点我</span><span onclick="1">点我</span><button style="width:20px;height:20px"></button></body>`);
      const cfg = JSON.parse(readFileSync(join(R.W, 'args.json'), 'utf8'));
      cfg.url = 'file://' + join(R.repo, 'app/d.html'); cfg.viewport = { width: 1000, height: 700, deviceScaleFactor: 1 };
      const s = await cap.discover({ W: R.W, cfg, root: R.repo, max: 7 });
      const st = JSON.parse(readFileSync(s.out, 'utf8')), clicks = st.slice(1).map(x => x.steps[1].click);
      expect(st[0].state === '00-start' && cap.validateStates(st).length === 0, '草稿应以 00-start 开头且通过校验');
      expect(clicks.length === 7 && s.overCap.length === 1, `应收 7 个、超上限 1 个: ${clicks.length} / ${s.overCap}`);
      expect(s.skipped.length === 1 && /^button @/.test(s.skipped[0]), '只有图标的按钮应列进 skipped: ' + s.skipped);
      expect(clicks.includes('[data-act="save"]') && clicks.includes('#t1') && clicks.includes('button:has-text("保存") >> nth=1'), 'data-* / id / 同名第二个 选择器不对: ' + clicks.join(' ; '));
      expect(clicks.includes('[role="tab"]:has-text("第二页")'), '带 role 的应按 role 找: ' + clicks.join(' ; '));
      expect(!clicks.some(c => /隐藏|禁用|外链/.test(c)), '隐藏/禁用/外链不该收');
      let threw = false;
      try { await cap.discover({ W: R.W, cfg, root: R.repo, out: join(R.repo, cfg.statesPath) }); } catch { threw = true; }
      expect(threw, '--out 指向正式配方应拒绝');
    } finally { R.cleanup(); }
  });
} else console.log('SKIP C2/C3 (本机没有可解析的 playwright / chrome)');

const fail = await runScenarios(S);
process.exit(fail ? 1 : 0);
