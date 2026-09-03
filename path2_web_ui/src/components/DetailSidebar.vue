<template>
  <div ref="sidebarEl" class="sidebar">
    <div class="panel-name">DetailSidebar</div>

    <!-- 入口 A(brush 时段查询)/ 入口 D(shift+click pair 查询):query 结果卡片,叠在其余
         内容之上、互斥展示(activeDetailCard 单值)。caveats 顶部条挂在各自 response 上。 -->
    <div v-if="activeDetailCard === 'time' && timeScopeResponse" class="detail-query-card">
      <button type="button" class="close-query-btn" title="关闭" @click="closeDetailCard">×</button>
      <div v-if="timeScopeResponse.caveats.length" class="caveats-top">
        <div v-for="c in timeScopeResponse.caveats" :key="c.code" class="caveat">⚠ {{ c.message }}</div>
      </div>
      <FailedAttemptsCard
        :payload="timeScopeResponse.payload"
        :node="view.currentDiagnoseNode"
        @update:node="onDiagnoseNodeChange"
      />
    </div>
    <div v-else-if="activeDetailCard === 'pair' && pairScopeResponse" class="detail-query-card">
      <button type="button" class="close-query-btn" title="关闭" @click="closeDetailCard">×</button>
      <div v-if="pairScopeResponse.caveats.length" class="caveats-top">
        <div v-for="c in pairScopeResponse.caveats" :key="c.code" class="caveat">⚠ {{ c.message }}</div>
      </div>
      <PairDetailCard
        v-if="pairPayloadValid"
        :payload="(pairScopeResponse.payload as PairPayload)"
        @undo-swap="undoSwap"
      />
      <div v-else class="hint">scope=pair 端点未接线(见上方 caveat)</div>
    </div>

    <!-- v2 event-debug(2026-07-15) · marker 右键触发的 debug pending 卡片
         detail-debug-card 只作 hook class(不带样式) · 视觉全靠 detail-query-card 继承 -->
    <div v-else-if="activeDetailCard === 'debug' && debugTarget" class="detail-query-card detail-debug-card">
      <button type="button" class="close-query-btn" title="关闭" @click="closeDetailCard">×</button>
      <div class="debug-header">
        Debugging <b>{{ debugTarget.node_id }}</b>
        <b>{{ debugTarget.anchor }}</b>
        at bar <b>{{ debugTarget.bar }}</b>
      </div>
      <div v-if="debugPending" class="debug-spinner">
        <span class="spinner-dot"></span>
        等待 IDE 断点命中,请在 PyCharm 按 F9 继续,或点取消放弃本次 debug
      </div>
      <div v-else-if="debugError" class="debug-error">断点释放失败({{ debugError }})· 请检查后端 / 网络</div>
      <div v-else class="debug-done">断点已释放,可再次触发或关闭卡片</div>
      <button type="button" class="debug-cancel-btn"
              title="取消 = 放弃本次 fetch; IDE 断点需自行 F9/F8 unblock; 新 debug 请求会 abort 本次"
              @click="onCancelDebug">
        取消
      </button>
    </div>

    <!-- 硬伤级修补:被 A2 post-filter 淘汰的残缺 match(数据未到时恒不渲染,见 droppedMatches 注释) -->
    <div v-if="droppedMatches.length" class="dropped-matches-notice">
      ⚠ 这些 marker 属于被消费的 node · 当前 pattern 未触发({{ droppedMatches.length }} 个残缺 match)
    </div>

    <!-- 漏斗总览:analysis 就绪时常驻 -->
    <template v-if="effectivePattern && effectiveAnalysis">
      <h3 class="section-title">node 漏斗</h3>
      <div v-for="node in effectivePattern.topology.nodes" :key="node.node_id">
        <div class="funnel-row"
             :class="{ 'funnel-row--selected': expandedNodeIds.has(node.node_id) && !isolated.has(node.node_id) }"
             @click="!isolated.has(node.node_id) && toggleExpand(node.node_id)">
          <!-- stream-source(孤立 node):密度徽标行 -->
          <template v-if="isolated.has(node.node_id)">
            <span class="node-label stream-source">{{ node.node_id }}</span>
            <span class="badge">原始检测 {{ detectedCount(node) }}</span>
          </template>
          <!-- pattern node(有边):完整漏斗行 -->
          <template v-else>
            <span class="node-label">{{ node.node_id }}</span>
            <span class="funnel-segment" :style="{ color: tierColor('detected', node.node_id) }">
              {{ detectedCount(node) }}
            </span>
            <span class="funnel-arrow">▸</span>
            <span class="funnel-segment" :style="{ color: tierColor('qualified', node.node_id) }">
              {{ tracedCount(node) }}
            </span>
            <span class="funnel-arrow">▸</span>
            <span class="funnel-segment" :style="{ color: tierColor('matched', node.node_id) }">
              {{ matchedCountForNode(node) }}
            </span>
            <span class="expand-icon">{{ expandedNodeIds.has(node.node_id) ? '▲' : '▼' }}</span>
          </template>
        </div>
        <!-- 就地展开:候选表跟在当前展开的 funnel-row 下方(spec §3.4a) -->
        <div v-if="expandedNodeIds.has(node.node_id) && !isolated.has(node.node_id) && diag"
             class="candidate-table-wrap">
          <table class="candidate-table" v-if="nodeAttr(node.node_id).length">
            <thead>
              <tr>
                <th>事件</th>
                <th v-for="cid in nodeClauseIds(node.node_id)" :key="cid">{{ cid }}</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="row in nodeAttr(node.node_id)"
                :key="row.instance_id"
                class="attr-row"
                :class="{ 'attr-row--selected': markedEventIds.has(row.instance_id) }"
                @click="selectCandidateRow(row.instance_id)"
              >
                <td class="cell-id" :style="{ borderLeft: `${leftWidth(row)}px solid ${leftColor(row, node.node_id)}`, paddingLeft: `${15 - leftWidth(row)}px` }">seg@{{ row.start_idx }}-{{ row.end_idx }}</td>
                <td v-for="cid in nodeClauseIds(node.node_id)" :key="cid" class="cell-clause">
                  <template v-if="row.clauses[cid]">
                    <!-- 组合子 clause:单元格聚合 n/m(kind),完整逐分支明细挂 native title;
                         全量树形展示在 K线 hover tooltip(主诊断面),此处保持表格紧凑 -->
                    <span
                      v-if="(row.clauses[cid].children?.length ?? 0) > 0"
                      :title="combinatorDetail(row.clauses[cid])"
                    >{{ combinatorSummary(row.clauses[cid]) }} {{ row.clauses[cid].satisfied ? '✓' : '✗' }}</span>
                    <template v-else>
                      {{ fmtValue(row.clauses[cid].measured) }}
                      <em v-if="row.clauses[cid].op"> ({{ row.clauses[cid].op }}{{ row.clauses[cid].threshold }})</em>
                      {{ row.clauses[cid].satisfied ? '✓' : '✗' }}
                    </template>
                  </template>
                  <template v-else>—</template>
                </td>
              </tr>
            </tbody>
          </table>
          <div v-else class="hint">无候选数据</div>
        </div>
      </div>
    </template>

    <!-- 命中匹配列表:analysis 就绪时常驻;点行 → 选中 match 展开 trace + 图上高亮 -->
    <template v-if="effectivePattern && effectiveAnalysis && effectiveAnalysis.matches.length">
      <h3 class="section-title">命中匹配</h3>
      <div
        v-for="(m, mi) in effectiveAnalysis.matches" :key="m.match_id"
        class="match-row"
        :class="{ 'match-row--selected': markedMatchIds.has(m.match_id) }"
        @click="selectMatchRow(m.match_id)"
      >
        <span class="match-span">{{ '①②③④⑤⑥⑦⑧⑨'[mi] ?? (mi + 1) }} {{ m.start_idx }}–{{ m.end_idx }}</span>
        <span v-if="m.forward_return !== undefined" class="match-ret"
              :class="m.forward_return !== null && m.forward_return >= 0 ? 'ret-pos' : 'ret-neg'">
          ret_{{ (effectiveScan ?? scanFile?.scan)?.label_horizon }}: {{ formatForwardReturn(m.forward_return) }}
          <span v-if="view.isExploring" class="ret-live"
                title="探索态现算值(Working Copy 口径),与左侧列表的 scan 冻结 ret 口径不同">†</span>
        </span>
        <span v-if="m.forward_drawdown !== undefined" class="match-dd"
              :class="m.forward_drawdown !== null && m.forward_drawdown < 0 ? 'dd-neg' : 'dd-pos'">
          d_{{ (effectiveScan ?? scanFile?.scan)?.label_horizon }}: {{ formatForwardReturn(m.forward_drawdown) }}
          <span v-if="view.isExploring" class="ret-live"
                title="探索态现算值(Working Copy 口径),与左侧列表的 scan 冻结 d 口径不同">†</span>
        </span>
      </div>
    </template>

    <!-- per-match trace:选中 match 时叠加显示 -->
    <div v-if="showTrace && selectedMatch" ref="traceEl" class="match-trace">
      <h3 class="section-title">匹配 trace</h3>
      <div v-if="selectedMatch.forward_return !== undefined" class="ret-row">
        ret_{{ (effectiveScan ?? scanFile?.scan)?.label_horizon }}: <strong>{{ formatForwardReturn(selectedMatch.forward_return) }}</strong>
        <span v-if="view.isExploring" class="ret-live"
              title="探索态现算值(Working Copy 口径),与左侧列表的 scan 冻结 ret 口径不同">†</span>
      </div>
      <div v-if="selectedMatch.forward_drawdown !== undefined" class="ret-row">
        d_{{ (effectiveScan ?? scanFile?.scan)?.label_horizon }}: <strong>{{ formatForwardReturn(selectedMatch.forward_drawdown) }}</strong>
        <span v-if="view.isExploring" class="ret-live"
              title="探索态现算值(Working Copy 口径),与左侧列表的 scan 冻结 d 口径不同">†</span>
      </div>
      <!-- node 行:可点击,高亮当前聚焦实例 focusedInstanceRef -->
      <div
        v-for="(nid, nodeKey) in selectedMatch.node_index" :key="nodeKey"
        class="node-row trace-node-row"
        :class="{ 'trace-node-row--selected': isNodeSelected(nid) }"
        @click="selectNodeEvent(nid)"
      >
        <strong>{{ nodeKey }}</strong>
        <!-- 硬伤 A · node.rel "K/N ✓" 徽标(数据存在才亮,来自 diag.nodes[node].rel) -->
        <RelBadge v-if="nodeRel(nodeKey)" :ok="nodeRel(nodeKey)!.ok" :total="nodeRel(nodeKey)!.total" size="sm" />
        <span class="event-ref">{{ nid }}</span>
        <template v-if="selectedMatch.predicate_trace?.where_results[nodeKey]">
          <span v-for="(w, cid) in selectedMatch.predicate_trace.where_results[nodeKey]" :key="cid" class="clause">
            {{ cid }}={{ fmtValue(w.measured) }}
            <em v-if="w.op">({{ w.op }}{{ w.threshold }})</em>
            {{ w.satisfied ? '✓' : '✗' }}
          </span>
        </template>
      </div>
      <h4>边</h4>
      <div v-for="(w, key) in selectedMatch.predicate_trace?.edge_results" :key="key" class="edge-row">
        {{ key }} {{ fmt(w.measured?.value, w.measured?.kind) }} {{ w.satisfied ? '✓' : '✗' }}
      </div>
    </div>

    <div v-if="!effectivePattern || !effectiveAnalysis" class="hint">hover K 线 event 看属性 · 点匹配带看 trace · 点拓扑节点展开候选表</div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import { storeToRefs } from 'pinia'
