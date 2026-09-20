import { Canvas, useFrame } from '@react-three/fiber'
import { OrbitControls, Grid, Line, Html } from '@react-three/drei'
import { useRef, useMemo } from 'react'
import * as THREE from 'three'
import type { MapPayload, SoundSource, HeatPoint, Hazard, Annotation } from '../types'

function MappedRover({ pose }: { pose: [number, number, number] }) {
  const ref = useRef<THREE.Group>(null)
  const [x, y, heading] = pose
  const headingRad = (heading * Math.PI) / 180

  useFrame(() => {
    if (ref.current) {
      ref.current.position.set(x, 0.1, -y)
      ref.current.rotation.y = -headingRad
    }
  })

  return (
    <group ref={ref}>
      <mesh position={[0, 0.1, 0]}>
        <boxGeometry args={[0.3, 0.15, 0.2]} />
        <meshStandardMaterial color="#22c55e" emissive="#22c55e" emissiveIntensity={0.4} />
      </mesh>
      <mesh position={[0.2, 0.1, 0]}>
        <boxGeometry args={[0.1, 0.02, 0.02]} />
        <meshStandardMaterial color="#bbf7d0" emissive="#22c55e" emissiveIntensity={0.6} />
      </mesh>
    </group>
  )
}

function DetectionLabel({ position, text, color }: { position: [number, number, number]; text: string; color: string }) {
  return (
    <Html position={position} center distanceFactor={8} occlude>
      <div
        className="pointer-events-none whitespace-nowrap rounded-md px-2 py-1 text-[10px] font-semibold tracking-wide shadow-lg backdrop-blur-sm"
        style={{
          backgroundColor: `${color}22`,
          border: `1px solid ${color}`,
          color: color,
        }}
      >
        {text}
      </div>
    </Html>
  )
}

function MappedObstacles({ payload }: { payload: MapPayload | null }) {
  const obstacles = useMemo(() => {
    if (!payload?.grid || !payload?.grid_width) return []
    const gw = payload.grid_width
    const gh = payload.grid_height
    const res = payload.grid_resolution_m || 0.2
    const half = (gw * res) / 2
    const result: { x: number; y: number; prob: number }[] = []

    if (typeof payload.grid === 'string') {
      const bytes = atob(payload.grid)
      for (let i = 0; i < gw * gh; i++) {
        const prob = bytes.charCodeAt(i) / 255
        if (prob > 0.6) {
          const col = i % gw
          const row = Math.floor(i / gw)
          result.push({
            x: col * res - half,
            y: half - row * res,
            prob,
          })
        }
      }
    }
    return result
  }, [payload])

  return (
    <>
      {obstacles.slice(0, 80).map((obs, i) => {
        const height = 0.2 + obs.prob * 1.8
        return (
          <mesh key={i} position={[obs.x, height / 2, -obs.y]}>
            <boxGeometry args={[0.35, height, 0.35]} />
            <meshStandardMaterial
              color="#475569"
              transparent
              opacity={0.5 + obs.prob * 0.4}
              emissive="#22d3ee"
              emissiveIntensity={obs.prob * 0.1}
            />
          </mesh>
        )
      })}
    </>
  )
}

function MappedSounds({ sounds }: { sounds: SoundSource[] }) {
  return (
    <>
      {sounds.map((s, i) => {
        const color = s.kind === 'distress' ? '#ef4444' : s.kind === 'voice' ? '#38bdf8' : '#a78bfa'
        const label = s.kind === 'distress' ? 'DISTRESS' : s.kind === 'voice' ? 'VOICE' : 'SPEECH'
        return (
          <group key={i}>
            <mesh position={[s.x, 0.3, -s.y]}>
              <sphereGeometry args={[0.15, 12, 12]} />
              <meshStandardMaterial color={color} emissive={color} emissiveIntensity={0.6} transparent opacity={0.7} />
            </mesh>
            <DetectionLabel position={[s.x, 0.6, -s.y]} text={`${label}: ${s.label}`} color={color} />
          </group>
        )
      })}
    </>
  )
}

