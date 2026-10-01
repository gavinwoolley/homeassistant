# GitHub Actions + Azure DevOps approval visibility (prod + demo)

## Context

The real production dashboard already has a "Builds & Releases" view
showing Azure DevOps pipeline status (`ui-lovelace.yaml`, `configuration.yaml`
- see "Home Assistant Pipeline Info" / "Docker Pipeline Info" / "Renovate
Pipeline Info" cards, and the "🔄 Azure Pipeline Running" / "⚠️ Azure
Pipeline Failure" conditional banners at the top of the Home view). It has
no visibility into:

- GitHub Actions runs on the public mirror (`demo-image.yml` and friends),
  including whether one is currently running.
- What version of the demo images (`homeassistant-demo`,
  `homeassistant-demo-grafana`) is actually published right now.
- Whether the `azure-pipelines-publish.yml` "Publish to Github" pipeline is
  sitting paused, waiting on a human to approve its `public-mirror`
  environment gate - a state the existing "Pipeline Running" banner can't
  distinguish from "actively building" (Azure DevOps reports both as
  `inProgress` at the run level; approval-pending is a separate API).

The user wants both closed, on the real dashboard, then mirrored onto the
demo - pointing at the real, already-public GitHub data (no obfuscation
needed there) while replacing the private Azure DevOps side with
fake/demo data in the same visual shape, matching the "Come Alive"
automations already used for the mower/vacuums/irrigation.

## Existing patterns this reuses

- **`rest:` sensor, legacy platform style** (`configuration.yaml`, `sensor
  41`/`sensor 81`): `platform: rest`, `resource:`, `value_template:`,
  `scan_interval:`, `json_attributes_path:`/`json_attributes:` for extra
  fields. New sensors here follow this exact shape.
- **Aggregating template binary_sensor with a list attribute**
  (`binary_sensor.azure_pipeline_running`/`azure_pipeline_failure`):
  computes an "on"/"off" state from one or more source sensors, and builds
  a `running`/`failed` list attribute (name/build/started/url per item)
  for a card to loop over. New binary sensors here follow this same shape.
- **Conditional markdown card with `card_mod` tinting**
  (`ui-lovelace.yaml` lines 6-51): a `type: conditional` card wrapping a
  `type: markdown` card, Jinja `{% for %}` loop over the binary sensor's
  list attribute, `card_mod` for a colored background/border. New popup
  cards match this exactly (blue for "running", amber for "needs your
  approval", matching the existing blue/red running/failure convention).
- **Entities-card pipeline-info shape** ("Renovate Pipeline Info" card,
  `ui-lovelace.yaml` lines 6241-6265): 4 rows - a "what's this tracking"
  or build-number row, a build number, a date/time row, a result row. The
  new "GitHub Actions Info" card matches this: Build Number, Last Commit
  Message, Date / Time Last Build, Last Run Status.
- **"Come Alive" automation** (`demo/tools/generate_demo_entities.py` -
  mower/vacuum/irrigation): a `time_pattern`-triggered `choose:` state
  machine cycling an `input_select`-backed fake value. The demo's fake
  Azure DevOps card is driven by a new automation in this same family.
- **Secrets pattern** (`secrets.yaml`, gitignored real file / CI-safe stub
  committed with placeholder values, real values injected at deploy time):
  the new Azure DevOps PAT follows this, never committed with a real
  value.

## Scope boundary (confirmed with the user)

- **No write access anywhere.** The Azure DevOps PAT is read-only (Build +
  Approvals read). No "Approve" button. The approval-pending card links to
  the pipeline's own run history page
  (`https://dev.azure.com/example/Home/_build?definitionId=7`,
  matching the existing badge URL's `definitionId`) so a human finishes
  the approval in Azure DevOps itself, same as they do today.
- **Dashboard-only visibility.** No integration with the existing
  WhatsApp/mobile alert pipeline (`input_boolean.alerts_muted` etc.) -
  these are cards that appear/disappear on the Home view, nothing pushes
  anywhere.
- **GitHub side is identical on both dashboards.** The GitHub Actions
  Info card and the "GitHub Action Running" popup use the exact same
  public, unauthenticated API calls on prod and on demo - there is nothing
  private in a public repo's own Actions run list, so no separate demo
  variant is needed for this half.
- **Azure DevOps side is prod-only, faked on demo.** The demo's version is
  a single consolidated "Azure DevOps Pipeline Info" card (not a 1:1
  replica of prod's four separate pipeline cards - that level of detail
  doesn't add anything for a demo visitor and isn't worth the extra
  generated-entity surface) plus a fake, occasionally-toggling "waiting on
  approval" popup, both driven by a new Come Alive automation. No real
  Azure DevOps credentials or org/project names ever appear in `demo/`.

## Data sources

### 1. GitHub Actions status (prod + demo, identical)

New legacy `rest:` sensor, no auth:

```yaml
- platform: rest
  name: github_actions_latest_run
  unique_id: github_actions_latest_run
  resource: "https://api.github.com/repos/gavinwoolley/homeassistant/actions/workflows/demo-image.yml/runs?per_page=1"
  value_template: "{{ value_json.workflow_runs[0].status }}"
  scan_interval: 120
  json_attributes_path: "$.workflow_runs[0]"
  json_attributes:
    - conclusion
    - run_number
    - html_url
    - created_at
    - head_commit
```

Filtered to `demo-image.yml` specifically (not "most recent run of any
workflow") - confirmed live this filtered endpoint works
(`/actions/workflows/{filename}/runs`) and returns `status`, `conclusion`,
`run_number`, `html_url`, `created_at`, `head_commit.message`, all
unauthenticated. This is the one workflow that actually produces
something a visitor cares about (the published image), so it's the one
tracked - not gitleaks/yamllint/the other per-push checks.

`scan_interval: 120` - matches this session's existing "make the demo/
dashboard visibly do something without a long wait" bias while staying
well inside GitHub's 60/hour unauthenticated rate limit (30 polls/hour
per sensor).

New template `binary_sensor.github_action_running`:

```yaml
- name: github_action_running
  unique_id: github_action_running
  icon: mdi:github
  state: "{{ is_state('sensor.github_actions_latest_run', 'in_progress') }}"
  attributes:
    running: >-
      {% if is_state('sensor.github_actions_latest_run', 'in_progress') %}
        {{ [{
          'name': 'Publish demo image',
          'build': state_attr('sensor.github_actions_latest_run', 'run_number'),
          'started': state_attr('sensor.github_actions_latest_run', 'created_at'),
          'url': state_attr('sensor.github_actions_latest_run', 'html_url') }] }}
      {% else %}
        {{ [] }}
      {% endif %}
```

Single-item list (only one workflow tracked) built the same shape as
`azure_pipeline_running`'s `running` attribute, so the popup card's Jinja
loop is copy-paste identical in structure.

### 2. Published demo image version (prod + demo, identical)

New `rest:` sensor reading the public mirror's own already-published
devcontainer config - no GHCR API auth needed (package version listings
require a token even for public packages; this file doesn't):

```yaml
- platform: rest
  name: demo_image_published_version
  unique_id: demo_image_published_version
  resource: "https://raw.githubusercontent.com/gavinwoolley/homeassistant/main/.devcontainer/devcontainer.json"
  value_template: "{{ (value_json.image.split(':')[-1]) }}"
  scan_interval: 300
```

Same raw-file-fetch approach for the Grafana image tag from
`.devcontainer/grafana/docker-compose.codespaces.yml` (not valid JSON - a
second sensor with a regex `value_template` pulling the tag after
`homeassistant-demo-grafana:` from the raw YAML text).

### 3. Azure DevOps approval-pending (prod only)

New secret in `secrets.yaml` (committed CI-safe stub gets a placeholder;
real PAT injected at deploy time, same mechanism as the existing 4
secrets there):

```yaml
azure_devops_pat: "__REPLACE_ME__"
```

**Confirmed via Microsoft's own REST API docs** (no live test possible -
this needs a real PAT the user hasn't shared, and shouldn't need to):
`GET https://dev.azure.com/{org}/{project}/_apis/pipelines/approvals?state=pending&api-version=7.1`
returns `{"count": N, "value": [{"id", "status", "createdOn",
"lastModifiedOn", ...}]}`. The bare (non-`$expand`ed) approval object does
**not** include a pipeline/environment name or a human-browsable web URL -
only an API self-link. Since this project has exactly one
approval-gated environment (`public-mirror`, gating "Publish to Github"
specifically), the sensor doesn't need to resolve that per-approval - a
nonzero count can only mean that one pipeline, so the display name is a
fixed string and the link is the same static, already-known
`definitionId=7` pipeline-runs URL used elsewhere in this file, not
something parsed out of the response.

```yaml
- platform: rest
  name: azure_devops_pending_approvals
  unique_id: azure_devops_pending_approvals
  resource: "https://dev.azure.com/example/Home/_apis/pipelines/approvals?state=pending&api-version=7.1"
  authentication: basic
  username: ""
  password: REDACTED azure_devops_pat
  value_template: "{{ value_json.count }}"
  scan_interval: 120
  json_attributes_path: "$"
  json_attributes:
    - value
```

New template `binary_sensor.azure_devops_approval_pending`:

```yaml
- name: azure_devops_approval_pending
  unique_id: azure_devops_approval_pending
  icon: mdi:account-check
  state: "{{ states('sensor.azure_devops_pending_approvals') | int(0) > 0 }}"
  attributes:
    pending: >-
      {% set items = state_attr('sensor.azure_devops_pending_approvals', 'value') or [] %}
      {% if items %}
        {{ [{
          'name': 'Publish to Github',
          'since': items[0].createdOn,
          'url': 'https://dev.azure.com/example/Home/_build?definitionId=7' }] }}
      {% else %}
        {{ [] }}
      {% endif %}
```

**Implementation-time risk flagged explicitly:** the exact response shape
is taken from Microsoft's own current docs, not a live call (no PAT
available to this session). The `value_template`/`json_attributes_path`
above assume `count` and `value[].createdOn` exist as documented; if the
first real deploy shows the sensor come up `unavailable` or with an
unexpected shape, that's a live-data correction to make then, not a
design flaw to solve speculatively now.

## Cards

### Prod - two new conditional popups (top of Home view, same block as the existing two)

```yaml
- type: conditional
  conditions:
    - entity: binary_sensor.github_action_running
      state: "on"
  card:
    type: markdown
    title: 🔄 GitHub Action Running
    content: >-
      {% for p in state_attr('binary_sensor.github_action_running', 'running') %}
      **{{ p.name }}** — running since {{ as_timestamp(p.started) | timestamp_custom('%H:%M', true) }} · [build {{ p.build }}]({{ p.url }})
      {% endfor %}
    card_mod:
      style: |
        ha-card { background: rgba(30, 136, 229, 0.12); border: 1px solid var(--info-color, #1e88e5); }
        ha-card .card-header { color: var(--info-color, #1e88e5); }

- type: conditional
  conditions:
    - entity: binary_sensor.azure_devops_approval_pending
      state: "on"
  card:
    type: markdown
    title: ⏳ Publish to Github Waiting on Approval
    content: >-
      {% for p in state_attr('binary_sensor.azure_devops_approval_pending', 'pending') %}
      **{{ p.name }}** — waiting since {{ as_timestamp(p.since) | timestamp_custom('%H:%M', true) }} · [approve it]({{ p.url }})
      {% endfor %}
    card_mod:
      style: |
        ha-card { background: rgba(255, 160, 0, 0.15); border: 1px solid #ffa000; }
        ha-card .card-header { color: #ffa000; }
```

### Prod - new "GitHub Actions Info" entities card (Builds & Releases panel, next to the existing Renovate/Docker/HA Pipeline Info cards)

```yaml
- entities:
    - type: attribute
      entity: sensor.github_actions_latest_run
      attribute: run_number
      icon: mdi:github
      name: Build Number
    - type: template
      entity: sensor.github_actions_latest_run
      content: "{{ state_attr('sensor.github_actions_latest_run', 'head_commit').message }}"
      icon: mdi:message-text
      name: Last Commit Message
    - type: attribute
      entity: sensor.github_actions_latest_run
      attribute: created_at
      icon: mdi:calendar
      name: Date / Time Last Build
    - type: template
      entity: sensor.github_actions_latest_run
      content: "{{ state_attr('sensor.github_actions_latest_run', 'conclusion') or states('sensor.github_actions_latest_run') }}"
      icon: mdi:check-circle-outline
      name: Last Run Status
    - entity: sensor.demo_image_published_version
      icon: mdi:docker
      name: HA Demo Image Version
    - entity: sensor.demo_grafana_image_published_version
      icon: mdi:docker
      name: Grafana Demo Image Version
  show_header_toggle: false
  title: GitHub Actions Info
  type: entities
```

`head_commit` is a nested object (`{id, message, timestamp, author,
committer}`), so its message needs a `type: template` row (HA's entities
card supports this directly), not a plain `type: attribute` one, which
would just dump the whole object as text. Last Run Status also needs a
template row: `conclusion` is `null` while a run is still in progress, so
it falls back to `status` (e.g. "in_progress") in that case rather than
showing a blank field.

### Demo - GitHub Actions Info card

Identical to prod's, verbatim - same public data, no reason to differ.

### Demo - fake "Azure DevOps Pipeline Info" card + Come Alive automation

One consolidated entities card (Build Number / Commit Message / Date-Time
/ Status), backed by `input_number`/`input_text`/`input_datetime` helpers
a new `Come Alive - Azure DevOps` automation cycles on a timer, same
shape as `mower_come_alive_automation` et al. A second fake
`input_boolean` (rare on/off, matching the mower's dock-most-of-the-time
weighting) drives a demo-only `binary_sensor.demo_azure_devops_approval_pending`
and the matching amber popup card - visually identical to prod's, static
`url:` pointing nowhere meaningful (there's no real approval to grant;
matches how the demo's other fake action buttons already behave when
there's nothing real behind them).

## Files touched

- `configuration.yaml` - 3 new `rest:` sensors (GitHub Actions run,
  2× published version), 2 new template `binary_sensor`s (GitHub Action
  running, Azure DevOps approval pending).
- `secrets.yaml` - new `azure_devops_pat` key (CI-safe placeholder only).
- `ui-lovelace.yaml` - 2 new conditional popup cards (Home view), 1 new
  entities card (Builds & Releases panel).
- `demo/tools/generate_demo_entities.py` - GitHub-side entities (real
  data, same sensors as prod, no fakery needed) + fake Azure DevOps
  entities/input helpers + the new Come Alive automation.
- `demo/ui-lovelace.yaml` - mirrored cards (GitHub Actions Info identical
  to prod; fake Azure DevOps Pipeline Info card; both popups).

## Testing

- Prod: cannot be tested against the real Azure DevOps PAT/environment
  from this session (no credentials here) - the Azure DevOps approval
  sensor's exact response shape gets confirmed on first real deploy, per
  the risk note above. The GitHub Actions and published-version sensors
  *can* and will be verified against the real public API before shipping,
  same as every other REST-integration piece of work this session.
- Demo: full live verification on dev-linux, same process used for every
  other demo change this session (bring up a real container, confirm the
  new entities/automation/cards behave correctly, including at least one
  full Come Alive cycle).
