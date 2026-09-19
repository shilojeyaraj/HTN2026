import type { ActiveEncounter, Encounter, EncounterStatus, Rover } from '../types'

export const rover: Rover = {
  id: 'ROVER-01',
  connected: true,
  battery: 78,
  cameraName: 'FRONT-CAM',
}

export const statusLabels: Record<EncounterStatus, string> = {
  rescued: 'RESCUED',
  located: 'LOCATED',
  'no-contact': 'NO CONTACT',
}

export const activeEncounter: ActiveEncounter = {
  id: 'ENC-2026-0148',
  status: 'located',
  location: 'Sector 7-B // Riverside Apartments, Block C',
  timestamp: 'Sep 19, 2026 04:12',
  duration: '00:18:42',
  startedAt: '04:12:06',
  transcript: [
    {
      id: 'm-01',
      speaker: 'person',
      text: 'Can anyone hear me?',
      timestamp: '04:12:09',
    },
    {
      id: 'm-02',
      speaker: 'driver',
      text: "Yes, we can hear you. We're here to help.",
      timestamp: '04:12:14',
    },
    {
      id: 'm-03',
      speaker: 'person',
      text: "I'm trapped underneath the building.",
      timestamp: '04:12:22',
    },
    {
      id: 'm-04',
      speaker: 'rover',
      text: 'We have located you. Please stay where you are.',
      timestamp: '04:12:27',
    },
    {
      id: 'm-05',
      speaker: 'driver',
      text: 'Can you tell me your name and whether anyone is with you?',
      timestamp: '04:13:02',
    },
    {
      id: 'm-06',
      speaker: 'person',
      text: "Maya. There's one more person near me, I think she's unconscious.",
      timestamp: '04:13:19',
    },
    {
      id: 'm-07',
      speaker: 'rover',
      text: 'Two heat signatures confirmed, approximately 4 meters ahead.',
      timestamp: '04:13:24',
    },
    {
      id: 'm-08',
      speaker: 'driver',
      text: 'Understood, Maya. Are you able to move your arms and legs?',
      timestamp: '04:13:41',
    },
    {
      id: 'm-09',
      speaker: 'person',
      text: "My left leg is pinned. There's water coming in from somewhere.",
      timestamp: '04:14:03',
    },
    {
      id: 'm-10',
      speaker: 'driver',
      text: 'Copy that. A rescue team is nine minutes out. Keep talking to me.',
      timestamp: '04:14:15',
    },
    {
      id: 'm-11',
      speaker: 'rover',
      text: 'Structural shift detected overhead. Holding position.',
      timestamp: '04:14:38',
    },
    {
      id: 'm-12',
      speaker: 'person',
      text: 'Okay. Please hurry.',
      timestamp: '04:14:52',
    },
  ],
}

