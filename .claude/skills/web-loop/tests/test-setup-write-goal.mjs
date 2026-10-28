import { readTemplate, assertContains, assertMatches, ok } from './_helpers.mjs';
const src = readTemplate();

// P1-3 已删 goal.json(GOAL 三件套→1.5 件套);原子写随之移除
assertContains(src, 'write-goal', 'write-goal agent label 存在');
assertMatches(src, /label:"write-goal"[\s\S]{0,200}phase:"setup"/, 'write-goal 在 setup phase');
assertContains(src, 'goal.md', 'write-goal 提及 goal.md');
assertMatches(src, /write-goal[\s\S]{0,800}safeInsert/, 'write-goal prompt 用 safeInsert');
assertMatches(src, /summarizeSubgoals/, '调用 summarizeSubgoals');
assertMatches(src, /summarizeRefImages/, '调用 summarizeRefImages');

ok('test-setup-write-goal');
