#!/usr/bin/env bash
# Provisions a Hetzner VPS for mm-forums-vector-db.
# Usage: ./deploy/provision_hetzner.sh
# Required env vars:
#   HCLOUD_TOKEN   - Hetzner Cloud API token
#   HCLOUD_SSH_KEY - Name of SSH key already registered in your Hetzner project
#   DOMAIN         - Hostname that will point to this server (e.g. search.example.com)
# Optional:
#   HCLOUD_SERVER_TYPE   - default: cx22
#   HCLOUD_LOCATION      - default: nbg1
#   HCLOUD_SERVER_NAME   - default: mm-forums

set -euo pipefail

: "${HCLOUD_TOKEN:?HCLOUD_TOKEN is required}"
: "${HCLOUD_SSH_KEY:?HCLOUD_SSH_KEY is required}"
: "${DOMAIN:?DOMAIN is required}"

SERVER_TYPE="${HCLOUD_SERVER_TYPE:-cx22}"
LOCATION="${HCLOUD_LOCATION:-nbg1}"
SERVER_NAME="${HCLOUD_SERVER_NAME:-mm-forums}"
IMAGE="ubuntu-24.04"
CLOUD_INIT="$(dirname "$0")/cloud-init.yml"

API="https://api.hetzner.cloud/v1"
AUTH="Authorization: Bearer ${HCLOUD_TOKEN}"

echo "==> Looking up SSH key '${HCLOUD_SSH_KEY}'..."
SSH_KEY_ID=$(curl -fsSL -H "$AUTH" "${API}/ssh_keys" \
  | python3 -c "
import sys, json
keys = json.load(sys.stdin)['ssh_keys']
match = [k for k in keys if k['name'] == '${HCLOUD_SSH_KEY}']
if not match:
    print('ERROR: SSH key not found', file=sys.stderr)
    sys.exit(1)
print(match[0]['id'])
")
echo "    SSH key ID: ${SSH_KEY_ID}"

echo "==> Creating server '${SERVER_NAME}' (${SERVER_TYPE}, ${LOCATION}, ${IMAGE})..."
RESPONSE=$(curl -fsSL -X POST "${API}/servers" \
  -H "$AUTH" \
  -H "Content-Type: application/json" \
  -d "{
    \"name\": \"${SERVER_NAME}\",
    \"server_type\": \"${SERVER_TYPE}\",
    \"image\": \"${IMAGE}\",
    \"location\": \"${LOCATION}\",
    \"ssh_keys\": [${SSH_KEY_ID}],
    \"user_data\": $(python3 -c "import json, sys; print(json.dumps(open('${CLOUD_INIT}').read()))"),
    \"labels\": {
      \"project\": \"mm-forums-vector-db\"
    }
  }")

SERVER_ID=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['server']['id'])")
IPV4=$(echo "$RESPONSE"     | python3 -c "import sys,json; print(json.load(sys.stdin)['server']['public_net']['ipv4']['ip'])")

echo ""
echo "==> Server created!"
echo "    ID:   ${SERVER_ID}"
echo "    IPv4: ${IPV4}"
echo ""
echo "==> Next steps:"
echo "    1. Add an A record:  ${DOMAIN} -> ${IPV4}"
echo "    2. Wait ~60 s for cloud-init to finish, then SSH in:"
echo "       ssh root@${IPV4}"
echo "    3. Clone your repo:"
echo "       git clone <your-repo-url> /srv/mm-forums"
echo "    4. Copy your .env file to /srv/mm-forums/.env"
echo "    5. Come back here — SSL provisioning is the next step."
