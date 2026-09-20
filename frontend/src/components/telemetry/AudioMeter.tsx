import { AudioLines } from 'lucide-react'
import type { AudioState } from '../../types'
import { Metric } from '../ui/Metric'
import { Sparkline } from '../ui/Sparkline'
import { StateChip } from '../ui/StateChip'
import type { ChipTone } from '../ui/StateChip'
import { Tile } from '../ui/Tile'

const kindTone: Record<'distress' | 'sound' | 'voice', ChipTone> = {
  distress: 'alert',
  sound: 'warn',
  voice: 'accent',
}

interface AudioMeterProps {
  audio: AudioState
  className?: string
}

export function AudioMeter({ audio, className = '' }: AudioMeterProps) {
  const { event } = audio
  const tone = event ? (event.kind === 'distress' ? 'alert' : 'warn') : 'live'

  return (
    <Tile
      title="Ambient Audio"
      icon={AudioLines}
      className={className}
      actions={
        event ? (
          <StateChip label={event.kind} tone={kindTone[event.kind]} pulse />
        ) : (
          <StateChip label="Listening" tone="live" pulse />
        )
      }
    >
      <div className="flex h-full flex-col justify-between gap-1.5">
        <div className="flex items-end justify-between gap-3">
          <Metric label="Level" value={audio.db.toFixed(1)} unit="dB" size="headline" tone={tone} />
          {event && (
            <span className="font-mono text-[10px] text-ink-faint">
              bearing {event.bearingDeg > 0 ? '+' : ''}
              {event.bearingDeg}°
            </span>
          )}
        </div>

        <Sparkline values={audio.history} min={26} max={72} tone={tone} className="h-7" />

        <p className="truncate text-[11px] text-ink-muted">
          {event ? (
            <>
              {event.label && (
                <span className="font-mono text-ink-faint">{event.label} · </span>
              )}
              {event.text ? `"${event.text}"` : 'non-speech event'}
            </>
          ) : (
            <span className="text-ink-faint">No classified event</span>
          )}
        </p>
      </div>
    </Tile>
  )
}
