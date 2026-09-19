import { Clock, MapPin, Mic, Radar } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'
import type { ActiveEncounter } from '../types'
import { Panel } from './ui/Panel'
import { StatusBadge } from './ui/StatusBadge'

interface CurrentEncounterProps {
  encounter: ActiveEncounter
  className?: string
}

export function CurrentEncounter({ encounter, className = '' }: CurrentEncounterProps) {
  return (
    <Panel title="Current Encounter" icon={Radar} className={className}>
      <div className="flex flex-col gap-5 px-5 py-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <span className="font-mono text-lg tracking-wider text-ink">{encounter.id}</span>
          <StatusBadge status={encounter.status} />
        </div>

        <dl className="flex flex-col gap-4">
          <Field icon={MapPin} label="Location">
            {encounter.location}
          </Field>
          <Field icon={Clock} label="Started">
            <span className="font-mono">{encounter.startedAt}</span>
            <span className="text-ink-faint"> · elapsed {encounter.duration}</span>
          </Field>
        </dl>

        <div className="flex items-center gap-2.5 rounded border border-live/20 bg-live/5 px-3.5 py-3">
          <Mic className="h-4 w-4 text-live" strokeWidth={2} />
          <span className="text-xs font-medium tracking-[0.12em] text-live uppercase">
            Microphone active
          </span>
          <span className="animate-blip ml-auto h-2 w-2 rounded-full bg-live" />
        </div>
      </div>
    </Panel>
  )
}

interface FieldProps {
  icon: LucideIcon
  label: string
  children: ReactNode
}

function Field({ icon: Icon, label, children }: FieldProps) {
  return (
    <div>
      <dt className="mb-1.5 flex items-center gap-2 text-[11px] font-semibold tracking-[0.14em] text-ink-faint uppercase">
        <Icon className="h-3.5 w-3.5" strokeWidth={2} />
        {label}
      </dt>
      <dd className="text-sm leading-relaxed text-ink">{children}</dd>
    </div>
  )
}
