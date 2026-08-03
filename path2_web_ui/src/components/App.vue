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
import { onMounted, onBeforeUnmount } from 'vue'
import SidebarPatternPanel from './SidebarPatternPanel.vue'
import SidebarScanPanel from './SidebarScanPanel.vue'
import SidebarResultList from './SidebarResultList.vue'
import ChartArea from './ChartArea.vue'
import { useConfigStore } from '../stores/config'
import { useViewStore } from '../stores/view'

// 启动即加载 config,使 loadScanFile 能读到持久化的 last_selected_pattern
onMounted(() => { void useConfigStore().load() })

// Task 13 · beforeunload 双保险:探索态有未落盘/未固化的脏 WC 时提示确认。
// localStorage 已实时兜底(updateWorkingCopy 每次编辑都落盘),此提示只是防用户误刷新丢当前编辑焦点的 belt-and-suspenders。
const _view = useViewStore()
function _guard(e: BeforeUnloadEvent) {
  const anyDirty = Object.keys(_view.workingCopy).some(pid => _view.wcDirty(pid))
  if (anyDirty) { e.preventDefault(); e.returnValue = '' }
}
onMounted(() => window.addEventListener('beforeunload', _guard))
onBeforeUnmount(() => window.removeEventListener('beforeunload', _guard))
</script>

<style>
* { box-sizing: border-box; }
body { margin: 0; font-family: system-ui, sans-serif; color: #0f172a; }
.app { display: grid; grid-template-columns: minmax(220px, max-content) 1fr; height: 100vh; }
.left { border-right: 1px solid #e5e7eb; display: flex; flex-direction: column; overflow: hidden; max-width: 50vw; }
.right { display: flex; flex-direction: column; min-height: 0; overflow: auto; }
</style>
