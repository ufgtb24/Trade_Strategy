<template>
  <div class="annot-chart" :class="{ large, highlighted }" :data-item-id="item.item_id">
    <div class="head">
      <span class="sym">{{ item.symbol }}</span>
      <span class="when">决策日 {{ item.t }}</span>
      <template v-if="!blind">
        <span v-if="item.metrics.rel != null" class="metric">相对涨幅 {{ fmtNum(item.metrics.rel) }}</span>
        <span v-if="item.metrics.rise != null" class="metric">涨幅 {{ fmtPct(item.metrics.rise) }}</span>
        <span v-if="item.metrics.max_jump != null" class="metric"
              title="从决策日往前一段到观察窗结束,单日收盘相对前一天的最大变化倍数(跌按倒数算),仅供核对数据时参考">
          最大单日跳变 ×{{ fmtNum(item.metrics.max_jump) }}</span>
        <span v-for="t in item.tags" :key="t" class="tag">{{ t }}</span>
        <a class="tv" :href="tvUrl" target="_blank" rel="noopener noreferrer"
           data-testid="tv-link">在 TradingView 打开</a>
      </template>
    </div>
    <div class="tools">
      <button type="button" class="tool" :aria-pressed="mode === 'brush'" data-testid="tool-brush"
              @click="setMode('brush')">框选起止</button>
      <button type="button" class="tool" :aria-pressed="mode === 'buy'" data-testid="tool-buy"
              @click="setMode('buy')">点买点</button>
      <label class="radio"><input type="radio" :name="`lbl-${uid}`" value="positive"
             :checked="annotation?.label === 'positive'" data-testid="label-positive"
             @change="setLabel('positive')">正例</label>
      <label class="radio"><input type="radio" :name="`lbl-${uid}`" value="negative"
             :checked="annotation?.label === 'negative'" data-testid="label-negative"
             @change="setLabel('negative')">反例</label>
      <label class="radio"><input type="radio" :name="`lbl-${uid}`" value="data_error"
             :checked="annotation?.label === 'data_error'" data-testid="label-data-error"
             @change="setLabel('data_error')">数据有误</label>
      <input class="note" type="text" placeholder="备注" maxlength="500" data-testid="note"
             :value="annotation?.note ?? ''" @input="onNote">
      <button type="button" class="tool" data-testid="tool-clear" :disabled="!annotation"
              @click="store.deleteAnnotation(item.item_id)">清除</button>
      <button v-if="!large" type="button" class="tool" data-testid="tool-zoom"
              @click="store.setZoom(item.item_id)">放大</button>
    </div>
    <div v-if="annotation" class="ann-line" data-testid="ann-summary">
      <b>{{ labelText(annotation.label) }}</b>
      起止 {{ annotation.range_start ?? '未框' }} → {{ annotation.range_end ?? '未框' }}
      · 买点 {{ annotation.buy_date ?? '无' }}
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
 * 标签与线型(实线 / 虚线)区分,不靠色相。
 *
 * 两个互斥的工具开关:「框选起止」用 ECharts lineX brush + createBrushRequestHandler 把
 * (startIdx, endIdx) 换成日期写进草稿;「点买点」在图上点一下,把那根 K 线的日期写成买点。 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
import type { Annotation, AnnotationLabel, Bar, WorkflowItem } from '../types'
import { getWorkflowOhlc } from '../api'
import { tradingViewUrl, useWorkflowStore } from '../stores/workflow'
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
// 盲看清单不给链接:TradingView 会露出决策日之后的走势
const tvUrl = computed(() => tradingViewUrl(props.item.symbol, props.item.exchange))
const uid = Math.random().toString(36).slice(2, 9)
const el = ref<HTMLDivElement | null>(null)
const bars = ref<Bar[]>([])
const error = ref<string | null>(null)
const mode = ref<'none' | 'brush' | 'buy'>('none')
let chart: echarts.ECharts | null = null
let ro: ResizeObserver | null = null

