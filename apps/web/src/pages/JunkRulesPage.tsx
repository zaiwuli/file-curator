import { ArrowDown, ArrowUp, Copy, Plus, Save, ShieldCheck, Trash2, X } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import { useI18n } from '../i18n'
import type { JunkRule, JunkRulePack, JunkRulePackVersion, JunkRulePackWrite, Workflow } from '../types'

type Props={workflows:Workflow[];notify:(message:string)=>void;refresh:()=>Promise<void>}

const newRule=(order:number):JunkRule=>({
  id:`custom.rule.${Date.now()}`,name:'New junk rule',description:'',enabled:true,order,
  action:'review',score:30,extensions:[],filename_contains:[],filename_regex:[],
  path_contains:[],max_size:null,min_size:null,empty_only:false,stop_on_match:false,
})
const newPack=():JunkRulePack=>({
  id:'',version:'0',name:'New junk rule pack',description:'',protected_extensions:['.srt','.ass','.ssa','.nfo'],
  protected_names:[],protected_paths:[],rules:[newRule(0)],source:'personal',read_only:false,current_version:0,
})
const writable=(pack:JunkRulePack,changeNote=''):JunkRulePackWrite=>({
  name:pack.name,description:pack.description,protected_extensions:pack.protected_extensions,
  protected_names:pack.protected_names,protected_paths:pack.protected_paths,rules:pack.rules,change_note:changeNote,
})

function Tags({label,value,onChange,disabled,placeholder}:{label:string;value:string[];onChange:(value:string[])=>void;disabled?:boolean;placeholder?:string}){
  const {t}=useI18n();const [draft,setDraft]=useState('')
  const add=()=>{const item=draft.trim();if(item&&!value.includes(item))onChange([...value,item]);setDraft('')}
  return <div className="junk-field"><label>{label}</label><div className="tag-editor"><div className="tag-list">{value.map(item=><span key={item}>{item}{!disabled&&<button title={t('Remove')} onClick={()=>onChange(value.filter(value=>value!==item))}><X size={12}/></button>}</span>)}</div><input aria-label={label} disabled={disabled} value={draft} placeholder={placeholder} onChange={event=>setDraft(event.target.value)} onKeyDown={event=>{if(event.key==='Enter'||event.key===','){event.preventDefault();add()}}}/><button className="icon-button" title={t('Add')} disabled={disabled||!draft.trim()} onClick={add}><Plus size={14}/></button></div></div>
}

