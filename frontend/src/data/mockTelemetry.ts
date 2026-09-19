import type {
  AudioEvent,
  CmdVelSource,
  DepthStatus,
  Detection,
  TempStatus,
  ToolResultStatus,
} from '../types'

/**
 * Mock telemetry source for the Telemetry and Brain tabs.
 *
 * Everything here is a pure function of elapsed seconds inside a fixed loop, so
 * every tile stays in sync off a single timer and the demo reliably walks
 * through the interesting states (reflex stop, safety veto, depth dropout,
 * overheat, tip, wheel slip) instead of idling. The event script mirrors
 * build_events() in control/fake_robot_full.py.
 */

export const CYCLE_S = 36
export const TICK_MS = 200

// Backend constants, re-exported so tiles can label their own thresholds
// instead of hardcoding them in JSX.
export const REFLEX_STOP_DISTANCE_M = 0.3
export const SAYCAN_MIN_CLEARANCE_M = 0.4
export const WATCHDOG_TIMEOUT_S = 0.5
export const DEPTH_STALENESS_LIMIT_S = 2
export const ARBITER_HZ = 30
export const REFLEX_HZ = 30
export const CONTROLLER_HZ = 20
export const CAMERA_FPS = 15
export const CAMERA_RESOLUTION = '640x480'
export const TICKS_PER_METER = 800
export const SLIP_FACTOR = 0.35
export const WARM_C = 42
export const OVERHEAT_C = 55
export const EPISODE_GAP_S = 1
export const MAX_TOOL_ROUNDS = 6
export const SENSOR_RANGE_M = 2.5
export const GATE_CONE_DEG = 30

export const DEPTH_HOST = '172.20.10.11'
export const DEPTH_PORT = 8765
export const PTT_GPIO_PIN = 17
export const STT_MODEL = 'whisper-large-v3'
export const PARSER_MODEL_ID = 'qwen3-1.7b-verb-lora'
export const PLANNER_MODEL = 'gemini-2.5-pro'
export const VISION_MODEL = 'gemini-2.5-flash'
export const THREAD_ID = 'thr_9f2c41ae7b0d'
export const ASSISTANT_ID = 'asst_4d18c60b'

export const GPS_ORIGIN = { latitude: 43.4723, longitude: -80.5449 }

export const VERB_CATALOG: { name: string; kind: 'motion' | 'speech' | 'read' }[] = [
  { name: 'forward', kind: 'motion' },
  { name: 'backward', kind: 'motion' },
  { name: 'turn', kind: 'motion' },
  { name: 'stop', kind: 'motion' },
  { name: 'speak', kind: 'speech' },
  { name: 'get_obstacles', kind: 'read' },
  { name: 'get_state', kind: 'read' },
  { name: 'get_temperature', kind: 'read' },
  { name: 'get_audio', kind: 'read' },
  { name: 'get_gyro', kind: 'read' },
]

/* -------------------------------------------------------------------------
 * Helpers
 * ---------------------------------------------------------------------- */

export const clamp = (value: number, min: number, max: number) =>
  Math.min(max, Math.max(min, value))

export const clamp01 = (value: number) => clamp(value, 0, 1)

const lerp = (a: number, b: number, t: number) => a + (b - a) * clamp01(t)

/** Deterministic band-limited wobble in roughly -1..1, stable across renders. */
const noise = (t: number, seed: number) =>
  Math.sin(t * 2.3 + seed * 1.7) * 0.5 +
  Math.sin(t * 5.7 + seed * 3.1) * 0.32 +
  Math.sin(t * 11.3 + seed * 5.9) * 0.18

/** Rise-hold-fall envelope across an event's duration. */
const envelope = (progress: number) => Math.sin(Math.PI * clamp01(progress))

/* -------------------------------------------------------------------------
 * Motion profile
 * ---------------------------------------------------------------------- */

interface MotionSegment {
  until: number
  linear: number
  angular: number
}

// 0.3 m/s and 60 deg/s match control/controller.py.
const TURN_RAD_S = (60 * Math.PI) / 180

