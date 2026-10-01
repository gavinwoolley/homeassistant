# Grafana Arcade

A self-contained arcade dashboard pack for **Grafana OSS 12.1.x**. Every dashboard uses Business Text 6.1.0; no datasource, backend, CDN, or network call is required. Dashboard JSON uses Grafana's classic export format, for direct imports, file provisioning, and Grafana.com dashboard-library uploads.

## This repository's Grafana deployment

This repository provisions the Arcade automatically. The Grafana service mounts
`grafanaDashboards/dashboards` at `/var/lib/grafana/dashboards`, scans for
changes every 30 seconds, and now mirrors the source directories as Grafana
folders. The Arcade therefore appears in the **Games** folder.

The Compose service also installs `marcusolsson-dynamictext-panel` before
dashboard provisioning, so the games render after a clean Grafana deployment.

On the Docker host, deploy repository changes and recreate Grafana once to pick
up Compose/plugin changes:

```bash
cd /home/homeassistant/.homeassistant
docker compose up -d grafana
docker compose logs --tail=100 grafana
```

After that, JSON edits are detected automatically within 30 seconds; no manual
dashboard import is needed. Provisioned dashboards are source-controlled, so
change their JSON files in this repository rather than editing them in Grafana.

## Standalone install/import

```bash
grafana cli plugins install marcusolsson-dynamictext-panel 6.1.0
```

Restart Grafana, then import every `grafana-*.json` file in this directory. Start with **Grafana Arcade** (`grafana-arcade`); its cards use relative `/d/<uid>` links. Browser localStorage retains high scores.

| File | UID | Description / controls |
|---|---|---|
| grafana-arcade.json | grafana-arcade | Launcher |
| grafana-snake-v2.json | grafana-snake | Snake: arrows/WASD, Space restart |
| grafana-pong.json | grafana-pong | Pong: click panel to focus; controls shown in panel |
| grafana-breakout.json | grafana-breakout | Breakout: click panel to focus; controls shown in panel |
| grafana-2048.json | grafana-2048 | 2048: click panel to focus; controls shown in panel |
| grafana-minesweeper.json | grafana-minesweeper | Minesweeper: click panel to focus; controls shown in panel |
| grafana-pacman.json | grafana-pacman | Pac-Man: arrows/WASD, Space restart |
| grafana-sre-tetris.json | grafana-sre-tetris | SRE Tetris: click panel to focus; controls shown in panel |
| grafana-tic-tac-toe.json | grafana-tic-tac-toe | Grot-Tac-Toe: click a square or use keys 1?9; R starts a new round |
| grafana-alert-whack-a-mole.json | grafana-alert-whack-a-mole | Alert Whack-a-Mole: click panel to focus; controls shown in panel |
| grafana-cardinality-invaders.json | grafana-cardinality-invaders | Cardinality Invaders: click panel to focus; controls shown in panel |
| grafana-asteroids.json | grafana-asteroids | Asteroids: click panel to focus; controls shown in panel |
| grafana-simon.json | grafana-simon | Simon: click panel to focus; controls shown in panel |

| grafana-grot-road-rage.json | grafana-grot-road-rage | Grot Road Rage: Left/Right or A/D dodge hazards |

| grafana-grot-observability-run.json | grafana-grot-observability-run | Grot Observability Run: jump incoming incidents |

## Notes

Games are intentionally single-panel dashboards and need manual browser testing after import, especially keyboard focus inside embedded/edited Grafana panels. Snake, Pong, Breakout, SRE Tetris, Alert Whack-a-Mole, Cardinality Invaders, Asteroids, and Pac-Man include synthesized sound effects and an `AUDIO: ON/OFF` control. Audio defaults to off; the shared preference is retained in browser local storage. The launcher has an opt-in `MUSIC: ON/OFF` arcade riff using the same preference. The launcher expects the stable UIDs listed above. `grafana-snake-v2.json` is the retained supplied Snake dashboard (its filename differs from the launcher UID target).

## Grafana.com publishing content

Each dashboard has a catalog-ready description embedded in its JSON and a matching submission README in [`catalog-readmes/`](catalog-readmes/). Use the matching Markdown file as the starting point for the Grafana.com listing README, then add a current screenshot in the Grafana.com editor.
