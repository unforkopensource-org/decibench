<script setup lang="ts">
import { computed } from 'vue'

import { useFailureStats, useRuns } from '../api'
import logoFinal from '../assets/logo-final.png'
import ErrorBox from '../components/ErrorBox.vue'
import Spinner from '../components/Spinner.vue'
import { formatScore, relativeTime } from '../format'

const { data: stats, isLoading: statsLoading, error: statsError } = useFailureStats()
const { data: runs, isLoading: runsLoading, error: runsError } = useRuns()

const latestRuns = computed(() => (runs.value ?? []).slice(0, 3))
const latestRun = computed(() => latestRuns.value[0] ?? null)

const avgScore = computed(() => {
  if (stats.value?.score?.avg) return stats.value.score.avg
  return latestRun.value?.score ?? 0
})

const failureCount = computed(() => {
  if (stats.value) return stats.value.failed
  return (runs.value ?? []).reduce((sum, r) => sum + r.failed, 0)
})

const passRate = computed(() => {
  if (stats.value) {
    const t = stats.value.failed + stats.value.passed
    return t > 0 ? Math.round((stats.value.passed / t) * 100) : 0
  }
  const total = (runs.value ?? []).reduce((s, r) => s + r.total_scenarios, 0)
  const passed = (runs.value ?? []).reduce((s, r) => s + r.passed, 0)
  return total > 0 ? Math.round((passed / total) * 100) : 0
})

const sourceCount = computed(() => {
  const stored = Object.keys(stats.value?.sources ?? {}).length
  if (stored > 0) return stored
  return new Set((runs.value ?? []).map(r => r.target)).size
})

function runTone(score: number): string {
  if (score >= 80) return 'text-emerald-600'
  if (score >= 60) return 'text-amber-600'
  return 'text-rose-600'
}
function runBar(score: number): string {
  if (score >= 80) return 'bg-emerald-500'
  if (score >= 60) return 'bg-amber-500'
  return 'bg-rose-500'
}
</script>

