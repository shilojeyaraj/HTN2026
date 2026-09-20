export type BarTone = 'live' | 'warn' | 'alert' | 'accent' | 'muted'

const fillStyles: Record<BarTone, string> = {
  live: 'bg-live',
  warn: 'bg-warn',
  alert: 'bg-alert',
  accent: 'bg-accent',
  muted: 'bg-ink-faint',
}

const labelStyles: Record<BarTone, string> = {
  live: 'text-live',
  warn: 'text-warn',
  alert: 'text-alert',
  accent: 'text-accent',
  muted: 'text-ink-muted',
}

interface MeterBarProps {
  /** 0 to 1. */
  value: number
  tone?: BarTone
  label?: string
  valueLabel?: string
  /** 0 to 1. Draws a tick where a backend limit sits. */
  threshold?: number
  className?: string
}

export function MeterBar({
  value,
  tone = 'accent',
  label,
  valueLabel,
  threshold,
  className = '',
}: MeterBarProps) {
  const pct = Math.min(100, Math.max(0, value * 100))
  return (
    <div className={`flex flex-col gap-1 ${className}`}>
      {(label || valueLabel) && (
        <div className="flex items-baseline justify-between gap-2">
          {label && (
            <span className="truncate text-[10px] font-semibold tracking-[0.12em] text-ink-faint uppercase">
              {label}
            </span>
          )}
          {valueLabel && (
            <span className={`font-mono text-[11px] ${labelStyles[tone]}`}>{valueLabel}</span>
          )}
        </div>
      )}
      <div className="relative h-1.5 w-full overflow-hidden rounded-full bg-raised">
        <div
          className={`h-full rounded-full transition-[width] duration-200 ease-out ${fillStyles[tone]}`}
          style={{ width: `${pct}%` }}
        />
        {threshold !== undefined && (
          <span
            className="absolute inset-y-0 w-px bg-ink-faint/70"
            style={{ left: `${Math.min(100, Math.max(0, threshold * 100))}%` }}
          />
        )}
      </div>
    </div>
  )
}
