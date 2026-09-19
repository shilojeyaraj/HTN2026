"""Native desktop preview; network and inference stay off the UI thread."""

from collections import deque
import logging
import threading
import tkinter as tk

from PIL import ImageTk


def run_preview(serve):
    root = tk.Tk()
    root.title("Pi camera — live preview")
    root.withdraw()  # Open automatically on the first received frame.
    label = tk.Label(root)
    label.pack()
    pending = deque(maxlen=1)  # Display only the newest frame, never build a backlog.

    def worker():
        try:
            serve(pending.append)
        except Exception as exc:
            logging.exception("Camera server stopped")
            pending.append(f"Server stopped: {exc}")

    def update():
        try:
            frame = pending.popleft()
        except IndexError:
            pass
        else:
            if frame is None or isinstance(frame, str):
                label.configure(image="", text=frame or "Pi disconnected — waiting for frames")
                label.image = None
            else:
                photo = ImageTk.PhotoImage(frame)
                label.configure(image=photo, text="")
                label.image = photo
            root.deiconify()
        root.after(30, update)

    threading.Thread(target=worker, daemon=True).start()
    root.after(30, update)
    root.bind("<Escape>", lambda event: root.destroy())
    try:
        root.mainloop()
    except KeyboardInterrupt:
        root.destroy()
