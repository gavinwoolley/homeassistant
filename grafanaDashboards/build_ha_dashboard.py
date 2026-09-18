# Generates dashboards/Home Assistant.json and dashboards/Topology.json.
# These two files are GENERATED - do not hand-edit their JSON. If you add a
# container/probe/panel to the topology or the main dashboard, add it here and
# run:
#   python grafanaDashboards/build_ha_dashboard.py
# from the repo root, then commit the regenerated JSON alongside this script.
# (History: before this script was committed, two different sessions hand-
# patched Topology.json's mermaid content directly - each regeneration from
# this script silently dropped those edits until they were folded in here.)
import copy
import json
import os
import shutil
import subprocess
from datetime import date, timedelta

MIMIR = {"type": "prometheus", "uid": "PAE45454D0EDB9216"}
LOKI = {"type": "loki", "uid": "P8E80F9AEF21F6940"}

panels = []
_id = [0]
def nid():
    _id[0] += 1
    return _id[0]

REF = [chr(c) for c in range(ord("A"), ord("Z") + 1)]
REF += ["A" + chr(c) for c in range(ord("A"), ord("Z") + 1)]

def t(expr, legend, refId, instant=False):
    return {"datasource": MIMIR, "editorMode": "code", "expr": expr,
            "instant": instant, "range": not instant,
            "legendFormat": legend, "refId": refId}

# curated batteries: the people/devices we care about, with human labels
BATT_LABELS = [
    ("pixel_10_pro_battery_level", "Homer Simpson - Pixel 10"),
    ("pixel_9_pro_battery_level", "Marge Simpson - Pixel 9"),
    ("pixel_6_pro_lisa_simpson_battery_level", "Lisa Simpson - Pixel 6"),
    ("dog_battery_level", "Dog"),
    ("oneplus_watch_battery_level", "Homer Simpson - Watch"),
    ("wt_11w_battery_level", "Irrigation Valve"),
]
BATTSTEPS = [{"color": "red", "value": None}, {"color": "orange", "value": 20},
             {"color": "yellow", "value": 40}, {"color": "green", "value": 60}]
def batt_targets(instant=True):
    return [t(f'homeassistant_sensor_battery_percent{{entity="sensor.{e}"}}', lbl, REF[i], instant=instant)
            for i, (e, lbl) in enumerate(BATT_LABELS)]

# ---------------------------------------------------------------- diagram
def _diagram_css(pid, fs):
    # jdbranham hard-codes `.label { font-size: 0.75rem }` in a <style> it injects
    # AFTER render, so the mermaid `%%{init fontSize}%%` never shows. Our Custom CSS
    # ("style" option) is appended after that rule -> !important wins it back.
    # Also flex-centre the label inside the (min-height stretched) foreignObject so
    # the text sits in the middle of the box instead of pinned to the top.
    #
    # The font/size "jump a minute after load" bug: mermaid 8.8.0's flowchart
    # renderer (src read from the actual bundled dist, not guessed) does, per
    # render:
    #   if (conf.useMaxWidth) { svg.attr('width','100%'); svg.attr('style',
    #     `max-width: ${w}px;`) } else { svg.attr('height', h); svg.attr(
    #     'width', w) }   // no style at all in this branch
    # We set useMaxWidth:false below, so on first paint the <svg> has plain
    # numeric width/height attributes and NO style - looks right. But
    # jdbranham's updateDiagramStyle() ALSO unconditionally runs, on every
    # panel data refresh (every ~1m here), regardless of useMaxWidth:
    #   if (options.maxWidth) { select(svg).style('max-width','100%') }
    # - a plain (non-!important) INLINE style, freshly re-applied each
    # refresh, that's what was scaling the whole diagram up to fill the panel
    # a while after first load and never reverting. An !important rule in an
    # external stylesheet beats a non-!important inline style regardless of
    # which was applied more recently, so lock max-width/max-height here -
    # this is the fix, not useMaxWidth:false alone (kept anyway: it's what
    # gives the SVG a stable intrinsic width/height to lock to).
    d = f"#diagram-{pid}"
    return (
        # locking the SVG's size means it no longer auto-shrinks to fit a
        # narrow panel/viewport - let the container scroll instead of
        # silently clipping if that ever happens.
        f".diagram-container-{pid}{{overflow:auto !important;}}"
        f"{d} svg{{max-width:none !important;max-height:none !important;}}"
        f"{d} .label,{d} .nodeLabel,{d} span.nodeLabel,{d} .diagram-value,"
        f"{d} foreignObject div{{font-size:{fs}px !important;line-height:1.15 !important;"
        f"text-shadow:none !important;}}"
        f"{d} .edgeLabel{{font-size:{fs}px !important;}}"
        f"{d} foreignObject{{overflow:visible;}}"
        f"{d} foreignObject>div{{display:flex !important;flex-direction:column !important;"
        f"align-items:center !important;justify-content:center !important;"
        f"height:100% !important;width:100% !important;}}"
    )

def diagram_panel(title, content, targets, gridPos, fs=24, node=(150, 62)):
    pid = nid()
    return {
        "datasource": MIMIR,
        "type": "jdbranham-diagram-panel",
        "pluginVersion": "1.7.3",
        "id": pid,
        "title": title,
        "transparent": True,
        "gridPos": gridPos,
        "fieldConfig": {
            "defaults": {
                "unit": "ms",
                "decimals": 1,
                "mappings": [],
                "thresholds": {"mode": "absolute", "steps": [
                    {"color": "green", "value": None},
                    {"color": "yellow", "value": 100},
                    {"color": "red", "value": 400},
                ]},
            },
            "overrides": [],
        },
        "options": {
            "composites": [],
            "content": content,
            "decimals": 1,
            "legend": {"show": False, "asTable": True, "displayMode": "table",
                       "placement": "bottom", "gradient": {"enabled": True, "show": True},
                       "stats": ["mean", "last", "min", "max"], "showLegend": False},
            "maxWidth": True,
            "mermaidServiceUrl": "",
            "metricCharacterReplacements": [],
            "moddedSeriesVal": 0,
            "mode": "content",
            "nodeSize": {"minWidth": node[0], "minHeight": node[1]},
            "style": _diagram_css(pid, fs),
            "useBackground": False,
            "useBasicAuth": False,
            "valueName": "last",
        },
        "targets": targets,
    }

def probe(slug, job):
    return f'probe_duration_seconds{{instance="{slug}",job="{job}"}} * 1000'

# node id == blackbox instance slug == series legendFormat (the jdbranham panel
# matches a series to the graph node whose *id* equals the series name; ids must
# be CSS-selector-safe, so slugs - not "Server 1" - and the human label goes in
# the [brackets]).
# (node_id, label, probe_instance or None, job)  -- node_id is the mermaid id AND
# the series legendFormat; probe_instance is the blackbox `instance` label.
NET = [
    ("google_dns", "Google DNS", "google_dns", "blackbox_icmp"),
    ("cloudflare_dns", "Cloudflare DNS", "cloudflare_dns", "blackbox_icmp"),
    ("firewall", "Firewall", "firewall", "blackbox_icmp"),
    ("hp_switch", "HP Switch", "hp_switch", "blackbox_icmp"),
    ("server_1", "Server 1", "server_1", "blackbox_icmp"),
    ("server_2", "Server 2", "server_2", "blackbox_icmp"),
    ("server_3", "Server 3", "server_3", "blackbox_icmp"),
    ("plex", "Plex (VM)", "plex", "blackbox_icmp"),
    ("blue_iris", "Blue Iris (VM)", "blue_iris", "blackbox_icmp"),
    ("ubuntu", "Ubuntu VM (Docker)", "this_host", "blackbox_icmp"),
    ("home_assistant", "Home Assistant", "home_assistant", "blackbox_http"),
    ("grafana", "Grafana", "grafana", "blackbox_http"),
    ("mimir", "Mimir", "mimir", "blackbox_http"),
    ("loki", "Loki", "loki", "blackbox_http"),
    ("alloy", "Alloy", "alloy", "blackbox_http"),
    ("cadvisor", "cAdvisor", "cadvisor", "blackbox_http"),
    ("portainer", "Portainer", "portainer", "blackbox_http"),
    ("coder", "Coder", "coder", "blackbox_http"),
    ("adguard", "AdGuard", "adguard", "blackbox_http"),
    ("nginx", "Nginx", "nginx_external", "blackbox_http"),
    ("mosquitto", "Mosquitto", "mosquitto", "blackbox_tcp"),
    ("unpoller", "UnPoller", "unpoller", "blackbox_http"),
    ("unifi_controller", "UniFi Controller", "unifi_controller", "blackbox_http"),
    ("unifi_db", "UniFi DB (Mongo)", "unifi_db", "blackbox_tcp"),
    ("mongodb_exporter", "MongoDB Exporter", "mongodb_exporter", "blackbox_http"),
    ("nginx_exporter", "Nginx Exporter", "nginx_exporter", "blackbox_http"),
    ("mosquitto_exporter", "Mosquitto Exporter", "mosquitto_exporter", "blackbox_http"),
    ("adguard_exporter", "AdGuard Exporter", "adguard_exporter", "blackbox_http"),
    ("u6_pro_hallway", "U6 Pro Hallway", "u6_pro_hallway", "blackbox_icmp"),
    ("u7_kitchen", "U7 Pro Kitchen", "u7_kitchen", "blackbox_icmp"),
    ("u7_lite_office", "U7 Lite Office", "u7_lite_office", "blackbox_icmp"),
    ("ac_lite_lounge", "AC Lite Lounge", "ac_lite_lounge", "blackbox_icmp"),
    ("uap_drive", "UAP Drive", "uap_drive", "blackbox_icmp"),
    ("uap_garden", "UAP Garden", "uap_garden", "blackbox_icmp"),
]
label = {s: l for s, l, *_ in NET}

