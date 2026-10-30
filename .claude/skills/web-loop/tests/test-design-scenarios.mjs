// 新设计(design.md §3 测试计划)的控制流与判据场景。D=整条流程(外壳真跑 SHELL),
// 凡标「CORE」的直接调用 CORE 纯函数以便检查台账细节。只跑某个:SCN='^D12' node test-design-scenarios.mjs
import { THROW, newArgs, fakeVerify, okImpl, okReview, mustIssue2, runNew, run, sim, core, coreInit, coreStep, loadCoreSource,
  deepEqual, byPrefix, byLabel, runScenarios, expect, expectNoError, checkSyntax, STATES } from './dryrun.mjs';

const S = [];
const sc = (id, title, fn) => S.push([id, title, fn]);
const ret = r => { expect(r.result, '没有顶层返回值' + (r.error ? ': ' + r.error.message : '')); return r.result; };
const issueOf = (res, id) => (res.ledger.issues || []).find(i => i.id === id);
const labels = r => r.calls.map(c => c.label);
const rnd = n => 'r' + String(n).padStart(2, '0');
const ux = (known = [], issues = [], o = {}) => ({ known, issues, subgoals: [{ id: 'G1', status: 'unmet', evidence: 'e' }], directions: [], ...o });
const gone = id => ({ id, status: 'gone', evidence: 'e' }), present = id => ({ id, status: 'present', evidence: 'e' });