import { useViewStore } from '../stores/view'
import { colorOf } from '../render/colors'
import { formatForwardReturn } from '../render/visible'
import RelBadge from '../shared/RelBadge.vue'
// fmt(val, kind) 按 EdgeWitness.measured.kind 加前缀(硬伤 E · Task 13 落地接线);fmtValue 硬伤 D 数组/scalar 递归格式化
import { fmt, fmtValue } from '../shared/formatters'
import FailedAttemptsCard from './FailedAttemptsCard.vue'
import PairDetailCard from './PairDetailCard.vue'
import type { TopoNode, AttrRow, ClauseWitness, PairPayload } from '../types'

const view = useViewStore()
const {
  selectedMatch, effectivePattern, effectiveAnalysis,
  diag, isolated, matchedIds, matchedEventIds, qualifiedIds, nodeColors, focusedInstanceRef, scanFile, effectiveScan,
  activeDetailCard, timeScopeResponse, pairScopeResponse,
  debugPending, debugTarget, debugError,
  showTrace, expandedNodeIds, markedMatchIds, markedEventIds,   // Task 4 新增(集合版)
  focusedMatchId,   // watch 滚动 trace 用
} = storeToRefs(view)

// DOM refs for scroll-to-trace
const sidebarEl = ref<HTMLElement | null>(null)
const traceEl = ref<HTMLElement | null>(null)

