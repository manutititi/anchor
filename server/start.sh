#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env"

# ── Colors ────────────────────────────────────────────────────────────────────
bold='\033[1m'
dim='\033[2m'
cyan='\033[36m'
green='\033[32m'
yellow='\033[33m'
red='\033[31m'
reset='\033[0m'

header()  { echo -e "\n${cyan}${bold}$1${reset}"; }
info()    { echo -e "  ${dim}$1${reset}"; }
ok()      { echo -e "  ${green}[ok]${reset} $1"; }
warn()    { echo -e "  ${yellow}[!]${reset} $1"; }

# ── ask: prompt with default ──────────────────────────────────────────────────
# usage: ask "Prompt text" DEFAULT_VALUE
# result goes into $REPLY
ask() {
  local prompt="$1" default="$2"
  echo -en "  ${bold}$prompt${reset} ${dim}[$default]${reset}: "
  read -r REPLY
  REPLY="${REPLY:-$default}"
}

# ── ask_secret: like ask but generates a random default ───────────────────────
ask_secret() {
  local prompt="$1"
  local generated
  generated="$(openssl rand -base64 32)"
  echo -en "  ${bold}$prompt${reset} ${dim}[auto-generate]${reset}: "
  read -r REPLY
  REPLY="${REPLY:-$generated}"
}

echo ""
echo -e "${cyan}${bold}Anchor Server — Setup${reset}"
echo ""

# =============================================================================
#  Check prerequisites
# =============================================================================
header "Checking prerequisites..."

for cmd in docker openssl; do
  if command -v "$cmd" &>/dev/null; then
    ok "$cmd found"
  else
    echo -e "  ${red}[x]${reset} $cmd not found — please install it first."
    exit 1
  fi
done

if docker compose version &>/dev/null; then
  ok "docker compose plugin found"
else
  echo -e "  ${red}[x]${reset} docker compose plugin not found (need Docker Compose V2)."
  exit 1
fi

# =============================================================================
#  If .env already exists, ask what to do
# =============================================================================
RECONFIGURE=false

if [ -f "$ENV_FILE" ]; then
  echo ""
  warn ".env already exists at $ENV_FILE"
  echo -en "  ${bold}Reconfigure? (y/N)${reset}: "
  read -r yn
  if [[ "$yn" =~ ^[Yy] ]]; then
    cp "$ENV_FILE" "$ENV_FILE.bak.$(date +%s)"
    ok "Backup saved as .env.bak.*"
    RECONFIGURE=true
  else
    ok "Using existing .env"
  fi
else
  RECONFIGURE=true
fi

