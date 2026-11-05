<template>
  <div class="chart-area" :class="{ 'no-sidebar': !annotating && !showSidebar, annotating }">
    <!-- row0: 全局 level 控件 + 三 panel toggle chip + 休眠草稿 banner。
         .header-row 包一层让 banner 挂在 chip 行下方,同时对 grid 只占单一自动行——
         不新增显式行号,不改动 topology-row/kline/sidebar 既有的 auto-placement,避免二者同时出现时抢行。 -->
    <!-- annotate、compare 不显示 app 相关的控件(档位、pattern、参数、拓扑、诊断侧栏);compare 的 app 输出档位一直到 detected -->
    <div v-if="!annotating" class="header-row">
      <div class="level-bar" data-testid="level-control">
        <button
          v-for="opt in LEVEL_OPTIONS"
          :key="opt.value"
          :class="['level-btn', { active: level === opt.value }]"
          :title="opt.title"
          @click="view.setLevel(opt.value)"
        >{{ opt.label }}</button>
        <!-- 现算的 app(顶栏切过来的,app 名写在顶栏):扫描的 pattern 选择与参数副本不适用 -->
        <template v-if="!linkedView">
          <select :value="view.activePatternId ?? ''"
                  data-role="active-pattern"
                  @change="onActivePatternChange"
                  class="active-pattern-select"
                  v-if="view.patternIds.length > 0">
            <option v-for="pid in view.patternIds" :key="pid" :value="pid">
              {{ pid }}
            </option>
          </select>
          <ParamsChip :drawer-open="drawerOpen" @toggle-drawer="drawerOpen = !drawerOpen" />
        </template>
        <span class="spacer" />
        <button
          v-for="t in PANEL_TOGGLES"
          :key="t.key"
          :class="['level-btn', 'panel-toggle', { active: panels[t.refKey] }]"
          :data-testid="`panel-toggle-${t.key}`"
          :title="t.title"
          @click="panels.toggle(t.key)"
        >{{ t.label }}</button>
      </div>
      <DormantDraftBanner />
    </div>
    <!-- annotate:标注的提示条(指纹不符、冲突、保存被拒),占 row1 -->
    <AnnotationNotices v-if="annotating" class="notices-row" />
    <!-- row1: 拓扑控制(可隐藏,wrapper .topology-row 让 CSS 精准跨列) -->
    <div v-if="!annotating && showTopology" class="topology-row">
      <TopologyControl @hover-node="onHoverNode" />
    </div>
    <!-- row2: K线 + 诊断侧栏(侧栏可隐藏) -->
    <KlineChart />
    <AnnotationSidebar v-if="annotating" class="sidebar" />
    <DetailSidebar v-else-if="showSidebar" />
    <WorkingCopyDrawer :open="drawerOpen" @close="drawerOpen = false" />
    <!-- Task 12 · 全局一次性提示(如 scan 完成自动固化 WC) -->
    <div v-if="view.toastMsg" class="toast">{{ view.toastMsg }}</div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { storeToRefs } from 'pinia'
import TopologyControl from './TopologyControl.vue'
import KlineChart from './KlineChart.vue'
import DetailSidebar from './DetailSidebar.vue'
import ParamsChip from './ParamsChip.vue'
import WorkingCopyDrawer from './WorkingCopyDrawer.vue'
import DormantDraftBanner from './DormantDraftBanner.vue'
import AnnotationSidebar from './AnnotationSidebar.vue'
import AnnotationNotices from './AnnotationNotices.vue'
import { useViewStore } from '../stores/view'
import { usePanelsStore, type PanelKey } from '../stores/panels'
import { useAnnotationStore } from '../stores/annotation'
import type { Level } from '../types'

const view = useViewStore()
const { level, annotating, linkedView } = storeToRefs(view)
const panels = usePanelsStore()
const { showTopology, showSidebar } = storeToRefs(panels)
// 抽屉开关 ref 由 ChartArea 持有,ParamsChip 只 emit toggle-drawer;WorkingCopyDrawer(Task 11)在此渲染
const drawerOpen = ref(false)

// Shift+P 切换参数抽屉(与 ParamsChip 的 ✎ 按钮同一 toggle)。
// window bubble 阶段;capture 阶段 onGlobalCharKey 已对 shift 整体让出不抢序。
// 焦点在可编辑元素时放行 → 浏览器默认输入大写 P,不误关抽屉(防误触优先)。
function onKey(e: KeyboardEvent) {
  if (!(e.key === 'P' && e.shiftKey && !e.ctrlKey && !e.metaKey && !e.altKey)) return
  const ae = document.activeElement as HTMLElement | null
  if (ae && ae.closest('input, textarea, select, [contenteditable=""], [contenteditable="true"]')) return
  e.preventDefault()
  drawerOpen.value = !drawerOpen.value
}
onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))

