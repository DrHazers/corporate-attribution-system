<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps({
  topItem: {
    type: Object,
    default: () => ({ label: '回到顶部', targetId: 'module-top' }),
  },
  groups: {
    type: Array,
    default: () => [],
  },
  items: {
    type: Array,
    default: () => [],
  },
  hidden: {
    type: Boolean,
    default: false,
  },
})

const open = ref(false)
const rootRef = ref(null)

const navGroups = computed(() => {
  if (props.groups.length) {
    return props.groups
  }
  return [
    {
      title: '模块目录',
      items: props.items,
    },
  ]
})

function closeMenu() {
  open.value = false
}

function toggleMenu() {
  open.value = !open.value
}

function scrollToTop() {
  window.scrollTo({ top: 0, behavior: 'smooth' })
  closeMenu()
}

function scrollToItem(item) {
  const target = document.getElementById(item?.targetId)
  if (target) {
    target.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
  closeMenu()
}

function handleDocumentPointerDown(event) {
  if (!open.value) {
    return
  }
  if (rootRef.value?.contains(event.target)) {
    return
  }
  closeMenu()
}

function handleDocumentKeydown(event) {
  if (event.key === 'Escape') {
    closeMenu()
  }
}

watch(
  () => props.hidden,
  (hidden) => {
    if (hidden) {
      closeMenu()
    }
  },
)

onMounted(() => {
  document.addEventListener('pointerdown', handleDocumentPointerDown)
  document.addEventListener('keydown', handleDocumentKeydown)
})

onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', handleDocumentPointerDown)
  document.removeEventListener('keydown', handleDocumentKeydown)
})
</script>

<template>
  <div
    v-if="!props.hidden"
    ref="rootRef"
    class="floating-module-nav"
    :class="{ 'floating-module-nav--open': open }"
  >
    <nav
      v-show="open"
      class="floating-module-nav__menu"
      aria-label="页面模块快速导航"
    >
      <button type="button" class="floating-module-nav__top-action" @click="scrollToTop">
        <span class="floating-module-nav__top-icon">↑</span>
        <span>{{ props.topItem.label }}</span>
      </button>

      <div class="floating-module-nav__divider" />

      <section
        v-for="group in navGroups"
        :key="group.title"
        class="floating-module-nav__group"
      >
        <div class="floating-module-nav__group-title">{{ group.title }}</div>
        <button
          v-for="item in group.items"
          :key="item.targetId"
          type="button"
          class="floating-module-nav__item"
          @click="scrollToItem(item)"
        >
          <span class="floating-module-nav__item-dot" aria-hidden="true" />
          <span>{{ item.label }}</span>
        </button>
      </section>
    </nav>

    <button
      type="button"
      class="floating-module-nav__button"
      :aria-expanded="open"
      aria-label="打开页面模块快速导航"
      @click="toggleMenu"
    >
      ☰
    </button>
  </div>
</template>

<style scoped>
.floating-module-nav {
  position: fixed;
  right: 24px;
  bottom: 24px;
  z-index: 900;
  display: inline-flex;
  align-items: flex-end;
  justify-content: flex-end;
  width: auto;
  max-width: 240px;
  pointer-events: none;
}

.floating-module-nav__button,
.floating-module-nav__menu {
  pointer-events: auto;
}

.floating-module-nav__button {
  width: 44px;
  height: 44px;
  border: 1px solid rgba(31, 59, 87, 0.14);
  border-radius: 50%;
  color: var(--brand-ink);
  background: rgba(255, 255, 255, 0.96);
  box-shadow: 0 10px 24px rgba(31, 59, 87, 0.14);
  font-size: 18px;
  font-weight: 700;
  line-height: 1;
  cursor: pointer;
  transition:
    border-color 0.16s ease,
    box-shadow 0.16s ease,
    transform 0.16s ease;
}

.floating-module-nav__button:hover,
.floating-module-nav__button:focus-visible {
  border-color: rgba(31, 59, 87, 0.28);
  box-shadow: 0 14px 28px rgba(31, 59, 87, 0.18);
  transform: translateY(-1px);
}

.floating-module-nav__menu {
  position: absolute;
  right: 0;
  bottom: 54px;
  width: 220px;
  max-height: 60vh;
  padding: 10px;
  overflow-y: auto;
  overflow-x: hidden;
  border: 1px solid rgba(31, 59, 87, 0.12);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.98);
  box-shadow: 0 16px 36px rgba(17, 37, 58, 0.16);
}

.floating-module-nav__top-action {
  display: flex;
  width: 100%;
  min-height: 38px;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border: 1px solid rgba(31, 59, 87, 0.1);
  border-radius: 8px;
  color: var(--brand-ink);
  background: rgba(248, 251, 254, 0.92);
  font-size: 13px;
  font-weight: 700;
  line-height: 1.35;
  text-align: left;
  cursor: pointer;
}

.floating-module-nav__top-action:hover,
.floating-module-nav__top-action:focus-visible {
  background: rgba(31, 59, 87, 0.07);
  border-color: rgba(31, 59, 87, 0.18);
}

.floating-module-nav__top-icon {
  display: inline-flex;
  width: 18px;
  height: 18px;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  color: #ffffff;
  background: var(--brand-ink);
  font-size: 12px;
  line-height: 1;
}

.floating-module-nav__divider {
  height: 1px;
  margin: 9px 0 10px;
  background: rgba(31, 59, 87, 0.1);
}

.floating-module-nav__group + .floating-module-nav__group {
  margin-top: 10px;
}

.floating-module-nav__group-title {
  padding: 0 8px 4px;
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 650;
  line-height: 1.4;
}

.floating-module-nav__item {
  display: flex;
  width: 100%;
  min-height: 34px;
  align-items: center;
  gap: 8px;
  padding: 7px 10px 7px 12px;
  border: 0;
  border-radius: 7px;
  color: #314255;
  background: transparent;
  font-size: 13px;
  font-weight: 600;
  line-height: 1.35;
  text-align: left;
  cursor: pointer;
}

.floating-module-nav__item-dot {
  width: 5px;
  height: 5px;
  flex: 0 0 auto;
  border-radius: 50%;
  background: rgba(49, 66, 85, 0.32);
}

.floating-module-nav__item:hover,
.floating-module-nav__item:focus-visible {
  color: var(--brand-ink);
  background: rgba(31, 59, 87, 0.07);
}

.floating-module-nav__item:hover .floating-module-nav__item-dot,
.floating-module-nav__item:focus-visible .floating-module-nav__item-dot {
  background: rgba(31, 59, 87, 0.58);
}

@media (max-width: 640px) {
  .floating-module-nav {
    right: 16px;
    bottom: 16px;
  }

  .floating-module-nav__menu {
    width: 210px;
  }
}
</style>
