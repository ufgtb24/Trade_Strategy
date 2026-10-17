/** 看图工作流模式的状态:清单目录与当前清单、分组 / 标签筛选 / 翻页、标注草稿、发送状态、放大中的 item。
 *
 * 标注草稿只放内存(Map<item_id, Annotation>,每个 item 最多一条),不写 localStorage:
 * 未发送就丢,只靠 WorkflowView 的离开提醒兜底。草稿属于产生它的那份清单(draftListId),
 * 切到别的清单时要先确认丢弃。
 *
 * 一张图可以点多个买点:普通点击 setBuyPoint 只留这一个(主买点),Shift + 点击 toggleBuyPoint
 * 没有就加、有就去掉;去掉主买点时剩下的里最早加入的那个变成主买点。
 *
 * 大涨段清单点第一个买点之前不露结果(AnnotChart):每张图的初始右边界(决策日之后随机
 * 3~15 根,initialRight)每次打开清单随机一次,小图和放大图共用;没有买点时把窗口右端拖过它,
 * 这张图就记进 peeked,之后草稿的 peeked_before_buy = true。对数 / 线性坐标开关也在这里
 * (默认对数,本次页面会话内有效,不写浏览器存储)。 */
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import type {
  Annotation, AnnotationBatchResult, AnnotationLabel, BuyPoint, WorkflowItem, WorkflowList,
  WorkflowListKind, WorkflowListMeta,
} from '../types'
import { listWorkflowLists, loadWorkflowList, sendAnnotations } from '../api'

export const PAGE_SIZE = 6

/** 横向缩放窗口:dataZoom 的 start / end 百分比(0-100);或按 K 线序号的 startValue / endValue。 */
export interface ZoomWindow { start?: number, end?: number, startValue?: number, endValue?: number }

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

/** 初始右边界:决策日之后随机几根(待验证)。 */
export const INITIAL_RIGHT_MIN = 3
export const INITIAL_RIGHT_MAX = 15
export function randomRight(rand: () => number = Math.random): number {
  return INITIAL_RIGHT_MIN + Math.floor(rand() * (INITIAL_RIGHT_MAX - INITIAL_RIGHT_MIN + 1))
}

/** 一条草稿缺什么(空数组 = 可以发送):标签必填;「数据有误」要起止;正例要至少一个买点。 */
export function missingFields(a: Annotation): string[] {
  const out: string[] = []
  if (!a.label) out.push('标签')
  if (a.label === 'data_error' && (!a.range_start || !a.range_end)) out.push('起止')
  if (a.label === 'positive' && !(a.buy_points?.length)) out.push('买点')
  return out
}

/** 判定的显示文字随清单种类变(存的值不变):大涨段里反例叫「像但不买」;
 *  盲看里正 / 反例叫「是我的意思 / 不是我的意思」;普通对照照旧。 */
export function labelText(l: AnnotationLabel | null | undefined, kind?: WorkflowListKind | null): string {
  if (l === 'data_error') return '数据有误'
  if (!l) return '未选标签'
  if (kind === 'contrast_blind') return l === 'positive' ? '是我的意思' : '不是我的意思'
  if (kind === 'bigmoves') return l === 'positive' ? '正例' : '像但不买'
  return l === 'positive' ? '正例' : '反例'
}

