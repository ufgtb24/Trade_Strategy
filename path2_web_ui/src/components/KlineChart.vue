<template>
  <div class="kline-wrap-v2" ref="wrapEl">
    <div ref="mainEl" class="main-chart" style="flex: 1" />
    <ResizableDivider @drag="onDrag" @dragend="onDragEnd" @dblclick="onDblclick" />
    <CandidateStatusBar :matches="effectiveAnalysis?.matches ?? []" />
    <div class="sub-outer" :style="{ height: effectiveSubH + 'px' }" ref="subOuterEl">
      <div class="band-zoom-controls" @wheel.stop>
        <button type="button" class="band-zoom-btn"
                :disabled="bandZoomFactor <= BAND_ZOOM_MIN"
                title="缩小 marker 竖直尺寸(−0.2)"
                @click="onBandZoomMinus">−</button>
        <span class="band-zoom-readout">{{ formatFactor(bandZoomFactor) }}</span>
        <button type="button" class="band-zoom-btn"
                :disabled="bandZoomFactor >= factorCap"
                title="放大 marker 竖直尺寸(+0.2)"
                @click="onBandZoomPlus">+</button>
        <button type="button" class="band-zoom-btn band-zoom-reset"
                :disabled="bandZoomFactor === BAND_ZOOM_MIN"
                title="复位到 1.0×"
                @click="onBandZoomReset">↺</button>
      </div>
      <div ref="subInnerEl" class="sub-inner" :style="{ height: subCanvasH + 'px' }" />
    </div>
    <CrosshairOverlay :x="overlayX" />
  </div>
</template>

<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref, watch, computed } from 'vue'
import * as echarts from 'echarts'
import { storeToRefs } from 'pinia'
import { useViewStore } from '../stores/view'
import { usePanelsStore } from '../stores/panels'
import { getOhlc } from '../api'
import { computeEventData, buildMainOption, buildSubOption, buildVolumeSeriesAndYAxis } from '../render/chart'
import {
  computeSubGeometry, composeEffectiveSubH, SUB_CANVAS_MIN_H, MIN_SUB_H,
  MAIN_MIN_H, BAND_ZOOM_MIN, BAND_ZOOM_MAX, LS_KEY_BAND_ZOOM,
  BAND_ZOOM_STEP_BUTTON, BAND_ZOOM_STEP_WHEEL,
} from '../render/subGeometry'
import { ctrlState } from '../render/ctrlState'
import { bandKeyOf, roleOfEventByBand, resolveTooltipData, windowOf, formatForwardReturn, subBandTagList } from '../render/visible'
import type { Bar } from '../types'
import { handleChartClick } from './KlineChart'
import CandidateStatusBar from './CandidateStatusBar.vue'
import ResizableDivider from './ResizableDivider.vue'
import CrosshairOverlay from './CrosshairOverlay.vue'

const view = useViewStore()
const { symbol, effectiveAnalysis, roleColors, roleVisible, level, tagMap, isolated,
        effectivePattern, effectiveScan, scanFile, selectedEventId, diag,
        activePatternId, selectedMatchId, candidateMatchIds,
        highlightedEventIds, pendingDisambigEventId } = storeToRefs(view)
const panels = usePanelsStore()
const { showSlider, subHeightOffset } = storeToRefs(panels)

const wrapEl = ref<HTMLElement | null>(null)
const mainEl = ref<HTMLElement | null>(null)
const subOuterEl = ref<HTMLElement | null>(null)
const subInnerEl = ref<HTMLElement | null>(null)
const bars = ref<Bar[]>([])
// CrosshairOverlay(DOM 一根到底竖线)的 x 坐标 + main-chart 相对 kline-wrap 的偏移(修 S3)
const overlayX = ref<number | null>(null)
const mainCanvasOffsetX = ref<number>(0)

// ── band zoom factor(spec 2026-07-03)─────────────────────────────────
// 从 localStorage 初始化,parse 失败 / NaN / out-of-range 回 default 1.0
function loadBandZoom(): number {
  const raw = parseFloat(localStorage.getItem(LS_KEY_BAND_ZOOM) ?? '')
  if (!Number.isFinite(raw) || raw < BAND_ZOOM_MIN || raw > BAND_ZOOM_MAX) return 1.0
  return raw
}
const bandZoomFactor = ref<number>(loadBandZoom())
const containerH = ref<number>(0)   // wrapEl 高度,ResizeObserver 更新

