"""Play received PCM in memory without blocking video reception."""

from collections import deque
from contextlib import contextmanager
import logging
import subprocess
import threading

from shared.protocol import AUDIO_RATE


@contextmanager
def audio_playback(muted=False):
    if muted:
        yield lambda samples: None
        return
    player = subprocess.Popen([
        "ffplay", "-hide_banner", "-loglevel", "warning", "-nodisp", "-autoexit",
        "-f", "s16le", "-ar", str(AUDIO_RATE), "-ch_layout", "mono",
        "-probesize", "32", "-analyzeduration", "0", "-i", "pipe:0",
    ], stdin=subprocess.PIPE)
    # ponytail: independent audio/video clocks, suitable for monitoring; use a
    # timestamped media container if synchronized playback becomes necessary.
    pending = deque(maxlen=10)  # Bound Python-side audio buffering to 200 ms.
    condition = threading.Condition()
    stopped = False
    failure = []

    def play():
        try:
            while True:
                with condition:
                    condition.wait_for(lambda: pending or stopped)
                    if stopped:
                        return
                    samples = pending.popleft()
                player.stdin.write(samples)
                player.stdin.flush()
        except OSError as exc:
            failure.append(exc)
            logging.error("Audio playback failed: %s", exc)

    def submit(samples):
        if failure or player.poll() is not None:
            raise OSError("Audio player exited; check ffplay output or use --mute")
        with condition:
            pending.append(samples)
            condition.notify()

    worker = threading.Thread(target=play, daemon=True)
    worker.start()
    try:
        yield submit
    finally:
        with condition:
            stopped = True
            condition.notify()
        player.terminate()
        try:
            player.wait(timeout=2)
        except subprocess.TimeoutExpired:
            player.kill()
            player.wait()
        worker.join()
        try:
            player.stdin.close()
        except BrokenPipeError:
            pass