# =============================================================================
#  Interactive configuration
# =============================================================================
if [ "$RECONFIGURE" = true ]; then

  # ── General ──────────────────────────────────────────────────────────────
  header "1/4  General"
  info "Basic server settings."
  echo ""

  ask "Timezone (e.g. Europe/Madrid, America/New_York, UTC)" "UTC"
  CFG_TZ="$REPLY"

  ask "PUID (host user ID for file permissions)" "$(id -u)"
  CFG_PUID="$REPLY"

  ask "PGID (host group ID for file permissions)" "$(id -g)"
  CFG_PGID="$REPLY"

  # ── Network / VPN ──────────────────────────────────────────────────────
  header "2/4  Network & VPN"
  info "WireGuard tunnel and SPA knock configuration."
  info "The server is only reachable through the VPN tunnel."
  echo ""

  # Detect public IP
  DEFAULT_IP="auto"
  DETECTED_IP=""
  if command -v curl &>/dev/null; then
    DETECTED_IP="$(curl -sf --max-time 3 https://ifconfig.me 2>/dev/null || true)"
  fi
  if [ -n "$DETECTED_IP" ]; then
    DEFAULT_IP="$DETECTED_IP"
    info "Detected public IP: $DETECTED_IP"
  fi

  ask "Server public IP or domain (clients connect here)" "$DEFAULT_IP"
  CFG_SERVERURL="$REPLY"

  ask "WireGuard port (UDP, must be open in firewall)" "51820"
  CFG_SERVERPORT="$REPLY"

  ask "VPN subnet" "10.13.13.0"
  CFG_SUBNET="$REPLY"

  ask "SPA knock port (UDP, must be open in firewall)" "62201"
  CFG_KNOCK="$REPLY"

  ask "DNS pushed to VPN clients (empty = none)" ""
  CFG_PEERDNS="$REPLY"

  # Default allowed IPs = server gateway inside the subnet
  DEFAULT_ALLOWEDIPS="${CFG_SUBNET%.*}.1/32"
  ask "Allowed IPs for clients (split-tunnel default, 0.0.0.0/0 = full tunnel)" "$DEFAULT_ALLOWEDIPS"
  CFG_ALLOWEDIPS="$REPLY"

  ask "Static admin peers (comma-separated names)" "peer1"
  CFG_PEERS="$REPLY"

  # ── Database ──────────────────────────────────────────────────────────
  header "3/4  MongoDB"
  info "Credentials for the internal MongoDB instance."
  info "Only accessible from inside the Docker network."
  echo ""

  ask "MongoDB admin username" "ancadmin"
  CFG_MONGO_USER="$REPLY"

  ask "MongoDB admin password" "ancpass"
  CFG_MONGO_PASS="$REPLY"

  CFG_MONGO_DB="anchor"

  # ── Secrets ────────────────────────────────────────────────────────────
  header "4/4  Secrets"
  info "Cryptographic keys. Press Enter to auto-generate (recommended)."
  echo ""

  ask_secret "JWT signing secret"
  CFG_JWT="$REPLY"

  ask_secret "Vault master key (AES-256, CHANGING THIS INVALIDATES ALL SECRETS)"
  CFG_VAULT="$REPLY"

  ask_secret "WireGuard sidecar API key"
  CFG_WG_API="$REPLY"

  info "Generating SPA v2 X25519 keypair..."
  CFG_SPA_PRIV="$(openssl genpkey -algorithm X25519 2>/dev/null | openssl pkey -outform DER 2>/dev/null | tail -c 32 | base64)"
  ok "X25519 private key generated"

  # ── Write .env ─────────────────────────────────────────────────────────
  header "Writing .env..."

  cat > "$ENV_FILE" <<EOF
# =============================================================
# Anchor Server — generated by start.sh on $(date -u +"%Y-%m-%dT%H:%M:%SZ")
# NEVER commit this file to version control.
# =============================================================

# ── General ───────────────────────────────────────────────────
TZ=$CFG_TZ
PUID=$CFG_PUID
PGID=$CFG_PGID

# ── Network & VPN ─────────────────────────────────────────────
SERVERURL=$CFG_SERVERURL
SERVERPORT=$CFG_SERVERPORT
INTERNAL_SUBNET=$CFG_SUBNET
KNOCK_PORT=$CFG_KNOCK
PEERDNS=$CFG_PEERDNS
ALLOWEDIPS=$CFG_ALLOWEDIPS
PEERS=$CFG_PEERS

# ── MongoDB ───────────────────────────────────────────────────
MONGO_USER=$CFG_MONGO_USER
MONGO_PASS=$CFG_MONGO_PASS
MONGO_DB=$CFG_MONGO_DB

# ── Secrets ───────────────────────────────────────────────────
JWT_SECRET=$CFG_JWT
VAULT_MASTER_KEY=$CFG_VAULT
WG_API_KEY=$CFG_WG_API
SPA_PRIVKEY_B64=$CFG_SPA_PRIV
EOF

  chmod 600 "$ENV_FILE"
  ok ".env written with mode 600"
fi

