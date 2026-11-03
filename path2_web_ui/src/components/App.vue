<template>
  <div class="app">
    <TopBar class="top" />
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
import TopBar from './TopBar.vue'
import { useConfigStore } from '../stores/config'
import { useViewStore } from '../stores/view'
import { useAnnotationStore } from '../stores/annotation'
import { useLinkStore } from '../stores/links'

// 启动即加载 config,使 loadScanFile 能读到持久化的 last_selected_pattern
onMounted(() => { void useConfigStore().load() })
// 标注:启动即读一遍(全部批次重放出的状态);之后每次保存都换上后端回来的结果
onMounted(() => { void useAnnotationStore().load() })
// 直达链接(格式见 annotate/links.ts):页面带着链接打开时跟一次,地址的 # 部分变了再跟
const _links = useLinkStore()
const _follow = () => { void _links.follow(location.hash) }
onMounted(() => { _follow(); window.addEventListener('hashchange', _follow) })
onBeforeUnmount(() => window.removeEventListener('hashchange', _follow))

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
/* 标注界面的共用字体与中性色(灰都取自用户确认过的安全色板):
   --mono       程序固定文字(字段名、状态、页签)的等宽字体
   --ink        文字一律黑
   --ink-off    没选上的状态(如未选中的页签)
   --ink-empty  空着的状态(如空页、占位)
   --line       面板分隔线;--line-strong 输入框边;--line-soft 页签栏下沿;--bar-bg 顶栏底色
   --chip-bg    不在输入框里的业务内容(如清单里的股票代码)的浅灰底 */
:root {
  --mono: ui-monospace, "JetBrains Mono", "DejaVu Sans Mono", Consolas, monospace;
  --ink: #111;
  --ink-off: #888888;
  --ink-empty: #9ca3af;
  --line: #d1d5db;
  --line-strong: #9ca3af;
  --line-soft: #e4e4e7;
  --bar-bg: #fafafa;
  --chip-bg: #f4f4f5;
}
* { box-sizing: border-box; }
body { margin: 0; font-family: system-ui, sans-serif; color: #0f172a; }
.app { display: grid; grid-template-columns: minmax(220px, max-content) 1fr; grid-template-rows: auto 1fr; height: 100vh; }
.app > .top { grid-column: 1 / -1; }
.left { border-right: 1px solid #e5e7eb; display: flex; flex-direction: column; overflow: hidden; max-width: 50vw; min-height: 0; }
.right { display: flex; flex-direction: column; min-height: 0; min-width: 0; overflow: auto; }
</style>
