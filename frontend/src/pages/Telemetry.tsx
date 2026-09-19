import { AudioMeter } from '../components/telemetry/AudioMeter'
import { DepthLink } from '../components/telemetry/DepthLink'
import { DepthProximity } from '../components/telemetry/DepthProximity'
import { DriveStatus } from '../components/telemetry/DriveStatus'
import { Encoders } from '../components/telemetry/Encoders'
import { GpsPanel } from '../components/telemetry/GpsPanel'
import { ImuPanel } from '../components/telemetry/ImuPanel'
import { ObstacleRadar } from '../components/telemetry/ObstacleRadar'
import { PoseTrack } from '../components/telemetry/PoseTrack'
import { ReflexMonitor } from '../components/telemetry/ReflexMonitor'
import { SafetyGate } from '../components/telemetry/SafetyGate'
import { StatusStrip } from '../components/telemetry/StatusStrip'
import { TemperaturePanel } from '../components/telemetry/TemperaturePanel'
import type { BrainSnapshot, TelemetrySnapshot } from '../types'

interface TelemetryProps {
  telemetry: TelemetrySnapshot
  brain: BrainSnapshot
}

export function Telemetry({ telemetry, brain }: TelemetryProps) {
  return (
    <div className="flex flex-col gap-3">
      <StatusStrip telemetry={telemetry} />

      <div className="grid grid-cols-1 gap-3 md:auto-rows-[minmax(146px,auto)] md:grid-cols-6 xl:grid-cols-12">
        <ObstacleRadar
          detections={telemetry.detections}
          blocked={telemetry.reflex.blocked}
          className="md:col-span-3 md:row-span-2 xl:col-span-4"
        />
        <PoseTrack
          pose={telemetry.pose}
          goal={brain.goal.current}
          className="md:col-span-3 md:row-span-2 xl:col-span-4"
        />
        <DriveStatus drive={telemetry.drive} className="md:col-span-3 xl:col-span-4" />
        <DepthProximity depth={telemetry.depth} className="md:col-span-3 xl:col-span-4" />

        <AudioMeter audio={telemetry.audio} className="md:col-span-3 xl:col-span-4" />
        <ImuPanel gyro={telemetry.gyro} className="md:col-span-3 xl:col-span-4" />
        <Encoders encoder={telemetry.encoder} className="md:col-span-3 xl:col-span-4" />

        <DepthLink depth={telemetry.depth} className="md:col-span-3 xl:col-span-4" />
        <ReflexMonitor reflex={telemetry.reflex} className="md:col-span-3 xl:col-span-2" />
        <SafetyGate safety={telemetry.safety} className="md:col-span-3 xl:col-span-2" />
        <TemperaturePanel
          temperature={telemetry.temperature}
          className="md:col-span-3 xl:col-span-2"
        />
        <GpsPanel gps={telemetry.gps} className="md:col-span-3 xl:col-span-2" />
      </div>
    </div>
  )
}
