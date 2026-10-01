# Grafana SRE Tetris

A complete SRE-themed Tetris game whose colored tetrominoes represent operational signals, load, and incidents.

## Requirements

- Grafana OSS 12.1.x (tested target)
- Business Text plugin `marcusolsson-dynamictext-panel` version `6.1.0`
- No datasource, backend service, CDN, images, or network access

Install the required panel plugin:

```bash
grafana cli plugins install marcusolsson-dynamictext-panel 6.1.0
```

## Import

In Grafana, select **Dashboards ? New ? Import dashboard**, then upload `grafana-sre-tetris.json`. No datasource mapping is needed.

## Controls

Click to focus. Arrow keys move, Up rotates, and Space restarts after game over. AUDIO: ON/OFF enables effects and an optional chiptune loop.

## Notes

This dashboard is self-contained in its Business Text panel JavaScript. Click the game panel before using keyboard controls. High-score and audio preferences, where applicable, use browser local storage. Add a screenshot when publishing the dashboard to the Grafana community catalog.
