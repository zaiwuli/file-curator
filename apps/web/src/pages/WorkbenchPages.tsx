import { CheckCircle2, CirclePause, RotateCcw, ShieldCheck } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import type { AuditLog, Batch, PipelineRun, PlanSummary, ProcessorConfig, ProcessorManifest, StageResult, Workflow } from '../types'

type ActionProps = { notify: (message: string) => void; refresh: () => Promise<void> }

function Header({ eyebrow = 'FILE CURATOR', heading, description, actions }: { eyebrow?: string; heading: string; description: string; actions?: React.ReactNode }) {
  return <div className="page-header"><div><div className="eyebrow">{eyebrow}</div><h1>{heading}</h1><p>{description}</p></div><div className="header-actions">{actions}</div></div>
}
function Badge({ value }: { value: string }) {
  const tone = ['completed','confirmed','frozen','matched','high'].includes(value) ? 'green' : ['failed','warning','review','cancelled'].includes(value) ? 'red' : 'blue'
  return <span className={`badge ${tone}`}>{value.replaceAll('_', ' ')}</span>
}
function Empty({ children }: { children: React.ReactNode }) { return <div className="empty-state">{children}</div> }
async function perform(action: () => Promise<unknown>, refresh: () => Promise<void>, notify: (message: string) => void, success: string) {
  try { await action(); await refresh(); notify(success) } catch (cause) { notify(cause instanceof Error ? cause.message : 'api.request_failed') }
}

export function PipelinePage({ sources, workflows, processors, runs, notify, refresh }: ActionProps & { sources: { id: string; name: string }[]; workflows: Workflow[]; processors: ProcessorManifest[]; runs: PipelineRun[] }) {
  const [sourceId, setSourceId] = useState('')
  const [workflowId, setWorkflowId] = useState('')
  const [name, setName] = useState('Rename Only')
  const [preset, setPreset] = useState('rename_only')
  const [policy, setPolicy] = useState('balanced')
  const [configs, setConfigs] = useState<ProcessorConfig[]>([])
  useEffect(() => { if (!sourceId && sources[0]) setSourceId(sources[0].id) }, [sourceId, sources])
  useEffect(() => { if (!workflowId && workflows[0]) setWorkflowId(workflows[0].id) }, [workflowId, workflows])
  useEffect(() => { setConfigs(processors.map(item => ({ id: item.id, enabled: item.default_enabled, options: {} }))) }, [processors])
  const selected = workflows.find(item => item.id === workflowId)
  const toggle = (id: string) => setConfigs(items => items.map(item => item.id === id ? { ...item, enabled: !item.enabled } : item))
  const create = () => perform(async () => { const workflow = await api.createWorkflow({ name, preset, review_policy: policy, processors: configs }); setWorkflowId(workflow.id) }, refresh, notify, 'Workflow created')
  const revise = () => selected && perform(() => api.reviseWorkflow(selected.id, configs, policy), refresh, notify, 'Workflow revision saved')
  const run = () => sourceId && workflowId && perform(() => api.runPipeline(sourceId, workflowId), refresh, notify, 'Virtual processing completed')
  return <><Header eyebrow="DETERMINISTIC PIPELINE" heading="Workflow builder" description="Each enabled processor records its input, output, reasons and decision score." actions={<><button className="button secondary" disabled={!selected} onClick={()=>void revise()}>Save revision</button><button className="button primary" disabled={!sourceId||!workflowId} onClick={()=>void run()}>Run simulation</button></>}/>
    <div className="pipeline-layout"><section className="panel stages-panel"><div className="panel-heading"><div><div className="section-kicker">PROCESSORS</div><h2>Runtime switches</h2></div><Badge value="simulation"/></div>{configs.map(config => { const manifest = processors.find(item => item.id === config.id); return <div className={!config.enabled?'stage-row disabled':'stage-row'} key={config.id}><span className="stage-number">{manifest?.category.slice(0,1).toUpperCase()}</span><div className="stage-copy"><strong>{config.id.replaceAll('_',' ')}</strong><small>v{manifest?.version} · {manifest?.safety_class} · score {manifest?.score_weight}</small></div><button aria-label={`Toggle ${config.id}`} className={`toggle ${config.enabled?'on':''}`} onClick={()=>toggle(config.id)}><span/></button></div>})}</section>
      <aside className="panel processor-panel"><div className="section-kicker">WORKFLOW</div><h2>{selected ? selected.name : 'Create workflow'}</h2><label className="form-label">Name</label><input className="text-input" value={name} onChange={e=>setName(e.target.value)}/><label className="form-label">Preset</label><select className="text-input" value={preset} onChange={e=>setPreset(e.target.value)}><option value="rename_only">Rename Only</option><option value="rename_and_organize">Rename And Organize</option></select><label className="form-label">Review policy</label><select className="text-input" value={policy} onChange={e=>setPolicy(e.target.value)}><option value="conservative">Conservative</option><option value="balanced">Balanced</option><option value="automatic">Automatic</option></select><label className="form-label">Source</label><select className="text-input" value={sourceId} onChange={e=>setSourceId(e.target.value)}>{sources.map(item=><option key={item.id} value={item.id}>{item.name}</option>)}</select><label className="form-label">Existing workflow</label><select className="text-input" value={workflowId} onChange={e=>setWorkflowId(e.target.value)}><option value="">New workflow</option>{workflows.map(item=><option key={item.id} value={item.id}>{item.name} · rev {item.current_revision}</option>)}</select><button className="button secondary" onClick={()=>void create()}>Create as new</button><div className="callout"><ShieldCheck size={15}/><div><strong>Latest run</strong><small>{runs[0] ? `${runs[0].status} · revision ${runs[0].workflow_revision}` : 'No pipeline run yet'}</small></div></div></aside></div></>
}

