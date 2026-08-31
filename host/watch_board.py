#!/usr/bin/env python3
"""Watch for the UNO R4 BLE bridge and sync newly recorded rides."""

import os
import subprocess
import sys
import time
from pathlib import Path


RETRY_SECONDS = float(os.environ.get("XOSS_RETRY_SECONDS", "60"))


def main():
    root = Path(__file__).resolve().parent.parent
    python = root / ".venv" / "bin" / "python"
    sync = root / "host" / "board_sync.py"
    weather = root / "host" / "weather_cache.py"
    print("Watching for XOSS through UNO R4 WiFi", flush=True)

    while True:
        try:
            result = subprocess.run([str(python), str(sync)], cwd=root)
            print(f"Sync exited with status {result.returncode}", flush=True)
            if result.returncode == 0:
                subprocess.run([str(python), str(weather)], cwd=root)
        except Exception as error:
            print(f"Watcher error: {error}", file=sys.stderr, flush=True)
        time.sleep(RETRY_SECONDS)


if __name__ == "__main__":
    main()
