<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  mode: string
  suite?: string
}>()

// Determine if this is a semantic-rag run based on mode + suite string
const isRag = computed(() => {
  return props.mode === 'semantic' && (props.suite || '').includes('rag')
})

const modeClass = computed(() => {
  if (isRag.value) return 'mode-chip-semantic-rag'
  if (props.mode === 'semantic-local') return 'mode-chip-semantic-local'
  if (props.mode === 'semantic') return 'mode-chip-semantic'
  return 'mode-chip-deterministic'
})

const label = computed(() => {
  if (isRag.value) return 'Semantic + RAG'
  if (props.mode === 'semantic-local') return 'Semantic Local'
  if (props.mode === 'semantic') return 'Semantic'
  return 'Deterministic'
})
</script>

<template>
  <span class="inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium" :class="modeClass">
    <template if="props.mode === 'deterministic'">
      <svg class="mr-1.5 h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <polyline points="4 14 10 14 10 20"></polyline>
        <polyline points="20 10 14 10 14 4"></polyline>
        <line x1="14" y1="10" x2="21" y2="3"></line>
        <line x1="3" y1="21" x2="10" y2="14"></line>
      </svg>
    </template>
    <template v-else-if="props.mode === 'semantic'">
      <svg class="mr-1.5 h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M12 2v20"></path>
        <path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"></path>
      </svg>
    </template>
    <template v-else-if="isRag">
      <svg class="mr-1.5 h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1 0-5H20"></path>
      </svg>
    </template>
    <template v-else>
      <svg class="mr-1.5 h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M12 2v20"></path>
        <path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"></path>
      </svg>
    </template>
    {{ label }}
  </span>
</template>
