import { BrainCircuit, Target, Terminal } from 'lucide-react'
import { Metric } from '../components/ui/Metric'
import { StateChip } from '../components/ui/StateChip'
import { Tile } from '../components/ui/Tile'
import type { LiveMission } from '../types'

export function Brain({ mission, live }: { mission: LiveMission | null; live: boolean }) {
  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
      <Tile title="Mission" icon={Target} actions={<StateChip label={mission?.phase.replaceAll('_', ' ') ?? 'waiting'}
        tone={!live ? 'muted' : mission?.phase === 'failed' ? 'alert' : mission?.phase === 'complete' ? 'live' : 'accent'} />}>
        <p className="text-base text-ink">{mission?.goal ?? 'Monitoring — no mission assigned'}</p>
        <p className="mt-2 text-sm text-ink-muted">{mission?.reason ?? 'Waiting for mission status.'}</p>
        {!live && <p className="mt-2 text-xs text-warn">Last received state · feed offline</p>}
        <div className="mt-5 grid grid-cols-2 gap-4">
          <Metric label="Mode" value={mission?.mode ?? '—'} />
          <Metric label="Valid cycles" value={mission?.cycles ?? '—'} />
          <Metric label="Failures" value={mission?.failures ?? '—'} />
          <Metric label="Retry in" value={mission?.retry_in_s.toFixed(1) ?? '—'} unit="s" />
        </div>
      </Tile>

      <Tile title="Latest observation" icon={BrainCircuit}>
        <p className="text-sm leading-relaxed text-ink">{mission?.scene ?? 'No camera observation yet.'}</p>
        <div className="mt-4 space-y-3">
          <Metric label="Model" value={mission?.model ?? '—'} />
          <Metric label="Inference time" value={mission?.inference_ms?.toFixed(0) ?? '—'} unit="ms" />
          <Metric label="Observed at" value={mission?.scene_at ? new Date(mission.scene_at * 1000).toLocaleTimeString() : '—'} />
        </div>
      </Tile>

      <Tile title="Search and findings">
        <div className="mb-4 flex flex-wrap gap-3">
          <StateChip label={mission?.search_active ? 'Searching' : 'Search inactive'} tone={live && mission?.search_active ? 'accent' : 'muted'} />
          <span className="text-xs text-ink-muted">{mission?.search_rotation_deg.toFixed(0) ?? '—'}° commanded search turns</span>
        </div>
        <ul className="max-h-52 space-y-2 overflow-auto text-sm text-ink-muted">
          {(mission?.findings ?? []).map((finding, i) => <li key={i}><strong>{finding.type}:</strong> {finding.description}</li>)}
        </ul>
        {!mission?.findings.length && <p className="text-sm text-ink-faint">No findings recorded.</p>}
      </Tile>

      <Tile title="Action history" icon={Terminal} className="md:col-span-2 xl:col-span-3">
        {!mission?.actions.length ? <p className="py-4 text-sm text-ink-faint">No actions recorded.</p> : (
          <ol className="max-h-[480px] space-y-3 overflow-y-auto">
            {[...mission.actions].reverse().map(action => <li key={action.id} className="rounded border border-line p-3">
              <div className="flex flex-wrap items-center gap-2">
                <strong className="font-mono text-sm">#{action.id} {action.name}</strong>
                <StateChip label={action.status} tone={!live ? 'muted' : ['error', 'rejected'].includes(action.status) ? 'alert' : action.status === 'executing' ? 'accent' : 'live'} />
                <span className="text-xs text-ink-faint">{action.mode} · {new Date(action.started_at * 1000).toLocaleTimeString()} · {action.duration_ms === null ? 'in progress' : `${action.duration_ms.toFixed(0)} ms`}</span>
              </div>
              <p className="mt-2 break-words font-mono text-xs text-ink-muted">Requested: {action.requested_args}</p>
              {action.applied_args && <p className="mt-1 break-words font-mono text-xs text-ink-muted">Applied: {JSON.stringify(action.applied_args)}</p>}
              {action.result && <pre className="mt-2 whitespace-pre-wrap break-words text-xs text-ink-faint">{JSON.stringify(action.result, null, 2)}</pre>}
            </li>)}
          </ol>
        )}
      </Tile>
    </div>
  )
}
