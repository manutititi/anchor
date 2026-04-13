# Graph Report - .  (2026-04-10)

## Corpus Check
- 103 files · ~43,622 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 844 nodes · 1430 edges · 41 communities detected
- Extraction: 76% EXTRACTED · 24% INFERRED · 0% AMBIGUOUS · INFERRED: 339 edges (avg confidence: 0.51)
- Token cost: 0 input · 0 output

## God Nodes (most connected - your core abstractions)
1. `AnchorClient` - 71 edges
2. `AnchorClientError` - 53 edges
3. `WireGuardProvider` - 46 edges
4. `NotAuthenticatedError` - 41 edges
5. `LogEntry` - 27 edges
6. `LDAPProvider` - 21 edges
7. `VPNRequestBody` - 21 edges
8. `BaseAnchor` - 18 edges
9. `SPAData` - 18 edges
10. `vpn_up()` - 16 edges

## Surprising Connections (you probably didn't know these)
- `SPA WireGuard VPN` --semantically_similar_to--> `anc vpn up Full SPA Flow`  [INFERRED] [semantically similar]
  README.md → docs/features/knock.md
- `Ephemeral SSH Agent Injection` --semantically_similar_to--> `Ephemeral ssh-agent with Isolated Socket`  [INFERRED] [semantically similar]
  README.md → docs/security/ssh.md
- `VPN Onboarding Full Flow` --semantically_similar_to--> `anc vpn up Full SPA Flow`  [INFERRED] [semantically similar]
  server/docs/vpn-onboarding.md → docs/features/knock.md
- `Kubernetes Init Container Integration` --semantically_similar_to--> `Context B: Ephemeral Docker/K8s Container`  [INFERRED] [semantically similar]
  server/README.md → docs/ci-xapi/xapi-discussion.md
- `Self-Contained CI Token (anc_v1_ with embedded WG config)` --semantically_similar_to--> `VPN Provision Token (self-contained, base64 JSON)`  [INFERRED] [semantically similar]
  docs/ci-xapi/xapi-discussion.md → server/docs/vpn-onboarding.md

## Hyperedges (group relationships)
- **SPA Knock Full Stack: Packet, Crypto, Protocol, Anti-Replay, Lease** — knock_spa_packet, knock_spa_crypto, knock_protocol, knock_anti_replay, knock_lease_onboarding, knock_uid_to_ip [EXTRACTED 0.95]
- **VPN Security Layered Defense: SPA + TOTP + Anti-Replay + Client Isolation + JWT-in-Tunnel** — knock_spa_crypto, vpn_totp_seed_enc, knock_anti_replay, vpn_client_isolation, vpn_jwt_inside_tunnel, knock_forward_secrecy [EXTRACTED 0.92]
- **SSH Secret Injection Chain: Vault Marker -> In-Memory Fetch -> Ephemeral Agent -> Native SSH** — readme_vault_marker, readme_secret_resolution, ssh_vault_reference, ssh_ephemeral_agent [INFERRED 0.88]

## Communities

### Community 0 - "Server Core & Logging"
Cohesion: 0.03
Nodes (88): BaseModel, Exception, LogEntry, AnchorUpsert, ErrorResponse, IntegrationSummary, LDAPConfig, LeaseInfo (+80 more)

### Community 1 - "CLI Client Layer"
Cohesion: 0.04
Nodes (102): AnchorClient, AnchorClientError, base_url(), get_client(), get_collection(), get_db(), NotAuthenticatedError, AnchorClient — authenticated HTTP client for the Anchor server.  Usage:     clie (+94 more)

### Community 2 - "Anchor Models & Types"
Cohesion: 0.06
Nodes (48): ABC, AnsibleAnchor, _Base, BaseAnchor, DockerAnchor, DockerInfo, EnvAnchor, FilesAnchor (+40 more)

### Community 3 - "Integration Provider Base"
Cohesion: 0.06
Nodes (31): IntegrationProvider, Unique lowercase identifier (e.g. 'ldap', 'saml')., True if the provider is configured and marked as enabled., Base class for all external integration providers.      Each provider encapsulat, _check_enabled(), get_user_groups(), ldap_authenticate(), LDAP auth shim — delegates to integrations/ldap/provider.py.  This module keeps (+23 more)

### Community 4 - "VPN Integration Runtime"
Cohesion: 0.06
Nodes (33): IntegrationProvider, _cleanup_expired(), _get_sidecar_client(), _in_blackout(), _manage_blackouts(), _now_utc(), Async background janitor: cleans up expired VPN leases and manages blackout wind, For every active lease whose user has a blackout window configured:       - Ente (+25 more)

