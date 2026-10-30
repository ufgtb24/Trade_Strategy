// 一条命令跑全部测试:node .claude/skills/web-loop/tests/run-all.mjs
// 逐个子进程跑 test-*.mjs;汇总文件级通过/失败,并统计 dryrun 场景里的 PASS/FAIL 行数。失败时打印该文件的 FAIL 行。
import { readdirSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const files = readdirSync(here).filter(f => /^test-.*\.mjs$/.test(f)).sort();
const only = process.argv[2];
let pass = 0, fail = 0, scnPass = 0, scnFail = 0;
const failed = [];
for (const f of files) {
  if (only && !f.includes(only)) continue;
  const r = spawnSync(process.execPath, [join(here, f)], { encoding: 'utf8', timeout: 900000 });
  const out = (r.stdout || '') + (r.stderr || '');
  const killed = r.error || r.signal;
  const lines = out.split('\n');
  const isScn = lines.some(l => /^-- \d+ passed, \d+ failed/.test(l));
  if (isScn) {
    scnPass += lines.filter(l => /^PASS /.test(l)).length;
    scnFail += lines.filter(l => /^FAIL /.test(l)).length;
  }
  if (r.status === 0) { pass++; console.log(`ok   ${f}`); }
  else {
    fail++; failed.push(f); console.log(`FAIL ${f}${killed ? '  [超时被杀: ' + (r.signal || (r.error && r.error.code)) + ']' : ''}`);
    for (const l of lines.filter(l => /^FAIL /.test(l) || (!isScn && l.trim())).slice(0, isScn ? 40 : 6)) console.log('     ' + l.slice(0, 240));
  }
}
console.log(`\n文件: ${pass} 通过, ${fail} 失败; dryrun 场景: ${scnPass} 通过, ${scnFail} 失败`);
process.exit(fail ? 1 : 0);
