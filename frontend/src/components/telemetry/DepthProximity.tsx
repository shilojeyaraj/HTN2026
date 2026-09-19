import { Layers } from 'lucide-react'
import type { DepthState } from '../../types'
import { MeterBar } from '../ui/MeterBar'
import { StateChip } from '../ui/StateChip'
import type { ChipTone } from '../ui/StateChip'
import { Tile } from '../ui/Tile'

const OBSTACLE_THRESHOLD = 0.5

const statusTone: Record<DepthState['status'], ChipTone> = {
  ok: 'live',
  uncertain: 'warn',
  error: 'alert',
  preview: 'muted',
}

interface DepthProximityProps {
  depth: DepthState
  className?: string
}

export function DepthProximity({ depth, className = '' }: DepthProximityProps) {
  const regions: { key: 'left' | 'center' | 'right'; bearing: string }[] = [
    { key: 'left', bearing: '-30°' },
    { key: 'center', bearing: '0°' },
    { key: 'right', bearing: '+30°' },
  ]

  return (
    <Tile
      title="Monocular Depth"
      icon={Layers}
      className={className}
      actions={<StateChip label={depth.status} tone={statusTone[depth.status]} />}
    >
      <div className="flex h-full flex-col justify-between gap-2">
        {depth.relativeProximity ? (
          regions.map(({ key, bearing }) => {
            const score = depth.relativeProximity![key]
            const preferred = depth.preferredDirection === key
            return (
              <MeterBar
                key={key}
                label={`${key} ${bearing}`}
                value={score}
                valueLabel={score.toFixed(2)}
                threshold={OBSTACLE_THRESHOLD}
                tone={score > OBSTACLE_THRESHOLD ? 'alert' : preferred ? 'live' : 'accent'}
              />
            )
          })
        ) : (
          <p className="flex flex-1 items-center text-[11px] text-warn">
            No proximity scores in the last reply. Detections fail closed.
          </p>
        )}

        <p className="flex items-center justify-between gap-2 truncate text-[10px] tracking-[0.1em] text-ink-faint uppercase">
          <span>
            Prefer{' '}
            <span className="font-mono text-ink">{depth.preferredDirection ?? 'unknown'}</span>
          </span>
          <span>Advisory only · relative</span>
        </p>
      </div>
    </Tile>
  )
}
