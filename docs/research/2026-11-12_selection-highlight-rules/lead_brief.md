# lead 交给全队的共同背景（事实，不是结论）

## 已核实的现状（2026-11-12，CRNC、pattern new_step、compare 模式，lead 在真页面用 store 读出）

| 选中 | 路径 | 粗框（focus）| 细深框（group，band 上点亮的 event）| hits 行格子上的细实线框 | 琥珀闪烁 | 粗底线 |
|---|---|---|---|---|---|---|
| event today 12-02（today_795#0）| node › event | today 12-02 的 ▼ | 一个随手挑的 plateau（09-16→12-02，plateau_741_795#0，不在任何 hit 里）及其 old_plat 09-16→10-04、step 10-07、new_plat 10-08→11-29、today 12-02 | 用到它的 2 次 hit（774-795#0、#1）| 无 | 无 |
| 买点日 12-02（这天叠着 2 次 hit）| hit_family › buy | **无**（被选中的 ▼ 那格什么都不画）| 两次 hit 组成的合集：plateau 10-31→12-02 ×2、old_plat 10-31→11-20、step 11-21→11-22 与 step 11-21、new_plat 11-25→11-29 与 new_plat 11-22→11-29、today 12-02 | 无 | 无 | 族 hits@774 |
| event step 11-21→11-22（step_789_790#0）| node › event | 那格 step | 一个随手挑的 plateau（10-31→11-26，plateau_774_792#1，不在任何 hit 里）及其 old_plat、step、new_plat 11-25、today 11-26 | 用到它的 11 次 hit | 无 | 无 |
| 一次 hit（774-795#0）| hit_family › buy › hit | hits 行那格 | 它的组成：plateau、old_plat、step 11-21、new_plat 11-22→11-29、today 12-02 | 无 | 无 | 族 hits@774 |

粗框 = 深色 #1e293b 2.5px + 阴影；细深框 = 同色 1.5px + 同样阴影。肉眼几乎分不出。

## lead 诊断出的问题

1. 「选中的那一个」和「跟它有关的」是同一种画法（深色实线框，只差 1px），用户分不出竖线上哪个是选中的。hits 行「用到这个 event 的 hit」的细实线框看起来也像选中。
2. 选中买点日（一整天）时，被选中的 ▼ 本身没有任何标记（规格写的是「选中的那一个粗框」）。
3. 选中一整天时点亮的是几次 hit 组成的合集：同一条 band 上框了两个 event，看起来像选中了多个。
4. 选中 event 时有一条更早的「组成型一选全选」规则（view.ts 的 compositionGroupIds）：取 child_refs 里第一个找到的上层 event 的整套组成。它默认一个子段只属于一个上层 event；现在 step_789_790#0 被 39 个 plateau 共用、today_795#0 被 3 个共用，挑中的常常不在任何 hit 里——在 `in_hit` 档下画不出来或在视窗外，于是用户看到「new_plat 没被选中」。这条规则不在规格「图上」那一句里，是旧功能残留。

## 代码位置（行号是 2026-11-12 的近似值，先 grep）

- `path2_web_ui/src/stores/view.ts`：highlightedEventIds、compositionGroupIds、candidateHitIds、pendingDisambigInstanceId、markedHitIds / markedEventIds（侧栏常标）、activeFamilyKey；选中动作 clickBuyDay / clickHitCell / clickFamilyLine / focusMark / focusHit / clickFeedback / selectNode / setPath。
- `path2_web_ui/src/render/chart.ts`：buildHlShape（group / focus / pendingDisambig 三种画法）、HL_* 常量、makeRenderBracket（hits 行的格与 ▼；粗框只在选中一次 hit 时画）、当前日竖线 CURSOR_*。
- `path2_web_ui/src/render/select.ts`、`selWorld.ts`、`walk.ts`、`selSnapshot.ts`：选中路径、同层 / 里面、显示栏与选中卡的文字。
- `path2_web_ui/src/components/KlineChart.vue`：反馈竖带（选中的反馈、开着的作答面板）。

## 规格与前序研究

- 规格 `.scratch/annotation-path2/spec.md`：grep「选中（2026-11-12 定）」那一段（点什么选中什么的表、按键走动、显示栏、选中卡、「图上：选中的那一个粗框」那一句、侧栏常标）；1.13、1.14；6.13（反馈记号）。说明书 `.scratch/annotation-path2/manual.md`。
- 前序研究：`docs/research/2026-11-11_selection-business-entities/final_report.md`、`切换规律.md`（选中路径与八种可选中的东西）；`docs/research/2026-11-11_one-to-many-selection/final_report.md`、`user_tasks.md`（用户用这个工具做什么）。
- 词表：`path2/GLOSSARY.md`、`path2_web/GLOSSARY.md`（grep 定位，只读那一段）。

## 在真页面上复现

前端 http://localhost:5171/ 、后端 8001（用户正在用，别重启）。打开后：symbol 框填 CRNC 回车，点 `compare`。store：

```js
const v = document.querySelector('#app').__vue_app__.config.globalProperties.$pinia._s.get('view')
v.focusMark(['today_795#0'])                       // 选中一个 event
v.setPath([{kind:'hit_family',familyKey:'hits@774'},{kind:'buy',day:795}])   // 选中买点日 12-02
v.focusHit('new_step@774-795#plateau:plateau_774_795#0', {day: 795})          // 选中一次 hit
// 读：v.selPath、v.highlightedEventIds、v.compositionGroupIds、v.candidateHitIds、v.pendingDisambigInstanceId、v.activeFamilyKey
```

默认整段视窗很宽，看 12-02 附近要在主图上滚轮放大。
