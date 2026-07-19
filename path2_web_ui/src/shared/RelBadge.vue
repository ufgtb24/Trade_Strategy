<script setup lang="ts">
// 硬伤 A · node.rel 前端渲染 · "入边 K/N ✓" 徽标
defineProps<{
    ok: number
    total: number
    size?: 'sm' | 'md'
}>()

function badgeClass(ok: number, total: number): string {
    if (total === 0) return 'badge-neutral'
    if (ok === total) return 'badge-ok'
    if (ok === 0) return 'badge-fail'
    return 'badge-warn'
}
</script>

<template>
    <span :class="['rel-badge', badgeClass(ok, total), `size-${size ?? 'md'}`]">
        <span class="count">{{ ok }}/{{ total }}</span>
        <span v-if="ok === total && total > 0" class="check">✓</span>
    </span>
</template>

<style scoped>
.rel-badge { display: inline-flex; align-items: center; gap: 2px; padding: 0 6px; border-radius: 4px; font-size: 12px; }
.size-sm { padding: 0 4px; font-size: 10px; }
.badge-ok { background: #c6f6d5; color: #22543d; }
.badge-warn { background: #fefcbf; color: #744210; }
.badge-fail { background: #fed7d7; color: #742a2a; }
.badge-neutral { background: #e2e8f0; color: #4a5568; }
</style>
