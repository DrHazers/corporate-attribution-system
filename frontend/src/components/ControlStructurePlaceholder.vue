<script setup>
defineProps({
  title: {
    type: String,
    default: '控制结构示意图',
  },
})
</script>

<template>
  <section class="control-structure-placeholder" aria-label="control structure diagram placeholder">
    <header class="control-structure-placeholder__header">
      <div>
        <h3>{{ title }}</h3>
        <p>展示企业控制结构与关键控制路径。</p>
      </div>
    </header>

    <div class="control-structure-placeholder__stage">
      <div class="control-structure-placeholder__mark">控制结构图</div>
      <p>当前暂无可展示的控制结构数据。</p>
    </div>
  </section>
</template>

<style scoped>
.control-structure-placeholder {
  margin-top: 18px;
  padding: 14px;
  border: 1px solid rgba(31, 59, 87, 0.1);
  border-radius: 8px;
  background: #f7fafc;
}

.control-structure-placeholder__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
}

.control-structure-placeholder__header h3 {
  margin: 0;
  color: var(--brand-ink);
  font-family: "Noto Serif SC", "Source Han Serif SC", "STSong", Georgia, serif;
}

.control-structure-placeholder__header p {
  margin: 8px 0 0;
  color: var(--text-secondary);
  font-size: 13px;
}

.control-structure-placeholder__stage {
  display: grid;
  place-items: center;
  min-height: 520px;
  margin-top: 14px;
  border: 1px dashed rgba(31, 59, 87, 0.16);
  border-radius: 8px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.92), rgba(247, 250, 252, 0.96));
  text-align: center;
}

.control-structure-placeholder__stage p {
  margin: 10px 0 0;
  color: var(--text-secondary);
  font-size: 13px;
}

.control-structure-placeholder__mark {
  padding: 10px 16px;
  border-radius: 8px;
  border: 1px solid rgba(31, 59, 87, 0.14);
  background: rgba(255, 255, 255, 0.9);
  color: #172033;
  font-size: 18px;
  font-weight: 700;
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.06);
}

@media (max-width: 760px) {
  .control-structure-placeholder__header {
    display: grid;
  }

  .control-structure-placeholder__stage {
    min-height: 420px;
  }
}
</style>
