"""
One-time (idempotent, safe to re-run) post-deploy setup: completes onboarding
if it isn't done yet, then creates the 18 local_file camera config entries
the real dashboard references, plus the moon config entry (see
ensure_moon_integration below - same config_flow-only problem as cameras,
just with no fields to fill in).

Why cameras can't just be YAML like everything else in demo/generated/: the
local_file integration's manifest.json declares "config_flow": true with no
legacy platform fallback in this HA version - `camera: - platform:
local_file` is rejected outright at boot ("does not support platform setup,
please remove it from your config"). There's no template.py for camera
either. The only way to create these entities is driving the config_entries
API against a *running* instance, which can't happen at config-generation
time. Onboarding has the same shape of problem (no YAML path at all) - both
need a live, running instance, so both live in this one script.

Usage (from the repo root, or point --base-url elsewhere):
    python demo/tools/setup_demo_cameras.py --username demo --password demo

Run it again any time - already-completed onboarding and already-created
cameras are both detected and skipped, nothing gets duplicated or redone.
Used directly by demo/tools/bake_demo_image.sh to produce a fully
self-contained image; also fine to run by hand against docker-compose.demo.yml.
"""
import argparse
import asyncio
import json
import shutil
import sys
from pathlib import Path

try:
    import aiohttp
except ImportError:
    print("Needs aiohttp - if running outside the HA container: pip install aiohttp")
    sys.exit(1)

try:
    import yaml
except ImportError:
    print("Needs PyYAML - if running outside the HA container: pip install pyyaml")
    sys.exit(1)

REPO_ROOT = Path(__file__).resolve().parents[2]
CAMERA_MAP_FILE = REPO_ROOT / "demo" / "generated" / "cameras.json"
WWW_DIR = REPO_ROOT / "demo" / "www"
CUSTOMIZE_FILE = REPO_ROOT / "demo" / "customize.yaml"


def title(object_id: str) -> str:
    """The real (non-Simpsons) title for a camera object_id - local_file's
    config flow needs this to suggest the matching entity_id (e.g.
    "Bart Simpson Room Camera" -> camera.bart_simpson_room_camera), same rule as every other
    domain in generate_demo_entities.py. Duplicated here (not imported) since
    that file isn't a package and this needs only this one small, pure
    function - deliberately never written to cameras.json or any other
    published file, only used transiently as this script runs. The cosmetic
    Simpsons swap for on-screen display still happens via the
    customize.yaml override generate_demo_entities.py already queues."""
    words = object_id.replace("_", " ").split()
    small = {"a", "an", "the", "of", "in", "on", "to", "and"}
    out = []
    for i, w in enumerate(words):
        if w.isdigit() or (w.isalnum() and any(c.isdigit() for c in w) and any(c.isalpha() for c in w)):
            out.append(w.upper() if len(w) <= 4 else w)
        elif w.lower() in small and i != 0:
            out.append(w.lower())
        else:
            out.append(w.capitalize())
    return " ".join(out)


def ensure_unique_source_files(camera_map: dict) -> dict:
    """local_file's config flow rejects a second entry with a file_path
    that's already in use by another entry - several of these cameras
    deliberately point at the same underlying illustration (e.g. a
    "last motion" variant reusing its camera's own image). Give any
    camera whose source image is shared by another camera its own copy,
    named after its object_id, so every entry gets a genuinely unique path.
    Idempotent: skips the copy if that file already exists.
    """
    from collections import Counter

    counts = Counter(v["source_image"] for v in camera_map.values())
    resolved = {}
    for object_id, info in camera_map.items():
        source_image = info["source_image"]
        name = title(object_id)
        if counts[source_image] > 1:
            unique_name = f"{object_id}.jpg"
            dest = WWW_DIR / unique_name
            if not dest.exists():
                shutil.copy(WWW_DIR / source_image, dest)
            resolved[object_id] = {"name": name, "file_path": f"/config/www/{unique_name}"}
        else:
            resolved[object_id] = {"name": name, "file_path": f"/config/www/{source_image}"}
    return resolved