export function ReviewPage({ reviews, runs }: { reviews: StageResult[]; runs: PipelineRun[] }) {
  const [runId, setRunId] = useState('')
  const [trace, setTrace] = useState<StageResult[]>([])
  const loadTrace = async (id: string) => { setRunId(id); setTrace(id ? await api.trace(id) : []) }
  const rows = trace.length ? trace : reviews
  return <><Header heading="Review center" description="Inspect deterministic evidence. Warning and review results are never hidden." actions={<select className="select" value={runId} onChange={e=>void loadTrace(e.target.value)}><option value="">Review gates only</option>{runs.map(run=><option key={run.id} value={run.id}>Run {run.id.slice(0,8)} · rev {run.workflow_revision}</option>)}</select>}/><section className="panel review-list">{rows.length===0?<Empty>No review items. Run a pipeline or select a trace.</Empty>:rows.map(row=><div className="review-item" key={row.id}><div className="review-symbol"><CheckCircle2 size={16}/></div><div className="review-main"><div><strong>{row.processor_id.replaceAll('_',' ')}</strong><Badge value={row.status}/></div><span>{row.reasons.join(', ') || row.warnings.join(', ') || 'No additional evidence'}</span><code>Score {Math.round(row.confidence*100)}% · file {row.file_entry_id.slice(0,8)}</code><details><summary>Input and output</summary><pre>{JSON.stringify({ input: row.input_data, output: row.output_data }, null, 2)}</pre></details></div></div>)}</section></>
}

export function PreviewPage({ runs, plans, notify, refresh }: ActionProps & { runs: PipelineRun[]; plans: PlanSummary[] }) {
  const [runId,setRunId]=useState(''); const [planId,setPlanId]=useState('')
  useEffect(()=>{if(!runId&&runs[0])setRunId(runs[0].id)},[runId,runs]); useEffect(()=>{if(!planId&&plans[0])setPlanId(plans[0].id)},[planId,plans])
  const plan=plans.find(item=>item.id===planId)
  const create=()=>runId&&perform(async()=>{const next=await api.createPlan(runId);setPlanId(next.id)},refresh,notify,'Draft plan created')
  const freeze=()=>plan&&perform(()=>api.freezePlan(plan.id),refresh,notify,'Plan frozen')
  const confirm=()=>plan&&perform(()=>api.confirmPlan(plan.id),refresh,notify,'Plan confirmed')
  return <><Header heading="Virtual preview" description="This diff comes from SQLite metadata. Real paths are untouched until execution." actions={<><select className="select" value={runId} onChange={e=>setRunId(e.target.value)}><option value="">Select run</option>{runs.map(run=><option key={run.id} value={run.id}>{run.id.slice(0,8)} · {run.status}</option>)}</select><button className="button secondary" disabled={!runId} onClick={()=>void create()}>Create plan</button><button className="button secondary" disabled={!plan||plan.status!=='draft'} onClick={()=>void freeze()}>Freeze</button><button className="button primary" disabled={!plan||plan.status!=='frozen'} onClick={()=>void confirm()}>Confirm</button></>}/><div className="review-toolbar"><select className="select" value={planId} onChange={e=>setPlanId(e.target.value)}><option value="">Select plan</option>{plans.map(item=><option value={item.id} key={item.id}>{item.id.slice(0,8)} · {item.status}</option>)}</select>{plan&&<Badge value={plan.status}/>}</div><section className="panel preview-panel">{!plan?<Empty>Create or select a plan to inspect its virtual paths.</Empty>:<div className="operation-table"><div className="table-head"><span>Original path</span><span>Proposed path</span><span>Operation</span><span>Reason</span></div>{plan.operations.map(operation=><div className="table-row" key={operation.id}><code>{operation.source_relative_path}</code><code>{operation.target_relative_path}</code><Badge value={operation.kind}/><span>{operation.reasons.join(', ')}</span></div>)}</div>}</section></>
}

