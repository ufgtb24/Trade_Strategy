<template>
  <div class="app">
    <aside class="left">
      <SidebarPatternPanel />
      <SidebarScanPanel />
      <SidebarResultList />
    </aside>
    <main class="right"><ChartArea /></main>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import SidebarPatternPanel from './SidebarPatternPanel.vue'
import SidebarScanPanel from './SidebarScanPanel.vue'
import SidebarResultList from './SidebarResultList.vue'
import ChartArea from './ChartArea.vue'
import { useConfigStore } from '../stores/config'

// 启动即加载 config,使 loadScanFile 能读到持久化的 last_selected_pattern
onMounted(() => { void useConfigStore().load() })
</script>

<style>
* { box-sizing: border-box; }
body { margin: 0; font-family: system-ui, sans-serif; color: #0f172a; }
.app { display: grid; grid-template-columns: minmax(220px, max-content) 1fr; height: 100vh; }
.left { border-right: 1px solid #e5e7eb; display: flex; flex-direction: column; overflow: hidden; max-width: 50vw; }
.right { display: flex; flex-direction: column; min-height: 0; overflow: auto; }
</style>
