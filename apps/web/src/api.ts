import type { ApiSource, AuditLog, Backup, Batch, Diagnostics, FileGroup, FilePage, Health, JunkRulePack, JunkRulePackValidation, PipelineRun, PlanSummary, Preflight, ProcessorConfig, ProcessorManifest, ReviewDecision, ReviewItem, RollbackPreview, RuleCard, Schedule, StageResult, TemplateValidation, Workflow, WorkflowCompare, WorkflowDiagnostics, WorkflowImpact, WorkflowPortable, WorkflowRevision, WorkflowSimulation, WorkflowTemplateV2 } from './types'

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
  junkRulePacks: () => request<JunkRulePack[]>('/junk-rule-packs'),
  validateJunkRulePack: (pack: unknown) => post<JunkRulePackValidation>('/junk-rule-packs/validate', pack),
  workflowTemplates: () => request<WorkflowTemplateV2[]>('/workflow-templates'),
  validateTemplate: (content: string, format: 'auto'|'yaml'|'json' = 'auto') => post<TemplateValidation>('/workflow-templates/validate', { content, format }),
  importTemplate: (content: string, format: 'auto'|'yaml'|'json' = 'auto') => post<Workflow>('/workflow-templates/import', { content, format }),
  updateTemplate: (id: string, template: WorkflowTemplateV2) => request<Workflow>(`/workflow-templates/${id}`, { method: 'PUT', body: JSON.stringify({ template }) }),
  exportTemplate: async (id: string, format: 'yaml'|'json') => { const response=await fetch(`${apiBase}/workflow-templates/${id}/export?format=${format}`); if(!response.ok)throw new Error(`template.export_http_${response.status}`); return response.text() },
  testRule: (id: string, rule: RuleCard, relative_path: string) => post<{matched:boolean;status:string;input:Record<string,unknown>;output:Record<string,unknown>;reasons:string[];warnings:string[]}>(`/workflow-templates/${id}/test-rule`, { rule, relative_path }),
  workflowImpact: (id: string, sourceId: string) => post<WorkflowImpact>(`/workflows/${id}/impact?source_id=${encodeURIComponent(sourceId)}`),
  simulateWorkflow: (template: WorkflowTemplateV2, relative_path: string, size = 0) => post<WorkflowSimulation>('/workflow-templates/simulate', { template, relative_path, size, fields: {} }),
  diagnoseWorkflow: (template: WorkflowTemplateV2) => post<WorkflowDiagnostics>('/workflow-templates/diagnostics', template),
  pipelineRuns: () => request<PipelineRun[]>('/pipeline-runs'),
  reviews: (runId?: string) => request<ReviewItem[]>(`/reviews${runId ? `?run_id=${encodeURIComponent(runId)}` : ''}`),
  plans: () => request<PlanSummary[]>('/plans'),
  batches: () => request<Batch[]>('/batches'),
  history: () => request<AuditLog[]>('/history'),
  schedules: () => request<Schedule[]>('/schedules'),
  backups: () => request<Backup[]>('/backups'),
  diagnostics: () => request<Diagnostics>('/diagnostics'),
  createSource: (payload: { name: string; root_path: string; read_only: boolean }) => post<ApiSource>('/sources', { ...payload, exclusions: [], protected_paths: [] }),
  createScan: (sourceId: string, hashContents = false, inspectSmallText = false) => post<{ id: string; status: string }>('/scans', { source_id: sourceId, mode: 'full', hash_contents: hashContents, inspect_small_text: inspectSmallText }),
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
  preflight: (id: string) => request<Preflight>(`/plans/${id}/preflight`),
  createBatch: (planId: string) => post<Batch>(`/batches?plan_id=${encodeURIComponent(planId)}`),
  batchAction: (id: string, action: 'pause'|'cancel'|'retry'|'rollback') => post<Batch>(`/batches/${id}/${action}`),
  rollbackPreview: (id: string) => request<RollbackPreview>(`/batches/${id}/rollback-preview`),
  backup: () => post<{ status: string; filename: string }>('/backups'),
  createSchedule: (payload: { name: string; source_id: string; interval_minutes: number; enabled: boolean }) => post<Schedule>('/schedules', payload),
  updateSchedule: (id: string, payload: Partial<Pick<Schedule,'name'|'interval_minutes'|'enabled'>>) => request<Schedule>(`/schedules/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  deleteSchedule: (id: string) => request<void>(`/schedules/${id}`, { method: 'DELETE' }),
  downloadBackup: async (filename: string) => {
    const token = window.localStorage.getItem('file-curator.admin-token')
    const response = await fetch(`${apiBase}/backups/${encodeURIComponent(filename)}`, { headers: token ? { authorization: `Bearer ${token}` } : {} })
    if (!response.ok) throw new Error(`backup.download_http_${response.status}`)
    const url = URL.createObjectURL(await response.blob())
    const anchor = document.createElement('a'); anchor.href = url; anchor.download = filename; anchor.click(); URL.revokeObjectURL(url)
  },
}
