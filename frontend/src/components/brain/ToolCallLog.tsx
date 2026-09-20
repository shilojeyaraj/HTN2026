import { Terminal } from 'lucide-react'
import type { ToolCallRecord, ToolResultStatus } from '../../types'
import { StateChip } from '../ui/StateChip'
import type { ChipTone } from '../ui/StateChip'
import { Tile } from '../ui/Tile'

const statusTone: Record<ToolResultStatus, ChipTone> = {
  completed: 'live',
  stopped_by_obstacle: 'warn',
  vetoed: 'alert',
  error: 'alert',
  read: 'muted',
}

const statusBorder: Record<ToolResultStatus, string> = {
  completed: 'border-l-live/60',
  stopped_by_obstacle: 'border-l-warn/60',
  vetoed: 'border-l-alert/70',
  error: 'border-l-alert/70',
  read: 'border-l-line-strong',
}

interface ToolCallLogProps {
  toolCalls: ToolCallRecord[]
  className?: string
}

export function ToolCallLog({ toolCalls, className = '' }: ToolCallLogProps) {
  return (
    <Tile
      title="Tool Calls"
      icon={Terminal}
      className={className}
      bodyClassName="scroll-slim overflow-y-auto px-3 py-2"
      actions={
        <span className="font-mono text-[10px] text-ink-faint">{toolCalls.length} recent</span>
      }
    >
      {toolCalls.length === 0 ? (
        <p className="text-[11px] text-ink-faint">Waiting for the first episode.</p>
      ) : (
        <ol className="flex flex-col gap-2">
          {toolCalls.map((call) => (
            <li key={call.id} className={`border-l-2 pl-2.5 ${statusBorder[call.status]}`}>
              <div className="flex items-center gap-2">
                <span className="font-mono text-[11px] text-ink">{call.name}</span>
                <span className="truncate font-mono text-[10px] text-ink-faint">{call.args}</span>
                <StateChip
                  label={call.status.replace(/_/g, ' ')}
                  tone={statusTone[call.status]}
                  dot={false}
                  className="ml-auto shrink-0"
                />
              </div>
              <div className="mt-0.5 flex items-baseline gap-2">
                <span className="font-mono text-[10px] text-ink-faint">
                  {call.clock} · ep {call.episode}
                </span>
                <span className="truncate font-mono text-[10px] text-ink-muted">{call.result}</span>
              </div>
            </li>
          ))}
        </ol>
      )}
    </Tile>
  )
}