containers = ["home_assistant", "grafana", "mimir", "loki", "alloy", "cadvisor", "portainer",
              "coder", "adguard", "nginx", "mosquitto", "unpoller", "unifi_controller", "unifi_db",
              "mongodb_exporter", "nginx_exporter", "mosquitto_exporter", "adguard_exporter"]
aps = ["u6_pro_hallway", "u7_kitchen", "u7_lite_office", "ac_lite_lounge", "uap_drive", "uap_garden"]

# mermaid node shape per kind of thing:
#   {{ }} hexagon = external internet   { } diamond = firewall/gateway
#   [/ \] trapezoid = network switch    [[ ]] subroutine = physical server
#   ( ) rounded = VM                    [( )] cylinder = database
#   ([ ]) stadium = wifi AP             [ ] rect = container/service (default)
SHAPE = {"google_dns": ("{{", "}}"), "cloudflare_dns": ("{{", "}}"),
         "firewall": ("{", "}"), "hp_switch": ("[/", "\\]"),
         "server_1": ("[[", "]]"), "server_2": ("[[", "]]"), "server_3": ("[[", "]]"),
         "plex": ("(", ")"), "blue_iris": ("(", ")"), "ubuntu": ("(", ")"),
         "unifi_db": ("[(", ")]")}
SHAPE.update({a: ("([", "])") for a in aps})
def n(s):
    o, c = SHAPE.get(s, ("[", "]"))
    return f'{s}{o}"{label[s]}"{c}'

# graph LR: ranks run left->right (Internet -> Firewall -> Switch -> Servers ->
# VMs -> Containers), so the long Containers list stacks VERTICALLY into the
# tall panel instead of blowing the width out sideways.
# NOTE: per-subgraph `direction` (to render WiFi/Cameras as a horizontal row
# while Containers stays a vertical column) is NOT available - the plugin
# bundles mermaid 8.8.0 (confirmed from the actual published plugin .zip),
# which predates subgraph `direction` support entirely: it parses `direction`
# as a bare vertex id, then chokes on the following word ("TB TB"/"direction
# TB a([...")). Validated against a local mermaid@8.8.0 parse (see
# grafanaDashboards/validate_mermaid.js) - do not reintroduce this without
# that script passing first. Every subgraph in this diagram therefore
# inherits the parent `graph LR` direction (all vertical columns).
# nodeSpacing = gap between stacked siblings (tight); rankSpacing = gap between
# columns (wide, for the long labels).
# useMaxWidth:false -> the SVG gets fixed pixel dimensions instead of
# width=100%+max-width:<Npx>. The plugin otherwise rewrites that max-width to
# 100% a few seconds after first paint (on data arrival) regardless of the
# panel's own maxWidth option, scaling the whole diagram up and making the
# text balloon every time. With fixed dims that rewrite is a no-op.
_MERMAID_INIT = ("%%{init: {'flowchart': {'nodeSpacing': 14, 'rankSpacing': 90, "
                 "'padding': 6, 'useMaxWidth': false}}}%%")
L = [_MERMAID_INIT, "graph LR"]
L.append("subgraph Internet")
L += [f"  {n('google_dns')}", f"  {n('cloudflare_dns')}"]
L.append("end")
L.append(f"{n('google_dns')} --- {n('firewall')}")
L.append(f"{n('cloudflare_dns')} --- {n('firewall')}")
L.append(f"{n('firewall')} --> {n('hp_switch')}")
for s in ("server_1", "server_2", "server_3"):
    L.append(f"{n('hp_switch')} --> {n(s)}")
L.append(f"{n('server_3')} --> {n('plex')}")
L.append(f"{n('server_2')} --> {n('blue_iris')}")
L.append(f"{n('server_2')} --> {n('ubuntu')}")
L.append("subgraph Containers")
L += [f"  {n(c)}" for c in containers]
L.append("end")
for c in containers:
    L.append(f"{n('ubuntu')} --> {n(c)}")
L.append("subgraph WiFi")
L += [f"  {n(a)}" for a in aps]
L.append("end")
for a in aps:
    L.append(f"{n('unifi_controller')} --> {n(a)}")
# cameras hang off Blue Iris (same diagram, forked below it)
CAMS = [
    ("camera_front", "Front Camera"),
    ("camera_patio", "Patio Camera"),
    ("camera_garden_upper", "Garden Upper Camera"),
    ("camera_shed_upper", "Shed Upper Camera"),
    ("camera_shed_lower", "Shed Lower Camera"),
    ("camera_bart_simpson_room", "Bart Simpson Room Camera"),
]
L.append("subgraph Cameras")
L += [f'  {s}["{l}"]' for s, l in CAMS]
L.append("end")
for s, _l in CAMS:
    L.append(f"{n('blue_iris')} --> {s}")
# dependency / data-flow links (dotted)
deps = [
    ("unifi_controller", "unifi_db"),
    ("unpoller", "unifi_controller"),
    ("mosquitto", "home_assistant"),
    ("mosquitto", "blue_iris"),
    ("alloy", "loki"),
    ("alloy", "mimir"),
    ("grafana", "loki"),
    ("grafana", "mimir"),
    ("mongodb_exporter", "unifi_db"),
    ("nginx_exporter", "nginx"),
    ("mosquitto_exporter", "mosquitto"),
    ("adguard_exporter", "adguard"),
]
for a, b in deps:
    L.append(f"{a} -.-> {b}")
net_content = "\n".join(L) + "\n"
net_targets = []
_i = 0
for node_id, _lbl, inst, job in NET:
    if inst is None:
        continue
    net_targets.append(t(probe(inst, job), node_id, REF[_i], instant=True))
    _i += 1
for j, (s, _l) in enumerate(CAMS):
    net_targets.append(t(probe(s, "blackbox_icmp"), s, REF[_i + j], instant=True))
_net_panel = diagram_panel("Network Diagram", net_content, net_targets,
                           {"h": 40, "w": 24, "x": 0, "y": 0}, fs=13, node=(150, 54))

# ---------------------------------------------------------------- helpers
def row(title, y):
    return {"type": "row", "id": nid(), "title": title, "collapsed": False,
            "gridPos": {"h": 1, "w": 24, "x": 0, "y": y}, "panels": []}

def ts(title, targets, gridPos, unit="short", fill=10, draw="line", stack=False):
    return {
        "datasource": MIMIR, "type": "timeseries", "id": nid(), "title": title,
        "gridPos": gridPos,
        "fieldConfig": {"defaults": {
            "unit": unit,
            "custom": {"drawStyle": draw, "lineInterpolation": "smooth", "lineWidth": 1,
                       "fillOpacity": fill, "showPoints": "never", "spanNulls": False,
                       "stacking": {"mode": "normal" if stack else "none"}},
            "color": {"mode": "palette-classic"}}, "overrides": []},
        "options": {"legend": {"displayMode": "table", "placement": "bottom",
                               "calcs": ["mean", "max", "last"], "showLegend": True},
                    "tooltip": {"mode": "multi", "sort": "desc"}},
        "targets": targets,
    }

