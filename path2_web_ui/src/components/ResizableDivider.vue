<template>
  <div
    class="resizable-divider"
    :class="{ dragging }"
    role="separator"
    aria-orientation="horizontal"
    @pointerdown="onPointerDown"
    @dblclick="onDblclick"
  />
</template>

<script setup lang="ts">
import { ref, onBeforeUnmount } from 'vue'

const emit = defineEmits<{
  (e: 'drag', dy: number): void
  (e: 'dragend'): void
  (e: 'dblclick'): void
}>()

const dragging = ref(false)
let startY = 0
let activePointerId = -1

function onDblclick() {
  emit('dblclick')
}

function onPointerDown(e: PointerEvent) {
  if (e.button !== 0) return
  dragging.value = true
  startY = e.clientY
  activePointerId = e.pointerId
  document.body.style.cursor = 'row-resize'
  document.body.style.userSelect = 'none'
  window.addEventListener('pointermove', onPointerMove)
  window.addEventListener('pointerup', onPointerUp)
  window.addEventListener('pointercancel', onPointerUp)
}

function onPointerMove(e: PointerEvent) {
  if (!dragging.value || e.pointerId !== activePointerId) return
  emit('drag', e.clientY - startY)
}

function onPointerUp(e: PointerEvent) {
  if (e.pointerId !== activePointerId) return
  dragging.value = false
  activePointerId = -1
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
  window.removeEventListener('pointermove', onPointerMove)
  window.removeEventListener('pointerup', onPointerUp)
  window.removeEventListener('pointercancel', onPointerUp)
  emit('dragend')
}

onBeforeUnmount(() => {
  window.removeEventListener('pointermove', onPointerMove)
  window.removeEventListener('pointerup', onPointerUp)
  window.removeEventListener('pointercancel', onPointerUp)
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
})
</script>

<style scoped>
/* 主/副图分割线,同时兼视觉分区 divider #1 与拖拽 handle。
   4px 静息 / 6px hover;#e0e6f1 静息 / #cbd5e1 hover;row-resize 光标提示可拖。 */
.resizable-divider {
  flex: 0 0 4px;
  height: 4px;
  background: #e0e6f1;
  cursor: row-resize;
  user-select: none;
  transition: background 0.12s ease, flex-basis 0.12s ease;
}
.resizable-divider:hover,
.resizable-divider.dragging {
  flex-basis: 6px;
  height: 6px;
  background: #94a3b8;
}
</style>
