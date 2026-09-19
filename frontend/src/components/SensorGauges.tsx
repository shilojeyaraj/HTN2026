import { Activity, Thermometer, Volume2, Cpu } from 'lucide-react'
import type { SensorSnapshot } from '../types'
import { Panel } from './ui/Panel'

interface SensorGaugesProps {
  sensors: SensorSnapshot | null
}

function tempColor(celsius: number): string {
  if (celsius >= 60) return '#ef4444'
  if (celsius >= 40) return '#f59e0b'
  return '#22c55e'
}

function tempLabel(status: string): string {
  if (status === 'overheat') return 'OVERHEAT'
  if (status === 'warm') return 'WARM'
  return 'OK'
}

function dbColor(db: number): string {
  if (db >= 80) return '#ef4444'
  if (db >= 60) return '#f59e0b'
  return '#38bdf8'
}

function Gauge({
  icon: Icon,
  label,
  value,
  unit,
  color,
  status,
  max,
}: {
  icon: typeof Thermometer
  label: string
  value: number
  unit: string
  color: string
  status?: string
  max: number
}) {
  const pct = Math.min(100, (value / max) * 100)
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <Icon className="h-4 w-4" style={{ color }} strokeWidth={2} />
        <span className="text-[11px] font-semibold tracking-[0.12em] text-ink-faint uppercase">
          {label}
        </span>
        {status && (
          <span
            className="ml-auto rounded px-1.5 py-0.5 text-[10px] font-bold tracking-wider"
            style={{ color, backgroundColor: `${color}15` }}
          >
            {status}
          </span>
        )}
      </div>
      <div className="flex items-baseline gap-1">
        <span className="font-mono text-2xl font-bold" style={{ color }}>
          {value.toFixed(1)}
        </span>
        <span className="font-mono text-sm text-ink-faint">{unit}</span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-line/30">
        <div
          className="h-full rounded-full transition-all duration-300"
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
      </div>
    </div>
  )
}

export function SensorGauges({ sensors }: SensorGaugesProps) {
  const temp = sensors?.temperature ?? { celsius: 22.0, status: 'ok' }
  const audio = sensors?.audio ?? { db: 35.0, event: null }
  const gyro = sensors?.gyro ?? { pitch_deg: 0, roll_deg: 0, tipped: false, bump: false }

  const tempC = temp.celsius
  const tempCol = tempColor(tempC)
  const tempStat = tempLabel(temp.status)

  const db = audio.db
  const dbCol = dbColor(db)
  const audioStatus = audio.event ? audio.event.kind.toUpperCase() : null

  const tilt = Math.max(Math.abs(gyro.pitch_deg), Math.abs(gyro.roll_deg))
  const tiltCol = gyro.tipped ? '#ef4444' : tilt > 15 ? '#f59e0b' : '#22c55e'
  const tiltStatus = gyro.tipped ? 'TIPPED' : gyro.bump ? 'BUMP' : tilt > 15 ? 'TILTED' : 'STABLE'

  return (
    <Panel title="Sensor Array" icon={Activity}>
      <div className="grid grid-cols-3 gap-5 px-5 py-4">
        <Gauge
          icon={Thermometer}
          label="Temp"
          value={tempC}
          unit="°C"
          color={tempCol}
          status={tempStat}
          max={100}
        />
        <Gauge
          icon={Volume2}
          label="Audio"
          value={db}
          unit="dB"
          color={dbCol}
          status={audioStatus ?? undefined}
          max={120}
        />
        <Gauge
          icon={Cpu}
          label="Tilt"
          value={tilt}
          unit="°"
          color={tiltCol}
          status={tiltStatus}
          max={45}
        />
      </div>
    </Panel>
  )
}
