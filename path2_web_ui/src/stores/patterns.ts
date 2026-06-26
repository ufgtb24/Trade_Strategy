import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { SerializedPattern } from '../types'
import { getPatterns } from '../api'

export const usePatternsStore = defineStore('patterns', () => {
  const list = ref<SerializedPattern[]>([])
  const selectedIds = ref<Set<string>>(new Set())
  const loaded = ref(false)

  async function loadPatterns() {
    list.value = await getPatterns()
    loaded.value = true
  }

  function toggleSelected(id: string) {
    const s = new Set(selectedIds.value)
    if (s.has(id)) s.delete(id); else s.add(id)
    selectedIds.value = s
  }
  function selectAll() {
    selectedIds.value = new Set(list.value.map(p => p.pattern_id))
  }
  function selectNone() {
    selectedIds.value = new Set()
  }
  function invertSelection() {
    const s = new Set<string>()
    for (const p of list.value) if (!selectedIds.value.has(p.pattern_id)) s.add(p.pattern_id)
    selectedIds.value = s
  }

  const selectedArray = computed(() => Array.from(selectedIds.value))

  return { list, loaded, selectedIds, selectedArray,
           loadPatterns, toggleSelected, selectAll, selectNone, invertSelection }
})
