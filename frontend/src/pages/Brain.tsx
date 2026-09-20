import { BrainSessionPanel } from '../components/brain/BrainSessionPanel'
import { EpisodeTimeline } from '../components/brain/EpisodeTimeline'
import { GoalPanel } from '../components/brain/GoalPanel'
import { ParserFastPath } from '../components/brain/ParserFastPath'
import { SceneDescription } from '../components/brain/SceneDescription'
import { ToolCallLog } from '../components/brain/ToolCallLog'
import { VerbPalette } from '../components/brain/VerbPalette'
import { VoicePanel } from '../components/brain/VoicePanel'
import type { BrainSnapshot } from '../types'

interface BrainProps {
  brain: BrainSnapshot
}

export function Brain({ brain }: BrainProps) {
  return (
    <div className="grid grid-cols-1 gap-3 md:auto-rows-[minmax(152px,auto)] md:grid-cols-6 xl:grid-cols-12">
      <ToolCallLog
        toolCalls={brain.toolCalls}
        className="max-h-[420px] md:col-span-3 md:row-span-2 md:max-h-none xl:col-span-5"
      />
      <SceneDescription
        scene={brain.scene}
        className="md:col-span-3 md:row-span-2 xl:col-span-4"
      />
      <BrainSessionPanel session={brain.session} className="md:col-span-3 xl:col-span-3" />
      <ParserFastPath parser={brain.parser} className="md:col-span-3 xl:col-span-3" />

      <EpisodeTimeline
        episodes={brain.episodes}
        className="max-h-[260px] md:col-span-6 md:max-h-none xl:col-span-5"
      />
      <VoicePanel voice={brain.voice} className="md:col-span-3 xl:col-span-4" />
      <GoalPanel goal={brain.goal} className="md:col-span-3 xl:col-span-3" />

      <VerbPalette verbs={brain.verbs} className="md:col-span-6 xl:col-span-12" />
    </div>
  )
}
