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
creates the recorder DB and registers the generated entities.

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

## A single self-contained image

```sh
pip install aiohttp pyyaml
./demo/tools/bake_demo_image.sh homer_simpson/homeassistant-demo:latest
```

Builds an image with onboarding and camera setup already done, so `docker run` shows the
dashboard immediately with no setup steps - this is what the public mirror's GitHub Actions
workflow and the published `ghcr.io/homer_simpson/homeassistant-demo` image are built from.
See [design notes](docs/design-notes.md) for how it works.

---

Deployment internals, the Docker networking tradeoffs behind the isolation above, how the
entity generator works, and the copyright reasoning behind the camera artwork are in
[`docs/design-notes.md`](docs/design-notes.md) - background for anyone extending this,
not needed just to run it.