// 手动 toggle:点已展开 node → 折叠该行;点未展开 → 加入展开集(不折叠其他)。
function toggleExpand(nodeId: string) {
  view.toggleExpandedNode(nodeId)
}

// trace 展开时滚入视口(旧 watch(selected) 里 kind==='match' 分支迁到这里)
watch([showTrace, focusedMatchId], ([show]) => {
  if (show) {
    nextTick(() => {
      if (traceEl.value && sidebarEl.value && typeof traceEl.value.scrollIntoView === 'function') {
        traceEl.value.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
      }
    })
  }
})

// ─── 计数派生(单一真相源,从 store computed 读) ────────────────────────────────

/** 某 node 所对应 band 的所有 events。band 键 = node_id;段等子事件由引擎
 * children 声明命名表直标子结构 node_id(如 tb_seg),天然独立泳道。 */
function bandEvents(node: TopoNode) {
  const events = effectiveAnalysis.value?.events ?? []
  return events.filter(e => e.node_id === node.node_id)
}

function detectedCount(node: TopoNode): number {
  return bandEvents(node).length
}

function tracedCount(node: TopoNode): number {
  // 实例流:matchedIds 集合元素为复合键,单键 has 恒 miss;改用 eventTier(实例级正确,
  // 与 KlineChart.vue marker 上色同一判定)。traced = qualified ∪ matched = 非 detected。
  return bandEvents(node).filter(e => view.eventTier(e) !== 'detected').length
}

