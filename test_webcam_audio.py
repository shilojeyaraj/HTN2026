"""End-to-end FFmpeg A/V check with synthetic inputs and a stub transcriber."""

import shutil
import socket
import subprocess
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from laptop.audio import audio_transcription
from laptop.server import handle_connection
from pi.client import stream


@unittest.skipUnless(shutil.which("ffmpeg"), "requires ffmpeg")
class WebcamAudioTest(unittest.TestCase):
    def test_video_audio_transcription_and_cleanup(self):
        real_popen = subprocess.Popen
        frames, audio, results, errors, processes, transcripts = [], [], [], [], [], []

        def capture_process(command, **kwargs):
            # Replace only physical input devices; use real encoders, pipes,
            # TCP framing and receiver. Stub only speech model inference.
            base = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-re", "-f", "lavfi", "-i"]
            if "v4l2" in command:
                command = base + ["testsrc=size=640x480:rate=15", "-t", "5", "-c:v", "mjpeg",
                                  "-threads", "1", "-f", "mjpeg", "-flush_packets", "1", "pipe:1"]
            elif "alsa" in command:
                command = base + ["sine=frequency=440:sample_rate=16000", "-t", "5", "-ac", "1",
                                  "-c:a", "pcm_s16le", "-f", "s16le", "-flush_packets", "1", "pipe:1"]
            process = real_popen(command, **kwargs)
            processes.append(process)
            return process

        client, server = socket.socketpair()
        client.settimeout(5)
        server.settimeout(5)

        def serve():
            try:
                with server, audio_transcription(lambda pcm: "test speech", transcripts.append) as submit:
                    def receive_audio(samples):
                        audio.append(samples)
                        submit(samples)
                    handle_connection(server, None, frames.append, receive_audio)
            except (EOFError, BrokenPipeError, ConnectionResetError):
                pass
            except Exception as exc:
                errors.append(exc)

        def result_received(line, **kwargs):
            results.append(line)
            if len(results) >= 30 and len(audio) >= 50:
                raise KeyboardInterrupt  # Exercise normal client Ctrl+C cleanup.

        worker = threading.Thread(target=serve, daemon=True)
        with patch("pi.client.subprocess.Popen", side_effect=capture_process):
            worker.start()
            try:
                with client, patch("builtins.print", side_effect=result_received):
                    stream(client, SimpleNamespace(image=None, once=False, fps=15, quality=70, timeout=5,
                           no_audio=False, input_format="mjpeg", width=640, height=480,
                           video_device="/dev/video0", audio_device="default"))
            except KeyboardInterrupt:
                pass
            finally:
                client.close()
                worker.join(6)
                leaked = [process for process in processes if process.poll() is None]
                for process in leaked:
                    process.kill()
                    process.wait()
        self.assertFalse(worker.is_alive())
        self.assertFalse(errors)
        self.assertGreaterEqual(len(frames), 30)
        self.assertGreaterEqual(len(audio), 50)
        self.assertEqual(len(processes), 2)
        self.assertTrue(transcripts[-1]["final"])
        self.assertEqual(transcripts[-1]["text"], "test speech")
        self.assertFalse(leaked, "capture process leaked")


if __name__ == "__main__":
    unittest.main()
