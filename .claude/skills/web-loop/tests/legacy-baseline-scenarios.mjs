// [冻结的旧基线] 针对重构前的旧模板(label 为 refresh/capture/persist 等)写的场景,只用于证明外壳测得出旧毛病;不以 test- 开头,run-all 不跑。新设计的场景见 test-design-scenarios.mjs。
// 控制流场景(真跑 workflow-template.js,用 dryrun.mjs 外壳)。每个场景写「期望行为」,现有毛病会让对应场景 FAIL。
// 只跑某个:SCN='^T1' node test-dryrun-scenarios.mjs
import { A0, SUB_G1, V_G1, run, verdict, rnum, lensOf, byPrefix, byLabel, issuesFromPersist, exitText,
  pausedCalls, pausedCriteria, runScenarios, expect, expectNoError, checkSyntax } from './dryrun.mjs';

const mustIssue = (title, o = {}) => ({ title, severity: 'must', ...o });
const converged = r => /converged/.test(exitText(r)) && !/stalled|max-rounds/.test(exitText(r));

const S = [];
const sc = (id, title, fn) => S.push([id, title, fn]);

sc('G0', '模板语法可过(接受顶层 return)且缺省配置跑完不抛错', async () => {
  checkSyntax();
  const r = await run({ ...A0, maxRounds: 2, lenses: ['ux'] });
  expectNoError(r);
  expect(converged(r), '全 pass 的 run 应收敛: ' + exitText(r));
});

sc('G1', 'args 传 JSON 字符串与传对象,调用序列一致', async () => {
  const a = { ...A0, maxRounds: 1, lenses: ['ux', 'code'] };
  const r1 = await run(a, undefined, { argsForm: 'string' }), r2 = await run(a, undefined, { argsForm: 'object' });
  expectNoError(r1); expectNoError(r2);
  expect(JSON.stringify(r1.calls.map(c => c.label)) === JSON.stringify(r2.calls.map(c => c.label)), '两种 args 形态的 label 序列不同');
});

// ── 第 10 条:treadmill ──
const T_OPTS = { ...A0, goalSubgoals: SUB_G1 };
sc('T1', '真停滞(3 个 lens 各 1 条 must 原样不动)仍应暂停', async () => {
  const r = await run({ ...T_OPTS, lenses: ['ux', 'func', 'code'] }, (label) => {
    const lens = lensOf(label), n = rnum(label);
    if (lens) return verdict(lens, { ...V_G1, verdict: 'fail', issues: n === 1 ? [mustIssue(lens + ' m')] : [], knownIssuesStatus: n > 1 ? [{ id: `${lens}-r1-1`, stillPresent: true }] : [] });
  });
  expectNoError(r);
  expect(pausedCalls(r.calls).length > 0 || /stalled|paused/.test(exitText(r)), '真停滞没有暂停/停滞退出: ' + exitText(r));
});
sc('T2', '稳步推进(ux 报 5 条 must、每轮修 1 条、不新增;func/code 无 must)不应暂停', async () => {
  const r = await run({ ...T_OPTS, lenses: ['ux', 'func', 'code'] }, (label) => {
    const lens = lensOf(label), n = rnum(label);
    if (lens === 'ux') return verdict('ux', { ...V_G1, verdict: 'fail', issues: n === 1 ? [1, 2, 3, 4, 5].map(k => mustIssue('m' + k)) : [], knownIssuesStatus: n === 1 ? [] : [1, 2, 3, 4, 5].map(k => ({ id: `ux-r1-${k}`, stillPresent: k >= n })) });
    if (lens) return verdict(lens, V_G1);
  });
  expectNoError(r);
  expect(pausedCalls(r.calls).length === 0, '稳步推进被判暂停: ' + pausedCriteria(r.calls).join(','));
});
sc('T3', 'ux 每轮修一条同时新增一条、func 从无 must:不应因 func 暂停', async () => {
  const r = await run({ ...A0, maxRounds: 5, lenses: ['ux', 'func'] }, (label) => {
    const n = rnum(label);
    if (lensOf(label) === 'ux') return verdict('ux', { verdict: 'fail', issues: [mustIssue('new must ' + n)], knownIssuesStatus: n > 1 ? [{ id: `ux-r${n - 1}-1`, stillPresent: false }] : [] });
  });
  expectNoError(r);
  expect(!pausedCriteria(r.calls).includes('treadmill'), '全局累计新增 vs 单 lens 修复,误报 treadmill');
});
sc('T4', '已收敛的 run,SUMMARY/finalize 不挂 PAUSED,也不退成 stalled', async () => {
  const r = await run({ ...A0, maxRounds: 5, lenses: ['ux', 'func'] }, (label) => {
    if (label === 'review-ux-r01') return verdict('ux', { verdict: 'fail', issues: [mustIssue('u1')] });
    if (label === 'review-ux-r02') return verdict('ux', { knownIssuesStatus: [{ id: 'ux-r1-1', stillPresent: false }] });
    if (label === 'review-func-r02') return verdict('func', { verdict: 'fail', issues: [mustIssue('f2')] });
    if (label === 'review-func-r03') return verdict('func', { knownIssuesStatus: [{ id: 'func-r2-1', stillPresent: false }] });
  });
  expectNoError(r);
  expect(converged(r), '应收敛: ' + exitText(r));
  const fin = byLabel(r.calls, 'finalize');
  expect(!fin || !fin.prompt.includes('## ⚠ PAUSED'), 'finalize 仍带 PAUSED 节');
});

