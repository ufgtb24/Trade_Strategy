<template>
  <div class="kline-wrap" :style="wrapCssVars">
    <div ref="el" class="kline" />
    <CandidateStatusBar :matches="effectiveAnalysis?.matches ?? []" />
  </div>
</template>

<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref, watch, computed } from 'vue'
import * as echarts from 'echarts'
import { storeToRefs } from 'pinia'
import { useViewStore } from '../stores/view'
import { usePanelsStore } from '../stores/panels'
import { getOhlc } from '../api'
import { buildKlineOption, buildVolumeSeriesAndYAxis } from '../render/chart'
import { ctrlState } from '../render/ctrlState'
import { bandKeyOf, roleOfEventByBand, resolveTooltipData, windowOf, formatForwardReturn } from '../render/visible'
import type { Bar } from '../types'
import { handleChartClick } from './KlineChart'
import CandidateStatusBar from './CandidateStatusBar.vue'

const view = useViewStore()
const { symbol, effectiveAnalysis, roleColors, roleVisible, level, tagMap, isolated, effectivePattern, effectiveScan, scanFile, selectedEventId, diag, activePatternId, selectedMatchId, candidateMatchIds, highlightedEventIds, pendingDisambigEventId } = storeToRefs(view)
const panels = usePanelsStore()
const { showSlider } = storeToRefs(panels)
const el = ref<HTMLElement | null>(null)
const bars = ref<Bar[]>([])

// grid1 顶部对齐 CSS 变量(与 chart.ts grid[1].top 完全同步):
//   sliderShow=true  → '68%'
//   sliderShow=false → '76%'
const wrapCssVars = computed(() => ({ '--grid1-top-px': showSlider.value ? '68%' : '76%' }))
let chart: echarts.ECharts | null = null
let ro: ResizeObserver | null = null
let unsubCtrl: (() => void) | null = null

async function reloadBars() {
  if (!symbol.value || !scanFile.value) { bars.value = []; return }
  const { start, end } = windowOf(effectiveScan.value ?? scanFile.value.scan)   // 缓冲窗(旧文件回退严格窗)
  try {
    bars.value = (await getOhlc(symbol.value, start, end)).bars
  } catch { bars.value = [] }
}

// 严格窗边界(有缓冲时才有):bars 中第一根 >= start_date 与最后一根 <= end_date(ISO 串比较)
function strictWindowIdx(): { startIdx: number; endIdx: number } | null {
  const s = scanFile.value?.scan
  if (!s || !s.win_start || s.win_start === s.start_date) return null
  const startIdx = bars.value.findIndex((b) => b.date >= s.start_date)
  let endIdx = -1
  for (let i = bars.value.length - 1; i >= 0; i--) {
    if (bars.value[i].date <= s.end_date) { endIdx = i; break }
  }
  return startIdx >= 0 && endIdx >= 0 ? { startIdx, endIdx } : null
}

// match 归属带 tooltip 行:ret_{N}: +x.x%(无 label 数据 → null 不显示)
function matchLabel(matchId: string): string | null {
  const m = effectiveAnalysis.value?.matches.find((mm) => mm.event_id === matchId)
  if (!m || m.forward_return === undefined) return null
  return `ret_${(effectiveScan.value ?? scanFile.value?.scan)?.label_horizon}: ${formatForwardReturn(m.forward_return)}`
}

