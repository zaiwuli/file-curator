import { useEffect } from 'react'

const zh: Record<string,string> = {
  'Dashboard':'仪表盘','Sources':'数据源','File browser':'文件浏览器','Pipeline':'处理流程','Review center':'审核中心','Virtual preview':'虚拟预览','Execution':'执行','History':'历史记录','Settings':'设置',
  'Workspace':'工作区','Local library':'本地文件库','Local-first workbench':'本地文件工作台','Safe mode':'安全模式','Frozen plan required':'必须冻结计划','API connected':'API 已连接','Connecting to API':'正在连接 API','API unavailable':'API 不可用','Switch to Chinese':'切换到中文','Switch to English':'切换到英文',
  'Workspace overview':'工作区概览','Review indexed metadata and virtual plans before touching any files.':'在更改文件前审核索引元数据和虚拟计划。','Add source':'添加数据源','Preview plan':'预览计划','Data mode':'数据模式','Metadata':'元数据','Real files remain unchanged':'真实文件保持不变','Safety boundary':'安全边界','Frozen plan':'冻结计划','Confirmation required':'需要确认','Workflows':'工作流','Plans':'计划','ACTIVE WORKFLOW':'当前工作流','Create your first workflow':'创建第一个工作流','Simulation only until a plan is frozen and confirmed':'计划冻结并确认前仅进行模拟','Configure workflow':'配置工作流',
  'LOCAL FILESYSTEM':'本地文件系统','Directories indexed by File Curator. Standard scans read metadata only.':'由 File Curator 索引的目录。标准扫描只读取元数据。','Connected':'已连接','Unavailable':'不可用','Loading':'加载中','Scan metadata':'扫描元数据','Hash contents':'计算内容哈希','NEW SOURCE':'新数据源','Add local directory':'添加本地目录','Display name':'显示名称','Absolute path':'绝对路径','Read-only source':'只读数据源','Cancel':'取消',
  'INDEXED METADATA':'已索引元数据','Search indexed paths and inspect related file groups without reading file contents.':'搜索已索引路径，并在不读取文件内容的情况下查看相关文件组。','Select source':'选择数据源','Search path':'搜索路径','Extension':'扩展名','Apply filters':'应用筛选','No indexed files match the current filters.':'没有符合当前筛选条件的文件。','Path':'路径','Type':'类型','Size':'大小','Modified':'修改时间','RELATED FILES':'相关文件','Detected groups':'检测到的文件组',
  'Workflow builder':'工作流构建器','Each enabled processor records its input, output, reasons and decision score.':'每个启用的处理器都会记录输入、输出、原因和决策分数。','Save revision':'保存修订','Run simulation':'运行模拟','PROCESSORS':'处理器','Runtime switches':'运行时开关','Configure':'配置','WORKFLOW':'工作流','Name':'名称','Preset':'预设','Rename Only':'仅改名','Rename And Organize':'改名并整理','Review policy':'审核策略','Conservative':'保守','Balanced':'平衡','Automatic':'自动','Source':'数据源','Existing workflow':'现有工作流','New workflow':'新工作流','Create as new':'创建新工作流','Apply processor options':'应用处理器选项','Latest run':'最近运行','MAINTENANCE':'维护','Revision comparison and portable JSON':'修订对比与可移植 JSON','Export':'导出','Import as new':'导入为新工作流',
  'Approve, keep, or override every gated file before it can enter an executable plan.':'每个受控文件必须接受、保留或覆盖后才能进入可执行计划。','All review gates':'全部审核关卡','No unresolved review items.':'没有未解决的审核项。','Manual target path':'手动目标路径','Keep unchanged':'保持不变','Use manual path':'使用手动路径','Accept suggestion':'接受建议','Evidence and processors':'证据和处理器',
  'This diff comes from SQLite metadata. Real paths are untouched until execution.':'此差异来自 SQLite 元数据，执行前不会更改真实路径。','Select run':'选择运行','Create plan':'创建计划','Freeze':'冻结','Confirm':'确认','Select plan':'选择计划','Create or select a plan to inspect its virtual paths.':'创建或选择计划以查看虚拟路径。','Original path':'原始路径','Proposed path':'建议路径','Operation':'操作','Reason':'原因',
  'CONFIRMED OPERATIONS ONLY':'仅执行已确认操作','Preflight validation runs again before every bounded batch.':'每个有限批次执行前都会重新进行预检。','Confirmed plan':'已确认计划','Confirm and execute':'确认并执行','No execution batch selected.':'尚未选择执行批次。','No silent overwrite':'禁止静默覆盖','Extension protected':'扩展名受保护','Rollback journal enabled':'已启用回滚日志','Pause safely':'安全暂停','Retry':'重试','Cancel safely':'安全取消','Select batch':'选择批次','Refresh status':'刷新状态',
  'History and recovery':'历史与恢复','Audit events and reversible execution batches are stored in SQLite.':'审核事件和可回滚执行批次存储在 SQLite 中。','Create backup':'创建备份','Event':'事件','Status':'状态','Details':'详情','Time':'时间','No audit events yet.':'暂无审核事件。','ROLLBACK':'回滚','Execution batches':'执行批次','Simulate':'模拟','Roll back':'回滚','BACKUPS':'备份','SQLite snapshots':'SQLite 快照','No backups created yet.':'尚未创建备份。','Download':'下载',
  'Browser preferences, schedules, diagnostics and the optional single-admin API token.':'浏览器偏好、计划任务、诊断和可选的单管理员 API 令牌。','Save changes':'保存更改','SAFETY':'安全','Non-disableable guardrails':'不可关闭的安全规则','No permanent delete, no cross-source copy, no silent overwrite, extension protection, frozen-plan confirmation and audit logging.':'禁止永久删除、跨数据源复制和静默覆盖，并强制扩展名保护、冻结计划确认和审核日志。','DIAGNOSTICS':'诊断','Version':'版本','Worker':'工作进程','Database':'数据库','Config':'配置','Webhook':'Webhook','Running':'运行中','Stopped':'已停止','Writable':'可写','Read only':'只读','Configured':'已配置','Off':'关闭','Enable browser notifications':'启用浏览器通知','Language':'语言','English':'英语','Simplified Chinese':'简体中文','Admin token':'管理员令牌','Optional bearer token':'可选 Bearer 令牌','SCHEDULED SCANS':'定时扫描','Schedule name':'任务名称','Add schedule':'添加任务','Delete':'删除','Enabled':'已启用','Paused':'已暂停','Diagnostics unavailable':'诊断不可用',
}

