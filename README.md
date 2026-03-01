# Govee BLE Plug

Home Assistant custom integration for the **Govee H5080** BLE smart plug.

Controls the plug over Bluetooth LE — no cloud, no Wi-Fi, no Govee account required.

## Features

- **Switch entity** — turn the plug on or off from HA
- **Passive state updates** — state reflects instantly from BLE advertisements
- **Active polling** — GATT connection queries state every 30 s
- **Physical button pairing** — one-time setup via button press on the plug

> Energy monitoring is H5086-only and is not included.

## Requirements

- Home Assistant 2024.1 or newer
- A Bluetooth adapter visible to HA (built-in or USB dongle)
- Govee H5080 smart plug

## Installation via HACS

1. In HACS, go to **Integrations → Custom repositories**
2. Add `https://github.com/jordankurtz/ha-govee-ble-plug` with category **Integration**
3. Install **Govee BLE Plug** and restart Home Assistant

## Manual Installation

Copy `custom_components/govee_ble_plug/` into your HA `config/custom_components/` directory and restart.

## Setup

1. Go to **Settings → Integrations → Add Integration → Govee BLE Plug**
2. HA will auto-discover the plug or let you select it from a list
3. When prompted, click **Submit** then press the physical button on the plug within 30 seconds
4. A switch entity will appear for the plug
