# Home Assistant

A full household smart-home dashboard: who's home and where, a live family map with movement trails, cameras, motion, switches, climate, energy, irrigation, a robot mower, 3D printer, vacuum, and CI/CD build status - all in one view.

## Requirements

- [Infinity datasource](https://grafana.com/grafana/plugins/yesoreyeram-infinity-datasource/), pointed at a Home Assistant instance's `/api/states`
- Prometheus, scraping Home Assistant's own `/api/prometheus` endpoint (history for most panels)

## Notes

Every panel queries specific entity_ids (device names, serials, room labels) from one real household's own Home Assistant setup - there's no generic way to swap those for "whatever devices you own," so this won't show meaningful data against your own instance. It's meaningfully importable specifically against [this repo's public demo stack](https://github.com/gavinwoolley/homeassistant) (`demo/docker-compose.demo.yml` + `demo/docker-compose.demo-observability.yml`), whose entity_ids match what this dashboard expects.
