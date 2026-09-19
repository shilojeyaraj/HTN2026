"""Optional local Matroska recording; copy JPEG and PCM without re-encoding."""

from datetime import datetime, timezone
from fractions import Fraction
import logging
from pathlib import Path
import time
from uuid import uuid4

from shared.protocol import AUDIO_RATE


class Recording:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.container = None
        self.file = None
        self.path = None
        self.started = None
        self.pending_audio = []
        self.pending_bytes = 0
        self.audio_end = 0
        self.video_pts = -1

    def elapsed(self):
        now = time.monotonic()
        if self.started is None:
            self.started = now
        return now - self.started

    def open(self, size=None):
        import av

        self.directory.mkdir(parents=True, exist_ok=True)
        name = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.path = self.directory / f"{name}-{uuid4().hex[:8]}.mkv"
        self.file = self.path.open("xb")
        try:
            self.container = av.open(self.file, mode="w", format="matroska")
            self.audio_stream = self.container.add_stream("pcm_s16le", rate=AUDIO_RATE)
            self.audio_stream.layout = "mono"
            if size:
                self.video_stream = self.container.add_stream("mjpeg", rate=30)
                self.video_stream.width, self.video_stream.height = size
                self.video_stream.pix_fmt = "yuvj420p"
            for samples, elapsed in self.pending_audio:
                self.write_audio(samples, elapsed)
            self.pending_audio.clear()
            self.pending_bytes = 0
            logging.info("Recording to %s", self.path)
        except Exception:
            self.close()
            raise

    def audio(self, samples):
        elapsed = self.elapsed()
        if self.container is None:
            # At most ~30 s before video arrives. Do not silently lose recordings.
            if self.pending_bytes + len(samples) > AUDIO_RATE * 2 * 30:
                raise OSError("Recording received 30 seconds of audio without video")
            self.pending_audio.append((samples, elapsed))
            self.pending_bytes += len(samples)
        else:
            self.write_audio(samples, elapsed)

    def write_audio(self, samples, elapsed):
        import av

        packet = av.Packet(samples)
        packet.stream = self.audio_stream
        packet.time_base = Fraction(1, AUDIO_RATE)
        packet.pts = packet.dts = max(self.audio_end, round(elapsed * AUDIO_RATE) - len(samples) // 2)
        packet.duration = len(samples) // 2
        self.audio_end = packet.pts + packet.duration
        self.container.mux(packet)

    def video(self, jpeg, size):
        import av

        elapsed = self.elapsed()
        if self.container is None:
            self.open(size)
        packet = av.Packet(jpeg)
        packet.stream = self.video_stream
        packet.time_base = Fraction(1, 1000000)
        self.video_pts = max(self.video_pts + 1, round(elapsed * 1000000))
        packet.pts = packet.dts = self.video_pts
        self.container.mux(packet)

    def close(self):
        if self.container is None and self.pending_audio and self.file is None:
            self.open()  # Preserve an audio-only connection too.
        try:
            if self.container is not None:
                self.container.close()
        finally:
            if self.file is not None:
                self.file.close()
        self.container = None
