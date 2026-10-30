// K1:smoke 每轮都红(例如开发服务器挂了,和本轮改动无关) → 每轮 opus implementer 白干 + 回滚,跑满 maxRounds,不暂停、不 persist
import { run, labels } from './h.mjs';
const r = await run({ url:'u', goal:'g', workdir:'/w', lenses:['ux'], maxRounds:5 },
  (label) => label.startsWith('smoke-') ? { pass:false, summary:'ECONNREFUSED localhost:5173' } : undefined);
const L = labels(r.calls);
console.log('error:', r.error?.message ?? null);
console.log('impl 次数:', L.filter(l=>l.startsWith('impl-')).length, ' rollback 次数:', L.filter(l=>l.startsWith('rollback-')).length,
  ' persist 次数:', L.filter(l=>l.startsWith('persist-')).length, ' paused:', L.some(l=>l.startsWith('paused-')));
console.log('finalize 退出原因:', (r.calls.find(c=>c.label==='finalize').prompt.match(/退出 = (\S+?)\(/)||[])[1]);
