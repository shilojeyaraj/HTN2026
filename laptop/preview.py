"""Native desktop preview; network and inference stay off the UI thread."""

from collections import deque
import logging
import threading
import time
import tkinter as tk

from PIL import ImageTk


def run_preview(serve):
    root = tk.Tk()
    root.title("Pi camera — live preview")
    root.withdraw()  # Open automatically on the first received frame.
    label = tk.Label(root)
    label.pack()
    caption = tk.Label(root, text="Waiting for speech…", wraplength=640, justify="left")
    caption.pack(fill="x")
    transcripts = deque(maxlen=1)
    pending = deque(maxlen=1)  # Display only the newest frame, never build a backlog.
    frames = 0
    measured_at = time.monotonic()

    def worker():
        try:
            serve(pending.append, transcripts.append)
        except Exception as exc:
            logging.exception("Camera server stopped")
            pending.append(f"Server stopped: {exc}")

    def update():
        nonlocal frames, measured_at
        if transcripts:
            transcript = transcripts.popleft()
            text = transcript["text"]
            if transcript.get("error"):
                text = "Transcription failed — listening…"
            caption.configure(text=text if transcript["final"] else f"{text} … (provisional)")
        try:
            frame = pending.popleft()
        except IndexError:
            pass
        else:
            if frame is None or isinstance(frame, str):
                label.configure(image="", text=frame or "Pi disconnected — waiting for frames")
                label.image = None
                root.title("Pi camera — disconnected" if frame is None else "Pi camera — error")
                frames = 0
                measured_at = time.monotonic()
            else:
                photo = ImageTk.PhotoImage(frame)
                label.configure(image=photo, text="")
                label.image = photo
                frames += 1
                now = time.monotonic()
                if now - measured_at >= 1:
                    root.title(f"Pi camera — {frames / (now - measured_at):.1f} display FPS")
                    frames = 0
                    measured_at = now
            root.deiconify()
        root.after(30, update)

    threading.Thread(target=worker, daemon=True).start()
    root.after(30, update)
    root.bind("<Escape>", lambda event: root.destroy())
    try:
        root.mainloop()
    except KeyboardInterrupt:
        root.destroy()
