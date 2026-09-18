# Public mirror sanitizer

Produces the sanitized public mirror at
[github.com/gavinwoolley/homeassistant](https://github.com/gavinwoolley/homeassistant) from
this private repo. The public repo is a **derived artifact**: one squashed commit, force-pushed
every run. Nothing here changes how the private repo itself is built or deployed.

## Setup (first time)

```
cp publish/config/replacements.local.example.yaml publish/config/replacements.local.yaml
```

Fill in real values on the left of `replacements.local.yaml` (it's gitignored - never commit
it). The example file documents the shape and the Simpsons-themed mapping already in use.

## Running it

```
python publish/sanitize.py --dry-run
```

Assembles a sanitized copy in `publish/out/` (gitignored) and runs every gate, but doesn't push
anywhere. Check `publish/out/` and `publish/out.report/hits.json` (per-rule hit counts) before
trusting it.

```
GITHUB_PAT=... python publish/sanitize.py --push
```

Same, plus commits and force-pushes `publish/out/` to the public repo as a single commit on
`main`. This is also what `azure-pipelines-publish.yml` runs (Workstream 5), with the real map
pulled from an Azure DevOps Secure File instead of a local copy.

## How it works

1. **Assemble** - `git ls-tree` at `--source-ref` (default `HEAD`) minus
   `config/denylist.txt` globs, copied into `--out`.
2. **Exact-string pass** - every `key: value` pair in `replacements.local.yaml`, longest key
   first. Names get a leading word-boundary only (not trailing) - real names show up glued to
   the next word in camelCase identifiers/URLs and in plurals/possessives, and a trailing `\b`
   silently skips those. Everything else (zones, domain, generic words) keeps both boundaries,
   since those are common substrings of unrelated identifiers (`homeassistant`) that need strict
   isolation.
3. **Regex pass** - `config/redaction-rules.yaml`: shape-based patterns (JWTs, API keys, PEM
   blocks, coordinate fields, emails, phone numbers) plus deterministic hash-substitution for
   MACs/GUIDs/internal IPs/21-digit IDs (same salt → same fake value everywhere, every run, so
   cross-references between files stay consistent).
4. **Structural re-check** - every touched `.yaml`/`.json` file is re-parsed; a redaction that
   broke syntax aborts the run rather than shipping malformed config.
5. **Templates** - `publish/templates/` (README, LICENSE, `.github/workflows/`, etc. -
   Workstream 3) copied over the sanitized tree, never redacted.
6. **CI-safe `secrets.yaml`** - the real one (still just `#{token}#` placeholders in this repo)
   gets overwritten with dummy-but-valid values so the public repo's `check_config` workflow has
   something to resolve `!secret` against.
7. **Gates** (all four must pass or nothing publishes):
   - **A - gitleaks**: `gitleaks detect --no-git` over the sanitized tree.
   - **B - leftover literal scan**: greps for every real value from
     `replacements.local.yaml` (names/emails/domain/misc - not `zones`, see above) plus a
     static list of known secret prefixes. Independent of the regex/exact passes, so a rule
     that silently under-matches still gets caught here.
   - **C - dashboard validity**: every `grafanaDashboards/dashboards/**/*.json` parses, and the
     duplicate-uid/duplicate-title-in-folder check from `grafanaDashboards/README.md`.
   - **D - yamllint**.
8. **Report** - `publish/out.report/hits.json`, per-rule hit counts (exact + regex passes).
9. **Publish** (only with `--push`) - `git init`/commit/`--force push` `publish/out/` to the
   public repo as `main`.

Gates A and D are skipped with a warning (not a failure) if `gitleaks`/`yamllint` aren't on
`PATH` - pass `--strict` to make their absence a hard failure (what CI does).

## Adding a redaction rule

- New real value (a name, email, place) → add it to `replacements.local.yaml` under the right
  section (and to `replacements.local.example.yaml` too, without the real value, so the shape
  stays documented).
- New shape (a token format, an ID pattern) → add it to `config/redaction-rules.yaml`.
- New file/folder that should never be published at all → add a line to `config/denylist.txt`.

After any change, re-run `--dry-run` and check `publish/out.report/hits.json` - a rule that
never fires is either redundant or the pattern's wrong.
