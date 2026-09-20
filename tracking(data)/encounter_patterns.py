"""Compute and cache encounter pattern analytics.

Analyzes patterns across all encounters: rescue success rates, duration trends,
and insights. Results are stored in the encounter_patterns collection.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


def compute_patterns() -> Optional[dict]:
    """Compute analytics across all encounters.
    
    Returns:
        Dictionary with computed patterns, or None if MongoDB unavailable
    """
    from tracking.encounters import _get_db
    
    db = _get_db()
    if db is None:
        return None
    
    try:
        # Get all completed encounters
        encounters = list(db["encounters"].find({"completed_at": {"$ne": None}}))
        
        if not encounters:
            return {
                "computed_at": datetime.now(timezone.utc),
                "total_encounters": 0,
                "by_status": {"rescued": 0, "located": 0, "no-contact": 0},
                "duration_stats": {},
                "insights": [],
            }
        
        total = len(encounters)
        
        # Count by status
        by_status = {
            "rescued": sum(1 for e in encounters if e["status"] == "rescued"),
            "located": sum(1 for e in encounters if e["status"] == "located"),
            "no-contact": sum(1 for e in encounters if e["status"] == "no-contact"),
        }
        
        # Duration statistics (only for completed encounters with duration)
        durations = [e["duration_seconds"] for e in encounters if e.get("duration_seconds")]
        
        duration_stats = {}
        if durations:
            durations_minutes = [d / 60 for d in durations]
            duration_stats = {
                "avg_minutes": sum(durations_minutes) / len(durations_minutes),
                "median_minutes": sorted(durations_minutes)[len(durations_minutes) // 2],
                "min_minutes": min(durations_minutes),
                "max_minutes": max(durations_minutes),
            }
            
            # Find longest and shortest
            longest = max(encounters, key=lambda e: e.get("duration_seconds", 0))
            shortest = min((e for e in encounters if e.get("duration_seconds")), 
                          key=lambda e: e["duration_seconds"])
            
            duration_stats["longest_encounter_id"] = longest["encounter_id"]
            duration_stats["shortest_encounter_id"] = shortest["encounter_id"]
        
        # Generate insights
        insights = []
        
        if total >= 3:
            rescue_rate = (by_status["rescued"] / total) * 100
            insights.append({
                "key": "rescue_rate",
                "value": f"{rescue_rate:.0f}% ({by_status['rescued']} of {total} encounters)"
            })
        
        if len(durations) >= 4:
            # Analyze duration vs outcome
            rescued_durations = [e["duration_seconds"] / 60 for e in encounters 
                                if e["status"] == "rescued" and e.get("duration_seconds")]
            no_contact_durations = [e["duration_seconds"] / 60 for e in encounters 
                                   if e["status"] == "no-contact" and e.get("duration_seconds")]
            
            if rescued_durations and no_contact_durations:
                avg_rescued = sum(rescued_durations) / len(rescued_durations)
                avg_no_contact = sum(no_contact_durations) / len(no_contact_durations)
                
                if avg_rescued > avg_no_contact * 1.5:
                    insights.append({
                        "key": "duration_correlation",
                        "value": f"Longer encounters ({avg_rescued:.0f}min avg) correlate with rescue success"
                    })
        
        # Quick vs extended encounters
        if durations:
            quick_encounters = [e for e in encounters 
                              if e.get("duration_seconds", 0) < 900]  # < 15 minutes
            if quick_encounters:
                quick_rescued = sum(1 for e in quick_encounters if e["status"] == "rescued")
                quick_total = len(quick_encounters)
                insights.append({
                    "key": "quick_encounters",
                    "value": f"Quick encounters (<15min): {quick_rescued}/{quick_total} rescued"
                })
        
        patterns = {
            "computed_at": datetime.now(timezone.utc),
            "total_encounters": total,
            "by_status": by_status,
            "duration_stats": duration_stats,
            "insights": insights,
        }
        
        # Store in database
        db["encounter_patterns"].replace_one(
            {},
            patterns,
            upsert=True
        )
        
        logger.info(f"Computed patterns: {total} encounters, {by_status['rescued']} rescued")
        return patterns
        
    except Exception:
        logger.error("Failed to compute encounter patterns", exc_info=True)
        return None


def get_cached_patterns() -> Optional[dict]:
    """Get the most recently computed patterns from cache.
    
    Returns:
        Cached patterns or None
    """
    from tracking.encounters import _get_db
    
    db = _get_db()
    if db is None:
        return None
    
    try:
        patterns = db["encounter_patterns"].find_one()
        if patterns:
            patterns["_id"] = str(patterns["_id"])
        return patterns
    except Exception:
        logger.debug("Failed to get cached patterns", exc_info=True)
        return None


def get_patterns(force_recompute: bool = False) -> Optional[dict]:
    """Get encounter patterns, computing if necessary.
    
    Args:
        force_recompute: If True, recompute even if cache exists
    
    Returns:
        Patterns dictionary or None
    """
    if force_recompute:
        return compute_patterns()
    
    cached = get_cached_patterns()
    if cached:
        return cached
    
    return compute_patterns()
