# OpenWrt state discovery with `owrt-extra.sh`

Use `scripts/owrt-extra.sh` when you want to inspect an already
customized OpenWrt 25.12 router before bringing it under Ansible
management. The script compares the running system with a reconstructed
factory reference and reports likely configuration candidates.

The script does not change live UCI configuration, install packages, or
apply reported differences. However, factory-generation scripts run in a
chroot and are not a security sandbox. They can still affect live state
through interfaces exposed by the kernel or device nodes. The collector
does not bind the live `/proc`, `/sys`, or `/dev` into the chroot, but
review device-specific `config_generate` and `uci-defaults` scripts for
side effects before running it. Treat discovery as read-only with respect
to the live configuration managed by the collector, not as a guarantee
that arbitrary factory scripts are side-effect free.

## Prerequisites

- An APK-based OpenWrt 25.12 system.
- Root access on the router.
- A mounted overlay at `/overlay/upper`, the factory image at `/rom`,
  and a readable `/etc/board.json`.
- The commands and utilities used by the script, including `mount`,
  `chroot`, `uci`, `sysupgrade`, and `apk`.

The reference reconstruction uses the router's own board data and
factory files. It mounts a temporary overlay on `/rom`, runs
`config_generate` and the factory `uci-defaults` scripts in that
reference, and compares the result with the live system. This is a
best-effort reconstruction, not a pristine copy of the router's original
factory state. Device-specific initialization and unavailable hardware can
affect the
result. Errors are written to `/tmp/owrt-diff/chroot.log`. The script
checks the exit status of `config_generate`, each `uci-defaults`
script, and `uci commit`; failures mark the reference as incomplete even
if later commands succeed.

## Run the discovery

Copy the script to the router and run it as root:

```sh
scp scripts/owrt-extra.sh root@router1:/tmp/owrt-extra.sh
ssh root@router1 'sh /tmp/owrt-extra.sh'
```

The report and retained evidence are written below
`/tmp/owrt-diff/`. Each run obtains a lock at `/tmp/owrt-extra.lock`;
concurrent runs are refused because the reference mount and report path
are shared. Each accepted run starts with a fresh report directory,
removing files from previous or interrupted runs. The directory is
created with restrictive permissions and resides in RAM on a normal
OpenWrt system. Retrieve only the files you need over a protected
connection.

### Options

| Option | Behavior |
| --- | --- |
| `-k` | Keep the temporary reference mounted after the run. |
| | Path: `/tmp/ref/merged`. |
| | Otherwise, a reference built by this run is removed. |
| `-f` | Rebuild the factory reference, even if one is mounted. |
| | An existing reference is cleaned up before rebuilding. |
| `-H` | Export available Dropbear/OpenSSH host keys and the |
| | uhttpd certificate/key to `/tmp/owrt-diff/secrets/`. |
| | These files are copied in plaintext. |
| `-h` | Print the script's usage notes. |

Options can be combined, for example `-f -k` to rebuild and retain the
reference. If a reference was retained with `-k`, a later run without
`-f` reuses it; that later run does not automatically remove the
pre-existing mount.

To remove a retained reference, unmount its child mounts and then the
reference. Stop if any unmount fails; do not run the removal command
unless every unmount succeeded and no mount remains below `/tmp/ref`:

```sh
umount /tmp/ref/merged/dev &&
umount /tmp/ref/merged/sys &&
umount /tmp/ref/merged/proc &&
umount /tmp/ref/merged &&
! grep -F ' /tmp/ref/' /proc/mounts &&
rm -rf /tmp/ref
```

If a path is not mounted, omit its `umount` command. If any unmount
fails or the mount check finds a remaining mount, stop and investigate;
never use recursive removal while a child mount remains. Rebooting the
router also clears temporary RAM-backed mounts.

## Understand the report

The script prints a human-readable summary and retains selected raw
comparisons in `/tmp/owrt-diff/`. The principal sections are:

