"""Thread-safe transcript buffer bridging laptop STT output to the brain loop.

The laptop runs faster-whisper locally and emits transcript events over TCP.
Whatever delivers those events (pi/client.py, an HTTP endpoint, etc.) pushes
into this buffer; the brain loop polls it each episode and uses the latest
final transcript as last_user_command.
"""

import threading
from collections import deque
from dataclasses import dataclass


@dataclass
class TranscriptEvent:
    text: str
    final: bool
    utterance_id: int


class TranscriptBuffer:
    def __init__(self, maxlen: int = 16):
        self._events: deque[TranscriptEvent] = deque(maxlen=maxlen)
        self._lock = threading.Lock()
        self._latest_final: TranscriptEvent | None = None

    def push(self, text: str, final: bool, utterance_id: int) -> None:
        with self._lock:
            self._events.append(TranscriptEvent(text, final, utterance_id))
            if final:
                self._latest_final = TranscriptEvent(text, final, utterance_id)

    def latest_final(self) -> TranscriptEvent | None:
        with self._lock:
            return self._latest_final

    def consume_final(self) -> str | None:
        with self._lock:
            if self._latest_final is not None:
                text = self._latest_final.text
                self._latest_final = None
                return text
            return None

    def recent(self, n: int = 5) -> list[TranscriptEvent]:
        with self._lock:
            return list(self._events)[-n:]
