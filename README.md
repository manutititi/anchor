# Anchor

A developer tool designed to reduce context-switching and protect secrets for small and medium engineering teams. It combines a local CLI for navigating infrastructure with an optional self-hosted server that acts as a secure secret vault — secrets are resolved at runtime, kept in memory only, and never written to disk.

The CLI can be used standalone. The server adds vault-backed secret resolution, team sync, and a WireGuard VPN gateway.

---

## Architecture

```
Developer machine                    Self-hosted server (optional)
-----------------                    --------------------------------
anc (CLI)                            Anchor Vault Server (FastAPI)
  - local anchors (~/.anchors/data)    - MongoDB (encrypted secrets)
  - shell wrapper (anc.sh)             - JWT + service token auth
  - WireGuard client (anc vpn)         - WireGuard control plane
  - rsync transfers (anc cp)           - REST API on port 17017
  - vault resolution at runtime  <-->  - Web UI (/ui)
```

The server has its own documentation in [server/README.md](server/README.md).

---

## Goal

Anchor aims to be the **context layer for infrastructure access** — a bastion that knows where things are, who can reach them, and how credentials travel. Secrets are injected at the moment of use (SSH session, file restore, rsync transfer) and discarded immediately after. Nothing sensitive touches disk.

The target is teams that manage multiple environments, servers, and credentials without the overhead of enterprise secrets platforms.

---

## Installation

```bash
git clone <repo>
cd anchor
./install.sh
source ~/.bashrc
```

`install.sh` checks required system dependencies (`ssh`, `rsync`, `jq`, `sshpass`, `wg`, `wg-quick`), creates a Python venv at `~/.anchors/venv`, installs the package non-editable (code is independent of the source directory), copies the shell wrapper, and adds the necessary lines to `.bashrc`/`.zshrc`.

Re-running `install.sh` upgrades the installation.

**Requirements:** Python 3.10+, the system dependencies above, and a Linux host for VPN features.

---

## How Secrets Are Protected

SSH keys and passwords stored in anchors reference vault paths (`[[secret:vault/path]]`) rather than literal values. When a command needs them:

1. The CLI fetches the plaintext from the vault over HTTPS (JWT-authenticated).
2. For SSH keys: the PEM is loaded into an isolated, ephemeral `ssh-agent` process via stdin pipe. The key never touches disk. The agent is killed after the operation.
3. For passwords: passed to `sshpass` through a file descriptor pipe. The value never appears in process arguments or command history.
4. For rsync transfers: the same agent injection is used to authenticate the underlying SSH connection.

---

## CLI Reference


## add here the basic for anc <name> and it goes to ssh local or url 


### Authentication

```bash
anc login                            # Authenticate against the server, save token
anc login --url https://host:17017
```

---

### Anchors

Anchors are JSON objects stored in `~/.anchors/data/`. Types: `local`, `ssh`, `url`, `files`.

```bash
# Create anchors
anc set                              # Local anchor for current directory
anc set --path myproject ~/projects/myproject
anc set --ssh prodserver user@host:22 -i ~/.ssh/id_rsa
anc set --ssh prodserver user@host:22 --key-secret vault/ssh/prod
anc set --url api https://api.example.com

# Navigate
anc myproject                        # cd into local anchor (instant, no Python)
anc prodserver                       # Open SSH session to server

# List
anc ls                               # All local anchors
anc ls -t ssh                        # Filter by type
anc ls -f "meta.env=prod"            # Filter by metadata
anc ls -r                            # List anchors on the server
anc ls -r -f "type=ssh"

# Sync with server
anc push myproject                   # Upload anchor to server
anc pull myproject                   # Download anchor from server
anc pull -f "type=ssh"              # Pull all matching anchors
anc pull --all

# Inspect
anc path myproject                   # Print path (for scripting: cd $(anc path x))
anc go prodserver --pubkey           # Print SSH public key from vault
```

---

### Secrets

```bash
anc secret push vault/myapp/db_pass              # Create (prompts for value)
anc secret push vault/myapp/db_pass --file .env  # From file
anc secret get vault/myapp/db_pass               # Print plaintext
anc secret get vault/myapp/db_pass --out /tmp/f  # Write to file (mode 0600)
anc secret ls                                    # List visible secrets
anc secret ls myapp/                             # Filter by prefix
anc secret update vault/myapp/db_pass            # Update (creates new version)
anc secret del vault/myapp/db_pass               # Delete
```

