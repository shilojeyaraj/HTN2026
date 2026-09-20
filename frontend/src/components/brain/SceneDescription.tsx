import { Eye } from 'lucide-react'
import { VISION_MODEL } from '../../data/mockTelemetry'
import type { SceneState } from '../../types'
import { StateChip } from '../ui/StateChip'
import { Tile } from '../ui/Tile'

interface SceneDescriptionProps {
  scene: SceneState
  className?: string
}

export function SceneDescription({ scene, className = '' }: SceneDescriptionProps) {
  return (
    <Tile
      title="Scene Understanding"
      icon={Eye}
      className={className}
      bodyClassName="flex flex-col gap-2 px-3 py-2.5"
      actions={<StateChip label={VISION_MODEL} tone="accent" dot={false} />}
    >
      <p className="scroll-slim min-h-0 flex-1 overflow-y-auto text-[13px] leading-relaxed text-ink">
        {scene.text}
      </p>

      <div className="flex shrink-0 flex-wrap gap-1.5 border-t border-line pt-2">
        {scene.detections.map((detection, index) => (
          <span
            key={`${detection.bearingDeg}-${index}`}
            className="rounded border border-line-strong bg-raised px-1.5 py-0.5 font-mono text-[10px] text-ink-muted"
          >
            {detection.label} {detection.distanceM.toFixed(2)}m @{detection.bearingDeg}°
          </span>
        ))}
      </div>

      <p className="shrink-0 font-mono text-[10px] text-ink-faint">
        frame {scene.frameId.toLocaleString()} · {scene.ageS.toFixed(1)}s old · BYOK via Backboard
      </p>
    </Tile>
  )
}
