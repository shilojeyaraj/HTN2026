"""OAK-D S2 capture via DepthAI: RGB frames, depth, and on-camera object detections."""

import depthai as dai

from brain.state import Detection


def build_pipeline() -> dai.Pipeline:
    pipeline = dai.Pipeline()
    # TODO: RGB cam node -> XLinkOut "rgb"; StereoDepth -> XLinkOut "depth";
    # on-device YOLO detection network -> XLinkOut "detections". Wire once the
    # chassis/camera mount is confirmed (CLAUDE.md section 11).
    return pipeline


class Camera:
    """Holds the open DepthAI device for the process lifetime."""

    def __init__(self):
        self.device = dai.Device(build_pipeline())
        self.rgb_queue = self.device.getOutputQueue("rgb", maxSize=1, blocking=False)
        self.det_queue = self.device.getOutputQueue("detections", maxSize=1, blocking=False)

    def read_detections(self) -> list[Detection]:
        raise NotImplementedError

    def read_frame_jpeg(self) -> bytes:
        raise NotImplementedError

    def get_latest(self) -> tuple[bytes, list[Detection]]:
        return self.read_frame_jpeg(), self.read_detections()


_camera: Camera | None = None


def _get_camera() -> Camera:
    """Lazily opens the device on first call, then reuses it for the process lifetime."""
    global _camera
    if _camera is None:
        _camera = Camera()
    return _camera


def get_latest_frame() -> tuple[bytes, list[Detection]]:
    return _get_camera().get_latest()


def get_latest_detections() -> list[Detection]:
    """Cheap, no JPEG encode -- safe to call at reflex/verb-polling rate (~20-30 Hz),
    unlike get_latest_frame() which is only for the once-per-episode vision calls."""
    return _get_camera().read_detections()
