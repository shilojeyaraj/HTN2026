"""Local speech transcription, independently of video reception and depth."""

from collections import deque
from contextlib import contextmanager
import logging
import os
from pathlib import Path
import threading

import numpy as np

from shared.protocol import AUDIO_RATE


def load_transcriber(model_name, cache_dir):
    # The download cache also needs a writable Xet cache when HF_HOME is /opt.
    os.environ.setdefault("HF_XET_CACHE", str(Path(cache_dir).resolve() / "xet"))
    from faster_whisper import WhisperModel

    model = WhisperModel(model_name, device="cpu", compute_type="int8",
                         cpu_threads=2, download_root=str(cache_dir))

    def transcribe(pcm):
        audio = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768
        segments, _ = model.transcribe(audio, beam_size=1, vad_filter=True,
                                       condition_on_previous_text=False)
        return " ".join(segment.text.strip() for segment in segments).strip()

    return transcribe


@contextmanager
def audio_transcription(transcribe, on_text, threshold=0.015):
    """Finish utterances after 0.7 s of quiet; cap them at 10 s and RAM at two queued clips."""
    if transcribe is None:
        yield lambda samples: None
        return
    pending = deque(maxlen=2)
    preroll = deque(maxlen=10)  # 200 ms at the current 20 ms packet size.
    utterance = bytearray()
    quiet = voiced = 0
    condition = threading.Condition()
    stopped = False

    def finish():
        nonlocal quiet, voiced
        if voiced >= int(AUDIO_RATE * 0.2):
            with condition:
                if len(pending) == pending.maxlen:
                    logging.warning("Transcription overloaded: dropping oldest pending utterance")
                pending.append(bytes(utterance))
                condition.notify()
        utterance.clear()
        quiet = voiced = 0

    def submit(samples):
        nonlocal quiet, voiced
        values = np.frombuffer(samples, dtype="<i2").astype(np.float32) / 32768
        speech = float(np.sqrt(np.mean(values * values))) >= threshold
        # ponytail: RMS gate needs tuning for noisy rooms; replace with streaming
        # neural VAD if quiet speech/noise cannot be separated by the threshold.
        if speech:
            if not utterance:
                utterance.extend(b"".join(preroll))
                preroll.clear()
            voiced += len(values)
            quiet = 0
        elif not utterance:
            preroll.append(samples)
            return
        else:
            quiet += len(values)
        utterance.extend(samples)
        if quiet >= int(AUDIO_RATE * 0.7) or len(utterance) >= AUDIO_RATE * 2 * 10:
            finish()

    def recognize():
        while True:
            with condition:
                condition.wait_for(lambda: pending or stopped)
                if not pending:
                    return
                pcm = pending.popleft()
            try:
                text = transcribe(pcm)
                if text:
                    on_text(text)
            except Exception:
                logging.exception("Transcription failed; continuing with the next utterance")

    worker = threading.Thread(target=recognize, daemon=True)
    worker.start()
    try:
        yield submit
    finally:
        finish()  # Flush speech on disconnect, without mixing different connections.
        with condition:
            stopped = True
            condition.notify()
        worker.join()
