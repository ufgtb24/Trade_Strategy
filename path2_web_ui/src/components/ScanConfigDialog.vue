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
        <label>首次穿越 k (波动率倍数)</label>
        <input v-model.number="firstPassageK" type="number" min="0.1" step="0.1" data-field="first_passage_k" />
      </div>
      <div class="row">
        <label>价格区间</label>
        <input v-model="priceMin" data-field="price_min" placeholder="(可空)" />
        ~
        <input v-model="priceMax" data-field="price_max" placeholder="(可空)" />
      </div>
      <div class="row">
        <label>最小日均成交量</label>
        <input v-model="volumeMin" data-field="volume_min" placeholder="(可空)" />
      </div>
      <div v-if="badFilterFields.length" class="err">
        {{ badFilterFields.join('、') }} 不是数字(留空 = 不过滤)
      </div>
      <div class="row">
        <label>名称(可选)</label>
        <input v-model="note" data-field="note" placeholder="留空用时间戳自动命名,如:tb深度28-38" />
      </div>
      <div class="row">
        <label>ticker regex</label>
        <input v-model="tickerRegex" data-field="ticker_regex" placeholder="留空扫全部;如 ^(AAPL|TSLA)$" />
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
            <select class="src-select" data-testid="param-source"
                    :data-pid="p.pattern_id"
                    v-model="paramSource[p.pattern_id]"
                    title="本次扫描该 pattern 用哪份参数"
                    @click.stop
                    @change="onParamSourceChange(p.pattern_id)">
              <option v-for="f in (paramFiles[p.pattern_id] ?? ['params.yaml'])"
                      :key="f" :value="f">{{ f }}</option>
              <option v-if="view.workingCopy[p.pattern_id]" value="wc">
                Working Copy(改 {{ wcDiffCount(p.pattern_id) }} 字段)
              </option>
            </select>
          </li>
        </ul>
        <div v-if="!patterns.loaded" class="hint">加载中…</div>
      </div>

      <div class="footer">
        <button @click="onCancel">取消</button>
        <button class="primary"
                :disabled="patterns.selectedIds.size === 0 || scan.running || badFilterFields.length > 0"
                @click="onStart">开始扫描</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { usePatternsStore } from '../stores/patterns'
import { useConfigStore } from '../stores/config'
import { useScanStore } from '../stores/scan'
import { useViewStore } from '../stores/view'
import { listParamFiles } from '../api'
import { restoreSelectedPatterns, resolveParamSource } from './paramsEditorState'
import { validateScanName } from '../shared/scanName'

const SELECTED_LS_KEY = 'p2wc:scan:selectedPatterns'
const PARAM_SRC_LS_PREFIX = 'p2wc:scan:paramSource:'

const emit = defineEmits<{ close: [] }>()

const patterns = usePatternsStore()
const cfg = useConfigStore()
const scan = useScanStore()
const view = useViewStore()

const start = ref('2025-01-01')
const end = ref('2025-12-31')
const workers = ref(8)
const labelHorizon = ref(20)
const firstPassageK = ref(5)
const tickerRegex = ref('')
const note = ref('')
// 扫描过滤(spec §8):存 string 而非 number,空串 = 不过滤;
// 价格锚 end_node 事件日收盘价(match 级),成交量是扫描区间内日均量(股票级预筛)
const priceMin = ref('')
const priceMax = ref('')
const volumeMin = ref('')

// 空串/非数字 → null(不过滤),与 ticker_regex 的 .trim() || null 同一惯例
function numOrNull(s: string): number | null {
  const t = s.trim()
  if (!t) return null
  const n = Number(t)
  return Number.isFinite(n) ? n : null
}
// 三个过滤输入保持纯文本(不用 type="number":它会把 "1,000,000" 归一成空串,校验就
// 再也看不到用户到底输了什么)。非法输入(如带千分位、"10k")经 numOrNull 会静默变成
// null(=不过滤)——放宽筛选是静默的、不像误输入导致 0 命中那样会被立刻发现,而这个
// 项目的产出就是「某筛选条件下的命中数/lift」,静默放宽会污染研究结论。此处就地校验,
// 非法值挡在按钮禁用这一层,不让它有机会流进 numOrNull。
const badFilterFields = computed(() => {
  const out: string[] = []
  for (const [label, r] of [['价格下限', priceMin], ['价格上限', priceMax],
                            ['最小日均成交量', volumeMin]] as const) {
    const t = r.value.trim()
    if (t && !Number.isFinite(Number(t))) out.push(label)
  }
  return out
})
// 参数源(per-pid):'wc' = Working Copy(按值直扫) | '<name>.yaml' = app 目录下的具名文件(按引用)。
// 哨兵 'wc' 与文件名不会碰撞:白名单要求 .yaml 结尾。
const paramSource = ref<Record<string, string>>({})
const paramFiles = ref<Record<string, string[]>>({})   // pid → app 目录下可选 yaml

let anchorIndex = 0

