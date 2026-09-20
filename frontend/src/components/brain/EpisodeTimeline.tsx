import { ListOrdered } from 'lucide-react'
import type { EpisodeRecord } from '../../types'
import { StateChip } from '../ui/StateChip'
import { Tile } from '../ui/Tile'

interface EpisodeTimelineProps {
  episodes: EpisodeRecord[]
  className?: string
}

export function EpisodeTimeline({ episodes, className = '' }: EpisodeTimelineProps) {
  return (
    <Tile
      title="Deliberative Episodes"
      icon={ListOrdered}
      className={className}
      bodyClassName="scroll-slim overflow-y-auto px-3 py-2"
      actions={<span className="font-mono text-[10px] text-ink-faint">~1 Hz</span>}
    >
      {episodes.length === 0 ? (
        <p className="text-[11px] text-ink-faint">No episodes yet.</p>
      ) : (
        <ol className="flex flex-col gap-1.5">
          {episodes.map((episode) => (
            <li key={episode.id} className="flex items-center gap-2">
              <span className="w-8 shrink-0 font-mono text-[10px] text-ink-faint">
                #{episode.number}
              </span>
              <StateChip
                label={episode.path}
                tone={episode.path === 'parser' ? 'warn' : 'accent'}
                dot={false}
                className="shrink-0"
              />
              <span className="min-w-0 flex-1 truncate text-[11px] text-ink-muted">
                {episode.summary}
              </span>
              <span className="shrink-0 font-mono text-[10px] text-ink-faint">
                {episode.toolRounds}r · {episode.durationMs}ms
              </span>
            </li>
          ))}
        </ol>
      )}
    </Tile>
  )
}