// 计算副图 canvas 需要的高度
const subCanvasH = ref<number>(SUB_CANVAS_MIN_H)  // 首帧兜底

// 副图容器高度合成:fit(offset=null)贴合内容;负 offset = drag 藏掉的像素数,
// zoom 只改 subCanvasH → 分界线随 zoom 移动而隐藏量守恒。
// spec: 2026-07-03-subchart-boundary-model-design.md §1/§2
const effectiveSubH = computed(() => composeEffectiveSubH(subCanvasH.value, subHeightOffset.value))

let chartMain: echarts.ECharts | null = null
let chartSub: echarts.ECharts | null = null
let roMain: ResizeObserver | null = null
let roSub: ResizeObserver | null = null
let roWrap: ResizeObserver | null = null
let unsubCtrl: (() => void) | null = null
let lastMarkLineKey: string | null = null

async function reloadBars() {
  if (!symbol.value || !scanFile.value) { bars.value = []; return }
  const { start, end } = windowOf(effectiveScan.value ?? scanFile.value.scan)
  try {
    bars.value = (await getOhlc(symbol.value, start, end)).bars
  } catch { bars.value = [] }
}

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

function matchLabel(matchId: string): string | null {
  const m = effectiveAnalysis.value?.matches.find((mm) => mm.event_id === matchId)
  if (!m || m.forward_return === undefined) return null
  return `ret_${(effectiveScan.value ?? scanFile.value?.scan)?.label_horizon}: ${formatForwardReturn(m.forward_return)}`
}

// 副图 subGeometry 派生(由 bracket lane 数 + 各 band 内 lane 数决定)
// zoomOverride: 显式传入时优先(factorCap 计算需要 z=1 时的 naturalSubH,不受当前 bandZoomFactor 影响)
function deriveSubGeometry(zoomOverride?: number) {
  const z = zoomOverride ?? bandZoomFactor.value
  if (!effectiveAnalysis.value || !tagMap.value.tagList.length) {
    return computeSubGeometry({ bracketLaneCount: 0, bandLaneCounts: [] }, z)
  }
  // 需要 bundle 里 bracketData / intervalData / pointData 分组
  const params = buildRenderInput()
  const bundle = computeEventData(bars.value, effectiveAnalysis.value.events, effectiveAnalysis.value.matches, params)
  const bracketLaneCount = bundle.bracketData.length === 0
    ? 0
    : (Math.max(0, ...bundle.bracketData.map((d: any) => d.value[2])) + 1)
  // 分轨只含 time 轴 tag,与 computeEventData 的 band 索引空间(subTags)对齐
  const subTags = subBandTagList(tagMap.value.tagList, effectivePattern.value!.topology)
  const bandLaneCounts: number[] = subTags.map((_, band) => {
    let maxLane = 0
    for (const d of bundle.intervalData) {
      if (d.value[3] === band && d.value[2] + 1 > maxLane) maxLane = d.value[2] + 1
    }
    // points lane 恒 0 → +1
    const hasPoint = bundle.pointData.some((d: any) => d.value[2] === band)
    return Math.max(maxLane, hasPoint ? 1 : 0)
  })
  return computeSubGeometry({ bracketLaneCount, bandLaneCounts }, z)
}

// factorCap(spec §6.1):naturalSubH_at_1(bandZoomFactor=1 时的副图 canvas 高)决定 zoom 上限。
// 若 wrap 剩余空间(containerH - MAIN_MIN_H)不足容纳 naturalSubH_at_1 → factorCap = 1.0(zoom 不可用)。
// 封顶对象维持内容高度口径(boundary-model spec §4:不随 offset 放宽)。
const factorCap = computed<number>(() => {
  const wrapH = containerH.value
  if (wrapH <= 0) return BAND_ZOOM_MAX    // 未 mount 时给最大;mount 后由 RO 更新收紧
  const naturalSubH = deriveSubGeometry(1.0).subCanvasH
  const maxSubH = wrapH - MAIN_MIN_H
  if (naturalSubH <= 0 || naturalSubH >= maxSubH) return BAND_ZOOM_MIN
  return Math.min(BAND_ZOOM_MAX, maxSubH / naturalSubH)
})

