import { CircleDot } from 'lucide-react'
import type { EncoderState } from '../../types'
import { MeterBar } from '../ui/MeterBar'
import { Metric } from '../ui/Metric'
import { StateChip } from '../ui/StateChip'
import { Tile } from '../ui/Tile'

const MAX_MPS = 0.4

interface EncodersProps {
  encoder: EncoderState
  className?: string
}

export function Encoders({ encoder, className = '' }: EncodersProps) {
  return (
    <Tile
      title="Wheel Encoders"
      icon={CircleDot}
      className={className}
      actions={
        <>
          <span className="font-mono text-[10px] text-ink-faint">
            {encoder.ticksPerMeter}/m
          </span>
          {encoder.slipDetected ? (
            <StateChip label="Slip" tone="warn" pulse />
          ) : (
            <StateChip label="Tracking" tone="live" />
          )}
        </>
      }
    >
      <div className="flex h-full flex-col justify-between gap-2">
        <div className="grid grid-cols-2 gap-2">
          <Metric label="Left ticks" value={encoder.leftTicksTotal.toLocaleString()} />
          <Metric label="Right ticks" value={encoder.rightTicksTotal.toLocaleString()} />
        </div>

        <MeterBar
          label="Commanded"
          value={Math.abs(encoder.commandedVelocityMps) / MAX_MPS}
          valueLabel={`${encoder.commandedVelocityMps.toFixed(2)} m/s`}
          tone="muted"
        />
        <MeterBar
          label="Estimated"
          value={Math.abs(encoder.estimatedVelocityMps) / MAX_MPS}
          valueLabel={`${encoder.estimatedVelocityMps.toFixed(2)} m/s`}
          tone={encoder.slipDetected ? 'warn' : 'accent'}
        />
      </div>
    </Tile>
  )
}
