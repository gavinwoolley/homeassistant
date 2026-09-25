"""
One-shot generator: scans the REAL ui-lovelace.yaml at the repo root for every
entity_id it references, and emits demo/generated/ YAML that defines a fake,
genuinely-stateful backing entity for each one, using the exact same
entity_id/domain as the real dashboard - so demo/ui-lovelace.yaml (a copy of
the real file, entity_ids untouched) just works against fake data.

Not run at HA startup - a dev-time tool. Re-run (`python demo/tools/generate_demo_entities.py`
from the repo root) and recommit demo/generated/ if the real dashboard's entity set changes.
"""
import collections
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_LOVELACE = REPO_ROOT / "ui-lovelace.yaml"
OUT = REPO_ROOT / "demo" / "generated"
OUT.mkdir(parents=True, exist_ok=True)

DOMAINS = [
    "light", "switch", "sensor", "binary_sensor", "climate", "media_player", "camera",
    "vacuum", "lawn_mower", "cover", "fan", "lock", "valve", "number", "input_boolean",
    "input_number", "input_select", "input_datetime", "person", "device_tracker",
    "script", "automation", "timer", "utility_meter", "alarm_control_panel",
    "water_heater", "humidifier", "group", "image_processing", "select", "button",
    "update", "todo", "remote", "weather", "image",
    # input_text/input_button - genuine pre-existing gap, not related to any
    # rename: confirmed live (2026-09-23) these were never in this list at
    # all, so input_text.tts_text/input_button.tts_cast (the real dashboard's
    # Media > Text To Speech card, ui-lovelace.yaml) have never had backing
    # entities in the demo, since this scan was first written.
    "input_text", "input_button",
]
# Not real entities - service-call strings the domain.object regex also matches.
BOGUS = {"light.turn_on", "light.turn_off", "switch.turn_off", "climate.turn_off", "remote.send_command"}

_pattern = re.compile(r"\b(" + "|".join(DOMAINS) + r")\.[a-z0-9_]+\b")
_text = REAL_LOVELACE.read_text(encoding="utf-8")
_by_domain = collections.defaultdict(set)
for _m in _pattern.finditer(_text):
    if _m.group(0) not in BOGUS:
        _by_domain[_m.group(1)].add(_m.group(0))
data = {d: sorted(v) for d, v in _by_domain.items()}

# Demo-only additions: not referenced anywhere in the real ui-lovelace.yaml
# (so the scan above never finds them), added directly into the scanned set
# so they flow through the same generic pipeline/TEXT_SENSORS mechanism as
# everything else:
#   sensor.bart_simpson_battery - the same "battery" keyword random 35-99% value
#   sensor.homer_simpson_battery/marge_simpson_battery/lisa_simpson_battery already get, filling
#   in the family battery-bar row's missing 4th slot (Bart has no
#   phone-battery sensor on the real dashboard - the kids' phones aren't
#   individually monitored there, but the demo's UI has a slot for him).
#   sensor.bart_simpson / sensor.dog - the "Exact Locations" list's missing
#   Bart/dog rows (TEXT_SENSORS entries below).
#   sensor.irrigation_zone_1/2/3_watering_today - real history_stats
#   sensors (grafanaDashboards/build_ha_dashboard.py's own comment: "from
#   history_stats sensors... hours"), feeding the Grafana dashboard's
#   Irrigation > Watering Today panel directly - never referenced by
#   ui-lovelace.yaml at all (history_stats has no HA dashboard card of its
#   own here), so this scan structurally could never find them regardless
#   of what else changed. Confirmed live (2026-09-23) as a silently-empty
#   panel with no amount of renaming ever fixing it, since the entities
#   themselves never existed in the demo at all.
#   sensor.home_homer_simpson_com_humidity - same structural gap: the
#   Climate & Environment > Humidity panel is the only thing that
#   references it, apparent_temperature/rain_intensity (siblings of this
#   same weather integration) happened to already be scanned via other
#   ui-lovelace.yaml cards but this one never was.
data.setdefault("sensor", [])
for _extra in (
    "sensor.bart_simpson_battery", "sensor.bart_simpson", "sensor.dog",
    "sensor.irrigation_zone_1_watering_today",
    "sensor.irrigation_zone_2_watering_today",
    "sensor.irrigation_zone_3_watering_today",
    "sensor.home_homer_simpson_com_humidity",
):
    if _extra not in data["sensor"]:
        data["sensor"].append(_extra)

# device_tracker.eleqqixh_dog: demo/configuration.yaml's person.dog
# hardcodes this as its one and only device_trackers: source (see the
# person: block there) - it used to be picked up by the scan above via
# demo/ui-lovelace.yaml's Locations-view map/badge cards, which all
# referenced it directly. Confirmed live (2026-09-17): once those cards were
# fixed to point at person.dog instead (the GM1-marker/stuck-tracker
# fix), the string "device_tracker.eleqqixh_dog" no longer appeared
# anywhere in the real ui-lovelace.yaml this scans, so this entity silently
# stopped being generated - person.dog's only source tracker never
# existed, leaving it permanently "unknown". Same fix shape as the
# sensor.bart_simpson_battery extras above: force it into the scanned set instead of
# relying on it still being mentioned somewhere.
data.setdefault("device_tracker", [])
if "device_tracker.eleqqixh_dog" not in data["device_tracker"]:
    data["device_tracker"].append("device_tracker.eleqqixh_dog")

# device_tracker.google_maps_104199578859638696260/_146646711938998732988:
# same gap as the dog tracker just above, for the same reason - these are
# Homer's/Marge's entries in FAMILY_EXTRA_TRACKER_WHO (grafanaDashboards/
# build_ha_dashboard.py's Family Map panel queries them directly, exactly
# like Lisa's device_tracker.pixel_6_pro_lisa_simpson does), but neither
# ui-lovelace.yaml (the HA dashboard) nor anything else scanned above ever
# mentions them, so they never made it into data["device_tracker"] and were
# never generated at all. Confirmed live (2026-09-24): the demo Grafana's
# Family Map / "Where is everyone" panels showed a JSONata "no results
# found" error and dropped Homer and Marge from the legend entirely, since
# their Infinity queries were hitting entity_ids that plain didn't exist in
# this HA instance.
for _extra in ("device_tracker.google_maps_104199578859638696260",
               "device_tracker.google_maps_146646711938998732988"):
    if _extra not in data["device_tracker"]:
        data["device_tracker"].append(_extra)

# script.heating_boost_on/_off: only ever referenced from switch.heating_boost's
# turn_on/turn_off, which live in configuration.yaml, not ui-lovelace.yaml -
# this scan only looks at the dashboard, so these two script ids would
# never make it into data["script"] on their own (same class of gap as the
# device_tracker one above), and SCRIPT_OVERRIDES below would have nothing
# to attach its real behaviour to.
data.setdefault("script", [])
for _extra in ("script.heating_boost_on", "script.heating_boost_off"):
    if _extra not in data["script"]:
        data["script"].append(_extra)
data["sensor"].sort()


# Real object_ids that themselves embed sensitive data (not just a name that
# needs a Simpsons swap - the id string itself, e.g. the lawn mower's real
# device serial baked directly into "mower_demo" by its
# integration). Applied to every generated entity's object_id so the real
# value never appears anywhere in demo/generated/ or on screen - unlike the
# NAME_MAP swap below, this has to change the id itself, so
# demo/ui-lovelace.yaml (otherwise an unmodified copy of the real dashboard)
# needs the same substitution applied to it directly wherever these ids
# appear, kept in sync by hand since that file isn't regenerated here.
OBJECT_ID_SANITIZE = [
    ("mower_demo", "mower_demo"),
    # Same PII class as the mower serial - the real internal LAN subnet
    # baked directly into the "Camera Response Times" ping sensors'
    # entity_ids (sensor.10_0_0_51_round_trip_time_average
    # etc). Confirmed live (2026-09-24): the public mirror's sanitizer DOES
    # catch the underscore-joined form here (internal_ip_entity_id ->
    # 10_0_0_<n>) in most places, but HA derives a template sensor's actual
    # entity_id from its `name:` field, not its `unique_id:` - and that
    # name is auto-titled from the object_id with underscores turned into
    # SPACES ("192 168 69 84 Round Trip Time Average"), which the
    # underscore-anchored redaction regex never matches. Real subnet
    # digits leaked into the published mirror's actual runtime entity
    # (title-cased, space-separated) even though every underscore-joined
    # reference to the same IP got redacted correctly - the two diverged,
    # which is why this panel showed "Entity not available" for entities
    # the dashboard could no longer find under either name. Fixing it here
    # (same as the mower serial) removes the real digits from every demo
    # file entirely, so no sanitizer regex - space- or underscore-based -
    # ever needs to catch them in the first place. Decoys are the exact
    # values publish/sanitize.py's own hash_sub already produces for these
    # real IPs (matching digits, matching salt), kept in sync by hand -
    # trailing "_" included in each match, not just the IP, since some of
    # these real IPs are literal prefixes of others (10_0_0_172 vs
    # 10_0_0_118) and a bare .replace() would otherwise corrupt the
    # longer one.
    ("10_0_0_92_", "10_0_0_92_"),
    ("10_0_0_118_", "10_0_0_118_"),
    ("10_0_0_240_", "10_0_0_240_"),
    ("10_0_0_172_", "10_0_0_172_"),
    ("10_0_0_247_", "10_0_0_247_"),
    ("10_0_0_58_", "10_0_0_58_"),
    ("10_0_0_132_", "10_0_0_132_"),
    ("10_0_0_120_", "10_0_0_120_"),
    ("10_0_0_51_", "10_0_0_51_"),
    ("10_0_0_228_", "10_0_0_228_"),
    ("10_0_0_68_", "10_0_0_68_"),
    ("10_0_0_60_", "10_0_0_60_"),
    # Blackbox-probe target hostnames and the weather integration's own
    # entity are named after the real domain ("camera11.homer_simpson.com",
    # "home.example.com") - confirmed live (2026-09-17): this baked the
    # real domain straight into entity_id/unique_id (and so into the
    # Developer Tools states list, the API, and anywhere the id string is
    # shown), not just a cosmetic name.
    #
    # Renamed 2026-09-23 from ("homer_simpson_com", "example_com") to just
    # "homer_simpson" -> "homer_simpson": the public mirror's sanitizer
    # doesn't actually treat this as a domain substitution when it shows up
    # entity-id-shaped (underscore-joined, no literal dots - the `domain:`
    # section's home.example.com -> home.example.com mapping requires
    # real dots, which an entity_id never has). It's caught by the `names:`
    # section's Homer Simpson -> Homer Simpson rule instead (same one that
    # redacts the surname everywhere else it's glued into an identifier),
    # slugified per exact_pass's own lowercase-match handling. Confirmed
    # live (2026-09-23): the real sanitized dashboard queries
    # sensor.home_homer_simpson_com_rain_intensity /
    # ..._humidity, not ..._example_com_... - same silent-empty-panel
    # pattern as the whole Homer Simpson/Dog/Bart Simpson/Lisa Simpson rename, just for this
    # one compound identifier. "_com" is kept as a literal trailing
    # fragment either way (never part of what's redacted), so this rename
    # alone reproduces the exact same output the domain-based version used
    # to for the "_com" suffix, just with the correct prefix now.
    ("homer_simpson", "homer_simpson"),
    # Family/pet nicknames - the same PII class as the mower serial above,
    # just spelled as a household nickname instead of a device id. The
    # public mirror's sanitizer (replacements.local.yaml's `names:` section)
    # already redacts these inside the real dashboard's entity_id text too
    # (Homer Simpson -> Homer Simpson, Dog -> Dog, ...), not just display text -
    # confirmed live (2026-09-22) the sanitized Grafana dashboard queries
    # person.homer_simpson/sensor.dog_minutes_active/etc, while this demo's
    # own entities stayed on the real names (person.homer_simpson/sensor.dog_*),
    # so every panel keyed on a family member or the dog silently returned no
    # data - Family Map, Who's Home, People & Presence, the Dogs row, and the
    # two kids' room-prefixed climate/camera/cost sensors (Bart Simpson's Room, Lisa Simpson's
    # Room use the same real-nickname-as-room-name convention). Renaming here
    # also stops the demo's own committed config (previously
    # demo/configuration.yaml, customize.yaml, ui-lovelace.yaml) from shipping
    # the real nicknames unredacted - a separate, independent exposure from
    # the dashboard-query mismatch. Same "kept in sync by hand in
    # ui-lovelace.yaml" caveat as above.
    ("homer_simpson", "homer_simpson"),
    ("marge_simpson", "marge_simpson"),
    ("bart_simpson", "bart_simpson"),
    ("lisa_simpson", "lisa_simpson"),
    ("dog", "dog"),
]


def obj_id(entity_id):
    o = entity_id.split(".", 1)[1]
    for old, new in OBJECT_ID_SANITIZE:
        o = o.replace(old, new)
    return o


# Cosmetic-only, and NEVER used for anything that drives entity_id - see
# CUSTOMIZE below for why that distinction is load-bearing.
#
# Homer Simpson/Marge Simpson/Bart Simpson/Lisa Simpson/Dog are NOT here - unlike everyone below,
# those 5 are core household identities the real dashboard also keys
# entity_ids on directly (person.homer_simpson, sensor.dog_minutes_active,
# sensor.bart_simpson_room_*, ...), and the public mirror's sanitizer redacts them
# inside that entity_id text too, not just display text (see
# OBJECT_ID_SANITIZE above). A cosmetic-only swap here would leave the demo's
# own entities on the real names while the sanitized Grafana dashboard
# queries the decoy names - permanently empty panels. They're renamed at the
# object_id level instead (OBJECT_ID_SANITIZE), which makes their `real`
# title from title() already equal what simpsons_title() would have
# produced, so register_name() naturally emits no customize.yaml override
# for them - nothing left for NAME_MAP to do.
NAME_MAP = {
    "Homer Simpson": "Homer", "Marge Simpson": "Marge",
    "Patty Bouvier": "Patty", "Comic Book Guy": "Comic Book Guy", "Barney Gumble": "Barney",
    "Ned Flanders": "Ned", "Abraham Simpson": "Grampa", "Mona Simpson": "Mona",
    "Abraham Simpson": "Grampa", "Mona Simpson": "Mona",
}

# Media players get model/serial-shaped real names (chromecast1049,
# googlehome8636, lenovosmartdisplay80739, ...) that mean nothing to a demo
# visitor - NAME_MAP's generic word-swap can't fix this (none of those words
# are in it), so a dedicated per-device override, applied as a
# customize.yaml friendly_name the same way register_name() does for
# everything else (real object_id/entity_id untouched, only the *display*
# changes). Keeps each device's assigned room consistent with what it
# actually is - a "_speaker"/"googlehome"/"nestaudio" object_id only ever
# gets an audio-flavoured room name, never a room name implying a screen,
# since demo_media_player classifies come-alive content (show/movie vs.
# song+artist) from the real object_id's shape, not this display name -
# see custom_components/demo_media_player's _VIDEO_HINTS.
# Confirmed live (2026-09-17): the object_id itself is not a reliable guide
# to which room a device is actually in - the real scripts.yaml/
# automations.yaml (execute_cast_dropdown / the TTS cast script) reveal the
# REAL room each media_player is actually used in via their own
# is_state(cast_dropdown, "<room>") chains, and several are outright
# misleading: "dogs_speaker" is really the Kitchen speaker, "lounge_speaker"
# is really Garden Audio, "nestaudio8600" is really the Lounge speaker,
# "lounge_assistant" is really an Upstairs Bedroom speaker, "kitchen_speaker_2"
# is really the Bathroom speaker. Built from that real mapping, not guessed
# from the object_id text - see execute_cast_dropdown in scripts.yaml and
# the TTS cast automation in automations.yaml for the source of truth.
# A few entities that script doesn't cover (lisa_simpson_roku_tv, lounge_roku_tv,
# bedroom_speaker, kitchen_speaker_3) aren't misleadingly named, so kept as
# their object_id already implies.
MEDIA_PLAYER_ROOM_NAMES = {
    "chromecast1049": "Lounge Chromecast",
    "chromecast6664": "Bart's Room TV",
    "chromecast7681": "Master Bedroom TV",
    "lenovosmartdisplay80739": "Master Bedroom Display",
    "lenovosmartdisplay81380": "Kitchen Display",
    "dogs_speaker": "Kitchen Speaker",
    "googlehome2510": "Lisa's Room Speaker",
    "googlehome6669": "Garden Speaker",
    "lounge_speaker": "Garden Audio",
    "nestaudio8600": "Lounge Speaker",
    "googlehome8636": "Bart's Room Speaker",
    "lounge_assistant": "Upstairs Bedroom Speaker",
    "kitchen_speaker_2": "Bathroom Speaker",
    "googlehome3553": "Utility Speaker",
    "lisa_simpson_roku_tv": "Lisa's Room TV",
    "lounge_roku_tv": "Lounge TV",
    "bedroom_speaker": "Master Bedroom Speaker",
    "kitchen_speaker_3": "Office Speaker",
}

# object_id -> the customize.yaml friendly_name override needed for it, for
# every entity whose real title differs from its Simpsons one (populated by
# register_name() below). Written out to demo/customize.yaml at the end.
CUSTOMIZE = {}

