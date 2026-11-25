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
The initial format version is `1.0`. Version `1.1` adds metadata-only
secret observations within `finding.observation`. A bundle using the
metadata-only `observation.secret` contract must declare
`format_version: "1.1"`; the schema enforces this whenever the `secret`
property is present. Format `1.0` retains its extensible observation shape,
but the reserved `secret` property is available only in `1.1`. Existing
`evidence.sensitivity` and `evidence.availability` semantics are unchanged.

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

Consumers must validate the manifest against the schema before use and
reject a bundle whose declared format version they do not support.
The schema validates structure and types; it cannot detect secrets
embedded in arbitrary strings or inspect evidence bytes. Before sharing,
the bundle writer and consumer must additionally run content-level
secret detection/redaction and review, verify that included evidence
artifacts are available at their declared locations, referenced IDs
resolve, and declared hashes match the actual included evidence bytes.
A successful schema validation alone is not a safety approval.

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
properties are intentionally extensible for ordinary findings. Secret
findings use a restricted metadata-only observation shape. Producers must
follow the category conventions below and document any additional fields
they emit:

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
| Secret-bearing setting | `secret` metadata object |

For a secret-bearing setting, `observation.secret` is a structured
metadata object. `kind` identifies the credential class, `status`
records whether the setting is known to be present or absent, and
`value_handling` is always `excluded-from-bundle` for normal bundle output.
The setting identity remains in the finding's `subject` and its
provenance in `evidence_ids`; do not copy the secret value into
`observation`, `comparison`, identifiers, descriptions or evidence
metadata. The finding itself is the bundle-local reference to the
secret-bearing setting. It is not a reference to a stored secret payload.

`secret.kind` uses these values: `wifi-psk`, `wireguard-private-key`,
`wireguard-preshared-key`, `password`, `token`, `private-key`,
`certificate-private-key`, `shared-secret`, or `other`. `secret.status`
uses `present`, `absent`, `unknown`, or `not-checked`. Use `present`
only when existing discovery evidence establishes that a value is
configured; do not read a secret solely to establish presence. Use
`unknown` when evidence exists but does not establish whether the
credential value is present or absent, and `not-checked` when no
relevant check was performed. `absent` means evidence establishes that
the credential value itself is absent; it does not mean that the UCI
option or setting is missing. It must not be inferred from missing or
inaccessible evidence. `value_handling`
uses the constant `excluded-from-bundle`: the secret value is excluded
from the normal bundle and report. This does not claim that existing raw
source evidence never contains the value; such evidence remains sensitive
and must be handled separately.

For format version `1.1`, the schema requires `observation.secret` when
a `uci`/`uci-option` finding has a recognized credential-bearing option
name as the final component of `subject.identifier`. Format `1.0` keeps
its original extensible observation fields and validation behavior.
Producers normalize option names to lowercase before validation. The
pattern accepts the documented underscore/hyphen variants (including
`sae_password`) and optional numeric suffixes.

The rule is scoped to UCI option subjects. A generic option named `key`
is deliberately not matched because it may contain a public key; names
such as `wep_key` remain recognized. Producers must add
`observation.secret` whenever other evidence establishes that a setting
contains secret material, including private-key findings.

For secret findings, the schema permits only the documented non-secret
identity metadata and the `secret` object in `observation`;
`comparison` must be omitted or null. This is structural validation
only: JSON Schema cannot determine whether arbitrary free-form strings
actually contain credentials, password hashes or secret-derived
fingerprints. A `subject.kind: key` alone does
not imply secret material: the same subject kind can represent public
keys and certificates. Producers must therefore add `observation.secret`
for private-key or other secret-bearing key findings based on the
observed material; the schema does not classify every generic key subject
as secret. Before a bundle is treated as
safe to share, a separate content-level secret scan/redaction and review
of identifiers, descriptions, evidence metadata and included evidence
bytes is mandatory. A schema-valid bundle is not, by itself, proof that
it contains no secret material.

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
  or `unknown`. Evidence containing raw credentials or other secret
  material is `secret`, not merely `sensitive`. Secret evidence must
  never have `availability: included`; use `redacted`, `omitted` or
  `unavailable` for the raw source.
- For format version `1.1`, the schema forbids SHA-256 digests for evidence
  classified `sensitive`, `secret` or `unknown`, and forbids included
  evidence classified `secret`. These additional constraints apply only
  to `1.1`; existing `1.0` evidence semantics remain unchanged. A
  separately generated, content-scanned redacted derivative is a new
  evidence artifact: classify it `internal`, set
  `availability: included`, describe the redaction, and hash only the
  exact redacted bytes. Never reuse the source evidence ID or digest.
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
sensitive content safe to publish. JSON Schema cannot inspect evidence
bytes or prove that a redacted derivative is actually clean. The separate
content-level scan and review must run before sharing; only after that
check may the derivative be classified as `internal` and receive a
digest of its redacted bytes. Never hash the original credential-bearing
source for a normal bundle.

