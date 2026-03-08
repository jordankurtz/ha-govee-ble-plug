"""Govee H5080 BLE device abstraction."""
from __future__ import annotations

import asyncio
import logging
from typing import Callable

from bleak import BleakClient
from bleak.backends.device import BLEDevice
from bleak.exc import BleakError
from bleak_retry_connector import establish_connection

from .const import (
    AUTH_TIMEOUT,
    BLE_TIMEOUT,
    CMD_AUTH_CONF,
    CMD_AUTH_REQ,
    CMD_POWER,
    CMD_STATE_QUERY,
    NOTIFY_CHAR_UUID,
    POWER_OFF_BYTE,
    POWER_ON_BYTE,
    WRITE_CHAR_UUID,
)
from .protocol import build_packet, extract_auth_key, parse_state_response, verify_checksum

_LOGGER = logging.getLogger(__name__)


class GoveePlugDevice:
    """Represents a Govee H5080 BLE smart plug."""

    def __init__(
        self,
        address: str,
        ble_device: BLEDevice | None = None,
        auth_key: bytes | None = None,
        name: str | None = None,
    ) -> None:
        """Initialize device."""
        self._address = address
        self._ble_device = ble_device
        self._auth_key = auth_key  # 15-byte key; None until pairing complete
        self._name = name or f"Govee Plug {address[-5:]}"
        self._client: BleakClient | None = None
        self._lock = asyncio.Lock()
        self._connected = False
        self.is_on: bool | None = None

        # Events for async response synchronisation
        self._auth_req_event = asyncio.Event()   # AA B1 button-press received
        self._auth_conf_event = asyncio.Event()  # 33 B2 confirmation received
        self._state_event = asyncio.Event()       # AA 01 state response received
        self._power_event = asyncio.Event()       # 33 01 power-set confirmation

        self._state_callbacks: list[Callable[[], None]] = []

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def address(self) -> str:
        """Return BLE address."""
        return self._address

    @property
    def name(self) -> str:
        """Return device name."""
        return self._name

    @property
    def connected(self) -> bool:
        """Return True when BLE link is up and auth is complete."""
        return self._connected

    @property
    def auth_key(self) -> bytes | None:
        """Return stored auth key (None until paired)."""
        return self._auth_key

    def set_ble_device(self, ble_device: BLEDevice) -> None:
        """Update the BLEDevice reference (e.g. from a fresh advertisement)."""
        self._ble_device = ble_device

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def register_callback(self, cb: Callable[[], None]) -> Callable[[], None]:
        """Register a state-change callback. Returns unregister callable."""
        self._state_callbacks.append(cb)
        return lambda: self._state_callbacks.remove(cb)

    def _fire_state_callbacks(self) -> None:
        for cb in self._state_callbacks:
            try:
                cb()
            except Exception:
                _LOGGER.exception("State callback error")

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> bool:
        """Connect (and authenticate) using a stored auth key.

        Requires self._auth_key to be set. Use pair() for first-time setup.
        """
        if self._auth_key is None:
            _LOGGER.error("No auth key — run pairing first")
            return False

        async with self._lock:
            if self._connected:
                return True
            return await self._do_connect()

    async def pair(self) -> bytes | None:
        """Initiate pairing: send auth request, wait for button press.

        Returns the 15-byte auth key on success, None on failure.
        Caller must keep the connection open for the full AUTH_TIMEOUT.
        """
        async with self._lock:
            try:
                await self._open_ble_connection()
                if self._client is None:
                    return None

                # Send AA B1 auth request
                self._auth_req_event.clear()
                pkt = build_packet(*CMD_AUTH_REQ)
                await self._client.write_gatt_char(WRITE_CHAR_UUID, pkt, response=False)
                _LOGGER.debug("Auth request sent, waiting for button press (%.0fs)", AUTH_TIMEOUT)

                # Wait for user to press button on plug
                try:
                    await asyncio.wait_for(self._auth_req_event.wait(), AUTH_TIMEOUT)
                except asyncio.TimeoutError:
                    _LOGGER.error("Pairing timeout — button not pressed in time")
                    await self._close_ble_connection()
                    return None

                if self._auth_key is None:
                    _LOGGER.error("Button-press response received but key extraction failed")
                    await self._close_ble_connection()
                    return None

                # Send 33 B2 auth confirmation
                self._auth_conf_event.clear()
                conf_pkt = build_packet(*CMD_AUTH_CONF, payload=self._auth_key)
                await self._client.write_gatt_char(WRITE_CHAR_UUID, conf_pkt, response=False)

                try:
                    await asyncio.wait_for(self._auth_conf_event.wait(), BLE_TIMEOUT)
                except asyncio.TimeoutError:
                    _LOGGER.warning("No auth confirmation from device — continuing anyway")

                self._connected = True
                _LOGGER.info("Pairing complete, auth key: %s", self._auth_key.hex())
                return self._auth_key

            except BleakError as exc:
                _LOGGER.error("Pairing BLE error: %s", exc)
                await self._close_ble_connection()
                return None

    async def disconnect(self) -> None:
        """Disconnect from device."""
        self._connected = False
        await self._close_ble_connection()

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    async def set_power(self, on: bool) -> bool:
        """Send power on/off command."""
        payload = bytes([POWER_ON_BYTE if on else POWER_OFF_BYTE])
        pkt = build_packet(*CMD_POWER, payload=payload)
        return await self._send_and_wait(pkt, self._power_event)

    async def query_state(self) -> bool | None:
        """Send state query; return current on/off state or None on failure."""
        pkt = build_packet(*CMD_STATE_QUERY)
        ok = await self._send_and_wait(pkt, self._state_event)
        if not ok:
            return None
        return self.is_on

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _do_connect(self) -> bool:
        """Open BLE, authenticate with stored key, query state."""
        try:
            await self._open_ble_connection()
            if self._client is None:
                return False

            assert self._auth_key is not None
            self._auth_conf_event.clear()
            conf_pkt = build_packet(*CMD_AUTH_CONF, payload=self._auth_key)
            _LOGGER.info("Sending auth confirmation (%d-byte key: %s)", len(self._auth_key), self._auth_key.hex())
            await self._client.write_gatt_char(WRITE_CHAR_UUID, conf_pkt, response=False)

            try:
                await asyncio.wait_for(self._auth_conf_event.wait(), BLE_TIMEOUT)
                _LOGGER.info("Auth confirmation acknowledged by device")
            except asyncio.TimeoutError:
                _LOGGER.warning("Auth confirmation timeout — device did not respond")

            self._connected = True

            # Initial state query
            pkt = build_packet(*CMD_STATE_QUERY)
            await self._client.write_gatt_char(WRITE_CHAR_UUID, pkt, response=False)

            _LOGGER.info("Connected to %s (client.is_connected=%s)", self._address, self._client.is_connected)
            return True

        except BleakError as exc:
            _LOGGER.error("Connection failed for %s: %s", self._address, exc)
            await self._close_ble_connection()
            return False

    async def _open_ble_connection(self) -> None:
        """Establish BLE connection and start notifications."""
        if self._ble_device is None:
            raise BleakError(f"No BLEDevice available for {self._address}")
        _LOGGER.info("Opening BLE connection to %s (ble_device=%s)", self._address, self._ble_device)
        self._client = await establish_connection(
            BleakClient,
            device=self._ble_device,
            name=self._name,
            disconnected_callback=self._on_disconnect,
        )
        _LOGGER.info("BLE connected, subscribing to notifications on %s", NOTIFY_CHAR_UUID)
        await self._client.start_notify(NOTIFY_CHAR_UUID, self._on_notification)
        _LOGGER.info("BLE link up, notifications started")

    async def _close_ble_connection(self) -> None:
        if self._client:
            try:
                await self._client.disconnect()
            except BleakError:
                pass
            self._client = None

    async def _send_and_wait(self, packet: bytes, event: asyncio.Event, timeout: float = BLE_TIMEOUT) -> bool:
        """Write packet and wait for the associated response event."""
        if not self._connected or self._client is None:
            _LOGGER.error("Cannot send — not connected (connected=%s, client=%s)", self._connected, self._client is not None)
            return False

        async with self._lock:
            try:
                is_conn = self._client.is_connected if self._client else False
                _LOGGER.info("Sending packet %s (client.is_connected=%s)", packet.hex(), is_conn)
                event.clear()
                await self._client.write_gatt_char(WRITE_CHAR_UUID, packet, response=False)
                _LOGGER.info("Write succeeded, waiting for response (%.1fs timeout)", timeout)
                try:
                    await asyncio.wait_for(event.wait(), timeout)
                    _LOGGER.info("Response received for packet %s", packet[:2].hex())
                except asyncio.TimeoutError:
                    _LOGGER.warning("Response timeout for packet %s", packet[:2].hex())
                return True
            except BleakError as exc:
                _LOGGER.error("Send error: %s", exc)
                return False

    def _on_disconnect(self, _client: BleakClient) -> None:
        """Handle unexpected disconnection."""
        _LOGGER.info("Disconnected from %s", self._address)
        self._connected = False

    def _on_notification(self, _sender: int, data: bytearray) -> None:
        """Route incoming BLE notification to appropriate handler."""
        pkt = bytes(data)
        _LOGGER.info("Notification (%d bytes): %s", len(pkt), pkt.hex())

        if len(pkt) < 2:
            _LOGGER.warning("Notification too short (%d bytes)", len(pkt))
            return

        if not verify_checksum(pkt):
            _LOGGER.warning("Checksum mismatch — raw: %s", pkt.hex())
            return

        hi, lo = pkt[0], pkt[1]

        if hi == 0xAA and lo == 0xB1:
            # Button-press response during pairing
            _LOGGER.info("Auth response received — pkt[2]=0x%02x, len=%d", pkt[2], len(pkt))
            key = extract_auth_key(pkt)
            if key is not None:
                self._auth_key = key
                _LOGGER.info("Auth key extracted: %s", key.hex())
                self._auth_req_event.set()
            else:
                _LOGGER.warning("Auth key extraction failed from: %s", pkt.hex())

        elif hi == 0x33 and lo == 0xB2:
            # Auth confirmation
            self._auth_conf_event.set()

        elif hi == 0xAA and lo == 0x01:
            # State query response
            self.is_on = parse_state_response(pkt)
            _LOGGER.debug("State response: is_on=%s", self.is_on)
            self._state_event.set()
            self._fire_state_callbacks()

        elif hi == 0x33 and lo == 0x01:
            # Power-set confirmation
            # byte[2]: 0x01 on, 0x00 off (mirrors what we sent)
            if len(pkt) > 2:
                self.is_on = pkt[2] == 0x01 or pkt[2] == POWER_ON_BYTE
            self._power_event.set()
            self._fire_state_callbacks()