function matchedCountForNode(node: TopoNode): number {
  // 实例流:同上,matched 档判定走 eventTier(实例级)
  return bandEvents(node).filter(e => view.eventTier(e) === 'matched').length
}

// ─── 着色 ─────────────────────────────────────────────────────────────────────

function tierColor(tier: 'detected' | 'qualified' | 'matched', nodeId: string): string {
  return colorOf(tier, nodeId, nodeColors.value)
}

// ─── 候选表 ───────────────────────────────────────────────────────────────────

// 循环体内每 node 独立取候选表数据(避免 expandedNode 单值假设)。
function nodeAttr(nodeId: string): AttrRow[] {
  return diag.value?.nodes[nodeId]?.attr ?? []
}

function nodeClauseIds(nodeId: string): string[] {
  const ids = new Set<string>()
  for (const row of nodeAttr(nodeId))
    for (const cid of Object.keys(row.clauses)) ids.add(cid)
  return [...ids]
}

/** 组合子 witness 单元格摘要:如 "1/2(or)"。 */
function combinatorSummary(w: ClauseWitness): string {
  const kids = w.children ?? []
  if (w.label === 'not') return '(not)'      // n/m 对 not 无意义(0 个子分支通过恰是 not 成立)
  const pass = kids.filter((k) => k.satisfied).length
  return `${pass}/${kids.length}(${w.label ?? '?'})`
}

/** 组合子 witness 悬停明细(native title):逐分支一行,层次用树线 ├ └ │ 显式画出
 * (与 K 线 tooltip 同款记号)。组合子行不出 n/m —— 子分支恒全量展开,数字属冗余。 */
