import { Canvas, useFrame } from '@react-three/fiber'
import { OrbitControls, Environment, ContactShadows } from '@react-three/drei'
import { useRef, useMemo } from 'react'
import * as THREE from 'three'
import type { MapPayload, SoundSource } from '../types'

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
      <mesh castShadow position={[0, 0.25, 0]}>
        <boxGeometry args={[0.6, 0.3, 0.4]} />
        <meshStandardMaterial color="#22c55e" metalness={0.3} roughness={0.4} emissive="#22c55e" emissiveIntensity={0.15} />
      </mesh>
      <mesh castShadow position={[0, 0.45, 0]}>
        <boxGeometry args={[0.4, 0.2, 0.35]} />
        <meshStandardMaterial color="#1e293b" metalness={0.6} roughness={0.2} />
      </mesh>
      <mesh position={[0, 0.6, 0]}>
        <cylinderGeometry args={[0.08, 0.1, 0.06, 16]} />
        <meshStandardMaterial color="#334155" metalness={0.9} roughness={0.1} />
      </mesh>
      <mesh position={[0, 0.6, 0]} rotation={[0, 0, 0]}>
        <boxGeometry args={[0.02, 0.02, 1.5]} />
        <meshStandardMaterial color="#22d3ee" emissive="#22d3ee" emissiveIntensity={1} transparent opacity={0.4} />
      </mesh>
      {[[0.25, -0.22], [0.25, 0.22], [-0.25, -0.22], [-0.25, 0.22]].map(([wx, wz], i) => (
        <mesh key={i} position={[wx, 0.1, wz]} rotation={[0, 0, Math.PI / 2]} castShadow>
          <cylinderGeometry args={[0.1, 0.1, 0.06, 16]} />
          <meshStandardMaterial color="#0f172a" roughness={0.8} />
        </mesh>
      ))}
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

function Person({ position, waving = false, color = '#d4a574' }: { position: [number, number, number]; waving?: boolean; color?: string }) {
  const armRef = useRef<THREE.Mesh>(null)

  useFrame(({ clock }) => {
    if (armRef.current && waving) {
      armRef.current.rotation.x = Math.sin(clock.getElapsedTime() * 3) * 0.5 - 0.3
    }
  })

  return (
    <group position={position}>
      {/* Head */}
      <mesh castShadow position={[0, 1.7, 0]}>
        <sphereGeometry args={[0.12, 12, 12]} />
        <meshStandardMaterial color={color} roughness={0.6} />
      </mesh>
      {/* Body */}
      <mesh castShadow position={[0, 1.1, 0]}>
        <capsuleGeometry args={[0.15, 0.6, 8, 16]} />
        <meshStandardMaterial color="#4a5568" roughness={0.7} />
      </mesh>
      {/* Left arm */}
      <mesh ref={armRef} castShadow position={[0.22, 1.3, 0]} rotation={[0, 0, -0.3]}>
        <capsuleGeometry args={[0.05, 0.4, 8, 16]} />
        <meshStandardMaterial color={color} roughness={0.6} />
      </mesh>
      {/* Right arm */}
      <mesh castShadow position={[-0.22, 1.3, 0]} rotation={[0, 0, 0.3]}>
        <capsuleGeometry args={[0.05, 0.4, 8, 16]} />
        <meshStandardMaterial color={color} roughness={0.6} />
      </mesh>
      {/* Legs */}
      <mesh castShadow position={[0.08, 0.4, 0]}>
        <capsuleGeometry args={[0.06, 0.5, 8, 16]} />
        <meshStandardMaterial color="#2d3748" roughness={0.8} />
      </mesh>
      <mesh castShadow position={[-0.08, 0.4, 0]}>
        <capsuleGeometry args={[0.06, 0.5, 8, 16]} />
        <meshStandardMaterial color="#2d3748" roughness={0.8} />
      </mesh>
    </group>
  )
}

function Building({ position, size, color, damaged = false }: { position: [number, number, number]; size: [number, number, number]; color: string; damaged?: boolean }) {
  return (
    <group position={position}>
      <mesh castShadow receiveShadow>
        <boxGeometry args={size} />
        <meshStandardMaterial color={color} roughness={0.7} metalness={0.1} />
      </mesh>
      {damaged && (
        <>
          {/* Cracks / broken top */}
          <mesh position={[size[0] * 0.2, size[1] * 0.5, size[2] * 0.3]} rotation={[0.3, 0.5, 0.2]}>
            <boxGeometry args={[size[0] * 0.3, size[1] * 0.2, size[2] * 0.3]} />
            <meshStandardMaterial color="#1a1a2e" roughness={0.9} />
          </mesh>
          <mesh position={[-size[0] * 0.3, size[1] * 0.3, -size[2] * 0.2]} rotation={[-0.2, -0.3, 0.4]}>
            <boxGeometry args={[size[0] * 0.2, size[1] * 0.15, size[2] * 0.2]} />
            <meshStandardMaterial color="#16213e" roughness={0.9} />
          </mesh>
        </>
      )}
    </group>
  )
}

