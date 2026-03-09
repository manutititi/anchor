"""
VPN commands — WireGuard tunnel management via SPA (Single Packet Authorization).

  anc vpn up     — full flow: SPA knock → onboarding tunnel → promote → full tunnel
  anc vpn down   — bring down the VPN tunnel and best-effort revoke server lease
  anc vpn status — show server lease info + local wg show

First-time setup: 'anc vpn up' runs an interactive wizard that saves
~/.config/anchor/vpn.toml (mode 0600).

Dependencies (install with pip install 'anchor-cli[vpn]'):
  pycryptodome>=3  — AES-256-GCM for SPA packet
  qrcode>=7.4      — ASCII QR code in terminal (optional, falls back to URL)

External binaries (wireguard-tools, must be in PATH):
  wg, wg-quick     — WireGuard key generation and tunnel management
"""
from __future__ import annotations

import base64
import getpass
import json
import ipaddress
import os
import socket
import struct
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import requests
import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from anchor.config import (
    CONFIG_DIR,
    ensure_dirs,
    load_credentials,
    save_credentials,
)
from anchor.client import AnchorClient, AnchorClientError, NotAuthenticatedError

console = Console()
app = typer.Typer(
    name="vpn",
    help="Manage WireGuard VPN tunnel via SPA.",
    no_args_is_help=True,
)

VPN_CONFIG_FILE = CONFIG_DIR / "vpn.toml"
WG_IFACE = "anc-vpn"
WG_CONF = Path("/tmp/anc-vpn.conf")


# ---------------------------------------------------------------------------
# VPN config helpers
# ---------------------------------------------------------------------------

def _load_vpn_config() -> dict:
    if not VPN_CONFIG_FILE.exists():
        return {}
    try:
        import tomllib  # stdlib 3.11+
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ImportError:
            return {}
    with open(VPN_CONFIG_FILE, "rb") as f:
        return tomllib.load(f)


def _save_vpn_config(cfg: dict) -> None:
    ensure_dirs()
    VPN_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for k, v in cfg.items():
        if isinstance(v, bool):
            lines.append(f"{k} = {'true' if v else 'false'}")
        elif isinstance(v, str):
            escaped = v.replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'{k} = "{escaped}"')
        else:
            lines.append(f"{k} = {v}")
    VPN_CONFIG_FILE.write_text("\n".join(lines) + "\n")
    os.chmod(VPN_CONFIG_FILE, 0o600)


def _parse_provision_token(token: str) -> dict:
    """
    Decode a base64url provision token.

    Accepts two formats:
      - /otp token (knock-only): has spa_pubkey, no seed_b32/wg_privkey
      - /provision token (full):  has spa_pubkey + seed_b32 + wg_privkey

    Raises ValueError with a human-readable message on failure.
    """
    try:
        padded = token + "=" * (4 - len(token) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded))
    except Exception:
        raise ValueError("Invalid token — could not decode. Make sure you copied it completely.")

    # Fields required in all token types
    required = {"uid", "vpn_uid", "knock_host", "knock_port",
                "subnet", "server_vpn_uid", "server_endpoint", "server_pubkey",
                "server_port", "spa_pubkey"}
    missing = required - set(data.keys())
    if missing:
        raise ValueError(f"Token is missing fields: {', '.join(sorted(missing))}")

    return data


