import { Database, Folder, History as HistoryIcon, LayoutDashboard, ListChecks, Play, Settings as SettingsIcon, ShieldCheck, Workflow as WorkflowIcon } from 'lucide-react'
import { useState } from 'react'
import { Topbar } from '../components/Topbar'
import { useWorkspace } from '../hooks/useWorkspace'
import { messages, type Locale } from '../i18n'
import { DashboardPage } from '../pages/DashboardPage'
import { SourcesPage } from '../pages/SourcesPage'
import { ExecutionPage, HistoryPage, PipelinePage, PreviewPage, ReviewPage, SettingsPage } from '../pages/WorkbenchPages'
import type { Page } from '../types'

const navItems: { id: Page; label: string; icon: React.ComponentType<{size?:number}> }[] = [
  {id:'dashboard',label:'Dashboard',icon:LayoutDashboard}, {id:'sources',label:'Sources',icon:Database}, {id:'pipeline',label:'Pipeline',icon:WorkflowIcon}, {id:'review',label:'Review center',icon:ListChecks}, {id:'preview',label:'Virtual preview',icon:Folder}, {id:'execution',label:'Execution',icon:Play}, {id:'history',label:'History',icon:HistoryIcon}, {id:'settings',label:'Settings',icon:SettingsIcon},
]

export function App() {
  const [page,setPage]=useState<Page>('dashboard'); const [locale,setLocale]=useState<Locale>('en'); const [toast,setToast]=useState('')
  const workspace=useWorkspace(); const title=navItems.find(item=>item.id===page)?.label||'Dashboard'
  const notify=(message:string)=>{setToast(message);window.setTimeout(()=>setToast(''),3000)}
  const common={notify,refresh:workspace.refresh}
  return <div className="app-shell"><aside className="sidebar"><div className="brand"><div className="brand-mark">FC</div><div><strong>File Curator</strong><small>Local-first workbench</small></div></div><div className="workspace-label">WORKSPACE</div><div className="workspace-select"><span className={`status-dot ${workspace.state}`}/> Local library</div><nav>{navItems.map(item=>{const Icon=item.icon;return <button key={item.id} className={`nav-item ${page===item.id?'active':''}`} onClick={()=>setPage(item.id)}><span className="nav-icon"><Icon size={16}/></span><span>{(messages[locale].nav as Record<string,string>)[item.id]}</span>{item.id==='review'&&workspace.reviews.length>0&&<em>{workspace.reviews.length}</em>}</button>})}</nav><div className="sidebar-bottom"><div className="safe-card"><div className="safe-icon"><ShieldCheck size={14}/></div><div><strong>Safe mode</strong><small>Frozen plan required</small></div><span className="toggle on"><span/></span></div><div className="version">v0.1.0 · local instance</div></div></aside><main className="main-content"><Topbar title={title} state={workspace.state} locale={locale} onLocale={()=>setLocale(locale==='en'?'zh-CN':'en')}/><div className="content-wrap">
    {page==='dashboard'&&<DashboardPage setPage={setPage} state={workspace.state} workflows={workspace.workflows} plans={workspace.plans}/>} 
    {page==='sources'&&<SourcesPage notify={notify} data={workspace.sources} state={workspace.state} error={workspace.error} refresh={workspace.refresh}/>} 
    {page==='pipeline'&&<PipelinePage {...common} sources={workspace.apiSources} workflows={workspace.workflows} processors={workspace.processors} runs={workspace.runs}/>} 
    {page==='review'&&<ReviewPage {...common} reviews={workspace.reviews} runs={workspace.runs}/>}
    {page==='preview'&&<PreviewPage {...common} runs={workspace.runs} plans={workspace.plans}/>} 
    {page==='execution'&&<ExecutionPage {...common} plans={workspace.plans} batches={workspace.batches}/>} 
    {page==='history'&&<HistoryPage {...common} history={workspace.history} batches={workspace.batches}/>} 
    {page==='settings'&&<SettingsPage locale={locale} setLocale={setLocale} notify={notify}/>} 
  </div></main>{toast&&<div className="toast">{toast}</div>}</div>
}
