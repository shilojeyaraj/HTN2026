import { useState } from 'react'
import { Header } from './components/Header'
import { Navigation } from './components/Navigation'
import { rover } from './data/mockData'
import { Dashboard } from './pages/Dashboard'
import { Encounters } from './pages/Encounters'
import type { Tab } from './types'

function App() {
  const [tab, setTab] = useState<Tab>('dashboard')

  return (
    <div className="min-h-screen bg-base">
      <Header rover={rover} />
      <Navigation active={tab} onChange={setTab} />
      <main className="mx-auto max-w-[1600px] px-6 py-8 lg:px-10">
        {tab === 'dashboard' ? <Dashboard /> : <Encounters />}
      </main>
    </div>
  )
}

export default App
