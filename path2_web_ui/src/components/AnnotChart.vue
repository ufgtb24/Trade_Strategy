<template>
  <div class="annot-chart" :class="{ large, highlighted }" :data-item-id="item.item_id">
    <div class="head">
      <span class="sym">{{ item.symbol }}</span>
      <span v-if="item.sec_label" class="sec" :class="{ unknown: item.sec_known === false }"
            data-testid="sec-label">{{ item.sec_label }}</span>
      <template v-if="!hideOutcome">
        <span class="when" data-testid="decision">{{ cardMode ? '卡成立日' : '决策日' }} {{ item.t }}</span>
        <template v-if="!blind">
          <span v-if="item.metrics.rel != null" class="metric">相对涨幅 {{ fmtNum(item.metrics.rel) }}</span>
          <span v-if="item.metrics.rise != null" class="metric">涨幅 {{ fmtPct(item.metrics.rise) }}</span>
          <span v-if="item.metrics.max_jump != null" class="metric"
                title="从决策日往前一段到观察窗结束,单日收盘相对前一天的最大变化倍数(跌按倒数算),仅供核对数据时参考">
            最大单日跳变 ×{{ fmtNum(item.metrics.max_jump) }}</span>
          <span v-for="t in item.tags" :key="t" class="tag">{{ t }}</span>
        </template>
      </template>
      <span v-else class="hint-inline" data-testid="outcome-hidden">点了买点再显示清单的标记</span>
    </div>
    <div v-if="xcheckText" class="xcheck-warn" data-testid="xcheck-warn"
         title="生成清单时拿 Nasdaq 日线逐日比涨跌幅,单日倍数之比超出阈值就列在这里;确认有误请标「数据有误」">
      {{ xcheckText }}</div>
    <div v-if="cardMode" class="tools" data-testid="card-tools">
      <button type="button" class="tool verdict" data-testid="card-yes" :disabled="cardBusy"
              :aria-pressed="cardMark?.verdict === 'yes'" @click="onCardYes">是</button>
      <button type="button" class="tool verdict" data-testid="card-no" :disabled="cardBusy"
              :aria-pressed="noOpen || cardMark?.verdict === 'no'" @click="onCardNo">不是</button>
      <template v-if="noOpen">
        <input v-model="reason" class="note" type="text" placeholder="为什么不是（一句话）" maxlength="500"
               data-testid="card-reason" @keydown.enter="submitNo">
        <button type="button" class="tool" data-testid="card-no-submit" :disabled="cardBusy || !reason.trim()"
                @click="submitNo">记下</button>
      </template>
      <button type="button" class="tool" data-testid="tool-log" :aria-pressed="store.logScale"
              title="主图纵轴:对数坐标(按下)/ 线性坐标" @click="store.toggleLogScale()">
        {{ store.logScale ? '对数' : '线性' }}</button>
      <button v-if="!large" type="button" class="tool" data-testid="tool-zoom" title="也可以双击图放大"
              @click="openZoom">放大</button>
    </div>
    <div v-if="cardMode" class="hint-line" data-testid="card-hint">
      <template v-if="!cardMark">卡说这一天成立。是你说的那个形态吗？标完才露出成立日之后的走势</template>
      <template v-else>
        <b data-testid="card-verdict">已标：{{ cardMark.verdict === 'yes' ? '是' : '不是' }}</b>
        <template v-if="cardMark.verdict === 'no'">——{{ cardMark.reason }}</template>
        <span v-if="cardMark.n > 1" data-testid="card-changed">（看过走势后改过，第一下是「{{ cardMark.first_verdict === 'yes' ? '是' : '不是' }}」）</span>
        · 再改会记成看过走势之后改的
      </template>
    </div>
    <div v-if="!cardMode" class="tools">
      <button type="button" class="tool" :aria-pressed="mode === 'brush'" data-testid="tool-brush"
              @click="setMode('brush')">框选起止</button>
      <button type="button" class="tool" :aria-pressed="mode === 'buy'" data-testid="tool-buy"
              title="点一下设一个买点;按住 Shift 点再加一个,Shift 点已有的买点取消它"
              @click="setMode('buy')">点买点</button>
      <label class="radio"><input type="radio" :name="`lbl-${uid}`" value="positive"
             :checked="annotation?.label === 'positive'" data-testid="label-positive"
             @change="setLabel('positive')">{{ labelText('positive', kind) }}</label>
      <label class="radio"><input type="radio" :name="`lbl-${uid}`" value="negative"
             :checked="annotation?.label === 'negative'" data-testid="label-negative"
             @change="setLabel('negative')">{{ labelText('negative', kind) }}</label>
      <label class="radio"><input type="radio" :name="`lbl-${uid}`" value="data_error"
             :checked="annotation?.label === 'data_error'" data-testid="label-data-error"
             @change="setLabel('data_error')">数据有误</label>
      <input class="note" type="text" placeholder="备注" maxlength="500" data-testid="note"
             :value="annotation?.note ?? ''" @input="onNote">
      <button type="button" class="tool" data-testid="tool-log" :aria-pressed="store.logScale"
              title="主图纵轴:对数坐标(按下)/ 线性坐标" @click="store.toggleLogScale()">
        {{ store.logScale ? '对数' : '线性' }}</button>
      <button type="button" class="tool" data-testid="tool-clear" :disabled="!annotation"
              @click="store.deleteAnnotation(item.item_id)">清除</button>
      <button v-if="!large" type="button" class="tool" data-testid="tool-zoom" title="也可以双击图放大"
              @click="openZoom">放大</button>
    </div>
    <div v-if="!cardMode" class="hint-line" data-testid="brush-hint">框上更好，会话靠它找你说的峰（框选起止可以不填，「数据有误」除外）</div>
    <div v-if="annotation" class="ann-line" data-testid="ann-summary">
      <b>{{ labelText(annotation.label, kind) }}</b>
      起止 {{ annotation.range_start ?? '未框' }} → {{ annotation.range_end ?? '未框' }}
      · 买点 {{ buyText(annotation) }}
    </div>
    <div v-if="error" class="err">{{ error }}</div>
    <div ref="el" class="chart" :class="{ armed: mode !== 'none' }" />
  </div>
