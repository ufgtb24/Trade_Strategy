<template>
  <div class="kline-wrap-v2" ref="wrapEl">
    <div ref="mainEl" class="main-chart" style="flex: 1" @contextmenu="handleContextMenu" />
    <ResizableDivider @drag="onDrag" @dragend="onDragEnd" @dblclick="onDblclick" />
    <CandidateStatusBar :matches="effectiveAnalysis?.matches ?? []" />
    <ShiftPairBanner />
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
      <div ref="subInnerEl" class="sub-inner" :style="{ height: subCanvasH + 'px' }" @contextmenu="handleContextMenu" />
    </div>
    <!-- 主图顶部居中标题:HTML 代码 + 一键复制按钮(取代原 canvas title)。
         code 用 HTML,可直接选中复制;按钮紧跟代码右侧。容器 pointer-events:none,
         仅文字/按钮可交互,不挡标题区 K 线拖拽。 -->
    <div v-if="symbol" class="symbol-title-bar">
      <span class="symbol-text" :data-symbol="symbol">{{ symbol }}</span>
      <button type="button" class="copy-symbol-btn"
              :title="`复制代码 ${symbol}`"
              aria-label="复制股票代码"
              @click.stop="copySymbol">
        <svg viewBox="0 0 16 16" width="13" height="13" aria-hidden="true">
          <rect x="5.2" y="5.2" width="8.6" height="8.6" rx="1.6" fill="none" stroke="currentColor" stroke-width="1.4"/>
          <rect x="2.2" y="2.2" width="8.6" height="8.6" rx="1.6" fill="none" stroke="currentColor" stroke-width="1.4"/>
        </svg>
      </button>
    </div>
    <div class="brush-toggle-wrap">
      <button type="button" class="brush-toggle-btn" :class="{ active: brushActive }"
              title="框选主图时段 → 查询该窗口内 gate 失败样例(入口 A · 快捷键 Shift+,)"
              @click="toggleBrush">框选</button>
    </div>
    <CrosshairOverlay :x="overlayX" />
    <div v-if="contextMenuVisible" ref="driverMenuEl" class="driver-menu"
         :style="{ left: contextMenuPos.x + 'px', top: contextMenuPos.y + 'px' }">
      <!-- 复制 instance_id · marker 右键即显示(contextMenuInstanceId 非 null)、空白右键隐藏 -->
      <button v-if="contextMenuInstanceId" type="button" class="copy-driver-btn"
              @click.stop="copyInstanceId">复制 instance_id</button>
      <!-- v2 event-debug(2026-07-15) · debug 菜单分支(marker + whitelist 命中) -->
      <template v-if="menuDispatch.menu === 'debug' && menuDispatch.anchors">
        <button v-for="a in menuDispatch.anchors" :key="a.key"
                type="button" class="debug-menu-item"
                :class="{ 'debug-menu-item-disabled': a.disabled }"
                :title="a.disabled ? a.disabledReason : ''"
                @click.stop="onDebugMenuClick(a)">
          <div class="menu-item-title">Debug {{ menuDebugClassName }} {{ a.disabled ? '(未定位)' : a.label }} (bar {{ a.bar }})</div>
          <div class="menu-item-hint">↳ {{ a.hint }}</div>
        </button>
        <div class="debug-menu-separator"></div>
        <button type="button" class="copy-driver-btn" @click.stop="copyDriverScript">复制 driver 脚本</button>
      </template>
      <!-- driver 菜单分支(空白 K 线 / marker 不在 whitelist / 生产 env) -->
      <template v-else>
        <button type="button" class="copy-driver-btn" @click.stop="copyDriverScript">复制 driver 脚本</button>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref, watch, computed, nextTick } from 'vue'