<template>
  <section>

    <!-- ═══════════════════════════════════════════════════════════════════ -->
    <!-- SECTION 1: HERO — The first thing anyone sees                     -->
    <!-- ═══════════════════════════════════════════════════════════════════ -->
    <section class="home-dark-band home-band relative overflow-hidden">
      <div class="hero-backdrop absolute inset-0" />
      <div class="hero-glow absolute inset-0" />

      <div class="section-shell relative flex min-h-[82svh] flex-col justify-end pb-16 pt-16 sm:pb-20">
        <div class="max-w-3xl">
          <!-- Logo + tagline -->
          <div class="mb-6 flex items-center gap-4">
            <div class="rounded-xl border border-white/10 bg-white/90 p-2.5 shadow-2xl">
              <img :src="logoFinal" alt="Decibench logo" class="h-16 w-16 rounded-lg object-cover" />
            </div>
            <div class="text-white/80">
              <div class="eyebrow text-white/50">The open standard for voice agent quality</div>
              <div class="mt-1 text-sm font-medium">Run. Inspect. Replay. Tighten.</div>
            </div>
          </div>

          <h1 class="max-w-3xl text-5xl font-semibold leading-[1.02] tracking-tight text-white sm:text-6xl lg:text-7xl">
            Ship voice agents<br />with proof, not vibes.
          </h1>

          <p class="mt-6 max-w-2xl text-base leading-7 text-white/75 sm:text-lg">
            Decibench is the open-source testing framework that catches what your ears miss.
            Run deterministic + AI-powered evaluations on any voice agent — Retell, Vapi, custom
            WebSocket, or HTTP — and get a single quality score backed by real metrics, not gut feelings.
          </p>

          <!-- CTAs -->
          <div class="mt-8 flex flex-wrap gap-3">
            <RouterLink to="/runs" class="btn bg-white text-ink-950 hover:bg-cloud-100 shadow-lg">
              Open latest runs
            </RouterLink>
            <RouterLink to="/inbox" class="btn ring-1 ring-white/20 bg-white/10 text-white hover:bg-white/20">
              Work the failures
            </RouterLink>
            <a
              href="https://github.com/unforkopensource-org/decibench"
              target="_blank"
              rel="noreferrer"
              class="btn ring-1 ring-white/20 bg-transparent text-white/80 hover:bg-white/10"
            >
              <svg class="h-4 w-4" viewBox="0 0 24 24" fill="currentColor"><path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/></svg>
              GitHub
            </a>
          </div>

          <!-- Feature pills -->
          <div class="mt-8 flex flex-wrap gap-2 text-sm text-white/80">
            <span class="rounded-lg border border-white/10 bg-white/10 px-3 py-1.5">100% local — no cloud</span>
            <span class="rounded-lg border border-white/10 bg-white/10 px-3 py-1.5">Deterministic, Semantic &amp; RAG</span>
            <span class="rounded-lg border border-white/10 bg-white/10 px-3 py-1.5">Import &rarr; Evaluate &rarr; Replay</span>
            <span class="rounded-lg border border-white/10 bg-white/10 px-3 py-1.5">Retell &middot; Vapi &middot; Custom</span>
            <span class="rounded-lg border border-white/10 bg-white/10 px-3 py-1.5">Open source &middot; Apache 2.0</span>
          </div>
        </div>

        <!-- Live metric tiles -->
        <div class="mt-14 grid gap-3 sm:grid-cols-2 md:grid-cols-4">
          <div class="metric-tile">
            <div class="metric-kicker">Average score</div>
            <div class="mt-3 text-3xl font-bold">{{ formatScore(avgScore) }}</div>
            <div class="mt-2 text-sm text-white/50">Across all stored evaluations</div>
          </div>
          <div class="metric-tile">
            <div class="metric-kicker">Failures queued</div>
            <div class="mt-3 text-3xl font-bold">{{ failureCount }}</div>
            <div class="mt-2 text-sm text-white/50">Ready to replay into regressions</div>
          </div>
          <div class="metric-tile">
            <div class="metric-kicker">Pass rate</div>
            <div class="mt-3 text-3xl font-bold">{{ passRate }}%</div>
            <div class="mt-2 text-sm text-white/50">Evaluations clearing the quality bar</div>
          </div>
          <div class="metric-tile">
            <div class="metric-kicker">Agent sources</div>
            <div class="mt-3 text-3xl font-bold">{{ sourceCount || '&mdash;' }}</div>
            <div class="mt-2 text-sm text-white/50">Live + imported call streams</div>
          </div>
        </div>
      </div>
    </section>

    <!-- ═══════════════════════════════════════════════════════════════════ -->
    <!-- SECTION 2: THE QUALITY LOOP — How Decibench works                 -->
    <!-- ═══════════════════════════════════════════════════════════════════ -->
    <section class="home-band bg-white">
      <div class="section-shell grid gap-10 py-20 lg:grid-cols-[1.15fr_0.85fr] lg:items-start">
        <div>
          <div class="eyebrow text-coral-600">The quality loop</div>
          <h2 class="section-title mt-3">Take a miss from production.<br />Make it part of the bar.</h2>
          <p class="section-copy">
            Pull in the real call, grade what actually happened, turn the miss into a scenario,
            then run the suite again. No cloud. No vendor lock-in. Everything stays on your machine.
          </p>

          <div class="mt-10 grid gap-4 sm:grid-cols-2">
            <div class="workflow-step">
              <div class="flex items-center gap-2">
                <span class="grid h-7 w-7 place-items-center rounded-lg bg-sage-100 text-xs font-bold text-sage-700">01</span>
                <div class="eyebrow text-sage-600">Import reality</div>
              </div>
              <p class="mt-3 text-lg font-semibold text-ink-950">Bring real calls straight into the loop.</p>
              <p class="mt-2 text-sm leading-6 text-ink-600">
                JSONL, Vapi webhooks, and Retell exports all land in the same local store. No format wrestling.
              </p>
            </div>
            <div class="workflow-step">
              <div class="flex items-center gap-2">
                <span class="grid h-7 w-7 place-items-center rounded-lg bg-coral-100 text-xs font-bold text-coral-700">02</span>
                <div class="eyebrow text-coral-600">Score the miss</div>
              </div>
              <p class="mt-3 text-lg font-semibold text-ink-950">See which checks failed before you guess why.</p>
              <p class="mt-2 text-sm leading-6 text-ink-600">
                Deterministic metrics (latency, audio, compliance) are free. Add an LLM judge for hallucination detection and task completion when nuance matters.
              </p>
            </div>
            <div class="workflow-step">
              <div class="flex items-center gap-2">
                <span class="grid h-7 w-7 place-items-center rounded-lg bg-gold-100 text-xs font-bold text-gold-700">03</span>
                <div class="eyebrow text-gold-600">Replay the edge</div>
              </div>
              <p class="mt-3 text-lg font-semibold text-ink-950">Turn a bad call into a regression case.</p>
              <p class="mt-2 text-sm leading-6 text-ink-600">
                Auto-generate YAML scenarios from failed calls. Keep them close to the failure so the fix stays honest.
              </p>
            </div>
            <div class="workflow-step">
              <div class="flex items-center gap-2">
                <span class="grid h-7 w-7 place-items-center rounded-lg bg-sage-100 text-xs font-bold text-sage-700">04</span>
                <div class="eyebrow text-sage-600">Tighten & rerun</div>
              </div>
              <p class="mt-3 text-lg font-semibold text-ink-950">Make the improvement visible in the next pass.</p>
              <p class="mt-2 text-sm leading-6 text-ink-600">
                Works for demo agents, HTTP targets, Retell agents, WebSocket endpoints, and bridge-backed sessions.
              </p>
            </div>
          </div>
        </div>

        <!-- CLI quickstart -->
        <div class="card-dark p-6">
          <div class="eyebrow text-white/40">Get started in 30 seconds</div>
          <p class="mt-3 max-w-sm text-sm leading-6 text-white/60">
            One install. One config. Run tests immediately with the built-in demo agent.
          </p>
          <pre class="mt-6 overflow-x-auto text-sm leading-7 text-white/90"><code><span class="text-emerald-400">$</span> pipx install git+https://github.com/unforkopensource-org/decibench.git
