import type { LiveSnapshot } from '../types'
import { useMapStream } from './useMapStream'

const object = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value)
const number = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value)
const nullableNumber = (value: unknown) => value === null || number(value)
const nullableString = (value: unknown) => value === null || typeof value === 'string'
const numericArray = (value: unknown): value is number[] => Array.isArray(value) && value.every(number)

/** Check the network boundary before components format or iterate sensor values. */
export function decodeTelemetry(value: unknown): LiveSnapshot {
  if (!object(value) || value.schema !== 'rover.v1' || !number(value.timestamp)
      || !object(value.rover) || !object(value.mission)) throw new Error('Not rover telemetry')
  const { rover, mission } = value
  const sources = rover.sources
  if (typeof rover.connected !== 'boolean' || !object(sources)) throw new Error('Missing rover state')
  for (const key of ['position_m', 'attitude_deg', 'velocity_mps', 'status', 'tof_mm', 'battery_percent']) {
    const source = sources[key]
    if (!object(source) || !['live', 'stale', 'unavailable'].includes(String(source.status))
        || !['pending', 'active', 'failed', 'unsupported'].includes(String(source.subscription))
        || !nullableNumber(source.age_s) || !nullableNumber(source.received_at)
        || !(source.value === null || (key === 'battery_percent' ? number(source.value) : numericArray(source.value)))) {
      throw new Error('Invalid sensor reading')
    }
  }
  const camera = rover.camera
  if (!object(camera) || !nullableNumber(camera.frame_age_s) || typeof camera.reader_alive !== 'boolean'
      || !['decode_fps', 'decode_failures', 'stream_restarts'].every(key => number(camera[key]))
      || !(rover.flags === null || (object(rover.flags) && Object.values(rover.flags).every(v => typeof v === 'boolean')))
      || !Array.isArray(rover.trail) || !rover.trail.every(p => numericArray(p) && p.length === 2)
      || !Array.isArray(rover.alerts) || !rover.alerts.every(a => object(a) && typeof a.name === 'string' && number(a.timestamp))) {
    throw new Error('Invalid rover snapshot')
  }
  if (rover.stop !== null && (!object(rover.stop) || typeof rover.stop.status !== 'string'
      || typeof rover.stop.motion !== 'string' || !number(rover.stop.requested_at) || !nullableString(rover.stop.detail))) {
    throw new Error('Invalid stop state')
  }
  if (typeof mission.phase !== 'string' || typeof mission.search_active !== 'boolean'
      || !['reason', 'mode', 'goal', 'model', 'scene', 'last_command'].every(key => nullableString(mission[key]))
      || !['search_rotation_deg', 'retry_in_s', 'failures', 'cycles'].every(key => number(mission[key]))
      || !nullableNumber(mission.inference_ms) || !nullableNumber(mission.scene_at)
      || !Array.isArray(mission.findings) || !mission.findings.every(f => object(f) && typeof f.type === 'string' && typeof f.description === 'string')
      || !Array.isArray(mission.actions) || !mission.actions.every(a => object(a)
        && number(a.id) && typeof a.name === 'string' && typeof a.requested_args === 'string'
        && typeof a.mode === 'string' && typeof a.status === 'string' && number(a.started_at)
        && nullableNumber(a.finished_at) && nullableNumber(a.duration_ms)
        && (a.result === null || object(a.result)) && (a.applied_args === null || object(a.applied_args)))) {
    throw new Error('Invalid mission snapshot')
  }
  return value as unknown as LiveSnapshot
}

export function useTelemetry() {
  const { payload, connected, fresh } = useMapStream(undefined, decodeTelemetry)
  return { snapshot: payload, live: connected && fresh }
}
