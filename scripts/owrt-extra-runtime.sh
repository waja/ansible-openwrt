#!/bin/sh
# Read-only point-in-time snapshots of selected live kernel/network state.
set -u
OUT=${1:-}
[ -n "$OUT" ] || { echo "Usage: $0 OUTPUT_DIRECTORY" >&2; exit 2; }
case "$OUT" in
 /*) ;;
 *) echo "Output directory must be an absolute path: $OUT" >&2; exit 1 ;;
esac
case "$OUT" in
 */) echo "Output directory must not end with a slash: $OUT" >&2; exit 1 ;;
 */*)
  parent=${OUT%/*}
  output_name=${OUT##*/}
  [ -n "$parent" ] || parent=/
  ;;
esac
case "$output_name" in
 ""|.|..) echo "Invalid output directory name: $output_name" >&2; exit 1 ;;
esac
# Pin the parent directory as the working directory before validating it.
# All subsequent output paths are relative to this directory, so a rename or
# replacement of the original pathname cannot redirect status/snapshot writes.
cd -P "$parent" || { echo "Cannot access output parent: $parent" >&2; exit 1; }
parent_metadata=$(stat -c '%u %a' .) || {
 echo "Cannot inspect output parent directory." >&2
 exit 1
}
case "$parent_metadata" in
 *" "*)
  parent_uid=${parent_metadata%% *}
  parent_mode_text=${parent_metadata#* }
  ;;
 *) echo "Invalid output parent metadata." >&2; exit 1 ;;
esac
[ "$parent_uid" = "$(id -u)" ] || {
 echo "Output parent must be owned by the invoking user." >&2
 exit 1
}
case "$parent_mode_text" in
 ""|*[!0-7]*) echo "Invalid output parent mode." >&2; exit 1 ;;
esac
parent_mode=$((0$parent_mode_text))
[ $((parent_mode & 0022)) -eq 0 ] || {
 echo "Output parent must not be group- or world-writable." >&2
 exit 1
}
OUT=./$output_name
[ ! -e "$OUT" ] && [ ! -L "$OUT" ] || {
 echo "Refusing to overwrite existing path: $OUT" >&2
 exit 1
}
umask 077
mkdir -m 700 "$OUT" || exit 1
STATUS=$OUT/status.txt
: > "$STATUS" || exit 1
chmod 600 "$STATUS" || exit 1
snapshot() {
 name=$1; command_name=$2; shift 2; output=$OUT/$name.txt
 if ! command -v "$command_name" >/dev/null 2>&1; then
  printf '%s\t%s\t%s\n' "$name" unavailable - >> "$STATUS" || return 1
  return 0
 fi
 "$@" > "$output" 2>&1
 rc=$?
 chmod 600 "$output" || return 1
 if [ "$rc" -eq 0 ]; then
  printf '%s\t%s\t%s\n' "$name" ok "$rc" >> "$STATUS" || return 1
 else
  printf '%s\t%s\t%s\n' "$name" failed "$rc" >> "$STATUS" || return 1
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
snapshot ip6-routes ip ip -6 route show table all || exit 1
snapshot ip-rules ip ip rule show || exit 1
snapshot ip6-rules ip ip -6 rule show || exit 1
snapshot loaded-modules lsmod lsmod || exit 1
exit 0
