"""Constants for the Dawarich integration."""

from datetime import timedelta
from enum import Enum

DOMAIN = "dawarich"


DEFAULT_PORT = 80
DEFAULT_NAME = "Dawarich"
DEFAULT_SSL = False
DEFAULT_VERIFY_SSL = True
CONF_DEVICE = "mobile_app"
UPDATE_INTERVAL = timedelta(seconds=60)
VERSION_UPDATE_INTERVAL = timedelta(hours=1)

CONF_MIN_DISTANCE = "min_distance"
# Matches Dawarich's own `visit_radius_meters` default: if the device hasn't
# left the radius that defines a place, there is nothing worth sending.
DEFAULT_MIN_DISTANCE = 100
CONF_HEARTBEAT_INTERVAL = "heartbeat_interval"
# Paired with the distance filter on purpose. Filtering state changes without a
# heartbeat to replace them would leave larger gaps than doing neither.
DEFAULT_HEARTBEAT_INTERVAL = 15
CONF_HEARTBEAT_IDLE_AFTER = "heartbeat_idle_after"
# Kept short on purpose: active-cadence heartbeats fired while the device is
# already parked fall inside the merge floor, so they extend the journey's track
# by however long this is. Just long enough to establish the visit.
DEFAULT_HEARTBEAT_IDLE_AFTER = 30
CONF_HEARTBEAT_IDLE_INTERVAL = "heartbeat_idle_interval"
# Off by default. The idle cadence only splits tracks when it sits above the
# server's merge floor *and* below its stay gap, and on a stock Dawarich those
# two are both 60 minutes, leaving no valid value. Enabling it blind produces a
# cadence that costs points without splitting anything, so the server has to be
# tuned first -- see `describe_idle_interval` for the check.
DEFAULT_HEARTBEAT_IDLE_INTERVAL = 0
CONF_GPS_ACCURACY_THRESHOLD = "gps_accuracy_threshold"
# Off by default. Dawarich has its own `gps_accuracy_threshold` and applies it
# on ingest when `gps_filtering_enabled` is set, so a client-side threshold is
# redundant unless it is *stricter* than the server's. Setting it loosely (the
# old 200 m default against a server filtering at 100 m) filtered nothing at all.
DEFAULT_GPS_ACCURACY_THRESHOLD = 0

# Distance used to decide "the device actually moved" when no explicit
# minimum distance is configured. Keeps GPS jitter from resetting the
# heartbeat back to its active cadence.
DEFAULT_MOVEMENT_METERS = 50

# Dawarich ends a track only on a gap larger than
# `max(minutes_between_routes, 30.minutes)` (Tracks::BoundaryDetector). The
# 30 is a hard floor in the Ruby source; `minutes_between_routes` is a
# per-user server setting we read at setup, so the effective floor is only
# known at runtime.
DAWARICH_ABSOLUTE_MERGE_FLOOR_MINUTES = 30
# Dawarich's own defaults, used when the server settings can't be read.
DAWARICH_DEFAULT_MINUTES_BETWEEN_ROUTES = 30
DAWARICH_DEFAULT_STAY_MAX_GAP_MINUTES = 60


def merge_floor_minutes(minutes_between_routes: int | None) -> int:
    """Smallest gap that starts a new track, per Tracks::BoundaryDetector."""
    if minutes_between_routes is None:
        minutes_between_routes = DAWARICH_DEFAULT_MINUTES_BETWEEN_ROUTES
    return max(minutes_between_routes, DAWARICH_ABSOLUTE_MERGE_FLOOR_MINUTES)


def describe_idle_interval(
    idle_interval: int,
    minutes_between_routes: int | None,
    stay_max_gap_minutes: int | None,
) -> str | None:
    """Explain why an idle cadence won't do what the user expects, if so.

    Returns None when the configured value sits in the window that actually
    splits stationary periods into their own track.
    """
    if idle_interval <= 0:
        return None

    floor = merge_floor_minutes(minutes_between_routes)
    stay_gap = stay_max_gap_minutes or DAWARICH_DEFAULT_STAY_MAX_GAP_MINUTES

    if floor >= stay_gap:
        return (
            f"no idle interval can work while the server's merge floor "
            f"({floor} min) is at or above its stay gap ({stay_gap} min): "
            f"splitting a track needs a gap above {floor} min, but keeping a "
            f"stay intact needs one at or below {stay_gap} min. Lower "
            f"'minutes_between_routes' in Dawarich's settings to open a window"
        )
    if idle_interval <= floor:
        return (
            f"{idle_interval} min is not above the server's {floor} min merge "
            f"floor, so stationary periods stay merged into the surrounding "
            f"track. Use a value between {floor + 1} and {stay_gap} minutes"
        )
    if idle_interval > stay_gap:
        return (
            f"{idle_interval} min is above the server's {stay_gap} min stay "
            f"gap, so stays will be broken into separate visits. Use a value "
            f"between {floor + 1} and {stay_gap} minutes"
        )
    return None


class DawarichTrackerStates(Enum):
    """States of the Dawarich tracker sensor."""

    UNKNOWN = "unknown"
    SUCCESS = "success"
    ERROR = "error"
