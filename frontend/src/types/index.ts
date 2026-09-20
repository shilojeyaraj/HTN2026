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
  battery: number | null
  cameraName: string
}

export type Tab = 'dashboard' | 'telemetry' | 'brain' | 'encounters'

export interface LiveReading {
  value: number | number[] | null
  age_s: number | null
  received_at: number | null
  status: 'live' | 'stale' | 'unavailable'
  subscription: 'pending' | 'active' | 'failed' | 'unsupported'
}

export interface LiveAction {
  id: number
  name: string
  requested_args: string
  applied_args: Record<string, unknown> | null
  mode: string
  status: string
  started_at: number
  finished_at: number | null
  duration_ms: number | null
  result: Record<string, unknown> | null
}

export interface LiveMission {
  phase: string
  reason: string | null
  mode: string | null
  goal: string | null
  model: string | null
  scene: string | null
  scene_at: number | null
  findings: { type: string; description: string }[]
  search_active: boolean
  search_rotation_deg: number
  retry_in_s: number
  failures: number
  cycles: number
  inference_ms: number | null
  last_command: string | null
  actions: LiveAction[]
}

export interface LiveSnapshot {
  schema: 'rover.v1'
  timestamp: number
  rover: {
    connected: boolean
    sources: Record<'position_m' | 'attitude_deg' | 'velocity_mps' | 'status' | 'tof_mm' | 'battery_percent', LiveReading>
    flags: Record<string, boolean> | null
    trail: number[][]
    alerts: { name: string; timestamp: number }[]
    stop: { status: string; requested_at: number; motion: string; detail: string | null } | null
    camera: {
      frame_age_s: number | null
      decode_fps: number
      decode_failures: number
      stream_restarts: number
      reader_alive: boolean
    }
  }
  mission: LiveMission
}

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
