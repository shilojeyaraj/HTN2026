import type { ReactNode } from 'react'
import type { TelemetrySnapshot } from '../../types'
import { StateChip } from '../ui/StateChip'
import type { ChipTone } from '../ui/StateChip'

const sourceTone: Record<TelemetrySnapshot['drive']['source'], ChipTone> = {
  reflex: 'alert',
  brain: 'accent',
  watchdog: 'warn',
}

const depthTone: Record<TelemetrySnapshot['depth']['status'], ChipTone> = {
  ok: 'live',
  uncertain: 'warn',
  error: 'alert',
  preview: 'muted',
}

interface StatusStripProps {
  telemetry: TelemetrySnapshot
}

export function StatusStrip({ telemetry }: StatusStripProps) {
  const { drive, safety, reflex, depth, uptimeS, clock } = telemetry

  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-2.5 rounded-lg border border-line bg-surface px-4 py-2.5">
      <Item label="cmd_vel">
        <StateChip label={drive.source} tone={sourceTone[drive.source]} pulse />
      </Item>
      <Item label="Safety">
        <StateChip label={safety.status} tone={safety.status === 'OK' ? 'live' : 'alert'} />
      </Item>
      <Item label="Reflex">
        <StateChip
          label={reflex.blocked ? 'Blocked' : 'Clear'}
          tone={reflex.blocked ? 'alert' : 'live'}
        />
      </Item>
      <Item label="Depth link">
        <StateChip label={depth.status} tone={depthTone[depth.status]} />
      </Item>
      <Item label="Uptime">
        <span className="font-mono text-xs text-ink">{formatUptime(uptimeS)}</span>
      </Item>
      <Item label="Clock" className="ml-auto">
        <span className="font-mono text-xs text-ink-muted">{clock}</span>
      </Item>
    </div>
  )
}

function Item({
  label,
  children,
  className = '',
}: {
  label: string
  children: ReactNode
  className?: string
}) {
  return (
    <div className={`flex items-center gap-2 ${className}`}>
      <span className="text-[10px] font-semibold tracking-[0.14em] text-ink-faint uppercase">
        {label}
      </span>
      {children}
    </div>
  )
}

function formatUptime(seconds: number): string {
  const total = Math.floor(seconds)
  const mm = String(Math.floor(total / 60)).padStart(2, '0')
  const ss = String(total % 60).padStart(2, '0')
  return `${mm}:${ss}`
}
