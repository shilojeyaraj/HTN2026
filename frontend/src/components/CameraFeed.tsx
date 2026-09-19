import { Flashlight, Maximize2, SignalHigh } from 'lucide-react'
import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import type { Rover } from '../types'

interface CameraFeedProps {
  rover: Rover
}

export function CameraFeed({ rover }: CameraFeedProps) {
  const [lampOn, setLampOn] = useState(true)
  const [clock, setClock] = useState(() => formatClock(new Date()))

  useEffect(() => {
    const id = window.setInterval(() => setClock(formatClock(new Date())), 1000)
    return () => window.clearInterval(id)
  }, [])

  return (
    <section className="overflow-hidden rounded-lg border border-line bg-surface shadow-lg shadow-black/30">
      <div className="relative aspect-video w-full bg-black">
        <DisasterScene lampOn={lampOn} />

        <div className="cam-scanlines pointer-events-none absolute inset-0" />
        <div className="cam-vignette pointer-events-none absolute inset-0" />
        <div className="pointer-events-none absolute inset-0 overflow-hidden">
          <div className="animate-sweep h-1/3 w-full bg-gradient-to-b from-transparent via-white/4 to-transparent" />
        </div>

        <CornerBrackets />

        <div className="pointer-events-none absolute inset-0 flex flex-col justify-between p-4 sm:p-5">
          <div className="flex items-start justify-between gap-3">
            <span className="flex items-center gap-2 rounded border border-live/30 bg-black/55 px-2.5 py-1.5 text-[11px] font-semibold tracking-[0.16em] text-live uppercase backdrop-blur-[2px]">
              <span className="animate-blip h-2 w-2 rounded-full bg-live" />
              Live
            </span>

            <div className="flex flex-col items-end gap-1.5 text-right">
              <span className="rounded border border-white/10 bg-black/55 px-2.5 py-1.5 font-mono text-[11px] tracking-[0.1em] text-ink uppercase backdrop-blur-[2px]">
                {rover.cameraName} <span className="text-ink-faint">//</span> {rover.id}
              </span>
              <span className="rounded border border-white/10 bg-black/55 px-2.5 py-1.5 font-mono text-[11px] tracking-[0.1em] text-ink-muted backdrop-blur-[2px]">
                {clock}
              </span>
            </div>
          </div>

          <div className="flex items-end justify-between gap-3">
            <span className="flex items-center gap-1.5 rounded border border-white/10 bg-black/55 px-2.5 py-1.5 font-mono text-[11px] tracking-[0.1em] text-ink-muted backdrop-blur-[2px]">
              <SignalHigh className="h-3.5 w-3.5 text-live" strokeWidth={2} />
              1080p · 24FPS
            </span>

            <div className="pointer-events-auto flex items-center gap-2">
              <FeedButton
                label={lampOn ? 'Turn headlamp off' : 'Turn headlamp on'}
                active={lampOn}
                onClick={() => setLampOn((on) => !on)}
              >
                <Flashlight className="h-4 w-4" strokeWidth={2} />
              </FeedButton>
              <FeedButton label="Expand feed">
                <Maximize2 className="h-4 w-4" strokeWidth={2} />
              </FeedButton>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

interface FeedButtonProps {
  label: string
  active?: boolean
  onClick?: () => void
  children: ReactNode
}

function FeedButton({ label, active = false, onClick, children }: FeedButtonProps) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      aria-pressed={onClick ? active : undefined}
      onClick={onClick}
      className={`rounded border bg-black/55 p-2 backdrop-blur-[2px] transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent ${
        active
          ? 'border-accent/40 text-accent'
          : 'border-white/10 text-ink-muted hover:border-white/25 hover:text-ink'
      }`}
    >
      {children}
    </button>
  )
}

function CornerBrackets() {
  const base = 'pointer-events-none absolute h-6 w-6 border-white/25'
  return (
    <>
      <span className={`${base} top-3 left-3 border-t border-l`} />
      <span className={`${base} top-3 right-3 border-t border-r`} />
      <span className={`${base} bottom-3 left-3 border-b border-l`} />
      <span className={`${base} right-3 bottom-3 border-r border-b`} />
    </>
  )
}

/**
 * Stand-in for the rover's optical feed: a collapsed structure at night, lit by
 * the rover's headlamp. Drawn inline so the demo carries no image assets.
 */
