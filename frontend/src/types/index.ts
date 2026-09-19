export type Speaker = 'person' | 'driver' | 'rover'

export type EncounterStatus = 'rescued' | 'located' | 'no-contact'

export interface TranscriptMessage {
  id: string
  speaker: Speaker
  text: string
  timestamp: string
}

export interface Encounter {
  id: string
  status: EncounterStatus
  location: string
  timestamp: string
  duration: string
  transcript: TranscriptMessage[]
}

export interface ActiveEncounter extends Encounter {
  startedAt: string
}

export interface Rover {
  id: string
  connected: boolean
  battery: number
  cameraName: string
}

export type Tab = 'dashboard' | 'encounters'

// --- Map types ---

export interface SoundSource {
  x: number
  y: number
  kind: 'distress' | 'sound' | 'voice' | 'speech'
  label: string
  db?: number
  final?: boolean
}

export interface HeatPoint {
  x: number
  y: number
  celsius: number
  status: 'ok' | 'warm' | 'overheat'
}

export interface Hazard {
  x: number
  y: number
  type: 'bump' | 'tipped'
}

export interface Annotation {
  x: number
  y: number
  text: string
  source: string
}

export interface MapPayload {
  rover_pose: [number, number, number]
  grid: number[]
  grid_width: number
  grid_height: number
  grid_resolution_m: number
  sound_sources: SoundSource[]
  heat_points: HeatPoint[]
  hazards: Hazard[]
  annotations: Annotation[]
  trail: number[][]
}