// 稳步推进:r1 报 total 条;第 n(≥2)轮只剩 k>=n-1 的开着,其中 k==n-1 这条 gone
const steady = (L, n, total, subgoalMetAtEnd = false) => {
  if (n === 1) return { known: [], issues: Array.from({ length: total }, (_, i) => mustIssue2(L + (i + 1))), subgoals: [{ id: 'G1', status: 'unmet', evidence: 'e' }], directions: [] };
  const known = []; for (let k = n - 1; k <= total; k++) known.push(k === n - 1 ? gone(`${L}-r1-${k}`) : present(`${L}-r1-${k}`));
  return { known, issues: [], subgoals: [{ id: 'G1', status: subgoalMetAtEnd && n - 1 >= total ? 'met' : 'unmet', evidence: 'e' }], directions: [] };
};
// ── 出口判据 ──
sc('D1', 'T1 真停滞:ux 把 r1 的 2 条原样报 present,子项一直 unmet;第 3 轮 stalled', async () => {
  const a = newArgs({ lenses: ['ux'], maxRounds: 6 });
  const r = await runNew(a, { review: (L, n) => n === 1 ? ux([], [mustIssue2('A'), mustIssue2('B')]) : ux([present('ux-r1-1'), present('ux-r1-2')]) });
  expectNoError(r); const res = ret(r);
  expect(res.exitReason === 'stalled' && res.rounds === 3, `exit=${res.exitReason} rounds=${res.rounds}`);
});
sc('D2', 'T2 稳步推进:r1 报 5 条,之后每轮 gone 1 条;不 stalled,最后一条 gone 且子项 met 的那轮 converged', async () => {
  const a = newArgs({ lenses: ['ux'], maxRounds: 8 });
  const r = await runNew(a, { review: (L, n) => steady('ux', n, 5, true) });
  expectNoError(r); const res = ret(r);
  expect(res.exitReason === 'converged' && res.rounds === 6, `exit=${res.exitReason} rounds=${res.rounds}`);
});
sc('D3', '多角度里 code 从不报 must,其余每轮修好 1 条:前 3 轮不出现 stalled/blocked', async () => {
  const a = newArgs({ lenses: ['ux', 'func', 'code'], maxRounds: 3, staleRounds: 2 });
  const r = await runNew(a, { review: (L, n) => L === 'code' ? undefined : steady(L, n, 4) });
  expectNoError(r); const res = ret(r);
  expect(!['stalled', 'blocked'].includes(res.exitReason), 'exit=' + res.exitReason);
});
sc('D4', 'S7 capture 每轮 okStates 为空:第 2 轮 blocked;评审一次都没派', async () => {
  const a = newArgs({ lenses: ['ux'] });
  const r = await runNew(a, { verify: () => ({ okStates: [], failed: [{ state: '01-a', error: 'boom' }] }) });
  expectNoError(r); const res = ret(r);
  expect(res.exitReason === 'blocked' && res.rounds === 2, `exit=${res.exitReason} rounds=${res.rounds}`);
  expect(byPrefix(r.calls, 'review-').length === 0, '派了评审');
  expect(String(res.exitDetail || '').length > 0, 'exitDetail 为空');
});
sc('D5', 'implementer 返回 null:verify 的 kind 取上一轮(首轮 frontend);照常评审;不新增 must', async () => {
  const a = newArgs({ lenses: ['ux'], maxRounds: 3 });
  const r = await runNew(a, { impl: n => n === 1 ? null : n === 2 ? okImpl({ kind: 'none' }) : null,
    review: () => ux() });
  expectNoError(r);
  expect(/--kind frontend/.test(byLabel(r.calls, 'verify-r01').prompt), 'r1 kind 应为 frontend');
  expect(/--kind none/.test(byLabel(r.calls, 'verify-r03').prompt), 'r3 kind 应取上一轮 none');
  expect(byPrefix(r.calls, 'review-ux').length === 3, '本轮没有照常评审');
  expect(!(ret(r).ledger.issues || []).some(i => i.lens === 'workflow'), 'impl 为 null 不应新增 must');
});
sc('D5b', 'CORE:impl 为 null 时 rec.implOk=false', async () => {
  const { cfg, S: st } = coreInit(newArgs());
  const rec = coreStep(cfg, st, 1, { impl: null });
  expect(rec.implOk === false, 'implOk=' + rec.implOk);
});
sc('D6', 'U1 唯一 must 标 unverifiable、requiredStates 点名没截成功的态、子项 met:evidence-gap,不是 converged', async () => {
  const a = newArgs({ lenses: ['ux'] });
  const r = await runNew(a, { verify: () => ({ okStates: ['01-a'] }),
    review: () => ({ issues: [mustIssue2('配方截错', { unverifiable: true, requiredStates: ['14-x'] })] }) });
  expectNoError(r); const res = ret(r);
  expect(res.exitReason === 'evidence-gap', 'exit=' + res.exitReason);
});
sc('D6b', 'CORE:requiredStates 点名的态本轮已截成功 → 按确证处理,记 unverifiableRejected', async () => {
  const { cfg, S: st } = coreInit(newArgs({ lenses: ['ux'] }));
  const rec = coreStep(cfg, st, 1, { verify: fakeVerify({ round: 1, okStates: ['01-a', '14-x'] }),
    reviews: [okReview(cfg, 'ux', { issues: [mustIssue2('x', { unverifiable: true, requiredStates: ['14-x'] })] })] });
  const it = st.issues[0];
  expect(it && !it.unverifiable, '应按确证处理');
  expect(rec.unverifiableRejected && rec.unverifiableRejected.length > 0, 'unverifiableRejected 无记录');
  expect(st.exit !== 'evidence-gap', 'exit=' + st.exit);
});
sc('D7', 'U2 评审只报 nice,子项 met:converged', async () => {
  const a = newArgs({ lenses: ['ux'] });
  const r = await runNew(a, { review: () => ({ issues: [{ title: '小建议', severity: 'nice', detail: 'd', evidence: 'e' }] }) });
  expectNoError(r);
  expect(ret(r).exitReason === 'converged', 'exit=' + ret(r).exitReason);
});
sc('D8', 'CORE:S4 matchesIssueId 写成不存在的 id → 按新条目入账,badMatch 有记录', async () => {
  const { cfg, S: st } = coreInit(newArgs({ lenses: ['ux'] }));
  coreStep(cfg, st, 1, { reviews: [okReview(cfg, 'ux', { issues: [mustIssue2('A')] })] });
  const rec = coreStep(cfg, st, 2, { reviews: [okReview(cfg, 'ux', { known: [{ id: 'ux-r1-1', status: 'gone', evidence: 'e' }], issues: [mustIssue2('B 新', { matchesIssueId: 'ux-r1-01' })] })] });
  expect(st.issues.some(i => i.title === 'B 新' && i.status === 'open'), '新条目 B 被丢');
  expect((rec.badMatch || []).includes('ux-r1-01'), 'badMatch 无记录');
});
sc('D9', 'K7 一个角度连续两个可评审轮都返回 null:blocked,detail 点名角度', async () => {
  const a = newArgs({ lenses: ['ux', 'rival'], maxRounds: 5 });
  const r = await runNew(a, { review: L => L === 'rival' ? null : undefined });
  expectNoError(r); const res = ret(r);
  expect(res.exitReason === 'blocked', 'exit=' + res.exitReason);
  expect(/rival/.test(res.exitDetail || ''), 'detail 未点名 rival: ' + res.exitDetail);
});
sc('D10', 'S6 只有 ux、r1 verify 返回 rolledBack、r2 全通过且子项 met:r1 不评审并立 wf-regress;r2 wf-regress fixed 且不计进展;r2 converged', async () => {
  const a = newArgs({ lenses: ['ux'] });
  const r = await runNew(a, { verify: n => n === 1 ? { smokePass: false, rolledBack: true } : {} });
  expectNoError(r); const res = ret(r);
  expect(byPrefix(r.calls, 'review-ux-r01').length === 0, 'r1 不应评审');
  expect(res.exitReason === 'converged' && res.rounds === 2, `exit=${res.exitReason} rounds=${res.rounds}`);
  const w = issueOf(res, 'wf-regress');
  expect(w && w.status === 'fixed', 'wf-regress 状态=' + (w && w.status));
  const { cfg, S: st } = coreInit(a);
  coreStep(cfg, st, 1, { verify: fakeVerify({ round: 1, smokePass: false, rolledBack: true }) });
  expect(st.issues.find(i => i.id === 'wf-regress')?.status === 'open', 'r1 应立 wf-regress');
  coreStep(cfg, st, 2, {});                                    // 第 1 个可评审轮,只作起点
  const rec3 = coreStep(cfg, st, 3, { verify: fakeVerify({ round: 3 }) });
  expect(rec3.progress === false, '关闭 wf-regress 不应计进展(此处用「无新进展轮」旁证)');
});
sc('D10b', 'verify 返回 envBroken:当轮 blocked,detail 写环境或基线坏了', async () => {
  const a = newArgs({ lenses: ['ux'] });
  const r = await runNew(a, { verify: () => ({ smokePass: false, envBroken: true }) });
  expectNoError(r); const res = ret(r);
  expect(res.exitReason === 'blocked' && res.rounds === 1, `exit=${res.exitReason} rounds=${res.rounds}`);
  expect(/环境|基线/.test(res.exitDetail || ''), 'detail=' + res.exitDetail);
});
sc('D10c', '连续两轮 rolledBack:第 2 轮 blocked', async () => {
  const a = newArgs({ lenses: ['ux'], maxRounds: 5 });
  const r = await runNew(a, { verify: () => ({ smokePass: false, rolledBack: true }) });
  expectNoError(r); const res = ret(r);
  expect(res.exitReason === 'blocked' && res.rounds === 2, `exit=${res.exitReason} rounds=${res.rounds}`);
});
// ── 台账归并(CORE) ──
const two = () => coreInit(newArgs({ lenses: ['ux', 'rival'], goalSubgoals: [{ id: 'G1', desc: 'd', lenses: ['ux'] }] }));
const rv = (cfg, o) => cfg.lenses.map(L => okReview(cfg, L, o[L] || {}));
sc('D11', 'K6 负责角度 gone、其他角度同轮 matches 该条:关闭,记一条 dissent,不重开', async () => {
  const { cfg, S: st } = two();
  coreStep(cfg, st, 1, { reviews: rv(cfg, { ux: { issues: [mustIssue2('A')] } }) });
  coreStep(cfg, st, 2, { reviews: rv(cfg, { ux: { known: [gone('ux-r1-1')] }, rival: { issues: [mustIssue2('A 同', { matchesIssueId: 'ux-r1-1' })] } }) });
  const it = st.issues.find(i => i.id === 'ux-r1-1');
  expect(it.status === 'fixed', 'status=' + it.status);
  expect((it.dissent || []).length === 1, 'dissent=' + (it.dissent || []).length);
});
sc('D12', 'K6 修好后另一角度 matches 重开(reopenedBy);负责角度 gone → fixed+disputed;再 matches 只记 dissent', async () => {
  const { cfg, S: st } = two();
  coreStep(cfg, st, 1, { reviews: rv(cfg, { ux: { issues: [mustIssue2('A')] } }) });
  coreStep(cfg, st, 2, { reviews: rv(cfg, { ux: { known: [gone('ux-r1-1')] } }) });
  coreStep(cfg, st, 3, { reviews: rv(cfg, { rival: { issues: [mustIssue2('A 复现', { matchesIssueId: 'ux-r1-1' })] } }) });
  let it = st.issues.find(i => i.id === 'ux-r1-1');
  expect(it.status === 'open' && it.reopenedBy === 'rival', `r3 status=${it.status} reopenedBy=${it.reopenedBy}`);
  coreStep(cfg, st, 4, { reviews: rv(cfg, { ux: { known: [gone('ux-r1-1')] } }) });
  it = st.issues.find(i => i.id === 'ux-r1-1');
  expect(it.status === 'fixed' && it.disputed === true, `r4 status=${it.status} disputed=${it.disputed}`);
  coreStep(cfg, st, 5, { reviews: rv(cfg, { rival: { issues: [mustIssue2('A 又', { matchesIssueId: 'ux-r1-1' })] } }) });
  it = st.issues.find(i => i.id === 'ux-r1-1');
  expect(it.status === 'fixed' && (it.dissent || []).length >= 1, `r5 status=${it.status}`);
});
sc('D13', 'CORE:负责角度自己 matches 一条已修好的条目 → 重开,regressions=1', async () => {
  const { cfg, S: st } = two();
  coreStep(cfg, st, 1, { reviews: rv(cfg, { ux: { issues: [mustIssue2('A')] } }) });
  coreStep(cfg, st, 2, { reviews: rv(cfg, { ux: { known: [gone('ux-r1-1')] } }) });
  coreStep(cfg, st, 3, { reviews: rv(cfg, { ux: { issues: [mustIssue2('A 回来', { matchesIssueId: 'ux-r1-1' })] } }) });
  const it = st.issues.find(i => i.id === 'ux-r1-1');
  expect(it.status === 'open' && it.regressions === 1, `status=${it.status} regressions=${it.regressions}`);
});
sc('D14', 'CORE:verify.failed 含态 X → wf-state-X 先开后关;关闭那轮 progress=true', async () => {
  const { cfg, S: st } = coreInit(newArgs({ lenses: ['ux'] }));
  coreStep(cfg, st, 1, { verify: fakeVerify({ round: 1, okStates: ['01-a'], failed: [{ state: 'X', error: 'e' }] }) });
  expect(st.issues.find(i => i.id === 'wf-state-X')?.status === 'open', 'wf-state-X 应开着');
  const rec = coreStep(cfg, st, 2, { verify: fakeVerify({ round: 2, okStates: ['01-a', 'X'] }) });
  expect(st.issues.find(i => i.id === 'wf-state-X')?.status === 'fixed', 'wf-state-X 应已关');
  expect(rec.progress === true, 'progress=' + rec.progress);
});
sc('D15', 'CORE:newErrors 含 Y → 立 wf-pageerror-Y;Y 成功且不在 errorStates 时关闭', async () => {
  const { cfg, S: st } = coreInit(newArgs({ lenses: ['ux'] }));
  coreStep(cfg, st, 1, { verify: fakeVerify({ round: 1, okStates: ['01-a', 'Y'], errorStates: ['Y'], newErrors: ['Y'] }) });
  expect(st.issues.find(i => i.id === 'wf-pageerror-Y')?.status === 'open', '应立 wf-pageerror-Y');
  coreStep(cfg, st, 2, { verify: fakeVerify({ round: 2, okStates: ['01-a', 'Y'] }) });
  expect(st.issues.find(i => i.id === 'wf-pageerror-Y')?.status === 'fixed', '应关闭');
});
sc('D16', 'CORE:verify 的 sig 被改坏 → 照常评审,本轮不开关 wf 条目,sigOk=false', async () => {
  const { cfg, S: st } = coreInit(newArgs({ lenses: ['ux'] }));
  const rec = coreStep(cfg, st, 1, { verify: fakeVerify({ round: 1, failed: [{ state: 'X', error: 'e' }], tamper: true }) });
  expect(rec.sigOk === false, 'sigOk=' + rec.sigOk);
  expect(rec.reviewed, '应照常评审');
  expect(!st.issues.some(i => i.lens === 'workflow'), '不应开 wf 条目');
});
sc('D17', 'impl 交回 override:waive 有效 id 生效(评审 prompt 里没有它)、无效 id 进 overrideErrors、两个 key 进下一轮 intake 的 --done', async () => {
  const a = newArgs({ lenses: ['ux'], maxRounds: 3, staleRounds: 9 });
  const r = await runNew(a, {
    impl: n => n === 2 ? okImpl({ overrides: [{ key: 'override-a.json#0', id: 'ux-r1-1', action: 'waive', note: 'n' }, { key: 'override-a.json#1', id: 'nope-r9-9', action: 'waive', note: 'n' }] }) : undefined,
    review: (L, n) => n === 1 ? ux([], [mustIssue2('WAIVE_ME')]) : ux() });
  expectNoError(r);
  expect(!byLabel(r.calls, 'review-ux-r02').prompt.includes('WAIVE_ME'), '被 waive 的条目仍出现在评审 prompt');
  const p3 = byLabel(r.calls, 'impl-r03').prompt;
  expect(p3.includes('override-a.json#0') && p3.includes('override-a.json#1'), 'impl-r03 的 --done 缺这两个 key');
  const { cfg, S: st } = coreInit(a);
  coreStep(cfg, st, 1, { reviews: [okReview(cfg, 'ux', { issues: [mustIssue2('W')] })] });
  coreStep(cfg, st, 2, { impl: okImpl({ overrides: [{ key: 'k#0', id: 'ux-r1-1', action: 'waive', note: 'n' }, { key: 'k#1', id: 'zzz', action: 'waive', note: 'n' }] }) });
  expect(st.issues[0].status === 'waived', 'status=' + st.issues[0].status);
  expect(st.overrideErrors.length === 1, 'overrideErrors=' + st.overrideErrors.length);
  expect(st.doneControl.includes('k#0') && st.doneControl.includes('k#1'), 'doneControl 缺 key');
});
sc('D18', 'impl 交回 attempts → 下一轮 impl prompt 出现该做法与「上轮评审仍判存在」', async () => {
  const a = newArgs({ lenses: ['ux'], maxRounds: 3, staleRounds: 9 });
  const r = await runNew(a, {
    impl: n => n === 1 ? undefined : okImpl({ attempts: [{ issueId: 'ux-r1-1', approach: 'APPROACH_MARK' }] }),
    review: (L, n) => n === 1 ? ux([], [mustIssue2('A')]) : ux([present('ux-r1-1')]) });
  expectNoError(r);
  const p = byLabel(r.calls, 'impl-r03').prompt;
  expect(p.includes('APPROACH_MARK'), 'r3 prompt 无 attempts');
  expect(p.includes('上轮评审仍判存在'), 'r3 prompt 无「上轮评审仍判存在」');
});
sc('D19', '6 角度、maxAgents=20:第 2 轮后以 budget 结束,用掉 16 个', async () => {
  const L6 = ['ux', 'func', 'code', 'rival', 'razor', 'newbie'];
  const a = newArgs({ lenses: L6, maxAgents: 20, maxRounds: 8, staleRounds: 8, goalSubgoals: [{ id: 'G1', desc: 'd', lenses: ['ux'] }] });
  const r = await runNew(a, { review: (L, n) => L === 'ux' ? ux([], n === 1 ? [mustIssue2('x')] : [], { known: n === 1 ? [] : [present('ux-r1-1')] }) : undefined });
  expectNoError(r); const res = ret(r);
  expect(res.exitReason === 'budget', 'exit=' + res.exitReason);
  expect(r.calls.length === 16, 'agent 数=' + r.calls.length);
});
sc('D20', '第 2 轮 impl 抛错(预算耗尽):budget 结束,不崩,有顶层返回值', async () => {
  const a = newArgs({ lenses: ['ux'], maxRounds: 5, staleRounds: 9, debug: true });
  const r = await runNew(a, { impl: n => n === 2 ? THROW : undefined, review: () => ux() });
  expectNoError(r);
  expect(ret(r).exitReason === 'budget', 'exit=' + ret(r).exitReason);
  expect(ret(r).state.round === 1, 'impl 抛错的轮不应归并: round=' + ret(r).state.round);
});
sc('D21', 'CORE:形状异常的 impl / verify / 评审结果不崩;评审算缺席并记 malformed', async () => {
  const { cfg, S: st } = coreInit(newArgs({ lenses: ['ux'] }));
  const rec = coreStep(cfg, st, 1, { impl: { kind: 'frontend', summary: 's', changedFiles: 'oops' },
    reviews: [{ known: [], subgoals: [], issues: 'oops', directions: [] }] });
  expect((rec.missingLenses || []).includes('ux'), '异常评审应算缺席');
  expect((rec.malformed || []).length > 0, 'rec.malformed 无记录');
  coreStep(cfg, st, 2, { verify: { result: { round: 2 } } });          // 缺 smoke → 当作 null
  coreStep(cfg, st, 3, { verify: { result: 'string' } });
});

