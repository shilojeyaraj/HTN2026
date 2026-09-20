import { Activity, Camera, Radio, Shield } from 'lucide-react'
import { PoseTrack } from '../components/telemetry/PoseTrack'
import { Metric } from '../components/ui/Metric'
import { StateChip } from '../components/ui/StateChip'
import { Tile } from '../components/ui/Tile'
import type { LiveSnapshot } from '../types'

const format = (value: number | null | undefined, digits = 2) => value == null ? '—' : value.toFixed(digits)
const labels: Record<string, string> = {
  position_m: 'Position', attitude_deg: 'Orientation', velocity_mps: 'Velocity',
  status: 'Chassis flags', tof_mm: 'Distance sensors', battery_percent: 'Battery',
}

export function Telemetry({ snapshot, live }: { snapshot: LiveSnapshot | null; live: boolean }) {
  const rover = snapshot?.rover
  const sources = rover?.sources
  const position = sources?.position_m.value
  const attitude = sources?.attitude_deg.value
  const velocity = sources?.velocity_mps.value
  const distances = sources?.tof_mm.value
  const camera = rover?.camera
  const poseLive = live && sources?.position_m.status === 'live' && sources?.attitude_deg.status === 'live'
  const flagsLive = live && sources?.status.status === 'live'
  const activeFlags = Object.entries(rover?.flags ?? {}).filter(([, active]) => active)

  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
      <Tile title="Rover connection" icon={Radio} className="md:col-span-2 xl:col-span-3">
        <div className="flex flex-wrap items-center gap-3">
          <StateChip label={!live ? 'Feed offline' : rover?.connected ? 'Rover receiving' : 'Waiting for rover'}
            tone={live && rover?.connected ? 'live' : 'warn'} />
          <span className="text-xs text-ink-muted">{snapshot ? `Last snapshot ${new Date(snapshot.timestamp * 1000).toLocaleTimeString()}` : 'Waiting for the first snapshot'}</span>
          <span className="text-xs text-ink-faint">Readings below are marked when stale or unavailable.</span>
        </div>
      </Tile>

      <div className="flex flex-col gap-2">
        {Array.isArray(position) && position.length >= 2 && Array.isArray(attitude) && attitude.length >= 3 ? (
          <>
            {!poseLive && <p className="text-xs text-warn">Last known pose — readings are stale.</p>}
            <PoseTrack pose={{ x: position[0], y: position[1], headingDeg: attitude[0],
              trail: (rover?.trail ?? []).map(([x, y]) => ({ x, y })) }} goal={null} className="flex-1" />
          </>
        ) : <Tile title="Pose / Track"><p className="py-12 text-sm text-ink-faint">Waiting for position and orientation.</p></Tile>}
      </div>

      <Tile title="Chassis motion" icon={Activity} actions={<StateChip
        label={!live ? 'stale' : sources?.velocity_mps.status ?? 'unavailable'}
        tone={live && sources?.velocity_mps.status === 'live' ? 'live' : 'muted'} />}>
        <div className="grid grid-cols-2 gap-5 py-2">
          <Metric label="Forward speed" value={format(Array.isArray(velocity) ? velocity[3] : null)} unit="m/s" size="headline" />
          <Metric label="Sideways speed" value={format(Array.isArray(velocity) ? velocity[4] : null)} unit="m/s" size="headline" />
          <Metric label="Yaw" value={format(Array.isArray(attitude) ? attitude[0] : null, 1)} unit="°" />
          <Metric label="Pitch / Roll" value={Array.isArray(attitude) ? `${format(attitude[1], 1)} / ${format(attitude[2], 1)}` : '—'} unit="°" />
        </div>
        <p className="mt-3 text-xs text-ink-faint">Velocity uses the rover body frame. Orientation: {live ? sources?.attitude_deg.status ?? 'unavailable' : 'stale'}.</p>
      </Tile>

      <Tile title="Camera health" icon={Camera} actions={<StateChip label={
        !live ? 'offline' : camera?.reader_alive && camera.frame_age_s !== null && camera.frame_age_s <= 1 ? 'fresh' : camera?.reader_alive ? 'waiting' : 'not running'
      } tone={live && camera?.reader_alive && camera.frame_age_s !== null && camera.frame_age_s <= 1 ? 'live' : 'muted'} />}>
        <div className="grid grid-cols-2 gap-5 py-2">
          <Metric label="Frame age" value={format(camera?.frame_age_s)} unit="s" size="headline" />
          <Metric label="Decoded frames" value={format(camera?.decode_fps, 0)} unit="fps" size="headline" />
          <Metric label="Decode failures" value={camera?.decode_failures ?? '—'} />
          <Metric label="Stream restarts" value={camera?.stream_restarts ?? '—'} />
        </div>
        <p className="mt-3 text-xs text-ink-faint">Camera starts when an autonomous mission needs a frame.</p>
      </Tile>

      <Tile title="Sensor freshness" className="md:col-span-2">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="text-ink-faint"><tr><th className="py-2">Source</th><th>Status</th><th>Age at snapshot</th><th>Subscription</th></tr></thead>
            <tbody>{Object.entries(labels).map(([key, label]) => {
              const source = sources?.[key as keyof typeof sources]
              const status = source?.status === 'live' && !live ? 'stale' : source?.status ?? 'unavailable'
              return <tr key={key} className="border-t border-line">
                <td className="py-3 pr-3 text-ink">{label}</td>
                <td><StateChip label={status} tone={status === 'live' ? 'live' : status === 'stale' ? 'warn' : 'muted'} /></td>
                <td className="font-mono">{format(source?.age_s)} s</td>
                <td>{source?.subscription ?? 'pending'}</td>
              </tr>
            })}</tbody>
          </table>
        </div>
      </Tile>

      <Tile title="Distance readings" actions={<StateChip label={live ? sources?.tof_mm.status ?? 'unavailable' : 'stale'} />}>
        <div className="grid grid-cols-2 gap-4 py-2">
          {Array.isArray(distances) ? distances.map((distance, i) => <Metric key={i} label={`Sensor ${i + 1}`} value={distance > 0 ? format(distance, 0) : 'Unavailable'} unit={distance > 0 ? 'mm' : undefined} />)
            : <p className="text-sm text-ink-faint">No distance readings received.</p>}
        </div>
        <p className="mt-3 text-xs text-ink-faint">Raw sensor channels. Mounting directions have not been assigned.</p>
      </Tile>

      <Tile title="Chassis alerts" icon={Shield} actions={<StateChip label={flagsLive ? 'live' : 'unavailable / stale'} tone={flagsLive ? 'live' : 'muted'} />}>
        <div className="flex flex-wrap gap-2">
          {activeFlags.map(([name]) => <StateChip key={name} label={name.replaceAll('_', ' ')} tone={!flagsLive ? 'muted' : name === 'static' ? 'live' : 'warn'} />)}
          {!activeFlags.length && <p className="text-xs text-ink-faint">{flagsLive ? 'No active status flags.' : 'Waiting for status readings.'}</p>}
        </div>
        <ol className="mt-3 max-h-36 space-y-2 overflow-auto text-xs text-ink-muted">
          {[...(rover?.alerts ?? [])].reverse().map((alert, i) => <li key={`${alert.timestamp}-${i}`}>{new Date(alert.timestamp * 1000).toLocaleTimeString()} · {alert.name.replaceAll('_', ' ')}</li>)}
        </ol>
      </Tile>

      <Tile title="Last stop request">
        {rover?.stop ? <div className="space-y-3 text-sm">
          <StateChip label={rover.stop.status} tone={rover.stop.status === 'failed' ? 'alert' : 'muted'} />
          <p>Motion after request: <strong>{live ? rover.stop.motion : 'unknown — feed offline'}</strong></p>
          {rover.stop.detail && <p className="text-alert">{rover.stop.detail}</p>}
        </div> : <p className="text-sm text-ink-faint">No stop request recorded.</p>}
      </Tile>

      <Tile title="Additional sensors">
        <p className="text-sm leading-relaxed text-ink-faint">GPS, temperature, microphone levels, depth inference, wheel encoders, and arm/gripper feedback are not connected to this feed.</p>
      </Tile>
    </div>
  )
}
