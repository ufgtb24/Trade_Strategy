/**
 * 直达链接与「按编号找样本」(spec 5.3「链接」;链接格式见 annotate/links.ts)。
 *
 * - follow(hash):跟着页面地址 # 后面的链接走。页面打开时和地址的 # 部分变了时(App.vue)各跟一次;跟完把
 *   # 部分从地址里去掉,同一个链接在这一页再点一次照样会跟,刷新也不会把图拉回链接那里。
 *   - 股票 + 日期:打开那只股票,图窗停在那天附近,落在 annotate。代码不存在时和顶栏输入一样由换图报 not_found。
 *   - 样本编号:等标注读完,按编号找样本,打开它所在的图并选中它。编号不存在 → problem 记下,提示条一直显示到点 ok。
 *   - 认不出的写法 → problem 记下(bad_link)。
 *   链接一律落在 annotate,提示条也只在 annotate 下显示。
 * - openSample(id):按编号找样本,打开它所在的图(图窗停在样本的跨度上)并选中它;找不到返回 false。
 *   样本链接、pattern 页的样本卡,以及第二段的题目链接(#q=)都用这一处。
 */
import { defineStore } from 'pinia'
import { nextTick, ref, watch } from 'vue'
import { findSample } from '../annotate/model'
import { sampleWindow } from '../annotate/grouping'
import { chartLinkWindow, parseLink } from '../annotate/links'
import { useAnnotationStore } from './annotation'
import { useViewStore } from './view'

/** 链接没跟成的原因:样本编号不存在,或认不出的写法(raw 是 # 后面的原文)。 */
export type LinkProblem =
  | { code: 'not_found'; sample: string }
  | { code: 'bad_link'; raw: string }

export const useLinkStore = defineStore('links', () => {
  const problem = ref<LinkProblem | null>(null)

  /** 等标注读完(读成功或读失败都算完)。 */
  function annotationsSettled(): Promise<void> {
    const ann = useAnnotationStore()
    const done = () => ann.status !== 'idle' && ann.status !== 'loading'
    if (done()) return Promise.resolve()
    return new Promise(resolve => {
      const stop = watch(() => ann.status, () => {
        if (!done()) return
        stop()
        resolve()
      })
    })
  }

  /** 按编号找样本,打开它所在的图并选中它。keepTab:侧栏留在当前页(从 pattern 页的样本卡打开时)。 */
  async function openSample(id: string, opts: { keepTab?: boolean } = {}): Promise<boolean> {
    const ann = useAnnotationStore()
    const hit = ann.state ? findSample(ann.state, id) : null
    if (!hit) return false
    useViewStore().openSymbol(hit.chart.symbol, sampleWindow(hit))
    await nextTick()               // 换图会清掉选中(KlineChart 的 symbol 监听),等它跑完再选中
    ann.selectSample(id, opts)
    return true
  }

  async function follow(hash: string): Promise<void> {
    const link = parseLink(hash)
    if (!link) return
    history.replaceState(null, '', location.pathname + location.search)
    const view = useViewStore()
    problem.value = null
    if (link.kind === 'chart') {
      view.openSymbol(link.symbol, chartLinkWindow(link.date).window)
      return
    }
    view.mode = 'annotate'
    if (link.kind === 'bad') { problem.value = { code: 'bad_link', raw: link.raw }; return }
    await annotationsSettled()
    if (useAnnotationStore().status !== 'ready') return     // 标注读不到:提示条已经写了 annotations 的状态
    if (!(await openSample(link.id))) problem.value = { code: 'not_found', sample: link.id }
  }

  return { problem, openSample, follow }
})
