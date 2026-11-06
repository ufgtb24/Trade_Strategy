<template>
  <div v-if="count > 0" class="candidate-banner">
    <span class="mono">candidates {{ count }}</span>
    <span class="mono">←/→</span>
    <span class="mono">Esc</span>
  </div>
</template>

<script setup lang="ts">
// 多归属待选:一个记号(或共用对象)属于几次 hit 时出现。bracket 折叠后一行可含几十次 hit,逐个圈号已无意义,
// 只报个数;候选在 bracket 上加框,←/→ 在候选间走、点其中一个选定,Esc 取消。
import { computed } from 'vue'
import { storeToRefs } from 'pinia'
import { useViewStore } from '../stores/view'
import type { HitDict } from '../types'

defineProps<{ hits: HitDict[] }>()
const view = useViewStore()
const { candidateHitIds } = storeToRefs(view)

const count = computed<number>(() => candidateHitIds.value.size)
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
  pointer-events: none;
  flex-shrink: 0;
}
.mono { font-family: ui-monospace, "JetBrains Mono", "DejaVu Sans Mono", Consolas, monospace; margin-right: 12px; }
</style>
