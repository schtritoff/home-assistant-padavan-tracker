# Home Assistant Padavan-ng Tracker

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![hacs_badge](https://img.shields.io/badge/Validate-With_hassfest-blue.svg)](https://github.com/home-assistant/ops/scripts/hassfest)

This custom device tracker integration shows **all connected LAN clients**
(wired and wireless behind the router) of **[padavan-ng](https://gitlab.com/hadzhioglu/padavan-ng)**
routers as `device_tracker` entities in Home Assistant.

This integration targets **padavan-ng** (the maintained fork) only — the old
Padavan firmware series (3.x "rt-n56u" on Bitbucket) is **not** supported: its
webUI platform names and API surface differ.

Tested with padavan-ng (hadzhioglu fork) on a D-Link DIR-860L and
Home Assistant 2026.8.

## Purpose

Show one `device_tracker` entity per client the router currently sees
(`/lan_clients.asp` client list), each grouped under a router device, so you
can automate on presence of any device. Each tracked device gets a registry
device entry with hostname/IP, and the tracker state carries hostname and IP
attributes. Clients go "Not home" as soon as their client-list entry is no
longer fresh (stale ARP entries are filtered out).

## Installation

### HACS (custom repository)

This integration is not in the HACS default store yet:

1. Open **HACS** in your Home Assistant sidebar.
2. Click the **⋮ (three dot menu) → Custom repositories**.
3. Paste `https://github.com/schtritoff/home-assistant-padavan-tracker`
   and set the category to **Integration**.
4. Click **Install** on *Padavan-ng Tracker*.
5. Restart Home Assistant when HACS prompts you.

### Manual

Copy `custom_components/padavan_tracker` into your Home Assistant
`config/custom_components/` folder and restart HA.

## Configuration (UI only)

1. Go to **Settings → Devices & services → Add integration** and pick
   **Padavan-ng Tracker**.
2. Fill in the router web-interface address (e.g. `http://192.168.2.1/` or
   `https://192.168.2.1/` if you enabled HTTPS), user name and password.
   If the router uses a self-signed certificate, keep
   **Verify TLS certificate** off.
3. All currently connected clients are tracked automatically; new clients
   appear as devices/entities when the router sees them.

The following can be changed in the integration's **Configure** dialog:

- **Scan interval** (default 300 s, 5-3600)
- **Consider home** (seconds after last seen before a device becomes "Not home";
  default 180 s)
- **Track devices without a hostname**
- **Require an IP address to track a device**

## Why not ...?

- [Nmap tracker](https://www.home-assistant.io/integrations/nmap_tracker/) -
  sleeping devices ignore ARP/pings for minutes, unreliable for phones.
- [Xiaomi tracker](https://www.home-assistant.io/integrations/xiaomi_miio/) -
  similar accuracy, but router-mode only.

## Useful links

- Firmware: https://gitlab.com/hadzhioglu/padavan-ng