function combinatorDetail(w: ClauseWitness, prefix = ''): string {
  const kids = w.children ?? []
  return kids.map((k, i) => {
    const last = i === kids.length - 1
    const mark = k.satisfied ? '✓' : '✗'
    const head = `${prefix}${last ? '└ ' : '├ '}${k.label ?? '?'}`
    const grand = k.children ?? []
    if (grand.length > 0) {
      return `${head} ${mark}\n` + combinatorDetail(k, prefix + (last ? '  ' : '│ '))
    }
    const opStr = k.op != null ? ` ${k.op} ${k.threshold}` : ''
    return `${head}: ${fmtValue(k.measured)}${opStr} ${mark}`
  }).join('\n')
}

/** 候选表行的 tier:先看 matched 实例集,再看 qualifiedIds,否则 detected。
 *  实例流:AttrRow.instance_id 直接查集(matchedEventIds/qualifiedIds 集合元素即 instance_id)。 */
function rowTier(row: AttrRow): 'matched' | 'qualified' | 'detected' {
  if (matchedEventIds.value.has(row.instance_id)) return 'matched'
  if (qualifiedIds.value.has(row.instance_id)) return 'qualified'
  return 'detected'
}
/** 候选表首列左侧色块色 · 走 colorOf 与副图 marker + 漏斗数字三处共用同一 API
 * leftColor 接受 nodeId 参数(template 从 v-for 传入,取代 expandedNode 单值假设) */
function leftColor(row: AttrRow, nodeId: string): string {
  return colorOf(rowTier(row), nodeId, nodeColors.value)
}
/** 色条宽度按 tier 分档:matched 最宽,便于色盲/低对比场景通过宽度识别层级(色恒非唯一信道)。
 * total = borderWidth + paddingLeft 保持 15px 恒定 → 文字左端在三档间对齐,只有色条本身变宽/变窄。 */
function leftWidth(row: AttrRow): number {
  const t = rowTier(row)
  return t === 'matched' ? 12 : t === 'qualified' ? 6 : 3
}

// ─── 匹配 trace 双向高亮 ─────────────────────────────────────────────────────

/**
 * 硬伤 A · node 的入边关系判定汇总(K/N)。diag.nodes[node].rel 是 RelRow[](按 src class 分行);
 * 汇总 ok_count/total_src 得 RelBadge 的 {ok,total}。空数组(无关系边节点,或诊断未跑)→ null 不渲染。
 */
function nodeRel(nodeKey: string | number): { ok: number; total: number } | null {
  const rel = diag.value?.nodes[String(nodeKey)]?.rel
  if (!rel || rel.length === 0) return null
  return {
    ok: rel.reduce((sum, r) => sum + r.ok_count, 0),
    total: rel.reduce((sum, r) => sum + r.total_src, 0),
  }
}

/** match node_index 值为 instance_id 字符串(node 名 → 实例键),直接参与聚焦判定 */
function isNodeSelected(instanceId: string): boolean {
  return !!instanceId && instanceId === focusedInstanceRef.value
}

/** 点击 trace node 行 → focusEvent(spec §3.3 统一 action,实例级入口) */
function selectNodeEvent(instanceId: string) {
  if (instanceId) view.focusEvent(instanceId)
}

/** 点击候选表行 → focusEvent(等价图上 marker click,spec §3.3) */
function selectCandidateRow(instanceId: string) {
  view.focusEvent(instanceId)
}

/** 点击命中匹配列表行 → focusMatch(等价图上 bracket click,spec §3.3) */
function selectMatchRow(matchId: string): void {
  view.focusMatch(matchId)
}

// ── 首次穿越方向 chip(Task 5) ─────────────────────────────────────────────
// ─── Task 18 · 入口 A(brush 时段查询)+ 入口 D(shift+click pair 查询)query 卡片 ─────────
// KlineChart 触发(brush/shift+click)→ view.triggerTimeQuery/triggerPairQuery → 落地
// timeScopeResponse/pairScopeResponse + activeDetailCard,这里只负责渲染 + 关闭。

