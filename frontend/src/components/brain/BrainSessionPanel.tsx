import { Network } from 'lucide-react'
import type { BrainSession } from '../../types'
import { MeterBar } from '../ui/MeterBar'
import { Metric } from '../ui/Metric'
import { StateChip } from '../ui/StateChip'
import type { ChipTone } from '../ui/StateChip'
import { Tile } from '../ui/Tile'

const statusTone: Record<BrainSession['status'], ChipTone> = {
  idle: 'muted',
  thinking: 'accent',
  requires_action: 'warn',
}

interface BrainSessionPanelProps {
  session: BrainSession
  className?: string
}

export function BrainSessionPanel({ session, className = '' }: BrainSessionPanelProps) {
  return (
    <Tile
      title="Backboard Session"
      icon={Network}
      className={className}
      actions={
        <StateChip
          label={session.status.replace(/_/g, ' ')}
          tone={statusTone[session.status]}
          pulse={session.status !== 'idle'}
        />
      }
    >
      <div className="flex h-full flex-col justify-between gap-2">
        <div className="grid grid-cols-2 gap-2">
          <Metric label="Planner" value={session.plannerModel} />
          <Metric label="Vision" value={session.visionModel} />
          <Metric label="thread_id" value={session.threadId} tone="faint" />
          <Metric label="assistant_id" value={session.assistantId} tone="faint" />
        </div>

        <MeterBar
          label="Tool rounds"
          value={session.toolRounds / session.maxToolRounds}
          valueLabel={`${session.toolRounds} / ${session.maxToolRounds}`}
          tone={session.toolRounds >= session.maxToolRounds ? 'warn' : 'accent'}
        />

        <p className="truncate text-[10px] tracking-[0.1em] text-ink-faint uppercase">
          provider {session.provider} · min gap {session.episodeGapS.toFixed(1)}s
        </p>
      </div>
    </Tile>
  )
}