import * as echarts from 'echarts'
import { isBrushToggleKey } from './klineBrushKey'
import { createBrushRequestHandler } from './klineBrushHandler'
import { computeRightAnchoredZoom } from './klineCtrlZoom'
import { storeToRefs } from 'pinia'
import { useViewStore } from '../stores/view'
import { dispatchDebugMenu, type MenuDispatch } from './KlineChart.debug-menu'
import { usePanelsStore } from '../stores/panels'
import { getOhlc } from '../api'
import { computeEventData, buildMainOption, buildSubOption, buildVolumeSeriesAndYAxis } from '../render/chart'
import {
  computeSubGeometry, composeEffectiveSubH, SUB_CANVAS_MIN_H, MIN_SUB_H,
  MAIN_MIN_H, BAND_ZOOM_MIN, BAND_ZOOM_MAX, LS_KEY_BAND_ZOOM,
  BAND_ZOOM_STEP_BUTTON, BAND_ZOOM_STEP_WHEEL,
} from '../render/subGeometry'
import { ctrlState } from '../render/ctrlState'
import { bandKeyOf, nodeOfEventByBand, resolveTooltipData, windowOf, formatForwardReturn, subBandTagList } from '../render/visible'
import type { Bar } from '../types'
import { handleChartClick, handleShiftClick, MARKER_SERIES } from './KlineChart'
import CandidateStatusBar from './CandidateStatusBar.vue'
import ShiftPairBanner from './ShiftPairBanner.vue'
import ResizableDivider from './ResizableDivider.vue'
import CrosshairOverlay from './CrosshairOverlay.vue'

const view = useViewStore()
const { symbol, effectiveAnalysis, nodeColors, nodeVisible, level, tagMap, isolated,
        effectivePattern, effectiveScan, scanFile, focusedInstanceRef, diag,
        activePatternId, activeDetailCard, selectedMatchId, candidateMatchIds,
        highlightedEventIds, pendingDisambigInstanceId, shiftSelectedEventIds,
        focusedInstanceId, selectedInstanceId, compositionGroupIds } = storeToRefs(view)
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

// ── 入口 A(Task 18):主图 brush 框选时段 → scope=time 查询 ───────────────────
// brush 组件配置只需最简实现(spec 明确要求),不做 toolbox UI,靠下方按钮
// takeGlobalCursor 切换刷选态;outOfBrush.colorAlpha=1 关掉默认淘选变暗视觉副作用
// (candlestick/自定义 marker 系列不需要被 brush 的可视化管线改色)。
// removeOnClick:false + transformable:false:框选完的 area 保持为"仅装饰"覆盖层,
// 不吞底下 series 的 mouseover(否则框内 K-bar/marker 无法弹 tooltip)。
const BRUSH_OPTION = {
  xAxisIndex: 0,
  brushType: 'lineX' as const,
  brushMode: 'single' as const,
  // 【修复 · brush 首次刷失效】原 debounce 300ms:拖动(约 100ms)结束时 brushSelect 还在
  // debounce 中 → brushEnd 读 latestRange=null → 首次框选请求丢失。改回默认 fixRate 0
  // (即时派发;请求只在 brushEnd 发一次,拖动中的高频 brushSelect 仅更新 latestRange,无副作用)。
  brushStyle: { borderWidth: 1, color: 'rgba(59,130,246,0.12)', borderColor: '#3b82f6' },
  outOfBrush: { colorAlpha: 1 },
  removeOnClick: false,
  transformable: false,
}
const brushActive = ref(false)
function toggleBrush() {
  brushActive.value = !brushActive.value
  chartMain?.dispatchAction({
    type: 'takeGlobalCursor',
    key: 'brush',
    brushOption: { brushType: brushActive.value ? 'lineX' : false, brushMode: 'single' },
  })
}
/** 清主图已落 brush area + 同步 brushActive=false(退出光标态)。切股/切 pattern/
 * 离开 time 卡片时联动,防跨股残影与视觉噪音。副作用:也把 Esc/按钮/联动三条路径
 * 收敛到同一状态,后续 watcher 依赖 brushActive 不会 desync。 */
function clearBrushAreas() {
  if (!chartMain) return
  chartMain.dispatchAction({ type: 'brush', areas: [] })
  if (brushActive.value) {
    brushActive.value = false
    chartMain.dispatchAction({
      type: 'takeGlobalCursor', key: 'brush',
      brushOption: { brushType: false, brushMode: 'single' },
    })
  }
}

// ── 入口 D(Task 18):marker shift+click 跨图累积 → scope=pair 查询 ───────────
// MARKER_SERIES 上落 shift 时不进 handleChartClick 的四分支 candidate 流,转给
// view.shiftSelectedEvents 累积器(KlineChart.ts::handleShiftClick)。返回 true = 已消费。
function handleMaybeShiftClick(p: any, source: 'main' | 'sub'): boolean {
  const native = p?.event?.event as MouseEvent | undefined
  if (!native?.shiftKey || !p?.seriesName || !MARKER_SERIES.includes(p.seriesName) || !p.data?.instance_id) {
    return false
  }
  const instanceId = p.data.instance_id as string
  const nodeId = effectiveAnalysis.value?.events.find((e) => e.instance_id === instanceId)?.node_id ?? 'unknown'
  handleShiftClick(instanceId, nodeId, source, view)
  return true
}

