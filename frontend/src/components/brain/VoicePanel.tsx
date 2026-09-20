import { Mic } from 'lucide-react'
import type { TtsUtterance, VoiceState } from '../../types'
import { StateChip } from '../ui/StateChip'
import type { ChipTone } from '../ui/StateChip'
import { Tile } from '../ui/Tile'

const ttsTone: Record<TtsUtterance['status'], ChipTone> = {
  queued: 'muted',
  playing: 'live',
  done: 'muted',
}

interface VoicePanelProps {
  voice: VoiceState
  className?: string
}

export function VoicePanel({ voice, className = '' }: VoicePanelProps) {
  return (
    <Tile
      title="Voice I/O"
      icon={Mic}
      className={className}
      bodyClassName="flex flex-col gap-2 px-3 py-2.5"
      actions={
        <StateChip
          label={voice.pushToTalkHeld ? 'PTT held' : `GPIO ${voice.gpioPin}`}
          tone={voice.pushToTalkHeld ? 'live' : 'muted'}
          pulse={voice.pushToTalkHeld}
        />
      }
    >
      <div className="shrink-0">
        <span className="text-[10px] font-semibold tracking-[0.14em] text-ink-faint uppercase">
          Last transcript
        </span>
        <p className="truncate text-[13px] text-ink">
          {voice.transcript ? `"${voice.transcript}"` : 'Nothing heard yet'}
        </p>
        <p className="truncate font-mono text-[10px] text-ink-faint">
          Baseten · {voice.sttModel}
        </p>
      </div>

      <div className="flex min-h-0 flex-1 flex-col gap-1 border-t border-line pt-2">
        <span className="text-[10px] font-semibold tracking-[0.14em] text-ink-faint uppercase">
          ElevenLabs queue
        </span>
        <ul className="scroll-slim flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto">
          {voice.tts.length === 0 ? (
            <li className="text-[11px] text-ink-faint">Nothing spoken yet.</li>
          ) : (
            voice.tts.map((utterance) => (
              <li key={utterance.id} className="flex items-center gap-2">
                <StateChip
                  label={utterance.status}
                  tone={ttsTone[utterance.status]}
                  dot={utterance.status === 'playing'}
                  pulse={utterance.status === 'playing'}
                  className="shrink-0"
                />
                <span
                  className={`truncate text-[11px] ${
                    utterance.status === 'done' ? 'text-ink-faint' : 'text-ink-muted'
                  }`}
                >
                  {utterance.text}
                </span>
              </li>
            ))
          )}
        </ul>
      </div>
    </Tile>
  )
}
