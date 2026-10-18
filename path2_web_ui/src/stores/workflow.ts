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
 * 这张图就记进 peeked,之后草稿的 peeked_before_buy = true,并经后端记一条 peek(后端收标注时据此校正)。
 * 改点痕迹(只在大涨段清单记):买点从无到有那一刻结果就露出来了,把当时的买点记进 revealed,草稿的
 * first_buy_points 就是它;之后买点有任何改动(换点、加点、去点),或者「清除」这张图的标注,都记进
 * changedAfterReveal(草稿 changed_after_reveal = true);清除或去掉全部买点时也记进 peeked。
 * peeked / revealed / changedAfterReveal 按「清单 + 条目」记,整个页面会话内不清空(重新打开同一份
 * 清单、切走再切回都还在),草稿被清除后痕迹也留着,下次再标这张图照样带上。
 * 改点痕迹最终以后端为准:结果露出的那一刻经后端记一条 reveal(带当时的买点),后端收标注时按这张图
 * 最早那次 reveal 校正,刷新页面、换天都洗不掉。reveal 写成功之后才真正显示结果(revealConfirmed,
 * AnnotChart 据此决定藏不藏);写失败就撤回 revealed、结果继续藏着并在 viewError 提示,下次改买点时重试。
 * 单张图的看过事件(放大看了 zoom、点了买点或选了判定 annotate、露出结果 reveal、往右拖看后续 peek)
 * 经后端记进看过记录,每张图每种事件在一次打开清单里只记一次;发送标注前先等这些请求落地
 * (reveal 要在标注之前记上)。
 * 对数 / 线性坐标开关也在这里(默认对数,本次页面会话内有效,不写浏览器存储)。
 *
 * 卡成立日清单(card_hits,只在调试模式下用)不走草稿和发送:每张图点「是」或「不是」(「不是」要写一句为什么)
 * 立刻经后端记下(markCard),后端记上之后才放行到成立日之后的走势(cardMarks 里有这张图,AnnotChart 据此取
 * 到 reveal_end 的 K 线)。打开清单时后端把每张图现在的标记带在 card_marks 里。可以改,改的那一下后端记成
 * 看过走势之后的。 */
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import type {
  Annotation, AnnotationBatchResult, AnnotationLabel, BuyPoint, CardMark, WorkflowItem, WorkflowList,
  WorkflowListKind, WorkflowListMeta, WorkflowStateInfo, ChartViewEvent,
} from '../types'
import {
  getWorkflowState, listWorkflowLists, loadWorkflowList, postCardMark, recordChartView, sendAnnotations,
} from '../api'

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

/** 点买点模式下单击等这么久(毫秒)没有双击才设买点:双击只管放大,不先设一个买点、闪一下结果 */
export const CLICK_DELAY_MS = 250

