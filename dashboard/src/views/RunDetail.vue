<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRun } from '../api'
import type { MetricResult, EvalResult } from '../api'
import ErrorBox from '../components/ErrorBox.vue'
import Spinner from '../components/Spinner.vue'
import { formatDuration, formatScore, formatTimestamp } from '../format'

const props = defineProps<{ runId: string }>()
const runId = computed(() => props.runId)
const { data, isLoading, error } = useRun(runId)

const expandedScenarios = ref<Set<string>>(new Set())
function toggleScenario(id: string) {
  if (expandedScenarios.value.has(id)) expandedScenarios.value.delete(id)
  else expandedScenarios.value.add(id)
}

// ── Core computed ──
const passRate = computed(() => {
  if (!data.value) return 0
  return Math.round((data.value.passed / data.value.total_scenarios) * 100)
})
const isSemantic = computed(() => data.value?.evaluation_mode === 'semantic')

// ── Executive Insight (computed from data, not LLM) ──
const executiveInsight = computed(() => {
  if (!data.value) return { summary: '', details: [] as string[] }
  const d = data.value
  const score = d.decibench_score
  const total = d.total_scenarios

  // Aggregate metrics across all scenarios
  const allMetrics: Record<string, { passed: number; total: number; values: number[] }> = {}
  for (const er of d.results) {
    for (const m of Object.values(er.metrics)) {
      if (!allMetrics[m.name]) allMetrics[m.name] = { passed: 0, total: 0, values: [] }
      allMetrics[m.name].total++
      allMetrics[m.name].values.push(m.value)
      if (m.passed) allMetrics[m.name].passed++
    }
  }

  // Find strengths (>90% pass rate)
  const strengths: string[] = []
  const weaknesses: string[] = []

  // Latency
  const ttfw = allMetrics['ttfw_ms']
  if (ttfw) {
    const avg = ttfw.values.reduce((a, b) => a + b, 0) / ttfw.values.length
    if (ttfw.passed === ttfw.total) strengths.push(`responds in ${avg.toFixed(0)}ms average (fast)`)
    else weaknesses.push(`slow first response (${avg.toFixed(0)}ms average)`)
  }

  // Audio
  const audio = allMetrics['audio_quality_estimate']
  if (audio) {
    const avg = audio.values.reduce((a, b) => a + b, 0) / audio.values.length
    if (avg >= 3.0) strengths.push(`audio quality ${avg.toFixed(1)}/5.0`)
  }

  // Silence
  const silence = allMetrics['silence_pct']
  if (silence && silence.passed === silence.total) strengths.push('no dead air')

  // PII
  const pii = allMetrics['pii_violations']
  if (pii && pii.passed === pii.total) strengths.push('no PII leaks')

  // Hallucination
  const hall = allMetrics['hallucination_rate']
  if (hall) {
    const avg = hall.values.reduce((a, b) => a + b, 0) / hall.values.length
    if (hall.passed === hall.total) strengths.push(`0% hallucination rate (fully grounded)`)
    else weaknesses.push(`${avg.toFixed(1)}% hallucination rate`)
  }

  // AI disclosure
  const disc = allMetrics['ai_disclosure']
  if (disc && disc.passed === 0) weaknesses.push('never identifies itself as AI')

  // Task completion
  const task = allMetrics['task_completion']
  if (task) {
    const avg = task.values.reduce((a, b) => a + b, 0) / task.values.length
    if (task.passed === 0) weaknesses.push(`0% task completion — doesn't achieve caller goals`)
    else if (avg < 50) weaknesses.push(`only ${avg.toFixed(0)}% task completion`)
  }

  // Build summary
  const target = d.target.split('//')[1] || d.target
  const strengthStr = strengths.length > 0
    ? `Strengths: ${strengths.slice(0, 3).join(', ')}.`
    : ''
  const weakStr = weaknesses.length > 0
    ? `Critical gaps: ${weaknesses.join('; ')}.`
    : ''

  const summary = `Tested ${total} scenarios against ${target}. Score ${score.toFixed(1)}/100. ${strengthStr} ${weakStr}`.trim()

  // Build detail bullets
  const details: string[] = []
  if (disc && disc.passed === 0) {
    details.push(`AI Disclosure: Agent says "Angela from Real Estate AI team" but never explicitly states "I am an AI" — this single check blocks all ${total} scenarios from passing.`)
  }
  if (task && task.passed === 0 && isSemantic.value) {
    const taskReasoning = getJudgeReasoning('task_completion')
    if (taskReasoning) {
      const firstLine = taskReasoning.split(/[.!]\s/)[0]
      details.push(`Task Completion (AI Judge): ${firstLine}. Score: 0% across ${task.total} scenarios.`)
    } else {
      details.push(`Task Completion: The LLM judge (${d.judge_model || 'gemini'}) confirmed the agent doesn't complete any test goals — it greets callers but doesn't follow through on bookings, transfers, or orders.`)
    }
  }
  if (hall && isSemantic.value) {
    const hallReasoning = getJudgeReasoning('hallucination_rate')
    if (hallReasoning) {
      const firstLine = hallReasoning.split(/[.!]\s/)[0]
      details.push(`Hallucination (AI Judge): ${firstLine}. ${hall.passed === hall.total ? 'All grounding checks passed.' : `${hall.total - hall.passed} scenarios flagged.`}`)
    } else if (hall.passed === hall.total) {
      details.push(`Hallucination: Good news — the agent doesn't fabricate information. All ${hall.total} grounding checks passed with 0% hallucination.`)
    }
  }
  const kw = allMetrics['keyword_presence_t0']
  if (kw && kw.passed < kw.total) {
    details.push(`Keywords: ${kw.total - kw.passed} of ${kw.total} scenarios missing expected phrases in the agent's first response. Review scenario YAML to align prompts.`)
  }

  return { summary, details }
})

