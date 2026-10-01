#!/usr/bin/env python3
"""
One-time (but safe to re-run) setup: creates a long-lived Home Assistant
access token scoped to the DEMO homeassistant-demo instance - never the
real production token - and pushes it into the running demo Grafana's
"Home Assistant" (Infinity) datasource live, over Grafana's own HTTP API.

Patches the datasource live rather than editing
demo/grafana/provisioning/datasources/datasources.yml + restarting the
container: this script needs to run unattended in contexts with no Docker
access at all (a GitHub Codespaces devcontainer's lifecycle hooks run
INSIDE a service container, no docker socket available there - see
publish/templates/.devcontainer/grafana/), not just from a shell with
full access to the compose stack. The API approach works identically in
both contexts.

Usage:
    python demo/tools/setup_demo_grafana_token.py \
        --ha-base-url http://localhost:8124 \
        --grafana-base-url http://localhost:3001 \
        --username <demo-ha-username> --password <demo-ha-password>

Defaults match demo/docker-compose.demo.yml's published ports for local
runs; a Codespaces devcontainer overrides both to the in-network service
hostnames (see grafana/devcontainer.json).
"""
from __future__ import annotations

import argparse
import sys

try:
    import aiohttp
    import asyncio
except ImportError:
    print("ERROR: aiohttp is required (pip install aiohttp)", file=sys.stderr)
    sys.exit(1)

GRAFANA_ADMIN_USER = "admin"
GRAFANA_ADMIN_PASSWORD = "demo"  # matches GF_SECURITY_ADMIN_PASSWORD in the compose file
DATASOURCE_UID = "homeassistant-api"
TOKEN_CLIENT_NAME = "grafana-demo"


async def get_ha_access_token(session: aiohttp.ClientSession, base_url: str, username: str,
                               password: str, client_id: str) -> str | None:
    async with session.post(
        f"{base_url}/auth/login_flow",
        json={"client_id": client_id, "handler": ["homeassistant", None], "redirect_uri": client_id},
    ) as resp:
        flow = await resp.json()
    flow_id = flow.get("flow_id")
    if not flow_id:
        print("login_flow init failed:", resp.status, flow)
        return None
    async with session.post(
        f"{base_url}/auth/login_flow/{flow_id}",
        json={"client_id": client_id, "username": username, "password": password},
    ) as resp:
        result = await resp.json()
    if result.get("type") != "create_entry":
        print("login failed:", resp.status, result)
        return None
    auth_code = result["result"]
    async with session.post(
        f"{base_url}/auth/token",
        data={"grant_type": "authorization_code", "code": auth_code, "client_id": client_id},
    ) as resp:
        token_data = await resp.json()
    if resp.status != 200:
        print("token exchange failed:", resp.status, token_data)
        return None
    return token_data["access_token"]


async def create_ha_long_lived_token(session: aiohttp.ClientSession, base_url: str,
                                      access_token: str) -> str | None:
    # Confirmed live (2026-09-22): HA's auth/long_lived_access_token websocket
    # command raises ValueError(f"{client_name} already exists") - surfaced to
    # the caller as a bare "Unknown error" - if a refresh token with this
    # client_name already exists for the user. That's not a one-off: the
    # baked demo image itself boots HA once during its own build (to drive
    # onboarding), which fires this same automation and creates one, so
    # EVERY container started from that image already has one before this
    # script ever runs for the first time - not just on a genuine re-run.
    # Delete any existing one by this client_name first so this script is
    # actually safe to re-run, matching what its own docstring already
    # claims.
    ws_url = base_url.replace("https://", "wss://", 1).replace("http://", "ws://", 1) + "/api/websocket"
    async with session.ws_connect(ws_url, ssl=False) as ws:
        await ws.receive_json()  # auth_required
        await ws.send_json({"type": "auth", "access_token": access_token})
        auth_result = await ws.receive_json()
        if auth_result.get("type") != "auth_ok":
            print(f"HA websocket auth failed - {auth_result}")
            return None

        await ws.send_json({"id": 1, "type": "auth/refresh_tokens"})
        tokens_result = await ws.receive_json()
        if not tokens_result.get("success"):
            print(f"HA refresh token listing failed - {tokens_result}")
            return None
        existing = [t for t in tokens_result["result"] if t.get("client_name") == TOKEN_CLIENT_NAME]
        if existing:
            await ws.send_json({
                "id": 2,
                "type": "auth/delete_refresh_token",
                "refresh_token_id": existing[0]["id"],
            })
            delete_result = await ws.receive_json()
            if not delete_result.get("success"):
                print(f"HA refresh token deletion failed - {delete_result}")
                return None

        await ws.send_json({
            "id": 3,
            "type": "auth/long_lived_access_token",
            "client_name": TOKEN_CLIENT_NAME,
            "lifespan": 3650,
        })
        result = await ws.receive_json()
        if not result.get("success"):
            print(f"HA long-lived token creation failed - {result}")
            return None
        return result["result"]


async def patch_grafana_datasource_token(session: aiohttp.ClientSession, grafana_base_url: str,
                                          ha_token: str) -> bool:
    auth = aiohttp.BasicAuth(GRAFANA_ADMIN_USER, GRAFANA_ADMIN_PASSWORD)
    async with session.get(
        f"{grafana_base_url}/api/datasources/uid/{DATASOURCE_UID}", auth=auth,
    ) as resp:
        datasource = await resp.json()
    if resp.status != 200:
        print(f"fetching datasource failed: {resp.status} {datasource}")
        return False
    datasource.setdefault("secureJsonData", {})["bearerToken"] = ha_token
    async with session.put(
        f"{grafana_base_url}/api/datasources/uid/{DATASOURCE_UID}", auth=auth, json=datasource,
    ) as resp:
        result = await resp.json()
    if resp.status != 200:
        print(f"updating datasource failed: {resp.status} {result}")
        return False
    return True


async def main_async(args: argparse.Namespace) -> int:
    client_id = f"{args.ha_base_url}/"
    async with aiohttp.ClientSession() as session:
        access_token = await get_ha_access_token(
            session, args.ha_base_url, args.username, args.password, client_id)
        if not access_token:
            return 1
        ha_token = await create_ha_long_lived_token(session, args.ha_base_url, access_token)
        if not ha_token:
            return 1
        if not await patch_grafana_datasource_token(session, args.grafana_base_url, ha_token):
            return 1
    print("Home Assistant datasource token updated - no restart needed.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ha-base-url", default="http://localhost:8124",
                         help="The demo Home Assistant instance, not the real one")
    parser.add_argument("--grafana-base-url", default="http://localhost:3001")
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", required=True)
    args = parser.parse_args()
    sys.exit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()
