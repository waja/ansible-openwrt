#!/bin/sh
# Manage the temporary CVE-2026-98432 nftables mitigation.
set -eu

NFT_FILE=/etc/cve_2026_98432.nft
UCI_SECTION=ansible_cve_2026_98432
SYSUPGRADE_FILE=/etc/sysupgrade.conf
TABLE=cve_2026_98432
# OpenWrt 25.12 provides nftables destroy-table support.
ACTION=${CVE_ACTION:-${1:-detect}}

version_ge() {
    awk -v a="$1" -v b="$2" 'BEGIN {
        split(a, x, /[.]/); split(b, y, /[.]/);
        for (i = 1; i <= 3; i++) {
            if ((x[i] + 0) > (y[i] + 0)) exit 0;
            if ((x[i] + 0) < (y[i] + 0)) exit 1;
        }
        exit 0;
    }'
}

ensure_fw4_support() {
    if ! command -v fw4 >/dev/null 2>&1; then
        echo "CVE mitigation currently requires OpenWrt firewall4 (fw4)" >&2
        return 1
    fi
    if [ ! -x /etc/init.d/firewall ] ||
       ! /etc/init.d/firewall enabled >/dev/null 2>&1; then
        echo "The OpenWrt firewall service is disabled; refusing a non-persistent deployment" >&2
        return 1
    fi
    if ! command -v uci >/dev/null 2>&1 ||
       ! command -v nft >/dev/null 2>&1; then
        echo "CVE mitigation requires uci and nft" >&2
        return 1
    fi
}

ensure_destroy_support() {
    kernel_version=$(uname -r |
        sed -n 's/^\([0-9][0-9]*\.[0-9][0-9]*\.[0-9][0-9]*\).*/\1/p')
    nft_version=$(nft --version 2>/dev/null |
        sed -n 's/.* v\([0-9][0-9]*\.[0-9][0-9]*\.[0-9][0-9]*\).*/\1/p')
    if ! version_ge "$kernel_version" 6.3.0; then
        echo "CVE mitigation requires Linux >= 6.3 for nft destroy table" >&2
        return 1
    fi
    if ! version_ge "$nft_version" 1.0.8; then
        echo "CVE mitigation requires nftables >= 1.0.8" >&2
        return 1
    fi
}

parse_kernel_release() {
    printf '%s\n' "$1" |
        sed -n \
            -e 's/^\([0-9][0-9]*\.[0-9][0-9]*\.[0-9][0-9]*\)\(-rc[0-9][0-9]*\)\?\([+._-].*\)\?$/\1\2/p' \
            -e 's/^\(7\.3-rc[0-9][0-9]*\)\([+._-].*\)\?$/\1/p'
}

classify_version() {
    version=$1
    status=unknown
    case "$version" in
        5.10.*)
            if version_ge "$version" 5.10.272; then
                status=patched
            else
                status=vulnerable
            fi
            ;;
        5.15.*)
            if version_ge "$version" 5.15.223; then
                status=patched
            else
                status=vulnerable
            fi
            ;;
        6.1.*)
            if version_ge "$version" 6.1.190; then
                status=patched
            else
                status=vulnerable
            fi
            ;;
        6.6.*)
            if version_ge "$version" 6.6.159; then
                status=patched
            else
                status=vulnerable
            fi
            ;;
        6.12.*)
            if version_ge "$version" 6.12.113; then
                status=patched
            else
                status=vulnerable
            fi
            ;;
        6.18.*)
            if version_ge "$version" 6.18.56; then
                status=patched
            else
                status=vulnerable
            fi
            ;;
        7.2.*)
            if version_ge "$version" 7.2.10; then
                status=patched
            else
                status=vulnerable
            fi
            ;;
        7.3.*-rc*|7.3-rc*)
            rc_number=${version##*-rc}
            if [ "$rc_number" -ge 7 ]; then
                status=patched
            else
                status=vulnerable
            fi
            ;;
        7.3.*)  status=patched ;;
    esac
    printf '%s' "$status"
}

