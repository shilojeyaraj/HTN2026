import { Zap } from 'lucide-react'
import type { ReflexState } from '../../types'
import { Metric } from '../ui/Metric'
import { StateChip } from '../ui/StateChip'
import { Tile } from '../ui/Tile'

interface ReflexMonitorProps {
  reflex: ReflexState
  className?: string
}

export function ReflexMonitor({ reflex, className = '' }: ReflexMonitorProps) {
  const near = reflex.clearanceM < reflex.stopDistanceM * 2

  return (
    <Tile
      title="Reflex Loop"
      icon={Zap}
      className={className}
      actions={
        <StateChip
          label={reflex.blocked ? 'Stop' : 'Clear'}
          tone={reflex.blocked ? 'alert' : 'live'}
          pulse={reflex.blocked}
        />
      }
    >
      <div className="flex h-full flex-col justify-between gap-2">
        <Metric
          label="Front clearance"
          value={reflex.clearanceM.toFixed(2)}
          unit="m"
          size="headline"
          tone={reflex.blocked ? 'alert' : near ? 'warn' : 'live'}
        />
        <p className="text-[10px] leading-relaxed tracking-[0.1em] text-ink-faint uppercase">
          Halts under{' '}
          <span className="font-mono text-ink-muted">{reflex.stopDistanceM.toFixed(2)} m</span>
          <br />
          {reflex.hz} Hz · onboard · no cloud
        </p>
      </div>
    </Tile>
  )
}
