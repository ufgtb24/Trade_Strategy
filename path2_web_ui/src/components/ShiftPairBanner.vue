<template>
  <div v-if="shiftPairPending && candidateMatchIds.size === 0" class="shift-pair-banner">
    入口 D · 已选 1/2 — 再 shift+click 一个 event / Esc 取消
  </div>
</template>

<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { useViewStore } from '../stores/view'

const view = useViewStore()
const { shiftPairPending, candidateMatchIds } = storeToRefs(view)
</script>

<style scoped>
/* 与 CandidateStatusBar `.candidate-banner` 视觉字节等价(spec 2026-07-10 §决策 1)。
   两条 banner v-if 排他,同一位置最多一条,总占 16px,不影响 subGeometry。 */
.shift-pair-banner {
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
</style>
