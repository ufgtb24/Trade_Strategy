/**
 * 直达链接的格式与解析(spec 5.3「链接」)。会话在对话里给用户一个链接,用户点开就落到那张图上去标或者看。
 * 链接写在页面地址的 # 后面,键值照后端路由的查询串写法(`?symbol=…&start=…`):
 *
 *   <前端地址>/#symbol=<代码>&date=<YYYY-MM-DD>   股票 + 日期:打开那只股票,图窗停在那天附近,落在 annotate
 *   <前端地址>/#sample=<样本编号>                  样本编号:打开样本所在的那张图,并选中它
 *
 * 前端地址是 http://localhost:<configs/path2_web.yaml 的 frontend_port>。代码照顶栏输入的规则去空白、转大写;
 * 样本编号就是标注文件里样本的 id(如 s-pc-12)。
 *
 * 日期晚于训练段末日 TRAIN_END 的,一律截到 TRAIN_END(数据墙,spec 4.1)。图窗按日历日取:那天往前约半年、
 * 往后约两个月(往前多留,是因为样本的依据都在样本日之前)。
 *
 * 这里只是纯函数;跟着链接打开图在 stores/directLinks.ts。
 */
import type { ViewWindow } from '../types'
import { resolveSymbolInput } from './symbolInput'
import { shiftDays } from './viewWindow'

/** 训练段末日:和后端 path2_web/data.py 的 TRAIN_END 同值(单测核对两边一致)。 */
export const TRAIN_END = '2025-12-31'
/** 「股票 + 日期」的图窗:那天往前、往后各留的日历日数。 */
const LINK_DAYS_BEFORE = 180
const LINK_DAYS_AFTER = 60

export type DirectLink =
  | { kind: 'chart'; symbol: string; date: string }
  | { kind: 'sample'; id: string }
  | { kind: 'bad'; raw: string }

const DATE = /^\d{4}-\d{2}-\d{2}$/

/** 合法的日历日(YYYY-MM-DD,且这一天存在)。 */
function isDate(s: string): boolean {
  if (!DATE.test(s)) return false
  const t = new Date(`${s}T00:00:00Z`)
  return !Number.isNaN(t.getTime()) && t.toISOString().slice(0, 10) === s
}

/**
 * 页面地址的 # 部分 → 链接。没有 # 或 # 后面是空的 → null(不是链接);认不出的写法 → bad。
 * 认得的写法:恰好 symbol 与 date 两个键,或恰好 sample 一个键,值都不能为空。
 */
export function parseLink(hash: string): DirectLink | null {
  const raw = hash.startsWith('#') ? hash.slice(1) : hash
  if (!raw.trim()) return null
  const p = new URLSearchParams(raw)
  const keys = [...p.keys()].sort().join(',')
  if (keys === 'date,symbol') {
    const sym = resolveSymbolInput(p.get('symbol')!, null)
    const date = p.get('date')!.trim()
    if (sym.kind === 'ok' && isDate(date)) return { kind: 'chart', symbol: sym.symbol, date }
  } else if (keys === 'sample') {
    const id = p.get('sample')!.trim()
    if (id) return { kind: 'sample', id }
  }
  return { kind: 'bad', raw }
}

/** 「股票 + 日期」链接的图窗:晚于 TRAIN_END 的日期先截到 TRAIN_END,再往前、往后各留一段。 */
export function chartLinkWindow(date: string): ViewWindow {
  const d = date > TRAIN_END ? TRAIN_END : date
  return { start: shiftDays(d, -LINK_DAYS_BEFORE), end: shiftDays(d, LINK_DAYS_AFTER) }
}
