# 票 02 独立审查：规范轴

固定点 cc46e73，审查时分支尖 5a60980。下面是审查子代理的原始报告。

**硬违规**
1. `e2e/match-event-disambig.spec.ts:85,90-91`、`e2e/sidebar-chart-focus.spec.ts:183,328,332,455`：对 `hits` 仍读 `m.event_id`。违反 CLAUDE.md 编码规范「术语」（该词已退役）。问题是旧的，但就在改动行或其紧邻；`HitDict` 没有此字段。disambig 三条 e2e 为 ✘，是否同因未验证。
2. `eval_runner.py:269,409,412` 的 `tickers_hit`、`universe_hit_tickers` 与 `hit_stocks` 同义。违反 GLOSSARY-MAP 命名规则 2，无票接手。

**判断题**
- 续行未对齐：`eval_runner.py:416-417`，缩进 27 应为 24（脚本扫全 diff 仅此处）。
- Mysterious Name：`target_hits` 是布尔却读作列表（对照表定的）；`view.ts:473` 布尔 `_previewHits` 紧邻 `pv.analysis.hits`，无票接手。
- 同名两义：`KlineChart.vue:171` `hits: packHits(a.hits…)`，前者是 `{rows,placed}`，后者是列表；`serialize.py:466` 的 summary（数）与 analysis（列表），spec 定的。
- 注释不符：
  - `DetailSidebar.vue:373` 称 `dropped_hits` 已进 `AnalysisResult`，实无此字段，读取恒空（兼 Speculative Generality）。
  - `match-event-disambig.spec.ts:85` 写 `props.hits`，实际 prop 仍是 `matches`。
  - `miss-detection-walkthrough.spec.ts:12` 与夹具 docstring 写 `scan.py:80-81`，实在 142-144。
- 改名不一致：`scan.py` 的 `hc`/`hfp` 改了，`serialize.py:446` 的 `m_counts` 没改。
- 证据：`check_scan_keys.py` 的 `path` 只传不用（Speculative Generality）；`key_grep.txt` 记的 `any_match` 残留已被 c688066 修掉，重跑为零，文件过时。

未见旧键双读，符合 scan-file-no-backcompat。

## 处理

- 硬违规 1：不修，交代给 03。`event_id` 不是本票改的键；这几个 e2e 在基线上就失败，共用执行边界第 4 条写明本批不修。
- 硬违规 2：已修。`tickers_hit` → `hit_stocks`，`universe_hit_tickers` → `universe_hit_stocks`（`eval_runner.py`、`path2_eval_scan.py`、`path2_eval_bottom_burst.py` 的打印标签、`test_eval_runner.py`）。
- 续行对齐：已修。
- `props.hits` 注释：已修，改回 `props.matches`，这个 prop 归 03 改。
- `check_scan_keys.py` 的 `path`、过时的 `key_grep.txt`：已修、已重新生成。
- 不改：
  - `target_hits`：对照表定的名字。
  - `_previewHits`：通用的 hit，在 `stores/view.ts`，归 03 按允许列表判断。
  - `KlineChart.vue:171` 的 `hits`：`packHits` 的结果和 hit 是同一件事，局部名归 03。
  - `summary.hits` 与 `analysis.hits` 同名：spec 表定的。
  - `DetailSidebar.vue:373` 的注释：之前就不准，本票只按对照表换键名；要不要删这段死代码不在本批范围。
  - `scan.py:80-81` 的行号引用：之前就过时，和改名无关。
  - `serialize.py` 的 `m_counts`：跟循环变量 `m` 走，票 01 已定 `m` 不改。
