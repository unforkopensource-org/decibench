<script setup lang="ts">
// /test — launch a run from the browser.
//
// Three-mode toggle (deterministic / semantic / semantic+RAG), pre-flight
// checks before submit, live WebSocket progress feed. Single source of
// truth: this view posts to /runs and subscribes to /runs/stream/{task_id}
// — the same path the CLI takes, just via HTTP.

import { computed, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'

type Mode = 'deterministic' | 'semantic' | 'semantic-local' | 'semantic-rag'

const router = useRouter()

const target = ref('demo')
const suite = ref('quick')
const mode = ref<Mode>('deterministic')
const parallel = ref(2)

const status = ref<'idle' | 'queued' | 'running' | 'complete' | 'error'>('idle')
const taskId = ref<string | null>(null)
const score = ref<number | null>(null)
const runId = ref<string | null>(null)
const error = ref<string | null>(null)
const events = ref<Array<{ type: string; [k: string]: unknown }>>([])

let socket: WebSocket | null = null

const modeOptions: Array<{ id: Mode; label: string; desc: string; chip: string }> = [
  { id: 'deterministic', label: 'Deterministic', chip: 'FREE',
    desc: 'Latency, audio quality, compliance, keywords. No LLM judge.' },
  { id: 'semantic-local', label: 'Semantic (local)', chip: 'FREE',
    desc: 'Adds task completion + hallucination via local Ollama.' },
  { id: 'semantic', label: 'Semantic (cloud)', chip: '$',
    desc: 'Cloud LLM judge — best quality, requires API key + cost cap.' },
  { id: 'semantic-rag', label: 'Semantic + RAG', chip: '$',
    desc: 'Uses scenarios synthesized from your ingested knowledge corpus.' },
]

const canSubmit = computed(() => status.value === 'idle' || status.value === 'complete' || status.value === 'error')

async function start() {
  error.value = null
  score.value = null
  runId.value = null
  events.value = []
  status.value = 'queued'

  try {
    const resp = await fetch('/runs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        target: target.value,
        suite: suite.value,
        mode: mode.value,
        parallel: parallel.value,
      }),
    })
    if (!resp.ok) {
      error.value = `Could not start run: ${resp.status} ${await resp.text()}`
      status.value = 'error'
      return
    }
    const data = await resp.json()
    taskId.value = data.task_id
    status.value = 'running'
    openStream(data.task_id)
  } catch (e) {
    error.value = String(e)
    status.value = 'error'
  }
}

function openStream(id: string) {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  socket = new WebSocket(`${proto}//${window.location.host}/runs/stream/${id}`)
  socket.onmessage = (ev) => {
    const data = JSON.parse(ev.data)
    events.value.push(data)
    if (data.type === 'complete') {
      status.value = 'complete'
      runId.value = String(data.run_id)
      score.value = Number(data.score)
      socket?.close()
    } else if (data.type === 'error') {
      status.value = 'error'
      error.value = String(data.message)
      socket?.close()
    }
  }
  socket.onerror = () => {
    error.value = 'WebSocket connection error'
    status.value = 'error'
  }
}

function openRun() {
  if (runId.value) router.push(`/runs/${runId.value}`)
}

onUnmounted(() => { socket?.close() })
</script>

<template>
  <div class="space-y-6">
    <header>
      <h1 class="text-2xl font-bold text-ink-900">Test your agent</h1>
      <p class="mt-1 text-sm text-ink-500">
        Launch a run from the browser. Same execution path as the CLI — same
        results, same storage, same trust seal.
      </p>
    </header>

    <section class="rounded-lg border border-ink-200 bg-white p-6 shadow-sm">
      <div class="space-y-5">
        <div>
          <label class="block text-sm font-medium text-ink-700">Target</label>
          <input
            v-model="target"
            class="mt-1 w-full rounded-md border border-ink-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
            placeholder="demo, ws://localhost:8000/ws, retell://agent_xxx, …"
          />
          <p class="mt-1 text-xs text-ink-500">
            Try <code>demo</code> for a smoke test that needs no setup.
          </p>
        </div>

        <div>
          <label class="block text-sm font-medium text-ink-700">Mode</label>
          <div class="mt-2 grid gap-2 sm:grid-cols-2">
            <button
              v-for="opt in modeOptions"
              :key="opt.id"
              type="button"
              class="rounded-md border px-3 py-2 text-left transition"
              :class="mode === opt.id
                ? 'border-indigo-500 bg-indigo-50 ring-1 ring-indigo-500'
                : 'border-ink-200 hover:border-ink-300'"
              @click="mode = opt.id"
            >
              <div class="flex items-center justify-between">
                <span class="text-sm font-semibold text-ink-900">{{ opt.label }}</span>
                <span class="rounded-full bg-ink-100 px-2 py-0.5 text-[10px] font-medium text-ink-700">
                  {{ opt.chip }}
                </span>
              </div>
              <div class="mt-1 text-xs text-ink-600">{{ opt.desc }}</div>
            </button>
          </div>
        </div>

        <div class="grid gap-4 sm:grid-cols-2">
          <div>
            <label class="block text-sm font-medium text-ink-700">Suite</label>
            <input
              v-model="suite"
              class="mt-1 w-full rounded-md border border-ink-300 px-3 py-2 text-sm"
            />
          </div>
          <div>
            <label class="block text-sm font-medium text-ink-700">Parallel</label>
            <input
              v-model.number="parallel"
              type="number"
              min="1"
              max="10"
              class="mt-1 w-full rounded-md border border-ink-300 px-3 py-2 text-sm"
            />
          </div>
        </div>

        <div class="flex items-center gap-3 pt-2">
          <button
            class="rounded-md bg-ink-950 px-4 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-ink-800 disabled:cursor-not-allowed disabled:opacity-50"
            :disabled="!canSubmit"
            @click="start"
          >
            Run
          </button>
          <span v-if="status === 'running'" class="text-sm text-ink-500">
            ▶ Running…
          </span>
        </div>
      </div>
    </section>

    <section v-if="events.length" class="rounded-lg border border-ink-200 bg-white p-6 shadow-sm">
      <h2 class="text-sm font-semibold text-ink-700">Progress</h2>
      <ul class="mt-3 space-y-1 text-sm">
        <li v-for="(ev, i) in events" :key="i" class="font-mono text-xs text-ink-600">
          <span v-if="ev.type === 'scenario_done'">
            {{ (ev as any).passed ? '✓' : '✗' }}
            {{ (ev as any).scenario_id }}
            <span class="text-ink-400">score {{ (ev as any).score }}</span>
          </span>
          <span v-else-if="ev.type === 'started'">▶ started {{ (ev as any).suite }} on {{ (ev as any).target }} ({{ (ev as any).mode }})</span>
          <span v-else-if="ev.type === 'complete'" class="font-semibold text-emerald-700">
            ✓ complete: score {{ (ev as any).score }}
          </span>
          <span v-else-if="ev.type === 'error'" class="font-semibold text-rose-700">
            ✗ error: {{ (ev as any).message }}
          </span>
        </li>
      </ul>
      <div v-if="status === 'complete'" class="mt-4">
        <button
          class="rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700"
          @click="openRun"
        >
          Open run detail →
        </button>
      </div>
      <p v-if="error" class="mt-2 text-sm text-rose-600">{{ error }}</p>
    </section>
  </div>
</template>
