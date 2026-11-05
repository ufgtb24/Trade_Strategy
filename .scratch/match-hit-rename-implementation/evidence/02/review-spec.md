# 票 02 独立审查：需求轴

固定点 cc46e73，审查时分支尖 5a60980。下面是审查子代理的原始报告。

**结论：改名主体正确，缺部分验收证据，另有几处小错。** `hit_stocks` 与 `per_pattern.hits` 没分错（夹具也对），03 的名字没动，夹具无旧键，`tests/path2_web` 没改错。数据墙未破，跳过 `miss-detection` 正是为此。

**(a) 缺失**
1. 「全套指…`npx playwright test`」：22 个 spec 只跑 13 个。本票改过的 `sidebar-chart-focus`、`subchart-blankclick-yaxis`、`subchart-scroll-drag` 没跑，01 基线也没有。
2. 「全仓代码里不再有 `"matches"`」：`.scratch/annotation-path2/scripts/01-dump-proto-data.py:68` 还读 `ana["matches"]`，`api_check.txt` 却报 0。脚本已跑不通，单列进完成记录即可。
3. 「失败清单与基线相同」：`logs/` 无 vitest、vue-tsc 改后日志。我复跑：vitest 同基线 4 失败，vue-tsc 无错。

**(b) 越界**：无。

**(c) 做错**
1. 「局部名留给 03」：`match-event-disambig.spec.ts:85` 注释写成 `props.hits`，prop 仍叫 `matches`。
2. 同文件 :91、`sidebar-chart-focus.spec.ts:328` 等取 hit 的 `event_id`，该键不存在。基线就坏，非本票引入，应改 `hit_id` 或转 03。
3. `key_grep.txt` 仍列 `any_match`，HEAD 已无，证据未重新生成。

## 处理

- (a)1：照实写进完成记录。没跑的 spec 写死了不在的旧扫描，基线上每条等满 600 秒超时才失败（票 01 已实测），本批不修。
- (a)2：单列进完成记录，没改。这是已 resolved 的决定票的原型取数脚本，属历史资产。
- (a)3：已补 `logs/vitest-after-failures.txt`、`logs/vue-tsc.log`。
- (c)1：已修。
- (c)2：不修，交代给 03（共用执行边界第 4 条）。
- (c)3：已重新生成。
