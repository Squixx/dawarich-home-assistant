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
CONF_HEARTBEAT_INTERVAL = "heartbeat_interval"

# Matches Dawarich's own default visit_radius_meters, so a point is only sent
# once the device has plausibly left the place it was at.
DEFAULT_MIN_DISTANCE = 100
DEFAULT_HEARTBEAT_INTERVAL = 15

MAX_DISTANCE_METERS = 10000
MAX_HEARTBEAT_MINUTES = 1440
MIN_HEARTBEAT_MINUTES = 5


class DawarichTrackerStates(Enum):
    """States of the Dawarich tracker sensor."""

    UNKNOWN = "unknown"
    SUCCESS = "success"
    ERROR = "error"