// ── 续跑与入口校验 ──
function seedLedger() {
  const { cfg, S: st } = coreInit(newArgs({ lenses: ['ux', 'func'], goalSubgoals: [{ id: 'G1', desc: 'd', lenses: ['ux'] }] }));
  for (const n of [1, 2, 3]) coreStep(cfg, st, n, { reviews: [okReview(cfg, 'ux', { issues: n === 1 ? [mustIssue2('SEED_UX_TITLE')] : [], known: n === 1 ? [] : [present('ux-r1-1')], subgoals: [{ id: 'G1', status: 'unmet', evidence: 'e' }] }),
    okReview(cfg, 'func', { issues: n === 1 ? [mustIssue2('SEED_FUNC_TITLE')] : [], known: n === 1 ? [] : [present('func-r1-1')] })] });
  return core().toSeed(st);
}
sc('D22', '续跑:INJECTED.seed 的 round=3 带开着的条目:第一个 label 就是 impl-r04;impl prompt 有延续条目;负责角度不在新 lenses 里的条目置 waived', async () => {
  const led = seedLedger();
  const a = newArgs({ lenses: ['ux'], continueFrom: '.claude/web-loop/old', maxRounds: 1 });
  const r = await run(a, sim(a, { review: () => ux() }), { seed: led });
  expectNoError(r);
  expect(labels(r)[0] === 'impl-r04', '第一个 label=' + labels(r)[0]);
  expect(byLabel(r.calls, 'impl-r04').prompt.includes('SEED_UX_TITLE'), 'impl-r04 无延续条目');
  const { S: st } = coreInit(newArgs({ lenses: ['ux'] }), led);
  expect(st.issues.find(i => i.id === 'func-r1-1')?.status === 'waived', 'func 条目未置 waived');
});
sc('D23', 'INJECTED.seed 的 v 不是 1:一个 agent 都没调就 throw BLOCKED', async () => {
  const led = { ...seedLedger(), v: 2 };
  const a = newArgs({ lenses: ['ux', 'func'] });
  const r = await run(a, sim(a, {}), { seed: led });
  expect(r.error && /^BLOCKED/.test(r.error.message), '应 throw BLOCKED: ' + (r.error && r.error.message));
  expect(r.calls.length === 0, '调了 ' + r.calls.length + ' 个 agent');
});
sc('D24', 'INJECTED 为 null(未经 init)或 args 无效:一个 agent 都没调就 throw BLOCKED', async () => {
  const a = newArgs();
  const r1 = await run(a, sim(a, {}), { injected: null });
  expect(r1.error && /^BLOCKED/.test(r1.error.message) && r1.calls.length === 0, 'INJECTED=null: ' + (r1.error && r1.error.message));
  const bad = newArgs({ goal: '' });
  const r2 = await run(bad, sim(bad, {}));
  expect(r2.error && /^BLOCKED/.test(r2.error.message) && r2.calls.length === 0, 'args 无效: ' + (r2.error && r2.error.message));
});

