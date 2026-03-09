"""Govee BLE Plug integration for Home Assistant."""
from __future__ import annotations

import logging

from homeassistant.components.bluetooth import async_ble_device_from_address
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, CONF_NAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import CONF_AUTH_KEY, DOMAIN
from .coordinator import GoveePlugCoordinator
from .device import GoveePlugDevice

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SWITCH]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Govee BLE Plug from a config entry."""
    address: str = entry.data[CONF_ADDRESS]
    name: str = entry.data.get(CONF_NAME, f"Govee Plug {address[-5:]}")
    auth_key = bytes.fromhex(entry.data[CONF_AUTH_KEY])

    _LOGGER.info("Setting up Govee BLE Plug at %s", address)

    ble_device = async_ble_device_from_address(hass, address)
    if not ble_device:
        raise ConfigEntryNotReady(f"BLE device not found for {address}")

    device = GoveePlugDevice(address=address, ble_device=ble_device, auth_key=auth_key, name=name)
    coordinator = GoveePlugCoordinator(hass, device)

    if not await coordinator.async_setup():
        raise ConfigEntryNotReady(f"Failed to connect to Govee plug at {address}")

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        coordinator: GoveePlugCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_shutdown()
    return unload_ok