detect_kernel() {
    release=$(uname -r)
    version=$(parse_kernel_release "$release")
    running_status=$(classify_version "$version")
    printf 'kernel_release=%s\nkernel_version=%s\nkernel_status=%s\n' \
        "$release" "${version:-unknown}" "$running_status"

    package=
    if command -v opkg >/dev/null 2>&1; then
        package=$(opkg status kernel 2>/dev/null |
            sed -n 's/^Version: //p' | head -n 1)
    elif command -v apk >/dev/null 2>&1; then
        package=$(apk list --installed 2>/dev/null |
            grep -E '^kernel-[0-9]' | head -n 1 || true)
    fi
    package_version=$(printf '%s\n' "$package" |
        sed -n 's/.*\([0-9][0-9]*\.[0-9][0-9]*\.[0-9][0-9]*\).*/\1/p')
    [ -n "$package_version" ] ||
        package_version=$(printf '%s\n' "$package" |
            sed -n 's/.*\([0-9][0-9]*\.[0-9][0-9]*\)-rc\([0-9][0-9]*\).*/\1-rc\2/p')
    package_status=$(classify_version "$package_version")
    package_suggests_fixed_update=no
    if [ "$running_status" = vulnerable ] &&
       [ "$package_status" = patched ]; then
        package_suggests_fixed_update=yes
    fi
    printf 'kernel_package=%s\ninstalled_kernel_version=%s\n' \
        "${package:-unknown}" "${package_version:-unknown}"
    printf 'installed_kernel_status=%s\nkernel_package_suggests_fixed_update=%s\n' \
        "$package_status" "$package_suggests_fixed_update"
}

is_active() {
    rules=$(nft list table ip "$TABLE" 2>/dev/null) || return 1
    printf '%s\n' "$rules" | grep -Fq 'chain pre {' &&
        printf '%s\n' "$rules" |
            grep -Eq 'hook prerouting priority (-310|raw - 10)' &&
        printf '%s\n' "$rules" |
            grep -Fq 'ip protocol tcp ip hdrlength 6-15' &&
        printf '%s\n' "$rules" | grep -Fq 'counter' &&
        printf '%s\n' "$rules" | grep -Fq 'drop'
}

write_ruleset() {
    cat > "$1" <<'NFT'
destroy table ip cve_2026_98432
table ip cve_2026_98432 {
    chain pre {
        type filter hook prerouting priority -310; policy accept;
        ip protocol tcp ip hdrlength 6-15 counter drop
    }
}
NFT
}

status() {
    detect_kernel
    [ ! -f "$NFT_FILE" ] || file_state=present
    [ -f "$NFT_FILE" ] || file_state=absent
    section_type=$(uci -q get "firewall.$UCI_SECTION" 2>/dev/null || true)
    section_path=$(uci -q get "firewall.$UCI_SECTION.path" 2>/dev/null || true)
    section_kind=$(uci -q get "firewall.$UCI_SECTION.type" 2>/dev/null || true)
    section_position=$(uci -q get "firewall.$UCI_SECTION.position" 2>/dev/null || true)
    if [ "$section_type" = include ] &&
       [ "$section_path" = "$NFT_FILE" ] &&
       [ "$section_kind" = nftables ] &&
       [ "$section_position" = ruleset-post ]; then
        include_state=present
    else
        include_state=absent
    fi
    if grep -Fxq "$NFT_FILE" "$SYSUPGRADE_FILE" 2>/dev/null; then
        backup_state=present
    else
        backup_state=absent
    fi
    if is_active; then active_state=present; else active_state=absent; fi
    firewall_backend=none
    command -v fw4 >/dev/null 2>&1 && firewall_backend=fw4
    firewall_service_enabled=no
    if [ -x /etc/init.d/firewall ] &&
       /etc/init.d/firewall enabled >/dev/null 2>&1; then
        firewall_service_enabled=yes
    fi
    printf 'file=%s\ninclude=%s\nsysupgrade=%s\nactive=%s\n' \
        "$file_state" "$include_state" "$backup_state" "$active_state"
    printf 'firewall_backend=%s\nfirewall_service_enabled=%s\n' \
        "$firewall_backend" "$firewall_service_enabled"
}


