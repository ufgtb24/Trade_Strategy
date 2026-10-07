<template>
  <div class="wf">
    <header class="top">
      <button type="button" data-testid="wf-exit" @click="emit('exit')">返回调试视图</button>
      <select class="list-select" data-testid="wf-list" :value="store.current?.list_id ?? ''"
              @change="onPickList(($event.target as HTMLSelectElement).value)">
        <option value="" disabled>选择清单…</option>
        <option v-for="l in store.lists" :key="l.list_id" :value="l.list_id">
          {{ l.title }}（{{ KIND_TEXT[l.kind] ?? l.kind }}，{{ l.n_items }} 条，{{ l.created_at }}）
        </option>
      </select>
      <div v-if="store.current" class="tabs" role="tablist">
        <button v-for="g in store.current.groups" :key="g.key" type="button" role="tab"
                :aria-selected="g.key === store.groupKey" :data-group="g.key"
                @click="store.setGroup(g.key)">{{ g.title }}</button>
      </div>
      <select v-if="store.allTags.length" data-testid="wf-tag" :value="store.tagFilter"
              @change="store.setTagFilter(($event.target as HTMLSelectElement).value)">
        <option value="">全部标签</option>
        <option v-for="t in store.allTags" :key="t" :value="t">{{ t }}</option>
      </select>
      <div v-if="store.current" class="pager">
        <button type="button" :disabled="store.page <= 0" @click="store.setPage(store.page - 1)">上一页</button>
        <span>第 {{ store.page + 1 }} / {{ store.pageCount }} 页（共 {{ store.filteredItems.length }} 条）</span>
        <button type="button" :disabled="store.page >= store.pageCount - 1"
                @click="store.setPage(store.page + 1)">下一页</button>
      </div>
      <button type="button" class="drawer-toggle" data-testid="wf-drawer" :aria-pressed="drawerOpen"
              @click="drawerOpen = !drawerOpen">已标注 ({{ store.draftCount }})</button>
    </header>

    <div v-if="store.loadError" class="err">{{ store.loadError }}</div>
    <div v-if="!store.lists.length && !store.loadError" class="hint">
      还没有清单。清单由会话用命令行工具生成，放在 outputs/chart_workflow/lists/ 下。
    </div>

    <section v-if="store.current?.summary" class="summary" data-testid="wf-summary">
      <table>
        <thead>
          <tr>
            <th>范围</th><th>命中数</th><th>股票数</th><th>周数</th>
            <th>命中方向均值</th><th>对照方向均值</th><th>方向领先</th><th>方向偶然波动</th>
            <th>命中涨幅中位</th><th>对照涨幅中位</th><th>幅度领先</th><th>幅度偶然波动</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in store.current.summary.rows" :key="r.scope">
            <td>{{ r.scope }}</td><td>{{ r.n_hits }}</td><td>{{ r.n_stocks }}</td><td>{{ r.n_weeks }}</td>
            <td>{{ sgn(r.hit_dir_mean) }}</td><td>{{ sgn(r.ctrl_dir_mean) }}</td>
            <td class="key">{{ sgn(r.dir_lead) }}</td><td>{{ num(r.dir_noise) }}</td>
            <td>{{ pct(r.hit_mag_median) }}</td><td>{{ pct(r.ctrl_mag_median) }}</td>
            <td class="key">{{ pctSgn(r.mag_lead) }}</td><td>{{ pct(r.mag_noise) }}</td>
          </tr>
        </tbody>
      </table>
      <div class="grad">
        <span>扎堆度：单周最多占 {{ pct(store.current.summary.concentration.max_week_share) }}，
          单只股票最多占 {{ pct(store.current.summary.concentration.max_stock_share) }}</span>
        <span class="verdict" data-testid="wf-graduation">毕业判定：{{ store.current.summary.graduation.passed ? '通过' : '未通过' }}</span>
        <span v-for="(ok, k) in store.current.summary.graduation.checks" :key="k" class="check">
          {{ CHECK_TEXT[k] ?? k }}：{{ ok ? '通过' : '未通过' }}</span>
      </div>
    </section>

    <div class="body">
      <main class="grid" data-testid="wf-grid">
        <AnnotChart v-for="it in store.pageItems" :key="it.item_id" :item="it"
                    :annotation="store.drafts.get(it.item_id) ?? null"
                    :highlighted="store.highlightItemId === it.item_id" />
      </main>
      <AnnotReviewPanel v-if="drawerOpen" />
    </div>

    <div v-if="store.zoomItem" class="backdrop" data-testid="wf-zoom" @click.self="store.setZoom(null)">
      <div class="modal">
        <div class="modal-head">
          <span>放大查看</span>
          <button type="button" data-testid="wf-zoom-close" @click="store.setZoom(null)">关闭</button>
        </div>
        <AnnotChart :item="store.zoomItem" :annotation="store.drafts.get(store.zoomItem.item_id) ?? null"
                    :large="true" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/** 看图工作流模式:上面是清单 summary 数表,下面 2×3 网格的 AnnotChart,右侧可收起的已标注抽屉。
 *
 * 入口:App.vue 见到 URL 带 wf 参数时渲染本视图。深链 ?wf=<list_id>&item=<item_id> 打开清单、
 * 翻到含这一条的页、高亮并放大;?wf= 为空时打开最新的一份清单。打开清单后 URL 同步成 ?wf=<list_id>。
 * 草稿非空时离开页面要确认(beforeunload)。 */
