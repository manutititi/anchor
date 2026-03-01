"""
Low-level WireGuard command helpers.

Every function wraps a single `wg` invocation via subprocess.
Errors are raised as WireGuardError so the router can translate them to HTTP 500.
"""

import os
import subprocess
from dataclasses import dataclass, field

INTERFACE = "wg0"

# IPs that must never be added or removed by the sidecar.
# Populated from WG_PROTECTED_IPS env var (comma-separated).
# Used to protect statically configured peers (e.g. the admin backdoor peer1).
_PROTECTED_IPS: frozenset = frozenset(
    ip.strip() for ip in os.environ.get("WG_PROTECTED_IPS", "").split(",") if ip.strip()
)


class WireGuardError(Exception):
    """Raised when a `wg` command exits with a non-zero code."""

    def __init__(self, cmd: str, returncode: int, stderr: str):
        self.cmd = cmd
        self.returncode = returncode
        self.stderr = stderr
        super().__init__(f"wg command failed (rc={returncode}): {stderr}")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _run(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    """Run a command and optionally raise on failure."""
    result = subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if check and result.returncode != 0:
        raise WireGuardError(
            cmd=" ".join(args),
            returncode=result.returncode,
            stderr=result.stderr.strip(),
        )
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def add_peer(pubkey: str, allowed_ip: str) -> None:
    """Add or update a peer on the live interface (zero downtime).

    Also ensures the kernel has a host route for the peer IP via the WireGuard
    interface so the server can route reply packets back through the tunnel.
    Without this, servers configured with Address=/32 (instead of /24) would
    have no route for dynamically added peer IPs and replies would be dropped.
    """
    if allowed_ip in _PROTECTED_IPS:
        raise WireGuardError(
            f"wg set {INTERFACE} peer ... allowed-ips {allowed_ip}/32",
            0,
            f"IP {allowed_ip} is protected and cannot be managed by the sidecar",
        )
    _run(["wg", "set", INTERFACE, "peer", pubkey, "allowed-ips", f"{allowed_ip}/32"])
    # Add host route (idempotent: ignore errors if it already exists)
    _run(["ip", "route", "add", f"{allowed_ip}/32", "dev", INTERFACE], check=False)


def remove_peer(pubkey: str) -> None:
    """Remove a peer from the live interface and clean up its IP route."""
    # Retrieve the allowed IP before removing the peer
    allowed_ip: str | None = None
    try:
        dump = show_dump()
        for p in dump.peers:
            if p.public_key == pubkey:
                # allowed_ips may be "10.x.x.x/32" — extract the host part
                allowed_ip = p.allowed_ips.split("/")[0]
                break
    except Exception:
        pass

    if allowed_ip and allowed_ip in _PROTECTED_IPS:
        raise WireGuardError(
            f"wg set {INTERFACE} peer {pubkey[:8]}... remove",
            0,
            f"IP {allowed_ip} is protected and cannot be removed by the sidecar",
        )

    _run(["wg", "set", INTERFACE, "peer", pubkey, "remove"])

    if allowed_ip:
        _run(["ip", "route", "del", f"{allowed_ip}/32", "dev", INTERFACE], check=False)


@dataclass
class RawPeer:
    """Parsed row from `wg show <iface> dump` (peer lines)."""

    public_key: str = ""
    preshared_key: str = ""
    endpoint: str | None = None
    allowed_ips: str = ""
    latest_handshake: int = 0
    transfer_rx: int = 0
    transfer_tx: int = 0
    persistent_keepalive: str = ""


@dataclass
class InterfaceInfo:
    """Parsed first row from `wg show <iface> dump` (interface line)."""

    private_key: str = ""
    public_key: str = ""
    listen_port: int = 0
    fwmark: str = ""


@dataclass
class DumpResult:
    """Complete parsed output of `wg show <iface> dump`."""

    interface: InterfaceInfo = field(default_factory=InterfaceInfo)
    peers: list[RawPeer] = field(default_factory=list)


def show_dump() -> DumpResult:
    """
    Parse `wg show wg0 dump`.

    Output format (tab-separated):
      Line 1 (interface): private_key  public_key  listen_port  fwmark
      Line 2+ (peers):    public_key  preshared_key  endpoint  allowed_ips
                           latest_handshake  transfer_rx  transfer_tx
                           persistent_keepalive
    """
    result = _run(["wg", "show", INTERFACE, "dump"])
    lines = result.stdout.strip().splitlines()

    dump = DumpResult()

    if not lines:
        return dump

    # First line = interface
    iface_parts = lines[0].split("\t")
    dump.interface = InterfaceInfo(
        private_key=iface_parts[0] if len(iface_parts) > 0 else "",
        public_key=iface_parts[1] if len(iface_parts) > 1 else "",
        listen_port=int(iface_parts[2]) if len(iface_parts) > 2 and iface_parts[2].isdigit() else 0,
        fwmark=iface_parts[3] if len(iface_parts) > 3 else "",
    )

    # Remaining lines = peers
    for line in lines[1:]:
        parts = line.split("\t")
        if len(parts) < 8:
            continue
        dump.peers.append(RawPeer(
            public_key=parts[0],
            preshared_key=parts[1],
            endpoint=parts[2] if parts[2] != "(none)" else None,
            allowed_ips=parts[3],
            latest_handshake=int(parts[4]) if parts[4].isdigit() else 0,
            transfer_rx=int(parts[5]) if parts[5].isdigit() else 0,
            transfer_tx=int(parts[6]) if parts[6].isdigit() else 0,
            persistent_keepalive=parts[7],
        ))

    return dump


def check_interface() -> dict:
    """
    Verify that the wg0 interface exists and is operational.
    Returns basic interface info or raises WireGuardError.
    """
    dump = show_dump()
    return {
        "public_key": dump.interface.public_key,
        "listen_port": dump.interface.listen_port,
        "peer_count": len(dump.peers),
    }
