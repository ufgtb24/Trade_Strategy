<template>
  <aside class="annotation-sidebar" data-testid="annotation-sidebar">
    <nav class="tabs" role="tablist">
      <button v-for="t in TABS" :key="t" type="button" role="tab"
              :class="['tab', { on: tab === t }]"
              :aria-selected="tab === t"
              :data-testid="`annotation-tab-${t}`"
              @click="tab = t">{{ t }}</button>
    </nav>
    <section class="body" :data-testid="`annotation-page-${tab}`">
      <span class="empty">empty</span>
    </section>
  </aside>
</template>

<script setup lang="ts">
/**
 * annotate 模式的右侧栏,三页:selection(选中的框或样本)、features(词表)、pattern(当前 pattern 总览)。
 * 三页目前都是空页。
 */
import { ref } from 'vue'

const TABS = ['selection', 'features', 'pattern'] as const
type Tab = typeof TABS[number]
const tab = ref<Tab>('selection')
</script>

<style scoped>
/* 字体与色值见 App.vue 的 :root 变量 */
.annotation-sidebar {
  display: flex; flex-direction: column; min-height: 0; overflow: auto;
  border-left: 1px solid var(--line); background: #fff; color: var(--ink);
}
.tabs {
  position: sticky; top: 0; display: flex; gap: 12px; padding: 6px 8px 0;
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
