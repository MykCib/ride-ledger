#!/usr/bin/env python3
"""Fetch XOSS files through the UNO R4 WiFi BLE bridge."""

import json
import os
import re
import sys
import time
from pathlib import Path

import serial


ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
BOARD_PORT = os.environ.get(
    "XOSS_BOARD_PORT",
    "/dev/serial/by-id/usb-Arduino_UNO_WiFi_R4_CMSIS-DAP_48CA435CF8F0-if01",
)
BAUD = 115200
LINE_TIMEOUT = 90
FIT_FILENAME = re.compile(r"[A-Za-z0-9_.-]+\.fit\Z")


class BoardSyncError(RuntimeError):
    def __init__(self, message, downloaded_files=()):
        super().__init__(message)
        self.downloaded_files = tuple(downloaded_files)


def read_line(port, timeout=LINE_TIMEOUT):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        line = port.readline()
        if line:
            return line
    raise BoardSyncError("timed out waiting for UNO response")


def read_exact(port, size):
    remaining = size
    deadline = time.monotonic() + max(60, size / 8000 + 60)
    while remaining:
        if time.monotonic() >= deadline:
            raise BoardSyncError(f"timed out receiving file ({remaining} bytes remain)")
        chunk = port.read(min(65536, remaining))
        if not chunk:
            continue
        yield chunk
        remaining -= len(chunk)


def fetch_file(port, filename, destination):
    port.write(f"GET {filename}\n".encode("ascii"))
    port.flush()

    while True:
        line = read_line(port)
        if line.startswith(b"#") or line in (b"READY\n", b"READY\r\n"):
            continue
        if line.startswith(b"ERR "):
            raise BoardSyncError(line.decode("utf-8", errors="replace").strip())
        if not line.startswith(b"FILE "):
            continue
        parts = line.decode("ascii", errors="strict").strip().split()
        if len(parts) != 3:
            raise BoardSyncError("invalid file header from UNO")
        received_name = parts[1]
        try:
            size = int(parts[2])
        except ValueError as error:
            raise BoardSyncError("invalid file size from UNO") from error
        if received_name != filename or size < 0:
            raise BoardSyncError("unexpected file header from UNO")
        break

    temporary = destination.with_name(destination.name + ".part")
    try:
        with temporary.open("wb") as output:
            for chunk in read_exact(port, size):
                output.write(chunk)
        if read_line(port).strip() != b"END":
            raise BoardSyncError("UNO did not finish the file transfer")
        os.replace(temporary, destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def close_board(port):
    try:
        port.write(b"CLOSE\n")
        port.flush()
    except (serial.SerialException, OSError):
        return


def fit_filenames(index_path):
    try:
        index = json.loads(index_path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise BoardSyncError(f"cannot parse {index_path.name}: {error}") from error

    if not isinstance(index, dict):
        raise BoardSyncError(f"{index_path.name} is not a JSON object")

    names = set()
    for workout in index.get("workouts", []):
        if isinstance(workout, list) and workout:
            filename = f"{workout[0]}.fit"
            if FIT_FILENAME.fullmatch(filename):
                names.add(filename)
    return sorted(names)


def sync():
    DATA.mkdir(exist_ok=True)
    downloaded_files = []
    port = None
    try:
        port = serial.Serial(BOARD_PORT, BAUD, timeout=1, write_timeout=5)
        port.reset_input_buffer()
        index_path = DATA / "workouts.json"
        fetch_file(port, "workouts.json", index_path)
        print(f"Downloaded {index_path.name}")

        for filename in fit_filenames(index_path):
            destination = DATA / filename
            if destination.exists():
                print(f"Skip: {filename}")
                continue
            fetch_file(port, filename, destination)
            downloaded_files.append(filename)
            print(f"Downloaded {filename}")
        return downloaded_files
    except BoardSyncError as error:
        error.downloaded_files = tuple(downloaded_files)
        raise
    except (serial.SerialException, OSError) as error:
        raise BoardSyncError(str(error), downloaded_files) from error
    except Exception as error:
        raise BoardSyncError(str(error), downloaded_files) from error
    finally:
        if port is not None:
            close_board(port)
            port.close()


if __name__ == "__main__":
    try:
        sync()
    except (BoardSyncError, serial.SerialException, OSError) as error:
        print(f"Board sync failed: {error}", file=sys.stderr)
        raise SystemExit(1)