// ── 一致性 ──
sc('D25', '回放一致:跑完的 calls 转成假 journal → replay 得到的状态与 SHELL 最终的状态(debug:true)深度相等,出口相同', async () => {
  const a = newArgs({ lenses: ['ux', 'func'], maxRounds: 4, staleRounds: 9, debug: true, goalSubgoals: [{ id: 'G1', desc: 'd', lenses: ['ux'] }] });
  const r = await runNew(a, { review: (L, n) => L === 'ux' ? (n === 1 ? ux([], [mustIssue2('A'), mustIssue2('B')]) : ux([gone('ux-r1-1'), present('ux-r1-2')])) : undefined,
    verify: n => n === 3 ? { smokePass: false, rolledBack: true } : undefined });
  expectNoError(r); const res = ret(r);
  expect(res.state, 'debug:true 但返回值没有 state');
  const results = {}, started = new Set();
  for (const c of r.calls) { started.add(c.label); if (c.result !== undefined) results[c.label] = c.result; }
  const { cfg } = coreInit(a);
  const rep = core().replay(cfg, null, { results, started: [...started] }, 'end');
  const Sx = rep.S || rep;
  expect(deepEqual(Sx, res.state), '回放得到的 S 与 SHELL 的 S 不同');
  expect((rep.exitReason ?? Sx.exit) === res.exitReason, `出口不同 replay=${rep.exitReason ?? Sx.exit} shell=${res.exitReason}`);
});
sc('D25b', '回放一致(impl 抛错路径):第 2 或第 3 轮 impl 抛错,SHELL 不归并该轮;抛错的 label 进 started 或干脆不进,replay 结果都相同', async () => {
  for (const throwAt of [2, 3]) for (const startedIn of [true, false]) {
    const a = newArgs({ lenses: ['ux'], maxRounds: 5, staleRounds: 9, debug: true });
    const r = await runNew(a, { impl: n => n === throwAt ? THROW : undefined, review: () => ux() });
    expectNoError(r); const res = ret(r);
    expect(res.exitReason === 'budget', `throwAt=${throwAt} SHELL 出口=${res.exitReason}`);
    const results = {}, started = [];
    for (const c of r.calls) { if (!startedIn && c.threw) continue; started.push(c.label); if (c.result !== undefined && !c.threw) results[c.label] = c.result; }
    const { cfg } = coreInit(a);
    const rep = core().replay(cfg, null, { results, started }, 'end');
    const strip = x => { const { exit, exitDetail, ...rest } = x; return rest; };      // journal 里看不到抛错本身,出口只能回放成 interrupted(设计如此)
    const tag = `throwAt=${throwAt} startedIn=${startedIn}`;
    expect(res.state.round === throwAt - 1, tag + ' SHELL 应只归并到 r' + (throwAt - 1));
    expect(deepEqual(strip(rep.S), strip(res.state)), tag + ' 回放的 S 与 SHELL 不同(出口除外)');
    expect(rep.exitReason === 'interrupted', tag + ' replay 出口=' + rep.exitReason);
  }
});
sc('D43', 'I4 data 档的 .md 刷新被退回后强制 data:r2 的 verify prompt 含 --kind data 与 --refreshed、effort=medium;r2 刷新成功后 r3 回到 frontend', async () => {
  const a = newArgs({ lenses: ['ux'], maxRounds: 4, staleRounds: 9, refreshDataCmd: 'docs/refresh.md', debug: true });
  const r = await runNew(a, { impl: n => okImpl({ kind: n === 1 ? 'data' : 'frontend' }),
    verify: n => n === 1 ? { smokePass: false, rolledBack: true } : undefined, review: () => ux() });
  expectNoError(r);
  const v2 = byLabel(r.calls, 'verify-r02'), v3 = byLabel(r.calls, 'verify-r03');
  expect(/--kind data/.test(v2.prompt) && /--refreshed/.test(v2.prompt), 'verify-r02 应强制 data 且带 --refreshed: ' + v2.prompt.slice(0, 300));
  expect(v2.opts.effort === 'medium', 'verify-r02 effort=' + v2.opts.effort);
  expect(/--kind frontend/.test(v3.prompt), 'r2 刷新成功后 r3 应回到 frontend');
});
sc('D44', 'L4 回归:verify 结果的四种形式(字符串/带杂讯字符串/已解析对象/包一层 {line}):reviewGate 都认,sigOk 为 true;pending 行、乱码、null 不认', async () => {
  const C = core();
  for (const form of ['string', 'noisy', 'object', 'wrapped']) {
    const g = C.reviewGate(fakeVerify({ round: 1, form }));
    expect(g.reviewable === true && g.sigOk !== false, `form=${form} gate=${JSON.stringify(g)}`);
    const st = C.normalizeVerify(fakeVerify({ round: 1, form }));
    expect(st && st.round === 1, `form=${form} normalizeVerify 取不出`);
  }
  for (const [name, v] of [['pending 行', { result: '{"pending":true,"round":1}' }], ['乱码', { result: 'blah blah' }], ['null', { result: null }], ['整个为 null', null]])
    expect(C.reviewGate(v).reviewable !== true, name + ' 不应可评审');
});
sc('D45', 'L4 回归:第 1 轮 verify 返回包了一层的 {result:{line:...}} 时,第 1 轮照常派评审', async () => {
  const a = newArgs({ lenses: ['ux'], maxRounds: 1 });
  const r = await runNew(a, { verify: n => fakeVerify({ round: n, form: 'wrapped' }) });
  expectNoError(r);
  expect(byPrefix(r.calls, 'review-ux-r01').length === 1, '第 1 轮应派评审');
  expect(ret(r).state.rounds[0].sigOk === true, 'sigOk 应为 true');
});
sc('D46', 'VERIFY_SCHEMA.result 约定为字符串(或 null)', async () => {
  const t = core().VERIFY_SCHEMA.properties.result.type;
  expect([].concat(t).includes('string'), 'VERIFY_SCHEMA.result.type=' + JSON.stringify(t));
});
sc('D47', '结果行的 round 与本轮不同(过期的 verify 结果):sigOk=false、照常评审、不开关 wf 条目', async () => {
  const { cfg, S: st } = coreInit(newArgs({ lenses: ['ux'] }));
  coreStep(cfg, st, 1, {});
  const rec = coreStep(cfg, st, 2, { verify: fakeVerify({ round: 1, failed: [{ state: 'X', error: 'e' }] }) });
  expect(rec.sigOk === false, 'sigOk=' + rec.sigOk);
  expect(rec.reviewed === true, '应照常评审');
  expect(!st.issues.some(i => i.id === 'wf-state-X'), '不应开 wf-state-X');
  expect(core().reviewGate(fakeVerify({ round: 1 })).sigOk !== false, '不传 round 时行为不变');
});
sc('D41', '子项合成状态 pending 排在 unverifiable 前:有负责角度没表态时不走 evidence-gap', async () => {
  const { cfg, S: st } = coreInit(newArgs({ lenses: ['ux', 'func'], goalSubgoals: [{ id: 'G1', desc: 'd', lenses: ['ux', 'func'] }] }));
  coreStep(cfg, st, 1, { reviews: [okReview(cfg, 'ux', { subgoals: [{ id: 'G1', status: 'unverifiable', evidence: 'e', requiredStates: ['X-missing'] }] }),
    okReview(cfg, 'func', { subgoals: [] })] });
  expect(st.exit !== 'evidence-gap' && st.exit !== 'converged', 'exit=' + st.exit);
});
sc('D26', 'label/类型/effort:每轮依次 impl、verify、各 review;任何调用都不带 model;verify 不带 agentType 且 low;impl 不带 agentType;review 带 Explore', async () => {
  const a = newArgs({ lenses: ['ux', 'func'], maxRounds: 1 });
  const r = await runNew(a, {});
  expectNoError(r);
  expect(labels(r).join() === 'impl-r01,verify-r01,review-ux-r01,review-func-r01', labels(r).join());
  const o = l => byLabel(r.calls, l).opts;
  for (const c of r.calls) { expect(c.opts.model === undefined, c.label + ' 带了 model'); expect(c.opts.schema && c.opts.schema.type === 'object', c.label + ' 缺 schema'); }
  expect(o('verify-r01').agentType === undefined && o('verify-r01').effort === 'low', 'verify opts=' + JSON.stringify(o('verify-r01')));
  expect(o('impl-r01').agentType === undefined && o('impl-r01').effort === undefined, 'impl opts=' + JSON.stringify(o('impl-r01')));
  expect(o('review-ux-r01').agentType === 'Explore' && o('review-ux-r01').effort === undefined, 'review opts=' + JSON.stringify(o('review-ux-r01')));
});
sc('D28', '冻结标准:impl 与评审 prompt 指向 <workdir>/rubric.md,不含 args.rubricPath 原路径', async () => {
  const a = newArgs({ lenses: ['ux'], maxRounds: 1, rubricPath: 'docs/SRC_RUBRIC_PATH.md' });
  const r = await runNew(a, {});
  expectNoError(r);
  for (const l of ['impl-r01', 'review-ux-r01']) {
    const p = byLabel(r.calls, l).prompt;
    expect(p.includes('.claude/web-loop/rt/rubric.md'), l + ' 未指向冻结的 rubric.md');
    expect(!p.includes('SRC_RUBRIC_PATH'), l + ' 仍含原 rubricPath');
  }
});
sc('D29', '自定义角度 flow:角色说明按 rubric.md「角度 flow」专节,并写明不能点击', async () => {
  const a = newArgs({ lenses: ['ux', 'flow'], maxRounds: 1 });
  const r = await runNew(a, {});
  expectNoError(r);
  const p = byLabel(r.calls, 'review-flow-r01').prompt;
  expect(p.includes('角度 flow') && p.includes('rubric.md'), '角色说明未指向专节');
  expect(p.includes('点击'), '未写明不能点击');
});
// ── 签名/抖动/原型模式 ──
sc('D38', 'S1 sig 被篡改而其余条件都满足收敛:当轮不以 converged 结束,下一轮签名正常即可收敛', async () => {
  const a = newArgs({ lenses: ['ux'], maxRounds: 4 });
  const r = await runNew(a, { verify: n => n === 1 ? { tamper: true } : {} });
  expectNoError(r); const res = ret(r);
  expect(res.exitReason === 'converged' && res.rounds === 2, `exit=${res.exitReason} rounds=${res.rounds}`);
});
sc('D39', 'S3 verify 返回 smoke.flaky:true(pass:true):照常评审,不立 wf-regress', async () => {
  const a = newArgs({ lenses: ['ux'], maxRounds: 2 });
  const r = await runNew(a, { verify: () => ({ flaky: true }) });
  expectNoError(r);
  expect(byPrefix(r.calls, 'review-ux').length > 0, '应照常评审');
  expect(!issueOf(ret(r), 'wf-regress'), '不应立 wf-regress');
});
const PROTO = (o = {}) => newArgs({ mode: 'prototype', schemeFiles: ['proto/data.js'], contractPath: 'proto/contract.md', lenses: ['newbie', 'contract'],
  goalSubgoals: [{ id: 'G1', desc: 'SUBGOAL_G1', lenses: ['newbie'] }], maxRounds: 4, staleRounds: 9, ...o });