def _run_wizard() -> dict:
    """
    Interactive first-time setup wizard.
    Primary path: paste the provision token the admin gave you (one field).
    Fallback: enter fields manually if you don't have a token.
    Returns the saved config dict.
    """
    console.print()
    console.print(Panel(
        "[bold]VPN First-Time Setup[/bold]\n\n"
        "Ask your admin to run:\n"
        "  [cyan]POST /vpn/admin/users/{tu_usuario}/otp[/cyan]\n\n"
        "Te dará un [bold]provision token[/bold]. Pégalo aquí y listo.",
        title="[bold blue]anc vpn setup",
    ))
    console.print()

    token_raw = Prompt.ask("[cyan]Provision token (or press Enter for manual setup)")
    if token_raw.strip():
        try:
            cfg = _parse_provision_token(token_raw.strip())
        except ValueError as exc:
            console.print(f"[red]Token error:[/red] {exc}")
            raise typer.Exit(1)
        _save_vpn_config(cfg)
        console.print(f"[green]Config saved to[/green] {VPN_CONFIG_FILE}")
        seed = cfg.get("seed_b32", "")
        uid = cfg.get("uid", "")
        if seed and uid:
            from urllib.parse import quote
            purl = f"otpauth://totp/Anchor:{quote(uid)}?secret={seed}&issuer=Anchor"
            _show_qr(purl)
            console.print("[dim]Scan the QR with your authenticator app, then run [bold]anc vpn up[/bold][/dim]")
        else:
            console.print("[dim]Scan the QR your admin showed you, then run [bold]anc vpn up[/bold][/dim]")
        return cfg

    # ── Manual fallback ──────────────────────────────────────────────────────
    console.print("[dim]Manual setup — ask your admin for each value.[/dim]\n")
    uid = Prompt.ask("[cyan]Your username")
    spa_pubkey = Prompt.ask("[cyan]Server SPA public key (base64, from admin)")
    knock_host = Prompt.ask("[cyan]Knock server hostname or IP")
    knock_port = int(Prompt.ask("[cyan]Knock UDP port", default="62201"))
    subnet = Prompt.ask("[cyan]VPN subnet", default="10.13.13.0/24")
    server_endpoint = Prompt.ask("[cyan]WireGuard server endpoint (host:port)")
    server_pubkey = Prompt.ask("[cyan]WireGuard server public key")
    server_port = int(Prompt.ask("[cyan]Anchor server internal port", default="17017"))

    console.print(
        "[yellow]vpn_uid unknown in manual mode.[/yellow] "
        "The correct IP will be set after the first successful 'anc vpn up'.\n"
        "If the first attempt times out, ask the admin for your numeric vpn_uid "
        "and set it manually in ~/.config/anchor/vpn.toml."
    )
    vpn_uid = int(Prompt.ask("[cyan]Your VPN UID (numeric, from admin; 0 = unknown)", default="0"))

    cfg = {
        "uid": uid,
        "vpn_uid": vpn_uid,
        "spa_pubkey": spa_pubkey,
        "knock_host": knock_host,
        "knock_port": knock_port,
        "subnet": subnet,
        "server_vpn_uid": 1,
        "server_endpoint": server_endpoint,
        "server_pubkey": server_pubkey,
        "server_port": server_port,
    }
    _save_vpn_config(cfg)
    console.print(f"[green]Config saved to[/green] {VPN_CONFIG_FILE}")
    return cfg


# ---------------------------------------------------------------------------
# Crypto helpers (replicates server/code/vpn/spa.py — no server deps in CLI)
# ---------------------------------------------------------------------------

def _check_vpn_deps() -> None:
    """Fail fast with a helpful message if optional VPN deps are missing."""
    try:
        from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey  # noqa: F401
    except ImportError:
        console.print(
            "[red]Missing VPN dependency: cryptography[/red]\n"
            "Install with: [bold]pip install 'anchor-cli[vpn]'[/bold]"
        )
        raise typer.Exit(1)


def _show_qr(provisioning_url: str) -> None:
    """Print an ASCII QR code in the terminal for the TOTP provisioning URL."""
    try:
        import qrcode  # type: ignore[import]
        qr = qrcode.QRCode(border=1)
        qr.add_data(provisioning_url)
        qr.make(fit=True)
        console.print("\n[bold]Scan this QR with Google Authenticator / Authy:[/bold]")
        qr.print_ascii(invert=True)
        console.print()
    except ImportError:
        console.print(f"[dim]Provisioning URL:[/dim] {provisioning_url}")
        console.print("[dim](Install qrcode for a QR code in terminal)[/dim]")


def _uid_to_ip(uid: int, subnet: str) -> str:
    net = ipaddress.IPv4Network(subnet, strict=False)
    return str(net.network_address + uid)


