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
        :data-role-node="box.node.node_id"
        class="node" :class="{ off: roleVisible[box.node.node_id] === false }"
        :style="{
          left: box.x + 'px', top: box.y + 'px', width: box.w + 'px',
          background: roleColors[box.node.node_id] ?? '#888',
          borderColor: roleColors[box.node.node_id] ?? '#888',
        }"
        :title="ruleText(box.node)"
        @click="handleNodeClick(box.node.node_id, $event)"
        @dblclick="handleNodeDblClick(box.node.node_id)"
        @mouseenter="emit('hover-role', box.node.node_id)"
        @mouseleave="emit('hover-role', null)"
      >
        <span class="label">{{ box.node.label || box.node.node_id }}</span>
      </button>

      <!-- 边标签:HTML 绝对定位,富排版(kind 小灰上标 + rule 深色),常驻 -->
      <div
        v-for="(e, i) in layout.edges" :key="'l' + i" class="elabel"
        :style="{ left: e.label.x + 'px', top: e.label.y + 'px' }"
      >
        <span class="kind">{{ e.edge.kind.replace('Edge', '') }}</span>
        <span class="rule">{{ e.edge.rule }}</span>
      </div>
    </div>
    <div class="hint">点节点=显隐切换 · 双击=诊断 · 悬停看类级阈值</div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useViewStore } from '../stores/view'
import { layoutTopology, type TopoLayout } from '../render/topology'
import type { TopoNode } from '../types'

const emit = defineEmits<{ (e: 'hover-role', nodeId: string | null): void }>()
const view = useViewStore()
const { effectivePattern, roleColors, roleVisible } = storeToRefs(view)

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
      view.toggleRole(nodeId)
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
  // 确保延迟中的 toggleRole 已取消(detail>=2 path 已取消,但防御性再取消一次)
  if (pendingTimer.value !== null) {
    clearTimeout(pendingTimer.value)
    pendingTimer.value = null
  }
  view.selectRole(nodeId)
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
}
.elabel .kind { display: block; color: #64748b; font-size: 9px; letter-spacing: 0.2px; }
.elabel .rule { color: #0f172a; }
.hint { margin-top: 4px; font-size: 10px; color: #94a3b8; }
</style>