Access control is per-secret: `--users alice,bob`, `--groups devops`, `--gedit` (allow group edit). Secrets support up to 10 versions.

---

### File Capture and Restore

```bash
# Capture
anc cr myconfig                      # Capture current directory
anc cr myconfig /etc/nginx.conf      # Capture a specific file
anc cr myconfig src/ --mode replace  # Capture directory with write mode
anc cr myconfig /etc/hosts --blank   # Capture metadata only (no content)

# Restore
anc rc myconfig                      # Restore to original paths
anc rc myconfig /opt/deploy          # Restore relative files under /opt/deploy
anc rc myconfig --yes                # Skip confirmation

# Write modes: replace (default), append, prepend, regex
# Absolute paths (~/... or /...) restore to original location.
# Relative paths restore under the target directory.
# Privilege escalation is automatic for system paths (/etc, /usr, /opt, /root).
```

---

### File Transfer

```bash
anc cp src/ dst/                           # Local to local
anc cp ./file.txt prodserver/deploy/       # Local to SSH anchor
anc cp prodserver/logs/ ./logs             # SSH anchor to local
anc cp server-a/data server-b/data         # SSH to SSH (via local relay)

anc cp src/ dst/ --exclude .git            # Exclude pattern
anc cp src/ dst/ --exclude .git --exclude node_modules
anc cp src/ dst/ --dry-run                 # Preview without copying
```

SSH credentials are injected the same way as `anc go` — in-memory agent or sshpass pipe. The source anchor's key or password is fetched from the vault at transfer time.

---

### VPN

```bash
anc vpn init <token>                 # Save provisioning token
anc vpn up                           # Bring up WireGuard tunnel
anc vpn up --debug                   # Verbose output
anc vpn down                         # Tear down tunnel
anc vpn status                       # Show lease and interface info
```

The VPN uses SPA (Single Packet Authorization) with X25519/AES-256-GCM for zero-exposure port knocking. The server only opens the WireGuard peer after validating a TOTP-authenticated encrypted UDP packet. The WireGuard private key is never written to disk — it is passed to the kernel directly and the config file is deleted immediately after interface setup.

---

## Server

The server is optional. Without it, the CLI works fully offline with local anchors that do not reference vault secrets.

The server provides:

- **Vault**: AES-256-GCM encrypted secrets with per-secret HKDF key derivation, versioning (up to 10), and user/group access control.
- **Anchor sync**: push/pull anchors across machines or team members.
- **WireGuard control plane**: peer registration, lease management, SPA knock listener.
- **Web UI**: secrets management, user administration.
- **Service tokens**: scoped API keys (`vault:read`, `vault:write`, `anchors:read`, `anchors:write`, `admin`) for CI/CD and Kubernetes init containers.
- **Auth**: local users (bcrypt) or LDAP/Active Directory.

See [server/README.md](server/README.md) for setup, configuration, API reference, and Kubernetes integration.

---

## Filter Expressions

Both `anc ls` and `anc pull` accept filter expressions:

```bash
anc ls -f "type=ssh"
anc ls -f "meta.env=prod AND type~ssh"
anc ls -f "groups~devops OR meta.project=infra"
```

Operators: `=` (exact), `!=` (not equal), `~` (contains), `!~` (not contains). Logical: `AND`, `OR`.

---

## Planned Features

- **Service token CLI (`anc token`)**: create and manage scoped API keys from the CLI without accessing the server UI. This is the primary integration path for Kubernetes and CI/CD pipelines — a pipeline requests only the scopes it needs, the token is short-lived, and Anchor is the single source of truth for secret injection.

- **GitHub SSH middleware**: use Anchor as a proxy layer for SSH-based Git access to organization repositories. Developer SSH keys are stored in the vault; Anchor validates identity and injects the key for the duration of the operation. Private keys are never distributed — the vault is the only copy.

- **Security audit and test coverage**: the codebase currently has no automated tests. Planned work includes unit and integration tests for vault operations, secret resolution, SPA packet handling, and the rsync transfer layer.

- **CSPRNG replacement**: several areas use Python's `random` module, which is not cryptographically secure. These will be replaced with `secrets` particularly in token generation, nonce handling, and any place randomness feeds into a security decision.

- **Distroless Dockerfile** 

- **Secure /dev/shm when private peer file key enters**

- **Considering a web plugin for secrets**