export function ExecutionPage({ plans, batches, notify, refresh }: ActionProps & { plans: PlanSummary[]; batches: Batch[] }) {
  const ready=plans.filter(item=>item.status==='confirmed'||item.status==='queued'); const [planId,setPlanId]=useState(''); const [batchId,setBatchId]=useState('')
  useEffect(()=>{if(!planId&&ready[0])setPlanId(ready[0].id)},[planId,ready]); useEffect(()=>{if(!batchId&&batches[0])setBatchId(batches[0].id)},[batchId,batches])
  const batch=batches.find(item=>item.id===batchId)
  const start=()=>planId&&perform(async()=>{const next=await api.createBatch(planId);setBatchId(next.id)},refresh,notify,'Execution queued')
  const action=(name:'pause'|'cancel'|'retry')=>batch&&perform(()=>api.batchAction(batch.id,name),refresh,notify,`Batch ${name} requested`)
  return <><Header eyebrow="CONFIRMED OPERATIONS ONLY" heading="Execution" description="Preflight validation runs again before every bounded batch." actions={<><select className="select" value={planId} onChange={e=>setPlanId(e.target.value)}><option value="">Confirmed plan</option>{ready.map(item=><option key={item.id} value={item.id}>{item.id.slice(0,8)} · {item.operations.length} operations</option>)}</select><button className="button primary" disabled={!planId} onClick={()=>void start()}>Confirm and execute</button></>}/><section className="execution-hero panel">{!batch?<Empty>No execution batch selected.</Empty>:<><div className="execution-status"><CirclePause size={34}/><div><div className="section-kicker">BATCH {batch.id.slice(0,8)}</div><h2>{batch.status.replaceAll('_',' ')}</h2><p>{batch.succeeded} succeeded · {batch.failed} failed · {batch.skipped} skipped</p></div></div><div className="guardrails"><div><CheckCircle2 size={14}/> No silent overwrite</div><div><CheckCircle2 size={14}/> Extension protected</div><div><CheckCircle2 size={14}/> Rollback journal enabled</div></div>{batch.error&&<div className="form-error">{batch.error}</div>}<div className="execution-actions"><button className="button secondary" onClick={()=>void action('pause')}>Pause safely</button><button className="button secondary" onClick={()=>void action('retry')}>Retry</button><button className="button danger" onClick={()=>void action('cancel')}>Cancel safely</button></div></>}</section><div className="review-toolbar"><select className="select" value={batchId} onChange={e=>setBatchId(e.target.value)}><option value="">Select batch</option>{batches.map(item=><option key={item.id} value={item.id}>{item.id.slice(0,8)} · {item.status}</option>)}</select><button className="button quiet" onClick={()=>void refresh()}>Refresh status</button></div></>
}

export function HistoryPage({ history, batches, notify, refresh }: ActionProps & { history: AuditLog[]; batches: Batch[] }) {
  const rollback=(batch:Batch)=>perform(()=>api.batchAction(batch.id,'rollback'),refresh,notify,'Rollback completed')
  return <><Header heading="History and recovery" description="Audit events and reversible execution batches are stored in SQLite." actions={<button className="button secondary" onClick={()=>perform(()=>api.backup(),refresh,notify,'Database backup created')}>Create backup</button>}/><section className="panel history-panel"><div className="table-head"><span>Event</span><span>Status</span><span>Details</span><span>Time</span><span/></div>{history.length===0?<Empty>No audit events yet.</Empty>:history.map(row=><div className="table-row" key={row.id}><strong>{row.event}</strong><Badge value={row.status}/><code>{JSON.stringify(row.details)}</code><span>{new Date(row.created_at).toLocaleString()}</span><span/></div>)}</section><section className="panel history-panel"><div className="panel-heading"><div><div className="section-kicker">ROLLBACK</div><h2>Execution batches</h2></div></div>{batches.map(batch=><div className="table-row" key={batch.id}><strong>{batch.id.slice(0,8)}</strong><Badge value={batch.status}/><span>{batch.succeeded} successful operations</span><span/><button className="button quiet" disabled={batch.status!=='completed'} onClick={()=>void rollback(batch)}><RotateCcw size={13}/> Roll back</button></div>)}</section></>
}

export function SettingsPage({ locale, setLocale, notify }: { locale: string; setLocale: (locale: 'en'|'zh-CN') => void; notify: (message:string)=>void }) {
  const [token,setToken]=useState(()=>window.localStorage.getItem('file-curator.admin-token')||'')
  const save=()=>{if(token)window.localStorage.setItem('file-curator.admin-token',token);else window.localStorage.removeItem('file-curator.admin-token');notify('Local settings saved')}
  return <><Header heading="Settings" description="Browser preferences and the optional single-admin API token." actions={<button className="button primary" onClick={save}>Save changes</button>}/><div className="settings-grid"><section className="panel settings-section"><div className="section-kicker">SAFETY</div><h2>Non-disableable guardrails</h2><p className="muted">No permanent delete, no cross-source copy, no silent overwrite, extension protection, frozen-plan confirmation and audit logging.</p></section><section className="panel settings-section"><label className="form-label">Language</label><select className="text-input" value={locale} onChange={e=>setLocale(e.target.value as 'en'|'zh-CN')}><option value="en">English</option><option value="zh-CN">Simplified Chinese</option></select><label className="form-label">Admin token</label><input type="password" className="text-input" value={token} onChange={e=>setToken(e.target.value)} placeholder="Optional bearer token"/></section></div></>
}

export function useOperationCount(plans: PlanSummary[]) { return useMemo(()=>plans.reduce((total,plan)=>total+plan.operations.length,0),[plans]) }
