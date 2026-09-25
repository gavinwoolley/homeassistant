# GitHub Actions + Azure DevOps Approval Visibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add GitHub Actions run status, published demo image version, and
Azure DevOps "waiting on approval" visibility to the real production Home
Assistant dashboard, then mirror the GitHub-facing half onto the demo
dashboard verbatim (same public data) plus a fake approval-pending toggle
for visual parity.

**Architecture:** New `rest:` legacy-platform sensors (GitHub's public
Actions API, a raw-file fetch for the published image tag, Azure DevOps's
Approvals API) feed new template `binary_sensor`s that aggregate into a
`name`/`build`/`started or since`/`url` list attribute, exactly matching
the shape `binary_sensor.azure_pipeline_running` already uses. New
conditional markdown cards (same `card_mod`-tinted pattern as the existing
"🔄 Azure Pipeline Running" banner) loop over those attributes. One new
entities card matches the existing "Renovate Pipeline Info" 4-row shape.
The demo mirrors the GitHub half with the exact same sensors (public data,
nothing to fake) and adds one new fake toggle for the approval popup only
- the demo's Azure-DevOps-flavored cards already exist as auto-generated
fake sensors from the existing entity-scan mechanism (discovered during
planning - see Task 6's note) and need no new work beyond that one toggle.

**Tech Stack:** Home Assistant YAML config (legacy `rest:` sensor
platform, `template:` binary_sensor, Lovelace `conditional`/`markdown`/
`entities` cards, `card_mod`), Python (`demo/tools/generate_demo_entities.py`
- the demo entity/automation generator), Azure DevOps REST API, GitHub
REST API.

**Spec:** `docs/superpowers/specs/2026-09-25-github-devops-pipeline-visibility-design.md`

## Global Constraints

- No write access to Azure DevOps anywhere - the new PAT is read-only
  (Build + Approvals read); no "Approve" action exists in this feature.
- New popups are dashboard-only - no integration with the existing
  WhatsApp/mobile alert pipeline (`input_boolean.alerts_muted` etc).
- The GitHub-facing sensors/cards are byte-for-byte identical between
  `configuration.yaml`/`ui-lovelace.yaml` (prod) and
  `demo/tools/generate_demo_entities.py`/`demo/ui-lovelace.yaml` (demo) -
  same public API, no reason to diverge.
- No real Azure DevOps org/project name, PAT, or `definitionId` ever
  appears anywhere under `demo/`.
- Every new secret goes into `secrets.yaml` as a placeholder value only
  (`"__REPLACE_ME__"`, matching the existing 4 entries there) - never a
  real value committed.
- This session has no real Azure DevOps PAT to test against - Task 3's
  approvals sensor is verified for YAML/schema correctness via HA's
  `check_config` only, not live API behavior. That gap is called out
  explicitly in Task 3, not silently skipped.
- Ship as a single PR (prod + demo together) via
  `az repos pr create --auto-complete true --delete-source-branch true --squash true`,
  branched fresh off `origin/master`, no `Co-Authored-By` trailer, never
  merged directly.

---

## Task 1: Prod - GitHub Actions status sensor

**Files:**
- Modify: `configuration.yaml` (new `sensor:` block near the existing
  `sensor 41`/`sensor 81` REST sensors, e.g. as `sensor 91:`; new
  `binary_sensor:` entry in the same block as `azure_pipeline_running`/
  `azure_pipeline_failure`, around line 863)

**Interfaces:**
- Produces: `sensor.github_actions_latest_run` (state: `status` -
  `"queued"`/`"in_progress"`/`"completed"`; attributes: `conclusion`,
  `run_number`, `html_url`, `created_at`, `head_commit` with a `.message`
  sub-field), `binary_sensor.github_action_running` (state: `on`/`off`;
  attribute `running`: list of 0 or 1 `{name, build, started, url}` dicts)
  - both consumed by Task 4's cards.

- [ ] **Step 1: Confirm the live API shape hasn't drifted**

```bash
curl -s "https://api.github.com/repos/gavinwoolley/homeassistant/actions/workflows/demo-image.yml/runs?per_page=1" | python3 -m json.tool | head -40
```

Expected: a `workflow_runs` array with one object containing `status`,
`conclusion`, `run_number`, `html_url`, `created_at`, and a `head_commit`
object with a `message` field. (Already confirmed once during
brainstorming on 2026-09-25 - this step just guards against it having
changed since.)

- [ ] **Step 2: Add the REST sensor**

In `configuration.yaml`, find the `sensor 81:` block (the `active_alerts`
REST sensor, currently ends around line 2729) and add a new block
immediately after it:

```yaml
sensor 91:
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

- [ ] **Step 3: Add the aggregating binary_sensor**

Find `binary_sensor.azure_pipeline_running`'s block in `configuration.yaml`
(starts `- name: azure_pipeline_running` around line 863, ends before the
`- sensor:` block around line 897). Add this new binary_sensor entry
immediately after it, inside the same `binary_sensor:` list:

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

- [ ] **Step 4: Validate config loads**

```bash
ssh dev-linux "docker run --rm -v /c/Code/HomeAssistant:/config:ro homeassistant/home-assistant:stable python -m homeassistant --script check_config --config /config"
```

(Adjust the bind-mount source path if running from a different checkout
location than this session used.) Expected: no errors mentioning
`github_actions_latest_run` or `github_action_running`. Pre-existing,
unrelated warnings in the real config are fine - only new errors matter
here.

- [ ] **Step 5: Commit**

```bash
git add configuration.yaml
git commit -m "feat: add GitHub Actions run status sensor"
```

---

## Task 2: Prod - published demo image version sensors

**Files:**
- Modify: `configuration.yaml` (two new REST sensors in the same
  `sensor 91:` block as Task 1)

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: `sensor.demo_image_published_version`,
  `sensor.demo_grafana_image_published_version` (both plain string state,
  e.g. `"1.0.42"`) - consumed by Task 4's entities card.

- [ ] **Step 1: Confirm both raw files are fetchable and check their exact current shape**

```bash
curl -s "https://raw.githubusercontent.com/gavinwoolley/homeassistant/main/.devcontainer/devcontainer.json" | python3 -c "import json,sys; print(json.load(sys.stdin)['image'])"
curl -s "https://raw.githubusercontent.com/gavinwoolley/homeassistant/main/.devcontainer/grafana/docker-compose.codespaces.yml" | grep "homeassistant-demo-grafana:"
```

Expected: first command prints something like
`ghcr.io/gavinwoolley/homeassistant-demo:<tag>`; second prints a line
containing `image: ghcr.io/gavinwoolley/homeassistant-demo-grafana:<tag>`.
Note the exact tag format either prints (a real semantic version once
PR 319 has actually published once, a 12-char sha until then) - both are
plain strings, the templates below don't care which.

- [ ] **Step 2: Add both REST sensors**

Append to the `sensor 91:` block from Task 1:

```yaml
  - platform: rest
    name: demo_image_published_version
    unique_id: demo_image_published_version
    resource: "https://raw.githubusercontent.com/gavinwoolley/homeassistant/main/.devcontainer/devcontainer.json"
    value_template: "{{ value_json.image.split(':')[-1] }}"
    scan_interval: 300
  - platform: rest
    name: demo_grafana_image_published_version
    unique_id: demo_grafana_image_published_version
    resource: "https://raw.githubusercontent.com/gavinwoolley/homeassistant/main/.devcontainer/grafana/docker-compose.codespaces.yml"
    value_template: >-
      {% set m = value | regex_findall('homeassistant-demo-grafana:(\S+)') %}
      {{ m[0] if m else 'unknown' }}
    scan_interval: 300
```

(`value_template` on the second sensor operates on the raw response text
via the built-in `value` variable, not `value_json` - the file is YAML,
not JSON, so there's nothing to parse as an object; a regex pull is
simpler and matches this repo's existing preference for plain text
substitution over introducing a YAML parse step for one field.)

- [ ] **Step 3: Validate config loads**

Same command as Task 1 Step 4. Expected: no new errors.

- [ ] **Step 4: Commit**

```bash
git add configuration.yaml
git commit -m "feat: add published demo image version sensors"
```

---

## Task 3: Prod - Azure DevOps approval-pending sensor (KNOWN VERIFICATION GAP)

**Files:**
- Modify: `secrets.yaml` (new key)
- Modify: `configuration.yaml` (new REST sensor in `sensor 91:` block, new
  binary_sensor next to Task 1's)

**Interfaces:**
- Produces: `sensor.azure_devops_pending_approvals` (state: pending
  count as a string; attribute `value`: raw API array),
  `binary_sensor.azure_devops_approval_pending` (state: `on`/`off`;
  attribute `pending`: list of 0 or 1 `{name, since, url}` dicts) -
  consumed by Task 4's popup card.

- [ ] **Step 1: Add the secret placeholder**

In `secrets.yaml`, add a new line alongside the existing 4 entries:

```yaml
azure_devops_pat: "__REPLACE_ME__"
```

- [ ] **Step 2: Add the REST sensor**

Append to the `sensor 91:` block:

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

- [ ] **Step 3: Add the aggregating binary_sensor**

Add immediately after Task 1's `github_action_running` entry, in the same
`binary_sensor:` list:

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

- [ ] **Step 4: Validate config loads (schema only - see gap note below)**

Same `check_config` command as Task 1 Step 4. Expected: no new errors.
This confirms the YAML/Jinja is syntactically valid and the entities get
created - it does **not** confirm the Approvals API actually returns
`count`/`value[].createdOn` as documented, since `check_config` never
makes the live HTTP call and this session has no real
`azure_devops_pat` to test one with.

**Known verification gap, explicit per the spec:** the response shape
above is taken from Microsoft's current REST API docs
(`approvalsandchecks/approvals/query`), not a live call. On first real
deploy, check `sensor.azure_devops_pending_approvals` isn't
`unavailable`/`unknown` and that the popup card renders sensibly the next
time a real approval is actually pending. If the shape is wrong, the fix
is a one-line `value_template`/`json_attributes_path` correction, not a
design change - note it in the PR description so it isn't forgotten.

- [ ] **Step 5: Commit**

```bash
git add configuration.yaml secrets.yaml
git commit -m "feat: add Azure DevOps approval-pending sensor (read-only)

Response shape taken from Microsoft's REST API docs - not live-tested,
no PAT available this session. Verify on first real deploy per the
comment in configuration.yaml."
```

---

## Task 4: Prod - dashboard cards

**Files:**
- Modify: `ui-lovelace.yaml` (two new conditional cards near line 51,
  after the existing `azure_pipeline_failure` card; one new entities card
  near line 6265, after the existing "Renovate Pipeline Info" card)

**Interfaces:**
- Consumes: `binary_sensor.github_action_running` (Task 1),
  `binary_sensor.azure_devops_approval_pending` (Task 3),
  `sensor.github_actions_latest_run` (Task 1),
  `sensor.demo_image_published_version`,
  `sensor.demo_grafana_image_published_version` (Task 2).

- [ ] **Step 1: Add the two popup cards**

In `ui-lovelace.yaml`, find the end of the `azure_pipeline_failure`
conditional card (the block closing around line 51, right before the
`Active Alerts` conditional card that starts around line 52). Insert
these two new cards there, in the same top-level `cards:` list:

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
            {% if not loop.first %}

            {% endif %}
            **{{ p.name }}** — running since {{ as_timestamp(p.started) | timestamp_custom('%H:%M', true) }} · [build {{ p.build }}]({{ p.url }})
            {% endfor %}
          card_mod:
            style: |
              ha-card {
                background: rgba(30, 136, 229, 0.12);
                border: 1px solid var(--info-color, #1e88e5);
              }
              ha-card .card-header {
                color: var(--info-color, #1e88e5);
              }
      - type: conditional
        conditions:
          - entity: binary_sensor.azure_devops_approval_pending
            state: "on"
        card:
          type: markdown
          title: ⏳ Publish to Github Waiting on Approval
          content: >-
            {% for p in state_attr('binary_sensor.azure_devops_approval_pending', 'pending') %}
            {% if not loop.first %}

            {% endif %}
            **{{ p.name }}** — waiting since {{ as_timestamp(p.since) | timestamp_custom('%H:%M', true) }} · [approve it]({{ p.url }})
            {% endfor %}
          card_mod:
            style: |
              ha-card {
                background: rgba(255, 160, 0, 0.15);
                border: 1px solid #ffa000;
              }
              ha-card .card-header {
                color: #ffa000;
              }
```

(The `{% if not loop.first %}` blank-line separator matches the existing
`azure_pipeline_running`/`azure_pipeline_failure` cards' own formatting
exactly, even though these two lists only ever hold 0 or 1 items today -
consistency with the pattern they're copied from, and it costs nothing if
either ever tracks more than one thing later.)

- [ ] **Step 2: Add the GitHub Actions Info entities card**

Find the end of the "Renovate Pipeline Info" `entities` card (closes
around line 6265, right before the `content: >-` markdown card that
starts with `{% set prs = state_attr('sensor.renovate_open_prs', 'prs') %}`
around line 6267). Insert this new card there, in the same `cards:` list:

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

- [ ] **Step 3: Validate config loads**

Same `check_config` command as Task 1 Step 4. Expected: no new errors -
in particular, no Lovelace/template syntax errors from the two new markdown
cards or the entities card.

- [ ] **Step 4: Commit**

```bash
git add ui-lovelace.yaml
git commit -m "feat: add GitHub Actions + approval-pending cards to the dashboard"
```

---

## Task 5: Demo - mirror the GitHub Actions sensors and card (real data)

**Files:**
- Modify: `demo/tools/generate_demo_entities.py` (new sensor generation +
  new automations_text component)
- Modify: `demo/ui-lovelace.yaml` (mirror Task 4's popup + entities card)
- Regenerate: `demo/generated/template.yaml` (via the script, not by hand)

**Interfaces:**
- Consumes: nothing from earlier tasks (demo/ is a separate tree).
- Produces: the same entity_ids as Task 1/2 - `sensor.github_actions_latest_run`,
  `binary_sensor.github_action_running`, `sensor.demo_image_published_version`,
  `sensor.demo_grafana_image_published_version` - inside the demo instance.

These 3 sensors are real, hand-written REST integrations, not fake
entities derived by scanning `ui-lovelace.yaml` - the generic "demo-only
additions" extras list (`for _extra in (...)`, used for things like
`sensor.irrigation_zone_1_watering_today`) exists specifically to make
the *generic name-heuristic fake-value generator* create a matching fake
sensor, which is the opposite of what's wanted here. These go directly
into `demo/configuration.yaml`'s own hand-maintained `sensor:` block
instead (confirmed present at line 105 - currently just
`- platform: time_date`, the demo's clock backing), the same file/pattern
already used for other real (non-generated) integrations like `prometheus:`
just above it. Only the aggregating `binary_sensor.github_action_running`
goes through the generator, in Step 2 below, since `binary_sensor:` under
`template:` *is* the generator's own domain (matching how
`github_action_running`'s prod counterpart lives in `configuration.yaml`'s
`template:` block too).

- [ ] **Step 1: Add the three REST sensors directly to demo/configuration.yaml**

In `demo/configuration.yaml`, extend the existing `sensor:` block (line
105) with three more list items, identical `resource:`/`value_template:`
values to Task 1 Step 2 and Task 2 Step 2 (real public data - nothing to
change for the demo):

```yaml
sensor:
  - platform: time_date
    display_options:
      - time
      - date
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
  - platform: rest
    name: demo_image_published_version
    unique_id: demo_image_published_version
    resource: "https://raw.githubusercontent.com/gavinwoolley/homeassistant/main/.devcontainer/devcontainer.json"
    value_template: "{{ value_json.image.split(':')[-1] }}"
    scan_interval: 300
  - platform: rest
    name: demo_grafana_image_published_version
    unique_id: demo_grafana_image_published_version
    resource: "https://raw.githubusercontent.com/gavinwoolley/homeassistant/main/.devcontainer/grafana/docker-compose.codespaces.yml"
    value_template: >-
      {% set m = value | regex_findall('homeassistant-demo-grafana:(\S+)') %}
      {{ m[0] if m else 'unknown' }}
    scan_interval: 300
```

- [ ] **Step 2: Add the aggregating binary_sensor via the generator**

In `demo/tools/generate_demo_entities.py`, add a new
`LINES_TEMPLATE.append(("binary_sensor", (...)))` call, same string-YAML
construction style as the other hand-written template entries in this
file (e.g. Task 6 Step 2's own binary_sensor below is built the same way -
write this one first and copy its exact construction pattern rather than
inventing a different one for the two):

```python
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
```

Verify the resulting entity_id in Step 3's output - HA derives it from
`name:`, per this file's own established convention (see the mower/
vacuum/dog entities earlier this session for the same rule), so confirm
it's actually `binary_sensor.github_action_running` (matching prod, no
`demo_` prefix, since the `name:` string itself has none) rather than
assuming the `unique_id`'s prefix carries over - it doesn't.

