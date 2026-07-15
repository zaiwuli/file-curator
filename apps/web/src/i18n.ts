import { useEffect } from 'react'

const zh: Record<string,string> = {
  'Review duplicate files':'\u5ba1\u6838\u91cd\u590d\u6587\u4ef6','Detect duplicate groups':'\u68c0\u6d4b\u91cd\u590d\u6587\u4ef6\u7ec4','Detect duplicate files':'\u68c0\u6d4b\u91cd\u590d\u6587\u4ef6','Detect junk and advertisements':'\u68c0\u6d4b\u5783\u573e\u548c\u5e7f\u544a','Detect indexed duplicate groups and send candidates to review.':'\u68c0\u6d4b\u5df2\u7d22\u5f15\u7684\u91cd\u590d\u6587\u4ef6\u7ec4\uff0c\u5e76\u5c06\u5019\u9009\u6587\u4ef6\u9001\u5165\u5ba1\u6838\u3002',
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
  'DETERMINISTIC PIPELINE':'确定性处理流程','Create workflow':'创建工作流','No pipeline run yet':'尚无处理流程运行记录','Exported workflow JSON or paste a workflow definition to import':'已导出的工作流 JSON，或粘贴要导入的工作流定义','Toggle language':'切换语言','local instance':'本地实例','WORKSPACE':'工作区','stored revisions':'个已保存修订','normal':'常规','advanced':'高级','· score':'· 分数',
  'Scan':'扫描','Extract':'提取','Normalize':'规范化','Group':'分组','Target':'生成目标','Review':'审核','Live API':'API 在线','Connecting':'连接中','Deterministic pipelines':'确定性处理流程','Draft, frozen and executed':'草稿、已冻结和已执行','Revision':'修订',
  'simulation':'模拟','score':'分数','revision':'修订','rev':'修订','options (JSON)':'选项（JSON）','Added':'新增','Removed':'移除','Changed':'更改','none':'无',
  'date extractor':'日期提取','identifier extractor':'标识符提取','sequence extractor':'序号提取','quality extractor':'质量标记提取','language extractor':'语言提取','source prefix extractor':'来源前缀提取','parent context extractor':'父目录上下文提取','custom regex extractor':'自定义正则提取','extension classifier':'扩展名分类','name normalizer':'名称规范化','naming template':'命名模板','junk candidate':'垃圾文件候选','folder template':'文件夹模板','group detector':'文件组检测','duplicate candidate':'重复文件候选',
  'extract date':'提取日期','extract identifier':'提取标识符','extract sequence':'提取序号','extract quality':'提取质量标记','extract parent context':'提取父目录上下文','extract regex':'正则提取','normalize name':'规范化名称','target template':'目标路径模板','detect junk':'检测垃圾候选','extract language':'提取语言','extract source prefix':'提取来源前缀','classify extension':'按扩展名分类',
  'extractor':'提取器','classifier':'分类器','normalizer':'规范化器','template':'模板','grouping':'分组','safe':'安全','review':'需审核','high':'高','medium':'中','low':'低',
  'unresolved':'未处理','accepted':'已接受','keep':'保持不变','override':'手动覆盖','draft':'草稿','frozen':'已冻结','confirmed':'已确认','queued':'排队中','processing':'处理中','completed':'已完成','failed':'失败','cancelled':'已取消','paused':'已暂停','rolled back':'已回滚','rename':'改名','move':'移动','archive':'归档','quarantine':'隔离','unchanged':'保持不变','conflicts':'冲突',
  'Run':'运行','Manual review required':'需要手动审核','File will remain unchanged':'文件将保持不变','Review decision saved':'审核决定已保存','Workflow created':'工作流已创建','Workflow revision saved':'工作流修订已保存','Virtual processing completed':'虚拟处理已完成','Processor options applied':'处理器选项已应用','Workflow exported below':'工作流已导出到下方','Workflow imported':'工作流已导入',
  'Draft plan created':'草稿计划已创建','Plan frozen':'计划已冻结','Plan confirmed':'计划已确认','Preflight passed; execution queued':'预检通过，执行任务已排队','Rollback simulation is ready':'回滚模拟已就绪','Rollback simulation found conflicts':'回滚模拟发现冲突','Rollback completed':'回滚已完成','Database backup created':'数据库备份已创建','Backup download started':'备份下载已开始','Local settings saved':'本地设置已保存','Schedule created':'计划任务已创建','Schedule updated':'计划任务已更新','Schedule deleted':'计划任务已删除','Source added':'数据源已添加',
  'Previous page':'上一页','Next page':'下一页','Loading...':'加载中...','directory':'目录','members':'个成员','confidence':'置信度','Media library':'媒体库','Adding source...':'正在添加数据源...','The API is unavailable':'API 不可用','Start the API to manage sources.':'请启动 API 后管理数据源。','indexed count pending':'索引数量待更新',
  'files':'个文件','groups':'个文件组','sources':'数据源','workflows':'工作流','plans':'计划','batches':'执行批次','of':'共',
  'succeeded':'成功','failed operations':'失败','skipped':'跳过','operations':'项操作','successful operations':'项成功操作','reversible':'项可回滚操作','ready':'就绪','conflict':'冲突','BATCH':'批次',
  'FILE ORGANIZATION':'文件整理','Build an organization workflow':'创建整理流程','Choose what you want to change. A preview is required before any real file is touched.':'选择需要处理的内容。修改真实文件前必须先生成预览。','Simple':'简单模式','Advanced':'高级模式',
  'Choose the folder to process':'选择要处理的文件夹','Only indexed metadata is used until you confirm a final plan.':'确认最终计划前，只使用已索引的元数据。','Add and scan a source before building a workflow.':'请先添加并扫描一个数据源。',
  'Choose the result':'选择整理结果','Start with rename only. Folder organization may require review when a file type is unknown.':'建议先使用仅改名。遇到未知文件类型时，分类整理可能需要人工审核。','Rename files only':'仅修改文件名','Clean names without moving files.':'清理名称，但不移动文件。','Rename and organize':'改名并分类整理','Clean names and place known types into folders.':'清理名称，并将已知类型放入对应文件夹。',
  'Choose what to detect and clean':'选择需要识别和清理的内容','Recommended options are enabled. Turn off anything you do not need.':'推荐功能已启用，可以关闭不需要的项目。','Clean file names':'清理文件名','Remove extra spaces and normalize separators.':'删除多余空格并规范分隔符。','Recognize file details':'识别文件信息','Detect dates, identifiers, episodes, quality, language and file type.':'识别日期、编号、集数、清晰度、语言和文件类型。','Flag junk candidates':'标记垃圾候选','Mark temporary and incomplete downloads for review.':'标记临时文件和未完成下载，等待审核。',
  'Prefixes to remove':'需要移除的前缀','Example: [WEB], SAMPLE_':'例如：[WEB], SAMPLE_','Convert dots and underscores to spaces':'将点号和下划线转换为空格','Generate a safe preview':'生成安全预览','You will review before and after paths on the next screen.':'下一页将显示处理前后的路径对比。','Rename only':'仅改名','feature groups selected · no real file changes':'项功能已选择 · 不会修改真实文件','Generating preview...':'正在生成预览...','Save and generate preview':'保存并生成预览','Preview generated; real files are unchanged':'预览已生成，真实文件未修改',
  'Advanced configuration':'高级配置','Import or export workflow JSON':'导入或导出工作流 JSON',
  'WORKFLOW ENGINE 2.0':'工作流引擎 2.0','Start from a template, paste an AI-generated template, or build rule cards manually.':'从内置模板开始、粘贴 AI 生成的模板，或手动搭建规则卡。','Save':'保存','Calculate impact':'计算影响','Generate preview':'生成预览','Working...':'处理中...',
  'Start from template':'从模板创建','Paste AI template':'粘贴 AI 模板','Build manually':'手动搭建','rules':'条规则','AI TEMPLATE PASTE':'AI 模板粘贴','Paste YAML or JSON':'粘贴 YAML 或 JSON','Ask any AI to produce a File Curator workflow v2 template. AI cannot execute files; this screen validates every step first.':'让任意 AI 生成 File Curator v2 工作流模板。AI 无法执行文件，本页面会先验证每个步骤。','Describe filters, name cleanup, date handling, archive paths, conflict policy and review rules.':'描述筛选条件、名称清理、日期处理、归档路径、冲突策略和审核规则。','Validate template':'验证模板','Import as workflow':'导入为工作流','Template is valid':'模板有效','Missing':'缺失',
  'PIPELINE GATES':'处理关卡','Scope':'作用范围','File filters':'文件筛选','Extract information':'提取信息','Clean names':'清理名称','Classify and group':'分类与分组','Rename, move and archive':'改名、移动与归档','Conflicts and review':'冲突与审核','Preview and execute':'预览与执行','total rules':'条规则总计','Add rule':'添加规则','No rules in this gate. Add one or keep the gate empty.':'此关卡暂无规则。可以添加规则，也可以保持为空。','On':'开启','Action':'动作','After match':'命中后','Continue':'继续','Stop later rules':'停止后续规则','Skip file':'跳过文件','Require review':'需要审核','Rule name':'规则名称','Enable this rule':'启用此规则','Action options (JSON)':'动作选项（JSON）',
  'Run processor':'运行处理器','Extract all dates':'提取全部日期','Clean file name':'清理文件名','Remove number patterns':'删除数字规则','Inherit parent name':'继承父目录名称','Render name template':'生成名称模板','Keep in place':'保持原位','Move':'移动','Archive':'归档','Quarantine':'隔离','LIVE INSPECTOR':'实时检查','Impact and risk':'影响与风险','Real files remain unchanged until a frozen plan is confirmed.':'冻结计划并确认前，真实文件保持不变。','Example relative path':'示例相对路径','Test selected rule':'测试所选规则','Conflict policy':'冲突策略','Append number':'追加序号','Skip':'跳过','Stop plan':'停止计划','Workflow template imported':'工作流模板已导入','Workflow saved':'工作流已保存',
  'Match conditions':'匹配条件','Run this rule only when these conditions match.':'仅当这些条件匹配时运行本规则。','Add condition':'添加条件','Condition logic':'条件逻辑','Match all':'全部匹配','Match any':'任一匹配','Match none':'全部不匹配','No conditions — applies to every file.':'没有条件——适用于所有文件。','Remove condition':'删除条件','Action settings':'动作设置','Processor':'处理器','Words to remove':'需要删除的词','Put all extracted dates first':'将提取的全部日期放到最前','Normalize spaces and separators':'规范空格和分隔符','Allowed number-removal patterns':'允许删除的数字规则','Separator':'分隔符','Name template':'名称模板','Destination folder template':'目标文件夹模板','Missing information':'缺少信息时','Keep original folder':'保持原文件夹','No extra settings required.':'无需额外设置。','Developer options (JSON)':'开发者选项（JSON）','Extract date':'提取日期','Extract identifier':'提取编号','Extract sequence':'提取集数','Extract quality':'提取清晰度','Extract language':'提取语言','Classify extension':'按扩展名分类','Normalize name':'规范名称',
  'filename':'文件名','name':'名称','extension':'扩展名','relative path':'相对路径','parent path':'父目录路径','parent name':'父目录名称','size':'大小','mtime ns':'修改时间','is empty':'是否为空','category':'分类','language':'语言','resolution':'清晰度','contains':'包含','not contains':'不包含','equals':'等于','not equals':'不等于','starts with':'开头为','ends with':'结尾为','regex':'正则表达式','in':'属于列表','greater than':'大于','less than':'小于','is true':'是','is false':'否',
  'Normalize names without moving files.':'规范名称但不移动文件。','Archive by year and month':'按年月归档','Extract dates and archive within the source.':'提取日期并在当前数据源内归档。','Inherit parent folder':'继承父目录名称','Prefix names with the direct parent folder.':'将直属父目录名称加到文件名前。','Image date archive':'图片按日期归档','Archive dated images by year and month.':'将含日期的图片按年月归档。','Media organization':'影视和关联文件整理','Extract metadata and organize known media types.':'提取信息并整理常见媒体文件。','Classify and organize common media and sidecar files.':'分类整理常见媒体及关联字幕文件。','Downloads cleanup':'下载目录清理','Clean download names and review incomplete files.':'清理下载名称并审核未完成文件。','Ads and temporary file quarantine':'广告与临时文件隔离','Quarantine configured junk candidates for review.':'将匹配的垃圾候选隔离并审核。','Duplicate file review':'重复文件审核','Send duplicate candidates to review.':'将重复候选送入审核。','Send indexed duplicate candidates to review.':'将索引出的重复候选送入审核。',
  'Junk rules':'垃圾规则','JUNK RULE LIBRARY':'垃圾规则库','RULE PACKS':'规则包','junk.rules_load_failed':'垃圾规则加载失败','junk.rules_invalid_json':'规则 JSON 无效',
  'Inspect small text':'检查小文本','Small text inspection':'小文本检查','Small text inspection scan queued for':'小文本检查已加入队列：',
  'Simulate full workflow':'模拟完整工作流','Final action':'最终动作','Review required':'需要审核','processing steps':'个处理步骤','Workflow diagnostics':'工作流诊断','errors':'个错误','warnings':'个警告',
  'Quick rule cards':'快捷规则卡','Insert common business rules, then adjust their options.':'插入常用业务规则，然后按需要调整参数。','Extract and prepend all dates':'提取并前置全部日期','Remove advertisement words':'删除广告词','Inherit parent folder name':'继承父目录名称','Archive by earliest year and month':'按最早日期年月归档','Detect and quarantine BT advertisements':'检测并隔离 BT 广告',
  'WORKFLOW ENGINE 3.0':'工作流引擎 3.0','Quick':'快速模式','Standard':'标准模式','Expert':'专家模式','Scope switches':'范围开关','Include subdirectories':'包含子目录','Ignore hidden paths':'忽略隐藏路径','Include extensions':'包含扩展名','Exclude paths':'排除路径','Undo':'撤销','Redo':'重做','Draft saved locally':'草稿已保存在本地',
}