/** 两组买点是否相同(只看日期与主买点,不看顺序)。 */
export function sameBuyPoints(a: BuyPoint[], b: BuyPoint[]): boolean {
  if (a.length !== b.length) return false
  const key = (x: BuyPoint) => `${x.date}|${x.primary ? 1 : 0}`
  const ka = new Set(a.map(key))
  return b.every(x => ka.has(key(x)))
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
  /** 点买点前把窗口往右展开过初始右边界的图(键:清单::条目,页面会话内不清空) */
  const peeked = ref(new Set<string>())
  /** 大涨段:第一次露出结果时的买点(键同上) */
  const revealed = ref(new Map<string, BuyPoint[]>())
  /** 大涨段:后端已确认记下露出结果的图(键同上);确认之前结果继续藏着 */
  const revealConfirmed = ref(new Set<string>())
  /** 大涨段:露出结果后买点改过或清除过的图(键同上) */
  const changedAfterReveal = ref(new Set<string>())
  /** 后端状态根信息(来自环境变量时界面显示提示条);取不到为 null */
  const stateInfo = ref<WorkflowStateInfo | null>(null)
  /** 本次打开清单里已经记过的单张图事件(键:条目::事件) */
  const viewEventsSent = ref(new Set<string>())
  /** 单张图事件记不进去时的说明 */
  const viewError = ref<string | null>(null)
  /** 还没落地的单张图事件请求;发送标注前先等它们 */
  let pendingViews: Promise<unknown>[] = []
  /** 主图纵轴用对数坐标(默认);只在本次页面会话内有效 */
  const logScale = ref(true)
  /** 卡成立日清单:每张图现在的标记(后端记上的才在这里) */
  const cardMarks = ref(new Map<string, CardMark>())

  const isBlind = computed(() => current.value?.kind === 'contrast_blind')
  const isCardHits = computed(() => current.value?.kind === 'card_hits')
  const cardMarkedCount = computed(() => cardMarks.value.size)
  /** 还没标、但现在标就会记成揭开后才标(不进统计)的张数 */
  const cardLateCount = computed(() => Object.keys(current.value?.card_late ?? {})
    .filter(id => !cardMarks.value.has(id)).length)
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
    try {
      stateInfo.value = await getWorkflowState()
    } catch {
      stateInfo.value = null
    }
  }

  /** 痕迹的键:当前清单 + 条目 */
  function trailKey(itemId: string): string {
    return `${current.value?.list_id ?? ''}::${itemId}`
  }

  function isPeeked(itemId: string): boolean {
    return peeked.value.has(trailKey(itemId))
  }

  /** 这张图的露出结果后端已经记上了(大涨段据此才显示结果)。 */
  function isRevealConfirmed(itemId: string): boolean {
    return revealConfirmed.value.has(trailKey(itemId))
  }

  /** 大涨段结果此刻要露出:先经后端记 reveal,写成功才算露出;写失败撤回 revealed(草稿的第一次买点
   *  一并清掉),结果继续藏着并提示,下次改买点时重试。 */
  function sendReveal(itemId: string, bps: BuyPoint[]) {
    if (!current.value) return
    const key = trailKey(itemId)
    const p = recordChartView(current.value.list_id, itemId, 'reveal', bps)
      .then(() => {
        revealConfirmed.value.add(key)
        viewError.value = null
      })
      .catch((e: any) => {
        revealed.value.delete(key)
        const d = drafts.value.get(itemId)
        if (d) drafts.value.set(itemId, { ...d, first_buy_points: null })
        viewError.value = `露出结果没记上(${itemId}),结果继续藏着;再点一次买点重试:`
          + String(e?.message ?? e)
      })
    pendingViews.push(p)
  }

  /** 记一条单张图事件;同一张图同一种事件在本次打开清单里只记一次。记不进去时写 viewError,
   *  并允许下次再记。 */
  function noteChartView(itemId: string, event: ChartViewEvent, buyPoints?: BuyPoint[]) {
    if (!current.value) return
    const key = `${itemId}::${event}`
    if (viewEventsSent.value.has(key)) return
    viewEventsSent.value.add(key)
    const listId = current.value.list_id
    const p = recordChartView(listId, itemId, event, buyPoints)
      .then(() => { viewError.value = null })
      .catch((e: any) => {
        viewEventsSent.value.delete(key)
        viewError.value = `看过记录没记上(${itemId}):${String(e?.message ?? e)}`
      })
    pendingViews.push(p)
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
    cardMarks.value = new Map(Object.entries(current.value.card_marks ?? {}))
    viewEventsSent.value = new Set()
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
      peeked_before_buy: false, first_buy_points: null, changed_after_reveal: false, updated_at: '',
    }
    const key = trailKey(itemId)
    if (listKind.value === 'bigmoves') {
      const before = prev.buy_points ?? []
      const after = patch.buy_points ?? before
      if (!revealed.value.has(key)) {
        if (after.length) {                                   // 结果此刻露出(后端记上后才显示)
          revealed.value.set(key, after.map(b => ({ ...b })))
          sendReveal(itemId, after.map(b => ({ ...b })))
        }
      } else if (!sameBuyPoints(before, after)) {
        changedAfterReveal.value.add(key)                                      // 看过结果后改过
        if (!after.length) peeked.value.add(key)
      }
    }
    const first = revealed.value.get(key)
    drafts.value.set(itemId, { ...prev, ...patch, item_id: itemId, symbol: item.symbol,
                               peeked_before_buy: prev.peeked_before_buy || peeked.value.has(key),
                               first_buy_points: first ? first.map(b => ({ ...b })) : null,
                               changed_after_reveal: changedAfterReveal.value.has(key),
                               updated_at: nowLocal() })
    if ('buy_points' in patch || 'label' in patch) noteChartView(itemId, 'annotate')
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

  /** 点买点前往右展开看过后续:记下来并经后端记一条 peek;已有草稿的立刻写 peeked_before_buy。 */
  function markPeeked(itemId: string) {
    const key = trailKey(itemId)
    if (peeked.value.has(key)) return
    peeked.value.add(key)
    noteChartView(itemId, 'peek')
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

  /** 「清除」:删掉这张图的草稿。大涨段里结果已经露出过的,记成看过结果后改过、看过后续
   *  (痕迹留在 store 里,下次再标这张图照样带上)。 */
  function deleteAnnotation(itemId: string) {
    const key = trailKey(itemId)
    if (revealed.value.has(key)) {
      changedAfterReveal.value.add(key)
      peeked.value.add(key)
    }
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
      await Promise.allSettled(pendingViews.splice(0))     // reveal 等事件先落地
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

  /** 卡成立日清单:这张图标「是 / 不是」。后端记上之后才算标了(此后放行成立日之后的走势);
   *  返回 null = 记上了,否则是记不上的说明。 */
  async function markCard(itemId: string, verdict: 'yes' | 'no', reason = ''): Promise<string | null> {
    if (!current.value || !isCardHits.value) return '当前不是卡成立日清单'
    if (verdict === 'no' && !reason.trim()) return '标「不是」要写一句为什么'
    try {
      const res = await postCardMark(current.value.list_id, itemId, verdict, verdict === 'no' ? reason.trim() : '')
      cardMarks.value.set(itemId, res.card_mark)
      return null
    } catch (e: any) {
      return `没记上:${String(e?.message ?? e)}`
    }
  }

  function cardMarkOf(itemId: string): CardMark | null {
    return cardMarks.value.get(itemId) ?? null
  }

  /** 打开(itemId)或关闭(null)放大框;win 是小图当时的缩放窗口,放大图从它开始。 */
  function setZoom(itemId: string | null, win: ZoomWindow | null = null) {
    zoomItemId.value = itemId
    zoomWindow.value = itemId ? win : null
    if (itemId) {
      highlightItemId.value = itemId
      noteChartView(itemId, 'zoom')
    }
  }

  return {
    lists, current, loadError, groupKey, tagFilter, page, drafts, draftListId,
    sending, sendError, lastSent, zoomItemId, zoomWindow, highlightItemId,
    initialRight, peeked, revealed, revealConfirmed, changedAfterReveal, stateInfo, viewEventsSent, viewError,
    logScale, cardMarks,
    isBlind, isCardHits, cardMarkedCount, cardLateCount, listKind, itemsById, currentGroup, groupItems, allTags, filteredItems, pageCount,
    pageItems, draftList, draftCount, incomplete, zoomItem,
    loadLists, openList, setGroup, setTagFilter, setPage, gotoItem,
    upsertAnnotation, setBuyPoint, toggleBuyPoint, markPeeked, isPeeked, isRevealConfirmed, noteChartView,
    initialRightOf,
    toggleLogScale,
    deleteAnnotation, clearDrafts, send, setZoom, markCard, cardMarkOf,
  }
})