/** scope=pair 端点未接线(api.py 尚未 recompute+attach AnalysisResult,Task 17 遗留 systemic gap)
 * 时降级为 {stub:true},非真 PairPayload——'valid' in payload 探测,防裸渲染时读 undefined 字段炸模板。*/
const pairPayloadValid = computed(() =>
  !!pairScopeResponse.value && 'valid' in pairScopeResponse.value.payload)

/** 硬伤级修补:dropped_matches(A2 post-filter 淘汰的残缺 match)已加到 path2/dag/result.py::
 * AnalysisResult,但 serialize.py 尚未序列化进前端 Analysis 契约——any-cast 防御式探测,同
 * 数据未到时恒空数组、不渲染。*/
const droppedMatches = computed<unknown[]>(() => (effectiveAnalysis.value as any)?.dropped_matches ?? [])

function closeDetailCard() {
  view.clearDetailCard()   // clearDetailCard 内部已重置 currentDiagnoseNode
}

// v2 event-debug(2026-07-15) · cancel debug fetch(不 unblock IDE 断点)
function onCancelDebug() {
  view.cancelDebug()
}

/** 入口 A · node 下拉 filter。'' = 全部 · 其余**本地过滤显示**(FailedAttemptsCard
 * 按 node 过滤),不重新请求——后端 node 严格过滤会返回子集,payload 坍缩 →
 * failedNodes 坍缩 → 下拉其他 node 全置灰不可选(2026-08-10 实测)。payload 恒全量。
 * 过滤态提升到 view store(currentDiagnoseNode),供 FailedAttemptsCard 消费。*/
function onDiagnoseNodeChange(v: string) {
  view.currentDiagnoseNode = v
}
/** 卡片切离 'time'(关闭/切走 pair/candidate)→ 复位下拉,防陈旧值。
 * brush 从 'time' → 'time' 无变化、不触发此 watch,是**正确**行为:此时应沿用当前过滤,由 KlineChart 透传。*/
watch(activeDetailCard, (v) => { if (v !== 'time') view.currentDiagnoseNode = '' })
/** PairDetailCard 撤回:无 force-no-swap 查询参数(backend 按 edge 存在性确定性判定方向,
 * 非记忆用户点击史)· "撤回" 语义上只能是撤销本次查询展示,而非重新以原始顺序强制查询。*/
function undoSwap() {
  view.clearDetailCard()
}
</script>