// ── 第 12 条:证据缺口不挡收敛;verdict 由台账推导 ──
sc('U1', '唯一的 must 标 unverifiable(截图配方问题)、子项全覆盖:应能收敛', async () => {
  const r = await run({ ...T_OPTS, maxRounds: 3, lenses: ['func'] }, (label) => {
    if (label === 'review-func-r01') return verdict('func', { ...V_G1, issues: [mustIssue('14 号截图截错框', { unverifiable: true, requiredStates: ['14-compare-box'] })] });
    if (lensOf(label)) return verdict('func', { ...V_G1, knownIssuesStatus: [{ id: 'func-r1-1', stillPresent: true, unverifiable: true }] });
  });
  expectNoError(r);
  expect(converged(r), 'unverifiable 挡住了收敛: ' + exitText(r));
});
sc('U2', '评审自报 fail 但台账只有 nice:应能收敛(verdict 由台账推导)', async () => {
  const r = await run({ ...T_OPTS, maxRounds: 3, lenses: ['func'] }, (label) => {
    if (lensOf(label)) return verdict('func', { ...V_G1, verdict: 'fail', issues: [{ title: '小建议', severity: 'nice' }] });
  });
  expectNoError(r);
  expect(converged(r), '自报 fail 挡住了收敛: ' + exitText(r));
});

// ── 第 14 条:台账保留全部字段 ──
sc('S1', '评审的 detail/evidence/matchesSubgoal/requiredStates 进台账,并出现在下一轮 implementer prompt', async () => {
  const r = await run({ ...A0, maxRounds: 2, lenses: ['ux'] }, (label) => {
    if (lensOf(label)) return verdict('ux', { verdict: 'fail', issues: [mustIssue('T' + rnum(label), { detail: 'DETAIL_MARK', evidence: 'EVID_MARK', matchesSubgoal: 'G1', requiredStates: ['S9'] })] });
  });
  expectNoError(r);
  const i2 = byLabel(r.calls, 'impl-r02').prompt;
  expect(i2.includes('DETAIL_MARK'), 'impl-r02 看不到 detail');
  expect(i2.includes('EVID_MARK'), 'impl-r02 看不到 evidence');
  const led = issuesFromPersist(r.calls, 'r01');
  if (led) for (const k of ['detail', 'evidence', 'matchesSubgoal', 'requiredStates']) expect(k in led[0], `台账缺字段 ${k}`);
});
sc('S1b', '评审记录文件名:写与读的两侧一致(两位数轮号),且写入侧拿得到评审正文', async () => {
  const r = await run({ ...A0, maxRounds: 2, lenses: ['ux'] }, (label) => {
    if (lensOf(label)) return verdict('ux', { verdict: 'fail', issues: [mustIssue('T' + rnum(label), { detail: 'DETAIL_MARK' })] });
  });
  expectNoError(r);
  const writers = [...byPrefix(r.calls, 'persist-r01'), ...byPrefix(r.calls, 'review-ux-r01')].map(c => c.prompt).join('\n');
  expect(!/reviews\/round_1\b/.test(writers), '写入侧用了不补零的 round_1');
  expect(writers.includes('reviews/round_01'), '写入侧没有 reviews/round_01');
  expect(byLabel(r.calls, 'impl-r02').prompt.includes('reviews/round_01'), '读取侧没指向 reviews/round_01');
});
sc('S2b', '同一子项连续 3 轮不可验证且 requiredStates 相同 → 触发 missingStates 暂停', async () => {
  const r = await run({ ...T_OPTS, maxRounds: 4, staleRounds: 9, lenses: ['func'] }, (label) => {
    const n = rnum(label);
    if (lensOf(label)) return verdict('func', { verdict: 'fail', knownIssuesStatus: n > 1 ? [{ id: 'func-r1-1', stillPresent: true, unverifiable: true }] : [],
      issues: [mustIssue('G1 看不到 r' + n, { unverifiable: true, matchesSubgoal: 'G1', requiredStates: ['05-open'] })] });
  });
  expectNoError(r);
  expect(pausedCriteria(r.calls).includes('missingStates'), 'missingStates 未触发; 暂停判据=' + JSON.stringify(pausedCriteria(r.calls)));
});