// ── Fix These First ──
const fixActions = computed(() => {
  if (!data.value) return []
  const total = data.value.total_scenarios
  const actions: Array<{
    title: string; impact: string; failCount: number; failRate: number;
    description: string; severity: 'critical' | 'high' | 'medium'
  }> = []

  // Aggregate failures
  const fails: Record<string, { count: number; details: Array<Record<string, unknown>> }> = {}
  for (const er of data.value.results) {
    for (const m of Object.values(er.metrics)) {
      if (!m.passed && m.threshold != null) {
        if (!fails[m.name]) fails[m.name] = { count: 0, details: [] }
        fails[m.name].count++
        if (m.details) fails[m.name].details.push(m.details)
      }
    }
  }

  // AI disclosure
  if (fails['ai_disclosure']) {
    const f = fails['ai_disclosure']
    actions.push({
      title: 'Add AI disclosure to agent greeting',
      impact: `Blocking ${f.count}/${total} scenarios`,
      failCount: f.count, failRate: f.count / total,
      description: 'Your agent introduces itself as "Angela from the Real Estate AI team" but never explicitly states it\'s an AI or virtual assistant. Add "I\'m an AI assistant" to the greeting prompt. Most jurisdictions require this disclosure.',
      severity: f.count === total ? 'critical' : 'high',
    })
  }

  // Task completion
  if (fails['task_completion']) {
    const f = fails['task_completion']
    actions.push({
      title: 'Connect task completion tools',
      impact: `${f.count}/${total} scenarios at 0%`,
      failCount: f.count, failRate: f.count / total,
      description: 'The LLM judge evaluated whether your agent achieved each scenario\'s goal (booking appointments, processing orders, handling transfers) and found it completes none of them. Wire up the relevant tool calls and ensure the agent follows through on requests.',
      severity: 'critical',
    })
  }

  // Compliance
  if (fails['compliance_score'] && !fails['ai_disclosure']) {
    const f = fails['compliance_score']
    actions.push({
      title: 'Fix compliance violations',
      impact: `${f.count}/${total} scenarios failing`,
      failCount: f.count, failRate: f.count / total,
      description: 'Composite compliance score failed. Check AI disclosure, PII handling, and PCI requirements.',
      severity: 'high',
    })
  }

  // Keywords
  for (const [name, f] of Object.entries(fails)) {
    if (name.startsWith('keyword_presence')) {
      const turnIdx = name.slice(-1)
      const missingKeywords = f.details
        .flatMap(d => (d.missing as string[]) || [])
        .filter((v, i, a) => a.indexOf(v) === i)
        .slice(0, 5)
      actions.push({
        title: `Add expected keywords to agent turn ${turnIdx}`,
        impact: `Missing in ${f.count}/${total} scenarios`,
        failCount: f.count, failRate: f.count / total,
        description: `Scenarios expect specific phrases like "${missingKeywords.join('", "')}" in the agent's response. Update your agent's prompt or review scenario definitions to ensure alignment.`,
        severity: 'medium',
      })
    }
  }

  // Tool calls
  if (fails['tool_call_correctness']) {
    const f = fails['tool_call_correctness']
    actions.push({
      title: 'Fix tool call integration',
      impact: `${f.count}/${total} scenarios`,
      failCount: f.count, failRate: f.count / total,
      description: 'Expected tool calls were not invoked. The agent needs to call the right functions when handling orders, bookings, or transfers.',
      severity: 'high',
    })
  }

  // TTFW
  if (fails['ttfw_ms']) {
    const f = fails['ttfw_ms']
    actions.push({
      title: 'Reduce time-to-first-word',
      impact: `${f.count}/${total} scenarios too slow`,
      failCount: f.count, failRate: f.count / total,
      description: 'Agent takes too long to start speaking. Optimize cold-start latency or add a quick filler phrase ("One moment...") while processing.',
      severity: 'medium',
    })
  }

  return actions.sort((a, b) => b.failRate - a.failRate).slice(0, 5)
})

