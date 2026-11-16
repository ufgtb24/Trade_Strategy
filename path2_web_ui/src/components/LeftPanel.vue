<template>
  <aside class="left-panel" data-testid="left-panel">
    <!-- 抽屉:drawer 按内容排成自己的宽度(最少 220px、最多半屏),clip 只决定露出多少、把靠图一侧遮掉,
         内容不重排、不出横向滚动条。收起时 clip 藏起来(只藏不拆:页签、滚动位置、列表位置都留着) -->
    <div v-show="!panels.leftCollapsed" ref="clipEl" class="clip" data-testid="left-clip" :style="clipStyle">
      <div ref="drawerEl" class="drawer" data-testid="left-drawer" :style="{ minWidth: `${LEFT_FLOOR}px` }">
        <!-- 前三档:找图清单;scan 档:扫描面板与扫描结果列表。两份切档时只藏不拆,滚动位置与列表位置都留着 -->
        <FinderList v-show="!scanView" />
        <div v-show="scanView" class="scan-side" data-testid="scan-side">
          <SidebarPatternPanel />
          <SidebarScanPanel />
          <SidebarResultList />
        </div>
      </div>
    </div>
    <ColumnEdge side="left" tid="left-edge" collapsible :collapsed="panels.leftCollapsed"
                close-tip="收起左栏(Shift+L)" open-tip="打开左栏(Shift+L)"
                @toggle="panels.leftCollapsed = !panels.leftCollapsed"
                @dragstart="onDragStart" @drag="onDrag" />
  </aside>
</template>

<script setup lang="ts">
/**
 * 主视图的左栏,随顶栏 mode 换内容:
 * - annotate / compare / app:找图清单(FinderList),只列用户自己存下的东西和这次 random 抽到的图,
 *   不出现 app 的任何结果(扫描的命中、收益都不在这里);
 * - scan:扫描的 Patterns 面板、扫描面板(扫描 ⚙、打开历史)和扫描结果列表,按法不变。
 *
 * 收起与拖宽(几何见 columnLayout.ts,状态在 stores/panels.ts,四档、三页共用一份):
 * - 靠图一侧的边(ColumnEdge)上有小箭头,点它或按 Shift+L(App.vue)收起;收起后左栏只剩那条窄边。
 *   收着时 PageUp / PageDown 照样换图(清单还挂着,只是看不见)。
 * - 拖那条边改露出多少,像抽屉:没拖过时全开;拖出的宽度超过当前内容的全宽时按全宽露出,
 *   换到内容更宽的页或档就恢复拖出的宽度。
 */
import { computed, ref } from 'vue'
import { storeToRefs } from 'pinia'
import FinderList from './FinderList.vue'
import SidebarPatternPanel from './SidebarPatternPanel.vue'
import SidebarScanPanel from './SidebarScanPanel.vue'
import SidebarResultList from './SidebarResultList.vue'
import ColumnEdge from './ColumnEdge.vue'
import { useViewStore } from '../stores/view'
import { usePanelsStore } from '../stores/panels'
import { LEFT_FLOOR, leftDragged } from './columnLayout'

const { scanView } = storeToRefs(useViewStore())
const panels = usePanelsStore()

const clipEl = ref<HTMLElement | null>(null)
const drawerEl = ref<HTMLElement | null>(null)

// 露出宽度 = min(拖出的宽度, 内容全宽):clip 的宽度取内容的 max-content,再用 max-width 截到拖出的宽度
const clipStyle = computed(() => (panels.leftWidth === null ? undefined : { maxWidth: `${panels.leftWidth}px` }))

let startW = 0
let full = 0
function onDragStart() {
  startW = clipEl.value?.getBoundingClientRect().width ?? 0
  full = drawerEl.value?.getBoundingClientRect().width ?? 0
}
function onDrag(dx: number) {
  panels.leftWidth = leftDragged(startW + dx, full)
}
</script>

<style scoped>
.left-panel { display: flex; min-height: 0; }
/* overflow: clip 而不是 hidden:hidden 的盒子仍能被程序滚动(聚焦搜索框、把一行滚进视野时浏览器会横向滚它),
   抽屉里的内容就整体左移、代码列被遮;clip 不让任何滚动 */
.clip { flex: none; width: max-content; min-height: 0; overflow: clip; }
.drawer {
  display: flex; flex-direction: column; height: 100%;
  width: max-content; max-width: 50vw;   /* 最少 LEFT_FLOOR(style 里给) */
}
.scan-side { display: flex; flex-direction: column; flex: 1; min-height: 0; overflow: hidden; }
</style>
