<template>
  <div class="panel">
    <div class="hdr">
      <span class="title">Patterns</span>
    </div>
    <div v-if="!scanFile" class="hint">未加载扫描结果</div>
    <div v-for="pid in patternIds" :key="pid" class="row">
      <label>
        <input type="checkbox"
               :data-pid="pid"
               :checked="visiblePatterns.has(pid)"
               @change="view.togglePattern(pid)" />
        <span class="name">{{ pid }}</span>
      </label>
    </div>
  </div>
</template>

<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { useViewStore } from '../stores/view'
const view = useViewStore()
const { scanFile, patternIds, visiblePatterns } = storeToRefs(view)
</script>

<style scoped>
.panel { padding: 6px 10px; border-bottom: 1px solid #e5e7eb; }
.hdr { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.title { font-weight: 600; }
.row { padding: 2px 0; }
.row label { display: flex; align-items: center; gap: 6px; cursor: pointer; font-size: 12px; }
.name { font-weight: 500; }
.hint { font-size: 12px; color: #64748b; }
</style>
