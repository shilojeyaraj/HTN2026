import { Activity, Brain, Cpu, Gauge, Search, Shield, Thermometer, Volume2, Waves } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { useEffect, useRef } from 'react'
import type { BrainActivityEvent } from '../types'
import { Panel } from './ui/Panel'

const TOOL_ICONS: Record<string, LucideIcon> = {
  forward: Activity,
  backward: Activity,
  turn: Activity,
  stop: Activity,
  speak: Volume2,
  look_around: Search,
  check_map: Gauge,
  check_safety: Shield,
  search_knowledge: Brain,
  log_finding: Cpu,
  analyze_patterns: Brain,
  get_obstacles: Gauge,
  get_state: Gauge,
  get_temperature: Thermometer,
  get_audio: Waves,
  get_gyro: Cpu,
}

const TOOL_COLORS: Record<string, string> = {
  forward: 'text-accent',
  backward: 'text-accent',
  turn: 'text-accent',
  stop: 'text-alert',
  speak: 'text-live',
  look_around: 'text-sky-400',
  check_map: 'text-sky-400',
  check_safety: 'text-amber-400',
  search_knowledge: 'text-violet-400',
  log_finding: 'text-violet-400',
  analyze_patterns: 'text-violet-400',
  get_obstacles: 'text-ink-faint',
  get_state: 'text-ink-faint',
  get_temperature: 'text-amber-400',
  get_audio: 'text-sky-400',
  get_gyro: 'text-ink-faint',
}

function formatTime(ts: number) {
  const d = new Date(ts * 1000)
  return d.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function truncate(s: unknown, max = 80): string {
  const str = typeof s === 'string' ? s : JSON.stringify(s)
  return str.length > max ? str.slice(0, max) + '…' : str
}

export function BrainActivity({ events }: { events: BrainActivityEvent[] }) {
  const listRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight
    }
  }, [events])

  return (
    <Panel
      title="Brain Activity"
      icon={Brain}
      actions={
        <span className="font-mono text-[11px] text-ink-faint">
          {events.length} calls
        </span>
      }
    >
      <div ref={listRef} className="scroll-slim max-h-[280px] overflow-y-auto px-4 py-3">
        {events.length === 0 ? (
          <div className="flex items-center justify-center py-8 text-sm text-ink-faint">
            Waiting for brain activity…
          </div>
        ) : (
          <div className="flex flex-col gap-1.5">
            {events.map((event, i) => {
              const Icon = TOOL_ICONS[event.tool] || Cpu
              const color = TOOL_COLORS[event.tool] || 'text-ink-faint'
              const resultStr = truncate(event.result)
              const argsStr = truncate(event.args, 60)
              return (
                <div
                  key={i}
                  className="flex items-start gap-2.5 rounded border border-line/50 bg-surface/50 px-3 py-2 transition-colors hover:border-line"
                >
                  <Icon className={`mt-0.5 h-3.5 w-3.5 shrink-0 ${color}`} strokeWidth={2} />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-[13px] font-semibold text-ink">
                        {event.tool}
                      </span>
                      {argsStr !== '{}' && (
                        <span className="font-mono text-[11px] text-ink-faint">
                          {argsStr}
                        </span>
                      )}
                      <span className="ml-auto font-mono text-[10px] text-ink-faint">
                        {formatTime(event.timestamp)}
                      </span>
                    </div>
                    <div className="mt-0.5 truncate font-mono text-[11px] text-ink-muted">
                      → {resultStr}
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </Panel>
  )
}