const MOTION: MotionSegment[] = [
  { until: 6, linear: 0.3, angular: 0 },
  { until: 9, linear: 0, angular: -TURN_RAD_S },
  { until: 11.5, linear: 0.3, angular: 0 },
  { until: 13.5, linear: 0, angular: 0 },
  { until: 16, linear: -0.3, angular: 0 },
  { until: 19, linear: 0, angular: TURN_RAD_S },
  { until: 25, linear: 0.3, angular: 0 },
  { until: 27.6, linear: 0, angular: 0 },
  { until: 31.5, linear: 0.3, angular: 0 },
  { until: 33.5, linear: 0, angular: -TURN_RAD_S },
  { until: CYCLE_S, linear: 0.3, angular: 0 },
]

const motionAt = (t: number) => MOTION.find((segment) => t < segment.until) ?? MOTION[0]

/** Approaches a wall around t=11, holds inside the reflex threshold, backs off. */
const frontClearanceM = (t: number) => {
  if (t < 9) return 2.2 + noise(t, 1) * 0.22
  if (t < 11.5) return lerp(1.6, 0.22, (t - 9) / 2.5)
  if (t < 13.5) return 0.22 + noise(t, 2) * 0.015
  if (t < 16) return lerp(0.24, 1.1, (t - 13.5) / 2.5)
  return 1.8 + noise(t, 3) * 0.38
}

const leftClearanceM = (t: number) => 1.55 + noise(t, 7) * 0.62
const rightClearanceM = (t: number) => 1.35 + noise(t, 13) * 0.58

// Wi-Fi hiccup: the depth link stalls, the brain command goes stale and the
// arbiter falls through to its watchdog halt.
const DEPTH_DROPOUT = { start: 21.6, end: 22.8 }

/* -------------------------------------------------------------------------
 * Scripted sensor events (mirrors control/fake_robot_full.py build_events)
 * ---------------------------------------------------------------------- */

export interface ScriptedEvent {
  t: number
  duration: number
  kind: 'distress' | 'voice' | 'sound' | 'temp' | 'tip' | 'bump' | 'wheel_slip'
  label?: string
  text?: string
  bearingDeg?: number
  dbBoost?: number
  deltaC?: number
  pitchDeg?: number
  accelSpikeG?: number
  side?: 'l' | 'r'
}

export const SCRIPT: ScriptedEvent[] = [
  {
    t: 2,
    duration: 2.2,
    kind: 'distress',
    label: 'scream',
    text: 'Help, I am under the slab!',
    bearingDeg: -24,
    dbBoost: 28,
  },
  {
    t: 8,
    duration: 2.4,
    kind: 'distress',
    label: 'call_for_help',
    text: 'Over here, please, I can hear you.',
    bearingDeg: 16,
    dbBoost: 24,
  },
  { t: 13, duration: 1.6, kind: 'sound', label: 'structural_creak', bearingDeg: 42, dbBoost: 18 },
  { t: 17, duration: 1.2, kind: 'voice', text: 'stop', bearingDeg: 0, dbBoost: 20 },
  { t: 20, duration: 6, kind: 'temp', deltaC: 38 },
  { t: 26, duration: 1.6, kind: 'tip', pitchDeg: 70 },
  { t: 28.5, duration: 0.5, kind: 'bump', accelSpikeG: 1.2 },
  { t: 30, duration: 1.8, kind: 'wheel_slip', side: 'l' },
]

const activeEvents = (t: number) =>
  SCRIPT.filter((event) => t >= event.t && t < event.t + event.duration)

const eventProgress = (event: ScriptedEvent, t: number) => (t - event.t) / event.duration

/* -------------------------------------------------------------------------
 * Scene narration, phase-keyed
 * ---------------------------------------------------------------------- */

const SCENE_LINES: { until: number; text: string }[] = [
  {
    until: 6,
    text: 'Collapsed corridor ahead. Debris piled along the right wall, roughly two metres of clear floor straight on. A voice was heard off to the left.',
  },
  {
    until: 9,
    text: 'Turning to face the left void. Splintered joists overhead, dust in the beam. No clear path yet on this bearing.',
  },
  {
    until: 13.5,
    text: 'A concrete slab blocks the path at close range. Free space to the left of the slab. Do not advance.',
  },
  {
    until: 19,
    text: 'Backed away from the slab. Reassessing: the corridor opens to the right past the fallen shelving.',
  },
  {
    until: 25,
    text: 'Advancing down the cleared side passage. Warm air from the far end, floor is uneven but passable.',
  },
  {
    until: 28,
    text: 'Heat source ahead and the floor pitches sharply. Holding position until the chassis settles.',
  },
  {
    until: CYCLE_S,
    text: 'Chassis level again. Rubble field continues, two possible voids ahead worth sweeping for survivors.',
  },
]

