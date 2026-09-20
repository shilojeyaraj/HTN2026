import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'

interface TileProps {
  title: string
  icon?: LucideIcon
  actions?: ReactNode
  children: ReactNode
  className?: string
  bodyClassName?: string
}

/**
 * Compact sibling of Panel for the dense telemetry grids. Same shell, tighter
 * header and padding so a tile reads at a glance without scrolling.
 */
export function Tile({
  title,
  icon: Icon,
  actions,
  children,
  className = '',
  bodyClassName = 'px-3 py-2.5',
}: TileProps) {
  return (
    <section
      className={`flex min-h-0 flex-col overflow-hidden rounded-lg border border-line bg-surface shadow-lg shadow-black/25 ${className}`}
    >
      <header className="flex shrink-0 items-center justify-between gap-2 border-b border-line px-3 py-2">
        <div className="flex min-w-0 items-center gap-2">
          {Icon && <Icon className="h-3.5 w-3.5 shrink-0 text-ink-faint" strokeWidth={2} />}
          <h2 className="truncate text-[10px] font-semibold tracking-[0.14em] text-ink-muted uppercase">
            {title}
          </h2>
        </div>
        {actions && <div className="flex shrink-0 items-center gap-1.5">{actions}</div>}
      </header>
      <div className={`min-h-0 flex-1 ${bodyClassName}`}>{children}</div>
    </section>
  )
}
