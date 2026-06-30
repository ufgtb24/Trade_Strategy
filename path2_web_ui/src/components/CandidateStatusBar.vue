<template>
  <div v-if="ordinalChars.length > 0" class="candidate-banner">
    候选: {{ ordinalChars.join(' ') }} — click 任一 bracket 高亮 / Esc 取消
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { storeToRefs } from 'pinia'
import { useViewStore } from '../stores/view'
import type { MatchDict } from '../types'

const props = defineProps<{ matches: MatchDict[] }>()
const view = useViewStore()
const { candidateMatchIds } = storeToRefs(view)

const ORDINAL_CHARS = ['①', '②', '③', '④', '⑤', '⑥', '⑦', '⑧', '⑨']

const ordinalChars = computed<string[]>(() => {
  if (candidateMatchIds.value.size === 0) return []
  // Sort matches by start_idx to match packBrackets / tooltip ordinal semantics (same as Task 9 fix)
  const sortedByStart = [...props.matches].sort((a, b) => a.start_idx - b.start_idx)
  const out: string[] = []
  for (const id of candidateMatchIds.value) {
    const m = sortedByStart.find((mm) => mm.event_id === id)
    if (!m) continue
    const ord = sortedByStart.indexOf(m) + 1
    if (ord >= 1 && ord <= 9) out.push(ORDINAL_CHARS[ord - 1])
    else if (ord > 9) out.push(String(ord))
  }
  // Sort output ordinals ascending (① ③ ⑤, not arbitrary Set iteration order)
  out.sort((a, b) => {
    const ai = ORDINAL_CHARS.indexOf(a)
    const bi = ORDINAL_CHARS.indexOf(b)
    const av = ai >= 0 ? ai : parseInt(a, 10) - 1
    const bv = bi >= 0 ? bi : parseInt(b, 10) - 1
    return av - bv
  })
  return out
})
</script>

<style scoped>
.candidate-banner {
  height: 16px;
  line-height: 16px;
  padding: 0 8px;
  font-size: 12px;
  color: #fbbf24;
  background: rgba(0, 0, 0, 0.04);
  border-top: 1px solid rgba(0, 0, 0, 0.08);
  border-bottom: 1px solid rgba(251, 191, 36, 0.25);
  user-select: none;
  flex-shrink: 0;
}
</style>
