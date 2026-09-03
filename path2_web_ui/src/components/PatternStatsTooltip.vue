<template>
  <div class="pattern-stats-tooltip">
    <div class="block-title block-title--up">forward_return</div>
    <div class="row"><span class="label">count</span><span class="val">{{ stats.count }}</span></div>
    <div class="row"><span class="label">mean</span><span class="val">{{ fmtVal(stats.mean) }}</span></div>
    <div class="row"><span class="label">min</span><span class="val">{{ fmtVal(stats.min) }}</span></div>
    <div class="row"><span class="label">max</span><span class="val">{{ fmtVal(stats.max) }}</span></div>
    <div class="row"><span class="label">q25</span><span class="val">{{ fmtVal(stats.q25) }}</span></div>
    <div class="row"><span class="label">median</span><span class="val">{{ fmtVal(stats.median) }}</span></div>
    <div class="row"><span class="label">q75</span><span class="val">{{ fmtVal(stats.q75) }}</span></div>
    <div class="row"><span class="label">win_rate</span><span class="val">{{ fmtWinRate(stats.win_rate) }}</span></div>
    <!-- drawdown 块(T1 注入):per-pattern 全局最差下行分布,与上方 forward_return stats 同 shape。
         仅当 hover 的 pattern 落盘了 stats_drawdown 时才渲染,老 scan file 无此字段 → 不渲染。 -->
    <div v-if="statsDrawdown" class="stats-drawdown">
      <div class="block-title">drawdown</div>
      <div class="row"><span class="label">count</span><span class="val">{{ statsDrawdown.count }}</span></div>
      <div class="row"><span class="label">mean</span><span class="val">{{ fmtVal(statsDrawdown.mean) }}</span></div>
      <div class="row"><span class="label">min</span><span class="val">{{ fmtVal(statsDrawdown.min) }}</span></div>
      <div class="row"><span class="label">max</span><span class="val">{{ fmtVal(statsDrawdown.max) }}</span></div>
      <div class="row"><span class="label">q25</span><span class="val">{{ fmtVal(statsDrawdown.q25) }}</span></div>
      <div class="row"><span class="label">median</span><span class="val">{{ fmtVal(statsDrawdown.median) }}</span></div>
      <div class="row"><span class="label">q75</span><span class="val">{{ fmtVal(statsDrawdown.q75) }}</span></div>
      <div class="row"><span class="label">win_rate</span><span class="val">{{ fmtWinRate(statsDrawdown.win_rate) }}</span></div>
    </div>
    <!-- 首次穿越块(T3 注入 · T5 展示 · T8 单组化):pattern 整体方向判据 —— 命中集先涨比例 vs 随机日基线。
         ratio / random_ratio 后端已算好(up/(up+down),both/none 排除分母),前端只展示、不再算 lift。
         单组(几何对称单 k);n_bars=0 不渲染(防空标题)。老 scan file 或 first_passage_enabled=False → undefined → 不渲染。 -->
    <div v-if="firstPassageStats && (firstPassageStats.n_bars ?? 0) > 0" class="stats-first-passage">
      <div class="block-title">首次穿越 <span class="fp-k">k={{ firstPassageStats.k }}</span></div>
      <div class="fp-row fp-row--head">
        <span class="fp-label"></span>
        <span class="fp-head">pat</span>
        <span class="fp-sep">vs</span>
        <span class="fp-head">rdm</span>
      </div>
      <div class="fp-row">
        <span class="fp-label">方向</span>
        <span class="fp-val">{{ fmtRatio(firstPassageStats.ratio) }}</span>
        <span class="fp-sep">/</span>
        <span class="fp-val fp-val--rand">{{ fmtRatio(firstPassageStats.random_ratio) }}</span>
      </div>
      <div class="fp-row">
        <span class="fp-label">有效</span>
        <span class="fp-val">{{ fmtRatio(fpEff(firstPassageStats)) }}</span>
        <span class="fp-sep">/</span>
        <span class="fp-val fp-val--rand">{{ fmtRatio(fpEffRand(firstPassageStats)) }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { PatternStats, FirstPassageStats } from '../types'
import { fmtVal, fmtRatio } from '../shared/formatters'

defineProps<{
  stats: PatternStats
  statsDrawdown?: PatternStats
  firstPassageStats?: FirstPassageStats
}>()

function fmtWinRate(v: number | null): string {
  if (v == null) return '—'
  return `${(v * 100).toFixed(0)}%`
}

// 有效比例(非 none)= 触到任一阈值的买点占比 (up+down+both)/n_bars;与 ratio(方向)正交 ——
// ratio 看先涨先跌、有效看路径活跃度(多大比例的买点在 horizon 内动到了 kM 阈值)。
function fpEff(fp: FirstPassageStats): number | null {
  if (!fp.n_bars) return null
  return (fp.up + fp.down + fp.both) / fp.n_bars
}
function fpEffRand(fp: FirstPassageStats): number | null {
  if (!fp.random_n) return null
  return (fp.random_up + fp.random_down + fp.random_both) / fp.random_n
}
</script>

<style scoped>
.pattern-stats-tooltip {
  display: grid;
  grid-template-columns: auto auto;
  gap: 2px 12px;
  padding: 8px 10px;
  background: #1e293b;
  color: #f1f5f9;
  border-radius: 4px;
  font-family: ui-monospace, monospace;
  font-size: 11px;
  min-width: 140px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
  white-space: nowrap;
}
.row { display: contents; }
.label { text-align: left; opacity: 0.75; }
.val { text-align: right; font-weight: 600; }

/* drawdown 块:与上方 forward_return stats 视觉分隔。display:contents 的 .row 不影响布局,
   .stats-drawdown 作为 grid 子项跨两列、内部再展开自己的 8 行(也走 .row display:contents)。 */
.stats-drawdown {
  grid-column: 1 / -1;
  display: grid;
  grid-template-columns: auto auto;
  gap: 2px 12px;
  margin-top: 6px;
  padding-top: 6px;
  border-top: 1px solid rgba(241, 245, 249, 0.18);
}
.block-title {
  grid-column: 1 / -1;
  font-weight: 700;
  font-size: 10px;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: #fbbf24;   /* 与 ret-neg 红 / win_rate 中性 区分,提示这是下行分布 */
  margin-bottom: 2px;
}
.block-title--up { color: #4ade80; }   /* forward_return 上行/正向,与 drawdown 黄、首次穿越蓝区分(文字标签为主,颜色辅助) */

/* 首次穿越块(T5 · T8 单组化):与 drawdown 块同结构(跨两列分隔块),仅单行。
   命中集先涨% · / · 随机% —— 命中集用满亮度白、随机用半透明,饱和度差区分(色盲友好)。
   不用红绿:up/down 已是方向语义,但此处只展示「先涨比例」单一数值,无对偶色需求。 */
.stats-first-passage {
  grid-column: 1 / -1;
  display: grid;
  grid-template-columns: auto auto auto auto;
  gap: 2px 8px;
  margin-top: 6px;
  padding-top: 6px;
  border-top: 1px solid rgba(241, 245, 249, 0.18);
}
.stats-first-passage .block-title { color: #60a5fa; }   /* 蓝色,与 drawdown 黄区分 */
.fp-k { color: #93c5fd; font-family: ui-monospace, monospace; font-size: 10px; }   /* 浅蓝(比标题蓝 #60a5fa 更浅),与深色背景区分 */
.fp-row { display: contents; }
.fp-label { text-align: left; opacity: 0.6; font-size: 10px; }   /* 方向/有效 行标签 */
.fp-head { text-align: right; opacity: 0.6; font-size: 9px; }   /* pat/rdm 表头:右对齐 val 列,颜色与 fp-label 行名一致 */
.fp-val { text-align: right; font-weight: 600; }
.fp-val--rand { opacity: 0.6; font-weight: 400; }   /* 随机基线弱化,命中集为主 */
.fp-sep { opacity: 0.4; text-align: center; }
</style>