// ── Strengths & Weaknesses ──
const categoryBreakdown = computed(() => {
  if (!data.value) return []
  const cats: Record<string, { passed: number; total: number; hasJudge: boolean; scores: number[] }> = {}
  for (const er of data.value.results) {
    for (const m of Object.values(er.metrics)) {
      const cat = metricCategory(m.name)
      if (!cats[cat]) cats[cat] = { passed: 0, total: 0, hasJudge: false, scores: [], }
      cats[cat].total++
      cats[cat].scores.push(m.value)
      if (m.passed) cats[cat].passed++
      if (isSemanticMetric(m.name)) cats[cat].hasJudge = true
    }
  }
  return Object.entries(cats).map(([name, c]) => ({
    name,
    passRate: Math.round((c.passed / c.total) * 100),
    passed: c.passed,
    total: c.total,
    hasJudge: c.hasJudge,
  })).sort((a, b) => b.passRate - a.passRate)
})

const strengths = computed(() => categoryBreakdown.value.filter(c => c.passRate >= 80))
const weaknesses = computed(() => categoryBreakdown.value.filter(c => c.passRate < 80))

// ── Score interpretation ──
const scoreGrade = computed(() => {
  if (!data.value) return { label: '', desc: '', color: '' }
  const s = data.value.decibench_score
  if (s >= 90) return { label: 'Excellent', desc: 'Production-ready.', color: 'text-emerald-500' }
  if (s >= 75) return { label: 'Good', desc: 'Minor gaps to address.', color: 'text-emerald-500' }
  if (s >= 60) return { label: 'Fair', desc: 'Notable quality gaps.', color: 'text-amber-500' }
  if (s >= 40) return { label: 'Needs Work', desc: 'Significant issues.', color: 'text-amber-500' }
  return { label: 'Critical', desc: 'Fundamental issues.', color: 'text-rose-500' }
})

// ── Helpers ──
function isSemanticMetric(name: string): boolean {
  return ['hallucination_rate', 'task_completion', 'conversation_quality'].includes(name)
}

function scoreColor(s: number): string {
  return s >= 80 ? 'text-emerald-600' : s >= 60 ? 'text-amber-600' : 'text-rose-600'
}
function scoreStroke(s: number): string {
  return s >= 80 ? 'stroke-emerald-500' : s >= 60 ? 'stroke-amber-500' : 'stroke-rose-500'
}
function scoreBg(s: number): string {
  return s >= 80 ? 'bg-emerald-500' : s >= 60 ? 'bg-amber-500' : 'bg-rose-500'
}
function scoreBgLight(s: number): string {
  return s >= 80 ? 'bg-emerald-50' : s >= 60 ? 'bg-amber-50' : 'bg-rose-50'
}

function metricCategory(name: string): string {
  if (name.includes('latency') || name.includes('ttfw') || name.includes('response_gap')) return 'Latency'
  if (name.includes('wer') || name.includes('cer') || name.includes('keyword') || name.includes('hallucination')) return 'Conversation'
  if (name.includes('mos') || name.includes('snr') || name.includes('intelligibility') || name.includes('audio')) return 'Audio Quality'
  if (name.includes('pii') || name.includes('disclosure') || name.includes('compliance') || name.includes('hipaa') || name.includes('pci')) return 'Compliance'
  if (name.includes('silence') || name.includes('turn_gap')) return 'Robustness'
  if (name.includes('interrupt') || name.includes('barge')) return 'Interruption'
  if (name.includes('task') || name.includes('tool') || name.includes('slot')) return 'Task Completion'
  return 'Other'
}

function categoryIcon(name: string): string {
  const icons: Record<string, string> = {
    'Latency': 'M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z',
    'Conversation': 'M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z',
    'Audio Quality': 'M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2z',
    'Compliance': 'M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z',
    'Robustness': 'M13 10V3L4 14h7v7l9-11h-7z',
    'Interruption': 'M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636',
    'Task Completion': 'M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4',
  }
  return icons[name] || 'M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z'
}

const metricDescriptions: Record<string, string> = {
  ai_disclosure: 'Agent must explicitly state it is an AI/virtual assistant in the first turn',
  compliance_score: 'Composite: AI disclosure + PII protection + PCI compliance',
  pii_violations: 'Count of personally identifiable information leaked by agent',
  pci_no_echo: 'Agent must not read back credit card numbers',
  ttfw_ms: 'Time from call connect to agent\'s first word',
  turn_latency_p50_ms: 'Median response time across all turns',
  turn_latency_p95_ms: '95th percentile response time',
  turn_latency_p99_ms: '99th percentile response time (worst case)',
  response_gap_avg_ms: 'Average silence between caller finishing and agent responding',
  silence_pct: 'Percentage of call duration with dead air',
  silence_segments: 'Number of awkward silence gaps (>2 seconds)',
  audio_quality_estimate: 'Mean Opinion Score estimate (1=bad, 5=excellent)',
  intelligibility_estimate: 'Speech clarity from SNR + spectral analysis + STT confidence',
  turn_gap_avg_ms: 'Average gap between conversation turns',
  hallucination_rate: 'Percentage of agent claims not grounded in conversation context',
  task_completion: 'LLM judge assessment: did the agent achieve the caller\'s goal?',
  tool_call_correctness: 'Were the right tools called with correct parameters?',
  slot_extraction_accuracy: 'Were key data points (name, date, etc.) correctly extracted?',
}

