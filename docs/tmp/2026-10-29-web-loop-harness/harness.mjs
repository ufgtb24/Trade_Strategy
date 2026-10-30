// 临时 dry-run 外壳(审计用,第 0 条的参考;跑时会在本目录生成 _tpl_N.mjs,用完删):注入 mock agent/parallel/phase/log/args,真跑 workflow-template.js 的控制流
import { readFileSync, writeFileSync } from 'node:fs';
const TPL = new URL('../../../.claude/skills/web-loop/workflow-template.js', import.meta.url).pathname;
const DIR = new URL('.', import.meta.url).pathname;
let n = 0;
export const pad = r => `r${String(r).padStart(2,'0')}`;
export const base = (label) => {
  if (label === 'cleanup-old-runs') return { cleaned_runtags: [], deleted_mcp: false };
  if (label === 'pw-selfcheck') return { ok: true };
  if (label === 'preflight') return { rubricFound: true, smokeBaselineGreen: true };
  if (label === 'write-goal') return { wrote: true };
  if (label.startsWith('read-state-')) return { exists: false, forbiddenApproaches: [], entries: [], totalLines: 300, p1_skip_reason: null };
  if (label.startsWith('impl-')) return { reviewer_stuck: false, kind: 'frontend' };
  if (label.startsWith('smoke-')) return { pass: true };
  if (label.startsWith('refresh-')) return { ready: true, kind: 'frontend' };
  if (label.startsWith('capture-')) return { shots: [{ state: '01', path: '/w/shots/x.png', bytes: 10 }] };
  if (label.startsWith('read-impl-stuck-')) return { ok: true, stuck: false, summary: '' };
  if (label.startsWith('meta-agent-')) return { forbiddenApproaches: [], prioritizedMustIds: [], p1_skip_reason: 'no-stall', escapeRequest: null };
  return undefined;
};
export async function run(args, respond) {
  const calls = [];
  globalThis.args = JSON.stringify(args);           // 真 runtime 传字符串
  globalThis.phase = () => {};
  globalThis.log = m => calls.push({ label: 'LOG', prompt: String(m) });
  globalThis.parallel = async thunks => Promise.all(thunks.map(t => t()));
  globalThis.agent = async (prompt, opts = {}) => {
    const label = opts.label || '';
    calls.push({ label, prompt, model: opts.model });
    const r = respond(label, prompt);
    return r === undefined ? base(label) : r;
  };
  const f = `${DIR}/_tpl_${n++}.mjs`;
  writeFileSync(f, readFileSync(TPL, 'utf8'));
  let error = null;
  try { await import(f); } catch (e) { error = e; }
  return { calls, error };
}
export function issuesFromPersist(calls, rtag) {
  const c = calls.find(c => c.label === `persist-${rtag}`);
  if (!c) return null;
  const m = c.prompt.match(/issues\.json\(覆写\)=(.*?);写 /s);
  return JSON.parse(m[1]);
}
export const verdict = (lens, o = {}) => ({ lens, verdict: 'pass', mustFixOpen: 0, issues: [], verified: [], knownIssuesStatus: [], ...o });
