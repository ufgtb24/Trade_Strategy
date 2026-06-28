<template>
  <div class="chart-area">
    <!-- row0: 全局 level 控件 -->
    <div class="level-bar" data-testid="level-control">
      <button
        v-for="opt in LEVEL_OPTIONS"
        :key="opt.value"
        :class="['level-btn', { active: level === opt.value }]"
        :title="opt.title"
        @click="view.setLevel(opt.value)"
      >{{ opt.label }}</button>
      <select :value="view.activePatternId ?? ''"
              data-role="active-pattern"
              @change="onActivePatternChange"
              class="active-pattern-select"
              v-if="view.patternIds.length > 0">
        <option v-for="pid in view.patternIds" :key="pid" :value="pid">
          {{ pid }}
        </option>
      </select>
    </div>
    <!-- row1: 拓扑控制 -->
    <TopologyControl @hover-role="onHoverRole" />
    <!-- row2: K线 + 诊断侧栏 -->
    <KlineChart />
    <DetailSidebar />
  </div>
</template>

<script setup lang="ts">
import { storeToRefs } from 'pinia'
import TopologyControl from './TopologyControl.vue'
import KlineChart from './KlineChart.vue'
import DetailSidebar from './DetailSidebar.vue'
import { useViewStore } from '../stores/view'
import type { Level } from '../types'

const view = useViewStore()
const { level } = storeToRefs(view)

const LEVEL_OPTIONS: { value: Level; label: string; title: string }[] = [
  { value: 'matched', label: 'Matched',  title: '仅显示命中 match 的事件' },
  { value: 'qualified',  label: 'Qualified',   title: '显示命中 match 或参与诊断 trace 的事件' },
  { value: 'detected', label: 'Detected', title: '显示所有被 detector 检出的事件' },
]

function onHoverRole(_nodeId: string | null) { /* 高亮交互留 KlineChart 内部增强,见 Task 12 微调 */ }

function onActivePatternChange(e: Event) {
  view.setActivePattern((e.target as HTMLSelectElement).value)
}
</script>

<style scoped>
/* row0: level bar; row1: topology; row2: 限 560px */
.chart-area {
  display: grid;
  grid-template-columns: 1fr 280px;
  grid-template-rows: auto auto 560px;
  gap: 0;
}
/* level-bar 和 topology 各跨两列 */
.level-bar,
.chart-area > :nth-child(2) { grid-column: 1 / 3; }

.level-bar {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 4px 8px;
  background: #1a1a2e;
  border-bottom: 1px solid #2a2a4a;
}

.level-btn {
  padding: 3px 14px;
  border: 1px solid #3a3a5a;
  border-radius: 4px;
  background: transparent;
  color: #aaa;
  font-size: 12px;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}
.level-btn:hover { background: #2a2a4a; color: #ddd; }
.level-btn.active { background: #4a4aaa; color: #fff; border-color: #6a6acc; }

.active-pattern-select { margin-left: 8px; font-size: 12px; padding: 2px 4px; }
</style>
