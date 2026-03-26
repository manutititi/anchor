# Knock — Single Packet Authorization (SPA v2)

El knock es el mecanismo por el que un cliente registra su peer WireGuard en el servidor con una sola ráfaga UDP cifrada, sin que el servidor exponga ningún puerto observable ni responda a nada.

---

## Visión de alto nivel

```
anc vpn up
  │
  ├─ 1. Genera keypair WireGuard (wg genkey)
  ├─ 2. Construye paquete SPA v2 de 186 bytes (ECIES + AES-256-GCM)
  ├─ 3. Envía 3× UDP al knock listener :62201
  │
  │   [servidor: knock.py → spa.py]
  │     ├─ parse_packet()    — descifra, valida timestamp
  │     ├─ anti-replay       — nonce único en MongoDB
  │     ├─ verify_otp()      — TOTP contra otp_seed_enc
  │     ├─ uid_to_ip()       — IP determinista desde vpn_uid
  │     ├─ sidecar.add_peer()— registra peer en WireGuard
  │     └─ insert lease      — state=onboarding, expires_in=5min
  │
  ├─ 4. sleep 5 s (da tiempo al sidecar)
  ├─ 5. wg-quick up (AllowedIPs = 10.13.13.1/32)
  ├─ 6. Espera handshake WireGuard (≤ 20 s)
  ├─ 7. POST /auth/login (por el túnel) → JWT
  ├─ 8. POST /vpn/promote → lease active + rutas completas
  └─ 9. hot-reload AllowedIPs sin bajar el túnel
```

---

## Paquete SPA v2 (186 bytes)

Definido en `server/code/vpn/spa.py` y replicado en `anchor/commands/vpn.py:_build_spa_packet()`.

```
┌─────────────────────────────────────────────────────────┐
│  32 B  ephemeral_pub   clave X25519 efímera del cliente │
│  12 B  nonce           nonce AES-GCM (os.urandom)       │
│ 122 B  ciphertext      payload cifrado (ver abajo)       │
│  16 B  tag             GCM authentication tag            │
│   4 B  version         \x00\x02\x00\x00                 │
└─────────────────────────────────────────────────────────┘
```

### Payload cifrado (122 bytes plaintext)

```
┌─────────────────────────────────────────────────────────┐
│  64 B  uid             username, null-padded             │
│   6 B  otp             código TOTP (ASCII, 6 dígitos)   │
│   8 B  timestamp       Unix epoch uint64 big-endian      │
│  44 B  wg_pubkey       clave pública WireGuard (base64)  │
└─────────────────────────────────────────────────────────┘
```

### Crypto

```
cliente genera X25519 efímero (eph_priv, eph_pub)
  ↓
DH: eph_priv.exchange(server_spa_pub) → shared_secret
  ↓
HKDF-SHA256(salt="spa-v2", info="spa-v2-aes-key") → aes_key (32 B)
  ↓
AES-256-GCM.encrypt(nonce, payload) → ciphertext + tag
  ↓
paquete = eph_pub + nonce + ciphertext + tag + version
```

El servidor realiza el camino inverso: `server_privkey.exchange(eph_pub)` → mismo `shared_secret`.

**Forward secrecy:** la clave efímera se genera nueva en cada knock. Filtrar `SPA_PRIVKEY_B64` del servidor no compromete sesiones pasadas.

---

## Código: construcción del paquete (CLI)

`anchor/commands/vpn.py` — función `_build_spa_packet()` (línea ~229)

```python
# 1. Cargar clave pública del servidor (del provision token)
server_pub = X25519PublicKey.from_public_bytes(base64.b64decode(server_spa_pubkey_b64))

# 2. Generar clave efímera (nueva en cada llamada)
eph_priv = X25519PrivateKey.generate()
eph_pub_raw = eph_priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)

# 3. ECDH → HKDF → AES key
shared = eph_priv.exchange(server_pub)
aes_key = HKDF(SHA256(), 32, b"spa-v2", b"spa-v2-aes-key").derive(shared)

# 4. Ensamblar payload en claro
payload = uid_bytes(64) + otp_bytes(6) + struct.pack(">Q", ts) + wg_pubkey_bytes(44)

# 5. Cifrar
nonce = os.urandom(12)
ct_with_tag = AESGCM(aes_key).encrypt(nonce, payload, None)

# 6. Ensamblar paquete
return eph_pub_raw + nonce + ciphertext + tag + VERSION
```

El CLI envía el mismo paquete **3 veces** con 0.5 s de separación (`vpn.py:602`). UDP no garantiza entrega; con 3 intentos se minimizan pérdidas de red sin riesgo de replay (el nonce es el mismo — el servidor acepta el primero y descarta los duplicados silenciosamente).

---

## Código: procesamiento del knock (servidor)

### `server/code/vpn/spa.py` — `parse_packet()`

Valida y descifra el paquete. Retorna `None` en cualquier fallo (semántica de descarte silencioso):

1. `len(data) != 186` → drop
2. `data[182:] != b"\x00\x02\x00\x00"` → drop (versión incorrecta)
3. DH + HKDF + AES-GCM decrypt — cualquier excepción → drop
4. `abs(time.time() - ts) > 30` → drop (timestamp fuera de ventana)
5. Retorna `SPAData(uid, otp, timestamp, wg_pubkey)`

### `server/code/vpn/knock.py` — `KnockProtocol._process()`

Ejecuta los pasos de negocio **en un thread-pool executor** (no bloquea el event loop asyncio):

