# Dashboard catalog

Genericized dashboards authored/shared here, staged for or already published to
[grafana.com/grafana/dashboards](https://grafana.com/grafana/dashboards). **Deliberately outside
`grafanaDashboards/dashboards/`** so `foldersFromFilesStructure` never picks them up and provisions
them as live dashboards — nothing in here is meant to run against this repo's own Grafana. Most
aren't useful against a single-host Docker Compose LGTM stack in the first place (multi-tenant /
Kubernetes-shaped, or sized for a much bigger deployment).

## Contents

| File | uid | What it is |
| --- | --- | --- |
| `Mimir Sizing.json` | `mimir-sizing` | Genericized Mimir capacity/sizing reference dashboard, published to the community catalog. |
| `platform-limits.json` | `platform-limits` | Mimir/Loki/Tempo runtime-limits overview. Not importable here - the metrics it reads (`cortex_limits_defaults`, `loki_overrides_defaults`, `tempo_limits_defaults`) aren't exposed by this stack's Mimir/Loki, and there's no Tempo service running at all. Kept for reference / in case that ever changes. |
| `LGTM-Stats.json` | `lgtm-stats` | Full LGTM-stack overview (tenant counts, ingestion, resource usage, Kubernetes events) built for a Kubernetes, multi-tenant LGTM deployment - not this single-host, single-tenant, no-Tempo stack. Datasources templated via `__inputs`/`${DS_PROMETHEUS}`/`${DS_LOKI}` for import elsewhere or grafana.com publishing. `dashboards/LGTM/LGTM Stats.json` (same `uid`, so this and that are never provisioned together) is a *different* file - the un-genericized original, now fixed to use this stack's real Mimir/Loki uids (was `"uid": "prometheus"`/`"loki"`, a dangling import-block leftover that never resolved to a real datasource here - see its git history). |
| `Home Assistant.json` | `oVTa8pdWk` | Sanitized + genericized copy of `dashboards/Home Assistant.json`, built by `demo/tools/build_demo_dashboards.py` then `demo/tools/genericize_ha_dashboard.py` - regenerate with those two, don't hand-edit. Meaningfully importable specifically against the public demo stack (`demo/docker-compose.demo.yml` + `demo/docker-compose.demo-observability.yml`): its panels query fixed entity_ids that only that demo HA instance has matching data for. Same `uid` as the live original, never provisioned locally. |

## Published to grafana.com

Everything currently live under [grafana.com/orgs/homer_simpson2/dashboards](https://grafana.com/orgs/homer_simpson2/dashboards),
with a link straight to each listing. Add a row here whenever a new one goes up - this is the
index. The Games/Arcade dashboards are a different distribution shape from everything else in this
folder: they're genericized *and* published *and* still run live in this repo's own Grafana (see
`dashboards/Games/README.md` for controls/UID details), whereas the rest of this folder is
published-only, never provisioned locally (see "Deliberately outside `dashboards/`" above).

### Grafana Arcade

| grafana.com | Local file | What it is |
| --- | --- | --- |
| [Grafana Arcade Home Launcher](https://grafana.com/grafana/dashboards/25719) | `dashboards/Games/grafana-arcade.json` | Collection launcher - the entry point, links out to every game below. |
| [Cardinality Invaders](https://grafana.com/grafana/dashboards/25725) | `dashboards/Games/grafana-cardinality-invaders.json` | Space Invaders-style game defending against toxic observability labels. |
| [2048](https://grafana.com/grafana/dashboards/25720) | `dashboards/Games/grafana-2048.json` | Playable 2048 puzzle in a Business Text panel. |
| [Alert Whack-a-Mole](https://grafana.com/grafana/dashboards/25721) | `dashboards/Games/grafana-alert-whack-a-mole.json` | SRE-themed reaction game with alert acknowledgment. |
| [Grot Observability Run](https://grafana.com/grafana/dashboards/25735) | `dashboards/Games/grafana-grot-observability-run.json` | Endless runner dodging incoming incidents. |
| [Grot Road Rage](https://grafana.com/grafana/dashboards/25727) | `dashboards/Games/grafana-grot-road-rage.json` | Horizontal driving/avoidance game. |
| [Incident Queue](https://grafana.com/grafana/dashboards/25724) | `dashboards/Games/grafana-breakout.json` | Breakout-style on-call game, clearing incidents. |
| [Minesweeper](https://grafana.com/grafana/dashboards/25728) | `dashboards/Games/grafana-minesweeper.json` | Fully playable Minesweeper. |
| [Node Graph-oids](https://grafana.com/grafana/dashboards/25723) | `dashboards/Games/grafana-asteroids.json` | Asteroids, resolving incident services instead of rocks. |
| [Pac-Man](https://grafana.com/grafana/dashboards/25729) | `dashboards/Games/grafana-pacman.json` | Maze game with ghosts and power pills. |
| [Pong](https://grafana.com/grafana/dashboards/25730) | `dashboards/Games/grafana-pong.json` | Classic Pong with an AI opponent. |
| [Grot-Tac-Toe](https://grafana.com/grafana/dashboards/25734) | `dashboards/Games/grafana-tic-tac-toe.json` | Tic-tac-toe against Grafana automation. |
| [Simon](https://grafana.com/grafana/dashboards/25731) | `dashboards/Games/grafana-simon.json` | Memory game with Grafana-style status tiles. |
| [Snake](https://grafana.com/grafana/dashboards/25732) | `dashboards/Games/grafana-snake-v2.json` | Snake, scored. |
| [SRE Tetris](https://grafana.com/grafana/dashboards/25733) | `dashboards/Games/grafana-sre-tetris.json` | Tetris with an operational-signals theme. |

### LGTM Stack & Platform Monitoring

| grafana.com | Local file | What it is |
| --- | --- | --- |
| [LGTM Stats](https://grafana.com/grafana/dashboards/25700) | `dashboards/LGTM/LGTM Stats.json` (different, un-genericized file locally - see History below) | Overview of Loki/Grafana/Tempo/Mimir stack metrics. |
| [LGTM Versions/Releases](https://grafana.com/grafana/dashboards/25701) | `dashboards/LGTM/LGTM Versions Releases.json` | Component version comparison against each project's GitHub releases. |
| [Mimir/Sizing](https://grafana.com/grafana/dashboards/25779) | `Mimir Sizing.json` | Capacity/sizing reference for a Grafana Mimir deployment. |
| [Platform Limits](https://grafana.com/grafana/dashboards/25702) | `platform-limits.json` | Mimir/Loki/Tempo per-tenant runtime-limits overview. |

## Publishing a dashboard here

1. Genericize it: template every real datasource reference via a top-level `__inputs` block (same
   shape Grafana's own "Export for sharing externally" produces) instead of a fixed uid, clear `id`,
   add a `description` (required for the grafana.com listing).
2. Drop the file here.
3. Sign in at grafana.com → **My Account → My Dashboards** → upload the JSON, fill in
   title/description/screenshots/tags, publish.

## History

Replaces the old `temp-dashboards/` staging area. `LGTM-Versions-Releases.json` (also originally
staged there) is the exception - that one *was* absorbed into `dashboards/LGTM/` as a real, working
dashboard (its datasources are now variables, `$prometheus_datasource`/`$github_datasource`, so it
isn't pinned to this instance's specific uids either).