const INK = '#0f172a'
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
function labelText(l: AnnotationLabel | null | undefined) {
  return l === 'positive' ? '正例' : l === 'negative' ? '反例'
    : l === 'data_error' ? '数据有误' : '未选标签'
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

function setLabel(l: AnnotationLabel) {
  store.upsertAnnotation(props.item.item_id, { label: l })
}

function onNote(e: Event) {
  const v = (e.target as HTMLInputElement).value
  if (v === (props.annotation?.note ?? '')) return
  store.upsertAnnotation(props.item.item_id, { note: v })
}

function onZrClick(e: any) {
  if (mode.value !== 'buy' || !chart || !bars.value.length) return
  const px = [e.offsetX, e.offsetY]
  if (!chart.containPixel({ gridIndex: 0 }, px) && !chart.containPixel({ gridIndex: 1 }, px)) return
  // 两个 grid 左右边距相同,横坐标换算统一借主图 grid(按 xAxisIndex 换算拿不到值)
  const p = chart.convertFromPixel({ gridIndex: 0 }, px) as any
  const x = Array.isArray(p) ? p[0] : p
  if (x == null || Number.isNaN(Number(x))) return
  const idx = Math.min(bars.value.length - 1, Math.max(0, Math.round(Number(x))))
  store.upsertAnnotation(props.item.item_id, { buy_date: bars.value[idx].date })
}

function buildOption() {
  const b = bars.value
  const dates = b.map(x => x.date)
  const has = new Set(dates)
  const byDate = new Map(b.map(x => [x.date, x]))
  const m = props.item.marks ?? {}
  const lines: any[] = []
  if (m.decision && has.has(m.decision)) {
    lines.push({ xAxis: m.decision, lineStyle: { type: 'solid', color: INK, width: 1 },
                 label: { formatter: '决策日', position: 'insideEndTop' } })
  }
  if (m.entry && has.has(m.entry)) {
    lines.push({ xAxis: m.entry, lineStyle: { type: 'dotted', color: INK, width: 1 },
                 label: { formatter: '买入日', position: 'insideEndBottom' } })
  }
  const points: any[] = []
  if (!blind.value) {
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
      { xAxis: a.range_start, name: labelText(a.label),
        itemStyle: { color: 'rgba(15,23,42,0.07)', borderColor: INK, borderWidth: 1.5,
                     borderType: BORDER_TYPE[a.label ?? ''] ?? 'solid' },
        label: { show: true, position: 'insideTop', color: INK, fontWeight: 'bold' } },
      { xAxis: a.range_end },
    ])
  }
  if (a?.buy_date && byDate.has(a.buy_date)) {
    points.push({ name: '买点', coord: [a.buy_date, byDate.get(a.buy_date)!.l],
                  symbol: 'triangle', symbolSize: 12, symbolOffset: [0, 10],
                  itemStyle: { color: INK },
                  label: { show: true, position: 'bottom', formatter: '买点', color: INK } })
  }
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
      { scale: true, gridIndex: 0, splitNumber: 4, axisLabel: { fontSize: 10 } },
      { gridIndex: 1, splitNumber: 2, axisLabel: { show: false }, splitLine: { show: false } },
    ],
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
    tooltip: { trigger: 'axis', axisPointer: { type: 'cross' }, confine: true },
    brush: BRUSH_OPTION,
    toolbox: { show: false },
    series: [
      {
        type: 'candlestick', name: 'K线', xAxisIndex: 0, yAxisIndex: 0, barWidth: '70%',
        data: b.map(x => [x.o, x.c, x.l, x.h]),
        itemStyle: { color: '#47b262', color0: '#eb5454', borderColor: '#47b262',
                     borderColor0: '#eb5454' },
        markLine: { symbol: 'none', silent: true, data: lines },
        markArea: { silent: true, data: areas },
        markPoint: { silent: true, data: points },
      },
      {
        type: 'bar', name: '成交量', xAxisIndex: 1, yAxisIndex: 1,
        data: b.map(x => x.v), itemStyle: { color: '#94a3b8' },
      },
    ],
  }
}

function render() {
  if (!chart || !bars.value.length) return
  chart.setOption(buildOption() as any, { notMerge: true })
  if (mode.value === 'brush') {
    chart.dispatchAction({ type: 'takeGlobalCursor', key: 'brush',
                           brushOption: { brushType: 'lineX', brushMode: 'single' } })
  }
}

async function load() {
  try {
    const o = await getWorkflowOhlc(props.item.symbol, props.item.view_start, props.item.view_end)
    bars.value = o.bars
    error.value = o.bars.length ? null : '这段区间没有行情'
  } catch (e: any) {
    error.value = String(e?.message ?? e)
  }
  render()
}

onMounted(() => {
  if (!el.value) return
  chart = echarts.init(el.value)
  chart.on('brushselected', brushH.onBrushSelected)
  chart.on('brushEnd', brushH.onBrushEnd)
  chart.getZr().on('click', onZrClick)
  if (typeof ResizeObserver !== 'undefined') {
    ro = new ResizeObserver(() => chart?.resize())
    ro.observe(el.value)
  }
  void load()
})

watch(() => props.item.item_id, () => { mode.value = 'none'; void load() })
watch(() => [props.annotation, blind.value], render, { deep: true })

onBeforeUnmount(() => {
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
.tag { border: 1px solid #94a3b8; border-radius: 3px; padding: 0 4px; font-size: 11px; color: #334155; }
.tv { font-size: 12px; color: #0f172a; text-decoration: underline; margin-left: auto; }
.tools { display: flex; flex-wrap: wrap; gap: 4px; align-items: center; margin: 3px 0; font-size: 12px; }
.tool { font-size: 12px; padding: 1px 6px; border: 1px solid #94a3b8; background: #fff; border-radius: 3px;
        cursor: pointer; }
.tool[aria-pressed="true"] { background: #0f172a; color: #fff; border-color: #0f172a; }
.tool:disabled { opacity: 0.5; cursor: default; }
.radio { display: inline-flex; align-items: center; gap: 2px; }
.note { flex: 1 1 100px; min-width: 80px; font-size: 12px; padding: 1px 4px; }
.ann-line { font-size: 11px; color: #334155; }
.err { color: #b91c1c; font-size: 12px; }
.chart { width: 100%; height: max(220px, calc(50vh - 160px)); }
.chart.armed { cursor: crosshair; }
.large .chart { height: 72vh; }
</style>