</template>

<script setup lang="ts">
/** 看图工作流里的一格 K 线(独立 ECharts 实例,K 线 + 成交量),也用于放大模态框(large)。
 *
 * 画两类东西:清单自带的标记(决策日 / 买入日竖线,上下线横线,最高点;盲看清单只画
 * 决策日和买入日),用户的标注(形态范围 markArea、买点 markPoint)。正例和反例靠文字
 * 标签与线型(实线 / 虚线)区分,不靠色相;判定文字随清单种类变(store.labelText)。
 * 用户色盲:K 线涨 = 白色填充深色边、跌 = 深色填充,量柱涨浅灰、跌深灰;主买点实心三角「★买点」,
 * 其他买点空心三角「买点2」「买点3」……;主图纵轴默认对数(store.logScale)。
 *
 * 大涨段清单点第一个买点之前不露结果:不画决策日、买入日、上下线、最高点,图头不显示决策日、
 * 涨幅、最大单日跳变、标签和跨源比对不一致的提示;初始横向窗口从图窗起点到决策日后随机 3~15 根(store.initialRightOf),
 * 用户把窗口右端拖过它就记成「点买点前看过后续」(store.markPeeked)。有了买点、且后端记上了露出结果
 * (store.isRevealConfirmed)之后照常显示,窗口不动;记不上就继续藏着。
 * 露出结果之后再改买点或「清除」,store 记成「看过结果后改过」(见 stores/workflow.ts 的改点痕迹)。
 *
 * 卡成立日清单(card_hits,只在调试模式下用):不框选、不点买点、不选判定,只有「是」「不是」两个按钮,「不是」
 * 要写一句为什么再点「记下」;后端记上之前只画到成立日(条目的 view_end),记上之后重取到 reveal_end,
 * 露出成立日之后的走势。成立日画一条竖线。标过的显示标的是什么,改过的注明第一下是什么。
 *
 * 两个互斥的工具开关:「框选起止」用 ECharts lineX brush + createBrushRequestHandler 把
 * (startIdx, endIdx) 换成日期写进草稿;「点买点」在图上点一下,把那根 K 线设成唯一的(主)买点,
 * 按住 Shift 点再加一个,Shift 点已有的买点取消它。
 *
 * 点买点模式下单击要等 CLICK_DELAY_MS:这段时间里没有双击才设买点。双击只管放大 / 退出放大,
 * 不会先设一个买点、把结果闪出来再还原。
 * 小图双击打开放大模态框,放大图里双击关掉它;放大图从小图当时的缩放窗口开始。
 * 小图和放大图都挂 inside dataZoom:滚轮横向缩放(ECharts 以鼠标处为不动点),按住拖动平移
 * (框选开着时拖动是框选);只在已取回的 K 线里缩放,不会多取数据。 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
import type { Annotation, AnnotationLabel, PricedBar as Bar, WorkflowItem } from '../types'
import { getWorkflowOhlc } from '../api'
import {
  CLICK_DELAY_MS, labelText, orderedBuyPoints, useWorkflowStore, type ZoomWindow,
} from '../stores/workflow'
import { createBrushRequestHandler } from './klineBrushHandler'

const props = withDefaults(defineProps<{
  item: WorkflowItem
  annotation?: Annotation | null
  large?: boolean
  /** 盲看清单:只画决策日和买入日。默认取当前清单的 kind。 */
  blind?: boolean | null
  highlighted?: boolean
}>(), { annotation: null, large: false, blind: null, highlighted: false })

