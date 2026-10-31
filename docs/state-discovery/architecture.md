# State discovery and Ansible migration architecture

**Status:** design contract. The current discovery script does not yet
produce this bundle. It continues to write its existing files under
`/tmp/owrt-diff/`. Implementing the manifest writer and generated report
is a subsequent step; a legacy report directory is not a schema-valid
bundle.

## Responsibilities and data flow

The workflow has two deliberately separate stages:

1. **Router-side discovery** runs `scripts/owrt-extra.sh` as a read-only
   collector. It records observable differences from a reconstructed
   factory reference where available, together with raw evidence and
   detection limitations. It does not decide whether a difference is
   intentional, desirable or suitable for Ansible.
2. **Control-host assessment** consumes a validated discovery bundle and
   compares its findings with the capabilities implemented in this
   repository. It may create reviewable draft inventory variables or
   task suggestions. It never applies generated content.

The boundary matters: observations describe the device; assessments
describe how this repository could represent those observations.
Inferred purpose, ownership, intent, recommendations and Ansible
mappings must not be written into discovery findings as if they were
facts collected from the router.

## Bundle format

The machine-readable format is the input contract for future assessment
tools. Its JSON Schema is
[`schema/discovery-bundle.schema.json`](schema/discovery-bundle.schema.json).
The initial format version is `1.0`.

The bundle layout is:

```text
discovery/
  manifest.json
  evidence/
    <evidence-id>.<extension>
  report.md
```

- `manifest.json` is authoritative. It contains target metadata,
  discovery and reference status, findings, evidence records and
  detection limitations.
- `evidence/` contains raw or safely redacted source material referenced
  by the manifest. Paths are relative to the bundle root.
- `report.md` is generated from the manifest and evidence. It is a
  presentation artifact, not a second source of truth. It may be included
  in the bundle for human review, but it is never an input to any later
  processing step. Assessment tools, validators, migration generators and
  other consumers must not parse, scrape or otherwise derive data from it.
  If information is needed by a consumer, it must be represented in the
  manifest or referenced evidence.

Consumers must validate the manifest against the schema before use.
The schema validates structure and types; the bundle writer and
consumer must additionally verify that evidence paths exist, referenced
IDs resolve, and declared hashes match the actual evidence bytes.

### Versioning

The `format` field identifies the format and `format_version` uses
`major.minor`:

- Increment the major version for incompatible structural or semantic
  changes.
- Increment the minor version for backward-compatible additions.
- Consumers must reject unsupported major versions and must not silently
  reinterpret unknown semantics.

The schema is strict about the outer structure and defined records.
Category-specific observed values live in `finding.observation`, whose
properties are intentionally extensible. This flexibility must not become
an excuse for ad-hoc, inconsistent keys. Producers must follow the
category conventions below and document any additional fields they emit:

| Category | Expected observation fields (where applicable) |
| --- | --- |
| `uci` | `config`, `section_type`, `section_name`, `option`, `value` |
| `filesystem` | `path`, `object_type`, `mode`, `owner`, `group`, `size` |
| `package` | `name`, `version`, `status`, `source` |
| `service` | `name`, `enabled`, `running`, `init_script` |
| `symlink` | `path`, `target` |
| `account` | `name`, `uid`, `gid`, `shell`, `groups` |
| `feed` | `name`, `url`, `enabled` |
| `network` | `interface`, `device`, `protocol`, `addresses` |
| `firewall` | `config`, `section_type`, `section_name`, `options` |
| `runtime` | `object_type`, `name`, `state` |

These are conventions, not a claim that every field is always available.
Use explicit null/unknown values or record a limitation rather than
silently omitting a field whose absence could be misread. Do not put
assessment conclusions or inferred intent in observations. As the
collector matures, frequently used category patterns can be promoted into
schema definitions. New categories, action values, or changes to field
meaning require a schema/version review.

### Findings and stable identity

Each finding records:

- A stable identifier.
- A category and structured subject identifier.
- The observed action: added, modified, removed, present, absent or
  unknown.
- Structured observed facts, kept separate from interpretation.
- One or more references to supporting evidence.
- References to applicable detection limitations.

Finding IDs must be derived from semantic identity: the normalized
category and stable subject attributes. They must never depend on report
line numbers, traversal order, scan order, generated timestamps or
mutable array positions. The same identifiable object should therefore
receive the same finding ID across runs, even if discovery order changes.

Some objects—especially anonymous UCI sections—have no reliable
cross-run identity. The subject must explicitly mark its identity
stability as `unstable` or `unknown`; a scan-local index may be retained
as a locator, but must not be presented as a stable identity. In that
case, a cross-run deterministic finding ID cannot be promised.
Evidence IDs need only be unique within one bundle.

