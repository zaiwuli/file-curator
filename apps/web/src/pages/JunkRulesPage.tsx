import { CheckCircle2, FileWarning, Save, ShieldCheck, TriangleAlert } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api } from '../api'
import { WorkflowOptionForm } from '../components/WorkflowOptionForm'
import { useI18n } from '../i18n'
import type { JunkRulePack, JunkRulePackValidation, RuleCard, Workflow, WorkflowAction, WorkflowOptionSchema, WorkflowTemplateV2 } from '../types'

type Props = { workflows:Workflow[]; notify:(message:string)=>void; refresh:()=>Promise<void> }

const defaultOptions:Record<string,unknown>={
  processor_id:'detect_junk', extensions:[], filename_contains:[], protected_extensions:[],
  require_hash_evidence:false, require_small_text:false,
}

function junkAction(template:WorkflowTemplateV2):WorkflowAction|undefined{
  return template.stages.flatMap(stage=>stage.rules).flatMap(rule=>rule.actions)
    .find(action=>action.kind==='run_processor'&&action.options.processor_id==='detect_junk')
}

function withJunkOptions(template:WorkflowTemplateV2,options:Record<string,unknown>):WorkflowTemplateV2{
  const next=structuredClone(template)
  let updated=false
  for(const stage of next.stages){
    for(const rule of stage.rules){
      const action=rule.actions.find(value=>value.kind==='run_processor'&&value.options.processor_id==='detect_junk')
      if(action){action.options={...options,processor_id:'detect_junk'};updated=true;break}
    }
    if(updated)break
  }
  if(!updated){
    const stage=next.stages.find(value=>value.id==='classify')
    if(!stage)throw new Error('workflow.classify_stage_missing')
    const rule:RuleCard={
      id:`classify.junk.custom.${Date.now()}`,name:'Detect junk and advertisements',description:'',enabled:true,
      order:stage.rules.length,conditions:{mode:'all',conditions:[],groups:[]},
      actions:[{kind:'run_processor',options:{...options,processor_id:'detect_junk'}}],on_match:'continue',
    }
    stage.rules.push(rule)
  }
  return next
}

