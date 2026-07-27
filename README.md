# Dawarich Home Assistant Integration

> [!IMPORTANT]
> Version 1.0.0 includes a **breaking change** that affects entity identifiers.
> [More Information](#upgrading-to-v100)

<!--toc:start-->
- [Dawarich Home Assistant Integration](#dawarich-home-assistant-integration)
  - [Install](#install)
    - [Install with HACS](#install-with-hacs)
    - [Manual Installation](#manual-installation)
  - [Upgrading](#upgrading)
    - [Upgrading to v1.0.0](#upgrading-to-v100)
  - [Configuration](#configuration)
  - [Known Issues](#known-issues)
    - [Entity or Device not found in registry](#entity-or-device-not-found-in-registry)
<!--toc:end-->
---
> [!NOTE]
> This is an experimental integration for Dawarich, expect possibly breaking changes. This is a community integration, not affiliated with Dawarich.


[Dawarich](https://dawarich.app/) is a self-hosted Google Timeline alternative ([see](https://support.google.com/maps/answer/14169818?hl=en&co=GENIE.Platform%3DAndroid) why you would want to consider it).

This integration does two things, one of which is optional.
1. It provides statistics for your account. This includes total distance, number of cities visited, current Dawarich version, and more.
2. (optional) You can set a device tracker (such as a mobile phone) to send its data through Home Assistant to Dawarich. This way, you don't need another app and can instead use any existing location entities in Home Assistant.

## Install
There are two ways to install this. The easiest is with [HACS](https://hacs.xyz/).

### Install with HACS
Altough the below instructions might look complicated, they are rather simple.
1. Make sure you have HACS installed using [these instructions](https://hacs.xyz/docs/use/).
2. Click the button below to add the custom repository to HACS directly:\
   [![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=AlbinLind&repository=dawarich-home-assistant&category=integration)
3. Press the download button in the bottom right corner.
4. Restart Home Assistant.
5. Click the button below to configure the Dawarich integration:\
   [![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=dawarich)

### Manual Installation
Take the items under `custom_components/dawarich` and place them in the folder `homeassistant/custom_components/dawarich`.

## Upgrading

### Upgrading to v1.0.0

> [!IMPORTANT]
> Version 1.0.0 includes a **breaking change** that affects entity identifiers.

In version 1.0.0, we changed how device and entity unique IDs are generated. Previously, they were based on the API key, which caused issues when reconfiguring credentials. Now they use the stable config entry ID.

**If you are upgrading from a version earlier than 1.0.0**, you need to:

1. **Delete** the existing Dawarich integration from Home Assistant
   - Go to **Settings** → **Devices & Services** → **Dawarich**
   - Click the three dots menu (⋮) and select **Delete**
2. **Re-add** the integration
   - Click **Add Integration** and search for "Dawarich"
   - Enter your connection details and API key

> [!TIP]
> **Your history will be preserved!** When you re-add the integration with the same name, the new entity IDs will be generated based on the config entry ID. Since this creates the same entity IDs as before, Home Assistant will automatically reconnect your historical data to the new entities.

This is a one-time migration. After upgrading to 1.0.0, you can use the new **Reconfigure** option (⋮ menu → Reconfigure) to update your settings, including your API key, without losing your entities or history.

## Configuration
Below are the configuration options for the Dawarich Home Assistant integration. After configuration, input your Dawarich API key when prompted, which is available on the Dawarich account page.

- **Host:** hostname, IP address, or URL that resolves to the running Dawarich instance
- **Port:** port number for host
- **Name:** integration entry category to contain devices
- **Device Tracker:** device tracker to send data to Dawarich
- **Minimum distance:** meters the tracker must have moved since the last point sent before a state change is forwarded. Filters out attribute-only updates (battery, wifi, GPS jitter). Defaults to `100`, matching Dawarich's own `visit_radius_meters`. `0` disables it.
- **GPS accuracy threshold:** meters of reported GPS accuracy above which a state change is discarded — not sent and not counted as movement. **Defaults to `0` (disabled)**, because Dawarich applies its own `gps_accuracy_threshold` on ingest whenever `gps_filtering_enabled` is set. Only set this if you want a *stricter* limit than your server's; a looser one filters nothing. Heartbeats are deliberately exempt, so a device parked somewhere with a permanently poor fix still reports in.
- **Heartbeat interval:** minutes between location pushes while the device is active, independent of state changes. Defaults to `15`. `0` disables the heartbeat entirely.
- **Drop to idle heartbeat after:** minutes without real movement before the heartbeat slows to its idle cadence. Defaults to `30`. `0` disables the idle cadence.
- **Idle heartbeat interval:** minutes between pushes once the device is considered stationary. **Defaults to `0` (disabled)** — on a stock Dawarich there is no value that works. See [Splitting tracks during stays](#splitting-tracks-during-stays) before enabling it.

> [!WARNING]
> Minimum distance and the heartbeat are meant to be used together. Filtering state changes without a heartbeat to replace them leaves *larger* gaps than running neither, which makes visit fragmentation worse. If you set **Heartbeat interval** to `0`, set **Minimum distance** to `0` as well.
- **Use SSL:** check to use HTTPS (i.e. prepends url with `https`)
- **Verify SSL:** make sure secure connection is made through SSL

### Why the heartbeat exists

Home Assistant device trackers only update on zone transitions or significant movement, so long stationary periods send nothing to Dawarich. Combined with the minimum-distance filter — which by design drops the attribute-only updates that would otherwise have kept the stream alive — that silence can stretch for hours. The heartbeat guarantees a point every N minutes regardless, which is why the two settings are meant to be used together.

### Splitting tracks during stays

The idle cadence targets a second, separate problem: a heartbeat that never leaves a gap means a track never ends, so days of history collapse into one continuous track.

Dawarich's `Tracks::BoundaryDetector` only ends a track on a gap **larger than `max(minutes_between_routes, 30 minutes)`**, where `minutes_between_routes` is a per-user server setting. So to split a track during a stay, the idle interval must sit:

- **above** `max(minutes_between_routes, 30)` — otherwise the gap merges and nothing splits
- **at or below** `stay_max_gap_minutes` — otherwise the stay itself fragments into separate visits

> [!IMPORTANT]
> **On a stock Dawarich these two bounds leave no valid value.** Both `minutes_between_routes` and `stay_max_gap_minutes` default to `60`, so you would need an interval that is simultaneously above 60 and at or below 60. This is why the idle interval now defaults to `0` (disabled).
>
> To open a usable window, lower `minutes_between_routes` on the **server** (Dawarich → Settings, or `PATCH /api/v1/settings`). Setting it to `30` gives a 30-minute merge floor and a workable idle range of **31–60 minutes**.

The integration reads both values from your server at startup and logs a warning naming the exact problem if your configured idle interval can't work. Check the Home Assistant log after enabling it.

Because Dawarich only builds a track from segments of two or more points, isolated idle points don't produce spurious tracks of their own.

When the device starts moving again, the integration re-sends the **last stationary position** immediately before the first moving point. That closes the visit at the actual moment of departure rather than at the last idle heartbeat, and makes the new journey start from where it really began.

> [!IMPORTANT]
> **Don't raise "drop to idle heartbeat after" much beyond its default.** Dawarich puts no minimum distance or duration on a track — any two points close enough in time form one. Heartbeats fired at the *active* cadence while the device is already parked are closer together than the merge floor, so they land in the same segment as the journey that just ended and extend that track for as long as this setting lasts. At 120 minutes a 30 minute commute records as a 2.5 hour track sitting at home. The default of 30 minutes is long enough to establish the visit while keeping that tail short.

### What this integration cannot fix

Some fragmentation is decided entirely on the server, after the points arrive. If your stays are being chopped into fixed-length visits (for example a run of visits all exactly `stay_max_gap_minutes` long) while points are still flowing steadily, no client-side setting will change that — the input is already continuous. Verify by checking whether visit durations respond to changing the heartbeat interval; if they don't, the cause is server-side and belongs in Dawarich's settings or its issue tracker.

### Service: `dawarich.push_location`
Call this service against your Dawarich tracker sensor entity to push the current location on demand, for example from your own automation on a custom schedule.

## Known Issues
Below are some known issues that are being looked at, but with workarounds for the moment.

### Entity or Device not found in registry
This warning shows up because we are trying to determine if the device or entity
is disabled. If you change the name of the tracker sensor of Dawarich you will
get a warning. If you at the same time have disabled the entity then this will,
until you restart your home assistant instance, continue to send new locations.