# entity_id -> entity_picture override (real Simpsons character art the repo
# owner supplied into demo/www/ - see OTHER_PEOPLE_AVATARS below). Separate
# from CUSTOMIZE since not every customized entity has a picture and not
# every pictured entity needs a name override.
CUSTOMIZE_PICTURE = {}


def _format_words(object_id):
    words = object_id.replace("_", " ").split()
    small = {"a", "an", "the", "of", "in", "on", "to", "and"}
    out = []
    for i, w in enumerate(words):
        if w.isdigit() or (w.isalnum() and any(c.isdigit() for c in w) and any(c.isalpha() for c in w)):
            out.append(w.upper() if len(w) <= 4 else w)
        elif w.lower() in small and i != 0:
            out.append(w.lower())
        else:
            out.append(w.capitalize())
    return out


def title(object_id):
    """The REAL title (no Simpsons swap) - safe to feed into any entity's
    own `name:` field. HA derives entity_id from `name:` at first creation
    (confirmed live: person's `id:` field only sets unique_id, not
    entity_id - the swapped title "Bart Room..." for object_id
    "bart_simpson_room..." produced entity_id sensor.bart_room..., not
    sensor.bart_simpson_room... that the real dashboard actually references, and
    the entity registry then remembers that wrong entity_id forever, across
    every future restart, regardless of what the YAML says afterwards).
    Cosmetic swapping happens only as a customize.yaml override, applied on
    top of the real entity_id - see register_name().
    """
    return " ".join(_format_words(object_id))


def simpsons_title(object_id):
    """Cosmetic-only Simpsons-swapped title - never pass this as an
    entity's own `name:`, only into a customize.yaml friendly_name."""
    return " ".join(NAME_MAP.get(w, w) for w in _format_words(object_id))


def register_name(entity_id, object_id):
    """The real title for object_id, plus - if it differs - a queued
    customize.yaml override so the entity still *displays* the Simpsons
    name without entity_id ever depending on the swap. Use this (not
    title() directly) for anything that creates a new HA entity."""
    real = title(object_id)
    cosmetic = simpsons_title(object_id)
    if cosmetic != real:
        CUSTOMIZE[entity_id] = cosmetic
    return real


def yq(s):
    """Quote a string safely for single-line YAML."""
    s = str(s)
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def jinja_list(items):
    """A Jinja list literal, single-quoted items - for embedding inside a
    double-quoted YAML string (json.dumps' double quotes would collide with
    that outer wrapper; single-quoted Jinja string literals never need
    escaping here since none of these items contain an apostrophe)."""
    return "[" + ",".join(f"'{i}'" for i in items) + "]"


LINES_CFG = []      # extra top-level config file fragments needing separate !include (input_boolean/number/select/datetime/timer/button-less)
LINES_TEMPLATE = []  # content under template: (list items)

# ---------------------------------------------------------------------------
# helpers: plain HA helper domains (input_boolean/number/select/datetime/timer/text/button)
# ---------------------------------------------------------------------------
input_boolean_block = {}   # key -> dict
input_number_block = {}
input_select_block = {}
input_datetime_block = {}
timer_block = {}
input_text_block = {}
input_button_block = {}


def backing_bool(name, icon="mdi:toggle-switch", initial=False):
    input_boolean_block[name] = {"name": title(name), "icon": icon, "initial": initial}
    return f"input_boolean.{name}"


def backing_number(name, minv, maxv, step, unit=None, initial=None):
    d = {"name": title(name), "min": minv, "max": maxv, "step": step}
    if unit:
        d["unit_of_measurement"] = unit
    if initial is not None:
        d["initial"] = initial
    input_number_block[name] = d
    return f"input_number.{name}"


def backing_select(name, options, initial=None):
    input_select_block[name] = {"name": title(name), "options": options, "initial": initial or options[0]}
    return f"input_select.{name}"


# ---------------------------------------------------------------------------
# SENSOR + BINARY_SENSOR -> one big trigger-based template block, refreshed
# every 60s, heuristic fake values by name pattern.
# ---------------------------------------------------------------------------
def sensor_state_and_unit(oid):
    n = oid.lower()
    if "round_trip_time" in n:
        return "{{ (5 + range(0, 55) | random) }}", "ms", None
    if "battery" in n:
        return "{{ (35 + range(0, 65) | random) }}", "%", "battery"
    if n.endswith("_temp") or "temperature" in n:
        return "{{ (16 + range(0, 9) | random) }}", "\u00b0C", "temperature"
    if "humidity" in n:
        return "{{ (35 + range(0, 35) | random) }}", "%", "humidity"
    if "signal" in n or "rssi" in n:
        return "{{ (-80 + range(0, 40) | random) }}", "dBm", "signal_strength"
    # active_alerts/_critical/_warning/_info are TEXT_SENSORS entries (see
    # DEMO_ALERTS_JINJA below) - counted from a real `alerts` list attribute
    # instead of an independent random number, so the count sensors and the
    # Alerts page's actual list agree with each other.
    if "steps" in n:
        return "{{ (1500 + range(0, 9000) | random) }}", "steps", None
    if "heart_rate" in n:
        return "{{ (55 + range(0, 45) | random) }}", "bpm", None
    if "distance" in n:
        return "{{ (range(0, 100) | random / 10) }}", "km", "distance"
    if "watering_today" in n:
        # unit/device_class both None deliberately - the dashboard queries
        # this one via the bare homeassistant_sensor_state metric (no
        # unit/class suffix at all), matching how a real history_stats
        # sensor (which HA's own history_stats integration creates without
        # a unit_of_measurement) would actually export. Setting either
        # produces a homeassistant_sensor_h/_duration_h metric instead,
        # confirmed live to leave the real query matching nothing. Value
        # still a realistic 0-1 (hours, what the real dashboard's `* 60`
        # multiplies into minutes), just without a unit label attached.
        return "{{ (range(0, 100) | random / 100) }}", None, None
    if "calories" in n:
        return "{{ (300 + range(0, 2200) | random) }}", "kcal", None
    if "sleep" in n and "duration" in n:
        return "{{ (300 + range(0, 240) | random) }}", "min", None
    # The dog's own activity/sleep/goal sensors - checked before the "sleep"
    # (needs "duration" too, these don't have it) and "_daily_" (dog_daily_goal
    # false-matched that branch pre-rename, giving it kWh/energy instead of
    # minutes - confirmed live via the Prometheus dump these fell through to
    # the generic no-unit default, so the real dashboard's Activity/Sleep
    # panels (homeassistant_sensor_unit_min{entity=~"sensor.dog_..."}) never
    # got the unit-suffixed metric to query at all) checks below.
    if n in ("dog_minutes_active", "dog_daily_goal", "dog_rest_time", "dog_day_sleep", "dog_night_sleep"):
        return "{{ (range(0, 100) | random) }}", "min", None
    if "power" in n and "saving" not in n:
        return "{{ (range(0, 2400) | random) }}", "W", "power"
    if "energy" in n or n.endswith("_daily") or "_daily_" in n:
        return "{{ (range(0, 400) | random / 10) }}", "kWh", "energy"
    # device_class None on every cost/price/rate/charge branch below is
    # deliberate, not an oversight - confirmed live (2026-09-23) HA's
    # Prometheus integration names a numeric sensor's metric
    # homeassistant_sensor_<device_class>_<unit> when device_class is set
    # (e.g. "monetary_gbp"), and only homeassistant_sensor_unit_<unit>
    # (what every cost/price panel here actually queries) when it's left
    # unset - "monetary" on these produced homeassistant_sensor_monetary_gbp/
    # _monetary_u0xa3 instead, so Energy & Cost > Today so far and Climate &
    # AC > AC Cost Today silently matched nothing, pre-existing and
    # unrelated to any of this session's renames. Contrast gas_today below,
    # which the real dashboard queries as homeassistant_sensor_energy_kwh -
    # device_class "energy" there is correct and deliberately kept.
    #
    # Checked before the generic "cost" branch: production's real AC cost
    # sensors report unit_of_measurement "£" specifically (not "GBP" text,
    # unlike elec_cost_day/gas_cost_day) - grafanaDashboards/
    # build_ha_dashboard.py's own comment confirms this deliberately ("AC
    # cost sensors report in GBP; the £ sign mangles the metric name to
    # _unit_u0xa3").
    if "ac_cost_today" in n:
        return "{{ (range(0, 5000) | random / 100) }}", "£", None
    # Same wrong-unit class as ac_cost_today just above: production's real
    # elec_price_now reports in pence/kWh ("p", not "GBP" text) - the
    # dashboard's own column label confirms it ("Elec Price (p/kWh)").
    # gas_today falls through every branch above with no unit/device_class
    # at all (it's neither "energy"-named nor "_daily"-suffixed), so it
    # never got the kWh/energy device_class the dashboard's
    # homeassistant_sensor_energy_kwh query needs - device_class IS
    # correct/needed here, unlike the monetary ones (see comment above).
    if n == "elec_price_now":
        return "{{ (range(0, 4000) | random / 100) }}", "p", None
    if n == "gas_today":
        return "{{ (range(0, 100) | random) }}", "kWh", "energy"
    if "cost" in n:
        return "{{ (range(0, 5000) | random / 100) }}", "GBP", None
    if "price" in n or "rate" in n or "charge" in n:
        return "{{ (range(0, 4000) | random / 100) }}", "GBP", None
    if "progress" in n or "percent" in n:
        return "{{ (range(0, 100) | random) }}", "%", None
    if "lifespan" in n or "brush" in n:
        return "{{ (range(20, 100) | random) }}", "%", None
    if "cleaning_duration" in n:
        return "{{ (10 + range(0, 50) | random) }}", "min", None
    if "area_cleaned" in n:
        return "{{ (5 + range(0, 45) | random) }}", "m\u00b2", None
    if "wi_fi_signal" in n:
        return "{{ (-75 + range(0, 35) | random) }}", "dBm", None
    if "layer" in n and "total" not in n:
        return "{{ (range(0, 200) | random) }}", None, None
    if "total_layer_count" in n:
        return "\"250\"", None, None
    if "ip_address" in n or n == "current_ip":
        return '"10.42.0.{{ range(2, 250) | random }}"', None, None
    return "{{ (range(0, 100) | random) }}", None, None


TEXT_SENSORS = {
    # Real semantics: a Life360-style "current place" sensor, not the
    # person's own name - confirmed live: person.homer_simpson's state already
    # resolves to "home", "not_home", or the exact zone name ("Moe's
    # Tavern") depending on where family_presence_cycle has it right now,
    # since HA computes a GPS-based device_tracker's state that way
    # natively. Just needs "home"/"not_home" cleaned up into real words;
    # a named zone (e.g. "Moe's Tavern") already reads fine as-is.
    "homer_simpson": (
        "{% set s = states('person.homer_simpson') %}"
        "{{ 'Home' if s == 'home' else ('Away' if s == 'not_home' else s) }}",
        None,
    ),
    "marge_simpson": (
        "{% set s = states('person.marge_simpson') %}"
        "{{ 'Home' if s == 'home' else ('Away' if s == 'not_home' else s) }}",
        None,
    ),
    "lisa_simpson": (
        "{% set s = states('person.lisa_simpson') %}"
        "{{ 'Home' if s == 'home' else ('Away' if s == 'not_home' else s) }}",
        None,
    ),
    "bart_simpson": (
        "{% set s = states('person.bart_simpson') %}"
        "{{ 'Home' if s == 'home' else ('Away' if s == 'not_home' else s) }}",
        None,
    ),
    "dog": (
        "{% set s = states('person.dog') %}"
        "{{ 'Home' if s == 'home' else ('Away' if s == 'not_home' else s) }}",
        None,
    ),
    # Real semantics (configuration.yaml): "on" only while genuinely en
    # route and not yet home - drives the "Heading Home" map popup cards.
    # input_select.demo_homer_simpson_presence/demo_marge_simpson_presence is what
    # automations/family_presence.yaml actually drives - see below.
    "homer_simpson_towards_home": ("{{ 'on' if is_state('input_select.demo_homer_simpson_presence', 'heading_home') else 'off' }}", None),
    "marge_simpson_towards_home": ("{{ 'on' if is_state('input_select.demo_marge_simpson_presence', 'heading_home') else 'off' }}", None),
    "current_version_2": ("2026.9.1", None),
    "custom_date": ("{{ now().strftime('%A %d %B') }}", None),
    "ha_latest_version": ("2026.9.1", None),
    "last_boot": ("{{ (now() - timedelta(days=3)).isoformat() }}", "timestamp"),
    "azure_devops_build_number": ("{{ '1.0.' ~ (range(1,999) | random) }}", None),
    "azure_devops_docker_build_number": ("{{ '1.0.' ~ (range(1,999) | random) }}", None),
    "azure_devops_commit_message": ("Demo commit message", None),
    "azure_devops_docker_commit_message": ("Demo commit message", None),
    "azure_devops_date_of_build": ("{{ now().isoformat() }}", "timestamp"),
    "azure_devops_docker_date_of_build": ("{{ now().isoformat() }}", "timestamp"),
    "azure_devops_publish_to_github_build_number": ("{{ '1.0.' ~ (range(1,999) | random) }}", None),
    "azure_devops_publish_to_github_commit_message": ("Demo commit message", None),
    "azure_devops_publish_to_github_date_of_build": ("{{ now().isoformat() }}", "timestamp"),
    "lisa_simpson_last_sensor_update": ("{{ now().isoformat() }}", "timestamp"),
    # Driven by input_select.demo_printer_status (see printer_come_alive
    # automation below) rather than a fixed "idle" - the real dashboard's
    # "Print job running" card is conditional on this being
    # running/pause/prepare (see ui-lovelace.yaml), so a permanently-idle
    # value meant that card could never appear in the demo at all.
    "p2s_22e8bj620203679_print_status": ("{{ states('input_select.demo_printer_status') }}", None),
    "p2s_22e8bj620203679_current_stage": (
        "{% set s = states('input_select.demo_printer_status') %}"
        "{{ {'idle': 'Idle', 'prepare': 'Heating & Levelling', 'running': 'Printing', 'pause': 'Paused'}.get(s, 'Idle') }}",
        None,
    ),
    "p2s_22e8bj620203679_task_name": ("Demo Print Job", None),
    "p2s_22e8bj620203679_serial_number": ("DEMO0001", None),
    "p2s_22e8bj620203679_nozzle_type": ("Hardened Steel", None),
    "p2s_22e8bj620203679_print_bed_type": ("Textured PEI", None),
    "p2s_22e8bj620203679_mqtt_connection_mode": ("LAN", None),
    "p2s_22e8bj620203679_ip_address": ("10.42.0.50", None),
    "p2s_22e8bj620203679_start_time": ("{{ now().isoformat() }}", "timestamp"),
    "p2s_22e8bj620203679_end_time": ("{{ (now() + timedelta(hours=2)).isoformat() }}", "timestamp"),
    "p2s_22e8bj620203679_externalspool_external_spool": ("Off", None),
    "p2s_22e8bj620203679_nozzle_size": ("0.4mm", None),
    "outside_condition": ("{{ states('weather.home_homer_simpson_com') }}", None),
    "dog_tracker_state": ("At Home", None),
    "mower_demo": ("Docked", None),
    "mower_demo_connect_expiration": ("{{ (now() + timedelta(days=200)).isoformat() }}", "timestamp"),
    "renovate_open_prs": ("{{ range(0, 6) | random }}", None),
    "time": None,  # covered by time_date integration
    "moon": None,  # covered by moon integration
}


# These TEXT_SENSORS entries are a pure, deterministic function of another
# entity's current state (homer_simpson/marge_simpson/bart_simpson/dog of person.<who>, the
# towards_home pair of input_select.demo_<who>_presence) - nothing random,
# nothing that needs a timer. Putting them on the shared 2-minute trigger
# like everything else meant they could lag up to 2 minutes behind the
# person entity they're derived from - confirmed live: person.homer_simpson flipped
# to "home" instantly, but sensor.homer_simpson (the Exact Locations panel, and the
# same value the mushroom-person-card's secondary_info reads) kept showing
# "Moe's Tavern" for another 8 minutes until its next tick. Generating these
# into a reactive (non-triggered) block instead makes HA's own state-change
# tracking recompute them the instant their source entity changes.
REACTIVE_SENSOR_NAMES = {
    "homer_simpson", "marge_simpson", "lisa_simpson", "bart_simpson", "dog", "homer_simpson_towards_home", "marge_simpson_towards_home",
    "p2s_22e8bj620203679_print_status", "p2s_22e8bj620203679_current_stage",
}
# Same idea, but for binary_sensor - the conditional "Bins out tomorrow"
# cards need to disappear as soon as "Done" is picked, not up to 2 minutes
# later on the next global tick.
REACTIVE_BINARY_SENSOR_NAMES = {
    "recycling_bin_done", "waste_bin_done", "garden_waste_bin_done", "food_waste_bin_done",
}
# outside_condition deliberately NOT reactive, unlike the presence sensors
# above: confirmed live (2026-09-16) that as a non-triggered sensor whose
# template only calls states('weather.X'), it never actually recomputed
# after its first evaluation - weather.home_homer_simpson_com's own state
# changed (partlycloudy -> rainy) on its 2-minute trigger, but
# sensor.outside_condition stayed stuck on its initial value regardless.
# Simplest reliable fix: put it on the same 2-minute trigger block as the
# weather entity itself, so it updates in that same cycle instead of
# depending on template dependency-tracking behavior that didn't hold up
# here (unclear why homer_simpson/marge_simpson's person.* dependency tracking works but
# this weather.* one didn't - not worth the time to root-cause further for
# a passive background icon where a couple of minutes of lag is fine).

