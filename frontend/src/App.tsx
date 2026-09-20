import { useState } from 'react'
import { Header } from './components/Header'
import { Navigation } from './components/Navigation'
import { useTelemetry } from './hooks/useTelemetry'
import { Brain } from './pages/Brain'
import { Dashboard } from './pages/Dashboard'
import { Encounters } from './pages/Encounters'
import { Telemetry } from './pages/Telemetry'
import type { Tab } from './types'

function App() {
  const [tab, setTab] = useState<Tab>('dashboard')
  const { snapshot, live } = useTelemetry()
  const battery = snapshot?.rover.sources.battery_percent
  const rover = { id: 'ROVER-01', cameraName: 'FRONT-CAM', connected: live && !!snapshot?.rover.connected,
    battery: live && battery?.status === 'live' && typeof battery.value === 'number' ? battery.value : null }

  return (
    <div className="min-h-screen bg-base">
      <Header rover={rover} />
      <Navigation active={tab} onChange={setTab} />
      <main className="mx-auto max-w-[1600px] px-6 py-8 lg:px-10">
        {tab === 'dashboard' && <Dashboard snapshot={snapshot} live={live} />}
        {tab === 'telemetry' && <Telemetry snapshot={snapshot} live={live} />}
        {tab === 'brain' && <Brain mission={snapshot?.mission ?? null} live={live} />}
        {tab === 'encounters' && <Encounters />}
      </main>
    </div>
  )
}

export default App
