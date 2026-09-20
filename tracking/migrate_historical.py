"""Import historical encounters from knowledge/encounter_history.md into MongoDB.

Run this script once to populate the encounters collection with the 8 historical
encounters used for RAG and pattern learning.
"""

import os
import sys
from datetime import datetime, timezone

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from tracking import encounters


# Historical encounters from knowledge/encounter_history.md
HISTORICAL_ENCOUNTERS = [
    {
        "encounter_id": "ENC-2026-0147",
        "status": "rescued",
        "started_at": datetime(2026, 9, 19, 2, 47, tzinfo=timezone.utc),
        "duration_seconds": 42 * 60 + 11,  # 42 minutes 11 seconds
        "survivor_count": 1,
        "notes": "Riverside Apartments, Block A. Survivor found in upper floor unit. Approach required navigating stairwell debris.",
        "transcript": [
            {"speaker": "rover", "text": "Voice detected in collapsed stairwell.", "timestamp": datetime(2026, 9, 19, 2, 47, 3, tzinfo=timezone.utc)},
            {"speaker": "driver", "text": "This is search and rescue. If you can hear me, respond.", "timestamp": datetime(2026, 9, 19, 2, 47, 11, tzinfo=timezone.utc)},
            {"speaker": "person", "text": "I'm here. Second floor, by the stairs.", "timestamp": datetime(2026, 9, 19, 2, 47, 29, tzinfo=timezone.utc)},
            {"speaker": "driver", "text": "We have your position. Team is entering now.", "timestamp": datetime(2026, 9, 19, 2, 48, 2, tzinfo=timezone.utc)},
            {"speaker": "person", "text": "I can see the lights. Thank you.", "timestamp": datetime(2026, 9, 19, 3, 26, 44, tzinfo=timezone.utc)},
            {"speaker": "rover", "text": "Subject extracted. Handing off to medical.", "timestamp": datetime(2026, 9, 19, 3, 29, 14, tzinfo=timezone.utc)},
        ]
    },
    {
        "encounter_id": "ENC-2026-0146",
        "status": "located",
        "started_at": datetime(2026, 9, 19, 1, 33, tzinfo=timezone.utc),
        "duration_seconds": 26 * 60 + 55,
        "survivor_count": 1,
        "notes": "Harbor Warehouse 12. Survivor trapped under shelving unit. Extraction required additional equipment.",
        "transcript": [
            {"speaker": "rover", "text": "Thermal contact behind fallen shelving.", "timestamp": datetime(2026, 9, 19, 1, 33, 8, tzinfo=timezone.utc)},
            {"speaker": "driver", "text": "Can you hear me? Tap twice if you can.", "timestamp": datetime(2026, 9, 19, 1, 33, 20, tzinfo=timezone.utc)},
            {"speaker": "person", "text": "I hear you. I can't move much.", "timestamp": datetime(2026, 9, 19, 1, 34, 2, tzinfo=timezone.utc)},
            {"speaker": "driver", "text": "Stay still. Marking your location for the extraction team.", "timestamp": datetime(2026, 9, 19, 1, 34, 18, tzinfo=timezone.utc)},
        ]
    },
    {
        "encounter_id": "ENC-2026-0145",
        "status": "no-contact",
        "started_at": datetime(2026, 9, 19, 0, 58, tzinfo=timezone.utc),
        "duration_seconds": 11 * 60 + 7,
        "survivor_count": 0,
        "notes": "Old Mill Road, Residential. No distress calls detected. Area cleared.",
        "transcript": [
            {"speaker": "rover", "text": "Entering structure. Air quality degraded.", "timestamp": datetime(2026, 9, 19, 0, 58, 12, tzinfo=timezone.utc)},
            {"speaker": "driver", "text": "Anyone inside, call out if you can hear me.", "timestamp": datetime(2026, 9, 19, 0, 59, 40, tzinfo=timezone.utc)},
            {"speaker": "rover", "text": "No response detected after three sweeps.", "timestamp": datetime(2026, 9, 19, 1, 7, 51, tzinfo=timezone.utc)},
            {"speaker": "driver", "text": "Marking sector for secondary search. Withdrawing.", "timestamp": datetime(2026, 9, 19, 1, 9, 19, tzinfo=timezone.utc)},
        ]
    },
    {
        "encounter_id": "ENC-2026-0144",
        "status": "rescued",
        "started_at": datetime(2026, 9, 18, 23, 41, tzinfo=timezone.utc),
        "duration_seconds": 64 * 60 + 38,  # 1 hour 4 minutes 38 seconds
        "survivor_count": 4,
        "notes": "Northgate Transit Tunnel. Four survivors, conscious and mobile, guided out through service exit.",
        "transcript": [
            {"speaker": "person", "text": "Hello? Is someone there?", "timestamp": datetime(2026, 9, 18, 23, 41, 15, tzinfo=timezone.utc)},
            {"speaker": "driver", "text": "We hear you. How many people are with you?", "timestamp": datetime(2026, 9, 18, 23, 41, 28, tzinfo=timezone.utc)},
            {"speaker": "person", "text": "Four of us. We moved away from the water.", "timestamp": datetime(2026, 9, 18, 23, 41, 52, tzinfo=timezone.utc)},
            {"speaker": "rover", "text": "Four signatures confirmed on the east platform.", "timestamp": datetime(2026, 9, 18, 23, 42, 7, tzinfo=timezone.utc)},
            {"speaker": "driver", "text": "Good. Keep everyone together and keep talking to us.", "timestamp": datetime(2026, 9, 18, 23, 42, 33, tzinfo=timezone.utc)},
            {"speaker": "rover", "text": "All four subjects extracted. Sector clear.", "timestamp": datetime(2026, 9, 19, 0, 45, 53, tzinfo=timezone.utc)},
        ]
    },
    {
        "encounter_id": "ENC-2026-0143",
        "status": "located",
        "started_at": datetime(2026, 9, 18, 22, 19, tzinfo=timezone.utc),
        "duration_seconds": 33 * 60 + 24,
        "survivor_count": 1,
        "notes": "Grainview School, Gymnasium. Survivor with leg injury under bleachers, unable to self-evacuate.",
        "transcript": [
            {"speaker": "rover", "text": "Partial roof collapse. Void space detected beneath bleachers.", "timestamp": datetime(2026, 9, 18, 22, 19, 44, tzinfo=timezone.utc)},
            {"speaker": "person", "text": "We're under here. Please don't move the beams.", "timestamp": datetime(2026, 9, 18, 22, 21, 2, tzinfo=timezone.utc)},
            {"speaker": "driver", "text": "Nobody is touching anything. Engineers are on the way.", "timestamp": datetime(2026, 9, 18, 22, 21, 20, tzinfo=timezone.utc)},
        ]
    },
    {
        "encounter_id": "ENC-2026-0142",
        "status": "rescued",
        "started_at": datetime(2026, 9, 18, 20, 55, tzinfo=timezone.utc),
        "duration_seconds": 51 * 60 + 9,
        "survivor_count": 1,
        "notes": "Civic Center Parking Deck. Survivor found behind collapsed barrier wall on lower level. Extracted via emergency stairwell.",
        "transcript": [
            {"speaker": "driver", "text": "Rover is on level three. Call out if you can hear the engine.", "timestamp": datetime(2026, 9, 18, 20, 55, 31, tzinfo=timezone.utc)},
            {"speaker": "person", "text": "I hear it. My car is crushed against the wall.", "timestamp": datetime(2026, 9, 18, 20, 56, 48, tzinfo=timezone.utc)},
            {"speaker": "rover", "text": "Visual confirmed. Subject responsive.", "timestamp": datetime(2026, 9, 18, 20, 57, 3, tzinfo=timezone.utc)},
            {"speaker": "person", "text": "I can wait. Just tell me someone is coming.", "timestamp": datetime(2026, 9, 18, 20, 58, 11, tzinfo=timezone.utc)},
            {"speaker": "driver", "text": "Someone is coming. We are not leaving.", "timestamp": datetime(2026, 9, 18, 20, 58, 19, tzinfo=timezone.utc)},
        ]
    },
    {
        "encounter_id": "ENC-2026-0141",
        "status": "no-contact",
        "started_at": datetime(2026, 9, 18, 19, 30, tzinfo=timezone.utc),
        "duration_seconds": 8 * 60 + 52,
        "survivor_count": 0,
        "notes": "Lakeside Trailer Park. Area largely evacuated before rover arrival. Quick sweep confirmed no distress signals.",
        "transcript": [
            {"speaker": "rover", "text": "Debris field impassable beyond 12 meters.", "timestamp": datetime(2026, 9, 18, 19, 30, 41, tzinfo=timezone.utc)},
            {"speaker": "driver", "text": "Search and rescue. Respond if you hear this.", "timestamp": datetime(2026, 9, 18, 19, 33, 10, tzinfo=timezone.utc)},
            {"speaker": "rover", "text": "No contact. Recommending aerial survey.", "timestamp": datetime(2026, 9, 18, 19, 38, 27, tzinfo=timezone.utc)},
        ]
    },
    {
        "encounter_id": "ENC-2026-0140",
        "status": "rescued",
        "started_at": datetime(2026, 9, 18, 17, 2, tzinfo=timezone.utc),
        "duration_seconds": 82 * 60 + 47,  # 1 hour 22 minutes 47 seconds
        "survivor_count": 7,
        "notes": "Fairmount Hospital, East Wing. Complex multi-room search. Seven patients evacuated via structurally sound stairwell.",
        "transcript": [
            {"speaker": "person", "text": "There are patients in here who can't walk.", "timestamp": datetime(2026, 9, 18, 17, 2, 55, tzinfo=timezone.utc)},
            {"speaker": "driver", "text": "Understood. How many, and what floor?", "timestamp": datetime(2026, 9, 18, 17, 3, 9, tzinfo=timezone.utc)},
            {"speaker": "person", "text": "Six, on the third floor. The elevators are gone.", "timestamp": datetime(2026, 9, 18, 17, 3, 31, tzinfo=timezone.utc)},
            {"speaker": "rover", "text": "Stairwell B is structurally sound. Routing team.", "timestamp": datetime(2026, 9, 18, 17, 4, 2, tzinfo=timezone.utc)},
            {"speaker": "rover", "text": "All seven subjects evacuated. Wing clear.", "timestamp": datetime(2026, 9, 18, 18, 25, 42, tzinfo=timezone.utc)},
        ]
    },
]


