// Baseline: workflow-template.js 顶层合法 + meta 块结构存在。
import { readTemplate, assertContains, ok } from './_helpers.mjs';

const src = readTemplate();
assertContains(src, 'export const meta = {', 'meta 块存在');
ok('meta 块存在');
assertContains(src, 'name: "web-iterate-review"', 'meta.name 存在');
ok('meta.name 存在');
assertContains(src, 'phase("setup")', 'setup phase 存在');
ok('setup phase 存在');
assertContains(src, 'phase("iterate")', 'iterate phase 存在');
ok('iterate phase 存在');
assertContains(src, 'phase("finalize")', 'finalize phase 存在');
ok('finalize phase 存在');
ok('test-baseline');
