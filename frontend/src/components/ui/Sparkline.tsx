export type SparkTone = 'live' | 'warn' | 'alert' | 'accent' | 'muted'

const toneStyles: Record<SparkTone, string> = {
  live: 'text-live',
  warn: 'text-warn',
  alert: 'text-alert',
  accent: 'text-accent',
  muted: 'text-ink-faint',
}

interface SparklineProps {
  values: number[]
  min?: number
  max?: number
  tone?: SparkTone
  className?: string
}

/**
 * Inline SVG trend line over a rolling history. Stretched with a non-uniform
 * aspect so it fills whatever box the tile gives it.
 */
export function Sparkline({
  values,
  min,
  max,
  tone = 'accent',
  className = 'h-8',
}: SparklineProps) {
  if (values.length < 2) {
    return <div className={`${className} w-full`} aria-hidden="true" />
  }

  const lo = min ?? Math.min(...values)
  const hi = max ?? Math.max(...values)
  const span = hi - lo || 1

  const points = values.map((value, index) => {
    const x = (index / (values.length - 1)) * 100
    const y = 30 - ((value - lo) / span) * 28 - 1
    return `${x.toFixed(2)},${y.toFixed(2)}`
  })

  return (
    <svg
      className={`${className} w-full ${toneStyles[tone]}`}
      viewBox="0 0 100 30"
      preserveAspectRatio="none"
      role="img"
      aria-hidden="true"
    >
      <polygon
        points={`0,30 ${points.join(' ')} 100,30`}
        fill="currentColor"
        opacity="0.12"
        stroke="none"
      />
      <polyline
        points={points.join(' ')}
        fill="none"
        stroke="currentColor"
        strokeWidth="1.2"
        strokeLinejoin="round"
        strokeLinecap="round"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  )
}
