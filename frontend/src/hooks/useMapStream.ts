import { useEffect, useRef, useState } from 'react'
import type { MapPayload } from '../types'

const DEFAULT_URL = import.meta.env.VITE_TELEMETRY_URL || `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.hostname}:8766`
const identity = <T,>(value: unknown) => value as T

export function useMapStream<T = MapPayload>(url: string = DEFAULT_URL, decode: (value: unknown) => T = identity) {
  const [payload, setPayload] = useState<T | null>(null)
  const [connected, setConnected] = useState(false)
  const [fresh, setFresh] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    let retry: number
    let stale: number
    let closed = false

    const connect = () => {
      const ws = new WebSocket(url)
      wsRef.current = ws

      ws.onopen = () => {
        if (closed) ws.close()
        else setConnected(true)
      }
      ws.onclose = () => {
        if (closed) return
        setConnected(false)
        setFresh(false)
        window.clearTimeout(stale)
        if (!closed) retry = window.setTimeout(connect, 2000)
      }
      ws.onerror = () => ws.close()
      ws.onmessage = (e) => {
        if (closed) return
        try {
          const next = decode(JSON.parse(e.data))
          setPayload(next)
          setFresh(true)
          window.clearTimeout(stale)
          stale = window.setTimeout(() => setFresh(false), 2500)
        } catch {
          /* skip malformed */
        }
      }
    }

    connect()
    return () => {
      closed = true
      window.clearTimeout(retry)
      window.clearTimeout(stale)
      // A pending connection closes on open; closing it early causes a browser warning.
      if (wsRef.current?.readyState !== WebSocket.CONNECTING) wsRef.current?.close()
    }
  }, [url, decode])

  return { payload, connected, fresh }
}
