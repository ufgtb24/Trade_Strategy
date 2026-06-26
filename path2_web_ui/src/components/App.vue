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
import SidebarPatternPanel from './SidebarPatternPanel.vue'
import SidebarScanPanel from './SidebarScanPanel.vue'
import SidebarResultList from './SidebarResultList.vue'
import ChartArea from './ChartArea.vue'
</script>

<style>
* { box-sizing: border-box; }
body { margin: 0; font-family: system-ui, sans-serif; color: #0f172a; }
.app { display: grid; grid-template-columns: 300px 1fr; height: 100vh; }
.left { border-right: 1px solid #e5e7eb; display: flex; flex-direction: column; overflow: hidden; }
.right { overflow: auto; }
</style>
