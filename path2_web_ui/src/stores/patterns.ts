import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { SerializedPattern } from '../types'
import { getPatterns } from '../api'

export const usePatternsStore = defineStore('patterns', () => {
  const list = ref<SerializedPattern[]>([])
  const selectedId = ref<string | null>(null)
  async function load() {
    list.value = await getPatterns()
    if (!selectedId.value && list.value.length) selectedId.value = list.value[0].pattern_id
  }
  function select(id: string) { selectedId.value = id }
  return { list, selectedId, load, select }
})