| Paso | Código | Descripción |
|---|---|---|
| 1 | `parse_packet(data)` | Descifrado ECIES + validación de timestamp |
| 2 | `vpn_nonces.insert_one({"nonce": nonce_hex})` | Anti-replay: índice único, falla si ya existe |
| 3 | `verify_otp(spa.uid, spa.otp)` | TOTP contra semilla cifrada en MongoDB |
| 4 | `users.find_one({"username": spa.uid})` | Obtener `vpn_uid` entero para calcular IP |
| 5 | `uid_to_ip(vpn_uid, subnet)` | IP determinista: `network_address + vpn_uid` |
| 6 | `_handle_existing_lease()` (si existe) | Limpiar peer antiguo + borrar lease previo |
| 7 | `sidecar.add_peer(wg_pubkey, assigned_ip, uid)` | Registrar peer en WireGuard vía sidecar HTTP |
| 8 | `vpn_leases.insert_one({state="onboarding"})` | Lease con expiración de 5 minutos |

Cualquier fallo en cualquier paso → `return` silencioso, sin respuesta al cliente.

### Política de leases existentes (`_handle_existing_lease`)

```
estado del lease existente     acción
─────────────────────────────  ──────────────────────────────────────────
onboarding (intento anterior)  remove_peer(pubkey_viejo) + delete lease
active (reconexión)            remove_peer(pubkey_viejo) + delete lease
expirado (cualquier estado)    remove_peer(pubkey_viejo) + delete lease
```

En todos los casos se elimina el peer antiguo y el lease antes de crear los nuevos. Esto permite reconexión sin intervención del admin.

---

## Ciclo de vida del listener

`server/code/vpn/knock.py` — `start_knock_listener()`

```python
# Llamado desde server.py lifespan via asyncio.create_task()
transport, _ = await loop.create_datagram_endpoint(
    lambda: KnockProtocol(subnet),
    local_addr=(host, port),   # "0.0.0.0", 62201
)
await asyncio.Future()  # corre hasta CancelledError (shutdown del servidor)
```

El listener arranca junto con el servidor FastAPI. Comparte el namespace de red con el contenedor WireGuard (`network_mode: "service:wireguard"` en docker-compose), por lo que puede escuchar en el mismo host que el puerto UDP 51820.

---

## Flujo completo `anc vpn up` (SPA path)

```
anc vpn up
  │
  ├─[1] _load_vpn_config()               Lee ~/.config/anchor/vpn.toml
  ├─[2] _wg_genkey()                     wg genkey | wg pubkey (en memoria)
  ├─[3] Prompt TOTP
  │     _build_spa_packet(uid, otp, pubkey, spa_pubkey_b64)
  │     sock.sendto(pkt, (knock_host, 62201))  × 3
  │
  │   ─── UDP 186 bytes ────────────────────────────────────────────►
  │                                    KnockProtocol.datagram_received()
  │                                      asyncio.ensure_future(_handle())
  │                                        loop.run_in_executor(_process())
  │                                          parse_packet()    ← spa.py
  │                                          anti-replay nonce
  │                                          verify_otp()
  │                                          uid_to_ip()
  │                                          _handle_existing_lease()
  │                                          sidecar.add_peer()
  │                                          vpn_leases.insert(onboarding)
  │   ◄─── sin respuesta ───────────────────────────────────────────
  │
  ├─[4] time.sleep(5)                    Espera a que el sidecar procese
  ├─[5] _wg_up(privkey, my_ip,           wg-quick up /dev/shm/anc-vpn.conf
  │           server_pubkey,             AllowedIPs = 10.13.13.1/32
  │           server_endpoint,           (solo alcanza al servidor)
  │           f"{server_vpn_ip}/32")
  │
  ├─[6] _wait_for_handshake(timeout=20)  Polling wg show latest-handshakes
  │     si timeout → _wg_down() + exit(1)
  │
  ├─[7] POST http://10.13.13.1:17017/auth/login
  │     ◄── JWT ──
  │
  ├─[8] POST http://10.13.13.1:17017/vpn/promote  (JWT en header)
  │     ◄── {assigned_ip, server_pubkey, server_endpoint, routes, lease_expires}
  │          [servidor: lease → state=active, AllowedIPs ampliados]
  │
  ├─[9] _wg_update_routes(server_pubkey, routes_list)
  │     sudo wg set anc-vpn peer <server_pubkey> allowed-ips <routes>
  │     sudo ip route flush dev anc-vpn
  │     sudo ip route add <route> dev anc-vpn  (por cada ruta)
  │
  └─[10] Panel "VPN Connected"
```

---

## Archivos clave

| Archivo | Responsabilidad |
|---|---|
| `server/code/vpn/spa.py` | Constantes del paquete, `build_packet()`, `parse_packet()`, `uid_to_ip()` |
| `server/code/vpn/knock.py` | `KnockProtocol` (asyncio UDP), `start_knock_listener()`, política de leases |
| `server/code/vpn/otp.py` | `verify_otp()` — TOTP contra semilla cifrada en MongoDB |
| `server/code/vpn/router.py` | `POST /vpn/promote`, `GET /vpn/sync`, endpoints admin OTP |
| `anchor/commands/vpn.py` | `_build_spa_packet()`, `vpn_up()`, `_wg_up()`, `_wait_for_handshake()` |

---

## Colecciones MongoDB implicadas

| Colección | Uso |
|---|---|
| `vpn_nonces` | Anti-replay: `{nonce, created_at}` con TTL + índice único en `nonce` |
| `vpn_leases` | `{uid, pubkey, assigned_ip, state, expires_at, created_at}` |
| `users` | Fuente de `vpn_uid` entero y `otp_seed_enc` |
