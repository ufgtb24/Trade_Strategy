<template>
  <div class="backdrop">
    <div class="card" tabindex="-1">
      <p class="prompt">当前已经命中 {{ hits }}，是否保存？</p>
      <footer>
        <button data-testid="btn-save"     @click="$emit('save')">保存</button>
        <button data-testid="btn-discard"  @click="$emit('discard')">丢弃</button>
        <button data-testid="btn-continue" @click="$emit('continue')">继续扫描</button>
      </footer>
    </div>
  </div>
</template>

<script setup lang="ts">
// 三按钮中途停止对话框:hits 由父组件绑定 reactive progress.hits,扫描期间会跟着涨。
// Esc / 点 backdrop 外侧不响应——用户必须显式选保存/丢弃/继续才能离开。
defineProps<{ hits: number }>()
defineEmits<{ (e: 'save'): void; (e: 'discard'): void; (e: 'continue'): void }>()
</script>

<style scoped>
.backdrop {
  position: fixed; inset: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex; align-items: center; justify-content: center;
  z-index: 1100;                       /* 高于 ScanResultDialog 的 1000 */
}
.card {
  background: #fff;
  border-radius: 8px;
  padding: 20px 24px;
  min-width: 320px;
  max-width: 480px;
  outline: none;
}
.prompt { margin: 0 0 16px; font-size: 14px; }
footer { display: flex; gap: 10px; justify-content: flex-end; }
button { padding: 6px 14px; font-size: 13px; cursor: pointer; }
button[data-testid="btn-save"]    { background: #2563eb; color: #fff; border: none; border-radius: 4px; }
button[data-testid="btn-discard"] { background: #ef4444; color: #fff; border: none; border-radius: 4px; }
button[data-testid="btn-continue"]{ background: #fff;    color: #1f2937; border: 1px solid #cbd5e1; border-radius: 4px; }
</style>
