<script setup lang="ts">
// 硬伤 C 前端 · refs_other_node / cross_node_pending 呈现
const props = defineProps<{
    reason: 'refs_other_node' | 'cross_node_pending'
}>()

const titleMap = {
    refs_other_node: '跨节点 clause · 编译期标注 · 当前诊断层未复核',
    cross_node_pending: '跨节点 clause · 运行期 tripwire 兜底 · 数据延后',
}
</script>

<template>
    <span class="pending-icon" :title="titleMap[props.reason]">⚠</span>
</template>

<style scoped>
.pending-icon { display: inline-block; color: #dd6b20; cursor: help; }
</style>
