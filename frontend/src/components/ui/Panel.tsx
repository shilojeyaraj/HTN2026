import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'

interface PanelProps {
  title?: string
  icon?: LucideIcon
  actions?: ReactNode
  children: ReactNode
  className?: string
  bodyClassName?: string
}

export function Panel({
  title,
  icon: Icon,
  actions,
  children,
  className = '',
  bodyClassName = '',
}: PanelProps) {
  return (
    <section
      className={`flex flex-col overflow-hidden rounded-lg border border-line bg-surface shadow-lg shadow-black/25 ${className}`}
    >
      {title && (
        <header className="flex items-center justify-between gap-4 border-b border-line px-5 py-3.5">
          <div className="flex items-center gap-2.5">
            {Icon && <Icon className="h-4 w-4 text-ink-faint" strokeWidth={2} />}
            <h2 className="text-xs font-semibold tracking-[0.14em] text-ink-muted uppercase">
              {title}
            </h2>
          </div>
          {actions}
        </header>
      )}
      <div className={`flex-1 ${bodyClassName}`}>{children}</div>
    </section>
  )
}
