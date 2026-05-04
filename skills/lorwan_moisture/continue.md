# lorwan_moisture — continue

## Where we are

Directory has been pruned to Python only. Sole file:
- `main.py` — `LoranStorageInterface` class (TTN v3 storage API client) + `if __name__ == "__main__"` test driver. Pure stdlib (`urllib.request`).

Everything Go/C/Arduino/build-related has been removed (Dockerfile, Makefile, `WioTerminal-LoRaWAN-Gateway-Tester/`, `cli/`, `loran_storage_interface/`, `generate_time_field.go`, `loran_secrets.go`, `main.go`, the Go binaries, the `.bsh` scripts). Reference data (`data.txt`, `log_data/`) was removed too.

A nested foreign `.git` (under the deleted Arduino dir) was also removed earlier in the session — parent `/home/gedgar/robot_person` repo can now track normally.

## What we verified about the data stream

TTN uplinks for app `seeedec` carry SenseCAP S2105 soil sensors. Three devices observed: `lacima1c`, `lacima1d`, `lacamia1b` (note the typo in 1b's device_id).

Decoded payload contains three measurements per uplink:
- **measurementId 4108** = volumetric water content (m³/m³)
- **measurementId 4102** = soil temperature (°C)
- **measurementId 4103** = soil EC (mS/cm)

Frame layout (per measurement, repeating in the hex frm_payload):
`01` (channel) + `<id LE u16>` + `10` (type) + `<value LE i32, scaled ×1000>`

RF/gateway metadata lives in `rx_metadata[0]` and `settings`: gateway_id, gateway_eui, lat/lon/alt, rssi, channel_rssi, snr, frequency, spreading_factor, bandwidth, coding_rate, consumed_airtime, packet_error_rate.

## The task — pick up here

Convert this into **two leaf functions for the python robot** (behavior-tree leaves). Glenn's spec, verbatim:

> create a sqlite database of two tables — moisture data and link data. If the database is set up then the initialization is skipped. The main function will take a tick event and capture the last 24 hours of data, not to overwrite if already there. There is a second leaf function that will take the database and extract information based on sql parameters in the node data. The storage will be a python dictionary at a blackboard location specified in the leaf node.

### Leaf 1 — fetcher
- Init: open `db_path` (from node_data), create `moisture` and `link` tables if absent. Skip if schema present.
- Tick: query TTN with `after = now - 24h`, parse each `result` line, INSERT OR IGNORE rows.
- Idempotency via primary keys (proposed): `moisture(device_id, received_at, measurement_id)`, `link(device_id, received_at)`.

### Leaf 2 — query
- Reads `sql` (and bind params) from node_data.
- Executes against the same sqlite DB.
- Writes result dict to blackboard at `bb_key` from node_data.

## Open questions for Glenn (asked at end of last session, NOT YET ANSWERED — start the next session by getting these answered before coding)

1. **Leaf signature in this python-robot** — `def tick(blackboard, node_data) -> Status`? Class-based with `__init__(node_data)` + `tick(blackboard)`? Separate `setup()` call, or "first-tick-does-init"? Pointing at an existing leaf in the python-robot repo would resolve this fastest.
2. **node_data shape** — is it a plain dict from YAML/CFL? Confirm the fields I'll consume:
   - fetcher: `db_path`, `ttn_url_base`, `ttn_app`, `ttn_password`, `ttn_url_after`, `lookback_hours` (default 24)
   - query: `db_path`, `sql`, `params`, `bb_key`
3. **Table split confirmation**:
   - `moisture(device_id, received_at, measurement_id, value, type, f_cnt)` PK `(device_id, received_at, measurement_id)`
   - `link(device_id, received_at, gateway_id, rssi, snr, frequency, spreading_factor, bandwidth, coding_rate, airtime_s, packet_error_rate)` PK `(device_id, received_at)`
4. **Query-leaf output shape** — `{"columns": [...], "rows": [[...]]}`, list-of-dicts `[{col:val,...}]`, or something else other leaves already use?

## Reference: blackboard discipline

From auto-memory: chain_tree blackboard is **user-only** — engine builtins must not write. These leaves are user leaves writing to a user-supplied `bb_key`, which is fine. (s_engine has a different rule — its dictionary IS the working memory, so operator writes there are expected. Don't conflate the two.)

## Working TTN credentials (from old main.go, currently embedded in main.py)

- url_base: `https://nam1.cloud.thethings.network/api/v3/as/applications/`
- app_name: `seeedec`
- url_after: `/packages/storage/uplink_message?`
- password (Bearer): `NNSXS.5N2DRLTP3QD4SNMBXNWXZ6V3SMPEGXSW6JOT25I.7VUBLSUKWWEK4KAQUY3SP66Z6YHLQQVMRIKTWL2I7GH4GNRHETIA`

These should move into node_data (or a secrets file referenced from node_data) rather than living in code — flag this when wiring the fetcher leaf.

## Next session — recommended first move

Ask Glenn the four open questions above (or have him point at an existing python-robot leaf). Don't start coding the leaves until the interface is pinned down.
