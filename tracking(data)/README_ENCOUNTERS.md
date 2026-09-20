# Encounters Tracking System

MongoDB-based encounter case management for rescue missions. Each encounter represents a complete rescue case with embedded transcripts, status tracking, and links to findings and brain activity.

## Setup

### 1. Install MongoDB

The system requires a MongoDB instance. Set the connection URI in `.env`:

```bash
MONGODB_URI=mongodb://localhost:27017/
# or for MongoDB Atlas:
# MONGODB_URI=mongodb+srv://user:pass@cluster.mongodb.net/
```

### 2. Import Historical Data

Import the 8 historical encounters from `knowledge/encounter_history.md`:

```bash
python tracking/migrate_historical.py
```

This will:
- Create all necessary indexes
- Import 8 past encounters with full transcripts
- Compute initial pattern analytics

## Schema

### Collections

#### `encounters` (primary)
```javascript
{
  encounter_id: "ENC-2026-0148",     // unique ID
  status: "rescued",                 // "rescued" | "located" | "no-contact"
  started_at: ISODate,
  completed_at: ISODate | null,
  duration_seconds: 1234 | null,
  survivor_count: 2 | null,
  notes: "Additional notes...",
  is_active: false,                  // only one can be true at a time
  transcript: [
    {
      id: "a3f8d2",
      speaker: "person",             // "person" | "driver" | "rover"
      text: "Can anyone hear me?",
      timestamp: ISODate,
      message_index: 0
    }
  ],
  finding_ids: [ObjectId, ...],      // refs to findings collection
  brain_activity_ids: [ObjectId, ...], // refs to brain_activity collection
  created_at: ISODate,
  updated_at: ISODate
}
```

**Indexes:**
- `encounter_id` (unique)
- `is_active`
- `started_at` (descending)
- `status`
- Compound: `{started_at: -1, status: 1}`

#### `encounter_patterns` (analytics cache)
Pre-computed statistics refreshed on-demand:
```javascript
{
  computed_at: ISODate,
  total_encounters: 8,
  by_status: {rescued: 4, located: 2, "no-contact": 2},
  duration_stats: {
    avg_minutes: 45.2,
    median_minutes: 38.5,
    min_minutes: 8.9,
    max_minutes: 82.8,
    longest_encounter_id: "ENC-2026-0140",
    shortest_encounter_id: "ENC-2026-0141"
  },
  insights: [
    {key: "rescue_rate", value: "50% (4 of 8 encounters)"},
    {key: "duration_correlation", value: "Longer encounters correlate with rescue success"}
  ]
}
```

#### Existing collections (extended)
- `transcripts` — added `encounter_id` field
- `findings` — added `encounter_id` field  
- `brain_activity` — added `encounter_id` field

## API

### Core CRUD Operations

```python
from tracking import encounters

# Create new encounter (automatically deactivates previous active encounter)
enc_id = encounters.create_encounter(status="located")
# Returns: "ENC-2026-0149" or None

# Get active encounter
active = encounters.get_active_encounter()
# Returns: encounter dict or None

# Get specific encounter
enc = encounters.get_encounter("ENC-2026-0147")
# Returns: encounter dict or None

# List encounters (recent first)
recent = encounters.list_encounters(limit=20)
rescued = encounters.list_encounters(limit=20, status="rescued")
# Returns: list of encounter dicts

# Update encounter
encounters.update_encounter("ENC-2026-0148", {
    "survivor_count": 2,
    "notes": "Two survivors located in basement"
})

# Complete encounter (sets is_active=False, calculates duration)
encounters.complete_encounter(
    "ENC-2026-0148",
    status="rescued",
    survivor_count=2,
    notes="Both survivors extracted successfully"
)
```

### Transcript Management

```python
# Add message to encounter transcript
encounters.add_transcript_message(
    "ENC-2026-0148",
    speaker="person",
    text="Can anyone hear me?"
)

# Transcript is embedded in the encounter document
enc = encounters.get_encounter("ENC-2026-0148")
for msg in enc['transcript']:
    print(f"[{msg['speaker']}] {msg['text']}")
```

### Linking Related Data

```python
# Link a finding to an encounter
finding_id = db.log_finding("survivor", "Person located at (2.3, 1.1)", encounter_id=enc_id)
if finding_id:
    encounters.link_finding(enc_id, finding_id)

# Link brain activity to an encounter  
activity_id = db.log_brain_call("forward", {"distance_m": 2.0}, result, encounter_id=enc_id)
if activity_id:
    encounters.link_brain_activity(enc_id, activity_id)
```

### Analytics

