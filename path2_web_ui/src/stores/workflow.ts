/** 看图工作流模式的状态:清单目录与当前清单、分组 / 标签筛选 / 翻页、标注草稿、发送状态、放大中的 item。
 *
 * 标注草稿只放内存(Map<item_id, Annotation>,每个 item 最多一条),不写 localStorage:
 * 未发送就丢,只靠 WorkflowView 的离开提醒兜底。草稿属于产生它的那份清单(draftListId),
 * 切到别的清单时要先确认丢弃。 */
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import type {
  Annotation, AnnotationBatchResult, WorkflowItem, WorkflowList, WorkflowListMeta,
} from '../types'
import { listWorkflowLists, loadWorkflowList, sendAnnotations } from '../api'

export const PAGE_SIZE = 6

/** 本地时间 YYYY-MM-DDTHH:MM:SS(与后端写盘口径一致)。 */
export function nowLocal(d: Date = new Date()): string {
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
    + `T${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

function newId(): string {
  const c = (globalThis as any).crypto
  if (c?.randomUUID) return c.randomUUID()
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, ch => {
    const r = Math.random() * 16 | 0
    return (ch === 'x' ? r : (r & 0x3) | 0x8).toString(16)
  })
}

/** 一条草稿缺什么(空数组 = 可以发送)。 */
export function missingFields(a: Annotation): string[] {
  const out: string[] = []
  if (!a.range_start || !a.range_end) out.push('起止')
  if (!a.label) out.push('标签')
  return out
}

export const useWorkflowStore = defineStore('workflow', () => {
  const lists = ref<WorkflowListMeta[]>([])
  const current = ref<WorkflowList | null>(null)
  const loadError = ref<string | null>(null)
  const groupKey = ref('')
  const tagFilter = ref('')
  const page = ref(0)
  const drafts = ref(new Map<string, Annotation>())
  const draftListId = ref<string | null>(null)
  const sending = ref(false)
  const sendError = ref<string | null>(null)
  const lastSent = ref<AnnotationBatchResult | null>(null)
  const zoomItemId = ref<string | null>(null)
  const highlightItemId = ref<string | null>(null)

  const isBlind = computed(() => current.value?.kind === 'contrast_blind')
  const itemsById = computed(() => new Map<string, WorkflowItem>(
    (current.value?.items ?? []).map(it => [it.item_id, it])))
  const currentGroup = computed(() =>
    current.value?.groups.find(g => g.key === groupKey.value) ?? null)
  const groupItems = computed<WorkflowItem[]>(() =>
    (currentGroup.value?.item_ids ?? [])
      .map(id => itemsById.value.get(id))
      .filter((x): x is WorkflowItem => !!x))
  const allTags = computed(() =>
    [...new Set(groupItems.value.flatMap(it => it.tags ?? []))].sort())
  const filteredItems = computed(() => tagFilter.value
    ? groupItems.value.filter(it => (it.tags ?? []).includes(tagFilter.value))
    : groupItems.value)
  const pageCount = computed(() => Math.max(1, Math.ceil(filteredItems.value.length / PAGE_SIZE)))
  const pageItems = computed(() =>
    filteredItems.value.slice(page.value * PAGE_SIZE, (page.value + 1) * PAGE_SIZE))
  const draftList = computed(() => [...drafts.value.values()])
  const draftCount = computed(() => drafts.value.size)
  const incomplete = computed(() => draftList.value.filter(a => missingFields(a).length > 0))
  const zoomItem = computed(() =>
    zoomItemId.value ? itemsById.value.get(zoomItemId.value) ?? null : null)

  async function loadLists() {
    try {
      lists.value = await listWorkflowLists()
      loadError.value = null
    } catch (e: any) {
      loadError.value = String(e?.message ?? e)
    }
  }

  /** 打开一份清单;有别的清单的未发送草稿时先确认丢弃(取消则不切换,返回 false)。
   *  itemId:深链用,打开后翻到含它的那一页、高亮并放大。 */
  async function openList(listId: string, opts: { itemId?: string | null } = {}): Promise<boolean> {
    if (drafts.value.size > 0 && draftListId.value && draftListId.value !== listId) {
      const ok = window.confirm(
        `还有 ${drafts.value.size} 条标注没有发送，切换清单会丢掉它们。确定切换吗？`)
      if (!ok) return false
      clearDrafts()
    }
    try {
      const doc = await loadWorkflowList(listId)
      current.value = doc
      loadError.value = null
    } catch (e: any) {
      loadError.value = String(e?.message ?? e)
      return false
    }
    groupKey.value = current.value.groups[0]?.key ?? ''
    tagFilter.value = ''
    page.value = 0
    zoomItemId.value = null
    highlightItemId.value = null
    sendError.value = null
    if (opts.itemId) gotoItem(opts.itemId, { zoom: true })
    return true
  }

  function setGroup(key: string) {
    groupKey.value = key
    tagFilter.value = ''
    page.value = 0
  }

  function setTagFilter(tag: string) {
    tagFilter.value = tag
    page.value = 0
  }

  function setPage(p: number) {
    page.value = Math.min(Math.max(0, p), pageCount.value - 1)
  }

  /** 翻到含这一条的那一页并高亮;当前分组(含筛选)里没有就换到第一个含它的分组。 */
  function gotoItem(itemId: string, opts: { zoom?: boolean } = {}) {
    if (!current.value || !itemsById.value.has(itemId)) return
    let idx = filteredItems.value.findIndex(it => it.item_id === itemId)
    if (idx < 0) {
      const inGroup = currentGroup.value?.item_ids.includes(itemId)
      if (inGroup) {
        tagFilter.value = ''
      } else {
        const g = current.value.groups.find(x => x.item_ids.includes(itemId))
        if (!g) return
        setGroup(g.key)
      }
      idx = filteredItems.value.findIndex(it => it.item_id === itemId)
    }
    page.value = Math.floor(idx / PAGE_SIZE)
    highlightItemId.value = itemId
    if (opts.zoom) zoomItemId.value = itemId
  }

  function upsertAnnotation(itemId: string, patch: Partial<Annotation>) {
    const item = itemsById.value.get(itemId)
    if (!item || !current.value) return
    const prev = drafts.value.get(itemId) ?? {
      ann_id: newId(), item_id: itemId, symbol: item.symbol,
      range_start: null, range_end: null, buy_date: null, label: null, note: '', updated_at: '',
    }
    drafts.value.set(itemId, { ...prev, ...patch, item_id: itemId, symbol: item.symbol,
                               updated_at: nowLocal() })
    draftListId.value = current.value.list_id
    lastSent.value = null
  }

  function deleteAnnotation(itemId: string) {
    drafts.value.delete(itemId)
    if (drafts.value.size === 0) draftListId.value = null
  }

  function clearDrafts() {
    drafts.value.clear()
    draftListId.value = null
  }

  /** 发送本批全部草稿。有没标完的就不发,把缺什么写进 sendError。成功后清空草稿。 */
  async function send(): Promise<boolean> {
    if (!current.value || drafts.value.size === 0 || sending.value) return false
    if (incomplete.value.length) {
      sendError.value = `还有 ${incomplete.value.length} 条没标完：`
        + incomplete.value.map(a => `${a.symbol} 缺${missingFields(a).join('、')}`).join('；')
      return false
    }
    sending.value = true
    sendError.value = null
    try {
      const res = await sendAnnotations(draftListId.value ?? current.value.list_id, draftList.value)
      lastSent.value = res
      clearDrafts()
      return true
    } catch (e: any) {
      sendError.value = String(e?.message ?? e)
      return false
    } finally {
      sending.value = false
    }
  }

  function setZoom(itemId: string | null) {
    zoomItemId.value = itemId
    if (itemId) highlightItemId.value = itemId
  }

  return {
    lists, current, loadError, groupKey, tagFilter, page, drafts, draftListId,
    sending, sendError, lastSent, zoomItemId, highlightItemId,
    isBlind, itemsById, currentGroup, groupItems, allTags, filteredItems, pageCount, pageItems,
    draftList, draftCount, incomplete, zoomItem,
    loadLists, openList, setGroup, setTagFilter, setPage, gotoItem,
    upsertAnnotation, deleteAnnotation, clearDrafts, send, setZoom,
  }
})