def bargauge(title, expr, legend, gridPos, unit="percent", mn=0, mx=100):
    return {
        "datasource": MIMIR, "type": "bargauge", "id": nid(), "title": title, "gridPos": gridPos,
        "fieldConfig": {"defaults": {
            "unit": unit, "min": mn, "max": mx,
            "thresholds": {"mode": "absolute", "steps": [
                {"color": "red", "value": None}, {"color": "orange", "value": 20},
                {"color": "yellow", "value": 40}, {"color": "green", "value": 60}]}},
            "overrides": []},
        "options": {"displayMode": "lcd", "orientation": "horizontal",
                    "valueMode": "color", "showUnfilled": True,
                    "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}},
        "targets": [t(expr, legend, "A", instant=True)],
    }

def stat(title, expr, gridPos, mappings=None, thresholds=None, unit="none",
         colormode="background", text="value_and_name", legend="{{friendly_name}}"):
    return {
        "datasource": MIMIR, "type": "stat", "id": nid(), "title": title, "gridPos": gridPos,
        "fieldConfig": {"defaults": {
            "unit": unit, "mappings": mappings or [],
            "thresholds": {"mode": "absolute",
                           "steps": thresholds or [{"color": "green", "value": None}]}},
            "overrides": []},
        "options": {"colorMode": colormode, "graphMode": "none", "justifyMode": "auto",
                    "orientation": "auto", "textMode": text,
                    "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}},
        "targets": [t(expr, legend, "A", instant=True)],
    }

def state_timeline(title, targets, gridPos, mappings, steps):
    return {
        "datasource": MIMIR, "type": "state-timeline", "id": nid(), "title": title, "gridPos": gridPos,
        "fieldConfig": {"defaults": {
            "custom": {"fillOpacity": 80, "lineWidth": 0, "insertNulls": False},
            "mappings": mappings,
            "color": {"mode": "thresholds"},
            "thresholds": {"mode": "absolute", "steps": steps}}, "overrides": []},
        "options": {"mergeValues": True, "showValue": "never", "alignValue": "left",
                    "rowHeight": 0.9, "legend": {"showLegend": False},
                    "tooltip": {"mode": "single", "sort": "none"}},
        "targets": targets,
    }

def logs(title, expr, gridPos):
    return {
        "datasource": LOKI, "type": "logs", "id": nid(), "title": title, "gridPos": gridPos,
        "options": {"showTime": True, "showLabels": False, "showCommonLabels": False,
                    "wrapLogMessage": True, "prettifyLogMessage": False, "enableLogDetails": True,
                    "dedupStrategy": "none", "sortOrder": "Descending"},
        "targets": [{"datasource": LOKI, "editorMode": "code", "expr": expr,
                     "queryType": "range", "refId": "A"}],
    }

y = 2  # rows 0 and 1 are the inserted Topology + Infra Stats collapsed rows
# ---------------- Status
panels.append(row("Status", y)); y += 1
panels.append(stat("Entities Online",
                   # exclude the automation domain: HA reports every *disabled*
                   # automation as unavailable, which is not an outage.
                   'round(100 * count(homeassistant_entity_available{domain!="automation"} == 1)'
                   ' / count(homeassistant_entity_available{domain!="automation"}))',
                   {"h": 5, "w": 5, "x": 0, "y": y}, unit="percent", text="value", legend="Online",
                   colormode="value",
                   thresholds=[{"color": "orange", "value": None}, {"color": "yellow", "value": 85},
                               {"color": "green", "value": 93}]))
panels.append({
    "datasource": MIMIR, "type": "stat", "id": nid(), "title": "People Home",
    "gridPos": {"h": 5, "w": 9, "x": 5, "y": y},
    "fieldConfig": {"defaults": {
        "unit": "none",
        "mappings": [{"type": "value", "options": {
            "0": {"text": "Away", "color": "dark-red", "index": 0},
            "1": {"text": "Home", "color": "green", "index": 1}}}],
        "thresholds": {"mode": "absolute", "steps": [{"color": "text", "value": None}]}},
        "overrides": []},
    "options": {"colorMode": "background", "graphMode": "none", "justifyMode": "auto",
                "orientation": "auto", "textMode": "value_and_name",
                "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": True}},
    "targets": [t('homeassistant_person_state', "{{friendly_name}}", "A", instant=True)],
})
panels.append(stat("Updates Available",
                   'sum(homeassistant_update_state) or vector(0)',
                   {"h": 5, "w": 5, "x": 14, "y": y}, unit="none", text="value", legend="Updates",
                   colormode="value",
                   thresholds=[{"color": "text", "value": None}, {"color": "yellow", "value": 1},
                               {"color": "orange", "value": 10}]))
panels.append(stat("Automations Fired (24h)",
                   'round(sum(increase(homeassistant_automation_triggered_count_total[24h])))',
                   {"h": 5, "w": 5, "x": 19, "y": y}, unit="none", text="value", legend="Fired",
                   colormode="value", thresholds=[{"color": "text", "value": None}]))
y += 5

# ---------------- Home Assistant Host
panels.append(row("Home Assistant Host", y)); y += 1
panels.append(ts("System Metrics", [
    t('homeassistant_sensor_unit_percent{entity="sensor.processor_use_percent"}', "CPU Use", "A"),
    t('homeassistant_sensor_unit_percent{entity="sensor.memory_use_percent"}', "Memory Use", "B"),
    t('homeassistant_sensor_state{entity=~"sensor.load_(1|5|15)m"}', "{{friendly_name}}", "C"),
], {"h": 8, "w": 12, "x": 0, "y": y}, unit="percent"))
panels.append(ts("Disk Space", [
    t('homeassistant_sensor_unit_percent{entity="sensor.system_monitor_disk_usage"}', "Disk / used", "A"),
    t('homeassistant_sensor_unit_percent{entity="sensor.system_monitor_disk_usage_config"}', "Disk /config used", "B"),
], {"h": 8, "w": 12, "x": 12, "y": y}, unit="percent"))
y += 8

# ---------------- Network
panels.append(row("Network", y)); y += 1
panels.append(ts("Internet Speed", [
    t('homeassistant_sensor_data_rate_mbit_per_s{entity="sensor.speedtest_download"}', "Download", "A"),
    t('homeassistant_sensor_data_rate_mbit_per_s{entity="sensor.speedtest_upload"}', "Upload", "B"),
], {"h": 8, "w": 12, "x": 0, "y": y}, unit="Mbits"))
panels.append(ts("Response Times", [
    t('probe_duration_seconds{job=~"blackbox_(icmp|http|tcp)"} * 1000 <= 5000', "{{instance}} ({{job}})", "A"),
], {"h": 8, "w": 12, "x": 12, "y": y}, unit="ms", fill=0))
y += 8

# ---------------- Climate & Environment
panels.append(row("Climate & Environment", y)); y += 1
# One temperature panel: the climate entities' current temp covers every room
# (incl. the lounge, which has no AC) with clean names, plus outside and the
# per-room setpoints.
panels.append(ts("Temperature", [
    t('homeassistant_sensor_temperature_celsius{entity="sensor.outside_temperature"}', "Outside", "A"),
    t('homeassistant_climate_current_temperature_celsius', "{{friendly_name}}", "B"),
    t('homeassistant_climate_target_temperature_celsius', "{{friendly_name}} target", "C"),
], {"h": 8, "w": 12, "x": 0, "y": y}, unit="celsius", fill=0))
panels.append(ts("Humidity", [
    t('homeassistant_sensor_humidity_percent{entity="sensor.home_homer_simpson_com_humidity"}', "Outside", "A"),
    t('homeassistant_sensor_humidity_percent{entity="sensor.lounge_humidity"}', "Lounge", "B"),
    t('homeassistant_sensor_humidity_percent{entity="sensor.p2s_22e8bj620203679_ams_1_humidity"}', "P2S 3D Printer", "C"),
], {"h": 8, "w": 12, "x": 12, "y": y}, unit="humidity", fill=0))
y += 8

# ---------------- Home
panels.append(row("Home", y)); y += 1
panels.append(state_timeline("Motion & Occupancy", [
    t('homeassistant_binary_sensor_state{entity=~".*(motion|occupancy).*"}', "{{friendly_name}}", "A"),
], {"h": 8, "w": 12, "x": 0, "y": y},
    mappings=[{"type": "value", "options": {
        "0": {"text": "clear", "color": "dark-green", "index": 0},
        "1": {"text": "motion", "color": "orange", "index": 1}}}],
    steps=[{"color": "dark-green", "value": None}, {"color": "orange", "value": 1}]))
panels.append(ts("Power Usage", [
    t('homeassistant_sensor_power_w{entity!~".*(battery|corrected).*"}', "{{friendly_name}}", "A"),
    t('homeassistant_sensor_power_kw{entity!~".*(battery|corrected).*"} * 1000', "{{friendly_name}}", "B"),
], {"h": 8, "w": 12, "x": 12, "y": y}, unit="watt"))
panels.append({
    "datasource": MIMIR, "type": "bargauge", "id": nid(), "title": "Battery Levels",
    "gridPos": {"h": 8, "w": 12, "x": 0, "y": y + 8},
    "fieldConfig": {"defaults": {"unit": "percent", "min": 0, "max": 100,
        "thresholds": {"mode": "absolute", "steps": BATTSTEPS}}, "overrides": []},
    "options": {"displayMode": "lcd", "orientation": "horizontal", "valueMode": "color",
                "showUnfilled": True, "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}},
    "targets": batt_targets(),
})
panels.append(ts("Automations Triggered (1h)", [
    t('increase(homeassistant_automation_triggered_count_total[1h])', "{{friendly_name}}", "A"),
], {"h": 8, "w": 12, "x": 12, "y": y + 8}, unit="short", draw="bars", fill=70))
y += 16

# ---------------- Logs
panels.append(row("Logs", y)); y += 1
panels.append(logs("Home Assistant Logs", '{service_name="home-assistant"}', {"h": 11, "w": 8, "x": 0, "y": y}))
panels.append(logs("Nginx Access Logs", '{service_name="nginx_access"}', {"h": 11, "w": 8, "x": 8, "y": y}))
panels.append(logs("Errors & Warnings",
                   '{job="docker"} |~ `(?i)(error|warn|critical|fatal|panic)` != `will attempt privileged`',
                   {"h": 11, "w": 8, "x": 16, "y": y}))
y += 11

# ================================================================= collapsed rows
HA = {"type": "yesoreyeram-infinity-datasource", "uid": "homeassistant-api"}

def inf(root_selector, columns, refId="A", url="/states"):
    return {"datasource": HA, "refId": refId, "type": "json", "source": "url",
            "format": "table", "parser": "backend", "url": url,
            "url_options": {"method": "GET", "data": ""},
            "root_selector": root_selector, "columns": columns, "filters": []}

def c(sel, text, typ="string"):
    return {"selector": sel, "text": text, "type": typ}

def dom(d):
    return f'$substringBefore($v.entity_id, ".") = "{d}"'

def ha_table(title, root_selector, columns, gridPos, url="/states", target=None):
    names = [col["text"] for col in columns]
    return {"datasource": HA, "type": "table", "id": nid(), "title": title, "gridPos": gridPos,
            "fieldConfig": {"defaults": {"custom": {"align": "auto", "filterable": True,
                            "cellOptions": {"type": "auto"}}}, "overrides": []},
            "options": {"showHeader": True, "cellHeight": "sm", "footer": {"show": False}},
            "transformations": [{"id": "organize", "options": {
                "indexByName": {n: i for i, n in enumerate(names)},
                "renameByName": {}, "excludeByName": {}}}],
            "targets": [target or inf(root_selector, columns, url=url)]}

def inf_template(template, columns, refId="A"):
    return {"datasource": HA, "refId": refId, "type": "json", "source": "url",
            "format": "table", "parser": "backend", "url": "/template",
            "url_options": {"method": "POST", "body_type": "raw",
                            "body_content_type": "application/json",
                            "data": json.dumps({"template": template})},
            "root_selector": "", "columns": columns, "filters": []}

def ha_kv(title, pairs, gridPos, k="Item", v="State"):
    """Two-column table with hand-written labels: pairs = [(label, jinja_expr)].
    Sidesteps the mangled `<device_id> <sensor>` friendly names."""
    rows = ",".join("{'" + k + "': '" + lbl.replace("'", "") + "', '" + v + "': " + expr + "}"
                    for lbl, expr in pairs)
    cols = [c(k, k), c(v, v)]
    return ha_table(title, "", cols, gridPos,
                    target=inf_template("{{ [" + rows + "] | tojson }}", cols))

def annolist(title, tags, gridPos):
    return {
        "datasource": {"type": "grafana", "uid": "-- Grafana --"},
        "type": "annolist", "id": nid(), "title": title, "gridPos": gridPos,
        "options": {"onlyFromThisDashboard": False, "onlyInTimeRange": False, "tags": tags,
                    "limit": 20, "showTags": True, "showUser": False, "showTime": True,
                    "navigateToPanel": False, "navigateBefore": "6h", "navigateAfter": "6h"},
    }

def dyntext(title, content, targets, gridPos):
    return {"datasource": HA, "type": "marcusolsson-dynamictext-panel", "id": nid(),
            "title": title, "gridPos": gridPos,
            "options": {"content": content, "defaultContent": "<em>no image</em>",
                        "editor": {"format": "auto", "language": "html"},
                        "renderMode": "everyRow", "wrap": True, "contentPartials": [],
                        "helpers": "", "styles": "", "externalStyles": []},
            "targets": targets}

def crow(title, ry, children, collapsed=True):
    for ch in children:
        ch["gridPos"]["y"] += ry + 1
    return {"type": "row", "id": nid(), "title": title, "collapsed": collapsed,
            "gridPos": {"h": 1, "w": 24, "x": 0, "y": ry}, "panels": children}

# ---- Topology extras: infra health beside the diagram
_WIN = 'instance=~"blueiris|plex01|server[1-3]|homer_simpson-hp-laptop"'  # windows_exporter
_LIN = 'instance=~"ubuntu01|dev-linux"'                           # node_exporter hosts
PCT = {"mode": "absolute", "steps": [
    {"color": "green", "value": None}, {"color": "yellow", "value": 75}, {"color": "red", "value": 90}]}

# fed straight off /api/states (GET). A stat panel renders all-string frames as
# "No data"; a table shows them fine.
_WAN_ENT = ["sensor.current_ip", "sensor.speedtest_download",
            "sensor.speedtest_upload", "sensor.speedtest_ping"]
_topo_wan = ha_table("Internet", "", [c("metric", "metric"), c("value", "value")],
    {"h": 4, "w": 24, "x": 0, "y": 0},
    target=inf('$filter($, function($v){ $v.entity_id in ['
               + ",".join('"%s"' % e for e in _WAN_ENT) + '] })',
               [c("attributes.friendly_name", "metric"), c("state", "value")]))

_topo_cpu = bargauge("Host CPU",
    f'100 - avg by (instance)(rate(windows_cpu_time_total{{{_WIN},mode="idle"}}[5m])) * 100'
    f' or 100 - avg by (instance)(rate(node_cpu_seconds_total{{{_LIN},mode="idle"}}[5m])) * 100',
    "{{instance}}", {"h": 9, "w": 8, "x": 0, "y": 4}, unit="percent")
_topo_cpu["fieldConfig"]["defaults"]["thresholds"] = PCT
_topo_ram = bargauge("Host RAM",
    f'sum by (instance)((1 - windows_os_physical_memory_free_bytes{{{_WIN}}} / on(instance) windows_cs_physical_memory_bytes) * 100)'
    f' or sum by (instance)((1 - node_memory_MemAvailable_bytes{{{_LIN}}} / node_memory_MemTotal_bytes) * 100)',
    "{{instance}}", {"h": 9, "w": 8, "x": 8, "y": 4}, unit="percent")
_topo_ram["fieldConfig"]["defaults"]["thresholds"] = PCT
_topo_disk = bargauge("Host Disk",
    f'(1 - sum by (instance)(windows_logical_disk_free_bytes{{{_WIN}}}) / sum by (instance)(windows_logical_disk_size_bytes{{{_WIN}}})) * 100'
    f' or max by (instance)((1 - node_filesystem_avail_bytes{{{_LIN},mountpoint="/"}} / node_filesystem_size_bytes{{{_LIN},mountpoint="/"}}) * 100)',
    "{{instance}}", {"h": 9, "w": 8, "x": 16, "y": 4}, unit="percent")
_topo_disk["fieldConfig"]["defaults"]["thresholds"] = PCT

_topo_apc = bargauge("Wi-Fi Clients per AP",
    'unifi_device_stations{type="uap",name!~"Not in Use.*"}', "{{name}}",
    {"h": 8, "w": 8, "x": 0, "y": 13}, unit="short", mn=0, mx=40)
_topo_apc["fieldConfig"]["defaults"]["thresholds"] = {"mode": "absolute", "steps": [
    {"color": "green", "value": None}, {"color": "yellow", "value": 25}, {"color": "orange", "value": 35}]}
_topo_air = bargauge("AP Channel Utilisation",
    'unifi_device_radio_channel_utilization_total_ratio{name!~"Not in Use.*",band=~"2.4|5"} * 100',
    "{{name}} {{band}}GHz", {"h": 8, "w": 8, "x": 8, "y": 13}, unit="percent")
_topo_air["fieldConfig"]["defaults"]["thresholds"] = PCT
_topo_certs = bargauge("Cert Expiry",
    '(min by (instance)(probe_ssl_earliest_cert_expiry{instance=~"ha_external|nginx_external|grafana"}) - time()) / 86400',
    "{{instance}}", {"h": 8, "w": 8, "x": 16, "y": 13}, unit="d", mn=0, mx=90)
_topo_certs["fieldConfig"]["defaults"]["thresholds"] = {"mode": "absolute", "steps": [
    {"color": "red", "value": None}, {"color": "orange", "value": 7}, {"color": "yellow", "value": 14}, {"color": "green", "value": 21}]}

_topo_containers = stat("Containers Running",
    'count(group by (name)(container_last_seen{name!=""}))',
    {"h": 4, "w": 6, "x": 0, "y": 21}, unit="none", text="value", legend="running",
    colormode="value", thresholds=[{"color": "green", "value": None}])
_topo_adg = {
    "datasource": MIMIR, "type": "stat", "id": nid(), "title": "AdGuard",
    "gridPos": {"h": 4, "w": 18, "x": 6, "y": 21},
    "fieldConfig": {"defaults": {"thresholds": {"mode": "absolute", "steps": [{"color": "blue", "value": None}]}},
        "overrides": [
            {"matcher": {"id": "byFrameRefID", "options": "C"}, "properties": [{"id": "unit", "value": "percent"}]},
            {"matcher": {"id": "byFrameRefID", "options": "D"}, "properties": [{"id": "unit", "value": "ms"}]}]},
    "options": {"colorMode": "value", "graphMode": "none", "textMode": "value_and_name",
                "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}},
    "targets": [t('adguard_num_dns_queries', "DNS Queries", "A", instant=True),
                t('adguard_num_blocked_filtering', "Blocked", "B", instant=True),
                t('100 * adguard_num_blocked_filtering / adguard_num_dns_queries', "Blocked %", "C", instant=True),
                t('adguard_avg_processing_time * 1000', "Avg Processing", "D", instant=True)],
}

_STATS_PANELS = [_topo_wan, _topo_cpu, _topo_ram, _topo_disk, _topo_apc, _topo_air,
                 _topo_certs, _topo_containers, _topo_adg]
_DIAGRAM_PANELS = [_net_panel]

# Standalone "Topology" dashboard (uid ha-topology) - what the Home Assistant
# UI "Topology" view embeds as one kiosk iframe. Diagram + cameras only; the
# infra stats live on the main "Home Assistant" dashboard. Deep-copied BEFORE
# the crow() call below mutates the originals for the main dashboard.
_ANN = [
    {"builtIn": 1, "datasource": {"type": "grafana", "uid": "-- Grafana --"}, "enable": True,
     "hide": True, "name": "Annotations & Alerts", "type": "dashboard"},
    # One region annotation per deploy (time + timeEnd, posted once at the end
    # covering the whole deploy span) rather than separate Started/Finished
    # point markers - see the pipelines' "Post Deploy Timespan Annotation" step.
    {"datasource": {"type": "grafana", "uid": "-- Grafana --"}, "enable": True, "hide": False,
     "iconColor": "#73BF69", "name": "Deploy", "tags": ["Deploy"], "type": "tags"},
]
topology_dashboard = {
    # no deploy-tag annotations here - the diagram is instant data and the
    # annotation toggles just eat vertical space in the embedded kiosk view.
    "annotations": {"list": [_ANN[0]]}, "editable": True, "graphTooltip": 1, "id": None, "links": [],
    "panels": copy.deepcopy(_DIAGRAM_PANELS), "preload": False, "refresh": "1m", "schemaVersion": 39,
    "tags": ["home-assistant", "topology"], "templating": {"list": []},
    "time": {"from": "now-3h", "to": "now"}, "timepicker": {}, "timezone": "browser",
    "title": "Topology", "uid": "ha-topology", "weekStart": "",
}

# Two collapsed rows at the very top: infra stats first, then the diagram.
panels.insert(0, crow("Topology", 1, _DIAGRAM_PANELS, collapsed=True))
panels.insert(0, crow("Stats", 0, _STATS_PANELS, collapsed=True))

ONOFF = [{"type": "value", "options": {
    "0": {"text": "OFF", "color": "dark-red"}, "1": {"text": "ON", "color": "green"}}}]
OC = [{"type": "value", "options": {
    "0": {"text": "Closed", "color": "green"}, "1": {"text": "OPEN", "color": "orange"}}}]
LOCK = [{"type": "value", "options": {
    "0": {"text": "🔓 Unlocked", "color": "orange"}, "1": {"text": "🔒 Locked", "color": "green"}}}]

# ================================================================= curated rows
def rx(lst):
    return "|".join(lst)

# lights + switches/sockets exposed on the HA "Home" Lovelace views (physical
# devices only - camera PTZ, TV-IR, motion-automation toggles and Wi-Fi blocks
# are left out).
SW = ["car_charger_socket_1", "christmas_lights_front_socket_1", "disco_ball_socket_1",
      "door_number_light_socket", "front_lights_switch_1", "front_lights_switch_2",
      "garden_lights_and_sound", "garden_tree_and_path_switch_1", "garden_tree_and_path_switch_2",
      "heating_boost", "lisa_simpson_fairy_lights_socket_1", "marge_simpson_electric_blanket_socket",
      "kitchen_counter_socket_1", "patio_lights_socket_1", "patio_switch_1", "patio_switch_2",
      "shed_light_socket_1", "smart_plug_2_socket_1", "smart_plug_3_socket_1", "smart_plug_4_socket_1",
      "smart_plug_5_socket_1", "smart_plug_6_socket_1", "smart_socket_5_socket",
      "smoke_machine_socket_1", "tree_house_light_socket"]
LIGHT = ["bedroom_lamp", "lisa_simpson_dimmer_switch_light_1", "master_bedroom_dimmer_switch_light_1",
         "kitchen_island_plinth", "kitchen_plinths", "kitchen_sink_plinth", "kitchen_tall_units_plinth",
         "kitchen_under_stair_units_plinth", "kitchen_wall_units", "utility_units"]
AC_ROOMS = ["bart_simpson_room", "lisa_simpson_room", "kitchen", "master_bedroom", "office", "upstairs"]
P2S = "sensor.p2s_22e8bj620203679"

def gauge(title, expr, legend, gridPos, unit="celsius", mn=0, mx=100, steps=None, instant=True):
    return {
        "datasource": MIMIR, "type": "gauge", "id": nid(), "title": title, "gridPos": gridPos,
        "fieldConfig": {"defaults": {
            "unit": unit, "min": mn, "max": mx,
            "thresholds": {"mode": "absolute", "steps": steps or [{"color": "blue", "value": None}]}},
            "overrides": []},
        "options": {"showThresholdLabels": False, "showThresholdMarkers": True,
                    "orientation": "auto",
                    "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": True}},
        "targets": [t(expr, legend, "A", instant=instant)],
    }

def ha_bargauge(title, root_selector, name_col, val_col, gridPos, unit="percent", mn=0, mx=100, steps=None):
    return {
        "datasource": HA, "type": "bargauge", "id": nid(), "title": title, "gridPos": gridPos,
        "fieldConfig": {"defaults": {"unit": unit, "min": mn, "max": mx,
            "thresholds": {"mode": "absolute", "steps": steps or BATTSTEPS}}, "overrides": []},
        "options": {"displayMode": "lcd", "orientation": "horizontal", "valueMode": "color",
                    "showUnfilled": True, "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": True}},
        "transformations": [{"id": "organize", "options": {"indexByName": {name_col: 0, val_col: 1}}}],
        "targets": [inf(root_selector, [c("attributes.friendly_name", name_col),
                                        c("state", val_col, "number")])],
    }

def ha_onoff_stat(title, domain, ids, gridPos):
    lst = ",".join(f'"{domain}.{e}"' for e in ids)
    return {
        "datasource": HA, "type": "stat", "id": nid(), "title": title, "gridPos": gridPos,
        "fieldConfig": {"defaults": {
            "mappings": [{"type": "value", "options": {
                "on": {"text": "ON", "color": "green", "index": 0},
                "off": {"text": "OFF", "color": "dark-red", "index": 1},
                "unavailable": {"text": "n/a", "color": "text", "index": 2}}}],
            "thresholds": {"mode": "absolute", "steps": [{"color": "text", "value": None}]}},
            "overrides": []},
        "options": {"colorMode": "background", "graphMode": "none", "justifyMode": "auto",
                    "orientation": "auto", "textMode": "value_and_name",
                    "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": True}},
        "transformations": [{"id": "organize", "options": {"indexByName": {"name": 0, "state": 1}}}],
        "targets": [inf(f'$filter($, function($v){{ $v.entity_id in [{lst}] }})',
                        [c("attributes.friendly_name", "name"), c("state", "state")])],
    }

