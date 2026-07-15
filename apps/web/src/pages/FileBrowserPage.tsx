import { ChevronLeft, ChevronRight, Files, Search } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api } from '../api'
import { useI18n } from '../i18n'
import type { ApiSource, FileGroup, FilePage } from '../types'

const emptyPage: FilePage = { items: [], total: 0, limit: 50, offset: 0 }

function formatSize(size: number) {
  if (size < 1024) return `${size} B`
  if (size < 1024 ** 2) return `${(size / 1024).toFixed(1)} KB`
  if (size < 1024 ** 3) return `${(size / 1024 ** 2).toFixed(1)} MB`
  return `${(size / 1024 ** 3).toFixed(1)} GB`
}

export function FileBrowserPage({ sources, notify }: { sources: ApiSource[]; notify: (message: string) => void }) {
  const {t}=useI18n()
  const [sourceId,setSourceId]=useState(''); const [search,setSearch]=useState(''); const [extension,setExtension]=useState('')
  const [page,setPage]=useState<FilePage>(emptyPage); const [groups,setGroups]=useState<FileGroup[]>([]); const [busy,setBusy]=useState(false)
  useEffect(()=>{if(!sourceId&&sources[0])setSourceId(sources[0].id)},[sourceId,sources])
  const load=async(offset=0)=>{if(!sourceId)return;setBusy(true);try{const [files,fileGroups]=await Promise.all([api.files({sourceId,search,extension,limit:50,offset}),api.fileGroups(sourceId)]);setPage(files);setGroups(fileGroups)}catch(cause){notify(cause instanceof Error?cause.message:'api.request_failed')}finally{setBusy(false)}}
  useEffect(()=>{if(sourceId)void load(0)},[sourceId]) // eslint-disable-line react-hooks/exhaustive-deps
  const end=Math.min(page.offset+page.items.length,page.total)
  return <><div className="page-header"><div><div className="eyebrow">{t('INDEXED METADATA')}</div><h1>{t('File browser')}</h1><p>{t('Search indexed paths and inspect related file groups without reading file contents.')}</p></div><div className="header-actions"><span className="badge blue">{t(`${page.total} files`)}</span><span className="badge neutral">{t(`${groups.length} groups`)}</span></div></div><section className="panel file-browser"><div className="browser-toolbar"><select className="select" value={sourceId} onChange={event=>setSourceId(event.target.value)}><option value="">{t('Select source')}</option>{sources.map(source=><option key={source.id} value={source.id}>{source.name}</option>)}</select><div className="search-control"><Search size={14}/><input value={search} onChange={event=>setSearch(event.target.value)} placeholder={t('Search path')}/></div><input className="select extension-filter" value={extension} onChange={event=>setExtension(event.target.value)} placeholder={t('Extension')}/><button className="button primary" disabled={!sourceId||busy} onClick={()=>void load(0)}>{busy?'Loading...':'Apply filters'}</button></div>{page.items.length===0?<div className="empty-state">{t('No indexed files match the current filters.')}</div>:<div className="file-table"><div className="table-head"><span>{t('Path')}</span><span>{t('Type')}</span><span>{t('Size')}</span><span>{t('Modified')}</span></div>{page.items.map(file=><div className="table-row" key={file.id}><div className="path-cell"><Files size={14}/><code>{file.relative_path}</code></div><span>{file.extension||t('directory')}</span><span>{file.is_dir?'—':formatSize(file.size)}</span><span>{new Date(file.mtime_ns/1_000_000).toLocaleString()}</span></div>)}</div>}<div className="pagination"><span>{page.total===0?'0':page.offset+1}–{end} of {page.total}</span><div><button className="icon-button" title={t('Previous page')} disabled={page.offset===0||busy} onClick={()=>void load(Math.max(0,page.offset-page.limit))}><ChevronLeft size={15}/></button><button className="icon-button" title={t('Next page')} disabled={end>=page.total||busy} onClick={()=>void load(page.offset+page.limit)}><ChevronRight size={15}/></button></div></div></section>{groups.length>0&&<section className="panel group-panel"><div className="panel-heading"><div><div className="section-kicker">{t('RELATED FILES')}</div><h2>{t('Detected groups')}</h2></div></div>{groups.map(group=><div className="group-row" key={group.id}><strong>{group.group_key}</strong><span>{t(`${group.member_ids.length} members`)}</span><span>{t(`${Math.round(group.confidence*100)}% confidence`)}</span><code>{group.reasons.join(', ')}</code></div>)}</section>}</>
}
