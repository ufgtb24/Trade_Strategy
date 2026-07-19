<template>
  <div class="pattern-stats-tooltip">
    <div class="row"><span class="label">count</span><span class="val">{{ stats.count }}</span></div>
    <div class="row"><span class="label">mean</span><span class="val">{{ fmtVal(stats.mean) }}</span></div>
    <div class="row"><span class="label">min</span><span class="val">{{ fmtVal(stats.min) }}</span></div>
    <div class="row"><span class="label">q25</span><span class="val">{{ fmtVal(stats.q25) }}</span></div>
    <div class="row"><span class="label">median</span><span class="val">{{ fmtVal(stats.median) }}</span></div>
    <div class="row"><span class="label">q75</span><span class="val">{{ fmtVal(stats.q75) }}</span></div>
    <div class="row"><span class="label">max</span><span class="val">{{ fmtVal(stats.max) }}</span></div>
    <div class="row"><span class="label">win_rate</span><span class="val">{{ fmtWinRate(stats.win_rate) }}</span></div>
  </div>
</template>

<script setup lang="ts">
import type { PatternStats } from '../types'

defineProps<{ stats: PatternStats }>()

function fmtVal(v: number | null): string {
  if (v == null) return '—'
  const pct = (v * 100).toFixed(1)
  return v >= 0 ? `+${pct}%` : `${pct}%`
}

function fmtWinRate(v: number | null): string {
  if (v == null) return '—'
  return `${(v * 100).toFixed(0)}%`
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
</style>