# Infinity feeding a stat panel renders "No data" (all-string frame - see the
# _topo_wan note). Where a numeric Mimir series exists (switch state, light
# brightness>0), drive the ON/OFF tiles from Mimir instead so they actually show.
_ONOFF_NUM = [{"type": "value", "options": {
    "1": {"text": "ON", "color": "green", "index": 0},
    "0": {"text": "OFF", "color": "dark-red", "index": 1}}}]

def mimir_onoff_stat(title, expr, gridPos):
    return {
        "datasource": MIMIR, "type": "stat", "id": nid(), "title": title, "gridPos": gridPos,
        "fieldConfig": {"defaults": {
            "mappings": _ONOFF_NUM,
            "thresholds": {"mode": "absolute", "steps": [{"color": "text", "value": None}]}},
            "overrides": []},
        "options": {"colorMode": "background", "graphMode": "none", "justifyMode": "auto",
                    "orientation": "auto", "textMode": "value_and_name",
                    "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}},
        "targets": [t(expr, "{{friendly_name}}", "A", instant=True)],
    }

# ---- People & Presence
# One marker layer per person so each gets its own fixed colour and a clean
# name. Entity is the most reliable GPS source for each: google_maps / phone
# GPS / dog collar always carry coords; person.bart_simpson has no dedicated GPS device
# so Bart Simpson only appears when away (the person's source switches to a GPS tracker).
PEOPLE_MAP = [
    ("A", "device_tracker.google_maps_104199578859638696260", "Homer Simpson",   "blue"),
    ("B", "device_tracker.google_maps_146646711938998732988", "Marge Simpson",   "red"),
    ("C", "device_tracker.pixel_6_pro_lisa_simpson",               "Lisa Simpson", "purple"),
    ("D", "person.bart_simpson",                                       "Bart Simpson",    "orange"),
    ("E", "device_tracker.eleqqixh_dog",                   "Dog", "green"),
]

def _person_target(refId, eid):
    return inf(f'$filter($, function($v){{ $v.entity_id = "{eid}" and $exists($v.attributes.latitude) }})',
               [c("attributes.latitude", "latitude", "number"),
                c("attributes.longitude", "longitude", "number"),
                c("state", "state")], refId=refId)

def _person_layer(refId, name, color):
    return {
        "type": "markers", "name": name,
        "location": {"mode": "coords", "latitude": "latitude", "longitude": "longitude"},
        "filterData": {"id": "byRefId", "options": refId},
        "config": {"style": {
            "size": {"fixed": 11}, "color": {"fixed": color}, "opacity": 0.9,
            "symbol": {"fixed": "img/icons/marker/circle.svg", "mode": "fixed"},
            "text": {"fixed": name, "mode": "fixed", "fontSize": 11},
            "textConfig": {"fontSize": 11, "offsetY": -16, "textAlign": "center",
                           "textBaseline": "middle"}},
            "showLegend": True},
        "tooltip": True,
    }

_geo = {
    "datasource": HA, "type": "geomap", "id": nid(), "title": "Where is everyone",
    "gridPos": {"h": 11, "w": 14, "x": 0, "y": 0},
    "fieldConfig": {"defaults": {}, "overrides": []},
    "options": {
        # fit to whoever is on the map (needs allLayers). maxZoom caps the
        # everyone's-home cluster at ~village level; falls back to a fixed
        # zoom-14 home view if fit can't compute an extent.
        "view": {"id": "fit", "allLayers": True, "padding": 20, "maxZoom": 14,
                 "lat": 39.7817, "lon": -89.6501, "zoom": 14},
        # Grafana's "default" basemap now resolves to CARTO, which serves an
        # "API KEY REQUIRED" tile without a key. osm-standard needs no key.
        "basemap": {"type": "osm-standard", "name": "Open Street Map"},
        "layers": [_person_layer(r, n, col) for r, _e, n, col in PEOPLE_MAP],
        "controls": {"showZoom": True, "mouseWheelZoom": True, "showAttribution": True},
        "tooltip": {"mode": "details"},
    },
    "targets": [_person_target(r, e) for r, e, _n, _col in PEOPLE_MAP],
}
_presence = ha_table("Presence",
    f'$filter($, function($v){{ {dom("person")} and $v.entity_id != "person.homer_simpson" }})',
    [c("attributes.friendly_name", "Person"), c("state", "Location"),
     c("last_changed", "Since", "timestamp")],
    {"h": 11, "w": 10, "x": 14, "y": 0})
_batt = {
    "datasource": MIMIR, "type": "gauge", "id": nid(), "title": "Batteries",
    "gridPos": {"h": 6, "w": 24, "x": 0, "y": 11},
    "fieldConfig": {"defaults": {"unit": "percent", "min": 0, "max": 100,
        "thresholds": {"mode": "absolute", "steps": BATTSTEPS}}, "overrides": []},
    "options": {"showThresholdLabels": False, "showThresholdMarkers": True, "orientation": "auto",
                "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}},
    "targets": batt_targets(),
}
panels.append(crow("People & Presence", y, [_geo, _presence, _batt])); y += 1

# ---- Media Players
_media = ha_table("Now Playing",
    f'$filter($, function($v){{ {dom("media_player")} and $v.state != "unavailable" and $v.state != "off" and $v.state != "standby" }})',
    [c("attributes.friendly_name", "Player"), c("state", "State"),
     c("attributes.media_title", "Title"), c("attributes.media_artist", "Artist"),
     c("attributes.app_name", "App"), c("attributes.volume_level", "Volume", "number")],
    {"h": 9, "w": 24, "x": 0, "y": 0})
panels.append(crow("Media Players", y, [_media])); y += 1

# ---- Lighting (curated). HA prometheus has no light on/off metric, but an off
# light still reports homeassistant_light_brightness_percent as 0, so ">bool 0"
# is a clean on/off. Switches have a real homeassistant_switch_state (0/1).
_li = mimir_onoff_stat("Lights",
    f'homeassistant_light_brightness_percent{{entity=~"light.({rx(LIGHT)})"}} > bool 0',
    {"h": 6, "w": 12, "x": 0, "y": 0})
_lb = bargauge("Brightness", f'homeassistant_light_brightness_percent{{entity=~"light.({rx(LIGHT)})"}}',
               "{{friendly_name}}", {"h": 6, "w": 12, "x": 12, "y": 0})
_sw = mimir_onoff_stat("Switches & Sockets",
    f'homeassistant_switch_state{{entity=~"switch.({rx(SW)})"}}',
    {"h": 12, "w": 24, "x": 0, "y": 6})
panels.append(crow("Lighting & Switches", y, [_li, _lb, _sw])); y += 1

# ---- Climate & AC
_cl = ha_table("Air Conditioning",
    f'$filter($, function($v){{ {dom("climate")} }})',
    [c("attributes.friendly_name", "Unit"), c("state", "Mode"),
     c("attributes.hvac_action", "Action"),
     c("attributes.current_temperature", "Current C", "number"),
     c("attributes.temperature", "Target C", "number"),
     c("attributes.fan_mode", "Fan")],
    {"h": 9, "w": 14, "x": 0, "y": 0})
# AC cost sensors report in GBP; the £ sign mangles the metric name to _unit_u0xa3
_ac_cost = stat("AC Cost Today",
                f'homeassistant_sensor_unit_u0xa3{{entity=~"sensor.({rx(r + "_ac_cost_today" for r in AC_ROOMS)})"}}',
                {"h": 9, "w": 10, "x": 14, "y": 0}, unit="currencyGBP", text="value_and_name",
                colormode="value", thresholds=[{"color": "green", "value": None},
                                               {"color": "yellow", "value": 0.5}, {"color": "orange", "value": 1.5}])
_ac_temp = ts("Room vs Outside Temperature", [
    t('homeassistant_sensor_temperature_celsius{entity="sensor.outside_temperature"}', "Outside", "A"),
    t(f'homeassistant_sensor_temperature_celsius{{entity=~"sensor.({rx(r + "_room_temperature" for r in AC_ROOMS)})"}}',
      "{{friendly_name}}", "B"),
], {"h": 8, "w": 12, "x": 0, "y": 9}, unit="celsius", fill=0)
_ac_set = ts("Current vs Target (AC)", [
    t('homeassistant_climate_current_temperature_celsius', "{{friendly_name}} now", "A"),
    t('homeassistant_climate_target_temperature_celsius', "{{friendly_name}} set", "B"),
], {"h": 8, "w": 12, "x": 12, "y": 9}, unit="celsius", fill=0)
panels.append(crow("Climate & AC", y, [_cl, _ac_cost, _ac_temp, _ac_set])); y += 1

# ---- Energy & Cost
def sens(e):
    return f'homeassistant_sensor_state{{entity="{e}"}} or homeassistant_sensor_unit_gbp{{entity="{e}"}} or homeassistant_sensor_unit_kwh{{entity="{e}"}}'
_cost = {
    "datasource": MIMIR, "type": "stat", "id": nid(), "title": "Today so far",
    "gridPos": {"h": 5, "w": 24, "x": 0, "y": 0},
    "fieldConfig": {"defaults": {"unit": "currencyGBP",
        "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": None},
                       {"color": "yellow", "value": 3}, {"color": "orange", "value": 6}]}},
        "overrides": [
            {"matcher": {"id": "byFrameRefID", "options": "C"}, "properties": [
                {"id": "unit", "value": "none"}, {"id": "decimals", "value": 1}]},
            {"matcher": {"id": "byFrameRefID", "options": "D"}, "properties": [{"id": "unit", "value": "kwatth"}]}]},
    "options": {"colorMode": "value", "graphMode": "none", "textMode": "value_and_name",
                "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}},
    "targets": [t('homeassistant_sensor_unit_gbp{entity="sensor.elec_cost_day"}', "Electricity Cost Today", "A"),
                t('homeassistant_sensor_unit_gbp{entity="sensor.gas_cost_day"}', "Gas Cost Today", "B"),
                t('homeassistant_sensor_unit_p{entity="sensor.elec_price_now"}', "Elec Price (p/kWh)", "C"),
                t('homeassistant_sensor_energy_kwh{entity="sensor.gas_today"}', "Gas Used Today", "D")],
}
_pw = ts("Live Power", [
    t('homeassistant_sensor_power_w{entity=~"sensor.(electricity_power|smart_plug_[2-6]_power)"}', "{{friendly_name}}", "A"),
], {"h": 8, "w": 12, "x": 0, "y": 5}, unit="watt")
_dailyE = ts("Energy Today by Device", [
    t('homeassistant_sensor_energy_kwh{entity=~"sensor.[a-z0-9_]+_daily"}', "{{friendly_name}}", "A"),
], {"h": 8, "w": 12, "x": 12, "y": 5}, unit="kwatth", draw="bars", fill=60)
panels.append(crow("Energy & Cost", y, [_cost, _pw, _dailyE])); y += 1

