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
PATH="$BIN:/usr/bin:/bin" sh "$HELPER" "$TMP/success"
test "$(stat -c %a "$TMP/success")" = 700 || fail "directory mode"
test "$(stat -c %a "$TMP/success/status.txt")" = 600 || fail "status mode"
for f in fw4-ruleset nft-ruleset netifd-interfaces ip-address ip-routes ip-rules ip6-rules loaded-modules; do
 test -s "$TMP/success/$f.txt" || fail "missing snapshot $f"
 test "$(stat -c %a "$TMP/success/$f.txt")" = 600 || fail "$f mode"
done
grep -Fx "fw4-ruleset	ok	0" "$TMP/success/status.txt" >/dev/null || fail "fw4 success status"
grep -Fx "netifd-interfaces	ok	0" "$TMP/success/status.txt" >/dev/null || fail "netifd success status"
grep -Fq '"interface"' "$TMP/success/netifd-interfaces.txt" || fail "netifd output"
cat > "$BIN/nft" <<'EOF'
#!/bin/sh
echo "partial ruleset"
exit 7
EOF
PATH="$BIN:/usr/bin:/bin" sh "$HELPER" "$TMP/failure"
grep -Fx "nft-ruleset	failed	7" "$TMP/failure/status.txt" >/dev/null || fail "failure status"
grep -Fq "partial ruleset" "$TMP/failure/nft-ruleset.txt" || fail "partial output"
grep -Fx "ip-address	ok	0" "$TMP/failure/status.txt" >/dev/null || fail "later snapshot skipped"
mkdir -m 700 "$TMP/missing-bin"
cp "$BIN/ip" "$TMP/missing-bin/ip"
PATH="$TMP/missing-bin:/usr/bin:/bin" sh "$HELPER" "$TMP/missing"
grep -Fx "fw4-ruleset	unavailable	-" "$TMP/missing/status.txt" >/dev/null || fail "missing command status"
if PATH="$BIN:/usr/bin:/bin" sh "$HELPER" "$TMP/success" >/dev/null 2>&1; then fail "existing path overwritten"; fi
mkdir -m 700 "$TMP/target"
ln -s "$TMP/target" "$TMP/link"
if PATH="$BIN:/usr/bin:/bin" sh "$HELPER" "$TMP/link" >/dev/null 2>&1; then fail "symlink accepted"; fi
# A failed status append must fail collection rather than report success.
mkdir -m 700 "$TMP/status-write"
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
if OWRT_TEST_STATUS="$TMP/status-write/status.txt" PATH="$BIN:/usr/bin:/bin" sh "$HELPER" "$TMP/status-write" >/dev/null 2>&1; then
 fail "status append failure reported success"
fi

echo "All owrt-extra runtime snapshot tests passed."
