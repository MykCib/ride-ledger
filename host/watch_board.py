#!/usr/bin/env python3
"""Watch for the UNO R4 BLE bridge and sync newly recorded rides."""

import os
import subprocess
import sys
import time
from pathlib import Path

try:
    from .board_sync import BoardSyncError, sync as sync_board
except ImportError:
    from board_sync import BoardSyncError, sync as sync_board


RETRY_SECONDS = float(os.environ.get("XOSS_RETRY_SECONDS", "60"))
COOLDOWN_SECONDS = float(os.environ.get("XOSS_COOLDOWN_SECONDS", "3600"))


def sync_cycle(root, python, weather):
    sync_failed = False
    try:
        new_files = list(sync_board())
    except BoardSyncError as error:
        sync_failed = True
        new_files = list(error.downloaded_files)
        print(f"Sync failed: {error}", file=sys.stderr, flush=True)
    except Exception as error:
        print(f"Watcher error: {error}", file=sys.stderr, flush=True)
        return RETRY_SECONDS

    if not new_files:
        if not sync_failed:
            print("Sync complete: no new FIT files", flush=True)
        return RETRY_SECONDS

    if sync_failed:
        print(f"Sync saved {len(new_files)} new FIT file(s) before failure", flush=True)
    else:
        print(f"Sync complete: {len(new_files)} new FIT file(s)", flush=True)
    try:
        result = subprocess.run([str(python), str(weather), *new_files], cwd=root)
        print(f"Weather enrichment exited with status {result.returncode}", flush=True)
    except Exception as error:
        print(f"Weather enrichment error: {error}", file=sys.stderr, flush=True)

    print(f"XOSS polling paused for {COOLDOWN_SECONDS:g} seconds", flush=True)
    return COOLDOWN_SECONDS


def main():
    root = Path(__file__).resolve().parent.parent
    python = root / ".venv" / "bin" / "python"
    weather = root / "host" / "weather_cache.py"
    print("Watching for XOSS through UNO R4 WiFi", flush=True)

    while True:
        time.sleep(sync_cycle(root, python, weather))


if __name__ == "__main__":
    main()
