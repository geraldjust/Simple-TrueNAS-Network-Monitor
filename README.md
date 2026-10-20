# Simple TrueNAS Network Monitor

A colorful dark-themed, read-only network dashboard for TrueNAS SCALE. **Version 1.0.0.**

## Features
- 1-second live TCP traffic sampling using Linux `ss -tin` socket counters
- Per-peer NAS receive/send MB/s, grouped by client IP and protocol
- SMB, iSCSI, NFS, SSH, HTTP(S), Plex, and other TCP connections
- Network interface selector and true interface RX/TX counters
- 60-second, 5-minute, 1-hour and 24-hour history stored in SQLite
- Local-only web dashboard; no external JS/CDN or telemetry
- Responsive, vibrant dark interface, protocol filters, sortable client table

## TrueNAS SCALE installation
1. Open **Apps → Discover Apps → Install via YAML** (label varies by TrueNAS version).
2. Paste the contents of [compose.yaml](compose.yaml) and install.
3. Open **http://YOUR-TRUENAS-IP:8090**.

The image is published by GitHub Actions to `ghcr.io/geraldjust/simple-truenas-network-monitor:latest`. Wait until the **Build and publish Docker image** workflow finishes before installing. If the image is private, make its GHCR package public.

**Port 8090:** Uses host networking, so `ports:` mapping is intentionally absent. Change `PORT` if 8090 is already in use.

## What the numbers mean
- **NAS RX:** TCP payload bytes received by TrueNAS from the peer.
- **NAS TX:** TCP payload bytes sent by TrueNAS to the peer.
- **Interface RX/TX:** Actual Linux interface byte counters, including non-TCP traffic and protocol overhead.
- Rates are decimal MB/s (1 MB = 1,000,000 bytes), sampled approximately every second.
- TCP socket counters reset on reconnect. New connections start at 0 to prevent false spikes.
- The first sample needs a baseline. Protocol classification is port-based and best-effort.
- `ss` may not expose all other users' sockets without appropriate host permissions; verify results against the host's `ss -tin` output.
- Host networking and host PID visibility expose host network metadata to the container. The app makes no network changes, but the dashboard has **no authentication**: restrict port 8090 to your trusted LAN/VPN. Do not expose it to the Internet.
- This is not packet capture and does not provide reliable per-peer UDP bandwidth. IPv4/IPv6 are supported.
- History records aggregate interface throughput every 5 seconds and retains up to 24 hours. Client-level history is not persisted.
- Docker image must be rebuilt when source changes.

## Local development
```bash
docker build -t simple-truenas-network-monitor .
docker run --rm --network host --pid host -e PORT=8090 -v monitor-data:/data simple-truenas-network-monitor
```
