# X-API / CI-CD Integration — Design Discussion

> Status: exploratory. The ideas here are not final. Core implementation patterns are
> defined; the surface API and UX are still open.

---

## Problem

The anchor server runs behind a WireGuard VPN. CI/CD systems (GitHub Actions, GitLab,
Kubernetes jobs, Docker-based runners) need to reach it without a human login session.
The existing service token system (`anc_*`) provides credential-level auth but does not
address the network layer.

The goal is to make automated systems first-class principals in the anchor ecosystem —
same group model, same CLI, no new paradigm to learn.

---

## Core idea

A CI/CD principal needs two things to function:

1. **Network identity** — a WireGuard peer with a static, reserved IP
2. **API credential** — a scoped service token

These are provisioned together as a single operation and treated as one logical entity.

---

## Two deployment contexts

### Context A — Persistent VM runner (self-hosted)

The runner machine is long-lived. WireGuard can be installed at the host level once.

```
Layer 1 (static, host level):  wg.conf  — installed once, never in job env vars
Layer 2 (ephemeral, job level): ANC_TOKEN — short TTL, generated per pipeline run
```

The WireGuard connection stays up across jobs. A leaked job token does not expose the
VPN config. Revoking the runner peer removes network access for all future jobs.

### Context B — Ephemeral Docker / Kubernetes

Each job is a fresh container. Host access is not available. The kernel WireGuard module
may not be accessible.

```
Single artifact: ANC_TOKEN (self-contained, short TTL)
VPN:            boringtun / wireguard-go (userspace, no kernel module, no --privileged)
```

`anc connect` detects the context and uses the appropriate mechanism.

---

## Token format

For context B, the token must be self-contained. Proposed encoding:

```
anc_v1_<base64url(payload)>
```

Payload (JSON, signed by server):

```json
{
  "credential": "<raw api token>",
  "wg": {
    "privkey":  "<client private key>",
    "pubkey":   "<client public key>",
    "address":  "10.13.13.X/32",
    "endpoint": "vpn.host:51820",
    "server_pubkey": "<server public key>",
    "dns":      "10.13.13.1"
  },
  "groups": ["infra"],
  "exp": 1234567890
}
```

The payload is signed (HMAC-SHA256) with the server's JWT secret so it cannot be
tampered with. The private key is visible to whoever holds the token — treat it like a
certificate, not a password.

---

## Security model

| Threat | Mitigation |
|---|---|
| Token leaked in CI logs | Short TTL — expires before it can be acted on |
| Token stolen | `anc token revoke <name>` — removes WireGuard peer + invalidates credential in one step |
| Runner compromised (context A) | Revoke the runner's static peer — all future jobs blocked at network level |
| Scope creep | Token inherits groups from creation — accesses only what that group can access |

Revocation is **network-level**, not just credential-level. The attacker loses both the
API credential and the WireGuard peer simultaneously.

---

## Group inheritance

Service tokens inherit the group model used by human users. No separate scope system.

```
anc token create ci-deploy --groups infra --ttl 1h
```

This token has exactly the same access as a human member of the `infra` group. The
`access.py` logic in vault and anchors is unchanged — it checks group membership, which
now applies to both users and tokens.

---

## CLI surface (proposed)

```bash
# Provision a runner (context A — persistent VM)
anc token provision <name> --groups <groups>
# → installs wg.conf on runner, registers peer in sidecar + MongoDB
# → creates long-lived runner credential

# Create a job token (context A — issued per run from the runner)
anc token issue <runner-name> --ttl 30m
# → short-lived token, no WireGuard config embedded

# Create a self-contained token (context B — ephemeral Docker/K8s)
anc token create <name> --groups <groups> --ttl 1h
# → full token with embedded WireGuard config

# Connect (works in both contexts)
anc connect
# → context A: wg-quick up (kernel WireGuard, wg.conf already present)
# → context B: starts boringtun userspace tunnel from token payload

# Revoke (both peer and credential)
anc token revoke <name>
```

---

## Peer persistence

WireGuard sidecar currently does not persist peers across restarts — dynamic peers are
lost on restart. This affects both human VPN users and CI tokens.

Required: a `vpn_peers` collection in MongoDB storing active peers. On sidecar startup,
reload all peers via `wg syncconf`. `add_peer()` and `remove_peer()` in the sidecar
write through to MongoDB.

This makes peer registration idempotent and survivable across restarts.

```
vpn_peers: {
  pubkey:     str,
  allowed_ip: str,       # 10.13.13.X/32
  owner:      str,       # token name or username
  owner_type: str,       # "token" | "user"
  created_at: datetime,
  expires_at: datetime | null
}
```

---

## Re-registration endpoint

For context B (ephemeral containers), the container may restart mid-session and lose
the userspace WireGuard tunnel. A lightweight re-registration endpoint allows the
container to reconnect without a new token:

```
POST /vpn/peer/register
Authorization: Bearer anc_xxx
```

Server validates token, looks up the peer associated with it, calls `sidecar.add_peer()`
with the stored pubkey and IP. Idempotent. No knock, no TOTP.

---

## What is NOT changing

- The existing knock / SPA flow for human VPN users — untouched
- The vault and anchor ACL logic — unchanged, tokens use the same group checks
- The `anc_*` token prefix and SHA256 storage model
- The `X-API-Key` header support for Kubernetes init containers

---

## Open questions

- Should `anc token create` (context B) require admin or can group members self-serve?
- TTL enforcement: should the WireGuard peer also expire at the same time as the token?
- Should `boringtun` be bundled in the `anchor-cli[vpn]` extra or required separately?
- Is the embedded privkey acceptable risk for the target use cases, or do we need
  server-assisted decryption (token unusable without a server handshake)?