# ---- Irrigation
_irr_valves = ha_table("Zones",
    '$filter($, function($v){ $v.entity_id in ["valve.wt_11w_zone_1","valve.wt_11w_zone_2","valve.wt_11w_zone_3","number.wt_11w_zone_1_duration","number.wt_11w_zone_2_duration","number.wt_11w_zone_3_duration"] })',
    [c("attributes.friendly_name", "Zone"), c("state", "State"),
     c("attributes.unit_of_measurement", "Unit")],
    {"h": 8, "w": 12, "x": 12, "y": 0})
_irr_sched = ha_table("Schedule",
    '$filter($, function($v){ $v.entity_id in ["input_boolean.irrigation_enabled","input_boolean.irrigation_rain_sensor_enabled","input_datetime.irrigation_start_time","input_number.irrigation_rain_threshold","sensor.home_homer_simpson_com_rain_intensity","automation.irrigation_daily_schedule"] })',
    [c("attributes.friendly_name", "Setting"), c("state", "State")],
    {"h": 8, "w": 12, "x": 12, "y": 8})
# zone polygons + colours mirror www/irrigation-map.js (600x380 image space -> %)
_GMAP = ("https://maps.googleapis.com/maps/api/staticmap?center=39.7817,-89.6501"
         "&zoom=19&size=600x380&maptype=satellite&key=#{google_maps_api_key}#")