const store = useWorkflowStore()
const blind = computed(() => props.blind ?? store.isBlind)
const kind = computed(() => store.listKind)
/** 卡成立日清单:只标「是 / 不是」;标完(后端记上)才露出成立日之后的走势 */
const cardMode = computed(() => kind.value === 'card_hits')
const cardMark = computed(() => (cardMode.value ? store.cardMarkOf(props.item.item_id) : null))
const cardRevealed = computed(() => !!cardMark.value)
const noOpen = ref(false)
const reason = ref('')
const cardBusy = ref(false)
const hasBuy = computed(() => (props.annotation?.buy_points?.length ?? 0) > 0)
/** 大涨段清单还没有买点,或露出结果还没被后端记上:不露结果 */
const hideOutcome = computed(() =>
  kind.value === 'bigmoves' && !(hasBuy.value && store.isRevealConfirmed(props.item.item_id)))
// 跨源比对不一致的段在图头列出那几天;盲看清单不显示(也不该带这份结果);大涨段点第一个买点前
// 也不显示——列出的日子和涨跌幅可能落在决策日之后,同样会露结果
const xcheckText = computed(() => {
  const x = props.item.xcheck
  if (blind.value || hideOutcome.value || !x || x.status !== 'mismatch') return ''
  const sgn = (r: number) => `${r >= 0 ? '+' : ''}${(r * 100).toFixed(1)}%`
  const days = x.mismatch_days.slice(0, 5)
    .map(d => `${d.date}（我们 ${sgn(d.r_ours)}，Nasdaq ${sgn(d.r_nasdaq)}）`).join('；')
  const more = x.mismatch_days.length > 5 ? `；等共 ${x.mismatch_days.length} 天` : ''
  return `两份数据不一致：${days}${more}`
})
const uid = Math.random().toString(36).slice(2, 9)
const el = ref<HTMLDivElement | null>(null)
const bars = ref<Bar[]>([])
const error = ref<string | null>(null)
const mode = ref<'none' | 'brush' | 'buy'>('none')
let chart: echarts.ECharts | null = null
let ro: ResizeObserver | null = null
/** 等着生效的那次单击(双击前浏览器先发两次 click;等 CLICK_DELAY_MS 没有双击才设买点) */
let clickTimer: ReturnType<typeof setTimeout> | null = null

function cancelPendingClick() {
  if (clickTimer != null) {
    clearTimeout(clickTimer)
    clickTimer = null
  }
}

const INK = '#0f172a'
const VOL_UP = '#cbd5e1'      // 涨:浅灰
const VOL_DOWN = '#475569'    // 跌:深灰
const BRUSH_OPTION = {
  xAxisIndex: 0,
  brushType: 'lineX' as const,
  brushMode: 'single' as const,
  brushStyle: { borderWidth: 1, color: 'rgba(15,23,42,0.10)', borderColor: INK },
  outOfBrush: { colorAlpha: 1 },
  removeOnClick: false,
  transformable: false,
}

