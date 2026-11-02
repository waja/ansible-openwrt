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
  readable `/etc/board.json`, and `/tmp/sysinfo/board_name`.
- The commands and BusyBox applets used by the script, including `mount`,
  `umount`, `chroot`, `find`, `comm`, `diff`, `uci`, `sysupgrade`,
  and `apk`. On installations without the required applets, install the
  OpenWrt packages `coreutils-comm` and `diffutils`. The script performs
  a command preflight before creating a report; `stat` and `fw_printenv`
  are optional.

The reference reconstruction uses the router's own board data and
factory files. It copies `/etc/board.json` and the device's
`/tmp/sysinfo/board_name` (plus `model`, when present) into the
reference so `board_name()` does not fall back to the generic board.
For `config_generate`, it mirrors the presence or absence of
`/proc/sys/net/ipv6` as an empty directory; it does not bind the live
`/proc` or expose kernel state.

The factory defaults `12_network-generate-ula` and
`14_network-generate-duid` are deliberately skipped. They generate
random first-boot values that cannot be reconstructed later. Their
current live values are recorded in `factory-generated-values.txt` and
excluded from the ordinary UCI customization diff. Consequently, this
comparison cannot identify later manual changes to either setting; review
the recorded values separately if either setting is relevant.

The script mounts a temporary overlay on `/rom`, runs
`config_generate` and the remaining factory `uci-defaults` scripts
in that reference, and compares the result with the live system. This is
a best-effort reconstruction, not a pristine copy of the router's original
factory state. Device-specific initialization and unavailable hardware can
affect the result. Errors are written to `/tmp/owrt-diff/chroot.log`. The script
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
are shared. A run refuses to start if a report directory already exists;
it never silently removes evidence from a previous or interrupted run.
The directory is created with restrictive permissions and resides in
RAM on a normal OpenWrt system. Retrieve only the files you need over
a protected connection.

After retrieving or securely preserving the report, remove it explicitly
with `sh /tmp/owrt-extra.sh -c`. This cleanup mode acquires and releases
the normal run lock, refuses a pre-existing lock, symlink, or mounted
report path, removes only `/tmp/owrt-diff/`, and exits without touching
`/tmp/ref/`. It is safe to repeat when no report exists. A normal
discovery run can then be started again. The `-c` option must be used
on its own.

A process killed with SIGKILL or a power loss can leave a stale lock.
Before removing it manually, verify that no owrt-extra.sh process is
running and inspect /proc/mounts for mounts below /tmp/ref/. Do not
remove the lock while a run is active or while reference mounts remain
in an uncertain state. If cleanup failed, the script deliberately keeps
the lock to prevent another run from reusing that reference. Once the
process and mounts are confirmed absent, remove the stale lock with
`rm -rf /tmp/owrt-extra.lock`.

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
| `-c` | Remove the existing report directory and exit. |
| | Refuses existing locks, symlinks, and mounted report paths. |
| | Removes only the report; acquires/releases its own lock. |
| `--redact-uci-diff FILE` | Print a redacted view of an existing |
| | UCI diff to stdout without changing the raw file. |
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
- `uci.diff`: normal-format difference between the UCI snapshots,
  excluding the non-reproducible random first-boot values.
- `factory-generated-values.txt`: current live ULA prefix and DHCP DUID;
  their original first-boot values cannot be recovered.
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
UCI values, command output and raw diffs can contain Wi-Fi passwords,
password hashes, API tokens, authentication headers, embedded credentials
in URLs, and private-key material. The human-readable presentation applies
best-effort masking to crypt(3) password hashes, credential-like key/value
names (including common password, passphrase, token, API-key, shared-secret,
authentication and private-key variants), Authorization/Cookie headers,
URL user-info, and PEM private-key blocks. Feed/repository diffs, APK audit
findings, and matching shell-history lines use the same display filter.
Sensitive file locations (for example account databases, SSH/Dropbear private
keys, TLS private-key directories, WireGuard keys and VPN shared secrets) are
reported by path only. Classification is based on known locations and
explicit filenames; file extensions such as `.key`, `.p12`, and `.pfx`
are not treated as sensitive globally. A file with one of those extensions
outside a known sensitive location is not automatically classified. Public
SSH keys and ordinary public certificates are not classified as private-key
material merely because they are key/certificate files. The path classifier
is explicit and best-effort; it does not inspect file contents or identify
arbitrary secrets stored under unexpected names.
Use `sh /tmp/owrt-extra.sh --is-sensitive-path RELATIVE_PATH` to check the
script's current path rules.

