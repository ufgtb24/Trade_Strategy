import { readTemplate, assertContains, assertMatches, ok } from './_helpers.mjs';
const src = readTemplate();

// implementer prompt 含 forbiddenApproaches 内插段
assertMatches(src, /label:\s*implLabel[\s\S]{0,3000}forbiddenApproaches/, 'implementer prompt 含 forbiddenApproaches');

// 脚本侧 read-state agent 调用(P1-2 合并 read-decision-log + p1-diffstat)
assertMatches(src, /label:`read-state-\$\{rtag\}`[\s\S]{0,200}phase:"iterate"/, 'read-state agent 在 iterate phase');

// forbiddenApproaches union 内插(动态生成段,基于读到的内容)
assertContains(src, 'forbiddenList', 'forbiddenList 变量(union 后内插到 prompt)');

// 优先级 3 段含"不得重试"指令
assertContains(src, '不得重试', 'implementer 强制「不得重试」forbiddenApproaches');

ok('test-p1-implementer-inject');