// ── 第 17 条:不轻信评审回填 ──
sc('S4', 'matchesIssueId 笔误(查无此 id)时,新问题按新问题入账,不被静默丢掉', async () => {
  const r = await run({ ...A0, maxRounds: 2, lenses: ['ux'] }, (label) => {
    if (label === 'review-ux-r01') return verdict('ux', { verdict: 'fail', issues: [mustIssue('A')] });
    if (label === 'review-ux-r02') return verdict('ux', { verdict: 'fail', knownIssuesStatus: [{ id: 'ux-r1-1', stillPresent: false }], issues: [mustIssue('B 新问题', { matchesIssueId: 'ux-r1-01' })] });
  });
  expectNoError(r);
  expect(!converged(r), '新 must B 被丢,错报收敛: ' + exitText(r));
  const led = issuesFromPersist(r.calls, 'r02');
  if (led) expect(led.some(i => i.title === 'B 新问题'), '台账里没有 B');
});
sc('S5', '评审回填错误的 lens 名:归属按调度侧已知的 lens', async () => {
  const r = await run({ ...A0, maxRounds: 1, lenses: ['ux', 'rival'] }, (label) => {
    if (label === 'review-rival-r01') return verdict('ux', { verdict: 'fail', issues: [mustIssue('rival 发现')] });
  });
  expectNoError(r);
  const led = issuesFromPersist(r.calls, 'r01');
  expect(led, '拿不到 r01 台账');
  const it = led.find(i => i.title === 'rival 发现');
  expect(it && it.lens === 'rival', `rival 的问题记在 ${it && it.lens} 名下`);
});

// ── 第 16 条 ──
sc('S6', 'lenses 不含 code:脚本自己插入的 infra 问题由脚本关闭,能收敛', async () => {
  const r = await run({ ...A0, maxRounds: 4, lenses: ['ux'] }, (label) => {
    if (label === 'refresh-r01') return { ready: false };
    if (lensOf(label)) return verdict('ux', { knownIssuesStatus: [{ id: 'infra-r01', stillPresent: false }] });
  });
  expectNoError(r);
  expect(converged(r), 'infra 条目关不掉: ' + exitText(r));
});

// ── 第 2 条 ──
sc('S7', '每轮截图都失败:连续两轮跳过评审就暂停,且已写台账', async () => {
  const r = await run({ ...A0, maxRounds: 5, lenses: ['ux', 'func', 'code'] }, (label) => {
    if (label.startsWith('capture')) return { shots: [{ state: '01', path: null, error: 'boom' }] };
  });
  expectNoError(r);
  expect(pausedCalls(r.calls).length > 0, '空转到 ' + r.calls.length + ' 个 agent 仍未暂停: ' + exitText(r));
  expect(byPrefix(r.calls, 'persist').length > 0, '跳过的轮次没有 persist');
  expect(r.calls.length < 30, `agent 数 ${r.calls.length} 过多`);
});
sc('S7b', 'implementer 返回空:capture 与评审照常执行,台账记一条 workflow 问题', async () => {
  const r = await run({ ...A0, maxRounds: 1, lenses: ['ux'] }, (label) => { if (label.startsWith('impl-')) return null; });
  expectNoError(r);
  expect(byPrefix(r.calls, 'capture').length > 0, '没有 capture');
  expect(byPrefix(r.calls, 'review-ux').length > 0, '没有评审');
  const led = issuesFromPersist(r.calls, 'r01');
  expect(led && led.some(i => i.lens === 'workflow'), '台账里没有 lens=workflow 的未交回条目');
});

