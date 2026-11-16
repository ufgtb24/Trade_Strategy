<template>
  <div class="app">
    <TopBar class="top" />
    <LeftPanel class="left" />
    <main class="right"><ChartArea /></main>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onBeforeUnmount } from 'vue'
import LeftPanel from './LeftPanel.vue'
import ChartArea from './ChartArea.vue'
import TopBar from './TopBar.vue'
import { useConfigStore } from '../stores/config'
import { useViewStore } from '../stores/view'
import { useAnnotationStore } from '../stores/annotation'
import { useDirectLinkStore } from '../stores/directLinks'
import { useAppLinkStore } from '../stores/appLink'
import { useFeedbackStore } from '../stores/feedback'
import { usePanelsStore } from '../stores/panels'
import { focusBlocksKeys } from './keyGuard'

// 启动即加载 config,使 loadScanFile 能读到持久化的 last_selected_pattern
onMounted(() => { void useConfigStore().load() })
// 标注:启动即读一遍(全部批次重放出的状态);之后每次保存都换上后端回来的结果
onMounted(() => { void useAnnotationStore().load() })
// 当前 pattern 的 app(mapping 文件):启动即读一遍,之后窗口重新拿到焦点再读(stores/appLink.ts)
onMounted(() => { void useAppLinkStore().load() })
// 反馈的状态(stores/feedback.ts):store 一建起来就接好重取的时机(进 compare、换 pattern、存删反馈后、app 重跑、
// 窗口重新拿到焦点),不等图上或侧栏第一次用到它
useFeedbackStore()
// 直达链接(格式见 annotate/directLinks.ts):页面带着链接打开时跟一次,地址的 # 部分变了再跟
const _links = useDirectLinkStore()
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

// 左右栏的收起快捷键(状态在 stores/panels.ts,箭头在 ColumnEdge.vue):Shift+L 左栏(四档)、
// Shift+R 标注侧栏(只在 annotate、compare;app、scan 的诊断侧栏照旧用 Sidebar 按钮)。左右各管各。
// 焦点在任何输入框、下拉框里不响应(keyGuard.ts,同找图清单的翻页键):在 note 里打大写 L、R 是在写字。
// 单个字母会被 scan 档扫描列表的「敲字母搜股票」接走,所以带 Shift(同 Shift+B)
const _panels = usePanelsStore()
function _columnKey(e: KeyboardEvent) {
  if (!e.shiftKey || e.ctrlKey || e.metaKey || e.altKey || e.isComposing || e.repeat) return
  if (e.code !== 'KeyL' && e.code !== 'KeyR') return
  if (e.code === 'KeyR' && !_view.annotating) return
  if (focusBlocksKeys()) return
  e.preventDefault()
  if (e.code === 'KeyL') _panels.leftCollapsed = !_panels.leftCollapsed
  else _panels.annCollapsed = !_panels.annCollapsed
}
onMounted(() => window.addEventListener('keydown', _columnKey))
onBeforeUnmount(() => window.removeEventListener('keydown', _columnKey))
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
/* 左栏的宽度由它自己定(抽屉露出多少 + 靠图一侧的那条边,见 LeftPanel.vue),图区占其余 */
.app { display: grid; grid-template-columns: auto minmax(0, 1fr); grid-template-rows: auto 1fr; height: 100vh; }
.app > .top { grid-column: 1 / -1; }
.left { grid-column: 1; grid-row: 2; min-height: 0; }
.right { grid-column: 2; grid-row: 2; display: flex; flex-direction: column; min-height: 0; min-width: 0; overflow: auto; }
</style>
