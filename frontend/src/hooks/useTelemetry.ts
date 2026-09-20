import { useEffect, useState } from 'react'
import {
  ARBITER_HZ,
  ASSISTANT_ID,
  CAMERA_FPS,
  DEPTH_HOST,
  DEPTH_PORT,
  DEPTH_STALENESS_LIMIT_S,
  EPISODE_GAP_S,
  GPS_ORIGIN,
  MAX_TOOL_ROUNDS,
  OVERHEAT_C,
  PARSER_MODEL_ID,
  PLANNER_MODEL,
  PTT_GPIO_PIN,
  REFLEX_HZ,
  REFLEX_STOP_DISTANCE_M,
  SAYCAN_MIN_CLEARANCE_M,
  SLIP_FACTOR,
  STT_MODEL,
  THREAD_ID,
  TICKS_PER_METER,
  TICK_MS,
  VERB_CATALOG,
  VISION_MODEL,
  WARM_C,
  WATCHDOG_TIMEOUT_S,
  buildEpisodePlan,
  clamp,
  sampleTelemetry,
} from '../data/mockTelemetry'
import type {
  BrainSnapshot,
  EpisodeRecord,
  TelemetrySnapshot,
  ToolCallRecord,
  TtsUtterance,
  VetoRecord,
  VerbUsage,
} from '../types'

const MAX_TRAIL = 180
const MAX_HISTORY = 60
const MAX_TOOL_CALLS = 40
const MAX_EPISODES = 24
const MAX_VETOES = 6
const MAX_TTS = 4

interface QueuedUtterance {
  id: string
  text: string
  at: number
}

interface Store {
  startedAt: number
  lastTickAt: number
  x: number
  y: number
  headingDeg: number
  trail: { x: number; y: number }[]
  leftTicks: number
  rightTicks: number
  tempHistory: number[]
  audioHistory: number[]
  speedHistory: number[]
  episodes: EpisodeRecord[]
  toolCalls: ToolCallRecord[]
  vetoes: VetoRecord[]
  verbCounts: Record<string, { calls: number; lastUsedClock: string | null }>
  parserHits: number
  parserMisses: number
  lastCommand: string | null
  lastParsed: { verb: string; args: Record<string, unknown> } | null
  lastParserLatencyMs: number
  transcript: string | null
  pttUntil: number
  tts: QueuedUtterance[]
  episodeIndex: number
  nextEpisodeAt: number
  lastEpisodeAt: number
  lastToolRounds: number
  wasVetoed: boolean
  seq: number
}

const clockOf = (date: Date) => date.toLocaleTimeString('en-GB', { hour12: false })

function createStore(now: number): Store {
  return {
    startedAt: now,
    lastTickAt: now,
    x: 0,
    y: 0,
    headingDeg: 0,
    trail: [{ x: 0, y: 0 }],
    leftTicks: 0,
    rightTicks: 0,
    tempHistory: [],
    audioHistory: [],
    speedHistory: [],
    episodes: [],
    toolCalls: [],
    vetoes: [],
    verbCounts: Object.fromEntries(
      VERB_CATALOG.map((verb) => [verb.name, { calls: 0, lastUsedClock: null }]),
    ),
    parserHits: 0,
    parserMisses: 0,
    lastCommand: null,
    lastParsed: null,
    lastParserLatencyMs: 0,
    transcript: null,
    pttUntil: 0,
    tts: [],
    episodeIndex: 0,
    nextEpisodeAt: now + 600,
    lastEpisodeAt: now,
    lastToolRounds: 0,
    wasVetoed: false,
    seq: 0,
  }
}

const push = <T,>(list: T[], item: T, cap: number) => {
  const next = [...list, item]
  return next.length > cap ? next.slice(next.length - cap) : next
}

const pushHistory = (list: number[], value: number) => push(list, value, MAX_HISTORY)

/** Rendered for the first frame, before the interval takes over on mount. */
const SEED_SNAPSHOTS = build(createStore(0), 0)

/**
 * Single source of animated mock telemetry for the Telemetry and Brain tabs.
 * One timer drives both snapshots so every tile agrees with every other tile.
 */
export function useTelemetry(): { telemetry: TelemetrySnapshot; brain: BrainSnapshot } {
  const [snapshots, setSnapshots] = useState(SEED_SNAPSHOTS)

  useEffect(() => {
    const store = createStore(Date.now())
    const id = window.setInterval(() => setSnapshots(build(store, Date.now())), TICK_MS)
    return () => window.clearInterval(id)
  }, [])

  return snapshots
}

