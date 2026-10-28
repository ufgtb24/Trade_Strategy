// SKILL.md 批量文档改动验证(Task 2 + Task 3 共用此文件)。
import { readSkillMd, assertContains, ok } from './_helpers.mjs';

const md = readSkillMd();

// args 表新增字段
assertContains(md, '`goalSubgoals`', 'args 表含 goalSubgoals');
assertContains(md, '`refImages`', 'args 表含 refImages');
assertContains(md, 'verifiable_via', 'goalSubgoals 行含 verifiable_via 字段说明');
assertContains(md, 'role / description / relatedSubgoals', 'refImages 行含 role/description/relatedSubgoals');

// 核心机制第 5 点
assertContains(md, 'GOAL 持久化', '核心机制含 GOAL 持久化');
assertContains(md, 'goal.md', '核心机制提及 goal.md');
assertContains(md, '收敛判据加严', '核心机制提及收敛判据加严');

// 红线
assertContains(md, '`.claude/web-loop/` 必须在', '红线 .gitignore 要求');
assertContains(md, '.gitignore', '红线 .gitignore 要求');
assertContains(md, 'refs 持久化由**主会话**', '红线 refs 责任方 = 主会话');

// 清理豁免清单
// P1-3 删 goal.json,豁免清单只含 goal.md / refs/
assertContains(md, '豁免清单**追加** goal.md / refs/', '清理豁免清单追加(P1-3 已删 goal.json)');

// Task 3 — 智能入口层 2b 末尾增段 + §2c 参考图持久化
assertContains(md, '### 2c 参考图持久化', '智能入口层新增 §2c 节标题');
assertContains(md, 'image-cache', '§2c 提及 image-cache 遍历');
assertContains(md, '`<workdir>/refs/manifest.json`', '§2c 提及 manifest.json');
assertContains(md, '≤ 2MB', '§2c 体积上限 2MB');
assertContains(md, '≤ 2048', '§2c 像素上限 2048');
assertContains(md, '`goal`', '§2c role 三档 - goal');
assertContains(md, '`baseline`', '§2c role 三档 - baseline');
assertContains(md, '`anti-example`', '§2c role 三档 - anti-example');
assertContains(md, '目标 / 现状 / 负例', '§2c description 前缀强制');
assertContains(md, '用户没贴图也合法', '§2c 用户未贴图兜底');
assertContains(md, '拆 1-6 个可勾选的子项', '2b 末尾增段 - 拆子项');
assertContains(md, '回讲点头', '2b 末尾增段 - 回讲');
ok('test-skill-doc · Task 3 §2c');

ok('test-skill-doc · Task 2 batch');
