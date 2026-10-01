# DevOps Pull Requests and Commits

Per-repository report of completed pull requests and commits in an Azure DevOps project, with author breakdown.

## Requirements

- [Infinity datasource](https://grafana.com/grafana/plugins/yesoreyeram-infinity-datasource/)
- Basic Auth, password = a PAT (user or service account) with **Code (Read)** scope

## Variables

- **Azure DevOps organization** (`AZDO_ORG`): textbox; set this first, every query depends on it
- **project**: single-select, populated live
- **repo_id**: multi-select, populated live; each selection repeats the Pull Requests/Commits rows

## Notes

Azure DevOps caps list responses at 101 results per call. Each panel shows at most the 101 most recent PRs/commits per repo in the selected time range.