function metricDesc(name: string): string {
  if (name.startsWith('keyword_presence_t')) return `Required phrases present in agent turn ${name.slice(-1)}`
  if (name.startsWith('keyword_absence_t')) return `Forbidden phrases absent from agent turn ${name.slice(-1)}`
  return metricDescriptions[name] || name.replace(/_/g, ' ')
}

function formatMetricValue(m: MetricResult): string {
  if (m.unit === '%') return `${m.value.toFixed(1)}%`
  if (m.unit === '/5.0') return `${m.value.toFixed(2)}/5`
  if (m.unit === 'ms') return `${m.value.toFixed(0)}ms`
  if (m.unit === 'count') return `${m.value}`
  return m.value.toFixed(2)
}

function metricDetailText(m: MetricResult): string {
  const d = m.details || {}
  // For semantic metrics with judge reasoning, show a short version (first sentence)
  if (d.judge_reasoning && typeof d.judge_reasoning === 'string') {
    const reasoning = d.judge_reasoning as string
    const firstSentence = reasoning.split(/[.!]\s/)[0]
    return firstSentence.length > 120 ? firstSentence.slice(0, 117) + '...' : firstSentence + '.'
  }
  if (m.name === 'ai_disclosure') return d.disclosed_within_first_turn ? 'Disclosed in first turn' : 'Agent never identified itself as AI'
  if (m.name === 'hallucination_rate') return `Grounding score: ${d.grounding_score ?? 'N/A'}% — ${m.value === 0 ? 'all claims verified against context' : 'ungrounded claims detected'}`
  if (m.name === 'task_completion') return m.value === 0 ? 'Agent did not complete the scenario goal' : `${m.value.toFixed(0)}% of goal criteria met`
  if (m.name.startsWith('keyword_presence')) {
    const missing = (d.missing as string[]) || []
    return missing.length > 0 ? `Missing: "${missing.join('", "')}"` : 'All keywords found'
  }
  if (m.name === 'audio_quality_estimate') return `${m.value >= 4 ? 'Excellent' : m.value >= 3 ? 'Acceptable' : 'Poor'} audio clarity (${d.scoring_method || 'heuristic'})`
  if (m.name === 'intelligibility_estimate') return `SNR: ${((d.snr_score as number) ?? 0) * 100}% · Spectral: ${((d.spectral_clarity as number) ?? 0) * 100}% · STT: ${((d.stt_confidence as number) ?? 0) * 100}%`
  if (m.name === 'tool_call_correctness') return m.value === 0 ? 'No expected tool calls were invoked' : `${m.value.toFixed(0)}% of tool calls correct`
  if (m.name === 'slot_extraction_accuracy') return m.value === 0 ? 'Key data points not extracted from conversation' : `${m.value.toFixed(0)}% of slots correctly filled`
  if (m.name === 'silence_pct') return m.value === 0 ? 'No dead air detected' : `${m.value.toFixed(1)}% of call was silence`
  if (m.name === 'turn_gap_avg_ms') {
    const gaps = (d.gaps as number[]) || []
    const max = (d.max_gap_ms as number) || 0
    return gaps.length > 0 ? `${gaps.length} turns, longest gap: ${max.toFixed(0)}ms` : ''
  }
  return ''
}

// Get metrics with judge reasoning from a scenario's metrics
function getJudgeMetrics(metrics: Record<string, MetricResult>): MetricResult[] {
  return Object.values(metrics).filter(m => m.details?.judge_reasoning)
}

// Get the first judge reasoning found across all scenarios for a given metric name
function getJudgeReasoning(metricName: string): string {
  if (!data.value) return ''
  for (const er of data.value.results) {
    const m = er.metrics[metricName]
    if (m?.details?.judge_reasoning) return m.details.judge_reasoning as string
  }
  return ''
}

function judgeScoreLabel(value: number): string {
  if (value >= 90) return 'Excellent'
  if (value >= 75) return 'Good'
  if (value >= 50) return 'Fair'
  if (value >= 25) return 'Poor'
  return 'Failed'
}

function judgeScorePillClass(value: number): string {
  if (value >= 75) return 'bg-emerald-100 text-emerald-700'
  if (value >= 50) return 'bg-amber-100 text-amber-700'
  return 'bg-rose-100 text-rose-700'
}

