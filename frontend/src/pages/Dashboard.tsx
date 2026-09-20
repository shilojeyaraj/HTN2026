import { BrainActivity } from '../components/BrainActivity'
import { PatternInsightsCard } from '../components/PatternInsights'
import { RescueScene3D } from '../components/RescueScene3D'
import { SensorGauges } from '../components/SensorGauges'
import { Transcript } from '../components/Transcript'
import { useMapStream } from '../hooks/useMapStream'
import { activeEncounter } from '../data/mockData'

export function Dashboard() {
  const { payload } = useMapStream()

  return (
    <div className="flex flex-col gap-6">
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <RescueScene3D payload={payload} />
        <Transcript
          messages={activeEncounter.transcript}
          listening
          className="min-h-0"
          bodyClassName="max-h-[520px]"
        />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <SensorGauges sensors={payload?.sensor_state ?? null} />
        <BrainActivity events={payload?.brain_activity ?? []} />
        <PatternInsightsCard insights={payload?.insights ?? null} />
      </div>
    </div>
  )
}