// ── Task 23:主图右键复制 driver 脚本(V1 D0)──────────────────────────
// 兜底 detector 内部超细节调查:主图 contextmenu → 弹菜单 → 复制一段可直接粘贴到 IDE
// 的 driver 脚本(build_pattern + attach_and_collect + engine.analyze + detach,同
// Task 22 scan-top-miss.py 的真实接线方式;非 brief 原始伪代码里不存在的 scan_one_symbol)。
// 纯前端 UX,不动 backend。
const contextMenuVisible = ref(false)
const contextMenuPos = ref({ x: 0, y: 0 })
const driverMenuEl = ref<HTMLElement | null>(null)

// v2 event-debug(2026-07-15) · 右键菜单分流状态
const menuDispatch = ref<MenuDispatch>({ menu: 'driver' })  // 默认 driver
const contextMenuInstanceId = ref<string | null>(null)      // 右键落点 marker 的 instance_id(null=空白)

// marker 命中 flag:chartMain.on('contextmenu')(见 onMounted)命中 marker 时置 true 并自行开菜单,
// 随后原生事件冒泡到本 div 的 DOM handler(handleContextMenu)时消费该 flag 后直接跳过 ——
// ECharts contextmenu 只在数据项(含 marker)上触发、不覆盖空白 K 线,故留 DOM handler 兜底空白路径。
let markerContextMenuHandled = false

function handleContextMenu(ev: MouseEvent) {
  // ⚠ preventDefault 必须无条件在 flag 判之前调 —— marker 路径下 ECharts handler 的
  // nativeEv.preventDefault() 是在 zrender 合成 event 层,不覆盖浏览器 native 层,
  // Chromium 对 canvas 会弹默认 image 菜单(save/copy/screenshot/inspect)。
  // 由 DOM handler 无条件拦浏览器菜单,再按 flag 决定是否 open。
  ev.preventDefault()
  if (markerContextMenuHandled) {
    markerContextMenuHandled = false
    return  // marker handler 已 open,跳 open
  }
  openContextMenuAt(null, ev.clientX, ev.clientY)
}

function openContextMenuAt(instanceId: string | null, x: number, y: number) {
  // 屏蔽 ECharts marker tooltip · 右键触发时 hover 还在 marker 上会导致 tooltip 遮住菜单
  chartMain?.dispatchAction({ type: 'hideTip' })
  chartSub?.dispatchAction({ type: 'hideTip' })
  contextMenuInstanceId.value = instanceId
  menuDispatch.value = dispatchDebugMenu({ instanceId }, view)
  contextMenuVisible.value = true
  contextMenuPos.value = { x, y }
  // 位置越界翻转 —— nextTick 后菜单已渲染, 读实际 rect 判是否溢出 viewport, 溢出则改用左/上定位
  void nextTick(() => {
    const el = driverMenuEl.value
    if (!el) return
    const rect = el.getBoundingClientRect()
    const vw = window.innerWidth, vh = window.innerHeight
    let nx = x, ny = y
    if (rect.right > vw) nx = Math.max(0, x - rect.width)  // 右溢 → 翻左
    if (rect.bottom > vh) ny = Math.max(0, y - rect.height)  // 下溢 → 翻上
    if (nx !== x || ny !== y) contextMenuPos.value = { x: nx, y: ny }
  })
}

function buildDriverScript(sym: string, patternId: string): string {
  return `
# path2 driver · ${sym}
from path2.debug import set_current_symbol
from path2_web.gate_collector import attach_and_collect, detach
from path2.dag.engine import analyze
from path2_apps.${patternId}.dag_spec import build_pattern
from path2_apps.${patternId}.params import Params

set_current_symbol('${sym}')
params = Params.default()
spec = build_pattern(params)
# 在这里加 breakpoint() · PyCharm 断在 Detector 内部
collector = attach_and_collect(spec)
try:
    result = analyze(spec, df, params)   # df 需自己 load
finally:
    detach(spec)
print(f"matches: {len(result.matches)}, gate_failures: {len(collector.snapshot())}")
`.trim()
}