function fmtNum(x: number | null | undefined) { return x == null ? '—' : x.toFixed(2) }
function fmtPct(x: number | null | undefined) { return x == null ? '—' : `${(x * 100).toFixed(1)}%` }
function fmtPrice(x: number) { return x >= 100 ? x.toFixed(1) : x >= 1 ? x.toFixed(2) : x.toPrecision(3) }
function fmtVol(x: number | null | undefined) {
  if (x == null) return '—'
  return x >= 1e8 ? `${(x / 1e8).toFixed(2)}亿` : x >= 1e4 ? `${(x / 1e4).toFixed(1)}万` : String(Math.round(x))
}
function buyText(a: Annotation) {
  const bps = orderedBuyPoints(a.buy_points)
  return bps.length ? bps.map(b => (b.primary ? '★' : '') + b.date).join('、') : '无'
}
/** 正例实线、反例虚线、数据有误点线(不靠色相区分) */
const BORDER_TYPE: Record<string, string> = { positive: 'solid', negative: 'dashed', data_error: 'dotted' }

const brushH = createBrushRequestHandler((s, e) => {
  const b = bars.value
  if (!b.length) return
  store.upsertAnnotation(props.item.item_id, { range_start: b[s].date, range_end: b[e].date })
  chart?.dispatchAction({ type: 'brush', areas: [] })      // 框选结果改由 markArea 画
}, () => bars.value.length)

function setMode(m: 'brush' | 'buy') {
  mode.value = mode.value === m ? 'none' : m
  chart?.dispatchAction({
    type: 'takeGlobalCursor', key: 'brush',
    brushOption: { brushType: mode.value === 'brush' ? 'lineX' : false, brushMode: 'single' },
  })
}

async function submitCard(verdict: 'yes' | 'no', why = '') {
  cardBusy.value = true
  const err = await store.markCard(props.item.item_id, verdict, why)
  cardBusy.value = false
  if (err) {
    error.value = err
    return
  }
  error.value = null
  noOpen.value = false
  reason.value = ''
}

function onCardYes() {
  noOpen.value = false
  if (cardMark.value?.verdict !== 'yes') void submitCard('yes')
}

function onCardNo() {
  noOpen.value = true
  reason.value = cardMark.value?.verdict === 'no' ? cardMark.value.reason : reason.value
}

function submitNo() {
  if (!reason.value.trim() || cardBusy.value) return
  void submitCard('no', reason.value)
}

function setLabel(l: AnnotationLabel) {
  store.upsertAnnotation(props.item.item_id, { label: l })
}

function onNote(e: Event) {
  const v = (e.target as HTMLInputElement).value
  if (v === (props.annotation?.note ?? '')) return
  store.upsertAnnotation(props.item.item_id, { note: v })
}

function onZrClick(e: any) {
  if (mode.value !== 'buy') return
  if ((e.event?.detail ?? 1) >= 2) {           // 双击的第二次 click:前一次也不算
    cancelPendingClick()
    return
  }
  if (!chart || !bars.value.length) return
  const px = [e.offsetX, e.offsetY]
  if (!chart.containPixel({ gridIndex: 0 }, px) && !chart.containPixel({ gridIndex: 1 }, px)) return
  // 两个 grid 左右边距相同,横坐标换算统一借主图 grid(按 xAxisIndex 换算拿不到值)
  const p = chart.convertFromPixel({ gridIndex: 0 }, px) as any
  const x = Array.isArray(p) ? p[0] : p
  if (x == null || Number.isNaN(Number(x))) return
  const idx = Math.min(bars.value.length - 1, Math.max(0, Math.round(Number(x))))
  const date = bars.value[idx].date
  const shift = !!e.event?.shiftKey
  cancelPendingClick()
  clickTimer = setTimeout(() => {
    clickTimer = null
    if (shift) store.toggleBuyPoint(props.item.item_id, date)
    else store.setBuyPoint(props.item.item_id, date)
  }, CLICK_DELAY_MS)
}

/** 决策日在已取回 K 线里的序号(没有正好那天就取之后第一根)。 */
function decisionIdx(): number {
  const t = props.item.marks?.decision ?? props.item.t
  const i = bars.value.findIndex(b => b.date >= t)
  return i < 0 ? bars.value.length - 1 : i
}

