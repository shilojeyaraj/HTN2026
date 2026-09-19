import { Map as MapIcon } from 'lucide-react'
import { useEffect, useRef } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { useMapStream } from '../hooks/useMapStream'
import type { MapPayload } from '../types'
import { Panel } from './ui/Panel'

// ── constants ──────────────────────────────────────────────────────────
const SENSOR_FOV_DEG = 120
const SENSOR_RANGE_M = 2.5

const SOUND_COLORS: Record<string, number> = {
  distress: 0xef4444,
  voice: 0x38bdf8,
  sound: 0xf59e0b,
  speech: 0xa78bfa,
}

// ── helpers ─────────────────────────────────────────────────────────────

/** Decode the occupancy grid from the payload into a Float32Array of 0-1
 *  probabilities. Supports base64_uint8 (compact binary) and legacy float
 *  array formats. */
function decodeGrid(
  grid: string | number[],
  encoding: string | undefined,
  count: number,
): Float32Array {
  if (encoding === 'base64_uint8' && typeof grid === 'string') {
    const binary = atob(grid)
    const bytes = new Uint8Array(binary.length)
    for (let i = 0; i < binary.length; i++) {
      bytes[i] = binary.charCodeAt(i)
    }
    const result = new Float32Array(count)
    for (let i = 0; i < count; i++) {
      result[i] = bytes[i] / 255
    }
    return result
  }
  // legacy: plain float array
  return Float32Array.from(grid as number[])
}

/** Occupancy probability → THREE.Color.  <0.5 free (cyan), >0.5 occupied (amber). */
function probToColor(prob: number, out: THREE.Color): void {
  if (prob === undefined || Math.abs(prob - 0.5) < 0.02) {
    out.setRGB(0.03, 0.04, 0.06) // unknown — dark
    return
  }
  if (prob < 0.5) {
    const t = (0.5 - prob) * 2
    out.setRGB(0.13 * t, 0.83 * t, 0.93 * t)
  } else {
    const t = (prob - 0.5) * 2
    out.setRGB(0.98 * t, 0.57 * t, 0.24 * t)
  }
}

// ── component ───────────────────────────────────────────────────────────

