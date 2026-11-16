<template>
  <aside class="left-panel">
    <!-- 前三档:找图清单;scan 档:扫描面板与扫描结果列表。两份切档时只藏不拆,滚动位置与列表位置都留着 -->
    <FinderList v-show="!scanView" />
    <div v-show="scanView" class="scan-side" data-testid="scan-side">
      <SidebarPatternPanel />
      <SidebarScanPanel />
      <SidebarResultList />
    </div>
  </aside>
</template>

<script setup lang="ts">
/**
 * 主视图的左栏,随顶栏 mode 换内容:
 * - annotate / compare / app:找图清单(FinderList),只列用户自己存下的东西和这次 random 抽到的图,
 *   不出现 app 的任何结果(扫描的命中、收益都不在这里);
 * - scan:扫描的 Patterns 面板、扫描面板(扫描 ⚙、打开历史)和扫描结果列表,按法不变。
 */
import { storeToRefs } from 'pinia'
import FinderList from './FinderList.vue'
import SidebarPatternPanel from './SidebarPatternPanel.vue'
import SidebarScanPanel from './SidebarScanPanel.vue'
import SidebarResultList from './SidebarResultList.vue'
import { useViewStore } from '../stores/view'

const { scanView } = storeToRefs(useViewStore())
</script>

<style scoped>
.left-panel { display: flex; flex-direction: column; min-height: 0; overflow: hidden; }
.scan-side { display: flex; flex-direction: column; flex: 1; min-height: 0; overflow: hidden; }
</style>
