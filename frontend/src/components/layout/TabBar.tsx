import { useAppStore } from '@/stores/appStore'
import { TABS } from '@/lib/constants'
import { useEffect } from 'react'

export function TabBar() {
  const { activeTab, setActiveTab } = useAppStore()

  // Keyboard shortcuts
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.altKey) {
        const tab = TABS.find(t => t.shortcut === e.key)
        if (tab) { e.preventDefault(); setActiveTab(tab.id) }
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [setActiveTab])

  return (
    <nav className="flex px-5 border-b"
      style={{ background: 'var(--color-slate-card)', borderColor: 'var(--color-border)' }}>
      {TABS.map(tab => (
        <button key={tab.id} onClick={() => setActiveTab(tab.id)}
          className="px-4 py-2.5 text-[11px] font-semibold tracking-[0.1em] border-b-2 transition-all cursor-pointer bg-transparent border-x-0 border-t-0"
          style={{
            fontFamily: 'var(--font-sans)',
            color: activeTab === tab.id ? 'var(--color-arctic)' : 'var(--color-text-dim)',
            borderBottomColor: activeTab === tab.id ? 'var(--color-arctic)' : 'transparent',
          }}>
          {tab.label}
          <span className="ml-1.5 text-[9px] opacity-40">⌥{tab.shortcut}</span>
        </button>
      ))}
    </nav>
  )
}
