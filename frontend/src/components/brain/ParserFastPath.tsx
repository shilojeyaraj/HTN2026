import { Split } from 'lucide-react'
import type { ParserState } from '../../types'
import { Metric } from '../ui/Metric'
import { StateChip } from '../ui/StateChip'
import { Tile } from '../ui/Tile'

interface ParserFastPathProps {
  parser: ParserState
  className?: string
}

export function ParserFastPath({ parser, className = '' }: ParserFastPathProps) {
  const total = parser.hits + parser.misses
  const hitRate = total === 0 ? 0 : Math.round((parser.hits / total) * 100)

  return (
    <Tile
      title="Parser Fast Path"
      icon={Split}
      className={className}
      actions={
        <StateChip
          label={parser.lastParsed ? 'Hit' : 'Fell through'}
          tone={parser.lastParsed ? 'live' : 'muted'}
        />
      }
    >
      <div className="flex h-full flex-col justify-between gap-2">
        <div className="flex items-end justify-between gap-2">
          <Metric label="Hit rate" value={`${hitRate}%`} size="headline" tone="accent" />
          <Metric label="Latency" value={parser.lastLatencyMs} unit="ms" />
        </div>

        <div className="min-w-0">
          <p className="truncate text-[11px] text-ink-muted">
            {parser.lastCommand ? `"${parser.lastCommand}"` : 'No command yet'}
          </p>
          <p className="truncate font-mono text-[10px] text-ink-faint">
            {parser.lastParsed
              ? `${parser.lastParsed.verb}(${JSON.stringify(parser.lastParsed.args)})`
              : 'null · routed to Backboard'}
          </p>
        </div>

        <p className="truncate font-mono text-[10px] text-ink-faint">
          {parser.hits}/{total} · {parser.modelId}
        </p>
      </div>
    </Tile>
  )
}