### Community 5 - "VPN SPA Documentation"
Cohesion: 0.05
Nodes (51): Refactor Session Workflow (project.json driven), Anti-Replay via MongoDB Nonce Collection, Forward Secrecy via Ephemeral X25519 Key, Onboarding Lease (5-minute TTL), KnockProtocol (asyncio UDP listener), Silent Drop Policy (no UDP response), SPA Crypto: X25519 ECDH + HKDF + AES-256-GCM, SPA v2 Packet (186 bytes) (+43 more)

### Community 6 - "SPA Crypto Protocol"
Cohesion: 0.05
Nodes (39): build_packet(), _derive_aes_key(), get_spa_pubkey_b64(), init_server_keypair(), parse_packet(), SPA v2 (Single Packet Authorization) — ECIES packet builder / parser.  Packet la, Return the server SPA public key (base64). Empty if not initialized., HKDF-SHA256 over the X25519 shared secret → 32-byte AES key. (+31 more)

### Community 7 - "CLI Configuration"
Cohesion: 0.08
Nodes (31): BaseSettings, clear_credentials(), Config, _config_dir(), _data_dir(), ensure_dirs(), get_server_url(), get_token() (+23 more)

### Community 8 - "Local Anchor Store"
Cohesion: 0.1
Nodes (28): anchor_exists(), anchor_path(), _decrypt_config(), delete_anchor(), delete_config(), _encrypt_config(), get_config(), get_masked_config() (+20 more)

### Community 9 - "Server Admin API"
Cohesion: 0.08
Nodes (23): admin_create_token(), admin_create_user(), admin_delete_user(), admin_get_logs(), admin_list_secrets(), admin_list_tokens(), admin_list_users(), admin_revoke_token() (+15 more)

### Community 10 - "AST Filter Engine"
Cohesion: 0.13
Nodes (21): AndNode, Condition, _eval_condition(), _eval_node(), _get_nested(), matches_filter(), _normalize(), OrNode (+13 more)

### Community 11 - "RC Subsystem"
Cohesion: 0.15
Nodes (19): _apply_files(), _apply_ownership(), _build_preview(), _download(), _escalate_if_needed(), anc rc — restore files from a files anchor to the filesystem.  Examples:     anc, Re-exec as root if any destination path requires it., Build a list of (tag, dest_path) describing pending changes. (+11 more)

### Community 12 - "WireGuard Interface Manager"
Cohesion: 0.17
Nodes (17): add_peer(), check_interface(), DumpResult, InterfaceInfo, Low-level WireGuard command helpers.  Every function wraps a single `wg` invocat, Remove a peer from the live interface and clean up its IP route., Parsed row from `wg show <iface> dump` (peer lines)., Parsed first row from `wg show <iface> dump` (interface line). (+9 more)

### Community 13 - "CR Config Rendering"
Cohesion: 0.22
Nodes (15): _as_relative_to_home(), _build_files(), cr(), _encode_file(), _get_perm(), _make_entry(), anc cr — capture files/directories into a files anchor.  Examples:     anc cr my, Expand ~ and resolve to absolute. (+7 more)

### Community 14 - "Anchor Creation Commands"
Cohesion: 0.26
Nodes (15): _check_overwrite(), _create_mask_anchor(), _create_path_anchor(), _create_ssh_anchor(), _create_url_anchor(), _looks_like_path(), _now(), _parse_groups() (+7 more)

### Community 15 - "Server Middleware & App Core"
Cohesion: 0.12
Nodes (7): BaseHTTPMiddleware, APIKeyMiddleware, WireGuard Sidecar — FastAPI application entry point.  Security: every request mu, Simple API-Key guard.      Rejects any request that does not carry a valid X-API, AuthMiddleware, For service tokens: require a specific scope. JWT users pass automatically., require_scope()

### Community 16 - "Sidecar Peer Management"
Cohesion: 0.21
Nodes (13): delete_peer(), get_name(), load_metadata(), Peer metadata persistence.  The WireGuard kernel module only stores public keys., Load the metadata file, returning an empty dict if missing or corrupt., Atomically write the metadata file., Return the full metadata dict (pubkey → {name, ...})., Return the human-readable name for a pubkey, or None. (+5 more)

