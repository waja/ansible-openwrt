# OWUT update-check role

The `router_owut` role runs the read-only `owut check` command and
reports whether OWUT's preflight check considers an upgrade safe to
attempt. It supports
OpenWrt 25.12 and newer only.

## Enable the check

The role is disabled by default because the `owut` package must be
installed separately. Enable it for routers where OWUT is installed:

```yaml
---
router_owut_enabled: true
```

| Variable | Default | Purpose |
| --- | --- | --- |
| `router_owut_enabled` | `false` | Run the Ansible-managed OWUT check |
| `router_owut_binary` | `/usr/bin/owut` | Path to the OWUT executable |

The role does not install OWUT or modify UCI configuration. If enabled,
it fails clearly when the router is older than OpenWrt 25.12 or the
configured executable is missing.

## Result handling

The role runs only `owut check`, without `--force`. It distinguishes:

- `up_to_date`: OWUT reports that no changes are needed.
- `update_available`: OWUT reports that it is safe to proceed with an
  upgrade. Newer package versions are considered for a subsequent firmware
  image build; no image is built and no packages are upgraded in place.
- `downgrade`: OWUT reports package downgrades. A build would require
  `--force`, which the role never supplies.
- `error`: OWUT returns a non-zero exit code.
- `unknown`: OWUT exits successfully but returns an unrecognized result.

Update availability, downgrade, tool errors, and unknown output are
reported as warnings in Ansible output. A failed remote check does not
abort the remaining configuration run. All check tasks report
`changed: false`.

The role never runs `apk upgrade`, installs packages, downloads or builds
firmware, initiates sysupgrade, reboots, or changes UCI configuration.

## Relationship with router_system

The `router_system_asu_*` variables configure the LuCI Attended
Sysupgrade client through UCI. They do not enable or disable this
Ansible-run check. The roles have separate responsibilities.