function RubblePile({ position, scale = 1 }: { position: [number, number, number]; scale?: number }) {
  return (
    <group position={position} scale={scale}>
      {[0, 1, 2, 3, 4, 5].map((i) => (
        <mesh
          key={i}
          position={[
            Math.sin(i * 2.3) * 0.4,
            0.15 + i * 0.12,
            Math.cos(i * 1.7) * 0.4,
          ]}
          rotation={[Math.random() * 3, Math.random() * 3, Math.random() * 3]}
          castShadow
        >
          <dodecahedronGeometry args={[0.2 + i * 0.04, 0]} />
          <meshStandardMaterial color={i % 2 === 0 ? '#78716c' : '#6b7280'} roughness={0.9} />
        </mesh>
      ))}
    </group>
  )
}

function Tree({ position }: { position: [number, number, number] }) {
  return (
    <group position={position}>
      <mesh castShadow position={[0, 0.8, 0]}>
        <cylinderGeometry args={[0.08, 0.1, 1.6, 8]} />
        <meshStandardMaterial color="#3f3f46" roughness={0.9} />
      </mesh>
      <mesh castShadow position={[0, 1.8, 0]}>
        <coneGeometry args={[0.5, 1.2, 8]} />
        <meshStandardMaterial color="#1a3a2e" roughness={0.8} />
      </mesh>
    </group>
  )
}

function Terrain() {
  const geometry = useMemo(() => {
    const geo = new THREE.PlaneGeometry(50, 50, 50, 50)
    const positions = geo.attributes.position
    for (let i = 0; i < positions.count; i++) {
      const x = positions.getX(i)
      const y = positions.getY(i)
      const dist = Math.sqrt(x * x + y * y)
      // Gentle terrain undulation, flattened near center
      const height = Math.sin(x * 0.3) * Math.cos(y * 0.3) * 0.3 * Math.min(1, dist / 5)
      positions.setZ(i, height)
    }
    geo.computeVertexNormals()
    return geo
  }, [])

  return (
    <mesh geometry={geometry} rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
      <meshStandardMaterial color="#2a3a2a" roughness={1} metalness={0} vertexColors={false} />
    </mesh>
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
      <pointsMaterial size={0.03} color="#c4a882" transparent opacity={0.25} sizeAttenuation />
    </points>
  )
}

function Victims({ sounds }: { sounds: SoundSource[] }) {
  const victims = sounds.filter((s) => s.kind === 'distress' || s.kind === 'voice' || s.kind === 'speech')

  return (
    <>
      {victims.map((v, i) => (
        <group key={i}>
          <Person position={[v.x, 0, -v.y]} waving={v.kind === 'distress'} />
        </group>
      ))}
    </>
  )
}

export function DrivingView3D({ payload }: { payload: MapPayload | null }) {
  const roverPose = payload?.rover_pose ?? [0, 0, 0]
  const soundSources = payload?.sound_sources ?? []

  return (
    <div className="relative w-full" style={{ aspectRatio: '16 / 10' }}>
      <Canvas
        shadows
        camera={{ position: [3, 2.5, 4], fov: 65 }}
        gl={{ antialias: true, alpha: false }}
      >
        <color attach="background" args={['#1a1a2e']} />
        <fog attach="fog" args={['#1a1a2e', 10, 30]} />

        {/* Dusk lighting — warm sky */}
        <ambientLight intensity={0.35} color="#fbbf24" />
        <directionalLight
          position={[8, 15, 8]}
          intensity={0.6}
          color="#f59e0b"
          castShadow
          shadow-mapSize={[2048, 2048]}
          shadow-camera-far={30}
          shadow-camera-left={-15}
          shadow-camera-right={15}
          shadow-camera-top={15}
          shadow-camera-bottom={-15}
        />
        <hemisphereLight args={['#fbbf24', '#2a3a2a', 0.3]} />
        <Environment preset="sunset" />

        {/* Terrain with height variation */}
        <Terrain />

        {/* Buildings — some damaged */}
        <Building position={[4, 1.5, -3]} size={[2, 3, 2]} color="#475569" damaged />
        <Building position={[-3, 1.2, -5]} size={[1.5, 2.4, 1.5]} color="#525b6a" />
        <Building position={[6, 2, 2]} size={[2.5, 4, 2.5]} color="#3f4756" damaged />
        <Building position={[-5, 1, 3]} size={[1.8, 2, 1.8]} color="#4b5563" />
        <Building position={[2, 1.8, -7]} size={[2, 3.6, 2]} color="#3b4252" damaged />
        <Building position={[-6, 0.8, -1]} size={[1.2, 1.6, 1.2]} color="#525b6a" />

        {/* Broken walls */}
        <Building position={[0, 0.6, 5]} size={[4, 1.2, 0.2]} color="#475569" />
        <Building position={[-7, 0.5, -3]} size={[0.2, 1, 4]} color="#475569" />

        {/* Rubble piles */}
        <RubblePile position={[1, 0, 2]} />
        <RubblePile position={[-2, 0, -3]} scale={1.3} />
        <RubblePile position={[5, 0, -1]} />
        <RubblePile position={[-4, 0, 4]} scale={0.8} />

        {/* Trees for environment */}
        <Tree position={[-8, 0, 6]} />
        <Tree position={[8, 0, -5]} />
        <Tree position={[-2, 0, 7]} />

        {/* Victims from sound sources */}
        <Victims sounds={soundSources} />

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
      <div className="absolute left-3 top-3 rounded bg-black/50 px-2 py-1 text-[11px] font-semibold tracking-wider text-amber-400 uppercase backdrop-blur-sm">
        Rescue Rover — Live View
      </div>
    </div>
  )
}
