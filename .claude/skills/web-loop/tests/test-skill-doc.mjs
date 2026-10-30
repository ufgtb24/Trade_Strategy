// 文档一致性:SKILL.md / examples/path2.md 与模板、判据的关键句对得上,且不再出现已删机制的字眼。
// 只断言「读者会据此操作」的内容;命令与路径名以 implementer 的实际实现为准(不在此处钉字面)。
import { readSkillMd, readExamplesPath2, readTemplate } from './_helpers.mjs';
import { runScenarios, expect, newArgs, core } from './dryrun.mjs';

const md = readSkillMd(), ex = readExamplesPath2();
const desc = (md.match(/^description:\s*(.+)$/m) || [])[1] || '';
const S = [];
const sc = (id, title, fn) => S.push([id, title, fn]);

sc('DOC1', 'description 用用户会说的词,不含内部词', () => {
  expect(desc.length > 40, 'description 缺失或过短');
  for (const w of ['自动迭代改进', '打磨', '多个角度', 'loop'])
    expect(desc.includes(w), 'description 缺触发词 ' + w);
  for (const bad of ['Workflow', 'smoke', 'refresh', 'rubric', 'reviewer', 'playwright', 'persist'])
    expect(!desc.includes(bad), 'description 含内部词 ' + bad);
  expect(/不归它管/.test(desc), 'description 缺「不归它管」的边界');
});
sc('DOC2', '红线:不得用 SendMessage 回复 workflow 子代理;评审零浏览器;不设 isolation', () => {
  expect(/不得用 SendMessage 回复 workflow 子代理/.test(md), '缺「不得用 SendMessage 回复 workflow 子代理」');
  expect(md.includes('评审零浏览器'), '缺「评审零浏览器」');
  expect(md.includes('isolation'), '缺 isolation 红线');
});
sc('DOC3', '截图配方禁止 || 兜底', () => {
  expect(/配方里不写 `\|\|` 兜底/.test(md), '缺「配方里不写 || 兜底」');
});
sc('DOC4', '出口表列全 8 个出口值', () => {
  const sec = md.slice(md.indexOf('## 出口与下一步'));
  for (const e of ['converged', 'evidence-gap', 'decision-gap', 'blocked', 'stalled', 'max-rounds', 'budget', 'error'])
    expect(sec.includes('`' + e), '出口表缺 ' + e);
});
sc('DOC5', '不再出现已删机制与错误用法', () => {
  for (const bad of ['treadmill', 'oscillating', 'missingStates', 'decision_log', 'META_AGENT_SCHEMA', 'P1 meta-agent', 'paused.latest.md', 'persist', 'read-state', 'human-hint-r', 'resumeFromRunId: "<runtag>"', 'final_report', '§5.1', 'implementer = opus'])
    for (const [n, t] of [['SKILL.md', md], ['examples/path2.md', ex]]) expect(!t.includes(bad), `${n} 仍含已删/过时内容 ${bad}`);
});
sc('DOC6', 'examples/path2.md 不含已知过时的项目细节', () => {
  for (const bad of ['data-role-node', '.hrow', 'roleVisible', 'selectedEventId', '__e2e.chart()', 'bottom_breakout_burst', 'specs/2026-06-02-path2-web-ui-design.md', '派 tom'])
    expect(!ex.includes(bad), 'examples/path2.md 含过时内容 ' + bad);
});
sc('DOC7', 'args 表覆盖模板校验后产生的全部 cfg 字段(内部字段除外)', () => {
  const { cfg, errors } = core().validateArgs(newArgs());
  expect(!errors.length, 'validateArgs: ' + errors.join(';'));
  const internal = new Set(['skillDir', 'debug', 'derived', 'argsHash', 'terms', 'root', 'W', 'skill']);
  const sec = md.slice(md.indexOf('## args'), md.indexOf('## 智能入口层'));
  for (const k of Object.keys(cfg)) if (!internal.has(k)) expect(sec.includes('`' + k + '`'), 'SKILL.md args 表缺 ' + k);
});
sc('DOC8', '模板头注释不再引用不存在的测试与已失效出处', () => {
  const t = readTemplate();
  expect(!/tests\/dryrun\.mjs 场景全绿/.test(t), '头注释仍写旧的「场景全绿」');
  expect(!t.includes('docs/tmp/2026-06-12-web-loop-skill-improvements.md'), '头注释引用失效文档');
});

const fail = await runScenarios(S);
process.exit(fail ? 1 : 0);
