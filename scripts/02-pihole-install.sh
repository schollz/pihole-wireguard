#!/usr/bin/env bash
set -euo pipefail

WG_SERVER_IP="${WG_SERVER_IP:-10.66.66.1}"
WG_SERVER_CIDR="${WG_SERVER_CIDR:-10.66.66.1/24}"
UPSTREAM_DNS_1="${UPSTREAM_DNS_1:-1.1.1.1}"
UPSTREAM_DNS_2="${UPSTREAM_DNS_2:-1.0.0.1}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIGS_DIR="$(dirname "${SCRIPT_DIR}")/configs"

echo "Generating Pi-hole web admin password..."
PIHOLE_PASS=$(openssl rand -base64 16)
PIHOLE_PASS_DOUBLE_SHA256=$(echo -n "${PIHOLE_PASS}" | sha256sum | awk '{print $1}' | sha256sum | awk '{print $1}')

echo "Writing setupVars.conf..."
mkdir -p /etc/pihole
cat > /etc/pihole/setupVars.conf << EOF
PIHOLE_INTERFACE=wg0
PIHOLE_DNS_1=${UPSTREAM_DNS_1}
PIHOLE_DNS_2=${UPSTREAM_DNS_2}
QUERY_LOGGING=true
INSTALL_WEB_SERVER=true
INSTALL_WEB_INTERFACE=true
LIGHTTPD_ENABLED=true
CACHE_SIZE=10000
DNS_FQDN_REQUIRED=true
DNS_BOGUS_PRIV=true
DNSMASQ_LISTENING=local
WEBPASSWORD=${PIHOLE_PASS_DOUBLE_SHA256}
BLOCKING_ENABLED=true
IPV4_ADDRESS=${WG_SERVER_CIDR}
IPV6_ADDRESS=
PIHOLE_DNS_3=
PIHOLE_DNS_4=
EOF

# Also save a copy to the project configs dir
cp /etc/pihole/setupVars.conf "${CONFIGS_DIR}/setupVars.conf"

echo "Running Pi-hole unattended install..."
curl -sSL https://install.pi-hole.net | bash /dev/stdin --unattended

echo ""
echo "========================================="
echo " Pi-hole Admin Credentials"
echo "========================================="
echo "  Web interface: http://${WG_SERVER_IP}/admin"
echo "  Password:      ${PIHOLE_PASS}"
echo "========================================="
echo ""
echo "Save this password! You can change it later with: pihole -a -p"
echo ""
echo "Pi-hole install complete."
