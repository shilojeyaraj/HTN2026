import { Map as MapIcon } from 'lucide-react'
import { useEffect, useRef } from 'react'
import { useMapStream } from '../hooks/useMapStream'
import type { MapPayload } from '../types'
import { Panel } from './ui/Panel'

const CELL_PX = 20
const SENSOR_FOV_DEG = 120
const SENSOR_RANGE_M = 2.5
const DANGER_ARC_DEG = 140

const SOUND_COLORS: Record<string, string> = {
  distress: '#ef4444',
  voice: '#38bdf8',
  sound: '#f59e0b',
  speech: '#a78bfa',
}

let gridCanvas: HTMLCanvasElement | null = null

function probToRGB(prob: number): [number, number, number, number] {
  if (prob === undefined || Math.abs(prob - 0.5) < 0.02) return [7, 11, 18, 255]
  if (prob < 0.5) {
    const t = (0.5 - prob) * 2
    return [
      Math.round(7 + (34 - 7) * t),
      Math.round(11 + (211 - 11) * t),
      Math.round(18 + (238 - 18) * t),
      Math.round(40 + 180 * t),
    ]
  }
  const t = (prob - 0.5) * 2
  return [
    Math.round(7 + (251 - 7) * t),
    Math.round(11 + (146 - 11) * t),
    Math.round(18 + (60 - 18) * t),
    Math.round(40 + 200 * t),
  ]
}

