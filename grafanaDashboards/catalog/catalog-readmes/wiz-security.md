# Wiz Security

Open Wiz findings by severity: issue trends over time, threat detections, and risk (posture/vulnerability) issues, filterable by project.

## Requirements

- [Infinity datasource](https://grafana.com/grafana/plugins/yesoreyeram-infinity-datasource/), v4.0.0+
- A Wiz Service Account, OAuth2 client-credentials auth, pointed at your tenant's GraphQL endpoint (`https://api.<region>.app.wiz.io/graphql`, token URL `https://auth.app.wiz.io/oauth/token`, audience `wiz-api`)

## Variables

- **Severity**: multi-select severity filter
- **Project**: multi-select Wiz project filter, populated live from your tenant

## Notes

Tables show the top 500 issues per query, sorted by severity. Refresh interval: 5m.
