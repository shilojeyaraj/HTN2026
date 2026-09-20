import { BatteryMedium, Radio } from 'lucide-react'
import type { Rover } from '../types'

interface HeaderProps {
  rover: Rover
}

export function Header({ rover }: HeaderProps) {
  const batteryColor =
    rover.battery === null ? 'text-ink-faint' : rover.battery <= 20 ? 'text-alert' : rover.battery <= 40 ? 'text-warn' : 'text-ink'

  return (
    <header className="border-b border-line bg-surface">
      <div className="mx-auto flex max-w-[1600px] flex-wrap items-center justify-between gap-4 px-6 py-4 lg:px-10">
        <div className="flex items-center gap-3">
          <Radio className="h-5 w-5 text-accent" strokeWidth={2} />
          <span className="text-base font-semibold tracking-[0.2em] text-ink">
            ROVER <span className="text-ink-faint">//</span> RESCUE
          </span>
        </div>

        <div className="flex flex-wrap items-center gap-x-5 gap-y-3 text-xs font-medium tracking-[0.12em] uppercase">
          <span className="flex items-center gap-2">
            <span
              className={`h-2 w-2 rounded-full ${
                rover.connected ? 'animate-blip bg-live' : 'bg-alert'
              }`}
            />
            <span className={rover.connected ? 'text-live' : 'text-alert'}>
              {rover.connected ? 'Connected' : 'Disconnected'}
            </span>
          </span>

          <span className="hidden h-4 w-px bg-line-strong sm:block" />

          <span className="whitespace-nowrap font-mono text-ink-muted">{rover.id}</span>

          <span className="hidden h-4 w-px bg-line-strong sm:block" />

          <span className={`flex items-center gap-2 ${batteryColor}`}>
            <BatteryMedium className="h-4 w-4" strokeWidth={2} />
            <span className="font-mono">{rover.battery === null ? 'Battery unavailable' : `${rover.battery}%`}</span>
          </span>
        </div>
      </div>
    </header>
  )
}