# The real configuration.yaml's sensor.outside_condition has its own icon:
# template mapping the weather entity's condition to a proper mdi icon
# (confirmed live, 2026-09-16, against the real dashboard - it was never
# actually broken there). The generic generator only produces a bare state
# with no icon logic, which state-icon falls back to a default "eye" glyph
# for - the demo's clock card looked broken while the real one never was.
# Reusing the exact same template text (including the real weather entity
# id) means this goes through the same redaction path as everything else
# instead of needing special-casing there too.
TEXT_SENSOR_ICONS = {
    "outside_condition": (
        "{% set s = states('weather.home_homer_simpson_com') %}"
        "{% set m = {"
        "'clear-night':'mdi:weather-night',"
        "'cloudy':'mdi:weather-cloudy',"
        "'fog':'mdi:weather-fog',"
        "'hail':'mdi:weather-hail',"
        "'lightning':'mdi:weather-lightning',"
        "'lightning-rainy':'mdi:weather-lightning-rainy',"
        "'partlycloudy':'mdi:weather-partly-cloudy',"
        "'pouring':'mdi:weather-pouring',"
        "'rainy':'mdi:weather-rainy',"
        "'snowy':'mdi:weather-snowy',"
        "'snowy-rainy':'mdi:weather-snowy-rainy',"
        "'sunny':'mdi:weather-sunny',"
        "'windy':'mdi:weather-windy',"
        "'windy-variant':'mdi:weather-windy-variant',"
        "'exceptional':'mdi:alert-circle-outline'"
        "} %}"
        "{{ m.get(s, 'mdi:weather-partly-cloudy') }}"
    ),
}

# The real ha-bambulab integration's AMS tray sensors carry color/remain/type
# attributes that demo/ui-lovelace.yaml's AMS panel reads directly
# (states[...].attributes.color, attribute: remain, attribute: type) - the
# generic per-entity random-state generator above has no way to know that,
# so these 4 came out with a bare numeric state and no attributes at all.
# Confirmed live: that's exactly what produced the amber warning-triangle
# icons (config-template-card's JS templating erroring on
# undefined.substring(...)) and "AMS Filament %: NaN" (mini-graph-card
# plotting a nonexistent `remain` attribute). Fixed colors per tray, matching
# each element's own fallback swatch color already hardcoded in
# ui-lovelace.yaml, so the 4 trays stay visually distinct instead of
# flickering to a random material color every 2 minutes.
# Confirmed live 2026-09-18: reported as "alerts firing but not listed" -
# sensor.active_alerts showed a random nonzero count, but the Alerts page's
# actual list (ui-lovelace.yaml's markdown card, `state_attr('sensor.
# active_alerts', 'alerts')`) had nothing to read - no `alerts` attribute
# was ever generated, so `or []` always won and the page said "No alerts
# firing" regardless of what the count said. A handful of fixed, plausible
# alertmanager-shaped entries instead - real Jinja list/dict literals (not
# JSON-dumped like every other list attribute below), since these need
# genuine now()-relative timestamps, which a static JSON blob can't produce.
# Two of the six are deliberately filtered OUT by the markdown card's own
# existing churn-filter logic (TargetDown+tier:transient, and Watchdog) -
# demonstrates that filter actually does something, rather than every entry
# always being visible.
_DEMO_ALERT_ENTRIES = [
    "{'state': 'firing', 'labels': {'alertname': 'NodeSwapFillingUp', 'severity': 'warning', 'job': 'windows', 'instance': 'SERVER2', 'tier': 'steady'}, 'annotations': {'summary': 'Swap usage has been above 80 percent for 15 minutes.', 'description': 'SERVER2 is under memory pressure - check for a runaway process before it starts paging heavily.'}, 'activeAt': (now() - timedelta(hours=2)).isoformat()}",
    "{'state': 'firing', 'labels': {'alertname': 'MimirIngesterDown', 'severity': 'critical', 'job': 'integrations/unix', 'instance': 'mimir-01', 'tier': 'steady'}, 'annotations': {'summary': 'A Mimir ingester has been unreachable for 5 minutes.', 'description': 'Metrics ingestion may be lossy until this recovers.'}, 'activeAt': (now() - timedelta(minutes=20)).isoformat()}",
    "{'state': 'firing', 'labels': {'alertname': 'CertificateExpiringSoon', 'severity': 'warning', 'job': 'blackbox', 'tier': 'steady'}, 'annotations': {'summary': 'TLS certificate for home.example.com expires in 6 days.', 'runbook_url': 'https://example.com/runbooks/cert-renew'}, 'activeAt': (now() - timedelta(days=1)).isoformat()}",
    "{'state': 'firing', 'labels': {'alertname': 'CertRenewalScheduled', 'severity': 'info', 'job': 'blackbox', 'tier': 'steady'}, 'annotations': {'summary': 'Automatic renewal is scheduled for this certificate.'}, 'activeAt': (now() - timedelta(days=1)).isoformat()}",
    "{'state': 'firing', 'labels': {'alertname': 'TargetDown', 'severity': 'warning', 'job': 'windows', 'instance': 'laptop', 'tier': 'transient'}, 'annotations': {'summary': 'Scrape target unreachable.'}, 'activeAt': (now() - timedelta(minutes=5)).isoformat()}",
    "{'state': 'firing', 'labels': {'alertname': 'Watchdog', 'severity': 'none', 'job': 'misc', 'tier': 'steady'}, 'annotations': {'summary': 'Dead mans switch - always firing while the alerting pipeline is healthy.'}, 'activeAt': (now() - timedelta(days=30)).isoformat()}",
]
DEMO_ALERTS_JINJA = "[" + ", ".join(_DEMO_ALERT_ENTRIES) + "]"

# Same churn-filter logic as the markdown card in ui-lovelace.yaml (state ==
# firing, alertname != Watchdog, not transient+TargetDown/WindowsHostRebooted)
# - kept in sync by hand since it's duplicated Jinja, not shared code; if
# that card's filter ever changes, update this too.
def _alerts_count_jinja(severity=None):
    sev_filter = f" and a.labels.severity == {yq(severity)}" if severity else ""
    return (
        "{% set alerts = state_attr('sensor.active_alerts', 'alerts') or [] %}"
        "{% set churn = ['TargetDown', 'WindowsHostRebooted'] %}"
        "{% set ns = namespace(n=0) %}"
        "{% for a in alerts %}"
        "{% if a.state == 'firing' and a.labels.alertname != 'Watchdog'"
        " and not (a.labels.get('tier') == 'transient' and a.labels.alertname in churn)"
        f"{sev_filter} %}}"
        "{% set ns.n = ns.n + 1 %}"
        "{% endif %}"
        "{% endfor %}"
        "{{ ns.n }}"
    )


TEXT_SENSORS.update({
    "active_alerts": (_alerts_count_jinja(), None),
    "active_alerts_critical": (_alerts_count_jinja("critical"), None),
    "active_alerts_warning": (_alerts_count_jinja("warning"), None),
    "active_alerts_info": (_alerts_count_jinja("info"), None),
})

SENSOR_ATTRIBUTES = {
    "active_alerts": {"alerts": "{{ " + DEMO_ALERTS_JINJA + " }}"},
    "p2s_22e8bj620203679_ams_1_tray_1": {"remain": "{{ range(0, 100) | random }}", "color": "#F5547CFF", "type": "PLA"},
    "p2s_22e8bj620203679_ams_1_tray_2": {"remain": "{{ range(0, 100) | random }}", "color": "#FEC600FF", "type": "PETG"},
    "p2s_22e8bj620203679_ams_1_tray_3": {"remain": "{{ range(0, 100) | random }}", "color": "#888888FF", "type": "ABS"},
    "p2s_22e8bj620203679_ams_1_tray_4": {"remain": "{{ range(0, 100) | random }}", "color": "#0086D6FF", "type": "TPU"},
    # The real Azure DevOps integration's "latest build" sensors carry
    # definition_name/finish_time/result attributes - the "Renovate Pipeline
    # Info" card reads all three directly (type: attribute cards), which a
    # bare random-number sensor doesn't have.
    "home_homeassistant_latest_build": {
        "definition_name": "HomeAssistant CI",
        "finish_time": "{{ (now() - timedelta(hours=3)).isoformat() }}",
        "result": "succeeded",
    },
    # Same shape as azure_pipeline_failure/running's `failed`/`running` list
    # attributes (BINARY_SENSOR_ATTRIBUTES below) - the markdown card loops
    # `state_attr('sensor.renovate_open_prs', 'prs')`, which throws on None.
    "renovate_open_prs": {"prs": []},
}


def _sensor_attributes_block(o):
    if o not in SENSOR_ATTRIBUTES:
        return ""
    block = "        attributes:\n"
    for attr_name, attr_value in SENSOR_ATTRIBUTES[o].items():
        if not isinstance(attr_value, str):
            # A list/dict attribute (e.g. Renovate's `prs`, matching the
            # empty-list convention BINARY_SENSOR_ATTRIBUTES already uses
            # for azure_pipeline_failure/running) - serialize as JSON inside
            # a Jinja template so it comes back as a real Python list, not a
            # string, for `{% for pr in state_attr(...) %}`-style templates.
            block += f'          {attr_name}: "{{{{ {json.dumps(attr_value)} }}}}"\n'
        elif "{{" in attr_value:
            block += f'          {attr_name}: "{attr_value}"\n'
        else:
            block += f"          {attr_name}: {yq(attr_value)}\n"
    return block


for oid in data.get("sensor", []):
    o = obj_id(oid)
    if o == "time" or o == "moon":
        continue
    if o in (
        "github_actions_latest_run",
        "demo_image_published_version",
        "demo_grafana_image_published_version",
        "github_actions_last_commit_message",
        "github_actions_last_run_status",
    ):
        # These are real platform: rest sensors hand-added directly to
        # demo/configuration.yaml's sensor: block (Task 5 Step 1), not
        # generated entities - the dashboard card referencing them (Task 5
        # Step 4) would otherwise make this generic scanner also generate
        # colliding random-value template fakes for the same entity_ids,
        # same class of bug already fixed for the binary_sensor loop above
        # (see the github_action_running/azure_devops_approval_pending
        # skip) - just never applied here. github_actions_last_commit_message
        # and github_actions_last_run_status aren't REST sensors like the
        # other three - they're hand-appended template sensors just below
        # (same fix as prod's configuration.yaml, replacing an invalid
        # `type: template` entities-card row) - still need the same skip,
        # since the card row referencing them is what the scanner picks up.
        continue
    name = register_name(f"sensor.{o}", o)
    if o in TEXT_SENSORS and TEXT_SENSORS[o] is not None:
        value, dclass = TEXT_SENSORS[o]
        entry = f'      - name: {yq(name)}\n        unique_id: demo_sn_{o}\n        state: >-\n          {value}\n'
        if dclass:
            entry += f"        device_class: {dclass}\n"
        if o in TEXT_SENSOR_ICONS:
            entry += f"        icon: >-\n          {TEXT_SENSOR_ICONS[o]}\n"
        entry += _sensor_attributes_block(o)
        domain_tag = "sensor_reactive" if o in REACTIVE_SENSOR_NAMES else "sensor"
        LINES_TEMPLATE.append((domain_tag, entry))
        continue
    expr, unit, dclass = sensor_state_and_unit(o)
    entry = f'      - name: {yq(name)}\n        unique_id: demo_sn_{o}\n        state: >-\n          {expr}\n'
    if unit:
        entry += f"        unit_of_measurement: {yq(unit)}\n"
    if dclass:
        entry += f"        device_class: {dclass}\n"
        if dclass in ("temperature", "humidity", "power", "energy", "signal_strength", "distance"):
            entry += "        state_class: measurement\n"
    entry += _sensor_attributes_block(o)
    LINES_TEMPLATE.append(("sensor", entry))

# ---------------------------------------------------------------------------
# WEATHER -> template weather entity. Not in the original DOMAINS list (an
# oversight - the template component does have weather.py, confirmed against
# the installed source), so weather.home_homer_simpson_com was never scanned
# for and the real dashboard's weather-forecast cards + "Weather Sensors"
# glance card permanently showed "Entity not found". condition/temperature
# reuse the same outside_condition/outside_temperature values the clock card
# already shows, so the two stay consistent with each other.
WEATHER_CONDITIONS_JINJA = "['sunny', 'partlycloudy', 'cloudy', 'rainy', 'clear-night', 'windy']"
FORECAST_DAILY_TEMPLATE = (
    "{% set conditions = " + WEATHER_CONDITIONS_JINJA + " %}\n"
    "          {% set base = states('sensor.outside_temperature') | float(18) %}\n"
    "          {% set ns = namespace(days=[]) %}\n"
    "          {% for i in range(5) %}\n"
    "          {% set ns.days = ns.days + [{\n"
    "            'datetime': (now() + timedelta(days=i)).strftime('%Y-%m-%d'),\n"
    "            'condition': conditions | random,\n"
    "            'native_temperature': base + (range(-2, 4) | random),\n"
    "            'native_templow': base - (range(2, 6) | random),\n"
    "          }] %}\n"
    "          {% endfor %}\n"
    "          {{ ns.days }}"
)
for oid in data.get("weather", []):
    o = obj_id(oid)
    name = register_name(f"weather.{o}", o)
    entry = (
        f'      - name: {yq(name)}\n'
        f'        unique_id: demo_wx_{o}\n'
        f'        condition: >-\n'
        f'          {{{{ {WEATHER_CONDITIONS_JINJA} | random }}}}\n'
        f'        temperature: "{{{{ states(\'sensor.outside_temperature\') | float(18) }}}}"\n'
        f'        humidity: "{{{{ range(55, 85) | random }}}}"\n'
        f'        forecast_daily: >-\n'
        f'          {FORECAST_DAILY_TEMPLATE}\n'
    )
    LINES_TEMPLATE.append(("weather", entry))

# ---------------------------------------------------------------------------
# IMAGE -> template image entity. Also missing from the original DOMAINS
# list (template.py has image.py too) - image.lounge_map/hallway_map (the
# vacuum cards' live floor-map thumbnails) and
# image.p2s_22e8bj620203679_cover_image (the 3D printer's job-cover photo)
# all showed "Entity not found" as a result. `url:` has to be a real
# fetchable URL (ImageEntity proxies the fetch itself, it can't just take a
# /local/ path like a picture card can) - looping back to the container's
# own HTTP server keeps this self-contained, no external dependency.
IMAGE_URLS = {
    "p2s_22e8bj620203679_cover_image": "http://127.0.0.1:8123/local/3d-print.jpg",
}
# Lounge Map/Hallway Map cards ("Vacuum Live Map") need an actual floor
# map, not the robot itself - vaccuum-transparent.jpg (a transparent-
# background render of the vacuum, correct for custom:vacuum-card's own
# `image:` thumbnail - see that card's own comment) was wired here by
# mistake earlier this session, so this card showed the robot graphic
# instead of a map. Requested directly (2026-09-24): swapped to
# vacuuum-map.jpg, a real static floor-map image.
for oid in data.get("image", []):
    o = obj_id(oid)
    name = register_name(f"image.{o}", o)
    url = IMAGE_URLS.get(o, "http://127.0.0.1:8123/local/images/vacuuum-map.jpg")
    entry = (
        f'      - name: {yq(name)}\n'
        f'        unique_id: demo_img_{o}\n'
        f'        url: {yq(url)}\n'
        f'        verify_ssl: false\n'
    )
    LINES_TEMPLATE.append(("image", entry))

BINARY_DCLASS = {
    "motion": "motion", "door": "door", "camera": None, "connection": "connectivity",
    "online": "connectivity", "firmware": None, "dns": "connectivity", "firewall": "connectivity",
    "switch": None, "tv": None, "active": None, "drying": None, "hms_errors": "problem",
    "error": "problem", "bin": None, "done": None, "ac_lite": None, "plex": "connectivity",
    "server": "connectivity", "watchdog": "problem", "bool": None,
}


def binary_dclass(oid):
    n = oid.lower()
    for key, dclass in BINARY_DCLASS.items():
        if key in n:
            return dclass
    return None


# The real dashboard's markdown cards iterate these two sensors' `failed`/
# `running` attributes as lists of pipeline dicts (the real Azure DevOps
# integration shapes them that way) - without a matching attribute here the
# `{% for p in state_attr(...) %}` in those cards throws (None isn't
# iterable). Empty list renders as "nothing running/failed", correct for a
# demo with no real pipelines.
BINARY_SENSOR_ATTRIBUTES = {
    "azure_pipeline_failure": ("failed", []),
    "azure_pipeline_running": ("running", []),
}

