export type Speaker = 'person' | 'driver' | 'rover'

export type EncounterStatus = 'rescued' | 'located' | 'no-contact'

export interface TranscriptMessage {
  id: string
  speaker: Speaker
  text: string
  timestamp: string
}

export interface Encounter {
  id: string
  status: EncounterStatus
  location: string
  timestamp: string
  duration: string
  transcript: TranscriptMessage[]
}

export interface ActiveEncounter extends Encounter {
  startedAt: string
}

export interface Rover {
  id: string
  connected: boolean
  battery: number
  cameraName: string
}

export type Tab = 'dashboard' | 'encounters'
