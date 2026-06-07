<script setup lang="ts">
import { ref } from 'vue'
import { useUploadCallAudio, useEvaluateCall } from '../api'
import Spinner from './Spinner.vue'

const fileInput = ref<HTMLInputElement | null>(null)
const uploading = ref(false)
const evaluating = ref(false)
const error = ref<string | null>(null)

const agentName = ref('uploaded-agent')
const diarize = ref(false)
const uploadResult = ref<any>(null)
const evalResult = ref<any>(null)

const { mutateAsync: uploadAudio } = useUploadCallAudio()
const { mutateAsync: evaluateCall } = useEvaluateCall()

async function handleFile(e: Event) {
  const target = e.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file) return
  await upload(file)
}

async function handleDrop(e: DragEvent) {
  const file = e.dataTransfer?.files[0]
  if (!file) return
  await upload(file)
}

async function upload(file: File) {
  uploading.value = true
  error.value = null
  uploadResult.value = null
  evalResult.value = null

  try {
    const res = await uploadAudio({
      file,
      agent_name: agentName.value,
      diarize: diarize.value,
    })
    uploadResult.value = res
  } catch (e: any) {
    error.value = e.message || String(e)
  } finally {
    uploading.value = false
    if (fileInput.value) {
      fileInput.value.value = ''
    }
  }
}

async function evaluate(callId: string) {
  evaluating.value = true
  error.value = null
  try {
    const res = await evaluateCall(callId)
    evalResult.value = res
  } catch (e: any) {
    error.value = e.message || String(e)
  } finally {
    evaluating.value = false
  }
}

function reset() {
  uploadResult.value = null
  evalResult.value = null
  error.value = null
}
</script>