<span class="text-emerald-400">$</span> decibench init
<span class="text-emerald-400">$</span> decibench run --target demo --suite quick --mode deterministic
<span class="text-emerald-400">$</span> decibench serve</code></pre>
          <div class="mt-6 flex flex-wrap gap-2 text-xs text-white/60">
            <span class="rounded-lg border border-white/10 bg-white/5 px-3 py-1.5">No hosted control plane</span>
            <span class="rounded-lg border border-white/10 bg-white/5 px-3 py-1.5">API keys stay local</span>
            <span class="rounded-lg border border-white/10 bg-white/5 px-3 py-1.5">Runs stay inspectable</span>
          </div>
        </div>
      </div>
    </section>

    <!-- ═══════════════════════════════════════════════════════════════════ -->
    <!-- SECTION 3: EVERY COMMAND EXPLAINED                                -->
    <!-- ═══════════════════════════════════════════════════════════════════ -->
    <section class="home-dark-band">
      <div class="section-shell py-20">
        <div class="max-w-3xl">
          <div class="eyebrow text-white/40">CLI reference</div>
          <h2 class="mt-3 text-3xl font-semibold tracking-tight text-white sm:text-4xl">
            Every command you need. Nothing you don't.
          </h2>
          <p class="mt-4 max-w-2xl text-base leading-7 text-white/60 sm:text-lg">
            Decibench ships a single CLI that covers the entire testing workflow — from setup to evaluation to dashboarding.
          </p>
        </div>

        <div class="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <!-- init -->
          <div class="cli-card">
            <div class="flex items-center gap-3 mb-3">
              <span class="grid h-8 w-8 place-items-center rounded-lg bg-sage-500/20 text-sage-400">
                <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 5v14M5 12h14" /></svg>
              </span>
              <code class="text-sm font-bold text-white">decibench init</code>
            </div>
            <p class="text-sm text-white/60 leading-relaxed">
              Scaffold a new project. Creates <code class="text-white/80">decibench.toml</code> with your agent target,
              evaluation provider, and suite configuration. Interactive or <code class="text-white/80">--no-prompt</code> for CI.
            </p>
            <div class="mt-3 text-xs text-white/40">Use when: starting a new project</div>
          </div>

          <!-- run -->
          <div class="cli-card">
            <div class="flex items-center gap-3 mb-3">
              <span class="grid h-8 w-8 place-items-center rounded-lg bg-emerald-500/20 text-emerald-400">
                <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M5 3l14 9-14 9V3z" /></svg>
              </span>
              <code class="text-sm font-bold text-white">decibench run</code>
            </div>
            <p class="text-sm text-white/60 leading-relaxed">
              Execute a test suite against your agent. Measures latency, audio quality, compliance, conversation flow.
              Add <code class="text-white/80">--mode semantic</code> to enable LLM-judge evaluations (hallucination, task completion).
            </p>
            <div class="mt-3 text-xs text-white/40">Use when: testing quality before deploy</div>
          </div>

          <!-- serve -->
          <div class="cli-card">
            <div class="flex items-center gap-3 mb-3">
              <span class="grid h-8 w-8 place-items-center rounded-lg bg-violet-500/20 text-violet-400">
                <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="2" y="3" width="20" height="14" rx="2" /><path d="M8 21h8M12 17v4" /></svg>
              </span>
              <code class="text-sm font-bold text-white">decibench serve</code>
            </div>
            <p class="text-sm text-white/60 leading-relaxed">
              Launch this dashboard. Serves the API + workbench UI locally. All your runs, failures,
              and deep-dive analysis in one browser tab.
            </p>
            <div class="mt-3 text-xs text-white/40">Use when: reviewing results visually</div>
          </div>

          <!-- doctor -->
          <div class="cli-card">
            <div class="flex items-center gap-3 mb-3">
              <span class="grid h-8 w-8 place-items-center rounded-lg bg-amber-500/20 text-amber-400">
                <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" /></svg>
              </span>
              <code class="text-sm font-bold text-white">decibench doctor</code>
            </div>
            <p class="text-sm text-white/60 leading-relaxed">
              Health check your setup. Validates config, API keys, dependencies, and network
              connectivity to your agent. Fix issues before you waste a run.
            </p>
            <div class="mt-3 text-xs text-white/40">Use when: something feels off</div>
          </div>

          <!-- import -->
          <div class="cli-card">
            <div class="flex items-center gap-3 mb-3">
              <span class="grid h-8 w-8 place-items-center rounded-lg bg-coral-500/20 text-coral-400">
                <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3" /></svg>
              </span>
              <code class="text-sm font-bold text-white">decibench import</code>
            </div>
            <p class="text-sm text-white/60 leading-relaxed">
              Pull production calls into your local store. Supports Retell exports, Vapi webhooks,
              and raw JSONL transcripts. Score them with <code class="text-white/80">evaluate-calls</code> next.
            </p>
            <div class="mt-3 text-xs text-white/40">Use when: debugging production issues</div>
          </div>

          <!-- models preset -->
          <div class="cli-card">
            <div class="flex items-center gap-3 mb-3">
              <span class="grid h-8 w-8 place-items-center rounded-lg bg-white/10 text-white/60">
                <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" /></svg>
              </span>
              <code class="text-sm font-bold text-white">decibench models</code>
            </div>
            <p class="text-sm text-white/60 leading-relaxed">
              Configure which LLM judges your agent. Pick from presets (OpenAI, Anthropic, Gemini)
              or set a custom endpoint. Budget models cost as low as $0.003 per run.
            </p>
            <div class="mt-3 text-xs text-white/40">Use when: enabling semantic evaluation</div>
          </div>
        </div>
      </div>
    </section>

    <!-- ═══════════════════════════════════════════════════════════════════ -->
    <!-- SECTION 4: WHAT IT MEASURES — Deterministic vs Semantic           -->
    <!-- ═══════════════════════════════════════════════════════════════════ -->
    <section class="home-band bg-cloud-50">
      <div class="section-shell py-20">
        <div class="max-w-3xl">
          <div class="eyebrow text-sage-600">What it measures</div>
          <h2 class="section-title mt-3">Three evaluation modes. One quality score.</h2>
          <p class="section-copy">
            Start free with deterministic metrics. Add an LLM judge when you need deeper understanding. Or use RAG synthesis to test knowledge boundaries.
            All feed into the same 0-100 Decibench score.
          </p>
        </div>

        <div class="mt-10 grid gap-6 lg:grid-cols-3">
          <!-- Deterministic -->
          <div class="card p-6">
            <div class="flex items-center gap-3 mb-4">
              <span class="grid h-10 w-10 place-items-center rounded-xl bg-amber-100">
                <svg class="h-5 w-5 text-amber-700" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
              </span>
              <div>
                <h3 class="text-lg font-semibold text-ink-950">Deterministic</h3>
                <span class="text-xs font-medium text-amber-600 bg-amber-50 px-2 py-0.5 rounded-full">Free &mdash; no API key needed</span>
              </div>
            </div>
            <div class="space-y-3">
              <div class="flex items-start gap-3">
                <svg class="h-4 w-4 text-sage-500 mt-0.5 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M20 6L9 17l-5-5" /></svg>
                <div><span class="text-sm font-medium text-ink-900">Latency</span><span class="text-sm text-ink-500"> &mdash; Time-to-first-word, turn response times (P50/P95/P99), silence gaps</span></div>
              </div>
              <div class="flex items-start gap-3">
                <svg class="h-4 w-4 text-sage-500 mt-0.5 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M20 6L9 17l-5-5" /></svg>
                <div><span class="text-sm font-medium text-ink-900">Audio quality</span><span class="text-sm text-ink-500"> &mdash; MOS estimate, SNR analysis, spectral clarity, STT confidence</span></div>
              </div>
              <div class="flex items-start gap-3">
                <svg class="h-4 w-4 text-sage-500 mt-0.5 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M20 6L9 17l-5-5" /></svg>
                <div><span class="text-sm font-medium text-ink-900">Compliance</span><span class="text-sm text-ink-500"> &mdash; AI disclosure, PII leak detection, PCI no-echo checks</span></div>
              </div>
              <div class="flex items-start gap-3">
                <svg class="h-4 w-4 text-sage-500 mt-0.5 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M20 6L9 17l-5-5" /></svg>
                <div><span class="text-sm font-medium text-ink-900">Keywords &amp; flow</span><span class="text-sm text-ink-500"> &mdash; Presence/absence of expected phrases per turn</span></div>
              </div>
            </div>
          </div>

          <!-- Semantic -->
          <div class="card p-6 ring-2 ring-violet-200/60">
            <div class="flex items-center gap-3 mb-4">
              <span class="grid h-10 w-10 place-items-center rounded-xl bg-violet-100">
                <svg class="h-5 w-5 text-violet-700" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M2 3h6a4 4 0 014 4v14a3 3 0 00-3-3H2z" /><path d="M22 3h-6a4 4 0 00-4 4v14a3 3 0 013-3h7z" /></svg>
              </span>
              <div>
                <h3 class="text-lg font-semibold text-ink-950">Semantic AI Judge</h3>
                <span class="text-xs font-medium text-violet-600 bg-violet-50 px-2 py-0.5 rounded-full">LLM-powered &mdash; ~$0.003/run with Gemini</span>
              </div>
            </div>
            <div class="space-y-3">
              <div class="flex items-start gap-3">
                <svg class="h-4 w-4 text-violet-500 mt-0.5 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M20 6L9 17l-5-5" /></svg>
                <div><span class="text-sm font-medium text-ink-900">Hallucination detection</span><span class="text-sm text-ink-500"> &mdash; Catches fabricated info, wrong prices, invented policies</span></div>
              </div>
              <div class="flex items-start gap-3">
                <svg class="h-4 w-4 text-violet-500 mt-0.5 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M20 6L9 17l-5-5" /></svg>
                <div><span class="text-sm font-medium text-ink-900">Task completion</span><span class="text-sm text-ink-500"> &mdash; Did the agent actually achieve the caller's goal? Book the appointment? Process the order?</span></div>
              </div>
              <div class="flex items-start gap-3">
                <svg class="h-4 w-4 text-violet-500 mt-0.5 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M20 6L9 17l-5-5" /></svg>
                <div><span class="text-sm font-medium text-ink-900">Conversation quality</span><span class="text-sm text-ink-500"> &mdash; Coherence, tone, empathy, and flow assessed by an LLM judge</span></div>
              </div>
              <div class="flex items-start gap-3">
                <svg class="h-4 w-4 text-violet-500 mt-0.5 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M20 6L9 17l-5-5" /></svg>
                <div><span class="text-sm font-medium text-ink-900">Tool &amp; slot accuracy</span><span class="text-sm text-ink-500"> &mdash; Were the right functions called? Were data points extracted correctly?</span></div>
              </div>
            </div>
            <div class="mt-4 rounded-lg bg-violet-50 px-4 py-3">
              <p class="text-xs text-violet-700 leading-relaxed">
                <strong>Supported providers:</strong> Gemini (cheapest), OpenAI, Anthropic. Auto-detects your API key and picks the budget model.
                Run with <code class="bg-violet-100 px-1 py-0.5 rounded text-violet-900">--mode semantic</code>
              </p>
            </div>
          </div>

          <!-- Semantic + RAG -->
          <div class="card p-6 ring-2 ring-emerald-200/60">
            <div class="flex items-center gap-3 mb-4">
              <span class="grid h-10 w-10 place-items-center rounded-xl bg-emerald-100">
                <svg class="h-5 w-5 text-emerald-700" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" /></svg>
              </span>
              <div>
                <h3 class="text-lg font-semibold text-ink-950">Semantic + RAG</h3>
                <span class="text-xs font-medium text-emerald-600 bg-emerald-50 px-2 py-0.5 rounded-full">Knowledge-bound synthesis</span>
              </div>
            </div>
            <div class="space-y-3">
              <div class="flex items-start gap-3">
                <svg class="h-4 w-4 text-emerald-500 mt-0.5 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M20 6L9 17l-5-5" /></svg>
                <div><span class="text-sm font-medium text-ink-900">Auto-synthesis</span><span class="text-sm text-ink-500"> &mdash; Transforms your Markdown/PDF docs into comprehensive scenario suites.</span></div>
              </div>
              <div class="flex items-start gap-3">
                <svg class="h-4 w-4 text-emerald-500 mt-0.5 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M20 6L9 17l-5-5" /></svg>
                <div><span class="text-sm font-medium text-ink-900">Boundary testing</span><span class="text-sm text-ink-500"> &mdash; Tests if your agent hallucinates beyond provided context.</span></div>
              </div>
              <div class="flex items-start gap-3">
                <svg class="h-4 w-4 text-emerald-500 mt-0.5 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M20 6L9 17l-5-5" /></svg>
                <div><span class="text-sm font-medium text-ink-900">Grounded evaluations</span><span class="text-sm text-ink-500"> &mdash; The AI judge scores based strictly on the injected corpus.</span></div>
              </div>
            </div>
            <div class="mt-4 rounded-lg bg-emerald-50 px-4 py-3">
              <p class="text-xs text-emerald-700 leading-relaxed">
                <strong>Knowledge integration:</strong> Ingest files directly from the dashboard and run synthesis.
                Run with <code class="bg-emerald-100 px-1 py-0.5 rounded text-emerald-900">--mode semantic-rag</code>
              </p>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- ═══════════════════════════════════════════════════════════════════ -->
    <!-- SECTION 5: LIVE DASHBOARD PREVIEW — Show the workbench            -->
    <!-- ═══════════════════════════════════════════════════════════════════ -->
    <section class="home-band bg-white">
      <div class="section-shell py-20">
        <div class="max-w-3xl">
          <div class="eyebrow text-sage-600">Inside the workbench</div>
          <h2 class="section-title mt-3">See the miss clearly enough to fix it once.</h2>
          <p class="section-copy">
            When the score drops, you need the transcript, timing, failure reason, and regression
            trail right there with it. Not spread across three tabs and a Slack thread.
          </p>
        </div>

        <!-- Browser mock -->
        <div class="browser-frame mt-10">
          <div class="browser-chrome">
            <div class="flex items-center gap-2">
              <span class="browser-dot bg-rose-400" />
              <span class="browser-dot bg-amber-400" />
              <span class="browser-dot bg-emerald-400" />
            </div>
            <div class="browser-tab">127.0.0.1:8081 &mdash; Decibench Workbench</div>
          </div>
          <div class="grid gap-4 bg-white p-5 lg:grid-cols-[0.92fr_1.08fr]">
            <div class="rounded-xl border border-ink-200 bg-cloud-50 p-4">
              <div class="label">Failure queue</div>
              <div class="mt-1 text-2xl font-semibold text-ink-950">{{ failureCount }}</div>
              <div class="mt-4 space-y-3">
                <div class="rounded-lg border border-rose-200 bg-rose-50 p-3">
                  <div class="flex items-center justify-between gap-3">
                    <span class="text-sm font-semibold text-ink-950">AI Disclosure Missing</span>
                    <span class="pill-fail text-[10px]">compliance</span>
                  </div>
                  <p class="mt-2 text-sm leading-6 text-ink-600">
                    Agent never identifies itself as AI &mdash; blocks all scenarios from passing.
                  </p>
                </div>
                <div class="rounded-lg border border-amber-200 bg-amber-50 p-3">
                  <div class="flex items-center justify-between gap-3">
                    <span class="text-sm font-semibold text-ink-950">Task Completion 0%</span>
                    <span class="pill-warn text-[10px]">semantic</span>
                  </div>
                  <p class="mt-2 text-sm leading-6 text-ink-600">
                    LLM judge says the agent greets callers but doesn't follow through on goals.
                  </p>
                </div>
              </div>
            </div>

            <div class="grid gap-4">
              <div class="rounded-xl border border-ink-200 bg-white p-4">
                <div class="flex items-center justify-between gap-3">
                  <div>
                    <div class="label">Latest run</div>
                    <div class="text-lg font-semibold text-ink-950">
                      {{ latestRun?.suite ?? 'quick' }}
                    </div>
                  </div>
                  <div class="rounded-lg px-3 py-2 text-right" :class="latestRun ? runTone(latestRun.score) : 'text-ink-500'">
                    <div class="text-2xl font-semibold">{{ latestRun ? formatScore(latestRun.score) : '&mdash;' }}</div>
                    <div class="text-[10px] uppercase tracking-[0.16em] text-ink-400">score</div>
                  </div>
                </div>
                <div class="mt-4">
                  <div class="mb-1 flex items-center justify-between text-xs text-ink-500">
                    <span>Pass rate</span>
                    <span>{{ passRate }}%</span>
                  </div>
                  <div class="category-bar">
                    <div class="category-bar-fill bg-emerald-500" :style="{ width: `${passRate}%` }" />
                  </div>
                </div>
              </div>

              <div class="rounded-xl border border-ink-200 bg-ink-950 p-4 text-white">
                <div class="eyebrow text-white/40">Run loop</div>
                <pre class="mt-3 overflow-x-auto text-sm leading-7 text-white/80"><code>decibench import calls.jsonl