_irr_map = {
    "datasource": HA, "type": "marcusolsson-dynamictext-panel", "id": nid(),
    "title": "Garden zones", "gridPos": {"h": 16, "w": 12, "x": 0, "y": 0},
    "options": {
        "renderMode": "everyRow", "wrap": True,
        "editor": {"format": "html", "language": "html"},
        "defaultContent": "waiting for valve states",
        "content": (
            f'<div style="position:relative;width:100%;line-height:0">'
            f'<img src="{_GMAP}" style="width:100%;border-radius:6px"/>'
            f'<div class="z z1 s-{{{{z1}}}}"></div><div class="z z2 s-{{{{z2}}}}"></div>'
            f'<div class="z z3 s-{{{{z3}}}}"></div>'
            f'<div class="zl zl1">Zone 1</div><div class="zl zl2">Zone 2</div>'
            f'<div class="zl zl3">Zone 3</div>'
            f'<div class="lg"><b style="color:#42a5f5">&#9632;</b> Z1 {{{{z1}}}} &nbsp; '
            f'<b style="color:#ef5350">&#9632;</b> Z2 {{{{z2}}}} &nbsp; '
            f'<b style="color:#ffee58">&#9632;</b> Z3 {{{{z3}}}}</div></div>'),
        "styles": (
            ".z{position:absolute;inset:0;transition:opacity .3s;mix-blend-mode:screen}"
            ".z1{background:#1e88e5;clip-path:polygon(71.7% 62.6%,92.7% 62.6%,93% 74.5%,71.3% 75.3%)}"
            ".z2{background:#e53935;clip-path:polygon(88.7% 56.6%,98.7% 56.6%,98.7% 63.2%,88.7% 63.2%)}"
            ".z3{background:#fdd835;clip-path:polygon(2.5% 25.8%,75% 49.5%,72.5% 63.2%,50.8% 66.3%,2.5% 37.4%)}"
            ".z.s-closed{opacity:.5}.z.s-open{opacity:1;mix-blend-mode:normal;box-shadow:0 0 0 2px #fff inset}"
            ".zl{position:absolute;transform:translate(-50%,-50%);font:700 12px system-ui;"
            "color:#fff;white-space:nowrap;pointer-events:none;letter-spacing:.02em;"
            "text-shadow:0 0 3px #000,0 0 4px #000,0 1px 2px #000}"
            ".zl1{left:82%;top:69%}.zl2{left:93%;top:60%}.zl3{left:34%;top:46%}"
            ".lg{position:absolute;left:6px;bottom:6px;font:600 11px system-ui;"
            "background:rgba(0,0,0,.65);color:#fff;padding:3px 7px;border-radius:4px;line-height:1.5}"),
    },
    "targets": [inf_template(
        "{{ {'z1': states('valve.wt_11w_zone_1'), 'z2': states('valve.wt_11w_zone_2'), "
        "'z3': states('valve.wt_11w_zone_3')} | tojson }}",
        [c("z1", "z1"), c("z2", "z2"), c("z3", "z3")])],
}
_irr_dur = bargauge("Zone Durations",
    'homeassistant_number_state_min{entity=~"number.wt_11w_zone_[1-3]_duration"}', "{{friendly_name}}",
    {"h": 5, "w": 12, "x": 0, "y": 16}, unit="m", mn=0, mx=30)
_irr_batt = gauge("Valve Controller Battery",
    'homeassistant_sensor_battery_percent{entity="sensor.wt_11w_battery_level"}', "Irrigation Valve",
    {"h": 5, "w": 12, "x": 12, "y": 16}, unit="percent", mn=0, mx=100, steps=BATTSTEPS)
