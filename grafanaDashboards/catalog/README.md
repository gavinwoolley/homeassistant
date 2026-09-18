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
| `LGTM-Stats.json` | `lgtm-stats` | Full LGTM-stack overview (tenant counts, ingestion, resource usage, Kubernetes events) built for a Kubernetes, multi-tenant LGTM deployment - not this single-host, single-tenant, no-Tempo stack. Datasources templated via `__inputs`/`${DS_PROMETHEUS}`/`${DS_LOKI}` for import elsewhere or grafana.com publishing. `dashboards/LGTM/LGTM Stats.json` (same `uid`, so this and that are never provisioned together) is a *different* file - the un-genericized original, still broken locally (`"uid": "prometheus"`/`"loki"` don't match a real datasource here). |

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
