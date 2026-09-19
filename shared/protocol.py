"""Full-duplex TCP: uint32 length + JPEG or PCM1/audio upstream, JSON downstream.

Depth replies identify the 1-based received frame_id; unsampled frames have no reply.
"""

import struct

MAX_FRAME = 2 * 1024 * 1024
MAX_RESULT = 8192
AUDIO_PREFIX = b"PCM1"
AUDIO_RATE = 16000
AUDIO_CHUNK = 640  # 20 ms, mono signed 16-bit little-endian PCM.


def audio_samples(payload):
    samples = payload[len(AUDIO_PREFIX):]
    if not payload.startswith(AUDIO_PREFIX) or not 0 < len(samples) <= AUDIO_CHUNK or len(samples) % 2:
        raise ValueError("invalid PCM audio packet")
    return samples


def recv_exact(sock, size):
    data = bytearray()
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise EOFError("connection closed")
        data.extend(chunk)
    return bytes(data)


def receive(sock, limit):
    size = struct.unpack("!I", recv_exact(sock, 4))[0]
    if not 0 < size <= limit:
        raise ValueError(f"invalid message length: {size}")
    return recv_exact(sock, size)


def send(sock, payload, limit):
    if not 0 < len(payload) <= limit:
        raise ValueError("message too large or empty")
    sock.sendall(struct.pack("!I", len(payload)) + payload)
