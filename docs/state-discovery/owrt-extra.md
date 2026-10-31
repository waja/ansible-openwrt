# OpenWrt state discovery with `owrt-extra.sh`

Use `scripts/owrt-extra.sh` when you want to inspect an already
customized OpenWrt 25.12 router before bringing it under Ansible
management. The script compares the running system with a reconstructed
factory reference and reports likely configuration candidates.

The script is a read-only discovery aid, not an Ansible playbook and not
a configuration generator. It does not change the live UCI configuration,
install packages, or apply any of the reported differences. Review every
finding and decide explicitly whether it belongs in Ansible.

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
factory state. Device-specific initialization and unavailable hardware
can affect the result. Errors during reference generation are written
to `/tmp/owrt-diff/chroot.log` and reported as warnings.

## Run the discovery

Copy the script to the router and run it as root:

```sh
scp scripts/owrt-extra.sh root@router1:/tmp/owrt-extra.sh
ssh root@router1 'sh /tmp/owrt-extra.sh'
```

The report and retained evidence are written below
`/tmp/owrt-diff/`. The directory is created with restrictive
permissions and resides in RAM on a normal OpenWrt system. Retrieve only
the files you need over an appropriately protected connection.

### Options

| Option | Behavior |
| --- | --- |
| `-k` | Keep the temporary factory reference mounted at `/tmp/ref/merged` after the run so you can inspect it. Without this option, a reference built by this run is unmounted and removed. |
| `-f` | Rebuild the factory reference even if `/tmp/ref/merged` is already mounted. An existing reference is cleaned up before rebuilding. |
| `-H` | Additionally copy available Dropbear/OpenSSH host keys and the uhttpd certificate/key into `/tmp/owrt-diff/secrets/`. These files are copied in plaintext. |
| `-h` | Print the script's usage notes. |

Options can be combined, for example `-f -k` to rebuild and retain the
reference. If a reference was retained with `-k`, a later run without
`-f` reuses it; that later run does not automatically remove the
pre-existing mount.

To remove a retained reference, first ensure its child bind mounts are
unmounted, then unmount the reference and remove its temporary directory:

```sh
umount /tmp/ref/merged/dev /tmp/ref/merged/sys /tmp/ref/merged/proc
umount /tmp/ref/merged
rm -rf /tmp/ref
```

Only run the cleanup commands for mounts that exist. Do not remove
`/tmp/ref` while anything is still mounted below it. Rebooting the
router also clears these temporary RAM-backed mounts.

## Understand the report

The script prints a human-readable summary and retains selected raw
comparisons in `/tmp/owrt-diff/`. The principal sections are:

| Section | What it reports | How to interpret it |
| --- | --- | --- |
| 1. UCI diff | Sorted comparison of factory and current `uci show` output. Lines marked `<` are from the reference; `>` are from the live router. | Review the setting and its intent. Anonymous section indexes can shift when sections are inserted, so do not treat an index such as `@rule[3]` as a stable identity. |
| 2. Files for Ansible | New or changed files in the overlay that are not classified as UCI, secret, package-owned, or known generated files. It includes mode/owner information where available and a sysupgrade-list hint. | These are candidates, not confirmed configuration. Inspect file content and identify the owning service before managing them. |
| 3. Package files you modified | Package-owned files for which an `.apk-new` or `.apk-old` marker was found. | The marker indicates a package update conflict or related file change; inspect both files and determine which version should be authoritative. |
| 4. Services | Service enablement differences inferred from `/etc/rc.d` links and whiteouts. | Confirm the package and service relationship. Package installation may enable services as a side effect. |
| 5. Other symlinks and deleted files | Changed symlinks and deletions represented in the overlay. | Check whether the change is intentional and whether the target is generated or package-managed. |
| 6. Packages | Explicit APK world additions/removals, installed-package differences from the reference, and repository/feed or signing-key changes. | The world list is the useful starting point for explicitly requested packages. Installed dependencies and version differences are context, not necessarily packages to declare individually. |
| 3a. APK system audit | Output from `apk audit --system`, when the installed APK supports it. | This can identify modified package-owned system files outside protected configuration paths. It complements, rather than replaces, the overlay scan. See [issue #52](https://github.com/waja/ansible-openwrt/issues/52) for runtime validation status. |
| 7. Info only | UCI file paths, secret-related paths, account/group differences, ignored files, and sysupgrade persistence information. | This section provides context and pointers; it does not mean every listed item should be managed by Ansible. |
| 8. U-Boot environment | Saved output from `fw_printenv`, if available, and a check of shell history for `fw_setenv`. | Informational and recovery evidence only. Do not turn these values into routine Ansible tasks. |
| 9. Host keys | Files copied when `-H` is selected. | Highly sensitive recovery material. Keep it separate from ordinary discovery output. |

### Files retained in `/tmp/owrt-diff/`

Depending on available commands and discovered state, the directory can
contain:

- `factory.show` and `current.show`: sorted UCI state from the
  reconstructed reference and live router.
- `uci.diff`: the unified difference between those UCI snapshots.
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
UCI values and raw diffs can contain Wi-Fi passwords and other plaintext
credentials. The script avoids printing password hashes in its normal
summary, but that does not make the retained output safe to publish.
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
The rootfs container used in CI checks shell syntax and command-line
behavior but does not provide a booted device-like overlay environment.
The full mount/chroot workflow and detection of actual overlay changes
still need validation on a suitable OpenWrt VM or physical router.

The current script does not generate the structured discovery bundle
defined by the [state discovery architecture](architecture.md).
Its report directory is a legacy collection of files, not a
schema-valid bundle. The bundle writer, generated report, and later
Ansible assessment/generation stage are separate implementation work.