def _build_spa_packet(uid_str: str, otp_str: str, wg_pubkey: str, server_spa_pubkey_b64: str) -> bytes:
    """
    Build a 186-byte SPA v2 UDP packet (ECIES).
    Mirrors server/code/vpn/spa.py:build_packet() exactly.
    The uid is encrypted — an observer cannot determine who sent the packet.
    """
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.hashes import SHA256
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, PublicFormat

    UID_SIZE, OTP_SIZE, TS_SIZE, PUBKEY_SIZE = 64, 6, 8, 44
    PAYLOAD_SIZE = UID_SIZE + OTP_SIZE + TS_SIZE + PUBKEY_SIZE  # 122
    VERSION = b"\x00\x02\x00\x00"

    # Load server public key and generate ephemeral client keypair
    server_pub = X25519PublicKey.from_public_bytes(base64.b64decode(server_spa_pubkey_b64))
    eph_priv = X25519PrivateKey.generate()
    eph_pub_raw = eph_priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)

    # DH → HKDF → AES key
    shared = eph_priv.exchange(server_pub)
    hkdf = HKDF(algorithm=SHA256(), length=32, salt=b"spa-v2", info=b"spa-v2-aes-key")
    aes_key = hkdf.derive(shared)

    # Build plaintext payload: uid + otp + timestamp + wg_pubkey
    ts = int(time.time())
    payload = (
        uid_str.encode().ljust(UID_SIZE, b"\x00")[:UID_SIZE]
        + otp_str.encode().ljust(OTP_SIZE, b"\x00")[:OTP_SIZE]
        + struct.pack(">Q", ts)
        + wg_pubkey.encode().ljust(PUBKEY_SIZE, b"\x00")[:PUBKEY_SIZE]
    )

    # AES-256-GCM encrypt (returns ciphertext + 16-byte tag)
    nonce = os.urandom(12)
    ct_with_tag = AESGCM(aes_key).encrypt(nonce, payload, None)
    ciphertext = ct_with_tag[:PAYLOAD_SIZE]
    tag = ct_with_tag[PAYLOAD_SIZE:]

    return eph_pub_raw + nonce + ciphertext + tag + VERSION


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------

