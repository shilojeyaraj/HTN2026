import { Brain, Activity, AlertCircle, Mic } from 'lucide-react'
import type { BrainActivityEvent, SensorSnapshot, PatternInsights } from '../types'
import { Panel } from './ui/Panel'

interface AINarrativeProps {
  brainEvents: BrainActivityEvent[]
  sensors: SensorSnapshot | null
  insights: PatternInsights | null
}

function timeAgo(ts: number): string {
  const diff = Math.floor(Date.now() / 1000 - ts)
  if (diff < 60) return `${diff}s ago`
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  return `${Math.floor(diff / 3600)}h ago`
}

function summarizeEvents(events: BrainActivityEvent[]): string {
  if (events.length === 0) return 'Waiting for brain activity...'

  const recent = events.slice(-5)
  const tools = recent.map((e) => e.tool)
  const hasMotion = tools.some((t) => ['forward', 'backward', 'turn', 'stop'].includes(t))
  const hasSpeak = tools.some((t) => t === 'speak')
  const hasSearch = tools.some((t) => t === 'search_knowledge')
  const hasLog = tools.some((t) => t === 'log_finding')
  const hasSensor = tools.some((t) => ['get_temperature', 'get_audio', 'get_gyro'].includes(t))

  const parts: string[] = []
  if (hasMotion) parts.push('rover is navigating')
  if (hasSpeak) parts.push('communicating with victim')
  if (hasSearch) parts.push('consulting rescue protocols')
  if (hasSensor) parts.push('monitoring sensors')
  if (hasLog) parts.push('logging findings')

  if (parts.length === 0) parts.push('processing scene')

  return `The ${parts.join(', ')}.`
}

export function AINarrative({ brainEvents, sensors, insights }: AINarrativeProps) {
  const summary = summarizeEvents(brainEvents)

  // Check for alerts
  const alerts: string[] = []
  if (sensors) {
    if (sensors.temperature.status === 'overheat') alerts.push('Thermal hazard detected')
    else if (sensors.temperature.status === 'warm') alerts.push('Elevated temperature')
    if (sensors.audio.event) alerts.push(`${sensors.audio.event.kind.toUpperCase()}: ${sensors.audio.event.label}`)
    if (sensors.gyro.tipped) alerts.push('Rover tipped!')
    else if (sensors.gyro.bump) alerts.push('Impact detected')
  }

  const recentEvents = brainEvents.slice(-6)

  return (
    <Panel
      title="AI Mission Summary"
      icon={Brain}
      actions={
        <span className={`font-mono text-[11px] ${alerts.length > 0 ? 'text-alert' : 'text-ink-faint'}`}>
          {alerts.length > 0 ? `${alerts.length} ALERTS` : 'monitoring'}
        </span>
      }
    >
      <div className="flex flex-col gap-3 px-5 py-4">
        {/* Current status */}
        <div className="flex items-start gap-2.5 rounded border border-line/50 bg-surface/50 px-3.5 py-2.5">
          <Activity className="mt-0.5 h-4 w-4 shrink-0 text-live" strokeWidth={2} />
          <div>
            <div className="text-[11px] font-semibold tracking-[0.12em] text-ink-faint uppercase">
              Current Status
            </div>
            <div className="mt-0.5 text-sm text-ink">{summary}</div>
          </div>
        </div>

        {/* Alerts */}
        {alerts.length > 0 && (
          <div className="flex flex-col gap-1.5">
            {alerts.map((alert, i) => (
              <div
                key={i}
                className="flex items-center gap-2 rounded border border-alert/30 bg-alert/10 px-3 py-2"
              >
                <AlertCircle className="h-4 w-4 shrink-0 text-alert" strokeWidth={2} />
                <span className="text-sm font-medium text-alert">{alert}</span>
              </div>
            ))}
          </div>
        )}

        {/* Recent brain activity */}
        <div>
          <div className="mb-2 flex items-center gap-2 text-[11px] font-semibold tracking-[0.12em] text-ink-faint uppercase">
            <Mic className="h-3.5 w-3.5" strokeWidth={2} />
            Recent Decisions
          </div>
          <div className="flex flex-col gap-1">
            {recentEvents.length === 0 ? (
              <div className="text-sm text-ink-faint">No activity yet...</div>
            ) : (
              recentEvents.map((e, i) => (
                <div key={i} className="flex items-center gap-2 text-[12px]">
                  <span className="font-mono font-semibold text-ink">{e.tool}</span>
                  <span className="font-mono text-ink-faint truncate flex-1">
                    {JSON.stringify(e.args).slice(0, 40)}
                  </span>
                  <span className="font-mono text-[10px] text-ink-faint shrink-0">
                    {timeAgo(e.timestamp)}
                  </span>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Insights */}
        {insights && (
          <div className="rounded border border-violet-400/20 bg-violet-400/5 px-3.5 py-2.5">
            <div className="text-[11px] font-semibold tracking-[0.12em] text-violet-400 uppercase">
              Pattern Analysis
            </div>
            <div className="mt-1 text-sm text-ink">
              {Object.entries(insights)
                .filter(([_, v]) => v != null && typeof v !== 'object')
                .slice(0, 3)
                .map(([k, v]) => `${k.replace(/_/g, ' ')}: ${v}`)
                .join(' · ')}
            </div>
          </div>
        )}
      </div>
    </Panel>
  )
}
