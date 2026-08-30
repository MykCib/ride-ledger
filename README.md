# XOSS G-933835 and Arduino UNO R4 WiFi

This project discovers a nearby XOSS BLE computer and performs read-only protocol
probes. It deliberately does not write settings or firmware.

## Build and upload

```sh
arduino-cli lib install ArduinoBLE
arduino-cli compile --fqbn arduino:renesas_uno:unor4wifi arduino/xoss_scanner
arduino-cli upload -p /dev/ttyACM0 --fqbn arduino:renesas_uno:unor4wifi arduino/xoss_scanner
arduino-cli monitor -p /dev/ttyACM0 -c baudrate=115200
```

The computer must be in its Bluetooth connection/sync screen and disconnected
from the XOSS phone app while testing.

## Linux probe

The Python probe is useful for inspecting services and testing the same protocol
from the host computer. It requires `bleak` and accepts a device-name substring.

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install bleak
python host/xoss_probe.py 'XOSS G-933835'
```

Download the G-933835 ride index and FIT files:

```sh
mkdir -p data
../.venv/bin/python host/xoss_sync.py
```

The Arduino is not required for the homeserver. Any Linux computer with a
working Bluetooth LE adapter can connect directly to the XOSS. The UNO R4
scanner is kept separately for hardware experiments.

Run continuously as a user service on the homeserver:

```sh
mkdir -p ~/.config/systemd/user
cp systemd/xoss-watcher.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now xoss-watcher.service
journalctl --user -u xoss-watcher.service -f
```

Stop it with `systemctl --user disable --now xoss-watcher.service`.

## Workout Website

Start the dashboard directly during development:

```sh
cd ~/www/xoss-uno-r4
.venv/bin/python -m flask --app web.app run --host 0.0.0.0 --port 8080
```

Open `http://localhost:8080` or `http://SERVER-IP:8080`. The app reads the
FIT directory on every request, so press `Refresh` after the watcher downloads
a new ride.

Run the dashboard permanently as a user service:

```sh
mkdir -p ~/.config/systemd/user
cp systemd/ride-ledger.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now ride-ledger.service
journalctl --user -u ride-ledger.service -f
```

The dashboard does not need the Arduino. It needs only the downloaded FIT files
and Python packages installed in `.venv`.

Weather enrichment runs automatically after the XOSS watcher completes a sync.
It uses the historical Open-Meteo archive and stores one JSON cache file per
ride in `data/weather_cache/`. To enrich existing rides manually, run:

```sh
.venv/bin/python host/weather_cache.py
```

The watcher performs a 15-second BLE scan, then waits 60 seconds before the
next scan. After finding the computer, it runs the synchronizer and waits 60
seconds before checking again. It is safe to leave the XOSS active: existing
FIT files are skipped.

## Homeserver prerequisites

Install Python 3, a Bluetooth LE adapter, and Bluetooth service support. Then:

```sh
cd ~/www/xoss-uno-r4
python3 -m venv .venv
.venv/bin/pip install bleak
mkdir -p data ~/.config/systemd/user
cp systemd/xoss-watcher.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now xoss-watcher.service
```

The server user needs permission to access Bluetooth through BlueZ. Confirm
that scanning works with `bluetoothctl scan on` before starting the service.
Keep the XOSS disconnected from the phone app while it is syncing.

The public protocol implementation used as reference is:
https://github.com/ekspla/xoss_sync
