import { readSkillMd, assertContains, assertMatches, ok } from './_helpers.mjs';
const src = readSkillMd();

assertContains(src, 'P1 meta-agent', 'SKILL.md 新节「P1 meta-agent」');
assertContains(src, 'META_AGENT_SCHEMA', 'SKILL.md 提 META_AGENT_SCHEMA');
assertContains(src, 'forbiddenApproaches', 'SKILL.md 提 forbiddenApproaches');
assertContains(src, 'escapeRequest', 'SKILL.md 提 escapeRequest');
assertContains(src, 'decision_log.json', 'SKILL.md 提 decision_log.json');
assertMatches(src, /物理禁[\s\S]{0,200}双源|双源真理/, 'SKILL.md 强调物理禁双源真理');

ok('test-skill-doc-p1');
