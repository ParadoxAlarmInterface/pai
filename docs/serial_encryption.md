# EVO Serial Encryption (E0 FE frames)

EVO panels with firmware ≥ 7.50.000 encrypt the RS-232 serial bus using a
Paradox-custom AES-256-ECB algorithm.  The unencrypted serial port can be
re-enabled with an unlock code from Paradox.

---

## Two distinct E0 FE frame formats

Both formats share the same two-byte header (`0xE0`, `0xFE`), but differ
in everything that follows.

### Format 1 — BabyWare compact (firmware < 7.50 / BabyWare software)

```
[E0 | status_nibble] [FE] [length] [0x00] [request_nr] [data...] [checksum] [end]
```

- `byte[2]` is the **total frame length** (including all header/trailer bytes).
- Data payload is short (typically 4–8 bytes); the proprietary encryption
  algorithm is unknown.
- PAI passes these frames to the handler unchanged.  They cannot be decrypted.

### Format 2 — Full-AES (ESP32 firmware / EVO ≥ 7.50)

```
[0xE0 | (payload[0] & 0x0F)] [0xFE] [AES-256 ciphertext...] [checksum]
```

- **No length byte** at position `[2]`.  The low nibble of `byte[0]` echoes
  the low nibble of the first byte of the plaintext payload.
- AES ciphertext occupies `ceil(len(payload) / 16) * 16` bytes
  (payload is padded to a 16-byte boundary with `0xEE`).
- `byte[-1]` is `sum(all preceding bytes) % 256`.
- Frame boundary is determined by scanning for a **valid checksum at AES block
  boundaries**: try `frame_len = 2 + n×16 + 1` for n = 1, 2, 3… and accept
  the first position where `sum(frame[:-1]) % 256 == frame[-1]`.  No length
  field or inter-byte timeout is required.

#### Example: 37-byte InitiateCommunication

```
plaintext  : 37 bytes
padded     : 48 bytes (3 × 16, trailing 0xEE fill)
frame size : 2 (header) + 48 (AES) + 1 (checksum) = 51 bytes
```

---

## Encryption algorithm

Paradox uses a **custom pure-Python AES-256-ECB** implementation
(`paradox/lib/crypto.py`).  The same algorithm is used for IP150 TCP
encryption; only the key derivation differs.

### Key derivation for serial

```
key = pc_password_bytes  +  b"\xee" * (32 - len(pc_password_bytes))
```

- `make_serial_key(password)` in `paradox/connections/serial/encryption.py`
  handles `str`, `bytes`, and `int` password types.
- The PC password is the 4-hex-digit code configured on the panel
  (e.g. `"0000"` → `b"0000" + b"\xee" * 28`).
- **Do not call `str()` on a `bytes` password** — `str(b"1234")` yields
  `"b'1234'"`, producing the wrong key bytes.

### Padding

Plaintext is padded with `0xEE` bytes to the next 16-byte boundary before
encryption.  After decryption, trailing `0xEE` bytes are stripped.

---

## PAI implementation

### Outgoing messages (`SerialConnectionProtocol.send_message`)

When `SERIAL_ENCRYPTED = True`, `connection_made()` wraps the raw asyncio
transport with `EncryptedSerialTransport`.  Every call to `transport.write()`
transparently passes through `encrypt_serial_message()` before hitting the
wire.

```
PAI message bytes
    → encrypt_serial_message(payload, key)
    → [E0|nibble][FE][AES...][cs]
    → serial port
```

### Incoming messages (`SerialConnectionProtocol.data_received`)

The framer distinguishes the two E0 FE modes by the `SERIAL_ENCRYPTED` config
flag:

| `SERIAL_ENCRYPTED` | `buffer[1] == 0xFE` action |
|---|---|
| `False` | Read `buffer[2]` as total frame length (BabyWare compact) |
| `True` | Scan `frame_len = 2 + n×16 + 1` (n = 1…7); accept first valid checksum |

For Format 2, the framer scans incrementally as bytes arrive — no timer is
needed.  The decrypted payload is forwarded to `handler.on_message()`
immediately once a valid checksum boundary is found.

### Configuration

```python
# pai.conf
SERIAL_ENCRYPTED = True   # default: False
PASSWORD = "0000"         # PC password (same as used for non-encrypted serial)
```

`SERIAL_ENCRYPTED` applies to both `SERIAL_PORT` and `IP_CONNECTION_BARE` connections.
Both use `SerialConnectionProtocol`, so the same framing and decryption logic is active
for either transport.

---

## Capture file decryption (`ip150_connection_decrypt --serial`)

The `--serial` mode in `paradox/console_scripts/ip150_connection_decrypt.py`
can decrypt capture files produced by the ESP32 or a serial sniffer.

### Capture file format

```
TX [51]: e0 fe 12 c5 ca 4a b7 dc b3 c5 92 06 f6 e9 eb 47 76 1e c9 28 bf 27 54 ee 41 dd d3 ab b4 d0 88 bb b3 ee 36 9b e2 17 50 fd 52 cc 91 19 ...
RX [51]: e0 fe ...
```

Each line is a complete framed packet.  The tool calls
`decrypt_serial_message(frame, key)` directly on each E0 FE line; no
timeout-based framing is needed since packet boundaries are already known.

### Usage

```bash
pai-decrypt capture.serial --serial --pc-password 0000
```

### Decryption behaviour

| Frame type | Outcome |
|---|---|
| Full-AES E0 FE (≥ 16 bytes AES data) | Decrypted; inner message parsed by panel parsers |
| BabyWare compact E0 FE (< 16 bytes AES data) | Structure displayed (`request_nr`, raw data); content not decryptable |
| Regular Paradox frame | Parsed normally |

---

## File locations

| File | Role |
|---|---|
| `paradox/lib/crypto.py` | `encrypt()`, `decrypt()`, `encrypt_serial_message()`, `decrypt_serial_message()` |
| `paradox/connections/serial/encryption.py` | `EncryptedSerialTransport`, `make_serial_key()` |
| `paradox/connections/serial/framing.py` | `SerialFramer` — pure byte framing and AES block scan |
| `paradox/connections/serial/protocol.py` | `SerialConnectionProtocol` — asyncio glue and dispatch |
| `paradox/config.py` | `SERIAL_ENCRYPTED` flag |
| `paradox/console_scripts/ip150_connection_decrypt.py` | Offline capture decryption tool |
| `tests/lib/test_serial_crypto.py` | Unit tests for encrypt/decrypt roundtrips |
| `tests/connection/serial/test_protocol.py` | Integration tests for framing and decryption |

---

## Known pitfalls

- **No length byte in Format 2.** An earlier PAI implementation incorrectly
  read `buffer[2]` as the frame length.  In Format 2, that byte is AES
  ciphertext — roughly half the time it exceeds the actual frame length,
  causing the framer to stall.

- **AES data offset.** An earlier implementation read `frame[3:-1]` for the
  ciphertext, skipping three bytes instead of two, so decryption always
  produced garbage.

- **`str(bytes)` key corruption.** Passing a `bytes` password through
  `str()` before encoding produces `"b'1234'"` instead of `"1234"`,
  generating the wrong key.  `make_serial_key()` handles `bytes` directly to
  avoid this.

- **BabyWare compact frames are not AES.** These 12–13 byte frames use a
  proprietary algorithm; brute-forcing the PC password across 0000–9999 yields
  no valid decryptions.
