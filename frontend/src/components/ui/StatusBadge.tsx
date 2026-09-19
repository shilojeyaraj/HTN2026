import { statusLabels } from '../../data/mockData'
import type { EncounterStatus } from '../../types'

const statusStyles: Record<EncounterStatus, string> = {
  rescued: 'border-live/30 bg-live/10 text-live',
  located: 'border-accent/30 bg-accent/10 text-accent',
  'no-contact': 'border-warn/30 bg-warn/10 text-warn',
}

interface StatusBadgeProps {
  status: EncounterStatus
  className?: string
}

export function StatusBadge({ status, className = '' }: StatusBadgeProps) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded border px-2 py-1 text-[10px] font-semibold tracking-[0.12em] uppercase ${statusStyles[status]} ${className}`}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {statusLabels[status]}
    </span>
  )
}
