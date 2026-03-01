"""Quick protocol verification tests (no test framework required)."""
import sys
sys.path.insert(0, "custom_components/govee_ble_plug")

from protocol import build_packet, verify_checksum, extract_auth_key, parse_state_response


def test_power_on():
    pkt = build_packet(0x33, 0x01, bytes([0xFF]))
    expected = bytes.fromhex("3301ff" + "00" * 16 + "cd")
    assert pkt == expected, f"Power ON mismatch: {pkt.hex()} != {expected.hex()}"
    print(f"PASS  power ON:  {pkt.hex()}")


def test_power_off():
    pkt = build_packet(0x33, 0x01, bytes([0xF0]))
    expected = bytes.fromhex("3301f0" + "00" * 16 + "c2")
    assert pkt == expected, f"Power OFF mismatch: {pkt.hex()} != {expected.hex()}"
    print(f"PASS  power OFF: {pkt.hex()}")


def test_auth_request():
    pkt = build_packet(0xAA, 0xB1)
    # Checksum: 0xAA ^ 0xB1 = 0x1B (all zeros XOR don't change it)
    assert pkt[0] == 0xAA and pkt[1] == 0xB1
    assert verify_checksum(pkt)
    print(f"PASS  auth req:  {pkt.hex()}")


def test_state_query():
    pkt = build_packet(0xAA, 0x01)
    assert verify_checksum(pkt)
    print(f"PASS  state qry: {pkt.hex()}")


def test_verify_checksum():
    pkt = build_packet(0x33, 0x01, bytes([0xFF]))
    assert verify_checksum(pkt)
    bad = bytearray(pkt)
    bad[-1] ^= 0xFF
    assert not verify_checksum(bytes(bad))
    print("PASS  checksum verify")


def test_parse_state_response():
    on_pkt = bytes([0xAA, 0x01, 0x01] + [0x00] * 16 + [0x00])
    off_pkt = bytes([0xAA, 0x01, 0x00] + [0x00] * 16 + [0x00])
    assert parse_state_response(on_pkt) is True
    assert parse_state_response(off_pkt) is False
    print("PASS  parse state response")


def test_extract_auth_key():
    # Simulate button-press response with 0x01 at byte[2] and 15 key bytes
    key_bytes = bytes(range(1, 16))  # 15 bytes
    pkt = bytes([0xAA, 0xB1, 0x01]) + key_bytes + bytes([0x00])  # last byte = checksum placeholder
    key = extract_auth_key(pkt)
    assert key == key_bytes, f"{key.hex()} != {key_bytes.hex()}"
    print(f"PASS  extract auth key: {key.hex()}")

    # Not-ready response (byte[2] == 0x00)
    not_ready = bytes([0xAA, 0xB1, 0x00] + [0x00] * 16 + [0x00])
    assert extract_auth_key(not_ready) is None
    print("PASS  extract auth key (not ready → None)")


if __name__ == "__main__":
    tests = [
        test_power_on,
        test_power_off,
        test_auth_request,
        test_state_query,
        test_verify_checksum,
        test_parse_state_response,
        test_extract_auth_key,
    ]
    failures = 0
    for t in tests:
        try:
            t()
        except AssertionError as e:
            print(f"FAIL  {t.__name__}: {e}")
            failures += 1
    print(f"\n{len(tests) - failures}/{len(tests)} tests passed")
    sys.exit(failures)