# The prometheus exporter has no valve state metric, so per-zone run time comes
# from history_stats sensors (sensor.irrigation_zone_N_watering_today, hours) -
# see configuration.yaml. *60 -> minutes for a readable bar.
_irr_usage = bargauge("Watering Today",
    'label_replace('
    'homeassistant_sensor_state{entity=~"sensor.irrigation_zone_[1-3]_watering_today"} * 60,'
    ' "z", "Zone $1", "entity", "sensor.irrigation_zone_(.+)_watering_today")',
    "{{z}}", {"h": 6, "w": 24, "x": 0, "y": 21}, unit="m", mn=0, mx=15)
_irr_usage["fieldConfig"]["defaults"]["thresholds"] = {"mode": "absolute",
    "steps": [{"color": "blue", "value": None}]}
_irr_rain = ts("Rain Intensity", [
    t('homeassistant_sensor_precipitation_intensity_mm_per_h{entity="sensor.home_homer_simpson_com_rain_intensity"} '
      'or homeassistant_sensor_state{entity="sensor.home_homer_simpson_com_rain_intensity"}',
      "Rain", "A"),
    t('homeassistant_input_number_state_mm_per_h{entity="input_number.irrigation_rain_threshold"} '
      'or homeassistant_input_number_state{entity="input_number.irrigation_rain_threshold"}', "Skip threshold", "B"),
], {"h": 7, "w": 24, "x": 0, "y": 27}, unit="lengthmm", fill=20)
panels.append(crow("Irrigation", y, [_irr_map, _irr_valves, _irr_sched, _irr_dur, _irr_batt, _irr_usage, _irr_rain])); y += 1

# ---- Mower
M355 = "mower_355444099856651"
# No homeassistant_lawn_mower_state metric exists and Infinity->stat renders
# "No data", so this is a table (see the _topo_wan note).
_mow_stat = ha_table("Mower",
    '$filter($, function($v){ $v.entity_id = "lawn_mower.%s" })' % M355,
    [c("attributes.friendly_name", "Mower"), c("state", "Activity"),
     c("attributes.status", "Detail")],
    {"h": 5, "w": 10, "x": 14, "y": 0})
_mow_kv = ha_kv("Status", [
    ("Activity", f"states('lawn_mower.{M355}')"),
    ("State", f"states('sensor.{M355}')"),
    ("Detailed", f"state_attr('lawn_mower.{M355}','status')"),
    ("Connected", f"states('binary_sensor.{M355}_connection')"),
    ("Error", f"states('binary_sensor.{M355}_error')"),
    ("Connect expires", f"as_timestamp(states('sensor.{M355}_connect_expiration')) | timestamp_custom('%d %b %Y', true)"),
], {"h": 9, "w": 10, "x": 14, "y": 5})
_mow_img = dyntext("Mower Location",
    '<img style="width:100%;max-height:460px;object-fit:contain;border-radius:6px" src="https://home.example.com:8123{{entity_picture}}" />',
    [inf('$filter($, function($v){ $v.entity_id = "camera.maps_googleapis_com" })',
         [c("attributes.entity_picture", "entity_picture")])],
    {"h": 14, "w": 14, "x": 0, "y": 0})
panels.append(crow("Mower", y, [_mow_img, _mow_stat, _mow_kv])); y += 1

# ---- 3D Printer (Bambu Lab P2S)
_pr_cam = dyntext("Printer",
    '<img style="width:100%;max-height:280px;object-fit:contain;border-radius:6px" src="https://home.example.com:8123{{entity_picture}}" />',
    [inf('$filter($, function($v){ $v.entity_id = "image.p2s_22e8bj620203679_cover_image" })',
         [c("attributes.entity_picture", "entity_picture")])],
    {"h": 12, "w": 9, "x": 0, "y": 0})
_P = "p2s_22e8bj620203679"
_pr_status = ha_kv("Job", [
    ("Task", f"states('sensor.{_P}_task_name')"),
    ("Print status", f"states('sensor.{_P}_print_status')"),
    ("Stage", f"states('sensor.{_P}_current_stage')"),
    ("Remaining", f"states('sensor.{_P}_remaining_time')"),
    ("Ends", f"states('sensor.{_P}_end_time')"),
    ("Online", f"states('binary_sensor.{_P}_online')"),
    ("HMS errors", f"states('binary_sensor.{_P}_hms_errors')"),
], {"h": 12, "w": 7, "x": 9, "y": 0})
_pr_prog = bargauge("Print Progress", f'homeassistant_sensor_unit_percent{{entity="{P2S}_print_progress"}}',
                    "progress", {"h": 4, "w": 8, "x": 16, "y": 0})
_pr_noz = gauge("Nozzle", f'homeassistant_sensor_temperature_celsius{{entity="{P2S}_nozzle_temperature"}}',
                "nozzle", {"h": 8, "w": 3, "x": 16, "y": 4}, unit="celsius", mn=0, mx=300,
                steps=[{"color": "blue", "value": None}, {"color": "orange", "value": 200}, {"color": "red", "value": 280}])
_pr_bed = gauge("Bed", f'homeassistant_sensor_temperature_celsius{{entity="{P2S}_bed_temperature"}}',
                "bed", {"h": 8, "w": 3, "x": 19, "y": 4}, unit="celsius", mn=0, mx=120,
                steps=[{"color": "blue", "value": None}, {"color": "orange", "value": 80}, {"color": "red", "value": 110}])
_pr_ch = gauge("Chamber", f'homeassistant_sensor_temperature_celsius{{entity="{P2S}_chamber_temperature"}}',
               "chamber", {"h": 8, "w": 2, "x": 22, "y": 4}, unit="celsius", mn=0, mx=70)
_pr_temps = ts("Temperatures", [
    t(f'homeassistant_sensor_temperature_celsius{{entity=~"{P2S}_(nozzle|bed|chamber)_temperature"}}', "{{friendly_name}}", "A"),
], {"h": 7, "w": 12, "x": 0, "y": 12}, unit="celsius", fill=0)
_pr_ams = ha_kv("AMS & Fans", [
    ("AMS humidity %", f"states('sensor.{_P}_ams_1_humidity')"),
    ("AMS temperature", f"states('sensor.{_P}_ams_1_temperature') ~ ' C'"),
    ("AMS drying", f"states('binary_sensor.{_P}_ams_1_drying')"),
    ("Cooling fan %", f"states('sensor.{_P}_cooling_fan_speed')"),
    ("Chamber fan %", f"states('sensor.{_P}_chamber_fan_speed')"),
    ("Wi-Fi signal", f"states('sensor.{_P}_wi_fi_signal') ~ ' dBm'"),
    ("Total usage", f"states('sensor.{_P}_total_usage')"),
], {"h": 7, "w": 12, "x": 12, "y": 12})
panels.append(crow("3D Printer", y, [_pr_cam, _pr_status, _pr_prog, _pr_noz, _pr_bed, _pr_ch, _pr_temps, _pr_ams])); y += 1

# ---- Dogs (Dog)
_dog_batt = gauge("Dog Battery",
                  'homeassistant_sensor_battery_percent{entity="sensor.dog_battery_level"}',
                  "Dog", {"h": 6, "w": 6, "x": 0, "y": 0}, unit="percent", mn=0, mx=100,
                  steps=[{"color": "red", "value": None}, {"color": "orange", "value": 15}, {"color": "green", "value": 40}])
_dog_act = stat("Activity",
                'homeassistant_sensor_unit_min{entity=~"sensor.dog_(minutes_active|daily_goal|rest_time)"}',
                {"h": 6, "w": 12, "x": 6, "y": 0}, unit="m", text="value_and_name",
                colormode="value", thresholds=[{"color": "text", "value": None}])
_dog_state = ha_kv("Tracker", [
    ("Status", "states('sensor.dog_tracker_state')"),
    ("Charging", "states('binary_sensor.dog_tracker_battery_charging')"),
    ("Power saving", "states('binary_sensor.dog_tracker_power_saving')"),
    ("Live tracking", "states('switch.dog_live_tracking')"),
    ("Buzzer", "states('switch.dog_tracker_buzzer')"),
    ("LED", "states('switch.dog_tracker_led')"),
], {"h": 6, "w": 6, "x": 18, "y": 0})
# day/night sleep are once-a-day summary sensors - a stat row for "today" plus a
# 7-day history (pinned to now-7d so it ignores the dashboard's short window).
_dog_sleep_today = stat("Sleep Today",
    'homeassistant_sensor_unit_min{entity=~"sensor.dog_(day|night)_sleep"}',
    {"h": 3, "w": 24, "x": 0, "y": 6}, unit="m", text="value_and_name",
    colormode="value", thresholds=[{"color": "text", "value": None}])
_dog_sleep = ts("Sleep (7d)", [
    t('homeassistant_sensor_unit_min{entity="sensor.dog_day_sleep"}', "Day sleep", "A"),
    t('homeassistant_sensor_unit_min{entity="sensor.dog_night_sleep"}', "Night sleep", "B"),
], {"h": 8, "w": 24, "x": 0, "y": 9}, unit="m", draw="bars", fill=60)
_dog_sleep["timeFrom"] = "7d"
panels.append(crow("Dogs", y, [_dog_batt, _dog_act, _dog_state, _dog_sleep_today, _dog_sleep])); y += 1

# ---- Vacuums
# HA 2026.8 dropped the `battery_level` attribute from vacuum entities (base-class
# fallback removed entirely in 2026.9); ecovacs now exposes a dedicated
# `sensor.<robot>_battery`. A template joins that sensor back onto each robot so
# the Robots table keeps its Battery column.
_VAC_ROBOTS = [("Lounge", "lounge"), ("Hallway", "hallway")]
_vac_batt = ha_bargauge("Vacuum Battery",
    f'$filter($, function($v){{ $v.entity_id in {json.dumps([f"sensor.{s}_battery" for _, s in _VAC_ROBOTS])} }})',
    "Vacuum", "Battery", {"h": 4, "w": 12, "x": 0, "y": 0}, unit="percent")