// Delete 删掉选中的框(与 selection 页的 delete 按钮同一动作:成员关系与挂在它上面的 attach 一并拿掉)。
// 只认 Delete、不认 Backspace(后者在别处常用,误触代价是删掉用户的标注);
// 焦点在可编辑元素时放行,写特征名、属性、定义时按 Delete 只删字。
const ann = useAnnotationStore()
function onDeleteKey(e: KeyboardEvent) {
  if (e.key !== 'Delete' || e.ctrlKey || e.metaKey || e.altKey || e.shiftKey) return
  const id = ann.selectedBoxId
  if (!annotating.value || !id) return
  const ae = document.activeElement as HTMLElement | null
  if (ae && ae.closest('input, textarea, select, [contenteditable=""], [contenteditable="true"]')) return
  e.preventDefault()
  ann.deleteBox(id)
}
onMounted(() => window.addEventListener('keydown', onDeleteKey))
onBeforeUnmount(() => window.removeEventListener('keydown', onDeleteKey))

const LEVEL_OPTIONS: { value: Level; label: string; title: string }[] = [
  { value: 'in_hit', label: 'in_hit', title: '仅显示进了某一次 hit 的事件' },
  { value: 'qualified', label: 'qualified', title: '显示进了 hit 或参与诊断 trace 的事件' },
  { value: 'detected', label: 'detected', title: '显示所有被 detector 检出的事件' },
]

const PANEL_TOGGLES: { key: PanelKey; refKey: 'showTopology' | 'showSidebar' | 'showSlider'; label: string; title: string }[] = [
  { key: 'topology', refKey: 'showTopology', label: 'Topology', title: '显示/隐藏拓扑面板' },
  { key: 'sidebar',  refKey: 'showSidebar',  label: 'Sidebar',  title: '显示/隐藏右侧诊断侧栏' },
  { key: 'slider',   refKey: 'showSlider',   label: 'Slider',   title: '显示/隐藏 K 线下方缩放滑块' },
]

function onHoverNode(_nodeId: string | null) { /* 高亮交互留 KlineChart 内部增强 */ }

function onActivePatternChange(e: Event) {
  view.setActivePattern((e.target as HTMLSelectElement).value)
}
</script>

<style scoped>
/* grid 列数由 .no-sidebar 切换;row1 用 .topology-row 精准跨列(避开脆弱 nth-child) */
.chart-area {
  display: grid;
  grid-template-columns: 1fr 280px;
  grid-template-rows: auto auto 1fr;
  gap: 0;
  flex: 1;
  min-height: 0;
  min-width: 0;
}
.chart-area.no-sidebar { grid-template-columns: 1fr; }
.chart-area.annotating { grid-template-columns: 1fr 320px; }
.header-row, .level-bar, .chart-area > .topology-row, .chart-area > .notices-row { grid-column: 1 / -1; }
.chart-area > .notices-row { grid-row: 2; }
.chart-area > .kline-wrap-v2, .chart-area > .sidebar { grid-row: 3; }

.level-bar {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 4px 8px;
  background: #1a1a2e;
  border-bottom: 1px solid #2a2a4a;
}
.spacer { flex: 1; }

.level-btn {
  padding: 3px 14px;
  border: 1px solid #3a3a5a;
  border-radius: 4px;
  background: transparent;
  color: #aaa;
  font-size: 12px;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}
.level-btn:not(.panel-toggle) { font-family: var(--mono); }   /* 三档的固定文字是档位值本身 */
.level-btn:hover { background: #2a2a4a; color: #ddd; }
.level-btn.active { background: #4a4aaa; color: #fff; border-color: #6a6acc; }

.active-pattern-select { margin-left: 8px; font-size: 12px; padding: 2px 4px; }

/* Task 12 · 全局 toast:fixed 底部居中,浮在所有面板/弹窗之上 */
.toast {
  position: fixed; left: 50%; bottom: 32px; transform: translateX(-50%);
  background: rgba(30, 41, 59, 0.92); color: #fff; padding: 8px 18px;
  border-radius: 6px; font-size: 12px; box-shadow: 0 4px 14px rgba(0,0,0,0.25);
  z-index: 1200; pointer-events: none;
}
</style>