def import_historical_encounters():
    """Import all historical encounters into MongoDB."""
    from tracking.encounters import _get_db
    
    db = _get_db()
    if db is None:
        print("ERROR: MongoDB connection failed. Check MONGODB_URI in .env")
        return False
    
    print(f"Importing {len(HISTORICAL_ENCOUNTERS)} historical encounters...")
    imported = 0
    skipped = 0
    
    for enc_data in HISTORICAL_ENCOUNTERS:
        encounter_id = enc_data["encounter_id"]
        
        # Check if already exists
        existing = db["encounters"].find_one({"encounter_id": encounter_id})
        if existing:
            print(f"  SKIP {encounter_id} (already exists)")
            skipped += 1
            continue
        
        # Build encounter document
        now = datetime.now(timezone.utc)
        completed_at = enc_data["started_at"]
        if enc_data.get("duration_seconds"):
            from datetime import timedelta
            completed_at = enc_data["started_at"] + timedelta(seconds=enc_data["duration_seconds"])
        
        encounter = {
            "encounter_id": encounter_id,
            "status": enc_data["status"],
            "started_at": enc_data["started_at"],
            "completed_at": completed_at,
            "duration_seconds": enc_data.get("duration_seconds"),
            "survivor_count": enc_data.get("survivor_count"),
            "notes": enc_data.get("notes"),
            "is_active": False,
            "transcript": [],
            "finding_ids": [],
            "brain_activity_ids": [],
            "created_at": now,
            "updated_at": now,
        }
        
        # Add transcript messages
        for i, msg in enumerate(enc_data.get("transcript", [])):
            import uuid
            encounter["transcript"].append({
                "id": str(uuid.uuid4())[:8],
                "speaker": msg["speaker"],
                "text": msg["text"],
                "timestamp": msg["timestamp"],
                "message_index": i,
            })
        
        try:
            db["encounters"].insert_one(encounter)
            print(f"  OK   {encounter_id}: {enc_data['status']}, {len(encounter['transcript'])} messages")
            imported += 1
        except Exception as e:
            print(f"  ERROR {encounter_id}: {e}")
    
    print(f"\nImport complete: {imported} imported, {skipped} skipped")
    
    # Compute initial patterns
    print("\nComputing patterns...")
    from tracking.encounter_patterns import compute_patterns
    patterns = compute_patterns()
    if patterns:
        print(f"  Patterns computed: {patterns['total_encounters']} encounters")
        print(f"  By status: {patterns['by_status']}")
        if patterns.get("insights"):
            print("  Insights:")
            for insight in patterns["insights"]:
                print(f"    - {insight['value']}")
    
    return True


if __name__ == "__main__":
    success = import_historical_encounters()
    sys.exit(0 if success else 1)
