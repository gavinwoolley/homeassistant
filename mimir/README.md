# Mimir alerting

Rules and Alertmanager config for the Mimir monolith on the Docker host. Mimir runs
`-target=all,alertmanager` (see `../docker-compose.yml`); the ruler + Alertmanager config
blocks are in `../mimir.yaml`.

## Layout

```
mimir/
  rules/
    vendor/    rendered mixin prometheus_alerts.yaml (node, windows, loki, mimir, alloy, mongodb)
    custom/    hand-written rule groups (infra-meta, blackbox, mosquitto, adguard, unifi, ...)
  alertmanager/
    alertmanager.yaml   routing tree + webhook receivers into Home Assistant
```

Each rule file is a Prometheus rules file (`groups:`) **plus a top-level `namespace:` key**
— `mimirtool rules load` requires it. When vendoring a mixin's `prometheus_alerts.yaml`,
prepend `namespace: <slug>` (e.g. `namespace: node-exporter`).

## Deploy

The Deploy stage of `../azure-pipelines-docker.yml` runs, on the Docker host, after
`docker-compose up -d`:

```sh
docker run --rm -v "$PWD/mimir:/mimir" grafana/mimirtool:latest \
  rules load /mimir/rules/vendor/*.yaml /mimir/rules/custom/*.yaml \
  --address=http://localhost:9009 --id=anonymous

docker run --rm -v "$PWD/mimir:/mimir" grafana/mimirtool:latest \
  alertmanager load /mimir/alertmanager/alertmanager.yaml \
  --address=http://localhost:9009 --id=anonymous
```

The Build stage validates first with `mimirtool rules check` and
`mimirtool alertmanager verify`.

## Check what's live

```sh
curl -s 'http://localhost:9009/prometheus/api/v1/rules?type=alert' | jq '.data.groups[].name'
curl -s  http://localhost:9009/prometheus/api/v1/alerts | jq '.data.alerts[].labels'
mimirtool alertmanager get --address=http://localhost:9009 --id=anonymous
```

**There is no standalone Alertmanager web UI** - Mimir only serves the API under
`/alertmanager/api/v2/*` (confirmed: the bare `/alertmanager` path 404s, `/alertmanager/api/v2/
status|alerts|silences` return 200). The UI is **Grafana**: Alerting -> pick "Mimir
Alertmanager" from the Alertmanager selector at the top of the page (default is "Grafana",
which is unrelated and intentionally empty). From there: Contact points / Notification
policies / Templates / Silences all read live from Mimir.

Useful direct API calls (all via the nginx `/alertmanager/` proxy on :599, or `localhost:9009`
on the host):

```sh
curl -s https://home.example.com:599/alertmanager/api/v2/status
curl -s https://home.example.com:599/alertmanager/api/v2/alerts
curl -s https://home.example.com:599/alertmanager/api/v2/silences
```

## Gotchas

- **Receivers firewall:** the webhook receivers point at Home Assistant on a private LAN IP
  (`10.0.0.10:8123`). Mimir's `alertmanager.receivers_firewall_block_private_addresses`
  defaults to `false`, so this works. If it's ever turned on, alerts silently stop reaching HA.
- Mimir runs `-target=all,alertmanager`. Plain `-target=all` starts the ruler but **not** the
  Alertmanager, and the ruler's alerts go nowhere.
- On a first deploy the Alertmanager logs `no matching configuration for user anonymous` until
  `mimirtool alertmanager load` has run once.

## Rule sets

Hand-curated from the standard mixins (node-exporter, windows-exporter,
blackbox, mimir/loki/alloy) plus custom groups for the exporters with no
upstream mixin. One file per subsystem, `namespace:` = the subsystem:

| File | Covers |
|---|---|
| `custom/infra-meta.yaml` | Watchdog dead-man's-switch, TargetDown, scrape + pipeline health |
| `node-exporter.yaml` | Linux hosts - disk, inodes, memory, swap, CPU, load, clock |
| `windows-exporter.yaml` | Windows hosts - disk, memory, CPU, services, reboots |
| `blackbox.yaml` | probe up/latency, TLS cert expiry |
| `lgtm-stack.yaml` | Mimir / Loki / Alloy self-health |
| `mosquitto.yaml` | broker up, restarts, client count, dropped messages |
| `adguard.yaml` | DNS resolver up, query flatline, protection left off |
| `unifi.yaml` | unpoller up, devices disconnected, WAN flapping, Wi-Fi satisfaction |
| `containers.yaml` | critical container down, restart loops, memory-limit pressure |
| `home-assistant.yaml` | HA scrape/staleness, mass entity unavailability, low battery |
| `mongodb.yaml` | mongod up, connections, assert rate (needs the PR3 exporter) |
| `nginx.yaml` | nginx up, dropped/hot connections (needs the PR3 exporter) |

### Editing conventions

- Every alert carries `labels.severity` (`critical` / `warning` / `info` / `none`)
  and `annotations.summary` + `annotations.description`. High-value alerts add a
  `runbook_url` anchored into this file (below).
- Prometheus/Mimir ruler templating - **no sprig `default`**; only the built-in
  Prometheus template functions (`humanize*`, `printf`, `title`, `reReplaceAll`, …).
