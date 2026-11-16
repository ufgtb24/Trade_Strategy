<template>
  <!-- 栏和图之间的那条边:开着时拖它改宽度;能收起的栏另有一个小箭头。收起后栏缩成这条窄边,点窄边或箭头打开 -->
  <div class="column-edge" :class="[side, { collapsed, dragging }]" :data-testid="tid"
       :title="collapsed ? openTip : DRAG_TIP"
       @pointerdown="onPointerDown" @pointermove="onPointerMove" @pointerup="onPointerUp"
       @pointercancel="onPointerUp" @click="onStripClick">
    <!-- 不挂 aria-expanded:快捷键守卫(keyGuard.ts)把页面上任何 aria-expanded="true" 当成开着的下拉菜单 -->
    <div v-if="collapsible" class="arrow" role="button" :data-testid="`${tid}-toggle`"
         :data-collapsed="collapsed ? 'true' : 'false'" :title="collapsed ? openTip : closeTip"
         @pointerdown.stop @click.stop="emit('toggle')">{{ glyph }}</div>
  </div>
</template>

<script setup lang="ts">
/**
 * 左栏、右栏靠图一侧的边(components/LeftPanel.vue、components/ChartArea.vue 用)。
 * - 开着:按住拖动改宽度,发 dragstart / drag(相对按下处的横向位移,CSS 像素)/ dragend;宽度怎么夹由用的一方
 *   按 columnLayout.ts 算。拖动用指针捕获,不经过图,所以不会平移图、不会画框、不会熄掉点亮的工具。
 * - collapsible:另有一个小箭头,点它发 toggle;收起后整条窄边都可点,点了发 toggle。收起时不能拖。
 * 箭头和窄边不是可聚焦的按钮:点它们和点空白处一样,焦点回到页面,之后的快捷键照常。
 */
import { computed, ref } from 'vue'

const props = defineProps<{
  side: 'left' | 'right'
  tid: string
  collapsible?: boolean
  collapsed?: boolean
  /** 收起 / 打开的悬停提示(含快捷键) */
  closeTip?: string
  openTip?: string
}>()
const emit = defineEmits<{
  (e: 'toggle'): void
  (e: 'dragstart'): void
  (e: 'drag', dx: number): void
  (e: 'dragend'): void
}>()

const DRAG_TIP = '拖动改宽度'
const dragging = ref(false)
let x0 = 0
let pointerId = -1

// 箭头指向点了以后栏往哪边走:左栏开着 ‹、收着 ›;右栏反过来
const glyph = computed(() => ((props.side === 'left') !== !!props.collapsed ? '‹' : '›'))

function onPointerDown(e: PointerEvent) {
  if (props.collapsed || e.button !== 0) return
  e.preventDefault()
  e.stopPropagation()
  ;(e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId)
  pointerId = e.pointerId
  x0 = e.clientX
  dragging.value = true
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
  emit('dragstart')
}

function onPointerMove(e: PointerEvent) {
  if (!dragging.value || e.pointerId !== pointerId) return
  emit('drag', e.clientX - x0)
}

function onPointerUp(e: PointerEvent) {
  if (!dragging.value || e.pointerId !== pointerId) return
  dragging.value = false
  pointerId = -1
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
  emit('dragend')
}

function onStripClick() {
  if (props.collapsed) emit('toggle')
}
</script>

<style scoped>
/* 窄边是浅灰底(--bar-bg)两侧各一道分隔线,和两边的白底靠分隔线与深浅分开;悬停、拖动时深一档(--line-soft、--line)。
   箭头是程序固定符号,黑色、等宽。灰都取自 App.vue 的 :root 变量(用户确认过的安全色板) */
.column-edge {
  flex: none; position: relative; width: 10px; min-height: 0;
  border-left: 1px solid var(--line); border-right: 1px solid var(--line);
  background: var(--bar-bg); cursor: col-resize; user-select: none; touch-action: none;
}
.column-edge:hover { background: var(--line-soft); }
.column-edge.dragging { background: var(--line); }
.column-edge.collapsed { cursor: pointer; }
.arrow {
  position: absolute; top: 4px; left: 0; right: 0; height: 22px;
  display: flex; align-items: center; justify-content: center;
  font-family: var(--mono); font-size: 13px; line-height: 1; color: var(--ink); cursor: pointer;
}
.arrow:hover { background: var(--line); }
</style>