- [ ] **Step 3: Regenerate and validate**

```bash
python demo/tools/generate_demo_entities.py
python3 -c "
import yaml
with open('demo/generated/template.yaml') as f:
    yaml.safe_load(f)
print('template.yaml OK')
"
```

Expected: script exits 0, no new warnings; YAML parses.

- [ ] **Step 4: Mirror the popup and entities card into demo/ui-lovelace.yaml**

Same two-card/one-card content as Task 4 Steps 1-2, verbatim (same
entity_ids, since they're identical between prod and demo for this half).
Insert at the equivalent locations - find `azure_pipeline_failure`'s
matching card block and the demo's own "Renovate Pipeline Info" card
(confirmed present at demo/ui-lovelace.yaml - search for that exact title)
to anchor the insertion the same way Task 4 did for the real file. Only
the "GitHub Action Running" popup and the "GitHub Actions Info" entities
card go in here, not the approval-pending popup (that's Task 6/7, uses a
different, demo-only binary_sensor).

- [ ] **Step 5: Commit**

```bash
git add demo/tools/generate_demo_entities.py demo/ui-lovelace.yaml demo/generated/template.yaml
git commit -m "feat(demo): mirror GitHub Actions status + published version (real public data)"
```

---

## Task 6: Demo - fake Azure DevOps approval-pending toggle

**Files:**
- Modify: `demo/tools/generate_demo_entities.py` (new input_boolean + come
  alive automation + template binary_sensor)

**Interfaces:**
- Consumes: nothing.
- Produces: `binary_sensor.demo_azure_devops_approval_pending` (state:
  `on`/`off`; attribute `pending`: list of 0 or 1 `{name, since, url}`
  dicts, `url` a dead/placeholder link since there's nothing real to
  approve) - consumed by Task 7's popup card.

**Note on scope (discovered during planning, not assumed in the spec):**
the demo's *other* Azure-DevOps-flavored cards ("Home Assistant Pipeline
Info", "Docker Pipeline Info", "Renovate Pipeline Info" - confirmed
present in `demo/ui-lovelace.yaml` today) already work and already show
plausible fake data (`sensor.azure_devops_build_number` etc are already
auto-generated by the existing entity-scan mechanism, confirmed in
`demo/generated/template.yaml` - e.g. a `'1.0.' ~ (range(1,999) | random)`
fake build number, a live `now().isoformat()` fake timestamp). The spec's
"consolidated fake card" idea assumed these didn't exist yet; they do, and
already look reasonable, so this task is scoped down to just the one
genuinely new thing the demo doesn't have yet - the approval-pending
signal and its popup. No new fake Pipeline Info card is being built.