function render(forceResetZoom = false) {
  if (!chart || !effectiveAnalysis.value || !effectivePattern.value) return
  // 非 reset 路径:保留用户当前 zoom(读 chart 现态作 override);
  // 换股(forceResetZoom=true)走 strictWindow 默认,新 bars 配新初始窗
  let zoomOverride: { start: number; end: number } | null = null
  if (!forceResetZoom) {
    const cur = (chart.getOption() as any)?.dataZoom?.[0]
    if (cur && typeof cur.start === 'number' && typeof cur.end === 'number') {
      zoomOverride = { start: cur.start, end: cur.end }
    }
  }
  const tagList = tagMap.value.tagList
  const opt = buildKlineOption(
    bars.value, effectiveAnalysis.value.events, effectiveAnalysis.value.matches,
    {
      topology: effectivePattern.value.topology,
      isolatedNodeIds: isolated.value,
      tagList,
      level: level.value,
      roleColors: roleColors.value,
      eventTier: (e) => view.eventTier(e),
      roleOfEventByBand: (e) => roleOfEventByBand(e, tagMap.value.tagToNodes, tagList),
      bandKeyOf: (e) => bandKeyOf(e, tagList),
      roleVisible: roleVisible.value,
      tagToNodes: tagMap.value.tagToNodes,
      selectedEventId: selectedEventId.value,
      tooltipResolver: (id: string) => resolveTooltipData(id, diag.value, effectiveAnalysis.value?.events ?? [], bars.value),
      strictWindow: strictWindowIdx(),
      matchLabel,
      sliderShow: showSlider.value,
      zoomOverride,
      endRole: scanFile.value?.per_pattern[activePatternId.value!]?.end_role ?? undefined,
      selectedMatchId: selectedMatchId.value,
      candidateMatchIds: candidateMatchIds.value,
      highlightedEventIds: highlightedEventIds.value,
      pendingDisambigEventId: pendingDisambigEventId.value,
    },
  )
  chart.setOption(opt as any, true)
}

function onKeyDown(e: KeyboardEvent) {
  if (e.key !== 'Escape') return
  const t = e.target as HTMLElement | null
  if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return
  view.clearCandidates()
  view.clearHighlight()
  view.selectMatch(null)
  view.selectEvent(null)
}

