"""2D occupancy grid map accumulator with sensor overlay layers.

Builds a top-down map as the rover drives: ultrasonic readings ray-cast onto a
log-odds grid (high confidence), camera depth proximity scores (low confidence),
plus overlay layers for sound events, heat points, hazard incidents, vision
annotations, and the rover's trail.

Single-mic audio: sound markers are placed at the rover's position with a label
but no bearing (no DOA without a mic array). The cluster of markers as the rover
moves shows the operator where the source is.

Grid is serialized to JSON via to_payload() for the WebSocket server to push to
the frontend.
"""

import math

import numpy as np

GRID_SIZE_M = 20.0
GRID_RESOLUTION_M = 0.2
LOG_ODD_OCC = 0.85
LOG_ODD_FREE = -0.4
LOG_ODD_MIN = -2.0
LOG_ODD_MAX = 2.0
TRAIL_MAX = 500
ULTRASONIC_CONE_HALF_ANGLE = 7.0


class OccupancyMap:
    def __init__(self, size_m: float = GRID_SIZE_M, resolution_m: float = GRID_RESOLUTION_M):
        self.resolution = resolution_m
        self.size = int(size_m / resolution_m)
        self.grid = np.zeros((self.size, self.size), dtype=np.float32)
        self.sound_sources: list[dict] = []
        self.heat_points: list[dict] = []
        self.hazards: list[dict] = []
        self.annotations: list[dict] = []
        self.trail: list[list[float]] = []

    def _world_to_grid(self, x: float, y: float) -> tuple[int, int]:
        half = self.size * self.resolution / 2
        gx = int((x + half) / self.resolution)
        gy = int((y + half) / self.resolution)
        return gx, gy

    def _in_bounds(self, gx: int, gy: int) -> bool:
        return 0 <= gx < self.size and 0 <= gy < self.size

    @staticmethod
    def _bresenham(x0: int, y0: int, x1: int, y1: int):
        dx = abs(x1 - x0)
        dy = abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy
        while True:
            yield x0, y0
            if x0 == x1 and y0 == y1:
                break
            err2 = 2 * err
            if err2 > -dy:
                err -= dy
                x0 += sx
            if err2 < dx:
                err += dx
                y0 += sy

    def _ray_cast(self, pose: tuple[float, float, float], angle_rad: float, distance_m: float,
                 occ_weight: float, free_weight: float) -> None:
        x, y, _ = pose
        end_x = x + distance_m * math.cos(angle_rad)
        end_y = y + distance_m * math.sin(angle_rad)
        gx0, gy0 = self._world_to_grid(x, y)
        gx1, gy1 = self._world_to_grid(end_x, end_y)
        if not self._in_bounds(gx1, gy1):
            return
        for gx, gy in self._bresenham(gx0, gy0, gx1, gy1):
            if self._in_bounds(gx, gy):
                self.grid[gy, gx] = max(LOG_ODD_MIN, self.grid[gy, gx] + free_weight)
        self.grid[gy1, gx1] = min(LOG_ODD_MAX, self.grid[gy1, gx1] + occ_weight)

    def add_ultrasonic(self, pose: tuple[float, float, float], bearing_deg: float,
                       distance_m: float) -> None:
        """Ray-cast an ultrasonic reading (3 rays across the cone) onto the grid."""
        heading_rad = math.radians(pose[2])
        for offset in [-ULTRASONIC_CONE_HALF_ANGLE, 0, ULTRASONIC_CONE_HALF_ANGLE]:
            angle = heading_rad + math.radians(bearing_deg + offset)
            self._ray_cast(pose, angle, distance_m, LOG_ODD_OCC, LOG_ODD_FREE)

    def add_depth(self, pose: tuple[float, float, float], bearing_deg: float,
                  proximity: float) -> None:
        """Add camera depth proximity (0-1, 1=close). Lower confidence than ultrasonic."""
        if proximity < 0.3:
            return
        distance_m = proximity * 3.0
        angle = math.radians(pose[2] + bearing_deg)
        self._ray_cast(pose, angle, distance_m, LOG_ODD_OCC * 0.5, LOG_ODD_FREE * 0.5)

    def add_sound(self, pose: tuple[float, float, float], kind: str, label: str, db: float) -> None:
        """Place a sound marker at the rover's position (single mic, no bearing)."""
        self.sound_sources.append({"x": pose[0], "y": pose[1], "kind": kind, "label": label, "db": db})

    def add_transcript(self, pose: tuple[float, float, float], text: str, final: bool) -> None:
        """Place a speech transcript marker at the rover's position.

        Provisional transcripts are dimmed; finals are solid. The cluster of
        markers as the rover moves shows the operator where speech happened.
        """
        self.sound_sources.append({
            "x": pose[0], "y": pose[1],
            "kind": "speech",
            "label": text[:120],
            "final": final,
        })

    def add_heat(self, pose: tuple[float, float, float], celsius: float, status: str) -> None:
        """Place a heat point at the rover's position if warm or overheat."""
        if status == "ok":
            return
        self.heat_points.append({"x": pose[0], "y": pose[1], "celsius": celsius, "status": status})

    def add_hazard(self, pose: tuple[float, float, float], hazard_type: str) -> None:
        """Place a hazard marker (bump, tipped) at the rover's position."""
        self.hazards.append({"x": pose[0], "y": pose[1], "type": hazard_type})

    def add_annotation(self, pose: tuple[float, float, float], text: str, source: str = "gemini") -> None:
        """Place a vision annotation at the rover's position."""
        self.annotations.append({"x": pose[0], "y": pose[1], "text": text, "source": source})

    def add_trail(self, pose: tuple[float, float, float]) -> None:
        self.trail.append([pose[0], pose[1]])
        if len(self.trail) > TRAIL_MAX:
            self.trail = self.trail[-TRAIL_MAX:]

    def nearby_summary(self, pose: tuple[float, float, float], radius_m: float = 3.0) -> dict:
        """Return a summary of map features within radius_m of the pose."""
        x, y, _ = pose
        obstacles = []
        gx, gy = self._world_to_grid(x, y)
        r = int(radius_m / self.resolution)
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                cx, cy = gx + dx, gy + dy
                if not self._in_bounds(cx, cy):
                    continue
                prob = 1.0 / (1.0 + np.exp(-self.grid[cy, cx]))
                if prob > 0.65:
                    wx = (cx * self.resolution) - self.size * self.resolution / 2
                    wy = (cy * self.resolution) - self.size * self.resolution / 2
                    dist = math.sqrt((wx - x) ** 2 + (wy - y) ** 2)
                    if dist <= radius_m:
                        obstacles.append({"x": round(wx, 2), "y": round(wy, 2), "prob": round(float(prob), 2), "dist_m": round(dist, 2)})
        sounds = [{"x": s["x"], "y": s["y"], "kind": s["kind"], "label": s["label"], "dist_m": round(math.sqrt((s["x"] - x) ** 2 + (s["y"] - y) ** 2), 2)}
                  for s in self.sound_sources if math.sqrt((s["x"] - x) ** 2 + (s["y"] - y) ** 2) <= radius_m]
        heat = [{"x": h["x"], "y": h["y"], "celsius": h["celsius"], "status": h["status"], "dist_m": round(math.sqrt((h["x"] - x) ** 2 + (h["y"] - y) ** 2), 2)}
                for h in self.heat_points if math.sqrt((h["x"] - x) ** 2 + (h["y"] - y) ** 2) <= radius_m]
        hazards = [{"x": h["x"], "y": h["y"], "type": h["type"], "dist_m": round(math.sqrt((h["x"] - x) ** 2 + (h["y"] - y) ** 2), 2)}
                   for h in self.hazards if math.sqrt((h["x"] - x) ** 2 + (h["y"] - y) ** 2) <= radius_m]
        annotations = [{"x": a["x"], "y": a["y"], "text": a["text"], "dist_m": round(math.sqrt((a["x"] - x) ** 2 + (a["y"] - y) ** 2), 2)}
                       for a in self.annotations if math.sqrt((a["x"] - x) ** 2 + (a["y"] - y) ** 2) <= radius_m]
        return {
            "obstacles_nearby": obstacles[:10],
            "sounds_nearby": sounds,
            "heat_nearby": heat,
            "hazards_nearby": hazards,
            "annotations_nearby": annotations,
            "trail_points": len(self.trail),
        }

    def to_payload(self, rover_pose: tuple[float, float, float]) -> dict:
        """Serialize to JSON for the WebSocket server.

        The occupancy grid is quantized to uint8 (0-255) and base64-encoded
        for compact transport (~7x smaller, ~5x faster to serialize than a
        JSON float array). The frontend decodes it back to 0-1 probabilities.
        """
        import base64

        prob = 1.0 / (1.0 + np.exp(-self.grid))
        grid_uint8 = np.clip(prob * 255, 0, 255).astype(np.uint8)
        grid_b64 = base64.b64encode(grid_uint8.tobytes()).decode("ascii")
        return {
            "rover_pose": list(rover_pose),
            "grid": grid_b64,
            "grid_encoding": "base64_uint8",
            "grid_width": self.size,
            "grid_height": self.size,
            "grid_resolution_m": self.resolution,
            "sound_sources": self.sound_sources,
            "heat_points": self.heat_points,
            "hazards": self.hazards,
            "annotations": self.annotations,
            "trail": self.trail,
        }
