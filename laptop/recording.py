"""Optional per-session silent MP4, WAV, and finalized transcript files."""

from contextlib import ExitStack
from datetime import datetime, timezone
from fractions import Fraction
import logging
from pathlib import Path
import time
import wave

from shared.protocol import AUDIO_RATE


class Recording:
    def __init__(self, directory):
        name = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        self.path = Path(directory) / name
        self.path.mkdir(parents=True, exist_ok=False)
        self.resources = ExitStack()
        self.container = None
        self.stream = None
        self.started = None
        self.video_pts = -1
        try:
            self.wav = self.resources.enter_context(wave.open(str(self.path / "audio.wav"), "wb"))
            self.wav.setnchannels(1)
            self.wav.setsampwidth(2)
            self.wav.setframerate(AUDIO_RATE)
            self.text = self.resources.enter_context((self.path / "transcript.txt").open("x", encoding="utf-8"))
        except Exception:
            self.resources.close()
            raise
        logging.info("Recording to %s", self.path)

    def audio(self, samples):
        self.wav.writeframes(samples)

    def transcript(self, event):
        if event.get("final") and event.get("text") and not event.get("error"):
            self.text.write(event["text"].strip() + "\n")
            self.text.flush()

    def video(self, image):
        import av

        now = time.monotonic()
        if self.container is None:
            self.started = now
            self.container = av.open(str(self.path / "video.mp4"), mode="w", format="mp4")
            self.stream = self.container.add_stream("libx264", rate=30)
            # H.264 yuv420p needs even dimensions; usual 640x480 stays unchanged.
            self.stream.width = image.width + image.width % 2
            self.stream.height = image.height + image.height % 2
            self.stream.pix_fmt = "yuv420p"
            self.stream.codec_context.time_base = Fraction(1, 1000)
            self.stream.options = {"preset": "ultrafast", "tune": "zerolatency", "crf": "23"}
        frame = av.VideoFrame.from_image(image).reformat(
            width=self.stream.width, height=self.stream.height, format="yuv420p")
        self.video_pts = max(self.video_pts + 1, round((now - self.started) * 1000))
        frame.pts = self.video_pts
        frame.time_base = Fraction(1, 1000)
        for packet in self.stream.encode(frame):
            self.container.mux(packet)

    def close(self):
        try:
            if self.container is not None:
                try:
                    if self.stream is not None:
                        for packet in self.stream.encode():
                            self.container.mux(packet)
                finally:
                    self.container.close()
                    self.container = None
        finally:
            self.resources.close()