/** 主买点在前,其余按加入顺序。 */
export function orderedBuyPoints(bps: BuyPoint[] | null | undefined): BuyPoint[] {
  const list = bps ?? []
  return [...list.filter(b => b.primary), ...list.filter(b => !b.primary)]
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
  /** 放大图打开时的横向缩放窗口(dataZoom 百分比),取自小图当时的窗口;null = 全段。 */
  const zoomWindow = ref<ZoomWindow | null>(null)
  const highlightItemId = ref<string | null>(null)
  /** 每张图点买点前的初始右边界:决策日之后第几根(打开清单时随机一次,小图和放大图共用) */
  const initialRight = ref(new Map<string, number>())
  /** 点买点前把窗口往右展开过初始右边界的图 */
  const peeked = ref(new Set<string>())
  /** 主图纵轴用对数坐标(默认);只在本次页面会话内有效 */
  const logScale = ref(true)

  const isBlind = computed(() => current.value?.kind === 'contrast_blind')
  const listKind = computed<WorkflowListKind | null>(() => current.value?.kind ?? null)
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
    initialRight.value = new Map(current.value.items.map(it => [it.item_id, randomRight()]))
    peeked.value = new Set()
    setZoom(null)
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
    if (opts.zoom) setZoom(itemId)
  }

  function upsertAnnotation(itemId: string, patch: Partial<Annotation>) {
    const item = itemsById.value.get(itemId)
    if (!item || !current.value) return
    const prev = drafts.value.get(itemId) ?? {
      ann_id: newId(), item_id: itemId, symbol: item.symbol,
      range_start: null, range_end: null, buy_points: [], label: null, note: '',
      peeked_before_buy: false, updated_at: '',
    }
    drafts.value.set(itemId, { ...prev, ...patch, item_id: itemId, symbol: item.symbol,
                               peeked_before_buy: prev.peeked_before_buy || peeked.value.has(itemId),
                               updated_at: nowLocal() })
    draftListId.value = current.value.list_id
    lastSent.value = null
  }

  /** 普通点击:只留这一个买点(主买点)。 */
  function setBuyPoint(itemId: string, date: string) {
    upsertAnnotation(itemId, { buy_points: [{ date, primary: true }] })
  }

  /** Shift + 点击:没有就加、有就去掉;去掉主买点时剩下的里最早加入的变成主买点。 */
  function toggleBuyPoint(itemId: string, date: string) {
    const cur = drafts.value.get(itemId)?.buy_points ?? []
    let next: BuyPoint[]
    if (cur.some(b => b.date === date)) {
      next = cur.filter(b => b.date !== date).map(b => ({ ...b }))
      if (next.length && !next.some(b => b.primary)) next[0].primary = true
    } else {
      next = [...cur.map(b => ({ ...b })), { date, primary: cur.length === 0 }]
    }
    upsertAnnotation(itemId, { buy_points: next })
  }

  /** 点买点前往右展开看过后续:记下来;已有草稿的立刻写 peeked_before_buy。 */
  function markPeeked(itemId: string) {
    if (peeked.value.has(itemId)) return
    peeked.value.add(itemId)
    const d = drafts.value.get(itemId)
    if (d) drafts.value.set(itemId, { ...d, peeked_before_buy: true })
  }

  /** 这张图的初始右边界(决策日之后第几根);还没有就随机一个记下(直接设 current 的场合)。 */
  function initialRightOf(itemId: string): number {
    let k = initialRight.value.get(itemId)
    if (k == null) {
      k = randomRight()
      initialRight.value.set(itemId, k)
    }
    return k
  }

  function toggleLogScale() {
    logScale.value = !logScale.value
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

  /** 打开(itemId)或关闭(null)放大框;win 是小图当时的缩放窗口,放大图从它开始。 */
  function setZoom(itemId: string | null, win: ZoomWindow | null = null) {
    zoomItemId.value = itemId
    zoomWindow.value = itemId ? win : null
    if (itemId) highlightItemId.value = itemId
  }

  return {
    lists, current, loadError, groupKey, tagFilter, page, drafts, draftListId,
    sending, sendError, lastSent, zoomItemId, zoomWindow, highlightItemId,
    initialRight, peeked, logScale,
    isBlind, listKind, itemsById, currentGroup, groupItems, allTags, filteredItems, pageCount,
    pageItems, draftList, draftCount, incomplete, zoomItem,
    loadLists, openList, setGroup, setTagFilter, setPage, gotoItem,
    upsertAnnotation, setBuyPoint, toggleBuyPoint, markPeeked, initialRightOf, toggleLogScale,
    deleteAnnotation, clearDrafts, send, setZoom,
  }
})
