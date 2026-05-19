<script setup lang="ts">
// /rag — knowledge corpus management.
//
// Three actions in one screen: see what's ingested, paste new context,
// upload files. Synthesize moves to the test form once the corpus is
// non-empty.

import { computed, onMounted, ref } from 'vue'

interface DocRow {
  id: string
  title: string
  source_path: string
  mime_type: string
  bytes: number
  embedding_provider: string
  ingested_at: string
  chunk_count: number
}

const docs = ref<DocRow[]>([])
const stats = ref<{ documents: number; chunks: number; configured_embedder: string; allow_cloud: boolean } | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)
const pasteText = ref('')
const pasteTitle = ref('agent-context')

async function refresh() {
  loading.value = true
  error.value = null
  try {
    const [docsResp, statsResp] = await Promise.all([
      fetch('/rag/documents').then(r => r.json()),
      fetch('/rag/stats').then(r => r.json()),
    ])
    docs.value = docsResp.documents
    stats.value = statsResp
  } catch (e) {
    error.value = String(e)
  } finally {
    loading.value = false
  }
}

async function ingestText() {
  if (!pasteText.value.trim()) return
  error.value = null
  try {
    const resp = await fetch('/rag/ingest-text', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: pasteText.value, title: pasteTitle.value }),
    })
    if (!resp.ok) {
      error.value = `Ingest failed: ${resp.status} ${await resp.text()}`
      return
    }
    pasteText.value = ''
    refresh()
  } catch (e) {
    error.value = String(e)
  }
}

async function uploadFiles(event: Event) {
  const input = event.target as HTMLInputElement
  const files = input.files
  if (!files || files.length === 0) return
  const form = new FormData()
  for (const f of Array.from(files)) form.append('files', f)
  try {
    const resp = await fetch('/rag/ingest-files', { method: 'POST', body: form })
    if (!resp.ok) {
      error.value = `Upload failed: ${resp.status} ${await resp.text()}`
      return
    }
    input.value = ''
    refresh()
  } catch (e) {
    error.value = String(e)
  }
}

async function remove(id: string) {
  if (!confirm('Remove this document and all its chunks?')) return
  await fetch(`/rag/documents/${id}`, { method: 'DELETE' })
  refresh()
}

const isLocal = computed(() => (stats.value?.configured_embedder ?? '').startsWith('embed://local'))

onMounted(refresh)
</script>

<template>
  <div class="space-y-6">
    <header>
      <h1 class="text-2xl font-bold text-ink-900">Knowledge corpus</h1>
      <p class="mt-1 text-sm text-ink-500">
        Documents you ingest stay on this machine unless you explicitly enable
        cloud egress. Scenarios synthesized from this corpus are tested against
        your live agent.
      </p>
    </header>

    <section v-if="stats" class="rounded-lg border border-ink-200 bg-white p-4 shadow-sm">
      <div class="flex items-center justify-between">
        <div class="flex flex-wrap gap-x-6 gap-y-1 text-sm">
          <span><strong>{{ stats.documents }}</strong> documents</span>
          <span><strong>{{ stats.chunks }}</strong> chunks</span>
          <span>embedder: <code>{{ stats.configured_embedder }}</code></span>
          <span class="rounded-full px-2 py-0.5 text-[10px] font-medium"
            :class="isLocal && !stats.allow_cloud
              ? 'bg-emerald-100 text-emerald-700'
              : 'bg-amber-100 text-amber-800'">
            {{ isLocal && !stats.allow_cloud ? 'fully local' : 'cloud egress allowed' }}
          </span>
        </div>
        <RouterLink
          v-if="stats.documents > 0"
          to="/rag/synthesize"
          class="rounded-md bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white shadow-sm transition hover:bg-emerald-700"
        >
          Synthesize Scenarios &rarr;
        </RouterLink>
      </div>
    </section>

    <section class="rounded-lg border border-ink-200 bg-white p-6 shadow-sm">
      <h2 class="text-sm font-semibold text-ink-700">Add knowledge</h2>
      <div class="mt-4 grid gap-4 lg:grid-cols-2">
        <div>
          <label class="block text-xs font-medium text-ink-700">Upload files</label>
          <input
            type="file"
            multiple
            accept=".md,.markdown,.txt,.rst"
            class="mt-2 block w-full rounded-md border border-dashed border-ink-300 px-3 py-6 text-sm text-ink-500 file:mr-3 file:rounded-md file:border-0 file:bg-ink-950 file:px-3 file:py-1.5 file:text-xs file:text-white"
            @change="uploadFiles"
          />
          <p class="mt-1 text-xs text-ink-500">
            Markdown / text supported in v1. Drop multiple files at once.
          </p>
        </div>
        <div>
          <label class="block text-xs font-medium text-ink-700">Or paste agent context</label>
          <input
            v-model="pasteTitle"
            class="mt-2 w-full rounded-md border border-ink-300 px-3 py-1.5 text-xs"
            placeholder="title (e.g. agent-prompt)"
          />
          <textarea
            v-model="pasteText"
            rows="6"
            class="mt-2 w-full rounded-md border border-ink-300 px-3 py-2 text-xs font-mono"
            placeholder="# Your agent's system prompt, conversation flow, FAQs…"
          ></textarea>
          <button
            class="mt-2 rounded-md bg-ink-950 px-3 py-1.5 text-xs font-medium text-white disabled:opacity-50"
            :disabled="!pasteText.trim()"
            @click="ingestText"
          >
            Ingest
          </button>
        </div>
      </div>
      <p v-if="error" class="mt-3 text-sm text-rose-600">{{ error }}</p>
    </section>

    <section>
      <h2 class="text-sm font-semibold text-ink-700">Documents in corpus</h2>
      <div v-if="loading" class="mt-4 text-sm text-ink-500">Loading…</div>
      <div v-else-if="docs.length === 0" class="mt-4 rounded-lg border border-dashed border-ink-300 p-8 text-center text-sm text-ink-500">
        Empty. Paste an agent prompt or upload a file above to get started.
      </div>
      <table v-else class="mt-3 w-full text-left text-sm">
        <thead class="text-xs uppercase text-ink-500">
          <tr>
            <th class="py-2">Title</th>
            <th class="py-2">Chunks</th>
            <th class="py-2">Bytes</th>
            <th class="py-2">Embedder</th>
            <th class="py-2">Ingested</th>
            <th class="py-2"></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="d in docs" :key="d.id" class="border-t border-ink-200">
            <td class="py-2"><strong>{{ d.title }}</strong> <span class="text-ink-400">{{ d.id.slice(0,8) }}</span></td>
            <td class="py-2">{{ d.chunk_count }}</td>
            <td class="py-2">{{ d.bytes }}</td>
            <td class="py-2"><code class="text-xs">{{ d.embedding_provider }}</code></td>
            <td class="py-2 text-xs text-ink-500">{{ d.ingested_at }}</td>
            <td class="py-2 text-right">
              <button class="text-xs text-rose-600 hover:underline" @click="remove(d.id)">
                Remove
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </section>
  </div>
</template>
