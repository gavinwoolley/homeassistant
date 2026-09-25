# Demo design notes

Background on why the demo is built the way it is - not needed to run it, see
[`demo/README.md`](../README.md) for that. This is for anyone extending it.

## Why not `internal: true`

The first version of this used an `internal: true` network so the container genuinely
couldn't reach the internet at all. That cost more than it was worth:

- Docker doesn't publish container ports to the host at all on an internal network -
  confirmed directly (empty `NetworkSettings.Ports`, no `docker-proxy` process, no iptables
  DNAT rule, despite the port mapping being configured correctly). Routing around that meant
  nginx joining the network directly instead of a normal host-port proxy.
- That makes nginx a multi-network container, and the `docker-compose` version on this host
  can't reliably recreate a multi-network service in place - it failed with "Cannot create
  container ... already in use" on the next unrelated `docker-compose.yml` change, breaking
  nginx (and therefore Grafana, AdGuard, Portainer, everything else it fronts) with it.

That's a real, recurring cost (nginx-fronted services blip on routine deploys) for isolation
this demo doesn't actually need beyond "can't reach anything real" - a normal published port
gets that without any of it. The tradeoff: this container can reach the internet like any
other container in `docker-compose.yml` - see the discovery-integrations note in the main
README for the one place that matters.

## How the real dashboard runs against fake data

The real `ui-lovelace.yaml` references several hundred distinct entity_ids - lights,
switches, sensors, the mower, the 3D printer, irrigation valves, cameras, media players, and
so on. `demo/tools/generate_demo_entities.py` scans the real file for every one of those and
writes a matching fake, stateful backing entity for each - same domain, same object_id - into
`demo/generated/`:

- **`template.yaml`** - the bulk of it: template `sensor`/`binary_sensor` entities with
  plausible heuristic values (battery %, °C, kWh, ping ms, …) refreshed every 2 minutes so
  numbers drift, plus template `switch`/`light`/`number`/`select`/`button`/`vacuum` entities
  that are genuinely toggleable - clicking one in the UI changes its state and it sticks,
  backed by a hidden `input_boolean`/`input_number`/`input_select` helper.
- **`climate.yaml`** - `generic_thermostat` entries, not template ones: this HA version's
  template integration has no climate support, so each real climate entity gets a
  `generic_thermostat` instead, backed by a hidden "heater" input_boolean and a template
  temperature sensor. Working climate behaviour (`hvac_action`, target temp, modes), not
  faked.
- **`cameras.json`** - a plain data file for `demo/tools/setup_demo_cameras.py` to drive - one
  entry per real camera, matched to the illustration for that camera's actual location (see
  "Why original illustrations" below), not a cycling/arbitrary assignment.
- **`input_boolean.yaml` / `input_number.yaml` / `input_select.yaml` / `input_datetime.yaml`
  / `timer.yaml`** - the real dashboard's own helper entities, recreated directly.

`demo/automations.yaml` and `demo/scripts.yaml` are generated the same way: one automation
picks a random switch/light every few minutes, turns it on, then off again after a random
stretch, so the demo looks lived-in without anyone clicking anything; every real `script.*` id
gets a script that logs "ran (demo)" - except `reload_all_yaml`/`reload_lovelace`/
`restart_home_assistant_service`, which call the real, harmless HA services since those are
genuinely safe to run here.

**`media_player`, `remote`, `lawn_mower`** have no template/YAML backing in this HA version,
but their dashboard cards need to actually work (not just degrade gracefully) - the tiny,
purpose-built platforms in `demo/custom_components/` cover them instead: one real, toggleable
entity each, same "come alive" treatment as everything else.

**Not generated at all: `valve`.** No card on the real dashboard actually depends on it
working, so it shows "entity not available" rather than being faked - a better trade than a
bespoke fake integration for a domain nothing here exercises.

## Why original illustrations, not real Simpsons imagery

Character *names* used as placeholders are unambiguously fine - obviously fictional,
non-commercial, nothing to infringe. Actual show screenshots or copied artwork are different:
that's reproducing someone else's specific copyrighted expression, which carries takedown
risk regardless of intent. The camera and avatar images in `www/` are original illustrations -
same joke, none of that exposure.

## Sharing it as a single self-contained image

`demo/tools/bake_demo_image.sh` builds the static image (`demo/Dockerfile`), runs it as a
throwaway container with no volumes (so `docker commit` at the end captures `/config` as real
image layers, not a bind mount it can't see into), drives onboarding and camera setup against
it live, lets it settle, commits the result, then verifies a fresh container from that image
needs zero setup. Reproducible from a clean checkout - unlike a plain `docker build`, which
only bakes the static YAML/`www/` files and would still show the onboarding wizard on first
run.

On the public mirror, this happens automatically -
[`.github/workflows/demo-image.yml`](../../publish/templates/.github/workflows/demo-image.yml)
runs this script on every `demo/**` change and pushes the result to
`ghcr.io/gavinwoolley/homeassistant-demo:latest`, what the public README's `docker run`
one-liner and the Codespaces badge both point at.

Sharing it yourself instead: the result of `bake_demo_image.sh` is a normal image - push it
to whichever registry to make `docker pull` work for anyone else. Nobody else gets the home
LAN's passwordless bypass (`auth_providers` only trusts the home subnet) - they'll see a
normal login screen, `demo`/`demo`.

## Auto-reset

Nothing in `docker-compose.demo.yml` resets the container automatically - giving any
container access to the Docker socket to restart this one would mean giving it effective
control of every container on whatever host runs it, real stack included, which defeats the
isolation this is supposed to guarantee. For a periodic reset to a clean seeded state, add it
on the host instead:

```
0 */6 * * *  docker restart homeassistant-demo
```

This also wipes the one-time onboarding/camera setup - re-run `setup_demo_cameras.py` after a
reset that goes through onboarding again.
