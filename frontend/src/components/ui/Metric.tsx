import type { ReactNode } from 'react'

export type MetricTone = 'default' | 'live' | 'warn' | 'alert' | 'accent' | 'faint'

const toneStyles: Record<MetricTone, string> = {
  default: 'text-ink',
  live: 'text-live',
  warn: 'text-warn',
  alert: 'text-alert',
  accent: 'text-accent',
  faint: 'text-ink-faint',
}

interface MetricProps {
  label: string
  value: ReactNode
  unit?: string
  tone?: MetricTone
  size?: 'headline' | 'inline'
  className?: string
}

export function Metric({
  label,
  value,
  unit,
  tone = 'default',
  size = 'inline',
  className = '',
}: MetricProps) {
  const headline = size === 'headline'
  return (
    <div className={`flex min-w-0 flex-col gap-1 ${className}`}>
      <span className="truncate text-[10px] font-semibold tracking-[0.14em] text-ink-faint uppercase">
        {label}
      </span>
      <span
        className={`flex items-baseline gap-1 font-mono leading-none ${
          headline ? 'text-lg' : 'text-xs'
        } ${toneStyles[tone]}`}
      >
        <span className="truncate">{value}</span>
        {unit && <span className="text-[10px] text-ink-faint">{unit}</span>}
      </span>
    </div>
  )
}
