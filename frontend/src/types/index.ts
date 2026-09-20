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
  /** Base64-encoded uint8 array (when grid_encoding === "base64_uint8")
   *  or legacy float array (when grid_encoding is absent). */
  grid: string | number[]
  grid_encoding?: 'base64_uint8'
  grid_width: number
  grid_height: number
  grid_resolution_m: number
  sound_sources: SoundSource[]
  heat_points: HeatPoint[]
  hazards: Hazard[]
  annotations: Annotation[]
  trail: number[][]
  brain_activity?: BrainActivityEvent[]
  sensor_state?: SensorSnapshot
  insights?: PatternInsights | null
  transcript?: TranscriptMessage[]
}

export interface BrainActivityEvent {
  tool: string
  args: Record<string, unknown>
  result: Record<string, unknown>
  timestamp: number
}

export interface SensorSnapshot {
  temperature: { celsius: number; status: 'ok' | 'warm' | 'overheat' }
  audio: { db: number; event: { kind: string; label: string } | null }
  gyro: { pitch_deg: number; roll_deg: number; tipped: boolean; bump: boolean }
}

export interface PatternInsights {
  summary?: string
  rescue_rate?: string
  avg_duration?: string
  [key: string]: unknown
}