### Community 17 - "Vault Access Control"
Cohesion: 0.15
Nodes (12): can_delete(), can_edit(), can_manage_acl(), can_read_plaintext(), is_visible(), Determine if a user/token can read a secret.      Access model:     - JWT users:, Determine if a user/token may receive the decrypted plaintext of a secret., Can change non-ACL fields (note, host, paths, etc.) (+4 more)

### Community 18 - "Mask Anchor Feature"
Cohesion: 0.3
Nodes (11): _add_rule(), _apply_mask(), _apply_unmask(), _load_or_fail(), mask(), anc mask — sanitize text by replacing sensitive data with placeholders.  Usage:, Sanitize text by replacing sensitive data with consistent placeholders., Apply mask rules to text. Returns (masked_text, mapping). (+3 more)

### Community 19 - "Filter/Match Utilities"
Cohesion: 0.22
Nodes (8): expr_to_lambda(), get_nested(), matches_filter(), normalize_value(), Convierte strings comunes a tipos útiles: bool, int, etc., Convierte una expresión tipo: env=prod AND project~web     en una función que ev, Evalúa si un diccionario cumple con una expresión de filtro., Permite acceder a claves anidadas usando notación punto, ej: endpoint.base_url

### Community 20 - "VPN OTP & TOTP"
Cohesion: 0.22
Nodes (9): assign_vpn_uid(), generate_otp_seed(), get_otp_seed(), OTP seed management and vpn_uid assignment for the SPA flow.  assign_vpn_uid:, Validate a 6-digit TOTP code against the user's seed. valid_window=1 (±30 s)., Return the existing VPN UID for username, or atomically assign the next one., Generate a new TOTP seed for username, encrypt it with the vault master key,, Return the plaintext TOTP seed for username, or None if not configured. (+1 more)

