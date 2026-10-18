<template>
  <div v-if="banner" :class="['mode-banner', `mode-banner--${banner.kind}`]" :title="banner.text"
       :role="banner.kind === 'debug' ? 'status' : 'alert'" data-testid="mode-banner" :data-kind="banner.kind">
    {{ banner.text }}
  </div>
</template>

<script setup lang="ts">
// 页顶横幅(内容见 stores/mode.ts):看图工作流的调试模式(后端带 CHART_WORKFLOW_MODE=debug 启动,见
// chart_workflow/mode.py)、模式未知(后端没连上)、前后端模式对不上。标签页标题加对应前缀。
// 三种横幅靠文字和明暗区分,不靠色相:调试是深底白字斜纹,模式未知是白底黑字粗虚线框,对不上是纯黑底白字白虚线框。
// 横幅高度写进根元素的 --mode-banner-h,两个视图的整页高度减掉它;不挂横幅时为 0。
import { computed, onMounted, onUnmounted, watch } from 'vue'
import { useModeStore, type BannerKind } from '../stores/mode'

const BANNER_H = '30px'
const PREFIX: Record<BannerKind, string> = { debug: '【调试模式】', unknown: '【模式未知】', mismatch: '【模式对不上】' }
const store = useModeStore()
const banner = computed(() => store.banner)
const baseTitle = document.title.replace(/^【(调试模式|模式未知|模式对不上)】/, '')
watch(banner, (b) => {
  document.documentElement.style.setProperty('--mode-banner-h', b ? BANNER_H : '0px')
  document.title = b ? `${PREFIX[b.kind]}${baseTitle}` : baseTitle
}, { immediate: true })
onMounted(() => store.start())
onUnmounted(() => store.stop())
</script>

<style scoped>
.mode-banner { height: var(--mode-banner-h, 30px); box-sizing: border-box; display: flex; align-items: center;
               justify-content: center; padding: 0 12px; font-size: 15px; font-weight: 800; letter-spacing: 2px;
               overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
.mode-banner--debug { color: #fff; background: repeating-linear-gradient(-45deg, #0f172a 0 14px, #334155 14px 28px);
                      text-shadow: 0 0 3px #000; border-bottom: 2px solid #000; }
.mode-banner--unknown { color: #000; background: #fff; border: 3px dashed #000; }
.mode-banner--mismatch { color: #fff; background: #000; border: 3px dashed #fff; }
</style>