onMounted(() => {
  window.addEventListener('keydown', onKeyDown)
  chart = echarts.init(el.value!)
  chart.on('click', (p: any) => {
    handleChartClick(p, effectiveAnalysis.value?.matches ?? [], view)
  })
  // ZRender 级别 click:捕获空白画布点击(ECharts chart.on('click') 仅对 series item 触发)
  // e.target 非 undefined → series item 已由 chart.on('click') 处理,此处跳过防双触
  chart.getZr().on('click', (e: any) => {
    if (!e.target) {
      handleChartClick(null, effectiveAnalysis.value?.matches ?? [], view)
    }
  })
  // 容器尺寸跟随:grid 布局稳定/侧栏 mount 后 canvas resize 到正确宽度,
  // 防 ECharts 早期 init 取全宽后撑宽 grid 列、把渐进披露侧栏挤出视口。
  ro = new ResizeObserver(() => chart?.resize())
  ro.observe(el.value!)
  // dev-only e2e hook:暴露 view store + echarts 实例,供 playwright canvas 精确 click/hover
  if ((import.meta as any).env?.DEV) {
    ;(window as any).__e2e = { view, chart: () => chart }
  }

  // Ctrl 切换 → axisPointer 颜色/snap/type
  // type: 普通 'line'(只竖线) ↔ Ctrl 'cross'(竖+横)
  unsubCtrl = ctrlState.subscribe((pressed) => {
    chart?.setOption({
      tooltip: {
        axisPointer: {
          type: pressed ? 'cross' : 'line',
          lineStyle: { color: pressed ? '#FF6600' : '#0088CC' },
          snap: !pressed,
        },
      },
    })
  })

  // 鼠标移动 → 维护 ctrlState.mouseY
  // 注意 ECharts API: convertFromPixel({yAxisIndex:0}, [x,y]) 返回 null (finder/input 签名错配),
  // 必须用 {gridIndex:0} 或 {seriesIndex:0} 接受 [x,y] 返回 [xData, yData],
  // 或 {yAxisIndex:0} 接受 scalar 返回 scalar yData。这里选 gridIndex(grid0=价格区)。
  chart.getZr().on('mousemove', (e: { offsetX: number; offsetY: number }) => {
    if (!chart) return
    const arr = chart.convertFromPixel({ gridIndex: 0 }, [e.offsetX, e.offsetY])
    if (Array.isArray(arr) && typeof arr[1] === 'number') {
      ctrlState.setMouseY(arr[1])
    }
  })

  // 用户 zoom/pan → 重算 volume scale + yAxis[0]
  chart.on('datazoom', () => {
    if (!chart) return
    const dz = (chart.getOption() as any).dataZoom?.[0]
    if (!dz) return
    const start = typeof dz.start === 'number' ? dz.start : 0
    const end = typeof dz.end === 'number' ? dz.end : 100
    const N = bars.value.length
    const visStart = Math.max(0, Math.round((start / 100) * N))
    const visEnd = Math.min(N - 1, Math.round((end / 100) * N) - 1)
    if (visEnd < visStart) return
    const { volSeries, yAxisOverride } = buildVolumeSeriesAndYAxis(bars.value, visStart, visEnd)
    chart.setOption({
      series: [{ name: 'volume', data: volSeries.data }],
      yAxis: [{ min: yAxisOverride.min, max: yAxisOverride.max }, {}, {}],
    })
  })

  // 横线锁 close — updateAxisPointer: 非 Ctrl 时锁 y 轴线到当前 bar.close(markLine 方案)
  // 注意: setOption 的 series.name 必须 === 'kline'(与 chart.ts 一致), 否则 ECharts
  // 按 index merge 会覆盖 candlestick 的 name 字段,导致 tooltip formatter 找不到 kline param。
  chart.on('updateAxisPointer', (e: any) => {
    if (!chart) return
    if (ctrlState.isPressed()) {
      // Ctrl 模式: 清掉锁 close 的 markLine, 让 ECharts cross axisPointer 自带横线跟鼠标
      chart.setOption({
        series: [{ name: 'kline', markLine: { data: [] } }],
      })
      return
    }
    const dataIdx = e?.dataIndex ?? e?.seriesAxesInfo?.[0]?.dataIndex
    if (typeof dataIdx !== 'number') return
    const b = bars.value[dataIdx]
    if (!b) return
    chart.setOption({
      series: [{ name: 'kline', markLine: { silent: true, symbol: 'none', lineStyle: { color: '#0088CC', type: 'dashed', width: 1 }, data: [{ yAxis: b.c }] } }],
    })
  })

  void reloadBars().then(() => render(true))
})
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeyDown)
  unsubCtrl?.()
  chart?.getZr().off('mousemove')
  chart?.getZr().off('click')
  chart?.off('datazoom')
  chart?.off('updateAxisPointer')
  ro?.disconnect()
  chart?.dispose()
})

// 换股 = 唯一应 reset zoom 的事件(bars 数组全换,旧 zoom% 应用到新股语义错乱)
watch(symbol, () => void reloadBars().then(() => render(true)))
// 同股重 load / preview 切换(scanFile/effectiveScan):bars 可能重抓,但 zoom% 保留对用户更友好
watch([scanFile, effectiveScan], () => void reloadBars().then(() => render(false)))
// 上层视觉/过滤/UI/高亮(level/role/showSlider 等):bars 不变,zoom 必须保留
watch([effectiveAnalysis, roleVisible, level, roleColors, selectedEventId, diag, showSlider,
       selectedMatchId, candidateMatchIds, highlightedEventIds, pendingDisambigEventId],
      () => render(false), { deep: true })
</script>

<style scoped>
/* min-width:0 让 grid 列能收缩到比 canvas 窄(打破 canvas 撑列死锁);overflow 裁剪 init 瞬时溢出。
   position:relative 提供 CandidateStatusBar 的 absolute 定位坐标系 → banner 贴 grid1 顶部。 */
.kline-wrap { position: relative; width: 100%; height: 100%; min-width: 0; }
.kline { width: 100%; height: 100%; min-width: 0; min-height: 0; overflow: hidden; }
</style>
