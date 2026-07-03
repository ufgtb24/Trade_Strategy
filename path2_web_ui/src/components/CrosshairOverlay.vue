<template>
  <div v-if="x != null" class="crosshair-overlay" :style="{ left: x + 'px' }" />
</template>

<script setup lang="ts">
defineProps<{ x: number | null }>()
</script>

<style scoped>
/* 视觉:一根到底 dashed 竖线,覆盖 .kline-wrap-v2 全高 —— main-chart + ResizableDivider handle + sub-outer。
   x 由 KlineChart.vue manual sync 逻辑写入:chartMain snap 后 axisValue 经 convertToPixel
   + mainCanvasOffsetX 得到相对 .kline-wrap-v2 的 pixel(x=0 表 wrap 最左)。
   z-index=5 压过 divider handle(handle z 一般 ≤ 2);pointer-events:none 不阻挡鼠标事件。 */
.crosshair-overlay {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 0;
  border-left: 1.5px dashed rgba(0, 136, 204, 0.7);
  pointer-events: none;
  z-index: 5;
}
</style>
