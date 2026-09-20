"""MongoDB encounter tracking: CRUD operations for rescue encounter cases.

Each encounter represents a complete rescue case with embedded transcripts,
status tracking, and references to findings and brain activity.
"""

import logging
import os
import threading
import uuid
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

_client = None
_db = None
_lock = threading.Lock()


def _get_db():
    """Get MongoDB connection (shared with mongo.py)."""
    global _client, _db
    if _db is not None:
        return _db
    with _lock:
        if _db is not None:
            return _db
        uri = os.environ.get("MONGODB_URI")
        if not uri:
            logger.info("MONGODB_URI not set — encounter tracking disabled")
            return None
        try:
            from pymongo import MongoClient
            _client = MongoClient(uri, serverSelectionTimeoutMS=5000)
            _client.admin.command("ping")
            _db = _client["htn2026_rescue"]
            logger.info("MongoDB connected for encounters: htn2026_rescue")
            _ensure_indexes()
        except Exception:
            logger.warning("MongoDB connection failed — encounter tracking disabled", exc_info=True)
            _client = None
            return None
    return _db


def _ensure_indexes():
    """Create indexes for efficient encounter queries."""
    db = _get_db()
    if db is None:
        return
    try:
        encounters = db["encounters"]
        encounters.create_index("encounter_id", unique=True)
        encounters.create_index("is_active")
        encounters.create_index([("started_at", -1)])
        encounters.create_index("status")
        encounters.create_index([("started_at", -1), ("status", 1)])
        logger.info("Encounter indexes created")
    except Exception:
        logger.debug("Failed to create encounter indexes", exc_info=True)


def create_encounter(encounter_id: Optional[str] = None, status: str = "located") -> Optional[str]:
    """Create a new encounter and set it as active.
    
    Args:
        encounter_id: Optional encounter ID (auto-generated if not provided)
        status: Initial status (default: "located")
    
    Returns:
        The encounter_id if successful, None otherwise
    """
    db = _get_db()
    if db is None:
        return None
    
    # Generate encounter ID if not provided
    if encounter_id is None:
        now = datetime.now(timezone.utc)
        # Format: ENC-YYYY-NNNN (4-digit sequential number within year)
        year = now.year
        # Find the highest encounter number for this year
        existing = list(db["encounters"].find(
            {"encounter_id": {"$regex": f"^ENC-{year}-"}},
            {"encounter_id": 1}
        ).sort("encounter_id", -1).limit(1))
        
        if existing:
            last_id = existing[0]["encounter_id"]
            last_num = int(last_id.split("-")[-1])
            next_num = last_num + 1
        else:
            next_num = 1
        
        encounter_id = f"ENC-{year}-{next_num:04d}"
    
    # Deactivate any existing active encounter
    try:
        db["encounters"].update_many(
            {"is_active": True},
            {"$set": {"is_active": False, "updated_at": datetime.now(timezone.utc)}}
        )
    except Exception:
        logger.debug("Failed to deactivate existing encounters", exc_info=True)
    
    # Create new encounter
    now = datetime.now(timezone.utc)
    encounter = {
        "encounter_id": encounter_id,
        "status": status,
        "started_at": now,
        "completed_at": None,
        "duration_seconds": None,
        "survivor_count": None,
        "notes": None,
        "is_active": True,
        "transcript": [],
        "finding_ids": [],
        "brain_activity_ids": [],
        "created_at": now,
        "updated_at": now,
    }
    
    try:
        db["encounters"].insert_one(encounter)
        logger.info(f"Created encounter {encounter_id}")
        return encounter_id
    except Exception:
        logger.error(f"Failed to create encounter {encounter_id}", exc_info=True)
        return None


