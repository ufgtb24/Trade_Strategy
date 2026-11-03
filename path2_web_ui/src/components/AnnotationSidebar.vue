<template>
  <aside class="annotation-sidebar" data-testid="annotation-sidebar">
    <nav class="tabs" role="tablist">
      <button v-for="t in TABS" :key="t" type="button" role="tab"
              :class="['tab', { on: ann.tab === t }]"
              :aria-selected="ann.tab === t"
              :data-testid="`annotation-tab-${t}`"
              @click="ann.tab = t">{{ t }}</button>
    </nav>
    <section class="body" :data-testid="`annotation-page-${ann.tab}`">
      <BoxPanel v-if="ann.tab === 'selection' && ann.selectedBox" />
      <SamplePanel v-else-if="ann.tab === 'selection' && ann.selectedSample" />
      <FeaturesPanel v-else-if="ann.tab === 'features' && ann.state" />
      <PatternPanel v-else-if="ann.tab === 'pattern' && ann.state" />
      <span v-else class="empty">empty</span>
    </section>
  </aside>
</template>

<script setup lang="ts">
/**
 * annotate 模式的右侧栏,三页:selection(选中的框或样本)、features(词表)、pattern(当前 pattern 总览;
 * 当前 pattern 是 unsorted 时是 unsorted 页)。
 * 页签由标注 store 管:在图上选中框或样本时自动翻到 selection。
 */
import { useAnnotationStore } from '../stores/annotation'
import BoxPanel from './BoxPanel.vue'
import FeaturesPanel from './FeaturesPanel.vue'
import PatternPanel from './PatternPanel.vue'
import SamplePanel from './SamplePanel.vue'

const TABS = ['selection', 'features', 'pattern'] as const
const ann = useAnnotationStore()
</script>

<style scoped>
/* 字体与色值见 App.vue 的 :root 变量 */
.annotation-sidebar {
  display: flex; flex-direction: column; min-height: 0; overflow: auto;
  border-left: 1px solid var(--line); background: #fff; color: var(--ink);
}
.tabs {
  position: sticky; top: 0; z-index: 1; display: flex; gap: 12px; padding: 6px 8px 0;
  background: #fff; border-bottom: 1px solid var(--line-soft);
}
.tab, .empty { font-family: var(--mono); font-size: 12px; }
/* 文字一律黑;没选上的页签按「没选上的状态」用灰字,选中的加黑色下划线 */
.tab {
  padding: 2px 2px 4px; border: none; border-bottom: 2px solid transparent;
  background: none; color: var(--ink-off); cursor: pointer;
}
.tab.on { color: var(--ink); border-bottom-color: var(--ink); }
.body { padding: 8px; }
.empty { color: var(--ink-empty); }
</style>
