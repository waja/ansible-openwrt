# Tailscale role

The `router_tailscale` role configures the official Tailscale package on
OpenWrt 25.12. Package installation and service lifecycle remain owned by
`router_packages` and `router_base`; the standard playbook includes
Tailscale in those roles only when `router_tailscale_enabled: true`.

OpenWrt 25.12 uses APK and provides the official `tailscale` package from
its configured OpenWrt package repositories. The package provides both
`tailscaled` and the `tailscale` CLI, plus the OpenWrt init script and UCI
configuration. No third-party feed, installer script, or manually
downloaded binary is required.

## Enable Tailscale

Set the following in `host_vars/router1.yml` or a suitable group vars file:

```yaml
---
router_tailscale_enabled: true
router_tailscale_port: 41641
router_tailscale_fw_mode: nftables
router_tailscale_accept_dns: false
router_tailscale_accept_routes: true
router_tailscale_advertise_routes:
  - 192.168.1.0/24
```

The role configures the daemon's UCI settings and, when the node is already
authenticated, applies any explicitly configured node preferences through
`tailscale set`. This includes exit-node advertisement; the role does not run
an additional `tailscale up` on every playbook run. Tailscale's `set` command
updates only the supplied preferences, so unset preference variables remain
unchanged. An empty `router_tailscale_advertise_routes: []` explicitly clears
advertised routes.

When authentication or node preferences are requested, the role checks
`tailscale status --json` before changing node state. It validates the JSON
object and its string `BackendState` field, and only handles `Running`,
`NeedsLogin`, `NoState`, and `NeedsMachineAuth`. Invalid responses, unknown
states, and an unavailable daemon fail closed with an actionable error. A
`NeedsMachineAuth` state requires administrator approval in the tailnet
console before provisioning can continue.

| Variable | Default | Purpose |
| --- | --- | --- |
| `router_tailscale_enabled` | `false` | Enable Tailscale integration |
| `router_tailscale_port` | `41641` | Daemon UDP port |
| `router_tailscale_state_file` | `/etc/tailscale/tailscaled.state` | Path |
| `router_tailscale_fw_mode` | `nftables` | Firewall backend |
| `router_tailscale_auth_key` | `""` | Vault-protected enrollment key |
| `router_tailscale_cli` | `tailscale` | CLI executable; useful for test overrides |
| `router_tailscale_accept_dns` | `null` | Accept tailnet DNS |
| `router_tailscale_accept_routes` | `null` | Accept advertised routes |
| `router_tailscale_advertise_routes` | `null` | Routes to advertise |
| `router_tailscale_advertise_exit_node` | `null` | Advertise as exit node |
| `router_tailscale_hostname` | `null` | Tailscale node hostname |
| `router_tailscale_ssh` | `null` | Enable Tailscale SSH |

The daemon state is stored under `/etc/tailscale`, which is included in the
official package's preserved configuration files. Keep this state private:
it contains the node's Tailscale identity and credentials.

## Optional non-interactive authentication

Without `router_tailscale_auth_key`, the role does not run `tailscale up`
and never starts an interactive login. The daemon is installed and started
but remains unauthenticated until an operator completes enrollment.

For unattended provisioning, store an auth key in Ansible Vault. For example,
put this in an encrypted `host_vars/router1.vault.yml` file:

```yaml
---
router_tailscale_auth_key: !vault |
  $ANSIBLE_VAULT;1.1;AES256
  <encrypted-value>
```

Include the encrypted vars file through the inventory or your normal
Ansible Vault workflow. Do not put a real key in plaintext inventory,
examples, command-line extra vars, or source control. The authentication
task uses `no_log: true` so the key and command output are not exposed.

The role checks the daemon's backend state and uses the key only when the
node is not already authenticated. A second run does not re-submit the key.
If the device is awaiting administrator approval, approve it in the Tailscale
admin console before rerunning the playbook.

Use a short-lived key with the minimum required permissions. A one-time key
is sufficient for initial enrollment; use a reusable key only when your
recovery or reprovisioning process specifically requires it. Understand the
expiry and reuse settings in the Tailscale admin console, and revoke keys
that are no longer needed.

## Apply the configuration

The standard playbook installs the package, enables and starts the service,
then applies the role configuration when enabled:

```bash
ansible-playbook -i inventory.ini playbooks/site.yml \
  --limit router1 --tags router_tailscale
```

Selecting only the `router_tailscale` tag does not run its package and
base-service prerequisites. Run the standard playbook first, or include
`router_packages` and `router_base` in the same invocation.

The role is currently supported and tested against OpenWrt 25.12, which is
the release in this repository's Molecule matrix. Other OpenWrt releases
must not be assumed compatible without adding them to the supported test
matrix.