async def ensure_onboarded(session: aiohttp.ClientSession, base_url: str, name: str, username: str, password: str, client_id: str, language: str = "en") -> bool:
    """Complete onboarding (create the owner account, confirm location,
    opt out of analytics, finish the integration step) if it hasn't been
    done yet. All four steps are required before HA stops showing the
    wizard - see homeassistant/components/onboarding/const.py's STEPS."""
    async with session.get(f"{base_url}/api/onboarding") as resp:
        # HA removes this endpoint entirely once onboarding is fully done
        # (not just an empty/all-done payload) - confirmed live: a 404 with
        # a text/plain body, not JSON, which .json() would otherwise choke
        # on ("unexpected mimetype"). A 404 here IS "already done".
        if resp.status == 404:
            print("onboarding: already done")
            return True
        status = await resp.json()
    if all(s["done"] for s in status):
        print("onboarding: already done")
        return True

    async with session.post(
        f"{base_url}/api/onboarding/users",
        json={"name": name, "username": username, "password": password, "client_id": client_id, "language": language},
    ) as resp:
        result = await resp.json()
        if resp.status != 200:
            print("onboarding users step failed:", resp.status, result)
            return False
        auth_code = result["auth_code"]

    async with session.post(
        f"{base_url}/auth/token",
        data={"grant_type": "authorization_code", "code": auth_code, "client_id": client_id},
    ) as resp:
        token_data = await resp.json()
        if resp.status != 200:
            print("onboarding token exchange failed:", resp.status, token_data)
            return False
        headers = {"Authorization": f"Bearer {token_data['access_token']}"}

    for step_url in ("core_config", "analytics"):
        async with session.post(f"{base_url}/api/onboarding/{step_url}", headers=headers) as resp:
            if resp.status != 200:
                print(f"onboarding {step_url} step failed:", resp.status, await resp.text())
                return False

    async with session.post(
        f"{base_url}/api/onboarding/integration",
        json={"client_id": client_id, "redirect_uri": client_id},
        headers=headers,
    ) as resp:
        if resp.status != 200:
            print("onboarding integration step failed:", resp.status, await resp.text())
            return False

    print(f"onboarding: completed (user {username!r})")
    return True


async def get_access_token(session: aiohttp.ClientSession, base_url: str, username: str, password: str, client_id: str) -> str | None:
    async with session.post(
        f"{base_url}/auth/login_flow",
        json={"client_id": client_id, "handler": ["homeassistant", None], "redirect_uri": client_id},
    ) as resp:
        flow = await resp.json()
        if resp.status != 200:
            print("login_flow init failed:", resp.status, flow)
            return None
        flow_id = flow["flow_id"]

    async with session.post(
        f"{base_url}/auth/login_flow/{flow_id}",
        json={"client_id": client_id, "username": username, "password": password},
    ) as resp:
        result = await resp.json()
        if resp.status != 200 or result.get("type") != "create_entry":
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


DEMO_CALENDARS = {
    # (title -> the resulting entity_id is title, slugified by local_calendar's
    # own config flow - confirmed live: "Family Calendar" -> calendar.family_calendar)
    # matching the decoy names publish/config/replacements.local.yaml already
    # uses for the equivalent real calendars, so demo/ui-lovelace.yaml's
    # Calendar card entities line up with something that actually exists.
    "Homer Family Calendar": [
        # (summary, days from now, start "HH:MM", end "HH:MM" or None for all-day)
        ("Mona Simpson Mona Birthday", 2, None, None),
        ("Bart Football Practice", 1, "11:35", "12:20"),
    ],
    "Lisa Simpson School Calendar": [
        ("Springfield Elementary Open Evening", 4, "18:30", "21:00"),
        ("Lisa School Trip - Power Plant Tour", 7, "09:15", "14:30"),
    ],
    "Lisa Simpson Calendar": [
        ("Lisa Swimming Lessons", 3, "17:20", "18:20"),
        ("Gymnastics", 6, "16:00", "17:00"),
    ],
    "Marge Family Calendar": [
        ("Bake Sale - Springfield Elementary", 5, "15:00", "16:00"),
        ("Dentist Appointment", 8, "10:00", "10:45"),
    ],
}