# =============================================================================
#  Review before launch
# =============================================================================
header "Configuration summary"
echo ""
echo -e "  ${dim}File:${reset}     $ENV_FILE"
# Show non-secret values
while IFS='=' read -r key val; do
  [[ "$key" =~ ^#.*$ || -z "$key" ]] && continue
  case "$key" in
    JWT_SECRET|VAULT_MASTER_KEY|WG_API_KEY|SPA_PRIVKEY_B64|MONGO_PASS)
      echo -e "  ${bold}$key${reset} = ${dim}********${reset}" ;;
    *)
      echo -e "  ${bold}$key${reset} = $val" ;;
  esac
done < "$ENV_FILE"

echo ""
echo -en "  ${bold}Deploy now? (Y/n)${reset}: "
read -r yn
if [[ "$yn" =~ ^[Nn] ]]; then
  echo ""
  info "Aborted. Run this script again when ready, or:"
  info "  cd $SCRIPT_DIR && docker compose --env-file .env up -d --build"
  exit 0
fi

# =============================================================================
#  Deploy
# =============================================================================
header "Starting services..."
cd "$SCRIPT_DIR"
docker compose --env-file .env up -d --build

# ── Wait for health ──────────────────────────────────────────────────────────
header "Waiting for anc-server..."
echo -n "  "
HEALTHY=false
for i in $(seq 1 30); do
  # Port 17017 is not published — check via Docker's own healthcheck
  STATUS="$(docker inspect --format='{{.State.Health.Status}}' anc-server 2>/dev/null || echo "starting")"
  if [ "$STATUS" = "healthy" ]; then
    HEALTHY=true
    break
  fi
  echo -n "."
  sleep 2
done
echo ""

if [ "$HEALTHY" = true ]; then
  ok "anc-server is healthy"
else
  warn "Health check timed out — check logs: docker compose logs anc-server"
fi

# =============================================================================
#  Summary
# =============================================================================
# Read subnet from .env if not set from interactive
if [ -z "${CFG_SUBNET:-}" ]; then
  CFG_SUBNET="$(grep '^INTERNAL_SUBNET=' "$ENV_FILE" | cut -d= -f2)"
fi
GW="${CFG_SUBNET%.*}.1"

echo ""
echo -e "${green}${bold}"
echo "  ┌──────────────────────────────────────────────────┐"
echo "  │  Anchor Server deployed                          │"
echo "  ├──────────────────────────────────────────────────┤"
echo "  │                                                  │"
echo "  │  VPN API:   http://$GW:17017              │"
echo "  │  Docs:      http://$GW:17017/docs         │"
echo "  │  Dashboard: http://$GW:17017/dashboard    │"
echo "  │  Health:    http://$GW:17017/health       │"
echo "  │                                                  │"
echo "  │  WireGuard: 0.0.0.0:${CFG_SERVERPORT:-51820}/udp              │"
echo "  │  SPA Knock: 0.0.0.0:${CFG_KNOCK:-62201}/udp              │"
echo "  │                                                  │"
echo "  └──────────────────────────────────────────────────┘"
echo -e "${reset}"
echo -e "  ${bold}Next steps:${reset}"
echo ""
echo "  1. Import admin peer config from ./wireguard/config/peer_peer1/"
echo "     into your WireGuard client and connect to the VPN."
echo ""
echo "  2. Create your first admin user (from inside VPN):"
echo ""
echo -e "     ${dim}curl -X POST http://$GW:17017/admin/users \\${reset}"
echo -e "     ${dim}  -H 'Content-Type: application/json' \\${reset}"
echo -e "     ${dim}  -d '{\"username\": \"admin\", \"password\": \"changeme\", \"groups\": [\"admins\"]}'${reset}"
echo ""
echo "  3. Configure CLI:  anc login --server http://$GW:17017"
echo ""
echo -e "  ${dim}Logs:    docker compose logs -f${reset}"
echo -e "  ${dim}Stop:    docker compose down${reset}"
echo -e "  ${dim}Restart: docker compose restart${reset}"
echo ""
