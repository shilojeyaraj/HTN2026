import { CameraFeed } from '../components/CameraFeed'
import { CurrentEncounter } from '../components/CurrentEncounter'
import { Transcript } from '../components/Transcript'
import { activeEncounter, rover } from '../data/mockData'

export function Dashboard() {
  return (
    <div className="flex flex-col gap-6">
      <CameraFeed rover={rover} />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[2fr_1fr]">
        <Transcript messages={activeEncounter.transcript} listening />
        <CurrentEncounter encounter={activeEncounter} className="self-start" />
      </div>
    </div>
  )
}
