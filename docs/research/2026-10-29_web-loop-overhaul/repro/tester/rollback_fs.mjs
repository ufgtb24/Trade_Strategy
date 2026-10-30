// 回滚算法的文件层验证(清单第 1 条):在临时 git 仓库里模拟「r1 改 A、r2 改 B 并新建 C 后 smoke 红」。
// 参考实现 snapshot()/rollback() 即第 1 条的文字描述;implementer 可直接照这两个函数的命令序写进回滚指令。
// 同时演示旧做法(git checkout -- .)冲掉 r1 的改动与开跑前的脏文件。
// 运行:node rollback_fs.mjs
import { mkdtempSync, writeFileSync, readFileSync, existsSync, mkdirSync, copyFileSync, rmSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';

const sh = (cwd, ...a) => execFileSync('git', a, { cwd, encoding: 'utf8' });
const dirty = repo => sh(repo, 'status', '--porcelain=v1', '-z', '-uall').split('\0').filter(Boolean)
  .map(e => ({ st: e.slice(0, 2), path: e.slice(3) }));
const isUntracked = st => st === '??';

/** implementer 开工前:把当时所有脏文件(已跟踪改动 + 未跟踪)拷到 snap/r{N}/files/,清单写 manifest.json */
function snapshot(repo, snap, n) {
  const dir = join(snap, `r${String(n).padStart(2, '0')}`);
  const man = [];
  for (const { st, path } of dirty(repo)) {
    const deleted = st.includes('D');
    man.push({ path, untracked: isUntracked(st), deleted });
    if (!deleted) { const to = join(dir, 'files', path); mkdirSync(dirname(to), { recursive: true }); copyFileSync(join(repo, path), to); }
  }
  mkdirSync(dir, { recursive: true });
  writeFileSync(join(dir, 'manifest.json'), JSON.stringify(man));
}
/** 回滚到 snap/r{N} 的状态:快照里有的拷回;快照没有、现在脏的已跟踪文件 git checkout;新冒出的未跟踪文件删掉 */
function rollback(repo, snap, n) {
  const dir = join(snap, `r${String(n).padStart(2, '0')}`);
  const man = JSON.parse(readFileSync(join(dir, 'manifest.json'), 'utf8'));
  const inSnap = new Map(man.map(m => [m.path, m]));
  for (const { st, path } of dirty(repo)) {
    if (inSnap.has(path)) continue;
    if (isUntracked(st)) rmSync(join(repo, path), { force: true }); else sh(repo, 'checkout', '--', path);
  }
  for (const m of man) {
    const p = join(repo, m.path);
    if (m.deleted) rmSync(p, { force: true });
    else { mkdirSync(dirname(p), { recursive: true }); copyFileSync(join(dir, 'files', m.path), p); }
  }
}

function setup() {
  const repo = mkdtempSync(join(tmpdir(), 'wl-rb-'));
  const snap = mkdtempSync(join(tmpdir(), 'wl-snap-'));
  sh(repo, 'init', '-q'); sh(repo, 'config', 'user.email', 't@t'); sh(repo, 'config', 'user.name', 't');
  for (const f of ['A', 'B', 'X']) writeFileSync(join(repo, f), f + '0\n');
  sh(repo, 'add', '.'); sh(repo, 'commit', '-qm', 'init');
  writeFileSync(join(repo, 'X'), 'X-user-dirty\n');          // 开跑前就有的未提交改动
  writeFileSync(join(repo, 'U0'), 'U0-user-untracked\n');    // 开跑前就有的未跟踪文件
  return { repo, snap };
}
const rd = (repo, f) => existsSync(join(repo, f)) ? readFileSync(join(repo, f), 'utf8').trim() : '(不存在)';
function play(repo, snap, how) {
  snapshot(repo, snap, 1); writeFileSync(join(repo, 'A'), 'A-r1\n');                 // r1 改 A
  snapshot(repo, snap, 2); writeFileSync(join(repo, 'B'), 'B-r2\n'); writeFileSync(join(repo, 'C'), 'C-r2\n'); // r2 改 B 新建 C
  if (how === 'snapshot') rollback(repo, snap, 2); else sh(repo, 'checkout', '--', '.');  // smoke 红 → 回滚
  return { A: rd(repo, 'A'), B: rd(repo, 'B'), C: rd(repo, 'C'), X: rd(repo, 'X'), U0: rd(repo, 'U0') };
}
const want = { A: 'A-r1', B: 'B0', C: '(不存在)', X: 'X-user-dirty', U0: 'U0-user-untracked' };
let bad = 0;
for (const how of ['git-checkout', 'snapshot']) {
  const { repo, snap } = setup();
  const got = play(repo, snap, how);
  const okAll = Object.keys(want).every(k => got[k] === want[k]);
  console.log(`${how === 'snapshot' ? '新做法(快照)' : '旧做法(git checkout -- .)'}: ${okAll ? 'PASS' : 'FAIL'} ${JSON.stringify(got)}`);
  if (how === 'snapshot' && !okAll) bad++;
  if (how === 'git-checkout' && okAll) { console.log('  意外:旧做法也满足期望'); bad++; }
  rmSync(repo, { recursive: true, force: true }); rmSync(snap, { recursive: true, force: true });
}
console.log('期望 =', JSON.stringify(want));
process.exit(bad ? 1 : 0);