/** 初始右边界的 K 线序号:决策日之后 store 里记的那么多根。 */
function initialRightIdx(): number {
  return Math.min(bars.value.length - 1, decisionIdx() + store.initialRightOf(props.item.item_id))
}

/** 没有买点时,窗口右端拖过初始右边界 → 记成点买点前看过后续。 */
function onDataZoom() {
  if (!hideOutcome.value || !chart || !bars.value.length) return
  const dz = (chart.getOption() as any)?.dataZoom?.[0]
  if (!dz) return
  const end = dz.endValue != null ? Number(dz.endValue)
    : dz.end != null ? Math.round((Number(dz.end) / 100) * (bars.value.length - 1)) : null
  if (end != null && end > initialRightIdx()) store.markPeeked(props.item.item_id)
}

function onZrDblClick() {
  cancelPendingClick()                         // 双击带出的单击不设买点
  if (props.large) store.setZoom(null)
  else openZoom()
}

function currentZoom(): ZoomWindow | null {
  const dz = (chart?.getOption() as any)?.dataZoom?.[0]
  if (dz?.start != null && dz?.end != null) return { start: dz.start, end: dz.end }
  if (dz?.startValue != null && dz?.endValue != null) {
    return { startValue: dz.startValue, endValue: dz.endValue }
  }
  return null
}

/** 还没有买点的大涨段图:从图窗起点到初始右边界;其余为 null(全段)。 */
function initialWindow(): ZoomWindow | null {
  return hideOutcome.value && bars.value.length ? { startValue: 0, endValue: initialRightIdx() } : null
}

function openZoom() {
  store.setZoom(props.item.item_id, currentZoom())
}

