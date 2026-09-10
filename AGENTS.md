# AGENTS.md

Guidance for AI coding agents working on this repository.

## Project

Home Assistant custom integration `padavan_tracker` (HACS-installable) that
tracks clients connected to **padavan-ng**-firmware routers
(https://gitlab.com/hadzhioglu/padavan-ng). The integration targets padavan-ng
ONLY (the old Padavan 3.x series from Bitbucket is NOT supported; its platform
names/endpoints differ — keep the naming/docs differentiated).

- Live router on the test network: **D-Link DIR-860L** running **padavan-ng** (https://gitlab.com/hadzhioglu/padavan-ng) at `192.168.2.1`. Radios on the router are DISABLED; wireless is served by an external AP, so the tracker must report *all LAN clients* (wired + wireless behind the router).
- Real Home Assistant instance is on the LAN (URL + long-lived token in `.env`); verified target **HA 2026.8.3**.
- Target HA API surface is the *modern* integration style: config flow + `DataUpdateCoordinator` + `ScannerEntity` (reference pattern: `homeassistant/components/unifi_direct` on HA `dev`).

## Layout

```
custom_components/padavan_tracker/   # the integration (HACS: this folder)
  manifest.json                      # config_flow: true, version, iot_class local_polling
  const.py                           # DOMAIN, defaults, CONF_*, endpoint paths
  client.py                          # PadavanWebClient (aiohttp bridge, Basic Auth) + parsing + errors
  router.py                          # PadavanRouter central object (asuswrt-style): polling,
                                     #   PadavanDevInfo state, consider_home, device registry
  device_tracker.py                  # per-MAC ScannerEntity entities (asuswrt-style, dispatcher)
  config_flow.py                     # UI setup + options (scan_interval, consider_home,
                                     #   track_unknown, require_ip)
  strings.json / translations/en.json
_dev/                                # NOT shipped to HA; dev scripts + asuswrt reference copy
  test_api.py                        # fetches live client list using .env creds
.env                                 # SECRETS (router + HA). NEVER commit, NEVER print values.
```

## Router API notes (padavan-ng, ASUS-style webui)

- Auth: HTTP Basic (admin / password). httpd returns `Server: httpd`, 401 on bad creds.
- HTTPS: padavan uses a self-signed cert by default -> `PadavanRouter(verify_ssl=False)`
  (default) requests the TLS layer with `ssl=False` in aiohttp. `verify_ssl=True`
  verifies against the CA bundle. Config flow exposes the checkbox.
- Single-session quirk: only ONE web user at a time in old padavan; the type
  used here (hadzhioglu padavan-ng with `/lan_clients.asp`) does not enforce it
  against Basic Auth API polling, but avoid logins via the web UI while testing.
- `GET /lan_clients.asp` -> JS assignment containing TWO arrays:
  - `var ipmonitor_last = [["ip","mac","name","type","http","staled"], ...]`
    Types: "1"=PC, "2"=Router, "3"=AP, "5"=IP camera, "6"=Other. `staled=="1"`
    means expired/ghost entry -> must be filtered out for presence.
  - NOTE: only `ipmonitor_last` appears in `lan_clients.asp`; the page
    `device-map/clients.asp` embeds the same data as `var ipmonitor = ...`.
    Both are parsed by the regex in `client.py` (`ipmonitor(?:_last)?`).
- MAC formats: `ipmonitor` uses `AA:BB:CC:DD:EE:FF`; DHCP list (`m_dhcp` on
  other pages) uses colon-less uppercase. Always normalize via `normalize_mac`.
- Name can be `null` or `"*"` -> treat as no hostname.
- Main page: `index.html` (NOT `index.asp`). Redirect endpoints
  (`Main_WStatus2g_Content.asp` etc.) return "Radio X is disabled" when radios
  are off - do not use wireless-only endpoints.
- Wireless station list/RSSI (when radios are used): `var wireless = {MAC: RSSI}`
  map in `device-map/clients.asp` (empty when radios disabled).

## Conventions

- Modern HA style: `config_entry.runtime_data` holds the PadavanRouter object
  (asuswrt-style; no raw DataUpdateCoordinator), polling via
  `async_track_time_interval`, entity updates via dispatcher signals
  (`signal_device_new`/`signal_device_update`).
- No YAML platform support (`PLATFORM_SCHEMA` legacy scanners were removed from
  HA); configuration is UI-only. Unique id per entry = normalized host URL.
- Entity naming: `has_entity_name = True`, `_attr_name = None`, device name =
  hostname or MAC, `identifiers={(DOMAIN, mac)}`.
- Client list staleness: coordinator data contains ONLY non-staled clients.
- No third-party requirements (aiohttp ships with HA).
- Comments only where requested; no secrets in code or docs.

## Dev workflow

- Python 3.11 with `aiohttp` installed (`python -m pip install aiohttp`).
- Syntax check: `python -m compileall -q custom_components/padavan_tracker`
- Live API test: `python _dev/test_api.py` (expects `OK: N clients`).
- HA version check: `GET <ha_url>/api/config` with `Authorization: Bearer
  <ha_token>` from `.env` — read the `version` field (verified 2026.8.3).
- Deployment for real testing: copy `custom_components/padavan_tracker` into
  the assistant's config dir, then restart HA. (No SSH confirmed yet.)

## Gotchas

- Custom integrations hit a "Detected blocking call to import_module" warning
  when platforms are imported lazily inside `async_forward_entry_setups`.
  Fix: preload each platform module at the top of `__init__.py`
  (`from . import device_tracker  # noqa`) so it imports in the executor.
- `SOURCE_TYPE_ROUTER` no longer exists on `homeassistant.components.device_tracker`
  (it is `SourceType.ROUTER` now); `ScannerEntity` already defaults to
  `source_type = ROUTER`, so don't set it manually.
- `config_entries.OptionsFlow.config_entry` is a READ-ONLY property in recent
  HA (2025+); do NOT set it in `__init__` (500 on flow). Just define the class
  without `__init__`; the base sets `config_entry`/`handler` before steps run.
- Device registry entries are only created when the entity is FIRST added;
  entities created while device_info failed never group retroactively. If the
  user sees MAC-named orphan device_tracker entities with no device, they must
  delete the config entry (removes its entities) and re-add.
- Logs access for dev: websocket command `system_log/list` (50-entry buffer)
  is the only programmatic way in 2026.8 (`/api/error_log` and
  `subscribe_logs` are gone). Script: `_dev/get_logs.py`.
- `.env` key names are lowercase (`host`, `user`, `pass`, `ha_url`, `ha_token`).
- `ipmonitor` regex must stay non-greedy and DOTALL-aware; entries are
  JSON-compatible arrays (strings quoted, names may be `null`).
- aiohttp `ClientResponse` does not support `with resp:` on the installed
  version; use `resp.release()` or `async with` fetch helpers instead.
