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

## Using a Client Config on Ubuntu 24.04

1. Install WireGuard:

```bash
sudo apt update && sudo apt install wireguard
```

2. Copy the client config to the WireGuard directory:

```bash
sudo cp wgclient.conf /etc/wireguard/wg0.conf
sudo chmod 600 /etc/wireguard/wg0.conf
```

3. Start the tunnel:

```bash
sudo wg-quick up wg0
```

4. Verify the connection:

```bash
sudo wg show
```

5. Stop the tunnel:

```bash
sudo wg-quick down wg0
```

### Auto-start on Boot

To enable the tunnel at startup:

```bash
sudo systemctl enable wg-quick@wg0
```

To disable:

```bash
sudo systemctl disable wg-quick@wg0
```
