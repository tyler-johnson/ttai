#!/usr/bin/env python3
"""Development script that auto-restarts the GUI on file changes."""

import os
import subprocess
import sys
import time
from pathlib import Path

try:
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer
except ImportError:
    print("Installing watchdog...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "watchdog"])
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer

# SSL configuration for development
SSL_DOMAIN = "tt-ai.dev"


class RestartHandler(FileSystemEventHandler):
    def __init__(self):
        self.process: subprocess.Popen | None = None
        self.restart_pending = False
        self.last_restart = 0

    def start_app(self):
        if self.process:
            self.process.terminate()
            self.process.wait()
        print("\n🚀 Starting TTAI GUI with MCP server...")
        env = os.environ.copy()
        env["TTAI_SSL_DOMAIN"] = SSL_DOMAIN
        self.process = subprocess.Popen(
            [sys.executable, "-m", "src.server.main", "--gui", "--transport", "sse"],
            cwd=Path(__file__).parent,
            env=env,
        )
        self.last_restart = time.time()

    def on_modified(self, event):
        if event.is_directory:
            return
        if not event.src_path.endswith(".py"):
            return
        # Debounce - don't restart more than once per second
        if time.time() - self.last_restart < 1:
            return
        print(f"📝 Changed: {event.src_path}")
        self.start_app()

    def stop(self):
        if self.process:
            self.process.terminate()
            self.process.wait()


def main():
    src_path = Path(__file__).parent / "src"

    handler = RestartHandler()
    observer = Observer()
    observer.schedule(handler, str(src_path), recursive=True)
    observer.start()

    print(f"👀 Watching {src_path} for changes...")
    handler.start_app()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n👋 Stopping...")
        handler.stop()
        observer.stop()
    observer.join()


if __name__ == "__main__":
    main()
