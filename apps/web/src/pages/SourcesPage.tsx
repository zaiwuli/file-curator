import { Folder, Play, Plus, X } from 'lucide-react'
import { useState } from 'react'
import { api } from '../api'
import { useI18n } from '../i18n'
import type { Source } from '../types'

type Props = { data: Source[]; state: 'loading'|'live'|'offline'; error: string|null; refresh: () => Promise<void>; notify: (message:string) => void }

export function SourcesPage({data,state,error,refresh,notify}:Props) {
  const {t}=useI18n()
  const [open,setOpen]=useState(false)
  const [name,setName]=useState('')
  const [path,setPath]=useState('')
  const [readOnly,setReadOnly]=useState(false)
  const [busy,setBusy]=useState(false)
  const [formError,setFormError]=useState('')
  const create=async(event:React.FormEvent)=>{event.preventDefault();setBusy(true);setFormError('');try{await api.createSource({name,root_path:path,read_only:readOnly});await refresh();setOpen(false);setName('');setPath('');notify('Source added')}catch(cause){setFormError(cause instanceof Error?cause.message:'Could not add source')}finally{setBusy(false)}}
  const scan=async(source:Source,hashContents=false,inspectSmallText=false)=>{try{await api.createScan(source.id,hashContents,inspectSmallText);notify(`${hashContents?'Content hash':inspectSmallText?'Small text inspection':'Metadata'} scan queued for ${source.name}`);await refresh()}catch(cause){notify(cause instanceof Error?cause.message:'Could not queue scan')}}
  return <>
    <div className="page-header"><div><div className="eyebrow">{t('LOCAL FILESYSTEM')}</div><h1>{t('Sources')}</h1><p>{t('Directories indexed by File Curator. Standard scans read metadata only.')}</p></div><div className="header-actions"><span className={`badge ${state==='live'?'green':state==='loading'?'blue':'red'}`}>{t(state==='live'?'Connected':state==='loading'?'Loading':'Unavailable')}</span><button className="button primary" onClick={()=>setOpen(true)} disabled={state!=='live'}><Plus size={14}/> {t('Add source')}</button></div></div>
    {state==='offline'&&<div className="api-notice">{t('The API is unavailable')} ({error}). {t('Start the API to manage sources.')}</div>}
    <div className="source-grid">{data.map(source=><section className="panel source-card" key={source.id}><div className="source-top"><div className="folder-icon"><Folder size={18}/></div><span className={`badge ${source.status==='ready'?'green':source.status==='scanning'?'blue':'red'}`}>{t(source.status)}</span></div><h2>{source.name}</h2><code>{source.path}</code><div className="source-metrics"><span><strong>{source.files.toLocaleString()}</strong> {t('indexed count pending')}</span><span><strong>{source.size}</strong></span></div><div className="source-foot"><span className="muted">{source.lastScan}</span><div><button className="button quiet" onClick={()=>void scan(source)}><Play size={13}/> {t('Scan metadata')}</button><button className="button quiet" onClick={()=>void scan(source,true)}>{t('Hash contents')}</button><button className="button quiet" onClick={()=>void scan(source,false,true)}>{t('Inspect small text')}</button></div></div></section>)}</div>
    {open&&<div className="modal-backdrop" role="presentation" onMouseDown={()=>setOpen(false)}><form className="modal" onSubmit={create} onMouseDown={event=>event.stopPropagation()}><div className="modal-head"><div><div className="section-kicker">{t('NEW SOURCE')}</div><h2>{t('Add local directory')}</h2></div><button type="button" className="icon-button" title={t('Cancel')} onClick={()=>setOpen(false)}><X size={16}/></button></div><label className="form-label">{t('Display name')}</label><input className="text-input" value={name} onChange={event=>setName(event.target.value)} required placeholder={t('Media library')}/><label className="form-label">{t('Absolute path')}</label><input className="text-input" value={path} onChange={event=>setPath(event.target.value)} required placeholder="/volume1/media"/><label className="checkbox-line"><input type="checkbox" checked={readOnly} onChange={event=>setReadOnly(event.target.checked)}/><span>{t('Read-only source')}</span></label>{formError&&<div className="form-error">{t(formError)}</div>}<div className="modal-actions"><button type="button" className="button secondary" onClick={()=>setOpen(false)}>{t('Cancel')}</button><button className="button primary" disabled={busy}>{t(busy?'Adding source...':'Add source')}</button></div></form></div>}
  </>
}
