#!/bin/sh
# Read-only point-in-time snapshots of selected live kernel/network state.
set -u
OUT=${1:-}
[ -n "$OUT" ] || { echo "Usage: $0 OUTPUT_DIRECTORY" >&2; exit 2; }
[ ! -e "$OUT" ] && [ ! -L "$OUT" ] || { echo "Refusing to overwrite existing path: $OUT" >&2; exit 1; }
umask 077
mkdir -m 700 "$OUT" || exit 1
STATUS=$OUT/status.txt
: > "$STATUS" || exit 1
chmod 600 "$STATUS" || exit 1
snapshot() {
 name=$1; command_name=$2; shift 2; output=$OUT/$name.txt
 if ! command -v "$command_name" >/dev/null 2>&1; then
  printf '%s\t%s\t%s\n' "$name" unavailable - >> "$STATUS"
  return 0
 fi
 "$@" > "$output" 2>&1
 rc=$?
 chmod 600 "$output" || return 1
 if [ "$rc" -eq 0 ]; then
  printf '%s\t%s\t%s\n' "$name" ok "$rc" >> "$STATUS"
 else
  printf '%s\t%s\t%s\n' "$name" failed "$rc" >> "$STATUS"
 fi
 return 0
}
# fw4 print is the generated firewall configuration; nft list ruleset is
# the effective kernel ruleset, including runtime-only additions.
snapshot fw4-ruleset fw4 fw4 print || exit 1
snapshot nft-ruleset nft nft list ruleset || exit 1
# netifd/ubus state complements the live kernel view from iproute2.
snapshot netifd-interfaces ubus ubus call network.interface dump || exit 1
snapshot ip-address ip ip address show || exit 1
snapshot ip-routes ip ip route show table all || exit 1
snapshot ip-rules ip ip rule show || exit 1
snapshot loaded-modules lsmod lsmod || exit 1
exit 0
