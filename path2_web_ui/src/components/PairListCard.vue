<script setup lang="ts">
import { computed } from 'vue'
import type { NodesPayload, PairFailure } from '../types'

const props = defineProps<{ payload: NodesPayload }>()

const emit = defineEmits<{
  (e: 'pair-deep-dive', payload: { srcInstanceId: string; dstInstanceId: string }): void
}>()

const totalFailed = computed(() => props.payload.total_pair - props.payload.ok_pair)

// miss_reasons 可能是空 dict(no_such_edge 早退路径)· 缺 key 时按 0 显示,不炸模板。
function missCount(reason: string): number {
  return props.payload.miss_reasons[reason] ?? 0
}

function handleRowClick(row: PairFailure): void {
  emit('pair-deep-dive', { srcInstanceId: row.src_event_id, dstInstanceId: row.dst_event_id })
}
</script>

<template>
  <div class="pair-list-card">
    <header>
      <strong>{{ payload.edge_id }}</strong>
      <span class="summary">{{ payload.ok_pair }} / {{ payload.total_pair }} 通过 · {{ totalFailed }} 失败</span>
    </header>
    <section class="miss-reasons">
      <span>gap 越界:{{ missCount('gap_out') }}</span>
      <span>anchor 破位:{{ missCount('anchor_mismatch') }}</span>
      <span>strict fail:{{ missCount('strict_fail') }}</span>
    </section>
    <section class="examples">
      <table v-if="payload.example_failed_pairs.length">
        <thead><tr><th>src</th><th>dst</th><th>栽在</th></tr></thead>
        <tbody>
          <tr
            v-for="row in payload.example_failed_pairs"
            :key="`${row.src_event_id}_${row.dst_event_id}`"
            class="clickable"
            @click="handleRowClick(row)"
          >
            <td>{{ row.src_event_id }}</td>
            <td>{{ row.dst_event_id }}</td>
            <td>{{ row.subcheck_stage }}</td>
          </tr>
        </tbody>
      </table>
      <div v-else class="hint">无失败样例</div>
    </section>
  </div>
</template>

<style scoped>
.pair-list-card { padding: 8px 10px; overflow-x: auto; min-width: 0; font-size: 12px; }
.pair-list-card header { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; }
.summary { color: #64748b; font-size: 11px; white-space: nowrap; }
.miss-reasons { display: flex; gap: 12px; margin: 6px 0; color: #744210; font-size: 11px; }
.examples table { border-collapse: collapse; width: 100%; }
.examples th, .examples td { padding: 2px 6px; text-align: left; font-size: 11px; }
.examples th { color: #64748b; font-weight: 500; }
.clickable { cursor: pointer; }
.clickable:hover { background: #edf2f7; }
.hint { color: #94a3b8; font-size: 11px; }
</style>
