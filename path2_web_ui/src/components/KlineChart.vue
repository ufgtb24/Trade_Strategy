<template>
  <div class="kline-wrap-v2" ref="wrapEl">
    <div ref="mainEl" class="main-chart" style="flex: 1" @contextmenu="handleContextMenu" />
    <ResizableDivider @drag="onDrag" @dragend="onDragEnd" @dblclick="onDblclick" />
    <WalkStatusBar v-if="mode !== 'annotate'" ref="walkBarRef" :feedback="walkFeedback" @feedback="toggleFeedbackPanel" />
    <div class="sub-outer" :style="{ height: effectiveSubH + 'px' }" ref="subOuterEl">
      <!-- 副图竖直缩放挪到顶栏(ChartArea 的 #band-zoom-slot):浮在副图右上角会盖住最右边的 ▲ 与 ✓ / ✗、hit 的 ▼
           (训练段末日附近的样本正落在那里);顶栏和这个控件同在 annotate 以外的模式出现 -->
      <Teleport v-if="mode !== 'annotate' && zoomSlot" :to="zoomSlot">
      <div class="band-zoom-controls" data-testid="band-zoom-controls" @wheel.stop>
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
                :disabled="bandZoomFactor === bandZoomHome"
                :title="`复位到 ${formatFactor(bandZoomHome)}`"
                @click="onBandZoomReset">↺</button>
      </div>
      </Teleport>
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
    <div v-if="!annotating" class="brush-toggle-wrap">
      <button type="button" class="brush-toggle-btn" :class="{ active: brushActive }"
              title="框选主图时段 → 查询该窗口内 gate 失败样例(入口 A · 快捷键 Shift+,)"
              @click="toggleBrush">框选</button>
    </div>
    <CrosshairOverlay :x="overlayX" />
    <!-- annotate:改起止停在样本日时,鼠标旁写它是哪个样本的成员框 -->
    <div v-if="resizeStop" class="resize-stop" data-testid="resize-stop"
         :style="{ left: `${resizeStop.x + 12}px`, top: `${resizeStop.y + 12}px` }">{{ resizeStop.text }}</div>
    <!-- compare 的 feedback 工具:拖动中贯穿主副图的竖带;拖出的范围里没有买点时,在松开处浮 2 秒 no buy in range -->
    <div v-if="rangeBand" class="feedback-range-band" data-testid="feedback-range-band"
         :style="{ left: `${rangeBand.left}px`, width: `${rangeBand.width}px` }" />
    <!-- compare:作答面板管的那段日期(面板开着时),或选中的那条反馈(侧栏点卡片、点记号)的日期范围,贯穿主副图的
         竖带:很淡的底 + 两侧深色实线边(拖选草稿是虚线边);范围伸出图窗的那一侧不画边 -->
    <div v-if="selectedBand" class="feedback-selected-band" data-testid="feedback-selected-band"
         :class="{ 'cut-left': selectedBand.cutLeft, 'cut-right': selectedBand.cutRight }"
         :style="{ left: `${selectedBand.left}px`, width: `${selectedBand.width}px` }" />
    <div v-if="fbHint" class="resize-stop" :data-testid="FB_HINT[fbHint.kind].testid"
         :style="{ left: `${fbHint.x + 12}px`, top: `${fbHint.y + 12}px` }">{{ FB_HINT[fbHint.kind].text }}</div>
    <!-- compare 的反馈作答面板(默认靠在竖带旁、贴住显示栏上沿,可拖走;状态在 stores/feedback.ts) -->
    <FeedbackPanel v-if="comparing && fb.panel" :feature-of="featureOfNode" :anchor="panelAnchor" @hover-node="onHoverNode" />
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
import { onMounted, onBeforeUnmount, ref, shallowRef, watch, computed, nextTick } from 'vue'
import * as echarts from 'echarts'
import { isBrushToggleKey } from './klineBrushKey'
import { isFeedbackOpenKey, walkKeyOf, type WalkFeedbackState } from './walkKey'
import { createBrushRequestHandler } from './klineBrushHandler'
import { computeRightAnchoredZoom } from './klineCtrlZoom'
import { storeToRefs } from 'pinia'
import { useViewStore } from '../stores/view'
import { dispatchDebugMenu, type MenuDispatch } from './KlineChart.debug-menu'
import { usePanelsStore } from '../stores/panels'
import { getAllOhlc, getOhlc } from '../api'
import { zoomForWindow } from '../annotate/viewWindow'
import {
  computeEventData, buildMainOption, buildSubOption, buildVolumeSeriesAndYAxis,
  emptyEventBundle, mainGridLayout, MAIN_GRID_LEFT, MAIN_GRID_RIGHT, type BandLabelExtra, type EventBundle,
} from '../render/chart'
import {
  computeSubGeometry, composeEffectiveSubH, SUB_CANVAS_MIN_H, MIN_SUB_H,
  MAIN_MIN_H, BAND_ZOOM_MIN, BAND_ZOOM_MAX, LS_KEY_BAND_ZOOM,
  BAND_ZOOM_STEP_BUTTON, BAND_ZOOM_STEP_WHEEL,
} from '../render/subGeometry'
import { ctrlState } from '../render/ctrlState'
import { bandKeyOf, nodeOfEventByBand, resolveTooltipData, windowOf, formatForwardReturn, subBandTagList } from '../render/visible'
import { peakIdIndex } from '../render/peakState'
import type { Bar } from '../types'
import type { Lane } from '../annotate/model'
import { handleAppClick, handleChartClick, handleShiftClick, MARKER_SERIES } from './KlineChart'
import WalkStatusBar from './WalkStatusBar.vue'
import ResizableDivider from './ResizableDivider.vue'
import CrosshairOverlay from './CrosshairOverlay.vue'
import FeedbackPanel from './FeedbackPanel.vue'
import { rangeBandPx, selectedBandPx, type PanelAnchor } from './feedbackPanel'
import { useAnnotationStore } from '../stores/annotation'
import { chartOf, computeLanes, type AnnBox } from '../annotate/model'
import { emptySlots } from '../annotate/membership'
import { boxMarks, resizeLimit, sampleLetters, sampleRange, sampleTag } from '../annotate/samples'
import { featureOrder, patternSamples } from '../annotate/grouping'
import {
  afterDimSeries, annotateDataZoom, annotateLayer, bracketContentBottom, bracketGeometry, buildAnnotateSubOption, laneGeometry,
  mainMarksSeries, mainSamplesSeries, packBrackets, triangleRect, BRACKET_ROW_H, COMPARE_BRACKET_ROW_H, LANES_TOP,
  type BracketItem, type Draft, type LaneGeom, type SampleMark,
} from '../render/annotateLanes'
import { createAnnotateGestures } from './annotateGestures'
import { useRefLayerStore } from '../stores/refLayers'
import { peaksSeries } from '../render/refLayers'
import { useAppLinkStore } from '../stores/appLink'
import { compareLinks } from '../render/compareLayout'
import { useCompareStore, SAMPLES_ROW } from '../stores/compare'
import { defaultFocus } from '../annotate/compareRead'
import { useCopyRefStore } from '../stores/copyRef'
import { useFeedbackStore } from '../stores/feedback'
import { useLandingStore } from '../stores/landing'
import { buyDatesIn, posSamplesInside } from '../annotate/feedback'
import { dateSpanToIdx, feedbackMarks, feedbackRowCount, feedbackTip } from '../render/feedbackStrip'

const view = useViewStore()
const { symbol, effectiveAnalysis, nodeColors, nodeVisible, level, tagMap, isolated,
        effectivePattern, effectiveScan, scanFile, focusedInstanceRef, diag,
        activePatternId, activeDetailCard, selectedHitId, candidateHitIds,
        highlightedEventIds, pendingDisambigInstanceId, shiftSelectedEventIds,
        focusedInstanceId, selectedInstanceId, compositionGroupIds, mode, annotating, viewWindow,
        comparing, linkedView, endNode, currentDay, activeFamilyKey } = storeToRefs(view)
// annotating(annotate、compare):画 K 线、成交量和用户的标注,不给框选诊断、driver 菜单。
// annotate 不画任何 app 产物;compare 的副图就是主视图那张(app 的族行、bracket 的 hit 行、档位、缩放、选中与当前日),
// 顶上让出用户区:特征轨在上、样本跨度那一行 user 在用户区最后,一道分界线下面就是 app 区(标注层,render/annotateLanes.ts
// 的 annotateLayer;两区的对应 render/compareLayout.ts);K 线区是 annotate 的标注层加上 app 模式 K 线区画的东西。
// wholeChart:图是这只股票截到训练段末日的全部 K 线(annotate、compare、现算的 app);扫描结果的 app 只画扫描窗口
const wholeChart = computed(() => mode.value !== 'app' || linkedView.value)
const appLink = useAppLinkStore()
const panels = usePanelsStore()
const { showSlider, subHeightOffset } = storeToRefs(panels)

// tooltip Refs 段的短标识注入:被引用的实例在图上叫什么。pk 语义(pk_id 字段)封装在
// peakState.ts(契约 C7 唯一落点),此处只调纯函数;非 pk 事件返回 null,渲染层只印 node_id。
const pkIdByInstance = computed(() => peakIdIndex(effectiveAnalysis.value?.events ?? []))
const refLabelOf = (id: string): string | null => {
  const n = pkIdByInstance.value.get(id)
  return n == null ? null : String(n)
}

const wrapEl = ref<HTMLElement | null>(null)
const mainEl = ref<HTMLElement | null>(null)
const subOuterEl = ref<HTMLElement | null>(null)
const subInnerEl = ref<HTMLElement | null>(null)
const bars = ref<Bar[]>([])
// annotate 下副图是用户的特征轨,框画在自己特征的轨上;画框、改起止的手势见 ./annotateGestures.ts
const ann = useAnnotationStore()
const draft = ref<Draft | null>(null)            // 正在拖出的新框
const preview = ref<AnnBox | null>(null)         // 正在改起止的框
const annDates = computed(() => bars.value.map(b => b.date))
// 参照层 peaks:开着、且当前模式可用时才画峰线(开关、换股票自动关见 stores/refLayers.ts)
const refs = useRefLayerStore()
const shownPeaks = computed(() => refs.peaks && refs.available ? refs.lines : [])
const annChart = computed(() => (ann.state ? chartOf(ann.state, symbol.value) : null))
// 轨序:当前 pattern 里各段的先后(annotate/grouping.ts 的 featureOrder),不在其中的特征按这张图上首次出现排
const annOrder = computed(() => featureOrder(ann.state ? patternSamples(ann.state, ann.currentPattern) : []))
const baseLanes = computed(() => {
  const chart = annChart.value
  return chart ? computeLanes(chart.boxes, chart.samples, (f) => ann.nameOf(f) ?? f, annDates.value, annOrder.value) : []
})
const cmp = useCompareStore()
const landing = useLandingStore()
// compare:app 跑完、当前 pattern 有 mapping 时,副图是主视图那张副图 + 标注层;还没跑完时照 annotate 只画标注
const compareReady = computed(() => comparing.value && !!effectiveAnalysis.value && !!effectivePattern.value
                                    && !!appLink.mapping && tagMap.value.tagList.length > 0)
// compare:map 了的特征这张图上还没有框时另起一条空轨(排在特征轨之后、unnamed 之前),标题照样写 ⇣ node,
// 可以直接在上面画框
const annLanes = computed<Lane[]>(() => {
  const base = baseLanes.value
  const features = compareReady.value ? appLink.mapping?.features : null
  if (!features) return base
  const have = new Set(base.map(l => l.key))
  const extra: Lane[] = Object.keys(features).filter(fid => !have.has(fid) && cmp.nodeOfFeature(fid) !== null)
    .sort((a, b) => ((ann.nameOf(a) ?? a) < (ann.nameOf(b) ?? b) ? -1 : 1))
    .map(fid => ({ key: fid, parent: null, rows: 1, boxes: [] }))
  const unnamed = base.findIndex(l => l.key === null)
  return unnamed < 0 ? [...base, ...extra] : [...base.slice(0, unnamed), ...extra, ...base.slice(unnamed)]
})
// compare 分两区:上区用户(特征轨照 annotate 顺序,样本跨度 user 行在最后),下区 app(和主视图一样);
// 这里只算两区之间的对应(轨 → node、unmapped、app_only、选中框要加粗的 band)
const cmpLayout = computed(() => {
  const pat = effectivePattern.value
  if (!compareReady.value || !pat || !appLink.mapping) return null
  const bands = subBandTagList(tagMap.value.tagList, pat.topology)
  return { bands, ...compareLinks(annLanes.value, bands, pat.topology, appLink.mapping.features,
                                  (fid) => ann.featureById.has(fid)) }
})
// compare 的反馈(spec 6.13):hits 行底下的反馈带画这只股票、当前 pattern、用户自己挑的反馈;配色照后端给的状态,
// 选中的那条(侧栏点行、点记号时设)描边加粗。app 模式不画(只在 renderCompareSub 里用)
const fb = useFeedbackStore()
const copyRef = useCopyRefStore()   // 「复制指代」:Shift+C 复制当前选中的东西;点轨名选中一个 node
const cmpFeedbackList = computed(() => (compareReady.value ? ann.feedbackOf(symbol.value) : []))
const cmpFeedbackMarks = computed(() =>
  feedbackMarks(cmpFeedbackList.value, annDates.value, fb.statusById, fb.selectedId))
/** 反馈带记号的悬停文字:悬停时现算(范围里有没有当前 pattern 的正样本) */
function feedbackTipOf(id: string): string {
  const f = cmpFeedbackList.value.find(x => x.id === id)
  if (!f) return ''
  const inside = posSamplesInside(annChart.value, ann.currentPattern, f.start, f.end).length > 0
  return feedbackTip(f, fb.statusById[id], inside, fb.placesById[id] ?? 1)
}
// 作答面板的 node 按钮:文字同 band 表头(node 名 + 对到它的用户特征名);悬停时那条 band 加亮
// (hoverBand,副图装饰层在那一行垫一条浅蓝底、描蓝边,离开即消失;面板关了也消失)
const hoverBand = ref<string | null>(null)
/** node 所在的 band(副图里的一行);band 键就是 node 名,或这一行合并了几个 node 时含它的那一行 */
function bandOfNode(node: string): string | null {
  const lay = cmpLayout.value
  if (!lay) return null
  if (lay.bands.includes(node)) return node
  return lay.bands.find(b => (tagMap.value.tagToNodes[b] ?? [b]).includes(node)) ?? null
}
function featureOfNode(node: string): string | null {
  const b = bandOfNode(node)
  return b ? bandExtras.value[b]?.feature ?? null : null
}
function onHoverNode(node: string | null) { hoverBand.value = node ? bandOfNode(node) : null }
watch(() => fb.panel, (p) => { if (!p) hoverBand.value = null })
// feedback 工具拖选中的竖带(相对 kline-wrap 的像素)与松开处的提示(视口坐标):范围里没有买点(拖出一段、
// 拖边改起止都会碰到),或拖边改出的范围和另一条反馈完全相同(防重复,不存)
const rangeBand = ref<{ left: number; width: number } | null>(null)
type FbHintKind = 'no_buy' | 'same_range'
const FB_HINT: Record<FbHintKind, { text: string; testid: string }> = {
  no_buy: { text: 'no buy in range', testid: 'feedback-no-buy' },
  same_range: { text: 'same range as another feedback', testid: 'feedback-same-range' },
}
const fbHint = ref<{ x: number; y: number; kind: FbHintKind } | null>(null)
const FB_HINT_MS = 2000
let fbHintTimer: ReturnType<typeof setTimeout> | null = null
function showFbHint(at: { x: number; y: number }, kind: FbHintKind) {
  fbHint.value = { ...at, kind }
  if (fbHintTimer) clearTimeout(fbHintTimer)
  fbHintTimer = setTimeout(() => { fbHint.value = null; fbHintTimer = null }, FB_HINT_MS)
}
/** 拖选范围 → 竖带:整根 K 线对齐主图的 x 轴(副图的 x 轴与它左右对齐),裁到图区内 */
function setRangeBand(r: { start: string; end: string } | null) {
  const el = mainEl.value
  if (!r || !chartMain || !el) { rangeBand.value = null; return }
  const dates = annDates.value
  const i0 = dates.indexOf(r.start), i1 = dates.indexOf(r.end)
  if (i0 < 0 || i1 < 0) { rangeBand.value = null; return }
  const main = chartMain
  const px = rangeBandPx(i0, i1, (i) => Number(main.convertToPixel({ xAxisIndex: 0 }, i)),
                         MAIN_GRID_LEFT, el.clientWidth - MAIN_GRID_RIGHT)
  rangeBand.value = px ? { left: px.left + mainCanvasOffsetX.value, width: px.width } : null
}
/** 这只股票、[start, end] 里有没有 app 的买点日(compare 且有现算结果时才算) */
function hasBuyIn(start: string, end: string): boolean {
  const a = effectiveAnalysis.value
  return !!(compareReady.value && a && symbol.value
    && buyDatesIn(a.hits, a.events, endNode.value, annDates.value, start, end).length)
}
/** 拖完一段(工具已熄):范围里有 app 的买点日就在松开处打开 range 面板,没有就在松开处提示 no buy in range */
function onRangeDone(start: string, end: string, at: { x: number; y: number }) {
  const sym = symbol.value
  if (!sym || !hasBuyIn(start, end)) { showFbHint(at, 'no_buy'); return }
  fb.open({ symbol: sym, start, end, target: 'range' })
}
/** 拖完选中那条反馈竖带的一条边(工具已熄):新范围里没有买点就不改、提示 no buy in range;
 *  否则交给 store 直接存(和另一条同范围时不存、提示;以前存下的没写 note 的,store 打开它的面板补 note) */
function onFeedbackResized(id: string, start: string, end: string, at: { x: number; y: number }) {
  if (!hasBuyIn(start, end)) { showFbHint(at, 'no_buy'); return }
  if (fb.resize(id, start, end) === 'same') showFbHint(at, 'same_range')
}
/** 选中的那条反馈(用户自己挑的、这只股票、当前 pattern;竖带画的就是它):拖它竖带的边改起止。
 *  作答面板开着、对着的不是它时,竖带画的是面板的范围,这时不认它的边(免得悬停在看不见的边上出改起止的光标) */
function selectedFeedbackRange(): { id: string; start: string; end: string } | null {
  if (fb.panel && fb.panel.editingId !== fb.selectedId) return null
  const id = fb.selectedId
  const f = id ? cmpFeedbackList.value.find(x => x.id === id && x.source === 'picked') : null
  return f ? { id: f.id, start: f.start, end: f.end } : null
}
// 作答面板管的那段日期(面板开着时),或选中的那条反馈的竖带(相对 kline-wrap 的像素):反馈是这只股票、当前 pattern、
// 用户自己挑的那条才有(同反馈带上画的)。面板开着时画面板的范围,面板放哪都能在图上看出它对着什么。
// 落点同拖选的竖带(整根 K 线对齐主图的 x 轴)。主图每画完一帧(平移、缩放、重画、改尺寸)重算一次,值没变不动
const selectedSpan = computed(() => {
  const p = fb.panel
  if (p && p.symbol === symbol.value) return dateSpanToIdx(annDates.value, p.start, p.end)
  const id = fb.selectedId
  const f = id ? cmpFeedbackList.value.find(x => x.id === id && x.source === 'picked') : null
  return f ? dateSpanToIdx(annDates.value, f.start, f.end) : null
})
const selectedBand = ref<{ left: number; width: number; cutLeft: boolean; cutRight: boolean } | null>(null)
function syncSelectedBand() {
  const span = selectedSpan.value
  const el = mainEl.value
  const main = chartMain
  const px = span && main && el
    ? selectedBandPx(span[0], span[1], (i) => Number(main.convertToPixel({ xAxisIndex: 0 }, i)),
                     MAIN_GRID_LEFT, el.clientWidth - MAIN_GRID_RIGHT)
    : null
  const next = px ? { ...px, left: px.left + mainCanvasOffsetX.value } : null
  const cur = selectedBand.value
  if (cur?.left === next?.left && cur?.width === next?.width
      && cur?.cutLeft === next?.cutLeft && cur?.cutRight === next?.cutRight) return
  selectedBand.value = next
}
// compare 的用户区:特征轨从顶上排起(不随 band zoom 变),user 行接在它们下面
const cmpUserLanes = computed(() => laneGeometry(annLanes.value, LANES_TOP))
// compare 副图的总高(画的时候算出来)
const cmpGeom = shallowRef<{ height: number } | null>(null)
/**
 * 侧栏卡片的 edit(stores/feedback.ts 的 editRequest,落到那段日期之后才提):等落下那天引起的重画做完,
 * 选中那条并打开它的面板(预填),等同选中它再按 Enter。图上没有这条记号(app 没跑成、已被删)时不开。
 */
watch(() => fb.editRequest, async (id) => {
  if (!id) return
  await nextTick()
  if (fb.editRequest !== id) return
  fb.takeEditRequest()
  if (!cmpFeedbackMarks.value.some(m => m.id === id)) return
  fb.select(id)
  fb.open({ id })
})

// ── 反馈面板:对选中的那一个打开(Enter、显示栏的 feedback 按钮);默认落点 ──
/** 焦点在这些容器里时 Enter 归它们,不开反馈面板:对话框(扫描配置、停止扫描等的 .backdrop)、pattern 选择框、右键菜单 */
const ENTER_KEEPS = '.backdrop, [role="dialog"], dialog, .pattern-picker, .driver-menu'
/** 显示栏 feedback 按钮的样子:不在 compare 没有按钮;面板开着 open;能作答(app 跑完、选中的是买点日 / 它上面的
 *  一次 hit / 一族 / 一条反馈)on;否则 off */
const walkFeedback = computed<WalkFeedbackState | undefined>(() => {
  if (!comparing.value) return undefined
  if (fb.panel) return 'open'
  return compareReady.value && fb.selTarget ? 'on' : 'off'
})
/** 对选中的那一个打开面板;返回开没开 */
function openSelectedFeedback(): boolean {
  return compareReady.value && fb.openSelected()
}
/** 显示栏的 feedback 按钮:面板开着就关(不存),没开就对选中的那一个打开 */
function toggleFeedbackPanel() {
  if (fb.panel) fb.close()
  else openSelectedFeedback()
}
const walkBarRef = ref<InstanceType<typeof WalkStatusBar> | null>(null)
/** 面板默认落点要用的几样(视口坐标):竖带露在图区里的左右、显示栏的上沿、图表区的左右。面板开着时,
 *  主图每画完一帧、竖带重算之后量一次,值没变不动 */
const panelAnchor = shallowRef<PanelAnchor | null>(null)
function syncPanelAnchor() {
  const wrap = wrapEl.value
  const bar = walkBarRef.value?.$el as HTMLElement | undefined
  if (!fb.panel || !wrap || !bar) { if (panelAnchor.value) panelAnchor.value = null; return }
  const w = wrap.getBoundingClientRect()
  const b = selectedBand.value
  const next: PanelAnchor = {
    band: b ? { left: w.left + b.left, right: w.left + b.left + b.width } : null,
    bottom: bar.getBoundingClientRect().top, left: w.left, right: w.right,
  }
  const cur = panelAnchor.value
  if (cur && cur.bottom === next.bottom && cur.left === next.left && cur.right === next.right
      && cur.band?.left === next.band?.left && cur.band?.right === next.band?.right) return
  panelAnchor.value = next
}
// compare:选中的框所在特征轨对的 node(及子孙)的 band,表头加粗
const cmpLinkedBands = computed<string[]>(() => {
  const lay = cmpLayout.value
  const id = ann.selectedBoxId
  if (!lay || !id) return []
  const li = annLanes.value.findIndex(l => l.boxes.some(b => b.box.id === id))
  return (lay.linkedBands.get(li) ?? []).map(b => lay.bands[b])
})
const APP_ONLY_TIP = 'app_only: none of your features is mapped to this part of the app; the app checks something you did not annotate'
// band 表头:node 名后跟用户的特征名(mapping 对到它的特征;app 模式与 compare 都写);compare 下所在组没有 node 被 map 的挂 app_only
const shownMapping = computed(() => {
  if (comparing.value) return appLink.mapping
  const ms = (appLink.mappings ?? []).filter(m => m.app === view.appId && !m.problem)
  return ms.find(m => m.pattern === ann.currentPattern) ?? ms[0] ?? null
})
const bandExtras = computed<Record<string, BandLabelExtra>>(() => {
  const out: Record<string, BandLabelExtra> = {}
  const m = shownMapping.value
  const tags = tagMap.value.tagList
  if (m) {
    for (const tag of tags) {
      const nodes = tagMap.value.tagToNodes[tag] ?? [tag]
      const names = Object.entries(m.features).filter(([fid, node]) => ann.featureById.has(fid) && nodes.includes(node))
        .map(([fid]) => ann.nameOf(fid) ?? fid)
      if (names.length) out[tag] = { feature: names.join(' / ') }
    }
  }
  const lay = cmpLayout.value
  if (lay) for (const b of lay.appOnly) out[lay.bands[b]] = { ...out[lay.bands[b]], tag: 'app_only', tagTip: APP_ONLY_TIP }
  return out
})
// 样本:字母(当前 pattern)、选中的样本(在这张图上)、它的空槽、框旁的标记、bracket 轨
const annLetters = computed(() => sampleLetters(annChart.value, ann.currentPattern))
const annSelSample = computed(() =>
  (ann.selectedSample && ann.selectedSample.chart.symbol === symbol.value ? ann.selectedSample.sample : null))
const annSlots = computed(() => (annSelSample.value && ann.state && ann.membership && symbol.value
  ? emptySlots(ann.state.charts, symbol.value, annSelSample.value.id, annDates.value, ann.membership.near) : []))
const annMarks = computed(() => boxMarks(annChart.value, ann.currentPattern, annSelSample.value, annSlots.value))
const annBracket = computed(() => {
  const chart = annChart.value
  const reads = compareReady.value ? cmp.sampleReads : null
  const items: BracketItem[] = (chart?.samples ?? []).map(smp => {
    const r = reads?.get(smp.id)
    const off = r?.match.offset
    return {
      id: smp.id, ...sampleRange(smp, chart!), pos: smp.judgment === 'pos', letter: annLetters.value.get(smp.id) ?? null,
      faded: smp.pattern !== ann.currentPattern,
      emphasis: smp.id === ann.selectedSampleId ? 2 : smp.id === ann.currentSampleId ? 1 : 0,
      // compare:▲ 字母后的 ✓ / ✗(app 与这个样本的判断一致与否),matched / unmatched 与买点差几根在悬停
      mark: r ? { sign: r.mark, tip: `${r.match.state}${off != null ? ` · buy ${off >= 0 ? '+' : ''}${off}` : ''}` } : null,
    }
  })
  const { rows, placed } = packBrackets(items, annDates.value)
  // compare 下这是用户区的最后一行 user(行高放大,接在特征轨下面),隔着两区的分界线与下面 app 的 hits 对照
  if (compareReady.value) {
    const lanes = cmpUserLanes.value.geom
    const top = lanes.length ? lanes[lanes.length - 1].top + lanes[lanes.length - 1].h : LANES_TOP
    return { geom: bracketGeometry(rows, COMPARE_BRACKET_ROW_H, top), placed }
  }
  return { geom: bracketGeometry(rows, BRACKET_ROW_H), placed }
})
const annSampleMarks = computed<SampleMark[]>(() => (annChart.value?.samples ?? []).map(smp => ({
  id: smp.id, date: smp.date, pos: smp.judgment === 'pos', selected: smp.id === ann.selectedSampleId,
  faded: smp.pattern !== ann.currentPattern, letter: annLetters.value.get(smp.id) ?? null,
})))
const annGeom = computed(() => (compareReady.value
  ? { geom: cmpUserLanes.value.geom, height: cmpGeom.value?.height ?? cmpUserLanes.value.height }
  : laneGeometry(annLanes.value, annBracket.value.geom.top + annBracket.value.geom.h)))
const resizeStop = ref<{ x: number; y: number; text: string } | null>(null)   // 改起止停在样本日时的提示(页面坐标)
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
// 悬停提示什么时候不弹:右键菜单开着时两张图都不弹;反馈作答面板开着时副图也不弹——面板里已有悬停提示的
// 全部内容,而点记号打开面板时鼠标正停在记号上,提示不收会一直挂着。主图的 K 线数值提示照常,写 note 时还能对着看。
const mainTipOff = computed(() => contextMenuVisible.value)
const subTipOff = computed(() => contextMenuVisible.value || !!fb.panel)
/** 把「弹不弹」套到一张图上;不弹时顺手收起已经挂着的提示 */
function applyTipOff(chart: any, off: boolean): void {
  if (!chart) return
  chart.setOption({ tooltip: { triggerOn: off ? 'none' : 'mousemove|click' } } as any, { lazyUpdate: true } as any)
  if (off) chart.dispatchAction({ type: 'hideTip' })
}
/** 全量替换(notMerge)重画后 triggerOn 回到默认,要重新套上 */
function reapplyTipOff(): void {
  if (mainTipOff.value) applyTipOff(chartMain, true)
  if (subTipOff.value) applyTipOff(chartSub, true)
}
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
  if (annotating.value) return
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
print(f"hits: {len(result.hits)}, gate_failures: {len(collector.snapshot())}")
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
// 从 localStorage 初始化,parse 失败 / NaN / out-of-range 回 default。
// compare 单独一份、默认放大一档:副图里多了用户轨和 user 行(▲ 与 ✓ / ✗),按主视图的 1.0× 每条轨不到 20 像素,
// 第一屏读不出;放大只改行高,画出来的东西和主视图同一套。
const LS_KEY_BAND_ZOOM_COMPARE = `${LS_KEY_BAND_ZOOM}-compare`
const COMPARE_BAND_ZOOM_DEFAULT = 2.0   // 待验证:在真图上定
function loadBandZoom(key = LS_KEY_BAND_ZOOM, dflt = 1.0): number {
  const raw = parseFloat(localStorage.getItem(key) ?? '')
  if (!Number.isFinite(raw) || raw < BAND_ZOOM_MIN || raw > BAND_ZOOM_MAX) return dflt
  return raw
}
const bandZoomApp = ref<number>(loadBandZoom())
const bandZoomCmp = ref<number>(loadBandZoom(LS_KEY_BAND_ZOOM_COMPARE, COMPARE_BAND_ZOOM_DEFAULT))
const bandZoomFactor = computed<number>({
  get: () => (comparing.value ? bandZoomCmp.value : bandZoomApp.value),
  set: (v) => { if (comparing.value) bandZoomCmp.value = v; else bandZoomApp.value = v },
})
// ↺ 复位到的值:app 1.0×,compare 它自己的默认
const bandZoomHome = computed(() => (comparing.value ? COMPARE_BAND_ZOOM_DEFAULT : BAND_ZOOM_MIN))
const containerH = ref<number>(0)   // wrapEl 高度,ResizeObserver 更新

// 计算副图 canvas 需要的高度
const subCanvasH = ref<number>(SUB_CANVAS_MIN_H)  // 首帧兜底

// 副图容器高度合成:fit(offset=null)贴合内容;负 offset = drag 藏掉的像素数,
// zoom 只改 subCanvasH → 分界线随 zoom 移动而隐藏量守恒。
// spec: 2026-07-03-subchart-boundary-model-design.md §1/§2
// 上限:容器高减去主图至少要留的 MAIN_MIN_H,内容再高也不把 K 线主图挤掉(多出来的在副图里滚);容器还没量出高度时不设
const effectiveSubH = computed(() => composeEffectiveSubH(subCanvasH.value, subHeightOffset.value,
                                                          containerH.value > 0 ? containerH.value - MAIN_MIN_H : Infinity))

let chartMain: echarts.ECharts | null = null
let chartSub: echarts.ECharts | null = null
let roMain: ResizeObserver | null = null
let roSub: ResizeObserver | null = null
let roWrap: ResizeObserver | null = null
let unsubCtrl: (() => void) | null = null
let lastMarkLineKey: string | null = null

// 只认最后一次请求的结果:连续换股时,先发的慢响应不能盖掉后发的(否则标题和 K 线对不上)
let barsSeq = 0
async function reloadBars() {
  const seq = ++barsSeq
  const sym = symbol.value
  let next: Bar[] = []
  if (wholeChart.value) {
    // 按代码打开:这只股票的全部 K 线(后端截到训练段末日);compare 与现算的 app 也画这一份(app 的下标和它逐根对齐)
    if (sym) {
      try { next = (await getAllOhlc(sym)).bars }
      catch (e: any) {
        if (seq === barsSeq) view.showToast(`${sym}: ${e?.status === 404 ? 'not_found' : 'load_failed'}`)
      }
    }
  } else if (sym && scanFile.value) {
    const { start, end } = windowOf(effectiveScan.value ?? scanFile.value.scan)
    try { next = (await getOhlc(sym, start, end)).bars } catch { next = [] }
  }
  if (seq !== barsSeq) return
  bars.value = next
  view.setBarDates(next.map(b => b.date))
  if (annotating.value && sym && next.length) ann.setDays(sym, next.map(b => b.date))
}

function strictWindowIdx(): { startIdx: number; endIdx: number } | null {
  if (linkedView.value) return null                 // 现算的 app 跑的是全部 K 线,没有缓冲段
  const s = scanFile.value?.scan
  if (!s || !s.win_start || s.win_start === s.start_date) return null
  const startIdx = bars.value.findIndex((b) => b.date >= s.start_date)
  let endIdx = -1
  for (let i = bars.value.length - 1; i >= 0; i--) {
    if (bars.value[i].date <= s.end_date) { endIdx = i; break }
  }
  return startIdx >= 0 && endIdx >= 0 ? { startIdx, endIdx } : null
}

function hitLabel(hitId: string): string | null {
  const m = effectiveAnalysis.value?.hits.find((mm) => mm.hit_id === hitId)
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
  const bundle = computeEventData(bars.value, effectiveAnalysis.value.events, effectiveAnalysis.value.hits, params)
  return computeSubGeometry(laneCountsOf(bundle), z)
}

// bracket 区 hit 的行数、每条 band 的行数(由 computeEventData 排好的 lane 号读出)
function laneCountsOf(bundle: EventBundle): { bracketLaneCount: number; bandLaneCounts: number[]; bracketCountLanes: number[] } {
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
  // 带个数行的 hit 行:这一行里有哪天并了几次 hit(买入日 ▼ 的 hit_ids 不止一个)
  const bracketCountLanes = [...new Set(bundle.bracketData
    .filter((d: any) => d.kind === 'buy' && (d.hit_ids?.length ?? 0) >= 2).map((d: any) => d.value[2] as number))]
  return { bracketLaneCount, bandLaneCounts, bracketCountLanes }
}

// factorCap(spec §6.1):naturalSubH_at_1(bandZoomFactor=1 时的副图 canvas 高)决定 zoom 上限。
// 若 wrap 剩余空间(containerH - MAIN_MIN_H)不足容纳 naturalSubH_at_1 → factorCap = 1.0(zoom 不可用)。
// 封顶对象维持内容高度口径(boundary-model spec §4:不随 offset 放宽)。
// 它不计 compare 的用户区和反馈行(口径与 deriveSubGeometry 一致):compare 下估矮了,最多让副图出滚动条。
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
  localStorage.setItem(comparing.value ? LS_KEY_BAND_ZOOM_COMPARE : LS_KEY_BAND_ZOOM, String(clamped))
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
  setBandZoom(bandZoomHome.value)
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

function onSubScroll() { fb.close() }

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

// 按键走动(← / →、↑ / ↓、Esc 退一层)把当前日带出了视窗:平移到让它进来,两边留几根 K 线,视窗宽度不变。
// 这种平移不是用户拖出来的,不关反馈面板(walkPanning 期间 datazoom 的监听跳过)。
const WALK_PAN_MARGIN = 5
let walkPanning = false
function panToCurrentDay() {
  const day = view.currentDay
  const n = bars.value.length
  const cur = readZoomOverride()
  if (day === null || n < 2 || !cur || !chartMain) return
  const from = (cur.start / 100) * (n - 1)
  const to = (cur.end / 100) * (n - 1)
  const width = to - from
  const margin = Math.min(WALK_PAN_MARGIN, Math.max(0, width / 2 - 1))
  let nf = from
  if (day < from + margin) nf = day - margin
  else if (day > to - margin) nf = day + margin - width
  else return
  nf = Math.max(0, Math.min(nf, n - 1 - width))
  walkPanning = true
  chartMain.dispatchAction({ type: 'dataZoom', start: (nf / (n - 1)) * 100, end: ((nf + width) / (n - 1)) * 100 })
  walkPanning = false
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
      resolveTooltipData(id, diag.value, effectiveAnalysis.value?.events ?? [], bars.value,
                         refLabelOf),
    strictWindow: strictWindowIdx(),
    hitLabel,
    sliderShow: showSlider.value,
    zoomOverride: readZoomOverride(),
    endNode: endNode.value ?? undefined,
    selectedHitId: selectedHitId.value,
    candidateHitIds: candidateHitIds.value,
    // 组成型组「一选全选」:0 归属非 hit 组的选中集并入 group 高亮
    // (chart group 分支按 focusedInstanceRef 排除点击者 → 点击者 focus 框独家,
    // 组员 group 框;hit 组时本集为空,由 inHitIds 闭包独占)。
    highlightedEventIds: new Set([...highlightedEventIds.value, ...compositionGroupIds.value]),
    pendingDisambigInstanceId: pendingDisambigInstanceId.value,
    shiftSelectedEventIds: shiftSelectedEventIds.value,
    hits: effectiveAnalysis.value?.hits ?? [],
    events: effectiveAnalysis.value?.events ?? [],
    currentDay: currentDay.value,
    activeFamily: activeFamilyKey.value,
    bandExtras: bandExtras.value,
    selectedBand: copyRef.selectedNode,
    onBandLabelClick: (band: string) => copyRef.selectNode(band),
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

// annotate:主图只有 K 线 + 成交量,副图是用户的特征轨。换图时(forceResetZoom)停在打开时给的图窗上,
// 没给就按默认缩放。K 线区的拖动留给画框,所以关掉拖动平移,缩放滑块常显(在成交量带上拖也能平移)。
function renderBarsOnly(forceResetZoom: boolean) {
  if (!chartMain || !chartSub) return
  if (!bars.value.length) {
    subCanvasH.value = computeSubGeometry({ bracketLaneCount: 0, bandLaneCounts: [] }).subCanvasH
    chartSub.clear()
    chartMain.clear()
    return
  }
  const zoomOverride = forceResetZoom
    ? (viewWindow.value ? zoomForWindow(bars.value.map(b => b.date), viewWindow.value) : null)
    : readZoomOverride()
  const cmpOn = compareReady.value && !!cmpBundle
  const input = cmpOn ? { ...buildRenderInput(), sliderShow: true, zoomOverride } : { sliderShow: true, zoomOverride }
  // compare:K 线区和 app 模式画的一样(画在价格区的 node 的记号、它们的高亮、当前日竖线);annotate 只有 K 线
  const mainBundle = cmpOn ? cmpBundle! : emptyEventBundle(bars.value)
  const mainOpt = buildMainOption(bars.value, mainBundle, input,
                                  { getChartEl: () => mainEl.value, height: chartMain.getHeight() }) as any
  mainOpt.dataZoom[0].moveOnMouseMove = false
  // 主图上的标注层(选中的框、样本日之后暗一档)是一段:只要有一端在图窗里、或横跨整个图窗就照画。
  // 默认的 filter 要两端都在图窗里,图窗没拉到最后一根时「暗一档」整条消失;K 线、成交量只有一个 x,两种筛法一样
  for (const dz of mainOpt.dataZoom) dz.filterMode = 'weakFilter'
  // 滑块贴底,放在日期刻度下面(按百分比放会在高的窗口里压住成交量带)
  const slider = mainOpt.dataZoom[1]
  delete slider.top
  Object.assign(slider, { bottom: 6, height: 22 })
  mainOpt.series.push(mainMarksSeries(annDates.value, null, null), mainSamplesSeries(bars.value, []),
                      afterDimSeries(annDates.value, null), peaksSeries(annDates.value, shownPeaks.value))
  chartMain.setOption(mainOpt, true)
  reapplyTipOff()
  lastMarkLineKey = null
  renderAnnotateLayers()
}

// compare 的 app 产物(族行、hit 行、当前日):app 那边的状态变了(render)才重算,框变了只重画标注层时沿用
let cmpBundle: EventBundle | null = null

// annotate 的两层:副图的特征轨与框,主图 K 线区上选中的框、正在拖的框。框变了只重画这两层,不动 K 线与缩放
function renderAnnotateLayers() {
  if (!annotating.value || !chartMain || !chartSub || !bars.value.length) return
  if (compareReady.value) renderCompareSub()
  else {
    cmpGeom.value = null
    const { geom, height } = annGeom.value
    subCanvasH.value = height
    chartSub.setOption(buildAnnotateSubOption(bars.value, {
      lanes: annLanes.value, geom, nameOf: ann.nameOf, selectedId: ann.selectedBoxId,
      preview: preview.value, draft: draft.value, zoom: readZoomOverride(), width: chartSub.getWidth(),
      bracket: annBracket.value, marks: annMarks.value,
    }) as any, true)
    reapplyTipOff()
  }
  const sel = ann.selectedBox?.box ?? null
  const shownSel = sel && preview.value?.id === sel.id ? preview.value : sel
  chartMain.setOption({ series: [
    mainMarksSeries(annDates.value, shownSel, draft.value ?? preview.value),
    mainSamplesSeries(bars.value, annSampleMarks.value),
    afterDimSeries(annDates.value, annSelSample.value?.date ?? null),
  ] })
}

// compare 的副图:主视图那张副图(buildSubOption,app 的 hit 行与族行,顶上让出用户区),
// 再合进标注层(annotateLayer:用户区的特征轨与 user 行、⇣ / unmapped / ✓ ✗、两区分界的分界线)
function renderCompareSub() {
  const lay = cmpLayout.value
  if (!chartSub || !lay || !effectiveAnalysis.value) return
  const bundle = cmpBundle ?? (cmpBundle = computeEventData(bars.value, effectiveAnalysis.value.events,
                                                            effectiveAnalysis.value.hits, buildRenderInput()))
  const zoom = readZoomOverride()
  const marks = cmpFeedbackMarks.value
  const params = { ...buildRenderInput(), zoomOverride: zoom, zoomFactor: bandZoomFactor.value,
                   linkedBands: cmpLinkedBands.value, feedback: { marks, tip: feedbackTipOf },
                   hoverBand: hoverBand.value }
  const bg = annBracket.value.geom
  const subGeom = computeSubGeometry({ ...laneCountsOf(bundle), userContentBottom: bracketContentBottom(bg),
                                       feedbackRowCount: feedbackRowCount(marks) }, bandZoomFactor.value)
  subCanvasH.value = subGeom.subCanvasH
  cmpGeom.value = { height: subGeom.subCanvasH }
  const opt: any = buildSubOption(bars.value, bundle, subGeom, params, chartSub.getWidth(),
                                  { getChartEl: () => subInnerEl.value })
  const layer = annotateLayer(bars.value, {
    lanes: annLanes.value, geom: cmpUserLanes.value.geom, nameOf: ann.nameOf, selectedId: ann.selectedBoxId,
    preview: preview.value, draft: draft.value, zoom, width: chartSub.getWidth(),
    bracket: annBracket.value, marks: annMarks.value,
    compare: { laneNode: lay.laneNode, unmapped: lay.unmapped,
               userActive: activeFamilyKey.value === SAMPLES_ROW, edges: subGeom.userAppEdges },
  })
  opt.graphic.push(...layer.graphics)
  opt.series.push(...layer.series)
  opt.dataZoom = [annotateDataZoom(zoom)]
  chartSub.setOption(opt, true)
  reapplyTipOff()
}

// 参照层开关或峰变了:只重画峰线这一个系列
function renderRefLayers() {
  if (!annotating.value || !chartMain || !bars.value.length) return
  chartMain.setOption({ series: [peaksSeries(annDates.value, shownPeaks.value)] })
}

/** 主图上这一点(相对主图容器)落在哪个样本的三角上;后画的盖在上面,倒着找。 */
function sampleAtMain(x: number, y: number): string | null {
  if (!chartMain) return null
  const dates = annDates.value
  const marks = annSampleMarks.value
  for (let k = marks.length - 1; k >= 0; k--) {
    const i = dates.indexOf(marks[k].date)
    if (i < 0) continue
    const [px, py] = chartMain.convertToPixel({ xAxisIndex: 0, yAxisIndex: 0 }, [i, bars.value[i].l]) as number[]
    const r = triangleRect(px, py)
    if (x >= r.left && x <= r.right && y >= r.top && y <= r.bottom) return marks[k].id
  }
  return null
}

// 主图容器高度变了:按新高度重排 K 线区与成交量带(成交量带高 = K 线区的 VOLUME_HEIGHT_RATIO)
function relayoutMainGrid() {
  if (!chartMain || !bars.value.length || !(chartMain.getOption() as any)?.grid) return
  chartMain.setOption({ grid: mainGridLayout(chartMain.getHeight(), annotating.value || showSlider.value) })
}

function render(forceResetZoom = false) {
  if (annotating.value) {
    // compare:app 那边的状态(产物、档位、选中、当前日)变了才走到这里,重算 app 产物再画
    cmpBundle = compareReady.value && effectiveAnalysis.value
      ? computeEventData(bars.value, effectiveAnalysis.value.events, effectiveAnalysis.value.hits, buildRenderInput())
      : null
    renderBarsOnly(forceResetZoom)
    return
  }
  if (!chartMain || !chartSub) return
  if (!effectiveAnalysis.value || !effectivePattern.value) {
    // 现算的 app 还没跑完(或没跑成):先只画 K 线,副图清空
    if (linkedView.value) { renderBarsOnly(forceResetZoom); chartSub.clear() }
    return
  }
  const params = { ...buildRenderInput(), zoomOverride: forceResetZoom ? null : readZoomOverride() }
  const bundle = computeEventData(bars.value, effectiveAnalysis.value.events, effectiveAnalysis.value.hits, params)
  const subGeom = deriveSubGeometry()

  // 更新 subCanvasH → sub-inner div 高度触发 chartSub 容器 resize
  subCanvasH.value = subGeom.subCanvasH

  const mainOpt = buildMainOption(bars.value, bundle, params,
                                  { getChartEl: () => mainEl.value, height: chartMain.getHeight() })
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
  reapplyTipOff()
  lastMarkLineKey = null
}

function onKeyDown(e: KeyboardEvent) {
  const t = e.target as HTMLElement | null
  // 输入框内不响应任何全局快捷键(承 Esc/Shift+, 共用同一守卫)。
  if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return
  // Shift+,:切换框选光标态(与按钮 toggleBrush 同一路径 · 双向 toggle)。
  // Shift+,(key '<')不进搜索框:onGlobalCharKey 已整体屏蔽 shift(无需逐键让位)。
  // Shift+B(annotate、compare 下):点亮 / 熄灭 box 工具。单个字母会被左侧列表的「敲字母搜股票」抢走,所以带 Shift
  if (annotating.value && e.code === 'KeyB' && e.shiftKey && !e.ctrlKey && !e.metaKey && !e.altKey && !e.isComposing) {
    annGestures.cancel()
    ann.toggleTool('box')
    e.preventDefault()
    return
  }
  // Shift+F(compare 下):点亮 / 熄灭 feedback 工具(同 Shift+B 的写法)
  if (comparing.value && e.code === 'KeyF' && e.shiftKey && !e.ctrlKey && !e.metaKey && !e.altKey && !e.isComposing) {
    annGestures.cancel()
    ann.toggleTool('feedback')
    e.preventDefault()
    return
  }
  // Shift+C:把选中的那一个(没选中时是当前日)写成一行复制出去(见 stores/copyRef.ts)。
  // 单个字母会被左侧列表的「敲字母搜股票」抢走,所以带 Shift(同 Shift+B)
  if (e.code === 'KeyC' && e.shiftKey && !e.ctrlKey && !e.metaKey && !e.altKey && !e.isComposing) {
    copyRef.copy()
    e.preventDefault()
    return
  }
  // Enter(compare 下):选中的那一个能作答时,对它打开反馈面板(stores/feedback.ts 的 selTarget)。
  // 面板开着时 Enter 归面板(保存),在捕获阶段就被截下,走不到这里。焦点停在别处的按钮、链接上(多半是刚用鼠标
  // 点过的:图上按下鼠标不夺焦点)也照样开面板,并截下浏览器默认的「Enter 点按钮」、放掉那个焦点;
  // 不能作答时不接,按钮照常吃 Enter。下拉框里的 Enter 归下拉框(输入框、文本区开头已整体放行);对话框、
  // pattern 选择框、右键菜单里的按钮也归它们自己(多半是用 Tab 走过去的,Enter 就是要点它)
  if (comparing.value && isFeedbackOpenKey(e) && t?.tagName !== 'SELECT' && !t?.closest?.(ENTER_KEEPS)) {
    if (fb.panel || !compareReady.value || !fb.selTarget) return
    e.preventDefault()
    if (t && t !== document.body) t.blur()
    openSelectedFeedback()
    return
  }
  if (isBrushToggleKey(e)) {
    if (annotating.value) return
    toggleBrush()
    e.preventDefault()
    return
  }
  // 按键走动(键的判定与显示栏上的键名同在 walkKey.ts):← / → 跨天(竖线会动),↑ / ↓ 留在同一天(竖线不动);
  // 进去还是换到旁边由 stores/view.ts 照同一个判断定。没有选中时不接:← / → 照常归别处,↑ / ↓ 在页面上什么都不做
  // (不滚动;切股票是 PageUp / PageDown)
  const wk = walkKeyOf(e)
  if (wk && t?.tagName !== 'SELECT') {
    const lineBefore = view.currentDay
    const taken = wk.kind === 'stack' ? view.stepStack(wk.dir) : view.stepPos(wk.dir)
    // 只有这一下把竖线带到了别的日子才平移(到头、换到旁边一族、进到同一天的某一次都不动视窗)
    if (taken) { e.preventDefault(); if (view.currentDay !== lineBefore) panToCurrentDay() }
    else if (wk.kind === 'stack' && (!t || t === document.body)) e.preventDefault()
    return
  }
  if (e.key !== 'Escape') return
  if (contextMenuVisible.value) { contextMenuVisible.value = false; return }
  // 工具亮着时 Esc 只熄灭工具,选中的框、样本和当前样本都留着(画到一半退出,接着画的框照样并进当前样本)
  // (反馈面板开着时 Esc 先归面板:FeedbackPanel 在捕获阶段截下,只关面板,走不到这里)
  if (annotating.value && ann.tool) {
    annGestures.cancel()
    ann.tool = null
    ;(document.activeElement as HTMLElement | null)?.blur()
    return
  }
  // Esc 一下退一件,先退最后开始的:反馈面板(面板自己截下)→ 亮着的工具(上面)→ 进行到一半的 Shift 配对
  // → 选中的东西往外退一层 → 退到最外一层后再按才全清
  if (view.shiftPairPending) {
    view.clearShiftSelection()
    ;(document.activeElement as HTMLElement | null)?.blur()
    return
  }
  if (view.selPath.length > 1) {
    const lineBefore = view.currentDay
    view.stepUp()
    if (view.currentDay !== lineBefore) panToCurrentDay()   // 竖线没动(退到一族、一条反馈)就不动视窗
    ;(document.activeElement as HTMLElement | null)?.blur()
    return
  }
  if (annotating.value) { annGestures.cancel(); ann.clearSelection() }
  fb.select(null)                                     // 选中的反馈(粗边与竖带)也一并取消
  copyRef.selectNode(null)                            // 选中的轨名也取消
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

// ── annotate 下的画框手势 ──────────────────────────────────────────────
const annGestures = createAnnotateGestures({
  main: () => chartMain, sub: () => chartSub, mainEl: () => mainEl.value, subEl: () => subInnerEl.value,
  active: () => annotating.value && bars.value.length > 0 && ann.status === 'ready',
  tool: () => ann.tool,
  toolDone: () => { ann.tool = null },
  dates: () => annDates.value, lanes: () => annLanes.value, geom: () => annGeom.value.geom,
  bracket: () => annBracket.value, marks: () => annMarks.value,
  zoom: () => readZoomOverride(),
  sampleAt: sampleAtMain,
  limitOf: (boxId) => {
    const chart = annChart.value
    const smp = chart ? resizeLimit(boxId, chart) : null
    if (!chart || !smp) return null
    const letter = smp.pattern === ann.currentPattern ? annLetters.value.get(smp.id) : null
    return { date: smp.date, text: `member box of ${sampleTag(smp, letter)}` }
  },
  setDraft: (d) => { draft.value = d },
  setRange: setRangeBand,
  rangeDone: onRangeDone,
  selectedFeedback: selectedFeedbackRange,
  resizeFeedback: onFeedbackResized,
  setPreview: (b) => { preview.value = b },
  setStop: (st) => { resizeStop.value = st },
  createBox: (start, end, feature) => { if (symbol.value) ann.createBox(symbol.value, start, end, feature) },
  resizeBox: (id, start, end) => ann.resizeBox(id, start, end),
  select: (id) => {
    if (!id) { ann.clearSelection(); return }
    ann.selectBox(id)
    if (compareReady.value) cmp.focusBox(id, { reset: true })   // 再点同一个框也回到只选中它(点过 app 的格、按键进去之后)
  },
  selectSample: (id) => {
    ann.selectSample(id)
    if (compareReady.value && id) cmp.focusSample(id, { reset: true })
  },
  placeSample: (date) => { if (symbol.value && date) ann.placeSample(symbol.value, date) },
  take: (boxId) => { if (annSelSample.value) ann.toggleMember(annSelSample.value.id, boxId) },
  // compare:用户区(特征轨与 user 行)归画框手势,下面 app 区的 hit 行、band 留给图表的点击
  claims: (y) => {
    if (!compareReady.value) return true
    const bg = annBracket.value.geom
    return y < bg.top + bg.h
  },
})

// 换股票、换模式时熄灭工具:亮着的工具只对眼前这张图用一次
watch([symbol, mode], () => { ann.tool = null })

// 副图竖直缩放控件的落点:顶栏里的 #band-zoom-slot(ChartArea,annotate 以外的模式才有)。
// 每次换模式等 DOM 更新完再找;找不到(单独挂载本组件时)就不画控件。
const zoomSlot = shallowRef<HTMLElement | null>(null)
const findZoomSlot = () => { zoomSlot.value = document.getElementById('band-zoom-slot') }
watch(mode, findZoomSlot, { flush: 'post' })

// ── 挂钩 chart 生命周期 ─────────────────────────────────────────────
onMounted(() => {
  findZoomSlot()
  window.addEventListener('keydown', onKeyDown)
  document.addEventListener('click', handleDocumentClick)

  chartMain = echarts.init(mainEl.value!)
  chartSub  = echarts.init(subInnerEl.value!)
  // annotate 下的鼠标样式(工具亮着时十字、能点的地方是手):挂在图表自己的 mousemove 上,
  // 它先按悬停的元素重设样式,这里再改才不会被盖掉
  for (const [chart, which] of [[chartMain, 'main'], [chartSub, 'sub']] as const) {
    chart.getZr().on('mousemove', (e: any) => {
      const c = annGestures.cursorAt(which, e.offsetX, e.offsetY)
      if (c) chart.getZr().setCursorStyle(c)
    })
  }

  // click 分流:主/副 chart 各一套,handleChartClick 按 seriesName 天然分流;
  // shift+click 先被 handleMaybeShiftClick 拦截(入口 D),消费后不再回退到候选四分支。
  // compare 下点中 app 的东西时取消标注框的选中、点反馈记号时选中那条反馈(点只选中,不开反馈面板):见 handleAppClick
  const onAppClick = (p: any) => {
    handleAppClick(p, effectiveAnalysis.value?.hits ?? [], view, {
      comparing: comparing.value, compareReady: compareReady.value,
      selectBox: (id) => ann.selectBox(id), feedback: fb,
    })
  }
  chartMain.on('click', (p: any) => {
    if (handleMaybeShiftClick(p, 'main')) return
    onAppClick(p)
  })
  chartSub.on('click', (p: any) => {
    if (handleMaybeShiftClick(p, 'sub')) return
    onAppClick(p)
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
  // 反馈作答面板开着时副图同样不弹(判据与套用见 subTipOff / applyTipOff)。
  watch(mainTipOff, (off) => applyTipOff(chartMain, off))
  watch(subTipOff, (off) => applyTipOff(chartSub, off))
  const suppressTip = (chart: any, off: () => boolean) => {
    chart.on('showTip', () => {
      if (off()) chart.dispatchAction({ type: 'hideTip' })
    })
  }
  suppressTip(chartMain, () => mainTipOff.value)
  suppressTip(chartSub, () => subTipOff.value)
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
  // 点空白同时取消选中的反馈(粗边与竖带消失);竖带本身不接事件,点在带里的空白也算空白
  chartMain.getZr().on('click', (e: any) => {
    if (!e.target) { fb.select(null); copyRef.selectNode(null); handleChartClick(null, effectiveAnalysis.value?.hits ?? [], view) }
  })
  chartSub.getZr().on('click', (e: any) => {
    if (!e.target) { fb.select(null); copyRef.selectNode(null); handleChartClick(null, effectiveAnalysis.value?.hits ?? [], view) }
  })

  // ResizeObserver 观测两 chart 容器
  roMain = new ResizeObserver(() => { chartMain?.resize(); relayoutMainGrid(); updateMainCanvasOffset() })
  roMain.observe(mainEl.value!)
  roSub = new ResizeObserver(() => { chartSub?.resize(); updateMainCanvasOffset(); renderAnnotateLayers() })
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
  // 副图上下滚动收起反馈面板,不存
  if (subOuter) subOuter.addEventListener('scroll', onSubScroll, { passive: true })
  if (main) main.addEventListener('wheel', mainWheelCapture, { capture: true, passive: false })

  // dev-only e2e hook
  if ((import.meta as any).env?.DEV) {
    ;(window as any).__e2e = { view, ann: () => ann, fb: () => fb, copyRef: () => copyRef, chartMain: () => chartMain, chartSub: () => chartSub }
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
    const { volSeries, yAxisOverride, volAxisMax } = buildVolumeSeriesAndYAxis(bars.value, visStart, visEnd)
    chartMain.setOption({
      series: [{ name: 'volume', data: volSeries.data }],
      yAxis: [{ min: yAxisOverride.min, max: yAxisOverride.max }, { max: volAxisMax }],
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
  // 选中的反馈的竖带(连同面板的默认落点)跟着主图走:每画完一帧重算(平移、缩放、重画、改尺寸都会画)
  chartMain.on('rendered', () => { syncSelectedBand(); syncPanelAnchor() })
  // 用户自己平移、缩放时收起反馈面板,不存;按键走动带出的平移不算(见 panToCurrentDay)
  chartMain.on('datazoom', () => { if (!walkPanning) fb.close() })
  chartSub.on('datazoom', () => { if (!walkPanning) fb.close() })

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

  annGestures.attach()
  void reloadBars().then(() => render(true))
})

onBeforeUnmount(() => {
  annGestures.detach()
  window.removeEventListener('keydown', onKeyDown)
  document.removeEventListener('click', handleDocumentClick)
  subOuterEl.value?.removeEventListener('wheel', subWheelCapture, { capture: true })
  subOuterEl.value?.removeEventListener('scroll', onSubScroll)
  if (fbHintTimer) clearTimeout(fbHintTimer)
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
// 换图、换模式:重读 K 线,图窗回到打开时的样子。只是在画全部 K 线的几档之间切(annotate / compare / 现算的 app):
// K 线不变,不重读,图窗不动
watch([symbol, viewWindow], () => void reloadBars().then(() => render(true)))
watch([mode, wholeChart], ([, whole], [, wasWhole]) => {
  if (whole && wasWhole && bars.value.length) { render(false); return }
  void reloadBars().then(() => render(true))
})
watch([scanFile, effectiveScan], () => {
  if (wholeChart.value) return      // 画全部 K 线的几档与扫描无关
  void reloadBars().then(() => render(false))
})
watch([effectiveAnalysis, nodeVisible, level, nodeColors, focusedInstanceRef, diag, showSlider,
       selectedHitId, candidateHitIds, highlightedEventIds, pendingDisambigInstanceId,
       shiftSelectedEventIds, bandZoomFactor, focusedInstanceId, selectedInstanceId,
       compositionGroupIds, currentDay, activeFamilyKey, () => copyRef.selectedNode, () => view.selPath],
      () => render(false), { deep: true })

// annotate:框、词表、选中、拖动中的样子变了 → 只重画标注的两层;compare 下轨序、✓ / ✗ 变了也一样
watch(() => [ann.view, ann.selectedBoxId, ann.selectedSampleId, ann.currentSampleId, ann.currentPattern,
             draft.value, preview.value, cmpLayout.value, cmp.sampleReads, cmp.boxReads], () => renderAnnotateLayers())
// compare:反馈带(反馈的增删改、后端给的状态、选中的那条)变了 → 只重画标注层(含主视图那张副图)
// (按画出来的样子比:别的标注改动已由上面那条 watch 重画;悬停文字悬停时现算,不必为理由、node 改动重画)
watch(() => cmpFeedbackMarks.value.map(m => [m.id, m.start, m.end, m.lane, m.nodes.join(','), m.tone, m.selected].join(':')).join('|'),
      () => renderAnnotateLayers())
// compare:选中的反馈换了(或它的范围、图的左右偏移变了)、面板开了 / 关了 → 竖带与面板落点重算(主图没重画时也要跟上)
watch([selectedSpan, mainCanvasOffsetX, () => fb.opens, () => !!fb.panel], () => { syncSelectedBand(); syncPanelAnchor() })
// compare:作答面板的 node 按钮悬停 → 对应 band 加亮 / 取消
watch(hoverBand, () => renderAnnotateLayers())
// app 模式:band 表头的特征名(mapping、词表)变了
watch(bandExtras, () => { if (!annotating.value) render(false) })

// compare:选中样本 → 当前日落在样本日、选中配对的那个;选中框 → 落在框终点(stores/compare.ts)
watch(() => ann.selectedSampleId, (id) => { if (id && compareReady.value) cmp.focusSample(id) })
watch(() => ann.selectedBoxId, (id) => { if (id && compareReady.value) cmp.focusBox(id) })
// 进 compare、换股票后 app 跑完:侧栏点行 / 落在 compare 的链接有待落的那天就落那天(stores/landing.ts,
// 消费掉);否则有选中的样本 / 框就聚焦它,再否则默认聚焦离图窗中心最近的样本
// (只设当前日与 app 的选中,不动标注的选中,侧栏不翻页)
watch(() => [compareReady.value, effectiveAnalysis.value, view.barDates] as const, async ([ready]) => {
  if (!ready) return
  await nextTick()
  if (landing.claim()) return
  const sel = ann.selectedSampleId
  if (sel && cmp.focusSample(sel)) return
  if (ann.selectedBoxId && cmp.focusBox(ann.selectedBoxId)) return
  const z = readZoomOverride() ?? { start: 0, end: 100 }
  const center = ((z.start + z.end) / 200) * bars.value.length
  const id = defaultFocus(cmp.sampleDays, null, center)
  if (id) cmp.focusSample(id)
})
watch(shownPeaks, () => renderRefLayers())
// 换图:拖到一半的手势作废,选中的框或样本(在原来那张图上)清掉,当前样本也清掉(冻结)
watch(symbol, () => { annGestures.cancel(); ann.clearSelection() })

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
.resize-stop {
  position: fixed; z-index: 70; pointer-events: none; padding: 1px 6px;
  font-family: var(--mono); font-size: 12px; color: var(--ink);
  background: #fff; border: 1px solid var(--ink); border-radius: 3px;
}
.feedback-range-band {
  position: absolute; top: 0; bottom: 0; z-index: 6; pointer-events: none;
  background: rgba(0, 0, 0, 0.16); border-left: 1.5px dashed #555; border-right: 1.5px dashed #555;
}
/* 选中的反馈:底很淡(不压 K 线),靠两侧深色实线边认;边线画在范围外侧(一根 K 线宽的范围也看得见里面) */
.feedback-selected-band {
  position: absolute; top: 0; bottom: 0; z-index: 5; pointer-events: none; box-sizing: content-box;
  margin-left: -2px; background: rgba(0, 0, 0, 0.06); border-left: 2px solid #111; border-right: 2px solid #111;
}
.feedback-selected-band.cut-left { border-left-color: transparent; }
.feedback-selected-band.cut-right { border-right-color: transparent; }
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
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 2px 4px;
  background: #ffffff;
  border: 1px solid #cbd5e1;
  border-radius: 4px;
  margin-right: 8px;
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
