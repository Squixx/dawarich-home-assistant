"""Show statistical data from your Dawarich instance."""

import logging
from datetime import datetime, timedelta

from dawarich_api import DawarichAPI
from homeassistant.components.device_tracker.const import SourceType
from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.components.sensor.const import SensorDeviceClass, SensorStateClass
from homeassistant.const import (
    CONF_HOST,
    CONF_NAME,
    UnitOfLength,
)
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.helpers.issue_registry import (
    IssueSeverity,
    async_create_issue,
    async_delete_issue,
)
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
)
from homeassistant.util.location import distance as location_distance

from custom_components.dawarich import DawarichConfigEntry

from .const import (
    CONF_DEVICE,
    CONF_HEARTBEAT_INTERVAL,
    CONF_MIN_DISTANCE,
    DEFAULT_HEARTBEAT_INTERVAL,
    DEFAULT_MIN_DISTANCE,
    DOMAIN,
    DawarichTrackerStates,
)
from .coordinator import DawarichStatsCoordinator, DawarichVersionCoordinator

_LOGGER = logging.getLogger(__name__)

SENSOR_TYPES = (
    SensorEntityDescription(
        key="total_distance_km",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        name="Total Distance",
        icon="mdi:map-marker-distance",
        device_class=SensorDeviceClass.DISTANCE,
        translation_key="total_distance",
    ),
    SensorEntityDescription(
        key="total_points_tracked",
        name="Total Points Tracked",
        icon="mdi:map-marker-multiple",
        translation_key="total_points_tracked",
    ),
    SensorEntityDescription(
        key="total_reverse_geocoded_points",
        name="Total Reverse Geocoded Points",
        icon="mdi:map-marker-question",
        translation_key="total_reverse_geocoded_points",
    ),
    SensorEntityDescription(
        key="total_countries_visited",
        name="Total Countries Visited",
        icon="mdi:earth",
        translation_key="total_countries_visited",
    ),
    SensorEntityDescription(
        key="total_cities_visited",
        name="Total Cities Visited",
        icon="mdi:city",
        translation_key="total_cities_visited",
    ),
)

TRACKER_SENSOR_TYPES = SensorEntityDescription(
    key="last_update",
    name="Last Update",
    device_class=SensorDeviceClass.ENUM,
    translation_key="last_update",
)

VERSION_SENSOR_TYPES = SensorEntityDescription(
    key="version",
    name="Dawarich Version",
    translation_key="version",
)

type DawarichSensors = (
    DawarichTrackerSensor | DawarichStatisticsSensor | DawarichVersionSensor
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DawarichConfigEntry,
    async_add_entities: AddEntitiesCallback,
):
    """Set up Dawarich sensor."""
    url = entry.data[CONF_HOST]
    name = entry.data[CONF_NAME]
    coordinator = entry.runtime_data.coordinator
    # Use entry_id for stable identifiers (doesn't change when API key changes)
    entry_id = entry.entry_id

    device_info = DeviceInfo(
        identifiers={(DOMAIN, entry_id)},
        name=name,
        manufacturer="Dawarich",
        configuration_url=entry.runtime_data.api.url,
        entry_type=DeviceEntryType.SERVICE,
    )

    # Add statistics sensor
    sensors: list[DawarichSensors] = [
        DawarichStatisticsSensor(url, entry_id, name, desc, coordinator, device_info)
        for desc in SENSOR_TYPES
    ]

    # Add version sensor
    sensors.append(
        DawarichVersionSensor(
            coordinator=entry.runtime_data.version_coordinator,
            description=VERSION_SENSOR_TYPES,
            entry_id=entry_id,
            device_info=device_info,
        )
    )

    # Add (optional) mobile app tracker sensor
    mobile_app = entry.data[CONF_DEVICE]
    if mobile_app is not None:
        _LOGGER.info("Adding tracker sensor for %s", mobile_app)
        api = entry.runtime_data.api
        min_distance = entry.data.get(CONF_MIN_DISTANCE, DEFAULT_MIN_DISTANCE)
        heartbeat_interval = entry.data.get(
            CONF_HEARTBEAT_INTERVAL, DEFAULT_HEARTBEAT_INTERVAL
        )
        if min_distance > 0 and heartbeat_interval == 0:
            _LOGGER.warning(
                (
                    "%s has a minimum distance of %s m but no heartbeat. Standing "
                    "still will now produce no points at all, which Dawarich reads "
                    "as leaving and returning. Set a heartbeat interval, or set the "
                    "minimum distance to 0."
                ),
                mobile_app,
                min_distance,
            )
        sensors.append(
            DawarichTrackerSensor(
                entry_id=entry_id,
                device_name=name,
                mobile_app=mobile_app,
                api=api,
                hass=hass,
                device_info=device_info,
                description=TRACKER_SENSOR_TYPES,
                min_distance=min_distance,
                heartbeat_interval=heartbeat_interval,
            )
        )
    else:
        _LOGGER.info("No mobile device provided, skipping tracker sensor")

    async_add_entities(sensors)