# These 4 aren't independent random state - the real ones are literally
# is_state(<matching input_select>, 'Done'), which is what makes the bin
# cards' "Mark when done" conditional actually clear itself once you pick
# "Done" from the select (see IB_SEL_DEFAULTS above for the matching
# options fix - without both halves, the card either never has a Done
# option, or has one that doesn't do anything).
BINARY_SENSOR_STATE_OVERRIDES = {
    "recycling_bin_done": "is_state('input_select.recycling_bin', 'Done')",
    "waste_bin_done": "is_state('input_select.waste_bin', 'Done')",
    "garden_waste_bin_done": "is_state('input_select.garden_waste_bin', 'Done')",
    "food_waste_bin_done": "is_state('input_select.food_waste_bin', 'Done')",
    # The "Bins out tomorrow" cards (ui-lovelace.yaml) are conditional on
    # BOTH sunday_bool AND the specific bin's own day-boolean being "on" at
    # once - real semantics are day-of-week-driven (collection day minus
    # one), which in a demo means these would independently need to land on
    # the same ~1-in-6 random tick together to ever be visible. Confirmed
    # live 2026-09-18: reported as "bins reminder not working" - it wasn't
    # broken, just so unlikely to be visible at once that nobody watching
    # for a few minutes would ever see it. Bumped to ~1-in-3 each so the
    # combined ~1-in-9 chance actually shows up within a normal demo
    # session, without making it permanently on (which would hide the
    # "only shows before collection day" behaviour entirely).
    "sunday_bool": "(range(0, 3) | random) == 0",
    "recycling_bin": "(range(0, 3) | random) == 0",
    "waste_bin": "(range(0, 3) | random) == 0",
    "garden_waste_bin": "(range(0, 3) | random) == 0",
}

for oid in data.get("binary_sensor", []):
    o = obj_id(oid)
    if o == "github_action_running" or o == "azure_devops_approval_pending":
        # Real dashboard's cards reference these (Task 4), so the generic
        # scan below would otherwise also generate random-state fakes for
        # them, colliding (same name + unique_id) with the real aggregating
        # entries hand-appended near the bottom of this file (same idea as
        # the sensor loop's "time"/"moon" skip above). The
        # azure_devops_approval_pending entry itself is hand-written by a
        # later task (its own demo-only fake), not this one - it's skipped
        # here pre-emptively so that task doesn't hit the same collision.
        continue
    name = register_name(f"binary_sensor.{o}", o)
    dclass = binary_dclass(o)
    state_expr = BINARY_SENSOR_STATE_OVERRIDES.get(o, "(range(0, 6) | random) == 0")
    entry = f'      - name: {yq(name)}\n        unique_id: demo_bs_{o}\n        state: >-\n          {{{{ {state_expr} }}}}\n'
    if dclass:
        entry += f"        device_class: {dclass}\n"
    if o in BINARY_SENSOR_ATTRIBUTES:
        attr_name, attr_value = BINARY_SENSOR_ATTRIBUTES[o]
        entry += f'        attributes:\n          {attr_name}: "{{{{ {json.dumps(attr_value)} }}}}"\n'
    domain_tag = "binary_sensor_reactive" if o in REACTIVE_BINARY_SENSOR_NAMES else "binary_sensor"
    LINES_TEMPLATE.append((domain_tag, entry))

# ---------------------------------------------------------------------------
# SWITCH / LIGHT -> template entity backed by a hidden input_boolean, exactly
# the pattern already used in the real configuration.yaml (state: is_state(...)).
# ---------------------------------------------------------------------------
STATE_TEMPLATE_ENTRIES = {"switch": [], "light": []}

LIVELY_SWITCHES = []  # every switch/light's backing input_boolean, for the "come alive" automation below

# heating_boost's real turn_on/turn_off call scripts, not a bare toggle
# (see SCRIPT_OVERRIDES' heating_boost_on/off) - state has to reflect the
# same input_boolean those scripts actually flip, not a throwaway backing
# boolean nothing else knows about, or the "Heating Boost Active"
# conditional card (gated on input_boolean.heating_boost) can never agree
# with the switch tile's own on/off state.
SWITCH_SCRIPT_BACKED = {
    "heating_boost": "input_boolean.heating_boost",
}

for domain in ("switch", "light"):
    for oid in data.get(domain, []):
        o = obj_id(oid)
        name = register_name(f"{domain}.{o}", o)
        if domain == "switch" and o in SWITCH_SCRIPT_BACKED:
            backing = SWITCH_SCRIPT_BACKED[o]
            entry = (
                f'      - name: {yq(name)}\n'
                f'        unique_id: demo_{domain[:2]}_{o}\n'
                f'        state: "{{{{ is_state(\'{backing}\', \'on\') }}}}"\n'
                f'        turn_on:\n'
                f'          - action: script.{o}_on\n'
                f'        turn_off:\n'
                f'          - action: script.{o}_off\n'
            )
            LINES_TEMPLATE.append((domain, entry))
            continue
        backing = backing_bool(f"demo_{'sw' if domain == 'switch' else 'lt'}_{o}")
        LIVELY_SWITCHES.append(backing)
        entry = (
            f'      - name: {yq(name)}\n'
            f'        unique_id: demo_{domain[:2]}_{o}\n'
            f'        state: "{{{{ is_state(\'{backing}\', \'on\') }}}}"\n'
            f'        turn_on:\n'
            f'          - action: input_boolean.turn_on\n'
            f'            target:\n'
            f'              entity_id: {backing}\n'
            f'        turn_off:\n'
            f'          - action: input_boolean.turn_off\n'
            f'            target:\n'
            f'              entity_id: {backing}\n'
        )
        LINES_TEMPLATE.append((domain, entry))

# ---------------------------------------------------------------------------
# VALVE -> no template/YAML backing exists in this HA version either (no
# valve.py under the template component, confirmed against the installed
# source, same as lawn_mower/media_player/remote) - custom_components/
# demo_valve provides one real, toggleable entity per irrigation zone
# instead, same pattern as demo_lawn_mower.
# ---------------------------------------------------------------------------
LINES_VALVE = []
for oid in data.get("valve", []):
    o = obj_id(oid)
    name = register_name(f"valve.{o}", o)
    LINES_VALVE.append(
        f'    - name: {yq(name)}\n'
        f'      object_id: {yq(o)}\n'
    )

# ---------------------------------------------------------------------------
# NUMBER -> template number backed by input_number.
# ---------------------------------------------------------------------------
for oid in data.get("number", []):
    o = obj_id(oid)
    name = register_name(f"number.{o}", o)
    backing = backing_number(f"demo_num_{o}", 0, 60, 1, unit="min", initial=15)
    entry = (
        f'      - name: {yq(name)}\n'
        f'        unique_id: demo_num_{o}\n'
        f'        state: "{{{{ states(\'{backing}\') }}}}"\n'
        f'        set_value:\n'
        f'          - action: input_number.set_value\n'
        f'            target:\n'
        f'              entity_id: {backing}\n'
        f'            data:\n'
        f'              value: "{{{{ value }}}}"\n'
        f'        min: 0\n'
        f'        max: 60\n'
        f'        step: 1\n'
        f'        unit_of_measurement: min\n'
    )
    LINES_TEMPLATE.append(("number", entry))

# ---------------------------------------------------------------------------
# SELECT (real select. domain) -> template select backed by input_select.
# ---------------------------------------------------------------------------
GENERIC_OPTIONS = ["Off", "Warm White", "Cool White", "Party"]
for oid in data.get("select", []):
    o = obj_id(oid)
    name = register_name(f"select.{o}", o)
    opts = GENERIC_OPTIONS
    if "channel" in o:
        opts = [str(i) for i in range(1, 11)]
    backing = backing_select(f"demo_sel_{o}", opts)
    opts_yaml = ", ".join(yq(op) for op in opts)
    entry = (
        f'      - name: {yq(name)}\n'
        f'        unique_id: demo_sel_{o}\n'
        f'        state: "{{{{ states(\'{backing}\') }}}}"\n'
        f"        options: '{{{{ [{opts_yaml}] }}}}'\n"
        f'        select_option:\n'
        f'          - action: input_select.select_option\n'
        f'            target:\n'
        f'              entity_id: {backing}\n'
        f'            data:\n'
        f'              option: "{{{{ option }}}}"\n'
    )
    LINES_TEMPLATE.append(("select", entry))

# ---------------------------------------------------------------------------
# BUTTON -> template button, no backing store needed.
# ---------------------------------------------------------------------------
for oid in data.get("button", []):
    o = obj_id(oid)
    name = register_name(f"button.{o}", o)
    entry = (
        f'      - name: {yq(name)}\n'
        f'        unique_id: demo_btn_{o}\n'
        f'        press:\n'
        f'          - action: logbook.log\n'
        f'            data:\n'
        f'              name: {yq(name)}\n'
        f'              message: pressed (demo)\n'
    )
    LINES_TEMPLATE.append(("button", entry))

# ---------------------------------------------------------------------------
# CLIMATE -> NOT template (this HA version's template integration has no
# climate.py at all - confirmed against the installed source, so a
# `template: - climate:` block is silently invalid config, not just a
# schema nitpick). generic_thermostat is a real, fully-supported climate
# integration instead: a template switch stands in for the "heater", a
# template sensor (added to the shared sensor block above) stands in for
# the temperature sensor, and generic_thermostat computes hvac_action/mode
# itself from those two - genuinely real climate behavior, not faked.
# ---------------------------------------------------------------------------
LINES_GENERIC_THERMOSTAT = []
LIVELY_CLIMATE = []  # every AC/thermostat entity_id, for the "come alive" automation below
for oid in data.get("climate", []):
    o = obj_id(oid)
    LIVELY_CLIMATE.append(f"climate.{o}")
    name = register_name(f"climate.{o}", o)
    heater = backing_bool(f"demo_cl_{o}_heater")
    # A template sensor here would have the exact same name-derives-entity_id
    # problem register_name() exists to avoid, except worse - there'd be no
    # real entity_id to register it AS, since nothing outside this file ever
    # needs to address it by name. input_number sidesteps the whole question:
    # its entity_id is the dict key, not derived from anything - genuinely
    # deterministic, so target_sensor below is guaranteed to resolve.
    sensor_entity = backing_number(f"demo_cl_{o}_currenttemp", 10, 28, 0.5, unit="\u00b0C", initial=19.5)
    LINES_GENERIC_THERMOSTAT.append(
        f'  - platform: generic_thermostat\n'
        f'    name: {yq(name)}\n'
        f'    unique_id: demo_cl_{o}\n'
        f'    heater: {heater}\n'
        f'    target_sensor: {sensor_entity}\n'
        f'    min_temp: 10\n'
        f'    max_temp: 28\n'
        f'    target_temp: 20\n'
        f'    initial_hvac_mode: "heat"\n'
    )

# ---------------------------------------------------------------------------
# MEDIA_PLAYER / REMOTE -> no template/YAML backing exists for either domain
# in this HA version (no media_player.py/remote.py under the template
# component - confirmed against the installed source, same as lawn_mower).
# Unlike valve (genuinely dropped - see below), these have real dashboard
# cards (TV remotes, Roku players) that need to actually work, not just
# degrade gracefully - custom_components/demo_media_player and
# custom_components/demo_remote are tiny, purpose-built platforms providing
# one real, toggleable entity each, same pattern as demo_lawn_mower.
# ---------------------------------------------------------------------------
LINES_MEDIA_PLAYER = []
LIVELY_MEDIA_PLAYERS = []  # individual (non-group) players, for the "come alive" automation below
for oid in data.get("media_player", []):
    o = obj_id(oid)
    name = register_name(f"media_player.{o}", o)
    if o in MEDIA_PLAYER_ROOM_NAMES:
        CUSTOMIZE[f"media_player.{o}"] = MEDIA_PLAYER_ROOM_NAMES[o]
    LINES_MEDIA_PLAYER.append(
        f'    - name: {yq(name)}\n'
        f'      object_id: {yq(o)}\n'
    )
    # Groups (home_group, downstairs_group, ...) aggregate the individual
    # players below rather than being independent devices, and
    # doorbell_group is a chime/announcement target, not a general playback
    # source - none of those make sense picking their own random "now
    # playing" content.
    if not o.endswith("_group"):
        LIVELY_MEDIA_PLAYERS.append(f"media_player.{o}")

LINES_REMOTE = []
for oid in data.get("remote", []):
    o = obj_id(oid)
    name = register_name(f"remote.{o}", o)
    LINES_REMOTE.append(
        f'    - name: {yq(name)}\n'
        f'      object_id: {yq(o)}\n'
    )

# ---------------------------------------------------------------------------
# VACUUM -> template, backed by input_select(state). No battery_level field
# in this version's template vacuum schema (confirmed against the installed
# source) - state only.
# ---------------------------------------------------------------------------
for oid in data.get("vacuum", []):
    o = obj_id(oid)
    name = register_name(f"vacuum.{o}", o)
    state_sel = backing_select(f"demo_vac_{o}_state", ["docked", "cleaning", "returning", "idle"], initial="docked")
    entry = (
        f'      - name: {yq(name)}\n'
        f'        unique_id: demo_vac_{o}\n'
        f'        state: "{{{{ states(\'{state_sel}\') }}}}"\n'
        f'        start:\n'
        f'          - action: input_select.select_option\n'
        f'            target: {{entity_id: {state_sel}}}\n'
        f'            data: {{option: cleaning}}\n'
        f'        stop:\n'
        f'          - action: input_select.select_option\n'
        f'            target: {{entity_id: {state_sel}}}\n'
        f'            data: {{option: idle}}\n'
        f'        return_to_base:\n'
        f'          - action: input_select.select_option\n'
        f'            target: {{entity_id: {state_sel}}}\n'
        f'            data: {{option: returning}}\n'
    )
    LINES_TEMPLATE.append(("vacuum", entry))

# ---------------------------------------------------------------------------
# CAMERA -> NOT YAML-configurable at all in this HA version. local_file's
# manifest.json declares "config_flow": true with no legacy platform
# fallback - confirmed live: HA rejects `camera: - platform: local_file`
# outright ("does not support platform setup, please remove it from your
# config"). There's no template.py for camera either. The only way to
# create these is driving the config_entries API, which needs a running,
# authenticated instance - can't happen at file-generation time. Emits a
# JSON map instead (object_id -> matched source image, one per real
# location, not a cycling/arbitrary assignment) for
# demo/tools/setup_demo_cameras.py to drive after onboarding.
CAMERA_IMAGES = {
    "bart_simpson_room_camera": "bart_room_camera.jpg",
    "bart_simpson_room_last_motion": "bart_room_last_motion.jpg",
    "boot_room_boot_room_doorbell": "BootRoom.jpg",
    "dogs_camera": "dogs_camera.jpg",
    "dogs_last_motion": "dogs_last_motion.jpg",
    "front_camera": "front_camera.jpg",
    "front_door": "FrontDoor.jpg",
    "front_last_motion": "front_last_motion.jpg",
    "garden_shed_lower": "garden_shed_lower.jpg",
    "garden_shed_lower_camera": "garden_shed_lower_camera.jpg",
    "garden_shed_lower_last_motion": "garden_shed_lower_last_motion.jpg",
    "garden_shed_upper_camera": "garden_shed_upper_camera.jpg",
    "garden_shed_upper_last_motion": "garden_shed_upper_last_motion.jpg",
    "garden_upper_camera": "garden_upper_camera.jpg",
    "garden_upper_last_motion": "garden_upper_last_motion.jpg",
    "maps_googleapis_com": "mower-satellite.png",
    "p2s_22e8bj620203679_camera": "3d-print.jpg",
    "patio_last_motion": "patio_last_motion.jpg",
    "patio_outdoor_camera": "patio_outdoor_camera.jpg",
}
CAMERA_MAP = {}
for oid in data.get("camera", []):
    o = obj_id(oid)
    # register_name() still gets called (queues the customize.yaml override
    # for the cosmetic Simpsons title shown on screen) but its *return value*
    # isn't kept here - cameras.json is published as part of the public
    # mirror, and local_file's config flow needs the REAL title to suggest
    # the matching entity_id (same rule as every other domain), which would
    # leak a real name (e.g. "Bart Simpson Room Camera") straight into a committed,
    # public file. demo/tools/setup_demo_cameras.py re-derives that real
    # title itself, from the object_id alone, purely to pass to the config
    # flow - it's never written to disk anywhere.
    register_name(f"camera.{o}", o)
    img = CAMERA_IMAGES.get(o, "Lounge.jpg")
    CAMERA_MAP[o] = {"source_image": img}

# ---------------------------------------------------------------------------
# INPUT_BOOLEAN / INPUT_NUMBER / INPUT_SELECT / INPUT_DATETIME / TIMER that
# are THEMSELVES referenced directly by the dashboard (not backing helpers).
# ---------------------------------------------------------------------------
for oid in data.get("input_boolean", []):
    o = obj_id(oid)
    input_boolean_block[o] = {"name": title(o), "icon": "mdi:toggle-switch-outline"}

IB_NUM_DEFAULTS = {
    "heating_boost_minutes": (0, 120, 5, "min", 30),
    "irrigation_rain_threshold": (0, 25, 0.5, "mm", 3),
    "irrigation_zone1_duration": (0, 60, 1, "min", 15),
    "irrigation_zone2_duration": (0, 60, 1, "min", 15),
    "irrigation_zone3_duration": (0, 60, 1, "min", 15),
    "media_volume_select": (0, 100, 1, "%", 35),
}
for oid in data.get("input_number", []):
    o = obj_id(oid)
    minv, maxv, step, unit, initial = IB_NUM_DEFAULTS.get(o, (0, 100, 1, None, 0))
    d = {"name": title(o), "min": minv, "max": maxv, "step": step, "initial": initial}
    if unit:
        d["unit_of_measurement"] = unit
    input_number_block[o] = d

