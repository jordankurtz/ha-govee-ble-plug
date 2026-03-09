"""Govee BLE plug packet builder and parser."""
from __future__ import annotations


def build_packet(cmd_hi: int, cmd_lo: int, payload: bytes = b"") -> bytes:
    """Build a 20-byte Govee BLE command packet with XOR checksum.

    Format: [cmd_hi][cmd_lo][17-byte payload, zero-padded][xor checksum]
    """
    data = bytes([cmd_hi, cmd_lo]) + (payload + b"\x00" * 17)[:17]
    checksum = 0
    for b in data:
        checksum ^= b
    return data + bytes([checksum])


def verify_checksum(packet: bytes) -> bool:
    """Return True if the packet's XOR checksum is valid."""
    if len(packet) < 1:
        return False
    xor = 0
    for b in packet[:-1]:
        xor ^= b
    return xor == packet[-1]


def parse_state_response(packet: bytes) -> bool:
    """Parse an AA 01 state query response. Returns True if plug is ON."""
    return len(packet) > 2 and packet[2] == 0x01


def extract_auth_key(packet: bytes) -> bytes | None:
    """Extract auth key from AA B1 response.

    packet[2] == 0x01 means the button was pressed and the key is valid.
    packet[2] == 0x00 means the button has NOT been pressed yet (random data).
    Key is 16 bytes from packet[3:19] (everything between header and checksum).
    """
    if len(packet) < 20 or packet[2] != 0x01:
        return None
    return bytes(packet[3:19])


def parse_advertisement_state(mfr_data: dict[int, bytes] | None) -> bool | None:
    """Parse power state from BLE advertisement manufacturer data.

    Last byte of any manufacturer data value: 0x01 = ON, 0x00 = OFF.
    Returns None if data is absent or unrecognisable.
    """
    if not mfr_data:
        return None
    for value in mfr_data.values():
        if value:
            last = value[-1]
            if last in (0x00, 0x01):
                return last == 0x01
    return None
