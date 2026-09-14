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

Open `http://localhost:8124` or `http://SERVER-IP:8124`. The dashboard polls the
lightweight `/api/status` endpoint every 10 seconds and reloads data only when
the ride count or file timestamps change; `Refresh` can be used for an
immediate check. An “Indexing new ride…” badge appears while the background
indexer is working.

## Ride Index (SQLite)

FIT parsing happens once per file in a background indexer, not on every API
request. Derived analytics are served from `data/ledger.db` (SQLite, stdlib
only — no new dependencies):

```sh
.venv/bin/python -m host.indexer --full        # rebuild everything (run once after upgrading)
.venv/bin/python -m host.indexer --incremental # upsert new/changed files only (default)
.venv/bin/python -m host.indexer --check       # exit 0 if the DB covers all FITs, else 2
.venv/bin/python -m host.indexer --ride <id>   # re-ingest a single ride
```

The XOSS watcher runs `--incremental` automatically after each sync (disable
with `INDEX_ON_SYNC=0`). New files are ingested incrementally, so API
responses stay in the millisecond range instead of re-parsing the archive.
`LEDGER_DB` overrides the database path (default `data/ledger.db`). If the
database is missing or stale, the API falls back to the legacy FIT-parsing
path automatically. Insights are additionally cached in
`data/ledger_insights_cache.json` so restarts stay fast.

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

Weather enrichment runs automatically for newly downloaded rides after the XOSS
watcher completes a sync. It uses the historical Open-Meteo archive and stores
one JSON cache file per ride in `data/weather_cache/`. To enrich existing rides
manually, run:

```sh
.venv/bin/python host/weather_cache.py
```

The watcher checks the XOSS through the bridge when no new FIT files are
available. When the device is reachable but idle it backs off exponentially
(60s, 2m, 4m, … up to 15 minutes) so repeated BLE connections don't keep it
awake. When the device is unreachable (asleep or switched off) scanning does
not wake it, so it keeps retrying every 60s up to 2 minutes and picks it up
within a couple of minutes of being switched on. Any new download resets the
backoff. After one or more new FIT files are downloaded, it closes the bridge
connection and pauses all XOSS polling for one hour to let the device sleep.
Set `XOSS_COOLDOWN_SECONDS` to change the cooldown, `XOSS_MAX_IDLE_SECONDS`
for the idle cap (default 900), and `XOSS_MAX_ASLEEP_SECONDS` for the
unreachable cap (default 120). Existing FIT files are skipped and do not
start the cooldown.

ArduinoBLE's scanner can silently wedge after several days of uptime: the
bridge still answers `PING` but never reports the XOSS. When the device stays
invisible for `XOSS_BOARD_RESET_AFTER` consecutive checks (default 5, `0`
disables) the watcher sends `RESET`, which reboots the UNO bridge and clears
the scanner.

To force a sync immediately (for example right after switching the XOSS on),
run a single cycle:

```sh
.venv/bin/python host/watch_board.py --once
```

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