- [ ] **Step 1: Add a backing input_boolean**

Confirmed the existing helper's exact signature -
`backing_bool(name, icon="mdi:toggle-switch", initial=False)` (defined at
line 389, registers into `input_boolean_block` and returns the
entity_id) - use it directly rather than constructing the dict by hand.
Near the other `backing_bool(...)` calls in
`demo/tools/generate_demo_entities.py`, add:

```python
backing_bool("demo_azure_devops_approval_pending", icon="mdi:account-check")
```

- [ ] **Step 2: Add the template binary_sensor**

Alongside the other demo device_tracker/sensor templates in
`LINES_TEMPLATE`, add a `binary_sensor` entry:

```python
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
```

(Confirm the entity_id this actually produces - HA derives it from
`name:`, per this file's own established convention, so verify the
resulting entity_id is `binary_sensor.demo_azure_devops_approval_pending`
by checking the generated output in Step 4, not by assuming the slug.)

- [ ] **Step 3: Add a Come Alive automation to toggle it**

Same shape as `printer_come_alive_automation` (a `choose:` block flipping
one input_boolean's state occasionally, low probability per tick so it's
rare - matching the "needs occasional excitement, not constant" weighting
already used for the printer/dog). Add near the other Come Alive
automation definitions:

```python
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
```

