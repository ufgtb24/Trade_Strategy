import { readTemplate, assertContains, assertNotContains, ok } from './_helpers.mjs';
const src = readTemplate();

// 把 reviewerPrompt 函数体切出来单独执行(它只读参数,不碰 workflow 全局)
const start = src.indexOf('const ADVERSARIAL_LENS_BRIEF=');
const end = src.indexOf('\n}\n', src.indexOf('function reviewerPrompt(', start));
const reviewerPrompt = new Function(`${src.slice(start, end + 2)}; return reviewerPrompt;`)();

const issues = [
  { id: 'ux-r1-1', lens: 'ux', title: 'UX_ISSUE_MARK', severity: 'must', status: 'open' },
  { id: 'newbie-r1-1', lens: 'newbie', title: 'NEWBIE_ISSUE_MARK', severity: 'must', status: 'open' },
];
const ctx = {
  round: 2, GOAL: 'g', RUBRIC_PATH: 'rubric.md', shotList: 's', issuesJson: JSON.stringify(issues),
  consoleNote: '', probeNote: '', verifiedJson: '[{"title":"VERIFIED_MARK"}]',
  goalSubgoalsSummary: 'G1', refImagesSummary: '', WORKDIR: 'w', stuckSignal: '',
};

// 每个 lens(含未登记的名字)都不能把 undefined 拼进 prompt
for (const lens of ['ux', 'func', 'code', 'rival', 'razor', 'newbie', 'some_custom_lens']) {
  assertNotContains(reviewerPrompt(lens, ctx), 'undefined', `${lens} prompt 无 undefined`);
}

// 对抗 lens 各有自己的说明
assertContains(reviewerPrompt('rival', ctx), '第二位独立复核员', 'rival brief');
assertContains(reviewerPrompt('rival', ctx), '建立视觉基准', 'rival 与 ux 同样必读 refs');
assertContains(reviewerPrompt('razor', ctx), '剃刀', 'razor brief');
assertContains(reviewerPrompt('newbie', ctx), '先只看截图', 'newbie brief');
assertContains(reviewerPrompt('some_custom_lens', ctx), '「some_custom_lens」', '未登记 lens 走兜底说明');

// newbie 保持第一眼:看不到别的 lens 的已验证项与问题,只看得到自己名下的旧问题
const nb = reviewerPrompt('newbie', ctx);
assertNotContains(nb, 'VERIFIED_MARK', 'newbie 不给 verified');
assertNotContains(nb, 'UX_ISSUE_MARK', 'newbie 不给别的 lens 的 issue');
assertContains(nb, 'NEWBIE_ISSUE_MARK', 'newbie 看得到自己的旧 issue(才能表态 stillPresent)');

// 其他 lens 照旧看到全部
const ux = reviewerPrompt('ux', ctx);
assertContains(ux, 'VERIFIED_MARK', 'ux 照旧给 verified');
assertContains(ux, 'NEWBIE_ISSUE_MARK', 'ux 照旧给全部 issue');

ok('test-reviewer-prompt-adversarial');
