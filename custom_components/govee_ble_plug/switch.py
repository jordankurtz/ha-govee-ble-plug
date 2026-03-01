"""Switch platform for Govee BLE Plug."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import GoveePlugCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Govee BLE Plug switch from config entry."""
    coordinator: GoveePlugCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([GoveePlugSwitch(coordinator, entry)])


class GoveePlugSwitch(CoordinatorEntity[GoveePlugCoordinator], SwitchEntity):
    """Representation of a Govee H5080 smart plug as a switch."""

    _attr_has_entity_name = True
    _attr_name = None  # Use device name as entity name

    def __init__(self, coordinator: GoveePlugCoordinator, entry: ConfigEntry) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        name = entry.data.get(CONF_NAME, f"Govee Plug {coordinator.device.address[-5:]}")
        self._attr_unique_id = coordinator.device.address
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.device.address)},
            "name": name,
            "manufacturer": "Govee",
            "model": "H5080",
        }

    @property
    def is_on(self) -> bool | None:
        """Return True if plug is on."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get("is_on")

    @property
    def available(self) -> bool:
        """Return True when coordinator has data."""
        return self.coordinator.last_update_success

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn plug on."""
        await self.coordinator.async_set_power(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn plug off."""
        await self.coordinator.async_set_power(False)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle coordinator data update."""
        self.async_write_ha_state()
