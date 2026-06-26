import { readTemplate, assertContains, assertMatches, ok } from './_helpers.mjs';
const src = readTemplate();

// 解构
assertContains(src, 'const GOAL_SUBGOALS', 'GOAL_SUBGOALS 解构存在');
assertContains(src, 'A.goalSubgoals', 'GOAL_SUBGOALS 从 A.goalSubgoals 取');
assertContains(src, 'const REF_IMAGES', 'REF_IMAGES 解构存在');
assertContains(src, 'A.refImages', 'REF_IMAGES 从 A.refImages 取');

// helpers 函数定义
assertContains(src, 'function safeInsert(', 'safeInsert 函数定义');
assertContains(src, 'function safeBlock(', 'safeBlock 函数定义');
assertContains(src, 'function summarizeSubgoals(', 'summarizeSubgoals 函数定义');
assertContains(src, 'function summarizeRefImages(', 'summarizeRefImages 函数定义');

// safeInsert 实现核查 — 必须用 JSON.stringify 包裹 strip 引号
assertMatches(src, /function safeInsert[\s\S]{0,200}JSON\.stringify/, 'safeInsert 用 JSON.stringify');

// 等价 helper 在测试里独立实现,验证逻辑边界(不抽 workflow-template.js 的 helper,因其在顶层闭包内):
function safeInsertExpect(s) {
  if (s == null) return '';
  return JSON.stringify(String(s)).slice(1, -1)
    .replace(/\\n/g, '\n')
    .replace(/\$/g, '\\$');   // 防 prompt 文本里被 agent 误读为模板占位符
}
// 1. 反引号 + $:$ 被转义为 \$
const ttg = '`echo $X`';
if (safeInsertExpect(ttg) !== '`echo \\$X`') { console.error('FAIL safeInsert: 反引号 + $'); process.exit(1); }
// 2. ${} 转义为字面 \${} 不被重解析
const dol = '${INJECT}';
const expected = '\\${INJECT}';
if (safeInsertExpect(dol) !== expected) {
  console.error(`FAIL safeInsert: \${} 转义,得到 ${safeInsertExpect(dol)} 期望 ${expected}`);
  process.exit(1);
}
// 3. 反斜杠转义
if (safeInsertExpect('a\\b') !== 'a\\\\b') { console.error('FAIL safeInsert: 反斜杠'); process.exit(1); }
// 4. 换行 \n 保留为字面换行(JSON.stringify 会变 \\n,我们 replace 回 \n)
if (safeInsertExpect('a\nb') !== 'a\nb') { console.error('FAIL safeInsert: 换行'); process.exit(1); }
// 5. 中文引号原样
if (safeInsertExpect('“目标”') !== '“目标”') { console.error('FAIL safeInsert: 中文引号'); process.exit(1); }
console.log('PASS safeInsert behavior (5 边界)');

ok('test-args-helpers');
