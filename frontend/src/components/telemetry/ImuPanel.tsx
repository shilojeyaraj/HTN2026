import { Compass } from 'lucide-react'
import type { GyroState } from '../../types'
import { Metric } from '../ui/Metric'
import { StateChip } from '../ui/StateChip'
import { Tile } from '../ui/Tile'

const TIP_LIMIT_DEG = 45

interface ImuPanelProps {
  gyro: GyroState
  className?: string
}

export function ImuPanel({ gyro, className = '' }: ImuPanelProps) {
  // Pitch shifts the horizon, roll rotates it, same as an attitude indicator.
  const pitchOffset = Math.max(-26, Math.min(26, gyro.pitchDeg * 0.5))
  const color = gyro.tipped ? '#ef4444' : Math.abs(gyro.pitchDeg) > 20 ? '#f59e0b' : '#38bdf8'

  return (
    <Tile
      title="IMU / Attitude"
      icon={Compass}
      className={className}
      actions={
        <>
          {gyro.bump && <StateChip label="Bump" tone="warn" />}
          <StateChip
            label={gyro.tipped ? 'Tipped' : 'Level'}
            tone={gyro.tipped ? 'alert' : 'live'}
            pulse={gyro.tipped}
          />
        </>
      }
    >
      <div className="flex h-full items-center gap-3">
        <svg
          className="h-[68px] w-[68px] shrink-0"
          viewBox="0 0 80 80"
          role="img"
          aria-label="Attitude indicator"
        >
          <defs>
            <clipPath id="imu-clip">
              <circle cx="40" cy="40" r="31" />
            </clipPath>
          </defs>
          <circle cx="40" cy="40" r="31" fill="#0b1118" stroke="#2a3b4e" strokeWidth="1.2" />
          <g clipPath="url(#imu-clip)">
            <g transform={`rotate(${-gyro.rollDeg} 40 40) translate(0 ${pitchOffset})`}>
              <rect x="0" y="40" width="80" height="60" fill={color} opacity="0.14" />
              <line x1="0" y1="40" x2="80" y2="40" stroke={color} strokeWidth="1.4" />
              {[-16, -8, 8, 16].map((offset) => (
                <line
                  key={offset}
                  x1={offset % 16 === 0 ? 30 : 34}
                  y1={40 + offset}
                  x2={offset % 16 === 0 ? 50 : 46}
                  y2={40 + offset}
                  stroke="#2a3b4e"
                  strokeWidth="0.9"
                />
              ))}
            </g>
          </g>
          <path d="M 26 40 L 35 40 M 45 40 L 54 40" stroke="#f1f5f9" strokeWidth="1.4" />
          <circle cx="40" cy="40" r="1.6" fill="#f1f5f9" />
        </svg>

        <div className="grid min-w-0 flex-1 grid-cols-2 gap-2">
          <Metric
            label="Pitch"
            value={gyro.pitchDeg.toFixed(1)}
            unit="°"
            tone={gyro.tipped ? 'alert' : 'default'}
          />
          <Metric label="Roll" value={gyro.rollDeg.toFixed(1)} unit="°" />
          <Metric label="accel_z" value={gyro.accelZG.toFixed(2)} unit="g" />
          <Metric label="Tip limit" value={TIP_LIMIT_DEG} unit="°" tone="faint" />
        </div>
      </div>
    </Tile>
  )
}
