import { Command } from 'lucide-react'
import type { VerbUsage } from '../../types'
import { Tile } from '../ui/Tile'

const kindStyles: Record<VerbUsage['kind'], string> = {
  motion: 'border-accent/30 text-accent',
  speech: 'border-live/30 text-live',
  read: 'border-line-strong text-ink-muted',
}

interface VerbPaletteProps {
  verbs: VerbUsage[]
  className?: string
}

export function VerbPalette({ verbs, className = '' }: VerbPaletteProps) {
  const total = verbs.reduce((sum, verb) => sum + verb.calls, 0)
  const mostRecent = verbs
    .filter((verb) => verb.lastUsedClock)
    .sort((a, b) => (a.lastUsedClock! < b.lastUsedClock! ? 1 : -1))[0]

  return (
    <Tile
      title="Verb Schema"
      icon={Command}
      className={className}
      actions={<span className="font-mono text-[10px] text-ink-faint">{total} calls</span>}
    >
      <div className="flex h-full flex-wrap content-start items-start gap-1.5">
        {verbs.map((verb) => {
          const active = mostRecent?.name === verb.name
          return (
            <span
              key={verb.name}
              title={verb.lastUsedClock ? `last used ${verb.lastUsedClock}` : 'not yet called'}
              className={`inline-flex items-center gap-1.5 rounded border px-1.5 py-1 font-mono text-[10px] transition-colors ${
                kindStyles[verb.kind]
              } ${active ? 'bg-accent/10' : 'bg-raised'} ${verb.calls === 0 ? 'opacity-45' : ''}`}
            >
              {verb.name}
              <span className="rounded bg-black/30 px-1 text-[9px] text-ink-faint">
                {verb.calls}
              </span>
            </span>
          )
        })}
      </div>
    </Tile>
  )
}
