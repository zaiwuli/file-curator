import { Languages } from 'lucide-react'
import type { Locale } from '../i18n'

export function Topbar({ title, state, locale, onLocale }: { title: string; state: 'loading'|'live'|'offline'; locale: Locale; onLocale: () => void }) {
  return <header className="topbar"><div className="breadcrumb"><span>Workspace</span><b>/</b><strong>{title}</strong></div><div className="top-actions"><div className="connection"><span className={`status-dot ${state}`}/>{state === 'live' ? 'API connected' : state === 'loading' ? 'Connecting to API' : 'API unavailable'}</div><button className="icon-button" title="Toggle language" onClick={onLocale}><Languages size={15}/><span className="sr-only">{locale === 'en' ? 'Switch to Chinese' : 'Switch to English'}</span></button><div className="avatar">FC</div></div></header>
}
