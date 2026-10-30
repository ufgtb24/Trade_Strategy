// K3:按第 10 条修好 treadmill 之后(这里直接把 treadmill 置 false 模拟),稳步推进的 run 从第 3 轮起每轮都触发 opus meta-agent
// 场景:6 个子项第 1 轮就全覆盖、之后覆盖集不变;每轮修好 1 条 must、不新增(稳步推进,非停滞)
import { run, v } from './h.mjs';
const SG = ['G1','G2'].map(id=>({id, desc:id, verifiable_via:'screenshot'}));
const cov = [{title:'G', evidence:'x', coveredSubgoals:['G1','G2']}];
const resp = (label) => {
  const m = label.match(/^review-ux-r0(\d)$/); if (!m) return undefined; const r = +m[1];
  if (r===1) return v('ux',{ verdict:'fail', verified:cov, issues:[1,2,3,4,5].map(i=>({title:'m'+i, severity:'must'})) });
  return v('ux',{ verdict:'fail', verified:cov, knownIssuesStatus:[{id:`ux-r1-${r-1}`, stillPresent:false}] });
};
const r = await run({ url:'u', goal:'g', workdir:'/w', lenses:['ux'], maxRounds:5, goalSubgoals:SG }, resp,
  [['return lastNewCum >= fixedCum && lastNewCum > 0 && lastNewCum >= prevNewCum;', 'return false;']]);
console.log('error:', r.error?.message ?? null);
console.log('meta-agent 触发轮次:', r.calls.filter(c=>c.label.startsWith('meta-agent-')).map(c=>c.label));
const m = r.calls.find(c=>c.label.startsWith('meta-agent-'));
console.log('单次 meta-agent prompt 字符数(此玩具场景):', m?.prompt.length, '; 其中内联整份台账+verifiedLog');
