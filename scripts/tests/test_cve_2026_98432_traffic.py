#!/usr/bin/env python3
"""Exercise the CVE-2026-98432 nftables rule on INPUT and FORWARD paths."""

from __future__ import annotations

import re
import socket
import subprocess
import sys
import time
from pathlib import Path


CLIENT = "cve-test-client"
ROUTER = "cve-test-router"
SERVER = "cve-test-server"
TABLE = "cve_2026_98432"
INPUT_PORT = 18080
FORWARD_PORT = 18081
IPV6_PORT = 18082


def run(*args: str, namespace: str | None = None) -> str:
    command = (
        ["ip", "netns", "exec", namespace, *args]
        if namespace
        else list(args)
    )
    result = subprocess.run(
        command, check=True, text=True, capture_output=True
    )
    return result.stdout


def start_server(
    namespace: str, family: int, address: str, port: int
) -> subprocess.Popen[str]:
    source = """
import socket
import sys

family = int(sys.argv[1])
address = sys.argv[2]
port = int(sys.argv[3])
server = socket.socket(family, socket.SOCK_STREAM)
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
if family == socket.AF_INET6:
    server.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
server.bind((address, port))
server.listen()
while True:
    connection, _ = server.accept()
    connection.close()
"""
    return subprocess.Popen(
        [
            "ip", "netns", "exec", namespace, sys.executable, "-c", source,
            str(family), address, str(port),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )


def wait_for_listeners(
    servers: list[tuple[subprocess.Popen[str], int, str, int]],
    timeout: float = 5.0,
) -> None:
    probe = """
import socket
import sys

family = int(sys.argv[1])
address = sys.argv[2]
port = int(sys.argv[3])
client = socket.socket(family, socket.SOCK_STREAM)
client.settimeout(0.2)
try:
    client.connect((address, port))
except OSError:
    sys.exit(1)
finally:
    client.close()
"""
    pending = list(servers)
    deadline = time.monotonic() + timeout
    while pending:
        remaining = []
        for process, family, address, port in pending:
            if process.poll() is not None:
                error = process.stderr.read() if process.stderr else ""
                raise RuntimeError(
                    f"Listener {address}:{port} exited before becoming ready: "
                    f"{error.strip() or process.returncode}"
                )
            result = subprocess.run(
                [
                    "ip", "netns", "exec", CLIENT, sys.executable, "-c", probe,
                    str(family), address, str(port),
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=1,
            )
            if result.returncode == 0:
                continue
            if result.returncode != 1:
                raise RuntimeError(
                    f"Listener probe for {address}:{port} failed: "
                    f"{result.stderr or result.stdout}"
                )
            remaining.append((process, family, address, port))
        pending = remaining
        if pending and time.monotonic() >= deadline:
            endpoints = ", ".join(
                f"{address}:{port}" for _, _, address, port in pending
            )
            raise TimeoutError(
                f"Listeners did not become ready within {timeout}s: {endpoints}"
            )
        if pending:
            time.sleep(0.05)


def connect(
    address: str, port: int, *, ipv6: bool = False, ip_options: bool = False
) -> bool:
    source = """
import socket
import sys

address = sys.argv[1]
port = int(sys.argv[2])
ipv6 = sys.argv[3] == "true"
ip_options = sys.argv[4] == "true"
family = socket.AF_INET6 if ipv6 else socket.AF_INET
client = socket.socket(family, socket.SOCK_STREAM)
client.settimeout(1.5)
if ip_options:
    client.setsockopt(
        socket.IPPROTO_IP,
        socket.IP_OPTIONS,
        b"\\x01\\x01\\x01\\x00",
    )
try:
    client.connect((address, port))
except (TimeoutError, socket.timeout):
    sys.exit(10)
except ConnectionResetError:
    sys.exit(11)
finally:
    client.close()
"""
    result = subprocess.run(
        [
            "ip", "netns", "exec", CLIENT, sys.executable, "-c", source,
            address, str(port), str(ipv6).lower(), str(ip_options).lower(),
        ],
        check=False, capture_output=True, text=True,
    )
    if result.returncode == 0:
        return True
    if result.returncode in (10, 11):
        return False
    raise RuntimeError(
        "Client connection failed unexpectedly: "
        f"{result.stderr or result.stdout}"
    )


def counter_packets() -> int:
    output = run(
        "nft", "-nn", "list", "chain", "ip", TABLE, "pre",
        namespace=ROUTER,
    )
    match = re.search(r"counter packets (\d+)", output)
    if not match:
        raise RuntimeError(f"Could not read mitigation counter:\n{output}")
    return int(match.group(1))


def expect_drop(address: str, port: int, label: str) -> None:
    before = counter_packets()
    if connect(address, port, ip_options=True):
        raise AssertionError(f"{label}: IPv4 TCP with IP options was accepted")
    after = counter_packets()
    if after <= before:
        raise AssertionError(
            f"{label}: the mitigation counter did not increase "
            f"({before} -> {after})"
        )


def configure(created_namespaces: list[str]) -> None:
    for namespace in (CLIENT, ROUTER, SERVER):
        run("ip", "netns", "add", namespace)
        created_namespaces.append(namespace)
        run("ip", "-n", namespace, "link", "set", "lo", "up")

    run("ip", "link", "add", "c0", "type", "veth", "peer", "name", "r0")
    run("ip", "link", "set", "c0", "netns", CLIENT)
    run("ip", "link", "set", "r0", "netns", ROUTER)
    run("ip", "link", "add", "r1", "type", "veth", "peer", "name", "s0")
    run("ip", "link", "set", "r1", "netns", ROUTER)
    run("ip", "link", "set", "s0", "netns", SERVER)

    for namespace, interface in (
        (CLIENT, "c0"), (ROUTER, "r0"), (ROUTER, "r1"), (SERVER, "s0")
    ):
        run("ip", "-n", namespace, "link", "set", interface, "up")

    for namespace, interface, address in (
        (CLIENT, "c0", "192.0.2.2/24"),
        (ROUTER, "r0", "192.0.2.1/24"),
        (ROUTER, "r1", "198.51.100.1/24"),
        (SERVER, "s0", "198.51.100.2/24"),
    ):
        run("ip", "-n", namespace, "address", "add", address, "dev", interface)

    for namespace, interface, address in (
        (CLIENT, "c0", "fd00:1::2/64"),
        (ROUTER, "r0", "fd00:1::1/64"),
        (ROUTER, "r1", "fd00:2::1/64"),
        (SERVER, "s0", "fd00:2::2/64"),
    ):
        run(
            "ip", "-n", namespace, "-6", "address", "add",
            address, "dev", interface, "nodad",
        )

    run(
        "ip", "-n", CLIENT, "route", "add", "198.51.100.0/24",
        "via", "192.0.2.1",
    )
    run(
        "ip", "-n", SERVER, "route", "add", "192.0.2.0/24",
        "via", "198.51.100.1",
    )
    run(
        "ip", "-n", CLIENT, "-6", "route", "add", "fd00:2::/64",
        "via", "fd00:1::1",
    )
    run(
        "ip", "-n", SERVER, "-6", "route", "add", "fd00:1::/64",
        "via", "fd00:2::1",
    )

    run(
        "ip", "netns", "exec", ROUTER, "sysctl", "-q", "-w",
        "net.ipv4.ip_forward=1",
    )
    run(
        "ip", "netns", "exec", ROUTER, "sysctl", "-q", "-w",
        "net.ipv6.conf.all.forwarding=1",
    )

    ruleset = (
        Path(__file__).resolve().parents[2]
        / "roles/router_cve_2026_98432/files/mitigation.nft"
    )
    subprocess.run(
        ["ip", "netns", "exec", ROUTER, "nft", "-f", str(ruleset)],
        check=True,
    )


def main() -> int:
    servers: list[subprocess.Popen[str]] = []
    created_namespaces: list[str] = []
    try:
        configure(created_namespaces)
        servers.extend([
            start_server(ROUTER, socket.AF_INET, "192.0.2.1", INPUT_PORT),
            start_server(SERVER, socket.AF_INET, "198.51.100.2", FORWARD_PORT),
            start_server(SERVER, socket.AF_INET6, "fd00:2::2", IPV6_PORT),
        ])
        wait_for_listeners([
            (servers[0], socket.AF_INET, "192.0.2.1", INPUT_PORT),
            (servers[1], socket.AF_INET, "198.51.100.2", FORWARD_PORT),
            (servers[2], socket.AF_INET6, "fd00:2::2", IPV6_PORT),
        ])

        # Ordinary IPv4 TCP must continue to work on both paths.
        if not connect("192.0.2.1", INPUT_PORT):
            raise AssertionError("ordinary IPv4 TCP to INPUT was not accepted")
        print("PASS: ordinary IPv4 TCP to INPUT is accepted")
        if not connect("198.51.100.2", FORWARD_PORT):
            raise AssertionError(
                "ordinary IPv4 TCP to FORWARD was not accepted"
            )
        print("PASS: ordinary IPv4 TCP to FORWARD is accepted")

        # IP options must be dropped on both paths and counted by the rule.
        expect_drop("192.0.2.1", INPUT_PORT, "INPUT")
        print("PASS: IPv4 TCP with IP options is dropped on INPUT")
        expect_drop("198.51.100.2", FORWARD_PORT, "FORWARD")
        print("PASS: IPv4 TCP with IP options is dropped on FORWARD")

        # The IPv4-only rule must not affect IPv6.
        if not connect("fd00:2::2", IPV6_PORT, ipv6=True):
            raise AssertionError("IPv6 TCP was not accepted")
        print("PASS: IPv6 TCP is accepted")
        return 0
    except Exception:
        for namespace in (CLIENT, ROUTER, SERVER):
            print(f"=== {namespace} interfaces ===", file=sys.stderr)
            subprocess.run(
                ["ip", "-n", namespace, "address"],
                check=False, text=True,
            )
            print(f"=== {namespace} routes ===", file=sys.stderr)
            subprocess.run(
                ["ip", "-n", namespace, "route", "show"],
                check=False, text=True,
            )
        for server in servers:
            if server.poll() is not None and server.stderr is not None:
                print(server.stderr.read(), file=sys.stderr)
        subprocess.run(
            ["ip", "netns", "exec", ROUTER, "nft", "list", "ruleset"],
            check=False, text=True,
        )
        raise
    finally:
        for server in servers:
            server.terminate()
            try:
                server.wait(timeout=2)
            except subprocess.TimeoutExpired:
                server.kill()
        for namespace in reversed(created_namespaces):
            subprocess.run(
                ["ip", "netns", "del", namespace],
                check=False, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as error:
        print(
            f"Command failed: {error.cmd}\n{error.stderr or error.stdout}",
            file=sys.stderr,
        )
        raise SystemExit(error.returncode or 1)
