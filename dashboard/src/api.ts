// Typed API client + TanStack Query hooks against the Decibench FastAPI app.
//
// Every call returns plain JSON typed by what the backend exposes. We keep the
// types co-located here (rather than auto-generated) because the API surface
// is small and the dashboard wants to be readable end-to-end.

import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import type { MaybeRefOrGetter } from 'vue'
import { computed, toValue } from 'vue'

// ----------------------------------------------------------------- shared types

export interface RunSummary {
  id: string
  suite: string
  target: string
  score: number
  passed: number
  failed: number
  total_scenarios: number
  timestamp: string
  evaluation_mode?: string
  judge_provider?: string
  judge_model?: string
}

export interface MetricResult {
  name: string
  value: number
  unit: string
  passed: boolean
  threshold?: number | null
  details?: Record<string, unknown>
}

export interface EvalResult {
  scenario_id: string
  passed: boolean
  score: number
  metrics: Record<string, MetricResult>
  failures: string[]
  failure_summary: string[]
  latency: Record<string, number>
  cost: Record<string, number>
  duration_ms: number
  transcript: Array<Record<string, unknown>>
  spans: Array<{
    name: string
    start_ms: number
    end_ms: number
    duration_ms: number
    turn_index: number | null
  }>
}

export interface SuiteResult {
  suite: string
  target: string
  decibench_score: number
  score_breakdown?: Record<string, number>
  total_scenarios: number
  passed: number
  failed: number
  results: EvalResult[]
  timestamp: string
  duration_seconds: number
  evaluation_mode?: string
  judge_provider?: string
  judge_model?: string
}

export interface TranscriptSegment {
  role: 'caller' | 'agent'
  text: string
  start_ms: number
  end_ms: number
  confidence: number
}

export interface CallTrace {
  id: string
  source: string
  target: string
  started_at: string
  duration_ms: number
  transcript: TranscriptSegment[]
  events: Array<{ type: string; timestamp_ms: number; data: Record<string, unknown> }>
  spans: Array<{
    name: string
    start_ms: number
    end_ms: number
    duration_ms: number
    turn_index: number | null
  }>
  metadata: Record<string, unknown>
  imported_at: string
}

export interface CallTimeline {
  call_id: string
  duration_ms: number
  spans: Array<{
    name: string
    start_ms: number
    end_ms: number
    duration_ms: number
    turn_index: number | null
  }>
  turns: TranscriptSegment[]
  event_kinds: Record<string, number>
}

export interface CallEvaluationSummary {
  id: string
  call_id: string
  source: string
  scenario_id: string
  score: number
  passed: boolean
  evaluated_at: string
  failure_summary: string[]
}

export interface FailureInboxStats {
  total_evaluations: number
  failed: number
  passed: number
  sources: Record<string, number>
  categories: Record<string, number>
  score: { avg: number; min: number; max: number }
}

export interface RegressionScenario {
  call_id: string
  scenario_id: string
  yaml: string
}

// -------------------------------------------------------------------- transport

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: { Accept: 'application/json', ...(init?.headers ?? {}) },
    ...init,
  })
  if (!response.ok) {
    let detail = response.statusText
    try {
      const body = (await response.json()) as { detail?: string }
      if (body.detail) detail = body.detail
    } catch {
      // Non-JSON body — leave the statusText as the message.
    }
    throw new Error(`${response.status} ${detail}`)
  }
  return (await response.json()) as T
}

// ---------------------------------------------------------------------- hooks

export interface FailureInboxFilters {
  failed_only?: boolean
  source?: string | null
  category?: string | null
  max_score?: number | null
  q?: string | null
  limit?: number
}

export function useFailureInbox(filters: MaybeRefOrGetter<FailureInboxFilters>) {
  const params = computed(() => {
    const f = toValue(filters)
    const search = new URLSearchParams()
    if (f.failed_only) search.set('failed_only', 'true')
    if (f.source) search.set('source', f.source)
    if (f.category) search.set('category', f.category)
    if (f.max_score != null) search.set('max_score', String(f.max_score))
    if (f.q) search.set('q', f.q)
    search.set('limit', String(f.limit ?? 100))
    return search.toString()
  })
  return useQuery({
    queryKey: ['call-evaluations', params],
    queryFn: () => api<CallEvaluationSummary[]>(`/call-evaluations?${params.value}`),
  })
}

export function useFailureStats() {
  return useQuery({
    queryKey: ['failure-inbox-stats'],
    queryFn: () => api<FailureInboxStats>('/failure-inbox/stats'),
  })
}

export function useCallTrace(callId: MaybeRefOrGetter<string>) {
  return useQuery({
    queryKey: ['call', () => toValue(callId)],
    queryFn: () => api<CallTrace>(`/calls/${encodeURIComponent(toValue(callId))}`),
  })
}

