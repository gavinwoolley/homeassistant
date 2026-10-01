#!/usr/bin/env python3
"""
Builds the curated dashboard set both demo Grafana flows mount read-only
(the Codespaces devcontainer's grafana-demo, and the local
demo/docker-compose.demo-observability.yml one).

Reuses publish/sanitize.py's existing redaction passes against the WHOLE
repo (not a dashboard-only reimplementation of the same rules - see
ENGINEERING_NOTES.md's "Passes are sequential, not combined" note for why
that would be risky to duplicate), then keeps only:

- Home Assistant.json - with five rows stripped, each for a data source
  that structurally cannot exist in this demo, ever, regardless of
  anything else being fixed (confirmed live per-row before dropping any
  of them - see DROP_ROW_TITLES below):
    - Logs - three Loki-backed panels. The demo has no Loki (see
      demo/alloy/config.alloy's own comment: no docker.sock access, by
      deliberate isolation design, so there's nothing to ship logs from
      regardless of whether Loki itself runs).
    - Home Assistant Host, Network - read HA's own system_monitor/
      speedtest integrations, neither configured in
      demo/configuration.yaml (confirmed live: zero matching entities in
      the demo HA's own /api/prometheus output).
    - Stats, Topology - read cAdvisor/UniFi/AdGuard-exporter/blackbox
      metrics; none of those services exist in this demo stack at all.
  Dropping a row that could only ever show "No data" isn't just cosmetic:
  it's also what let Loki itself be dropped as a service, rather than
  keeping it running empty forever just so its panels degrade to "No
  data" instead of a harder "datasource not found" error.
  Production's own copy of this dashboard is untouched; this stripping
  happens only to the copy staged here.

  Also rewrites every <img> src the sanitizer decoyed to the dead
  https://home.example.com:8123 domain (Who's Home avatars, Mower
  Location, 3D Printer, vacuum maps - confirmed live 2026-09-25, all
  permanently broken images otherwise) to
  /api/datasources/proxy/uid/ha-static-proxy instead, so the browser
  fetches through Grafana's own reachable origin rather than a domain that
  was never meant to resolve to anything - see rewrite_image_proxy_urls
  and demo/grafana/provisioning/datasources/datasources.yml's "HA Static
  Asset Proxy" entry for how.
- Games/ - already genericized/self-contained (see
  grafanaDashboards/catalog/README.md), works as-is.

Everything else in grafanaDashboards/dashboards/ (LGTM Stats, Topology,
per-service dashboards for AdGuard/Mosquitto/MongoDB/UniFi/cAdvisor/
node-exporter/windows-exporter, ...) is deliberately left out: none of
those services exist in this demo, so every one of those panels would
show "No data" forever, for every visitor, regardless of anything else
working - not a useful thing to provision by default. (Confirmed 2026-09-22
after the user found this out by testing every panel and asking "did we
add alloy/loki/mimir to the demo" - the original 2026-09-16 design
intentionally provisioned the whole catalogue "for browsing," but in
practice a visitor has no way to tell an inherently-empty panel from a
broken one, so scope was narrowed to only what can show real data here.)

Output goes to demo/grafana/dashboards/ - committed to git (unlike the
old copy-the-whole-tree version of this script, whose output was
gitignored and rebuilt on demand): the Codespaces devcontainer's compose
file mounts this directly with no build step of its own (the public
mirror has no publish/config/replacements.local.yaml to run
publish/sanitize.py against at all), so it has to already exist as
regular committed files, the same way demo/generated/ and
demo/automations.yaml are script-generated but checked in.

Usage:
    python demo/tools/build_demo_dashboards.py

Needs publish/config/replacements.local.yaml to exist locally (see
publish/README.md) - the same file publish/sanitize.py itself needs. Only
needed when re-running this after a real change to Home Assistant.json or
Games/ - the committed output already reflects the last run.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SANITIZE_OUT = REPO_ROOT / "publish" / "out"
DEMO_DASHBOARDS_OUT = REPO_ROOT / "demo" / "grafana" / "dashboards"

# Titles of the rows to drop from the demo's copy of Home Assistant.json -
# see module docstring for why each one. build_ha_dashboard.py nests each
# row's own panels inside that row's own "panels" list in the final JSON
# (confirmed live - NOT flat siblings the way the row()/crow() source reads
# in isolation), so removing each of these one top-level entries takes all
# of its children with it in one shot - nothing else to enumerate
# separately.
DROP_ROW_TITLES = {"Logs", "Home Assistant Host", "Network", "Stats", "Topology"}


def strip_unworkable_panels(dashboard_path: Path) -> None:
    dashboard = json.loads(dashboard_path.read_text(encoding="utf-8"))
    before = len(dashboard["panels"])
    dashboard["panels"] = [p for p in dashboard["panels"] if p.get("title") not in DROP_ROW_TITLES]
    removed = before - len(dashboard["panels"])
    if removed != len(DROP_ROW_TITLES):
        print(f"WARNING: expected to remove exactly {len(DROP_ROW_TITLES)} top-level "
              f"rows {sorted(DROP_ROW_TITLES)} from {dashboard_path.name}, removed "
              f"{removed} - one or more may have been renamed or restructured, check "
              f"DROP_ROW_TITLES above still matches.", file=sys.stderr)
    # open(), not write_text() - write_text()'s newline= param needs Python
    # 3.10+; open()'s has worked since long before this repo's minimum
    # supported version (see publish/sanitize.py's exact_pass for the same
    # fix, forced by a real CI break on python3.9 there).
    with open(dashboard_path, "w", encoding="utf-8", newline="") as f:
        f.write(json.dumps(dashboard, indent=2, ensure_ascii=False) + "\n")


# The sanitized dashboard's <img> tags (Who's Home avatars, Mower Location,
# 3D Printer, vacuum maps) all read `https://home.example.com:8123{{...}}` -
# publish/sanitize.py's own decoy for the real https://home.example.com:8123
# production genuinely uses. That decoy domain doesn't resolve to anything;
# every one of those images is permanently broken on the demo Grafana as a
# result (confirmed live 2026-09-25). Plain text substitution on the raw
# JSON, not a structured walk - these URLs are embedded deep inside HTML
# template strings across several unrelated panels, and a text replace is
# both simpler and safer than trying to find every one of them
# structurally. See demo/grafana/provisioning/datasources/datasources.yml's
# "HA Static Asset Proxy" entry for why this specific replacement path
# works (routes the browser's fetch through Grafana's own already-reachable
# origin instead of a dead domain).
DEAD_IMAGE_DOMAIN = "https://home.example.com:8123"
IMAGE_PROXY_PREFIX = "/api/datasources/proxy/uid/ha-static-proxy"


def rewrite_image_proxy_urls(dashboard_path: Path) -> None:
    text = dashboard_path.read_text(encoding="utf-8")
    n = text.count(DEAD_IMAGE_DOMAIN)
    text = text.replace(DEAD_IMAGE_DOMAIN, IMAGE_PROXY_PREFIX)
    if n == 0:
        print(f"WARNING: expected at least one {DEAD_IMAGE_DOMAIN!r} occurrence in "
              f"{dashboard_path.name} to rewrite, found none - the sanitizer's decoy "
              f"domain may have changed.", file=sys.stderr)
    with open(dashboard_path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def main() -> int:
    print("== Running publish/sanitize.py --dry-run to produce a sanitized tree ==")
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "publish" / "sanitize.py"), "--dry-run"],
        cwd=REPO_ROOT,
    )
    if result.returncode != 0:
        print("ERROR: sanitize.py failed - not building demo dashboards from a "
              "possibly-unsanitized or incomplete tree.", file=sys.stderr)
        return result.returncode

    source = SANITIZE_OUT / "grafanaDashboards" / "dashboards"
    if not source.is_dir():
        print(f"ERROR: expected sanitized dashboards at {source}, not found.",
              file=sys.stderr)
        return 1

    if DEMO_DASHBOARDS_OUT.exists():
        shutil.rmtree(DEMO_DASHBOARDS_OUT)
    DEMO_DASHBOARDS_OUT.mkdir(parents=True)

    print("== Copying Home Assistant.json (stripping unworkable rows) ==")
    ha_dest = DEMO_DASHBOARDS_OUT / "Home Assistant.json"
    shutil.copy2(source / "Home Assistant.json", ha_dest)
    strip_unworkable_panels(ha_dest)

    print("== Rewriting dead-domain image URLs to the Grafana proxy path ==")
    rewrite_image_proxy_urls(ha_dest)

    print("== Copying Games/ ==")
    shutil.copytree(source / "Games", DEMO_DASHBOARDS_OUT / "Games")

    print(f"== Done. {sum(1 for _ in DEMO_DASHBOARDS_OUT.rglob('*.json'))} "
          f"dashboard JSON files staged for the demo Grafana. ==")
    return 0


if __name__ == "__main__":
    sys.exit(main())