// 单入口:clamp + localStorage 写
function setBandZoom(next: number) {
  const clamped = Math.max(BAND_ZOOM_MIN, Math.min(next, factorCap.value))
  bandZoomFactor.value = clamped
  localStorage.setItem(LS_KEY_BAND_ZOOM, String(clamped))
}

// 若 factorCap 收紧到低于当前 factor,自动 clamp(container resize / bandLaneCounts 变化)
watch(factorCap, (cap) => {
  if (bandZoomFactor.value > cap) setBandZoom(cap)
})

const formatFactor = (f: number) => f.toFixed(1) + '×'

function onBandZoomMinus() {
  setBandZoom(bandZoomFactor.value - BAND_ZOOM_STEP_BUTTON)
}
function onBandZoomPlus() {
  setBandZoom(bandZoomFactor.value + BAND_ZOOM_STEP_BUTTON)
}
function onBandZoomReset() {
  setBandZoom(BAND_ZOOM_MIN)
}

// Task 4 amendment(Task 5 e2e review 发现):ECharts dataZoomInside 在 canvas 上注册
// wheel 监听并 stopPropagation,bubble-phase 的 @wheel 永远收不到真实物理 Shift+wheel
// (只有 button 和合成 dispatchEvent 能到达)。改用 capture-phase 原生监听,在 ECharts
// 的 canvas-target 监听触发前拦截 —— 只在 e.shiftKey 时 preventDefault+stopPropagation
// 并接管;非 shift 立即 return,不 preventDefault/不 stopPropagation,原生滚轮 x-zoom 路径不变。
function subWheelCapture(e: WheelEvent) {
  if (!e.shiftKey) return          // 放行,交给 ECharts 走原生 x-zoom
  e.preventDefault()
  e.stopPropagation()               // 拦截,不让 ECharts 消费该 Shift+wheel
  const mul = e.deltaY < 0 ? BAND_ZOOM_STEP_WHEEL : (1 / BAND_ZOOM_STEP_WHEEL)
  setBandZoom(bandZoomFactor.value * mul)
}

// Shift+wheel over 主图 = 显式吞掉(spec §5.4;fork 结论),防浏览器页面滚动打扰视觉;不做 y-zoom
function mainWheelCapture(e: WheelEvent) {
  if (!e.shiftKey) return
  e.preventDefault()
  e.stopPropagation()               // 同上,拦截 ECharts 消费
}

function buildRenderInput() {
  const tagList = tagMap.value.tagList
  return {
    topology: effectivePattern.value!.topology,
    isolatedNodeIds: isolated.value,
    tagList,
    level: level.value,
    roleColors: roleColors.value,
    eventTier: (e: any) => view.eventTier(e),
    roleOfEventByBand: (e: any) => roleOfEventByBand(e, tagMap.value.tagToNodes, tagList),
    bandKeyOf: (e: any) => bandKeyOf(e, tagList),
    roleVisible: roleVisible.value,
    tagToNodes: tagMap.value.tagToNodes,
    selectedEventId: selectedEventId.value,
    tooltipResolver: (id: string) => resolveTooltipData(id, diag.value, effectiveAnalysis.value?.events ?? [], bars.value),
    strictWindow: strictWindowIdx(),
    matchLabel,
    sliderShow: showSlider.value,
    zoomOverride: readZoomOverride(),
    endRole: scanFile.value?.per_pattern[activePatternId.value!]?.end_role ?? undefined,
    selectedMatchId: selectedMatchId.value,
    candidateMatchIds: candidateMatchIds.value,
    highlightedEventIds: highlightedEventIds.value,
    pendingDisambigEventId: pendingDisambigEventId.value,
    matches: effectiveAnalysis.value?.matches ?? [],
  }
}