class DawarichTrackerSensor(SensorEntity):
    """Sensor that updates and keep track of the updates to the Dawarich API."""

    def __init__(
        self,
        entry_id: str,
        device_name: str,
        mobile_app: str,
        api: DawarichAPI,
        hass: HomeAssistant,
        device_info: DeviceInfo,
        description: SensorEntityDescription,
        min_distance: int = DEFAULT_MIN_DISTANCE,
        heartbeat_interval: int = DEFAULT_HEARTBEAT_INTERVAL,
    ) -> None:
        """Initialize the sensor."""
        self._device_name = device_name
        self._mobile_app = mobile_app
        self._entry_id = entry_id
        self._hass = hass
        self._api = api
        self._attr_device_info = device_info
        self._attr_device_class = description.device_class
        self.entity_description = description
        self._repair_issue_created = False

        self._min_distance = min_distance
        self._heartbeat_interval = heartbeat_interval
        self._last_sent_coordinates: tuple[float, float] | None = None
        # Subscriptions are registered in async_added_to_hass, not here: an entity
        # that is disabled in the registry is still constructed but never added,
        # and would otherwise keep pushing points forever.
        self._async_unsubscribe_state_changed: CALLBACK_TYPE | None = None
        self._async_unsubscribe_heartbeat: CALLBACK_TYPE | None = None

        self._state: DawarichTrackerStates = DawarichTrackerStates.UNKNOWN
        self._attr_options = [state.value for state in DawarichTrackerStates]

    async def async_added_to_hass(self) -> None:
        """Run when entity is added to hass."""
        self._async_unsubscribe_state_changed = async_track_state_change_event(
            hass=self._hass,
            entity_ids=[self._mobile_app],
            action=self._async_update_callback,
        )
        if self._heartbeat_interval > 0:
            self._async_unsubscribe_heartbeat = async_track_time_interval(
                self._hass,
                self._async_heartbeat_callback,
                timedelta(minutes=self._heartbeat_interval),
            )

        # Check initial state of the tracked entity
        initial_state = self._hass.states.get(self._mobile_app)
        self._async_check_entity_availability(initial_state)

    @property
    def _issue_id(self) -> str:
        """Return the issue id for the repair issue."""
        return f"device_tracker_unavailable_{self._entry_id}"

    @callback
    def _async_check_entity_availability(self, state) -> bool:
        """Check if the tracked entity is available and manage repair issue.

        Returns True if the entity is available, False otherwise.
        """
        if state is None or state.state in ("unavailable", "unknown"):
            if not self._repair_issue_created:
                _LOGGER.warning(
                    "Device tracker %s is not available. Please check the entity.",
                    self._mobile_app,
                )
                async_create_issue(
                    self._hass,
                    DOMAIN,
                    self._issue_id,
                    is_fixable=False,
                    severity=IssueSeverity.WARNING,
                    translation_key="device_tracker_unavailable",
                    translation_placeholders={
                        "device_tracker": self._mobile_app,
                        "device_name": self._device_name,
                    },
                )
                self._repair_issue_created = True
            return False
        if self._repair_issue_created:
            _LOGGER.info(
                "Device tracker %s is available again, clearing repair issue.",
                self._mobile_app,
            )
            async_delete_issue(self._hass, DOMAIN, self._issue_id)
            self._repair_issue_created = False
        return True

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is removed."""
        if self._async_unsubscribe_state_changed is not None:
            self._async_unsubscribe_state_changed()
            self._async_unsubscribe_state_changed = None
        if self._async_unsubscribe_heartbeat is not None:
            self._async_unsubscribe_heartbeat()
            self._async_unsubscribe_heartbeat = None
        if self._repair_issue_created:
            async_delete_issue(self._hass, DOMAIN, self._issue_id)

    @property
    def unique_id(self) -> str:  # type: ignore[override]
        """Return a unique id for the sensor."""
        return f"{self._entry_id}/tracker"

    @property
    def state(self) -> StateType:
        """Return the state of the sensor."""
        return self._state.value

    @property
    def icon(self) -> str:  # type: ignore[override]
        """Return the icon to use in the frontend."""
        return "mdi:map-marker-circle"

    async def _async_update_callback(self, event):
        """Update the Dawarich API with the new location."""
        if await self._async_check_is_disabled():
            return

        _LOGGER.debug(
            "State change detected for %s, updating Dawarich", self._mobile_app
        )
        new_state = event.data.get("new_state")

        if not self._async_check_entity_availability(new_state):
            return

        if new_state is None:
            _LOGGER.error("No new state found for %s", self._mobile_app)
            return

        # Log received data
        new_data = new_state.attributes
        _LOGGER.debug("Received data: %s", new_data)

        coordinates = self._async_get_coordinates(new_data)
        if coordinates is None:
            return

        if not self._async_has_moved_far_enough(coordinates):
            _LOGGER.debug(
                "%s moved less than %s m since the last point, skipping update",
                self._mobile_app,
                self._min_distance,
            )
            return

        await self._async_send_location(coordinates, new_data)

    async def _async_heartbeat_callback(self, now: datetime) -> None:
        """Send the current position on a timer, even if nothing changed.

        Home Assistant device trackers are event driven, so a stationary device
        can emit nothing for hours. Dawarich reads that silence as a departure
        and a return, and splits one continuous stay into several visits.
        """
        if await self._async_check_is_disabled():
            return

        state = self._hass.states.get(self._mobile_app)
        if not self._async_check_entity_availability(state) or state is None:
            return

        coordinates = self._async_get_coordinates(state.attributes)
        if coordinates is None:
            return

        _LOGGER.debug("Sending heartbeat for %s", self._mobile_app)
        # is_heartbeat: the entity's own last_seen reflects its last state
        # change, not now. Reusing it would give every heartbeat the same stale
        # timestamp instead of spreading them over time.
        await self._async_send_location(
            coordinates, state.attributes, is_heartbeat=True
        )

    def _async_get_coordinates(self, new_data: dict) -> tuple[float, float] | None:
        """Return the coordinates in the state attributes, if there are any."""
        latitude = new_data.get("latitude")
        longitude = new_data.get("longitude")

        if latitude is None or longitude is None:
            if new_data.get("source") != SourceType.GPS:
                _LOGGER.warning(
                    (
                        "The choosen device tracker (%s) is emitting a '%s' "
                        "source type which typically does not have coordinates. "
                        "Please change the device tracker to one that provides GPS coordinates."
                    ),
                    self._mobile_app,
                    new_data.get("source"),
                )
            _LOGGER.debug("Coordinates are not present, skipping update")
            return None

        return (latitude, longitude)

    def _async_has_moved_far_enough(self, coordinates: tuple[float, float]) -> bool:
        """Check the device has moved at least min_distance since the last point."""
        if self._min_distance <= 0 or self._last_sent_coordinates is None:
            return True

        moved = location_distance(
            *self._last_sent_coordinates,
            *coordinates,
        )
        # location_distance returns None for out of range coordinates. Send the
        # point rather than silently dropping it.
        return moved is None or moved >= self._min_distance

    async def _async_send_location(
        self,
        coordinates: tuple[float, float],
        new_data: dict,
        *,
        is_heartbeat: bool = False,
    ) -> None:
        """Send the given coordinates to the Dawarich API."""
        latitude, longitude = coordinates
        optional_params = await self._async_add_optional_params(
            new_data, is_heartbeat=is_heartbeat
        )

        # Send to Dawarich API
        response = await self._api.add_one_point(
            name=self._device_name,
            latitude=latitude,
            longitude=longitude,
            **optional_params,
        )
        if response.success:
            _LOGGER.debug("Location sent to Dawarich API")
            self._state = DawarichTrackerStates.SUCCESS
            self._last_sent_coordinates = coordinates
        else:
            self._state = DawarichTrackerStates.ERROR
            _LOGGER.error(
                "Error sending location to Dawarich API response code %s and error: %s",
                response.response_code,
                response.error,
            )

    async def _async_add_optional_params(
        self, new_data: dict, *, is_heartbeat: bool = False
    ) -> dict:
        # Only include optional parameters if they have valid values
        optional_params = {}

        if (gps_accuracy := new_data.get("gps_accuracy")) is not None:
            optional_params["horizontal_accuracy"] = gps_accuracy

        if (altitude := new_data.get("altitude")) is not None:
            optional_params["altitude"] = altitude

        if (vertical_accuracy := new_data.get("vertical_accuracy")) is not None:
            optional_params["vertical_accuracy"] = vertical_accuracy

        if (speed := new_data.get("speed")) is not None:
            optional_params["speed"] = speed
        elif (velocity := new_data.get("velocity")) is not None:
            optional_params["speed"] = velocity

        if (battery := new_data.get("battery")) is not None:
            optional_params["battery"] = battery

        if not is_heartbeat and (
            (raw_timestamp := new_data.get("last_seen")) is not None
            or (raw_timestamp := new_data.get("last_timestamp")) is not None
        ):
            optional_params["timestamp"] = raw_timestamp

        return optional_params

    async def _async_check_is_disabled(self) -> bool:
        """Check if the Dawarich tracker sensor is disabled."""
        device_registry = dr.async_get(self._hass)
        entity_registry = er.async_get(self._hass)

        # Look up device
        if self.device_entry is None:
            _LOGGER.debug("No device entry found, instead looking based on identifiers")
            device = device_registry.async_get_device(
                identifiers={(DOMAIN, self._entry_id)}
            )
        else:
            _LOGGER.debug(
                "Device entry found (%s), looking up device based on device entry",
                self.device_entry.id,
            )
            # While the device entry could be the same we are re-querying
            # it to ensure that we do not get a stale version.
            device = device_registry.async_get(self.device_entry.id)
        if device is None:
            _LOGGER.warning(
                "Device not found in device registry. This should not typically "
                "happen. Try restarting Home Assistant.",
            )
            return False

        # Look up entity
        if self.registry_entry is None:
            _LOGGER.debug("No registry entry found, looking up based on unique id")
            # async_get expects an entity_id, not a unique_id, so the unique_id
            # has to be resolved first or the lookup always misses.
            entity_id = entity_registry.async_get_entity_id(
                "sensor", DOMAIN, self.unique_id
            )
            entity_entry = (
                entity_registry.async_get(entity_id) if entity_id is not None else None
            )
        else:
            _LOGGER.debug(
                "Registry entry found (%s), looking up entity based on registry entry",
                self.registry_entry.entity_id,
            )
            # While the registry entry could be the same we are re-querying
            # it to ensure that we do not get a stale version.
            entity_entry = entity_registry.async_get(self.registry_entry.entity_id)
        if entity_entry is None:
            _LOGGER.warning(
                "Entity not found in entity registry. This should not typically "
                "happen. Try restarting Home Assistant.",
            )
            return False

        if device.disabled:
            _LOGGER.debug(
                "State change detected for %s, however, Dawarich device is disabled, not updating.",
                self._mobile_app,
            )
            return True
        if entity_entry.disabled:
            _LOGGER.debug(
                "State change detected for %s, however, Dawarich tracker sensor is disabled, not updating.",
                self._mobile_app,
            )
            return True
        return False

    @property
    def name(self) -> str:  # type: ignore[override]
        """Return the name of the sensor."""
        return self._device_name + " Tracker"


class DawarichStatisticsSensor(CoordinatorEntity, SensorEntity):  # type: ignore[incompatible-subclass]
    """Representation of a Dawarich sensor."""

    def __init__(
        self,
        url: str,
        entry_id: str,
        device_name: str,
        description: SensorEntityDescription,
        coordinator: DawarichStatsCoordinator,
        device_info: DeviceInfo,
    ):
        """Initialize Dawarich sensor."""
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._url = url
        self._device_name = device_name
        self.entity_description = description
        self._attr_unique_id = f"{entry_id}/{description.key}"
        self._attr_device_info = device_info
        self._attr_state_class = SensorStateClass.TOTAL

    @property
    def native_value(self) -> StateType:  # type: ignore[override]
        """Return the state of the device."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data[self.entity_description.key]

    @property
    def icon(self) -> str:  # type: ignore[override]
        """Return the icon to use in the frontend."""
        if self.entity_description.icon is not None:
            return self.entity_description.icon
        return "mdi:eye"

    @property
    def name(self) -> str:  # type: ignore[override]
        """Return the name of the sensor."""
        if isinstance(self.entity_description.name, str):
            return f"{self._device_name} {self.entity_description.name.title()}"
        _LOGGER.error("Name is not a string for %s", self.entity_description.key)
        return f"{self._device_name}"


class DawarichVersionSensor(
    CoordinatorEntity[DawarichVersionCoordinator], SensorEntity
):  # type: ignore[incompatible-subclass]
    """Representation of a Dawarich version sensor."""

    def __init__(
        self,
        coordinator: DawarichVersionCoordinator,
        description: SensorEntityDescription,
        entry_id: str,
        device_info: DeviceInfo,
    ):
        """Initialize Dawarich version sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry_id}/{description.key}"
        self._attr_device_info = device_info

    @property
    def native_value(self) -> StateType:  # type: ignore[override]
        """Return the state of the device."""
        if self.coordinator.data is None:
            return None
        # Combine the version parts
        major = self.coordinator.data["major"]
        minor = self.coordinator.data["minor"]
        patch = self.coordinator.data["patch"]
        return f"{major}.{minor}.{patch}"

    @property
    def icon(self) -> str:
        """Return the icon to use in the frontend."""
        return "mdi:information-outline"