An empty findings list does not prove that the router has no custom
state. The manifest must also report checks that were unsupported,
incomplete, skipped or failed. Unknown and unavailable values must
remain explicit; they must not be replaced with guessed defaults.

## Evidence and sensitive data

Discovery output can contain credentials, private keys, certificates,
network identifiers and other sensitive material. The default export
policy is data-minimizing:

- Do not collect secret contents merely to prove that a secret exists.
  Prefer a path, presence marker, ownership/mode metadata or a redacted
  representation.
- Never include private keys, password hashes, tokens or plaintext
  credentials in a normal bundle. Existing opt-in host-key export remains
  a separate high-risk path and must not be silently included.
- Classify evidence as `public`, `internal`, `sensitive`, `secret`
  or `unknown`. Use `redacted` or `omitted` availability with an
  explanation when content is not included.
- Treat raw command output and diffs as sensitive until inspected.
  Redaction must happen before a bundle is shared or committed.
- A digest or fingerprint derived from secret material is itself
  sensitive: it can disclose equality or help confirm guesses. Do not
  include hashes of private keys, passwords, tokens, password hashes or
  other secret values in a normal bundle. Hash only the safely redacted
  artifact that is actually included.
- Keep bundles out of Git by default and store them with access controls
  appropriate to router configuration backups.

A SHA-256 digest identifies exact evidence bytes; it does not make
sensitive content safe to publish. A redacted artifact needs a digest
for the redacted bytes, not for the original secret.

## Human-readable report

The report is generated from the structured manifest and evidence.
It should group findings by useful topics, explain technical values
where appropriate, link findings to their structured records and
supporting evidence, and highlight uncertainty, detection gaps and
sensitive material. Regenerating it must not change the manifest or
evidence.

The report is deliberately not an input to the assessment tool or to
any other automated consumer. The generator consumes only the validated
machine-readable manifest and referenced evidence, never Markdown,
terminal output or ad-hoc shell formatting. No later stage may recover
structured data by parsing the generated report.

## Assessment categories

The control-host tool assigns each finding an assessment separate from
the discovery manifest:

- **Mapped** — an existing role and variable can represent the
  observation, subject to review of intent and applicability.
- **Partially mapped** — the repository represents only part of the
  observed state.
- **Not mapped** — no current role or variable represents it.
- **Needs manual review** — ownership, intent, safety or reproducibility
  cannot be established from the evidence.
- **Not suitable for Ansible** — ephemeral, device-specific, generated
  or otherwise inappropriate state.

Assessment output must retain finding and evidence identifiers so every
conclusion is traceable. It should identify repository capability gaps
where possible. Suggested variables, package lists and tasks are draft
artifacts only. Nothing is applied automatically.

## Custom integrations: LibreNMS example

Discovery must include custom integrations, not just standard OpenWrt
UCI settings. The repository now has an optional `router_librenms` role;
its deployment on an existing router is a useful end-to-end test case.

A LibreNMS/SNMP installation can leave evidence in several places:

- SNMP UCI configuration and service enablement.
- Installed packages and package versions.
- Custom files such as `/etc/librenms/wlInterfaces.txt`.
- Downloaded helper scripts and locally installed scripts.
- Modified package-owned files or service scripts.

Stage 1 records evidence and relationships it can establish, such as
file paths, package ownership, checksums, service links and UCI values.
It must not infer that a shell script belongs to LibreNMS solely from
its filename or directory. Stage 2 may correlate observations, but
inferred relationships must be labelled as assessments and supported
by evidence.

For example, discovery may establish that
`/etc/librenms/wlInterfaces.txt` exists, is not package-owned, has a
particular checksum and is referenced by an SNMP extend entry. It
cannot infer from those facts alone that the file should be regenerated
from `router_librenms_wireless_interfaces`. That mapping belongs to
the assessment stage and must be reviewed.

## Related work and boundaries

This architecture coordinates, but does not close or replace, these
independent work items:

- [#51 — Document the current discovery workflow and its
  limitations](https://github.com/waja/ansible-openwrt/issues/51)
- [#52 — Evaluate `apk audit --system`](
  https://github.com/waja/ansible-openwrt/issues/52)
- [#53 — Assess runtime-only state discovery](
  https://github.com/waja/ansible-openwrt/issues/53)

This workflow is not intended to clone a router's live state. Runtime
snapshots, generated files, credentials, hardware calibration data and
bootloader state must not be blindly converted into persistent Ansible
tasks.
