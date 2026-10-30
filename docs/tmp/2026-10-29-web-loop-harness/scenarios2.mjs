import { run, pad, issuesFromPersist, verdict } from './harness.mjs';
const A0 = { url: 'http://localhost:1', goal: 'g', workdir: '/w', rubricPath: '/w/r.md', runtag: 'rt', uiDir: '/u', shotsDir: '/w/shots', smokeCmd: 'true' };
const rnum = l => parseInt((l.match(/-r(\d\d)$/) || [])[1] || '0', 10);
const out = (k, v) => console.log(`\n### ${k}\n` + (typeof v === 'string' ? v : JSON.stringify(v, null, 1)));
const flags = p => (p.match(/## 判据 \d · \w+\((true|false)\)/g) || []).join(' | ');

// S2b missingStates:同一 G1 连续 3 轮 unverifiable+同 requiredStates,且每轮用 matchesIssueId 续同一条(避免 treadmill 抢先)
{
  const { calls } = await run({ ...A0, maxRounds: 4, staleRounds: 9, lenses: ['func'], goalSubgoals: [{ id: 'G1', desc: 'd', verifiable_via: 'screenshot' }] }, (label) => {
    const r = rnum(label);
    if (label.startsWith('review-func-')) return verdict('func', { verdict: 'fail',
      knownIssuesStatus: r > 1 ? [{ id: 'func-r1-1', stillPresent: true, unverifiable: true }] : [],
      issues: [{ title: 'G1 看不到 r' + r, severity: 'must', unverifiable: true, matchesSubgoal: 'G1', requiredStates: ['05-open'] }] });
  });
  const p = calls.filter(c => c.label.startsWith('paused-'));
  out('S2b paused', p.map(c => c.label + ' :: ' + flags(c.prompt)));
  out('S2b 退出', calls.find(c => c.label === 'LOG' && c.prompt.includes('done')).prompt);
}

// S9b 收敛那轮 treadmill 恰好成立 → SUMMARY 顶部仍挂 PAUSED
{
  const { calls } = await run({ ...A0, maxRounds: 5, lenses: ['ux', 'func'] }, (label) => {
    const r = rnum(label);
    if (label === 'review-ux-r01') return verdict('ux', { verdict: 'fail', issues: [{ title: 'u1', severity: 'must' }] });
    if (label === 'review-ux-r02') return verdict('ux', { knownIssuesStatus: [{ id: 'ux-r1-1', stillPresent: false }] });
    if (label === 'review-func-r02') return verdict('func', { verdict: 'fail', issues: [{ title: 'f2', severity: 'must' }] });
    if (label === 'review-func-r03') return verdict('func', { knownIssuesStatus: [{ id: 'func-r2-1', stillPresent: false }] });
    if (label.startsWith('review-')) return verdict(label.split('-')[1]);
  });
  out('S9b 退出', calls.find(c => c.label === 'LOG' && c.prompt.includes('done')).prompt);
  const fin = calls.find(c => c.label === 'finalize').prompt;
  out('S9b finalize 带 PAUSED 节?', fin.includes('## ⚠ PAUSED'));
  out('S9b finalize 的退出描述', (fin.match(/退出 = (\w[\w-]*)/) || [])[1]);
}

// S11 子项一直全覆盖、must 每轮都在推进(修一条)→ P1 meta-agent 仍被「覆盖集合没变」触发
{
  const { calls } = await run({ ...A0, maxRounds: 5, staleRounds: 3, lenses: ['ux'], goalSubgoals: [{ id: 'G1', desc: 'd', verifiable_via: 'screenshot' }] }, (label) => {
    const r = rnum(label);
    if (label.startsWith('review-ux-')) {
      // r1 报 4 条 must,之后每轮修掉 1 条(真进展)
      const open = [1, 2, 3, 4].filter(k => k >= r);
      return verdict('ux', { verdict: r >= 4 ? 'pass' : 'fail',
        issues: r === 1 ? [1, 2, 3, 4].map(k => ({ title: 'm' + k, severity: 'must' })) : [],
        knownIssuesStatus: r === 1 ? [] : [1, 2, 3, 4].map(k => ({ id: `ux-r1-${k}`, stillPresent: k >= r })),
        verified: [{ title: 'G1 ok', evidence: 'e', coveredSubgoals: ['G1'] }] });
    }
  });
  out('S11 meta-agent 触发轮', calls.filter(c => c.label.startsWith('meta-agent-')).map(c => c.label + ' :: ' + (c.prompt.match(/mustStaleStreak=\d+ \/ coveredSubgoalsUnchangedRounds=\d+ \/ gitDiffSmallRounds=\d+/) || [])[0]));
  out('S11 退出', calls.find(c => c.label === 'LOG' && c.prompt.includes('done')).prompt);
}

// S12 meta-agent 某轮给了 forbidden,下一轮又给 p1_skip_reason → 前面累计的 forbidden 是否还进 implementer
{
  const { calls } = await run({ ...A0, maxRounds: 5, staleRounds: 3, lenses: ['ux'], goalSubgoals: [{ id: 'G1', desc: 'd', verifiable_via: 'screenshot' }] }, (label) => {
    const r = rnum(label);
    if (label.startsWith('review-ux-')) return verdict('ux', { verdict: 'fail', issues: r === 1 ? [{ title: 'm', severity: 'must' }] : [], knownIssuesStatus: r > 1 ? [{ id: 'ux-r1-1', stillPresent: true }] : [], verified: [{ title: 'G1', evidence: 'e', coveredSubgoals: ['G1'] }] });
    // read-state 模拟忠实读 decision_log:r4 时日志里有两条,最后一条 skip
    if (label === 'read-state-r04') return { exists: true, forbiddenApproaches: [{ issueId: 'ux-r1-1', triedMethod: 'FORBID_MARK', why_failed_evidence: 'x' }], entries: [{}, {}], totalLines: 300, p1_skip_reason: 'no-stall' };
  });
  out('S12 r4 implementer 是否还看到之前的 forbidden', calls.find(c => c.label === 'impl-r04')?.prompt.includes('FORBID_MARK'));
}