export function MapView() {
  const { payload, connected } = useMapStream()
  const containerRef = useRef<HTMLDivElement>(null)
  const payloadRef = useRef<MapPayload | null>(payload)
  payloadRef.current = payload

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    // ── scene ──────────────────────────────────────────────────────────
    const scene = new THREE.Scene()
    scene.background = new THREE.Color('#05080d')
    scene.fog = new THREE.FogExp2('#05080d', 0.045)

    // ── camera ─────────────────────────────────────────────────────────
    const camera = new THREE.PerspectiveCamera(50, 1, 0.1, 100)
    camera.position.set(5, 7, 5)

    // ── renderer ───────────────────────────────────────────────────────
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.toneMapping = THREE.ACESFilmicToneMapping
    renderer.toneMappingExposure = 1.1
    container.appendChild(renderer.domElement)
    renderer.domElement.style.width = '100%'
    renderer.domElement.style.height = '100%'
    renderer.domElement.style.display = 'block'

    // ── controls ──────────────────────────────────────────────────────
    const controls = new OrbitControls(camera, renderer.domElement)
    controls.enableDamping = true
    controls.dampingFactor = 0.08
    controls.maxPolarAngle = Math.PI / 2.05 // keep camera above ground
    controls.minDistance = 1.5
    controls.maxDistance = 30

    // ── lights ─────────────────────────────────────────────────────────
    scene.add(new THREE.AmbientLight(0x3b4a5e, 0.7))
    const dirLight = new THREE.DirectionalLight(0xffffff, 0.9)
    dirLight.position.set(6, 12, 4)
    scene.add(dirLight)
    const fillLight = new THREE.DirectionalLight(0x38bdf8, 0.25)
    fillLight.position.set(-5, 4, -5)
    scene.add(fillLight)

    // ── ground reference grid ─────────────────────────────────────────
    const gridHelper = new THREE.GridHelper(20, 20, 0x1e2b3a, 0x0f1620)
    ;(gridHelper.material as THREE.Material).transparent = true
    ;(gridHelper.material as THREE.Material).opacity = 0.35
    scene.add(gridHelper)

    // ── occupancy grid (instanced voxels) ──────────────────────────────
    const boxGeo = new THREE.BoxGeometry(1, 1, 1)
    const gridMat = new THREE.MeshStandardMaterial({
      roughness: 0.65,
      metalness: 0.1,
      transparent: true,
      opacity: 0.88,
    })
    let gridMesh: THREE.InstancedMesh | null = null
    let gridDims = { w: 0, h: 0 }

    const dummy = new THREE.Object3D()
    const tmpColor = new THREE.Color()

    // ── rover ──────────────────────────────────────────────────────────
    const roverGroup = new THREE.Group()
    scene.add(roverGroup)

    // body — arrow pointing +X (forward at heading 0)
    const bodyGeo = new THREE.ConeGeometry(0.14, 0.38, 4)
    bodyGeo.rotateZ(Math.PI / 2) // apex → +X
    const bodyMat = new THREE.MeshStandardMaterial({
      color: 0x22c55e,
      emissive: 0x22c55e,
      emissiveIntensity: 0.45,
      roughness: 0.4,
    })
    const bodyMesh = new THREE.Mesh(bodyGeo, bodyMat)
    bodyMesh.position.y = 0.12
    roverGroup.add(bodyMesh)

    // glow ring under rover
    const ringGeo = new THREE.RingGeometry(0.18, 0.26, 32)
    ringGeo.rotateX(-Math.PI / 2)
    const ringMat = new THREE.MeshBasicMaterial({
      color: 0x22c55e,
      transparent: true,
      opacity: 0.35,
      side: THREE.DoubleSide,
    })
    const ringMesh = new THREE.Mesh(ringGeo, ringMat)
    ringMesh.position.y = 0.01
    roverGroup.add(ringMesh)

    // sensor cone — semi-transparent, fans forward
    const coneGeo = new THREE.ConeGeometry(
      Math.tan((SENSOR_FOV_DEG / 2) * Math.PI / 180) * SENSOR_RANGE_M,
      SENSOR_RANGE_M,
      32,
      1,
      true,
    )
    // lay flat: apex at rover, base forward (+X)
    coneGeo.rotateZ(-Math.PI / 2) // apex → -X, base → +X
    coneGeo.translate(SENSOR_RANGE_M / 2, 0, 0) // apex at 0, base at +X
    const coneMat = new THREE.MeshBasicMaterial({
      color: 0x22d3ee,
      transparent: true,
      opacity: 0.1,
      side: THREE.DoubleSide,
      depthWrite: false,
    })
    const coneMesh = new THREE.Mesh(coneGeo, coneMat)
    coneMesh.position.y = 0.12
    roverGroup.add(coneMesh)

    // ── trail ──────────────────────────────────────────────────────────
    const trailMat = new THREE.LineBasicMaterial({
      vertexColors: true,
      transparent: true,
      opacity: 0.75,
      linewidth: 2,
    })
    let trailLine: THREE.Line | null = null

    // ── markers (shared geometries + material cache) ────────────────────
    const markersGroup = new THREE.Group()
    scene.add(markersGroup)

    const soundGeo = new THREE.SphereGeometry(0.09, 16, 16)
    const heatGeo = new THREE.SphereGeometry(0.14, 16, 16)
    const hazardGeo = new THREE.ConeGeometry(0.11, 0.28, 4)
    const annotGeo = new THREE.SphereGeometry(0.06, 12, 12)
    const ringMarkerGeo = new THREE.RingGeometry(0.12, 0.16, 24)
    ringMarkerGeo.rotateX(-Math.PI / 2)

    const matCache = new Map<string, THREE.MeshStandardMaterial>()
    function getMat(color: number, intensity = 0.6): THREE.MeshStandardMaterial {
      const key = `${color}_${intensity}`
      let m = matCache.get(key)
      if (!m) {
        m = new THREE.MeshStandardMaterial({
          color,
          emissive: color,
          emissiveIntensity: intensity,
          roughness: 0.35,
        })
        matCache.set(key, m)
      }
      return m
    }

    const annotMat = new THREE.MeshBasicMaterial({ color: 0x38bdf8 })
    const annotRingMat = new THREE.MeshBasicMaterial({
      color: 0x38bdf8,
      transparent: true,
      opacity: 0.4,
      side: THREE.DoubleSide,
    })

    // ── resize ─────────────────────────────────────────────────────────
    const resize = () => {
      const w = container.clientWidth
      const h = container.clientHeight
      if (w === 0 || h === 0) return
      renderer.setSize(w, h, false)
      camera.aspect = w / h
      camera.updateProjectionMatrix()
    }
    resize()
    const ro = new ResizeObserver(resize)
    ro.observe(container)

    // ── animation loop ─────────────────────────────────────────────────
    let raf: number
    const clock = new THREE.Clock()
    let lastProcessed: MapPayload | null = null
    const lastRoverPos = new THREE.Vector3()

    const render = () => {
      raf = requestAnimationFrame(render)
      const elapsed = clock.getElapsedTime()
      const p = payloadRef.current

      // Only rebuild the scene graph when a new payload arrives (5 Hz).
      if (p && p !== lastProcessed) {
        lastProcessed = p
        const gw = p.grid_width || 100
        const gh = p.grid_height || 100
        const res = p.grid_resolution_m || 0.2
        const grid = decodeGrid(p.grid, p.grid_encoding, gw * gh)

        // ── occupancy grid ───────────────────────────────────────────
        const count = gw * gh
        if (!gridMesh || gridDims.w !== gw || gridDims.h !== gh) {
          if (gridMesh) {
            scene.remove(gridMesh)
            gridMesh.dispose()
          }
          gridMesh = new THREE.InstancedMesh(boxGeo, gridMat, count)
          gridMesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage)
          scene.add(gridMesh)
          gridDims = { w: gw, h: gh }
        }

        for (let row = 0; row < gh; row++) {
          for (let col = 0; col < gw; col++) {
            const i = row * gw + col
            const prob = grid[i] ?? 0.5
            const wx = (col - gw / 2) * res
            const wz = (gh / 2 - row) * res

            if (Math.abs(prob - 0.5) < 0.02) {
              // unknown — hide
              dummy.scale.set(0, 0, 0)
              dummy.position.set(wx, 0, wz)
              dummy.updateMatrix()
              gridMesh.setMatrixAt(i, dummy.matrix)
              continue
            }

            if (prob > 0.5) {
              // occupied — raised wall
              const h = (prob - 0.5) * 2 * 0.5 + 0.05
              dummy.scale.set(res * 0.92, h, res * 0.92)
              dummy.position.set(wx, h / 2, wz)
            } else {
              // free — flat floor tile
              dummy.scale.set(res * 0.88, 0.03, res * 0.88)
              dummy.position.set(wx, 0.015, wz)
            }
            dummy.updateMatrix()
            gridMesh.setMatrixAt(i, dummy.matrix)
            probToColor(prob, tmpColor)
            gridMesh.setColorAt(i, tmpColor)
          }
        }
        gridMesh.instanceMatrix.needsUpdate = true
        if (gridMesh.instanceColor) gridMesh.instanceColor.needsUpdate = true

        // ── rover pose ───────────────────────────────────────────────
        const [rx, ry, heading] = p.rover_pose
        roverGroup.position.set(rx, 0, ry)
        roverGroup.rotation.y = (-heading * Math.PI) / 180

        // camera follows rover (keep relative offset)
        const roverPos = new THREE.Vector3(rx, 0, ry)
        const delta = roverPos.clone().sub(lastRoverPos)
        if (lastRoverPos.lengthSq() > 0) {
          camera.position.add(delta)
        }
        controls.target.copy(roverPos)
        lastRoverPos.copy(roverPos)

        // ── trail ─────────────────────────────────────────────────────
        if (trailLine) {
          scene.remove(trailLine)
          trailLine.geometry.dispose()
          trailLine = null
        }
        if (p.trail && p.trail.length > 1) {
          const pts = p.trail.map(
            ([tx, ty]) => new THREE.Vector3(tx, 0.04, ty),
          )
          const trailGeo = new THREE.BufferGeometry().setFromPoints(pts)
          const colors = new Float32Array(pts.length * 3)
          for (let i = 0; i < pts.length; i++) {
            const a = i / pts.length
            colors[i * 3] = 0.13 * a
            colors[i * 3 + 1] = 0.77 * a + 0.05
            colors[i * 3 + 2] = 0.37 * a
          }
          trailGeo.setAttribute('color', new THREE.BufferAttribute(colors, 3))
          trailLine = new THREE.Line(trailGeo, trailMat)
          scene.add(trailLine)
        }

        // ── markers ──────────────────────────────────────────────────
        // dispose old marker meshes (geometries are shared, so just clear)
        markersGroup.clear()

        for (const ss of p.sound_sources || []) {
          const c = SOUND_COLORS[ss.kind] ?? 0xf59e0b
          const isDanger = ss.kind === 'distress' || (ss.db ?? 0) >= 80
          const mat = getMat(c, isDanger ? 0.8 : 0.55)
          const m = new THREE.Mesh(soundGeo, mat)
          m.position.set(ss.x, 0.12, ss.y)
          m.userData.pulse = true
          m.userData.pulseSpeed = isDanger ? 3 : 2
          m.userData.baseScale = isDanger ? 1.3 : 1
          markersGroup.add(m)
        }

        for (const hp of p.heat_points || []) {
          const c = hp.status === 'overheat' ? 0xef4444 : 0xf59e0b
          const mat = getMat(c, 0.85)
          const m = new THREE.Mesh(heatGeo, mat)
          m.position.set(hp.x, 0.16, hp.y)
          m.userData.pulse = true
          m.userData.pulseSpeed = hp.status === 'overheat' ? 4 : 2.5
          m.userData.baseScale = hp.status === 'overheat' ? 1.4 : 1
          markersGroup.add(m)
        }

        for (const hz of p.hazards || []) {
          const mat = getMat(0xef4444, 0.5)
          const m = new THREE.Mesh(hazardGeo, mat)
          m.position.set(hz.x, 0.14, hz.y)
          m.rotation.y = Math.PI / 4
          markersGroup.add(m)
        }

        for (const ann of p.annotations || []) {
          const dot = new THREE.Mesh(annotGeo, annotMat)
          dot.position.set(ann.x, 0.06, ann.y)
          markersGroup.add(dot)
          const ring = new THREE.Mesh(ringMarkerGeo, annotRingMat)
          ring.position.set(ann.x, 0.02, ann.y)
          markersGroup.add(ring)
        }
      }

      // ── per-frame animations ──────────────────────────────────────────
      // pulsing markers
      for (const m of markersGroup.children) {
        if (m.userData.pulse) {
          const s =
            m.userData.baseScale *
            (1 + 0.25 * Math.sin(elapsed * m.userData.pulseSpeed))
          m.scale.setScalar(s)
        }
      }

      // sensor cone shimmer
      coneMat.opacity = 0.08 + 0.04 * Math.sin(elapsed * 1.5)

      // rover ring pulse
      ringMat.opacity = 0.25 + 0.15 * Math.sin(elapsed * 2)

      controls.update()
      renderer.render(scene, camera)
    }
    render()

    // ── cleanup ────────────────────────────────────────────────────────
    return () => {
      cancelAnimationFrame(raf)
      ro.disconnect()
      controls.dispose()

      boxGeo.dispose()
      gridMat.dispose()
      bodyGeo.dispose()
      bodyMat.dispose()
      ringGeo.dispose()
      ringMat.dispose()
      coneGeo.dispose()
      coneMat.dispose()
      trailMat.dispose()
      soundGeo.dispose()
      heatGeo.dispose()
      hazardGeo.dispose()
      annotGeo.dispose()
      ringMarkerGeo.dispose()
      annotMat.dispose()
      annotRingMat.dispose()
      matCache.forEach((m) => m.dispose())

      if (trailLine) trailLine.geometry.dispose()
      if (gridMesh) {
        gridMesh.dispose()
      }
      markersGroup.clear()

      renderer.dispose()
      if (renderer.domElement.parentNode) {
        renderer.domElement.parentNode.removeChild(renderer.domElement)
      }
    }
  }, [])

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
      <div
        ref={containerRef}
        className="relative w-full"
        style={{ aspectRatio: '16 / 10' }}
      >
        {!payload && (
          <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
            <span className="text-sm text-ink-faint">
              {connected
                ? 'Waiting for map data…'
                : 'Disconnected — run the map server on the Pi'}
            </span>
          </div>
        )}
      </div>
    </Panel>
  )
}
