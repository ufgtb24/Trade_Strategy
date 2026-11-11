<template>
  <div v-if="count > 0" class="candidate-banner" data-testid="candidate-banner">
    <span class="mono">candidates {{ count }}</span>
    <span class="mono">←/→</span>
    <span class="mono">Esc</span>
  </div>
  <div v-else-if="same" class="candidate-banner" data-testid="same-day-hits"
       title="several hits buy on this same day and are drawn as one mark; the bold frames show only the selected one">
    <span class="mono">hit {{ same.index + 1 }}/{{ same.ids.length }}</span>
    <span v-if="arrows" class="mono">←/→</span>
  </div>
</template>

<script setup lang="ts">
// 两种情形共用这一条(同一个位置、同样的高度):
// - 多归属待选:一个记号(或共用对象)属于几次 hit、买入日又不全一样时出现。bracket 折叠后一行可含几十次 hit,
//   逐个圈号已无意义,只报个数;候选在 bracket 上加框,←/→ 在候选间走、点其中一个选定,Esc 取消。
// - 同一天的几次 hit:选中的那次 hit 和别的几次买在同一天(只差切法),图上并成一个 ▼、一格,加粗框只标选中的
//   那一次。这里写「hit k/n」;当家行是 hits 行时 ←/→ 能换到同一天的下一次,才写 ←/→(当家行是样本时
//   ←/→ 走的是样本,不写)。
import { computed } from 'vue'
import { storeToRefs } from 'pinia'
import { useViewStore } from '../stores/view'
import type { HitDict } from '../types'

defineProps<{ hits: HitDict[] }>()
const view = useViewStore()
const { candidateHitIds, sameDayHits } = storeToRefs(view)

const count = computed<number>(() => candidateHitIds.value.size)
// Shift 配对待定时让位给它那一条(ShiftPairBanner),两条不叠着出
const same = computed(() => (view.shiftPairPending ? null : sameDayHits.value))
const arrows = computed(() => view.activeFamily?.kind === 'bracket')
</script>

<style scoped>
/* spec 2026-07-03-subchart-boundary-model §3:滚动容器外的独立条件行,位于 divider 与
   sub-outer 之间;candidate 态出现时主图伸缩 16px,canvas 内容绝对位置不动。 */
.candidate-banner {
  height: 16px;
  line-height: 16px;
  padding: 0 8px;
  font-size: 12px;
  color: #fbbf24;
  background: rgba(15, 23, 42, 0.92);
  border-radius: 3px;
  user-select: none;
  flex-shrink: 0;
}
.candidate-banner[data-testid="candidate-banner"] { pointer-events: none; }
.mono { font-family: ui-monospace, "JetBrains Mono", "DejaVu Sans Mono", Consolas, monospace; margin-right: 12px; }
</style>
