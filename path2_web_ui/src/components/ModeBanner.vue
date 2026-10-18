<template>
  <div v-if="label" class="mode-banner" role="status" data-testid="mode-banner">{{ label }}</div>
</template>

<script setup lang="ts">
// 看图工作流的调试模式(后端带 CHART_WORKFLOW_MODE=debug 启动,见 chart_workflow/mode.py):页顶挂一条横幅,
// 标签页标题加「【调试模式】」前缀。横幅靠文字和明暗(深底白字、斜纹)区分,不靠色相。
// 横幅高度写进根元素的 --mode-banner-h,两个视图的整页高度减掉它;正式模式为 0。
import { computed, onMounted, watch } from 'vue'
import { useModeStore } from '../stores/mode'

const BANNER_H = '30px'
const store = useModeStore()
const label = computed(() => store.info?.label ?? null)
const baseTitle = document.title.replace(/^【调试模式】/, '')
watch(label, (l) => {
  document.documentElement.style.setProperty('--mode-banner-h', l ? BANNER_H : '0px')
  document.title = l ? `【调试模式】${baseTitle}` : baseTitle
}, { immediate: true })
onMounted(() => { if (!store.info) void store.load() })
</script>

<style scoped>
.mode-banner { height: var(--mode-banner-h, 30px); line-height: var(--mode-banner-h, 30px); padding: 0 12px;
               text-align: center; font-size: 15px; font-weight: 800; letter-spacing: 2px; color: #fff;
               background: repeating-linear-gradient(-45deg, #0f172a 0 14px, #334155 14px 28px);
               text-shadow: 0 0 3px #000; border-bottom: 2px solid #000; overflow: hidden; white-space: nowrap; }
</style>
