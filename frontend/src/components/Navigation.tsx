import { Activity, BrainCircuit, History, LayoutDashboard } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import type { Tab } from '../types'

const tabs: { id: Tab; label: string; icon: LucideIcon }[] = [
  { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { id: 'telemetry', label: 'Telemetry', icon: Activity },
  { id: 'brain', label: 'Brain', icon: BrainCircuit },
  { id: 'encounters', label: 'Encounters', icon: History },
]

interface NavigationProps {
  active: Tab
  onChange: (tab: Tab) => void
}

export function Navigation({ active, onChange }: NavigationProps) {
  return (
    <nav className="border-b border-line bg-base">
      <div className="mx-auto flex max-w-[1600px] gap-1 px-6 lg:px-10">
        {tabs.map(({ id, label, icon: Icon }) => {
          const isActive = id === active
          return (
            <button
              key={id}
              type="button"
              onClick={() => onChange(id)}
              aria-current={isActive ? 'page' : undefined}
              className={`-mb-px flex items-center gap-2 border-b-2 px-4 py-3.5 text-sm font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent ${
                isActive
                  ? 'border-accent text-ink'
                  : 'border-transparent text-ink-faint hover:text-ink-muted'
              }`}
            >
              <Icon className="h-4 w-4" strokeWidth={2} />
              {label}
            </button>
          )
        })}
      </div>
    </nav>
  )
}
