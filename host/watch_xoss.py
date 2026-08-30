#!/usr/bin/env python3
"""Watch for the XOSS computer and sync newly recorded rides."""

import asyncio
import os
import subprocess
import sys
from bleak import BleakScanner

TARGET = os.environ.get("XOSS_NAME", "XOSS G-933835")
SCAN_SECONDS = float(os.environ.get("XOSS_SCAN_SECONDS", "15"))
RETRY_SECONDS = float(os.environ.get("XOSS_RETRY_SECONDS", "60"))


async def find_xoss():
    devices = await BleakScanner.discover(timeout=SCAN_SECONDS)
    target = TARGET.lower()
    return next(
        (device for device in devices if target in (device.name or "").lower()),
        None,
    )


async def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data = os.path.join(root, "data")
    python = os.path.join(root, ".venv", "bin", "python")
    sync = os.path.join(root, "host", "xoss_sync.py")
    os.makedirs(data, exist_ok=True)
    print(f"Watching for {TARGET}", flush=True)

    while True:
        try:
            device = await find_xoss()
            if device:
                print(f"Found {device.name} at {device.address}; syncing", flush=True)
                result = subprocess.run([python, sync], cwd=data)
                print(f"Sync exited with status {result.returncode}", flush=True)
                weather = os.path.join(root, "host", "weather_cache.py")
                subprocess.run([python, weather], cwd=data)
                await asyncio.sleep(RETRY_SECONDS)
            else:
                print("XOSS not present", flush=True)
                await asyncio.sleep(RETRY_SECONDS)
        except Exception as error:
            print(f"Watcher error: {error}", file=sys.stderr, flush=True)
            await asyncio.sleep(RETRY_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())