export const messages = {
  en: { appName: 'File Curator', nav: { dashboard: 'Dashboard', sources: 'Sources', files: 'File browser', pipeline: 'Pipeline', junk: 'Junk rules', review: 'Review center', preview: 'Virtual preview', execution: 'Execution', history: 'History', settings: 'Settings' }, actions: { scan: 'Scan now', preview: 'Preview plan', execute: 'Execute plan', save: 'Save changes', back: 'Back' } },
  'zh-CN': { appName: 'File Curator', nav: { dashboard: '仪表盘', sources: '数据源', files: '文件浏览器', pipeline: '处理流程', junk: '垃圾规则', review: '审核中心', preview: '虚拟预览', execution: '执行', history: '历史记录', settings: '设置' }, actions: { scan: '立即扫描', preview: '预览计划', execute: '执行计划', save: '保存更改', back: '返回' } },
} as const

export type Locale = keyof typeof messages

export function translate(locale:Locale,value:string):string {
  if(locale==='en') return value
  if(zh[value]) return zh[value]
  return value
    .replace(/^Every (\d+) minutes$/, '每 $1 分钟')
    .replace(/^(\d+) rules$/, '$1 条规则')
    .replace(/^(\d+) total rules$/, '共 $1 条规则')
    .replace(/^(\d+) stored revisions$/, '已保存 $1 个修订')
    .replace(/^(\d+) files$/, '$1 个文件')
    .replace(/^(\d+) groups$/, '$1 个文件组')
    .replace(/^(\d+) members$/, '$1 个成员')
    .replace(/^(\d+)% confidence$/, '置信度 $1%')
    .replace(/^(\d+)[–-](\d+) of (\d+)$/, '第 $1–$2 项，共 $3 项')
    .replace(/^Revision (\d+)$/, '修订 $1')
    .replace(/^Run ([^ ]+) · rev (\d+)$/, '运行 $1 · 修订 $2')
    .replace(/^Rev (\d+) → (\d+)$/, '修订 $1 → $2')
    .replace(/^Added: (.*)$/, '新增：$1')
    .replace(/^Removed: (.*)$/, '移除：$1')
    .replace(/^Changed: (.*)$/, '更改：$1')
    .replace(/^v([^ ]+) · ([^·]+) · score (.+)$/, (_match, version:string, safety:string, weight:string) => `v${version} · ${translate(locale, safety.trim())} · 分数 ${weight}`)
    .replace(/^(.+) options \(JSON\)$/, (_match, processor:string) => `${translate(locale, processor)} 选项（JSON）`)
    .replace(/^(\d+) succeeded · (\d+) failed · (\d+) skipped$/, '成功 $1 · 失败 $2 · 跳过 $3')
    .replace(/^(\d+) reversible · ready$/, '$1 项可回滚操作 · 就绪')
    .replace(/^(\d+) reversible · conflict$/, '$1 项可回滚操作 · 存在冲突')
    .replace(/^(\d+) successful operations$/, '$1 项成功操作')
    .replace(/^(\d+) operations$/, '$1 项操作')
    .replace(/^v([\d.]+) · local instance$/, 'v$1 · 本地实例')
    .replace(/^Toggle (.+)$/, (_match, processor:string) => `切换${translate(locale, processor.replaceAll('_', ' '))}`)
    .replace(/^Batch (pause|cancel|retry) requested$/, (_match, action:string) => `已请求${action === 'pause' ? '暂停' : action === 'cancel' ? '取消' : '重试'}批次`)
    .replace(/^Notifications (granted|denied|default)$/, (_match, permission:string) => `浏览器通知：${permission === 'granted' ? '已允许' : permission === 'denied' ? '已拒绝' : '未决定'}`)
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
