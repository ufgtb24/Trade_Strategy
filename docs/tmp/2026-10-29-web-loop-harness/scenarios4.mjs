import { run, verdict, issuesFromPersist } from './harness.mjs';
const A0 = { url: 'http://localhost:1', goal: 'g', workdir: '/w', rubricPath: '/w/r.md', runtag: 'rt', uiDir: '/u', shotsDir: '/w/shots', smokeCmd: 'true', goalSubgoals: [{ id: 'G1', desc: 'd', verifiable_via: 'screenshot' }] };
const V = { verified: [{ title: 'G1', evidence: 'e', coveredSubgoals: ['G1'] }] };
// U1 唯一的 must 标了 unverifiable(只是截图配方截错),reviewer 判 pass、子项全覆盖 → 能收敛吗?
{
  const { calls } = await run({ ...A0, maxRounds: 3, lenses: ['func'] }, (label) => {
    if (label === 'review-func-r01') return verdict('func', { ...V, issues: [{ title: '14 号截图截错框,判不了', severity: 'must', unverifiable: true, requiredStates: ['14-compare-box'] }] });
    if (label.startsWith('review-func-')) return verdict('func', { ...V, knownIssuesStatus: [{ id: 'func-r1-1', stillPresent: true, unverifiable: true }] });
  });
  console.log('U1', calls.find(c => c.label === 'LOG' && c.prompt.includes('done')).prompt);
  console.log('U1 paused', calls.filter(c => c.label.startsWith('paused')).map(c => c.label + ':' + (c.prompt.match(/触发判据:\*\*(\w+)/) || [])[1]));
}
// U2 reviewer 申报 fail 但台账里没有 must(比如只有 nice)→ 能收敛吗?
{
  const { calls } = await run({ ...A0, maxRounds: 3, lenses: ['func'] }, (label) => {
    if (label.startsWith('review-func-')) return verdict('func', { ...V, verdict: 'fail', issues: [{ title: '小建议', severity: 'nice' }] });
  });
  console.log('U2', calls.find(c => c.label === 'LOG' && c.prompt.includes('done')).prompt);
}