/** zoom:横向缩放窗口(百分比或序号);null = 全段。 */
function buildOption(zoom: ZoomWindow | null) {
  const b = bars.value
  const dates = b.map(x => x.date)
  const has = new Set(dates)
  const byDate = new Map(b.map(x => [x.date, x]))
  const m = props.item.marks ?? {}
  const lines: any[] = []
  const showMarks = !hideOutcome.value
  if (showMarks && m.decision && has.has(m.decision)) {
    lines.push({ xAxis: m.decision, lineStyle: { type: 'solid', color: INK, width: 1 },
                 label: { formatter: cardMode.value ? '成立日' : '决策日', position: 'insideEndTop' } })
  }
  if (showMarks && m.entry && has.has(m.entry)) {
    lines.push({ xAxis: m.entry, lineStyle: { type: 'dotted', color: INK, width: 1 },
                 label: { formatter: '买入日', position: 'insideEndBottom' } })
  }
  const points: any[] = []
  if (!blind.value && showMarks) {
    if (m.up_line != null) {
      lines.push({ yAxis: m.up_line, lineStyle: { type: 'dashed', color: '#475569' },
                   label: { formatter: '上线', position: 'insideStartTop' } })
    }
    if (m.down_line != null) {
      lines.push({ yAxis: m.down_line, lineStyle: { type: 'dashed', color: '#475569' },
                   label: { formatter: '下线', position: 'insideStartBottom' } })
    }
    if (m.peak_date && byDate.has(m.peak_date)) {
      points.push({ name: '最高点', coord: [m.peak_date, byDate.get(m.peak_date)!.h],
                    symbol: 'pin', symbolSize: 28, itemStyle: { color: '#64748b' },
                    label: { formatter: '高', color: '#fff', fontSize: 10 } })
    }
  }
  const a = props.annotation
  const areas: any[] = []
  if (a?.range_start && a?.range_end) {
    areas.push([
      { xAxis: a.range_start, name: labelText(a.label, kind.value),
        itemStyle: { color: 'rgba(15,23,42,0.07)', borderColor: INK, borderWidth: 1.5,
                     borderType: BORDER_TYPE[a.label ?? ''] ?? 'solid' },
        label: { show: true, position: 'insideTop', color: INK, fontWeight: 'bold' } },
      { xAxis: a.range_end },
    ])
  }
  orderedBuyPoints(a?.buy_points).forEach((bp, k) => {
    if (!byDate.has(bp.date)) return
    const text = bp.primary ? '★买点' : `买点${k + 1}`
    points.push({ name: text, coord: [bp.date, byDate.get(bp.date)!.l],
                  symbol: 'triangle', symbolSize: 12, symbolOffset: [0, 10],
                  // 主买点实心、其他空心(不靠色相)
                  itemStyle: bp.primary ? { color: INK }
                    : { color: '#ffffff', borderColor: INK, borderWidth: 1.5 },
                  label: { show: true, position: 'bottom', formatter: text, color: INK } })
  })
  const range = zoom == null ? { start: 0, end: 100 }
    : zoom.start != null ? { start: zoom.start, end: zoom.end }
      : { startValue: zoom.startValue, endValue: zoom.endValue }
  return {
    animation: false,
    grid: [
      { left: 48, right: 28, top: 10, bottom: '30%' },
      { left: 48, right: 28, top: '74%', bottom: 22 },
    ],
    xAxis: [
      { type: 'category', data: dates, gridIndex: 0, boundaryGap: true,
        axisLabel: { show: false }, axisTick: { show: false } },
      { type: 'category', data: dates, gridIndex: 1, boundaryGap: true,
        axisLabel: { fontSize: 10 } },
    ],
    yAxis: [
      store.logScale
        ? { type: 'log', gridIndex: 0, splitNumber: 4, axisLabel: { fontSize: 10 },
            min: (v: any) => v.min * 0.97, max: (v: any) => v.max * 1.03 }
        : { type: 'value', scale: true, gridIndex: 0, splitNumber: 4, axisLabel: { fontSize: 10 } },
      { gridIndex: 1, splitNumber: 2, axisLabel: { show: false }, splitLine: { show: false } },
    ],
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
    // 紧凑提示:两行小字,贴在光标对侧的上角,不挡光标附近的 K 线
    tooltip: {
      trigger: 'axis', axisPointer: { type: 'cross' }, confine: true,
      padding: [3, 6], textStyle: { fontSize: 11, lineHeight: 15 },
      position: (pt: number[], _p: any, _d: any, _r: any, size: any) =>
        pt[0] < size.viewSize[0] / 2 ? { top: 4, right: 32 } : { top: 4, left: 52 },
      formatter: (ps: any) => {
        const i = Array.isArray(ps) ? ps[0]?.dataIndex : ps?.dataIndex
        const x = i != null ? b[i] : undefined
        if (!x) return ''
        const prev = i > 0 ? b[i - 1].c : null
        const chg = prev ? ` ${x.c >= prev ? '+' : ''}${((x.c / prev - 1) * 100).toFixed(1)}%` : ''
        return `${x.date}　收 ${fmtPrice(x.c)}${chg}　量 ${fmtVol(x.v)}<br/>`
          + `开 ${fmtPrice(x.o)}　高 ${fmtPrice(x.h)}　低 ${fmtPrice(x.l)}`
      },
    },
    brush: BRUSH_OPTION,
    toolbox: { show: false },
    dataZoom: [{ type: 'inside', xAxisIndex: [0, 1], ...range,
                 zoomOnMouseWheel: true, moveOnMouseMove: true, moveOnMouseWheel: false, minValueSpan: 10 }],
    series: [
      {
        type: 'candlestick', name: 'K线', xAxisIndex: 0, yAxisIndex: 0, barWidth: '70%',
        data: b.map(x => [x.o, x.c, x.l, x.h]),
        // 涨 = 白色填充 + 深色边,跌 = 深色填充(不靠红绿色相)
        itemStyle: { color: '#ffffff', color0: INK, borderColor: INK, borderColor0: INK },
        markLine: { symbol: 'none', silent: true, data: lines },
        markArea: { silent: true, data: areas },
        markPoint: { silent: true, data: points },
      },
      {
        type: 'bar', name: '成交量', xAxisIndex: 1, yAxisIndex: 1,
        data: b.map(x => ({ value: x.v, itemStyle: { color: x.c >= x.o ? VOL_UP : VOL_DOWN } })),
      },
    ],
  }
}

/** keepZoom:改标注触发的重画保留当前缩放窗口;重取数据时小图回到初始窗口(还没买点的大涨段图
 *  到初始右边界,其余全段),放大图从小图当时的窗口开始。 */
