#!/usr/bin/env bash
set -euo pipefail

# Pi-hole + WireGuard Server Setup
# Must be run as root

if [[ $EUID -ne 0 ]]; then
    echo "Error: This script must be run as root (sudo bash setup.sh)"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Configuration (exported for sub-scripts)
export WG_PORT="51820"
export WG_SUBNET="10.66.66.0/24"
export WG_SERVER_IP="10.66.66.1"
export WG_SERVER_CIDR="10.66.66.1/24"
export UPSTREAM_DNS_1="1.1.1.1"
export UPSTREAM_DNS_2="1.0.0.1"

echo "========================================="
echo " Pi-hole + WireGuard Server Setup"
echo "========================================="
echo ""
echo "Configuration:"
echo "  WireGuard port:  ${WG_PORT}/udp"
echo "  VPN subnet:      ${WG_SUBNET}"
echo "  Server VPN IP:   ${WG_SERVER_IP}"
echo "  Upstream DNS:    ${UPSTREAM_DNS_1}, ${UPSTREAM_DNS_2}"
echo ""

# Step 1: System setup (packages, zsh, oh-my-zsh)
echo ">>> Step 1/4: System setup..."
bash "${SCRIPT_DIR}/scripts/01-system-setup.sh"
echo ">>> Step 1/4: Complete."
echo ""

# Step 2: WireGuard (must come before Pi-hole so wg0 exists)
echo ">>> Step 2/4: WireGuard setup..."
bash "${SCRIPT_DIR}/scripts/03-wireguard-setup.sh"
echo ">>> Step 2/4: Complete."
echo ""

# Step 3: Pi-hole (binds to wg0 interface)
echo ">>> Step 3/4: Pi-hole install..."
bash "${SCRIPT_DIR}/scripts/02-pihole-install.sh"
echo ">>> Step 3/4: Complete."
echo ""

# Step 4: Create first VPN client
echo ">>> Step 4/4: Creating first VPN client..."
bash "${SCRIPT_DIR}/scripts/04-add-client.sh" phone
echo ">>> Step 4/4: Complete."
echo ""

echo "========================================="
echo " Setup Complete!"
echo "========================================="
echo ""
echo "Verification commands:"
echo "  wg show                  - Check WireGuard status"
echo "  pihole status            - Check Pi-hole status"
echo "  zsh --version            - Check zsh"
echo ""
echo "To add more VPN clients:"
echo "  sudo bash ${SCRIPT_DIR}/scripts/04-add-client.sh <client-name>"
echo ""