Wire it into `automations_text` (the assembly point around line 2403)
alongside the other Come Alive automations.

- [ ] **Step 4: Regenerate and validate**

```bash
python demo/tools/generate_demo_entities.py
python3 -c "
import yaml
with open('demo/generated/template.yaml') as f:
    yaml.safe_load(f)
with open('demo/automations.yaml') as f:
    data = yaml.safe_load(f)
print(len(data), 'automations parse OK')
assert 'azure_devops_approval_come_alive' in [a['id'] for a in data]
print('new automation present')
"
```

Expected: both parse cleanly, the new automation id is present.

- [ ] **Step 5: Commit**

```bash
git add demo/tools/generate_demo_entities.py demo/generated/template.yaml demo/generated/input_boolean.yaml demo/automations.yaml
git commit -m "feat(demo): fake Azure DevOps approval-pending toggle"
```

---

## Task 7: Demo - approval-pending popup card

**Files:**
- Modify: `demo/ui-lovelace.yaml`

**Interfaces:**
- Consumes: `binary_sensor.demo_azure_devops_approval_pending` (Task 6).

- [ ] **Step 1: Add the popup card**

Same shape as Task 4's approval-pending popup, pointed at the demo's own
fake binary_sensor:

```yaml
      - type: conditional
        conditions:
          - entity: binary_sensor.demo_azure_devops_approval_pending
            state: "on"
        card:
          type: markdown
          title: ⏳ Publish to Github Waiting on Approval
          content: >-
            {% for p in state_attr('binary_sensor.demo_azure_devops_approval_pending', 'pending') %}
            {% if not loop.first %}

            {% endif %}
            **{{ p.name }}** — waiting since {{ as_timestamp(p.since) | timestamp_custom('%H:%M', true) }} · demo only, nothing to approve
            {% endfor %}
          card_mod:
            style: |
              ha-card {
                background: rgba(255, 160, 0, 0.15);
                border: 1px solid #ffa000;
              }
              ha-card .card-header {
                color: #ffa000;
              }
```

