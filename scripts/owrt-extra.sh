#!/bin/sh
# owrt-extra.sh - Rebuild the factory state, diff UCI, and find everything in
# the overlay that needs to go into Ansible besides the UCI changes.
# Runs under BusyBox ash on OpenWrt (apk, 25.x), as root.
#
# Steps:
#   0. Build a throwaway overlay on top of /rom (/tmp/ref), run config_generate
#      and the uci-defaults there with this device's board.json -> "factory state"
#   1. UCI diff (sorted "uci show"), factory vs. current
#   2.-9. Classify overlay files (Ansible candidates, package files, services,
#      packages, sysupgrade tagging, U-Boot env, optional host-key dump)
#   The throwaway overlay is torn down afterwards.
#
# Options:
#   -k   Keep the throwaway overlay after the run (/tmp/ref/merged)
#   -f   Rebuild the throwaway overlay even if one is already mounted
#   -H   Copy host keys (dropbear, openssh if present, uhttpd certificate)
#        to /tmp/owrt-diff/secrets/ (plaintext!)
#   -c   Remove the previous report in /tmp/owrt-diff, then exit
#   --redact-uci-diff FILE  Print a redacted copy of an existing UCI diff
#   -h   Show this help
#
# Runs are serialized with /tmp/owrt-extra.lock. A new run refuses to
# overwrite an existing /tmp/owrt-diff report; use -c to remove it explicitly.
# Factory scripts run in a chroot without live /proc, /sys or /dev bind mounts;
# inspect local scripts for other side effects. Raw data can contain plaintext
# secrets. Keep it private and delete it when you are done.

# Redact the display copy only. Raw snapshots and uci.diff remain intact.
redact_uci_diff() {
    sed -E 's/\$[0-9A-Za-z]+\$[^ "'"'"';]*/[REDACTED PASSWORD HASH]/g' "$1" |
        awk '
            {
                eq = index($0, "=")
                if (!eq) {
                    print
                    next
                }
                option = substr($0, 1, eq - 1)
                sub(/^.*\./, "", option)
                option = tolower(option)
                suffix = "password|passwd|passphrase|secret|psk|" \
                    "preshared[-_]key|presharedkey|private[-_]key|" \
                    "privatekey|privkey|secret[-_]key|client[-_]key|" \
                    "encryption[-_]key|signing[-_]key|shared[-_]key|" \
                    "auth[-_]key|api[-_]key|access[-_]token|token"
                if (option == "key" || option == "wep_key" ||
                    option == "psk" || option == "preshared_key" ||
                    option == "preshared-key" || option == "presharedkey" ||
                    option == "private_key" || option == "private-key" ||
                    option == "privatekey" || option == "privkey" || \
                    option == "secret_key" || option == "secret-key" || \
                    option == "client_key" || option == "client-key" || \
                    option == "encryption_key" || option == "encryption-key" || \
                    option == "signing_key" || option == "signing-key" || \
                    option == "shared_key" || option == "shared-key" || \
                    option == "password" || option == "passwd" ||
                    option == "passphrase" || option == "secret" ||
                    option == "shared_secret" || option == "auth_key" ||
                    option == "api_key" || option == "access_token" ||
                    option == "token" || option ~ ("[-_](" suffix ")$")) {
                    print substr($0, 1, eq) "\047[REDACTED]\047"
                } else {
                    print
                }
            }
        '
}

# This read-only mode is also useful for safely reviewing an existing raw diff.
if [ "${1:-}" = "--redact-uci-diff" ]; then
    [ "$#" = 2 ] || {
        echo "Usage: $0 --redact-uci-diff FILE" >&2
        exit 1
    }
    redact_uci_diff "$2"
    exit $?
fi

KEEP=0
FORCE=0
HOSTKEYS=0
CLEAN=0
for a in "$@"; do
    case "$a" in
        -k) KEEP=1 ;;
        -f) FORCE=1 ;;
        -H) HOSTKEYS=1 ;;
        -c) CLEAN=1 ;;
        -h|--help) sed -n '2,/^$/p' "$0"; exit 0 ;;
        *) echo "Unknown option: $a (allowed: -k -f -H -c -h)" >&2; exit 1 ;;
    esac
