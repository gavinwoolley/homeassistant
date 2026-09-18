# Homer's Smart Home

A public Home Assistant showcase, built from my private home config with personal data
swapped for fictional Simpsons-themed demo data. Try the dashboard, then borrow whatever's
useful from the automations, scripts, and Lovelace YAML for your own setup.

This is a **sanitized mirror** of a private, actively-developed repo - see
[About this mirror](#about-this-mirror).

<a href="https://github.com/gavinwoolley/homeassistant/actions/workflows/ha-config-check.yml" target="_blank" rel="noopener noreferrer"><img src="https://github.com/gavinwoolley/homeassistant/actions/workflows/ha-config-check.yml/badge.svg" alt="HA config check"></a>
<a href="https://github.com/gavinwoolley/homeassistant/actions/workflows/grafana-validate.yml" target="_blank" rel="noopener noreferrer"><img src="https://github.com/gavinwoolley/homeassistant/actions/workflows/grafana-validate.yml/badge.svg" alt="Grafana dashboards"></a>
<a href="https://github.com/gavinwoolley/homeassistant/actions/workflows/yamllint.yml" target="_blank" rel="noopener noreferrer"><img src="https://github.com/gavinwoolley/homeassistant/actions/workflows/yamllint.yml/badge.svg" alt="yamllint"></a>
<a href="https://github.com/gavinwoolley/homeassistant/actions/workflows/gitleaks.yml" target="_blank" rel="noopener noreferrer"><img src="https://github.com/gavinwoolley/homeassistant/actions/workflows/gitleaks.yml/badge.svg" alt="gitleaks"></a>
<a href="https://github.com/gavinwoolley/homeassistant/actions/workflows/demo-image.yml" target="_blank" rel="noopener noreferrer"><img src="https://github.com/gavinwoolley/homeassistant/actions/workflows/demo-image.yml/badge.svg" alt="demo image"></a>
![license](https://img.shields.io/github/license/gavinwoolley/homeassistant)
![last commit](https://img.shields.io/github/last-commit/gavinwoolley/homeassistant)

![Home Assistant dashboard](docs/screenshots/ha-home.jpg)

## Try the demo

<a href="https://github.com/codespaces/new?hide_repo_select=true&ref=main&repo=1374266358" target="_blank" rel="noopener noreferrer"><img src="https://github.com/codespaces/badge.svg" alt="Open in GitHub Codespaces"></a>

- **In your browser:** click the badge above, sign in with GitHub, and wait a few minutes. It opens
  the dashboard automatically once it detects port `8123`; if your browser blocks the popup,
  open it manually from the **Ports** tab in the bottom panel.
- **Locally:** `docker run -p 8123:8123 ghcr.io/gavinwoolley/homeassistant-demo:latest`, then
  open <http://localhost:8123>.
- **From source:** see [`demo/README.md`](demo/README.md).

Both the Codespaces and Docker options land on a login screen - use `demo` / `demo`.

[`demo/`](demo/) runs the full Lovelace dashboard against fake data. The Grafana, AdGuard and
Portainer sidebar entries are screenshots, not running services.

## Good places to borrow ideas from

- [`ui-lovelace.yaml`](ui-lovelace.yaml) - conditional cards that show useful controls and
  alerts only when they matter.
- [`automations.yaml`](automations.yaml) and [`scripts.yaml`](scripts.yaml) - day-to-day
  logic: heating schedules, irrigation with rain-skip, camera/motion handling, presence.
- [`themes/`](themes/) - the dark theme the dashboard runs. The custom Lovelace cards it
  depends on (mushroom, mini-graph, vacuum-card, and others) are installed via HACS, not
  vendored here, but the demo bundles static copies in
  [`demo/www/community/`](demo/www/community/) if you want the actual files.
- A few specific areas worth a look if you have the matching hardware: energy monitoring,
  camera/motion handling, heating, irrigation, and the Bambu Lab 3D printer integration - all
  in `configuration.yaml` and the two files above.

## Screenshots

[More in `docs/screenshots/`](docs/screenshots/) - click any image below to open it full-size.

| | |
| --- | --- |
| [![Overview](docs/screenshots/ha-home.jpg)](docs/screenshots/ha-home.jpg) | [![People and locations](docs/screenshots/ha-people.jpg)](docs/screenshots/ha-people.jpg) |
| Main dashboard | People and location view, demo data |
| [![Cameras](docs/screenshots/ha-cctv.jpg)](docs/screenshots/ha-cctv.jpg) | [![Media players](docs/screenshots/ha-media.jpg)](docs/screenshots/ha-media.jpg) |
| Camera grid with motion-triggered snapshots | Every speaker and TV, cast-to-room dropdowns |
| [![3D printer](docs/screenshots/ha-3d-printer.jpg)](docs/screenshots/ha-3d-printer.jpg) | [![CI/CD pipeline status](docs/screenshots/ha-pipelines.jpg)](docs/screenshots/ha-pipelines.jpg) |
| Bambu Lab AMS: per-tray filament, temps, camera | Build status, surfaced right in the dashboard |

## Also included

The repo also includes the Docker, monitoring and deployment configuration that supports the
private setup - Grafana, Prometheus/Mimir, Loki, a reverse proxy, DNS filtering, TLS
automation, and the CI/CD pipelines that deploy all of it. It is reference material only; the
Home Assistant demo runs independently. See [`docs/architecture.md`](docs/architecture.md)
for the diagram, dashboard catalogue, and deploy mechanics.

## About this mirror

The private source repo is never published directly. A [sanitizer](publish/) assembles an
allowlisted copy, redacts anything secret- or PII-shaped, checks the result against two
independent secret scans plus a dashboard-validity check, and only then pushes it here as a
single commit with no history of its own - every sync replaces the last rather than building
on it. Full rule set in [`publish/README.md`](publish/README.md).

## License

[MIT](LICENSE), Copyright (c) 2026 Gavin Woolley. Simpsons character names are used purely
as obviously-fictional placeholders for a personal, non-commercial project; no affiliation
with or endorsement by Disney/Fox.
