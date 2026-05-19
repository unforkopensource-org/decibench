<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useRagSynthesize } from '../api'

const router = useRouter()
const synthesizeResult = useRagSynthesize()

const suite = ref(`rag-suite-${Math.floor(Math.random() * 1000)}`)
const rawTopics = ref('Caller wants to book an appointment\nCaller asks if agent is AI\nCaller is in a noisy cafe')
const errorMsg = ref<string | null>(null)
const successMsg = ref<string | null>(null)

async function startSynthesis() {
  errorMsg.value = null
  successMsg.value = null
  const topics = rawTopics.value.split('\n').map(t => t.trim()).filter(Boolean)
  if (topics.length === 0) {
    errorMsg.value = 'Enter at least one topic.'
    return
  }
  
  try {
    const res = await synthesizeResult.mutateAsync({ suite: suite.value, topics })
    successMsg.value = `Synthesized ${res.accepted?.length || 0} scenarios into suite '${suite.value}'.`
    if (res.rejected && res.rejected.length > 0) {
      errorMsg.value = `${res.rejected.length} scenarios rejected. Check terminal logs for details.`
    }
  } catch (err: any) {
    errorMsg.value = String(err)
  }
}
</script>

<template>
  <div class="space-y-6">
    <header>
      <h1 class="text-2xl font-bold text-ink-900">Synthesize Scenarios</h1>
      <p class="mt-1 text-sm text-ink-500">
        Generate custom scenarios from your RAG corpus by describing what you want to test.
      </p>
    </header>

    <section class="card p-6 max-w-2xl">
      <div class="space-y-5">
        <div>
          <label class="block text-sm font-medium text-ink-700">Suite Name</label>
          <input
            v-model="suite"
            class="mt-1 w-full rounded-md border border-ink-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none"
            placeholder="custom-rag-suite"
          />
        </div>

        <div>
          <label class="block text-sm font-medium text-ink-700">Topics (one per line)</label>
          <textarea
            v-model="rawTopics"
            rows="6"
            class="mt-1 w-full rounded-md border border-ink-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none"
            placeholder="Caller wants to reset their password..."
          ></textarea>
        </div>

        <div class="pt-2">
          <button
            class="rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-emerald-700 disabled:opacity-50"
            :disabled="synthesizeResult.isPending.value"
            @click="startSynthesis"
          >
            {{ synthesizeResult.isPending.value ? 'Synthesizing...' : 'Synthesize Scenarios' }}
          </button>
        </div>
        
        <div v-if="errorMsg" class="rounded-md bg-rose-50 p-4 text-sm text-rose-700 ring-1 ring-rose-200">
          {{ errorMsg }}
        </div>
        
        <div v-if="successMsg" class="rounded-md bg-emerald-50 p-4 text-sm text-emerald-700 ring-1 ring-emerald-200">
          <p class="font-bold">{{ successMsg }}</p>
          <button 
            class="mt-3 rounded-md bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white shadow-sm transition hover:bg-emerald-700"
            @click="router.push('/test')"
          >
            Run Test with Suite &rarr;
          </button>
        </div>
      </div>
    </section>
  </div>
</template>
