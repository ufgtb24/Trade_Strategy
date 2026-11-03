/**
 * 跟着直达链接走(spec 5.3「链接」;链接格式见 annotate/directLinks.ts)。
 *
 * follow(hash):跟着页面地址 # 后面的链接走。页面打开时和地址的 # 部分变了时(App.vue)各跟一次;跟完把
 * # 部分从地址里去掉,同一个链接在这一页再点一次照样会跟,刷新也不会把图拉回链接那里。链接一律落在 annotate。
 * - 股票 + 日期:代码先对股票列表(训练段副本里有的股票)核一遍,在就打开那只股票,图窗停在那天附近;
 *   不在就记下 not_found、不动当前的图。股票列表没拿到时不拦,交给后端判(同顶栏 symbol 输入)。
 * - 样本编号:等标注读完,按编号打开样本所在的图并选中它(标注 store 的 openSample);编号不存在 → 记下 not_found。
 *   标注读不到时不记:提示条已经写了标注的状态。
 * - 认不出的写法 → 记下 bad_url。
 * 记下的原因(problem)显示在 annotate 的提示条上,一直到点 ok,或下一个链接跟成。
 */
import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import { getSymbols } from '../api'
import { chartLinkWindow, parseLink, type DirectLink } from '../annotate/directLinks'
import { resolveSymbolInput } from '../annotate/symbolInput'
import { useAnnotationStore } from './annotation'
import { useViewStore } from './view'

/** 链接没跟成的原因:股票代码或样本编号不存在,或认不出的写法(raw 是 # 后面的原文)。 */
export type LinkProblem =
  | { code: 'not_found'; kind: 'symbol' | 'sample'; id: string }
  | { code: 'bad_url'; raw: string }

/** 股票列表;拿不到为 null。 */
async function symbolSet(): Promise<ReadonlySet<string> | null> {
  try { return new Set(await getSymbols()) } catch { return null }
}

export const useDirectLinkStore = defineStore('directLinks', () => {
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

  /** 跟着链接打开图;没跟成返回原因(标注读不到时为 null,见模块说明)。 */
  async function open(link: DirectLink): Promise<LinkProblem | null> {
    if (link.kind === 'bad') return { code: 'bad_url', raw: link.raw }
    if (link.kind === 'chart') {
      const r = resolveSymbolInput(link.symbol, await symbolSet())
      if (r.kind !== 'ok') return { code: 'not_found', kind: 'symbol', id: link.symbol }
      useViewStore().openSymbol(r.symbol, chartLinkWindow(link.date))
      return null
    }
    await annotationsSettled()
    const ann = useAnnotationStore()
    if (ann.status !== 'ready' || (await ann.openSample(link.id))) return null
    return { code: 'not_found', kind: 'sample', id: link.id }
  }

  async function follow(hash: string): Promise<void> {
    const link = parseLink(hash)
    if (!link) return
    history.replaceState(null, '', location.pathname + location.search)
    problem.value = null
    problem.value = await open(link)
    useViewStore().enterAnnotate()      // 跟成时打开图已经落在 annotate;没跟成也落在这里,提示条在 annotate 下
  }

  return { problem, follow }
})