function DisasterScene({ lampOn }: { lampOn: boolean }) {
  return (
    <svg
      className="absolute inset-0 h-full w-full"
      viewBox="0 0 1600 900"
      preserveAspectRatio="xMidYMid slice"
      role="img"
      aria-label="Rover camera view of a collapsed structure at night"
    >
      <defs>
        <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#16222e" />
          <stop offset="55%" stopColor="#0e161f" />
          <stop offset="100%" stopColor="#080d12" />
        </linearGradient>
        <radialGradient id="lamp" cx="0.5" cy="0.92" r="0.75">
          <stop offset="0%" stopColor="#dbeafe" stopOpacity="0.20" />
          <stop offset="45%" stopColor="#bfdbfe" stopOpacity="0.07" />
          <stop offset="100%" stopColor="#bfdbfe" stopOpacity="0" />
        </radialGradient>
        <linearGradient id="cone" x1="0" y1="1" x2="0" y2="0">
          <stop offset="0%" stopColor="#e2e8f0" stopOpacity="0.13" />
          <stop offset="100%" stopColor="#e2e8f0" stopOpacity="0" />
        </linearGradient>
        <filter id="haze" x="-30%" y="-30%" width="160%" height="160%">
          <feGaussianBlur stdDeviation="38" />
        </filter>
      </defs>

      <rect width="1600" height="900" fill="url(#sky)" />

      {/* Distant skyline of damaged structures */}
      <g fill="#0d151d">
        <polygon points="0,620 0,430 90,418 104,452 168,404 196,448 262,422 288,470 340,446 340,620" />
        <polygon points="372,620 372,352 438,338 452,392 516,318 532,376 596,360 596,620" />
        <polygon points="1020,620 1020,392 1078,378 1092,424 1150,364 1178,416 1236,398 1236,620" />
        <polygon points="1268,620 1268,436 1340,414 1356,462 1422,406 1448,452 1520,430 1600,446 1600,620" />
      </g>

      {/* Leaning facade, partially sheared */}
      <g fill="#111c26">
        <polygon points="620,620 648,300 742,286 790,620" />
        <polygon points="790,620 800,318 868,336 884,620" />
      </g>
      <g stroke="#0a1118" strokeWidth="3" opacity="0.9">
        <line x1="656" y1="392" x2="748" y2="382" />
        <line x1="650" y1="470" x2="754" y2="462" />
        <line x1="644" y1="548" x2="762" y2="542" />
        <line x1="806" y1="404" x2="872" y2="418" />
        <line x1="802" y1="496" x2="878" y2="506" />
      </g>

      {/* Dust haze hanging in the lamp beam */}
      <g filter="url(#haze)" opacity="0.5">
        <ellipse cx="760" cy="596" rx="420" ry="86" fill="#26333f" />
        <ellipse cx="1140" cy="648" rx="300" ry="62" fill="#1d2833" />
        <ellipse cx="320" cy="660" rx="280" ry="58" fill="#1d2833" />
      </g>

      {lampOn && (
        <>
          <polygon points="688,900 912,900 1240,392 360,392" fill="url(#cone)" />
          <rect width="1600" height="900" fill="url(#lamp)" />
        </>
      )}

      {/* Mid-ground slabs, lighter on faces angled toward the lamp */}
      <g>
        <polygon points="404,720 690,586 742,638 476,780" fill="#1b2734" />
        <polygon points="690,586 742,638 760,632 706,578" fill="#26374a" />
        <polygon points="880,630 1164,566 1208,646 916,724" fill="#182430" />
        <polygon points="880,630 1164,566 1172,586 890,650" fill="#243444" />
        <polygon points="1180,700 1420,648 1468,742 1216,796" fill="#16212d" />
      </g>

      {/* Exposed rebar */}
      <g stroke="#2b3a4a" strokeWidth="4" fill="none" strokeLinecap="round">
        <path d="M700 590 C 726 548, 762 560, 786 524" />
        <path d="M722 600 C 754 566, 786 582, 816 548" />
        <path d="M1150 570 C 1182 534, 1214 552, 1238 520" />
        <path d="M1172 580 C 1206 552, 1232 570, 1262 544" />
      </g>

      {/* Foreground rubble ridge, closest to the lens and darkest */}
      <polygon
        points="0,900 0,796 132,742 268,790 392,736 530,792 668,744 812,800 946,748 1094,804 1236,752 1380,806 1520,760 1600,792 1600,900"
        fill="#0a1017"
      />
      <polyline
        points="0,796 132,742 268,790 392,736 530,792 668,744 812,800 946,748 1094,804 1236,752 1380,806 1520,760 1600,792"
        fill="none"
        stroke="#243444"
        strokeWidth="4"
        opacity="0.75"
      />

      {/* Airborne dust caught in the beam */}
      <g fill="#cbd5e1">
        <circle cx="612" cy="524" r="2.5" opacity="0.30" />
        <circle cx="758" cy="452" r="2" opacity="0.22" />
        <circle cx="884" cy="560" r="3" opacity="0.26" />
        <circle cx="972" cy="486" r="2" opacity="0.18" />
        <circle cx="520" cy="620" r="2.5" opacity="0.24" />
        <circle cx="1088" cy="602" r="2" opacity="0.20" />
        <circle cx="690" cy="676" r="3" opacity="0.16" />
        <circle cx="1210" cy="516" r="2.5" opacity="0.18" />
      </g>
    </svg>
  )
}

function formatClock(date: Date): string {
  return date.toLocaleTimeString('en-GB', { hour12: false })
}