done

[ "$(id -u)" = 0 ] || { echo "Please run as root." >&2; exit 1; }
if [ "$CLEAN" = 1 ] && {
    [ "$KEEP" = 1 ] || [ "$FORCE" = 1 ] || [ "$HOSTKEYS" = 1 ];
}; then
    echo "Option -c must be used on its own." >&2
    exit 1
fi

UPPER=/overlay/upper
R=/tmp/ref
REF=$R/merged
OUT=/tmp/owrt-diff
LOCK=/tmp/owrt-extra.lock
BUILT=0
REF_READY=0
LOCK_KEEP=0

umask 077

# Serialize access to the shared reference mount and report directory.
if ! mkdir "$LOCK" 2>/dev/null; then
    echo "Another owrt-extra.sh run may be active (lock: $LOCK)." >&2
    echo "Check for an active run and inspect reference mounts before removing a stale lock." >&2
    exit 1
fi
# Install a minimal trap immediately so prerequisite failures cannot orphan
# the lock. The full cleanup trap below replaces this on normal startup.
trap 'rm -rf "$LOCK"' EXIT
trap 'exit 1' HUP INT TERM

is_mounted() { grep -Fq " $1 " /proc/mounts; }

# Cleanup is deliberately report-only. It never touches /tmp/ref or the
# lock directory, and refuses symlinks and mounted report paths.
if [ "$CLEAN" = 1 ]; then
    if [ -L "$OUT" ]; then
        echo "Refusing to clean symlink $OUT." >&2
        exit 1
    fi
    if [ -e "$OUT" ]; then
        [ -d "$OUT" ] || { echo "$OUT exists but is not a directory." >&2; exit 1; }
        if grep -Fq " $OUT " /proc/mounts ||
           grep -Fq " $OUT/" /proc/mounts; then
            echo "Refusing to clean mounted path $OUT." >&2
            exit 1
        fi
        rm -rf "$OUT" || { echo "Could not remove $OUT." >&2; exit 1; }
        echo "Removed report directory $OUT."
    else
        echo "No report directory to remove."
    fi
    exit 0
fi

# Never discard evidence from a previous or interrupted run.
if [ -e "$OUT" ] || [ -L "$OUT" ]; then
    echo "Report directory already exists: $OUT" >&2
    echo "Review or retrieve it, then remove it explicitly with: $0 -c" >&2
    exit 1
fi

[ -d "$UPPER" ] || { echo "$UPPER not found (no overlay?)" >&2; exit 1; }
[ -d /rom ]     || { echo "/rom not found, cannot rebuild the factory state." >&2; exit 1; }
[ -r /etc/board.json ] || { echo "/etc/board.json is missing." >&2; exit 1; }

T=$(mktemp -d) || exit 1
mkdir -m 700 "$OUT" || { rm -rf "$T"; exit 1; }

# Tear down $R. Only deletes if nothing is mounted below it anymore, otherwise
# rm -rf could follow a leftover bind mount into /dev, /proc or /sys.
cleanup_ref() {
    for m in dev sys proc; do
        if is_mounted "$R/merged/$m"; then
            umount "$R/merged/$m" || {
                echo "WARNING: cannot unmount $R/merged/$m; keeping $R." >&2
                return 1
            }
        fi
    done
    if is_mounted "$REF"; then
        umount "$REF" || {
            echo "WARNING: cannot unmount $REF; keeping $R." >&2
            return 1
        }
    fi
    if grep -Fq " $R/" /proc/mounts; then
        echo "WARNING: mounts remain below $R; deleting nothing." >&2
        return 1
    fi
    rm -rf "$R"
}

