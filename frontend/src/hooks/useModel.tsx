import { useGLTF } from '@react-three/drei'
import { useMemo } from 'react'
import * as THREE from 'three'

/**
 * Load a GLTF/GLB model from the public/models directory.
 * Returns the scene ready to render, or null if the file doesn't exist.
 *
 * Usage:
 *   const model = useModel('/models/building.glb')
 *   if (model) return <primitive object={model} position={[x, y, z]} />
 *
 * Drop downloaded Quaternius GLB files into frontend/public/models/
 * and reference them by filename here.
 */

export function useModel(path: string): THREE.Group | null {
  try {
    const gltf = useGLTF(path)
    return gltf.scene
  } catch {
    return null
  }
}

/**
 * Render multiple instances of a loaded model at given positions.
 * Usage:
 *   <ModelInstances path="/models/building.glb" positions={[[0,0,0], [3,0,0]]} />
 */
export function ModelInstances({
  path,
  positions,
  scale = 1,
  rotation = [0, 0, 0],
}: {
  path: string
  positions: [number, number, number][]
  scale?: number
  rotation?: [number, number, number]
}) {
  const scene = useModel(path)

  const instances = useMemo(() => {
    if (!scene) return []
    return positions.map((pos) => {
      const clone = scene.clone(true)
      clone.position.set(pos[0], pos[1], pos[2])
      clone.rotation.set(rotation[0], rotation[1], rotation[2])
      clone.scale.setScalar(scale)
      return clone
    })
  }, [scene, positions, scale, rotation])

  if (!scene) return null

  return (
    <>
      {instances.map((obj, i) => (
        <primitive key={i} object={obj} />
      ))}
    </>
  )
}