## Secret-bearing settings: metadata-only discovery

A secret is part of the observed configuration even when its value is
excluded from the normal bundle. Discovery must therefore retain a finding
for the setting and record its identity, credential kind, presence
status, source evidence and sensitivity classification. The schema
requires `observation.secret` for recognized credential-bearing UCI
option names. Producers must also supply it for secret-bearing findings
that cannot be identified from the UCI option name alone, including
private-key findings. A generic `key` subject is not sufficient evidence
of a secret because public keys and certificates use that subject kind
too. Whenever metadata-form `observation.secret` is present, the schema
restricts the finding to metadata-only observation fields and disallows
non-null comparison data. This prevents a Wi-Fi network or WireGuard interface
from appearing fully described while silently omitting a required
credential.

This issue defines a metadata-only discovery contract. It does not define
or implement secret-value collection, a protected payload, a sidecar,
transport to the control host, encryption, a Vault/secret-manager import,
or generated Ansible secret variables. The focused follow-up work is
tracked in [#205](https://github.com/waja/ansible-openwrt/issues/205)
(secure export and transfer),
[#206](https://github.com/waja/ansible-openwrt/issues/206) (secret-backend
import), [#207](https://github.com/waja/ansible-openwrt/issues/207)
(secret-aware assessment), and
[#208](https://github.com/waja/ansible-openwrt/issues/208) (Ansible
generation using secret references).

The normal manifest and report must never contain plaintext secret
values, password hashes, tokens, private-key material, or fingerprints
or digests derived from those values. A report may say that a secret is
present and protected, but must not display it. Do not use a secret hash
as a substitute for the value: it can reveal equality across bundles or
support guessing attacks.

Raw source evidence must not be rewritten to achieve redaction. Treat
raw UCI snapshots, diffs, command output and files that may contain
credentials as sensitive; protect them with restrictive permissions and
keep them out of ordinary shareable bundle content unless they have been
safely redacted. If a raw evidence file is retained separately for
forensic traceability, it remains sensitive and is not a secret handoff
artifact. A redacted derivative is a separate presentation artifact and
must not be mistaken for the original evidence. The existing optional
`owrt-extra.sh -H` host-key export remains a separate high-risk recovery
path; it is not part of this metadata-only contract and must not be
silently folded into a normal discovery bundle.

The status distinctions are important:

- `present`: existing evidence establishes that the setting has a secret
  value, but the value itself is excluded from the normal bundle.
- `absent`: evidence establishes that the credential value itself is
  absent; the UCI option or setting may still exist, for example with an
  empty value.
- `unknown`: the available evidence cannot establish whether a value is
  present.
- `not-checked`: no relevant check was performed.

The finding `action` describes the setting's lifecycle relative to the
reference; `observation.secret.status` describes whether the credential
value is known to be present. These are independent: an existing option
may have an empty value (`action: present`, `status: absent`), or the
value may be unknown/not checked. The schema therefore does not tie these
fields together; producers must report each from its own evidence.

An inaccessible or failed read is not evidence that a secret is absent.
Record the relevant limitation and use `unknown` or `not-checked` as
appropriate. Never invent, replace, normalize or regenerate a value.

### Examples

A Wi-Fi PSK finding can document the UCI setting without including its
value in the normal bundle:

```json
{
  "id": "uci.wireless.default_radio0.key",
  "category": "uci",
  "subject": {
    "kind": "uci-option",
    "identifier": "wireless.default_radio0.key",
    "identity_stability": "stable"
  },
  "action": "present",
  "observation": {
    "config": "wireless",
    "section_name": "default_radio0",
    "option": "key",
    "secret": {
      "kind": "wifi-psk",
      "status": "present",
      "value_handling": "excluded-from-bundle"
    }
  },
  "evidence_ids": ["evidence-wireless-current"],
  "limitations": []
}
```

The example is a finding record; its evidence ID resolves to the
corresponding evidence record in the containing bundle.

A WireGuard peer uses the same structure. For a private key, use
`kind: wireguard-private-key`; for a peer preshared key, use
`kind: wireguard-preshared-key`. For example:

```json
{
  "id": "uci.network.wg0_peer1.preshared_key",
  "category": "uci",
  "subject": {
    "kind": "uci-option",
    "identifier": "network.wg0_peer1.preshared_key",
    "identity_stability": "stable"
  },
  "action": "present",
  "observation": {
    "config": "network",
    "section_name": "wg0_peer1",
    "option": "preshared_key",
    "secret": {
      "kind": "wireguard-preshared-key",
      "status": "present",
      "value_handling": "excluded-from-bundle"
    }
  },
  "evidence_ids": ["evidence-network-current"],
  "limitations": []
}
```

The finding subject identifies the interface/peer and option, while
the evidence records identify the source. No secret value or
value-derived digest appears in the manifest.

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