function render(keepZoom = true) {
  if (!chart || !bars.value.length) return
  const zoom = keepZoom ? currentZoom()
    : (props.large ? store.zoomWindow : null) ?? initialWindow()
  chart.setOption(buildOption(zoom) as any, { notMerge: true })
  if (mode.value === 'brush') {
    chart.dispatchAction({ type: 'takeGlobalCursor', key: 'brush',
                           brushOption: { brushType: 'lineX', brushMode: 'single' } })
  }
}

/** 取 K 线的终点:卡成立日清单标完了到 reveal_end,其余都到条目的 view_end。 */
function loadEnd(): string {
  return cardMode.value && cardRevealed.value ? (props.item.reveal_end ?? props.item.view_end) : props.item.view_end
}

async function load() {
  try {
    const o = await getWorkflowOhlc(props.item.symbol, props.item.view_start, loadEnd())
    bars.value = o.bars
    error.value = o.bars.length ? null : '这段区间没有行情'
  } catch (e: any) {
    error.value = String(e?.message ?? e)
  }
  render(false)
}

onMounted(() => {
  if (!el.value) return
  chart = echarts.init(el.value)
  chart.on('brushselected', brushH.onBrushSelected)
  chart.on('brushEnd', brushH.onBrushEnd)
  chart.on('datazoom', onDataZoom)
  chart.getZr().on('click', onZrClick)
  chart.getZr().on('dblclick', onZrDblClick)
  if (typeof ResizeObserver !== 'undefined') {
    ro = new ResizeObserver(() => chart?.resize())
    ro.observe(el.value)
  }
  void load()
})

watch(() => props.item.item_id, () => { mode.value = 'none'; noOpen.value = false; reason.value = ''; void load() })
watch(cardRevealed, (now, before) => { if (now && !before) void load() })
watch(() => [props.annotation, blind.value, hideOutcome.value, store.logScale], () => render(),
      { deep: true })

onBeforeUnmount(() => {
  cancelPendingClick()
  ro?.disconnect()
  chart?.dispose()
  chart = null
})
</script>

<style scoped>
.annot-chart { display: flex; flex-direction: column; border: 1px solid #cbd5e1; border-radius: 4px;
               padding: 4px 6px; min-width: 0; background: #fff; }
.annot-chart.highlighted { outline: 3px solid #0f172a; outline-offset: -1px; }
.head { display: flex; flex-wrap: wrap; gap: 6px; align-items: baseline; font-size: 12px; }
.sym { font-weight: 700; font-size: 14px; }
.when, .metric { color: #334155; }
.sec { border: 1px solid #94a3b8; border-radius: 3px; padding: 0 4px; font-size: 11px; color: #334155; }
.sec.unknown { font-weight: 700; border: 2px solid #0f172a; color: #0f172a; }
.hint-inline { color: #475569; font-size: 11px; }
.hint-line { font-size: 11px; color: #475569; margin-bottom: 2px; }
.tag { border: 1px solid #94a3b8; border-radius: 3px; padding: 0 4px; font-size: 11px; color: #334155; }
.xcheck-warn { font-size: 12px; font-weight: 700; color: #0f172a; border-left: 3px solid #0f172a;
               padding-left: 4px; margin: 2px 0; }
.tools { display: flex; flex-wrap: wrap; gap: 4px; align-items: center; margin: 3px 0; font-size: 12px; }
.tool { font-size: 12px; padding: 1px 6px; border: 1px solid #94a3b8; background: #fff; border-radius: 3px;
        cursor: pointer; }
.tool[aria-pressed="true"] { background: #0f172a; color: #fff; border-color: #0f172a; }
.tool:disabled { opacity: 0.5; cursor: default; }
.tool.verdict { font-weight: 700; padding: 1px 12px; }
.radio { display: inline-flex; align-items: center; gap: 2px; }
.note { flex: 1 1 100px; min-width: 80px; font-size: 12px; padding: 1px 4px; }
.ann-line { font-size: 11px; color: #334155; }
.err { color: #b91c1c; font-size: 12px; }
.chart { width: 100%; height: max(220px, calc(50vh - 160px)); }
.chart.armed { cursor: crosshair; }
.large .chart { height: 72vh; }
</style>
