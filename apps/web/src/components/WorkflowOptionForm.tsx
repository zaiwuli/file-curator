import { Plus, Trash2, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useI18n } from '../i18n'
import type { WorkflowOptionSchema, WorkflowProcessorCapability } from '../types'

type Props={
  schema:Record<string,WorkflowOptionSchema>
  options:Record<string,unknown>
  onChange:(options:Record<string,unknown>)=>void
  processors?:WorkflowProcessorCapability[]
}

const list=(value:unknown)=>Array.isArray(value)?value.map(String):[]

function TagInput({value,onChange,placeholder,label}:{value:string[];onChange:(value:string[])=>void;placeholder?:string;label?:string}){
  const {t}=useI18n()
  const [draft,setDraft]=useState('')
  const add=()=>{const next=draft.trim();if(next&&!value.includes(next))onChange([...value,next]);setDraft('')}
  return <div className="tag-editor"><div className="tag-list">{value.map(item=><span key={item}>{item}<button type="button" title={t('Remove')} onClick={()=>onChange(value.filter(value=>value!==item))}><X size={13}/></button></span>)}</div><input aria-label={label} value={draft} placeholder={placeholder} onChange={event=>setDraft(event.target.value)} onKeyDown={event=>{if(event.key==='Enter'||event.key===','){event.preventDefault();add()}}}/><button type="button" className="icon-button" title={t('Add')} disabled={!draft.trim()} onClick={add}><Plus size={14}/></button></div>
}

function KeyValueTags({value,onChange}:{value:Record<string,unknown>;onChange:(value:Record<string,unknown>)=>void}){
  const {t}=useI18n()
  const entries=Object.entries(value)
  const update=(oldKey:string,key:string,items:string[])=>{const next={...value};delete next[oldKey];if(key.trim())next[key.trim()]=items;onChange(next)}
  return <div className="key-value-editor">{entries.map(([key,items])=><div className="key-value-row" key={key}><input aria-label={t('Key')} value={key} onChange={event=>update(key,event.target.value,list(items))}/><TagInput value={list(items)} onChange={next=>update(key,key,next)}/><button type="button" className="icon-button" title={t('Delete')} onClick={()=>{const next={...value};delete next[key];onChange(next)}}><Trash2 size={14}/></button></div>)}<button type="button" className="button secondary" onClick={()=>onChange({...value,[`field_${entries.length+1}`]:[]})}><Plus size={14}/> {t('Add mapping')}</button></div>
}

function Replacements({value,onChange}:{value:unknown[];onChange:(value:unknown[])=>void}){
  const {t}=useI18n()
  const rows=value.map(item=>(typeof item==='object'&&item?item:{})) as Record<string,unknown>[]
  return <div className="replacement-editor">{rows.map((row,index)=><div className="replacement-row" key={index}><input aria-label={t('Pattern')} value={String(row.pattern??'')} placeholder={t('Pattern')} onChange={event=>onChange(rows.map((item,position)=>position===index?{...item,pattern:event.target.value}:item))}/><input aria-label={t('Replacement')} value={String(row.replacement??'')} placeholder={t('Replacement')} onChange={event=>onChange(rows.map((item,position)=>position===index?{...item,replacement:event.target.value}:item))}/><button type="button" className="icon-button" title={t('Delete')} onClick={()=>onChange(rows.filter((_,position)=>position!==index))}><Trash2 size={14}/></button></div>)}<button type="button" className="button secondary" onClick={()=>onChange([...rows,{pattern:'',replacement:''}])}><Plus size={14}/> {t('Add replacement')}</button></div>
}

export function validateWorkflowOption(name:string,definition:WorkflowOptionSchema,value:unknown):string{
  if(definition.required&&(value===undefined||value===null||value===''))return 'This field is required.'
  if(definition.control==='regex'&&value){try{new RegExp(String(value))}catch{return 'Enter a valid regular expression.'}}
  if(definition.control==='number'&&value!==''&&value!==undefined){const number=Number(value);if(!Number.isFinite(number))return 'Enter a valid number.';if(definition.minimum!==undefined&&number<definition.minimum)return `Minimum: ${definition.minimum}`;if(definition.maximum!==undefined&&number>definition.maximum)return `Maximum: ${definition.maximum}`}
  if(name.includes('extensions')&&list(value).some(item=>!item.startsWith('.')))return 'Extensions must start with a dot.'
  return ''
}

