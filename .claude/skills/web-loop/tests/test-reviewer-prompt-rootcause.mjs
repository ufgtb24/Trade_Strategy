import { readTemplate, assertContains, assertMatches, ok } from './_helpers.mjs';
const src = readTemplate();

// 1. code lens brief 内强制 4 字段必填
assertContains(src, '必填 rootCauseHypothesis', 'code lens brief 强制必填 rootCauseHypothesis');
assertContains(src, '必填 affectedFiles', 'code lens brief 强制必填 affectedFiles');
assertContains(src, '必填 nextStepPlan', 'code lens brief 强制必填 nextStepPlan');

// 2. nextStepPlan 模板字样(策略级,禁代码级)
assertMatches(src, /nextStepPlan[\s\S]{0,1500}策略级|策略级[\s\S]{0,500}nextStepPlan/, 'nextStepPlan 明文「策略级」');
assertContains(src, '禁代码级', 'nextStepPlan 明文「禁代码级」prescription');
assertMatches(src, /读\s*[^\n]{0,40}→\s*改\s*[^\n]{0,40}主线\s*→\s*验证|读 X[\s\S]{0,200}改 Y[\s\S]{0,200}验证 Z[\s\S]{0,200}不要再试 W/, 'nextStepPlan 含「读 X → 改 Y 主线 → 验证 Z → 不要再试 W」模板');

// 3. 跨轮反思段:stuckSignal 程序化注入(P1-5/P0-1 red-line:reviewer 不直接 Read impl.md)
assertContains(src, 'reviewer_stuck', 'reviewer prompt 引用 reviewer_stuck 信号');
// P0-1 part iii 已移除 reviewer 直接 Read impl.md(红线);改由 workflow 程序化注入 stuckSignal
assertMatches(src, /stuckSignal/, 'reviewer prompt 通过 stuckSignal 参数接收 impl.md 反根因(而非直接 Read)');
// dedupBlock 中的换主线逻辑(P1-5 合并段)
assertContains(src, '换主线', 'reviewer prompt 含「换主线」指令(取代旧「不同主线」)');
assertContains(src, '换措辞重写同', 'reviewer prompt 禁「换措辞重写同一 plan」');
// 异议通道通过 reviewer_disagreement 实现(P1-5 dedupBlock)
assertContains(src, 'reviewer_disagreement', 'reviewer prompt 含 reviewer_disagreement 异议通道');

// 4. mustStaleStreak 语义聚类(§3.3):强制 matchesIssueId 优先
assertContains(src, 'matchesIssueId', 'reviewer prompt 引用 matchesIssueId');
assertMatches(src, /matchesIssueId[\s\S]{0,300}引用现有 id|引用现有 id[\s\S]{0,300}matchesIssueId/, '强制「引用现有 id」语义聚类指令');
assertContains(src, '真新增 bug', '只有「真新增 bug」才新立 id');

ok('test-reviewer-prompt-rootcause');