# The 4 bin selects' real options aren't days of the week - they're just
# [bin type, "Done"] (confirmed against the real configuration.yaml). The
# matching *_bin_done binary_sensors below key off is_state(..., 'Done') on
# these exact selects, so getting the option text right is what makes
# "mark when done" actually work rather than just showing a day picker.
IB_SEL_DEFAULTS = {
    "alert_mute_duration": ["15 min", "1 hour", "4 hours", "Until tomorrow"],
    "camera_dropdown": [title(obj_id(o)) for o in data.get("camera", [])],
    "cast_to_media_player_dropdown": [
        MEDIA_PLAYER_ROOM_NAMES.get(obj_id(o), title(obj_id(o))) for o in data.get("media_player", [])
    ],
    "cast_to_screen_dropdown": [
        MEDIA_PLAYER_ROOM_NAMES.get(obj_id(o), title(obj_id(o))) for o in data.get("media_player", [])
    ],
    "food_waste_bin": ["Food Waste", "Done"],
    "garden_waste_bin": ["Garden Waste", "Done"],
    "kids_block_duration": ["30 min", "1 hour", "2 hours", "Rest of day"],
    "plinth_default_audio_effect": ["Warm White", "Cool White", "Reactive"],
    "recycling_bin": ["Recycling Bin", "Done"],
    "tts_voice_dropdown": ["Default", "Marge", "Homer"],
    "utility_units_default_audio_effect": ["Warm White", "Cool White", "Reactive"],
    "wall_units_default_audio_effect": ["Warm White", "Cool White", "Reactive"],
    "waste_bin": ["Refuse Bin", "Done"],
}
for oid in data.get("input_select", []):
    o = obj_id(oid)
    opts = IB_SEL_DEFAULTS.get(o) or ["Option 1", "Option 2"]
    opts = opts if opts else ["Option 1", "Option 2"]
    input_select_block[o] = {"name": title(o), "options": opts, "initial": opts[0]}

IB_DT_DEFAULTS = {
    "irrigation_start_time": {"has_time": True},
    "motion_alert_evening_condition_time": {"has_time": True},
    "motion_alert_morning_condition_time": {"has_time": True},
}
for oid in data.get("input_datetime", []):
    o = obj_id(oid)
    d = {"name": title(o)}
    d.update(IB_DT_DEFAULTS.get(o, {"has_date": True, "has_time": True}))
    input_datetime_block[o] = d

for oid in data.get("timer", []):
    o = obj_id(oid)
    timer_block[o] = {"name": title(o), "duration": "00:15:00"}

IB_TEXT_DEFAULTS = {
    "tts_text": "Hello from the demo!",
}
for oid in data.get("input_text", []):
    o = obj_id(oid)
    input_text_block[o] = {"name": title(o), "initial": IB_TEXT_DEFAULTS.get(o, "")}

for oid in data.get("input_button", []):
    o = obj_id(oid)
    input_button_block[o] = {"name": title(o)}

HOME_LAT, HOME_LON = 39.7817, -89.6501

# Named locations (not just one fixed "away" spot) for the 3 family members
# with a school/work schedule - each maps to a real zone already defined in
# configuration.yaml's zone: list, picked to read naturally against the
# input_select option name (e.g. is_state(..., 'arcade')). Order matters
# for input_select_block below: first entry becomes each option list's
# "school"/"work" entry specifically (see family_presence_automation).
FAMILY_LOCATIONS = {
    "homer_simpson": {
        "work": (39.7900, -89.6400),        # Springfield Nuclear Power Plant
        "pub": (39.7800, -89.6480),         # Moe's Tavern
        "kwik_e_mart": (39.7750, -89.6400), # Kwik-E-Mart
    },
    "marge_simpson": {
        "kwik_e_mart": (39.7750, -89.6400), # Kwik-E-Mart
        "school": (39.7850, -89.6550),      # Springfield Elementary
        "park": (39.7830, -89.6520),        # Springfield Park
    },
    "bart_simpson": {
        "school": (39.7850, -89.6550),      # Springfield Elementary
        "arcade": (39.7900, -89.6450),      # Noiseland Video Arcade
        "ice_rink": (39.7700, -89.6550),    # Springfield Ice Arena
        "kwik_e_mart": (39.7750, -89.6400), # Kwik-E-Mart
        "park": (39.7830, -89.6520),        # Springfield Park
    },
    "lisa_simpson": {
        "school": (39.7850, -89.6550),      # Springfield Elementary
        "arcade": (39.7900, -89.6450),      # Noiseland Video Arcade
        "ice_rink": (39.7700, -89.6550),    # Springfield Ice Arena
        "kwik_e_mart": (39.7750, -89.6400), # Kwik-E-Mart
        "park": (39.7830, -89.6520),        # Springfield Park
    },
}

# Requested directly: "the always go from home to the zone and back...
# can homer go from home to work to the pub to kwik e mart, then home...
# its better showing a journey rather than home and back constantly" -
# each person's FIXED, ordered route (not a random single spot picked
# from FAMILY_LOCATIONS[who] each time - see itinerary_presence_block
# below, which replaces the old scheduled_person_presence_block/
# unscheduled_multi_location_presence_block pair entirely). Marge's own
# route revisits "park" twice (school run, then collecting the dog from a
# walk on the way back) - deliberately kept as two separate stops rather
# than deduplicated, matching exactly what was asked for.
FAMILY_ITINERARY = {
    "homer_simpson": ["work", "pub", "kwik_e_mart"],
    "marge_simpson": ["park", "school", "kwik_e_mart", "park"],
    "bart_simpson": ["school", "arcade", "park", "kwik_e_mart", "ice_rink"],
    "lisa_simpson": ["school", "arcade", "park", "kwik_e_mart", "ice_rink"],
}

# FAMILY_LOCATIONS name -> the matching zone: entry's own slug (HA's
# util.slugify of its `name:` in configuration.yaml - confirmed live,
# apostrophes/hyphens both become "_", not stripped: "Moe's Tavern" ->
# moe_s_tavern, "Kwik-E-Mart" -> kwik_e_mart). Shared across every family
# member since the same named spot (e.g. "school") always means the same
# real zone regardless of who's there.
FAMILY_LOCATION_ZONE_SLUG = {
    "work": "springfield_nuclear_power_plant",
    "pub": "moe_s_tavern",
    "school": "springfield_elementary",
    "arcade": "noiseland_video_arcade",
    "ice_rink": "springfield_ice_arena",
    "kwik_e_mart": "kwik_e_mart",
    "gymnastics": "springfield_gymnastics",
    "park": "springfield_park",
}


def _presence_in_zones_block(sel, who):
    """in_zones: template mirroring _presence_coord_expr's own step_N
    branches (see FAMILY_ITINERARY - step-indexed, not named-location-
    indexed, since a route can revisit the same named spot twice, e.g.
    Marge's "park"). Needed for the exact same reason the dog's tracker
    already has one (see its own comment, "stuck derived state" bug
    confirmed live 2026-09-18): a template device_tracker with only
    latitude/longitude never reliably re-derives its zone-matched state as
    those coordinates change over time, so every other family/kids tracker
    relying on HA's automatic zone-matching was hitting the same bug -
    showing as a bare "Away" that never tracked the real zone.
    'home'/'heading_home'/anything else fall through to zone.home,
    matching _presence_coord_expr's own fallback to home_val for those
    same states."""
    lines = ['        in_zones: >-\n']
    branch = "if"
    for i, name in enumerate(FAMILY_ITINERARY[who], start=1):
        slug = FAMILY_LOCATION_ZONE_SLUG[name]
        lines.append(f"          {{% {branch} is_state('{sel}', 'step_{i}') %}}\n")
        lines.append(f"          {{{{ ['zone.{slug}'] }}}}\n")
        branch = "elif"
    lines.append("          {% else %}\n")
    lines.append("          {{ ['zone.home'] }}\n")
    lines.append("          {% endif %}\n")
    return "".join(lines)

# Requested directly: "the dog is away too often - if the dog is away a
# person needs to be with him, or he has escaped." Dog's own presence
# state machine (see dog_come_and_go_automation below) - a legitimate
# "walk" only happens while someone's actually home to take him; if the
# automation ever needs to move him while the house is empty, that's framed
# as "escaped" instead, landing him somewhere outside every defined zone
# (not a real destination) rather than a suspiciously specific place.
DOG_LOCATIONS = {
    "walk": (39.7830, -89.6520),      # Springfield Park
    "escaped": (39.7770, -89.6610),   # nowhere recognisable - outside every zone
}

# Requested directly: "make the mower move around the location map if
# possible" - four small waypoints around the house (~30-50m offsets, a
# back garden's worth of space, comfortably inside zone.home's 150m radius
# so the mower never leaves "home" as far as zone-matching is concerned;
# it's still visibly moving on any map card that actually plots
# device_tracker.mower_demo's own lat/long, which is the whole point).
# mower_come_alive_automation cycles input_select.demo_mower_position
# through these while lawn_mower.mower_demo's real state is "mowing".
MOWER_GARDEN_SPOTS = {
    "spot_1": (HOME_LAT + 0.0004, HOME_LON + 0.0003),
    "spot_2": (HOME_LAT + 0.0004, HOME_LON - 0.0003),
    "spot_3": (HOME_LAT - 0.0003, HOME_LON - 0.0004),
    "spot_4": (HOME_LAT - 0.0003, HOME_LON + 0.0004),
}
input_select_block["demo_mower_position"] = {
    "name": title("mower_position"),
    "options": ["dock"] + list(MOWER_GARDEN_SPOTS),
    "initial": "dock",
}

# Not referenced anywhere in the real dashboard (purely an internal state
# machine for automations/family_presence.yaml, see below) - "home" most of
# the time, "heading_home" for one tick on the way back so the real
# dashboard's "Heading Home" map popup has something to actually show.
# "step_1".."step_N" (N = len(FAMILY_ITINERARY[who])) walk through that
# person's fixed route one stop at a time - step-indexed rather than
# named-location-indexed since a route can revisit the same named spot
# twice (Marge's "park") and the input_select's current VALUE has to
# unambiguously identify WHICH visit it's on, not just which place.
for who in ("homer_simpson", "marge_simpson", "bart_simpson", "lisa_simpson"):
    options = (
        ["home"]
        + [f"step_{i}" for i in range(1, len(FAMILY_ITINERARY[who]) + 1)]
        + ["heading_home"]
    )
    input_select_block[f"demo_{who}_presence"] = {
        "name": title(f"{who}_presence"),
        "options": options,
        "initial": "home",
    }

# Backing input_select for the 3D printer's fake status (see
# REACTIVE_SENSOR_NAMES/TEXT_SENSORS' p2s_22e8bj620203679_print_status
# above, and printer_come_alive_automation further down) - has to be
# registered before the dump_helper_file("input_select.yaml", ...) call
# below, same as every other backing_select()/input_select_block entry.
backing_select("demo_printer_status", ["idle", "prepare", "running", "pause"], initial="idle")

input_select_block["demo_dog_presence"] = {
    "name": title("dog_presence"),
    "options": ["home"] + list(DOG_LOCATIONS),
    "initial": "home",
}

# ---------------------------------------------------------------------------
# DEVICE_TRACKER -> template device_tracker entities (in_zones: / latitude+
# longitude: templates), NOT device_tracker.see - that action is deprecated
# as of 2026.x and HA's own repair warning says it'll be removed in 2027.5,
# pointing at template trackers as the replacement. Template trackers also
# need no startup seeding at all (unlike .see, which needed an automation to
# call it once) - they compute their position live from the moment HA
# starts, same as every other template domain here.
FAMILY_PRESENCE_TRACKER_IDS = {"homer_simpson_phone", "marge_simpson_phone", "bart_simpson_phone", "lisa_simpson_phone"}
OTHER_PEOPLE = ["comic_book_guy2", "abraham_simpson_s_a52s", "ned_flanders_iphone", "barney_gumble_s_z_flip5", "patty_bouviers_iphone", "mona_simpson_s_a22"]
# Real Simpsons character art the repo owner supplied into demo/www/ (not
# fetched or generated here) - one per non-family tracked person, matched to
# NAME_MAP's swap for that same object_id's leading word.
OTHER_PEOPLE_AVATARS = {
    "comic_book_guy2": "avatar_comic_book_guy.png",
    "abraham_simpson_s_a52s": "avatar_abraham_simpson.jpg",
    "ned_flanders_iphone": "avatar_ned_flanders.jpg",
    "barney_gumble_s_z_flip5": "avatar_barney_gumble.jpg",
    "patty_bouviers_iphone": "avatar_patty_bouvier.png",
    "mona_simpson_s_a22": "avatar_mona_simpson.jpg",
}
OTHER_AWAY_LAT, OTHER_AWAY_LON = 39.9000, -89.9000


def _presence_coord_expr(sel, who, coord_index, home_val):
    """Nested-ternary Jinja expr resolving sel's current step_N option to a
    coordinate, via FAMILY_ITINERARY[who][N-1] -> FAMILY_LOCATIONS[who].
    Falls through to home_val for 'home'/'heading_home'/anything else. Same
    boundary-free approach as everywhere else here - avoids a Jinja dict
    literal (more moving parts, harder to read in generated YAML) for what
    is at most 5 steps."""
    expr = f"{home_val}"
    for i, name in enumerate(FAMILY_ITINERARY[who], start=1):
        coord = FAMILY_LOCATIONS[who][name][coord_index]
        expr = f"({coord} if is_state('{sel}', 'step_{i}') else {expr})"
    return expr

# The real dashboard's map cards and picture-entity "arrived home" badges
# (ui-lovelace.yaml's Locations view) reference a SECOND device_tracker per
# family member - the real integration's own id (Google Maps/Pixel/GPS
# collar), separate from person:'s own device_trackers: list (homer_simpson_phone
# etc, right below). Confirmed live (2026-09-17): these fell through to the
# generic "everything else stays permanently home" branch below (static
# in_zones: zone.home, no latitude/longitude at all), so the map cards had
# no coordinates to plot a pin or history from, and the picture-entity
# badges that show this tracker's own state permanently read "Home" while
# the mushroom-person-card next to it (fed by person.homer_simpson, itself fed by
# the correctly-dynamic homer_simpson_phone tracker) showed the real, varying
# state - two cards for the same person, permanently disagreeing. Wiring
# these to the same input_select.demo_<who>_presence phase as homer_simpson_phone
# fixes both: real coordinates to plot (map pins + history), and a state
# that actually agrees with person.<who> since they share the same source.
FAMILY_EXTRA_TRACKER_WHO = {
    "google_maps_104199578859638696260": "homer_simpson",
    "google_maps_146646711938998732988": "marge_simpson",
    "pixel_6_pro_lisa_simpson": "lisa_simpson",
}


def _dog_coord_expr(coord_index):
    home_val = HOME_LAT if coord_index == 0 else HOME_LON
    expr = f"{home_val}"
    for name, coords in DOG_LOCATIONS.items():
        expr = f"({coords[coord_index]} if is_state('input_select.demo_dog_presence', '{name}') else {expr})"
    return expr

