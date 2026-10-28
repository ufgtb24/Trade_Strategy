import { readTemplate, assertContains, assertMatches, ok } from './_helpers.mjs';
const src = readTemplate();

// reviewerPrompt 函数体内含
assertContains(src, 'function reviewerPrompt', 'reviewerPrompt 函数');
assertMatches(src, /reviewerPrompt[\s\S]{0,4000}本次 GOAL/, 'reviewerPrompt 含「本次 GOAL」');
assertMatches(src, /reviewerPrompt[\s\S]{0,4000}GOAL 子项清单/, 'reviewerPrompt 含「GOAL 子项清单」');
assertMatches(src, /reviewerPrompt[\s\S]{0,4000}第一步.*建立视觉基准/, 'reviewerPrompt 含「第一步 · 建立视觉基准」');
assertMatches(src, /reviewerPrompt[\s\S]{0,5000}第二步.*GOAL 子项逐条复核/, 'reviewerPrompt 含「第二步 · GOAL 子项逐条复核」');

// role 三档明文
assertMatches(src, /role=goal[\s\S]{0,200}靠近/, 'role=goal 明文「靠近」');
assertMatches(src, /role=baseline[\s\S]{0,300}禁模仿|禁止把它当 goal 模仿/, 'role=baseline 明文「禁模仿」');
assertMatches(src, /role=anti-example[\s\S]{0,200}远离/, 'role=anti-example 明文「远离」');

// evidence ⚠⚠ + 4 类
assertContains(src, '⚠⚠', 'evidence ⚠⚠ 双重叹号');
assertContains(src, 'screenshot', 'evidence 类 screenshot');
assertContains(src, 'console', 'evidence 类 console');
assertContains(src, 'probe', 'evidence 类 probe');
assertContains(src, 'diff', 'evidence 类 diff');
assertContains(src, '看起来满足', '明禁不可定位修辞「看起来满足」');

// lens 分级 — ux 必读 / func 摘要 / code 不读
assertMatches(src, /reviewerPrompt[\s\S]{0,5000}ux[\s\S]{0,500}Read 每张|必读全图/, 'ux 必读 refs');
assertMatches(src, /reviewerPrompt[\s\S]{0,5000}func[\s\S]{0,500}description 摘要|不强制 Read 图/, 'func 不强制 Read 图');
assertMatches(src, /reviewerPrompt[\s\S]{0,5000}code[\s\S]{0,500}不 Read refs|不强制读图/, 'code 不读 refs');

// func brief 增强:首要轴① 子项复核
assertContains(src, '首要任务 = 对照 GOAL 子项清单', 'func brief 首要轴① 子项复核');

// 反锚定 goalEcho
assertContains(src, 'goalEcho', 'reviewer prompt 提 goalEcho');
assertContains(src, '注意力归位', 'goalEcho 标注作用');

// 调用点传新参数
assertMatches(src, /reviewerPrompt\(lens,[\s\S]{0,400}goalSubgoalsSummary/, '调用点传 goalSubgoalsSummary');
assertMatches(src, /reviewerPrompt\(lens,[\s\S]{0,400}refImagesSummary/, '调用点传 refImagesSummary');

ok('test-reviewer-prompt');