refuse_pending_firewall_changes() {
    pending=$(uci changes firewall 2>/dev/null || true)
    [ -z "$pending" ] || {
        echo "Refusing to modify firewall state with pending UCI changes; commit or revert them first" >&2
        return 1
    }
}

prepare_backups() {
    tmp_file_backup=$(mktemp)
    tmp_uci_backup=$(mktemp)
    tmp_upgrade_backup=$(mktemp)
    file_existed=no
    upgrade_existed=no
    table_existed=no
    live_changed=no
    if nft list table ip "$TABLE" >/dev/null 2>&1; then
        table_existed=yes
    fi
    [ ! -e "$NFT_FILE" ] || {
        cp -p "$NFT_FILE" "$tmp_file_backup"
        file_existed=yes
    }
    cp -p /etc/config/firewall "$tmp_uci_backup"
    [ ! -e "$SYSUPGRADE_FILE" ] || {
        cp -p "$SYSUPGRADE_FILE" "$tmp_upgrade_backup"
        upgrade_existed=yes
    }
}

rollback() {
    if [ "$file_existed" = yes ]; then
        cp -p "$tmp_file_backup" "$NFT_FILE"
    else
        rm -f "$NFT_FILE"
    fi
    cp -p "$tmp_uci_backup" /etc/config/firewall
    uci revert firewall >/dev/null 2>&1 || true
    if [ "$upgrade_existed" = yes ]; then
        cp -p "$tmp_upgrade_backup" "$SYSUPGRADE_FILE"
    else
        rm -f "$SYSUPGRADE_FILE"
    fi
    if [ "$live_changed" = yes ] && fw4 check >/dev/null 2>&1; then
        fw4 reload >/dev/null 2>&1 || true
    fi
    if [ "$table_existed" = no ]; then
        nft destroy table ip "$TABLE" >/dev/null 2>&1 || true
    fi
    rm -f "$tmp_file_backup" "$tmp_uci_backup" "$tmp_upgrade_backup"
}

cleanup_backups() {
    rm -f "$tmp_file_backup" "$tmp_uci_backup" "$tmp_upgrade_backup"
}

install_mitigation() {
    before=$(status)
    refuse_pending_firewall_changes || return 1
    section_type=$(uci -q get "firewall.$UCI_SECTION" 2>/dev/null || true)
    section_path=$(uci -q get "firewall.$UCI_SECTION.path" 2>/dev/null || true)
    section_kind=$(uci -q get "firewall.$UCI_SECTION.type" 2>/dev/null || true)

    if nft list table ip "$TABLE" >/dev/null 2>&1 &&
       [ "$section_path" != "$NFT_FILE" ] &&
       [ ! -e "$NFT_FILE" ]; then
        echo "Refusing to adopt an existing unmanaged nftables table" >&2
        return 1
    fi
    if [ -n "$section_type" ] &&
       { [ "$section_type" != include ] ||
         [ "$section_path" != "$NFT_FILE" ] ||
         [ "$section_kind" != nftables ]; }; then
        echo "Refusing to replace conflicting UCI section $UCI_SECTION" >&2
        return 1
    fi

    ensure_fw4_support
    ensure_destroy_support
    tmp_new=$(mktemp)
    write_ruleset "$tmp_new"
    if printf '%s\n' "$before" | grep -qx 'file=present' &&
       printf '%s\n' "$before" | grep -qx 'include=present' &&
       printf '%s\n' "$before" | grep -qx 'sysupgrade=present' &&
       printf '%s\n' "$before" | grep -qx 'active=present' &&
       cmp -s "$tmp_new" "$NFT_FILE"; then
        rm -f "$tmp_new"
        printf 'changed=no\n'
        return 0
    fi

    prepare_backups
    trap 'rm -f "$tmp_new"; rollback' EXIT
    trap 'exit 1' HUP INT TERM
    chmod 0644 "$tmp_new"
    mv "$tmp_new" "$NFT_FILE"

    uci set "firewall.$UCI_SECTION=include"
    uci set "firewall.$UCI_SECTION.type=nftables"
    uci set "firewall.$UCI_SECTION.path=$NFT_FILE"
    uci set "firewall.$UCI_SECTION.position=ruleset-post"
    uci commit firewall

    touch "$SYSUPGRADE_FILE"
    grep -Fxq "$NFT_FILE" "$SYSUPGRADE_FILE" ||
        printf '%s\n' "$NFT_FILE" >> "$SYSUPGRADE_FILE"

    fw4 check
    live_changed=yes
    fw4 reload
    is_active
    trap - EXIT HUP INT TERM
    cleanup_backups
    printf 'changed=yes\n'
}

