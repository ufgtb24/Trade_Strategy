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
 * 现在只有页签和空页;各页内容由画框、样本、归组几张票填。
 */
import { ref } from 'vue'

const TABS = ['selection', 'features', 'pattern'] as const
type Tab = typeof TABS[number]
const tab = ref<Tab>('selection')
</script>

<style scoped>
.annotation-sidebar {
  display: flex; flex-direction: column; min-height: 0; overflow: auto;
  border-left: 1px solid #d4d4d8; background: #fff; color: #111;
}
.tabs {
  position: sticky; top: 0; display: flex; gap: 12px; padding: 6px 8px 0;
  background: #fff; border-bottom: 1px solid #e4e4e7;
}
.tab, .empty { font-family: ui-monospace, "JetBrains Mono", "DejaVu Sans Mono", Consolas, monospace; font-size: 12px; }
/* 文字一律黑;没选上的页签按「没选上的状态」用灰字,选中的加黑色下划线 */
.tab {
  padding: 2px 2px 4px; border: none; border-bottom: 2px solid transparent;
  background: none; color: #71717a; cursor: pointer;
}
.tab.on { color: #111; border-bottom-color: #111; }
.body { padding: 8px; }
.empty { color: #a1a1aa; }
</style>
