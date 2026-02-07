# Pi-hole + WireGuard Server

Ad-blocking VPN server combining Pi-hole DNS with WireGuard. Clients connect via WireGuard and route DNS through Pi-hole for ad-free browsing.

## Setup

```bash
sudo bash setup.sh
```

This installs Zsh/Oh-My-Zsh, WireGuard, and Pi-hole in one pass. A default client named `phone` is created automatically.

## Adding Clients

```bash
sudo bash scripts/04-add-client.sh <name>
```

This generates a config at `/etc/wireguard/clients/<name>.conf` and prints a QR code to scan with the WireGuard mobile app.
