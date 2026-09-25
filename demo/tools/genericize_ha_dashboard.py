#!/usr/bin/env python3
"""
Produces grafanaDashboards/catalog/Home Assistant.json - a grafana.com-
publishable copy of the dashboard, built from the SANITIZED version (see
demo/tools/build_demo_dashboards.py), never the live production one.

Why the sanitized version and not the raw one: this dashboard's panels query
specific entity_ids (person.homer_simpson, device_tracker.eleqqixh_dog, ...), so
it's only meaningfully importable/useful against an HA instance that has
matching entities - which is exactly what the public demo stack
(demo/docker-compose.demo.yml + demo/docker-compose.demo-observability.yml)
provides. Publishing the raw production dashboard would also leak real
names/domains baked into panel content (see the "Who's Home" family map).

Genericizes the three datasource references it uses (Loki, Mimir/Prometheus,
the Home Assistant Infinity datasource) into __inputs placeholders, the same
shape grafana.com's own listing flow and this repo's other catalog/ entries
already use (see catalog/LGTM-Stats.json) - the dashboard-level uid is left
alone, matching the existing convention that catalog/ files intentionally
share their uid with the live original since catalog/ is never provisioned
locally (see catalog/README.md).

Usage:
    python demo/tools/build_demo_dashboards.py   # produces the sanitized input first
    python demo/tools/genericize_ha_dashboard.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SOURCE = REPO_ROOT / "demo" / "grafana" / "dashboards" / "Home Assistant.json"
DEST = REPO_ROOT / "grafanaDashboards" / "catalog" / "Home Assistant.json"

# Production datasource uid -> __inputs placeholder name + plugin metadata.
DATASOURCE_MAP = {
    "P8E80F9AEF21F6940": ("DS_LOKI", "Loki", "loki", "Loki"),
    "PAE45454D0EDB9216": ("DS_PROMETHEUS", "Prometheus", "prometheus", "Prometheus"),
    "homeassistant-api": (
        "DS_HOMEASSISTANT", "Home Assistant (Infinity)",
        "yesoreyeram-infinity-datasource", "Infinity",
    ),
}
# mimir-alertmanager is only ever referenced from markdown link text in this
# dashboard, never as a panel/target datasource - nothing to genericize.


def _walk_replace_uids(obj):
    """Recursively replaces any {"uid": "<real-uid>", ...} datasource dict's
    uid with its __inputs placeholder, in place."""
    if isinstance(obj, dict):
        if "uid" in obj and obj["uid"] in DATASOURCE_MAP:
            obj["uid"] = "${%s}" % DATASOURCE_MAP[obj["uid"]][0]
        for v in obj.values():
            _walk_replace_uids(v)
    elif isinstance(obj, list):
        for v in obj:
            _walk_replace_uids(v)


def _collect_panel_types(obj, found: set[str]):
    if isinstance(obj, dict):
        t = obj.get("type")
        if isinstance(t, str) and ("gridPos" in obj or "panels" in obj):
            found.add(t)
        for v in obj.values():
            _collect_panel_types(v, found)
    elif isinstance(obj, list):
        for v in obj:
            _collect_panel_types(v, found)


def main() -> int:
    if not SOURCE.is_file():
        print(f"ERROR: {SOURCE} not found - run demo/tools/build_demo_dashboards.py first.",
              file=sys.stderr)
        return 1

    dashboard = json.loads(SOURCE.read_text(encoding="utf-8"))

    panel_types: set[str] = set()
    _collect_panel_types(dashboard, panel_types)

    _walk_replace_uids(dashboard)

    dashboard["id"] = None
    dashboard["description"] = (
        "This household's real Home Assistant + Grafana/Mimir/Loki dashboard, "
        "with names/places swapped out (see the repo's publish/ sanitizer). "
        "Entity IDs match the public demo stack - import against "
        "github.com/gavinwoolley/homeassistant's demo/ instance to see it "
        "render real (fake) data rather than empty panels."
    )
    dashboard["__inputs"] = [
        {"name": name, "label": label, "description": "", "type": "datasource",
         "pluginId": plugin_id, "pluginName": plugin_name}
        for name, label, plugin_id, plugin_name in DATASOURCE_MAP.values()
    ]
    dashboard["__requires"] = [
        {"type": "grafana", "id": "grafana", "name": "Grafana", "version": "10.0.0"},
        *[
            {"type": "datasource", "id": plugin_id, "name": plugin_name, "version": "1.0.0"}
            for _n, _l, plugin_id, plugin_name in DATASOURCE_MAP.values()
        ],
        *[
            {"type": "panel", "id": t, "name": t, "version": ""}
            for t in sorted(panel_types)
        ],
    ]

    DEST.parent.mkdir(parents=True, exist_ok=True)
    DEST.write_text(json.dumps(dashboard, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {DEST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