function copyDriverScript() {
  if (!symbol.value || !activePatternId.value) { contextMenuVisible.value = false; return }
  const script = buildDriverScript(symbol.value, activePatternId.value)
  void navigator.clipboard.writeText(script)
  contextMenuVisible.value = false
}

// 复制右键落点 marker 的 instance_id 到剪贴板 · marker 右键时 contextMenuInstanceId 已在手
function copyInstanceId() {
  const iid = contextMenuInstanceId.value
  if (!iid) return
  void navigator.clipboard.writeText(iid)
    .then(() => view.showToast(`已复制 instance_id: ${iid}`))
  contextMenuVisible.value = false
}

// 一键复制当前股票代码到剪贴板 · 主图左上角图标按钮;复用 clipboard + toast 模式
function copySymbol() {
  if (!symbol.value) return
  void navigator.clipboard.writeText(symbol.value)
    .then(() => view.showToast(`已复制:${symbol.value}`))
}

// v2 event-debug(2026-07-15) · debug 菜单点击 → 触发 triggerEventDebug
const menuDebugClassName = computed(() => {
  if (!contextMenuInstanceId.value) return ''
  const ev = view.effectiveAnalysis?.events?.find(e => e.instance_id === contextMenuInstanceId.value)
  return ev?.node_id ?? ''
})

function onDebugMenuClick(anchor: { key: 'entry' | 'start' | 'end' | 'confirm'; disabled?: boolean }) {
  if (anchor.disabled) return
  if (!contextMenuInstanceId.value) return
  void view.triggerEventDebug(contextMenuInstanceId.value, anchor.key)
  contextMenuVisible.value = false
}

function handleDocumentClick(ev: MouseEvent) {
  if (!contextMenuVisible.value) return
  const target = ev.target as Node | null
  if (driverMenuEl.value && target && driverMenuEl.value.contains(target)) return
  contextMenuVisible.value = false
}

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
  const m = effectiveAnalysis.value?.matches.find((mm) => mm.match_id === matchId)
  if (!m || m.forward_return === undefined) return null
  const horizon = (effectiveScan.value ?? scanFile.value?.scan)?.label_horizon
  // forward_drawdown 与 forward_return 同层展示(T1 注入);老 scan file 无此字段时不追加。
  const dd = m.forward_drawdown !== undefined
    ? `<br/>d_${horizon}: ${formatForwardReturn(m.forward_drawdown)}`
    : ''
  return `ret_${horizon}: ${formatForwardReturn(m.forward_return)}${dd}`
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
    // spec 2026-07-13:spot 与 span 已合并 packLanes,统一读 value[3]=band, value[2]=lane
    let maxLane = -1
    for (const d of [...bundle.intervalData, ...bundle.pointData]) {
      if (d.value[3] === band && d.value[2] > maxLane) maxLane = d.value[2]
    }
    return maxLane + 1
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
  if (!e.shiftKey && e.ctrlKey) { ctrlWheelZoom(e); return }   // Ctrl → 右锚定 x 缩放
  if (!e.shiftKey) return          // 放行,交给 ECharts 走原生 x-zoom
  e.preventDefault()
  e.stopPropagation()               // 拦截,不让 ECharts 消费该 Shift+wheel
  const mul = e.deltaY < 0 ? BAND_ZOOM_STEP_WHEEL : (1 / BAND_ZOOM_STEP_WHEEL)
  setBandZoom(bandZoomFactor.value * mul)
}

// Shift+wheel over 主图 = 显式吞掉(spec §5.4;fork 结论),防浏览器页面滚动打扰视觉;不做 y-zoom
function mainWheelCapture(e: WheelEvent) {
  if (!e.shiftKey && e.ctrlKey) { ctrlWheelZoom(e); return }   // Ctrl → 右锚定 x 缩放
  if (!e.shiftKey) return
  e.preventDefault()
  e.stopPropagation()               // 同上,拦截 ECharts 消费
}