- Transient hosts (`homer_simpson-hp-laptop`, `dev-linux`) are stamped
  `tier="transient"` in `config.alloy`. They page like any other host *except*
  for `TargetDown` and `WindowsHostRebooted`, which the Alertmanager drops on a
  non-paging route (a laptop that sleeps going unreachable is not an incident).
  Do not special-case them in the rules.

## Refreshing from upstream mixins

The rules are curated, not vendored verbatim (the upstream node/windows mixins
assume Kubernetes labels). To compare against the current upstream set when a
mixin is updated:

```sh
docker run --rm -v "$PWD:/w" -w /w grafana/jsonnet:latest sh -c '
  jb init && jb install github.com/prometheus/node_exporter/docs/node-mixin &&
  jsonnet -S -e "std.manifestYamlDoc((import \"node-mixin/mixin.libsonnet\").prometheusAlerts)"'
```

Diff that against `node-exporter.yaml` and pull in anything newly relevant.

## Runbooks

### TargetDown
A scrape target has been unreachable for 15m. Check: is the host/container up
(`docker ps`, `ssh` the box)? Is Alloy running (`systemctl status alloy`)? For a
`blackbox_*` job, the probe target itself is down. For transient hosts
(`homer_simpson-hp-laptop`, `dev-linux`) this alert is dropped before it pages - usually
just a laptop that's off.

### NodeFilesystemAlmostOutOfSpace / WindowsDiskAlmostFull
Free space under 8% (4% = critical). On the Docker VM the usual culprit is
`/var/lib/docker` (image/layer bloat - `docker system prune`) or
`mimir-data` / `loki-data` growth. Excludes blueiris's `E:` and server2's
`C:`/`D:` - see `WindowsDiskNearlyFullByDesign` below.

### WindowsDiskNearlyFullByDesign
server2 (the hypervisor) has allocated most of its `C:`/`D:` to the blueiris
guest VM, whose `E:` is the same storage from inside the VM - both run
deliberately near-full and BlueIris manages retention within that space fine,
so the normal disk alerts exclude them. BlueIris runs `E:` as a rolling buffer:
free space sawtooths between ~2.6 GB and ~6 GB as retention deletes footage in
batches (never below 2.6 GB over 21 days of history). This alert therefore uses
an absolute floor - **< 1 GiB free for 1h** - which only trips if that cleanup
has actually stopped. Check BlueIris clip/storage settings and disk health, or
whether server2 needs more storage allocated to the guest.

### BlackboxProbeFailed
The named service isn't answering. Cross-check the HA `binary_sensor.*` for the
same host and the Topology dashboard. External probes (`env="external"`) failing
but internal ones OK => WAN or nginx.

### AdGuardNotRunning
The LAN's only DNS resolver is down - the house has no internet name resolution.
`ssh ha && docker restart adguard`. Fall back: point a device's DNS at
`1.1.1.1` to confirm it's DNS-only.

### UnifiDevicesDisconnected
`unpoller` says an adopted device is offline. Check the UniFi console; power-cycle
the AP/switch. If several at once => uplink switch or PoE.

### UnifiClientWeakSignal
A wireless client is stuck on a distant/weak AP instead of roaming to a closer
one - this is a controller-config problem, not something to fix in an alert
rule. In the UniFi console, per AP-group / WiFi network:
- **Minimum RSSI** - enable and set around -75dBm so weak clients get
  disconnected and forced to re-associate with whichever AP is strongest,
  instead of clinging to the one they first joined.
- **Band Steering** - push dual-band clients onto 5GHz/6GHz where signal allows.
- **Fast Roaming (802.11r/k/v)** - lets supporting clients roam without a full
  re-auth handshake; enable if client devices support it (most modern
  phones do).
- **AP TX power** - if APs badly overlap, an AP running at max power can keep a
  client attached well past the point a neighbouring AP would serve it better;
  consider "Medium" instead of "High"/"Auto" on APs that are close together.
- Check whether any of the affected APs are the older `UAP-AC-M` / `AC-Lite`
  models - weaker radios/mesh backhaul than the U6/U7 units, and a likely
  weak spot if the same AP keeps showing up.

### ContainerDown
A critical container isn't reporting to cAdvisor. `ssh ha && docker ps -a | grep
<name>`, then `docker logs <name> --tail 100` and `docker compose up -d <name>`.

### ContainerHighMemory
A container's working set (`container_memory_working_set_bytes` - usage minus
reclaimable page cache, i.e. what's actually close to what the OOM killer
weighs) has been above 90% of its `mem_limit` (docker-compose.yml) for 15
minutes - Docker will OOM-kill it if it crosses 100%. The Ubuntu Docker host
itself only has ~5.7 GiB total RAM and runs close to the edge stack-wide (this
is the same RAM ceiling behind `max_global_series_per_user` and the Mimir/Loki
mem_limit comments in docker-compose.yml) - raising one container's limit just
moves the pressure elsewhere unless the host actually has headroom. Check
`docker stats` for what's actually using memory right now before deciding
whether to bump the limit, trim what the container is doing (e.g. an
exporter's cardinality), or free memory elsewhere first.

### HomeAssistantScrapeDown
HA isn't answering `/api/prometheus`. Check `docker logs home-assistant`, the
companion app, and `https://home.example.com:8123`. A boot loop shows as
repeated `HomeAssistantHostRebooted`-style gaps.

### MongoDBDown / NginxDown
`unifi-db` down => the UniFi controller will fail; `nginx` down => every
externally published service is unreachable. `ssh ha && docker restart <name>`.
