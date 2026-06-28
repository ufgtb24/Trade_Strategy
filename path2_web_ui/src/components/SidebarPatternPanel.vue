<template>
  <div class="panel">
    <div class="hdr">
      <span class="title">Patterns</span>
      <div class="actions">
        <button data-action="select-all"  @click="ps.selectAll">全选</button>
        <button data-action="select-none" @click="ps.selectNone">清空</button>
        <button data-action="invert"      @click="ps.invertSelection">反选</button>
      </div>
    </div>
    <div v-if="!ps.loaded" class="hint">加载中…</div>
    <div v-for="p in ps.list" :key="p.pattern_id" class="row">
      <label>
        <input type="checkbox"
               :data-pid="p.pattern_id"
               :checked="ps.selectedIds.has(p.pattern_id)"
               @change="ps.toggleSelected(p.pattern_id)" />
        <span class="name">{{ p.pattern_id }}</span>
      </label>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { usePatternsStore } from '../stores/patterns'
const ps = usePatternsStore()
onMounted(() => { if (!ps.loaded) void ps.loadPatterns() })
</script>

<style scoped>
.panel { padding: 6px 10px; border-bottom: 1px solid #e5e7eb; }
.hdr { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.title { font-weight: 600; }
.actions button { font-size: 11px; margin-left: 4px; padding: 1px 6px;
                  border: 1px solid #cbd5e1; background: #fff; cursor: pointer; }
.row { padding: 2px 0; }
.row label { display: flex; align-items: center; gap: 6px; cursor: pointer; font-size: 12px; }
.name { font-weight: 500; }
.pid { color: #94a3b8; font-size: 10px; }
.hint { font-size: 12px; color: #64748b; }
</style>
