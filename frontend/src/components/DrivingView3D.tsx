import { Canvas, useFrame } from '@react-three/fiber'
import { OrbitControls } from '@react-three/drei'
import { useRef } from 'react'
import * as THREE from 'three'
import type { MapPayload } from '../types'

function RoverChase({ pose }: { pose: [number, number, number] }) {
  const ref = useRef<THREE.Group>(null)
  const [x, y, heading] = pose
  const headingRad = (heading * Math.PI) / 180

  useFrame(({ camera }) => {
    if (ref.current) {
      ref.current.position.set(x, 0, -y)
      ref.current.rotation.y = -headingRad
      // Chase camera follows behind rover
      const behindX = x - Math.cos(headingRad) * 3
      const behindZ = -y + Math.sin(headingRad) * 3
      camera.position.lerp(new THREE.Vector3(behindX, 2.5, behindZ), 0.05)
      camera.lookAt(x, 0.5, -y)
    }
  })

  return (
    <group ref={ref}>
      {/* Rover body */}
      <mesh castShadow position={[0, 0.2, 0]}>
        <boxGeometry args={[0.5, 0.25, 0.35]} />
        <meshStandardMaterial color="#22c55e" emissive="#22c55e" emissiveIntensity={0.2} />
      </mesh>
      {/* LiDAR dome on top */}
      <mesh position={[0, 0.4, 0]}>
        <cylinderGeometry args={[0.1, 0.12, 0.08, 16]} />
        <meshStandardMaterial color="#1e293b" metalness={0.8} roughness={0.2} />
      </mesh>
      {/* Wheels */}
      {[[0.2, -0.18], [0.2, 0.18], [-0.2, -0.18], [-0.2, 0.18]].map(([wx, wz], i) => (
        <mesh key={i} position={[wx, 0.07, wz]} rotation={[0, 0, Math.PI / 2]}>
          <cylinderGeometry args={[0.07, 0.07, 0.05, 16]} />
          <meshStandardMaterial color="#0f172a" />
        </mesh>
      ))}
      {/* LiDAR sweep beam */}
      <LiDARSweep />
    </group>
  )
}

function LiDARSweep() {
  const ref = useRef<THREE.Mesh>(null)
  useFrame(({ clock }) => {
    if (ref.current) {
      const t = clock.getElapsedTime()
      ref.current.rotation.y = t * 3
    }
  })
  return (
    <mesh position={[0, 0.4, 0]} rotation={[-Math.PI / 2, 0, 0]}>
      <coneGeometry args={[0.8, 2.5, 32, 1, true, 0, Math.PI / 6]} />
      <meshStandardMaterial
        color="#22d3ee"
        transparent
        opacity={0.08}
        side={THREE.DoubleSide}
        emissive="#22d3ee"
        emissiveIntensity={0.3}
      />
    </mesh>
  )
}

function TerrainObstacles({ payload }: { payload: MapPayload | null }) {
  const obstacles = useRef<{ x: number; y: number; height: number; type: string }[]>([])

  // Static environment that the rover drives through
  if (obstacles.current.length === 0 && payload) {
    const items = [
      { x: 3, y: 2, height: 2.0, type: 'building' },
      { x: -2, y: 4, height: 1.5, type: 'wall' },
      { x: 5, y: -3, height: 1.8, type: 'building' },
      { x: -4, y: -2, height: 1.2, type: 'rubble' },
      { x: 1, y: 6, height: 2.5, type: 'building' },
      { x: 6, y: 3, height: 1.0, type: 'debris' },
      { x: -5, y: 1, height: 1.6, type: 'wall' },
      { x: 2, y: -5, height: 2.2, type: 'building' },
      { x: -3, y: -4, height: 0.8, type: 'rubble' },
      { x: 7, y: 0, height: 1.4, type: 'wall' },
    ]
    obstacles.current = items
  }

  return (
    <>
      {obstacles.current.map((obs, i) => (
        <mesh key={i} position={[obs.x, obs.height / 2, -obs.y]} castShadow>
          {obs.type === 'building' ? (
            <boxGeometry args={[1.0, obs.height, 1.0]} />
          ) : obs.type === 'wall' ? (
            <boxGeometry args={[2.0, obs.height, 0.2]} />
          ) : (
            <dodecahedronGeometry args={[obs.height * 0.4, 0]} />
          )}
          <meshStandardMaterial
            color={obs.type === 'building' ? '#475569' : obs.type === 'wall' ? '#64748b' : '#78716c'}
            transparent
            opacity={0.7}
          />
        </mesh>
      ))}
    </>
  )
}

function GroundGrid() {
  return (
    <>
      <mesh rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
        <planeGeometry args={[50, 50]} />
        <meshStandardMaterial color="#0f1729" metalness={0.1} roughness={0.95} />
      </mesh>
      <gridHelper args={[50, 50, '#1e3a5f', '#0f1729']} position={[0, 0.01, 0]} />
    </>
  )
}

export function DrivingView3D({ payload }: { payload: MapPayload | null }) {
  const roverPose = payload?.rover_pose ?? [0, 0, 0]

  return (
    <div className="relative w-full" style={{ aspectRatio: '16 / 10' }}>
      <Canvas
        shadows
        camera={{ position: [3, 3, 3], fov: 65 }}
        gl={{ antialias: true, alpha: false }}
      >
        <color attach="background" args={['#050810']} />
        <ambientLight intensity={0.25} />
        <directionalLight position={[10, 20, 10]} intensity={0.6} castShadow />
        <pointLight position={[0, 3, 0]} intensity={0.3} color="#22d3ee" />
        <fog attach="fog" args={['#050810', 10, 30]} />

        <GroundGrid />
        <TerrainObstacles payload={payload} />
        <RoverChase pose={roverPose} />

        <OrbitControls
          enablePan
          enableZoom
          enableRotate
          minDistance={2}
          maxDistance={15}
          maxPolarAngle={Math.PI / 2.1}
        />
      </Canvas>
      <div className="absolute left-3 top-3 rounded bg-black/60 px-2 py-1 text-[11px] font-semibold tracking-wider text-cyan-400 uppercase backdrop-blur-sm">
        LiDAR Scan View
      </div>
    </div>
  )
}
