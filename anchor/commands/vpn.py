"""
VPN commands — WireGuard tunnel management via SPA (Single Packet Authorization).

  anc vpn up     — full flow: SPA knock → onboarding tunnel → promote → full tunnel
  anc vpn down   — bring down the VPN tunnel and best-effort revoke server lease
  anc vpn status — show server lease info + local wg show

First-time setup: 'anc vpn up' runs an interactive wizard that saves
~/.config/anchor/vpn.toml (mode 0600).

Dependencies (install with pip install 'anchor-cli[vpn]'):
  pyotp>=2.9       — TOTP code generation
  pycryptodome>=3  — AES-256-GCM for SPA packet

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


def _run_wizard() -> dict:
    """Interactive first-time setup wizard. Returns the saved config dict."""
    console.print()
    console.print(Panel(
        "[bold]VPN First-Time Setup[/bold]\n"
        "Your admin should have given you a TOTP provisioning URL or QR code.\n"
        "You can find your [cyan]uid[/cyan] and [cyan]seed_b32[/cyan] in that URL:\n"
        "  [dim]otpauth://totp/Anchor:[cyan]uid[/cyan]?secret=[cyan]SEED[/cyan]&issuer=Anchor[/dim]",
        title="[bold blue]anc vpn setup",
    ))
    console.print()

    uid = Prompt.ask("[cyan]Your username (uid)")
    seed_b32 = Prompt.ask("[cyan]TOTP seed (base32, from provisioning URL)")
    knock_host = Prompt.ask("[cyan]Knock server hostname or IP")
    knock_port = int(Prompt.ask("[cyan]Knock UDP port", default="62201"))
    subnet = Prompt.ask("[cyan]VPN subnet", default="10.8.0.0/24")
    server_vpn_uid = int(Prompt.ask("[cyan]Server VPN UID (usually 1)", default="1"))
    server_port = int(Prompt.ask("[cyan]Anchor server internal port", default="17017"))

    cfg = {
        "uid": uid,
        "seed_b32": seed_b32,
        "knock_host": knock_host,
        "knock_port": knock_port,
        "subnet": subnet,
        "server_vpn_uid": server_vpn_uid,
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
    missing = []
    try:
        import pyotp  # noqa: F401
    except ImportError:
        missing.append("pyotp")
    try:
        from Crypto.Cipher import AES  # noqa: F401
    except ImportError:
        missing.append("pycryptodome")
    if missing:
        console.print(
            f"[red]Missing VPN dependencies: {', '.join(missing)}[/red]\n"
            "Install with: [bold]pip install 'anchor-cli[vpn]'[/bold]"
        )
        raise typer.Exit(1)


def _uid_to_ip(uid: int, subnet: str) -> str:
    net = ipaddress.IPv4Network(subnet, strict=False)
    return str(net.network_address + uid)


def _build_spa_packet(uid_str: str, otp_str: str, wg_pubkey: str, seed_b32: str) -> bytes:
    """
    Build the 154-byte SPA UDP packet.
    Mirrors server/code/vpn/spa.py:build_packet() exactly.
    """
    from Crypto.Cipher import AES
    from Crypto.Hash import SHA256
    from Crypto.Protocol.KDF import HKDF
    from Crypto.Random import get_random_bytes

    UID_SIZE, NONCE_SIZE, OTP_SIZE, TS_SIZE, PUBKEY_SIZE = 64, 16, 6, 8, 44

    seed_bytes = base64.b32decode(seed_b32)
    key = HKDF(
        master=seed_bytes,
        key_len=32,
        salt=b"spa-v1",
        hashmod=SHA256,
        context=uid_str.encode(),
    )

    ts = int(time.time())
    uid_raw = uid_str.encode().ljust(UID_SIZE, b"\x00")[:UID_SIZE]
    nonce = get_random_bytes(NONCE_SIZE)
    plaintext = (
        otp_str.encode().ljust(OTP_SIZE, b"\x00")[:OTP_SIZE]
        + struct.pack(">Q", ts)
        + wg_pubkey.encode().ljust(PUBKEY_SIZE, b"\x00")[:PUBKEY_SIZE]
    )
    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
    ciphertext, tag = cipher.encrypt_and_digest(plaintext)
    return uid_raw + nonce + ciphertext + tag


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
    dns: str = "1.1.1.1",
) -> None:
    WG_CONF.write_text(
        f"[Interface]\n"
        f"PrivateKey = {privkey}\n"
        f"Address = {my_ip}/32\n"
        f"DNS = {dns}\n"
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

@app.command("up")
def vpn_up() -> None:
    """
    Bring up the WireGuard VPN tunnel via SPA knock flow.

    First run: interactive wizard collects uid, TOTP seed, knock host/port,
    subnet, and saves to ~/.config/anchor/vpn.toml (0600).
    Subsequent runs: reads saved config and goes straight to tunnel setup.
    """
    _check_vpn_deps()
    import pyotp

    # ── 1. Read / create config ──────────────────────────────────────────────
    cfg = _load_vpn_config()
    if not cfg:
        cfg = _run_wizard()

    uid: str = cfg["uid"]
    seed_b32: str = cfg["seed_b32"]
    knock_host: str = cfg["knock_host"]
    knock_port: int = int(cfg.get("knock_port", 62201))
    subnet: str = cfg.get("subnet", "10.8.0.0/24")
    server_vpn_uid: int = int(cfg.get("server_vpn_uid", 1))
    server_port: int = int(cfg.get("server_port", 17017))

    server_vpn_ip = _uid_to_ip(server_vpn_uid, subnet)
    my_vpn_uid = None   # filled after knock + server info is available
    my_ip_str = None    # filled once we know our uid (need server's assigned_ip)

    # ── 2. Generate WireGuard keypair ────────────────────────────────────────
    with console.status("[bold]Generating keypair…"):
        privkey, pubkey = _wg_genkey()

    # ── 3. Generate OTP ──────────────────────────────────────────────────────
    otp_str = pyotp.TOTP(seed_b32).now()

    # ── 4. Build + send SPA packet ───────────────────────────────────────────
    pkt = _build_spa_packet(uid, otp_str, pubkey, seed_b32)

    with console.status(f"[bold]Knocking {knock_host}:{knock_port}…"):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.sendto(pkt, (knock_host, knock_port))
            sock.close()
        except Exception as exc:
            console.print(f"[red]UDP send failed:[/red] {exc}")
            raise typer.Exit(1)

    # ── 5. Write restricted tunnel config + bring up ─────────────────────────
    #   AllowedIPs restricted to server_ip/32 so only the server is reachable
    #   through the tunnel (onboarding mode; no internet routing yet).
    #   We use a placeholder pubkey — will be filled after sidecar responds.
    #   Write config with server_ip/32 for now; promote will give us the real
    #   server pubkey.  We need at least the server endpoint to write a conf.
    #   Use a dummy server pubkey initially — wg-quick won't connect without
    #   a valid one, so we need to wait for the promote response first.
    #
    #   Strategy: write a minimal conf with the server's expected VPN IP as
    #   endpoint. The actual server pubkey comes from the promote response.
    #   Until then, we poll on the client side.
    #
    #   Simpler approach: write conf after promote, but we need the tunnel up
    #   to reach /vpn/promote. This circular dependency is resolved by:
    #     a) Pause ~1s for knock to register the peer on the server
    #     b) Write conf with server_ip/32 AllowedIPs + real server pubkey
    #        (obtained via GET /status on the sidecar — but we can't reach it
    #        without a tunnel). We use the placeholder and rely on the server
    #        to accept our pubkey.
    #
    #   Practical solution used here:
    #     - The knock server registers our peer; the tunnel will establish as
    #       soon as both sides have each other's pubkeys.
    #     - We write the conf with knock_host as the WireGuard endpoint
    #       (same host, different port — WG port is in knock_host config but
    #       the server_endpoint from the provisioning URL has the WG UDP port).
    #     - We get server_pubkey from the promote response (after the tunnel
    #       is up using a temporary conf).
    #
    #   Since we don't know server_pubkey before the tunnel is up, we must
    #   do a 2-step approach:
    #     Step A: bring up tunnel in "stub" mode with a temp placeholder,
    #             OR rely on the user having pre-configured server_pubkey.
    #
    #   Final resolution: store server_pubkey in vpn.toml after first successful
    #   promote. On subsequent runs, reuse it. On first run, require it in wizard.

    server_pubkey_cached: str = cfg.get("server_pubkey", "")
    if not server_pubkey_cached:
        console.print(
            "\n[yellow]Tip:[/yellow] server_pubkey not in config. "
            "After first 'anc vpn up' the key will be cached automatically.\n"
            "Ask your admin for the WireGuard server public key if this is your first time."
        )
        server_pubkey_cached = Prompt.ask("[cyan]WireGuard server public key")
        cfg["server_pubkey"] = server_pubkey_cached
        _save_vpn_config(cfg)

    with console.status("[bold]Bringing up tunnel (onboarding mode)…"):
        # Pause briefly to allow the knock to propagate to the sidecar
        time.sleep(1.0)

        _write_wg_conf(
            privkey=privkey,
            my_ip=_uid_to_ip(0, subnet),  # placeholder; will be overwritten
            server_pubkey=server_pubkey_cached,
            server_endpoint=f"{knock_host}:51820",  # WireGuard default; overridden later
            allowed_ips=f"{server_vpn_ip}/32",
        )

        # We don't know our assigned_ip yet — write a placeholder and wait
        # for the promote response to give us the real IP.
        # wg-quick requires a valid Address; derive it from uid if configured.
        my_uid_int: Optional[int] = cfg.get("vpn_uid")
        if my_uid_int:
            my_ip_str = _uid_to_ip(int(my_uid_int), subnet)
        else:
            my_ip_str = _uid_to_ip(2, subnet)  # fallback; corrected after promote

        _write_wg_conf(
            privkey=privkey,
            my_ip=my_ip_str,
            server_pubkey=server_pubkey_cached,
            server_endpoint=f"{knock_host}:51820",
            allowed_ips=f"{server_vpn_ip}/32",
        )

        result = _wg_quick("up", str(WG_CONF), check=False)
        if result.returncode != 0:
            console.print(f"[red]wg-quick up failed:[/red]\n{result.stderr.strip()}")
            raise typer.Exit(1)

    # ── 6. Wait for handshake ────────────────────────────────────────────────
    with console.status("[bold]Waiting for tunnel handshake…"):
        ok = _wait_for_handshake(timeout=10.0)

    if not ok:
        _wg_quick("down", WG_IFACE, check=False)
        console.print(
            "[red]Handshake timeout (10 s).[/red]\n"
            "Possible causes:\n"
            "  • knock_host / knock_port misconfigured\n"
            "  • clock skew > 2 s (OTP window)\n"
            "  • wrong seed or uid\n"
            "  • WireGuard UDP port unreachable (check firewall)"
        )
        raise typer.Exit(1)

    # ── 7. Authenticate ──────────────────────────────────────────────────────
    internal_url = f"http://{server_vpn_ip}:{server_port}"
    token: Optional[str] = None

    with console.status("[bold]Authenticating…"):
        creds = load_credentials()
        existing_token = creds.get("token")
        if existing_token and _token_valid(existing_token):
            token = existing_token
        else:
            console.print()  # newline before getpass
            token = _do_login(internal_url, uid)
            if token:
                creds["token"] = token
                save_credentials(creds)

    if not token:
        _wg_quick("down", WG_IFACE, check=False)
        console.print("[red]Authentication failed. Tunnel closed.[/red]")
        raise typer.Exit(1)

    # ── 8. POST /vpn/promote ─────────────────────────────────────────────────
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

    # ── 9. Rewrite config + hot-reload ───────────────────────────────────────
    assigned_ip: str = promote_data["assigned_ip"]
    server_pubkey: str = promote_data["server_pubkey"]
    server_endpoint: str = promote_data["server_endpoint"]
    lease_expires: str = promote_data["lease_expires"]

    # Cache server_pubkey + vpn_uid for next run
    cfg["server_pubkey"] = server_pubkey
    # Parse uid from assigned_ip to store as vpn_uid
    try:
        net = ipaddress.IPv4Network(promote_data.get("subnet", subnet), strict=False)
    except Exception:
        net = ipaddress.IPv4Network(subnet, strict=False)
    ip_obj = ipaddress.IPv4Address(assigned_ip)
    cfg["vpn_uid"] = int(ip_obj) - int(net.network_address)
    _save_vpn_config(cfg)

    _write_wg_conf(
        privkey=privkey,
        my_ip=assigned_ip,
        server_pubkey=server_pubkey,
        server_endpoint=server_endpoint,
        allowed_ips="0.0.0.0/0",
    )

    # Hot-reload without dropping the tunnel
    syncconf = subprocess.run(
        f"sudo wg syncconf {WG_IFACE} <(sudo wg-quick strip {WG_CONF})",
        shell=True, executable="/bin/bash",
        capture_output=True, text=True,
    )
    if syncconf.returncode != 0:
        console.print(f"[yellow]wg syncconf warning:[/yellow] {syncconf.stderr.strip()}")

    # ── 10. Show summary panel ───────────────────────────────────────────────
    table = Table.grid(padding=(0, 2))
    table.add_column(style="dim")
    table.add_column()
    table.add_row("IP address", f"[green]{assigned_ip}[/green]")
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
