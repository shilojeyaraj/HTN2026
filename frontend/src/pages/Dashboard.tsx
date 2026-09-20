import { BrainActivity } from '../components/BrainActivity'
import { DrivingView3D } from '../components/DrivingView3D'
import { MappingView3D } from '../components/MappingView3D'
import { PatternInsightsCard } from '../components/PatternInsights'
import { SensorGauges } from '../components/SensorGauges'
import { Transcript } from '../components/Transcript'
import { useMapStream } from '../hooks/useMapStream'
import { activeEncounter } from '../data/mockData'

export function Dashboard() {
  const { payload } = useMapStream()

  return (
    <div className="flex flex-col gap-6">
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <DrivingView3D payload={payload} />
        <MappingView3D payload={payload} />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <SensorGauges sensors={payload?.sensor_state ?? null} />
        <BrainActivity events={payload?.brain_activity ?? []} />
        <PatternInsightsCard insights={payload?.insights ?? null} />
      </div>

      <Transcript
        messages={activeEncounter.transcript}
        listening
        className="min-h-0"
        bodyClassName="max-h-[320px]"
      />
    </div>
  )
}