for oid in data.get("device_tracker", []):
    o = obj_id(oid)
    name = register_name(f"device_tracker.{o}", o)
    if o in OTHER_PEOPLE_AVATARS:
        CUSTOMIZE_PICTURE[f"device_tracker.{o}"] = f"/local/{OTHER_PEOPLE_AVATARS[o]}"
    if o in FAMILY_EXTRA_TRACKER_WHO:
        who = FAMILY_EXTRA_TRACKER_WHO[o]
        sel = f"input_select.demo_{who}_presence"
        # Confirmed live (2026-09-24): with no entity_picture, HA's frontend
        # falls back to auto-generated initials for this tracker's own
        # more-info dialog/badges - "Pixel 6 Pro Lisa Simpson" -> "P6P" (first
        # letter of each of the first 3 words), never seen on the real
        # instance only because the real Google/Pixel tracker integrations
        # supply a genuine profile picture there. Reusing the same avatar
        # already wired to person.<who> (ui-lovelace.yaml's picture-entity
        # cards) avoids that fallback ever triggering here too.
        CUSTOMIZE_PICTURE[f"device_tracker.{o}"] = f"/local/avatar_{who}.png"
        LINES_TEMPLATE.append(("device_tracker", (
            f'      - name: {yq(name)}\n'
            f'        unique_id: demo_dt_{o}\n'
            f'        latitude: "{{{{ {_presence_coord_expr(sel, who, 0, HOME_LAT)} }}}}"\n'
            f'        longitude: "{{{{ {_presence_coord_expr(sel, who, 1, HOME_LON)} }}}}"\n'
            + _presence_in_zones_block(sel, who)
        )))
        continue
    if o == "eleqqixh_dog":
        # Driven by input_select.demo_dog_presence (see
        # dog_come_and_go_automation below) - home most of the time,
        # occasionally out for a walk (or, rarely, escaped) rather than
        # permanently home with nothing to plot.
        #
        # Confirmed live 2026-09-18: this entity's derived state/in_zones
        # never updated away from "home" no matter how many times its
        # latitude/longitude changed (verified: the attributes themselves
        # were correct every time; a live homer_simpson_phone control-group test
        # on the same container, same template shape, updated correctly)
        # - the same "stuck derived state" class of bug documented in
        # ENGINEERING_NOTES.md, this time not fixable by pointing the
        # dashboard at person.dog instead (it only has this one
        # tracker to source from, so it inherits the same stuck value).
        # Worked around by setting in_zones: explicitly instead of relying
        # on HA's automatic lat/long-to-zone matching for this entity -
        # same in_zones: templating already used below for the
        # "everything else stays permanently home" entities.
        LINES_TEMPLATE.append(("device_tracker", (
            f'      - name: {yq(name)}\n'
            f'        unique_id: demo_dt_{o}\n'
            f'        latitude: "{{{{ {_dog_coord_expr(0)} }}}}"\n'
            f'        longitude: "{{{{ {_dog_coord_expr(1)} }}}}"\n'
            f'        in_zones: >-\n'
            f'          {{% if is_state(\'input_select.demo_dog_presence\', \'walk\') %}}\n'
            f'          {{{{ [\'zone.springfield_park\'] }}}}\n'
            f'          {{% elif is_state(\'input_select.demo_dog_presence\', \'escaped\') %}}\n'
            f'          {{{{ [] }}}}\n'
            f'          {{% else %}}\n'
            f'          {{{{ [\'zone.home\'] }}}}\n'
            f'          {{% endif %}}\n'
        )))
        continue
    if o in OTHER_PEOPLE:
        # Presence driven by automations/other_people_presence (see below)
        # flipping this backing input_boolean - the template just reflects it.
        backing = backing_bool(f"demo_other_{o}_home")
        LINES_TEMPLATE.append(("device_tracker", (
            f'      - name: {yq(name)}\n'
            f'        unique_id: demo_dt_{o}\n'
            f'        latitude: "{{{{ {HOME_LAT} if is_state(\'{backing}\', \'on\') else {OTHER_AWAY_LAT} }}}}"\n'
            f'        longitude: "{{{{ {HOME_LON} if is_state(\'{backing}\', \'on\') else {OTHER_AWAY_LON} }}}}"\n'
        )))
        continue
    if o == "mower_demo":
        # Requested directly: "make the mower move around the location map
        # if possible" - it was permanently pinned to zone.home (the generic
        # fallback below), same static-forever bug every other tracker here
        # had before getting its own presence wiring. mower_come_alive_automation
        # (below) advances input_select.demo_mower_position through
        # MOWER_GARDEN_SPOTS while lawn_mower.mower_demo's own state is
        # "mowing" - no separate presence phase needed, the mower entity's
        # real state IS the phase.
        expr = f"{HOME_LAT}"
        lon_expr = f"{HOME_LON}"
        for spot, (lat, lon) in MOWER_GARDEN_SPOTS.items():
            expr = f"({lat} if is_state('input_select.demo_mower_position', '{spot}') else {expr})"
            lon_expr = f"({lon} if is_state('input_select.demo_mower_position', '{spot}') else {lon_expr})"
        LINES_TEMPLATE.append(("device_tracker", (
            f'      - name: {yq(name)}\n'
            f'        unique_id: demo_dt_{o}\n'
            f'        latitude: "{{{{ {expr} }}}}"\n'
            f'        longitude: "{{{{ {lon_expr} }}}}"\n'
            f'        in_zones: "{{{{ [\'zone.home\'] }}}}"\n'
        )))
        continue
    # Everything else stays permanently home - no automation ever moves
    # these, same "always home" behaviour the old seed-once .see call gave
    # them.
    LINES_TEMPLATE.append(("device_tracker", (
        f'      - name: {yq(name)}\n'
        f'        unique_id: demo_dt_{o}\n'
        f'        in_zones: "{{{{ [\'zone.home\'] }}}}"\n'
    )))
# The 4 family phone trackers aren't referenced anywhere in the real
# dashboard (person: device_trackers: is the only thing pointing at them, in
# configuration.yaml) so they're never picked up by the regex scan above -
# their position is driven directly by automations/family_presence.yaml's
# input_select.demo_<who>_presence phase - see FAMILY_LOCATIONS above for
# the coordinates each option resolves to.
for who in ("homer_simpson", "marge_simpson", "bart_simpson", "lisa_simpson"):
    name = title(f"{who}_phone")
    sel = f"input_select.demo_{who}_presence"
    LINES_TEMPLATE.append(("device_tracker", (
        f'      - name: {yq(name)}\n'
        f'        unique_id: demo_dt_{who}_phone\n'
        f'        latitude: "{{{{ {_presence_coord_expr(sel, who, 0, HOME_LAT)} }}}}"\n'
        f'        longitude: "{{{{ {_presence_coord_expr(sel, who, 1, HOME_LON)} }}}}"\n'
        + _presence_in_zones_block(sel, who)
    )))

# ---------------------------------------------------------------------------
# binary_sensor.github_action_running - aggregates sensor.github_actions_latest_run
# (a real, hand-written REST sensor in demo/configuration.yaml) into the same
# shape prod's binary_sensor.github_action_running exposes, for the popup card.
# ---------------------------------------------------------------------------
LINES_TEMPLATE.append(("binary_sensor", (
    '      - name: "Github Action Running"\n'
    '        unique_id: demo_bs_github_action_running\n'
    '        icon: mdi:github\n'
    '        state: "{{ is_state(\'sensor.github_actions_latest_run\', \'in_progress\') }}"\n'
    '        attributes:\n'
    '          running: >-\n'
    '            {% if is_state(\'sensor.github_actions_latest_run\', \'in_progress\') %}\n'
    '              {{ [{\n'
    '                \'name\': \'Publish demo image\',\n'
    '                \'build\': state_attr(\'sensor.github_actions_latest_run\', \'run_number\'),\n'
    '                \'started\': state_attr(\'sensor.github_actions_latest_run\', \'created_at\'),\n'
    '                \'url\': state_attr(\'sensor.github_actions_latest_run\', \'html_url\') }] }}\n'
    '            {% else %}\n'
    '              {{ [] }}\n'
    '            {% endif %}\n'
)))

# ---------------------------------------------------------------------------
# sensor.github_actions_last_commit_message / sensor.github_actions_last_run_status
# - derive real values off sensor.github_actions_latest_run for the
# "GitHub Actions Info" entities card. Mirrors prod's configuration.yaml fix
# (2026-09-25): the card previously used `type: template` rows, which is
# only a valid row type on custom:mushroom-chips-card, not the core
# `entities` card - it silently rendered as "Configuration error" here too.
# ---------------------------------------------------------------------------
LINES_TEMPLATE.append(("sensor", (
    '      - name: "GitHub Actions Last Commit Message"\n'
    '        unique_id: demo_sn_github_actions_last_commit_message\n'
    '        icon: mdi:message-text\n'
    '        state: "{{ (state_attr(\'sensor.github_actions_latest_run\', \'head_commit\') or {}).get(\'message\', \'Unknown\') }}"\n'
)))
LINES_TEMPLATE.append(("sensor", (
    '      - name: "GitHub Actions Last Run Status"\n'
    '        unique_id: demo_sn_github_actions_last_run_status\n'
    '        icon: mdi:check-circle-outline\n'
    '        state: "{{ state_attr(\'sensor.github_actions_latest_run\', \'conclusion\') or states(\'sensor.github_actions_latest_run\') }}"\n'
)))

# ---------------------------------------------------------------------------
# binary_sensor.demo_azure_devops_approval_pending - demo-only FAKE signal:
# the demo has no real Azure DevOps to query, so this is a toggleable
# simulated "waiting on approval" state (backed by an input_boolean flipped
# occasionally by azure_devops_approval_come_alive_automation below), not a
# mirror of any real prod entity. url is a dead '#' link - nothing real to
# approve.
# ---------------------------------------------------------------------------
backing_bool("demo_azure_devops_approval_pending", icon="mdi:account-check")
LINES_TEMPLATE.append(("binary_sensor", (
    '      - name: "Demo Azure Devops Approval Pending"\n'
    '        unique_id: demo_bs_azure_devops_approval_pending\n'
    '        state: "{{ is_state(\'input_boolean.demo_azure_devops_approval_pending\', \'on\') }}"\n'
    '        attributes:\n'
    '          pending: >-\n'
    '            {% if is_state(\'input_boolean.demo_azure_devops_approval_pending\', \'on\') %}\n'
    '              {{ [{\n'
    '                \'name\': \'Publish to Github\',\n'
    '                \'since\': now().isoformat(),\n'
    '                \'url\': \'#\' }] }}\n'
    '            {% else %}\n'
    '              {{ [] }}\n'
    '            {% endif %}\n'
)))

# ---------------------------------------------------------------------------
# AUTOMATION -> automation.irrigation_daily_schedule needs to exist with that id
# ---------------------------------------------------------------------------
AUTOMATION_STUB = """- id: irrigation_daily_schedule
  alias: Irrigation Daily Schedule
  description: Demo stand-in for the real irrigation scheduler.
  trigger:
    - trigger: time
      at: input_datetime.irrigation_start_time
  condition:
    - condition: state
      entity_id: input_boolean.irrigation_enabled
      state: "on"
  action:
    - action: logbook.log
      data:
        name: Irrigation
        message: demo irrigation cycle started
  mode: single
"""

# ===========================================================================
# WRITE FILES
# ===========================================================================

# --- template.yaml : one static block (sensor/binary_sensor) + reactive blocks
by_domain_template = {}
for domain, entry in LINES_TEMPLATE:
    by_domain_template.setdefault(domain, []).append(entry)

out = []
# trigger-based block: sensor + binary_sensor (need periodic refresh to feel alive)
out.append("# Auto-generated by generate_demo_entities.py - do not hand-edit; regenerate instead.")
out.append("- trigger:")
out.append("    - trigger: time_pattern")
out.append('      minutes: "/2"')
out.append("  sensor:")
out.extend(e.rstrip("\n") for e in by_domain_template.get("sensor", []))
out.append("  binary_sensor:")
out.extend(e.rstrip("\n") for e in by_domain_template.get("binary_sensor", []))
# weather's condition/humidity have no entity reference for HA to key a
# reactive re-render off of (plain range()|random), so it needs the same
# periodic trigger as sensor/binary_sensor to actually vary over time.
out.append("  weather:")
out.extend(e.rstrip("\n") for e in by_domain_template.get("weather", []))

# reactive (state-based) blocks: one list item per domain, no trigger needed
for domain in ("switch", "light", "number", "select", "button", "vacuum", "device_tracker", "image"):
    entries = by_domain_template.get(domain, [])
    if not entries:
        continue
    out.append(f"- {domain}:")
    out.extend(e.rstrip("\n") for e in entries)

# sensor_reactive: same idea, but domain is still "sensor" - see
# REACTIVE_SENSOR_NAMES above for why these specific ones are split out of
# the trigger-based sensor: block.
reactive_sensor_entries = by_domain_template.get("sensor_reactive", [])
if reactive_sensor_entries:
    out.append("- sensor:")
    out.extend(e.rstrip("\n") for e in reactive_sensor_entries)

# binary_sensor_reactive: same idea, for REACTIVE_BINARY_SENSOR_NAMES above.
reactive_binary_sensor_entries = by_domain_template.get("binary_sensor_reactive", [])
if reactive_binary_sensor_entries:
    out.append("- binary_sensor:")
    out.extend(e.rstrip("\n") for e in reactive_binary_sensor_entries)

(OUT / "template.yaml").write_text("\n".join(out) + "\n", encoding="utf-8")

# --- climate.yaml : generic_thermostat entries (not template - see comment above)
climate_out = ["# Auto-generated by generate_demo_entities.py - do not hand-edit; regenerate instead."]
climate_out.extend(e.rstrip("\n") for e in LINES_GENERIC_THERMOSTAT)
(OUT / "climate.yaml").write_text("\n".join(climate_out) + "\n", encoding="utf-8")

# --- media_player.yaml / remote.yaml : custom_components/demo_media_player,
# custom_components/demo_remote (not template - neither domain has a
# template.py in this HA version, see comment above)
mp_out = [
    "# Auto-generated by generate_demo_entities.py - do not hand-edit; regenerate instead.",
    "- platform: demo_media_player",
    "  players:",
]
mp_out.extend(e.rstrip("\n") for e in LINES_MEDIA_PLAYER)
(OUT / "media_player.yaml").write_text("\n".join(mp_out) + "\n", encoding="utf-8")

remote_out = [
    "# Auto-generated by generate_demo_entities.py - do not hand-edit; regenerate instead.",
    "- platform: demo_remote",
    "  remotes:",
]
remote_out.extend(e.rstrip("\n") for e in LINES_REMOTE)
(OUT / "remote.yaml").write_text("\n".join(remote_out) + "\n", encoding="utf-8")

# --- valve.yaml : custom_components/demo_valve (not template - no valve.py
# in this HA version, see comment above)
valve_out = [
    "# Auto-generated by generate_demo_entities.py - do not hand-edit; regenerate instead.",
    "- platform: demo_valve",
    "  valves:",
]
valve_out.extend(e.rstrip("\n") for e in LINES_VALVE)
(OUT / "valve.yaml").write_text("\n".join(valve_out) + "\n", encoding="utf-8")

# --- cameras.json (consumed by demo/tools/setup_demo_cameras.py, not by HA directly)
(OUT / "cameras.json").write_text(json.dumps(CAMERA_MAP, indent=2) + "\n", encoding="utf-8")

# --- helpers.yaml (input_boolean/input_number/input_select/input_datetime/timer)
import yaml as _yaml


def dump_helper_file(filename, block):
    header = "# Auto-generated by generate_demo_entities.py - do not hand-edit; regenerate instead.\n\n"
    body = _yaml.safe_dump(block, sort_keys=False, allow_unicode=True, default_flow_style=False)
    (OUT / filename).write_text(header + body, encoding="utf-8")


dump_helper_file("input_boolean.yaml", input_boolean_block)
dump_helper_file("input_number.yaml", input_number_block)
dump_helper_file("input_select.yaml", input_select_block)
dump_helper_file("input_datetime.yaml", input_datetime_block)
dump_helper_file("timer.yaml", timer_block)
dump_helper_file("input_text.yaml", input_text_block)
dump_helper_file("input_button.yaml", input_button_block)

# --- automations.yaml (top-level, mirrors the real repo's !include automations.yaml)
# No more "seed device trackers at startup" automation - template
# device_trackers (see the DEVICE_TRACKER section above) compute their own
# state live from boot, same as every other template domain, so there's
# nothing left to seed.
# Makes the demo look lived-in without anyone clicking anything: every few
# minutes, flips a random switch/light on, then back off after a random
# stretch - like someone's actually home, not just an idle showcase.
lively_list_yaml = "[" + ", ".join(yq(e) for e in LIVELY_SWITCHES) + "]"
come_alive_automation = (
    "- id: come_alive_random_switch\n"
    "  alias: Come Alive - Random Switch/Light\n"
    "  description: Flips a random switch or light on, then off again after a random stretch - makes the demo feel lived-in on its own.\n"
    "  trigger:\n"
    "    - trigger: time_pattern\n"
    "      minutes: \"/3\"\n"
    "  variables:\n"
    f"    lively_entity: '{{{{ {lively_list_yaml} | random }}}}'\n"
    "  action:\n"
    "    - action: input_boolean.turn_on\n"
    "      target:\n"
    "        entity_id: \"{{ lively_entity }}\"\n"
    "    - delay:\n"
    "        seconds: \"{{ range(60, 600) | random }}\"\n"
    "    - action: input_boolean.turn_off\n"
    "      target:\n"
    "        entity_id: \"{{ lively_entity }}\"\n"
    "  mode: parallel\n"
    "  max: 10\n"
)

# Same "come alive" shape as the switch/light one above, but for media
# players: every so often, turns a random individual (non-group) player on
# - which itself picks a random Simpsons-themed "now playing" title/artist,
# see demo_media_player's DemoMediaPlayer._pick_now_playing() - then off
# again after a random stretch, same on/delay/off cycle as the switch
# automation (not a pause - pausing and never resuming would leave a player
# stuck non-"off" forever, so the state condition below would never pick it
# again). A longer trigger interval and a longer play stretch than the
# switch automation: real media sessions last minutes to hours, not seconds.
lively_media_list_yaml = "[" + ", ".join(yq(e) for e in LIVELY_MEDIA_PLAYERS) + "]"
come_alive_media_automation = (
    "- id: come_alive_random_media\n"
    "  alias: Come Alive - Random Media Player\n"
    "  description: Starts a random media player playing something, then stops it again after a while - makes the house feel lived-in without anyone clicking play.\n"
    "  trigger:\n"
    "    - trigger: time_pattern\n"
    "      minutes: \"/6\"\n"
    "  variables:\n"
    f"    lively_player: '{{{{ {lively_media_list_yaml} | random }}}}'\n"
    "  condition:\n"
    # A `state` condition's entity_id must be a literal entity_id (or list),
    # not a template - confirmed live (2026-09-16): HA rejected this whole
    # automation at load time ("Entity {{ lively_player }} is neither a
    # valid entity ID nor a valid UUID"), disabling it entirely (entity
    # state stuck "unavailable", not just skipping a run). A `template`
    # condition evaluates the Jinja itself instead of validating its output
    # as an entity_id, so the same is_state() check works here.
    "    - condition: template\n"
    "      value_template: \"{{ is_state(lively_player, 'off') }}\"\n"
    "  action:\n"
    "    - action: media_player.turn_on\n"
    "      target:\n"
    "        entity_id: \"{{ lively_player }}\"\n"
    "    - delay:\n"
    "        seconds: \"{{ range(300, 2400) | random }}\"\n"
    "    - action: media_player.turn_off\n"
    "      target:\n"
    "        entity_id: \"{{ lively_player }}\"\n"
    "  mode: parallel\n"
    "  max: 10\n"
)

