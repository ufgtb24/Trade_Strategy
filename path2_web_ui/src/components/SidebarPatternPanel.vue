<template>
  <div class="panel">
    <label>Pattern</label>
    <select :value="selectedId ?? ''" @change="onSelect">
      <option v-for="p in list" :key="p.pattern_id" :value="p.pattern_id">{{ p.display_name }}</option>
    </select>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { usePatternsStore } from '../stores/patterns'
const patterns = usePatternsStore()
const { list, selectedId } = storeToRefs(patterns)
onMounted(() => patterns.load())
function onSelect(e: Event) { patterns.select((e.target as HTMLSelectElement).value) }
</script>

<style scoped>
.panel { padding: 10px; } label { font-size: 11px; color: #64748b; display: block; }
select { width: 100%; padding: 4px; }
</style>
