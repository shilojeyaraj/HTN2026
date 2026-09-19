"""Push-to-talk voice-in loop: waits for the button, records, transcribes, and sets a
wake event so the main episode loop reacts immediately instead of waiting for its next
scheduled tick (CLAUDE.md section 5, "Voice-in (event-driven)") -- this is what makes
voice feel real-time rather than laggy.
"""

import threading
import time

from brain.state import RobotState
from voice.stt import record_while_held, transcribe

# TODO: confirm the physical GPIO pin the push-to-talk button is wired to
# (CLAUDE.md section 8, chassis/wiring still open).
BUTTON_GPIO_PIN = 17
POLL_HZ = 20


def _gpio_is_held():
    from gpiozero import Button  # hardware import, deferred so this module still imports off-Pi

    button = Button(BUTTON_GPIO_PIN)
    return lambda: button.is_pressed


class PushToTalkLoop:
    def __init__(self, state: RobotState, wake_event: threading.Event, is_held=None):
        self.state = state
        self.wake_event = wake_event
        self.is_held = is_held or _gpio_is_held()

    def run_forever(self) -> None:
        period = 1.0 / POLL_HZ
        while True:
            if self.is_held():
                audio_path = record_while_held(self.is_held)
                self.state.last_user_command = transcribe(audio_path)
                self.wake_event.set()
            time.sleep(period)
