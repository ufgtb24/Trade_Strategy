# 票 13 独立审查 · Standards（对照成文编码规范 + 坏味道基线）

审查范围：`git diff e4297b344b47925e4b7bc1469cc6b1c893c74b34...23ec7c0`（分支 impl/13-scan-tier）。审查子代理只读，看不到执行过程。

**硬违规：未见。** 已核对：
- 改动文件里没有引用 `docs/research`。
- 没碰 2026 年起的数据。
- 界面固定文字都是英文等宽。
- `no_scan` 用灰字，它是空状态，规范允许。
- 没有新色值，截图也没调过尺寸。
- 票 13 第 26 行认可沿用 `mode` 加 `appSource` 的表示，所以不报 Primitive Obsession。

**判断题：**
1. 可能是 Duplicated Code，有三处：
   - `view.ts` 的 `selectSymbol`、`enterScan`、`loadScanFile` 重复同一串进 scan 的赋值（mode、appSource、symbol、scanStop、resetChartState、runPreview）。
   - `leaveScan` 和 `openSymbol` 重复 `scanReturn=null; scanPicked=false`。
   - 测试里的 `scanOf` 在 `stores.scan-tier.spec.ts` 和 `components/scan-tier.spec.ts` 各抄了一份。
2. 可能是 Data Clumps 或 Shotgun Surgery：`scanStop`、`scanReturn`、`scanPicked` 总是一起读写，散在 7 个 action 里。
3. 可能是 Mysterious Name：`scanStop`、`scanReturn` 看不出装的是股票；`frontSymbol` 的 front 在词表里没有。
4. 小处不一致，两处：
   - `KlineChart.vue` 新分支的注释写 no_scan，条件却是 `!symbol.value`。
   - no_scan 有两处悬停说同一件事，措辞不同，其中 `ChartArea` 那处中英混排。
5. 叫法残留：`KlineChart.vue:158` 的「扫描结果的 app」、`stores.view-mode.spec.ts` 第 1 行和第 100 行、`TopBar` 的「主视图顶栏」，和本票改后的 scan 档叫法不一致。store 层仍是 `mode=app`，所以这些不算写错。