import { onBeforeUnmount, onMounted, ref } from 'vue'
import AnnotChart from './AnnotChart.vue'
import AnnotReviewPanel from './AnnotReviewPanel.vue'
import { useWorkflowStore } from '../stores/workflow'

const emit = defineEmits<{ exit: [] }>()
const store = useWorkflowStore()
const drawerOpen = ref(false)

const KIND_TEXT: Record<string, string> = {
  bigmoves: '大涨段', contrast: '对照', contrast_blind: '盲看',
}
const CHECK_TEXT: Record<string, string> = {
  dir_lead: '方向领先够大', mag_lead: '幅度领先为正', each_year: '每年都领先',
  beyond_noise: '超出偶然波动', not_clustered: '不扎堆',
}

function num(x: number | null | undefined) { return x == null ? '—' : x.toFixed(3) }
function sgn(x: number | null | undefined) { return x == null ? '—' : (x >= 0 ? '+' : '') + x.toFixed(3) }
function pct(x: number | null | undefined) { return x == null ? '—' : `${(x * 100).toFixed(1)}%` }
function pctSgn(x: number | null | undefined) {
  return x == null ? '—' : `${x >= 0 ? '+' : ''}${(x * 100).toFixed(1)}%`
}

function syncUrl(listId: string) {
  history.replaceState(null, '', `?wf=${encodeURIComponent(listId)}`)
}

async function onPickList(listId: string) {
  if (!listId) return
  if (await store.openList(listId)) syncUrl(listId)
}

function guard(e: BeforeUnloadEvent) {
  if (store.draftCount > 0) { e.preventDefault(); e.returnValue = '' }
}

onMounted(async () => {
  window.addEventListener('beforeunload', guard)
  await store.loadLists()
  const q = new URLSearchParams(location.search)
  const wf = q.get('wf') ?? ''
  const item = q.get('item')
  const target = wf || store.current?.list_id || store.lists[0]?.list_id
  if (!target) return
  if (store.current?.list_id === target && !item) return      // 从调试视图切回来,保留原状态
  // 深链打开后 URL 保留 item 参数,刷新页面仍能回到这一条
  if (await store.openList(target, { itemId: item }) && !item) syncUrl(target)
})
onBeforeUnmount(() => window.removeEventListener('beforeunload', guard))
</script>

<style scoped>
.wf { display: flex; flex-direction: column; height: 100vh; overflow: hidden; }
.top { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; padding: 6px 8px;
       border-bottom: 1px solid #cbd5e1; font-size: 13px; }
.list-select { max-width: 520px; }
.tabs { display: flex; gap: 2px; }
.tabs button { border: 1px solid #94a3b8; background: #fff; padding: 2px 8px; cursor: pointer; }
.tabs button[aria-selected="true"] { background: #0f172a; color: #fff; border-color: #0f172a; font-weight: 700; }
.pager { display: flex; gap: 6px; align-items: center; }
.drawer-toggle[aria-pressed="true"] { background: #0f172a; color: #fff; }
.err { color: #b91c1c; padding: 6px 8px; }
.hint { color: #475569; padding: 6px 8px; }
.summary { padding: 4px 8px; border-bottom: 1px solid #cbd5e1; font-size: 12px; overflow-x: auto; }
.summary table { border-collapse: collapse; }
.summary th, .summary td { border: 1px solid #e2e8f0; padding: 2px 6px; text-align: right; white-space: nowrap; }
.summary th:first-child, .summary td:first-child { text-align: left; }
.summary td.key { font-weight: 700; }
.grad { display: flex; flex-wrap: wrap; gap: 12px; margin-top: 4px; }
.verdict { font-weight: 700; }
.body { flex: 1; display: flex; min-height: 0; }
.grid { flex: 1; display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); grid-auto-rows: min-content;
        gap: 6px; padding: 6px; overflow: auto; }
.backdrop { position: fixed; inset: 0; background: rgba(15, 23, 42, 0.45); display: flex;
            align-items: center; justify-content: center; z-index: 50; }
.modal { background: #fff; width: 92vw; max-height: 96vh; overflow: auto; border-radius: 6px; padding: 8px; }
.modal-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;
              font-weight: 700; }
</style>
