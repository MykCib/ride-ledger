# XOSS Ride Ledger

Downloads XOSS G-933835 workouts over Bluetooth LE through an Arduino UNO R4
WiFi bridge and provides a local route analytics dashboard. The dashboard reads
FIT files, caches historical weather, and does not modify the device.

Download the G-933835 ride index and FIT files:

```sh
mkdir -p data
.venv/bin/python host/board_sync.py
```

The UNO R4 WiFi must remain connected by USB. The bridge is read-only and the
XOSS should be disconnected from the phone app while it is syncing.

## UNO R4 WiFi Bridge

Install the Arduino CLI and board support, then compile and upload the bridge:

```sh
arduino-cli core install arduino:renesas_uno
arduino-cli lib install ArduinoBLE
arduino-cli compile --fqbn arduino:renesas_uno:unor4wifi arduino/xoss-board
arduino-cli upload --port /dev/ttyACM0 --fqbn arduino:renesas_uno:unor4wifi arduino/xoss-board
```

The host user needs access to `/dev/ttyACM0` through the `dialout` group. The
service uses the stable `/dev/serial/by-id/` path automatically.

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

The dashboard frontend is a TypeScript React application. Build its static
assets after installing the Node dependencies and whenever the frontend source
changes:

```sh
npm install
npm run typecheck
npm run build
```

The Flask service serves the generated files from `web/static/dist/`. During
frontend development, run the API on port 8124 and the Vite server separately:

```sh
.venv/bin/python -m flask --app web.app run --host 0.0.0.0 --port 8124
npm run dev
```

The Vite development server proxies `/api` requests to Flask.

Ride details include elapsed time, moving time, moving share, estimated stopped
time, stop count, longest stop, and the detected stop intervals. Stopped time is
the FIT session's elapsed time minus moving time; individual intervals are
inferred from unchanged-distance timestamp gaps and sustained speeds at or
below 0.5 m/s, with intervals shorter than five seconds ignored.

Archive insights include the fastest rolling 1, 2, and 5 km sections, linked to
their source rides, plus a speed distribution based on recorded FIT samples.

Repeated rides are grouped by endpoints within 500 metres. The direction with
the earlier typical departure is labelled outbound and the reverse direction return.
Route cards show median departure and arrival times, average elapsed commute
duration, and distance spread. Endpoint labels start anonymous and can be renamed
in the stacked route map; names are stored locally by coordinate.
Commute times use `Europe/Vilnius` by default; set `RIDE_LEDGER_TIMEZONE` to an
IANA timezone to override it.

The dashboard also compares average speed with historical temperature, wind, and
precipitation, including dry-versus-wet and outbound-versus-return summaries.

Start the dashboard directly during development:

```sh
cd ~/www/ride-ledger
.venv/bin/python -m flask --app web.app run --host 0.0.0.0 --port 8124
```

Open `http://localhost:8124` or `http://SERVER-IP:8124`. The dashboard checks
for new FIT files automatically every minute; `Refresh` can be used for an
immediate check.

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
cd ~/www/ride-ledger
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

Install Python 3 and the Arduino UNO R4 WiFi USB bridge. Then:

```sh
cd ~/www/ride-ledger
python3 -m venv .venv
.venv/bin/pip install -r requirements-web.txt -r requirements-host.txt
mkdir -p data ~/.config/systemd/user
cp systemd/xoss-watcher.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now xoss-watcher.service
```

The server user needs permission to access the UNO serial port through the
`dialout` group. Keep the XOSS disconnected from the phone app while it is
syncing.

The public protocol implementation used as reference is:
https://github.com/ekspla/xoss_sync
