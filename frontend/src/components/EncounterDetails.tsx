import { CalendarClock, MapPin, Timer, X } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { useEffect } from 'react'
import type { ReactNode } from 'react'
import type { Encounter } from '../types'
import { Transcript } from './Transcript'
import { StatusBadge } from './ui/StatusBadge'

interface EncounterDetailsProps {
  encounter: Encounter | null
  onClose: () => void
}

export function EncounterDetails({ encounter, onClose }: EncounterDetailsProps) {
  const isOpen = encounter !== null

  useEffect(() => {
    if (!isOpen) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKeyDown)
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      window.removeEventListener('keydown', onKeyDown)
      document.body.style.overflow = previousOverflow
    }
  }, [isOpen, onClose])

  return (
    <>
      <div
        onClick={onClose}
        aria-hidden="true"
        className={`fixed inset-0 z-40 bg-black/60 transition-opacity duration-200 ${
          isOpen ? 'opacity-100' : 'pointer-events-none opacity-0'
        }`}
      />

      <aside
        role="dialog"
        aria-modal="true"
        aria-label={encounter ? `Encounter ${encounter.id}` : 'Encounter details'}
        aria-hidden={!isOpen}
        className={`fixed inset-y-0 right-0 z-50 flex w-full max-w-[34rem] flex-col border-l border-line bg-base shadow-2xl shadow-black/50 transition-transform duration-300 ease-out ${
          isOpen ? 'translate-x-0' : 'translate-x-full'
        }`}
      >
        {encounter && (
          <>
            <header className="flex items-start justify-between gap-4 border-b border-line px-6 py-5">
              <div className="flex flex-col gap-2.5">
                <span className="text-[11px] font-semibold tracking-[0.14em] text-ink-faint uppercase">
                  Encounter Record
                </span>
                <span className="font-mono text-xl tracking-wider text-ink">{encounter.id}</span>
                <StatusBadge status={encounter.status} className="self-start" />
              </div>
              <button
                type="button"
                onClick={onClose}
                aria-label="Close encounter details"
                className="rounded border border-line p-2 text-ink-faint transition-colors hover:border-line-strong hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
              >
                <X className="h-4 w-4" strokeWidth={2} />
              </button>
            </header>

            <div className="scroll-slim flex-1 overflow-y-auto">
              <dl className="flex flex-col gap-5 border-b border-line px-6 py-5">
                <Field icon={MapPin} label="Location">
                  {encounter.location}
                </Field>
                <div className="grid grid-cols-2 gap-5">
                  <Field icon={CalendarClock} label="Time">
                    {encounter.timestamp}
                  </Field>
                  <Field icon={Timer} label="Duration">
                    <span className="font-mono">{encounter.duration}</span>
                  </Field>
                </div>
              </dl>

              <div className="px-6 py-5">
                <Transcript
                  messages={encounter.transcript}
                  title="Historical Transcript"
                  bodyClassName="max-h-none"
                />
              </div>
            </div>
          </>
        )}
      </aside>
    </>
  )
}

interface FieldProps {
  icon: LucideIcon
  label: string
  children: ReactNode
}

function Field({ icon: Icon, label, children }: FieldProps) {
  return (
    <div>
      <dt className="mb-1.5 flex items-center gap-2 text-[11px] font-semibold tracking-[0.14em] text-ink-faint uppercase">
        <Icon className="h-3.5 w-3.5" strokeWidth={2} />
        {label}
      </dt>
      <dd className="text-sm leading-relaxed text-ink">{children}</dd>
    </div>
  )
}
