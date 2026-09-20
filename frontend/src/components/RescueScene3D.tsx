import { Canvas, useFrame } from '@react-three/fiber'
import { OrbitControls, Grid } from '@react-three/drei'
import { useRef, useMemo } from 'react'
import * as THREE from 'three'
import type { MapPayload, SoundSource, HeatPoint, Hazard } from '../types'

const ROVER_COLOR = '#22c55e'
const OBSTACLE_COLOR = '#475569'
const HAZARD_COLOR = '#ef4444'
const HEAT_WARM = '#f59e0b'
const HEAT_HOT = '#ef4444'
const SOUND_DISTRESS = '#ef4444'
const SOUND_VOICE = '#38bdf8'
const SOUND_SPEECH = '#a78bfa'

function Rover({ pose }: { pose: [number, number, number] }) {
  const ref = useRef<THREE.Group>(null)
  const [x, y, heading] = pose
  const headingRad = (heading * Math.PI) / 180

  useFrame(() => {
    if (ref.current) {
      ref.current.position.set(x, 0, -y)
      ref.current.rotation.y = -headingRad
    }
  })

  return (
    <group ref={ref}>
      {/* Body */}
      <mesh castShadow position={[0, 0.15, 0]}>
        <boxGeometry args={[0.4, 0.2, 0.3]} />
        <meshStandardMaterial color={ROVER_COLOR} emissive={ROVER_COLOR} emissiveIntensity={0.3} />
      </mesh>
      {/* Wheels */}
      {[[0.15, -0.15], [0.15, 0.15], [-0.15, -0.15], [-0.15, 0.15]].map(([wx, wz], i) => (
        <mesh key={i} position={[wx, 0.05, wz]} rotation={[0, 0, Math.PI / 2]}>
          <cylinderGeometry args={[0.06, 0.06, 0.04, 16]} />
          <meshStandardMaterial color="#1e293b" />
        </mesh>
      ))}
      {/* Sensor cone */}
      <mesh position={[0, 0.15, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <coneGeometry args={[0.5, 1.5, 32, 1, true]} />
        <meshStandardMaterial
          color="#22d3ee"
          transparent
          opacity={0.12}
          side={THREE.DoubleSide}
          emissive="#22d3ee"
          emissiveIntensity={0.2}
        />
      </mesh>
      {/* Heading indicator */}
      <mesh position={[0.3, 0.15, 0]}>
        <boxGeometry args={[0.15, 0.03, 0.03]} />
        <meshStandardMaterial color="#bbf7d0" emissive="#22c55e" emissiveIntensity={0.5} />
      </mesh>
    </group>
  )
}

function ObstacleField({ obstacles }: { obstacles: { x: number; y: number; prob: number }[] }) {
  return (
    <>
      {obstacles
        .filter((o) => o.prob > 0.6)
        .slice(0, 50)
        .map((obs, i) => {
          const height = 0.3 + obs.prob * 1.5
          return (
            <mesh key={i} position={[obs.x, height / 2, -obs.y]} castShadow>
              <boxGeometry args={[0.4, height, 0.4]} />
              <meshStandardMaterial
                color={OBSTACLE_COLOR}
                transparent
                opacity={0.6 + obs.prob * 0.3}
              />
            </mesh>
          )
        })}
    </>
  )
}

function SoundMarker({ sound, t }: { sound: SoundSource; t: number }) {
  const color = sound.kind === 'distress' ? SOUND_DISTRESS : sound.kind === 'voice' ? SOUND_VOICE : SOUND_SPEECH
  const ref = useRef<THREE.Mesh>(null)

  useFrame(() => {
    if (ref.current) {
      const phase = (t * 0.5) % 1
      const scale = 0.3 + phase * 1.5
      ref.current.scale.set(scale, scale, scale)
      const mat = ref.current.material as THREE.MeshStandardMaterial
      mat.opacity = (1 - phase) * 0.4
    }
  })

  return (
    <group position={[sound.x, 0.3, -sound.y]}>
      <mesh ref={ref}>
        <sphereGeometry args={[0.3, 16, 16]} />
        <meshStandardMaterial color={color} transparent opacity={0.4} emissive={color} emissiveIntensity={0.5} />
      </mesh>
      <mesh position={[0, 0.5, 0]}>
        <sphereGeometry args={[0.08, 8, 8]} />
        <meshStandardMaterial color={color} emissive={color} emissiveIntensity={0.8} />
      </mesh>
    </group>
  )
}

function HeatDome({ heat }: { heat: HeatPoint }) {
  const color = heat.status === 'overheat' ? HEAT_HOT : HEAT_WARM
  const radius = heat.status === 'overheat' ? 1.0 : 0.7
  return (
    <mesh position={[heat.x, 0.1, -heat.y]}>
      <sphereGeometry args={[radius, 16, 16, 0, Math.PI * 2, 0, Math.PI / 2]} />
      <meshStandardMaterial
        color={color}
        transparent
        opacity={0.25}
        emissive={color}
        emissiveIntensity={0.4}
        side={THREE.DoubleSide}
      />
    </mesh>
  )
}

function HazardMarker({ hazard }: { hazard: Hazard }) {
  return (
    <group position={[hazard.x, 0.5, -hazard.y]}>
      <mesh>
        <coneGeometry args={[0.2, 0.4, 4]} />
        <meshStandardMaterial color={HAZARD_COLOR} emissive={HAZARD_COLOR} emissiveIntensity={0.5} />
      </mesh>
      <mesh position={[0, -0.25, 0]}>
        <cylinderGeometry args={[0.02, 0.02, 0.5, 8]} />
        <meshStandardMaterial color={HAZARD_COLOR} />
      </mesh>
    </group>
  )
}

function Scene({ payload, t }: { payload: MapPayload | null; t: number }) {
  const roverPose = payload?.rover_pose ?? [0, 0, 0]

  const gridObstacles = useMemo(() => {
    if (!payload?.grid || !payload?.grid_width) return []
    const gw = payload.grid_width
    const gh = payload.grid_height
    const res = payload.grid_resolution_m || 0.2
    const half = (gw * res) / 2
    const obstacles: { x: number; y: number; prob: number }[] = []

    if (typeof payload.grid === 'string') {
      // base64 uint8
      const bytes = atob(payload.grid)
      for (let i = 0; i < gw * gh; i++) {
        const prob = bytes.charCodeAt(i) / 255
        if (prob > 0.6) {
          const col = i % gw
          const row = Math.floor(i / gw)
          obstacles.push({
            x: col * res - half,
            y: half - row * res,
            prob,
          })
        }
      }
    }
    return obstacles
  }, [payload])

  return (
    <>
      <ambientLight intensity={0.3} />
      <directionalLight position={[10, 20, 10]} intensity={0.8} castShadow />
      <pointLight position={[0, 5, 0]} intensity={0.5} color="#22d3ee" />

      {/* Floor */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
        <planeGeometry args={[40, 40]} />
        <meshStandardMaterial color="#0a0f1a" metalness={0.1} roughness={0.9} />
      </mesh>

      {/* Grid overlay */}
      <Grid
        args={[40, 40]}
        cellSize={1}
        cellColor="#1e3a5f"
        sectionSize={5}
        sectionColor="#22d3ee"
        fadeDistance={30}
        fadeStrength={1}
        position={[0, 0.01, 0]}
      />

      {/* Obstacles from occupancy grid */}
      <ObstacleField obstacles={gridObstacles} />

      {/* Sound markers */}
      {(payload?.sound_sources || []).map((s, i) => (
        <SoundMarker key={i} sound={s} t={t} />
      ))}

      {/* Heat domes */}
      {(payload?.heat_points || []).map((h, i) => (
        <HeatDome key={i} heat={h} />
      ))}

      {/* Hazard markers */}
      {(payload?.hazards || []).map((h, i) => (
        <HazardMarker key={i} hazard={h} />
      ))}

      {/* Rover */}
      <Rover pose={roverPose} />

      {/* Environment fog for atmosphere */}
      <fog attach="fog" args={['#05080d', 8, 25]} />
    </>
  )
}

export function RescueScene3D({ payload }: { payload: MapPayload | null }) {
  const tRef = useRef(0)

  return (
    <div className="relative w-full" style={{ aspectRatio: '16 / 10' }}>
      <Canvas
        shadows
        camera={{ position: [5, 5, 5], fov: 60 }}
        gl={{ antialias: true, alpha: false }}
      >
        <color attach="background" args={['#05080d']} />
        <Scene payload={payload} t={tRef.current} />
        <OrbitControls
          enablePan
          enableZoom
          enableRotate
          minDistance={3}
          maxDistance={20}
          maxPolarAngle={Math.PI / 2.2}
          target={[0, 0, 0]}
        />
      </Canvas>
    </div>
  )
}
