import { readTemplate, assertContains, assertMatches, assertNotContains, ok } from './_helpers.mjs';
const src = readTemplate();

// subgoalCoverage 聚合
assertContains(src, 'subgoalCoverage', 'subgoalCoverage 变量存在');

// converged 判据加严
assertMatches(src, /converged\s*=\s*\(allPass\s*&&\s*openMust\.length===0\s*&&\s*allSubgoalsCovered\)/, 'converged 判据加严含 allSubgoalsCovered');

// allSubgoalsCovered 计算
assertContains(src, 'allSubgoalsCovered', 'allSubgoalsCovered 变量');
assertMatches(src, /allSubgoalsCovered\s*=[\s\S]{0,400}coveredSubgoals/, 'allSubgoalsCovered 引用 coveredSubgoals');

// 旧判据彻底被替换(不能存在裸的 converged=(allPass && openMust.length===0))
assertNotContains(src, 'converged=(allPass && openMust.length===0);', '旧弱判据已删');

ok('test-converged-logic');