async def ensure_demo_calendars(session: aiohttp.ClientSession, base_url: str, headers: dict) -> None:
    """calendar.* needs the local_calendar integration - like local_file and
    moon, its manifest.json declares config_flow: true with no legacy YAML
    platform, so this can only be created live against a running instance,
    same shape of problem as ensure_moon_integration above. Confirmed live
    2026-09-18: demo/ui-lovelace.yaml's Calendar card referenced 4 calendar
    entities that never existed at all (not a YAML domain the generator
    scans), so the card was permanently empty - reported as "add some
    calendar entries". Seeds a handful of events per calendar so the card
    has something to actually show, at dates relative to whenever this
    script runs (no live-templating equivalent exists for calendar events,
    so - like the AMS tray colours above - this is static data that'll
    eventually look stale; acceptable for a demo, re-run
    bake_demo_image.sh periodically to refresh it).
    """
    from datetime import datetime, timedelta

    for title, events in DEMO_CALENDARS.items():
        async with session.post(
            f"{base_url}/api/config/config_entries/flow",
            json={"handler": "local_calendar"},
            headers=headers,
        ) as resp:
            flow = await resp.json()
        flow_id = flow.get("flow_id")
        if not flow_id:
            print(f"{title}: flow init failed - {flow}")
            continue
        async with session.post(
            f"{base_url}/api/config/config_entries/flow/{flow_id}",
            json={"calendar_name": title, "import": "create_empty"},
            headers=headers,
        ) as resp:
            result = await resp.json()
        if result.get("type") == "create_entry":
            print(f"{title}: created")
        elif result.get("reason") == "already_configured":
            print(f"{title}: already set up, skipped (events not re-seeded)")
            continue
        else:
            print(f"{title}: unexpected result - {result}")
            continue

        entity_id = "calendar." + "_".join(title.lower().split())
        now = datetime.now()
        for summary, days, start, end in events:
            when = now + timedelta(days=days)
            data = {"entity_id": entity_id, "summary": summary}
            if start:
                data["start_date_time"] = when.strftime(f"%Y-%m-%dT{start}:00")
                data["end_date_time"] = when.strftime(f"%Y-%m-%dT{end}:00")
            else:
                data["start_date"] = when.strftime("%Y-%m-%d")
                data["end_date"] = (when + timedelta(days=1)).strftime("%Y-%m-%d")
            async with session.post(
                f"{base_url}/api/services/calendar/create_event",
                json=data,
                headers=headers,
            ) as resp:
                if resp.status != 200:
                    print(f"  {summary}: create_event failed - {resp.status} {await resp.text()}")
        print(f"  seeded {len(events)} events")


async def ensure_moon_integration(session: aiohttp.ClientSession, base_url: str, headers: dict) -> None:
    """sensor.moon (the clock/weather cards' "Sun ... Below horizon" glance
    row) needs the moon integration - like local_file, its manifest.json
    declares config_flow: true with no legacy YAML platform, so `moon:` in
    configuration.yaml fails boot ("does not support YAML setup"). Single-
    instance, no user-input fields: flow init alone is enough to complete it.
    """
    async with session.post(
        f"{base_url}/api/config/config_entries/flow",
        json={"handler": "moon"},
        headers=headers,
    ) as resp:
        result = await resp.json()
    if result.get("type") == "form":
        # No fields to fill in - the confirm step just needs an empty POST.
        flow_id = result["flow_id"]
        async with session.post(
            f"{base_url}/api/config/config_entries/flow/{flow_id}",
            json={},
            headers=headers,
        ) as resp:
            result = await resp.json()
    if result.get("type") == "create_entry":
        print("moon: created")
    elif result.get("reason") == "single_instance_allowed":
        print("moon: already set up, skipped")
    else:
        print(f"moon: unexpected result - {result}")


