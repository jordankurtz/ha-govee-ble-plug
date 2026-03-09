"""Constants for Govee BLE Plug integration."""

DOMAIN = "govee_ble_plug"

# BLE characteristic UUIDs
WRITE_CHAR_UUID = "00010203-0405-0607-0809-0a0b0c0d2b11"
NOTIFY_CHAR_UUID = "00010203-0405-0607-0809-0a0b0c0d2b10"

# Command identifiers (cmd_hi, cmd_lo)
CMD_AUTH_REQ = (0xAA, 0xB1)
CMD_AUTH_CONF = (0x33, 0xB2)
CMD_POWER = (0x33, 0x01)
CMD_STATE_QUERY = (0xAA, 0x01)

# Power payload bytes
POWER_ON_BYTE = 0x01
POWER_OFF_BYTE = 0x00

# Config entry keys
CONF_AUTH_KEY = "auth_key"

# Timeouts
BLE_TIMEOUT = 10.0
AUTH_TIMEOUT = 30.0  # User must press button within 30s

# Poll interval seconds
UPDATE_INTERVAL = 30
