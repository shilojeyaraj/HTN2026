import { Satellite } from 'lucide-react'
import type { GpsState } from '../../types'
import { Metric } from '../ui/Metric'
import { StateChip } from '../ui/StateChip'
import { Tile } from '../ui/Tile'

interface GpsPanelProps {
  gps: GpsState
  className?: string
}

/** No backend module reads GPS yet; CLAUDE.md only lists the hardware. */
export function GpsPanel({ gps, className = '' }: GpsPanelProps) {
  return (
    <Tile
      title="GPS"
      icon={Satellite}
      className={className}
      actions={
        <StateChip label={gps.fix} tone={gps.fix === '3D' ? 'live' : gps.fix === '2D' ? 'warn' : 'alert'} />
      }
    >
      <div className="flex h-full flex-col justify-between gap-2">
        <div className="flex flex-col gap-1">
          <Metric label="Latitude" value={gps.latitude.toFixed(6)} />
          <Metric label="Longitude" value={gps.longitude.toFixed(6)} />
        </div>
        <div className="flex items-end justify-between gap-2">
          <Metric label="Sats" value={gps.satellites} />
          <Metric label="HDOP" value={gps.hdop.toFixed(2)} />
          <span className="text-[10px] tracking-[0.1em] text-ink-faint uppercase">Unwired</span>
        </div>
      </div>
    </Tile>
  )
}
