import { Route } from 'lucide-react'
import type { PoseState } from '../../types'
import { Metric } from '../ui/Metric'
import { StateChip } from '../ui/StateChip'
import { Tile } from '../ui/Tile'

const VIEW_W = 200
const VIEW_H = 108
const PAD = 10

interface PoseTrackProps {
  pose: PoseState
  goal: { x: number; y: number } | null
  className?: string
}

export function PoseTrack({ pose, goal, className = '' }: PoseTrackProps) {
  const points = pose.trail
  const xs = points.map((p) => p.x)
  const ys = points.map((p) => p.y)

  // Auto-fit the wandering trail, with a floor on the span so a stationary
  // rover does not get magnified into noise.
  const minX = Math.min(...xs, pose.x)
  const maxX = Math.max(...xs, pose.x)
  const minY = Math.min(...ys, pose.y)
  const maxY = Math.max(...ys, pose.y)
  const span = Math.max(maxX - minX, maxY - minY, 1.5)
  const cx = (minX + maxX) / 2
  const cy = (minY + maxY) / 2
  const scale = (Math.min(VIEW_W, VIEW_H) - PAD * 2) / span

  const project = (x: number, y: number) => ({
    px: VIEW_W / 2 + (x - cx) * scale,
    // World y grows up, SVG y grows down.
    py: VIEW_H / 2 - (y - cy) * scale,
  })

  const path = points
    .map((point, index) => {
      const { px, py } = project(point.x, point.y)
      return `${index === 0 ? 'M' : 'L'} ${px.toFixed(1)} ${py.toFixed(1)}`
    })
    .join(' ')

  const head = project(pose.x, pose.y)
  const goalPoint = goal ? project(goal.x, goal.y) : null

  return (
    <Tile
      title="Pose / Track"
      icon={Route}
      className={className}
      bodyClassName="flex flex-col px-3 py-2"
      actions={<StateChip label="odom estimate" tone="muted" dot={false} />}
    >
      <svg
        className="w-full min-h-[150px] flex-1"
        viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
        preserveAspectRatio="xMidYMid meet"
        role="img"
        aria-label="Top-down rover track"
      >
        <defs>
          <pattern id="pose-grid" width="16" height="16" patternUnits="userSpaceOnUse">
            <path d="M 16 0 L 0 0 0 16" fill="none" stroke="#1e2b3a" strokeWidth="0.6" />
          </pattern>
        </defs>
        <rect width={VIEW_W} height={VIEW_H} fill="url(#pose-grid)" />

        {goalPoint && (
          <g>
            <circle
              cx={goalPoint.px}
              cy={goalPoint.py}
              r="4.5"
              fill="none"
              stroke="#38bdf8"
              strokeWidth="1"
              strokeDasharray="2 2"
            />
            <circle cx={goalPoint.px} cy={goalPoint.py} r="1.4" fill="#38bdf8" />
          </g>
        )}

        <path d={path} fill="none" stroke="#38bdf8" strokeWidth="1.3" opacity="0.55" />

        <g transform={`rotate(${90 - pose.headingDeg} ${head.px} ${head.py})`}>
          <polygon
            points={`${head.px},${head.py - 5.5} ${head.px - 4},${head.py + 3.5} ${head.px + 4},${head.py + 3.5}`}
            fill="#22c55e"
          />
        </g>
        <circle cx={head.px} cy={head.py} r="8" fill="#22c55e" opacity="0.12" />
      </svg>

      <div className="mt-1.5 grid shrink-0 grid-cols-4 gap-2 border-t border-line pt-2">
        <Metric label="x" value={pose.x.toFixed(2)} unit="m" />
        <Metric label="y" value={pose.y.toFixed(2)} unit="m" />
        <Metric label="Heading" value={pose.headingDeg.toFixed(0)} unit="°" />
        <Metric label="Scale" value={`${span.toFixed(1)}`} unit="m" tone="faint" />
      </div>
    </Tile>
  )
}