def get_active_encounter() -> Optional[dict]:
    """Get the currently active encounter.
    
    Returns:
        Encounter document (with _id as string) or None
    """
    db = _get_db()
    if db is None:
        return None
    
    try:
        enc = db["encounters"].find_one({"is_active": True})
        if enc:
            enc["_id"] = str(enc["_id"])
            # Convert ObjectIds in arrays to strings
            enc["finding_ids"] = [str(oid) for oid in enc.get("finding_ids", [])]
            enc["brain_activity_ids"] = [str(oid) for oid in enc.get("brain_activity_ids", [])]
        return enc
    except Exception:
        logger.debug("Failed to get active encounter", exc_info=True)
        return None


def get_encounter(encounter_id: str) -> Optional[dict]:
    """Get an encounter by ID.
    
    Returns:
        Encounter document (with _id as string) or None
    """
    db = _get_db()
    if db is None:
        return None
    
    try:
        enc = db["encounters"].find_one({"encounter_id": encounter_id})
        if enc:
            enc["_id"] = str(enc["_id"])
            enc["finding_ids"] = [str(oid) for oid in enc.get("finding_ids", [])]
            enc["brain_activity_ids"] = [str(oid) for oid in enc.get("brain_activity_ids", [])]
        return enc
    except Exception:
        logger.debug(f"Failed to get encounter {encounter_id}", exc_info=True)
        return None


def list_encounters(limit: int = 20, status: Optional[str] = None) -> list[dict]:
    """List encounters, most recent first.
    
    Args:
        limit: Maximum number to return
        status: Optional status filter ("rescued", "located", "no-contact")
    
    Returns:
        List of encounter documents
    """
    db = _get_db()
    if db is None:
        return []
    
    try:
        query = {}
        if status:
            query["status"] = status
        
        cursor = db["encounters"].find(query).sort("started_at", -1).limit(limit)
        encounters = []
        for enc in cursor:
            enc["_id"] = str(enc["_id"])
            enc["finding_ids"] = [str(oid) for oid in enc.get("finding_ids", [])]
            enc["brain_activity_ids"] = [str(oid) for oid in enc.get("brain_activity_ids", [])]
            encounters.append(enc)
        return encounters
    except Exception:
        logger.debug("Failed to list encounters", exc_info=True)
        return []


def update_encounter(encounter_id: str, updates: dict) -> bool:
    """Update an encounter.
    
    Args:
        encounter_id: The encounter to update
        updates: Dictionary of fields to update
    
    Returns:
        True if successful
    """
    db = _get_db()
    if db is None:
        return False
    
    try:
        updates["updated_at"] = datetime.now(timezone.utc)
        result = db["encounters"].update_one(
            {"encounter_id": encounter_id},
            {"$set": updates}
        )
        return result.modified_count > 0
    except Exception:
        logger.error(f"Failed to update encounter {encounter_id}", exc_info=True)
        return False


def complete_encounter(encounter_id: str, status: str, survivor_count: Optional[int] = None, notes: Optional[str] = None) -> bool:
    """Mark an encounter as complete.
    
    Args:
        encounter_id: The encounter to complete
        status: Final status ("rescued", "located", "no-contact")
        survivor_count: Number of survivors
        notes: Optional completion notes
    
    Returns:
        True if successful
    """
    db = _get_db()
    if db is None:
        return False
    
    try:
        enc = db["encounters"].find_one({"encounter_id": encounter_id})
        if not enc:
            logger.warning(f"Encounter {encounter_id} not found")
            return False
        
        now = datetime.now(timezone.utc)
        duration_seconds = (now - enc["started_at"]).total_seconds()
        
        updates = {
            "status": status,
            "is_active": False,
            "completed_at": now,
            "duration_seconds": duration_seconds,
            "updated_at": now,
        }
        
        if survivor_count is not None:
            updates["survivor_count"] = survivor_count
        if notes is not None:
            updates["notes"] = notes
        
        result = db["encounters"].update_one(
            {"encounter_id": encounter_id},
            {"$set": updates}
        )
        
        if result.modified_count > 0:
            logger.info(f"Completed encounter {encounter_id}: {status}, duration={duration_seconds:.0f}s")
            return True
        return False
    except Exception:
        logger.error(f"Failed to complete encounter {encounter_id}", exc_info=True)
        return False