_vac_cols = [c("Vacuum", "Vacuum"), c("State", "State"), c("Battery", "Battery", "number")]
_vac_rows = ",".join(
    "{'Vacuum': '%s', 'State': states('vacuum.%s'), 'Battery': states('sensor.%s_battery') | int(0)}" % (name, slug, slug)
    for name, slug in _VAC_ROBOTS)
_vac_state = ha_table("Robots", "", _vac_cols,
    {"h": 4, "w": 12, "x": 12, "y": 0},
    target=inf_template("{{ [" + _vac_rows + "] | tojson }}", _vac_cols))
_vac_life = ha_bargauge("Consumables Remaining",
    '$filter($, function($v){ $v.entity_id in ["sensor.hallway_filter_lifespan","sensor.hallway_main_brush_lifespan","sensor.hallway_side_brush_lifespan","sensor.lounge_filter_lifespan","sensor.lounge_main_brush_lifespan","sensor.lounge_side_brush_lifespan"] })',
    "Part", "Life", {"h": 7, "w": 12, "x": 0, "y": 4}, unit="percent")
_vac_area = ha_table("Cleaning",
    '$filter($, function($v){ $v.entity_id in ["sensor.hallway_area_cleaned","sensor.hallway_cleaning_duration","sensor.lounge_area_cleaned","sensor.lounge_cleaning_duration"] })',
    [c("attributes.friendly_name", "Item"), c("state", "State"),
     c("attributes.unit_of_measurement", "Unit")],
    {"h": 7, "w": 12, "x": 12, "y": 4})
_vac_m1 = dyntext("Lounge Map",
    '<img style="width:100%;max-height:220px;object-fit:contain" src="https://home.example.com:8123{{entity_picture}}" />',
    [inf('$filter($, function($v){ $v.entity_id = "image.lounge_map" })', [c("attributes.entity_picture", "entity_picture")])],
    {"h": 8, "w": 12, "x": 0, "y": 11})
_vac_m2 = dyntext("Hallway Map",
    '<img style="width:100%;max-height:220px;object-fit:contain" src="https://home.example.com:8123{{entity_picture}}" />',
    [inf('$filter($, function($v){ $v.entity_id = "image.hallway_map" })', [c("attributes.entity_picture", "entity_picture")])],
    {"h": 8, "w": 12, "x": 12, "y": 11})
panels.append(crow("Vacuums", y, [_vac_batt, _vac_state, _vac_life, _vac_area, _vac_m1, _vac_m2])); y += 1

# ---- Builds & Releases
# ha_kv (table), not ha_kv_stat - Infinity->stat renders "No data".
_bld_ver = ha_kv("Versions", [
    ("HA current", "states('sensor.current_version_2')"),
    ("HA latest", "states('sensor.ha_latest_version')"),
    ("Config build", "states('sensor.azure_devops_build_number')"),
    ("Docker build", "states('sensor.azure_devops_docker_build_number')"),
    ("Renovate PRs", "states('sensor.renovate_open_prs')"),
], {"h": 5, "w": 24, "x": 0, "y": 0})
_bld_kv = ha_kv("Latest Deploys", [
    ("Config build", "states('sensor.azure_devops_build_number')"),
    ("Config built", "states('sensor.azure_devops_date_of_build')"),
    ("Config commit", "states('sensor.azure_devops_commit_message')"),
    ("Docker build", "states('sensor.azure_devops_docker_build_number')"),
    ("Docker built", "states('sensor.azure_devops_docker_date_of_build')"),
    ("Docker commit", "states('sensor.azure_devops_docker_commit_message')"),
], {"h": 8, "w": 12, "x": 0, "y": 5})
_bld_timeline = annolist("Deploy Timeline", ["Deploy"], {"h": 8, "w": 12, "x": 12, "y": 5})
panels.append(crow("Builds & Releases", y, [_bld_ver, _bld_kv, _bld_timeline])); y += 1

# ---- Pixel Health
_pix = ha_table("Pixel 10 Pro & Watch",
    '$filter($, function($v){ ($substringBefore($v.entity_id, "pixel_10_pro") != $v.entity_id and $substringBefore($v.entity_id,".") = "sensor") or $v.entity_id = "sensor.oneplus_watch_battery_level" })',
    [c("attributes.friendly_name", "Metric"), c("state", "State"),
     c("attributes.unit_of_measurement", "Unit")],
    {"h": 10, "w": 12, "x": 0, "y": 0})
_pixg = ts("Steps & Heart Rate (7d)", [
    t('homeassistant_sensor_unit_steps{entity="sensor.pixel_10_pro_daily_steps"}', "Steps", "A"),
    t('homeassistant_sensor_unit_bpm{entity=~"sensor.pixel_10_pro_(heart_rate|resting_heart_rate)"}', "{{friendly_name}}", "B"),
], {"h": 10, "w": 12, "x": 12, "y": 0}, unit="short", fill=0)
panels.append(crow("Pixel Health", y, [_pix, _pixg])); y += 1

# ---- Bins: render the HA "Bins" view's Jinja via POST /api/template so it always matches
_bin_tmpl = (
    "{%- set anchor = as_timestamp(strptime('2026-06-08','%Y-%m-%d')) -%}"
    "{%- set secs = 604800 -%}"
    "{%- set dtm = (7 - now().weekday()) % 7 -%}"
    "{%- set first = (today_at() | as_timestamp) + dtm * 86400 -%}"
    "{%- set ns = namespace(items=[]) -%}"
    "{%- for i in range(13) -%}"
    "{%- set t = first + i * secs -%}"
    "{%- set w = ((t - anchor) / secs) | int -%}"
    "{%- set ns.items = ns.items + [{'Date': t | timestamp_custom('%a %d %b'), "
    "'Recycling': ('YES' if w % 2 == 0 else '-'), 'Garden': ('YES' if w % 2 == 0 else '-'), "
    "'Refuse': ('YES' if w % 3 == 0 else '-'), 'Food': 'YES'}] -%}"
    "{%- endfor -%}{{ ns.items | tojson }}")
_bin_cols = [c("Date", "Date"), c("Recycling", "\U0001F535 Recycling"),
             c("Garden", "\U0001F7E2 Garden"), c("Refuse", "⚫ Refuse"), c("Food", "\U0001F7E0 Food")]
_bins = ha_table("Upcoming Bin Collections", "", _bin_cols, {"h": 12, "w": 24, "x": 0, "y": 0},
                 target=inf_template(_bin_tmpl, _bin_cols))
panels.append(crow("Bins", y, [_bins])); y += 1


dashboard = {
    "annotations": {"list": [
        {"builtIn": 1, "datasource": {"type": "grafana", "uid": "-- Grafana --"},
         "enable": True, "hide": True, "iconColor": "rgba(0, 211, 255, 1)",
         "name": "Annotations & Alerts", "type": "dashboard"},
        # One region annotation per deploy (time + timeEnd, posted once at the
        # end covering the whole deploy span) rather than separate Started/
        # Finished point markers - see the pipelines' "Post Deploy Timespan
        # Annotation" step.
        {"datasource": {"type": "grafana", "uid": "-- Grafana --"}, "enable": True, "hide": False,
         "iconColor": "#73BF69", "limit": 100, "matchAny": False, "name": "Deploy",
         "tags": ["Deploy"], "type": "tags"},
        {"datasource": {"type": "grafana", "uid": "-- Grafana --"}, "enable": True, "hide": False,
         "iconColor": "#5794F2", "limit": 100, "matchAny": True, "name": "System Events",
         "tags": ["Reboot", "Service", "Server"], "type": "tags"},
    ]},
    "editable": True,
    "fiscalYearStartMonth": 0,
    "graphTooltip": 1,
    "id": None,
    "links": [],
    "panels": panels,
    "preload": False,
    "refresh": "1m",
    "schemaVersion": 39,
    "tags": ["home-assistant"],
    "templating": {"list": []},
    "time": {"from": "now-6h", "to": "now"},
    "timepicker": {},
    "timezone": "browser",
    "title": "Home Assistant",
    "uid": "oVTa8pdWk",
    "weekStart": "",
}

_here = os.path.dirname(os.path.abspath(__file__))
out = os.path.join(_here, "dashboards", "Home Assistant.json")
with open(out, "w", encoding="utf-8") as f:
    json.dump(dashboard, f, indent=2)
    f.write("\n")

topo_out = os.path.join(_here, "dashboards", "Topology.json")
with open(topo_out, "w", encoding="utf-8") as f:
    json.dump(topology_dashboard, f, indent=2)
    f.write("\n")

ids = [p["id"] for p in panels]
assert len(ids) == len(set(ids))
for p in panels:
    r = [x["refId"] for x in p.get("targets", [])]
    assert len(r) == len(set(r)), (p["title"], r)
print("wrote", out, "panels:", len(panels))
for p in panels:
    print(f"  {p['gridPos']}  {p.get('title')}")

# Best-effort: validate every diagram panel's mermaid content against the
# exact mermaid version jdbranham-diagram-panel bundles (8.8.0 - it predates
# per-subgraph `direction` and other things a browser preview would happily
# render but this plugin's parser rejects). See mermaid-validate/README or
# validate.js's header comment. Requires `npm install` once in
# grafanaDashboards/mermaid-validate/; silently skipped if that hasn't been
# done or node isn't on PATH - run it manually before trusting a diagram
# content change.
_validator = os.path.join(_here, "mermaid-validate", "validate.js")
if shutil.which("node") and os.path.isdir(os.path.join(_here, "mermaid-validate", "node_modules")):
    print("\n--- mermaid parse validation (mermaid 8.8.0) ---")
    r = subprocess.run(["node", _validator], cwd=os.path.dirname(_validator))
    if r.returncode != 0:
        raise SystemExit("mermaid-validate failed - fix the diagram content above before committing")
else:
    print("\n(skipped mermaid parse validation - run `npm install` in "
          "grafanaDashboards/mermaid-validate/ once, then rerun this script, "
          "to catch mermaid syntax errors the plugin's old bundled mermaid "
          "8.8.0 would reject)")
