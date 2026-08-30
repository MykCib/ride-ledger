# XOSS Ride Ledger

Downloads XOSS G-933835 workouts over Bluetooth LE and provides a local route
analytics dashboard. The dashboard reads FIT files, caches historical weather,
and does not modify the device.

Download the G-933835 ride index and FIT files:

```sh
mkdir -p data
../.venv/bin/python host/xoss_sync.py
```

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
.venv/bin/python -m flask --app web.app run --host 0.0.0.0 --port 8124
```

Open `http://localhost:8124` or `http://SERVER-IP:8124`. The app reads the
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

The dashboard needs only the downloaded FIT files and the Python packages
installed in `.venv`.

## Docker Dashboard

The web dashboard can run independently in Docker. The host only needs Docker
and the downloaded `data/` directory:

```sh
cd ~/www/xoss-uno-r4
systemctl --user disable --now ride-ledger.service  # if the native service is enabled
docker compose up -d --build
```

Open `http://SERVER-IP:8124`. The XOSS watcher continues to run separately on
the host and writes new FIT files into `data/`. The dashboard writes only its
derived JSON caches there and never modifies FIT files. Restarting the
container is not required for new workouts.

View dashboard logs:

```sh
docker compose logs -f ride-ledger
```

Stop the dashboard:

```sh
docker compose down
```

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
.venv/bin/pip install bleak fitparse
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