# Every generic_thermostat boots with initial_hvac_mode: "heat" and nothing
# ever changed it afterward - confirmed live (2026-09-17): every AC/
# thermostat card showed "Heat" simultaneously forever, not what a real
# house looks like (some rooms warm enough to have cycled off, some not).
# Weighted toggle (not a plain on/off cycle) so it settles into a mix
# rather than a synchronized on-then-off pulse across every unit: a
# currently-heating unit is more likely to turn off than a currently-off
# one is to turn back on, matching other_people_presence_automation's
# "mostly settled, occasional change" shape.
lively_climate_list_yaml = "[" + ", ".join(yq(e) for e in LIVELY_CLIMATE) + "]"
come_alive_climate_automation = (
    "- id: come_alive_random_climate\n"
    "  alias: Come Alive - Random Climate Cycle\n"
    "  description: Occasionally turns a random AC/thermostat on or off, so the panel doesn't show every unit heating at once.\n"
    "  trigger:\n"
    "    - trigger: time_pattern\n"
    "      minutes: \"/5\"\n"
    "  variables:\n"
    f"    lively_climate: '{{{{ {lively_climate_list_yaml} | random }}}}'\n"
    "  action:\n"
    "    - choose:\n"
    "        - conditions:\n"
    "            - \"{{ not is_state(lively_climate, 'off') and (range(0, 10) | random) < 6 }}\"\n"
    "          sequence:\n"
    "            - action: climate.set_hvac_mode\n"
    "              target:\n"
    "                entity_id: \"{{ lively_climate }}\"\n"
    "              data:\n"
    "                hvac_mode: \"off\"\n"
    "        - conditions:\n"
    "            - \"{{ is_state(lively_climate, 'off') and (range(0, 10) | random) < 4 }}\"\n"
    "          sequence:\n"
    "            - action: climate.set_hvac_mode\n"
    "              target:\n"
    "                entity_id: \"{{ lively_climate }}\"\n"
    "              data:\n"
    "                hvac_mode: \"heat\"\n"
    "  mode: single\n"
)

# Home/away/heading-home for the 4 tracked family members, walking through
# FAMILY_ITINERARY[who] one stop per tick rather than teleporting to one
# random spot and straight back - requested directly: "they always go from
# home to the zone and back... its better showing a journey rather than
# home and back constantly". A "heading_home" tick before actually arriving
# back so the real dashboard's "Heading Home" map popup cards (which key
# off sensor.homer_simpson_towards_home / sensor.marge_simpson_towards_home
# being "on" - see TEXT_SENSORS above) have something to show. Only flips
# input_select.demo_<who>_presence - the template device_tracker entities
# above read that same select directly, so there's no separate "move the
# tracker" step (and nothing here uses the deprecated device_tracker.see
# action).
#
# Dropped the old 09:00-15:00 school/work wall-clock forcing entirely -
# that was the earlier design's other source of "not showing a journey":
# real hours meant Homer/the kids could sit pinned at one place for hours
# of demo time with zero visible movement. The route itself already puts
# work/school first, so the "normal day" shape is still there; it just
# isn't gated behind the real clock anymore.


def itinerary_presence_block(who, leave_chance_of_10=4):
    """choose: state machine walking sel through every step in
    FAMILY_ITINERARY[who], in order, one step per automation tick:
    home -> step_1 -> step_2 -> ... -> step_N -> heading_home -> home. At
    home, leave_chance_of_10-in-10 chance of setting out each tick;
    once started, always advances to the next step (no early random
    return partway through - the whole point is a complete, readable
    journey, not another truncated one)."""
    sel = f"input_select.demo_{who}_presence"
    n = len(FAMILY_ITINERARY[who])
    lines = [
        "    - choose:\n",
        "        - conditions:\n",
        "            - condition: state\n",
        f"              entity_id: {sel}\n",
        "              state: home\n",
        f"            - \"{{{{ (range(0, 10) | random) < {leave_chance_of_10} }}}}\"\n",
        "          sequence:\n",
        "            - action: input_select.select_option\n",
        f"              target: {{entity_id: {sel}}}\n",
        "              data:\n",
        "                option: step_1\n",
    ]
    for i in range(1, n):
        lines += [
            "        - conditions:\n",
            "            - condition: state\n",
            f"              entity_id: {sel}\n",
            f"              state: step_{i}\n",
            "          sequence:\n",
            "            - action: input_select.select_option\n",
            f"              target: {{entity_id: {sel}}}\n",
            "              data:\n",
            f"                option: step_{i + 1}\n",
        ]
    lines += [
        "        - conditions:\n",
        "            - condition: state\n",
        f"              entity_id: {sel}\n",
        f"              state: step_{n}\n",
        "          sequence:\n",
        "            - action: input_select.select_option\n",
        f"              target: {{entity_id: {sel}}}\n",
        "              data:\n",
        "                option: heading_home\n",
        "        - conditions:\n",
        "            - condition: state\n",
        f"              entity_id: {sel}\n",
        "              state: heading_home\n",
        "          sequence:\n",
        "            - action: input_select.select_option\n",
        f"              target: {{entity_id: {sel}}}\n",
        "              data:\n",
        "                option: home\n",
    ]
    return "".join(lines)


family_presence_automation = (
    "- id: family_presence_cycle\n"
    "  alias: Family Presence - Come and Go\n"
    "  description: >-\n"
    "    Each of the 4 tracked family members has a fixed route (see\n"
    "    FAMILY_ITINERARY): Homer goes to work, then Moe's Tavern, then\n"
    "    Kwik-E-Mart, then home. Marge does the school run via the park,\n"
    "    then Kwik-E-Mart, then back via the park again (collecting the dog\n"
    "    from a walk) before heading home. Bart and Lisa go to school, the\n"
    "    arcade, the park, Kwik-E-Mart, then the ice rink, before heading\n"
    "    home. Mostly home, with a chance to set out each tick - once\n"
    "    someone's out, they walk the whole route stop by stop rather than\n"
    "    teleporting to one random spot and back, so the family map shows\n"
    "    an actual journey.\n"
    "  trigger:\n"
    "    - trigger: time_pattern\n"
    # 30s, not minutes - requested directly: a visitor watching the demo for
    # a couple of minutes should actually see the map/history build up, not
    # sit on one state for most of that window. 5 real-minute ticks meant a
    # brand-new demo instance looked frozen for its first few minutes.
    "      seconds: \"/30\"\n"
    "  action:\n"
    + itinerary_presence_block("homer_simpson")
    + itinerary_presence_block("marge_simpson")
    + itinerary_presence_block("bart_simpson")
    + itinerary_presence_block("lisa_simpson")
    + "  mode: single\n"
)

# The 6 non-family tracked people (Comic Book Guy, Barney, Patty, Ned, ...) -
# no person: entity, just raw device_trackers the real dashboard shows
# directly, each behind a `state: home` conditional card so they only
# appear on the Home view while actually "visiting". Occasionally flips one
# of their backing input_booleans (see the template device_tracker loop
# above) - weighted so it's a brief pop-in, not a coin flip: a plain 50/50
# toggle is a symmetric random walk across 6 independent booleans and will
# happily drift toward "everyone home at once" over enough ticks, which is
# exactly the "showing all entities" bug this was written to avoid. Mostly
# away, occasionally visiting, never staying long - not evenly split.
other_people_list_yaml = "[" + ", ".join(yq(f"input_boolean.demo_other_{o}_home") for o in OTHER_PEOPLE) + "]"
other_people_presence_automation = (
    "- id: other_people_presence\n"
    "  alias: Friends & Neighbours - Come and Go\n"
    "  description: Every so often, sends one of the non-family tracked people home or away - simulates friends dropping by rather than a permanent fixed state.\n"
    "  trigger:\n"
    "    - trigger: time_pattern\n"
    # Sped up alongside family_presence_cycle - same "demo should visibly do
    # something within its first couple of minutes" reasoning.
    "      seconds: \"/45\"\n"
    "  variables:\n"
    f"    presence_entity: '{{{{ {other_people_list_yaml} | random }}}}'\n"
    "  action:\n"
    "    - choose:\n"
    "        - conditions:\n"
    "            - \"{{ is_state(presence_entity, 'on') and (range(0, 10) | random) < 7 }}\"\n"
    "          sequence:\n"
    "            - action: input_boolean.turn_off\n"
    "              target:\n"
    "                entity_id: \"{{ presence_entity }}\"\n"
    "        - conditions:\n"
    "            - \"{{ is_state(presence_entity, 'off') and (range(0, 10) | random) < 2 }}\"\n"
    "          sequence:\n"
    "            - action: input_boolean.turn_on\n"
    "              target:\n"
    "                entity_id: \"{{ presence_entity }}\"\n"
    "  mode: single\n"
)

printer_come_alive_automation = (
    "- id: printer_come_alive\n"
    "  alias: Come Alive - 3D Printer\n"
    "  description: Cycles the 3D printer through prepare -> running -> (occasional pause) -> idle, roughly once an hour, so the \"Print job running\" conditional card actually appears sometimes instead of staying permanently idle.\n"
    "  trigger:\n"
    "    - trigger: time_pattern\n"
    "      minutes: \"/5\"\n"
    "  action:\n"
    "    - choose:\n"
    "        - conditions:\n"
    "            - condition: state\n"
    "              entity_id: input_select.demo_printer_status\n"
    "              state: idle\n"
    "            - \"{{ (range(0, 12) | random) < 1 }}\"\n"
    "          sequence:\n"
    "            - action: input_select.select_option\n"
    "              target: {entity_id: input_select.demo_printer_status}\n"
    "              data:\n"
    "                option: prepare\n"
    "        - conditions:\n"
    "            - condition: state\n"
    "              entity_id: input_select.demo_printer_status\n"
    "              state: prepare\n"
    "          sequence:\n"
    "            - action: input_select.select_option\n"
    "              target: {entity_id: input_select.demo_printer_status}\n"
    "              data:\n"
    "                option: running\n"
    "        - conditions:\n"
    "            - condition: state\n"
    "              entity_id: input_select.demo_printer_status\n"
    "              state: running\n"
    "          sequence:\n"
    "            - action: input_select.select_option\n"
    "              target: {entity_id: input_select.demo_printer_status}\n"
    "              data:\n"
    "                option: \"{{ (['running','running','running','running','running','running','pause','idle'] | random) }}\"\n"
    "        - conditions:\n"
    "            - condition: state\n"
    "              entity_id: input_select.demo_printer_status\n"
    "              state: pause\n"
    "          sequence:\n"
    "            - action: input_select.select_option\n"
    "              target: {entity_id: input_select.demo_printer_status}\n"
    "              data:\n"
    "                option: running\n"
    "  mode: single\n"
)

# Requested directly: "make more of the conditional panels come alive... the
# mower go to work" - same shape as printer_come_alive_automation: a
# choose: state machine keyed off lawn_mower.mower_demo's own real state
# (no backing input_select needed, the entity already tracks its own
# activity), calling the actual start_mowing/pause/dock services so
# lawn_mower cards see genuine state changes, not just a template read.
# Position (input_select.demo_mower_position, see MOWER_GARDEN_SPOTS above)
# advances a step each "mowing" tick and resets to "dock" on docking, so
# any map card plotting device_tracker.mower_demo visibly moves too.
mower_come_alive_automation = (
    "- id: mower_come_alive\n"
    "  alias: Come Alive - Mower\n"
    "  description: Sends the mower out to mow, moving it between a few spots in the garden, then back to dock - so the mower cards and any map plotting its position show it actually doing something instead of sitting docked forever.\n"
    "  trigger:\n"
    "    - trigger: time_pattern\n"
    "      minutes: \"/5\"\n"
    "  action:\n"
    "    - choose:\n"
    "        - conditions:\n"
    "            - condition: state\n"
    "              entity_id: lawn_mower.mower_demo\n"
    "              state: docked\n"
    "            - \"{{ (range(0, 12) | random) < 1 }}\"\n"
    "          sequence:\n"
    "            - action: lawn_mower.start_mowing\n"
    "              target: {entity_id: lawn_mower.mower_demo}\n"
    "            - action: input_select.select_option\n"
    "              target: {entity_id: input_select.demo_mower_position}\n"
    "              data:\n"
    f"                option: \"{{{{ {jinja_list(MOWER_GARDEN_SPOTS)} | random }}}}\"\n"
    "        - conditions:\n"
    "            - condition: state\n"
    "              entity_id: lawn_mower.mower_demo\n"
    "              state: mowing\n"
    "          sequence:\n"
    "            - choose:\n"
    "                - conditions:\n"
    "                    - \"{{ (range(0, 10) | random) < 1 }}\"\n"
    "                  sequence:\n"
    "                    - action: lawn_mower.dock\n"
    "                      target: {entity_id: lawn_mower.mower_demo}\n"
    "                    - action: input_select.select_option\n"
    "                      target: {entity_id: input_select.demo_mower_position}\n"
    "                      data:\n"
    "                        option: dock\n"
    "                - conditions:\n"
    "                    - \"{{ (range(0, 10) | random) < 2 }}\"\n"
    "                  sequence:\n"
    "                    - action: lawn_mower.pause\n"
    "                      target: {entity_id: lawn_mower.mower_demo}\n"
    "              default:\n"
    "                - action: input_select.select_option\n"
    "                  target: {entity_id: input_select.demo_mower_position}\n"
    "                  data:\n"
    f"                    option: \"{{{{ {jinja_list(MOWER_GARDEN_SPOTS)} | random }}}}\"\n"
    "        - conditions:\n"
    "            - condition: state\n"
    "              entity_id: lawn_mower.mower_demo\n"
    "              state: paused\n"
    "          sequence:\n"
    "            - choose:\n"
    "                - conditions:\n"
    "                    - \"{{ (range(0, 10) | random) < 3 }}\"\n"
    "                  sequence:\n"
    "                    - action: lawn_mower.dock\n"
    "                      target: {entity_id: lawn_mower.mower_demo}\n"
    "                    - action: input_select.select_option\n"
    "                      target: {entity_id: input_select.demo_mower_position}\n"
    "                      data:\n"
    "                        option: dock\n"
    "              default:\n"
    "                - action: lawn_mower.start_mowing\n"
    "                  target: {entity_id: lawn_mower.mower_demo}\n"
    "  mode: single\n"
)

# Same request, for the vacuums: docked -> cleaning -> returning -> docked,
# driving the already-generated input_select.demo_vac_<name>_state entities
# directly (see the VACUUM generator above - start/stop/return_to_base were
# already wired to it, just nothing ever called them, so both vacuums sat
# permanently "docked" and the picture-glance "Vacuum Live Map"/cleaning-
# stats conditional cards never appeared).
_vacuum_state_selects = [f"input_select.demo_vac_{obj_id(o)}_state" for o in data.get("vacuum", [])]
vacuum_come_alive_automation = (
    "- id: vacuum_come_alive\n"
    "  alias: Come Alive - Vacuums\n"
    "  description: Sends a docked vacuum out to clean, then back to dock a while later - so the live-map and cleaning-stats conditional cards actually appear sometimes instead of every vacuum sitting permanently docked.\n"
    "  trigger:\n"
    "    - trigger: time_pattern\n"
    "      minutes: \"/4\"\n"
    "  variables:\n"
    f"    vac_sel: '{{{{ {json.dumps(_vacuum_state_selects)} | random }}}}'\n"
    "  action:\n"
    "    - choose:\n"
    "        - conditions:\n"
    "            - \"{{ is_state(vac_sel, 'docked') and (range(0, 8) | random) < 1 }}\"\n"
    "          sequence:\n"
    "            - action: input_select.select_option\n"
    "              target: \"{{ vac_sel }}\"\n"
    "              data:\n"
    "                option: cleaning\n"
    "        - conditions:\n"
    "            - \"{{ is_state(vac_sel, 'cleaning') and (range(0, 10) | random) < 3 }}\"\n"
    "          sequence:\n"
    "            - action: input_select.select_option\n"
    "              target: \"{{ vac_sel }}\"\n"
    "              data:\n"
    "                option: returning\n"
    "        - conditions:\n"
    "            - \"{{ is_state(vac_sel, 'returning') }}\"\n"
    "          sequence:\n"
    "            - action: input_select.select_option\n"
    "              target: \"{{ vac_sel }}\"\n"
    "              data:\n"
    "                option: docked\n"
    "  mode: single\n"
)

