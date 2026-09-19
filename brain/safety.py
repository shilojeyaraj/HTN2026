"""SayCan-style feasibility gate: the brain proposes a verb, this vetoes it against the
latest detections before it ever reaches the arbiter (CLAUDE.md section 7)."""

from brain.state import Detection

MIN_CLEARANCE_M = 0.4
GATED_VERBS = {"forward"}


def check(name: str, args: dict, detections: list[Detection]) -> str:
    if name not in GATED_VERBS:
        return "OK"

    for det in detections:
        if abs(det["bearing_deg"]) < 30 and det["distance_m"] < MIN_CLEARANCE_M:
            return "VETO"

    return "OK"
