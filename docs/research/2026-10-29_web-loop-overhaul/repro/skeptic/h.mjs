// skeptic 复现用外壳:基于 docs/tmp/2026-10-29-web-loop-harness/harness.mjs,多一个 patches 参数(对模板文本做字符串替换,模拟"某条改动之后"的行为)
import { readFileSync, writeFileSync, unlinkSync } from 'node:fs';
import { base } from '../../../../tmp/2026-10-29-web-loop-harness/harness.mjs';
const TPL = new URL('../../../../../.claude/skills/web-loop/workflow-template.js', import.meta.url).pathname;
const DIR = new URL('.', import.meta.url).pathname;
let n = 0;
export async function run(args, respond, patches = []) {
  const calls = [];
  globalThis.args = JSON.stringify(args);
  globalThis.phase = () => {};
  globalThis.log = m => calls.push({ label: 'LOG', prompt: String(m) });
  globalThis.parallel = async thunks => Promise.all(thunks.map(t => t()));
  globalThis.agent = async (prompt, opts = {}) => {
    const label = opts.label || '';
    calls.push({ label, prompt });
    const r = respond(label, prompt);
    return r === undefined ? base(label) : r;
  };
  let src = readFileSync(TPL, 'utf8');
  for (const [a, b] of patches) { if (!src.includes(a)) throw new Error('patch miss: ' + a.slice(0, 60)); src = src.replace(a, b); }
  const f = `${DIR}/_tpl_${process.pid}_${n++}.mjs`;
  writeFileSync(f, src);
  let error = null;
  try { await import(f); } catch (e) { error = e; } finally { unlinkSync(f); }
  return { calls, error };
}
export const v = (lens, o = {}) => ({ lens, verdict: 'pass', mustFixOpen: 0, issues: [], verified: [], knownIssuesStatus: [], ...o });
export const labels = calls => calls.map(c => c.label);
