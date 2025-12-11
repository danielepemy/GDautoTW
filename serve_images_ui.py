#!/usr/bin/env python3
"""
Tiny Tkinter UI that serves the local ./images directory and exposes it via ngrok.
Close the window (or press Ctrl+C) to stop the HTTP server and tunnel.
"""

from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import unquote
import signal
import sys
import tkinter as tk
from tkinter import ttk
import webbrowser

from pyngrok import ngrok


IMAGES_DIR = Path(__file__).resolve().parent / "images"
PORT = 8080
BIND_HOST = "127.0.0.1"


class ImageHandler(SimpleHTTPRequestHandler):
    """Restrict every request to the images directory."""

    def translate_path(self, path):
        clean = unquote(path.split("?", 1)[0].split("#", 1)[0])
        parts = [p for p in clean.strip("/").split("/") if p not in ("", ".", "..")]
        return str(IMAGES_DIR.joinpath(*parts))


class ImageServerApp:
    def __init__(self):
        if not IMAGES_DIR.exists():
            raise SystemExit(f"Images directory not found: {IMAGES_DIR}")

        self.server = ThreadingHTTPServer((BIND_HOST, PORT), ImageHandler)
        self.server_thread = Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()

        tunnel = ngrok.connect(addr=PORT, proto="http", bind_tls=True)
        public_url = tunnel.public_url
        if public_url.startswith("http://"):
            # Force HTTPS so browsers treat the URL as a secure origin.
            public_url = "https://" + public_url[len("http://") :]
        self.public_url = public_url
        self.tunnel_name = tunnel.name

        self.root = tk.Tk()
        self.root.title("Image Server")
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        ttk.Label(self.root, text=f"Local server: http://{BIND_HOST}:{PORT}").pack(
            anchor="w", padx=10, pady=(10, 0)
        )
        ttk.Label(self.root, text=f"Public HTTPS URL: {self.public_url}").pack(
            anchor="w", padx=10, pady=(0, 10)
        )

        ttk.Label(self.root, text="Image URLs:").pack(anchor="w", padx=10)
        self.listbox = tk.Listbox(self.root, width=80)
        self.listbox.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.urls = []
        for file in sorted(IMAGES_DIR.iterdir()):
            if file.is_file():
                url = f"{self.public_url}/{file.name}"
                self.urls.append(url)
                self.listbox.insert(tk.END, f"{file.name} -> {url}")

        self.context_menu = tk.Menu(self.root, tearoff=0)
        self.context_menu.add_command(label="Open URL", command=self.open_selected)
        self.context_menu.add_command(label="Copy URL", command=self.copy_selected)
        self.listbox.bind("<Double-Button-1>", self.open_selected)
        self.listbox.bind("<Return>", self.open_selected)
        self.listbox.bind("<Button-3>", self.show_context_menu)
        self.listbox.bind("<Control-Button-1>", self.show_context_menu)

    def on_close(self):
        ngrok.disconnect(self.tunnel_name)
        self.server.shutdown()
        self.server.server_close()
        self.root.destroy()

    def _selected_url(self):
        selection = self.listbox.curselection()
        if not selection:
            return None
        index = selection[0]
        if 0 <= index < len(self.urls):
            return self.urls[index]
        return None

    def open_selected(self, event=None):
        url = self._selected_url()
        if url:
            webbrowser.open(url)
        return "break"

    def copy_selected(self, event=None):
        url = self._selected_url()
        if url:
            self.root.clipboard_clear()
            self.root.clipboard_append(url)
        return "break"

    def show_context_menu(self, event):
        index = self.listbox.nearest(event.y)
        if index >= 0:
            self.listbox.selection_clear(0, tk.END)
            self.listbox.selection_set(index)
            self.listbox.activate(index)
        try:
            self.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.context_menu.grab_release()
        return "break"

    def run(self):
        print(f"Serving {IMAGES_DIR} on http://{BIND_HOST}:{PORT}")
        print(f"Public ngrok URL: {self.public_url}")
        self.root.mainloop()


def main():
    app = ImageServerApp()

    def handle_interrupt(signum, frame):
        del signum, frame
        app.on_close()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_interrupt)
    app.run()


if __name__ == "__main__":
    main()
