import { Wifi } from 'lucide-react'
import { CAMERA_RESOLUTION } from '../../data/mockTelemetry'
import type { DepthState } from '../../types'
import { Metric } from '../ui/Metric'
import { StateChip } from '../ui/StateChip'
import { Tile } from '../ui/Tile'

interface DepthLinkProps {
  depth: DepthState
  className?: string
}

export function DepthLink({ depth, className = '' }: DepthLinkProps) {
  const stale = depth.ageS > depth.stalenessLimitS
  const aging = !stale && depth.ageS > depth.stalenessLimitS / 2

  return (
    <Tile
      title="Depth Link"
      icon={Wifi}
      className={className}
      actions={
        <StateChip
          label={stale ? 'Stale' : aging ? 'Lagging' : 'Live'}
          tone={stale ? 'alert' : aging ? 'warn' : 'live'}
          pulse={!stale && !aging}
        />
      }
    >
      <div className="flex h-full flex-col justify-between gap-2.5">
        <div className="grid grid-cols-3 gap-2">
          <Metric label="frame_id" value={depth.frameId.toLocaleString()} />
          <Metric label="Inference" value={depth.processingMs} unit="ms" />
          <Metric label="Queue age" value={depth.serverFrameAgeMs} unit="ms" />
          <Metric
            label="Reply age"
            value={depth.ageS.toFixed(2)}
            unit="s"
            tone={stale ? 'alert' : aging ? 'warn' : 'default'}
          />
          <Metric label="Capture" value={depth.fps} unit="fps" />
          <Metric label="Frame" value={CAMERA_RESOLUTION} tone="faint" />
        </div>

        <p className="truncate font-mono text-[10px] text-ink-faint">
          {depth.host}:{depth.port} · stale &gt; {depth.stalenessLimitS.toFixed(1)}s
        </p>
      </div>
    </Tile>
  )
}
