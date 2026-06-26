// 验 mergeIssues 持久化 REVIEWER_SCHEMA 输出的 4 决策字段
// P0-1 part (i) 的 TDD RED test
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const TEMPLATE = resolve(__dirname, '..', 'workflow-template.js');
const src = readFileSync(TEMPLATE, 'utf8');

// 提取 mergeIssues 函数源码 + 在隔离作用域里 eval(简易,只为测纯函数)
// nextId 也需要被提取(mergeIssues 依赖)
// nextId 是单行函数(无 \n 前的 }),用 [^\n]+ 捕获整行
const nextIdMatch = src.match(/function nextId[^\n]+/);
const mergeMatch = src.match(/function mergeIssues[\s\S]+?\n\}/);
assert(nextIdMatch, 'nextId 函数未找到');
assert(mergeMatch, 'mergeIssues 函数未找到');

const wrapper = `
const seqCounter = {};
${nextIdMatch[0]}
${mergeMatch[0]}
export { mergeIssues, nextId };
`;
const dataUrl = 'data:text/javascript;base64,' + Buffer.from(wrapper).toString('base64');
const { mergeIssues } = await import(dataUrl);

// 场景 1:新建 issue 必须持久化 nextStepPlanHistory(4 决策字段历史数组)
const issues = [];
const presentRound1 = [{
  lens: 'code',
  knownIssuesStatus: [],
  issues: [{
    title: 'K线 grid 高度不足',
    severity: 'must',
    rootCauseHypothesis: '父容器 flex 比例配错',
    affectedFiles: ['src/Chart.vue:42', 'src/styles/grid.css:18'],
    suggestedFix: '改 grid: 6fr 1fr 为 grid: 8fr 1fr',
    nextStepPlan: '读 Chart.vue 22-50 → 改 grid 主线 → 验证截图 G1'
  }]
}];
mergeIssues(issues, presentRound1, 1);
assert.equal(issues.length, 1, '应新建 1 个 issue');
assert(Array.isArray(issues[0].nextStepPlanHistory), 'nextStepPlanHistory 字段缺失');
assert.equal(issues[0].nextStepPlanHistory.length, 1, '首轮应有 1 条历史');
const h0 = issues[0].nextStepPlanHistory[0];
assert.equal(h0.round, 1);
assert.equal(h0.rootCauseHypothesis, '父容器 flex 比例配错');
assert.deepEqual(h0.affectedFiles, ['src/Chart.vue:42', 'src/styles/grid.css:18']);
assert.equal(h0.suggestedFix, '改 grid: 6fr 1fr 为 grid: 8fr 1fr');
assert.equal(h0.nextStepPlan, '读 Chart.vue 22-50 → 改 grid 主线 → 验证截图 G1');

// 场景 2:status=regressed 路径(matchesIssueId 命中 fixed → regressed)也要 append 新历史
issues[0].status = 'fixed';
const presentRound2 = [{
  lens: 'code',
  knownIssuesStatus: [],
  issues: [{
    matchesIssueId: issues[0].id,
    title: 'K线 grid 高度回归',
    severity: 'must',
    rootCauseHypothesis: 'r1 修法在某 viewport 失效',
    affectedFiles: ['src/Chart.vue:42'],
    suggestedFix: '加 media query',
    nextStepPlan: '换 affectedFiles 主线:从 grid 改 viewport responsive'
  }]
}];
mergeIssues(issues, presentRound2, 2);
assert.equal(issues[0].status, 'regressed', '应被标 regressed');
assert.equal(issues[0].nextStepPlanHistory.length, 2, 'regressed 路径应 append 第 2 条历史');
assert.equal(issues[0].nextStepPlanHistory[1].round, 2);
assert.equal(issues[0].nextStepPlanHistory[1].nextStepPlan,
  '换 affectedFiles 主线:从 grid 改 viewport responsive');

console.log('PASS · test-mergeissues-fieldflow');
