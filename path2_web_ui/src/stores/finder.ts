/**
 * 标注三档左栏找图清单(components/FinderList.vue)的状态:当前页签、大涨段清单、这次抽过的图。
 *
 * - 页签:rally / random / charts,打开、刷新页面时落在 rally;切到 scan 档再切回来还是原来那页(左栏只藏不拆)。
 * - 大涨段清单:页面一打开就向后端要一次(后端首次整池算一遍约半分钟,之后读缓存),拿到后留在这里。
 * - 这次抽过的图:顶栏 random 每抽一张就按先后加一行(TopBar.vue 调 addDraw),点回去、挨个翻都不改它。
 *
 * 全部只在页面内存里:不写文件、不写浏览器存储,刷新后回到 rally 页、random 页清空。看过什么一律不记。
 */
import { defineStore } from 'pinia'
import { ref, shallowRef } from 'vue'
import { getRally } from '../api'
import type { RallyItem, RandomWindow } from '../types'

export const FINDER_TABS = ['rally', 'random', 'charts'] as const
export type FinderTab = typeof FINDER_TABS[number]
export type RallyStatus = 'idle' | 'loading' | 'load_failed' | 'empty' | 'ready'

export const useFinderStore = defineStore('finder', () => {
  const tab = ref<FinderTab>('rally')
  const rally = shallowRef<RallyItem[]>([])
  const rallyStatus = ref<RallyStatus>('idle')
  const draws = shallowRef<RandomWindow[]>([])     // 这次抽过的图,按抽的先后

  function setTab(t: FinderTab): void { tab.value = t }

  /** 取大涨段清单;已经在取或取到了就什么都不做,取失败了可以再取。 */
  async function loadRally(): Promise<void> {
    if (rallyStatus.value === 'loading' || rallyStatus.value === 'ready' || rallyStatus.value === 'empty') return
    rallyStatus.value = 'loading'
    try {
      rally.value = await getRally()
      rallyStatus.value = rally.value.length ? 'ready' : 'empty'
    } catch {
      rallyStatus.value = 'load_failed'
    }
  }

  /** 顶栏 random 抽到一张:排到最后。 */
  function addDraw(w: RandomWindow): void {
    draws.value = [...draws.value, { symbol: w.symbol, start: w.start, end: w.end }]
  }

  return { tab, rally, rallyStatus, draws, setTab, loadRally, addDraw }
})