function getMetricsSorted(metrics: Record<string, MetricResult>): MetricResult[] {
  const vals = Object.values(metrics)
  return [...vals.filter(m => !m.passed), ...vals.filter(m => m.passed)]
}

function getAgentText(er: EvalResult): string {
  if (!er.transcript || er.transcript.length === 0) return ''
  const agent = er.transcript.find(t => (t as Record<string, unknown>).role === 'agent')
  const text = (agent as Record<string, unknown>)?.text ?? (er.transcript[0] as Record<string, unknown>)?.text
  return typeof text === 'string' ? text : ''
}
</script>

<template>
  <section class="space-y-5">
    <RouterLink to="/runs" class="inline-flex items-center gap-1.5 text-sm font-medium text-ink-400 transition-colors hover:text-ink-700">
      <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M15 18l-6-6 6-6" /></svg>
      All Runs
    </RouterLink>

    <div v-if="isLoading" class="card p-12 text-center"><Spinner label="Loading run..." /></div>
    <ErrorBox v-else-if="error" :error="error" />

    <div v-else-if="data" class="space-y-5">

      <!-- ═══ 1. HERO ═══ -->
      <div class="card-dark p-6 sm:p-8">
        <div class="flex flex-col sm:flex-row items-center gap-8">
          <div class="relative flex-shrink-0">
            <svg class="score-ring" viewBox="0 0 140 140" :style="{ '--score': data.decibench_score }">
              <circle class="track" cx="70" cy="70" r="65" />
              <circle class="progress" :class="scoreStroke(data.decibench_score)" cx="70" cy="70" r="65" />
            </svg>
            <div class="absolute inset-0 flex flex-col items-center justify-center">
              <span class="text-3xl font-bold text-white">{{ formatScore(data.decibench_score) }}</span>
              <span class="text-[10px] text-ink-500 font-medium uppercase tracking-wider">score</span>
            </div>
          </div>
          <div class="flex-1 text-center sm:text-left">
            <div class="flex items-center gap-2 justify-center sm:justify-start flex-wrap">
              <h1 class="text-xl font-bold text-white">{{ data.suite }}</h1>
              <span class="text-ink-500">&rarr;</span>
              <span class="text-sm text-ink-400 truncate max-w-xs">{{ data.target }}</span>
              <span
                class="rounded-full px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider"
                :class="isSemantic ? 'bg-violet-500/20 text-violet-300 ring-1 ring-violet-400/30' : 'bg-amber-500/20 text-amber-300 ring-1 ring-amber-400/30'"
              >
                {{ isSemantic ? `Semantic · ${data.judge_model}` : 'Deterministic' }}
              </span>
            </div>
            <div class="mt-2">
              <span class="text-sm font-semibold" :class="scoreGrade.color">{{ scoreGrade.label }}</span>
              <span class="text-sm text-ink-400 ml-1">{{ scoreGrade.desc }}</span>
              <div v-if="isSemantic" class="mt-1 text-xs text-violet-300/80">
                Evaluated by {{ data.judge_model }} — full AI reasoning below
              </div>
            </div>
            <div class="mt-4 grid grid-cols-3 gap-6">
              <div>
                <div class="text-[10px] text-ink-500 uppercase tracking-wider">Scenarios</div>
                <div class="mt-1 text-lg font-semibold text-white">{{ data.total_scenarios }}</div>
              </div>
              <div>
                <div class="text-[10px] text-ink-500 uppercase tracking-wider">Pass Rate</div>
                <div class="mt-1 text-lg font-semibold" :class="passRate >= 80 ? 'text-emerald-400' : passRate >= 50 ? 'text-amber-400' : 'text-rose-400'">{{ passRate }}%</div>
              </div>
              <div>
                <div class="text-[10px] text-ink-500 uppercase tracking-wider">Duration</div>
                <div class="mt-1 text-lg font-semibold text-white">{{ formatDuration(data.duration_seconds * 1000) }}</div>
              </div>
            </div>
            <div class="mt-3 flex items-center gap-2 flex-wrap justify-center sm:justify-start">
              <span class="pill-pass">{{ data.passed }} passed</span>
              <span v-if="data.failed > 0" class="pill-fail">{{ data.failed }} failed</span>
              <span class="text-xs text-ink-500 ml-1">{{ formatTimestamp(data.timestamp) }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- ═══ 2. EXECUTIVE INSIGHT ═══ -->
      <div class="card p-5 border-l-4 border-l-ink-900">
        <div class="flex items-start gap-3">
          <div class="grid h-8 w-8 flex-shrink-0 place-items-center rounded-lg bg-ink-900">
            <svg class="h-4 w-4 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M2 3h6a4 4 0 014 4v14a3 3 0 00-3-3H2z" /><path d="M22 3h-6a4 4 0 00-4 4v14a3 3 0 013-3h7z" />
            </svg>
          </div>
          <div class="flex-1">
            <h2 class="text-sm font-semibold text-ink-900">Analysis Summary</h2>
            <p class="mt-1.5 text-sm text-ink-600 leading-relaxed">{{ executiveInsight.summary }}</p>
            <div v-if="executiveInsight.details.length > 0" class="mt-3 space-y-2">
              <div
                v-for="(detail, i) in executiveInsight.details"
                :key="i"
                class="text-xs text-ink-500 leading-relaxed pl-3 border-l-2 border-ink-200"
              >
                {{ detail }}
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- ═══ 3. FIX THESE FIRST ═══ -->
      <div v-if="fixActions.length > 0">
        <h2 class="text-sm font-semibold text-ink-700 uppercase tracking-wide mb-3">Fix These First</h2>
        <div class="space-y-2">
          <div
            v-for="(action, i) in fixActions"
            :key="action.title"
            class="card overflow-hidden"
          >
            <div class="flex items-stretch">
              <!-- Priority number -->
              <div
                class="flex w-12 flex-shrink-0 items-center justify-center text-lg font-bold text-white"
                :class="action.severity === 'critical' ? 'bg-rose-500' : action.severity === 'high' ? 'bg-amber-500' : 'bg-ink-400'"
              >
                {{ i + 1 }}
              </div>
              <div class="flex-1 px-4 py-3">
                <div class="flex items-center gap-2 flex-wrap">
                  <span class="text-sm font-semibold text-ink-900">{{ action.title }}</span>
                  <span
                    class="rounded-full px-2 py-0.5 text-[10px] font-bold uppercase"
                    :class="action.severity === 'critical' ? 'bg-rose-100 text-rose-700' : action.severity === 'high' ? 'bg-amber-100 text-amber-700' : 'bg-ink-100 text-ink-600'"
                  >
                    {{ action.impact }}
                  </span>
                </div>
                <p class="mt-1 text-xs text-ink-500 leading-relaxed">{{ action.description }}</p>
              </div>
              <!-- Impact bar -->
              <div class="flex w-20 flex-shrink-0 flex-col items-center justify-center border-l border-ink-100 bg-ink-50/50">
                <span class="text-lg font-bold" :class="action.failRate >= 0.8 ? 'text-rose-600' : 'text-amber-600'">{{ Math.round(action.failRate * 100) }}%</span>
                <span class="text-[9px] text-ink-400 uppercase">fail rate</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- ═══ 4. STRENGTHS & WEAKNESSES ═══ -->
      <div class="grid gap-4 sm:grid-cols-2">
        <!-- Strengths -->
        <div class="card p-5">
          <h3 class="flex items-center gap-2 text-sm font-semibold text-emerald-700 mb-3">
            <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 11-5.93-9.14" /><path d="M22 4L12 14.01l-3-3" /></svg>
            Strengths
          </h3>
          <div v-if="strengths.length === 0" class="text-xs text-ink-400">No categories above 80% pass rate.</div>
          <div v-else class="space-y-2.5">
            <div v-for="cat in strengths" :key="cat.name" class="flex items-center gap-3">
              <div class="grid h-7 w-7 place-items-center rounded-md bg-emerald-50">
                <svg class="h-3.5 w-3.5 text-emerald-600" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path :d="categoryIcon(cat.name)" /></svg>
              </div>
              <div class="flex-1">
                <div class="flex items-center justify-between">
                  <span class="text-xs font-medium text-ink-700">{{ cat.name }}</span>
                  <span class="text-xs font-bold text-emerald-600">{{ cat.passRate }}%</span>
                </div>
                <div class="mt-1 h-1.5 rounded-full bg-emerald-100">
                  <div class="h-full rounded-full bg-emerald-500" :style="{ width: `${cat.passRate}%` }"></div>
                </div>
              </div>
              <span v-if="cat.hasJudge" class="rounded bg-violet-100 px-1 py-0.5 text-[9px] font-bold text-violet-600">AI</span>
            </div>
          </div>
        </div>

        <!-- Weaknesses -->
        <div class="card p-5">
          <h3 class="flex items-center gap-2 text-sm font-semibold text-rose-700 mb-3">
            <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" /><line x1="12" y1="9" x2="12" y2="13" /><line x1="12" y1="17" x2="12.01" y2="17" /></svg>
            Weaknesses
          </h3>
          <div v-if="weaknesses.length === 0" class="text-xs text-ink-400">All categories above 80%!</div>
          <div v-else class="space-y-2.5">
            <div v-for="cat in weaknesses" :key="cat.name" class="flex items-center gap-3">
              <div class="grid h-7 w-7 place-items-center rounded-md" :class="scoreBgLight(cat.passRate)">
                <svg class="h-3.5 w-3.5" :class="scoreColor(cat.passRate)" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path :d="categoryIcon(cat.name)" /></svg>
              </div>
              <div class="flex-1">
                <div class="flex items-center justify-between">
                  <span class="text-xs font-medium text-ink-700">{{ cat.name }}</span>
                  <span class="text-xs font-bold" :class="scoreColor(cat.passRate)">{{ cat.passRate }}%</span>
                </div>
                <div class="mt-1 h-1.5 rounded-full bg-ink-100">
                  <div class="h-full rounded-full" :class="scoreBg(cat.passRate)" :style="{ width: `${cat.passRate}%` }"></div>
                </div>
              </div>
              <span v-if="cat.hasJudge" class="rounded bg-violet-100 px-1 py-0.5 text-[9px] font-bold text-violet-600">AI</span>
            </div>
          </div>
        </div>
      </div>

      <!-- ═══ 5. SCENARIO DEEP DIVE ═══ -->
      <div>
        <div class="flex items-center justify-between mb-3">
          <h2 class="text-sm font-semibold text-ink-700 uppercase tracking-wide">Scenario Deep Dive</h2>
          <button
            class="text-xs text-ink-400 hover:text-ink-700 transition-colors"
            @click="expandedScenarios.size === data.results.length ? expandedScenarios.clear() : data.results.forEach(r => expandedScenarios.add(r.scenario_id))"
          >
            {{ expandedScenarios.size === data.results.length ? 'Collapse all' : 'Expand all' }}
          </button>
        </div>

        <div class="space-y-2">
          <div
            v-for="er in data.results"
            :key="er.scenario_id"
            class="card overflow-hidden"
            :class="er.passed ? 'border-l-4 border-l-emerald-400' : 'border-l-4 border-l-rose-400'"
          >
            <!-- Header row -->
            <div class="flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-ink-50/50 transition-colors" @click="toggleScenario(er.scenario_id)">
              <svg
                class="h-4 w-4 flex-shrink-0 text-ink-400 transition-transform duration-200"
                :class="expandedScenarios.has(er.scenario_id) ? 'rotate-90' : ''"
                viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"
              ><path d="M9 18l6-6-6-6" /></svg>

              <span class="font-mono text-xs text-ink-700 flex-1 min-w-0 truncate">{{ er.scenario_id }}</span>

              <span v-if="er.passed" class="inline-flex items-center gap-1 text-emerald-600 text-xs font-medium">
                <svg class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M20 6L9 17l-5-5" /></svg>
                Pass
              </span>
              <span v-else class="inline-flex items-center gap-1 text-rose-600 text-xs font-medium">
                <svg class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M18 6L6 18M6 6l12 12" /></svg>
                Fail
              </span>

              <span class="text-sm font-bold w-10 text-right" :class="scoreColor(er.score)">{{ formatScore(er.score) }}</span>

              <div class="hidden md:flex items-center gap-1 max-w-xs">
                <span v-for="cat in er.failure_summary.slice(0, 3)" :key="cat" class="pill-fail text-[10px]">{{ cat }}</span>
              </div>

              <span class="text-xs text-ink-400 w-14 text-right">{{ formatDuration(er.duration_ms) }}</span>
            </div>

            <!-- Expanded detail -->
            <div v-if="expandedScenarios.has(er.scenario_id)" class="border-t border-ink-100">

              <!-- Agent response -->
              <div v-if="getAgentText(er)" class="px-5 py-3 bg-ink-50/50 border-b border-ink-100">
                <div class="text-[10px] font-semibold uppercase tracking-wider text-ink-400 mb-1">Agent Said</div>
                <p class="text-sm text-ink-700 leading-relaxed">"{{ getAgentText(er) }}"</p>
              </div>

              <!-- AI Judge Analysis (semantic only) -->
              <div v-if="isSemantic && getJudgeMetrics(er.metrics).length > 0" class="px-5 py-4 border-b border-ink-100">
                <div class="card-ai-judge p-5">
                  <div class="flex items-center justify-between mb-4">
                    <div class="flex items-center gap-2">
                      <div class="grid h-7 w-7 place-items-center rounded-lg bg-violet-500">
                        <svg class="h-4 w-4 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                          <path d="M12 2a4 4 0 014 4c0 1.95-2 3-2 8h-4c0-5-2-6.05-2-8a4 4 0 014-4z" />
                          <path d="M10 14h4" /><path d="M10 18h4" /><path d="M11 22h2" />
                        </svg>
                      </div>
                      <span class="text-sm font-semibold text-violet-900">AI Judge Analysis</span>
                    </div>
                    <span class="pill-ai text-[10px]">{{ data!.judge_model }}</span>
                  </div>

                  <div class="space-y-3">
                    <div
                      v-for="jm in getJudgeMetrics(er.metrics)"
                      :key="jm.name"
                      class="judge-reasoning-block"
                    >
                      <div class="flex items-center justify-between mb-2">
                        <span class="text-xs font-semibold text-violet-800 uppercase tracking-wide">
                          {{ jm.name.replace(/_/g, ' ') }}
                        </span>
                        <div class="flex items-center gap-2">
                          <span
                            class="rounded-full px-2 py-0.5 text-[10px] font-bold"
                            :class="judgeScorePillClass(jm.value)"
                          >
                            {{ jm.value.toFixed(0) }}/100 — {{ judgeScoreLabel(jm.value) }}
                          </span>
                          <span v-if="jm.passed" class="text-emerald-500">
                            <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M20 6L9 17l-5-5" /></svg>
                          </span>
                          <span v-else class="text-rose-500">
                            <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M18 6L6 18M6 6l12 12" /></svg>
                          </span>
                        </div>
                      </div>
                      <p class="text-sm text-ink-700 leading-relaxed whitespace-pre-line">{{ jm.details?.judge_reasoning }}</p>
                    </div>
                  </div>
                </div>
              </div>

              <!-- Metrics organized by category -->
              <div class="px-5 py-4">
                <!-- Failed metrics first with full explanation -->
                <div v-if="getMetricsSorted(er.metrics).some(m => !m.passed)" class="mb-4">
                  <div class="text-[10px] font-semibold uppercase tracking-wider text-rose-500 mb-2">Failed Checks</div>
                  <div class="space-y-2">
                    <div
                      v-for="m in getMetricsSorted(er.metrics).filter(m => !m.passed)"
                      :key="m.name"
                      class="rounded-lg bg-rose-50 border border-rose-200 px-4 py-3"
                    >
                      <div class="flex items-center justify-between">
                        <div class="flex items-center gap-2">
                          <svg class="h-4 w-4 text-rose-500 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M18 6L6 18M6 6l12 12" /></svg>
                          <span class="text-sm font-medium text-rose-800">{{ m.name.replace(/_/g, ' ') }}</span>
                          <span v-if="isSemanticMetric(m.name)" class="rounded bg-violet-100 px-1 py-0.5 text-[9px] font-bold text-violet-600">AI Judge</span>
                        </div>
                        <div class="text-right">
                          <span class="text-sm font-bold text-rose-600">{{ formatMetricValue(m) }}</span>
                          <span v-if="m.threshold != null" class="text-[10px] text-rose-400 ml-1">/ {{ m.unit === '%' ? `${m.threshold}%` : m.unit === 'ms' ? `${m.threshold}ms` : m.threshold }}</span>
                        </div>
                      </div>
                      <p class="mt-1 text-xs text-rose-600/80">{{ metricDesc(m.name) }}</p>
                      <p v-if="metricDetailText(m)" class="mt-1 text-xs text-rose-700 font-medium">{{ metricDetailText(m) }}</p>
                    </div>
                  </div>
                </div>

                <!-- Passed metrics compact -->
                <div>
                  <div class="text-[10px] font-semibold uppercase tracking-wider text-emerald-600 mb-2">Passed Checks</div>
                  <div class="grid gap-1.5 sm:grid-cols-2 lg:grid-cols-3">
                    <div
                      v-for="m in getMetricsSorted(er.metrics).filter(m => m.passed)"
                      :key="m.name"
                      class="flex items-center gap-2 rounded-md bg-white border border-ink-100 px-3 py-2"
                    >
                      <svg class="h-3.5 w-3.5 text-emerald-500 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M20 6L9 17l-5-5" /></svg>
                      <div class="flex-1 min-w-0">
                        <div class="flex items-center justify-between gap-1">
                          <span class="text-[11px] text-ink-600 truncate">{{ m.name.replace(/_/g, ' ') }}</span>
                          <span class="text-[11px] font-semibold text-emerald-600 flex-shrink-0">{{ formatMetricValue(m) }}</span>
                        </div>
                        <div v-if="metricDetailText(m)" class="text-[10px] text-ink-400 truncate mt-0.5">{{ metricDetailText(m) }}</div>
                      </div>
                      <span v-if="isSemanticMetric(m.name)" class="rounded bg-violet-100 px-1 py-0.5 text-[9px] font-bold text-violet-600">AI</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- ═══ 6. DETERMINISTIC-ONLY NOTE ═══ -->
      <div v-if="!isSemantic" class="card px-5 py-4 border-l-4 border-l-amber-400 bg-amber-50/30">
        <div class="flex items-start gap-3">
          <svg class="h-5 w-5 text-amber-600 flex-shrink-0 mt-0.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          <div>
            <div class="text-sm font-semibold text-amber-800">Running without LLM judge</div>
            <p class="mt-0.5 text-xs text-amber-700">
              Hallucination detection and semantic task completion are unavailable. Re-run with:
            </p>
            <code class="mt-1.5 inline-block rounded bg-amber-100 px-2 py-1 text-xs text-amber-900 font-mono">
              decibench run --mode semantic --suite {{ data.suite }}
            </code>
          </div>
        </div>
      </div>

    </div>
  </section>
</template>
