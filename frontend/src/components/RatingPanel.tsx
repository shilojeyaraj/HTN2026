import { ThumbsUp, ThumbsDown, Volume2, Brain } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import type { BrainActivityEvent } from '../types'
import { Panel } from './ui/Panel'

interface RatingPanelProps {
  brainEvents: BrainActivityEvent[]
}

interface RatingEntry {
  id: number
  text: string
  timestamp: number
  rating: 'up' | 'down' | null
}

export function RatingPanel({ brainEvents }: RatingPanelProps) {
  const [entries, setEntries] = useState<RatingEntry[]>([])
  const lastSeenRef = useRef(0)

  useEffect(() => {
    // Find new speak() calls from brain events
    const speakCalls = brainEvents
      .filter((e) => e.tool === 'speak' && e.timestamp > lastSeenRef.current)
      .map((e, i) => ({
        id: e.timestamp + i,
        text: (e.args as Record<string, unknown>).text as string || '',
        timestamp: e.timestamp,
        rating: null as 'up' | 'down' | null,
      }))

    if (speakCalls.length > 0) {
      lastSeenRef.current = speakCalls[speakCalls.length - 1].timestamp
      setEntries((prev) => [...speakCalls, ...prev].slice(0, 10))
    }
  }, [brainEvents])

  const rate = (id: number, rating: 'up' | 'down') => {
    setEntries((prev) =>
      prev.map((e) => (e.id === id ? { ...e, rating } : e))
    )

    // Send rating to the WebSocket server (piggyback on the map stream)
    // The server can store this in MongoDB for training weights
    const ws = new WebSocket(`ws://${window.location.hostname}:8766`)
    ws.onopen = () => {
      ws.send(JSON.stringify({ type: 'rating', id, rating }))
      ws.close()
    }
  }

  return (
    <Panel
      title="TTS Evaluation"
      icon={Volume2}
      actions={
        <span className="font-mono text-[11px] text-ink-faint">
          {entries.filter((e) => e.rating).length}/{entries.length} rated
        </span>
      }
    >
      <div className="flex flex-col gap-2 px-5 py-4">
        {entries.length === 0 ? (
          <div className="flex items-center gap-2.5 py-4 text-sm text-ink-faint">
            <Brain className="h-4 w-4" strokeWidth={2} />
            <span>Waiting for the rover to speak...</span>
          </div>
        ) : (
          entries.map((entry) => (
            <div
              key={entry.id}
              className={`rounded border px-3.5 py-2.5 transition-colors ${
                entry.rating === 'up'
                  ? 'border-live/30 bg-live/5'
                  : entry.rating === 'down'
                  ? 'border-alert/30 bg-alert/5'
                  : 'border-line/50 bg-surface/50'
              }`}
            >
              <p className="mb-2 text-sm text-ink">"{entry.text}"</p>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => rate(entry.id, 'up')}
                  className={`flex items-center gap-1.5 rounded px-2.5 py-1.5 text-xs font-semibold transition-colors ${
                    entry.rating === 'up'
                      ? 'bg-live/20 text-live'
                      : 'text-ink-faint hover:bg-live/10 hover:text-live'
                  }`}
                >
                  <ThumbsUp className="h-3.5 w-3.5" strokeWidth={2} />
                  Good
                </button>
                <button
                  onClick={() => rate(entry.id, 'down')}
                  className={`flex items-center gap-1.5 rounded px-2.5 py-1.5 text-xs font-semibold transition-colors ${
                    entry.rating === 'down'
                      ? 'bg-alert/20 text-alert'
                      : 'text-ink-faint hover:bg-alert/10 hover:text-alert'
                  }`}
                >
                  <ThumbsDown className="h-3.5 w-3.5" strokeWidth={2} />
                  Needs work
                </button>
                <span className="ml-auto font-mono text-[10px] text-ink-faint">
                  {new Date(entry.timestamp * 1000).toLocaleTimeString('en-US', { hour12: false })}
                </span>
              </div>
            </div>
          ))
        )}
      </div>
    </Panel>
  )
}