export const encounters: Encounter[] = [
  {
    id: 'ENC-2026-0147',
    status: 'rescued',
    location: 'Sector 7-A // Riverside Apartments, Block A',
    timestamp: 'Sep 19, 2026 02:47',
    duration: '00:42:11',
    transcript: [
      {
        id: 'e147-01',
        speaker: 'rover',
        text: 'Voice detected in collapsed stairwell.',
        timestamp: '02:47:03',
      },
      {
        id: 'e147-02',
        speaker: 'driver',
        text: 'This is search and rescue. If you can hear me, respond.',
        timestamp: '02:47:11',
      },
      {
        id: 'e147-03',
        speaker: 'person',
        text: "I'm here. Second floor, by the stairs.",
        timestamp: '02:47:29',
      },
      {
        id: 'e147-04',
        speaker: 'driver',
        text: 'We have your position. Team is entering now.',
        timestamp: '02:48:02',
      },
      {
        id: 'e147-05',
        speaker: 'person',
        text: 'I can see the lights. Thank you.',
        timestamp: '03:26:44',
      },
      {
        id: 'e147-06',
        speaker: 'rover',
        text: 'Subject extracted. Handing off to medical.',
        timestamp: '03:29:14',
      },
    ],
  },
  {
    id: 'ENC-2026-0146',
    status: 'located',
    location: 'Sector 4-C // Harbor Warehouse 12',
    timestamp: 'Sep 19, 2026 01:33',
    duration: '00:26:55',
    transcript: [
      {
        id: 'e146-01',
        speaker: 'rover',
        text: 'Thermal contact behind fallen shelving.',
        timestamp: '01:33:08',
      },
      {
        id: 'e146-02',
        speaker: 'driver',
        text: 'Can you hear me? Tap twice if you can.',
        timestamp: '01:33:20',
      },
      {
        id: 'e146-03',
        speaker: 'person',
        text: "I hear you. I can't move much.",
        timestamp: '01:34:02',
      },
      {
        id: 'e146-04',
        speaker: 'driver',
        text: 'Stay still. Marking your location for the extraction team.',
        timestamp: '01:34:18',
      },
    ],
  },
  {
    id: 'ENC-2026-0145',
    status: 'no-contact',
    location: 'Sector 2-D // Old Mill Road, Residential',
    timestamp: 'Sep 19, 2026 00:58',
    duration: '00:11:07',
    transcript: [
      {
        id: 'e145-01',
        speaker: 'rover',
        text: 'Entering structure. Air quality degraded.',
        timestamp: '00:58:12',
      },
      {
        id: 'e145-02',
        speaker: 'driver',
        text: 'Anyone inside, call out if you can hear me.',
        timestamp: '00:59:40',
      },
      {
        id: 'e145-03',
        speaker: 'rover',
        text: 'No response detected after three sweeps.',
        timestamp: '01:07:51',
      },
      {
        id: 'e145-04',
        speaker: 'driver',
        text: 'Marking sector for secondary search. Withdrawing.',
        timestamp: '01:09:19',
      },
    ],
  },
  {
    id: 'ENC-2026-0144',
    status: 'rescued',
    location: 'Sector 9-F // Northgate Transit Tunnel',
    timestamp: 'Sep 18, 2026 23:41',
    duration: '01:04:38',
    transcript: [
      {
        id: 'e144-01',
        speaker: 'person',
        text: 'Hello? Is someone there?',
        timestamp: '23:41:15',
      },
      {
        id: 'e144-02',
        speaker: 'driver',
        text: 'We hear you. How many people are with you?',
        timestamp: '23:41:28',
      },
      {
        id: 'e144-03',
        speaker: 'person',
        text: 'Four of us. We moved away from the water.',
        timestamp: '23:41:52',
      },
      {
        id: 'e144-04',
        speaker: 'rover',
        text: 'Four signatures confirmed on the east platform.',
        timestamp: '23:42:07',
      },
      {
        id: 'e144-05',
        speaker: 'driver',
        text: 'Good. Keep everyone together and keep talking to us.',
        timestamp: '23:42:33',
      },
      {
        id: 'e144-06',
        speaker: 'rover',
        text: 'All four subjects extracted. Sector clear.',
        timestamp: '00:45:53',
      },
    ],
  },
  {
    id: 'ENC-2026-0143',
    status: 'located',
    location: 'Sector 5-B // Grainview School, Gymnasium',
    timestamp: 'Sep 18, 2026 22:19',
    duration: '00:33:24',
    transcript: [
      {
        id: 'e143-01',
        speaker: 'rover',
        text: 'Partial roof collapse. Void space detected beneath bleachers.',
        timestamp: '22:19:44',
      },
      {
        id: 'e143-02',
        speaker: 'person',
        text: "We're under here. Please don't move the beams.",
        timestamp: '22:21:02',
      },
      {
        id: 'e143-03',
        speaker: 'driver',
        text: 'Nobody is touching anything. Engineers are on the way.',
        timestamp: '22:21:20',
      },
    ],
  },
  {
    id: 'ENC-2026-0142',
    status: 'rescued',
    location: 'Sector 1-A // Civic Center Parking Deck',
    timestamp: 'Sep 18, 2026 20:55',
    duration: '00:51:09',
    transcript: [
      {
        id: 'e142-01',
        speaker: 'driver',
        text: 'Rover is on level three. Call out if you can hear the engine.',
        timestamp: '20:55:31',
      },
      {
        id: 'e142-02',
        speaker: 'person',
        text: 'I hear it. My car is crushed against the wall.',
        timestamp: '20:56:48',
      },
      {
        id: 'e142-03',
        speaker: 'rover',
        text: 'Visual confirmed. Subject responsive.',
        timestamp: '20:57:03',
      },
      {
        id: 'e142-04',
        speaker: 'person',
        text: 'I can wait. Just tell me someone is coming.',
        timestamp: '20:58:11',
      },
      {
        id: 'e142-05',
        speaker: 'driver',
        text: 'Someone is coming. We are not leaving.',
        timestamp: '20:58:19',
      },
    ],
  },
  {
    id: 'ENC-2026-0141',
    status: 'no-contact',
    location: 'Sector 3-E // Lakeside Trailer Park',
    timestamp: 'Sep 18, 2026 19:30',
    duration: '00:08:52',
    transcript: [
      {
        id: 'e141-01',
        speaker: 'rover',
        text: 'Debris field impassable beyond 12 meters.',
        timestamp: '19:30:41',
      },
      {
        id: 'e141-02',
        speaker: 'driver',
        text: 'Search and rescue. Respond if you hear this.',
        timestamp: '19:33:10',
      },
      {
        id: 'e141-03',
        speaker: 'rover',
        text: 'No contact. Recommending aerial survey.',
        timestamp: '19:38:27',
      },
    ],
  },
  {
    id: 'ENC-2026-0140',
    status: 'rescued',
    location: 'Sector 6-C // Fairmount Hospital, East Wing',
    timestamp: 'Sep 18, 2026 17:02',
    duration: '01:22:47',
    transcript: [
      {
        id: 'e140-01',
        speaker: 'person',
        text: "There are patients in here who can't walk.",
        timestamp: '17:02:55',
      },
      {
        id: 'e140-02',
        speaker: 'driver',
        text: 'Understood. How many, and what floor?',
        timestamp: '17:03:09',
      },
      {
        id: 'e140-03',
        speaker: 'person',
        text: 'Six, on the third floor. The elevators are gone.',
        timestamp: '17:03:31',
      },
      {
        id: 'e140-04',
        speaker: 'rover',
        text: 'Stairwell B is structurally sound. Routing team.',
        timestamp: '17:04:02',
      },
      {
        id: 'e140-05',
        speaker: 'rover',
        text: 'All seven subjects evacuated. Wing clear.',
        timestamp: '18:25:42',
      },
    ],
  },
]
