import { Brain, TrendingUp } from 'lucide-react'
import type { PatternInsights } from '../types'
import { Panel } from './ui/Panel'

interface PatternInsightsCardProps {
  insights: PatternInsights | null | undefined
}

export function PatternInsightsCard({ insights }: PatternInsightsCardProps) {
  const entries = insights
    ? Object.entries(insights).filter(([_, v]) => v != null && typeof v !== 'object')
    : []

  return (
    <Panel
      title="Pattern Analysis"
      icon={TrendingUp}
      actions={
        <span className="font-mono text-[11px] text-ink-faint">
          {insights ? `${entries.length} insights` : '—'}
        </span>
      }
    >
      <div className="px-5 py-4">
        {!insights ? (
          <div className="flex items-center gap-2.5 py-4 text-sm text-ink-faint">
            <Brain className="h-4 w-4" strokeWidth={2} />
            <span>No analysis yet — brain will call analyze_patterns()</span>
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            {entries.map(([key, value]) => (
              <div
                key={key}
                className="flex items-center justify-between rounded border border-line/50 bg-surface/50 px-3.5 py-2.5"
              >
                <span className="text-[11px] font-semibold tracking-[0.12em] text-ink-faint uppercase">
                  {key.replace(/_/g, ' ')}
                </span>
                <span className="font-mono text-sm font-medium text-ink">
                  {String(value)}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </Panel>
  )
}
