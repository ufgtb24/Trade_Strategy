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
      <FocusedSamplePanel v-else-if="ann.tab === 'selection' && cmp.focusedSample" />
      <FeaturesPanel v-else-if="ann.tab === 'features' && ann.state" />
      <PatternPanel v-else-if="ann.tab === 'pattern' && ann.state" />
      <FeedbackPage v-else-if="ann.tab === 'feedback' && view.comparing" />
      <span v-else class="empty">empty</span>
    </section>
  </aside>
</template>

<script setup lang="ts">
/**
 * annotate / compare 的右侧栏。三页:selection(选中的框或样本)、features(词表)、pattern(当前 pattern 总览;
 * 当前 pattern 是 unsorted 时是 unsorted 页);compare 下多一页 feedback(当前 pattern 的全部反馈,FeedbackPage)。
 * 页签由标注 store 管:在图上选中框或样本时自动翻到 selection;离开 compare 时停在 feedback 页就退回 selection
 * (侧栏挂上时也核一次:从 compare 切到 app 再回 annotate,侧栏是重新挂上的)。
 * compare 下 selection 页什么都没选中时,显示进 compare 时默认聚焦的那个样本(FocusedSamplePanel,只读)。
 */
import { computed, watch } from 'vue'
import { useAnnotationStore, type SidebarTab } from '../stores/annotation'
import { useCompareStore } from '../stores/compare'
import { useViewStore } from '../stores/view'
import BoxPanel from './BoxPanel.vue'
import FeaturesPanel from './FeaturesPanel.vue'
import FeedbackPage from './FeedbackPage.vue'
import FocusedSamplePanel from './FocusedSamplePanel.vue'
import PatternPanel from './PatternPanel.vue'
import SamplePanel from './SamplePanel.vue'

const ann = useAnnotationStore()
const cmp = useCompareStore()
const view = useViewStore()
const TABS = computed<SidebarTab[]>(() => (view.comparing
  ? ['selection', 'features', 'pattern', 'feedback'] : ['selection', 'features', 'pattern']))
watch(() => [view.comparing, ann.tab] as const, ([on, tab]) => {
  if (!on && tab === 'feedback') ann.tab = 'selection'
}, { immediate: true })
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