const INJ = a => ({ v: 1, args: a, seed: null, derived: { terms: ['方向'] } });
const DEFER = id => okImpl({ deferred: [{ issueId: id, title: 'DEFER_TITLE', options: [{ choice: 'a', cost: 'c' }], recommend: 'a', why: 'w' }] });
const dec = id => ({ id, status: 'decision', evidence: 'e' });
sc('D36', '原型模式 W1:impl 提议挂起方案层条目,负责角度回 decision:proposed → agreed;新增 dir-impl 方向题;负责角度 prompt 有提议内容;decision-gap', async () => {
  const a = PROTO({ debug: true });
  const r = await run(a, sim(a, {
    impl: n => n === 2 ? DEFER('newbie-r1-1') : undefined,
    review: (L, n) => L === 'newbie' ? (n === 1 ? { issues: [mustIssue2('SCHEME', { files: ['proto/data.js:12'] })] } : { known: [dec('newbie-r1-1')] }) : undefined }), { injected: INJ(a) });
  expectNoError(r); const res = ret(r);
  expect(res.exitReason === 'decision-gap', 'exit=' + res.exitReason + ' ' + res.exitDetail);
  expect(res.state.issues.find(i => i.id === 'newbie-r1-1').needsDecision === 'agreed', 'needsDecision 应为 agreed');
  expect(res.state.directions.some(d => /^dir-impl-/.test(d.id)), '无 dir-impl 方向题');
  expect(byLabel(r.calls, 'review-newbie-r02').prompt.includes('DEFER_TITLE'), '负责角度 prompt 没有提议内容');
  // proposed 阶段:applyImpl 之后、评审之前
  const { cfg, S: st } = coreInit(PROTO());
  coreStep(cfg, st, 1, { reviews: [okReview(cfg, 'newbie', { issues: [mustIssue2('SCHEME', { files: ['proto/data.js:12'] })] }), okReview(cfg, 'contract')] });
  core().applyImpl(cfg, st, 2, DEFER('newbie-r1-1'));
  expect(st.issues[0].needsDecision === 'proposed', '提议后应为 proposed: ' + st.issues[0].needsDecision);
});
sc('D37', '三种挂起都不生效:与方案层无关;app 模式;通过筛选但负责角度回 present。deferRejected 有原因,条目照常挡收敛,当轮不算进展', async () => {
  const cases = [
    ['prototype 无关', PROTO({ debug: true, maxRounds: 2 }), 'newbie', ['proto/ui.js:3'], null],
    ['app 模式', newArgs({ debug: true, maxRounds: 2, lenses: ['ux'], goalSubgoals: [{ id: 'G1', desc: 'd', lenses: ['ux'] }] }), 'ux', ['proto/data.js:3'], null],
    ['负责角度不同意', PROTO({ debug: true, maxRounds: 2 }), 'newbie', ['proto/data.js:3'], '不同意'],
  ];
  for (const [name, a, L, files, reason] of cases) {
    const id = `${L}-r1-1`;
    const r = await run(a, sim(a, {
      impl: n => n === 2 ? DEFER(id) : undefined,
      review: (l, n) => l === L ? (n === 1 ? { issues: [mustIssue2('X', { files })] } : { known: [present(id)] }) : undefined }), { injected: INJ(a) });
    expectNoError(r); const res = ret(r);
    expect(res.exitReason !== 'decision-gap', name + ' exit=' + res.exitReason);
    const rec = res.state.rounds[1];
    expect(rec.deferRejected && rec.deferRejected.length > 0, name + ' deferRejected 无记录');
    if (reason) expect(JSON.stringify(rec.deferRejected).includes(reason), name + ' 原因应含「不同意」: ' + JSON.stringify(rec.deferRejected));
    expect(res.state.issues.find(i => i.id === id).needsDecision !== 'agreed', name + ' 不应 agreed');
    expect(rec.progress === false, name + ' 当轮不应算进展');
  }
});
sc('D42', '原型模式:对 wf-* 条目提议挂起(没有负责角度,等不到同意)直接拒收并记 deferRejected,不停在 proposed', async () => {
  const { cfg, S: st } = coreInit(PROTO());
  coreStep(cfg, st, 1, { verify: fakeVerify({ round: 1, okStates: ['01-a'], failed: [{ state: 'x', error: 'e' }] }) });
  core().applyImpl(cfg, st, 2, DEFER('wf-state-x'));
  const it = st.issues.find(i => i.id === 'wf-state-x');
  expect(it && it.needsDecision !== 'proposed' && it.needsDecision !== 'agreed', 'wf 条目 needsDecision=' + (it && it.needsDecision));
  const rec = st.rounds[st.rounds.length - 1];
  expect((rec.deferRejected || []).length > 0, 'deferRejected 无记录');
});
sc('D40', '提议的条目负责角度本轮缺席:保持 proposed,不扣、不算进展;下一轮回 decision 才 agreed', async () => {
  const { cfg, S: st } = coreInit(PROTO());
  coreStep(cfg, st, 1, { reviews: [okReview(cfg, 'newbie', { issues: [mustIssue2('SCHEME', { files: ['proto/data.js:12'] })] }), okReview(cfg, 'contract')] });
  const rec = coreStep(cfg, st, 2, { impl: DEFER('newbie-r1-1'), reviews: [null, okReview(cfg, 'contract')] });
  expect(st.issues[0].needsDecision === 'proposed', 'needsDecision=' + st.issues[0].needsDecision);
  expect(rec.progress === false, '缺席轮不应算进展');
  coreStep(cfg, st, 3, { reviews: [okReview(cfg, 'newbie', { known: [dec('newbie-r1-1')] }), okReview(cfg, 'contract')] });
  expect(st.issues[0].needsDecision === 'agreed', '下一轮应 agreed: ' + st.issues[0].needsDecision);
});
sc('P4', '原型模式 prompt:implementer 含方案层/术语/deferred/同步清单;contract 含清单路径与后端提示;newbie 含两种叫法', async () => {
  const a = PROTO({ maxRounds: 1 });
  const r = await run(a, sim(a, {}), { injected: INJ(a) });
  expectNoError(r);
  const im = byLabel(r.calls, 'impl-r01').prompt;
  for (const [n, why] of [['deferred', '挂起写 deferred'], ['proto/data.js', 'schemeFiles'], ['proto/contract.md', '清单路径'], ['方向', '术语表词']]) expect(im.includes(n), 'impl prompt 缺 ' + why);
  const ct = byLabel(r.calls, 'review-contract-r01').prompt;
  expect(ct.includes('proto/contract.md') && ct.includes('wl.mjs diff'), 'contract prompt 缺清单路径或 diff 命令');
  expect(/后端/.test(ct), 'contract prompt 缺「后端可能拿不到」');
  expect(/两种叫法/.test(byLabel(r.calls, 'review-newbie-r01').prompt), 'newbie prompt 缺「同一概念两种叫法」');
});
// ── R2 / N1 / N3 / N7 ──
sc('D31', 'R2 子项声明的 states 本轮都截图失败,负责角度却给 met:降为 unverifiable,metDowngraded 有记录,当轮不 converged', async () => {
  const { cfg, S: st } = coreInit(newArgs({ lenses: ['ux'], goalSubgoals: [{ id: 'G1', desc: 'd', lenses: ['ux'], states: ['01-a'] }] }));
  const rec = coreStep(cfg, st, 1, { verify: fakeVerify({ round: 1, okStates: ['02-b'], failed: [{ state: '01-a', error: 'e' }] }) });
  expect((rec.metDowngraded || []).length > 0, 'metDowngraded 无记录');
  expect(!rec.met.includes('G1'), 'G1 不应算 met');
  expect(st.exit !== 'converged', 'exit=' + st.exit);
});
sc('D32', 'R2 条目所在的态本轮截图失败,负责角度却给 gone:不关闭,goneIgnored 有记录', async () => {
  const { cfg, S: st } = coreInit(newArgs({ lenses: ['ux'] }));
  coreStep(cfg, st, 1, { reviews: [okReview(cfg, 'ux', { issues: [mustIssue2('A', { state: '01-a' })] })] });
  const rec = coreStep(cfg, st, 2, { verify: fakeVerify({ round: 2, okStates: ['02-b'], failed: [{ state: '01-a', error: 'e' }] }),
    reviews: [okReview(cfg, 'ux', { known: [gone('ux-r1-1')] })] });
  expect(st.issues.find(i => i.id === 'ux-r1-1').status === 'open', '不应关闭');
  expect((rec.goneIgnored || []).includes('ux-r1-1'), 'goneIgnored 无记录');
});
sc('D33', 'N1 verify 返回 noChange:true 连续两轮:都不派评审,按 design 以 stalled 结束(noChange 不计 skipStreak)', async () => {
  const a = newArgs({ lenses: ['ux'], maxRounds: 5 });
  const r = await runNew(a, { verify: () => ({ noChange: true }) });
  expectNoError(r); const res = ret(r);
  expect(byPrefix(r.calls, 'review-').length === 0, '派了评审');
  expect(res.exitReason === 'stalled' && res.rounds === 2, `exit=${res.exitReason} rounds=${res.rounds}`);
});
sc('D34', 'N3 verify 返回 env.ok:false:不派评审,当轮 blocked', async () => {
  const a = newArgs({ lenses: ['ux'], maxRounds: 5 });
  const r = await runNew(a, { verify: () => ({ envOk: false }) });
  expectNoError(r); const res = ret(r);
  expect(byPrefix(r.calls, 'review-').length === 0, '派了评审');
  expect(res.exitReason === 'blocked' && res.rounds === 1, `exit=${res.exitReason} rounds=${res.rounds}`);
});
sc('D35', 'N7 负责角度交回的 subgoals 漏了一条自己负责的子项:untabledSubgoals 有记录,该子项算 pending', async () => {
  const { cfg, S: st } = coreInit(newArgs({ lenses: ['ux'], goalSubgoals: [{ id: 'G1', desc: 'd1', lenses: ['ux'] }, { id: 'G2', desc: 'd2', lenses: ['ux'] }] }));
  const rec = coreStep(cfg, st, 1, { reviews: [{ known: [], issues: [], directions: [], subgoals: [{ id: 'G1', status: 'met', evidence: 'e' }] }] });
  expect(JSON.stringify(rec.untabledSubgoals || null).includes('G2'), 'untabledSubgoals 无 G2: ' + JSON.stringify(rec.untabledSubgoals));
  expect(!rec.met.includes('G2') && st.exit !== 'converged', 'G2 应算 pending,不能 converged');
});
sc('D30', '子项进展按历史最高计:met 数 2、1、2 且无修好条目,staleRounds=2 → 第 3 轮 stalled', async () => {
  const a = newArgs({ lenses: ['ux'], maxRounds: 6, staleRounds: 2, goalSubgoals: [{ id: 'G1', desc: 'd1', lenses: ['ux'] }, { id: 'G2', desc: 'd2', lenses: ['ux'] }, { id: 'G3', desc: 'd3', lenses: ['ux'] }] });
  const plan = { 1: ['met', 'met', 'unmet'], 2: ['met', 'unmet', 'unmet'], 3: ['met', 'met', 'unmet'] };
  const r = await runNew(a, { review: (L, n) => ({ known: [], issues: [], directions: [], subgoals: (plan[n] || plan[3]).map((st, i) => ({ id: 'G' + (i + 1), status: st, evidence: 'e' })) }) });
  expectNoError(r); const res = ret(r);
  expect(res.exitReason === 'stalled' && res.rounds === 3, `exit=${res.exitReason} rounds=${res.rounds}`);
});
sc('D27', '模板能在 AsyncFunction 里编译;CORE 不引用禁用的全局名', async () => {
  checkSyntax();
  const src = loadCoreSource().replace(/\/\/[^\n]*/g, '').replace(/\/\*[\s\S]*?\*\//g, '');
  for (const bad of [/\bagent\s*\(/, /\bparallel\s*\(/, /\bphase\s*\(/, /\blog\s*\(/, /\bbudget\s*[.(]/, /\bDate\.now\b/, /\bMath\.random\b/, /new Date\(\s*\)/, /\bstructuredClone\b/, /\brequire\s*\(/, /\bimport\s*\(/])
    expect(!bad.test(src), 'CORE 含 ' + bad);
  expect(!/\bargs\b/.test(src.replace(/validateArgs|goalArgs/g, '')), 'CORE 引用了 args');
});

// ── prompt 内容 ──
const FULL_R2 = async (extra = {}) => {
  const a = newArgs({ lenses: ['ux', 'newbie', 'func'], maxRounds: 2, staleRounds: 9, goalSubgoals: [{ id: 'G1', desc: 'SUBGOAL_G1', lenses: ['ux'] }, { id: 'G2', desc: 'SUBGOAL_G2', lenses: ['newbie'] }], ...extra });
  const r = await runNew(a, { review: (L, n) => {
    if (n === 1 && L === 'ux') return { issues: [mustIssue2('UX_TITLE', { detail: 'DETAIL_MARK', evidence: 'EVID_MARK' })], subgoals: [{ id: 'G1', status: 'unmet', evidence: 'e' }] };
    if (n === 1 && L === 'func') return { issues: [mustIssue2('FUNC_TITLE')] };
    if (n === 1 && L === 'newbie') return { issues: [mustIssue2('NEWBIE_TITLE')], subgoals: [{ id: 'G2', status: 'unmet', evidence: 'e' }] };
    return undefined;
  } });
  expectNoError(r); return r;
};
sc('P1', 'implementer prompt:intake+done、条目 detail/evidence、COMMON、principles 路径、自查命令', async () => {
  const p = byLabel((await FULL_R2()).calls, 'impl-r02').prompt;
  for (const [needle, why] of [['wl.mjs intake', 'intake 命令'], ['--done', 'done 列表'], ['DETAIL_MARK', 'detail'], ['EVID_MARK', 'evidence'], ['SendMessage', 'COMMON 禁 SendMessage'],
    ['中文', 'COMMON 中文'], ['toMain', 'COMMON toMain'], ['git', 'COMMON 禁 git 写'], ['principles.md', 'principles 路径'], ['capture.mjs shoot', '自查命令']])
    expect(p.includes(needle), 'impl prompt 缺 ' + why);
});
sc('P2', '评审 prompt:manifest(rNN)、crops/<L>-rNN、principles、unverifiable 规则、wl.mjs diff;newbie 不含他人标题与已修标题', async () => {
  const r = await FULL_R2();
  const p = byLabel(r.calls, 'review-ux-r02').prompt;
  for (const [needle, why] of [['r02_manifest.json', '本轮 manifest'], ['principles.md', 'principles 路径'], ['unverifiable', 'unverifiable 规则']])
    expect(p.includes(needle), 'ux 评审 prompt 缺 ' + why);
  const nb = byLabel(r.calls, 'review-newbie-r02').prompt;
  expect(!p.includes('crops/'), 'ux 评审 prompt 含 crops/ 写入指令(U2)');
  expect(!nb.includes('FUNC_TITLE') && !nb.includes('UX_TITLE'), 'newbie prompt 含其他角度标题');
  const code = byLabel(r.calls, 'review-func-r02').prompt;                  // 本场景无 code 角度:summary 与 diff 命令只有 code 能看到
  expect(!p.includes('IMPL_SUMMARY'), 'ux 评审 prompt 含 implementer 的 summary(R3 只给 code)');
  expect(!code.includes('IMPL_SUMMARY'), 'func 评审 prompt 含 implementer 的 summary');
  const { cfg, S: st } = coreInit(newArgs({ lenses: ['ux', 'func'] }));
  const C = core();
  const len = nFixed => { st.issues = Array.from({ length: nFixed }, (_, k) => ({ id: `func-r1-${k + 1}`, lens: 'func', title: 'FIXED_TITLE_' + String(k).padStart(3, '0'), severity: 'must', status: 'fixed', fixedRound: 1, detail: '', evidence: '', regressions: 0, alsoReportedBy: [], dissent: [], attempts: [], requiredStates: [], files: [] })); st.round = 1;
    return C.reviewerPrompt(cfg, st, 2, 'ux', fakeVerify({ round: 2 })).length; };
  const l0 = len(0), l100 = len(100);
  expect(l100 - l0 < 40 * 110, `已修条目 0→100,prompt 增 ${l100 - l0} 字符,应有上限(40 条)`);
});
sc('P2b', 'R3 只有 code 角度的 prompt 含 implementer 的 summary 与 wl.mjs diff 命令', async () => {
  const a = newArgs({ lenses: ['code', 'ux'], maxRounds: 1 });
  const r = await runNew(a, {});
  expectNoError(r);
  const p = byLabel(r.calls, 'review-code-r01').prompt;
  expect(p.includes('IMPL_SUMMARY') && p.includes('wl.mjs diff'), 'code prompt 缺 summary 或 diff 命令');
  expect(!byLabel(r.calls, 'review-ux-r01').prompt.includes('wl.mjs diff'), 'ux prompt 不应含 diff 命令');
});
sc('P3', '子项只交给负责角度', async () => {
  const r = await FULL_R2();
  const ux1 = byLabel(r.calls, 'review-ux-r01').prompt, nb = byLabel(r.calls, 'review-newbie-r01').prompt, fn = byLabel(r.calls, 'review-func-r01').prompt;
  expect(ux1.includes('SUBGOAL_G1') && !ux1.includes('SUBGOAL_G2'), 'ux prompt 子项不对');
  expect(nb.includes('SUBGOAL_G2') && !nb.includes('SUBGOAL_G1'), 'newbie prompt 子项不对');
  expect(!fn.includes('SUBGOAL_G1') && !fn.includes('SUBGOAL_G2'), 'func 不负责子项却拿到了');
});

sc('SC1', 'schema:reviewer 的 known 枚举含 decision;razor 多 counts;IMPL_SCHEMA 含 deferred;各 schema 根为 object', async () => {
  const C = core(), rs = C.reviewerSchema('ux');
  expect(rs.properties.known.items.properties.status.enum.includes('decision'), 'known.status 缺 decision');
  expect(!rs.properties.counts && C.reviewerSchema('razor').properties.counts, 'counts 仅 razor');
  for (const k of ['required']) expect(rs[k].includes('known') && rs[k].includes('subgoals'), 'required 缺 known/subgoals');
  expect(C.IMPL_SCHEMA.properties.deferred && C.IMPL_SCHEMA.required.includes('overrides'), 'IMPL_SCHEMA 缺 deferred/overrides');
  for (const sch of [C.IMPL_SCHEMA, C.VERIFY_SCHEMA, rs]) expect(sch.type === 'object', 'schema 根须 object');
});

// ── 起点评审（INJECTED.start）──
const START0 = { okStates: STATES, errorStates: [], manifest: '/abs/.claude/web-loop/rt/shots/r00_manifest.json' };
const withStart = (a, o = {}) => ({ injected: { v: 1, args: a, seed: o.seed ?? null, start: START0 }, ...(o.seed ? { seed: o.seed } : {}) });
sc('D50', '起点评审:先派 r00 评审再派 impl-r01;r00 prompt 指向 r00 清单;impl-r01 只拿到起点评审立的条目', async () => {
  const a = newArgs({ debug: true, maxRounds: 1, staleRounds: 9 });
  const r = await run(a, sim(a, { review: (L, n) => (L === 'ux' && n === 0 ? { issues: [mustIssue2('START_UX')], subgoals: [{ id: 'G1', status: 'unmet', evidence: 'e' }] } : undefined) }), withStart(a));
  expectNoError(r);
  const ls = labels(r);
  expect(ls.slice(0, 3).every(l => /-r00$/.test(l)) && ls[3] === 'impl-r01', 'label 顺序=' + ls.slice(0, 5).join(','));
  const p0 = byLabel(r.calls, 'review-ux-r00').prompt;
  expect(p0.includes('起点评审') && p0.includes('r00_manifest.json'), 'r00 prompt 没说起点评审或没指向 r00 清单');
  expect(byLabel(r.calls, 'impl-r01').prompt.includes('START_UX'), 'impl-r01 没拿到起点评审的条目');
  expect(ret(r).state.issues.find(i => i.title === 'START_UX').bornRound === 0, '起点条目 bornRound 应为 0');
});
sc('D51', '起点评审就全部达标:converged,一个 implementer 都不派;SUMMARY 写「只做了起点评审」', async () => {
  const a = newArgs({ debug: true });
  const r = await run(a, sim(a, {}), withStart(a));
  expectNoError(r);
  const res = ret(r);
  expect(res.exitReason === 'converged', 'exit=' + res.exitReason);
  expect(!labels(r).some(l => /^(impl|verify)-/.test(l)), '不应派 implementer / verify: ' + labels(r).join(','));
  const { cfg } = coreInit(a);
  expect(core().renderSummary(cfg, res.state, {}).includes('只做了起点评审'), 'SUMMARY 没写只做了起点评审');
});
sc('D52', '续跑带起点评审:r00 评审占上一个 run 末轮之后的新轮号、不占修改轮数、streak 清零;下一个 label 是 impl-r05', async () => {
  const led = seedLedger();
  const a = newArgs({ debug: true, lenses: ['ux', 'func'], goalSubgoals: [{ id: 'G1', desc: 'd', lenses: ['ux'] }], continueFrom: '.claude/web-loop/old', maxRounds: 1, staleRounds: 9 });
  const r = await run(a, sim(a, { review: L => (L === 'ux' ? ux([present('ux-r1-1')]) : { known: [present('func-r1-1')] }) }), withStart(a, { seed: led }));
  expectNoError(r);
  const ls = labels(r);
  expect(ls[0] === 'review-ux-r00' && ls.includes('impl-r05') && !ls.includes('impl-r04') && !ls.includes('impl-r06'), 'label=' + ls.join(','));
  const st = ret(r).state, startRec = st.rounds.find(x => x.start);
  expect(startRec && startRec.round === 4 && startRec.streak === 0 && st.runFirstRound === 5, '起点评审记录不对: ' + JSON.stringify(startRec && { round: startRec.round, streak: startRec.streak }));
});
sc('D57', '续跑的起点评审:新条目、新方向题的编号不撞延续下来的 id', async () => {
  const C = core(), a = newArgs({ lenses: ['ux'], goalSubgoals: [{ id: 'G1', desc: 'd', lenses: ['ux'] }] });
  const { cfg, S: st } = coreInit(a);
  const dir = t => ({ title: t, options: [{ choice: 'a', cost: 'c' }], recommend: 'a', why: 'w', states: [] });
  for (const n of [1, 2, 3]) coreStep(cfg, st, n, { reviews: [okReview(cfg, 'ux', { issues: n === 3 ? [mustIssue2('OLD_R3')] : [], directions: n === 3 ? [dir('OLD_DIR')] : [] })] });
  const { S: s2 } = coreInit(a, C.toSeed(st));
  const r0 = C.beginStart(cfg, s2).round;
  C.reduceRound(cfg, s2, r0, C.startVerify(START0, r0), [okReview(cfg, 'ux', { issues: [mustIssue2('NEW_START')], directions: [dir('NEW_DIR')] })]);
  const ids = s2.issues.map(i => i.id), dids = s2.directions.map(d => d.id);
  expect(new Set(ids).size === ids.length && new Set(dids).size === dids.length, '编号撞了: ' + ids.join(',') + ' / ' + dids.join(','));
  expect(s2.issues.find(i => i.title === 'NEW_START').id === 'ux-r4-1', '新条目 id=' + s2.issues.find(i => i.title === 'NEW_START').id);
});
sc('D58', '续跑的起点评审不把上一个 run 末轮的结论当成自己的:旧「达成」不算本轮证据、刚修好的条目被别的角度复现就重开、最近一次绿是开跑前', async () => {
  const C = core(), a = newArgs({ lenses: ['ux', 'func'], goalSubgoals: [{ id: 'G1', desc: 'd1', lenses: ['ux'] }, { id: 'G2', desc: 'd2', lenses: ['func'] }], staleRounds: 9 });
  const { cfg, S: st } = coreInit(a);
  const met = id => ({ id, status: 'met', evidence: 'e' });
  coreStep(cfg, st, 1, { reviews: [okReview(cfg, 'ux', { issues: [mustIssue2('X')], subgoals: [{ id: 'G1', status: 'unmet', evidence: 'e' }] }), okReview(cfg, 'func', { subgoals: [{ id: 'G2', status: 'unmet', evidence: 'e' }] })] });
  coreStep(cfg, st, 2, { reviews: [okReview(cfg, 'ux', { known: [gone('ux-r1-1')], subgoals: [met('G1')] }), okReview(cfg, 'func', { subgoals: [{ id: 'G2', status: 'unmet', evidence: 'e' }] })] });
  expect(st.issues[0].status === 'fixed', '前置:X 应在 r02 修好');
  const { S: s2 } = coreInit(a, C.toSeed(st));
  const r0 = C.beginStart(cfg, s2).round;
  C.reduceRound(cfg, s2, r0, C.startVerify(START0, r0), [okReview(cfg, 'ux', { subgoals: [] }),
    okReview(cfg, 'func', { subgoals: [met('G2')], issues: [mustIssue2('X again', { matchesIssueId: 'ux-r1-1' })] })]);
  expect(s2.exit !== 'converged', '不应收敛: exit=' + s2.exit);
  expect(s2.issues.find(i => i.id === 'ux-r1-1').status === 'open', '被复现的刚修好条目应重开: ' + s2.issues.find(i => i.id === 'ux-r1-1').status);
  expect(s2.lastGreenRound === 0, 'lastGreenRound=' + s2.lastGreenRound);
  const sum = C.renderSummary(cfg, s2, {});
  expect(sum.includes('最近一次绿是 r00（开跑前）') && sum.includes('| r00（起点） |'), 'SUMMARY 的绿或起点行不对');
});
sc('D59', '延续下来的方向题:不再按 shotTag 取新运行目录的截图,改从上一个 run 的 evidence/ 取;取不到时说明来源', async () => {
  const C = core(), a = newArgs({ lenses: ['ux'], goalSubgoals: [{ id: 'G1', desc: 'd', lenses: ['ux'] }] });
  const { cfg, S: st } = coreInit(a);
  coreStep(cfg, st, 1, { reviews: [okReview(cfg, 'ux', { directions: [{ title: 'OLD', options: [], recommend: '', why: '', states: ['01-a'] }] })] });
  const { cfg: c2, S: s2 } = coreInit({ ...a, continueFrom: '.claude/web-loop/old/' }, C.toSeed(st));
  const d = s2.directions[0];
  expect(d.shotTag === null && d.evidenceFrom === `.claude/web-loop/old/evidence/${d.id}`, '延续方向题字段不对: ' + JSON.stringify(d));
  expect(C.renderSummary(c2, s2, {}).includes('在 .claude/web-loop/old/evidence/'), 'SUMMARY 没说明证据来源');
});
sc('D60', '上一轮有角度缺席时 verify 不带「无改动沿用上一轮评审」的提示;全员交回时带', async () => {
  const C = core();
  for (const [miss, want] of [[true, false], [false, true]]) {
    const { cfg, S: st } = coreInit(newArgs({ lenses: ['ux', 'func'] }));
    const r0 = C.beginStart(cfg, st).round;
    C.reduceRound(cfg, st, r0, C.startVerify(START0, r0), [okReview(cfg, 'ux', { subgoals: [{ id: 'G1', status: 'unmet', evidence: 'e' }] }), miss ? null : okReview(cfg, 'func')]);
    C.applyImpl(cfg, st, 1, okImpl());
    expect(C.verifyPrompt(cfg, st, 1).includes('--no-change-hint') === want, `缺席=${miss} 时提示应为 ${want}`);
  }
});
sc('D53', 'implementer prompt:只改被指出的地方;搜索定位后按行段读;自查截图限次', async () => {
  const p = byLabel((await FULL_R2()).calls, 'impl-r02').prompt;
  for (const [needle, why] of [['没有被指出的地方不要改', '只改指出的地方'], ['offset / limit', '按行段读'], ['每轮最多跑 2 次', '自查截图限次']])
    expect(p.includes(needle), 'impl prompt 缺 ' + why);
});
sc('D54', '方向题带态与截图轮次;export 给了证据图时 SUMMARY 嵌图,没给时列出态名;有方向题时有「拍板之后」', async () => {
  const a = newArgs({ debug: true, maxRounds: 1, staleRounds: 9 });
  const dir = { title: 'DIR_T', options: [{ choice: 'a', cost: 'c' }], recommend: 'a', why: 'w', states: ['01-a'] };
  const r = await run(a, sim(a, { review: (L, n) => (L === 'ux' && n === 0 ? { directions: [dir], subgoals: [{ id: 'G1', status: 'unmet', evidence: 'e' }] } : L === 'ux' && n === 1 ? { directions: [{ ...dir, title: 'DIR_R1', states: ['02-b'] }], subgoals: [{ id: 'G1', status: 'unmet', evidence: 'e' }] } : undefined) }), withStart(a));
  expectNoError(r);
  const st = ret(r).state, d0 = st.directions.find(d => d.title === 'DIR_T'), d1 = st.directions.find(d => d.title === 'DIR_R1');
  expect(d0 && d0.shotTag === 'r00' && d0.states.join() === '01-a', '起点方向题的态/轮次不对: ' + JSON.stringify(d0));
  expect(d1 && d1.shotTag === 'r01', '第 1 轮方向题 shotTag=' + (d1 && d1.shotTag));
  const { cfg } = coreInit(a), C = core();
  const withEv = C.renderSummary(cfg, st, { evidence: { [d0.id]: [`evidence/${d0.id}/r00_01-a.png`] } });
  expect(withEv.includes(`![${d0.id}](evidence/${d0.id}/r00_01-a.png)`), 'SUMMARY 没嵌证据图');
  expect(withEv.includes('r01_02-b') && withEv.includes('没找到图片文件'), '没有图时应列出态名');
  expect(withEv.includes('## 拍板之后') && withEv.includes('web-loop 自己不保存决定'), '缺「拍板之后」');
  expect(!C.renderSummary(cfg, { ...st, directions: [] }, {}).includes('## 拍板之后'), '没有方向题不该有「拍板之后」');
});
sc('D55', '原型模式 contract:mockFiles 进角色说明与 diff 过滤,有第④类;起点评审要求通读;contract 条目算方案层', async () => {
  const a = PROTO({ mockFiles: ['proto/mock.html'], maxRounds: 1, debug: true });
  const r = await run(a, sim(a, {}), { injected: { ...INJ(a), start: START0 } });
  expectNoError(r);
  const p0 = byLabel(r.calls, 'review-contract-r00').prompt;
  expect(p0.includes('proto/mock.html') && p0.includes('④') && p0.includes('通读'), 'r00 contract prompt 缺 mockFiles / ④ / 通读');
  const { cfg, S: st } = coreInit(PROTO({ mockFiles: ['proto/mock.html'] }));
  coreStep(cfg, st, 1, { reviews: [okReview(cfg, 'newbie'), okReview(cfg, 'contract')] });
  const p1 = core().reviewerPrompt(cfg, st, 2, 'contract', fakeVerify({ round: 2 }));
  expect(/wl\.mjs diff[^\n]*proto\/mock\.html/.test(p1), '普通轮 contract 的 diff 过滤没带 mockFiles');
  expect(core().inSchemeLayer(cfg, { lens: 'contract', files: [] }) === true, 'contract 条目应算方案层');
});
sc('D56', 'mockFiles 校验:非数组或含空串报错;app 模式写了报错', async () => {
  const C = core();
  expect(C.validateArgs(PROTO({ mockFiles: 'x.html' })).errors.some(e => /mockFiles/.test(e)), '非数组应报错');
  expect(C.validateArgs(PROTO({ mockFiles: [''] })).errors.some(e => /mockFiles/.test(e)), '空串应报错');
  expect(C.validateArgs(newArgs({ mockFiles: ['a.html'] })).errors.some(e => /mockFiles/.test(e)), 'app 模式写 mockFiles 应报错');
  expect(!C.validateArgs(PROTO({ mockFiles: ['proto/mock.html'] })).errors.length, '合法 mockFiles 不该报错');
});

const fail = await runScenarios(S);
process.exit(fail ? 1 : 0);
