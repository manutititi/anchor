"""
SshHandler — handle 'ssh' type anchors using the native ssh client.

Estrategia de inyección de claves (cero escrituras a disco):

    PEM del vault → ssh-agent temporal en RAM:
        1. ssh-agent -a <socket en tmpdir 0700>   (agente aislado)
        2. ssh-add - < pipe(key_bytes)            (stdin, nunca en disco)
        3. ssh con SSH_AUTH_SOCK=socket            (cliente nativo)
        4. kill agent                              (clave desaparece de RAM)

    key = path de archivo  → ssh -i /ruta  (usuario guardó el path, no la clave)
    password del vault     → sshpass -d N  (pipe fd, no en cmdline)
    sin auth configurada   → ssh defaults  (agent del sistema / ~/.ssh/config)
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import tempfile
from typing import Optional, TYPE_CHECKING

from anchor.handlers import Handler
from anchor.utils.output import err, out, warn
from anchor.utils.secrets import resolve_field

if TYPE_CHECKING:
    from anchor.client import AnchorClient
    from anchor.models.anchor import SshAnchor


class SshHandler(Handler):
    def handle(self, anchor: "SshAnchor", client: "AnchorClient | None" = None) -> None:
        host: str = anchor.host
        user: str = anchor.user
        port: int = getattr(anchor, "port", 22) or 22

        raw_key: Optional[str] = getattr(anchor, "key", None)
        raw_pass: Optional[str] = getattr(anchor, "password", None)

        # Resolver [[secret:...]] — resultado queda solo en memoria
        key_str: Optional[str] = resolve_field(raw_key, client)
        password: Optional[str] = resolve_field(raw_pass, client)

        out.print(
            f"[dim]Connecting to [bold]{user}@{host}[/bold]"
            + (f":[bold]{port}[/bold]" if port != 22 else "")
            + "…[/dim]"
        )

        _connect(host, user, port, key_str, password)


# ---------------------------------------------------------------------------
# Núcleo de conexión
# ---------------------------------------------------------------------------

def _connect(
    host: str,
    user: str,
    port: int,
    key_str: Optional[str],
    password: Optional[str],
) -> None:
    dest = f"{user}@{host}"
    base = ["ssh", "-p", str(port)]

    if key_str and _is_pem(key_str):
        _connect_via_agent(dest, port, key_str, base)

    elif key_str:
        # Path de archivo guardado en el anchor
        subprocess.run(base + ["-i", os.path.expanduser(key_str), dest])

    elif password:
        _connect_with_password(dest, password, base)

    else:
        # Sin auth → ssh usa agent del sistema / ~/.ssh/config
        subprocess.run(base + [dest])


# ---------------------------------------------------------------------------
# Estrategia 1: agente SSH temporal para clave PEM en memoria
# ---------------------------------------------------------------------------

def _connect_via_agent(
    dest: str,
    port: int,
    key_str: str,
    base: list[str],
) -> None:
    """Carga la clave en un ssh-agent efímero (solo RAM), conecta, mata el agente."""
    for binary in ("ssh-agent", "ssh-add"):
        if not shutil.which(binary):
            raise RuntimeError(
                f"{binary} no encontrado. "
                "Instala openssh-client: sudo apt install openssh-client"
            )

    # tmpdir con permisos 0700 — solo el usuario puede acceder al socket
    with tempfile.TemporaryDirectory(prefix="anc-") as tmpdir:
        os.chmod(tmpdir, 0o700)
        sock = os.path.join(tmpdir, "agent.sock")

        # Arrancar agente aislado (socket propio, no el del sistema)
        r = subprocess.run(
            ["ssh-agent", "-a", sock],
            capture_output=True,
            text=True,
        )
        if r.returncode != 0:
            raise RuntimeError(f"No se pudo iniciar ssh-agent: {r.stderr.strip()}")

        agent_pid = _parse_agent_pid(r.stdout)
        env = {**os.environ, "SSH_AUTH_SOCK": sock}

        try:
            # Normalizar la clave antes de pasarla al agente
            key_bytes = _normalize_pem(key_str).encode()

            # Cargar clave desde stdin — nunca toca el disco
            add = subprocess.run(
                ["ssh-add", "-"],
                input=key_bytes,
                env=env,
                stderr=subprocess.PIPE,  # capturar solo errores; stdout al terminal
            )
            if add.returncode != 0:
                stderr_out = add.stderr.decode().strip()
                hint = _key_error_hint(key_str, stderr_out)
                raise RuntimeError(
                    f"No se pudo cargar la clave en el agente.\n"
                    f"  {hint}\n"
                    f"  Error: {stderr_out}"
                )

            # El agente temporal solo contiene nuestra clave — no hace falta
            # IdentitiesOnly (que bloquearía el uso del agente).
            subprocess.run(base + [dest], env=env)

        finally:
            # Matar agente — la clave desaparece de RAM inmediatamente
            if agent_pid:
                try:
                    os.kill(agent_pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass


# ---------------------------------------------------------------------------
# Estrategia 2: contraseña via pipe a sshpass
# ---------------------------------------------------------------------------

def _connect_with_password(
    dest: str,
    password: str,
    base: list[str],
) -> None:
    if not shutil.which("sshpass"):
        warn(
            "sshpass no encontrado — se pedirá la contraseña interactivamente.\n"
            "  Instala sshpass para inyectarla automáticamente: "
            "sudo apt install sshpass"
        )
        subprocess.run(base + [dest])
        return

    # sshpass -d N lee del fd N, no de args → no aparece en /proc/<pid>/cmdline
    r_fd, w_fd = os.pipe()
    try:
        os.write(w_fd, (password + "\n").encode())
        os.close(w_fd)
        w_fd = -1
        subprocess.run(["sshpass", "-d", str(r_fd)] + base + [dest], pass_fds=(r_fd,))
    finally:
        for fd in (w_fd, r_fd):
            if fd != -1:
                try:
                    os.close(fd)
                except OSError:
                    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_pem(text: str) -> bool:
    return text.strip().startswith("-----BEGIN")


def _normalize_pem(key_str: str) -> str:
    """Normalizar una clave PEM antes de pasarla a ssh-add.

    Problema habitual: los saltos de línea se almacenan como literales \\n
    (dos caracteres) en lugar de newlines reales al guardar la clave en JSON
    o en el vault. OpenSSL no puede parsear el PEM en ese estado.
    """
    # Caso: la clave llegó como una línea única con \\n literales
    # Ej: "-----BEGIN RSA PRIVATE KEY-----\\nMIIE...\\n-----END..."
    if "\\n" in key_str and "\n" not in key_str:
        key_str = key_str.replace("\\n", "\n")

    # Normalizar CRLF → LF
    key_str = key_str.replace("\r\n", "\n").replace("\r", "\n")

    # Asegurar newline al final (ssh-add lo requiere)
    if not key_str.endswith("\n"):
        key_str += "\n"

    return key_str


def _key_error_hint(key_str: str, stderr: str) -> str:
    """Produce una pista útil basada en el contenido de la clave y el error."""
    first_line = key_str.strip().splitlines()[0] if key_str.strip() else ""

    if "libcrypto" in stderr or "invalid format" in stderr.lower():
        if "\\n" in key_str:
            return "La clave parece tener saltos de línea escapados (\\\\n en lugar de newlines)."
        if not first_line.startswith("-----BEGIN"):
            return "La clave no empieza con '-----BEGIN ...' — verifica que el secret contiene el PEM completo."
        return "Formato de clave no válido para OpenSSL. Verifica que el PEM está completo y sin caracteres extra."

    if "passphrase" in stderr.lower() or "bad passphrase" in stderr.lower():
        return "La clave está protegida con passphrase. Almacena también la passphrase en el vault y añádela al anchor."

    return "Verifica el formato de la clave (RSA / Ed25519 / ECDSA)."


def _parse_agent_pid(agent_output: str) -> Optional[int]:
    for line in agent_output.splitlines():
        if line.startswith("SSH_AGENT_PID="):
            try:
                return int(line.split("=", 1)[1].rstrip(";"))
            except ValueError:
                pass
    return None
