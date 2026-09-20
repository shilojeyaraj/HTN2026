"""Small, local semantic memory. Bearings are command estimates, never a metric map."""

from dataclasses import dataclass, field, asdict
import logging
import math

logger = logging.getLogger(__name__)

ROOM_FEATURES = ["doorway", "wall", "passage", "furniture", "open area", "obstacle"]
DISTANCES = ["near", "medium", "far", "unknown"]
VIEW_QUALITIES = ["good", "limited", "poor", "unknown"]
MAX_OBSERVATIONS = 36
MAX_ENTITIES = 128

DETECTION_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "type": {"type": "string", "minLength": 1, "maxLength": 60},
        "description": {"type": "string", "minLength": 1, "maxLength": 240},
        "distance": {"type": "string", "enum": DISTANCES},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "status": {"type": "string", "minLength": 1, "maxLength": 80},
        "matched_id": {"type": ["string", "null"]},
    },
    "required": ["type", "description", "distance", "confidence", "status", "matched_id"],
}
WORLD_OBSERVATION_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "view_quality": {"type": "string", "enum": VIEW_QUALITIES},
        # Gemini rejects this combined schema with maxItems on these arrays.
        # Keep the 24-item limit in validate_world_observation below.
        "entities": {"type": "array", "items": DETECTION_SCHEMA},
        "room_features": {"type": "array", "items": {
            **DETECTION_SCHEMA, "properties": {**DETECTION_SCHEMA["properties"],
                                               "type": {"type": "string", "enum": ROOM_FEATURES}},
        }},
    },
    "required": ["view_quality", "entities", "room_features"],
}


def validate_world_observation(value: dict) -> None:
    if not isinstance(value, dict) or set(value) != set(WORLD_OBSERVATION_SCHEMA["required"]):
        raise ValueError("world_observation requires view_quality, entities, room_features")
    if value["view_quality"] not in VIEW_QUALITIES:
        raise ValueError("invalid view quality")
    for group in ("entities", "room_features"):
        if not isinstance(value[group], list) or len(value[group]) > 24:
            raise ValueError("semantic detections must be a list of at most 24 items")
        for item in value[group]:
            if not isinstance(item, dict) or set(item) != set(DETECTION_SCHEMA["required"]):
                raise ValueError("invalid semantic detection fields")
            for key, limit in (("type", 60), ("description", 240), ("status", 80)):
                if not isinstance(item[key], str) or not 1 <= len(item[key].strip()) <= limit:
                    raise ValueError(f"invalid detection {key}")
            if group == "room_features" and item["type"] not in ROOM_FEATURES:
                raise ValueError("invalid room feature type")
            if item["distance"] not in DISTANCES:
                raise ValueError("invalid rough distance")
            confidence = item["confidence"]
            if type(confidence) not in (int, float) or not 0 <= confidence <= 1 or not math.isfinite(confidence):
                raise ValueError("confidence must be finite and within [0, 1]")
            if item["matched_id"] is not None and (not isinstance(item["matched_id"], str)
                                                   or not 1 <= len(item["matched_id"]) <= 60):
                raise ValueError("matched_id must be a local id or null")


@dataclass
class WorldState:
    robot: dict = field(default_factory=lambda: {"heading_deg": 0.0, "camera_height": "unknown"})
    observations: list[dict] = field(default_factory=list)
    entities: list[dict] = field(default_factory=list)
    room_features: list[dict] = field(default_factory=list)
    searched_headings: list[float] = field(default_factory=list)
    bearings_stale: bool = False
    next_id: int = 1

    def observe(self, summary: str, semantic: dict, timestamp: float) -> None:
        validate_world_observation(semantic)
        heading = self.robot["heading_deg"]
        self.observations.append({"heading_deg": heading, "summary": summary,
                                  "camera_height": self.robot["camera_height"],
                                  "timestamp": timestamp, "view_quality": semantic["view_quality"]})
        del self.observations[:-MAX_OBSERVATIONS]
        if heading is not None and heading not in self.searched_headings:
            self.searched_headings.append(heading)
            del self.searched_headings[:-MAX_OBSERVATIONS]
        for group in ("entities", "room_features"):
            records = getattr(self, group)
            known = {entity["id"]: entity for entity in records}
            matched = set()
            for detection in semantic[group]:
                entity = known.get(detection["matched_id"])
                # ponytail: visual identity comes from the current image + local context;
                # add visual tracking if this conservative association proves insufficient.
                if (entity is None or entity["id"] in matched or detection["confidence"] < 0.8
                        or entity["type"].casefold() != detection["type"].casefold()):
                    entity = {"id": f"entity-{self.next_id}", "first_seen_heading_deg": heading,
                              "first_seen_camera_height": self.robot["camera_height"],
                              "first_seen_at": timestamp}
                    self.next_id += 1
                    records.append(entity)
                    change = "new"
                else:
                    matched.add(entity["id"])
                    change = "updated"
                entity.update({key: value for key, value in detection.items() if key != "matched_id"})
                entity.update(last_seen_heading_deg=heading, last_seen_at=timestamp,
                              last_seen_camera_height=self.robot["camera_height"])
                logger.info("WorldState %s %s id=%s heading_deg=%s description=%s confidence=%.2f",
                            change, group, entity["id"], heading, entity["description"], entity["confidence"])
            del records[:-MAX_ENTITIES]

    def summary(self) -> str:
        lines = [f"{entity['description']} around heading {entity['last_seen_heading_deg']}° "
                 f"({entity['distance']}, confidence {entity['confidence']:.2f})"
                 for entity in self.entities + self.room_features]
        if not lines:
            lines = [f"Heading {obs['heading_deg']}°: {obs['summary']} ({obs['view_quality']} view)"
                     for obs in self.observations]
        poor = [obs["heading_deg"] for obs in self.observations if obs["view_quality"] in {"poor", "unknown"}]
        return ("Historical hints; re-perceive before approaching. "
                + ("Robot has translated; stored bearings may be stale. " if self.bearings_stale else "")
                + "; ".join(lines[:12])
                + (f"; Unclear views at headings {poor}." if poor else ""))

    def context(self) -> dict:
        result = asdict(self)
        result.pop("next_id")
        return result
