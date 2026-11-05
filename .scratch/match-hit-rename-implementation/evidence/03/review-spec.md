# 票 03 独立审查 · Spec 轴

固定点 85ec540，提交 45a2829、ac60f81、29cacfe。子代理原文（路径相对 worktree 的 `path2_web_ui/`），末尾「处理」是执行者写的。

重点项都没问题：残留的 match、匹配逐行读过，全属允许类别；allow_03.tsv 判定都对；参数快照 match、对照 tag、正则没被误改；派生名与对照表一致。vitest 实跑失败 4 条，同基线；vue-tsc（用 --noEmit）通过。

**(a) 只做了一部分**
1. 「`npx playwright test` 的失败清单与基线相同」：只跑了 13/22 个文件。改过的 sidebar-chart-focus、subchart-blankclick-yaxis、subchart-scroll-drag 没实跑，证据里没写原因。证据也缺改后 vitest、vue-tsc 日志。
2. 「英文标识符风格、等宽字体；解释放进悬停提示」：`src/render/chart.ts` 悬停的 `hit:`、`归属: hit`、`确认: N 个 hit 共享此买点` 非等宽（读代码判断，未看渲染）；侧栏残缺 hit 提示仍是说明句。

**(b) 范围蔓延**：无实质问题。`_previewApplies`、`hasHit` 不在表内，须按「写旧名、新名和理由」记入完成记录。

**(c) 看着不对**
1. `src/render/annotateLanes.ts:303`、`:334` 有同样的断引号，只修了 `:389`（不归本票验收）。
2. 仓库根 `configs/path2_web.yaml` 端口未按「跑完复原」改回，未提交。
3. 拿不准：`patternHitCounts` 数的是股票数，与 `hit_stocks` 规则同类。

## 处理

- (a)1：e2e 清单是调度会话按票 02 的 `run_e2e.sh` 定的，没跑的文件和原因写进完成记录；改后 vitest、vue-tsc 日志补进 `logs/`；另加一个静态核对（`e2e_static_check.py`），确认没实跑的 spec 用到的 store 名字和类名都存在。
- (a)2：已修，见 Standards 报告的「处理」；残缺 hit 提示改成 `⚠ dropped_hits: N`，说明进悬停。
- (b)：派生名写进完成记录。
- (c)1：已修，三处收成一个 `monoTip`。这两处不是本票要求的，同一个文件、同一个缺陷，一起修掉。
- (c)2：验收跑完复原，配置改动没提交。
- (c)3：已修，见 Standards 报告的「处理」。