function MappedHeat({ heat }: { heat: HeatPoint[] }) {
  return (
    <>
      {heat.map((h, i) => {
        const color = h.status === 'overheat' ? '#ef4444' : '#f59e0b'
        const radius = h.status === 'overheat' ? 0.8 : 0.5
        return (
          <group key={i}>
            <mesh position={[h.x, 0.05, -h.y]}>
              <sphereGeometry args={[radius, 16, 16, 0, Math.PI * 2, 0, Math.PI / 2]} />
              <meshStandardMaterial color={color} transparent opacity={0.2} emissive={color} emissiveIntensity={0.3} side={THREE.DoubleSide} />
            </mesh>
            <DetectionLabel position={[h.x, 0.8, -h.y]} text={`${h.celsius}°C ${h.status.toUpperCase()}`} color={color} />
          </group>
        )
      })}
    </>
  )
}

function MappedHazards({ hazards }: { hazards: Hazard[] }) {
  return (
    <>
      {hazards.map((h, i) => (
        <group key={i}>
          <mesh position={[h.x, 0.4, -h.y]}>
            <coneGeometry args={[0.15, 0.3, 4]} />
            <meshStandardMaterial color="#ef4444" emissive="#ef4444" emissiveIntensity={0.5} />
          </mesh>
          <DetectionLabel position={[h.x, 0.7, -h.y]} text={`HAZARD: ${h.type.toUpperCase()}`} color="#ef4444" />
        </group>
      ))}
    </>
  )
}

function MappedAnnotations({ annotations }: { annotations: Annotation[] }) {
  return (
    <>
      {annotations.map((a, i) => (
        <DetectionLabel key={i} position={[a.x, 0.5, -a.y]} text={a.text} color="#7dd3fc" />
      ))}
    </>
  )
}

function Trail3D({ trail }: { trail: number[][] }) {
  const points = useMemo(() => {
    return trail.map(([x, y]) => [x, 0.05, -y] as [number, number, number])
  }, [trail])

  if (points.length < 2) return null

  return <Line points={points} color="#22c55e" lineWidth={2} transparent opacity={0.4} />
}

export function MappingView3D({ payload }: { payload: MapPayload | null }) {
  return (
    <div className="relative w-full" style={{ aspectRatio: '16 / 10' }}>
      <Canvas
        shadows
        camera={{ position: [6, 6, 6], fov: 55 }}
        gl={{ antialias: true, alpha: false }}
      >
        <color attach="background" args={['#05080d']} />
        <ambientLight intensity={0.3} />
        <directionalLight position={[10, 20, 10]} intensity={0.7} castShadow />
        <pointLight position={[0, 5, 0]} intensity={0.3} color="#22d3ee" />
        <fog attach="fog" args={['#05080d', 12, 30]} />

        {/* Floor */}
        <mesh rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
          <planeGeometry args={[40, 40]} />
          <meshStandardMaterial color="#0a0f1a" metalness={0.1} roughness={0.9} />
        </mesh>

        <Grid
          args={[40, 40]}
          cellSize={1}
          cellColor="#1e3a5f"
          sectionSize={5}
          sectionColor="#22d3ee"
          fadeDistance={25}
          fadeStrength={1}
          position={[0, 0.01, 0]}
        />

        <MappedObstacles payload={payload} />

        {payload?.trail && payload.trail.length > 1 && (
          <Trail3D trail={payload.trail} />
        )}

        <MappedSounds sounds={payload?.sound_sources || []} />
        <MappedHeat heat={payload?.heat_points || []} />
        <MappedHazards hazards={payload?.hazards || []} />
        <MappedAnnotations annotations={payload?.annotations || []} />

        <MappedRover pose={payload?.rover_pose ?? [0, 0, 0]} />

        <OrbitControls
          enablePan
          enableZoom
          enableRotate
          minDistance={3}
          maxDistance={25}
          maxPolarAngle={Math.PI / 2.2}
          target={[0, 0, 0]}
        />
      </Canvas>
      <div className="absolute left-3 top-3 rounded bg-black/60 px-2 py-1 text-[11px] font-semibold tracking-wider text-cyan-400 uppercase backdrop-blur-sm">
        3D Occupancy Map — LiDAR + Sensor Fusion
      </div>
    </div>
  )
}