function readZoomOverride(): { start: number; end: number } | null {
  if (!chartMain) return null
  const cur = (chartMain.getOption() as any)?.dataZoom?.[0]
  if (cur && typeof cur.start === 'number' && typeof cur.end === 'number') {
    return { start: cur.start, end: cur.end }
  }
  return null
}

function render(forceResetZoom = false) {
  if (!chartMain || !chartSub || !effectiveAnalysis.value || !effectivePattern.value) return
  const params = { ...buildRenderInput(), zoomOverride: forceResetZoom ? null : readZoomOverride() }
  const bundle = computeEventData(bars.value, effectiveAnalysis.value.events, effectiveAnalysis.value.matches, params)
  const subGeom = deriveSubGeometry()

  // 更新 subCanvasH → sub-inner div 高度触发 chartSub 容器 resize
  subCanvasH.value = subGeom.subCanvasH

  const mainOpt = buildMainOption(bars.value, bundle, params, { getChartEl: () => mainEl.value })
  const subOpt  = buildSubOption(
    bars.value, bundle, subGeom,
    { ...params, zoomFactor: bandZoomFactor.value },
    chartSub.getWidth(),
    { getChartEl: () => subInnerEl.value },
  )

  chartMain.setOption(mainOpt as any, true)
  chartSub.setOption(subOpt as any, true)
  lastMarkLineKey = null
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

// ── drag handler ────────────────────────────────────────────────────
// spec §2: dy>0 向下拖 → 副图变小;写入相对 offset(≤0),zoom 变化后隐藏量守恒。
// startSubH 在首次 drag 事件时锁存(拖拽期间 subCanvasH 不变,故逐帧与绝对语义等价)。
let dragActive = false
let startSubH = 0
function onDrag(dy: number) {
  if (!subOuterEl.value) return
  if (!dragActive) {
    startSubH = subOuterEl.value.clientHeight
    dragActive = true
  }
  const raw = startSubH - dy
  const newSubH = Math.max(MIN_SUB_H, Math.min(raw, subCanvasH.value))
  panels.setSubHeightOffset(newSubH - subCanvasH.value)
  chartMain?.resize()
  chartSub?.resize()
}
function onDragEnd() {
  dragActive = false
  startSubH = 0
}
function onDblclick() {
  panels.setSubHeightOffset(null)
  chartMain?.resize()
  chartSub?.resize()
}

// main-chart 左边距相对 kline-wrap 的偏移(overlay 坐标源:chartMain.convertToPixel 是
// grid-relative,需加此偏移才是 kline-wrap 内 CrosshairOverlay 的绝对 left)
const updateMainCanvasOffset = () => {
  const wrap = wrapEl.value
  const main = mainEl.value
  if (!wrap || !main) return
  mainCanvasOffsetX.value = main.getBoundingClientRect().left - wrap.getBoundingClientRect().left
}

// ── 挂钩 chart 生命周期 ─────────────────────────────────────────────
onMounted(() => {
  window.addEventListener('keydown', onKeyDown)

  chartMain = echarts.init(mainEl.value!)
  chartSub  = echarts.init(subInnerEl.value!)

  // click 分流:主/副 chart 各一套,handleChartClick 按 seriesName 天然分流
  chartMain.on('click', (p: any) => {
    handleChartClick(p, effectiveAnalysis.value?.matches ?? [], view)
  })
  chartSub.on('click', (p: any) => {
    handleChartClick(p, effectiveAnalysis.value?.matches ?? [], view)
  })
  // ZRender blank click:两 chart 各一套
  chartMain.getZr().on('click', (e: any) => {
    if (!e.target) handleChartClick(null, effectiveAnalysis.value?.matches ?? [], view)
  })
  chartSub.getZr().on('click', (e: any) => {
    if (!e.target) handleChartClick(null, effectiveAnalysis.value?.matches ?? [], view)
  })

  // ResizeObserver 观测两 chart 容器
  roMain = new ResizeObserver(() => { chartMain?.resize(); updateMainCanvasOffset() })
  roMain.observe(mainEl.value!)
  roSub = new ResizeObserver(() => { chartSub?.resize(); updateMainCanvasOffset() })
  roSub.observe(subInnerEl.value!)

  // containerH 追踪 wrap 高度,factorCap 消费(spec §6.1)
  const wrap = wrapEl.value
  if (wrap) {
    containerH.value = wrap.clientHeight
    roWrap = new ResizeObserver(() => { containerH.value = wrap.clientHeight })
    roWrap.observe(wrap)
  }

  updateMainCanvasOffset()

  // Task 4 amendment:capture-phase 原生 wheel 监听,抢在 ECharts canvas-target 监听之前
  // 拦截 Shift+wheel(见 subWheelCapture/mainWheelCapture 定义处注释)。
  const subOuter = subOuterEl.value
  const main = mainEl.value
  if (subOuter) subOuter.addEventListener('wheel', subWheelCapture, { capture: true, passive: false })
  if (main) main.addEventListener('wheel', mainWheelCapture, { capture: true, passive: false })

  // dev-only e2e hook
  if ((import.meta as any).env?.DEV) {
    ;(window as any).__e2e = { view, chartMain: () => chartMain, chartSub: () => chartSub }
  }

  // Ctrl 切换(只作用于主图,副图无价格轴)
  unsubCtrl = ctrlState.subscribe((pressed) => {
    chartMain?.setOption({
      xAxis: [{ axisPointer: { snap: !pressed } }],
      yAxis: [{ axisPointer: { show: pressed } }],
    })
  })

  // 用户 zoom/pan(主图) → 重算 volume scale + yAxis[0]
  chartMain.on('datazoom', () => {
    if (!chartMain) return
    const dz = (chartMain.getOption() as any).dataZoom?.[0]
    if (!dz) return
    const start = typeof dz.start === 'number' ? dz.start : 0
    const end = typeof dz.end === 'number' ? dz.end : 100
    const N = bars.value.length
    const visStart = Math.max(0, Math.round((start / 100) * N))
    const visEnd = Math.min(N - 1, Math.round((end / 100) * N) - 1)
    if (visEnd < visStart) return
    const { volSeries, yAxisOverride } = buildVolumeSeriesAndYAxis(bars.value, visStart, visEnd)
    chartMain.setOption({
      series: [{ name: 'volume', data: volSeries.data }],
      yAxis: [{ min: yAxisOverride.min, max: yAxisOverride.max }],
    })
  })

  // —— Manual sync axisPointer 双向 relay(syncing flag 一次往返闭环防循环)
  let syncing = false
  const relay = (to: echarts.EChartsType) => (e: any) => {
    if (syncing) return
    const v = e?.axesInfo?.[0]?.value
    if (v == null) return
    syncing = true
    to.dispatchAction({
      type: 'updateAxisPointer',
      currTrigger: 'mousemove',
      xAxisIndex: 0,
      xAxisValue: v,
    })
    syncing = false
    // Overlay x 始终从 chartMain 一路算(kline-wrap 内坐标源统一)
    if (!chartMain) return
    const px = chartMain.convertToPixel({ gridIndex: 0 }, [v, 0])[0]
    overlayX.value = px + mainCanvasOffsetX.value
  }
  chartMain.on('updateAxisPointer', relay(chartSub))
  chartSub.on('updateAxisPointer', relay(chartMain))

  // —— 出图外双向清对方 axisPointer(dispatchAction 幂等)
  chartMain.getZr().on('mouseout', () => {
    if (!chartSub) return
    chartSub.dispatchAction({ type: 'updateAxisPointer', currTrigger: 'leave' })
    overlayX.value = null
  })
  chartSub.getZr().on('mouseout', () => {
    if (!chartMain) return
    chartMain.dispatchAction({ type: 'updateAxisPointer', currTrigger: 'leave' })
    overlayX.value = null
  })

  // —— dataZoom 双向同步(独立 zoomSyncing flag,与 axisPointer 路径正交)
  let zoomSyncing = false
  const relayZoom = (to: echarts.EChartsType) => (p: any) => {
    if (zoomSyncing) return
    const start = p.start ?? p.batch?.[0]?.start
    const end = p.end ?? p.batch?.[0]?.end
    if (start == null || end == null) return
    zoomSyncing = true
    to.dispatchAction({ type: 'dataZoom', start, end })
    zoomSyncing = false
  }
  chartMain.on('datazoom', relayZoom(chartSub))
  chartSub.on('datazoom', relayZoom(chartMain))

  // updateAxisPointer 锁 close 横线(主图专属)
  chartMain.on('updateAxisPointer', (e: any) => {
    if (!chartMain) return
    if (ctrlState.isPressed()) {
      const key = 'ctrl'
      if (lastMarkLineKey === key) return
      lastMarkLineKey = key
      chartMain.setOption({ series: [{ name: 'kline', markLine: { data: [] } }] })
      return
    }
    const dataIdx = e?.dataIndex ?? e?.seriesAxesInfo?.[0]?.dataIndex
    if (typeof dataIdx !== 'number') return
    const b = bars.value[dataIdx]
    if (!b) return
    const key = `nc:${dataIdx}`
    if (lastMarkLineKey === key) return
    lastMarkLineKey = key
    chartMain.setOption({
      series: [{ name: 'kline', markLine: { silent: true, symbol: 'none',
        lineStyle: { color: '#0088CC', type: 'dashed', width: 1 },
        data: [{ yAxis: b.c }] } }],
    })
  })

  void reloadBars().then(() => render(true))
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeyDown)
  subOuterEl.value?.removeEventListener('wheel', subWheelCapture, { capture: true })
  mainEl.value?.removeEventListener('wheel', mainWheelCapture, { capture: true })
  unsubCtrl?.()
  chartMain?.getZr().off('click')
  chartSub?.getZr().off('click')

  chartMain?.getZr().off('mouseout')
  chartSub?.getZr().off('mouseout')

  chartMain?.off('updateAxisPointer')
  chartSub?.off('updateAxisPointer')
  chartMain?.off('datazoom')
  chartSub?.off('datazoom')

  roMain?.disconnect()
  roSub?.disconnect()
  roWrap?.disconnect()
  roWrap = null
  chartMain?.dispose()
  chartSub?.dispose()
  chartMain = null
  chartSub = null
})