export function WorkflowOptionForm({schema,options,onChange,processors=[]}:Props){
  const {t}=useI18n()
  const set=(name:string,value:unknown)=>onChange({...options,[name]:value})
  return <div className="schema-form">{Object.entries(schema).map(([name,definition])=>{
    const value=options[name]??definition.default??''
    const error=validateWorkflowOption(name,definition,value)
    const label=t(definition.title_key)
    const help=definition.description_key?t(definition.description_key):''
    let control
    if(definition.control==='processor')control=<select aria-label={label} className="text-input" value={String(value||processors[0]?.id||'')} onChange={event=>onChange({processor_id:event.target.value})}>{processors.map(item=><option value={item.id} key={item.id}>{t(item.title_key)}</option>)}</select>
    else if(definition.control==='tags')control=<TagInput label={label} value={list(value)} onChange={next=>set(name,next)} placeholder={definition.placeholder_key?t(definition.placeholder_key):undefined}/>
    else if(definition.control==='toggle')control=<label className="switch-control"><input aria-label={label} type="checkbox" checked={Boolean(value)} onChange={event=>set(name,event.target.checked)}/><span/><em>{Boolean(value)?t('Enabled'):t('Off')}</em></label>
    else if(definition.control==='segmented')control=<div className="segmented option-segmented">{(definition.enum??[]).map(item=><button type="button" className={value===item?'selected':''} key={String(item)} onClick={()=>set(name,item)}>{t(String(item).replaceAll('_',' '))}</button>)}</div>
    else if(definition.control==='select')control=<select aria-label={label} className="text-input" value={String(value)} onChange={event=>set(name,event.target.value)}>{(definition.enum??[]).map(item=><option value={String(item)} key={String(item)}>{t(String(item))}</option>)}</select>
    else if(definition.control==='number')control=<input aria-label={label} className="text-input" type="number" min={definition.minimum} max={definition.maximum} value={String(value)} onChange={event=>set(name,event.target.value===''?'':Number(event.target.value))}/>
    else if(definition.control==='key_value_tags')control=<KeyValueTags value={typeof value==='object'&&value&&!Array.isArray(value)?value as Record<string,unknown>: {}} onChange={next=>set(name,next)}/>
    else if(definition.control==='replacements')control=<Replacements value={Array.isArray(value)?value:[]} onChange={next=>set(name,next)}/>
    else control=<input aria-label={label} className="text-input" value={String(value)} placeholder={definition.placeholder_key?t(definition.placeholder_key):''} onChange={event=>set(name,event.target.value)}/>
    return <div className={`schema-field ${error?'invalid':''}`} key={name}><div className="schema-label"><strong>{label}</strong>{help&&<small>{help}</small>}</div>{control}{error&&<span className="field-error">{t(error)}</span>}</div>
  })}</div>
}

export function ExpertJsonEditor({value,onChange}:{value:Record<string,unknown>;onChange:(value:Record<string,unknown>)=>void}){
  const {t}=useI18n();const [draft,setDraft]=useState(()=>JSON.stringify(value,null,2));const [error,setError]=useState('')
  useEffect(()=>setDraft(JSON.stringify(value,null,2)),[value])
  const apply=()=>{try{const parsed=JSON.parse(draft);if(!parsed||Array.isArray(parsed)||typeof parsed!=='object')throw new Error();onChange(parsed as Record<string,unknown>);setError('')}catch{setError(t('Options must be valid JSON'))}}
  return <div className="expert-json"><textarea className="text-input rule-options" value={draft} onChange={event=>setDraft(event.target.value)}/>{error&&<span className="field-error">{error}</span>}<button type="button" className="button secondary" onClick={apply}>{t('Apply processor options')}</button></div>
}
