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

export type Tab = 'dashboard' | 'telemetry' | 'brain' | 'encounters'

/* --------------------------------------------------------------------------
 * Telemetry
 *
 * Field names mirror the Python backend so swapping the mock feed for a live
 * one is a change to the data layer only. Backend sources are noted per block.
 * ------------------------------------------------------------------------ */

/** control/arbiter.py priority mux: reflex > brain > watchdog halt. */
export type CmdVelSource = 'reflex' | 'brain' | 'watchdog'

/** brain/safety.py SayCan gate. */
export type SafetyStatus = 'OK' | 'VETO'

/** laptop/server.py depth reply status. */
export type DepthStatus = 'ok' | 'uncertain' | 'error' | 'preview'

/** perception/sensors.py read_temperature(). */
export type TempStatus = 'ok' | 'warm' | 'overheat'

/** perception/sensors.py read_audio() event kinds. */
export type AudioEventKind = 'distress' | 'sound' | 'voice'

/** brain/state.py Detection TypedDict. bbox is dropped; it is unused for depth. */
export interface Detection {
  label: string
  distanceM: number
  bearingDeg: number
}

export interface AudioEvent {
  kind: AudioEventKind
  label: string | null
  text: string | null
  bearingDeg: number
}

export interface VetoRecord {
  id: string
  verb: string
  reason: string
  clock: string
}

export interface DriveState {
  linear: number
  angular: number
  source: CmdVelSource
  watchdogAgeS: number
  watchdogTimeoutS: number
  publishHz: number
}

export interface ReflexState {
  blocked: boolean
  clearanceM: number
  stopDistanceM: number
  sinceTriggerS: number | null
  hz: number
}

export interface SafetyState {
  status: SafetyStatus
  reason: string | null
  gatedVerbs: string[]
  minClearanceM: number
  recent: VetoRecord[]
}

export interface DepthState {
  status: DepthStatus
  relativeProximity: { left: number; center: number; right: number } | null
  preferredDirection: 'left' | 'center' | 'right' | null
  frameId: number
  processingMs: number
  serverFrameAgeMs: number
  ageS: number
  stalenessLimitS: number
  fps: number
  advisoryOnly: boolean
  host: string
  port: number
}

export interface PoseState {
  x: number
  y: number
  headingDeg: number
  trail: { x: number; y: number }[]
}

export interface EncoderState {
  leftTicksTotal: number
  rightTicksTotal: number
  estimatedVelocityMps: number
  commandedVelocityMps: number
  slipDetected: boolean
  ticksPerMeter: number
}

export interface GyroState {
  pitchDeg: number
  rollDeg: number
  accelZG: number
  tipped: boolean
  bump: boolean
}

export interface TemperatureState {
  celsius: number
  status: TempStatus
  warmC: number
  overheatC: number
  history: number[]
}

export interface AudioState {
  db: number
  event: AudioEvent | null
  history: number[]
}

/** Not backed by a module yet: CLAUDE.md lists GPS hardware, nothing reads it. */
export interface GpsState {
  latitude: number
  longitude: number
  fix: 'none' | '2D' | '3D'
  satellites: number
  hdop: number
}

export interface TelemetrySnapshot {
  uptimeS: number
  clock: string
  drive: DriveState
  reflex: ReflexState
  safety: SafetyState
  detections: Detection[]
  depth: DepthState
  pose: PoseState
  encoder: EncoderState
  gyro: GyroState
  temperature: TemperatureState
  audio: AudioState
  gps: GpsState
  speedHistory: number[]
}

/* --------------------------------------------------------------------------
 * Brain
 * ------------------------------------------------------------------------ */

/** control/controller.py + brain/loop.py verb result statuses. */
export type ToolResultStatus = 'completed' | 'stopped_by_obstacle' | 'vetoed' | 'error' | 'read'

export interface ToolCallRecord {
  id: string
  episode: number
  name: string
  args: string
  result: string
  status: ToolResultStatus
  clock: string
}

export interface EpisodeRecord {
  id: string
  number: number
  path: 'parser' | 'backboard'
  durationMs: number
  toolRounds: number
  summary: string
  clock: string
}

export interface BrainSession {
  provider: string
  plannerModel: string
  visionModel: string
  threadId: string
  assistantId: string
  toolRounds: number
  maxToolRounds: number
  status: 'idle' | 'thinking' | 'requires_action'
  episodeGapS: number
}

export interface SceneState {
  text: string
  detections: Detection[]
  frameId: number
  ageS: number
}

export interface VerbUsage {
  name: string
  kind: 'motion' | 'speech' | 'read'
  calls: number
  lastUsedClock: string | null
}

export interface ParserState {
  modelId: string
  hits: number
  misses: number
  lastCommand: string | null
  lastParsed: { verb: string; args: Record<string, unknown> } | null
  lastLatencyMs: number
}

export interface TtsUtterance {
  id: string
  text: string
  status: 'queued' | 'playing' | 'done'
}

export interface VoiceState {
  transcript: string | null
  pushToTalkHeld: boolean
  gpioPin: number
  sttModel: string
  tts: TtsUtterance[]
}

export interface GoalState {
  current: { x: number; y: number } | null
  lastUserCommand: string | null
  safetyStatus: SafetyStatus
}

export interface BrainSnapshot {
  session: BrainSession
  episodes: EpisodeRecord[]
  toolCalls: ToolCallRecord[]
  scene: SceneState
  verbs: VerbUsage[]
  parser: ParserState
  voice: VoiceState
  goal: GoalState
}
