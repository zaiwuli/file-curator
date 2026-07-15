import { CheckCircle2, FileWarning, ShieldCheck, TriangleAlert } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api } from '../api'
import { useI18n } from '../i18n'
import type { JunkRulePack, JunkRulePackValidation } from '../types'

type Props = { notify: (message:string)=>void }

export function JunkRulesPage({notify}:Props){
  const {t}=useI18n()
  const [packs,setPacks]=useState<JunkRulePack[]>([])
  const [selected,setSelected]=useState<JunkRulePack|null>(null)
  const [text,setText]=useState('')
  const [validation,setValidation]=useState<JunkRulePackValidation|null>(null)
  useEffect(()=>{void api.junkRulePacks().then(value=>{setPacks(value);setSelected(value[0]??null);setText(JSON.stringify(value[0]??{},null,2))}).catch(()=>notify('junk.rules_load_failed'))},[notify])
  const choose=(pack:JunkRulePack)=>{setSelected(pack);setText(JSON.stringify(pack,null,2));setValidation(null)}
  const validate=async()=>{try{const value=JSON.parse(text) as unknown;setValidation(await api.validateJunkRulePack(value))}catch{notify('junk.rules_invalid_json')}}
  return <>
    <div className="page-header"><div><div className="eyebrow">{t('JUNK RULE LIBRARY')}</div><h1>{t('Junk rules')}</h1><p>{t('Use deterministic evidence to identify BT advertisements, temporary files, and suspicious attachments.')}</p></div></div>
    <div className="junk-library-layout">
      <aside className="panel junk-pack-list"><div className="section-kicker">{t('RULE PACKS')}</div>{packs.map(pack=><button key={pack.id} className={selected?.id===pack.id?'junk-pack selected':'junk-pack'} onClick={()=>choose(pack)}><ShieldCheck size={16}/><span><strong>{t(pack.name)}</strong><small>v{pack.version} · {t(`${pack.rules.length} rules`)}</small></span></button>)}</aside>
      <main className="panel junk-pack-detail">{selected&&<>
        <div className="panel-heading"><div><div className="section-kicker">{selected.id}</div><h2>{t(selected.name)}</h2></div><span className="badge green">{t(`${selected.rules.length} rules`)}</span></div>
        <p className="junk-description">{t(selected.description)}</p>
        <div className="junk-protected"><CheckCircle2 size={14}/><span>{t('Protected extensions')}: {selected.protected_extensions.join(', ')}</span></div>
        <div className="junk-rule-table"><div className="table-head"><span>{t('Rule')}</span><span>{t('Evidence')}</span><span>{t('Action')}</span><span>{t('Score')}</span></div>{selected.rules.map(rule=><div className="table-row" key={rule.id}><div><strong>{t(rule.name)}</strong><small>{t(rule.description)}</small></div><code>{[...rule.extensions,...rule.filename_contains].slice(0,4).join(', ')||t('path / size')}</code><span className={`badge ${rule.action==='quarantine'?'red':rule.action==='review'?'amber':'green'}`}>{t(rule.action)}</span><strong>{rule.score}</strong></div>)}</div>
        <div className="junk-custom-note"><strong>{t('Custom rules are saved with each workflow')}</strong><span>{t('Add Detect junk and advertisements in the Classify and group stage to enter extra keywords, extensions, and protected values.')}</span></div>
        <details className="junk-developer"><summary>{t('Import or validate a custom rule pack (JSON)')}</summary><textarea className="text-input portable-editor" value={text} onChange={event=>{setText(event.target.value);setValidation(null)}}/><button className="button secondary" onClick={()=>void validate()}><FileWarning size={13}/> {t('Validate rule pack')}</button>{validation&&<div className={validation.valid?'validation-result valid':'validation-result invalid'}>{validation.valid?<><CheckCircle2 size={14}/> {t('Rule pack is valid')}: {t(`${validation.rule_count} rules`)}</>:<><TriangleAlert size={14}/> {validation.errors.join(', ')}</>}</div>}</details>
      </>}</main>
    </div>
  </>
}
