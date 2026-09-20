import { Target } from 'lucide-react'
import type { GoalState } from '../../types'
import { Metric } from '../ui/Metric'
import { StateChip } from '../ui/StateChip'
import { Tile } from '../ui/Tile'

interface GoalPanelProps {
  goal: GoalState
  className?: string
}

export function GoalPanel({ goal, className = '' }: GoalPanelProps) {
  const vetoed = goal.safetyStatus === 'VETO'

  return (
    <Tile
      title="Goal / Intent"
      icon={Target}
      className={className}
      actions={
        <StateChip label={goal.safetyStatus} tone={vetoed ? 'alert' : 'live'} pulse={vetoed} />
      }
    >
      <div className="flex h-full flex-col justify-between gap-2">
        <Metric
          label="current_goal"
          value={goal.current ? `${goal.current.x.toFixed(1)}, ${goal.current.y.toFixed(1)}` : 'none'}
          unit={goal.current ? 'm' : undefined}
          size="headline"
          tone="accent"
        />
        <div className="min-w-0">
          <span className="text-[10px] font-semibold tracking-[0.14em] text-ink-faint uppercase">
            last_user_command
          </span>
          <p className="truncate text-[11px] text-ink-muted">
            {goal.lastUserCommand ? `"${goal.lastUserCommand}"` : 'none'}
          </p>
        </div>
      </div>
    </Tile>
  )
}
