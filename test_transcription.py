"""Speech segmentation and worker checks without model downloads."""

import threading
import unittest

import numpy as np

from laptop.audio import audio_transcription


class TranscriptionTest(unittest.TestCase):
    speech = np.full(320, 5000, dtype="<i2").tobytes()
    silence = bytes(640)

    def test_partial_before_pause_and_final_replaces_it(self):
        texts = []
        ready = threading.Event()

        def publish(event):
            texts.append(event)
            ready.set()

        with audio_transcription(lambda pcm: "hello", publish) as submit:
            for _ in range(40):
                submit(self.speech)
            self.assertTrue(ready.wait(1), "no provisional text during speech")
            self.assertFalse(texts[0]["final"])
            for _ in range(35):
                submit(self.silence)
        self.assertEqual([event["final"] for event in texts], [False, True])
        self.assertEqual([event["utterance_id"] for event in texts], [1, 1])

    def test_stale_partial_is_suppressed_and_finals_take_priority(self):
        busy, release = threading.Event(), threading.Event()
        texts, calls = [], []

        def transcribe(pcm):
            calls.append(pcm)
            if len(calls) == 1:
                busy.set()
                if not release.wait(2):
                    raise TimeoutError("test did not release partial")
            return "hello"

        with audio_transcription(transcribe, texts.append) as submit:
            try:
                for _ in range(40):
                    submit(self.speech)
                self.assertTrue(busy.wait(1))
                for _ in range(120):
                    submit(self.speech)  # Replace pending partials while one is active.
                for _ in range(35):
                    submit(self.silence)
                for _ in range(15):
                    submit(self.speech)
            finally:
                release.set()
        self.assertEqual([event["utterance_id"] for event in texts], [1, 2])
        self.assertTrue(all(event["final"] for event in texts))
        self.assertEqual(len(calls), 3)  # Stale active partial, then two finals.

    def test_silence_pause_and_disconnect(self):
        clips, texts = [], []

        def transcribe(pcm):
            clips.append(pcm)
            return "hello"

        with audio_transcription(transcribe, texts.append) as submit:
            for _ in range(100):
                submit(self.silence)
            for _ in range(15):
                submit(self.speech)
            for _ in range(35):
                submit(self.silence)
            for _ in range(15):
                submit(self.speech)
        self.assertEqual([event["text"] for event in texts], ["hello", "hello"])
        self.assertTrue(all(event["final"] for event in texts))
        self.assertEqual(len(clips[0]), (10 + 15 + 35) * 640)
        self.assertEqual(len(clips[1]), 15 * 640)

    def test_slow_inference_does_not_block_and_queue_is_bounded(self):
        busy, release = threading.Event(), threading.Event()
        texts = []

        def transcribe(pcm):
            busy.set()
            if not release.wait(3):
                raise TimeoutError("test inference was not released")
            return "speech"

        with audio_transcription(transcribe, texts.append) as submit:
            try:
                for _ in range(15):
                    submit(self.speech)
                for _ in range(35):
                    submit(self.silence)
                self.assertTrue(busy.wait(1))
                with self.assertLogs(level="WARNING"):
                    for _ in range(4):
                        for _ in range(15):
                            submit(self.speech)
                        for _ in range(35):
                            submit(self.silence)
            finally:
                release.set()
        self.assertEqual(len(texts), 3)  # One active clip and the newest two queued.

    def test_silence_disabled_and_long_speech(self):
        clips = []
        with audio_transcription(lambda pcm: clips.append(pcm) or "", lambda text: None, partial_interval=20) as submit:
            for _ in range(100):
                submit(self.silence)
        self.assertEqual(clips, [])
        with audio_transcription(None, lambda text: self.fail(text)) as submit:
            submit(self.speech)
        with audio_transcription(lambda pcm: clips.append(pcm) or "", lambda text: None, partial_interval=20) as submit:
            for _ in range(600):
                submit(self.speech)
        self.assertEqual([len(pcm) for pcm in clips], [320000, 64000])


if __name__ == "__main__":
    unittest.main()
