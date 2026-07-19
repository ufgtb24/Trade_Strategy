<template>
  <div class="backdrop" @click.self="onCancel">
    <div class="dialog">
      <h3>扫描配置</h3>

      <div class="row">
        <label>区间</label>
        <input v-model="start" data-field="start_date" />
        ~
        <input v-model="end" data-field="end_date" />
      </div>
      <div class="row">
        <label>workers</label>
        <input v-model.number="workers" type="number" min="1" data-field="workers" />
      </div>
      <div class="row">
        <label>label horizon (days)</label>
        <input v-model.number="labelHorizon" type="number" min="1" data-field="label_horizon" />
      </div>
      <div class="row">
        <label>ticker regex</label>
        <input v-model="tickerRegex" data-field="ticker_regex" placeholder="(可空)" />
      </div>

      <div class="patterns-block">
        <div class="patterns-hdr">
          <span class="title">Patterns</span>
          <div class="actions">
            <button @click="patterns.selectAll">全选</button>
            <button @click="patterns.selectNone">清空</button>
            <button @click="patterns.invertSelection">反选</button>
          </div>
        </div>
        <ul class="pattern-list" tabindex="0" @keydown.esc="onCancel">
          <li v-for="(p, i) in patterns.list" :key="p.pattern_id"
              :data-pid="p.pattern_id"
              :class="{ selected: patterns.selectedIds.has(p.pattern_id) }"
              @click="onRowClick($event, i, p.pattern_id)">
            <input type="checkbox"
                   :checked="patterns.selectedIds.has(p.pattern_id)"
                   @click.stop="patterns.toggleSelected(p.pattern_id)" />
            <span class="name">{{ p.pattern_id }}</span>
          </li>
        </ul>
        <div v-if="!patterns.loaded" class="hint">加载中…</div>
      </div>

      <div class="footer">
        <button @click="onCancel">取消</button>
        <button class="primary"
                :disabled="patterns.selectedIds.size === 0 || scan.running"
                @click="onStart">开始扫描</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { usePatternsStore } from '../stores/patterns'
import { useConfigStore } from '../stores/config'
import { useScanStore } from '../stores/scan'

const emit = defineEmits<{ close: [] }>()

const patterns = usePatternsStore()
const cfg = useConfigStore()
const scan = useScanStore()

const start = ref('2025-01-01')
const end = ref('2025-12-31')
const workers = ref(8)
const labelHorizon = ref(20)
const tickerRegex = ref('')

let anchorIndex = 0

onMounted(async () => {
  try {
    await cfg.load()
  } catch { /* 后端不可用: 保留默认 */ }
  const s = cfg.config?.scan
  if (s) {
    if (s.start_date) start.value = s.start_date
    if (s.end_date) end.value = s.end_date
    if (typeof s.workers === 'number' && s.workers > 0) workers.value = s.workers
    if (typeof s.label_horizon === 'number' && s.label_horizon > 0) labelHorizon.value = s.label_horizon
    tickerRegex.value = s.ticker_regex ?? ''
  }
  await patterns.loadPatterns()
  patterns.selectAll()
})

function onRowClick(evt: MouseEvent, i: number, pid: string) {
  if (evt.shiftKey) {
    const [lo, hi] = anchorIndex <= i ? [anchorIndex, i] : [i, anchorIndex]
    const s = new Set(patterns.selectedIds)
    for (let k = lo; k <= hi; k++) s.add(patterns.list[k].pattern_id)
    patterns.selectedIds = s
  } else if (evt.ctrlKey || evt.metaKey) {
    patterns.toggleSelected(pid)
    anchorIndex = i
  } else {
    patterns.selectedIds = new Set([pid])
    anchorIndex = i
  }
}

async function onStart() {
  if (patterns.selectedIds.size === 0 || scan.running) return
  const s = {
    start_date: start.value,
    end_date: end.value,
    workers: workers.value,
    ticker_regex: tickerRegex.value.trim() || null,
    label_horizon: labelHorizon.value,
  }
  if (cfg.config) {
    await cfg.save({ ...cfg.config, scan: s })
  }
  scan.run({ pattern_ids: patterns.selectedArray, ...s } as any)
  emit('close')
}

function onCancel() { emit('close') }
</script>

<style scoped>
.backdrop {
  position: fixed; inset: 0; background: rgba(0,0,0,0.4);
  display: flex; align-items: center; justify-content: center; z-index: 200;
}
.dialog {
  background: #fff; border-radius: 6px; padding: 16px 20px;
  width: 480px; max-height: 80vh; overflow: auto;
  box-shadow: 0 8px 24px rgba(0,0,0,0.2);
}
.dialog h3 { margin: 0 0 12px; font-size: 15px; }
.row { margin: 8px 0; display: flex; align-items: center; gap: 8px; }
.row label { font-size: 12px; color: #64748b; min-width: 130px; }
.row input { padding: 3px 6px; font-size: 12px; flex: 1; }
.row input[type="number"] { max-width: 80px; flex: none; }

.patterns-block { margin-top: 14px; border-top: 1px solid #e5e7eb; padding-top: 10px; }
.patterns-hdr { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.patterns-hdr .title { font-weight: 600; font-size: 13px; }
.patterns-hdr .actions button { font-size: 11px; margin-left: 4px; padding: 1px 6px;
                                 border: 1px solid #cbd5e1; background: #fff; cursor: pointer; }
.pattern-list {
  list-style: none; padding: 0; margin: 0;
  max-height: 220px; overflow-y: auto;
  border: 1px solid #e5e7eb; border-radius: 4px;
}
.pattern-list li {
  display: flex; align-items: center; gap: 6px;
  padding: 4px 8px; font-size: 12px; cursor: pointer; user-select: none;
}
.pattern-list li:hover { background: #f8fafc; }
.pattern-list li.selected { background: #dbeafe; }
.pattern-list li .name { font-weight: 500; }

.footer { margin-top: 14px; display: flex; justify-content: flex-end; gap: 8px; }
.footer button { padding: 6px 14px; font-size: 12px; cursor: pointer;
                 border: 1px solid #cbd5e1; background: #fff; }
.footer button.primary { background: #2563eb; color: #fff; border-color: #2563eb; }
.footer button.primary:disabled { background: #94a3b8; border-color: #94a3b8; cursor: not-allowed; }

.hint { font-size: 11px; color: #64748b; margin-top: 4px; }
</style>
