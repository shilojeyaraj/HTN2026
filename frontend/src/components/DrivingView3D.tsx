import { Canvas, useFrame } from '@react-three/fiber'
import { OrbitControls, Environment, ContactShadows } from '@react-three/drei'
import { useRef, useMemo } from 'react'
import * as THREE from 'three'
import type { MapPayload } from '../types'

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
      <mesh castShadow position={[0, 0.25, 0]}>
        <boxGeometry args={[0.6, 0.3, 0.4]} />
        <meshStandardMaterial color="#22c55e" metalness={0.3} roughness={0.4} emissive="#22c55e" emissiveIntensity={0.15} />
      </mesh>
      {/* Cabin */}
      <mesh castShadow position={[0, 0.45, 0]}>
        <boxGeometry args={[0.4, 0.2, 0.35]} />
        <meshStandardMaterial color="#1e293b" metalness={0.6} roughness={0.2} />
      </mesh>
      {/* LiDAR unit */}
      <mesh position={[0, 0.6, 0]}>
        <cylinderGeometry args={[0.08, 0.1, 0.06, 16]} />
        <meshStandardMaterial color="#334155" metalness={0.9} roughness={0.1} />
      </mesh>
      {/* Rotating LiDAR beam */}
      <mesh position={[0, 0.6, 0]} rotation={[0, 0, 0]}>
        <boxGeometry args={[0.02, 0.02, 1.5]} />
        <meshStandardMaterial color="#22d3ee" emissive="#22d3ee" emissiveIntensity={1} transparent opacity={0.4} />
      </mesh>
      {/* Wheels */}
      {[[0.25, -0.22], [0.25, 0.22], [-0.25, -0.22], [-0.25, 0.22]].map(([wx, wz], i) => (
        <mesh key={i} position={[wx, 0.1, wz]} rotation={[0, 0, Math.PI / 2]} castShadow>
          <cylinderGeometry args={[0.1, 0.1, 0.06, 16]} />
          <meshStandardMaterial color="#0f172a" roughness={0.8} />
        </mesh>
      ))}
      {/* Headlights */}
      <mesh position={[0.3, 0.25, 0.15]}>
        <sphereGeometry args={[0.04, 8, 8]} />
        <meshStandardMaterial color="#fef3c7" emissive="#fde68a" emissiveIntensity={2} />
      </mesh>
      <mesh position={[0.3, 0.25, -0.15]}>
        <sphereGeometry args={[0.04, 8, 8]} />
        <meshStandardMaterial color="#fef3c7" emissive="#fde68a" emissiveIntensity={2} />
      </mesh>
    </group>
  )
}

function Building({ position, size, color }: { position: [number, number, number]; size: [number, number, number]; color: string }) {
  return (
    <mesh position={position} castShadow receiveShadow>
      <boxGeometry args={size} />
      <meshStandardMaterial color={color} roughness={0.7} metalness={0.1} />
    </mesh>
  )
}

function RubblePile({ position }: { position: [number, number, number] }) {
  return (
    <group position={position}>
      {[0, 1, 2, 3, 4].map((i) => (
        <mesh
          key={i}
          position={[
            (Math.sin(i * 2.3) * 0.3),
            0.2 + i * 0.15,
            (Math.cos(i * 1.7) * 0.3),
          ]}
          rotation={[Math.random(), Math.random(), Math.random()]}
          castShadow
        >
          <dodecahedronGeometry args={[0.25 + i * 0.05, 0]} />
          <meshStandardMaterial color="#78716c" roughness={0.9} />
        </mesh>
      ))}
    </group>
  )
}

function DustParticles() {
  const ref = useRef<THREE.Points>(null)
  const count = 200

  const positions = useMemo(() => {
    const arr = new Float32Array(count * 3)
    for (let i = 0; i < count; i++) {
      arr[i * 3] = (Math.random() - 0.5) * 20
      arr[i * 3 + 1] = Math.random() * 3
      arr[i * 3 + 2] = (Math.random() - 0.5) * 20
    }
    return arr
  }, [])

  useFrame(({ clock }) => {
    if (ref.current) {
      ref.current.rotation.y = clock.getElapsedTime() * 0.02
    }
  })

  return (
    <points ref={ref}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" count={count} array={positions} itemSize={3} args={[positions, 3]} />
      </bufferGeometry>
      <pointsMaterial size={0.03} color="#94a3b8" transparent opacity={0.3} sizeAttenuation />
    </points>
  )
}

export function DrivingView3D({ payload }: { payload: MapPayload | null }) {
  const roverPose = payload?.rover_pose ?? [0, 0, 0]

  return (
    <div className="relative w-full" style={{ aspectRatio: '16 / 10' }}>
      <Canvas
        shadows
        camera={{ position: [3, 2.5, 4], fov: 65 }}
        gl={{ antialias: true, alpha: false }}
      >
        <color attach="background" args={['#0a0f1a']} />
        <fog attach="fog" args={['#0a0f1a', 8, 25]} />

        {/* Lighting */}
        <ambientLight intensity={0.15} />
        <directionalLight
          position={[8, 15, 8]}
          intensity={0.4}
          castShadow
          shadow-mapSize={[2048, 2048]}
          shadow-camera-far={30}
          shadow-camera-left={-15}
          shadow-camera-right={15}
          shadow-camera-top={15}
          shadow-camera-bottom={-15}
        />
        <Environment preset="night" />

        {/* Ground */}
        <mesh rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
          <planeGeometry args={[50, 50]} />
          <meshStandardMaterial color="#1a1f2e" roughness={1} metalness={0} />
        </mesh>
        <gridHelper args={[50, 50, '#1e3a5f', '#0f1729']} position={[0, 0.01, 0]} />

        {/* Buildings */}
        <Building position={[4, 1.5, -3]} size={[2, 3, 2]} color="#3b4252" />
        <Building position={[-3, 1.2, -5]} size={[1.5, 2.4, 1.5]} color="#4c5566" />
        <Building position={[6, 2, 2]} size={[2.5, 4, 2.5]} color="#374151" />
        <Building position={[-5, 1, 3]} size={[1.8, 2, 1.8]} color="#4b5563" />
        <Building position={[2, 1.8, -7]} size={[2, 3.6, 2]} color="#3f4756" />
        <Building position={[-6, 0.8, -1]} size={[1.2, 1.6, 1.2]} color="#525b6a" />

        {/* Walls */}
        <Building position={[0, 0.6, 5]} size={[4, 1.2, 0.2]} color="#475569" />
        <Building position={[-7, 0.5, -3]} size={[0.2, 1, 4]} color="#475569" />

        {/* Rubble piles */}
        <RubblePile position={[1, 0, 2]} />
        <RubblePile position={[-2, 0, -3]} />
        <RubblePile position={[5, 0, -1]} />

        {/* Dust atmosphere */}
        <DustParticles />

        {/* Rover */}
        <Rover pose={roverPose} />

        <ContactShadows position={[0, 0.01, 0]} opacity={0.4} scale={20} blur={2} far={5} />

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
        Rescue Rover — Live View
      </div>
    </div>
  )
}
