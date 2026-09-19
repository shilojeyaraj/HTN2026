"""One request/reply at a time: uint32 big-endian length, then JPEG or JSON."""

import struct

MAX_FRAME = 2 * 1024 * 1024
MAX_RESULT = 8192


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
