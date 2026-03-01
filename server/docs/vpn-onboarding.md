# VPN Onboarding — Guía completa

Anchor usa **SPA (Single Packet Authorization)** para levantar túneles WireGuard sin exponer ningún puerto HTTP a internet. El servidor solo escucha en un puerto UDP opaco; si el paquete no es válido, se descarta en silencio.

## Índice

1. [Arquitectura del flujo](#arquitectura-del-flujo)
2. [Requisitos previos](#requisitos-previos)
3. [Setup del servidor (admin)](#setup-del-servidor-admin)
4. [Provisionar un usuario (admin)](#provisionar-un-usuario-admin)
5. [Primera conexión del cliente](#primera-conexión-del-cliente)
6. [Uso diario](#uso-diario)
7. [Revocar acceso](#revocar-acceso)
8. [Troubleshooting](#troubleshooting)

---

## Arquitectura del flujo

```
Cliente                         Servidor
───────                         ────────

wg genkey → privkey, pubkey
TOTP.now() → otp
build_packet(uid, otp, pubkey, seed)
       ──── UDP knock_port ────►  KnockProtocol:
                                    parse_packet()   ← crypto validation
                                    nonce dedup      ← anti-replay (60s TTL)
                                    verify_otp()     ← TOTP ±30s
                                    uid_to_ip(vpn_uid, subnet)  ← determinístico
                                    sidecar.add_peer(pubkey, ip/32)
                                    vpn_leases ← state=onboarding, TTL 5min

wg-quick up /tmp/anc-vpn.conf
  Address    = subnet.N/32      (IP del usuario, fija por uid)
  AllowedIPs = server_ip/32    (túnel restringido: solo el servidor)

── handshake WireGuard ────────► (ambos tienen la pubkey del otro)

POST /auth/login               ► JWT  (o usa token ya guardado)
POST /vpn/promote              ► lease onboarding → active
  ◄── { assigned_ip, server_pubkey, server_endpoint, wg_conf }

wg syncconf anc-vpn            (hot-reload, sin bajar el túnel)
  AllowedIPs = 0.0.0.0/0      (túnel completo)

✓ Túnel activo                 vpn_leases: state=active
```

**Propiedades de seguridad:**
- El servidor nunca expone HTTP/HTTPS a internet directamente.
- El paquete SPA lleva OTP + timestamp + pubkey cifrado con AES-256-GCM; la clave deriva del seed TOTP con HKDF-SHA256.
- Anti-replay por nonce único (TTL 60 s en MongoDB).
- Ventana de timestamp ±2 s.
- Un lease no promovido en 5 minutos es eliminado automáticamente por el janitor.
- IP asignada determinísticamente: `subnet_base + vpn_uid`. Sin pool ni DB en el knock.

---

## Requisitos previos

### Servidor

| Componente | Estado necesario |
|---|---|
| Anchor server | Corriendo |
| WireGuard sidecar | Corriendo y accesible desde Anchor |
| MongoDB | Inicializado con `init-mongo.js` |
| Puerto UDP `knock_port` | Abierto en firewall (ej. 62201/udp) |
| Puerto UDP `51820` (WG) | Abierto en firewall |

### Cliente

```bash
# wireguard-tools
sudo apt install wireguard-tools     # Debian/Ubuntu
sudo dnf install wireguard-tools     # Fedora/RHEL

# Dependencias Python para anc vpn
pip install 'anchor-cli[vpn]'
# instala: pyotp>=2.9, pycryptodome>=3.19
```

---

## Setup del servidor (admin)

### 1. Activar el knock listener

**Opción A — vía UI:**
Abre Anchor → **Integrations → WireGuard** y configura:

| Campo | Ejemplo | Descripción |
|---|---|---|
| `sidecar_url` | `http://localhost:8000` | URL interna del sidecar |
| `subnet` | `10.8.0.0/24` | Subred VPN |
| `server_endpoint` | `vpn.ejemplo.com:51820` | Endpoint público WireGuard (host:puerto) |
| `knock_port` | `62201` | Puerto UDP del knock listener (**0 = desactivado**) |
| `lease_hours` | `8` | Duración del lease activo |

**Opción B — vía API:**
```bash
curl -X PUT https://anchor.ejemplo.com/integrations/wireguard \
  -H "Authorization: Bearer $ADMIN_JWT" \
  -H "Content-Type: application/json" \
  -d '{
    "sidecar_url": "http://localhost:8000",
    "api_key": "tu-api-key-sidecar",
    "subnet": "10.8.0.0/24",
    "server_endpoint": "vpn.ejemplo.com:51820",
    "knock_port": 62201,
    "lease_hours": 8,
    "enabled": true
  }'
```

**Opción C — variable de entorno** (sobreescribe la config de la integración):
```bash
VPN_KNOCK_PORT=62201
VPN_SERVER_PORT=17017   # puerto interno del Anchor server (default 17017)
```

El knock listener arranca automáticamente cuando el servidor Anchor se reinicia si `knock_port > 0`. Verifica en los logs:
```
INFO: SPA knock listener active on udp 0.0.0.0:62201
```

---

## Provisionar un usuario (admin)

> **Un solo comando. Un solo token para el usuario.**

El usuario debe tener una cuenta en Anchor (local o LDAP). Luego:

```bash
curl -X POST https://anchor.ejemplo.com/vpn/admin/users/alice/otp \
  -H "Authorization: Bearer $ADMIN_JWT"
```

Respuesta:
```json
{
  "vpn_uid": 2,
  "provisioning_url": "otpauth://totp/Anchor:alice?secret=JBSWY3D...&issuer=Anchor",
  "provision_token": "eyJ1aWQiOiJhbGljZSIsInZwbl91aWQiOjIsInNlZWRfYjMyIjoiSkJTV1kzRC4uLiIsImtub2NrX2hvc3QiOiJ2cG4uZWplbXBsby5jb20iLCJrbm9ja19wb3J0Ijo2MjIwMSwic3VibmV0IjoiMTAuOC4wLjAvMjQiLCJzZXJ2ZXJfdnBuX3VpZCI6MSwic2VydmVyX2VuZHBvaW50IjoidnBuLmVqZW1wbG8uY29tOjUxODIwIiwic2VydmVyX3B1YmtleSI6ImFiYzEyMy4uLiIsInNlcnZlcl9wb3J0IjoxNzAxN30="
}
```

**Envía al usuario** (por Signal, correo cifrado, etc.):

1. **`provision_token`** — lo pega en el CLI (un solo campo, contiene todo)
2. **`provisioning_url`** — lo escanea con Google Authenticator / Aegis / Bitwarden para el OTP

El `provision_token` contiene automáticamente el endpoint del servidor, la public key de WireGuard, la subnet, el knock port y el seed TOTP. **El usuario no necesita saber su `vpn_uid` ni ningún detalle técnico.**

> Si el sidecar no está disponible en el momento de la provisión, `server_pubkey` quedará vacío en el token. El usuario deberá ejecutar `anc vpn up` y si falla, volver a generar el token cuando el sidecar esté activo.

---

## Primera conexión del cliente

### Opción A — no-interactiva (recomendada)

```bash
anc vpn init eyJ1aWQiOiJhbGljZSIsInZwbl91aWQiOjIs...
```

Salida:
```
VPN configured for user alice (IP: 10.8.0.2)
Config saved to /home/alice/.config/anchor/vpn.toml

Run anc vpn up to connect.
```

Luego:
```bash
anc vpn up
```

### Opción B — wizard interactivo

Si no tienes el token, `anc vpn up` sin config existente lanza el wizard. La primera pregunta es el token; si lo tienes, pégalo y listo. Si no, presiona Enter para el modo manual (pide cada campo).

```bash
anc vpn up

╭──────────────── anc vpn setup ─────────────────╮
│  VPN First-Time Setup                           │
│                                                 │
│  Ask your admin to run:                         │
│    POST /vpn/admin/users/{tu_usuario}/otp       │
│                                                 │
│  Te dará un provision token. Pégalo aquí.       │
╰─────────────────────────────────────────────────╯

Provision token (or press Enter for manual setup): eyJ1aWQiOiJhbGljZSIs...
Config saved to /home/alice/.config/anchor/vpn.toml
```

### Flujo automático tras la config

```
● Generating keypair…
● Knocking vpn.ejemplo.com:62201…
● Bringing up tunnel (onboarding mode)…
● Waiting for tunnel handshake…
● Authenticating…
● Promoting to full tunnel…

╭──────────── VPN Connected ─────────────╮
│ IP address      10.8.0.2               │
│ Server endpoint vpn.ejemplo.com:51820  │
│ Server pubkey   abc123…                │
│ Lease expires   2026-03-01 16:00 UTC   │
│ Interface       anc-vpn                │
╰─────────────────────────────────────────╯
```

Si el token JWT ya está guardado (de un `anc login` anterior), el paso de autenticación es transparente. Si no, pide usuario/contraseña una sola vez.

---

## Uso diario

```bash
anc vpn up      # conectar
anc vpn status  # ver estado (lease servidor + wg show local)
anc vpn down    # desconectar
```

### Re-provisionar (nuevo dispositivo o seed perdido)

```bash
# Admin revoca el anterior y genera uno nuevo
curl -X DELETE https://anchor.ejemplo.com/vpn/admin/users/alice/otp \
  -H "Authorization: Bearer $ADMIN_JWT"

curl -X POST https://anchor.ejemplo.com/vpn/admin/users/alice/otp \
  -H "Authorization: Bearer $ADMIN_JWT"
# → nuevo provision_token con el mismo vpn_uid
```

El `vpn_uid` (y por tanto la IP) se mantiene si el usuario ya lo tenía asignado — solo se regenera el seed TOTP.

---

## Revocar acceso

### Revocar lease activo (el propio usuario)

```bash
anc vpn down
```

### Revocar lease de cualquier usuario (admin)

```bash
curl -X DELETE https://anchor.ejemplo.com/vpn/admin/leases/alice \
  -H "Authorization: Bearer $ADMIN_JWT"
```

### Revocar acceso VPN permanente (admin)

Elimina el seed TOTP y el vpn_uid. Sin seed, no puede construir un paquete SPA válido.

```bash
curl -X DELETE https://anchor.ejemplo.com/vpn/admin/users/alice/otp \
  -H "Authorization: Bearer $ADMIN_JWT"
```

El usuario tendrá que ejecutar `anc vpn init <nuevo_token>` si se le reprovisiona.

---

## Troubleshooting

### Handshake timeout (10 s)

| Causa | Verificación | Solución |
|---|---|---|
| `knock_port` no abierto en firewall | `nc -u vpn.ejemplo.com 62201` (silencio = OK; "refused" = bloqueado) | Abrir 62201/udp en el firewall |
| Knock listener no arrancó | `grep "knock listener" <logs_anchor>` | Verificar `knock_port > 0` en la integración; reiniciar Anchor |
| `server_endpoint` o `server_pubkey` incorrectos | `wg show wg0` en el servidor | Regenerar el token con el sidecar activo: `DELETE` + `POST /vpn/admin/users/alice/otp` |
| Puerto WireGuard (51820) bloqueado | `nc -u vpn.ejemplo.com 51820` | Abrir 51820/udp en el firewall |
| `vpn_uid` incorrecto (setup manual sin token) | Ver `assigned_ip` en el lease del servidor | Usar `anc vpn init <token>` en lugar de setup manual |

### OTP inválido (knock silencioso, no registra peer)

| Causa | Solución |
|---|---|
| `seed_b32` incorrecto | Regenerar token: `DELETE` + `POST /vpn/admin/users/alice/otp` |
| Desfase de reloj > 30 s | `sudo systemctl restart systemd-timesyncd` en el cliente |
| Desfase de reloj > 2 s (timestamp del paquete) | Mismo fix de NTP |

### Error de autenticación post-handshake

```
Authentication failed. Tunnel closed.
```

- Contraseña incorrecta → el servidor devuelve 401.
- El Anchor server no escucha en la interfaz WireGuard → verificar que `server_port` en el token coincide con el puerto real de Anchor.
- iptables bloqueando el tráfico al puerto 17017 en la interfaz `wg0` del servidor.

### `wg-quick up` falla: `Operation not permitted`

El usuario necesita `sudo` para `wg` y `wg-quick`. Añadir a `/etc/sudoers`:
```sudoers
alice ALL=(ALL) NOPASSWD: /usr/bin/wg, /usr/bin/wg-quick
```

### Verificación desde el servidor (admin)

```bash
# Leases activos
curl https://anchor.ejemplo.com/vpn/admin/leases \
  -H "Authorization: Bearer $ADMIN_JWT"

# Peers en WireGuard ahora mismo
curl http://localhost:8000/peers -H "X-API-Key: $WG_API_KEY"

# Logs del knock listener
docker compose logs -f anc-server | grep -iE "knock|spa"

# Estado WireGuard
docker compose exec wireguard wg show
```

### Limpiar y empezar de cero (cliente)

```bash
anc vpn down                      # bajar túnel si está activo
rm ~/.config/anchor/vpn.toml      # borrar config
anc vpn init <nuevo_token>        # inicializar con token nuevo
anc vpn up
```