SIDEBAR_PANEL_ORDER = [
    "lovelace", "dashboard-cctv", "dashboard-grafana", "dashboard-plex",
    "dashboard-coder", "dashboard-portainer", "dashboard-adguard",
    "dashboard-alloy", "unifi-controller", "dashboard-hacs", "map",
    "calendar", "logbook", "history", "media-browser", "todo", "energy",
]
SIDEBAR_HIDDEN_PANELS = ["light", "security", "climate", "home"]


async def ensure_frontend_preferences(session: aiohttp.ClientSession, base_url: str, access_token: str) -> None:
    """Sets the demo user's theme/dark-mode and sidebar order/hidden-panels
    preferences - both are per-user frontend.user_data storage, REST-inaccessible
    (frontend/set_user_data is websocket-only). Without this: the theme
    registered in demo/themes/ is dark-mode-only, and without an explicit
    darkMode the browser's own light/dark preference decides, so half of
    what card_mod relies on (e.g. the clock card's background) silently
    doesn't apply for anyone whose browser isn't already in dark mode.
    Without an explicit panelOrder, the 9 sidebar panels this script also
    creates (see demo/panels/) sort into HA's default order (roughly
    alphabetical) instead of matching the real dashboard's layout, burying
    "Overview" partway down the list instead of at the top.
    """
    ws_url = base_url.replace("https://", "wss://", 1).replace("http://", "ws://", 1) + "/api/websocket"
    async with session.ws_connect(ws_url, ssl=False) as ws:
        await ws.receive_json()  # auth_required
        await ws.send_json({"type": "auth", "access_token": access_token})
        auth_result = await ws.receive_json()
        if auth_result.get("type") != "auth_ok":
            print(f"frontend preferences: websocket auth failed - {auth_result}")
            return
        msg_id = 1
        for key, value in (
            ("theme", {"theme": "midnight_springfield", "darkMode": True}),
            ("sidebar", {"panelOrder": SIDEBAR_PANEL_ORDER, "hiddenPanels": SIDEBAR_HIDDEN_PANELS}),
            # HA resolves the post-login landing panel as
            # hass.userData.default_panel -> hass.systemData.default_panel ->
            # localStorage -> the built-in "home" panel, in that order
            # (frontend/src/data/panel.ts). Without this, the built-in "home"
            # panel wins even though it's hidden from the sidebar - being
            # hidden only affects the sidebar list, not what you land on.
            ("core", {"default_panel": "lovelace"}),
        ):
            await ws.send_json({"id": msg_id, "type": "frontend/set_user_data", "key": key, "value": value})
            result = await ws.receive_json()
            if not result.get("success"):
                print(f"frontend preferences: setting {key!r} failed - {result}")
            msg_id += 1

        # configuration.yaml's http: block (use_x_forwarded_for/trusted_proxies,
        # needed for the real-host nginx deployment's trusted_networks
        # auto-login) sits alongside HA's *storage*-based network config,
        # which only trusts it once an admin "promotes" it from pending to
        # stable - normally a one-click confirm in Settings > System >
        # Network after a restart. Confirmed live (2026-09-16): every fresh
        # container baked without this step left the YAML values stuck as
        # "pending" forever (nobody's ever there to click confirm), so every
        # single viewer of the published demo got a "Confirm new HTTP server
        # configuration" popup on first load. http/config/promote is the
        # same call that button makes.
        await ws.send_json({"id": msg_id, "type": "http/config/promote"})
        result = await ws.receive_json()
        if not result.get("success"):
            print(f"frontend preferences: http/config/promote failed - {result}")
        msg_id += 1
    print("frontend preferences: theme/dark-mode, sidebar order, and HTTP config set")


