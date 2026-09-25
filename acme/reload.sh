#!/usr/bin/env bash
set -euo pipefail

DOMAIN="home.example.com"
ACME_CERT_DIR="$HOME/.acme.sh/${DOMAIN}_ecc"
NGINX_CERT_DIR="/home/homeassistant/.homeassistant/Certificate"
HA_CERT_DIR="/home/homeassistant/.homeassistant/docker-home-assistant-config/Certificate"

for DEST in "$NGINX_CERT_DIR" "$HA_CERT_DIR"; do
  sudo cp "$ACME_CERT_DIR/fullchain.cer" "$DEST/certificate.pem"
  sudo cp "$ACME_CERT_DIR/$DOMAIN.key" "$DEST/privateKey.key"
done

docker exec nginx nginx -s reload
docker restart home-assistant
