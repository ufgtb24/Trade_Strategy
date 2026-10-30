// K2:修好的问题,评审从此看不到它的 id → 复现时只能新立一条,regressed / oscillating 这条路实际走不到
import { run, v } from './h.mjs';
const r = await run({ url:'u', goal:'g', workdir:'/w', lenses:['ux'], maxRounds:3 }, (label) => {
  if (label==='review-ux-r01') return v('ux',{ verdict:'fail', issues:[{title:'右缘被截', severity:'must'},{title:'另一条', severity:'must'}] });
  if (label==='review-ux-r02') return v('ux',{ verdict:'fail', knownIssuesStatus:[{id:'ux-r1-1', stillPresent:false},{id:'ux-r1-2', stillPresent:true}] });
  if (label==='review-ux-r03') return v('ux',{ verdict:'fail', issues:[{title:'右缘又被截', severity:'must'}], knownIssuesStatus:[{id:'ux-r1-2', stillPresent:true}] });
});
console.log('error:', r.error?.message ?? null);
const p3 = r.calls.find(c=>c.label==='review-ux-r03').prompt;
console.log('r03 评审 prompt 里出现已修条目 id ux-r1-1:', p3.includes('ux-r1-1'), '; 出现未修条目 ux-r1-2:', p3.includes('ux-r1-2'));
const fin = r.calls.find(c=>c.label==='finalize').prompt;
const left = JSON.parse((fin.match(/残留 must\(确证缺陷\)=(\[.*?\]),待人工/s)||[])[1]);
console.log('finalize 残留 must:', left.map(i=>`${i.id}:${i.status}:regr=${i.regressionCount||0}`));
