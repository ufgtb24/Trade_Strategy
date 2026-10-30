import { run, verdict } from './harness.mjs';
const A0 = { url: 'http://localhost:1', goal: 'g', workdir: '/w', rubricPath: '/w/r.md', runtag: 'rt', uiDir: '/u', shotsDir: '/w/shots', smokeCmd: 'true', goalSubgoals: [{ id: 'G1', desc: 'd', verifiable_via: 'screenshot' }] };
const rnum = l => parseInt((l.match(/-r(\d\d)$/) || [])[1] || '0', 10);
const summary = calls => ({ done: calls.find(c => c.label === 'LOG' && c.prompt.includes('done')).prompt,
  paused: calls.filter(c => c.label.startsWith('paused-')).map(c => c.label + ':' + (c.prompt.match(/触发判据:\*\*(\w+)/) || [])[1]),
  meta: calls.filter(c => c.label.startsWith('meta-agent-')).map(c => c.label) });
const V = { verified: [{ title: 'G1', evidence: 'e', coveredSubgoals: ['G1'] }] };
// T1 真停滞:3 个 lens 各 1 条 must,原样挂着不动(默认 maxRounds 5 / staleRounds 3)
{
  const { calls } = await run({ ...A0, lenses: ['ux', 'func', 'code'] }, (label) => {
    const lens = (label.match(/^review-(\w+)-r/) || [])[1]; const r = rnum(label);
    if (lens) return verdict(lens, { ...V, verdict: 'fail', issues: r === 1 ? [{ title: lens + ' m', severity: 'must' }] : [], knownIssuesStatus: r > 1 ? [{ id: `${lens}-r1-1`, stillPresent: true }] : [] });
  });
  console.log('T1 真停滞', JSON.stringify(summary(calls)));
}
// T2 稳步推进:只有 ux 一开始报 5 条 must,之后每轮修 1 条、不新增(真进展)
{
  const { calls } = await run({ ...A0, lenses: ['ux', 'func', 'code'] }, (label) => {
    const lens = (label.match(/^review-(\w+)-r/) || [])[1]; const r = rnum(label);
    if (lens === 'ux') return verdict('ux', { ...V, verdict: 'fail', issues: r === 1 ? [1,2,3,4,5].map(k => ({ title: 'm' + k, severity: 'must' })) : [], knownIssuesStatus: r === 1 ? [] : [1,2,3,4,5].map(k => ({ id: `ux-r1-${k}`, stillPresent: k >= r })) });
    if (lens) return verdict(lens, V);
  });
  console.log('T2 稳步推进', JSON.stringify(summary(calls)));
}