// 持久化 pattern 子集:setup 同步注册 watch(组件 scope 随卸载自动 stop);
// flag 门控 onMounted init 期间的恢复赋值 —— onMounted 是 async,await 之后注册的 watch 会脱离
// 组件 effect scope(不随卸载 stop),故必须在 setup 同步段注册、用 flag 挡 init 期间的写。
let selectedInitDone = false
watch(() => patterns.selectedArray, (arr) => {
  if (!selectedInitDone) return
  try { localStorage.setItem(SELECTED_LS_KEY, JSON.stringify(arr)) } catch { /* 配额/禁用:静默 */ }
})

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
    if (typeof s.first_passage_k === 'number' && s.first_passage_k > 0) firstPassageK.value = s.first_passage_k
    tickerRegex.value = s.ticker_regex ?? ''
    priceMin.value = s.price_min != null ? String(s.price_min) : ''
    priceMax.value = s.price_max != null ? String(s.price_max) : ''
    volumeMin.value = s.volume_min != null ? String(s.volume_min) : ''
  }
  await patterns.loadPatterns()
  // pattern 子集持久化恢复:无记录 / 记录里 pattern 全失效 → selectAll(首次全选);否则恢复子集
  const restored = restoreSelectedPatterns(
    localStorage.getItem(SELECTED_LS_KEY),
    patterns.list.map(p => p.pattern_id),
  )
  if (restored) patterns.selectedIds = new Set(restored)
  else patterns.selectAll()
  // 每 pattern 并发拉文件列表;单个失败只回退该 pid,不整批中止(同 WorkingCopyDrawer 的 catch)
  await Promise.all(patterns.list.map(async (p) => {
    const pid = p.pattern_id
    let fileList: string[]
    try { fileList = await listParamFiles(pid) }
    catch { fileList = ['params.yaml'] }
    paramFiles.value[pid] = fileList
    // 参数源持久化:LS 记录的文件 / 'wc' 找不到或 WC 失效 → 回退 params.yaml;首次(null)统一 params.yaml
    paramSource.value[pid] = resolveParamSource(
      localStorage.getItem(PARAM_SRC_LS_PREFIX + pid), fileList, !!view.workingCopy[pid],
    )
  }))
  selectedInitDone = true   // init 完成,后续 selectedIds 变化才持久化
})

// Task 12 · WC 相对 baseline 变更的字段数(两层:section → field),供参数源下拉的
// Working Copy option 文案提示改了多少
function wcDiffCount(pid: string): number {
  const wc = view.workingCopy[pid]
  if (!wc) return 0
  let n = 0
  for (const sect of new Set([...Object.keys(wc.baseline), ...Object.keys(wc.currentDict)])) {
    const b = wc.baseline[sect] ?? {}, c = wc.currentDict[sect] ?? {}
    for (const k of new Set([...Object.keys(b), ...Object.keys(c)])) if (b[k] !== c[k]) n++
  }
  return n
}

// 参数源下拉切换 → 持久化(v-model 已写 paramSource[pid],@change 读即新值;
// onMounted 直接赋值不经 @change → 不会误触发)。LS 不可用则静默。
function onParamSourceChange(pid: string) {
  try { localStorage.setItem(PARAM_SRC_LS_PREFIX + pid, paramSource.value[pid]) } catch { /* 静默 */ }
}

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
  const nameErr = validateScanName(note.value)
  if (nameErr) { alert(nameErr); return }
  if (patterns.selectedIds.size === 0 || scan.running) return
  const s = {
    start_date: start.value,
    end_date: end.value,
    workers: workers.value,
    ticker_regex: tickerRegex.value.trim() || null,
    label_horizon: labelHorizon.value,
    first_passage_k: firstPassageK.value,
    price_min: numOrNull(priceMin.value),
    price_max: numOrNull(priceMax.value),
    volume_min: numOrNull(volumeMin.value),
  }
  if (cfg.config) {
    await cfg.save({ ...cfg.config, scan: s })
  }
  // 参数源分三桶:'wc' → 按值 override(且记 WC 快照);具名文件 → 按引用;
  // 'params.yaml' → 两桶都不进,后端走兜底 load_params()(与「不选」逐字等价)
  const overrides: Record<string, Record<string, any>> = {}
  const files: Record<string, string> = {}
  const wcPids: string[] = []
  for (const pid of patterns.selectedIds) {
    const src = paramSource.value[pid]
    const wc = view.workingCopy[pid]
    if (src === 'wc' && wc) {
      overrides[pid] = wc.currentDict
      wcPids.push(pid)                     // ★ 红线:wcPids 只在这一支填(见 plan Task 4)
    } else if (src && src !== 'wc' && src !== 'params.yaml') {
      files[pid] = src
    }
  }
  scan.markWcLaunch(wcPids)   // 发起前记 hash snapshot,done 后 hash 守卫自动清 WC(见 scan store)
  try {
    await scan.run({ pattern_ids: patterns.selectedArray, ...s,
                     ...(Object.keys(overrides).length ? { params_overrides: overrides } : {}),
                     ...(Object.keys(files).length ? { params_files: files } : {}),
                     ...(note.value.trim() ? { note: note.value.trim() } : {}) } as any)
  } catch (e: any) {
    scan.markWcLaunch([])       // 启动失败,清掉刚记的 WC 快照,免得污染下一次 settle
    alert(`扫描启动失败: ${e?.message ?? e}`)
    return                      // 不关对话框:用户可就地改参数源再试
  }
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
.err { color: #dc2626; font-size: 11px; margin: -4px 0 8px; }

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
  display: flex; align-items: center; flex-wrap: wrap; gap: 6px;
  padding: 4px 8px; font-size: 12px; cursor: pointer; user-select: none;
}
.pattern-list li:hover { background: #f8fafc; }
.pattern-list li.selected { background: #dbeafe; }
.pattern-list li .name { font-weight: 500; }
.src-select { margin-left: auto; font-size: 11px; max-width: 190px; }

.footer { margin-top: 14px; display: flex; justify-content: flex-end; gap: 8px; }
.footer button { padding: 6px 14px; font-size: 12px; cursor: pointer;
                 border: 1px solid #cbd5e1; background: #fff; }
.footer button.primary { background: #2563eb; color: #fff; border-color: #2563eb; }
.footer button.primary:disabled { background: #94a3b8; border-color: #94a3b8; cursor: not-allowed; }

.hint { font-size: 11px; color: #64748b; margin-top: 4px; }
</style>
