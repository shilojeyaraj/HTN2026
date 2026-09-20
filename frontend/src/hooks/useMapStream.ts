import { useEffect, useRef, useState } from 'react'
import type { MapPayload } from '../types'

const DEFAULT_URL = `ws://${window.location.hostname}:8766`

export function useMapStream(url: string = DEFAULT_URL) {
  const [payload, setPayload] = useState<MapPayload | null>(null)
  const [connected, setConnected] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    let retry: number
    let closed = false

    const connect = () => {
      const ws = new WebSocket(url)
      wsRef.current = ws

      ws.onopen = () => setConnected(true)
      ws.onclose = () => {
        setConnected(false)
        if (!closed) retry = window.setTimeout(connect, 2000)
      }
      ws.onerror = () => ws.close()
      ws.onmessage = (e) => {
        try {
          setPayload(JSON.parse(e.data) as MapPayload)
        } catch {
          /* skip malformed */
        }
      }
    }

    connect()
    return () => {
      closed = true
      window.clearTimeout(retry)
      wsRef.current?.close()
    }
  }, [url])

  return { payload, connected }
}
