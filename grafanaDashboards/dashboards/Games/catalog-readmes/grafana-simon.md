# Grafana Simon

A playable incident-response memory game with four Grafana-style status tiles, sequence levels, attempts, and high score.

## Requirements

- Grafana OSS 12.1.x (tested target)
- Business Text plugin `marcusolsson-dynamictext-panel` version `6.1.0`
- No datasource, backend service, CDN, images, or network access

Install the required panel plugin:

```bash
grafana cli plugins install marcusolsson-dynamictext-panel 6.1.0
```

## Import

In Grafana, select **Dashboards ? New ? Import dashboard**, then upload `grafana-simon.json`. No datasource mapping is needed.

## Controls

Click a tile to begin, then repeat the displayed sequence. AUDIO: ON/OFF is optional.

## Notes

This dashboard is self-contained in its Business Text panel JavaScript. Click the game panel before using keyboard controls. High-score and audio preferences, where applicable, use browser local storage. Add a screenshot when publishing the dashboard to the Grafana community catalog.
