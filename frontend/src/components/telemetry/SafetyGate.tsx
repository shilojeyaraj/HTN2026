import { ShieldAlert } from 'lucide-react'
import type { SafetyState } from '../../types'
import { Metric } from '../ui/Metric'
import { StateChip } from '../ui/StateChip'
import { Tile } from '../ui/Tile'

interface SafetyGateProps {
  safety: SafetyState
  className?: string
}

export function SafetyGate({ safety, className = '' }: SafetyGateProps) {
  const vetoed = safety.status === 'VETO'
  const last = safety.recent[0]

  return (
    <Tile
      title="Safety Gate"
      icon={ShieldAlert}
      className={className}
      actions={
        <StateChip
          label={safety.status}
          tone={vetoed ? 'alert' : 'live'}
          pulse={vetoed}
        />
      }
    >
      <div className="flex h-full flex-col justify-between gap-2">
        <Metric
          label="SayCan gate"
          value={vetoed ? 'Blocking' : 'Passing'}
          size="headline"
          tone={vetoed ? 'alert' : 'live'}
        />
        <p className="text-[10px] leading-relaxed tracking-[0.1em] text-ink-faint uppercase">
          {vetoed ? (
            <span className="text-alert">{safety.reason}</span>
          ) : (
            <>
              <span className="font-mono text-ink-muted">{safety.gatedVerbs.join(', ')}</span> under{' '}
              <span className="font-mono text-ink-muted">{safety.minClearanceM.toFixed(2)} m</span>
            </>
          )}
          <br />
          {safety.recent.length} veto{safety.recent.length === 1 ? '' : 'es'}
          {last && <span className="font-mono"> · {last.clock}</span>}
        </p>
      </div>
    </Tile>
  )
}
