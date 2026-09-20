export type ChipTone = 'live' | 'warn' | 'alert' | 'accent' | 'muted'

const toneStyles: Record<ChipTone, string> = {
  live: 'border-live/30 bg-live/10 text-live',
  warn: 'border-warn/30 bg-warn/10 text-warn',
  alert: 'border-alert/30 bg-alert/10 text-alert',
  accent: 'border-accent/30 bg-accent/10 text-accent',
  muted: 'border-line-strong bg-raised text-ink-faint',
}

interface StateChipProps {
  label: string
  tone?: ChipTone
  dot?: boolean
  pulse?: boolean
  className?: string
}

/** Generic status chip. StatusBadge stays encounter-specific. */
export function StateChip({
  label,
  tone = 'muted',
  dot = true,
  pulse = false,
  className = '',
}: StateChipProps) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded border px-1.5 py-0.5 text-[10px] font-semibold tracking-[0.12em] whitespace-nowrap uppercase ${toneStyles[tone]} ${className}`}
    >
      {dot && (
        <span
          className={`h-1.5 w-1.5 shrink-0 rounded-full bg-current ${pulse ? 'animate-blip' : ''}`}
        />
      )}
      {label}
    </span>
  )
}
