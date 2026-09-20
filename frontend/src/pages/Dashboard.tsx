import type { LiveSnapshot } from '../types'
import { Brain } from './Brain'
import { Telemetry } from './Telemetry'

export function Dashboard({ snapshot, live }: { snapshot: LiveSnapshot | null; live: boolean }) {
  return (
    <div className="flex flex-col gap-6">
      <Brain mission={snapshot?.mission ?? null} live={live} />
      <Telemetry snapshot={snapshot} live={live} />
    </div>
  )
}