export function JunkRulesPage({workflows,notify,refresh}:Props){
  const {t}=useI18n()
  const [packs,setPacks]=useState<JunkRulePack[]>([])
  const [selected,setSelected]=useState<JunkRulePack|null>(null)
  const [text,setText]=useState('')
  const [validation,setValidation]=useState<JunkRulePackValidation|null>(null)
  const [workflowId,setWorkflowId]=useState('')
  const [template,setTemplate]=useState<WorkflowTemplateV2|null>(null)
  const [options,setOptions]=useState<Record<string,unknown>>(defaultOptions)
  const [processorSchema,setProcessorSchema]=useState<Record<string,WorkflowOptionSchema>|null>(null)
  const [loading,setLoading]=useState(false)
  const [saving,setSaving]=useState(false)

  useEffect(()=>{
    void Promise.all([api.junkRulePacks(),api.workflowCapabilities()]).then(([value,capabilities])=>{
      setPacks(value);setSelected(value[0]??null);setText(JSON.stringify(value[0]??{},null,2))
      const processor=capabilities.processors.find(item=>item.id==='detect_junk')
      setProcessorSchema(processor?.option_schema??{})
    }).catch(()=>notify('junk.rules_load_failed'))
  },[notify])

  useEffect(()=>{if(!workflowId&&workflows[0])setWorkflowId(workflows[0].id)},[workflowId,workflows])
  useEffect(()=>{
    if(!workflowId){setTemplate(null);setOptions(defaultOptions);return}
    let active=true;setLoading(true)
    void api.exportTemplate(workflowId,'json').then(content=>{
      if(!active)return
      const value=JSON.parse(content) as WorkflowTemplateV2
      setTemplate(value)
      setOptions({...defaultOptions,...(junkAction(value)?.options??{}),processor_id:'detect_junk'})
    }).catch(()=>notify('junk.workflow_load_failed')).finally(()=>{if(active)setLoading(false)})
    return()=>{active=false}
  },[workflowId,notify])

  const choose=(pack:JunkRulePack)=>{setSelected(pack);setText(JSON.stringify(pack,null,2));setValidation(null)}
  const validate=async()=>{try{const value=JSON.parse(text) as unknown;setValidation(await api.validateJunkRulePack(value))}catch{notify('junk.rules_invalid_json')}}
  const save=async()=>{
    if(!template||!workflowId)return
    setSaving(true)
    try{
      await api.updateTemplate(workflowId,withJunkOptions(template,options))
      notify('Junk rules saved to workflow')
      await refresh()
      const content=await api.exportTemplate(workflowId,'json')
      const value=JSON.parse(content) as WorkflowTemplateV2
      setTemplate(value);setOptions({...defaultOptions,...(junkAction(value)?.options??{}),processor_id:'detect_junk'})
    }catch{notify('junk.rules_save_failed')}finally{setSaving(false)}
  }

  return <>
    <div className="page-header"><div><div className="eyebrow">{t('JUNK RULE LIBRARY')}</div><h1>{t('Junk rules')}</h1><p>{t('Manage built-in evidence and workflow-specific junk rules in one place.')}</p></div></div>
    <section className="panel junk-workflow-editor">
      <div className="panel-heading"><div><div className="section-kicker">{t('WORKFLOW CUSTOM RULES')}</div><h2>{t('Manual rule configuration')}</h2><p>{t('These values are saved only to the selected workflow. Built-in rules remain unchanged.')}</p></div><button className="button primary" disabled={!template||loading||saving} onClick={()=>void save()}><Save size={14}/> {t(saving?'Saving...':'Save to workflow')}</button></div>
      <label className="junk-workflow-select">{t('Target workflow')}<select className="text-input" value={workflowId} onChange={event=>setWorkflowId(event.target.value)}><option value="">{t('Select workflow')}</option>{workflows.map(item=><option key={item.id} value={item.id}>{item.name} ({t('revision')} {item.current_revision})</option>)}</select></label>
      {workflows.length===0?<div className="empty-state">{t('Create a workflow before adding custom junk rules.')}</div>:loading?<div className="empty-state">{t('Loading...')}</div>:processorSchema&&template?<><div className="junk-workflow-status"><CheckCircle2 size={15}/><span>{junkAction(template)?t('This workflow already has junk detection; saving creates a new revision.'):t('Saving will add junk detection to this workflow and create a new revision.')}</span></div><WorkflowOptionForm schema={processorSchema} options={options} onChange={setOptions}/></>:null}
    </section>
    <div className="junk-library-heading"><div><div className="section-kicker">{t('BUILT-IN RULE LIBRARY')}</div><h2>{t('Read-only evidence rules')}</h2></div></div>
    <div className="junk-library-layout">
      <aside className="panel junk-pack-list"><div className="section-kicker">{t('RULE PACKS')}</div>{packs.map(pack=><button key={pack.id} className={selected?.id===pack.id?'junk-pack selected':'junk-pack'} onClick={()=>choose(pack)}><ShieldCheck size={16}/><span><strong>{t(pack.name)}</strong><small>v{pack.version} · {t(`${pack.rules.length} rules`)}</small></span></button>)}</aside>
      <main className="panel junk-pack-detail">{selected&&<>
        <div className="panel-heading"><div><div className="section-kicker">{selected.id}</div><h2>{t(selected.name)}</h2></div><span className="badge green">{t(`${selected.rules.length} rules`)}</span></div>
        <p className="junk-description">{t(selected.description)}</p>
        <div className="junk-protected"><CheckCircle2 size={14}/><span>{t('Protected extensions')}: {selected.protected_extensions.join(', ')}</span></div>
        <div className="junk-rule-table"><div className="table-head"><span>{t('Rule')}</span><span>{t('Evidence')}</span><span>{t('Action')}</span><span>{t('Score')}</span></div>{selected.rules.map(rule=><div className="table-row" key={rule.id}><div><strong>{t(rule.name)}</strong><small>{t(rule.description)}</small></div><code>{[...rule.extensions,...rule.filename_contains].slice(0,4).join(', ')||t('path / size')}</code><span className={`badge ${rule.action==='quarantine'?'red':rule.action==='review'?'amber':'green'}`}>{t(rule.action)}</span><strong>{rule.score}</strong></div>)}</div>
        <details className="junk-developer"><summary>{t('Import or validate a custom rule pack (JSON)')}</summary><textarea className="text-input portable-editor" value={text} onChange={event=>{setText(event.target.value);setValidation(null)}}/><button className="button secondary" onClick={()=>void validate()}><FileWarning size={13}/> {t('Validate rule pack')}</button>{validation&&<div className={validation.valid?'validation-result valid':'validation-result invalid'}>{validation.valid?<><CheckCircle2 size={14}/> {t('Rule pack is valid')}: {t(`${validation.rule_count} rules`)}</>:<><TriangleAlert size={14}/> {validation.errors.join(', ')}</>}</div>}</details>
      </>}</main>
    </div>
  </>
}
