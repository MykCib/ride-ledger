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
MAX_IDLE_SECONDS = float(os.environ.get("XOSS_MAX_IDLE_SECONDS", "900"))
INDEX_ON_SYNC = os.environ.get("INDEX_ON_SYNC", "1").strip() not in ("0", "false", "no", "")

# Consecutive-cycle counters driving adaptive backoff. A successful BLE
# connection can keep the XOSS awake, so polling every 60s forever creates a
# loop: device wakes -> watcher connects within a minute -> device stays
# awake. Backing off while idle lets the device sleep; a missing device
# (asleep = desired state) is likewise left alone with growing intervals.
_idle_streak = 0
_fail_streak = 0


def _reset_backoff():
    global _idle_streak, _fail_streak
    _idle_streak = 0
    _fail_streak = 0


def _backoff_delay(streak):
    delay = RETRY_SECONDS * (2 ** min(streak, 10))
    return max(1.0, min(delay, MAX_IDLE_SECONDS))


def sync_cycle(root, python, weather, indexer=None):
    global _idle_streak, _fail_streak
    sync_failed = False
    try:
        new_files = list(sync_board())
    except BoardSyncError as error:
        sync_failed = True
        new_files = list(error.downloaded_files)
        print(f"Sync failed: {error}", file=sys.stderr, flush=True)
    except Exception as error:
        print(f"Watcher error: {error}", file=sys.stderr, flush=True)
        _idle_streak = 0
        delay = _backoff_delay(_fail_streak)
        _fail_streak += 1
        if delay > RETRY_SECONDS:
            print(f"Next check in {delay:g} seconds (backoff)", flush=True)
        return delay

    if not new_files:
        if not sync_failed:
            print("Sync complete: no new FIT files", flush=True)
            _fail_streak = 0
            delay = _backoff_delay(_idle_streak)
            _idle_streak += 1
            if INDEX_ON_SYNC:
                # Heal a stale index (e.g. from a past indexer failure).
                # No-op in milliseconds when everything is already indexed.
                try:
                    indexer_path = Path(indexer) if indexer else Path(root) / "host" / "indexer.py"
                    heal = subprocess.run(
                        [str(python), str(indexer_path), "--incremental", "--quiet"],
                        cwd=root,
                    )
                    if heal.returncode != 0:
                        print(f"Ride indexer exited with status {heal.returncode}", flush=True)
                except Exception as error:
                    print(f"Ride indexer error: {error}", file=sys.stderr, flush=True)
        else:
            # Device unreachable (usually asleep). Leave it alone longer.
            _idle_streak = 0
            delay = _backoff_delay(_fail_streak)
            _fail_streak += 1
        if delay > RETRY_SECONDS:
            print(f"Next check in {delay:g} seconds (backoff)", flush=True)
        return delay

    _reset_backoff()

    if sync_failed:
        print(f"Sync saved {len(new_files)} new FIT file(s) before failure", flush=True)
    else:
        print(f"Sync complete: {len(new_files)} new FIT file(s)", flush=True)
    try:
        result = subprocess.run([str(python), str(weather), *new_files], cwd=root)
        print(f"Weather enrichment exited with status {result.returncode}", flush=True)
    except Exception as error:
        print(f"Weather enrichment error: {error}", file=sys.stderr, flush=True)

    if INDEX_ON_SYNC:
        try:
            indexer_path = Path(indexer) if indexer else Path(root) / "host" / "indexer.py"
            index_result = subprocess.run(
                [str(python), str(indexer_path), "--incremental"], cwd=root
            )
            print(f"Ride indexer exited with status {index_result.returncode}", flush=True)
        except Exception as error:
            print(f"Ride indexer error: {error}", file=sys.stderr, flush=True)

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