// ── Reactive watches ────────────────────────────────────────────────
watch(symbol, () => void reloadBars().then(() => render(true)))
watch([scanFile, effectiveScan], () => void reloadBars().then(() => render(false)))
watch([effectiveAnalysis, roleVisible, level, roleColors, selectedEventId, diag, showSlider,
       selectedMatchId, candidateMatchIds, highlightedEventIds, pendingDisambigEventId,
       bandZoomFactor],
      () => render(false), { deep: true })

// subHeightOffset / subCanvasH 变化 → chart.resize()(RO 会自动触发,这里手动兜底)
watch([subHeightOffset, subCanvasH], () => {
  chartMain?.resize()
  chartSub?.resize()
})
</script>

<style scoped>
/* 双 chart 上下 flex 布局,主图 fixed 顶、副图 overflow-y 滚动。
   min-width:0 让 flex 列能收缩到比 canvas 窄。 */
.kline-wrap-v2 {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
  min-width: 0;
  overflow: hidden;
  position: relative;
}
.main-chart {
  min-height: 0;
  min-width: 0;
  overflow: hidden;
}
.sub-outer {
  min-height: 0;
  min-width: 0;
  overflow-y: auto;
  overflow-x: hidden;
  position: relative;
}
.sub-inner {
  width: 100%;
  /* height 由 :style 动态设 */
  min-width: 0;
}
.band-zoom-controls {
  position: absolute;
  top: 4px;
  right: 4px;
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 2px 4px;
  background: rgba(255, 255, 255, 0.85);
  border: 1px solid #cbd5e1;
  border-radius: 4px;
  z-index: 10;
  user-select: none;
}
.band-zoom-btn {
  width: 20px;
  height: 20px;
  padding: 0;
  border: 1px solid #cbd5e1;
  border-radius: 2px;
  background: #f8fafc;
  color: #334155;
  font-size: 13px;
  line-height: 1;
  cursor: pointer;
}
.band-zoom-btn:hover:not(:disabled) { background: #e2e8f0; }
.band-zoom-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.band-zoom-readout {
  min-width: 36px;
  text-align: center;
  font-size: 11px;
  color: #334155;
  font-variant-numeric: tabular-nums;
}
</style>
