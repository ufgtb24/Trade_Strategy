<script setup lang="ts">
import { fmt } from '../shared/formatters'
import type { TimePayload } from '../types'

defineProps<{ payload: TimePayload; eventClass: string }>()
const emit = defineEmits<{ (e: 'update:eventClass', v: string): void }>()

/** overlap 徽标:(start,end) vs 用户框选 frame 的三种关系 → 3 色分类(入口 A)。
 * 框内(fully_inside)/ 包含框(contains_frame)/ 部分重叠(partial)。*/
function overlapClass(fw: [number, number], frame: [number, number]): string {
  const [ws, we] = fw
  const [fs, fe] = frame
  if (ws >= fs && we <= fe) return 'overlap-fully_inside'
  if (ws <= fs && we >= fe) return 'overlap-contains_frame'
  return 'overlap-partial'
}

function onFilterChange(e: Event) {
  emit('update:eventClass', (e.target as HTMLSelectElement).value)
}
</script>

<template>
  <div class="failed-attempts-card">
    <header>
      <strong>时段 [{{ payload.frame[0] }}, {{ payload.frame[1] }}]</strong>
      · 框内 {{ payload.failed_attempts.length }} 个 attempt
      <label class="filter-label">
        · 只看
        <select class="event-class-filter" :value="eventClass" @change="onFilterChange">
          <option value="">全部</option>
          <option value="burst">burst</option>
          <option value="bo">bo</option>
          <option value="tb">tb</option>
        </select>
      </label>
    </header>
    <div
      v-for="(a, i) in payload.failed_attempts" :key="i"
      :class="['attempt-card', overlapClass(a.failure_event_window, payload.frame)]"
    >
      <div class="attempt-header">
        <span class="class-id">{{ a.class_id }}</span>
        <span class="window">[{{ a.failure_event_window[0] }}, {{ a.failure_event_window[1] }}]</span>
      </div>
      <div class="gate">栽在 {{ a.gate_name }}</div>
      <div class="clause">
        <template v-if="a.op !== null">
          {{ fmt(a.measured.value, a.measured.kind) }} {{ a.op }} {{ a.threshold }}<template v-if="a.threshold_param"> ({{ a.threshold_param }})</template> ✗
        </template>
        <template v-else>
          {{ a.measured.label }}: {{ fmt(a.measured.value, a.measured.kind) }} ✗
        </template>
      </div>
      <div class="trigger">触发 bar {{ a.gate_idx }}</div>
      <div
        v-if="a.evaluation_lookback" class="lookback"
        :title="`参照历史 [${a.evaluation_lookback[0]}, ${a.evaluation_lookback[1]}]`"
      >
        参照历史 ({{ a.evaluation_lookback[0] }} .. {{ a.evaluation_lookback[1] }})
      </div>
      <div v-if="a.code_location" class="code-location">{{ a.code_location }}</div>
    </div>
    <div v-if="!payload.failed_attempts.length" class="hint">框内无 gate 失败样例</div>
  </div>
</template>

<style scoped>
.failed-attempts-card { padding: 8px 10px; overflow-x: auto; min-width: 0; font-size: 12px; }
.failed-attempts-card header { color: #334155; margin-bottom: 6px; }
.filter-label { color: #64748b; margin-left: 2px; }
.event-class-filter { font-size: 11px; padding: 1px 4px; border: 1px solid #cbd5e1; border-radius: 3px; background: white; margin-left: 4px; }
.attempt-card { border: 1px solid #e2e8f0; border-left-width: 3px; border-radius: 4px; padding: 6px 8px; margin: 6px 0; }
.overlap-fully_inside { border-left-color: #22c55e; }
.overlap-partial { border-left-color: #f59e0b; }
.overlap-contains_frame { border-left-color: #3b82f6; }
.attempt-header { display: flex; gap: 8px; font-weight: 600; color: #1e293b; }
.attempt-header .window { color: #64748b; font-weight: 400; }
.gate, .trigger, .lookback { margin-top: 2px; color: #475569; font-size: 11px; }
.hint { color: #94a3b8; font-size: 11px; margin-top: 4px; }
.clause { color: #334155; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; margin-top: 2px; }
.code-location {
  margin-top: 2px;
  color: #94a3b8;
  font-size: 0.85em;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}
</style>
