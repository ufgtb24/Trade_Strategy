import { readExamplesPath2, assertContains, ok } from './_helpers.mjs';
const md = readExamplesPath2();

assertContains(md, 'goalSubgoals', 'path2.md 含 goalSubgoals');
assertContains(md, 'refImages', 'path2.md 含 refImages');
assertContains(md, '"role": "goal"', 'path2.md 含 "role": "goal" 示例');
assertContains(md, '"role": "baseline"', 'path2.md 含 "role": "baseline" 示例');
assertContains(md, 'verifiable_via', 'path2.md 含 verifiable_via 示例');
assertContains(md, 'measurable', 'path2.md 含 measurable 示例');
assertContains(md, 'K 线', 'path2.md 含 K 线相关示例');

ok('test-examples-path2');
