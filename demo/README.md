# Demo instance

A running Home Assistant instance you can click around - your dashboard, all ~25 views,
against fake data. `demo/ui-lovelace.yaml` is the repo root's `ui-lovelace.yaml`, copied with
only the display text swapped (names to their Simpsons equivalents); every entity_id it
references is untouched, so the dashboard itself is unmodified.

## Built with Home Assistant

This is a public demo configuration built for
[Home Assistant](https://www.home-assistant.io/), the open-source home automation platform.

It is not affiliated with the Home Assistant project.

## Run it

```sh
docker compose -f demo/docker-compose.demo.yml up
```

Then open <http://localhost:8124>. First boot takes a few minutes while Home Assistant
creates the recorder DB and registers the generated entities. Log in with `demo` / `demo`
(the baked-in onboarding account - see `demo/tools/bake_demo_image.sh`).

### Optional: with Grafana too

Want the observability side as well - a real Grafana fed by Mimir/Loki/Alloy, provisioned with
a sanitized copy of this repo's entire dashboard catalogue (Home Assistant, Games, everything
under `grafanaDashboards/dashboards/`)? On the public mirror, there's a one-click "Open in
GitHub Codespaces - Grafana demo" option in the
[root README](../README.md#try-the-grafana-observability-demo) - a second, separate demo from
the plain Home Assistant one, no local Docker needed. From this private repo / a local clone,
there's no separate Codespace to pick, so it's still both compose files together on the one
instance - build the sanitized dashboards once, then bring both up:

```sh
python demo/tools/build_demo_dashboards.py
docker compose -f demo/docker-compose.demo.yml -f demo/docker-compose.demo-observability.yml up
```

Open <http://localhost:3001> - no login needed. This add-on is purely a local convenience for
trying the repo out; it's separate from the always-on `demo/docker-compose.demo.yml` instance and
never deployed by CI. See `demo/docker-compose.demo-observability.yml`'s own comments for why it
deliberately doesn't ship container logs (no `/var/run/docker.sock` mount, unlike the real stack's
Alloy) - some dashboard panels will show "no data" for signals this single-instance demo has no
source for (per-container CPU/mem, Unifi, MongoDB, Windows), same as they would in the real
Grafana for a signal that's currently absent.

The "Home Assistant" datasource wires its own access token up automatically - a "Wire up the demo
Grafana datasource token" automation runs `demo/tools/setup_demo_grafana_token.py` every time this
HA instance starts (see the automation and the `shell_command:` block in `demo/configuration.yaml`),
retrying for a couple of minutes in case Grafana is still starting too. No manual step, and it's a
harmless no-op if you're running the plain `demo/docker-compose.demo.yml` on its own (Grafana
unreachable, the retries just time out). Re-run it by hand any time with:

```sh
python demo/tools/setup_demo_grafana_token.py --username <your-demo-username> --password <your-demo-password>
```

## One-time setup after a fresh instance

Two things only need doing once, on first boot - after that they persist in `.storage/` on
the bind-mounted `/config`, surviving every future container recreation:

1. **Onboarding** - go through the "Create my smart home" wizard (any name/username/
   password; this is a throwaway local instance). The account you create becomes the owner
   referenced by `auth_providers` in `configuration.yaml` - if you use a different username,
   update the `trusted_users` entry to match (get the id from `.storage/auth`).
2. **Cameras and the `moon` integration** - neither is YAML-configurable in this HA version.
   Run once, after onboarding:

   ```sh
   pip install aiohttp pyyaml   # only if running this outside the HA container
   python demo/tools/setup_demo_cameras.py --username <your-username> --password <your-password>
   ```

   Safe to re-run - already-created entries are detected and skipped.

Everything else - all other entities, the dashboard itself - is config-as-code and comes up
correctly on every fresh container with no manual steps.

## How it's isolated

A structurally separate config directory, container, and Docker network from the real stack -
no shared volumes, no shared network, no credentials for anything real. It reaches the
internet like any other container in `docker-compose.yml` (see
[design notes](docs/design-notes.md) for why), so `configuration.yaml` leaves Home
Assistant's device-discovery integrations out of its config - there's no real device for it
to find, so no reason to go looking.

On the home LAN, `configuration.yaml`'s `auth_providers` auto-logs in anyone connecting from
that network as the owner account, no login screen - a genuine access relaxation, not just a
convenience toggle, so worth knowing about if the range it's scoped to ever changes.

## Rebuilding the generated entities

If the real dashboard's entity set changes, re-copy `ui-lovelace.yaml` and regenerate:

```sh
python demo/tools/generate_demo_entities.py
```

`demo/generated/`, `demo/automations.yaml`, and `demo/scripts.yaml` are produced by that
script and shouldn't be hand-edited - `demo/customize.yaml` is the hook point for a one-off
cosmetic tweak that isn't worth adding to the generator. See
[design notes](docs/design-notes.md) for how the generator maps real entity_ids to fake,
stateful backing entities.

If you're running the optional observability stack (above), also rebuild its sanitized dashboard
set whenever `grafanaDashboards/dashboards/` changes:

```sh
python demo/tools/build_demo_dashboards.py
```

This reuses `publish/sanitize.py`'s existing redaction against the whole repo and copies out just
the dashboards subtree into `demo/grafana/dashboards/` (gitignored, rebuilt on demand - needs
`publish/config/replacements.local.yaml` to exist locally, same as `publish/sanitize.py` itself).

## A single self-contained image

```sh
pip install aiohttp pyyaml
./demo/tools/bake_demo_image.sh homer_simpson/homeassistant-demo:latest
```

Builds an image with onboarding and camera setup already done, so `docker run` shows the
dashboard immediately with no setup steps - this is what the public mirror's GitHub Actions
workflow and the published `ghcr.io/gavinwoolley/homeassistant-demo` image are built from.
See [design notes](docs/design-notes.md) for how it works.

---

Deployment internals, the Docker networking tradeoffs behind the isolation above, how the
entity generator works, and the copyright reasoning behind the camera artwork are in
[`docs/design-notes.md`](docs/design-notes.md) - background for anyone extending this,
not needed just to run it.
