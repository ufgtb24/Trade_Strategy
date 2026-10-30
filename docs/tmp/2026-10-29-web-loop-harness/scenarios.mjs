import { run, pad, issuesFromPersist, verdict } from './harness.mjs';
const A0 = { url: 'http://localhost:1', goal: 'g', workdir: '/w', rubricPath: '/w/r.md', runtag: 'rt', uiDir: '/u', shotsDir: '/w/shots', smokeCmd: 'true' };
const rnum = l => parseInt((l.match(/-r(\d\d)$/) || [])[1] || '0', 10);
const out = (k, v) => console.log(`\n### ${k}\n` + (typeof v === 'string' ? v : JSON.stringify(v, null, 1)));

// S1 评审记录命名 + persist 拿不到 verdict 正文
{
  const { calls } = await run({ ...A0, maxRounds: 2, lenses: ['ux'] }, (label) => {
    if (label.startsWith('review-ux-')) return verdict('ux', { verdict: 'fail', issues: [{ title: 'T' + rnum(label), severity: 'must', detail: 'DETAIL_MARK', evidence: 'EVID_MARK', matchesSubgoal: 'G1', requiredStates: ['S9'], unverifiable: false }] });
  });
  const p1 = calls.find(c => c.label === 'persist-r01').prompt;
  const i2 = calls.find(c => c.label === 'impl-r02').prompt;
  out('S1 persist 写的文件名', (p1.match(/reviews\/round_[^ 。]*?\.md/) || [])[0]);
  out('S1 impl r2 要读的文件名', (i2.match(/reviews\/round_[^ (]*?\.md/) || [])[0]);
  out('S1 persist prompt 里有没有 reviewer 的 detail 原文', p1.includes('DETAIL_MARK'));
  out('S1 台账字段', Object.keys(issuesFromPersist(calls, 'r01')[0]));
  out('S1 impl r2 能看到 detail/evidence 吗', { detail: i2.includes('DETAIL_MARK'), evidence: i2.includes('EVID_MARK') });
}

// S2 missingStates 判据:同一 G1 连续 3 轮 unverifiable + 同一 requiredStates
{
  const { calls } = await run({ ...A0, maxRounds: 3, lenses: ['func'], goalSubgoals: [{ id: 'G1', desc: 'd', verifiable_via: 'screenshot' }] }, (label) => {
    if (label.startsWith('review-func-')) return verdict('func', { verdict: 'fail', issues: [{ title: 'cannot see G1 r' + rnum(label), severity: 'must', unverifiable: true, matchesSubgoal: 'G1', requiredStates: ['05-open'] }] });
  });
  out('S2 是否触发 paused(missingStates)', calls.filter(c => c.label.startsWith('paused-')).map(c => c.label));
  const fin = calls.find(c => c.label === 'finalize').prompt;
  out('S2 SUMMARY 的「待补 STATES」节', (fin.match(/## 待补 STATES[\s\S]*?```markdown\n([\s\S]*?)\n```/) || [])[1]);
}

// S3 treadmill 误报:func 从没出过 must,只是 ux 每轮修一条、新增一条
{
  const { calls } = await run({ ...A0, maxRounds: 5, lenses: ['ux', 'func'] }, (label, prompt) => {
    const r = rnum(label);
    if (label.startsWith('review-ux-')) {
      const prev = r > 1 ? [{ id: `ux-r${r - 1}-1`, stillPresent: false }] : [];
      return verdict('ux', { verdict: 'fail', issues: [{ title: 'new must ' + r, severity: 'must' }], knownIssuesStatus: prev });
    }
    if (label.startsWith('review-func-')) return verdict('func');
  });
  out('S3 paused 轮次与原因', calls.filter(c => c.label.startsWith('paused-')).map(c => c.label + ' :: ' + (c.prompt.match(/触发判据:\*\*(\w+)/) || [])[1]));
}

// S4 reviewer 引用了一个不存在的 id(笔误)→ 新 must 被静默丢掉
{
  const { calls } = await run({ ...A0, maxRounds: 2, lenses: ['ux'] }, (label) => {
    if (label === 'review-ux-r01') return verdict('ux', { verdict: 'fail', issues: [{ title: 'A', severity: 'must' }] });
    if (label === 'review-ux-r02') return verdict('ux', { verdict: 'fail', knownIssuesStatus: [{ id: 'ux-r1-1', stillPresent: false }], issues: [{ matchesIssueId: 'ux-r1-01', title: 'B 新问题', severity: 'must' }] });
  });
  const iss = issuesFromPersist(calls, 'r02');
  out('S4 r2 台账', iss.map(i => `${i.id} ${i.status} ${i.title}`));
  out('S4 退出', calls.find(c => c.label === 'LOG' && c.prompt.includes('done')).prompt);
}

// S5 reviewer 回报的 lens 名与实际 lens 不一致 → 归属错
{
  const { calls } = await run({ ...A0, maxRounds: 1, lenses: ['ux', 'rival'] }, (label) => {
    if (label === 'review-ux-r01') return verdict('ux');
    if (label === 'review-rival-r01') return verdict('ux', { verdict: 'fail', issues: [{ title: 'rival 发现', severity: 'must' }] });
  });
  out('S5 rival 的问题记在谁名下', issuesFromPersist(calls, 'r01').map(i => `${i.id} lens=${i.lens}`));
}

// S6 lenses 不含 code 时,一次 refresh 失败留下的 infra must 永远关不掉
{
  const { calls } = await run({ ...A0, maxRounds: 4, lenses: ['ux'] }, (label) => {
    if (label === 'refresh-r01') return { ready: false };
    if (label.startsWith('review-ux-')) return verdict('ux', { knownIssuesStatus: [{ id: 'infra-r01', stillPresent: false }] });
  });
  out('S6 结果', calls.find(c => c.label === 'LOG' && c.prompt.includes('done')).prompt);
  out('S6 r01 是否写了 issues.json', !!calls.find(c => c.label === 'persist-r01'));
}

// S7 每轮都截图失败 → 一直空转到 maxRounds,不暂停
{
  const { calls } = await run({ ...A0, maxRounds: 5, lenses: ['ux', 'func', 'code'] }, (label) => {
    if (label.startsWith('capture')) return { shots: [{ state: '01', path: null, error: 'boom' }] };
  });
  out('S7 结果', calls.find(c => c.label === 'LOG' && c.prompt.includes('done')).prompt);
  out('S7 agent 总数 / paused / persist', { agents: calls.filter(c => c.label !== 'LOG').length, paused: calls.filter(c => c.label.startsWith('paused')).length, persist: calls.filter(c => c.label.startsWith('persist')).length });
}

// S8 implementer 的结构化返回有没有被用:让 impl 返回 kind=backend / stuck=true,看 refresh/reviewer prompt 是否反映
{
  const { calls } = await run({ ...A0, maxRounds: 2, lenses: ['code'] }, (label) => {
    if (label.startsWith('impl-')) return { reviewer_stuck: true, planRepetition: 'STUCK_MARK', kind: 'backend' };
    if (label.startsWith('read-impl-stuck-')) return { ok: false };
    if (label.startsWith('review-code-')) return verdict('code', { verdict: 'fail', issues: [{ title: 'x' + label, severity: 'must' }] });
  });
  const rv2 = calls.find(c => c.label === 'review-code-r02').prompt;
  out('S8 r2 code reviewer 收到 implementer 的 stuck 信号吗', rv2.includes('STUCK_MARK'));
  out('S8 refresh prompt 里有 implementer 返回的 kind 吗', calls.find(c => c.label === 'refresh-r01').prompt.includes('kind=backend') );
}

// S9 收敛后 SUMMARY 仍挂 PAUSED?(treadmill 在收敛那轮成立)
{
  const { calls } = await run({ ...A0, maxRounds: 5, lenses: ['ux', 'func'] }, (label) => {
    const r = rnum(label);
    if (label.startsWith('review-ux-')) {
      if (r <= 3) return verdict('ux', { verdict: 'fail', issues: [{ title: 'm' + r, severity: 'must' }], knownIssuesStatus: r > 1 ? [{ id: `ux-r${r - 1}-1`, stillPresent: false }] : [] });
      return verdict('ux', { knownIssuesStatus: [{ id: `ux-r3-1`, stillPresent: false }] });
    }
    if (label.startsWith('review-func-')) return verdict('func');
  });
  out('S9 结果', calls.find(c => c.label === 'LOG' && c.prompt.includes('done')).prompt);
  const fin = calls.find(c => c.label === 'finalize').prompt;
  out('S9 finalize 是否带 PAUSED 节 / 指向的文件', { paused: fin.includes('## ⚠ PAUSED'), pointsTo: (fin.match(/详 `([^`]*paused[^`]*)`/) || [])[1] });
}

// S10 每轮 agent 数(6 lens)
{
  const L = ['ux', 'func', 'code', 'rival', 'razor', 'newbie'];
  const { calls } = await run({ ...A0, maxRounds: 3, lenses: L }, (label) => {
    const lens = (label.match(/^review-(\w+)-r/) || [])[1];
    if (lens) return verdict(lens, { verdict: 'fail', issues: [{ title: lens + label, severity: 'must' }] });
  });
  const per = {};
  for (const c of calls) { if (c.label === 'LOG') continue; const r = rnum(c.label); per[r ? 'r' + r : 'setup/finalize'] = (per[r ? 'r' + r : 'setup/finalize'] || 0) + 1; }
  out('S10 每轮 agent 数(含 meta 等)', per);
}
