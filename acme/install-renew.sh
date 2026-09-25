#!/usr/bin/env bash
set -euo pipefail

DOMAIN="home.example.com"
ACME_DIR="/home/homeassistant/.homeassistant/acme"
ACME_HOME="$HOME/.acme.sh"
ACME="$ACME_HOME/acme.sh"
STRATO_IMAGE="strato-dns-api:local"
LE_EMAIL="redacted@example.com"

if ! docker image inspect "$STRATO_IMAGE" >/dev/null 2>&1; then
  DOCKER_BUILDKIT=0 docker build -t "$STRATO_IMAGE" - <<'DOCKERFILE'
FROM python:3.11-slim
RUN pip install --no-cache-dir strato-dns-api
RUN printf "%s\n" \
      "from strato_dns_api.strato_dns_api import StratoDnsApi" \
      "StratoDnsApi.API_URLS['uk'] = 'https://www.strato-hosting.co.uk/apps/CustomerService'" \
      > "$(python -c 'import site; print(site.getsitepackages()[0])')/sitecustomize.py"
ENTRYPOINT ["python", "-m", "strato_dns_api"]
DOCKERFILE
fi

if [ ! -x "$ACME" ]; then
  curl https://get.acme.sh | sh -s email="$LE_EMAIL"
fi

mkdir -p "$ACME_HOME/dnsapi"
cp "$ACME_DIR/dns_strato.sh" "$ACME_HOME/dnsapi/dns_strato.sh"
cp "$ACME_DIR/reload.sh" "$ACME_HOME/reload.sh"
chmod +x "$ACME_HOME/dnsapi/dns_strato.sh" "$ACME_HOME/reload.sh"

if [ ! -d "$ACME_HOME/${DOMAIN}_ecc" ]; then
  echo "No existing cert tracked for $DOMAIN - issuing for the first time (Let's Encrypt staging)"
  "$ACME" --issue --server letsencrypt_test --dns dns_strato -d "$DOMAIN" --reloadcmd "$ACME_HOME/reload.sh"
else
  echo "Cert for $DOMAIN already tracked by acme.sh - leaving renewal to its own cron"
fi