(No `[approve it](url)` link here, unlike prod's version - the content
line just says "demo only, nothing to approve" instead, so a visitor
doesn't click through to a dead `#` link expecting something real.)

- [ ] **Step 2: Validate YAML**

```bash
python3 -c "
import yaml
with open('demo/ui-lovelace.yaml') as f:
    yaml.safe_load(f)
print('demo/ui-lovelace.yaml OK')
"
```

- [ ] **Step 3: Commit**

```bash
git add demo/ui-lovelace.yaml
git commit -m "feat(demo): approval-pending popup card"
```

---

## Task 8: Full live verification (demo) + sanitizer gate + ship

**Files:** none new - verification and shipping only.

**Interfaces:** none.

- [ ] **Step 1: Sync and bring up a full demo instance on dev-linux**

```bash
ssh dev-linux "rm -rf /tmp/gh-devops-test && mkdir -p /tmp/gh-devops-test"
tar czf /tmp/gh-devops-sync.tar.gz -C /c/Code/HomeAssistant demo
scp -q /tmp/gh-devops-sync.tar.gz dev-linux:/tmp/gh-devops-test/
ssh dev-linux "cd /tmp/gh-devops-test && tar xzf gh-devops-sync.tar.gz && cd demo && docker compose -f docker-compose.demo.yml up -d"
```

Wait for readiness (poll `http://127.0.0.1:8124/` for `200`, same pattern
used throughout this session), then log in via the REST onboarding/login
flow (username `demo`, password `demo`, matching every other live check
this session already did).

- [ ] **Step 2: Verify the GitHub Actions entities are real and correct**

```bash
curl -s http://127.0.0.1:8124/api/states/sensor.github_actions_latest_run -H "Authorization: Bearer $TOKEN"
curl -s http://127.0.0.1:8124/api/states/sensor.demo_image_published_version -H "Authorization: Bearer $TOKEN"
```

Expected: real `status`/`conclusion`/`run_number`/`html_url` values
matching what a direct `curl` to the GitHub API itself returns (spot-check
against Task 1 Step 1's output) - confirming this is genuinely live public
data, not a fake/stale placeholder.

- [ ] **Step 3: Verify the approval-pending toggle actually toggles**

```bash
curl -s -X POST http://127.0.0.1:8124/api/services/input_boolean/turn_on -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"entity_id":"input_boolean.demo_azure_devops_approval_pending"}'
curl -s http://127.0.0.1:8124/api/states/binary_sensor.demo_azure_devops_approval_pending -H "Authorization: Bearer $TOKEN"
```

Expected: binary_sensor state flips to `on`, `pending` attribute has one
item with a populated `name`/`since`.

- [ ] **Step 4: Tear down the test container**

```bash
ssh dev-linux "cd /tmp/gh-devops-test/demo && docker compose -f docker-compose.demo.yml down"
ssh dev-linux "docker run --rm -v /tmp/gh-devops-test:/cleanup alpine sh -c 'rm -rf /cleanup'"
rm -f /tmp/gh-devops-sync.tar.gz
```

- [ ] **Step 5: Run the full sanitizer gate**

```bash
rm -rf /tmp/gh-devops-gate
python publish/sanitize.py --out /tmp/gh-devops-gate --report /tmp/gh-devops-gate-report.txt
```

Expected: `== All gates passed ==`. In particular, Gate B (leftover
literal scan) must not flag `homer_simpson`, the real Azure DevOps org
name, or `definitionId=7` anywhere under the sanitized `demo/` output -
if it does, Task 5/6/7 leaked something that needs fixing before this
ships, not after.

```bash
rm -rf /tmp/gh-devops-gate /tmp/gh-devops-gate-report.txt
```

- [ ] **Step 6: Push and open the PR**

```bash
git push -u origin feat/github-devops-pipeline-visibility
az repos pr create --title "feat: GitHub Actions + Azure DevOps approval visibility" \
  --description "See docs/superpowers/specs/2026-09-25-github-devops-pipeline-visibility-design.md for the full design. Known gap: the Azure DevOps approval-pending sensor's response shape is taken from Microsoft's docs, not live-tested (no PAT available this session) - verify on first real deploy." \
  --source-branch feat/github-devops-pipeline-visibility --target-branch master \
  --auto-complete true --delete-source-branch true --squash true
```