const sceneAt = (t: number) =>
  (SCENE_LINES.find((line) => t < line.until) ?? SCENE_LINES[0]).text

/* -------------------------------------------------------------------------
 * Sample
 * ---------------------------------------------------------------------- */

export interface RawSample {
  cycleT: number
  linear: number
  angular: number
  detections: Detection[]
  frontClearanceM: number
  reflexBlocked: boolean
  safetyVeto: boolean
  source: CmdVelSource
  watchdogAgeS: number
  depthStatus: DepthStatus
  proximity: { left: number; center: number; right: number } | null
  preferred: 'left' | 'center' | 'right' | null
  depthAgeS: number
  processingMs: number
  serverFrameAgeMs: number
  frameId: number
  temperatureC: number
  tempStatus: TempStatus
  audioDb: number
  audioEvent: AudioEvent | null
  pitchDeg: number
  rollDeg: number
  accelZG: number
  tipped: boolean
  bump: boolean
  slipDetected: boolean
  sceneText: string
}

export function sampleTelemetry(elapsedS: number): RawSample {
  const cycleT = elapsedS % CYCLE_S
  const events = activeEvents(cycleT)

  const front = frontClearanceM(cycleT)
  const left = leftClearanceM(cycleT)
  const right = rightClearanceM(cycleT)

  const reflexBlocked = front < REFLEX_STOP_DISTANCE_M
  const safetyVeto = front < SAYCAN_MIN_CLEARANCE_M

  const dropout = cycleT >= DEPTH_DROPOUT.start && cycleT < DEPTH_DROPOUT.end
  const segment = motionAt(cycleT)
  const linear = reflexBlocked || dropout ? 0 : segment.linear
  const angular = reflexBlocked || dropout ? 0 : segment.angular

  const source: CmdVelSource = reflexBlocked ? 'reflex' : dropout ? 'watchdog' : 'brain'
  const watchdogAgeS = dropout
    ? clamp(cycleT - DEPTH_DROPOUT.start, 0, 3)
    : 0.02 + Math.abs(noise(cycleT, 21)) * 0.06

  const detections: Detection[] = (
    [
      { label: 'obstacle', distanceM: front, bearingDeg: 0 },
      { label: 'obstacle', distanceM: left, bearingDeg: -30 },
      { label: 'obstacle', distanceM: right, bearingDeg: 30 },
    ] as Detection[]
  )
    .filter((detection) => detection.distanceM < SENSOR_RANGE_M)
    .map((detection) => ({ ...detection, distanceM: Number(detection.distanceM.toFixed(2)) }))
    .sort((a, b) => a.distanceM - b.distanceM)

  // laptop/server.py semantics: higher score means nearer.
  const score = (distance: number) => Number(clamp01(1 - distance / SENSOR_RANGE_M).toFixed(2))
  const proximity = dropout
    ? null
    : { left: score(left), center: score(front), right: score(right) }

  let preferred: 'left' | 'center' | 'right' | null = null
  if (proximity) {
    const entries = Object.entries(proximity) as ['left' | 'center' | 'right', number][]
    preferred = entries.reduce((best, entry) => (entry[1] < best[1] ? entry : best))[0]
  }

  const depthStatus: DepthStatus = dropout ? 'uncertain' : 'ok'
  const depthAgeS = dropout
    ? cycleT - DEPTH_DROPOUT.start
    : 0.06 + Math.abs(noise(cycleT, 31)) * 0.05

  const tempEvent = events.find((event) => event.kind === 'temp')
  const temperatureC =
    22 +
    noise(cycleT, 41) * 0.35 +
    (tempEvent ? (tempEvent.deltaC ?? 0) * envelope(eventProgress(tempEvent, cycleT)) : 0)
  const tempStatus: TempStatus =
    temperatureC >= OVERHEAT_C ? 'overheat' : temperatureC >= WARM_C ? 'warm' : 'ok'

  const audioEventSource = events.find(
    (event) => event.kind === 'distress' || event.kind === 'voice' || event.kind === 'sound',
  )
  const audioDb =
    32 +
    noise(cycleT, 53) * 2.6 +
    (audioEventSource
      ? (audioEventSource.dbBoost ?? 0) * envelope(eventProgress(audioEventSource, cycleT))
      : 0)
  const audioEvent: AudioEvent | null = audioEventSource
    ? {
        kind: audioEventSource.kind as AudioEvent['kind'],
        label: audioEventSource.label ?? null,
        text: audioEventSource.text ?? null,
        bearingDeg: audioEventSource.bearingDeg ?? 0,
      }
    : null

  const tipEvent = events.find((event) => event.kind === 'tip')
  const bumpEvent = events.find((event) => event.kind === 'bump')
  const slipEvent = events.find((event) => event.kind === 'wheel_slip')

  const pitchDeg =
    noise(cycleT, 61) * 0.6 +
    (tipEvent ? (tipEvent.pitchDeg ?? 0) * envelope(eventProgress(tipEvent, cycleT)) : 0)
  const rollDeg = noise(cycleT, 67) * 0.5 + (slipEvent ? (slipEvent.side === 'l' ? -2.4 : 2.4) : 0)
  const accelZG =
    1 +
    noise(cycleT, 71) * 0.015 +
    (bumpEvent ? (bumpEvent.accelSpikeG ?? 0) * envelope(eventProgress(bumpEvent, cycleT)) : 0)

  return {
    cycleT,
    linear,
    angular,
    detections,
    frontClearanceM: front,
    reflexBlocked,
    safetyVeto,
    source,
    watchdogAgeS,
    depthStatus,
    proximity,
    preferred,
    depthAgeS,
    processingMs: Math.round(46 + noise(cycleT, 83) * 11),
    serverFrameAgeMs: Math.round(19 + noise(cycleT, 89) * 7),
    frameId: Math.floor(elapsedS * CAMERA_FPS),
    temperatureC,
    tempStatus,
    audioDb,
    audioEvent,
    pitchDeg,
    rollDeg,
    accelZG,
    tipped: Math.abs(pitchDeg) > 45,
    bump: Boolean(bumpEvent),
    slipDetected: Boolean(slipEvent),
    sceneText: sceneAt(cycleT),
  }
}

