import { Gauge } from 'lucide-react'
import type { DriveState } from '../../types'
import { MeterBar } from '../ui/MeterBar'
import { StateChip } from '../ui/StateChip'
import type { ChipTone } from '../ui/StateChip'
import { Tile } from '../ui/Tile'

const MAX_LINEAR = 0.4
const MAX_ANGULAR = 1.2

const sourceTone: Record<DriveState['source'], ChipTone> = {
  reflex: 'alert',
  brain: 'accent',
  watchdog: 'warn',
}

const sourceNote: Record<DriveState['source'], string> = {
  reflex: 'Reflex override is winning the mux',
  brain: 'Brain intent passing through',
  watchdog: 'No fresh command, halted',
}

interface DriveStatusProps {
  drive: DriveState
  className?: string
}

export function DriveStatus({ drive, className = '' }: DriveStatusProps) {
  const watchdogRatio = drive.watchdogAgeS / drive.watchdogTimeoutS
  const watchdogTone = watchdogRatio >= 1 ? 'alert' : watchdogRatio > 0.5 ? 'warn' : 'live'

  return (
    <Tile
      title="Drive / Arbiter"
      icon={Gauge}
      className={className}
      actions={<StateChip label={drive.source} tone={sourceTone[drive.source]} pulse />}
    >
      <div className="flex h-full flex-col justify-between gap-2.5">
        <MeterBar
          label="linear.x"
          value={Math.abs(drive.linear) / MAX_LINEAR}
          valueLabel={`${drive.linear >= 0 ? '+' : ''}${drive.linear.toFixed(2)} m/s`}
          tone={drive.linear === 0 ? 'muted' : 'accent'}
        />
        <MeterBar
          label="angular.z"
          value={Math.abs(drive.angular) / MAX_ANGULAR}
          valueLabel={`${drive.angular >= 0 ? '+' : ''}${drive.angular.toFixed(2)} rad/s`}
          tone={drive.angular === 0 ? 'muted' : 'accent'}
        />
        <MeterBar
          label={`Watchdog / ${drive.watchdogTimeoutS.toFixed(1)}s`}
          value={Math.min(watchdogRatio, 1)}
          valueLabel={`${drive.watchdogAgeS.toFixed(2)} s`}
          tone={watchdogTone}
        />
        <p className="truncate text-[11px] text-ink-faint">
          {sourceNote[drive.source]} · {drive.publishHz} Hz
        </p>
      </div>
    </Tile>
  )
}