// ── 第 13 条 ──
sc('S8', 'implementer 的返回值被直接使用:不派 read-impl-stuck;kind 传给 refresh;stuck 信号到评审', async () => {
  const r = await run({ ...A0, maxRounds: 2, lenses: ['code'] }, (label) => {
    if (label.startsWith('impl-')) return { reviewer_stuck: true, planRepetition: 'STUCK_MARK', kind: 'backend' };
    if (label.startsWith('read-impl-stuck-')) return { ok: false };
    if (lensOf(label)) return verdict('code', { verdict: 'fail', issues: [mustIssue('x' + label)] });
  });
  expectNoError(r);
  expect(byPrefix(r.calls, 'read-impl-stuck').length === 0, '仍在派 read-impl-stuck');
  expect(byLabel(r.calls, 'review-code-r02').prompt.includes('STUCK_MARK'), 'r02 code 评审没收到 implementer 的 stuck 信号');
  expect(byLabel(r.calls, 'refresh-r01').prompt.includes('backend'), 'refresh 没拿到 implementer 返回的 kind');
});
sc('S8b', 'implementer 不写 impl.md 也不影响刷新(refresh 不依赖 impl.md)', async () => {
  const r = await run({ ...A0, maxRounds: 1, lenses: ['ux'] }, (label, prompt) => {
    if (label.startsWith('refresh-') && /impl\.md/.test(prompt)) return { ready: false, note: 'impl.md 不存在' };
  });
  expectNoError(r);
  expect(byPrefix(r.calls, 'review-ux').length > 0, 'refresh 依赖 impl.md,缺文件整轮评审被跳过');
});

// ── 第 1 条:回滚(外壳层面只断言发出的指令;文件层面见 repro/tester/rollback_fs.mjs)──
sc('R1', 'smoke 红:回滚指令基于本轮快照 snapshots/r02,不再裸 git checkout -- .', async () => {
  const r = await run({ ...A0, maxRounds: 3, lenses: ['ux'] }, (label) => {
    if (label === 'smoke-r02') return { pass: false, summary: 'boom' };
    if (label === 'review-ux-r01') return verdict('ux', { verdict: 'fail', issues: [mustIssue('a')] });
  });
  expectNoError(r);
  const rb = byPrefix(r.calls, 'rollback')[0];
  expect(rb, 'smoke 红却没有 rollback 调用');
  expect(rb.label.endsWith('r02'), '回滚 label=' + rb.label);
  expect(rb.prompt.includes('snapshots/r02'), '回滚指令没指向 snapshots/r02');
  expect(!/git checkout -- \.(?!\w)/.test(rb.prompt), '回滚指令仍含裸 git checkout -- .');
  const impl2 = byLabel(r.calls, 'impl-r02').prompt;
  expect(impl2.includes('snapshots/r02'), 'impl-r02 开工前没有被要求做快照到 snapshots/r02');
});

// ── 第 3 条/第 15 条:human-hint ──
sc('H1', 'human-hint 不按确切轮号命名(human-hint-r7.md)在第 3 轮也会被读到', async () => {
  const r = await run({ ...A0, maxRounds: 3, lenses: ['ux'] }, (label) => {
    if (lensOf(label)) return verdict('ux', { verdict: 'fail', issues: [mustIssue('m' + rnum(label))] });
  });
  expectNoError(r);
  const p = byLabel(r.calls, 'impl-r03').prompt;
  expect(/human-hint-(r)?\*|human-hint-\*|human-hint-\S*\*/.test(p), 'impl-r03 只认确切文件名, 没有按通配符消费所有未消费的 hint');
});
sc('H2', 'implementer prompt 含 to-main 约束(不等回复、不 SendMessage)', async () => {
  const r = await run({ ...A0, maxRounds: 1, lenses: ['ux'] });
  expectNoError(r);
  const p = byLabel(r.calls, 'impl-r01').prompt;
  expect(/to-main-r01\.md/.test(p), '缺 to-main-r01.md');
  expect(/SendMessage/.test(p), '没有禁用 SendMessage 的明令');
});

// ── K7:某个 lens 返回 null / 抛错(parallel 按真语义记 null)──
sc('K7', '一个 lens 每轮都缺席(返回 null):不能空转到 maxRounds,须暂停或明确退出', async () => {
  const r = await run({ ...A0, maxRounds: 5, lenses: ['ux', 'rival'] }, (label) => { if (label.startsWith('review-rival-')) return null; });
  expectNoError(r);
  expect(!/max-rounds/.test(exitText(r)), '缺席 lens 导致空转到触顶: ' + exitText(r));
});
sc('K7b', '一个 lens 抛错(parallel 位置记 null,不拖垮整轮)', async () => {
  const r = await run({ ...A0, maxRounds: 3, lenses: ['ux', 'rival'] }, (label) => { if (label.startsWith('review-rival-')) throw new Error('agent died'); });
  expectNoError(r);
  expect(!/max-rounds/.test(exitText(r)), '抛错 lens 导致空转: ' + exitText(r));
});

const fail = await runScenarios(S);
process.exit(fail ? 1 : 0);