### Community 21 - "IP Pool Allocation"
Cohesion: 0.2
Nodes (9): allocate_ip(), free_ip(), init_pool(), pool_status(), Atomic IP allocation pool backed by MongoDB.  Collection: vpn_ip_pool Schema: {, Populate vpn_ip_pool from a CIDR subnet.     Only inserts IPs that are not alrea, Atomically allocate a free IP to uid.     Uses findOneAndUpdate for race-conditi, Release a leased IP back to the free pool. (+1 more)

### Community 22 - "List Command"
Cohesion: 0.67
Nodes (5): _location(), ls(), _ls_local(), _ls_remote(), _print_table()

### Community 23 - "CLI Output Utilities"
Cohesion: 0.33
Nodes (1): Shared Rich console instances and output helpers.

### Community 24 - "Metadata Detection"
Cohesion: 0.33
Nodes (5): detect_docker(), detect_git(), Local metadata detectors used when creating anchors.  - detect_git(path)    → di, Return git metadata for the given directory, or None if not a repo.     Runs fas, Return Docker Compose metadata if docker-compose.yml exists in path.     Returns

### Community 25 - "Shared Error Types"
Cohesion: 0.7
Nodes (4): AccessDeniedError, ConflictError, ErrorDetail, NotFoundError

### Community 26 - "Login Command"
Cohesion: 0.5
Nodes (3): login(), anc login — authenticate with the Anchor server.  Saves the JWT token to ~/.conf, Authenticate with the Anchor server and save credentials.

### Community 27 - "Path Command"
Cohesion: 0.5
Nodes (3): path(), anc path <name> — print the filesystem path for a local anchor.  Designed for sh, Print the filesystem path of a local anchor (for use with cd).

### Community 28 - "Vault Versioning"
Cohesion: 0.5
Nodes (0): 

### Community 29 - "CLI Entry Point"
Cohesion: 0.67
Nodes (1): Anchor CLI entry point.  Registered as the `anc` binary via pyproject.toml:

### Community 30 - "FastAPI Server Entry"
Cohesion: 0.67
Nodes (0): 

### Community 31 - "Auth Group Checker"
Cohesion: 0.67
Nodes (2): check_anchor_access(), Lanza HTTP 403 si el usuario no pertenece a ningún grupo autorizado en el anchor

### Community 32 - "Test Configuration"
Cohesion: 1.0
Nodes (1): Pytest configuration for server/code tests. Run from server/code/:  python -m py

### Community 33 - "Admin Dashboard"
Cohesion: 1.0
Nodes (0): 

### Community 34 - "WG Key Security Notes"
Cohesion: 1.0
Nodes (2): Replaced: WG privkey in /dev/shm (tmpfs, 100ms window), WireGuard Private Key via Anonymous Pipe (no filesystem)

### Community 35 - "MongoDB Init Script"
Cohesion: 1.0
Nodes (0): 

### Community 36 - "Integration Rationale"
Cohesion: 1.0
Nodes (1): Probe the external service. Must not raise — return TestResult(ok=False)

### Community 37 - "GitHub SSH Middleware Plan"
Cohesion: 1.0
Nodes (1): GitHub SSH Middleware (Planned)

### Community 38 - "Service Token CLI Plan"
Cohesion: 1.0
Nodes (1): Service Token CLI anc token (Planned)

### Community 39 - "SPA Server Key Config"
Cohesion: 1.0
Nodes (1): SPA_PRIVKEY_B64 Server Key (env var, in-memory)

### Community 40 - "VPN Onboarding Troubleshooting"
Cohesion: 1.0
Nodes (1): VPN Onboarding Troubleshooting Guide

## Knowledge Gaps
- **169 isolated node(s):** `Anchor CLI entry point.  Registered as the `anc` binary via pyproject.toml:`, `Configuration and credential management.  Config:      ~/.config/anchor/config.t`, `XDG-compliant config directory. Respects $XDG_CONFIG_HOME on Linux,     %APPDATA`, `Local anchor JSON storage. Overridable via $ANCHOR_DIR.`, `Write a simple nested TOML dict (one level of sections).` (+164 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Test Configuration`** (2 nodes): `conftest.py`, `Pytest configuration for server/code tests. Run from server/code/:  python -m py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Admin Dashboard`** (2 nodes): `dashboard.py`, `dashboard()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `WG Key Security Notes`** (2 nodes): `Replaced: WG privkey in /dev/shm (tmpfs, 100ms window)`, `WireGuard Private Key via Anonymous Pipe (no filesystem)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `MongoDB Init Script`** (1 nodes): `init-mongo.js`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Integration Rationale`** (1 nodes): `Probe the external service. Must not raise — return TestResult(ok=False)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `GitHub SSH Middleware Plan`** (1 nodes): `GitHub SSH Middleware (Planned)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Service Token CLI Plan`** (1 nodes): `Service Token CLI anc token (Planned)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `SPA Server Key Config`** (1 nodes): `SPA_PRIVKEY_B64 Server Key (env var, in-memory)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `VPN Onboarding Troubleshooting`** (1 nodes): `VPN Onboarding Troubleshooting Guide`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `WireGuardProvider` connect `VPN Integration Runtime` to `Server Core & Logging`, `Integration Provider Base`?**
  _High betweenness centrality (0.163) - this node is a cross-community bridge._
- **Why does `AnchorClient` connect `CLI Client Layer` to `Anchor Models & Types`?**
  _High betweenness centrality (0.107) - this node is a cross-community bridge._
- **Are the 60 inferred relationships involving `AnchorClient` (e.g. with `LocalHandler` and `LocalHandler — handle 'local' type anchors.  Prints the expanded filesystem path`) actually correct?**
  _`AnchorClient` has 60 INFERRED edges - model-reasoned connections that need verification._
- **Are the 46 inferred relationships involving `AnchorClientError` (e.g. with `anc go <name>    — dispatch to the handler for the anchor's type. anc _type <nam` and `Dispatch to the appropriate handler based on the anchor's type.`) actually correct?**
  _`AnchorClientError` has 46 INFERRED edges - model-reasoned connections that need verification._
- **Are the 34 inferred relationships involving `WireGuardProvider` (e.g. with `VPN endpoints — WireGuard lease management.  User endpoints (any authenticated u` and `Upsert a vault secret using the same flat schema as vault/router.py.      uid`) actually correct?**
  _`WireGuardProvider` has 34 INFERRED edges - model-reasoned connections that need verification._
- **Are the 37 inferred relationships involving `NotAuthenticatedError` (e.g. with `anc go <name>    — dispatch to the handler for the anchor's type. anc _type <nam` and `Dispatch to the appropriate handler based on the anchor's type.`) actually correct?**
  _`NotAuthenticatedError` has 37 INFERRED edges - model-reasoned connections that need verification._
- **Are the 22 inferred relationships involving `LogEntry` (e.g. with `VPN endpoints — WireGuard lease management.  User endpoints (any authenticated u` and `Upsert a vault secret using the same flat schema as vault/router.py.      uid`) actually correct?**
  _`LogEntry` has 22 INFERRED edges - model-reasoned connections that need verification._