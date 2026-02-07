#!/usr/bin/env bash
set -euo pipefail

WG_PORT="${WG_PORT:-51820}"
WG_SERVER_CIDR="${WG_SERVER_CIDR:-10.66.66.1/24}"

echo "Installing WireGuard..."
apt install -y wireguard

echo "Generating server keypair..."
umask 077
mkdir -p /etc/wireguard
wg genkey | tee /etc/wireguard/server_private.key | wg pubkey > /etc/wireguard/server_public.key
SERVER_PRIVKEY=$(cat /etc/wireguard/server_private.key)
SERVER_PUBKEY=$(cat /etc/wireguard/server_public.key)

echo "Detecting public IP..."
PUBLIC_IP=$(curl -s ifconfig.me)
echo "  Public IP: ${PUBLIC_IP}"

echo "Detecting default network interface..."
DEFAULT_IFACE=$(ip -4 route show default | awk '{print $5}' | head -1)
echo "  Default interface: ${DEFAULT_IFACE}"

echo "Writing /etc/wireguard/wg0.conf..."
cat > /etc/wireguard/wg0.conf << EOF
[Interface]
Address = ${WG_SERVER_CIDR}
ListenPort = ${WG_PORT}
PrivateKey = ${SERVER_PRIVKEY}

PostUp = iptables -A FORWARD -i wg0 -j ACCEPT; iptables -A FORWARD -o wg0 -j ACCEPT; iptables -t nat -A POSTROUTING -o ${DEFAULT_IFACE} -j MASQUERADE
PostDown = iptables -D FORWARD -i wg0 -j ACCEPT; iptables -D FORWARD -o wg0 -j ACCEPT; iptables -t nat -D POSTROUTING -o ${DEFAULT_IFACE} -j MASQUERADE
EOF

chmod 600 /etc/wireguard/wg0.conf

# Save public IP and interface for later use by add-client
echo "${PUBLIC_IP}" > /etc/wireguard/server_public_ip
echo "${DEFAULT_IFACE}" > /etc/wireguard/server_default_iface

echo "Enabling IP forwarding..."
sysctl -w net.ipv4.ip_forward=1
if ! grep -q '^net.ipv4.ip_forward=1' /etc/sysctl.conf; then
    echo 'net.ipv4.ip_forward=1' >> /etc/sysctl.conf
fi

echo "Enabling and starting WireGuard..."
systemctl enable wg-quick@wg0
systemctl start wg-quick@wg0

echo "Configuring firewall..."
if command -v ufw &>/dev/null && ufw status | grep -q "active"; then
    ufw allow "${WG_PORT}/udp"
    echo "  Opened port ${WG_PORT}/udp in ufw."
else
    echo "  ufw not active, skipping firewall rule."
fi

echo "WireGuard setup complete."
echo "  Server public key: ${SERVER_PUBKEY}"
