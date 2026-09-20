import { Thermometer } from 'lucide-react'
import type { TemperatureState } from '../../types'
import { Metric } from '../ui/Metric'
import { Sparkline } from '../ui/Sparkline'
import { StateChip } from '../ui/StateChip'
import type { ChipTone } from '../ui/StateChip'
import { Tile } from '../ui/Tile'

const statusTone: Record<TemperatureState['status'], ChipTone> = {
  ok: 'live',
  warm: 'warn',
  overheat: 'alert',
}

interface TemperaturePanelProps {
  temperature: TemperatureState
  className?: string
}

export function TemperaturePanel({ temperature, className = '' }: TemperaturePanelProps) {
  const tone =
    temperature.status === 'overheat' ? 'alert' : temperature.status === 'warm' ? 'warn' : 'live'

  return (
    <Tile
      title="Ambient Temp"
      icon={Thermometer}
      className={className}
      actions={
        <StateChip
          label={temperature.status}
          tone={statusTone[temperature.status]}
          pulse={temperature.status === 'overheat'}
        />
      }
    >
      <div className="flex h-full flex-col justify-between gap-1">
        <Metric
          label="Reading"
          value={temperature.celsius.toFixed(1)}
          unit="°C"
          size="headline"
          tone={tone}
        />
        <Sparkline
          values={temperature.history}
          min={18}
          max={temperature.overheatC + 8}
          tone={tone}
          className="h-7"
        />
        <p className="text-[10px] tracking-[0.1em] text-ink-faint uppercase">
          Warm {temperature.warmC}° · Overheat {temperature.overheatC}°
        </p>
      </div>
    </Tile>
  )
}
