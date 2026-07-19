<template>
  <div class="topo" v-if="effectivePattern">
    <div class="topo-graph" :style="{ width: layout.width + 'px', height: layout.height + 'px' }">
      <!-- 边层:只画曲线 + 箭头,不拦鼠标 -->
      <svg class="edges-svg" :viewBox="`0 0 ${layout.width} ${layout.height}`"
           :width="layout.width" :height="layout.height">
        <defs>
          <marker id="topo-arrow" markerWidth="9" markerHeight="9" refX="7" refY="3"
                  orient="auto" markerUnits="userSpaceOnUse">
            <path d="M0,0 L7,3 L0,6 Z" fill="#94a3b8" />
          </marker>
        </defs>
        <path
          v-for="(e, i) in layout.edges" :key="i" class="edge-line" :d="e.d"
          fill="none" stroke="#94a3b8" stroke-width="1.6" marker-end="url(#topo-arrow)"
        />
      </svg>

      <!-- 节点:绝对定位,完整保留现有 button 的全部绑定 -->
      <button
        v-for="box in layout.nodes" :key="box.node.node_id"
        :data-node-id="box.node.node_id"
        class="node" :class="{ off: nodeVisible[box.node.node_id] === false }"
        :style="{
          left: box.x + 'px', top: box.y + 'px', width: box.w + 'px',
          background: nodeColors[box.node.node_id] ?? '#888',
          borderColor: nodeColors[box.node.node_id] ?? '#888',
        }"
        :title="ruleText(box.node)"
        @click="handleNodeClick(box.node.node_id, $event)"
        @dblclick="handleNodeDblClick(box.node.node_id)"
        @mouseenter="emit('hover-node', box.node.node_id)"
        @mouseleave="emit('hover-node', null)"
      >
        <span class="label">{{ box.node.node_id }}</span>
      </button>

      <!-- 边标签:HTML 绝对定位,富排版(kind 小灰上标 + rule 深色),常驻;
           点击 = 入口 B 降级(scope=nodes → PairListCard),cursor 提示可点 -->
      <div
        v-for="(e, i) in layout.edges" :key="'l' + i" class="elabel"
        :style="{ left: e.label.x + 'px', top: e.label.y + 'px' }"
        @click="handleEdgeClick(e.edge.src, e.edge.dst)"
      >
        <span class="kind">{{ e.edge.kind.replace('Edge', '') }}</span>
        <span class="rule">{{ e.edge.rule }}</span>
      </div>
    </div>
    <div class="hint">点节点=显隐切换 · 双击=诊断 · 点边标签=miss_reasons 明细 · 悬停看类级阈值</div>

    <!-- 入口 B 降级:点 edge 弹出的 miss_reasons/example_failed_pairs 卡片 -->
    <div v-if="activeNodesEdge" class="nodes-popover">
      <div class="nodes-popover-hdr">
        <span>{{ activeNodesEdge.src }} → {{ activeNodesEdge.dst }}</span>
        <button class="close-btn" @click="closeNodes">×</button>
      </div>
      <div v-if="nodesLoading" class="hint">加载中…</div>
      <div v-else-if="nodesError" class="hint nodes-error">{{ nodesError }}</div>
      <template v-else-if="nodesResponse">
        <PairListCard :payload="nodesResponse.payload" />
        <div v-if="nodesResponse.caveats.length" class="nodes-caveats">
          <div v-for="c in nodesResponse.caveats" :key="c.code" class="hint">⚠ {{ c.message }}</div>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useViewStore } from '../stores/view'
import { layoutTopology, type TopoLayout } from '../render/topology'
import { windowOf } from '../render/visible'
import { getNodesDiagnose } from '../api'
import PairListCard from './PairListCard.vue'
import type { TopoNode, NodesScopeResponse } from '../types'

const emit = defineEmits<{ (e: 'hover-node', nodeId: string | null): void }>()
const view = useViewStore()
const { effectivePattern, nodeColors, nodeVisible, symbol, activePatternId, effectiveScan } = storeToRefs(view)

const EMPTY: TopoLayout = { nodes: [], edges: [], width: 0, height: 0 }
const layout = computed<TopoLayout>(() =>
  effectivePattern.value ? layoutTopology(effectivePattern.value.topology.nodes, effectivePattern.value.topology.edges) : EMPTY)

function ruleText(n: TopoNode): string {
  const parts = n.where_rules.map((r) => `${r.clause_id} ${r.op} ${r.threshold}`)
  return parts.length ? parts.join(' · ') : '(无类级阈值)'
}

