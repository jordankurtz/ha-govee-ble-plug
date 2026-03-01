"""Config flow for Govee BLE Plug integration."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.data_entry_flow import FlowResult

from .const import CONF_AUTH_KEY, DOMAIN
from .device import GoveePlugDevice

_LOGGER = logging.getLogger(__name__)

# Local name prefixes/patterns that indicate a Govee H5080
GOVEE_LOCAL_NAME_PREFIXES = ("Govee_H5080", "GVH5080")


def _is_govee_plug(info: BluetoothServiceInfoBleak) -> bool:
    name = info.name or ""
    return any(name.startswith(pfx) for pfx in GOVEE_LOCAL_NAME_PREFIXES)


class GoveePlugConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle config flow for Govee BLE Plug."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize."""
        self._discovered_devices: dict[str, BluetoothServiceInfoBleak] = {}
        self._selected_address: str | None = None
        self._selected_name: str | None = None
        self._pairing_device: GoveePlugDevice | None = None

    # ------------------------------------------------------------------
    # Bluetooth auto-discovery entry point
    # ------------------------------------------------------------------

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> FlowResult:
        """Handle automatic bluetooth discovery."""
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()

        self._selected_address = discovery_info.address
        self._selected_name = discovery_info.name or f"Govee Plug {discovery_info.address[-5:]}"
        self.context["title_placeholders"] = {"name": self._selected_name}

        return await self.async_step_pair_confirm()

    # ------------------------------------------------------------------
    # Manual user flow
    # ------------------------------------------------------------------

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show discovered Govee devices for manual selection."""
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            info = self._discovered_devices.get(address)
            self._selected_address = address
            self._selected_name = (info.name if info else None) or f"Govee Plug {address[-5:]}"

            await self.async_set_unique_id(address)
            self._abort_if_unique_id_configured()

            return await self.async_step_pair_confirm()

        # Discover nearby Govee devices
        self._discovered_devices = {
            info.address: info
            for info in async_discovered_service_info(self.hass)
            if _is_govee_plug(info)
        }

        if not self._discovered_devices:
            return self.async_abort(reason="no_devices_found")

        device_options = {
            address: f"{info.name or 'Govee Plug'} ({address})"
            for address, info in self._discovered_devices.items()
        }

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_ADDRESS): vol.In(device_options)}),
        )

    # ------------------------------------------------------------------
    # Pairing confirmation — show "press button" instructions
    # ------------------------------------------------------------------

    async def async_step_pair_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show pairing instructions; user clicks Submit then presses plug button."""
        if user_input is not None:
            return await self.async_step_do_pair()

        return self.async_show_form(
            step_id="pair_confirm",
            description_placeholders={"name": self._selected_name},
        )

    # ------------------------------------------------------------------
    # Actual pairing — connect + wait for button press
    # ------------------------------------------------------------------

    async def async_step_do_pair(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Connect to device and wait for physical button press."""
        assert self._selected_address is not None
        assert self._selected_name is not None

        errors: dict[str, str] = {}

        device = GoveePlugDevice(
            address=self._selected_address,
            auth_key=None,
            name=self._selected_name,
        )

        try:
            auth_key = await asyncio.wait_for(device.pair(), timeout=35.0)
        except asyncio.TimeoutError:
            auth_key = None
        finally:
            await device.disconnect()

        if auth_key is None:
            errors["base"] = "pairing_failed"
            return self.async_show_form(
                step_id="pair_confirm",
                description_placeholders={"name": self._selected_name},
                errors=errors,
            )

        return self.async_create_entry(
            title=self._selected_name,
            data={
                CONF_ADDRESS: self._selected_address,
                CONF_NAME: self._selected_name,
                CONF_AUTH_KEY: auth_key.hex(),
            },
        )
