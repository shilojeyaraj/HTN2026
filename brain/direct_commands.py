"""Exact local command grammar; anything uncertain belongs to the visual planner."""

import re
from decimal import Decimal

from brain.tools import TOOL_PARAMETERS, validate_tool_args

SLIGHT_TRANSLATION_M = 0.2
SLIGHT_TURN_DEG = 15.0
MAX_DIRECT_CHUNKS = 100

NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)"
TURN_DIRECTION = r"left|right|clockwise|counterclockwise"
TRANSLATIONS = {"forward", "backward", "strafe_left", "strafe_right"}


def parse_direct_command(text: str | None) -> dict | None:
    """Match a complete user command, never a substring of an autonomous goal."""
    if not isinstance(text, str):
        return None
    text = " ".join(text.lower().split()).rstrip(".!")
    text = re.sub(r"^please ", "", text)
    if re.fullmatch(r"stop(?: (?:the )?(?:robot|chassis))?", text):
        return {"verb": "stop", "args": {}}
    if match := re.fullmatch(r"(open|close) (?:the )?(?:gripper|claw)", text):
        return {"verb": f"{match[1]}_gripper", "args": {}}
    if re.fullmatch(r"(?:recenter|recentre) (?:the )?arm", text):
        return {"verb": "recenter_arm", "args": {}}

    if match := re.fullmatch(
        rf"(?:turn|rotate)(?: ({TURN_DIRECTION}))? "
        rf"({NUMBER}(?:\s*(?:degrees?|°))?|slightly|a little)(?: ({TURN_DIRECTION}))?", text,
    ):
        before, quantity, after = match.groups()
        if before and after:  # Conflicting/redundant directions are ambiguous.
            return None
        direction = before or after
        degrees = SLIGHT_TURN_DEG if quantity in {"slightly", "a little"} else float(re.sub(r"\s*(?:degrees?|°)$", "", quantity))
        if direction and degrees < 0:
            return None
        if direction in {"right", "clockwise"}:
            degrees = -degrees
        return {"verb": "turn", "args": {"degrees": degrees}}

    if match := re.fullmatch(
        rf"((?:(?:move|drive) )?(?:forward|backward|backwards)|strafe (?:left|right)) "
        rf"({NUMBER}\s*(?:m|metres?|meters?)|slightly|a little)", text,
    ):
        direction, quantity = match.groups()
        name = re.sub(r"^(?:move|drive) ", "", direction).replace(" ", "_")
        if name == "backwards":
            name = "backward"
        distance = SLIGHT_TRANSLATION_M if quantity in {"slightly", "a little"} else float(re.sub(r"\s*(?:m|metres?|meters?)$", "", quantity))
        return {"verb": name, "args": {"distance_m": distance}}

    if match := re.fullmatch(rf"move (?:the )?arm (forward|backward|up|down) ({NUMBER})\s*mm", text):
        direction, quantity = match.groups()
        amount = float(quantity)
        if amount < 0:
            return None
        if direction in {"backward", "down"}:
            amount = -amount
        return {"verb": "move_arm", "args": {
            "x_mm": amount if direction in {"forward", "backward"} else 0,
            "y_mm": amount if direction in {"up", "down"} else 0,
        }}
    return None


def decompose_direct_command(command: dict) -> list[dict]:
    """Build bounded local calls without truncating totals or overshooting a small tail."""
    name, args = command.get("verb"), command.get("args")
    # Reuse the executor's numeric/type checks, but don't clamp the requested total.
    validate_tool_args(name, args)
    if name not in TRANSLATIONS and name != "turn":
        return [command]
    key = "degrees" if name == "turn" else "distance_m"
    total = float(args.get(key))
    if name in TRANSLATIONS and total < 0:
        raise ValueError("translation totals must be non-negative; choose forward/backward/strafe direction")
    if total == 0:
        return []

    rule = TOOL_PARAMETERS[name]["properties"][key]
    minimum = Decimal(str(rule["minimum"])) if name in TRANSLATIONS else Decimal(0)
    maximum = Decimal(str(rule["maximum"] if total > 0 else -rule["minimum"]))
    magnitude = Decimal(str(abs(total)))
    if magnitude < minimum:
        raise ValueError(f"requested total is below the {minimum} m minimum; refusing to overshoot")
    if magnitude > maximum * MAX_DIRECT_CHUNKS:
        raise ValueError(f"direct command exceeds the {MAX_DIRECT_CHUNKS}-chunk limit")

    count, remainder = divmod(magnitude, maximum)
    chunks = [maximum] * int(count)
    if remainder:
        if remainder < minimum:
            chunks[-1] -= minimum - remainder
            remainder = minimum
        chunks.append(remainder)
    calls = [{"verb": name, "args": {key: float(chunk) * (1 if total > 0 else -1)}} for chunk in chunks]
    # Validate the whole plan before the first move. No chunk may rely on clamping
    # to silently change the distance/angle the user explicitly requested.
    for call in calls:
        if validate_tool_args(name, call["args"]) != call["args"]:
            raise ValueError("requested total cannot be split within the configured tool bounds")
    return calls
