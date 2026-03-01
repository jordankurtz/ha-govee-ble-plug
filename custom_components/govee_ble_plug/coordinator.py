"""DataUpdateCoordinator for Govee BLE Plug."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, UPDATE_INTERVAL
from .device import GoveePlugDevice
from .protocol import parse_advertisement_state

_LOGGER = logging.getLogger(__name__)


class GoveePlugCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator managing BLE connection and periodic state polling."""

    def __init__(self, hass: HomeAssistant, device: GoveePlugDevice) -> None:
        """Initialize coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{device.address}",
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
        )
        self.device = device
        self._unregister_device_cb: callable | None = None
        self._unregister_adv_cb: callable | None = None

    async def async_setup(self) -> bool:
        """Connect device and register advertisement callback."""
        # Register device-level state callback → push updates to HA
        self._unregister_device_cb = self.device.register_callback(self._on_device_state_update)

        # Register BLE advertisement watcher for passive state updates
        self._unregister_adv_cb = bluetooth.async_register_callback(
            self.hass,
            self._on_advertisement,
            bluetooth.BluetoothCallbackMatcher(address=self.device.address),
            bluetooth.BluetoothScanningMode.PASSIVE,
        )

        if not await self.device.connect():
            _LOGGER.error("Failed initial connection to %s", self.device.address)
            return False

        return True

    async def async_shutdown(self) -> None:
        """Clean up callbacks and disconnect."""
        if self._unregister_device_cb:
            self._unregister_device_cb()
            self._unregister_device_cb = None

        if self._unregister_adv_cb:
            self._unregister_adv_cb()
            self._unregister_adv_cb = None

        await self.device.disconnect()

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    @callback
    def _on_device_state_update(self) -> None:
        """Push device state into HA immediately."""
        self.async_set_updated_data({"is_on": self.device.is_on})

    @callback
    def _on_advertisement(
        self,
        service_info: BluetoothServiceInfoBleak,
        change: bluetooth.BluetoothChange,
    ) -> None:
        """Parse passive advertisement for power state."""
        state = parse_advertisement_state(service_info.manufacturer_data)
        if state is None:
            return
        if state != self.device.is_on:
            _LOGGER.debug("Advertisement state change → is_on=%s", state)
            self.device.is_on = state
            self.async_set_updated_data({"is_on": state})

    # ------------------------------------------------------------------
    # Polling
    # ------------------------------------------------------------------

    async def _async_update_data(self) -> dict[str, Any]:
        """Reconnect if needed, then poll device state."""
        if not self.device.connected:
            _LOGGER.debug("Device not connected, reconnecting")
            if not await self.device.connect():
                raise UpdateFailed(f"Cannot reconnect to {self.device.address}")

        state = await self.device.query_state()
        return {"is_on": state}

    # ------------------------------------------------------------------
    # Control
    # ------------------------------------------------------------------

    async def async_set_power(self, on: bool) -> None:
        """Turn plug on or off."""
        if not self.device.connected:
            if not await self.device.connect():
                _LOGGER.error("Cannot set power — device not connected")
                return
        await self.device.set_power(on)
        await self.async_request_refresh()