# Same request, for irrigation: opens one zone valve at a time (real
# irrigation runs zones sequentially, not all at once - a condition below
# skips the whole tick if any zone's already open, rather than layering
# more open on top), closes it again after that zone's own configured
# duration - so ui-lovelace.yaml's custom:irrigation-map-card conditional
# (any zone valve open) actually shows up sometimes.
_valve_entities = [f"valve.{obj_id(o)}" for o in data.get("valve", [])]
irrigation_come_alive_automation = (
    "- id: irrigation_come_alive\n"
    "  alias: Come Alive - Irrigation Zones\n"
    "  description: Opens a random irrigation zone for its own configured duration, then closes it again - so the irrigation map card actually appears sometimes instead of every zone sitting permanently closed.\n"
    "  trigger:\n"
    "    - trigger: time_pattern\n"
    "      minutes: \"/7\"\n"
    "  variables:\n"
    f"    valve_entity: '{{{{ {json.dumps(_valve_entities)} | random }}}}'\n"
    "  condition:\n"
    "    - \"{{ (range(0, 6) | random) < 1 }}\"\n"
    f"    - \"{{{{ {jinja_list(_valve_entities)} | select('is_state', 'open') | list | count == 0 }}}}\"\n"
    "  action:\n"
    "    - action: valve.open_valve\n"
    "      target:\n"
    "        entity_id: \"{{ valve_entity }}\"\n"
    "    - delay:\n"
    "        minutes: \"{{ range(3, 15) | random }}\"\n"
    "    - action: valve.close_valve\n"
    "      target:\n"
    "        entity_id: \"{{ valve_entity }}\"\n"
    "  mode: parallel\n"
    "  max: 3\n"
)

# Matches the real automations.yaml's "Heating Boost Timer Finished" -
# without this, timer.heating_boost (correctly started by
# script.heating_boost_on above) just expires silently and
# input_boolean.heating_boost - and the switch tile riding on it - stays
# stuck "on" forever.
heating_boost_timer_automation = (
    "- id: heating_boost_timer_finished\n"
    "  alias: Heating Boost Timer Finished\n"
    "  trigger:\n"
    "    - trigger: event\n"
    "      event_type: timer.finished\n"
    "      event_data:\n"
    "        entity_id: timer.heating_boost\n"
    "  action:\n"
    "    - action: script.heating_boost_off\n"
    "  mode: single\n"
)

# Wires up the demo Grafana's "Home Assistant" datasource automatically,
# every time this demo HA instance starts - answers "can the manual
# setup_demo_grafana_token.py step be automated" directly: yes, since it's
# just the same script HA itself can run via shell_command. The retrying
# happens HERE, at the automation level, not inside the shell command
# itself: confirmed live that HA's shell_command integration hard-kills
# anything still running after 60s with no YAML-configurable override, so a
# shell-level retry loop just gets killed (and logs an error) every single
# time - one shell_command call per repeat instead, each one fast either
# way. continue_on_error is required - without it, one failed attempt stops
# the whole repeat instead of trying again after the delay.
#
# 30 attempts, 60s apart (~30 minutes total, same coverage as before) - NOT
# just "Grafana might still be starting" (that alone would need far less).
# This trigger fires the moment HA's own core finishes starting, which is
# well BEFORE a human has clicked through the onboarding wizard by hand -
# confirmed live, an earlier shorter window (12x/15s, ~3 min) logged
# nothing but "invalid authentication" on every attempt because the
# demo/demo account the script logs in as didn't exist yet. This has to
# patiently out-wait a human, not race them.
#
# 60s apart, not 15s - confirmed live: each failed attempt's login POST
# gets logged by HA's http.ban component as "invalid authentication", and
# at 15s spacing this was fielding one of those roughly every 15 seconds
# for the ENTIRE first several minutes of HA's life, on top of an
# (also since-fixed) postStartCommand poll doing the same every 3s -
# together a near-constant stream of failed-auth requests during exactly
# the window .storage/http needs to go quiet to promote pending to stable.
# Spacing attempts out 4x reduces that load without giving up total
# coverage; see docker-compose.codespaces.yml's postStartCommand comment
# for the fuller picture of what else was contributing to that noise.
#
# Harmless no-op if the observability stack isn't running at all (plain
# `docker compose -f demo/docker-compose.demo.yml up`) - every attempt just
# fails to resolve grafana-demo's hostname and the repeat exhausts quietly;
# HA doesn't treat a failed shell_command as fatal.
grafana_token_setup_automation = (
    "- id: setup_demo_grafana_token\n"
    "  alias: Wire up the demo Grafana datasource token\n"
    "  description: >-\n"
    "    Runs demo/tools/setup_demo_grafana_token.py against this HA instance\n"
    "    whenever it starts, so the optional Grafana add-on's \"Home Assistant\"\n"
    "    datasource needs no manual step. No-op if the observability compose\n"
    "    overlay isn't running (grafana-demo unreachable).\n"
    "  trigger:\n"
    "    - trigger: homeassistant\n"
    "      event: start\n"
    "  action:\n"
    "    - repeat:\n"
    "        count: 30\n"
    "        sequence:\n"
    "          - action: shell_command.setup_demo_grafana_token\n"
    "            continue_on_error: true\n"
    "          - delay:\n"
    "              seconds: 60\n"
    "  mode: single\n"
)

# Answers "can demo/README.md's manual setup_demo_cameras.py step be
# automated" directly: yes, same shape as the Grafana token automation just
# above - it's the same idempotent, safe-to-re-run script either way. Unlike
# Grafana (a separate container that might still be starting, or entirely
# absent if the observability overlay isn't running), this one calls THIS
# instance's own localhost API, so it doesn't need the same long, spaced-out
# retry window - a handful of quick attempts covers HA's own brief post-start
# settling instead. Also covers a rename adding a new camera object_id that
# was never created before (confirmed live 2026-09-23: this is exactly what
# broke after the Homer Simpson/Dog->Simpsons rename - restarting HA alone can't
# create a NEW config-flow-only camera entity, only this script can).
setup_demo_cameras_automation = (
    "- id: setup_demo_cameras\n"
    "  alias: Set up demo cameras and moon integration\n"
    "  description: >-\n"
    "    Runs demo/tools/setup_demo_cameras.py against this HA instance whenever\n"
    "    it starts, so the one-time camera/moon config-flow setup demo/README.md\n"
    "    documents needs no manual step, including after a rename adds a camera\n"
    "    object_id that's never existed before.\n"
    "  trigger:\n"
    "    - trigger: homeassistant\n"
    "      event: start\n"
    "  action:\n"
    "    - repeat:\n"
    "        count: 6\n"
    "        sequence:\n"
    "          - action: shell_command.setup_demo_cameras\n"
    "            continue_on_error: true\n"
    "          - delay:\n"
    "              seconds: 20\n"
    "  mode: single\n"
)

dog_come_and_go_automation = (
    "- id: dog_come_and_go\n"
    "  alias: Dog - Walks and Wandering\n"
    "  description: >-\n"
    "    Dog stays home unless someone is actually around to take him for a\n"
    "    walk - occasionally wanders off on his own if the house is empty, which\n"
    "    reads as \"escaped\" rather than a legitimate walk.\n"
    "  trigger:\n"
    "    - trigger: time_pattern\n"
    # Sped up alongside family_presence_cycle/other_people_presence. Every
    # 60 SECONDS, not "seconds: /60" - confirmed live: HA's time_pattern
    # trigger validates seconds/minutes/hours divisors against 0-59, so 60
    # is out of range ("must be a value between 0 and 59 at 'seconds'. Got
    # None") and silently disabled this entire automation on startup.
    # minutes: "/1" is the correct way to say "every 60 seconds" here.
    "      minutes: \"/1\"\n"
    "  variables:\n"
    "    someone_home: \"{{ is_state('person.homer_simpson', 'home') or is_state('person.marge_simpson', 'home') or is_state('person.bart_simpson', 'home') or is_state('person.lisa_simpson', 'home') }}\"\n"
    "  action:\n"
    "    - choose:\n"
    "        - conditions:\n"
    "            - condition: state\n"
    "              entity_id: input_select.demo_dog_presence\n"
    "              state: home\n"
    "            - \"{{ someone_home and (range(0, 10) | random) < 1 }}\"\n"
    "          sequence:\n"
    "            - action: input_select.select_option\n"
    "              target: {entity_id: input_select.demo_dog_presence}\n"
    "              data:\n"
    "                option: walk\n"
    "        - conditions:\n"
    "            - condition: state\n"
    "              entity_id: input_select.demo_dog_presence\n"
    "              state: home\n"
    "            - \"{{ not someone_home and (range(0, 40) | random) < 1 }}\"\n"
    "          sequence:\n"
    "            - action: input_select.select_option\n"
    "              target: {entity_id: input_select.demo_dog_presence}\n"
    "              data:\n"
    "                option: escaped\n"
    "        - conditions:\n"
    "            - condition: state\n"
    "              entity_id: input_select.demo_dog_presence\n"
    "              state: walk\n"
    "            - \"{{ (range(0, 3) | random) < 1 }}\"\n"
    "          sequence:\n"
    "            - action: input_select.select_option\n"
    "              target: {entity_id: input_select.demo_dog_presence}\n"
    "              data:\n"
    "                option: home\n"
    "        - conditions:\n"
    "            - condition: state\n"
    "              entity_id: input_select.demo_dog_presence\n"
    "              state: escaped\n"
    "            - \"{{ (range(0, 4) | random) < 1 }}\"\n"
    "          sequence:\n"
    "            - action: input_select.select_option\n"
    "              target: {entity_id: input_select.demo_dog_presence}\n"
    "              data:\n"
    "                option: home\n"
    "  mode: single\n"
)

azure_devops_approval_come_alive_automation = (
    "- id: azure_devops_approval_come_alive\n"
    "  alias: Come Alive - Azure DevOps Approval\n"
    "  description: Occasionally toggles a fake \"waiting on approval\" state, so the demo's approval-pending popup shows up sometimes instead of never.\n"
    "  trigger:\n"
    "    - trigger: time_pattern\n"
    "      minutes: \"/5\"\n"
    "  action:\n"
    "    - choose:\n"
    "        - conditions:\n"
    "            - condition: state\n"
    "              entity_id: input_boolean.demo_azure_devops_approval_pending\n"
    "              state: \"off\"\n"
    "            - \"{{ (range(0, 12) | random) < 1 }}\"\n"
    "          sequence:\n"
    "            - action: input_boolean.turn_on\n"
    "              target: {entity_id: input_boolean.demo_azure_devops_approval_pending}\n"
    "        - conditions:\n"
    "            - condition: state\n"
    "              entity_id: input_boolean.demo_azure_devops_approval_pending\n"
    "              state: \"on\"\n"
    "            - \"{{ (range(0, 6) | random) < 1 }}\"\n"
    "          sequence:\n"
    "            - action: input_boolean.turn_off\n"
    "              target: {entity_id: input_boolean.demo_azure_devops_approval_pending}\n"
    "  mode: single\n"
)

automations_text = (
    "# Auto-generated by demo/tools/generate_demo_entities.py - do not hand-edit; regenerate instead.\n\n"
    + come_alive_automation + "\n" + come_alive_media_automation + "\n"
    + come_alive_climate_automation + "\n"
    + family_presence_automation + "\n" + other_people_presence_automation + "\n"
    + printer_come_alive_automation + "\n"
    + mower_come_alive_automation + "\n" + vacuum_come_alive_automation + "\n"
    + irrigation_come_alive_automation + "\n"
    + heating_boost_timer_automation + "\n"
    + dog_come_and_go_automation + "\n" + grafana_token_setup_automation + "\n"
    + setup_demo_cameras_automation + "\n"
    + azure_devops_approval_come_alive_automation + "\n"
    + AUTOMATION_STUB
)
(REPO_ROOT / "demo" / "automations.yaml").write_text(automations_text, encoding="utf-8")

# --- scripts.yaml (top-level, mirrors the real repo's !include scripts.yaml)
# A few ids get a real, harmless HA service instead of the generic logbook
# placeholder - genuinely useful and safe to run against this demo instance.
SCRIPT_OVERRIDES = {
    "reload_all_yaml": [{"action": "homeassistant.reload_all"}],
    "reload_lovelace": [{"action": "lovelace.reload"}],
    "restart_home_assistant_service": [{"action": "homeassistant.restart"}],
    # Confirmed live 2026-09-18: reported as "heating boost does nothing" -
    # switch.heating_boost's turn_on/turn_off (see the switch/light loop
    # above) call these scripts, same as the real dashboard, but as generic
    # logbook-only stubs they never touched input_boolean.heating_boost or
    # timer.heating_boost - so the "Heating Boost Active" conditional card
    # (gated on input_boolean.heating_boost) could never appear. Replicates
    # the real scripts.yaml's actual effect (minus the scene snapshot/
    # restore, not worth building here) instead of just logging.
    "heating_boost_on": [
        {"action": "input_boolean.turn_on", "data": {"entity_id": "input_boolean.heating_boost"}},
        {"action": "climate.set_hvac_mode", "data": {"entity_id": "climate.lounge", "hvac_mode": "heat"}},
        {
            "action": "climate.set_temperature",
            "data": {
                "entity_id": "climate.lounge",
                "temperature": "{{ (state_attr('climate.lounge', 'current_temperature') | float(20) + 5) | round(0) | int }}",
            },
        },
        {
            "action": "timer.start",
            "data": {
                "entity_id": "timer.heating_boost",
                "duration": "{{ '{:02d}:{:02d}:00'.format((states('input_number.heating_boost_minutes') | int(30)) // 60, (states('input_number.heating_boost_minutes') | int(30)) % 60) }}",
            },
        },
    ],
    "heating_boost_off": [
        {"action": "input_boolean.turn_off", "data": {"entity_id": "input_boolean.heating_boost"}},
        {"action": "timer.cancel", "data": {"entity_id": "timer.heating_boost"}},
    ],
}
script_entries = {}
for oid in data.get("script", []):
    o = obj_id(oid)
    sequence = SCRIPT_OVERRIDES.get(o) or [
        {"action": "logbook.log", "data": {"name": title(o), "message": "ran (demo)"}}
    ]
    script_entries[o] = {"alias": title(o), "sequence": sequence, "mode": "single"}
scripts_text = "# Auto-generated by demo/tools/generate_demo_entities.py - do not hand-edit; regenerate instead.\n\n"
scripts_text += _yaml.safe_dump(script_entries, sort_keys=False, allow_unicode=True, default_flow_style=False)
(REPO_ROOT / "demo" / "scripts.yaml").write_text(scripts_text, encoding="utf-8")

# --- customize.yaml (friendly_name overrides for every entity whose real
# title - the one its entity_id is actually derived from - differs from its
# Simpsons-cosmetic one). person: isn't part of `data` (it's declared
# directly in configuration.yaml, not scanned from the real dashboard), so
# its 5 overrides are added by hand here rather than through register_name().
CUSTOMIZE.update({
    "person.homer_simpson": "Homer Simpson",
    "person.marge_simpson": "Marge Simpson",
    "person.bart_simpson": "Bart Simpson",
    "person.lisa_simpson": "Lisa Simpson",
    "person.dog": "Dog",
    # Cleaner than the auto-derived versions (e.g. "Grampa S A52S") - the
    # object_id's device-model suffix (a52s, z_flip5, iphone, ...) doesn't
    # need to survive into a person's display name the way a room/device
    # name legitimately does elsewhere.
    "device_tracker.comic_book_guy2": "Comic Book Guy",
    "device_tracker.abraham_simpson_s_a52s": "Grampa",
    "device_tracker.ned_flanders_iphone": "Ned Flanders",
    "device_tracker.barney_gumble_s_z_flip5": "Barney Gumble",
    "device_tracker.patty_bouviers_iphone": "Patty Bouvier",
    "device_tracker.mona_simpson_s_a22": "Mona Simpson",
})
customize_text = (
    "# Auto-generated by demo/tools/generate_demo_entities.py - do not hand-edit; regenerate instead.\n"
    "#\n"
    "# Every entity here has entity_id derived from its real (unswapped) name -\n"
    "# HA slugifies entity_id from name: at first creation, and the entity\n"
    "# registry remembers that mapping forever afterwards regardless of what\n"
    "# the YAML says later (confirmed live: unique_id/id: fields never\n"
    "# control entity_id, only internal dedup). The real dashboard needs\n"
    "# these exact entity_ids (sensor.bart_simpson_room_*, person.lisa_simpson, etc), so\n"
    "# the Simpsons name can only be applied cosmetically, here, as a\n"
    "# friendly_name override layered on top - never as the entity's own name.\n\n"
)
_all_customize_eids = sorted(set(CUSTOMIZE) | set(CUSTOMIZE_PICTURE))
_customize_merged = {}
for eid in _all_customize_eids:
    entry = {}
    if eid in CUSTOMIZE:
        entry["friendly_name"] = CUSTOMIZE[eid]
    if eid in CUSTOMIZE_PICTURE:
        entry["entity_picture"] = CUSTOMIZE_PICTURE[eid]
    _customize_merged[eid] = entry
customize_text += _yaml.safe_dump(
    _customize_merged,
    sort_keys=False, allow_unicode=True, default_flow_style=False,
)
(REPO_ROOT / "demo" / "customize.yaml").write_text(customize_text, encoding="utf-8")
print(f"customize.yaml overrides: {len(CUSTOMIZE)}")

print("counts:")
for d, v in data.items():
    print(f"  {d}: {len(v)}")
print("input_boolean total:", len(input_boolean_block))
print("input_number total:", len(input_number_block))
print("input_select total:", len(input_select_block))
print("input_datetime total:", len(input_datetime_block))
print("timer total:", len(timer_block))
print("scripts:", len(script_entries))
print("done ->", OUT)
