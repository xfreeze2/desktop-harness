# desktop-harness tunnel (SDTP)

Optional **C** encrypted UDP tunnel for remote reachability.

Local `desktop-harness` (AX + real mouse/keyboard) stays the default.
This component exists so a controller on another machine can open a
mutually-authenticated, forward-secret path to the Mac — without
putting raw control traffic on the public internet.

**Protocol:** SDTP v1 (same wire format as [secdogie-tunnel](https://github.com/Larrydev-cpp/secdogie/tree/main/tunnel)).
The two implementations can talk to each other.

**Crypto (libsodium only):**
- Identity: long-term X25519 keypairs (exchanged out of band)
- Handshake: 1-RTT triple-DH (Noise IK–style), mutual auth + forward secrecy
- Data: XChaCha20-Poly1305 AEAD, sliding replay window
- Optional **hub** mode: one public node terminates many client tunnels

See [PROTOCOL.md](PROTOCOL.md) for the full design and known limitations.
This code has **not** had an independent cryptographic audit — treat it as
personal / lab infrastructure, not a compliance control.

---

## Why it lives here

```
remote agent / controller
        │  SDTP (encrypted UDP)
        ▼
   [this tunnel]  ← optional
        │  private IP / local socket
        ▼
desktop-harness daemon  →  real Mac (AX + CGEvent)
```

Without the tunnel, the harness is local-only (correct default).
With it, you can drive a Mac you own across a network you control.

---

## Build

Requires a C compiler, CMake, and **libsodium** (dev headers + pkg-config).

```sh
# macOS (Homebrew)
brew install cmake libsodium pkg-config

# Debian/Ubuntu
sudo apt-get install -y build-essential cmake libsodium-dev pkg-config

cmake -S tunnel -B tunnel/build
cmake --build tunnel/build -j
./tunnel/build/dh-tunnel          # prints usage
./tunnel/build/test_protocol      # crypto / handshake / replay unit tests
```

**TUN device:** the current data plane uses a Linux `tun` interface
(`CAP_NET_ADMIN` / root). On macOS the binary still builds and can run the
handshake + userspace path; full utun support is a follow-up. For a pure
Mac-to-Mac lab today, run the tunnel on a Linux jump host or use the
hub mode with a Linux hub.

---

## Quick use (point-to-point)

```sh
# On each machine
./tunnel/build/dh-tunnel genkey server.key   # public key printed to stderr
./tunnel/build/dh-tunnel genkey client.key
```

Exchange the two public keys out of band. Example configs:

**server.conf** (reachable side):
```
private_key = <server private key>
peer_public_key = <client public key>
address = 10.66.0.1/24
listen_port = 51820
```

**client.conf**:
```
private_key = <client private key>
peer_public_key = <server public key>
address = 10.66.0.2/24
endpoint = <server-ip>:51820
```

```sh
sudo ./tunnel/build/dh-tunnel server server.conf
sudo ./tunnel/build/dh-tunnel client client.conf
```

When both logs show `handshake completed`, traffic to the peer’s tunnel
address is encrypted over UDP.

### Hub mode (one public node, many clients)

```
# hub.conf
private_key = <hub private key>
address     = 10.66.0.1/24
listen_port = 51820
peer = <client1 public key> 10.66.0.2
peer = <client2 public key> 10.66.0.3
```

```sh
sudo ./tunnel/build/dh-tunnel hub hub.conf
```

Clients are ordinary `client` configs pointing at the hub. The hub
decrypts to route (hub-and-spoke, not end-to-end between clients).

---

## Layout

```
tunnel/
  PROTOCOL.md     wire format + crypto design
  CMakeLists.txt
  include/        public headers (sdtp.h, crypto, handshake, …)
  src/            implementation (no malloc in the hot path)
  tests/          protocol unit tests + packet fuzzer + recv bench
```

Binary name: **`dh-tunnel`** (avoids clashing with `secdogie-tunnel` on PATH).

---

## Safety notes for desktop-harness users

- The tunnel only moves **bytes**. It does not grant Accessibility by itself.
- Once a remote party can reach the Mac over the tunnel, treat that path
  like giving them shell on a private network segment. Combine with the
  existing harness gates (`DH_ALLOW_SENSITIVE`, audit log, daemon token).
- Prefer short-lived sessions; there is no automatic rekey yet (restart
  both sides for fresh forward secrecy).
- Do not expose the listen port on the public internet without a firewall
  and a clear threat model.

---

## Status

| Item | State |
|------|--------|
| SDTP wire protocol (interop with secdogie) | yes |
| Point-to-point + hub | yes |
| Linux TUN data plane | yes |
| macOS utun | planned |
| Control-plane RPC on top of tunnel | planned (feed commands into local daemon) |
| Independent crypto audit | no |
