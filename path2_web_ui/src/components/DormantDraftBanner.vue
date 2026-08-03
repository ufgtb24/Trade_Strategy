<!-- Task 13 · 休眠草稿恢复 banner:localStorage 有未生效的 Working Copy 草稿(上次会话遗留、刷新后不自动激活)时
     顶部黄条提示,per-pid 可「恢复」(激活探索态,锚 WC dict)或「丢弃」(清 slot + localStorage)。
     spec = docs/research/2026-07-20_params-profiles-dev-modes -->
<template>
  <div v-if="dormantDrafts.length" class="dormant-banner" data-testid="dormant-banner">
    上次会话遗留 {{ dormantDrafts.length }} 份未扫描的工作副本草稿(休眠,未生效,可在抽屉 Save As 存盘):
    <span v-for="d in dormantDrafts" :key="d.pid" class="draft">
      {{ d.pid }}
      <button :data-testid="`dormant-restore-${d.pid}`" @click="view.restoreDormant(d.pid)">恢复</button>
      <button @click="view.discardWorkingCopy(d.pid)">丢弃</button>
    </span>
  </div>
</template>

<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { useViewStore } from '../stores/view'
const view = useViewStore()
const { dormantDrafts } = storeToRefs(view)
</script>

<style scoped>
.dormant-banner { background: #fffbeb; border: 1px solid #fde047; padding: 6px 10px;
                  font-size: 12px; color: #854d0e; display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.draft { display: inline-flex; gap: 4px; align-items: center; font-weight: 600; }
.draft button { font-size: 11px; }
</style>