/* -------------------------------------------------------------------------
 * Brain episode scripting
 * ---------------------------------------------------------------------- */

export interface PlannedCall {
  name: string
  args: string
  result: string
  status: ToolResultStatus
}

export interface EpisodePlan {
  path: 'parser' | 'backboard'
  summary: string
  calls: PlannedCall[]
  parsed: { verb: string; args: Record<string, unknown> } | null
  command: string | null
  speech: string | null
  durationMs: number
}

const fmt = (value: number, digits = 2) => value.toFixed(digits)

/**
 * Builds one deliberative episode. The rotation keeps the log varied while the
 * live sample decides how the motion verbs actually resolve, so the Brain tab
 * agrees with what the Telemetry tab is showing.
 */
export function buildEpisodePlan(index: number, sample: RawSample): EpisodePlan {
  const obstacles = `{"detections": ${sample.detections.length} items, nearest ${fmt(
    sample.detections[0]?.distanceM ?? 0,
  )}m}`

  const forwardCall = (): PlannedCall => {
    if (sample.safetyVeto) {
      return {
        name: 'forward',
        args: '{"distance_m": 0.5}',
        result: '{"status": "vetoed", "reason": "obstacle ahead"}',
        status: 'vetoed',
      }
    }
    if (sample.reflexBlocked) {
      return {
        name: 'forward',
        args: '{"distance_m": 0.5}',
        result: `{"status": "stopped_by_obstacle", "distance_m": ${fmt(sample.frontClearanceM)}}`,
        status: 'stopped_by_obstacle',
      }
    }
    return {
      name: 'forward',
      args: '{"distance_m": 0.5}',
      result: '{"status": "completed"}',
      status: 'completed',
    }
  }

  // A voice event in the audio stream is what the parser fast path exists for.
  if (sample.audioEvent?.kind === 'voice' && sample.audioEvent.text) {
    const command = sample.audioEvent.text
    return {
      path: 'parser',
      summary: `Parser fast path handled "${command}"`,
      command,
      parsed: { verb: 'stop', args: {} },
      speech: null,
      durationMs: 90 + (index % 5) * 7,
      calls: [
        { name: 'stop', args: '{}', result: '{"status": "completed"}', status: 'completed' },
      ],
    }
  }

  if (sample.audioEvent?.kind === 'distress') {
    const heard = sample.audioEvent.text ?? 'distress signal'
    const speech = 'I hear you. Stay still, help is on the way.'
    return {
      path: 'backboard',
      summary: `Distress on bearing ${Math.round(sample.audioEvent.bearingDeg)} deg, responding`,
      command: null,
      parsed: null,
      speech,
      durationMs: 1400 + (index % 4) * 120,
      calls: [
        {
          name: 'get_audio',
          args: '{}',
          result: `{"db": ${fmt(sample.audioDb, 1)}, "event": {"kind": "distress", "text": "${heard}"}}`,
          status: 'read',
        },
        {
          name: 'speak',
          args: `{"text": "${speech}"}`,
          result: '{"status": "completed"}',
          status: 'completed',
        },
        {
          name: 'turn',
          args: `{"degrees": ${Math.round(-sample.audioEvent.bearingDeg)}}`,
          result: '{"status": "completed"}',
          status: 'completed',
        },
      ],
    }
  }

  const rotation = index % 6
  const base = { command: null, parsed: null, speech: null }

  if (rotation === 0) {
    return {
      ...base,
      path: 'backboard',
      summary: 'Checked obstacles, then advanced',
      durationMs: 1120 + (index % 3) * 90,
      calls: [
        { name: 'get_obstacles', args: '{}', result: obstacles, status: 'read' },
        forwardCall(),
      ],
    }
  }

  if (rotation === 1) {
    return {
      ...base,
      path: 'backboard',
      summary: 'Sampled ambient audio for survivors',
      durationMs: 940 + (index % 3) * 70,
      calls: [
        {
          name: 'get_audio',
          args: '{}',
          result: `{"db": ${fmt(sample.audioDb, 1)}, "event": null}`,
          status: 'read',
        },
      ],
    }
  }

  if (rotation === 2) {
    return {
      ...base,
      path: 'backboard',
      summary: 'Reoriented toward the open bearing',
      durationMs: 1260 + (index % 3) * 110,
      calls: [
        {
          name: 'get_state',
          args: '{}',
          result: '{"pose": [x, y, heading], "velocity": [lin, ang], "goal": null}',
          status: 'read',
        },
        {
          name: 'turn',
          args: `{"degrees": ${sample.preferred === 'left' ? 25 : -25}}`,
          result: '{"status": "completed"}',
          status: 'completed',
        },
      ],
    }
  }

  if (rotation === 3) {
    return {
      ...base,
      path: 'backboard',
      summary: 'Thermal check before entering the void',
      durationMs: 880 + (index % 3) * 60,
      calls: [
        {
          name: 'get_temperature',
          args: '{}',
          result: `{"celsius": ${fmt(sample.temperatureC, 1)}, "status": "${sample.tempStatus}"}`,
          status: 'read',
        },
      ],
    }
  }

  if (rotation === 4) {
    return {
      ...base,
      path: 'backboard',
      summary: 'Chassis attitude check',
      durationMs: 910 + (index % 3) * 80,
      calls: [
        {
          name: 'get_gyro',
          args: '{}',
          result: `{"pitch_deg": ${fmt(sample.pitchDeg, 1)}, "tipped": ${sample.tipped}, "bump": ${sample.bump}}`,
          status: 'read',
        },
        ...(sample.tipped
          ? [
              {
                name: 'stop',
                args: '{}',
                result: '{"status": "completed"}',
                status: 'completed' as ToolResultStatus,
              },
            ]
          : []),
      ],
    }
  }

  return {
    ...base,
    path: 'parser',
    summary: 'Operator command routed through the fine-tuned parser',
    command: 'forward half a meter',
    parsed: { verb: 'forward', args: { distance_m: 0.5 } },
    durationMs: 104 + (index % 5) * 6,
    calls: [forwardCall()],
  }
}

export const TRANSCRIPT_POOL = [
  'forward two meters',
  'stop',
  'turn left ninety degrees',
  'what do you see',
  'back up a little',
]
