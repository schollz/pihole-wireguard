#!/usr/bin/env bash
set -euo pipefail

WG_PORT="${WG_PORT:-51820}"
WG_SERVER_IP="${WG_SERVER_IP:-10.66.66.1}"

CLIENT_NAME="${1:-phone}"
CLIENTS_DIR="/etc/wireguard/clients"

echo "Adding WireGuard client: ${CLIENT_NAME}"

# Validate client name
if [[ ! "${CLIENT_NAME}" =~ ^[a-zA-Z0-9_-]+$ ]]; then
    echo "Error: Client name must contain only alphanumeric characters, hyphens, and underscores."
    exit 1
fi

mkdir -p "${CLIENTS_DIR}"

# If client already exists, remove old peer from server config and reuse its IP
if [[ -f "${CLIENTS_DIR}/${CLIENT_NAME}.conf" ]]; then
    echo "  Client '${CLIENT_NAME}' already exists, overwriting..."
    # Remove old peer block from wg0.conf (comment line + [Peer] block)
    sed -i "/^# Client: ${CLIENT_NAME}$/,/^$/d" /etc/wireguard/wg0.conf
fi

# Get server info
SERVER_PUBKEY=$(cat /etc/wireguard/server_public.key)
PUBLIC_IP=$(cat /etc/wireguard/server_public_ip)

# Find next available IP in 10.66.66.0/24 (starting at .2)
USED_IPS=$(grep -oP 'AllowedIPs = 10\.66\.66\.\K[0-9]+' /etc/wireguard/wg0.conf 2>/dev/null || true)
NEXT_IP=2
while echo "${USED_IPS}" | grep -qw "${NEXT_IP}"; do
    NEXT_IP=$((NEXT_IP + 1))
    if [[ ${NEXT_IP} -ge 255 ]]; then
        echo "Error: No available IPs in subnet."
        exit 1
    fi
done
CLIENT_IP="10.66.66.${NEXT_IP}"

echo "  Assigned IP: ${CLIENT_IP}"

# Generate client keypair
CLIENT_PRIVKEY=$(wg genkey)
CLIENT_PUBKEY=$(echo "${CLIENT_PRIVKEY}" | wg pubkey)
CLIENT_PSK=$(wg genpsk)

# Write client config
cat > "${CLIENTS_DIR}/${CLIENT_NAME}.conf" << EOF
[Interface]
PrivateKey = ${CLIENT_PRIVKEY}
Address = ${CLIENT_IP}/32
DNS = ${WG_SERVER_IP}

[Peer]
PublicKey = ${SERVER_PUBKEY}
PresharedKey = ${CLIENT_PSK}
AllowedIPs = 0.0.0.0/0
Endpoint = ${PUBLIC_IP}:${WG_PORT}
PersistentKeepalive = 25
EOF

chmod 600 "${CLIENTS_DIR}/${CLIENT_NAME}.conf"

# Add peer to server config
cat >> /etc/wireguard/wg0.conf << EOF

# Client: ${CLIENT_NAME}
[Peer]
PublicKey = ${CLIENT_PUBKEY}
PresharedKey = ${CLIENT_PSK}
AllowedIPs = ${CLIENT_IP}/32
EOF

# Reload WireGuard without restarting
wg syncconf wg0 <(wg-quick strip wg0)

echo ""
echo "Client '${CLIENT_NAME}' added successfully."
echo "Config saved to: ${CLIENTS_DIR}/${CLIENT_NAME}.conf"
echo ""
echo "========================================="
echo " QR Code for ${CLIENT_NAME}"
echo "========================================="
qrencode -t ansiutf8 < "${CLIENTS_DIR}/${CLIENT_NAME}.conf"
echo "========================================="
