"""One-command launcher: starts the Quantis server and opens your browser.

    python serve.py
"""
import threading
import webbrowser

import uvicorn

URL = "http://127.0.0.1:8000"

if __name__ == "__main__":
    threading.Timer(1.5, lambda: webbrowser.open(URL)).start()
    print(f"\n  Quantis is starting -> {URL}  (Ctrl+C to stop)\n")
    uvicorn.run("server:app", host="127.0.0.1", port=8000, log_level="warning")