| Section | What it reports and how to interpret it |
| --- | --- |
| 1. UCI diff | Sorted comparison of factory and current `uci show` output. |
| | Lines marked `<` are from the reference; `>` are from live. |
| | Review intent; anonymous section indexes can shift. |
| 2. Files for Ansible | New or changed overlay files not classified as UCI, |
| | secret, package-owned, or known generated files. Mode/owner |
| | and sysupgrade-list hints are included where available. |
| | Candidates only; inspect content and identify the owner. |
| 3. Package files | Package-owned files with an `.apk-new` or `.apk-old` |
| | marker. Inspect both versions and decide which is authoritative. |
| 4. Services | Enablement differences inferred from `/etc/rc.d` links |
| | and whiteouts. Package installation may enable services too. |
| 5. Symlinks/deletions | Changed symlinks and deletions in the overlay. |
| | Check intent and whether the target is generated or package-managed. |
| 6. Packages | APK world additions/removals, installed-package |
| | differences, and repository/feed or signing-key changes. |
| | The world list is the starting point for explicitly requested |
| | packages; dependencies and version differences are context. |
| 3a. APK audit | Output from `apk audit --system`, if supported. |
| | Finds modified package-owned files outside protected paths. |
| | Complements the overlay scan. See [issue #52][issue-52]. |
| 7. Info only | UCI/secret paths, account/group differences, ignored |
| | files, and sysupgrade persistence information. Context only; |
| | not every item belongs in Ansible. |
| 8. U-Boot | `fw_printenv` output and shell-history check for |
| | `fw_setenv`. Recovery evidence only; not routine Ansible state. |
| 9. Host keys | Files copied with `-H`. Highly sensitive recovery |
| | material; keep it separate from ordinary discovery output. |

### Files retained in `/tmp/owrt-diff/`

Depending on available commands and discovered state, the directory can
contain:

- `factory.show` and `current.show`: sorted UCI state from the
  reconstructed reference and live router.
- `uci.diff`: normal-format difference between the UCI snapshots.
- `packages.yml`: a starting list of package additions and removals.
  Its variable names are generic placeholders, not variables consumed
  directly by this project's roles.
- `installed.factory` and `installed.now`: installed package lists
  when both comparisons are available.
- `sysupgrade.list`: paths reported by `sysupgrade -l`.
- `apk-audit-system.txt`: raw APK system-audit output when supported.
- `uboot.env`: U-Boot environment output when `fw_printenv` succeeds.
- `chroot.log`: output from factory-reference generation.
- `secrets/`: host keys and certificates only when `-H` is used.

Some intermediate files are deliberately stored in a temporary directory
and removed when the script exits. Files above are evidence to review,
not a complete machine-readable export or an automatically applicable
Ansible configuration.

## Review findings and migrate deliberately

Work through the report by category rather than copying every difference
into inventory:

1. Confirm that the difference is intentional and still required.
2. Identify whether it is persistent configuration, package state,
   generated data, runtime state, or device-specific data.
3. Find the role and variable that own that configuration in this
   repository. Check the role guide and defaults before proposing new
   variables or tasks.
4. Add only the desired state to inventory or a focused role change.
5. Test the change on a non-production router and verify idempotence
   before applying it to a production device.

The report does not know the purpose of a file or whether a setting is
still needed. A difference from the reconstructed factory reference is
not, by itself, a recommendation to preserve that difference.

### UCI differences are not Ansible tasks

Translating `uci.diff` into `community.openwrt.uci` operations is
manual. Review the complete section and its relationships before
writing tasks:

- List options may require several ordered values. Do not assume that
  a textual diff represents the intended list operation.
- Anonymous sections are addressed by positional indexes in UCI output.
  Inserting or removing a section can change later indexes.
- Section and option ordering in a sorted text diff is not necessarily
  the order in which UCI operations should be applied.
- Deletions need explicit handling. Omitting an option from an Ansible
  variable does not necessarily remove it from an existing router.
- A factory difference may be a device default, a package side effect,
  or a generated value rather than an intentional customization.

Use the relevant role's documented variables where they express the
desired state. If the repository has no suitable role or variable, treat
that as a capability gap for a separate, reviewed change. Do not paste
raw diff lines into a playbook or assume that `packages.yml` is ready
to use without adapting its variable names and validating the package
list.

### Overlay files may be generated state

The overlay scan can find caches, counters, logs, Munin data, and other
service-generated files alongside genuine configuration. It cannot
reliably infer a file's purpose or ownership intent.

The `[NOT in sysupgrade -l]` marker means that the path was not
reported by the current `sysupgrade -l` command. It is a persistence
clue, not proof that the file is disposable or should be copied into
Ansible. Likewise, `[in sysupgrade -l]` does not prove that a file is
appropriate to manage as configuration.

Inspect each candidate, identify the owning package/service, and consult
its documentation. Prefer managing the setting through UCI or the
service's supported configuration interface rather than copying generated
files. Keep only files that are genuinely required, reproducible, and
appropriate to manage as desired state.

### Runtime-only state needs separate inspection

The script primarily discovers persistent configuration and filesystem
differences. It does not comprehensively capture changes made directly
to the running kernel or network stack. Examples include manually added
nftables rules, IP addresses and routes, policy-routing rules,
`sysctl -w` changes, loaded kernel modules, and manually started
processes.

For a manual, read-only snapshot, collect the relevant state separately:

```sh
nft list ruleset
ip address show
ip route show table all
ip rule show
sysctl -a
lsmod
ps w
```

Compare these observations with persistent configuration and service
state, for example firewall UCI configuration, `/etc/config/network`,
and the services that are enabled. A snapshot shows what is active now;
it does not establish how the state was created, whether it is intended,
or whether it will survive a reboot. Do not replay runtime output as
Ansible tasks. Any persistent change must be designed and reviewed
explicitly. Runtime discovery is tracked separately in
[issue #53](https://github.com/waja/ansible-openwrt/issues/53).

### Flash and hardware data are not normal Ansible state

Calibration data, device MAC addresses, and bootloader contents may live
outside the writable overlay and are not ordinary router configuration.
The script's U-Boot output and any related history are informational
evidence for investigation or recovery. They must not be copied to other
devices or routinely applied through Ansible. Hardware-specific recovery
must follow the device manufacturer's or OpenWrt device-page procedure;
preserve backups separately and verify that they belong to the exact
device before any recovery operation.

## Security and cleanup

Treat the entire report as sensitive until you have reviewed it.
UCI values and raw diffs can contain Wi-Fi passwords, password hashes,
and other plaintext credentials. The terminal summary redacts common
crypt(3) password hashes in UCI differences and masks the password field
in `/etc/passwd` comparisons. Raw files such as `factory.show`,
`current.show`, and `uci.diff` are not redacted and remain sensitive.
Do not commit raw discovery output, attach it to public issues, or store
it in an unprotected shared location.

The `-H` option is especially sensitive. It copies private Dropbear
and OpenSSH host keys, where present, as well as the uhttpd certificate
and key. Private keys are copied in plaintext under
`/tmp/owrt-diff/secrets/`. Use this option only when you have a
specific recovery need. Retrieve the files over a protected channel,
store them encrypted (for example with Ansible Vault), restrict access,
and remove temporary copies promptly. Restoring host keys should be
done deliberately: install them at their original paths with restrictive
permissions before the relevant service starts for the first time, or
restart that service afterwards.

After retrieving the evidence you need, remove the report and copied
script from the router:

```sh
rm -rf /tmp/owrt-diff
rm -f /tmp/owrt-extra.sh
```

If you used `-k`, clean up the retained reference mount as described
in the options section before removing `/tmp/ref`. Rebooting also clears
temporary RAM-backed files and mounts. Verify that any evidence retained
off-device is stored securely and delete it when it is no longer needed.

## Limitations and test status

The reconstructed reference is a best-effort approximation of factory
state, not a guaranteed exact representation of the original device.
Factory scripts run without live `/proc`, `/sys`, and `/dev` bind
mounts, but the chroot is not a security boundary.
The rootfs container used in CI checks shell syntax and command-line
behavior but does not provide a booted device-like overlay environment.
The full mount/chroot workflow and detection of actual overlay changes
still need validation on a suitable OpenWrt VM or physical router.

The current script does not generate the structured discovery bundle
defined by the [state discovery architecture](architecture.md).
Its report directory is a legacy collection of files, not a
schema-valid bundle. The bundle writer, generated report, and later
Ansible assessment/generation stage are separate implementation work.

[issue-52]: https://github.com/waja/ansible-openwrt/issues/52