export const messages = {
  en: { appName: 'File Curator', nav: { dashboard: 'Dashboard', sources: 'Sources', files: 'File browser', pipeline: 'Pipeline', review: 'Review center', preview: 'Virtual preview', execution: 'Execution', history: 'History', settings: 'Settings' }, actions: { scan: 'Scan now', preview: 'Preview plan', execute: 'Execute plan', save: 'Save changes', back: 'Back' } },
  'zh-CN': { appName: 'File Curator', nav: { dashboard: '仪表盘', sources: '数据源', files: '文件浏览器', pipeline: '处理流程', review: '审核中心', preview: '虚拟预览', execution: '执行', history: '历史记录', settings: '设置' }, actions: { scan: '立即扫描', preview: '预览计划', execute: '执行计划', save: '保存更改', back: '返回' } },
} as const

export type Locale = keyof typeof messages

export function translate(locale:Locale,value:string) {
  if(locale==='en') return value
  if(zh[value]) return zh[value]
  return value
    .replace(/^Every (\d+) minutes$/, '每 $1 分钟')
    .replace(/^(\d+) stored revisions$/, '已保存 $1 个修订')
    .replace(/^(\d+) files$/, '$1 个文件')
    .replace(/^(\d+) groups$/, '$1 个文件组')
}

const originals = new WeakMap<Node,string>()
const applied = new WeakMap<Node,string>()
const attributeOriginals = new WeakMap<Element,Record<string,string>>()

function localizeDocument(locale:Locale) {
  const root=document.getElementById('root')
  if(!root)return
  const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT)
  let node:Node|null
  while((node=walker.nextNode())) {
    const current=node.nodeValue||''
    if(!originals.has(node)||current!==applied.get(node)) originals.set(node,current)
    const original=originals.get(node)||current
    const trimmed=original.trim()
    const localized=trimmed?original.replace(trimmed,translate(locale,trimmed)):original
    applied.set(node,localized)
    if(current!==localized)node.nodeValue=localized
  }
  for(const element of root.querySelectorAll('*')) {
    const stored=attributeOriginals.get(element)||{}
    for(const attribute of ['placeholder','title','aria-label']) {
      const current=element.getAttribute(attribute)
      if(current!==null&&stored[attribute]===undefined)stored[attribute]=current
      if(stored[attribute]!==undefined) {
        const localized=translate(locale,stored[attribute])
        if(current!==localized)element.setAttribute(attribute,localized)
      }
    }
    attributeOriginals.set(element,stored)
  }
}

export function useDocumentLocale(locale:Locale) {
  useEffect(()=>{
    document.documentElement.lang=locale
    const apply=()=>localizeDocument(locale)
    apply()
    const observer=new MutationObserver(apply)
    const root=document.getElementById('root')
    if(root)observer.observe(root,{childList:true,subtree:true,characterData:true})
    return()=>observer.disconnect()
  },[locale])
}