function build(store: Store, now: number): { telemetry: TelemetrySnapshot; brain: BrainSnapshot } {
  const dt = Math.min((now - store.lastTickAt) / 1000, 0.5)
  store.lastTickAt = now
  const elapsedS = (now - store.startedAt) / 1000
  const sample = sampleTelemetry(elapsedS)
  // now === 0 only for the module-level seed snapshot, which has no wall clock.
  const clock = now === 0 ? '--:--:--' : clockOf(new Date(now))

  /* --- odometry ------------------------------------------------------- */

  store.headingDeg = (store.headingDeg + (sample.angular * 180 * dt) / Math.PI + 360) % 360
  const heading = (store.headingDeg * Math.PI) / 180
  store.x += Math.cos(heading) * sample.linear * dt
  store.y += Math.sin(heading) * sample.linear * dt
  store.trail = push(store.trail, { x: store.x, y: store.y }, MAX_TRAIL)

  const commandedVelocity = sample.linear
  const estimatedVelocity = sample.slipDetected
    ? commandedVelocity * (1 - SLIP_FACTOR)
    : commandedVelocity
  const wheelDelta = Math.abs(estimatedVelocity) * dt * TICKS_PER_METER
  store.leftTicks += Math.round(wheelDelta * (sample.slipDetected ? 1 - SLIP_FACTOR : 1))
  store.rightTicks += Math.round(wheelDelta)

  /* --- rolling histories ---------------------------------------------- */

  store.tempHistory = pushHistory(store.tempHistory, sample.temperatureC)
  store.audioHistory = pushHistory(store.audioHistory, sample.audioDb)
  store.speedHistory = pushHistory(store.speedHistory, Math.abs(sample.linear))

  /* --- safety veto log ------------------------------------------------- */

  if (sample.safetyVeto && !store.wasVetoed) {
    store.seq += 1
    store.vetoes = push(
      store.vetoes,
      { id: `veto-${store.seq}`, verb: 'forward', reason: 'obstacle ahead', clock },
      MAX_VETOES,
    )
  }
  store.wasVetoed = sample.safetyVeto

  /* --- deliberative episode -------------------------------------------- */

  if (now >= store.nextEpisodeAt) {
    const index = store.episodeIndex
    const plan = buildEpisodePlan(index, sample)
    store.episodeIndex += 1
    store.lastEpisodeAt = now
    store.nextEpisodeAt = now + EPISODE_GAP_S * 1000
    store.lastToolRounds = Math.min(plan.calls.length, MAX_TOOL_ROUNDS)

    store.episodes = push(
      store.episodes,
      {
        id: `ep-${index}`,
        number: index + 1,
        path: plan.path,
        durationMs: plan.durationMs,
        toolRounds: store.lastToolRounds,
        summary: plan.summary,
        clock,
      },
      MAX_EPISODES,
    )

    plan.calls.forEach((call) => {
      store.seq += 1
      store.toolCalls = push(
        store.toolCalls,
        {
          id: `tc-${store.seq}`,
          episode: index + 1,
          name: call.name,
          args: call.args,
          result: call.result,
          status: call.status,
          clock,
        },
        MAX_TOOL_CALLS,
      )
      const usage = store.verbCounts[call.name]
      if (usage) {
        usage.calls += 1
        usage.lastUsedClock = clock
      }
    })

    if (plan.path === 'parser') {
      store.parserHits += 1
      store.lastParsed = plan.parsed
      store.lastParserLatencyMs = plan.durationMs
      if (plan.command) {
        store.lastCommand = plan.command
        store.transcript = plan.command
        store.pttUntil = now + 900
      }
    } else if (index % 4 === 3) {
      // Parser was consulted, returned null, and the episode fell through.
      store.parserMisses += 1
      store.lastParsed = null
    }

    if (plan.speech) {
      store.seq += 1
      store.tts = push(store.tts, { id: `tts-${store.seq}`, text: plan.speech, at: now }, MAX_TTS)
    }
  }

  /* --- snapshots -------------------------------------------------------- */

  const sinceEpisodeMs = now - store.lastEpisodeAt

  const telemetry: TelemetrySnapshot = {
    uptimeS: elapsedS,
    clock,
    drive: {
      linear: sample.linear,
      angular: sample.angular,
      source: sample.source,
      watchdogAgeS: sample.watchdogAgeS,
      watchdogTimeoutS: WATCHDOG_TIMEOUT_S,
      publishHz: ARBITER_HZ,
    },
    reflex: {
      blocked: sample.reflexBlocked,
      clearanceM: sample.frontClearanceM,
      stopDistanceM: REFLEX_STOP_DISTANCE_M,
      sinceTriggerS: sample.reflexBlocked ? 0 : null,
      hz: REFLEX_HZ,
    },
    safety: {
      status: sample.safetyVeto ? 'VETO' : 'OK',
      reason: sample.safetyVeto ? 'obstacle ahead' : null,
      gatedVerbs: ['forward'],
      minClearanceM: SAYCAN_MIN_CLEARANCE_M,
      recent: [...store.vetoes].reverse(),
    },
    detections: sample.detections,
    depth: {
      status: sample.depthStatus,
      relativeProximity: sample.proximity,
      preferredDirection: sample.preferred,
      frameId: sample.frameId,
      processingMs: sample.processingMs,
      serverFrameAgeMs: sample.serverFrameAgeMs,
      ageS: sample.depthAgeS,
      stalenessLimitS: DEPTH_STALENESS_LIMIT_S,
      fps: CAMERA_FPS,
      advisoryOnly: true,
      host: DEPTH_HOST,
      port: DEPTH_PORT,
    },
    pose: {
      x: store.x,
      y: store.y,
      headingDeg: store.headingDeg,
      trail: store.trail,
    },
    encoder: {
      leftTicksTotal: store.leftTicks,
      rightTicksTotal: store.rightTicks,
      estimatedVelocityMps: estimatedVelocity,
      commandedVelocityMps: commandedVelocity,
      slipDetected: sample.slipDetected,
      ticksPerMeter: TICKS_PER_METER,
    },
    gyro: {
      pitchDeg: sample.pitchDeg,
      rollDeg: sample.rollDeg,
      accelZG: sample.accelZG,
      tipped: sample.tipped,
      bump: sample.bump,
    },
    temperature: {
      celsius: sample.temperatureC,
      status: sample.tempStatus,
      warmC: WARM_C,
      overheatC: OVERHEAT_C,
      history: store.tempHistory,
    },
    audio: {
      db: sample.audioDb,
      event: sample.audioEvent,
      history: store.audioHistory,
    },
    gps: {
      latitude: GPS_ORIGIN.latitude + store.y * 9e-6,
      longitude: GPS_ORIGIN.longitude + store.x * 1.24e-5,
      fix: sample.depthStatus === 'uncertain' ? '2D' : '3D',
      satellites: 9 + (Math.floor(elapsedS / 7) % 4),
      hdop: Number((1.1 + Math.sin(elapsedS / 5) * 0.3).toFixed(2)),
    },
    speedHistory: store.speedHistory,
  }

  const verbs: VerbUsage[] = VERB_CATALOG.map((verb) => ({
    name: verb.name,
    kind: verb.kind,
    calls: store.verbCounts[verb.name]?.calls ?? 0,
    lastUsedClock: store.verbCounts[verb.name]?.lastUsedClock ?? null,
  }))

  const tts: TtsUtterance[] = [...store.tts]
    .reverse()
    .map(({ id, text, at }) => ({
      id,
      text,
      status: now - at < 400 ? 'queued' : now - at < 3400 ? 'playing' : 'done',
    }))

  const brain: BrainSnapshot = {
    session: {
      provider: 'google',
      plannerModel: PLANNER_MODEL,
      visionModel: VISION_MODEL,
      threadId: THREAD_ID,
      assistantId: ASSISTANT_ID,
      toolRounds: store.lastToolRounds,
      maxToolRounds: MAX_TOOL_ROUNDS,
      status:
        sinceEpisodeMs < 320 ? 'thinking' : sinceEpisodeMs < 620 ? 'requires_action' : 'idle',
      episodeGapS: EPISODE_GAP_S,
    },
    episodes: [...store.episodes].reverse(),
    toolCalls: [...store.toolCalls].reverse(),
    scene: {
      text: sample.sceneText,
      detections: sample.detections,
      frameId: sample.frameId,
      ageS: clamp(sinceEpisodeMs / 1000, 0, 9),
    },
    verbs,
    parser: {
      modelId: PARSER_MODEL_ID,
      hits: store.parserHits,
      misses: store.parserMisses,
      lastCommand: store.lastCommand,
      lastParsed: store.lastParsed,
      lastLatencyMs: store.lastParserLatencyMs,
    },
    voice: {
      transcript: store.transcript,
      pushToTalkHeld: now < store.pttUntil,
      gpioPin: PTT_GPIO_PIN,
      sttModel: STT_MODEL,
      tts,
    },
    goal: {
      current: { x: 3.5, y: 2.5 },
      lastUserCommand: store.lastCommand,
      safetyStatus: sample.safetyVeto ? 'VETO' : 'OK',
    },
  }

  return { telemetry, brain }
}
