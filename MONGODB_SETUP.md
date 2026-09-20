# MongoDB Setup Instructions

## What this does

The rover logs everything to MongoDB for real-time mission tracking and post-mission analysis:
- **transcripts** — every STT transcript with timestamp + rover pose
- **brain_activity** — every brain tool call with args + result + pose
- **findings** — every mission finding (survivors, hazards, explored areas) with pose
- **sensor_readings** — temperature + audio + gyro with pose
- **rag_logs** — every RAG knowledge retrieval with query + results + pose
- **insights** — every pattern analysis result

## Setup

### 1. Install dependencies
```bash
pip install pymongo python-dotenv
```

### 2. Add MongoDB credentials to .env
```bash
# Add these to your .env file:
MONGODB_URI=mongodb+srv://nickdodotron_db_user:zAQoNibqJLSfiJQ8@cluster0.d0anmu9.mongodb.net/?appName=Cluster0
MONGODB_USER=nickdodotron_db_user
MONGODB_PASSWORD=zAQoNibqJLSfiJQ8
```

### 3. Whitelist your IP in MongoDB Atlas
1. Go to https://cloud.mongodb.com
2. Select your cluster (Cluster0)
3. Left sidebar → **Network Access**
4. Click **Add IP Address**
5. Click **Add Current IP Address** (or `0.0.0.0/0` to allow all IPs for the hackathon)
6. Click Confirm
7. Wait 1-2 minutes

### 4. Test the connection
```bash
python tracking/query.py --stats
```

You should see:
```
MISSION TRACKING STATS
  connected: True
  transcripts: 0
  brain_activity: 0
  findings: 0
  sensor_readings: 0
  rag_logs: 0
  insights: 0
```

### 5. Run the rover
```bash
python main.py
```

As the rover runs, everything is automatically logged to MongoDB. No extra code needed — the brain loop already calls the tracking functions.

## Querying records

```bash
# Show everything (5 recent from each collection)
python tracking/query.py

# Show stats only
python tracking/query.py --stats

# Show 20 recent transcripts
python tracking/query.py --collection transcripts --limit 20

# Show recent brain activity
python tracking/query.py --collection brain_activity

# Show recent findings
python tracking/query.py --collection findings
```

## How it works

The tracking module (`tracking/mongo.py`) hooks into `brain/loop.py`:
- Every tool call → `db.log_brain_call()`
- Every transcript → `db.log_transcript()`
- Every finding → `db.log_finding()`
- Every sensor read → `db.log_sensor_reading()`
- Every RAG search → `db.log_rag()`
- Every pattern analysis → `db.log_insights()`

If MongoDB is unavailable, all log methods silently no-op — the rover keeps running without crashing.

## Files

| File | Role |
|---|---|
| `tracking/mongo.py` | MongoDB connection + log/query methods |
| `tracking/query.py` | CLI to query stored records and show stats |
| `brain/loop.py` | Calls tracking functions alongside telemetry |
| `.env` | `MONGODB_URI` (gitignored — never committed) |
