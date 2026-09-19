import { Bot, Headset, MessagesSquare, User } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { useEffect, useRef } from 'react'
import type { Speaker, TranscriptMessage } from '../types'
import { Panel } from './ui/Panel'

const speakerConfig: Record<Speaker, { label: string; icon: LucideIcon; accent: string; text: string }> = {
  person: {
    label: 'Person',
    icon: User,
    accent: 'border-l-ink',
    text: 'text-ink',
  },
  driver: {
    label: 'Driver',
    icon: Headset,
    accent: 'border-l-accent',
    text: 'text-ink',
  },
  rover: {
    label: 'Rover',
    icon: Bot,
    accent: 'border-l-line-strong',
    text: 'text-ink-muted',
  },
}

interface TranscriptProps {
  messages: TranscriptMessage[]
  title?: string
  listening?: boolean
  className?: string
  bodyClassName?: string
}

export function Transcript({
  messages,
  title = 'Communication Transcript',
  listening = false,
  className = '',
  bodyClassName = 'max-h-[420px]',
}: TranscriptProps) {
  const listRef = useRef<HTMLOListElement>(null)

  // Pin to the newest message without scrolling the page itself.
  useEffect(() => {
    const container = listRef.current?.parentElement
    if (container) container.scrollTop = container.scrollHeight
  }, [messages])

  return (
    <Panel
      title={title}
      icon={MessagesSquare}
      className={className}
      bodyClassName={`scroll-slim overflow-y-auto ${bodyClassName}`}
      actions={
        <span className="font-mono text-[11px] text-ink-faint">
          {messages.length} MSG
        </span>
      }
    >
      <ol ref={listRef} className="flex flex-col gap-4 px-5 py-4">
        {messages.map((message) => {
          const { label, icon: Icon, accent, text } = speakerConfig[message.speaker]
          return (
            <li key={message.id} className={`border-l-2 pl-4 ${accent}`}>
              <div className="mb-1.5 flex items-center gap-2">
                <Icon className="h-3.5 w-3.5 text-ink-faint" strokeWidth={2} />
                <span className="text-[11px] font-semibold tracking-[0.14em] text-ink-muted uppercase">
                  {label}
                </span>
                <span className="font-mono text-[11px] text-ink-faint">{message.timestamp}</span>
              </div>
              <p className={`text-[15px] leading-relaxed ${text}`}>{message.text}</p>
            </li>
          )
        })}
      </ol>

      {listening && (
        <div className="sticky bottom-0 flex items-center gap-2.5 border-t border-line bg-surface/95 px-5 py-3 backdrop-blur-sm">
          <ListeningBars />
          <span className="text-[11px] font-medium tracking-[0.14em] text-ink-faint uppercase">
            Listening
          </span>
        </div>
      )}
    </Panel>
  )
}

function ListeningBars() {
  return (
    <span className="flex h-3 items-center gap-[3px]" aria-hidden="true">
      {[0, 0.2, 0.4].map((delay) => (
        <span
          key={delay}
          className="animate-listen h-3 w-[3px] rounded-full bg-live/70"
          style={{ animationDelay: `${delay}s` }}
        />
      ))}
    </span>
  )
}
