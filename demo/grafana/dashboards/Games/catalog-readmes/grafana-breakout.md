# Grafana Breakout

A Grafana-styled Breakout game with status-tile bricks, keyboard/mouse paddle control, lives, score, and high score.

## Requirements

- Grafana OSS 12.1.x (tested target)
- Business Text plugin `marcusolsson-dynamictext-panel` version `6.1.0`
- No datasource, backend service, CDN, images, or network access

Install the required panel plugin:

```bash
grafana cli plugins install marcusolsson-dynamictext-panel 6.1.0
```

## Import

In Grafana, select **Dashboards ? New ? Import dashboard**, then upload `grafana-breakout.json`. No datasource mapping is needed.

## Controls

Click to focus. Use Left/Right or A/D, or move the mouse. Space restarts after game over. AUDIO: ON/OFF is optional.

## Notes

This dashboard is self-contained in its Business Text panel JavaScript. Click the game panel before using keyboard controls. High-score and audio preferences, where applicable, use browser local storage. Add a screenshot when publishing the dashboard to the Grafana community catalog.
