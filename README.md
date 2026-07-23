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
- **Minimum distance:** if set to a value greater than 0 (meters), a state change is only sent to Dawarich if the tracker has moved at least that far since the last point that was sent. Defaults to `0` (disabled, i.e. every state change is sent, which is the previous behavior).
- **Use SSL:** check to use HTTPS (i.e. prepends url with `https`)
- **Verify SSL:** make sure secure connection is made through SSL

> [!WARNING]
> **Minimum distance alone can make visit tracking worse, not better.** Home Assistant device trackers already update infrequently while stationary (see [Known Issues](#known-issues) below), and this setting only suppresses updates further. If you enable it, do so together with something that guarantees a point still reaches Dawarich periodically while stationary — for example a `time_pattern` automation that calls a location-push mechanism on a schedule.
>
> Dawarich's stay-point visit detector does internally track a maximum time gap (`stay_max_gap_minutes` in its `Visits::StayPointDetector` service) below which a stationary period still counts as one continuous visit, but as of this writing that value isn't exposed as a setting anywhere in the Dawarich UI (it's not one of the fields on the **Settings → Visits** page, which currently only exposes Visit radius, Minimum points, Minimum visit duration, and Smart density fill) — so you can't tune it from your side today. In practice this means: keep your fallback push frequency reasonably tight (a handful of minutes, not hours) and treat "how much silence Dawarich will tolerate" as an internal implementation detail rather than something you can configure, until Dawarich exposes it.
>
> This mirrors how dedicated tracking clients (OwnTracks, Traccar, GPSLogger, …) are built: they all report on "moved far enough OR enough time has passed," never distance alone, precisely to avoid silence during stationary periods.

## Known Issues
Below are some known issues that are being looked at, but with workarounds for the moment.

### Entity or Device not found in registry
This warning shows up because we are trying to determine if the device or entity
is disabled. If you change the name of the tracker sensor of Dawarich you will
get a warning. If you at the same time have disabled the entity then this will,
until you restart your home assistant instance, continue to send new locations.