def add_transcript_message(encounter_id: str, speaker: str, text: str, timestamp: Optional[datetime] = None) -> bool:
    """Add a message to an encounter's transcript.
    
    Args:
        encounter_id: The encounter to update
        speaker: "person", "driver", or "rover"
        text: The message text
        timestamp: Optional timestamp (defaults to now)
    
    Returns:
        True if successful
    """
    db = _get_db()
    if db is None:
        return False
    
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)
    
    try:
        # Get current transcript to determine message_index
        enc = db["encounters"].find_one({"encounter_id": encounter_id}, {"transcript": 1})
        if not enc:
            logger.warning(f"Encounter {encounter_id} not found")
            return False
        
        message_index = len(enc.get("transcript", []))
        message_id = str(uuid.uuid4())[:8]  # Short ID for UI
        
        message = {
            "id": message_id,
            "speaker": speaker,
            "text": text,
            "timestamp": timestamp,
            "message_index": message_index,
        }
        
        result = db["encounters"].update_one(
            {"encounter_id": encounter_id},
            {
                "$push": {"transcript": message},
                "$set": {"updated_at": datetime.now(timezone.utc)}
            }
        )
        
        return result.modified_count > 0
    except Exception:
        logger.error(f"Failed to add transcript message to {encounter_id}", exc_info=True)
        return False


def link_finding(encounter_id: str, finding_id: str) -> bool:
    """Link a finding to an encounter.
    
    Args:
        encounter_id: The encounter
        finding_id: The finding ObjectId (as string)
    
    Returns:
        True if successful
    """
    db = _get_db()
    if db is None:
        return False
    
    try:
        from bson import ObjectId
        result = db["encounters"].update_one(
            {"encounter_id": encounter_id},
            {
                "$addToSet": {"finding_ids": ObjectId(finding_id)},
                "$set": {"updated_at": datetime.now(timezone.utc)}
            }
        )
        return result.modified_count > 0
    except Exception:
        logger.debug(f"Failed to link finding to encounter {encounter_id}", exc_info=True)
        return False


def link_brain_activity(encounter_id: str, activity_id: str) -> bool:
    """Link a brain activity record to an encounter.
    
    Args:
        encounter_id: The encounter
        activity_id: The brain_activity ObjectId (as string)
    
    Returns:
        True if successful
    """
    db = _get_db()
    if db is None:
        return False
    
    try:
        from bson import ObjectId
        result = db["encounters"].update_one(
            {"encounter_id": encounter_id},
            {
                "$addToSet": {"brain_activity_ids": ObjectId(activity_id)},
                "$set": {"updated_at": datetime.now(timezone.utc)}
            }
        )
        return result.modified_count > 0
    except Exception:
        logger.debug(f"Failed to link brain activity to encounter {encounter_id}", exc_info=True)
        return False


def get_encounter_stats() -> dict:
    """Get statistics about all encounters.
    
    Returns:
        Dictionary with count, by_status, etc.
    """
    db = _get_db()
    if db is None:
        return {"connected": False}
    
    try:
        total = db["encounters"].count_documents({})
        by_status = {
            "rescued": db["encounters"].count_documents({"status": "rescued"}),
            "located": db["encounters"].count_documents({"status": "located"}),
            "no-contact": db["encounters"].count_documents({"status": "no-contact"}),
        }
        
        active = db["encounters"].find_one({"is_active": True})
        
        return {
            "connected": True,
            "total": total,
            "by_status": by_status,
            "active_encounter_id": active["encounter_id"] if active else None,
        }
    except Exception:
        logger.debug("Failed to get encounter stats", exc_info=True)
        return {"connected": False}
