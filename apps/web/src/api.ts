import type { ApiSource, AuditLog, Batch, FileGroup, FilePage, Health, PipelineRun, PlanSummary, ProcessorConfig, ProcessorManifest, ReviewDecision, ReviewItem, StageResult, Workflow, WorkflowCompare, WorkflowPortable, WorkflowRevision } from './types'

declare global { interface Window { __FILE_CURATOR_CONFIG__?: { apiBase?: string } } }

const apiBase = window.__FILE_CURATOR_CONFIG__?.apiBase || new URL('api', document.baseURI).pathname.replace(/\/$/, '')
const appBase = new URL('.', document.baseURI).pathname.replace(/\/$/, '')

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = window.localStorage.getItem('file-curator.admin-token')
  const response = await fetch(`${apiBase}${path}`, {
    ...init,
    headers: { 'content-type': 'application/json', ...(token ? { authorization: `Bearer ${token}` } : {}), ...(init?.headers || {}) },
  })
  if (!response.ok) {
    const body = await response.json().catch(() => ({})) as { detail?: string }
    throw new Error(body.detail || `api.http_${response.status}`)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

const post = <T>(path: string, body?: unknown) => request<T>(path, { method: 'POST', ...(body === undefined ? {} : { body: JSON.stringify(body) }) })

export const api = {
  health: async () => { const response = await fetch(`${appBase}/health/ready`); if (!response.ok) throw new Error(`health.http_${response.status}`); return response.json() as Promise<Health> },
  sources: () => request<ApiSource[]>('/sources'),
  workflows: () => request<Workflow[]>('/workflows'),
  processors: () => request<ProcessorManifest[]>('/processors'),
  pipelineRuns: () => request<PipelineRun[]>('/pipeline-runs'),
  reviews: (runId?: string) => request<ReviewItem[]>(`/reviews${runId ? `?run_id=${encodeURIComponent(runId)}` : ''}`),
  plans: () => request<PlanSummary[]>('/plans'),
  batches: () => request<Batch[]>('/batches'),
  history: () => request<AuditLog[]>('/history'),
  createSource: (payload: { name: string; root_path: string; read_only: boolean }) => post<ApiSource>('/sources', { ...payload, exclusions: [], protected_paths: [] }),
  createScan: (sourceId: string) => post<{ id: string; status: string }>('/scans', { source_id: sourceId, mode: 'full' }),
  files: (params: { sourceId: string; search?: string; extension?: string; limit?: number; offset?: number }) => {
    const query = new URLSearchParams({ source_id: params.sourceId, limit: String(params.limit ?? 100), offset: String(params.offset ?? 0) })
    if (params.search) query.set('search', params.search)
    if (params.extension) query.set('extension', params.extension)
    return request<FilePage>(`/files/page?${query}`)
  },
  fileGroups: (sourceId: string) => request<FileGroup[]>(`/file-groups?source_id=${encodeURIComponent(sourceId)}`),
  createWorkflow: (payload: { name: string; preset: string; review_policy: string; processors: ProcessorConfig[] }) => post<Workflow>('/workflows', payload),
  reviseWorkflow: (id: string, processors: ProcessorConfig[], review_policy: string) => post<Workflow>(`/workflows/${id}/revisions`, { processors, review_policy }),
  workflowRevisions: (id: string) => request<WorkflowRevision[]>(`/workflows/${id}/revisions`),
  exportWorkflow: (id: string) => request<WorkflowPortable>(`/workflows/${id}/export`),
  importWorkflow: (payload: WorkflowPortable) => post<Workflow>('/workflows/import', payload),
  compareWorkflow: (id: string, from: number, to: number) => request<WorkflowCompare>(`/workflows/${id}/compare?from_revision=${from}&to_revision=${to}`),
  runPipeline: (source_id: string, workflow_id: string) => post<PipelineRun>('/pipeline-runs', { source_id, workflow_id }),
  trace: (runId: string) => request<StageResult[]>(`/pipeline-runs/${runId}/trace`),
  decideReview: (runId: string, fileEntryId: string, payload: { action: 'accept'|'keep'|'override'; target_relative_path?: string; note?: string }) => request<ReviewDecision>(`/reviews/${runId}/${fileEntryId}`, { method: 'PUT', body: JSON.stringify(payload) }),
  createPlan: (run_id: string) => post<PlanSummary>('/plans', { run_id }),
  freezePlan: (id: string) => post<PlanSummary>(`/plans/${id}/freeze`),
  confirmPlan: (id: string) => post<PlanSummary>(`/plans/${id}/confirm`),
  createBatch: (planId: string) => post<Batch>(`/batches?plan_id=${encodeURIComponent(planId)}`),
  batchAction: (id: string, action: 'pause'|'cancel'|'retry'|'rollback') => post<Batch>(`/batches/${id}/${action}`),
  backup: () => post<{ status: string; filename: string }>('/backups'),
}
