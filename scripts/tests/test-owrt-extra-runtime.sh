#!/bin/sh
set -eu
HELPER=${1:?usage: test-owrt-extra-runtime.sh HELPER}
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
BIN=$TMP/bin
mkdir -m 700 "$BIN"
fail() { echo "FAIL: $*" >&2; exit 1; }
cat > "$BIN/fw4" <<'EOF'
#!/bin/sh
[ "$1" = print ] || exit 9
echo "table inet fw4"
EOF
cat > "$BIN/nft" <<'EOF'
#!/bin/sh
[ "$1" = list ] && [ "$2" = ruleset ] || exit 9
echo "table inet fixture"
EOF
cat > "$BIN/ubus" <<'EOF'
#!/bin/sh
[ "$1" = call ] && [ "$2" = network.interface ] && [ "$3" = dump ] || exit 9
echo '{"interface":[{"interface":"lan","up":true}]}'
EOF
cat > "$BIN/ip" <<'EOF'
#!/bin/sh
case "$*" in
 "address show") echo "lo: <LOOPBACK>" ;;
 "route show table all") echo "default dev eth0" ;;
 "-6 route show table all") echo "default dev eth0" ;;
 "rule show") echo "0: from all lookup local" ;;
 "-6 rule show") echo "0: from all lookup local" ;;
 *) exit 8 ;;
esac
EOF
cat > "$BIN/lsmod" <<'EOF'
#!/bin/sh
echo "fixture_module 123 0"
EOF
chmod 700 "$BIN/"*
mkdir -m 700 "$TMP/untrusted-parent"
chmod 777 "$TMP/untrusted-parent"
if PATH="$BIN:/usr/bin:/bin" sh "$HELPER" \
 "$TMP/untrusted-parent/rejected" >/dev/null 2>&1; then
 fail "group/world-writable output parent accepted"
fi
PATH="$BIN:/usr/bin:/bin" sh "$HELPER" "$TMP/success"
test "$(stat -c %a "$TMP/success")" = 700 || fail "directory mode"
test "$(stat -c %a "$TMP/success/status.txt")" = 600 || fail "status mode"
for f in fw4-ruleset nft-ruleset netifd-interfaces ip-address \
 ip-routes ip6-routes ip-rules ip6-rules loaded-modules; do
 test -s "$TMP/success/$f.txt" || fail "missing snapshot $f"
 test "$(stat -c %a "$TMP/success/$f.txt")" = 600 || fail "$f mode"
done
grep -Fx "fw4-ruleset	ok	0" "$TMP/success/status.txt" \
 >/dev/null || fail "fw4 success status"
grep -Fx "netifd-interfaces	ok	0" "$TMP/success/status.txt" \
 >/dev/null || fail "netifd success status"
grep -Fq '"interface"' "$TMP/success/netifd-interfaces.txt" \
 || fail "netifd output"
cat > "$BIN/nft" <<'EOF'
#!/bin/sh
echo "partial ruleset"
exit 7
EOF
PATH="$BIN:/usr/bin:/bin" sh "$HELPER" "$TMP/failure"
grep -Fx "nft-ruleset	failed	7" "$TMP/failure/status.txt" \
 >/dev/null || fail "failure status"
grep -Fq "partial ruleset" "$TMP/failure/nft-ruleset.txt" \
 || fail "partial output"
grep -Fx "ip-address	ok	0" "$TMP/failure/status.txt" \
 >/dev/null || fail "later snapshot skipped"
mkdir -m 700 "$TMP/no-stat-bin"
if PATH="$TMP/no-stat-bin" /bin/sh "$HELPER" \
 "$TMP/no-stat" >"$TMP/no-stat.log" 2>&1; then
 fail "missing stat accepted"
fi
grep -F "stat is required to inspect the output parent." \
 "$TMP/no-stat.log" >/dev/null ||
 fail "missing stat error not reported"
mkdir -m 700 "$TMP/missing-bin"
cp "$BIN/ip" "$TMP/missing-bin/ip"
for tool in stat id mkdir chmod; do
 tool_path=$(command -v "$tool") || fail "missing test prerequisite: $tool"
 ln -s "$tool_path" "$TMP/missing-bin/$tool"
done
PATH="$TMP/missing-bin" /bin/sh "$HELPER" "$TMP/missing"
for name in fw4-ruleset nft-ruleset netifd-interfaces loaded-modules; do
 grep -Fx "$name	unavailable	-" "$TMP/missing/status.txt" \
  >/dev/null || fail "missing command status: $name"
done
printf 'sentinel\n' > "$TMP/success/sentinel"
if PATH="$BIN:/usr/bin:/bin" sh "$HELPER" "$TMP/success" \
 >/dev/null 2>&1; then
 fail "existing path overwritten"
fi
test "$(cat "$TMP/success/sentinel")" = sentinel || \
 fail "existing output directory was modified"
mkdir -m 700 "$TMP/target"
printf 'symlink sentinel\n' > "$TMP/target/sentinel"
ln -s "$TMP/target" "$TMP/link"
if PATH="$BIN:/usr/bin:/bin" sh "$HELPER" "$TMP/link" \
 >/dev/null 2>&1; then
 fail "symlink accepted"
fi
test -L "$TMP/link" || fail "symlink was replaced"
test "$(cat "$TMP/target/sentinel")" = "symlink sentinel" || \
 fail "symlink target was modified"

# A single snapshot must not fill the router's RAM-backed /tmp.
cat > "$BIN/fw4" <<'EOF'
#!/bin/sh
dd if=/dev/zero bs=65536 count=32 2>/dev/null
EOF
PATH="$BIN:/usr/bin:/bin" sh "$HELPER" "$TMP/oversized"
test "$(wc -c < "$TMP/oversized/fw4-ruleset.txt")" -le 1048576 || \
 fail "snapshot exceeded 1 MiB"
grep -E '^fw4-ruleset[[:space:]]failed[[:space:]][0-9]+$' \
 "$TMP/oversized/status.txt" >/dev/null || \
 fail "oversized snapshot not reported as failed"
grep -Fx "ip-address	ok	0" "$TMP/oversized/status.txt" \
 >/dev/null || fail "later snapshot skipped after output limit"

# A failed status append must fail collection rather than report success.
cat > "$BIN/ip" <<'EOF'
#!/bin/sh
case "$*" in
 "address show") echo "lo: <LOOPBACK>" ;;
 "route show table all") echo "default dev eth0" ;;
 "rule show") echo "0: from all lookup local" ;;
 "-6 rule show")
  echo "0: from all lookup local"
  rm -f "$OWRT_TEST_STATUS"
  mkdir "$OWRT_TEST_STATUS"
  ;;
 *) exit 8 ;;
esac
EOF
chmod 700 "$BIN/ip"
if OWRT_TEST_STATUS="$TMP/status-write/status.txt" \
 PATH="$BIN:/usr/bin:/bin" sh "$HELPER" "$TMP/status-write" \
 >/dev/null 2>&1; then
 status_rc=0
else
 status_rc=$?
fi
test -d "$TMP/status-write/status.txt" || \
 fail "ip fixture did not replace status file"
[ "$status_rc" -ne 0 ] || fail "status append failure reported success"

echo "All owrt-extra runtime snapshot tests passed."