<template>
  <div class="card p-6 border-emerald-100 bg-gradient-to-br from-white to-cloud-50/30">
    <div class="flex items-center justify-between mb-4">
      <div>
        <h3 class="text-lg font-semibold text-ink-950">Upload Call Recording</h3>
        <p class="text-xs text-ink-500">Normalizes audio to 16 kHz mono PCM, transcribes, and saves as trace.</p>
      </div>
      <span class="eyebrow text-emerald-600 bg-emerald-50 px-2 py-0.5 rounded-md text-[9px]">Beta</span>
    </div>

    <!-- Inputs row -->
    <div v-if="!uploadResult" class="grid gap-4 sm:grid-cols-2 mb-4">
      <div>
        <label class="label">Agent Name</label>
        <input
          v-model="agentName"
          class="input bg-white"
          placeholder="support-bot-v1"
          type="text"
        />
      </div>
      <div>
        <label class="label">Diarization</label>
        <div class="flex items-center h-10">
          <label class="flex items-center gap-2 text-sm text-ink-700 cursor-pointer">
            <input
              v-model="diarize"
              type="checkbox"
              class="h-4 w-4 rounded border-ink-300 text-emerald-600 focus:ring-emerald-500"
            />
            <span>Enable Speaker Diarization</span>
          </label>
        </div>
      </div>
    </div>

    <!-- Drop Zone -->
    <div
      v-if="!uploading && !uploadResult"
      class="group border-2 border-dashed border-ink-200 hover:border-emerald-400 focus-within:ring-2 focus-within:ring-emerald-100 transition duration-150 rounded-xl bg-cloud-50/50 hover:bg-cloud-50/80 p-8 text-center cursor-pointer relative"
      @drop.prevent="handleDrop"
      @dragover.prevent
      @click="fileInput?.click()"
    >
      <input
        ref="fileInput"
        type="file"
        accept=".wav,.mp3,.m4a,.ogg,.flac"
        class="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
        @change="handleFile"
      />
      
      <!-- Upload Icon -->
      <div class="mx-auto w-12 h-12 mb-3 bg-emerald-100/50 group-hover:bg-emerald-100 text-emerald-700 rounded-full flex items-center justify-center transition">
        <svg class="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
        </svg>
      </div>

      <p class="text-sm font-semibold text-ink-900">Drag & drop call audio here, or click to browse</p>
      <p class="mt-1 text-xs text-ink-400">Supports WAV, MP3, M4A, OGG, FLAC</p>
    </div>

    <!-- Progress / Loading -->
    <div v-if="uploading" class="flex flex-col items-center justify-center p-8 border-2 border-dashed border-emerald-200 bg-emerald-50/20 rounded-xl">
      <Spinner label="Uploading, transcoding & transcribing audio..." />
    </div>

    <!-- Success Result -->
    <div v-if="uploadResult" class="space-y-4">
      <div class="rounded-xl border border-emerald-200 bg-emerald-50/30 p-4">
        <div class="flex items-center gap-3">
          <div class="w-8 h-8 rounded-full bg-emerald-100 text-emerald-700 flex items-center justify-center">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
            </svg>
          </div>
          <div>
            <h4 class="text-sm font-bold text-ink-950">Audio Imported Successfully</h4>
            <p class="text-xs text-ink-500 font-mono mt-0.5">Call ID: {{ uploadResult.call_id }}</p>
          </div>
        </div>

        <div class="mt-4 grid grid-cols-2 gap-4 text-xs">
          <div>
            <span class="text-ink-400 block">Duration</span>
            <span class="font-semibold text-ink-900">{{ (uploadResult.duration_ms / 1000).toFixed(1) }} seconds</span>
          </div>
          <div>
            <span class="text-ink-400 block">Agent Target</span>
            <span class="font-semibold text-ink-900">{{ uploadResult.target || 'uploaded-agent' }}</span>
          </div>
        </div>
      </div>

      <div class="flex items-center gap-3">
        <button
          v-if="!evalResult && !evaluating"
          class="rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white font-medium text-sm px-4 py-2 shadow transition"
          @click="evaluate(uploadResult.call_id)"
        >
          Evaluate Call Recording
        </button>
        
        <div v-if="evaluating" class="flex items-center gap-2 py-2 text-sm text-emerald-700">
          <svg class="animate-spin h-4 w-4 text-emerald-700" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
          </svg>
          <span>Running evaluator stack...</span>
        </div>

        <button
          class="rounded-lg border border-ink-200 hover:bg-ink-50 text-ink-700 font-medium text-sm px-4 py-2 transition"
          @click="reset"
        >
          Upload Another
        </button>
      </div>

      <!-- Eval Outcome -->
      <div v-if="evalResult" class="rounded-xl border p-4" :class="evalResult.passed ? 'border-emerald-200 bg-emerald-50/20' : 'border-rose-200 bg-rose-50/20'">
        <div class="flex items-center justify-between">
          <div>
            <h5 class="text-sm font-bold" :class="evalResult.passed ? 'text-emerald-900' : 'text-rose-900'">
              {{ evalResult.passed ? 'Evaluation Passed' : 'Evaluation Failed' }}
            </h5>
            <p class="text-xs text-ink-500 mt-0.5">Scored against canonical criteria stack.</p>
          </div>
          <div class="text-right">
            <div class="text-2xl font-bold" :class="evalResult.passed ? 'text-emerald-600' : 'text-rose-600'">
              {{ Math.round(evalResult.score) }}/100
            </div>
          </div>
        </div>

        <!-- Failure Details -->
        <div v-if="evalResult.failures && evalResult.failures.length" class="mt-3 space-y-1">
          <span class="text-xs font-bold text-rose-700 block">Failures:</span>
          <div v-for="failure in evalResult.failures" :key="failure" class="text-xs text-rose-600 bg-rose-50 border border-rose-100 rounded px-2.5 py-1">
            {{ failure }}
          </div>
        </div>

        <div class="mt-4 flex gap-2">
          <RouterLink
            :to="{ name: 'call', params: { callId: uploadResult.call_id } }"
            class="text-xs font-semibold text-emerald-700 hover:text-emerald-800 underline"
          >
            Go to Call Timeline & Details &rarr;
          </RouterLink>
        </div>
      </div>
    </div>

    <!-- Error state -->
    <div v-if="error" class="mt-4 rounded-xl border border-rose-200 bg-rose-50 p-4 text-xs text-rose-800 font-medium flex gap-2 items-start">
      <svg class="h-4 w-4 text-rose-600 flex-shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
      </svg>
      <div>
        <p class="font-bold">Import Error</p>
        <p class="mt-0.5 leading-relaxed">{{ error }}</p>
      </div>
    </div>
  </div>
</template>
