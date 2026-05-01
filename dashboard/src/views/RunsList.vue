<script setup lang="ts">
import { useRuns } from '../api'
import ErrorBox from '../components/ErrorBox.vue'
import Spinner from '../components/Spinner.vue'
import { formatScore, relativeTime } from '../format'

const { data, isLoading, error } = useRuns()

function scoreColor(score: number): string {
  if (score >= 80) return 'text-emerald-600'
  if (score >= 60) return 'text-amber-600'
  return 'text-rose-600'
}

function scoreBg(score: number): string {
  if (score >= 80) return 'bg-emerald-500'
  if (score >= 60) return 'bg-amber-500'
  return 'bg-rose-500'
}

function scoreGradient(score: number): string {
  if (score >= 80) return 'from-emerald-500 to-emerald-600'
  if (score >= 60) return 'from-amber-500 to-amber-600'
  return 'from-rose-500 to-rose-600'
}

function gradeLabel(score: number): string {
  if (score >= 90) return 'Excellent'
  if (score >= 75) return 'Good'
  if (score >= 60) return 'Fair'
  if (score >= 40) return 'Needs Work'
  return 'Critical'
}
</script>

<template>
  <section class="space-y-5">
    <div class="flex items-end justify-between">
      <div>
        <h1 class="text-2xl font-bold tracking-tight text-ink-900">Test Runs</h1>
        <p class="mt-1 text-sm text-ink-500">
          Quality assessments from <code class="text-xs bg-ink-100 px-1 py-0.5 rounded font-mono">decibench run</code>
        </p>
      </div>
      <div v-if="data && data.length > 0" class="flex items-center gap-3">
        <span class="text-sm text-ink-400">{{ data.length }} run{{ data.length !== 1 ? 's' : '' }}</span>
      </div>
    </div>

    <div v-if="isLoading" class="card p-12 text-center"><Spinner label="Loading runs..." /></div>
    <ErrorBox v-else-if="error" :error="error" />

    <!-- Empty state -->
    <div v-else-if="!data || data.length === 0" class="card p-16 text-center">
      <div class="mx-auto mb-4 grid h-14 w-14 place-items-center rounded-2xl bg-ink-100">
        <svg class="h-7 w-7 text-ink-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M2 20h20" /><path d="M5 20V8l4 4 4-8 4 6 4-4v14" />
        </svg>
      </div>
      <p class="text-ink-600 font-medium">No runs yet</p>
      <p class="mt-1 text-sm text-ink-400">Run your first test:</p>
      <code class="mt-3 inline-block rounded-lg bg-ink-900 px-4 py-2 text-sm text-emerald-400 font-mono">
        decibench run --suite quick
      </code>
    </div>

    <!-- Runs list -->
    <div v-else class="space-y-2">
      <div
        v-for="run in data"
        :key="run.id"
        class="card group cursor-pointer overflow-hidden transition-all duration-150 hover:shadow-md hover:border-ink-300/60"
        @click="$router.push({ name: 'run', params: { runId: run.id } })"
      >
        <div class="flex items-center gap-4 px-5 py-4">
          <!-- Score badge -->
          <div class="flex-shrink-0">
            <div
              class="grid h-12 w-12 place-items-center rounded-xl text-white font-bold text-base shadow-sm"
              :class="`bg-gradient-to-br ${scoreGradient(run.score)}`"
            >
              {{ Math.round(run.score) }}
            </div>
          </div>

          <!-- Info -->
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2">
              <span class="font-semibold text-ink-900">{{ run.suite }}</span>
              <span class="text-ink-300">&rarr;</span>
              <span class="text-sm text-ink-500 truncate">{{ run.target.split('//')[1] || run.target }}</span>
            </div>
            <div class="mt-1.5 flex items-center gap-2 text-xs flex-wrap">
              <span class="pill-pass">{{ run.passed }} passed</span>
              <span v-if="run.failed > 0" class="pill-fail">{{ run.failed }} failed</span>
              <span class="text-ink-400">{{ run.total_scenarios }} scenarios</span>
              <span
                class="rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider"
                :class="run.evaluation_mode === 'semantic'
                  ? 'bg-violet-100 text-violet-700 ring-1 ring-violet-200/60'
                  : 'bg-amber-50 text-amber-600 ring-1 ring-amber-200/60'"
              >
                {{ run.evaluation_mode === 'semantic' ? 'Semantic' : 'Deterministic' }}
              </span>
              <span v-if="run.evaluation_mode === 'semantic' && run.judge_model" class="text-[10px] text-violet-500 font-medium">
                {{ run.judge_model }}
              </span>
            </div>
          </div>

          <!-- Grade -->
          <div class="hidden lg:block text-right mr-2">
            <div class="text-xs font-semibold" :class="scoreColor(run.score)">{{ gradeLabel(run.score) }}</div>
          </div>

          <!-- Score bar -->
          <div class="hidden sm:block w-28">
            <div class="flex items-center justify-between text-xs mb-1">
              <span class="font-semibold" :class="scoreColor(run.score)">{{ formatScore(run.score) }}</span>
              <span class="text-ink-400">/100</span>
            </div>
            <div class="h-1.5 rounded-full bg-ink-100">
              <div class="h-full rounded-full transition-all duration-700" :class="scoreBg(run.score)" :style="{ width: `${run.score}%` }"></div>
            </div>
          </div>

          <!-- Timestamp + arrow -->
          <div class="flex items-center gap-3">
            <span class="text-xs text-ink-400">{{ relativeTime(run.timestamp) }}</span>
            <svg class="h-4 w-4 text-ink-300 transition-transform group-hover:translate-x-0.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M9 18l6-6-6-6" />
            </svg>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>
