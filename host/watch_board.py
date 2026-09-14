#!/usr/bin/env python3
"""Watch for the UNO R4 BLE bridge and sync newly recorded rides."""

import os
import subprocess
import sys
import time
from pathlib import Path

try:
    from .board_sync import BoardSyncError, reset_board, sync as sync_board
except ImportError:
    from board_sync import BoardSyncError, reset_board, sync as sync_board


RETRY_SECONDS = float(os.environ.get("XOSS_RETRY_SECONDS", "60"))
COOLDOWN_SECONDS = float(os.environ.get("XOSS_COOLDOWN_SECONDS", "3600"))
MAX_IDLE_SECONDS = float(os.environ.get("XOSS_MAX_IDLE_SECONDS", "900"))
MAX_ASLEEP_SECONDS = float(os.environ.get("XOSS_MAX_ASLEEP_SECONDS", "120"))
BOARD_RESET_AFTER = int(os.environ.get("XOSS_BOARD_RESET_AFTER", "5"))
INDEX_ON_SYNC = os.environ.get("INDEX_ON_SYNC", "1").strip() not in ("0", "false", "no", "")

# Consecutive-cycle counters driving adaptive backoff. A successful BLE
# connection can keep the XOSS awake, so when the device is reachable but has
# nothing new we back off progressively to let it sleep. When the device is
# unreachable it is already asleep, and scanning does not wake it, so we keep
# retrying quickly to catch it as soon as the user turns it on.
_idle_streak = 0
_fail_streak = 0
_unavailable_streak = 0


def _reset_backoff():
    global _idle_streak, _fail_streak, _unavailable_streak
    _idle_streak = 0
    _fail_streak = 0
    _unavailable_streak = 0


def _maybe_reset_bridge(is_unavailable):
    """Reboot the bridge after repeated misses.

    ArduinoBLE's scan can wedge after several days of uptime: the firmware
    still answers PING but never reports the XOSS. A reboot clears it. Only a
    genuine "xoss-unavailable" counts; transport errors are left alone.
    """
    global _unavailable_streak
    if not is_unavailable or BOARD_RESET_AFTER <= 0:
        _unavailable_streak = 0
        return
    _unavailable_streak += 1
    if _unavailable_streak < BOARD_RESET_AFTER:
        return
    _unavailable_streak = 0
    try:
        if reset_board():
            print("Bridge scanner looked wedged; rebooted the UNO bridge", flush=True)
        else:
            print("Bridge did not acknowledge reset request", file=sys.stderr, flush=True)
    except Exception as error:
        print(f"Bridge reset error: {error}", file=sys.stderr, flush=True)


def _backoff_delay(streak, cap=None):
    delay = RETRY_SECONDS * (2 ** min(streak, 10))
    limit = MAX_IDLE_SECONDS if cap is None else cap
    return max(1.0, min(delay, limit))


def sync_cycle(root, python, weather, indexer=None):
    global _idle_streak, _fail_streak, _unavailable_streak
    sync_failed = False
    unavailable = False
    try:
        new_files = list(sync_board())
    except BoardSyncError as error:
        sync_failed = True
        unavailable = "xoss-unavailable" in str(error).lower()
        new_files = list(error.downloaded_files)
        print(f"Sync failed: {error}", file=sys.stderr, flush=True)
    except Exception as error:
        print(f"Watcher error: {error}", file=sys.stderr, flush=True)
        _idle_streak = 0
        delay = _backoff_delay(_fail_streak, cap=MAX_ASLEEP_SECONDS)
        _fail_streak += 1
        if delay > RETRY_SECONDS:
            print(f"Next check in {delay:g} seconds (backoff)", flush=True)
        return delay

    if not new_files:
        if not sync_failed:
            print("Sync complete: no new FIT files", flush=True)
            _fail_streak = 0
            _unavailable_streak = 0
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
            # Device unreachable (asleep/off or a wedged bridge scanner).
            # Keep retrying quickly so a freshly woken device is picked up
            # within a couple of minutes, and reboot the bridge if it stays
            # invisible for several cycles.
            _idle_streak = 0
            _maybe_reset_bridge(unavailable)
            delay = _backoff_delay(_fail_streak, cap=MAX_ASLEEP_SECONDS)
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


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(
        description="Watch for XOSS rides through the UNO R4 BLE bridge"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="run a single sync cycle now and exit (ignores cooldown/backoff)",
    )
    args = parser.parse_args(argv)

    root = Path(__file__).resolve().parent.parent
    python = root / ".venv" / "bin" / "python"
    weather = root / "host" / "weather_cache.py"

    if args.once:
        delay = sync_cycle(root, python, weather)
        print(f"Next scheduled check would be in {delay:g} seconds", flush=True)
        return 0

    print("Watching for XOSS through UNO R4 WiFi", flush=True)
    while True:
        time.sleep(sync_cycle(root, python, weather))


if __name__ == "__main__":
    raise SystemExit(main())
