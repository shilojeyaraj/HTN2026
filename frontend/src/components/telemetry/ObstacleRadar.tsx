import { Radar } from 'lucide-react'
import {
  GATE_CONE_DEG,
  REFLEX_STOP_DISTANCE_M,
  SAYCAN_MIN_CLEARANCE_M,
  SENSOR_RANGE_M,
} from '../../data/mockTelemetry'
import type { Detection } from '../../types'
import { StateChip } from '../ui/StateChip'
import { Tile } from '../ui/Tile'

const CX = 100
const CY = 104
const R_MAX = 92
const FOV_DEG = 60

/** Near field matters most, so radius is compressed toward the far edge. */
const radiusFor = (distanceM: number) =>
  R_MAX * Math.pow(Math.min(distanceM, SENSOR_RANGE_M) / SENSOR_RANGE_M, 0.6)

const pointAt = (distanceM: number, bearingDeg: number) => {
  const radius = radiusFor(distanceM)
  const radians = (bearingDeg * Math.PI) / 180
  return { x: CX + radius * Math.sin(radians), y: CY - radius * Math.cos(radians) }
}

const wedgePath = (halfAngleDeg: number, radius: number) => {
  const a = (-halfAngleDeg * Math.PI) / 180
  const b = (halfAngleDeg * Math.PI) / 180
  const x1 = CX + radius * Math.sin(a)
  const y1 = CY - radius * Math.cos(a)
  const x2 = CX + radius * Math.sin(b)
  const y2 = CY - radius * Math.cos(b)
  return `M ${CX} ${CY} L ${x1} ${y1} A ${radius} ${radius} 0 0 1 ${x2} ${y2} Z`
}

const arcPath = (radius: number) => {
  const a = (-FOV_DEG * Math.PI) / 180
  const b = (FOV_DEG * Math.PI) / 180
  const x1 = CX + radius * Math.sin(a)
  const y1 = CY - radius * Math.cos(a)
  const x2 = CX + radius * Math.sin(b)
  const y2 = CY - radius * Math.cos(b)
  return `M ${x1} ${y1} A ${radius} ${radius} 0 0 1 ${x2} ${y2}`
}

interface ObstacleRadarProps {
  detections: Detection[]
  blocked: boolean
  className?: string
}

export function ObstacleRadar({ detections, blocked, className = '' }: ObstacleRadarProps) {
  const nearest = detections[0]

  return (
    <Tile
      title="Obstacle Field"
      icon={Radar}
      className={className}
      bodyClassName="flex flex-col px-3 py-2"
      actions={
        <StateChip
          label={`${detections.length} det`}
          tone={blocked ? 'alert' : 'muted'}
          dot={false}
        />
      }
    >
      <svg
        className="w-full min-h-[150px] flex-1"
        viewBox="0 0 200 116"
        preserveAspectRatio="xMidYMax meet"
        role="img"
        aria-label="Top-down obstacle field"
      >
        {/* Sensor field of view */}
        <path d={wedgePath(FOV_DEG, R_MAX)} fill="#16212e" opacity="0.7" />

        {/* SayCan gate cone, the sector the safety check actually reads */}
        <path d={wedgePath(GATE_CONE_DEG, R_MAX)} fill="#38bdf8" opacity="0.07" />

        {/* Threshold rings */}
        <path
          d={arcPath(radiusFor(REFLEX_STOP_DISTANCE_M))}
          fill="none"
          stroke="#ef4444"
          strokeWidth="0.8"
          strokeDasharray="3 2"
          opacity="0.8"
        />
        <path
          d={arcPath(radiusFor(SAYCAN_MIN_CLEARANCE_M))}
          fill="none"
          stroke="#f59e0b"
          strokeWidth="0.8"
          strokeDasharray="3 2"
          opacity="0.7"
        />
        {[1, 2].map((ring) => (
          <path
            key={ring}
            d={arcPath(radiusFor(ring))}
            fill="none"
            stroke="#2a3b4e"
            strokeWidth="0.7"
          />
        ))}

        {/* Cone edges */}
        {[-GATE_CONE_DEG, GATE_CONE_DEG].map((angle) => {
          const edge = pointAt(SENSOR_RANGE_M, angle)
          return (
            <line
              key={angle}
              x1={CX}
              y1={CY}
              x2={edge.x}
              y2={edge.y}
              stroke="#38bdf8"
              strokeWidth="0.6"
              opacity="0.35"
            />
          )
        })}

        {detections.map((detection, index) => {
          const { x, y } = pointAt(detection.distanceM, detection.bearingDeg)
          const inGate = Math.abs(detection.bearingDeg) < GATE_CONE_DEG
          const critical = inGate && detection.distanceM < REFLEX_STOP_DISTANCE_M
          const warning = inGate && detection.distanceM < SAYCAN_MIN_CLEARANCE_M
          const color = critical ? '#ef4444' : warning ? '#f59e0b' : '#94a3b8'
          return (
            <g key={`${detection.bearingDeg}-${index}`}>
              <circle cx={x} cy={y} r={critical ? 5.5 : 4} fill={color} opacity="0.2" />
              <circle cx={x} cy={y} r={critical ? 3 : 2.2} fill={color} />
              <text
                x={x}
                y={y - 6}
                fill={color}
                fontSize="6.5"
                fontFamily="ui-monospace, monospace"
                textAnchor="middle"
              >
                {detection.distanceM.toFixed(2)}
              </text>
            </g>
          )
        })}

        {/* Rover */}
        <polygon
          points={`${CX},${CY - 7} ${CX - 5},${CY + 4} ${CX + 5},${CY + 4}`}
          fill={blocked ? '#ef4444' : '#22c55e'}
        />
      </svg>

      <div className="mt-1.5 flex shrink-0 items-center justify-between gap-2 border-t border-line pt-1.5 text-[10px] tracking-[0.1em] text-ink-faint uppercase">
        <span>
          Nearest{' '}
          <span className="font-mono text-ink">
            {nearest ? `${nearest.distanceM.toFixed(2)} m @ ${nearest.bearingDeg}°` : 'clear'}
          </span>
        </span>
        <span className="flex items-center gap-2">
          <Legend color="#ef4444" label={`${REFLEX_STOP_DISTANCE_M} m`} />
          <Legend color="#f59e0b" label={`${SAYCAN_MIN_CLEARANCE_M} m`} />
        </span>
      </div>
    </Tile>
  )
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <span className="flex items-center gap-1">
      <span className="h-px w-3" style={{ backgroundColor: color }} />
      <span className="font-mono">{label}</span>
    </span>
  )
}
