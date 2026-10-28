import { readTemplate, assertContains, assertMatches, assertNotContains, ok } from './_helpers.mjs';
const src = readTemplate();

// implementer prompt 重写
assertContains(src, 'impl-${rtag}', 'implementer label 存在');
assertMatches(src, /impl-\$\{rtag\}[\s\S]{0,4000}本次 GOAL/, 'implementer prompt 含「本次 GOAL」段');
assertMatches(src, /impl-\$\{rtag\}[\s\S]{0,5000}GOAL 子项清单/, 'implementer prompt 含子项清单段');
assertMatches(src, /impl-\$\{rtag\}[\s\S]{0,4000}参考图/, 'implementer prompt 含参考图段');
assertMatches(src, /impl-\$\{rtag\}[\s\S]{0,5000}已 verified 子项/, 'implementer prompt 含已 verified 段');

// role=goal 条件性强制读 refs
assertMatches(src, /role.*goal.*第一轮.*强制|第一轮.*role.*goal/, 'refs Read 限 role=goal + 第一轮');

// 反锚定句(轮 ≥2)
assertContains(src, '勿偏离 GOAL 全局', '轮 ≥2 反锚定句');

ok('test-implementer-prompt');
