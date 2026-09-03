<script setup lang="ts">
import { computed, watch } from 'vue'
import { fmt } from '../shared/formatters'
import type { TimePayload } from '../types'

const props = defineProps<{ payload: TimePayload; node: string }>()
const emit = defineEmits<{ (e: 'update:node', v: string): void }>()

/** 区间内实际有 gate 失败的 node_id 集合(唯一可选的过滤键)。
 * 恒基于全量 payload:请求不带 node 过滤,后端不过滤(2026-08-10)。
 * ★ wire:GateFailure.node_id 值 = 物化来源 node(Task 1),此处即 node_id 字符串。 */
const failedNodes = computed(() => {
  return new Set(props.payload.failed_attempts.map(a => a.node_id))
})

/** 显示过滤 = 本地:node 非空时只显示该 node 的 attempt。
 * 不重新请求(后端 node 过滤会返回子集 → failedNodes 坍缩 → 其他 node 置灰)。 */
const filteredAttempts = computed(() => {
  if (!props.node) return props.payload.failed_attempts
  return props.payload.failed_attempts.filter(a => a.node_id === props.node)
})

/** 全部 node 选项(全集)= 后端下发的 pattern 全部 node_id ∪ 实际失败的 node_id。
 * 不能硬编码(burst/bo/tb)——node 名随重构漂移(tb → tb_v1/tb_seg)时,硬编码选项与
 * 真实 node 不匹配 → 后端 node 严格过滤后 0 结果,表现为"诊断卡片没有该
 * 类型条目"(无声失败,与 anchorsOf 白名单同源)。
 * 全集可见但无失败者置灰:能区分"这个 node 存在、只是本区间没失败"与"这个 node 不存在",
 * 又不会选中后得到 0 结果空卡片。all_nodes 缺失(旧后端)→ 回退实际失败集。 */
const nodeOptions = computed(() => {
  const set = new Set<string>(props.payload.all_nodes ?? [])
  for (const c of failedNodes.value) set.add(c)
  return [...set].sort()
})

// node 残留保护:切股/切区间后旧 node 在该区间无失败(置灰不可选)或已不存在
// → 自动回退"全部",防"下拉选了 tb,新区间无 tb 失败 → 本地过滤恒空卡片"的静默态。
// watch failedNodes 而非 nodeOptions:切区间后 failedNodes 必变、nodeOptions 可能不变
// (同 pattern 全集相同),依赖 nodeOptions 的变化事件会漏掉"选项置灰"这一回退触发。
// immediate:mount 时(payload 更新后)立即检查一次。
watch(failedNodes, () => {
  if (props.node && !failedNodes.value.has(props.node)) {
    emit('update:node', '')
  }
}, { immediate: true })

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
  emit('update:node', (e.target as HTMLSelectElement).value)
}
</script>

<template>
  <div class="failed-attempts-card">
    <header>
      <strong>时段 [{{ payload.frame[0] }}, {{ payload.frame[1] }}]</strong>
      · 框内 {{ filteredAttempts.length }} 个 attempt
      <label class="filter-label">
        · 只看
        <select class="event-class-filter" :value="node" @change="onFilterChange">
          <option value="">全部</option>
          <option v-for="c in nodeOptions" :key="c" :value="c" :disabled="!failedNodes.has(c)">{{ c }}</option>
        </select>
      </label>
    </header>
    <div
      v-for="(a, i) in filteredAttempts" :key="i"
      :class="['attempt-card', overlapClass(a.failure_event_window, payload.frame)]"
    >
      <div class="attempt-header">
        <span class="node-id">{{ a.node_id }}</span>
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
    <div v-if="!filteredAttempts.length" class="hint">框内无 gate 失败样例</div>
  </div>
</template>

<style scoped>
.failed-attempts-card { padding: 8px 10px; overflow-x: auto; min-width: 0; font-size: 12px; }
.failed-attempts-card header { color: #334155; margin-bottom: 6px; }
.filter-label { color: #64748b; margin-left: 2px; }
.event-class-filter { font-size: 11px; padding: 1px 4px; border: 1px solid #cbd5e1; border-radius: 3px; background: white; margin-left: 4px; }
/* disabled(本区间无该 class 的 gate 失败)= 灰底 + 与 enable 同色黑字:
 * 置灰语义靠底色传达(可见但不可选),字体保持可读,不靠字体变色 */
.event-class-filter option:disabled { background-color: #e2e8f0; color: #1e293b; }
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
