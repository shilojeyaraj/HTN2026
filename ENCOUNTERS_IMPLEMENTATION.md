# MongoDB Encounter Schema - Implementation Summary

## What Was Built

A complete MongoDB-based encounter tracking system for rescue mission cases with:

### 1. Core Schema ✓
- **`encounters` collection** with 6 indexes for efficient queries
- **`encounter_patterns` collection** for cached analytics
- Extended existing collections (`transcripts`, `findings`, `brain_activity`) with `encounter_id` fields

### 2. CRUD API (`tracking/encounters.py`) ✓
**16 functions covering:**
- Create/read/update/complete encounters
- Active encounter management (only one active at a time)
- Embedded transcript management
- Linking findings and brain activity
- Statistics and queries

### 3. Pattern Analytics (`tracking/encounter_patterns.py`) ✓
- Compute rescue success rates
- Duration statistics (avg, median, min, max)
- Automatic insight generation
- Caching for performance

### 4. Migration Script (`tracking/migrate_historical.py`) ✓
- Imports 8 historical encounters from `knowledge/encounter_history.md`
- Creates all indexes
- Populates initial analytics
- **Run with:** `python tracking/migrate_historical.py`

### 5. Integration (`tracking/mongo.py`, `brain/loop.py`) ✓
- Updated logging functions to accept `encounter_id` parameter
- Modified brain loop to:
  - Get active encounter at start of each episode
  - Link all transcripts, findings, and brain activity
  - Add messages to embedded transcript array
- Backward compatible (encounter_id is optional)

### 6. Demo & Documentation ✓
- `tracking/demo_encounters.py` — interactive demo script
- `tracking/README_ENCOUNTERS.md` — complete API documentation with examples

## Schema Overview

```javascript
// encounters collection
{
  encounter_id: "ENC-2026-0148",        // auto-generated
  status: "rescued" | "located" | "no-contact",
  started_at: ISODate,
  completed_at: ISODate | null,
  duration_seconds: number | null,
  survivor_count: number | null,
  notes: string | null,
  is_active: boolean,                   // only one true at a time
  transcript: [                         // embedded for frontend
    {
      id: string,
      speaker: "person" | "driver" | "rover",
      text: string,
      timestamp: ISODate,
      message_index: number
    }
  ],
  finding_ids: [ObjectId],              // references
  brain_activity_ids: [ObjectId],       // references
  created_at: ISODate,
  updated_at: ISODate
}
```

**Indexes:** `encounter_id` (unique), `is_active`, `started_at`, `status`, compound `{started_at: -1, status: 1}`

## Quick Start

### 1. Set MongoDB URI
```bash
# Add to .env
MONGODB_URI=mongodb://localhost:27017/
```

### 2. Import Historical Data
```bash
python tracking/migrate_historical.py
```

### 3. Try the Demo
```bash
python tracking/demo_encounters.py
```

## Usage Examples

### Create and Complete an Encounter
```python
from tracking import encounters

# Create
enc_id = encounters.create_encounter(status="located")

# Add transcript
encounters.add_transcript_message(enc_id, "person", "Can anyone hear me?")
encounters.add_transcript_message(enc_id, "driver", "Yes, we hear you.")

# Complete
encounters.complete_encounter(enc_id, status="rescued", survivor_count=1)
```

### Query Encounters
```python
# Get active
active = encounters.get_active_encounter()

# List all
all_enc = encounters.list_encounters(limit=20)

# Filter by status
rescued = encounters.list_encounters(status="rescued")

# Get specific
enc = encounters.get_encounter("ENC-2026-0147")
```

### Analytics
```python
from tracking import encounter_patterns

patterns = encounter_patterns.get_patterns()
print(f"Total: {patterns['total_encounters']}")
print(f"Rescue rate: {patterns['by_status']['rescued'] / patterns['total_encounters'] * 100:.0f}%")
print(f"Avg duration: {patterns['duration_stats']['avg_minutes']:.1f} min")

for insight in patterns['insights']:
    print(f"  • {insight['value']}")
```

## Integration Points

### Automatic (No Code Changes Needed)
The brain loop automatically links all activity to the active encounter:
- ✓ Transcripts → `encounter_id` + embedded in `transcript` array
- ✓ Findings → `encounter_id` + reference in `finding_ids`
- ✓ Brain activity → `encounter_id` + reference in `brain_activity_ids`

### Manual Control
Create/complete encounters when appropriate:
```python
# Start new encounter when distress signal detected
from tracking import encounters
enc_id = encounters.create_encounter(status="located")

# Complete when rescue team arrives
encounters.complete_encounter(
    enc_id, 
    status="rescued",
    survivor_count=2,
    notes="Both survivors extracted via north stairwell"
)
```

## Files Created/Modified

### New Files (5)
- `tracking/encounters.py` (465 lines) — Core CRUD API
- `tracking/encounter_patterns.py` (159 lines) — Analytics engine
- `tracking/migrate_historical.py` (240 lines) — Migration script
- `tracking/demo_encounters.py` (154 lines) — Demo/test script
- `tracking/README_ENCOUNTERS.md` — Full documentation

### Modified Files (2)
- `tracking/mongo.py` — Added `encounter_id` parameter to logging functions
- `brain/loop.py` — Integrated encounter tracking into episode loop

## What's Not Included (Per Your Request)

- ❌ Location fields (GPS integration pending)
- ❌ Mission context (pose snapshots)
- ❌ Location-based analytics (sector/location_type queries)

These can be easily added later by extending the schema.

## Testing

1. **Import historical data:**
   ```bash
   python tracking/migrate_historical.py
   ```

2. **Run demo:**
   ```bash
   python tracking/demo_encounters.py
   ```

3. **Check MongoDB:**
   ```bash
   python tracking/query.py --stats
   ```

## Next Steps

1. **Import historical encounters** to populate the database
2. **Test the API** with the demo script
3. **Integrate with frontend** using the format examples in README
4. **Add encounter creation logic** for when distress signals are detected
5. **Extend schema** with GPS fields when ready

## Notes

- All MongoDB operations gracefully degrade if DB is unavailable
- Backward compatible — existing code continues to work
- Thread-safe for concurrent access
- Indexes created automatically on first connection
- Works with both MongoDB local and Atlas

---

**All TODOs completed!** The schema and scripts are ready to use.
