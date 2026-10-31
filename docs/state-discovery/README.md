# OpenWrt state discovery

For a router that already has manual changes, use the read-only discovery
script `scripts/owrt-extra.sh` to compare the live system with a
reconstructed factory reference and collect likely Ansible candidates.
Copy it to the router and run it there as root on OpenWrt; it is not an
Ansible playbook.

See the [owrt-extra.sh user guide](owrt-extra.md) for prerequisites,
options, report sections, retained files, security precautions, migration
guidance, and known limitations.

```sh
scp scripts/owrt-extra.sh root@router1:/tmp/owrt-extra.sh
ssh root@router1 'sh /tmp/owrt-extra.sh'
```

The report is written to `/tmp/owrt-diff/` in RAM. Treat it as sensitive:
the terminal summary masks common password hashes and credential-named
UCI options, but raw evidence can still contain secrets. Host-key export
is opt-in (`-H`); with `-H`, private keys are copied in plaintext under
`/tmp/owrt-diff/secrets/`. A new run refuses to overwrite an existing
report. After securely retrieving what you need, remove the report with
`sh /tmp/owrt-extra.sh -c`, then remove the copied script.

Options: `-k` keeps the temporary factory reference mounted for
inspection, `-f` rebuilds that reference, `-H` exports host keys, and
`-c` explicitly removes an existing report without touching the reference
mount. Use `-c` on its own. To review an existing raw UCI diff with the
terminal redaction filter, use
`sh /tmp/owrt-extra.sh --redact-uci-diff /tmp/owrt-diff/uci.diff`.
Read the script's help (`sh /tmp/owrt-extra.sh -h`) before using these
options.

The report includes a UCI diff, overlay-file candidates, package and
service differences, and—when supported—`apk audit --system` output in
`/tmp/owrt-diff/apk-audit-system.txt`. The APK audit can detect modified
package-owned system files outside protected configuration paths, but it
does not report arbitrary untracked files; the overlay scan handles a
different set of candidates. This check requires an APK-based OpenWrt
system (25.12+) and is skipped with a warning when the command or option
is unavailable.

CI checks shell syntax and command-line behavior using the OpenWrt 25.12
rootfs image. It does not run the full discovery workflow in that
container: the rootfs image does not provide the same device-like overlay
environment as a booted OpenWrt router. The mount/chroot reconstruction
and detection of real overlay changes still need validation on a suitable
OpenWrt VM or physical router.

This is an investigative report, not an automatic Ansible generator.
Runtime state such as manually installed nftables rules, `ip` changes,
temporary `sysctl` values, loaded modules, and running processes is not
comprehensively captured. Files in the overlay may also be caches or
service state rather than configuration. Review each candidate before
managing it with Ansible. Data outside the overlay, such as calibration
data and bootloader storage, is not suitable for normal Ansible
configuration.

## Migration architecture

The two-stage discovery and Ansible assessment design, including the
machine-readable bundle contract, is documented in the
[state discovery architecture guide](architecture.md). The bundle schema
is a target format; the current script does not yet generate it.
