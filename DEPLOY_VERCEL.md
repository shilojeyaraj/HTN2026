# Deploy to Vercel + ngrok tunnel

This lets judges access the rescue rover dashboard from a public URL instead of localhost.

## Setup

### 1. Install Vercel CLI
```bash
npm i -g vercel
vercel login
```

### 2. Install ngrok (to expose the brain server)
```bash
npm i -g ngrok
# Sign up at ngrok.com (free), get your authtoken:
ngrok config add-authtoken YOUR_TOKEN
```

### 3. Start the brain server locally
```bash
cd ~/VScode/htn2026/HTN2026
source .venv/bin/activate
python frontend/virtual_brain_server.py
```
Wait for "Brain initialized — RAG uploaded, encounters loaded"

### 4. Start ngrok tunnel to expose port 8766
```bash
ngrok http 8766
```
Copy the forwarding URL (e.g., `https://abc123.ngrok.io`)

### 5. Deploy frontend to Vercel with the ngrok WebSocket URL
```bash
cd frontend
# Set the WebSocket URL to your ngrok forwarding URL
vercel env add VITE_WS_URL
# Enter: wss://abc123.ngrok.io  (use wss:// for ngrok HTTPS)

# Deploy
vercel --prod
```

### 6. Open the Vercel URL
Vercel gives you a URL like `https://rescue-rover.vercel.app`.
Open it in the browser — the dashboard connects to your brain server via ngrok.

## How it works

```
Browser (Vercel) → wss://ngrok.io → ngrok tunnel → localhost:8766 → brain server
                                                              ↓
                                                     Backboard (Gemini)
                                                     ElevenLabs TTS
                                                     MongoDB
```

## Notes

- The brain server must stay running on your laptop during the demo
- ngrok free tier has a random URL that changes on restart — use a paid plan for a fixed URL
- The Vercel frontend is static — it just needs the WebSocket URL to connect to the brain
- If the brain server restarts, the frontend auto-reconnects (2s retry)

## Alternative: Run everything locally

If you don't want to use Vercel:
```bash
# Terminal 1: brain server
python frontend/virtual_brain_server.py

# Terminal 2: frontend
cd frontend && npm run dev
# Open http://localhost:5173
```
