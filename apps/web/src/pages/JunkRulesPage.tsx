import { CheckCircle2, FileWarning, ShieldCheck, TriangleAlert } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api } from '../api'
import type { JunkRulePack, JunkRulePackValidation } from '../types'

type Props = { notify: (message:string)=>void }

export function JunkRulesPage({notify}:Props){
  const [packs,setPacks]=useState<JunkRulePack[]>([])
  const [selected,setSelected]=useState<JunkRulePack|null>(null)
  const [text,setText]=useState('')
  const [validation,setValidation]=useState<JunkRulePackValidation|null>(null)
  useEffect(()=>{void api.junkRulePacks().then(value=>{setPacks(value);setSelected(value[0]??null);setText(JSON.stringify(value[0]??{},null,2))}).catch(()=>notify('junk.rules_load_failed'))},[notify])
  const choose=(pack:JunkRulePack)=>{setSelected(pack);setText(JSON.stringify(pack,null,2));setValidation(null)}
  const validate=async()=>{try{const value=JSON.parse(text) as unknown;const result=await api.validateJunkRulePack(value);setValidation(result)}catch{notify('junk.rules_invalid_json')}}
  return <><div className="page-header"><div><div className="eyebrow">JUNK RULE LIBRARY</div><h1>垃圾规则库</h1><p>用确定性证据识别 BT 广告、临时文件和可疑附件。命中后默认进入审核或隔离。</p></div></div><div className="junk-library-layout"><aside className="panel junk-pack-list"><div className="section-kicker">RULE PACKS</div>{packs.map(pack=><button key={pack.id} className={selected?.id===pack.id?'junk-pack selected':'junk-pack'} onClick={()=>choose(pack)}><ShieldCheck size={16}/><span><strong>{pack.name}</strong><small>v{pack.version} · {pack.rules.length} 条规则</small></span></button>)}</aside><main className="panel junk-pack-detail">{selected&&<><div className="panel-heading"><div><div className="section-kicker">{selected.id}</div><h2>{selected.name}</h2></div><span className="badge green">{selected.rules.length} rules</span></div><p className="junk-description">{selected.description}</p><div className="junk-protected"><CheckCircle2 size={14}/><span>保护扩展名：{selected.protected_extensions.join(', ')}</span></div><div className="junk-rule-table"><div className="table-head"><span>规则</span><span>证据</span><span>动作</span><span>分数</span></div>{selected.rules.map(rule=><div className="table-row" key={rule.id}><div><strong>{rule.name}</strong><small>{rule.description}</small></div><code>{[...rule.extensions,...rule.filename_contains].slice(0,4).join(', ')||'path / size'}</code><span className={`badge ${rule.action==='quarantine'?'red':rule.action==='review'?'amber':'green'}`}>{rule.action}</span><strong>{rule.score}</strong></div>)}</div><details className="junk-developer"><summary>导入或验证自定义规则包（JSON）</summary><textarea className="text-input portable-editor" value={text} onChange={event=>{setText(event.target.value);setValidation(null)}}/><button className="button secondary" onClick={()=>void validate()}><FileWarning size={13}/> 验证规则包</button>{validation&&<div className={validation.valid?'validation-result valid':'validation-result invalid'}>{validation.valid?<><CheckCircle2 size={14}/> 规则包有效，共 {validation.rule_count} 条规则</>:<><TriangleAlert size={14}/> {validation.errors.join(', ')}</>}</div>}</details></>}</main></div></>
}