// 单击 vs 双击消歧:
// 原生序列 = click(detail=1) → click(detail=2) → dblclick
// 策略:@click 时 detail===1 延迟 250ms 执行单击动作;detail>=2 取消延迟(dblclick handler 执行双击);
// @dblclick 直接执行双击动作——也让单测可通过 trigger('dblclick') 验证
const pendingTimer = ref<ReturnType<typeof setTimeout> | null>(null)

function handleNodeClick(nodeId: string, event: MouseEvent) {
  if (event.detail === 1) {
    // 可能是单击;延迟等待,若随后 dblclick 则取消
    pendingTimer.value = setTimeout(() => {
      pendingTimer.value = null
      view.toggleNode(nodeId)
    }, 250)
  } else {
    // detail>=2 说明是双击前的第二次 click;取消延迟(dblclick handler 负责执行)
    if (pendingTimer.value !== null) {
      clearTimeout(pendingTimer.value)
      pendingTimer.value = null
    }
  }
}

function handleNodeDblClick(nodeId: string) {
  // 确保延迟中的 toggleNode 已取消(detail>=2 path 已取消,但防御性再取消一次)
  if (pendingTimer.value !== null) {
    clearTimeout(pendingTimer.value)
    pendingTimer.value = null
  }
  view.toggleExpandedNode(nodeId)
}

// ── 入口 B 降级:点 edge 标签 → scope=nodes → PairListCard(自包含,不依赖 DetailSidebar) ──
const activeNodesEdge = ref<{ src: string; dst: string } | null>(null)
const nodesResponse = ref<NodesScopeResponse | null>(null)
const nodesLoading = ref(false)
const nodesError = ref<string | null>(null)

async function handleEdgeClick(src: string, dst: string) {
  activeNodesEdge.value = { src, dst }
  nodesResponse.value = null
  nodesError.value = null
  if (!symbol.value || !activePatternId.value || !effectiveScan.value) {
    nodesError.value = '缺 symbol/pattern/窗口,无法查询'
    return
  }
  const w = windowOf(effectiveScan.value as any)
  nodesLoading.value = true
  try {
    nodesResponse.value = await getNodesDiagnose(
      activePatternId.value, symbol.value, w.start, w.end, src, dst)
  } catch (e: any) {
    nodesError.value = String(e?.message ?? e)
  } finally {
    nodesLoading.value = false
  }
}

function closeNodes() {
  activeNodesEdge.value = null
  nodesResponse.value = null
  nodesError.value = null
}
</script>

<style scoped>
.topo { padding: 8px 12px; border-bottom: 1px solid #e5e7eb; }
.topo-graph { position: relative; }
.edges-svg { position: absolute; inset: 0; pointer-events: none; z-index: 1; }
.node {
  position: absolute; box-sizing: border-box; z-index: 2;
  display: inline-flex; align-items: center; justify-content: center; gap: 4px;
  height: 30px; padding: 0 12px; border-radius: 15px;
  color: #fff; border: 2px solid; cursor: pointer; font-size: 13px; white-space: nowrap;
}
.node.off { opacity: 0.32; }
.elabel {
  position: absolute; z-index: 2; transform: translate(-50%, -50%);
  background: rgba(255, 255, 255, 0.92); padding: 1px 5px; border-radius: 5px;
  font-size: 11px; line-height: 1.35; white-space: nowrap; text-align: center;
  cursor: pointer;
}
.elabel .kind { display: block; color: #64748b; font-size: 9px; letter-spacing: 0.2px; }
.elabel .rule { color: #0f172a; }
.hint { margin-top: 4px; font-size: 10px; color: #94a3b8; }

.nodes-popover {
  margin-top: 6px; border: 1px solid #e2e8f0; border-radius: 6px;
  background: #fff; overflow-x: auto; min-width: 0;
}
.nodes-popover-hdr {
  display: flex; justify-content: space-between; align-items: center;
  padding: 4px 8px; background: #f8fafc; border-bottom: 1px solid #e2e8f0;
  font-size: 12px; font-weight: 600; color: #334155;
}
.close-btn {
  border: none; background: transparent; cursor: pointer; font-size: 14px;
  line-height: 1; color: #64748b; padding: 0 4px;
}
.nodes-caveats { padding: 0 10px 8px; }
.nodes-error { color: #b91c1c; }
</style>