<style scoped>
.sidebar { padding: 10px 12px; font-size: 12px; overflow-y: auto; }
.panel-name { font-weight: 700; font-size: 13px; color: #334155; padding-bottom: 6px; margin-bottom: 8px; border-bottom: 1px solid #e2e8f0; }
.section-title { font-size: 12px; font-weight: 600; color: #475569; margin: 8px 0 4px; }

.funnel-row {
  display: flex; align-items: center; gap: 6px; padding: 4px 6px;
  border-radius: 4px; cursor: default; flex-wrap: wrap;
  border: 1px solid transparent; margin-bottom: 2px;
}
.funnel-row:not(.funnel-row--stream-source) { cursor: pointer; }
.funnel-row:hover:not(.funnel-row--stream-source) { background: #f1f5f9; }
.funnel-row--selected { background: #e0f2fe; border-color: #7dd3fc; }

.node-label { font-weight: 600; min-width: 48px; color: #1e293b; }
.node-label.stream-source { color: #64748b; }
.badge { background: #e2e8f0; border-radius: 4px; padding: 1px 6px; font-size: 11px; color: #475569; }
.funnel-segment { font-weight: 700; font-size: 13px; min-width: 20px; text-align: right; }
.funnel-arrow { color: #94a3b8; font-size: 10px; }
.expand-icon { margin-left: auto; color: #94a3b8; font-size: 10px; }

.candidate-table-wrap { margin: 4px 0 8px; background: #f8fafc; border-radius: 4px; padding: 6px; }
.candidate-table { width: 100%; border-collapse: collapse; font-size: 11px; }
.candidate-table th { text-align: left; padding: 2px 6px; color: #64748b; border-bottom: 1px solid #e2e8f0; }
.attr-row { cursor: pointer; }
.attr-row:hover { background: #f1f5f9; }
.attr-row--selected { background: #fef9c3 !important; }
.attr-row--selected td { border-top: 1px solid #fbbf24; border-bottom: 1px solid #fbbf24; }
.attr-row--selected td:first-child { border-left: 1px solid #fbbf24; }
.attr-row--selected td:last-child { border-right: 1px solid #fbbf24; }
.cell-id { padding: 2px 6px; color: #475569; white-space: nowrap; }
.cell-clause { padding: 2px 6px; }
.cell-clause em { color: #94a3b8; font-style: normal; }

.match-row {
  display: flex; align-items: center; gap: 8px; padding: 4px 6px;
  border-radius: 4px; cursor: pointer; border: 1px solid transparent; margin-bottom: 2px;
}
.match-row:hover { background: #f1f5f9; }
.match-row--selected { background: #fef9c3; border-color: #fbbf24; }
.match-span { font-size: 11px; color: #475569; flex: 1; }
.match-ret { font-weight: 700; font-size: 12px; }
.ret-pos { color: #16a34a; }
.ret-neg { color: #dc2626; }
/* forward_drawdown 显示(ret 的对偶):统一带符号百分比,负值(下行)用红,零/正值用绿;
   颜色纪律遵循全项目色盲友好约定(饱和度而非色相区分,见 .match-ret)。 */
.match-dd { font-weight: 700; font-size: 12px; }
.dd-neg { color: #dc2626; }
.dd-pos { color: #16a34a; }
/* Task 13 · 探索态现算 ret 上标(与 scan 冻结口径区分) */
.ret-live { color: #d97706; font-weight: 700; margin-left: 1px; }

.ret-row { margin: 4px 0; color: #334155; }
.match-trace { margin-top: 10px; border-top: 1px solid #e2e8f0; padding-top: 8px; }
.node-row, .edge-row { margin: 4px 0; display: flex; gap: 8px; flex-wrap: wrap; }
.trace-node-row { cursor: pointer; padding: 3px 6px; border-radius: 4px; border: 1px solid transparent; }
.trace-node-row:hover { background: #f1f5f9; }
.trace-node-row--selected { background: #fef9c3 !important; border-color: #fbbf24; }
.event-ref { color: #64748b; font-size: 11px; margin-left: 4px; }
.clause em { color: #64748b; font-style: normal; }
.hint { color: #94a3b8; margin-top: 8px; }

.detail-query-card {
  position: relative; margin-bottom: 10px; padding: 8px 10px 4px;
  border: 1px solid #7dd3fc; border-radius: 6px; background: #f0f9ff;
}
.close-query-btn {
  position: absolute; top: 2px; right: 4px; border: none; background: transparent;
  cursor: pointer; font-size: 14px; line-height: 1; color: #64748b; padding: 2px 4px;
}
.caveats-top { margin: 2px 20px 6px 0; }
.caveat { font-size: 11px; color: #92400e; background: #fefcbf; border-radius: 4px; padding: 3px 6px; margin-bottom: 2px; }
.dropped-matches-notice {
  font-size: 11px; color: #92400e; background: #fefcbf; border-radius: 4px;
  padding: 4px 6px; margin-bottom: 8px;
}

/* v2 event-debug(2026-07-15) */
.debug-header {
  font-size: 13px;
  padding: 8px 12px 4px;
  color: #333;
}
.debug-spinner {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  font-size: 12px;
  color: #666;
  line-height: 1.5;
}
.spinner-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  background: #4a90e2;
  border-radius: 50%;
  animation: pulse 1.2s ease-in-out infinite;
  flex-shrink: 0;
}
@keyframes pulse {
  0%, 100% { opacity: 0.3; transform: scale(0.8); }
  50% { opacity: 1; transform: scale(1.2); }
}
.debug-done {
  padding: 10px 12px;
  font-size: 12px;
  color: #4a7;
}
.debug-error {
  padding: 10px 12px;
  font-size: 12px;
  color: #c0392b;
}
.debug-cancel-btn {
  margin: 4px 12px 12px;
  padding: 6px 12px;
  background: #e74c3c;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
}
.debug-cancel-btn:hover {
  background: #c0392b;
}
</style>