export function useCallTimeline(callId: MaybeRefOrGetter<string>) {
  return useQuery({
    queryKey: ['call-timeline', () => toValue(callId)],
    queryFn: () =>
      api<CallTimeline>(`/calls/${encodeURIComponent(toValue(callId))}/timeline`),
  })
}

export function useCallLatestEvaluation(callId: MaybeRefOrGetter<string>) {
  return useQuery({
    queryKey: ['call-latest-evaluation', () => toValue(callId)],
    queryFn: async () => {
      const id = encodeURIComponent(toValue(callId))
      const res = await fetch(`/calls/${id}/evaluation`)
      if (res.status === 404) return null
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
      return (await res.json()) as EvalResult
    },
  })
}

export function useStoredEvaluation(evaluationId: MaybeRefOrGetter<string>) {
  return useQuery({
    queryKey: ['evaluation', () => toValue(evaluationId)],
    queryFn: () =>
      api<EvalResult>(`/call-evaluations/${encodeURIComponent(toValue(evaluationId))}`),
  })
}

export function useRuns() {
  return useQuery({
    queryKey: ['runs'],
    queryFn: () => api<RunSummary[]>('/runs?limit=100'),
  })
}

export function useRun(runId: MaybeRefOrGetter<string>) {
  return useQuery({
    queryKey: ['run', () => toValue(runId)],
    queryFn: () => api<SuiteResult>(`/runs/${encodeURIComponent(toValue(runId))}`),
  })
}

export function useEvaluateCall() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (callId: string) =>
      api<EvalResult>(`/calls/${encodeURIComponent(callId)}/evaluate`),
    onSuccess: (_data, callId) => {
      queryClient.invalidateQueries({ queryKey: ['call-latest-evaluation'] })
      queryClient.invalidateQueries({ queryKey: ['call-evaluations'] })
      queryClient.invalidateQueries({ queryKey: ['failure-inbox-stats'] })
      queryClient.invalidateQueries({ queryKey: ['call', () => callId] })
    },
  })
}

export function useGenerateRegression() {
  return useMutation({
    mutationFn: (callId: string) =>
      api<RegressionScenario>(`/calls/${encodeURIComponent(callId)}/regression`, {
        method: 'POST',
      }),
  })
}

// ---------------------------------------------------------------------- RAG hooks

export interface RagDocument {
  id: string
  title: string
  chunk_count: number
  bytes: number
  embedding_provider: string
  ingested_at: string
}

export interface RagStats {
  store_path: string
  documents: number
  chunks: number
  bytes: number
  providers: string[]
}

export interface RagSearchResult {
  score: number
  text: string
  section_path: string[]
  document_id: string
  chunk_id: string
}

export function useRagDocuments() {
  return useQuery({
    queryKey: ['rag-documents'],
    queryFn: () => api<RagDocument[]>('/rag/documents'),
  })
}

export function useRagStats() {
  return useQuery({
    queryKey: ['rag-stats'],
    queryFn: () => api<RagStats>('/rag/stats'),
  })
}

export function useIngestText() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: { text: string; title: string; cloud_confirm?: boolean }) =>
      api<any>('/rag/ingest-text', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rag-documents'] })
      queryClient.invalidateQueries({ queryKey: ['rag-stats'] })
    },
  })
}

export function useIngestFiles() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: { files: File[]; cloud_confirm?: boolean }) => {
      const formData = new FormData()
      data.files.forEach(f => formData.append('files', f))
      if (data.cloud_confirm) formData.append('cloud_confirm', 'true')
      
      // We cannot use the `api` wrapper directly because fetch handles FormData Content-Type boundary automatically
      // when headers['Content-Type'] is NOT set. Our api wrapper sets Accept but doesn't force Content-Type.
      return api<any>('/rag/ingest-files', {
        method: 'POST',
        body: formData,
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rag-documents'] })
      queryClient.invalidateQueries({ queryKey: ['rag-stats'] })
    },
  })
}

export function useRagSearch(query: MaybeRefOrGetter<string>) {
  return useQuery({
    queryKey: ['rag-search', () => toValue(query)],
    queryFn: () => {
      const q = encodeURIComponent(toValue(query))
      return q ? api<RagSearchResult[]>(`/rag/search?query=${q}`) : Promise.resolve([])
    },
    enabled: () => !!toValue(query),
  })
}

export function useRemoveDocument() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (documentId: string) =>
      api<any>(`/rag/documents/${encodeURIComponent(documentId)}`, { method: 'DELETE' }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rag-documents'] })
      queryClient.invalidateQueries({ queryKey: ['rag-stats'] })
    },
  })
}

export function useStartRun() {
  return useMutation({
    mutationFn: (data: { target: string; suite: string; mode: string; parallel?: number }) =>
      api<{ task_id: string; stream_url: string; status: string }>('/runs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      }),
  })
}

export function useRagSynthesize() {
  return useMutation({
    mutationFn: (data: { topics: string[]; suite: string }) =>
      api<any>('/rag/synthesize', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      }),
  })
}
