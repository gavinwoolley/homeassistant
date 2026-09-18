#!/usr/bin/env python3
"""
Sanitizer for the public GitHub mirror of this repo.

Assembles an allowlisted (git-tracked, denylist-filtered) copy of the repo,
redacts secrets/PII via an exact-match real-value map + shape-based regex
rules, drops in the public-facing templates, and (unless --dry-run) pushes
the result as a single squashed commit to the public GitHub repo.

Usage:
    python publish/sanitize.py --dry-run
    python publish/sanitize.py --out /tmp/mirror --report /tmp/report
    python publish/sanitize.py --push  (also commits/pushes; needs GITHUB_PAT env var)

See publish/README.md for the full design.
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML is required (pip install pyyaml)", file=sys.stderr)
    sys.exit(1)

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = Path(__file__).resolve().parent / "config"
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

# Text extensions the redaction passes are applied to. Everything else that
# survives the denylist is copied through byte-for-byte untouched (images,
# fonts, etc. - which is exactly why the denylist has to catch every real
# photo/binary on its own; redaction can't help those).
TEXT_EXTENSIONS = {
    ".yaml", ".yml", ".json", ".py", ".sh", ".ps1", ".js", ".md", ".conf",
    ".alloy", ".service", ".txt", ".toml", ".ini", ".cfg", ".css", ".html",
    ".env", ".csv", ".j2", ".gitignore", ".gitattributes",
}


def _is_scannable_text(path: Path) -> bool:
    # Confirmed live (2026-09-16): a file with no extension at all
    # (nginx/sites-available/default - a plain nginx site config, no
    # ".conf") has Path.suffix == "", which was never in TEXT_EXTENSIONS
    # and had no dotfile-name special case either - completely invisible
    # to every pass and to Gate B, so a real domain sitting in it published
    # untouched. Extensionless text config files (Dockerfiles, nginx's own
    # "default" site, etc.) are common enough that this needs to be the
    # default-safe direction: scan anything without a *recognized binary*
    # shape, not just an *allowlisted text* one. UnicodeDecodeError on the
    # actual read is still the real backstop for genuine binaries.
    if path.suffix.lower() in TEXT_EXTENSIONS:
        return True
    if path.name in (".gitignore", ".gitattributes"):
        return True
    return path.suffix == ""

# NOTE: publish/ is itself part of the public mirror (published for
# transparency - see publish/README.md), so this file's own source ships
# publicly. Never put a real value here - only generic, shared-format
# prefixes that aren't specific to any one person/account. Anything real
# (domains, plates, IPs, project slugs, ...) belongs in
# replacements.local.yaml instead, which build_leftover_blocklist() pulls
# from and which is gitignored/never published.
STATIC_LEFTOVER_BLOCKLIST = [
    "AIza",     # Google API key prefix - shared format, not account-specific
    "eyJhbG",   # JWT header prefix (base64 of {"alg":...}) - shared format
    "glsa_",    # Grafana service-account token prefix - shared format
]


class SanitizeError(RuntimeError):
    pass


# --------------------------------------------------------------------------
# Config loading
# --------------------------------------------------------------------------

def load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load_rules() -> dict:
    return load_yaml(CONFIG_DIR / "redaction-rules.yaml")


def load_map(map_path: Path) -> dict:
    if not map_path.exists():
        raise SanitizeError(
            f"Real-value map not found: {map_path}\n"
            f"Copy {CONFIG_DIR / 'replacements.local.example.yaml'} to that path "
            f"and fill in real values (never commit it - it's gitignored)."
        )
    return load_yaml(map_path)


def _load_pattern_file(path: Path) -> list[str]:
    patterns = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith("#"):
                patterns.append(line)
    return patterns


def load_denylist() -> list[str]:
    patterns = _load_pattern_file(CONFIG_DIR / "denylist.txt")
    # denylist.local.txt (gitignored, same pattern as replacements.local.yaml,
    # pulled from an Azure DevOps Secure File in CI) holds path globs that are
    # themselves PII - a real person's first name in a photo filename - so
    # they can't sit in the committed denylist.txt that ships as part of the
    # public mirror. Optional: a fresh checkout with nothing to exclude here
    # yet just gets the committed patterns.
    local_path = CONFIG_DIR / "denylist.local.txt"
    if local_path.exists():
        patterns.extend(_load_pattern_file(local_path))
    return patterns


# --------------------------------------------------------------------------
# Step 1: assemble the allowlisted tree
# --------------------------------------------------------------------------

def git_tracked_files(source_ref: str) -> list[str]:
    out = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", source_ref],
        cwd=REPO_ROOT, capture_output=True, text=True, check=True,
    )
    return [line for line in out.stdout.splitlines() if line]


def is_denylisted(rel_path: str, patterns: list[str]) -> bool:
    p = rel_path.replace("\\", "/")
    for pat in patterns:
        if fnmatch.fnmatch(p, pat) or fnmatch.fnmatch(p, pat.rstrip("/") + "/*"):
            return True
        # ** glob support beyond fnmatch's single-level *
        if "**" in pat:
            regex = "^" + re.escape(pat).replace(r"\*\*", ".*").replace(r"\*", "[^/]*") + "$"
            if re.match(regex, p):
                return True
    return False


def assemble_tree(source_ref: str, denylist: list[str], out_dir: Path) -> list[Path]:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    files = git_tracked_files(source_ref)
    written: list[Path] = []
    for rel in files:
        if is_denylisted(rel, denylist):
            continue
        content = subprocess.run(
            ["git", "show", f"{source_ref}:{rel}"],
            cwd=REPO_ROOT, capture_output=True, check=True,
        ).stdout
        dest = out_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)
        written.append(dest)
    return written


# --------------------------------------------------------------------------
# Step 2: exact-string pass
# --------------------------------------------------------------------------

def flatten_map(m: dict) -> dict[str, str]:
    flat: dict[str, str] = {}
    for section in ("names", "emails", "domain", "zones", "misc"):
        flat.update(m.get(section, {}) or {})
    return flat


def build_exact_replacer(m: dict):
    # Longest key first so e.g. a full email is matched before a bare name
    # that happens to be a substring of it.
    entries = []
    for section in ("names", "emails", "domain", "zones", "misc"):
        for key, value in (m.get(section, {}) or {}).items():
            entries.append((section, key, value))
    entries.sort(key=lambda e: -len(e[1]))

    # One combined alternation, not N sequential passes over the evolving
    # text: confirmed live (2026-09-15) that sequential subn() calls can
    # re-scan a rule's OWN decoy output and corrupt it again if a later,
    # shorter rule's word also happens to appear in that decoy value - e.g.
    # domain's "home.example-real-domain.test" -> "home.example.com" ran fine, but
    # the shorter zones rule "Home" -> "742 Evergreen Terrace" then matched
    # the "home" *inside that decoy* on its own separate pass, producing
    # "742 Evergreen Terrace.example.com". A single-pass alternation can
    # only ever consume each character once, so a decoy value is never
    # reconsidered by a later alternative - regex alternation prefers
    # whichever alternative is listed first at a given position, which is
    # exactly the longest-key-first behavior the two-pass version was
    # supposed to provide (and didn't, reliably).
    group_value: dict[str, str] = {}
    group_slug: dict[str, str] = {}
    group_key: dict[str, str] = {}
    group_exclude_suffixes: dict[str, frozenset[str]] = {}
    parts = []
    for i, (section, key, value) in enumerate(entries):
        if section == "names":
            # Real names show up glued to the next word in camelCase
            # identifiers/URLs and hostname-derived labels (e.g.
            # "SomeoneCom", "someonehousehold_gmail_com") and
            # plurals/possessives ("Smiths") - no trailing boundary at all,
            # so those aren't silently skipped. The leading boundary treats
            # "_" as a real delimiter (unlike \b, which counts "_" as a word
            # char) - confirmed live that HA's own entity_id/object_id
            # slugification means a name is exactly as likely to be
            # underscore-adjacent ("midnight_someone", "pixel_6_pro_someone")
            # as space-adjacent, and \b was silently skipping all of those.
            prefix = r"(?<![A-Za-z0-9])"
            suffix = ""
        elif section == "misc":
            # misc entries are long, unique, non-English-word identifiers
            # (vehicle reg, Wi-Fi SSID, GCP project slugs, slugified
            # email/URL fragments) - never a short generic word that could
            # collide with an unrelated identifier the way "Home"/a bare
            # first name can, so the same underscore-safe leading lookaround "names"
            # uses is safe here too (trailing stays \b - these are whole
            # tokens, not names with plural/possessive endings to catch).
            # Confirmed live (2026-09-16): a plain \b failed to match a
            # misc entry immediately preceded by "_" (known_devices.yaml's
            # "google_maps_<real-slug>" device_tracker key), leaving the
            # household's real Gmail account slug published untouched.
            prefix = r"(?<![A-Za-z0-9])"
            suffix = r"\b" if key[-1].isalnum() or key[-1] == "_" else ""
        else:
            # Every other category (zones, domain, generic words like
            # "Home"/"Work") keeps the original \b-based boundaries on both
            # sides deliberately: those ARE common substrings of unrelated,
            # legitimate identifiers ("homeassistant", "home_docker_compose")
            # that must NOT be touched, and \b's underscore-is-a-word-char
            # behavior is exactly what protects them today. Widening this
            # the same way as "names" would start corrupting entity_ids like
            # sensor.home_docker_compose_latest_build.
            prefix = r"\b" if key[0].isalnum() or key[0] == "_" else ""
            suffix = r"\b" if key[-1].isalnum() or key[-1] == "_" else ""
        # mdi: icon names ("mdi:home", "mdi:home-thermometer", "mdi:school")
        # are a fixed, global namespace from Material Design Icons - never
        # PII, but "home"/"school"/other zone words are exactly the kind of
        # everyday word that collides with a real icon name. Confirmed live
        # (2026-09-16): the zones "Home" rule was corrupting mdi:home into
        # mdi:742_evergreen_terrace throughout both demo/ and the real
        # config. \b alone doesn't protect this - ":" and "-" are both
        # non-word chars, so \b is satisfied on both sides of "home" in
        # "mdi:home-thermometer" too.
        prefix += r"(?<!mdi:)"
        # A value immediately after "== '" or '== "' is being compared
        # against, not displayed - confirmed live (2026-09-16): Jinja
        # templates comparing a device_tracker/person's state against HA's
        # own fixed "home"/"not_home" zone-state constants (never
        # configurable, identical on every HA install regardless of the
        # zone's real name) matched the zones "Home" rule and got the
        # lowercase-context slug substituted in - "s == 'home'" became
        # "s == '742_evergreen_terrace'", which can never be true since the
        # real state is always literally "home", permanently breaking the
        # Home/Away display logic it gated.
        prefix += r"(?<!== ')(?<!==\")"
        gname = f"g{i}"
        group_value[gname] = value
        group_key[gname] = key
        if section == "zones":
            # Confirmed live (2026-09-16): "home" (lowercase) also shows up
            # in .py tooling as a bare panel/url_path identifier unrelated
            # to any zone - demo/tools/setup_demo_cameras.py's
            # SIDEBAR_HIDDEN_PANELS list has to contain the literal string
            # "home" to hide Home Assistant's own built-in "home" panel
            # (confirmed via that panel's real title/component_name via
            # get_panels), and this rule was rewriting it to the zone's
            # slug, which doesn't match any real panel - the built-in
            # duplicate "Overview" stayed visible instead of being hidden.
            # Unlike "names", .py tooling in this repo has no legitimate
            # need for zone-word redaction (zone display text lives in the
            # generated YAML, not the generator's own source), so this is
            # a blanket exclusion rather than another narrow lookbehind.
            group_exclude_suffixes[gname] = frozenset({".py"})
        if section in ("names", "zones"):
            # Confirmed live (2026-09-16): zones have the exact same problem
            # as names - "zone.home" (a real, lowercase entity_id reference
            # inside an `in_zones: ['zone.home']` list) matches the zones
            # section's "Home" -> "742 Evergreen Terrace" rule just fine
            # (the existing \b boundaries are satisfied either side of
            # "home" there), but inserting the display-cased decoy produced
            # "zone.742 Evergreen Terrace" - not a valid entity_id, and HA
            # rejected the whole demo config for it. Same fix as names: use
            # the slugified decoy whenever the match itself was lowercase.
            group_slug[gname] = _slugify(value)
        parts.append(f"(?P<{gname}>{prefix}{re.escape(key)}{suffix})")

    # IGNORECASE: also confirmed live leaking (same incident) -
    # configuration.yaml's `name: Home.example-real-domain.test` has a
    # capital H, which the all-lowercase domain key
    # ("home.example-real-domain.test") never matched case-sensitively in
    # the first place, leaving the real domain
    # exposed for the *previous* version of this function to partially
    # corrupt rather than fully redact. A real value can appear in any
    # casing anywhere in the tree.
    combined = re.compile("|".join(parts), re.IGNORECASE) if parts else None
    return combined, group_value, group_key, group_slug, group_exclude_suffixes


def _slugify(value: str) -> str:
    # Must match HA's own homeassistant.util.slugify exactly, not just be
    # entity_id-safe - confirmed live (2026-09-16) that HA treats an
    # apostrophe as an ordinary separator, not something to delete:
    # slugify("Santa's Little Helper") -> "santa_s_little_helper", not
    # "santas_little_helper". Stripping the apostrophe here (the old
    # behavior) produced a decoy slug that looked reasonable but never
    # matched what HA itself actually assigns as the entity_id when a
    # template entity's `name:` gets this same redacted text - every
    # entity_id reference this pass generates was pointing at a dog that
    # doesn't exist.
    s = value.lower()
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


def exact_pass(files: list[Path], replacer) -> dict[str, int]:
    combined, group_value, group_key, group_slug, group_exclude_suffixes = replacer
    hits: dict[str, int] = {}
    if combined is None:
        return hits

    def _sub(match: re.Match, suffix: str) -> str:
        gname = match.lastgroup
        if suffix in group_exclude_suffixes.get(gname, ()):
            return match.group(0)
        hits[group_key[gname]] = hits.get(group_key[gname], 0) + 1
        # A name matched in lowercase (no \b right boundary means it can
        # start mid-identifier too) is HA entity_id/object_id shape, not
        # prose - those only ever allow [a-z0-9_]. Swapping in the
        # display-cased decoy there ("person.Homer Simpson") would insert
        # spaces/capitals into a live entity reference and silently break
        # it; use the slugified decoy instead whenever the match itself
        # wasn't capitalized.
        slug = group_slug.get(gname)
        if slug and match.group(0)[:1].islower():
            return slug
        return group_value[gname]

    for path in files:
        if not _is_scannable_text(path):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, IsADirectoryError):
            continue
        suffix = path.suffix.lower()
        new_text = combined.sub(lambda m: _sub(m, suffix), text)
        if new_text != text:
            path.write_text(new_text, encoding="utf-8")
    return hits


def rename_redacted_files(files: list[Path], replacer) -> dict[str, str]:
    # Confirmed live (2026-09-16): a redacted family name showing up in a
    # FILENAME, not just file contents, was never handled at all -
    # customize.yaml's `entity_picture: /local/avatar_someone.png` correctly
    # became `/local/avatar_comic_book_guy.png` (exact_pass already redacts
    # file *contents*), but avatar_someone.png itself was never renamed on
    # disk (this pass only ever rewrites text found *inside* files) - every
    # single person's photo 404'd on the published/demo site. Applies the
    # same combined regex to each file's basename and renames it to match
    # whatever the text substitution already produced everywhere else, so
    # a reference and the file it points at always agree post-redaction.
    combined, group_value, group_key, group_slug, group_exclude_suffixes = replacer
    renamed: dict[str, str] = {}
    if combined is None:
        return renamed

    def _sub(match: re.Match, suffix: str) -> str:
        gname = match.lastgroup
        if suffix in group_exclude_suffixes.get(gname, ()):
            return match.group(0)
        slug = group_slug.get(gname)
        if slug and match.group(0)[:1].islower():
            return slug
        return group_value[gname]

    for path in files:
        if not path.exists():
            continue
        suffix = path.suffix.lower()
        new_name = combined.sub(lambda m: _sub(m, suffix), path.name)
        if new_name != path.name:
            new_path = path.with_name(new_name)
            path.rename(new_path)
            renamed[str(path)] = str(new_path)
    return renamed


# --------------------------------------------------------------------------
# Step 3: regex pass (shape-based + deterministic hash-sub)
# --------------------------------------------------------------------------

def hash_sub(value: str, kind: str, salt: str) -> str:
    digest = hashlib.sha256((salt + value).encode()).hexdigest()
    if kind == "mac":
        b = [digest[i:i + 2] for i in range(0, 12, 2)]
        b[0] = format((int(b[0], 16) & 0xFC) | 0x02, "02x")  # locally administered
        return ":".join(b)
    if kind == "guid":
        h = digest[:32]
        return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"
    if kind == "ip":
        last = int(digest[:8], 16) % 254 + 1
        return f"10.0.0.{last}"
    if kind == "subnet":
        return "10.0.0.0/24"
    if kind == "digits21":
        return str(int(digest[:20], 16))[:21].ljust(21, "0")
    if kind in ("lat_jitter", "lon_jitter"):
        # value is the WHOLE match (e.g. "latitude: 52.36149", any prefix
        # spacing/quoting/casing the pattern allowed) - preserve everything
        # up to the real number verbatim, only the number itself changes.
        m = re.search(r"-?\d{1,3}\.\d+", value)
        prefix = value[:m.start()]
        base = 39.7817 if kind == "lat_jitter" else -89.6501
        # +/- ~0.03 degrees (a few miles), derived from the hash so it's
        # deterministic per real value but has no relationship to the real
        # value's actual magnitude or direction.
        offset = (int(digest[8:16], 16) % 6001 - 3000) / 100000
        return f"{prefix}{base + offset:.4f}"
    raise SanitizeError(f"unknown hash-sub kind: {kind}")


def regex_pass(files: list[Path], rules: dict, real_map: dict | None = None) -> dict[str, int]:
    hits: dict[str, int] = {}
    salt = rules.get("salt", "public-mirror")
    compiled_regex = [
        (r["name"], re.compile(r["pattern"]), r["replacement"],
         frozenset(s.lower() for s in r.get("exclude_suffixes", [])))
        for r in rules.get("regex_rules", [])
    ]
    # Bare coordinate literals with no "latitude:"/"longitude:" field name to
    # key on (a static-map URL, a JS comment/default) - driven by the
    # gitignored map since the real prefix can't live in the committed rules
    # file. \bPREFIX\d*\b so "52.36" also catches "52.3615"/"52.36163" etc.
    for entry in (real_map or {}).get("coord_literal_backstops", []):
        prefix = entry["prefix"]
        # Leading \b only works before a word char - a "-" (negative
        # longitude) is non-word, and whatever precedes it (space, comma,
        # quote) usually is too, so \b never matches there. Only require it
        # when the prefix actually starts with a word character.
        lead = r"\b" if prefix[0].isalnum() else ""
        pattern = re.compile(lead + re.escape(prefix) + r"\d*\b")
        compiled_regex.append((f"coord_literal:{prefix}", pattern, entry["decoy"], frozenset()))
    compiled_hash = [(r["name"], re.compile(r["pattern"]), r["kind"])
                      for r in rules.get("hash_sub_rules", [])]

    for path in files:
        suffix = path.suffix.lower()
        if not _is_scannable_text(path):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, IsADirectoryError):
            continue
        original = text
        for name, pattern, replacement, exclude_suffixes in compiled_regex:
            if suffix in exclude_suffixes:
                continue
            text, n = pattern.subn(replacement, text)
            if n:
                hits[name] = hits.get(name, 0) + n
        for name, pattern, kind in compiled_hash:
            def _sub(m, kind=kind):
                return hash_sub(m.group(0), kind, salt)
            text, n = pattern.subn(_sub, text)
            if n:
                hits[name] = hits.get(name, 0) + n
        if text != original:
            path.write_text(text, encoding="utf-8")
    return hits


# --------------------------------------------------------------------------
# Step 4: structural re-check
# --------------------------------------------------------------------------

class _TagTolerantLoader(yaml.SafeLoader):
    pass


def _any_constructor(loader, tag_suffix, node):
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    return loader.construct_mapping(node)


_TagTolerantLoader.add_multi_constructor("!", _any_constructor)


def structural_recheck(files: list[Path]) -> list[str]:
    errors = []
    for path in files:
        suffix = path.suffix.lower()
        try:
            if suffix in (".yaml", ".yml"):
                with path.open(encoding="utf-8") as fh:
                    yaml.load(fh, Loader=_TagTolerantLoader)
            elif suffix == ".json":
                with path.open(encoding="utf-8") as fh:
                    json.load(fh)
        except Exception as e:  # noqa: BLE001 - report, don't crash the whole run
            errors.append(f"{path}: {e}")
    return errors


# --------------------------------------------------------------------------
# Step 5: templates
# --------------------------------------------------------------------------

def apply_templates(out_dir: Path) -> None:
    if not TEMPLATES_DIR.exists():
        return
    for src in TEMPLATES_DIR.rglob("*"):
        if src.is_dir():
            continue
        rel = src.relative_to(TEMPLATES_DIR)
        dest = out_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)


SCREENSHOTS_DIR = Path(__file__).resolve().parent / "assets" / "screenshots"


def apply_screenshots(out_dir: Path) -> None:
    # Hand-reviewed images (Workstream 4) - copied verbatim, never redacted
    # (redaction can't touch pixels; that review has to happen before a file
    # lands in publish/assets/screenshots/ at all). README.md references
    # them at docs/screenshots/<name>.
    if not SCREENSHOTS_DIR.exists():
        return
    dest_dir = out_dir / "docs" / "screenshots"
    dest_dir.mkdir(parents=True, exist_ok=True)
    for src in SCREENSHOTS_DIR.iterdir():
        if src.is_file():
            shutil.copy2(src, dest_dir / src.name)


# --------------------------------------------------------------------------
# Step 6: CI-safe secrets.yaml
# --------------------------------------------------------------------------

def write_ci_safe_secrets(out_dir: Path) -> None:
    target = out_dir / "secrets.yaml"
    if not target.exists():
        return
    target.write_text(
        "# CI-safe placeholder values - overwritten here by publish/sanitize.py.\n"
        "# The private repo's real secrets.yaml is populated at deploy time by\n"
        "# the Azure Pipelines replacetokens step; this copy exists so\n"
        "# ha-config-check.yml's `check_config` has *something* to resolve\n"
        "# !secret references against.\n"
        'google_maps_api_key: "demo-not-a-real-key"\n'
        'adguard_auth_header: "Basic ZGVtbzpkZW1v"\n'
        'callmebot_phone: "447700900000"\n'
        'callmebot_apikey: "000000"\n',
        encoding="utf-8",
    )


# --------------------------------------------------------------------------
# Gates
# --------------------------------------------------------------------------

def gate_gitleaks(out_dir: Path) -> tuple[bool, str]:
    if shutil.which("gitleaks") is None:
        return True, "SKIPPED (gitleaks not on PATH)"
    cmd = ["gitleaks", "detect", "--no-git", "--source", str(out_dir), "-v"]
    # apply_templates() (Step 5, runs before this gate) copies
    # publish/templates/.gitleaks.toml into out_dir - its allowlist covers
    # the sanitizer's own decoy values plus known-benign false positives
    # (e.g. Grafana's auto-generated panel "key" refIds, which are shaped
    # exactly like a high-entropy secret to gitleaks' generic-api-key rule
    # but aren't credentials). Without --config here, that allowlist only
    # ever applied to the *published* repo's own CI, never to this gate.
    config_path = out_dir / ".gitleaks.toml"
    if config_path.exists():
        cmd.extend(["--config", str(config_path)])
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        return True, "clean"
    return False, result.stdout + result.stderr


def build_leftover_blocklist(real_map: dict, extra: list[str]) -> list[tuple[str, str]]:
    # "zones" and generic-word map keys ("Home", "Work", "School", "Grandma",
    # "Gymnastics", ...) are excluded: they're ordinary English words that
    # appear constantly in unrelated contexts throughout an HA config
    # ("Home Assistant", "Homer" already renamed things, etc.), so using them
    # as leftover-literal signal is all noise, no signal. Names/emails/
    # domain/misc are all genuinely rare/PII-shaped strings - real signal.
    #
    # Each entry carries a boundary "style" alongside the needle - see
    # gate_leftover_scan's _leftover_pattern(). Confirmed live (2026-09-15,
    # three separate times: a vendored JS blob, ".dockerignore", and this
    # tool's own code comment) that a bare substring check flags a short
    # mapped name as "found" purely because it's a coincidental substring of
    # an ordinary, unrelated English word - real signal needs the same
    # boundary discipline the redaction pass itself uses, not just
    # case-insensitivity.
    blocklist: list[tuple[str, str]] = []
    for key in (real_map.get("names", {}) or {}).keys():
        blocklist.append((key, "loose"))
    for section in ("emails", "domain", "misc"):
        for key in (real_map.get(section, {}) or {}).keys():
            blocklist.append((key, "strict"))
    for prefix in real_map.get("leftover_backstop_prefixes", []) or []:
        blocklist.append((prefix, "strict"))
    # Independently re-verify the coord_literal_backstops replacements too -
    # Gate B shouldn't just trust the same rule that did the replacing. Same
    # "prefix + trailing digits" shape as the regex_pass rule that actually
    # replaces these (a rounded/truncated copy like "52.3615" is still a
    # leak), so it needs the matching "coord" style, not "strict".
    for e in real_map.get("coord_literal_backstops", []) or []:
        blocklist.append((e["prefix"], "coord"))
    # Static secret-key prefixes ("AIza", "glsa_", ...) are deliberately
    # unbounded on the right - a real key is always more characters glued
    # directly on, never a whole word by itself.
    blocklist.extend((e, "loose") for e in extra)
    return blocklist


def _leftover_scan_exempt_paths(out_dir: Path) -> set[str]:
    # Two categories of file are exempt from the leftover-literal scan, not
    # because they're denylisted from the mirror (they're published), but
    # because Gate B's job is to verify REDACTION worked on the assembled
    # private-repo tree - it has nothing to say about deliberately-authored
    # public content:
    #   1. Template output (README.md, LICENSE, .github/**, ...) - copied
    #      verbatim, never redacted, reviewed as source. This is where
    #      "Copyright (c) ... Gavin Woolley" deliberately lives.
    #   2. publish/ itself - the sanitizer's own tooling. Its committed files
    #      legitimately reference generic secret-shape prefixes ("AIza",
    #      "glsa_", ...) as rule definitions, which would otherwise look like
    #      the tool matching its own blocklist against itself.
    exempt = set()
    if TEMPLATES_DIR.exists():
        for src in TEMPLATES_DIR.rglob("*"):
            if src.is_file():
                exempt.add(str(src.relative_to(TEMPLATES_DIR)).replace("\\", "/"))
    return exempt


# Vendored third-party frontend bundles (HACS cards, under */www/community/*)
# - never touched by redaction, and dense enough with arbitrary SVG path
# coordinates/hex colors that a short coord_literal_backstop prefix (e.g.
# "-1.83", deliberately short so it also catches a truncated/rounded copy of
# a real coordinate elsewhere) will eventually collide with one by pure
# chance. Confirmed live: demo/www/community/custom-icons/custom-icons.js's
# own icon path data happens to contain the substring "-1.83", nothing to do
# with any real location. A path check, not a content check - it's the
# *kind* of file (generic open-source library code) that makes it safe to
# skip, not anything about its content.
#
# Same reasoning for the Grafana arcade panels (grafanaDashboards/dashboards/
# Games/*.json): each embeds a single ~100K+ character packed/minified JS
# blob for its game canvas. Confirmed live: making Gate B case-insensitive
# (2026-09-15, the domain-leak fix) surfaced one of the short mapped names as
# a coincidental substring inside that blob's noise in 3 of the 15 games -
# nothing to do with any real person, just the base statistical odds of a
# short 4-letter name occurring somewhere in >100K characters of packed
# identifiers. Since any of the other short names could collide the same way
# in a different game/build, this is a path exemption (the *kind* of file),
# not a case-by-case allowlist of one specific name.
_NO_REDACTION_PATH_MARKERS = ("/www/community/", "/dashboards/Games/")


def _leftover_pattern(needle: str, style: str) -> re.Pattern:
    # Same boundary philosophy as build_exact_replacer(): "loose" mirrors the
    # "names" section (leading boundary only - a real name glued to the next
    # word, e.g. a hostname-derived label, is still a leak), "strict" is a
    # real word on both sides (misc/domain/emails - common-word collisions
    # matter here), "coord" allows trailing digits (a rounded/truncated
    # coordinate copy is still the same leak).
    prefix = r"(?<![A-Za-z0-9])"
    if style == "loose":
        suffix = ""
    elif style == "coord":
        suffix = r"\d*(?![A-Za-z0-9])"
    else:
        suffix = r"(?![A-Za-z0-9])"
    return re.compile(prefix + re.escape(needle) + suffix, re.IGNORECASE)


def gate_leftover_scan(out_dir: Path, blocklist: list[tuple[str, str]]) -> tuple[bool, list[str]]:
    exempt_files = _leftover_scan_exempt_paths(out_dir)
    compiled = [(needle, _leftover_pattern(needle, style)) for needle, style in blocklist if needle]
    findings = []
    for path in out_dir.rglob("*"):
        if not path.is_file() or not _is_scannable_text(path):
            continue
        rel = str(path.relative_to(out_dir)).replace("\\", "/")
        if rel in exempt_files or rel == "publish" or rel.startswith("publish/"):
            continue
        if any(marker in f"/{rel}" for marker in _NO_REDACTION_PATH_MARKERS):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, IsADirectoryError):
            continue
        for needle, pattern in compiled:
            if pattern.search(text):
                for i, line in enumerate(text.splitlines(), 1):
                    if pattern.search(line):
                        findings.append(f"{path.relative_to(out_dir)}:{i}: contains {needle!r}")
    return (len(findings) == 0), findings


def gate_dashboards(out_dir: Path) -> tuple[bool, list[str]]:
    problems = []
    dash_dir = out_dir / "grafanaDashboards" / "dashboards"
    if not dash_dir.exists():
        return True, []
    uids: dict[str, list[str]] = {}
    titles: dict[tuple, list[str]] = {}
    for p in dash_dir.rglob("*.json"):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            problems.append(f"invalid JSON: {p.relative_to(out_dir)}: {e}")
            continue
        uids.setdefault(d.get("uid"), []).append(str(p.relative_to(out_dir)))
        titles.setdefault((str(p.parent), d.get("title")), []).append(str(p.relative_to(out_dir)))
    for k, v in {**uids, **titles}.items():
        if len(v) > 1:
            problems.append(f"duplicate {k}: {v}")
    return (len(problems) == 0), problems


def gate_yamllint(out_dir: Path) -> tuple[bool, str]:
    if shutil.which("yamllint") is None:
        return True, "SKIPPED (yamllint not on PATH)"
    yamllint_cfg = TEMPLATES_DIR / ".yamllint"
    cmd = ["yamllint"]
    if yamllint_cfg.exists():
        cmd += ["-c", str(out_dir / ".yamllint")]
    cmd.append(str(out_dir))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        return True, "clean"
    return False, result.stdout + result.stderr


# --------------------------------------------------------------------------
# Publish
# --------------------------------------------------------------------------

def git_publish(out_dir: Path, github_url: str, pat: str, source_sha: str) -> None:
    def run(*args):
        subprocess.run(args, cwd=out_dir, check=True)

    run("git", "init", "-q")
    run("git", "checkout", "-q", "-b", "main")
    run("git", "-c", "user.name=Gavin Woolley", "-c", "user.email=noreply@users.noreply.github.com",
        "add", "-A")
    run("git", "-c", "user.name=Gavin Woolley", "-c", "user.email=noreply@users.noreply.github.com",
        "commit", "-q", "-m", f"Sanitized public mirror - source {source_sha[:12]}")
    push_url = github_url.replace("https://", f"https://x-access-token:{pat}@")
    run("git", "push", "--force", push_url, "main")


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source-ref", default="HEAD")
    ap.add_argument("--map", type=Path, default=CONFIG_DIR / "replacements.local.yaml")
    ap.add_argument("--out", type=Path, default=REPO_ROOT / "publish" / "out")
    ap.add_argument("--report", type=Path, default=REPO_ROOT / "publish" / "out.report")
    ap.add_argument("--dry-run", action="store_true", help="run all gates, skip the publish step")
    ap.add_argument("--push", action="store_true", help="commit and push (needs GITHUB_PAT env var)")
    ap.add_argument("--github-url", default="https://github.com/gavinwoolley/homeassistant.git")
    ap.add_argument("--strict", action="store_true",
                     help="fail if gitleaks/yamllint aren't installed instead of skipping them")
    args = ap.parse_args()

    print(f"== Sanitizer: source={args.source_ref} out={args.out} ==")

    rules = load_rules()
    real_map = load_map(args.map)
    flat_map = flatten_map(real_map)
    denylist = load_denylist()

    print("-- Assembling tree --")
    files = assemble_tree(args.source_ref, denylist, args.out)
    print(f"   {len(files)} files")

    # publish/ is the sanitizer's own tooling - already safe by construction
    # (no real values live in its committed files; the one that would,
    # replacements.local.yaml, is denylisted). Redacting it anyway just
    # mangles its own rule-definition strings and doc comments (and, worse,
    # the git commit author identity in this very function) against itself.
    redactable = [f for f in files if "publish" not in f.relative_to(args.out).parts]

    print("-- Exact-string pass --")
    exact_hits = exact_pass(redactable, build_exact_replacer(real_map))
    for k, n in sorted(exact_hits.items(), key=lambda kv: -kv[1]):
        print(f"   {k}: {n}")

    print("-- Renaming redacted filenames --")
    renamed = rename_redacted_files(redactable, build_exact_replacer(real_map))
    for old, new in renamed.items():
        print(f"   {Path(old).name} -> {Path(new).name}")
    if renamed:
        # Every later step (regex_pass, structural_recheck) still holds the
        # pre-rename Path objects - update both lists in place so they open
        # the files that now actually exist on disk instead of crashing on
        # a FileNotFoundError for the name that no longer exists.
        files = [Path(renamed.get(str(f), f)) for f in files]
        redactable = [Path(renamed.get(str(f), f)) for f in redactable]

    print("-- Regex pass --")
    regex_hits = regex_pass(redactable, rules, real_map)
    for k, n in sorted(regex_hits.items(), key=lambda kv: -kv[1]):
        print(f"   {k}: {n}")

    print("-- Structural re-check --")
    struct_errors = structural_recheck(files)
    if struct_errors:
        print("STRUCTURAL PARSE ERRORS (redaction broke something):")
        for e in struct_errors:
            print(f"   {e}")
        return 1
    print("   OK")

    print("-- Templates --")
    apply_templates(args.out)

    print("-- Screenshots --")
    apply_screenshots(args.out)

    print("-- CI-safe secrets.yaml --")
    write_ci_safe_secrets(args.out)

    ok = True

    print("-- Gate A: gitleaks --")
    passed, detail = gate_gitleaks(args.out)
    print(f"   {'PASS' if passed else 'FAIL'}: {detail}")
    ok = ok and (passed or (detail.startswith("SKIPPED") and not args.strict))

    print("-- Gate B: leftover literal scan --")
    passed, findings = gate_leftover_scan(
        args.out, build_leftover_blocklist(real_map, STATIC_LEFTOVER_BLOCKLIST)
    )
    print(f"   {'PASS' if passed else 'FAIL'}")
    for f in findings[:50]:
        print(f"   {f}")
    ok = ok and passed

    print("-- Gate C: dashboard validity / dup uid+title --")
    passed, problems = gate_dashboards(args.out)
    print(f"   {'PASS' if passed else 'FAIL'}")
    for p in problems:
        print(f"   {p}")
    ok = ok and passed

    print("-- Gate D: yamllint --")
    passed, detail = gate_yamllint(args.out)
    print(f"   {'PASS' if passed else 'FAIL'}: {detail[:2000]}")
    ok = ok and (passed or (detail.startswith("SKIPPED") and not args.strict))

    args.report.mkdir(parents=True, exist_ok=True)
    (args.report / "hits.json").write_text(
        json.dumps({"exact": exact_hits, "regex": regex_hits}, indent=2), encoding="utf-8"
    )

    if not ok:
        print("\n== FAILED - not publishing. See gate output above. ==")
        return 1

    print("\n== All gates passed ==")

    if args.push:
        pat = os.environ.get("GITHUB_PAT")
        if not pat:
            print("ERROR: --push requires GITHUB_PAT env var", file=sys.stderr)
            return 1
        source_sha = subprocess.run(
            ["git", "rev-parse", args.source_ref], cwd=REPO_ROOT,
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        git_publish(args.out, args.github_url, pat, source_sha)
        print(f"== Pushed to {args.github_url} ==")
    elif args.dry_run:
        print("(--dry-run: not publishing)")
    else:
        print("(pass --push to actually publish)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