finish() {
    rm -rf "$T"
    lock_release=1
    [ "$LOCK_KEEP" = 1 ] && lock_release=0
    if [ "$BUILT" = 1 ] && { [ "$KEEP" = 0 ] || [ "$REF_READY" = 0 ]; }; then
        cleanup_ref || {
            echo "WARNING: reference cleanup incomplete; keeping lock $LOCK." >&2
            lock_release=0
        }
    fi
    # Keep the lock if mounts could not be cleaned up. This prevents a later
    # run from reusing or deleting a reference with unknown mount state.
    [ "$lock_release" = 1 ] && rm -rf "$LOCK"
}
trap finish EXIT
trap 'exit 1' HUP INT TERM

build_ref() {
    BUILT=1
    mkdir -p "$R/upper" "$R/work" "$R/merged" || return 1
    mount -t overlay overlay \
        -o "lowerdir=/rom,upperdir=$R/upper,workdir=$R/work" "$REF" || return 1

    mkdir -p "$REF/etc"
    cp /etc/board.json "$REF/etc/board.json"

    # Do not expose the live kernel or device interfaces to factory scripts.
    # The chroot is not a security sandbox: review device-specific scripts.
    # Each command runs separately so one failure cannot be hidden by a
    # later successful uci-defaults script.
    # shellcheck disable=SC2016
    chroot "$REF" /bin/sh -c '
        failed=0
        /bin/config_generate
        rc=$?
        if [ "$rc" -ne 0 ]; then
            echo "FAIL: /bin/config_generate (exit $rc)"
            failed=1
        fi
        for f in /etc/uci-defaults/*; do
            [ -f "$f" ] || continue
            (
                . "$f"
            )
            rc=$?
            if [ "$rc" -ne 0 ]; then
                echo "FAIL: $f (exit $rc)"
                failed=1
            else
                rm -f "$f"
            fi
        done
        uci commit
        rc=$?
        if [ "$rc" -ne 0 ]; then
            echo "FAIL: uci commit (exit $rc)"
            failed=1
        fi
        exit "$failed"
    ' > "$OUT/chroot.log" 2>&1
    rc=$?
    if [ "$rc" -ne 0 ]; then
        echo "WARNING: factory generation was incomplete (exit $rc)." >&2
        echo "Review failed commands in $OUT/chroot.log" >&2
        return 1
    fi
    return 0
}

# --- Step 0: provide the reference ----------------------------------------
if is_mounted "$REF" && [ "$FORCE" = 0 ]; then
    REF_READY=1
    echo "Using existing reference overlay $REF (use -f to rebuild)." >&2
else
    if [ -e "$R" ]; then
        cleanup_ref || { LOCK_KEEP=1; exit 1; }
    fi
    echo "Building factory state under $REF ..." >&2
    build_ref || { echo "Failed to build the reference overlay." >&2; exit 1; }
    REF_READY=1
fi

# Files OpenWrt itself treats as user configuration (kept by sysupgrade)
sysupgrade -l 2>/dev/null | sort -u > "$T/keep"

print_section() { printf '\n##### %s\n' "$1"; }

# --- Step 1: UCI diff -----------------------------------------------------
print_section "1. UCI diff ('<' = factory, '>' = current)"
uci -q -c "$REF/etc/config" show 2>/dev/null | sort > "$OUT/factory.show"
uci -q show 2>/dev/null | sort > "$OUT/current.show"
diff "$OUT/factory.show" "$OUT/current.show" > "$OUT/uci.diff"
if [ -s "$OUT/uci.diff" ]; then
    # Keep raw evidence unchanged; redact hashes and credential-valued UCI
    # options only in the human-readable terminal summary.
    redact_uci_diff "$OUT/uci.diff"
else
    echo "(no differences)"
fi
echo "Note: anonymous sections (@rule[3] etc.) are numbered; inserting one shifts"
echo "all following indexes in the diff."

# --- Step 2: classify overlay files ---------------------------------------
rel() { sed "s|^$UPPER/||"; }

# Tag whether sysupgrade -l would keep the file (empty if sysupgrade -l gave nothing)
ktag() {
    [ -s "$T/keep" ] || return 0
    if grep -qxF "/$1" "$T/keep"; then
        printf ' [in sysupgrade -l]'
    else
        printf ' [NOT in sysupgrade -l]'
    fi
}

# File mode and owner for Ansible's mode/owner parameters (empty if stat -c is unavailable)
mtag() {
    m=$(stat -c '%a %U:%G' "$UPPER/$1" 2>/dev/null) || return 0
    printf ' mode=%s' "${m% *}"
    [ "${m#* }" = "root:root" ] || printf ' owner=%s' "${m#* }"
}

: > "$T/ansible"; : > "$T/dirs"; : > "$T/pkgchanged"; : > "$T/pkgclean"
: > "$T/uci"; : > "$T/secret"; : > "$T/ignored"; : > "$T/apknew"

# Collect .apk-new markers (package put a new default file next to your modified one)
find "$UPPER" -type f \( -name '*.apk-new' -o -name '*.apk-old' \) | rel | while IFS= read -r f; do
    b=${f%.apk-new}; b=${b%.apk-old}
    echo "$b" >> "$T/apknew"
done

find "$UPPER" -type f | rel | sort | while IFS= read -r f; do
    # Identical to the reference -> not interesting
    [ -e "$REF/$f" ] && cmp -s "$REF/$f" "$UPPER/$f" && continue

    case "$f" in
        *.apk-new|*.apk-old)
            echo "$f" >> "$T/ignored"; continue ;;
        etc/config/*)
            echo "$f" >> "$T/uci"; continue ;;
        etc/shadow|etc/passwd|etc/group)
            echo "$f" >> "$T/secret"; continue ;;
        etc/apk/world|etc/apk/repositories|etc/apk/repositories.d/*|etc/apk/keys/*)
            continue ;;   # handled separately in section 6
        lib/apk/*|usr/lib/opkg/*|etc/backup/*|etc/urandom.seed|\
        etc/dropbear/dropbear_*_host_key|etc/uhttpd.crt|etc/uhttpd.key)
            echo "$f" >> "$T/ignored"; continue ;;
    esac

    # Does a package own the file? (check the output format of "apk info -W")
    owner=$(apk info -W "/$f" 2>/dev/null | sed -n 's/.* is owned by //p')
    if [ -n "$owner" ]; then
        if grep -qxF "$f" "$T/apknew"; then
            echo "$f  [$owner]" >> "$T/pkgchanged"
        else
            echo "$f  [$owner]" >> "$T/pkgclean"
        fi
        continue
    fi

    if [ -e "$REF/$f" ]; then
        echo "CHANGED  /$f$(mtag "$f")$(ktag "$f")" >> "$T/ansible"
    else
        echo "NEW      /$f$(mtag "$f")$(ktag "$f")" >> "$T/ansible"
    fi
done

# Parent directories of the candidates that do not exist in the factory state
# (Ansible's copy/template does not create them)
sed -n 's/^[A-Z]* *\(\/[^ ]*\).*/\1/p' "$T/ansible" | while IFS= read -r p; do
    d=$(dirname "$p")
    while [ "$d" != "/" ] && [ ! -d "$REF$d" ]; do
        echo "$d"
        d=$(dirname "$d")
    done
done | sort -u | while IFS= read -r d; do
    echo "NEW DIR  $d$(mtag "${d#/}")"
done > "$T/dirs"

print_section "2. Files for Ansible (copy/template; directories first)"
if [ -s "$T/ansible" ] || [ -s "$T/dirs" ]; then
    cat "$T/dirs" "$T/ansible"
else
    echo "(none)"
fi
if [ -s "$T/keep" ]; then
    echo "Note: files marked NOT in sysupgrade -l are lost on a normal sysupgrade."
fi

print_section "3. Package files you modified (.apk-new present)"
if [ -s "$T/pkgchanged" ]; then cat "$T/pkgchanged"; else echo "(none)"; fi

# --- Services via rc.d symlinks and whiteouts -----------------------------
print_section "4. Services (service enabled: true/false)"
{
    find "$UPPER/etc/rc.d" -type l 2>/dev/null | rel | while IFS= read -r f; do
        tgt=$(readlink "$UPPER/$f")
        [ "$(readlink "$REF/$f" 2>/dev/null)" = "$tgt" ] && continue
        echo "enable   $(basename "$tgt")"
    done
    find "$UPPER/etc/rc.d" -type c 2>/dev/null | rel | while IFS= read -r f; do
        # A whiteout only matters if the reference has the link
        if [ -L "$REF/$f" ] || [ -e "$REF/$f" ]; then
            b=$(basename "$f"); b=${b#[SK][0-9][0-9]}
            echo "disable  $b"
        fi
    done
} | sort -u > "$T/services"
if [ -s "$T/services" ]; then cat "$T/services"; else echo "(no differences)"; fi
echo "Note: packages sometimes enable their services themselves on installation."

# --- Other symlinks and deleted files -------------------------------------
print_section "5. Other symlinks and deleted files"
{
    find "$UPPER" -type l 2>/dev/null | rel | grep -v '^etc/rc\.d/' | while IFS= read -r f; do
        tgt=$(readlink "$UPPER/$f")
        [ "$(readlink "$REF/$f" 2>/dev/null)" = "$tgt" ] && continue
        echo "LINK     /$f -> $tgt"
    done
    find "$UPPER" -type c 2>/dev/null | rel | grep -v '^etc/rc\.d/' | while IFS= read -r f; do
        if [ -L "$REF/$f" ] || [ -e "$REF/$f" ]; then
            echo "DELETED  /$f"
        fi
    done
} | sort > "$T/links"
if [ -s "$T/links" ]; then cat "$T/links"; else echo "(none)"; fi

# --- Packages -------------------------------------------------------------
print_section "6. Packages"

# 6a: world = explicitly installed packages (this is the list for Ansible)
WREF="$REF/etc/apk/world"
[ -e "$WREF" ] || WREF=/rom/etc/apk/world
: > "$T/wn_ref"; : > "$T/wn_now"
if [ -e "$WREF" ] && [ -e /etc/apk/world ]; then
    # Strip version constraints (foo>=1.2), compare names only
    tr ' ' '\n' < "$WREF"        | sed -e '/^$/d' -e 's/[<>=~!].*//' | sort -u > "$T/wn_ref"
    tr ' ' '\n' < /etc/apk/world | sed -e '/^$/d' -e 's/[<>=~!].*//' | sort -u > "$T/wn_now"
else
    echo "(world not found: check 'ls /rom/etc/apk /etc/apk')"
fi
comm -13 "$T/wn_ref" "$T/wn_now" > "$T/wadd"
comm -23 "$T/wn_ref" "$T/wn_now" > "$T/wdel"

echo "-- Added via world (-> Ansible: install):"
if [ -s "$T/wadd" ]; then sed 's|^|   |' "$T/wadd"; else echo "   (none)"; fi
echo "-- Removed via world (-> Ansible: remove before installing):"
if [ -s "$T/wdel" ]; then sed 's|^|   |' "$T/wdel"; else echo "   (none)"; fi

# 6b: actually installed packages vs. factory (incl. dependencies, versions)
apk list --installed 2>/dev/null | sed 's/ .*//' | sort > "$T/i_now"
apk --root "$REF" list --installed 2>/dev/null | sed 's/ .*//' | sort > "$T/i_ref"
if [ -s "$T/i_now" ] && [ -s "$T/i_ref" ]; then
    cp "$T/i_now" "$OUT/installed.now"
    cp "$T/i_ref" "$OUT/installed.factory"
    # Package name = entry without version and release (-1.2.3-r1)
    sed 's/-[^-]*-r[0-9]*$//' "$T/i_now" | sort -u > "$T/n_now"
    sed 's/-[^-]*-r[0-9]*$//' "$T/i_ref" | sort -u > "$T/n_ref"
    comm -13 "$T/n_ref" "$T/n_now" > "$T/n_added"
    comm -23 "$T/n_ref" "$T/n_now" > "$T/n_removed"
    comm -13 "$T/i_ref" "$T/i_now" | sed 's/-[^-]*-r[0-9]*$//' | sort -u > "$T/n_nowonly"
    comm -12 "$T/n_nowonly" "$T/n_ref" > "$T/n_changed"
    # Dependencies = added, but not explicitly in world
    comm -23 "$T/n_added" "$T/wn_now" > "$T/n_deps"

    echo "-- Removed from the factory image (installed, not just world):"
    if [ -s "$T/n_removed" ]; then sed 's|^|   |' "$T/n_removed"; else echo "   (none)"; fi
    echo "-- Additional dependencies (pulled in automatically): $(wc -l < "$T/n_deps")"
    echo "-- Version differs from the image: $(wc -l < "$T/n_changed") packages"
    echo "   Lists: $OUT/installed.factory and $OUT/installed.now"
else
    echo "(Installed-package comparison not possible: 'apk list --installed' or"
    echo " 'apk --root $REF list --installed' returned nothing; the world diff above still applies)"
fi

# 6c: variables file for Ansible
{
    echo "# generated by owrt-extra.sh - adapt the variable names to your role"
    echo "owrt_packages_present:"
    sed 's|^|  - |' "$T/wadd"
    echo "owrt_packages_absent:"
    sed 's|^|  - |' "$T/wdel"
} > "$OUT/packages.yml"
echo "-- Ansible variables: $OUT/packages.yml"

# 6d: package feeds and signing keys vs. factory
echo "-- Feeds and signing keys vs. factory:"
{
    for d in etc/apk/repositories.d etc/apk/keys; do
        [ -d "/$d" ]     && (cd "/$d"     && find . -type f | sed "s|^\./|$d/|")
        [ -d "$REF/$d" ] && (cd "$REF/$d" && find . -type f | sed "s|^\./|$d/|")
    done
    if [ -e /etc/apk/repositories ] || [ -e "$REF/etc/apk/repositories" ]; then
        echo "etc/apk/repositories"
    fi
} | sort -u > "$T/feedfiles"
while IFS= read -r f; do
    if [ -e "/$f" ] && [ ! -e "$REF/$f" ]; then
        echo "   ADDED    /$f$(mtag "$f")"
    elif [ ! -e "/$f" ] && [ -e "$REF/$f" ]; then
        echo "   REMOVED  /$f"
    elif ! cmp -s "/$f" "$REF/$f"; then
        echo "   CHANGED  /$f"
        case "$f" in
            etc/apk/keys/*) ;;   # public keys: name is enough
            *) diff "$REF/$f" "/$f" | sed 's/^/      /' ;;
        esac
    fi
done < "$T/feedfiles" > "$T/feedout"
if [ -s "$T/feedout" ]; then cat "$T/feedout"; else echo "   (identical to factory)"; fi

# --- APK system audit ------------------------------------------------------
print_section "3a. APK system audit findings"
APK_AUDIT="$OUT/apk-audit-system.txt"
if command -v apk >/dev/null 2>&1; then
    if apk audit --help 2>&1 | grep -q -- '--system'; then
        if apk audit --system > "$APK_AUDIT" 2>&1; then
            if [ -s "$APK_AUDIT" ]; then
                findings=$(wc -l < "$APK_AUDIT" | tr -d ' ')
                echo "$findings APK system audit finding(s):"
                cat "$APK_AUDIT"
            else
                echo "(no differences reported)"
            fi
            echo "Raw output: $APK_AUDIT"
        else
            rc=$?
            echo "WARNING: 'apk audit --system' exited with status $rc." >&2
            if [ -s "$APK_AUDIT" ]; then cat "$APK_AUDIT"; fi
            echo "Raw output: $APK_AUDIT"
        fi
    else
        echo "WARNING: installed apk does not advertise '--system' support." >&2
        echo "See 'apk audit --help' on this device."
        rm -f "$APK_AUDIT"
    fi
else
    echo "(apk not found; this check requires OpenWrt 25.12+ with apk)"
fi

# --- Info -----------------------------------------------------------------
print_section "7. Info only"
echo "-- UCI files (covered by the UCI diff in section 1):"
if [ -s "$T/uci" ]; then sed 's|^|   /|' "$T/uci"; else echo "   (none)"; fi
echo "-- Secrets (paths only, content is NOT printed; keep out of the repo, use a vault):"
if [ -s "$T/secret" ]; then sed 's|^|   /|' "$T/secret"; else echo "   (none)"; fi
echo "-- Users/groups differing from factory (no hashes in passwd/group;"
echo "   accounts created by installed packages show up here as well):"
for f in etc/passwd etc/group; do
    if [ -e "$REF/$f" ]; then
        if [ "$f" = etc/passwd ]; then
            diff "$REF/$f" "/$f" |
                sed -E 's/^([<>][^:]*:)[^:]*:/\1[REDACTED]:/' |
                grep '^[<>]' | sed 's|^|   |'
        else
            diff "$REF/$f" "/$f" | grep '^[<>]' | sed 's|^|   |'
        fi
    fi
done > "$T/pg"
if [ -s "$T/pg" ]; then cat "$T/pg"; else echo "   (identical)"; fi
echo "-- Unmodified package files: $(wc -l < "$T/pkgclean") (not listed)"
echo "-- Ignored (generated/runtime):"
if [ -s "$T/ignored" ]; then sed 's|^|   /|' "$T/ignored"; else echo "   (none)"; fi

echo "-- /etc/sysupgrade.conf (paths you marked as persistent):"
if [ -f /etc/sysupgrade.conf ]; then
    grep -v '^[[:space:]]*\(#\|$\)' /etc/sysupgrade.conf > "$T/sc" 2>/dev/null
fi
if [ -s "$T/sc" ]; then
    while IFS= read -r p; do
        if [ -e "$p" ]; then echo "   $p"; else echo "   $p  (does not exist)"; fi
    done < "$T/sc"
else
    echo "   (no entries)"
fi
if [ -s "$T/keep" ]; then
    echo "-- sysupgrade -l lists $(wc -l < "$T/keep") files in total (saved to $OUT/sysupgrade.list)"
    cp "$T/keep" "$OUT/sysupgrade.list"
else
    echo "-- sysupgrade -l returned nothing; section 2 has no sysupgrade tags"
fi

# --- U-Boot environment ---------------------------------------------------
print_section "8. U-Boot environment (info only)"
if command -v fw_printenv >/dev/null 2>&1 && fw_printenv > "$OUT/uboot.env" 2>/dev/null; then
    echo "Saved to $OUT/uboot.env ($(wc -l < "$OUT/uboot.env") variables)."
else
    rm -f "$OUT/uboot.env"
    echo "(fw_printenv not available or returned nothing)"
fi
if [ -r /root/.ash_history ]; then
    if grep -q 'fw_setenv' /root/.ash_history; then
        echo "/root/.ash_history contains fw_setenv calls:"
        grep 'fw_setenv' /root/.ash_history | sed 's|^|   |'
    else
        echo "No fw_setenv in /root/.ash_history."
    fi
else
    echo "(no shell history available, cannot check for fw_setenv calls)"
fi

# --- Host keys (optional) -------------------------------------------------
if [ "$HOSTKEYS" = 1 ]; then
    print_section "9. Host keys (-H)"
    SD=$OUT/secrets
    mkdir -p "$SD" && chmod 700 "$SD"
    n=0
    for f in /etc/dropbear/dropbear_*_host_key \
             /etc/ssh/ssh_host_*_key /etc/ssh/ssh_host_*_key.pub \
             /etc/uhttpd.crt /etc/uhttpd.key; do
        [ -f "$f" ] || continue
        d="$SD$(dirname "$f")"
        mkdir -p "$d" && cp -p "$f" "$d/" && n=$((n + 1)) && echo "   $f"
    done
    echo "$n files copied to $SD (plaintext, in RAM below /tmp)."
    echo "Encrypt with ansible-vault or delete after retrieving them."
    echo "Restore: copy back to the same paths with mode 600 BEFORE the service"
    echo "starts for the first time, or restart dropbear afterwards."
fi

echo
echo "Raw data: $OUT/ (factory.show, current.show, uci.diff, packages.yml, ...)"