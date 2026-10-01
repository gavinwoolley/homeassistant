# Grafana Minesweeper

A fully playable Minesweeper dashboard with reveal, flagging, elapsed time, and observability-style state tiles.

## Requirements

- Grafana OSS 12.1.x (tested target)
- Business Text plugin `marcusolsson-dynamictext-panel` version `6.1.0`
- No datasource, backend service, CDN, images, or network access

Install the required panel plugin:

```bash
grafana cli plugins install marcusolsson-dynamictext-panel 6.1.0
```

## Import

In Grafana, select **Dashboards ? New ? Import dashboard**, then upload `grafana-minesweeper.json`. No datasource mapping is needed.

## Controls

Left-click to reveal and right-click to flag. The dashboard automatically flags remaining mines after a win.

## Notes

This dashboard is self-contained in its Business Text panel JavaScript. Click the game panel before using keyboard controls. High-score and audio preferences, where applicable, use browser local storage. Add a screenshot when publishing the dashboard to the Grafana community catalog.
