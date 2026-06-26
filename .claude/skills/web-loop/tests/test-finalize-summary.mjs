import { readTemplate, assertContains, assertMatches, ok } from './_helpers.mjs';
const src = readTemplate();

// finalize prompt 增强各节
assertMatches(src, /finalize[\s\S]{0,3000}## 本次 GOAL/, 'finalize 含 "## 本次 GOAL" 节');
assertMatches(src, /finalize[\s\S]{0,3000}## 参考图/, 'finalize 含 "## 参考图" 节');
assertMatches(src, /finalize[\s\S]{0,3000}## 待补 STATES/, 'finalize 含 "## 待补 STATES" 节');
assertMatches(src, /finalize[\s\S]{0,3000}## 已知设计 risk/, 'finalize 含 "## 已知设计 risk" 节');

// 子项逐条 ✓/✗/?
assertContains(src, '✓', 'SUMMARY 子项 ✓ 状态');
assertContains(src, '✗', 'SUMMARY 子项 ✗ 状态');
assertContains(src, '?', 'SUMMARY 子项 ? 状态');

// requiredStates 单列
assertContains(src, 'requiredStates', 'finalize 提 requiredStates');

// 已知 risk 提主会话拆错
assertContains(src, 'single point of failure', 'finalize 提 single point of failure');

ok('test-finalize-summary');