remove_mitigation() {
    before=$(status)
    section_path=$(uci -q get "firewall.$UCI_SECTION.path" 2>/dev/null || true)
    if nft list table ip "$TABLE" >/dev/null 2>&1 &&
       [ "$section_path" != "$NFT_FILE" ] &&
       [ ! -e "$NFT_FILE" ]; then
        echo "Refusing to remove an unmanaged nftables table" >&2
        return 1
    fi
    section_type=$(uci -q get "firewall.$UCI_SECTION" 2>/dev/null || true)
    section_exists=no
    if [ -n "$section_type" ]; then
        [ "$section_type" = include ] || {
            echo "Refusing to remove conflicting UCI section $UCI_SECTION" >&2
            return 1
        }
        [ "$(uci -q get "firewall.$UCI_SECTION.path" 2>/dev/null || true)" = "$NFT_FILE" ] || {
            echo "Refusing to remove UCI include with unexpected path" >&2
            return 1
        }
        [ "$(uci -q get "firewall.$UCI_SECTION.type" 2>/dev/null || true)" = nftables ] || {
            echo "Refusing to remove UCI include with unexpected type" >&2
            return 1
        }
        section_exists=yes
    fi
    if printf '%s\n' "$before" | grep -qx 'file=absent' &&
       printf '%s\n' "$before" | grep -qx 'include=absent' &&
       printf '%s\n' "$before" | grep -qx 'sysupgrade=absent' &&
       printf '%s\n' "$before" | grep -qx 'active=absent' &&
       [ "$section_exists" = no ]; then
        printf 'changed=no\n'
        return 0
    fi
    refuse_pending_firewall_changes || return 1
    prepare_backups
    trap 'rollback' EXIT
    trap 'exit 1' HUP INT TERM
    if [ "$section_exists" = yes ]; then
        uci -q delete "firewall.$UCI_SECTION"
        uci commit firewall
    fi
    if [ -f "$SYSUPGRADE_FILE" ]; then
        awk -v path="$NFT_FILE" '$0 != path' "$SYSUPGRADE_FILE" \
            > "$SYSUPGRADE_FILE.tmp"
        cat "$SYSUPGRADE_FILE.tmp" > "$SYSUPGRADE_FILE"
        rm -f "$SYSUPGRADE_FILE.tmp"
    fi
    rm -f "$NFT_FILE"
    fw4 check
    live_changed=yes
    fw4 reload
    if nft list table ip "$TABLE" >/dev/null 2>&1; then
        nft delete table ip "$TABLE"
    fi
    if is_active; then
        echo "Mitigation table remains active after removal" >&2
        return 1
    fi
    trap - EXIT HUP INT TERM
    cleanup_backups
    printf 'changed=yes\n'
}

case "$ACTION" in
    detect) detect_kernel ;;
    status) status ;;
    install) install_mitigation; status ;;
    remove) remove_mitigation; status ;;
    classify) classify_version "${CVE_VERSION:-${2:-}}" ;;
    parse-release)
        parsed=$(parse_kernel_release "${CVE_RELEASE:-${2:-}}")
        if [ -n "$parsed" ]; then
            printf 'kernel_version=%s\nkernel_status=%s\n' \
                "$parsed" "$(classify_version "$parsed")"
        else
            printf 'kernel_version=unknown\nkernel_status=unknown\n'
        fi
        ;;
    *) echo "Usage: $0 {detect|status|install|remove|classify|parse-release}" >&2; exit 2 ;;
esac
