import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import type { ApiSource, AuditLog, Batch, PipelineRun, PlanSummary, ProcessorManifest, ReviewItem, Source, Workflow } from '../types'

export function useWorkspace() {
  const [sources, setSources] = useState<Source[]>([])
  const [apiSources, setApiSources] = useState<ApiSource[]>([])
  const [workflows, setWorkflows] = useState<Workflow[]>([])
  const [processors, setProcessors] = useState<ProcessorManifest[]>([])
  const [runs, setRuns] = useState<PipelineRun[]>([])
  const [reviews, setReviews] = useState<ReviewItem[]>([])
  const [plans, setPlans] = useState<PlanSummary[]>([])
  const [batches, setBatches] = useState<Batch[]>([])
  const [history, setHistory] = useState<AuditLog[]>([])
  const [state, setState] = useState<'loading'|'live'|'offline'>('loading')
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    setState('loading'); setError(null)
    try {
      const [, sourceRows, workflowRows, processorRows, runRows, reviewRows, planRows, batchRows, auditRows] = await Promise.all([
        api.health(), api.sources(), api.workflows(), api.processors(), api.pipelineRuns(), api.reviews(), api.plans(), api.batches(), api.history(),
      ])
      setApiSources(sourceRows)
      setSources(sourceRows.map(source => ({ id: source.id, name: source.name, path: source.root_path, status: source.enabled ? 'ready' : 'offline', files: 0, size: source.read_only ? 'Read only' : 'Writable', lastScan: 'Indexed locally' })))
      setWorkflows(workflowRows); setProcessors(processorRows); setRuns(runRows); setReviews(reviewRows); setPlans(planRows); setBatches(batchRows); setHistory(auditRows); setState('live')
    } catch (cause) {
      setState('offline'); setError(cause instanceof Error ? cause.message : 'api.unavailable')
    }
  }, [])

  useEffect(() => { void refresh() }, [refresh])
  return { sources, apiSources, workflows, processors, runs, reviews, plans, batches, history, state, error, refresh }
}
