"""Query MongoDB for mission tracking records.

Shows recent transcripts, brain activity, findings, sensor readings,
RAG logs, and insights stored during a rescue mission.

Run:
    python tracking/query.py              # show stats + recent records
    python tracking/query.py --collection transcripts --limit 20
    python tracking/query.py --stats       # just the stats
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
_env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
load_dotenv(_env_path)

from tracking import mongo

COLLECTIONS = ["transcripts", "brain_activity", "findings", "sensor_readings", "rag_logs", "insights"]


def show_stats():
    stats = mongo.get_stats()
    if not stats.get("connected"):
        print("MongoDB not connected. Check MONGODB_URI in .env")
        return
    print("=" * 60)
    print("MISSION TRACKING STATS")
    print("=" * 60)
    for key, val in stats.items():
        print(f"  {key}: {val}")
    print()


def show_recent(collection: str, limit: int = 10):
    records = mongo.get_recent(collection, limit)
    if not records:
        print(f"\n  No records in {collection}")
        return
    print(f"\n{'─' * 60}")
    print(f"RECENT {collection.upper()} ({len(records)} records)")
    print(f"{'─' * 60}")
    for r in records:
        ts = r.get("timestamp", "")
        if collection == "transcripts":
            final = "FINAL" if r.get("final") else "partial"
            print(f"  [{ts}] ({final}) {r.get('text', '')}")
        elif collection == "brain_activity":
            print(f"  [{ts}] {r.get('tool', '')}({json.dumps(r.get('args', {}))[:60]}) → {json.dumps(r.get('result', {}))[:60]}")
        elif collection == "findings":
            print(f"  [{ts}] [{r.get('finding_type', '')}] {r.get('description', '')}")
        elif collection == "sensor_readings":
            temp = r.get("temperature", {})
            audio = r.get("audio", {})
            gyro = r.get("gyro", {})
            print(f"  [{ts}] temp={temp.get('celsius', '?')}°C audio={audio.get('db', '?')}dB gyro_tipped={gyro.get('tipped', '?')}")
        elif collection == "rag_logs":
            print(f"  [{ts}] query='{r.get('query', '')}' → {json.dumps(r.get('results', {}))[:80]}")
        elif collection == "insights":
            print(f"  [{ts}] {json.dumps(r.get('insights', {}))[:100]}")


def main():
    ap = argparse.ArgumentParser(description="Query MongoDB mission tracking")
    ap.add_argument("--collection", default=None, help=f"specific collection: {', '.join(COLLECTIONS)}")
    ap.add_argument("--limit", type=int, default=10, help="number of records to show")
    ap.add_argument("--stats", action="store_true", help="show only stats")
    args = ap.parse_args()

    if args.stats:
        show_stats()
        return

    show_stats()

    if args.collection:
        show_recent(args.collection, args.limit)
    else:
        for col in COLLECTIONS:
            show_recent(col, 5)


if __name__ == "__main__":
    main()