```python
from tracking import encounter_patterns

# Get statistics
stats = encounters.get_encounter_stats()
print(f"Total: {stats['total']}")
print(f"By status: {stats['by_status']}")
print(f"Active: {stats['active_encounter_id']}")

# Get cached patterns (fast)
patterns = encounter_patterns.get_cached_patterns()

# Compute fresh patterns (runs aggregations)
patterns = encounter_patterns.compute_patterns()

# Get patterns (uses cache if available, computes if not)
patterns = encounter_patterns.get_patterns(force_recompute=False)

# Access pattern data
print(f"Average duration: {patterns['duration_stats']['avg_minutes']:.1f} min")
for insight in patterns['insights']:
    print(f"  {insight['value']}")
```

## Integration with Brain Loop

The brain loop (`brain/loop.py`) automatically:
1. Gets the active encounter at the start of each episode
2. Links all transcripts, findings, and brain activity to the encounter
3. Adds transcript messages to the encounter's embedded transcript array

This happens transparently — the encounter tracking doesn't interfere with the existing workflow.

## Query Examples

### MongoDB Shell

```javascript
// Find all rescued encounters
db.encounters.find({status: "rescued"}).sort({started_at: -1})

// Get active encounter with full transcript
db.encounters.findOne({is_active: true})

// Search transcript content
db.encounters.find({
  "transcript.text": {$regex: "distress", $options: "i"}
})

// Encounters by duration range (20-40 minutes)
db.encounters.find({
  duration_seconds: {$gte: 1200, $lte: 2400}
})

// Count by status
db.encounters.aggregate([
  {$group: {_id: "$status", count: {$sum: 1}}},
  {$sort: {count: -1}}
])

// Average duration by status
db.encounters.aggregate([
  {$match: {duration_seconds: {$ne: null}}},
  {$group: {
    _id: "$status",
    avg_duration_min: {$avg: {$divide: ["$duration_seconds", 60]}},
    count: {$sum: 1}
  }}
])
```

### Python Queries

```python
from tracking.encounters import _get_db

db = _get_db()
if db:
    # Complex aggregation: rescue rate by encounter duration bracket
    pipeline = [
        {"$match": {"duration_seconds": {"$ne": None}}},
        {"$bucket": {
            "groupBy": "$duration_seconds",
            "boundaries": [0, 900, 1800, 3600, 7200],  # 0, 15min, 30min, 1hr, 2hr
            "default": "2hr+",
            "output": {
                "count": {"$sum": 1},
                "rescued": {"$sum": {"$cond": [{"$eq": ["$status", "rescued"]}, 1, 0]}}
            }
        }}
    ]
    results = list(db["encounters"].aggregate(pipeline))
```

## Testing

Run the demo script to test all functionality:

```bash
python tracking/demo_encounters.py
```

Runs through:
- Creating an encounter
- Adding transcript messages
- Completing the encounter
- Listing and filtering encounters
- Computing patterns and insights

## Frontend Integration

The frontend expects the `Encounter` interface (see `frontend/src/types/index.ts`):

```typescript
interface Encounter {
  id: string              // encounter_id
  status: EncounterStatus // "rescued" | "located" | "no-contact"
  location: string        // may be empty if GPS not available
  timestamp: string       // started_at formatted
  duration: string        // "HH:MM:SS" formatted
  transcript: TranscriptMessage[]
}
```

To serve encounters to the frontend, convert the MongoDB documents:

```python
def format_for_frontend(enc: dict) -> dict:
    duration_str = "00:00:00"
    if enc.get("duration_seconds"):
        m, s = divmod(int(enc["duration_seconds"]), 60)
        h, m = divmod(m, 60)
        duration_str = f"{h:02d}:{m:02d}:{s:02d}"
    
    return {
        "id": enc["encounter_id"],
        "status": enc["status"],
        "location": enc.get("notes", ""),  # or derive from GPS when available
        "timestamp": enc["started_at"].strftime("%b %d, %Y %H:%M"),
        "duration": duration_str,
        "transcript": [
            {
                "id": msg["id"],
                "speaker": msg["speaker"],
                "text": msg["text"],
                "timestamp": msg["timestamp"].strftime("%H:%M:%S")
            }
            for msg in enc.get("transcript", [])
        ]
    }
```

## Maintenance

### Recompute patterns
```bash
python -c "from tracking.encounter_patterns import compute_patterns; compute_patterns()"
```

### Check stats
```bash
python tracking/query.py --stats
```

### Backup
```bash
mongodump --uri="$MONGODB_URI" --db=htn2026_rescue --collection=encounters
```

## Graceful Degradation

If MongoDB is unavailable:
- All operations return `None` or empty lists
- The rover continues to operate normally
- Logging is suppressed (except initial connection warning)
- When MongoDB comes back online, new data flows in automatically