export function JunkRulesPage({workflows,notify,refresh}:Props){
  const {t}=useI18n()
  const [packs,setPacks]=useState<JunkRulePack[]>([])
  const [pack,setPack]=useState<JunkRulePack|null>(null)
  const [selectedRuleId,setSelectedRuleId]=useState('')
  const [versions,setVersions]=useState<JunkRulePackVersion[]>([])
  const [viewVersion,setViewVersion]=useState(0)
  const [workflowId,setWorkflowId]=useState('')
  const [changeNote,setChangeNote]=useState('')
  const [busy,setBusy]=useState(false)
  const [deleteArmed,setDeleteArmed]=useState(false)
  const [validationErrors,setValidationErrors]=useState<string[]>([])

  const selectPack=(value:JunkRulePack)=>{setPack(structuredClone(value));setSelectedRuleId(value.rules[0]?.id??'');setViewVersion(value.current_version);setDeleteArmed(false);void api.junkRulePackVersions(value.id).then(setVersions).catch(()=>setVersions([]))}
  const loadPacks=async(selectId?:string)=>{const values=await api.junkRulePacks();setPacks(values);const selected=values.find(item=>item.id===(selectId??pack?.id))??values[0];if(selected)selectPack(selected)}
  useEffect(()=>{void loadPacks().catch(()=>notify('junk.rules_load_failed'))},[])
  useEffect(()=>{if(!workflowId&&workflows[0])setWorkflowId(workflows[0].id)},[workflowId,workflows])
  const rule=useMemo(()=>pack?.rules.find(item=>item.id===selectedRuleId)??pack?.rules[0],[pack,selectedRuleId])
  const historical=Boolean(pack&&pack.id&&viewVersion!==pack.current_version)
  const locked=Boolean(pack?.read_only||historical)
  const changePack=(value:Partial<JunkRulePack>)=>{setValidationErrors([]);setPack(current=>current?{...current,...value}:current)}
  const changeRule=(value:Partial<JunkRule>)=>{setValidationErrors([]);setPack(current=>current?{...current,rules:current.rules.map(item=>item.id===rule?.id?{...item,...value}:item)}:current)}
  const addRule=()=>{if(!pack)return;const value=newRule(pack.rules.length);changePack({rules:[...pack.rules,value]});setSelectedRuleId(value.id)}
  const copyRule=()=>{if(!pack||!rule)return;const value={...structuredClone(rule),id:`custom.rule.${Date.now()}`,name:`${rule.name} copy`,order:pack.rules.length};changePack({rules:[...pack.rules,value]});setSelectedRuleId(value.id)}
  const deleteRule=()=>{if(!pack||!rule||pack.rules.length===1)return;const rows=pack.rules.filter(item=>item.id!==rule.id).map((item,order)=>({...item,order}));changePack({rules:rows});setSelectedRuleId(rows[0]?.id??'')}
  const moveRule=(delta:number)=>{if(!pack||!rule)return;const index=pack.rules.findIndex(item=>item.id===rule.id);const target=index+delta;if(target<0||target>=pack.rules.length)return;const rows=[...pack.rules];[rows[index],rows[target]]=[rows[target],rows[index]];changePack({rules:rows.map((item,order)=>({...item,order}))})}
  const save=async()=>{if(!pack)return;setBusy(true);try{const validation=await api.validateJunkRulePack({...pack,id:pack.id||'draft-pack',version:pack.version||'1'});if(!validation.valid){setValidationErrors(validation.errors);return}const saved=pack.id?await api.updateJunkRulePack(pack.id,writable(pack,changeNote)):await api.createJunkRulePack(writable(pack,changeNote));setChangeNote('');setValidationErrors([]);await loadPacks(saved.id);notify('Junk rule pack saved')}catch{notify('junk.rules_save_failed')}finally{setBusy(false)}}
  const copyPack=async()=>{if(!pack?.id)return;setBusy(true);try{const saved=await api.copyJunkRulePack(pack.id);await loadPacks(saved.id);notify('Junk rule pack copied')}catch{notify('junk.rules_copy_failed')}finally{setBusy(false)}}
  const removePack=async()=>{if(!pack?.id||pack.read_only)return;if(!deleteArmed){setDeleteArmed(true);return}setBusy(true);try{await api.deleteJunkRulePack(pack.id);setPack(null);await loadPacks();notify('Junk rule pack deleted')}catch{notify('junk.rules_delete_failed')}finally{setBusy(false)}}
  const apply=async()=>{if(!pack?.id||!workflowId)return;setBusy(true);try{await api.applyJunkRulePack(pack.id,workflowId,viewVersion||undefined);await refresh();notify('Junk rule pack applied to workflow')}catch{notify('junk.rules_apply_failed')}finally{setBusy(false)}}
  const showVersion=async(version:number)=>{if(!pack?.id)return;setBusy(true);try{const value=await api.junkRulePack(pack.id,version);setPack({...value,current_version:pack.current_version});setSelectedRuleId(value.rules[0]?.id??'');setViewVersion(version)}finally{setBusy(false)}}

  return <>
    <div className="page-header"><div><div className="eyebrow">{t('JUNK RULE LIBRARY')}</div><h1>{t('Junk rules')}</h1><p>{t('Build reusable rule packs. Every rule has its own evidence, score and action.')}</p></div><div className="header-actions"><button className="button secondary" onClick={()=>{const value=newPack();setPack(value);setSelectedRuleId(value.rules[0].id);setVersions([]);setViewVersion(0)}}><Plus size={14}/> {t('New rule pack')}</button><button className="button secondary" disabled={!pack?.id||busy} onClick={()=>void copyPack()}><Copy size={14}/> {t('Copy rule pack')}</button><button className="button primary" disabled={!pack||locked||busy} onClick={()=>void save()}><Save size={14}/> {t(busy?'Working...':'Save new version')}</button></div></div>
    <section className="panel junk-apply-bar"><div><strong>{t('Use this rule pack in a workflow')}</strong><small>{t('The selected version is copied into a new workflow revision.')}</small></div><select aria-label={t('Target workflow')} className="text-input" value={workflowId} onChange={event=>setWorkflowId(event.target.value)}><option value="">{t('Select workflow')}</option>{workflows.map(item=><option value={item.id} key={item.id}>{item.name} ({t('revision')} {item.current_revision})</option>)}</select><button className="button primary" disabled={!pack?.id||!workflowId||busy} onClick={()=>void apply()}>{t('Apply selected version')}</button></section>
    <div className="junk-manager">
      <aside className="panel junk-pack-list"><div className="section-kicker">{t('RULE PACKS')}</div>{packs.map(item=><button key={item.id} className={pack?.id===item.id?'junk-pack selected':'junk-pack'} onClick={()=>selectPack(item)}><ShieldCheck size={16}/><span><strong>{t(item.name)}</strong><small>{item.source==='built_in'?t('Built-in · read only'):`${t('Personal')} · ${t('version')} ${item.current_version}`}</small></span></button>)}</aside>
      <main className="panel junk-pack-editor">{pack&&<>
        <div className="junk-pack-meta"><label>{t('Rule pack name')}<input className="text-input" disabled={locked} value={pack.source==='built_in'?t(pack.name):pack.name} onChange={event=>changePack({name:event.target.value})}/></label><label>{t('Description')}<input className="text-input" disabled={locked} value={pack.source==='built_in'?t(pack.description):pack.description} onChange={event=>changePack({description:event.target.value})}/></label><label>{t('Version')}<select className="text-input" value={viewVersion} disabled={!pack.id||busy} onChange={event=>void showVersion(Number(event.target.value))}>{versions.map(item=><option key={item.version} value={item.version}>v{item.version}{item.change_note?` · ${t(item.change_note)}`:''}</option>)}</select></label></div>
        {pack.read_only&&<div className="junk-info">{t('Built-in packs cannot be edited. Copy this pack to create a personal version.')}</div>}{historical&&<div className="junk-info">{t('You are viewing an immutable historical version.')}</div>}
        {validationErrors.length>0&&<div className="junk-validation-errors"><strong>{t('Fix these rules before saving')}</strong>{validationErrors.map(error=><span key={error}>{t(error.startsWith('junk.unbounded_quarantine_rule')?'A quarantine rule must have at least one matching condition.':error.startsWith('junk.invalid_regex')?'One file-name regular expression is invalid.':error.startsWith('junk.duplicate_rule')?'Rule identifiers must be unique.':error)}</span>)}</div>}
        <details className="junk-whitelist" open><summary>{t('Pack whitelist')}</summary><div className="junk-whitelist-grid"><Tags label={t('Protected extension whitelist')} value={pack.protected_extensions} disabled={locked} onChange={value=>changePack({protected_extensions:value})}/><Tags label={t('Protected file name values')} value={pack.protected_names} disabled={locked} onChange={value=>changePack({protected_names:value})}/><Tags label={t('Protected path values')} value={pack.protected_paths} disabled={locked} onChange={value=>changePack({protected_paths:value})}/></div></details>
        <div className="junk-rule-workspace">
          <aside className="junk-rule-list"><div className="subsection-heading"><div><strong>{t('Rules')}</strong><small>{t(`${pack.rules.length} rules`)}</small></div><button className="icon-button" title={t('Add rule')} disabled={locked} onClick={addRule}><Plus size={14}/></button></div>{pack.rules.map(item=><button key={item.id} className={item.id===rule?.id?'junk-rule-item selected':'junk-rule-item'} onClick={()=>setSelectedRuleId(item.id)}><span>{item.order+1}</span><div><strong>{t(item.name)}</strong><small>{t(item.action)} · {item.score}</small></div><em className={item.enabled?'on':''}/></button>)}</aside>
          {rule&&<section className="junk-rule-editor"><div className="rule-toolbar"><button title={t('Move up')} disabled={locked} onClick={()=>moveRule(-1)}><ArrowUp size={14}/></button><button title={t('Move down')} disabled={locked} onClick={()=>moveRule(1)}><ArrowDown size={14}/></button><button title={t('Duplicate')} disabled={locked} onClick={copyRule}><Copy size={14}/></button><button title={t('Delete')} disabled={locked||pack.rules.length===1} onClick={deleteRule}><Trash2 size={14}/></button></div>
            <div className="junk-rule-basics"><label>{t('Rule name')}<input className="text-input" disabled={locked} value={pack.source==='built_in'?t(rule.name):rule.name} onChange={event=>changeRule({name:event.target.value})}/></label><label>{t('Description')}<input className="text-input" disabled={locked} value={pack.source==='built_in'?t(rule.description):rule.description} onChange={event=>changeRule({description:event.target.value})}/></label><label className="checkbox-line"><input type="checkbox" disabled={locked} checked={rule.enabled} onChange={event=>changeRule({enabled:event.target.checked})}/><span>{t('Enable this rule')}</span></label></div>
            <div className="junk-rule-decision"><label>{t('Action')}<select className="text-input" disabled={locked} value={rule.action} onChange={event=>changeRule({action:event.target.value as JunkRule['action']})}><option value="keep">{t('Keep unchanged')}</option><option value="review">{t('Require review')}</option><option value="quarantine">{t('Quarantine and review')}</option></select></label><label>{t('Evidence score')}<input className="text-input" type="number" min="0" max="100" disabled={locked} value={rule.score} onChange={event=>changeRule({score:Number(event.target.value)})}/></label><label className="checkbox-line"><input type="checkbox" disabled={locked} checked={rule.stop_on_match} onChange={event=>changeRule({stop_on_match:event.target.checked})}/><span>{t('Stop after this rule matches')}</span></label></div>
            <div className="junk-match-grid"><Tags label={t('File extensions')} value={rule.extensions} disabled={locked} placeholder=".tmp" onChange={value=>changeRule({extensions:value})}/><Tags label={t('File name keywords')} value={rule.filename_contains} disabled={locked} onChange={value=>changeRule({filename_contains:value})}/><Tags label={t('File name regular expressions')} value={rule.filename_regex} disabled={locked} onChange={value=>changeRule({filename_regex:value})}/><Tags label={t('Path keywords')} value={rule.path_contains} disabled={locked} onChange={value=>changeRule({path_contains:value})}/><label>{t('Minimum bytes')}<input className="text-input" type="number" min="0" disabled={locked} value={rule.min_size??''} onChange={event=>changeRule({min_size:event.target.value===''?null:Number(event.target.value)})}/></label><label>{t('Maximum bytes')}<input className="text-input" type="number" min="0" disabled={locked} value={rule.max_size??''} onChange={event=>changeRule({max_size:event.target.value===''?null:Number(event.target.value)})}/></label><label className="checkbox-line"><input type="checkbox" disabled={locked} checked={rule.empty_only} onChange={event=>changeRule({empty_only:event.target.checked})}/><span>{t('Only empty files')}</span></label></div>
          </section>}
        </div>
        {!locked&&pack.id&&<div className="junk-pack-footer"><label>{t('Version note')}<input className="text-input" value={changeNote} onChange={event=>setChangeNote(event.target.value)} placeholder={t('Describe what changed')}/></label><button className={deleteArmed?'button danger':'button secondary'} disabled={busy} onClick={()=>void removePack()}><Trash2 size={14}/> {t(deleteArmed?'Confirm delete rule pack':'Delete rule pack')}</button></div>}
      </>}</main>
    </div>
  </>
}