async def apply_customize_registry_names(session: aiohttp.ClientSession, base_url: str, access_token: str) -> None:
    """Pushes every demo/customize.yaml friendly_name into the entity
    registry's own `name` field, not just the state attribute customize:
    already sets. Confirmed live (2026-09-17): the more-info dialog's title
    bar (and, empirically, anything else that resolves a name from the
    entity registry rather than straight off the state object) shows the
    entity's `original_name` - the REAL, un-swapped title register_name()
    put in the entity's own `name:` field at creation, needed so entity_id
    stays "dog_..."/"bart_simpson_..." and matches what demo/ui-lovelace.yaml
    hardcodes - not customize's friendly_name. A registry `name` override
    (the same field HA's own Settings > Entities rename UI writes) takes
    priority over original_name everywhere, without touching entity_id,
    since it's looked up by unique_id, not by name, once an entity already
    exists. This has to run over the WS API - there's no YAML/config-flow
    equivalent for renaming an existing registry entry.
    """
    customize = yaml.safe_load(CUSTOMIZE_FILE.read_text(encoding="utf-8")) or {}
    renames = {
        entity_id: val["friendly_name"]
        for entity_id, val in customize.items()
        if isinstance(val, dict) and "friendly_name" in val
    }
    ws_url = base_url.replace("https://", "wss://", 1).replace("http://", "ws://", 1) + "/api/websocket"
    async with session.ws_connect(ws_url, ssl=False) as ws:
        await ws.receive_json()  # auth_required
        await ws.send_json({"type": "auth", "access_token": access_token})
        auth_result = await ws.receive_json()
        if auth_result.get("type") != "auth_ok":
            print(f"registry names: websocket auth failed - {auth_result}")
            return
        msg_id, applied, failed = 1, 0, 0
        for entity_id, name in renames.items():
            await ws.send_json({
                "id": msg_id,
                "type": "config/entity_registry/update",
                "entity_id": entity_id,
                "name": name,
            })
            result = await ws.receive_json()
            if result.get("success"):
                applied += 1
            else:
                failed += 1
                print(f"registry name: {entity_id} -> {name!r} failed - {result}")
            msg_id += 1
    print(f"registry names: {applied} applied, {failed} failed (of {len(renames)})")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8123")
    parser.add_argument("--username", required=True, help="Also used to complete onboarding if it isn't done yet")
    parser.add_argument("--password", required=True)
    parser.add_argument("--onboard-name", default=None, help="Display name for the owner account (defaults to --username, title-cased)")
    args = parser.parse_args()
    onboard_name = args.onboard_name or args.username.title()

    client_id = f"{args.base_url}/"
    camera_map = json.loads(CAMERA_MAP_FILE.read_text(encoding="utf-8"))
    cameras = ensure_unique_source_files(camera_map)

    async with aiohttp.ClientSession() as session:
        if not await ensure_onboarded(session, args.base_url, onboard_name, args.username, args.password, client_id):
            sys.exit(1)

        access_token = await get_access_token(session, args.base_url, args.username, args.password, client_id)
        if not access_token:
            sys.exit(1)
        headers = {"Authorization": f"Bearer {access_token}"}

        await ensure_moon_integration(session, args.base_url, headers)
        await ensure_demo_calendars(session, args.base_url, headers)
        await ensure_frontend_preferences(session, args.base_url, access_token)
        await apply_customize_registry_names(session, args.base_url, access_token)

        created, skipped, failed = 0, 0, 0
        for object_id, cam in cameras.items():
            async with session.post(
                f"{args.base_url}/api/config/config_entries/flow",
                json={"handler": "local_file"},
                headers=headers,
            ) as resp:
                flow = await resp.json()
            flow_id = flow.get("flow_id")
            if not flow_id:
                print(f"{cam['name']}: flow init failed - {flow}")
                failed += 1
                continue
            async with session.post(
                f"{args.base_url}/api/config/config_entries/flow/{flow_id}",
                json={"name": cam["name"], "file_path": cam["file_path"]},
                headers=headers,
            ) as resp:
                result = await resp.json()
            if result.get("type") == "create_entry":
                print(f"{cam['name']}: created")
                created += 1
            elif result.get("reason") == "already_configured":
                print(f"{cam['name']}: already set up, skipped")
                skipped += 1
            else:
                print(f"{cam['name']}: unexpected result - {result}")
                failed += 1

        print(f"\n{created} created, {skipped} already existed, {failed} failed (of {len(cameras)})")


if __name__ == "__main__":
    asyncio.run(main())