function draw(ctx: CanvasRenderingContext2D, payload: MapPayload, w: number, h: number) {
  ctx.clearRect(0, 0, w, h)

  // Background gradient
  const bgGrad = ctx.createRadialGradient(w / 2, h / 2, 0, w / 2, h / 2, Math.max(w, h) * 0.7)
  bgGrad.addColorStop(0, '#0a0f1a')
  bgGrad.addColorStop(1, '#05080d')
  ctx.fillStyle = bgGrad
  ctx.fillRect(0, 0, w, h)

  const [roverX, roverY, roverHeading] = payload.rover_pose
  const res = payload.grid_resolution_m || 0.2
  const gw = payload.grid_width || 100
  const gh = payload.grid_height || 100
  const grid = payload.grid

  const scale = CELL_PX / res
  const cx = w / 2 - roverX * scale
  const cy = h / 2 + roverY * scale
  const t = Date.now() / 1000

  // --- smooth occupancy grid ---
  if (!gridCanvas) gridCanvas = document.createElement('canvas')
  if (gridCanvas.width !== gw || gridCanvas.height !== gh) {
    gridCanvas.width = gw
    gridCanvas.height = gh
  }
  const gctx = gridCanvas.getContext('2d')
  if (gctx) {
    const imgData = gctx.createImageData(gw, gh)
    for (let i = 0; i < gw * gh; i++) {
      const [r, g, b, a] = probToRGB(grid[i] ?? 0.5)
      imgData.data[i * 4] = r
      imgData.data[i * 4 + 1] = g
      imgData.data[i * 4 + 2] = b
      imgData.data[i * 4 * 3] = a
    }
    gctx.putImageData(imgData, 0, 0)
  }

  ctx.imageSmoothingEnabled = true
  ctx.imageSmoothingQuality = 'high'
  const gridScreenW = gw * CELL_PX
  const gridScreenH = gh * CELL_PX
  const gridScreenX = cx - (gw / 2) * CELL_PX
  const gridScreenY = cy - (gh / 2) * CELL_PX
  ctx.drawImage(gridCanvas!, 0, 0, gw, gh, gridScreenX, gridScreenY, gridScreenW, gridScreenH)

  // --- radar grid lines ---
  ctx.strokeStyle = 'rgba(56, 189, 248, 0.04)'
  ctx.lineWidth = 1
  const gridLineSpacing = CELL_PX * 5
  for (let x = gridScreenX; x < gridScreenX + gridScreenW; x += gridLineSpacing) {
    ctx.beginPath()
    ctx.moveTo(x, gridScreenY)
    ctx.lineTo(x, gridScreenY + gridScreenH)
    ctx.stroke()
  }
  for (let y = gridScreenY; y < gridScreenY + gridScreenH; y += gridLineSpacing) {
    ctx.beginPath()
    ctx.moveTo(gridScreenX, y)
    ctx.lineTo(gridScreenX + gridScreenW, y)
    ctx.stroke()
  }

  // --- trail with gradient opacity ---
  if (payload.trail && payload.trail.length > 1) {
    const trail = payload.trail
    for (let i = 1; i < trail.length; i++) {
      const [tx, ty] = trail[i]
      const [px, py] = trail[i - 1]
      const alpha = (i / trail.length) * 0.5
      ctx.strokeStyle = `rgba(34, 197, 94, ${alpha})`
      ctx.lineWidth = 2 + (i / trail.length) * 2
      ctx.beginPath()
      ctx.moveTo(cx + px * scale, cy - py * scale)
      ctx.lineTo(cx + tx * scale, cy - ty * scale)
      ctx.stroke()
    }
  }

  // --- heat points with glow ---
  for (const hp of payload.heat_points || []) {
    const sx = cx + hp.x * scale
    const sy = cy - hp.y * scale
    const color = hp.status === 'overheat' ? '#ef4444' : '#f59e0b'
    const radius = hp.status === 'overheat' ? 50 : 36
    ctx.shadowBlur = 25
    ctx.shadowColor = color
    const grad = ctx.createRadialGradient(sx, sy, 0, sx, sy, radius)
    grad.addColorStop(0, color)
    grad.addColorStop(0.5, `${color}66`)
    grad.addColorStop(1, 'transparent')
    ctx.fillStyle = grad
    ctx.beginPath()
    ctx.arc(sx, sy, radius, 0, Math.PI * 2)
    ctx.fill()
    ctx.shadowBlur = 0
    ctx.fillStyle = '#f1f5f9'
    ctx.font = '600 12px Inter, sans-serif'
    ctx.fillText(`${hp.celsius}°C`, sx + 14, sy - 10)
  }

  // --- danger soundwaves (directional, for distress sounds) ---
  const headingRad = (roverHeading * Math.PI) / 180
  const arcHalfRad = (DANGER_ARC_DEG / 2) * Math.PI / 180
  for (const ss of payload.sound_sources || []) {
    if (ss.kind !== 'distress' && (ss.db ?? 0) < 80) continue
    const sx = cx + ss.x * scale
    const sy = cy - ss.y * scale
    const color = SOUND_COLORS[ss.kind] || '#ef4444'
    const maxRadius = 120
    // 3 expanding waves at different phases
    for (let w_i = 0; w_i < 3; w_i++) {
      const phase = ((t * 0.6 + w_i * 0.33) % 1)
      const radius = phase * maxRadius
      const alpha = (1 - phase) * 0.5
      if (alpha < 0.02 || radius < 4) continue
      ctx.save()
      ctx.translate(sx, sy)
      ctx.rotate(-headingRad)
      ctx.shadowBlur = 20
      ctx.shadowColor = color
      // arc wave (directional — centered on rover heading)
      ctx.strokeStyle = `${color}${Math.round(alpha * 255).toString(16).padStart(2, '0')}`
      ctx.lineWidth = 3 * (1 - phase * 0.5)
      ctx.beginPath()
      ctx.arc(0, 0, radius, -arcHalfRad, arcHalfRad)
      ctx.stroke()
      // inner glow arc
      ctx.strokeStyle = `${color}${Math.round(alpha * 0.3 * 255).toString(16).padStart(2, '0')}`
      ctx.lineWidth = 8 * (1 - phase * 0.5)
      ctx.beginPath()
      ctx.arc(0, 0, radius, -arcHalfRad, arcHalfRad)
      ctx.stroke()
      ctx.restore()
    }
  }

  // --- sound sources with pulsing glow ---
  for (const ss of payload.sound_sources || []) {
    const sx = cx + ss.x * scale
    const sy = cy - ss.y * scale
    const color = SOUND_COLORS[ss.kind] || '#f59e0b'
    const isSpeech = ss.kind === 'speech'
    const isDanger = ss.kind === 'distress' || (ss.db ?? 0) >= 80
    const alpha = isSpeech && ss.final === false ? 0.4 : 1
    ctx.globalAlpha = alpha
    ctx.shadowBlur = isDanger ? 20 : 12
    ctx.shadowColor = color
    // expanding ripple rings
    for (let r = 0; r < 2; r++) {
      const phase = (t * 0.8 + r * 0.5) % 1
      const ringRadius = 8 + phase * (isDanger ? 30 : 20)
      const ringAlpha = (1 - phase) * 0.6
      ctx.strokeStyle = `${color}${Math.round(ringAlpha * 255).toString(16).padStart(2, '0')}`
      ctx.lineWidth = 2
      ctx.beginPath()
      ctx.arc(sx, sy, ringRadius, 0, Math.PI * 2)
      ctx.stroke()
    }
    // core dot
    ctx.fillStyle = color
    ctx.beginPath()
    ctx.arc(sx, sy, isDanger ? 6 : 4, 0, Math.PI * 2)
    ctx.fill()
    ctx.shadowBlur = 0
    // label
    ctx.fillStyle = '#e2e8f0'
    ctx.font = '500 11px Inter, sans-serif'
    const label = isSpeech && ss.final === false ? `"${ss.label}" …` : ss.label
    ctx.fillText(label, sx + 14, sy + 4)
    ctx.globalAlpha = 1
  }

  // --- hazards with glow ---
  for (const hz of payload.hazards || []) {
    const sx = cx + hz.x * scale
    const sy = cy - hz.y * scale
    ctx.shadowBlur = 15
    ctx.shadowColor = '#ef4444'
    ctx.fillStyle = '#ef4444'
    ctx.beginPath()
    ctx.moveTo(sx, sy - 14)
    ctx.lineTo(sx - 11, sy + 8)
    ctx.lineTo(sx + 11, sy + 8)
    ctx.closePath()
    ctx.fill()
    ctx.shadowBlur = 0
    ctx.fillStyle = '#0b1118'
    ctx.font = 'bold 12px Inter, sans-serif'
    ctx.fillText('!', sx - 4, sy + 5)
  }

  // --- annotations ---
  for (const ann of payload.annotations || []) {
    const sx = cx + ann.x * scale
    const sy = cy - ann.y * scale
    ctx.fillStyle = 'rgba(56, 189, 248, 0.9)'
    ctx.beginPath()
    ctx.arc(sx, sy, 4, 0, Math.PI * 2)
    ctx.fill()
    ctx.strokeStyle = 'rgba(56, 189, 248, 0.4)'
    ctx.lineWidth = 1
    ctx.beginPath()
    ctx.arc(sx, sy, 8, 0, Math.PI * 2)
    ctx.stroke()
    ctx.font = '500 11px Inter, sans-serif'
    const textWidth = ctx.measureText(ann.text).width
    ctx.fillStyle = 'rgba(7, 11, 18, 0.85)'
    ctx.fillRect(sx + 10, sy - 16, textWidth + 8, 18)
    ctx.fillStyle = '#7dd3fc'
    ctx.fillText(ann.text, sx + 14, sy - 3)
  }

  // --- rover with sensor cone ---
  const rx = cx + roverX * scale
  const ry = cy - roverY * scale

  // sensor cone
  ctx.save()
  ctx.translate(rx, ry)
  ctx.rotate(-headingRad)
  const coneRangePx = SENSOR_RANGE_M * scale
  const coneHalfRad = (SENSOR_FOV_DEG / 2) * Math.PI / 180
  const coneGrad = ctx.createRadialGradient(0, 0, 0, 0, 0, coneRangePx)
  coneGrad.addColorStop(0, 'rgba(34, 211, 238, 0.15)')
  coneGrad.addColorStop(0.7, 'rgba(34, 211, 238, 0.05)')
  coneGrad.addColorStop(1, 'rgba(34, 211, 238, 0)')
  ctx.fillStyle = coneGrad
  ctx.beginPath()
  ctx.moveTo(0, 0)
  ctx.arc(0, 0, coneRangePx, -coneHalfRad, coneHalfRad)
  ctx.closePath()
  ctx.fill()
  ctx.restore()

  // rover body with glow
  ctx.save()
  ctx.translate(rx, ry)
  ctx.rotate(-headingRad)
  ctx.shadowBlur = 15
  ctx.shadowColor = '#22c55e'
  ctx.fillStyle = '#22c55e'
  ctx.beginPath()
  ctx.moveTo(16, 0)
  ctx.lineTo(-9, -10)
  ctx.lineTo(-5, 0)
  ctx.lineTo(-9, 10)
  ctx.closePath()
  ctx.fill()
  ctx.strokeStyle = '#bbf7d0'
  ctx.lineWidth = 2
  ctx.stroke()
  ctx.shadowBlur = 0
  ctx.strokeStyle = 'rgba(34, 197, 94, 0.5)'
  ctx.lineWidth = 1
  ctx.setLineDash([5, 5])
  ctx.beginPath()
  ctx.moveTo(16, 0)
  ctx.lineTo(40, 0)
  ctx.stroke()
  ctx.setLineDash([])
  ctx.restore()
}

