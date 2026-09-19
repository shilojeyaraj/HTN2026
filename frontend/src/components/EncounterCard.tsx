import { ArrowRight, CalendarClock, MapPin, Timer } from 'lucide-react'
import type { Encounter } from '../types'
import { StatusBadge } from './ui/StatusBadge'

interface EncounterCardProps {
  encounter: Encounter
  onView: (encounter: Encounter) => void
}

export function EncounterCard({ encounter, onView }: EncounterCardProps) {
  return (
    <article className="group flex flex-col gap-4 rounded-lg border border-line bg-surface p-5 transition-colors hover:border-line-strong hover:bg-raised">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <span className="font-mono text-sm tracking-wider text-ink">{encounter.id}</span>
        <StatusBadge status={encounter.status} />
      </div>

      <div className="flex flex-col gap-2.5 text-sm">
        <span className="flex items-start gap-2.5 text-ink-muted">
          <MapPin className="mt-0.5 h-4 w-4 shrink-0 text-ink-faint" strokeWidth={2} />
          {encounter.location}
        </span>
        <span className="flex items-center gap-2.5 text-ink-muted">
          <CalendarClock className="h-4 w-4 shrink-0 text-ink-faint" strokeWidth={2} />
          {encounter.timestamp}
        </span>
        <span className="flex items-center gap-2.5 text-ink-muted">
          <Timer className="h-4 w-4 shrink-0 text-ink-faint" strokeWidth={2} />
          <span className="font-mono">{encounter.duration}</span>
        </span>
      </div>

      <button
        type="button"
        onClick={() => onView(encounter)}
        className="mt-auto flex items-center justify-center gap-2 rounded border border-line-strong px-3 py-2 text-xs font-semibold tracking-[0.12em] text-ink-muted uppercase transition-colors group-hover:border-accent/40 group-hover:text-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
      >
        View
        <ArrowRight className="h-3.5 w-3.5" strokeWidth={2} />
      </button>
    </article>
  )
}