def _decode_jwt_exp(token: str) -> int:
    """Return JWT exp claim (Unix timestamp), or 0 on failure."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return 0
        padding = 4 - len(parts[1]) % 4
        payload = json.loads(base64.b64decode(parts[1] + "=" * padding))
        return int(payload.get("exp", 0))
    except Exception:
        return 0


def _token_valid(token: str) -> bool:
    return time.time() < _decode_jwt_exp(token) - 30  # 30 s buffer


def _do_login(server_url: str, username: str) -> Optional[str]:
    """Prompt for password, POST /auth/login, return JWT or None."""
    try:
        password = getpass.getpass(f"Password for {username}: ")
        resp = requests.post(
            f"{server_url.rstrip('/')}/auth/login",
            json={"username": username, "password": password},
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json().get("access_token")
        console.print(f"[red]Login failed:[/red] {resp.json().get('detail', resp.status_code)}")
    except Exception as exc:
        console.print(f"[red]Login error:[/red] {exc}")
    return None


# ---------------------------------------------------------------------------
# WireGuard helpers
# ---------------------------------------------------------------------------

def _wg_genkey() -> tuple[str, str]:
    """Generate a WireGuard keypair. Returns (privkey, pubkey) strings."""
    try:
        privkey = subprocess.check_output(
            ["wg", "genkey"], stderr=subprocess.DEVNULL
        ).decode().strip()
        pubkey = subprocess.check_output(
            ["wg", "pubkey"], input=privkey.encode(), stderr=subprocess.DEVNULL
        ).decode().strip()
        return privkey, pubkey
    except FileNotFoundError:
        console.print("[red]'wg' not found. Install wireguard-tools.[/red]")
        raise typer.Exit(1)
    except subprocess.CalledProcessError as exc:
        console.print(f"[red]Key generation failed:[/red] {exc}")
        raise typer.Exit(1)


def _wg_quick(action: str, target: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["sudo", "wg-quick", action, target],
        capture_output=True, text=True, check=check,
    )


def _wait_for_handshake(timeout: float = 10.0, interval: float = 0.5) -> bool:
    """Poll wg show until a handshake timestamp > 0 is seen."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = subprocess.run(
            ["sudo", "wg", "show", WG_IFACE, "latest-handshakes"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            for line in result.stdout.strip().splitlines():
                parts = line.split()
                if len(parts) >= 2 and int(parts[-1]) > 0:
                    return True
        time.sleep(interval)
    return False


def _write_wg_conf(
    privkey: str,
    my_ip: str,
    server_pubkey: str,
    server_endpoint: str,
    allowed_ips: str,
    dns: str = "",
) -> None:
    dns_line = f"DNS = {dns}\n" if dns else ""
    WG_CONF.write_text(
        f"[Interface]\n"
        f"PrivateKey = {privkey}\n"
        f"Address = {my_ip}/32\n"
        f"{dns_line}"
        f"\n"
        f"[Peer]\n"
        f"PublicKey = {server_pubkey}\n"
        f"Endpoint = {server_endpoint}\n"
        f"AllowedIPs = {allowed_ips}\n"
        f"PersistentKeepalive = 25\n"
    )
    os.chmod(WG_CONF, 0o600)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

@app.command("init")
def vpn_init(
    token: str = typer.Argument(..., help="Provision token from POST /vpn/admin/users/{u}/otp"),
) -> None:
    """
    Save VPN config from a provision token (non-interactive).

    The admin runs 'POST /vpn/admin/users/{you}/otp' and sends you the
    'provision_token' field. Paste it here — no other input needed.

    Example:
      anc vpn init eyJ1aWQiOiJhbGljZSIsInZwbl91aWQiOjIsInNlZWRfYjMyI...
      anc vpn up
    """
    try:
        cfg = _parse_provision_token(token.strip())
    except ValueError as exc:
        console.print(f"[red]Token error:[/red] {exc}")
        raise typer.Exit(1)

    _save_vpn_config(cfg)
    ip_hint = cfg.get("assigned_ip") or _uid_to_ip(cfg["vpn_uid"], cfg["subnet"])
    keypair_hint = " (keypair pre-generated by server)" if cfg.get("wg_privkey") else ""
    console.print(
        f"[green]VPN configured for user[/green] [bold]{cfg['uid']}[/bold] "
        f"[dim](IP: {ip_hint}{keypair_hint})[/dim]\n"
        f"Config saved to {VPN_CONFIG_FILE}"
    )

    seed = cfg.get("seed_b32", "")
    uid = cfg.get("uid", "")
    if seed and uid:
        # Full /provision token — seed is in token, show QR now
        from urllib.parse import quote
        purl = f"otpauth://totp/Anchor:{quote(uid)}?secret={seed}&issuer=Anchor"
        _show_qr(purl)
        console.print("[dim]Scan the QR with your authenticator app, then run [bold]anc vpn up[/bold][/dim]")
    else:
        # Standard /otp token — admin showed the QR separately via provisioning_url
        console.print(
            "\n[dim]Scan the QR your admin showed you (from provisioning_url) "
            "into your authenticator app, then run [bold]anc vpn up[/bold][/dim]"
        )


@app.command("up")
def vpn_up(
    totp_code: Optional[str] = typer.Argument(
        None,
        help="6-digit TOTP from your authenticator app. Prompted interactively if not given.",
    ),
) -> None:
    """
    Bring up the WireGuard VPN tunnel.

    Two modes depending on how the config was created:

    PRE-PROVISIONED (anc vpn init <token>): The admin pre-generated the keypair
    and registered the peer. Connect directly — no knock or promote needed.

    SPA KNOCK (manual setup): Send a UDP knock with your TOTP code, bring up a
    restricted onboarding tunnel, authenticate, then promote to the full tunnel.
    """
    _check_vpn_deps()

    # ── 1. Read / create config ──────────────────────────────────────────────
    cfg = _load_vpn_config()
    if not cfg:
        cfg = _run_wizard()

    uid: str = cfg["uid"]
    subnet: str = cfg.get("subnet", "10.8.0.0/24")
    server_vpn_uid: int = int(cfg.get("server_vpn_uid", 1))
    server_port: int = int(cfg.get("server_port", 17017))
    my_vpn_uid: int = int(cfg.get("vpn_uid", 0))
    server_endpoint_cfg: str = cfg["server_endpoint"]
    server_pubkey_cfg: str = cfg["server_pubkey"]

    server_vpn_ip = _uid_to_ip(server_vpn_uid, subnet)

    # IP: prefer pre-computed assigned_ip from token, then derive from vpn_uid
    if cfg.get("assigned_ip"):
        my_ip_str = cfg["assigned_ip"]
    elif my_vpn_uid > 0:
        my_ip_str = _uid_to_ip(my_vpn_uid, subnet)
    else:
        console.print(
            "[yellow]vpn_uid not set — using placeholder IP.[/yellow]\n"
            "Ask the admin for 'anc vpn init <token>'."
        )
        my_ip_str = _uid_to_ip(2, subnet)

    # ── PRE-PROVISIONED PATH ─────────────────────────────────────────────────
    # Server pre-generated the keypair (token contains wg_privkey).
    # Peer is already registered on the sidecar with state=active.
    # Flow: split-tunnel up → handshake → auth → /vpn/sync → hot-reload routes.
    if cfg.get("wg_privkey") and cfg.get("wg_pubkey"):
        privkey = cfg["wg_privkey"]
        server_pubkey = cfg.get("server_pubkey", server_pubkey_cfg)
        assigned_ip = cfg.get("assigned_ip", my_ip_str)

        with console.status("[bold]Bringing up VPN tunnel…"):
            # Start with split-tunnel (server IP only) so we can reach the API.
            _write_wg_conf(
                privkey=privkey,
                my_ip=assigned_ip,
                server_pubkey=server_pubkey,
                server_endpoint=server_endpoint_cfg,
                allowed_ips=f"{server_vpn_ip}/32",
            )
            result = _wg_quick("up", str(WG_CONF), check=False)
            if result.returncode != 0:
                console.print(f"[red]wg-quick up failed:[/red]\n{result.stderr.strip()}")
                raise typer.Exit(1)

        with console.status("[bold]Waiting for handshake…"):
            ok = _wait_for_handshake(timeout=15.0)

        if not ok:
            _wg_quick("down", WG_IFACE, check=False)
            console.print(
                "[red]Handshake timeout (15 s).[/red]\n"
                "Possible causes:\n"
                "  • server_endpoint misconfigured (check host:port)\n"
                "  • WireGuard UDP port unreachable (check firewall)\n"
                "  • Peer was revoked — ask admin to re-provision"
            )
            raise typer.Exit(1)

        # Authenticate via VPN tunnel to fetch current routes from /vpn/sync
        internal_url = f"http://{server_vpn_ip}:{server_port}"
        token: Optional[str] = None

        creds = load_credentials()
        existing_token = creds.get("token")
        if existing_token and _token_valid(existing_token):
            token = existing_token
            console.print("[dim]Using cached credentials.[/dim]")
        else:
            console.print(f"[bold]Authenticating via VPN tunnel ({internal_url})…[/bold]")
            token = _do_login(internal_url, uid)
            if token:
                creds["token"] = token
                save_credentials(creds)

        if not token:
            # Auth failed but tunnel is up — still usable with token routes
            console.print("[yellow]Auth failed — using routes from provision token.[/yellow]")
            routes_list: list[str] = cfg.get("routes", ["0.0.0.0/0"])
        else:
            # Fetch current routes from server
            try:
                internal_client = AnchorClient(server_url=internal_url, token=token)
                sync_resp = internal_client.get("/vpn/sync")
                if sync_resp.status_code == 200:
                    routes_list = sync_resp.json().get("routes", ["0.0.0.0/0"])
                else:
                    routes_list = cfg.get("routes", ["0.0.0.0/0"])
            except AnchorClientError:
                routes_list = cfg.get("routes", ["0.0.0.0/0"])

        # Hot-reload with full routes (no tunnel drop)
        _write_wg_conf(
            privkey=privkey,
            my_ip=assigned_ip,
            server_pubkey=server_pubkey,
            server_endpoint=server_endpoint_cfg,
            allowed_ips=", ".join(routes_list),
        )
        syncconf = subprocess.run(
            f"sudo wg syncconf {WG_IFACE} <(sudo wg-quick strip {WG_CONF})",
            shell=True, executable="/bin/bash",
            capture_output=True, text=True,
        )
        if syncconf.returncode != 0:
            console.print(f"[yellow]wg syncconf warning:[/yellow] {syncconf.stderr.strip()}")

        table = Table.grid(padding=(0, 2))
        table.add_column(style="dim")
        table.add_column()
        table.add_row("IP address", f"[green]{assigned_ip}[/green]")
        table.add_row("Routes", ", ".join(routes_list))
        table.add_row("Server endpoint", server_endpoint_cfg)
        table.add_row("Server pubkey", server_pubkey[:16] + "…")
        table.add_row("Interface", WG_IFACE)
        console.print(Panel(table, title="[bold green]VPN Connected", border_style="green"))
        return

    # ── SPA KNOCK PATH ───────────────────────────────────────────────────────
    # Knock-based setup: uses user-supplied TOTP + SPA v2 ECIES to register peer.
    spa_pubkey_b64: str = cfg["spa_pubkey"]
    knock_host: str = cfg["knock_host"]
    knock_port: int = int(cfg.get("knock_port", 62201))

    # ── 2. Generate keypair ──────────────────────────────────────────────────
    with console.status("[bold]Generating keypair…"):
        privkey, pubkey = _wg_genkey()

    # ── 3. Get TOTP from user and send knock ─────────────────────────────────
    if totp_code:
        otp_str = totp_code.strip()
    else:
        otp_str = Prompt.ask("[cyan]Enter TOTP from your authenticator app")
    pkt = _build_spa_packet(uid, otp_str, pubkey, spa_pubkey_b64)

    with console.status(f"[bold]Knocking {knock_host}:{knock_port}…"):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.sendto(pkt, (knock_host, knock_port))
            sock.close()
        except Exception as exc:
            console.print(f"[red]UDP send failed:[/red] {exc}")
            raise typer.Exit(1)

    # ── 4. Write restricted tunnel config + bring up ─────────────────────────
    with console.status("[bold]Bringing up tunnel (onboarding mode)…"):
        time.sleep(2.0)  # allow knock packet to be processed by sidecar

        _write_wg_conf(
            privkey=privkey,
            my_ip=my_ip_str,
            server_pubkey=server_pubkey_cfg,
            server_endpoint=server_endpoint_cfg,
            allowed_ips=f"{server_vpn_ip}/32",
        )

        result = _wg_quick("up", str(WG_CONF), check=False)
        if result.returncode != 0:
            console.print(f"[red]wg-quick up failed:[/red]\n{result.stderr.strip()}")
            raise typer.Exit(1)

    # ── 5. Wait for handshake ────────────────────────────────────────────────
    with console.status("[bold]Waiting for tunnel handshake…"):
        ok = _wait_for_handshake(timeout=20.0)

    if not ok:
        _wg_quick("down", WG_IFACE, check=False)
        console.print(
            "[red]Handshake timeout (20 s).[/red]\n"
            "Possible causes:\n"
            "  • Knock was dropped — wrong TOTP code or seed mismatch\n"
            "  • knock_host / knock_port misconfigured (check vpn.toml)\n"
            "  • Sidecar could not add peer (check server logs)\n"
            "  • WireGuard UDP port 51820 unreachable (check firewall)\n"
            "  • Run: docker exec anc-server tail -f /var/log/... for server logs"
        )
        raise typer.Exit(1)

    # ── 6. Authenticate ──────────────────────────────────────────────────────
    # NOTE: getpass MUST run outside any console.status() context — Rich's
    # live-rendering overrides terminal line-discipline and the password
    # prompt becomes invisible / unresponsive.
    internal_url = f"http://{server_vpn_ip}:{server_port}"
    token: Optional[str] = None

    creds = load_credentials()
    existing_token = creds.get("token")
    if existing_token and _token_valid(existing_token):
        token = existing_token
        console.print("[dim]Using cached credentials.[/dim]")
    else:
        console.print(f"[bold]Authenticating via VPN tunnel ({internal_url})…[/bold]")
        token = _do_login(internal_url, uid)
        if token:
            creds["token"] = token
            save_credentials(creds)

    if not token:
        _wg_quick("down", WG_IFACE, check=False)
        console.print("[red]Authentication failed. Tunnel closed.[/red]")
        raise typer.Exit(1)

    # ── 7. POST /vpn/promote ─────────────────────────────────────────────────
    with console.status("[bold]Promoting to full tunnel…"):
        try:
            internal_client = AnchorClient(server_url=internal_url, token=token)
            resp = internal_client.post("/vpn/promote")
        except AnchorClientError as exc:
            _wg_quick("down", WG_IFACE, check=False)
            console.print(f"[red]Promote request failed:[/red] {exc}")
            raise typer.Exit(1)

        if resp.status_code != 200:
            _wg_quick("down", WG_IFACE, check=False)
            detail = resp.json().get("detail", resp.status_code)
            console.print(f"[red]Promote failed:[/red] {detail}")
            raise typer.Exit(1)

        promote_data = resp.json()

    # ── 8. Rewrite config + hot-reload ───────────────────────────────────────
    assigned_ip: str = promote_data["assigned_ip"]
    server_pubkey: str = promote_data["server_pubkey"]
    server_endpoint: str = promote_data["server_endpoint"]
    lease_expires: str = promote_data["lease_expires"]
    routes_list: list[str] = promote_data.get("routes", ["0.0.0.0/0"])

    # Update cached values for next run
    cfg["server_pubkey"] = server_pubkey
    cfg["server_endpoint"] = server_endpoint
    if cfg.get("vpn_uid", 0) == 0:
        net = ipaddress.IPv4Network(subnet, strict=False)
        cfg["vpn_uid"] = int(ipaddress.IPv4Address(assigned_ip)) - int(net.network_address)
    _save_vpn_config(cfg)

    _write_wg_conf(
        privkey=privkey,
        my_ip=assigned_ip,
        server_pubkey=server_pubkey,
        server_endpoint=server_endpoint,
        allowed_ips=", ".join(routes_list),
    )

    # Hot-reload without dropping the tunnel
    syncconf = subprocess.run(
        f"sudo wg syncconf {WG_IFACE} <(sudo wg-quick strip {WG_CONF})",
        shell=True, executable="/bin/bash",
        capture_output=True, text=True,
    )
    if syncconf.returncode != 0:
        console.print(f"[yellow]wg syncconf warning:[/yellow] {syncconf.stderr.strip()}")

    # ── 9. Show summary panel ────────────────────────────────────────────────
    table = Table.grid(padding=(0, 2))
    table.add_column(style="dim")
    table.add_column()
    table.add_row("IP address", f"[green]{assigned_ip}[/green]")
    table.add_row("Routes", ", ".join(routes_list))
    table.add_row("Server endpoint", server_endpoint)
    table.add_row("Server pubkey", server_pubkey[:16] + "…")
    table.add_row("Lease expires", lease_expires.replace("T", " ").split(".")[0] + " UTC")
    table.add_row("Interface", WG_IFACE)

    console.print(Panel(table, title="[bold green]VPN Connected", border_style="green"))


@app.command("down")
def vpn_down() -> None:
    """Bring down the VPN tunnel and revoke the server lease."""
    result = _wg_quick("down", WG_IFACE, check=False)
    if result.returncode == 0:
        console.print(f"[green]Interface {WG_IFACE} down.[/green]")
    else:
        console.print(f"[yellow]{result.stderr.strip() or 'Interface not active.'}[/yellow]")

    # Best-effort: revoke lease on server
    try:
        client = AnchorClient()
        resp = client.delete("/vpn/lease")
        if resp.status_code == 200:
            console.print("[dim]Server lease revoked.[/dim]")
    except Exception:
        pass  # server unreachable or no lease — ignore


@app.command("status")
def vpn_status() -> None:
    """Show VPN status: server lease info and local wg show output."""
    # Server lease
    try:
        client = AnchorClient()
        resp = client.get("/vpn/status")
        if resp.status_code == 200:
            lease = resp.json()
            table = Table.grid(padding=(0, 2))
            table.add_column(style="dim")
            table.add_column()
            for k, v in lease.items():
                if k != "_id":
                    table.add_row(k, str(v))
            console.print(Panel(table, title="[bold]Server Lease"))
        elif resp.status_code == 404:
            console.print("[yellow]No active VPN lease on server.[/yellow]")
        else:
            console.print(f"[red]Server error:[/red] {resp.status_code}")
    except NotAuthenticatedError:
        console.print("[yellow]Not authenticated. Run: anc login[/yellow]")
    except AnchorClientError as exc:
        console.print(f"[red]Cannot reach server:[/red] {exc}")

    # Local wg status
    result = subprocess.run(
        ["sudo", "wg", "show", WG_IFACE],
        capture_output=True, text=True,
    )
    if result.returncode == 0 and result.stdout.strip():
        console.print(Panel(result.stdout.strip(), title=f"[bold]{WG_IFACE} (local)"))
    else:
        console.print(f"[dim]Interface {WG_IFACE} not active.[/dim]")