export function MapView() {
  const { payload, connected } = useMapStream()
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const payloadRef = useRef<MapPayload | null>(payload)
  payloadRef.current = payload

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    let raf: number
    const render = () => {
      const p = payloadRef.current
      if (p) {
        draw(ctx, p, canvas.width, canvas.height)
      } else {
        ctx.clearRect(0, 0, canvas.width, canvas.height)
        const bgGrad = ctx.createRadialGradient(
          canvas.width / 2, canvas.height / 2, 0,
          canvas.width / 2, canvas.height / 2, Math.max(canvas.width, canvas.height) * 0.7,
        )
        bgGrad.addColorStop(0, '#0a0f1a')
        bgGrad.addColorStop(1, '#05080d')
        ctx.fillStyle = bgGrad
        ctx.fillRect(0, 0, canvas.width, canvas.height)
        ctx.fillStyle = '#64748b'
        ctx.font = '13px Inter, sans-serif'
        ctx.textAlign = 'center'
        ctx.fillText(
          connected ? 'Waiting for map data…' : 'Disconnected — run the map server on the Pi',
          canvas.width / 2,
          canvas.height / 2,
        )
        ctx.textAlign = 'left'
      }
      raf = requestAnimationFrame(render)
    }
    render()
    return () => cancelAnimationFrame(raf)
  }, [connected])

  return (
    <Panel
      title="Area Map"
      icon={MapIcon}
      actions={
        <span
          className={`text-[10px] font-semibold tracking-[0.12em] uppercase ${
            connected ? 'text-live' : 'text-alert'
          }`}
        >
          <span
            className={`mr-1.5 inline-block h-1.5 w-1.5 rounded-full ${
              connected ? 'bg-live animate-blip' : 'bg-alert'
            }`}
          />
          {connected ? 'Live' : 'Offline'}
        </span>
      }
    >
      <div className="relative w-full" style={{ aspectRatio: '16 / 10' }}>
        <canvas
          ref={canvasRef}
          width={1280}
          height={800}
          className="h-full w-full"
        />
      </div>
    </Panel>
  )
}
