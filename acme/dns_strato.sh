#!/usr/bin/env bash

STRATO_CONFIG_DIR="${STRATO_CONFIG_DIR:-/home/homeassistant/.homeassistant/acme}"
STRATO_IMAGE="${STRATO_IMAGE:-strato-dns-api:local}"

_strato_dns_api() {
  docker run --rm -v "$STRATO_CONFIG_DIR:/cfg:ro" "$STRATO_IMAGE" -c /cfg/strato-config.json "$@"
}

dns_strato_add() {
  fulldomain=$1
  txtvalue=$2
  _info "strato: adding TXT record for $fulldomain"
  _strato_dns_api del-record -t TXT -n "$fulldomain" >/dev/null 2>&1 || true
  if ! _strato_dns_api add-record -t TXT -n "$fulldomain" -v "$txtvalue"; then
    _err "strato: failed to add TXT record for $fulldomain"
    return 1
  fi
  return 0
}

dns_strato_rm() {
  fulldomain=$1
  txtvalue=$2
  _info "strato: removing TXT record for $fulldomain"
  if ! _strato_dns_api del-record -t TXT -n "$fulldomain" -v "$txtvalue"; then
    _err "strato: failed to remove TXT record for $fulldomain (non-fatal)"
  fi
  return 0
}