The filter is deliberately heuristic: it cannot identify every secret,
especially opaque values under innocuous names, arbitrary binary data,
unusual encodings, or secrets split across lines/formats it does not know.
It is a presentation filter, not a sanitization step: only selected terminal
output is masked. The report files and diagnostic logs remain raw, including
`factory.show`, `current.show`, `uci.diff`, `factory-generated-values.txt`,
`chroot.log`, `sysupgrade.log`, the APK installation logs,
`apk-audit-system.txt`, `uboot.env`, and optional host-key exports.
Treat every file under `/tmp/owrt-diff/` as confidential until individually
reviewed; do not upload the directory wholesale to CI artifacts, paste its
contents into issue or pull-request comments, or attach it to public tickets.
Even output passed through the display filter is best-effort and must be
reviewed before external sharing. The filter does not alter or sanitize
persisted evidence.

Review the report before sharing it. For an existing raw text file, use
`sh /tmp/owrt-extra.sh --redact-text FILE`; for a UCI diff,
`sh /tmp/owrt-extra.sh --redact-uci-diff /tmp/owrt-diff/uci.diff`.
Both commands write only to stdout and leave the input byte-for-byte
unchanged. Raw files such as `factory.show`, `current.show`, `uci.diff`,
`apk-audit-system.txt`, `uboot.env`, and optional host-key exports are
not automatically rewritten and remain sensitive.
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

After retrieving the evidence you need, remove the report through the
script's guarded cleanup mode, then remove the copied script:

```sh
sh /tmp/owrt-extra.sh -c
rm -f /tmp/owrt-extra.sh
```

Do not replace the guarded cleanup with a manual `rm -rf`: the `-c`
mode checks the lock and refuses symlinked or mounted report paths.

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
behavior. It is intentionally not treated as a complete router root
filesystem: packages such as `uci` may not be present in that minimal
image. The script's preflight therefore has to be validated on an
actual booted OpenWrt environment. The container does not provide a
booted device-like overlay environment.

The full mount/chroot workflow has been exercised on a booted OpenWrt
25.12.5 x86/64 QEMU system using a SquashFS `/rom` and OverlayFS
`/overlay/upper`. Factory inputs, overlay comparison, report generation,
and normal cleanup completed successfully (exit status 0). This validates
the successful execution path on that environment, not every device model
or failure path. A separate OpenWrt 25.12.6 x86/64 QEMU system with an
ext4 root filesystem was used only for a comparative APK audit; the full
discovery workflow was not run there.

The SquashFS test system's APK audit reported 18 missing
`/etc/uci-defaults` scripts, one missing `rom/note`, and one modified
`usr/bin/cmp`. The missing defaults are one-shot first-boot scripts
that had already been processed. The current `/usr/bin/cmp` resolves to
`/usr/libexec/cmp-gnu` from `diffutils`, while APK associates the path
with BusyBox. On the ext4 comparison system, the same 18 defaults and
the `cmp` finding appeared, but `/rom/note` was present. These are
observed image/system-specific audit findings, not automatically evidence
of user changes or discovery failures; review them in context. Do not
treat all APK audit findings as router customizations.

The current script does not generate the structured discovery bundle
defined by the [state discovery architecture](architecture.md).
Its report directory is a legacy collection of files, not a
schema-valid bundle. The bundle writer, generated report, and later
Ansible assessment/generation stage are separate implementation work.

[issue-52]: https://github.com/waja/ansible-openwrt/issues/52
