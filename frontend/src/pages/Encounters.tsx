import { Search } from 'lucide-react'
import { useMemo, useState } from 'react'
import { EncounterCard } from '../components/EncounterCard'
import { EncounterDetails } from '../components/EncounterDetails'
import { encounters, statusLabels } from '../data/mockData'
import type { Encounter, EncounterStatus } from '../types'

type Filter = EncounterStatus | 'all'

const filters: { id: Filter; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'rescued', label: statusLabels.rescued },
  { id: 'located', label: statusLabels.located },
  { id: 'no-contact', label: statusLabels['no-contact'] },
]

export function Encounters() {
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<Filter>('all')
  const [selected, setSelected] = useState<Encounter | null>(null)

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase()
    return encounters.filter((encounter) => {
      const matchesStatus = filter === 'all' || encounter.status === filter
      const matchesQuery =
        needle === '' ||
        encounter.id.toLowerCase().includes(needle) ||
        encounter.location.toLowerCase().includes(needle)
      return matchesStatus && matchesQuery
    })
  }, [query, filter])

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1.5">
        <h1 className="text-xl font-semibold tracking-wide text-ink">Previous Encounters</h1>
        <p className="text-sm text-ink-muted">
          {visible.length} of {encounters.length} records
        </p>
      </div>

      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <label className="relative w-full lg:max-w-sm">
          <Search
            className="pointer-events-none absolute top-1/2 left-3.5 h-4 w-4 -translate-y-1/2 text-ink-faint"
            strokeWidth={2}
          />
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search by ID or location"
            aria-label="Search encounters"
            className="w-full rounded border border-line bg-surface py-2.5 pr-3.5 pl-10 text-sm text-ink placeholder:text-ink-faint focus:border-accent/50 focus:outline-none"
          />
        </label>

        <div className="flex flex-wrap gap-2">
          {filters.map(({ id, label }) => (
            <button
              key={id}
              type="button"
              onClick={() => setFilter(id)}
              aria-pressed={filter === id}
              className={`rounded border px-3 py-2 text-[11px] font-semibold tracking-[0.12em] uppercase transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent ${
                filter === id
                  ? 'border-accent/40 bg-accent/10 text-accent'
                  : 'border-line bg-surface text-ink-faint hover:border-line-strong hover:text-ink-muted'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {visible.length > 0 ? (
        <div className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-3">
          {visible.map((encounter) => (
            <EncounterCard key={encounter.id} encounter={encounter} onView={setSelected} />
          ))}
        </div>
      ) : (
        <p className="rounded-lg border border-dashed border-line bg-surface px-6 py-16 text-center text-sm text-ink-faint">
          No encounters match the current search.
        </p>
      )}

      <EncounterDetails encounter={selected} onClose={() => setSelected(null)} />
    </div>
  )
}
