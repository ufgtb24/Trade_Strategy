<script setup lang="ts">
import { fmt } from '../shared/formatters'
import type { PairPayload } from '../types'

defineProps<{ payload: PairPayload }>()
const emit = defineEmits<{ (e: 'undo-swap'): void }>()

// 4 类真实 invalid_reason(path2_web/diagnose.py::_derive_pair_response 逐字对应);
// 未命中的兜底原样显示 raw 值(防未来新增值时前端裸 falsy)。
const invalidLabels: Record<string, string> = {
  same_node: '两个 event 属于同一 node · node 内无 edge · 无法查 pair',
  no_edge_between_nodes: '两 node 在 dag_spec 中无直连 edge · pair 无从查起',
  only_negation_edge: '两 node 间只有 NegationEdge(全称禁止约束,非可导航依赖边)· 请用入口 C(候选级)看违禁信号',
  event_not_found: '找不到该 event · 请检查 instance_id',
}
</script>

<template>
  <div class="pair-detail-card">
    <div v-if="payload.applied_swap" class="swap-notice">
      ⚠ 顺序已自动切换:你点击 {{ payload.original_first_click }} → {{ payload.original_second_click }} ·
      该方向无 edge · 已改按 {{ payload.src_event_id }} → {{ payload.dst_event_id }} 查询
      <button type="button" class="undo-swap" @click="emit('undo-swap')">撤回</button>
    </div>
    <div v-if="!payload.valid" class="invalid-notice">
      {{ invalidLabels[payload.invalid_reason ?? ''] ?? payload.invalid_reason }}
    </div>
    <template v-else>
      <header>
        <strong>{{ payload.src_event_id }} → {{ payload.dst_event_id }}</strong>
        <span class="edge-meta">{{ payload.edge_kind }} · {{ payload.edge_id }}</span>
      </header>
      <div
        v-for="sc in payload.subchecks ?? []" :key="sc.channel"
        :class="['subcheck', sc.passed ? 'passed' : 'failed']"
      >
        <span class="channel">{{ sc.channel }}</span>
        <span class="verdict">{{ sc.passed ? '✓' : '✗' }}</span>
        <span v-if="sc.measured" class="measured">{{ fmt(sc.measured.value, sc.measured.kind) }}</span>
        <span v-if="sc.reason" class="reason">{{ sc.reason }}</span>
      </div>
      <div v-if="!payload.subchecks?.length" class="hint">无 subcheck 记录</div>
    </template>
  </div>
</template>

<style scoped>
.pair-detail-card { padding: 8px 10px; overflow-x: auto; min-width: 0; font-size: 12px; }
.swap-notice { background: #fefcbf; color: #744210; padding: 6px; border-radius: 4px; margin-bottom: 6px; }
.undo-swap {
  margin-left: 8px; border: 1px solid #cbd5e1; border-radius: 4px; background: #fff;
  color: #334155; font-size: 11px; padding: 1px 8px; cursor: pointer;
}
.undo-swap:hover { background: #f1f5f9; }
.invalid-notice { background: #fed7d7; color: #742a2a; padding: 10px; border-radius: 4px; }
.pair-detail-card header { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; color: #1e293b; }
.edge-meta { color: #64748b; font-size: 11px; white-space: nowrap; }
.subcheck { display: flex; gap: 8px; padding: 4px 0; border-bottom: 1px solid #f1f5f9; align-items: baseline; }
.subcheck .channel { font-weight: 600; min-width: 96px; }
.subcheck.passed { color: #16a34a; }
.subcheck.failed { color: #dc2626; }
.subcheck .reason { color: #94a3b8; }
.hint { color: #94a3b8; font-size: 11px; margin-top: 4px; }
</style>