decibench evaluate-calls
decibench replay --from-failures
decibench run --suite full --mode semantic
decibench serve</code></pre>
              </div>
            </div>
          </div>
        </div>

        <!-- Feature cards -->
        <div class="mt-10 grid gap-4 lg:grid-cols-3">
          <div class="stat-card">
            <div class="eyebrow text-coral-600">Failure-first design</div>
            <p class="mt-3 text-lg font-semibold text-ink-950">Triage what broke before it becomes a pattern.</p>
            <p class="mt-2 text-sm leading-6 text-ink-600">
              Imported calls, local runs, and stored evaluations all feed the same failure inbox. No context switching.
            </p>
          </div>
          <div class="stat-card">
            <div class="eyebrow text-sage-600">Deep metric analysis</div>
            <p class="mt-3 text-lg font-semibold text-ink-950">Know whether the miss was policy, latency, or audio.</p>
            <p class="mt-2 text-sm leading-6 text-ink-600">
              Every scenario drills down to individual metrics with human-readable explanations, not just numbers.
            </p>
          </div>
          <div class="stat-card">
            <div class="eyebrow text-gold-600">Regression-ready</div>
            <p class="mt-3 text-lg font-semibold text-ink-950">Carry hard-earned failures back into the suite.</p>
            <p class="mt-2 text-sm leading-6 text-ink-600">
              One-click regression generation from any failed call. The best fix is the one that cannot quietly regress next week.
            </p>
          </div>
        </div>
      </div>
    </section>

    <!-- ═══════════════════════════════════════════════════════════════════ -->
    <!-- SECTION 6: LIVE SIGNAL — Recent runs from actual data             -->
    <!-- ═══════════════════════════════════════════════════════════════════ -->
    <section class="home-band bg-white">
      <div class="section-shell py-16">
        <div class="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div class="max-w-2xl">
            <div class="eyebrow text-coral-600">Live signal</div>
            <h2 class="section-title mt-3">Grounded in the runs already on disk.</h2>
            <p class="section-copy">
              Recent runs and stored evaluations stay visible so the homepage stays connected
              to the actual QA loop &mdash; not a detached marketing shell.
            </p>
          </div>
          <RouterLink to="/runs" class="btn-primary w-fit">Browse all runs</RouterLink>
        </div>

        <div v-if="runsLoading || statsLoading" class="mt-8 card p-6">
          <Spinner label="Loading recent local signal..." />
        </div>
        <ErrorBox v-else-if="runsError || statsError" :error="runsError ?? statsError" class="mt-8" />
        <div v-else class="mt-8 grid gap-4 lg:grid-cols-[0.95fr_1.05fr]">
          <!-- Stats panel -->
          <div class="card p-6">
            <div class="eyebrow text-sage-600">Current bench</div>
            <div class="mt-4 grid gap-4 sm:grid-cols-2">
              <div>
                <div class="label">Latest run</div>
                <div class="text-lg font-semibold text-ink-950">{{ latestRun?.suite ?? 'No runs yet' }}</div>
                <div class="mt-1 text-sm text-ink-500">{{ latestRun?.target ?? 'Run a suite to start.' }}</div>
              </div>
              <div>
                <div class="label">Score</div>
                <div class="text-3xl font-semibold" :class="runTone(latestRun?.score ?? 0)">{{ latestRun ? formatScore(latestRun.score) : '&mdash;' }}</div>
                <div class="mt-1 text-sm text-ink-500">{{ latestRun ? relativeTime(latestRun.timestamp) : '' }}</div>
              </div>
              <div>
                <div class="label">Stored evaluations</div>
                <div class="text-2xl font-semibold text-ink-950">{{ stats?.total_evaluations ?? '&mdash;' }}</div>
              </div>
              <div>
                <div class="label">Failure queue</div>
                <div class="text-2xl font-semibold text-rose-600">{{ stats?.failed ?? '&mdash;' }}</div>
              </div>
            </div>
          </div>

          <!-- Recent runs -->
          <div class="card overflow-hidden">
            <div class="border-b border-ink-200 px-5 py-4">
              <div class="eyebrow text-gold-600">Recent runs</div>
              <p class="mt-2 text-sm text-ink-600">Click any run for the full deep-dive analysis.</p>
            </div>
            <div v-if="latestRuns.length === 0" class="p-6 text-sm text-ink-500">No runs stored yet.</div>
            <div v-else class="divide-y divide-ink-100">
              <RouterLink
                v-for="run in latestRuns"
                :key="run.id"
                :to="{ name: 'run', params: { runId: run.id } }"
                class="flex items-center gap-4 px-5 py-4 transition-colors hover:bg-cloud-100/80"
              >
                <div class="min-w-0 flex-1">
                  <div class="flex items-center gap-2">
                    <span class="font-semibold text-ink-950">{{ run.suite }}</span>
                    <span class="text-ink-300">&rarr;</span>
                    <span class="truncate text-sm text-ink-500">{{ run.target }}</span>
                    <span
                      class="rounded-full px-2 py-0.5 text-[9px] font-bold uppercase"
                      :class="run.evaluation_mode === 'semantic' ? 'bg-violet-100 text-violet-700' : 'bg-amber-50 text-amber-600'"
                    >{{ run.evaluation_mode === 'semantic' ? 'semantic' : 'determ.' }}</span>
                  </div>
                  <div class="mt-1 text-xs text-ink-400">
                    {{ run.total_scenarios }} scenarios &middot; {{ relativeTime(run.timestamp) }}
                  </div>
                </div>
                <div class="w-28">
                  <div class="mb-1 flex items-center justify-between text-xs">
                    <span class="font-semibold" :class="runTone(run.score)">{{ formatScore(run.score) }}</span>
                    <span class="text-ink-400">/100</span>
                  </div>
                  <div class="category-bar">
                    <div class="category-bar-fill" :class="runBar(run.score)" :style="{ width: `${run.score}%` }" />
                  </div>
                </div>
              </RouterLink>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- ═══════════════════════════════════════════════════════════════════ -->
    <!-- SECTION 7: FINAL CTA                                             -->
    <!-- ═══════════════════════════════════════════════════════════════════ -->
    <section class="home-dark-band">
      <div class="section-shell py-20">
        <div class="grid gap-8 lg:grid-cols-[1.2fr_0.8fr] lg:items-center">
          <div>
            <div class="eyebrow text-white/40">Ready to run</div>
            <h2 class="mt-4 max-w-2xl text-4xl font-semibold tracking-tight text-white sm:text-5xl">
              Keep the quality loop<br />local, fast, and honest.
            </h2>
            <p class="mt-4 max-w-2xl text-base leading-7 text-white/60 sm:text-lg">
              Start with the failure inbox if you already have calls.
              Start with a run if you want to watch the next benchmark land.
              The same local workbench holds both stories together.
            </p>
            <p class="mt-6 text-sm text-white/40">
              Open source &middot; Apache 2.0 &middot; Made for teams who ship voice agents and need proof they work.
            </p>
          </div>

          <div class="flex flex-col gap-3 sm:flex-row lg:flex-col">
            <RouterLink to="/inbox" class="btn bg-white text-ink-950 hover:bg-cloud-100 shadow-lg">
              Open failure inbox
            </RouterLink>
            <RouterLink to="/runs" class="btn ring-1 ring-white/20 bg-white/10 text-white hover:bg-white/20">
              Open runs
            </RouterLink>
            <a
              href="https://github.com/unforkopensource-org/decibench"
              target="_blank"
              rel="noreferrer"
              class="btn ring-1 ring-white/20 bg-transparent text-white/70 hover:bg-white/10"
            >
              <svg class="h-4 w-4" viewBox="0 0 24 24" fill="currentColor"><path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/></svg>
              Star on GitHub
            </a>
          </div>
        </div>
      </div>
    </section>

  </section>
</template>