// Ctrl+wheel:右锚定 x 缩放(不动点=当前视图最右侧 K 线;不按 Ctrl 保持 ECharts 鼠标中心缩放)。
// preventDefault 必须:浏览器默认 Ctrl+wheel = 页面缩放。主/副图容器上滚都单入口 dispatch 到
// chartMain —— dispatchAction 同步触发其 datazoom 事件,既有 relayZoom 带动 chartSub、
// volume/y 轴重算 handler 同帧生效。
function ctrlWheelZoom(e: WheelEvent) {
  e.preventDefault()
  e.stopPropagation()
  const cur = readZoomOverride()
  if (!cur) return
  const next = computeRightAnchoredZoom(cur.start, cur.end, e.deltaY, bars.value.length)
  if (!next) return
  chartMain?.dispatchAction({ type: 'dataZoom', start: next.start, end: next.end })
}

function buildRenderInput() {
  const tagList = tagMap.value.tagList
  return {
    topology: effectivePattern.value!.topology,
    isolatedNodeIds: isolated.value,
    tagList,
    level: level.value,
    nodeColors: nodeColors.value,
    eventTier: (e: any) => view.eventTier(e),
    nodeOfEventByBand: (e: any) => nodeOfEventByBand(e, tagMap.value.tagToNodes, tagList),
    bandKeyOf: (e: any) => bandKeyOf(e),
    nodeVisible: nodeVisible.value,
    tagToNodes: tagMap.value.tagToNodes,
    // 当前聚焦实例(合并):selectedInstanceId(0 归属)与 focusedInstanceId(1 归属)互斥,
    // 合并即「当前聚焦实例」,供 bracket 是否本身被点的判定(marker 分支必设)。
    selectedInstanceId: focusedInstanceRef.value,
    // 精确实例(1 归属直选时非空):chart 的 focus 条目按它精确到实例(点 #0 只亮 #0)。
    focusedInstanceId: focusedInstanceId.value,
    // 实例级签名:formatter 直接把 data.instance_id 传给 resolver,展示【所悬停实例】的判定。
    tooltipResolver: (id: string) =>
      resolveTooltipData(id, diag.value, effectiveAnalysis.value?.events ?? [], bars.value),
    strictWindow: strictWindowIdx(),
    matchLabel,
    sliderShow: showSlider.value,
    zoomOverride: readZoomOverride(),
    endNode: scanFile.value?.per_pattern[activePatternId.value!]?.end_node ?? undefined,
    selectedMatchId: selectedMatchId.value,
    candidateMatchIds: candidateMatchIds.value,
    // 组成型组「一选全选」:0 归属非 match 组的选中集并入 group 高亮
    // (chart group 分支按 focusedInstanceRef 排除点击者 → 点击者 focus 框独家,
    // 组员 group 框;match 组时本集为空,由 matchedIds 闭包独占)。
    highlightedEventIds: new Set([...highlightedEventIds.value, ...compositionGroupIds.value]),
    pendingDisambigInstanceId: pendingDisambigInstanceId.value,
    shiftSelectedEventIds: shiftSelectedEventIds.value,
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
  // mainOpt 走 notMerge:true 全量替换,不含 brush 组件声明 → 每帧渲染后需合并模式补挂回来
  // (chart.ts::buildMainOption 不在本任务改动范围,brush 只是 KlineChart.vue 自己的交互层)。
  chartMain.setOption({ brush: BRUSH_OPTION })
  lastMarkLineKey = null
}

function onKeyDown(e: KeyboardEvent) {
  const t = e.target as HTMLElement | null
  // 输入框内不响应任何全局快捷键(承 Esc/Shift+, 共用同一守卫)。
  if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return
  // Shift+,:切换框选光标态(与按钮 toggleBrush 同一路径 · 双向 toggle)。
  // Shift+,(key '<')不进搜索框:onGlobalCharKey 已整体屏蔽 shift(无需逐键让位)。
  if (isBrushToggleKey(e)) {
    toggleBrush()
    e.preventDefault()
    return
  }
  if (e.key !== 'Escape') return
  if (contextMenuVisible.value) { contextMenuVisible.value = false; return }
  view.clearFocus()
  // Esc 也退出 brush 光标态(sync Vue state 与 ECharts 内部,防"点两下按钮才能重开")。
  // blur:Esc 本身是键盘事件 · 浏览器会把当前 focus 元素的 :focus-visible 判为 true,
  // CSS `:not(:focus-visible)` 拦不住 → 手动 blur 让 focus outline 消失(开头已挡输入框)。
  if (brushActive.value) brushActive.value = false
  ;(document.activeElement as HTMLElement | null)?.blur()
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
  document.addEventListener('click', handleDocumentClick)

  chartMain = echarts.init(mainEl.value!)
  chartSub  = echarts.init(subInnerEl.value!)

  // click 分流:主/副 chart 各一套,handleChartClick 按 seriesName 天然分流;
  // shift+click 先被 handleMaybeShiftClick 拦截(入口 D),消费后不再回退到候选四分支。
  chartMain.on('click', (p: any) => {
    if (handleMaybeShiftClick(p, 'main')) return
    handleChartClick(p, effectiveAnalysis.value?.matches ?? [], view)
  })
  chartSub.on('click', (p: any) => {
    if (handleMaybeShiftClick(p, 'sub')) return
    handleChartClick(p, effectiveAnalysis.value?.matches ?? [], view)
  })
  // v2 event-debug(2026-07-15) · marker 右键 → debug 菜单(主+副图,tb marker 主要在副图泳道)
  // ECharts element-level, 只在数据项上触发 —— 空白 K 线 / 蜡烛区由 DOM handleContextMenu 兜底,
  // 见 markerContextMenuHandled 注释。主副 chart 共享 flag。
  const onContextMenuMarker = (p: any) => {
    const nativeEv = p.event?.event as MouseEvent | undefined
    if (!nativeEv) return
    nativeEv.preventDefault()
    const instanceId = (p.seriesName && MARKER_SERIES.includes(p.seriesName) && p.data?.instance_id)
      ? String(p.data.instance_id) : null
    if (!instanceId) return
    openContextMenuAt(instanceId, nativeEv.clientX, nativeEv.clientY)
    markerContextMenuHandled = true
  }
  chartMain.on('contextmenu', onContextMenuMarker)
  chartSub.on('contextmenu', onContextMenuMarker)
  // 菜单开启期间彻底屏蔽 tooltip · 源头拦截:
  // (a) setOption tooltip.triggerOn='none' 让 ECharts 不响应 hover(彻底防 tooltip 渲染)
  // (b) showTip listener 兜底任何主动 dispatchAction showTip 场景(便宜的双保险)
  // 关闭菜单后 triggerOn 恢复 'mousemove|click'(ECharts 默认)。
  watch(contextMenuVisible, (visible) => {
    const opt = { tooltip: { triggerOn: visible ? 'none' : 'mousemove|click' } }
    chartMain?.setOption(opt as any, { lazyUpdate: true } as any)
    chartSub?.setOption(opt as any, { lazyUpdate: true } as any)
  })
  const suppressTipDuringMenu = (chart: any) => {
    chart.on('showTip', () => {
      if (contextMenuVisible.value) chart.dispatchAction({ type: 'hideTip' })
    })
  }
  suppressTipDuringMenu(chartMain)
  suppressTipDuringMenu(chartSub)
  // 入口 A:主图 brush 完成一次框选 → 换算 bar 索引区间 → scope=time 查询
  // 双事件模式(见 ./klineBrushHandler · docs/superpowers/specs/2026-07-18-brush-double-request-fix-design.md):
  //   brushselected 每次拖动触发 → 只更新缓存(不发 request)· brushEnd mouseup 触发一次 → 发 1 次 request。
  //   为何双事件:ECharts brushEnd payload 未文档化(不能可靠取 coordRange) · brushselected 每次拖动触发。
  const brushH = createBrushRequestHandler(
    // 不传 node 过滤:过滤是前端显示层,请求恒全量(见 view.ts::triggerTimeQuery 注释)
    (s, e) => { void view.triggerTimeQuery(s, e) },
    () => bars.value.length,
  )
  chartMain.on('brushselected', brushH.onBrushSelected)
  chartMain.on('brushEnd', brushH.onBrushEnd)
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
  document.removeEventListener('click', handleDocumentClick)
  subOuterEl.value?.removeEventListener('wheel', subWheelCapture, { capture: true })
  mainEl.value?.removeEventListener('wheel', mainWheelCapture, { capture: true })
  unsubCtrl?.()
  chartMain?.getZr().off('click')
  chartSub?.getZr().off('click')
  chartMain?.off('brushselected')
  chartMain?.off('contextmenu')
  chartSub?.off('contextmenu')
  chartMain?.off('showTip')
  chartSub?.off('showTip')

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
watch([effectiveAnalysis, nodeVisible, level, nodeColors, focusedInstanceRef, diag, showSlider,
       selectedMatchId, candidateMatchIds, highlightedEventIds, pendingDisambigInstanceId,
       shiftSelectedEventIds, bandZoomFactor, focusedInstanceId, selectedInstanceId,
       compositionGroupIds],
      () => render(false), { deep: true })

// subHeightOffset / subCanvasH 变化 → chart.resize()(RO 会自动触发,这里手动兜底)
watch([subHeightOffset, subCanvasH], () => {
  chartMain?.resize()
  chartSub?.resize()
})

// 入口 A brush area 联动清理:切股/切 pattern → 清框,防跨股残影;离开 time 卡片
// (关闭卡片或切到 pair/candidate)→ 清框,视觉自洽。选项 3 + 选项 2 一处 wire。
watch([symbol, activePatternId], () => clearBrushAreas())
watch(activeDetailCard, (v, prev) => {
  if (prev === 'time' && v !== 'time') clearBrushAreas()
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
/* 主图顶部居中标题:HTML code + 复制按钮(取代原 canvas title)· 相对 kline-wrap-v2,
   left:50%+translateX 居中(= main-chart 中心),top:6 与原 canvas title 同高。
   容器 pointer-events:none 穿透,仅文字/按钮可交互,不挡标题区 K 线拖拽。 */
.symbol-title-bar {
  position: absolute;
  top: 6px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 6px;
  z-index: 10;
  pointer-events: none;
}
.symbol-text {
  font-size: 14px;
  font-weight: bold;
  color: #333;
  user-select: text;
  -webkit-user-select: text;
  pointer-events: auto;
}
.copy-symbol-btn {
  pointer-events: auto;
  width: 22px;
  height: 22px;
  padding: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid #cbd5e1;
  border-radius: 4px;
  background: rgba(248, 250, 252, 0.9);
  color: #334155;
  cursor: pointer;
}
.copy-symbol-btn:hover { background: #e2e8f0; }
.copy-symbol-btn:focus:not(:focus-visible) { outline: none; }
.brush-toggle-wrap {
  position: absolute;
  top: 4px;
  left: 60px;
  z-index: 10;
}
.brush-toggle-btn {
  height: 22px;
  padding: 0 10px;
  border: 1px solid #cbd5e1;
  border-radius: 4px;
  background: rgba(248, 250, 252, 0.9);
  color: #334155;
  font-size: 11px;
  cursor: pointer;
}
.brush-toggle-btn:hover { background: #e2e8f0; }
.brush-toggle-btn.active { background: #3b82f6; color: #fff; border-color: #3b82f6; }
/* 鼠标点击后不显 focus outline(Esc 关闭 brush 时按钮变白露出黑框的观感修复);
   键盘 Tab 导航仍显 outline · 保留可访问性。 */
.brush-toggle-btn:focus:not(:focus-visible) { outline: none; }
.driver-menu {
  position: fixed;
  background: white;
  border: 1px solid #cbd5e0;
  padding: 4px;
  border-radius: 4px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
  z-index: 1000;
}
.copy-driver-btn {
  display: block;
  width: 100%;
  padding: 4px 12px;
  border: none;
  background: transparent;
  color: #334155;
  font-size: 12px;
  text-align: left;
  cursor: pointer;
  white-space: nowrap;
}
.copy-driver-btn:hover { background: #f1f5f9; }
/* v2 event-debug(2026-07-15) · debug 菜单项(两行文案 · font-size 差 2px) */
.debug-menu-item {
  display: block;
  width: 100%;
  padding: 6px 10px;
  text-align: left;
  background: transparent;
  border: none;
  cursor: pointer;
  font-family: inherit;
}
.debug-menu-item:hover:not(.debug-menu-item-disabled) {
  background: #f0f0f0;
}
.debug-menu-item-disabled {
  opacity: 0.5;
  pointer-events: none;
}
.menu-item-title {
  font-size: 13px;
  color: #222;
}
.menu-item-hint {
  font-size: 11px;  /* 差 2px */
  color: #888;
  margin-top: 2px;
}
.debug-menu-separator {
  height: 1px;
  background: #ddd;
  margin: 4px 0;
}
</style>
