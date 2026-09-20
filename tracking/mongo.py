"""MongoDB mission tracking: stores transcripts, brain activity, findings,
sensor readings, RAG retrievals, and pattern insights for real-time mission
tracking and post-mission analysis.

Graceful degradation: if MongoDB is unavailable, all log methods silently
no-op so the rover keeps running.
"""

import logging
import os
import threading
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_client = None
_db = None
_lock = threading.Lock()


def _get_db():
    global _client, _db
    if _db is not None:
        return _db
    with _lock:
        if _db is not None:
            return _db
        uri = os.environ.get("MONGODB_URI")
        if not uri:
            logger.info("MONGODB_URI not set — tracking disabled")
            return None
        try:
            from pymongo import MongoClient
            _client = MongoClient(uri, serverSelectionTimeoutMS=5000)
            _client.admin.command("ping")
            _db = _client["htn2026_rescue"]
            logger.info("MongoDB connected: htn2026_rescue")
        except Exception:
            logger.warning("MongoDB connection failed — tracking disabled", exc_info=True)
            _client = None
            return None
    return _db


def _insert(collection: str, doc: dict) -> None:
    db = _get_db()
    if db is None:
        return
    doc["timestamp"] = datetime.now(timezone.utc)
    try:
        db[collection].insert_one(doc)
    except Exception:
        logger.debug("MongoDB insert failed for %s", collection, exc_info=True)


def log_transcript(text: str, final: bool, utterance_id: int, pose: tuple = None) -> None:
    _insert("transcripts", {
        "text": text,
        "final": final,
        "utterance_id": utterance_id,
        "pose": list(pose) if pose else None,
    })


def log_brain_call(tool: str, args: dict, result: dict, pose: tuple = None) -> None:
    _insert("brain_activity", {
        "tool": tool,
        "args": args,
        "result": result,
        "pose": list(pose) if pose else None,
    })


def log_finding(finding_type: str, description: str, pose: tuple = None) -> None:
    _insert("findings", {
        "finding_type": finding_type,
        "description": description,
        "pose": list(pose) if pose else None,
    })


def log_sensor_reading(temperature: dict, audio: dict, gyro: dict, pose: tuple = None) -> None:
    _insert("sensor_readings", {
        "temperature": temperature,
        "audio": audio,
        "gyro": gyro,
        "pose": list(pose) if pose else None,
    })


def log_rag(query: str, results: dict, pose: tuple = None) -> None:
    _insert("rag_logs", {
        "query": query,
        "results": results,
        "pose": list(pose) if pose else None,
    })


def log_insights(insights: dict) -> None:
    _insert("insights", {"insights": insights})


def get_recent(collection: str, limit: int = 10) -> list:
    db = _get_db()
    if db is None:
        return []
    try:
        cursor = db[collection].find().sort("timestamp", -1).limit(limit)
        return [{**doc, "_id": str(doc["_id"]), "timestamp": doc["timestamp"].isoformat()} for doc in cursor]
    except Exception:
        return []


def get_stats() -> dict:
    db = _get_db()
    if db is None:
        return {"connected": False}
    try:
        return {
            "connected": True,
            "transcripts": db["transcripts"].count_documents({}),
            "brain_activity": db["brain_activity"].count_documents({}),
            "findings": db["findings"].count_documents({}),
            "sensor_readings": db["sensor_readings"].count_documents({}),
            "rag_logs": db["rag_logs"].count_documents({}),
            "insights": db["insights"].count_documents({}),
        }
    except Exception:
        return {"connected": False}
